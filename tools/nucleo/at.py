#!/usr/bin/env python3
"""Send AT commands to a NUCLEO-WL55JC1 running the ST factory Concentrator firmware.

The factory firmware's console runs at 9600 8N1 (not 115200).

Usage: python3 tools/nucleo/at.py /dev/cu.usbmodemXXXX "AT+VER=?" "AT?"
"""
import os
import select
import sys
import termios
import time


def talk(port, cmds, baud=termios.B9600, wait=1.2):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = attrs[5] = baud
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    out = b""

    def drain(seconds):
        nonlocal out
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    out += os.read(fd, 4096)
                except BlockingIOError:
                    pass

    drain(0.5)
    for cmd in cmds:
        os.write(fd, (cmd + "\r\n").encode())
        drain(wait)
    os.close(fd)
    return out.decode(errors="replace")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    print(talk(sys.argv[1], sys.argv[2:]))
