#!/usr/bin/env python3
"""Score the 24-hour delivery test (H01) from the gateway database.

Rules (docs/H01-checklist.md):
  * The window [start, start + hours) is cut into one-minute intervals: the denominator.
  * An interval is ON TIME when an observation with a KNOWN acquisition time falls in it and
    was committed within 120 s of that time. Known = synchronized, or gateway-reconstructed
    with an error bound of at most 5 s (owner's rule, 2026-10-12).
  * Each interval counts once (unique intervals, not packets or retransmissions).
  * Pass: on-time intervals with a VALID sensor reading >= ceil(0.99 x intervals).
    Transport-only success (counting sensor-fault readings) is reported beside it, never
    instead of it.
  * Every other interval is reported in one category: late, sensor-fault-only, missing.
    Observations with unknown or too-uncertain time cannot be placed in an interval; they are
    counted separately as invalid-clock. Nothing is silently excluded.
  * Serial-link gaps (H8 in docs/superpowers/specs/2026-10-29-build-progression-decisions.md)
    are listed beside the score, never in it, from the gateway's own gateway_events rows: a
    serial-lost to the next serial-open; a serial-reopen, over its silent_s; a receiver-silent
    from the start of the silence it names to the next RX report ('#alive' in rx_alive, or an
    rx_boot event); and each run of missing '#alive' minutes in rx_alive (kind alive-missing):
    two reports more than ALIVE_LATE_S apart, so one missed 60 s report shows, from the last
    report heard to the next. No run is inferred before the station's first '#alive' row ever
    (an RX that never sent one); the last row before the window is read, so a silence that
    began earlier is kept. A gap still open at the window end ends there and is marked open. Gaps
    are clipped to the window; the total counts overlapping time once.

  .venv/bin/python tools/h01_report.py --db run-hw/observations.sqlite3 --station station-01 \
      --start 2026-10-15T00:00:00Z --hours 24 --output evidence/h01-2026-10-15
"""
import argparse
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MINUTE_S = 60
MINUTES_PER_HOUR = 60
REQUIRED_FRACTION = 0.99   # the pass rule: at least 99 % of the minutes on time
LATENCY_S = 120
TIME_TOLERANCE_S = 5

EDGE_S = 2   # readings closer than this to an interval edge make the interval grid unreliable
RECEIVER_SILENT_S = 180   # ws0/__main__.py: the silence a receiver-silent row reports, when its text names none
# The kind is the word after '#gateway' (ws0/web.py Telemetry.event); the receiver-silent line has a
# colon after that word, so both spellings are read.
LINK_KINDS = ('serial-lost', 'serial-open', 'serial-reopen', 'receiver-silent', 'receiver-silent:')
# The RX sends '#alive' every 60 s (firmware/stage0-node/App/app_rx.c:70). Two reports further apart
# than one and a half periods mean at least one report was missed: a 120 s silence shows, jitter does not.
ALIVE_PERIOD_S = 60
ALIVE_LATE_S = ALIVE_PERIOD_S * 3 // 2
SILENT_TEXT = {'serial-reopen': re.compile(r'silent_s=(\d+)'), 'receiver-silent': re.compile(r'for (\d+) s')}

def utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('start must include a timezone, for example Z')
    return value.timestamp()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


RANKS = ('on_time_valid', 'on_time_sensor_fault', 'late')   # an interval's category, best first


def known_time(effective, basis, uncertainty):
    """Synchronized, or reconstructed within the tolerance: the reading can be placed in an interval."""
    return effective is not None and basis in ('synchronized', 'reconstructed') and \
        (uncertainty or 0) <= TIME_TOLERANCE_S


def rank(record, latency):
    """Index into RANKS. The test scores the validity of the temperature and humidity fields
    themselves (docs/protocol-design.md section 5.7)."""
    valid = record.get('temperature_c') is not None and record.get('humidity_pct') is not None
    return (0 if valid else 1) if 0 <= latency <= LATENCY_S else 2


