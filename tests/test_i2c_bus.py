"""The shared I2C bus (firmware/stage0-node/App/i2c_bus.c, as built) on the host.

firmware/host/i2c_sim.c models ST's HAL I2C with many devices; firmware/host/wsmp_harness.c, built with
-DWSMP_BUS_ONLY, records every i2c_bus_done. Every transfer must end in exactly one completion with
the documented code, never wait, and leave the bus ready. The cases of the earlier SHT45 driver
(tests/test_sensor_machine.py) appear here for one client. Host-model results, not bench evidence.

Two profiles (App/i2c_bus.lit.md section 11): I2cBus builds the mux profile (WS_I2C_MUX=1, the ports
board), I2cBusHub the firmware default (WS_I2C_MUX=0, the official phase A STEMMA QT hub)."""
import ctypes
import re
import unittest
from pathlib import Path

try:
    from toolchain import fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>

DEVK_TEST, DEVK_SHT45, DEVK_INA228, DEVK_MAX17048, DEVK_MUX, DEVK_EEPROM = 1, 2, 6, 7, 8, 9
UPSTREAM = -1
MUX = 0x71
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY = range(5)
DM_BUS_ERROR = 6                                   # i2c_sim.h: a bus error (BERR), not a NACK
OK, ENACK_ADDR, ENACK_DATA, ESTUCK, ETIMEOUT, EBUS = 0, -2, -3, -5, -6, -7
SHT45, BMP581, LTR390 = 0, 1, 2
SHTC3 = 3
INA_BATT, INA_LOAD, INA_SOLAR, INA_USB, MAX17048, REC_AIR = 4, 5, 6, 7, 8, 9   # enum i2c_client
ADDR = {SHT45: 0x44, BMP581: 0x47, LTR390: 0x53, SHTC3: 0x70}
# The rail monitors (power telemetry spec section 9.2): battery, load, solar, USB-C.
RAILS = {INA_BATT: 0x40, INA_LOAD: 0x41, INA_SOLAR: 0x45, INA_USB: 0x48}
GAUGE = 0x36
INA_MANUFACTURER, INA_TI = 0x3E, (0x54, 0x49)        # MANUFACTURER_ID 'TI'
GAUGE_VERSION, GAUGE_0012 = 0x08, (0x00, 0x12)


def counters(lib):
    """(recoveries, stuck, mux resets) since boot: the bus's own saturating counters (i2c_bus.h)."""
    for f in (lib.i2c_bus_recoveries, lib.i2c_bus_stuck, lib.i2c_bus_mux_resets):
        f.restype = ctypes.c_uint16
    return lib.i2c_bus_recoveries(), lib.i2c_bus_stuck(), lib.i2c_bus_mux_resets()


