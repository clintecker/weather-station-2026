"""Live local dashboard for the bench telemetry CSV (tools/benchlink_log.py).

    .venv/bin/python tools/benchlink_dash.py --csv <benchlink.csv> [--port 8099] [--points 1500]
        [--sources <sources.csv>] [--anchor "YYYY-MM-DD HH:MM:SS"] [--gauge-valid-from "YYYY-MM-DD HH:MM:SS"]
        [--shunt-from "YYYY-MM-DD HH:MM:SS"]

Serves http://127.0.0.1:<port>/ (the page, benchlink_dash.html) and /data?since=<unix time>: JSON with the
CSV's numeric columns from that time (bucketed to at most --points rows), the counted charge (soc_cc,
q_mah), the gaps, the input windows of --sources, the anchor, marks and the newest packet's time. Local
only; no external libraries in the page.

The state of charge is counted from --anchor (a moment when the cell had rested near 0 A; without it,
nothing is counted): the start from the rest voltage (OCV, about +-10 %), then the net battery current
integrated over time. A gap (no packet for over GAP_S) is bridged with the mean battery current at its two
ends, and that estimate is reported with the gap.

The battery current is the measured one (the logger's battery_ma: the INA228 shunt, + into the cell) for
rows at or after --shunt-from, the moment the cell went through the shunt. Rows before it, rows without
it, and CSVs without the battery_ma column fall back to the ISET charge current minus the load
(estimate_ma()); the page marks those as an estimate. Without --shunt-from every row is an estimate.

The step 1 flags (build-progression record M4, M6, M7, P8, P9; computed here, drawn by the page):
    [--dv0 mV] [--r-pack mOhm] [--power-mode A|B] [--preflight NOTES.md]
    [--events <benchlink-events.csv>] [--rewrite-iset OLD] [--r-iset ohm]
- drop form (M6, PATH_CELL_OUT): valid only with PGOOD inactive and the measured (INA228) battery current
  discharging at 30 mA or more; drop = VCELL - VOUT - dV0, flagged above 20 mV or on a step of over 10 mV
  between consecutive valid samples at constant load (|dI| < 2 mA). It covers CELL+ to OUT only.
- VCELL step (M6): a gauge VCELL step of over 8 mV between consecutive samples with |dI| < 2 mA.
- SOC suspect (M4, M6): from a drop or step flag until 30 minutes pass with no further flag.
- M7: PGOOD against the divider input (asserted below 4.0 V, or not asserted above 4.7 V); CHG against
  V_ISET (asserted with V_ISET under 0.02 V, or V_ISET above 0.2 V with CHG off); the ISET current against
  the INA228 current while CHG is on above 200 mA, outside 10 % + 20 mA.
- M4: vcell is the CELL+ node, which includes the pack-lead drop; the estimate VCELL - I x R_pack is
  returned beside it.
- P9: at each CHG release with PGOOD still on, the last sample before it must have the INA228 current in
  0.20-0.40 A and VCELL - I x R_pack >= 4.12 V.
Every flag that needs the battery current takes the measured one (battery_ma, from --shunt-from on), never
the ISET estimate: without --shunt-from those flags stay off.
--preflight takes dV0 (for --power-mode) and R_pack from the run's preflight block (tools/preflight.py)
and shows its status; a stale block is shown as a warning and its values are still used. --dv0 and
--r-pack override it. --rewrite-iset OLD (needs --events, the logger's <out>-events.csv) rescales
charge_ma by OLD/1000 for the rows logged after a logger_start with r_iset=OLD, up to the next
logger_start; the CSV on disk is not changed. The 1b current balance and the 2c power balance are not
here: the one-INA228 benchlink packet does not carry their currents."""
import argparse
import bisect
import csv
import dataclasses
import datetime
import importlib.util
import json
import math
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# battery_ma: the measured battery current (+ into the cell), None where the page must use the estimate.
COLS = ('charge_ma', 'load_ma', 'vcell_v', 'temp_c', 'rh_pct', 'rssi', 'pgood', 'chg', 'vout_v', 'vin_v', 'soc_pct',
        'soc_cc', 'q_mah', 'battery_ma')
