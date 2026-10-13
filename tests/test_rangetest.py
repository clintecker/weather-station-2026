"""Bench range-test firmware (firmware/rangetest): packet format and the settings handshake.

The handshake changes spreading factor or power on both boards together and rolls back
when the boards lose each other right after a change. Pure C, compiled for the host.
"""
import ctypes
import subprocess
import tempfile
import unittest
from toolchain import needs_cc
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent/'firmware/rangetest/App/rt_proto.c'
EV_SWITCHED, EV_COMMIT, EV_ROLLBACK, EV_ADOPTED, EV_FALLBACK = 1, 2, 4, 8, 16
EV_LOST_MISSES = 10  # RT_LOST_MISSES: ~30 s of 3 s receive windows


class Board:
    def __init__(self, lib):
        self.lib = lib
        self.st = ctypes.create_string_buffer(lib.rt_state_size())
        lib.rt_init(self.st)

    def cfg(self):
        return (self.lib.rt_cur_sf(self.st), self.lib.rt_cur_pwr(self.st))

    def tentative(self):
        return bool(self.lib.rt_is_tentative(self.st))


@needs_cc
class RangeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name)/'rt_proto.so'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(SRC), '-o', str(path)], check=True)
        lib = cls.lib = ctypes.CDLL(str(path))
        lib.rt_state_size.restype = ctypes.c_size_t
        lib.rt_build.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_int16,
                                 ctypes.c_int8, ctypes.POINTER(ctypes.c_uint8)]
        lib.rt_build.restype = ctypes.c_size_t
        lib.rt_on_rx.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
                                 ctypes.c_void_p]
        for name in ('rt_cur_sf', 'rt_cur_pwr', 'rt_info_sf', 'rt_info_pwr'):
            getattr(lib, name).restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def send(self, src, dst, kind=0, seq=1, rssi=-80, snr=5, lost=False):
        """src transmits one packet; dst hears it only if not lost and both share an SF."""
        buf = (ctypes.c_uint8*16)()
        n = self.lib.rt_build(src.st, kind, seq, rssi, snr, buf)
        self.assertEqual(n, 16)
        src_sf = src.cfg()[0]
        ev_tx = self.lib.rt_on_tx_done(src.st)
        if lost or dst.cfg()[0] != src_sf:
            return ev_tx, None, bytes(buf)
        info = ctypes.create_string_buffer(16)
        ev_rx = self.lib.rt_on_rx(dst.st, buf, 16, info)
        return ev_tx, ev_rx, bytes(buf)

    def exchange(self, a, b, **kw):
        self.send(a, b, kind=0, **kw)
        self.send(b, a, kind=1, **kw)

    def test_boot_setting_is_most_robust(self):
        self.assertEqual(Board(self.lib).cfg(), (12, 22))

    def test_packet_fields_round_trip(self):
        a, b = Board(self.lib), Board(self.lib)
        buf = (ctypes.c_uint8*16)()
        self.lib.rt_build(a.st, 1, 0x1234, -97, -3, buf)
        raw = bytes(buf)
        self.assertEqual(raw[:3], b'RT\x01')
        self.assertEqual(raw[3], 1)
        self.assertEqual(int.from_bytes(raw[8:10], 'little'), 0x1234)
        self.assertEqual(int.from_bytes(raw[10:12], 'little', signed=True), -97)
        self.assertEqual(ctypes.c_int8(raw[12]).value, -3)
        self.assertEqual(self.lib.rt_on_rx(b.st, buf, 16, None), 0)

    def test_rejects_foreign_or_short_packets(self):
        b = Board(self.lib)
        junk = (ctypes.c_uint8*16)(*b'PING' + bytes(12))
        self.assertEqual(self.lib.rt_on_rx(b.st, junk, 16, None), -1)
        good = (ctypes.c_uint8*16)()
        self.lib.rt_build(Board(self.lib).st, 0, 1, -50, 9, good)
        self.assertEqual(self.lib.rt_on_rx(b.st, good, 15, None), -1)

    def test_power_change_reaches_both_boards_then_commits(self):
        a, b = Board(self.lib), Board(self.lib)
        self.lib.rt_press_pwr(a.st)
        self.assertEqual(a.cfg(), (12, 22))          # nothing changes until the peer agrees
        _, ev, _ = self.send(a, b, kind=0)          # proposal
        self.assertEqual(ev & EV_SWITCHED, 0)
        ev_tx, _, _ = self.send(b, a, kind=1)       # ack; b switches once it is sent
        self.assertTrue(ev_tx & EV_SWITCHED)
        self.assertEqual(b.cfg(), (12, 14))
        self.assertEqual(a.cfg(), (12, 14))          # a switched on hearing the ack
        self.assertTrue(a.tentative() and b.tentative())
        self.exchange(a, b)
        self.assertFalse(a.tentative() or b.tentative())

    def test_sf_change_with_lost_ack_rolls_back_then_retries(self):
        a, b = Board(self.lib), Board(self.lib)
        self.lib.rt_press_sf(a.st)
        self.send(a, b, kind=0)
        self.send(b, a, kind=1, lost=True)          # b switched to SF10, a never heard the ack
        self.assertEqual((a.cfg()[0], b.cfg()[0]), (12, 10))
        rolled = [self.lib.rt_on_miss(b.st) & EV_ROLLBACK for _ in range(5)]
        self.assertEqual(rolled, [0, 0, 0, 0, EV_ROLLBACK])
        self.assertEqual(b.cfg(), (12, 22))           # back where a still is
        self.send(a, b, kind=0)                     # a still carries the same proposal
        self.send(b, a, kind=1)
        self.assertEqual((a.cfg()[0], b.cfg()[0]), (10, 10))
        self.exchange(a, b)
        self.assertFalse(a.tentative() or b.tentative())

    def committed(self, sf_presses=0, pwr_presses=0):
        a, b = Board(self.lib), Board(self.lib)
        self.exchange(a, b)                         # first contact
        for _ in range(sf_presses):
            self.lib.rt_press_sf(a.st)
        for _ in range(pwr_presses):
            self.lib.rt_press_pwr(a.st)
        self.send(a, b, kind=0)
        self.send(b, a, kind=1)
        self.exchange(a, b)
        self.assertFalse(a.tentative() or b.tentative())
        return a, b

    def test_brief_dropouts_after_commit_keep_settings(self):
        a, _ = self.committed(sf_presses=1)         # SF10
        for _ in range(2):
            for _ in range(EV_LOST_MISSES - 1):
                self.assertEqual(self.lib.rt_on_miss(a.st), 0)
            self.lib.rt_on_rx(a.st, self.packet_from(Board(self.lib), sf_presses=1), 16, None)
        self.assertEqual(a.cfg(), (10, 22))           # hearing anything restarts the count

    def test_long_lost_contact_returns_to_defaults(self):
        a, _ = self.committed(sf_presses=2, pwr_presses=2)   # SF9 / 10 dBm
        evs = [self.lib.rt_on_miss(a.st) for _ in range(EV_LOST_MISSES)]
        self.assertEqual(evs[:-1], [0]*(EV_LOST_MISSES - 1))
        self.assertTrue(evs[-1] & EV_FALLBACK)
        self.assertEqual(a.cfg(), (12, 22))

    def test_walking_out_of_range_falls_back_to_longest_reach(self):
        a, b = self.committed(sf_presses=3, pwr_presses=3)   # stepped down to SF7 / 0 dBm
        for board in (a, b):                                 # both lose contact
            evs = [self.lib.rt_on_miss(board.st) for _ in range(EV_LOST_MISSES)]
            self.assertTrue(evs[-1] & EV_FALLBACK)
        self.assertEqual((a.cfg(), b.cfg()), ((12, 22), (12, 22)))   # never weaker than where we started

    def test_restarted_board_adopts_peer_settings(self):
        a, b = self.committed(pwr_presses=1)        # SF12 / 14 dBm: a restart keeps the SF
        self.lib.rt_init(b.st)                      # b restarts at SF12 / 22 dBm
        _, ev, _ = self.send(a, b, kind=0)
        self.assertTrue(ev & EV_ADOPTED)
        self.assertEqual(b.cfg(), (12, 14))
        self.exchange(a, b)
        self.assertEqual(a.cfg(), b.cfg())

    def test_restart_at_different_sf_reconverges_at_defaults(self):
        a, b = self.committed(sf_presses=1, pwr_presses=3)   # SF10 / 0 dBm
        self.lib.rt_init(b.st)                      # b back at SF12: they cannot hear each other
        for _ in range(EV_LOST_MISSES):
            self.send(a, b, kind=0)                 # unheard
            self.lib.rt_on_miss(a.st)
        self.assertEqual(a.cfg(), (12, 22))
        self.exchange(b, a)
        self.exchange(a, b)
        self.assertEqual((a.cfg(), b.cfg()), ((12, 22), (12, 22)))

    def test_packets_report_sender_settings(self):
        a, _ = self.committed(sf_presses=3, pwr_presses=3)   # SF7 / 0 dBm
        buf = (ctypes.c_uint8*16)()
        self.lib.rt_build(a.st, 0, 1, -50, 5, buf)
        info = (ctypes.c_uint8*16)()
        self.lib.rt_on_rx(Board(self.lib).st, buf, 16, info)
        self.assertEqual(self.lib.rt_info_sf(info), 7)
        self.assertEqual(self.lib.rt_info_pwr(info), 0)

    def packet_from(self, board, sf_presses=0):
        """A packet sent by a board committed sf_presses steps down from SF12 (used to feed a plain reception)."""
        src, peer = self.committed(sf_presses=sf_presses)
        buf = (ctypes.c_uint8*16)()
        self.lib.rt_build(src.st, 0, 1, -50, 5, buf)
        return buf

    def test_presses_accumulate_and_wrap(self):
        a, b = Board(self.lib), Board(self.lib)
        for _ in range(2):
            self.lib.rt_press_sf(a.st)
        self.send(a, b, kind=0)
        self.send(b, a, kind=1)
        self.assertEqual((a.cfg(), b.cfg()), ((9, 22), (9, 22)))
        self.exchange(a, b)
        for _ in range(4):
            self.lib.rt_press_pwr(a.st)             # 22 -> 14 -> 10 -> 0 -> 22
        self.send(a, b, kind=0)
        self.send(b, a, kind=1)
        self.assertEqual(a.cfg(), (9, 22))

    def test_full_power_and_sf_ladders(self):
        a, b = Board(self.lib), Board(self.lib)
        seen = []
        for _ in range(4):
            self.lib.rt_press_sf(a.st)
            self.lib.rt_press_pwr(a.st)
            self.send(a, b, kind=0)
            self.send(b, a, kind=1)
            self.exchange(a, b)
            seen.append(a.cfg())
        self.assertEqual(seen, [(10, 14), (9, 10), (7, 0), (12, 22)])

    def test_new_proposal_after_many_changes_is_not_mistaken_for_old(self):
        a, b = Board(self.lib), Board(self.lib)
        for i in range(300):                        # generation counter wraps; must never be "no proposal"
            self.lib.rt_press_pwr(a.st)
            self.send(a, b, kind=0)
            self.send(b, a, kind=1)
            self.exchange(a, b)
            self.assertEqual(a.cfg(), b.cfg(), f'diverged at change {i}')


