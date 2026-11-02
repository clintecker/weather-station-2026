"""Host/MCU known-answer agreement: the firmware's C frame code (Mbed TLS AES-CCM)
must produce and accept exactly the bytes the Python gateway does."""
import ctypes
import os
import random
import re
import struct
import tempfile
import unittest
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import MBEDTLS, ROOT, host_library, needs_cc, needs_vendor
except ImportError:
    from tests.toolchain import MBEDTLS, ROOT, host_library, needs_cc, needs_vendor
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ws0.fields import encode
from ws0.protocol import (CHARGER_NONE, COUNTER_MAX, DIAG, DIAG_DEFAULTS, DIAG_FIELDS, I16_NONE, KIND_ACK, KIND_DIAG,
                          KIND_NACK, KIND_OBS, STATION_MAX, U16_NONE, Nonces, charger_keys, diag_problems, frame_counter,
                          frame_kind, pack_diag, pack_reply, seal, unpack_diag, unpack_reply, unseal)

# Known-answer test (KAT) vectors of protocol version 6 (byte 0 = 0x61-0x64). The ACK and NACK are
# also compiled into the TX firmware's boot self-test (App/selftest.c), with an observation of its own.
# They were made directly with AESCCM from the designed header and nonce (spec_frame; see
# test_vectors_follow_the_spec), not by ws0/protocol.py. So they check the implementations rather
# than echo them. The version byte is in the AAD, so every tag changes with the version: regenerate
# all of them from spec_frame with `python -m tests.test_frame --kat` (it prints the selftest.c arrays).
SPEC_VERSION = 6                            # power telemetry design section 4, independent of ws0/protocol.py
KAT_KEY = bytes(range(16))
KAT_COUNTER = 0x100000002
KAT_OBS = bytes.fromhex('6100010100000002bd50c6ae3400a778bec2d16fadad588beedf778fa19f9c444ee29d050b4c85b4')
KAT_ACK = bytes.fromhex('62000100000000050e1eb4544766f4e6e0ffdbb3f6d1413d0674082e29b921fddd')
KAT_NACK = bytes.fromhex('6300010000000006849addbf88d9aadd884aa3bb891365753788e8b4e4aa83cefb')
KAT_OBS_PLAIN = struct.pack('>IIIIhHBBH', 17, 42, 100000, 3600, -1234, 4567, 1, 1, 0)  # any 24-byte plaintext


def spec_frame(key, kind, station, counter, plain, version=SPEC_VERSION):
    """docs/protocol-design.md section 3, written out independently of ws0/protocol.py."""
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
    header = bytes([version << 4 | kind]) + station.to_bytes(2, 'big') + counter.to_bytes(5, 'big')
    nonce = bytes([kind]) + station.to_bytes(4, 'big') + counter.to_bytes(8, 'big')
    return header + AESCCM(key, tag_length=8).encrypt(nonce, plain, header)


def selftest_frames():
    """The one source of the boot self-test vectors (App/selftest.c): its observation is the KAT
    record of tests/test_obs.py (T -12.34 C = code 2766, RH 45.67 %, epoch 1, seq 2, UTC 1791991189,
    uptime 300 s, NORMAL, calibration 0); its ACK and NACK are KAT_ACK and KAT_NACK."""
    obs_plain = encode(1, 2, 1791991189, 300, 1, 0, {0: 2766, 1: 4567})
    return {'KAT_OBS': spec_frame(KAT_KEY, KIND_OBS, 1, KAT_COUNTER, obs_plain),
            'KAT_ACK': spec_frame(KAT_KEY, KIND_ACK, 1, 5, pack_reply(17, 42, 1760000000, KAT_COUNTER)),
            'KAT_NACK': spec_frame(KAT_KEY, KIND_NACK, 1, 6, pack_reply(17, 42, 1, KAT_COUNTER))}


