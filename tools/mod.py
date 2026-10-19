"""Manifest-driven, offline Arena voice replacement builder (Python 3.11+)."""
import argparse
import csv
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from tools.pack.reader import ArenaPack, require
from tools.wem.fingerprint import fingerprint
from tools.resources import ROOT


@lru_cache(maxsize=1024)
def fingerprint_by_verified_hash(path, digest):
    # Caller checks the current file hash first, so a changed payload cannot
    # reuse an earlier structural inspection within this process.
    return fingerprint(path)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def load_manifest(commander='hannibal'):
    require(bool(re.fullmatch(r'[a-z][a-z0-9_-]*', commander)), 'Invalid commander name')
    folder = ROOT / 'data' / 'commanders' / commander
    value = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    require(value['schema_version'] == 1 and value['commander'] == commander, 'Unsupported manifest')
    require(value['runtime_slot'] == 'audio_cn.pack', 'Unsupported runtime slot')
    require(value['id'] == commander and value['spoken_count'] == value['expected_spoken_count']
            and value['replacement_count'] == value['expected_replacement_count']
            and value['supported_base_pack_hash'] == value['base']['sha256']
            and value['required_runtime_pack'] == value['runtime_slot']
            and value['replacement_directory'] == f'replacements/{commander}/wem', 'Installer metadata mismatch')
    return value


def validate_data(manifest):
    """Validate the allowlist against independent inventory, metadata and WEMs."""
    if 'components' in manifest:
        from tools.installer.catalog import merge_manifests
        parts = [load_manifest(name) for name in manifest['components']]
        results = [validate_data(part) for part in parts]
        require(merge_manifests(parts, manifest['release']) == manifest, 'Joint manifest mismatch')
        return {'status': 'PASS', 'components': results, 'replacement_wems': len(manifest['replacements'])}
    name = manifest['commander']
    folder = ROOT / 'data' / 'commanders' / name
    rows = csv_rows(folder / 'voice-lines.csv')
    inventory = csv_rows(folder / 'media-inventory.csv')
    by_id = {r['media_id']: r for r in inventory}
    require(len(by_id) == len(inventory), 'Duplicate inventory Media IDs')
    spoken = {r['media_id'] for r in inventory if r['scope'] == name.upper() + '_SPECIFIC'
              and r['silent_placeholder'] == 'NO' and r['safe_to_replace_for_' + name] == 'YES'}
    silent = {r['media_id'] for r in inventory if r['scope'] == name.upper() + '_SPECIFIC'
              and r['silent_placeholder'] == 'YES'}
    specs = manifest['replacements']
    ids = {r['media_id'] for r in specs}
    require(len(ids) == len(specs) == manifest['expected_replacement_count'], 'Replacement count/duplicates')
    require(len(rows) == len({r['media_id'] for r in rows}) == manifest['expected_spoken_count'], 'Metadata count/duplicates')
    require(ids == {r['media_id'] for r in rows} == spoken, 'Replacement/spoken allowlist mismatch')
    require(silent == set(manifest['silent_placeholder_ids']) and not ids & silent, 'Silent IDs mismatch')
    require(manifest['release']['changed_entries'] == len(ids), 'Invalid release changed count')
    require(manifest['release']['unchanged_entries'] + len(ids) == manifest['base']['entry_count'], 'Invalid release unchanged count')
    wem_dir = ROOT / 'replacements' / name / 'wem'
    require({p.name for p in wem_dir.iterdir()} == {mid + '.wem' for mid in ids}, 'Unexpected/missing replacement files')
    metadata = {r['media_id']: r for r in rows}
    for spec in specs:
        mid = spec['media_id']
        require(mid.isdecimal() and spec['path'] == f'audio/wwise/{mid}.wem', 'Invalid Media ID/path')
        original = by_id[mid]
        require(original['scope'] == name.upper() + '_SPECIFIC' and original['silent_placeholder'] == 'NO'
                and original['safe_to_replace_for_' + name] == 'YES', 'Shared/silent/unsafe replacement')
        require(int(metadata[mid]['original_size_bytes']) == int(original['original_size_bytes']) == spec['size'], 'Original size mismatch')
        require(original['wem_sha256'] == spec['original_sha256'], 'Original inventory hash mismatch')
        path = wem_dir / (mid + '.wem')
        digest = sha256(path)
        require(path.stat().st_size == spec['size'] and digest == spec['sha256'] == metadata[mid]['wem_sha256'], 'Replacement hash/size mismatch: ' + mid)
        fp = fingerprint_by_verified_hash(str(path), digest)
        expected = manifest['wem_format']
        require(fp['container'] == 'RIFF' and fp['fmt_chunk_size'] == expected['fmt_chunk_size'], 'WEM container mismatch')
        require(all(fp['fmt'][key] == expected[key] for key in ('sample_rate', 'channels', 'block_sizes', 'subtype_channel_config')), 'WEM format mismatch: ' + mid)
        require(fp['packets']['mod_packets'] and fp['setup']['stripped_setup']
                and fp['setup']['codebook_reference_bits'] == 10, 'WEM packet/setup mismatch')
    return {'status': 'PASS', 'commander': name, 'replacement_wems': len(specs), 'metadata_rows': len(rows),
            'silent_placeholders': len(silent), 'shared_replacements': 0, 'fingerprints': 'PASS'}


