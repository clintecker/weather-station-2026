#!/usr/bin/env python3
"""Recompute every number cited in README.md from the CSVs in this folder (stdlib only).

    python3 evidence/rangetest-office-2026-10-13/analyze.py

Definitions (also in README.md):
- event: one RX receive window, i.e. one `rx` row (round trip succeeded) or one `miss` row
  (nothing valid heard; failure in either direction). From 16:46:39 each `miss` is preceded
  by an `rx_timeout` or `rx_error` annotation row; those are NOT counted as extra events.
- segment: a maximal run of consecutive events with the same RX setting (sf, pwr_dbm),
  additionally cut at every `mark` row and every `usb` row. A segment is therefore
  "switch-to-switch" (or switch-to-mark) at one spot/setting, with no hand-picked window.
- loss streak: a maximal run of consecutive `miss` events inside one segment.
- signal estimate: RSSI minus the noise share implied by SNR,
  S = RSSI - 10*log10(1 + 10**(-SNR/10)) dBm.
Times are UTC (HH:MM:SS.mmm strings compare correctly within the day).
"""
import csv
import math
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
WALK_START = '16:43:37'      # logger restart on the laptop at the start of the walk
RX_RESTART = '16:54:35.745'  # first RX USB dropout; RX fell back to SF7/0 dBm


def load(name):
    with open(HERE / name, newline='') as f:
        return list(csv.DictReader(f))


def med(values):
    values = [v for v in values if v is not None]
    return st.median(values) if values else None


def num(v):
    return int(v) if v not in ('', None) else None


def signal(rssi, snr):
    return rssi - 10 * math.log10(1 + 10 ** (-snr / 10))


def segments(rows):
    """Split rx/miss events into segments (same setting; cut at mark and usb rows)."""
    segs, cur, key = [], [], None
    for r in rows:
        if r['event'] in ('mark', 'usb'):
            if cur:
                segs.append(cur)
            cur, key = [], None
            continue
        if r['event'] not in ('rx', 'miss'):
            continue
        k = (r['sf'], r['pwr_dbm'])
        if k != key and cur:
            segs.append(cur)
            cur = []
        key = k
        cur.append(r)
    if cur:
        segs.append(cur)
    return segs


def describe(seg):
    rx = [r for r in seg if r['event'] == 'rx']
    up_rssi = med(num(r['up_rssi']) for r in rx)
    dn_rssi = med(num(r['down_rssi']) for r in rx)
    up_snr = med(num(r['up_snr']) for r in rx)
    dn_snr = med(num(r['down_snr']) for r in rx)
    sig = med(signal(int(r['up_rssi']), int(r['up_snr'])) for r in rx)
    return (f"{seg[0]['utc']}-{seg[-1]['utc']}  SF{seg[0]['sf']}/{seg[0]['pwr_dbm']:>2} dBm  "
            f"round trips {len(rx)}/{len(seg)} ({100 * len(rx) / len(seg):.0f} %)  "
            f"RSSI up/down {up_rssi}/{dn_rssi}  SNR up/down {up_snr}/{dn_snr}  "
            f"signal est. {sig:.1f} dBm" if rx else
            f"{seg[0]['utc']}-{seg[-1]['utc']}  SF{seg[0]['sf']}/{seg[0]['pwr_dbm']} dBm  round trips 0/{len(seg)}")


