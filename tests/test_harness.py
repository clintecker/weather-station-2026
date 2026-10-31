"""Check the fault harness itself, including intentional failure controls."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability

import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sqlite3
from ws0.harness import (BATTERY_MONITOR_FIELDS, PHASE_B_RAILS, Campaign, Scenario, assess, assess_health,
                         health_mismatches)
from ws0.service import HEALTH_KEYS
from ws0.simulator import PHASE_A_POWER, power_state


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


class VerdictTests(unittest.TestCase):
    """Characterization of every failure rule of a campaign verdict, and their order. Each case runs
    a short lossless campaign and then perturbs one input the verdict reads: the oracle's metrics,
    an availability snapshot or a campaign counter."""
    def campaign(self, scenario, metrics=None, hook=None):
        from unittest import mock
        from ws0 import harness
        real_assess, real_snapshot = harness.assess, Campaign.snapshot
        def assess_override(*args):
            return real_assess(*args) | (metrics or {})
        def snapshot(campaign):
            real_snapshot(campaign)
            if hook:
                hook(campaign, campaign.availability[-1])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(harness, 'assess', assess_override), \
                mock.patch.object(Campaign, 'snapshot', snapshot):
            return Campaign(scenario, Path(tmp) / 'case').run()

    def failures(self, metrics=None, hook=None, minutes=5, **settings):
        return self.campaign(Scenario('verdict', 'Verdict rule.', minutes=minutes, **settings), metrics, hook)['failures']

    def test_clean_run_passes(self):
        result = self.campaign(Scenario('verdict', 'Verdict rule.', minutes=5, require_latency_target=True))
        self.assertEqual((result['failures'], result['scenario_pass']), ([], True))

    def test_oracle_and_latency_rules(self):
        self.assertEqual(self.failures({'missing': [[1, 1]], 'unexpected_rows': [[9, 9]], 'payload_mismatches': [[1, 2]],
                                        'power_mismatches': [[1, 2]], 'duplicate_rows': 1}),
                         ['missing', 'unexpected_rows', 'payload_mismatches', 'power_mismatches', 'duplicate_rows'])
        self.assertEqual(self.failures({'latency_target_met': False}, require_latency_target=True),
                         ['live_latency_target'])
        self.assertEqual(self.failures({'latency_target_met': False}), [])
        self.assertEqual(self.failures(expect_latency_failure=True), ['expected_latency_failure_not_observed'])
        self.assertEqual(self.failures({'unresolved_time_samples': 1}, require_time_reconstruction=True),
                         ['time_not_reconstructed'])
        self.assertEqual(self.failures({'unresolved_time_samples': 1}), [])
        self.assertEqual(self.failures(expect_unavailable=True), [])     # the first minute is not yet current
        self.assertEqual(self.failures(hook=lambda c, snap: snap.update(
            available=True, effective_sampled_at=snap['true_sampled_at']), expect_unavailable=True),
                         ['unavailable_not_observed'])

    def test_counter_rules(self):
        def bump(*names, value=1):
            def hook(c, snap):
                for name in names:
                    if name in c.counts:
                        c.counts[name] += value if snap['minute'] == 0 else 0
                    elif snap['minute'] == 0:
                        setattr(c, name, getattr(c, name) + value)
            return hook
        self.assertEqual(self.failures(hook=bump('nonce_collisions')), ['nonce_reuse'])
        self.assertEqual(self.failures(hook=bump('node_counter_not_increasing')), ['node_counter_not_increasing'])
        self.assertEqual(self.failures(hook=bump('expected_counter_regressions')), ['counter_regression_mismatch'])
        self.assertEqual(self.failures(hook=bump('expected_replays')), ['replay_mismatch'])
        both = bump('counter_regressions', 'expected_counter_regressions')
        self.assertEqual(self.failures(hook=both), ['counter_regression_mismatch', 'counter_regression_false_positive'])
        self.assertEqual(self.failures(hook=both, max_delay_seconds=1), ['counter_regression_mismatch'])
        self.assertEqual(self.failures(hook=bump('identity_collision_rejections', value=2), minutes=32,
                                       inject_identity_collision=True), ['identity_collision_not_rejected'])
        self.assertEqual(self.failures(minutes=32, inject_identity_collision=True), [])
        self.assertEqual(self.failures(inject_identity_collision=True), ['identity_collision_not_rejected'])
        self.assertEqual(self.failures(uplink_loss=1),
                         ['missing', 'unacknowledged_journal_records', 'availability_not_recovered'])

    def test_availability_rules_and_their_order(self):
        def at(minute, **changes):
            def hook(c, snap):
                if snap['minute'] == minute:
                    snap.update(changes)
            return hook
        def both(*hooks):
            return lambda c, snap: [h(c, snap) for h in hooks]
        wrong = lambda minute: (lambda c, snap: snap['minute'] == minute and snap.update(
            available=True, effective_sampled_at=snap['true_sampled_at'] + 6))
        self.assertEqual(self.failures(hook=at(1, available=True), sensor_faults=[[1, 2]]),
                         ['fault_or_bad_clock_presented_as_current'])
        self.assertEqual(self.failures(hook=at(1, available=True), clock_steps=[[1, 2, 3600]]),
                         ['fault_or_bad_clock_presented_as_current'])
        self.assertEqual(self.failures(sensor_faults=[[1, 2]], clock_steps=[[2, 3, 3600]], unknown_clock=[[3, 4]]), [])
        self.assertEqual(self.failures(hook=at(1, available=True, time_basis='unknown'), unknown_clock=[[1, 2]]),
                         ['unknown_clock_presented_with_wrong_time'])
        self.assertEqual(self.failures(hook=wrong(1), unknown_clock=[[1, 2]]),
                         ['unknown_clock_presented_with_wrong_time'])
        self.assertEqual(self.failures(hook=wrong(2)), ['current_value_with_wrong_time'])
        self.assertEqual(self.failures(hook=at(2, true_sampled_at=None, effective_sampled_at=0)), [])
        # Only the first availability failure is reported.
        self.assertEqual(self.failures(hook=both(wrong(3), at(1, available=True)), sensor_faults=[[1, 2]]),
                         ['fault_or_bad_clock_presented_as_current'])
        self.assertEqual(self.failures(hook=both(wrong(1), wrong(2)), unknown_clock=[[1, 2]]),
                         ['unknown_clock_presented_with_wrong_time'])
        # The end of the run must be current again, unless it ends inside a fault or an outage.
        self.assertEqual(self.failures(hook=at(4, available=False)), ['availability_not_recovered'])
        for ends_inside in ('sensor_faults', 'unknown_clock', 'link_outages', 'host_outages', 'commit_failures'):
            self.assertEqual(self.failures(hook=at(4, available=False), **{ends_inside: [[4, 5]]}), [], ends_inside)
        self.assertEqual(self.failures(hook=at(4, available=False), clock_steps=[[4, 5, 3600]]), [])
        self.assertEqual(self.failures(hook=at(4, available=False), expect_unavailable=True), ['availability_not_recovered'])


class ScenarioValidationTests(unittest.TestCase):
    """Characterization of Scenario.validate: every rule and its message."""
    def test_each_rule(self):
        cases = [
            (dict(name=''), 'Scenario name must use lowercase letters, digits, - or _'),
            (dict(name='Bad'), 'Scenario name must use lowercase letters, digits, - or _'),
            (dict(minutes=0), 'minutes must be an integer from 1 to 10080'),
            (dict(minutes=10081), 'minutes must be an integer from 1 to 10080'),
            (dict(minutes=5.0), 'minutes must be an integer from 1 to 10080'),
            (dict(minutes=True), 'minutes must be an integer from 1 to 10080'),
            (dict(ack_loss='0'), 'ack_loss must be a probability'),
            (dict(corruption=True), 'corruption must be a probability'),
            (dict(duplicates=1.5), 'duplicates must be a probability'),
            (dict(max_delay_seconds=601), 'max_delay_seconds must be 0..600'),
            (dict(max_delay_seconds=-1), 'max_delay_seconds must be 0..600'),
            (dict(max_delay_seconds=1.0), 'max_delay_seconds must be 0..600'),
            (dict(host_outages=[[1]]), 'Invalid interval in host_outages'),
            (dict(commit_failures=[[1, 2.0]]), 'Invalid interval in commit_failures'),
            (dict(clock_steps=[[1, 2]]), 'Invalid interval in clock_steps'),
            (dict(sensor_faults=[[1, 2, 3]]), 'Invalid interval in sensor_faults'),
            (dict(unknown_clock=[[-1, 2]]), 'Out-of-range interval in unknown_clock'),
            (dict(link_outages=[[2, 2]]), 'Out-of-range interval in link_outages'),
            (dict(minutes=10, clock_steps=[[1, 11, 5]]), 'Out-of-range interval in clock_steps'),
            (dict(node_reboots=[1440]), 'Reboot outside sampling interval'),
            (dict(gateway_reboots=[-1]), 'Reboot outside sampling interval'),
            (dict(gateway_reboots=[1.0]), 'Reboot outside sampling interval'),
            (dict(require_latency_target=True, expect_latency_failure=True), 'Contradictory latency expectations'),
            (dict(monitor_faults=[[1]]), 'Invalid interval in monitor_faults'),
            (dict(minutes=10, monitor_faults=[[5, 11]]), 'Out-of-range interval in monitor_faults'),
            (dict(power_profile='C'), 'power_profile must be A or B'),
            (dict(power_profile='a'), 'power_profile must be A or B'),
            (dict(name='Bad', minutes=0), 'Scenario name must use lowercase letters, digits, - or _'),
            (dict(minutes=0, ack_loss=2), 'minutes must be an integer from 1 to 10080'),
            (dict(uplink_loss=2, ack_loss=2), 'uplink_loss must be a probability'),
            (dict(link_outages=[[1]], host_outages=[[1]]), 'Invalid interval in link_outages'),
        ]
        for settings, message in cases:
            scenario = Scenario(**({'name': 'ok', 'description': 'd'} | settings))
            with self.assertRaises(ValueError, msg=settings) as caught:
                scenario.validate()
            self.assertEqual(str(caught.exception), message, settings)
        for settings in (dict(), dict(minutes=10080, max_delay_seconds=600, uplink_loss=1, ack_loss=0.0),
                         dict(minutes=10, link_outages=[[0, 10]], clock_steps=[[0, 1, -5]], node_reboots=[0, 9]),
                         dict(minutes=10, monitor_faults=[[0, 10]], power_profile='B')):
            Scenario(**({'name': 'ok-1_a', 'description': 'd'} | settings)).validate()


class AssessTests(unittest.TestCase):
    """Characterization of the oracle's accounting: trustworthy time and latency bounds."""
    def test_empty_schedule(self):
        result = assess({}, [], 0)
        self.assertEqual((result['live_delivery_percent'], result['latency_target_met'],
                          result['maximum_ground_truth_latency_seconds']), (0, False, None))

    def test_on_time_needs_a_trustworthy_time_and_bounded_latency(self):
        def record(seq, **changes):
            return {'session': '1', 'sequence': seq, 'quality': 'valid', 'time_quality': 'synchronized'} | changes
        def row(seq, received, effective, basis, **changes):
            return record(seq, **changes) | {'received_at': received, '_effective': effective, '_basis': basis}
        acquired = 1000
        cases = [  # received, effective, basis -> on time
            (1120, 1000, 'synchronized', True), (1121, 1000, 'synchronized', False),
            (999, 1000, 'synchronized', False), (1000, 1005, 'reconstructed', True),
            (1000, 994.5, 'reconstructed', False), (1000, None, 'unknown', False), (1000, 1000, 'unknown', False)]
        expected = {('1', i): (record(i), acquired) for i in range(len(cases))}
        expected[('1', 99)] = (record(99, quality='sensor_fault', time_quality='unknown'), acquired)  # never stored
        rows = [row(i, received, effective, basis) for i, (received, effective, basis, _) in enumerate(cases)]
        rows.append(row(50, 1000, 1000, 'synchronized'))
        result = assess(expected, rows, 2000)
        self.assertEqual(result['within_120s_with_trustworthy_time'], sum(c[-1] for c in cases))
        self.assertEqual((result['scheduled'], result['stored'], result['missing'], result['unexpected_rows']),
                         (8, 8, [['1', 99]], [['1', 50]]))
        self.assertEqual((result['unknown_clock_samples'], result['sensor_fault_samples'],
                          result['reconstructed_time_samples'], result['unresolved_time_samples']), (1, 1, 2, 2))
        self.assertEqual((result['live_delivery_percent'], result['latency_target_met'],
                          result['maximum_ground_truth_latency_seconds']), (25.0, False, 121))
        everything = {k: v for k, v in expected.items() if k[1] < 1}
        self.assertTrue(assess(everything, rows[:1], 2000)['latency_target_met'])


