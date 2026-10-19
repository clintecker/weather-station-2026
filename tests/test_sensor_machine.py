"""The SHT45 driver (firmware/stage0-node/App/sensor.c, as built) on the shared I2C bus (App/i2c_bus.c).

firmware/host/sensor_harness.c and i2c_sim.c simulate ST's timer rounding, the sequencer, the I2C completions and
a sensor that answers, NACKs, hangs, sends a bad CRC or holds SDA low. Every case must end in
exactly one done() with the documented code, never wait, and leave the bus ready for the next
measurement. Host-model results, not bench evidence."""
import ctypes
import shutil
import tempfile
import unittest
from pathlib import Path
try:
    from toolchain import ROOT, host_library, needs_cc
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc

DEV_OK, DEV_NACK_CMD, DEV_NACK_READ, DEV_BAD_CRC, DEV_HANG_CMD, DEV_HANG_READ, DEV_BUSY = range(7)
BUS_STUCK, TIMEOUT = -5, -6


@needs_cc
class SensorMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        lib = host_library(cls, 'sensormachine', '-I', fw/'host/include', '-I', fw/'stage0-node/App',
                           '-I', fw/'stage0-node/Core/Inc', '-I', fw, '-I', fw/'common',
                           '-I', fw/'host', fw/'host/sensor_harness.c', fw/'host/sim_core.c', fw/'host/i2c_sim.c', fw/'host/i2c_models.c',
                           fw/'stage0-node/App/sensor.c', fw/'stage0-node/App/i2c_bus.c', fw/'stage0-node/App/busymon.c',
                           fw/'stage0.c', fw/'common/ws_check.c')
        cls.library = lib._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.count = 0

    def sensor(self, mode=DEV_OK, sda_hold=0, latency=1):
        """A fresh driver (its own copy of the library: statics start at zero)."""
        type(self).count += 1
        path = Path(self.tmp.name)/f's{self.count}.so'
        shutil.copy(self.library, path)
        lib = ctypes.CDLL(str(path))
        lib.h_done_after.restype = ctypes.c_uint32
        lib.h_init()
        lib.h_device(mode, sda_hold, latency)
        self.addCleanup(lambda: self.assertEqual((lib.h_read_too_early(), lib.h_pin_errors(), lib.ws_check_count()), (0, 0, 0)))
        return lib

    def measure(self, lib, ms=200):
        self.assertEqual(lib.h_start(), 0)
        before = lib.h_done_calls()
        lib.h_advance(0)
        self.assertEqual(lib.h_done_calls(), before, 'done() must not run inside sensor_start')
        lib.h_advance(ms)
        self.assertEqual(lib.h_done_calls(), before + 1, 'exactly one done() per measurement')
        return lib.h_done_rc()

    def test_a_reading_after_the_measurement_time(self):
        s = self.sensor()
        self.assertEqual(self.measure(s), 0)
        self.assertEqual((s.h_done_t(), s.h_done_h()), (4250, 5650))
        self.assertTrue(11 <= s.h_done_after() <= 15, s.h_done_after())   # 1 ms write + >= 9.8 ms wait + read
        self.assertEqual((s.h_transfers(), s.h_deinits()), (2, 0))

    def test_each_failure_has_its_code_and_recovers_the_bus(self):
        for mode, rc in ((DEV_NACK_CMD, -2), (DEV_NACK_READ, -3), (DEV_BAD_CRC, -4), (DEV_HANG_CMD, TIMEOUT),
                         (DEV_HANG_READ, TIMEOUT), (DEV_BUSY, -2)):
            with self.subTest(mode=mode):
                s = self.sensor(mode)
                self.assertEqual(self.measure(s), rc)
                self.assertEqual(s.h_done_t(), 0)
                self.assertEqual(s.h_deinits(), 1)          # the recovery ran ...
                self.assertEqual(s.h_i2c_ready(), 1)        # ... and the peripheral is back
                self.assertLess(s.h_done_after(), 120)
                s.h_device(DEV_OK, 0, 1)
                self.assertEqual(self.measure(s), 0)        # the next measurement works

    def test_held_sda_is_clocked_free_or_reported_stuck(self):
        s = self.sensor(DEV_NACK_CMD, sda_hold=5)
        self.assertEqual(self.measure(s), -2)               # released after 5 clocks: the original error
        self.assertGreaterEqual(s.h_scl_edges(), 5)
        s = self.sensor(DEV_NACK_CMD, sda_hold=99)
        self.assertEqual(self.measure(s), BUS_STUCK)        # never released: 9 clocks, then -5
        self.assertEqual(s.h_scl_edges(), 9 + 1)            # nine pulses and the STOP's rising SCL

    def test_a_start_while_busy_is_refused_at_once(self):
        s = self.sensor(DEV_HANG_CMD)
        self.assertEqual(s.h_start(), 0)
        self.assertEqual(s.h_start(), -1)                   # measuring
        s.h_advance(31)                                     # guard expired: now recovering
        self.assertEqual(s.h_start(), -1)
        s.h_advance(200)
        self.assertEqual(s.h_done_calls(), 1)
        s.h_device(DEV_OK, 0, 1)
        self.assertEqual(self.measure(s), 0)

    def test_a_completion_after_the_guard_is_ignored(self):
        s = self.sensor(DEV_OK, latency=40)                 # the write completes after the 30 ms guard
        self.assertEqual(self.measure(s), TIMEOUT)          # one done(), the timeout ...
        s.h_advance(500)
        self.assertEqual(s.h_done_calls(), 1)               # ... and the late completion adds nothing


    def test_a_completion_at_the_guard_instant_counts_once(self):
        # The read ends (data, or an I2C error) in the same instant its guard expires. The guard
        # interrupt (RTC, priority 0) runs first and ends the measurement; the I2C interrupt
        # (priority 2) that follows before the main loop must not overwrite the result.
        for error in (0, 1):
            with self.subTest(error=error):
                s = self.sensor(DEV_HANG_READ)
                self.assertEqual(s.h_start(), 0)
                s.h_advance(13)                             # the write is done, the read is in flight
                self.assertEqual(s.h_complete_read_at_guard(error), 1)
                s.h_advance(200)
                self.assertEqual((s.h_done_calls(), s.h_done_rc()), (1, TIMEOUT))

if __name__ == '__main__':
    unittest.main()
