"""Real Tk callbacks and PACK transactions, exclusively in disposable mock folders.

Shared by regression tests and frozen --self-test. Dialog answers and folder
discovery are simulated; ttk.invoke executes real widget commands and workers.
No process guard is bypassed and no real game directory can be supplied.
"""
from itertools import combinations
import json
from pathlib import Path
import shutil
import tempfile
import time
import tkinter as tk

from tools import mod
from tools.installer import backend, gui
from tools.installer.catalog import discover, selection
from tools.pack.reader import require

MAIN_PROFILE = 'private state'


class MockGUI:
    """Count real backend calls and writes without substituting their behavior."""

    def __init__(self, base_path):
        self.base = Path(base_path).resolve(strict=True)
        self.parts = discover()
        require(mod.sha256(self.base) == self.parts[0]['base']['sha256'], 'Unsupported test original')
        self.names = tuple(m['commander'] for m in self.parts)
        self.temp = self.root = None
        self.originals = []
        self.calls = dict(inspect=0, install=0, restore=0, build=0, additive_build=0, backup=0, game_writes=0)
        self.install_selections = []
        self.dialogs = []

    def hook(self, obj, name, replacement):
        self.originals.append((obj, name, getattr(obj, name)))
        setattr(obj, name, replacement)

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-gui-regression-')
        self.folder = Path(self.temp.name)
        self.game = self.folder / 'mock game with spaces'
        (self.game / 'data').mkdir(parents=True)
        self.target = self.game / 'data/audio_cn.pack'
        self.state_root = self.folder / MAIN_PROFILE
        shutil.copyfile(self.base, self.target)
        try:
            for action in ('inspect', 'install', 'restore', 'backup'):
                original = getattr(backend.Installer, action)

                def tracked(service, *args, _action=action, _original=original, **kwargs):
                    self.calls[_action] += 1
                    if _action == 'install':
                        self.install_selections.append(tuple(service.manifest.get(
                            'components', [service.manifest['commander']])))
                    return _original(service, *args, **kwargs)

                self.hook(backend.Installer, action, tracked)
            original_build, original_additive, original_replace = mod.build, mod.build_additive, backend.os.replace

            def build(*args, **kwargs):
                self.calls['build'] += 1
                return original_build(*args, **kwargs)

            def build_additive(*args, **kwargs):
                self.calls['additive_build'] += 1
                return original_additive(*args, **kwargs)

            def replace(src, dst, *args, **kwargs):
                if Path(dst).resolve() == self.target:
                    self.calls['game_writes'] += 1
                return original_replace(src, dst, *args, **kwargs)

            self.hook(mod, 'build', build)
            self.hook(mod, 'build_additive', build_additive)
            self.hook(backend.os, 'replace', replace)
            for name in ('showinfo', 'showerror'):
                self.hook(gui.messagebox, name, lambda title, text, **kw: self.dialogs.append((title, text)))
            self.hook(gui.messagebox, 'askyesno', lambda *args, **kw: True)
            self.hook(gui.filedialog, 'askdirectory', lambda **kw: str(self.game))
            self.hook(gui, 'known_game_folders', lambda: [self.game])
            self.open()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        try:
            if self.root is not None:
                self.wait()
                self.app.close()
                self.root = None
        finally:
            for obj, name, original in reversed(self.originals):
                setattr(obj, name, original)
            self.originals.clear()
            if self.temp is not None:
                self.temp.cleanup()

    def pump(self, seconds=0):
        deadline = time.monotonic() + seconds
        while True:
            self.root.update()
            if time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def wait(self):
        deadline = time.monotonic() + 180
        while self.app.busy or self.app.timer:
            require(time.monotonic() < deadline, 'GUI worker/timer timed out')
            self.pump(0.02)
        self.pump()

    def manifest(self, names):
        return selection([m for m in self.parts if m['commander'] in names])

    def assert_ui(self, names):
        expected = frozenset(names)
        require(self.app.installed_commanders == expected, 'Installed state differs from verified PACK')
        require(self.app.pending_commanders == expected, 'Pending state was not synchronized')
        require(frozenset(m['commander'] for m, var in self.app.choices if var.get()) == expected,
                'Checkboxes differ from verified PACK')
        require(str(self.app.install_button['state']) == 'disabled', 'Matching selection remains installable')
        require(self.app.install_button['text'] == ('Installed' if names else 'Install'), 'Wrong Install label')

    def open(self):
        before, digest = dict(self.calls), mod.sha256(self.target)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gui.App(self.root, state_root=self.state_root, auto_detect=True)
        require(not self.app.pending_commanders and not any(var.get() for _, var in self.app.choices),
                'Startup preselected available commanders before verification')
        self.wait()
        require(self.app.last is not None, 'Startup inspection failed: ' + self.app.status.get())
        require(self.calls['inspect'] == before['inspect'] + 1, 'Startup did not inspect exactly once')
        for action in ('install', 'restore', 'build', 'additive_build', 'backup', 'game_writes'):
            require(self.calls[action] == before[action], 'Startup invoked ' + action)
        require(mod.sha256(self.target) == digest, 'Startup changed PACK bytes')
        self.assert_ui(self.app.last['installed_commanders'])

    def restart(self):
        self.app.close()
        self.root = None
        self.open()

    def use_profile(self, name):
        """Restart in another installer profile, like a new Windows account with no backup."""
        self.state_root = self.folder / name
        self.restart()

    def backup_files(self):
        return sorted(p for p in (self.state_root / 'backup').rglob('*.pack')) if self.state_root.exists() else []

    def original_available(self):
        last = self.app.last or {}
        return bool(last.get('original_source')) and last.get('backup_state') != 'INVALID'

    def persistent_files(self):
        # A transaction may create its harmless OS lock file; every other file must be unchanged.
        return {k: v for k, v in self.state_files().items() if not k.endswith('/operation.lock')}

    def state_files(self):
        return {p.relative_to(self.state_root).as_posix(): (p.stat().st_mtime_ns, mod.sha256(p))
                for p in self.state_root.rglob('*') if p.is_file()}

    def select(self, names, toggles=None):
        """Wait beyond the former debounce: no Verify, build, backup, write or log."""
        before = dict(self.calls)
        digest, timestamp = mod.sha256(self.target), self.target.stat().st_mtime_ns
        files, log = self.state_files(), self.app.log.get('1.0', 'end')
        installed, last = self.app.installed_commanders, self.app.last
        if toggles is None:
            toggles = [m['commander'] for m, var in self.app.choices
                       if var.get() != (m['commander'] in names)]
        for name in toggles:
            self.app.checks[self.names.index(name)].invoke()
            self.pump()
        self.pump(0.85)
        require(self.calls == before, 'Checkbox invoked backend work: ' + repr(self.calls))
        require(not self.app.busy and self.app.timer is None, 'Checkbox scheduled a background operation')
        require(mod.sha256(self.target) == digest and self.target.stat().st_mtime_ns == timestamp,
                'Checkbox changed PACK bytes or modification time')
        require(self.state_files() == files, 'Checkbox changed backups or technical logs')
        require(self.app.log.get('1.0', 'end') == log, 'Checkbox appended an installation/verification log')
        require(self.app.last is last and self.app.installed_commanders == installed,
                'Pending selection changed installed state')
        require(self.app.pending_commanders == frozenset(names), 'Pending selection mismatch')
        require(frozenset(m['commander'] for m, var in self.app.choices if var.get()) == frozenset(names),
                'Widget selection mismatch')
        # Removing installed dubbing needs original bytes; adding never does.
        removing = bool(installed - frozenset(names))
        invalid = (self.app.last or {}).get('backup_state') == 'INVALID'
        enabled = (bool(names) and frozenset(names) != installed and not invalid
                   and (self.original_available() or not removing))
        require(str(self.app.install_button['state']) == ('normal' if enabled else 'disabled'),
                'Checkbox did not update Install availability')
        return {'game_writes': 0, 'backend_calls': 0, 'pack_sha256_unchanged': True,
                'button_enabled': self.app.install_button.instate(['!disabled'])}

    def assert_locked(self):
        require(self.app.busy, 'Explicit action did not start a GUI worker')
        for widget in (*self.app.checks, self.app.install_button, self.app.verify_button,
                       self.app.restore_button, self.app.entry, self.app.browse_button):
            require(str(widget['state']) == 'disabled', 'Control enabled during a transaction')

    def actual(self, names):
        manifest = self.manifest(names) if names else self.parts[0]
        result = mod.verify_pack(self.target, manifest, self.base)
        require(result['diff_outside_allowed_payloads'] == 0 and result['RSA'] == 'PASS',
                'Unexpected PACK differences or RSA failure')
        require(result['changed_entries'] == (len(manifest['replacements']) if names else 0),
                'Actual PACK diff has the wrong replacement count')
        return result

    def install(self, names):
        expected, before = self.manifest(names), dict(self.calls)
        backups = self.backup_files()
        require(str(self.app.install_button['state']) == 'normal', 'Install button disabled for pending changes')
        self.app.install_button.invoke()
        self.assert_locked()
        self.wait()
        require(self.app.last is not None, 'Install failed: ' + self.app.status.get())
        for action in ('install', 'game_writes'):
            require(self.calls[action] == before[action] + 1, 'Install did not invoke exactly one ' + action)
        require(self.calls['restore'] == before['restore'], 'Install called Restore')
        builds = (self.calls['build'] - before['build'], self.calls['additive_build'] - before['additive_build'])
        require(builds in ((1, 0), (0, 1)), 'Install did not run exactly one validated build: ' + repr(builds))
        mode = 'CANONICAL' if builds == (1, 0) else 'ADDITIVE'
        require(mode == 'CANONICAL' or not self.backup_files(), 'Additive install created a backup')
        require(self.install_selections[-1] == tuple(sorted(names)), 'GUI sent the wrong selection to backend')
        result = self.actual(names)
        require(result['sha256'] == expected['release']['sha256'], 'Installed whole-PACK SHA differs')
        self.assert_ui(names)
        message = expected['display_name'] + ' installed correctly.'
        require(self.app.status.get() == message and self.app.last['message'] == message,
                'Success message differs from actual installed state')
        tail = (message + '\nSHA-256: ' + result['sha256'] + '\nRSA PASS · '
                + str(result['entry_count']) + ' entries · ' + str(result['changed_entries']) + ' replacements')
        require(self.app.log.get('1.0', 'end').rstrip().endswith(tail), 'Status log has stale names/counts')
        require(float(self.app.progress['value']) == 100, 'Progress did not finish')
        records = [json.loads(line) for line in (self.state_root / 'logs/installer.jsonl').read_text(
            encoding='utf-8').splitlines()]
        require(records[-1]['action'] == 'install' and records[-1]['sha256'] == result['sha256']
                and records[-1]['changed_entries'] == result['changed_entries']
                and set(records[-1]['installed_commanders']) == set(names), 'Technical log has stale state')
        for path in self.backup_files():
            require(mod.sha256(path) == self.parts[0]['base']['sha256'], 'Backup is not the canonical original')
        return {'writes_before_install': 0, 'actual_replacements': result['changed_entries'],
                'sha256': result['sha256'], 'RSA': result['RSA'], 'entry_count': result['entry_count'],
                'diff_outside_selected_payloads': result['diff_outside_allowed_payloads'],
                'verify_state': expected['display_name'], 'status_message': message, 'mode': mode,
                'backup_created': len(self.backup_files()) > len(backups), 'result': 'PASS'}

    def verify(self, names):
        before = dict(self.calls)
        digest, timestamp = mod.sha256(self.target), self.target.stat().st_mtime_ns
        self.app.verify_button.invoke()
        self.wait()
        require(self.calls['inspect'] == before['inspect'] + 1, 'Verify did not inspect once')
        for action in ('install', 'restore', 'build', 'additive_build', 'backup', 'game_writes'):
            require(self.calls[action] == before[action], 'Verify invoked ' + action)
        require(mod.sha256(self.target) == digest and self.target.stat().st_mtime_ns == timestamp,
                'Verify wrote to the PACK')
        self.assert_ui(names)

    def restore(self):
        before = dict(self.calls)
        self.app.restore_button.invoke()
        self.assert_locked()
        self.wait()
        require(self.app.last is not None and self.app.last['state'] == 'ORIGINAL', 'Restore failed')
        require(self.calls['restore'] == before['restore'] + 1 and
                self.calls['game_writes'] == before['game_writes'] + 1, 'Restore callback/write mismatch')
        require(self.calls['install'] == before['install'], 'Restore unexpectedly installed dubbing')
        self.actual(())
        self.assert_ui(())