# Typical Li-ion (LiCoO2/NMC) rest voltage to state of charge; cells differ, so a start taken from it is about
# +-10 %. Used once, at the anchor (a moment when the cell had rested near 0 A).
OCV = ((3.00, 0), (3.45, 5), (3.60, 10), (3.68, 20), (3.72, 30), (3.76, 40), (3.80, 50), (3.86, 60),
       (3.93, 70), (4.00, 80), (4.08, 90), (4.20, 100))
CAPACITY_MAH = 6600.0
GAP_S = 30   # no packet for longer than this (one is due every 5 s): a gap, bridged by count(), shaded on the page


def ocv_soc(v):
    if v <= OCV[0][0]:
        return 0.0
    for (v0, s0), (v1, s1) in zip(OCV, OCV[1:], strict=False):
        if v <= v1:
            return s0 + (s1 - s0) * (v - v0) / (v1 - v0)
    return 100.0


def battery_ma(r):
    """Net battery current, + into the cell: the measured one when the row has it (from --shunt-from on),
    else estimate_ma()."""
    measured = r.get('battery_ma')
    return measured if measured is not None else estimate_ma(r)


def estimate_ma(r):
    """The fallback battery current, + into the cell: the ISET charge current, minus the load when the battery
    carries it (PGOOD off, or OUT sagged to the cell while the input is weak: then the whole load is counted,
    an upper bound on what the battery gave)."""
    chg = r.get('charge_ma') or 0.0
    load = r.get('load_ma') or 0.0
    vout, vcell = r.get('vout_v'), r.get('vcell_v')
    carrying = not r.get('pgood') or (chg <= 2 and vout is not None and vcell is not None and vout - vcell < 0.1)
    return chg - load if carrying else chg


def count(rows, anchor_t):
    """Adds soc_cc (%) and q_mah (net mAh since the anchor) to each row dict, from the anchor on. Returns
    (the anchor's time or None, {start of each gap: its estimated mAh}). A gap (no packet for over
    GAP_S) is bridged with the mean battery current at its two ends: the load runs on whether or not
    the TX reports, so skipping it would leave the whole gap's discharge out. Over a gap in which the
    input changed (a charger plugged in or out) that is a guess, which is why it is reported."""
    start = next((r for r in rows if r['t'] >= anchor_t and r.get('vcell_v')), None)
    if not start:
        return None, {}
    soc0 = ocv_soc(start['vcell_v'])
    q, prev, bridged = 0.0, None, {}
    for r in rows:
        if r['t'] < start['t']:
            continue
        if prev is not None:
            step = (battery_ma(prev) + battery_ma(r)) / 2 * (r['t'] - prev['t']) / 3600.0
            q += step
            if r['t'] - prev['t'] > GAP_S:
                bridged[prev['t']] = step
        r['q_mah'] = q
        r['soc_cc'] = soc0 + 100.0 * q / CAPACITY_MAH
        prev = r
    return start['t'], bridged


PAGE = Path(__file__).with_name('benchlink_dash.html')


def local_ts(text):
    """A local 'YYYY-MM-DD HH:MM:SS' as a Unix time."""
    return datetime.datetime.strptime(text, '%Y-%m-%d %H:%M:%S').astimezone().timestamp()


def sources(path):
    """([[start, end or None, source], ...] from the hand-kept sources.csv (local times), an error or '').
    A line it cannot read is reported, not fatal: the automatic call then decides."""
    out = []
    if not path or not Path(path).exists():
        return out, ''
    try:
        with open(path, newline='') as f:
            for n, r in enumerate(csv.DictReader(f), 2):
                try:
                    out.append([local_ts(r['start']), local_ts(r['end']) if r['end'] else None, r['source']])
                except (KeyError, TypeError, ValueError) as e:
                    return out, f'{path} line {n}: {e}'
    except OSError as e:
        return out, f'{path}: {e}'
    return out, ''


