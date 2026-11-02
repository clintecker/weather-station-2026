"""Record calibration and the shared rounding helper (firmware/common/wsmp_cal.c, ws_round.h).

The frozen calibration table, the order (raw, calibration in int64, crop) and the rounding come from
docs/firmware-current-design.md section 6.9, through the independent
reference tests/wsmp_record_ref.py. The rounding golden vectors (tests/ws_div_round_vectors.csv) are
one table for the C helper and the Python reference.
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
#include "ws_round.h"
#include "wsmp.h"
#include "wsmp_cal.h"
int64_t t_div_round(int64_t num, int64_t den) { return ws_div_round(num, den); }
int t_cal_check(const uint8_t rec[WSMP_RECORD_LEN])
{
  wsmp_record r;
  int st = wsmp_record_parse(rec, &r);
  return st != WSMP_REC_APPLIED ? -st : wsmp_cal_check(&r);
}
int t_sample(const uint8_t *rec, unsigned quantity, unsigned kind, int32_t raw, int32_t *out, unsigned *revision)
{
  wsmp_record r;
  const wsmp_record *applied = rec && wsmp_record_parse(rec, &r) == WSMP_REC_APPLIED ? &r : NULL;
  const wsmp_cal_entry *e = applied ? wsmp_cal_find(applied, (uint16_t)quantity, (uint8_t)kind) : NULL;
  *revision = e ? e->revision : 0U;
  return wsmp_cal_sample(applied, (uint16_t)quantity, (uint8_t)kind, raw, out);
}
int t_crop(unsigned quantity, int64_t v, int32_t *out) { return wsmp_cal_crop((uint16_t)quantity, v, out); }
'''

GOOD, SUSPECT = 0, 2                    # WSMP section 9 quality codes
TYPE_OF = {1: 1, 2: 1, 3: 2, 8: 3}     # a module type that has the quantity (WSMP section 4.4)


def rec(module_type, cal):
    kw = {'bind_kind': 0, 'bind_value': 0} if module_type != 1 else {}
    return ref.record(module_type=module_type, cal=cal, **kw)


def buf(b):
    return (ctypes.c_uint8 * len(b))(*b)


@needs_cc
class Rounding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Cal.setUpClass.__func__(cls)

    def test_golden_vectors_for_c_and_python(self):
        rows = ref.vectors()
        self.assertGreaterEqual(len(rows), 30)
        for num, den, want in rows:
            with self.subTest(num=num, den=den):
                self.assertEqual(ref.div_round(num, den), want, 'the Python reference')
                self.assertEqual(self.lib.t_div_round(num, den), want, 'the C helper')

    def test_half_up_not_half_even_and_not_truncation(self):
        self.assertEqual(self.lib.t_div_round(-3, 2), -1)            # half to even (Python round) gives -2
        self.assertEqual(self.lib.t_div_round(-7, 4), -2)            # truncation gives -1
        self.assertEqual(round(-1.5), -2)                            # why the reference never uses round()

    def test_sweep_against_the_reference(self):
        for den in (1, 2, 3, 4, 7, 255, 1_000_000):
            for num in range(-3 * den - 2, 3 * den + 3, max(1, den // 50)):
                self.assertEqual(self.lib.t_div_round(num, den), ref.div_round(num, den), (num, den))


@needs_cc
class Cal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        cls.lib = host_library(cls, 'wsmp_cal', '-Wconversion', '-Wsign-conversion', '-I', fw/'common',
                               fw/'common'/'wsmp.c', fw/'common'/'wsmp_cal.c', files={'shim.c': SHIM})
        cls.lib.t_div_round.restype = ctypes.c_int64
        cls.lib.t_div_round.argtypes = [ctypes.c_int64, ctypes.c_int64]
        cls.lib.t_crop.argtypes = [ctypes.c_uint, ctypes.c_int64, ctypes.POINTER(ctypes.c_int32)]

    def check(self, module_type, cal):
        return self.lib.t_cal_check(buf(rec(module_type, cal)))

    def sample(self, record, quantity, kind, raw):
        out, revision = ctypes.c_int32(), ctypes.c_uint()
        q = self.lib.t_sample(buf(record) if record else None, quantity, kind, raw, ctypes.byref(out), ctypes.byref(revision))
        return out.value, q, revision.value

    def crop(self, quantity, v):
        out = ctypes.c_int32()
        q = self.lib.t_crop(quantity, v, ctypes.byref(out))
        return out.value, q

    def test_bounds_edges_of_the_frozen_table(self):
        for quantity, (off, gmin, gmax, *_) in ref.CAL.items():
            t = TYPE_OF[quantity]
            with self.subTest(quantity=quantity):
                for offset, gain in ((off, gmin), (-off, gmax), (0, 1_000_000 if gmin <= 1_000_000 <= gmax else gmin)):
                    self.assertEqual(self.check(t, [(quantity, 2, 1, offset, gain)]), ref.APPLIED, (offset, gain))
                for offset, gain in ((off + 1, gmin), (-off - 1, gmax), (0, gmin - 1), (0, gmax + 1)):
                    self.assertEqual(self.check(t, [(quantity, 2, 1, offset, gain)]), ref.CAL_REJECTED, (offset, gain))

    def test_the_table_values(self):
        # Section 6.9 written out once more: +-2 degC, +-10 %RH, +-5 hPa, +-16 counts; the gains.
        self.assertEqual({q: v[:3] for q, v in ref.CAL.items()},
                         {1: (200, 980_000, 1_020_000), 2: (1_000, 900_000, 1_100_000), 3: (50, 990_000, 1_010_000),
                          8: (16, 100_000, 10_000_000)})

    def test_entries_rejected_by_check_7(self):
        R = ref.CAL_REJECTED
        cases = {
            'wind speed: not in the table': (6, [(4, 0, 1, 0, 1_000_000)]),
            'anemometer pulses (a counter)': (6, [(17, 6, 1, 0, 1_000_000)]),
            'rain tips (a counter)': (7, [(7, 0, 1, 0, 1_000_000)]),
            'unknown quantity 99': (1, [(99, 2, 1, 0, 1_000_000)]),
            'pressure on a type-1 module': (1, [(3, 2, 1, 0, 1_000_000)]),
            'temperature on a UVA module': (3, [(1, 2, 1, 0, 1_000_000)]),
            'duplicate (1, 2)': (1, [(1, 2, 1, 0, 1_000_000), (1, 2, 2, 5, 1_000_000)]),
            'duplicate (2, 0)': (1, [(2, 0, 1, 0, 1_000_000), (0, 0, 0, 0, 0), (2, 0, 2, 5, 1_000_000)]),
            'one good entry, one bad': (1, [(1, 2, 1, 0, 1_000_000), (2, 2, 1, 1_001, 1_000_000)]),
            'gain 0': (1, [(1, 2, 1, 0, 0)]),
            'revision 0 on a used entry (0 means uncorrected)': (1, [(1, 2, 0, 5, 1_000_000)]),
            'revision 0 with kind 0': (3, [(8, 0, 0, 0, 1_000_000)]),
            '(1, 1): type 1 has no point temperature': (1, [(1, 1, 1, 0, 1_000_000)]),
            '(8, 6): type 3 has no UVA counter': (3, [(8, 6, 1, 0, 1_000_000)]),
            '(3, 10): kind 10 on pressure': (2, [(3, 10, 1, 0, 1_000_000)]),
        }
        for name, (t, cal) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.check(t, cal), R)

    def test_entries_accepted(self):
        cases = {
            'no entries': (1, []),
            'all-zero entries skipped': (2, [(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (3, 0, 1, 50, 990_000)]),
            '(q, 0) beside (q, k)': (1, [(1, 0, 1, 10, 1_000_000), (1, 2, 1, 20, 1_000_000)]),
            'three entries': (1, [(1, 2, 1, 10, 1_000_000), (2, 2, 1, 20, 1_000_000), (2, 0, 1, 0, 1_000_000)]),
        }
        for name, (t, cal) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.check(t, cal), ref.APPLIED)

    def test_revision_edges(self):
        self.assertEqual(self.check(1, [(1, 2, 1, 0, 1_000_000)]), ref.APPLIED)
        self.assertEqual(self.check(1, [(1, 2, 0xFFFF, 0, 1_000_000)]), ref.APPLIED)
        self.assertEqual(self.check(1, [(1, 2, 0, 0, 1_000_000)]), ref.CAL_REJECTED)

    def test_unknown_quantity_is_rejected_at_any_minor(self):
        # Check 7 is strict: a higher minor may widen the table only for a station that knows it.
        for minor in (0, 1, 255):
            for t, cal in ((1, [(4, 0, 1, 0, 1_000_000)]), (6, [(5, 7, 1, 0, 1_000_000)]), (1, [(99, 2, 1, 0, 1_000_000)])):
                with self.subTest(minor=minor, type=t, cal=cal):
                    kw = {'bind_kind': 0, 'bind_value': 0} if t != 1 else {}
                    record = ref.record(module_type=t, cal=cal, minor=minor, **kw)
                    self.assertEqual(self.lib.t_cal_check(buf(record)), ref.CAL_REJECTED)

    def test_every_key_against_the_reference(self):
        # Every (type, quantity, kind) a table quantity can take, with a revision of 0 and 1, against
        # check 7 of the reference: (q, k) must match a channel of the type, (q, 0) any of the quantity.
        for t in ref.CHANNELS:
            for q in ref.CAL:
                for k in range(0, 11):
                    for revision in (0, 1):
                        e = (q, k, revision, 0, ref.CAL[q][1])
                        with self.subTest(type=t, entry=e):
                            self.assertEqual(self.check(t, [e]), ref.check7(t, [e]))

    def test_precedence_q_k_over_q_0(self):
        r = rec(1, [(1, 0, 1, 100, 1_000_000), (1, 2, 5, 10, 1_000_000)])
        self.assertEqual(self.sample(r, 1, 2, 2000), (2010, GOOD, 5))      # (1, 2) wins over (1, 0)
        self.assertEqual(self.sample(r, 1, 1, 2000), (2100, GOOD, 1))      # another kind: (1, 0)
        self.assertEqual(self.sample(r, 2, 2, 5000), (5000, GOOD, 0))      # no entry: uncorrected, revision 0
        self.assertEqual(self.sample(None, 1, 2, 2000), (2000, GOOD, 0))   # no applied record

    def test_apply_in_int64_with_half_up_rounding(self):
        rh = rec(1, [(2, 2, 1, 0, 1_100_000)])
        self.assertEqual(self.sample(rh, 2, 2, 6000), (6600, GOOD, 1))     # 6000 x 1.1: 6.6e9 before the division
        t = rec(1, [(1, 2, 1, 0, 1_020_000)])
        self.assertEqual(self.sample(t, 1, 2, -1), (-1, GOOD, 1))          # -1.02 to -1; truncation would give 0
        self.assertEqual(ref.apply(-1, 0, 1_020_000), -1)
        t = rec(1, [(1, 2, 1, 0, 980_000)])
        self.assertEqual(self.sample(t, 1, 2, -75), (-73, GOOD, 1))        # -73.5 half up; half to even gives -74
        self.assertEqual(ref.apply(-75, 0, 980_000), -73)
        for raw in (-8000, -4321, -1, 0, 1, 2500, 6000):
            for offset, gain in ((-200, 980_000), (200, 1_020_000), (-7, 1_013_333)):
                with self.subTest(raw=raw, offset=offset, gain=gain):
                    want = ref.crop(1, ref.apply(raw, offset, gain))
                    got = self.sample(rec(1, [(1, 2, 1, offset, gain)]), 1, 2, raw)
                    self.assertEqual(got[1], GOOD if want[1] else SUSPECT)
                    self.assertEqual(got[0], want[0])   # suspect values are clamped too

    def test_uva_negative_offset_at_night_crops_to_0(self):
        r = rec(3, [(8, 2, 1, -5, 1_000_000)])
        for raw in (0, 1, 2):
            self.assertEqual(self.sample(r, 8, 2, raw), (0, GOOD, 1))       # never a negative count
        self.assertEqual(self.sample(r, 8, 2, 9), (4, GOOD, 1))
        r = rec(3, [(8, 0, 1, -16, 100_000)])
        self.assertEqual(self.sample(r, 8, 2, 0), (0, GOOD, 1))           # -16: the whole margin below
        self.assertEqual(self.crop(8, -16), (0, GOOD))
        self.assertEqual(self.crop(8, -17)[1], SUSPECT)
        r = rec(3, [(8, 2, 1, 0, 10_000_000)])
        self.assertEqual(self.sample(r, 8, 2, 104_857)[:2], (1_048_570, GOOD))
        self.assertEqual(self.sample(r, 8, 2, 104_858)[1], SUSPECT)      # 1,048,580: above the range, no margin

    def test_relative_humidity_100_to_103_percent(self):
        self.assertEqual(self.crop(2, 10_000), (10_000, GOOD))
        self.assertEqual(self.crop(2, 10_001), (10_000, GOOD))
        self.assertEqual(self.crop(2, 10_300), (10_000, GOOD))
        self.assertEqual(self.crop(2, 10_301)[1], SUSPECT)
        self.assertEqual(self.crop(2, -300), (0, GOOD))
        self.assertEqual(self.crop(2, -301)[1], SUSPECT)
        r = rec(1, [(2, 2, 1, 250, 1_000_000)])
        self.assertEqual(self.sample(r, 2, 2, 10_000)[:2], (10_000, GOOD))   # 102.50 % cropped
        self.assertEqual(self.sample(r, 2, 2, 10_100)[1], SUSPECT)          # 103.50 %

    def test_crop_edges_match_the_reference(self):
        for quantity, (_, _, _, lo, hi, below, above) in ref.CAL.items():
            for v in (lo - below - 1, lo - below, lo - 1, lo, lo + 1, hi - 1, hi, hi + 1, hi + above, hi + above + 1,
                      -(1 << 40), 1 << 40):
                with self.subTest(quantity=quantity, v=v):
                    want = ref.crop(quantity, v)
                    got = self.crop(quantity, v)
                    self.assertEqual(got[1], GOOD if want[1] else SUSPECT)
                    self.assertEqual(got[0], want[0])   # suspect values are clamped too

    def test_quantity_outside_the_table_is_not_cropped(self):
        self.assertEqual(self.crop(4, 9_999), (9_999, GOOD))
        self.assertEqual(self.crop(4, 1 << 40)[1], SUSPECT)              # still never wraps into 32 bits


if __name__ == '__main__':
    unittest.main()
