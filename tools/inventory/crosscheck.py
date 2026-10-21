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


def safe_value(name, row):
    return row.get('safe_to_replace_for_commander') or row.get('safe_to_replace_for_' + name, '')


def inventory_pairs(new, references):
    """New research inventories are compared with each other and with every reference."""
    return [(a, b) for i, a in enumerate(new) for b in new[i + 1:]] + [(a, b) for a in new for b in references]


def pair_overlaps(datasets, pairs):
    """Shared IDs per pair; any shared ID that either side may replace is a conflict."""
    safe = {name: {mid for mid, r in data.items() if safe_value(name, r) == 'YES'} for name, data in datasets.items()}
    result = {}
    for a, b in pairs:
        ids = sorted(set(datasets[a]) & set(datasets[b]), key=int)
        conflicts = [mid for mid in ids if mid in safe[a] or mid in safe[b]]
        status = 'CONFLICT' if conflicts else 'SHARED_NOT_SAFE' if ids else 'NO_OVERLAP'
        result[a, b] = {'ids': ids, 'safe_conflicts': conflicts, 'status': status,
                        'both_safe': [mid for mid in ids if mid in safe[a] and mid in safe[b]]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--commander-root', required=True)
    parser.add_argument('--left', required=True)
    parser.add_argument('--right', action='append', default=[],
                        help='Optional further new inventory (repeatable); omit to check one commander against the references')
    parser.add_argument('--reference', action='append', required=True, help='Repeatable read-only comparison inventory')
    parser.add_argument('--output', required=True)
    parser.add_argument('--stem', help='Output basename; defaults to the selected commander IDs')
    parser.add_argument('--reference-audio-audit', action='append', default=[],
                        help='[NAME=]PATH private original audit for a legacy reference without PCM hashes; '
                             'without NAME it applies to the first reference')
    parser.add_argument('--duplicates-output', default='cross-commander-duplicate-recordings.csv')
    parser.add_argument('--shared-analysis-output', default='shared-media-analysis.csv', help="'' skips this copy")
    args = parser.parse_args()
    root, output = Path(args.commander_root), Path(args.output)
    usage = workspace_graph(Path(args.workspace))
    specs = json.loads((Path(args.workspace)/'specs.json').read_text(encoding='utf-8'))
    new = [args.left] + args.right
    order = new + args.reference
    require(len(set(order)) == len(order), 'Duplicate crosscheck inventory')
    datasets = {}
    for name in order:
        folder = root/name
        path = folder/'research/voice-lines.csv'
        if not path.exists():
            path = folder/'media-inventory.csv'
        datasets[name] = {r['media_id']: r for r in read_csv(path)}
    for item in args.reference_audio_audit:
        name, path = item.split('=', 1) if '=' in item else (args.reference[0], item)
        require(name in args.reference, 'Audio audit names an unknown reference')
        facts = json.loads(Path(path).read_text(encoding='utf-8'))['results']
        for mid, row in datasets[name].items():
            row.update({k: facts[mid][k] for k in ['pcm_sha256', 'sample_rate', 'channels', 'sample_count']})
    rows = []
    headers = [n.replace('-', '_') for n in datasets]
    differing = []
    for mid in sorted(set().union(*(set(d) for d in datasets.values())), key=int):
        present = [name for name, data in datasets.items() if mid in data]
        refs = usage.refs[int(mid)]
        other = {usage.owner(r).removeprefix('commander:') for r in refs
                 if usage.owner(r).startswith('commander:')}
        # Use metadata actor identity, avoiding an English display-name inference.
        for spec in specs:
            if spec['id'] in datasets:
                other.discard(spec['actor_name'])
        scopes = []
        for name in present:
            scope = datasets[name][mid].get('sharing_scope', datasets[name][mid].get('scope'))
            if scope.endswith('_SPECIFIC'):
                scope = 'COMMANDER_SPECIFIC'
            elif scope not in {'COMMANDER_SPECIFIC', 'CULTURE_SHARED', 'UNIT_TYPE_SHARED', 'GLOBAL_SHARED', 'UNKNOWN_SHARED_SCOPE'}:
                scope = 'CULTURE_SHARED' if scope.endswith('_SHARED') and 'UNKNOWN' not in scope else 'UNKNOWN_SHARED_SCOPE'
            scopes.append(scope)
        notes = ('Shared inventory ID; every replacement selection must exclude shared ownership' if len(present) > 1 else '')
        if other:
            notes = (notes + '; ' if notes else '') + 'Other explicit commander branches exist; inspect full usage paths'
        if len(set(scopes)) > 1:
            differing.append(mid)
            notes = (notes + '; ' if notes else '') + 'Classification differs between inventories: ' + \
                ', '.join(f'{n}={s}' for n, s in zip(present, scopes))
        rows.append({'media_id': mid, **{head: 'YES' if mid in datasets[name] else 'NO' for head, name in zip(headers, datasets)},
                     'other_commanders': ';'.join(sorted(other)), 'classification': scopes[0],
                     'safe': '; '.join(f'{n}={safe_value(n, datasets[n][mid]) or "UNKNOWN"}' for n in present),
                     'notes': notes})
    output.mkdir(parents=True, exist_ok=True)
    fields = ['media_id'] + headers + ['other_commanders', 'classification', 'safe', 'notes']
    filename = args.stem or '-'.join(new) + '-crosscheck'
    write_csv(output/(filename+'.csv'), rows, fields)
    if args.shared_analysis_output:
        write_csv(output/args.shared_analysis_output, rows, fields)
    overlaps = pair_overlaps(datasets, inventory_pairs(new, args.reference))
    lines = ['# Cross-commander voice inventory', '',
             'Counts compare primary voice inventories, including relevant shared unit sets. Generic advisor/tutorial references are separate.', '',
             '| Pair | Shared Media IDs | Shared IDs safe for either side | Status | IDs |', '|---|---:|---:|---|---|']
    for (a, b), item in overlaps.items():
        ids = item['ids']
        listed = ', '.join(ids) if len(ids) <= 40 else f'{len(ids)} IDs; every row is listed in the CSV'
        lines.append(f"| {a} / {b} | {len(ids)} | {len(item['safe_conflicts'])} | {item['status']} | {listed or 'none'} |")
    conflicts = set().union(*(set(item['both_safe']) for item in overlaps.values()))
    lines += ['', f'Safe-candidate Media ID conflicts: **{len(conflicts)}**. This does not create or approve a joint release manifest.', '',
              f'Media IDs classified differently by two inventories: **{len(differing)}**'
              + (f" ({', '.join(differing)})" if differing else '') + '.', '',
              '| Explicit speaker with shared ownership | Media ID | Other owners |', '|---|---|---|']
    for name in new:
        for mid, r in datasets[name].items():
            if r['explicit_commander_speaker'] == 'YES' and r['sharing_scope'] != 'COMMANDER_SPECIFIC':
                lines.append(f"| {name} | {mid} | {r['shared_with']} |")
    lines += ['', 'Overlaps with the reference inventories:', '']
    for name in new:
        for reference in args.reference:
            ids = set(datasets[name]) & set(datasets[reference])
            classifications = sorted({datasets[name][mid]['sharing_scope'] for mid in ids})
            replaced = {mid for mid in ids if safe_value(reference, datasets[reference][mid]) == 'YES'}
            lines.append(f"- {name} / {reference}: {len(ids)} IDs; classifications: {', '.join(classifications) or 'none'}; "
                         f"reference safe/replacement IDs affected: {len(replaced)}.")
    advisory = {}
    for name in datasets:
        path = root/name/'research/battle-advice-global-reference.csv'
        if path.exists():
            advisory[name] = {r['media_id']: r for r in read_csv(path)}
    duplicates, primary_groups, advisor_groups = recording_links(datasets, advisory)
    write_csv(output/args.duplicates_output, duplicates,
              ['media_id', 'duplicate_group', 'duplicate_content_of', 'kind', 'members', 'inventories',
               'primary_inventories', 'advisor_reference_inventories', 'pcm_sha256'])
    lines += ['', f'Exact recording duplicate groups spanning primary commander inventories with different Media IDs: **{len(primary_groups)}**.', '',
              f'Primary-to-generic-advisor duplicate groups: **{len(advisor_groups)}**. Advisor copies are catalogued alongside both research inventories but are not either commander speaking. The duplicate CSV explicitly distinguishes primary_inventories from advisor_reference_inventories.', '',
              'Recording identity does not imply Media ID identity. Ownership and recording deduplication are separate.', '',
              'Culture and unit sets can contain wider fallback reuse. Tone of voice and culture names alone never establish commander ownership.', '']
    for name in new:
        advice = root/name/'research/battle-advice-global-reference.csv'
        count = len(read_csv(advice)) if advice.exists() else 0
        lines.append(f'- {name}: {count} file-backed advisor/tutorial reference IDs, excluded from primary voice counts. External-source cookies are not missing WEMs.')
    lines.append('')
    (output/(filename+'.md')).write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({a+' / '+b: {'shared': len(v['ids']), 'status': v['status']} for (a, b), v in overlaps.items()}))


if __name__ == '__main__':
    main()
