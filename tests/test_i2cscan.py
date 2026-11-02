"""Bench I2C tool (firmware/i2cscan): the shared power conversions (firmware/common/power_regs.c, also
used by the node and benchlink) against the datasheet scale factors, and the bench-only helpers.

Pure C, compiled for the host. Not bench evidence: the tool's readings are checked against a meter on
the bench (firmware/i2cscan/README.md)."""
import ctypes
import re
import subprocess
import sys
import unittest
try:
    from toolchain import ROOT, c_function, host_library, needs_cc, sensor_power_problems   # discover -s tests
except ImportError:
    from tests.toolchain import ROOT, c_function, host_library, needs_cc, sensor_power_problems

COMMON = ROOT/'firmware/common'
POWER = COMMON/'power_regs.c'
SRC = ROOT/'firmware/i2cscan/App/bench_regs.c'
SHUNT_UOHM = 15_000                 # the INA228 breakout's 0.015 ohm shunt


def raw24(count20):
    """A 20-bit two's-complement count as the INA228 sends it: in the top 20 of 24 bits."""
    return (count20 & 0xFFFFF) << 4


def signatures(lib, restype, argtypes, *names):
    for name in names:
        getattr(lib, name).restype = restype
        getattr(lib, name).argtypes = argtypes


@needs_cc
class PowerRegs(unittest.TestCase):
    """firmware/common/power_regs.c on its own: no bench code, no HAL."""
    @classmethod
    def setUpClass(cls):
        lib = cls.lib = host_library(cls, 'power_regs', '-I', COMMON, POWER)
        i32, u16, u32 = ctypes.c_int32, ctypes.c_uint16, ctypes.c_uint32
        signatures(lib, i32, [u32], 'ina228_count', 'ina228_vshunt_nv', 'ina228_vbus_uv')
        signatures(lib, u32, [i32], 'ina228_raw24')
        signatures(lib, i32, [u32, i32], 'ina228_current_ua')
        signatures(lib, u16, [u32, u32], 'ina228_shunt_cal')
        signatures(lib, ctypes.c_int64, [ctypes.c_int64, u32], 'ina228_charge_uas')
        signatures(lib, i32, [u16], 'ina228_dietemp_mc', 'max17048_vcell_uv', 'max17048_soc_mpct',
                   'max17048_crate_mpct_h')
        signatures(lib, ctypes.c_int, [u16, u16], 'ina228_ids_match')
        signatures(lib, ctypes.c_int, [u16], 'max17048_version_match', 'adc_clipped')
        signatures(lib, u16, [u16], 'max17048_soc_256')
        signatures(lib, u32, [u16, u16], 'adc_vdda_mv')
        signatures(lib, i32, [u16, u32], 'adc_pin_uv')
        signatures(lib, i32, [i32, u32], 'iset_charge_ua', 'divider_mv', 'divider_mv_ppm', 'divider_uv_ppm',
                   'unscale_ppm')

    def test_ina228_shunt_and_current(self):
        # 37.6 mA through 15 mOhm is 564 uV: 1805 counts of 312.5 nV (564.0625 uV).
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(1805)), 564062)
        self.assertEqual(self.lib.ina228_current_ua(raw24(1805), SHUNT_UOHM), 37604)
        # Charging: current into the battery is negative (VIN- above VIN+).
        self.assertEqual(self.lib.ina228_current_ua(raw24(-1805), SHUNT_UOHM), -37604)
        # Full scale, +-163.84 mV, and the 4 reserved low bits are ignored.
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(0x7FFFF) | 0xF), 163839687)
        self.assertEqual(self.lib.ina228_vshunt_nv(raw24(-0x80000)), -163840000)
        self.assertEqual(self.lib.ina228_current_ua(raw24(-0x80000), SHUNT_UOHM), -10922666)   # -10.9 A
        # No shunt: 0, not a division by zero; a tiny one saturates instead of wrapping.
        self.assertEqual(self.lib.ina228_current_ua(raw24(1805), 0), 0)
        self.assertEqual(self.lib.ina228_current_ua(raw24(1805), -15), 0)
        self.assertEqual(self.lib.ina228_current_ua(raw24(0x7FFFF), 1), 2**31 - 1)
        self.assertEqual(self.lib.ina228_current_ua(raw24(-0x80000), 1), -2**31)

    def test_ina228_shunt_cal(self):
        # SHUNT_CAL = 13107.2 x 10^6 x CURRENT_LSB x R (ADCRANGE = 0): spec section 9.4.
        self.assertEqual(self.lib.ina228_shunt_cal(SHUNT_UOHM, 10), 1966)    # 1966.08
        self.assertEqual(self.lib.ina228_shunt_cal(SHUNT_UOHM, 20), 3932)    # 3932.16
        self.assertEqual(self.lib.ina228_shunt_cal(0, 10), 0)
        self.assertEqual(self.lib.ina228_shunt_cal(SHUNT_UOHM, 0), 0)
        self.assertEqual(self.lib.ina228_shunt_cal(2_499_999, 1), 32767)     # the 15-bit field's top
        self.assertEqual(self.lib.ina228_shunt_cal(2_500_000, 1), 0)         # 32768 does not fit
        self.assertEqual(self.lib.ina228_shunt_cal(0xFFFFFFFF, 0xFFFFFFFF), 0)

    def test_ina228_charge(self):
        # One CHARGE count is CURRENT_LSB x 1 s: 60 s at 500 mA with a 10 uA LSB is 3,000,000 counts.
        self.assertEqual(self.lib.ina228_charge_uas(3_000_000, 10), 30_000_000)
        self.assertEqual(self.lib.ina228_charge_uas(-3_000_000, 10), -30_000_000)
        self.assertEqual(self.lib.ina228_charge_uas(1_500_000, 20), 30_000_000)
        self.assertEqual(self.lib.ina228_charge_uas(-(2**39), 10), -(2**39) * 10)   # the 40-bit register's floor

    def test_ina228_count_round_trip(self):
        # The tools average counts and turn the average back into a register image.
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
        self.assertEqual(self.lib.max17048_soc_256(0x4E66), 0x4E66)        # as read, 1/256 %
        self.assertEqual(self.lib.max17048_soc_256(0x6500), 0x6500)        # 101 %: kept, near full
        self.assertEqual(self.lib.max17048_soc_256(0xFFFF), 0xFFFE)        # never the none code
        self.assertEqual(self.lib.max17048_crate_mpct_h(0xFFFD), -624)     # -0.624 %/h
        self.assertEqual(self.lib.max17048_crate_mpct_h(3), 624)
        self.assertTrue(self.lib.max17048_version_match(0x0012))
        self.assertFalse(self.lib.max17048_version_match(0x0000))
        self.assertFalse(self.lib.max17048_version_match(0xFFFF))          # a stuck-high bus reads all ones

    def test_adc_vdda(self):
        # VREFINT_CAL is the count at VDDA = 3.3 V (DS13293 table 14): the same count means 3300 mV.
        self.assertEqual(self.lib.adc_vdda_mv(1655, 1655), 3300)
        self.assertEqual(self.lib.adc_vdda_mv(1820, 1655), 3000)           # 3000.8: a lower VDDA, more counts
        self.assertEqual(self.lib.adc_vdda_mv(0, 1655), 0)

    def test_adc_pin(self):
        self.assertEqual(self.lib.adc_pin_uv(4095, 3300), 3_300_000)       # full scale is VDDA
        self.assertEqual(self.lib.adc_pin_uv(2048, 3300), 1_650_402)       # 1650402.9, truncated
        self.assertEqual(self.lib.adc_pin_uv(0, 3300), 0)
        self.assertEqual(self.lib.adc_pin_uv(65535, 3300), 3_300_000)      # past 12 bits: full scale

    def test_adc_clipped(self):
        # x16 oversampling averages a partly clipped input to 4090-4094 (spec section 9.5).
        self.assertFalse(self.lib.adc_clipped(4079))
        self.assertTrue(self.lib.adc_clipped(4080))
        self.assertTrue(self.lib.adc_clipped(4085))
        self.assertTrue(self.lib.adc_clipped(4095))

    def test_iset_charge(self):
        # I = 400 x V_ISET / R_ISET (SLUS810 eq. 3). The #4755's 1A jumper is R9 = 1 kOhm (record 1.4;
        # ICHG = 890 / 1000 = 0.89 A typ): 2.5 V on 1000 ohm is 1.000 A by the formula.
        self.assertEqual(self.lib.iset_charge_ua(2_500_000, 1000), 1_000_000)
        self.assertEqual(self.lib.iset_charge_ua(1_250_000, 1000), 500_000)
        self.assertEqual(self.lib.iset_charge_ua(2_225_000, 1000), 890_000)   # the 0.89 A typical charge
        self.assertEqual(self.lib.iset_charge_ua(2_500_000, 0), 0)
        self.assertEqual(self.lib.iset_charge_ua(-1, 1000), 0)

    def test_divider(self):
        # The charger input through 20k over 10k: 3 x the pin, in mV, rounded half up.
        self.assertEqual(self.lib.divider_mv(1_650_402, 3), 4951)          # 4951.206
        self.assertEqual(self.lib.divider_mv(1_666_500, 3), 5000)          # 4999.5 rounds up
        self.assertEqual(self.lib.divider_mv(3_300_000, 3), 9900)          # full scale at VDDA 3.3 V
        self.assertEqual(self.lib.divider_mv(0, 3), 0)
        self.assertEqual(self.lib.divider_mv(-5, 3), 0)

    def test_divider_ppm(self):
        # The measured ratio in ppm (record M2, 4.4 step 12): pin x ratio / 1e6, rounded half up.
        mv, uv = self.lib.divider_mv_ppm, self.lib.divider_uv_ppm
        self.assertEqual(uv(1_650_402, 3_000_000), 4_951_206)               # benchlink's vin_uv
        self.assertEqual(mv(1_650_402, 3_000_000), 4951)                    # 4951.206, as divider_mv
        self.assertEqual(mv(1_666_500, 3_000_000), 5000)                    # 4999.5 rounds up
        self.assertEqual(mv(3_300_000, 3_000_000), 9900)
        self.assertEqual(uv(1_650_402, 3_012_345), 4_971_580)               # a measured, non-integer ratio
        self.assertEqual(uv(1, 1_500_000), 2)                               # 1.5 uV rounds up
        self.assertEqual(uv(1, 1_499_999), 1)
        for f in (mv, uv):
            with self.subTest(f=f.__name__):
                self.assertEqual(f(0, 3_000_000), 0)
                self.assertEqual(f(-5, 3_000_000), 0)
                self.assertEqual(f(-2**31, 3_000_000), 0)
                self.assertEqual(f(1_650_402, 0), 0)
                # Any int32 tap and uint32 ratio: the int64 product cannot overflow; the result saturates.
                self.assertEqual(f(2**31 - 1, 2**32 - 1), 2**31 - 1)
        self.assertEqual(mv(2**31 - 1, 1_000_000), 2_147_484)               # 2147483.647 mV
        self.assertEqual(uv(2**31 - 1, 1_000_000), 2**31 - 1)               # ratio 1, exact

    def test_unscale_ppm(self):
        # The ISET pin behind 10k over 1M (gain 990099 ppm) back to V_ISET, rounded half up.
        self.assertEqual(self.lib.unscale_ppm(2_475_247, 990_099), 2_499_999)
        self.assertEqual(self.lib.unscale_ppm(1_000_000, 990_099), 1_010_000)
        self.assertEqual(self.lib.unscale_ppm(1_000_000, 1_000_000), 1_000_000)   # gain 1
        self.assertEqual(self.lib.unscale_ppm(1, 2_000_000), 1)                    # 0.5 rounds up
        self.assertEqual(self.lib.unscale_ppm(3, 2_000_000), 2)                    # 1.5 rounds up
        self.assertEqual(self.lib.unscale_ppm(1, 2_000_001), 0)                    # just under 0.5
        self.assertEqual(self.lib.unscale_ppm(2_475_247, 0), 0)
        self.assertEqual(self.lib.unscale_ppm(0, 990_099), 0)
        self.assertEqual(self.lib.unscale_ppm(-1, 990_099), 0)
        self.assertEqual(self.lib.unscale_ppm(-2**31, 990_099), 0)
        self.assertEqual(self.lib.unscale_ppm(2**31 - 1, 1), 2**31 - 1)            # saturates
        self.assertEqual(self.lib.unscale_ppm(2**31 - 1, 2**32 - 1), 500_000)      # 500000.0001


