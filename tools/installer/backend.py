"""Verified backup -> offline build -> atomic replace, with no network/TTS calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from tools import deploy, mod
from tools.installer.catalog import discover
from tools.pack.reader import require
from tools.resources import VERSION


def no_redirects(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        require(not item.is_symlink() and not (item.exists() and
                getattr(item.lstat(), 'st_file_attributes', 0) & 0x400),
                'Junctions/symlinks are unsupported for installer paths')
    return path


def normalize_game_path(value):
    path = no_redirects(Path(value).expanduser())
    require(path.is_dir(), 'Game folder does not exist')
    candidates = [path, path.parent] if path.name.lower() == 'data' else [path]
    # Only explicitly named direct children, never a recursive disk search.
    candidates += [path / name for name in ('TotalWar_Arena', 'Total War Arena', 'Total War - Arena')]
    matches = [p for p in candidates if (p / 'data/audio_cn.pack').is_file()]
    require(len(matches) == 1, 'Select the Total War: Arena folder containing data/audio_cn.pack')
    root = matches[0]
    no_redirects(root / 'data/audio_cn.pack')
    return root.resolve(strict=True)


def known_game_folders():
    candidates = []
    for key in ('ProgramFiles', 'ProgramFiles(x86)', 'SystemDrive'):
        if os.getenv(key):
            base = Path(os.environ[key])
            if key == 'SystemDrive':
                base = Path(str(base) + '\\') / 'Games'
            candidates += [base / n for n in ('TotalWar_Arena', 'Total War Arena', 'Total War - Arena')]
    results = []
    for path in candidates:
        try:
            root = normalize_game_path(path)
            if root not in results:
                results.append(root)
        except (OSError, ValueError):
            pass
    return results


def state_directory():
    require(bool(os.getenv('LOCALAPPDATA')), 'Windows LOCALAPPDATA is unavailable')
    return Path(os.environ['LOCALAPPDATA']) / 'TWA-Czech-Dubbing'


@contextmanager
def transaction_lock(path):
    no_redirects(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # OS lock is released on crash; the harmless lock file may remain.
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError('Another installer operation is already running') from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


class Installer:
    def __init__(self, manifest, state_root=None, progress=None):
        self.manifest = manifest
        self.state_root = no_redirects(state_root if state_root is not None else state_directory())
        self.progress = progress or (lambda percent, message: None)

    def paths(self, value):
        root = normalize_game_path(value)
        key = hashlib.sha256(str(root).casefold().encode('utf-8')).hexdigest()[:24]
        backup = self.state_root / 'backup' / key / 'audio_cn.pack'
        no_redirects(backup)
        return root, root / 'data/audio_cn.pack', backup

    def report(self, percent, message):
        self.progress(percent, message)

    def inspect(self, value):
        root, target, backup = self.paths(value)
        self.report(10, 'Checking Czech dubbing files…')
        data = mod.validate_data(self.manifest)
        self.report(25, 'Reading game file and verifying integrity…')
        digest = mod.sha256(target)
        manifests = [self.manifest, *discover()]
        known = next((m for m in manifests if digest in (m['base']['sha256'], m['release']['sha256'])), None)
        if known is None:
            return {'state': 'UNSUPPORTED', 'sha256': digest, 'RSA': 'NOT_CHECKED',
                    'message': 'Unsupported audio_cn.pack version. No files were modified.'}
        result = mod.verify_pack(target, known)
        installed = result['kind'] == 'modified'
        message = (known['display_name'] + ' installed correctly.' if installed else 'Supported original game version detected.')
        self.report(100, message)
        return {**result, 'state': 'INSTALLED' if installed else 'ORIGINAL', 'message': message,
                'data': data, 'backup_exists': backup.is_file(), 'game_path': str(root)}

    def verified_backup(self, backup):
        no_redirects(backup)
        require(backup.is_file(), 'Original backup missing. Nothing was restored.')
        require(mod.verify_pack(backup, self.manifest)['kind'] == 'original',
                'Original backup could not be verified')

    def backup(self, root, target, backup):
        deploy.ensure_backup(target, backup, self.manifest)
        self.verified_backup(backup)
        metadata = backup.with_suffix('.json')
        no_redirects(metadata)
        if metadata.exists():
            value = json.loads(metadata.read_text(encoding='utf-8'))
            require(value['original_sha256'] == self.manifest['base']['sha256']
                    and Path(value['game_path']) == root, 'Backup metadata mismatch')
        else:
            value = dict(original_sha256=self.manifest['base']['sha256'],
                         created_at=datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc).isoformat(),
                         game_path=str(root), mod_version=VERSION)
            with metadata.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())

    @staticmethod
    def writable(target):
        # Probe only a new temporary file; never open the live PACK for writing.
        try:
            with tempfile.TemporaryFile(dir=target.parent, prefix='.twa-permission-'):
                pass
            require(os.access(target, os.W_OK), 'Game file is read-only')
        except PermissionError as error:
            raise PermissionError('Write access denied. Close this installer, right-click '
                                  'TWA-Czech-Dubbing-Installer.exe and choose Run as administrator, '
                                  'then select the game folder again.') from error

    def install(self, value):
        root, target, backup = self.paths(value)
        with transaction_lock(backup.parent / 'operation.lock'):
            deploy.assert_stopped(root)
            before = self.inspect(root)
            require(before['state'] != 'UNSUPPORTED', before['message'])
            if backup.exists():
                self.verified_backup(backup)
            if before['state'] == 'INSTALLED' and before['sha256'] == self.manifest['release']['sha256']:
                return {**before, 'status': 'ALREADY_INSTALLED'}
            self.writable(target)
            self.report(30, 'Verifying and preserving the original backup…')
            require(mod.sha256(target) == before['sha256'], 'Game file changed before backup')
            deploy.assert_stopped(root)
            if before['state'] == 'ORIGINAL':
                self.backup(root, target, backup)
            else:
                self.verified_backup(backup)
            # Same volume as target is required for atomic os.replace.
            with tempfile.TemporaryDirectory(dir=target.parent, prefix='.twa-dubbing-') as stage:
                candidate = Path(stage) / 'candidate.pack'
                self.report(45, 'Building a temporary copy and validating every entry…')
                result = mod.build(backup, candidate, self.manifest)
                mod.verify_pack(candidate, self.manifest, backup)
                self.report(85, 'Validation passed. Checking game processes again…')
                self.verified_backup(backup)
                require(mod.sha256(target) == before['sha256'], 'Game file changed during build; installation stopped')
                no_redirects(target)
                deploy.assert_stopped(root)
                os.replace(candidate, target)
                final = mod.verify_pack(target, self.manifest)
            self.report(100, 'Czech dubbing installed successfully.')
            return {**result, 'status': 'INSTALLED', 'backup': str(backup), 'sha256': final['sha256']}

    def restore(self, value):
        root, target, backup = self.paths(value)
        with transaction_lock(backup.parent / 'operation.lock'):
            deploy.assert_stopped(root)
            before = self.inspect(root)
            require(before['state'] != 'UNSUPPORTED', before['message'])
            if before['state'] == 'ORIGINAL':
                return {**before, 'status': 'ALREADY_ORIGINAL'}
            self.verified_backup(backup)
            self.writable(target)
            self.report(45, 'Preparing and verifying the original game file…')
            with tempfile.TemporaryDirectory(dir=target.parent, prefix='.twa-dubbing-') as stage:
                candidate = Path(stage) / 'original.pack'
                with backup.open('rb') as src, candidate.open('xb') as dest:
                    shutil.copyfileobj(src, dest, 1024 * 1024)
                    dest.flush()
                    os.fsync(dest.fileno())
                require(mod.verify_pack(candidate, self.manifest)['kind'] == 'original', 'Restore validation failed')
                self.verified_backup(backup)
                require(mod.sha256(target) == before['sha256'], 'Game file changed before restore')
                no_redirects(target)
                deploy.assert_stopped(root)
                os.replace(candidate, target)
                result = mod.verify_pack(target, self.manifest)
            self.report(100, 'Original game audio restored successfully.')
            return {**result, 'status': 'RESTORED'}
