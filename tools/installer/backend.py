"""Verified state -> transition plan -> offline build -> atomic replace, no network/TTS calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from tools import deploy, mod
from tools.installer.catalog import discover, known_manifests
from tools.pack.reader import require
from tools.resources import VERSION

UNKNOWN_PACK = 'UNKNOWN_PACK'
ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL = 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL'
ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE = 'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE'
INVALID_BACKUP = 'INVALID_BACKUP'
INSTALL_VALIDATION_FAILED = 'INSTALL_VALIDATION_FAILED'
NO_WRITE = ' No game files were modified.'

# Explicitly named, read-only local files that may already hold the canonical
# original (launchers copy EN audio into the CN slot). A file is used only after
# its complete SHA-256, RSA and structure match; never a disk search.
ORIGINAL_SOURCE_CANDIDATES = ('audio_en.pack', 'audio_cn.pack.orig')


class InstallerError(ValueError):
    """Fail-closed refusal with a stable machine-readable code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def installed_message(manifest):
    return manifest['display_name'] + ' installed correctly.'


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

    def examine(self, root, target, backup):
        """Read-only: identify the PACK and the best verified canonical original source."""
        self.report(10, 'Checking Czech dubbing files…')
        data = mod.validate_data(self.manifest)
        self.report(25, 'Reading game file and verifying integrity…')
        digest = mod.sha256(target)
        known = next((m for m in known_manifests() if digest in (m['base']['sha256'], m['release']['sha256'])), None)
        if known is None:
            return {'state': 'UNSUPPORTED', 'sha256': digest, 'RSA': 'NOT_CHECKED', 'error_code': UNKNOWN_PACK,
                    'message': 'Unsupported audio_cn.pack version. No files were modified.'}, None
        result = mod.verify_pack(target, known)
        installed = result['kind'] == 'modified'
        self.report(60, 'Checking the original game audio backup…')
        source = self.original_source(root, backup, installed)
        message = installed_message(known) if installed else 'Supported original game version detected.'
        return {**result, 'state': 'INSTALLED' if installed else 'ORIGINAL', 'message': message,
                'data': data, 'backup_exists': backup.is_file(), 'game_path': str(root),
                'installed_commanders': known.get('components', [known['commander']]) if installed else [],
                **source}, (known if installed else None)

    def inspect(self, value):
        root, target, backup = self.paths(value)
        state, _ = self.examine(root, target, backup)
        self.report(100, state['message'])
        return state

    def original_source(self, root, backup, installed):
        """Profile backup first, then a clean current PACK, then a proven local game file."""
        if backup.exists() or backup.is_symlink():
            try:
                self.verified_backup(backup)
            except (OSError, ValueError):
                return dict(backup_state='INVALID', original_source=None, original_source_file=None)
            return dict(backup_state='VALID', original_source='BACKUP', original_source_file=None)
        if not installed:
            return dict(backup_state='MISSING', original_source='CURRENT_PACK',
                        original_source_file='data/audio_cn.pack')
        for name in ORIGINAL_SOURCE_CANDIDATES:
            path = root / 'data' / name
            try:
                no_redirects(path)
                # Size first avoids hashing unrelated packs; the full hash is the proof.
                if (path.is_file() and path.stat().st_size == self.manifest['base']['size']
                        and mod.verify_pack(path, self.manifest)['kind'] == 'original'):
                    return dict(backup_state='MISSING', original_source='GAME_FILE',
                                original_source_file='data/' + name)
            except (OSError, ValueError):
                continue
        return dict(backup_state='MISSING', original_source=None, original_source_file=None)

    @staticmethod
    def invalid_backup(backup):
        return InstallerError(INVALID_BACKUP, 'The original game audio backup is invalid. It was not used '
                              'or replaced.' + NO_WRITE + ' Backup: ' + str(backup))

    def verified_backup(self, backup):
        no_redirects(backup)
        try:
            valid = backup.is_file() and mod.verify_pack(backup, self.manifest)['kind'] == 'original'
        except (OSError, ValueError):
            valid = False
        if not valid:
            raise self.invalid_backup(backup)

    def backup(self, root, source, backup):
        """Keep one canonical backup; a new one is copied only from a verified clean source."""
        created = not backup.exists()
        if created:
            require(source is not None, 'No verified original source for the backup')
            source = no_redirects(source)
        # ensure_backup verifies the copy itself, so a modified source can never become a backup.
        deploy.ensure_backup(source, backup, self.manifest)
        self.verified_backup(backup)
        label = None
        if created:
            label = source.relative_to(root).as_posix() if source.is_relative_to(root) else source.name
        metadata = backup.with_suffix('.json')
        no_redirects(metadata)
        if metadata.exists():
            value = json.loads(metadata.read_text(encoding='utf-8'))
            require(value['original_sha256'] == self.manifest['base']['sha256']
                    and Path(value['game_path']) == root, 'Backup metadata mismatch')
        else:
            value = dict(original_sha256=self.manifest['base']['sha256'],
                         created_at=datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc).isoformat(),
                         game_path=str(root), mod_version=VERSION, source=label, size=backup.stat().st_size)
            with metadata.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        return {'backup_created': created, 'backup_size': backup.stat().st_size, 'backup_source': label}

    def plan(self, before):
        """CANONICAL rebuild when an original exists; otherwise only a strictly additive change."""
        if before['original_source']:
            return 'CANONICAL'
        selected = set(self.manifest.get('components', [self.manifest['commander']]))
        removed = set(before['installed_commanders']) - selected
        if removed:
            names = [m['display_name'] for m in discover() if m['commander'] in removed]
            raise InstallerError(ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL, 'Cannot remove '
                                 + ' + '.join(names)
                                 + ' because the original game audio backup is unavailable.' + NO_WRITE)
        return 'ADDITIVE'

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
            before, current = self.examine(root, target, backup)
            if before['state'] == 'UNSUPPORTED':
                raise InstallerError(UNKNOWN_PACK, before['message'])
            if before['state'] == 'INSTALLED' and before['sha256'] == self.manifest['release']['sha256']:
                return {**before, 'status': 'ALREADY_INSTALLED'}
            if before['backup_state'] == 'INVALID':
                raise self.invalid_backup(backup)
            mode = self.plan(before)
            self.writable(target)
            require(mod.sha256(target) == before['sha256'], 'Game file changed before backup')
            deploy.assert_stopped(root)
            saved = {'backup_created': False}
            if mode == 'CANONICAL':
                self.report(30, 'Verifying and preserving the original backup…')
                source = None if before['original_source'] == 'BACKUP' else root / before['original_source_file']
                saved = self.backup(root, source, backup)
            # Same volume as target is required for atomic os.replace.
            with tempfile.TemporaryDirectory(dir=target.parent, prefix='.twa-dubbing-') as stage:
                candidate = Path(stage) / 'candidate.pack'
                try:
                    if mode == 'CANONICAL':
                        self.report(45, 'Building a temporary copy from the original and validating every entry…')
                        result = mod.build(backup, candidate, self.manifest)
                        mod.verify_pack(candidate, self.manifest, backup)
                    else:
                        self.report(45, 'Adding the selected dubbing to a temporary copy and validating every entry…')
                        result = mod.build_additive(target, candidate, current, self.manifest)
                        mod.verify_pack(candidate, self.manifest)
                except InstallerError:
                    raise
                except (OSError, ValueError) as error:
                    raise InstallerError(INSTALL_VALIDATION_FAILED, 'Installation validation failed: '
                                         + str(error) + '.' + NO_WRITE) from error
                self.report(85, 'Validation passed. Checking game processes again…')
                if mode == 'CANONICAL':
                    self.verified_backup(backup)
                require(mod.sha256(target) == before['sha256'], 'Game file changed during build; installation stopped')
                no_redirects(target)
                deploy.assert_stopped(root)
                os.replace(candidate, target)
                final = mod.verify_pack(target, self.manifest)
            message = installed_message(self.manifest)
            self.report(100, message)
            return {**result, **saved, 'status': 'INSTALLED', 'mode': mode,
                    'backup': str(backup) if mode == 'CANONICAL' else None,
                    'sha256': final['sha256'], 'message': message,
                    'changed_entries': final['changed_entries'], 'entry_count': final['entry_count'],
                    'RSA': final['RSA']}

    def restore(self, value):
        root, target, backup = self.paths(value)
        with transaction_lock(backup.parent / 'operation.lock'):
            deploy.assert_stopped(root)
            before, _ = self.examine(root, target, backup)
            if before['state'] == 'UNSUPPORTED':
                raise InstallerError(UNKNOWN_PACK, before['message'])
            if before['state'] == 'ORIGINAL':
                return {**before, 'status': 'ALREADY_ORIGINAL'}
            if before['backup_state'] == 'INVALID':
                raise self.invalid_backup(backup)
            if not before['original_source']:
                raise InstallerError(ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE, 'Original game audio is not available. '
                                     'Restore cannot be performed safely.' + NO_WRITE)
            self.writable(target)
            saved = {'backup_created': False}
            if before['original_source'] == 'GAME_FILE':
                require(mod.sha256(target) == before['sha256'], 'Game file changed before backup')
                deploy.assert_stopped(root)
                self.report(30, 'Creating a verified backup of the original game audio…')
                saved = self.backup(root, root / before['original_source_file'], backup)
            self.verified_backup(backup)
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
            return {**result, **saved, 'status': 'RESTORED'}
