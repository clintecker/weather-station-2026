#!/usr/bin/env python3
"""H01 scorer: compute the 24-hour placement verdict from the gateway database.

Rules (docs/H01-checklist.md):
  * The window [start, start + hours) is cut into one-minute intervals: the denominator.
  * An interval is ON TIME when an observation with a KNOWN acquisition time falls in it and
    was committed within 120 s of that time. Known = synchronized, or gateway-reconstructed
    with an error bound of at most 5 s (Clint, 2026-10-12).
  * Each interval counts once (unique intervals, not packets or retransmissions).
  * Pass: on-time intervals with a VALID sensor reading >= ceil(0.99 x intervals).
    Transport-only success (counting sensor-fault readings) is reported beside it, never
    instead of it.
  * Every other interval is reported in one category: late, sensor-fault-only, missing.
    Observations with unknown or too-uncertain time cannot be placed in an interval; they are
    counted separately as invalid-clock. Nothing is silently excluded.

  .venv/bin/python tools/h01_report.py --db run-hw/observations.sqlite3 --station station-01 \
      --start 2026-10-15T00:00:00Z --hours 24 --output evidence/h01-2026-10-15
"""
import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MINUTE_S = 60
MINUTES_PER_HOUR = 60
REQUIRED_FRACTION = 0.99   # H01: at least 99 % of the minutes on time
LATENCY_S = 120
TIME_TOLERANCE_S = 5

EDGE_S = 2   # readings closer than this to an interval edge make the interval grid unreliable

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
    """Index into RANKS. H01 scores the T/RH fields' own validity (draft-5 design 5.7)."""
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
        'verdict': 'PASS' if counts['on_time_valid'] >= required else 'FAIL',
    }


def markdown(r):
    lines = [f"# H01 report — {r['verdict']}", '',
             f"Window: {r['window_start']} to {r['window_end']} ({r['intervals']} one-minute intervals)", '',
             '| Measure | Value |', '|---|---:|']
    for key in ('required_on_time_valid', 'on_time_valid', 'on_time_sensor_fault', 'transport_on_time',
                'late', 'missing', 'invalid_clock_observations', 'reconstructed_time_intervals_counted',
                'latency_median_s', 'latency_max_on_time_s', 'boot_epochs_seen', 'gateway_rejections',
                'intervals_with_several_readings', 'readings_near_interval_edge'):
        value = r[key]
        lines.append(f"| {key.replace('_', ' ')} | {round(value, 1) if isinstance(value, float) else value} |")
    if r['grid_warning']:
        lines += ['', f"**Warning:** {r['grid_warning']}."]
    if r['missing_first']:
        lines += ['', 'First missing intervals: ' + ', '.join(r['missing_first'])]
    return '\n'.join(lines) + '\n'


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