class Rails:
    """Shared by both profiles: the four INA228 rail monitors, upstream, read side by side."""
    def test_four_ina228_rail_monitors_work_upstream_together(self):
        lib = fresh_station(self, self.library)
        lib.h_init()
        devs = {c: lib.h_add_device(DEVK_INA228, a) for c, a in RAILS.items()}
        lib.h_advance(50)
        for c, a in RAILS.items():
            self.assertEqual(lib.h_submit(c, a, 1, INA_MANUFACTURER, 2), 0)
        lib.h_advance(100)
        self.assertEqual([(lib.h_log_client(i), lib.h_log_rc(i)) for i in range(lib.h_log_count())],
                         [(c, OK) for c in RAILS])
        self.assertEqual({c: (lib.h_rx(c, 0), lib.h_rx(c, 1)) for c in RAILS}, {c: INA_TI for c in RAILS})
        self.assertEqual({a: lib.h_addr_transfers(a) for a in RAILS.values()}, {a: 1 for a in RAILS.values()})
        self.assertEqual(lib.h_upstream_with_channel(), 0)
        lib.h_remove_device(devs[INA_SOLAR])                  # one rail absent: only its client sees it
        for c, a in RAILS.items():
            self.assertEqual(lib.h_submit(c, a, 1, INA_MANUFACTURER, 2), 0)
        lib.h_advance(100)
        self.assertEqual([lib.h_log_rc(i) for i in range(4, 8)], [OK, OK, ENACK_ADDR, OK])
        self.assertEqual(counters(lib)[:2], (0, 0))           # an absent part costs no recovery

    def test_pa9_cycles_drop_only_the_switched_sensors(self):
        # Build-progression record, step 1 change C and exit criterion 9: PA9 low 10 times. The SHT45 on
        # the switched branch drops off (a clean NACK) and is found again; the battery INA228 (0x40) and
        # the MAX17048 (0x36), on the unswitched QT branch (PORT-9, M6), never NACK; the bus recovers.
        lib = fresh_station(self, self.library)
        lib.h_init()
        sht45 = lib.h_add_device(DEVK_SHT45, ADDR[SHT45])
        lib.h_add_device(DEVK_INA228, RAILS[INA_BATT])
        lib.h_add_device(DEVK_MAX17048, GAUGE)
        lib.i2c_sim_switched(sht45, 1)
        lib.h_advance(50)                                      # the mux profile's boot job

        def round_of_reads():
            before = lib.h_log_count()
            for c, a, reg, n in ((SHT45, ADDR[SHT45], 0xFD, 0), (INA_BATT, RAILS[INA_BATT], INA_MANUFACTURER, 2),
                                 (MAX17048, GAUGE, GAUGE_VERSION, 2)):
                self.assertEqual(lib.h_submit(c, a, 1, reg, n), 0)
            lib.h_advance(100)
            self.assertEqual(lib.h_log_count(), before + 3, 'exactly one completion per transfer')
            return {lib.h_log_client(i): lib.h_log_rc(i) for i in range(before, before + 3)}

        for cycle in range(10):
            lib.i2c_bus_power(0)
            self.assertEqual(lib.h_power(), 0)
            self.assertEqual(round_of_reads(), {SHT45: ENACK_ADDR, INA_BATT: OK, MAX17048: OK}, cycle)
            self.assertEqual((lib.h_rx(INA_BATT, 0), lib.h_rx(INA_BATT, 1)), INA_TI)
            lib.i2c_bus_power(1)
            self.assertEqual(round_of_reads(), {SHT45: OK, INA_BATT: OK, MAX17048: OK}, cycle)
            self.assertEqual((lib.h_rx(MAX17048, 0), lib.h_rx(MAX17048, 1)), GAUGE_0012)
        self.assertEqual(counters(lib)[:2], (0, 0))           # a switched-off sensor is a clean NACK
        self.assertEqual(lib.h_upstream_with_channel(), 0)
        self.assertEqual(lib.h_power(), 1)

    def test_outcomes_name_the_clients_that_answered_and_failed(self):
        # i2c_bus_outcomes (TEST-SENSOR-POWER's evidence, step 1 exit 9): a bit for each client whose own
        # transfer answered, and one for each whose job failed, since the previous call, which clears
        # them. A recover-only request is neither; the masks never touch the bus.
        lib = fresh_station(self, self.library)
        lib.h_init()
        sht45 = lib.h_add_device(DEVK_SHT45, ADDR[SHT45])
        lib.h_add_device(DEVK_INA228, RAILS[INA_BATT])
        lib.i2c_sim_switched(sht45, 1)
        lib.h_advance(50)
        lib.h_transfers.restype = ctypes.c_uint32
        acked, failed = ctypes.c_uint16(), ctypes.c_uint16()

        def outcomes():
            lib.i2c_bus_outcomes(ctypes.byref(acked), ctypes.byref(failed))
            return acked.value, failed.value

        outcomes()                                             # forget the boot job's (none upstream)
        self.assertEqual(outcomes(), (0, 0))
        for c, a, reg, n in ((SHT45, ADDR[SHT45], 0xFD, 0), (INA_BATT, RAILS[INA_BATT], INA_MANUFACTURER, 2),
                             (INA_LOAD, RAILS[INA_LOAD], INA_MANUFACTURER, 2)):   # the load INA228 is not fitted
            self.assertEqual(lib.h_submit(c, a, 1, reg, n), 0)
        lib.h_advance(100)
        before = lib.h_transfers()
        self.assertEqual(outcomes(), (1 << SHT45 | 1 << INA_BATT, 1 << INA_LOAD))
        self.assertEqual((outcomes(), lib.h_transfers()), ((0, 0), before))   # cleared; no bus traffic
        lib.i2c_bus_power(0)                                   # the switched SHT45 is off: a NACK
        self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 1, 0xFD, 0), 0)
        self.assertEqual(lib.h_submit(INA_BATT, 0, 0, 0, 0), 0)   # recover only: neither bit
        lib.h_advance(100)
        self.assertEqual(outcomes(), (0, 1 << SHT45))
        lib.i2c_bus_power(1)
