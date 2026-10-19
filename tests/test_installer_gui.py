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
                                   newest_only_from_clean_original, pending_install_button,
                                   rapid_and_empty_selection, removal_without_backup, remove_commanders,
                                   remove_newest_with_backup, upgrade_newest)

ALL_FOUR = 'Hannibal + Spartacus + Zhuge Liang + Leonidas'


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

    def test_four_checkboxes_in_installer_order_with_line_counts(self):
        self.assertEqual(self.names, ('hannibal', 'spartacus', 'zhuge-liang', 'leonidas'))
        self.assertEqual([c['text'] for c in self.app.checks],
                         ['Hannibal  —  305 / 305 lines', 'Spartacus  —  304 / 304 lines',
                          'Zhuge Liang  —  293 / 293 lines', 'Leonidas  —  257 / 257 lines'])
        self.installed(self.names[:3], 'MISSING')
        self.assertEqual([var.get() for _, var in self.app.choices], [True, True, True, False])
        self.app.checks[3].invoke()
        self.assertEqual(self.app.selection_status.get(), 'Pending: ' + ALL_FOUR + '. Click Install to apply.')
        self.assert_button(True, 'Install')

    def test_install_button_state_matrix_with_and_without_local_backup(self):
        h, s, z, l = self.names
        # (installed, pending, enabled with an original source, enabled without any original source)
        cases = [((h,), (h,), False, False), ((h,), (h, z), True, True), ((h,), self.names, True, True),
                 (self.names, (h, s), True, False), (self.names, (s, z), True, False), ((s,), (s,), False, False),
                 ((), (z,), True, True), ((h,), (), False, False), ((h,), (s,), True, False),
                 ((s,), (h, s), True, True), ((z,), (s, z), True, True), ((h, s, z), self.names, True, True),
                 (self.names, (h, s, z), True, False), (self.names, (l,), True, False), ((l,), (l,), False, False),
                 ((), (l,), True, True), ((h, l), (s, l), True, False), ((s, z), (s, z, l), True, True),
                 (self.names, self.names, False, False)]
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

    def test_pending_hannibal_to_all_keeps_305_until_explicit_install_then_1159(self):
        report = hannibal_to_all(self.session())
        self.assertEqual(report['start_replacements'], 305)
        self.assertEqual([t['still_installed'] for t in report['toggles']], [305, 305, 305])
        self.assertEqual([t['game_writes'] for t in report['toggles']], [0, 0, 0])
        self.assertEqual(report['after_install'], 1159)
        self.assertEqual(report['verify_state'], ALL_FOUR)

    def test_pending_selection_enables_install_h_to_609_then_1159(self):
        report = pending_install_button(self.session())
        self.assertEqual(report['startup_h_replacements'], 305)
        self.assertTrue(report['startup_button_disabled'])
        for toggle in ('toggle_s', 'toggle_z'):
            self.assertTrue(report[toggle]['button_enabled'])
            self.assertEqual(report[toggle]['game_writes'], 0)
            self.assertEqual(report[toggle]['backend_calls'], 0)
        self.assertEqual(report['install_hs']['actual_replacements'], 609)
        self.assertEqual(report['install_all']['actual_replacements'], 1159)
        self.assertTrue(report['after_verify_button_disabled'])
        self.assertTrue(report['empty_selection_button_disabled'])

    def test_without_backup_h_to_hs_609_then_all_1159_never_restores(self):
        """The exact screenshot scenario: H installed, backup missing, select S, Install."""
        report = additive_without_backup(self.session())
        self.assertEqual((report['start_replacements'], report['backup_state'], report['original_source']),
                         (305, 'MISSING', None))
        self.assertEqual((report['toggle_s']['game_writes'], report['toggle_s']['backend_calls']), (0, 0))
        self.assertTrue(report['toggle_s']['button_enabled'])
        self.assertEqual((report['install_hs']['actual_replacements'], report['install_hs']['mode']), (609, 'ADDITIVE'))
        self.assertEqual(report['install_hs']['status_message'], 'Hannibal + Spartacus installed correctly.')
        self.assertEqual((report['install_all']['actual_replacements'], report['install_all']['mode']), (1159, 'ADDITIVE'))
        self.assertEqual((report['restore_calls'], report['backups_created']), (0, 0))
        self.assertEqual(report['verify_state'], ALL_FOUR)
        self.assertNotIn('Nothing was restored', ' '.join(report['dialogs']))

    def test_without_backup_h_to_all_four_with_zero_write_toggles(self):
        report = h_to_all_without_backup(self.session())
        self.assertEqual([t['game_writes'] for t in report['toggles']], [0, 0, 0])
        self.assertTrue(all(t['button_enabled'] for t in report['toggles']))
        self.assertEqual((report['after_install'], report['RSA'], report['mode']), (1159, 'PASS', 'ADDITIVE'))

    def test_without_backup_removal_is_disabled_and_backend_refuses(self):
        report = removal_without_backup(self.session())
        self.assertTrue(report['install_button_disabled'])
        self.assertEqual(report['pending_warning'], 'Original backup required to remove installed dubbing: Hannibal.')
        self.assertEqual((report['game_writes'], report['still_installed']), (0, 1159))
        self.assertEqual(report['backend_install_refusal'], 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')
        self.assertTrue(report['restore_button_disabled'])
        self.assertEqual(report['backend_restore_refusal'], 'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE')

    def test_scenario_a_upgrade_from_previous_release_without_backup(self):
        """v1.2.0 state H+S+Z (902), no backup: Verify, check Leonidas (0 writes), Install -> 1159."""
        report = upgrade_newest(self.session(), backup=False)
        self.assertEqual((report['backup_state'], report['original_source']), ('MISSING', None))
        self.assertEqual((report['start_replacements'], report['start_verify_state']),
                         (902, 'Hannibal + Spartacus + Zhuge Liang'))
        self.assertTrue(report['newest_unchecked_after_verify'])
        self.assertEqual((report['select_newest']['game_writes'], report['select_newest']['backend_calls']), (0, 0))
        self.assertTrue(report['select_newest']['button_enabled'])
        install = report['install']
        self.assertEqual((install['actual_replacements'], install['mode'], install['RSA'], install['entry_count'],
                          install['diff_outside_selected_payloads']), (1159, 'ADDITIVE', 'PASS', 16545, 0))
        self.assertEqual((install['verify_state'], install['status_message']), (ALL_FOUR, ALL_FOUR + ' installed correctly.'))
        self.assertTrue(report['all_checked_after_verify'])

    def test_upgrade_from_previous_release_with_backup(self):
        report = upgrade_newest(self.session(), backup=True)
        self.assertEqual((report['backup_state'], report['original_source']), ('VALID', 'BACKUP'))
        self.assertEqual(report['start_replacements'], 902)
        self.assertEqual((report['select_newest']['game_writes'], report['select_newest']['backend_calls']), (0, 0))
        self.assertEqual((report['install']['actual_replacements'], report['install']['mode']), (1159, 'CANONICAL'))
        self.assertTrue(report['newest_unchecked_after_verify'] and report['all_checked_after_verify'])

    def test_scenario_b_leonidas_only_from_clean_original(self):
        report = newest_only_from_clean_original(self.session())
        self.assertEqual((report['select']['game_writes'], report['install']['actual_replacements']), (0, 257))
        self.assertEqual(report['install']['status_message'], 'Leonidas installed correctly.')
        self.assertEqual(report['restore'], 'PASS')

    def test_scenario_d_remove_leonidas_without_original_is_rejected(self):
        report = removal_without_backup(self.session(), 'leonidas')
        self.assertTrue(report['install_button_disabled'])
        self.assertEqual(report['pending_warning'], 'Original backup required to remove installed dubbing: Leonidas.')
        self.assertEqual((report['game_writes'], report['still_installed']), (0, 1159))
        self.assertEqual(report['backend_install_refusal'], 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')

    def test_scenario_e_remove_leonidas_with_valid_backup(self):
        report = remove_newest_with_backup(self.session())
        self.assertEqual(report['start_replacements'], 1159)
        self.assertEqual((report['select_without_newest']['game_writes'],
                          report['install_without_newest']['actual_replacements']), (0, 902))
        self.assertEqual(report['install_without_newest']['verify_state'], 'Hannibal + Spartacus + Zhuge Liang')
        self.assertEqual(report['install_only_newest']['actual_replacements'], 257)
        self.assertEqual(report['restore'], 'PASS')

    def test_clean_original_in_fresh_profile_creates_backup_then_restores(self):
        report = clean_original_auto_backup(self.session())
        self.assertEqual((report['backup_created'], report['backup_sha256'], report['after_install']),
                         (True, report['canonical_sha256'], 1159))
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

    def test_all_fifteen_selections_actual_pack_diff_and_restart_checkbox_state(self):
        observed = all_selections(self.session())
        # Keys follow installer order (H, S, Z, L); counts come from the full diff of the actual PACK.
        self.assertEqual({k: r['actual_replacements'] for k, r in observed.items()}, {
            'hannibal': 305, 'spartacus': 304, 'zhuge-liang': 293, 'leonidas': 257,
            'hannibal+spartacus': 609, 'hannibal+zhuge-liang': 598, 'hannibal+leonidas': 562,
            'spartacus+zhuge-liang': 597, 'spartacus+leonidas': 561, 'zhuge-liang+leonidas': 550,
            'hannibal+spartacus+zhuge-liang': 902, 'hannibal+spartacus+leonidas': 866,
            'hannibal+zhuge-liang+leonidas': 855, 'spartacus+zhuge-liang+leonidas': 854,
            'hannibal+spartacus+zhuge-liang+leonidas': 1159})
        self.assertTrue(all(r['writes_before_install'] == 0 and r['diff_outside_selected_payloads'] == 0
                            and r['entry_count'] == 16545 and r['RSA'] == 'PASS' for r in observed.values()))
        self.assertEqual(observed['hannibal+spartacus+zhuge-liang+leonidas']['status_message'],
                         ALL_FOUR + ' installed correctly.')

    def test_remove_each_commander_writes_only_after_install(self):
        observed = remove_commanders(self.session())
        self.assertEqual({k: r['after_install'] for k, r in observed.items()},
                         {'hannibal': 854, 'spartacus': 855, 'zhuge-liang': 866, 'leonidas': 902})
        self.assertTrue(all(r['game_writes'] == 0 and r['before_install'] == 1159 for r in observed.values()))

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