@needs_cc
class BenchRegs(unittest.TestCase):
    """The bench-only helpers (bench_regs.c), built with the shared conversions as the tools link them."""
    @classmethod
    def setUpClass(cls):
        lib = cls.lib = host_library(cls, 'bench_regs', '-I', SRC.parent, '-I', COMMON, SRC, POWER)
        lib.bench_part_name.restype = ctypes.c_char_p
        lib.bench_part_name.argtypes = [ctypes.c_uint8]
        lib.bench_fixed.restype = ctypes.c_char_p
        lib.bench_fixed.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_uint,
                                    ctypes.c_uint, ctypes.c_int]

    def fixed(self, value, drop, decimals, sign=0, n=24):
        buf = ctypes.create_string_buffer(n)
        return self.lib.bench_fixed(buf, n, value, drop, decimals, sign).decode()

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

    def test_phase_b_rails_match_the_node(self):
        """The phase B rail INA228s (load, solar, USB-C) are named in the scan and read once a scan, at the
        node's addresses (stage0-node/App/power_config.h POWER_ADDR_*), so a bad strap shows before profile B."""
        cfg = (ROOT/'firmware/stage0-node/App/power_config.h').read_text()
        node = {name: int(v, 16) for name, v in re.findall(r'#define POWER_ADDR_(LOAD|SOLAR|USB)\s+(0x[0-9A-Fa-f]+)U', cfg)}
        scan = (ROOT/'firmware/i2cscan/App/i2cscan.c').read_text()
        tool = {rail: int(v, 16) for v, rail in re.findall(r'\{ (0x[0-9A-Fa-f]+)U, "([a-z-]+)" \}', scan)}
        self.assertEqual(tool, {'load': node['LOAD'], 'solar': node['SOLAR'], 'usb-c': node['USB']})
        for rail, addr in tool.items():
            name = self.lib.bench_part_name(addr).decode()
            self.assertTrue(name.startswith('INA228 ') and '(phase B)' in name, (rail, name))

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


