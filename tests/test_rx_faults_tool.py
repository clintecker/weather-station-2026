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
        self.assertIn('2 look like ours, 0 ours with a damaged header (1 with an accepted frame', text)
        self.assertIn('3 of 336 bits differ', text)
        self.assertIn('header CRC failed', text)
        self.assertIn('data=' + FRAME.hex()[:16], text)   # the capture, in full
        self.assertIn('1 bad receptions', self.run_tool('--since', '2027-01-15T08:01:43Z'))
        self.assertIn('No bad receptions', self.run_tool('--since', '2030-01-01T00:00:00Z'))
        self.assertFalse(Path(str(self.path) + '-wal').exists())   # opened read-only, nothing created

    def add(self, sql, *rows):
        db = Store(self.path).db
        with db:
            db.executemany(sql, rows)
        db.close()

    def test_damaged_kind_byte_close_to_an_accepted_frame_is_ours(self):
        damaged = bytearray(FRAME)
        damaged[0] ^= 0xF0                                     # kind byte hit: 0xa1, not one of ours
        far = bytes(len(FRAME))                                # same length, half the bits or so differ
        self.add("INSERT INTO rx_faults (station,received_at,kind,length,rssi_dbm,snr_db,data) "
                 "VALUES ('s',?,'crc',?,-100,-6,?)", (T + 4, len(FRAME), damaged.hex()), (T + 5, len(FRAME), far.hex()))
        rows = json.loads(self.run_tool('--json', '--since', tool.iso(T + 4)))
        self.assertEqual([r['class'] for r in rows['rows']][:2], ['ours (damaged header)', 'foreign/noise'])
        self.assertEqual(rows['rows'][0]['match']['bits_differ'], 4)
        self.assertEqual(rows['summary']['ours_damaged_header'], 1)
        self.assertIn('ours (damaged header)', self.run_tool('--since', tool.iso(T + 4)))

    def test_until_and_limit(self):
        rows = json.loads(self.run_tool('--json', '--until', tool.iso(T + 101)))['rows']
        self.assertEqual([r['received_at'] for r in rows], [T, T + 100])          # until is exclusive
        rows = json.loads(self.run_tool('--json', '--limit', '2'))['rows']
        self.assertEqual([r['received_at'] for r in rows], [T + 102, T + 103])    # the newest, oldest first
        rows = json.loads(self.run_tool('--json', '--since', tool.iso(T), '--until', tool.iso(T + 103),
                                        '--limit', '1'))['rows']
        self.assertEqual([r['received_at'] for r in rows], [T + 102])

    def test_two_queries_however_many_faults(self):
        import sqlite3
        db = sqlite3.connect(self.path)
        statements = []
        db.set_trace_callback(statements.append)
        rows = tool.load(db)
        db.close()
        self.assertEqual(len(rows), 5)
        self.assertEqual(len([q for q in statements if q.startswith('SELECT')]), 2)

    def test_old_database_is_named_not_a_traceback(self):
        import sqlite3
        db = sqlite3.connect(self.path)
        with db:
            db.execute('ALTER TABLE radio_events DROP COLUMN frame_hex')
        db.close()
        with self.assertRaises(SystemExit) as caught:
            self.run_tool()
        self.assertIn('table radio_events predates this gateway version', str(caught.exception.code))
        self.assertIn('rename or drop table radio_events', str(caught.exception.code))


if __name__ == '__main__':
    unittest.main()
