"""Host/MCU known-answer agreement: the firmware's C frame code (Mbed TLS AES-CCM)
must produce and accept exactly the bytes the Python gateway does."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import ctypes
import os
import struct
import subprocess
import tempfile
import unittest
try:
    from toolchain import needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import needs_cc    # python -m unittest tests.<module>
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ws0.protocol import (COUNTER_MAX, KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS, STATION_MAX, Nonces, frame_counter,
                          pack_reply, seal, unpack_reply, unseal)

ROOT = Path(__file__).resolve().parent.parent
MBEDTLS = ROOT/'vendor/STM32CubeWL/Middlewares/Third_Party/mbed-crypto'
# Same vectors are compiled into the TX firmware's boot self-test (App/app_tx.c). They were made
# directly with AESCCM from the spec's header and nonce (see test_vectors_follow_the_spec), not by
# ws0/protocol.py, so they check the implementations rather than echo them.
KAT_KEY = bytes(range(16))
KAT_OBS = bytes.fromhex('5100010100000002bd50c6ae3400a778bec2d16fadad588beedf778fa19f9c44aa67cd92b9f30417')
KAT_ACK = bytes.fromhex('52000100000000050e1eb4544766f4e6e0ffdbb3f6d1413d06f6369500199b8fe2')
KAT_NACK = bytes.fromhex('5300010000000006849addbf88d9aadd884aa3bb89136575374521c5e416a1d0c9')
KAT_OBS_PLAIN = struct.pack('>IIIIhHBBH', 17, 42, 100000, 3600, -1234, 4567, 1, 1, 0)  # any 24-byte plaintext


def spec_frame(key, kind, station, counter, plain):
    """docs/protocol-draft5-design.md section 3, written out independently of ws0/protocol.py."""
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
    header = bytes([0x50 | kind]) + station.to_bytes(2, 'big') + counter.to_bytes(5, 'big')
    nonce = bytes([kind]) + station.to_bytes(4, 'big') + counter.to_bytes(8, 'big')
    return header + AESCCM(key, tag_length=8).encrypt(nonce, plain, header)


class Fixed:
    """Allocator stub returning one predetermined counter (test vectors only)."""
    def __init__(self, station, kind, counter):
        self.station, self.kind, self.counter = station, kind, counter

    def next(self):
        return self.counter


# CI sets WS_REQUIRE_VENDOR=1 so a missing vendor/ fails these tests instead of skipping them.
REQUIRE_VENDOR = os.environ.get('WS_REQUIRE_VENDOR') == '1'


@needs_cc
@unittest.skipUnless(MBEDTLS.exists() or REQUIRE_VENDOR, 'run tools/fetch-vendor.sh to fetch pinned Mbed TLS')
class FrameAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MBEDTLS.exists():
            raise AssertionError(f'WS_REQUIRE_VENDOR=1 but {MBEDTLS} is missing; run tools/fetch-vendor.sh')
        # Windows cannot delete a library ctypes still has loaded; leave it for the OS temp cleanup.
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        lib = Path(cls.tmp.name)/'wsframe.so'
        sources = [ROOT/'firmware/common/ws_frame.c'] + [
            MBEDTLS/'library'/f'{name}.c' for name in
            ('aes', 'ccm', 'block_cipher', 'platform_util', 'constant_time')]
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-I', str(ROOT/'firmware/common'), '-I', str(MBEDTLS/'include'),
                        '-DMBEDTLS_CONFIG_FILE="ws_mbedtls_config.h"',
                        *map(str, sources), '-o', str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        u8p = ctypes.POINTER(ctypes.c_uint8)
        cls.lib.ws_key_check.argtypes = [u8p, u8p]
        cls.lib.ws_seal_kind.argtypes = [u8p, ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint64, u8p, ctypes.c_uint32,
                                         u8p, ctypes.c_uint32]
        cls.lib.ws_open_reply.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8)] + \
            [ctypes.POINTER(t) for t in (ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_uint32, ctypes.c_uint64)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

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
        for byte0 in (0x42, 0x62, 0x57, 0x51, 0x54):                          # other versions, other kinds
            other = bytes([byte0]) + KAT_ACK[1:]
            self.assertNotEqual(self.c_reply(KAT_KEY, 1, other)[0], 0)
        flipped = bytes([0x52]) + KAT_NACK[1:]                               # kind is authenticated
        self.assertNotEqual(self.c_reply(KAT_KEY, 1, flipped)[0], 0)
        from cryptography.exceptions import InvalidTag
        with self.assertRaises(InvalidTag):
            unseal(KAT_KEY, 1, KIND_ACK, KAT_ACK[:-1] + bytes([KAT_ACK[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, KIND_ACK, bytes([0x42]) + KAT_ACK[1:])

    def test_diagnostic_frame_agreement(self):
        from ws0.protocol import DIAG
        plain = DIAG.pack(7, 3600, 2, 51, 1, 3, 4, 0, 5, 1, 0x45f43e78, -61, 9, 2, 1)
        self.assertEqual(len(plain), 32)
        n, out = self.c_seal(KAT_KEY, 1, 9, plain, KIND_DIAG)
        self.assertEqual(out[:n], seal(KAT_KEY, 1, KIND_DIAG, Fixed(1, KIND_OBS, 9), plain))
        self.assertEqual(unseal(KAT_KEY, 1, KIND_DIAG, out[:n]), plain)
        out = out[:n]
        with self.assertRaisesRegex(ValueError, 'Unexpected frame header'):
            unseal(KAT_KEY, 1, 1, bytes(out))  # a health report is never accepted as an observation

    def test_key_check_value(self):
        out = (ctypes.c_uint8*3)()
        self.assertEqual(self.lib.ws_key_check(self.buf(KAT_KEY), out), 0)
        expected = Cipher(algorithms.AES(KAT_KEY), modes.ECB()).encryptor().update(b'\0'*16)[:3]
        self.assertEqual(bytes(out), expected)
        self.assertEqual(bytes(out).hex(), 'c6a13b')  # FIPS-197 AES-128 vector for this key


if __name__ == '__main__':
    unittest.main()
