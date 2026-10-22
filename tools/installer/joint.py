"""Create a validated joint descriptor from a canonical original, offline only."""
import argparse
import filecmp
import hashlib
import json
import os
from pathlib import Path
import shutil
from itertools import combinations

from tools import mod
from tools.installer.catalog import discover_all, merge_manifests, selection
from tools.pack.reader import ArenaPack, require
from tools.wem.production import save


def composition_hashes(original, spans):
    """Two independent hashes of an exact-size composition; original bytes are never modified."""
    patched = bytearray(original)
    streamed = hashlib.sha256()
    view = memoryview(original)
    previous = 0
    for offset, size, payload in sorted(spans):
        require(offset >= previous and size == len(payload) and size > 0
                and offset + size <= len(original), 'Invalid/overlapping exact-size composition span')
        patched[offset:offset + size] = payload
        streamed.update(view[previous:offset])
        streamed.update(payload)
        previous = offset + size
    streamed.update(view[previous:])
    direct = hashlib.sha256(patched).hexdigest()
    require(direct == streamed.hexdigest(), 'Independent composition hashes differ')
    return direct


def create_descriptors(base_path, work_path):
    """Prepare all selection metadata without building every PACK or exercising transitions.

    Every composition starts from the verified canonical bytes. A separate streaming hash
    reproduces each result. Existing descriptors and singleton release hashes must agree.
    Physical PACK/RSA/full-entry integration tests remain a separate targeted operation.
    """
    parts = discover_all()
    require(len(parts) >= 2, 'At least two production modules are required')
    work = Path(work_path).resolve()
    require(work.is_relative_to(mod.ROOT / 'work'), 'Metadata reports must remain under work/')
    base = Path(base_path).resolve(strict=True)
    require(not base.is_relative_to(mod.ROOT) and mod.sha256(base) == parts[0]['base']['sha256'],
            'Unknown canonical original')
    pack = ArenaPack(base)
    original = base.read_bytes()
    require(hashlib.sha256(original).hexdigest() == parts[0]['base']['sha256'], 'Canonical source changed')
    entries = {entry.path: entry for entry in pack.entries}
    payloads = {}
    validation = {}
    for part in parts:
        require(part['base'] == parts[0]['base'], 'Incompatible canonical bases')
        mod.check_structure(pack, part)
        validation[part['commander']] = mod.validate_data(part)['status']
        for spec in part['replacements']:
            entry = entries[spec['path']]
            require((entry.offset, entry.size) == (spec['offset'], spec['size']), 'Entry geometry mismatch')
            require(hashlib.sha256(original[entry.offset:entry.offset + entry.size]).hexdigest()
                    == spec['original_sha256'], 'Original entry hash mismatch')
            payload = (mod.ROOT / part['replacement_directory'] / (spec['media_id'] + '.wem')).read_bytes()
            require(len(payload) == entry.size and hashlib.sha256(payload).hexdigest() == spec['sha256'],
                    'Replacement changed during metadata preparation')
            payloads[(part['commander'], spec['media_id'])] = payload
    descriptors = []
    checked = []
    for count in range(1, len(parts) + 1):
        for group in combinations(parts, count):
            names = sorted(p['commander'] for p in group)
            key = '+'.join(names)
            if count == 1:
                merged = group[0]
            else:
                total = len({s['media_id'] for p in group for s in p['replacements']})
                merged = merge_manifests(group, dict(changed_entries=total,
                                                    unchanged_entries=len(pack.entries)-total))
            spans = [(s['offset'], s['size'], payloads[(s.get('source_commander', merged['commander']), s['media_id'])])
                     for s in merged['replacements']]
            digest = composition_hashes(original, spans)
            release = dict(sha256=digest, changed_entries=len(spans),
                           unchanged_entries=len(pack.entries)-len(spans), runtime_test='PENDING HUMAN IN-GAME TEST')
            path = mod.ROOT / 'data/releases' / (key + '.json')
            if count == 1:
                require(digest == group[0]['release']['sha256'], 'Singleton release hash differs')
            elif path.exists():
                known = json.loads(path.read_text(encoding='utf-8'))
                require(known['commanders'] == names and all(known['release'][field] == release[field]
                        for field in ('sha256','changed_entries','unchanged_entries')), 'Existing joint descriptor differs')
            else:
                descriptors.append((path, dict(commanders=names, release=release)))
            checked.append(dict(selection=names, sha256=digest, changed_entries=len(spans)))
            if len(checked) % 16 == 0:
                print(f'Metadata hashes {len(checked)}/{2**len(parts)-1}', flush=True)
    require(mod.sha256(base) == parts[0]['base']['sha256'], 'Canonical source changed during metadata preparation')
    for part in parts:
        for spec in part['replacements']:
            require(mod.sha256(mod.ROOT / part['replacement_directory'] / (spec['media_id'] + '.wem')) == spec['sha256'],
                    'Replacement changed during metadata preparation')
    for path, descriptor in descriptors:
        require(not path.exists(), 'Descriptor appeared during metadata preparation')
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(descriptor, indent=2) + '\n')
    result = dict(status='PASS', mode='METADATA_ONLY', states=len(checked), new_descriptors=len(descriptors),
                  module_validation=validation, independent_streaming_hash='PASS',
                  canonical_original_sha256=parts[0]['base']['sha256'], input_RSA='PASS',
                  physical_PACK_combinations_built=0, runtime_transitions_exercised=0, selections=checked)
    save(work / 'metadata-report.json', result)
    return {k:v for k,v in result.items() if k != 'selections'}


