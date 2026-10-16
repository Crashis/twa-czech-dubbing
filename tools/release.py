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

from tools import mod
from tools.installer.catalog import discover
from tools.pack.reader import require
from tools.resources import VERSION
from tools.validation.repository import audit, private_values, SECRET_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
EXE = 'TWA-Czech-Dubbing-Installer.exe'
NAME = f'TWA-Czech-Dubbing-Hannibal-v{VERSION}-win64'
EPOCH = '1792108800'
DATE = (2026, 10, 16, 0, 0, 0)


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
        (ROOT / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8') +
        '\nRuntime license texts are in licenses/. Development audio tools are not bundled.\n', encoding='utf-8')
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


def payload_files(manifests):
    files = [Path('data/arena-index-public-key.json')]
    for m in manifests:
        folder = Path('data/commanders') / m['commander']
        files += [folder / n for n in ('manifest.json', 'voice-lines.csv', 'media-inventory.csv')]
        files += [Path(m['replacement_directory']) / (s['media_id'] + '.wem') for s in m['replacements']]
    return sorted(set(files))


def bundle_audit(bundle, manifests):
    expected_payload = set(payload_files(manifests))
    actual_payload = {p.relative_to(bundle / 'payload') for p in file_list(bundle / 'payload')}
    require(actual_payload == expected_payload, 'Unexpected/missing release payload file')
    expected_top = {'Install.bat', EXE, 'README.txt', 'THIRD_PARTY_NOTICES.txt', 'SHA256SUMS.txt'}
    allowed_licenses = {'Python.txt', 'Tcl.txt', 'Tk.txt', 'PyInstaller.txt', 'RPFM-MIT.txt'}
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
            'embedded_archive_scan': 'PASS'}


