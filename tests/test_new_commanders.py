"""v1.5.0 targeted checks for Scipio Africanus, Germanicus and Julius Caesar; mock game folders only.

No exhaustive transition matrix: singletons, one new commander plus unit voices, the full selection,
removal of one new commander, pending-only checkboxes, unknown-PACK safety and installed-state detection.
"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy, mod
from tools.installer.backend import Installer, InstallerError
from tools.installer.catalog import discover, discover_all, discover_shared, known_manifests, selection

NEW = {'scipio-africanus': ('Scipio Africanus', 249, 5, 'dc68174cb3aae799113163bd1460d256ff9f7bd4d29ce72bab6fe9f382469f02'),
       'germanicus': ('Germanicus', 234, 6, 'b710d2c43aaf2136ec48eec357aa306c709f17ce46e9b8aa354c8d6057ae0626'),
       'julius-caesar': ('Julius Caesar', 246, 7, '47624e843b05ad84f4abbf28deb6097b7627ec65e2692bf9ba43512bb7aabde6')}
UNIT = 'unit-voices'
EVERYTHING, EVERYTHING_COUNT = tuple(sorted(m['commander'] for m in discover_all())), 2353
EVERYTHING_SHA = '083a09ded4641b74fbc2f1a6e8bbda5aa346f8a4fbddb034f334ec4f9d0c702b'
LABELS = ['Hannibal  —  305 / 305 lines', 'Spartacus  —  304 / 304 lines', 'Zhuge Liang  —  293 / 293 lines',
          'Leonidas  —  257 / 257 lines', 'Scipio Africanus  —  249 / 249 lines', 'Germanicus  —  234 / 234 lines',
          'Julius Caesar  —  246 / 246 lines']


def modules(*names):
    by_id = {m['commander']: m for m in discover_all()}
    return selection([by_id[name] for name in names])


class NewCommanderCatalogTests(unittest.TestCase):
    def test_active_manifests_with_validated_singleton_hashes(self):
        by_id = {m['commander']: m for m in discover()}
        for name, (display, count, order, sha) in NEW.items():
            with self.subTest(name):
                manifest = by_id[name]
                self.assertEqual((manifest['display_name'], manifest['replacement_count'], manifest['display_order'],
                                  manifest['version'], manifest['release']['sha256'], manifest['release']['changed_entries']),
                                 (display, count, order, '1.5.0', sha, count))
                self.assertEqual(mod.validate_data(manifest)['status'], 'PASS')
                self.assertFalse(list((mod.ROOT / 'data/commanders' / name).glob('*staged*')))

    def test_modules_are_disjoint_and_full_selection_is_known(self):
        parts = discover_all()
        ids = [s['media_id'] for p in parts for s in p['replacements']]
        silent = {i for p in parts for i in p['silent_placeholder_ids']}
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(silent & set(ids))
        full = modules(*EVERYTHING)
        self.assertEqual((len(full['replacements']), full['release']['changed_entries'], full['release']['sha256']),
                         (EVERYTHING_COUNT, EVERYTHING_COUNT, EVERYTHING_SHA))
        self.assertEqual(len(known_manifests()), 2 ** len(parts) - 1)


@unittest.skipUnless(os.name == 'nt', 'Windows Tk required')
class NewCommanderCheckboxTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tools.installer import gui
        self.temp = tempfile.TemporaryDirectory(prefix='twa-new-gui-')
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gui.App(self.root, state_root=Path(self.temp.name) / 'state', auto_detect=False)
        self.addCleanup(self.app.close)
        backend = patch.object(gui, 'Installer', side_effect=AssertionError('Checkbox called backend'))
        self.service = backend.start()
        self.addCleanup(backend.stop)
        self.app.path.set(self.temp.name)
        self.root.after_cancel(self.app.timer)
        self.app.timer = None

    def test_seven_commanders_and_one_shared_checkbox_change_only_pending_state(self):
        self.assertEqual([c['text'] for c in self.app.checks], LABELS)
        self.assertEqual([c['text'] for c in self.app.shared_checks], ['Univerzální hlášky  —  465 lines'])
        self.assertEqual(discover_shared()[0]['description'], 'Český dabing obecných hlášek jednotek')
        self.app.accept_verified_state(dict(state='INSTALLED', installed_commanders=['hannibal'], backup_state='MISSING',
                                            original_source=None, original_source_file=None))
        self.app.controls()
        for index in (4, 5, 6):
            self.app.checks[index].invoke()
        self.app.shared_checks[0].invoke()
        self.assertEqual(self.app.pending_commanders, frozenset({'hannibal', *NEW, UNIT}))
        self.assertEqual(self.app.installed_commanders, frozenset({'hannibal'}))
        self.assertEqual(self.app.selected()['release']['changed_entries'], 305 + 249 + 234 + 246 + 465)
        self.assertEqual(str(self.app.install_button['state']), 'normal')
        self.assertIn('Pending: Hannibal + Scipio Africanus + Germanicus + Julius Caesar + Univerzální hlášky',
                      self.app.selection_status.get())
        self.service.assert_not_called()


@unittest.skipUnless(os.getenv('TWA_TEST_BASE_PACK'), 'Private canonical original required')
class NewCommanderInstallTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ['TWA_TEST_BASE_PACK']).resolve(strict=True)
        self.assertEqual(mod.sha256(self.base), discover()[0]['base']['sha256'])
        self.temp = tempfile.TemporaryDirectory(prefix='twa-new-install-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.game = self.folder / 'mock game'
        (self.game / 'data').mkdir(parents=True)
        self.target = self.game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, self.target)
        processes = patch.object(deploy, 'assert_stopped')
        processes.start()
        self.addCleanup(processes.stop)

    def assert_state(self, names, result):
        manifest = modules(*names)
        diff = mod.verify_pack(self.target, manifest, self.base)
        self.assertEqual((result['sha256'], diff['RSA'], diff['diff_outside_allowed_payloads'], diff['changed_entries']),
                         (manifest['release']['sha256'], 'PASS', 0, len(manifest['replacements'])))
        state = Installer(manifest, self.folder / 'observer').inspect(self.game)
        self.assertEqual((state['state'], set(state['installed_commanders'])), ('INSTALLED', set(names)))

    def test_each_new_commander_alone_from_clean_original(self):
        profile = self.folder / 'profile'
        for index, (name, (_, count, _, sha)) in enumerate(NEW.items()):
            with self.subTest(name):
                result = Installer(modules(name), profile).install(self.game)
                self.assertEqual((result['mode'], result['backup_created'], result['changed_entries'], result['sha256']),
                                 ('CANONICAL', index == 0, count, sha))
                self.assert_state((name,), result)
        self.assertEqual(len(list(profile.rglob('*.pack'))), 1)

    def test_additive_unit_voices_then_everything_then_remove_germanicus(self):
        mod.build(self.base, self.folder / 'caesar.pack', modules('julius-caesar'))
        os.replace(self.folder / 'caesar.pack', self.target)
        profile = self.folder / 'profile'
        with patch.object(mod, 'build', side_effect=AssertionError('Canonical build without an original')):
            result = Installer(modules('julius-caesar', UNIT), profile).install(self.game)
        self.assertEqual(result['mode'], 'ADDITIVE')
        self.assert_state(('julius-caesar', UNIT), result)
        with self.assertRaises(InstallerError) as caught:
            Installer(modules(UNIT), profile).install(self.game)
        self.assertEqual(caught.exception.code, 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')
        # A byte-identical local original enables canonical rebuilds (and is backed up first).
        shutil.copyfile(self.base, self.game / 'data/audio_en.pack')
        result = Installer(modules(*EVERYTHING), profile).install(self.game)
        self.assertEqual((result['mode'], result['backup_created'], result['changed_entries'], result['sha256']),
                         ('CANONICAL', True, EVERYTHING_COUNT, EVERYTHING_SHA))
        self.assert_state(EVERYTHING, result)
        remaining = tuple(n for n in EVERYTHING if n != 'germanicus')
        result = Installer(modules(*remaining), profile).install(self.game)
        self.assertEqual((result['mode'], result['changed_entries']), ('CANONICAL', EVERYTHING_COUNT - 234))
        self.assert_state(remaining, result)
        self.assertEqual(Installer(modules(*remaining), profile).install(self.game)['status'], 'ALREADY_INSTALLED')

    def test_unknown_pack_is_never_patched_or_backed_up(self):
        data = bytearray(self.target.read_bytes())
        spec = modules('germanicus')['replacements'][0]
        data[spec['offset'] + 100] ^= 0xFF
        self.target.write_bytes(bytes(data))
        before = mod.sha256(self.target)
        for selected in (modules('scipio-africanus'), modules('germanicus', UNIT), modules(*EVERYTHING)):
            with self.subTest(selected=selected['commander']), self.assertRaises(InstallerError) as caught:
                Installer(selected, self.folder / 'profile').install(self.game)
            self.assertEqual(caught.exception.code, 'UNKNOWN_PACK')
        self.assertEqual(mod.sha256(self.target), before)
        self.assertFalse(list((self.folder / 'profile').rglob('*.pack')))


if __name__ == '__main__':
    unittest.main()
