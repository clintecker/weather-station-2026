"""The station's local WSMP modules (firmware/stage0-node/App/wsmp_local.c and mod_*.c) on the host.

firmware/host/wsmp_harness.c runs the modules on the shared I2C bus (App/i2c_bus.c) and the host bus
model (firmware/host/i2c_sim.c). The Conformance mixin holds the subset of the WSMP section 14 checks
that the host build can run (section 14 lists what it does not cover yet) for every module; each module class adds its own cases. Expected values come from docs/module-protocol.md
and the parts' datasheets. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import ROOT, WSMP_APP, fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
    import wsmp_wind_ref as wind_ref
except ImportError:
    from tests.toolchain import ROOT, WSMP_APP, fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>
    from tests import wsmp_wind_ref as wind_ref

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048 = 2, 3, 4, 5, 6, 7
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
DM_BUS_ERROR = 6
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_BATTERY, P_WIND, P_RAIN, P_RAILS = range(1, 9)
GOOD, PARTIAL, SUSPECT, MISSING, WARMING_UP, FAULT, NOT_FITTED = range(7)
FLAG_FIRST, FLAG_LONG = 1, 2
# The counter link probe (App/board_inputs.h, build-progression record M7): enum board_link, enum
# meter_link (worst last), the low reads in a row that make a verdict, and 24 h of 15-minute probes.
LINK_CUPS, LINK_RAIN = 0, 1
METER_OK, CUPS_SUSPECT, VANE_OUT, CUPS_OPEN, RAIN_OPEN = range(5)
LINK_LOWS, LOWS_DAY = 3, 24 * 4 + 1
BOOT = 0x0102_0304
MINUTE = 60_000


def be(b, i, n):
    return int.from_bytes(b[i:i + n], 'big')


def signed16(v):
    return v - 0x10000 if v & 0x8000 else v


class Sources(unittest.TestCase):
    def test_the_firmware_builds_every_module_the_tests_build(self):
        # tests/toolchain.py WSMP_APP and the Makefile list the same App files: a module added to one
        # and not the other is either untested or not in the firmware.
        makefile = (ROOT/'firmware/stage0-node/Makefile').read_text()
        for name in WSMP_APP:
            self.assertIn(f'App/{name}.c', makefile)

    def test_the_firmware_builds_the_identity_code_with_its_warnings(self):
        # The module record, calibration and verdict code (slice 1) is in the firmware build, so the
        # firmware's full warning set and -fanalyzer apply to it, not only the host tests' flags.
        makefile = (ROOT/'firmware/stage0-node/Makefile').read_text()
        for name in ('wsmp', 'wsmp_cal', 'wsmp_ident'):
            self.assertIn(f'$(ROOT)/firmware/common/{name}.c', makefile)


@needs_cc
class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'modules', *wsmp_sources())
        cls.library = lib._name

    def station(self, devices, start_ms=0):
        """A fresh station (its own copy of the library: statics start at zero) with these devices.
        start_ms is the clock when the modules start: a warm reset does not set the board clock to 0."""
        lib = fresh_station(self, self.library)
        lib.h_now_ms.restype = ctypes.c_uint32
        lib.h_advance.argtypes = [ctypes.c_uint32]
        lib.h_advance(start_ms)
        devs = {kind: lib.h_add_device(kind, addr) for kind, addr in devices}
        lib.h_init(BOOT)
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

    def bound_station(self, quantity, kind, offset, gain):
        """A station whose port driver was bound at boot to a module with one calibration entry, past
        its first (partial) window."""
        lib, devs = self.station(self.DEVICES)
        lib.h_bind(self.PORT, quantity, kind, offset, gain)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        return lib, devs[self.KIND]

    def test_identity_fields(self):
        lib, _ = self.station(self.DEVICES)
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(self.PORT, idb, desc)
        idb = bytes(idb)
        self.assertEqual(idb[:4], b'WS\x01\x01')                # WSMP 1.1 (not fitted, WSMP-V2)
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
        # The parser's raw value, then the crop of a port module (RH 0 to 100 %; these words are inside it).
        t, h = ctypes.c_int32(), ctypes.c_int32()
        self.assertEqual(lib.h_sht45_parse(t_raw, h_raw, ctypes.byref(t), ctypes.byref(h)), 0)
        return t.value, min(max(h.value, 0), 10_000)

    # RH = -6 + 125 S / 65535 and T = -45 + 175 S / 65535 (SHT4x datasheet 4.6), in 0.01.
    RH_MINUS_2, RH_102, RH_MINUS_6, RH_119, T_70 = 2097, 56_622, 0, 0xFFFF, 43_065

    def live(self, lib, unit=0):
        c, rh = ctypes.c_int32(), ctypes.c_int32()
        return lib.h_th_live(unit, ctypes.byref(c), ctypes.byref(rh)), c.value, rh.value

    def test_th_live_after_sample(self):
        # The screen's value is the sample the window took: 25.00 degC and 56.50 %RH.
        lib, devs = self.station(self.DEVICES)
        self.assertEqual(self.live(lib)[0], 0)                     # nothing yet
        self.set(lib, devs[self.KIND], 0x6666, 0x8000)             # -45 + 175 x 26214 / 65535 = 25.00; -6 + 125 x 32768 / 65535 = 56.50
        lib.h_run(1_000)
        self.assertEqual(self.live(lib), (1, 2500, 5650))

    def test_th_live_goes_stale(self):
        lib, devs = self.station(self.DEVICES)
        self.set(lib, devs[self.KIND], 0x6666, 0x8000)
        lib.h_run(1_000)
        self.assertEqual(self.live(lib)[0], 1)
        lib.h_remove_device(devs[self.KIND])
        lib.h_run(31_000)                                          # no reply for 31 s
        self.assertEqual(self.live(lib)[0], 0)

    def quarter(self, lib, dev, samples):
        """One window of four samples, (t_raw, h_raw) each, then the latch's (temperature, RH) slots."""
        for raw in samples:
            self.set(lib, dev, *raw)
            lib.h_run(15_000)
        snap = self.latch(lib, self.PORT, 2)
        return self.slot(snap, 0), self.slot(snap, 1)

    def test_rh_within_the_crop_margin_is_cropped_and_good(self):
        # Section 6.9: -3 to 0 % reports 0 % good, 100 to 103 % reports 100 % good.
        for h_raw, want in ((self.RH_MINUS_2, 0), (self.RH_102, 10_000)):
            with self.subTest(h_raw=h_raw):
                lib, dev = self.good_station()
                _, rh = self.quarter(lib, dev, [(0x8000, h_raw)] * 4)
                self.assertEqual(rh, (want, 4, GOOD))

    def test_rh_beyond_the_margin_is_suspect_and_out_of_the_sum(self):
        # One suspect RH sample: the RH mean is the other three's, its quality suspect, and the
        # temperature keeps all four samples (per-channel counts, PORT-19).
        for h_raw in (self.RH_MINUS_6, self.RH_119):
            with self.subTest(h_raw=h_raw):
                lib, dev = self.good_station()
                t, rh = self.quarter(lib, dev, [(0x8000, 0x8000)] * 3 + [(0x8000, h_raw)])
                self.assertEqual(rh, (self.expected(lib, 0x8000, 0x8000)[1], 3, SUSPECT))
                self.assertEqual(t[1:], (4, GOOD))

    def test_a_window_of_only_suspect_samples_is_missing(self):
        lib, dev = self.good_station()
        t, rh = self.quarter(lib, dev, [(0x8000, self.RH_MINUS_6)] * 4)
        self.assertEqual(rh, (0, 0, MISSING))
        self.assertEqual(t[1:], (4, GOOD))

    def test_suspect_wins_over_partial(self):
        lib, devs = self.station(self.DEVICES)
        self.set(lib, devs[self.KIND], 0x8000, self.RH_MINUS_6)
        lib.h_run(15_000)
        self.set(lib, devs[self.KIND], 0x8000, 0x8000)
        lib.h_run(MINUTE - 15_000)
        first = self.latch(lib, self.PORT, 1)                      # the first window: partial, but ...
        self.assertEqual(self.slot(first, 1)[1:], (3, SUSPECT))   # ... a suspect sample wins
        self.assertEqual(self.slot(first, 0)[1:], (4, PARTIAL))

    def test_air_temperature_above_its_physical_range_is_suspect(self):
        # A port module's air temperature crops to the registry's -80 to 60 C, margin 0.
        lib, dev = self.good_station()
        t, rh = self.quarter(lib, dev, [(0x8000, 0x8000)] * 3 + [(self.T_70, 0x8000)])
        self.assertEqual(t[1:], (3, SUSPECT))
        self.assertEqual(rh[1:], (4, GOOD))

    def test_calibration_comes_before_the_crop(self):
        # RH 99 % + 3.00 % is 102 %: 100 % good. + 5.00 % is 104 %: suspect. Temperature + 1.00 C.
        rh99 = round(105 * 65535 / 125)                            # 99.0 %RH
        for offset, want in ((300, (10_000, 4, GOOD)), (500, (0, 0, MISSING))):
            with self.subTest(offset=offset):
                lib, dev = self.bound_station(2, 0, offset, 1_000_000)
                _, rh = self.quarter(lib, dev, [(0x8000, rh99)] * 4)
                self.assertEqual(rh, want)
        lib, dev = self.bound_station(1, 2, 100, 1_000_000)
        t, _ = self.quarter(lib, dev, [(0x8000, 0x8000)] * 4)
        self.assertEqual(t, (4250 + 100, 4, GOOD))

    def test_a_bind_starts_a_fresh_window(self):
        # Section 6.7: the driver's window is reset at the bind, so no sample of the old module is in
        # the new module's first window.
        lib, dev = self.good_station()
        lib.h_run(30_000)
        lib.h_bind(self.PORT, 0, 0, 0, 0)
        lib.h_run(MINUTE)
        snap = self.latch(lib, self.PORT, 2)
        self.assertEqual(snap[6] & FLAG_FIRST, FLAG_FIRST)
        self.assertEqual(self.slot(snap, 0)[1], 4)

    def serial(self, lib):
        v = ctypes.c_uint32()
        rc = lib.h_th_serial_result(ctypes.byref(v))
        return rc, v.value

    def test_the_serial_read(self):
        lib, dev = self.good_station()
        lib.h_sht45_set_serial(dev, 0x1234_ABCD, 0)
        lib.h_th_serial_request()
        self.assertEqual(self.serial(lib)[0], 0)                   # requested, not yet read
        lib.h_run(1000)
        self.assertEqual(self.serial(lib), (1, 0x1234_ABCD))

    def test_the_serial_read_never_splits_a_measurement(self):
        # Section 6.7: the 0x89 read is a step from ST_IDLE, never between 0xFD and its 6-byte read;
        # a sample that falls due during it is deferred, not lost.
        lib, dev = self.good_station()
        lib.h_sht45_set_serial(dev, 0x0102_0304, 0)
        lib.h_tick_all()                                           # a sample starts (0xFD) ...
        lib.h_th_serial_request()                                  # ... and the serial is asked for
        lib.h_run(MINUTE - 250)
        self.assertEqual(self.serial(lib), (1, 0x0102_0304))
        self.assertEqual(lib.h_sht45_interleaved(), 0)
        self.assertEqual(lib.h_sht45_read_too_early(), 0)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[1:], (4, GOOD))

    def test_a_failed_serial_read_is_not_a_probe(self):
        # A failed identity read is not absence and not a missed probe: the probe stays as it was.
        for bad, rc in ((1, -4), (2, -2)):
            with self.subTest(bad=bad):
                lib, dev = self.good_station()
                lib.h_sht45_set_serial(dev, 0x0102_0304, bad)
                lib.h_run(5000)                                    # between two samples
                seq = lib.h_probe_seq(self.PORT)
                lib.h_th_serial_request()
                lib.h_run(1000)
                self.assertEqual(self.serial(lib)[0], rc)
                self.assertEqual((lib.h_probe_seq(self.PORT), lib.h_probe(self.PORT)), (seq, 1))

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

    def test_the_enclosure_sensor_keeps_its_125_c_check(self):
        # An on-board module keeps today's checks (section 6.9): 70 C is not cropped or suspect.
        lib, dev = self.good_station()
        t70 = (7000 + 4500) * 65536 // 17500
        lib.h_shtc3_set(dev, t70, 0x8000)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (self.expected(lib, t70, 0x8000)[0], 4, GOOD))

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

    def live(self, lib):
        v = ctypes.c_int32()
        return lib.h_reg_live(self.UNIT, ctypes.byref(v)), v.value

    def test_reg_live_value_and_stale(self):
        lib, devs = self.station(self.DEVICES)
        self.assertEqual(self.live(lib)[0], 0)                     # nothing yet
        lib.h_run(1_000)
        self.assertEqual(self.live(lib), (1, self.EXPECTED))
        lib.h_remove_device(devs[self.KIND])
        lib.h_run(31_000)
        self.assertEqual(self.live(lib)[0], 0)

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
    PORT, TYPE, KIND, WRONG_ID, UNIT = P_PRESSURE, 2, DEVK_BMP581, 0x51, 0
    DEVICES = [(DEVK_BMP581, 0x47)]
    EXPECTED = 10133                                               # 101,325 Pa = 1013.25 hPa, scale -1, half up

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_bmp581_set(devs[DEVK_BMP581], 101_325 * 64)          # PRESS_DATA: Pa x 64 (datasheet 4.3.8)
        return lib, devs


