#include "ws_obs.h"

/* Catalog v1 (docs/protocol-draft5-design.md section 5.3): bytes and highest in-range code.
 * INVALID is the field's all-ones value, except qualifiers, which have none. */
static const struct { uint8_t width; uint32_t max; } field[WS_FI_COUNT] = {
 {2, 16500},       /* temperature_c   0.01 C, offset -40.00 */
 {2, 10000},       /* humidity_pct    0.01 % */
 {2, 8000},        /* pressure_hpa    0.1 hPa, offset 300.0 */
 {2, 750},         /* wind_speed_ms   0.1 m/s */
 {2, 750},         /* wind_gust_ms    0.1 m/s */
 {2, 359},         /* wind_dir_deg    1 deg, plus CALM */
 {3, 16777214},    /* rain_tips       since boot */
 {1, 250},         /* uv_index        0.1 UVI */
 {2, 2000},        /* irradiance_wm2 */
 {3, 1048575},     /* uva_raw         LTR390 counts (20 bit) */
 {4, 0xFFFFFFFFU}, /* qualifiers      2 bits per field 0-15, no INVALID */
 {2, 65534},       /* batt_mv */
 {2, 65534},       /* batt_current_ma 0.1 mA, offset binary */
 {3, 16777214},    /* energy_in_mwh */
 {3, 16777214},    /* energy_out_mwh */
 {3, 16777214},    /* charge_in_mah */
 {3, 16777214},    /* charge_out_mah */
 {1, 100},         /* soc_gauge_pct */
 {1, 3},           /* charger_pins    bit 0 PGOOD, bit 1 CHG */
 {2, 16500},       /* enclosure_temp_c */
 {2, 10000},       /* enclosure_rh_pct */
};

unsigned ws_obs_width(unsigned i) { return i < WS_FI_COUNT ? field[i].width : 0; }

uint32_t ws_obs_invalid(unsigned i)
{
 if (i >= WS_FI_COUNT || i == WS_FI_QUALIFIERS) return 0;
 return field[i].width == 4 ? 0xFFFFFFFFU : ((uint32_t)1 << (8U * field[i].width)) - 1U;
}

int ws_obs_code_ok(unsigned i, uint32_t code)
{
 if (i >= WS_FI_COUNT) return 0;
 if (code <= field[i].max) return 1;
 if (i == WS_FI_QUALIFIERS) return 0;
 if (code == ws_obs_invalid(i)) return 1;
 return i == WS_FI_WIND_DIR_DEG && code == WS_WIND_DIR_CALM;
}

static void put(uint8_t *p, uint32_t v, unsigned n)
{
 for (unsigned k = 0; k < n; k++) p[k] = (uint8_t)(v >> (8U * (n - 1U - k)));
}

int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap)
{
 if (!o || !out || !o->bitmap || (o->bitmap & ~WS_FIELDS_DEFINED) || o->energy > WS_ENERGY_CRITICAL) return -1;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if (!(o->bitmap & WS_F(i))) continue;
  if (!ws_obs_code_ok(i, o->code[i])) return -1;
  len += field[i].width;
 }
 /* A direction needs a speed: INVALID speed forces INVALID direction (section 5.4). */
 if ((o->bitmap & WS_F(WS_FI_WIND_DIR_DEG)) && (o->bitmap & WS_F(WS_FI_WIND_SPEED_MS)) &&
     o->code[WS_FI_WIND_SPEED_MS] == ws_obs_invalid(WS_FI_WIND_SPEED_MS) &&
     o->code[WS_FI_WIND_DIR_DEG] != ws_obs_invalid(WS_FI_WIND_DIR_DEG)) return -1;
 if (len > cap) return -1;
 put(out, o->epoch, 4); put(out + 4, o->seq, 4); put(out + 8, o->utc, 4); put(out + 12, o->uptime, 4);
 out[16] = (uint8_t)((o->utc != 0) | (o->energy << 1));
 out[17] = o->cal_rev;
 put(out + 18, o->bitmap, 4);
 uint8_t *p = out + WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) {
  if (!(o->bitmap & WS_F(i))) continue;
  put(p, o->code[i], field[i].width);
  p += field[i].width;
 }
 return (int)len;
}

int ws_obs_plain_len(const uint8_t *plain, size_t avail)
{
 if (!plain || avail < WS_OBS_HEAD_LEN) return -1;
 uint32_t bitmap = (uint32_t)plain[18] << 24 | (uint32_t)plain[19] << 16 | (uint32_t)plain[20] << 8 | plain[21];
 if (!bitmap || (bitmap & ~WS_FIELDS_DEFINED)) return -1;
 size_t len = WS_OBS_HEAD_LEN;
 for (unsigned i = 0; i < WS_FI_COUNT; i++) if (bitmap & WS_F(i)) len += field[i].width;
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
