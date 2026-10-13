"""Host/MCU known-answer agreement: the firmware's C frame code (Mbed TLS AES-CCM)
must produce and accept exactly the bytes the Python gateway does."""
import ctypes
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ws0.protocol import ACK, OBS, RH_INVALID, TEMP_INVALID, decode_observation, frame_counter, seal, unseal

ROOT = Path(__file__).resolve().parent.parent
MBEDTLS = ROOT/'vendor/STM32CubeWL/Middlewares/Third_Party/mbed-crypto'
# Same vectors are compiled into the TX firmware's boot self-test (App/app_tx.c).
KAT_KEY = bytes(range(16))
KAT_OBS = bytes.fromhex('57530401000000010000000100000002bd50c6ae3400a778bec2d16f'
                        'adad588beedf778fa19f9c44d0b48401107c5419c40efafe6b0d84b7')
KAT_ACK = bytes.fromhex('575304020000000100000000000000050e1eb4544766f4e68818a3b3'
                        '9f36393d04a393ebcf0d38783b389a01f911c8748031a35a3b671bf7')


class Fixed:
    """Allocator stub returning one predetermined counter (test vectors only)."""
    def __init__(self, station, kind, counter):
        self.station, self.kind, self.counter = station, kind, counter

    def next(self):
        return self.counter >> 32, self.counter & 0xffffffff


