"""Safety and evidence regressions for offline commander TTS preparation."""
from collections import defaultdict
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.inventory.research_metadata import read_csv, write_csv
from tools.resources import ROOT
from tools.tts.research_plan import (budget_risk, check_delivery, english_key, performance_key, plan_delivery,
                                     prepare, read_memory, translation_memory, VOICE_PROFILES)


class ResearchPlanTests(unittest.TestCase):
    def test_group_requires_same_original_recording_and_wording(self):
        fact = {'sample_rate': '32000', 'channels': '1', 'sample_count': '32000',
                'pcm_sha256': 'a'*64, 'english_text': 'For Sparta!', 'media_id': '1'}
        self.assertEqual(performance_key(fact, 'Za Spartu!'),
                         performance_key(fact | {'media_id':'2'}, 'Za Spartu!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'),
                            performance_key(fact | {'english_text':'For Rome!'}, 'Za Spartu!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'), performance_key(fact, 'Za Řím!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'),
                            performance_key(fact | {'pcm_sha256':'b'*64}, 'Za Spartu!'))

    def test_plans_include_only_independently_safe_ids(self):
        memory = translation_memory(ROOT/'data/commanders/shared-research/commander-translation-memory.tsv')
        for name in ['leonidas','scipio-africanus']:
            with self.subTest(name=name):
                folder = ROOT/'data/commanders'/name
                research = {r['media_id']:r for r in read_csv(folder/'research/voice-lines.csv')}
                voices = read_csv(folder/'tts-plan/voice-lines-cz.csv')
                plan = read_csv(folder/'tts-plan/tts-plan.csv')
                self.assertEqual(len(voices),len({r['media_id'] for r in voices}))
                self.assertEqual({r['media_id'] for r in voices},
                                 {mid for mid,r in research.items() if r['safe_to_replace_for_commander']=='YES'})
                groups = defaultdict(list)
                for row in voices:
                    source = research[row['media_id']]
                    self.assertEqual((source['sharing_scope'],source['silent_placeholder'],source['reverse_reference_check']),
                                     ('COMMANDER_SPECIFIC','NO','PASS'))
                    self.assertEqual(row['original_size_bytes'],source['original_size_bytes'])
                    self.assertEqual(row['original_duration'],source['original_duration'])
                    if row['english_text']:
                        self.assertEqual(row['czech_text'],memory[' '.join(row['english_text'].casefold().split())])
                    self.assertIn(row['recommended_model'], {'eleven_v3','eleven_v4'})
                    self.assertTrue(row['recommended_tags'].startswith('[') and row['recommended_tags'].endswith(']'))
                    self.assertIn(row['wem_budget_risk'], {'LOW','MEDIUM','HIGH'})
                    groups[row['tts_performance_group']].append(row)
                self.assertEqual(len(groups),len(plan))
                self.assertEqual({r['tts_performance_group'] for r in plan},set(groups))
                for rows in groups.values():
                    self.assertEqual(len({r['pcm_sha256'] for r in rows}),1)
                    self.assertEqual(len({r['english_text'].casefold() for r in rows}),1)
                    self.assertEqual(len({r['czech_text'] for r in rows}),1)
                    self.assertEqual(len({r['recommended_model'] for r in rows}),1)
                    self.assertEqual({r['tts_source_media_id'] for r in rows},
                                     {min((r['media_id'] for r in rows),key=int)})
                for filename in ['pilot-menu.csv','pilot-battle.csv']:
                    for row in read_csv(folder/'tts-plan'/filename):
                        self.assertEqual(row['translation_status'],'PREPARED')
                        self.assertEqual(row['english'],row['english_text'])
                        self.assertEqual(row['czech'],row['czech_text'])
                        self.assertIn(row['trigger_confidence'],{'CONFIRMED','HIGH'})
                decisions = read_csv(folder/'tts-plan/transcript-review-decisions.csv')
                expected_review = {'leonidas': 3, 'scipio-africanus': 5}[name]
                self.assertEqual(len(decisions), expected_review)
                # Every originally disputed line is now resolved (second opinion or final human decision).
                self.assertEqual(sum(bool(r['final_transcript']) for r in decisions), expected_review)

    def test_manual_deferral_never_becomes_a_tts_request(self):
        # No live deferral remains, so a disposable copy of real research data simulates one.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'commanders'
            shutil.copytree(ROOT/'data/commanders/zhuge-liang/research', root/'zhuge-liang/research')
            path = root/'zhuge-liang/research/voice-lines.csv'
            rows = read_csv(path)
            next(r for r in rows if r['media_id'] == '32253270').update(
                english_text='', final_transcript='', transcript_confidence='UNKNOWN',
                transcript_resolution='NEEDS_MANUAL_TRANSCRIPTION', transcript_review_required='YES')
            write_csv(path, rows, list(rows[0]))
            memory, decisions = read_memory(ROOT/'data/commanders/zhuge-liang/tts-plan/translation-memory.tsv')
            memory.pop(english_key('Watch the wind, Zhou Yu!'))
            summary = prepare('zhuge-liang', root, memory, delivery_decisions=decisions)
            row = {r['media_id']: r for r in read_csv(root/'zhuge-liang/tts-plan/voice-lines-cz.csv')}['32253270']
            self.assertEqual((row['translation_status'], row['english_text'], row['czech_text']), ('NEEDS_MANUAL_TRANSCRIPTION', '', ''))
            review = {r['media_id']: r for r in read_csv(root/'zhuge-liang/tts-plan/transcript-review-decisions.csv')}['32253270']
            self.assertEqual((review['transcript_resolution'], review['final_transcript']), ('NEEDS_MANUAL_TRANSCRIPTION', ''))
            self.assertTrue(review['archive_wav_reference'].endswith('/32253270.wav'))
            self.assertEqual((summary['ready_for_elevenlabs'], summary['manual_review_ids']), (False, ['32253270']))

    def test_commander_specific_silent_placeholders_stay_out_of_the_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'commanders'
            shutil.copytree(ROOT/'data/commanders/hasdrubal/research', root/'hasdrubal/research')
            research = read_csv(root/'hasdrubal/research/voice-lines.csv')
            silent = {r['media_id'] for r in research if r['sharing_scope'] == 'COMMANDER_SPECIFIC' and r['silent_placeholder'] == 'YES'}
            self.assertEqual(len(silent), 13)
            self.assertEqual({r['safe_to_replace_for_commander'] for r in research if r['media_id'] in silent}, {'NO_SILENT'})
            memory, decisions = read_memory(ROOT/'data/commanders/hasdrubal/tts-plan/translation-memory.tsv')
            summary = prepare('hasdrubal', root, memory, delivery_decisions=decisions)
            voices = {r['media_id'] for r in read_csv(root/'hasdrubal/tts-plan/voice-lines-cz.csv')}
            self.assertEqual(summary['safe_spoken_media_ids'], 318)
            self.assertTrue(voices.isdisjoint(silent))

    def test_final_transcript_decisions_are_applied_and_every_plan_is_ready(self):
        expected = {('leonidas', '12766875'): ("We're being damaged by friendly fire!", 'CONFIRMED', 'HUMAN_CONFIRMED'),
                    ('zhuge-liang', '32253270'): ('Watch the wind, Zhou Yu!', 'CONFIRMED', 'HUMAN_CONFIRMED'),
                    ('zhuge-liang', '801277871'): ('Your arrogance ends, Lu Bu!', 'CONFIRMED', 'HUMAN_CONFIRMED'),
                    ('scipio-africanus', '191571653'): ("The flank's exposed!", 'HIGH', 'SECOND_OPINION_RESOLVED'),
                    ('scipio-africanus', '238862791'): ('Attack the flank!', 'HIGH', 'SECOND_OPINION_RESOLVED'),
                    ('scipio-africanus', '1022842783'): ('Onward!', 'HIGH', 'SECOND_OPINION_RESOLVED'),
                    ('spartacus', '697820721'): ('Strike through!', 'HIGH', 'SECOND_OPINION_RESOLVED')}
        for (name, mid), (english, confidence, resolution) in expected.items():
            with self.subTest(media_id=mid):
                folder = ROOT/'data/commanders'/name
                row = {r['media_id']: r for r in read_csv(folder/'tts-plan/voice-lines-cz.csv')}[mid]
                self.assertEqual((row['english_text'], row['transcript_confidence'], row['transcript_resolution'], row['translation_status']),
                                 (english, confidence, resolution, 'PREPARED'))
                self.assertTrue(row['czech_text'])
                review = {r['media_id']: r for r in read_csv(folder/'tts-plan/transcript-review-decisions.csv')}[mid]
                self.assertEqual((review['transcript_resolution'], review['final_transcript']), (resolution, english))
        for name in ['leonidas', 'scipio-africanus', 'spartacus', 'germanicus', 'zhuge-liang', 'miltiades', 'julius-caesar',
                     'hasdrubal']:
            summary = json.loads((ROOT/'data/commanders'/name/'tts-plan/plan-summary.json').read_text(encoding='utf-8'))
            self.assertEqual((summary['ready_for_elevenlabs'], summary['manual_review_ids']), (True, []), name)
        # Genuinely undecidable recordings stay deferred (no guessed English/Czech, never a TTS request).
        for name, deferred in [('alexander-the-great', ['305833039', '366092679']), ('cynane', ['667922401'])]:
            summary = json.loads((ROOT/'data/commanders'/name/'tts-plan/plan-summary.json').read_text(encoding='utf-8'))
            self.assertEqual((summary['ready_for_elevenlabs'], summary['manual_review_ids']), (False, deferred), name)
            plan_ids = {m for r in read_csv(ROOT/'data/commanders'/name/'tts-plan/tts-plan.csv') for m in r['member_media_ids'].split(';')
                        if r['czech_text']}
            self.assertTrue(plan_ids.isdisjoint(deferred), name)

    def test_budget_labels_do_not_claim_encoding(self):
        self.assertEqual(budget_risk(5000,1,'Go!','Běžte!'),'HIGH')
        self.assertEqual(budget_risk(12000,2,'Forward!','Vpřed!'),'LOW')

    def test_v3_is_only_for_shouted_expressive_delivery(self):
        self.assertEqual(check_delivery('BATTLE_SHOUT','eleven_v3','[fierce, shouting]')[1],'eleven_v3')
        for bad in [('BATTLE_SHOUT','eleven_v4','[fierce, shouting]'), ('AUTHORITATIVE','eleven_v3','[authoritative]'),
                    ('AUTHORITATIVE','eleven_v4','[proud, calm, authoritative]'), ('AUTHORITATIVE','eleven_v5','[calm]'),
                    ('AUTHORITATIVE','eleven_v4','authoritative')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_delivery(*bad)

    def test_profiled_routing_follows_hannibal_context_rules(self):
        def row(category, trigger, english='Line!'):
            return {'category':category,'trigger':trigger,'english_text':english}
        decide = lambda commander, *rows: plan_delivery(list(rows), commander, {})
        self.assertEqual(decide('spartacus', row('EMOTE','player selects emote: battlecry'))[1:], ('eleven_v3','[fierce, shouting]'))
        self.assertEqual(decide('germanicus', row('ORDER','unit ability ordered: unit manual charge'))[1:], ('eleven_v3','[shouting, commanding]'))
        self.assertEqual(decide('germanicus', row('ORDER','unit ability ordered: unit medium defence stance'))[1], 'eleven_v4')
        self.assertEqual(decide('spartacus', row('BATTLE_EVENT','battle event: one of your units routes'))[1:], ('eleven_v3','[angry, shouting]'))
        self.assertEqual(decide('spartacus', row('BATTLE_EVENT','battle event: your team draws first blood'))[1], 'eleven_v4')
        self.assertEqual(decide('germanicus', row('FRONTEND','open/select commander'))[2], '[proud, authoritative]')
        # A reviewed per-phrase decision wins over context rules.
        reviewed = {'line!': ('DEFIANT','eleven_v4','[defiant]')}
        self.assertEqual(plan_delivery([row('EMOTE','player selects emote: battlecry')],'spartacus',reviewed)[1],'eleven_v4')
        # Commanders without a profile keep the published legacy routing.
        self.assertEqual(decide('scipio-africanus', row('ORDER','unit ability ordered: unit manual charge'))[1], 'eleven_v4')

    def test_composed_profile_needs_shouted_original_for_v3(self):
        def row(category, trigger, english, raw=''):
            return {'category':category,'trigger':trigger,'english_text':english,'raw_transcript':raw}
        decide = lambda *rows: plan_delivery(list(rows), 'zhuge-liang', {})
        charge = 'unit ability ordered: unit manual charge'
        self.assertEqual(decide(row('ORDER', charge, 'Charge!'))[1:], ('eleven_v4', '[urgent, commanding]'))
        self.assertEqual(decide(row('ORDER', charge, 'CHARGE!'))[1:], ('eleven_v3', '[shouting, commanding]'))
        base = 'battle event: your base is under attack'
        self.assertEqual(decide(row('BATTLE_EVENT', base, 'Our base is under attack!'))[1:], ('eleven_v4', '[urgent, commanding]'))
        # Localized wording keeps normal case; the raw local hypothesis still carries the shouted delivery.
        self.assertEqual(decide(row('BATTLE_EVENT', base, 'Our base is under attack!', 'OUR BASE IS UNDER ATTACK!'))[1:],
                         ('eleven_v3', '[urgent, shouting]'))
        self.assertEqual(decide(row('EMOTE', 'player selects emote: quote', 'A prepared mind.'))[1:],
                         ('eleven_v4', '[strategic, composed]'))
        # Germanicus has no such requirement: the context rule alone routes a charge to v3.
        self.assertEqual(plan_delivery([row('ORDER', charge, 'Charge!')], 'germanicus', {})[1], 'eleven_v3')
        # Chinese chat-tag kinds yes/no map to affirmative/negative; extra kinds use the profile when it defines them.
        self.assertEqual(decide(row('EMOTE', 'player selects emote: yes', 'Yes.'))[2], '[confident, restrained]')
        self.assertEqual(decide(row('EMOTE', 'player selects emote: no', 'This seems unwise.'))[2], '[calm, serious]')
        self.assertEqual(decide(row('EMOTE', 'player selects emote: insult', 'As predicted!'))[2], '[confident, restrained]')
        self.assertEqual(decide(row('DEFEAT', 'battle event: defeat because your army was annihilated', 'We must plan better.'))[2],
                         '[calm, serious]')

    def test_miltiades_and_caesar_profiles_stay_distinct_and_composed(self):
        def row(category, trigger, english):
            return {'category':category,'trigger':trigger,'english_text':english,'raw_transcript':''}
        charge = 'unit ability ordered: unit manual charge'
        for name in ['miltiades', 'julius-caesar']:
            with self.subTest(name=name):
                self.assertEqual(plan_delivery([row('ORDER', charge, 'Charge!')], name, {})[1], 'eleven_v4')
                self.assertEqual(plan_delivery([row('ORDER', charge, 'CHARGE!')], name, {})[1:], ('eleven_v3', '[shouting, commanding]'))
        frontend = row('FRONTEND', 'open/select commander', 'Line.')
        self.assertEqual(plan_delivery([frontend], 'miltiades', {})[:1], ('STRATEGIC',))
        self.assertEqual(plan_delivery([frontend], 'julius-caesar', {})[:1], ('COMPOSED',))
        self.assertNotEqual(plan_delivery([frontend], 'miltiades', {}), plan_delivery([frontend], 'leonidas', {}))
        styles = {s for name, p in VOICE_PROFILES.items() if name not in {'miltiades', 'julius-caesar'}
                  for v in p.values() if isinstance(v, tuple) for s in [v[0]]} | {'CALM_COMMANDING', 'AUTHORITATIVE'}
        for name in ['miltiades', 'julius-caesar']:
            self.assertLessEqual({v[0] for v in VOICE_PROFILES[name].values() if isinstance(v, tuple)}, styles, name)

    def test_hasdrubal_alexander_cynane_profiles_are_distinct_and_reuse_project_styles(self):
        def row(category, trigger, english):
            return {'category':category,'trigger':trigger,'english_text':english,'raw_transcript':''}
        charge = 'unit ability ordered: unit manual charge'
        new = ['hasdrubal', 'alexander-the-great', 'cynane']
        for name in new:
            with self.subTest(name=name):
                # v3 stays reserved for originals that are audibly shouted.
                self.assertEqual(plan_delivery([row('ORDER', charge, 'Charge!')], name, {})[1], 'eleven_v4')
                self.assertEqual(plan_delivery([row('ORDER', charge, 'CHARGE!')], name, {})[1], 'eleven_v3')
        frontend = row('FRONTEND', 'open/select commander', 'Line.')
        cards = {name: plan_delivery([frontend], name, {}) for name in new + ['leonidas', 'miltiades', 'julius-caesar']}
        self.assertEqual(len(set(cards.values())), len(cards))
        # Hasdrubal must not sound like Hannibal's legacy calm routing.
        self.assertNotEqual(cards['hasdrubal'], plan_delivery([frontend], 'hannibal', {}))
        styles = {s for name, p in VOICE_PROFILES.items() if name not in new
                  for v in p.values() if isinstance(v, tuple) for s in [v[0]]} | {'CALM_COMMANDING', 'AUTHORITATIVE'}
        for name in new:
            self.assertLessEqual({v[0] for v in VOICE_PROFILES[name].values() if isinstance(v, tuple)}, styles, name)

    def test_memory_accepts_reviewed_delivery_columns_only_when_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'memory.tsv'
            path.write_text('english_text\tczech_text\tdelivery_style\trecommended_model\trecommended_tags\n'
                            'Charge!\tVpřed!\tBATTLE_SHOUT\televen_v3\t[fierce, shouting]\nHold!\tStát!\t\t\t\n', encoding='utf-8')
            memory, decisions = read_memory(path)
            self.assertEqual(memory, {'charge!':'Vpřed!','hold!':'Stát!'})
            self.assertEqual(decisions, {'charge!':('BATTLE_SHOUT','eleven_v3','[fierce, shouting]')})
            path.write_text('english_text\tczech_text\tdelivery_style\trecommended_model\trecommended_tags\n'
                            'Hold!\tStát!\tAUTHORITATIVE\televen_v3\t[authoritative]\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_memory(path)


if __name__=='__main__':
    unittest.main()
