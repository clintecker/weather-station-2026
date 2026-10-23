"""The WSMP station host (firmware/stage0-node/App/wsmp_host.c) on the host.

It runs over the real local modules and the host bus model (firmware/host/wsmp_harness.c with
-DWSMP_HOST). The rules are docs/module-protocol.md section 7: two good probes before admission,
three missed latches before removal, a bus fault keeps the layout, a module joins at the next latch,
the flap limit, the radio budget and quarantine. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
    import wsmp_record_ref as ref
except ImportError:
    from tests.toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>
    from tests import wsmp_record_ref as ref

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228 = 2, 3, 4, 5, 6
DM_OK, DM_NACK_ADDR, DM_NACK_DATA = 0, 1, 2
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN = range(1, 8)
ABSENT, PROBING, IDENTIFYING, ADMITTED, ACTIVE, SUSPECT, QUARANTINED, REFUSED = range(8)
MINUTE, HOUR = 60_000, 3_600_000
ADDR = {DEVK_SHT45: 0x44, DEVK_SHTC3: 0x70, DEVK_BMP581: 0x47, DEVK_LTR390: 0x53, DEVK_INA228: 0x40}
DEVK_EEPROM = 9
CHANNEL = {P_AIR_TH: 0, P_UVA: 1, P_PRESSURE: 2}         # the static channel map (ports design, section 4.1)
EPOCH = 7                                                  # the station boot epoch of station()


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
        lib.h_host_run(15_000)                                  # the second: the identity reads start
        self.assertEqual(lib.h_host_state(P_AIR_TH), IDENTIFYING)
        lib.h_host_run(1_000)                                   # the record read, then the 0x89 serial (2 ticks)
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


SERIAL32 = 0x1234_5678                                         # the SHT45's own serial (0x89) in these tests
REC_SERIAL = 0x01_A1B2C3D4E5F607


def sht_record(**kw):
    return ref.record(**{'bind_value': SERIAL32, **kw})


def ltr_record(**kw):
    return ref.record(**{'module_type': 3, 'bind_kind': 0, 'bind_value': 0, 'part': b'ADA-LTR390-M1', **kw})


@needs_cc
class Identity(unittest.TestCase):
    """Identification of an I2C port module (ports design, section 6.7): the record, the verdict order,
    the holder check, refusals and the boot hold. Each module has its EEPROM at 0x50 on its channel."""
    minutes, line = Host.minutes, Host.line

    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'hostid', '-DWSMP_HOST', *host_sources())._name

    def plug(self, lib, port, kind, record=None):
        """A module on port's channel: its part, and its EEPROM with record (None: no EEPROM)."""
        dev = lib.h_add_on(kind, ADDR[kind], CHANNEL[port])
        if kind == DEVK_SHT45:
            lib.h_sht45_set_serial(dev, SERIAL32, 0)
        if kind == DEVK_LTR390:
            lib.h_ltr390_set(dev, 1000)
        if kind == DEVK_BMP581:
            lib.h_bmp581_set(dev, 101_325 * 64)
        ee = None
        if record is not None:
            ee = lib.h_add_on(DEVK_EEPROM, 0x50, CHANNEL[port])
            lib.h_eeprom_write(ee, 0, record, len(record))
        return dev, ee

    def boot(self, modules):
        """A station booted with modules: [(port, kind, record)]."""
        lib = fresh_station(self, self.library)
        devs = {port: self.plug(lib, port, kind, rec) for port, kind, rec in modules}
        lib.h_init(EPOCH)
        lib.h_vane_mv(3_300)
        lib.h_host_init()
        return lib, devs

    def identity(self, lib, port):
        idb, desc = (ctypes.c_uint8 * 32)(), (ctypes.c_uint8 * 48)()
        lib.h_identity(port, idb, desc)
        b = bytes(idb)
        return {'serial': int.from_bytes(b[8:16], 'big'), 'boot': int.from_bytes(b[20:24], 'big'),
                'caps': int.from_bytes(b[24:26], 'big'), 'flags': int.from_bytes(b[30:32], 'big')}

    def slot0(self, lib, port):
        lib.h_host_slot_value.restype = ctypes.c_uint32
        return lib.h_host_slot_value(port, 0)

    def test_an_applied_record_gives_its_serial_flags_and_calibration(self):
        rec = sht_record(cal=[(1, 0, 1, 100, 1_000_000)])     # air temperature + 1.00 C
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, rec)])
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(self.identity(lib, P_AIR_TH), {'serial': REC_SERIAL, 'boot': EPOCH << 8 | 1, 'caps': 1,
                                                         'flags': 0x01})   # source record, status applied
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250 + 100)

    def test_no_eeprom_is_no_record_read_with_the_fallback_serial(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, None), (P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 1)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_PRESSURE)], [ACTIVE, ACTIVE])
        air, pressure = self.identity(lib, P_AIR_TH), self.identity(lib, P_PRESSURE)
        self.assertEqual((air['serial'], air['flags'], air['caps']), (ref.sensor_serial(1, SERIAL32), 0x12, 0))
        self.assertEqual((pressure['serial'], pressure['flags']), (ref.port_serial(P_PRESSURE, 2), 0x10))

    def test_a_read_error_is_retried_back_to_back(self):
        # Step 1: no ACK or a transfer error on 3 tries back to back is NO_RECORD (READ); fewer is not.
        for fails, flags in ((2, 0x01), (3, 0x12)):
            with self.subTest(fails=fails):
                lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
                lib.h_eeprom_fail_next(devs[P_AIR_TH][1], fails)
                self.minutes(lib, 1)
                self.assertEqual(self.identity(lib, P_AIR_TH)['flags'], flags)

    def test_a_crc_failure_is_read_once_more(self):
        for bad, flags in ((1, 0x01), (2, 0x62)):             # 0x62: source sensor, status CRC
            with self.subTest(bad=bad):
                lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
                lib.h_eeprom_corrupt_next(devs[P_AIR_TH][1], bad)
                self.minutes(lib, 1)
                self.assertEqual(self.identity(lib, P_AIR_TH)['flags'], flags)

    def test_a_changed_sensor_takes_the_sensor_serial_and_no_calibration(self):
        rec = sht_record(bind_value=SERIAL32 + 1, cal=[(1, 0, 1, 100, 1_000_000)])
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, rec)])
        self.minutes(lib, 2)
        ident = self.identity(lib, P_AIR_TH)
        self.assertEqual((ident['serial'], ident['flags'], ident['caps']), (ref.sensor_serial(1, SERIAL32), 0x82, 1))
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250)

    def test_a_failed_sensor_serial_read_is_retried_back_to_back(self):
        # A read error is not a verdict: one failed 0x89 read is tried again, and the module is
        # admitted with its record's serial and calibration, never SENSOR_CHANGED.
        rec = sht_record(cal=[(1, 0, 1, 100, 1_000_000)])
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, rec)])
        lib.h_sht45_serial_fail_next(devs[P_AIR_TH][0], 1)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(self.identity(lib, P_AIR_TH)['flags'], 0x01)
        self.assertEqual(self.identity(lib, P_AIR_TH)['serial'], REC_SERIAL)
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250 + 100)

    def test_three_failed_sensor_serial_reads_give_no_verdict_until_the_next_probe_slot(self):
        rec = sht_record(cal=[(1, 0, 1, 100, 1_000_000)])
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, rec)])
        lib.h_sht45_serial_fail_next(devs[P_AIR_TH][0], 3)
        lib.h_host_run(30_000)                                 # two probes, then the reads: 0x89 fails 3 times
        self.assertEqual(lib.h_host_state(P_AIR_TH), IDENTIFYING)
        self.assertIn(b'air_th=identifying(incomplete=1)', self.line(lib))
        self.minutes(lib, 2)                                   # the next probe slot identifies it again
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(self.identity(lib, P_AIR_TH)['flags'], 0x01)
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250 + 100)

    def test_a_sensor_serial_that_was_read_and_differs_is_sensor_changed(self):
        rec = sht_record(bind_value=SERIAL32 + 1, cal=[(1, 0, 1, 100, 1_000_000)])
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, rec)])
        lib.h_sht45_serial_fail_next(devs[P_AIR_TH][0], 1)
        self.minutes(lib, 2)
        self.assertEqual(self.identity(lib, P_AIR_TH)['flags'], 0x82)
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250)

    def test_a_type_conflict_is_quarantined_until_the_module_is_removed(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, ltr_record())])
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), QUARANTINED)
        self.assertIn(b'air_th=type_conflict', self.line(lib))
        lib.h_remove_device(devs[P_AIR_TH][0])
        lib.h_host_run(15_000)                                 # one missed probe: still quarantined
        self.assertEqual(lib.h_host_state(P_AIR_TH), QUARANTINED)
        lib.h_host_run(15_000)                                 # two in a row: removed (section 6.7)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)

    def test_a_duplicate_serial_at_boot_the_lower_port_wins_until_it_leaves(self):
        lib, devs = self.boot([(P_UVA, DEVK_LTR390, ltr_record()), (P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 1)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_UVA)], [ACTIVE, REFUSED])
        self.assertIn(b'uva=dup_serial', self.line(lib))
        for d in devs[P_AIR_TH]:
            lib.h_remove_device(d)
        self.minutes(lib, 3)                                   # three missed latches: the holder leaves ...
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)
        self.assertEqual(lib.h_host_state(P_UVA), ADMITTED)     # ... and the refusal is re-evaluated at that latch
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_UVA), ACTIVE)
        self.assertEqual(self.identity(lib, P_UVA)['serial'], REC_SERIAL)

    def test_a_refused_port_needs_two_missed_probes_to_be_absent(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record()), (P_UVA, DEVK_LTR390, ltr_record())])
        self.minutes(lib, 1)
        lib.h_remove_device(devs[P_UVA][0])
        lib.h_host_run(15_000)
        self.assertEqual(lib.h_host_state(P_UVA), REFUSED)
        lib.h_host_run(15_000)
        self.assertEqual(lib.h_host_state(P_UVA), ABSENT)

    def test_a_moved_module_ends_its_gone_holder_at_once(self):
        # The holder check finds no answer at 0x44 on two tries back to back: the holder is ended
        # before its own three missed latches, and the newcomer (the same record serial) is admitted.
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 1)
        for d in devs[P_AIR_TH]:
            lib.h_remove_device(d)
        self.plug(lib, P_UVA, DEVK_LTR390, ltr_record())
        lib.h_host_run(40_000)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_UVA)], [ABSENT, ADMITTED])

    def test_a_present_holder_refuses_the_newcomer(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 1)
        self.plug(lib, P_UVA, DEVK_LTR390, ltr_record())
        lib.h_host_run(40_000)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_UVA)], [ACTIVE, REFUSED])

    def test_the_identity_read_never_splits_a_measurement(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 3)
        self.assertEqual((lib.h_sht45_interleaved(), lib.h_sht45_read_too_early()), (0, 0))


if __name__ == '__main__':
    unittest.main()
