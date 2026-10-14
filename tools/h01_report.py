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

LATENCY_S = 120
TIME_TOLERANCE_S = 5


def utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('start must include a timezone, for example Z')
    return value.timestamp()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def score(db, station, start, hours):
    minutes = int(round(hours * 60))
    end = start + minutes * 60
    required = math.ceil(0.99 * minutes)
    rows = db.execute('''SELECT session,sequence,effective_at,received_at,time_basis,time_uncertainty_s,payload
        FROM observations WHERE station=? AND ((effective_at>=? AND effective_at<?)
        OR (effective_at IS NULL AND received_at>=? AND received_at<?+?))''',
        (station, start, end, start, end, LATENCY_S)).fetchall()
    best = {}  # interval -> (rank, latency); rank 0 on-time valid, 1 on-time fault, 2 late
    invalid_clock, reconstructed_used, epochs = 0, 0, set()
    for session, _sequence, effective, received, basis, uncertainty, payload in rows:
        epochs.add(session)
        known = effective is not None and basis in ('synchronized', 'reconstructed') and \
            (uncertainty or 0) <= TIME_TOLERANCE_S
        if not known:
            invalid_clock += 1
            continue
        minute = int((effective - start) // 60)
        if not 0 <= minute < minutes:
            continue
        latency = received - effective
        valid = json.loads(payload)['quality'] == 'valid'
        rank = (0 if valid else 1) if 0 <= latency <= LATENCY_S else 2
        if minute not in best or (rank, latency) < best[minute]:
            best[minute] = (rank, latency)
            if rank < 2 and basis == 'reconstructed':
                reconstructed_used += 1
    counts = {'on_time_valid': 0, 'on_time_sensor_fault': 0, 'late': 0}
    for rank, _ in best.values():
        counts[('on_time_valid', 'on_time_sensor_fault', 'late')[rank]] += 1
    missing = [m for m in range(minutes) if m not in best]
    latencies = sorted(lat for rank, lat in best.values() if rank < 2)
    rejections = db.execute('SELECT count(*) FROM rejections WHERE station=? AND received_at>=? AND received_at<?',
                            (station, start, end + LATENCY_S)).fetchone()[0]
    return {
        'gate': 'H01', 'station': station, 'window_start': iso(start), 'window_end': iso(end),
        'intervals': minutes, 'required_on_time_valid': required,
        **counts,
        'transport_on_time': counts['on_time_valid'] + counts['on_time_sensor_fault'],
        'missing': len(missing),
        'missing_first': [iso(start + 60 * m) for m in missing[:20]],
        'invalid_clock_observations': invalid_clock,
        'reconstructed_time_intervals_counted': reconstructed_used,
        'latency_median_s': latencies[len(latencies) // 2] if latencies else None,
        'latency_max_on_time_s': latencies[-1] if latencies else None,
        'boot_epochs_seen': len(epochs), 'gateway_rejections': rejections,
        'verdict': 'PASS' if counts['on_time_valid'] >= required else 'FAIL',
    }


def markdown(r):
    lines = [f"# H01 report — {r['verdict']}", '',
             f"Window: {r['window_start']} to {r['window_end']} ({r['intervals']} one-minute intervals)", '',
             '| Measure | Value |', '|---|---:|']
    for key in ('required_on_time_valid', 'on_time_valid', 'on_time_sensor_fault', 'transport_on_time',
                'late', 'missing', 'invalid_clock_observations', 'reconstructed_time_intervals_counted',
                'latency_median_s', 'latency_max_on_time_s', 'boot_epochs_seen', 'gateway_rejections'):
        value = r[key]
        lines.append(f"| {key.replace('_', ' ')} | {round(value, 1) if isinstance(value, float) else value} |")
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
