# wsmp_cal: calibration from the module record

A v1 module board carries its sensor's calibration in its module record. That's up to three
entries, and each one is an offset and a gain for one (quantity, kind) (`wsmp.lit.md` section 8). A
passive module can't apply its own calibration, so the station applies it before it reports a value
(WSMP-G6). This file holds the calibration part of the record rules in
`docs/firmware-current-design.md` section 6.9:

- check 7 of the record, against the calibration table frozen for record major 1
- which entry a channel takes
- the calibration itself, in int64 with the station's one rounding helper (`ws_round.h`)
- the crop and range check that every channel of a port module passes, calibrated or not

The file has no state, no HAL call and no heap. The station drivers already call it on every
sample. `mod_th.c` and `mod_reg.c` look up the entry with `wsmp_cal_find` when the module is bound.
Then they run `wsmp_cal_apply` and `wsmp_cal_crop` on each sample. `wsmp_ident.c` runs
`wsmp_cal_check` during identification. Only `wsmp_cal_sample` has no driver caller.

This document is the source. `tools/tangle.py` generates `wsmp_cal.c` from the code chunks below.
The header `wsmp_cal.h` is a plain file.

```sh
python3 tools/tangle.py firmware/common/wsmp_cal.lit.md            # write wsmp_cal.c
python3 tools/tangle.py --check firmware/common/wsmp_cal.lit.md    # committed .c == tangle
```

## 1. Guarantees

| Property | Guarantee | Checked by |
|---|---|---|
| Bounds | an entry is accepted exactly when its quantity is in the table, its (quantity, kind) matches a channel of the module type (kind 0: any channel of the quantity), its revision is not 0, and its offset and gain are within the table's bounds, edges included; at any minor | `test_bounds_edges_of_the_frozen_table`, `test_entries_rejected_by_check_7`, `test_every_key_against_the_reference`, `test_unknown_quantity_is_rejected_at_any_minor`, `fuzz_record` |
| Unique | two used entries with the same (quantity, kind) are `CAL_REJECTED`. An all-zero entry is skipped | `test_entries_rejected_by_check_7`, `test_entries_accepted` |
| Precedence | a channel (q, k) takes the entry (q, k), else (q, 0), else none | `test_precedence_q_k_over_q_0` |
| Rounding | `ws_div_round` gives the golden vectors that the Python reference gives, half up, also below zero | `tests/test_wsmp_cal.py` `Rounding` |
| Range | a calibrated value never leaves the channel's physical range with good quality; beyond the crop margin it is suspect, never wrapped | `test_uva_negative_offset_at_night_crops_to_0`, `test_relative_humidity_100_to_103_percent`, `test_crop_edges_match_the_reference` |

## 2. The table

The table lives in the registry (`wsmp_registry.toml`, `[[calibration]]`). The generator builds
the C header and the gateway's Python module from it, so both get the same numbers.
`wsmp_cal_limits_of` finds a quantity's row. It's in `wsmp.c`, next to the other registry tables:

| Quantity | Scale | Offset bound | Gain (ppm) | Physical range at the scale | Crop margin below, above |
|---|---|---|---|---|---|
| air temperature (1) | −2 | ±200 | 980,000–1,020,000 | −8,000 to 6,000 | 0, 0 |
| relative humidity (2) | −2 | ±1,000 | 900,000–1,100,000 | 0 to 10,000 | 300, 300 |
| station air pressure (3) | −1 | ±50 | 990,000–1,010,000 | 3,000 to 11,000 | 0, 0 |
| UVA sensor counts (8) | 0 | ±16 | 100,000–10,000,000 | 0 to 1,048,576 | 16, 0 |

A quantity outside the table takes no record calibration. That covers every counter and sum.

## 3. Check 7

An entry counts as *used* unless every field is 0. The parser already skips an all-zero entry's
bytes. A minor above 0 may set an entry's reserved bytes. The structure doesn't keep those, and this
station ignores what it doesn't know.

Check 7 itself is strict at any minor (spec section 6.9). If an entry names a quantity that this
firmware's table doesn't know, check 7 returns `CAL_REJECTED`, even under a higher minor. So you
upgrade the stations before you field records that use a widened table. A used entry must also:

- match a channel of the module type. An entry (q, k) needs a channel with that quantity and kind.
  An entry (q, 0) needs any channel of the quantity. The channels come from the registry for the
  type (`wsmp_type`), so an entry can never name a channel the module doesn't report.
- carry a calibration revision other than 0. An uncorrected channel reports revision 0 (section 4).
  So an applied entry with revision 0 would look the same as no correction (WSMP-G6).

The spec also lists a check for "a kind-0 entry over channels of different scales". With this
table it can't fail. The table gives one scale per quantity, and the module drivers report every
channel of a quantity at that scale. The drivers must keep that true. A channel whose descriptor
scale differs from the table's must not take an entry.

