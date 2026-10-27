"""The WSMP station host (firmware/stage0-node/App/wsmp_host.c) on the host.

It runs over the real local modules and the host bus model (firmware/host/wsmp_harness.c with
-DWSMP_HOST). The rules are docs/module-protocol.md section 7: two good probes before admission,
three missed latches before removal, a bus fault keeps the layout, a module joins at the next latch,
the flap limit, the radio budget and quarantine. Host-model results, not bench evidence."""
import ctypes
import unittest

from ws0 import wsmp_set

try:
    from toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
    import wsmp_record_ref as ref
    import wsmp_wind_ref as wind_ref
except ImportError:
    from tests.toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>
    from tests import wsmp_record_ref as ref
    from tests import wsmp_wind_ref as wind_ref

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228 = 2, 3, 4, 5, 6
DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_BUS_ERROR = 0, 1, 2, 6
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN = range(1, 8)
P_COUNT_ = 8
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



def bmp_record(**kw):
    return ref.record(**{'module_type': 2, 'serial': REC_SERIAL + 0x100, 'bind_kind': 0, 'bind_value': 0,
                         'part': b'ADA-BMP581-M1', **kw})


def bad_crc(rec, at=0x7E):
    b = bytearray(rec)
    b[at] ^= 0x10
    return bytes(b)


BMP_VALUE = 10133                                              # 101 325 Pa in 0.1 hPa
SLOT_MS = 3_000


