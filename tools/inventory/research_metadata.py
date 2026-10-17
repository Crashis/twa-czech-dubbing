"""Shared research CSV schema, transcript evidence, duplicates and invariants."""
from collections import defaultdict
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from tools.inventory.research_graph import SCOPES
from tools.pack.reader import require

FIELDS = '''commander media_id wem_filename bank dialogue_event_id event_id event_type event_name
container_id sound_id decision_tree_path object_path category trigger trigger_confidence
raw_transcript final_transcript english_text transcript_confidence transcript_resolution
original_duration original_size_bytes sample_rate channels sample_count decode_status
silent_placeholder sharing_scope scope safe_to_replace_for_commander shared_with
duplicate_group duplicate_content_of duplicate_kind random_group_id random_variant_count
delivery_style recommended_model czech_text notes speaker faction conditions variant_group
original_wem_sha256 wem_sha256 pcm_sha256 pack_path pack_offset audio_peak_pcm16 clipped_sample_count
explicit_commander_speaker advisor_only has_frontend_usage has_battle_usage
reference_count reverse_reference_count reverse_reference_check reference_owners all_references
stt_base_en stt_small_en stt_medium_en chat_tag_text localization_key transcript_review_required
archive_wem_reference archive_wav_reference all_triggers stt_alternative_evidence action_id audio_node_id'''.split()
NON_SPEECH_HYPOTHESES = {'', 'you', 'thank you', 'thanks for watching', 'bye', 'oh', 'uh', 'hmm', 'ah', 'huh'}
# Explicit final review outcomes recorded in a correction; each requires its own confidence level.
FINAL_RESOLUTIONS = {'HUMAN_CONFIRMED': 'CONFIRMED', 'SECOND_OPINION_RESOLVED': 'HIGH'}


def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9' ]", ' ', text.lower())).strip()


def similarity(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def transcript(hypotheses, chat=None, previous=None, correction=None):
    """Resolve evidence conservatively; no text is synthesized from event names."""
    usable = {m: v['text'].strip() for m, v in hypotheses.items()
              if norm(v.get('text', '')) not in NON_SPEECH_HYPOTHESES}
    preference = ['medium.en', 'small.en', 'base.en']
    raw = next((usable[m] for m in preference if m in usable), '')
    alternatives = '; '.join(m + ': ' + repr(v.get('text', '')) for m, v in hypotheses.items())
    text, confidence = raw, 'LOW' if raw else 'UNKNOWN'
    resolution = 'STT hypotheses disagree or only one model available. ' + alternatives
    if len(usable) >= 2:
        pairs = [(similarity(a, b), ma, mb) for ma, a in usable.items() for mb, b in usable.items() if ma < mb]
        best = max(pairs)
        if all(score >= .94 for score, _, _ in pairs):
            confidence = 'HIGH'
            resolution = f'{len(usable)} independent local STT models agree; context retained. ' + alternatives
        elif best[0] >= .88:
            pair = {best[1], best[2]}
            text = next(usable[m] for m in preference if m in pair)
            confidence = 'MEDIUM'
            resolution = 'Partial local STT agreement; verify wording. ' + alternatives
    if previous and previous.get('english_text'):
        # Previous text is admitted only by the caller's exact original hash match.
        text, confidence = previous['english_text'], previous['transcript_confidence']
        resolution = previous['source'] + '; source Media ID ' + str(previous['source_media_id']) + '. ' + alternatives
    if chat and chat.get('text'):
        match = max((similarity(chat['text'], v) for v in usable.values()), default=0)
        if match >= .70:
            text, confidence = chat['text'], 'CONFIRMED'
            resolution = 'Exact FNV-1 Play_<localization key> event link; independent STT agrees ' + f'({match:.3f}). ' + alternatives
        else:
            resolution += '; linked UI text differs from audio hypotheses; not accepted as spoken wording: ' + repr(chat['text'])
    if correction:
        if correction.get('resolution') == 'NEEDS_MANUAL_TRANSCRIPTION':
            return {'raw_transcript': raw, 'final_transcript': '', 'english_text': '',
                    'transcript_confidence': 'UNKNOWN', 'transcript_resolution': 'NEEDS_MANUAL_TRANSCRIPTION',
                    'transcript_review_required': 'YES'}
        require(correction.get('evidence') and correction['confidence'] in {'CONFIRMED', 'HIGH', 'MEDIUM', 'LOW'}, 'Correction needs evidence/confidence')
        final = correction.get('resolution')
        require(final is None or FINAL_RESOLUTIONS.get(final) == correction['confidence'], 'Final review label needs its matching confidence')
        confirmed_same_text = confidence == 'CONFIRMED' and norm(text) == norm(correction['text'])
        prior_resolution = resolution
        text, confidence = correction['text'], correction['confidence']
        resolution = 'CONTEXT_CORRECTION: ' + correction['evidence'] + '; RAW: ' + alternatives
        if final:
            # Raw hypotheses stay in raw_transcript/stt_* columns; evidence stays in transcript-corrections.json.
            resolution = final
        elif confirmed_same_text:
            confidence = 'CONFIRMED'
            resolution = prior_resolution + '; ' + resolution
    return {'raw_transcript': raw, 'final_transcript': text, 'english_text': text,
            'transcript_confidence': confidence, 'transcript_resolution': resolution,
            'transcript_review_required': 'YES' if confidence in {'LOW', 'UNKNOWN', 'MEDIUM'} else 'NO'}


def duplicate_groups(audio):
    """Exact recordings only: format+PCM or identical original WEM, never text."""
    groups = defaultdict(list)
    for mid, row in audio.items():
        if row.get('pcm_sha256'):
            key = ('PCM', row['sample_rate'], row['channels'], row['sample_count'], row['pcm_sha256'])
        else:
            key = ('WEM', row['original_wem_sha256'])
        groups[key].append(str(mid))
    result = {}
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=int)
        group = key[0] + '-' + key[-1][:16]
        for mid in members:
            result[mid] = {'duplicate_group': group, 'duplicate_content_of': members[0] if mid != members[0] else '',
                           'duplicate_kind': key[0] + '_EXACT', 'members': members,
                           **({'pcm_sha256': key[-1]} if key[0] == 'PCM' else {})}
    return result


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else FIELDS)
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), 'Missing/duplicate CSV columns')
        return list(reader)


