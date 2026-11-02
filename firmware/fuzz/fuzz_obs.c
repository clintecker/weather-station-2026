/* Observation encoder and length parser (firmware/common/ws_obs.c), driven with arbitrary records.
 * The input bytes become a ws_obs_t (header values, a 64-bit logical field mask, and per-field codes
 * chosen as random, INVALID, small, the range edge or CALM so valid records are common). Properties,
 * checked against an independent reading of docs/protocol-design.md section 5 and catalog v2 of the
 * power telemetry design (docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 5.1,
 * 5.2 and 5.4):
 *  - the encoder accepts exactly the canonical records and the ones that fit the buffer;
 *  - an accepted record has length 22 + the extension word (when a field 32-47 is present) + the
 *    present widths (and equals WS_OBS_PLAIN_LEN), its header bytes carry the inputs, flags bit 0 is
 *    (utc != 0), bitmap bit 31 (EXT) is set exactly when the extension word follows, and each field
 *    is its code, big-endian, in increasing index order;
 *  - ws_obs_plain_len gives back the encoded length of an accepted record, and on the raw input bytes
 *    (read as a stored plaintext) returns exactly what the specification's EXT rules allow: EXT with
 *    an empty extension bitmap, a reserved extension bit or no field at all is rejected, an
 *    extension-only record is legal;
 *  - no memory error (ASan/UBSan).
 * Input: the 22-byte header (epoch, seq, UTC, uptime, energy, calibration, mask bits 0-31), mask bits
 * 32-47 (u16, so bytes 0-23 also read as a plaintext header with its extension word), mask bits 48-63
 * (u16), the buffer size (u8), then per field a selector byte and a raw u32. */
#include <string.h>
#include "fuzz.h"
#include "ws_obs.h"
#include <limits.h>

#define SPEC_FIELDS    34U       /* catalog v2: field indexes 0-33 (design section 5.2) */
#define SPEC_EXT_INDEX 31U       /* bit 31 is EXT, never a field: width 0 */
#define SPEC_WIND_DIR  5U
#define SPEC_WIND_SPEED 3U
#define SPEC_QUALIFIERS 10U
#define SPEC_WIND_CALM 0xFFFEU   /* section 5.3: wind direction "calm" */
#define SPEC_BASE_FIELDS 0x7FFFFFFFU   /* fields 0-30: the wire bitmap's own bits */
#define SPEC_U16       2U
#define SPEC_MASK_BITS 64U
#define CAP_MAX 104U             /* buffer sizes tried: 0-103; the longest record is 94 (22 + 2 + 70) */
_Static_assert(WS_FI_COUNT == SPEC_FIELDS, "the encoder's catalog has the specification's 34 indexes");

/* The field catalog v2 (design section 5.2 over docs/protocol-design.md section 5.3), written out
 * again on purpose. A check with the encoder's own ws_obs_code_ok() would share any bug in it (a
 * planted off-by-one went unnoticed that way). Every current (12, 27, 30, 33) is offset binary, codes
 * 0-65534 (-32768 to +32766 mA); every rail voltage (11, 26, 28, 29, 32) 0-65534 mV; 31 is EXT. */
static const uint32_t spec_max[SPEC_FIELDS] = {16500, 10000, 8000, 750, 750, 359, 16777214, 250, 2000,
 1048575, 0xFFFFFFFFU, 65534, 65534, 16777214, 16777214, 16777214, 16777214, 100, 3, 16500, 10000,
 16500, 16500, 10000, 10000, 60, 65534, 65534, 65534, 65534, 65534, 0, 65534, 65534};
static const uint8_t spec_width[SPEC_FIELDS] = {2, 2, 2, 2, 2, 2, 3, 1, 2, 3, 4, 2, 2, 3, 3, 3, 3, 1, 1, 2, 2,
 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 0, 2, 2};

static uint32_t spec_invalid(unsigned i)
{
 return spec_width[i] >= SPEC_U32 ? UINT32_MAX : ((uint32_t)1 << (CHAR_BIT * spec_width[i])) - 1U;
}