CHANNEL = {SHT45: 0, LTR390: 1, BMP581: 2}           # the static channel map (ports design, section 4.1)


@needs_cc
class I2cBus(Rails, unittest.TestCase):
    """The mux profile (WS_I2C_MUX=1): the ports board with the TCA9548A at 0x71."""
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'i2cbus', '-DWSMP_BUS_ONLY', *wsmp_sources(('i2c_bus', 'busymon'), mux=1))
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

    def test_a_deselect_that_never_reads_back_fails_the_port_client(self):
        # The select and the transfer took, but the deselect read-back fails, then fails again after
        # the mux RESET: a channel may still be selected, so the port client gets a bus fault.
        lib, _ = self.bus(SHT45)
        lib.h_mux_readback_xor_idle(0x80)
        self.assertEqual(self.read(lib), EBUS)
        self.assertEqual((lib.h_mux_resets(), lib.h_mux_ok()), (2, 0))

    def test_an_upstream_job_deselects_first_while_the_mux_is_not_ok(self):
        # After a deselect that never read back, an upstream job deselects and checks the read-back
        # first, and runs its transfer only after a good one (which makes the mux ok again).
        lib, _ = self.bus(SHT45, SHTC3)
        lib.h_mux_readback_xor_idle(0x80)
        self.assertEqual(self.read(lib, SHT45), EBUS)
        lib.h_mux_readback_xor_idle(0)
        writes, reads = lib.h_mux_write_count(), lib.h_mux_reads()
        self.assertEqual(self.read(lib, SHTC3), OK)
        self.assertEqual((lib.h_mux_write_count() - writes, lib.h_mux_writes(writes)), (1, 0))
        self.assertEqual((lib.h_mux_reads() - reads, lib.h_mux_ok()), (1, 1))
        writes = lib.h_mux_write_count()
        self.assertEqual(self.read(lib, SHTC3), OK)               # the mux is ok: a bare transfer again
        self.assertEqual(lib.h_mux_write_count(), writes)

    def test_an_upstream_job_is_refused_while_the_deselect_does_not_read_back(self):
        lib, _ = self.bus(SHT45, SHTC3)
        lib.h_mux_readback_xor_idle(0x80)
        self.assertEqual(self.read(lib, SHT45), EBUS)
        before = lib.h_addr_transfers(ADDR[SHTC3])
        self.assertEqual(self.read(lib, SHTC3), EBUS)
        self.assertEqual(lib.h_addr_transfers(ADDR[SHTC3]), before)   # never touched
        self.assertEqual(lib.h_mux_ok(), 0)

    def test_an_absent_mux_is_a_bus_fault_for_every_client(self):
        # The mux profile only: an absent mux never reads back a deselect, so no client can know that
        # no channel is selected. (The hub profile has no mux to miss: I2cBusHub.)
        lib, devs = self.bus(SHT45, SHTC3)
        lib.h_remove_device(lib.h_mux_device())
        self.assertEqual(self.read(lib, SHT45), EBUS)
        self.assertEqual(self.read(lib, SHTC3), EBUS)

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

    def test_one_hang_is_one_recovery(self):
        lib, devs = self.bus()
        self.assertEqual(counters(lib), (0, 0, 1))           # the boot job's RESET pulse
        lib.h_device_mode(devs[SHT45], DM_HANG, 0, 1)
        self.assertEqual(self.read(lib), ETIMEOUT)
        self.assertEqual((counters(lib), lib.h_deinits()), ((1, 0, 1), 1))
        lib.h_device_mode(devs[SHT45], DM_NACK_ADDR, 0, 1)
        self.assertEqual(self.read(lib), ENACK_ADDR)         # a clean NACK: no recovery, no count
        self.assertEqual(counters(lib), (1, 0, 1))

    def test_held_sda_counts_as_stuck(self):
        # A held SDA that the 9 clocks free is a recovery, not a stuck one; one that stays low is
        # both, and in the mux profile it costs a RESET pulse (step 2).
        for hold, rc, want in ((5, ENACK_ADDR, (1, 0, 1)), (99, ESTUCK, (1, 1, 2))):
            with self.subTest(hold=hold):
                lib, devs = self.bus()
                lib.h_device_mode(devs[SHT45], DM_NACK_ADDR, hold, 1)
                self.assertEqual(self.read(lib), rc)
                self.assertEqual(counters(lib), want)
                self.assertEqual(lib.h_mux_resets(), want[2])

    def test_mux_resets_are_counted(self):
        # The deselect that never reads back pulses RESET once more (mux_done); the counter follows
        # the RESET line exactly.
        lib, _ = self.bus(SHT45)
        lib.h_mux_readback_xor_idle(0x80)
        self.assertEqual(self.read(lib), EBUS)
        self.assertEqual((counters(lib)[2], lib.h_mux_resets()), (2, 2))

    def test_an_ina228_is_never_behind_a_channel(self):
        # The host model's channel rule keys on the kind: an INA228 at a probe-table address (0x46 is
        # the BMP581's second address, channel 2 for a port part) stays upstream.
        lib, _ = self.bus()
        lib.h_add_device(DEVK_INA228, 0x46)
        self.assertEqual(lib.h_submit(INA_LOAD, 0x46, 1, INA_MANUFACTURER, 2), 0)
        lib.h_advance(50)
        self.assertEqual((lib.h_log_rc(0), lib.h_rx(INA_LOAD, 0), lib.h_rx(INA_LOAD, 1)), (OK, *INA_TI))
        self.assertEqual((lib.h_mux_write_count(), lib.h_upstream_with_channel()), (1, 0))   # the boot's deselect only

    def test_the_guard_grows_with_the_transfer(self):
        # 30 ms plus 90 us a byte: a 128-byte read whose bytes take 38 ms (a slow bus and a flash
        # erase stall) completes; a 6-byte read that slow times out at 30 ms.
        for n, rc in ((128, OK), (6, ETIMEOUT)):
            with self.subTest(n=n):
                lib, devs = self.bus()
                lib.h_device_mode(devs[SHT45], DM_OK, 0, 38)
                self.assertEqual(self.read(lib, n=n), rc)


