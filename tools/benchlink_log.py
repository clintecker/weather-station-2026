"""Log the bench telemetry link (firmware/benchlink) from the RX board's console to a CSV.

    .venv/bin/python tools/benchlink_log.py --serial-number <RX ST-LINK serial> --out <file.csv>
        [--r-iset 1000] [--k-iset 400] [--iset-gain 0.990099] [--r-load 100]
        [--model hardware/bench-breadboard-r0/source/wiring.toml] [--preflight <run notes.md>]

Each "#bl ... hex=" line from the RX is decoded (layout: firmware/benchlink/App/bl_pkt.h), checked
(magic, version, CRC) and appended as one CSV row, synced to disk. Missing sequence numbers are counted.
Before the first row, prepare_csv() rewrites an older header (keeping a copy), sets aside a file it cannot
use and ends a line cut off by an earlier failed write.

Beside the CSV, <file>-events.csv records what explains a gap (EVENTS below). The logger never exits on
its own: a failed open, a failed read, a failed write and a line it cannot handle are each recorded and
retried, and the alert events also raise a macOS notification.
Derived columns: charge_ma from the bq24074 ISET pin (I = K_ISET * V_ISET / R_ISET, datasheet eq. 3,
--k-iset 400 and --r-iset 1000 ohm, R9 behind the board's 1A jumper; V_ISET = the packet's iset_uv, the
PB1 node, / --iset-gain, the 10 kOhm and 1 MOhm divider of decision record M2), load_ma = OUT / --r-load (100 ohm, the
bench test load; the idle 3.3 V regulator adds about 1 mA that this leaves out), and battery_ma, the
INA228 shunt current with its sign turned once (battery_ma() below): + into the cell. ishunt_ma stays raw
(+ into VIN+). The dashboard uses battery_ma only from its --shunt-from moment, when the cell went
through the shunt. The gain and the sign turn are change A's (packet version 4, BL_VERSION in bl_pkt.h): a
version 3 or older packet (an old capture, an old TX) keeps its own meaning, iset_uv as the ISET pin and
battery_ma empty, and tx_first_packet and tx_boot name the version. Every row records its packet's version
(the version column), so a row's meaning never depends on when it was logged.

The logger_start event records the constants, the hashes of the breadboard model (--model) and of the
build-sheet.md beside its source directory, and the run's preflight status (--preflight, the notes holding
the `toml preflight` block; tools/preflight.py): valid, stale, failing or missing. They go in the event
detail, not the CSV header, because prepare_csv() sets a live CSV aside on a header it does not know
(decision record D6)."""
import argparse
import contextlib
import csv
import dataclasses
import datetime
import importlib.util
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import traceback
from pathlib import Path

import serial
from serial.tools import list_ports

# R9 = 1 kOhm behind the 1A jumper (decision record 1.4): ICHG = KISET 890 A*ohm / 1000 ohm = 0.89 A typ
# (SLUS810 eq. 2). Runs logged with the old default 890 read 12 % high. Confirmed by build-sheet check 2.
# Adopted with change A, read by this workflow from record 7.1 P3; Clint to confirm (design D4).
R_ISET_OHM = 1000.0     # default of --r-iset
K_ISET = 400.0          # V_ISET = I / 400 * R_ISET (eq. 3); default of --k-iset
# The PB1 node over V_ISET: 10 kOhm series at the charger end, 1 MOhm to ground at PB1 (record M2), so
# 1 MOhm / 1.01 MOhm. Nominal until the per-board fit against the battery INA228 (M2); default of --iset-gain.
# Adopted with change A, read by this workflow from record 7.1 P3; Clint to confirm (design D4).
ISET_GAIN = 0.990099
R_LOAD_OHM = 100.0      # the bench test load on OUT; default of --r-load
TOOLS = Path(__file__).resolve().parent
MODEL = TOOLS.parent/'hardware'/'bench-breadboard-r0'/'source'/'wiring.toml'   # default of --model


@dataclasses.dataclass(frozen=True)
class Cal:
    """The constants of the derived currents (--r-iset, --k-iset, --r-load, --iset-gain)."""
    r_iset_ohm: float = R_ISET_OHM
    k_iset: float = K_ISET
    r_load_ohm: float = R_LOAD_OHM
    iset_gain: float = ISET_GAIN   # PB1 node / V_ISET