def all_selections(session):
    observed = {}
    for size in range(1, len(session.names) + 1):
        for names in combinations(session.names, size):
            session.select(names)
            observed['+'.join(names)] = session.install(names)
            session.restart()
            session.verify(names)
            session.restore()
            session.verify(())
    return observed


def pending_install_button(session):
    """Exact button regression: existing H -> explicitly install H+S -> all."""
    first, pair = session.names[:1], session.names[:2]
    session.select(first)
    session.install(first)
    session.restart()
    session.assert_ui(first)
    start = session.actual(first)['changed_entries']
    toggle_s = session.select(pair)
    toggle_s['button_enabled'] = session.app.install_button.instate(['!disabled'])
    install_pair = session.install(pair)
    toggle_z = session.select(session.names)
    toggle_z['button_enabled'] = session.app.install_button.instate(['!disabled'])
    install_all = session.install(session.names)
    session.verify(session.names)
    after_verify_disabled = session.app.install_button.instate(['disabled'])
    session.select(())
    empty_disabled = session.app.install_button.instate(['disabled'])
    session.verify(session.names)
    return {'result': 'PASS', 'startup_h_replacements': start, 'startup_button_disabled': True,
            'toggle_s': toggle_s, 'install_hs': install_pair, 'toggle_z': toggle_z,
            'install_all': install_all, 'after_verify_button_disabled': after_verify_disabled,
            'empty_selection_button_disabled': empty_disabled}