def gaps(full, since_s, bridged):
    """[[last packet before, first packet after, how the TX came back, mAh the count bridged or None], ...]
    over every row (before any thinning). 'how' is the reset cause when the TX restarted in the gap (v3
    packets carry it; 'restart' for older ones), else ''."""
    out = []
    for a, b in zip(full, full[1:], strict=False):
        if b['t'] - a['t'] > GAP_S and b['t'] >= since_s:
            restarted = b['seq'] is not None and a['seq'] is not None and b['seq'] < a['seq']
            out.append([a['t'], b['t'], (b['reset'] or 'restart') if restarted else '', bridged.get(a['t'])])
    return out


def read_rows(path, gauge_from, shunt_from=float('inf')):
    """The CSV as row dicts, and (rows skipped, the first skipped line number). A row it cannot read (a
    line cut off while the logger writes it, a damaged file) is skipped and counted, not fatal. Before
    gauge_from the gauge's columns, and before shunt_from the measured battery current, are dropped."""
    full, skipped, first_bad = [], 0, None
    with open(path, newline='') as f:
        for n, r in enumerate(csv.DictReader(f), 2):
            try:
                d = {'t': datetime.datetime.fromisoformat(r['utc']).timestamp(),
                     'seq': int(r['seq']) if r.get('seq') else None, 'reset': r.get('reset') or ''}
                for c in COLS:
                    d[c] = float(r[c]) if r.get(c) not in (None, '') else None
            except (KeyError, TypeError, ValueError):
                skipped += 1
                first_bad = first_bad or n
                continue
            if d['t'] < gauge_from:   # the gauge read the charger's OUT, not the cell, before this moment
                d['vcell_v'] = d['soc_pct'] = None
            if d['t'] < shunt_from:   # the shunt was not in the battery path yet: the estimate stands in
                d['battery_ma'] = None
            full.append(d)
    return full, skipped, first_bad


def _agg(name, vals):
    """One bucket's value of a column: the state columns keep the last, a flag is raised if any row raised
    it, the rest are means."""
    if name in ('pgood', 'chg'):
        return vals[-1] if vals else None
    if name in FLAG_KEYS:
        return max(vals) if vals else 0
    return sum(vals) / len(vals) if vals else None


def bucket(rows, points, cols=COLS):
    """At most `points` rows of [t, *cols]: bucket means; the state columns keep the bucket's last value
    and the flags whether any row in the bucket raised them."""
    if len(rows) <= points:
        return rows
    size = len(rows) / points
    out = []
    for i in range(points):
        chunk = rows[int(i * size):int((i + 1) * size)] or rows[-1:]
        agg = [chunk[-1][0]]
        for k in range(1, len(cols) + 1):
            agg.append(_agg(cols[k - 1], [c[k] for c in chunk if c[k] is not None]))
        out.append(agg)
    return out


def marks(since_s, gauge_from, shunt_from):
    """[[time, label], ...]: the moments after since_s when the gauge moved to the cell and the cell went
    through the shunt."""
    out = [[gauge_from, 'gauge on cell']] if gauge_from > since_s else []
    if since_s < shunt_from < float('inf'):
        out.append([shunt_from, 'shunt in battery path'])
    return out


