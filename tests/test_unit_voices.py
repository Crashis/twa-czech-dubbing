"""Shared unit voices (Univerzální hlášky): plan routing, one installer module, mock installs only.

The module data is checked whether it is staged or active; installer behaviour is tested once it is active.
"""
import copy
import csv
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools import deploy, mod
from tools.installer.backend import Installer, InstallerError
from tools.installer.catalog import discover, discover_all, discover_shared, known_manifests, selection
from tools.tts import units
from tools.tts.production import DEFERRED, items_from_plan
from tools.tts.pronunciation import Resolver, ReviewRequired, unit_resolver
from tools.wem.promote import STAGED, load_unit

UNIT = 'unit-voices'
FOLDER = mod.ROOT / 'data/shared' / UNIT
ACTIVE, STAGED_SET = (FOLDER / 'manifest.json').is_file(), (FOLDER / STAGED).is_file()
# 465 reachable IDs, all replaced: Falxy approved, 5 compact sources, 10 byte-budget fallback lines.
REPLACED, FALXY_IDS, PRONUNCIATION_IDS, NO_WEM_IDS = 465, 6, 0, 0
GROUPS = {'CZ_UNIT_MALE': ('Units Male CZ', 'w1mDmAXaMBkdpEOg9E7B', 395),
          'CZ_UNIT_FEMALE': ('Units Women CZ', 'sIwXy4sPJTVqdHS9lRt8', 70)}
FALLBACKS = {'Jdeme!': 9, 'Hotovi!': 1}
COMMANDER_IDS = 1159  # v1.3.0 Hannibal + Spartacus + Zhuge Liang + Leonidas
ALL_COMMANDER_IDS = 1888  # v1.5.0 adds Scipio Africanus, Germanicus and Julius Caesar


def routing(folder):
    path = Path(folder) / 'routing.csv'
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, units.ROUTING_FIELDS)
        writer.writeheader()
        writer.writerows(units.routing_rows())
    return path


def modules(*names):
    by_id = {m['commander']: m for m in discover_all()}
    return selection([by_id[name] for name in names])


class UnitPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-unit-plan-')
        self.addCleanup(self.temp.cleanup)
        self.routing = routing(self.temp.name)

    def test_voice_groups_cover_scope_once_with_gender_forms(self):
        plans = {g: units.load_unit_plan(g, self.routing) for g in units.GROUPS}
        self.assertEqual({g: (len(p[0]), p[3]) for g, p in plans.items()},
                         {'CZ_UNIT_MALE': (29, 395), 'CZ_UNIT_FEMALE': (15, 70)})
        members = [m for p in plans.values() for row in p[0] for m in row['member_media_ids'].split(';')]
        self.assertEqual(len(members), len(set(members)), 465)
        texts = {g: {row['czech_text'] for row in p[0]} for g, p in plans.items()}
        for male, female in (('Připraveni!', 'Připraveny!'), ('Připraveni k boji!', 'Připraveny k boji!'),
                             ('Nedočkaví!', 'Nedočkavé!'), ('Lučištníci!', 'Lučištnice!')):
            with self.subTest(male=male):
                self.assertIn(male, texts['CZ_UNIT_MALE'])
                self.assertNotIn(male, texts['CZ_UNIT_FEMALE'])
                self.assertIn(female, texts['CZ_UNIT_FEMALE'])
                self.assertNotIn(female, texts['CZ_UNIT_MALE'])
        self.assertTrue(all(route['selected_model'] == 'eleven_v4' for p in plans.values() for route in p[1].values()))

    def test_slot_of_the_other_gender_is_rejected(self):
        # Only China's proven byte-identical male copies may sit in another slot gender's group.
        media = mod.csv_rows(units.MEDIA_PATH)
        female = next(r for r in media if r['voice_gender'] == 'female' and r['vo_cultures'] != 'China')
        tampered = [dict(r, voice_gender='male', vo_actors=r['vo_actors'].replace('Female_', 'Male_'))
                    if r is female else r for r in media]
        with patch.object(units, 'read_csv', side_effect=lambda p: tampered if Path(p) == units.MEDIA_PATH
                          else mod.csv_rows(p)), self.assertRaisesRegex(RuntimeError, 'outside voice group|cover'):
            units.load_unit_plan('CZ_UNIT_FEMALE', self.routing)

    def test_unapproved_override_defers_only_its_performance(self):
        plan, routes, _, _ = units.load_unit_plan('CZ_UNIT_MALE', self.routing)
        review = Resolver([dict(r, status='PROPOSED_VERIFY_IN_PILOT') for r in unit_resolver().rules])
        with self.assertRaises(ReviewRequired):
            items_from_plan(plan, routes, Path('work/x'), 'voice', pronunciation=review)
        items = items_from_plan(plan, routes, Path('work/x'), 'voice', pronunciation=review, defer_review=True)
        deferred = {k for k, v in items.items() if v['status'] == DEFERRED}
        self.assertEqual(deferred, {'male-falxes'})
        self.assertIsNone(items['male-falxes']['request_text'])
        self.assertEqual(len(items['male-falxes']['member_media_ids']), FALXY_IDS)
        # The real rule is approved (user decision 2026-10-22): production sends Falksy!, keeps Falxy!.
        self.assertEqual([r['status'] for r in unit_resolver().rules], ['APPROVED'])
        items = items_from_plan(plan, routes, Path('work/x'), 'voice', pronunciation=unit_resolver())
        falx = items['male-falxes']
        self.assertEqual((falx['status'], falx['canonical_text'], falx['tts_input_text']), ('planned', 'Falxy!', 'Falksy!'))
        self.assertEqual(falx['applied_pronunciation_overrides'][0]['tts'], 'Falksy')


