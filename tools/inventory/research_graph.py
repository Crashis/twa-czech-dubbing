"""Conservative, commander-independent Wwise inventory and reverse usage audit.

Only metadata is returned. Bank-local IDs are never joined across banks.
Reachability is an analysis model, not a claim about observed game playback.
"""
from collections import defaultdict
from itertools import product

from tools.inventory.names import branch_trie, match_branch
from tools.inventory.voice_map import resolve_bank
from tools.pack.reader import require

ACTOR, CULTURE, UNIT, GENDER = 112324978, 3113488887, 4273992948, 2703688388
ABILITY, BATTLE_EVENT = 1602634982, 636323490
SCOPES = {'COMMANDER_SPECIFIC', 'CULTURE_SHARED', 'UNIT_TYPE_SHARED',
          'GLOBAL_SHARED', 'UNKNOWN_SHARED_SCOPE'}


def group_ids(event):
    return [int(g['group']['value']) for g in event['groups']]


def keys(branch):
    return [int(k['value']) for k in branch['keys']]


class UsageGraph:
    def __init__(self, graph, names, event_names, commander_cultures=None):
        require(not graph['parser_errors_or_skips'], 'Resolve wwiser errors/skips first')
        self.banks = graph['banks']
        self.names = names
        self.event_names = event_names
        self.commander_cultures = commander_cultures or {}
        self.refs = defaultdict(list)
        self.sounds = defaultdict(list)
        self.events = {}
        self.nodes = {}
        self.reverse = {}
        self.voice_banks = set()
        self.empty_branches = []
        self.non_file_sources = []
        for bank, info in self.banks.items():
            # FX/state objects use separate namespaces and may share an ID.
            # They cannot be playback targets in this inventory graph.
            playback = [n for n in info['nodes'] if n['type'] in {
                'CAkSound', 'CAkRanSeqCntr', 'CAkSwitchCntr', 'CAkLayerCntr',
                'CAkActorMixer', 'CAkEvent', 'CAkDialogueEvent', 'CAkActionPlay'}]
            nodes = {n['id']: n for n in playback}
            require(len(nodes) == len(playback), 'Duplicate playback HIRC ID')
            self.nodes[bank] = nodes
            reverse = defaultdict(list)
            self.reverse[bank] = reverse
            for node in nodes.values():
                for child in node.get('children', []):
                    reverse[int(child['value'])].append(('parent', node['id']))
                if node['type'] == 'CAkActionPlay':
                    for target in node['target']:
                        reverse[int(target['value'])].append(('action', node['id']))
                if node['type'] == 'CAkEvent':
                    for action in node['actions']:
                        reverse[int(action['value'])].append(('event', node['id']))
                if node['type'] == 'CAkDialogueEvent':
                    self.events[bank, node['id']] = node
                    for i, br in enumerate(node['branches']):
                        reverse[int(br['target']['value'])].append(('dialogue', node['id'], i))
                if node['type'] == 'CAkSound':
                    self.sounds[int(node['sourceID'][0]['value'])].append((bank, node['id']))
            # Non-voice banks still participate in the independent Sound audit.
            if any(n['type'] == 'CAkDialogueEvent' for n in nodes.values()) or any(
                    n['type'] == 'CAkEvent' and n['id'] in event_names for n in nodes.values()) or bank == 'battle_advice.bnk':
                self.voice_banks.add(bank)
                for ref in resolve_bank(bank, info):
                    if 'media_id' not in ref or ref['event_type'] == 'SoundReference':
                        continue
                    if ref['plugin_id'] != 0x00040001:  # Wwise Vorbis file codec
                        self.non_file_sources.append(ref)
                        continue
                    ref['groups'] = [int(g['group']['value']) for g in ref.get('groups', [])]
                    ref['keys'] = [int(k['value']) for k in ref.pop('conditions', [])]
                    self.refs[ref['media_id']].append(ref)

    def label(self, value):
        return '*' if value == 0 else self.names.get(value, str(value))

    def owner(self, ref):
        if ref['event_type'] == 'Event':
            ev = self.event_names.get(ref['event_id'], {})
            return ev.get('owner', 'unknown:event:' + str(ref['event_id']))
        groups, values = ref['groups'], ref['keys']
        if ACTOR in groups:
            actor = values[groups.index(ACTOR)]  # first occurrence is the speaker
            if actor == 0:
                return 'wildcard:actor'
            name = self.label(actor)
            if name.startswith('Commander_'):
                return 'commander:' + name
            if name.startswith(('Male_', 'Female_')):
                culture = values[groups.index(CULTURE)] if CULTURE in groups else 0
                return f'unit:{culture}:{name}'
            return 'unknown:actor:' + str(actor)
        if CULTURE in groups:
            return 'culture:' + str(values[groups.index(CULTURE)])
        return 'unknown:conditions'

    def keyed(self, ref, spec):
        if ref['event_type'] == 'Event':
            return self.owner(ref) == 'commander:' + spec['actor_name']
        return ACTOR in ref['groups'] and ref['keys'][ref['groups'].index(ACTOR)] == spec['actor_id']

    def reachable(self, spec):
        """Enumerate commander, culture unit sets and conservative fallbacks."""
        reachable = defaultdict(set)
        for (bank, eid), event in self.events.items():
            groups, branches = group_ids(event), event['branches']
            trie = branch_trie(branches)
            contexts = []
            ai = groups.index(ACTOR) if ACTOR in groups else None
            ci = groups.index(CULTURE) if CULTURE in groups else None
            for culture in spec['culture_ids']:
                if ai is not None:
                    actors = {keys(b)[ai] for b in branches}
                    if any(self.label(a).startswith('Commander_') for a in actors):
                        contexts.append(('commander', spec['actor_id'], culture))
                    unit_actors = {keys(b)[ai] for b in branches
                                   if (ci is None or keys(b)[ci] == culture)
                                   and self.label(keys(b)[ai]).startswith(('Male_', 'Female_'))}
                    contexts.extend(('unit:' + self.label(a), a, culture) for a in sorted(unit_actors))
                elif ci is not None:
                    contexts.append(('culture-units', None, culture))
            for label, actor, culture in contexts:
                choices = []
                for i, group in enumerate(groups):
                    if i == ai:
                        choices.append([actor])
                    elif i == ci:
                        choices.append([culture])
                    else:
                        vals = {keys(b)[i] for b in branches}
                        if group == GENDER and ci is not None:
                            vals = {keys(b)[i] for b in branches if keys(b)[ci] == culture} or vals
                            choices.append(sorted(vals))  # only voice genders present for this culture
                        else:
                            sentinel = next(x for x in range(1, 100) if x not in vals)
                            choices.append(sorted(vals | {sentinel}))
                for values in product(*choices):
                    index = match_branch(trie, values)
                    if index is not None:
                        reachable[bank, eid, index].add(f'{label}:culture={culture}')
        return reachable

    def relevant(self, spec, include_advice=True):
        reach = self.reachable(spec)
        result = {}
        for mid, refs in self.refs.items():
            primary = [r for r in refs if self.keyed(r, spec)]
            contextual = [r for r in refs if (r['bank'], r['event_id'], r.get('branch_index')) in reach]
            advice = [r for r in refs if r['bank'] == 'battle_advice.bnk'] if include_advice else []
            if primary or contextual or advice:
                result[mid] = {'primary': primary or contextual or advice,
                               'contexts': sorted({c for r in contextual for c in reach[r['bank'], r['event_id'], r['branch_index']]}),
                               'explicit_speaker': bool(primary), 'advisor_only': not primary and not contextual}
        return result

    def reverse_roots(self, bank, sound_id):
        """Independent Sound-to-root traversal, without using forward rows."""
        found = set()
        stack = [(sound_id, ())]
        while stack:
            target, path = stack.pop()
            require(target not in path, 'Reverse graph cycle')
            for edge in self.reverse[bank].get(target, []):
                kind, parent, *index = edge
                if kind == 'dialogue':
                    found.add(('DialogueEvent', parent, index[0]))
                elif kind == 'event':
                    found.add(('Event', parent, None))
                else:
                    stack.append((parent, path + (target,)))
        return found

    def audit_media(self, mid):
        forward = {(r['bank'], r['sound_id'], r['event_type'], r['event_id'], r.get('branch_index')) for r in self.refs[mid]}
        reverse = {(bank, sid, kind, eid, bi) for bank, sid in self.sounds[mid]
                   for kind, eid, bi in self.reverse_roots(bank, sid)}
        uncovered = [(bank, sid) for bank, sid in self.sounds[mid]
                     if not self.reverse_roots(bank, sid)]
        # A reverse root in a non-voice bank must also block commander safety.
        return {'forward_count': len(forward), 'reverse_count': len(reverse),
                'missing_forward': sorted(reverse - forward, key=str),
                'missing_reverse': sorted(forward - reverse, key=str), 'unrooted_sounds': uncovered}

    def classify(self, mid, spec):
        refs = self.refs[mid]
        owners = {self.owner(r) for r in refs}
        audit = self.audit_media(mid)
        expected = 'commander:' + spec['actor_name']
        if audit['missing_forward'] or audit['missing_reverse'] or audit['unrooted_sounds'] or any(o.startswith('unknown:') for o in owners):
            return 'UNKNOWN_SHARED_SCOPE', owners, audit
        if owners == {expected}:
            return 'COMMANDER_SPECIFIC', owners, audit
        # Explicit unit-type selection beats culture-wide sharing; an additional
        # global/wildcard or commander owner prevents this narrower label.
        unit_only = owners and all(o.startswith(('unit:', 'culture:')) for o in owners)
        typed = unit_only and all(UNIT in r['groups'] and r['keys'][r['groups'].index(UNIT)] != 0 for r in refs)
        cultures = {r['keys'][r['groups'].index(CULTURE)] for r in refs if CULTURE in r['groups']}
        if typed and cultures and 0 not in cultures and len(cultures) == 1:
            return 'UNIT_TYPE_SHARED', owners, audit
        if unit_only and len(cultures) == 1 and 0 not in cultures:
            return 'CULTURE_SHARED', owners, audit
        if owners and all(o.startswith('commander:') for o in owners):
            affiliations = [self.commander_cultures.get(o.removeprefix('commander:')) for o in owners]
            if all(affiliations) and len({tuple(sorted(a)) for a in affiliations}) == 1:
                return 'CULTURE_SHARED', owners, audit
            return 'GLOBAL_SHARED', owners, audit
        if any(o.startswith(('global:', 'wildcard:')) for o in owners) or len(cultures) > 1:
            return 'GLOBAL_SHARED', owners, audit
        return 'UNKNOWN_SHARED_SCOPE', owners, audit


def safety(scope, silent):
    if silent:
        return 'NO_SILENT'
    if scope == 'UNKNOWN_SHARED_SCOPE':
        return 'NO_UNKNOWN'
    return 'YES' if scope == 'COMMANDER_SPECIFIC' else 'NO_SHARED'
