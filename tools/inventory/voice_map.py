"""Resolve bank-scoped DialogueEvent branches to external Media IDs.

Ownership needs review across ALL relevant banks. This tool never marks a
commander safe merely because one of its references mentions that commander.
"""
import argparse
import json
from pathlib import Path
from tools.pack.reader import require


def resolve_bank(bank, info):
    by_id = {n['id']: n for n in info['nodes']}
    require(len(by_id) == len(info['nodes']), 'Duplicate object ID inside bank')

    def walk(target, path=()):
        if target == 0:
            return []
        require(target not in path, 'Cycle in HIRC graph')
        require(target in by_id, f'Unresolved HIRC link in {bank}: {target}')
        node = by_id[target]
        chain = path + (target,)
        if node['type'] == 'CAkSound':
            return [(node, chain)]
        # Wwise permits an intentionally empty random container. It is a
        # structural no-audio branch, not an unresolved external WEM.
        if node['type'] == 'CAkRanSeqCntr' and not node.get('children'):
            require(not node.get('playlist'), 'Empty container has a nonempty playlist')
            return []
        require(node.get('children'), f'Unsupported terminal object in {bank}: {target}')
        if node['type'] == 'CAkRanSeqCntr':
            require({int(c['value']) for c in node['children']} == {int(p['target']['value']) for p in node['playlist']}, 'Playlist/children mismatch')
        return [item for child in node['children'] for item in walk(int(child['value']), chain)]

    rows = []
    for event in info['nodes']:
        if event['type'] == 'CAkEvent':
            for action in event['actions']:
                action_id = int(action['value'])
                require(action_id in by_id, 'Unresolved event action')
                action_node = by_id[action_id]
                if action_node['type'] != 'CAkActionPlay':
                    continue
                target = int(action_node['target'][0]['value'])
                for sound, chain in walk(target):
                    rows.append({'bank': bank, 'event_id': event['id'], 'event_type': 'Event',
                                 'action_id': action_id, 'target': target, 'conditions': [],
                                 'sound_id': sound['id'], 'object_path': chain,
                                 'media_id': int(sound['sourceID'][0]['value']),
                                 'plugin_id': int(sound['ulPluginID'][0]['value']), 'ownership': 'UNREVIEWED'})
        if event['type'] != 'CAkDialogueEvent':
            continue
        for branch_index, branch in enumerate(event['branches']):
            target = int(branch['target']['value'])
            context = {'bank': bank, 'event_id': event['id'], 'event_type': 'DialogueEvent', 'branch_index': branch_index, 'groups': event['groups'], 'conditions': branch['keys'],
                       'target': target, 'weight': branch['weight'], 'probability': branch['probability']}
            if target == 0:
                rows.append(context | {'null_branch': True})
            for sound, chain in walk(target):
                rows.append(context | {'sound_id': sound['id'], 'object_path': chain,
                                       'media_id': int(sound['sourceID'][0]['value']),
                                       'plugin_id': int(sound['ulPluginID'][0]['value']),
                                       'stream_type': sound['StreamType'], 'ownership': 'UNREVIEWED'})
    # Include every Sound, even one unreachable from known voice events. This
    # exposes potential cross-bank sharing rather than silently discarding it.
    for sound in info['nodes']:
        if sound['type'] == 'CAkSound':
            rows.append({'bank': bank, 'event_type': 'SoundReference', 'sound_id': sound['id'],
                         'media_id': int(sound['sourceID'][0]['value']),
                         'plugin_id': int(sound['ulPluginID'][0]['value']), 'ownership': 'UNREVIEWED'})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    graph = json.loads(Path(args.graph).read_text(encoding='utf-8'))
    require(not graph['parser_errors_or_skips'], 'wwiser parse errors/skips must be resolved')
    rows = [r for bank, info in graph['banks'].items() for r in resolve_bank(bank, info)]
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'references': len(rows), 'ownership': 'UNREVIEWED'}))
