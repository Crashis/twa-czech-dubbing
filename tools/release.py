"""Fail-closed Windows release build; private originals are read-only inputs."""
import argparse
from importlib.metadata import distribution, version
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

from itertools import combinations

from tools import mod
from tools.installer.catalog import discover_all, selection
from tools.pack.reader import require
from tools.resources import VERSION
from tools.validation.repository import audit, private_values, SECRET_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
EXE = 'TWA-Czech-Dubbing-Installer.exe'
NAME = f'TWA-Czech-Dubbing-v{VERSION}-win64'
EPOCH = '1792627200'
DATE = (2026, 10, 22, 0, 0, 0)
# Evidence record, not a selection rule: commanders whose payloads the user reported as tested in game.
USER_REPORTED_RUNTIME = ('hannibal', 'spartacus', 'zhuge-liang')


def checked(args, env=None):
    # Windows PowerShell 5 treats redirected native stderr as an ErrorRecord.
    # Test/build progress is normal output; merge it before returning to PowerShell.
    subprocess.run([str(a) for a in args], cwd=ROOT, env=env, check=True, stderr=subprocess.STDOUT)


def file_list(folder):
    return sorted(p for p in folder.rglob('*') if p.is_file())


def deterministic_zip(folder, output):
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in file_list(folder):
            info = zipfile.ZipInfo(folder.name + '/' + path.relative_to(folder).as_posix(), DATE)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def scan_bytes(raw, label):
    require(not any(value in raw for value in private_values(ROOT)) and
            not any(re.search(pattern, raw) for pattern in SECRET_PATTERNS), 'Secret scan failed in ' + label)
    require(not re.search(rb'(?i)[a-z]:[\\/]+Users[\\/]+[^\\/\s]+', raw), 'Personal path found in ' + label)


def audit_executable(path):
    # Scan decompressed embedded code/data too, not just the outer compressed PE.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(path))
    require('PYZ.pyz' in archive.toc, 'Missing embedded Python archive')
    for name, entry in archive.toc.items():
        if entry[-1] == 'z':
            pyz = archive.open_embedded_archive(name)
            for module in pyz.toc:
                scan_bytes(pyz.extract(module, raw=True) or b'', 'embedded module ' + module)
                require(not module.startswith(('tests.', 'tools.tts.', 'tools.release', 'tools.validation.')),
                        'Development-only module in executable: ' + module)
        elif entry[-1] not in ('o',):
            scan_bytes(archive.extract(name), 'embedded file ' + name)
            require(not name.lower().endswith(('.pack', '.orig', '.wem', '.bnk', '.wav', '.mp3', '.ogg')),
                    'Unexpected embedded game/audio asset')


def add_notices(bundle):
    (bundle / 'THIRD_PARTY_NOTICES.txt').write_text(
        'Third-party notices for TWA Czech Dubbing ' + VERSION + '\n\n'
        'The installer EXE bundles CPython and Tcl/Tk using PyInstaller 6.22.3.\n'
        'Their complete license texts are included beside this notice:\n'
        '  licenses/Python.txt\n'
        '  licenses/Tcl.txt\n'
        '  licenses/Tk.txt\n'
        '  licenses/PyInstaller.txt\n\n'
        'PyInstaller is GPL-2.0-or-later with a bootloader distribution exception.\n'
        'See licenses/PyInstaller.txt and https://pyinstaller.org/en/stable/license.html.\n\n'
        'PACK format research used RPFM by Ismael Gutiérrez González and contributors.\n'
        'Its MIT notice is retained in licenses/RPFM-MIT.txt.\n\n'
        'Development-only audio tools and original game assets are not bundled.\n',
        encoding='utf-8')
    folder = bundle / 'licenses'
    folder.mkdir()
    sources = {'RPFM-MIT.txt': ROOT / 'third_party/RPFM-MIT.txt',
               'Python.txt': Path(sys.base_prefix) / 'LICENSE.txt',
               'Tcl.txt': ROOT / 'third_party/Tcl-8.6.15.txt',
               'Tk.txt': Path(sys.base_prefix) / 'tcl/tk8.6/license.terms'}
    dist = distribution('pyinstaller')
    sources['PyInstaller.txt'] = dist.locate_file(next(p for p in dist.files if str(p).endswith('licenses/COPYING.txt')))
    for name, source in sources.items():
        require(source.is_file(), 'Missing required runtime license: ' + name)
        shutil.copyfile(source, folder / name)


