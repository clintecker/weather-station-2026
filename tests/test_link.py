"""Gap G3: the gateway's RX serial link survives unplug, replug and renamed ports."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import unittest
from types import SimpleNamespace
import serial
try:
    from toolchain import StreamPort
except ImportError:
    from tests.toolchain import StreamPort
from ws0.link import BACKOFF_S, MAX_LINE, ReceiverLink

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


if __name__ == '__main__':
    unittest.main()