def run(base_path, work_path, commanders=None):
    parts = discover_all()
    if commanders:
        by_name = {p['commander']: p for p in parts}
        require(set(commanders) <= set(by_name) and len(set(commanders)) == len(commanders),
                'Unknown or duplicate production module')
        parts = [by_name[name] for name in sorted(commanders)]
    require(len(parts) >= 2, 'At least two production modules are required')
    key = '+'.join(sorted(p['commander'] for p in parts))
    work = Path(work_path).resolve()
    require(work.is_relative_to(mod.ROOT / 'work'), 'Joint PACK must remain under work/')
    base = Path(base_path).resolve(strict=True)
    require(not base.is_relative_to(mod.ROOT) and mod.sha256(base) == parts[0]['base']['sha256'],
            'Unknown canonical original')
    original = ArenaPack(base)
    count = len({s['media_id'] for p in parts for s in p['replacements']})
    release = {'sha256': '0' * 64, 'changed_entries': count,
               'unchanged_entries': len(original.entries) - count,
               'runtime_test': 'PENDING HUMAN IN-GAME TEST'}
    merged = merge_manifests(parts, release)
    require(count == len(merged['replacements']), 'Joint overlap changed replacement count')
    work.mkdir(parents=True, exist_ok=True)
    candidate = work / (key + '-offline-candidate.pack')
    require(not candidate.exists(), 'Joint candidate already exists')
    for part in parts:
        mod.validate_data(part)
    with base.open('rb') as src, candidate.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        for spec in merged['replacements']:
            payload = (mod.ROOT / 'replacements' / spec['source_commander'] /
                       'wem' / (spec['media_id'] + '.wem')).read_bytes()
            require(len(payload) == spec['size'] and hashlib.sha256(payload).hexdigest() == spec['sha256'],
                    'Joint payload changed')
            dst.seek(spec['offset'])
            require(dst.write(payload) == spec['size'], 'Short payload write')
        dst.flush()
        os.fsync(dst.fileno())
    require(mod.sha256(base) == parts[0]['base']['sha256'], 'Canonical original changed during joint build')
    modified = ArenaPack(candidate)
    require(modified.entries == original.entries and modified.file_size == original.file_size,
            'Joint entry order/offsets/size changed')
    for name in ('header', 'dependencies_raw', 'index_raw', 'appendix'):
        require(getattr(modified, name) == getattr(original, name), 'Protected PACK bytes changed')
    changed = set()
    with base.open('rb') as left, candidate.open('rb') as right:
        for entry in original.entries:
            left.seek(entry.offset)
            right.seek(entry.offset)
            if left.read(entry.size) != right.read(entry.size):
                changed.add(entry.path)
    require(changed == {s['path'] for s in merged['replacements']}, 'Unexpected joint changed entries')
    release['sha256'] = mod.sha256(candidate)
    descriptor = mod.ROOT / 'data/releases' / (key + '.json')
    require(not descriptor.exists(), 'Joint descriptor already exists')
    save(descriptor, {'commanders': key.split('+'), 'release': release})
    joint = selection(parts)
    mod.validate_data(joint)
    reproduction = work / (key + '-generic-reproduction.pack')
    result = mod.build(base, reproduction, joint)
    require(mod.sha256(reproduction) == release['sha256'] and
            filecmp.cmp(reproduction, candidate, shallow=False), 'Joint generic reproduction differs')
    return {'status': 'PASS', 'commanders': key.split('+'), 'changed_entries': count,
            'unchanged_entries': len(original.entries) - count, 'sha256': release['sha256'],
            'RSA': result['RSA'], 'generic_reproduction': 'BYTE_IDENTICAL'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--commanders', help='comma-separated module ids (commanders and shared modules); default is all')
    parser.add_argument('--metadata-only', action='store_true',
                        help='prepare selection hashes by independent canonical-byte compositions; no PACK builds or runtime matrix')
    args = parser.parse_args()
    if args.metadata_only:
        if args.commanders:
            parser.error('--metadata-only prepares all discovered modules; omit --commanders')
        print(json.dumps(create_descriptors(args.base, args.work), indent=2))
        return
    names = args.commanders.split(',') if args.commanders else None
    print(json.dumps(run(args.base, args.work, names), indent=2))


if __name__ == '__main__':
    main()