def check_structure(pack, manifest):
    base = manifest['base']
    require(pack.file_size == base['size'] and len(pack.entries) == base['entry_count'], 'PACK size/count mismatch')
    require(pack.flags == base['flags'], 'PACK flags mismatch')
    for key, data in [('header', pack.header), ('dependencies', pack.dependencies_raw),
                      ('encrypted_index', pack.index_raw), ('appendix', pack.appendix)]:
        require(hashlib.sha256(data).hexdigest() == base[key + '_sha256'], key + ' changed')
    for spec in manifest['replacements']:
        entry = pack.find(spec['path'])
        require(entry.offset == spec['offset'] and entry.size == spec['size'], 'PACK offset/size mismatch')


def verify_pack(path, manifest, base_path=None):
    path = Path(path).resolve(strict=True)
    digest = sha256(path)
    kind = 'original' if digest == manifest['base']['sha256'] else 'modified' if digest == manifest['release']['sha256'] else 'unsupported'
    require(kind != 'unsupported', 'Unsupported PACK SHA-256: ' + digest)
    pack = ArenaPack(path)  # mandatory RSA verification
    check_structure(pack, manifest)
    with path.open('rb') as stream:
        for spec in manifest['replacements']:
            stream.seek(spec['offset'])
            payload = stream.read(spec['size'])
            expected = spec['original_sha256'] if kind == 'original' else spec['sha256']
            require(hashlib.sha256(payload).hexdigest() == expected, 'PACK WEM hash mismatch')
    result = {'status': 'PASS', 'kind': kind, 'sha256': digest, 'size': pack.file_size,
              'RSA': 'PASS', 'entry_count': len(pack.entries), 'header': 'PASS', 'dependencies': 'PASS',
              'encrypted_index': 'PASS', 'offsets': 'PASS', 'appendix': 'PASS',
              'replacement_hashes': 'PASS', 'expected_replacements': len(manifest['replacements']),
              'changed_entries': 0 if kind == 'original' else manifest['release']['changed_entries'],
              'unchanged_entries': len(pack.entries) if kind == 'original' else manifest['release']['unchanged_entries'],
              'counts_basis': 'known complete PACK SHA-256 and replacement hashes'}
    if base_path is not None:
        base_path = Path(base_path).resolve(strict=True)
        require(sha256(base_path) == manifest['base']['sha256'], 'Unsupported original SHA-256')
        original = ArenaPack(base_path)
        check_structure(original, manifest)
        require(original.entries == pack.entries, 'Entry ordering/offsets changed')
        allowed = {s['path'] for s in manifest['replacements']} if kind == 'modified' else set()
        changed = set()
        with base_path.open('rb') as left, path.open('rb') as right:
            # Entries cover the complete payload area; metadata was checked above.
            for entry in original.entries:
                left.seek(entry.offset)
                right.seek(entry.offset)
                if left.read(entry.size) != right.read(entry.size):
                    changed.add(entry.path)
        require(changed == allowed, 'Unexpected changed payload set')
        result.update(changed_entries=len(changed), unchanged_entries=len(pack.entries) - len(changed),
                      counts_basis='full byte comparison of every entry against canonical original',
                      diff_outside_allowed_payloads=0)
    return result


