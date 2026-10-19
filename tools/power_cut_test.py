#!/usr/bin/env python3
"""Real power-cut test for the TX node's flash state.

Each cycle: wait for the TX board to boot, read its status, start TEST-FLASH-STORM (continuous
journal and counter writes), wait a random time, then cut the board's USB power with uhubctl
(per-port power switching) and restore it. Checked on every boot:

  --  the transmission counter never goes back: next counter > every counter the storm printed
  --  the boot epoch strictly increases
  --  the self-test passes and the flash store initializes (no hang, no hard fault)

At the end the gateway database is checked for storm records (epoch 4294967295) and
rejections. Evidence goes to a new directory: --output must not exist.

  .venv/bin/python tools/power_cut_test.py --hub 1-1.2.2 --port 3 \
      --serial-number 003B00194142500E20353451 --cycles 200 --output evidence/power-cut-YYYY-MM-DD

Needs: uhubctl, and a hub that really switches VBUS per port (verify with --check first).
"""
import argparse
import json
import random
import re
import sqlite3
import subprocess
import time
from pathlib import Path

import serial

BAUD = 115200   # the boards' ST-LINK virtual COM port (ws0/link.py BAUD)
from serial.tools import list_ports


def find_port(serial_number, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for info in list_ports.comports():
            if (info.serial_number or '').upper() == serial_number.upper():
                return info.device
        time.sleep(0.2)
    return None


def power(hub, port, state):
    subprocess.run(['uhubctl', '-l', hub, '-p', str(port), '-a', state, '-r', '1'],
                   check=True, capture_output=True, text=True)


def nrst(stlink_serial):
    """Assert the MCU reset line through the ST-LINK (no power removal). A reset during a flash
    program/erase aborts it and can leave the double-word torn, like a power cut (RM0453)."""
    subprocess.run(['openocd', '-d0', '-f', 'interface/stlink.cfg', '-c', f'adapter serial {stlink_serial}',
                    '-f', 'target/stm32wlx.cfg', '-c', 'reset_config srst_only srst_nogate',
                    '-c', 'init', '-c', 'reset run', '-c', 'shutdown'],
                   check=True, capture_output=True, text=True, timeout=30)


def fields(line):
    return dict(f.split('=', 1) for f in line.split() if '=' in f)


def read_status(device, timeout=15):
    """Open the TX console, ask STATUS, return (boot lines, status fields)."""
    lines, status = [], None
    with serial.Serial(device, BAUD, timeout=0.3, exclusive=True) as p:
        end = time.monotonic() + timeout
        asked = False
        while time.monotonic() < end and status is None:
            line = p.readline().decode('ascii', 'replace').strip()
            if line:
                lines.append(line)
                if line.startswith('#status role=tx'):
                    status = fields(line)
            if not asked and time.monotonic() > end - timeout + 1.0:
                p.write(b'STATUS\n')
                asked = True
    return lines, status


def storm_then_cut(device, cut, run_s):
    """Start the storm, collect its progress lines, cut power at the deadline."""
    seen = []
    with serial.Serial(device, BAUD, timeout=0.05, exclusive=True) as p:
        p.write(b'TEST-FLASH-STORM\n')
        end = time.monotonic() + run_s
        while time.monotonic() < end:
            line = p.readline().decode('ascii', 'replace').strip()
            if line:
                seen.append(line)
        cut()
    return seen


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--method', choices=['power', 'reset'], default='power',
                    help='power: uhubctl removes VBUS (true power cut); reset: ST-LINK NRST during writes')
    ap.add_argument('--hub', help='uhubctl hub location (method power)')
    ap.add_argument('--port', type=int, help='uhubctl port (method power)')
    ap.add_argument('--serial-number', required=True, help='TX board ST-LINK serial')
    ap.add_argument('--cycles', type=int, default=200)
    ap.add_argument('--min-run', type=float, default=0.3)
    ap.add_argument('--max-run', type=float, default=4.0)
    ap.add_argument('--off', type=float, default=2.0, help='seconds without power')
    ap.add_argument('--seed', type=int, default=2026)
    ap.add_argument('--gateway-db', type=Path, default=Path('run-hw/observations.sqlite3'))
    ap.add_argument('--output', type=Path)
    ap.add_argument('--check', action='store_true', help='one cut: verify the hub really removes power')
    args = ap.parse_args()
    if args.method == 'power' and (not args.hub or not args.port):
        ap.error('--method power needs --hub and --port')
    if args.check and args.method != 'power':
        ap.error('--check tests a hub power cut: use it with --method power')
    if not args.check and not args.output:
        ap.error('--output is required for a test run')
    return args


def hub_check(args):
    """One cut: the board must disappear from USB while off and boot with reset cause 'power'."""
    device = find_port(args.serial_number, 5)
    print('before:', device)
    power(args.hub, args.port, 'off')
    time.sleep(args.off)
    gone = find_port(args.serial_number, 1) is None
    power(args.hub, args.port, 'on')
    device = find_port(args.serial_number, 20)
    _, status = read_status(device) if device else ([], None)
    reset = status.get('reset') if status else None
    print(f'enumeration removed while off: {gone}; boot reset cause: {reset}; status: {bool(status)}')
    print('PASS: hub cuts power' if gone and reset == 'power' else
          'FAIL: hub does not cut VBUS on this port (reset cause must be "power")')


