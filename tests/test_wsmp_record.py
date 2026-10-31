"""The module record v1.0 and the admission verdict (firmware/common/wsmp.c, wsmp_ident.c).

Expected bytes, statuses and verdicts come from the sensor-module-ports design
(docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md sections 6.7 and 6.9) through the
independent reference tests/wsmp_record_ref.py, not from the code under test.
"""
import ctypes
import unittest

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
    import wsmp_record_ref as ref
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>
    from tests import wsmp_record_ref as ref

SHIM = r'''
#include <string.h>
#include "wsmp.h"
#include "wsmp_cal.h"
#include "wsmp_ident.h"
int t_parse(const uint8_t in[WSMP_RECORD_LEN], uint8_t back[WSMP_RECORD_LEN], uint64_t *serial, uint32_t *crc)
{
  wsmp_record r;
  int st = wsmp_record_parse(in, &r);
  if (st == WSMP_REC_APPLIED) { wsmp_record_pack(&r, back); *serial = r.serial; *crc = r.crc; }
  return st;
}
void t_pack(unsigned type, uint64_t serial, unsigned bind_kind, uint32_t bind_value, unsigned hw, uint32_t programmed,
            const uint8_t part[WSMP_RECORD_PART_LEN], const int64_t *cal, unsigned ncal, uint8_t out[WSMP_RECORD_LEN])
{
  wsmp_record r; memset(&r, 0, sizeof r);
  r.type = (uint16_t)type; r.serial = serial; r.bind_kind = (uint8_t)bind_kind; r.bind_value = bind_value;
  r.hw_rev = (uint8_t)hw; r.programmed = programmed; memcpy(r.part, part, WSMP_RECORD_PART_LEN);
  for (unsigned i = 0; i < ncal && i < WSMP_RECORD_CAL_N; i++)
    r.cal[i] = (wsmp_cal_entry){ .quantity = (uint16_t)cal[5 * i], .kind = (uint8_t)cal[5 * i + 1],
                                 .revision = (uint16_t)cal[5 * i + 2], .offset = (int32_t)cal[5 * i + 3],
                                 .gain = (uint32_t)cal[5 * i + 4] };
  wsmp_record_pack(&r, out);
}
void t_verdict(unsigned port, unsigned probed_type, int read_ok, const uint8_t rec[WSMP_RECORD_LEN], int has_ss, uint32_t ss,
              const uint8_t *hp, const uint16_t *ht, const uint64_t *hs, const uint8_t *hh, unsigned n,
              uint64_t *serial, uint32_t *crc, uint8_t res[5])
{
  wsmp_port_held held[8];
  for (unsigned i = 0; i < n && i < 8; i++) held[i] = (wsmp_port_held){ .port = hp[i], .type = ht[i], .serial = hs[i], .holding = hh[i] };
  const wsmp_observed o = { .port = (uint8_t)port, .probed_type = (uint16_t)probed_type, .read_ok = (uint8_t)read_ok,
                            .record = rec, .has_sensor_serial = (uint8_t)has_ss, .sensor_serial = ss };
  wsmp_verdict v;
  wsmp_identify(&o, held, n, &v);
  *serial = v.serial; *crc = v.record_crc;
  res[0] = v.verdict; res[1] = v.holder_port; res[2] = v.status; res[3] = v.source; res[4] = v.id_flags;
}
'''

VALID = ref.record()                                       # type 1, serial 0x01A1B2C3D4E5F607, bind 0x12345678
SHT_SERIAL = 0x1234_5678
ADMIT, TYPE_CONFLICT, DUP_SERIAL, DUP_TYPE = range(4)


def buf(b):
    return (ctypes.c_uint8 * len(b))(*b)


def broken(record, offset, value):
    """record with byte offset set to value, the CRC sealed again (so only the structural check fails)."""
    b = bytearray(record)
    b[offset] = value
    return ref.seal(b)