def build(base_path, output_path, manifest):
    base_path = Path(base_path).resolve(strict=True)
    output = Path(output_path).resolve()
    require(output != base_path and not output.exists(), 'Output exists or aliases original')
    require(sha256(base_path) == manifest['base']['sha256'], 'Unsupported original SHA-256; refusing to patch')
    data = validate_data(manifest)
    original = ArenaPack(base_path)
    check_structure(original, manifest)
    partial = output.with_name(output.name + '.partial')
    require(not partial.exists(), 'Partial output already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    owned = False
    try:
        with base_path.open('rb') as source, partial.open('xb') as dest:
            owned = True
            shutil.copyfileobj(source, dest, 1024 * 1024)
            for spec in manifest['replacements']:
                owner = spec.get('source_commander', manifest['commander'])
                payload = (ROOT / 'replacements' / owner / 'wem' / (spec['media_id'] + '.wem')).read_bytes()
                require(len(payload) == spec['size'] and hashlib.sha256(payload).hexdigest() == spec['sha256'], 'Replacement changed during build')
                dest.seek(spec['offset'])
                require(dest.write(payload) == spec['size'], 'Short payload write')
            dest.flush()
            os.fsync(dest.fileno())
        require(sha256(base_path) == manifest['base']['sha256'], 'Original changed during build')
        result = verify_pack(partial, manifest, base_path)
        # Atomic publication that fails if the output was created concurrently.
        os.link(partial, output)
        result.update(data=data, matches_known_release=result['sha256'] == manifest['release']['sha256'])
        return result
    finally:
        if owned:
            partial.unlink(missing_ok=True)


def _without_owner(spec):
    return {k: v for k, v in spec.items() if k != 'source_commander'}


def build_additive(base_path, output_path, base_manifest, manifest):
    """Install-time only: add missing payloads to a verified known modified PACK.

    Used when no canonical original is available locally. The output must hash
    to the target's independently validated whole-PACK SHA-256, so it is
    byte-identical to the canonical-original build; releases still use build().
    """
    base_path = Path(base_path).resolve(strict=True)
    output = Path(output_path).resolve()
    require(output != base_path and not output.exists(), 'Output exists or aliases current PACK')
    digest = base_manifest['release']['sha256']
    require(sha256(base_path) == digest, 'Current PACK is not the verified installed state; refusing to patch')
    require(base_manifest['base'] == manifest['base'], 'Incompatible canonical bases')
    current = {s['media_id']: _without_owner(s) for s in base_manifest['replacements']}
    target = {s['media_id']: s for s in manifest['replacements']}
    require(all(mid in target and _without_owner(target[mid]) == spec for mid, spec in current.items()),
            'Installed dubbing is not a subset of the target selection')
    added = [target[mid] for mid in sorted(target, key=int) if mid not in current]
    require(bool(added), 'Target adds no replacement payloads')
    data = validate_data(manifest)
    installed = ArenaPack(base_path)  # mandatory RSA verification
    check_structure(installed, manifest)
    partial = output.with_name(output.name + '.partial')
    require(not partial.exists(), 'Partial output already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    owned = False
    try:
        with base_path.open('rb') as source, partial.open('xb') as dest:
            owned = True
            shutil.copyfileobj(source, dest, 1024 * 1024)
            for spec in added:
                owner = spec.get('source_commander', manifest['commander'])
                payload = (ROOT / 'replacements' / owner / 'wem' / (spec['media_id'] + '.wem')).read_bytes()
                require(len(payload) == spec['size'] and hashlib.sha256(payload).hexdigest() == spec['sha256'], 'Replacement changed during build')
                dest.seek(spec['offset'])
                require(dest.write(payload) == spec['size'], 'Short payload write')
            dest.flush()
            os.fsync(dest.fileno())
        require(sha256(base_path) == digest, 'Current PACK changed during build')
        # Known validated whole-PACK hash, RSA, structure and every target payload hash.
        result = verify_pack(partial, manifest)
        modified = ArenaPack(partial)
        require(modified.entries == installed.entries, 'Entry ordering/offsets changed')
        changed = set()
        with base_path.open('rb') as left, partial.open('rb') as right:
            for entry in installed.entries:
                left.seek(entry.offset)
                right.seek(entry.offset)
                if left.read(entry.size) != right.read(entry.size):
                    changed.add(entry.path)
        require(changed == {s['path'] for s in added}, 'Unexpected changed payload set')
        os.link(partial, output)
        result.update(data=data, mode='ADDITIVE', base_sha256=digest, added_entries=len(added),
                      diff_outside_added_payloads=0, matches_known_release=True,
                      counts_basis='known validated whole-PACK SHA-256; full entry diff against verified installed state')
        return result
    finally:
        if owned:
            partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commander', default='hannibal')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate')
    build_parser = commands.add_parser('build')
    build_parser.add_argument('--base', required=True)
    build_parser.add_argument('--output', required=True)
    build_parser.add_argument('--report')
    verify_parser = commands.add_parser('verify')
    verify_parser.add_argument('--pack', required=True)
    verify_parser.add_argument('--base', help='Optional canonical original for full entry byte diff')
    args = parser.parse_args()
    try:
        require(bool(re.fullmatch(r'[a-z][a-z0-9_-]*', args.commander)), 'Invalid commander name')
        research = ROOT / 'data' / 'commanders' / args.commander / 'research'
        production = research.parent / 'manifest.json'
        if args.command == 'validate' and not production.exists() and (research / 'manifest-draft.json').exists():
            from tools.inventory.research_metadata import validate_research
            result = validate_research(research, args.commander)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        manifest = load_manifest(args.commander)
        if args.command == 'build':
            if args.report:
                require(not Path(args.report).exists(), 'Report already exists')
            result = build(args.base, args.output, manifest)
            if args.report:
                with Path(args.report).open('x', encoding='utf-8') as stream:
                    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        else:
            result = validate_data(manifest)
            if args.command == 'verify':
                result = verify_pack(args.pack, manifest, args.base) | {'data': result}
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, AssertionError, IndexError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