class Invariants:
    """The checks across boots (counter never goes back, epoch increases, self-test, reset cause) and the run totals."""
    def __init__(self, expected_reset):
        self.expected_reset = expected_reset
        self.failures, self.last_epoch, self.max_ctr_used = [], None, 0
        self.totals = {'cycles': 0, 'boots_ok': 0, 'burned_max': 0, 'ecc_boot_events': 0, 'scrubbed': 0}

    def fail(self, cycle, error):
        self.failures.append({'cycle': cycle, 'error': error})

    def boot(self, cycle, boot_lines, status):
        """One boot's status (None: the board printed none)."""
        if not status:
            self.fail(cycle, 'no status after boot')
            return
        self.totals['boots_ok'] += 1
        epoch, ctr = int(status['epoch']), int(status['ctr'])
        if cycle > 0 and status.get('reset') != self.expected_reset:
            self.fail(cycle, f"reset cause {status.get('reset')!r}, expected {self.expected_reset!r}")
        if status.get('kat') != 'pass':
            self.fail(cycle, 'self-test failed')
        if self.last_epoch is not None and epoch <= self.last_epoch:
            self.fail(cycle, f'epoch did not increase ({self.last_epoch} -> {epoch})')
        if ctr <= self.max_ctr_used:
            self.fail(cycle, f'counter went back ({self.max_ctr_used} -> {ctr})')
        self.last_epoch = epoch
        self.totals['burned_max'] = max(self.totals['burned_max'], int(status.get('burned', 0)))
        self.totals['ecc_boot_events'] += int(int(status.get('ecc', 0)) > 0)
        self.totals['scrubbed'] += sum(int(m[1]) for m in (re.search(r'#storm-scrub dropped=(\d+)', line)
                                                           for line in boot_lines) if m)
        self.used_counter(ctr)

    def used_counter(self, next_ctr):
        """The board's next counter is next_ctr: everything below it may have been used."""
        self.max_ctr_used = max(self.max_ctr_used, next_ctr - 1)

    def storm(self, lines):
        for line in lines:
            m = re.search(r'ctr=(\d+)', line)
            if m:
                self.used_counter(int(m[1]))


def gateway_check(path, started):
    """(storm records stored, rejections since the start): storm records must never be sent."""
    db = sqlite3.connect(path)
    storm_rows = db.execute("SELECT count(*) FROM observations WHERE session='4294967295'").fetchone()[0]
    rejections = db.execute('SELECT count(*) FROM rejections WHERE received_at>=?', (started,)).fetchone()[0]
    return storm_rows, rejections


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    cut = (lambda: power(args.hub, args.port, 'off')) if args.method == 'power' else (lambda: nrst(args.serial_number))
    if args.check:
        hub_check(args)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    log = (args.output/'cycles.jsonl').open('w', buffering=1)
    started = time.time()
    run = Invariants('power' if args.method == 'power' else 'pin')

    for cycle in range(args.cycles + 1):
        device = find_port(args.serial_number, 30)
        if not device:
            run.fail(cycle, 'board did not enumerate')
            if args.method == 'power':   # with --method reset there is no hub to switch back on
                power(args.hub, args.port, 'on')
            continue
        boot_lines, status = read_status(device)
        record = {'cycle': cycle, 'boot': boot_lines[-6:], 'status': status}
        run.boot(cycle, boot_lines, status)
        if cycle == args.cycles:
            log.write(json.dumps(record) + '\n')
            break
        run_s = rng.uniform(args.min_run, args.max_run)
        storm_lines = storm_then_cut(device, cut, run_s)
        run.storm(storm_lines)
        record.update(run_s=round(run_s, 3), storm=storm_lines[-3:], max_ctr_used=run.max_ctr_used)
        log.write(json.dumps(record) + '\n')
        if args.method == 'power':
            time.sleep(args.off)
            power(args.hub, args.port, 'on')
        run.totals['cycles'] += 1
        print(f'cycle {cycle + 1}/{args.cycles} cut after {run_s:.2f}s; epoch={status and status["epoch"]} '
              f'failures={len(run.failures)}', flush=True)

    storm_rows, rejections = gateway_check(args.gateway_db, started)
    if storm_rows:
        run.failures.append({'error': f'{storm_rows} storm records reached the gateway'})
    summary = {'started': started, 'finished': time.time(), 'seed': args.seed, 'method': args.method,
               'hub': args.hub, 'port': args.port,
               'totals': run.totals, 'storm_rows_at_gateway': storm_rows, 'gateway_rejections': rejections,
               'failures': run.failures, 'pass': not run.failures}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if not run.failures else 1)


if __name__ == '__main__':
    main()