def selftest_c_arrays():
    """The selftest.c array definitions of selftest_frames(), in the file's layout."""
    out = []
    for name, frame in selftest_frames().items():
        half = (len(frame) + 1) // 2
        rows = [', '.join(f'0x{b:02x}' for b in frame[i:i + half]) for i in (0, half)]
        out.append(f'static const uint8_t {name}[] = {{\n  {rows[0]},\n  {rows[1]} }};')
    return '\n'.join(out)


# The health report (power telemetry design section 6.1): (offset, struct code, C member). The
# test checks DIAG, pack_diag and ws_diag_pack against this table, written out from the spec.
SPEC_DIAG = ((0, 'I', 'epoch'), (4, 'I', 'uptime'), (8, 'H', 'pending'), (10, 'I', 'lost'), (14, 'H', 'torn'),
             (16, 'H', 'abandoned'), (18, 'H', 'no_ack'), (20, 'H', 'rejects'), (22, 'B', 'reset_cause'),
             (23, 'B', 'link'), (24, 'I', 'build'), (28, 'b', 'rssi'), (29, 'b', 'snr'), (30, 'B', 'crashes'),
             (31, 'B', 'energy'), (32, 'I', 'crash_pc'), (36, 'H', 'boots'), (38, 'H', 'tx_timeouts'),
             (40, 'H', 'i2c_recoveries'), (42, 'H', 'vdda_mv'), (44, 'h', 'monitor_temp'), (46, 'H', 'soc'),
             (48, 'h', 'soc_rate'), (50, 'B', 'charger_status'), (51, 'B', 'fitted'),
             (52, 'H', 'chg_input_mv'), (54, 'h', 'chg_input_ma'), (56, 'H', 'chg_batt_mv'),
             (58, 'h', 'chg_batt_ma'), (60, 'h', 'chg_temp'), (62, 'h', 'pack_temp'))
SPEC_NONE = dict(crash_pc=0, vdda_mv=0xFFFF, monitor_temp=-32768, soc=0xFFFF, soc_rate=-32768, charger_status=0xFF,
                 chg_input_mv=0xFFFF, chg_input_ma=-32768, chg_batt_mv=0xFFFF, chg_batt_ma=-32768, chg_temp=-32768,
                 pack_temp=-32768)
CTYPE = {'I': ctypes.c_uint32, 'H': ctypes.c_uint16, 'h': ctypes.c_int16, 'B': ctypes.c_uint8, 'b': ctypes.c_int8}
C_TYPE_NAME = {ctypes.c_uint32: 'uint32_t', ctypes.c_uint16: 'uint16_t', ctypes.c_int16: 'int16_t',
               ctypes.c_uint8: 'uint8_t', ctypes.c_int8: 'int8_t'}


class DiagT(ctypes.Structure):
    """ws_diag_t in firmware/common/ws_frame.h, member for member (FirmwareTables checks the order)."""
    _fields_ = [(n, ctypes.c_uint32) for n in ('epoch', 'uptime', 'lost', 'build', 'crash_pc')] + \
               [(n, ctypes.c_uint16) for n in ('pending', 'torn', 'abandoned', 'no_ack', 'rejects', 'boots',
                                               'tx_timeouts', 'i2c_recoveries', 'vdda_mv', 'soc', 'chg_input_mv',
                                               'chg_batt_mv')] + \
               [(n, ctypes.c_int16) for n in ('monitor_temp', 'soc_rate', 'chg_input_ma', 'chg_batt_ma', 'chg_temp',
                                              'pack_temp')] + \
               [(n, ctypes.c_uint8) for n in ('reset_cause', 'link', 'crashes', 'energy', 'charger_status',
                                              'fitted')] + \
               [(n, ctypes.c_int8) for n in ('rssi', 'snr')]