@needs_cc
class Record(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        cls.lib = host_library(cls, 'wsmp_record', '-Wconversion', '-Wsign-conversion', '-I', fw/'common',
                               fw/'common'/'wsmp.c', fw/'common'/'wsmp_cal.c', fw/'common'/'wsmp_ident.c', files={'shim.c': SHIM})

    def parse(self, record):
        back, serial, crc = (ctypes.c_uint8 * 128)(), ctypes.c_uint64(), ctypes.c_uint32()
        st = self.lib.t_parse(buf(record), back, ctypes.byref(serial), ctypes.byref(crc))
        return st, bytes(back), serial.value, crc.value

    def test_crc32c_check_value_and_the_reference(self):
        self.lib.wsmp_crc32c.restype = ctypes.c_uint32
        self.assertEqual(self.lib.wsmp_crc32c(b'123456789', 9), 0xE3069283)
        self.assertEqual(ref.crc32c(b'123456789'), 0xE3069283)
        self.assertEqual(self.lib.wsmp_crc32c(buf(VALID), 0x7C), ref.crc32c(VALID[:0x7C]))

    def test_golden_valid_record(self):
        # The layout of section 6.9, big-endian; the CRC pinned so that a layout change shows here.
        self.assertEqual(VALID[:0x20].hex(), '57534d52' '01' '00' '0080' '0001' '02' '00' '01a1b2c3d4e5f607'
                                             '01' '000000' '12345678' '6acfc000')
        self.assertEqual(VALID[0x20:0x30], b'ADA-SHT45-M1\0\0\0\0')
        self.assertEqual(VALID[0x30:0x7C], bytes(0x4C))
        self.assertEqual(VALID[0x7C:].hex(), f'{ref.crc32c(VALID[:0x7C]):08x}')
        st, back, serial, crc = self.parse(VALID)
        self.assertEqual((st, serial, crc), (ref.APPLIED, 0x01A1B2C3D4E5F607, int.from_bytes(VALID[0x7C:], 'big')))
        self.assertEqual(back, VALID)

    def test_encoder_writes_the_reference_bytes(self):
        cal = [(1, 0, 3, -150, 1_010_000), (2, 2, 1, 250, 950_000), (8, 0, 0, 0, 1)]
        want = ref.record(cal=cal)
        flat = (ctypes.c_int64 * 15)(*[x for e in cal for x in e])
        out = (ctypes.c_uint8 * 128)()
        self.lib.t_pack(1, ctypes.c_uint64(0x01A1B2C3D4E5F607), 1, SHT_SERIAL, 2, 1_792_000_000,
                        buf(b'ADA-SHT45-M1'.ljust(16, b'\0')), flat, 3, out)
        self.assertEqual(bytes(out), want)
        self.assertEqual(want[0x40:0x50].hex(), '0001' '00' '00' '0003' '0000' 'ffffff6a' '000f6950')
        st, back, _, _ = self.parse(want)
        self.assertEqual((st, back), (ref.APPLIED, want))

    def test_read_failures_in_check_order(self):
        cases = {
            'blank 0xFF': (b'\xff' * 128, ref.BLANK),
            'all zero': (bytes(128), ref.NO_MAGIC),
            'bad magic': (broken(VALID, 3, ord('X')), ref.NO_MAGIC),
            'magic, then 0xFF': (b'WSMR' + b'\xff' * 124, ref.VERSION),
            'major 0': (broken(VALID, 4, 0), ref.VERSION),
            'major 2': (broken(VALID, 4, 2), ref.VERSION),
            'length 127': (ref.record(length=127), ref.MALFORMED),
            'length 256': (ref.record(length=256), ref.MALFORMED),
            'length checked before the CRC': (VALID[:7] + b'\x81' + VALID[8:], ref.MALFORMED),
            'bad CRC': (VALID[:0x7C] + bytes(4), ref.CRC),
            'one bit flipped': (VALID[:40] + bytes([VALID[40] ^ 1]) + VALID[41:], ref.CRC),
        }
        for name, (record, status) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.parse(record)[0], status)

    def test_each_structural_failure_is_malformed(self):
        M = ref.MALFORMED
        cases = {
            'serial namespace 0x02': ref.record(serial=0x02_A1B2C3D4E5F607),
            'serial namespace 0x00': ref.record(serial=0x00_A1B2C3D4E5F607),
            'serial value 0': ref.record(serial=0x01 << 56),
            'serial value all ones': ref.record(serial=0x01FF_FFFF_FFFF_FFFF),
            'module type 0': ref.record(module_type=0, bind_kind=0, bind_value=0),
            'module type 10 (not in the registry)': ref.record(module_type=10, bind_kind=0, bind_value=0),
            'type 1 without a sensor bind': ref.record(bind_kind=0, bind_value=0),
            'bind kind 2 (unknown)': ref.record(bind_kind=2),
            'bind value with kind 0': ref.record(module_type=3, bind_kind=0, bind_value=5),
            'kind 1 on type 2 (the BMP581 has no readable serial)': ref.record(module_type=2, bind_kind=1),
            'kind 1 on type 3 (the LTR390 has no readable serial)': ref.record(module_type=3, bind_kind=1, part=b'ADA-LTR390'),
            'part number character': ref.record(part=b'ADA;SHT45'),
            'part number after its padding': ref.record(part=b'ADA\0SHT45'),
            'flags byte': ref.record(flags=1),
            'reserved 0x15': broken(VALID, 0x15, 1),
            'reserved 0x17': broken(VALID, 0x17, 0x80),
            'reserved 0x30': broken(VALID, 0x30, 1),
            'reserved 0x3F': broken(VALID, 0x3F, 1),
            'reserved 0x70': broken(VALID, 0x70, 1),
            'reserved 0x7B': broken(VALID, 0x7B, 1),
            'entry reserved +3': broken(ref.record(cal=[(1, 2, 1, 5, 1_000_000)]), 0x43, 1),
            'entry reserved +6': broken(ref.record(cal=[(1, 2, 1, 5, 1_000_000)]), 0x46, 1),
            'entry reserved +7 of entry 3': broken(ref.record(cal=[(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (1, 2, 1, 5, 1_000_000)]), 0x67, 1),
            'reserved byte in an otherwise all-zero entry': broken(VALID, 0x46, 1),
            'entry kind 11 (unknown)': ref.record(cal=[(1, 11, 1, 5, 1_000_000)]),
        }
        for name, record in cases.items():
            with self.subTest(name):
                self.assertEqual(self.parse(record)[0], M)

    def test_accepted_edges(self):
        cases = {
            'type 3 with kind 0': ref.record(module_type=3, bind_kind=0, bind_value=0, part=b'ADA-LTR390'),
            'type 2 with kind 0': ref.record(module_type=2, bind_kind=0, bind_value=0),
            'type 8 (battery) with kind 0': ref.record(module_type=8, bind_kind=0, bind_value=0, part=b'INA228'),
            'type 9 (power rails) with kind 0': ref.record(module_type=9, bind_kind=0, bind_value=0, part=b'INA228'),
            'serial value 1': ref.record(serial=0x0100_0000_0000_0001),
            'serial value all ones but one': ref.record(serial=0x01FF_FFFF_FFFF_FFFE),
            'part number of exactly 16 characters': ref.record(part=b'ABCDEFGHIJKLMNOP'),
            'empty part number (the station accepts it; the fixture does not)': ref.record(part=b''),
            'minor 1 with reserved bytes and flags set': broken(ref.record(minor=1, flags=0x80), 0x30, 7),
            'an all-zero entry between two used ones': ref.record(cal=[(1, 2, 1, 5, 1_000_000), (0, 0, 0, 0, 0),
                                                                       (2, 0, 1, 5, 1_000_000)]),
            'entry kind 0 and kind 10': ref.record(cal=[(1, 0, 1, 5, 1_000_000), (2, 10, 1, 5, 1_000_000)]),
        }
        for name, record in cases.items():
            with self.subTest(name):
                self.assertEqual(self.parse(record)[0], ref.APPLIED)

    def test_sensor_bind_against_the_reference(self):
        # Kind 1 iff the type's part has a readable sensor serial (type 1 in v1), at any value and minor.
        for t in ref.CHANNELS:
            for kind, value in ((0, 0), (0, 1), (1, 0), (1, SHT_SERIAL), (2, 0)):
                for minor in (0, 1):
                    with self.subTest(type=t, kind=kind, value=value, minor=minor):
                        want = ref.APPLIED if ref.bind_ok(t, kind, value) else ref.MALFORMED
                        record = ref.record(module_type=t, bind_kind=kind, bind_value=value, minor=minor)
                        self.assertEqual(self.parse(record)[0], want)

    def test_minor_1_round_trip_keeps_the_known_fields(self):
        st, back, serial, _ = self.parse(broken(ref.record(minor=1), 0x70, 9))
        self.assertEqual(st, ref.APPLIED)
        self.assertEqual((back[5], back[0x70]), (1, 0))             # the minor kept; an unknown reserved byte is not
        self.assertEqual(self.parse(back)[0], ref.APPLIED)


@needs_cc
class Verdict(unittest.TestCase):
    """The ordered verdict table of section 6.7 (steps 1-6)."""
    @classmethod
    def setUpClass(cls):
        Record.setUpClass.__func__(cls)

    def verdict(self, record=VALID, port=2, probed=1, read_ok=True, ss=SHT_SERIAL, held=()):
        n = len(held)
        hp = (ctypes.c_uint8 * max(n, 1))(*[h[0] for h in held])
        ht = (ctypes.c_uint16 * max(n, 1))(*[h[1] for h in held])
        hs = (ctypes.c_uint64 * max(n, 1))(*[h[2] for h in held])
        hh = (ctypes.c_uint8 * max(n, 1))(*[h[3] for h in held])
        serial, crc, res = ctypes.c_uint64(), ctypes.c_uint32(), (ctypes.c_uint8 * 5)()
        rec = buf(record) if read_ok else None
        self.lib.t_verdict(port, probed, int(read_ok), rec, int(ss is not None), ss or 0, hp, ht, hs, hh, n,
                           ctypes.byref(serial), ctypes.byref(crc), res)
        v, holder, status, source, flags = res
        self.assertEqual(flags, source | status << 4, 'id_flags: bits 0-1 the source, 4-7 the record status')
        return {'verdict': v, 'holder': holder, 'status': status, 'source': source, 'serial': serial.value, 'crc': crc.value}

    def expect(self, got, **want):
        self.assertEqual({k: got[k] for k in want}, want)

    def test_admit_with_an_applied_record(self):
        crc = int.from_bytes(VALID[0x7C:], 'big')
        self.expect(self.verdict(), verdict=ADMIT, status=ref.APPLIED, source=ref.SRC_RECORD, serial=0x01A1B2C3D4E5F607, crc=crc)

    def test_step_1_read_failure_takes_the_sensor_or_port_serial(self):
        self.expect(self.verdict(read_ok=False), verdict=ADMIT, status=ref.READ, source=ref.SRC_SENSOR,
                    serial=ref.sensor_serial(1, SHT_SERIAL), crc=0)
        self.assertEqual(ref.sensor_serial(1, SHT_SERIAL), 0x0200_0100_1234_5678)
        self.expect(self.verdict(read_ok=False, probed=3, ss=None, port=4), verdict=ADMIT, status=ref.READ,
                    source=ref.SRC_PORT, serial=ref.port_serial(4, 3), crc=0)

    def test_step_2_content_failures(self):
        for record, status in ((b'\xff' * 128, ref.BLANK), (bytes(128), ref.NO_MAGIC), (broken(VALID, 4, 2), ref.VERSION),
                               (ref.record(length=64), ref.MALFORMED), (VALID[:0x7C] + bytes(4), ref.CRC)):
            with self.subTest(status=status):
                self.expect(self.verdict(record), verdict=ADMIT, status=status, source=ref.SRC_SENSOR,
                            serial=ref.sensor_serial(1, SHT_SERIAL), crc=0)
        self.expect(self.verdict(b'\xff' * 128, probed=2, ss=None, port=3), status=ref.BLANK, source=ref.SRC_PORT,
                    serial=ref.port_serial(3, 2))

    def test_step_3a_type_conflict_stops(self):
        uva = ref.record(module_type=3, bind_kind=0, bind_value=0)
        got = self.verdict(uva, probed=1, held=[(5, 1, 0, 1)])   # before the duplicate checks
        self.expect(got, verdict=TYPE_CONFLICT, crc=0)

    def test_step_3b_sensor_changed(self):
        got = self.verdict(ss=0xCAFE_F00D)
        self.expect(got, verdict=ADMIT, status=ref.SENSOR_CHANGED, source=ref.SRC_SENSOR,
                    serial=ref.sensor_serial(1, 0xCAFE_F00D), crc=0)

    def test_step_3c_cal_rejected_keeps_the_record_serial_with_crc_0(self):
        bad = ref.record(cal=[(1, 0, 1, 201, 1_000_000)])           # offset beyond +-200 (2 degC)
        self.expect(self.verdict(bad), verdict=ADMIT, status=ref.CAL_REJECTED, source=ref.SRC_RECORD,
                    serial=0x01A1B2C3D4E5F607, crc=0)

    def test_step_3b_before_3c(self):
        bad = ref.record(cal=[(1, 0, 1, 201, 1_000_000)])
        self.expect(self.verdict(bad, ss=7), status=ref.SENSOR_CHANGED, source=ref.SRC_SENSOR)

    def test_step_4_duplicate_serial_needs_the_holder_check(self):
        held = [(1, 1, 0x01A1B2C3D4E5F607, 1)]                    # a clone of the same module type on port 1
        self.expect(self.verdict(held=held), verdict=DUP_SERIAL, holder=1, status=ref.APPLIED, source=ref.SRC_RECORD)

    def test_step_4_clone_wins_over_type_duplicate(self):
        # Port 1 holds the same type with another serial, port 5 the same serial (a clone): the serial
        # step (4) comes first, whatever the port order.
        held = [(1, 1, 0x01_0000_0000_0000_99, 1), (5, 2, 0x01A1B2C3D4E5F607, 1)]
        self.expect(self.verdict(held=held), verdict=DUP_SERIAL, holder=5)

    def test_step_4_with_a_sensor_serial(self):
        held = [(6, 1, ref.sensor_serial(1, SHT_SERIAL), 1)]
        self.expect(self.verdict(read_ok=False, held=held), verdict=DUP_SERIAL, holder=6, status=ref.READ)

    def test_step_5_duplicate_type(self):
        held = [(3, 3, 0x01_0000_0000_0000_33, 1), (7, 1, 0x01_0000_0000_0000_77, 1)]
        self.expect(self.verdict(held=held), verdict=DUP_TYPE, holder=7, status=ref.APPLIED)

    def test_cal_rejected_still_meets_the_duplicate_steps(self):
        bad = ref.record(cal=[(9, 0, 1, 0, 1_000_000)])
        self.expect(self.verdict(bad, held=[(1, 1, 0x01A1B2C3D4E5F607, 1)]), verdict=DUP_SERIAL, status=ref.CAL_REJECTED, crc=0)

    def test_kind_1_on_a_uva_record_is_no_record_malformed(self):
        uva = ref.record(module_type=3, bind_kind=1, bind_value=SHT_SERIAL)
        self.expect(self.verdict(uva, probed=3, ss=None, port=5), verdict=ADMIT, status=ref.MALFORMED,
                    source=ref.SRC_PORT, serial=ref.port_serial(5, 3), crc=0)

    def test_revision_0_entry_is_cal_rejected_with_crc_0(self):
        bad = ref.record(cal=[(1, 2, 0, 5, 1_000_000)])
        self.expect(self.verdict(bad), verdict=ADMIT, status=ref.CAL_REJECTED, source=ref.SRC_RECORD,
                    serial=0x01A1B2C3D4E5F607, crc=0)

    def test_only_holding_modules_on_other_ports_count(self):
        held = [(2, 1, 0x01A1B2C3D4E5F607, 1),                      # this port itself
                (4, 1, 0x01A1B2C3D4E5F607, 0)]                      # quarantined or refused: holds nothing
        self.expect(self.verdict(held=held), verdict=ADMIT)


if __name__ == '__main__':
    unittest.main()
