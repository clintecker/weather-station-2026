"""Bench telemetry link (firmware/benchlink): the C packet and SHT45 helpers against the logger's decoder;
the logger (tools/benchlink_log.py): its rows, the events that explain a gap, its main loop against a
scripted port and a fake clock, and CSV preparation; the console logger (tools/benchlink_console.py); and
the dashboard (tools/benchlink_dash.py): the charge count, its gap bridging, the gap list, CSV reading
and the HTTP handler.

Pure C compiled for the host, and the tools without a serial port. Not bench evidence: the drills in
firmware/benchlink/README.md exercise the boards."""
import csv
import ctypes
import json
import os
import re
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

import serial
try:
    from toolchain import ROOT, host_library, load_tool, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, load_tool, needs_cc    # python -m unittest tests.<module>

APP = ROOT/'firmware/benchlink/App'
LOG = load_tool('benchlink_log')
DASH = load_tool('benchlink_dash')

# Fills a reading with distinct values in every field, packs it, and unpacks a packet back into the same
# order, so the test sees every field cross the C/Python boundary.
SHIM = r'''
#include <string.h>
#include "bl_pkt.h"
static int32_t *f(bl_reading *r, unsigned k)
{
  int32_t *const a[] = { &r->vout_uv, &r->ishunt_ua, &r->iset_uv, &r->iset_min_uv, &r->iset_max_uv,
                         &r->ina_die_mc, &r->vcell_uv, &r->soc_mpct, &r->crate_mpct_h, &r->sht_t_mc,
                         &r->sht_rh_mpct, &r->vin_uv };
  return a[k];
}
void shim_pack(uint8_t *out)
{
  bl_reading r;
  memset(&r, 0, sizeof r);
  r.flags = 0x3F; r.seq = 0x01020304u; r.uptime_s = 86400u;
  for (unsigned k = 0; k < 12; k++) *f(&r, k) = (int32_t)(k % 2 ? -1000003 * (int32_t)(k + 1) : 1000003 * (int32_t)(k + 1));
  r.samples = 20; r.misses = 3; r.reset_cause = 5; r.faults = 2; r.boots = 513;
  r.tx_timeouts = 7; r.i2c_restarts = 0x1234; r.i2c_unsticks = 9; r.fault_pc = 0x08001abcu;
  bl_pack(&r, out);
}
int shim_unpack(const uint8_t *in, unsigned n, int64_t *out)
{
  bl_reading r;
  if (bl_unpack(in, n, &r)) return -1;
  out[0] = r.flags; out[1] = r.seq; out[2] = r.uptime_s;
  for (unsigned k = 0; k < 12; k++) out[3 + k] = *f(&r, k);
  out[15] = r.samples; out[16] = r.misses; out[17] = r.reset_cause; out[18] = r.faults; out[19] = r.boots;
  out[20] = r.tx_timeouts; out[21] = r.i2c_restarts; out[22] = r.i2c_unsticks; out[23] = r.fault_pc;
  return 0;
}
'''


