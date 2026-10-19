"""The WSMP core (firmware/common/wsmp.c): blocks, descriptor checks, CRC-32C, quality, budget.

Expected bytes and rules come from docs/module-protocol.md (sections 5, 6, 9 and 11.3), not from
the code under test.
"""
import ctypes
import unittest

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

SHIM = r'''
#include <string.h>
#include "wsmp.h"
int t_pack_snapshot(unsigned token, unsigned boot16, unsigned window, unsigned flags, unsigned tag,
                    const uint32_t *values, const uint16_t *counts, const uint8_t *quality, unsigned n,
                    uint8_t out[WSMP_SNAPSHOT_LEN])
{
  wsmp_snapshot s; memset(&s, 0, sizeof s);
  s.token = (uint16_t)token; s.boot16 = (uint16_t)boot16; s.window_ms = (uint16_t)window;
  s.flags = (uint8_t)flags; s.desc_tag = (uint8_t)tag;
  for (unsigned i = 0; i < n && i < WSMP_MAX_CHANNELS; i++) { s.slot[i].value = values[i]; s.slot[i].count = counts[i]; s.slot[i].quality = quality[i]; }
  wsmp_pack_snapshot(&s, out);
  return 0;
}
int t_snapshot_round_trip(const uint8_t in[WSMP_SNAPSHOT_LEN], uint8_t out[WSMP_SNAPSHOT_LEN])
{
  wsmp_snapshot s;
  int rc = wsmp_unpack_snapshot(in, &s);
  if (rc == WSMP_OK) wsmp_pack_snapshot(&s, out);
  return rc;
}
int t_desc_check_bytes(const uint8_t block[WSMP_DESC_BLOCK_LEN], unsigned n, unsigned type, unsigned schema)
{
  wsmp_desc d[WSMP_MAX_CHANNELS];
  int rc = wsmp_unpack_desc(block, n, d);
  return rc != WSMP_OK ? rc : wsmp_desc_check(d, n, (uint16_t)type, (uint8_t)schema);
}
int t_identity_check(const uint8_t in[WSMP_IDENTITY_LEN]) { wsmp_identity id; return wsmp_unpack_identity(in, &id); }
void t_pack_identity(unsigned type, unsigned schema, unsigned channels, uint64_t serial, uint32_t boot,
                     uint32_t digest, uint8_t out[WSMP_IDENTITY_LEN])
{
  wsmp_identity id; memset(&id, 0, sizeof id);
  id.type = (uint16_t)type; id.schema = (uint8_t)schema; id.channels = (uint8_t)channels; id.serial = serial;
  id.fw_major = 1; id.fw_minor = 2; id.fw_build = 3; id.boot_id = boot; id.caps = 1; id.desc_digest = digest;
  wsmp_pack_identity(&id, out);
}
unsigned t_values_bytes(const uint8_t block[WSMP_DESC_BLOCK_LEN], unsigned n)
{
  wsmp_desc d[WSMP_MAX_CHANNELS];
  return wsmp_unpack_desc(block, n, d) == WSMP_OK ? wsmp_values_bytes(d, n) : 0U;
}
'''

# Descriptor bytes (WSMP section 5, bit 0 = most significant): quantity u16, unit, scale (signed),
# then one byte with (width - 1) in its top 3 bits, signed in the next bit and 4 reserved bits, then kind.
def desc(quantity, unit, scale, width, signed, kind):
    return bytes([quantity >> 8, quantity & 0xFF, unit, scale & 0xFF, (width - 1) << 5 | signed << 4, kind])


AIR_TH = desc(1, 1, -2, 2, 1, 2) + desc(2, 2, -2, 2, 0, 2)              # module type 1, schema 1
WIND = desc(17, 13, 0, 2, 0, 6) + desc(5, 4, -2, 2, 0, 7) + desc(6, 5, -2, 2, 1, 8) + desc(6, 5, -2, 2, 1, 9)


def block(b):
    return (ctypes.c_uint8 * 48)(*(b + bytes(48 - len(b))))


