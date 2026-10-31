#!/usr/bin/env python3
"""Bad receptions the RX board reported ('#rx crc', '#rx hdr'), from the gateway database.

Every one is stored in the rx_faults table (ws0/web.py), up to the noise rate limit, for
RX_FAULT_RETENTION_S (30 days). A CRC failure keeps the bytes the radio received; this tool
classifies each capture:

  * ours          the first byte is one of our frame kinds in the current protocol version:
                  {current}.
                  The closest authentic frame the gateway accepted within +-5 s is shown
                  with the bit difference (Hamming distance) to the capture: a few bits
                  means our frame, corrupted on the air; about half the bits means a
                  different frame (a retry has a new counter, so new ciphertext).
  * ours (previous version)
                  the first byte is one of our frame kinds in the previous protocol version:
                  {previous}.
                  A capture retained from the previous release's run, or a board not yet
                  flashed with this release (the gateway drops its frames). Shown like ours.
  * ours (damaged header)
                  the first byte is not one of our kinds, but an accepted frame within +-5 s
                  differs from the capture in under 10% of its bits: our frame, with the kind
                  byte among the corrupted ones.
  * foreign/noise anything else: another 915 MHz device, or noise that happened to decode.
  * header        a header CRC failure: nothing was received to classify.

Accepted frames are the radio_events rows with outcome ack, duplicate, diag or nack; only those
keep their bytes (frame_hex). The database is opened read-only (safe beside a running gateway).
A database whose tables predate this version is reported as such (no migrations), not with a
traceback.

  .venv/bin/python tools/rx_faults.py --db run-hw/observations.sqlite3 [--since 2026-10-15T00:00:00Z]
      [--until 2026-10-16T00:00:00Z] [--limit 50] [--json]
"""  # {current} and {previous}: the byte-0 values from ws0.protocol, filled in below (kind_bytes)
import argparse
import bisect
import collections
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import open_read_only  # noqa: E402
from ws0.protocol import (COUNTER_AT, HEADER_LEN, STATION_AT, KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS,  # noqa: E402
                          VERSION, VERSION_SHIFT)
from ws0.web import ACCEPTED_OUTCOMES as ACCEPTED, SchemaDrift, check_schema  # noqa: E402

FRAME_KINDS = ((KIND_OBS, 'obs'), (KIND_ACK, 'ack'), (KIND_NACK, 'nack'), (KIND_DIAG, 'diag'))
PREVIOUS_VERSION = VERSION - 1
CLASS_BY_VERSION = {VERSION: 'ours', PREVIOUS_VERSION: 'ours (previous version)'}
KINDS = {(version << VERSION_SHIFT) | k: (version, name)        # byte 0 -> (protocol version, frame kind)
         for version in CLASS_BY_VERSION for k, name in FRAME_KINDS}
WINDOW_S = 5
DAMAGED_HEADER_BITS = 0.10   # a capture this close to an accepted frame is ours, whatever its kind byte
OURS = ('ours', 'ours (previous version)', 'ours (damaged header)')


def kind_bytes(version):
    """The byte-0 values of one protocol version, e.g. 'version 6: 0x61 obs, 0x62 ack, 0x63 nack, 0x64 diag'."""
    return f'version {version}: ' + ', '.join(f'0x{(version << VERSION_SHIFT) | k:02x} {name}' for k, name in FRAME_KINDS)


__doc__ = __doc__.format(current=kind_bytes(VERSION), previous=kind_bytes(PREVIOUS_VERSION))


def utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('--since and --until must include a timezone, for example Z')
    return value.timestamp()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hamming(a, b):
    """Differing bits; each byte one frame has past the other's end counts 8."""
    return sum(bin(x ^ y).count('1') for x, y in zip(a, b, strict=False)) + 8 * abs(len(a) - len(b))


def header(data):
    """Station and counter from a capture's header (whatever it holds)."""
    if len(data) < HEADER_LEN:
        return {}
    return {'station_id': int.from_bytes(data[STATION_AT:COUNTER_AT], 'big'), 'counter': int.from_bytes(data[COUNTER_AT:HEADER_LEN], 'big')}


def closest(fault, data, accepted):
    """The accepted frame nearest in time to the capture, with its bit difference; None if none."""
    if not accepted:
        return None
    at, outcome, frame = min(accepted, key=lambda a: (abs(a[0] - fault['received_at']), a[0]))
    return {'dt_s': round(at - fault['received_at'], 3), 'outcome': outcome, 'length': len(frame),
            'bits_differ': hamming(data, frame), 'bits': 8 * max(len(data), len(frame)),
            **({'counter': int.from_bytes(frame[COUNTER_AT:HEADER_LEN], 'big')} if len(frame) >= HEADER_LEN else {})}


def classify(fault, accepted):
    """One rx_faults row (dict) -> dict with 'class' and, for ours, the closest accepted frame.
    accepted: [(received_at, outcome, frame bytes)] within the window."""
    out = dict(fault)
    if fault['kind'] == 'hdr':
        return out | {'class': 'header'}
    data = bytes.fromhex(fault['data'] or '')
    if not data:
        return out | {'class': 'foreign/noise'}
    match = closest(fault, data, accepted)
    if data[0] in KINDS:
        version, kind = KINDS[data[0]]
        return out | {'class': CLASS_BY_VERSION[version], 'frame_version': version, 'frame_kind': kind,
                      **header(data), 'match': match}
    if match and match['bits_differ'] < DAMAGED_HEADER_BITS * match['bits']:
        return out | {'class': 'ours (damaged header)', 'match': match}
    return out | {'class': 'foreign/noise'}


