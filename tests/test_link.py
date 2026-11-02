"""The gateway's RX serial link survives unplug, replug and renamed ports."""
import os
from pathlib import Path
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability

import unittest
from types import SimpleNamespace
import serial
try:
    from toolchain import StreamPort
except ImportError:
    from tests.toolchain import StreamPort
from ws0.link import BACKOFF_S, MAX_LINE, SILENT_REOPEN_MAX_S, SILENT_REOPEN_S, ReceiverLink, open_port
from ws0.__main__ import RECEIVER_SILENT_S, Services

RX = '0016001E4142500E20353451'


class FakePort:
    def __init__(self, lines, fail_after=None):
        self.lines, self.fail_after, self.reads, self.written, self.closed = list(lines), fail_after, 0, [], False

    def read_until(self, terminator, size):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise serial.SerialException('device reports readiness to read but returned no data')
        return self.lines.pop(0) if self.lines else b''

    def write(self, data):
        if self.closed:
            raise serial.SerialException('write on closed port')
        self.written.append(data)

    def close(self):
        self.closed = True


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.present = {'/dev/cu.usbmodem122303': RX}
        self.opened, self.logs, self.next_port = [], [], None

    def ports(self):
        return [SimpleNamespace(device=d, serial_number=s) for d, s in self.present.items()]

    def opener(self, path):
        self.opened.append(path)
        return self.next_port

    def link(self):
        return ReceiverLink(serial_number=RX, log=self.logs.append, opener=self.opener,
                            ports=self.ports, clock=lambda: self.now)

    def test_finds_board_by_serial_number_and_reads_lines(self):
        self.next_port = FakePort([b'aa', b'bb\n'])
        link = self.link()
        self.assertEqual(link.poll(), [])
        self.assertEqual(link.poll(), [b'aabb'])
        self.assertEqual(self.opened, ['/dev/cu.usbmodem122303'])
        self.assertIn('serial-open', self.logs[0])

    def test_a_new_connection_first_ends_any_partial_line_on_the_receiver(self):
        # The RX discards a partial line at the newline instead of prefixing the next ACK with it.
        self.next_port = FakePort([b'aa\n'])
        link = self.link()
        link.poll()
        self.assertEqual(self.next_port.written[:1], [b'\n'])

    def test_unplug_then_replug_under_a_new_name(self):
        self.next_port = FakePort([b'x\n'], fail_after=1)
        link = self.link()
        self.assertEqual(link.poll(), [b'x'])
        self.assertEqual(link.poll(), [])          # read error: no exception escapes
        self.assertFalse(link.connected)
        self.assertTrue(any('serial-lost' in line for line in self.logs))
        self.present = {}                            # unplugged
        self.now += BACKOFF_S[0]
        self.assertEqual(link.poll(), [])
        self.assertFalse(link.connected)
        self.present = {'/dev/cu.usbmodem1122303': RX}  # replugged: new port name
        self.next_port = FakePort([b'y\n'])
        self.now += 60
        self.assertEqual(link.poll(), [b'y'])       # reconnects and reads in the same poll
        self.assertTrue(link.connected)
        self.assertEqual(link.path, '/dev/cu.usbmodem1122303')
        self.assertEqual(link.reconnects, 1)

    def test_backoff_limits_retry_rate(self):
        self.present = {}
        link = self.link()
        link.poll()
        attempts = len([l for l in self.logs])
        for _ in range(100):
            link.poll()                              # same instant: no new attempts
        self.assertEqual(len(self.logs), attempts)
        self.now += BACKOFF_S[-1] * 10
        link.poll()
        self.assertFalse(link.connected)

    def test_write_failure_reports_false_and_reconnects(self):
        self.next_port = FakePort([b'z\n'])
        link = self.link()
        link.poll()
        self.next_port.closed = True
        self.assertFalse(link.write(b'ack\n'))
        self.assertFalse(link.connected)

    def test_oversized_line_is_discarded(self):
        self.next_port = FakePort([b'a' * (MAX_LINE + 1)])
        link = self.link()
        self.assertEqual(link.poll(), [])
        self.assertTrue(any('oversized' in line for line in self.logs))

    def poll_all(self, link):
        lines = []
        for _ in range(100):
            lines += link.poll()
        return lines

    def test_longest_firmware_line_is_read_whole(self):
        """A 255-byte '#rx crc' capture is ~560 characters: the RX firmware's trace buffer
        (UTIL_ADV_TRACE_TMP_BUF_SIZE) is 640 bytes, so every line it prints must fit."""
        self.assertGreaterEqual(MAX_LINE, 640)
        longest = b'#rx crc len=255 rssi=-123 snr=-20 data=' + b'ab' * 255
        self.next_port = StreamPort(longest + b'\n' + b'#alive uptime=1\n')
        self.assertEqual(self.poll_all(self.link()), [longest, b'#alive uptime=1'])
        self.assertFalse(any('oversized' in line for line in self.logs))

    def test_tail_of_an_oversized_line_is_not_a_line(self):
        """Hex digits past the limit must not reach the gateway as a radio frame of their own."""
        self.next_port = StreamPort(b'ab' * (MAX_LINE + 300) + b'\nnext\n' + b'cd' * MAX_LINE + b'\n')
        self.assertEqual(self.poll_all(self.link()), [b'next'])
        self.assertEqual(sum('oversized' in line for line in self.logs), 2)