class SharedCallers(unittest.TestCase):
    """The callers of the shared conversions, read as text: C does not tell a micro-ohm int from a
    milli-ohm one, so a caller passing the wrong unit builds cleanly and reads 1000x off."""
    CALL = re.compile(r'\bina228_current_ua\s*\(([^;]*?)\)\s*;')

    def callers(self):
        return [(path, m.group(1)) for path in sorted((ROOT/'firmware').rglob('*.c'))
                if path != POWER for m in self.CALL.finditer(path.read_text())]

    def test_current_takes_micro_ohm(self):
        calls = self.callers()
        self.assertTrue(calls, 'no caller of ina228_current_ua found')
        for path, args in calls:
            with self.subTest(file=str(path.relative_to(ROOT)), args=args):
                self.assertNotRegex(args, r'MOHM|_mohm\b|\bmohm', 'shunt passed in milli-ohm')

    def test_benchlink_readme_names_the_shared_decoder(self):
        readme = (ROOT/'firmware/benchlink/README.md').read_text()
        self.assertTrue('../common/power_regs.c' in readme,
                        'firmware/benchlink/README.md does not name ../common/power_regs.c')


APP =ROOT/'firmware/i2cscan/App'
OLED_W, OLED_H = 128, 64


class View(ctypes.Structure):
    _fields_ = [('found', ctypes.c_uint8*5), ('nfound', ctypes.c_uint), ('ina_ok', ctypes.c_int),
                ('ua', ctypes.c_int32), ('vbus_uv', ctypes.c_int32), ('gauge_ok', ctypes.c_int),
                ('vcell_uv', ctypes.c_int32), ('soc_mpct', ctypes.c_int32), ('crate_mpct_h', ctypes.c_int32)]   # bench_view