CAL = Cal()
LINE = re.compile(r'#bl rssi=(-?\d+) snr=(-?\d+) len=(\d+) hex=((?:[0-9a-f]{2})*)')
NOTE = re.compile(r'(#bl (?:boot|rx rearm|rx error|drill)[^\r\n]*|#(?:test-)?fault[ :][^\r\n]*|#error [^\r\n]*)')
HEARTBEAT = re.compile(r'#bl hb ')
SILENCE_S = 30           # no packet for this long (one is due every 5 s): silence_start
ALERT_S = 120            # no packet for this long: an alert
HEARTBEAT_LOST_S = 30    # no line from the RX for this long (its heartbeat is every 10 s): rx_heartbeat_lost
# No line at all for this long: close and reopen the port. Seen 2026-10-29: unplugging the other NUCLEO on
# the same USB hub left this port open but delivering nothing while the RX kept printing; a fresh open
# brought the lines back. A reopen that brings nothing back doubles the wait, up to STALL_MAX_S, and keeps
# the heartbeat clock running, so a hung RX still raises rx_heartbeat_lost.
STALL_S = 25
STALL_MAX_S = 400
REPEAT_S = 300           # a failure that repeats (open, write) is logged again at most this often
HOST_SLEEP_S = 10        # the wall clock ran ahead of the monotonic clock by this much: the Mac slept
NOTIFY_EVERY_S = 300     # at most one notification per event name in this time
# Every event, for the README and the tests. The alert ones also raise a macOS notification.
EVENTS = ('logger_start', 'logger_crash', 'logger_error', 'csv_prepared', 'csv_write_failed', 'csv_write_resumed',
          'host_sleep',
          'rx_absent', 'rx_connected', 'rx_open_failed', 'rx_disconnected', 'rx_port_reopen',
          'rx_heartbeat_lost', 'rx_heartbeat_back', 'rx_note', 'bad_packet', 'tx_first_packet', 'tx_boot',
          'packets_missed', 'tx_tx_timeouts', 'tx_i2c_restarts', 'tx_i2c_unsticks', 'silence_start',
          'silence_end', 'alert')
ALERT_EVENTS = ('alert', 'logger_crash', 'logger_error', 'csv_write_failed', 'rx_absent', 'rx_open_failed',
                'rx_heartbeat_lost')
RESETS = ('unknown', 'power', 'pin', 'brownout', 'software', 'watchdog', 'lowpower', 'option-bytes')
COUNTERS = ('tx_timeouts', 'i2c_restarts', 'i2c_unsticks')
FIELDS = ('vout_uv', 'ishunt_ua', 'iset_uv', 'iset_min_uv', 'iset_max_uv', 'ina_die_mc', 'vcell_uv',
          'soc_mpct', 'crate_mpct_h', 'sht_t_mc', 'sht_rh_mpct', 'vin_uv')
LAYOUT = {1: (11, 60), 2: (12, 64), 3: (12, 78), 4: (12, 78)}   # version: (i32 fields, packet length)
# Version 4 (bl_pkt.h BL_VERSION) is version 3's layout with change A's meaning: iset_uv is the PB1 node
# behind the ISET network (row() divides by --iset-gain) and the shunt sits in the official orientation
# (row() turns it into battery_ma). Version 3 and older keep their own meaning: iset_uv is the ISET pin
# (no gain) and battery_ma stays empty, so an old capture or an old TX is never given change A's numbers.
BL_VERSION = 4
CHANGE_A_VERSION = 4
OLD_MEANING = 'before change A: ISET pin, no battery_ma'
FLAGS = (('ina', 0x01), ('gauge', 0x02), ('sht', 0x04), ('pgood', 0x08), ('chg', 0x10), ('adc', 0x20))
# A clipped ADC reading in the interval (bl_pkt.h BL_F_VIN_CLIP, BL_F_ISET_CLIP; the node's adc_clipped rule,
# spec section 9.5): its columns stay empty, as the node sends INVALID. Not CSV columns of their own.
VIN_CLIP, ISET_CLIP = 0x40, 0x80
COLUMNS = ('utc', 'local', 'rssi', 'snr', 'seq', 'gap', 'uptime_s', *(f for f, _ in FLAGS), 'charge_ma',
           'charge_min_ma', 'charge_max_ma', 'load_ma', 'vout_v', 'vcell_v', 'soc_pct', 'rate_pct_h',
           'temp_c', 'rh_pct', 'ina_die_c', 'ishunt_ma', 'battery_ma', 'samples', 'misses', 'vin_v',
           'reset', 'boots', 'faults', 'fault_pc', *COUNTERS, 'version')
