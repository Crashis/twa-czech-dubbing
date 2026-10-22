"""Pronunciation overrides: canonical Czech text vs. the TTS input, one resolver for pilot and production."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.tts import production, pronunciation
from tools.tts.pronunciation import Resolver, ReviewRequired, read_rules

FIELDS = ['tts_performance_group', 'tts_source_media_id', 'member_media_ids', 'english_text', 'czech_text',
          'tts_text_override', 'palatalization_fallback_text', 'override_reason', 'status']


class PronunciationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-pronunciation-tests-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def rules(self, rows, scope='commander', name='rules.csv'):
        path = self.folder / name
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({'override_reason': 'test', 'status': 'APPROVED'} | row)
        return read_rules(path, scope)

    def token(self, source, tts, **extra):
        return {'czech_text': source, 'tts_text_override': tts} | extra

    def resolve(self, text, rows, mode='production', key=None):
        return Resolver(self.rules(rows)).resolve(text, mode, key)

    def test_required_cases(self):
        rows = [self.token('Caesar', 'Cézar'), self.token('Germanicus', 'Germanykus'),
                self.token('Xanthippus', 'Ksantypos'), self.token('Falxy', 'Falksy')]
        for canonical, expected in (('Caesar vítězí!', 'Cézar vítězí!'), ('Germanicus!', 'Germanykus!'),
                                    ('Xanthippus!', 'Ksantypos!'), ('Falxy!', 'Falksy!'), ('Vpřed!', 'Vpřed!'),
                                    ('Caesar a Germanicus!', 'Cézar a Germanykus!')):
            with self.subTest(canonical=canonical):
                spoken = self.resolve(canonical, rows)
                self.assertEqual((spoken['canonical_text'], spoken['tts_input_text']), (canonical, expected))
                self.assertEqual(bool(spoken['applied_pronunciation_overrides']), canonical != expected)
        applied = self.resolve('Caesar a Germanicus!', rows)['applied_pronunciation_overrides']
        self.assertEqual([(x['source'], x['tts'], x['scope']) for x in applied],
                         [('Caesar', 'Cézar', 'commander'), ('Germanicus', 'Germanykus', 'commander')])

    def test_whole_words_only_and_single_pass(self):
        rows = [self.token('Caesar', 'Cézar'), self.token('Cézar', 'WRONG'), self.token('Falxy', 'Falksy')]
        for canonical in ('Caesarovi sláva!', 'Caesarem!', 'NeoCaesar!', 'caesar!', 'CAESAR!', 'Falxymani!'):
            with self.subTest(canonical=canonical):
                self.assertEqual(self.resolve(canonical, rows)['tts_input_text'], canonical)
        # A replacement is never rewritten by another rule, and each canonical token is replaced once.
        self.assertEqual(self.resolve('Caesar, Cézar, Caesar.', rows)['tts_input_text'], 'Cézar, WRONG, Cézar.')
        self.assertEqual(len(self.resolve('Caesar! Caesar!', rows)['applied_pronunciation_overrides']), 1)
        longest = [self.token('Cornelius', 'Kornelius'), self.token('Publius Cornelius', 'Publius Kornélius')]
        self.assertEqual(self.resolve('Publius Cornelius Scipio!', longest)['tts_input_text'],
                         'Publius Kornélius Scipio!')

    def test_scope_precedence(self):
        global_rules = self.rules([self.token('Caesar', 'Kaesar')], 'global', 'global.csv')
        local = self.rules([self.token('Caesar', 'Cézar')], 'commander', 'local.csv')
        self.assertEqual(Resolver(global_rules + local).resolve('Caesar!', 'production')['tts_input_text'], 'Cézar!')
        self.assertEqual(Resolver(global_rules).resolve('Caesar!', 'production')['tts_input_text'], 'Kaesar!')
        rejected = self.rules([self.token('Caesar', 'Cézar', status='REJECTED')], 'commander', 'rejected.csv')
        self.assertEqual(Resolver(global_rules + rejected).resolve('Caesar!', 'production')['tts_input_text'], 'Caesar!')
        phrase = self.rules([{'tts_source_media_id': '7', 'czech_text': 'Sláva Caesarovi!',
                              'tts_text_override': 'Sláva Cézarovi!'}], 'commander', 'phrase.csv')
        resolver = Resolver(global_rules + local + phrase)
        spoken = resolver.resolve('Sláva Caesarovi!', 'production', '7')
        self.assertEqual(spoken['tts_input_text'], 'Sláva Cézarovi!')
        self.assertEqual([(x['scope'], x['source'], x['tts']) for x in spoken['applied_pronunciation_overrides']],
                         [('phrase', 'Caesarovi', 'Cézarovi')])
        # The phrase row binds one performance; the same text elsewhere is left to the token rules.
        self.assertEqual(resolver.resolve('Sláva Caesarovi!', 'production', '8')['tts_input_text'], 'Sláva Caesarovi!')
        with self.assertRaisesRegex(RuntimeError, 'Stale'):
            resolver.resolve('Sláva Caesarovi a Římu!', 'production', '7')
        with self.assertRaisesRegex(RuntimeError, 'Stale'):
            resolver.verify_phrases({'7': 'Jiný text.'})
        with self.assertRaisesRegex(RuntimeError, 'Conflicting'):
            Resolver(local + self.rules([self.token('Caesar', 'Cesar')], 'commander', 'other.csv'))

    def test_pilot_applies_proposals_and_production_requires_review(self):
        rows = [self.token('Caesar', 'Cézar', status='PROPOSED_VERIFY_IN_PILOT'),
                {'tts_source_media_id': '9', 'czech_text': 'Miltiadés!', 'tts_text_override': '',
                 'palatalization_fallback_text': 'Miltyadés!', 'status': 'FALLBACK_ONLY_IF_PILOT_PALATALIZES'}]
        resolver = Resolver(self.rules(rows))
        self.assertEqual(resolver.resolve('Caesar padl!', 'pilot')['tts_input_text'], 'Cézar padl!')
        self.assertEqual(resolver.resolve('Miltiadés!', 'pilot', '9')['tts_input_text'], 'Miltiadés!')
        self.assertEqual(resolver.resolve('Vpřed!', 'production')['tts_input_text'], 'Vpřed!')
        for text, key in (('Caesar padl!', None), ('Miltiadés!', '9')):
            with self.subTest(text=text), self.assertRaises(ReviewRequired):
                resolver.resolve(text, 'production', key)
        for bad in (self.token('Caesar', '', status='APPROVED'), self.token('Caesar', 'Cézar', status='MAYBE'),
                    self.token('Caesar', 'Caesar'), self.token('Caesar', 'Cézar', override_reason='')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                self.rules([bad])

    def test_repository_override_files(self):
        # Every phrase row still matches its commander's canonical plan, which the resolver never changes.
        self.assertGreater(pronunciation.report()['rules'], 0)
        for path in Path('data/commanders').glob('*/' + pronunciation.FILE):
            commander = path.parts[2]
            plan = production.read_csv(path.parent / 'tts-plan.csv')
            resolver = pronunciation.commander_resolver(commander)
            resolver.verify_phrases({row['tts_source_media_id']: row['czech_text'] for row in plan})
            for row in plan:
                spoken = resolver.resolve(row['czech_text'], 'pilot', row['tts_source_media_id'])
                self.assertEqual(spoken['canonical_text'], row['czech_text'])
        caesar = pronunciation.commander_resolver('julius-caesar').resolve('Jsem Caesar!', 'pilot', '26740450')
        self.assertEqual(caesar['tts_input_text'], 'Jsem Cézar!')
        units = pronunciation.unit_resolver()
        self.assertEqual(units.resolve('Falxy!', 'pilot')['tts_input_text'], 'Falksy!')
        # Approved by the user 2026-10-22: production sends Falksy!, the canonical text stays Falxy!.
        falxy = units.resolve('Falxy!', 'production')
        self.assertEqual((falxy['canonical_text'], falxy['tts_input_text']), ('Falxy!', 'Falksy!'))
        self.assertEqual(falxy['applied_pronunciation_overrides'][0]['status'], 'APPROVED')
        staged = json.loads(Path('data/shared/unit-acknowledgements/plan.staged.json').read_text(encoding='utf-8'))
        for performance in staged['performances']:
            self.assertEqual(units.resolve(performance['czech_text'], 'pilot')['tts_input_text'],
                             performance['tts_input_text'])


class ProductionPronunciationTests(unittest.TestCase):
    """tools.tts.production records canonical and TTS input and never treats stale audio as current."""

    def setUp(self):
        from tests.test_tts_production import routing_file
        self.temp = tempfile.TemporaryDirectory(prefix='twa-pronunciation-production-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.plan, self.routes, _, _ = production.load_plan('zhuge-liang', routing_file(self.folder), 'eleven_v4')
        self.plan = self.plan[:2]
        self.row = self.plan[0]
        self.mid = self.row['tts_source_media_id']
        self.word = pronunciation.words(self.row['czech_text'])[0]

    def resolver(self, tts):
        path = self.folder / 'rules.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, FIELDS)
            writer.writeheader()
            writer.writerow({'czech_text': self.word, 'tts_text_override': tts, 'override_reason': 'test',
                             'status': 'APPROVED'})
        return Resolver(read_rules(path, 'commander'))

    def items(self, resolver=None):
        return production.items_from_plan(self.plan, self.routes, self.folder, 'VOICE', 'Voice', resolver)

    def test_request_uses_tts_input_and_records_canonical(self):
        item = self.items(self.resolver('Xyz'))[self.mid]
        expected = self.row['czech_text'].replace(self.word, 'Xyz', 1)
        self.assertEqual((item['czech_text'], item['canonical_text'], item['tts_input_text']),
                         (self.row['czech_text'], self.row['czech_text'], expected))
        self.assertEqual(item['request_text'], self.row['recommended_tags'] + ' ' + expected)
        self.assertEqual(item['applied_pronunciation_overrides'][0]['tts'], 'Xyz')
        self.assertFalse([field for field in item if 'key' in field.lower()])  # never credentials
        plain = self.items()[self.mid]
        self.assertEqual((plain['tts_input_text'], plain['applied_pronunciation_overrides']), (self.row['czech_text'], []))

    def test_changed_override_marks_completed_audio_stale(self):
        old = self.items(self.resolver('Xyz'))
        done, planned = old[self.mid], old[self.plan[1]['tts_source_media_id']]
        done.update(status='complete', checksum='abc')
        sent = done['request_text']
        new = self.items(self.resolver('Qwe'))
        production.reconcile_pronunciation(done, new[self.mid])
        production.reconcile_pronunciation(planned, new[planned['tts_source_media_id']])
        self.assertEqual((done['status'], done['needs_regeneration'], done['request_text']), ('stale', True, sent))
        self.assertIn('Qwe', done['current_tts_input_text'])
        self.assertEqual(planned['status'], 'planned')
        # Reverting the override to what was actually sent restores the completed audio.
        production.reconcile_pronunciation(done, old[self.mid])
        self.assertEqual(done['status'], 'complete')
        self.assertNotIn('needs_regeneration', done)
        # Older ledgers without tts_input_text sent the canonical text and stay current without overrides.
        legacy = {k: v for k, v in self.items()[self.mid].items() if k not in production.REQUEST_FIELDS[:2]}
        legacy['status'] = 'complete'
        production.reconcile_pronunciation(legacy, self.items()[self.mid])
        self.assertEqual(legacy['status'], 'complete')

    def test_pilot_with_unapproved_pronunciation_is_not_reused(self):
        state = {'voice_id': 'VOICE', 'voice_name': 'Voice', 'items': self.items()}
        audio = self.folder / 'pilot.mp3'
        audio.write_bytes(b'a' * 2000)
        spoken = self.row['czech_text'].replace(self.word, 'Xyz', 1)
        journal = self.folder / 'journal.json'
        journal.write_text(json.dumps({'voice_name': 'Voice', 'requests': [{
            'media_id': self.mid, 'status': 'complete', 'model': state['items'][self.mid]['model'],
            'czech_text': self.row['czech_text'], 'tts_input_text': spoken, 'tags': self.row['recommended_tags'],
            'request_text': self.row['recommended_tags'] + ' ' + spoken, 'output': str(audio),
            'audio': {'sha256': production.sha_file(audio)}}]}), encoding='utf-8')
        production.import_pilot(state, journal, None)
        self.assertEqual(state['items'][self.mid]['status'], 'planned')

    def test_regeneration_uses_the_same_resolver(self):
        from tools.tts import regenerate
        state = self.folder / 'state.json'
        state.write_text(json.dumps({'voice_id': 'V', 'items': {self.mid: {
            'status': 'complete', 'czech_text': self.row['czech_text'], 'output_path': 'x.mp3', 'checksum': '0',
            'audio': {'duration_seconds': 1.0}}}}), encoding='utf-8')
        deliveries = self.folder / 'deliveries.csv'
        deliveries.write_text('media_id,attempt,tags\n' + self.mid + ',1,[calm]\n', encoding='utf-8')
        with patch.object(regenerate, 'commander_resolver', return_value=self.resolver('Xyz')):
            targets, _ = regenerate.load_targets('zhuge-liang', state, deliveries, 1)
        target = targets[self.mid + '#1']
        self.assertEqual((target['canonical_text'], target['tts_input_text']),
                         (self.row['czech_text'], self.row['czech_text'].replace(self.word, 'Xyz', 1)))


if __name__ == '__main__':
    unittest.main()
