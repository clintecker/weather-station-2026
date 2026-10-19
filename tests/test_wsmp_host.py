"""The WSMP station host (firmware/stage0-node/App/wsmp_host.c) on the host.

It runs over the real local modules and the host bus model (firmware/host/wsmp_harness.c with
-DWSMP_HOST). The rules are docs/module-protocol.md section 7: two good probes before admission,
three missed latches before removal, a bus fault keeps the layout, a module joins at the next latch,
the flap limit, the radio budget and quarantine. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228 = 2, 3, 4, 5, 6
DM_OK, DM_NACK_ADDR, DM_NACK_DATA = 0, 1, 2
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN = range(1, 8)
ABSENT, PROBING, IDENTIFYING, ADMITTED, ACTIVE, SUSPECT, QUARANTINED, REFUSED = range(8)
MINUTE, HOUR = 60_000, 3_600_000
ADDR = {DEVK_SHT45: 0x44, DEVK_SHTC3: 0x70, DEVK_BMP581: 0x47, DEVK_LTR390: 0x53, DEVK_INA228: 0x40}


def host_sources():
    return [*wsmp_sources(), ROOT/'firmware/stage0-node/App/wsmp_host.c']


@needs_cc
class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.libs = {budget: host_library(cls, f'host{budget}', '-DWSMP_HOST', f'-DWSMP_HOST_BUDGET={budget}',
                                         *host_sources())._name
                    for budget in (58, 8)}

    def station(self, kinds, budget=58):
        lib = fresh_station(self, self.libs[budget])
        devs = {k: lib.h_add_device(k, ADDR[k]) for k in kinds}
        lib.h_init(7)
        lib.h_vane_mv(3_300)                                   # no vane on the bench unless a test fits one
        lib.h_host_init()
        return lib, devs

    def minutes(self, lib, n, latch=True):
        for _ in range(n):
            lib.h_host_run(MINUTE)
            if latch:
                lib.h_host_latch(1_792_000_000)

    def test_two_probes_then_admitted_at_next_latch(self):
        lib, _ = self.station([DEVK_SHT45])
        lib.h_host_run(750)                                     # command at 0, read at 250, seen at 500: one good probe
        self.assertEqual(lib.h_host_state(P_AIR_TH), PROBING)
        lib.h_host_run(15_000)                                  # the second
        self.assertEqual(lib.h_host_state(P_AIR_TH), ADMITTED)
        self.assertEqual(lib.h_host_has_snapshot(P_AIR_TH), 0)  # not in a reading before the next latch
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(lib.h_host_has_snapshot(P_AIR_TH), 1)

    def test_absent_ports_stay_absent(self):
        lib, _ = self.station([DEVK_SHT45])
        self.minutes(lib, 2)
        self.assertEqual([lib.h_host_state(p) for p in (P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN)], [ABSENT] * 6)

    def test_three_missed_latches_then_absent(self):
        lib, devs = self.station([DEVK_SHT45])
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        lib.h_remove_device(devs[DEVK_SHT45])
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), SUSPECT)   # two misses: still in the layout
        self.assertEqual(lib.h_host_has_snapshot(P_AIR_TH), 1)
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)    # the third: removed
        self.assertEqual(lib.h_host_has_snapshot(P_AIR_TH), 0)

    def test_a_good_read_ends_suspect(self):
        lib, devs = self.station([DEVK_SHT45])
        self.minutes(lib, 1)
        lib.h_device_mode(devs[DEVK_SHT45], DM_NACK_ADDR, 0, 1)
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), SUSPECT)
        lib.h_device_mode(devs[DEVK_SHT45], DM_OK, 0, 1)
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)

    def test_bus_fault_keeps_layout(self):
        lib, devs = self.station([DEVK_SHT45])
        self.minutes(lib, 1)
        changes = lib.h_host_changes(P_AIR_TH)
        lib.h_device_mode(devs[DEVK_SHT45], DM_NACK_DATA, 0, 1)   # a bus fault, not an absence (WSMP-P3)
        self.minutes(lib, 4)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes)
        self.assertEqual(lib.h_host_slot_quality(P_AIR_TH, 0), 3)   # missing

    def test_flap_limit_quarantines_for_an_hour(self):
        lib, devs = self.station([DEVK_SHT45])
        dev = devs[DEVK_SHT45]
        for _ in range(3):                                          # join, leave: 2 changes a cycle
            self.minutes(lib, 1)
            lib.h_remove_device(dev)
            self.minutes(lib, 3)
            lib.h_restore_device(dev)
        self.assertEqual(lib.h_host_state(P_AIR_TH), QUARANTINED)  # the 5th change within the hour
        self.minutes(lib, 30)
        self.assertEqual(lib.h_host_state(P_AIR_TH), QUARANTINED)
        self.minutes(lib, 31)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)       # after the hour it is probed and admitted again

    def test_admission_refuses_over_budget(self):
        # Budget 8 bytes: air TH (4 + 1 quality byte) and pressure (2, quality fits) take 7; UVA (3) does not fit.
        lib, _ = self.station([DEVK_SHT45, DEVK_BMP581, DEVK_LTR390], budget=8)
        self.minutes(lib, 1)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_PRESSURE, P_UVA)], [ACTIVE, ACTIVE, REFUSED])
        self.assertIn(b'uva=refused', self.line(lib))

    def test_the_health_class_does_not_count_in_the_budget(self):
        lib, _ = self.station([DEVK_SHT45, DEVK_BMP581, DEVK_INA228], budget=8)
        self.minutes(lib, 1)
        # The battery module (16 bytes) is admitted first: it probes every second. It goes in the health
        # report, so the minute modules still fit the 8 bytes beside it.
        self.assertEqual([lib.h_host_state(p) for p in (P_POWER, P_AIR_TH, P_PRESSURE)], [ACTIVE, ACTIVE, ACTIVE])

    def test_bad_descriptor_quarantines(self):
        lib, _ = self.station([])
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(P_AIR_TH, idb, desc)
        self.assertEqual(lib.wsmp_host_admit(P_AIR_TH, idb, desc), ADMITTED)
        bad = bytearray(desc); bad[2] = 2                           # temperature in % : not its canonical unit
        self.assertEqual(lib.wsmp_host_admit(P_AIR_TH, idb, (ctypes.c_uint8 * 48)(*bad)), QUARANTINED)
        bad = bytearray(idb); bad[2] = 2                            # WSMP major version 2
        self.assertEqual(lib.wsmp_host_admit(P_AIR_TH, (ctypes.c_uint8 * 32)(*bad), desc), QUARANTINED)

    def test_a_descriptor_digest_that_does_not_match_quarantines(self):
        # WSMP-I1: the identity's digest is the CRC-32C of the descriptor block; a pair that does not
        # match (a corrupt read, blocks from two modules) is not admitted.
        lib, _ = self.station([])
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(P_AIR_TH, idb, desc)
        bad = bytearray(idb); bad[29] ^= 1                          # the digest's last byte (offset 26-29)
        self.assertEqual(lib.wsmp_host_admit(P_AIR_TH, (ctypes.c_uint8 * 32)(*bad), desc), QUARANTINED)

    def test_admit_is_a_check_that_changes_no_port(self):
        # Calling the check on a port in the layout must not change that port's share of the budget.
        lib, _ = self.station([DEVK_SHT45, DEVK_BMP581], budget=8)
        self.minutes(lib, 1)
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(P_POWER, idb, desc)                         # the health-class battery module's blocks
        self.assertEqual(lib.wsmp_host_admit(P_AIR_TH, idb, desc), ADMITTED)
        lib.h_add_device(DEVK_LTR390, ADDR[DEVK_LTR390])
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_UVA), REFUSED)         # air TH still takes its 5 bytes

    def line(self, lib):
        buf = ctypes.create_string_buffer(200)
        n = lib.h_host_line(buf, 200)
        self.assertEqual(n, len(buf.value))
        return buf.value

    def test_modules_line_lists_every_port(self):
        lib, _ = self.station([DEVK_SHT45])
        self.minutes(lib, 1)
        self.assertEqual(self.line(lib), b'#modules air_th=active pressure=absent uva=absent encl_th=absent '
                                         b'power=absent wind=absent rain=absent')


if __name__ == '__main__':
    unittest.main()
