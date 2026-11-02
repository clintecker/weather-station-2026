"""The descriptor set (docs/module-protocol.md section 11.1, with the identity entry of
docs/firmware-current-design.md section 6.7): the C codec
(firmware/common/wsmp.c) and the gateway's Python twin (ws0/wsmp_set.py), each against bytes written
here from the specification, and against each other.
"""
import ctypes
import random
import struct
import unittest

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

from ws0 import wsmp_set

SHIM = r'''
#include <string.h>
#include "wsmp.h"
/* unpack, then pack: the return code, and the packed bytes in out (*outlen) when accepted */
int t_set_round_trip(const uint8_t *in, unsigned len, uint8_t out[WSMP_SET_MAX_LEN], unsigned *outlen)
{
  wsmp_set s; memset(&s, 0, sizeof s);
  int rc = wsmp_unpack_set(in, len, &s);
  *outlen = rc == WSMP_OK ? wsmp_pack_set(&s, out) : 0U;
  return rc;
}
int t_set_check(const uint8_t *in, unsigned len)
{
  wsmp_set s; memset(&s, 0, sizeof s);
  int rc = wsmp_unpack_set(in, len, &s);
  return rc != WSMP_OK ? rc : wsmp_set_check(&s);
}
/* one field of module i of an accepted set: 0 port, 1 type, 2 schema, 3 channels, 4 id_flags,
   5 record_crc, 6 serial high 32 bits, 7 serial low 32 bits, 8 generation, 9 count, 10 digest */
/* a set built in C with one module of `channels` channels, `modules` times: its packed length */
unsigned t_pack_counts(unsigned modules, unsigned channels)
{
  wsmp_set s; memset(&s, 0, sizeof s);
  uint8_t out[WSMP_SET_MAX_LEN];
  s.count = (uint8_t)modules;
  for (unsigned i = 0; i < modules && i < WSMP_SET_MODULES_MAX; i++)
  { s.m[i].port = (uint8_t)(i + 1U); s.m[i].type = 1; s.m[i].schema = 1; s.m[i].channels = (uint8_t)channels; s.m[i].serial = i + 1U; }
  return wsmp_pack_set(&s, out);
}
long long t_set_field(const uint8_t *in, unsigned len, unsigned i, unsigned f)
{
  wsmp_set s; memset(&s, 0, sizeof s);
  if (wsmp_unpack_set(in, len, &s) != WSMP_OK || i >= WSMP_SET_MODULES_MAX) return -1;
  const wsmp_set_module *m = &s.m[i];
  switch (f)
  {
    case 0: return m->port;
    case 1: return m->type;
    case 2: return m->schema;
    case 3: return m->channels;
    case 4: return m->id_flags;
    case 5: return m->record_crc;
    case 6: return (long long)(m->serial >> 32);
    case 7: return (long long)(m->serial & 0xFFFFFFFFU);
    case 8: return s.generation;
    case 9: return s.count;
    default: return s.digest;
  }
}
'''

CODES = {'WSMP_OK': 0, 'WSMP_ECODE': -3, 'WSMP_EUNIT': -4, 'WSMP_ESCALE': -5, 'WSMP_ERESERVED': -6,
         'WSMP_ETYPE': -7, 'WSMP_ELEN': -8, 'WSMP_EDIGEST': -9}


def desc(quantity, unit, scale, width, signed, kind):
    """One descriptor (WSMP section 5): quantity u16, unit, scale (signed), (width-1)<<5 | signed<<4, kind."""
    return bytes([quantity >> 8, quantity & 0xFF, unit, scale & 0xFF, (width - 1) << 5 | signed << 4, kind])


AIR_TH = desc(1, 1, -2, 2, 1, 2) + desc(2, 2, -2, 2, 0, 2)          # module type 1, schema 1
PRESSURE = desc(3, 3, -2, 2, 0, 2)                                    # module type 2
WIND = desc(17, 13, 0, 2, 0, 6) + desc(5, 4, -2, 2, 0, 7) + desc(6, 5, -2, 2, 1, 8) + desc(6, 5, -2, 2, 1, 9)


