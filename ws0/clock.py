"""Host clock check.

The gateway is the station's only time source: every ACK carries host UTC. A wrong host clock
would put a consistent but wrong time on all data. This module measures the host clock offset
with a minimal SNTP query (RFC 4330) at startup and every hour, in a background thread so an
ACK is never delayed.

Policy. An SNTP offset is only known to within half the round trip (rtt/2), so:
  * |offset| + rtt/2 <= MAX_OFFSET_S           -> 'ok': ACKs carry host UTC
  * |offset| - rtt/2 >  MAX_OFFSET_S           -> 'bad': ACKs carry UTC 0, so the node keeps its
                                                  own clock (and marks samples unknown after 6 h)
  * in between (a slow round trip), or no      -> 'unverified': ACKs carry host UTC (the clock
    measurement possible (no network)             was set by NTP before); status shows it
A 'bad' result is kept until a later measurement is clearly within the limit. After a failed or
undecided check the next one comes after RETRY_S instead of CHECK_PERIOD_S.
"""
import socket
import struct
import threading
import time

MAX_OFFSET_S = 1.0
CHECK_PERIOD_S = 3600
RETRY_S = 300
NTP_EPOCH = 2208988800  # seconds from 1900-01-01 to 1970-01-01


def sntp_offset(server='pool.ntp.org', timeout=2.0):
    """Return (offset_s, round_trip_s): server time minus local time."""
    packet = bytearray(48)
    packet[0] = 0x23  # LI 0, version 4, mode 3 (client)
    # Resolve the name first: a lookup inside sendto() would fall between t1 and the server's
    # receive time and read as a positive offset of half the lookup time.
    address = socket.getaddrinfo(server, 123, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        t1 = time.time()
        sock.sendto(packet, address)
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
        """Measure once; return the delay in seconds until the next check."""
        try:
            offset, rtt = self.measure(self.server)
        except (OSError, ValueError) as exc:
            with self.lock:
                self.error = f'{type(exc).__name__}: {exc}'
                if self.state != 'bad':
                    self.state = 'unverified'
            self.log(f'#gateway host-clock unverified ({self.error})')
            return RETRY_S
        bound = max(rtt, 0.0) / 2
        with self.lock:
            previous = self.state
            self.offset, self.checked_at, self.error = offset, self.clock(), None
            if abs(offset) + bound <= MAX_OFFSET_S:
                self.state = 'ok'
            elif abs(offset) - bound > MAX_OFFSET_S:
                self.state = 'bad'
            elif self.state != 'bad':
                self.state = 'unverified'
                self.error = 'round trip too slow to decide'
        if self.state != 'ok' or previous != self.state:
            self.log(f'#gateway host-clock {self.state} offset={offset:+.3f}s rtt={rtt:.3f}s server={self.server}')
        return CHECK_PERIOD_S if self.state == 'ok' else RETRY_S

    def may_issue_time(self):
        with self.lock:
            return self.state != 'bad'

    def status(self):
        with self.lock:
            return {'state': self.state, 'offset_s': self.offset, 'checked_at': self.checked_at,
                    'error': self.error, 'server': self.server, 'max_offset_s': MAX_OFFSET_S}

    def run(self, sleep=time.sleep):
        """Check forever. An unexpected error (in a measurement or in the log callback, which writes
        to SQLite) is logged and retried after RETRY_S: before, it ended the thread and froze the
        clock state silently."""
        while True:
            try:
                delay = self.check()
            except Exception as exc:   # noqa: BLE001 - the thread must survive anything
                delay = RETRY_S
                try:
                    self.log(f'#gateway host-clock check failed ({type(exc).__name__}: {exc}); retrying')
                except Exception:      # noqa: BLE001 - the logger itself may be what failed
                    pass
            sleep(delay)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name='host-clock').start()
        return self
