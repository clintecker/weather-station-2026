"""Bench I2C tool (firmware/i2cscan): the shared power conversions (firmware/common/power_regs.c, also
used by the node and benchlink) against the datasheet scale factors, and the bench-only helpers.

Pure C, compiled for the host. Not bench evidence: the tool's readings are checked against a meter on
the bench (firmware/i2cscan/README.md)."""
import ctypes
import hashlib
import re
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


class SurfStruct(ctypes.Structure):
    _fields_ = [('px', ctypes.c_void_p), ('rot180', ctypes.c_uint8), ('ink', ctypes.c_uint8)]   # oled_surf (oled_draw.h)


class Surf:
    """An oled_surf over a cleared frame of its own, passed to the library as a pointer to it. raw: the frame."""
    def __init__(self, rot180=0):
        self.buf = ctypes.create_string_buffer(OLED_W*OLED_H//2)
        self.s = SurfStruct(ctypes.addressof(self.buf), rot180, 15)
        self._as_parameter_ = ctypes.byref(self.s)

    @property
    def raw(self):
        return self.buf.raw


class View(ctypes.Structure):
    _fields_ = [('found', ctypes.c_uint8*5), ('nfound', ctypes.c_uint), ('ina_ok', ctypes.c_int),
                ('ua', ctypes.c_int32), ('vbus_uv', ctypes.c_int32), ('gauge_ok', ctypes.c_int),
                ('vcell_uv', ctypes.c_int32), ('soc_mpct', ctypes.c_int32), ('crate_mpct_h', ctypes.c_int32),
                ('meters_ok', ctypes.c_int), ('wind_ums', ctypes.c_int32), ('vane', ctypes.c_char_p),
                ('tips', ctypes.c_uint32), ('air_ok', ctypes.c_int), ('box_ok', ctypes.c_int),
                ('press_ok', ctypes.c_int), ('uv_ok', ctypes.c_int), ('air_centi_c', ctypes.c_int32),
                ('air_centi_rh', ctypes.c_int32), ('box_centi_c', ctypes.c_int32), ('box_centi_rh', ctypes.c_int32),
                ('press_dhpa', ctypes.c_int32), ('uv_counts', ctypes.c_uint32)]   # bench_view


@needs_cc
class BenchScreen(unittest.TestCase):
    """The bench screen's layout (bench_screen.c) over the shared drawing surface and font (firmware/common)."""
    @classmethod
    def setUpClass(cls):
        cls.lib = host_library(cls, 'bench_screen', '-I', APP, '-I', COMMON, COMMON/'oled_draw.c', COMMON/'font5x7.c', APP/'bench_screen.c', APP/'bench_regs.c', POWER)
        cls.lib.oled_text.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        cls.lib.bench_screen.argtypes = [ctypes.c_void_p, ctypes.POINTER(View)]

    def fb(self, rot180=0):
        return Surf(rot180)

    def expected(self, lines):
        fb = self.fb()
        for y, text, scale in lines:
            self.lib.oled_text(fb, 0, y, text, scale)
        return fb.raw

    def rows(self, *lines):
        return self.expected([(8*i, text, 1) for i, text in enumerate(lines) if text is not None])

    def test_screen_with_everything(self):
        v = View(found=(0x36, 0x40, 0x44, 0x47, 0x53), nfound=6, ina_ok=1, ua=37604, vbus_uv=3845898, gauge_ok=1,
                 vcell_uv=3846015, soc_mpct=78398, meters_ok=1, wind_ums=1333960, vane=b'SE', tips=2,
                 air_ok=1, air_centi_c=2134, air_centi_rh=4521, box_ok=1, box_centi_c=2210, box_centi_rh=4002,
                 press_ok=1, press_dhpa=10132, uv_ok=1, uv_counts=123)
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.rows(b'I2C 36 40 44 47 53 +', b'BATT +37.60mA 3.846V', b'CELL 3.846V 78.4%',
                                           b'AIR 21.34C 45.21%', b'BOX 22.10C 40.02%', b'P 1013.2hPa UV 123',
                                           b'WIND 1.33m/s SE', b'RAIN 2 TIPS 0.56mm'))

    def test_screen_with_nothing_on_the_bus(self):
        v = View()
        fb = self.fb()
        self.lib.bench_screen(fb, ctypes.byref(v))
        self.assertEqual(fb.raw, self.rows(b'I2C NONE', b'BATT NO INA228', b'CELL NO MAX17048', b'AIR NO SHT45',
                                           b'BOX NO SHTC3', b'P NO BMP581 UV NO'))

    # Four views, each frame hashed as i2cscan sends it (App/i2cscan.c: drawn turned, for the panel): a refactor
    # of the drawing code keeps every hash, a deliberate change updates them here.
    GOLDEN = {'everything': 'cd110f612b27a962', 'nothing': '20b91cd48a2da55d', 'zero': 'dca2c19b3c844812',
              'cold': '1df2d072d3d8e2bc'}

    @staticmethod
    def golden_views():
        everything = View(found=(0x36, 0x40, 0x44, 0x47, 0x53), nfound=6, ina_ok=1, ua=37604, vbus_uv=3845898, gauge_ok=1,
                          vcell_uv=3846015, soc_mpct=78398, meters_ok=1, wind_ums=1333960, vane=b'SE', tips=2,
                          air_ok=1, air_centi_c=2134, air_centi_rh=4521, box_ok=1, box_centi_c=2210, box_centi_rh=4002,
                          press_ok=1, press_dhpa=10132, uv_ok=1, uv_counts=123)
        zero = View(found=(0x40,), nfound=1, ina_ok=1, ua=4, vbus_uv=0, meters_ok=1, wind_ums=0, vane=None, tips=200000,
                    press_ok=1, press_dhpa=9871)   # a zero current (Q3 of the visual system design), no vane, rain clamped
        cold = View(found=(0x44, 0x47, 0x53), nfound=3, ina_ok=1, ua=-125349, vbus_uv=4199999, gauge_ok=1, vcell_uv=4200000,
                    soc_mpct=100000, meters_ok=1, wind_ums=25010000, vane=b'NNW', tips=99999, air_ok=1, air_centi_c=-1234,
                    air_centi_rh=10000, box_ok=1, box_centi_c=-5, box_centi_rh=0, uv_ok=1, uv_counts=262143)
        return {'everything': everything, 'nothing': View(), 'zero': zero, 'cold': cold}

    def sent(self, v):
        fb = self.fb(rot180=1)
        self.lib.bench_screen(fb, ctypes.byref(v))
        return hashlib.sha256(fb.raw).hexdigest()[:16]

    def test_frames_are_as_they_were(self):
        got = {name: self.sent(v) for name, v in self.golden_views().items()}
        self.assertEqual(got, self.GOLDEN)
        self.assertEqual(len(set(got.values())), 4)

    def test_screen_text_has_no_missing_glyphs(self):
        # Every character the layout draws is in the font: a '?' on the screen is never a glyph gap.
        chars = (COMMON/'font5x7.c').read_text().split('font5x7_chars[] = "')[1].split('"')[0]
        for text in (b'BATT +37.60mA 3.846V', b'CELL NO MAX17048', b'P 1013.2hPa UV 123', b'WIND 1.33m/s NNE',
                     b'RAIN 2 TIPS 0.56mm', b'AIR 21.34C 45.21%'):
            self.assertTrue(set(text.decode()) <= set(chars), text)

    def test_sht_parse(self):
        self.lib.bench_sht_parse.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int32),
                                             ctypes.POINTER(ctypes.c_int32)]
        t, h = ctypes.c_int32(), ctypes.c_int32()
        def crc(w):
            x = 0xFF
            for byte in w:
                x ^= byte
                for _ in range(8):
                    x = ((x << 1) ^ 0x31) & 0xFF if x & 0x80 else (x << 1) & 0xFF
            return x
        self.assertEqual(crc(b'\xbe\xef'), 0x92)                 # Sensirion's datasheet example
        reply = b'\x66\x66' + bytes([crc(b'\x66\x66')]) + b'\x80\x00' + bytes([crc(b'\x80\x00')])
        self.assertEqual(self.lib.bench_sht_parse(reply, 0, t, h), 0)   # SHT45
        self.assertEqual((t.value, h.value), (2500, 5650))
        self.assertEqual(self.lib.bench_sht_parse(reply, 1, t, h), 0)   # SHTC3
        self.assertEqual((t.value, h.value), (2500, 5000))
        self.assertEqual(self.lib.bench_sht_parse(reply[:5] + b'\x00', 0, t, h), -1)
        low = b'\x00\x00' + bytes([crc(b'\x00\x00')]) * 1 + b'\x00\x00' + bytes([crc(b'\x00\x00')])
        self.assertEqual(self.lib.bench_sht_parse(low, 0, t, h), 0)
        self.assertEqual((t.value, h.value), (-4500, 0))               # RH cropped at 0, not -6 %

    def test_bmp581_and_ltr390(self):
        self.lib.bench_bmp581_dhpa.argtypes = [ctypes.c_char_p]
        self.lib.bench_ltr390_counts.argtypes = [ctypes.c_char_p]
        self.lib.bench_ltr390_counts.restype = ctypes.c_uint32
        raw = 101325 * 64                                           # 1013.25 hPa
        self.assertEqual(self.lib.bench_bmp581_dhpa(raw.to_bytes(3, 'little')), 10133)
        self.assertEqual(self.lib.bench_ltr390_counts(b'\x7b\x00\xf0'), 123)   # the top nibble is not data

    def test_vane_points(self):
        # SEN-15901 resistances under 10 kOhm to 3.3 V, clockwise from north (stage0-node/App/mod_wind.c).
        ohms = (33000, 6570, 8200, 891, 1000, 688, 2200, 1410, 3900, 3140, 16000, 14120, 120000, 42120, 64900, 21880)
        points = 'N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW'.split()
        self.lib.bench_vane_point.restype = ctypes.c_char_p
        self.lib.bench_vane_point.argtypes = [ctypes.c_uint16]
        for r, want in zip(ohms, points):
            mv = (3300*r + (r + 10000)//2) // (r + 10000)
            self.assertEqual(self.lib.bench_vane_point(mv).decode(), want, r)
        self.assertEqual(self.lib.bench_vane_point(3250), b'OPEN')
        self.assertEqual(self.lib.bench_vane_point(0), b'?')     # a short: inside no band


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