class PowerTelemetryTests(unittest.TestCase):
    """Power telemetry design section 10.2: the phase A power set every minute and the 64-byte health
    report every 15 minutes, through the real receive path into storage. The values are synthetic."""
    def run_case(self, scenario, mocks=()):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'case'
            with contextlib.ExitStack() as stack:
                for target, name, value in mocks:
                    stack.enter_context(mock.patch.object(target, name, value))
                result = Campaign(scenario, out).run()
            db = sqlite3.connect(out / 'observations.sqlite3')
            rows = [json.loads(p) for (p,) in db.execute('SELECT payload FROM observations ORDER BY session, sequence')]
            reports = {(session, uptime): json.loads(r) for session, uptime, r in
                       db.execute('SELECT session, uptime_s, report FROM diagnostics')}
            db.close()
            return result, rows, reports

    def test_phase_a_power_set_is_stored_and_phase_b_rails_absent(self):
        result, rows, _ = self.run_case(Scenario('phase-a', 'Phase A.', minutes=30))
        self.assertEqual((result['failures'], result['metrics']['power_mismatches']), ([], []))
        self.assertEqual(len(rows), 30)
        for row in rows:
            self.assertTrue(set(PHASE_A_POWER) <= set(row), row)
            self.assertFalse(set(PHASE_B_RAILS) & set(row), row)       # absent, never null
            self.assertEqual(row['quality'], 'valid')
            self.assertTrue(all(row[name] is not None for name in PHASE_A_POWER))

    def test_health_reports_every_15_minutes_with_every_key(self):
        result, _, reports = self.run_case(Scenario('health', 'Health reports.', minutes=61))
        self.assertEqual(sorted(reports), [(1, 0), (1, 900), (1, 1800), (1, 2700), (1, 3600)])
        self.assertEqual(result['health_reports'], {'sent': 5, 'arrived_intact': 5, 'stored': 5,
                                                    'not_stored': [], 'mismatches': []})
        start = 1_800_000_000
        for (_, uptime), report in reports.items():
            self.assertEqual(set(report), set(HEALTH_KEYS))
            state = power_state(start + uptime)
            # Not measured in phase A: present as null (design section 3.3).
            for name in ('charger_reported_input_mv', 'charger_reported_input_ma', 'charger_reported_battery_mv',
                         'charger_temp_c', 'pack_temp_c', 'charger_active_input', 'charger_stage', 'last_crash_pc'):
                self.assertIn(name, report)
                self.assertIsNone(report[name], name)
            self.assertEqual(report['charger_reported_battery_ma'], state['charge_ma'])
            self.assertIs(report['charger_input_power_ok'], state['sun'] > 0)
            self.assertIs(report['charger_charging'], state['charge_ma'] > 0)
            self.assertIs(report['charger_fault'], False)
            self.assertAlmostEqual(report['battery_soc_pct'], state['soc'], delta=1 / 256)
            self.assertIsInstance(report['mcu_supply_mv'], int)
            self.assertIsInstance(report['power_monitor_temp_c'], float)
            self.assertEqual((report['boots_since_power_up'], report['tx_timeouts_since_boot'],
                              report['i2c_recoveries_since_boot']), (1, 0, 0))

    def test_node_reboot_sends_a_health_report(self):
        _, _, reports = self.run_case(Scenario('reboot', 'Reboot.', minutes=30, node_reboots=[7]))
        self.assertEqual(sorted(reports), [(1, 0), (2, 0), (2, 900)])
        # fault_boot_note (design section 6.2): epoch 1 is a power-on (count 1), the reboot a pin reset
        # that keeps the count; never a power-on with a count above 1.
        self.assertEqual((reports[(1, 0)]['reset_cause'], reports[(1, 0)]['boots_since_power_up']), ('power', 1))
        self.assertEqual((reports[(2, 0)]['reset_cause'], reports[(2, 0)]['boots_since_power_up']), ('pin', 2))
        self.assertEqual(reports[(2, 0)]['power_sensor_faults'], [])

    def test_faulted_battery_monitor_sends_null_fields_never_absent(self):
        scenario = Scenario('monitor', 'Battery INA228 fault.', minutes=46, monitor_faults=[[10, 35]],
                            require_latency_target=True)
        result, rows, reports = self.run_case(scenario)
        self.assertEqual(result['failures'], [])
        for row in rows:
            faulted = 10 <= row['sequence'] < 35
            self.assertTrue(set(PHASE_A_POWER) <= set(row), row)
            self.assertEqual([row[n] is None for n in BATTERY_MONITOR_FIELDS['A']], [faulted] * 6, row)
            self.assertIsNotNone(row['batt_mv'])            # the gauge still measures the cell
            self.assertIsNotNone(row['charger_input_mv'])   # the divider is not the INA228
            self.assertEqual(row['quality'], 'partial' if faulted else 'valid')
        self.assertIsNone(reports[(1, 900)]['power_monitor_temp_c'])
        self.assertIsNotNone(reports[(1, 2700)]['power_monitor_temp_c'])
        self.assertEqual(set(reports[(1, 900)]), set(HEALTH_KEYS))

    def test_phase_b_profile_fills_every_rail(self):
        result, rows, _ = self.run_case(Scenario('phase-b', 'Phase B.', minutes=20, power_profile='B',
                                                 monitor_faults=[[5, 10]]))
        self.assertEqual(result['failures'], [])
        for row in rows:
            self.assertTrue(set(PHASE_A_POWER + PHASE_B_RAILS) <= set(row), row)
            self.assertEqual((row['usb_mv'], row['usb_current_ma']), (0, 0))   # never with solar
            self.assertIsNotNone(row['load_mv'])     # the load INA228, not the battery one, in phase B
        self.assertIsNone(rows[6]['batt_current_ma'])

    def test_lost_or_changed_health_reports_fail_the_verdict(self):
        from ws0 import service
        result, _, _ = self.run_case(Scenario('dropped', 'Store drops reports.', minutes=20),
                                     [(service.Gateway, 'receive_diagnostic', lambda *a: None)])
        self.assertEqual(result['failures'], ['health_reports_not_stored'])
        self.assertEqual(result['health_reports']['not_stored'], [[1, 0], [1, 900]])
        real = service.health_report
        def changed(payload):
            report, problems = real(payload)
            return report | {'charger_reported_input_mv': 5000}, problems
        result, _, _ = self.run_case(Scenario('changed', 'Changed report.', minutes=5),
                                     [(service, 'health_report', changed)])
        self.assertEqual(result['failures'], ['health_report_mismatches'])
        self.assertEqual(result['health_reports']['mismatches'], [[1, 0, 'charger_reported_input_mv']])

    def test_health_oracle(self):
        sent = {'at': 1_800_000_000, 'epoch': 1, 'uptime': 0, 'monitor_fault': False}
        state = power_state(sent['at'])
        good = dict.fromkeys(HEALTH_KEYS) | {
            'epoch': 1, 'uptime_s': 0, 'boots_since_power_up': 1, 'crashes_since_power_up': 0,
            'tx_timeouts_since_boot': 0, 'i2c_recoveries_since_boot': 0, 'charger_fault': False,
            'charger_input_power_ok': state['sun'] > 0, 'charger_charging': state['charge_ma'] > 0,
            'charger_reported_battery_ma': state['charge_ma'], 'battery_soc_pct': state['soc'],
            'battery_soc_rate_pct_h': state['soc_rate'], 'mcu_supply_mv': 3300, 'power_monitor_temp_c': 28.0}
        self.assertEqual(health_mismatches(good, sent), [])
        self.assertEqual(health_mismatches(good | {'power_monitor_temp_c': None}, sent), ['power_monitor_temp_c'])
        self.assertEqual(health_mismatches(good, sent | {'monitor_fault': True}), ['power_monitor_temp_c'])
        self.assertEqual(health_mismatches(good | {'charger_fault': 0}, sent), ['charger_fault'])   # a bool, not 0
        self.assertEqual(health_mismatches(good | {'battery_soc_pct': state['soc'] + 0.1}, sent), ['battery_soc_pct'])
        self.assertEqual(health_mismatches(good | {'charger_reported_battery_ma': None}, sent),
                         ['charger_reported_battery_ma'])
        self.assertEqual(health_mismatches(good | {'mcu_supply_mv': None}, sent), ['mcu_supply_mv'])
        missing = {k: v for k, v in good.items() if k != 'charger_active_input'}
        self.assertEqual(health_mismatches(missing, sent), ['key_set'])
        self.assertEqual(health_mismatches(good | {'soc_gauge_pct': 50}, sent), ['key_set'])
        result = assess_health({(1, 0): sent}, [(1, 0, good), (1, 60, good)], {(1, 0), (1, 900)})
        self.assertEqual((result['stored'], result['not_stored'], result['mismatches']),
                         (2, [[1, 900]], [[1, 60, 'not_sent']]))

    def test_assess_compares_power_fields(self):
        record = {'session': '1', 'sequence': 1, 'quality': 'valid', 'time_quality': 'synchronized',
                  'batt_mv': 3900, 'batt_current_ma': -35}
        expected = {('1', 1): (record, 1000)}
        row = record | {'received_at': 1001, '_effective': 1000, '_basis': 'synchronized'}
        self.assertEqual(assess(expected, [row], 1002)['power_mismatches'], [])
        for changed in ({'batt_current_ma': 35}, {'batt_current_ma': None}, {'usb_mv': None}):
            result = assess(expected, [row | changed], 1002)
            self.assertEqual((result['power_mismatches'], result['payload_mismatches']), ([['1', 1]], [['1', 1]]))
        absent = {k: v for k, v in row.items() if k != 'batt_current_ma'}
        self.assertEqual(assess(expected, [absent], 1002)['power_mismatches'], [['1', 1]])
