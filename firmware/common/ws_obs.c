#include "ws_obs.h"
#include "ws_be.h"

/* Catalog tables from WS_OBS_CATALOG (ws_obs.h): two arrays, so no padding between the widths and
 * the 32-bit maxima. */
#define WIDTH_(a, i, w, max) [i] = (w),
#define MAX_(a, i, w, max) [i] = (max),
#define COUNT_(a, i, w, max) + 1
static const uint8_t width[WS_FI_COUNT] = { WS_OBS_CATALOG(WIDTH_, ) };
static const uint32_t code_max[WS_FI_COUNT] = { WS_OBS_CATALOG(MAX_, ) };
_Static_assert(0 WS_OBS_CATALOG(COUNT_, ) == WS_FI_COUNT, "one catalog entry per field index");
_Static_assert(WS_OBS_HEAD_LEN == 4 * sizeof(uint32_t) + 2 + sizeof(uint32_t), "header: four u32, flags, calibration, bitmap");
_Static_assert(WS_OBS_EXT_LEN == sizeof(uint16_t), "the extension bitmap is a u16: fields 32-47");

#define BASE_FIELDS (WS_F(WS_FI_EXT) - 1U)   /* fields 0-30: the wire bitmap's own bits */
#define EXT_SHIFT 32U                        /* extension bitmap bit j = field 32 + j */

unsigned ws_obs_width(unsigned i) { return i < WS_FI_COUNT ? width[i] : 0; }

uint32_t ws_obs_invalid(unsigned i)
{
 if (i >= WS_FI_COUNT || i == WS_FI_QUALIFIERS || width[i] == 0) return 0;
 return width[i] >= sizeof(uint32_t) ? UINT32_MAX : ((uint32_t)1 << (CHAR_BIT * width[i])) - 1U;
}

int ws_obs_code_ok(unsigned i, uint32_t code)
{
 if (i >= WS_FI_COUNT || width[i] == 0) return 0;
 if (code <= code_max[i]) return 1;
 if (i == WS_FI_QUALIFIERS) return 0;
 if (code == ws_obs_invalid(i)) return 1;
 return i == WS_FI_WIND_DIR_DEG && code == WS_WIND_DIR_CALM;
}

/* A logical mask is canonical when it names at least one field and only defined ones (never EXT). */
static int mask_ok(uint64_t mask) { return mask != 0U && (mask & ~WS_FIELDS_DEFINED) == 0U; }

/* Bytes after the 22-byte header for a canonical mask: the extension word if any field >= 32, then
 * the fields. */
static size_t body_len(uint64_t mask)
{
 size_t len = (mask >> EXT_SHIFT) != 0U ? WS_OBS_EXT_LEN : 0U;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (mask & WS_F(i)) len += width[i];
 return len;
}

/* A direction needs a speed: INVALID speed forces INVALID direction (section 5.4). */
static int wind_ok(const ws_obs_t *o)
{
 uint64_t both = WS_F(WS_FI_WIND_DIR_DEG) | WS_F(WS_FI_WIND_SPEED_MS);
 if ((o->bitmap & both) != both || o->code[WS_FI_WIND_SPEED_MS] != ws_obs_invalid(WS_FI_WIND_SPEED_MS)) return 1;
 return o->code[WS_FI_WIND_DIR_DEG] == ws_obs_invalid(WS_FI_WIND_DIR_DEG);
}

/* The encoded length of a valid observation, or -1. */
static int obs_len(const ws_obs_t *o)
{
 if (!mask_ok(o->bitmap) || o->energy > WS_ENERGY_CRITICAL) return -1;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if ((o->bitmap & WS_F(i)) && !ws_obs_code_ok(i, o->code[i])) return -1;
 }
 return wind_ok(o) ? (int)(WS_OBS_HEAD_LEN + body_len(o->bitmap)) : -1;
}

int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap)
{
 int len = o && out ? obs_len(o) : -1;
 if (len < 0 || (size_t)len > cap) return -1;
 uint16_t ext = (uint16_t)(o->bitmap >> EXT_SHIFT);
 uint8_t *p = ws_write_be32(out, o->epoch);
 p = ws_write_be32(p, o->seq);
 p = ws_write_be32(p, o->utc);
 p = ws_write_be32(p, o->uptime);
 p = ws_write_u8(p, (uint8_t)((o->utc != 0 ? WS_OBS_FLAG_UTC : 0U) | (unsigned)o->energy << WS_OBS_ENERGY_SHIFT));
 p = ws_write_u8(p, o->cal_rev);
 p = ws_write_be32(p, (uint32_t)(o->bitmap & BASE_FIELDS) | (ext != 0U ? (uint32_t)WS_F_EXT : 0U));
 if (ext != 0U) p = ws_write_be16(p, ext);
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (o->bitmap & WS_F(i)) p = ws_write_be(p, o->code[i], width[i]);
 return len;
}

/* The logical mask of a stored plaintext's header (avail >= WS_OBS_HEAD_LEN), or 0 if it is not
 * canonical: no field, EXT with a short record or an empty extension bitmap, or a reserved bit. */
static uint64_t plain_mask(const uint8_t *plain, size_t avail)
{
 uint32_t base = ws_get_be32(plain + WS_OBS_BITMAP_OFF);
 uint64_t mask = base & BASE_FIELDS;
 if (base & WS_F_EXT) {
  if (avail < WS_OBS_HEAD_LEN + WS_OBS_EXT_LEN) return 0;
  uint16_t ext = ws_get_be16(plain + WS_OBS_EXT_OFF);
  if (ext == 0U) return 0;
  mask |= (uint64_t)ext << EXT_SHIFT;
 }
 return mask_ok(mask) ? mask : 0U;
}

int ws_obs_plain_len(const uint8_t *plain, size_t avail)
{
 if (!plain || avail < WS_OBS_HEAD_LEN) return -1;
 uint64_t mask = plain_mask(plain, avail);
 if (mask == 0U) return -1;
 size_t len = WS_OBS_HEAD_LEN + body_len(mask);
 return len <= avail ? (int)len : -1;
}

uint32_t ws_code_temp_centi(int32_t centi_c)
{
 if (centi_c < WS_TEMP_MIN_CENTI || centi_c > WS_TEMP_MAX_CENTI) return ws_obs_invalid(WS_FI_TEMPERATURE_C);
 return (uint32_t)(centi_c - WS_TEMP_MIN_CENTI);
}

uint32_t ws_code_rh_centi(int32_t centi_pct)
{
 if (centi_pct < 0) return 0;
 return centi_pct > WS_RH_MAX_CENTI ? WS_RH_MAX_CENTI : (uint32_t)centi_pct;
}

uint32_t ws_code_current_ma(int32_t ma)
{
 int64_t code = (int64_t)ma + WS_CURRENT_OFFSET_MA;
 if (code < 0 || code > (int64_t)code_max[WS_FI_BATT_CURRENT_MA]) return ws_obs_invalid(WS_FI_BATT_CURRENT_MA);
 return (uint32_t)code;
}
