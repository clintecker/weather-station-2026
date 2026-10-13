"""H01 scorer: denominators, categories and the strict pass rule."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import importlib.util
import tempfile
import unittest
from pathlib import Path
from gateway import Store

spec = importlib.util.spec_from_file_location('h01', Path(__file__).resolve().parent.parent/'tools/h01_report.py')
h01 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h01)
START = 1_800_000_000


def obs(seq, sampled, valid=True, session='1', uptime=None):
    return dict(version=2, station='s', session=session, sequence=seq, sampled_at=sampled,
                uptime_s=seq * 60 if uptime is None else uptime,
                time_quality='synchronized' if sampled is not None else 'unknown',
                temperature_c=20.0 if valid else None, humidity_pct=40.0 if valid else None,
                quality='valid' if valid else 'sensor_fault')


class H01ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'o.sqlite3')

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_perfect_run_passes(self):
        for m in range(60):
            self.store.ingest(obs(m, START + 60 * m + 5), START + 60 * m + 6)
        r = h01.score(self.store.db, 's', START, 1)
        self.assertEqual((r['intervals'], r['required_on_time_valid'], r['on_time_valid']), (60, 60, 60))
        self.assertEqual(r['verdict'], 'PASS')

    def test_categories_and_strict_rule(self):
        for m in range(60):
            if m == 10:
                continue                                                    # missing
            sampled = START + 60 * m + 5
            if m == 20:
                self.store.ingest(obs(m, sampled), sampled + 121)           # late
            elif m == 30:
                self.store.ingest(obs(m, sampled, valid=False), sampled + 1)  # sensor fault
            else:
                self.store.ingest(obs(m, sampled), sampled + 1)
        r = h01.score(self.store.db, 's', START, 1)
        self.assertEqual((r['on_time_valid'], r['on_time_sensor_fault'], r['late'], r['missing']), (57, 1, 1, 1))
        self.assertEqual(r['transport_on_time'], 58)
        self.assertEqual(r['verdict'], 'FAIL')  # 57 < 60 (ceil(0.99*60))

    def test_retransmissions_count_once_and_unknown_time_is_reported(self):
        self.store.ingest(obs(0, START + 5), START + 6)
        self.store.ingest(obs(0, START + 5, session='2'), START + 7)        # second boot, same minute
        self.store.ingest(obs(1, None, session='3', uptime=0), START + 70)   # no reference in epoch 3
        r = h01.score(self.store.db, 's', START, 1)
        self.assertEqual(r['on_time_valid'], 1)
        self.assertEqual(r['invalid_clock_observations'], 1)

    def test_reconstructed_time_counts_when_tight(self):
        self.store.ingest(obs(0, None, session='5', uptime=0), START + 70)   # boot sample, no time yet
        self.store.ingest(obs(1, START + 60, session='5', uptime=60), START + 61)
        r = h01.score(self.store.db, 's', START, 2 / 60)  # two one-minute intervals
        # minute 0: reconstructed to START (+-2 s), committed 70 s later; minute 1: synchronized
        self.assertEqual((r['on_time_valid'], r['missing']), (2, 0))
        self.assertEqual(r['reconstructed_time_intervals_counted'], 1)


if __name__ == '__main__':
    unittest.main()
