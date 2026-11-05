"""The bench screens' arithmetic and choices (firmware/stage0-node/App/scr_calc.c): the display's histories, the
dew point, the pressure tendency, HOME's icon, the scales, the fortune cookie and the frog. Pure C, built for the
host by tools/scr_render.py."""
import ctypes
import math
import tempfile
import unittest
try:
    from toolchain import load_tool, needs_cc   # discover -s tests
except ImportError:
    from tests.toolchain import load_tool, needs_cc

render = load_tool('scr_render')
GAP = render.SCR_GAP
I16 = ctypes.c_int16


@needs_cc
class ScrCalc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        lib = cls.lib = render.build(tmp.name)
        V = ctypes.POINTER(render.View)
        sigs = {'scr_hist_push': ([ctypes.POINTER(I16), ctypes.c_uint, ctypes.c_uint, I16], ctypes.c_uint),
                'scr_hist_value': ([ctypes.c_int32], I16),
                'scr_hist_due': ([ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32], ctypes.c_int),
                'scr_ln_q16': ([ctypes.c_uint32], ctypes.c_int32),
                'scr_dew_point': ([ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)], ctypes.c_int),
                'scr_tendency': ([V, ctypes.POINTER(ctypes.c_int32)], ctypes.c_int),
                'scr_is_day': ([ctypes.c_uint32, ctypes.c_int32], ctypes.c_int),
                'scr_rain_tips': ([ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint, ctypes.c_uint], ctypes.c_uint),
                'scr_icon_pick': ([V], ctypes.c_int),
                'scr_bar_px': ([ctypes.c_int32, ctypes.c_int32, ctypes.c_uint], ctypes.c_uint),
                'scr_spark_range': ([ctypes.POINTER(I16), ctypes.c_uint, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32),
                                     ctypes.POINTER(ctypes.c_int32)], ctypes.c_uint),
                'scr_spark_y': ([ctypes.c_int32] * 3 + [ctypes.c_int] * 2, ctypes.c_int),
                'scr_signal_bars': ([I16], ctypes.c_uint),
                'scr_acks': ([ctypes.POINTER(I16), ctypes.c_uint], ctypes.c_uint),
                'scr_next_tx_s': ([ctypes.c_uint32], ctypes.c_int32),
                'scr_fortune_pick': ([V], ctypes.c_uint),
                'scr_frog_mood': ([V], ctypes.c_int),
                'scr_matrix_speed': ([ctypes.c_uint], ctypes.c_uint)}
        for name, (args, res) in sigs.items():
            f = getattr(lib, name)
            f.argtypes, f.restype = args, res

    def fortune(self, i):
        arr = (ctypes.c_char_p * 15).in_dll(self.lib, 'scr_fortunes')
        return arr[i].decode()

    # ---- the histories ----

    def test_hist_push_fills_then_drops_the_oldest(self):
        s = (I16 * 4)()
        n = 0
        for v in (10, 20, 30, 40):
            n = self.lib.scr_hist_push(s, 4, n, v)
        self.assertEqual((n, list(s)), (4, [10, 20, 30, 40]))
        n = self.lib.scr_hist_push(s, 4, n, GAP)   # a gap is a sample too
        self.assertEqual((n, list(s)), (4, [20, 30, 40, GAP]))
        self.assertEqual(self.lib.scr_hist_push(s, 4, 200, 7), 4)   # a count past the capacity: as full
        self.assertEqual(list(s), [30, 40, GAP, 7])
        self.assertEqual(self.lib.scr_hist_push(s, 0, 0, 1), 0)

    def test_hist_value_is_never_a_gap(self):
        self.assertEqual([self.lib.scr_hist_value(v) for v in (0, -1234, 40000, -40000, -32768, -32767)],
                         [0, -1234, 32767, -32767, -32767, -32767])

    def test_hist_due(self):
        at = ctypes.c_uint32(1000)
        due = lambda now: (self.lib.scr_hist_due(now, ctypes.byref(at), 60000), at.value)
        self.assertEqual(due(999), (0, 1000))
        self.assertEqual(due(1000), (1, 61000))
        self.assertEqual(due(61100), (1, 121000))            # on the phase, not 60 s after the late step
        self.assertEqual(due(500000), (1, 560000))           # far behind: from now, no burst
        self.assertEqual(due(500100), (0, 560000))
        at.value = 0xFFFFFFF0
        self.assertEqual(due(5), (1, (0xFFFFFFF0 + 60000) & 0xFFFFFFFF))   # across the wrap

    # ---- the weather ----

    def test_ln(self):
        for n in (1, 2, 3, 7, 100, 4999, 5000, 10000, 65535, 1 << 20, 2**32 - 1):
            self.assertAlmostEqual(self.lib.scr_ln_q16(n) / 65536, math.log(n), delta=3 / 65536, msg=n)
        self.assertEqual(self.lib.scr_ln_q16(0), 0)

    @staticmethod
    def magnus(c, rh):
        g = math.log(rh / 100) + 17.62 * c / (243.12 + c)
        return 243.12 * g / (17.62 - g)

    def dew(self, centi_c, centi_rh):
        out = ctypes.c_int32()
        ok = self.lib.scr_dew_point(centi_c, centi_rh, ctypes.byref(out))
        return out.value if ok else None

    def test_dew_point_is_magnus(self):
        for c in (-4000, -1000, -1, 0, 1234, 2314, 3500, 5000):
            for rh in (100, 1000, 3333, 5080, 8500, 9999, 10000):
                self.assertAlmostEqual(self.dew(c, rh) / 100, self.magnus(c / 100, rh / 100), delta=0.02, msg=(c, rh))
        self.assertEqual(self.dew(2314, 10000), 2314)                     # saturated: the air's own temperature
        self.assertEqual(self.dew(2314, 12000), 2314)                     # past 100 %: as 100 %
        self.assertIsNone(self.dew(2314, 0))
        self.assertIsNone(self.dew(2314, -5))
        self.assertIsNone(self.dew(-20000, 5000))
        self.assertIsNotNone(self.dew(2**31 - 1, 2**31 - 1))              # no overflow at the ends
        self.assertIsNotNone(self.dew(-19999, 1))

    def press_view(self, now, oldest, n=36, ok=1):
        v = render.demo_view()
        render.history(v, 'press', [oldest] + [9900] * (n - 1))
        v.press_dhpa, v.press_ok = now, ok
        return v

    def tendency(self, v):
        d = ctypes.c_int32()
        return ['NONE', 'FALLING', 'STEADY', 'RISING'][self.lib.scr_tendency(ctypes.byref(v), ctypes.byref(d))], d.value

    def test_tendency_thresholds(self):
        # The live value against the oldest of a full 3-hour history: +-1.0 hPa is the edge.
        for now, want in ((9910, ('RISING', 10)), (9909, ('STEADY', 9)), (9891, ('STEADY', -9)), (9890, ('FALLING', -10)),
                          (9500, ('FALLING', -400)), (9900, ('STEADY', 0))):
            self.assertEqual(self.tendency(self.press_view(now, 9900)), want)
        self.assertEqual(self.tendency(self.press_view(9950, 9900, n=35)), ('NONE', 0))   # not 3 h yet
        self.assertEqual(self.tendency(self.press_view(9950, None)), ('NONE', 0))         # the oldest a gap
        self.assertEqual(self.tendency(self.press_view(9950, 9900, ok=0)), ('NONE', 0))   # no live value
        self.assertEqual(self.tendency(self.press_view(-2**31, 32767))[0], 'FALLING')      # no overflow

    def test_is_day(self):
        day = self.lib.scr_is_day
        noon_utc = render.NOON_UTC                   # 18:00 UTC: 12:00 at -360 min
        self.assertEqual(day(noon_utc, -360), 1)
        self.assertEqual(day(noon_utc + 6 * 3600, -360), 0)   # 18:00 local: night begins
        self.assertEqual(day(noon_utc + 6 * 3600 - 1, -360), 1)
        self.assertEqual(day(noon_utc - 6 * 3600, -360), 1)   # 06:00 local
        self.assertEqual(day(noon_utc - 6 * 3600 - 1, -360), 0)
        self.assertEqual(day(noon_utc, 0), 0)                 # 18:00 at UTC
        self.assertEqual(day(100, -360), 0)                   # before 1970 locally: still a time of day
        self.assertEqual(day(0, -360), -1)

    def icon(self, v):
        return ['SUN', 'MOON', 'CLOUD', 'RAIN', 'SNOW', 'WIND'][self.lib.scr_icon_pick(ctypes.byref(v))]

    def test_icon_pick_in_order(self):
        w = render.weather
        night = render.NIGHT_UTC
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 5000, 100)), 'SUN')
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 5000, 100, utc=night)), 'MOON')
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 5000, 100, utc=0)), 'SUN')       # no time: the sun
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 8500, 100, utc=night)), 'CLOUD')  # RH 85 % or more
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 8499, 100)), 'SUN')
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 9000, 501)), 'WIND')             # above 5.0 m/s
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 5000, 500)), 'SUN')
        self.assertEqual(self.icon(w(render.demo_view(), -1, 9000, 900)), 'SNOW')               # below 0 degC first
        self.assertEqual(self.icon(w(render.demo_view(), 0, 5000, 100)), 'SUN')
        self.assertEqual(self.icon(w(render.demo_view(), 2000, 5000, 900, tips10=1)), 'RAIN')   # a tip in 10 min wins
        self.assertEqual(self.icon(w(render.demo_view(), -300, 5000, 900, tips10=1)), 'SNOW')
        old = render.rain(render.demo_view(), 1, 600, {49: 1})                                  # 10 minutes ago: not now
        render.weather(old, 2000, 5000, 100)
        old.rain.per_min[49] = 1
        self.assertEqual(self.icon(old), 'SUN')
        old.rain.per_min[50] = 1
        self.assertEqual(self.icon(old), 'RAIN')
        absent = w(render.demo_view(), -900, 9900, 100)
        absent.air_ok = 0
        self.assertEqual(self.icon(absent), 'SUN')                                              # no air: no frost, no cloud

    def test_rain_tips(self):
        m = (ctypes.c_uint8 * 60)(*([1] * 50 + [2] * 10))
        self.assertEqual([self.lib.scr_rain_tips(m, 60, k) for k in (0, 1, 10, 11, 60, 99)], [0, 2, 20, 21, 70, 70])

    # ---- the scales ----

    def test_bar_px(self):
        px = self.lib.scr_bar_px
        self.assertEqual([px(v, 100, 20) for v in (-5, 0, 1, 5, 50, 99, 100, 1000)], [0, 0, 1, 1, 10, 20, 20, 20])
        self.assertEqual(px(1, 0, 20), 20)
        self.assertEqual(px(2**31 - 1, 2**31 - 2, 128), 128)
        self.assertEqual(px(2**31 - 2, 2**31 - 1, 128), 128)   # rounded up, no overflow

    def spark(self, samples, span):
        s = (I16 * len(samples))(*[GAP if x is None else x for x in samples])
        lo, hi = ctypes.c_int32(-1), ctypes.c_int32(-1)
        n = self.lib.scr_spark_range(s, len(samples), span, ctypes.byref(lo), ctypes.byref(hi))
        return n, lo.value, hi.value

    def test_spark_range(self):
        self.assertEqual(self.spark([5, None, 9, 1, None], 0), (3, 1, 9))
        self.assertEqual(self.spark([2000, 2010], 100), (2, 1955, 2055))   # widened about the middle to 1.0 degC
        self.assertEqual(self.spark([None, None], 100), (0, -1, -1))
        self.assertEqual(self.spark([], 100), (0, -1, -1))
        self.assertEqual(self.spark([-32767, 32767], 10), (2, -32767, 32767))

    def test_spark_y(self):
        y = self.lib.scr_spark_y
        self.assertEqual([y(v, 0, 100, 28, 24) for v in (100, 0, 50, 200, -50)], [28, 51, 40, 28, 51])
        self.assertEqual(y(5, 5, 5, 28, 24), 40)   # no span: the middle

    def test_signal_and_acks(self):
        self.assertEqual([self.lib.scr_signal_bars(r) for r in (-30, -85, -86, -100, -101, -115, -116, -32768)],
                         [3, 3, 2, 2, 1, 1, 0, 0])
        r = (I16 * 5)(-40, GAP, -90, GAP, -120)
        self.assertEqual((self.lib.scr_acks(r, 5), self.lib.scr_acks(r, 0)), (3, 0))

    def test_next_tx(self):
        self.assertEqual([self.lib.scr_next_tx_s(s) for s in (0, 1, 26, 59, 60, 61, 125)], [60, 59, 34, 1, 60, 59, 55])
        self.assertEqual(self.lib.scr_next_tx_s(render.SCR_NONE_S), -1)

    # ---- the fortune cookie, the frog, the digital rain ----

    def test_every_fortune_fits_its_slip(self):
        for i in range(15):
            rows = self.fortune(i).split('\n')
            self.assertLessEqual(len(rows), 3, i)
            self.assertTrue(all(0 < len(r) <= 21 for r in rows), rows)

    def pick(self, v):
        return self.fortune(self.lib.scr_fortune_pick(ctypes.byref(v)))

    def test_fortune_follows_the_weather(self):
        w = render.weather
        calm = w(render.demo_view(), 2000, 5000, 100)
        calm.power.soc_pct_x10, calm.press_n = 780, 0   # no 3 h of pressure: no tendency
        self.assertIn(self.pick(calm), [self.fortune(i) for i in range(11, 15)])
        seen = set()
        for seq in range(8):   # last_seq picks among the calm lines: all four in turn
            calm.last_seq = seq
            seen.add(self.pick(calm))
        self.assertEqual(len(seen), 4)
        cases = [('silent', lambda v: setattr(v, 'last_acked', render.SCR_TX_NO_ACK)),
                 ('Low battery', lambda v: setattr(v.power, 'soc_pct_x10', 199)),
                 ('bucket', lambda v: w(v, tips10=1)),
                 ('Below zero', lambda v: w(v, c=-1)),
                 ('hot', lambda v: w(v, c=3000)),
                 ('wind', lambda v: w(v, wind_cms=501)),
                 ('soup', lambda v: w(v, rh=8500)),
                 ('Dry air', lambda v: w(v, rh=2999)),
                 ('barometer sinks', lambda v: self.press_into(v, 9890)),
                 ('Pressure rises', lambda v: self.press_into(v, 9910))]
        for word, change in cases:
            with self.subTest(word=word):
                v = render.View.from_buffer_copy(calm)
                v.last_seq = 0
                change(v)
                self.assertIn(word, self.pick(v))
        both = render.View.from_buffer_copy(calm)   # the order: no ACK before rain
        both.last_acked = render.SCR_TX_NO_ACK
        w(both, tips10=3)
        self.assertIn('silent', self.pick(both))

    @staticmethod
    def press_into(v, now):
        render.history(v, 'press', [9900] * 36)
        v.press_dhpa = now

    def mood(self, v):
        return ['HAPPY', 'SLEEPY', 'MOPEY', 'SOGGY', 'CHILLY', 'BREEZY', 'TOASTY'][self.lib.scr_frog_mood(ctypes.byref(v))]

    def test_frog_mood(self):
        w = render.weather
        self.assertEqual(self.mood(w(render.demo_view(), 2000, 5000, 100)), 'HAPPY')
        self.assertEqual(self.mood(w(render.demo_view(), 2000, 5000, 100, utc=render.NIGHT_UTC)), 'SLEEPY')
        self.assertEqual(self.mood(w(render.demo_view(), 2000, 9000, 100)), 'MOPEY')
        self.assertEqual(self.mood(w(render.demo_view(), 3000, 9000, 100)), 'TOASTY')   # hot beats cloud
        self.assertEqual(self.mood(w(render.demo_view(), 3000, 5000, 900)), 'BREEZY')
        self.assertEqual(self.mood(w(render.demo_view(), -100, 5000, 100)), 'CHILLY')
        self.assertEqual(self.mood(w(render.demo_view(), 3000, 5000, 900, tips10=2)), 'SOGGY')

    def test_matrix_speed(self):
        self.assertEqual([self.lib.scr_matrix_speed(t) for t in (0, 1, 4, 5, 500)], [1, 2, 2, 3, 3])


if __name__ == '__main__':
    unittest.main()
