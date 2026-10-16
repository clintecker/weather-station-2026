"""Draft-5 observation codec: catalog arithmetic, exact decoding, canonical-encoding properties,
and byte-for-byte agreement between the C encoder (firmware/common/ws_obs.c) and ws0/fields.py."""
import ctypes
import random
import unittest

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>
from ws0 import fields
from ws0.fields import FIELDS, decode, encode

SEED = 20261014
# Encoding known-answer vector (docs/protocol-design.md section 6): T = -12.34 C, RH = 45.67 %,
# epoch 1, sequence 2, UTC 1791991189, uptime 300 s, NORMAL, calibration 0.
KAT = bytes.fromhex('00000001' '00000002' '6acf9d95' '0000012c' '03' '00' '00000003' '0ace' '11d7')


def random_record(rng, bitmap=None):
    """A canonical record: header values and {index: code} with edges, INVALID and CALM mixed in."""
    if bitmap is None:
        bitmap = rng.randrange(1, fields.DEFINED + 1)
    codes = {}
    for f in FIELDS:
        if bitmap >> f.index & 1:
            choices = [0, f.max, rng.randint(0, f.max)]
            if f.invalid is not None:
                choices.append(f.invalid)
            if f.name == 'wind_dir_deg':
                choices.append(fields.WIND_DIR_CALM)
            codes[f.index] = rng.choice(choices)
    if codes.get(3) == FIELDS[3].invalid and 5 in codes:
        codes[5] = FIELDS[5].invalid
    utc = rng.choice([0, rng.randrange(1, 2**32)])
    head = (rng.randrange(2**32), rng.randrange(2**32), utc, rng.randrange(2**32), rng.randrange(4), rng.randrange(256))
    return head, codes


class Catalog(unittest.TestCase):
    def test_widths_hold_max_and_invalid(self):
        for f in FIELDS:
            self.assertLess(f.max, 1 << 8 * f.width, f.name)
            if f.invalid is not None:
                self.assertGreater(f.invalid, f.max, f.name)

    def test_known_answer(self):
        codes = {0: FIELDS[0].code(-12.34), 1: FIELDS[1].code(45.67)}
        self.assertEqual(codes, {0: 2766, 1: 4567})
        self.assertEqual(encode(1, 2, 1791991189, 300, 1, 0, codes), KAT)
        head, back = decode(KAT)
        self.assertEqual(fields.values(back), {'temperature_c': -12.34, 'humidity_pct': 45.67})
        self.assertEqual((head['energy_state'], head['time_known']), ('normal', True))

    def test_every_code_decodes_exactly(self):
        """value(code) prints with no float noise and converts back to the same code."""
        for f in FIELDS:
            if f.width > 2 or f.name == 'qualifiers':
                continue
            decimals = len(str(f.scale)) - 1
            for code in range(f.max + 1):
                v = f.value(code)
                self.assertEqual(round(v, decimals), v, (f.name, code))
                self.assertLessEqual(len(repr(v).partition('.')[2]), max(decimals, 1), (f.name, code, v))
                self.assertEqual(f.code(v), code, (f.name, code))

    def test_range_edges(self):
        t, rh, wd, cur = FIELDS[0], FIELDS[1], FIELDS[5], FIELDS[12]
        self.assertEqual((t.value(0), t.value(16500), t.value(4000)), (-40.0, 125.0, 0.0))
        self.assertEqual((t.code(-40.005), t.code(125.004)), (0, 16500))     # half up
        self.assertEqual((t.code(-40.01), t.code(125.01)), (t.invalid, t.invalid))
        self.assertEqual((rh.code(-3.2), rh.code(119.0)), (0, 10000))         # RH clamps
        self.assertEqual((wd.code(359.6), wd.code(-0.4)), (0, 0))             # wraps mod 360
        self.assertEqual((cur.code(-3276.8), cur.code(3276.6), cur.code(3276.7)), (0, 65534, cur.invalid))
        self.assertEqual(fields.values({5: fields.WIND_DIR_CALM}), {'wind_calm': True, 'wind_dir_deg': None})
        self.assertEqual(fields.values({10: 1 | 2 << 12}), {'qualifiers': {'temperature_c': 'suspected_icing',
                                                                          'rain_tips': 'delayed_melt'}})