# ---- the step 1 flags (decision record M4, M6, M7, P8, P9) ----
DROP_MIN_DISCHARGE_MA = 30.0   # M6: the drop form is valid only while the cell discharges at least this much
DROP_LIMIT_MV = 20.0           # M6: about 0.5 ohm at 38 mA
DROP_STEP_MV = 10.0            # M6: a step between consecutive valid samples at constant load
CONSTANT_DI_MA = 2.0           # M6: |dI| below this between two samples is constant current
VCELL_STEP_MV = 8.0            # M6: a 6.6 Ah cell cannot step this much in one sample at constant current
SUSPECT_S = 1800               # M6: SOC stays suspect until 30 minutes pass with no flag
PGOOD_LOW_V, PGOOD_HIGH_V = 4.0, 4.7   # M7: PGOOD asserted below the low one, or not asserted above the high
ISET_ZERO_V, ISET_ON_V = 0.02, 0.2     # M7: CHG on with V_ISET near 0 (an open ISET wire reads 0 V), or off above
CC_MIN_MA = 200.0              # M7: the ISET-against-INA228 check runs while CHG is on above this
ISET_TOL, ISET_TOL_MA = 0.10, 20.0     # M7: outside 10 % + 20 mA is flagged
TERM_MIN_MA, TERM_MAX_MA, TERM_MIN_V = 200.0, 400.0, 4.12   # P9: ITERM 0.225-0.375 A; VBAT(REG) 4.16 V min - drop
K_ISET = 400.0                 # bq24074 ISET gain (SLUS810 eq. 3), as the logger's default --k-iset
R_ISET_OHM = 1000.0            # change A (record 7.1 P3): the R_ISET of rows the events file does not name
VCELL_LABEL = 'CELL+ node, includes the pack-lead drop'
DROP_COVERAGE = ('PATH_CELL_OUT only (CELL+ to OUT): the pack mating (PATH_PACK_POS, PATH_PACK_NEG) is not '
                 'covered; preflight C6/C11 and C12-C14 cover it, and live only the VCELL step flag')
# Every per-row flag and derived value the page draws. The page names each key (a test holds it to that).
FLAG_KEYS = ('flag_drop', 'flag_vcell_step', 'soc_suspect', 'flag_pgood', 'flag_chg', 'flag_iset')
FLAG_NAMES = {'flag_drop': 'drop form (M6)', 'flag_vcell_step': 'VCELL step (M6)', 'soc_suspect': 'SOC suspect',
              'flag_pgood': 'PGOOD vs divider (M7)', 'flag_chg': 'CHG vs ISET (M7)',
              'flag_iset': 'ISET vs INA228 (M7)'}
DERIVED = ('drop_mv', 'r_path_ohm', 'vcell_corr_v', 'v_iset_v')


@dataclasses.dataclass
class Settings:
    """What the flags need beyond the CSV. dv0_mv and r_pack_mohm None: that part is not computed."""
    dv0_mv: float | None = None
    r_pack_mohm: float | None = None
    power_mode: str = 'A'
    r_iset_ohm: float = R_ISET_OHM
    events: str = ''
    rewrite_iset: float | None = None
    preflight: dict | None = None


def logger_starts(path):
    """([(time, r_iset ohm), ...] of the logger_start events in the logger's events CSV, by time; the
    number of logger_start rows with an r_iset it could not read; error or ''). A skipped one would leave
    its rows unrescaled, so the error names the count and its first line."""
    out, skipped, first_bad = [], 0, None
    try:
        with open(path, newline='') as f:
            for n, r in enumerate(csv.DictReader(f), 2):
                m = re.search(r'\br_iset=([0-9.eE+-]+)', r.get('detail') or '')
                if r.get('event') != 'logger_start' or not m:
                    continue
                try:
                    out.append((datetime.datetime.fromisoformat(r['utc']).timestamp(), float(m.group(1))))
                except (KeyError, TypeError, ValueError):
                    skipped += 1
                    first_bad = first_bad or n
    except OSError as e:
        return [], 0, f'{path}: {e}'
    err = (f'{path}: {skipped} unreadable logger_start row{"s" if skipped > 1 else ""} skipped (first at line '
           f'{first_bad}); rows after one are taken as logged under the logger_start before it') if skipped else ''
    return sorted(out), skipped, err


_REPORTED = {}   # (what, path): the largest skipped count already printed


def report_once(what, path, skipped, text):
    """Prints `text` to stderr when `skipped` is above every count already printed for (what, path): once
    for a damaged file, not on every refresh of the page."""
    if skipped > _REPORTED.get((what, path), 0):
        _REPORTED[(what, path)] = skipped
        print(text, file=sys.stderr, flush=True)


def r_iset_at(starts, t):
    """The r_iset of the last logger_start at or before t, or None before the first one."""
    i = bisect.bisect_right([s[0] for s in starts], t)
    return starts[i - 1][1] if i else None


