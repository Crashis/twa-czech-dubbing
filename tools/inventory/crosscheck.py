"""Compare research inventories and a read-only reference commander dataset."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from tools.inventory.research import workspace_graph
from tools.inventory.research_metadata import duplicate_groups, read_csv, write_csv
from tools.pack.reader import require


def recording_links(primary, advisory):
    """Keep primary voices distinct from generic advisor reference copies."""
    facts, owners, advisors = {}, defaultdict(set), defaultdict(set)
    for datasets, section in [(primary, owners), (advisory, advisors)]:
        for name, rows in datasets.items():
            for mid, row in rows.items():
                if not row.get('pcm_sha256'):
                    continue
                value = {k: row[k] for k in ['pcm_sha256', 'sample_rate', 'channels', 'sample_count']}
                value.update({k: int(value[k]) for k in ['sample_rate', 'channels', 'sample_count']})
                require(mid not in facts or facts[mid] == value, 'Conflicting original recording facts')
                facts[mid] = value
                section[mid].add(name)
    groups = duplicate_groups(facts)
    result = []
    primary_groups, advisor_groups = set(), set()
    for mid, duplicate in groups.items():
        members = duplicate['members']
        primary_names = set().union(*(owners[m] for m in members))
        advisor_names = set().union(*(advisors[m] for m in members))
        if len(primary_names) > 1:
            primary_groups.add(duplicate['duplicate_group'])
        if primary_names and advisor_names:
            advisor_groups.add(duplicate['duplicate_group'])
        if len(primary_names) < 2 and not (primary_names and advisor_names):
            continue
        result.append({'media_id': mid, 'duplicate_group': duplicate['duplicate_group'],
                       'duplicate_content_of': duplicate['duplicate_content_of'], 'kind': duplicate['duplicate_kind'],
                       'members': ';'.join(members), 'inventories': ';'.join(sorted(primary_names | advisor_names)),
                       'primary_inventories': ';'.join(sorted(owners[mid])),
                       'advisor_reference_inventories': ';'.join(sorted(advisors[mid])),
                       'pcm_sha256': facts[mid]['pcm_sha256']})
    return result, primary_groups, advisor_groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--commander-root', required=True)
    parser.add_argument('--left', required=True)
    parser.add_argument('--right', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--stem', help='Output basename; defaults to the selected commander IDs')
    parser.add_argument('--reference-audio-audit', help='Optional private original audit to compare a legacy reference without PCM hashes')
    args = parser.parse_args()
    root, output = Path(args.commander_root), Path(args.output)
    usage = workspace_graph(Path(args.workspace))
    specs = json.loads((Path(args.workspace)/'specs.json').read_text(encoding='utf-8'))
    datasets = {}
    for name in [args.left, args.right, args.reference]:
        folder = root/name
        path = folder/'research/voice-lines.csv'
        if not path.exists():
            path = folder/'media-inventory.csv'
        datasets[name] = {r['media_id']: r for r in read_csv(path)}
    if args.reference_audio_audit:
        facts = json.loads(Path(args.reference_audio_audit).read_text(encoding='utf-8'))['results']
        for mid, row in datasets[args.reference].items():
            row.update({k: facts[mid][k] for k in ['pcm_sha256', 'sample_rate', 'channels', 'sample_count']})
    rows = []
    headers = [n.replace('-', '_') for n in datasets]
    for mid in sorted(set().union(*(set(d) for d in datasets.values())), key=int):
        present = [name for name, data in datasets.items() if mid in data]
        refs = usage.refs[int(mid)]
        other = {usage.owner(r).removeprefix('commander:') for r in refs
                 if usage.owner(r).startswith('commander:')}
        # Use metadata actor identity, avoiding an English display-name inference.
        for spec in specs:
            if spec['id'] in datasets:
                other.discard(spec['actor_name'])
        source = next(datasets[name][mid] for name in [args.left, args.right, args.reference] if mid in datasets[name])
        scope = source.get('sharing_scope', source.get('scope'))
        if scope.endswith('_SPECIFIC'):
            scope = 'COMMANDER_SPECIFIC'
        elif scope not in {'COMMANDER_SPECIFIC', 'CULTURE_SHARED', 'UNIT_TYPE_SHARED', 'GLOBAL_SHARED', 'UNKNOWN_SHARED_SCOPE'}:
            scope = 'CULTURE_SHARED' if scope.endswith('_SHARED') and 'UNKNOWN' not in scope else 'UNKNOWN_SHARED_SCOPE'
        notes = ('Shared inventory ID; every replacement selection must exclude shared ownership' if len(present) > 1 else '')
        if other:
            notes = (notes + '; ' if notes else '') + 'Other explicit commander branches exist; inspect full usage paths'
        rows.append({'media_id': mid, **{head: 'YES' if mid in datasets[name] else 'NO' for head, name in zip(headers, datasets)},
                     'other_commanders': ';'.join(sorted(other)), 'classification': scope, 'notes': notes})
    output.mkdir(parents=True, exist_ok=True)
    fields = ['media_id'] + headers + ['other_commanders', 'classification', 'notes']
    filename = args.stem or args.left + '-' + args.right + '-crosscheck'
    write_csv(output/(filename+'.csv'), rows, fields)
    write_csv(output/'shared-media-analysis.csv', rows, fields)
    intersections = {(a, b): sorted(set(datasets[a]) & set(datasets[b]), key=int)
                     for a, b in [(args.left, args.right), (args.left, args.reference), (args.right, args.reference)]}
    safe = {name: {mid for mid, r in data.items() if r.get('safe_to_replace_for_commander', r.get('safe_to_replace_for_'+name)) == 'YES'}
            for name, data in datasets.items()}
    lines = ['# Cross-commander voice inventory', '',
             'Counts compare primary voice inventories, including relevant shared unit sets. Generic advisor/tutorial references are separate.', '',
             '| Pair | Shared Media IDs | IDs |', '|---|---:|---|']
    for (a, b), ids in intersections.items():
        lines.append(f"| {a} / {b} | {len(ids)} | {', '.join(ids) or 'none'} |")
    conflicts = set().union(*(safe[a] & safe[b] for a, b in intersections))
    lines += ['', f'Safe-candidate Media ID conflicts: **{len(conflicts)}**. This does not create or approve a joint release manifest.', '',
              '| Explicit speaker with shared ownership | Media ID | Other owners |', '|---|---|---|']
    for name in [args.left, args.right]:
        for mid, r in datasets[name].items():
            if r['explicit_commander_speaker'] == 'YES' and r['sharing_scope'] != 'COMMANDER_SPECIFIC':
                lines.append(f"| {name} | {mid} | {r['shared_with']} |")
    lines += ['', 'Overlaps with the reference inventory:', '']
    for name in [args.left, args.right]:
        ids = set(datasets[name]) & set(datasets[args.reference])
        classifications = sorted({datasets[name][mid]['sharing_scope'] for mid in ids})
        replaced = ids & safe[args.reference]
        lines.append(f"- {name}: {len(ids)} IDs; classifications: {', '.join(classifications) or 'none'}; reference replacements affected: {len(replaced)}.")
    advisory = {}
    for name in datasets:
        path = root/name/'research/battle-advice-global-reference.csv'
        if path.exists():
            advisory[name] = {r['media_id']: r for r in read_csv(path)}
    duplicates, primary_groups, advisor_groups = recording_links(datasets, advisory)
    write_csv(output/'cross-commander-duplicate-recordings.csv', duplicates,
              ['media_id', 'duplicate_group', 'duplicate_content_of', 'kind', 'members', 'inventories',
               'primary_inventories', 'advisor_reference_inventories', 'pcm_sha256'])
    lines += ['', f'Exact recording duplicate groups spanning primary commander inventories with different Media IDs: **{len(primary_groups)}**.', '',
              f'Primary-to-generic-advisor duplicate groups: **{len(advisor_groups)}**. Advisor copies are catalogued alongside both research inventories but are not either commander speaking. The duplicate CSV explicitly distinguishes primary_inventories from advisor_reference_inventories.', '',
              'Recording identity does not imply Media ID identity. Ownership and recording deduplication are separate.', '',
              'Culture and unit sets can contain wider fallback reuse. Tone of voice and culture names alone never establish commander ownership.', '']
    for name in [args.left, args.right]:
        advice = root/name/'research/battle-advice-global-reference.csv'
        count = len(read_csv(advice)) if advice.exists() else 0
        lines.append(f'- {name}: {count} file-backed advisor/tutorial reference IDs, excluded from primary voice counts. External-source cookies are not missing WEMs.')
    lines.append('')
    (output/(filename+'.md')).write_text('\n'.join(lines), encoding='utf-8')
    print({a+' / '+b: len(ids) for (a, b), ids in intersections.items()})


if __name__ == '__main__':
    main()