def validate_rows(rows, commander, external_duplicates=None):
    by_id = {str(r['media_id']): r for r in rows}
    require(len(by_id) == len(rows), 'Duplicate Media ID in research CSV')
    safety_field = 'safe_to_replace_for_' + commander
    for mid, row in by_id.items():
        require(set(FIELDS) <= set(row), 'Research CSV schema incomplete')
        require(row['commander'] == commander and mid.isdecimal() and row['wem_filename'] == mid + '.wem', 'Research identity mismatch')
        require(row['sharing_scope'] in SCOPES, 'Unknown research sharing classification')
        require(row['transcript_confidence'] in {'CONFIRMED', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'}
                and row['trigger_confidence'] in {'CONFIRMED', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'}, 'Invalid evidence confidence')
        if row['transcript_resolution'] == 'NEEDS_MANUAL_TRANSCRIPTION':
            require(not row['english_text'] and not row['final_transcript']
                    and row['transcript_confidence'] in {'UNKNOWN', 'LOW'}
                    and row['transcript_review_required'] == 'YES', 'Deferred transcript must not contain guessed wording')
        require(row['silent_placeholder'] in {'YES', 'NO'}, 'Invalid silence classification')
        expected = ('NO_SILENT' if row['silent_placeholder'] == 'YES' else
                    'NO_UNKNOWN' if row['sharing_scope'] == 'UNKNOWN_SHARED_SCOPE' else
                    'YES' if row['sharing_scope'] == 'COMMANDER_SPECIFIC' else 'NO_SHARED')
        require(row['safe_to_replace_for_commander'] == row[safety_field] == expected, 'Unsafe research replacement flag')
        if expected == 'YES':
            require(row['reverse_reference_check'] == 'PASS' and not row['shared_with'], 'Shared/unverified ID cannot be safe')
        require(float(row['original_duration']) > 0 and int(row['original_size_bytes']) > 0
                and int(row['sample_rate']) > 0 and int(row['channels']) > 0 and int(row['sample_count']) > 0
                and row['decode_status'] == 'PASS_PCM16', 'Missing decoded original facts')
        require(abs(float(row['original_duration']) - int(row['sample_count']) / int(row['sample_rate'])) < .000001, 'Duration/sample count mismatch')
        for key in ['original_wem_sha256', 'pcm_sha256']:
            require(bool(re.fullmatch('[0-9a-f]{64}', row[key])), 'Invalid original audio hash')
        other = str(row.get('duplicate_content_of', ''))
        if other and other in by_id:
            target = by_id[other]
            require(other != mid and not target['duplicate_content_of'] and row['duplicate_group'] == target['duplicate_group']
                    and row['pcm_sha256'] == target['pcm_sha256'], 'Invalid duplicate reference')
        elif other:
            target = (external_duplicates or {}).get(other)
            require(target and not target['duplicate_content_of'] and target['duplicate_group'] == row['duplicate_group']
                    and target['pcm_sha256'] == row['pcm_sha256'], 'Unresolved external duplicate reference')
    return {'status': 'PASS', 'commander': commander, 'research_rows': len(rows),
            'safe_replacement_candidates': sum(r['safe_to_replace_for_commander'] == 'YES' for r in rows),
            'installer_release_ready': False}


def validate_research(folder, commander):
    folder = Path(folder)
    rows = read_csv(folder / 'voice-lines.csv')
    cross_path = folder.parents[1] / 'shared-research/cross-commander-duplicate-recordings.csv'
    external = {r['media_id']: r for r in read_csv(cross_path)} if cross_path.exists() else {}
    result = validate_rows(rows, commander, external)
    manifest = json.loads((folder / 'manifest-draft.json').read_text(encoding='utf-8'))
    require(manifest['status'] == 'research_ready' and manifest['release_ready'] is False, 'Research must never masquerade as a release')
    require(manifest['total_relevant_media_ids'] == len(rows), 'Research manifest count mismatch')
    require(manifest['safe_replacement_media_ids'] == result['safe_replacement_candidates'], 'Research safety count mismatch')
    complete = json.loads((folder / 'completeness.json').read_text(encoding='utf-8'))
    require(complete['forward_relevant_media'] == complete['reverse_relevant_media'] == len(rows)
            and not complete['forward_reverse_symmetric_difference'] and not complete['branch_enumeration_symmetric_difference']
            and not complete['emote_pool_symmetric_difference'], 'Independent completeness evidence differs')
    audio = json.loads((folder / 'original-audio-audit.json').read_text(encoding='utf-8'))
    require(audio['canonical_pack_sha256'] == manifest['canonical_original_pack_sha256'] and audio['RSA'] == 'PASS'
            and set(audio['results']) == {r['media_id'] for r in rows}, 'Independent original audit differs')
    usages = defaultdict(list)
    for usage in read_csv(folder / 'usage-paths.csv'):
        usages[usage['media_id']].append(usage)
    require(set(usages) == {r['media_id'] for r in rows}, 'Missing/extra independent usage IDs')
    for row in rows:
        mid = row['media_id']
        source = audio['results'][mid]
        for key in ['original_size_bytes', 'sample_rate', 'channels', 'sample_count', 'pack_offset', 'audio_peak_pcm16']:
            require(int(row[key]) == source[key], 'Original audio fact differs: ' + key)
        for key in ['original_wem_sha256', 'pcm_sha256', 'silent_placeholder', 'decode_status', 'pack_path']:
            require(row[key] == source[key], 'Original audio evidence differs: ' + key)
        require(abs(float(row['original_duration']) - source['original_duration']) < .000001, 'Original duration audit differs')
        audit = complete['per_media_reverse_audit'][mid]
        require(int(row['reference_count']) == len(usages[mid]) == audit['forward_count']
                and int(row['reverse_reference_count']) == audit['reverse_count']
                and not audit['missing_forward'] and not audit['missing_reverse'] and not audit['unrooted_sounds'], 'Independent reverse usage differs')
        if row['safe_to_replace_for_commander'] == 'YES':
            require({u['owner'] for u in usages[mid]} == {'commander:' + manifest['actor_name']}, 'Shared usage cannot be safe')
    require(not any(p.suffix.lower() in {'.wem', '.wav', '.pack', '.bnk', '.ogg', '.mp3'} for p in folder.rglob('*')), 'Original audio leaked into research repository')
    for name in ['pilot-menu.csv', 'pilot-battle.csv']:
        for row in read_csv(folder / name):
            require(row['media_id'] in {r['media_id'] for r in rows if r['safe_to_replace_for_commander'] == 'YES'
                                       and r['transcript_confidence'] in {'CONFIRMED', 'HIGH'}}, 'Unsafe or uncertain pilot row')
    return result | {'inventory_status': manifest['inventory_status'], 'ready_for_translation_tts': manifest['ready_for_translation_tts']}
