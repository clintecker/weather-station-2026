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

unsigned ws_obs_width(unsigned i) { return i < WS_FI_COUNT ? width[i] : 0; }

uint32_t ws_obs_invalid(unsigned i)
{
 if (i >= WS_FI_COUNT || i == WS_FI_QUALIFIERS) return 0;
 return width[i] == 4 ? 0xFFFFFFFFU : ((uint32_t)1 << (8U * width[i])) - 1U;
}

int ws_obs_code_ok(unsigned i, uint32_t code)
{
 if (i >= WS_FI_COUNT) return 0;
 if (code <= code_max[i]) return 1;
 if (i == WS_FI_QUALIFIERS) return 0;
 if (code == ws_obs_invalid(i)) return 1;
 return i == WS_FI_WIND_DIR_DEG && code == WS_WIND_DIR_CALM;
}

int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap)
{
 if (!o || !out || !o->bitmap || (o->bitmap & ~WS_FIELDS_DEFINED) || o->energy > WS_ENERGY_CRITICAL) return -1;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if (!(o->bitmap & WS_F(i))) continue;
  if (!ws_obs_code_ok(i, o->code[i])) return -1;
  len += width[i];
 }
 /* A direction needs a speed: INVALID speed forces INVALID direction (section 5.4). */
 if ((o->bitmap & WS_F(WS_FI_WIND_DIR_DEG)) && (o->bitmap & WS_F(WS_FI_WIND_SPEED_MS)) &&
     o->code[WS_FI_WIND_SPEED_MS] == ws_obs_invalid(WS_FI_WIND_SPEED_MS) &&
     o->code[WS_FI_WIND_DIR_DEG] != ws_obs_invalid(WS_FI_WIND_DIR_DEG)) return -1;
 if (len > cap) return -1;
 ws_put_be32(out, o->epoch); ws_put_be32(out + 4, o->seq); ws_put_be32(out + 8, o->utc); ws_put_be32(out + 12, o->uptime);
 out[16] = (uint8_t)((o->utc != 0) | (o->energy << 1));
 out[17] = o->cal_rev;
 ws_put_be32(out + 18, o->bitmap);
 uint8_t *p = out + WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if (!(o->bitmap & WS_F(i))) continue;
  ws_put_be(p, o->code[i], width[i]);
  p += width[i];
 }
 return (int)len;
}

int ws_obs_plain_len(const uint8_t *plain, size_t avail)
{
 if (!plain || avail < WS_OBS_HEAD_LEN) return -1;
 uint32_t bitmap = ws_get_be32(plain + 18);
 if (!bitmap || (bitmap & ~WS_FIELDS_DEFINED)) return -1;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (bitmap & WS_F(i)) len += width[i];
 return len <= avail ? (int)len : -1;
}

uint32_t ws_code_temp_centi(int32_t centi_c)
{
 if (centi_c < -4000 || centi_c > 12500) return ws_obs_invalid(WS_FI_TEMPERATURE_C);
 return (uint32_t)(centi_c + 4000);
}

uint32_t ws_code_rh_centi(int32_t centi_pct)
{
 if (centi_pct < 0) return 0;
 return centi_pct > 10000 ? 10000U : (uint32_t)centi_pct;
}