@needs_cc
class I2cBusHub(Rails, unittest.TestCase):
    """The hub profile (WS_I2C_MUX=0, the firmware default): the official phase A STEMMA QT hub."""
    @classmethod
    def setUpClass(cls):
        lib = host_library(cls, 'i2cbus-hub', '-DWSMP_BUS_ONLY', *wsmp_sources(('i2c_bus', 'busymon'), mux=0))
        cls.library = lib._name

    def hub(self, *devices):
        """A fresh hub bus with these (kind, addr7) devices, added by the host model's own rule."""
        lib = fresh_station(self, self.library)
        lib.h_transfers.restype = ctypes.c_uint32
        lib.h_addr_transfers.restype = ctypes.c_uint32
        devs = [lib.h_add_device(k, a) for k, a in devices]
        lib.h_init()
        return lib, devs

    def complete(self, lib, client, addr7, txlen, reg, rxlen, ms=50):
        before = lib.h_log_count()
        self.assertEqual(lib.h_submit(client, addr7, txlen, reg, rxlen), 0)
        lib.h_advance(ms)
        self.assertEqual(lib.h_log_count(), before + 1, 'exactly one completion per transfer')
        self.assertEqual(lib.h_log_client(before), client)
        return lib.h_log_rc(before)

    def assert_no_mux(self, lib):
        self.assertEqual((lib.h_mux_device(), lib.h_mux_write_count(), lib.h_mux_reads(), lib.h_mux_resets()),
                         (-1, 0, 0, 0))
        self.assertEqual((lib.h_addr_transfers(MUX), lib.h_phantoms(), counters(lib)[2]), (0, 0, 0))

    def test_a_hub_boot_reads_the_power_parts_and_the_sht45(self):
        # Spec section 9.1: the official wiring, INA228 0x40, MAX17048 0x36 and SHT45 0x44 on the hub,
        # read with no mux, no boot job and no phantom refusal (0x44 answers upstream).
        lib, _ = self.hub((DEVK_INA228, RAILS[INA_BATT]), (DEVK_MAX17048, GAUGE), (DEVK_SHT45, ADDR[SHT45]))
        self.assertEqual((lib.h_bus_ready(), lib.h_mux_ok()), (1, 1))     # at once: nothing to boot
        self.assertEqual(lib.h_transfers(), 0)
        self.assertEqual(self.complete(lib, INA_BATT, RAILS[INA_BATT], 1, INA_MANUFACTURER, 2), OK)
        self.assertEqual((lib.h_rx(INA_BATT, 0), lib.h_rx(INA_BATT, 1)), INA_TI)
        self.assertEqual(self.complete(lib, MAX17048, GAUGE, 1, GAUGE_VERSION, 2), OK)
        self.assertEqual((lib.h_rx(MAX17048, 0), lib.h_rx(MAX17048, 1)), GAUGE_0012)
        self.assertEqual(self.complete(lib, SHT45, ADDR[SHT45], 1, 0xFD, 0, ms=20), OK)   # measure, high precision
        self.assertEqual(self.complete(lib, SHT45, ADDR[SHT45], 0, 0, 6), OK)
        self.assertEqual((lib.model_sht45_commands(), lib.model_sht45_read_too_early()), (1, 0))
        self.assertEqual([lib.h_addr_log(i) for i in range(5)], [0x40, GAUGE, 0x44, 0x44, -1])
        self.assert_no_mux(lib)
        self.assertEqual(counters(lib), (0, 0, 0))

    def test_a_record_client_is_absent_without_bus_traffic(self):
        # No record EEPROM on the hub: a record client gets ENACK_ADDR without touching the bus, even
        # with a part at 0x50, so port_id admits its module with NO_RECORD.
        lib, _ = self.hub((DEVK_EEPROM, 0x50))
        self.assertEqual(self.complete(lib, REC_AIR, 0x50, 2, 0x00, 128), ENACK_ADDR)
        self.assertEqual((lib.h_transfers(), lib.h_addr_transfers(0x50)), (0, 0))
        self.assertEqual(self.complete(lib, REC_AIR, 0x50, 0, 0, 0, ms=200), OK)   # recover only: served
        self.assertEqual(counters(lib), (1, 0, 0))

    def test_a_port_address_is_upstream_and_not_a_phantom(self):
        # Every device is upstream, whatever its address, and no address is refused as a phantom.
        lib, _ = self.hub(*((DEVK_TEST, a) for a in ADDR.values()))
        for c, a in ADDR.items():
            self.assertEqual(self.complete(lib, c, a, 1, 0x20, 2), OK)
            self.assertEqual((lib.h_rx(c, 0), lib.h_rx(c, 1)), (0x20, 0x21))
        self.assert_no_mux(lib)

    def test_held_sda_counts_as_stuck_without_a_mux_reset(self):
        # No mux to let the bus go: SDA held for 15 clocks outlasts the first recovery's 9 (stuck),
        # and the next recovery frees it (counted, not stuck).
        lib, devs = self.hub((DEVK_TEST, ADDR[SHT45]))
        lib.h_device_mode(devs[0], DM_NACK_ADDR, 15, 1)
        self.assertEqual(self.complete(lib, SHT45, ADDR[SHT45], 1, 0, 6, ms=200), ESTUCK)
        self.assertEqual(counters(lib), (1, 1, 0))
        lib.h_device_mode(devs[0], DM_HANG, 0, 1)
        self.assertEqual(self.complete(lib, SHT45, ADDR[SHT45], 1, 0, 6, ms=200), ETIMEOUT)
        self.assertEqual(counters(lib), (2, 1, 0))
        self.assert_no_mux(lib)

    def test_the_counters_saturate(self):
        # 0xFFFF and no further (the health report's u16, spec section 6.2): one more recovery than
        # the counter holds, each a recover-only request with SDA held for good (stuck as well).
        lib, devs = self.hub((DEVK_TEST, ADDR[SHT45]))
        lib.h_device_mode(devs[0], DM_NACK_ADDR, 1 << 30, 1)
        self.assertEqual(self.complete(lib, SHT45, ADDR[SHT45], 1, 0, 6, ms=200), ESTUCK)
        for _ in range(0xFFFF):
            self.assertEqual(lib.h_submit(SHT45, ADDR[SHT45], 0, 0, 0), 0)
            lib.h_advance(100)
        self.assertEqual(lib.h_log_count(), 64)              # the harness log is full; the bus is not
        self.assertEqual(counters(lib), (0xFFFF, 0xFFFF, 0))
        self.assertEqual(lib.h_i2c_ready(), 1)


