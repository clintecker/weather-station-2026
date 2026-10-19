"""The station's local WSMP modules (firmware/stage0-node/App/wsmp_local.c and mod_*.c) on the host.

firmware/host/wsmp_harness.c runs the modules on the shared I2C bus (App/i2c_bus.c) and the host bus
model (firmware/host/i2c_sim.c). The Conformance mixin holds the WSMP section 14 checks that every
module passes; each module class adds its own cases. Expected values come from docs/module-protocol.md
and the parts' datasheets. Host-model results, not bench evidence."""
import ctypes
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

DEVK_SHT45, DEVK_SHTC3 = 2, 3
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
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

    def station(self, devices):
        """A fresh station (its own copy of the library: statics start at zero) with these devices."""
        type(self).count += 1
        path = Path(self.tmp.name)/f'm{self.count}.so'
        shutil.copy(self.library, path)
        lib = ctypes.CDLL(str(path))
        lib.h_now_ms.restype = ctypes.c_uint32
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

    def test_a_bad_crc_is_a_bus_fault(self):
        lib, dev = self.good_station()
        lib.h_sht45_set(dev, 0x8000, 0x8000, 1)
        lib.h_run(15_000)
        self.assertEqual(lib.h_probe(self.PORT), -1)


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


if __name__ == '__main__':
    unittest.main()
