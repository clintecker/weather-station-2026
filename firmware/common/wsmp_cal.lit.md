# wsmp_cal: calibration from the module record

A v1 module board carries its sensor's calibration in its module record: up to three entries, each
an offset and a gain for one (quantity, kind) (`wsmp.lit.md` section 8). A passive module cannot
apply its own calibration, so the station applies it before it reports a value (WSMP-G6). This file
holds that part of the record rules of
`docs/firmware-current-design.md` section 6.9:

- check 7 of the record, against the calibration table frozen for record major 1;
- which entry a channel takes;
- the calibration itself, in int64 with the station's one rounding helper (`ws_round.h`);
- the crop and range check that every channel of a port module passes, calibrated or not.

The file has no state, no HAL call and no heap. The station drivers call it per sample (a later
change; this file is the pure part).

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

The table is in the registry (`wsmp_registry.toml`, `[[calibration]]`), so the generator gives the
C header and the gateway's Python module the same numbers. `wsmp_cal_limits_of` (in `wsmp.c`, beside
the other registry tables) finds a quantity's row:

| Quantity | Scale | Offset bound | Gain (ppm) | Physical range at the scale | Crop margin below, above |
|---|---|---|---|---|---|
| air temperature (1) | −2 | ±200 | 980,000–1,020,000 | −8,000 to 6,000 | 0, 0 |
| relative humidity (2) | −2 | ±1,000 | 900,000–1,100,000 | 0 to 10,000 | 300, 300 |
| station air pressure (3) | −1 | ±50 | 990,000–1,010,000 | 3,000 to 11,000 | 0, 0 |
| UVA sensor counts (8) | 0 | ±16 | 100,000–10,000,000 | 0 to 1,048,576 | 16, 0 |

A quantity outside the table takes no record calibration; this covers every counter and sum.

## 3. Check 7

An entry is *used* unless every field is 0. The parser has already skipped an all-zero entry's
bytes; a minor above 0 may set an entry's reserved bytes, which the structure does not keep, and
this station ignores what it does not know.

Check 7 itself is strict at any minor (spec section 6.9): an entry for a quantity this firmware's
table does not know is `CAL_REJECTED` even under a higher minor, so stations are upgraded before
records that use a widened table are fielded. A used entry must also:

- match a channel of the module type: (q, k) a channel with that quantity and kind, (q, 0) any
  channel of the quantity. The channels are the registry's for the type (`wsmp_type`), so an entry
  can never name a channel the module does not report;
- carry a calibration revision other than 0. Revision 0 is what an uncorrected channel reports
  (section 4), so an applied entry with it could not be told from no correction (WSMP-G6).

The spec's check "a kind-0 entry over channels of different scales" cannot fail with this table:
the table gives one scale per quantity, and the module drivers report every channel of a quantity
at that scale. The driver change that wires calibration in must keep that true (a channel whose
descriptor scale differs from the table's must not take an entry).

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

For a channel (quantity q, kind k), an entry (q, k) wins over an entry (q, 0). A channel with
neither is reported uncorrected, with calibration revision 0. Check 7 has refused two entries with
the same key, so at most one of each kind matches.

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

`v' = ws_div_round(v × gain, 10⁶) + offset`, in int64. The product does not fit 32 bits: a relative
humidity of 6000 (60.00 %) times a gain of 1,100,000 is 6.6 × 10⁹. With the table's largest gain
(10⁷ < 2²⁴) and an int32 raw value the product stays below 2⁵⁵, far inside `ws_div_round`'s range.

```c {#apply}
int64_t wsmp_cal_apply(const wsmp_cal_entry *e, int32_t raw)
{
  if (e == NULL) return raw;
  return ws_div_round((int64_t)raw * (int64_t)e->gain, WSMP_CAL_UNITY) + e->offset;
}
```

## 6. Crop and range check

Each quantity has a physical range and a crop margin below and above it. A value within the margin
is cropped to the physical limit with good quality; a value beyond it is suspect and the driver
keeps it out of that channel's window sum. So a UVA offset of −5 on a night reading of 0–2 gives 0,
never a negative count, and a relative humidity of 100–103 % reports 100 %. *out is always the
cropped value, inside the physical range (and int32), also for a suspect sample.

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
