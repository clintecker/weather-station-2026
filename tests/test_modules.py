"""The station's local WSMP modules (firmware/stage0-node/App/wsmp_local.c and mod_*.c) on the host.

firmware/host/wsmp_harness.c runs the modules on the shared I2C bus (App/i2c_bus.c) and the host bus
model (firmware/host/i2c_sim.c). The Conformance mixin holds the subset of the WSMP section 14 checks
that the host build can run (section 14 lists what it does not cover yet) for every module; each module class adds its own cases. Expected values come from docs/module-protocol.md
and the parts' datasheets. Host-model results, not bench evidence."""
import ctypes
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
    import wsmp_wind_ref as wind_ref
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>
    from tests import wsmp_wind_ref as wind_ref

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048 = 2, 3, 4, 5, 6, 7
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
DM_BUS_ERROR = 6
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN = range(1, 8)
GOOD, PARTIAL, SUSPECT, MISSING = range(4)
FLAG_FIRST, FLAG_LONG = 1, 2
BOOT = 0x0102_0304
MINUTE = 60_000


def module_sources():
    fw = ROOT/'firmware'
    app = fw/'stage0-node/App'
    return ['-I', fw/'host/include', '-I', fw/'host', '-I', app, '-I', fw/'stage0-node/Core/Inc', '-I', fw,
            '-I', fw/'common', fw/'host/wsmp_harness.c', fw/'host/sim_core.c', fw/'host/i2c_sim.c',
            fw/'host/i2c_models.c', app/'i2c_bus.c', app/'busymon.c', app/'wsmp_local.c', app/'mod_th.c',
            app/'mod_mean.c', app/'mod_reg.c', app/'mod_power.c', app/'mod_wind.c', app/'mod_rain.c',
            fw/'stage0.c', fw/'common/ws_check.c', fw/'common/wsmp.c']


def be(b, i, n):
    return int.from_bytes(b[i:i + n], 'big')


def signed16(v):
    return v - 0x10000 if v & 0x8000 else v


@needs_cc
class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'modules', *module_sources())
        cls.library = lib._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.count = 0

    def station(self, devices, start_ms=0):
        """A fresh station (its own copy of the library: statics start at zero) with these devices.
        start_ms is the clock when the modules start: a warm reset does not set the board clock to 0."""
        type(self).count += 1
        path = Path(self.tmp.name)/f'm{self.count}.so'
        shutil.copy(self.library, path)
        lib = ctypes.CDLL(str(path))
        lib.h_now_ms.restype = ctypes.c_uint32
        lib.h_advance.argtypes = [ctypes.c_uint32]
        lib.h_advance(start_ms)
        devs = {kind: lib.h_add_device(kind, addr) for kind, addr in devices}
        lib.h_init(BOOT)
        self.addCleanup(lambda: self.assertEqual((lib.h_pin_errors(), lib.ws_check_count()), (0, 0)))
        return lib, devs

    def snapshot(self, lib, port):
        buf = (ctypes.c_uint8 * 72)()
        lib.h_snapshot(port, buf)
        return bytes(buf)

    def slot(self, snap, i):
        """(value, count, quality) of slot i."""
        at = 8 + 8 * i
        return be(snap, at, 4), be(snap, at + 4, 2), snap[at + 6]

    def latch(self, lib, port, token):
        lib.h_latch(port, token, 1_792_000_000)
        return self.snapshot(lib, port)


