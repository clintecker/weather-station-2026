"""The benchlink dashboard's step 1 flags (tools/benchlink_dash.py; build-progression record M4, M6, M7,
P8, P9): the drop form and its gates, the VCELL step flag, the SOC-suspect window, the two injection
cases, the M7 cross-checks, the CELL+ label with the R_pack estimate, the P9 termination check, the
--rewrite-iset rescale against the logger's events, --preflight with a stale block, and a structural
check that the page draws every flag the server returns.

Synthetic rows and files in a temporary directory only: no serial port, no evidence/ runs."""
import contextlib
import csv
import datetime
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
try:
    from test_preflight import MODE_A, MODEL, SHEET                 # python -m unittest discover -s tests
    from toolchain import ROOT, load_tool
except ImportError:
    from tests.test_preflight import MODE_A, MODEL, SHEET           # python -m unittest tests.<module>
    from tests.toolchain import ROOT, load_tool

DASH = load_tool('benchlink_dash')
T0 = datetime.datetime(2026, 10, 30, tzinfo=datetime.timezone.utc)


def r(t, **kw):
    """One row: discharging 38 mA through the shunt, PGOOD and CHG off, CELL+ 3.800 V, OUT 4.2 mV below
    it (the dV0 the tests use, so the drop is 0)."""
    d = dict(t=float(t), seq=None, reset='', charge_ma=0.0, load_ma=38.0, vcell_v=3.800, vout_v=3.7958,
             pgood=0.0, chg=0.0, battery_ma=-38.0, vin_v=None)
    d.update(kw)
    return d


def run(rows, **kw):
    """annotate() over the rows with dV0 4.2 mV unless given; returns (rows, its result)."""
    kw.setdefault('dv0_mv', 4.2)
    return rows, DASH.annotate(rows, DASH.Settings(**kw))


def col(rows, key):
    return [d[key] for d in rows]


class DropForm(unittest.TestCase):
    def test_a_drop_over_20_mv_flags_and_gives_r_path(self):
        rows, _ = run([r(0, vout_v=3.770)])   # 30 mV - 4.2 mV dV0 = 25.8 mV
        self.assertAlmostEqual(rows[0]['drop_mv'], 25.8)
        self.assertAlmostEqual(rows[0]['r_path_ohm'], 25.8 / 38.0)
        self.assertEqual(rows[0]['flag_drop'], 1)

    def test_pgood_active_turns_it_off(self):
        rows, _ = run([r(0, vout_v=3.770, pgood=1.0)])
        self.assertEqual((rows[0]['drop_mv'], rows[0]['flag_drop']), (None, 0))

    def test_the_30_ma_discharge_floor(self):
        rows, _ = run([r(0, vout_v=3.770, battery_ma=-29.0), r(5, vout_v=3.770, battery_ma=-30.0),
                       r(10, vout_v=3.770, battery_ma=200.0)])
        self.assertEqual(col(rows, 'flag_drop'), [0, 1, 0])
        self.assertIsNone(rows[2]['drop_mv'])   # charging: not valid

    def test_it_uses_the_ina_column_never_the_estimate(self):
        # no measured current (before --shunt-from): the ISET estimate (-38 mA) is not used
        rows, _ = run([r(0, vout_v=3.770, battery_ma=None)])
        self.assertEqual((rows[0]['drop_mv'], rows[0]['flag_drop']), (None, 0))
        self.assertEqual(DASH.estimate_ma(r(0)), -38.0)

    def test_dv0_is_subtracted_and_required(self):
        rows, _ = run([r(0, vout_v=3.776)], dv0_mv=4.2)    # 24 - 4.2 = 19.8: under 20
        self.assertEqual(rows[0]['flag_drop'], 0)
        rows, _ = run([r(0, vout_v=3.776)], dv0_mv=3.0)    # 24 - 3.0 = 21.0: over
        self.assertEqual(rows[0]['flag_drop'], 1)
        rows, _ = run([r(0, vout_v=3.700)], dv0_mv=None)   # no dV0: the form is off
        self.assertEqual((rows[0]['drop_mv'], rows[0]['flag_drop']), (None, 0))

    def test_a_step_over_10_mv_between_consecutive_valid_samples(self):
        rows, _ = run([r(0, vout_v=3.7938), r(5, vout_v=3.7818)])   # 2 mV, then 14 mV: both under 20
        self.assertEqual(col(rows, 'flag_drop'), [0, 1])
        rows, _ = run([r(0, vout_v=3.7938), r(5, vout_v=3.7848)])   # 2 mV, then 11 mV: a 9 mV step
        self.assertEqual(col(rows, 'flag_drop'), [0, 0])

    def test_the_step_needs_constant_load_and_consecutive_valid_samples(self):
        rows, _ = run([r(0, vout_v=3.7938), r(5, vout_v=3.7818, battery_ma=-48.0)])   # a load step
        self.assertEqual(col(rows, 'flag_drop'), [0, 0])
        rows, _ = run([r(0, vout_v=3.7938), r(5, pgood=1.0), r(10, vout_v=3.7818)])  # not consecutive
        self.assertEqual(col(rows, 'flag_drop'), [0, 0, 0])


