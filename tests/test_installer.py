"""Installer guards and full temporary-install transactions (never a real game)."""
import copy
from itertools import combinations
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
from tools.installer.backend import Installer, InstallerError, normalize_game_path, transaction_lock
from tools.installer.catalog import discover, known_manifests, merge_manifests, selection

# Validated changed-entry counts of every production selection that exists in this checkout.
EXPECTED_CHANGED = {'hannibal': 305, 'spartacus': 304, 'zhuge-liang': 293, 'hannibal+spartacus': 609,
                    'hannibal+zhuge-liang': 598, 'spartacus+zhuge-liang': 597,
                    'hannibal+spartacus+zhuge-liang': 902}


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
        for action in (self.service.install, self.service.restore):
            with patch.object(deploy, 'assert_stopped'), self.assertRaises(InstallerError) as caught:
                action(self.root)
            self.assertEqual(caught.exception.code, 'UNKNOWN_PACK')
            self.assertIsInstance(caught.exception, ValueError)
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
        (self.root / 'data').mkdir()
        target = self.root / 'data/audio_cn.pack'
        target.write_bytes(b'unchanged mock game file')
        with self.assertRaisesRegex(ValueError, 'CONFLICT'):
            selection(parts)
        self.assertEqual(target.read_bytes(), b'unchanged mock game file')

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

    def test_production_commanders_have_disjoint_validated_combinations(self):
        parts = discover()
        ids = [{s['media_id'] for s in p['replacements']} for p in parts]
        for left in range(len(ids)):
            for right in range(left + 1, len(ids)):
                self.assertFalse(ids[left] & ids[right], 'Production commanders overlap')
        # Every combination of production commanders has its own validated whole-PACK descriptor.
        self.assertEqual(len(known_manifests()), 2 ** len(parts) - 1)
        counts = {'+'.join(m.get('components', [m['commander']])): m['release']['changed_entries']
                  for m in known_manifests()}
        self.assertEqual(counts, {k: v for k, v in EXPECTED_CHANGED.items() if k in counts})
        self.assertEqual(set(counts) - set(EXPECTED_CHANGED), set())
        for manifest in known_manifests():
            self.assertEqual(mod.validate_data(manifest)['status'], 'PASS')

    def test_conflicting_production_payloads_abort_before_game_write(self):
        parts = [copy.deepcopy(p) for p in discover()]
        self.assertGreaterEqual(len(parts), 2)
        stolen = copy.deepcopy(parts[0]['replacements'][0])
        stolen['sha256'] = parts[-1]['replacements'][0]['sha256']
        parts[-1]['replacements'].append(stolen)
        (self.root / 'data').mkdir()
        target = self.root / 'data/audio_cn.pack'
        target.write_bytes(b'unchanged mock game file')
        with self.assertRaisesRegex(ValueError, 'CONFLICT'):
            selection(parts)
        self.assertEqual(target.read_bytes(), b'unchanged mock game file')

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
        with self.assertRaises(InstallerError) as caught:
            self.service.restore(self.game)
        self.assertEqual(caught.exception.code, 'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE')
        backup.write_bytes(b'corrupt')
        with self.assertRaises(InstallerError) as caught:
            self.service.restore(self.game)
        self.assertEqual(caught.exception.code, 'INVALID_BACKUP')
        self.assertEqual(mod.sha256(self.target), self.manifest['release']['sha256'])
        self.assertEqual(backup.read_bytes(), b'corrupt')

    # --- Backup-independent transitions -------------------------------------------------

    def selected(self, names):
        parts = {m['commander']: m for m in discover()}
        return selection([parts[n] for n in names])

    def put_state(self, names, target=None):
        """Place a known validated PACK as if an earlier, now-missing profile had installed it."""
        target = self.target if target is None else target
        target.unlink()
        if names:
            mod.build(self.base, target, self.selected(names))
        else:
            shutil.copyfile(self.base, target)
        return mod.sha256(target), target.stat().st_mtime_ns

    def assert_installed(self, names, result, count):
        manifest = self.selected(names)
        self.assertEqual((result['status'], result['sha256'], result['RSA'], result['changed_entries']),
                         ('INSTALLED', manifest['release']['sha256'], 'PASS', count))
        diff = mod.verify_pack(self.target, manifest, self.base)
        self.assertEqual((diff['changed_entries'], diff['diff_outside_allowed_payloads'],
                          diff['entry_count'], diff['RSA']), (count, 0, 16545, 'PASS'))
        observed = Installer(manifest, self.folder / 'observer').inspect(self.game)
        self.assertEqual(set(observed['installed_commanders']), set(names))

    def assert_refused(self, call, code, before):
        with self.assertRaises(InstallerError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual((mod.sha256(self.target), self.target.stat().st_mtime_ns), before)
        self.assertFalse(list(self.target.parent.glob('.twa-dubbing-*')))
        return caught.exception

    def no_backup(self, profile):
        return not list(Path(profile).rglob('*.pack'))

    def test_additive_h_to_hs_then_all_without_backup(self):
        h, s, z = (m['commander'] for m in discover())
        self.put_state((h,))
        profile = self.folder / 'fresh profile'
        state = Installer(self.selected((h, s)), profile).inspect(self.game)
        self.assertEqual((state['state'], state['changed_entries'], state['backup_state'], state['original_source']),
                         ('INSTALLED', 305, 'MISSING', None))
        with patch.object(Installer, 'restore', side_effect=AssertionError('Install called Restore')), \
                patch.object(mod, 'build', side_effect=AssertionError('Canonical build without an original')):
            result = Installer(self.selected((h, s)), profile).install(self.game)
            self.assertEqual(result['mode'], 'ADDITIVE')
            self.assert_installed((h, s), result, 609)
            result = Installer(self.selected((h, s, z)), profile).install(self.game)
            self.assertEqual(result['mode'], 'ADDITIVE')
            self.assert_installed((h, s, z), result, 902)
        self.assertTrue(self.no_backup(profile), 'A modified PACK became an original backup')

    def test_additive_single_to_all_and_other_supersets_without_backup(self):
        h, s, z = (m['commander'] for m in discover())
        for current, target, before, after in [((h,), (h, s, z), 305, 902), ((s,), (h, s), 304, 609),
                                               ((z,), (s, z), 293, 597), ((h,), (h, z), 305, 598)]:
            with self.subTest(current=current, target=target):
                self.put_state(current)
                self.assertEqual(mod.verify_pack(self.target, self.selected(current))['changed_entries'], before)
                profile = self.folder / ('fresh-' + '+'.join(current + target))
                result = Installer(self.selected(target), profile).install(self.game)
                self.assertEqual(result['mode'], 'ADDITIVE')
                self.assert_installed(target, result, after)
                self.assertTrue(self.no_backup(profile))

    def test_removal_without_original_source_is_refused_without_writes(self):
        h, s, z = (m['commander'] for m in discover())
        before = self.put_state((h, s, z))
        profile = self.folder / 'fresh profile'
        error = self.assert_refused(lambda: Installer(self.selected((s, z)), profile).install(self.game),
                                    'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL', before)
        self.assertIn('Cannot remove Hannibal because the original game audio backup is unavailable', str(error))
        self.assertEqual(mod.verify_pack(self.target, self.selected((h, s, z)))['changed_entries'], 902)
        self.assertTrue(self.no_backup(profile))

    def test_restore_without_original_source_is_refused_without_writes(self):
        h = discover()[0]['commander']
        before = self.put_state((h,))
        profile = self.folder / 'fresh profile'
        error = self.assert_refused(lambda: Installer(self.selected((h,)), profile).restore(self.game),
                                    'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE', before)
        self.assertIn('Original game audio is not available. Restore cannot be performed safely.', str(error))
        self.assertNotIn('Nothing was restored', str(error))
        self.assertTrue(self.no_backup(profile))

    def test_first_install_from_clean_original_creates_verified_backup(self):
        names = tuple(m['commander'] for m in discover())
        profile = self.folder / 'fresh profile'
        service = Installer(self.selected(names), profile)
        self.assertEqual(service.inspect(self.game)['original_source'], 'CURRENT_PACK')
        result = service.install(self.game)
        self.assertEqual((result['mode'], result['backup_created']), ('CANONICAL', True))
        self.assert_installed(names, result, 902)
        _, _, backup = service.paths(self.game)
        self.assertEqual((mod.sha256(backup), backup.stat().st_size, result['backup_size']),
                         (self.manifest['base']['sha256'], self.manifest['base']['size'], self.manifest['base']['size']))
        self.assertEqual(len(list(profile.rglob('*.pack'))), 1)
        self.assertEqual(service.inspect(self.game)['backup_state'], 'VALID')
        self.assertEqual(service.restore(self.game)['status'], 'RESTORED')
        self.assertEqual(mod.sha256(self.target), self.manifest['base']['sha256'])

    def test_canonical_game_file_is_recovered_as_backup_read_only(self):
        h, s, z = (m['commander'] for m in discover())
        self.put_state((h,))
        english = self.game / 'data/audio_en.pack'
        shutil.copyfile(self.base, english)
        english_state = (mod.sha256(english), english.stat().st_mtime_ns)
        profile = self.folder / 'fresh profile'
        state = Installer(self.selected((s,)), profile).inspect(self.game)
        self.assertEqual((state['backup_state'], state['original_source'], state['original_source_file']),
                         ('MISSING', 'GAME_FILE', 'data/audio_en.pack'))
        self.assertTrue(self.no_backup(profile), 'Inspect created a backup')
        # Removing Hannibal is possible only because a proven canonical source exists.
        result = Installer(self.selected((s,)), profile).install(self.game)
        self.assertEqual((result['mode'], result['backup_created'], result['backup_source']),
                         ('CANONICAL', True, 'data/audio_en.pack'))
        self.assert_installed((s,), result, 304)
        _, _, backup = Installer(self.manifest, profile).paths(self.game)
        self.assertEqual(mod.sha256(backup), self.manifest['base']['sha256'])
        meta = json.loads(backup.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['source'], 'data/audio_en.pack')
        self.assertEqual(Installer(self.manifest, profile).restore(self.game)['status'], 'RESTORED')
        self.assertEqual(mod.sha256(self.target), self.manifest['base']['sha256'])
        self.assertEqual((mod.sha256(english), english.stat().st_mtime_ns), english_state)
        # Restore directly from a modified state also recovers the game-file source first.
        self.put_state((h, z))
        second = self.folder / 'second fresh profile'
        self.assertEqual(Installer(self.manifest, second).restore(self.game)['status'], 'RESTORED')
        self.assertEqual(len(list(second.rglob('*.pack'))), 1)
        self.assertEqual((mod.sha256(english), english.stat().st_mtime_ns), english_state)

    def test_noncanonical_game_files_are_never_original_sources(self):
        h, s, _ = (m['commander'] for m in discover())
        before = self.put_state((h, s))
        english = self.game / 'data/audio_en.pack'
        shutil.copyfile(self.target, english)  # same size, known modded hash: never an original
        (self.game / 'data/audio_cn.pack.orig').write_bytes(b'not canonical')
        profile = self.folder / 'fresh profile'
        state = Installer(self.selected((s,)), profile).inspect(self.game)
        self.assertEqual(state['original_source'], None)
        self.assert_refused(lambda: Installer(self.selected((s,)), profile).install(self.game),
                            'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL', before)
        self.assert_refused(lambda: Installer(self.selected((s,)), profile).restore(self.game),
                            'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE', before)
        self.assertTrue(self.no_backup(profile))

    def test_invalid_backup_blocks_every_write_and_is_never_replaced(self):
        h = discover()[0]['commander']
        profile = self.folder / 'invalid profile'
        _, _, backup = Installer(self.manifest, profile).paths(self.game)
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'corrupt backup')
        for current in ((), (h,)):
            with self.subTest(current=current):
                before = self.put_state(current)
                state = Installer(self.manifest, profile).inspect(self.game)
                self.assertEqual((state['backup_state'], state['original_source']), ('INVALID', None))
                target = self.selected(tuple(m['commander'] for m in discover()))
                self.assert_refused(lambda: Installer(target, profile).install(self.game), 'INVALID_BACKUP', before)
                if current:
                    self.assert_refused(lambda: Installer(self.manifest, profile).restore(self.game),
                                        'INVALID_BACKUP', before)
                self.assertEqual(backup.read_bytes(), b'corrupt backup')

    def test_unknown_pack_is_never_patched_or_backed_up_even_with_original_sources(self):
        everything = self.selected(tuple(m['commander'] for m in discover()))
        shutil.copyfile(self.base, self.game / 'data/audio_en.pack')
        with self.target.open('r+b') as stream:
            stream.seek(everything['replacements'][0]['offset'])
            stream.write(b'\0' * 16)
        before = (mod.sha256(self.target), self.target.stat().st_mtime_ns)
        fresh, kept = self.folder / 'fresh profile', self.folder / 'kept profile'
        _, _, backup = Installer(self.manifest, kept).paths(self.game)
        backup.parent.mkdir(parents=True)
        shutil.copyfile(self.base, backup)
        stamp = backup.stat().st_mtime_ns
        for profile in (fresh, kept):
            self.assertEqual(Installer(everything, profile).inspect(self.game)['state'], 'UNSUPPORTED')
            self.assert_refused(lambda: Installer(everything, profile).install(self.game), 'UNKNOWN_PACK', before)
            self.assert_refused(lambda: Installer(everything, profile).restore(self.game), 'UNKNOWN_PACK', before)
        self.assertTrue(self.no_backup(fresh))
        self.assertEqual(backup.stat().st_mtime_ns, stamp)

    def test_additive_validation_failure_preserves_pack(self):
        h, s, _ = (m['commander'] for m in discover())
        before = self.put_state((h,))

        def reject(base, candidate, current, manifest):
            Path(candidate).write_bytes(b'incomplete additive candidate')
            raise ValueError('Injected additive validation failure')

        with patch.object(mod, 'build_additive', side_effect=reject):
            error = self.assert_refused(lambda: Installer(self.selected((h, s)), self.folder / 'p').install(self.game),
                                        'INSTALL_VALIDATION_FAILED', before)
        self.assertIn('Injected additive validation failure', str(error))

    def test_build_additive_requires_known_base_and_validated_target_hash(self):
        h, s, _ = (m['commander'] for m in discover())
        self.put_state((h,))
        current, target = self.selected((h,)), self.selected((h, s))
        output = self.folder / 'additive.pack'
        unvalidated = copy.deepcopy(target)
        unvalidated['release']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Unsupported PACK SHA-256'):
            mod.build_additive(self.target, output, current, unvalidated)
        with self.assertRaisesRegex(ValueError, 'not the verified installed state'):
            mod.build_additive(self.base, output, current, target)
        with self.assertRaisesRegex(ValueError, 'not a subset'):
            mod.build_additive(self.target, output, current, self.selected((s,)))
        self.assertFalse(output.exists() or list(self.folder.glob('*.partial')))
        result = mod.build_additive(self.target, output, current, target)
        self.assertEqual((result['sha256'], result['added_entries'], result['changed_entries'],
                          result['diff_outside_added_payloads']), (target['release']['sha256'], 304, 609, 0))

    def test_transition_matrix_with_and_without_backup(self):
        """Every known current state -> every target, with a canonical backup and with none."""
        names = tuple(m['commander'] for m in discover())
        states = [()] + [tuple(c) for n in range(1, len(names) + 1) for c in combinations(names, n)]
        rows, cache = [], self.folder / 'current-state.pack'
        backed = self.folder / 'matrix backup profile'
        service = Installer(self.manifest, backed)
        root, _, backup = service.paths(self.game)
        service.backup(root, self.base, backup)
        index = 0
        for current in states:
            cache.unlink(missing_ok=True)  # one cached state at a time keeps disk use bounded
            if current:
                mod.build(self.base, cache, self.selected(current))
            else:
                shutil.copyfile(self.base, cache)
            for has_backup in (True, False):
                for target in [*states[1:], 'RESTORE']:
                    index += 1
                    # Each backup-less row gets its own profile so no row can leak a backup into another.
                    profile = backed if has_backup else self.folder / f'matrix fresh profile {index}'
                    shutil.copyfile(cache, self.target)
                    before = (mod.sha256(self.target), self.target.stat().st_mtime_ns)
                    restoring = target == 'RESTORE'
                    manifest = self.manifest if restoring else self.selected(target)
                    allowed = has_backup or not current or (not restoring and set(current) <= set(target))
                    row = {'current': '+'.join(current) or 'original', 'target': '+'.join(target) if not restoring
                           else 'restore original', 'backup': 'present' if has_backup else 'missing'}
                    with self.subTest(**row):
                        if not has_backup:
                            self.addCleanup(shutil.rmtree, profile, True)
                        try:
                            call = Installer(manifest, profile).restore if restoring else Installer(manifest, profile).install
                            result = call(self.game)
                        except InstallerError as error:
                            self.assertFalse(allowed, str(error))
                            self.assertEqual(error.code, 'ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE' if restoring
                                             else 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')
                            self.assertEqual((mod.sha256(self.target), self.target.stat().st_mtime_ns), before)
                            row.update(allowed=False, actual_replacements=len(self.selected(current)['replacements']),
                                       result='SAFE REJECT ' + error.code, mode=None)
                        else:
                            self.assertTrue(allowed)
                            if restoring:
                                expected, count = self.manifest['base']['sha256'], 0
                                diff = mod.verify_pack(self.target, self.manifest, self.base)
                            else:
                                expected, count = manifest['release']['sha256'], len(manifest['replacements'])
                                diff = mod.verify_pack(self.target, manifest, self.base)
                            self.assertEqual((diff['sha256'], diff['changed_entries'], diff['RSA'], diff['entry_count'],
                                              diff['diff_outside_allowed_payloads']), (expected, count, 'PASS', 16545, 0))
                            if result['status'] in ('ALREADY_INSTALLED', 'ALREADY_ORIGINAL'):
                                self.assertEqual(self.target.stat().st_mtime_ns, before[1])
                            row.update(allowed=True, actual_replacements=count, result='PASS ' + result['status'],
                                       mode=result.get('mode'), backup_created=result.get('backup_created', False))
                        if not has_backup:
                            created = list(profile.rglob('*.pack'))
                            self.assertEqual(bool(created), bool(row.get('backup_created')))
                            for path in created:
                                self.assertEqual(mod.sha256(path), self.manifest['base']['sha256'])
                            shutil.rmtree(profile, ignore_errors=True)  # bound disk use; cleanup is a fallback
                        rows.append(row)
        self.assertEqual(mod.sha256(backup), self.manifest['base']['sha256'])
        self.assertEqual(len(rows), len(states) * len(states) * 2)
        self.assertEqual(sum(r['allowed'] for r in rows if r['backup'] == 'missing'),
                         sum(1 for c in states for t in [*states[1:], 'RESTORE']
                             if not c or (t != 'RESTORE' and set(c) <= set(t))))
        if os.getenv('TWA_TEST_MATRIX_REPORT'):
            Path(os.environ['TWA_TEST_MATRIX_REPORT']).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')

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

    def test_commander_selection_matrix(self):
        parts = {m['commander']: m for m in discover()}
        names = list(parts)
        self.assertEqual(names[:2], ['hannibal', 'spartacus'])
        ALL = tuple(names)
        subsets = [tuple(c) for n in range(1, len(names) + 1) for c in combinations(names, n)]

        def manifest(selected):
            return selection([parts[n] for n in selected])
        # Every path starts from a clean mock install; each arrow is an upgrade or a removal.
        scenarios = [[s, ALL, s] for s in subsets if s != ALL] + [[ALL]]
        newest = names[-1]
        if len(names) > 2:
            # Adding the newest commander next to each existing single installation.
            scenarios += [[(n,), tuple(x for x in names if x in (n, newest))] for n in names[:-1]]
        transitions = set()
        for index, steps in enumerate(scenarios):
            with self.subTest(steps=steps):
                game = self.folder / f'matrix-{index}'
                (game / 'data').mkdir(parents=True)
                target = game / 'data/audio_cn.pack'
                shutil.copyfile(self.base, target)
                state = self.folder / f'matrix-state-{index}'
                previous = ()
                for names in steps:
                    expected = manifest(names)
                    service = Installer(expected, state)
                    result = service.install(game)
                    self.assertEqual((result['sha256'], result['RSA'], result['changed_entries']),
                                     (expected['release']['sha256'], 'PASS', len(expected['replacements'])))
                    observed = service.inspect(game)
                    self.assertEqual((observed['state'], observed['sha256'], observed['RSA']),
                                     ('INSTALLED', expected['release']['sha256'], 'PASS'))
                    self.assertEqual(set(observed['installed_commanders']), set(names))
                    # Full byte diff against the canonical original: absent commanders stay original.
                    diff = mod.verify_pack(target, expected, self.base)
                    self.assertEqual((diff['changed_entries'], diff['diff_outside_allowed_payloads']),
                                     (len(expected['replacements']), 0))
                    transitions.add((previous, names))
                    previous = names
                self.assertEqual(service.restore(game)['status'], 'RESTORED')
                self.assertEqual(service.inspect(game)['state'], 'ORIGINAL')
                self.assertEqual(mod.sha256(target), parts[names[0]]['base']['sha256'])
        required = ({((), s) for s in subsets} | {(s, ALL) for s in subsets if s != ALL}
                    | {(ALL, s) for s in subsets if s != ALL})
        self.assertLessEqual(required, transitions)

    def test_unknown_modified_pack_is_never_patched(self):
        everything = selection(discover())
        with self.target.open('r+b') as stream:
            spec = everything['replacements'][0]
            stream.seek(spec['offset'])
            stream.write(b'\0' * 16)
        before = mod.sha256(self.target)
        service = Installer(everything, self.folder / 'state-unknown')
        self.assertEqual(service.inspect(self.game)['state'], 'UNSUPPORTED')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            service.install(self.game)
        self.assertEqual(mod.sha256(self.target), before)
        self.assertFalse(list((self.folder / 'state-unknown').rglob('*.pack')))


if __name__ == '__main__':
    unittest.main()