class Ltr390(SingleMean, Harness):
    PORT, TYPE, KIND, WRONG_ID, UNIT = P_UVA, 3, DEVK_LTR390, 0xA2, 1
    DEVICES = [(DEVK_LTR390, 0x53)]
    EXPECTED = 123_456

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_ltr390_set(devs[DEVK_LTR390], 123_456)
        return lib, devs

    def test_only_the_part_number_nibble_of_part_id_is_compared(self):
        # PART_ID 0x06: the high nibble is the part number (0xB), the low nibble the revision.
        for part_id in (0xB0, 0xB1, 0xB3):
            with self.subTest(part_id=part_id):
                lib, dev = self.good_station()
                lib.h_reg_set_id(dev, part_id)
                lib.h_run(MINUTE)
                self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (self.EXPECTED, 4, GOOD))

    def test_a_dark_count_offset_never_goes_negative(self):
        # Section 6.9: a UVA offset of -5 on night readings of 0 to 2 gives 0 (margin 16 below), never
        # a negative mean that would pack as 16,777,212 in 3 unsigned bytes.
        lib, dev = self.bound_station(8, 0, -5, 1_000_000)
        lib.h_ltr390_set(dev, 2)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (0, 4, GOOD))

    def test_a_gain_above_the_range_is_suspect_not_wrapped(self):
        lib, dev = self.bound_station(8, 0, 0, 10_000_000)
        lib.h_ltr390_set(dev, 200_000)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0), (0, 0, MISSING))

    def test_counts_are_20_bit(self):
        lib, dev = self.good_station()
        lib.h_ltr390_set(dev, (1 << 20) - 1)
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[0], (1 << 20) - 1)