EVENT_COLUMNS = ('utc', 'local', 'event', 'detail')


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def decode(raw):
    """The packet as a dict, or None when the magic, version, length or CRC is wrong."""
    if len(raw) < 4 or raw[:2] != b'WB' or raw[2] not in LAYOUT:
        return None
    nfields, size = LAYOUT[raw[2]]
    if len(raw) != size or struct.unpack_from('<H', raw, size - 2)[0] != crc16(raw[:size - 2]):
        return None
    flags = raw[3]
    seq, uptime = struct.unpack_from('<II', raw, 4)
    values = dict(zip(FIELDS, struct.unpack_from(f'<{nfields}i', raw, 12), strict=False))   # v1 has no vin_uv
    values.setdefault('vin_uv', None)
    samples, misses = raw[12 + 4 * nfields], raw[13 + 4 * nfields]
    p = dict(version=raw[2], flags=flags, seq=seq, uptime_s=uptime, samples=samples, misses=misses, **values)
    if raw[2] >= 3:
        reset, faults, boots, *counters, pc = struct.unpack_from('<BBHHHHI', raw, 62)
        p.update(reset=RESETS[reset] if reset < len(RESETS) else str(reset), faults=faults, boots=boots,
                 fault_pc=f'{pc:08x}' if pc else '', **dict(zip(COUNTERS, counters, strict=True)))
    return p


def battery_ma(ishunt_ma):
    """The battery current, + into the cell, from the INA228's raw shunt current (+ into VIN+). With the
    official orientation (docs/superpowers/specs/2026-10-29-power-telemetry-design.md section 3.1: CELL+
    on VIN+, the charger's BATT socket on VIN-) VIN+ to VIN- is out of the cell, so the sign turns. The only place
    the bench tools turn it."""
    return 0.0 - ishunt_ma   # 0.0 - x, not -x: a zero stays 0.0, not -0.0, in the CSV


def row(p, rssi, snr, gap, cal=CAL):
    change_a = p['version'] >= CHANGE_A_VERSION
    gain = cal.iset_gain if change_a else 1.0   # version 3 and older: iset_uv is the ISET pin itself

    def ma(uv):   # uv is the PB1 node (version 4); V_ISET = uv / iset_gain
        return round(cal.k_iset * (uv / gain) / 1e6 / cal.r_iset_ohm * 1000, 2)
    now = datetime.datetime.now(datetime.timezone.utc)
    r = dict(utc=now.isoformat(timespec='seconds'), local=now.astimezone().strftime('%Y-%m-%d %H:%M:%S'),
             rssi=rssi, snr=snr, seq=p['seq'], gap=gap, uptime_s=p['uptime_s'], version=p['version'],
             samples=p['samples'], misses=p['misses'])
    for name, bit in FLAGS:
        r[name] = int(bool(p['flags'] & bit))
    if r['adc'] and not p['flags'] & ISET_CLIP:
        r.update(charge_ma=ma(p['iset_uv']), charge_min_ma=ma(p['iset_min_uv']), charge_max_ma=ma(p['iset_max_uv']))
    if r['ina']:
        r.update(vout_v=p['vout_uv'] / 1e6, load_ma=round(p['vout_uv'] / 1e6 / cal.r_load_ohm * 1000, 2),
                 ina_die_c=p['ina_die_mc'] / 1e3, ishunt_ma=p['ishunt_ua'] / 1e3)
        if change_a:   # the sign turn is change A's orientation; an older TX's shunt is left raw only
            r['battery_ma'] = battery_ma(p['ishunt_ua'] / 1e3)
    if r['gauge']:
        r.update(vcell_v=p['vcell_uv'] / 1e6, soc_pct=p['soc_mpct'] / 1e3, rate_pct_h=p['crate_mpct_h'] / 1e3)
    if r['adc'] and p['vin_uv'] is not None and not p['flags'] & VIN_CLIP:
        r['vin_v'] = p['vin_uv'] / 1e6
    if r['sht']:
        r.update(temp_c=p['sht_t_mc'] / 1e3, rh_pct=p['sht_rh_mpct'] / 1e3)
    for k in ('reset', 'boots', 'faults', 'fault_pc', *COUNTERS):
        if k in p:
            r[k] = p[k]
    return r