def reach(session, names):
    """Reach a known installed state through the main profile, which owns the canonical backup."""
    if session.state_root != session.folder / MAIN_PROFILE:
        session.use_profile(MAIN_PROFILE)
    if session.app.installed_commanders != frozenset(names):
        if names:
            session.select(names)
            session.install(names)
        else:
            session.restore()


def without_backup(session, names, profile):
    """Known installed state in a fresh profile with no backup and no other original source."""
    reach(session, names)
    session.use_profile(profile)
    last = session.app.last
    require(not last['backup_exists'] and last['backup_state'] == 'MISSING' and last['original_source'] is None,
            'Missing-backup fixture unexpectedly has an original source')
    session.assert_ui(names)
    require(str(session.app.restore_button['state']) == 'disabled', 'Restore enabled without an original source')
    return last


def refused(session, call, code):
    """Direct backend call that must fail closed before any PACK write."""
    before, digest = dict(session.calls), mod.sha256(session.target)
    timestamp, files = session.target.stat().st_mtime_ns, session.persistent_files()
    try:
        call()
    except backend.InstallerError as error:
        require(error.code == code, 'Unexpected refusal code: ' + error.code)
    else:
        raise ValueError('Backend did not refuse: expected ' + code)
    require(session.calls['game_writes'] == before['game_writes'] and mod.sha256(session.target) == digest
            and session.target.stat().st_mtime_ns == timestamp, 'Refused operation changed the PACK')
    require(session.persistent_files() == files, 'Refused operation changed backups or logs')
    return code


