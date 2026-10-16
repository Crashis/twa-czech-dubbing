"""Safety and evidence regressions for offline commander TTS preparation."""
from collections import defaultdict
import json
from pathlib import Path
import tempfile
import unittest

from tools.inventory.research_metadata import read_csv
from tools.resources import ROOT
from tools.tts.research_plan import (budget_risk, check_delivery, performance_key, plan_delivery,
                                     read_memory, translation_memory)


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

    def test_v3_is_only_for_shouted_expressive_delivery(self):
        self.assertEqual(check_delivery('BATTLE_SHOUT','eleven_v3','[fierce, shouting]')[1],'eleven_v3')
        for bad in [('BATTLE_SHOUT','eleven_v4','[fierce, shouting]'), ('AUTHORITATIVE','eleven_v3','[authoritative]'),
                    ('AUTHORITATIVE','eleven_v4','[proud, calm, authoritative]'), ('AUTHORITATIVE','eleven_v5','[calm]'),
                    ('AUTHORITATIVE','eleven_v4','authoritative')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_delivery(*bad)

    def test_profiled_routing_follows_hannibal_context_rules(self):
        def row(category, trigger, english='Line!'):
            return {'category':category,'trigger':trigger,'english_text':english}
        decide = lambda commander, *rows: plan_delivery(list(rows), commander, {})
        self.assertEqual(decide('spartacus', row('EMOTE','player selects emote: battlecry'))[1:], ('eleven_v3','[fierce, shouting]'))
        self.assertEqual(decide('germanicus', row('ORDER','unit ability ordered: unit manual charge'))[1:], ('eleven_v3','[shouting, commanding]'))
        self.assertEqual(decide('germanicus', row('ORDER','unit ability ordered: unit medium defence stance'))[1], 'eleven_v4')
        self.assertEqual(decide('spartacus', row('BATTLE_EVENT','battle event: one of your units routes'))[1:], ('eleven_v3','[angry, shouting]'))
        self.assertEqual(decide('spartacus', row('BATTLE_EVENT','battle event: your team draws first blood'))[1], 'eleven_v4')
        self.assertEqual(decide('germanicus', row('FRONTEND','open/select commander'))[2], '[proud, authoritative]')
        # A reviewed per-phrase decision wins over context rules.
        reviewed = {'line!': ('DEFIANT','eleven_v4','[defiant]')}
        self.assertEqual(plan_delivery([row('EMOTE','player selects emote: battlecry')],'spartacus',reviewed)[1],'eleven_v4')
        # Commanders without a profile keep the published legacy routing.
        self.assertEqual(decide('scipio-africanus', row('ORDER','unit ability ordered: unit manual charge'))[1], 'eleven_v4')

    def test_memory_accepts_reviewed_delivery_columns_only_when_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'memory.tsv'
            path.write_text('english_text\tczech_text\tdelivery_style\trecommended_model\trecommended_tags\n'
                            'Charge!\tVpřed!\tBATTLE_SHOUT\televen_v3\t[fierce, shouting]\nHold!\tStát!\t\t\t\n', encoding='utf-8')
            memory, decisions = read_memory(path)
            self.assertEqual(memory, {'charge!':'Vpřed!','hold!':'Stát!'})
            self.assertEqual(decisions, {'charge!':('BATTLE_SHOUT','eleven_v3','[fierce, shouting]')})
            path.write_text('english_text\tczech_text\tdelivery_style\trecommended_model\trecommended_tags\n'
                            'Hold!\tStát!\tAUTHORITATIVE\televen_v3\t[authoritative]\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_memory(path)


if __name__=='__main__':
    unittest.main()
