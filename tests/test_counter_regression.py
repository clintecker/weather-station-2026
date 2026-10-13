"""Review item P4: the gateway detects AES-CCM nonce reuse by the node.

The node seals OBS (kind 1) and DIAG (kind 4) frames from one strictly increasing 64-bit
counter (firmware store_next_counter; WIPE keeps it). The gateway keeps a durable high-water
mark per key binding. A frame at or below it is never answered or stored; it is kept as a
rejection and raises a loud status alarm.
"""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import io
import sqlite3
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ws0.harness import Campaign, Scenario
from ws0.protocol import DIAG, KIND_DIAG, Nonces, frame_counter, seal
from ws0.service import CounterRegression, Gateway
from ws0.simulator import Node
from ws0 import __main__ as cli

KEY = bytes(range(16))
ALARM = 'possible key reuse: re-key the node'


def diag_payload(uptime, epoch=1):
    return DIAG.pack(epoch, uptime, 0, 0, 0, 0, 0, 0, 1, 0)


class CounterRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = {'station': 'simulation-01', 'station_id': 1, 'mode': 'simulation',
                    'radio_key': KEY.hex(), 'api_token': 'x' * 32, 'mqtt': {'enabled': False}}
        for name, kind in [('node', 1), ('gateway', 2)]:
            Nonces(self.dir/f'{name}-nonces.sqlite3', KEY, 1, kind, create=True).db.close()
        self.node = Node(self.cfg, self.dir)
        self.node.synced = True
        self.gateway = Gateway(self.cfg, self.dir)
        self.now = 1_800_000_000

    def tearDown(self):
        for db in (self.node.db, self.node.nonces.db, self.gateway.store.db, self.gateway.nonces.db):
            db.close()
        self.tmp.cleanup()

    def restart_gateway(self):
        self.gateway.store.db.close(); self.gateway.nonces.db.close()
        self.gateway = Gateway(self.cfg, self.dir)

    def wipe_node_counter(self):
        """A pre-0f456040fe54 WIPE (or another board) with the same key: the counter restarts."""
        self.node.nonces.db.close()
        (self.dir/'node-nonces.sqlite3').unlink()
        self.node.nonces = Nonces(self.dir/'node-nonces.sqlite3', KEY, 1, 1, create=True)

    def minute(self):
        self.now += 60
        return self.node.sample(self.now)

    def deliver(self, record):
        reply = self.gateway.receive(self.node.packet(record), self.now)
        self.node.handle_reply(reply)
        return reply

    def stored(self):
        return self.gateway.store.db.execute('SELECT count(*) FROM observations').fetchone()[0]

    def diagnostics(self):
        return self.gateway.store.db.execute('SELECT count(*) FROM diagnostics').fetchone()[0]

    def rejections(self):
        return self.gateway.store.db.execute(
            "SELECT reason, frame_hex FROM rejections WHERE reason='counter_regression'").fetchall()

    def assert_quiet(self):
        status = self.gateway.status()
        self.assertIsNone(status['alarm'])
        self.assertEqual(status['node_counter']['counter_regression'], 0)

    def test_replayed_obs_gets_no_reply_and_is_not_stored(self):
        first = self.node.packet(self.minute())
        self.assertIsNotNone(self.gateway.receive(first, self.now))
        second = self.minute()
        self.deliver(second)
        rows = self.stored()
        with self.assertRaises(CounterRegression):
            self.gateway.receive(first, self.now)        # an old frame, replayed later
        with self.assertRaises(CounterRegression):
            self.gateway.receive(first, self.now)        # and again
        self.assertEqual(self.stored(), rows)
        status = self.gateway.status()
        self.assertEqual(status['alarm'], ALARM)
        self.assertEqual(status['node_counter']['counter_regression'], 2)
        self.assertEqual(status['node_counter']['last_regression_counter'], frame_counter(first))
        self.assertEqual([r[1] for r in self.rejections()], [first.hex(), first.hex()])

    def test_exact_duplicate_of_latest_frame_is_not_answered(self):
        frame = self.node.packet(self.minute())
        self.gateway.receive(frame, self.now)
        with self.assertRaises(CounterRegression):
            self.gateway.receive(frame, self.now)

    def test_replayed_and_reused_diag_are_not_stored(self):
        self.deliver(self.minute())
        report = seal(KEY, 1, KIND_DIAG, self.node.nonces, diag_payload(100))
        self.assertIsNone(self.gateway.receive(report, self.now))
        self.assertEqual(self.diagnostics(), 1)
        with self.assertRaises(CounterRegression):
            self.gateway.receive(report, self.now)
        self.wipe_node_counter()
        reused = seal(KEY, 1, KIND_DIAG, self.node.nonces, diag_payload(200, epoch=2))
        with self.assertRaises(CounterRegression):
            self.gateway.receive(reused, self.now)
        self.assertEqual(self.diagnostics(), 1)
        self.assertEqual(self.gateway.status()['node_counter']['counter_regression'], 2)
        self.assertEqual(self.gateway.status()['alarm'], ALARM)

    def test_obs_and_diag_share_one_counter_space(self):
        self.deliver(self.minute())
        report = seal(KEY, 1, KIND_DIAG, self.node.nonces, diag_payload(100))
        self.gateway.receive(report, self.now)
        self.assertEqual(self.gateway.status()['node_counter']['max_node_counter'], frame_counter(report))
        self.deliver(self.minute())
        self.assert_quiet()

    def test_wipe_and_reuse_alarms_on_first_frame(self):
        for _ in range(5):
            self.deliver(self.minute())
        self.assert_quiet()
        self.wipe_node_counter()
        rows = self.stored()
        record = self.minute()
        frame = self.node.packet(record)
        self.assertEqual(frame_counter(frame), 1)
        with self.assertRaises(CounterRegression):
            self.gateway.receive(frame, self.now)
        self.assertEqual(self.stored(), rows)
        self.assertEqual(self.gateway.status()['alarm'], ALARM)
        self.assertEqual(self.gateway.status()['node_counter']['last_regression_counter'], 1)
        self.assertEqual(len(self.rejections()), 1)

    def test_unauthenticated_frame_never_moves_the_mark(self):
        self.deliver(self.minute())
        mark = self.gateway.status()['node_counter']['max_node_counter']
        forged = bytearray(self.node.packet(self.minute()))
        forged[8:16] = struct.pack('>Q', 2**40)  # huge counter, tag no longer valid
        with self.assertRaises(Exception) as caught:
            self.gateway.receive(bytes(forged), self.now)
        self.assertNotIsInstance(caught.exception, CounterRegression)
        self.assertEqual(self.gateway.status()['node_counter']['max_node_counter'], mark)
        self.deliver(self.minute())
        self.assert_quiet()

    def test_mark_survives_gateway_restart(self):
        old = self.node.packet(self.minute())
        self.gateway.receive(old, self.now)
        self.deliver(self.minute())
        mark = self.gateway.status()['node_counter']['max_node_counter']
        self.restart_gateway()
        self.assertEqual(self.gateway.status()['node_counter']['max_node_counter'], mark)
        with self.assertRaises(CounterRegression):
            self.gateway.receive(old, self.now)
        self.restart_gateway()  # the alarm also survives restart
        self.assertEqual(self.gateway.status()['alarm'], ALARM)
        self.assertEqual(self.gateway.status()['node_counter']['counter_regression'], 1)

    def test_mark_is_raised_before_commit(self):
        """Write-ahead: a commit failure (no ACK) never leaves the mark below a seen frame."""
        record = self.minute()
        frame = self.node.packet(record)
        with mock.patch.object(self.gateway.store, 'ingest', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.gateway.receive(frame, self.now)
        self.assertEqual(self.gateway.status()['node_counter']['max_node_counter'], frame_counter(frame))
        self.deliver(record)  # the node retries with a fresh counter and succeeds
        self.assertEqual(self.stored(), 1)
        self.assert_quiet()

    def test_normal_operation_retries_backfill_and_restarts_never_alarm(self):
        for minute in range(40):
            record = self.minute()
            frames = [self.node.packet(record)]
            for old in self.node.backfill():
                if old['sequence'] != record['sequence'] or old['session'] != record['session']:
                    frames.append(self.node.packet(old))
            for i, frame in enumerate(frames):
                if 10 <= minute < 15:
                    continue  # link outage: frames lost on air, journal grows
                reply = self.gateway.receive(frame, self.now)
                if minute % 3 or i:  # every third live ACK is lost: the node retries later
                    self.node.handle_reply(reply)
            if minute in (7, 20):
                self.restart_gateway()
            if minute in (12, 25):
                self.node.db.close(); self.node.nonces.db.close()
                self.node = Node(self.cfg, self.dir)
            if minute == 30:
                self.gateway.receive(seal(KEY, 1, KIND_DIAG, self.node.nonces, diag_payload(5, self.node.epoch)),
                                     self.now)
        self.assertGreater(self.stored(), 30)
        self.assert_quiet()

    def test_simulator_retry_uses_a_fresh_counter(self):
        record = self.minute()
        first, retry = self.node.packet(record), self.node.packet(record)
        self.assertGreater(frame_counter(retry), frame_counter(first))
        self.gateway.receive(first, self.now)
        self.assertIsNotNone(self.gateway.receive(retry, self.now))  # retry of a stored record: ACKed
        self.assert_quiet()

    def test_existing_nonce_state_gains_a_zero_mark(self):
        """A gateway directory from before P4 opens with mark 0 and no alarm."""
        self.gateway.nonces.db.close()
        db = sqlite3.connect(self.dir/'gateway-nonces.sqlite3')
        db.execute('DROP TABLE node_counter'); db.commit(); db.close()
        self.gateway.store.db.close()
        self.gateway = Gateway(self.cfg, self.dir)
        self.assertEqual(self.gateway.status()['node_counter']['max_node_counter'], 0)
        self.deliver(self.minute())
        self.assert_quiet()

    def test_provision_node_reports_mark(self):
        self.deliver(self.minute())
        mark = self.gateway.status()['node_counter']['max_node_counter']
        state = cli.node_counter_mark(self.dir)
        self.assertEqual(state['max_node_counter'], mark)
        self.assertEqual(state['counter_regression'], 0)
        self.assertIsNone(cli.node_counter_mark(self.dir/'missing'))
        out = io.StringIO()
        with redirect_stdout(out):
            cli.print_counter_mark(state)
        self.assertIn(f'high-water mark: {mark}', out.getvalue())
        # A board whose next counter is at or below the mark would reuse nonces with this key.
        with self.assertRaises(SystemExit):
            cli.check_node_counter({'ctr': str(mark)}, state)
        cli.check_node_counter({'ctr': str(mark+1)}, state)
        cli.check_node_counter({}, state)  # older firmware without ctr=: print only


class HarnessCounterTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as tmp:
            return Campaign(scenario, Path(tmp)/'case').run()

    def test_restarts_and_losses_without_wire_replays_never_alarm(self):
        result = self.run_case(Scenario('quiet', 'No wire duplication or reordering.', minutes=60,
                                        uplink_loss=.1, ack_loss=.3, link_outages=[[10, 15]],
                                        commit_failures=[[20, 22]], node_reboots=[8, 30],
                                        gateway_reboots=[12, 30, 40]))
        self.assertTrue(result['scenario_pass'], result['failures'])
        self.assertEqual(result['counter_regressions'], 0)

    def test_wire_duplicates_are_detected_exactly(self):
        result = self.run_case(Scenario('dups', 'Duplicated and delayed frames.', minutes=60,
                                        duplicates=.3, max_delay_seconds=15, gateway_reboots=[30]))
        self.assertTrue(result['scenario_pass'], result['failures'])
        self.assertGreater(result['counter_regressions'], 0)
        self.assertEqual(result['counter_regressions'], result['expected_counter_regressions'])


if __name__ == '__main__':
    unittest.main()
