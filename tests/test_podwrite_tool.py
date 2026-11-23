"""tools/podwrite.py: the serial draw, the console line, the reply parse and the ledger, with the TX's
serial port replaced by a scripted fake (no hardware is touched)."""
import datetime
import tempfile
import unittest
from pathlib import Path
try:
    from toolchain import load_tool
except ImportError:
    from tests.toolchain import load_tool

tool = load_tool('podwrite')
RECORD = '57534d52' + '00' * 124
NOW = datetime.datetime(2026, 11, 23, 12, 0, tzinfo=datetime.timezone.utc)


class FakePort:
    def __init__(self, replies):
        self.replies = [r.encode() + b'\n' for r in replies]
        self.sent = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.sent.append(data.decode())

    def readline(self):
        return self.replies.pop(0) if self.replies else b''


class SerialTests(unittest.TestCase):
    def test_namespace_and_bits(self):
        s = tool.draw_serial(set())
        self.assertEqual(len(s), 16)
        self.assertTrue(s.startswith('01'))

    def test_bad_draws_and_used_ones_are_drawn_again(self):
        draws = iter([0, (1 << 56) - 1, 5, 6])
        used = {'0100000000000005'}
        self.assertEqual(tool.draw_serial(used, lambda _: next(draws)), '0100000000000006')

    def test_command(self):
        self.assertEqual(tool.command('UV', '0123456789abcdef'), 'PODWRITE 3 3 0123456789abcdef WRITE-POD-RECORD')
        self.assertEqual(tool.command('BARO', '01ff')[:12], 'PODWRITE 2 2')


class ReplyTests(unittest.TestCase):
    def test_ok(self):
        r = tool.parse_reply(f'#podwrite ok port=1 type=1 serial=0102030405060708 bind=1a2b3c4d crc=deadbeef record={RECORD}')
        self.assertEqual((r['outcome'], r['bind'], r['crc'], r['record']), ('ok', '1a2b3c4d', 'deadbeef', RECORD))

    def test_fail_with_spaces_in_why(self):
        r = tool.parse_reply('#podwrite FAIL port=3 type=3 serial=0102030405060708 why=verify (is the JP1 shunt still on?)')
        self.assertEqual((r['outcome'], r['port']), ('verify', '3'))

    def test_other_lines(self):
        self.assertIsNone(tool.parse_reply('#podwrite started port=1 type=1 (JP1 shunt off)'))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name)/'ledger.csv'

    def tearDown(self):
        self.tmp.cleanup()

    def run_pod(self, pod, replies):
        port = FakePort(replies)
        serial, reply = tool.write_pod(port, pod, 'op', self.ledger, seconds=1.0, log=lambda _: None, now=NOW)
        return port, serial, reply

    def test_ok_write(self):
        # The reply has to carry the drawn serial, so the draw is fixed.
        orig = tool.draw_serial
        tool.draw_serial = lambda used: '0100000000000abc'
        try:
            port, serial, reply = self.run_pod('TH', ['#podwrite started port=1 type=1 (x)',
                                                      '#podwrite ok port=1 type=1 serial=0100000000000abc '
                                                      f'bind=1a2b3c4d crc=deadbeef record={RECORD}'])
        finally:
            tool.draw_serial = orig
        self.assertEqual(port.sent, ['PODWRITE 1 1 0100000000000abc WRITE-POD-RECORD\n'])
        rows = tool.read_ledger(self.ledger)
        self.assertEqual([r['outcome'] for r in rows], ['sent', 'ok'])
        self.assertEqual((rows[1]['serial'], rows[1]['bind'], rows[1]['record'], rows[1]['date']),
                         (serial, '1a2b3c4d', RECORD, '2026-11-23T12:00:00Z'))

    def test_failed_serial_is_never_drawn_again(self):
        _, first, reply = self.run_pod('UV', ['#podwrite FAIL port=3 type=3 serial=x why=no-eeprom'])
        self.assertEqual(reply['outcome'], 'no-eeprom')
        orig = tool.secrets.randbits
        draws = iter([int(first[2:], 16), 7])
        tool.secrets.randbits = lambda _: next(draws)
        try:
            used = {r['serial'] for r in tool.read_ledger(self.ledger)}
            self.assertEqual(tool.draw_serial(used, tool.secrets.randbits), '0100000000000007')
        finally:
            tool.secrets.randbits = orig

    def test_refusal_and_silence(self):
        _, _, reply = self.run_pod('BARO', ['#error podwrite type (not this port\'s module type)'])
        self.assertEqual(reply['outcome'], 'refused')
        _, _, reply = self.run_pod('BARO', [])
        self.assertEqual(reply['outcome'], 'no-reply')
        self.assertEqual([r['outcome'] for r in tool.read_ledger(self.ledger)], ['sent', 'refused', 'sent', 'no-reply'])

    def test_wrong_serial_in_reply(self):
        _, _, reply = self.run_pod('TH', [f'#podwrite ok port=1 type=1 serial=0100000000000001 bind=0 crc=0 record={RECORD}'])
        self.assertEqual(reply['outcome'], 'serial-mismatch')


if __name__ == '__main__':
    unittest.main()