class VcellStep(unittest.TestCase):
    def test_an_8_mv_step_at_constant_current_flags(self):
        rows, _ = run([r(0), r(5, vcell_v=3.791, vout_v=3.7868, battery_ma=-37.5)])   # 9 mV, dI 0.5 mA
        self.assertEqual(col(rows, 'flag_vcell_step'), [0, 1])
        rows, _ = run([r(0), r(5, vcell_v=3.793, vout_v=3.7888)])                     # 7 mV: not over 8
        self.assertEqual(col(rows, 'flag_vcell_step'), [0, 0])

    def test_a_load_step_does_not(self):
        rows, _ = run([r(0), r(5, vcell_v=3.780, vout_v=3.7758, battery_ma=-138.0)])
        self.assertEqual(col(rows, 'flag_vcell_step'), [0, 0])

    def test_it_holds_in_every_state_but_not_across_a_gap(self):
        rows, _ = run([r(0, pgood=1.0, battery_ma=300.0), r(5, pgood=1.0, battery_ma=300.5, vcell_v=3.830)])
        self.assertEqual(col(rows, 'flag_vcell_step'), [0, 1])   # charging, PGOOD on
        rows, _ = run([r(0), r(5 + DASH.GAP_S + 1, vcell_v=3.780)])
        self.assertEqual(col(rows, 'flag_vcell_step'), [0, 0])


