"""Discover commanders and resolve overlap before any build or installation."""
import copy
from itertools import combinations
import json

from tools import mod
from tools.pack.reader import require


def discover():
    return [mod.load_manifest(p.parent.name) for p in sorted(
        (mod.ROOT / 'data/commanders').glob('*/manifest.json'))]


def merge_manifests(parts, release):
    require(len(parts) > 1, 'A joint release needs at least two commanders')
    parts = sorted(parts, key=lambda m: m['commander'])
    require(len({p['commander'] for p in parts}) == len(parts), 'Duplicate commander selection')
    merged = {}
    silent = set()
    for part in parts:
        require(part['base'] == parts[0]['base'] and part['runtime_slot'] == parts[0]['runtime_slot']
                and part['wem_format'] == parts[0]['wem_format'], 'Incompatible commander bases/formats')
        silent.update(part['silent_placeholder_ids'])
        for spec in part['replacements']:
            mid = spec['media_id']
            if mid in merged:
                other = {k: v for k, v in merged[mid].items() if k != 'source_commander'}
                require(other == spec, 'CONFLICT: incompatible replacement for Media ID ' + mid)
            else:
                merged[mid] = dict(spec, source_commander=part['commander'])
    require(not silent.intersection(merged), 'CONFLICT: replacement overlaps a silent placeholder')
    require(release['changed_entries'] == len(merged) and
            release['unchanged_entries'] + len(merged) == parts[0]['base']['entry_count'], 'Joint counts mismatch')
    result = copy.deepcopy(parts[0])
    result.update(commander='combined', components=[p['commander'] for p in parts],
                  display_name=' + '.join(p['display_name'] for p in parts),
                  replacements=sorted(merged.values(), key=lambda s: int(s['media_id'])),
                  silent_placeholder_ids=sorted(silent), expected_replacement_count=len(merged),
                  expected_spoken_count=len(merged), release=release)
    return result


def selection(parts):
    require(bool(parts), 'Select at least one commander')
    if len(parts) == 1:
        return parts[0]
    # A complete, independently reproduced whole-PACK hash is mandatory even for combinations.
    key = '+'.join(sorted(p['commander'] for p in parts))
    descriptor = mod.ROOT / 'data/releases' / (key + '.json')
    # Check conflicts even when the joint release has not yet been approved.
    count = len({s['media_id'] for p in parts for s in p['replacements']})
    merge_manifests(parts, {'changed_entries': count,
                          'unchanged_entries': parts[0]['base']['entry_count'] - count})
    require(descriptor.is_file(), 'This commander combination has no validated joint release yet')
    joint = json.loads(descriptor.read_text(encoding='utf-8'))
    require(joint['commanders'] == key.split('+'), 'Joint release selection mismatch')
    return merge_manifests(parts, joint['release'])


def known_manifests():
    """All validated states the installer can recognize, including joint builds."""
    parts = discover()
    known = list(parts)
    for count in range(2, len(parts) + 1):
        for group in combinations(parts, count):
            key = '+'.join(sorted(p['commander'] for p in group))
            if (mod.ROOT / 'data/releases' / (key + '.json')).is_file():
                known.append(selection(group))
    hashes = [m['release']['sha256'] for m in known]
    require(len(hashes) == len(set(hashes)), 'Ambiguous known release hashes')
    return known