static int spec_code_ok(unsigned i, uint32_t c)
{
 if (c <= spec_max[i]) return 1;
 if (i == SPEC_QUALIFIERS) return 0;
 return c == spec_invalid(i) || (i == SPEC_WIND_DIR && c == SPEC_WIND_CALM);
}

/* A logical mask is canonical when it names at least one field and only catalog fields (never EXT,
 * never a reserved index 34-63). */
static int spec_mask_ok(uint64_t m)
{
 if (m == 0U) return 0;
 for (unsigned i = 0; i < SPEC_MASK_BITS; i++)
  if ((m >> i & 1U) && (i >= SPEC_FIELDS || spec_width[i] == 0)) return 0;
 return 1;
}

static size_t spec_fields_len(uint64_t m)
{
 size_t len = 0;
 for (unsigned i = 0; i < SPEC_FIELDS; i++) if (m >> i & 1U) len += spec_width[i];
 return len;
}

static uint64_t be(const uint8_t *p, unsigned n)
{
 uint64_t v = 0;
 for (unsigned k = 0; k < n; k++) v = v << 8 | p[k];
 return v;
}

/* The length of a stored plaintext by the specification's EXT rules (design section 5.1), or -1. */
static int spec_plain_len(const uint8_t *plain, size_t avail)
{
 if (avail < SPEC_OBS_HEAD_LEN) return -1;
 uint32_t base = (uint32_t)be(plain + SPEC_OBS_BITMAP_AT, SPEC_U32);
 uint64_t mask = base & SPEC_BASE_FIELDS;
 size_t len = SPEC_OBS_HEAD_LEN;
 if (base & SPEC_OBS_EXT) {
  if (avail < SPEC_OBS_HEAD_LEN + SPEC_OBS_EXT_BYTES) return -1;
  uint64_t ext = be(plain + SPEC_OBS_EXT_AT, SPEC_OBS_EXT_BYTES);
  if (ext == 0U) return -1;   /* EXT with an empty extension bitmap */
  mask |= ext << SPEC_OBS_EXT_FIRST;
  len += SPEC_OBS_EXT_BYTES;
 }
 if (!spec_mask_ok(mask)) return -1;   /* no field, or a reserved extension bit (fields 34-47) */
 len += spec_fields_len(mask);
 return len <= avail ? (int)len : -1;
}

/* The encoded length of o in a cap-byte buffer by the specification, or -1. */
static int spec_encoded_len(const ws_obs_t *o, size_t cap)
{
 if (!spec_mask_ok(o->bitmap) || o->energy > WS_ENERGY_CRITICAL) return -1;
 for (unsigned i = 0; i < SPEC_FIELDS; i++)
  if ((o->bitmap >> i & 1U) && !spec_code_ok(i, o->code[i])) return -1;
 uint64_t wind = (uint64_t)1 << SPEC_WIND_SPEED | (uint64_t)1 << SPEC_WIND_DIR;
 if ((o->bitmap & wind) == wind && o->code[SPEC_WIND_SPEED] == spec_invalid(SPEC_WIND_SPEED) &&
     o->code[SPEC_WIND_DIR] != spec_invalid(SPEC_WIND_DIR)) return -1;   /* a direction needs a speed */
 size_t len = SPEC_OBS_HEAD_LEN + ((o->bitmap >> SPEC_OBS_EXT_FIRST) ? SPEC_OBS_EXT_BYTES : 0U) + spec_fields_len(o->bitmap);
 return len <= cap ? (int)len : -1;
}

static uint32_t take(const uint8_t **p, size_t *n, unsigned bytes)
{
 uint32_t v = 0;
 for (unsigned k = 0; k < bytes; k++) { v = v << 8 | (*n ? **p : 0); if (*n) { (*p)++; (*n)--; } }
 return v;
}

