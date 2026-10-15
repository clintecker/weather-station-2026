"""tools/rx_faults.py: classification of stored bad receptions against accepted frames."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before gateway is imported
    from toolchain import load_tool
except ImportError:
    from tests.toolchain import load_tool
from gateway import Store
from ws0 import web

tool = load_tool('rx_faults')
T = 1_800_000_000
FRAME = bytes([0x51, 0x00, 0x01, 0, 0, 0, 0, 7]) + bytes(range(34))   # an obs frame as the gateway accepted it


class RxFaultsToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'observations.sqlite3'
        store = Store(self.path)
        db = store.db
        with db:
            for sql in web.TABLES:
                db.execute(sql)
            db.execute("INSERT INTO radio_events (station,received_at,kind,outcome,length,frame_hex) "
                       "VALUES ('s',?,'obs','ack',?,?)", (T + 2, len(FRAME), FRAME.hex()))
            db.execute("INSERT INTO radio_events (station,received_at,kind,outcome,length,frame_hex) "
                       "VALUES ('s',?,'obs','rejected',?,?)", (T + 1, len(FRAME), FRAME.hex()))   # not accepted
            corrupted = bytearray(FRAME)
            corrupted[10] ^= 0b101
            corrupted[30] ^= 0x80
            faults = [(T, 'crc', len(FRAME), -95, -4, corrupted.hex()),             # ours, 3 bits off
                      (T + 100, 'crc', 3, -110, -12, '540001'),                     # ours (diag), nothing near
                      (T + 101, 'crc', 4, -118, -14, '00ff12aa'),                   # foreign
                      (T + 102, 'crc', 0, -120, -15, ''),                           # empty capture
                      (T + 103, 'hdr', None, -121, None, None)]
            db.executemany("INSERT INTO rx_faults (station,received_at,kind,length,rssi_dbm,snr_db,data) "
                           "VALUES ('s',?,?,?,?,?,?)", faults)
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tool.main(['--db', str(self.path), *args])
        return out.getvalue()

    def test_classification(self):
        rows = json.loads(self.run_tool('--json'))
        classes = [r['class'] for r in rows['rows']]
        self.assertEqual(classes, ['ours', 'ours', 'foreign/noise', 'foreign/noise', 'header'])
        first = rows['rows'][0]
        self.assertEqual((first['frame_kind'], first['station_id'], first['counter']), ('obs', 1, 7))
        self.assertEqual(first['match'], {'dt_s': 2.0, 'outcome': 'ack', 'length': len(FRAME), 'bits_differ': 3,
                                          'bits': 8 * len(FRAME), 'counter': 7})
        self.assertEqual((rows['rows'][1]['frame_kind'], rows['rows'][1]['match']), ('diag', None))
        self.assertEqual({k: rows['summary'][k] for k in ('total', 'crc', 'hdr', 'ours', 'ours_matched',
                                                          'foreign_or_noise', 'median_bits_differ')},
                         {'total': 5, 'crc': 4, 'hdr': 1, 'ours': 2, 'ours_matched': 1, 'foreign_or_noise': 2,
                          'median_bits_differ': 3})

    def test_hamming_counts_length_difference(self):
        self.assertEqual(tool.hamming(b'\x00\xff', b'\x01\xff\x00\x00'), 1 + 16)

    def test_text_report_and_since(self):
        text = self.run_tool()
        self.assertIn('5 bad receptions', text)
        self.assertIn('2 look like ours (1 with an accepted frame', text)
        self.assertIn('3 of 336 bits differ', text)
        self.assertIn('header CRC failed', text)
        self.assertIn('data=' + FRAME.hex()[:16], text)   # the capture, in full
        self.assertIn('1 bad receptions', self.run_tool('--since', '2027-01-15T08:01:43Z'))
        self.assertIn('No bad receptions', self.run_tool('--since', '2030-01-01T00:00:00Z'))
        self.assertFalse(Path(str(self.path) + '-wal').exists())   # opened read-only, nothing created


if __name__ == '__main__':
    unittest.main()