class SilentPortTests(unittest.TestCase):
    """Decision record H8(f): an open port that delivers nothing is reopened in place."""
    PATH = '/dev/cu.usbmodem122303'

    def setUp(self):
        self.now = 0.0
        self.opened, self.logs, self.ports_made = [], [], []
        self.script = []   # lines the next opened port will deliver

    def opener(self, path):
        self.opened.append(path)
        port = FakePort(self.script)
        self.script = []
        self.ports_made.append(port)
        return port

    def link(self):
        return ReceiverLink(serial_number=RX, log=self.logs.append, opener=self.opener,
                            ports=lambda: [SimpleNamespace(device=self.PATH, serial_number=RX)],
                            clock=lambda: self.now)

    def reopens(self):
        return [line for line in self.logs if 'serial-reopen' in line]

    def test_silent_port_is_reopened_in_place_without_backoff(self):
        link = self.link()
        link.poll()
        self.now = SILENT_REOPEN_S - 1
        link.poll()
        self.assertEqual(self.reopens(), [])
        self.now = SILENT_REOPEN_S
        link.poll()
        self.assertEqual(self.opened, [self.PATH, self.PATH])     # same path, in the same poll
        self.assertTrue(self.ports_made[0].closed)
        self.assertTrue(link.connected)
        self.assertEqual((link.failures, link.retry_at, link.reconnects), (0, 0.0, 0))
        self.assertEqual(self.reopens(), [f'#gateway serial-reopen path={self.PATH} silent_s=90 next_s=180'])
        self.assertEqual(self.ports_made[1].written[:1], [b'\n'])   # ends any partial line, as a connect does
        self.assertFalse(any('serial-lost' in line for line in self.logs))

    def test_threshold_doubles_to_the_cap_and_a_line_resets_it(self):
        link = self.link()
        link.poll()
        waits = []
        for _ in range(5):
            before = len(self.reopens())
            start = self.now
            while len(self.reopens()) == before:
                self.now += 1
                link.poll()
            waits.append(self.now - start)
        self.assertEqual(waits, [90, 180, 360, 400, 400])
        self.assertEqual(SILENT_REOPEN_MAX_S, 400)
        self.assertEqual(link.silent_s, 400)
        link.port.lines.append(b'#alive uptime=1\n')
        self.assertEqual(link.poll(), [b'#alive uptime=1'])
        self.assertEqual(link.silent_s, SILENT_REOPEN_S)
        start, before = self.now, len(self.reopens())
        while len(self.reopens()) == before:
            self.now += 1
            link.poll()
        self.assertEqual(self.now - start, 90)
        self.assertTrue(self.reopens()[-1].endswith('silent_s=90 next_s=180'))

    def test_a_line_every_60_s_never_reopens(self):
        link = self.link()
        link.poll()
        for minute in range(1, 31):
            for _ in range(59):
                self.now += 1
                link.poll()
            self.now += 1
            link.port.lines.append(b'#alive uptime=%d\n' % (minute * 60))
            self.assertEqual(link.poll(), [b'#alive uptime=%d' % (minute * 60)])
        self.assertEqual(self.reopens(), [])
        self.assertEqual(self.opened, [self.PATH])

    def test_a_failed_reopen_falls_back_to_the_reconnect_backoff(self):
        link = self.link()
        link.poll()

        def refuse(path):
            raise serial.SerialException('gone')
        link.opener = refuse
        self.now = SILENT_REOPEN_S
        link.poll()
        self.assertFalse(link.connected)
        self.assertEqual(link.failures, 1)
        self.assertEqual(link.retry_at, self.now + BACKOFF_S[0])

    def test_reopen_note_is_a_warn_gateway_event(self):
        """Services.note passes the link's lines to Telemetry.event (ws0/web.py), which takes
        the kind from the word after '#gateway' and stores anything not calm as warn."""
        import sqlite3
        import threading
        from ws0.web import Telemetry
        published = []
        t = Telemetry.__new__(Telemetry)
        t.station = 'ws-test'
        t.store = SimpleNamespace(lock=threading.Lock(), db=sqlite3.connect(':memory:'))
        t.store.db.execute('CREATE TABLE gateway_events (id INTEGER PRIMARY KEY, station TEXT, at REAL, '
                           'source TEXT, kind TEXT, level TEXT, text TEXT)')
        t.hub = SimpleNamespace(publish=lambda topic, row: published.append((topic, row)))
        self.addCleanup(t.store.db.close)
        link = ReceiverLink(serial_number=RX, log=t.event, opener=self.opener,
                            ports=lambda: [SimpleNamespace(device=self.PATH, serial_number=RX)],
                            clock=lambda: self.now)
        link.poll()
        self.now = SILENT_REOPEN_S
        link.poll()
        rows = t.store.db.execute("SELECT kind, level, text FROM gateway_events WHERE kind='serial-reopen'").fetchall()
        self.assertEqual(rows, [('serial-reopen', 'warn', f'#gateway serial-reopen path={self.PATH} silent_s=90 next_s=180')])
        self.assertIn(('serial-reopen', 'warn'), [(r['kind'], r['level']) for _, r in published])


