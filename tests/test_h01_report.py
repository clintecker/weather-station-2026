"""Scorer for the 24-hour delivery test (H01): denominators, categories and the strict pass rule."""
import tempfile
import unittest
from pathlib import Path
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before gateway is imported
    from toolchain import load_tool
except ImportError:
    from tests.toolchain import load_tool
from gateway import RECORD_VERSION, Store

h01 = load_tool('h01_report')
START = 1_800_000_000


def obs(seq, sampled, valid=True, session='1', uptime=None):
    return dict(version=RECORD_VERSION, station='s', session=session, sequence=seq, sampled_at=sampled,
                uptime_s=seq * 60 if uptime is None else uptime,
                time_quality='synchronized' if sampled is not None else 'unknown',
                energy_state='normal', calibration_revision=0,
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

    def test_readings_at_the_interval_edge_are_flagged_not_rescored(self):
        """Sample times jitter about 1 s, so readings at :59.5 or :00.4 can land two in
        one interval and none in the next. The scorer flags it; the pass rule is unchanged."""
        for m in range(60):
            jitter = -0.6 if m % 7 == 3 else 0.4                       # mostly :00.4, sometimes :59.4
            self.store.ingest(obs(m, START + 60 * m + jitter), START + 60 * m + 2)
        r = h01.score(self.store.db, 's', START, 1)
        self.assertGreater(r['readings_near_interval_edge'], 0)
        self.assertGreater(r['intervals_with_several_readings'], 0)
        self.assertIn('choose a --start', r['grid_warning'])
        self.assertEqual(r['verdict'], 'FAIL')                          # same rule, same result
        shifted = h01.score(self.store.db, 's', START - 30, 1)        # readings mid-interval
        self.assertIsNone(shifted['grid_warning'])
        self.assertEqual(shifted['intervals_with_several_readings'], 0)

    def test_reconstructed_count_uses_each_intervals_final_choice(self):
        """A reconstructed reading later replaced by a better one is not counted."""
        self.store.ingest(obs(0, None, session='5', uptime=0), START + 70)   # reconstructed, 70 s late
        self.store.ingest(obs(1, START + 60, session='5', uptime=60), START + 61)
        self.store.ingest(obs(0, START + 3, session='6', uptime=0), START + 4)  # same minute, better
        r = h01.score(self.store.db, 's', START, 2 / 60)
        self.assertEqual(r['reconstructed_time_intervals_counted'], 0)

    def test_reconstructed_time_counts_when_tight(self):
        self.store.ingest(obs(0, None, session='5', uptime=0), START + 70)   # boot sample, no time yet
        self.store.ingest(obs(1, START + 60, session='5', uptime=60), START + 61)
        r = h01.score(self.store.db, 's', START, 2 / 60)  # two one-minute intervals
        # minute 0: reconstructed to START (+-2 s), committed 70 s later; minute 1: synchronized
        self.assertEqual((r['on_time_valid'], r['missing']), (2, 0))
        self.assertEqual(r['reconstructed_time_intervals_counted'], 1)


class H01RuleBoundaryTests(unittest.TestCase):
    """Characterization of score()'s every branch from stored rows, so the time basis, uncertainty
    and latency are set exactly (no reconstruction in between)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'o.sqlite3')
        self.seq = 0

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def row(self, effective, received, basis='synchronized', uncertainty=None, valid=True, session='1',
            temperature=True):
        import json
        record = obs(self.seq, effective, valid=valid, session=session)
        if valid and not temperature:
            record['temperature_c'] = None
        with self.store.db:
            self.store.db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)',
                                  ('s', session, self.seq, effective, received, json.dumps(record), 0,
                                   effective, basis, uncertainty))
        self.seq += 1

    def test_empty_window(self):
        r = h01.score(self.store.db, 's', START, 3 / 60)
        self.assertEqual(r, {
            'gate': 'H01', 'station': 's', 'window_start': h01.iso(START), 'window_end': h01.iso(START + 180),
            'intervals': 3, 'required_on_time_valid': 3, 'on_time_valid': 0, 'on_time_sensor_fault': 0,
            'late': 0, 'transport_on_time': 0, 'missing': 3,
            'missing_first': [h01.iso(START), h01.iso(START + 60), h01.iso(START + 120)],
            'invalid_clock_observations': 0, 'reconstructed_time_intervals_counted': 0,
            'latency_median_s': None, 'latency_max_on_time_s': None, 'boot_epochs_seen': 0,
            'gateway_rejections': 0, 'intervals_with_several_readings': 0, 'readings_near_interval_edge': 0,
            'grid_warning': None, 'serial_gaps': None, 'serial_gap_count': None, 'serial_gap_total_s': None,
            'verdict': 'FAIL'})
        self.assertIn('Serial-link gaps: not recorded', h01.markdown(r))   # no gateway_events: unknown, not zero

    def test_time_basis_tolerance_and_latency_edges(self):
        self.row(START + 30, START + 30 + 120)                               # m0: latency exactly 120: on time
        self.row(START + 90, START + 90 + 120.5)                             # m1: late
        self.row(START + 150, START + 149)                                   # m2: negative latency: late
        self.row(START + 210, START + 211, 'reconstructed', 5)               # m3: tolerance met
        self.row(START + 270, START + 271, 'reconstructed', 5.01)            # m4: too uncertain
        self.row(START + 330, START + 331, 'estimated', 0)                   # m5: unknown basis
        self.row(None, START + 400, None, None, session='2')                 # unplaced, in receipt window
        self.row(None, START + 600 + 119, None, None, session='3')           # receipt window end - 1
        self.row(None, START + 600 + 120, None, None, session='4')           # outside: not counted
        self.row(START + 390, START + 391, valid=True, temperature=False)    # m6: T missing: sensor fault
        self.row(START + 450, START + 451, valid=False)                      # m7: fault
        self.row(START + 452, START + 452 + 121)                             # m7: valid but late: fault stays
        self.row(START + 453, START + 453 + 119, valid=False)                # m7: later fault, worse latency
        self.row(START + 510, START + 520)                                   # m8: latency 10 ...
        self.row(START + 511, START + 514)                                   # m8: ... replaced by latency 3
        self.row(START + 540 + 0.5, START + 545, uncertainty=0)              # m9: near the edge
        self.row(START + 540 + 57.0, START + 600)                            # m9: twice, not near; latency 3
        r = h01.score(self.store.db, 's', START, 10 / 60)
        got = {k: r[k] for k in ('on_time_valid', 'on_time_sensor_fault', 'late', 'missing', 'transport_on_time',
                                 'invalid_clock_observations', 'reconstructed_time_intervals_counted',
                                 'latency_median_s', 'latency_max_on_time_s', 'boot_epochs_seen',
                                 'intervals_with_several_readings', 'readings_near_interval_edge', 'verdict')}
        self.assertEqual(got, {'on_time_valid': 4, 'on_time_sensor_fault': 2, 'late': 2, 'missing': 2,
                               'transport_on_time': 6, 'invalid_clock_observations': 4,
                               'reconstructed_time_intervals_counted': 1, 'latency_median_s': 3,
                               'latency_max_on_time_s': 120, 'boot_epochs_seen': 3,
                               'intervals_with_several_readings': 3, 'readings_near_interval_edge': 1,
                               'verdict': 'FAIL'})
        self.assertEqual(r['missing_first'], [h01.iso(START + 240), h01.iso(START + 300)])
        self.assertIn('1 readings lie within 2 s', r['grid_warning'])

    def test_pass_threshold_is_ceil_of_99_percent(self):
        minutes = 200                                                         # ceil(198.0) = 198
        for m in range(minutes - 2):
            self.row(START + 60 * m + 30, START + 60 * m + 31)
        self.row(START + 60 * 198 + 30, START + 60 * 198 + 31, valid=False)
        r = h01.score(self.store.db, 's', START, minutes / 60)
        self.assertEqual((r['required_on_time_valid'], r['on_time_valid'], r['verdict']), (198, 198, 'PASS'))
        with self.store.db:
            self.store.db.execute('DELETE FROM observations WHERE sequence=0')
        r = h01.score(self.store.db, 's', START, minutes / 60)
        self.assertEqual((r['on_time_valid'], r['missing'], r['verdict']), (197, 2, 'FAIL'))

    def test_rejections_window_and_other_stations(self):
        with self.store.db:
            for station, received in (('s', START - 1), ('s', START), ('s', START + 60 + 119), ('s', START + 180),
                                      ('t', START + 5)):
                self.store.db.execute('INSERT INTO rejections VALUES (?,?,?,?,?,?,?)',
                                      (station, '1', 0, received, 'x', '', ''))
        self.row(START + 30, START + 31)
        with self.store.db:
            self.store.db.execute("UPDATE observations SET station='t'")
        r = h01.score(self.store.db, 's', START, 1 / 60)
        self.assertEqual((r['gateway_rejections'], r['on_time_valid'], r['missing']), (2, 0, 1))



class H01SerialGapTests(unittest.TestCase):
    """Serial-link gaps beside the score (decision record H8): from gateway_events rows as ws0 writes
    them (ws0/link.py lines through ws0/web.py Telemetry.event) and the RX reports in rx_alive."""
    def setUp(self):
        from ws0.web import TABLES
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'o.sqlite3')
        with self.store.db:
            for sql in TABLES:
                self.store.db.execute(sql)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def event(self, at, kind, text='', station='s', source='gateway'):
        with self.store.db:
            self.store.db.execute('INSERT INTO gateway_events (station,at,source,kind,level,text) VALUES (?,?,?,?,?,?)',
                                  (station, at, source, kind, 'warn', text))

    def alive(self, at, station='s'):
        with self.store.db:
            self.store.db.execute('INSERT INTO rx_alive (station,received_at,uptime_s) VALUES (?,?,0)', (station, at))

    def alive_every(self, first, last, station='s'):
        """The RX's '#alive' every 60 s from START + first up to START + last (inclusive)."""
        for at in range(first, last + 1, 60):
            self.alive(START + at, station)

    def gaps(self, hours=1):
        r = h01.score(self.store.db, 's', START, hours)
        return r, [(g['kind'], g['start'], g['end'], g['duration_s'], g['open_at_window_end'])
                   for g in r['serial_gaps']]

    def test_empty_window_has_no_gaps(self):
        self.event(START + 10, 'serial-open', '#gateway serial-open path=/dev/x')   # calm: not a gap
        self.alive_every(-30, 3570)                                     # every report heard
        r, gaps = self.gaps()
        self.assertEqual((gaps, r['serial_gap_count'], r['serial_gap_total_s']), ([], 0, 0.0))
        self.assertIn('Serial-link gaps: none in the window.', h01.markdown(r))
        self.assertIn('| serial gap count | 0 |', h01.markdown(r))

    def test_each_gap_kind(self):
        self.event(START + 100, 'serial-lost', '#gateway serial-lost path=/dev/x reason=read:OSError')
        self.event(START + 101, 'serial-lost', '#gateway serial-lost path=/dev/x reason=board-not-present')
        self.event(START + 130, 'serial-open', '#gateway serial-open path=/dev/y')
        self.event(START + 1000, 'serial-reopen', '#gateway serial-reopen path=/dev/y silent_s=90 next_s=180')
        self.alive_every(0, 1500)                                     # 1500: last report before the silence
        self.event(START + 1680, 'receiver-silent:',                  # the kind as ws0/web.py stores it
                   '#gateway receiver-silent: no RX report for 180 s (check RX board, USB, watchdog)')
        self.event(START + 1700, 'rx_boot', '#boot role=rx', source='rx')   # an RX report ends it
        self.alive_every(1760, 3560)
        self.event(START + 200, 'serial-lost', 'other station', station='t')   # not this station
        r, gaps = self.gaps()
        self.assertEqual(gaps, [
            ('serial-lost', h01.iso(START + 100), h01.iso(START + 130), 30, False),
            ('serial-reopen', h01.iso(START + 910), h01.iso(START + 1000), 90, False),
            ('receiver-silent', h01.iso(START + 1500), h01.iso(START + 1700), 200, False),
            ('alive-missing', h01.iso(START + 1500), h01.iso(START + 1760), 260, False)])
        self.assertEqual((r['serial_gap_count'], r['serial_gap_total_s']), (4, 380.0))   # 30 + 90 + 260
        report = h01.markdown(r)
        self.assertIn('| serial gap total s | 380.0 |', report)
        self.assertIn(f"| serial-reopen | {h01.iso(START + 910)} | {h01.iso(START + 1000)} | 90.0 | no |", report)

    def test_receiver_silent_ends_at_the_next_alive(self):
        self.event(START + 400, 'receiver-silent', '#gateway receiver-silent: no RX report for 180 s')
        self.alive_every(450, 3570)
        r, gaps = self.gaps()
        self.assertEqual(gaps, [('receiver-silent', h01.iso(START + 220), h01.iso(START + 450), 230, False)])

    def test_unterminated_gaps_end_at_the_window_end(self):
        self.event(START + 3000, 'serial-lost', '#gateway serial-lost path=/dev/x reason=read:OSError')
        self.event(START + 3300, 'receiver-silent:', '#gateway receiver-silent: no RX report for 180 s')
        self.event(START + 3700, 'serial-open', '#gateway serial-open path=/dev/x')   # after the window
        r, gaps = self.gaps()
        self.assertEqual(gaps, [
            ('serial-lost', h01.iso(START + 3000), h01.iso(START + 3600), 600, True),
            ('receiver-silent', h01.iso(START + 3120), h01.iso(START + 3600), 480, True)])
        self.assertEqual(r['serial_gap_total_s'], 600.0)              # overlapping time counted once
        self.assertIn('| yes |', h01.markdown(r))

    def test_gaps_are_clipped_to_the_window(self):
        self.event(START - 50, 'serial-lost', '#gateway serial-lost path=/dev/x reason=read:OSError')
        self.event(START + 20, 'serial-open', '#gateway serial-open path=/dev/x')
        self.event(START - 500, 'serial-lost', 'earlier, closed before the window')
        self.event(START + 40, 'serial-reopen', '#gateway serial-reopen path=/dev/x silent_s=200 next_s=400')
        r, gaps = self.gaps()
        self.assertEqual(gaps, [('serial-lost', h01.iso(START), h01.iso(START + 20), 20, False),
                                ('serial-reopen', h01.iso(START), h01.iso(START + 40), 40, False)])
        self.assertEqual(r['serial_gap_total_s'], 40.0)

    def test_one_missed_alive_is_a_gap(self):
        """H8(d): a TX replug that costs one 60 s '#alive' (120 s apart) is shorter than the 90 s
        serial-reopen and the 180 s receiver-silent alarms, and still shows; jitter does not."""
        self.alive_every(0, 600)
        self.alive(START + 689)                                        # 89 s after the last: jitter
        self.alive_every(809, 3569)                                    # 120 s: one report missed
        self.alive(START + 120, station='t')                           # not this station
        r, gaps = self.gaps()
        self.assertEqual(gaps, [('alive-missing', h01.iso(START + 689), h01.iso(START + 809), 120, False)])
        self.assertEqual((r['serial_gap_count'], r['serial_gap_total_s']), (1, 120.0))
        self.assertIn(f"| alive-missing | {h01.iso(START + 689)} | {h01.iso(START + 809)} | 120.0 | no |",
                      h01.markdown(r))
        self.assertNotIn('none in the window', h01.markdown(r))

    def test_alive_silence_across_the_window_edges(self):
        self.alive(START - 100)                                        # the last report before the window
        self.alive_every(200, 3200)
        r, gaps = self.gaps()
        self.assertEqual(gaps, [('alive-missing', h01.iso(START), h01.iso(START + 200), 200, False),
                                ('alive-missing', h01.iso(START + 3200), h01.iso(START + 3600), 400, True)])
        self.assertEqual(r['serial_gap_total_s'], 600.0)

    def test_no_alive_inferred_before_the_first_report(self):
        """A station whose RX never sent '#alive' gets no alive-missing rows (receiver-silent covers
        a dead RX); the minutes before its first report are not counted either."""
        self.alive_every(0, 3540, station='t')
        self.assertEqual(self.gaps()[1], [])
        self.alive_every(300, 3540)
        self.assertEqual(self.gaps()[1], [])


if __name__ == '__main__':
    unittest.main()