def crc32c(b):
    crc = 0xFFFFFFFF
    for x in b:
        crc ^= x
        for _ in range(8):
            crc = crc >> 1 ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def entry(port, mtype, channels, serial, id_flags, record_crc, descs, schema=1):
    """An 18-byte entry written field by field from the spec: port u8, type u16, schema u8, channel
    count u8, serial u64, id_flags u8, record_crc u32; then the descriptors."""
    return (bytes([port]) + mtype.to_bytes(2, 'big') + bytes([schema, channels]) + serial.to_bytes(8, 'big')
            + bytes([id_flags]) + record_crc.to_bytes(4, 'big') + descs)


def header(generation, count, body, reserved=0, digest=None):
    d = crc32c(body) if digest is None else digest
    return generation.to_bytes(2, 'big') + bytes([count, reserved]) + d.to_bytes(4, 'big') + body


RECORD_SERIAL = 0x01_23456789ABCDEF        # namespace 0x01, a programmed record
SENSOR_SERIAL = 0x02_0001_00_0BADCAFE    # namespace 0x02: type 1 in bits 55-40, the SHT4x serial
PORT_SERIAL = 0x575300000000 | 6 << 8 | 6  # namespace 0x00: WSMP_LOCAL_SERIAL(6, 6)


def bench_set(generation=7):
    """Air (record applied), pressure (NO_RECORD: BLANK, sensor serial), wind (a port serial)."""
    body = (entry(1, 1, 2, RECORD_SERIAL, 0x01, 0xDEADBEEF, AIR_TH)
            + entry(2, 2, 1, SENSOR_SERIAL, 0x22, 0, PRESSURE)
            + entry(6, 6, 4, PORT_SERIAL, 0x00, 0, WIND))
    return header(generation, 3, body)


def buf(b):
    return (ctypes.c_uint8 * max(len(b), 1))(*b)