class SocSuspect(unittest.TestCase):
    def test_suspect_until_30_minutes_after_the_last_flag(self):
        rows = [r(10 * k) for k in range(230)]
        rows[10]['vout_v'] = 3.770          # a drop flag at t = 100 s, and the step back at 110 s
        rows, _ = run(rows)
        self.assertEqual([d['t'] for d in rows if d['flag_drop']], [100.0, 110.0])
        suspect = [d['t'] for d in rows if d['soc_suspect']]
        self.assertEqual((suspect[0], suspect[-1]), (100.0, 110.0 + DASH.SUSPECT_S - 10))
        self.assertEqual(len(suspect), DASH.SUSPECT_S // 10 + 1)

    def test_a_later_flag_extends_it(self):
        rows = [r(10 * k) for k in range(300)]
        rows[10]['vout_v'] = 3.770
        rows[100]['vout_v'] = 3.770         # a second flag at 1000 s
        rows, _ = run(rows)
        self.assertEqual(max(d['t'] for d in rows if d['soc_suspect']), 1010.0 + DASH.SUSPECT_S - 10)


class Injection(unittest.TestCase):
    """1 ohm inserted at t = 50 s while discharging 38 mA (the 100 ohm load: about 0.4 mA less)."""

    def series(self, vcell_after, vout_after):
        before = [r(5 * k) for k in range(10)]
        after = [r(50 + 5 * k, vcell_v=vcell_after, vout_v=vout_after, battery_ma=-37.6) for k in range(10)]
        rows, _ = run(before + after)
        return {k: sum(col(rows, k)) for k in ('flag_drop', 'flag_vcell_step')}

    def test_case_a_cell_plus_to_vin_plus_raises_the_drop_flag_only(self):
        # CELL+ is upstream of the resistor: VCELL holds, OUT falls 38 mV
        got = self.series(3.800, 3.7958 - 0.038)
        self.assertGreater(got['flag_drop'], 0)
        self.assertEqual(got['flag_vcell_step'], 0)

    def test_case_b_a_pack_lead_raises_the_step_flag_only(self):
        # in the pack lead: CELL+ and OUT fall together, the drop does not change
        got = self.series(3.800 - 0.038, 3.7958 - 0.038)
        self.assertEqual(got, {'flag_drop': 0, 'flag_vcell_step': 1})


class M7(unittest.TestCase):
    def test_pgood_against_the_divider(self):
        rows, _ = run([r(0, pgood=1.0, vin_v=3.9), r(5, pgood=1.0, vin_v=4.5), r(10, vin_v=4.8), r(15, vin_v=4.5),
                       r(20, pgood=1.0)])
        self.assertEqual(col(rows, 'flag_pgood'), [1, 0, 1, 0, 0])

    def test_chg_against_v_iset(self):
        # V_ISET = charge_ma x R_ISET / (400 x 1000), R_ISET 1000 ohm where no logger_start names it
        rows, _ = run([r(0, chg=1.0, charge_ma=0.0), r(5, charge_ma=100.0), r(10, charge_ma=50.0),
                       r(15, chg=1.0, charge_ma=500.0), r(20, chg=1.0, charge_ma=None)])
        self.assertAlmostEqual(rows[1]['v_iset_v'], 0.25)
        self.assertEqual(col(rows, 'flag_chg'), [1, 1, 0, 0, 0])

    def test_iset_against_the_ina_during_cc(self):
        on = dict(chg=1.0, pgood=1.0)
        rows, _ = run([r(0, battery_ma=500.0, charge_ma=500.0, **on), r(5, battery_ma=500.0, charge_ma=580.0, **on),
                       r(10, battery_ma=500.0, charge_ma=565.0, **on), r(15, battery_ma=150.0, charge_ma=400.0, **on),
                       r(20, battery_ma=500.0, charge_ma=580.0)])   # CHG off: not CC
        self.assertEqual(col(rows, 'flag_iset'), [0, 1, 0, 0, 0])   # 80 > 10 % + 20 = 70; 65 is not


class CellPlus(unittest.TestCase):
    def test_the_estimate_takes_off_i_times_r_pack(self):
        rows, _ = run([r(0, vcell_v=4.150, battery_ma=900.0), r(5, vcell_v=3.700, battery_ma=-100.0),
                       r(10, battery_ma=None)], r_pack_mohm=30.0)
        self.assertAlmostEqual(rows[0]['vcell_corr_v'], 4.150 - 0.027)   # charging: the pack sits below CELL+
        self.assertAlmostEqual(rows[1]['vcell_corr_v'], 3.700 + 0.003)   # discharging: above it
        self.assertIsNone(rows[2]['vcell_corr_v'])

    def test_the_label_and_no_r_pack(self):
        lb = DASH.labels(DASH.Settings(r_pack_mohm=30.0, dv0_mv=4.2))
        self.assertEqual(lb['vcell'], 'CELL+ node, includes the pack-lead drop')
        self.assertIn('R_pack 30 mOhm', lb['vcell_corr'])
        self.assertIn('PATH_CELL_OUT only', lb['drop_coverage'])
        rows, _ = run([r(0)], r_pack_mohm=None)
        self.assertIsNone(rows[0]['vcell_corr_v'])
        self.assertIn('no R_pack', DASH.labels(DASH.Settings())['vcell_corr'])


class P9(unittest.TestCase):
    def term(self, i_ma, vcell, pgood_after=1.0, r_pack=30.0):
        on = dict(chg=1.0, pgood=1.0)
        rows, (terms, _, _, _) = run([r(0, battery_ma=600.0, vcell_v=4.10, **on), r(5, battery_ma=i_ma, vcell_v=vcell, **on),
                                   r(10, pgood=pgood_after, battery_ma=0.0, vcell_v=4.10)], r_pack_mohm=r_pack)
        self.assertEqual(len(terms), 1)
        return terms[0]

    def test_a_healthy_termination(self):
        t = self.term(300.0, 4.150)   # cell 4.150 - 0.3 x 0.030 = 4.141
        self.assertEqual((t['ok'], t['why'], t['t']), (True, 'healthy', 10.0))
        self.assertAlmostEqual(t['cell_v'], 4.141)

    def test_an_early_end_and_a_low_cell(self):
        self.assertIn('outside', self.term(600.0, 4.150)['why'])
        self.assertFalse(self.term(150.0, 4.150)['ok'])
        t = self.term(300.0, 4.125)   # 4.116 V
        self.assertEqual((t['ok'], t['why']), (False, 'cell 4.116 V below 4.12 V'))

    def test_the_input_leaving_is_not_a_termination(self):
        self.assertIsNone(self.term(300.0, 4.150, pgood_after=0.0)['ok'])
        self.assertIsNone(self.term(300.0, 4.150, r_pack=None)['ok'])   # cannot judge without R_pack


def utc(t):
    return (T0 + datetime.timedelta(seconds=t)).isoformat(timespec='seconds')


def write_csv(path, rows):
    cols = ('utc', 'seq', 'reset', *DASH.COLS)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for k, d in enumerate(rows):
            w.writerow({**{c: d.get(c) for c in DASH.COLS}, 'utc': utc(d['t']), 'seq': k, 'reset': ''})


def write_events(path, starts):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(('utc', 'local', 'event', 'detail'))
        for t, r_iset in starts:
            w.writerow((utc(t), '', 'logger_start', f'pid=1 r_iset={r_iset:g} ohm k_iset=400 r_load=100 ohm'))
            w.writerow((utc(t + 1), '', 'rx_connected', 'r_iset=5 is not a logger_start'))


class RewriteIset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = os.path.join(self.tmp.name, 'run.csv')
        self.events = os.path.join(self.tmp.name, 'run-events.csv')
        # 0 s: before any logger_start; 100-110 s: logged at 890; 200-210 s: logged at 1000
        write_csv(self.csv, [r(t, charge_ma=100.0, pgood=1.0) for t in (0, 100, 105, 110, 200, 205, 210)])
        write_events(self.events, [(90, 890), (190, 1000)])

    def charge(self, cfg):
        j = DASH.load(self.csv, 0, 1500, 0.0, float('inf'), cfg=cfg)
        json.dumps(j, allow_nan=False)
        return [row[j['cols'].index('charge_ma')] for row in j['rows']], j

    def test_only_the_rows_logged_at_old_are_rescaled(self):
        got, j = self.charge(DASH.Settings(events=self.events, rewrite_iset=890.0))
        self.assertEqual([round(v, 6) for v in got], [100.0, 89.0, 89.0, 89.0, 100.0, 100.0, 100.0])
        self.assertEqual((j['settings']['rescaled_rows'], j['settings']['events_error']), (3, ''))

    def test_v_iset_is_recovered_with_the_r_iset_each_row_was_logged_at(self):
        _, j = self.charge(DASH.Settings(events=self.events, rewrite_iset=890.0))
        v = [round(x, 6) for x in j['derived']['v_iset_v']]
        self.assertEqual(v, [0.25, 0.2225, 0.2225, 0.2225, 0.25, 0.25, 0.25])

    def test_without_rewrite_nothing_changes(self):
        got, j = self.charge(DASH.Settings(events=self.events))
        self.assertEqual(got, [100.0] * 7)
        self.assertEqual(j['settings']['rescaled_rows'], 0)

    def test_without_events_it_refuses(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            DASH.options(['--csv', self.csv, '--rewrite-iset', '890'])
        self.assertEqual(e.exception.code, 2)
        self.assertIn('--rewrite-iset needs --events', err.getvalue())
        a, cfg = DASH.options(['--csv', self.csv, '--rewrite-iset', '890', '--events', self.events])
        self.assertEqual((cfg.rewrite_iset, cfg.events), (890.0, self.events))

    def test_an_unreadable_logger_start_is_counted_and_said_once(self):
        """A logger_start the reader cannot read (a damaged time) would leave its rows unrescaled without a
        word; it is counted, named in events_error and printed once, not on every refresh."""
        with open(self.events, 'a', newline='') as f:
            csv.writer(f).writerow(('2026-10-30T00:0', '', 'logger_start', 'pid=2 r_iset=890 ohm'))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _, j = self.charge(DASH.Settings(events=self.events, rewrite_iset=890.0))
            self.charge(DASH.Settings(events=self.events, rewrite_iset=890.0))
        self.assertEqual(j['settings']['events_skipped'], 1)
        self.assertIn('1 unreadable logger_start row skipped (first at line 6)', j['settings']['events_error'])
        self.assertEqual(err.getvalue().count('unreadable logger_start'), 1, err.getvalue())
        _, j = self.charge(DASH.Settings(events=os.path.join(self.tmp.name, 'none.csv')))
        self.assertEqual(j['settings']['events_skipped'], 0)

    def test_unreadable_csv_rows_are_printed_once(self):
        with open(self.csv, 'a') as f:
            f.write('2026-10-30T00:0\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            j = DASH.load(self.csv, 0, 1500, 0.0, float('inf'))
            DASH.load(self.csv, 0, 1500, 0.0, float('inf'))
        self.assertEqual((j['skipped'], j['first_bad_line']), (1, 9))
        self.assertEqual(err.getvalue().count('unreadable CSV row'), 1, err.getvalue())
        self.assertIn(self.csv, err.getvalue())

    def test_an_unreadable_events_file_rescales_nothing_and_says_so(self):
        got, j = self.charge(DASH.Settings(events=self.events + '.nope', rewrite_iset=890.0))
        self.assertEqual(got, [100.0] * 7)
        self.assertIn('.nope', j['settings']['events_error'])


class Preflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.model, self.sheet, self.notes = d/'wiring.toml', d/'build-sheet.md', d/'notes.md'
        self.model.write_text(MODEL)
        self.sheet.write_text(SHEET)
        sha = DASH._load_preflight().checklist.blob_sha1
        top = dict(model_hash='0' * 40, sheet_hash=sha(self.sheet), revision='bench-bb-r0.1', power_mode='A',
                   meter=DASH._load_preflight().checklist.METER, date='2026-10-30', photo='p.jpg', wiggle='pass',
                   rewire='false', step_exit='false', deviations='[]', dv0_mv='{ A = 4.2, B = 3.9 }',
                   r_pack_mohm=30.0)
        lines = [f'{k} = {v}' if k in ('rewire', 'step_exit', 'deviations', 'dv0_mv', 'r_pack_mohm', 'date')
                 else f'{k} = "{v}"' for k, v in top.items()]
        tables = ''.join(f'\n[[reading]]\n{x}\n' for x in MODE_A)
        self.notes.write_text('```toml preflight\n' + '\n'.join(lines) + '\n' + tables + '```\n')

    def test_a_stale_block_warns_and_its_values_are_used(self):
        pf = DASH.preflight_settings(self.notes, 'A', self.model, self.sheet)
        self.assertEqual(pf['status'], 'stale', pf['problems'])
        self.assertIn('stale', pf['warning'])
        self.assertIn('still used', pf['warning'])
        self.assertEqual((pf['dv0_mv'], pf['r_pack_mohm']), (4.2, 30.0))
        self.assertEqual(DASH.preflight_settings(self.notes, 'B', self.model, self.sheet)['dv0_mv'], 3.9)

    def test_options_fill_from_the_block_and_the_flags_override(self):
        # against the repo's own model the block's hash differs too: whatever its status, the values hold
        _, cfg = DASH.options(['--csv', 'x.csv', '--preflight', str(self.notes)])
        self.assertEqual((cfg.dv0_mv, cfg.r_pack_mohm), (4.2, 30.0))
        self.assertIn(cfg.preflight['status'], ('stale', 'failing'))
        self.assertTrue(cfg.preflight['warning'])
        _, cfg = DASH.options(['--csv', 'x.csv', '--preflight', str(self.notes), '--dv0', '3.5', '--r-pack', '41'])
        self.assertEqual((cfg.dv0_mv, cfg.r_pack_mohm), (3.5, 41.0))

    def test_load_returns_the_preflight_and_the_values_it_used(self):
        pf = DASH.preflight_settings(self.notes, 'A', self.model, self.sheet)
        path = os.path.join(self.tmp.name, 'run.csv')
        write_csv(path, [r(0, vout_v=3.770), r(5)])
        cfg = DASH.Settings(dv0_mv=pf['dv0_mv'], r_pack_mohm=pf['r_pack_mohm'], preflight=pf)
        j = DASH.load(path, 0, 1500, 0.0, float('inf'), 0.0, cfg)
        self.assertEqual(j['preflight']['status'], 'stale')
        self.assertEqual((j['settings']['dv0_mv'], j['settings']['r_pack_mohm']), (4.2, 30.0))
        self.assertEqual(j['flags']['flag_drop'], [1, 1])   # 25.8 mV, then the 25.8 mV step back
        json.dumps(j, allow_nan=False)


class Page(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT/'tools'/'benchlink_dash.html').read_text(encoding='utf-8')

    def test_the_page_names_every_flag_and_derived_key_the_server_returns(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'run.csv')
            write_csv(path, [r(0), r(5)])
            j = DASH.load(path, 0, 1500, 0.0, float('inf'), 0.0, DASH.Settings(dv0_mv=4.2, r_pack_mohm=30.0))
        self.assertEqual(j['flag_keys'], list(DASH.FLAG_KEYS))
        self.assertEqual(set(j['flags']), set(DASH.FLAG_KEYS))
        for key in (*j['flags'], *j['derived']):
            self.assertTrue(re.search(rf"'{re.escape(key)}'", self.html), f'the page does not draw {key}')
        for key in ('vcell', 'vcell_corr', 'drop_basis', 'drop_coverage', 'flags'):
            self.assertIn(key, j['labels'])
            self.assertTrue(key in self.html, f'the page does not show the label {key}')
        for key in ('flag_onsets', 'terminations', 'preflight', 'settings', 'derived'):
            self.assertTrue(re.search(rf'\b(data|d)\.{key}\b', self.html), f'the page does not read {key}')

    def test_the_bucket_keeps_a_flag_raised_anywhere_in_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'run.csv')
            write_csv(path, [r(0, vout_v=3.770), r(5), r(10), r(15)])   # the flag, then the 25.8 mV step back
            j = DASH.load(path, 0, 2, 0.0, float('inf'), 0.0, DASH.Settings(dv0_mv=4.2))
        self.assertEqual(j['flags']['flag_drop'], [1, 0])
        self.assertEqual(len(j['derived']['drop_mv']), 2)
        self.assertEqual(j['flag_onsets'][0][1], 'flag_drop')


if __name__ == '__main__':
    unittest.main()
