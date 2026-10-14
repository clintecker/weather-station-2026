"""Gap G9: the gateway never hands a measured-wrong host time to the node."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import tempfile
import unittest
from pathlib import Path
from ws0.__main__ import provision
from ws0.clock import HostClock
from ws0.protocol import KIND_ACK, unpack_reply, unseal
from ws0.service import Gateway, load_config
from ws0.simulator import Node


class ClockTests(unittest.TestCase):
    def clock(self, results):
        results = list(results)
        def measure(server):
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r if isinstance(r, tuple) else (r, 0.02)
        return HostClock(measure=measure, log=lambda *_: None, clock=lambda: 1000.0)

    def test_states(self):
        c = self.clock([0.2, 3.5, OSError('no network'), 0.1])
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('ok', True))
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('bad', False))
        c.check(); self.assertEqual(c.status()['state'], 'bad')  # unreachable does not clear 'bad'
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('ok', True))
        self.assertEqual(self.clock([OSError('x')]).may_issue_time(), True)  # never measured: unverified

    def test_bad_clock_ack_carries_no_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'s'; provision(root); cfg = load_config(root/'gateway.json')
            gateway, node = Gateway(cfg, root), Node(cfg, root)
            try:
                gateway.clock = self.clock([5.0]); gateway.clock.check()
                ack = gateway.receive(node.packet(node.sample(1000)), 1001)
                self.assertEqual(unpack_reply(unseal(node.key, 1, KIND_ACK, ack))[2], 0)
                self.assertEqual(gateway.status()['host_clock']['state'], 'bad')
                gateway.clock = self.clock([0.0]); gateway.clock.check()
                ack = gateway.receive(node.packet(node.sample(1060)), 1061)
                self.assertEqual(unpack_reply(unseal(node.key, 1, KIND_ACK, ack))[2], 1061)
            finally:
                for db in (gateway.store.db, gateway.nonces.db, node.db, node.nonces.db): db.close()

    def test_slow_round_trip_is_not_called_bad(self):
        # 2026-10-13 20:44Z: offset +1.114 s with rtt 2.099 s was logged as 'bad'. An SNTP offset is
        # only known to within rtt/2, so a clock is 'bad' only when it is wrong even at the edge of
        # that bound; a measurement too coarse to decide leaves the state unverified.
        c = self.clock([(1.114, 2.099), (1.6, 0.4), (0.9, 0.3)])
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('unverified', True))
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('bad', False))
        c.check(); self.assertEqual((c.status()['state'], c.may_issue_time()), ('bad', False))  # 0.9+0.15 > 1: cannot clear 'bad'

    def test_retries_soon_after_a_failed_check(self):
        c = self.clock([OSError('timed out'), 0.1])
        from ws0.clock import CHECK_PERIOD_S, RETRY_S
        self.assertEqual(c.check(), RETRY_S)
        self.assertEqual(c.check(), CHECK_PERIOD_S)
        self.assertLess(RETRY_S, CHECK_PERIOD_S)

    def test_name_lookup_is_outside_the_timed_exchange(self):
        # The DNS lookup used to happen inside sendto(), after t1: its delay counted as outbound
        # network time and showed up as offset = rtt/2 (+0.554 s with rtt 1.104 s in serve.log).
        import socket, struct, time
        from unittest.mock import patch
        from ws0 import clock as clockmod
        def ntp(t):
            t += clockmod.NTP_EPOCH
            return struct.pack('>II', int(t), int((t % 1) * 2**32))
        class FakeSocket:
            def __init__(self, *a): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def settimeout(self, t): pass
            def sendto(self, data, addr):
                if not isinstance(addr[0], str) or not addr[0][0].isdigit():
                    time.sleep(0.4)  # a name lookup inside the timed window
            def recvfrom(self, n):
                now = time.time()  # server clock == local clock: true offset 0
                return bytes([0x24, 2]) + bytes(30) + ntp(now) + ntp(now), None
        with patch.object(clockmod.socket, 'getaddrinfo', side_effect=lambda *a, **k: (time.sleep(0.4), [(socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('192.0.2.1', 123))])[1]), \
             patch.object(clockmod.socket, 'socket', FakeSocket):
            offset, rtt = clockmod.sntp_offset('pool.example')
        self.assertLess(abs(offset), 0.05)
        self.assertLess(rtt, 0.05)

    def test_thread_loop_survives_unexpected_errors(self):
        """GW10: a measurement that raises something other than OSError/ValueError, or a log
        callback that fails, must not end the checking loop."""
        from ws0.clock import RETRY_S
        calls, delays = [], []
        def measure(server):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('surprise')
            return 0.1, 0.02
        logged = []
        def log(text):
            logged.append(text)
            if len(logged) == 1:
                raise OSError('log file gone')
        c = HostClock(measure=measure, log=log, clock=lambda: 1000.0)
        def sleep(delay):
            delays.append(delay)
            if len(delays) == 2:
                raise StopIteration
        with self.assertRaises(StopIteration):
            c.run(sleep=sleep)
        self.assertEqual(delays[0], RETRY_S)                # the failure was retried soon
        self.assertEqual(c.status()['state'], 'ok')         # and the next check worked

    def test_real_sntp_query(self):
        from ws0.clock import sntp_offset
        try:
            offset, rtt = sntp_offset('time.apple.com', timeout=3)
        except OSError:
            self.skipTest('no network')
        self.assertLess(abs(offset), 60); self.assertLess(rtt, 3)


if __name__ == '__main__':
    unittest.main()
