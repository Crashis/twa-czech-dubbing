"""Export metadata-only commander research from a private, audited workspace."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from tools.inventory.research_graph import UsageGraph, ACTOR, CULTURE, UNIT, ABILITY, BATTLE_EVENT, safety
from tools.inventory.research_metadata import FIELDS, duplicate_groups, transcript, validate_rows, write_csv

GROUP_LABELS = {ACTOR: 'vo_actor', CULTURE: 'vo_culture', UNIT: 'vo_unit_type',
                ABILITY: 'ability_group_1602634982', BATTLE_EVENT: 'battle_event_group_636323490',
                2703688388: 'gender', 2545052772: 'speed', 3400800153: 'phase_group_3400800153'}


def load(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default


def conditions(usage, ref):
    return '; '.join(f'{GROUP_LABELS.get(g, g)}={usage.label(k)} ({k})' for g, k in zip(ref['groups'], ref['keys']))


def describe(usage, ref, spec, profiles):
    eid = str(ref['event_id'])
    if ref['event_type'] == 'Event':
        event = usage.event_names.get(ref['event_id'], {})
        if '_emote_' in event.get('name', '').lower():
            kind = event['name'].lower().split('_emote_')[1].split('_')[0]
            return 'EMOTE', 'player selects emote: ' + kind, 'HIGH'
        if event.get('owner') == 'commander:' + spec['actor_name'] and '_tutorial_' in event.get('name', '').lower():
            # Exact Event name literal found in the requesting tutorial script.
            verified = event.get('literal_byte_offset') is not None
            return 'TUTORIAL', 'tutorial script VO request ' + event['name'] + ' (' + event.get('source', 'unknown script') + ')', 'HIGH' if verified else 'MEDIUM'
        return 'ADVISOR', 'generic advisor/tutorial event ' + eid + '; exact request not recovered', 'LOW'
    if ref['event_id'] == 825794328:
        ability = ref['keys'][ref['groups'].index(ABILITY)]
        label = usage.label(ability)
        readable = label.removeprefix('vo_ua_').replace('_', ' ')
        if label.lower() in {s.lower() for s in spec.get('own_abilities', [])}:
            return 'ABILITY', 'commander ability activation: ' + readable, 'HIGH'
        if ability == 0:
            return 'ORDER', 'ability/order without a dedicated voice branch (wildcard fallback)', 'MEDIUM'
        return 'ORDER', 'unit ability ordered: ' + readable, 'HIGH' if label.startswith('vo_ua_') else 'LOW'
    if ref['event_id'] == 4168474204:
        state = ref['keys'][ref['groups'].index(BATTLE_EVENT)]
        label = usage.label(state)
        category = ('VICTORY' if label.lower().startswith('end_win') else
                    'DEFEAT' if label.lower().startswith('end_lose') else
                    'DEATH_REACTION' if label.lower() == 'your_commander_dead' else 'BATTLE_EVENT')
        readable = profiles.get(eid, {}).get('states', {}).get(label.lower(), label.replace('_', ' '))
        return category, 'battle event: ' + readable, 'HIGH' if not label.isdecimal() else 'LOW'
    if ref['event_id'] == 1053322782:
        return 'DEATH_REACTION', 'reaction to another commander: ' + usage.label(ref['keys'][1]) + '; death context inferred from sibling recordings', 'MEDIUM'
    profile = profiles.get(eid)
    if profile:
        return profile['category'], profile['trigger'], profile['confidence']
    return 'OTHER', 'unidentified event ' + eid, 'UNKNOWN'


def build_rows(usage, spec, audio, hypotheses, previous, duplicates, profiles, corrections, include_advice=False, chat_by_pcm=None, corrections_by_pcm=None, alternatives=None):
    relevant = usage.relevant(spec, include_advice=include_advice)
    rows = []
    paths = []
    for mid in sorted(relevant):
        context = relevant[mid]
        primary = context['primary'][0]
        refs = usage.refs[mid]
        fact = audio[str(mid)]
        scope, owners, reverse = usage.classify(mid, spec)
        safe = safety(scope, fact['silent_placeholder'] == 'YES')
        category, trigger, trigger_confidence = describe(usage, primary, spec, profiles)
        hyp = {m: results[fact['pcm_sha256']] for m, results in hypotheses.items() if fact['pcm_sha256'] in results}
        primary_chat = usage.event_names.get(primary['event_id'])
        chat = primary_chat if primary_chat and primary_chat.get('text') else (chat_by_pcm or {}).get(fact['pcm_sha256'], primary_chat)
        correction = corrections.get(str(mid)) or (corrections_by_pcm or {}).get(fact['pcm_sha256'])
        resolved = transcript(hyp, chat, previous.get(fact['pcm_sha256']), correction)
        if chat and chat.get('duplicate_source_media_id'):
            resolved['transcript_resolution'] += '; localization evidence transferred by exact PCM/format identity from Media ID ' + str(chat['duplicate_source_media_id'])
        if fact['silent_placeholder'] == 'YES':
            resolved = dict.fromkeys(['raw_transcript', 'final_transcript', 'english_text'], '') | {
                'transcript_confidence': 'CONFIRMED', 'transcript_resolution': 'Decoded PCM contains only zero samples.', 'transcript_review_required': 'NO'}
        chain = primary['object_path']
        random = [usage.nodes[primary['bank']][i] for i in chain if usage.nodes[primary['bank']][i]['type'] == 'CAkRanSeqCntr']
        random_group = random[-1] if random else None
        variants = len(random_group['playlist']) if random_group else 1
        expected = 'commander:' + spec['actor_name']
        other_owners = owners - {expected}
        shared = '; '.join(sorted(other_owners)) if scope != 'COMMANDER_SPECIFIC' else ''
        audit_ok = not (reverse['missing_forward'] or reverse['missing_reverse'] or reverse['unrooted_sounds'])
        style = 'CALM_COMMANDING' if category == 'FRONTEND' else 'AUTHORITATIVE'
        model = 'eleven_v4'
        if category == 'EMOTE' and 'battlecry' in trigger:
            style, model = 'BATTLE_SHOUT', 'eleven_v3'
        notes = ['delivery/model are proposed metadata only; performance approval and TTS are separate']
        if context['advisor_only']:
            notes.append('Generic advisor reference included for completeness; not the commander speaking')
        if not context['explicit_speaker'] and not context['advisor_only']:
            notes.append('Shared unit/culture voice context; not identified as the commander speaking')
        if context['explicit_speaker'] and scope != 'COMMANDER_SPECIFIC':
            notes.append('CRITICAL: explicit commander branch shares this Media ID with another owner')
        row = dict.fromkeys(FIELDS, '')
        row.update(fact)
        row.pop('media_id', None)
        row.update({k: v for k, v in resolved.items()})
        row.update(commander=spec['id'], media_id=str(mid), bank=primary['bank'],
                   dialogue_event_id=primary['event_id'] if primary['event_type'] == 'DialogueEvent' else '',
                   event_id=primary['event_id'], event_type=primary['event_type'],
                   event_name=primary_chat['name'] if primary_chat else 'UNKNOWN',
                   container_id=chain[-2] if len(chain) > 1 else '', sound_id=primary['sound_id'],
                   decision_tree_path=conditions(usage, primary), object_path='>'.join(map(str, chain)),
                   category=category, trigger=trigger, trigger_confidence=trigger_confidence,
                   sharing_scope=scope, scope=spec['id'].upper() + '_SPECIFIC' if scope == 'COMMANDER_SPECIFIC' else scope,
                   safe_to_replace_for_commander=safe, shared_with=shared,
                   random_group_id=str(random_group['id']) if random_group else '', random_variant_count=variants,
                   delivery_style=style, recommended_model=model, notes='; '.join(notes),
                   speaker=spec['display_name'] if context['explicit_speaker'] else usage.owner(primary),
                   faction='; '.join(spec['culture_names']), conditions=conditions(usage, primary),
                   variant_group=f"{random_group['id']} ({variants} variants)" if random_group else 'single sound',
                   wem_sha256=fact['original_wem_sha256'], explicit_commander_speaker='YES' if context['explicit_speaker'] else 'NO',
                   advisor_only='YES' if context['advisor_only'] else 'NO',
                   has_frontend_usage='YES' if any(r['bank'] == 'frontend_vo.bnk' for r in refs) else 'NO',
                   has_battle_usage='YES' if any(r['bank'].startswith('battle') for r in refs) else 'NO',
                   reference_count=len(refs), reverse_reference_count=reverse['reverse_count'],
                   reverse_reference_check='PASS' if audit_ok else 'FAIL', reference_owners='; '.join(sorted(owners)),
                   all_references=' || '.join(f"{r['bank']}:{r['event_id']}:{r['sound_id']}[{conditions(usage, r)}]" for r in refs),
                   stt_base_en=hyp.get('base.en', {}).get('text', ''), stt_small_en=hyp.get('small.en', {}).get('text', ''),
                   stt_medium_en=hyp.get('medium.en', {}).get('text', ''),
                   chat_tag_text=chat.get('text', '') if chat else '', localization_key=chat.get('key', '') if chat else '')
        row['archive_wem_reference'] = f"commander-research/{spec['id']}/original-wem/{mid}.wem"
        row['archive_wav_reference'] = f"commander-research/{spec['id']}/decoded-wav/{mid}.wav"
        row['all_triggers'] = ' || '.join(sorted({describe(usage, r, spec, profiles)[1] for r in refs}))
        row['stt_alternative_evidence'] = json.dumps((alternatives or {}).get(fact['pcm_sha256'], []), ensure_ascii=False)
        row['action_id'] = primary.get('action_id', '')
        row['audio_node_id'] = primary['target']
        row['safe_to_replace_for_' + spec['id']] = safe
        if str(mid) in duplicates:
            row.update({k: v for k, v in duplicates[str(mid)].items() if k != 'members'})
        rows.append(row)
        for ref in refs:
            paths.append({'media_id': str(mid), 'bank': ref['bank'], 'event_id': ref['event_id'],
                          'event_type': ref['event_type'], 'branch_index': ref.get('branch_index', ''),
                          'action_id': ref.get('action_id', ''),
                          'decision_tree_path': conditions(usage, ref), 'target_id': ref['target'],
                          'object_path': '>'.join(map(str, ref['object_path'])), 'sound_id': ref['sound_id'],
                          'owner': usage.owner(ref), 'weight': ref.get('weight', ''), 'probability': ref.get('probability', '')})
    validate_rows(rows, spec['id'], duplicates)
    return rows, paths


def summarize(rows):
    spoken = [r for r in rows if r['silent_placeholder'] == 'NO']
    specific = [r for r in spoken if r['sharing_scope'] == 'COMMANDER_SPECIFIC']
    ready = all(r['english_text'] and r['transcript_confidence'] in {'CONFIRMED', 'HIGH'} for r in specific)
    return {'total_relevant_media_ids': len(rows), 'spoken_media_ids': len(spoken),
            'silent_placeholders': len(rows) - len(spoken),
            'commander_specific_media_ids': sum(r['sharing_scope'] == 'COMMANDER_SPECIFIC' for r in rows),
            'explicit_commander_speaker_media_ids': sum(r['explicit_commander_speaker'] == 'YES' for r in spoken),
            'safe_replacement_media_ids': sum(r['safe_to_replace_for_commander'] == 'YES' for r in rows),
            'shared_media_ids': sum(r['sharing_scope'] != 'COMMANDER_SPECIFIC' for r in rows),
            'frontend_count': sum(r['category'] == 'FRONTEND' for r in specific),
            'battle_count': sum(r['category'] != 'FRONTEND' for r in specific),
            'sharing_counts': dict(Counter(r['sharing_scope'] for r in rows)),
            'category_counts': dict(Counter(r['category'] for r in specific)),
            'transcript_counts_all': dict(Counter(r['transcript_confidence'] for r in spoken)),
            'transcript_counts_commander_specific': dict(Counter(r['transcript_confidence'] for r in specific)),
            'duplicate_groups': len({r['duplicate_group'] for r in rows if r['duplicate_group']}),
            'commander_specific_transcripts_needing_review': sum(r['transcript_review_required'] == 'YES' for r in specific),
            'missing_transcripts_all': sum(not r['english_text'] for r in spoken),
            'manually_deferred_transcript_ids': [r['media_id'] for r in spoken if r['transcript_resolution'] == 'NEEDS_MANUAL_TRANSCRIPTION'],
            'unique_commander_specific_recordings': len({r['pcm_sha256'] for r in specific}),
            'ready_for_translation_tts': ready}


def pilot_battle(rows, candidates, limit=25):
    common = ['objective capture enemy base', 'base is under attack', 'unit is under attack',
              'unit has recovered', 'unit is routing', 'first blood', 'team is capturing']
    def priority(row):
        trigger = (row['trigger'] + ' ' + row.get('decision_tree_path', '')).lower().replace('_', ' ')
        if row['category'] == 'BATTLE_EVENT' and any(token in trigger for token in common):
            return (0, min(i for i, token in enumerate(common) if token in trigger))
        return ({'ABILITY': 1, 'EMOTE': 2, 'VICTORY': 3, 'DEFEAT': 3, 'BATTLE_EVENT': 4}.get(row['category'], 9), 0)
    groups = defaultdict(list)
    for row in rows:
        if row['category'] != 'FRONTEND':
            groups[row['bank'], row['random_group_id'] or 'single:' + row['media_id']].append(row)
    eligible = {r['media_id'] for r in candidates}
    ordered = sorted(groups.values(), key=lambda g: (priority(g[0]), int(g[0]['event_id']), int(g[0]['media_id'])))
    selected = []
    for group in ordered:
        if all(r['media_id'] in eligible for r in group) and len(selected)+len(group) <= limit:
            selected.extend(group)
    return selected


PILOT_BUCKETS = [
    ('battle', lambda r, t: r['category'] == 'BATTLE_EVENT'),
    ('aggressive order', lambda r, t: r['category'] == 'ORDER' and any(x in t for x in ['charge', 'chase', 'piercing', 'strain', 'push'])),
    ('standard order', lambda r, t: r['category'] == 'ORDER' and any(x in t for x in ['defence', 'brace', 'shield', 'formation', 'speed', 'march'])),
    ('ability', lambda r, t: r['category'] == 'ABILITY'),
    ('battlecry', lambda r, t: r['category'] == 'EMOTE' and 'battlecry' in t),
    ('emote', lambda r, t: r['category'] == 'EMOTE'),
    ('result', lambda r, t: r['category'] in {'VICTORY', 'DEFEAT'}),
]


def pilot_battle_mix(rows, candidates, limit=25):
    """Round-robin whole random groups across battle-event, order, ability, emote and result buckets."""
    eligible = {r['media_id'] for r in candidates}
    common = ['objective capture enemy base', 'base is under attack', 'unit is under attack', 'is attacked',
              'routes', 'rallies', 'first blood', 'capturing']
    groups = defaultdict(list)
    for row in rows:
        if row['category'] != 'FRONTEND':
            groups[row['bank'], row['random_group_id'] or 'single:' + row['media_id']].append(row)
    buckets = {name: [] for name, _ in PILOT_BUCKETS}
    for group in groups.values():
        if not all(r['media_id'] in eligible for r in group):
            continue
        trigger = (group[0]['trigger'] + ' ' + group[0]['decision_tree_path']).lower().replace('_', ' ')
        name = next((n for n, test in PILOT_BUCKETS if test(group[0], trigger)), None)
        if name and (name != 'battle' or any(token in trigger for token in common)):
            rank = min((i for i, token in enumerate(common) if token in trigger), default=0)
            buckets[name].append((rank, int(group[0]['event_id']), int(group[0]['media_id']), group))
    for items in buckets.values():
        items.sort(key=lambda item: item[:3])
    selected = []
    while any(buckets.values()):
        for name, _ in PILOT_BUCKETS:
            if buckets[name]:
                group = buckets[name].pop(0)[3]
                if len(selected) + len(group) <= limit:
                    selected.extend(group)
        if len(selected) >= limit:
            break
    return selected


def export_commander(folder, spec, rows, paths, complete, canonical_hash):
    folder.mkdir(parents=True, exist_ok=True)
    fields = FIELDS + ['safe_to_replace_for_' + spec['id']]
    write_csv(folder / 'voice-lines.csv', rows, fields)
    write_csv(folder / 'usage-paths.csv', paths)
    write_csv(folder / 'shared-media.csv', [r for r in rows if r['sharing_scope'] != 'COMMANDER_SPECIFIC'], fields)
    write_csv(folder / 'frontend-lines.csv', [r for r in rows if r['has_frontend_usage'] == 'YES'], fields)
    write_csv(folder / 'battle-lines.csv', [r for r in rows if r['has_battle_usage'] == 'YES'], fields)
    write_csv(folder / 'transcript-review.csv', [r for r in rows if r['transcript_review_required'] == 'YES'], fields)
    dup = [dict(media_id=r['media_id'], duplicate_group=r['duplicate_group'], duplicate_content_of=r['duplicate_content_of'],
                kind=r['duplicate_kind'], original_wem_sha256=r['original_wem_sha256'], pcm_sha256=r['pcm_sha256']) for r in rows if r['duplicate_group']]
    write_csv(folder / 'duplicate-groups.csv', dup, ['media_id', 'duplicate_group', 'duplicate_content_of', 'kind', 'original_wem_sha256', 'pcm_sha256'])
    candidates = [r for r in rows if r['safe_to_replace_for_commander'] == 'YES' and r['transcript_confidence'] in {'CONFIRMED', 'HIGH'}
                  and r['trigger_confidence'] in {'CONFIRMED', 'HIGH'}]
    menu = [r for r in candidates if r['category'] == 'FRONTEND'][:15]
    battle = pilot_battle_mix(rows, candidates) if spec.get('pilot_mix') else pilot_battle(rows, candidates)
    write_csv(folder / 'pilot-menu.csv', menu, fields)
    write_csv(folder / 'pilot-battle.csv', battle, fields)
    summary = summarize(rows) | {'pilot_menu': len(menu), 'pilot_battle': len(battle)}
    status = 'structural_complete_transcript_review_required' if summary['commander_specific_transcripts_needing_review'] or summary['missing_transcripts_all'] else 'complete_with_confidence_flags'
    manifest = {'schema_version': 1, 'research_schema_version': 1, 'id': spec['id'], 'display_name': spec['display_name'],
                'status': 'research_ready', 'inventory_status': status, 'release_ready': False,
                'canonical_original_pack_sha256': canonical_hash, 'actor_name': spec['actor_name'], 'actor_id': spec['actor_id'],
                'culture_names': spec['culture_names'], 'culture_ids': spec['culture_ids'],
                'human_listening': 'NOT_RUN', 'game_runtime_review': 'NOT_RUN', 'paid_api_calls': 0,
                'replacements': [], **summary}
    (folder / 'manifest-draft.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (folder / 'completeness.json').write_text(json.dumps(complete, indent=1) + '\n', encoding='utf-8')
    no_audio = [{**r, 'group_ids': ';'.join(map(str, r['group_ids'])), 'keys': ';'.join(map(str, r['keys']))}
                for r in complete.get('no_audio_commander_branches', [])]
    write_csv(folder / 'no-audio-branches.csv', no_audio, ['bank', 'event_id', 'target_id', 'group_ids', 'keys', 'kind'])
    lines = [f"# {spec['display_name']} — English voice inventory", '',
             'Metadata only. Original WEM and decoded WAV files are held in the private commander-research archive.', '',
             '| Media ID | Scope / safe | Category | English | Confidence | Trigger |', '|---|---|---|---|---|---|']
    for r in rows:
        escape = lambda text: str(text).replace('|', '\\|').replace('\n', ' ')
        lines.append('| ' + ' | '.join(escape(x) for x in [r['media_id'], r['sharing_scope'] + ' / ' + r['safe_to_replace_for_commander'], r['category'], r['english_text'], r['transcript_confidence'], r['trigger']]) + ' |')
    (folder / 'voice-lines.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--profiles', required=True)
    parser.add_argument('--commander', action='append', required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace)
    profiles = load(args.profiles)
    usage = UsageGraph(load(workspace / 'corpus/graph.json'), {int(k): v for k, v in load(workspace / 'names.json').items()},
                       {int(k): v for k, v in load(workspace / 'event-names.json').items()}, profiles.get('commander_cultures'))
    hypotheses = {}
    for model in ['base.en', 'small.en', 'medium.en']:
        hypotheses[model] = {}
        for path in sorted(workspace.glob('stt-' + model + '*.json')):
            hypotheses[model].update(load(path, {'results': {}})['results'])
    alternatives = defaultdict(list)
    for path in sorted(workspace.glob('asr-alternative-*.json')):
        data = load(path)
        for key, result in data.get('results', {}).items():
            alternatives[key].append({'source': path.name, 'model': data['model'],
                                      'leading_silence_seconds': data.get('analysis_leading_silence_seconds', 0),
                                      'beam_size': data['beam_size'], **result})
    specs = [s for s in load(workspace / 'specs.json') if s['id'] in args.commander]
    all_audio = {}
    audits = {}
    for spec in specs:
        audits[spec['id']] = load(workspace / spec['id'] / 'original-audio-audit.json')
        all_audio.update(audits[spec['id']]['results'])
    duplicates = duplicate_groups(all_audio)
    corrections = load(workspace / 'transcript-corrections.json', {})
    corrections_by_pcm = {}
    for mid, correction in corrections.items():
        if mid in all_audio:
            key = all_audio[mid]['pcm_sha256']
            prior = corrections_by_pcm.get(key)
            if prior and prior['text'].lower().rstrip('.!') != correction['text'].lower().rstrip('.!'):
                raise ValueError('Conflicting corrections for identical original PCM')
            corrections_by_pcm[key] = correction | {'evidence': correction['evidence'] + '; exact PCM/format transfer from source Media ID ' + mid}
    chat_by_pcm = {}
    for mid, fact in all_audio.items():
        for ref in usage.refs[int(mid)]:
            event = usage.event_names.get(ref['event_id'])
            if event and event.get('text'):
                chat_by_pcm.setdefault(fact['pcm_sha256'], event | {'duplicate_source_media_id': mid})
    for spec in specs:
        spec.update(profiles.get('commanders', {}).get(spec['id'], {}))
        rows, paths = build_rows(usage, spec, audits[spec['id']]['results'], hypotheses,
                                load(workspace / 'previous-transcripts.json', {}), duplicates,
                                profiles['events'], corrections, chat_by_pcm=chat_by_pcm, corrections_by_pcm=corrections_by_pcm, alternatives=alternatives)
        summary = export_commander(Path(args.output_root) / spec['id'] / 'research', spec, rows, paths,
                                   load(workspace / 'completeness.json')[spec['id']], audits[spec['id']]['canonical_pack_sha256'])
        original_audit = audits[spec['id']] | {'results': {r['media_id']: audits[spec['id']]['results'][r['media_id']] for r in rows}}
        (Path(args.output_root) / spec['id'] / 'research/original-audio-audit.json').write_text(
            json.dumps(original_audit, indent=1)+'\n', encoding='utf-8')
        extended, _ = build_rows(usage, spec, audits[spec['id']]['results'], hypotheses,
                                 load(workspace / 'previous-transcripts.json', {}), duplicates,
                                 profiles['events'], corrections, include_advice=True, chat_by_pcm=chat_by_pcm, corrections_by_pcm=corrections_by_pcm, alternatives=alternatives)
        write_csv(Path(args.output_root) / spec['id'] / 'research/battle-advice-global-reference.csv',
                  [r for r in extended if r['advisor_only'] == 'YES'], FIELDS + ['safe_to_replace_for_' + spec['id']])
        print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