def build_release(base_pack, reference_pack=None, output_directory=None):
    require(os.name == 'nt' and struct.calcsize('P') == 8, 'Build requires 64-bit Windows Python')
    require(version('pyinstaller') == '6.22.3', 'Install pinned requirements-development.txt in .venv')
    manifests = discover()
    require([m['commander'] for m in manifests] == ['hannibal'], 'Review release naming and joint tests before adding commanders')
    manifest = manifests[0]
    base = Path(base_pack).resolve(strict=True)
    require(mod.sha256(base) == manifest['base']['sha256'], 'Unsupported canonical original')
    require(not base.is_relative_to(ROOT), 'Canonical original must remain outside the repository')
    reference = Path(reference_pack).resolve(strict=True) if reference_pack else None
    if reference:
        require(mod.sha256(reference) == manifest['release']['sha256'], 'Reference Complete PACK hash mismatch')
    output = Path(output_directory).resolve() if output_directory else ROOT / 'release'
    output.mkdir(parents=True, exist_ok=True)
    final = output / NAME
    zipped = output / (NAME + '.zip')
    report_path = output / (NAME + '-build-report.json')
    require(not any(p.exists() for p in (final, zipped, report_path)), 'Release output already exists; select a new output directory')
    env = os.environ.copy()
    env.update(PYTHONHASHSEED='0', SOURCE_DATE_EPOCH=EPOCH, PYTHONDONTWRITEBYTECODE='1', TWA_TEST_BASE_PACK=str(base))
    checked([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], env)
    checked([sys.executable, '-B', '-m', 'tools.mod', '--commander', 'hannibal', 'validate'], env)
    checked([sys.executable, '-B', '-m', 'tools.validation.repository'], env)
    repository = audit()
    for m in manifests:
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
        (bundle / 'Install.bat').write_bytes(b'@echo off\r\nstart "" "%~dp0TWA-Czech-Dubbing-Installer.exe"\r\n')
        (bundle / 'README.txt').write_text(
            'Total War: Arena - Czech Dubbing ' + VERSION + '\n\n'
            '1. Extract the entire ZIP.\n2. Double-click Install.bat or TWA-Czech-Dubbing-Installer.exe.\n'
            '3. Select the Total War: Arena folder.\n4. Close the game and launcher; click Install Czech Dubbing.\n'
            '5. Start the game yourself.\n\n'
            'Verify checks installed audio. Restore Original restores the verified backup.\n'
            'Backups: %LOCALAPPDATA%\\TWA-Czech-Dubbing\\backup\\<installation-id>\\audio_cn.pack\n'
            'Logs: %LOCALAPPDATA%\\TWA-Czech-Dubbing\\logs\\\n'
            'Unsupported versions are rejected without modifying game audio.\n'
            'If write access is denied, close the installer and use Run as administrator on the EXE.\n'
            'Use the same Windows account so its backup remains available.\n'
            'Requires Windows x64 and your own supported game; no Python/Git/API key needed.\n'
            'Keep at least 750 MB free (backup, build, Python extraction).\n', encoding='utf-8')
        add_notices(bundle)
        sums = ''.join(mod.sha256(p) + '  ' + p.relative_to(bundle).as_posix() + '\n' for p in file_list(bundle))
        (bundle / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8', newline='\n')
        release_audit = bundle_audit(bundle, manifests)
        # Exercise the actual frozen GUI/backend using its external payload and a disposable mock game.
        smoke_report = temp / 'frozen-smoke.json'
        process = subprocess.run([str(bundle / EXE), '--self-test', str(base), str(smoke_report)], env=env, timeout=180)
        require(smoke_report.is_file(), 'Frozen installer did not create its smoke report')
        smoke = json.loads(smoke_report.read_text(encoding='utf-8'))
        require(process.returncode == 0 and smoke['status'] == 'PASS',
                'Frozen installer smoke test failed: ' + smoke.get('error', 'unknown error'))
        candidate = temp / 'reproduced.pack'
        integration = mod.build(base, candidate, manifest)
        if reference:
            with candidate.open('rb') as left, reference.open('rb') as right:
                while True:
                    block = left.read(1024 * 1024)
                    require(block == right.read(1024 * 1024), 'Complete reference differs byte for byte')
                    if not block:
                        break
            integration['byte_identical_to_complete_reference'] = True
        archive_a = temp / 'first.zip'
        archive_b = temp / 'second.zip'
        deterministic_zip(bundle, archive_a)
        deterministic_zip(bundle, archive_b)
        require(mod.sha256(archive_a) == mod.sha256(archive_b), 'ZIP reproduction failed')
        # Test what an end user extracts, including the checksums and exact payload allowlist.
        extracted = temp / 'extracted'
        with zipfile.ZipFile(archive_a) as archive:
            require(archive.testzip() is None, 'ZIP CRC failed')
            archive.extractall(extracted)
        bundle_audit(extracted / NAME, manifests)
        report = {'status': 'PASS', 'release_name': NAME, 'version': VERSION,
                  'zip_path': zipped.relative_to(ROOT).as_posix() if zipped.is_relative_to(ROOT) else zipped.name,
                  'zip_size': archive_a.stat().st_size, 'zip_sha256': mod.sha256(archive_a),
                  'installer_size': (bundle / EXE).stat().st_size, 'installer_sha256': hashes[0],
                  'EXE_rebuilt_twice_identically': True, 'ZIP_repacked_twice_identically': True,
                  'python': sys.version.split()[0], 'pyinstaller': version('pyinstaller'),
                  'build_dependencies': {n: version(n) for n in ('pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools')},
                  'SOURCE_DATE_EPOCH': EPOCH, 'PYTHONHASHSEED': '0', 'repository': repository,
                  'release_audit': release_audit, 'integration': integration, 'frozen_smoke': smoke,
                  'human_listening': 'NOT_PERFORMED', 'game_runtime_test': 'NOT_PERFORMED'}
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
    args = parser.parse_args()
    try:
        build_release(args.base_pack, args.reference_pack, args.output_directory)
        return 0
    except Exception as error:
        print('RELEASE BUILD FAIL: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
