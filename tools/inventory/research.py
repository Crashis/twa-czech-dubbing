"""Offline research workspace commands; originals always stay outside the repo."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re

from tools.inventory.names import fnv1
from tools.inventory.original_audio import extract_decode, private_directory, sha256
from tools.inventory.research_audit import audit_commander, orphan_audit, raw_bank_audit
from tools.inventory.research_graph import UsageGraph
from tools.pack.reader import ArenaPack, require
from tools.resources import ROOT


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def workspace_graph(workspace, profiles=None):
    return UsageGraph(load(workspace/'corpus/graph.json'), {int(k): v for k, v in load(workspace/'names.json').items()},
                      {int(k): v for k, v in load(workspace/'event-names.json').items()},
                      (profiles or {}).get('commander_cultures'))


def scan_banks(game_data, workspace):
    """Read every live PACK index and retain every distinct BNK, without VFS guesses."""
    game_data = Path(game_data).resolve(strict=True)
    workspace = private_directory(workspace, [ROOT, game_data.parent])
    corpus = workspace/'corpus'
    corpus.mkdir(exist_ok=True)
    def inspect(path):
        pack = ArenaPack(path)
        banks = [{'path': e.path, 'size': e.size, 'sha256': sha256_bytes(pack.read(e))}
                 for e in pack.entries if e.path.lower().endswith('.bnk')]
        return {'pack': path.name, 'entry_count': len(pack.entries), 'rsa': 'PASS', 'banks': banks}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(inspect, sorted(game_data.glob('*.pack'))))
    # Save scan evidence before detecting conflicting aliases, so a conflict is reviewable.
    save(corpus/'all-pack-bank-scan.json', results)
    inputs = []
    for result in results:
        if not result['banks']:
            continue
        pack = ArenaPack(game_data/result['pack'])
        by_path = {e.path: e for e in pack.entries}
        for bank in result['banks']:
            dest = corpus/Path(bank['path']).name
            raw = pack.read(by_path[bank['path']])
            require(not dest.exists() or dest.read_bytes() == raw, 'Conflicting bank aliases: preserve separate corpora before continuing')
            if not dest.exists():
                dest.write_bytes(raw)
            inputs.append({'pack': result['pack'], **bank, 'rsa': 'PASS'})
    save(corpus/'bank-inputs.json', inputs)
    return {'pack_indexes': len(results), 'unique_banks': len({b['sha256'] for b in inputs}), 'RSA': 'PASS'}


def sha256_bytes(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def emote_pool_events(usage, spec, kinds, max_variant=9):
    """Exact FNV-1 names for unnamed Events that play Sounds in the commander's own emote pools.

    The stem is taken from the commander's already named emote Events. A candidate
    <stem><kind>_<n> is kept only when its hash equals an unnamed Event playing a
    sibling Sound of those Events; a hash elsewhere in the bank is never accepted.
    """
    owner = 'commander:' + spec['actor_name']
    stems, pools = set(), set()
    for refs in usage.refs.values():
        for ref in refs:
            event = usage.event_names.get(ref['event_id'], {}) if ref['event_type'] == 'Event' else {}
            match = re.search(r'(?i)_emo(?:te)?_', event.get('name', ''))
            if 'emote' not in ref['bank'] or event.get('owner') != owner or not match:
                continue
            stems.add(event['name'][:match.end()])
            sound = usage.nodes[ref['bank']][ref['sound_id']]
            pools.update((ref['bank'], int(p['value'])) for p in sound.get('DirectParentID', []))
    unnamed = {}
    for bank, parent in sorted(pools):
        for child in usage.nodes[bank].get(parent, {}).get('children', []):
            node = usage.nodes[bank].get(int(child['value']), {})
            if node.get('type') == 'CAkSound':
                for kind, eid, _ in usage.reverse_roots(bank, node['id']):
                    if kind == 'Event' and eid not in usage.event_names:
                        unnamed[eid] = (bank, parent)
    found = {}
    for stem in sorted(stems):
        for kind in kinds:
            for number in range(max_variant + 1):
                name = f'{stem}{kind}_{number}'
                eid = fnv1(name)
                if eid not in unnamed:
                    continue
                require(eid not in found or found[eid]['name'].lower() == name.lower(), 'Conflicting emote pool event hash')
                found[eid] = {'name': name, 'owner': owner, 'bank': unnamed[eid][0], 'pool_container_id': unnamed[eid][1],
                              'source': 'emote parent pool of the commander\'s localized emote Events',
                              'normalization': 'exact FNV-1 of commander emote stem + candidate kind/variant, '
                                               'matched only against an unnamed Event playing a Sound in that pool'}
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--commander', action='append',
                        help='Limit enumerate/audit/decode/jobs to these spec IDs; other workspace results stay untouched')
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('scan')
    scan.add_argument('--game-data', required=True)
    sub.add_parser('enumerate')
    sub.add_parser('audit')
    jobs_parser = sub.add_parser('jobs')
    jobs_parser.add_argument('--output', default='stt-jobs.json')
    jobs_parser.add_argument('--pending-model', help='Omit recordings already present in stt-<model>*.json results')
    jobs_parser.add_argument('--explicit-only', action='store_true', help='Only recordings with an explicit commander speaker')
    review = sub.add_parser('review-jobs')
    review.add_argument('--output', default='stt-review-shared-jobs.json')
    emotes = sub.add_parser('emote-events')
    emotes.add_argument('--localization', required=True, help='Original localization PACK containing chat tags')
    pool = sub.add_parser('emote-pool-events')
    pool.add_argument('--kinds', required=True, help='Comma-separated candidate emote kinds; only exact FNV-1 pool matches are kept')
    pool.add_argument('--max-variant', type=int, default=9)
    decode = sub.add_parser('decode')
    decode.add_argument('--pack', required=True)
    decode.add_argument('--canonical-sha256', required=True)
    decode.add_argument('--decoder', required=True)
    decode.add_argument('--game-directory', required=True)
    args = parser.parse_args()
    if args.command == 'scan':
        print(json.dumps(scan_banks(args.game_data, args.workspace)))
        return
    workspace = private_directory(args.workspace, [ROOT] + ([args.game_directory] if args.command == 'decode' else []))
    specs = load(workspace/'specs.json')
    for spec in specs:
        require(fnv1(spec['actor_name']) == spec['actor_id'], 'Commander name/hash mismatch')
        require([fnv1(n) for n in spec['culture_names']] == spec['culture_ids'], 'Culture name/hash mismatch')
        require(spec['id'].replace('-', '').replace('_', '').isalnum(), 'Invalid workspace commander ID')
    if args.commander:
        require(set(args.commander) <= {s['id'] for s in specs}, 'Unknown workspace commander')
        specs = [s for s in specs if s['id'] in args.commander]
    if args.command in {'enumerate', 'audit', 'emote-pool-events'}:
        usage = workspace_graph(workspace)
    if args.command == 'enumerate':
        for spec in specs:
            folder = workspace/spec['id']
            folder.mkdir(exist_ok=True)
            save(folder/'graph-inventory.json', usage.relevant(spec))
            print(spec['id'], len(usage.relevant(spec, include_advice=False)))
    elif args.command == 'audit':
        raw = raw_bank_audit(usage, workspace/'corpus')
        scan = load(workspace/'corpus/all-pack-bank-scan.json')
        raw.update(pack_indexes_checked=len(scan), parsed_bank_count=len(usage.banks),
                   parsed_voicebank_count=len(usage.voice_banks), pack_bank_sources=sum(bool(r.get('banks')) for r in scan))
        orphans = orphan_audit(usage)
        path = workspace/'completeness.json'
        complete = load(path) if args.commander and path.exists() else {}
        complete.update({s['id']: audit_commander(usage, s) | raw | {'all_voice_orphans': orphans} for s in specs})
        save(path, complete)
        print(json.dumps(raw | {'commander_audits': len(specs), 'voice_orphans': orphans}))
    elif args.command == 'emote-events':
        from tools.inventory.localization import chat_tag_events, loc_rows
        graph = load(workspace/'corpus/graph.json')
        event_ids = {n['id'] for info in graph['banks'].values() for n in info['nodes'] if n['type'] == 'CAkEvent'}
        events = load(workspace/'event-names.json')
        actors = [n for n in load(workspace/'names.json').values() if n.startswith('Commander_')]
        pack = ArenaPack(args.localization)  # validates RSA
        found = {}
        for entry in pack.entries:
            if 'chat_tags' in entry.path and entry.path.endswith('.loc'):
                found.update(chat_tag_events(loc_rows(pack.read(entry)), event_ids, actors,
                                             Path(args.localization).name + ':' + entry.path))
        added = {}
        for eid, event in found.items():
            prior = events.get(str(eid))
            if prior:
                require(prior['owner'] == event['owner'] and prior.get('key') == event['key'], 'Conflicting event-name hash')
            else:
                added[str(eid)] = event
        events.update(added)
        save(workspace/'event-names.json', events)
        print(json.dumps({'chat_tag_events_matched': len(found), 'added': {k: v['name'] for k, v in added.items()}}))
    elif args.command == 'emote-pool-events':
        events = load(workspace/'event-names.json')
        kinds = [k.strip() for k in args.kinds.split(',') if k.strip()]
        added = {}
        for spec in specs:
            for eid, event in emote_pool_events(usage, spec, kinds, args.max_variant).items():
                prior = events.get(str(eid))
                require(not prior or prior['owner'] == event['owner'], 'Conflicting event-name hash')
                if not prior:
                    added[str(eid)] = event
        events.update(added)
        save(workspace/'event-names.json', events)
        print(json.dumps({'added': {k: v['name'] for k, v in added.items()}}))
    elif args.command == 'decode':
        for spec in specs:
            ids = load(workspace/spec['id']/'graph-inventory.json')
            result = extract_decode(args.pack, args.canonical_sha256, ids, workspace/spec['id'], args.decoder,
                                    [ROOT, args.game_directory], workers=4)
            print(spec['id'], len(result['results']))
    elif args.command == 'jobs':
        jobs = {}
        done = set()
        if args.pending_model:
            for path in workspace.glob('stt-' + args.pending_model + '*.json'):
                done.update(load(path)['results'])
        for spec in specs:
            rel = load(workspace/spec['id']/'graph-inventory.json')
            audio = load(workspace/spec['id']/'original-audio-audit.json')['results']
            for mid, fact in audio.items():
                if fact['silent_placeholder'] == 'YES':
                    continue
                key = fact['pcm_sha256']
                job = jobs.setdefault(key, {'key': key, 'wav': str(workspace/spec['id']/'decoded-wav'/(mid+'.wav')), 'media_ids': [], 'priority': 2})
                job['media_ids'].append(spec['id']+':'+mid)
                if rel[mid]['explicit_speaker']:
                    job['priority'] = 0
        selected = [j for j in jobs.values() if j['key'] not in done and (j['priority'] == 0 or not args.explicit_only)]
        require(Path(args.output).name == args.output and args.output.endswith('.json'), 'Jobs output must be a workspace file name')
        save(workspace/args.output, sorted(selected, key=lambda j: (j['priority'], j['media_ids'][0])))
        print(json.dumps({'unique_recordings': len(jobs), 'selected': len(selected), 'already_transcribed': len(jobs) - len(selected)}))
    elif args.command == 'review-jobs':
        from tools.inventory.research_metadata import similarity, norm, NON_SPEECH_HYPOTHESES
        models = {}
        for label in ['base.en', 'small.en', 'medium.en']:
            models[label] = {}
            for path in sorted(workspace.glob('stt-'+label+'*.json')):
                models[label].update(load(path)['results'])
        primary = set()
        for spec in specs:
            path = workspace/spec['id']/'graph-inventory.json'
            if path.exists():
                primary.update(spec['id']+':'+mid for mid, context in load(path).items() if not context['advisor_only'])
        review = []
        jobs = {}
        for path in sorted(workspace.glob('stt-jobs*.json')):
            for job in load(path):
                jobs.setdefault(job['key'], job)
        for job in jobs.values():
            key = job['key']
            if key in models['medium.en'] or not any(m in primary for m in job['media_ids']):
                continue
            if key not in models['base.en'] or key not in models['small.en']:
                continue
            a, b = [models[m][key].get('text', '') for m in ['base.en', 'small.en']]
            score = similarity(a, b)
            if score < .94 or norm(a) in NON_SPEECH_HYPOTHESES or norm(b) in NON_SPEECH_HYPOTHESES:
                review.append(job | {'prior_similarity': score})
        review.sort(key=lambda j: j['prior_similarity'])
        require(Path(args.output).name == args.output and args.output.endswith('.json'), 'Jobs output must be a workspace file name')
        save(workspace/args.output, review)
        print(json.dumps({'additional_uncertain_recordings': len(review)}))


if __name__ == '__main__':
    main()
