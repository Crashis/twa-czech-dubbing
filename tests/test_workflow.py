"""Safety regressions; optional full PACK transaction tests use local copies only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy, mod
from tools.pack.reader import ArenaPack
from tools.pack.signature import load_key, verify
from tools.wem.exact_size import chunks, pad
from tools.validation.repository import audit
from tools.inventory.names import fnv1, branch_trie, match_branch
from tools.inventory.voice_map import resolve_bank


class CanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = mod.load_manifest()

    def test_all_canonical_data(self):
        result = mod.validate_data(self.manifest)
        self.assertEqual((result['replacement_wems'], result['metadata_rows'], result['silent_placeholders']), (305, 305, 16))

    def test_manifest_tamper_rejected(self):
        changed = copy.deepcopy(self.manifest)
        changed['replacements'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            mod.validate_data(changed)

    def test_silent_or_shared_id_rejected(self):
        changed = copy.deepcopy(self.manifest)
        changed['silent_placeholder_ids'].append(changed['replacements'][0]['media_id'])
        with self.assertRaises(ValueError):
            mod.validate_data(changed)

    def test_commander_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            mod.load_manifest('../hannibal')

    def test_name_and_wildcard_analysis(self):
        self.assertEqual(fnv1('Commander_Hannibal'), 936285215)
        branches = [{'keys': [{'value': '7'}], 'target': {'value': '10'}},
                    {'keys': [{'value': '0'}], 'target': {'value': '11'}}]
        trie = branch_trie(branches)
        self.assertEqual(match_branch(trie, [7]), 0)
        self.assertEqual(match_branch(trie, [99]), 1)

    def test_ordinary_event_and_unreferenced_sound_are_retained(self):
        sound = {'id': 3, 'type': 'CAkSound', 'sourceID': [{'value': '42'}],
                 'ulPluginID': [{'value': '262145'}], 'children': []}
        info = {'nodes': [{'id': 1, 'type': 'CAkEvent', 'actions': [{'value': '2'}]},
                          {'id': 2, 'type': 'CAkActionPlay', 'target': [{'value': '3'}]}, sound]}
        rows = resolve_bank('test.bnk', info)
        self.assertEqual({r['event_type'] for r in rows}, {'Event', 'SoundReference'})
        self.assertTrue(all(r['media_id'] == 42 and r['ownership'] == 'UNREVIEWED' for r in rows))

    def test_junk_preserves_codec_chunks(self):
        raw = b'RIFF' + b'\0' * 4 + b'WAVE' + b'fmt ' + struct.pack('<I', 2) + b'xx' + b'data' + struct.pack('<I', 3) + b'abc\0'
        raw = raw[:4] + struct.pack('<I', len(raw) - 8) + raw[8:]
        result = pad(raw, len(raw) - 1 + 12)
        self.assertEqual(chunks(result)[b'data'][1], b'abc')
        self.assertEqual(chunks(result)[b'fmt '][1], b'xx')
        with self.assertRaises(ValueError):
            pad(raw, 10)
        with self.assertRaises(ValueError):
            pad(raw, len(raw))  # one-byte gap after terminal normalization

    def test_secret_audit_does_not_expose_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            value = 'test-sensitive-value-' + 'z' * 30
            (root / '.env').write_text('ELEVENLABS_API_KEY=' + value)
            (root / 'example.txt').write_text(value)
            result = audit(root)
            self.assertEqual(result['secret_scan'], 'SECRET SCAN FAIL')
            self.assertNotIn(value, json.dumps(result))
            self.assertEqual(result['secret_finding_files'], ['example.txt'])


@unittest.skipUnless(os.getenv('TWA_TEST_BASE_PACK'), 'Set TWA_TEST_BASE_PACK to a canonical local backup for full integration tests')
class PackIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(os.environ['TWA_TEST_BASE_PACK']).resolve(strict=True)
        cls.manifest = mod.load_manifest()
        if mod.sha256(cls.base) != cls.manifest['base']['sha256']:
            raise ValueError('Test base is unsupported; game files will never be used as output')
        cls.temp = tempfile.TemporaryDirectory(prefix='twa-cleanup-tests-', dir=os.getenv('TWA_TEST_OUTPUT_ROOT'))
        cls.root = Path(cls.temp.name)
        cls.output = cls.root / 'reproduced.pack'
        cls.result = mod.build(cls.base, cls.output, cls.manifest)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_byte_identical_complete_pack(self):
        self.assertEqual(self.result['sha256'], self.manifest['release']['sha256'])
        self.assertEqual((self.result['changed_entries'], self.result['unchanged_entries']), (305, 16240))
        self.assertEqual(self.result['RSA'], 'PASS')

    def test_existing_output_and_in_place_refused(self):
        with self.assertRaises(ValueError):
            mod.build(self.base, self.output, self.manifest)
        with self.assertRaises(ValueError):
            mod.build(self.base, self.base, self.manifest)

    def test_unknown_base_refused_before_output(self):
        bad = self.root / 'unsupported.pack'
        bad.write_bytes(b'unsupported')
        output = self.root / 'must-not-exist.pack'
        with self.assertRaises(ValueError):
            mod.build(bad, output, self.manifest)
        self.assertFalse(output.exists())

    def test_modified_pack_is_never_a_build_base(self):
        with self.assertRaises(ValueError):
            mod.build(self.output, self.root / 'incremental.pack', self.manifest)

    def test_rsa_tampering_refused(self):
        original = ArenaPack(self.base)
        self.assertTrue(verify(original.index_raw, original.appendix, *load_key()))
        changed = bytearray(original.index_raw)
        changed[0] ^= 1
        self.assertFalse(verify(changed, original.appendix, *load_key()))
        signature = bytearray(original.appendix)
        signature[-1] ^= 1
        self.assertFalse(verify(original.index_raw, signature, *load_key()))

    def test_install_restore_transaction_and_guards(self):
        game = self.root / 'mock game with spaces'
        (game / 'data').mkdir(parents=True)
        target = game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, target)
        with patch.object(deploy, 'assert_stopped'):
            before = {p.relative_to(game).as_posix() for p in game.rglob('*')}
            deploy.install(game, self.manifest, dry_run=True)
            self.assertEqual(before, {p.relative_to(game).as_posix() for p in game.rglob('*')})
            self.assertEqual(mod.sha256(target), self.manifest['base']['sha256'])
            deploy.install(game, self.manifest)
            self.assertEqual(mod.sha256(target), self.manifest['release']['sha256'])
            self.assertEqual(deploy.install(game, self.manifest)['status'], 'ALREADY_INSTALLED')
            _, _, _, backup = deploy.game_paths(game, self.manifest)
            saved = backup.with_suffix('.saved')
            backup.rename(saved)
            with self.assertRaises(ValueError):
                deploy.restore(game, self.manifest)
            self.assertEqual(mod.sha256(target), self.manifest['release']['sha256'])
            saved.rename(backup)
            deploy.restore(game, self.manifest, dry_run=True)
            self.assertEqual(mod.sha256(target), self.manifest['release']['sha256'])
            self.assertEqual(deploy.restore(game, self.manifest)['status'], 'RESTORED')
            self.assertEqual(mod.sha256(target), self.manifest['base']['sha256'])
            self.assertEqual(mod.sha256(backup), self.manifest['base']['sha256'])

    def test_running_process_blocks_writes(self):
        game = self.root / 'blocked mock game'
        (game / 'data').mkdir(parents=True)
        target = game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, target)
        with patch.object(deploy, 'assert_stopped', side_effect=ValueError('Game/launcher is running')):
            with self.assertRaises(ValueError):
                deploy.install(game, self.manifest)
        self.assertEqual(mod.sha256(target), self.manifest['base']['sha256'])
        self.assertFalse((game / '.twa-czech-dubbing').exists())

    def test_corrupted_backup_and_target_race_are_refused(self):
        game = self.root / 'race mock'
        (game / 'data').mkdir(parents=True)
        target = game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, target)
        _, _, _, backup = deploy.game_paths(game, self.manifest)
        with patch.object(deploy, 'assert_stopped'):
            deploy.ensure_backup(target, backup, self.manifest)
            saved = backup.read_bytes()
            backup.write_bytes(b'corrupt backup')
            with self.assertRaises(ValueError):
                deploy.install(game, self.manifest)
            self.assertEqual(mod.sha256(target), self.manifest['base']['sha256'])
            backup.write_bytes(saved)
            def concurrent_change(*args):
                result = mod.build(*args)
                target.write_bytes(b'concurrent external modification')
                return result
            with patch.object(deploy, 'build', side_effect=concurrent_change):
                with self.assertRaises(ValueError):
                    deploy.install(game, self.manifest)
            self.assertEqual(target.read_bytes(), b'concurrent external modification')
            self.assertEqual(mod.sha256(backup), self.manifest['base']['sha256'])

    @unittest.skipUnless(os.name == 'nt', 'PowerShell wrappers run on Windows')
    def test_real_powershell_wrappers_on_mock(self):
        game = self.root / 'powershell mock game'
        (game / 'data').mkdir(parents=True)
        target = game / 'data/audio_cn.pack'
        shutil.copyfile(self.base, target)
        for script, extra in [('install', ['-WhatIf']), ('verify', []), ('install', []), ('verify', []),
                              ('restore', ['-DryRun']), ('restore', []), ('verify', [])]:
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(mod.ROOT / f'scripts/{script}.ps1'), '-GamePath', str(game),
                                     '-PythonExecutable', sys.executable, *extra], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if extra:
                self.assertIn('DRY_RUN_PASS', result.stdout)
        self.assertEqual(mod.sha256(target), self.manifest['base']['sha256'])


if __name__ == '__main__':
    unittest.main()