class PowerStation:
    """The battery and rails modules (App/mod_power.c over App/power_acq.c; power telemetry design
    sections 5.3, 8.1, 8.4, 8.5 and 9.6) in the default profile A: the battery INA228 at 0x40 (shunt in
    the battery path, VBUS on its sense lead to the OUT connector, record P5), the MAX17048 at 0x36 on
    the CELL+ node (record M4: VCELL includes the pack-lead drop), and the board
    ADC (ISET, the PA10 charger-input divider, VREFINT) through sim_core.c's h_power_adc."""
    DEVICES = [(DEVK_INA228, 0x40), (DEVK_MAX17048, 0x36)]
    KIND = DEVK_INA228
    PGOOD, CHG = 1, 2                     # board_charger_pins(): bit 0 PGOOD asserted, bit 1 CHG asserted
    OUT_UV, CELL_UV = 4_400_000, 3_900_000

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_power_health.argtypes = [ctypes.c_int32 * 11]
        if DEVK_INA228 in devs:
            lib.h_ina228_set(devs[DEVK_INA228], self.OUT_UV, 0)    # the charger OUT at 4.400 V, no current
        if DEVK_MAX17048 in devs:
            lib.h_max17048_set(devs[DEVK_MAX17048], 87)
            lib.h_max17048_cell(self.CELL_UV)                       # the cell at 3.900 V
        return lib, devs

    def slots(self, snap, n=None):
        return [self.slot(snap, i) for i in range(n or self.CHANNELS)]

    def both(self, lib, token):
        """Latches the battery then the rails module with one token, as the station host does."""
        return (self.slots(self.latch(lib, P_BATTERY, token), 6), self.slots(self.latch(lib, P_RAILS, token), 7))

    def health(self, lib):
        out = (ctypes.c_int32 * 11)()
        lib.h_power_health(out)
        return dict(zip(HEALTH_KEYS, out, strict=True))


HEALTH_KEYS = ('vdda_mv', 'soc', 'chg_input_mv', 'chg_batt_mv', 'monitor_temp', 'soc_rate', 'chg_input_ma',
               'chg_batt_ma', 'chg_temp', 'pack_temp', 'charger_status')
U16_NONE, I16_NONE, U8_NONE = 0xFFFF, -32768, 0xFF


def signed32(v):
    return v - (1 << 32) if v & 0x8000_0000 else v


