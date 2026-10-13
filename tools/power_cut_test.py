#!/usr/bin/env python3
"""Real power-cut test for the TX node's flash state (failure-modes.md gap G7).

Each cycle: wait for the TX board to boot, read its status, start TEST-FLASH-STORM (continuous
journal and counter writes), wait a random time, then cut the board's USB power with uhubctl
(per-port power switching) and restore it. Checked on every boot:

  I3  the transmission counter never goes back: next counter > every counter the storm printed
  I4  the boot epoch strictly increases
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


def fields(line):
    return dict(f.split('=', 1) for f in line.split() if '=' in f)


def read_status(device, timeout=15):
    """Open the TX console, ask STATUS, return (boot lines, status fields)."""
    lines, status = [], None
    with serial.Serial(device, 115200, timeout=0.3) as p:
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


def storm_then_cut(device, hub, port, run_s):
    """Start the storm, collect its progress lines, cut power at the deadline."""
    seen = []
    with serial.Serial(device, 115200, timeout=0.05) as p:
        p.write(b'TEST-FLASH-STORM\n')
        end = time.monotonic() + run_s
        while time.monotonic() < end:
            line = p.readline().decode('ascii', 'replace').strip()
            if line:
                seen.append(line)
        power(hub, port, 'off')
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hub', required=True)
    ap.add_argument('--port', type=int, required=True)
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
    rng = random.Random(args.seed)

    if args.check:
        device = find_port(args.serial_number, 5)
        print('before:', device)
        power(args.hub, args.port, 'off')
        time.sleep(args.off)
        gone = find_port(args.serial_number, 1) is None
        power(args.hub, args.port, 'on')
        device = find_port(args.serial_number, 20)
        _, status = read_status(device) if device else ([], None)
        reset = None
        for line in _:
            if line.startswith('#boot'):
                reset = fields(line).get('reset')
        print(f'enumeration removed while off: {gone}; boot reset cause: {reset}; status: {bool(status)}')
        print('PASS: hub cuts power' if gone and reset == 'power' else
              'FAIL: hub does not cut VBUS on this port (reset cause must be "power")')
        return

    if not args.output:
        ap.error('--output is required for a test run')
    args.output.mkdir(parents=True, exist_ok=False)
    log = (args.output/'cycles.jsonl').open('w', buffering=1)
    started = time.time()
    failures, last_epoch, max_ctr_used = [], None, 0
    totals = {'cycles': 0, 'boots_ok': 0, 'burned_max': 0, 'ecc_boot_events': 0, 'scrubbed': 0}

    for cycle in range(args.cycles + 1):
        device = find_port(args.serial_number, 30)
        if not device:
            failures.append({'cycle': cycle, 'error': 'board did not enumerate'})
            power(args.hub, args.port, 'on')
            continue
        boot_lines, status = read_status(device)
        record = {'cycle': cycle, 'boot': boot_lines[-6:], 'status': status}
        if not status:
            failures.append({'cycle': cycle, 'error': 'no status after boot'})
        else:
            totals['boots_ok'] += 1
            epoch, ctr = int(status['epoch']), int(status['ctr'])
            if status.get('kat') != 'pass':
                failures.append({'cycle': cycle, 'error': 'self-test failed'})
            if last_epoch is not None and epoch <= last_epoch:
                failures.append({'cycle': cycle, 'error': f'epoch did not increase ({last_epoch} -> {epoch})'})
            if ctr <= max_ctr_used:
                failures.append({'cycle': cycle, 'error': f'counter went back ({max_ctr_used} -> {ctr})'})
            last_epoch = epoch
            totals['burned_max'] = max(totals['burned_max'], int(status.get('burned', 0)))
            totals['ecc_boot_events'] += int(int(status.get('ecc', 0)) > 0)
            for line in boot_lines:
                m = re.search(r'#storm-scrub dropped=(\d+)', line)
                if m:
                    totals['scrubbed'] += int(m[1])
            max_ctr_used = max(max_ctr_used, ctr - 1)
        if cycle == args.cycles:
            log.write(json.dumps(record) + '\n')
            break
        run_s = rng.uniform(args.min_run, args.max_run)
        storm_lines = storm_then_cut(device, args.hub, args.port, run_s)
        for line in storm_lines:
            m = re.search(r'ctr=(\d+)', line)
            if m:
                max_ctr_used = max(max_ctr_used, int(m[1]) - 1)
        record.update(run_s=round(run_s, 3), storm=storm_lines[-3:], max_ctr_used=max_ctr_used)
        log.write(json.dumps(record) + '\n')
        time.sleep(args.off)
        power(args.hub, args.port, 'on')
        totals['cycles'] += 1
        print(f'cycle {cycle + 1}/{args.cycles} cut after {run_s:.2f}s; epoch={status and status["epoch"]} '
              f'failures={len(failures)}', flush=True)

    db = sqlite3.connect(args.gateway_db)
    storm_rows = db.execute("SELECT count(*) FROM observations WHERE session='4294967295'").fetchone()[0]
    rejections = db.execute('SELECT count(*) FROM rejections WHERE received_at>=?', (started,)).fetchone()[0]
    if storm_rows:
        failures.append({'error': f'{storm_rows} storm records reached the gateway'})
    summary = {'started': started, 'finished': time.time(), 'seed': args.seed, 'hub': args.hub, 'port': args.port,
               'totals': totals, 'storm_rows_at_gateway': storm_rows, 'gateway_rejections': rejections,
               'failures': failures, 'pass': not failures}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if not failures else 1)


if __name__ == '__main__':
    main()