@needs_cc
class Packet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = cls.lib = host_library(cls, 'bl_pkt', '-I', APP, APP/'bl_pkt.c', files={'shim.c': SHIM})
        lib.shim_pack.argtypes = [ctypes.c_char_p]
        lib.shim_unpack.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int64)]
        lib.bl_crc16.restype = ctypes.c_uint16
        lib.bl_crc16.argtypes = [ctypes.c_char_p, ctypes.c_uint]

    def packed(self):
        buf = ctypes.create_string_buffer(78)
        self.lib.shim_pack(buf)
        return buf.raw

    def unpack(self, raw):
        out = (ctypes.c_int64 * 24)()
        return list(out) if self.lib.shim_unpack(raw, len(raw), out) == 0 else None

    def test_layout_is_version_3_of_78_bytes(self):
        raw = self.packed()
        self.assertEqual(raw[:3], b'WB\x03')
        self.assertEqual(struct.unpack_from('<H', raw, 76)[0], LOG.crc16(raw[:76]))

    def test_crc_is_ccitt_false(self):
        self.assertEqual(self.lib.bl_crc16(b'123456789', 9), 0x29B1)   # the standard check value
        self.assertEqual(LOG.crc16(b'123456789'), 0x29B1)

    def test_logger_decodes_every_field(self):
        p = LOG.decode(self.packed())
        self.assertEqual((p['flags'], p['seq'], p['uptime_s'], p['samples'], p['misses']), (0x3F, 0x01020304, 86400, 20, 3))
        for k, name in enumerate(LOG.FIELDS):
            self.assertEqual(p[name], 1000003 * (k + 1) * (-1 if k % 2 else 1), name)
        self.assertEqual((p['reset'], p['faults'], p['boots'], p['fault_pc']), ('watchdog', 2, 513, '08001abc'))
        self.assertEqual([p[k] for k in LOG.COUNTERS], [7, 0x1234, 9])

    def test_c_round_trip(self):
        out = self.unpack(self.packed())
        self.assertEqual(out[17:], [5, 2, 513, 7, 0x1234, 9, 0x08001abc])

    def test_every_single_bit_flip_is_refused(self):
        raw = self.packed()
        for i in range(len(raw)):
            for bit in range(8):
                bad = bytearray(raw)
                bad[i] ^= 1 << bit
                self.assertIsNone(self.unpack(bytes(bad)), (i, bit))
                self.assertIsNone(LOG.decode(bytes(bad)), (i, bit))

    def test_wrong_lengths_are_refused(self):
        raw = self.packed()
        for raw_n in (raw[:64], raw[:77], raw + b'\0', b'', b'WB'):
            self.assertIsNone(self.unpack(raw_n))
            self.assertIsNone(LOG.decode(raw_n))

    def test_version_2_still_decodes(self):
        body = b'WB\x02\x01' + struct.pack('<II', 5, 25) + struct.pack('<12i', *range(12)) + bytes([20, 0])
        p = LOG.decode(body + struct.pack('<H', LOG.crc16(body)))
        self.assertEqual((p['seq'], p['vin_uv'], p['samples']), (5, 11, 20))
        self.assertNotIn('reset', p)

    def test_version_1_still_decodes(self):
        body = b'WB\x01\x01' + struct.pack('<II', 5, 25) + struct.pack('<11i', *range(11)) + bytes([20, 3])
        p = LOG.decode(body + struct.pack('<H', LOG.crc16(body)))
        self.assertEqual((p['seq'], p['vin_uv'], p['samples'], p['misses']), (5, None, 20, 3))

    def test_c_refuses_another_version_with_a_good_crc(self):
        raw = bytearray(self.packed())
        raw[2] = 2
        struct.pack_into('<H', raw, 76, LOG.crc16(bytes(raw[:76])))
        self.assertIsNone(self.unpack(bytes(raw)))

    def test_an_unknown_reset_code_is_kept_as_a_number(self):
        raw = bytearray(self.packed())
        raw[62] = 9
        struct.pack_into('<H', raw, 76, LOG.crc16(bytes(raw[:76])))
        self.assertEqual(LOG.decode(bytes(raw))['reset'], '9')


