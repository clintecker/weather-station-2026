"""Regression checks for history integrity and freshness failures."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import tempfile
import unittest
from pathlib import Path
from gateway import Store


def reading(**updates):
    """Use deterministic simulated UTC times for repeatable age checks."""
    value = dict(version=5, station='test', session='boot-1', sequence=1, sampled_at=1000, uptime_s=60,
                 time_quality='synchronized', energy_state='normal', calibration_revision=0,
                 temperature_c=20, humidity_pct=40, quality='valid')
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
        for value in [float('nan'), float('inf'), True, 101, 40.001, '40']:
            with self.assertRaises(ValueError, msg=repr(value)):
                self.store.ingest(reading(sequence=2, humidity_pct=value))
        with self.assertRaises(ValueError):    # quality must match the values
            self.store.ingest(reading(sequence=3, humidity_pct=None))

    def test_one_dead_field_does_not_hide_the_others(self):
        self.store.ingest(reading(humidity_pct=None, quality='partial'), 1001)
        latest = self.store.latest('test', 1001)
        self.assertTrue(latest['available'])
        self.assertEqual(latest['fields_available'], {'temperature_c': True, 'humidity_pct': False})
        self.assertEqual(latest['units'], {'temperature_c': '°C', 'humidity_pct': '%'})

    def test_fifteen_second_summary_fields(self):
        """15-s sampling (PRD section 9): the minute's mean, extrema and sample count. A minute with
        no valid sample is still a sensor fault: the sample count (0) is metadata, not a reading."""
        summary = dict(temperature_min_c=19.5, temperature_max_c=20.5, humidity_min_pct=39.5,
                       humidity_max_pct=40.25, th_samples=4)
        self.store.ingest(reading(**summary), 1001)
        self.assertEqual(self.store.latest('test', 1001)['observation']['th_samples'], 4)
        dead = dict(temperature_c=None, humidity_pct=None, temperature_min_c=None, temperature_max_c=None,
                    humidity_min_pct=None, humidity_max_pct=None, th_samples=0)
        with self.assertRaises(ValueError):          # th_samples does not make it 'partial'
            self.store.ingest(reading(sequence=2, quality='partial', **dead))
        self.store.ingest(reading(sequence=2, sampled_at=1060, quality='sensor_fault', **dead), 1061)
        self.assertEqual(self.store.latest('test', 1061)['reason'], 'sensor_fault')
        with self.assertRaises(ValueError):          # at most 60 samples a minute
            self.store.ingest(reading(sequence=3, **(summary | {'th_samples': 61})))

    def test_dew_point_is_derived_not_stored(self):
        from ws0.fields import dew_point
        self.assertEqual(dew_point(20, 50), 9.26)            # by hand: gamma 0.6462, Td 157.10 / 16.974
        self.assertEqual(dew_point(6.74, 86.68), 4.67)       # the lab AC outlet, 2026-10-14
        self.assertEqual((dew_point(20, 100), dew_point(20, 0), dew_point(None, 50)), (20.0, None, None))
        self.store.ingest(reading(temperature_c=6.74, humidity_pct=86.68), 1001)
        latest = self.store.latest('test', 1001)
        self.assertEqual(latest['derived'], {'dew_point_c': 4.67})
        self.assertNotIn('dew_point_c', latest['observation'])       # the stored payload is unchanged

    def test_counters_never_decrease_in_sequence_order(self):
        rain = lambda seq, tips: reading(sequence=seq, sampled_at=1000 + 60 * seq, rain_tips=tips)
        self.store.ingest(rain(5, 10), 1400)
        self.store.ingest(rain(2, 7), 1401)          # backfill arriving after a later record: fine
        self.store.ingest(rain(3, 7), 1402)
        for seq, tips in ((4, 11), (4, 6), (6, 9)):  # above its successor, below its predecessor
            with self.assertRaises(ValueError, msg=(seq, tips)):
                self.store.ingest(rain(seq, tips), 1403)
        self.store.ingest(rain(4, 8), 1404)
        self.store.ingest(reading(session='boot-2', sequence=0, rain_tips=0), 1405)   # new epoch starts at 0



class ReconstructionTests(unittest.TestCase):
    def test_bounded_update_matches_a_full_rescan(self):
        """A new reference recomputes only the readings between its neighbouring references. After
        every ingest, in any arrival order, with quarantined references and untimed readings mixed
        in, the time columns must equal a full rescan of the epoch."""
        import random
        cols = 'SELECT sequence,effective_at,time_basis,time_uncertainty_s FROM observations ORDER BY sequence'
        for seed in range(6):
            rng = random.Random(seed)
            records = []
            for seq in range(120):
                uptime = 60 * seq + rng.randint(0, 5)
                if rng.random() < 0.6:
                    records.append((reading(session='9', sequence=seq, uptime_s=uptime, sampled_at=None,
                                            time_quality='unknown'), 5000 + uptime))
                else:
                    ahead = rng.random() < 0.1    # clock ahead of its receipt: quarantined, never a reference
                    t = 100_000 + uptime + rng.randint(-2, 2)
                    records.append((reading(session='9', sequence=seq, uptime_s=uptime, sampled_at=t),
                                    t - (60 if ahead else -1)))
            rng.shuffle(records)
            with tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp) / 'r.db')
                try:
                    for i, (record, received) in enumerate(records):
                        store.ingest(record, received)
                        bounded = store.db.execute(cols).fetchall()
                        with store.db:
                            store.reconstruct('test', '9')     # full rescan as the reference answer
                        self.assertEqual(store.db.execute(cols).fetchall(), bounded, (seed, i))
                finally:
                    store.db.close()

class DurabilityTests(unittest.TestCase):
    """Gap G4: commits must reach stable storage on macOS before an ACK exists."""
    def test_full_flush_pragmas_are_on(self):
        from unittest.mock import patch
        from ws0.protocol import Nonces
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WS0_UNSAFE_FAST_FSYNC': ''}):
            store = Store(Path(tmp)/'o.sqlite3')
            nonces = Nonces(Path(tmp)/'n.sqlite3', b'k'*16, 1, 2, create=True)
            try:
                for db in (store.db, nonces.db):
                    self.assertEqual(db.execute('PRAGMA fullfsync').fetchone()[0], 1)
                    self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0], 2)  # FULL
                    self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                self.assertEqual(store.db.execute('PRAGMA checkpoint_fullfsync').fetchone()[0], 1)
            finally:
                store.db.close(); nonces.db.close()


if __name__ == '__main__':
    unittest.main()