def additive_without_backup(session):
    """Scenario 1 (screenshot): H installed, backup missing, select H+S, Install -> 609, then all -> 902."""
    first, pair = session.names[:1], session.names[:2]
    last = without_backup(session, first, 'profile without backup - H to H+S')
    start = session.actual(first)['changed_entries']
    restores, dialogs = session.calls['restore'], len(session.dialogs)
    toggle_s = session.select(pair)
    install_pair = session.install(pair)
    toggle_z = session.select(session.names)
    install_all = session.install(session.names)
    session.verify(session.names)
    require(session.calls['restore'] == restores, 'Install without backup called Restore')
    require(not session.backup_files(), 'A modified PACK became an original backup')
    require(install_pair['mode'] == install_all['mode'] == 'ADDITIVE', 'Expected additive transitions')
    shown = [text for _, text in session.dialogs[dialogs:]]
    reach(session, session.names)
    return {'result': 'PASS', 'start_replacements': start, 'backup_state': last['backup_state'],
            'original_source': last['original_source'], 'toggle_s': toggle_s, 'install_hs': install_pair,
            'toggle_z': toggle_z, 'install_all': install_all, 'verify_state': install_all['verify_state'],
            'restore_calls': session.calls['restore'] - restores, 'backups_created': 0, 'dialogs': shown}