def pin_mv(raw, vdda_mv, ratio=1):
    """power_regs.c: the pin voltage of a 12-bit result, times the divider ratio, in mV half up."""
    uv = raw * vdda_mv * 1000 // 4095
    return (uv * ratio + 500) // 1000


class Battery(PowerStation, Conformance, Harness):
    """The battery module (port 5, WSMP type 8): the cell voltage from the gauge, the battery current
    and the energy and charge counters from the battery INA228."""
    PORT, TYPE, CHANNELS = P_BATTERY, 8, 6

    def test_the_build_is_profile_a(self):
        lib, _ = self.station(self.DEVICES)
        self.assertEqual((lib.h_power_profile(), lib.h_port_battery(), lib.h_port_rails()), (1, P_BATTERY, P_RAILS))

    def test_the_local_serial_is_a_new_series(self):
        # WSMP-C3 (design section 8.4): the type changed (5 -> 8), so the serial changed once and the
        # counters start a new series; it is not the type 5 serial of protocol version 5.
        lib, _ = self.station(self.DEVICES)
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(P_BATTERY, idb, desc)
        self.assertEqual(be(bytes(idb), 8, 8), 0x5753_0000_0508)
        self.assertNotEqual(be(bytes(idb), 8, 8), 0x5753_0000_0505)

    def test_charge_and_discharge_counters(self):
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_ina228_set(ina, self.OUT_UV, -500_000)               # VIN- -> VIN+: 500 mA into the cell for 60 s
        lib.h_run(MINUTE)
        lib.h_ina228_set(ina, self.OUT_UV, 250_000)                # VIN+ -> VIN-: 250 mA out of the cell for 120 s
        lib.h_run(2 * MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 1))
        # Energy in, energy out, charge in, charge out: whole mWh and mAh since boot, dQ x the cell's
        # VCELL (3.900 V), not the OUT voltage. In: 59 to 60 s at 0.5 A, 8.2 to 8.3 mAh and 32 mWh.
        # Out: 119 to 120 s at 0.25 A, 8.26 to 8.33 mAh and 32.2 to 32.5 mWh.
        self.assertEqual([s[i][0] for i in (2, 3, 4, 5)], [32, 32, 8, 8])
        lib.h_ina228_set(ina, self.OUT_UV, -500_000)
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual([s[i][0] for i in (2, 4)], [64, 16])       # the remainder below 1 mAh was kept

    def test_the_battery_current_is_signed_and_positive_while_charging(self):
        # The mean of a steady minute: the sum of the CHARGE deltas over their time (design section 9.4).
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        for token, (ua, ma) in enumerate(((-1_000_000, 1000), (250_000, -250)), start=1):
            with self.subTest(ma=ma):
                lib.h_ina228_set(ina, self.OUT_UV, ua)             # -: VIN- -> VIN+, into the cell (sign -1)
                lib.h_run(MINUTE)
                self.latch(lib, self.PORT, 2 * token)              # the minute with the change
                lib.h_run(MINUTE)
                value, count, quality = self.slots(self.latch(lib, self.PORT, 2 * token + 1))[1]
                self.assertEqual((signed32(value), count, quality), (ma, 60, GOOD))

    def test_a_burst_between_samples_is_counted(self):
        # A 250 ms load between two 1 s samples (a LoRa transmission) never coincides with a sample:
        # only the part's CHARGE accumulator sees it. 40 bursts of 4 A x 0.25 s = 40 A s = 11.1 mAh.
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_run(1000)
        for _ in range(40):
            lib.h_run(250)                                         # from a sample to 0.25 s after it
            lib.h_ina228_set(ina, self.OUT_UV, 4_000_000)          # 4 A out of the cell
            lib.h_run(250)
            lib.h_ina228_set(ina, self.OUT_UV, 0)
            lib.h_run(500)
        lib.h_run(1000)                                            # the sample after the last burst
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual((s[5][0], s[4][0]), (11, 0))              # charge out, charge in

    def test_a_silent_reset_of_the_monitor_recalibrates(self):
        # A brown-out clears SHUNT_CAL and the accumulators with no bus error. The acquisition sees the
        # wrong SHUNT_CAL, calibrates again and counts on from a new base: at most a step or two is lost.
        lib, devs = self.station(self.DEVICES)
        ina = devs[DEVK_INA228]
        lib.h_ina228_set(ina, self.OUT_UV, -1_000_000)
        lib.h_run(30_000)
        lib.h_ina228_power_cycle(ina)
        lib.h_run(30_000)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertIn(s[4][0], (15, 16))                           # 1 A for 56 to 59 s: 15.6 to 16.4 mAh

    def test_counters_never_reset_at_latch(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_ina228_set(devs[DEVK_INA228], self.OUT_UV, -1_000_000)
        lib.h_run(MINUTE)
        a = self.slots(self.latch(lib, self.PORT, 1))
        lib.h_run(MINUTE)
        b = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual((a[4][0], b[4][0]), (16, 33))              # 59 s then 119 s at 1 A: 16.4, 33.1 mAh

    def test_the_cell_voltage_comes_from_the_gauge_not_out(self):
        # OUT (4.400 V, the INA228's VBUS) and the cell (3.900 V, the gauge's VCELL) are kept apart.
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(MINUTE)
        self.assertEqual(self.slots(self.latch(lib, self.PORT, 2))[0], (3900, 4, GOOD))   # one read every 15 s

    def test_the_gauge_is_reported_without_the_ina228(self):
        # Design section 14: a gauge without its INA228 still gives the cell voltage; the module stays
        # present and only the INA228's slots are missing.
        lib, _ = self.station([(DEVK_MAX17048, 0x36)])
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual(lib.h_probe(self.PORT), 1)
        self.assertEqual(s[0], (3900, 4, GOOD))
        self.assertEqual([q for _, _, q in s[1:]], [MISSING] * 5)

    def test_present_with_every_part_absent(self):
        # PT-065, PT-124 (design sections 5.3 and 8.5): the module is fixed by the power profile. With
        # the INA228 and the gauge both dead it stays present, and every slot is missing (the map then
        # sends fields 11-16 as INVALID, not absent).
        lib, _ = self.station([])
        lib.h_run(MINUTE)
        self.assertEqual(lib.h_probe(self.PORT), 1)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual([q for _, _, q in s], [MISSING] * 6)

    def test_an_absent_gauge_is_tried_every_15_s(self):
        lib, _ = self.station([(DEVK_INA228, 0x40)])
        lib.h_run(MINUTE)
        self.assertEqual(lib.h_addr_transfers(0x36), 4)            # at 0, 15, 30 and 45 s, not every second

    def test_a_gauge_bus_fault_is_a_fault_not_an_absence(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_device_mode(devs[DEVK_MAX17048], DM_BUS_ERROR, 0, 1)
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual(s[0][2], FAULT)
        self.assertEqual([q for _, _, q in s[1:]], [GOOD] * 5)     # the INA228's slots are not touched
        lib.h_remove_device(devs[DEVK_MAX17048])
        lib.h_run(MINUTE)
        self.assertEqual(self.slots(self.latch(lib, self.PORT, 3))[0][2], MISSING)   # an absent gauge is missing

    def test_a_monitor_bus_fault_affects_only_its_slots(self):
        lib, devs = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.both(lib, 1)
        lib.h_device_mode(devs[DEVK_INA228], DM_BUS_ERROR, 0, 1)
        lib.h_run(MINUTE)
        battery, rails = self.both(lib, 2)
        self.assertEqual(battery[0], (3900, 4, GOOD))              # the gauge's slot
        self.assertEqual([q for _, _, q in battery[1:]], [FAULT] * 5)
        self.assertEqual(rails[0][2], FAULT)                       # the load voltage is the same INA228's VBUS
        self.assertEqual(lib.h_probe(self.PORT), 1)                # still present (WSMP-P3)


class Rails(PowerStation, Conformance, Harness):
    """The power rails module (port 8, WSMP type 9): load, charger input, solar and USB-C. Profile A
    fills the load voltage (the battery INA228's VBUS on OUT) and the charger input voltage (the PA10
    divider); the rest is not fitted."""
    PORT, TYPE, CHANNELS = P_RAILS, 9, 7
    VDDA = 3300

    def station(self, devices, start_ms=0):
        lib, devs = super().station(devices, start_ms)
        lib.h_power_adc.argtypes = [ctypes.c_uint16] * 4
        lib.h_power_adc(0, 2048, 1500, self.VDDA)                  # ISET 0, PA10 half scale, VDDA 3.3 V
        return lib, devs

    def test_the_local_serial_is_a_new_series(self):
        lib, _ = self.station(self.DEVICES)
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(P_RAILS, idb, desc)
        self.assertEqual(be(bytes(idb), 8, 8), 0x5753_0000_0809)   # port 8, type 9 (WSMP-C3)

    def test_profile_a_slots(self):
        lib, _ = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        lib.h_run(MINUTE)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual(s[0], (4400, 60, GOOD))                   # load voltage: OUT, a read a second
        self.assertEqual(s[2], (pin_mv(2048, self.VDDA, 3), 60, GOOD))   # charger input: 3 x the PA10 pin
        self.assertEqual([s[i] for i in (1, 3, 4, 5, 6)], [(0, 0, NOT_FITTED)] * 5)

    def test_not_fitted_slots_stay_not_fitted_with_every_part_absent(self):
        # Not fitted is a property of the build (WS_POWER_PROFILE), never of a part's state.
        lib, _ = self.station([])
        lib.h_power_adc(0, 4095, 1500, self.VDDA)                  # a clipped charger input
        lib.h_run(MINUTE)
        self.assertEqual(lib.h_probe(self.PORT), 1)
        s = self.slots(self.latch(lib, self.PORT, 1))
        self.assertEqual([q for _, _, q in s], [MISSING, NOT_FITTED, MISSING, NOT_FITTED, NOT_FITTED, NOT_FITTED, NOT_FITTED])

    def test_both_modules_share_the_latch_window(self):
        # The first module to latch with a token closes the acquisition window; the other copies it, so
        # the rails module latched second still reports the whole minute.
        lib, devs = self.station(self.DEVICES)
        lib.h_run(MINUTE)
        self.both(lib, 1)
        lib.h_run(MINUTE)
        battery, rails = self.both(lib, 2)
        self.assertEqual((battery[0], rails[0]), ((3900, 4, GOOD), (4400, 60, GOOD)))
        self.assertEqual(self.slots(self.latch(lib, P_RAILS, 2)), rails)   # a retry: the same values

    def test_the_health_values_are_cached_with_none_codes(self):
        lib, devs = self.station(self.DEVICES)
        h = self.health(lib)
        self.assertEqual(h, {**{k: U16_NONE for k in ('vdda_mv', 'soc', 'chg_input_mv', 'chg_batt_mv')},
                             **{k: I16_NONE for k in ('monitor_temp', 'soc_rate', 'chg_input_ma', 'chg_batt_ma',
                                                      'chg_temp', 'pack_temp')},
                             'charger_status': U8_NONE})       # nothing before the first latch
        lib.h_ina228_die(devs[DEVK_INA228], 31_250)
        lib.h_max17048_rate(-2_080)                            # -2.08 %/h, discharging
        lib.h_charger_pins(0)                                  # no input power: ISET gives 0 mA
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        h = self.health(lib)
        self.assertEqual((h['vdda_mv'], h['soc'], h['soc_rate'], h['monitor_temp'], h['chg_batt_ma'], h['charger_status']),
                         (self.VDDA, 87 * 256, -21, 313, 0, 0))
        self.assertEqual((h['chg_input_mv'], h['chg_batt_mv'], h['chg_input_ma'], h['chg_temp'], h['pack_temp']),
                         (U16_NONE, U16_NONE, I16_NONE, I16_NONE, I16_NONE))   # no charger ADC before phase C

    def test_the_health_status_follows_the_pins(self):
        lib, _ = self.station(self.DEVICES)
        for pins, status in ((self.PGOOD | self.CHG, 0x03), (self.PGOOD, 0x01), (0, 0x00)):
            with self.subTest(pins=pins):
                lib.h_charger_pins(pins)
                lib.h_run(MINUTE)
                self.latch(lib, self.PORT, 10 + pins)
                self.assertEqual(self.health(lib)['charger_status'], status)


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

    def live(self, lib):
        lib.h_wind_live()
        n = lib.h_wind_nbins()
        return {'speed': lib.h_wind_speed(), 'gust': lib.h_wind_gust(), 'mv': lib.h_wind_vane_mv(),
                'point': lib.h_wind_point(), 'bins': [lib.h_wind_bin(i) for i in range(n)]}

    def test_wind_live_bins_and_point(self):
        lib, _ = self.station([])
        lib.h_vane_mv(595)                                         # 2.2 kOhm on the 10 kOhm pull-up: position 6 (SE, 135 deg)
        lib.h_run(1_000)                                           # the module needs its first vane read
        lib.h_pulses_add(8)                                        # 8 pulses in one 250 ms bin
        lib.h_run(250)
        w = self.live(lib)
        self.assertEqual((w['mv'], w['point']), (595, 6))
        self.assertEqual(w['bins'][-1], 8)
        self.assertEqual(w['bins'][:-1], [0] * (len(w['bins']) - 1))
        self.assertEqual(len(w['bins']), 5)                        # 1 s of idle bins and the one with pulses

    def test_wind_live_speed_and_gust(self):
        lib, _ = self.station([])
        lib.h_run(250)                                             # the first tick only takes the counter's base
        for _ in range(12):                                        # 3 s at 8 pulses a bin: 32 Hz x 0.66698 m/s = 21.34 m/s
            lib.h_pulses_add(8)
            lib.h_run(250)
        w = self.live(lib)
        self.assertEqual((w['speed'], w['gust']), (2134, 2134))
        lib.h_run(3_000)                                           # calm again: the speed falls, the window's gust stays
        w = self.live(lib)
        self.assertEqual((w['speed'], w['gust']), (0, 2134))

    def test_wind_live_before_the_first_vane_reading_and_out_of_table(self):
        lib, _ = self.station([])
        lib.h_vane_mv(0)
        self.assertEqual((self.live(lib)['mv'], self.live(lib)['point']), (0, -1))
        lib.h_vane_mv(3_300)                                       # an unplugged vane: outside the table
        lib.h_run(1_000)
        w = self.live(lib)
        self.assertEqual((w['mv'], w['point']), (3_300, -1))

    def test_wind_live_bins_saturate_and_keep_30_s(self):
        lib, _ = self.station([])
        lib.h_run(250)                                             # the first tick only takes the counter's base
        self.assertEqual(self.live(lib)['bins'], [0])
        lib.h_pulses_add(300)
        lib.h_run(250)
        self.assertEqual(self.live(lib)['bins'], [0, 255])
        lib.h_run(40_000)
        w = self.live(lib)
        self.assertEqual(w['bins'], [0] * 120)                     # 30 s of bins; the 300 has scrolled out

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
        self.assertEqual(lib.h_meter_link(), VANE_OUT)             # the rail is outside the table too (M7)
        lib.h_vane_mv(wind_ref.vane_mv(4))
        lib.h_run(2_000)
        self.assertEqual(lib.h_probe(self.PORT), 1)
        self.assertEqual(lib.h_meter_link(), METER_OK)

    # The cups link (record M7, rows R-6 and R-16): the board's probe gives the low run (h_link_low)
    # and a real edge since the last probe (h_edge).
    def test_three_lows_are_suspect_not_fault(self):
        # Calm air with the magnet holding the reed closed reads like an open link: suspect only.
        for lows, quality, verdict in ((LINK_LOWS - 1, GOOD, METER_OK), (LINK_LOWS, SUSPECT, CUPS_SUSPECT),
                                       (LOWS_DAY - 1, SUSPECT, CUPS_SUSPECT)):
            with self.subTest(lows=lows):
                lib, _ = self.station([])
                lib.h_link_low(LINK_CUPS, lows)
                s, _ = self.second_window(lib)
                self.assertEqual((s[0][2], s[1][2]), (quality, quality))   # the counter and the gust
                self.assertEqual((s[2][2], s[3][2]), (GOOD, GOOD))         # the vane is not the cups
                self.assertEqual(lib.h_meter_link(), verdict)

    def test_suspect_becomes_fault_when_the_vane_moves(self):
        # Wind, but no cup pulse: the link is open.
        lib, _ = self.station([])
        lib.h_link_low(LINK_CUPS, LINK_LOWS)
        s, _ = self.second_window(lib, position=4)                 # north, then east in this window
        self.assertEqual((s[0][2], s[1][2]), (FAULT, FAULT))
        self.assertEqual(lib.h_meter_link(), CUPS_OPEN)
        lib.h_edge(LINK_CUPS)                                      # a real pulse: the link works after all
        self.assertEqual(lib.h_meter_link(), METER_OK)
        lib.h_run(2_000)                                           # (a new run takes probes: 30 min at least)
        lib.h_link_low(LINK_CUPS, LINK_LOWS)                       # a new run, the vane still: suspect again
        lib.h_run(2_000)
        self.assertEqual(lib.h_meter_link(), CUPS_SUSPECT)

    def test_suspect_becomes_fault_after_24_hours(self):
        lib, _ = self.station([])
        lib.h_link_low(LINK_CUPS, LOWS_DAY)
        s, _ = self.second_window(lib)
        self.assertEqual((s[0][2], s[1][2]), (FAULT, FAULT))
        self.assertEqual(lib.h_meter_link(), CUPS_OPEN)

    def test_a_real_edge_since_the_last_probe_clears_the_verdict(self):
        lib, _ = self.station([])
        lib.h_link_low(LINK_CUPS, LOWS_DAY)
        lib.h_edge(LINK_CUPS)
        s, _ = self.second_window(lib, lambda i: 1)
        self.assertEqual((s[0][2], s[1][2]), (GOOD, GOOD))
        self.assertEqual(lib.h_meter_link(), METER_OK)

    def test_the_probes_own_pulses_are_no_count(self):
        lib, _ = self.station([])

        def per_tick(i):
            if i % 60:
                return 0
            lib.h_probe_pulses(1)                                  # a probe on an open link: LPTIM1 counted its edge
            return 2                                               # and two real pulses

        s, bins = self.second_window(lib, per_tick)
        self.assertEqual(s[0][0], sum(bins))                       # only the real pulses

    def test_a_vane_reading_outside_the_table_is_flagged(self):
        # Between 21 880 and 33 000 ohm (2299 and 2502 mV at the bands' edges): no position.
        lib, _ = self.station([])
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        for second in range(60):
            lib.h_vane_mv(2_400 if second % 10 == 0 else wind_ref.vane_mv(2))
            lib.h_run(1000)
        s = self.slots(self.latch(lib, self.PORT, 2))
        self.assertEqual((s[2][1], s[2][2], s[3][2]), (54, SUSPECT, SUSPECT))   # out of the sums, and suspect
        self.assertEqual((s[0][2], s[1][2]), (GOOD, GOOD))
        lib.h_vane_mv(2_400)
        lib.h_run(1000)
        self.assertEqual(lib.h_meter_link(), VANE_OUT)
        lib.h_vane_mv(wind_ref.vane_mv(2))
        lib.h_run(1000)
        self.assertEqual(lib.h_meter_link(), METER_OK)

    def test_every_position_is_inside_its_band(self):
        for position in range(16):
            with self.subTest(position=position):
                lib, _ = self.station([])
                lib.h_vane_mv(wind_ref.vane_mv(position))
                lib.h_run(2_000)
                self.assertEqual(lib.h_meter_link(), METER_OK)


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

    def test_rain_tips_since_boot(self):
        lib, _ = self.station([])
        self.tips(lib, [200] * 3)
        self.assertEqual(lib.h_rain_tips(), 3)
        lib, _ = self.station([])
        self.tips(lib, [100 - 1, 500])                             # two closures 99 ms apart: one tip
        self.assertEqual(lib.h_rain_tips(), 1)

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

    def test_a_late_release_bounce_is_not_a_tip(self):
        # The lockout runs from the last edge: a slow tip whose contact chatters for longer than 100 ms
        # (edges 80 ms apart) is still one tip.
        lib, _ = self.station([])
        self.tips(lib, [80, 80, 300])                              # 0, 80, 160 ms, then 460 ms: two tips
        self.tips(lib, [1])
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

    # The rain link (record M7): the reed is open at rest, so three low probes with no tip since is an
    # open link between the jack-end pull-up and the MCU. mod_rain_link is the rain module's own
    # verdict (this station's vane reads 0 mV, outside the table, so #status would show the wind's).
    def test_three_lows_with_no_tip_are_a_fault(self):
        for lows, quality, verdict in ((LINK_LOWS - 1, GOOD, METER_OK), (LINK_LOWS, FAULT, RAIN_OPEN)):
            with self.subTest(lows=lows):
                lib, _ = self.station([])
                lib.h_link_low(LINK_RAIN, lows)
                lib.h_run(MINUTE)
                self.latch(lib, self.PORT, 1)
                lib.h_run(MINUTE)
                self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[2], quality)
                self.assertEqual(lib.mod_rain_link(), verdict)

    def test_a_tip_clears_the_fault(self):
        lib, _ = self.station([])
        lib.h_link_low(LINK_RAIN, LINK_LOWS)
        lib.h_run(MINUTE)
        self.latch(lib, self.PORT, 1)
        self.tips(lib, [200])
        lib.h_edge(LINK_RAIN)                                      # the board saw the tip's edge
        lib.h_run(MINUTE)
        self.assertEqual(self.slot(self.latch(lib, self.PORT, 2), 0)[::2], (1, GOOD))
        self.assertEqual(lib.mod_rain_link(), METER_OK)

    def test_a_gauge_switched_off_has_no_link_verdict(self):
        lib, _ = self.station([])
        lib.h_rain_enable(0)
        lib.h_link_low(LINK_RAIN, LINK_LOWS)
        self.assertEqual(lib.mod_rain_link(), METER_OK)

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


class RainHistory(Harness):
    """The bench screen's rain history (mod_rain_history): tips a minute for the last hour, in a ring the 250 ms
    tick rolls on mod_rain_init's minutes, and the time since the last tip. Read-only, like mod_*_live."""
    DEVICES = []

    def station(self, devices=(), start_ms=0):
        lib, devs = super().station(list(devices), start_ms)
        lib.h_rain_hist_tips.restype = lib.h_rain_hist_age.restype = ctypes.c_uint32
        return lib, devs

    def hist(self, lib):
        lib.h_rain_history()
        return [lib.h_rain_hist_min(i) for i in range(60)]

    def tip_then_run(self, lib, n, ms=MINUTE):
        """n tips 250 ms apart (past the lockout), then the station ticks on to ms after the first."""
        for _ in range(n):
            lib.h_rain_tip()
            lib.h_advance(250)
        lib.h_run(ms - 250 * n)

    def test_nothing_since_boot(self):
        lib, _ = self.station()
        lib.h_run(5 * MINUTE)
        self.assertEqual(self.hist(lib), [0] * 60)
        self.assertEqual((lib.h_rain_hist_tips(), lib.h_rain_hist_age()), (0, 0xFFFFFFFF))   # RAIN_AGE_NONE

    def test_minutes_roll_newest_last(self):
        lib, _ = self.station()
        self.tip_then_run(lib, 3)    # minute 0: 3 tips
        self.tip_then_run(lib, 0)    # minute 1: none
        self.tip_then_run(lib, 5, 30_000)   # minute 2, so far: 5
        self.assertEqual(self.hist(lib)[-3:], [3, 0, 5])
        self.assertEqual(sum(self.hist(lib)), 8)
        lib.h_run(30_250)            # the tick at 3 min: the 5 move back one
        self.assertEqual(self.hist(lib)[-4:], [3, 0, 5, 0])
        lib.h_run(56 * MINUTE)       # minute 59: the 3 are the oldest
        self.assertEqual(self.hist(lib)[0], 3)
        lib.h_run(MINUTE)            # an hour on: they are gone, the tips since boot are not
        self.assertEqual(self.hist(lib)[:2], [0, 5])
        self.assertEqual(lib.h_rain_hist_tips(), 8)

    def test_a_minute_saturates(self):
        lib, _ = self.station()
        for _ in range(300):         # 300 tips in 45 s
            lib.h_rain_tip()
            lib.h_advance(150)
        lib.h_run(1_000)
        h = self.hist(lib)
        self.assertEqual((h[-1], lib.h_rain_hist_tips()), (255, 300))

    def test_last_tip_age(self):
        lib, _ = self.station()
        lib.h_run(10_000)
        lib.h_rain_tip()
        lib.h_run(4 * MINUTE)
        self.hist(lib)
        self.assertEqual(lib.h_rain_hist_age(), 240)
        lib.h_rain_tip()
        lib.h_advance(50)            # a bounce: no tip, and no new age
        lib.h_rain_tip()
        lib.h_run(3_000)
        self.hist(lib)
        self.assertEqual((lib.h_rain_hist_age(), lib.h_rain_hist_tips()), (3, 2))

    def test_an_old_tip_stops_at_the_cap(self):
        # 99 h, RAIN_AGE_MAX_S: the age never wraps with the 49-day ms clock.
        lib, _ = self.station()
        lib.h_rain_tip()
        for _ in range(60 * 24):     # 60 days in 1 h steps, a tick each (the cap is found by a tick)
            lib.h_advance(3_600_000 - 250)
            lib.h_run(250)
        self.hist(lib)
        self.assertEqual(lib.h_rain_hist_age(), 99 * 3600)
        lib.h_rain_tip()
        lib.h_run(1_000)
        self.hist(lib)
        self.assertEqual(lib.h_rain_hist_age(), 1)

    def test_a_long_gap_clears_and_keeps_the_phase(self):
        for gap_min in (59, 60, 61, 600):
            with self.subTest(gap_min=gap_min):
                lib, _ = self.station()
                self.tip_then_run(lib, 4, 20_000)   # minute 0, at 20 s
                lib.h_advance(gap_min * MINUTE)    # no tick for the gap
                lib.h_run(250)
                h = self.hist(lib)
                self.assertEqual(h[0] == 4, gap_min == 59, h)
                self.assertEqual(sum(h), 4 if gap_min < 60 else 0)
                lib.h_rain_tip()
                lib.h_run(40_000 - 250)            # ticks to 59.75 s into the minute: still the same one
                self.assertEqual(self.hist(lib)[-1], 1)
                lib.h_run(250)                     # the minutes still start on the minute from init
                self.assertEqual(self.hist(lib)[-2:], [1, 0])

    def test_the_ms_clock_wraps(self):
        lib, _ = self.station(start_ms=2**32 - 90_000)   # 90 s before the 32-bit ms clock wraps
        self.tip_then_run(lib, 2)
        self.tip_then_run(lib, 1)    # across the wrap
        self.tip_then_run(lib, 3, 1_000)
        self.assertEqual(self.hist(lib)[-3:], [2, 1, 3])
        self.assertLess(lib.h_rain_hist_age(), 2)


class LiveReads(Harness):
    """The screen's live accessors read; they never write (mod_*_live)."""
    DEVICES = [(DEVK_SHT45, 0x44), (DEVK_SHTC3, 0x70), (DEVK_BMP581, 0x47), (DEVK_LTR390, 0x53)]

    def run_station(self, with_live):
        lib, devs = self.station(self.DEVICES)
        lib.h_rain_enable(1)
        lib.h_vane_mv(595)
        lib.h_sht45_set(devs[DEVK_SHT45], 0x6666, 0x8000, 0)
        lib.h_shtc3_set(devs[DEVK_SHTC3], 0x6666, 0x8000)
        lib.h_bmp581_set(devs[DEVK_BMP581], 101_325 * 64)
        lib.h_ltr390_set(devs[DEVK_LTR390], 123)
        a, b, c = ctypes.c_int32(), ctypes.c_int32(), ctypes.c_int32()
        for i in range(MINUTE // 250):
            lib.h_pulses_add(i % 7)
            if i % 40 == 0:
                lib.h_rain_tip()
            lib.h_run(250)
            if with_live:
                for _ in range(5):
                    for unit in (0, 1):
                        lib.h_th_live(unit, ctypes.byref(a), ctypes.byref(b))
                        lib.h_reg_live(unit, ctypes.byref(c))
                    lib.h_wind_live()
                    lib.h_rain_tips()
                    lib.h_rain_history()
        return b''.join(self.latch(lib, port, 1) for port in (P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_WIND, P_RAIN))

    def test_live_reads_do_not_change_window(self):
        plain = self.run_station(False)
        self.assertEqual(self.run_station(True), plain)
        self.assertNotEqual(plain, bytes(len(plain)))


if __name__ == '__main__':
    unittest.main()
