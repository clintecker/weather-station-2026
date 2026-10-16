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

unsigned ws_obs_width(unsigned i) { return i < WS_FI_COUNT ? width[i] : 0; }

uint32_t ws_obs_invalid(unsigned i)
{
 if (i >= WS_FI_COUNT || i == WS_FI_QUALIFIERS) return 0;
 return width[i] >= sizeof(uint32_t) ? UINT32_MAX : ((uint32_t)1 << (CHAR_BIT * width[i])) - 1U;
}

int ws_obs_code_ok(unsigned i, uint32_t code)
{
 if (i >= WS_FI_COUNT) return 0;
 if (code <= code_max[i]) return 1;
 if (i == WS_FI_QUALIFIERS) return 0;
 if (code == ws_obs_invalid(i)) return 1;
 return i == WS_FI_WIND_DIR_DEG && code == WS_WIND_DIR_CALM;
}

/* A direction needs a speed: INVALID speed forces INVALID direction (section 5.4). */
static int wind_ok(const ws_obs_t *o)
{
 uint32_t both = WS_F(WS_FI_WIND_DIR_DEG) | WS_F(WS_FI_WIND_SPEED_MS);
 if ((o->bitmap & both) != both || o->code[WS_FI_WIND_SPEED_MS] != ws_obs_invalid(WS_FI_WIND_SPEED_MS)) return 1;
 return o->code[WS_FI_WIND_DIR_DEG] == ws_obs_invalid(WS_FI_WIND_DIR_DEG);
}

/* The encoded length of a valid observation, or -1. */
static int obs_len(const ws_obs_t *o)
{
 if (!o->bitmap || (o->bitmap & ~WS_FIELDS_DEFINED) || o->energy > WS_ENERGY_CRITICAL) return -1;
 int len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if (!(o->bitmap & WS_F(i))) continue;
  if (!ws_obs_code_ok(i, o->code[i])) return -1;
  len += width[i];
 }
 return wind_ok(o) ? len : -1;
}

int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap)
{
 int len = o && out ? obs_len(o) : -1;
 if (len < 0 || (size_t)len > cap) return -1;
 uint8_t *p = ws_write_be32(out, o->epoch);
 p = ws_write_be32(p, o->seq);
 p = ws_write_be32(p, o->utc);
 p = ws_write_be32(p, o->uptime);
 p = ws_write_u8(p, (uint8_t)((o->utc != 0 ? WS_OBS_FLAG_UTC : 0U) | (unsigned)o->energy << WS_OBS_ENERGY_SHIFT));
 p = ws_write_u8(p, o->cal_rev);
 p = ws_write_be32(p, o->bitmap);
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (o->bitmap & WS_F(i)) p = ws_write_be(p, o->code[i], width[i]);
 return len;
}

int ws_obs_plain_len(const uint8_t *plain, size_t avail)
{
 if (!plain || avail < WS_OBS_HEAD_LEN) return -1;
 uint32_t bitmap = ws_get_be32(plain + WS_OBS_BITMAP_OFF);
 if (!bitmap || (bitmap & ~WS_FIELDS_DEFINED)) return -1;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (bitmap & WS_F(i)) len += width[i];
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
