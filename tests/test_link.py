"""Gap G3: the gateway's RX serial link survives unplug, replug and renamed ports."""
import unittest
from types import SimpleNamespace
import serial
from ws0.link import BACKOFF_S, ReceiverLink

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
        self.next_port = FakePort([b'a' * 257])
        link = self.link()
        self.assertEqual(link.poll(), [])
        self.assertTrue(any('oversized' in line for line in self.logs))


if __name__ == '__main__':
    unittest.main()