class LogParse(unittest.TestCase):
    """tools/rangetest_log.py against the firmware's console formats (TS_ON prefix included)."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
        import rangetest_log
        self.log = rangetest_log

    def test_rx_both_directions(self):
        row = self.log.parse('3862s157:#rt rx pong seq=41 rssi=-97 snr=-4 peer_rssi=-101 peer_snr=-6 sf=10 pwr=14')
        self.assertEqual((row['event'], row['sf'], row['pwr_dbm']), ('rx', 10, 14))
        self.assertEqual((row['up_rssi'], row['up_snr'], row['down_rssi'], row['down_snr']), (-97, -4, -101, -6))

    def test_first_packet_has_no_downlink_yet(self):
        row = self.log.parse('1s002:#rt rx ping seq=0 rssi=-20 snr=12 peer_rssi=-32768 peer_snr=0 sf=7 pwr=0')
        self.assertEqual((row['down_rssi'], row['down_snr']), ('', ''))

    def test_settings_marks_and_misses(self):
        self.assertEqual(self.log.parse('#rt cfg sf=9 pwr=22 rollback')['detail'], 'rollback')
        self.assertEqual(self.log.parse('5s1:#rt propose sf=12 pwr=0')['sf'], 12)
        self.assertEqual(self.log.parse('5s1:#rt mark 3')['detail'], '3')
        self.assertEqual(self.log.parse('5s1:#rt miss sf=7 pwr=0')['event'], 'miss')
        self.assertIsNone(self.log.parse('3866s691:Slave  Tx start'))

    def test_summary_announces_marks_proposals_and_settings(self):
        lines = []
        s = self.log.Summary(lines.append)
        for text in ('#rt mark 1', '#rt propose sf=9 pwr=0', '#rt cfg sf=9 pwr=0 switched'):
            row = self.log.parse(text)
            row['utc'] = '16:08:30.000'
            s.add(row)
        self.assertEqual(lines, ['16:08:30  MARK 1', '16:08:30  button: asking for SF9 / 0 dBm',
                                 '16:08:30  settings now SF9 / 0 dBm (switched)'])

    def test_peer_settings_and_persistent_mismatch_warning(self):
        line = '#rt rx ping seq=5 rssi=-14 snr=12 peer_rssi=-4 peer_snr=13 sf=7 pwr=10 peer_sf=7 peer_pwr=0'
        row = self.log.parse(line)
        self.assertEqual((row['peer_sf'], row['peer_pwr_dbm']), (7, 0))
        lines = []
        s = self.log.Summary(lines.append)
        for i in range(3):
            r = dict(row, utc='16:10:0%d.000' % i)
            s.add(r)
            self.assertEqual(any('MISMATCH' in x for x in lines), i == 2)   # one-packet handshake skew is normal
        s.add(dict(row, peer_pwr_dbm=10, utc='16:10:04.000'))
        s.add(dict(row, utc='16:10:05.000'))
        self.assertEqual(sum('MISMATCH' in x for x in lines), 1)            # warned once per episode

    def test_port_names_on_every_os_are_used_directly(self):
        for name in ('/dev/cu.usbmodem21303', '/dev/ttyACM0', 'COM3', 'com12'):
            self.assertEqual(self.log.find_port(name), name)

    def test_old_rx_lines_without_peer_settings_still_parse(self):
        row = self.log.parse('#rt rx ping seq=0 rssi=-20 snr=12 peer_rssi=-21 peer_snr=11 sf=7 pwr=0')
        self.assertEqual(row['peer_sf'], '')

    def test_summary_reports_link_loss_and_stays_quiet_when_steady(self):
        lines = []
        s = self.log.Summary(lines.append)
        rx = self.log.parse('#rt rx ping seq=1 rssi=-60 snr=9 peer_rssi=-62 peer_snr=8 sf=7 pwr=0')
        rx['utc'] = '16:00:00.000'
        for _ in range(8):
            s.add(dict(rx))
        s.tick(s.start + 10)
        self.assertEqual(len(lines), 1)                 # first window always reports
        for _ in range(8):
            s.add(dict(rx))
        s.tick(s.start + 10)
        self.assertEqual(len(lines), 1)                 # unchanged: quiet
        s.tick(s.start + 10)
        self.assertIn('NO LINK', lines[-1])
        n = len(lines)
        s.tick(s.start + 10)
        self.assertEqual(len(lines), n)                 # a continuing outage is reported once


if __name__ == '__main__':
    unittest.main()