static void take_codes(ws_obs_t *o, const uint8_t **p, size_t *n)
{
 for (unsigned i = 0; i < SPEC_FIELDS; i++) {
  uint32_t sel = take(p, n, 1), raw = take(p, n, SPEC_U32);
  switch (sel & 3U) {
   case 0: o->code[i] = raw & spec_invalid(i); break;
   case 1: o->code[i] = spec_invalid(i); break;
   case 2: o->code[i] = (sel & 8U) ? spec_max[i] + (sel >> 4 & 1U) : raw % 101U; break;   /* the edge, or one past it */
   default: o->code[i] = (sel & 4U) ? SPEC_WIND_CALM : raw; break;
  }
 }
}

/* An accepted record: the header, the wire bitmap and its extension word, the fields in order. */
static void check_record(const ws_obs_t *o, const uint8_t *out, int got)
{
 const uint8_t *h = out; size_t hl = (size_t)got;
 FUZZ_CHECK(take(&h, &hl, SPEC_U32) == o->epoch && take(&h, &hl, SPEC_U32) == o->seq && take(&h, &hl, SPEC_U32) == o->utc &&
            take(&h, &hl, SPEC_U32) == o->uptime);
 uint8_t flags = out[SPEC_OBS_FLAGS_AT];
 FUZZ_CHECK((flags & SPEC_OBS_FLAG_UTC) == (o->utc != 0) && (flags >> SPEC_OBS_ENERGY_SHIFT) == o->energy &&
            out[SPEC_OBS_CAL_AT] == o->cal_rev);
 uint64_t ext = o->bitmap >> SPEC_OBS_EXT_FIRST;
 FUZZ_CHECK(be(out + SPEC_OBS_BITMAP_AT, SPEC_U32) == ((o->bitmap & SPEC_BASE_FIELDS) | (ext ? SPEC_OBS_EXT : 0U)));
 const uint8_t *q = out + SPEC_OBS_HEAD_LEN; size_t left = (size_t)got - SPEC_OBS_HEAD_LEN;
 if (ext) FUZZ_CHECK(take(&q, &left, SPEC_OBS_EXT_BYTES) == ext);
 for (unsigned i = 0; i < SPEC_FIELDS; i++)
  if (o->bitmap >> i & 1U) FUZZ_CHECK(take(&q, &left, spec_width[i]) == o->code[i]);
 FUZZ_CHECK(left == 0);
 FUZZ_CHECK((size_t)got == WS_OBS_PLAIN_LEN(o->bitmap));
 FUZZ_CHECK(ws_obs_plain_len(out, (size_t)got) == got && ws_obs_plain_len(out, (size_t)got - 1U) == -1);
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
 FUZZ_CHECK(ws_obs_plain_len(data, size) == spec_plain_len(data, size));   /* the raw bytes as a stored plaintext */
 const uint8_t *p = data; size_t n = size;
 ws_obs_t o; memset(&o, 0, sizeof o);
 o.epoch = take(&p, &n, SPEC_U32); o.seq = take(&p, &n, SPEC_U32); o.utc = take(&p, &n, SPEC_U32); o.uptime = take(&p, &n, SPEC_U32);
 o.energy = (uint8_t)take(&p, &n, 1); o.cal_rev = (uint8_t)take(&p, &n, 1);
 o.bitmap = take(&p, &n, SPEC_U32);   /* bit 31 passes through: EXT in a logical mask must be refused */
 o.bitmap |= (uint64_t)take(&p, &n, SPEC_U16) << SPEC_OBS_EXT_FIRST;
 o.bitmap |= (uint64_t)take(&p, &n, SPEC_U16) << (SPEC_OBS_EXT_FIRST + CHAR_BIT * SPEC_U16);   /* 48-63: never fields */
 size_t cap = take(&p, &n, 1) % CAP_MAX;   /* below and above the longest record */
 take_codes(&o, &p, &n);
 uint8_t out[CAP_MAX];
 int got = ws_obs_encode(&o, out, cap);
 FUZZ_CHECK(got == spec_encoded_len(&o, cap));
 if (got >= 0) check_record(&o, out, got);
 return 0;
}
