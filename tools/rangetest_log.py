"""Log a firmware/rangetest board's console: both link directions, settings, spot marks.

    .venv/bin/python tools/rangetest_log.py <ST-LINK serial, /dev/... path or COMn> evidence/<run>/rangetest.csv

Give the board's ST-LINK serial number: port names change with the USB socket. The logger
reopens the port after a USB dropout and records the gap as a 'usb' row.

Writes one CSV row per console event and prints a short summary line every 10 s, but only
when something changed (fewer packets, median RSSI moved >= 4 dB, settings, a mark) or as a
2-minute heartbeat, so a live view stays readable. "up" is what this board heard from the
other; "down" is what the other board reported hearing of this board's previous packet.
"""
import argparse
import csv
import re
import statistics
import sys
import time
from datetime import datetime, timezone

RX = re.compile(r'#rt rx (\w+) seq=(\d+) rssi=(-?\d+) snr=(-?\d+) peer_rssi=(-?\d+) peer_snr=(-?\d+) '
                r'sf=(\d+) pwr=(-?\d+)(?: peer_sf=(\d+) peer_pwr=(-?\d+))?')
CFG = re.compile(r'#rt cfg sf=(\d+) pwr=(-?\d+) (\w+)')
PROPOSE = re.compile(r'#rt propose sf=(\d+) pwr=(-?\d+)')
MARK = re.compile(r'#rt mark (\d+)')
MISS = re.compile(r'#rt miss sf=(\d+) pwr=(-?\d+)')
RX_FAIL = re.compile(r'OnRx(Timeout|Error)')  # ST's own log line just before each '#rt miss'
NO_RSSI = -32768
FIELDS = ['utc', 'event', 'sf', 'pwr_dbm', 'up_rssi', 'up_snr', 'down_rssi', 'down_snr', 'peer_sf',
          'peer_pwr_dbm', 'detail']
MISMATCH_RUN = 3  # a handshake legitimately skews one packet; more means the boards disagree


def parse(line):
    """One console line -> CSV row dict, or None if it is not a rangetest line."""
    if m := RX.search(line):
        kind, seq, rssi, snr, prssi, psnr, sf, pwr, peer_sf, peer_pwr = m.groups()
        down = int(prssi) != NO_RSSI
        return {'event': 'rx', 'sf': int(sf), 'pwr_dbm': int(pwr), 'up_rssi': int(rssi), 'up_snr': int(snr),
                'down_rssi': int(prssi) if down else '', 'down_snr': int(psnr) if down else '',
                'peer_sf': int(peer_sf) if peer_sf else '', 'peer_pwr_dbm': int(peer_pwr) if peer_pwr else '',
                'detail': f'{kind} seq={seq}'}
    if m := CFG.search(line):
        return {'event': 'cfg', 'sf': int(m[1]), 'pwr_dbm': int(m[2]), 'detail': m[3]}
    if m := PROPOSE.search(line):
        return {'event': 'propose', 'sf': int(m[1]), 'pwr_dbm': int(m[2])}
    if m := MARK.search(line):
        return {'event': 'mark', 'detail': m[1]}
    if m := MISS.search(line):
        return {'event': 'miss', 'sf': int(m[1]), 'pwr_dbm': int(m[2])}
    if m := RX_FAIL.search(line):
        # timeout: nothing decoded; error: a packet arrived but failed its CRC/header (corrupted)
        return {'event': 'rx_' + m[1].lower()}
    return None


