"""Independent reverse/branch completeness and raw BNK offset verification."""
from tools.inventory.research_graph import ACTOR, group_ids, keys
from tools.pack.reader import require
import struct


def raw_bank_audit(usage, bank_directory):
    count = links = actions = 0
    for bank, info in usage.banks.items():
        raw = (bank_directory / bank).read_bytes()
        for node in info['nodes']:
            require(struct.unpack_from('<I', raw, node['id_offset'])[0] == node['id'], 'Raw HIRC ID differs')
            for field in node.get('children', []) + node.get('actions', []) + node.get('target', []) + node.get('bank_target', []):
                if 'offset' in field:
                    require(struct.unpack_from('<I', raw, int(field['offset']))[0] == int(field['value']), 'Raw playback link differs')
                    links += 1
            for item in node.get('playlist', []):
                field = item['target']
                require(struct.unpack_from('<I', raw, int(field['offset']))[0] == int(field['value']), 'Raw playlist differs')
                links += 1
            if node['type'] == 'CAkActionPlay':
                bank_id = int(info['header']['dwSoundBankID']['value'])
                require(node.get('bank_target') and all(int(f['value']) == bank_id for f in node['bank_target']),
                        'Cross-bank ActionPlay target needs explicit resolution; cannot declare complete')
                actions += 1
            if node['type'] == 'CAkSound':
                for field in node['sourceID']:
                    require(struct.unpack_from('<I', raw, int(field['offset']))[0] == int(field['value']), 'Raw Sound source differs')
                    count += 1
            if node['type'] == 'CAkDialogueEvent':
                require(node.get('mode') and int(node['mode'][0]['value']) == 0, 'Unsupported dialogue selection policy')
                for branch in node['branches']:
                    for field in branch['keys'] + [branch['target']]:
                        require(struct.unpack_from('<I', raw, int(field['offset']))[0] == int(field['value']), 'Raw decision tree differs')
    return {'raw_sound_sources_checked': count, 'raw_hirc_ids_and_decision_fields': 'PASS',
            'raw_playback_link_fields_checked': links, 'local_actionplay_bank_targets_checked': actions,
            'cross_bank_actionplay_links': 0}


def orphan_audit(usage):
    result = []
    for mid, sounds in usage.sounds.items():
        for bank, sid in sounds:
            if bank not in usage.voice_banks or usage.reverse_roots(bank, sid):
                continue
            sound = usage.nodes[bank][sid]
            parents = [int(f['value']) for f in sound.get('DirectParentID', [])]
            sibling_owners = set()
            for parent in parents:
                node = usage.nodes[bank].get(parent, {})
                for child in node.get('children', []):
                    sibling = usage.nodes[bank][int(child['value'])]
                    if sibling['type'] == 'CAkSound':
                        smid = int(sibling['sourceID'][0]['value'])
                        sibling_owners.update(usage.owner(r) for r in usage.refs.get(smid, []))
            result.append({'bank': bank, 'sound_id': sid, 'media_id': mid, 'parent_ids': parents,
                           'sibling_owners': sorted(sibling_owners),
                           'status': 'NO_PLAYBACK_ROOT; sibling ownership is context, not a playable event'})
    return result