@unittest.skipUnless(MBEDTLS.exists(), 'run tools/fetch-vendor.sh to fetch pinned Mbed TLS')
class FrameAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name)/'wsframe.so'
        sources = [ROOT/'firmware/common/ws_frame.c'] + [
            MBEDTLS/'library'/f'{name}.c' for name in
            ('aes', 'ccm', 'cipher', 'cipher_wrap', 'platform_util', 'constant_time')]
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-I', str(ROOT/'firmware/common'), '-I', str(MBEDTLS/'include'),
                        '-DMBEDTLS_CONFIG_FILE="ws_mbedtls_config.h"',
                        *map(str, sources), '-o', str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        u8p = ctypes.POINTER(ctypes.c_uint8)
        cls.lib.ws_seal_obs.argtypes = [u8p, ctypes.c_uint32, ctypes.c_uint64, u8p, u8p]
        cls.lib.ws_open_ack.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32] + \
            [ctypes.POINTER(t) for t in (ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_uint64, ctypes.c_uint64)]
        cls.lib.ws_key_check.argtypes = [u8p, u8p]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def buf(data, size=None):
        return (ctypes.c_uint8*(size or len(data))).from_buffer_copy(data.ljust(size or len(data), b'\0'))

    def c_seal(self, key, station, counter, plain):
        out = (ctypes.c_uint8*56)()
        self.assertEqual(self.lib.ws_seal_obs(self.buf(key), station, counter, self.buf(plain), out), 0)
        return bytes(out)

    def c_open(self, key, station, frame):
        values = [ctypes.c_uint64(), ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint64(), ctypes.c_uint64()]
        rc = self.lib.ws_open_ack(self.buf(key), station, self.buf(frame), len(frame), *map(ctypes.byref, values))
        return rc, [v.value for v in values]

    def test_known_answer_vectors(self):
        plain = OBS.pack(17, 42, 100000, 3600, -1234, 4567, 1, 1, 0)
        self.assertEqual(seal(KAT_KEY, 1, 1, Fixed(1, 1, 0x100000002), plain), KAT_OBS)
        self.assertEqual(self.c_seal(KAT_KEY, 1, 0x100000002, plain), KAT_OBS)
        self.assertEqual(seal(KAT_KEY, 1, 2, Fixed(1, 2, 5), ACK.pack(17, 42, 1760000000, 0x100000002)), KAT_ACK)
        self.assertEqual(self.c_open(KAT_KEY, 1, KAT_ACK), (0, [5, 17, 42, 1760000000, 0x100000002]))

    def test_random_agreement_both_directions(self):
        for _ in range(200):
            key, station = os.urandom(16), struct.unpack('>I', os.urandom(4))[0] or 1
            counter = struct.unpack('>Q', os.urandom(8))[0] >> 1
            plain = os.urandom(24)
            frame = self.c_seal(key, station, counter, plain)
            self.assertEqual(frame, seal(key, station, 1, Fixed(station, 1, counter), plain))
            self.assertEqual(unseal(key, station, 1, frame), plain)
            self.assertEqual(frame_counter(frame), counter)
            ack_plain = os.urandom(24)
            ack = seal(key, station, 2, Fixed(station, 2, counter), ack_plain)
            rc, values = self.c_open(key, station, ack)
            self.assertEqual(rc, 0)
            self.assertEqual(struct.pack('>IIQQ', *values[1:]), ack_plain)

    def test_ack_rejections(self):
        self.assertNotEqual(self.c_open(KAT_KEY, 1, KAT_ACK[:-1] + bytes([KAT_ACK[-1] ^ 1]))[0], 0)  # tag
        self.assertNotEqual(self.c_open(KAT_KEY, 2, KAT_ACK)[0], 0)        # wrong station
        self.assertNotEqual(self.c_open(b'x'*16, 1, KAT_ACK)[0], 0)        # wrong key
        self.assertNotEqual(self.c_open(KAT_KEY, 1, KAT_OBS)[0], 0)        # observation is not an ACK
        self.assertNotEqual(self.c_open(KAT_KEY, 1, KAT_ACK[:-1])[0], 0)   # length
        for version in (1, 2, 3):                                            # earlier drafts
            old = bytearray(KAT_ACK); old[2] = version
            self.assertNotEqual(self.c_open(KAT_KEY, 1, bytes(old))[0], 0)

    def test_invalid_reading_fillers(self):
        """Draft 3: a sensor fault never travels as a plausible number (e.g. 0.00 degC)."""
        stage0 = Path(self.tmp.name)/'stage0.so'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT/'firmware/stage0.c'), '-o', str(stage0)], check=True)
        pack = ctypes.CDLL(str(stage0)).ws_pack_observation
        pack.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                         ctypes.c_int16, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint8]
        out = (ctypes.c_uint8*24)()
        pack(out, 3, 7, 0, 90, 0, 0, 0, 0)  # fault: caller's 0/0 must not reach the wire
        self.assertEqual(bytes(out)[16:20], bytes.fromhex('8000ffff'))
        self.assertEqual(bytes(out), OBS.pack(3, 7, 0, 90, TEMP_INVALID, RH_INVALID, 0, 0, 0))
        record = decode_observation(bytes(out), 'test')
        self.assertIsNone(record['temperature_c']); self.assertEqual(record['quality'], 'sensor_fault')
        for bad in (OBS.pack(3, 7, 0, 90, 0, 0, 0, 0, 0),                     # draft-2 zero filler
                    OBS.pack(3, 7, 0, 90, 0, RH_INVALID, 0, 0, 0),            # half filler
                    OBS.pack(3, 7, 0, 90, TEMP_INVALID, 4000, 1, 0, 0),       # filler marked valid
                    OBS.pack(3, 7, 0, 90, 2100, RH_INVALID, 1, 0, 0)):
            with self.assertRaises(ValueError):
                decode_observation(bad, 'test')
        valid_zero = decode_observation(OBS.pack(3, 7, 0, 90, 0, 0, 1, 0, 0), 'test')
        self.assertEqual((valid_zero['temperature_c'], valid_zero['humidity_pct']), (0, 0))  # real 0.00 degC

    def test_key_check_value(self):
        out = (ctypes.c_uint8*3)()
        self.assertEqual(self.lib.ws_key_check(self.buf(KAT_KEY), out), 0)
        expected = Cipher(algorithms.AES(KAT_KEY), modes.ECB()).encryptor().update(b'\0'*16)[:3]
        self.assertEqual(bytes(out), expected)
        self.assertEqual(bytes(out).hex(), 'c6a13b')  # FIPS-197 AES-128 vector for this key


if __name__ == '__main__':
    unittest.main()