@needs_cc
class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        cls.lib = host_library(cls, 'wsmp', '-Wconversion', '-Wsign-conversion', '-I', fw/'common', fw/'common'/'wsmp.c', files={'shim.c': SHIM})

    def snapshot(self, **kw):
        values = kw.get('values', [])
        n = len(values)
        out = (ctypes.c_uint8 * 72)()
        self.lib.t_pack_snapshot(kw['token'], kw['boot16'], kw['window'], kw['flags'], kw['tag'],
                                 (ctypes.c_uint32 * max(n, 1))(*values), (ctypes.c_uint16 * max(n, 1))(*kw['counts']),
                                 (ctypes.c_uint8 * max(n, 1))(*kw['quality']), n, out)
        return bytes(out)

    def test_snapshot_round_trip_matches_the_wsmp_layout(self):
        raw = self.snapshot(token=0x1234, boot16=7, window=60000, flags=1, tag=0xAB,
                            values=[0xFFFFFF38], counts=[4], quality=[0])
        self.assertEqual(raw[:8].hex(), '12340007ea6001ab')     # token, boot16, window 60000, flags, tag
        self.assertEqual(raw[8:16].hex(), 'ffffff3800040000')   # value, count, quality, reserved
        self.assertEqual(len(raw), 72)
        self.assertEqual(raw[16:], bytes(56))                   # WSMP-S1: unused slots are zero
        back = (ctypes.c_uint8 * 72)()
        self.assertEqual(self.lib.t_snapshot_round_trip((ctypes.c_uint8 * 72)(*raw), back), 0)
        self.assertEqual(bytes(back), raw)

    def test_snapshot_refuses_a_set_reserved_byte(self):
        raw = bytearray(self.snapshot(token=1, boot16=1, window=60000, flags=0, tag=0, values=[5], counts=[1], quality=[0]))
        raw[15] = 1
        self.assertEqual(self.lib.t_snapshot_round_trip((ctypes.c_uint8 * 72)(*raw), (ctypes.c_uint8 * 72)()), -6)

    def test_desc_check_accepts_the_registry_entry(self):
        self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH), 2, 1, 1), 0)
        self.assertEqual(self.lib.t_desc_check_bytes(block(WIND), 4, 6, 1), 0)

    def test_desc_check_refuses_each_wsmp_d7_case(self):
        cases = {
            'unknown quantity': (desc(99, 1, -2, 2, 1, 2) + AIR_TH[6:], -3),
            'unit not canonical': (desc(1, 2, -2, 2, 1, 2) + AIR_TH[6:], -4),
            'scale 7': (desc(1, 1, 7, 2, 1, 2) + AIR_TH[6:], -5),
            'scale -7': (desc(1, 1, -7, 2, 1, 2) + AIR_TH[6:], -5),
            'reserved bit': (AIR_TH[:4] + bytes([AIR_TH[4] | 0x01]) + AIR_TH[5:], -6),
            'channel list differs': (AIR_TH[6:] + AIR_TH[:6], -7),
        }
        for name, (b, rc) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.lib.t_desc_check_bytes(block(b), 2, 1, 1), rc)
        with self.subTest('wrong channel count'):
            self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH[:6]), 1, 1, 1), -7)
        with self.subTest('unknown module type'):
            self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH), 2, 99, 1), -7)
        with self.subTest('wrong schema'):
            self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH), 2, 1, 2), -7)
        with self.subTest('trailing descriptor not zero'):
            self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH + desc(1, 1, 0, 1, 0, 1)), 2, 1, 1), -6)

    def test_desc_check_refuses_widths_kinds_and_counts_out_of_range(self):
        # WSMP section 5: a width of 1 to 4 bytes, a kind of 1 to 10, at most 8 channels.
        for width in range(5, 9):
            with self.subTest(width=width):
                b = desc(1, 1, -2, width, 1, 2) + AIR_TH[6:]
                self.assertEqual(self.lib.t_desc_check_bytes(block(b), 2, 1, 1), -8)       # WSMP_ELEN
        for kind in (0, 11):
            with self.subTest(kind=kind):
                b = desc(1, 1, -2, 2, 1, kind) + AIR_TH[6:]
                self.assertEqual(self.lib.t_desc_check_bytes(block(b), 2, 1, 1), -3)       # WSMP_ECODE
        with self.subTest('9 channels'):
            self.assertEqual(self.lib.t_desc_check_bytes(block(AIR_TH), 9, 1, 1), -8)

    def test_identity_refuses_0_or_9_channels(self):
        out = (ctypes.c_uint8 * 32)()
        self.lib.t_pack_identity(1, 1, 2, ctypes.c_uint64(1), 9, 0, out)
        for channels in (0, 9):
            with self.subTest(channels=channels):
                bad = bytearray(out); bad[7] = channels
                self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*bad)), -8)

    def test_snapshot_refuses_an_undefined_flag(self):
        for bit in (0x08, 0x80):                                    # flags 0-2 are defined (WSMP section 6)
            with self.subTest(bit=bit):
                raw = self.snapshot(token=1, boot16=1, window=60000, flags=bit, tag=0, values=[5], counts=[1], quality=[0])
                self.assertEqual(self.lib.t_snapshot_round_trip((ctypes.c_uint8 * 72)(*raw), (ctypes.c_uint8 * 72)()), -6)

    def test_crc32c_known_vector(self):
        self.lib.wsmp_crc32c.restype = ctypes.c_uint32
        self.assertEqual(self.lib.wsmp_crc32c(b'123456789', 9), 0xE3069283)

    def test_quality_air_table(self):
        self.assertEqual([self.lib.wsmp_quality_air(q) for q in range(6)], [0, 1, 2, 3, 1, 3])
        self.assertEqual(self.lib.wsmp_quality_air(200), 3)        # an unknown code is "missing"

    def test_identity_refuses_bad_magic_and_major(self):
        out = (ctypes.c_uint8 * 32)()
        self.lib.t_pack_identity(1, 1, 2, ctypes.c_uint64(0x0102030405060708), 9, 0xDEADBEEF, out)
        raw = bytes(out)
        self.assertEqual(raw[:4].hex(), '57530100')                  # "WS", version 1.0
        self.assertEqual(raw[4:8].hex(), '00010102')                 # type 1, schema 1, 2 channels
        self.assertEqual(raw[8:16].hex(), '0102030405060708')
        self.assertEqual(raw[20:24].hex(), '00000009')               # boot ID
        self.assertEqual(raw[26:30].hex(), 'deadbeef')               # descriptor digest
        self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*raw)), 0)
        bad = bytearray(raw); bad[0] = 0
        self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*bad)), -1)
        bad = bytearray(raw); bad[2] = 2
        self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*bad)), -2)
        bad = bytearray(raw); bad[2] = 1; bad[3] = 9                 # a higher minor version is accepted (WSMP-V2)
        self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*bad)), 0)
        bad = bytearray(raw); bad[8:16] = bytes(8)                   # serial 0 is not allowed
        self.assertEqual(self.lib.t_identity_check((ctypes.c_uint8 * 32)(*bad)), -8)

    def test_budget_bytes_for_the_bench_station(self):
        # WSMP 11.3: air TH 4, pressure 2, UVA 3, enclosure TH 4, wind 8, rain 2 = 23 bytes of values
        pressure, uva, rain = desc(3, 3, -1, 2, 0, 2), desc(8, 7, 0, 3, 0, 2), desc(7, 6, 0, 2, 0, 6)
        total = sum(self.lib.t_values_bytes(block(b), len(b) // 6) for b in (AIR_TH, pressure, uva, AIR_TH, WIND, rain))
        self.assertEqual(total, 23)
        self.assertEqual(self.lib.wsmp_quality_bytes(11), 3)
        self.assertEqual(self.lib.wsmp_quality_bytes(7), 2)
        self.assertEqual(self.lib.wsmp_quality_bytes(0), 0)

    def test_text_ok_charset(self):
        ok = self.lib.wsmp_text_ok
        self.assertEqual(ok(b'SHT45 v1.2_a-b' + bytes(2), 16), 1)
        self.assertEqual(ok(b'bad;text' + bytes(8), 16), 0)          # WSMP-M1: ';' is not allowed
        self.assertEqual(ok(b'a' + bytes(1) + b'b' + bytes(13), 16), 0)   # text after the padding
        self.assertEqual(ok(bytes(16), 16), 1)


if __name__ == '__main__':
    unittest.main()
