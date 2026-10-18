"""Cross-commander safety regressions over every research inventory and the Hannibal release."""
from collections import defaultdict
import hashlib
import json
import unittest

from tools.inventory.research_metadata import read_csv, validate_research
from tools.installer.catalog import discover
from tools.mod import load_manifest
from tools.resources import ROOT
from tools.tts.research_plan import V3_STYLES, english_key, read_memory

COMMANDERS = ROOT/'data/commanders'
AUDIO_SUFFIXES = {'.wem', '.wav', '.pack', '.bnk', '.ogg', '.mp3', '.flac', '.orig'}


def research_names():
    return sorted(p.parent.parent.name for p in COMMANDERS.glob('*/research/manifest-draft.json'))


def safe_flag(name, row):
    return row.get('safe_to_replace_for_commander') or row.get('safe_to_replace_for_' + name, '')


def inventories():
    result = {name: {r['media_id']: r for r in read_csv(COMMANDERS/name/'research/voice-lines.csv')}
              for name in research_names()}
    result['hannibal'] = {r['media_id']: r for r in read_csv(COMMANDERS/'hannibal/media-inventory.csv')}
    return result


class CommanderResearchSafetyTests(unittest.TestCase):
    def test_every_research_inventory_validates(self):
        names = research_names()
        self.assertTrue({'leonidas', 'scipio-africanus', 'spartacus', 'germanicus'} <= set(names))
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(validate_research(COMMANDERS/name/'research', name)['status'], 'PASS')

    def test_unique_ids_and_safe_ids_never_reach_another_inventory(self):
        data = inventories()
        safe = {name: {mid for mid, row in rows.items() if safe_flag(name, row) == 'YES'} for name, rows in data.items()}
        for name in research_names():
            rows = read_csv(COMMANDERS/name/'research/voice-lines.csv')
            self.assertEqual(len(rows), len({r['media_id'] for r in rows}))
        for left in data:
            for right in data:
                if left != right:
                    with self.subTest(left=left, right=right):
                        self.assertFalse(safe[left] & set(data[right]), 'safe Media ID present in another inventory')

    def test_shared_silent_and_unknown_rows_are_never_safe(self):
        for name in research_names():
            manifest = json.loads((COMMANDERS/name/'research/manifest-draft.json').read_text(encoding='utf-8'))
            usages = defaultdict(set)
            for usage in read_csv(COMMANDERS/name/'research/usage-paths.csv'):
                usages[usage['media_id']].add(usage['owner'])
            for row in read_csv(COMMANDERS/name/'research/voice-lines.csv'):
                with self.subTest(name=name, media_id=row['media_id']):
                    if row['silent_placeholder'] == 'YES':
                        self.assertEqual(row['safe_to_replace_for_commander'], 'NO_SILENT')
                    elif row['sharing_scope'] == 'UNKNOWN_SHARED_SCOPE':
                        self.assertEqual(row['safe_to_replace_for_commander'], 'NO_UNKNOWN')
                    elif row['sharing_scope'] != 'COMMANDER_SPECIFIC':
                        self.assertEqual(row['safe_to_replace_for_commander'], 'NO_SHARED')
                    if row['safe_to_replace_for_commander'] == 'YES':
                        self.assertEqual(usages[row['media_id']], {'commander:' + manifest['actor_name']})
                        self.assertEqual((row['shared_with'], row['reverse_reference_check']), ('', 'PASS'))

    def test_spoken_safe_lines_keep_original_facts(self):
        for name in research_names():
            audit = json.loads((COMMANDERS/name/'research/original-audio-audit.json').read_text(encoding='utf-8'))['results']
            for row in read_csv(COMMANDERS/name/'research/voice-lines.csv'):
                if row['safe_to_replace_for_commander'] != 'YES':
                    continue
                fact = audit[row['media_id']]
                with self.subTest(name=name, media_id=row['media_id']):
                    self.assertEqual(int(row['original_size_bytes']), fact['original_size_bytes'])
                    self.assertGreater(fact['original_size_bytes'], 0)
                    self.assertAlmostEqual(float(row['original_duration']), fact['original_duration'], places=6)
                    self.assertEqual((fact['decode_status'], fact['silent_placeholder']), ('PASS_PCM16', 'NO'))
                    self.assertGreater(fact['audio_peak_pcm16'], 0)

    def test_duplicate_groups_are_exact_recordings(self):
        for name in research_names():
            groups = defaultdict(list)
            for row in read_csv(COMMANDERS/name/'research/voice-lines.csv'):
                if row['duplicate_group']:
                    groups[row['duplicate_group']].append(row)
            for group, rows in groups.items():
                with self.subTest(name=name, group=group):
                    keys = {(r['sample_rate'], r['channels'], r['sample_count'], r['pcm_sha256']) for r in rows}
                    self.assertEqual(len(keys), 1)
                    roots = [r for r in rows if not r['duplicate_content_of']]
                    self.assertLessEqual(len(roots), 1)
                    for row in rows:
                        if row['duplicate_content_of'] and roots:
                            self.assertEqual(row['duplicate_content_of'], roots[0]['media_id'])

    def test_tts_plans_group_one_recording_one_wording_one_route(self):
        for name in research_names():
            folder = COMMANDERS/name/'tts-plan'
            if not (folder/'tts-plan.csv').exists():
                continue
            research = {r['media_id']: r for r in read_csv(COMMANDERS/name/'research/voice-lines.csv')}
            voices = read_csv(folder/'voice-lines-cz.csv')
            plan = {r['tts_performance_group']: r for r in read_csv(folder/'tts-plan.csv')}
            self.assertEqual({r['media_id'] for r in voices},
                             {m for m, r in research.items() if r['safe_to_replace_for_commander'] == 'YES'})
            groups = defaultdict(list)
            for row in voices:
                groups[row['tts_performance_group']].append(row)
                with self.subTest(name=name, media_id=row['media_id']):
                    tags = [p.strip() for p in row['recommended_tags'].strip('[]').split(',')]
                    self.assertTrue(1 <= len(tags) <= 2)
                    self.assertEqual(row['recommended_model'] == 'eleven_v3', 'shouting' in tags)
                    self.assertEqual(row['recommended_model'] == 'eleven_v3', row['delivery_style'] in V3_STYLES)
                    if row['translation_status'] == 'NEEDS_MANUAL_TRANSCRIPTION':
                        self.assertEqual((row['english_text'], row['czech_text']), ('', ''))
                    if row['translation_status'] == 'PREPARED':
                        self.assertIn(research[row['media_id']]['transcript_confidence'], {'CONFIRMED', 'HIGH'})
                        self.assertTrue(row['czech_text'])
            self.assertEqual(set(groups), set(plan))
            for group, rows in groups.items():
                with self.subTest(name=name, group=group):
                    self.assertEqual(int(plan[group]['media_ids_total']), len(rows))
                    for field in ['pcm_sha256', 'czech_text', 'recommended_model', 'recommended_tags']:
                        self.assertEqual(len({r[field] for r in rows}), 1, field)
                    self.assertEqual(len({english_key(r['english_text']) for r in rows}), 1)
                    self.assertEqual(plan[group]['tts_source_media_id'], min((r['media_id'] for r in rows), key=int))

    def test_commander_translation_memories_cover_exactly_their_safe_text(self):
        for name in research_names():
            path = COMMANDERS/name/'tts-plan/translation-memory.tsv'
            if not path.exists():
                continue
            memory, _ = read_memory(path)
            used = {english_key(r['english_text']) for r in read_csv(COMMANDERS/name/'research/voice-lines.csv')
                    if r['safe_to_replace_for_commander'] == 'YES' and r['english_text']}
            self.assertEqual(set(memory), used)

    def test_hannibal_replacements_unchanged_and_never_another_commanders_safe_id(self):
        manifest = load_manifest('hannibal')
        files = sorted((ROOT/'replacements/hannibal/wem').iterdir())
        self.assertEqual(len(manifest['replacements']), 305)
        self.assertEqual(len(files), 305)
        expected = {s['media_id']: s for s in manifest['replacements']}
        for path in files:
            spec = expected[path.stem]
            self.assertEqual(path.stat().st_size, spec['size'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), spec['sha256'])
        data = inventories()
        for name in research_names():
            safe = {m for m, r in data[name].items() if safe_flag(name, r) == 'YES'}
            self.assertFalse(safe & set(expected), name)

    def test_no_original_audio_in_commander_data_or_foreign_replacements(self):
        leaked = [p for p in COMMANDERS.rglob('*') if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES]
        self.assertEqual(leaked, [])
        self.assertEqual({p.name for p in (ROOT/'replacements').iterdir()},
                         {m['commander'] for m in discover()})


if __name__ == '__main__':
    unittest.main()
