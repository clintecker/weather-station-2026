"""Host clock check (failure-modes.md gap G9).

The gateway is the station's only time source: every ACK carries host UTC. A wrong host clock
would put a consistent but wrong time on all data. This module measures the host clock offset
with a minimal SNTP query (RFC 4330) at startup and every hour, in a background thread so an
ACK is never delayed.

Policy:
  * measured |offset| <= MAX_OFFSET_S          -> 'ok': ACKs carry host UTC
  * measured |offset| >  MAX_OFFSET_S          -> 'bad': ACKs carry UTC 0, so the node keeps its
                                                  own clock (and marks samples unknown after 6 h)
  * no measurement possible (no network)       -> 'unverified': ACKs carry host UTC (the clock
                                                  was set by NTP before); status shows it
A 'bad' result is kept until a later measurement is within the limit.
"""
import socket
import struct
import threading
import time

MAX_OFFSET_S = 1.0
CHECK_PERIOD_S = 3600
NTP_EPOCH = 2208988800  # seconds from 1900-01-01 to 1970-01-01


def sntp_offset(server='pool.ntp.org', timeout=2.0):
    """Return (offset_s, round_trip_s): server time minus local time."""
    packet = bytearray(48)
    packet[0] = 0x23  # LI 0, version 4, mode 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        t1 = time.time()
        sock.sendto(packet, (server, 123))
        data, _ = sock.recvfrom(512)
        t4 = time.time()
    if len(data) < 48 or (data[0] & 0x07) != 4 or data[1] == 0:  # server mode; stratum 0 = kiss-o'-death
        raise ValueError('invalid SNTP reply')
    def ts(offset):
        seconds, fraction = struct.unpack('>II', data[offset:offset + 8])
        return seconds - NTP_EPOCH + fraction / 2**32
    t2, t3 = ts(32), ts(40)
    return ((t2 - t1) + (t3 - t4)) / 2, (t4 - t1) - (t3 - t2)


class HostClock:
    def __init__(self, server='pool.ntp.org', measure=sntp_offset, log=print, clock=time.time):
        self.server, self.measure, self.log, self.clock = server, measure, log, clock
        self.state, self.offset, self.checked_at, self.error = 'unverified', None, None, None
        self.lock = threading.Lock()

    def check(self):
        try:
            offset, rtt = self.measure(self.server)
        except (OSError, ValueError) as exc:
            with self.lock:
                self.error = f'{type(exc).__name__}: {exc}'
                if self.state != 'bad':
                    self.state = 'unverified'
            self.log(f'#gateway host-clock unverified ({self.error})')
            return
        with self.lock:
            previous = self.state
            self.offset, self.checked_at, self.error = offset, self.clock(), None
            self.state = 'ok' if abs(offset) <= MAX_OFFSET_S else 'bad'
        if self.state == 'bad' or previous != self.state:
            self.log(f'#gateway host-clock {self.state} offset={offset:+.3f}s rtt={rtt:.3f}s server={self.server}')

    def may_issue_time(self):
        with self.lock:
            return self.state != 'bad'

    def status(self):
        with self.lock:
            return {'state': self.state, 'offset_s': self.offset, 'checked_at': self.checked_at,
                    'error': self.error, 'server': self.server, 'max_offset_s': MAX_OFFSET_S}

    def start(self):
        def loop():
            while True:
                self.check()
                time.sleep(CHECK_PERIOD_S)
        threading.Thread(target=loop, daemon=True, name='host-clock').start()
        return self