@unittest.skipUnless(ACTIVE or STAGED_SET, 'Unit voice production set not promoted')
class UnitDataTests(unittest.TestCase):
    def test_validation_male_female_bundled_and_no_commander_overlap(self):
        unit = load_unit(not ACTIVE)
        result = mod.validate_data(unit)
        self.assertEqual((result['status'], result['commander_overlap'], result['voice_groups']),
                         ('PASS', 0, {g: v[2] for g, v in GROUPS.items()}))
        self.assertEqual({g: (v['voice_name'], v['voice_id'], v['media_ids']) for g, v in unit['voice_groups'].items()}, GROUPS)
        ids = {s['media_id'] for s in unit['replacements']}
        commander_ids = {s['media_id'] for m in discover() for s in m['replacements']}
        self.assertEqual(len(commander_ids), ALL_COMMANDER_IDS)
        self.assertFalse(ids & commander_ids)
        reasons = [r.split(':')[0] for r in unit['deferred_reason'].values()]
        self.assertEqual((len(ids), reasons.count('PRONUNCIATION_REVIEW'), reasons.count('NO_EXACT_SIZE_WEM')),
                         (REPLACED, PRONUNCIATION_IDS, NO_WEM_IDS))
        self.assertFalse(ids & set(unit['deferred_media_ids']))
        self.assertEqual(len(ids) + len(unit['deferred_media_ids']), 465)
        # Byte-budget fallback lines only where approved; every other ID keeps the canonical Czech line.
        rows = mod.csv_rows(FOLDER / 'voice-lines.csv')
        fallback = [r for r in rows if r['translation_status'] == units.FALLBACK_REASON]
        approved = {r['media_id']: r for r in mod.csv_rows(units.FALLBACK_PATH)}
        self.assertEqual({r['media_id'] for r in fallback}, set(approved))
        self.assertEqual({t: sum(r['czech'] == t for r in fallback) for t in FALLBACKS}, FALLBACKS)
        self.assertTrue(all(r['canonical_plan_czech'] == approved[r['media_id']]['canonical_plan_czech']
                            and r['english'] == approved[r['media_id']]['english'] for r in fallback))
        self.assertTrue(all(r['czech'] == r['canonical_plan_czech'] for r in rows if r not in fallback))
        bad = copy.deepcopy(unit)
        bad['voice_groups']['CZ_UNIT_FEMALE']['voice_id'] = GROUPS['CZ_UNIT_MALE'][1]
        with self.assertRaisesRegex(ValueError, 'Voice group routing'):
            mod.validate_data(bad)

    @unittest.skipIf(ACTIVE, 'Unit voices are an active installer module')
    def test_staged_set_is_invisible_to_the_installer(self):
        self.assertEqual(discover_shared(), [])
        self.assertEqual(len(known_manifests()), 15)
        with self.assertRaises(FileNotFoundError):
            mod.load_manifest(UNIT)


