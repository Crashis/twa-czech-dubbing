"""Targeted, resume-safe re-generation of selected performances with an explicit delivery override.

Only listed Media IDs are requested; the canonical Czech text always comes from the TTS plan and
is never edited. A delivery CSV (media_id, attempt, tags) chooses the tags of each attempt. Outputs,
state and audits stay in a separate ignored work/ folder; the production ledger is never modified.
Paid requests require an explicitly authorized task, as for tools.tts.production.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path

from tools.tts.production import (FORMAT, MODELS, HardStop, api_key, decoder, generate_one, get_json, history_fields,
                                  history_items, inspect_audio, read_csv, retry_technical, save_json, sha_bytes,
                                  sha_file, subscription, utc_now, voice_and_models)
from tools.tts.pronunciation import commander_resolver, request_text


def active_speech_seconds(path, mini):
    """10 ms frames above -45 dBFS, the measure used by the original-asset analysis."""
    import math
    decoded = mini.decode_file(str(path), output_format=mini.SampleFormat.SIGNED16, nchannels=1)
    samples, rate = decoded.samples, decoded.sample_rate
    frame = rate // 100
    active = 0
    for start in range(0, len(samples) - frame + 1, frame):
        chunk = samples[start:start + frame]
        level = sum(int(x) * int(x) for x in chunk) / frame / 32768 ** 2
        active += 10 * math.log10(max(level, 1e-12)) > -45
    return active / 100


def same_words(left, right):
    """Equal wording ignoring only punctuation and case (synthesis-only prosody overrides)."""
    import re
    words = lambda text: re.sub(r'[^\w\s]', '', text, flags=re.UNICODE).casefold().split()
    return words(left) == words(right)


def load_targets(commander, production_state, deliveries, max_attempt, retranslated=()):
    root = Path('data/commanders') / commander
    plan = {r['tts_source_media_id']: r for r in read_csv(root / 'tts-plan/tts-plan.csv')}
    voices = {r['media_id']: r for r in read_csv(root / 'tts-plan/voice-lines-cz.csv')}
    production = json.loads(Path(production_state).read_text(encoding='utf-8'))
    rows = read_csv(Path(deliveries))
    pronunciation = commander_resolver(commander)
    pronunciation.verify_phrases({mid: row['czech_text'] for mid, row in plan.items()})
    targets = {}
    for row in rows:
        mid, attempt, tags = row['media_id'], int(row['attempt']), row['tags'].strip()
        if tags == 'canonical' and mid in plan:
            tags = plan[mid]['recommended_tags']  # isolate a speed change from any delivery-tag change
        speed = float(row['speed']) if (row.get('speed') or '').strip() else None
        if speed is not None and not 0.7 <= speed <= 1.2:
            raise RuntimeError(f'ElevenLabs speed must be 0.7-1.2 {mid}')
        if (mid not in plan or mid not in voices or voices[mid]['tts_source_media_id'] != mid
                or not 1 <= attempt <= max_attempt or not (tags.startswith('[') and tags.endswith(']'))
                or len(tags[1:-1].split(',')) > 2):
            raise RuntimeError(f'Invalid delivery row {mid} attempt {attempt}')
        old = production['items'][mid]
        # A canonical text may differ from the production ledger only for an explicitly approved retranslation.
        if old['status'] != 'complete' or (old['czech_text'] != plan[mid]['czech_text']) != (mid in retranslated):
            raise RuntimeError(f'Production performance missing, changed or not declared retranslated {mid}')
        # Approved pronunciation overrides first; a delivery override may then change punctuation only.
        spoken = pronunciation.resolve(plan[mid]['czech_text'], 'production', mid)
        override = (row.get('tts_text_override') or '').strip() or None
        if override and (override == spoken['tts_input_text'] or not same_words(override, spoken['tts_input_text'])
                         or not (row.get('override_reason') or '').strip()):
            raise RuntimeError(f'Synthesis override must keep the exact words and state a reason {mid}')
        targets[f'{mid}#{attempt}'] = {'media_id': mid, 'attempt': attempt, 'tags': tags, 'speed': speed,
                                       'canonical_text': plan[mid]['czech_text'], 'old': old,
                                       'tts_input_text': spoken['tts_input_text'],
                                       'applied_pronunciation_overrides': spoken['applied_pronunciation_overrides'],
                                       'tts_text_override': override,
                                       'override_reason': (row.get('override_reason') or '').strip() or None,
                                       'member_media_ids': plan[mid]['member_media_ids'].split(';')}
    if len(targets) != len(rows):
        raise RuntimeError('Duplicate delivery rows')
    return targets, production


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commander', required=True)
    parser.add_argument('--voice-name', required=True)
    parser.add_argument('--voice-id', required=True)
    parser.add_argument('--model', choices=sorted(MODELS), required=True)
    parser.add_argument('--production-state', required=True, type=Path)
    parser.add_argument('--deliveries', required=True, type=Path, help='CSV: media_id,attempt,tags')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--attempt', type=int, required=True, help='only send rows of this attempt')
    parser.add_argument('--max-attempt', type=int, default=2)
    parser.add_argument('--max-requests', type=int, default=52, help='hard cap over every attempt of this task')
    parser.add_argument('--max-credits', type=int, default=3000)
    parser.add_argument('--decoder-path', type=Path)
    parser.add_argument('--audit', action='store_true', help='read-only history audit; no TTS request')
    parser.add_argument('--retranslated', help='comma-separated Media IDs whose canonical Czech text was changed '
                                                'by an approved retranslation')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path('work').resolve()):
        parser.error('output must be under ignored work/')
    retranslated = tuple(filter(None, (args.retranslated or '').split(',')))
    targets, production = load_targets(args.commander, args.production_state, args.deliveries, args.max_attempt,
                                       retranslated)
    key = api_key()
    voice_id = voice_and_models(key, args.voice_name, args.voice_id, {args.model})
    stored_settings = get_json(f'/v1/voices/{voice_id}/settings', key)  # read-only
    if voice_id != production['voice_id']:
        raise HardStop('Regeneration voice differs from the production voice')
    before = subscription(key)
    mini = decoder(args.decoder_path)
    output = args.output
    (output / 'audio').mkdir(parents=True, exist_ok=True)
    state_path = output / 'generation-state.json'
    state = (json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else
             {'schema': 1, 'commander': args.commander, 'voice_name': args.voice_name, 'voice_id': voice_id,
              'model': args.model, 'production_state_sha256': sha_file(args.production_state),
              'deliveries_sha256': {}, 'starting_credits': before['remaining'], 'starting_usage': before['used'],
              'created_at': utc_now(), 'items': {}})
    if state['voice_id'] != voice_id or state['model'] != args.model:
        raise RuntimeError('Regeneration state belongs to another voice or model')
    if args.audit:
        print(json.dumps(audit(state, state_path, key, mini, before), ensure_ascii=False, indent=2))
        return
    state['deliveries_sha256'][str(args.attempt)] = sha_file(args.deliveries)
    pending = []
    for name, target in sorted(targets.items(), key=lambda kv: (kv[1]['attempt'], int(kv[1]['media_id']))):
        if target['attempt'] != args.attempt:
            continue
        mid = target['media_id']
        if any(state['items'].get(f'{mid}#{n}', {}).get('accepted') for n in range(1, target['attempt'])):
            raise RuntimeError(f'{mid} already has an accepted compact source; no further generation')
        item = state['items'].get(name)
        text = request_text(target['tags'], target['tts_text_override'] or target['tts_input_text'])
        if item:
            if item['request_text'] != text:
                raise RuntimeError(f'Frozen request changed {name}')
            continue
        old = target['old']
        old_audio = Path(old['output_path'])
        state['items'][name] = {
            'media_id': mid, 'tts_source_media_id': mid, 'member_media_ids': target['member_media_ids'],
            'canonical_text': target['canonical_text'], 'czech_text': target['canonical_text'],
            'tts_input_text': target['tts_input_text'],
            'applied_pronunciation_overrides': target['applied_pronunciation_overrides'],
            'tts_text_override': target['tts_text_override'], 'override_reason': target['override_reason'],
            'speed': target['speed'],
            'retranslated': mid in retranslated, 'previous_canonical_text': old['czech_text'] if mid in retranslated else None,
            # Stored settings copied unchanged; only speed differs, and only in this request.
            'voice_settings': stored_settings | {'speed': target['speed']} if target['speed'] is not None else None,
            'stored_voice_settings': stored_settings if target['speed'] is not None else None,
            'czech_text_sha256': sha_bytes(target['canonical_text'].encode('utf-8')), 'tags': target['tags'],
            'request_text': text, 'voice_id': voice_id, 'voice_name': args.voice_name, 'model': args.model,
            'attempt': target['attempt'], 'old_audio_path': str(old_audio), 'old_audio_sha256': old['checksum'],
            'old_duration': old['audio']['duration_seconds'], 'old_active_speech_s': active_speech_seconds(old_audio, mini),
            'new_audio_path': None, 'new_duration': None, 'duration_change_percent': None,
            'output_path': str(output / 'audio' / f'{mid}_v4_compact{target["attempt"]}.mp3'),
            'status': 'planned', 'credits_used': None, 'generation_timestamp': None, 'checksum': None,
            'accepted': False}
        pending.append(state['items'][name])
    save_json(state_path, state)
    requests_so_far = sum(1 for x in state['items'].values() if x['status'] != 'planned') \
        + sum(1 for x in state['items'].values() if x.get('prior_failed_attempt'))
    projected = sum(len(x['request_text']) for x in pending)
    spent = sum(x.get('credits_used') or 0 for x in state['items'].values())
    print(json.dumps({'attempt': args.attempt, 'pending': len(pending), 'projected_credit_ceiling': projected,
                      'credits_spent_so_far': spent, 'current_credits': before['remaining']}), flush=True)
    if requests_so_far + len(pending) > args.max_requests:
        raise HardStop(f'Paid request cap {args.max_requests} would be exceeded')
    if spent + projected > args.max_credits:
        raise HardStop(f'Projected credits exceed {args.max_credits}')
    if before['remaining'] < projected:
        raise HardStop('Insufficient credits')
    stop = None
    try:
        for item in pending:
            generate_one(item, key, voice_id, mini, state, state_path)
            if item['status'] != 'complete':
                try:
                    retry_technical(item, key, state, state_path, mini)
                except HardStop:
                    raise
                except RuntimeError as error:
                    item.update(status='uncertain', error=str(error))
            if item['status'] == 'complete':
                item['new_audio_path'] = item['output_path']
                item['new_duration'] = item['audio']['duration_seconds']
                item['new_active_speech_s'] = active_speech_seconds(Path(item['output_path']), mini)
                item['duration_change_percent'] = round(100 * (item['new_duration'] / item['old_duration'] - 1), 1)
                item['active_speech_change_percent'] = round(
                    100 * (item['new_active_speech_s'] / item['old_active_speech_s'] - 1), 1)
            save_json(state_path, state)
            print(item['media_id'], item['attempt'], item['status'], item.get('new_duration'),
                  item.get('active_speech_change_percent'), flush=True)
    except HardStop as error:
        stop = str(error)
        state['hard_stop'] = stop
    try:
        after = subscription(key)
        state['latest_credits'] = after['remaining']
    except RuntimeError:
        after = None
    state['finished_at'] = utc_now()
    save_json(state_path, state)
    print(json.dumps({'complete': sum(x['status'] == 'complete' for x in state['items'].values()),
                      'credits_used_headers': sum(x.get('credits_used') or 0 for x in state['items'].values()),
                      'remaining_credits': after and after['remaining'], 'hard_stop': stop}), flush=True)
    if stop:
        raise SystemExit(3)


def audit(state, state_path, key, mini, before):
    """Re-decode every new output and match each request to ElevenLabs history (read-only)."""
    items = [x for x in state['items'].values() if x['status'] == 'complete']
    problems = []
    for item in items:
        metrics = inspect_audio(Path(item['output_path']), mini)
        if (metrics['sha256'] != item['checksum'] or metrics['clipped_samples_pcm16']
                or item['request_text'] != request_text(item['tags'], item.get('tts_text_override')
                                                        or item.get('tts_input_text', item['canonical_text']))):
            problems.append(item['media_id'])
    since = min(datetime.fromisoformat(x['generation_timestamp']).timestamp() for x in items) - 60
    history = history_items(key, state['voice_id'], state['model'], since)
    by_request = {h.get('request_id'): h for h in history}
    mismatches, missing = [], []
    for item in items:
        found = by_request.get(item.get('request_id'))
        if not found:
            missing.append(item['media_id'])
            continue
        text, voice_id, _ = history_fields(found)
        if text != item['request_text'] or voice_id != state['voice_id'] or found.get('model_id') != state['model']:
            mismatches.append(item['media_id'])
    known = {x.get('request_id') for x in state['items'].values()}
    unexpected = [h.get('history_item_id') for h in history
                  if h.get('request_id') not in known and h.get('date_unix', 0) >= since + 60]
    result = {'status': 'PASS' if not (problems or missing or mismatches or unexpected) else 'FAIL',
              'complete_outputs': len(items), 'problems': problems, 'missing_history': missing,
              'text_voice_model_mismatches': mismatches, 'unexpected_history_items': len(unexpected),
              'credits_used_headers': sum(x.get('credits_used') or 0 for x in state['items'].values()),
              'starting_credits': state['starting_credits'], 'remaining_credits_api': before['remaining'],
              'account_usage_delta': before['used'] - state['starting_usage'], 'output_format': FORMAT}
    save_json(state_path.parent / 'history-audit.json', result)
    return result


if __name__ == '__main__':
    main()