class Canonical(unittest.TestCase):
    def test_round_trip(self):
        rng = random.Random(SEED)
        for _ in range(3000):
            head, codes = random_record(rng)
            plain = encode(*head, codes)
            self.assertEqual(len(plain), fields.HEAD_LEN + fields.fields_len(sum(1 << i for i in codes)))
            got_head, got = decode(plain)
            self.assertEqual(got, codes)
            self.assertEqual((got_head['epoch'], got_head['utc']), (head[0], head[2]))

    def test_whatever_decodes_reencodes_byte_for_byte(self):
        """The canonical property: no reading has two accepted encodings. Mutate valid records at
        random; anything decode() accepts must be exactly what encode() makes of its result."""
        rng = random.Random(SEED + 1)
        accepted = 0
        for _ in range(20000):
            plain = bytearray(encode(*random_record(rng)[0], random_record(rng)[1]))
            for _ in range(rng.randint(1, 3)):
                op = rng.randrange(4)
                if op == 0 and plain:
                    plain[rng.randrange(len(plain))] ^= 1 << rng.randrange(8)
                elif op == 1 and plain:
                    plain[rng.randrange(len(plain))] = rng.randrange(256)
                elif op == 2:
                    del plain[rng.randrange(len(plain) + 1):]
                else:
                    plain += bytes(rng.randrange(256) for _ in range(rng.randint(1, 4)))
            try:
                head, codes = decode(bytes(plain))
            except ValueError:
                continue
            accepted += 1
            energy = fields.ENERGY.index(head['energy_state'])
            again = encode(head['epoch'], head['sequence'], head['utc'], head['uptime'], energy,
                           head['calibration_revision'], codes)
            self.assertEqual(again, bytes(plain))
        self.assertGreater(accepted, 1000)   # the property was actually exercised

    def test_rejections(self):
        good = KAT
        bad = {
            'empty bitmap': good[:18] + bytes(4),
            'reserved bitmap bit': good[:18] + (1 << 21 | 3).to_bytes(4, 'big') + good[22:],
            'reserved flag bit': good[:16] + bytes([good[16] | 8]) + good[17:],
            'time flag without UTC': good[:8] + bytes(4) + good[12:],
            'UTC without time flag': good[:16] + bytes([good[16] & ~1]) + good[17:],
            'too long': good + b'\0',
            'too short': good[:-1],
            'temperature above max': good[:22] + (16501).to_bytes(2, 'big') + good[24:],
        }
        for why, plain in bad.items():
            with self.assertRaises(ValueError, msg=why):
                decode(plain)
        wind = {3: FIELDS[3].invalid, 5: 90}
        with self.assertRaises(ValueError):
            encode(1, 1, 0, 1, 1, 0, wind)
        with self.assertRaises(ValueError):
            decode(encode(1, 1, 0, 1, 1, 0, {3: FIELDS[3].invalid, 5: FIELDS[5].invalid})[:-2] + (90).to_bytes(2, 'big'))


class ObsT(ctypes.Structure):
    _fields_ = [('epoch', ctypes.c_uint32), ('seq', ctypes.c_uint32), ('utc', ctypes.c_uint32),
                ('uptime', ctypes.c_uint32), ('energy', ctypes.c_uint8), ('cal_rev', ctypes.c_uint8),
                ('bitmap', ctypes.c_uint32), ('code', ctypes.c_uint32 * len(FIELDS))]


