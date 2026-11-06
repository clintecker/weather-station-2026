"""The TX's bench screens (firmware/stage0-node/App/scr_view.c, scr_interludes.c, scr_rain.c, scr_art.c):
layout C, its packet banner and the seven interludes, drawn from a view and a frame number. Pure C, built for the host
by tools/scr_render.py (which also renders them to PNG for a look against the mockups). MATRIX is drawn in gray
(its glyphs each at their own ink), its glyphs from firmware/stage0-node/tools/make_scr_kana.py."""
import ctypes
import importlib.util
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
_spec = importlib.util.spec_from_file_location('make_scr_kana', ROOT/'firmware/stage0-node/tools/make_scr_kana.py')
kana = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kana)
COLS, ROWS, LEN_MIN, LEN_MAX = 21, 7, 4, 9   # App/scr_view.h SCR_MATRIX_*


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
        surf = render.Surf()
        self.lib.oled_text(ctypes.byref(surf), x, y, s.encode(), scale)
        return set(surf.levels())

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
        want = {'HOME': 1, 'BURST': 16, 'BANNER': 24, 'AIR': 8, 'PRESSURE': 8, 'POWER': 8, 'RADIO': 8, 'SCOPE': 64,
                'VANE': 64, 'RAIN': 64, 'SYSTEM': 64, 'BOOT': 64, 'HACK': 24, 'FORTUNE': 64, 'FROG': 64, 'MATRIX': 64,
                'PINBALL': 64}
        self.assertEqual({s: self.lib.scr_frames(i) for i, s in enumerate(render.SCREENS)}, want)

    def test_font_file_is_current(self):
        script = ROOT/'firmware/stage0-node/tools/make_scr_font.py'
        self.assertEqual(subprocess.run([sys.executable, script, '--check']).returncode, 0)

    def font(self, name):
        """The address of a font or style in the library (scr_big, oled_x1, ...)."""
        return ctypes.addressof(ctypes.c_char.in_dll(self.lib, name))

    def big(self, x, y, s):
        """The pixels of s in the big digits (oled_draw_text with scr_big) at (x, y), and the pen after it."""
        p, i = ctypes.c_void_p, ctypes.c_int
        self.lib.oled_draw_text.argtypes = [p, i, i, ctypes.c_char_p, p, p]
        surf = render.Surf()
        end = self.lib.oled_draw_text(ctypes.byref(surf), x, y, s.encode(), self.font('scr_big'), self.font('oled_x1'))
        return set(surf.levels()), end

    def big_width(self, s):
        self.lib.oled_text_w.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p]
        return self.lib.oled_text_w(s.encode(), self.font('scr_big'), self.font('oled_x1'))

    def test_big_digits(self):
        # A digit is 10 wide, the point 3, '-' 8, the degree sign 6, two pixels between; 16 tall; nothing for the rest.
        self.assertEqual([self.big_width(t) for t in ('8', '21.9', '-12.4^C', '', 'x?')], [10, 39, 69, 0, 0])
        lit, end = self.big(5, 3, '1')
        self.assertEqual(end, 17)   # the pen: the glyph and its gap
        self.assertEqual((min(y for _, y in lit), max(y for _, y in lit)), (3, 18))
        self.assertEqual(self.big(0, 0, '1x1')[0], self.big(0, 0, '11')[0])

    def right(self, y, s):
        """s ending at the screen's right edge."""
        return self.text(W - 6 * len(s) + 1, y, s)

    def big_right(self, s):
        return self.big(W - self.big_width(s), 1, s)[0]

    def test_home_rows(self):
        v = render.weather(render.demo_view(), 2190, 4600, 0)
        got = self.draw('HOME', 0, v)
        self.assertEqual(self.region(got, 48, 0, W, 40), self.big_right('21.9^C') | self.right(20, '46% RH') |
                         self.right(30, '983.0 hPa'))
        self.assertEqual(self.region(got, 0, 48, W, 56), self.text(0, 48, 'WIND calm  RAIN 0.0'))
        self.assertEqual(self.region(got, 0, 56, 112, H), self.text(0, 56, '#1233 ACK -41dBm'))   # the bars after

    def test_home_wind_rain_and_link_forms(self):
        v = render.demo_view()   # 1.3 m/s NE, 2 tips in the hour
        row6 = lambda v: self.region(self.draw('HOME', 0, v), 0, 48, W, 56)
        self.assertEqual(row6(v), self.text(0, 48, 'WIND 1.3 NE  RAIN 0.6'))
        v.wind.speed_cms, v.wind.point, v.rain.per_min[:] = 1234, 1, [9] * 60   # 12.3 NNE, 150.9 mm: the short form
        self.assertEqual(row6(v), self.text(0, 48, 'W 12.3 NNE R 150.9'))
        v.wind.point = -1   # out of the table: no point
        self.assertEqual(row6(v), self.text(0, 48, 'WIND 12.3  RAIN 150.9'))   # 21: the full form fits
        for acked, seq, rssi, line in ((render.SCR_TX_NONE, 0, 0, 'NO TX YET'), (render.SCR_TX_WAIT, 7, 0, '#7 SENT'),
                                       (render.SCR_TX_NO_ACK, 7, 0, '#7 NO ACK'),
                                       (render.SCR_TX_ACK, 12345678, -127, '#12345678 ACK -127'),
                                       (render.SCR_TX_ACK, 4294967295, -127, '#4294967295 ACK')):
            with self.subTest(line=line):
                v.last_acked, v.last_seq, v.ack_rssi = acked, seq, rssi
                self.assertEqual(self.region(self.draw('HOME', 0, v), 0, 56, 112, H), self.text(0, 56, line))

    def bars_lit(self, v):
        got = self.draw('HOME', 0, v)
        return [len(self.region(got, 113 + 5 * b, 56, 116 + 5 * b, 63)) > 3 for b in range(3)]

    def test_home_signal_bars(self):
        v = render.demo_view()
        for rssi, want in ((-41, 3), (-85, 3), (-86, 2), (-100, 2), (-101, 1), (-115, 1), (-116, 0)):
            v.ack_rssi = rssi
            self.assertEqual(self.bars_lit(v), [b < want for b in range(3)], rssi)
        v.last_acked = render.SCR_TX_NO_ACK
        self.assertEqual(self.bars_lit(v), [False] * 3)

    def test_home_absent_parts(self):
        v = render.demo_view()
        v.air_ok = v.press_ok = 0
        got = self.draw('HOME', 0, v)
        self.assertEqual(self.region(got, 48, 0, W, 40), self.big_right('--^C') | self.right(20, 'NO SHT45') |
                         self.right(30, 'NO BMP581'))

    def test_home_icons_animate(self):
        # Each icon's weather draws its own icon, which moves between frames 0 and 2 (its tick), not between 0 and 1
        # (HOME is redrawn every second step).
        icons = {}
        for name, v in render.home_views().items():
            if name in ('absent', 'noack'):
                continue
            f0 = self.region(self.draw('HOME', 0, v), 0, 0, 48, 44)
            self.assertTrue(f0, name)
            self.assertEqual(f0, self.region(self.draw('HOME', 1, v), 0, 0, 48, 44), name)
            self.assertNotEqual(f0, self.region(self.draw('HOME', 2, v), 0, 0, 48, 44), name)
            icons[name] = frozenset(f0)
        self.assertEqual(len(set(icons.values())), 6)

    def test_banner(self):
        # HOME with its bottom two rows inverted: the send, then the outcome.
        v = render.demo_view()
        v.last_seq = 1234
        bottom = lambda got: self.region(got, 0, 48, W, H)
        rows = lambda a, b: self.rows(['', '', '', '', '', '', a, b], (6, 7))
        self.assertEqual(bottom(self.draw('BANNER', 0, v)), rows('  SENDING TX 1234', '  ACK -41DBM SNR 13'))
        self.assertEqual(self.region(self.draw('BANNER', 0, v), 0, 0, W, 48), self.region(self.draw('HOME', 0, v), 0, 0, W, 48))
        v.last_acked = render.SCR_TX_WAIT
        self.assertEqual(bottom(self.draw('BANNER', 5, v)), rows('  SENDING TX 1234', ''))
        v.last_acked, v.extra_frames = render.SCR_TX_NO_ACK, 5
        self.assertEqual(bottom(self.draw('BANNER', 23, v)), rows('  TX 1234 +5 BACKLOG', '  NO ACK'))
        # The widest outcome the radio gives (SX126x packet RSSI down to -127 dBm, SNR down to -32 dB) fills the
        # 21 columns exactly: the unit is dBm, and nothing is cut.
        v.last_acked, v.extra_frames, v.ack_rssi, v.ack_snr = render.SCR_TX_ACK, 0, -127, -32
        line = '  ACK -127DBM SNR -32'
        self.assertEqual(len(line), 21)
        self.assertEqual(bottom(self.draw('BANNER', 0, v)), rows('  SENDING TX 1234', line))

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
        # 21 columns: a 5-digit sequence and a 2-digit backlog are shortened, not cut.
        v = render.demo_view()
        v.last_seq, v.extra_frames, v.reports = 12345, 12, 0
        self.assertEqual(self.banner_row(v), self.text(0, 48, '  TX 12345 +12 BKLG'))
        v.last_seq, v.extra_frames, v.reports = 4294967295, 65535, 1   # the widest: drawn as far as it goes
        self.assertTrue(self.banner_row(v))

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
        hi.rain.tips, hi.rain.last_age_s, hi.rain.per_min[:] = 2**32 - 1, render.RAIN_AGE_MAX_S, [255] * 60
        lo.rain.tips, lo.rain.last_age_s = 0, render.RAIN_AGE_NONE
        # The histories: full of their extremes, and counts of 255 past their capacity.
        for v, val in ((hi, 32767), (lo, -32767)):
            v.air.s[:], v.press.s[:] = [val] * 60, [val] * 36
            v.radio.rssi[:], v.radio.snr[:] = [val] * 30, [val] * 30
        lo.air.n, lo.press.n, lo.radio.n = 60, 36, 30
        hi.air.n = hi.press.n = hi.radio.n = 255
        lo.air.s[7] = lo.press.s[0] = lo.radio.rssi[3] = lo.radio.snr[3] = render.SCR_GAP
        lo.utc, lo.since_exchange_s = 0, render.SCR_NONE_S
        lo.power.charger, hi.power.charger = 0, 0xFF
        for r in hi.power.rail:
            r.fitted, r.ok, r.ma_x100, r.mv = 1, 1, 2**31 - 1, 2**31 - 1
        for r in lo.power.rail:
            r.fitted, r.ok, r.ma_x100, r.mv = 1, 1, -2**31, -2**31
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


    # The rain screen (scr_rain.c): mm and tips since boot, the last tip's age, the rate of the last 10
    # minutes, and a bar a minute for the last hour.
    def rain_text(self, got):
        """The pixels of its text rows: the top three and the bottom one."""
        return self.region(got, 0, 0, W, 24) | self.region(got, 0, 56, W, H)

    def rain_rows(self, *rows):
        return self.rows([*rows, '', '', '', '', '-60m     4/m      now'])   # the scale centred on the row

    def test_rain_rows(self):
        self.assertEqual(self.rain_text(self.draw('RAIN')), self.rain_rows(
            'RAIN          0.56 mm', '2 tips    last 4m ago', 'RATE  1.7 mm/h (10m)'))
        dry = render.rain_views()['dry']
        self.assertEqual(self.rain_text(self.draw('RAIN', 0, dry)), self.rain_rows(
            'RAIN          0.00 mm', '0 tips        last --', 'RATE  0.0 mm/h (10m)'))

    def test_rain_age_and_count_forms(self):
        # The age right-aligned, in a shorter form when the count leaves no room: "last X ago", "last X", "X".
        for tips, age, left, right in ((1, 45, '1 tip', 'last 45s ago'), (3, 100, '3 tips', 'last 1m ago'),
                                       (3, 7200, '3 tips', 'last 2h ago'), (12345, 99 * 3600, '12345 tips', 'last 99h'),
                                       (2**32 - 1, render.RAIN_AGE_MAX_S, '4294967295 tips', '99h')):
            with self.subTest(tips=tips, age=age):
                v = render.rain(render.demo_view(), tips, age, {})
                want = left + right.rjust(21 - len(left))
                self.assertEqual(self.region(self.draw('RAIN', 0, v), 0, 8, W, 16), self.text(0, 8, want))

    def test_rain_rate(self):
        rate = self.lib.scr_rain_rate_umh
        rate.argtypes, rate.restype = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint, ctypes.c_uint], ctypes.c_uint32
        mins = lambda xs: (ctypes.c_uint8 * len(xs))(*xs)
        self.assertEqual(rate(mins([0] * 60), 60, 10), 0)
        self.assertEqual(rate(mins([9] * 50 + [1] + [0] * 9), 60, 10), 1676)        # 0.2794 mm in 10 min: 1.6764 mm/h
        self.assertEqual(rate(mins([1] * 60), 60, 10), 16764)
        self.assertEqual(rate(mins([1] * 60), 60, 60), 16764)
        self.assertEqual(rate(mins([2] * 5), 5, 10), 16764)                         # fewer minutes than asked: the rest none
        self.assertEqual(rate(mins([255] * 60), 60, 10), 4274820)
        self.assertEqual(rate(mins([1]), 1, 0), 0)
        v = render.rain(render.demo_view(), 97, 0, {i: 9 for i in range(50, 60)})   # 150.9 mm/h: one space after RATE
        self.assertEqual(self.region(self.draw('RAIN', 0, v), 0, 16, W, 24), self.text(0, 16, 'RATE 150.9 mm/h (10m)'))
        v = render.rain(render.demo_view(), 2550, 0, {i: 255 for i in range(60)})   # too wide for the window's name
        self.assertEqual(self.region(self.draw('RAIN', 0, v), 0, 16, W, 24), self.text(0, 16, 'RATE  4274.8 mm/h'))

    def test_rain_bar_scale(self):
        px = self.lib.scr_bar_px
        px.argtypes, px.restype = [ctypes.c_int32, ctypes.c_int32, ctypes.c_uint], ctypes.c_uint
        self.assertEqual([px(c, 4, 26) for c in (0, 1, 2, 4, 5)], [0, 7, 13, 26, 26])
        self.assertEqual(px(1, 255, 26), 1)                                          # one tip is always a bar
        self.assertEqual(px(254, 255, 26), 26)
        self.assertEqual(px(3, 0, 26), 26)
        steps = self.lib.scr_scale_steps
        steps.argtypes, steps.restype = [ctypes.c_uint] * 3, ctypes.c_uint
        self.assertEqual([steps(n, 4, 256) for n in (0, 1, 4, 5, 8, 9, 40, 64, 65, 200, 255, 1000)],
                         [4, 4, 4, 8, 8, 16, 64, 64, 128, 256, 256, 256])   # steps, never creeps

    def bars(self, per_min):
        """Each minute's lit column heights inside the plot (x 4 + 2 i and the next, y 28 to 51)."""
        got = self.draw('RAIN', 0, render.rain(render.demo_view(), 99, 0, per_min))
        heights = []
        for i in range(60):
            cols = [len(self.region(got, x, 28, x + 1, 52)) for x in (4 + 2 * i, 5 + 2 * i)]
            self.assertEqual(cols[0], cols[1], i)
            heights.append(cols[0])
        return heights, got

    def test_rain_bars(self):
        heights, got = self.bars({59: 4, 0: 1})                # the floor of the scale: 4 tips a minute
        self.assertEqual(heights, [6] + [0] * 58 + [24])
        self.assertTrue({(x, 52) for x in range(2, 126)} <= got)   # the axis
        self.assertTrue({(2, y) for y in range(26, 53)} | {(125, y) for y in range(26, 53)} <= got)
        self.assertTrue({(x, 26) for x in range(2, 126, 2)} <= got)              # the dotted ceiling
        self.assertFalse({(x, 26) for x in range(3, 125, 2)} & got)
        self.assertFalse({(x, 27) for x in range(3, 125)} & got)                 # a pixel under it, always dark
        self.assertEqual(self.region(got, 0, 56, W, 64), self.text(0, 56, '-60m     4/m      now'))
        heights, got = self.bars({59: 40, 58: 1, 30: 20})      # the step that holds the largest: 64
        self.assertEqual((heights[59], heights[58], heights[30], sum(heights)), (15, 1, 8, 24))
        self.assertEqual(self.region(got, 0, 56, W, 64), self.text(0, 56, '-60m    64/m      now'))
        heights, got = self.bars({59: 255})                    # a saturated minute: full height, no further
        self.assertEqual(heights[59], 24)
        self.assertEqual(self.region(got, 0, 56, W, 64), self.text(0, 56, '-60m    256/m     now'))
        heights, _ = self.bars({})
        self.assertEqual(heights, [0] * 60)

    # ---- the digital rain ----

    def stream(self, c, s, frame, speed):
        head, length = ctypes.c_int(), ctypes.c_uint()
        self.lib.scr_matrix_stream.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
        if not self.lib.scr_matrix_stream(c, s, frame, speed, ctypes.byref(head), ctypes.byref(length)):
            return None
        return head.value, length.value

    def level(self, c, r, frame, speed):
        self.lib.scr_matrix_level.argtypes = [ctypes.c_uint] * 4
        self.lib.scr_matrix_level.restype = ctypes.c_uint
        return self.lib.scr_matrix_level(c, r, frame, speed)

    def test_kana_file_is_current(self):
        script = ROOT/'firmware/stage0-node/tools/make_scr_kana.py'
        self.assertEqual(subprocess.run([sys.executable, script, '--check']).returncode, 0)

    def test_kana_table(self):
        # 45 katakana-style glyphs and the 10 digits, all different, each in the table mirrored left to right.
        names = list(kana.GLYPHS)
        font = render.Font.in_dll(self.lib, 'scr_kana')
        n = font.n
        self.assertEqual((font.h, font.w, font.bits, font.gap, font.chars, font.widths), (7, 5, 8, 1, None, None))
        table = (ctypes.c_uint8 * 7 * n).from_address(font.rows)
        self.assertEqual((n, sum(1 for k in names if not k.isdigit()), sum(1 for k in names if k.isdigit())), (55, 45, 10))
        for i, name in enumerate(names):
            reads = kana.rows(kana.GLYPHS[name], mirror=False)
            self.assertEqual(list(table[i]), [int(f'{r:05b}'[::-1], 2) for r in reads], name)
        self.assertEqual(len({tuple(table[i]) for i in range(n)}), n)
        self.assertNotEqual(list(table[names.index('a')]), kana.rows(kana.GLYPHS['a'], mirror=False))

    def test_matrix_fade(self):
        # The head at 15, the glyph behind it 10, falling to 1 at the tail, never rising; dark off the trail.
        self.lib.scr_matrix_fade.argtypes = [ctypes.c_int, ctypes.c_uint]
        self.lib.scr_matrix_fade.restype = ctypes.c_uint
        for length in range(LEN_MIN, LEN_MAX + 1):
            trail = [self.lib.scr_matrix_fade(d, length) for d in range(-1, length + 1)]
            self.assertEqual((trail[0], trail[1], trail[2], trail[-2], trail[-1]), (0, 15, 10, 1, 0), length)
            self.assertEqual(trail[2:-1], sorted(trail[2:-1], reverse=True), length)

    def test_matrix_streams(self):
        # Every column has a stream, about half a second; the same arguments give the same stream; lengths
        # stay in range; a head moves down, never up, within a cycle, and further each frame with more rain.
        seconds = [c for c in range(COLS) if self.stream(c, 1, 0, 1) is not None]
        self.assertTrue(all(self.stream(c, 0, 0, 1) is not None for c in range(COLS)))
        self.assertTrue(5 <= len(seconds) <= 16, seconds)
        self.assertIsNone(self.stream(0, 2, 0, 1))
        self.assertEqual(self.stream(7, 0, 33, 2), self.stream(7, 0, 33, 2))
        for speed in (1, 2, 3):
            for c in range(COLS):
                prev = None
                for f in range(64):
                    st = self.stream(c, 0, f, speed)
                    self.assertTrue(LEN_MIN <= st[1] <= LEN_MAX, (c, f, st))
                    self.assertTrue(-10 <= st[0] < ROWS + LEN_MAX + 10, (c, f, st))   # its delay, the screen, its trail
                    if prev is not None and st[0] >= prev[0]:
                        self.assertLessEqual(st[0] - prev[0], 3, (c, f))   # at most 2.5 glyphs a frame
                    prev = st
        dry = sum(abs(self.stream(c, 0, 9, 1)[0] - self.stream(c, 0, 8, 1)[0]) for c in range(COLS))
        wet = sum(abs(self.stream(c, 0, 9, 3)[0] - self.stream(c, 0, 8, 3)[0]) for c in range(COLS))
        self.assertGreater(wet, dry)

    def test_matrix_restarts_dark(self):
        # A cycle ends with its trail off the screen: no glyph jumps from a trail to a new head's delay.
        for c in range(COLS):
            for f in range(1, 400):
                a, b = self.stream(c, 0, f - 1, 1), self.stream(c, 0, f, 1)
                if b[0] < a[0]:   # a new cycle
                    self.assertGreaterEqual(a[0] - (a[1] - 1), ROWS - 2, (c, f, a))   # within a frame's fall

    def drawn(self, screen, frame, v, rot180=0, dirty=False):
        """{(x, y): level} of what scr_draw draws on a surface (turned or not, cleared or full of junk)."""
        surf = render.Surf(rot180)
        if dirty:
            ctypes.memset(surf.buf, 0x55, render.FRAME_BYTES)
        self.lib.scr_draw(ctypes.byref(surf), render.SCREENS.index(screen), frame, ctypes.byref(v))
        return surf.levels()

    def test_matrix_gray_frame(self):
        # The glyphs sit on the 6 x 8 grid at their cells' levels, the head's glyph at 15, the footer dim;
        # the frame turned is the same picture turned; scr_draw clears first; the other screens are all 15.
        v = render.demo_view()
        for frame in (0, 5, 40):
            got = self.drawn('MATRIX', frame, v)
            self.assertEqual(got, self.drawn('MATRIX', frame, v, rot180=1))   # drawn turned, turned back
            self.assertEqual(got, self.drawn('MATRIX', frame, v, dirty=True))
            self.assertEqual({p: lv for p, lv in got.items() if p[1] >= 56}, dict.fromkeys(self.text(0, 57, 'TIPS 1/10m   SPEED x2'), 3))
            heads = 0
            for c in range(COLS):
                for r in range(ROWS):
                    cell = {lv for (x, y), lv in got.items() if 6 * c + 1 <= x < 6 * c + 6 and 8 * r <= y < 8 * r + 7}
                    want = self.level(c, r, frame, 2)
                    self.assertEqual(cell, {want} if want else set(), (frame, c, r))
                    heads += want == 15
            self.assertGreater(heads, 2)
            self.assertFalse({(x, y) for x, y in got if y < 56 and (x % 6 == 0 or y % 8 == 7)})   # the gaps
        for screen in render.SCREENS:
            if screen != 'MATRIX':
                self.assertEqual(set(self.drawn(screen, 7, v).values()), {15}, screen)
        self.assertEqual(self.drawn('MATRIX', 99, v), self.drawn('MATRIX', 63, v))
        self.assertEqual(self.missing.value, 0)

    def test_matrix_glyphs_change_now_and_then(self):
        # A trail's glyph holds for frames at a time; the head's changes every frame, mostly.
        self.lib.scr_matrix_glyph.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int]
        g = self.lib.scr_matrix_glyph
        trail = sum(g(c, r, f, 0) != g(c, r, f + 1, 0) for c in range(COLS) for r in range(ROWS) for f in range(64))
        head = sum(g(c, r, f, 1) != g(c, r, f + 1, 1) for c in range(COLS) for r in range(ROWS) for f in range(64))
        cells = COLS * ROWS * 64
        self.assertTrue(cells // 50 < trail < cells // 5, trail)
        self.assertGreater(head, cells * 9 // 10)
        self.assertTrue(all(g(c, r, f, h) < 55 for c in range(COLS) for r in range(ROWS) for f in (0, 63) for h in (0, 1)))

if __name__ == '__main__':
    unittest.main()