def joint_keys(manifests):
    names = sorted(m['commander'] for m in manifests)
    return ['+'.join(group) for count in range(2, len(names) + 1) for group in combinations(names, count)]


def payload_files(manifests):
    files = [Path('data/arena-index-public-key.json')]
    # Every selectable combination ships its own independently validated whole-PACK descriptor.
    files += [Path('data/releases') / (key + '.json') for key in joint_keys(manifests)]
    for m in manifests:
        folder = Path('data') / (mod.SHARED if mod.is_shared(m) else 'commanders') / m['commander']
        files += [folder / n for n in ('manifest.json', 'voice-lines.csv', 'media-inventory.csv')]
        files += [Path(m['replacement_directory']) / (s['media_id'] + '.wem') for s in m['replacements']]
    return sorted(set(files))


def bundle_audit(bundle, manifests):
    expected_payload = set(payload_files(manifests))
    actual_payload = {p.relative_to(bundle / 'payload') for p in file_list(bundle / 'payload')}
    require(actual_payload == expected_payload, 'Unexpected/missing release payload file')
    expected_top = {EXE, 'README.txt', 'THIRD_PARTY_NOTICES.txt', 'SHA256SUMS.txt'}
    allowed_licenses = {'Python.txt', 'Tcl.txt', 'Tk.txt', 'PyInstaller.txt', 'RPFM-MIT.txt'}
    require({p.name for p in bundle.iterdir() if p.is_file()} == expected_top,
            'Missing/unexpected top-level release file')
    require({p.name for p in (bundle / 'licenses').iterdir() if p.is_file()} == allowed_licenses,
            'Missing/unexpected runtime license text')
    sums = {}
    for line in (bundle / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        require(name not in sums, 'Duplicate release checksum')
        sums[name] = digest
    actual = {p.relative_to(bundle).as_posix() for p in file_list(bundle)}
    require(set(sums) == actual - {'SHA256SUMS.txt'}, 'Release checksum coverage mismatch')
    for path in file_list(bundle):
        rel = path.relative_to(bundle)
        allowed = (len(rel.parts) == 1 and rel.name in expected_top or
                   rel.parts[0] == 'payload' and Path(*rel.parts[1:]) in expected_payload or
                   len(rel.parts) == 2 and rel.parts[0] == 'licenses' and rel.name in allowed_licenses)
        require(allowed, 'Unexpected release file: ' + rel.as_posix())
        raw = path.read_bytes()
        scan_bytes(raw, rel.as_posix())
        if rel.as_posix() != 'SHA256SUMS.txt':
            require(sums[rel.as_posix()] == mod.sha256(path), 'Release checksum mismatch')
    for rel in expected_payload:
        require(mod.sha256(bundle / 'payload' / rel) == mod.sha256(ROOT / rel), 'Payload differs from source')
    audit_executable(bundle / EXE)
    return {'replacement_wem_count': sum(1 for p in expected_payload if p.suffix == '.wem'),
            'original_game_files_included': 0, 'secrets_included': 0,
            'secret_scan': 'SECRET SCAN PASS', 'payload_allowlist': 'PASS', 'checksums': 'PASS',
            'embedded_archive_scan': 'PASS', 'license_texts': sorted(allowed_licenses),
            'license_audit': 'PASS'}


def release_manifests():
    """Manifest-driven: every discovered production commander and shared module ships, and every
    combination of them needs its own independently validated descriptor (selection() fails closed)."""
    manifests = discover_all()
    require(bool(manifests), 'No production commander manifests found')
    require(all(m['version'] == VERSION for m in manifests),
            'Commander release version metadata does not match final version')
    require(all(m['base'] == manifests[0]['base'] for m in manifests), 'Production commanders use different bases')
    require({p.stem for p in (mod.ROOT / 'data/releases').glob('*.json')} == set(joint_keys(manifests)),
            'Joint descriptors do not match the production commander combinations')
    by_name = {m['commander']: m for m in manifests}
    return manifests, [selection([by_name[name] for name in key.split('+')]) for key in joint_keys(manifests)]


def readme_text(manifests):
    commanders = [m for m in manifests if not mod.is_shared(m)]
    shared = [m for m in manifests if mod.is_shared(m)]
    return ('Total War: Arena - Czech Dubbing ' + VERSION + '\n\n'
            'Commanders: ' + ', '.join(f"{m['display_name']} ({m['replacement_count']} lines)"
                                       for m in commanders) + '.\n'
            + ''.join(f"Optional shared module: {m['display_name']} - {m['description']} ({m['replacement_count']} lines; "
                      'male and female unit voices together, with any commander selection or alone).\n'
                      for m in shared) + '\n'
            '1. Extract the entire ZIP.\n2. Run TWA-Czech-Dubbing-Installer.exe.\n'
            '3. Choose the Total War: Arena folder; checkboxes show verified installed dubbing.\n'
            '4. Select any combination of available commanders and optional shared modules.\n'
            '   Close the game and launcher; click Install.\n'
            '5. Launch the game yourself.\n\n'
            'Checkboxes only change the pending selection. Only Install applies it.\n'
            'Verify checks installed audio and resets the selection to the actual state.\n'
            'Unchecking every commander does not restore audio; use Restore Original.\n'
            'Restore Original restores the verified backup and clears the selection.\n'
            'A verified backup of the clean original is created automatically before the first write,\n'
            'from the current audio_cn.pack or a byte-identical data\\audio_en.pack (read only).\n'
            'Without any original source you can still add dubbing; removing dubbing and\n'
            'Restore Original then stay disabled and no game file is changed.\n'
            'Backups: %LOCALAPPDATA%\\TWA-Czech-Dubbing\\backup\\<installation-id>\\audio_cn.pack\n'
            'Logs: %LOCALAPPDATA%\\TWA-Czech-Dubbing\\logs\\\n'
            'Unsupported versions are rejected without modifying game audio.\n'
            'If write access is denied, close the installer and use Run as administrator on the EXE.\n'
            'Use the same Windows account so its backup remains available.\n'
            'Requires Windows x64 and your own supported game; no Python/Git/API key needed.\n'
            'Keep at least 750 MB free (backup, build, Python extraction).\n')


def build_fast_release(base_pack, output_directory=None):
    """One frozen build and one ZIP, audited with a single full-selection mock PACK build.

    Module validation plus fail-closed selection descriptors cover the payload catalog.
    Targeted installer tests are run separately; no transition matrix or historical suite.
    """
    require(os.name == 'nt' and struct.calcsize('P') == 8, 'Build requires 64-bit Windows Python')
    require(version('pyinstaller') == '6.22.3', 'Install pinned requirements-development.txt in .venv')
    manifests, joints = release_manifests()
    base = Path(base_pack).resolve(strict=True)
    require(not base.is_relative_to(ROOT) and mod.sha256(base) == manifests[0]['base']['sha256'],
            'Unsupported canonical original')
    validated = {m['commander']: mod.validate_data(m)['status'] for m in manifests}
    repository = audit()
    require(repository['secret_scan'] == 'SECRET SCAN PASS' and not repository['prohibited_asset_files'],
            'Repository secret/asset audit failed')
    output = Path(output_directory).resolve() if output_directory else ROOT / 'work/fast-release'
    require(output.is_relative_to(ROOT / 'work'), 'FAST build outputs must stay under ignored work/')
    output.mkdir(parents=True, exist_ok=True)
    final, zipped, report_path = output / NAME, output / (NAME + '.zip'), output / (NAME + '-fast-build-report.json')
    require(not any(p.exists() for p in (final, zipped, report_path)), 'FAST release output already exists')
    env = os.environ.copy()
    env.update(PYTHONHASHSEED='0', SOURCE_DATE_EPOCH=EPOCH, PYTHONDONTWRITEBYTECODE='1')
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fast-release-', dir=ROOT / 'build') as temporary:
        temp = Path(temporary)
        checked([sys.executable, '-B', '-m', 'PyInstaller', '--noconfirm', '--clean',
                 '--distpath', temp / 'dist', '--workpath', temp / 'work', ROOT / 'scripts/installer.spec'], env)
        bundle = temp / NAME
        bundle.mkdir()
        shutil.copyfile(temp / 'dist' / EXE, bundle / EXE)
        for rel in payload_files(manifests):
            target = bundle / 'payload' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        (bundle / 'README.txt').write_text(readme_text(manifests), encoding='utf-8')
        add_notices(bundle)
        sums = ''.join(mod.sha256(p) + '  ' + p.relative_to(bundle).as_posix() + '\n' for p in file_list(bundle))
        (bundle / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8', newline='\n')
        package_audit = bundle_audit(bundle, manifests)
        archive = temp / 'release.zip'
        deterministic_zip(bundle, archive)
        extracted = temp / 'extracted folder with spaces'
        with zipfile.ZipFile(archive) as stream:
            require(stream.testzip() is None, 'ZIP CRC failed')
            stream.extractall(extracted)
        bundle_audit(extracted / NAME, manifests)
        integration = mod.build(base, temp / 'all-modules.pack', selection(manifests))
        require(integration['matches_known_release'] and integration['RSA'] == 'PASS', 'Full selection differs')
        exe_sha = mod.sha256(bundle / EXE)
        exe_size = (bundle / EXE).stat().st_size
        shutil.copytree(bundle, final)
        shutil.copyfile(archive, zipped)
    report = dict(status='PASS', build_type='FAST', version=VERSION, release_name=NAME,
                  zip_path=zipped.relative_to(ROOT).as_posix(), zip_size=zipped.stat().st_size,
                  zip_sha256=mod.sha256(zipped), installer_path=(final / EXE).relative_to(ROOT).as_posix(),
                  installer_size=exe_size, installer_sha256=exe_sha, modules=validated,
                  joint_descriptors=len(joints), catalog_states=len(manifests)+len(joints),
                  bundle_audit=package_audit, extracted_zip_audit='PASS', secret_scan=repository['secret_scan'],
                  integration={k:integration[k] for k in ('sha256','RSA','changed_entries','unchanged_entries',
                                                         'diff_outside_allowed_payloads','encrypted_index','appendix')},
                  python=sys.version.split()[0], pyinstaller=version('pyinstaller'),
                  SOURCE_DATE_EPOCH=EPOCH, PYTHONHASHSEED='0',
                  skipped=['full transition matrix','full historical/release suite','all combination PACK rebuilds',
                           'second EXE build/reproducibility','second ZIP reproducibility','frozen GUI smoke'],
                  game_runtime_test='NOT_PERFORMED', human_listening_of_final_WEMs='NOT_PERFORMED')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report


def build_release(base_pack, reference_pack=None, output_directory=None):
    require(os.name == 'nt' and struct.calcsize('P') == 8, 'Build requires 64-bit Windows Python')
    require(version('pyinstaller') == '6.22.3', 'Install pinned requirements-development.txt in .venv')
    manifests, joints = release_manifests()
    base = Path(base_pack).resolve(strict=True)
    require(mod.sha256(base) == manifests[0]['base']['sha256'], 'Unsupported canonical original')
    require(not base.is_relative_to(ROOT), 'Canonical original must remain outside the repository')
    reference = Path(reference_pack).resolve(strict=True) if reference_pack else None
    if reference:
        require(mod.sha256(reference) == manifests[0]['release']['sha256'], 'Reference Complete PACK hash mismatch')
    output = Path(output_directory).resolve() if output_directory else ROOT / 'release'
    output.mkdir(parents=True, exist_ok=True)
    final = output / NAME
    zipped = output / (NAME + '.zip')
    report_path = output / (NAME + '-build-report.json')
    require(not any(p.exists() for p in (final, zipped, report_path)), 'Release output already exists; select a new output directory')
    env = os.environ.copy()
    env.update(PYTHONHASHSEED='0', SOURCE_DATE_EPOCH=EPOCH, PYTHONDONTWRITEBYTECODE='1', TWA_TEST_BASE_PACK=str(base))
    checked([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], env)
    for manifest in manifests:
        checked([sys.executable, '-B', '-m', 'tools.mod', '--commander', manifest['commander'], 'validate'], env)
    checked([sys.executable, '-B', '-m', 'tools.validation.repository'], env)
    repository = audit()
    for m in [*manifests, *joints]:
        mod.validate_data(m)
    build_root = ROOT / 'build'
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-', dir=build_root) as temporary:
        temp = Path(temporary)
        hashes = []
        for label in ('first', 'second'):
            checked([sys.executable, '-B', '-m', 'PyInstaller', '--noconfirm', '--clean',
                     '--distpath', temp / label / 'dist', '--workpath', temp / label / 'work',
                     ROOT / 'scripts/installer.spec'], env)
            hashes.append(mod.sha256(temp / label / 'dist' / EXE))
        require(hashes[0] == hashes[1], 'Standalone EXE reproduction failed')
        bundle = temp / NAME
        bundle.mkdir()
        shutil.copyfile(temp / 'first/dist' / EXE, bundle / EXE)
        for rel in payload_files(manifests):
            target = bundle / 'payload' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        (bundle / 'README.txt').write_text(readme_text(manifests), encoding='utf-8')
        add_notices(bundle)
        sums = ''.join(mod.sha256(p) + '  ' + p.relative_to(bundle).as_posix() + '\n' for p in file_list(bundle))
        (bundle / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8', newline='\n')
        release_audit = bundle_audit(bundle, manifests)
        integration = {}
        for manifest in [*manifests, *joints]:
            label = '+'.join(manifest.get('components', [manifest['commander']]))
            candidate = temp / (label + '-reproduced.pack')
            integration[label] = mod.build(base, candidate, manifest)
            require(integration[label]['matches_known_release'] and integration[label]['RSA'] == 'PASS',
                    'Reproduced PACK differs from its validated release hash: ' + label)
            if label == manifests[0]['commander'] and reference:
                with candidate.open('rb') as left, reference.open('rb') as right:
                    while True:
                        block = left.read(1024 * 1024)
                        require(block == right.read(1024 * 1024), 'Complete reference differs byte for byte')
                        if not block:
                            break
                integration[label]['byte_identical_to_complete_reference'] = True
            candidate.unlink()  # keep at most one temporary full PACK on disk
        archive_a = temp / 'first.zip'
        archive_b = temp / 'second.zip'
        deterministic_zip(bundle, archive_a)
        deterministic_zip(bundle, archive_b)
        require(mod.sha256(archive_a) == mod.sha256(archive_b), 'ZIP reproduction failed')
        # Test what an end user extracts, including the checksums and exact payload allowlist.
        extracted = temp / 'arbitrary extracted folder with spaces'
        with zipfile.ZipFile(archive_a) as archive:
            require(archive.testzip() is None, 'ZIP CRC failed')
            archive.extractall(extracted)
        extracted_bundle = extracted / NAME
        bundle_audit(extracted_bundle, manifests)
        require(not (extracted_bundle / 'Install.bat').exists(), 'BAT launcher unexpectedly included')
        # Run the extracted EXE directly, with no BAT, from an unrelated working directory.
        # The frozen GUI/backend uses only a disposable mock game during this smoke test.
        foreign_cwd = temp / 'unrelated working directory'
        foreign_cwd.mkdir()
        smoke_report = temp / 'frozen-smoke.json'
        process = subprocess.run([str(extracted_bundle / EXE), '--self-test', str(base), str(smoke_report)],
                                 cwd=foreign_cwd, env=env, timeout=3600)
        require(smoke_report.is_file(), 'Frozen installer did not create its smoke report')
        smoke = json.loads(smoke_report.read_text(encoding='utf-8'))
        require(process.returncode == 0 and smoke['status'] == 'PASS',
                'Frozen installer smoke test failed: ' + smoke.get('error', 'unknown error'))
        smoke.update(standalone_exe_without_bat='PASS', payload_relative_to_exe='PASS',
                     extracted_path_with_spaces='PASS', unrelated_working_directory='PASS')
        report = {'status': 'PASS', 'release_name': NAME, 'version': VERSION,
                  'zip_path': zipped.relative_to(ROOT).as_posix() if zipped.is_relative_to(ROOT) else zipped.name,
                  'zip_size': archive_a.stat().st_size, 'zip_sha256': mod.sha256(archive_a),
                  'installer_size': (bundle / EXE).stat().st_size, 'installer_sha256': hashes[0],
                  'EXE_rebuilt_twice_identically': True, 'ZIP_repacked_twice_identically': True,
                  'python': sys.version.split()[0], 'pyinstaller': version('pyinstaller'),
                  'build_dependencies': {n: version(n) for n in ('pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools')},
                  'SOURCE_DATE_EPOCH': EPOCH, 'PYTHONHASHSEED': '0', 'repository': repository,
                  'commanders': {m['commander']: {'display_name': m['display_name'],
                                                  'display_order': m['display_order'],
                                                  'replacements': len(m['replacements']),
                                                  'release_sha256': m['release']['sha256']} for m in manifests},
                  'validated_combinations': len(integration),
                  'release_audit': release_audit, 'integration': integration, 'frozen_smoke': smoke,
                  'human_listening': {m['commander']: 'USER_REPORTED_IN_GAME' if m['commander'] in USER_REPORTED_RUNTIME
                                      else 'PENDING_HUMAN_IN_GAME_TEST' for m in manifests},
                  'game_runtime_test': 'NOT_PERFORMED_FOR_THIS_BUILD',
                  'historical_payload_runtime': 'USER_REPORTED_PASS: ' + ', '.join(
                      m['display_name'] for m in manifests if m['commander'] in USER_REPORTED_RUNTIME),
                  'installer_human_review': 'NOT_PERFORMED_FOR_THIS_BUILD'}
        # Only publish artifacts after every gate succeeds. No original PACK enters the bundle.
        shutil.copytree(bundle, final)
        shutil.copyfile(archive_a, zipped)
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'release_name', 'zip_path', 'zip_size', 'zip_sha256', 'installer_size', 'installer_sha256')}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-pack', required=True)
    parser.add_argument('--reference-pack')
    parser.add_argument('--output-directory')
    parser.add_argument('--fast', action='store_true', help='one EXE/ZIP; targeted checks only, no exhaustive suite')
    args = parser.parse_args()
    try:
        if args.fast:
            require(not args.reference_pack, '--fast does not use a historical reference PACK')
            build_fast_release(args.base_pack, args.output_directory)
        else:
            build_release(args.base_pack, args.reference_pack, args.output_directory)
        return 0
    except Exception as error:
        print('RELEASE BUILD FAIL: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
