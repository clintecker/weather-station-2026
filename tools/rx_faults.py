#!/usr/bin/env python3
"""Bad receptions the RX board reported ('#rx crc', '#rx hdr'), from the gateway database.

Every one is stored in the rx_faults table (ws0/web.py), up to the GW6 rate limit. A CRC failure
keeps the bytes the radio received; this tool classifies each capture:

  * ours          the first byte is one of our frame kinds (version 5: 0x51 obs, 0x52 ack,
                  0x53 nack, 0x54 diag). The closest authentic frame the gateway accepted within
                  +-5 s is shown with the bit difference (Hamming distance) to the capture: a few
                  bits means our frame, corrupted on the air; about half the bits means a
                  different frame (a retry has a new counter, so new ciphertext).
  * foreign/noise anything else: another 915 MHz device, or noise that happened to decode.
  * header        a header CRC failure: nothing was received to classify.

The database is opened read-only (safe beside a running gateway).

  .venv/bin/python tools/rx_faults.py --db run-hw/observations.sqlite3 [--since 2026-10-15T00:00:00Z] [--json]
"""
import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import open_read_only  # noqa: E402

VERSION, HEADER_LEN = 5, 8   # ws0/protocol.py, firmware/common/ws_frame.h
KINDS = {(VERSION << 4) | k: name for k, name in ((1, 'obs'), (2, 'ack'), (3, 'nack'), (4, 'diag'))}
ACCEPTED = ('ack', 'duplicate', 'diag', 'nack')   # radio_events outcomes of authentic frames
WINDOW_S = 5


def utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('--since must include a timezone, for example Z')
    return value.timestamp()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hamming(a, b):
    """Differing bits; each byte one frame has past the other's end counts 8."""
    return sum(bin(x ^ y).count('1') for x, y in zip(a, b)) + 8 * abs(len(a) - len(b))


def header(data):
    """Kind name, station and counter from a capture's header (whatever it holds)."""
    if len(data) < HEADER_LEN:
        return {}
    return {'station_id': int.from_bytes(data[1:3], 'big'), 'counter': int.from_bytes(data[3:HEADER_LEN], 'big')}


def classify(fault, accepted):
    """One rx_faults row (dict) -> dict with 'class' and, for ours, the closest accepted frame.
    accepted: [(received_at, outcome, frame bytes)] within the window."""
    out = dict(fault)
    if fault['kind'] == 'hdr':
        return out | {'class': 'header'}
    data = bytes.fromhex(fault['data'] or '')
    if not data or data[0] not in KINDS:
        return out | {'class': 'foreign/noise'}
    out |= {'class': 'ours', 'frame_kind': KINDS[data[0]], **header(data)}
    if not accepted:
        return out | {'match': None}
    at, outcome, frame = min(accepted, key=lambda a: (abs(a[0] - fault['received_at']), a[0]))
    out['match'] = {'dt_s': round(at - fault['received_at'], 3), 'outcome': outcome, 'length': len(frame),
                    'bits_differ': hamming(data, frame), 'bits': 8 * max(len(data), len(frame)),
                    **({'counter': int.from_bytes(frame[3:HEADER_LEN], 'big')} if len(frame) >= HEADER_LEN else {})}
    return out


def load(db, since=0.0, window_s=WINDOW_S):
    cols = ('id', 'station', 'received_at', 'kind', 'length', 'rssi_dbm', 'snr_db', 'data')
    faults = [dict(zip(cols, r)) for r in db.execute(
        f'SELECT {",".join(cols)} FROM rx_faults WHERE received_at>=? ORDER BY received_at,id', (since,))]
    marks = ','.join('?' * len(ACCEPTED))
    rows = []
    for f in faults:
        accepted = [(t, o, bytes.fromhex(h)) for t, o, h in db.execute(
            f'SELECT received_at,outcome,frame_hex FROM radio_events WHERE station=? AND received_at>=? '
            f'AND received_at<=? AND outcome IN ({marks}) AND frame_hex IS NOT NULL',
            (f['station'], f['received_at'] - window_s, f['received_at'] + window_s, *ACCEPTED))]
        rows.append(classify(f, accepted))
    return rows


def summarize(rows):
    by = lambda c: [r for r in rows if r['class'] == c]
    ours = by('ours')
    matched = [r for r in ours if r.get('match')]
    rssi = [r['rssi_dbm'] for r in rows if r['rssi_dbm'] is not None]
    return {'total': len(rows), 'crc': sum(r['kind'] == 'crc' for r in rows), 'hdr': len(by('header')),
            'ours': len(ours), 'ours_matched': len(matched), 'foreign_or_noise': len(by('foreign/noise')),
            'median_bits_differ': statistics.median(r['match']['bits_differ'] for r in matched) if matched else None,
            'rssi_dbm_min': min(rssi, default=None), 'rssi_dbm_max': max(rssi, default=None),
            'first': iso(rows[0]['received_at']) if rows else None, 'last': iso(rows[-1]['received_at']) if rows else None}


def detail(r):
    head = f"{iso(r['received_at'])}  {r['kind']:3}  rssi={r['rssi_dbm']} dBm"
    if r['kind'] == 'hdr':
        return head + '  header CRC failed (no payload)'
    head += f"  snr={r['snr_db']} dB  len={r['length']}  {r['class']}"
    if r['class'] == 'ours':
        head += f"  {r['frame_kind']}" + (f" station={r['station_id']} counter={r['counter']}" if 'counter' in r else '')
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
             f"CRC captures: {s['ours']} look like ours ({s['ours_matched']} with an accepted frame within "
             f"+-{WINDOW_S} s, median {s['median_bits_differ']} bits differ), {s['foreign_or_noise']} foreign/noise",
             f"RSSI {s['rssi_dbm_min']} .. {s['rssi_dbm_max']} dBm", '']
    return '\n'.join(lines + [detail(r) for r in rows])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', type=Path, default=Path('run-hw/observations.sqlite3'))
    ap.add_argument('--since', help='UTC, e.g. 2026-10-15T00:00:00Z (default: everything)')
    ap.add_argument('--json', action='store_true', help='one JSON object: summary and rows')
    args = ap.parse_args(argv)
    if not args.db.exists():
        ap.error(f'no database at {args.db}')
    db = open_read_only(args.db)
    try:
        rows = load(db, utc(args.since) if args.since else 0.0)
    finally:
        db.close()
    print(json.dumps({'summary': summarize(rows), 'rows': rows}, indent=2) if args.json else report(rows))


if __name__ == '__main__':
    main()