def stamp():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.isoformat(timespec='seconds'), now.astimezone().strftime('%Y-%m-%d %H:%M:%S')


class Events:
    """Appends one row per event to <out>-events.csv, echoes it to stdout and notifies on the alert
    events. Never raises: if the file cannot be written, the event still goes to stdout (launchd's log)
    and a notification says the events file is failing."""

    def __init__(self, path):
        self.path = path
        self.notified = {}   # event name: monotonic time of its last notification

    def __call__(self, event, detail=''):
        utc, local = stamp()
        try:
            if ends_cut_off(self.path):
                with open(self.path, 'a') as f:
                    f.write('\n')
            new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
            with open(self.path, 'a', newline='') as f:
                w = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
                if new:
                    w.writeheader()
                w.writerow(dict(utc=utc, local=local, event=event, detail=detail))
        except OSError as e:
            print(local, 'events file unwritable:', e, flush=True)
            self.notify('events_unwritable', f'events file unwritable: {e}')
        print(local, event, detail, flush=True)
        if event in ALERT_EVENTS:
            self.notify(event, f'{event}: {detail}')

    def notify(self, key, text):
        now = time.monotonic()
        if now - self.notified.get(key, -NOTIFY_EVERY_S) >= NOTIFY_EVERY_S:
            self.notified[key] = now
            notify(text)


