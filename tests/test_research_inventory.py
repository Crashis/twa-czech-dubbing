"""Offline regressions for commander ownership, original facts and research-only exports."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.inventory.names import fnv1
from tools.inventory.localization import CHAT_TAG_PREFIX, chat_tag_events, emote_spellings
from tools.inventory.crosscheck import pair_overlaps, recording_links
from tools.inventory.research_export import describe, pilot_battle_mix
from tools.inventory.research_audit import audit_commander
from tools.inventory.original_audio import extract_decode, private_directory
from tools.inventory.research_graph import UsageGraph, ACTOR, safety
from tools.inventory.research_metadata import FIELDS, duplicate_groups, read_csv, write_csv, transcript, validate_rows, validate_research
from tools.inventory.voice_map import resolve_bank
from tools.installer.catalog import discover
from tools.resources import ROOT


def field(value):
    return {'value': str(value)}


def sound(sid, mid=42):
    return {'id': sid, 'type': 'CAkSound', 'sourceID': [field(mid)], 'ulPluginID': [field(262145)],
            'StreamType': [field(2)], 'children': [], 'actions': []}


def event(branches, groups=None):
    return {'id': 1, 'type': 'CAkDialogueEvent', 'actions': [], 'children': [],
            'groups': [{'group': field(g)} for g in (groups or [ACTOR])],
            'branches': [{'keys': [field(v) for v in keys], 'target': field(target),
                          'weight': 50, 'probability': 100} for keys, target in branches]}


def usage(nodes, cultures=None):
    return UsageGraph({'parser_errors_or_skips': [], 'banks': {'test.bnk': {'nodes': nodes}}},
                      {7: 'Commander_A', 8: 'Commander_B'}, {}, cultures)


def row():
    value = dict.fromkeys(FIELDS, '')
    value.update(commander='example', media_id='42', wem_filename='42.wem', sharing_scope='COMMANDER_SPECIFIC',
                 silent_placeholder='NO', safe_to_replace_for_commander='YES', safe_to_replace_for_example='YES',
                 reverse_reference_check='PASS', original_duration=1, original_size_bytes=500,
                 sample_rate=32000, channels=1, sample_count=32000, decode_status='PASS_PCM16',
                 original_wem_sha256='a'*64, pcm_sha256='b'*64, transcript_confidence='HIGH', trigger_confidence='HIGH')
    return value


class OwnershipTests(unittest.TestCase):
    def test_shared_id_cannot_be_safe(self):
        graph = usage([event([([7], 2), ([8], 3)]), sound(2), sound(3)])
        scope, owners, audit = graph.classify(42, {'actor_name': 'Commander_A'})
        self.assertEqual(scope, 'GLOBAL_SHARED')
        self.assertEqual(len(owners), 2)
        self.assertEqual(safety(scope, False), 'NO_SHARED')
        self.assertEqual(audit['forward_count'], audit['reverse_count'])
        self.assertFalse(audit['missing_forward'] or audit['missing_reverse'])

    def test_same_culture_commanders_still_shared(self):
        graph = usage([event([([7], 2), ([8], 3)]), sound(2), sound(3)], {'Commander_A': [10], 'Commander_B': [10]})
        self.assertEqual(graph.classify(42, {'actor_name': 'Commander_A'})[0], 'CULTURE_SHARED')

    def test_second_actor_is_reaction_target(self):
        graph = usage([event([([7, 8], 2)], [ACTOR, ACTOR]), sound(2)])
        ref = graph.refs[42][0]
        self.assertEqual(graph.owner(ref), 'commander:Commander_A')
        self.assertFalse(graph.keyed(ref, {'actor_name': 'Commander_B', 'actor_id': 8}))

    def test_unrooted_same_media_blocks_safety(self):
        graph = usage([event([([7], 2)]), sound(2), sound(3)])
        self.assertEqual(graph.classify(42, {'actor_name': 'Commander_A'})[0], 'UNKNOWN_SHARED_SCOPE')

    def test_empty_random_container_is_no_audio(self):
        container = {'id': 2, 'type': 'CAkRanSeqCntr', 'children': [], 'playlist': []}
        self.assertEqual(resolve_bank('test.bnk', {'nodes': [event([([7], 2)]), container]}), [])
        container['playlist'] = [{'target': field(99)}]
        with self.assertRaises(ValueError):
            resolve_bank('test.bnk', {'nodes': [event([([7], 2)]), container]})

    def test_external_source_cookie_is_not_a_wem(self):
        node = sound(2)
        node['ulPluginID'] = [field(524289)]
        graph = usage([event([([7], 2)]), node])
        self.assertFalse(graph.refs)
        self.assertEqual(len(graph.non_file_sources), 1)

    def test_parent_pool_catches_unmapped_emote_event(self):
        first, second = sound(2), sound(3, 43)
        first['DirectParentID'] = second['DirectParentID'] = [field(5)]
        parent = {'id': 5, 'type': 'CAkRanSeqCntr', 'children': [field(2), field(3)],
                  'playlist': [{'target': field(2)}, {'target': field(3)}]}
        graph = UsageGraph({'parser_errors_or_skips': [], 'banks': {
            'battle_vo_emotes.bnk': {'nodes': [event([([7], 2)]), first, second, parent,
                {'id': 9, 'type': 'CAkEvent', 'actions': [field(10)], 'children': []},
                {'id': 10, 'type': 'CAkActionPlay', 'target': [field(3)], 'children': []}]}}},
            {7: 'Commander_A'}, {})
        with self.assertRaises(ValueError):
            audit_commander(graph, {'actor_name': 'Commander_A', 'actor_id': 7, 'culture_ids': [20]})

    def test_emote_punctuation_normalization_needs_exact_event_match(self):
        candidates = emote_spellings('prefix_quote_a_-_b')
        self.assertIn('prefix_quote_a_b', candidates)
        self.assertEqual(fnv1('Play_rom_scipio_emote_quote_gods_hear_me_bring_us_victory'), 2876436639)

    def test_typographic_apostrophe_is_dropped_only_for_an_actual_event(self):
        key = CHAT_TAG_PREFIX + 'gla_spartacus_emote_quote_freedom_doesn’t_come_without_a_fight'
        self.assertIn('gla_spartacus_emote_quote_freedom_doesnt_come_without_a_fight',
                      emote_spellings(key.removeprefix(CHAT_TAG_PREFIX)))
        rows = [(key, 'Freedom doesn’t come without a fight.')]
        found = chat_tag_events(rows, {1571957801}, ['Commander_Spartacus'], 'test.loc')
        self.assertEqual(found[1571957801]['name'], 'Play_gla_spartacus_emote_quote_freedom_doesnt_come_without_a_fight')
        self.assertEqual(found[1571957801]['owner'], 'commander:Commander_Spartacus')
        self.assertEqual(chat_tag_events(rows, {42}, ['Commander_Spartacus'], 'test.loc'), {})

    def test_chinese_emo_event_names_are_emotes(self):
        graph = usage([event([([7], 2)]), sound(2)])
        graph.event_names = {5: {'name': 'Play_CHI_A_EMO_follow_1', 'owner': 'commander:Commander_A'},
                             6: {'name': 'Play_rom_a_emote_quote_hear_me', 'owner': 'commander:Commander_A'}}
        spec = {'actor_name': 'Commander_A'}
        self.assertEqual(describe(graph, {'event_type': 'Event', 'event_id': 5}, spec, {}),
                         ('EMOTE', 'player selects emote: follow', 'HIGH'))
        self.assertEqual(describe(graph, {'event_type': 'Event', 'event_id': 6}, spec, {})[1], 'player selects emote: quote')

    def test_emote_pool_names_need_exact_hash_inside_the_commanders_own_pool(self):
        from tools.inventory.research import emote_pool_events
        named, pooled, foreign = fnv1('Play_CHI_A_EMO_attack_1'), fnv1('Play_CHI_A_EMO_stop_1'), fnv1('Play_CHI_A_EMO_help_1')
        nodes = [{'id': 30, 'type': 'CAkRanSeqCntr', 'children': [field(31), field(32)], 'actions': []},
                 {'id': 40, 'type': 'CAkRanSeqCntr', 'children': [field(41)], 'actions': []}]
        for sid, mid, parent in [(31, 101, 30), (32, 102, 30), (41, 103, 40)]:
            nodes.append(sound(sid, mid) | {'DirectParentID': [field(parent)]})
        for eid, target in [(named, 31), (pooled, 32), (foreign, 41)]:
            nodes += [{'id': eid, 'type': 'CAkEvent', 'actions': [field(eid + 1)], 'children': []},
                      {'id': eid + 1, 'type': 'CAkActionPlay', 'target': [field(target)], 'children': []}]
        graph = UsageGraph({'parser_errors_or_skips': [], 'banks': {'battle_vo_emotes.bnk': {'nodes': nodes}}},
                           {7: 'Commander_A'}, {named: {'name': 'Play_CHI_A_EMO_attack_1', 'owner': 'commander:Commander_A'}})
        found = emote_pool_events(graph, {'actor_name': 'Commander_A'}, ['stop', 'help'])
        # 'help' hashes to a real Event too, but it plays outside this commander's pool.
        self.assertEqual({k: v['name'] for k, v in found.items()}, {pooled: 'Play_CHI_A_EMO_stop_1'})
        self.assertEqual((found[pooled]['owner'], found[pooled]['pool_container_id']), ('commander:Commander_A', 30))
        self.assertEqual(emote_pool_events(graph, {'actor_name': 'Commander_B'}, ['stop', 'help']), {})

    def test_commander_tutorial_event_is_not_generic_advice(self):
        graph = usage([event([([7], 2)]), sound(2)])
        graph.event_names = {5: {'name': 'Play_A_Tutorial_VO_Request_01', 'owner': 'commander:Commander_A',
                                 'source': 'script.lua', 'literal_byte_offset': 10},
                             6: {'name': 'Play_Advice_01', 'owner': 'global:tutorial-advisor'}}
        spec = {'actor_name': 'Commander_A'}
        self.assertEqual(describe(graph, {'event_type': 'Event', 'event_id': 5}, spec, {})[0::2], ('TUTORIAL', 'HIGH'))
        self.assertEqual(describe(graph, {'event_type': 'Event', 'event_id': 6}, spec, {})[0::2], ('ADVISOR', 'LOW'))
        # Another commander's tutorial request stays a generic advice reference.
        other = {'actor_name': 'Commander_B'}
        self.assertEqual(describe(graph, {'event_type': 'Event', 'event_id': 5}, other, {})[0::2], ('ADVISOR', 'LOW'))

    def test_mixed_battle_pilot_keeps_whole_safe_groups_across_categories(self):
        def pilot_row(mid, category, trigger, group):
            return {'media_id': str(mid), 'category': category, 'trigger': trigger, 'decision_tree_path': '',
                    'bank': 'b', 'random_group_id': group, 'event_id': '1'}
        rows = [pilot_row(1, 'ORDER', 'unit ability ordered: unit manual charge', 'g1'),
                pilot_row(2, 'ORDER', 'unit ability ordered: unit manual charge', 'g1'),
                pilot_row(3, 'ORDER', 'unit ability ordered: unit brace', 'g2'),
                pilot_row(4, 'EMOTE', 'player selects emote: battlecry', 'g3'),
                pilot_row(5, 'BATTLE_EVENT', 'battle event: your base is under attack', 'g4'),
                pilot_row(6, 'ABILITY', 'commander ability activation: uprising', 'g5'),
                pilot_row(7, 'ABILITY', 'commander ability activation: uprising', 'g5')]
        eligible = [r for r in rows if r['media_id'] != '7']
        selected = pilot_battle_mix(rows, eligible, limit=5)
        self.assertEqual([r['media_id'] for r in selected], ['5', '1', '2', '3', '4'])

    def test_trigger_pilot_takes_one_whole_eligible_group_per_listed_trigger(self):
        from tools.inventory.research_export import pilot_battle_triggers
        def pilot_row(mid, category, trigger, group):
            return {'media_id': str(mid), 'category': category, 'trigger': trigger, 'decision_tree_path': '',
                    'bank': 'b', 'random_group_id': group, 'event_id': '1'}
        rows = [pilot_row(1, 'BATTLE_EVENT', 'battle event: one of your units routes', 'g1'),
                pilot_row(2, 'BATTLE_EVENT', 'battle event: one of your units routes', 'g1'),
                pilot_row(3, 'ORDER', 'unit ability ordered: unit_brace', 'g2'),
                pilot_row(4, 'ABILITY', 'commander ability activation: uprising', 'g3'),
                pilot_row(5, 'ABILITY', 'commander ability activation: uprising', 'g3')]
        eligible = [r for r in rows if r['media_id'] != '5']
        # Underscores read as spaces; a partially unsafe group is never split.
        selected = pilot_battle_triggers(rows, eligible, ['unit brace', 'routes'], limit=5)
        self.assertEqual([r['media_id'] for r in selected], ['3', '1', '2'])
        with self.assertRaises(ValueError):
            pilot_battle_triggers(rows, eligible, ['uprising'], limit=5)

    def test_pair_overlap_flags_any_shared_safe_id(self):
        datasets = {'a': {'1': {'safe_to_replace_for_commander': 'YES'}, '2': {'safe_to_replace_for_commander': 'NO_SHARED'}},
                    'b': {'2': {'safe_to_replace_for_commander': 'NO_SHARED'}, '3': {'safe_to_replace_for_commander': 'YES'}},
                    'hannibal': {'1': {'safe_to_replace_for_hannibal': 'NO_SHARED'}}}
        result = pair_overlaps(datasets, [('a', 'b'), ('a', 'hannibal'), ('b', 'hannibal')])
        self.assertEqual(result['a', 'b']['status'], 'SHARED_NOT_SAFE')
        self.assertEqual(result['a', 'hannibal']['safe_conflicts'], ['1'])
        self.assertEqual(result['a', 'hannibal']['status'], 'CONFLICT')
        self.assertEqual(result['b', 'hannibal']['status'], 'NO_OVERLAP')

    def test_crosscheck_pairs_for_one_or_two_new_inventories(self):
        from tools.inventory.crosscheck import inventory_pairs
        self.assertEqual(inventory_pairs(['a', 'b'], ['h', 'l']), [('a', 'b'), ('a', 'h'), ('a', 'l'), ('b', 'h'), ('b', 'l')])
        self.assertEqual(inventory_pairs(['z'], ['h', 'l']), [('z', 'h'), ('z', 'l')])


class MetadataTests(unittest.TestCase):
    def test_uniqueness_classification_silence_and_safety(self):
        valid = row()
        self.assertEqual(validate_rows([valid], 'example')['status'], 'PASS')
        for changes in [None, {'sharing_scope': 'CULTURE_SHARED'}, {'sharing_scope': 'BAD'},
                        {'silent_placeholder': 'YES'}, {'original_duration': ''}, {'sample_count': 1},
                        {'reverse_reference_check': 'FAIL'}, {'shared_with': 'Commander_B'}]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                if changes is None:
                    validate_rows([valid, valid], 'example')
                else:
                    validate_rows([valid | changes], 'example')

    def test_duplicate_group_is_pcm_based(self):
        facts = {'sample_rate': 32000, 'channels': 1, 'sample_count': 32000, 'pcm_sha256': 'b'*64}
        groups = duplicate_groups({'42': facts, '43': facts})
        self.assertEqual(groups['43']['duplicate_content_of'], '42')
        first, second = row(), row() | {'media_id': '43', 'wem_filename': '43.wem'}
        for item in [first, second]:
            item.update({k: v for k, v in groups[item['media_id']].items() if k != 'members'})
        validate_rows([first, second], 'example')
        second['pcm_sha256'] = 'c'*64
        with self.assertRaises(ValueError):
            validate_rows([first, second], 'example')

    def test_advisor_copy_is_not_a_second_commander_recording(self):
        fact = {'pcm_sha256': 'b'*64, 'sample_rate': 32000, 'channels': 1, 'sample_count': 32000}
        primary = {'first': {'42': fact}, 'second': {}}
        advisory = {'first': {'43': fact}, 'second': {'43': fact}}
        rows, groups, advisor_groups = recording_links(primary, advisory)
        self.assertFalse(groups)
        self.assertEqual(len(advisor_groups), 1)
        self.assertEqual(next(r for r in rows if r['media_id'] == '43')['primary_inventories'], '')
        primary['second']['44'] = fact
        self.assertEqual(len(recording_links(primary, advisory)[1]), 1)

    def test_ui_text_without_audio_agreement_is_not_confirmed(self):
        result = transcript({'base.en': {'text': 'A different sentence'}}, {'text': 'For Sparta!'})
        self.assertEqual(result['english_text'], 'A different sentence')
        self.assertEqual(result['transcript_confidence'], 'LOW')

    def test_exact_event_link_and_audio_agreement(self):
        result = transcript({'small.en': {'text': 'For Sparta!'}}, {'text': 'For Sparta!'})
        self.assertEqual(result['transcript_confidence'], 'CONFIRMED')

    def test_manual_transcription_deferral_keeps_raw_and_never_guesses(self):
        result = transcript({'medium.en': {'text': 'Unreliable words'}}, correction={
            'resolution': 'NEEDS_MANUAL_TRANSCRIPTION', 'text': '', 'confidence': 'UNKNOWN'})
        self.assertEqual(result['raw_transcript'], 'Unreliable words')
        self.assertEqual(result['english_text'], '')
        self.assertEqual(result['transcript_confidence'], 'UNKNOWN')
        self.assertEqual(result['transcript_resolution'], 'NEEDS_MANUAL_TRANSCRIPTION')
        validate_rows([row() | result], 'example')
        with self.assertRaises(ValueError):
            validate_rows([row() | result | {'english_text': 'Guessed wording'}], 'example')

    def test_final_review_labels_need_matching_confidence(self):
        hyp = {'medium.en': {'text': 'Watch the wind, say euro.'}}
        human = transcript(hyp, correction={'text': 'Watch the wind, Zhou Yu!', 'confidence': 'CONFIRMED',
                                            'resolution': 'HUMAN_CONFIRMED', 'evidence': 'Final human decision.'})
        self.assertEqual((human['english_text'], human['transcript_confidence'], human['transcript_resolution'],
                          human['transcript_review_required'], human['raw_transcript']),
                         ('Watch the wind, Zhou Yu!', 'CONFIRMED', 'HUMAN_CONFIRMED', 'NO', 'Watch the wind, say euro.'))
        second = transcript(hyp, correction={'text': 'Onward!', 'confidence': 'HIGH',
                                             'resolution': 'SECOND_OPINION_RESOLVED', 'evidence': 'Second opinion.'})
        self.assertEqual(second['transcript_resolution'], 'SECOND_OPINION_RESOLVED')
        validate_rows([row() | human], 'example')
        for bad in [{'confidence': 'HIGH', 'resolution': 'HUMAN_CONFIRMED'}, {'confidence': 'MEDIUM', 'resolution': 'SECOND_OPINION_RESOLVED'},
                    {'confidence': 'HIGH', 'resolution': 'APPROVED_BY_SOMEONE'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                transcript(hyp, correction={'text': 'X', 'evidence': 'e'} | bad)

    def test_independent_usage_and_original_audit_reject_tampering(self):
        source = ROOT/'data/commanders/leonidas/research'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'commanders'
            folder = root/'leonidas/research'
            shutil.copytree(source, folder)
            (root/'shared-research').mkdir()
            shutil.copyfile(ROOT/'data/commanders/shared-research/cross-commander-duplicate-recordings.csv',
                            root/'shared-research/cross-commander-duplicate-recordings.csv')
            safe = next(r['media_id'] for r in read_csv(folder/'voice-lines.csv')
                        if r['safe_to_replace_for_commander'] == 'YES')
            path = folder/'usage-paths.csv'
            original = path.read_bytes()
            usages = read_csv(path)
            next(r for r in usages if r['media_id'] == safe)['owner'] = 'commander:Other'
            write_csv(path, usages)
            with self.assertRaisesRegex(ValueError, 'Shared usage cannot be safe'):
                validate_research(folder, 'leonidas')
            path.write_bytes(original)
            path = folder/'original-audio-audit.json'
            audio = json.loads(path.read_text(encoding='utf-8'))
            audio['results'][safe]['original_size_bytes'] += 1
            path.write_text(json.dumps(audio), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Original audio fact differs'):
                validate_research(folder, 'leonidas')

    def test_research_datasets_and_installer_exclusion(self):
        for name in ['leonidas', 'scipio-africanus']:
            self.assertEqual(validate_research(ROOT/'data/commanders'/name/'research', name)['status'], 'PASS')
        self.assertEqual([m['commander'] for m in discover()], ['hannibal', 'spartacus'])

    def test_no_original_audio_in_repository_candidates(self):
        from tools.validation.repository import audit
        self.assertEqual(audit()['prohibited_asset_files'], [])

    def test_original_output_guard_and_unknown_base_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                private_directory(root/'protected'/'audio', [root/'protected'])
            source = root/'unknown.pack'
            source.write_bytes(b'unsupported')
            with self.assertRaises(ValueError):
                extract_decode(source, '0'*64, ['42'], root/'output', root/'decoder', [root/'protected'])
            self.assertFalse((root/'output').exists())


if __name__ == '__main__':
    unittest.main()
