"""Create a validated joint descriptor from a canonical original, offline only."""
import argparse
import filecmp
import hashlib
import json
import os
from pathlib import Path
import shutil

from tools import mod
from tools.installer.catalog import discover, merge_manifests, selection
from tools.pack.reader import ArenaPack, require
from tools.wem.production import save


def run(base_path, work_path):
    parts = discover()
    require(len(parts) >= 2, 'At least two production commanders are required')
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
    args = parser.parse_args()
    print(json.dumps(run(args.base, args.work), indent=2))


if __name__ == '__main__':
    main()