def notify(text):
    """A macOS notification; best effort and not waited for (no-op elsewhere, never raises)."""
    if sys.platform != 'darwin':
        return
    text = text.replace('\\', ' ').replace('"', "'")[:200]
    try:
        subprocess.Popen(['osascript', '-e', f'display notification "{text}" with title "Bench link"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def ends_cut_off(path):
    """True when the file is not empty and its last byte is not a newline: a write was cut off."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                return False
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b'\n'
    except FileNotFoundError:
        return False


def prepare_csv(path):
    """Makes `path` ready to append rows with COLUMNS; returns what it did ('' for nothing).
    - An older header (its columns all known) is rewritten to COLUMNS, keeping a copy as
      <path>.before-<n>-columns. A version 4 row without battery_ma gets it from its ishunt_ma (backfill()).
    - A file with columns this logger does not know, or that cannot be rewritten, is moved aside to
      <path>.set-aside-<time> and a new CSV starts.
    - A last line cut off by an earlier failed write is ended, so the next row does not join onto it."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return ''
    done = []
    if ends_cut_off(path):
        with open(path, 'a') as f:
            f.write('\n')
        done.append('ended a cut-off last line')
    try:
        with open(path, newline='') as f:
            header = next(csv.reader(f), [])
        if list(header) == list(COLUMNS):
            return '; '.join(done)
        unknown = sorted(set(header) - set(COLUMNS))
        if unknown:
            raise ValueError(f'columns this logger does not know: {unknown}')
        backup = f'{path}.before-{len(COLUMNS)}-columns'
        shutil.copy2(path, backup)
        with open(backup, newline='') as src, open(path + '.tmp', 'w', newline='') as dst:
            w = csv.DictWriter(dst, fieldnames=COLUMNS)
            w.writeheader()
            for old in csv.DictReader(src):
                old.pop(None, None)   # cells beyond the header
                w.writerow(backfill(old))
        os.replace(path + '.tmp', path)
        done.append(f'older header rewritten, copy at {backup}')
    except (OSError, ValueError, csv.Error) as e:
        aside = f'{path}.set-aside-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}'
        os.replace(path, aside)
        with contextlib.suppress(OSError):
            os.remove(path + '.tmp')
        done.append(f'cannot use it ({e}); moved to {aside}, starting a new CSV')
    return '; '.join(done)


def backfill(old):
    """An older row with its battery_ma filled from its ishunt_ma, through the one sign turn (battery_ma()),
    only when the row says it came from a version 4 or later packet (change A's orientation). A row with no
    version (logged before the column existed), an older version, or a blank or unreadable ishunt_ma is left
    blank. Whether the shunt was in the battery path at that moment is the dashboard's --shunt-from, not this."""
    try:
        change_a = int(old.get('version') or 0) >= CHANGE_A_VERSION
    except ValueError:
        change_a = False
    if change_a and not old.get('battery_ma') and old.get('ishunt_ma'):
        with contextlib.suppress(ValueError):
            old['battery_ma'] = battery_ma(float(old['ishunt_ma']))
    return old


class Watch:
    """Turns packets, RX lines and their absence into events. `now` is the monotonic clock."""

    def __init__(self, events, now):
        self.ev = events
        self.last = None            # the previous packet
        self.last_packet = now      # monotonic time of the previous packet, or of the start
        self.last_hb = None         # of the previous RX line; None while the RX is not connected
        self.silent = False
        self.alerted = False
        self.hb_lost = False

    @staticmethod
    def _version(p):
        v = p.get('version', '?')
        return f'version={v}' + (f' ({OLD_MEANING})' if isinstance(v, int) and v < CHANGE_A_VERSION else '')

    def _since(self):
        return f"last seq={self.last['seq']}" if self.last else 'none since the logger started'

    def packet(self, p, now):
        if self.silent:
            self.ev('silence_end', f'{now - self.last_packet:.0f} s without a packet')
            self.silent = self.alerted = False
        prev = self.last
        if prev is None:
            self.ev('tx_first_packet', f"seq={p['seq']} uptime={p['uptime_s']} s reset={p.get('reset', '?')}"
                    f" boots={p.get('boots', '?')} faults={p.get('faults', '?')} {self._version(p)}")
        elif p['seq'] < prev['seq'] or p.get('boots', 0) != prev.get('boots', 0):
            # A reboot: the counter went back, or (v3) the boot count changed. Not the uptime: it wraps.
            self.ev('tx_boot', f"reset={p.get('reset', '?')} boots={p.get('boots', '?')} faults={p.get('faults', '?')}"
                    f" fault_pc={p.get('fault_pc') or '-'} after seq={prev['seq']} uptime={prev['uptime_s']} s"
                    f" {self._version(p)}")
        else:
            if p['seq'] > prev['seq'] + 1:
                self.ev('packets_missed', f"{p['seq'] - prev['seq'] - 1} between seq {prev['seq']} and {p['seq']}")
            for k in COUNTERS:
                if k in p and k in prev and p[k] > prev[k]:
                    self.ev('tx_' + k, f'{prev[k]} -> {p[k]}')
        self.last, self.last_packet = p, now

    def heartbeat(self, now):
        if self.hb_lost:
            self.ev('rx_heartbeat_back', '')
            self.hb_lost = False
        self.last_hb = now

    def idle(self, now):
        if not self.silent and now - self.last_packet > SILENCE_S:
            self.ev('silence_start', f'no packet for {SILENCE_S} s; {self._since()}')
            self.silent = True
        if self.silent and not self.alerted and now - self.last_packet > ALERT_S:
            self.ev('alert', f'no packet from the TX for {ALERT_S // 60} min; {self._since()}')
            self.alerted = True
        if self.last_hb is not None and not self.hb_lost and now - self.last_hb > HEARTBEAT_LOST_S:
            self.ev('rx_heartbeat_lost', f'no line from the RX for {HEARTBEAT_LOST_S} s with its USB port open')
            self.hb_lost = True


class Repeating:
    """A failure that can repeat every few seconds: the first is logged, then one summary per REPEAT_S."""

    def __init__(self, ev, event):
        self.ev, self.event, self.count, self.logged = ev, event, 0, None

    def __call__(self, detail, now):
        self.count += 1
        if self.logged is None or now - self.logged >= REPEAT_S:
            self.ev(self.event, detail if self.count == 1 else f'{detail} ({self.count} times so far)')
            self.logged = now

    def clear(self):
        n, self.count, self.logged = self.count, 0, None
        return n


def port_for(serial_number):
    for p in list_ports.comports():
        if p.serial_number == serial_number:
            return p.device
    return None


def open_port(dev):
    # exclusive: a second program on the port would take lines from the same buffer (tests/test_link.py)
    return serial.Serial(dev, 115200, timeout=1, exclusive=True)


class Logger:
    """The logging loop. The port lookup, the opener and the clocks are parameters so the tests can run
    it against a scripted port and a fake clock."""

    def __init__(self, serial_number, out, ev, find=port_for, opener=open_port, clock=time.monotonic,
                 wall=time.time, sleep=time.sleep, cal=CAL):
        self.serial_number, self.out, self.ev, self.cal = serial_number, out, ev, cal
        self.find, self.opener, self.clock, self.wall, self.sleep = find, opener, clock, wall, sleep
        self.watch = Watch(ev, clock())
        self.absent = False
        self.stall_s = STALL_S
        self.open_failed = Repeating(ev, 'rx_open_failed')
        self.write_failed = Repeating(ev, 'csv_write_failed')
        self.skew = wall() - clock()
        self.csv = self.writer = None

    def run(self):
        while True:   # bound: none on purpose: logs until stopped
            self.cycle()

    def tick(self):
        """The time now, after checking whether the Mac slept (the monotonic clock stops in sleep)."""
        now = self.clock()
        skew = self.wall() - now
        if skew - self.skew > HOST_SLEEP_S:
            self.ev('host_sleep', f'the Mac was asleep for about {skew - self.skew:.0f} s')
        self.skew = skew
        self.watch.idle(now)
        return now

    def cycle(self):
        """One attempt: find the RX, open it and read until the port fails or stalls."""
        dev = self.find(self.serial_number)
        now = self.tick()
        if not dev:
            if not self.absent:
                self.ev('rx_absent', 'the RX is not on USB; waiting')
                self.absent = True
                self.watch.last_hb = None   # no line is expected from an RX that is not there
            self.sleep(2)
            return
        self.absent = False
        try:
            port = self.opener(dev)
        except (serial.SerialException, OSError) as e:
            self.watch.last_hb = None
            self.open_failed(f'{dev}: {e}', now)
            self.sleep(2)
            return
        failures = self.open_failed.clear()
        with port:
            self.read(port, dev, failures)

    def read(self, port, dev, failures):
        reopen = self.watch.last_hb is not None   # a reopen after a stall keeps the heartbeat clock
        self.ev('rx_connected', dev + (f' after {failures} failed opens' if failures else '')
                + (' (reopened)' if reopen else ''))
        if not reopen:
            self.watch.last_hb = self.clock()      # a booting RX gets HEARTBEAT_LOST_S to speak
        last_line = self.clock()
        try:
            while True:   # bound: none on purpose: until the port fails or stalls
                try:
                    line = port.readline()
                except (serial.SerialException, OSError) as e:
                    self.ev('rx_disconnected', str(e))
                    self.watch.last_hb = None
                    self.sleep(2)
                    return
                now = self.tick()
                if not line:
                    if now - last_line > self.stall_s:
                        self.ev('rx_port_reopen', f'no line for {self.stall_s} s; closing and reopening {dev}')
                        self.stall_s = min(self.stall_s * 2, STALL_MAX_S)
                        return
                    continue
                last_line, self.stall_s = now, STALL_S
                self.line(line, now)
        finally:
            self.close_csv()

    def line(self, line, now):
        try:
            r = handle(line.decode(errors='replace'), now, self.watch, self.ev, self.cal)
        except Exception as e:   # one bad line must never stop the night's log
            self.ev('logger_error', repr(e)[:200])
            return
        if r is not None:
            self.write(r, now)

    def write(self, r, now):
        """Appends one row and syncs it. A failure (a full or missing disk) is logged and retried with the
        next packet, reopening the file; reading goes on meanwhile."""
        try:
            if self.csv is None:
                if ends_cut_off(self.out):
                    with open(self.out, 'a') as f:
                        f.write('\n')
                self.csv = open(self.out, 'a', newline='')   # noqa: SIM115 (kept open between packets)
                self.writer = csv.DictWriter(self.csv, fieldnames=COLUMNS)
                if self.csv.tell() == 0:
                    self.writer.writeheader()
            self.writer.writerow(r)
            self.csv.flush()
            os.fsync(self.csv.fileno())
        except OSError as e:
            self.close_csv()
            self.write_failed(f'{self.out}: {e}', now)
            return
        if self.write_failed.count:
            self.ev('csv_write_resumed', f'writing again after {self.write_failed.clear()} failed rows')

    def close_csv(self):
        if self.csv is not None:
            with contextlib.suppress(OSError):
                self.csv.close()
        self.csv = self.writer = None


def handle(text, now, watch, ev, cal=CAL):
    """One console line: a heartbeat, a note or a packet. Returns the CSV row of a good packet, else None."""
    if HEARTBEAT.search(text):
        watch.heartbeat(now)
        return None
    note = NOTE.search(text)
    if note:
        watch.heartbeat(now)
        ev('rx_note', note.group(1).strip())
        return None
    m = LINE.search(text)
    if not m:
        return None
    watch.heartbeat(now)
    p = decode(bytes.fromhex(m.group(4)))
    if p is None:
        ev('bad_packet', m.group(4)[:24])
        return None
    last = watch.last
    gap = 0 if last is None or p['seq'] <= last['seq'] else p['seq'] - last['seq'] - 1
    watch.packet(p, now)
    return row(p, int(m.group(1)), int(m.group(2)), gap, cal)


def positive(text):
    """argparse type: a finite float above zero (a resistor or a gain)."""
    v = float(text)
    if not 0 < v < float('inf'):
        raise argparse.ArgumentTypeError(f'must be a finite number above zero: {text}')
    return v


def _preflight_module():
    """tools/preflight.py as a module (tools/ is scripts, not a package)."""
    spec = importlib.util.spec_from_file_location('preflight', TOOLS/'preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def provenance(model, notes):
    """The logger_start detail that ties a run to its drawing: the git blob hashes of the model and of
    build-sheet.md beside its source directory, and the preflight status of the run's notes ('missing'
    without notes). Never raises: an unreadable file is logged as such, so the logger still starts."""
    model = Path(model)
    sheet = model.parent.parent/'build-sheet.md'
    try:
        pf = _preflight_module()
    except Exception as e:   # a broken preflight.py must not stop the night's log
        return f'model_hash=? sheet_hash=? preflight=? ({e!r:.120})'
    hashes = []
    for name, path in (('model_hash', model), ('sheet_hash', sheet)):
        try:
            hashes.append(f'{name}={pf.checklist.blob_sha1(path)}')
        except OSError as e:
            hashes.append(f'{name}=unreadable ({path}: {e.strerror})')
    state = 'missing'
    if notes:
        try:
            state = pf.status(Path(notes), model, sheet)[0]
        except Exception as e:   # the status is a record, never a reason not to log
            state = f'failing ({e!r:.120})'
    return f"{' '.join(hashes)} preflight={state}"


def start_detail(cal, model, notes):
    """The logger_start event detail: the constants and provenance()."""
    return (f'pid={os.getpid()} r_iset={cal.r_iset_ohm:g} ohm k_iset={cal.k_iset:g} iset_gain={cal.iset_gain:g}'
            f' r_load={cal.r_load_ohm:g} ohm {provenance(model, notes)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--serial-number', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--r-iset', type=positive, default=R_ISET_OHM,
                    help='bq24074 ISET resistor, ohm (default %(default)s: R9 behind the 1A jumper)')
    ap.add_argument('--k-iset', type=positive, default=K_ISET,
                    help='bq24074 ISET gain, I = K * V_ISET / R_ISET (default %(default)s, SLUS810 eq. 3)')
    ap.add_argument('--iset-gain', type=positive, default=ISET_GAIN,
                    help='the PB1 node over V_ISET (default %(default)s: 1 MOhm / 1.01 MOhm, nominal)')
    ap.add_argument('--r-load', type=positive, default=R_LOAD_OHM,
                    help='the test load on OUT, ohm (default %(default)s)')
    ap.add_argument('--model', default=str(MODEL),
                    help='the breadboard model whose hash is logged (default %(default)s)')
    ap.add_argument('--preflight', metavar='NOTES',
                    help="the run's notes holding the `toml preflight` block (default: none, logged as missing)")
    args = ap.parse_args()
    cal = Cal(args.r_iset, args.k_iset, args.r_load, args.iset_gain)
    ev = Events(os.path.splitext(args.out)[0] + '-events.csv')
    try:
        ev('logger_start', start_detail(cal, args.model, args.preflight))
        try:
            did = prepare_csv(args.out)
        except OSError as e:
            did = ''
            ev('logger_error', f'cannot prepare {args.out}: {e}')
        if did:
            ev('csv_prepared', did)
        Logger(args.serial_number, args.out, ev, cal=cal).run()
    except KeyboardInterrupt:
        return 0
    except BaseException as e:   # launchd restarts the logger; say why it stopped first
        ev('logger_crash', f'{e!r}: ' + ' | '.join(traceback.format_exc().splitlines()[-4:])[:600])
        raise


if __name__ == '__main__':
    sys.exit(main())
