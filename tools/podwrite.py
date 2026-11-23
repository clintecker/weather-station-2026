"""Write a pod's ID record through the TX's PODWRITE console command, and keep the serial ledger.

    .venv/bin/python tools/podwrite.py 003B00194142500E20353451 TH
    .venv/bin/python tools/podwrite.py /dev/cu.usbmodem1103 UV --operator clint

The pod sits on its TX port (TH on S1, UV on S2, BARO on S3) with its JP1 shunt off. The tool draws a new
serial (top byte 01, 56 random bits), writes a "sent" row to the ledger, sends
`PODWRITE <port> <type> <serial> WRITE-POD-RECORD`, waits for the #podwrite reply and writes the outcome
row. A serial is never drawn twice: one already in the ledger is drawn again, failed writes included.
Put the JP1 shunt back on afterwards. The station reads the record at the next probe
(MODULES shows source=record).
"""
import argparse
import csv
import datetime
import re
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT/'hardware'/'pods-r1'/'serial-ledger.csv'
CONFIRM = 'WRITE-POD-RECORD'
HW_REV = 1                              # hardware/pods-r1 (POD_WRITE_HW_REV)
# The pod: its WSMP port on the TX (what #ident port= prints) and its module type.
PODS = {'TH': (1, 1), 'BARO': (2, 2), 'UV': (3, 3)}
FIELDS = ['date', 'serial', 'pod', 'port', 'type', 'hw_rev', 'outcome', 'bind', 'crc', 'record', 'operator']
SERIAL_NS = 0x01
LOW_BITS = 56
REPLY = re.compile(r'#podwrite (ok|FAIL) (.*)$')


def read_ledger(path=LEDGER):
    if not path.exists():
        return []
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def append_row(row, path=LEDGER):
    new = not path.exists()
    with path.open('a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, '') for k in FIELDS})


def draw_serial(used, rand=secrets.randbits):
    """A record serial (section 6.7): 0x01, then 56 random bits that are neither 0 nor all ones,
    and not in used (a set of 16-hex strings)."""
    for _ in range(64):   # 56 random bits: a repeat or a bad draw is all but impossible
        low = rand(LOW_BITS)
        text = f'{(SERIAL_NS << LOW_BITS) | low:016x}'
        if 0 < low < (1 << LOW_BITS) - 1 and text not in used:
            return text
    raise RuntimeError('no fresh serial in 64 draws (is the random source broken?)')


def command(pod, serial):
    port, mtype = PODS[pod]
    return f'PODWRITE {port} {mtype} {serial} {CONFIRM}'


def parse_reply(line):
    """A #podwrite ok/FAIL line as a dict (outcome, and the key=value fields), or None."""
    m = REPLY.search(line)
    if not m:
        return None
    out = {'outcome': 'ok' if m.group(1) == 'ok' else ''}
    rest = m.group(2)
    if 'why=' in rest:                              # the why text can hold spaces: it runs to the end
        rest, why = rest.split('why=', 1)
        out['outcome'] = why.split(' ')[0]
    for part in rest.split():
        if '=' in part:
            k, v = part.split('=', 1)
            out[k] = v
    return out


def converse(port, line, seconds, log=print):
    """Send the line and return the parsed #podwrite reply, or {'outcome': <why>} for an #error line
    or no reply in time."""
    port.reset_input_buffer()
    port.write(line.encode('ascii') + b'\n')
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        text = port.readline().decode('ascii', 'replace').rstrip()
        if not text:
            continue
        log(text)
        if text.startswith('#error'):
            return {'outcome': 'refused'}
        reply = parse_reply(text)
        if reply:
            return reply
    return {'outcome': 'no-reply'}


def write_pod(port, pod, operator='', ledger=LEDGER, seconds=15.0, log=print, now=None):
    used = {r['serial'] for r in read_ledger(ledger)}
    serial = draw_serial(used)
    num, mtype = PODS[pod]
    date = (now or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    base = {'date': date, 'serial': serial, 'pod': pod, 'port': num, 'type': mtype, 'hw_rev': HW_REV,
            'operator': operator}
    append_row({**base, 'outcome': 'sent'}, ledger)   # before the line goes out: the serial is spent
    reply = converse(port, command(pod, serial), seconds, log)
    if reply['outcome'] == 'ok' and reply.get('serial') != serial:
        reply = {'outcome': 'serial-mismatch'}
    append_row({**base, **{k: reply.get(k, '') for k in ('outcome', 'bind', 'crc', 'record')}}, ledger)
    return serial, reply


def open_port(target):
    import serial
    from serial.tools import list_ports
    device = target
    if not target.startswith('/') and not target.upper().startswith('COM'):
        device = next((i.device for i in list_ports.comports()
                       if (i.serial_number or '').upper() == target.upper()), None)
        if device is None:
            sys.exit(f'podwrite.py: no board with ST-LINK serial {target}')
    return serial.Serial(device, 115200, timeout=0.3, exclusive=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('board', help="the TX: its ST-LINK serial number or a serial device path")
    ap.add_argument('pod', choices=sorted(PODS), help='which pod is on its port')
    ap.add_argument('--operator', default='', help='who wrote it (goes in the ledger)')
    ap.add_argument('--seconds', type=float, default=15.0, help='how long to wait for the reply (default 15)')
    args = ap.parse_args(argv)
    with open_port(args.board) as port:
        serial, reply = write_pod(port, args.pod, args.operator, seconds=args.seconds)
    if reply['outcome'] != 'ok':
        sys.exit(f'podwrite.py: {args.pod} serial {serial} not written: {reply["outcome"]} '
                 f'(the serial stays spent in {LEDGER.name})')
    print(f'{args.pod}: serial {serial} written, crc {reply.get("crc")}. Put the JP1 shunt back on.')


if __name__ == '__main__':
    main()