def h_to_all_without_backup(session):
    """Scenario 2: H installed, backup missing, toggle S and Z (0 writes), one Install -> 902."""
    first = session.names[:1]
    without_backup(session, first, 'profile without backup - H to all')
    toggles, pending = [], first
    for name in session.names[1:]:
        pending += (name,)
        toggles.append(dict(session.select(pending), toggled=name,
                            still_installed=session.actual(first)['changed_entries']))
    result = session.install(session.names)
    session.verify(session.names)
    require(result['mode'] == 'ADDITIVE' and not session.backup_files(), 'Expected an additive install without backup')
    reach(session, session.names)
    return {'result': 'PASS', 'toggles': toggles, 'after_install': result['actual_replacements'],
            'RSA': result['RSA'], 'mode': result['mode'], 'sha256': result['sha256']}


def removal_without_backup(session):
    """Scenario 3: H+S+Z installed, backup missing, select S+Z: disabled, safe refusal, 0 writes."""
    without_backup(session, session.names, 'profile without backup - removal')
    remaining = session.names[1:]
    before = dict(session.calls)
    no_write = session.select(remaining)
    disabled = session.app.install_button.instate(['disabled'])
    warning = session.app.selection_status.get()
    session.app.install_button.invoke()  # a disabled ttk button runs no command
    session.pump(0.85)
    require(session.calls == before, 'Disabled removal Install invoked backend')
    install_code = refused(session, lambda: backend.Installer(session.manifest(remaining), session.state_root)
                           .install(session.game), backend.ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL)
    restore_disabled = session.app.restore_button.instate(['disabled'])
    session.app.restore_button.invoke()
    session.pump(0.2)
    restore_code = refused(session, lambda: backend.Installer(session.parts[0], session.state_root)
                           .restore(session.game), backend.ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE)
    still = session.actual(session.names)['changed_entries']
    require(not session.backup_files(), 'Refusal created a backup')
    session.verify(session.names)
    reach(session, session.names)
    return {'result': 'SAFE REJECT', 'install_button_disabled': disabled, 'pending_warning': warning,
            'game_writes': no_write['game_writes'], 'still_installed': still,
            'backend_install_refusal': install_code, 'restore_button_disabled': restore_disabled,
            'backend_restore_refusal': restore_code}


