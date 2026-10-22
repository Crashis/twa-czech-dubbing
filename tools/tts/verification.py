"""Resume-safe pronunciation samples, using the resolver's pilot mode and the production transport.

Only unresolved performances are eligible. This separate ledger never approves a rule and
cannot be used as a production ledger. Its pilot-journal.json can be imported by production
after a human decision, provided the exact text, tags, model and voice still match.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.tts import production as p
from tools.tts.pronunciation import commander_resolver, request_text


def sample_items(plan, routes, output, voice_id, voice_name, resolver):
    candidates = p.items_from_plan(plan, routes, output, voice_id, voice_name, resolver, defer_review=True)
    result = {}
    for row in plan:
        source = row['tts_source_media_id']
        if candidates[source]['status'] != p.DEFERRED:
            continue
        spoken = resolver.resolve(row['czech_text'], 'pilot', source)
        text = request_text(row['recommended_tags'], spoken['tts_input_text'])
        request = {'voice_id': voice_id, 'model_id': routes[source]['selected_model'],
                   'text': text, 'output_format': p.FORMAT}
        result[source] = dict(candidates[source], status='planned', purpose='pronunciation_verification',
                              tts_input_text=spoken['tts_input_text'], request_text=text,
                              applied_pronunciation_overrides=spoken['applied_pronunciation_overrides'],
                              request_sha256=hashlib.sha256(json.dumps(request, ensure_ascii=False,
                                                                      sort_keys=True).encode('utf-8')).hexdigest())
    return result


def export_journal(state, output):
    requests = []
    for item in state['items'].values():
        if item['status'] != 'complete':
            continue
        requests.append(dict(item, media_id=item['tts_source_media_id'], output=item['output_path'],
                             output_format=p.FORMAT, credits=item['credits_used'],
                             submitted_at_utc=item['generation_timestamp']))
    p.save_json(output / 'pilot-journal.json', {'voice_name': state['voice_name'],
                                               'purpose': 'pronunciation_verification', 'requests': requests})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('commander', 'routing', 'output', 'voice-name', 'voice-id'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--generate', action='store_true', help='explicit paid generation; otherwise preflight only')
    parser.add_argument('--auto-retry-technical', action='store_true')
    parser.add_argument('--max-credits', type=int, default=2000)
    args = parser.parse_args()
    output = Path(args.output)
    if not output.resolve().is_relative_to(Path('work').resolve()):
        parser.error('output must stay in ignored work/')
    plan, routes, hashes, _ = p.load_plan(args.commander, Path(args.routing), 'eleven_v4')
    resolver = commander_resolver(args.commander)
    expected = sample_items(plan, routes, output, args.voice_id, args.voice_name, resolver)
    if not expected:
        print('No pronunciation verification is required')
        return
    key = p.api_key()
    voice_id = p.voice_and_models(key, args.voice_name, args.voice_id, {'eleven_v4'})
    before = p.subscription(key)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'audio').mkdir(exist_ok=True)
    path = output / 'verification-state.json'
    frozen = dict(source_hashes=hashes, pronunciation_files=resolver.files,
                  voice_id=voice_id, voice_name=args.voice_name, commander=args.commander)
    if path.exists():
        state = json.loads(path.read_text(encoding='utf-8'))
        if any(state.get(k) != v for k, v in frozen.items()) or set(state['items']) != set(expected):
            raise RuntimeError('Verification inputs changed; refusing regeneration')
        for source, item in state['items'].items():
            if any(item.get(k) != expected[source].get(k) for k in
                   ('request_sha256', 'canonical_text', 'output_path')):
                raise RuntimeError('Verification request changed; refusing regeneration')
    else:
        state = dict(frozen, schema=1, purpose='pronunciation_verification', items=expected,
                     starting_credits=before['remaining'], starting_usage=before['used'], created_at=p.utc_now())
        p.save_json(path, state)
    mini = p.decoder(None)
    p.verify_and_recover(state, path, mini)
    pending = [x for x in state['items'].values() if x['status'] == 'planned']
    ceiling = sum(len(x['request_text']) for x in pending)
    print(json.dumps({'samples': len(expected), 'pending': len(pending), 'credit_ceiling': ceiling}), flush=True)
    if ceiling + p.spent_credits(state) > args.max_credits or ceiling > before['remaining']:
        raise p.HardStop('Verification exceeds the credit ceiling')
    if not args.generate:
        return
    for item in pending:
        p.generate_one(item, key, voice_id, mini, state, path)
        if item['status'] != 'complete' and args.auto_retry_technical:
            p.retry_technical(item, key, state, path, mini)
        export_journal(state, output)
        print(item['tts_source_media_id'], item['status'], flush=True)
    state['latest_credits'] = p.subscription(key)['remaining']
    p.save_json(path, state)
    export_journal(state, output)
    print(json.dumps({'complete': sum(x['status'] == 'complete' for x in state['items'].values()),
                      'samples': len(expected), 'credits': p.spent_credits(state)}), flush=True)


if __name__ == '__main__':
    main()