@needs_cc
class Reidentify(unittest.TestCase):
    """Re-identification before every latch (ports design, section 6.7; PORT-16, PORT-17): the pre-latch
    slot, the identity check against the identity seen at admission, the sticky possibly-replugged
    flag, the unverified counter and the 60-latch timeout. The latches fall every minute from boot."""
    minutes, line = Host.minutes, Host.line
    plug, identity, slot0 = Identity.plug, Identity.identity, Identity.slot0

    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'hostre', '-DWSMP_HOST', *host_sources())._name
        cls.noslot = host_library(cls, 'hostnoslot', '-DWSMP_HOST', '-DWSMP_HOST_SLOT_MS=0', *host_sources())._name

    def boot(self, modules, library=None, phase=0, upstream=()):
        lib = fresh_station(self, library or self.library)
        devs = {port: self.plug(lib, port, kind, rec) for port, kind, rec in modules}
        for kind in upstream:
            lib.h_add_device(kind, ADDR[kind])
        lib.h_init(EPOCH)
        lib.h_advance(phase)                                   # the latches start phase ms after the samples
        lib.h_vane_mv(3_300)
        lib.h_host_init()
        return lib, devs

    def quality(self, lib, port):
        return lib.h_host_slot_quality(port, 0)

    def withheld(self, lib, port):
        """1 if the port's last window is published as missing (every slot missing)."""
        return lib.h_host_has_snapshot(port) == 1 and self.quality(lib, port) == 3

    def nack_one_sample(self, lib, dev, mode=DM_NACK_ADDR):
        """One sample of the module fails (a missed probe), the others in the window are good."""
        lib.h_host_run(20_000)
        lib.h_device_mode(dev, mode, 0, 1)
        lib.h_host_run(15_000)
        lib.h_device_mode(dev, DM_OK, 0, 1)
        lib.h_host_run(25_000)
        lib.h_host_latch(1_792_000_000)

    # -- the slot -------------------------------------------------------------------------------------

    def window_counts(self, library, phase, latches=7):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record()), (P_PRESSURE, DEVK_BMP581, bmp_record()),
                            (P_UVA, DEVK_LTR390, None)], library, phase, upstream=(DEVK_SHTC3, DEVK_INA228))
        counts = []
        for _ in range(latches):
            self.minutes(lib, 1)
            counts.append([[lib.h_host_slot_count(p, i) for i in range(3)] for p in range(P_AIR_TH, P_COUNT_)])
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        return counts

    def test_the_slot_keeps_every_windows_sample_count(self):
        # PORT-16: a port-module sample due in the slot is deferred past the latch, phase kept; the
        # on-board drivers never wait. Each window after the first two (admission) has the counts of a
        # station without the slot.
        import random
        phases = [0, 250, 1_000, 2_999, 3_000, 3_001] + random.Random(16).sample(range(15_000), 4)
        for phase in phases:
            with self.subTest(phase=phase):
                with_slot, without = self.window_counts(self.library, phase), self.window_counts(self.noslot, phase)
                self.assertEqual(with_slot[2:], without[2:])
                self.assertEqual([w[P_AIR_TH - 1][0] for w in with_slot[2:]], [4] * 5)

    def test_no_port_module_sample_starts_in_the_slot_and_the_check_never_splits_one(self):
        for phase in (0, 250, 1_000, 2_750, 3_000, 3_250, 7_000, 14_750):
            with self.subTest(phase=phase):
                lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())], phase=phase)
                lib.h_now_ms.restype = ctypes.c_uint32
                latch = lib.h_now_ms() + MINUTE
                for _ in range(4):
                    checks = 0
                    while lib.h_now_ms() < latch:
                        t, measures, serials = lib.h_now_ms(), lib.h_sht45_commands(), lib.h_sht45_serial_commands()
                        lib.h_host_run(250)
                        if t >= latch - SLOT_MS:
                            self.assertEqual(lib.h_sht45_commands(), measures, f'a sample started in the slot at {t}')
                            checks += lib.h_sht45_serial_commands() - serials
                    lib.h_host_latch(1_792_000_000)
                    latch += MINUTE
                    if lib.h_host_state(P_AIR_TH) == ACTIVE:
                        self.assertEqual(checks, 1)            # the identity check's 0x89, once
                self.assertEqual((lib.h_sht45_interleaved(), lib.h_sht45_read_too_early()), (0, 0))
                self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
                self.assertFalse(self.withheld(lib, P_AIR_TH))
                self.assertNotIn(b'unverified', self.line(lib))

    def test_a_check_that_cannot_finish_by_the_latch_is_unverified(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        changes = lib.h_host_changes(P_AIR_TH)
        for n in range(1, 4):
            lib.h_host_run(MINUTE - SLOT_MS + 250)           # the slot's first tick, then the latch
            lib.h_host_latch(1_792_000_000)
            self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
            self.assertFalse(self.withheld(lib, P_AIR_TH))       # no flag: published as usual
            self.assertEqual(b'air_th=active(unverified=3)' in self.line(lib), n == 3)
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes)
        self.minutes(lib, 1)
        self.assertNotIn(b'unverified', self.line(lib))       # a matched check resets the run

    def test_the_identity_check_has_priority_over_a_holder_check(self):
        # The newcomer's second probe falls just before or in the slot (the latches start phase ms after
        # the samples): an identification or a holder check that has not begun waits until after the
        # latch (one already running finishes), so in the slot only the identity check sends the
        # holder's 0x89.
        for phase in range(3_000, 6_001, 250):
            with self.subTest(phase=phase):
                lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())], phase=phase)
                lib.h_now_ms.restype = ctypes.c_uint32
                self.minutes(lib, 1)
                lib.h_host_run(100_000 - lib.h_now_ms())       # probes at 105 s and 120 s
                self.plug(lib, P_UVA, DEVK_LTR390, ltr_record())
                for latch in (phase + 2 * MINUTE, phase + 3 * MINUTE):
                    checks = 0
                    while lib.h_now_ms() < latch:
                        t, serials = lib.h_now_ms(), lib.h_sht45_serial_commands()
                        lib.h_host_run(250)
                        if t > latch - SLOT_MS:
                            checks += lib.h_sht45_serial_commands() - serials
                    lib.h_host_latch(1_792_000_000)
                    self.assertEqual(checks, 1)
                self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_UVA)], [ACTIVE, REFUSED])
                self.assertFalse(self.withheld(lib, P_AIR_TH))
                self.assertNotIn(b'unverified', self.line(lib))

    # -- confirmed changes ----------------------------------------------------------------------------

    def test_an_sht45_board_swap_ends_the_port_at_the_next_latch(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record(cal=[(1, 0, 1, 100, 1_000_000)]))])
        self.minutes(lib, 2)
        changes = lib.h_host_changes(P_AIR_TH)
        lib.h_host_run(30_000)
        lib.h_sht45_set_serial(devs[P_AIR_TH][0], SERIAL32 + 5, 0)   # a new sensor board, the old record
        lib.h_host_run(30_000)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)  # ended at this latch ...
        self.assertEqual(lib.h_host_has_snapshot(P_AIR_TH), 0)   # ... no window under the old coefficients
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes + 1)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        ident = self.identity(lib, P_AIR_TH)
        self.assertEqual((ident['serial'], ident['flags']), (ref.sensor_serial(1, SERIAL32 + 5), 0x82))
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4250)     # SENSOR_CHANGED: no calibration

    def test_a_swap_whose_sensor_serial_fails_but_whose_record_differs_is_a_change(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        dev, ee = devs[P_AIR_TH]
        lib.h_host_run(30_000)
        rec = sht_record(serial=REC_SERIAL + 1, bind_value=SERIAL32 + 7)
        lib.h_eeprom_write(ee, 0, rec, len(rec))
        lib.h_sht45_set_serial(dev, SERIAL32 + 7, 1)         # its 0x89 fails its CRC every time
        lib.h_host_run(30_000)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)

    def test_a_swap_within_one_read_is_a_leave_and_a_join(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        changes = lib.h_host_changes(P_AIR_TH)
        lib.h_host_run(30_000)
        for d in devs[P_AIR_TH]:
            lib.h_remove_device(d)
        dev, _ = self.plug(lib, P_AIR_TH, DEVK_SHT45, sht_record(serial=REC_SERIAL + 2, bind_value=SERIAL32 + 9))
        lib.h_sht45_set_serial(dev, SERIAL32 + 9, 0)
        lib.h_host_run(30_000)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(self.identity(lib, P_AIR_TH)['serial'], REC_SERIAL + 2)
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes + 2)

    def descriptor_set(self, lib):
        out = (ctypes.c_uint8 * 296)()
        n = lib.h_host_set(out)                 # fill the buffer first, then copy it
        return wsmp_set.unpack(bytes(out)[:n])

    def ident_lines(self, lib):
        lines, buf = [], ctypes.create_string_buffer(112)
        for i in range(8):
            if not lib.h_host_ident_line(i, buf, 112):
                break
            lines.append(buf.value)
        return lines

    def test_the_set_carries_each_modules_identity(self):
        # WSMP section 11.1 with the identity entry of the ports design (section 6.7): an applied record
        # gives its serial and CRC, a module without an EEPROM its fallback serial, NO_RECORD (READ)
        # and CRC 0; the set passes the gateway's registry check (WSMP-E7)
        rec = sht_record(cal=[(1, 0, 1, 100, 1_000_000)])
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, rec), (P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 2)
        s = self.descriptor_set(lib)
        self.assertIsNone(wsmp_set.check(s))
        air, pressure = s.modules
        self.assertEqual((air.port, air.type, air.serial, air.source, air.status, air.record_crc),
                         (P_AIR_TH, 1, REC_SERIAL, 'record', 'applied', int.from_bytes(rec[0x7C:0x80], 'big')))
        self.assertEqual((pressure.port, pressure.type, pressure.serial, pressure.source, pressure.status,
                          pressure.no_record, pressure.record_crc),
                         (P_PRESSURE, 2, ref.port_serial(P_PRESSURE, 2), 'port', 'READ', True, 0))

    def test_a_module_whose_record_is_not_applied_has_crc_0(self):
        # SENSOR_CHANGED: a valid record bound to another SHT4x serial; serial from the sensor, CRC 0
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record(bind_value=SERIAL32 + 1))])
        self.minutes(lib, 2)
        (air,) = self.descriptor_set(lib).modules
        self.assertEqual((air.serial, air.source, air.status, air.record_crc),
                         (ref.sensor_serial(1, SERIAL32), 'sensor', 'SENSOR_CHANGED', 0))

    def test_a_changed_record_crc_changes_the_set(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record(cal=[(1, 0, 1, 100, 1_000_000)]))])
        self.minutes(lib, 2)
        before = self.descriptor_set(lib)
        rec = sht_record(cal=[(1, 0, 2, 50, 1_000_000)])     # recalibrated on the fixture, same serial
        lib.h_eeprom_write(devs[P_AIR_TH][1], 0, rec, len(rec))
        self.minutes(lib, 1)
        self.assertEqual(self.descriptor_set(lib).modules, ())          # left at the latch
        self.minutes(lib, 2)
        after = self.descriptor_set(lib)
        self.assertEqual(after.modules[0].serial, before.modules[0].serial)
        self.assertEqual(after.modules[0].record_crc, int.from_bytes(rec[0x7C:0x80], 'big'))
        self.assertNotEqual(after.digest, before.digest)                 # a new set: the WSMP-C1 boundary

    def test_a_cal_rejected_record_has_crc_0(self):
        # a structurally valid record whose calibration fails check 7: its serial is kept, no CRC
        lib, _ = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 500, 1_000_000)]))])
        self.minutes(lib, 2)
        (pressure,) = self.descriptor_set(lib).modules
        self.assertEqual((pressure.serial, pressure.source, pressure.status, pressure.record_crc),
                         (REC_SERIAL + 0x100, 'record', 'CAL_REJECTED', 0))

    def test_a_suspect_module_stays_in_the_set(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        lib.h_device_mode(devs[P_AIR_TH][0], DM_NACK_ADDR, 0, 1)
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), SUSPECT)
        self.assertEqual([m.serial for m in self.descriptor_set(lib).modules], [REC_SERIAL])

    def test_a_module_whose_blocks_do_not_unpack_is_counted(self):
        # a bug, never a silent gap: left out of the set and counted (#ident dropped=N)
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record()), (P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_set_dropped(), 0)
        lib.h_break_identity(P_PRESSURE)
        self.assertEqual([m.port for m in self.descriptor_set(lib).modules], [P_AIR_TH])
        self.assertEqual(lib.h_host_set_dropped(), 1)

    def test_a_module_that_never_has_a_record_shows_status_none(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        lib.h_vane_mv(wind_ref.vane_mv(0))                    # the wind module: a meter, no record in v1
        self.minutes(lib, 3)
        self.assertEqual(lib.h_host_state(P_WIND), ACTIVE)
        self.assertEqual(self.ident_lines(lib)[-1],
                         b'#ident port=6 type=6 serial=%016x source=port status=none crc=00000000' % ref.port_serial(P_WIND, 6))

    def test_only_the_layout_is_in_the_set(self):
        # a quarantined port (a type conflict) and a probing one are not in the layout, so not in the set
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, ltr_record()), (P_UVA, DEVK_LTR390, ltr_record(serial=REC_SERIAL + 1))])
        self.minutes(lib, 2)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_UVA)], [QUARANTINED, ACTIVE])
        self.plug(lib, P_PRESSURE, DEVK_BMP581)
        lib.h_host_run(750)
        self.assertEqual(lib.h_host_state(P_PRESSURE), PROBING)
        self.assertEqual([m.port for m in self.descriptor_set(lib).modules], [P_UVA])

    def test_the_ident_lines_follow_the_set(self):
        rec = sht_record()
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, rec), (P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 2)
        crc = rec[0x7C:0x80].hex().encode()
        self.assertEqual(self.ident_lines(lib), [
            b'#ident port=1 type=1 serial=%016x source=record status=applied crc=%s' % (REC_SERIAL, crc),
            b'#ident port=2 type=2 serial=%016x source=port status=READ crc=00000000' % ref.port_serial(P_PRESSURE, 2)])

    def test_a_changed_record_crc_with_the_same_serial_is_a_leave_and_a_join(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record(cal=[(1, 0, 1, 100, 1_000_000)]))])
        self.minutes(lib, 2)
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4350)
        changes = lib.h_host_changes(P_AIR_TH)
        rec = sht_record(cal=[(1, 0, 2, 50, 1_000_000)])     # recalibrated on the fixture, same serial
        lib.h_eeprom_write(devs[P_AIR_TH][1], 0, rec, len(rec))
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ABSENT)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertEqual(self.slot0(lib, P_AIR_TH), 4300)
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes + 2)

    def test_the_order_within_a_latch_with_changes_on_several_ports(self):
        # Transitions, then the identity results in port order, then the refusals: the refused clone of
        # the air module's record is admitted at the latch that ends the air module.
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record()),
                               (P_PRESSURE, DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 10, 1_000_000)])),
                               (P_UVA, DEVK_LTR390, ltr_record())])
        self.minutes(lib, 2)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_PRESSURE, P_UVA)], [ACTIVE, ACTIVE, REFUSED])
        lib.h_host_run(30_000)
        lib.h_sht45_set_serial(devs[P_AIR_TH][0], SERIAL32 + 5, 0)
        rec = bmp_record(cal=[(3, 0, 2, 20, 1_000_000)])
        lib.h_eeprom_write(devs[P_PRESSURE][1], 0, rec, len(rec))
        lib.h_host_run(30_000)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual([lib.h_host_state(p) for p in (P_AIR_TH, P_PRESSURE, P_UVA)], [ABSENT, ABSENT, ADMITTED])

    # -- the sticky flag -------------------------------------------------------------------------------

    def test_a_noticed_replug_is_missing_until_a_matched_check_then_a_new_boot_id(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        dev, ee = devs[P_AIR_TH]
        changes = lib.h_host_changes(P_AIR_TH)
        self.assertEqual(self.identity(lib, P_AIR_TH)['boot'], EPOCH << 8 | 1)
        lib.h_sht45_serial_fail_next(dev, 1)                   # and the check's reads fail: unverified
        lib.h_eeprom_fail_next(ee, 1)
        self.nack_one_sample(lib, dev)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertTrue(self.withheld(lib, P_AIR_TH))           # the flag survives an unverified check
        self.minutes(lib, 1)
        self.assertFalse(self.withheld(lib, P_AIR_TH))          # matched: published, the flag cleared
        self.assertEqual(self.identity(lib, P_AIR_TH)['boot'], EPOCH << 8 | 2)
        self.assertEqual(lib.h_host_snap_boot(P_AIR_TH), (EPOCH << 8 | 2) & 0xFFFF)
        self.assertEqual(self.identity(lib, P_AIR_TH)['serial'], REC_SERIAL)
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes)

    def test_a_failed_identity_check_read_alone_does_not_set_the_flag(self):
        lib, devs = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        dev, ee = devs[P_AIR_TH]
        lib.h_sht45_serial_fail_next(dev, 1)
        lib.h_eeprom_fail_next(ee, 1)
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertFalse(self.withheld(lib, P_AIR_TH))
        self.minutes(lib, 1)
        self.assertEqual(self.identity(lib, P_AIR_TH)['boot'], EPOCH << 8 | 1)   # no flag, nothing to clear

    def test_one_corrupted_bit_in_the_serial_read_is_not_a_change(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        lib.h_eeprom_corrupt_at(ee, 0x0F, 1)                   # the 8-byte serial read; the full read is clean
        self.nack_one_sample(lib, bmp)                         # with the flag set, only a match publishes
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertFalse(self.withheld(lib, P_PRESSURE))
        self.assertEqual(self.identity(lib, P_PRESSURE)['boot'], EPOCH << 8 | 2)
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    # -- unverified, Suspect and the timeout (PORT-17) --------------------------------------------------

    def test_an_eeprom_that_nacks_intermittently_keeps_the_port_published(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        pattern = [1, 0] * 3 + [1] * 10 + [0]                  # every other latch, then 10 in a row, then back
        run = 0
        for gone in pattern:
            if gone:
                lib.h_remove_device(ee)
            self.minutes(lib, 1)
            lib.h_restore_device(ee)
            run = run + 1 if gone else 0
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertFalse(self.withheld(lib, P_PRESSURE))
            self.assertEqual(self.identity(lib, P_PRESSURE)['serial'], REC_SERIAL + 0x100)
            shown = f'pressure=active(unverified={run})'.encode()
            self.assertEqual(shown in self.line(lib), run >= 3, self.line(lib))
        self.assertNotIn(b'unverified', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    def test_a_suspect_module_with_good_reads_and_unverified_checks_times_out_once(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        lib.h_remove_device(ee)                                # every check unverified from now on
        lib.h_remove_device(bmp)
        self.minutes(lib, 1)                                   # a missed latch: Suspect, the flag set
        lib.h_restore_device(bmp)
        for _ in range(58):                                    # good reads, unverified: the count is frozen
            self.minutes(lib, 1)
            self.assertEqual(lib.h_host_state(P_PRESSURE), SUSPECT)
            self.assertTrue(self.withheld(lib, P_PRESSURE))
        self.minutes(lib, 1)                                   # the 60th flagged, unverified latch in a row
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 1)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)   # rejoined as NO_RECORD (READ) ...
        self.assertEqual(self.identity(lib, P_PRESSURE)['flags'], 0x10)
        self.minutes(lib, 5)
        self.assertFalse(self.withheld(lib, P_PRESSURE))         # ... whose NACK then matches
        self.assertNotIn(b'unverified', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 2)   # once

    def test_an_active_bmp581_whose_eeprom_dies_then_one_read_fails(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        lib.h_remove_device(ee)
        self.minutes(lib, 3)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertFalse(self.withheld(lib, P_PRESSURE))       # unverified, no flag: still published
        self.assertIn(b'pressure=active(unverified=3)', self.line(lib))
        self.nack_one_sample(lib, bmp, DM_NACK_DATA)           # a failed data read: the flag
        self.assertTrue(self.withheld(lib, P_PRESSURE))
        for _ in range(58):
            self.minutes(lib, 1)
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertTrue(self.withheld(lib, P_PRESSURE))
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertEqual(self.identity(lib, P_PRESSURE)['flags'], 0x10)
        self.assertFalse(self.withheld(lib, P_PRESSURE))
        self.minutes(lib, 3)
        self.assertNotIn(b'unverified', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 2)

    def test_miss_good_unverified_miss_good_unverified_miss_removes_the_module(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        lib.h_remove_device(ee)
        for missed, state in ((1, SUSPECT), (0, SUSPECT), (1, SUSPECT), (0, SUSPECT), (1, ABSENT)):
            if missed:
                lib.h_remove_device(bmp)
            self.minutes(lib, 1)
            lib.h_restore_device(bmp)
            self.assertEqual(lib.h_host_state(P_PRESSURE), state)

    def test_a_port_fault_fails_every_check_without_moving_the_port(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        for d in (bmp, ee):
            lib.h_device_mode(d, DM_BUS_ERROR, 0, 1)
        for _ in range(5):
            self.minutes(lib, 1)
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertTrue(self.withheld(lib, P_PRESSURE))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    # -- what admission saw ------------------------------------------------------------------------------

    def test_modules_admitted_without_an_applied_record_do_not_flap(self):
        rows = [('READ', DEVK_BMP581, None, 0x10), ('BLANK', DEVK_BMP581, bytes([0xFF]) * 128, 0x20),
                ('CRC', DEVK_BMP581, bad_crc(bmp_record()), 0x60),
                ('MALFORMED', DEVK_BMP581, bmp_record(bind_kind=1, bind_value=7), 0x50),
                ('CAL_REJECTED', DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 500, 1_000_000)]), 0x71),
                ('SENSOR_CHANGED', DEVK_SHT45, sht_record(bind_value=SERIAL32 + 1), 0x82)]
        for name, kind, rec, flags in rows:
            with self.subTest(name):
                port = P_AIR_TH if kind == DEVK_SHT45 else P_PRESSURE
                lib, devs = self.boot([(port, kind, rec)])
                self.minutes(lib, 2)
                self.assertEqual(self.identity(lib, port)['flags'], flags)
                changes = lib.h_host_changes(port)
                self.minutes(lib, 50)
                self.nack_one_sample(lib, devs[port][0])        # a flag that only a matched check clears
                self.assertFalse(self.withheld(lib, port))
                self.minutes(lib, 50)
                self.assertEqual(lib.h_host_state(port), ACTIVE)
                self.assertEqual(lib.h_host_changes(port), changes)
                self.assertNotIn(b'unverified', self.line(lib))

    def test_a_read_module_whose_record_appears_changes_once(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 2)
        changes = lib.h_host_changes(P_PRESSURE)
        ee = lib.h_add_on(DEVK_EEPROM, 0x50, CHANNEL[P_PRESSURE])
        rec = bmp_record()
        lib.h_eeprom_write(ee, 0, rec, len(rec))
        self.minutes(lib, 1)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
        self.minutes(lib, 2)
        self.assertEqual((lib.h_host_state(P_PRESSURE), self.identity(lib, P_PRESSURE)['flags']), (ACTIVE, 0x01))
        lib.h_remove_device(ee)                                # a later NACK is never a change
        self.minutes(lib, 5)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 2)

    def test_a_content_no_record_or_cal_rejected_module_whose_record_reads_valid_later_is_a_change(self):
        for name, first in (('CRC', bad_crc(bmp_record())), ('MALFORMED', bmp_record(bind_kind=1, bind_value=7)),
                            ('CAL_REJECTED', bmp_record(cal=[(3, 0, 1, 500, 1_000_000)]))):
            with self.subTest(name):
                lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, first)])
                self.minutes(lib, 2)
                rec = bmp_record(cal=[(3, 0, 1, 10, 1_000_000)])
                lib.h_eeprom_write(devs[P_PRESSURE][1], 0, rec, len(rec))
                self.minutes(lib, 1)
                self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
                self.minutes(lib, 2)
                self.assertEqual(self.identity(lib, P_PRESSURE)['flags'], 0x01)
                self.assertEqual(self.slot0(lib, P_PRESSURE), BMP_VALUE + 10)

    def test_a_corrupt_tail_that_drifts_is_not_a_change(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bad_crc(bmp_record()))])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        for i in range(5):
            lib.h_eeprom_write(ee, 0x70 + i, bytes([0x5A]), 1)   # a new image, the same verdict, status, serial
            self.nack_one_sample(lib, bmp)
            self.assertFalse(self.withheld(lib, P_PRESSURE))   # matched
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    def test_two_full_reads_that_disagree_are_unverified(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bad_crc(bmp_record()))])
        self.minutes(lib, 2)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        for _ in range(3):
            lib.h_eeprom_corrupt_at(ee, 0x40, 1)                # the first read differs, the second does not
            self.minutes(lib, 1)
        self.assertIn(b'pressure=active(unverified=3)', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)


    # -- an applied record whose full read cannot be parsed (section 6.7, the applied row) ---------------

    def swap_in_slot(self, lib, setup):
        """Runs half a minute, calls setup() (the swap), then runs to the latch and latches."""
        lib.h_host_run(30_000)
        setup()
        lib.h_host_run(30_000)
        lib.h_host_latch(1_792_000_000)

    def test_an_applied_record_swapped_for_a_blank_eeprom_ends_the_port(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 10, 1_000_000)]))])
        self.minutes(lib, 2)
        self.assertEqual(self.slot0(lib, P_PRESSURE), BMP_VALUE + 10)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        self.swap_in_slot(lib, lambda: lib.h_eeprom_write(ee, 0, bytes([0xFF]) * 128, 128))   # no missed probe
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)   # two full reads that agree: a change
        self.assertEqual(lib.h_host_has_snapshot(P_PRESSURE), 0)  # the window is missing
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertEqual(self.identity(lib, P_PRESSURE)['flags'], 0x20)   # NO_RECORD (BLANK)
        self.assertEqual(self.slot0(lib, P_PRESSURE), BMP_VALUE)          # no calibration
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 2)

    def test_an_applied_record_whose_full_reads_both_nack_ends_the_port(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 10, 1_000_000)]))])
        self.minutes(lib, 2)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)

        def gone_after_the_short_read():
            lib.h_eeprom_corrupt_at(ee, 0x0F, 1)               # the 8-byte serial read differs ...
            lib.h_eeprom_fail_after(ee, 1, 2)                  # ... then both full reads NACK at 0x50
        self.swap_in_slot(lib, gone_after_the_short_read)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
        self.assertEqual(lib.h_host_has_snapshot(P_PRESSURE), 0)
        lib.h_remove_device(ee)                                # the module that joins has no EEPROM
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
        self.assertEqual(self.identity(lib, P_PRESSURE)['flags'], 0x10)   # NO_RECORD (READ)
        self.assertEqual(self.slot0(lib, P_PRESSURE), BMP_VALUE)
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes + 2)

    def test_an_applied_record_whose_full_reads_disagree_is_unverified(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record(cal=[(3, 0, 1, 10, 1_000_000)]))])
        self.minutes(lib, 2)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        blank = bytes([0xFF]) * 128
        lib.h_eeprom_write(ee, 0, blank, 128)
        setups = (lambda: lib.h_eeprom_corrupt_at(ee, 0x40, 1),   # the first full read differs from the second
                  lambda: lib.h_eeprom_fail_after(ee, 1, 1),      # a NACK, then a blank image
                  lambda: lib.h_eeprom_corrupt_at(ee, 0x40, 1))
        for setup in setups:
            self.swap_in_slot(lib, setup)
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertFalse(self.withheld(lib, P_PRESSURE))   # no flag: published as usual
        self.assertIn(b'pressure=active(unverified=3)', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    # -- the counters and the flag at the edges ----------------------------------------------------------

    def test_a_module_removed_by_three_missed_latches_shows_no_unverified_count(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        lib.h_remove_device(ee)
        self.minutes(lib, 3)
        self.assertIn(b'pressure=active(unverified=3)', self.line(lib))
        lib.h_remove_device(bmp)
        self.minutes(lib, 3)
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)
        self.assertNotIn(b'unverified', self.line(lib))

    def test_an_unplugged_read_module_takes_one_new_boot_id_per_replug(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, None)])
        self.minutes(lib, 2)
        bmp, _ = devs[P_PRESSURE]
        boot = self.identity(lib, P_PRESSURE)['boot']
        self.assertEqual(boot, EPOCH << 8 | 1)
        for _replug in (1, 2):
            lib.h_remove_device(bmp)
            for _ in range(2):                                 # missed latches: the NACK at 0x50 never matches
                self.minutes(lib, 1)
                self.assertEqual(lib.h_host_state(P_PRESSURE), SUSPECT)
                self.assertEqual(self.identity(lib, P_PRESSURE)['boot'], boot)
            lib.h_restore_device(bmp)
            self.minutes(lib, 1)
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            boot += 1
            self.assertEqual(self.identity(lib, P_PRESSURE)['boot'], boot)   # once
            self.assertEqual(lib.h_host_snap_boot(P_PRESSURE), boot & 0xFFFF)
            self.assertFalse(self.withheld(lib, P_PRESSURE))
            self.minutes(lib, 2)
            self.assertEqual(self.identity(lib, P_PRESSURE)['boot'], boot)

    def test_a_match_partway_through_resets_the_timeout_run(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        bmp, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        lib.h_remove_device(ee)
        self.nack_one_sample(lib, bmp, DM_NACK_DATA)           # the flag, the check unverified: run 1
        self.minutes(lib, 29)                                  # run 30
        self.assertTrue(self.withheld(lib, P_PRESSURE))
        lib.h_restore_device(ee)
        self.minutes(lib, 1)                                   # matched: the flag cleared, the run reset
        self.assertFalse(self.withheld(lib, P_PRESSURE))
        lib.h_remove_device(ee)
        self.nack_one_sample(lib, bmp, DM_NACK_DATA)           # a new run: 1
        for _ in range(58):
            self.minutes(lib, 1)
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertTrue(self.withheld(lib, P_PRESSURE))
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)
        self.minutes(lib, 1)                                   # the 60th of this run
        self.assertEqual(lib.h_host_state(P_PRESSURE), ABSENT)

    def test_a_check_still_running_at_the_latch_finishes_after_it_unverified(self):
        lib, devs = self.boot([(P_PRESSURE, DEVK_BMP581, bmp_record())])
        self.minutes(lib, 2)
        _, ee = devs[P_PRESSURE]
        changes = lib.h_host_changes(P_PRESSURE)
        lib.h_device_mode(ee, DM_OK, 0, 4_000)                 # the slot's reads take 4 s each
        for n in range(1, 4):
            self.minutes(lib, 1)                               # the check is on the bus at the latch
            self.assertEqual(lib.h_host_state(P_PRESSURE), ACTIVE)
            self.assertFalse(self.withheld(lib, P_PRESSURE))
            self.assertEqual(b'pressure=active(unverified=3)' in self.line(lib), n == 3)
        lib.h_host_run(10_000)                                 # the last check finishes after its latch ...
        lib.h_device_mode(ee, DM_OK, 0, 1)
        lib.h_host_run(MINUTE - 10_000)
        lib.h_host_latch(1_792_000_000)                        # ... and the next latch has its own check
        self.assertNotIn(b'unverified', self.line(lib))
        self.assertEqual(lib.h_host_slot_count(P_PRESSURE, 0), 4)
        self.assertEqual(lib.h_host_changes(P_PRESSURE), changes)

    # -- the latch schedule --------------------------------------------------------------------------------

    def serial_checks(self, lib, ms):
        before = lib.h_sht45_serial_commands()
        lib.h_host_run(ms)
        return lib.h_sht45_serial_commands() - before

    def test_a_latch_before_its_slot_is_unverified(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        changes = lib.h_host_changes(P_AIR_TH)
        for n in range(1, 4):
            self.assertEqual(self.serial_checks(lib, MINUTE - SLOT_MS - 1_000), 0)   # an early latch: no slot
            lib.h_host_latch(1_792_000_000)
            self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
            self.assertFalse(self.withheld(lib, P_AIR_TH))
            self.assertEqual(b'air_th=active(unverified=3)' in self.line(lib), n == 3)
        self.minutes(lib, 1)
        self.assertNotIn(b'unverified', self.line(lib))
        self.assertEqual(lib.h_host_changes(P_AIR_TH), changes)

    def test_a_late_latch_keeps_the_schedule(self):
        # The sample task ran 2 s late: the next latch is still due a minute after this one was due.
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        lib.h_host_run(MINUTE + 2_000)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(self.serial_checks(lib, MINUTE - 2_000 - SLOT_MS - 250), 0)
        self.assertEqual(self.serial_checks(lib, 1_000), 1)    # the slot opens 3 s before the scheduled latch
        lib.h_host_run(SLOT_MS - 750)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertNotIn(b'unverified', self.line(lib))

    def test_the_next_latch_told_by_the_application_moves_the_slot(self):
        lib, _ = self.boot([(P_AIR_TH, DEVK_SHT45, sht_record())])
        self.minutes(lib, 2)
        lib.h_now_ms.restype = ctypes.c_uint32
        lib.h_host_next_latch(lib.h_now_ms() + 20_000)
        self.assertEqual(self.serial_checks(lib, 20_000 - SLOT_MS - 250), 0)
        self.assertEqual(self.serial_checks(lib, 1_000), 1)
        lib.h_host_run(SLOT_MS - 750)
        lib.h_host_latch(1_792_000_000)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        self.assertFalse(self.withheld(lib, P_AIR_TH))
        self.assertEqual(self.serial_checks(lib, MINUTE - SLOT_MS - 250), 0)   # then a minute from that latch
        self.assertEqual(self.serial_checks(lib, 1_000), 1)

if __name__ == '__main__':
    unittest.main()