class Summary:
    """10 s windows; report only on change."""

    def __init__(self, out=print):
        self.out, self.rows, self.misses = out, [], 0
        self.last_med, self.last_print, self.start = None, 0.0, time.time()
        self.mismatch_run = 0
        self.crc_errors = 0

    def add(self, row):
        if row['event'] == 'rx':
            self.rows.append(row)
            differs = row['peer_sf'] != '' and (row['peer_sf'], row['peer_pwr_dbm']) != (row['sf'], row['pwr_dbm'])
            self.mismatch_run = self.mismatch_run + 1 if differs else 0
            if self.mismatch_run == MISMATCH_RUN:
                self.out(f"{row['utc'][:8]}  SETTINGS MISMATCH: this board SF{row['sf']}/{row['pwr_dbm']} dBm, "
                         f"other board SF{row['peer_sf']}/{row['peer_pwr_dbm']} dBm")
        elif row['event'] == 'miss':
            self.misses += 1
        elif row['event'] == 'rx_error':
            self.crc_errors += 1
        elif row['event'] == 'cfg':
            self.out(f"{row['utc'][:8]}  settings now SF{row['sf']} / {row['pwr_dbm']} dBm ({row['detail']})")
        elif row['event'] == 'propose':
            self.out(f"{row['utc'][:8]}  button: asking for SF{row['sf']} / {row['pwr_dbm']} dBm")
        elif row['event'] == 'mark':
            self.out(f"{row['utc'][:8]}  MARK {row['detail']}")

    def tick(self, now=None):
        now = now or time.time()
        if now - self.start < 10:
            return
        t = datetime.now(timezone.utc).strftime('%H:%M:%S')
        if self.rows:
            up = [r['up_rssi'] for r in self.rows]
            down = [r['down_rssi'] for r in self.rows if r['down_rssi'] != '']
            med = int(statistics.median(up))
            changed = (len(self.rows) < 7 or self.last_med is None or abs(med - self.last_med) >= 4
                       or now - self.last_print >= 120)
            if changed:
                last = self.rows[-1]
                down_s = f'{int(statistics.median(down))}' if down else 'n/a'
                self.out(f"{t}  SF{last['sf']}/{last['pwr_dbm']}dBm  heard={len(self.rows):2d}  "
                         f"up med={med} dBm (snr {int(statistics.median(r['up_snr'] for r in self.rows)):+d})  "
                         f"down med={down_s} dBm  misses={self.misses} (corrupted={self.crc_errors})")
                self.last_med, self.last_print = med, now
        elif self.last_med is not None or now - self.last_print >= 120:   # report a loss once, then 2-min heartbeat
            self.out(f'{t}  NO LINK  misses={self.misses} (corrupted={self.crc_errors})')
            self.last_med, self.last_print = None, now
        self.rows, self.misses, self.crc_errors, self.start = [], 0, 0, now


def find_port(board):
    """ST-LINK serial number -> current port (a /dev path or Windows COMn is used as given)."""
    from serial.tools import list_ports

    if board.startswith('/dev/') or re.fullmatch(r'(?i)com\d+', board):   # macOS/Linux path, Windows COMn
        return board
    for p in list_ports.comports():
        if p.serial_number == board:
            return p.device
    return None


def main():
    import serial

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('board', help='ST-LINK serial number (preferred) or serial port path')
    ap.add_argument('csv')
    args = ap.parse_args()
    f = open(args.csv, 'a', newline='')
    w = csv.DictWriter(f, FIELDS)
    if f.tell() == 0:
        w.writeheader()
    summary = Summary(lambda s: print(s, flush=True))

    def note(event, detail):
        row = {'utc': datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3], 'event': event, 'detail': detail}
        w.writerow(row)
        f.flush()
        summary.out(f"{row['utc'][:8]}  USB: {detail}")

    while True:
        path = find_port(args.board)
        if path is None:
            time.sleep(0.5)
            continue
        try:
            port = serial.Serial(path, 115200, timeout=0.2)
        except serial.SerialException:
            time.sleep(0.5)
            continue
        note('usb', f'connected on {path}')
        buf = b''
        try:
            while True:
                buf += port.read(4096)
                *lines, buf = buf.split(b'\n')
                for raw in lines:
                    row = parse(raw.decode(errors='replace'))
                    if row:
                        row['utc'] = datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
                        w.writerow(row)
                        summary.add(row)
                f.flush()
                summary.tick()
        except (serial.SerialException, OSError) as exc:
            note('usb', f'disconnected ({type(exc).__name__}); waiting for the board')
            port.close()


if __name__ == '__main__':
    sys.exit(main())