@unittest.skipUnless(ACTIVE, 'Unit voices are staged, not an installer module yet')
class UnitModuleTests(unittest.TestCase):
    def test_single_independent_shared_module(self):
        self.assertNotIn(UNIT, [m['commander'] for m in discover()])
        shared = discover_shared()
        self.assertEqual([m['commander'] for m in shared], [UNIT])
        unit = shared[0]
        self.assertEqual((unit['display_name'], unit['description']),
                         ('Univerzální hlášky', 'Český dabing obecných hlášek jednotek'))
        self.assertTrue(mod.is_shared(unit))
        # One module: male and female payloads together, never two user-selectable parts.
        self.assertEqual(set(unit['voice_groups']), set(GROUPS))
        self.assertEqual(unit['replacement_count'], REPLACED)
        self.assertEqual(len([m for m in discover_all() if m['commander'].startswith('unit')]), 1)

    def test_every_selection_with_unit_voices_has_a_validated_hash(self):
        known = known_manifests()
        self.assertEqual(len(known), 255)  # 7 commanders + unit voices: every non-empty selection
        self.assertEqual(len({m['release']['sha256'] for m in known}), 255)
        unit = mod.load_manifest(UNIT)
        joint = modules('hannibal', 'leonidas', 'spartacus', 'zhuge-liang', UNIT)
        self.assertEqual(len(joint['replacements']), joint['release']['changed_entries'], COMMANDER_IDS + REPLACED)
        self.assertNotIn('module_type', joint)
        self.assertEqual(joint['display_name'], 'Hannibal + Spartacus + Zhuge Liang + Leonidas + Univerzální hlášky')
        tail = modules(UNIT, 'zhuge-liang')  # the shared module sorts first in this key
        self.assertFalse(mod.is_shared(tail))
        self.assertEqual(tail['components'], [UNIT, 'zhuge-liang'])
        self.assertEqual(selection([unit]), unit)


@unittest.skipUnless(os.name == 'nt' and ACTIVE, 'Windows Tk and an active unit voice module required')
class UnitCheckboxTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tools.installer import gui
        self.temp = tempfile.TemporaryDirectory(prefix='twa-unit-gui-')
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

    def test_one_checkbox_changes_only_pending_state(self):
        self.assertEqual(len(self.app.shared_checks), 1)
        self.assertEqual(len(self.app.checks), 7)
        self.assertTrue(self.app.shared_checks[0]['text'].startswith('Univerzální hlášky'))
        self.app.accept_verified_state(dict(state='INSTALLED', installed_commanders=['hannibal'], backup_state='MISSING',
                                            original_source=None, original_source_file=None))
        self.app.controls()
        self.app.shared_checks[0].invoke()
        self.assertEqual(self.app.pending_commanders, frozenset({'hannibal', UNIT}))
        self.assertEqual(self.app.installed_commanders, frozenset({'hannibal'}))
        self.assertEqual(self.app.selected()['components'], ['hannibal', UNIT])
        self.assertEqual(str(self.app.install_button['state']), 'normal')
        self.assertIn('Pending: Hannibal + Univerzální hlášky', self.app.selection_status.get())
        self.service.assert_not_called()
        # Unit voices only: no commander needed.
        self.app.checks[0].invoke()
        self.assertEqual(self.app.selected()['commander'], UNIT)
        # Removing installed unit voices needs an original source; without one Install stays disabled.
        self.app.accept_verified_state(dict(state='INSTALLED', installed_commanders=['hannibal', UNIT],
                                            backup_state='MISSING', original_source=None, original_source_file=None))
        self.app.shared_checks[0].invoke()
        self.assertEqual(str(self.app.install_button['state']), 'disabled')
        self.assertIn('Univerzální hlášky', self.app.selection_status.get())
        self.service.assert_not_called()


