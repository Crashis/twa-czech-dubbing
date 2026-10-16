"""Safety and evidence regressions for offline commander TTS preparation."""
from collections import defaultdict
import json
import unittest

from tools.inventory.research_metadata import read_csv
from tools.resources import ROOT
from tools.tts.research_plan import budget_risk, performance_key, translation_memory


class ResearchPlanTests(unittest.TestCase):
    def test_group_requires_same_original_recording_and_wording(self):
        fact = {'sample_rate': '32000', 'channels': '1', 'sample_count': '32000',
                'pcm_sha256': 'a'*64, 'english_text': 'For Sparta!', 'media_id': '1'}
        self.assertEqual(performance_key(fact, 'Za Spartu!'),
                         performance_key(fact | {'media_id':'2'}, 'Za Spartu!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'),
                            performance_key(fact | {'english_text':'For Rome!'}, 'Za Spartu!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'), performance_key(fact, 'Za Řím!'))
        self.assertNotEqual(performance_key(fact, 'Za Spartu!'),
                            performance_key(fact | {'pcm_sha256':'b'*64}, 'Za Spartu!'))

    def test_plans_include_only_independently_safe_ids(self):
        memory = translation_memory(ROOT/'data/commanders/shared-research/commander-translation-memory.tsv')
        for name in ['leonidas','scipio-africanus']:
            with self.subTest(name=name):
                folder = ROOT/'data/commanders'/name
                research = {r['media_id']:r for r in read_csv(folder/'research/voice-lines.csv')}
                voices = read_csv(folder/'tts-plan/voice-lines-cz.csv')
                plan = read_csv(folder/'tts-plan/tts-plan.csv')
                self.assertEqual(len(voices),len({r['media_id'] for r in voices}))
                self.assertEqual({r['media_id'] for r in voices},
                                 {mid for mid,r in research.items() if r['safe_to_replace_for_commander']=='YES'})
                groups = defaultdict(list)
                for row in voices:
                    source = research[row['media_id']]
                    self.assertEqual((source['sharing_scope'],source['silent_placeholder'],source['reverse_reference_check']),
                                     ('COMMANDER_SPECIFIC','NO','PASS'))
                    self.assertEqual(row['original_size_bytes'],source['original_size_bytes'])
                    self.assertEqual(row['original_duration'],source['original_duration'])
                    if row['english_text']:
                        self.assertEqual(row['czech_text'],memory[' '.join(row['english_text'].casefold().split())])
                    self.assertIn(row['recommended_model'], {'eleven_v3','eleven_v4'})
                    self.assertTrue(row['recommended_tags'].startswith('[') and row['recommended_tags'].endswith(']'))
                    self.assertIn(row['wem_budget_risk'], {'LOW','MEDIUM','HIGH'})
                    groups[row['tts_performance_group']].append(row)
                self.assertEqual(len(groups),len(plan))
                self.assertEqual({r['tts_performance_group'] for r in plan},set(groups))
                for rows in groups.values():
                    self.assertEqual(len({r['pcm_sha256'] for r in rows}),1)
                    self.assertEqual(len({r['english_text'].casefold() for r in rows}),1)
                    self.assertEqual(len({r['czech_text'] for r in rows}),1)
                    self.assertEqual(len({r['recommended_model'] for r in rows}),1)
                    self.assertEqual({r['tts_source_media_id'] for r in rows},
                                     {min((r['media_id'] for r in rows),key=int)})
                for filename in ['pilot-menu.csv','pilot-battle.csv']:
                    for row in read_csv(folder/'tts-plan'/filename):
                        self.assertEqual(row['translation_status'],'PREPARED')
                        self.assertEqual(row['english'],row['english_text'])
                        self.assertEqual(row['czech'],row['czech_text'])
                        self.assertIn(row['trigger_confidence'],{'CONFIRMED','HIGH'})
                decisions = read_csv(folder/'tts-plan/transcript-review-decisions.csv')
                expected_review = {'leonidas': 3, 'scipio-africanus': 5}[name]
                self.assertEqual(len(decisions), expected_review)
                self.assertEqual(sum(bool(r['final_transcript']) for r in decisions),2)

    def test_manual_deferral_never_becomes_a_tts_request(self):
        folder = ROOT/'data/commanders/scipio-africanus'
        voices={r['media_id']:r for r in read_csv(folder/'tts-plan/voice-lines-cz.csv')}
        row=voices['1022842783']
        self.assertEqual(row['translation_status'],'NEEDS_MANUAL_TRANSCRIPTION')
        self.assertEqual((row['english_text'],row['czech_text']),('',''))
        decisions={r['media_id']:r for r in read_csv(folder/'tts-plan/transcript-review-decisions.csv')}
        self.assertEqual(decisions['1022842783']['transcript_resolution'],'NEEDS_MANUAL_TRANSCRIPTION')
        self.assertEqual(decisions['1022842783']['final_transcript'],'')
        self.assertTrue(decisions['1022842783']['archive_wav_reference'].endswith('/1022842783.wav'))
        self.assertFalse(json.loads((folder/'tts-plan/plan-summary.json').read_text(encoding='utf-8'))['ready_for_elevenlabs'])

    def test_budget_labels_do_not_claim_encoding(self):
        self.assertEqual(budget_risk(5000,1,'Go!','Běžte!'),'HIGH')
        self.assertEqual(budget_risk(12000,2,'Forward!','Vpřed!'),'LOW')


if __name__=='__main__':
    unittest.main()