def main():
    v1 = load('rangetest-v1-desk.csv')
    v2 = load('rangetest.csv')

    print('== Files')
    for name, rows in (('rangetest-v1-desk.csv', v1), ('rangetest.csv', v2)):
        print(f'{name}: {rows[0]["utc"]} to {rows[-1]["utc"]}, {len(rows)} rows')
    timeouts = [r for r in v2 if r['event'] == 'rx_timeout']
    errors = [r for r in v2 if r['event'] == 'rx_error']
    print(f'first rx_timeout/rx_error annotation: {min(r["utc"] for r in timeouts + errors)}')

    print('\n== usb rows (a "disconnected" row followed by "connected" = USB dropout; '
          'a lone "connected" = logger (re)start)')
    for r in v2:
        if r['event'] == 'usb':
            print(f'  {r["utc"]}  {r["detail"]}')

    print('\n== Packet rate (median spacing of consecutive rx rows, same setting, < 3 s apart)')
    for sf in ('7', '12'):
        gaps = []
        rx = [r for r in v1 + v2 if r['event'] == 'rx']
        for a, b in zip(rx, rx[1:]):
            if a['sf'] == b['sf'] == sf:
                ta = sum(float(x) * m for x, m in zip(a['utc'].split(':'), (3600, 60, 1)))
                tb = sum(float(x) * m for x, m in zip(b['utc'].split(':'), (3600, 60, 1)))
                if 0 < tb - ta < 3:
                    gaps.append(tb - ta)
        g = st.median(gaps)
        print(f'  SF{sf}: {g:.2f} s -> {1 / g:.2f} round trips per second')

    print('\n== Sequence resets (ping seq= goes down; the TX restarted or the RX re-adopted)')
    for name, rows in (('v1', v1), ('v2', v2)):
        last = None
        for r in rows:
            if r['event'] != 'rx':
                continue
            seq = int(r['detail'].split('=')[1])
            if last is not None and seq < last[1]:
                print(f'  {name} {r["utc"]}: seq {last[1]} (last heard {last[0]}) -> {seq}')
            last = (r['utc'], seq)

    walk = [r for r in v2 if r['utc'] >= WALK_START]
    segs = segments(walk)
    print(f'\n== Walk segments ({WALK_START} onwards; same setting, cut at marks/usb rows)')
    for s in segs:
        print('  ' + describe(s))

    print('\n== Marks in rangetest.csv during the walk')
    for r in walk:
        if r['event'] == 'mark':
            print(f'  {r["utc"]} mark {r["detail"]}')

    # Farmer's Fridge stop: from the SF7 switch (16:45:05.250) to the logger restart (16:46:39.634).
    # Mark 2 (16:45:46) fell inside the SF10 span, so it is not used as a cut here.
    print("\n== Farmer's Fridge stop, 16:45:05.250 to 16:46:39.634, events grouped by setting")
    ff = [r for r in v2 if '16:45:05.250' <= r['utc'] < '16:46:39.634' and r['event'] in ('rx', 'miss')]
    for key in sorted({(r['sf'], r['pwr_dbm']) for r in ff}, key=lambda k: int(k[0])):
        print('  ' + describe([r for r in ff if (r['sf'], r['pwr_dbm']) == key]))

    print('\n== Last SF12/+22 dBm stretch before the RX restart, 16:54:00 to 16:54:35.745')
    last = [r for r in v2 if '16:54:00' <= r['utc'] < RX_RESTART and r['event'] in ('rx', 'miss')]
    print('  ' + describe(last))
    snrs = [int(r['up_snr']) for r in last if r['event'] == 'rx']
    print(f'  up SNR range {max(snrs)} to {min(snrs)} dB')
    after = [r for r in v2 if r['utc'] > RX_RESTART and r['event'] == 'rx']
    print(f'  after the RX restart: first decoded packet {after[0]["utc"]} at SF{after[0]["sf"]}/'
          f'{after[0]["pwr_dbm"]} dBm; misses in between: '
          f'{sum(1 for r in v2 if RX_RESTART < r["utc"] < after[0]["utc"] and r["event"] == "miss")}')

    before = [s for s in segs if s[-1]['utc'] < RX_RESTART]
    print(f'\n== SF12 next-round-trip success by last up SNR (walk, before RX restart {RX_RESTART})')
    buckets = {}
    n = 0
    for s in before:
        if s[0]['sf'] != '12':
            continue
        for a, b in zip(s, s[1:]):
            if a['event'] != 'rx':
                continue
            n += 1
            snr = int(a['up_snr'])
            k = '+4..+7' if snr >= 4 else '0..+3' if snr >= 0 else '-1..-12' if snr >= -12 else '< -12'
            ok, tot = buckets.get(k, (0, 0))
            buckets[k] = (ok + (b['event'] == 'rx'), tot + 1)
    events12 = sum(len(s) for s in before if s[0]['sf'] == '12')
    print(f'  SF12 events: {events12}; rx events followed by another event in the same segment: {n}')
    for k in ('+4..+7', '0..+3', '-1..-12', '< -12'):
        ok, tot = buckets.get(k, (0, 0))
        if tot:
            print(f'  last up SNR {k:>8}: next succeeded {ok}/{tot} ({100 * ok / tot:.0f} %)')

    print(f'\n== Loss streaks (walk, before RX restart; within segments)')
    streaks, events, misses = [], 0, 0
    for s in before:
        run = 0
        for r in s:
            events += 1
            if r['event'] == 'miss':
                misses += 1
                run += 1
            elif run:
                streaks.append(run)
                run = 0
        if run:
            streaks.append(run)
    p = misses / events
    long = sum(x >= 2 for x in streaks)
    print(f'  events {events}, misses {misses}, loss rate p = {p:.2f}')
    print(f'  streaks {len(streaks)}, of which 2+ long: {long} ({100 * long / len(streaks):.0f} %); '
          f'expected if independent: p = {100 * p:.0f} %')

    print('\n== Noise floor: median RSSI of rx rows with SNR <= -5 dB (signal below noise), walk')
    up = [int(r['up_rssi']) for r in walk if r['event'] == 'rx' and int(r['up_snr']) <= -5]
    dn = [int(r['down_rssi']) for r in walk if r['event'] == 'rx' and r['down_snr'] != ''
          and int(r['down_snr']) <= -5]
    print(f'  RX (up): {med(up)} dBm over {len(up)} packets; TX (down): {med(dn)} dBm over {len(dn)} packets')
    print(f'  thermal floor at 500 kHz: {-174 + 10 * math.log10(500e3):.1f} dBm; plus 6 dB NF: '
          f'{-174 + 10 * math.log10(500e3) + 6:.1f} dBm')

    print('\n== Windows around single events')
    for lo, hi in (('16:54:00', '16:54:12.5'), ('16:58:39', '16:58:53')):
        ev = [r for r in v2 if lo <= r['utc'] < hi and r['event'] in ('rx', 'rx_timeout', 'rx_error')]
        print(f'  {lo}-{hi}:')
        for r in ev:
            extra = f' up RSSI {r["up_rssi"]} SNR {r["up_snr"]}' if r['event'] == 'rx' else ''
            print(f'    {r["utc"]} {r["event"]}{extra}')

    late = [r for r in v2 if r['utc'] >= '16:46:39']
    print(f'\n== Loss causes from 16:46:39 to end: rx_timeout {sum(r["event"] == "rx_timeout" for r in late)}, '
          f'rx_error {sum(r["event"] == "rx_error" for r in late)}')

    print('\n== Strong-signal SNR ceiling (rx with up RSSI > -40 dBm): median up SNR')
    for sf in ('7', '12'):
        vals = [int(r['up_snr']) for r in v2 if r['event'] == 'rx' and r['sf'] == sf and int(r['up_rssi']) > -40]
        print(f'  SF{sf}: median {med(vals)}, max {max(vals)} over {len(vals)} packets')


if __name__ == '__main__':
    main()