@unittest.skipUnless(os.getenv('TWA_TEST_BASE_PACK') and ACTIVE, 'Private canonical original and active module required')
class UnitInstallTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ['TWA_TEST_BASE_PACK']).resolve(strict=True)
        self.unit = mod.load_manifest(UNIT)
        self.assertEqual(mod.sha256(self.base), self.unit['base']['sha256'])
        self.temp = tempfile.TemporaryDirectory(prefix='twa-unit-install-')
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

    def test_unit_only_then_commanders_additive_then_removal_keeps_commanders(self):
        profile = self.folder / 'profile'
        result = Installer(self.unit, profile).install(self.game)
        self.assertEqual((result['mode'], result['backup_created'], result['changed_entries']), ('CANONICAL', True, REPLACED))
        self.assert_state((UNIT,), result)
        everything = ('hannibal', 'leonidas', 'spartacus', 'zhuge-liang', UNIT)
        result = Installer(modules(*everything), profile).install(self.game)
        self.assert_state(everything, result)
        self.assertEqual(result['changed_entries'], COMMANDER_IDS + REPLACED)
        # Untick unit voices + Install: canonical rebuild from the backup keeps every commander payload.
        result = Installer(modules(*everything[:-1]), profile).install(self.game)
        self.assertEqual(result['mode'], 'CANONICAL')
        self.assert_state(everything[:-1], result)
        self.assertEqual(mod.sha256(self.target), modules(*everything[:-1])['release']['sha256'])
        self.assertEqual(len(list(profile.rglob('*.pack'))), 1)
        self.assertEqual(Installer(self.unit, profile).restore(self.game)['status'], 'RESTORED')
        self.assertEqual(mod.sha256(self.target), self.unit['base']['sha256'])

    def test_added_to_installed_commander_without_backup_and_removal_refused(self):
        mod.build(self.base, self.folder / 'h.pack', modules('hannibal'))
        os.replace(self.folder / 'h.pack', self.target)
        profile = self.folder / 'no backup'
        with patch.object(mod, 'build', side_effect=AssertionError('Canonical build without an original')):
            result = Installer(modules('hannibal', UNIT), profile).install(self.game)
        self.assertEqual(result['mode'], 'ADDITIVE')
        self.assert_state(('hannibal', UNIT), result)
        self.assertFalse(list(profile.rglob('*.pack')))
        before = mod.sha256(self.target)
        for target in (('hannibal',), (UNIT,)):
            with self.subTest(remove_from=target), self.assertRaises(InstallerError) as caught:
                Installer(modules(*target), profile).install(self.game)
            self.assertEqual(caught.exception.code, 'ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL')
            self.assertEqual(mod.sha256(self.target), before)

    def test_unknown_pack_is_never_patched_with_unit_voices(self):
        data = bytearray(self.target.read_bytes())
        spec = self.unit['replacements'][0]
        data[spec['offset'] + 100] ^= 0xFF
        self.target.write_bytes(bytes(data))
        before = mod.sha256(self.target)
        for selected in (self.unit, modules('hannibal', UNIT)):
            with self.subTest(selected=selected['commander']), self.assertRaises(InstallerError) as caught:
                Installer(selected, self.folder / 'profile').install(self.game)
            self.assertEqual(caught.exception.code, 'UNKNOWN_PACK')
        self.assertEqual(mod.sha256(self.target), before)
        self.assertFalse(list((self.folder / 'profile').rglob('*.pack')))


if __name__ == '__main__':
    unittest.main()