def audit_commander(usage, spec):
    relevant = usage.relevant(spec, include_advice=False)
    reach = usage.reachable(spec)
    reverse_relevant, reverse_explicit = set(), set()
    for mid, sounds in usage.sounds.items():
        for bank, sid in sounds:
            for kind, eid, bi in usage.reverse_roots(bank, sid):
                if kind == 'DialogueEvent':
                    event = usage.events[bank, eid]
                    groups, values = group_ids(event), keys(event['branches'][bi])
                    own = ACTOR in groups and values[groups.index(ACTOR)] == spec['actor_id']
                    if own:
                        reverse_explicit.add(mid)
                    if own or (bank, eid, bi) in reach:
                        reverse_relevant.add(mid)
                elif usage.event_names.get(eid, {}).get('owner') == 'commander:' + spec['actor_name']:
                    reverse_relevant.add(mid)
                    reverse_explicit.add(mid)
    # Independent traversal C: direct first-actor branches / named ordinary
    # events followed by an iterative descent, without forward resolver rows.
    explicit = set()
    for bank, info in usage.banks.items():
        nodes = usage.nodes[bank]
        for event in info['nodes']:
            targets = []
            if event['type'] == 'CAkDialogueEvent':
                groups = group_ids(event)
                if ACTOR in groups:
                    targets = [int(b['target']['value']) for b in event['branches']
                               if keys(b)[groups.index(ACTOR)] == spec['actor_id']]
            elif event['type'] == 'CAkEvent' and usage.event_names.get(event['id'], {}).get('owner') == 'commander:' + spec['actor_name']:
                targets = [int(nodes[int(a['value'])]['target'][0]['value']) for a in event['actions']
                           if nodes.get(int(a['value']), {}).get('type') == 'CAkActionPlay']
            stack = [(t, ()) for t in targets]
            while stack:
                target, path = stack.pop()
                if target == 0:
                    continue
                require(target not in path and target in nodes, 'Cycle or missing branch target')
                node = nodes[target]
                if node['type'] == 'CAkSound':
                    explicit.add(int(node['sourceID'][0]['value']))
                else:
                    stack.extend((int(c['value']), path + (target,)) for c in node.get('children', []))
    forward_explicit = {m for m, v in relevant.items() if v['explicit_speaker']}
    # D: parent emote pools are an independent candidate inventory. This catches
    # a playable ordinary event missed by localization-key name normalization.
    # A sibling Sound with no playback root at all cannot be such an event; it
    # is reported separately (and in the corpus orphan audit), never as relevant.
    emote_known, emote_pool, emote_unrooted = set(), set(), set()
    for mid, refs in usage.refs.items():
        for ref in refs:
            if 'emote' not in ref['bank'] or not usage.keyed(ref, spec):
                continue
            emote_known.add(mid)
            sound = usage.nodes[ref['bank']][ref['sound_id']]
            for parent in sound.get('DirectParentID', []):
                node = usage.nodes[ref['bank']].get(int(parent['value']), {})
                for child in node.get('children', []):
                    sibling = usage.nodes[ref['bank']][int(child['value'])]
                    if sibling['type'] == 'CAkSound':
                        rooted = usage.reverse_roots(ref['bank'], sibling['id'])
                        (emote_pool if rooted else emote_unrooted).add(int(sibling['sourceID'][0]['value']))
    emote_delta = sorted(emote_pool ^ emote_known)
    delta = sorted(reverse_relevant ^ set(relevant))
    branch_delta = sorted(explicit ^ forward_explicit | explicit ^ reverse_explicit)
    audits = {str(m): usage.audit_media(m) for m in usage.relevant(spec)}
    unresolved = [m for m, a in audits.items() if a['missing_forward'] or a['missing_reverse'] or a['unrooted_sounds']]
    require(not delta and not branch_delta and not unresolved and not emote_delta, 'Commander completeness/safety discrepancy')
    no_audio = []
    for (bank, eid), event in usage.events.items():
        groups = group_ids(event)
        if ACTOR not in groups:
            continue
        for branch in event['branches']:
            values = keys(branch)
            if values[groups.index(ACTOR)] != spec['actor_id']:
                continue
            target = int(branch['target']['value'])
            stack, sounds = [target] if target else [], []
            while stack:
                node = usage.nodes[bank][stack.pop()]
                if node['type'] == 'CAkSound':
                    sounds.append(node['id'])
                else:
                    stack.extend(int(c['value']) for c in node.get('children', []))
            if not sounds:
                no_audio.append({'bank': bank, 'event_id': eid, 'target_id': target,
                                 'group_ids': groups, 'keys': values,
                                 'kind': 'NULL_LEAF' if target == 0 else 'EMPTY_CONTAINER'})
    return {'status': 'PASS_STRUCTURAL', 'forward_relevant_media': len(relevant),
            'reverse_relevant_media': len(reverse_relevant), 'forward_explicit_speaker_media': len(forward_explicit),
            'reverse_explicit_speaker_media': len(reverse_explicit), 'independent_branch_enumeration_media': len(explicit),
            'forward_reverse_symmetric_difference': delta, 'branch_enumeration_symmetric_difference': branch_delta,
            'unresolved_relevant_sound_references': unresolved, 'per_media_reverse_audit': audits,
            'no_audio_commander_branches': no_audio, 'emote_parent_pool_media': len(emote_pool),
            'emote_named_event_media': len(emote_known), 'emote_pool_symmetric_difference': emote_delta,
            'emote_pool_unrooted_media': sorted(emote_unrooted)}