class Conformance:
    """WSMP section 14 for one local module. A subclass sets PORT, TYPE, CHANNELS and DEVICES."""

    def test_identity_fields(self):
        lib, _ = self.station(self.DEVICES)
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(self.PORT, idb, desc)
        idb = bytes(idb)
        self.assertEqual(idb[:4], b'WS\x01\x00')
        self.assertEqual((be(idb, 4, 2), idb[6], idb[7]), (self.TYPE, 1, self.CHANNELS))
        self.assertNotEqual(be(idb, 8, 8), 0)
        self.assertEqual(be(idb, 20, 4), BOOT)                     # WSMP-I2: the station's boot epoch
        self.assertEqual(lib.h_desc_check(self.PORT), 0)           # the descriptors pass WSMP-D7

    def test_a_reset_late_in_the_clock_still_samples(self):
        # clock_ms() wraps after 49 days and is signed-compared, so a reset in its upper half
        # (24.9 to 49.7 days after power-up) must not leave the first deadline 2^31 ms away.
        lib, _ = self.station(self.DEVICES, start_ms=0x8000_0000 + 1000)
        seq = lib.h_probe_seq(self.PORT)
        lib.h_run(MINUTE)
        self.assertNotEqual(lib.h_probe_seq(self.PORT), seq)

    def test_latch_then_read_twice_gives_the_same_bytes(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        a = self.latch(lib, self.PORT, 1)
        self.assertEqual(self.snapshot(lib, self.PORT), a)
        self.assertEqual(be(a, 0, 2), 1)                           # the latch token
        self.assertEqual(be(a, 2, 2), BOOT & 0xFFFF)
        self.assertEqual(a[8 + 8 * self.CHANNELS:], bytes(72 - 8 - 8 * self.CHANNELS))   # WSMP-S1

    def test_a_repeated_token_does_not_open_a_window(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        a = self.latch(lib, self.PORT, 7)
        lib.h_run(MINUTE // 2)
        self.assertEqual(self.latch(lib, self.PORT, 7), a)         # WSMP-L3: a retry, the same bytes ...
        lib.h_run(MINUTE // 2)
        b = self.latch(lib, self.PORT, 8)
        self.assertEqual(be(b, 4, 2), MINUTE)                      # ... and no new window: 60 s, not 30 s

    def test_a_missed_latch_gives_a_long_window(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(2 * MINUTE)
        b = self.latch(lib, self.PORT, 2)
        self.assertEqual(be(b, 4, 2), 65_535)                       # two minutes: the length saturates ...
        self.assertEqual(b[6] & FLAG_LONG, FLAG_LONG)               # ... and the window is flagged long (WSMP-T3)

    def test_a_window_too_long_for_its_field_is_long(self):
        # 70 s fits no u16 of ms: the length saturates, and a saturated length sets the long flag
        # (WSMP section 6), or a reader would divide by 65.5 s.
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(70_000)
        b = self.latch(lib, self.PORT, 2)
        self.assertEqual((be(b, 4, 2), b[6] & FLAG_LONG), (65_535, FLAG_LONG))


class TempHumidity(Conformance):
    """The SHT45 and SHTC3 modules: means of the 15-s samples (WSMP section 4.4, types 1 and 4)."""
    CHANNELS = 2

    def good_station(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        first = self.latch(lib, self.PORT, 1)
        self.assertEqual(first[6] & FLAG_FIRST, FLAG_FIRST)       # the first window after boot
        self.assertEqual(self.slot(first, 0)[2], PARTIAL)
        return lib, devs[self.KIND]

    def test_minute_mean_of_four_samples(self):
        lib, dev = self.good_station()
        lib.h_run(MINUTE)
        snap = self.latch(lib, self.PORT, 2)
        t, h = self.expected(lib, 0x8000, 0x8000)
        self.assertEqual(snap[6] & FLAG_FIRST, 0)
        self.assertEqual(self.slot(snap, 0), (t & 0xFFFF_FFFF, 4, GOOD))
        self.assertEqual(self.slot(snap, 1), (h, 4, GOOD))
        self.assertTrue(59_000 <= be(snap, 4, 2) <= 61_000)

    def test_mean_of_different_samples_rounds_half_up(self):
        lib, dev = self.good_station()
        values = [(0x6000, 0x4000), (0x6001, 0x4001), (0x7000, 0x5000), (0x7003, 0x5003)]
        for raw in values:
            self.set(lib, dev, *raw)
            lib.h_run(15_000)
        snap = self.latch(lib, self.PORT, 2)
        ts, hs = zip(*(self.expected(lib, *raw) for raw in values), strict=True)
        self.assertEqual(signed16(self.slot(snap, 0)[0] & 0xFFFF), (sum(ts) * 2 + 4) // 8)
        self.assertEqual(self.slot(snap, 1)[0], (sum(hs) * 2 + 4) // 8)

    def test_mean_rounds_half_up_below_zero(self):
        # Below zero the mean rounds to the nearest (half up), not toward zero as C division does:
        # -1, -2, -2, -2 is -1.75, so -2 (truncation would give -1).
        lib, dev = self.good_station()
        near_zero = range(16_800, 16_900)                          # T = -45 + 175 S / 2^16 crosses 0 here
        raw = {self.expected(lib, r, 0x8000)[0]: r for r in near_zero}
        for t_raw in (raw[-1], raw[-2], raw[-2], raw[-2]):
            self.set(lib, dev, t_raw, 0x8000)
            lib.h_run(15_000)
        self.assertEqual(signed16(self.slot(self.latch(lib, self.PORT, 2), 0)[0] & 0xFFFF), -2)

    def test_three_samples_is_partial(self):
        lib, dev = self.good_station()
        lib.h_run(15_000)
        lib.h_device_mode(dev, DM_NACK_ADDR, 0, 1)
        lib.h_run(15_000)
        lib.h_device_mode(dev, DM_OK, 0, 1)
        lib.h_run(30_000)
        snap = self.latch(lib, self.PORT, 2)
        self.assertEqual(self.slot(snap, 0)[1:], (3, PARTIAL))

    def test_absent_is_missing(self):
        lib, dev = self.good_station()
        lib.h_remove_device(dev)
        lib.h_run(MINUTE)
        snap = self.latch(lib, self.PORT, 2)
        self.assertEqual(self.slot(snap, 0), (0, 0, MISSING))
        self.assertEqual(lib.h_probe(self.PORT), 0)

    def test_a_bus_error_is_a_bus_fault_not_an_absence(self):
        lib, dev = self.good_station()
        lib.h_device_mode(dev, DM_BUS_ERROR, 0, 1)
        lib.h_run(15_000)
        self.assertEqual(lib.h_probe(self.PORT), -1)               # WSMP-P3: the module stays in the layout

    def test_a_read_nack_is_a_bus_fault_not_an_absence(self):
        lib, dev = self.good_station()
        lib.h_device_mode(dev, DM_NACK_DATA, 0, 1)
        seq = lib.h_probe_seq(self.PORT)
        lib.h_run(15_000)
        self.assertNotEqual(lib.h_probe_seq(self.PORT), seq)
        self.assertEqual(lib.h_probe(self.PORT), -1)

    def test_sample_straddling_latch_counts_once(self):
        # Review Focus 2: the latch comes between the command and the read of one sample. That
        # sample belongs to the next window, never to both and never to none.
        lib, dev = self.good_station()
        lib.h_run(MINUTE - 15_000)                                 # three samples of this minute
        lib.h_tick_all()                                           # the fourth sample starts ...
        lib.h_advance(5)                                           # ... and its first transfer completes
        a = self.latch(lib, self.PORT, 2)
        lib.h_run(MINUTE)
        b = self.latch(lib, self.PORT, 3)
        self.assertEqual(self.slot(a, 0)[1] + self.slot(b, 0)[1], 3 + 4)
        self.assertEqual(self.slot(a, 0)[1], 3)


class Sht45(TempHumidity, Harness):
    PORT, TYPE, KIND = P_AIR_TH, 1, DEVK_SHT45
    DEVICES = [(DEVK_SHT45, 0x44)]

    def set(self, lib, dev, t_raw, h_raw):
        lib.h_sht45_set(dev, t_raw, h_raw, 0)

    def expected(self, lib, t_raw, h_raw):
        t, h = ctypes.c_int16(), ctypes.c_uint16()
        self.assertEqual(lib.h_sht45_parse(t_raw, h_raw, ctypes.byref(t), ctypes.byref(h)), 0)
        return t.value, h.value

    def test_a_bad_crc_is_a_bus_fault_and_recovers_the_bus(self):
        lib, dev = self.good_station()
        deinits = lib.h_deinits()
        lib.h_sht45_set(dev, 0x8000, 0x8000, 1)
        lib.h_run(15_000)
        self.assertEqual(lib.h_probe(self.PORT), -1)
        self.assertEqual(lib.h_deinits(), deinits + 1)              # as the earlier driver: one recovery
        lib.h_sht45_set(dev, 0x8000, 0x8000, 0)
        lib.h_run(15_000)
        self.assertEqual(lib.h_probe(self.PORT), 1)                 # the next sample is good


class Shtc3(TempHumidity, Harness):
    PORT, TYPE, KIND = P_ENCL_TH, 4, DEVK_SHTC3
    DEVICES = [(DEVK_SHTC3, 0x70)]

    def set(self, lib, dev, t_raw, h_raw):
        lib.h_shtc3_set(dev, t_raw, h_raw)

    def expected(self, lib, t_raw, h_raw):
        # SHTC3 datasheet section 5.11: T = -45 + 175 S/2^16, RH = 100 S/2^16; in 0.01, rounded half up.
        return (17500 * t_raw + 32768) // 65536 - 4500, (10000 * h_raw + 32768) // 65536

    def test_the_sensor_sleeps_between_samples(self):
        lib, dev = self.good_station()
        lib.h_run(15_000)
        self.assertEqual(lib.h_shtc3_asleep(dev), 1)


class SingleMean(Conformance):
    """The pressure and UVA modules: one mean channel each (WSMP section 4.4, types 2 and 3)."""
    CHANNELS = 1

    def good_station(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        first = self.latch(lib, self.PORT, 1)
        self.assertEqual(self.slot(first, 0)[2], PARTIAL)          # the first window after boot
        return lib, devs[self.KIND]

    def test_mean_of_four_samples(self):
        lib, dev = self.good_station()
        lib.h_run(MINUTE)
        snap = self.latch(lib, self.PORT, 2)
        self.assertEqual(self.slot(snap, 0), (self.EXPECTED, 4, GOOD))

    def test_wrong_chip_id_is_absent(self):
        lib, dev = self.good_station()
        lib.h_reg_set_id(dev, self.WRONG_ID)
        lib.h_run(15_000)
        self.assertEqual(lib.h_probe(self.PORT), 0)
        lib.h_run(MINUTE - 15_000)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (0, 0, MISSING))   # every sample saw the wrong chip

    def test_absent_is_missing(self):
        lib, dev = self.good_station()
        lib.h_remove_device(dev)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (0, 0, MISSING))
        self.assertEqual(lib.h_probe(self.PORT), 0)

    def test_replug_configures_the_part_again(self):
        lib, dev = self.good_station()
        lib.h_reg_power_cycle(dev)                                 # the part forgets its configuration
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (self.EXPECTED, 4, GOOD))


class Bmp581(SingleMean, Harness):
    PORT, TYPE, KIND, WRONG_ID = P_PRESSURE, 2, DEVK_BMP581, 0x51
    DEVICES = [(DEVK_BMP581, 0x47)]
    EXPECTED = 10133                                               # 101,325 Pa = 1013.25 hPa, scale -1, half up

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_bmp581_set(devs[DEVK_BMP581], 101_325 * 64)          # PRESS_DATA: Pa x 64 (datasheet 4.3.8)
        return lib, devs


class Ltr390(SingleMean, Harness):
    PORT, TYPE, KIND, WRONG_ID = P_UVA, 3, DEVK_LTR390, 0xB1
    DEVICES = [(DEVK_LTR390, 0x53)]
    EXPECTED = 123_456

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_ltr390_set(devs[DEVK_LTR390], 123_456)
        return lib, devs

    def test_counts_are_20_bit(self):
        lib, dev = self.good_station()
        lib.h_ltr390_set(dev, (1 << 20) - 1)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[0], (1 << 20) - 1)


class Power(Conformance, Harness):
    """The battery and charger module (WSMP section 4.4, type 5): INA228, MAX17048, bq24074 pins."""
    PORT, TYPE, CHANNELS = P_POWER, 5, 7
    DEVICES = [(DEVK_INA228, 0x40), (DEVK_MAX17048, 0x36)]
    PGOOD, CHG = 1, 2                     # board_charger_pins(): bit 0 PGOOD asserted, bit 1 CHG asserted

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        if DEVK_INA228 in devs:
            lib.h_ina228_set(devs[DEVK_INA228], 4_000_000, 0)      # 4.000 V, no current
        if DEVK_MAX17048 in devs:
            lib.h_max17048_set(devs[DEVK_MAX17048], 87)
        return lib, devs

    def slots(self, snap):
        return [self.slot(snap, i) for i in range(7)]

    def test_charge_and_discharge_counters(self):
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_ina228_set(ina, 4_000_000, 500_000)                  # +500 mA (charging) at 4.000 V for 60 s
        lib.h_run(MINUTE)
        lib.h_ina228_set(ina, 4_000_000, -250_000)                 # -250 mA for 120 s
        lib.h_run(2 * MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 1))
        # Energy in, energy out, charge in, charge out: whole mWh and mAh since boot, from the INA228's
        # own accumulators. Each 1 s step counts as in or out by the sign of its charge. In: the 60 s
        # at +0.5 A, 33.3 mWh and 8.33 mAh. Out: 119 s at -0.25 A up to the last sample before the
        # latch, 33.1 mWh and 8.26 mAh.
        self.assertEqual([s[i][0] for i in (1, 2, 3, 4)], [33, 33, 8, 8])
        lib.h_ina228_set(ina, 4_000_000, 500_000)
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual([s[i][0] for i in (1, 3)], [66, 16])       # 119 s: 66.1 mWh, 16.53 mAh: the remainder was kept
        self.assertEqual(s[0][:1], (4000,))                         # voltage mean, 1 mV

    def test_a_burst_between_samples_is_counted(self):
        # A 250 ms load between two 1 s samples (a LoRa transmission) never coincides with a sample:
        # only the part's accumulators see it. 40 bursts of 4 A x 0.25 s = 40 A s = 11.1 mAh.
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_run(1000)
        for _ in range(40):
            lib.h_run(250)                                         # from a sample to 0.25 s after it
            lib.h_ina228_set(ina, 4_000_000, -4_000_000)
            lib.h_run(250)
            lib.h_ina228_set(ina, 4_000_000, 0)
            lib.h_run(500)
        lib.h_run(1000)                                            # the sample after the last burst
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual((s[4][0], s[3][0]), (11, 0))              # charge out, charge in

    def test_a_silent_reset_of_the_monitor_recalibrates(self):
        # A brown-out clears SHUNT_CAL and the accumulators with no bus error. The module sees the
        # wrong SHUNT_CAL, calibrates again and counts on from a new base: at most one step is lost.
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_ina228_set(ina, 4_000_000, 1_000_000)
        lib.h_run(30_000)
        lib.h_ina228_power_cycle(ina)
        lib.h_run(30_000)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertIn(s[3][0], (15, 16))                           # 1 A for 57 to 59 s: 15.8 to 16.4 mAh

    def test_counters_never_reset_at_latch(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_ina228_set(devs[DEVK_INA228], 4_000_000, 1_000_000)
        lib.h_run(MINUTE)
        a = self.slots(self.latch(lib, self.PORT, 1))
        lib.h_run(MINUTE)
        b = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual((a[3][0], b[3][0]), (16, 33))              # 59 s then 119 s at 1 A: 16.4, 33.1 mAh

    def test_charger_states_from_pins(self):
        lib, _ = self.station(self.DEVICES)
        for pins, state in ((0, 0), (self.PGOOD | self.CHG, 1), (self.PGOOD, 2), (self.CHG, 0)):
            with self.subTest(pins=pins):
                lib.h_charger_pins(pins)
                lib.h_run(MINUTE)
                self.assertEqual(self.slots(self.latch(lib, self.PORT, 10 + pins))[6][0], state)

    def test_soc_point_and_missing_without_gauge(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.assertEqual(self.slots(self.latch(lib, self.PORT, 1))[5][0], 87)
        lib, _ = self.station([(DEVK_INA228, 0x40)])
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual(s[5][2], MISSING)
        self.assertNotEqual(s[0][2], MISSING)                      # the module is present without its gauge
        self.assertEqual(lib.h_probe(self.PORT), 1)

    def test_absent_without_the_monitor(self):
        lib, _ = self.station([(DEVK_MAX17048, 0x36)])
        lib.h_run(MINUTE)
        self.assertEqual(lib.h_probe(self.PORT), 0)

    def test_voltage_is_good_after_the_first_window(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(MINUTE)
        self.assertEqual(self.slots(self.latch(lib, self.PORT, 2))[0][1:], (60, GOOD))   # one a second


class Wind(Conformance, Harness):
    """The wind module (WSMP section 4.4, type 6): cup pulses, 3-s gust, vane vector sums."""
    PORT, TYPE, CHANNELS = P_WIND, 6, 4
    DEVICES = []

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_vane_mv(wind_ref.vane_mv(0))                         # the vane points north
        return lib, devs

    def slots(self, snap):
        return [self.slot(snap, i) for i in range(4)]

    def second_window(self, lib, per_tick=None, position=0):
        """The first window is partial; return the snapshot of the next minute."""
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_vane_mv(wind_ref.vane_mv(position))
        bins = []
        for i in range(MINUTE // 250):
            n = per_tick(i) if per_tick else 0
            bins.append(n)
            lib.h_pulses_add(n)
            lib.h_run(250)
        return self.slots(self.latch(lib, self.PORT, 2)), bins

    def test_pulse_counter_and_gust_match_reference(self):
        lib, _ = self.station([])
        s, bins = self.second_window(lib, lambda i: (i * 7) % 5 + (9 if 100 <= i < 108 else 0))
        self.assertEqual(s[0][0], sum(bins))                       # the counter since boot (no pulses before)
        self.assertEqual(s[1][0], wind_ref.gust_centi(bins))
        self.assertEqual(s[1][2], GOOD)

    def test_vector_sums_for_each_of_16_positions(self):
        for position in range(16):
            with self.subTest(position=position):
                lib, _ = self.station([])
                s, _ = self.second_window(lib, position=position)
                east, north = wind_ref.unit_vector_centi(position)
                self.assertEqual((s[2][1], s[3][1]), (60, 60))         # one vane sample a second
                self.assertEqual((signed16(s[2][0] & 0xFFFF), signed16(s[3][0] & 0xFFFF)), (60 * east, 60 * north))

    def test_337_and_22_degrees_average_to_north(self):
        lib, _ = self.station([])
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        for position in (15, 1) * 30:                              # 337.5 and 22.5 degrees, a second each
            lib.h_vane_mv(wind_ref.vane_mv(position))
            lib.h_run(1000)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual(signed16(s[2][0] & 0xFFFF), 0)            # never by averaging angles: east cancels
        self.assertGreater(signed16(s[3][0] & 0xFFFF), 0)          # the mean points north

    def test_counter_wrap_and_torn_read(self):
        # Review Focus 3: the 16-bit counter wraps between two reads, and one read changes between
        # the read and its confirming read. The total stays exact.
        lib, _ = self.station([])
        lib.h_pulse_counter_set(65_530)
        lib.h_run(250)
        lib.h_pulses_add(26)                                       # 65,530 -> 20: across the wrap
        lib.h_pulse_tear(1)                                        # the next read sees the counter move once
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual(s[0][0], 26 + 1)                          # the 26 pulses and the one that tore the read

    def test_no_vane_is_absent(self):
        lib, _ = self.station([])
        lib.h_vane_mv(3_300)                                       # unplugged: the pull-up reads the rail
        lib.h_run(2_000)
        self.assertEqual(lib.h_probe(self.PORT), 0)
        lib.h_vane_mv(wind_ref.vane_mv(4))
        lib.h_run(2_000)
        self.assertEqual(lib.h_probe(self.PORT), 1)


class Rain(Conformance, Harness):
    """The rain module (WSMP section 4.4, type 7): tips with a 100 ms lockout, on by a stored setting."""
    PORT, TYPE, CHANNELS = P_RAIN, 7, 1
    DEVICES = []

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_rain_enable(1)
        return lib, devs

    def tips(self, lib, gaps_ms):
        for gap in gaps_ms:
            lib.h_rain_tip()
            lib.h_advance(gap)

    def test_twenty_tips_count_twenty(self):
        lib, _ = self.station([])
        self.tips(lib, [200] * 20)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 1), 0)[0], 20)

    def test_bounce_inside_lockout_is_one_tip(self):
        lib, _ = self.station([])
        self.tips(lib, [5, 30, 64, 1])                             # 0, 5, 35 and 99 ms: one bucket tip
        lib.h_advance(200)
        self.tips(lib, [1])                                        # 300 ms: the next tip
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 1), 0)[0], 2)

    def test_counter_never_resets_at_latch(self):
        lib, _ = self.station([])
        self.tips(lib, [200] * 3)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        self.tips(lib, [200] * 4)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[:2], (7, 1))

    def test_disabled_is_absent(self):
        lib, _ = self.station([])
        lib.h_rain_enable(0)
        lib.h_run(2_000)
        self.assertEqual(lib.h_probe(self.PORT), 0)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 1), 0)[2], MISSING)
        lib.h_rain_enable(1)
        seq = lib.h_probe_seq(self.PORT)
        lib.h_run(2_000)
        self.assertEqual(lib.h_probe(self.PORT), 1)
        self.assertNotEqual(lib.h_probe_seq(self.PORT), seq)      # the setting is probed again, so it debounces


if __name__ == '__main__':
    unittest.main()
