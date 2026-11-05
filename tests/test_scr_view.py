"""The TX's bench screens (firmware/stage0-node/App/scr_view.c, scr_interludes.c, scr_art.c): layout C,
its packet banner and the six interludes, drawn from a view and a frame number. Pure C, built for the host
by tools/scr_render.py (which also renders them to PNG for a look against the mockups)."""
import ctypes
import subprocess
import sys
import tempfile
import unittest
try:
    from toolchain import ROOT, load_tool, needs_cc   # discover -s tests
except ImportError:
    from tests.toolchain import ROOT, load_tool, needs_cc

render = load_tool('scr_render')
W, H = render.W, render.H


@needs_cc
class ScrView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        cls.lib = render.build(tmp.name)
        cls.missing = ctypes.c_uint.in_dll(cls.lib, 'shim_missing')
        cls.missing_text = (ctypes.c_char * 64).in_dll(cls.lib, 'shim_missing_text')

    def draw(self, screen, frame=0, view=None):
        return render.draw(self.lib, screen, frame, view if view is not None else render.demo_view())

    def text(self, x, y, s, scale=1):
        fb = ctypes.create_string_buffer(W * H // 8)
        self.lib.oled_text(fb, x, y, s.encode(), scale)
        return {(px, py) for py in range(H) for px in range(W) if self.lib.oled_get(fb, px, py)}

    def rows(self, rows, inverted=()):
        """The pixels of up to 8 text rows at y = 8 i; rows in `inverted` lit behind dark text."""
        want = set()
        for i, s in enumerate(rows):
            lit = self.text(0, 8 * i, s)
            if i in inverted:
                lit = {(x, y) for y in range(8 * i, 8 * i + 8) for x in range(W)} - lit
            want |= lit
        return want

    @staticmethod
    def region(pixels, x0, y0, x1, y1):
        return {(x, y) for x, y in pixels if x0 <= x < x1 and y0 <= y < y1}

    def test_check_view_layout(self):
        self.assertEqual(self.lib.shim_view_size(), ctypes.sizeof(render.View))

    def test_art_file_is_current(self):
        script = ROOT/'firmware/stage0-node/tools/make_scr_art.py'
        self.assertEqual(subprocess.run([sys.executable, script, '--check']).returncode, 0)

    def test_frames(self):
        want = {'NORMAL': 1, 'BURST': 16, 'BANNER': 24, 'SCOPE': 64, 'VANE': 64, 'SYSTEM': 64, 'BOOT': 64, 'HACK': 24}
        self.assertEqual({s: self.lib.scr_frames(i) for i, s in enumerate(render.SCREENS)}, want)

    def test_normal_rows(self):
        self.assertEqual(self.draw('NORMAL'), self.rows([
            'AIR  23.1C  50.8%', 'BOX  22.9C  52.2%', 'P 983.0hPa   UV 0', 'WIND 1.3m/s NE G2.7',
            'RAIN 2 TIPS 0.56mm', 'BATT +37.6mA 3.85V', 'CELL 3.85V 78% CHG', 'TX 1233 ACK 58s AGO']))

    def test_absent_parts(self):
        v = render.demo_view()
        v.air_ok = v.box_ok = v.press_ok = v.uv_ok = 0
        v.power.batt_ok = v.power.gauge_ok = 0
        got = self.draw('NORMAL', 0, v)
        for i, s in ((0, 'AIR NO SHT45'), (1, 'BOX NO SHTC3'), (2, 'P NO BMP581 UV NO'), (5, 'BATT NO INA228'),
                     (6, 'CELL NO MAX17048')):
            self.assertEqual(self.region(got, 0, 8 * i, W, 8 * i + 8), self.text(0, 8 * i, s), s)

    def test_values_round_and_sign(self):
        v = render.demo_view()
        v.air_c, v.air_rh, v.press_dhpa, v.uv_ok, v.uv_counts = -1235, 10000, 10132, 0, 0
        v.power.batt_ma_x100, v.power.out_mv, v.power.charging = -4, 0, 0
        v.wind.point, v.last_acked, v.last_age_s = -1, render.SCR_TX_NO_ACK, 600
        got = self.draw('NORMAL', 0, v)
        for i, s in ((0, 'AIR  -12.4C  100.0%'), (2, 'P 1013.2hPa  UV NO'), (3, 'WIND 1.3m/s - G2.7'),
                     (5, 'BATT +0.0mA'), (6, 'CELL 3.85V 78%'), (7, 'TX 1233 NO ACK 10m')):   # no room for AGO
            self.assertEqual(self.region(got, 0, 8 * i, W, 8 * i + 8), self.text(0, 8 * i, s), s)

    def test_nothing_sent_yet(self):
        v = render.demo_view()
        v.last_acked = render.SCR_TX_NONE
        self.assertEqual(self.region(self.draw('NORMAL', 0, v), 0, 56, W, H), self.text(0, 56, 'TX NONE YET'))

    def test_banner(self):
        v = render.demo_view()
        v.last_seq = 1234
        top = ['AIR  23.1C  50.8%', 'BOX  22.9C  52.2%', 'P 983.0hPa   UV 0', 'WIND 1.3m/s NE G2.7',
               'RAIN 2 TIPS 0.56mm', 'BATT +37.6mA 3.85V']
        self.assertEqual(self.draw('BANNER', 0, v), self.rows(top + ['  SENDING TX 1234', '  ACK -41DBM SNR 13'], (6, 7)))
        v.last_acked = render.SCR_TX_WAIT
        self.assertEqual(self.draw('BANNER', 5, v), self.rows(top + ['  SENDING TX 1234', ''], (6, 7)))
        v.last_acked, v.extra_frames = render.SCR_TX_NO_ACK, 5
        self.assertEqual(self.draw('BANNER', 23, v), self.rows(top + ['  TX 1234 +5 BACKLOG', '  NO ACK'], (6, 7)))
        # The widest outcome the radio gives (SX126x packet RSSI down to -127 dBm, SNR down to -32 dB) fills the
        # 21 columns exactly: the unit is dBm, and nothing is cut.
        v.last_acked, v.extra_frames, v.ack_rssi, v.ack_snr = render.SCR_TX_ACK, 0, -127, -32
        line = '  ACK -127DBM SNR -32'
        self.assertEqual(len(line), 21)
        self.assertEqual(self.draw('BANNER', 0, v), self.rows(top + ['  SENDING TX 1234', line], (6, 7)))

    def banner_row(self, v):
        """The banner's first row, as drawn (inverted back to lit text)."""
        got = self.region(self.draw('BANNER', 0, v), 0, 48, W, 56)
        return {(x, y) for y in range(48, 56) for x in range(W)} - got

    def test_a_health_report_is_not_backlog(self):
        # The health report follows the live frame too, but nothing came from the backlog: +HEALTH, not +1 BACKLOG.
        v = render.demo_view()
        v.last_seq, v.extra_frames, v.reports = 1234, 0, 1
        self.assertEqual(self.banner_row(v), self.text(0, 48, '  TX 1234 +HEALTH'))
        v.extra_frames = 5   # both: the short words, then without the indent, to fit 21 columns
        self.assertEqual(self.banner_row(v), self.text(0, 48, 'TX 1234 +5 BKLG +HLTH'))

    def test_rows_that_would_overflow_take_a_shorter_form(self):
        # 21 columns: a 5-digit sequence and a 2-digit backlog, a 22-character wind row, are shortened, not cut.
        v = render.demo_view()
        v.last_seq, v.extra_frames, v.reports = 12345, 12, 0
        self.assertEqual(self.banner_row(v), self.text(0, 48, '  TX 12345 +12 BKLG'))
        v.last_seq, v.extra_frames, v.reports = 4294967295, 65535, 1   # the widest: drawn as far as it goes
        self.assertTrue(self.banner_row(v))
        v.wind.speed_cms, v.wind.gust_cms, v.wind.point = 1234, 2340, 1
        self.assertEqual(self.region(self.draw('NORMAL', 0, v), 0, 24, W, 32), self.text(0, 24, 'WND 12.3m/s NNE G23.4'))
        v.wind.point = 2   # a 2-letter point fits as it was
        self.assertEqual(self.region(self.draw('NORMAL', 0, v), 0, 24, W, 32), self.text(0, 24, 'WIND 12.3m/s NE G23.4'))

    def extreme_views(self):
        """Every field at its ends, the parts absent and present, each outcome."""
        lo, hi = render.demo_view(), render.demo_view()
        for name, kind in render.View._fields_:
            if kind in (ctypes.c_int32, ctypes.c_int16, ctypes.c_int8):
                bits = ctypes.sizeof(kind) * 8
                setattr(lo, name, -(1 << (bits - 1)))
                setattr(hi, name, (1 << (bits - 1)) - 1)
            elif kind in (ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint):
                setattr(lo, name, 0)
                setattr(hi, name, (1 << (ctypes.sizeof(kind) * 8)) - 1)
        lo.cipher_len, hi.cipher_len = 0, 96
        lo.wind.nbins, hi.wind.nbins, lo.wind.point, hi.wind.point = 0, 120, -1, 15
        hi.wind.speed_cms = hi.wind.gust_cms = hi.wind.vane_mv = 0xFFFF
        hi.wind.bins[:] = [255] * 120
        hi.power.batt_ma_x100, hi.power.out_mv, hi.power.vcell_mv, hi.power.soc_pct_x10 = 2**31 - 1, 2**31 - 1, 0xFFFF, 0xFFFF
        lo.power.batt_ma_x100, lo.power.out_mv = -2**31, -2**31
        lo.power.batt_ok = lo.power.gauge_ok = lo.power.charging = 1
        absent = render.demo_view()
        absent.air_ok = absent.box_ok = absent.press_ok = absent.uv_ok = absent.key_ok = 0
        absent.power.batt_ok = absent.power.gauge_ok = 0
        views = [lo, hi, absent, render.demo_view()]
        for outcome in (render.SCR_TX_NONE, render.SCR_TX_WAIT, render.SCR_TX_NO_ACK, render.SCR_TX_ACK):
            for base in (lo, hi):
                v = render.View.from_buffer_copy(base)
                v.last_acked = outcome
                views.append(v)
        return views

    def test_every_string_in_font(self):
        for v in self.extreme_views():
            for i, screen in enumerate(render.SCREENS):
                for frame in range(self.lib.scr_frames(i) + 1):   # and one past the end
                    self.missing.value = 0
                    self.draw(screen, frame, v)
                    self.assertEqual(self.missing.value, 0, (screen, frame, self.missing_text.value))

    def test_burst_shows_cipher_hex(self):
        got = self.draw('BURST', 8)
        self.assertEqual(self.region(got, 0, 35, 8 * 6, 42), self.text(0, 35, 'A4 C1 23'))
        self.assertEqual(self.region(got, 0, 0, W, 8),
                         {(x, y) for y in range(8) for x in range(W)} - self.text(0, 0, 'TX 1233 SF7 BW500'))
        self.assertEqual(self.region(got, 0, 56, W, H), self.text(0, 56, 'AES-CCM 77B 915.0MHz'))
        self.assertFalse(self.region(self.draw('BURST', 7), 0, 35, W, 52))   # the chirps first, then the bytes

    def test_hack_sequence(self):
        right = lambda p: self.region(p, 64, 0, W, H)
        f0 = self.draw('HACK', 0)
        self.assertEqual(right(f0), self.text(68, 2, 'HACK', 2))
        f12 = self.draw('HACK', 12)
        self.assertEqual(self.region(f12, 64, 0, W, 40), self.text(68, 2, 'HACK', 2) | self.text(74, 21, 'THE', 2))
        self.assertGreater(len(self.region(f12, 64, 42, W, 56)), 100)                     # PLANET
        self.assertIn((20, 21), f0)                                                      # the open eye
        f16 = self.draw('HACK', 16)
        self.assertNotIn((20, 21), f16)                                                  # the wink
        self.assertTrue({(x, 24) for x in range(16, 25)} <= f16)
        self.assertNotIn((39, 21), self.draw('HACK', 18))                                # the glint
        self.assertIn((39, 21), f12)
        base, f21 = self.draw('HACK', 15), self.draw('HACK', 21)
        shifted = [y for y in range(H) for d in range(-8, 9) if d and
                   {(x, yy) for x, yy in f21 if yy == y} == {(x + d, y) for x, yy in base if yy == y and 0 <= x + d < W}
                   and any(yy == y for _, yy in base)]
        self.assertTrue(shifted)

    def test_scope_plots_bins(self):
        v = render.demo_view()
        v.wind.nbins, v.wind.bins[:16] = 16, list(range(16))
        empty = render.demo_view()
        empty.wind.nbins = 0
        trace = self.region(self.draw('SCOPE', 0, v) - self.draw('SCOPE', 0, empty), 1, 10, W - 1, 54)
        xs = sorted({x for x, _ in trace})
        top = lambda col: min(y for x, y in trace if x == col)
        self.assertLess(top(xs[-1]), top(xs[0]))
        self.assertEqual(xs[-1], 126)                                    # the newest bin on the right edge


if __name__ == '__main__':
    unittest.main()