def iset_rows(full, cfg, starts):
    """Adds v_iset_v (inverted from the logged charge_ma with the R_ISET it was logged at) and, with
    --rewrite-iset OLD, rescales charge_ma by OLD/1000 on rows logged under a logger_start with r_iset=OLD.
    Returns the number of rows rescaled."""
    rescaled = 0
    for d in full:
        logged = r_iset_at(starts, d['t'])
        chg = d.get('charge_ma')
        d['v_iset_v'] = None if chg is None else chg * (logged or cfg.r_iset_ohm) / (K_ISET * 1000.0)
        old = cfg.rewrite_iset
        if old is not None and chg is not None and logged is not None and math.isclose(logged, old):
            d['charge_ma'] = chg * old / 1000.0
            rescaled += 1
    return rescaled


def _close(a, b):
    """True when b follows a without a gap (no packet for over GAP_S)."""
    return a is not None and b['t'] - a['t'] <= GAP_S


def _di_ok(a, b):
    """Both measured battery currents known and within CONSTANT_DI_MA of each other."""
    ia, ib = a.get('battery_ma'), b.get('battery_ma')
    return ia is not None and ib is not None and abs(ib - ia) < CONSTANT_DI_MA


def drop_rows(full, cfg):
    """M6 drop form on each row: drop_mv, r_path_ohm and flag_drop. Valid only with PGOOD inactive, the
    measured current discharging at DROP_MIN_DISCHARGE_MA or more, and dV0 known."""
    prev = None
    for d in full:
        d['drop_mv'] = d['r_path_ohm'] = None
        d['flag_drop'] = 0
        i, vc, vo = d.get('battery_ma'), d.get('vcell_v'), d.get('vout_v')
        valid = (cfg.dv0_mv is not None and not d.get('pgood') and i is not None and i <= -DROP_MIN_DISCHARGE_MA
                 and vc is not None and vo is not None)
        if not valid:
            prev = None
            continue
        d['drop_mv'] = (vc - vo) * 1000.0 - cfg.dv0_mv
        d['r_path_ohm'] = d['drop_mv'] / -i
        stepped = _close(prev, d) and _di_ok(prev, d) and abs(d['drop_mv'] - prev['drop_mv']) > DROP_STEP_MV
        d['flag_drop'] = int(d['drop_mv'] > DROP_LIMIT_MV or stepped)
        prev = d


def step_rows(full):
    """M6 VCELL step flag on each row: a gauge VCELL step over VCELL_STEP_MV from the previous sample while
    the measured battery current changed by less than CONSTANT_DI_MA."""
    prev = None
    for d in full:
        vc = d.get('vcell_v')
        d['flag_vcell_step'] = int(_close(prev, d) and vc is not None and prev.get('vcell_v') is not None
                                   and _di_ok(prev, d) and abs(vc - prev['vcell_v']) * 1000.0 > VCELL_STEP_MV)
        prev = d


def suspect_rows(full):
    """soc_suspect: from a drop or VCELL step flag until SUSPECT_S pass with no further flag."""
    last = None
    for d in full:
        if d['flag_drop'] or d['flag_vcell_step']:
            last = d['t']
        d['soc_suspect'] = int(last is not None and d['t'] - last < SUSPECT_S)


def m7_row(d):
    """The three M7 interface cross-checks on one row."""
    vin, vi, i, chg = d.get('vin_v'), d.get('v_iset_v'), d.get('battery_ma'), d.get('charge_ma')
    pg, on = bool(d.get('pgood')), bool(d.get('chg'))
    d['flag_pgood'] = int(vin is not None and ((pg and vin < PGOOD_LOW_V) or (not pg and vin > PGOOD_HIGH_V)))
    d['flag_chg'] = int(vi is not None and ((on and vi < ISET_ZERO_V) or (not on and vi > ISET_ON_V)))
    cc = on and i is not None and i > CC_MIN_MA and chg is not None
    d['flag_iset'] = int(cc and abs(chg - i) > ISET_TOL * i + ISET_TOL_MA)