@needs_cc
class BenchScreen(unittest.TestCase):
    """The OLED frame buffer, font and layout (oled_fb.c, font5x7.c, bench_screen.c)."""
    @classmethod
    def setUpClass(cls):
        cls.lib = host_library(cls, 'bench_screen', '-I', APP, '-I', COMMON, APP/'oled_fb.c', APP/'font5x7.c',
                               APP/'bench_screen.c', APP/'bench_regs.c', POWER)
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
        v = View((0x36, 0x40, 0, 0, 0), 2, 1, 37604, 3845898, 1, 3846015, 78398, -624)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C 36 40', 1), (11, b'+37.60mA', 2), (31, b'OUT 3.8459V', 1),
                                                (42, b'CELL 3.8460V 78.4%', 1), (53, b'RATE -0.62%/h', 1)]))

    def test_screen_with_nothing_on_the_bus(self):
        v = View((0,)*5, 0, 0, 0, 0, 0, 0, 0, 0)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C NONE', 1), (11, b'NO INA228', 2), (42, b'NO GAUGE', 1)]))

    def test_screen_with_more_addresses_than_fit(self):
        v = View((0x36, 0x3C, 0x40, 0x44, 0x47), 7, 0, 0, 0, 0, 0, 0, 0)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.expected([(0, b'I2C 36 3C 40 44 47 +', 1), (11, b'NO INA228', 2),
                                                (42, b'NO GAUGE', 1)]))
        # The "+" is the 20th character (x 114-118) and must be on the screen, not clipped.
        plus = {(x, y) for x in range(114, 120) for y in range(7) if self.lib.oled_get(fb, x, y)}
        self.assertEqual(plus, {(x + 114, y) for x, y in self.lit_of(b'+')})


