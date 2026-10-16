/* Draft-5 observation encoder (firmware/common/ws_obs.c), driven with arbitrary records.
 * The input bytes become a ws_obs_t (header values, bitmap, and per-field codes chosen as random,
 * INVALID, small or CALM so valid records are common). Properties, checked against an independent
 * reading of docs/protocol-design.md section 5:
 *  - the encoder accepts exactly the canonical records and the ones that fit the buffer;
 *  - an accepted record has length 22 + the present widths (and equals WS_OBS_PLAIN_LEN), its
 *    header bytes carry the inputs, flags bit 0 is (utc != 0), and each field is its code, big-endian;
 *  - no memory error (ASan/UBSan). */
#include <string.h>
#include "fuzz.h"
#include "ws_obs.h"
#include <limits.h>

#define SPEC_WIND_CALM 0xFFFEU   /* section 5.3: wind direction "calm" */
#define CAP_MAX 100U             /* buffer sizes tried: 0-99, the longest record is 78 + 22 */

/* The spec's catalog (section 5.3), written out again on purpose: checking the encoder with its own
 * ws_obs_code_ok() would share any bug in it (a planted off-by-one went unnoticed that way). */
static const uint32_t spec_max[WS_FI_COUNT] = {16500, 10000, 8000, 750, 750, 359, 16777214, 250, 2000,
 1048575, 0xFFFFFFFFU, 65534, 65534, 16777214, 16777214, 16777214, 16777214, 100, 3, 16500, 10000,
 16500, 16500, 10000, 10000, 60};
static const uint8_t spec_width[WS_FI_COUNT] = {2, 2, 2, 2, 2, 2, 3, 1, 2, 3, 4, 2, 2, 3, 3, 3, 3, 1, 1, 2, 2,
 2, 2, 2, 2, 1};

static uint32_t spec_invalid(unsigned i)
{
 return spec_width[i] >= SPEC_U32 ? UINT32_MAX : ((uint32_t)1 << (CHAR_BIT * spec_width[i])) - 1U;
}

static int spec_code_ok(unsigned i, uint32_t c)
{
 if (c <= spec_max[i]) return 1;
 if (i == WS_FI_QUALIFIERS) return 0;
 return c == spec_invalid(i) || (i == WS_FI_WIND_DIR_DEG && c == SPEC_WIND_CALM);
}

static uint32_t take(const uint8_t **p, size_t *n, unsigned bytes)
{
 uint32_t v = 0;
 for (unsigned k = 0; k < bytes; k++) { v = v << 8 | (*n ? **p : 0); if (*n) { (*p)++; (*n)--; } }
 return v;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
 const uint8_t *p = data; size_t n = size;
 ws_obs_t o; memset(&o, 0, sizeof o);
 o.epoch = take(&p, &n, SPEC_U32); o.seq = take(&p, &n, SPEC_U32); o.utc = take(&p, &n, SPEC_U32); o.uptime = take(&p, &n, SPEC_U32);
 o.energy = (uint8_t)take(&p, &n, 1); o.cal_rev = (uint8_t)take(&p, &n, 1);
 o.bitmap = take(&p, &n, SPEC_U32);
 size_t cap = take(&p, &n, 1) % CAP_MAX;   /* below and above the longest record */
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  uint32_t sel = take(&p, &n, 1), raw = take(&p, &n, SPEC_U32);
  unsigned w = ws_obs_width(i);
  uint32_t mask = w >= SPEC_U32 ? UINT32_MAX : ((uint32_t)1 << (CHAR_BIT * w)) - 1U;
  switch (sel & 3U) {
   case 0: o.code[i] = raw & mask; break;
   case 1: o.code[i] = ws_obs_invalid(i); break;
   case 2: o.code[i] = (sel & 8U) ? spec_max[i] + (sel >> 4 & 1U) : raw % 101U; break;
   default: o.code[i] = (sel & 4U) ? WS_WIND_DIR_CALM : raw; break;
  }
 }
 uint8_t out[CAP_MAX];
 int got = ws_obs_encode(&o, out, cap);

 /* Independent statement of the rules. */
 int ok = o.bitmap && !(o.bitmap & ~WS_FIELDS_DEFINED) && o.energy <= WS_ENERGY_CRITICAL;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT && ok; i++)
  if (o.bitmap & WS_F(i)) { ok = spec_code_ok(i, o.code[i]); len += spec_width[i]; }
 if (ok && (o.bitmap & WS_F(WS_FI_WIND_SPEED_MS)) && (o.bitmap & WS_F(WS_FI_WIND_DIR_DEG)) &&
     o.code[WS_FI_WIND_SPEED_MS] == spec_invalid(WS_FI_WIND_SPEED_MS) &&
     o.code[WS_FI_WIND_DIR_DEG] != spec_invalid(WS_FI_WIND_DIR_DEG)) ok = 0;
 if (ok && len > cap) ok = 0;
 FUZZ_CHECK(ok ? got == (int)len : got == -1);
 if (got < 0) return 0;

 FUZZ_CHECK((size_t)got == WS_OBS_PLAIN_LEN(o.bitmap));
 const uint8_t *h = out; size_t hl = WS_OBS_HEAD_LEN;
 FUZZ_CHECK(take(&h, &hl, SPEC_U32) == o.epoch && take(&h, &hl, SPEC_U32) == o.seq && take(&h, &hl, SPEC_U32) == o.utc &&
            take(&h, &hl, SPEC_U32) == o.uptime);
 uint8_t flags = out[SPEC_OBS_FLAGS_AT];
 FUZZ_CHECK((flags & SPEC_OBS_FLAG_UTC) == (o.utc != 0) && (flags >> SPEC_OBS_ENERGY_SHIFT) == o.energy &&
            out[SPEC_OBS_CAL_AT] == o.cal_rev);
 h = out + SPEC_OBS_BITMAP_AT; hl = SPEC_U32;
 FUZZ_CHECK(take(&h, &hl, SPEC_U32) == o.bitmap);
 const uint8_t *q = out + WS_OBS_HEAD_LEN; size_t left = (size_t)got - WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++)
  if (o.bitmap & WS_F(i)) FUZZ_CHECK(take(&q, &left, spec_width[i]) == o.code[i]);
 FUZZ_CHECK(left == 0);
 return 0;
}