def corr_row(d, r_pack_mohm):
    """M4: vcell_corr_v = VCELL - I x R_pack (I the measured current, + into the cell), else None."""
    vc, i = d.get('vcell_v'), d.get('battery_ma')
    ok = vc is not None and i is not None and r_pack_mohm is not None
    d['vcell_corr_v'] = vc - i / 1000.0 * r_pack_mohm / 1000.0 if ok else None


def termination(prev, d, r_pack_mohm):
    """P9 at a CHG release (prev CHG on, d CHG off): {t, i_ma, vcell_v, cell_v, ok, why}. A release with
    PGOOD off is the input leaving, not a termination: ok None."""
    i, vc = prev.get('battery_ma'), prev.get('vcell_v')
    cell = prev.get('vcell_corr_v')
    out = {'t': d['t'], 'i_ma': i, 'vcell_v': vc, 'cell_v': cell, 'ok': None, 'why': ''}
    if not d.get('pgood'):
        out['why'] = 'input lost (PGOOD off), not a termination'
    elif i is None or cell is None:
        out['why'] = 'no measured current or no R_pack: cannot judge'
    else:
        in_band = TERM_MIN_MA <= i <= TERM_MAX_MA
        out['ok'] = in_band and cell >= TERM_MIN_V
        out['why'] = 'healthy' if out['ok'] else (
            f'current {i:.0f} mA outside {TERM_MIN_MA:g}-{TERM_MAX_MA:g} mA' if not in_band
            else f'cell {cell:.3f} V below {TERM_MIN_V:g} V')
    return out


def terminations(full, r_pack_mohm):
    """P9: one entry per CHG release (the power-telemetry 6.3 edge, on->off between consecutive rows)."""
    return [termination(a, b, r_pack_mohm) for a, b in zip(full, full[1:], strict=False)
            if a.get('chg') and not b.get('chg') and b.get('chg') is not None]


def annotate(full, cfg):
    """Adds every derived value and flag to the row dicts. Returns (P9 terminations, rows rescaled,
    unreadable logger_start rows, events error or '')."""
    starts, ev_skipped, err = logger_starts(cfg.events) if cfg.events else ([], 0, '')
    report_once('events', cfg.events, ev_skipped, err)
    rescaled = iset_rows(full, cfg, starts)
    for d in full:
        corr_row(d, cfg.r_pack_mohm)
        m7_row(d)
    drop_rows(full, cfg)
    step_rows(full)
    suspect_rows(full)
    return terminations(full, cfg.r_pack_mohm), rescaled, ev_skipped, err


def flag_onsets(full, since_s):
    """[[time, flag key], ...]: each flag's rising edges from since_s, over every row (before thinning)."""
    out = []
    for a, b in zip([None, *full], full, strict=False):
        if b['t'] < since_s:
            continue
        out += [[b['t'], k] for k in FLAG_KEYS if b[k] and not (a and a[k])]
    return out


def labels(cfg):
    """The text the page shows beside the flags (M4, M6)."""
    r = cfg.r_pack_mohm
    return {'vcell': VCELL_LABEL,
            'vcell_corr': (f'pack terminal estimate, VCELL - I x R_pack (R_pack {r:g} mOhm)' if r is not None
                           else 'pack terminal estimate: no R_pack (--r-pack or --preflight)'),
            'drop_coverage': DROP_COVERAGE,
            'drop_basis': (f'drop = VCELL - VOUT - dV0 (dV0 {cfg.dv0_mv:g} mV, mode {cfg.power_mode})'
                           if cfg.dv0_mv is not None else 'drop form off: no dV0 (--dv0 or --preflight)'),
            'flags': FLAG_NAMES}