def diag_cases(rng):
    """Zero, maximum, minimum, none codes and random values for every member, by C member name."""
    width = {n: (8 * struct.calcsize(code), code.islower()) for _, code, n in SPEC_DIAG}

    def lo(n):
        return -2**(width[n][0] - 1) if width[n][1] else 0

    def hi(n):
        return 2**(width[n][0] - 1) - 1 if width[n][1] else 2**width[n][0] - 1
    cases = [{n: 0 for n in width}, {n: hi(n) for n in width}, {n: lo(n) for n in width},
             {n: SPEC_NONE.get(n, 0) for n in width}, {n: -1 if width[n][1] else 2**(width[n][0] - 1) for n in width}]
    return cases + [{n: rng.randint(lo(n), hi(n)) for n in width} for _ in range(200)]


class Fixed:
    """Allocator stub returning one predetermined counter (test vectors only)."""
    def __init__(self, station, kind, counter):
        self.station, self.kind, self.counter = station, kind, counter

    def next(self):
        return self.counter


# CI sets WS_REQUIRE_VENDOR=1 so a missing vendor/ fails these tests instead of skipping them.
@needs_cc
@needs_vendor
class FrameAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MBEDTLS.exists():
            raise AssertionError(f'WS_REQUIRE_VENDOR=1 but {MBEDTLS} is missing; run tools/fetch-vendor.sh')
        sources = [ROOT/'firmware/common/ws_frame.c'] + [
            MBEDTLS/'library'/f'{name}.c' for name in
            ('aes', 'ccm', 'block_cipher', 'platform_util', 'constant_time')]
        cls.lib = host_library(cls, 'wsframe', '-I', ROOT/'firmware/common', '-I', MBEDTLS/'include',
                               '-DMBEDTLS_CONFIG_FILE="ws_mbedtls_config.h"', *sources)
        u8p = ctypes.POINTER(ctypes.c_uint8)
        cls.lib.ws_key_check.argtypes = [u8p, u8p]
        cls.lib.ws_seal_kind.argtypes = [u8p, ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint64, u8p, ctypes.c_uint32,
                                         u8p, ctypes.c_uint32]
        cls.lib.ws_open_reply.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8)] + \
            [ctypes.POINTER(t) for t in (ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_uint32, ctypes.c_uint64)]

    @staticmethod
    def buf(data, size=None):
        return (ctypes.c_uint8*(size or len(data))).from_buffer_copy(data.ljust(size or len(data), b'\0'))

    def c_seal(self, key, station, counter, plain, kind=KIND_OBS):
        """The C sealer's result: (length or negative error, output buffer)."""
        out = (ctypes.c_uint8*300)()
        n = self.lib.ws_seal_kind(self.buf(key), station, kind, counter, self.buf(plain or b'\0'), len(plain), out, 300)
        return n, bytes(out)

    def c_reply(self, key, station, frame):
        kind = ctypes.c_uint8()
        values = [ctypes.c_uint64(), ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint64()]
        rc = self.lib.ws_open_reply(self.buf(key), station, self.buf(frame), len(frame), ctypes.byref(kind),
                                    *map(ctypes.byref, values))
        return rc, kind.value, [v.value for v in values]

    def test_vectors_follow_the_spec(self):
        self.assertEqual([v[0] for v in (KAT_OBS, KAT_ACK, KAT_NACK)], [0x61, 0x62, 0x63])
        self.assertEqual(spec_frame(KAT_KEY, KIND_OBS, 1, 0x100000002, KAT_OBS_PLAIN), KAT_OBS)
        self.assertEqual(spec_frame(KAT_KEY, KIND_ACK, 1, 5, pack_reply(17, 42, 1760000000, 0x100000002)), KAT_ACK)
        self.assertEqual(spec_frame(KAT_KEY, KIND_NACK, 1, 6, pack_reply(17, 42, 1, 0x100000002)), KAT_NACK)

    def test_known_answer_vectors(self):
        self.assertEqual(seal(KAT_KEY, 1, KIND_OBS, Fixed(1, KIND_OBS, 0x100000002), KAT_OBS_PLAIN), KAT_OBS)
        n, out = self.c_seal(KAT_KEY, 1, 0x100000002, KAT_OBS_PLAIN)
        self.assertEqual(out[:n], KAT_OBS)
        self.assertEqual(seal(KAT_KEY, 1, KIND_ACK, Fixed(1, KIND_ACK, 5), pack_reply(17, 42, 1760000000, 0x100000002)), KAT_ACK)
        self.assertEqual(self.c_reply(KAT_KEY, 1, KAT_ACK), (0, KIND_ACK, [5, 17, 42, 1760000000, 0x100000002]))
        self.assertEqual(seal(KAT_KEY, 1, KIND_NACK, Fixed(1, KIND_ACK, 6), pack_reply(17, 42, 1, 0x100000002)), KAT_NACK)
        self.assertEqual(self.c_reply(KAT_KEY, 1, KAT_NACK), (0, KIND_NACK, [6, 17, 42, 1, 0x100000002]))
        self.assertEqual(len(KAT_ACK), 33)
        self.assertEqual(unpack_reply(unseal(KAT_KEY, 1, KIND_ACK, KAT_ACK)), (17, 42, 1760000000, 0x100000002))

    def test_random_agreement_both_directions(self):
        for _ in range(300):
            key = os.urandom(16)
            station = 1 + int.from_bytes(os.urandom(2), 'big') % STATION_MAX
            counter = 1 + int.from_bytes(os.urandom(5), 'big') % COUNTER_MAX
            plain = os.urandom(24)
            n, out = self.c_seal(key, station, counter, plain)
            frame = out[:n]
            self.assertEqual(frame, seal(key, station, KIND_OBS, Fixed(station, KIND_OBS, counter), plain))
            self.assertEqual(frame, spec_frame(key, KIND_OBS, station, counter, plain))
            self.assertEqual(unseal(key, station, KIND_OBS, frame), plain)
            self.assertEqual(frame_counter(frame), counter)
            reply = pack_reply(*struct.unpack('>III', os.urandom(12)), int.from_bytes(os.urandom(5), 'big'))
            ack = seal(key, station, KIND_ACK, Fixed(station, KIND_ACK, counter), reply)
            rc, kind, values = self.c_reply(key, station, ack)
            self.assertEqual((rc, kind), (0, KIND_ACK))
            self.assertEqual(pack_reply(*values[1:]), reply)

    def test_counter_and_station_limits(self):
        """A value its header field cannot hold is refused on both sides, never truncated (a
        truncated counter would repeat a nonce). The refused C buffer is wiped."""
        plain = bytes(24)
        for station, counter, ok in [(1, COUNTER_MAX, True), (STATION_MAX, 1, True), (1, COUNTER_MAX + 1, False),
                                     (1, 0, False), (STATION_MAX + 1, 1, False), (0, 1, False), (1, 2**64 - 1, False)]:
            n, out = self.c_seal(KAT_KEY, station, counter, plain)
            self.assertEqual(n > 0, ok, (station, counter))
            if ok:
                self.assertEqual(out[:n], seal(KAT_KEY, station, KIND_OBS, Fixed(station, KIND_OBS, counter), plain))
            else:
                self.assertEqual(out, bytes(300))
                with self.assertRaises(ValueError):
                    seal(KAT_KEY, station, KIND_OBS, Fixed(station, KIND_OBS, counter), plain)
        for kind in (0, 5, 15):
            self.assertLess(self.c_seal(KAT_KEY, 1, 1, plain, kind)[0], 0)
            with self.assertRaises(ValueError):
                seal(KAT_KEY, 1, kind, Fixed(1, kind, 1), plain)
        self.assertLess(self.c_seal(KAT_KEY, 1, 1, bytes(240))[0], 0)    # 256-byte frame: over a LoRa payload

    def test_gateway_allocator_stops_at_the_limit(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            nonces = Nonces(Path(tmp)/'n.sqlite3', KAT_KEY, 1, KIND_ACK, create=True)
            with nonces.db:
                nonces.db.execute('UPDATE nonce SET counter=?', (COUNTER_MAX - 1,))
            self.assertEqual(nonces.next(), COUNTER_MAX)
            with self.assertRaisesRegex(ValueError, 'exhausted'):
                nonces.next()
            self.assertEqual(nonces.db.execute('SELECT counter FROM nonce').fetchone()[0], COUNTER_MAX)
            nonces.db.close()

    def test_reply_rejections(self):
        self.assertNotEqual(self.c_reply(KAT_KEY, 1, KAT_ACK[:-1] + bytes([KAT_ACK[-1] ^ 1]))[0], 0)  # tag
        self.assertNotEqual(self.c_reply(KAT_KEY, 2, KAT_ACK)[0], 0)        # wrong station
        self.assertNotEqual(self.c_reply(b'x'*16, 1, KAT_ACK)[0], 0)        # wrong key
        self.assertNotEqual(self.c_reply(KAT_KEY, 1, KAT_OBS)[0], 0)        # observation is not a reply
        self.assertNotEqual(self.c_reply(KAT_KEY, 1, KAT_ACK[:-1])[0], 0)   # length
        for byte0 in (0x42, 0x52, 0x72, 0x67, 0x61, 0x64):                    # other versions, other kinds
            other = bytes([byte0]) + KAT_ACK[1:]
            self.assertNotEqual(self.c_reply(KAT_KEY, 1, other)[0], 0)
        flipped = bytes([0x52]) + KAT_NACK[1:]                               # kind is authenticated
        self.assertNotEqual(self.c_reply(KAT_KEY, 1, flipped)[0], 0)
        from cryptography.exceptions import InvalidTag
        with self.assertRaises(InvalidTag):
            unseal(KAT_KEY, 1, KIND_ACK, KAT_ACK[:-1] + bytes([KAT_ACK[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, KIND_ACK, bytes([0x42]) + KAT_ACK[1:])

    def test_version_6_byte0(self):
        """Byte 0 is 0x61-0x64 on both sides. A version 5 frame, authentic under its own header, is
        another version: neither end opens it, so a stale peer drops frames instead of NACKing them."""
        for kind in (KIND_OBS, KIND_ACK, KIND_NACK, KIND_DIAG):
            plain = bytes(DIAG.size if kind == KIND_DIAG else 17 if kind in (KIND_ACK, KIND_NACK) else 24)
            n, out = self.c_seal(KAT_KEY, 1, 9, plain, kind)
            self.assertEqual(out[0], 0x60 | kind)
            self.assertEqual(out[:n], spec_frame(KAT_KEY, kind, 1, 9, plain))
            self.assertEqual(frame_kind(out[:n]), kind)
            self.assertIsNone(frame_kind(bytes([0x50 | kind]) + out[1:n]))
        reply = pack_reply(17, 42, 1760000000, KAT_COUNTER)
        old_ack = spec_frame(KAT_KEY, KIND_ACK, 1, 5, reply, version=5)
        self.assertEqual(self.c_reply(KAT_KEY, 1, old_ack)[0], -2)          # WS_FRAME_EHEADER
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, KIND_ACK, old_ack)
        old_diag = spec_frame(KAT_KEY, KIND_DIAG, 1, 9, bytes(DIAG.size), version=5)
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, KIND_DIAG, old_diag)
        with self.assertRaisesRegex(ValueError, 'Wrong frame length'):     # a version 5 health report: 32 B
            unseal(KAT_KEY, 1, KIND_DIAG, spec_frame(KAT_KEY, KIND_DIAG, 1, 9, bytes(32)))

    def test_diagnostic_frame_agreement(self):
        plain = pack_diag(epoch=7, uptime=3600, pending=2, lost=51, torn=1, abandoned=3, no_ack=4, rejects=0,
                          reset_cause=5, link=1, build=0x45f43e78, rssi=-61, snr=9, crashes=2, energy=1,
                          crash_pc=0x08001234, boots=3, tx_timeouts=1, i2c_recoveries=2, vdda_mv=3297,
                          monitor_temp=312, soc=200 * 256, soc_rate=-15, charger_status=0x03)
        self.assertEqual(len(plain), 64)
        n, out = self.c_seal(KAT_KEY, 1, 9, plain, KIND_DIAG)
        self.assertEqual(n, 80)
        self.assertEqual(out[:n], seal(KAT_KEY, 1, KIND_DIAG, Fixed(1, KIND_OBS, 9), plain))
        self.assertEqual(out[:n], spec_frame(KAT_KEY, KIND_DIAG, 1, 9, plain))
        self.assertEqual(unseal(KAT_KEY, 1, KIND_DIAG, out[:n]), plain)
        out = out[:n]
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, 1, bytes(out))  # a health report is never accepted as an observation

    def test_diag_plaintext_matches_python(self):
        """The TX health report's bytes (ws_diag_pack, used by send_diag in App/tx_exchange.c) are
        exactly ws0/protocol.py's pack_diag, field by field: zero, maximum, minimum, none codes and
        random values. ws_diag_pack clears bit 7 of byte 51 (the fitted byte) whatever fitted holds."""
        self.lib.ws_diag_pack.argtypes = [ctypes.POINTER(DiagT), ctypes.POINTER(ctypes.c_uint8)]
        self.assertEqual(ctypes.sizeof(DiagT), 64)
        for values in diag_cases(random.Random(4)):
            out = (ctypes.c_uint8*DIAG.size)()
            self.lib.ws_diag_pack(ctypes.byref(DiagT(**values)), out)
            canonical = {**values, 'fitted': values['fitted'] & 0x7F}
            self.assertEqual(bytes(out), pack_diag(**canonical), values)
            self.assertEqual(unpack_diag(bytes(out)), canonical)
            for at, code, name in SPEC_DIAG:                      # each member at its spec offset
                self.assertEqual(struct.unpack_from('>' + code, bytes(out), at)[0], canonical[name], name)

    def test_key_check_value(self):
        out = (ctypes.c_uint8*3)()
        self.assertEqual(self.lib.ws_key_check(self.buf(KAT_KEY), out), 0)
        expected = Cipher(algorithms.AES(KAT_KEY), modes.ECB()).encryptor().update(b'\0'*16)[:3]
        self.assertEqual(bytes(out), expected)
        self.assertEqual(bytes(out).hex(), 'c6a13b')  # FIPS-197 AES-128 vector for this key


class FirmwareTables(unittest.TestCase):
    """Constant tables in the board-only firmware sources (no host build), read back as text."""

    @staticmethod
    def c_array(source, name):
        m = re.search(r'static const uint8_t ' + name + r'\[\] = \{([^}]*)\};', source)
        if not m:
            raise AssertionError(f'{name} not found in selftest.c')
        return bytes(int(v, 16) for v in m.group(1).replace(',', ' ').split())

    def test_selftest_vectors(self):
        """The TX boot self-test (selftest_kat in App/selftest.c) holds its vectors as byte arrays: they must
        be the designed frames, so a typo there cannot make the board refuse to transmit."""
        source = (ROOT/'firmware/stage0-node/App/selftest.c').read_text()
        frames = selftest_frames()
        for name, frame in frames.items():
            self.assertEqual(self.c_array(source, name), frame, name)
            self.assertEqual(frame[0] >> 4, SPEC_VERSION, name)
        self.assertEqual((frames['KAT_ACK'], frames['KAT_NACK']), (KAT_ACK, KAT_NACK))
        self.assertIn(selftest_c_arrays(), source)              # written by --kat, in the file's layout

    def test_diag_mirror_matches_the_header(self):
        """DiagT mirrors ws_diag_t member for member, in the header's order and types."""
        header = (ROOT/'firmware/common/ws_frame.h').read_text()
        body = re.search(r'typedef struct \{(.*?)\} ws_diag_t;', header, re.S)
        self.assertIsNotNone(body)
        members = []
        for ctype, names in re.findall(r'^\s*(u?int\d+_t)\s+([^;]+);', re.sub(r'/\*.*?\*/', '', body.group(1), flags=re.S),
                                       re.M):
            members += [(n.strip(), ctype) for n in names.split(',')]
        self.assertEqual(members, [(n, C_TYPE_NAME[t]) for n, t in DiagT._fields_])
        self.assertEqual({n: CTYPE[c] for _, c, n in SPEC_DIAG}, dict(DiagT._fields_))

    def test_diag_layout_matches_the_spec(self):
        """DIAG, DIAG_FIELDS and the none codes are the spec's table (section 6.1): 64 bytes, byte 51
        (the fitted byte) decoded as B, no gap and no overlap; the WS_FIT_* bits equal protocol.FIT_*."""
        self.assertEqual(DIAG.format, '>IIHIHHHHBBIbbBBIHHHHhHhBBHhHhhh')
        self.assertEqual(DIAG.size, 64)
        self.assertEqual(DIAG_FIELDS, tuple(n for _, _, n in SPEC_DIAG))
        self.assertEqual('>' + ''.join(c for _, c, _ in SPEC_DIAG), DIAG.format)
        for (at, code, _), nxt in zip(SPEC_DIAG, [a for a, _, _ in SPEC_DIAG[1:]] + [64], strict=True):
            self.assertEqual(at + struct.calcsize(code), nxt)
        self.assertEqual((U16_NONE, I16_NONE, CHARGER_NONE), (0xFFFF, -32768, 0xFF))
        self.assertEqual({k: v for k, v in DIAG_DEFAULTS.items() if k in SPEC_NONE}, SPEC_NONE)
        self.assertEqual(set(DIAG_DEFAULTS) - set(SPEC_NONE), {'boots', 'tx_timeouts', 'i2c_recoveries', 'fitted'})
        self.assertFalse(any(DIAG_DEFAULTS[k] for k in ('boots', 'tx_timeouts', 'i2c_recoveries', 'fitted')))
        header = (ROOT/'firmware/common/ws_frame.h').read_text()
        for macro, value in (('WS_DIAG_PLAIN_LEN', '64'), ('WS_FRAME_VERSION', '6'), ('WS_U16_NONE', 'UINT16_MAX'),
                             ('WS_I16_NONE', 'INT16_MIN'), ('WS_CHARGER_NONE', '0xFFU')):
            self.assertRegex(header, rf'#define {macro} {value}\b')
        from ws0 import protocol
        fit = {m.group(1): int(m.group(2), 16) for m in re.finditer(r'#define WS_FIT_(\w+) 0x([0-9A-F]+)U', header)}
        self.assertEqual(fit, {name.removeprefix('FIT_'): getattr(protocol, name) for name in dir(protocol)
                               if name.startswith('FIT_') and name != 'FIT_RESERVED'} | {'DEFINED': 0x7F})

    def test_pack_diag_by_name(self):
        """pack_diag needs the version 5 fields, defaults the version 6 fields to their none codes and
        refuses unknown names; unpack_diag refuses any length but 64."""
        v5 = {n: i + 1 for i, n in enumerate(DIAG_FIELDS[:15])}
        d = unpack_diag(pack_diag(**v5))
        self.assertEqual(d, {**DIAG_DEFAULTS, **v5})
        self.assertEqual(diag_problems(d), ())
        with self.assertRaises(TypeError):
            pack_diag(**{k: v for k, v in v5.items() if k != 'epoch'})
        with self.assertRaises(TypeError):
            pack_diag(**v5, charger_pins=1)
        for size in (0, 32, 63, 65):
            with self.assertRaisesRegex(ValueError, 'Wrong health report length'):
                unpack_diag(bytes(size))

    def test_diag_canonical_rules(self):
        """diag_problems names each broken rule (fitted bit 7, stage 7) and is empty for a canonical
        report; an invalid status byte gives null charger keys, 0xFF never breaks a rule. Active input 3
        is canonical: 'no_input' (design section 6.3)."""
        base = {n: 0 for n in DIAG_FIELDS}
        stage7, input3 = 7 << 3, 3 << 6
        cases = [({}, ()), ({'fitted': 0x7F}, ()), ({'fitted': 0x80}, ('fitted bit 7 set',)),
                 ({'fitted': 0xFF}, ('fitted bit 7 set',)),
                 ({'charger_status': stage7 | 0x07}, ('charger stage 7',)),
                 ({'charger_status': input3 | 0x01}, ()),
                 ({'charger_status': 0xFE}, ('charger stage 7',)),
                 ({'charger_status': 0xFF}, ()), ({'charger_status': 6 << 3 | 2 << 6 | 0x07}, ())]
        for change, problems in cases:
            d = unpack_diag(pack_diag(**{**base, **change}))
            self.assertEqual(diag_problems(d), problems, change)
        nulls = dict.fromkeys(('charger_input_power_ok', 'charger_charging', 'charger_fault', 'charger_stage',
                               'charger_active_input'))
        for status in (0xFF, stage7, 0xFE):
            self.assertEqual(charger_keys(status), nulls, status)
        self.assertEqual(charger_keys(0x01), dict(charger_input_power_ok=True, charger_charging=False,
                                                  charger_fault=False, charger_stage=None, charger_active_input=None))
        self.assertEqual(charger_keys(0x06 | 5 << 3 | 2 << 6),
                         dict(charger_input_power_ok=False, charger_charging=True, charger_fault=True,
                              charger_stage='terminated', charger_active_input='usb_c'))
        self.assertEqual([charger_keys(s << 3)['charger_stage'] for s in range(7)],
                         [None, 'precharge', 'cc', 'cv', 'topoff', 'terminated', 'not_charging'])
        self.assertEqual([charger_keys(i << 6)['charger_active_input'] for i in range(4)],
                         [None, 'solar', 'usb_c', 'no_input'])
        self.assertEqual(charger_keys(input3 | 6 << 3),
                         dict(charger_input_power_ok=False, charger_charging=False, charger_fault=False,
                              charger_stage='not_charging', charger_active_input='no_input'))

    def test_reset_cause_numbering(self):
        """Byte 22 of the health report (DIAG) is the ws_reset_t code (enum order in watchdog.h). Its
        name in watchdog.c's table (designated initializers) must be ws0's RESET_CAUSES at that index."""
        from ws0.protocol import RESET_CAUSES
        header = (ROOT/'firmware/stage0-node/App/watchdog.h').read_text()
        source = (ROOT/'firmware/stage0-node/App/watchdog.c').read_text()
        enum = re.search(r'typedef enum \{([^}]*)\} ws_reset_t;', header)
        table = re.search(r'cause_name\[\] = \{([^}]*)\};', source)
        self.assertIsNotNone(enum)
        self.assertIsNotNone(table)
        codes = {name: i for i, name in enumerate(re.findall(r'WS_RESET_\w+', enum.group(1)))}
        named = {codes[k]: v for k, v in re.findall(r'\[(WS_RESET_\w+)\]\s*=\s*"([^"]*)"', table.group(1))}
        self.assertEqual(tuple(named[i] for i in range(len(RESET_CAUSES))), RESET_CAUSES)
        self.assertEqual(codes['WS_RESET_COUNT'], len(RESET_CAUSES))


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--kat']:       # regenerate the App/selftest.c arrays from selftest_frames()
        print(selftest_c_arrays())
    else:
        unittest.main()
