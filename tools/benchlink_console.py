"""Record a NUCLEO's console (by ST-LINK serial number) to a text file, one timestamp per line.

    .venv/bin/python tools/benchlink_console.py --serial-number <ST-LINK serial> --out <file.log>

For the bench link's TX (firmware/benchlink) while it sits on a Mac: if it hangs, the last lines show
where. Each line starts with the local time and its UTC offset (2026-10-29T14:00:00-05:00), so the hour
that repeats when daylight saving time ends stays readable. Lines of its own start with '##'.

It survives the board being unplugged or re-flashed (the console is the ST-LINK's USB serial port, not the
SWD link that flashes it), reopens a port that stays silent for STALL_S, and never exits on its own: a
failed write to the log goes to stdout (launchd's log) instead."""
import argparse
import datetime
import sys
import time

import serial
from serial.tools import list_ports

# The TX prints a packet line every 5 s. Longer than this without a line: reopen the port (a USB event on
# the same hub can leave it open but silent, seen 2026-10-29 on the RX).
STALL_S = 25


def port_for(serial_number):
    for p in list_ports.comports():
        if p.serial_number == serial_number:
            return p.device
    return None


def note(path, text):
    """Appends one timestamped line; on a failed write prints it with the error instead. Never raises."""
    line = f'{datetime.datetime.now().astimezone().isoformat(timespec="seconds")} {text}'
    try:
        with open(path, 'a') as f:
            f.write(line + '\n')
    except OSError as e:
        print(f'{line}   [not written: {e}]', flush=True)


def record(serial_number, out, find=port_for, opener=None, clock=time.monotonic, sleep=time.sleep):
    """The loop: find the board, open it, write each line, reopen after a stall or a failure."""
    opener = opener or (lambda dev: serial.Serial(dev, 115200, timeout=1, exclusive=True))
    absent = False
    while True:   # bound: none on purpose: records until stopped
        dev = find(serial_number)
        if not dev:
            if not absent:
                note(out, '## board not on USB; waiting')
                absent = True
            sleep(2)
            continue
        absent = False
        try:
            with opener(dev) as s:
                note(out, f'## connected {dev}')
                last = clock()
                while True:   # bound: none on purpose: until the port fails or stalls
                    line = s.readline()
                    if line:
                        last = clock()
                        note(out, line.decode(errors='replace').rstrip('\r\n'))
                    elif clock() - last > STALL_S:   # the port can go dead while open
                        note(out, f'## no line for {STALL_S} s; reopening')
                        break
        except (serial.SerialException, OSError) as e:
            note(out, f'## disconnected: {e}')
            sleep(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--serial-number', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    note(args.out, '## console logger start')
    try:
        record(args.serial_number, args.out)
    except KeyboardInterrupt:
        return 0
    except BaseException as e:   # launchd restarts it; say why it stopped first
        note(args.out, f'## console logger crash: {e!r}')
        raise


if __name__ == '__main__':
    sys.exit(main())