def _load_preflight():
    spec = importlib.util.spec_from_file_location('preflight', Path(__file__).with_name('preflight.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_settings(notes, power_mode='A', model=None, sheet=None):
    """{'status', 'problems', 'warning', 'dv0_mv', 'r_pack_mohm'} from a run's preflight block: dV0 for
    power_mode and R_pack from preflight.values(), the status from preflight.status(). A stale block is
    a warning; its values are still used."""
    pf = _load_preflight()
    kw = {k: v for k, v in (('model', model), ('sheet', sheet)) if v is not None}
    state, problems = pf.status(notes, **kw)
    vals = pf.values(notes)
    warning = {'stale': 'preflight stale: the model or build sheet changed since the run; its dV0 and R_pack are'
                        ' still used',
               'failing': 'preflight failing: wiring unverified; its dV0 and R_pack are used as stated',
               'missing': 'preflight missing: no dV0 or R_pack from it'}.get(state, '')
    return {'status': state, 'problems': problems, 'warning': warning,
            'dv0_mv': vals['dv0_mv'].get(power_mode), 'r_pack_mohm': vals['r_pack_mohm']}


def _split(rows):
    """Bucketed [t, *COLS, *DERIVED, *FLAG_KEYS] rows as (the [t, *COLS] rows, {derived key: values},
    {flag key: values}), each list aligned with the rows."""
    n, m = len(COLS) + 1, len(COLS) + 1 + len(DERIVED)
    derived = {k: [r[n + j] for r in rows] for j, k in enumerate(DERIVED)}
    flags = {k: [r[m + j] for r in rows] for j, k in enumerate(FLAG_KEYS)}
    return [r[:n] for r in rows], derived, flags


def load(path, since_s, points, gauge_from, anchor_t, shunt_from=float('inf'), cfg=None):
    """The /data answer: rows from since_s (bucketed), the gaps, the anchor, the newest packet's time
    (last_t, whatever the range), the count of unreadable rows (printed once) and shunt_from (None when not given); and
    the step 1 flags: per-row flag and derived arrays aligned with the rows, the flag onsets, the P9
    terminations, the labels and the settings they were computed with."""
    cfg = cfg or Settings()
    full, skipped, first_bad = read_rows(path, gauge_from, shunt_from)
    report_once('csv', path, skipped, f'{path}: {skipped} unreadable CSV row{"s" if skipped > 1 else ""} skipped '
                f'(first at line {first_bad})')
    terms, rescaled, events_skipped, events_error = annotate(full, cfg)   # before the count: it uses the rescaled charge_ma
    anchor, bridged = count(full, anchor_t)   # over every row, before any thinning
    ext = (*COLS, *DERIVED, *FLAG_KEYS)
    rows = [[d['t']] + [d.get(c) for c in ext] for d in full if d['t'] >= since_s]
    out_rows, derived, flags = _split(bucket(rows, points, ext))
    return {'cols': ['t', *COLS], 'rows': out_rows, 'total': len(rows),
            'gaps': gaps(full, since_s, bridged), 'anchor': anchor, 'last_t': full[-1]['t'] if full else None,
            'skipped': skipped, 'first_bad_line': first_bad,
            'marks': marks(since_s, gauge_from, shunt_from),
            'shunt_from': shunt_from if shunt_from < float('inf') else None,   # JSON has no Infinity
            'flag_keys': list(FLAG_KEYS), 'flags': flags, 'derived': derived,
            'flag_onsets': flag_onsets(full, since_s),
            'terminations': [t for t in terms if t['t'] >= since_s], 'labels': labels(cfg),
            'settings': {'dv0_mv': cfg.dv0_mv, 'r_pack_mohm': cfg.r_pack_mohm, 'power_mode': cfg.power_mode,
                         'rewrite_iset': cfg.rewrite_iset, 'rescaled_rows': rescaled, 'events_skipped': events_skipped,
                         'events_error': events_error},
            'preflight': cfg.preflight}


def handler(csv_path, sources_path, points, gauge_from, anchor_t, shunt_from=float('inf'), cfg=None):
    """The HTTP handler class: / is the page, /data?since=<unix time> the JSON. Any failure answers 500
    with {"error": ...}, so the page can say what is wrong."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            try:
                if u.path == '/data':
                    since = float(parse_qs(u.query).get('since', ['0'])[0])
                    d = load(csv_path, since, points, gauge_from, anchor_t, shunt_from, cfg)
                    d['sources'], d['sources_error'] = sources(sources_path)
                    self.send(200, json.dumps(d).encode(), 'application/json')
                elif u.path == '/':
                    self.send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
                else:
                    self.send_error(404)
            except Exception as e:   # the page shows it; the server stays up
                self.send(500, json.dumps({'error': f'{type(e).__name__}: {e}'}).encode(), 'application/json')

    return H


def settings(a, error):
    """Settings from the parsed options. --rewrite-iset without --events is refused through error()."""
    if a.rewrite_iset is not None and not a.events:
        error('--rewrite-iset needs --events (the logger\'s <out>-events.csv): only the rows logged after a '
              'logger_start with r_iset=OLD are rescaled, and without the events the rows logged at 1000 ohm '
              'cannot be told apart; nothing is rescaled')
    pf = preflight_settings(a.preflight, a.power_mode) if a.preflight else None
    pick = (lambda given, key: given if given is not None else (pf or {}).get(key))
    return Settings(dv0_mv=pick(a.dv0, 'dv0_mv'), r_pack_mohm=pick(a.r_pack, 'r_pack_mohm'),
                    power_mode=a.power_mode, r_iset_ohm=a.r_iset, events=a.events,
                    rewrite_iset=a.rewrite_iset, preflight=pf)


def finite(text):
    v = float(text)
    if not math.isfinite(v):
        raise argparse.ArgumentTypeError(f'must be a finite number: {text}')
    return v


def positive(text):
    v = finite(text)
    if v <= 0:
        raise argparse.ArgumentTypeError(f'must be above zero: {text}')
    return v


def flag_options(ap):
    """The step 1 flag options (M4, M6, M7, P9)."""
    ap.add_argument('--dv0', type=finite, default=None,
                    help='mV: gauge VCELL - INA VBUS at zero current for --power-mode (overrides --preflight)')
    ap.add_argument('--r-pack', type=finite, default=None,
                    help='mOhm: PATH_PACK_POS + PATH_PACK_NEG at 1 A, P8 (overrides --preflight)')
    ap.add_argument('--power-mode', choices=('A', 'B'), default='A', help='the run\'s power mode, for dV0')
    ap.add_argument('--preflight', default='', help='the run notes holding the preflight block (tools/preflight.py)')
    ap.add_argument('--events', default='', help='the logger\'s <out>-events.csv (its logger_start events)')
    ap.add_argument('--rewrite-iset', type=positive, default=None, metavar='OLD',
                    help='rescale charge_ma by OLD/1000 on rows logged under a logger_start with r_iset=OLD'
                         ' (needs --events; the CSV is not changed)')
    ap.add_argument('--r-iset', type=positive, default=R_ISET_OHM,
                    help='ohm: the R_ISET of rows no logger_start names, to recover V_ISET (default %(default)s)')


def options(argv=None):
    """(the parsed options, their Settings)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--csv', required=True)
    ap.add_argument('--port', type=int, default=8099)
    ap.add_argument('--points', type=int, default=1500)
    ap.add_argument('--sources', default='', help='sources.csv: start,end,source (local times) of known inputs')
    ap.add_argument('--anchor', default='', help='local time YYYY-MM-DD HH:MM:SS when the cell had rested near 0 A')
    ap.add_argument('--gauge-valid-from', default='', help='local time YYYY-MM-DD HH:MM:SS; vcell before it is hidden')
    ap.add_argument('--shunt-from', default='',
                    help='local time YYYY-MM-DD HH:MM:SS when the cell went through the INA228 shunt; the measured'
                         ' battery current is used from it on, ISET minus load (marked) before it and without it')
    flag_options(ap)
    a = ap.parse_args(argv)
    return a, settings(a, ap.error)


def main(argv=None):
    a, cfg = options(argv)
    gauge_from = local_ts(a.gauge_valid_from) if a.gauge_valid_from else 0.0
    anchor_t = local_ts(a.anchor) if a.anchor else float('inf')
    shunt_from = local_ts(a.shunt_from) if a.shunt_from else float('inf')
    H = handler(a.csv, a.sources, a.points, gauge_from, anchor_t, shunt_from, cfg)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
