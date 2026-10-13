"""Gap G9: the gateway never hands a measured-wrong host time to the node."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import tempfile
import unittest
from pathlib import Path
from ws0.__main__ import provision
from ws0.clock import HostClock
from ws0.protocol import ACK, unseal
from ws0.service import Gateway, load_config
from ws0.simulator import Node


class ClockTests(unittest.TestCase):
    def clock(self, results):
        results = list(results)
        def measure(server):
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r, 0.02
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
                self.assertEqual(ACK.unpack(unseal(node.key, 1, 2, ack))[2], 0)
                self.assertEqual(gateway.status()['host_clock']['state'], 'bad')
                gateway.clock = self.clock([0.0]); gateway.clock.check()
                ack = gateway.receive(node.packet(node.sample(1060)), 1061)
                self.assertEqual(ACK.unpack(unseal(node.key, 1, 2, ack))[2], 1061)
            finally:
                for db in (gateway.store.db, gateway.nonces.db, node.db, node.nonces.db): db.close()

    def test_real_sntp_query(self):
        from ws0.clock import sntp_offset
        try:
            offset, rtt = sntp_offset('time.apple.com', timeout=3)
        except OSError:
            self.skipTest('no network')
        self.assertLess(abs(offset), 60); self.assertLess(rtt, 3)


if __name__ == '__main__':
    unittest.main()
