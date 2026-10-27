"""Bench I2C tool (firmware/i2cscan): the register decoding against the datasheet scale factors.

Pure C, compiled for the host. Not bench evidence: the tool's readings are checked against a meter on
the bench (firmware/i2cscan/README.md)."""
import ctypes
import subprocess
import sys
import unittest
try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

SRC = ROOT/'firmware/i2cscan/App/bench_regs.c'


def raw24(count20):
    """A 20-bit two's-complement count as the INA228 sends it: in the top 20 of 24 bits."""
    return (count20 & 0xFFFFF) << 4


@needs_cc
class BenchRegs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = cls.lib = host_library(cls, 'bench_regs', '-I', SRC.parent, SRC)
        for name in ('ina228_vshunt_nv', 'ina228_vbus_uv', 'ina228_current_ua', 'ina228_dietemp_mc',
                     'max17048_vcell_uv', 'max17048_soc_mpct', 'max17048_crate_mpct_h'):
            getattr(lib, name).restype = ctypes.c_int32
        lib.ina228_vshunt_nv.argtypes = [ctypes.c_uint32]
        lib.ina228_vbus_uv.argtypes = [ctypes.c_uint32]
        lib.ina228_current_ua.argtypes = [ctypes.c_uint32, ctypes.c_int32]
        lib.ina228_dietemp_mc.argtypes = [ctypes.c_uint16]
        lib.ina228_ids_match.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
        for name in ('max17048_vcell_uv', 'max17048_soc_mpct', 'max17048_crate_mpct_h', 'max17048_version_match'):
            getattr(lib, name).argtypes = [ctypes.c_uint16]
        lib.bench_part_name.restype = ctypes.c_char_p
        lib.bench_part_name.argtypes = [ctypes.c_uint8]
        lib.bench_fixed.restype = ctypes.c_char_p
        lib.bench_fixed.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_uint,
                                    ctypes.c_uint, ctypes.c_int]

    def fixed(self, value, drop, decimals, sign=0, n=24):
        buf = ctypes.create_string_buffer(n)
        return self.lib.bench_fixed(buf, n, value, drop, decimals, sign).decode()

    def test_ina228_shunt_and_current(self):
        # 37.6 mA through 15 mOhm is 564 uV: 1805 counts of 312.5 nV (564.0625 uV).
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(1805)), 564062)
        self.assertEqual(self.lib.ina228_current_ua(raw24(1805), 15), 37604)
        # Charging: current into the battery is negative (VIN- above VIN+).
        self.assertEqual(self.lib.ina228_current_ua(raw24(-1805), 15), -37604)
        # Full scale, +-163.84 mV, and the 4 reserved low bits are ignored.
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(0x7FFFF) | 0xF), 163839687)
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(-0x80000)), -163840000)

    def test_ina228_count_round_trip(self):
        # The tool averages counts and turns the average back into a register image.
        self.lib.ina228_count.restype = ctypes.c_int32
        self.lib.ina228_count.argtypes = [ctypes.c_uint32]
        self.lib.ina228_raw24.restype = ctypes.c_uint32
        self.lib.ina228_raw24.argtypes = [ctypes.c_int32]
        for count in (0, 1, -1, 1805, -1805, 0x7FFFF, -0x80000):
            self.assertEqual(self.lib.ina228_raw24(count), raw24(count))
            self.assertEqual(self.lib.ina228_count(self.lib.ina228_raw24(count)), count)

    def test_ina228_bus_and_die(self):
        # 3.846 V is 19691 counts of 195.3125 uV (3845.8984 mV).
        self.assertEqual(self.lib.ina228_vbus_uv(raw24(19691)), 3845898)
        self.assertEqual(self.lib.ina228_dietemp_mc(3085), 24101)          # 24.1 degC
        self.assertEqual(self.lib.ina228_dietemp_mc(0xFF80), -1000)        # -1 degC
        self.assertTrue(self.lib.ina228_ids_match(0x5449, 0x2281))
        self.assertFalse(self.lib.ina228_ids_match(0x5449, 0x2371))        # an INA237 at 0x40
        self.assertFalse(self.lib.ina228_ids_match(0x0000, 0x2281))

    def test_max17048(self):
        self.assertEqual(self.lib.max17048_vcell_uv(49229), 3846015)       # 3.846 V
        self.assertEqual(self.lib.max17048_soc_mpct(0x4E66), 78398)        # 78.398 %
        self.assertEqual(self.lib.max17048_crate_mpct_h(0xFFFD), -624)     # -0.624 %/h
        self.assertEqual(self.lib.max17048_crate_mpct_h(3), 624)
        self.assertTrue(self.lib.max17048_version_match(0x0012))
        self.assertFalse(self.lib.max17048_version_match(0x0000))
        self.assertFalse(self.lib.max17048_version_match(0xFFFF))          # a stuck-high bus reads all ones

    def test_mean_rounds_to_nearest(self):
        self.lib.bench_mean.restype = ctypes.c_int32
        self.lib.bench_mean.argtypes = [ctypes.c_int64, ctypes.c_uint]
        self.assertEqual(self.lib.bench_mean(7, 4), 2)          # 1.75
        self.assertEqual(self.lib.bench_mean(-7, 4), -2)        # not -1: no bias toward zero
        self.assertEqual(self.lib.bench_mean(6, 4), 2)          # 1.5 rounds away from zero
        self.assertEqual(self.lib.bench_mean(-6, 4), -2)
        self.assertEqual(self.lib.bench_mean(4 * 1805 + 1, 4), 1805)
        self.assertEqual(self.lib.bench_mean(5, 0), 0)

    def test_part_names(self):
        self.assertEqual(self.lib.bench_part_name(0x36), b'MAX17048 gauge')
        self.assertEqual(self.lib.bench_part_name(0x40), b'INA228 battery monitor')
        self.assertEqual(self.lib.bench_part_name(0x3C), b'SSD1305 OLED')
        self.assertEqual(self.lib.bench_part_name(0x3D), b'SSD1305 OLED')
        self.assertEqual(self.lib.bench_part_name(0x11), b'?')

    def test_fixed_point_text(self):
        self.assertEqual(self.fixed(3845898, 2, 4), '3.8459')                 # uV -> V, 4 decimals
        self.assertEqual(self.fixed(37604, 1, 2, sign=1), '+37.60')           # uA -> mA, 2 decimals
        self.assertEqual(self.fixed(-37604, 1, 2, sign=1), '-37.60')
        self.assertEqual(self.fixed(-4, 1, 2, sign=1), '0.00')               # rounds to zero: no sign
        self.assertEqual(self.fixed(5, 1, 2, sign=1), '+0.01')               # half rounds away from zero
        self.assertEqual(self.fixed(-624, 1, 2), '-0.62')
        self.assertEqual(self.fixed(24101, 2, 1), '24.1')
        self.assertEqual(self.fixed(7, 0, 0), '7')
        self.assertEqual(self.fixed(-2147483647 - 1, 0, 3), '-2147483.648')   # INT32_MIN
        self.assertEqual(self.fixed(123456, 0, 2, n=5), '1234')               # truncated, terminated
        self.assertEqual(self.fixed(1, 10, 0), '?')                           # 10^10 is past the limit
        self.assertEqual(self.fixed(1, 0, 10), '?')
        self.assertEqual(self.fixed(1, 0, 10, n=1), '')


