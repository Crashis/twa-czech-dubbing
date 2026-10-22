"""Partial work must preserve the pronunciation gate and cannot substitute for a release."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import mod
from tools.tts.pronunciation import Resolver
from tools.tts.production import items_from_plan, sha_file, import_pilot
from tools.tts.verification import sample_items, export_journal
from tools.wem.production import context


class PartialCommanderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'work'
        self.folder.mkdir()
        (self.folder / 'audio').mkdir()
        self.plan = [dict(tts_source_media_id=str(i), member_media_ids=str(i),
                          tts_performance_group='P' + str(i), czech_text=text,
                          recommended_tags='[firm]', delivery_style='AUTHORITATIVE')
                     for i, text in ((1, 'Vpřed!'), (2, 'Caesar padl!'))]
        self.routes = {str(i): {'selected_model': 'eleven_v4'} for i in (1, 2)}
        self.resolver = Resolver([dict(scope='phrase', key='2', source='Caesar padl!', tts='Cézar padl!',
                                       fallback=None, status='PROPOSED_VERIFY_IN_PILOT',
                                       reason='pilot required', file='test.csv')])
        self.items = items_from_plan(self.plan, self.routes, self.folder, 'VOICE', 'Voice',
                                    self.resolver, defer_review=True)
        audio = Path(self.items['1']['output_path'])
        audio.write_bytes(b'approved audio fixture')
        self.items['1'].update(status='complete', checksum=sha_file(audio),
                               audio={'sha256': sha_file(audio), 'bytes': audio.stat().st_size})
        self.state = dict(commander='test', safe_media_ids=2, unique_performances=2,
                          source_hashes={}, voice_id='VOICE', voice_name='Voice', items=self.items)
        self.path = self.folder / 'generation-state.json'
        research = self.root / 'data/commanders/test/research'
        research.mkdir(parents=True)
        results = {str(i): dict(original_size_bytes=100, pack_offset=i * 100,
                                original_wem_sha256='hash' + str(i), silent_placeholder='NO') for i in (1, 2)}
        (research / 'original-audio-audit.json').write_text(json.dumps(dict(
            canonical_pack_sha256='base', RSA='PASS', results=results)), encoding='utf-8')
        self.inventory = [dict(media_id=k, safe_to_replace_for_commander='YES', safe_to_replace_for_test='YES',
                               scope='TEST_SPECIFIC', **v) for k, v in results.items()]

    def call_context(self, partial):
        self.path.write_text(json.dumps(self.state), encoding='utf-8')
        args = SimpleNamespace(commander='test', state=[str(self.path)], routing='routing.csv',
                               defer_pronunciation_review=partial)
        with patch.object(mod, 'ROOT', self.root), patch.object(mod, 'csv_rows', return_value=self.inventory), \
                patch('tools.wem.production.load_plan', return_value=(self.plan, self.routes, {}, 2)), \
                patch('tools.tts.pronunciation.commander_resolver', return_value=self.resolver):
            return context(args)

    def test_release_context_still_requires_every_performance(self):
        with self.assertRaisesRegex(ValueError, 'Unapproved or changed performance 2'):
            self.call_context(False)

    def test_work_subset_excludes_only_the_current_never_sent_blocker(self):
        plan, state, audit, safe = self.call_context(True)
        self.assertEqual([r['tts_source_media_id'] for r in plan], ['1'])
        self.assertEqual(set(safe), {'1'})
        self.assertEqual(state['safe_media_ids'], 2)  # full ledger is never rewritten into a partial release

    def test_forged_or_already_requested_deferred_item_is_rejected(self):
        self.items['2']['request_id'] = 'already-paid'
        with self.assertRaisesRegex(ValueError, 'Invalid deferred performance'):
            self.call_context(True)
        self.items['2']['request_id'] = None
        self.resolver = Resolver([])
        with self.assertRaisesRegex(ValueError, 'Invalid deferred performance'):
            self.call_context(True)

    def test_changed_pronunciation_and_other_incomplete_states_are_rejected(self):
        self.items['1']['tts_input_text'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'Stale pronunciation'):
            self.call_context(True)
        self.items['1']['tts_input_text'] = 'Vpřed!'
        self.items['1']['status'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'Unapproved or changed'):
            self.call_context(True)

    def test_verification_samples_keep_canonical_and_unapproved_status(self):
        items = sample_items(self.plan, self.routes, self.folder, 'VOICE', 'Voice', self.resolver)
        self.assertEqual(set(items), {'2'})
        self.assertEqual(items['2']['canonical_text'], 'Caesar padl!')
        self.assertEqual(items['2']['tts_input_text'], 'Cézar padl!')
        self.assertEqual(items['2']['applied_pronunciation_overrides'][0]['status'], 'PROPOSED_VERIFY_IN_PILOT')
        self.assertEqual(self.resolver.rules[0]['status'], 'PROPOSED_VERIFY_IN_PILOT')
        state = dict(voice_name='Voice', items=items)
        export_journal(state, self.folder)
        self.assertEqual(json.loads((self.folder / 'pilot-journal.json').read_text())['requests'], [])

    def test_paid_sample_is_reused_only_after_the_matching_human_decision(self):
        samples = sample_items(self.plan, self.routes, self.folder, 'VOICE', 'Voice', self.resolver)
        audio = Path(samples['2']['output_path'])
        audio.write_bytes(b'paid pilot fixture')
        samples['2'].update(status='complete', checksum=sha_file(audio), credits_used=12,
                            request_id='PILOT_REQUEST', generation_timestamp='2026-10-22T12:00:00+00:00',
                            audio={'sha256': sha_file(audio)})
        export_journal(dict(voice_name='Voice', items=samples), self.folder)
        target = self.folder / 'production'
        (target / 'audio').mkdir(parents=True)
        approved = Resolver([dict(self.resolver.rules[0], status='APPROVED')])
        items = items_from_plan(self.plan, self.routes, target, 'VOICE', 'Voice', approved)
        state = dict(voice_name='Voice', voice_id='VOICE', items=items)
        def inspect(path, mini):
            return {'sha256': sha_file(path)}
        with patch('tools.tts.production.inspect_audio', side_effect=inspect):
            import_pilot(state, self.folder / 'pilot-journal.json', None)
        self.assertEqual(items['2']['status'], 'complete')
        self.assertEqual(items['2']['origin'], 'pilot_reused')
        self.assertEqual(items['2']['request_id'], 'PILOT_REQUEST')
        self.assertEqual(items['2']['applied_pronunciation_overrides'][0]['status'], 'APPROVED')
        self.assertEqual(Path(items['2']['output_path']).read_bytes(), audio.read_bytes())

    def test_compact_preparation_resolves_duplicate_targets_to_one_performance(self):
        from tools.wem.recovery import run
        class Prepared(Exception):
            pass
        production = self.folder / 'prod'
        production.mkdir()
        args = SimpleNamespace(reselect=False, production_work=str(production),
                               work=str(self.folder / 'recovery'), source_dir=str(self.folder / 'sources'),
                               prepare_from_state='regeneration.json', attempt=1, media_ids='1,3')
        plan = [dict(tts_source_media_id='1', member_media_ids='1;3')]
        with patch.object(mod, 'ROOT', self.root), \
                patch('tools.wem.production.context', return_value=(plan, {}, {}, {'1': {}, '3': {}})), \
                patch('tools.wem.recovery.prepare_sources', side_effect=Prepared) as prepare:
            with self.assertRaises(Prepared):
                run(args)
            prepare.assert_called_once_with(Path('regeneration.json'), 1, ['1'], self.folder / 'sources')
            prepare.reset_mock()
            args.media_ids = '1,999'
            with self.assertRaisesRegex(ValueError, 'Only safe Media IDs'):
                run(args)
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