@needs_cc
class CAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The header's constant-expression length macro must agree with the runtime table.
        check = ('#include "ws_obs.h"\nint macro_width(unsigned i) { return (int)WS_OBS_FIELDS_LEN(WS_F(i)); }\n'
                 'int plain_all(void) { return (int)WS_OBS_PLAIN_ALL; }\n')
        cls.lib = host_library(cls, 'wsobs', '-Wconversion', '-Wsign-conversion', '-I', ROOT / 'firmware/common',
                               ROOT / 'firmware/common/ws_obs.c', files={'check.c': check})
        cls.lib.ws_obs_encode.argtypes = [ctypes.POINTER(ObsT), ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        cls.lib.ws_obs_code_ok.argtypes = [ctypes.c_uint, ctypes.c_uint32]
        cls.lib.ws_obs_invalid.restype = ctypes.c_uint32
        cls.lib.ws_code_temp_centi.argtypes = [ctypes.c_int32]
        cls.lib.ws_code_temp_centi.restype = ctypes.c_uint32
        cls.lib.ws_code_rh_centi.argtypes = [ctypes.c_int32]
        cls.lib.ws_code_rh_centi.restype = ctypes.c_uint32

    def c_encode(self, head, codes, cap=96):
        o = ObsT(*head[:6], sum(1 << i for i in codes))
        for i, c in codes.items():
            o.code[i] = c
        out = (ctypes.c_uint8 * cap)()
        n = self.lib.ws_obs_encode(ctypes.byref(o), out, cap)
        return None if n < 0 else bytes(out[:n])

    def test_table_matches_python(self):
        self.assertEqual(self.lib.plain_all(), fields.HEAD_LEN + fields.fields_len(fields.DEFINED))
        for f in FIELDS:
            self.assertEqual(self.lib.macro_width(f.index), f.width, f.name)
            self.assertEqual(self.lib.ws_obs_invalid(f.index), f.invalid or 0, f.name)
            for code in {0, f.max, f.max + 1, f.invalid or 0, fields.WIND_DIR_CALM, 2**32 - 1}:
                if code < 2**32:
                    self.assertEqual(bool(self.lib.ws_obs_code_ok(f.index, code)), f.code_ok(code), (f.name, code))

    def test_known_answer(self):
        self.assertEqual(self.c_encode((1, 2, 1791991189, 300, 1, 0), {0: 2766, 1: 4567}), KAT)

    def test_c_and_python_produce_the_same_bytes(self):
        rng = random.Random(SEED + 2)
        for _ in range(3000):
            head, codes = random_record(rng)
            c = self.c_encode(head, codes)
            self.assertEqual(c, encode(*head, codes))
            self.assertEqual(decode(c)[1], codes)

    def test_c_rejects_what_python_rejects(self):
        rng = random.Random(SEED + 3)
        for _ in range(3000):
            head, codes = random_record(rng)
            i = rng.choice(list(codes))
            f = FIELDS[i]
            if f.name == 'qualifiers':
                continue
            codes[i] = rng.choice([f.max + 1, f.invalid - 1 if f.invalid - 1 > f.max else f.max + 1])
            if f.code_ok(codes[i]):    # e.g. CALM for wind direction
                continue
            self.assertIsNone(self.c_encode(head, codes))
            with self.assertRaises(ValueError):
                encode(*head, codes)
        self.assertIsNone(self.c_encode((1, 1, 0, 1, 4, 0), {0: 1}))            # energy 4
        self.assertIsNone(self.c_encode((1, 1, 0, 1, 1, 0), {}))                # no fields
        self.assertIsNone(self.c_encode((1, 1, 0, 1, 1, 0), {3: 1023, 5: 90}))   # direction without speed
        self.assertIsNone(self.c_encode((1, 1, 0, 1, 1, 0), {0: 1}, cap=23))     # does not fit

    def test_physical_conversions(self):
        t, rh = self.lib.ws_code_temp_centi, self.lib.ws_code_rh_centi
        self.assertEqual([t(-4001), t(-4000), t(0), t(12500), t(12501)], [0xFFFF, 0, 4000, 16500, 0xFFFF])
        self.assertEqual([rh(-600), rh(0), rh(4567), rh(10000), rh(11900)], [0, 0, 4567, 10000, 10000])


if __name__ == '__main__':
    unittest.main()