@needs_cc
class Sht45(unittest.TestCase):
    """The SHT45 helpers the TX uses (Sensirion SHT4x datasheet 4.4, 4.6): a wrong CRC would clear the SHT
    flag on every packet and lose the air readings all night."""

    @classmethod
    def setUpClass(cls):
        lib = cls.lib = host_library(cls, 'bl_pkt_sht', '-I', APP, APP/'bl_pkt.c')
        lib.sht45_crc8.restype = ctypes.c_uint8
        lib.sht45_crc8.argtypes = [ctypes.c_char_p, ctypes.c_uint]
        for name in ('sht45_t_mc', 'sht45_rh_mpct'):
            getattr(lib, name).restype = ctypes.c_int32
            getattr(lib, name).argtypes = [ctypes.c_uint16]

    def test_crc8_datasheet_vector(self):
        self.assertEqual(self.lib.sht45_crc8(b'\xbe\xef', 2), 0x92)

    def test_temperature_ends(self):
        self.assertEqual(self.lib.sht45_t_mc(0), -45000)
        self.assertEqual(self.lib.sht45_t_mc(65535), 130000)

    def test_humidity_is_clamped(self):
        self.assertEqual(self.lib.sht45_rh_mpct(0), 0)            # the formula gives -6 %
        self.assertEqual(self.lib.sht45_rh_mpct(65535), 100000)   # the formula gives 119 %
        self.assertEqual(self.lib.sht45_rh_mpct(32768), -6000 + 125000 * 32768 // 65535)


def packet_hex(seq, flags=0x3F, uptime=100, reset=1, boots=1, **fields):
    """A valid v3 packet as the RX prints it, built in Python (no C compiler needed)."""
    vals = dict(vout_uv=3_800_000, iset_uv=890_000, iset_min_uv=0, iset_max_uv=2_225_000, vcell_uv=3_900_000,
                vin_uv=5_000_000)
    vals.update(fields)
    body = b'WB\x03' + bytes([flags]) + struct.pack('<II', seq, uptime)
    body += struct.pack('<12i', *(vals.get(f, 0) for f in LOG.FIELDS)) + bytes([20, 0])
    body += struct.pack('<BBHHHHI', reset, 0, boots, 0, 0, 0, 0)
    return (body + struct.pack('<H', LOG.crc16(body))).hex()


def line(seq, **kw):
    return f'#bl rssi=-45 snr=12 len=78 hex={packet_hex(seq, **kw)}\r\n'


class Rows(unittest.TestCase):
    """row(): the CSV columns. DictWriter refuses an unknown key, so one typo would lose every row."""

    def test_every_key_is_a_csv_column(self):
        for raw in (bytes.fromhex(packet_hex(1)), bytes.fromhex(packet_hex(1, flags=0))):
            self.assertLessEqual(set(LOG.row(LOG.decode(raw), -45, 12, 0)), set(LOG.COLUMNS))

    def test_derived_currents_and_voltages(self):
        r = LOG.row(LOG.decode(bytes.fromhex(packet_hex(1))), -45, 12, 0)
        self.assertEqual((r['charge_ma'], r['charge_min_ma'], r['charge_max_ma']), (400.0, 0.0, 1000.0))
        self.assertEqual((r['load_ma'], r['vout_v'], r['vcell_v'], r['vin_v']), (38.0, 3.8, 3.9, 5.0))
        self.assertEqual((r['reset'], r['boots']), ('power', 1))

    def test_a_cleared_flag_leaves_its_columns_blank(self):
        r = LOG.row(LOG.decode(bytes.fromhex(packet_hex(1, flags=0))), -45, 12, 0)
        for k in ('charge_ma', 'load_ma', 'vout_v', 'vcell_v', 'temp_c', 'vin_v'):
            self.assertNotIn(k, r)
        self.assertEqual((r['ina'], r['adc'], r['pgood']), (0, 0, 0))


class Clock:
    """A fake monotonic clock; its sleep advances it."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Port:
    """A scripted serial port: each readline takes the next item (bytes, or an exception to raise) and one
    second; past the script it times out with b'' forever."""

    def __init__(self, clock, script):
        self.clock, self.script = clock, list(script)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def readline(self):
        self.clock.t += 1
        if not self.script:
            return b''
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item.encode() if isinstance(item, str) else item


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.out = os.path.join(self.dir, 'run.csv')
        self.ev = LOG.Events(os.path.join(self.dir, 'run-events.csv'))
        sent = self.sent = []
        for patcher in (mock.patch.object(LOG, 'notify', sent.append), mock.patch('builtins.print')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def events(self):
        if not os.path.exists(self.ev.path):
            return []
        with open(self.ev.path, newline='') as f:
            return [(r['event'], r['detail']) for r in csv.DictReader(f)]

    def names(self):
        return [e for e, _ in self.events()]


class Watching(Base):
    def setUp(self):
        super().setUp()
        self.watch = LOG.Watch(self.ev, 0.0)

    @staticmethod
    def pkt(seq, uptime, **kw):
        p = dict(seq=seq, uptime_s=uptime, reset='power', boots=1, faults=0, fault_pc='',
                 tx_timeouts=0, i2c_restarts=0, i2c_unsticks=0)
        p.update(kw)
        return p

    def test_silence_then_a_watchdog_reboot(self):
        w = self.watch
        w.packet(self.pkt(10, 50), 100.0)
        for t in (110.0, 120.0):   # the RX heartbeat every 10 s keeps going while the TX is silent
            w.heartbeat(t)
            w.idle(t + 5)
        self.assertEqual(self.names(), ['tx_first_packet'])
        w.heartbeat(130.0)
        w.idle(131.0)
        w.packet(self.pkt(0, 5, reset='watchdog', boots=2), 140.0)
        self.assertEqual(self.names(), ['tx_first_packet', 'silence_start', 'silence_end', 'tx_boot'])
        self.assertIn('reset=watchdog boots=2', self.events()[-1][1])
        self.assertIn('after seq=10', self.events()[-1][1])

    def test_a_reboot_is_seen_by_the_boot_count_too(self):
        self.watch.packet(self.pkt(10, 50), 0.0)
        self.watch.packet(self.pkt(40, 200, boots=2, reset='watchdog'), 5.0)   # seq passed the last one heard
        self.assertEqual(self.names(), ['tx_first_packet', 'tx_boot'])

    def test_an_uptime_that_wraps_is_not_a_reboot(self):
        self.watch.packet(self.pkt(10, 4_194_303), 0.0)
        self.watch.packet(self.pkt(11, 1), 5.0)
        self.assertEqual(self.names(), ['tx_first_packet'])

    def test_a_long_silence_alerts_once(self):
        w = self.watch
        w.packet(self.pkt(1, 5), 0.0)
        for t in range(10, 300, 10):
            w.heartbeat(float(t))
            w.idle(float(t))
        self.assertEqual(self.names(), ['tx_first_packet', 'silence_start', 'alert'])
        self.assertEqual(len(self.sent), 1)
        self.assertIn('no packet from the TX for 2 min', self.sent[0])

    def test_no_packet_ever_still_alerts(self):
        for t in range(10, 200, 10):
            self.watch.heartbeat(float(t))
            self.watch.idle(float(t))
        self.assertEqual(self.names(), ['silence_start', 'alert'])
        self.assertIn('none since the logger started', self.events()[-1][1])

    def test_missed_packets_and_rising_counters(self):
        w = self.watch
        w.packet(self.pkt(1, 5), 0.0)
        w.packet(self.pkt(4, 20, i2c_restarts=2, i2c_unsticks=1), 15.0)
        self.assertEqual(self.events()[1:], [('packets_missed', '2 between seq 1 and 4'),
                                             ('tx_i2c_restarts', '0 -> 2'), ('tx_i2c_unsticks', '0 -> 1')])

    def test_rx_heartbeat_lost_and_back(self):
        w = self.watch
        w.packet(self.pkt(1, 5), 0.0)
        w.heartbeat(0.0)
        for t in (29.0, 31.0, 40.0):
            w.idle(t)
        w.heartbeat(41.0)
        self.assertEqual(self.names(), ['tx_first_packet', 'silence_start', 'rx_heartbeat_lost', 'rx_heartbeat_back'])


class Names(unittest.TestCase):
    def test_every_event_name_is_listed(self):
        src = (ROOT/'tools/benchlink_log.py').read_text()
        used = set(re.findall(r"ev\('([a-z_]+)'", src)) | set(re.findall(r"Repeating\(ev, '([a-z_]+)'\)", src))
        used = (used - {'tx_'}) | {'tx_' + k for k in LOG.COUNTERS}   # ev('tx_' + k, ...)
        self.assertEqual(used, set(LOG.EVENTS))
        self.assertLessEqual(set(LOG.ALERT_EVENTS), set(LOG.EVENTS))


class Lines(Watching):
    """handle(): what reaches it from the RX console, including lines cut off by a reset mid-print."""

    def test_a_packet_line_gives_a_row_with_its_gap(self):
        r1 = LOG.handle(line(1), 1.0, self.watch, self.ev)
        r4 = LOG.handle(line(4), 6.0, self.watch, self.ev)
        back = LOG.handle(line(2, boots=2), 11.0, self.watch, self.ev)
        self.assertEqual((r1['gap'], r4['gap'], back['gap']), (0, 2, 0))
        self.assertEqual(self.watch.last['seq'], 2)

    def test_a_cut_off_packet_line_is_a_bad_packet_not_a_crash(self):
        self.assertIsNone(LOG.handle('#bl rssi=-45 snr=12 len=78 hex=5742030', 1.0, self.watch, self.ev))
        self.assertEqual(self.events(), [('bad_packet', '574203')])

    def test_heartbeat_and_notes(self):
        h = lambda text: LOG.handle(text, 1.0, self.watch, self.ev)
        h('#bl hb up=10 good=1 bad=0 err=0 quiet_s=4 rearm=0 boots=1 reset=power faults=0')
        h('#bl boot role=rx reset=watchdog boots=3 faults=0\r\n')
        h('#test-fault: reading 20040000; expect a reset and #fault with bfar=20040000')
        h('random console noise')
        self.assertEqual(self.events(), [('rx_note', '#bl boot role=rx reset=watchdog boots=3 faults=0'),
                                         ('rx_note', '#test-fault: reading 20040000; expect a reset and #fault with bfar=20040000')])
        self.assertEqual(self.watch.last_hb, 1.0)


class Loop(Base):
    """Logger: the main loop against a scripted port and a fake clock."""

    def logger(self, scripts, find=None):
        clock = self.clock = Clock()
        scripts = list(scripts)
        self.opened = []

        def opener(dev):
            self.opened.append(dev)
            s = scripts.pop(0) if scripts else []
            if isinstance(s, BaseException):
                raise s
            return Port(clock, s)
        return LOG.Logger('SN', self.out, self.ev, find=find or (lambda sn: '/dev/fake'), opener=opener,
                          clock=clock, wall=lambda: clock.t, sleep=clock.sleep)

    def run_until(self, lg, t):
        while self.clock.t < t:
            lg.cycle()

    def rows(self):
        with open(self.out, newline='') as f:
            return list(csv.DictReader(f))

    def test_packets_become_rows(self):
        lg = self.logger([[line(1), line(2)]])
        self.run_until(lg, 1010)
        self.assertEqual([r['seq'] for r in self.rows()], ['1', '2'])

    def test_a_silent_port_is_reopened_and_rows_continue(self):
        lg = self.logger([[line(1)], [line(2)]])
        self.run_until(lg, 1040)
        self.assertEqual(self.names()[:4], ['rx_connected', 'tx_first_packet', 'rx_port_reopen', 'rx_connected'])
        self.assertEqual([r['seq'] for r in self.rows()], ['1', '2'])

    def test_a_hung_rx_raises_heartbeat_lost_despite_reopens(self):
        lg = self.logger([['#bl hb up=1 good=0 bad=0 err=0 quiet_s=1 rearm=0 boots=1 reset=power faults=0']])
        self.run_until(lg, 1000 + 600)
        names = self.names()
        self.assertIn('rx_heartbeat_lost', names)
        self.assertLess(names.count('rx_port_reopen'), 8)   # the wait doubles: 25, 50, 100, 200, 400 s
        self.assertIn('rx_heartbeat_lost', [s.split(':')[0] for s in self.sent])

    def test_a_disconnect_clears_the_heartbeat_and_absence_is_logged_once(self):
        present = iter([True] + [False] * 100)
        lg = self.logger([[OSError(6, 'Device not configured')]],
                         find=lambda sn: '/dev/fake' if next(present, False) else None)
        self.run_until(lg, 1000 + 120)
        names = self.names()
        self.assertEqual(names[:3], ['rx_connected', 'rx_disconnected', 'rx_absent'])
        self.assertEqual(names.count('rx_absent'), 1)
        self.assertNotIn('rx_heartbeat_lost', names)

    def test_a_port_that_will_not_open_is_logged_once_and_still_alerts(self):
        lg = self.logger([serial.SerialException('[Errno 16] Resource busy')] * 200)
        self.run_until(lg, 1000 + 200)
        names = self.names()
        self.assertEqual(names.count('rx_open_failed'), 1)
        self.assertIn('silence_start', names)
        self.assertIn('alert', names)

    def test_a_line_that_breaks_the_handler_is_logged_and_reading_goes_on(self):
        lg = self.logger([[line(1), line(2)]])
        real = LOG.handle
        calls = iter([ValueError('boom')])

        def flaky(*a):
            e = next(calls, None)
            if e:
                raise e
            return real(*a)
        with mock.patch.object(LOG, 'handle', flaky):
            self.run_until(lg, 1010)
        self.assertIn(('logger_error', "ValueError('boom')"), self.events())
        self.assertEqual([r['seq'] for r in self.rows()], ['2'])

    def test_a_failed_write_is_logged_retried_and_resumed(self):
        lg = self.logger([[line(1), line(2), line(3)]])
        real_open = open
        fails = iter([True, True, False])

        def flaky_open(path, *a, **kw):
            if path == self.out and next(fails, False):
                raise OSError(28, 'No space left on device')
            return real_open(path, *a, **kw)
        with mock.patch('builtins.open', flaky_open):
            self.run_until(lg, 1010)
        self.assertEqual([e for e in self.names() if e.startswith('csv_')], ['csv_write_failed', 'csv_write_resumed'])
        self.assertEqual([r['seq'] for r in self.rows()], ['3'])
        self.assertNotIn('rx_disconnected', self.names())

    def test_host_sleep_is_logged(self):
        lg = self.logger([[line(1)]])
        lg.wall = lambda: self.clock.t + 3600   # the wall clock jumps an hour: the Mac slept
        lg.cycle()
        self.assertIn('host_sleep', self.names())


class PrepareCsv(Base):
    def write(self, header, *rows, end='\n'):
        with open(self.out, 'w', newline='') as f:
            f.write(','.join(header) + '\n' + ''.join(','.join(r) + '\n' for r in rows))
            if end != '\n':
                f.seek(f.tell() - 1)
                f.truncate()

    def read(self):
        with open(self.out, newline='') as f:
            return list(csv.DictReader(f))

    def test_older_header_is_rewritten_and_kept(self):
        old = LOG.COLUMNS[:-7]
        self.write(old, ['1'] * len(old))
        did = LOG.prepare_csv(self.out)
        self.assertIn('older header rewritten', did)
        rows = self.read()
        self.assertEqual(list(rows[0]), list(LOG.COLUMNS))
        self.assertEqual((rows[0]['seq'], rows[0]['reset']), ('1', ''))
        self.assertTrue(os.path.exists(f'{self.out}.before-{len(LOG.COLUMNS)}-columns'))
        self.assertEqual(LOG.prepare_csv(self.out), '')   # current header: left alone

    def test_a_row_wider_than_its_header_is_trimmed(self):
        old = LOG.COLUMNS[:-7]
        self.write(old, ['1'] * (len(old) + 2))
        LOG.prepare_csv(self.out)
        self.assertEqual(self.read()[0]['seq'], '1')
        self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_unknown_columns_are_set_aside(self):
        self.write(['utc', 'surprise'], ['x', 'y'])
        did = LOG.prepare_csv(self.out)
        self.assertIn('moved to', did)
        self.assertFalse(os.path.exists(self.out))
        self.assertEqual(len([n for n in os.listdir(self.dir) if '.set-aside-' in n]), 1)

    def test_a_header_that_is_not_text_is_set_aside(self):
        with open(self.out, 'wb') as f:
            f.write(b'utc,\xff\xfe\n1,2\n')
        self.assertIn('moved to', LOG.prepare_csv(self.out))
        self.assertFalse(os.path.exists(self.out))

    def test_a_cut_off_last_line_is_ended(self):
        self.write(LOG.COLUMNS, ['1'] * len(LOG.COLUMNS), end='')
        self.assertTrue(LOG.ends_cut_off(self.out))
        self.assertIn('ended a cut-off last line', LOG.prepare_csv(self.out))
        self.assertFalse(LOG.ends_cut_off(self.out))

    def test_an_unwritable_events_file_does_not_raise(self):
        ev = LOG.Events(os.path.join(self.dir, 'missing-dir', 'e.csv'))
        ev('logger_error', 'x')   # prints and notifies instead
        self.assertTrue(any('events file unwritable' in s for s in self.sent))


class Console(unittest.TestCase):
    """tools/benchlink_console.py: the loop reopens a silent port and a failed write never raises."""

    def test_stall_reopen_and_lines(self):
        con = load_tool('benchlink_console')
        clock = Clock()
        scripts = [['#bl seq=1'], ['#bl seq=2']]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'tx.log')

            def opener(dev):
                if not scripts:
                    raise KeyboardInterrupt   # ends the test
                return Port(clock, scripts.pop(0))
            with self.assertRaises(KeyboardInterrupt):
                con.record('SN', out, find=lambda sn: '/dev/fake', opener=opener, clock=clock, sleep=clock.sleep)
            with open(out) as f:
                text = f.read()
        self.assertEqual(text.count('## connected'), 2)
        self.assertEqual(text.count('## no line for'), 2)
        self.assertIn('#bl seq=2', text)

    def test_a_failed_write_prints_instead(self):
        con = load_tool('benchlink_console')
        with mock.patch('builtins.print') as p:
            con.note('/nonexistent-dir/x.log', 'hello')
        self.assertIn('not written', p.call_args[0][0])


class Dashboard(unittest.TestCase):
    @staticmethod
    def r(t, **kw):
        d = dict(t=float(t), seq=None, reset='', charge_ma=0.0, load_ma=38.0, vout_v=3.80, vcell_v=3.80, pgood=0.0)
        d.update(kw)
        return d

    def test_ocv_table_ends_and_interpolation(self):
        self.assertEqual(DASH.ocv_soc(2.5), 0.0)
        self.assertEqual(DASH.ocv_soc(4.3), 100.0)
        self.assertAlmostEqual(DASH.ocv_soc(3.83), 55.0)   # halfway between 3.80 (50 %) and 3.86 (60 %)

    def test_battery_current_rules(self):
        self.assertEqual(DASH.battery_ma(self.r(0, charge_ma=5.0)), -33.0)   # no input: load minus bursts
        self.assertEqual(DASH.battery_ma(self.r(0, pgood=1.0, charge_ma=500.0, vout_v=4.4)), 500.0)
        self.assertEqual(DASH.battery_ma(self.r(0, pgood=1.0, charge_ma=0.0, vout_v=4.4)), 0.0)   # input carries the load
        self.assertEqual(DASH.battery_ma(self.r(0, pgood=1.0, charge_ma=0.0, vout_v=3.85)), -38.0)   # OUT sagged to the cell

    def test_a_gap_is_bridged_and_reported(self):
        rows = [self.r(0), self.r(5), self.r(5 + 3600), self.r(5 + 3605)]
        anchor, bridged = DASH.count(rows, 0)
        self.assertEqual(anchor, 0.0)
        self.assertEqual(list(bridged), [5.0])
        self.assertAlmostEqual(bridged[5.0], -38.0)   # one hour at 38 mA
        self.assertAlmostEqual(rows[-1]['q_mah'], -38.0 * 3610 / 3600)
        self.assertAlmostEqual(rows[0]['soc_cc'], 50.0)
        self.assertAlmostEqual(rows[-1]['soc_cc'], 50.0 + 100 * rows[-1]['q_mah'] / DASH.CAPACITY_MAH)

    def test_no_anchor_no_count(self):
        rows = [self.r(0, vcell_v=None)]
        self.assertEqual(DASH.count(rows, 0), (None, {}))
        self.assertNotIn('soc_cc', rows[0])

    def test_gaps_name_how_the_tx_came_back(self):
        full = [self.r(0, seq=10), self.r(5, seq=11), self.r(100, seq=12), self.r(200, seq=0, reset='power'),
                self.r(205, seq=1), self.r(300, seq=0)]   # the last restart is from an older packet: no cause
        self.assertEqual(DASH.gaps(full, 0, {5.0: -1.0}),
                         [[5.0, 100.0, '', -1.0], [100.0, 200.0, 'power', None], [205.0, 300.0, 'restart', None]])
        self.assertEqual(DASH.gaps(full, 150, {}), [[100.0, 200.0, 'power', None], [205.0, 300.0, 'restart', None]])

    def csv_file(self, d, times, extra=''):
        path = os.path.join(d, 'run.csv')
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=LOG.COLUMNS)
            w.writeheader()
            for i, t in enumerate(times):
                w.writerow(dict(utc=f'2026-10-29T00:{t // 60:02d}:{t % 60:02d}+00:00', seq=i, reset='watchdog',
                                load_ma=38.0, vout_v=3.8, vcell_v=3.8, pgood=i % 2, chg=0, charge_ma=0.0))
            f.write(extra)
        return path

    def test_load_reads_a_logger_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.csv_file(d, (0, 5, 65))
            j = DASH.load(path, 0, 1500, 0.0, 0.0)
            self.assertEqual((j['total'], j['skipped']), (3, 0))
            self.assertEqual(len(j['gaps']), 1)
            self.assertEqual(j['gaps'][0][2], '')                  # seq went on: no restart
            self.assertAlmostEqual(j['gaps'][0][3], -38.0 * 60 / 3600)
            self.assertEqual(j['anchor'], j['rows'][0][0])
            self.assertEqual(j['last_t'], j['rows'][-1][0])
            self.assertEqual(DASH.load(path, 1e12, 1500, 0.0, 0.0)['last_t'], j['last_t'])   # whatever the range

    def test_bucketing_keeps_the_last_state_and_averages_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            j = DASH.load(self.csv_file(d, (0, 5, 10, 15)), 0, 2, 0.0, 0.0)
        ci = j['cols'].index
        self.assertEqual(len(j['rows']), 2)
        self.assertEqual([r[ci('pgood')] for r in j['rows']], [1.0, 1.0])   # the bucket's last, not a mean
        self.assertEqual(j['total'], 4)

    def test_a_torn_last_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            j = DASH.load(self.csv_file(d, (0, 5), extra='2026-10-29T00:00:1'), 0, 1500, 0.0, 0.0)
        self.assertEqual((j['total'], j['skipped'], j['first_bad_line']), (2, 1, 4))

    def test_gauge_valid_from_hides_and_moves_the_anchor(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.csv_file(d, (0, 5, 10))
            t5 = DASH.read_rows(path, 0.0)[0][1]['t']
            j = DASH.load(path, 0, 1500, t5, 0.0)
        ci = j['cols'].index
        self.assertIsNone(j['rows'][0][ci('vcell_v')])
        self.assertEqual(j['anchor'], t5)
        self.assertEqual(j['marks'], [[t5, 'gauge on cell']])

    def test_a_bad_sources_line_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sources.csv')
            with open(path, 'w') as f:
                f.write('start,end,source\n2026-10-29 09:00:00,,usb-c\n2026-10-29 9:00,,solar\n')
            got, err = DASH.sources(path)
        self.assertEqual(len(got), 1)
        self.assertIn('line 3', err)

    def test_http_data_page_404_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.csv_file(d, (0, 5))
            srv = DASH.ThreadingHTTPServer(('127.0.0.1', 0), DASH.handler(path, '', 1500, 0.0, float('inf')))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            j = json.loads(urllib.request.urlopen(base + '/data?since=0').read())
            self.assertEqual((j['total'], j['sources'], j['sources_error'], j['anchor']), (2, [], '', None))
            self.assertIn(b'<title>', urllib.request.urlopen(base + '/').read())
            for url, code in (('/nope', 404), ('/data?since=abc', 500)):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(base + url)
                self.assertEqual(e.exception.code, code)
            self.assertIn('ValueError', json.loads(e.exception.read())['error'])


if __name__ == '__main__':
    unittest.main()