class SensorPower(unittest.TestCase):
    """With per-port power PA9 switches the sensor ports (record 4.6; change C, not part of the breadboard build
    since 2026-11-02): i2cscan drives PA9 high before its first bus access, or a switched sensor is unpowered.
    On the breadboard PA9 is unconnected, so the drive is harmless there."""

    def setUp(self):
        self.src = (ROOT/'firmware/i2cscan/App/i2cscan.c').read_text()

    def test_pa9_is_driven_high_before_the_bus_starts(self):
        init = c_function(self.src, 'void SubghzApp_Init(void)')
        self.assertEqual(sensor_power_problems(self.src, init), [])
        self.assertIn('#power PA9', init)

    def test_the_check_sees_a_missing_drive(self):
        init = c_function(self.src, 'void SubghzApp_Init(void)')
        self.assertTrue(sensor_power_problems(self.src, init.replace('  sensors_on();\n', '')))
        late = init.replace('  sensors_on();\n', '').replace('  bus_start();\n', '  bus_start();\n  sensors_on();\n')
        self.assertTrue(sensor_power_problems(self.src, late))
        low = self.src.replace('POWER_PIN, GPIO_PIN_SET', 'POWER_PIN, GPIO_PIN_RESET')
        self.assertTrue(sensor_power_problems(low, init))


if __name__ == '__main__':
    unittest.main()
