"""Offline guards of the paid TTS client; every network call is mocked."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from tools.resources import ROOT
from tools.tts import production

PLAN = ROOT / 'data/commanders/zhuge-liang/tts-plan'


def routing_file(folder, model='eleven_v4'):
    plan = production.read_csv(PLAN / 'tts-plan.csv')
    voices = {r['media_id']: r for r in production.read_csv(PLAN / 'voice-lines-cz.csv')}
    path = Path(folder) / 'routing.csv'
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, ['tts_performance_group', 'tts_source_media_id', 'czech_text', 'category',
                                         'trigger', 'delivery_style', 'selected_model', 'reason'])
        writer.writeheader()
        for row in plan:
            voice = voices[row['tts_source_media_id']]
            writer.writerow({'tts_performance_group': row['tts_performance_group'],
                             'tts_source_media_id': row['tts_source_media_id'], 'czech_text': row['czech_text'],
                             'category': voice['category'], 'trigger': voice['trigger'],
                             'delivery_style': row['delivery_style'], 'selected_model': model, 'reason': 'test'})
    return path


def metrics(path, mini=None):
    return {'duration_seconds': 1.0, 'sample_rate': 44100, 'rms_pcm16': 3000.0, 'peak_pcm16': 20000,
            'bytes': Path(path).stat().st_size, 'clipped_samples_pcm16': 0, 'sha256': production.sha_file(Path(path))}


class TTSProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-tts-tests-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def state(self):
        plan, routes, _, _ = production.load_plan('zhuge-liang', routing_file(self.folder), 'eleven_v4')
        (self.folder / 'audio').mkdir(exist_ok=True)
        items = production.items_from_plan(plan[:2], routes, self.folder, 'VOICE_B', 'Voice B')
        return {'voice_id': 'VOICE_B', 'voice_name': 'Voice B', 'items': items}, plan

    def test_hyphenated_commander_plan_and_required_model(self):
        # Paths in the client are relative to the repository root, like the release builder's test run.
        plan, routes, _, safe = production.load_plan('zhuge-liang', routing_file(self.folder), 'eleven_v4')
        self.assertEqual((safe, len(plan)), (293, 292))
        with self.assertRaisesRegex(RuntimeError, 'required production model'):
            production.load_plan('zhuge-liang', routing_file(self.folder, 'eleven_v3'), 'eleven_v4')

    def test_comparison_pilot_reuses_only_the_production_voice(self):
        state, plan = self.state()
        first = plan[0]
        text = first['recommended_tags'] + ' ' + first['czech_text']
        requests = []
        for voice, voice_id, data in (('a', 'VOICE_A', b'a' * 2000), ('b', 'VOICE_B', b'b' * 2000)):
            path = self.folder / f'pilot-{voice}.mp3'
            path.write_bytes(data)
            requests.append({'media_id': first['tts_source_media_id'], 'czech_text': first['czech_text'],
                             'tags': first['recommended_tags'], 'request_text': text, 'voice_name': 'Voice ' + voice.upper(),
                             'voice_id': voice_id, 'model': 'eleven_v4', 'output_format': production.FORMAT,
                             'output': str(path), 'status': 'complete', 'credits': 20, 'request_id': 'R' + voice,
                             'audio': {'sha256': production.sha_file(path)}})
        journal = self.folder / 'journal.json'
        journal.write_text(json.dumps({'requests': requests}), encoding='utf-8')
        with patch.object(production, 'inspect_audio', side_effect=metrics):
            production.import_pilot(state, journal, None)
        item = state['items'][first['tts_source_media_id']]
        self.assertEqual((item['status'], item['source'], item['request_id']), ('complete', 'reused_pilot', 'Rb'))
        self.assertEqual(Path(item['output_path']).read_bytes(), b'b' * 2000)
        self.assertEqual(state['items'][plan[1]['tts_source_media_id']]['status'], 'planned')

    def test_voice_id_mismatch_is_hard_stop(self):
        page = {'voices': [{'name': 'Voice B', 'voice_id': 'OTHER'}], 'has_more': False}
        with patch.object(production, 'get_json', side_effect=[page]), self.assertRaises(production.HardStop):
            production.voice_and_models('key', 'Voice B', 'VOICE_B', {'eleven_v4'})

    def test_rejected_credentials_stop_without_retry(self):
        state, plan = self.state()
        item = state['items'][plan[0]['tts_source_media_id']]
        error = HTTPError('url', 401, 'denied', {}, io.BytesIO(b'{"detail": {"status": "invalid_credentials"}}'))
        with patch.object(production, 'urlopen', side_effect=error), self.assertRaises(production.HardStop):
            production.generate_one(item, 'key', 'VOICE_B', None, state, self.folder / 'state.json')
        self.assertEqual((item['status'], item['failure_kind']), ('failed', 'rejected'))

    def test_transport_error_recovers_billed_history_before_any_retry(self):
        state, plan = self.state()
        item = state['items'][plan[0]['tts_source_media_id']]
        with patch.object(production, 'urlopen', side_effect=URLError('reset')):
            production.generate_one(item, 'key', 'VOICE_B', None, state, self.folder / 'state.json')
        self.assertEqual(item['failure_kind'], 'transport')
        with patch.object(production, 'recover_from_history', return_value=True) as recover, \
                patch.object(production, 'generate_one') as generate, patch.object(production.time, 'sleep'):
            production.retry_technical(item, 'key', state, self.folder / 'state.json', None)
        recover.assert_called_once()
        generate.assert_not_called()

    def test_empty_response_gets_exactly_one_retry(self):
        state, plan = self.state()
        item = state['items'][plan[0]['tts_source_media_id']]
        item.update(status='failed', failure_kind='empty_or_corrupt', error='empty',
                    generation_timestamp=production.utc_now())
        calls = []

        def fail_again(target, *args):
            calls.append(target['tts_source_media_id'])
            target.update(status='failed', failure_kind='empty_or_corrupt', error='empty')
        with patch.object(production, 'generate_one', side_effect=fail_again), \
                patch.object(production.time, 'sleep'):
            production.retry_technical(item, 'key', state, self.folder / 'state.json', None)
            production.retry_technical(item, 'key', state, self.folder / 'state.json', None)
        self.assertEqual(len(calls), 1)
        self.assertEqual((item['retry_count'], item['status']), (1, 'failed'))
        self.assertIn('one automatic retry already used', item['error'])


class RegenerationTargetTests(unittest.TestCase):
    """tools.tts.regenerate: explicit targets only, canonical text from the plan, bounded attempts."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='twa-regen-tests-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        plan = production.read_csv(PLAN / 'tts-plan.csv')
        self.mid = next(r['tts_source_media_id'] for r in plan if r['media_ids_total'] == '1')
        self.text = next(r['czech_text'] for r in plan if r['tts_source_media_id'] == self.mid)
        self.state = self.folder / 'state.json'
        self.state.write_text(json.dumps({'voice_id': 'V', 'items': {self.mid: {
            'status': 'complete', 'czech_text': self.text, 'output_path': 'x.mp3', 'checksum': '0',
            'audio': {'duration_seconds': 1.0}}}}), encoding='utf-8')

    def deliveries(self, rows):
        path = self.folder / 'deliveries.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, ['media_id', 'attempt', 'tags'])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_canonical_text_and_bounds(self):
        from tools.tts.regenerate import load_targets
        targets, _ = load_targets('zhuge-liang', self.state, self.deliveries(
            [{'media_id': self.mid, 'attempt': 1, 'tags': '[crisp, commanding]'}]), 2)
        self.assertEqual(targets[self.mid + '#1']['canonical_text'], self.text)
        for bad in ({'media_id': self.mid, 'attempt': 3, 'tags': '[crisp]'},
                    {'media_id': self.mid, 'attempt': 1, 'tags': '[crisp, brisk, commanding]'},
                    {'media_id': self.mid, 'attempt': 1, 'tags': 'crisp'},
                    {'media_id': '1064784445', 'attempt': 1, 'tags': '[crisp]'}):  # duplicate member, not a source
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                load_targets('zhuge-liang', self.state, self.deliveries([bad]), 2)

    def test_synthesis_override_keeps_words_and_needs_reason(self):
        from tools.tts.regenerate import load_targets, same_words
        self.assertTrue(same_words('Útok.', 'Útok!'))
        self.assertFalse(same_words('Útok teď.', 'Útok!'))
        base = {'media_id': self.mid, 'attempt': 1, 'tags': '[brisk, commanding]'}
        changed = self.text.rstrip('.!?') + ('.' if not self.text.endswith('.') else '!')
        rows = [dict(base, tts_text_override=changed, override_reason='compact prosody')]
        targets, _ = load_targets('zhuge-liang', self.state, self.deliveries_with_override(rows), 1)
        self.assertEqual((targets[self.mid + '#1']['tts_text_override'], targets[self.mid + '#1']['canonical_text']),
                         (changed, self.text))
        for bad in (dict(base, tts_text_override=changed, override_reason=''),
                    dict(base, tts_text_override='Jiná slova.', override_reason='x')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                load_targets('zhuge-liang', self.state, self.deliveries_with_override([bad]), 1)

    def deliveries_with_override(self, rows):
        path = self.folder / 'override.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, ['media_id', 'attempt', 'tags', 'tts_text_override', 'override_reason'])
            writer.writeheader()
            writer.writerows(rows)
        return path


if __name__ == '__main__':
    unittest.main()
