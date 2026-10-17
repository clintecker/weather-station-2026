"""Send one console line to a board found by its ST-LINK serial number, and print what it says back.

    .venv/bin/python tools/console.py 003B00194142500E20353451 STATUS
    .venv/bin/python tools/console.py 003B00194142500E20353451 "WIPE ERASE-ALL-NODE-STATE" --seconds 8

PROVISION is refused: a key on a command line ends up in shell history. Use `ws0 provision-node`.
Only one program can hold a port, so this never works on RX while `ws0 serve` runs.
"""
import argparse
import sys
import time

import serial
from serial.tools import list_ports

BAUD = 115200   # the boards' ST-LINK virtual COM port (ws0/link.py BAUD)


def find_port(serial_number):
    for info in list_ports.comports():
        if (info.serial_number or '').upper() == serial_number.upper():
            return info.device
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('serial_number', help='ST-LINK serial number of the board')
    ap.add_argument('line', help='the console line, for example STATUS')
    ap.add_argument('--seconds', type=float, default=4.0, help='how long to print replies (default 4)')
    args = ap.parse_args(argv)
    if args.line.upper().startswith('PROVISION'):
        sys.exit('console.py: PROVISION is refused here; use ws0 provision-node (keeps the key off the command line)')
    device = find_port(args.serial_number)
    if device is None:
        sys.exit(f'console.py: no board with ST-LINK serial {args.serial_number}')
    with serial.Serial(device, BAUD, timeout=0.3) as port:
        port.reset_input_buffer()
        port.write(args.line.encode('ascii') + b'\n')
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            text = port.readline().decode('ascii', 'replace').rstrip()
            if text:
                print(text, flush=True)


if __name__ == '__main__':
    main()