APP = ROOT/'firmware/i2cscan/App'
OLED_W, OLED_H = 128, 64


class View(ctypes.Structure):
    _fields_ = [('found', ctypes.c_uint8*6), ('nfound', ctypes.c_uint), ('ina_ok', ctypes.c_int),
                ('ua', ctypes.c_int32), ('vbus_uv', ctypes.c_int32), ('gauge_ok', ctypes.c_int),
                ('vcell_uv', ctypes.c_int32), ('soc_mpct', ctypes.c_int32), ('crate_mpct_h', ctypes.c_int32)]   # bench_view


@needs_cc
class BenchScreen(unittest.TestCase):
    """The OLED frame buffer, font and layout (oled_fb.c, font5x7.c, bench_screen.c)."""
    @classmethod
    def setUpClass(cls):
        cls.lib = host_library(cls, 'bench_screen', '-I', APP, APP/'oled_fb.c', APP/'font5x7.c',
                               APP/'bench_screen.c', APP/'bench_regs.c')
        cls.lib.oled_text.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        cls.lib.oled_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cls.lib.oled_get.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        cls.lib.ssd1325_column.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
        cls.lib.bench_screen.argtypes = [ctypes.c_void_p, ctypes.POINTER(View)]

    def fb(self):
        return ctypes.create_string_buffer(OLED_W*OLED_H//8)

    def lit(self, fb):
        return {(x, y) for y in range(OLED_H) for x in range(OLED_W) if self.lib.oled_get(fb, x, y)}

    def test_font_file_is_current(self):
        script = ROOT/'firmware/i2cscan/tools/make_font.py'
        self.assertEqual(subprocess.run([sys.executable, script, '--check']).returncode, 0)

    def test_glyph_pixels(self):
        fb = self.fb()
        self.assertEqual(self.lib.oled_text(fb, 10, 20, b'1', 1), 16)
        art = '..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.'.split()
        want = {(10 + c, 20 + r) for r, row in enumerate(art) for c, ch in enumerate(row) if ch == '#'}
        self.assertEqual(self.lit(fb), want)

    def test_scale_and_unknown_characters(self):
        fb, ref = self.fb(), self.fb()
        self.assertEqual(self.lib.oled_text(fb, 0, 0, b'x~', 2), 24)     # neither is in the font
        self.lib.oled_text(ref, 0, 0, b'??', 2)
        self.assertEqual(fb.raw, ref.raw)
        self.assertEqual(len(self.lit(ref)), 2*4*len(self.lit_of(b'?')))  # each font pixel is 2 x 2

    def lit_of(self, text):
        fb = self.fb()
        self.lib.oled_text(fb, 0, 0, text, 1)
        return self.lit(fb)

    def test_off_screen_is_ignored(self):
        fb = self.fb()
        for x, y in ((-1, 0), (0, -1), (OLED_W, 0), (0, OLED_H), (10**6, 10**6)):
            self.lib.oled_set(fb, x, y, 1)
            self.assertEqual(self.lib.oled_get(fb, x, y), 0)
        self.assertEqual(fb.raw, bytes(len(fb.raw)))
        self.lib.oled_text(fb, 120, 60, b'888', 2)                       # clipped, not wrapped
        self.assertTrue(all(x >= 120 and y >= 60 for x, y in self.lit(fb)))

    def test_ssd1325_column_order(self):
        fb = self.fb()
        for x, y in ((0, 0), (1, 5), (126, 63), (127, 63)):
            self.lib.oled_set(fb, x, y, 1)
        col = ctypes.create_string_buffer(OLED_H)
        self.lib.ssd1325_column(fb, 0, col)
        self.assertEqual(col.raw[0], 0xF0)          # x = 0: the left pixel, high nibble
        self.assertEqual(col.raw[5], 0x0F)          # x = 1: the right pixel, low nibble
        self.assertEqual(sum(1 for b in col.raw if b), 2)
        self.lib.ssd1325_column(fb, 63, col)
        self.assertEqual(col.raw[63], 0xFF)
        self.assertEqual(sum(1 for b in col.raw if b), 1)

    def expected(self, lines):
        fb = self.fb()
        for y, text, scale in lines:
            self.lib.oled_text(fb, 0, y, text, scale)
        return fb.raw

    def test_screen_with_both_parts(self):
        v = View((0x36, 0x40, 0, 0, 0, 0), 2, 1, 37604, 3845898, 1, 3846015, 78398, -624)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C 36 40', 1), (11, b'+37.60mA', 2), (31, b'VBUS 3.8459V', 1),
                                                (42, b'CELL 3.8460V 78.4%', 1), (53, b'RATE -0.62%/h', 1)]))

    def test_screen_with_nothing_on_the_bus(self):
        v = View((0,)*6, 0, 0, 0, 0, 0, 0, 0, 0)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C NONE', 1), (11, b'NO INA228', 2), (42, b'NO GAUGE', 1)]))

    def test_screen_with_more_addresses_than_fit(self):
        v = View((0x36, 0x3C, 0x40, 0x44, 0x47, 0x53), 7, 0, 0, 0, 0, 0, 0, 0)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C 36 3C 40 44 47 53 +', 1), (11, b'NO INA228', 2),
                                                (42, b'NO GAUGE', 1)]))


if __name__ == '__main__':
    unittest.main()
