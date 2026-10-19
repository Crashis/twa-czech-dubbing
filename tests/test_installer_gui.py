"""Actual ttk command -> worker -> real PACK regression tests, mock folders only."""
import os
from pathlib import Path
import threading
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from tools import mod
from tools.installer import gui
from tools.installer.smoke import (MockGUI, additive_without_backup, all_selections,
                                   clean_original_auto_backup, game_file_recovery,
                                   h_to_all_without_backup, hannibal_to_all, invalid_backup_refusal,
                                   pending_install_button, rapid_and_empty_selection,
                                   removal_without_backup, remove_commanders)


@unittest.skipUnless(os.name == 'nt', 'Windows Tk required')
class InstallerGUIButtonStateTests(unittest.TestCase):
    """Real widgets with supplied inspection results; no game or backend access."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-button-state-')
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gui.App(self.root, state_root=Path(self.temp.name) / 'state', auto_detect=False)
        self.addCleanup(self.close)
        self.backend = patch.object(gui, 'Installer', side_effect=AssertionError('Button refresh called backend'))
        self.service = self.backend.start()
        self.addCleanup(self.backend.stop)
        self.parts = self.app.available_commanders
        self.names = tuple(m['commander'] for m in self.parts)
        self.app.path.set(self.temp.name)
        self.root.after_cancel(self.app.timer)
        self.app.timer = None

    def close(self):
        self.app.busy = False
        self.app.close()

    SOURCES = {'VALID': ('VALID', 'BACKUP', None), 'GAME_FILE': ('MISSING', 'GAME_FILE', 'data/audio_en.pack'),
               'MISSING': ('MISSING', None, None), 'INVALID': ('INVALID', None, None)}

    def installed(self, names, backup):
        """Supply an inspect result; a clean original is always its own source."""
        backup_state, source, path = self.SOURCES[backup]
        if not names and backup == 'MISSING':
            source, path = 'CURRENT_PACK', 'data/audio_cn.pack'
        self.app.accept_verified_state(dict(state='INSTALLED' if names else 'ORIGINAL',
                                           installed_commanders=list(names), backup_exists=backup_state != 'MISSING',
                                           backup_state=backup_state, original_source=source,
                                           original_source_file=path))
        self.app.controls()

    def select(self, names):
        for index, (manifest, var) in enumerate(self.app.choices):
            if var.get() != (manifest['commander'] in names):
                self.app.checks[index].invoke()

    def assert_button(self, enabled, text):
        self.assertEqual(str(self.app.install_button['state']), 'normal' if enabled else 'disabled')
        self.assertEqual(self.app.install_button.instate(['!disabled']), enabled)
        self.assertEqual(self.app.install_button['text'], text)
        self.service.assert_not_called()
        self.assertIsNone(self.app.timer)

    def test_pending_selection_enables_install_even_without_local_backup(self):
        self.installed(self.names[:1], 'MISSING')
        self.assert_button(False, 'Installed')
        self.assertIn('Original backup: unavailable', self.app.source_status.get())
        self.app.checks[1].invoke()
        self.assertEqual(self.app.pending_commanders, frozenset(self.names[:2]))
        self.assertEqual(self.app.installed_commanders, frozenset(self.names[:1]))
        self.assertEqual(self.app.selection_status.get(), 'Pending: Hannibal + Spartacus. Click Install to apply.')
        self.assert_button(True, 'Install')
        self.root.update()
        self.assert_button(True, 'Install')

    def test_install_button_state_matrix_with_and_without_local_backup(self):
        h, s, z = self.names
        # (installed, pending, enabled with an original source, enabled without any original source)
        cases = [((h,), (h,), False, False), ((h,), (h, z), True, True), ((h,), self.names, True, True),
                 (self.names, (h, s), True, False), (self.names, (s, z), True, False), ((s,), (s,), False, False),
                 ((), (z,), True, True), ((h,), (), False, False), ((h,), (s,), True, False),
                 ((s,), (h, s), True, True), ((z,), (s, z), True, True)]
        for backup in ('VALID', 'GAME_FILE', 'MISSING', 'INVALID'):
            for installed, pending, with_source, without_source in cases:
                with self.subTest(installed=installed, pending=pending, backup=backup):
                    self.installed(installed, backup)
                    self.select(pending)
                    enabled = {'VALID': with_source, 'GAME_FILE': with_source,
                               'MISSING': with_source if not installed else without_source, 'INVALID': False}[backup]
                    self.assert_button(enabled, 'Installed' if pending and set(installed) == set(pending) else 'Install')
                    removal = bool(pending) and bool(set(installed) - set(pending))
                    if backup == 'MISSING' and removal:
                        self.assertTrue(self.app.selection_status.get().startswith(
                            'Original backup required to remove installed dubbing'), self.app.selection_status.get())
                    if backup == 'INVALID' and pending and set(installed) != set(pending):
                        self.assertIn('original backup is invalid', self.app.selection_status.get())
        self.installed((h,), 'MISSING')
        self.select((h, s))
        self.app.busy = True
        self.app.controls()
        self.assert_button(False, 'Install')
        self.app.busy = False
        self.app.controls()
        self.assert_button(True, 'Install')
        self.app.last = None
        self.app.controls()
        self.assert_button(False, 'Install')

    def test_restore_button_requires_an_original_source(self):
        h = self.names[0]
        for names, backup, enabled, text in [((h,), 'VALID', True, 'verified'),
                                             ((h,), 'GAME_FILE', True, 'data/audio_en.pack'),
                                             ((h,), 'MISSING', False, 'unavailable'),
                                             ((h,), 'INVALID', False, 'INVALID'),
                                             ((), 'MISSING', False, 'before the first installation'),
                                             ((), 'VALID', False, 'verified')]:
            with self.subTest(names=names, backup=backup):
                self.installed(names, backup)
                self.assertEqual(str(self.app.restore_button['state']), 'normal' if enabled else 'disabled')
                self.assertIn(text, self.app.source_status.get())
                self.service.assert_not_called()
        self.installed((h,), 'MISSING')
        self.select(())
        self.assertIn('Restore Original needs', self.app.selection_status.get())


@unittest.skipUnless(os.name == 'nt' and os.getenv('TWA_TEST_BASE_PACK'),
                     'Windows Tk and private canonical original required')
class InstallerGUIIntegrationTests(unittest.TestCase):
    def session(self):
        session = MockGUI(os.environ['TWA_TEST_BASE_PACK'])
        session.__enter__()
        self.addCleanup(session.__exit__, None, None, None)
        return session

    def test_startup_and_checkbox_toggle_do_not_install_or_verify(self):
        session = self.session()
        session.assert_ui(())
        self.assertEqual(session.calls['game_writes'], 0)
        self.assertEqual(session.calls['install'], 0)
        self.assertEqual(session.calls['build'], 0)
        session.select(session.names)
        self.assertEqual(session.calls['inspect'], 1)
        self.assertFalse(session.app.installed_commanders)
        self.assertEqual(session.actual(())['changed_entries'], 0)

    def test_pending_hannibal_to_all_keeps_305_until_explicit_install_then_902(self):
        report = hannibal_to_all(self.session())
        self.assertEqual(report['start_replacements'], 305)
        self.assertEqual([t['still_installed'] for t in report['toggles']], [305, 305])
        self.assertEqual([t['game_writes'] for t in report['toggles']], [0, 0])
        self.assertEqual(report['after_install'], 902)
        self.assertEqual(report['verify_state'], 'Hannibal + Spartacus + Zhuge Liang')

    def test_pending_selection_enables_install_h_to_609_then_902(self):
        report = pending_install_button(self.session())
        self.assertEqual(report['startup_h_replacements'], 305)
        self.assertTrue(report['startup_button_disabled'])
        for toggle in ('toggle_s', 'toggle_z'):
            self.assertTrue(report[toggle]['button_enabled'])
            self.assertEqual(report[toggle]['game_writes'], 0)
            self.assertEqual(report[toggle]['backend_calls'], 0)
        self.assertEqual(report['install_hs']['actual_replacements'], 609)
        self.assertEqual(report['install_all']['actual_replacements'], 902)
        self.assertTrue(report['after_verify_button_disabled'])
        self.assertTrue(report['empty_selection_button_disabled'])

    def test_without_backup_h_to_hs_609_then_all_902_never_restores(self):
        """The exact screenshot scenario: H installed, backup missing, select S, Install."""
        report = additive_without_backup(self.session())
        self.assertEqual((report['start_replacements'], report['backup_state'], report['original_source']),
                         (305, 'MISSING', None))
        self.assertEqual((report['toggle_s']['game_writes'], report['toggle_s']['backend_calls']), (0, 0))
        self.assertTrue(report['toggle_s']['button_enabled'])
        self.assertEqual((report['install_hs']['actual_replacements'], report['install_hs']['mode']), (609, 'ADDITIVE'))
        self.assertEqual(report['install_hs']['status_message'], 'Hannibal + Spartacus installed correctly.')
        self.assertEqual((report['install_all']['actual_replacements'], report['install_all']['mode']), (902, 'ADDITIVE'))
        self.assertEqual((report['restore_calls'], report['backups_created']), (0, 0))
        self.assertEqual(report['verify_state'], 'Hannibal + Spartacus + Zhuge Liang')
        self.assertNotIn('Nothing was restored', ' '.join(report['dialogs']))

    def test_without_backup_h_to_all_three_with_zero_write_toggles(self):
        report = h_to_all_without_backup(self.session())
        self.assertEqual([t['game_writes'] for t in report['toggles']], [0, 0])
        self.assertTrue(all(t['button_enabled'] for t in report['toggles']))
        self.assertEqual((report['after_install'], report['RSA'], report['mode']), (902, 'PASS', 'ADDITIVE'))

    def test_without_backup_removal_is_disabled_and_backend_refuses(self):
        report = removal_without_backup(self.session())
        self.assertTrue(report['install_button_disabled'])
        self.assertEqual(report['pending_warning'], 'Original backup required to remove installed dubbing: Hannibal.')
        self.assertEqual((report['game_writes'], report['still_installed']), (0, 902))
        self.assertEqual(report['backend_install_refusal'], 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')
        self.assertTrue(report['restore_button_disabled'])
        self.assertEqual(report['backend_restore_refusal'], 'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE')

    def test_clean_original_in_fresh_profile_creates_backup_then_restores(self):
        report = clean_original_auto_backup(self.session())
        self.assertEqual((report['backup_created'], report['backup_sha256'], report['after_install']),
                         (True, report['canonical_sha256'], 902))
        self.assertEqual(report['backup_size'], 244019593)
        self.assertEqual(report['restore'], 'PASS')

    def test_canonical_game_file_enables_removal_and_restore(self):
        report = game_file_recovery(self.session())
        self.assertEqual(report['original_source_file'], 'data/audio_en.pack')
        self.assertTrue(report['restore_button_enabled'] and report['removal_button_enabled'])
        self.assertEqual((report['install_s']['actual_replacements'], report['install_s']['mode']), (304, 'CANONICAL'))
        self.assertEqual((report['backup_created_from'], report['restore']), ('data/audio_en.pack', 'PASS'))
        self.assertTrue(report['game_file_unchanged'])

    def test_invalid_backup_disables_install_and_restore(self):
        report = invalid_backup_refusal(self.session())
        self.assertTrue(report['install_button_disabled'] and report['restore_button_disabled'])
        self.assertEqual((report['backend_refusal'], report['game_writes'], report['backup_unchanged']),
                         ('INVALID_BACKUP', 0, True))

    def test_all_seven_selections_actual_pack_diff_and_restart_checkbox_state(self):
        observed = all_selections(self.session())
        self.assertEqual({k: r['actual_replacements'] for k, r in observed.items()}, {
            'hannibal': 305, 'spartacus': 304, 'zhuge-liang': 293,
            'hannibal+spartacus': 609, 'hannibal+zhuge-liang': 598,
            'spartacus+zhuge-liang': 597, 'hannibal+spartacus+zhuge-liang': 902})
        self.assertTrue(all(r['writes_before_install'] == 0 and r['diff_outside_selected_payloads'] == 0
                            and r['entry_count'] == 16545 and r['RSA'] == 'PASS' for r in observed.values()))

    def test_remove_each_commander_writes_only_after_install(self):
        observed = remove_commanders(self.session())
        self.assertEqual({k: r['after_install'] for k, r in observed.items()},
                         {'hannibal': 597, 'spartacus': 598, 'zhuge-liang': 609})
        self.assertTrue(all(r['game_writes'] == 0 and r['before_install'] == 902 for r in observed.values()))

    def test_rapid_clicks_and_empty_selection_do_not_write_or_restore(self):
        session = self.session()
        session.select((session.names[0],))
        session.install((session.names[0],))
        rapid_and_empty_selection(session)

    def test_verify_replaces_pending_with_actual_installed_state(self):
        session = self.session()
        names = (session.names[1],)
        session.select(names)
        session.install(names)
        session.select(session.names)
        session.verify(names)
        self.assertEqual(session.actual(names)['changed_entries'], 304)
        session.select(())
        session.verify(names)

    def test_restore_clears_checkboxes_and_empty_selection_can_verify(self):
        session = self.session()
        session.select(session.names)
        session.install(session.names)
        session.restore()
        session.verify(())
        session.restart()
        self.assertFalse(session.app.pending_commanders)
        self.assertFalse(session.app.installed_commanders)

    def test_failed_install_does_not_promote_pending_to_installed(self):
        session = self.session()
        first = (session.names[0],)
        session.select(first)
        session.install(first)
        digest, timestamp = mod.sha256(session.target), session.target.stat().st_mtime_ns
        backup = next((session.state_root / 'backup').rglob('audio_cn.pack'))
        backup_hash = mod.sha256(backup)
        before_writes = session.calls['game_writes']
        session.select(session.names)

        def reject(base, candidate, manifest):
            Path(candidate).write_bytes(b'incomplete test candidate')
            raise ValueError('Injected candidate validation failure')

        with patch.object(mod, 'build', side_effect=reject):
            session.app.install_button.invoke()
            session.assert_locked()
            session.wait()
        self.assertEqual(session.calls['game_writes'], before_writes)
        self.assertEqual((mod.sha256(session.target), session.target.stat().st_mtime_ns), (digest, timestamp))
        self.assertEqual(mod.sha256(backup), backup_hash)
        self.assertEqual(session.app.installed_commanders, frozenset(first))
        self.assertEqual(session.app.pending_commanders, frozenset(session.names))
        self.assertIsNone(session.app.last)
        self.assertIn('Injected candidate validation failure', session.app.status.get())
        session.verify(first)

    def test_busy_controls_block_selection_and_duplicate_actions(self):
        session = self.session()
        names = session.names[:2]
        session.select(names)
        entered, proceed = threading.Event(), threading.Event()
        original_build = mod.build

        def wait_before_build(*args, **kwargs):
            entered.set()
            if not proceed.wait(15):
                raise ValueError('Test did not release build gate')
            return original_build(*args, **kwargs)

        with patch.object(mod, 'build', side_effect=wait_before_build):
            try:
                session.app.install_button.invoke()
                session.assert_locked()
                self.assertTrue(entered.wait(10), 'Install worker never reached build')
                for check in session.app.checks:
                    check.invoke()
                session.app.install_button.invoke()
                session.app.verify_button.invoke()
                session.app.restore_button.invoke()
                self.assertEqual(session.app.pending_commanders, frozenset(names))
                self.assertEqual(session.calls['install'], 1)
                self.assertEqual(session.calls['restore'], 0)
            finally:
                proceed.set()
                session.wait()
        session.assert_ui(names)
        self.assertEqual(session.install_selections, [names])
        self.assertEqual(session.actual(names)['changed_entries'], 609)

    def test_folder_change_clears_selection_and_unsupported_pack_disables_install(self):
        session = self.session()
        session.select(session.names)
        session.app.path.set(str(session.folder / 'missing'))
        session.wait()
        self.assertIsNone(session.app.last)
        self.assertFalse(session.app.pending_commanders)
        self.assertFalse(session.app.installed_commanders)
        self.assertEqual(str(session.app.install_button['state']), 'disabled')
        session.app.browse_button.invoke()
        session.wait()
        session.assert_ui(())
        unsupported = session.folder / 'unsupported mock game'
        (unsupported / 'data').mkdir(parents=True)
        target = unsupported / 'data/audio_cn.pack'
        target.write_bytes(b'unsupported mock pack')
        session.app.path.set(str(unsupported))
        session.wait()
        self.assertEqual(session.app.last['state'], 'UNSUPPORTED')
        self.assertEqual(str(session.app.install_button['state']), 'disabled')
        self.assertTrue(all(str(c['state']) == 'disabled' for c in session.app.checks))
        self.assertEqual(target.read_bytes(), b'unsupported mock pack')


if __name__ == '__main__':
    unittest.main()