if __name__ == '__main__':
    unittest.main()


class BusTiming(unittest.TestCase):
    """The I2C2 timing register (RM0453 I2C timings) at PCLK1 = 48 MHz: 100 kHz standard mode with at
    least 100 ns of data hold, which the INA228 needs on the address MSB when SDA straps A0 or A1
    (SBOS904; the USB-C rail at 0x48, power telemetry design section 9.2). The node, i2cscan and
    benchlink share the value."""
    ROOT = Path(__file__).resolve().parent.parent
    PCLK1_HZ = 48_000_000

    def timing(self, path):
        m = re.search(r'#define I2C_TIMING 0x([0-9A-Fa-f]{8})U', (self.ROOT / path).read_text())
        self.assertIsNotNone(m, path)
        return int(m.group(1), 16)

    def test_sdadel_gives_the_ina228_sda_strap_its_hold_time(self):
        t = self.timing('firmware/stage0-node/App/i2c_bus.c')
        presc, scldel, sdadel = t >> 28, (t >> 20) & 0xF, (t >> 16) & 0xF
        scll, sclh = t & 0xFF, (t >> 8) & 0xFF
        t_clk = 1e9 / self.PCLK1_HZ                      # ns
        t_presc = (presc + 1) * t_clk
        hold = sdadel * t_presc + t_clk                  # tSDADEL, RM0453
        self.assertGreaterEqual(hold, 100.0)
        self.assertLess(hold, 3450.0)                    # standard-mode tVD;DAT
        self.assertGreaterEqual((scldel + 1) * t_presc, 250.0)   # tSU;DAT
        self.assertGreaterEqual((scll + 1) * t_presc, 4700.0)   # standard-mode tLOW
        self.assertEqual(sclh, 0x3E)                     # ST's example; tHIGH also holds the sync delays
        self.assertEqual(t, 0x20323E5D)

    def test_the_bench_tools_use_the_node_timing(self):
        node = self.timing('firmware/stage0-node/App/i2c_bus.c')
        for path in ('firmware/i2cscan/App/i2cscan.c', 'firmware/benchlink/App/benchlink.c'):
            self.assertEqual(self.timing(path), node, path)
