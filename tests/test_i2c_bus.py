"""The shared I2C bus (firmware/stage0-node/App/i2c_bus.c, as built) on the host.

firmware/host/i2c_sim.c models ST's HAL I2C with many devices; firmware/host/wsmp_harness.c, built with
-DWSMP_BUS_ONLY, records every i2c_bus_done. Every transfer must end in exactly one completion with
the documented code, never wait, and leave the bus ready. The cases of the earlier SHT45 driver
(tests/test_sensor_machine.py) appear here for one client. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>

DEVK_TEST = 1
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
DM_BUS_ERROR = 6                                   # i2c_sim.h: a bus error (BERR), not a NACK
OK, ENACK_ADDR, ENACK_DATA, ESTUCK, ETIMEOUT, EBUS = 0, -2, -3, -5, -6, -7
SHT45, BMP581, LTR390 = 0, 1, 2
ADDR = {SHT45: 0x44, BMP581: 0x47, LTR390: 0x53}


@needs_cc
class I2cBus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'i2cbus', '-DWSMP_BUS_ONLY', *wsmp_sources(('i2c_bus', 'busymon')))
        cls.library = lib._name

    def bus(self, *clients):
        """A fresh bus (its own copy of the library: statics start at zero), one test device each."""
        lib = fresh_station(self, self.library)
        lib.h_log_ms.restype = ctypes.c_uint32
        lib.h_init()
        devs = {c: lib.h_add_device(DEVK_TEST, ADDR[c]) for c in clients or (SHT45,)}
        return lib, devs

    def read(self, lib, client=SHT45, ms=200, n=6, reg=True):
        """One transfer: a register read (address byte, then n bytes), or a plain n-byte read. A failed
        plain read is ENACK_DATA: the device took its command and then did not deliver (i2c_bus.h)."""
        before = lib.h_log_count()
        self.assertEqual(lib.h_submit(client, ADDR[client], 1 if reg else 0, 0, n), 0)
        lib.h_advance(0)
        self.assertEqual(lib.h_log_count(), before, 'no completion may run inside i2c_bus_submit')
        lib.h_advance(ms)
        self.assertEqual(lib.h_log_count(), before + 1, 'exactly one completion per transfer')
        return lib.h_log_rc(before)

    def test_a_read_returns_the_device_bytes(self):
        lib, _ = self.bus()
        self.assertEqual(self.read(lib, reg=False), OK)
        self.assertEqual([lib.h_rx(SHT45, i) for i in range(3)], [0xA0, 0xA1, 0xA2])
        self.assertEqual((lib.h_transfers(), lib.h_deinits()), (1, 0))
        self.assertEqual(lib.h_power(), 1)                  # the sensor supply is on after init

    def test_a_register_read_uses_the_repeated_start_form(self):
        lib, _ = self.bus(BMP581)
        self.assertEqual(lib.h_submit(BMP581, ADDR[BMP581], 1, 0x20, 3), 0)
        lib.h_advance(50)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, OK))
        self.assertEqual([lib.h_rx(BMP581, i) for i in range(3)], [0x20, 0x21, 0x22])

    def test_a_bad_form_is_refused(self):
        lib, _ = self.bus()
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 2, 0, 3), -1)    # two address bytes and a read

    def test_a_recovery_request_clocks_the_bus_and_reports_once(self):
        lib, devs = self.bus()
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 0), 0)   # neither write nor read: recover only
        lib.h_advance(200)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, OK))
        self.assertEqual((lib.h_deinits(), lib.h_transfers(), lib.h_i2c_ready()), (1, 0, 1))
        self.assertEqual(lib.h_scl_edges(), 1)             # SDA free at once: only the STOP's rising SCL
        self.assertEqual(self.read(lib), OK)               # the bus works afterwards

    def test_each_failure_has_its_code_and_recovers_the_bus(self):
        # A transfer that can leave the bus stuck (a timeout, a HAL refusal) is followed by the recovery.
        # A clean NACK, with SDA free, is not: absent modules are probed often, and a recovery each time
        # would only churn the bus. SDA held low after a NACK still recovers (the next test). Only a NACK
        # (HAL_I2C_ERROR_AF) is a NACK code: a bus error or a HAL refusal is a bus fault (WSMP-P3), never
        # "absent".
        for mode, reg, rc, recoveries in ((DM_NACK_ADDR, True, ENACK_ADDR, 0), (DM_NACK_ADDR, False, ENACK_DATA, 0),
                                          (DM_NACK_DATA, False, ENACK_DATA, 0), (DM_HANG, True, ETIMEOUT, 1),
                                          (DM_BUSY, True, EBUS, 1), (DM_BUS_ERROR, True, EBUS, 1),
                                          (DM_BUS_ERROR, False, EBUS, 1)):
            with self.subTest(mode=mode, reg=reg):
                lib, devs = self.bus()
                lib.h_device_mode(devs[SHT45], mode, 0, 1)
                self.assertEqual(self.read(lib, reg=reg), rc)
                self.assertEqual(lib.h_deinits(), recoveries)   # the recovery ran when it had to ...
                self.assertEqual(lib.h_i2c_ready(), 1)      # ... and the peripheral is back
                self.assertLess(lib.h_log_ms(0), 120)
                lib.h_device_mode(devs[SHT45], DM_OK, 0, 1)
                self.assertEqual(self.read(lib), OK)        # the next transfer works

    def test_an_absent_device_is_an_address_nack(self):
        lib, devs = self.bus()
        lib.h_remove_device(devs[SHT45])
        self.assertEqual(self.read(lib), ENACK_ADDR)

    def test_an_absent_device_costs_no_recovery(self):
        lib, devs = self.bus()
        lib.h_remove_device(devs[SHT45])
        for _ in range(5):
            self.assertEqual(self.read(lib), ENACK_ADDR)
        self.assertEqual((lib.h_deinits(), lib.h_scl_edges()), (0, 0))

    def test_held_sda_is_clocked_free_or_reported_stuck(self):
        lib, devs = self.bus()
        lib.h_device_mode(devs[SHT45], DM_NACK_ADDR, 5, 1)
        self.assertEqual(self.read(lib), ENACK_ADDR)        # released after 5 clocks: the original error
        self.assertGreaterEqual(lib.h_scl_edges(), 5)
        lib, devs = self.bus()
        lib.h_device_mode(devs[SHT45], DM_NACK_ADDR, 99, 1)
        self.assertEqual(self.read(lib), ESTUCK)            # never released: 9 clocks, then -5
        self.assertEqual(lib.h_scl_edges(), 9 + 1)          # nine pulses and the STOP's rising SCL

    def test_guard_timeout_reports_etimeout(self):
        lib, devs = self.bus()
        lib.h_device_mode(devs[SHT45], DM_HANG, 0, 1)
        self.assertEqual(self.read(lib), ETIMEOUT)
        self.assertGreaterEqual(lib.h_log_ms(0), 29)        # the 30 ms guard, in ST's whole ticks

    def test_a_completion_after_the_guard_is_ignored(self):
        lib, devs = self.bus()
        lib.h_device_mode(devs[SHT45], DM_OK, 0, 40)        # the read completes after the 30 ms guard
        self.assertEqual(self.read(lib), ETIMEOUT)          # one completion, the timeout ...
        lib.h_advance(500)
        self.assertEqual(lib.h_log_count(), 1)              # ... and the late completion adds nothing

    def test_a_completion_at_the_guard_instant_counts_once(self):
        for error in (0, 1):
            with self.subTest(error=error):
                lib, devs = self.bus()
                lib.h_device_mode(devs[SHT45], DM_HANG, 0, 1)
                self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 6), 0)
                lib.h_advance(5)
                self.assertEqual(lib.h_complete_at_guard(error), 1)
                lib.h_advance(200)
                self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, ETIMEOUT))

    def test_clients_are_served_in_order_one_at_a_time(self):
        lib, _ = self.bus(SHT45, BMP581, LTR390)
        for c in (LTR390, SHT45, BMP581):
            self.assertEqual(lib.h_submit(c, ADDR[c], 0, 0, 2), 0)
        lib.h_advance(100)
        self.assertEqual([lib.h_log_client(i) for i in range(3)], [LTR390, SHT45, BMP581])
        self.assertEqual([lib.h_log_rc(i) for i in range(3)], [OK, OK, OK])
        times = [lib.h_log_ms(i) for i in range(3)]
        self.assertEqual(times, sorted(times))
        self.assertEqual(lib.h_transfers(), 3)

    def test_a_second_submit_from_a_busy_client_is_refused(self):
        lib, _ = self.bus()
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 2), 0)
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 2), -1)
        lib.h_advance(100)
        self.assertEqual(lib.h_log_count(), 1)
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 2), 0)   # free again after its completion

    def test_unplug_mid_transfer_recovers_and_spares_other_clients(self):
        # Review Focus 1: the device of client 1 hangs mid-read and holds SDA low until the recovery
        # clocks it free (unplugged). Client 1 gets the timeout; clients 0 and 2 complete normally.
        lib, devs = self.bus(SHT45, BMP581, LTR390)
        lib.h_device_mode(devs[BMP581], DM_HANG, 5, 1)
        for c in (SHT45, BMP581, LTR390):
            self.assertEqual(lib.h_submit(c, ADDR[c], 0, 0, 2), 0)
        lib.h_advance(300)
        got = {lib.h_log_client(i): lib.h_log_rc(i) for i in range(lib.h_log_count())}
        self.assertEqual(got, {SHT45: OK, BMP581: ETIMEOUT, LTR390: OK})
        self.assertEqual([lib.h_rx(LTR390, i) for i in range(2)], [0xA0, 0xA1])
        self.assertEqual(lib.h_i2c_ready(), 1)


if __name__ == '__main__':
    unittest.main()