@needs_cc
class DescriptorSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        cls.lib = host_library(cls, 'wsmpset', '-Wconversion', '-Wsign-conversion', '-I', fw/'common',
                               fw/'common'/'wsmp.c', files={'shim.c': SHIM})
        cls.lib.t_set_field.restype = ctypes.c_longlong

    def c_round_trip(self, b):
        out, n = (ctypes.c_uint8 * 296)(), ctypes.c_uint()
        rc = self.lib.t_set_round_trip(buf(b), len(b), out, ctypes.byref(n))
        return rc, bytes(out)[:n.value]

    def c_rc(self, b):
        return self.c_round_trip(b)[0]

    def py_rc(self, b):
        try:
            wsmp_set.unpack(b)
            return 0
        except wsmp_set.SetError as e:
            return CODES[e.code]

    def test_the_bench_set_has_the_section_11_1_layout(self):
        raw = bench_set()
        self.assertEqual(len(raw), 8 + 3 * 18 + 7 * 6)
        self.assertEqual(raw[8:26].hex(), '01' '0001' '01' '02' '0123456789abcdef' '01' 'deadbeef')
        rc, back = self.c_round_trip(raw)
        self.assertEqual(rc, 0)
        self.assertEqual(back, raw)                                  # unpack then pack: the same bytes
        f = lambda i, k: self.lib.t_set_field(buf(raw), len(raw), i, k)   # noqa: E731
        self.assertEqual((f(0, 8), f(0, 9), f(0, 10)), (7, 3, crc32c(raw[8:])))
        self.assertEqual([f(i, 0) for i in range(3)], [1, 2, 6])
        self.assertEqual(f(1, 6) << 32 | f(1, 7), SENSOR_SERIAL)
        self.assertEqual((f(0, 4), f(0, 5), f(1, 4), f(1, 5)), (0x01, 0xDEADBEEF, 0x22, 0))

    def test_the_gateway_reads_serial_source_status_and_record_crc(self):
        s = wsmp_set.unpack(bench_set())
        self.assertEqual(s.generation, 7)
        air, pressure, wind = s.modules
        self.assertEqual((air.serial, air.source, air.status, air.record_crc, air.no_record),
                         (RECORD_SERIAL, 'record', 'applied', 0xDEADBEEF, False))
        self.assertEqual((pressure.source, pressure.status, pressure.no_record, pressure.namespace),
                         ('sensor', 'BLANK', True, 0x02))
        self.assertEqual((wind.port, wind.source, wind.namespace, len(wind.descriptors)), (6, 'port', 0, 4))
        self.assertEqual(wind.descriptors[2], wsmp_set.Descriptor(6, 5, -2, 2, True, 8))

    def test_python_packs_the_bytes_c_packs(self):
        raw = bench_set()
        s = wsmp_set.unpack(raw)
        self.assertEqual(wsmp_set.pack(s.generation, s.modules), raw)

    def test_a_full_set_is_296_bytes_wsmp_e4(self):
        body = b''.join(entry(p, 1, 3, RECORD_SERIAL + p, 0x01, p, AIR_TH + desc(1, 1, -2, 2, 1, 2))
                        for p in range(1, 9))
        raw = header(1, 8, body)
        self.assertEqual(len(raw), 296)
        self.assertEqual(self.c_rc(raw), 0)
        self.assertEqual(self.py_rc(raw), 0)

    def test_an_empty_set_is_valid(self):
        raw = header(3, 0, b'')
        self.assertEqual((self.c_rc(raw), self.py_rc(raw)), (0, 0))

    def test_each_fault_has_its_code_in_c_and_python(self):
        good = bench_set()
        nine = header(1, 9, b''.join(entry(p, 1, 2, p, 0, 0, AIR_TH) for p in range(1, 10)))
        cases = {
            'short header': (good[:7], -8),
            'one byte too long': (good + b'\0', -8),
            'one byte short': (good[:-1], -8),
            'reserved header byte': (good[:3] + b'\1' + good[4:], -6),
            'nine modules': (nine, -8),
            'zero channels': (header(1, 1, entry(1, 1, 0, 1, 0, 0, b'')), -8),
            'nine channels': (header(1, 1, entry(1, 1, 9, 1, 0, 0, AIR_TH * 4 + PRESSURE)), -8),
            '25 channels': (header(1, 4, b''.join(entry(p, 1, 7, p, 0, 0, (AIR_TH * 4)[:42]) for p in (1, 2, 3))
                                   + entry(4, 1, 4, 4, 0, 0, AIR_TH * 2)), -8),
            'zero serial': (header(1, 1, entry(1, 1, 2, 0, 0, 0, AIR_TH)), -8),
            'id_flags bit 2': (header(1, 1, entry(1, 1, 2, 1, 0x04, 0, AIR_TH)), -6),
            'id_flags bit 3': (header(1, 1, entry(1, 1, 2, 1, 0x08, 0, AIR_TH)), -6),
            'undefined status 9': (header(1, 1, entry(1, 1, 2, 1, 0x90, 0, AIR_TH)), -6),
            'reserved descriptor bit': (header(1, 1, entry(1, 1, 2, 1, 0, 0, AIR_TH[:4] + b'\x21' + AIR_TH[5:])), -6),
            'port twice': (header(1, 2, entry(1, 1, 2, 1, 0, 0, AIR_TH) + entry(1, 2, 1, 2, 0, 0, PRESSURE)), -7),
            'ports out of order': (header(1, 2, entry(2, 1, 2, 1, 0, 0, AIR_TH) + entry(1, 2, 1, 2, 0, 0, PRESSURE)), -7),
            'digest': (header(1, 1, entry(1, 1, 2, 1, 0, 0, AIR_TH), digest=0), -9),
            'flipped serial bit': (good[:15] + bytes([good[15] ^ 1]) + good[16:], -9),
        }
        for name, (raw, code) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.c_rc(raw), code)
                self.assertEqual(self.py_rc(raw), code)

    def test_the_registry_check_wsmp_e7(self):
        self.assertEqual(self.lib.t_set_check(buf(bench_set()), len(bench_set())), 0)
        self.assertIsNone(wsmp_set.check(wsmp_set.unpack(bench_set())))
        swapped = header(1, 1, entry(1, 1, 2, 1, 0, 0, AIR_TH[6:] + AIR_TH[:6]))   # humidity first
        self.assertEqual(self.lib.t_set_check(buf(swapped), len(swapped)), -7)
        self.assertIsNotNone(wsmp_set.check(wsmp_set.unpack(swapped)))
        schema2 = header(1, 1, entry(1, 1, 2, 1, 0, 0, AIR_TH, schema=2))
        self.assertEqual(self.lib.t_set_check(buf(schema2), len(schema2)), -7)
        self.assertIsNotNone(wsmp_set.check(wsmp_set.unpack(schema2)))
        bad_unit = header(1, 1, entry(1, 1, 2, 1, 0, 0, desc(1, 2, -2, 2, 1, 2) + AIR_TH[6:]))
        self.assertEqual(self.lib.t_set_check(buf(bad_unit), len(bad_unit)), -4)
        self.assertIsNotNone(wsmp_set.check(wsmp_set.unpack(bad_unit)))

    def test_the_identity_rules_of_e7(self):
        # the serial's namespace (top byte) is its source (id_flags bits 0-1), and v1 has one module per
        # type (firmware-current-design.md, section 6.7): both are WSMP_ETYPE in C and a fault in Python
        cases = {
            'record serial with source port': header(1, 1, entry(1, 1, 2, RECORD_SERIAL, 0x00, 0, AIR_TH)),
            'port serial with source record': header(1, 1, entry(1, 1, 2, PORT_SERIAL, 0x01, 0, AIR_TH)),
            'sensor serial with source adapter': header(1, 1, entry(1, 1, 2, SENSOR_SERIAL, 0x03, 0, AIR_TH)),
            'type twice': header(1, 2, entry(1, 1, 2, RECORD_SERIAL, 0x01, 0, AIR_TH)
                                 + entry(4, 1, 2, RECORD_SERIAL + 1, 0x01, 0, AIR_TH)),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                self.assertEqual(self.c_rc(raw), 0)                              # it unpacks: a check fault
                self.assertEqual(self.lib.t_set_check(buf(raw), len(raw)), -7)
                self.assertIsNotNone(wsmp_set.check(wsmp_set.unpack(raw)))

    def test_pack_refuses_counts_it_could_not_write(self):
        # Power of Ten rule 5: a caller's set outside the counts packs nothing
        self.assertEqual(self.lib.t_pack_counts(1, 2), 8 + 18 + 12)
        self.assertEqual(self.lib.t_pack_counts(3, 8), 8 + 3 * 18 + 24 * 6)      # 24 channels: the limit
        self.assertEqual(self.lib.t_pack_counts(4, 7), 0)                        # 28 channels
        self.assertEqual(self.lib.t_pack_counts(1, 9), 0)
        self.assertEqual(self.lib.t_pack_counts(1, 0), 0)
        self.assertEqual(self.lib.t_pack_counts(9, 1), 0)

    def test_c_and_python_agree_on_mutated_sets(self):
        # differential: random byte flips, truncations and extensions of valid sets with the digest
        # recomputed half the time, so the checks after the digest's are reached too
        rng = random.Random(20261023)
        seeds = [bench_set(), header(1, 1, entry(3, 3, 1, 9, 0x12, 0, desc(8, 7, -1, 2, 0, 2)))]
        for _ in range(3000):
            raw = bytearray(rng.choice(seeds))
            for _ in range(rng.randint(1, 3)):
                op = rng.random()
                if op < 0.7 and raw:
                    raw[rng.randrange(len(raw))] ^= 1 << rng.randrange(8)
                elif op < 0.85 and len(raw) > 1:
                    del raw[rng.randrange(len(raw)):]
                else:
                    raw += bytes([rng.randrange(256)])
            if rng.random() < 0.5 and len(raw) >= 8:
                struct.pack_into('>I', raw, 4, crc32c(bytes(raw[8:])))
            raw = bytes(raw)
            c, p = self.c_rc(raw), self.py_rc(raw)
            self.assertEqual(c, p, raw.hex())
            if c == 0:
                self.assertEqual(self.c_round_trip(raw)[1], raw)


if __name__ == '__main__':
    unittest.main()
