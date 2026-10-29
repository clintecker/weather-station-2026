"""Live local dashboard for the bench telemetry CSV (tools/benchlink_log.py).

    .venv/bin/python tools/benchlink_dash.py --csv <benchlink.csv> [--port 8099] [--points 1500]
        [--sources <sources.csv>] [--anchor "YYYY-MM-DD HH:MM:SS"] [--gauge-valid-from "YYYY-MM-DD HH:MM:SS"]

Serves http://127.0.0.1:<port>/ (the page, benchlink_dash.html) and /data?since=<unix time>: JSON with the
CSV's numeric columns from that time (bucketed to at most --points rows), the counted charge (soc_cc,
q_mah), the gaps, the input windows of --sources, the anchor, marks and the newest packet's time. Local
only; no external libraries in the page.

The state of charge is counted from --anchor (a moment when the cell had rested near 0 A; without it,
nothing is counted): the start from the rest voltage (OCV, about +-10 %), then the net battery current
integrated over time. A gap (no packet for over GAP_S) is bridged with the mean battery current at its two
ends, and that estimate is reported with the gap."""
import argparse
import csv
import datetime
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

COLS = ('charge_ma', 'load_ma', 'vcell_v', 'temp_c', 'rh_pct', 'rssi', 'pgood', 'chg', 'vout_v', 'vin_v', 'soc_pct',
        'soc_cc', 'q_mah')
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
    """Net battery current, + into the cell: the ISET charge current, minus the load when the battery carries
    it (PGOOD off, or OUT sagged to the cell while the input is weak: then the whole load is counted, an upper
    bound on what the battery gave)."""
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


def read_rows(path, gauge_from):
    """The CSV as row dicts, and (rows skipped, the first skipped line number). A row it cannot read (a
    line cut off while the logger writes it, a damaged file) is skipped and counted, not fatal."""
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
            full.append(d)
    return full, skipped, first_bad


def bucket(rows, points):
    """At most `points` rows: bucket means; the state columns keep the bucket's last value."""
    if len(rows) <= points:
        return rows
    size = len(rows) / points
    out = []
    for i in range(points):
        chunk = rows[int(i * size):int((i + 1) * size)] or rows[-1:]
        agg = [chunk[-1][0]]
        for k in range(1, len(COLS) + 1):
            vals = [c[k] for c in chunk if c[k] is not None]
            if COLS[k - 1] in ('pgood', 'chg'):
                agg.append(vals[-1] if vals else None)
            else:
                agg.append(sum(vals) / len(vals) if vals else None)
        out.append(agg)
    return out


def load(path, since_s, points, gauge_from, anchor_t):
    """The /data answer: rows from since_s (bucketed), the gaps, the anchor, the newest packet's time
    (last_t, whatever the range) and the count of unreadable rows."""
    full, skipped, first_bad = read_rows(path, gauge_from)
    anchor, bridged = count(full, anchor_t)   # over every row, before any thinning
    rows = [[d['t']] + [d.get(c) for c in COLS] for d in full if d['t'] >= since_s]
    return {'cols': ['t', *COLS], 'rows': bucket(rows, points), 'total': len(rows),
            'gaps': gaps(full, since_s, bridged), 'anchor': anchor, 'last_t': full[-1]['t'] if full else None,
            'skipped': skipped, 'first_bad_line': first_bad,
            'marks': [[gauge_from, 'gauge on cell']] if gauge_from > since_s else []}


def handler(csv_path, sources_path, points, gauge_from, anchor_t):
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
                    d = load(csv_path, since, points, gauge_from, anchor_t)
                    d['sources'], d['sources_error'] = sources(sources_path)
                    self.send(200, json.dumps(d).encode(), 'application/json')
                elif u.path == '/':
                    self.send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
                else:
                    self.send_error(404)
            except Exception as e:   # the page shows it; the server stays up
                self.send(500, json.dumps({'error': f'{type(e).__name__}: {e}'}).encode(), 'application/json')

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--csv', required=True)
    ap.add_argument('--port', type=int, default=8099)
    ap.add_argument('--points', type=int, default=1500)
    ap.add_argument('--sources', default='', help='sources.csv: start,end,source (local times) of known inputs')
    ap.add_argument('--anchor', default='', help='local time YYYY-MM-DD HH:MM:SS when the cell had rested near 0 A')
    ap.add_argument('--gauge-valid-from', default='', help='local time YYYY-MM-DD HH:MM:SS; vcell before it is hidden')
    a = ap.parse_args()
    gauge_from = local_ts(a.gauge_valid_from) if a.gauge_valid_from else 0.0
    anchor_t = local_ts(a.anchor) if a.anchor else float('inf')
    H = handler(a.csv, a.sources, a.points, gauge_from, anchor_t)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
