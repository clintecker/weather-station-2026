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

DEVK_TEST, DEVK_MUX, DEVK_EEPROM = 1, 8, 9
UPSTREAM = -1
MUX = 0x71
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
DM_BUS_ERROR = 6                                   # i2c_sim.h: a bus error (BERR), not a NACK
OK, ENACK_ADDR, ENACK_DATA, ESTUCK, ETIMEOUT, EBUS = 0, -2, -3, -5, -6, -7
SHT45, BMP581, LTR390 = 0, 1, 2
SHTC3 = 3
ADDR = {SHT45: 0x44, BMP581: 0x47, LTR390: 0x53, SHTC3: 0x70}
CHANNEL = {SHT45: 0, LTR390: 1, BMP581: 2}           # the static channel map (ports design, section 4.1)


@needs_cc
class I2cBus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'i2cbus', '-DWSMP_BUS_ONLY', *wsmp_sources(('i2c_bus', 'busymon')))
        cls.library = lib._name

    def bus(self, *clients, boot=True):
        """A fresh bus (its own copy of the library: statics start at zero), one test device each, on
        its client's channel (an upstream client's device upstream). With boot, the boot job (mux
        RESET, deselect, phantom check) is done and the counters below start after it."""
        lib = fresh_station(self, self.library)
        lib.h_log_ms.restype = ctypes.c_uint32
        lib.h_transfers.restype = ctypes.c_uint32
        lib.h_addr_transfers.restype = ctypes.c_uint32
        lib.h_init()
        devs = {c: lib.h_add_on(DEVK_TEST, ADDR[c], CHANNEL.get(c, UPSTREAM)) for c in clients or (SHT45,)}
        if boot:
            lib.h_advance(50)
            self.assertEqual(lib.h_bus_ready(), 1)
        self.base = lib.h_transfers()
        return lib, devs

    def transfers(self, lib):
        """Transfers to the parts (not the mux) since the boot job."""
        return lib.h_transfers() - self.base

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
        self.assertEqual((self.transfers(lib), lib.h_deinits()), (1, 0))
        self.assertEqual(lib.h_power(), 1)                  # the sensor supply is on after init

    def test_a_register_read_uses_the_repeated_start_form(self):
        lib, _ = self.bus(BMP581)
        self.assertEqual(lib.h_submit(BMP581, ADDR[BMP581], 1, 0x20, 3), 0)
        lib.h_advance(50)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, OK))
        self.assertEqual([lib.h_rx(BMP581, i) for i in range(3)], [0x20, 0x21, 0x22])

    def test_a_bad_form_is_refused(self):
        lib, _ = self.bus()
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 3, 0, 3), -1)    # three address bytes and a read
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 2, 0, 129), -1)  # more than 128 bytes

    def test_a_recovery_request_clocks_the_bus_and_reports_once(self):
        lib, devs = self.bus()
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 0), 0)   # neither write nor read: recover only
        lib.h_advance(200)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, OK))
        self.assertEqual((lib.h_deinits(), self.transfers(lib), lib.h_i2c_ready()), (1, 0, 1))
        self.assertEqual(lib.h_scl_edges(), 1)             # SDA free at once: only the STOP's rising SCL
        self.assertEqual(self.read(lib), OK)               # the bus works afterwards

    def test_each_failure_has_its_code_and_recovers_the_bus(self):
        # A transfer that can leave the bus stuck (a timeout, a HAL refusal) is followed by the recovery.
        # A clean NACK, with SDA free, is not: absent modules are probed often, and a recovery each time
        # would only churn the bus. SDA held low after a NACK still recovers (the next test). Only a NACK
        # (HAL_I2C_ERROR_AF) is a NACK code: a bus error or a HAL refusal is a bus fault (WSMP-P3), never
        # "absent". A busy bus refuses the mux too: the select (then the transfer is skipped), the
        # deselect and its one retry after the mux RESET each recover.
        for mode, reg, rc, recoveries in ((DM_NACK_ADDR, True, ENACK_ADDR, 0), (DM_NACK_ADDR, False, ENACK_DATA, 0),
                                          (DM_NACK_DATA, False, ENACK_DATA, 0), (DM_HANG, True, ETIMEOUT, 1),
                                          (DM_BUSY, True, EBUS, 3), (DM_BUS_ERROR, True, EBUS, 1),
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
        self.assertEqual(self.transfers(lib), 3)

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

    def test_boot_order(self):
        # Section 6.6: before any upstream transfer, a mux RESET pulse, mask 0x00 written and read
        # back, then the phantom check (the probe table and 0x50), then the clients.
        lib, _ = self.bus(SHTC3, boot=False)
        self.assertEqual(lib.h_submit(SHTC3, ADDR[SHTC3], 1, 0, 2), 0)    # an upstream driver, at once
        lib.h_advance(100)
        self.assertEqual(lib.h_mux_resets(), 1)
        order = [lib.h_addr_log(i) for i in range(7)]
        self.assertEqual(order, [MUX, MUX, 0x44, 0x47, 0x53, 0x50, ADDR[SHTC3]])
        self.assertEqual((lib.h_mux_writes(0), lib.h_mux_mask()), (0, 0))
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0), lib.h_phantoms(), lib.h_mux_ok()), (1, OK, 0, 1))

    def test_a_phantom_address_is_removed_for_the_boot(self):
        # PORT-15: a part that answers at a probe-table address with every channel deselected would
        # answer through every channel. Its port client is refused for the boot, without bus traffic.
        lib = fresh_station(self, self.library)
        lib.h_add_on(DEVK_TEST, ADDR[SHT45], UPSTREAM)
        lib.h_init()
        lib.h_advance(50)
        self.assertEqual(lib.h_phantoms(), 1)                # bit 0: 0x44
        before = lib.h_addr_transfers(ADDR[SHT45])
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 6), 0)
        self.assertEqual(lib.h_log_count(), 0, 'no completion may run inside i2c_bus_submit')
        lib.h_advance(50)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, ENACK_ADDR))
        self.assertEqual(lib.h_addr_transfers(ADDR[SHT45]), before)

    def test_a_port_transfer_selects_then_deselects(self):
        lib, _ = self.bus(BMP581)
        writes = lib.h_mux_write_count()
        self.assertEqual(self.read(lib, BMP581), OK)
        self.assertEqual(lib.h_mux_write_count() - writes, 2)
        self.assertEqual((lib.h_mux_writes(writes), lib.h_mux_writes(writes + 1)), (1 << CHANNEL[BMP581], 0))
        self.assertEqual(lib.h_mux_mask(), 0)                # deselected after the burst
        self.assertEqual(lib.h_mux_reads(), 2 + 1)           # each write read back (and the boot's)

    def test_a_device_on_another_channel_does_not_answer(self):
        lib, devs = self.bus(SHT45)
        lib.h_remove_device(devs[SHT45])
        lib.h_add_on(DEVK_TEST, ADDR[SHT45], 3)              # plugged into channel 3: the static map does not see it
        self.assertEqual(self.read(lib), ENACK_ADDR)

    def test_upstream_parts_are_served_with_no_channel_selected(self):
        lib, _ = self.bus(SHT45, BMP581, LTR390, SHTC3)
        for c in (SHT45, SHTC3, BMP581, SHTC3):
            if c == SHTC3:
                lib.h_advance(20)
            self.assertEqual(lib.h_submit(c, ADDR[c], 1, 0, 2), 0)
        lib.h_advance(200)
        self.assertEqual([lib.h_log_rc(i) for i in range(lib.h_log_count())], [OK] * 4)
        self.assertEqual(lib.h_upstream_with_channel(), 0)

    def test_a_mux_that_does_not_read_back_is_a_bus_fault(self):
        # The select did not take: the port client gets a bus fault (WSMP-P3), never "absent", its
        # transfer is not run, and the deselect still runs (with one RESET pulse when it fails too).
        lib, _ = self.bus(SHT45)
        before = self.transfers(lib)
        lib.h_mux_readback_xor(0x80)
        self.assertEqual(self.read(lib), EBUS)
        self.assertEqual(self.transfers(lib), before)
        self.assertEqual((lib.h_mux_resets(), lib.h_mux_ok()), (2, 0))   # the boot's and one more
        lib.h_mux_readback_xor(0)
        self.assertEqual(self.read(lib), OK)
        self.assertEqual(lib.h_mux_ok(), 1)

    def test_an_absent_mux_is_a_bus_fault_for_the_ports_only(self):
        lib, devs = self.bus(SHT45, SHTC3)
        lib.h_remove_device(lib.h_mux_device())
        self.assertEqual(self.read(lib, SHT45), EBUS)
        self.assertEqual(self.read(lib, SHTC3), OK)

    def test_held_sda_after_the_recovery_pulses_the_mux_reset(self):
        # Step 2 of section 6.6: the channel's device still holds SDA after the 9 clocks, and with it
        # the upstream bus; the mux RESET lets the upstream bus go, and the upstream part reads again.
        lib, devs = self.bus(SHT45, SHTC3)
        lib.h_device_mode(devs[SHT45], DM_NACK_ADDR, 99, 1)
        self.assertEqual(self.read(lib), ESTUCK)
        self.assertEqual(lib.h_mux_resets(), 2)
        self.assertEqual(self.read(lib, SHTC3), OK)

    def test_a_word_address_read_of_128_bytes(self):
        # The 24LC32A (section 6.9): the 2-byte word address, high byte first, then 128 bytes.
        lib, _ = self.bus()
        lib.h_add_on(DEVK_EEPROM, 0x50, CHANNEL[SHT45])
        self.assertEqual(lib.h_submit(SHT45, 0x50, 2, 0x00, 128), 0)    # address 0x0001 (h_submit's tx[1] = 1)
        lib.h_advance(100)
        self.assertEqual((lib.h_log_count(), lib.h_log_rc(0)), (1, OK))
        self.assertEqual([lib.h_rx(SHT45, i) for i in (0, 1, 126, 127)], [0x01, 0x02, 0x7F, 0x80])

    def test_the_guard_grows_with_the_transfer(self):
        # 30 ms plus 90 us a byte: a 128-byte read whose bytes take 38 ms (a slow bus and a flash
        # erase stall) completes; a 6-byte read that slow times out at 30 ms.
        for n, rc in ((128, OK), (6, ETIMEOUT)):
            with self.subTest(n=n):
                lib, devs = self.bus()
                lib.h_device_mode(devs[SHT45], DM_OK, 0, 38)
                self.assertEqual(self.read(lib, n=n), rc)


if __name__ == '__main__':
    unittest.main()