def clean_original_auto_backup(session):
    """Clean original + fresh profile: Install all creates one verified backup, then Restore works."""
    reach(session, ())
    session.use_profile('fresh profile - clean original')
    require(session.app.last['original_source'] == 'CURRENT_PACK' and not session.backup_files(),
            'Clean original fixture already has a backup')
    session.select(session.names)
    result = session.install(session.names)
    backups = session.backup_files()
    require(len(backups) == 1 and result['backup_created'] and result['mode'] == 'CANONICAL',
            'Clean original install did not create exactly one backup')
    backup_hash, size = mod.sha256(backups[0]), backups[0].stat().st_size
    session.restore()
    session.verify(())
    require(session.backup_files() == backups and mod.sha256(backups[0]) == backup_hash, 'Backup changed')
    session.use_profile(MAIN_PROFILE)
    return {'result': 'PASS', 'backup_created': True, 'backup_sha256': backup_hash, 'backup_size': size,
            'canonical_sha256': session.parts[0]['base']['sha256'], 'after_install': result['actual_replacements'],
            'restore': 'PASS'}


def game_file_recovery(session):
    """H installed, no backup, canonical data/audio_en.pack present: removal and Restore are safe."""
    first, second = session.names[:1], session.names[1:2]
    reach(session, first)
    english = session.game / 'data/audio_en.pack'
    shutil.copyfile(session.base, english)
    try:
        state = (mod.sha256(english), english.stat().st_mtime_ns)
        session.use_profile('fresh profile - canonical game file')
        last = session.app.last
        require(last['original_source'] == 'GAME_FILE' and not session.backup_files(),
                'Canonical game file was not recognized read-only')
        restore_enabled = session.app.restore_button.instate(['!disabled'])
        session.select(second)
        removal_enabled = session.app.install_button.instate(['!disabled'])
        result = session.install(second)
        backups = session.backup_files()
        meta = json.loads(backups[0].with_suffix('.json').read_text(encoding='utf-8'))
        require(result['mode'] == 'CANONICAL' and len(backups) == 1 and meta['source'] == 'data/audio_en.pack',
                'Backup was not recovered from the canonical game file')
        session.restore()
        unchanged = (mod.sha256(english), english.stat().st_mtime_ns) == state
        require(unchanged, 'Original source game file was modified')
    finally:
        english.unlink(missing_ok=True)
    session.use_profile(MAIN_PROFILE)
    return {'result': 'PASS', 'original_source_file': last['original_source_file'],
            'restore_button_enabled': restore_enabled, 'removal_button_enabled': removal_enabled,
            'install_s': result, 'backup_created_from': meta['source'], 'restore': 'PASS',
            'game_file_unchanged': unchanged}


def invalid_backup_refusal(session):
    """An invalid backup is never used or replaced; Install and Restore stay disabled."""
    first = session.names[:1]
    reach(session, first)
    profile = session.folder / 'profile with invalid backup'
    _, _, path = backend.Installer(session.parts[0], profile).paths(session.game)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'invalid backup fixture')
    session.use_profile(profile.name)
    require(session.app.last['backup_state'] == 'INVALID', 'Invalid backup was accepted')
    no_write = session.select(session.names)
    install_disabled = session.app.install_button.instate(['disabled'])
    restore_disabled = session.app.restore_button.instate(['disabled'])
    code = refused(session, lambda: backend.Installer(session.manifest(session.names), session.state_root)
                   .install(session.game), backend.INVALID_BACKUP)
    unchanged = path.read_bytes() == b'invalid backup fixture'
    session.verify(first)
    session.use_profile(MAIN_PROFILE)
    return {'result': 'SAFE REJECT', 'install_button_disabled': install_disabled,
            'restore_button_disabled': restore_disabled, 'backend_refusal': code,
            'game_writes': no_write['game_writes'], 'backup_unchanged': unchanged}