def load(db, since=0.0, until=None, limit=None, window_s=WINDOW_S):
    """Bad receptions received in [since, until), the newest `limit` of them, oldest first, each
    classified. The accepted frames around them come from one query over the whole span."""
    cols = ('id', 'station', 'received_at', 'kind', 'length', 'rssi_dbm', 'snr_db', 'data')
    faults = [dict(zip(cols, r, strict=True)) for r in db.execute(
        f'SELECT {",".join(cols)} FROM rx_faults WHERE received_at>=? AND received_at<? '
        'ORDER BY received_at DESC,id DESC LIMIT ?',
        (since, float('inf') if until is None else until, -1 if limit is None else limit))][::-1]
    if not faults:
        return []
    stations = sorted({f['station'] for f in faults})
    frames = collections.defaultdict(list)   # station -> [(received_at, outcome, frame bytes)], by time
    for station, at, outcome, frame_hex in db.execute(
            f'SELECT station,received_at,outcome,frame_hex FROM radio_events WHERE station IN '
            f'({",".join("?" * len(stations))}) AND received_at>=? AND received_at<=? '
            f'AND outcome IN ({",".join("?" * len(ACCEPTED))}) AND frame_hex IS NOT NULL ORDER BY received_at',
            (*stations, faults[0]['received_at'] - window_s, faults[-1]['received_at'] + window_s, *ACCEPTED)):
        frames[station].append((at, outcome, bytes.fromhex(frame_hex)))
    times = {station: [a[0] for a in near] for station, near in frames.items()}
    rows = []
    for f in faults:
        near, t = frames.get(f['station'], []), times.get(f['station'], [])
        lo = bisect.bisect_left(t, f['received_at'] - window_s)
        hi = bisect.bisect_right(t, f['received_at'] + window_s)
        rows.append(classify(f, near[lo:hi]))
    return rows


def summarize(rows):
    by = lambda c: [r for r in rows if r['class'] == c]
    ours = by('ours')
    matched = [r for r in rows if r['class'] in OURS and r.get('match')]
    rssi = [r['rssi_dbm'] for r in rows if r['rssi_dbm'] is not None]
    return {'total': len(rows), 'crc': sum(r['kind'] == 'crc' for r in rows), 'hdr': len(by('header')),
            'ours': len(ours), 'ours_previous_version': len(by('ours (previous version)')),
            'ours_damaged_header': len(by('ours (damaged header)')),
            'ours_matched': len(matched), 'foreign_or_noise': len(by('foreign/noise')),
            'median_bits_differ': statistics.median(r['match']['bits_differ'] for r in matched) if matched else None,
            'rssi_dbm_min': min(rssi, default=None), 'rssi_dbm_max': max(rssi, default=None),
            'first': iso(rows[0]['received_at']) if rows else None, 'last': iso(rows[-1]['received_at']) if rows else None}


def detail(r):
    head = f"{iso(r['received_at'])}  {r['kind']:3}  rssi={r['rssi_dbm']} dBm"
    if r['kind'] == 'hdr':
        return head + '  header CRC failed (no payload)'
    head += f"  snr={r['snr_db']} dB  len={r['length']}  {r['class']}"
    if r['class'] in OURS:
        if 'frame_kind' in r:
            head += f"  {r['frame_kind']}" + ('' if r['class'] == 'ours' else f" (version {r['frame_version']})") + (f" station={r['station_id']} counter={r['counter']}" if 'counter' in r else '')
        m = r['match']
        head += (f"\n    closest accepted frame {m['dt_s']:+.1f} s ({m['outcome']}, {m['length']} B"
                 + (f", counter={m['counter']}" if 'counter' in m else '')
                 + f"): {m['bits_differ']} of {m['bits']} bits differ") if m else f'\n    no accepted frame within +-{WINDOW_S} s'
    return head + f"\n    data={r['data']}"


def report(rows):
    s = summarize(rows)
    if not s['total']:
        return 'No bad receptions stored.'
    lines = [f"{s['total']} bad receptions {s['first']} .. {s['last']}: {s['crc']} CRC, {s['hdr']} header",
             f"CRC captures: {s['ours']} look like ours, {s['ours_damaged_header']} ours with a damaged header "
             f"({s['ours_matched']} with an accepted frame within +-{WINDOW_S} s, median {s['median_bits_differ']} "
             f"bits differ), {s['ours_previous_version']} ours from the previous protocol version "
             f"({PREVIOUS_VERSION}), {s['foreign_or_noise']} foreign/noise",
             f"RSSI {s['rssi_dbm_min']} .. {s['rssi_dbm_max']} dBm", '']
    return '\n'.join(lines + [detail(r) for r in rows])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', type=Path, default=Path('run-hw/observations.sqlite3'))
    ap.add_argument('--since', help='UTC, e.g. 2026-10-15T00:00:00Z (default: everything)')
    ap.add_argument('--until', help='UTC, exclusive, e.g. 2026-10-16T00:00:00Z (default: now)')
    ap.add_argument('--limit', type=int, help='only the newest N bad receptions in the range')
    ap.add_argument('--json', action='store_true', help='one JSON object: summary and rows')
    args = ap.parse_args(argv)
    if not args.db.exists():
        ap.error(f'no database at {args.db}')
    if args.limit is not None and args.limit < 1:
        ap.error('--limit must be at least 1')
    try:
        since, until = utc(args.since) if args.since else 0.0, utc(args.until) if args.until else None
    except ValueError as exc:
        ap.error(str(exc))
    db = open_read_only(args.db)
    try:
        check_schema(db, args.db, ('radio_events', 'rx_faults'))
        rows = load(db, since, until, args.limit)
    except SchemaDrift as exc:
        raise SystemExit(f'rx_faults: {exc}') from None
    finally:
        db.close()
    print(json.dumps({'summary': summarize(rows), 'rows': rows}, indent=2) if args.json else report(rows))


if __name__ == '__main__':
    main()
