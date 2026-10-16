"""Regression checks for history integrity and freshness failures."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability

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

class SchemaTests(unittest.TestCase):
    """Characterization of gateway.validate (design 5.7): every rule, its message, and the order
    in which the rules are applied (the first failing rule names the error)."""
    def check(self, record, message):
        from gateway import validate
        with self.assertRaises(ValueError) as caught:
            validate(record)
        self.assertEqual(str(caught.exception), message, repr(record))

    def test_valid_records_pass(self):
        from gateway import validate
        for record in (reading(), reading(sampled_at=None, time_quality='unknown'),
                       reading(sampled_at=1000.5), reading(humidity_pct=None, quality='partial'),
                       reading(wind_speed_ms=0, wind_dir_deg=None, wind_calm=True),
                       reading(wind_speed_ms=2.5, wind_dir_deg=90, wind_calm=False),
                       reading(wind_speed_ms=None, wind_dir_deg=None, wind_calm=False, quality='partial'),
                       reading(qualifiers={}), reading(qualifiers={'temperature_c': 'suspected_icing',
                                                                   'wind_speed_ms': 'outside_envelope'}),
                       reading(rain_tips=3, station='A-z_9', session='x' * 64, sequence=2**32 - 1,
                               uptime_s=0, calibration_revision=255, energy_state='critical')):
            validate(record)

    def test_each_rule_and_its_message(self):
        no_quality = reading(); del no_quality['quality']
        cases = [
            ([], 'Unsupported version'),
            (reading(version=4), 'Unsupported version'),
            (reading(version=True), 'Unsupported version'),
            (reading(version=5.0), 'Unsupported version'),
            ({k: v for k, v in reading().items() if k != 'version'}, 'Unsupported version'),
            (no_quality, 'Missing record fields'),
            (reading(bogus=1), 'Unexpected record fields'),
            (reading(dew_point_c=1), 'Unexpected record fields'),
            (reading(wind_calm=True), 'wind_calm goes with wind_dir_deg'),
            (reading(wind_speed_ms=1, wind_dir_deg=90), 'wind_calm goes with wind_dir_deg'),
            (reading(station='a b'), 'Invalid identity'),
            (reading(station=''), 'Invalid identity'),
            (reading(session='x' * 65), 'Invalid identity'),
            (reading(session=5), 'Invalid identity'),
            (reading(sequence=-1), 'Invalid sequence'),
            (reading(sequence=2**32), 'Invalid sequence'),
            (reading(sequence=True), 'Invalid sequence'),
            (reading(uptime_s=1.0), 'Invalid uptime_s'),
            (reading(uptime_s=2**32), 'Invalid uptime_s'),
            (reading(calibration_revision=256), 'Invalid calibration_revision'),
            (reading(energy_state='full'), 'Invalid energy state'),
            (reading(time_quality='gps'), 'Invalid time quality'),
            (reading(time_quality='unknown'), 'Unknown clock must have null time'),
            (reading(sampled_at=None), 'Invalid UTC timestamp'),
            (reading(sampled_at=0), 'Invalid UTC timestamp'),
            (reading(sampled_at=2**32), 'Invalid UTC timestamp'),
            (reading(sampled_at=float('nan')), 'Invalid UTC timestamp'),
            (reading(sampled_at=True), 'Invalid UTC timestamp'),
            (reading(sampled_at='1000'), 'Invalid UTC timestamp'),
            (reading(humidity_pct=40.001), 'humidity_pct: not an exact catalog value'),
            (reading(temperature_c=True), 'temperature_c: not an exact catalog value'),
            (reading(rain_tips=float('inf')), 'rain_tips: not an exact catalog value'),
            (reading(wind_speed_ms=1, wind_dir_deg=None, wind_calm=1), 'Invalid wind_calm'),
            (reading(wind_speed_ms=1, wind_dir_deg=90, wind_calm=True), 'Invalid wind_calm'),
            (reading(wind_speed_ms=None, wind_dir_deg=90, wind_calm=False), 'Wind direction without a valid speed'),
            (reading(wind_speed_ms=None, wind_dir_deg=None, wind_calm=True), 'Wind direction without a valid speed'),
            (reading(qualifiers=[]), 'Invalid qualifiers'),
            (reading(qualifiers={'pressure_hpa': None}), 'Invalid qualifiers'),
            (reading(qualifiers={'th_samples': 'suspected_icing'}), 'Invalid qualifiers'),
            (reading(qualifiers={'temperature_c': 'frozen'}), 'Invalid qualifiers'),
            (reading(quality='partial'), 'Quality does not match the field values'),
            ({k: v for k, v in reading().items() if k not in ('temperature_c', 'humidity_pct')}, 'No measurements'),
            # Order: the earlier rule wins when several fail.
            (reading(version=4, bogus=1), 'Unsupported version'),
            (reading(station='a b', sequence=-1, energy_state='x'), 'Invalid identity'),
            (reading(sequence=-1, uptime_s=-1), 'Invalid sequence'),
            (reading(energy_state='x', time_quality='x'), 'Invalid energy state'),
            (reading(sampled_at=None, humidity_pct=40.001), 'Invalid UTC timestamp'),
            (reading(humidity_pct=40.001, qualifiers=[]), 'humidity_pct: not an exact catalog value'),
            (reading(wind_speed_ms=None, wind_dir_deg=90, wind_calm=True), 'Invalid wind_calm'),
            (reading(wind_speed_ms=None, wind_dir_deg=90, wind_calm=False, qualifiers=[]),
             'Wind direction without a valid speed'),
        ]
        for record, message in cases:
            self.check(record, message)


class LatestReasonTests(unittest.TestCase):
    """Characterization of Store.latest's freshness verdict and its precedence, from stored rows."""
    def test_reasons(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'l.db')
            try:
                self.assertEqual(store.latest('test'), {'available': False, 'reason': 'no_observation'})
                fault = reading(quality='sensor_fault', temperature_c=None, humidity_pct=None)
                calm = reading(wind_speed_ms=0, wind_dir_deg=None, wind_calm=True, humidity_pct=None,
                               quality='partial')
                #  record, received, effective, uncertainty, now -> available, reason, fields
                cases = [
                    (reading(), 1001, 1000, 1, 1100, True, 'fresh', True),
                    (reading(), 1001, 1000, None, 1179, True, 'fresh', True),
                    (reading(), 1001, 1000, 1, 1180, False, 'stale_or_clock_step', False),
                    (reading(), 1001, 1000, 1, 999, False, 'stale_or_clock_step', False),
                    (reading(), 1001, None, None, 1001, False, 'unknown_clock', False),
                    (reading(), 1001, 1007, 1, 1010, False, 'future_clock_at_receipt', False),
                    (reading(), 1001, 1007, 11, 1010, False, 'future_clock_at_receipt', False),
                    (reading(), 1001, 1006, 1, 1010, True, 'fresh', True),
                    (reading(), 1001, 1000, 11, 1001, False, 'time_uncertain', False),
                    (reading(), 1001, 1000, 10, 1001, True, 'fresh', True),
                    (fault, 1001, 1000, 1, 1001, False, 'sensor_fault', False),
                    (fault, 1001, 1000, 11, 1001, False, 'time_uncertain', False),
                    (fault, 1001, 1000, 1, 1500, False, 'sensor_fault', False),
                    (calm, 1001, 1000, 1, 1001, True, 'fresh', None),
                ]
                for i, (record, received, effective, uncertainty, now, available, reason, timely) in enumerate(cases):
                    with store.db:
                        store.db.execute('DELETE FROM observations')
                        store.db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)',
                                         ('test', '1', i, record['sampled_at'], received, json.dumps(record),
                                          60, effective, 'synchronized', uncertainty))
                    got = store.latest('test', now)
                    self.assertEqual((got['available'], got['reason']), (available, reason), i)
                    self.assertEqual(got['age_seconds'], None if effective is None else now - effective)
                    expected = ({'temperature_c': True, 'humidity_pct': False, 'wind_speed_ms': True,
                                 'wind_dir_deg': True} if timely is None else
                                {n: timely and record[n] is not None for n in ('temperature_c', 'humidity_pct')})
                    self.assertEqual(got['fields_available'], expected, i)
                    self.assertEqual(set(got['labels']), set(expected))
                    self.assertEqual((got['received_at'], got['effective_sampled_at'], got['time_uncertainty_s'],
                                      got['time_basis']), (received, effective, uncertainty, 'synchronized'))
            finally:
                store.db.close()


class ReadOnlyOpen(unittest.TestCase):
    def test_reading_a_stopped_gateways_database_leaves_no_files(self):
        """CLI reads (provision-node's counter mark and epoch floor) may run as another user: with
        the gateway stopped they must not create -wal/-shm files that the service then can't open."""
        from gateway import open_read_only
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'o.sqlite3'
            store = Store(path)
            store.ingest(reading(), 1001)
            store.db.close()                              # last connection: WAL checkpointed, removed
            before = sorted(p.name for p in Path(tmp).iterdir())
            db = open_read_only(path)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 1)
            db.close()
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), before)
            store = Store(path)                           # and with the gateway running, it reads live data
            store.ingest(reading(sequence=2), 1002)
            db = open_read_only(path)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 2)
            db.close()
            store.db.close()

class DurabilityTests(unittest.TestCase):
    """Commits must reach stable storage on macOS before an ACK exists."""
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
