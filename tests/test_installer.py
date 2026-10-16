"""Installer guards and full temporary-install transactions (never a real game)."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy, mod
from tools.installer.backend import Installer, normalize_game_path, transaction_lock
from tools.installer.catalog import discover, merge_manifests, selection


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-installer-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = mod.load_manifest()
        self.service = Installer(self.manifest, self.root / 'state')

    def test_catalog_and_manifest_metadata(self):
        self.assertEqual(discover()[0]['id'], 'hannibal')
        self.assertEqual(selection([self.manifest]), self.manifest)
        self.assertEqual(self.manifest['replacement_count'], 305)

    def test_missing_pack_rejected(self):
        with self.assertRaises(ValueError):
            self.service.inspect(self.root)

    def test_unsupported_hash_rejected_without_target_writes(self):
        (self.root / 'data').mkdir()
        target = self.root / 'data/audio_cn.pack'
        target.write_bytes(b'unknown game version')
        self.assertEqual(self.service.inspect(self.root)['state'], 'UNSUPPORTED')
        with patch.object(deploy, 'assert_stopped'), self.assertRaises(ValueError):
            self.service.install(self.root)
        with patch.object(deploy, 'assert_stopped'), self.assertRaises(ValueError):
            self.service.restore(self.root)
        self.assertEqual(target.read_bytes(), b'unknown game version')
        self.assertFalse(list((self.root / 'state').rglob('*.pack')))

    def test_data_folder_and_explicit_parent_detection(self):
        game = self.root / 'TotalWar_Arena'
        (game / 'data').mkdir(parents=True)
        (game / 'data/audio_cn.pack').write_bytes(b'probe')
        self.assertEqual(normalize_game_path(game / 'data'), game)
        self.assertEqual(normalize_game_path(self.root), game)

    def joint_parts(self):
        other = copy.deepcopy(self.manifest)
        other.update(commander='leonidas', display_name='Leonidas')
        return [self.manifest, other]

    def test_identical_overlap_allowed(self):
        merged = merge_manifests(self.joint_parts(), self.manifest['release'])
        self.assertEqual(len(merged['replacements']), 305)

    def test_conflicting_overlap_rejected(self):
        parts = self.joint_parts()
        parts[1]['replacements'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'CONFLICT'):
            merge_manifests(parts, self.manifest['release'])

    def test_joint_release_requires_prevalidated_whole_hash(self):
        with self.assertRaisesRegex(ValueError, 'validated joint release'):
            selection(self.joint_parts())

    def test_replacement_hash_tampering(self):
        bad = copy.deepcopy(self.manifest)
        bad['replacements'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            mod.validate_data(bad)

    def test_structural_checks_survive_python_optimization(self):
        code = ('from tools import mod; from tools.wem.fingerprint import stripped_setup; '
                'mod.validate_data(mod.load_manifest()); print("VALID"); '
                'stripped_setup(bytes(128), 1)')
        result = subprocess.run([sys.executable, '-O', '-B', '-c', code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('VALID', result.stdout)
        self.assertIn('nonzero trailing setup bits', result.stderr)

    def test_concurrent_operation_rejected(self):
        path = self.root / 'operation.lock'
        with transaction_lock(path):
            with self.assertRaises((OSError, ValueError)):
                with transaction_lock(path):
                    self.fail('Concurrent transaction acquired the lock')


@unittest.skipUnless(os.getenv('TWA_TEST_BASE_PACK'), 'Private canonical original required')
class InstallerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ['TWA_TEST_BASE_PACK']).resolve(strict=True)
        self.manifest = mod.load_manifest()
        self.assertEqual(mod.sha256(self.base), self.manifest['base']['sha256'])
        self.temp = tempfile.TemporaryDirectory(prefix='twa-installer-integration-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.game = self.folder / 'mock game'
        (self.game / 'data').mkdir(parents=True)
        self.target = self.game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, self.target)
        self.service = Installer(self.manifest, self.folder / 'state')
        self.processes = patch.object(deploy, 'assert_stopped')
        self.stopped = self.processes.start()
        self.addCleanup(self.processes.stop)

    def test_install_verify_backup_already_installed_restore(self):
        self.assertEqual(self.service.inspect(self.game)['state'], 'ORIGINAL')
        result = self.service.install(self.game)
        self.assertEqual((result['changed_entries'], result['unchanged_entries'], result['RSA']), (305, 16240, 'PASS'))
        backup = Path(result['backup'])
        meta = json.loads(backup.with_suffix('.json').read_text())
        self.assertEqual(meta['original_sha256'], self.manifest['base']['sha256'])
        self.assertEqual(Path(meta['game_path']), self.game)
        stamp = backup.stat().st_mtime_ns
        self.assertEqual(self.service.inspect(self.game)['state'], 'INSTALLED')
        self.assertEqual(self.service.install(self.game)['status'], 'ALREADY_INSTALLED')
        self.assertEqual(backup.stat().st_mtime_ns, stamp)
        self.assertEqual(self.service.restore(self.game)['status'], 'RESTORED')
        self.assertEqual(mod.sha256(self.target), self.manifest['base']['sha256'])
        self.service.install(self.game)
        self.assertEqual(backup.stat().st_mtime_ns, stamp)
        self.assertGreaterEqual(self.stopped.call_count, 8)

    def test_failed_build_validation_leaves_original_unchanged(self):
        def fail(base, output, manifest):
            Path(output).write_bytes(b'incomplete candidate')
            raise ValueError('Pack validation failed')
        with patch.object(mod, 'build', side_effect=fail), self.assertRaises(ValueError):
            self.service.install(self.game)
        self.assertEqual(mod.sha256(self.target), self.manifest['base']['sha256'])
        self.assertFalse(list(self.target.parent.glob('.twa-dubbing-*')))

    def test_missing_and_corrupted_backup_refused(self):
        self.service.install(self.game)
        _, _, backup = self.service.paths(self.game)
        backup.unlink()
        with self.assertRaisesRegex(ValueError, 'backup missing'):
            self.service.restore(self.game)
        backup.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.service.restore(self.game)
        self.assertEqual(mod.sha256(self.target), self.manifest['release']['sha256'])

    def test_process_start_before_replace_blocks_install(self):
        self.stopped.side_effect = [None, None, ValueError('Game/launcher is running')]
        with self.assertRaises(ValueError):
            self.service.install(self.game)
        self.assertEqual(mod.sha256(self.target), self.manifest['base']['sha256'])

    def test_target_change_during_build_preserved(self):
        original_build = mod.build
        def race(*args):
            result = original_build(*args)
            self.target.write_bytes(b'external concurrent change')
            return result
        with patch.object(mod, 'build', side_effect=race), self.assertRaises(ValueError):
            self.service.install(self.game)
        self.assertEqual(self.target.read_bytes(), b'external concurrent change')


if __name__ == '__main__':
    unittest.main()
