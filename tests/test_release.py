"""Manifest-driven release builder gates and deterministic packaging, without PyInstaller or a game."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import mod, release
from tools.installer.catalog import discover, discover_all, discover_shared

COUNTS = {'hannibal': 305, 'spartacus': 304, 'zhuge-liang': 293, 'leonidas': 257}
UNIT, UNIT_COUNT = 'unit-voices', 465
ACTIVE = bool(discover_shared())  # a staged shared module never ships
COMMANDER_JOINTS = [550, 561, 562, 597, 598, 609, 854, 855, 866, 902, 1159]


class ReleaseBuilderTests(unittest.TestCase):
    def test_release_identity_is_v1_4_0(self):
        self.assertEqual(release.VERSION, '1.4.0')
        self.assertEqual(release.NAME, 'TWA-Czech-Dubbing-v1.4.0-win64')
        self.assertEqual(release.EXE, 'TWA-Czech-Dubbing-Installer.exe')

    def test_every_production_commander_and_combination_ships(self):
        manifests, joints = release.release_manifests()
        self.assertEqual([m['commander'] for m in manifests], list(COUNTS) + [UNIT] * ACTIVE)
        self.assertEqual(len(joints), 26 if ACTIVE else 11)
        # Commander joints, then every commander selection plus the shared unit voices.
        with_unit = [n + UNIT_COUNT for n in [*COUNTS.values(), *COMMANDER_JOINTS]] if ACTIVE else []
        self.assertEqual(sorted(len(j['replacements']) for j in joints), sorted(COMMANDER_JOINTS + with_unit))
        self.assertEqual(set(release.joint_keys(manifests)),
                         {p.stem for p in (mod.ROOT / 'data/releases').glob('*.json')})

    def test_payload_contains_exactly_the_production_data_and_wems(self):
        manifests = discover_all()
        files = release.payload_files(manifests)
        wems = [p for p in files if p.suffix == '.wem']
        self.assertEqual(len(wems), 1159 + UNIT_COUNT * ACTIVE)
        for name, count in {**COUNTS, **({UNIT: UNIT_COUNT} if ACTIVE else {})}.items():
            folder = Path('data/shared' if name == UNIT else 'data/commanders') / name
            ours = {p.name for p in wems if p.parts[1] == name}
            self.assertEqual(len(ours), count, name)
            self.assertEqual(ours, {p.name for p in (mod.ROOT / 'replacements' / name / 'wem').iterdir()})
            for data in ('manifest.json', 'voice-lines.csv', 'media-inventory.csv'):
                self.assertIn(folder / data, files)
            self.assertNotIn(folder / 'audio-qa.json', files)
        self.assertFalse([p for p in files if p.parts[:3] == ('data', 'shared', 'unit-acknowledgements')])
        joints = 26 if ACTIVE else 11
        self.assertEqual(len([p for p in files if p.parent == Path('data/releases')]), joints)
        self.assertEqual(len(files), 1 + joints + (4 + ACTIVE) * 3 + 1159 + UNIT_COUNT * ACTIVE)
        self.assertFalse([p for p in files if 'staged' in p.name or p.suffix in ('.pack', '.orig', '.bnk')])

    def test_readme_lists_commanders_in_installer_order(self):
        text = release.readme_text(discover())
        self.assertTrue(text.startswith('Total War: Arena - Czech Dubbing 1.4.0\n'))
        self.assertIn('Commanders: Hannibal (305 lines), Spartacus (304 lines), Zhuge Liang (293 lines), '
                      'Leonidas (257 lines).', text)
        self.assertNotIn('Univerzální', text)
        if ACTIVE:
            text = release.readme_text(discover_all())
            self.assertIn('Leonidas (257 lines).\nOptional shared module: Univerzální hlášky - Český dabing obecných '
                          'hlášek jednotek (465 lines; male and female unit voices together', text)
        self.assertNotIn('Install.bat', text)

    def test_builder_fails_closed_on_inconsistent_metadata(self):
        parts = discover()
        with patch.object(release, 'discover_all', return_value=parts[:3]), \
                self.assertRaisesRegex(ValueError, 'Joint descriptors do not match'):
            release.release_manifests()
        stale = copy.deepcopy(parts)
        stale[-1]['version'] = '1.2.0'
        with patch.object(release, 'discover_all', return_value=stale), \
                self.assertRaisesRegex(ValueError, 'version metadata'):
            release.release_manifests()
        with patch.object(release, 'discover_all', return_value=[]), self.assertRaisesRegex(ValueError, 'No production'):
            release.release_manifests()

    def test_deterministic_zip_is_byte_identical(self):
        with tempfile.TemporaryDirectory(prefix='twa-release-zip-') as temp:
            folder = Path(temp) / release.NAME
            (folder / 'payload/data').mkdir(parents=True)
            (folder / 'README.txt').write_text('readme', encoding='utf-8')
            (folder / 'payload/data/file.json').write_text('{}', encoding='utf-8')
            first, second = Path(temp) / 'first.zip', Path(temp) / 'second.zip'
            release.deterministic_zip(folder, first)
            (folder / 'README.txt').touch()  # timestamps must not leak into the archive
            release.deterministic_zip(folder, second)
            self.assertEqual(mod.sha256(first), mod.sha256(second))


if __name__ == '__main__':
    unittest.main()
