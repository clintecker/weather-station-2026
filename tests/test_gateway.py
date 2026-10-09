"""Regression checks for history integrity and freshness failures."""
import tempfile
import unittest
from pathlib import Path
from gateway import Store


def reading(**updates):
    """Use deterministic simulated UTC times for repeatable age checks."""
    value = dict(version=1, station='test', session='boot-1', sequence=1,
                 sampled_at=1000, time_quality='synchronized', temperature_c=20,
                 humidity_pct=40, quality='valid')
    return value | updates


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'test.db')
        self.store = Store(self.path)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_replay_and_restart(self):
        self.assertTrue(self.store.ingest(reading(), 1001))
        self.store.db.close()
        self.store = Store(self.path)
        self.assertFalse(self.store.ingest(reading(), 1100))
        self.assertEqual(self.store.latest('test', 1100)['received_at'], 1001)
        self.assertTrue(self.store.ingest(reading(session='boot-2'), 1101))

    def test_collision(self):
        self.store.ingest(reading())
        with self.assertRaises(ValueError):
            self.store.ingest(reading(temperature_c=21))

    def test_backfill_does_not_replace_live(self):
        self.store.ingest(reading(), 1001)
        self.store.ingest(reading(sequence=0, sampled_at=900), 1100)
        self.assertEqual(self.store.latest('test', 1100)['observation']['sequence'], 1)
        self.assertFalse(self.store.latest('test', 1180)['available'])

    def test_unknown_clock_and_future(self):
        self.store.ingest(reading(sampled_at=None, time_quality='unknown'))
        self.assertFalse(self.store.latest('test')['available'])
        self.store.ingest(reading(sequence=2, sampled_at=2000))
        self.assertFalse(self.store.latest('test', 1000)['available'])

    def test_fault_and_invalid_values(self):
        self.store.ingest(reading(quality='sensor_fault', temperature_c=None, humidity_pct=None))
        self.assertFalse(self.store.latest('test', 1001)['available'])
        for value in [float('nan'), float('inf'), True, 101]:
            with self.assertRaises(ValueError):
                self.store.ingest(reading(sequence=2, humidity_pct=value))


if __name__ == '__main__':
    unittest.main()