def hannibal_to_all(session):
    first = (session.names[0],)
    session.select(first)
    session.install(first)
    session.restart()
    before, transitions, pending = session.actual(first)['changed_entries'], [], first
    for name in session.names[1:]:
        pending += (name,)
        no_write = session.select(pending)
        transitions.append(dict(no_write, toggled=name, still_installed=session.actual(first)['changed_entries']))
    actual = session.install(session.names)
    session.verify(session.names)
    return {'start_replacements': before, 'toggles': transitions,
            'after_install': actual['actual_replacements'], 'verify_state': actual['verify_state'], 'result': 'PASS'}


def remove_commanders(session):
    observed = {}
    if session.app.installed_commanders != frozenset(session.names):
        session.select(session.names)
        session.install(session.names)
    for gone in session.names:
        names = tuple(n for n in session.names if n != gone)
        no_write = session.select(names)
        before = session.actual(session.names)['changed_entries']
        result = session.install(names)
        session.verify(names)
        observed[gone] = dict(no_write, before_install=before, after_install=result['actual_replacements'],
                              verify_state=result['verify_state'], result='PASS')
        session.select(session.names)
        session.install(session.names)
    return observed


def rapid_and_empty_selection(session):
    current = tuple(sorted(session.app.installed_commanders))
    session.select(current, toggles=list(session.names) * 40)
    session.select(())
    require(str(session.app.install_button['state']) == 'disabled', 'Empty selection enabled Install')
    before = dict(session.calls)
    session.app.install_button.invoke()
    session.pump(0.85)
    require(session.calls == before, 'Disabled empty-selection Install invoked backend')
    session.verify(current)
    return {'rapid_clicks': 'PASS', 'zero_selection_no_restore': 'PASS',
            'verify_synchronizes_checkboxes': 'PASS', 'game_writes': 0}


def run(base_path, report_path):
    report = {'status': 'FAIL', 'game_runs': 0, 'real_game_writes': 0,
              'native_dialog_visual_review': 'NOT_PERFORMED', 'dialog_answers': 'SIMULATED',
              'folder_discovery': 'MOCK_FOLDER_ONLY', 'widget_actions': 'REAL_TTK_INVOKE'}
    try:
        with MockGUI(base_path) as session:
            report['selections'] = all_selections(session)
            report['pending_install_button'] = pending_install_button(session)
            session.restore()
            report['hannibal_to_all'] = hannibal_to_all(session)
            # Required frozen scenarios 1-3: a profile without any original backup.
            report['scenario_1_h_to_hs_without_backup'] = additive_without_backup(session)
            report['scenario_2_h_to_all_without_backup'] = h_to_all_without_backup(session)
            report['scenario_3_removal_without_backup'] = removal_without_backup(session)
            report['canonical_game_file_recovery'] = game_file_recovery(session)
            report['invalid_backup_refusal'] = invalid_backup_refusal(session)
            report['removals'] = remove_commanders(session)
            report['selection_only'] = rapid_and_empty_selection(session)
            report['clean_original_auto_backup'] = clean_original_auto_backup(session)
            reach(session, ())
            session.restart()
            report.update(status='PASS', GUI_start='PASS', GUI_startup_writes=0,
                          checkbox_toggle_writes=0, checkbox_backend_calls=0,
                          only_explicit_actions_write='PASS', pending_vs_installed='PASS',
                          operation_controls_disabled='PASS', restore_clears_checkboxes='PASS',
                          startup_synchronizes_all_known_states='PASS', RSA='PASS',
                          additive_install_without_backup='PASS', removal_without_original='SAFE_REJECT',
                          restore_without_original='SAFE_REJECT', auto_backup_from_clean_original='PASS',
                          canonical_game_file_source='PASS', invalid_backup='SAFE_REJECT',
                          selectable_commanders=list(session.names),
                          verified_changed_entries={k: v['actual_replacements'] for k, v in report['selections'].items()},
                          restored_sha256=mod.sha256(session.target), observed_mock_calls=session.calls)
    except Exception as error:
        report['error'] = str(error)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'PASS' else 2
