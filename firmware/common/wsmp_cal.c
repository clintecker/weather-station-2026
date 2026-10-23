/* GENERATED from wsmp_cal.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/common/wsmp_cal.lit.md (tests/test_tangle.py checks this file). */
#include "wsmp_cal.h"
#include <stddef.h>
#include "ws_round.h"

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

int64_t wsmp_cal_apply(const wsmp_cal_entry *e, int32_t raw)
{
  if (e == NULL) return raw;
  return ws_div_round((int64_t)raw * (int64_t)e->gain, WSMP_CAL_UNITY) + e->offset;
}

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
