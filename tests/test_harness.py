"""Check the fault harness itself, including intentional failure controls."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import json
from pathlib import Path
import tempfile
import unittest
from ws0.harness import Campaign,Scenario,assess


class HarnessTests(unittest.TestCase):
    def run_case(self,scenario,negative=False):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'case'
            result=Campaign(scenario,out,negative).run()
            trace=(out/'trace.jsonl').read_text()
            availability=json.loads((out/'availability.json').read_text())
            return result,trace,availability

    def test_seed_reproduces_trace_and_results(self):
        scenario=Scenario('repeatable','Seeded network regression.',minutes=60,seed=18,
                          uplink_loss=.2,ack_loss=.2,duplicates=.3,corruption=.02,max_delay_seconds=15)
        first,trace,_=self.run_case(scenario)
        second,again,_=self.run_case(scenario)
        self.assertEqual(trace,again)
        self.assertEqual(first,second)
        self.assertTrue(first['scenario_pass'])

    def test_negative_control_is_detected(self):
        result,_,_=self.run_case(Scenario('broken','Deliberate missing-row control.',minutes=10),True)
        self.assertFalse(result['scenario_pass'])
        self.assertIn('missing',result['failures'])

    def test_total_loss_fails_without_hanging(self):
        result,_,_=self.run_case(Scenario('all-lost','Finite failure control.',minutes=5,uplink_loss=1))
        self.assertFalse(result['scenario_pass'])
        self.assertEqual(len(result['metrics']['missing']),5)
        self.assertEqual(result['pending_journal'],5)
        self.assertLessEqual(result['drain_minutes'],125)

    def test_outage_keeps_denominator_and_recovers(self):
        scenario=Scenario('outage','Outage test.',minutes=60,link_outages=[[10,20]],expect_unavailable=True)
        result,_,states=self.run_case(scenario)
        self.assertTrue(result['scenario_pass'])
        self.assertEqual(result['metrics']['scheduled'],60)
        self.assertEqual(result['metrics']['stored'],60)
        self.assertLess(result['metrics']['live_delivery_percent'],99)
        self.assertTrue(any(not s['available'] for s in states if 13<=s['minute']<20))
        self.assertTrue(states[-1]['available'])

    def test_commit_failure_does_not_lose_data(self):
        result,trace,_=self.run_case(Scenario('disk','Commit test.',minutes=60,commit_failures=[[10,15]]))
        self.assertTrue(result['scenario_pass'])
        self.assertGreater(result['network']['commit_errors'],0)
        self.assertIn('commit_failed_no_ack',trace)

    def test_oracle_rejects_duplicate_and_changed_payload(self):
        record={'session':'1','sequence':1,'sampled_at':1000,'quality':'valid','time_quality':'synchronized'}
        expected={('1',1):(record,1000)}
        # Rows carry the gateway-derived time columns next to the immutable payload.
        duplicate=record|{'received_at':1001,'_effective':1000,'_basis':'synchronized'}
        result=assess(expected,[duplicate,duplicate],1002)
        self.assertEqual(result['duplicate_rows'],1)
        result=assess(expected,[duplicate|{'sampled_at':999}],1002)
        self.assertTrue(result['payload_mismatches'])

    def test_scenario_validation(self):
        for value in [-.1,1.1,float('nan')]:
            with self.assertRaises(ValueError): Scenario('bad','bad',uplink_loss=value).validate()
        with self.assertRaises(ValueError): Scenario('../escape','bad').validate()
        with self.assertRaises(ValueError): Scenario('bad','bad',link_outages=[[10,1]]).validate()
