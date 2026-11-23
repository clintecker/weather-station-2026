"""PODWRITE: the TX writes a pod's ID record over the mux (firmware/stage0-node/App/pod_write.c).

It runs over the real station host, port_id and the local modules on the host bus model
(firmware/host/wsmp_harness.c with -DWSMP_HOST), with the 24LC32 model taking page writes, its 5 ms
write cycle (address NACKed) and WP. The expected record bytes come from the independent reference
tests/wsmp_record_ref.py and the record layout in docs/firmware-current-design.md section 6.9, not from
the code under test. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
    import wsmp_record_ref as ref
except ImportError:
    from tests.toolchain import fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>
    from tests import wsmp_record_ref as ref

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVK_SHT45, DEVK_BMP581, DEVK_LTR390, DEVK_EEPROM = 2, 4, 5, 9
ADDR = {DEVK_SHT45: 0x44, DEVK_BMP581: 0x47, DEVK_LTR390: 0x53}
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH = 1, 2, 3, 4
CHANNEL = {P_AIR_TH: 0, P_UVA: 1, P_PRESSURE: 2}          # the static channel map (firmware-current-design.md 4.1)
ACTIVE = 4
MINUTE = 60_000
EPOCH = 7
SERIAL32 = 0x1234_5678                                    # the SHT45's own serial (0x89)
SERIAL = 0x0102_0304_0506_0708                            # a record serial, namespace 0x01
UTC = 1_795_000_000
PW_OK, PW_HAS_RECORD, PW_NO_EEPROM, PW_NO_SERIAL, PW_WRITE, PW_TIMEOUT, PW_VERIFY = range(7)
START_OK, START_BUSY, START_PORT, START_TYPE, START_SERIAL = range(5)
PART = {1: b'WS-POD-TH-R1', 2: b'WS-POD-BARO-R1', 3: b'WS-POD-UV-R1'}


def expected(module_type, bind_value=0):
    """The record PODWRITE must write, from the reference: no calibration, board revision 1 (pods-r1)."""
    return ref.record(module_type=module_type, serial=SERIAL, bind_kind=1 if module_type == 1 else 0,
                      bind_value=bind_value, part=PART[module_type], hw=1, programmed=UTC)


@needs_cc
class Parse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = host_library(cls, 'podparse', '-DWSMP_HOST', *wsmp_sources(),
                               ROOT/'firmware/stage0-node/App/wsmp_host.c')

    def parse(self, text):
        port, typ, serial = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint64()
        rc = self.lib.h_pw_parse(text.encode(), ctypes.byref(port), ctypes.byref(typ), ctypes.byref(serial))
        return (rc, port.value, typ.value, serial.value) if rc == 0 else rc

    def test_the_full_line_parses(self):
        self.assertEqual(self.parse('1 1 0102030405060708 WRITE-POD-RECORD'), (0, 1, 1, 0x0102030405060708))
        self.assertEqual(self.parse('3 3 01abcdefABCDEF01 WRITE-POD-RECORD'), (0, 3, 3, 0x01ABCDEFABCDEF01))

    def test_without_the_exact_confirm_token_nothing_parses(self):
        for text in ('1 1 0102030405060708', '1 1 0102030405060708 ', '1 1 0102030405060708 write-pod-record',
                     '1 1 0102030405060708 WRITE-POD-RECORD ', '1 1 0102030405060708 WRITE-POD-RECORDS',
                     '1 1 0102030405060708 YES'):
            self.assertEqual(self.parse(text), -1, text)

    def test_bad_fields_do_not_parse(self):
        for text in ('', '1', '9 1 0102030405060708 WRITE-POD-RECORD', '1 65536 0102030405060708 WRITE-POD-RECORD',
                     '1 1 010203040506070 WRITE-POD-RECORD', '1 1 01020304050607089 WRITE-POD-RECORD',
                     '1 1 01020304050607zz WRITE-POD-RECORD', ' 1 1 0102030405060708 WRITE-POD-RECORD',
                     '1  1 0102030405060708 WRITE-POD-RECORD', '123456 1 0102030405060708 WRITE-POD-RECORD',
                     'x 1 0102030405060708 WRITE-POD-RECORD'):
            self.assertEqual(self.parse(text), -1, text)


@needs_cc
class Write(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'podwrite', '-DWSMP_HOST', *wsmp_sources(),
                                   ROOT/'firmware/stage0-node/App/wsmp_host.c')._name

    def boot(self, port, kind, contents=None, eeprom=True):
        """A station with one pod on port's channel: its sensor, and its EEPROM holding contents (None: the
        model's power-on bytes, each byte its address, as an EEPROM that never held a record)."""
        lib = fresh_station(self, self.library)
        lib.h_pw_bind.restype = lib.h_pw_crc.restype = lib.h_eeprom_page_writes.restype = lib.h_eeprom_transfers.restype = ctypes.c_uint32
        dev = lib.h_add_on(kind, ADDR[kind], CHANNEL[port])
        if kind == DEVK_SHT45:
            lib.h_sht45_set_serial(dev, SERIAL32, 0)
        if kind == DEVK_LTR390:
            lib.h_ltr390_set(dev, 1000)
        if kind == DEVK_BMP581:
            lib.h_bmp581_set(dev, 101_325 * 64)
        ee = lib.h_add_on(DEVK_EEPROM, 0x50, CHANNEL[port]) if eeprom else None
        if contents is not None:
            lib.h_eeprom_write(ee, 0, contents, len(contents))
        lib.h_init(EPOCH)
        lib.h_vane_mv(3_300)
        lib.h_host_init()
        self.minutes(lib, 2)
        self.assertEqual(lib.h_host_state(port), ACTIVE)
        return lib, dev, ee

    def minutes(self, lib, n):
        for _ in range(n):
            lib.h_host_run(MINUTE)
            lib.h_host_latch(UTC)

    def write(self, lib, port, module_type):
        self.assertEqual(lib.h_pw_start(port, module_type, ctypes.c_uint64(SERIAL), ctypes.c_uint32(UTC)), START_OK)
        self.assertEqual(lib.h_pw_busy(), 1)
        lib.h_host_run(5_000)
        self.assertEqual((lib.h_pw_busy(), lib.h_pw_reports()), (0, 1), "the job did not end with one report")
        return lib.h_pw_outcome()

    def eeprom(self, lib, ee):
        out = (ctypes.c_uint8 * 128)()
        lib.h_eeprom_read_back(ee, out)
        return bytes(out)

    def image(self, lib):
        out = (ctypes.c_uint8 * 128)()
        lib.h_pw_image(out)
        return bytes(out)

    def ident_line(self, lib, i):
        buf = ctypes.create_string_buffer(112)
        lib.h_host_ident_line(i, buf, 112)
        return buf.value

    def test_a_blank_th_pod_gets_its_record_with_the_sht45_bound(self):
        lib, _dev, ee = self.boot(P_AIR_TH, DEVK_SHT45, bytes([0xFF]) * 128)
        self.assertEqual(self.write(lib, P_AIR_TH, 1), PW_OK)
        want = expected(1, SERIAL32)
        self.assertEqual(self.image(lib), want)
        self.assertEqual(self.eeprom(lib, ee), want)
        self.assertEqual(lib.h_pw_bind(), SERIAL32)
        self.assertEqual(lib.h_pw_crc(), int.from_bytes(want[0x7C:], 'big'))
        self.assertEqual(lib.h_eeprom_page_writes(ee), 4)                     # four 32-byte pages
        # the station sees the change at its identity check and admits the pod again under the record's serial
        self.minutes(lib, 4)
        self.assertEqual(lib.h_host_state(P_AIR_TH), ACTIVE)
        crc = b'%08x' % int.from_bytes(want[0x7C:], 'big')
        self.assertIn(b'#ident port=1 type=1 serial=%016x source=record status=applied crc=%s' % (SERIAL, crc),
                      [self.ident_line(lib, i) for i in range(4)])

    def test_a_baro_pod_over_factory_bytes_gets_no_sensor_bind(self):
        lib, _dev, ee = self.boot(P_PRESSURE, DEVK_BMP581)
        self.assertEqual(self.write(lib, P_PRESSURE, 2), PW_OK)
        self.assertEqual(self.eeprom(lib, ee), expected(2))
        self.assertEqual(lib.h_pw_bind(), 0)

    def test_a_uv_pod(self):
        lib, _dev, ee = self.boot(P_UVA, DEVK_LTR390, bytes([0xFF]) * 128)
        self.assertEqual(self.write(lib, P_UVA, 3), PW_OK)
        self.assertEqual(self.eeprom(lib, ee), expected(3))

    def test_a_valid_record_is_never_written_over(self):
        rec = ref.record(module_type=2, bind_kind=0, bind_value=0, part=b'OLD')
        lib, _dev, ee = self.boot(P_PRESSURE, DEVK_BMP581, rec)
        self.assertEqual(self.write(lib, P_PRESSURE, 2), PW_HAS_RECORD)
        self.assertEqual(self.eeprom(lib, ee), rec)
        self.assertEqual(lib.h_eeprom_page_writes(ee), 0)

    def test_write_protect_on_fails_the_verify_and_writes_nothing(self):
        lib, _dev, ee = self.boot(P_UVA, DEVK_LTR390, bytes([0xFF]) * 128)
        lib.h_eeprom_wp(ee, 1)                                                 # JP1's shunt still on
        self.assertEqual(self.write(lib, P_UVA, 3), PW_VERIFY)
        self.assertEqual(self.eeprom(lib, ee), bytes([0xFF]) * 128)

    def test_a_slow_write_cycle_is_polled_until_the_part_answers(self):
        lib, _dev, ee = self.boot(P_UVA, DEVK_LTR390, bytes([0xFF]) * 128)
        lib.h_eeprom_cycle(ee, 40)                                             # longer than a poll or two
        before = lib.h_eeprom_transfers(ee)
        self.assertEqual(self.write(lib, P_UVA, 3), PW_OK)
        self.assertEqual(self.eeprom(lib, ee), expected(3))
        # 1 read, 4 pages, 4 x at least 2 polls (one NACKed, one answered), 1 verify
        self.assertGreaterEqual(lib.h_eeprom_transfers(ee) - before, 1 + 4 + 4 * 2 + 1)

    def test_a_write_cycle_that_never_ends_times_out(self):
        lib, _dev, ee = self.boot(P_UVA, DEVK_LTR390, bytes([0xFF]) * 128)
        lib.h_eeprom_cycle(ee, 60_000)
        self.assertEqual(self.write(lib, P_UVA, 3), PW_TIMEOUT)
        self.assertEqual(lib.h_eeprom_page_writes(ee), 1)                     # it stopped after the first page

    def test_no_eeprom_answers(self):
        lib, _dev, _ee = self.boot(P_UVA, DEVK_LTR390, eeprom=False)
        self.assertEqual(self.write(lib, P_UVA, 3), PW_NO_EEPROM)

    def test_an_sht45_whose_serial_fails_is_not_written(self):
        lib, dev, ee = self.boot(P_AIR_TH, DEVK_SHT45, bytes([0xFF]) * 128)
        lib.h_sht45_set_serial(dev, SERIAL32, 2)                               # its 0x89 NACKed from now on
        self.assertEqual(self.write(lib, P_AIR_TH, 1), PW_NO_SERIAL)
        self.assertEqual(lib.h_eeprom_page_writes(ee), 0)

    def test_the_start_refuses_a_bad_port_type_or_serial_and_a_second_job(self):
        lib, _dev, _ee = self.boot(P_UVA, DEVK_LTR390, bytes([0xFF]) * 128)
        start = lambda port, t, s: lib.h_pw_start(port, t, ctypes.c_uint64(s), ctypes.c_uint32(UTC))   # noqa: E731
        self.assertEqual(start(P_ENCL_TH, 4, SERIAL), START_PORT)
        self.assertEqual(start(P_UVA, 1, SERIAL), START_TYPE)
        for bad in (0x02_0000_0000_0000_01, 0x01_0000_0000_0000_00, 0x01_FFFF_FFFF_FFFF_FF, 0x5753_0000_0103):
            self.assertEqual(start(P_UVA, 3, bad), START_SERIAL, hex(bad))
        self.assertEqual(start(P_UVA, 3, SERIAL), START_OK)
        self.assertEqual(start(P_UVA, 3, SERIAL), START_BUSY)
        lib.h_host_run(5_000)
        self.assertEqual(lib.h_pw_outcome(), PW_OK)


if __name__ == '__main__':
    unittest.main()