```c {#check}
static int is_used(const wsmp_cal_entry *e)
{
  return e->quantity != 0 || e->kind != 0 || e->revision != 0 || e->offset != 0 || e->gain != 0;
}

static int has_channel(const wsmp_type_entry *t, uint16_t quantity, uint8_t kind)
{
  for (unsigned i = 0; i < t->channels && i < WSMP_MAX_CHANNELS; i++)
    if (t->ch[i].quantity == quantity && (kind == 0 || t->ch[i].kind == kind)) return 1;
  return 0;
}

static int entry_ok(const wsmp_type_entry *t, const wsmp_cal_entry *e)
{
  const wsmp_cal_limits *l = wsmp_cal_limits_of(e->quantity);
  if (l == NULL || e->revision == 0 || !has_channel(t, e->quantity, e->kind)) return 0;
  if (e->offset < -l->offset_bound || e->offset > l->offset_bound) return 0;
  return e->gain >= l->gain_min && e->gain <= l->gain_max;
}

static int duplicate(const wsmp_record *r, unsigned i)
{
  for (unsigned j = 0; j < i; j++)
    if (is_used(&r->cal[j]) && r->cal[j].quantity == r->cal[i].quantity && r->cal[j].kind == r->cal[i].kind) return 1;
  return 0;
}

uint8_t wsmp_cal_check(const wsmp_record *r)
{
  const wsmp_type_entry *t = wsmp_type(r->type);
  if (t == NULL) return WSMP_REC_CAL_REJECTED;   /* the parser refuses it first: MALFORMED */
  for (unsigned i = 0; i < WSMP_RECORD_CAL_N; i++)
    if (is_used(&r->cal[i]) && (!entry_ok(t, &r->cal[i]) || duplicate(r, i))) return WSMP_REC_CAL_REJECTED;
  return WSMP_REC_APPLIED;
}
```

## 4. Which entry

For a channel (quantity q, kind k), an entry (q, k) wins over an entry (q, 0). If a channel has
neither, the station reports it uncorrected, with calibration revision 0. Check 7 refuses two
entries with the same key, so at most one of each kind matches.

```c {#find}
const wsmp_cal_entry *wsmp_cal_find(const wsmp_record *r, uint16_t quantity, uint8_t kind)
{
  const wsmp_cal_entry *every_kind = NULL;
  for (unsigned i = 0; i < WSMP_RECORD_CAL_N; i++)
  {
    const wsmp_cal_entry *e = &r->cal[i];
    if (!is_used(e) || e->quantity != quantity) continue;
    if (e->kind == kind) return e;
    if (e->kind == 0) every_kind = e;
  }
  return every_kind;
}
```

## 5. Applying it

`v' = ws_div_round(v × gain, 10⁶) + offset`, in int64. The product doesn't fit in 32 bits. For
example, a relative humidity of 6000 (60.00 %) times a gain of 1,100,000 is 6.6 × 10⁹. The table's
largest gain is 10⁷, which is below 2²⁴. With that gain and an int32 raw value, the product stays
below 2⁵⁵. That's far inside `ws_div_round`'s range.

```c {#apply}
int64_t wsmp_cal_apply(const wsmp_cal_entry *e, int32_t raw)
{
  if (e == NULL) return raw;
  return ws_div_round((int64_t)raw * (int64_t)e->gain, WSMP_CAL_UNITY) + e->offset;
}
```

## 6. Crop and range check

Each quantity has a physical range, plus a crop margin below and above it. The crop moves a
value inside the margin to the physical limit, with good quality. A value beyond the margin is suspect,
and the driver keeps it out of that channel's window sum. So a UVA offset of −5 on a night reading
of 0–2 gives 0, never a negative count. A relative humidity of 100–103 % reports 100 %. `*out`
always gets the cropped value, inside the physical range (and int32), even for a suspect sample.

```c {#crop}
uint8_t wsmp_cal_crop(uint16_t quantity, int64_t v, int32_t *out)
{
  const wsmp_cal_limits *l = wsmp_cal_limits_of(quantity);
  int64_t lo = l ? l->range_min : INT32_MIN, hi = l ? l->range_max : INT32_MAX;
  int64_t below = l ? l->margin_below : 0, above = l ? l->margin_above : 0;
  *out = (int32_t)(v < lo ? lo : v > hi ? hi : v);
  return (v < lo - below || v > hi + above) ? (uint8_t)WSMP_QUAL_SUSPECT : (uint8_t)WSMP_QUAL_GOOD;
}

uint8_t wsmp_cal_sample(const wsmp_record *applied, uint16_t quantity, uint8_t kind, int32_t raw, int32_t *out)
{
  const wsmp_cal_entry *e = applied ? wsmp_cal_find(applied, quantity, kind) : NULL;
  return wsmp_cal_crop(quantity, wsmp_cal_apply(e, raw), out);
}
```

## 7. The file

```c {#wsmp_cal.c}
#include "wsmp_cal.h"
#include <stddef.h>
#include "ws_round.h"

<<check>>

<<find>>

<<apply>>

<<crop>>
```
