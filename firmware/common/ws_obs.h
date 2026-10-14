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

/* Catalog v1 (docs/protocol-draft5-design.md section 5.3), the only copy of each field's width in
 * bytes and highest in-range code: ws_obs.c builds its tables from it and WS_OBS_FIELDS_LEN its
 * constant-expression lengths. INVALID is the field's all-ones value, except qualifiers, which have
 * none. X(a, index, width, max); a is passed through to X. */
#define WS_OBS_CATALOG(X, a) \
 X(a, WS_FI_TEMPERATURE_C,     2, 16500)       /* 0.01 C, offset -40.00 */ \
 X(a, WS_FI_HUMIDITY_PCT,      2, 10000)       /* 0.01 % */ \
 X(a, WS_FI_PRESSURE_HPA,      2, 8000)        /* 0.1 hPa, offset 300.0 */ \
 X(a, WS_FI_WIND_SPEED_MS,     2, 750)         /* 0.1 m/s */ \
 X(a, WS_FI_WIND_GUST_MS,      2, 750)         /* 0.1 m/s */ \
 X(a, WS_FI_WIND_DIR_DEG,      2, 359)         /* 1 deg, plus CALM */ \
 X(a, WS_FI_RAIN_TIPS,         3, 16777214)    /* since boot */ \
 X(a, WS_FI_UV_INDEX,          1, 250)         /* 0.1 UVI */ \
 X(a, WS_FI_IRRADIANCE_WM2,    2, 2000) \
 X(a, WS_FI_UVA_RAW,           3, 1048575)     /* LTR390 counts (20 bit) */ \
 X(a, WS_FI_QUALIFIERS,        4, 0xFFFFFFFFU) /* 2 bits per field 0-15, no INVALID */ \
 X(a, WS_FI_BATT_MV,           2, 65534) \
 X(a, WS_FI_BATT_CURRENT_MA,   2, 65534)       /* 0.1 mA, offset binary */ \
 X(a, WS_FI_ENERGY_IN_MWH,     3, 16777214) \
 X(a, WS_FI_ENERGY_OUT_MWH,    3, 16777214) \
 X(a, WS_FI_CHARGE_IN_MAH,     3, 16777214) \
 X(a, WS_FI_CHARGE_OUT_MAH,    3, 16777214) \
 X(a, WS_FI_SOC_GAUGE_PCT,     1, 100) \
 X(a, WS_FI_CHARGER_PINS,      1, 3)           /* bit 0 PGOOD, bit 1 CHG */ \
 X(a, WS_FI_ENCLOSURE_TEMP_C,  2, 16500) \
 X(a, WS_FI_ENCLOSURE_RH_PCT,  2, 10000) \
 X(a, WS_FI_TEMPERATURE_MIN_C, 2, 16500)       /* lowest valid 15-s sample of the minute */ \
 X(a, WS_FI_TEMPERATURE_MAX_C, 2, 16500) \
 X(a, WS_FI_HUMIDITY_MIN_PCT,  2, 10000) \
 X(a, WS_FI_HUMIDITY_MAX_PCT,  2, 10000) \
 X(a, WS_FI_TH_SAMPLES,        1, 60)          /* valid T/RH samples behind the minute's values */

/* Bytes of the fields in bitmap m, as a constant expression so builds can size buffers from it. */
#define WS_OBS_FW_(m, i, w, max) + ((((m) >> (i)) & 1U) * (w))
#define WS_OBS_FIELDS_LEN(m) (0U WS_OBS_CATALOG(WS_OBS_FW_, m))
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