class ReceiverSilentAlarmTests(unittest.TestCase):
    """The reopen sits inside the gateway's receiver-silent alarm, which still fires at 180 s."""

    def services(self, last_seen):
        notes = []
        services = Services.__new__(Services)   # no gateway files, HTTP server or MQTT
        services.gateway = SimpleNamespace(receiver={'alive': True, 'last_seen': last_seen})
        services.link = SimpleNamespace(poll=lambda: [], connected=True)
        services.receiver_log = None
        services.note = notes.append
        return services, notes

    def test_receiver_silent_fires_after_180_s_without_alive(self):
        import time
        self.assertEqual(RECEIVER_SILENT_S, 180)
        services, notes = self.services(time.time() - (RECEIVER_SILENT_S - 5))
        services.poll_receiver()
        self.assertEqual(notes, [])
        self.assertTrue(services.gateway.receiver['alive'])
        services, notes = self.services(time.time() - (RECEIVER_SILENT_S + 1))
        services.poll_receiver()
        services.poll_receiver()   # once, not on every poll
        self.assertEqual(len(notes), 1)
        self.assertIn('#gateway receiver-silent', notes[0])
        self.assertFalse(services.gateway.receiver['alive'])


if __name__ == '__main__':
    unittest.main()


@unittest.skipIf(os.name != 'posix', 'flock locking is POSIX')
class ExclusivePort(unittest.TestCase):
    """Two programs on one board's port would take lines from the same buffer and lose frames."""

    def test_a_second_open_of_a_held_port_fails(self):
        main, sub = os.openpty()
        self.addCleanup(os.close, main); self.addCleanup(os.close, sub)
        with open_port(os.ttyname(sub), timeout=0.05):
            with self.assertRaises(serial.SerialException):
                open_port(os.ttyname(sub), timeout=0.05)
        open_port(os.ttyname(sub), timeout=0.05).close()             # free again after the first closes

    def test_every_serial_opener_holds_the_port(self):
        root = Path(__file__).resolve().parent.parent
        for path in [*root.glob('ws0/*.py'), *root.glob('tools/*.py')]:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if 'serial.Serial(' in line:
                    self.assertIn('exclusive=True', line, f'{path.name}:{n}')
