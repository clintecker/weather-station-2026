#ifndef WS_OBS_H
#define WS_OBS_H
#include <stddef.h>
#include <stdint.h>
/* Draft-5 observation plaintext (docs/protocol-draft5-design.md section 5). No hardware
 * dependencies: the TX firmware, the host tests and the fuzzers run the same code. The Python
 * twin of this table is ws0/fields.py; tests/test_obs.py checks that the two agree. */

#define WS_OBS_HEAD_LEN 22   /* epoch, sequence, UTC, uptime (4 each), flags, calibration, bitmap (4) */

/* Field catalog v1: index = bit in the field bitmap. */
enum {
 WS_FI_TEMPERATURE_C, WS_FI_HUMIDITY_PCT, WS_FI_PRESSURE_HPA, WS_FI_WIND_SPEED_MS,
 WS_FI_WIND_GUST_MS, WS_FI_WIND_DIR_DEG, WS_FI_RAIN_TIPS, WS_FI_UV_INDEX, WS_FI_IRRADIANCE_WM2,
 WS_FI_UVA_RAW, WS_FI_QUALIFIERS, WS_FI_BATT_MV, WS_FI_BATT_CURRENT_MA, WS_FI_ENERGY_IN_MWH,
 WS_FI_ENERGY_OUT_MWH, WS_FI_CHARGE_IN_MAH, WS_FI_CHARGE_OUT_MAH, WS_FI_SOC_GAUGE_PCT,
 WS_FI_CHARGER_PINS, WS_FI_ENCLOSURE_TEMP_C, WS_FI_ENCLOSURE_RH_PCT,
 /* 15-s sampling summary of the minute (PRD section 9: coverage and extrema) */
 WS_FI_TEMPERATURE_MIN_C, WS_FI_TEMPERATURE_MAX_C, WS_FI_HUMIDITY_MIN_PCT, WS_FI_HUMIDITY_MAX_PCT,
 WS_FI_TH_SAMPLES, WS_FI_COUNT
};
#define WS_F(i) ((uint32_t)1 << (i))
#define WS_F_TEMPERATURE_C WS_F(WS_FI_TEMPERATURE_C)
#define WS_F_HUMIDITY_PCT  WS_F(WS_FI_HUMIDITY_PCT)
#define WS_F_TH_SUMMARY (WS_F(WS_FI_TEMPERATURE_MIN_C) | WS_F(WS_FI_TEMPERATURE_MAX_C) | \
                         WS_F(WS_FI_HUMIDITY_MIN_PCT) | WS_F(WS_FI_HUMIDITY_MAX_PCT) | WS_F(WS_FI_TH_SAMPLES))
#define WS_FIELDS_DEFINED  (WS_F(WS_FI_COUNT) - 1U)

/* Bytes of each field, as a constant expression so builds can size buffers from a bitmap. */
#define WS_FW(m, i, w) ((((m) >> (i)) & 1U) * (w))
#define WS_OBS_FIELDS_LEN(m) (WS_FW(m,0,2) + WS_FW(m,1,2) + WS_FW(m,2,2) + WS_FW(m,3,2) + \
 WS_FW(m,4,2) + WS_FW(m,5,2) + WS_FW(m,6,3) + WS_FW(m,7,1) + WS_FW(m,8,2) + WS_FW(m,9,3) + \
 WS_FW(m,10,4) + WS_FW(m,11,2) + WS_FW(m,12,2) + WS_FW(m,13,3) + WS_FW(m,14,3) + WS_FW(m,15,3) + \
 WS_FW(m,16,3) + WS_FW(m,17,1) + WS_FW(m,18,1) + WS_FW(m,19,2) + WS_FW(m,20,2) + WS_FW(m,21,2) + \
 WS_FW(m,22,2) + WS_FW(m,23,2) + WS_FW(m,24,2) + WS_FW(m,25,1))
#define WS_OBS_PLAIN_LEN(m) (WS_OBS_HEAD_LEN + WS_OBS_FIELDS_LEN(m))
#define WS_OBS_PLAIN_ALL WS_OBS_PLAIN_LEN(WS_FIELDS_DEFINED)

#define WS_WIND_DIR_CALM 0xFFFEU

/* Energy state (section 5.2): the firmware's energy_t numbering. */
enum { WS_ENERGY_SURPLUS, WS_ENERGY_NORMAL, WS_ENERGY_CONSERVE, WS_ENERGY_CRITICAL };

typedef struct {
 uint32_t epoch, seq, utc, uptime;   /* utc 0 = time unknown */
 uint8_t energy, cal_rev;
 uint32_t bitmap;                    /* which code[] entries are sent */
 uint32_t code[WS_FI_COUNT];         /* catalog codes, INVALID = the field's all-ones value */
} ws_obs_t;

/* Width in bytes and INVALID code of field i (0 if i is not a catalog field). */
unsigned ws_obs_width(unsigned i);
uint32_t ws_obs_invalid(unsigned i);
/* 1 if code is a legal value of field i: within range, INVALID, or a special code. */
int ws_obs_code_ok(unsigned i, uint32_t code);
/* Serialize. Returns the plaintext length, or -1 if the record is not canonical (empty or
 * reserved bitmap, energy > 3, a code that ws_obs_code_ok rejects, wind direction valid with an
 * INVALID speed) or does not fit in cap bytes. */
int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap);

/* Length of a stored plaintext from its own field bitmap: WS_OBS_HEAD_LEN + the present widths, or
 * -1 if avail is shorter than the header or that length, or the bitmap is empty or reserved. */
int ws_obs_plain_len(const uint8_t *plain, size_t avail);

/* Physical value -> code (section 5.3). Out of range gives INVALID; RH is clamped to 0-100 %. */
uint32_t ws_code_temp_centi(int32_t centi_c);
uint32_t ws_code_rh_centi(int32_t centi_pct);
#endif
