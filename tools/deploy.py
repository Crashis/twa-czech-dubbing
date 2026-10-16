"""Windows installation/restore transactions; never starts or stops the game."""
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from tools.mod import build, load_manifest, sha256, validate_data, verify_pack
from tools.pack.reader import require

PROCESS_QUERY = r'''
$ErrorActionPreference = 'Stop'
$gameRoot = $env:TWA_DUBBING_GAME_ROOT.TrimEnd('\')
$related = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    $_.ProcessId -ne $PID -and (
        $_.Name -match '^(Arena(?:64)?|TotalWar[-_ ]?Arena|twa[-_ ]?launcher|ad[-_ ]?arma[-_ ]?launcher|TWARevival(?:Launcher)?)\.exe$' -or
        ($_.ExecutablePath -and (
            $_.ExecutablePath.StartsWith($gameRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $_.ExecutablePath -like '*\TWA Launcher\*'
        )) -or
        ($_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'TWARevival.+(player_launcher\.py|player_bootstrap\.py|native_launch\.py)')
    )
})
ConvertTo-Json -InputObject @($related | Select-Object ProcessId,Name) -Compress
'''


def assert_stopped(game_root):
    require(os.name == 'nt', 'Installation requires Windows; offline build/verify are portable')
    env = os.environ.copy()
    env['TWA_DUBBING_GAME_ROOT'] = str(game_root)
    encoded = base64.b64encode(PROCESS_QUERY.encode('utf-16-le')).decode('ascii')
    query = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                           env=env, capture_output=True, text=True)
    require(query.returncode == 0, 'Cannot inspect game/launcher processes; close them and retry')
    running = json.loads(query.stdout)
    require(isinstance(running, list), 'Unexpected process query response')
    require(not running, 'Game/launcher is running; close it before installation/restore')


def game_paths(game_path, manifest):
    root = Path(game_path).resolve(strict=True)
    require(root.is_dir(), 'GamePath is not a directory')
    target = root / 'data' / manifest['runtime_slot']
    control = root / '.twa-czech-dubbing'
    # Fail closed for redirected payloads/control directories.
    for item in (root / 'data', target, control, control / 'backups', control / 'staging'):
        require(not item.is_symlink() and not (item.exists() and bool(getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)),
                'Junctions/symlinks are unsupported for installation paths')
        require(item.resolve().is_relative_to(root), 'Installation path escapes GamePath')
    require(target.is_file(), 'Missing <GamePath>/data/' + manifest['runtime_slot'])
    backup = control / 'backups' / 'audio_cn.original.pack'
    return root, target, control, backup


def ensure_backup(source, backup, manifest):
    if backup.exists():
        require(verify_pack(backup, manifest)['kind'] == 'original', 'Backup is not canonical original')
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    partial = backup.with_name('b.' + uuid.uuid4().hex[:12] + '.partial')
    try:
        with source.open('rb') as src, partial.open('xb') as dest:
            shutil.copyfileobj(src, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
        require(verify_pack(partial, manifest)['kind'] == 'original', 'Backup copy failed validation')
        os.link(partial, backup)  # Never overwrite a previous backup.
    finally:
        partial.unlink(missing_ok=True)


def install(game_path, manifest, dry_run=False):
    root, target, control, backup = game_paths(game_path, manifest)
    assert_stopped(root)
    validate_data(manifest)
    before = verify_pack(target, manifest)
    if backup.exists():
        require(verify_pack(backup, manifest)['kind'] == 'original', 'Invalid original backup; no writes allowed')
    if before['kind'] == 'modified':
        require(backup.exists(), 'Mod is already present but original backup is missing; recover a supported original before reinstalling')
        return {'status': 'ALREADY_INSTALLED', 'sha256': before['sha256'], 'dry_run': dry_run}
    if dry_run:
        return {'status': 'DRY_RUN_PASS', 'action': 'install', 'base_sha256': before['sha256'],
                'expected_sha256': manifest['release']['sha256'], 'replacements': manifest['expected_replacement_count']}
    assert_stopped(root)
    require(sha256(target) == before['sha256'], 'Game PACK changed before backup')
    ensure_backup(target, backup, manifest)
    staging = control / 'staging'
    staging.mkdir(parents=True, exist_ok=True)
    candidate = staging / ('i.' + uuid.uuid4().hex[:12] + '.pack')
    try:
        result = build(backup, candidate, manifest)
        assert_stopped(root)
        require(sha256(target) == before['sha256'], 'Game PACK changed during build; refusing installation')
        require(sha256(backup) == manifest['base']['sha256'], 'Backup changed during build')
        os.replace(candidate, target)
        installed = verify_pack(target, manifest)
        require(installed['kind'] == 'modified', 'Post-install verification failed; original backup is preserved')
        return {**result, 'status': 'INSTALLED', 'backup': str(backup)}
    finally:
        candidate.unlink(missing_ok=True)


def restore(game_path, manifest, dry_run=False):
    root, target, control, backup = game_paths(game_path, manifest)
    assert_stopped(root)
    before = verify_pack(target, manifest)
    if before['kind'] == 'original':
        return {'status': 'ALREADY_ORIGINAL', 'sha256': before['sha256'], 'dry_run': dry_run}
    require(backup.is_file(), 'Original backup missing; nothing was changed')
    require(verify_pack(backup, manifest)['kind'] == 'original', 'Backup is not canonical original')
    if dry_run:
        return {'status': 'DRY_RUN_PASS', 'action': 'restore', 'expected_sha256': manifest['base']['sha256']}
    staging = control / 'staging'
    staging.mkdir(parents=True, exist_ok=True)
    candidate = staging / ('r.' + uuid.uuid4().hex[:12] + '.pack')
    try:
        with backup.open('rb') as src, candidate.open('xb') as dest:
            shutil.copyfileobj(src, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
        require(verify_pack(candidate, manifest)['kind'] == 'original', 'Restore candidate failed verification')
        assert_stopped(root)
        require(sha256(target) == before['sha256'], 'Game PACK changed before restore')
        require(sha256(backup) == manifest['base']['sha256'], 'Backup changed before restore')
        os.replace(candidate, target)
        result = verify_pack(target, manifest)
        return {'status': 'RESTORED', 'sha256': result['sha256'], 'RSA': result['RSA']}
    finally:
        candidate.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'restore', 'verify'])
    parser.add_argument('--game-path', required=True)
    parser.add_argument('--commander', default='hannibal')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.commander)
        if args.action == 'verify':
            _, target, _, _ = game_paths(args.game_path, manifest)
            result = verify_pack(target, manifest) | {'data': validate_data(manifest)}
        else:
            result = (install if args.action == 'install' else restore)(args.game_path, manifest, args.dry_run)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, AssertionError, IndexError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