class Placement:
    """Each interval's best reading: interval -> (rank, latency, time basis); lower is better. The
    grid diagnostics (readings per interval, readings near an edge) never change the verdict."""
    def __init__(self, start, minutes):
        self.start, self.minutes = start, minutes
        self.best, self.invalid_clock, self.epochs = {}, 0, set()
        self.per_minute, self.edge = {}, 0

    def add(self, session, effective, received, basis, uncertainty, payload):
        self.epochs.add(session)
        if not known_time(effective, basis, uncertainty):
            self.invalid_clock += 1
            return
        minute = int((effective - self.start) // MINUTE_S)
        if not 0 <= minute < self.minutes:
            return
        self.per_minute[minute] = self.per_minute.get(minute, 0) + 1
        phase = (effective - self.start) % MINUTE_S
        self.edge += int(phase < EDGE_S or phase > MINUTE_S - EDGE_S)
        latency = received - effective
        candidate = (rank(json.loads(payload), latency), latency)
        if minute not in self.best or candidate < self.best[minute][:2]:
            self.best[minute] = (*candidate, basis)


def tally(best):
    """From each interval's final choice (an earlier pick may have been replaced): intervals per
    category, on-time intervals that used a reconstructed time, and the sorted on-time latencies."""
    counts = dict.fromkeys(RANKS, 0)
    for r, _, _ in best.values():
        counts[RANKS[r]] += 1
    reconstructed_used = sum(1 for r, _, basis in best.values() if r < 2 and basis == 'reconstructed')
    latencies = sorted(lat for r, lat, _ in best.values() if r < 2)
    return counts, reconstructed_used, latencies


def grid_warning(edge, several):
    """The node's clock is set from ACKs to whole seconds and its sample timer runs freely, so
    sample times jitter by about a second. Readings this close to an interval edge can land two in
    one interval and none in the next: a miss that lost no data. The rule itself is unchanged; pick
    a --start that puts the readings mid-interval and score again."""
    if not edge:
        return None
    return (f'{edge} readings lie within {EDGE_S} s of an interval edge and {several} intervals hold more '
            'than one reading: choose a --start that puts the readings mid-interval')


def has_table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def silent_for(kind, text, default):
    """The silence a serial-reopen (silent_s=) or receiver-silent (for N s) row reports."""
    found = SILENT_TEXT[kind].search(text or '')
    return int(found.group(1)) if found else default


def next_rx_report(db, station, at):
    """Time of the first RX report after `at`: an '#alive' row or an RX boot, or None."""
    times = []
    if has_table(db, 'rx_alive'):
        times.append(db.execute('SELECT min(received_at) FROM rx_alive WHERE station=? AND received_at>?',
                                (station, at)).fetchone()[0])
    times.append(db.execute("SELECT min(at) FROM gateway_events WHERE station=? AND kind='rx_boot' AND at>?",
                            (station, at)).fetchone()[0])
    times = [t for t in times if t is not None]
    return min(times) if times else None


def raw_gaps(db, station, end):
    """(kind, start, end or None) for every link gap that starts before `end`. Rows before the
    window are read too, so a gap that began earlier and is still open is not missed."""
    rows = db.execute(f"SELECT at,kind,text FROM gateway_events WHERE station=? AND at<? "
                      f"AND kind IN ({','.join('?' * len(LINK_KINDS))}) ORDER BY at,id",
                      (station, end, *LINK_KINDS)).fetchall()
    gaps, lost_at = [], None
    for at, kind, text in rows:
        kind = kind.rstrip(':')
        if kind == 'serial-lost' and lost_at is None:
            lost_at = at
        elif kind == 'serial-open' and lost_at is not None:
            gaps.append(('serial-lost', lost_at, at))
            lost_at = None
        elif kind == 'serial-reopen':
            gaps.append((kind, at - silent_for(kind, text, 0), at))
        elif kind == 'receiver-silent':
            gaps.append((kind, at - silent_for(kind, text, RECEIVER_SILENT_S), next_rx_report(db, station, at)))
    if lost_at is not None:
        gaps.append(('serial-lost', lost_at, None))
    return gaps


def alive_gaps(db, station, start, end):
    """(kind, start, end or None) for each run of missing '#alive' reports before `end`: from the
    last report heard to the next one (None: none came before `end`). Empty when the database has
    no rx_alive table or the station has no '#alive' row before `start` or in the window."""
    if not has_table(db, 'rx_alive'):
        return []
    before = db.execute('SELECT max(received_at) FROM rx_alive WHERE station=? AND received_at<?',
                        (station, start)).fetchone()[0]
    times = [at for (at,) in db.execute('SELECT received_at FROM rx_alive WHERE station=? AND received_at>=? '
                                        'AND received_at<? ORDER BY received_at',
                                        (station, start if before is None else before, end))]
    gaps = [('alive-missing', a, b) for a, b in zip(times, times[1:], strict=False) if b - a > ALIVE_LATE_S]
    if times and end - times[-1] > ALIVE_LATE_S:
        gaps.append(('alive-missing', times[-1], None))
    return gaps


def serial_gaps(db, station, start, end):
    """The link gaps clipped to [start, end), in start order, or None when the database has no
    gateway_events table (a gateway older than the telemetry tables: gaps unknown, not zero)."""
    if not has_table(db, 'gateway_events'):
        return None
    gaps = []
    for kind, begin, finish in raw_gaps(db, station, end) + alive_gaps(db, station, start, end):
        still_open = finish is None or finish >= end
        lo, hi = max(begin, start), (end if still_open else finish)
        if hi > lo or (hi == lo and begin >= start):
            gaps.append({'kind': kind, 'start': iso(lo), 'end': iso(hi), 'duration_s': round(hi - lo, 1),
                         'open_at_window_end': still_open, '_span': (lo, hi)})
    return sorted(gaps, key=lambda g: g['_span'])


def union_s(spans):
    """Seconds covered by the spans, overlapping time counted once (spans sorted by start)."""
    total, reach = 0.0, None
    for lo, hi in spans:
        if reach is None or lo > reach:
            total, reach = total + hi - lo, hi
        elif hi > reach:
            total, reach = total + hi - reach, hi
    return round(total, 1)


def gap_summary(db, station, start, end):
    gaps = serial_gaps(db, station, start, end)
    if gaps is None:
        return {'serial_gaps': None, 'serial_gap_count': None, 'serial_gap_total_s': None}
    total = union_s([g.pop('_span') for g in gaps])
    return {'serial_gaps': gaps, 'serial_gap_count': len(gaps), 'serial_gap_total_s': total}


def score(db, station, start, hours):
    minutes = int(round(hours * MINUTES_PER_HOUR))
    end = start + minutes * MINUTE_S
    required = math.ceil(REQUIRED_FRACTION * minutes)
    rows = db.execute('''SELECT session,sequence,effective_at,received_at,time_basis,time_uncertainty_s,payload
        FROM observations WHERE station=? AND ((effective_at>=? AND effective_at<?)
        OR (effective_at IS NULL AND received_at>=? AND received_at<?+?))''',
        (station, start, end, start, end, LATENCY_S)).fetchall()
    placed = Placement(start, minutes)
    for session, _sequence, *reading in rows:
        placed.add(session, *reading)
    counts, reconstructed_used, latencies = tally(placed.best)
    missing = [m for m in range(minutes) if m not in placed.best]
    several = sum(1 for n in placed.per_minute.values() if n > 1)
    rejections = db.execute('SELECT count(*) FROM rejections WHERE station=? AND received_at>=? AND received_at<?',
                            (station, start, end + LATENCY_S)).fetchone()[0]
    return {
        'gate': 'H01', 'station': station, 'window_start': iso(start), 'window_end': iso(end),
        'intervals': minutes, 'required_on_time_valid': required,
        **counts,
        'transport_on_time': counts['on_time_valid'] + counts['on_time_sensor_fault'],
        'missing': len(missing),
        'missing_first': [iso(start + MINUTE_S * m) for m in missing[:20]],
        'invalid_clock_observations': placed.invalid_clock,
        'reconstructed_time_intervals_counted': reconstructed_used,
        'latency_median_s': latencies[len(latencies) // 2] if latencies else None,
        'latency_max_on_time_s': latencies[-1] if latencies else None,
        'boot_epochs_seen': len(placed.epochs), 'gateway_rejections': rejections,
        'intervals_with_several_readings': several, 'readings_near_interval_edge': placed.edge,
        'grid_warning': grid_warning(placed.edge, several),
        **gap_summary(db, station, start, end),
        'verdict': 'PASS' if counts['on_time_valid'] >= required else 'FAIL',
    }


def markdown(r):
    lines = [f"# H01 report — {r['verdict']}", '',
             f"Window: {r['window_start']} to {r['window_end']} ({r['intervals']} one-minute intervals)", '',
             '| Measure | Value |', '|---|---:|']
    for key in ('required_on_time_valid', 'on_time_valid', 'on_time_sensor_fault', 'transport_on_time',
                'late', 'missing', 'invalid_clock_observations', 'reconstructed_time_intervals_counted',
                'latency_median_s', 'latency_max_on_time_s', 'boot_epochs_seen', 'gateway_rejections',
                'intervals_with_several_readings', 'readings_near_interval_edge',
                'serial_gap_count', 'serial_gap_total_s'):
        value = r[key]
        value = 'not recorded' if value is None and key.startswith('serial') else value
        lines.append(f"| {key.replace('_', ' ')} | {round(value, 1) if isinstance(value, float) else value} |")
    if r['grid_warning']:
        lines += ['', f"**Warning:** {r['grid_warning']}."]
    if r['missing_first']:
        lines += ['', 'First missing intervals: ' + ', '.join(r['missing_first'])]
    return '\n'.join(lines + gap_lines(r['serial_gaps'])) + '\n'


def gap_lines(gaps):
    """The serial-link gap table (H8): one row per gap, or why there is none."""
    if gaps is None:
        return ['', 'Serial-link gaps: not recorded (no gateway_events table in this database).']
    if not gaps:
        return ['', 'Serial-link gaps: none in the window.']
    lines = ['', '## Serial-link gaps', '', '| Kind | Start | End | Duration s | Open at window end |',
             '|---|---|---|---:|---|']
    for g in gaps:
        lines.append(f"| {g['kind']} | {g['start']} | {g['end']} | {g['duration_s']} | "
                     f"{'yes' if g['open_at_window_end'] else 'no'} |")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', type=Path, default=Path('run-hw/observations.sqlite3'))
    ap.add_argument('--station', default='station-01')
    ap.add_argument('--start', required=True, help='UTC, e.g. 2026-10-15T00:00:00Z')
    ap.add_argument('--hours', type=float, default=24)
    ap.add_argument('--output', type=Path, help='new directory for report.json and report.md')
    args = ap.parse_args()
    db = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    result = score(db, args.station, utc(args.start), args.hours)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
        (args.output / 'report.md').write_text(markdown(result))
    print(markdown(result))
    raise SystemExit(0 if result['verdict'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
