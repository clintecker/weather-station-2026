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
from ws0.protocol import KIND_DIAG, KIND_OBS, VERSION, VERSION_SHIFT

tool = load_tool('rx_faults')
T = 1_800_000_000
OBS, DIAG = ((VERSION << VERSION_SHIFT) | k for k in (KIND_OBS, KIND_DIAG))     # byte 0, current version
FRAME = bytes([OBS, 0x00, 0x01, 0, 0, 0, 0, 7]) + bytes(range(34))   # an obs frame as the gateway accepted it


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
                      (T + 100, 'crc', 3, -110, -12, f'{DIAG:02x}0001'),            # ours (diag), nothing near
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
        self.assertEqual({r['frame_version'] for r in rows['rows'][:2]}, {VERSION})
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

    def test_a_previous_version_capture_is_ours_not_noise(self):
        """A run keeps its captures for 30 days: one from the previous release (version 5 under
        version 6) is classified as ours, from the previous version, and never as noise."""
        old = bytearray(FRAME)
        old[0] = ((VERSION - 1) << VERSION_SHIFT) | KIND_DIAG
        nonsense = bytes([((VERSION - 2) << VERSION_SHIFT) | KIND_OBS]) + bytes(range(50, 90))   # two versions back
        self.add("INSERT INTO rx_faults (station,received_at,kind,length,rssi_dbm,snr_db,data) "
                 "VALUES ('s',?,'crc',?,-100,-6,?)", (T + 4, len(old), old.hex()), (T + 5, len(nonsense), nonsense.hex()))
        rows = json.loads(self.run_tool('--json', '--since', tool.iso(T + 4), '--until', tool.iso(T + 6)))
        first = rows['rows'][0]
        self.assertEqual((first['class'], first['frame_version'], first['frame_kind'], first['station_id'], first['counter']),
                         ('ours (previous version)', VERSION - 1, 'diag', 1, 7))
        self.assertEqual(first['match']['bits_differ'], bin(FRAME[0] ^ old[0]).count('1'))   # byte 0 only
        self.assertEqual(rows['rows'][1]['class'], 'foreign/noise')
        self.assertEqual({k: rows['summary'][k] for k in ('ours', 'ours_previous_version', 'ours_matched')},
                         {'ours': 0, 'ours_previous_version': 1, 'ours_matched': 1})
        text = self.run_tool('--since', tool.iso(T + 4), '--until', tool.iso(T + 6))
        self.assertIn(f'1 ours from the previous protocol version ({VERSION - 1})', text)
        self.assertIn(f'ours (previous version)  diag (version {VERSION - 1}) station=1 counter=7', text)

    def test_the_docstring_names_the_byte_values_of_both_versions(self):
        for version in (VERSION, VERSION - 1):
            self.assertIn(f'0x{(version << VERSION_SHIFT) | KIND_OBS:02x} obs', tool.__doc__)
        self.assertNotIn('{', tool.__doc__)

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
