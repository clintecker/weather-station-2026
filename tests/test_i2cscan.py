"""Bench I2C tool (firmware/i2cscan): the register decoding against the datasheet scale factors.

Pure C, compiled for the host. Not bench evidence: the tool's readings are checked against a meter on
the bench (firmware/i2cscan/README.md)."""
import ctypes
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


if __name__ == '__main__':
    unittest.main()
