#ifndef WS_OBS_H
#define WS_OBS_H
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include "ws_be.h"
/* Observation plaintext (docs/protocol-design.md section 5). No hardware
 * dependencies: the TX firmware, the host tests and the fuzzers run the same code. The Python
 * twin of this table is ws0/fields.py; tests/test_obs.py checks that the two agree. */

#define WS_OBS_EPOCH_LEN 4   /* the identity, (epoch, sequence), opens the plaintext */
#define WS_OBS_ID_LEN 8
/* Header: epoch, sequence, UTC, uptime (u32 each), flags, calibration revision (u8 each), bitmap
 * (u32). Flags: bit 0 = UTC known, bits 1-2 = energy state. Bitmap bits 0-30 are fields 0-30; bit 31
 * (EXT) announces the u16 extension bitmap at offset 22, whose bit j is field 32 + j (catalog v2,
 * docs/superpowers/specs/2026-10-29-power-telemetry-design.md section 5.1). */
#define WS_OBS_BITMAP_OFF 18
#define WS_OBS_HEAD_LEN (WS_OBS_BITMAP_OFF + 4)
#define WS_OBS_EXT_OFF WS_OBS_HEAD_LEN
#define WS_OBS_EXT_LEN 2
#define WS_OBS_FLAG_UTC 0x01U
#define WS_OBS_ENERGY_SHIFT 1
/* Sensor ranges in 0.01 units (SHT45: -40.00 to 125.00 C; RH 0 to 100.00 %). */
#define WS_TEMP_MIN_CENTI (-4000)
#define WS_TEMP_MAX_CENTI 12500
#define WS_RH_MAX_CENTI 10000
#define WS_TH_SAMPLES_MAX 60   /* 15-s samples in a minute's window, at most */
#define WS_TEMP_CODE_TOP (WS_TEMP_MAX_CENTI - WS_TEMP_MIN_CENTI)   /* code = centi C + 40.00 C */
/* The highest in-range code of a w-byte field whose all-ones value is INVALID. */
#define WS_CODE_TOP(w) ((1UL << (CHAR_BIT * (w))) - 2U)

/* A stored plaintext's identity. */
static inline uint32_t ws_obs_epoch(const uint8_t *plain) { return ws_get_be32(plain); }
static inline uint32_t ws_obs_seq(const uint8_t *plain) { return ws_get_be32(plain + WS_OBS_EPOCH_LEN); }

/* Field catalog v2: index = bit of the logical field mask (ws_obs_t.bitmap). Index 31 (EXT) is not a
 * field: it is the wire bit that announces the extension bitmap, width 0. Fields 32-47 travel in the
 * extension bitmap; 34-47 are reserved. Names say what is measured, never which part measures it. */
enum {
 WS_FI_TEMPERATURE_C, WS_FI_HUMIDITY_PCT, WS_FI_PRESSURE_HPA, WS_FI_WIND_SPEED_MS,
 WS_FI_WIND_GUST_MS, WS_FI_WIND_DIR_DEG, WS_FI_RAIN_TIPS, WS_FI_UV_INDEX, WS_FI_IRRADIANCE_WM2,
 WS_FI_UVA_RAW, WS_FI_QUALIFIERS, WS_FI_BATT_MV, WS_FI_BATT_CURRENT_MA, WS_FI_ENERGY_IN_MWH,
 WS_FI_ENERGY_OUT_MWH, WS_FI_CHARGE_IN_MAH, WS_FI_CHARGE_OUT_MAH, WS_FI_SOC_GAUGE_PCT,
 WS_FI_CHARGER_PINS, WS_FI_ENCLOSURE_TEMP_C, WS_FI_ENCLOSURE_RH_PCT,
 /* 15-s sampling summary of the minute: coverage and extrema (product spec, sampling section) */
 WS_FI_TEMPERATURE_MIN_C, WS_FI_TEMPERATURE_MAX_C, WS_FI_HUMIDITY_MIN_PCT, WS_FI_HUMIDITY_MAX_PCT,
 WS_FI_TH_SAMPLES,
 /* Power rails (catalog v2, design section 5.2) */
 WS_FI_LOAD_MV, WS_FI_LOAD_CURRENT_MA, WS_FI_CHARGER_INPUT_MV, WS_FI_SOLAR_MV, WS_FI_SOLAR_CURRENT_MA,
 WS_FI_EXT,   /* 31: not a field, the wire's extension-bitmap bit */
 WS_FI_USB_MV, WS_FI_USB_CURRENT_MA, WS_FI_COUNT
};
_Static_assert(WS_FI_EXT == 31, "EXT is bitmap bit 31");
_Static_assert(WS_FI_COUNT <= 48, "the extension bitmap holds fields 32-47");
#define WS_F(i) ((uint64_t)1 << (i))
#define WS_F_TEMPERATURE_C WS_F(WS_FI_TEMPERATURE_C)
#define WS_F_HUMIDITY_PCT  WS_F(WS_FI_HUMIDITY_PCT)
#define WS_F_EXT           WS_F(WS_FI_EXT)
#define WS_FIELDS_DEFINED  ((WS_F(WS_FI_COUNT) - 1U) & ~WS_F_EXT)
/* Current code: 1 mA, offset binary, + per the rail's sign (design section 3.1). */
#define WS_CURRENT_OFFSET_MA 32768

/* Catalog v2 (docs/protocol-design.md section 5.3; design 2026-10-29 section 5.2), the only copy of
 * each field's width in bytes and highest in-range code: ws_obs.c builds its tables from it and
 * WS_OBS_FIELDS_LEN its constant-expression lengths. INVALID is the field's all-ones value, except
 * qualifiers, which have none, and EXT, which is not a field. Every current is 2 bytes, 1 mA, offset
 * binary (code = I + 32768), range -32768 to +32766 mA; every rail voltage 2 bytes, 1 mV.
 * X(a, index, width, max); a is passed through to X. */
#define WS_OBS_CATALOG(X, a) \
 X(a, WS_FI_TEMPERATURE_C,     2, WS_TEMP_CODE_TOP)     /* 0.01 C, offset -40.00 */ \
 X(a, WS_FI_HUMIDITY_PCT,      2, WS_RH_MAX_CENTI)      /* 0.01 % */ \
 X(a, WS_FI_PRESSURE_HPA,      2, 8000)                 /* 0.1 hPa, offset 300.0 */ \
 X(a, WS_FI_WIND_SPEED_MS,     2, 750)                  /* 0.1 m/s */ \
 X(a, WS_FI_WIND_GUST_MS,      2, 750)                  /* 0.1 m/s */ \
 X(a, WS_FI_WIND_DIR_DEG,      2, 359)                  /* 1 deg, plus CALM */ \
 X(a, WS_FI_RAIN_TIPS,         3, WS_CODE_TOP(3))       /* since boot */ \
 X(a, WS_FI_UV_INDEX,          1, 250)                  /* 0.1 UVI */ \
 X(a, WS_FI_IRRADIANCE_WM2,    2, 2000)                 \
 X(a, WS_FI_UVA_RAW,           3, (1UL << 20) - 1U)     /* LTR390 counts (20 bit) */ \
 X(a, WS_FI_QUALIFIERS,        4, UINT32_MAX)           /* 2 bits per field 0-15, no INVALID */ \
 X(a, WS_FI_BATT_MV,           2, WS_CODE_TOP(2))       /* 1 mV, battery terminal (cell) voltage */ \
 X(a, WS_FI_BATT_CURRENT_MA,   2, WS_CODE_TOP(2))       /* 1 mA, offset binary (code = I + 32768), + into the cell, range -32768..+32766 mA */ \
 X(a, WS_FI_ENERGY_IN_MWH,     3, WS_CODE_TOP(3))       /* battery-terminal energy in, since boot; INVALID in a minute without a fresh battery voltage */ \
 X(a, WS_FI_ENERGY_OUT_MWH,    3, WS_CODE_TOP(3))       /* battery-terminal energy out, as 13 */ \
 X(a, WS_FI_CHARGE_IN_MAH,     3, WS_CODE_TOP(3))       /* battery-terminal charge in (+ into the cell), since boot */ \
 X(a, WS_FI_CHARGE_OUT_MAH,    3, WS_CODE_TOP(3))       /* battery-terminal charge out, since boot */ \
 X(a, WS_FI_SOC_GAUGE_PCT,     1, 100)                  /* retired: version 6 builds do not send it (health report) */ \
 X(a, WS_FI_CHARGER_PINS,      1, 3)                    /* retired: bit 0 PGOOD, bit 1 CHG; the health report carries charger status */ \
 X(a, WS_FI_ENCLOSURE_TEMP_C,  2, WS_TEMP_CODE_TOP)     \
 X(a, WS_FI_ENCLOSURE_RH_PCT,  2, WS_RH_MAX_CENTI)      \
 X(a, WS_FI_TEMPERATURE_MIN_C, 2, WS_TEMP_CODE_TOP)     /* lowest valid 15-s sample of the minute */ \
 X(a, WS_FI_TEMPERATURE_MAX_C, 2, WS_TEMP_CODE_TOP)     \
 X(a, WS_FI_HUMIDITY_MIN_PCT,  2, WS_RH_MAX_CENTI)      \
 X(a, WS_FI_HUMIDITY_MAX_PCT,  2, WS_RH_MAX_CENTI)      \
 X(a, WS_FI_TH_SAMPLES,        1, WS_TH_SAMPLES_MAX)    /* valid temperature/humidity samples behind the minute's values */ \
 X(a, WS_FI_LOAD_MV,           2, WS_CODE_TOP(2))       /* 1 mV, load (system rail) voltage */ \
 X(a, WS_FI_LOAD_CURRENT_MA,   2, WS_CODE_TOP(2))       /* 1 mA offset binary, + into the load */ \
 X(a, WS_FI_CHARGER_INPUT_MV,  2, WS_CODE_TOP(2))       /* 1 mV, charger input after the sources join; source not identified */ \
 X(a, WS_FI_SOLAR_MV,          2, WS_CODE_TOP(2))       /* 1 mV, solar input upstream of the join */ \
 X(a, WS_FI_SOLAR_CURRENT_MA,  2, WS_CODE_TOP(2))       /* 1 mA offset binary, + into the station */ \
 X(a, WS_FI_EXT,               0, 0)                    /* not a field: width 0, never in a mask */ \
 X(a, WS_FI_USB_MV,            2, WS_CODE_TOP(2))       /* 1 mV, USB-C input upstream of the join */ \
 X(a, WS_FI_USB_CURRENT_MA,    2, WS_CODE_TOP(2))       /* 1 mA offset binary, + into the station */

/* Bytes of the fields in logical mask m, as a constant expression so builds can size buffers from it. */
#define WS_OBS_FW_(m, i, w, max) + ((unsigned)(((uint64_t)(m) >> (i)) & 1U) * (w))
#define WS_OBS_FIELDS_LEN(m) (0U WS_OBS_CATALOG(WS_OBS_FW_, m))
/* The extension word is on the wire when any field 32-47 is present. */
#define WS_OBS_EXT_BYTES(m) (((uint64_t)(m) >> 32) != 0U ? (unsigned)WS_OBS_EXT_LEN : 0U)
#define WS_OBS_PLAIN_LEN(m) (WS_OBS_HEAD_LEN + WS_OBS_EXT_BYTES(m) + WS_OBS_FIELDS_LEN(m))
#define WS_OBS_PLAIN_ALL WS_OBS_PLAIN_LEN(WS_FIELDS_DEFINED)

#define WS_WIND_DIR_CALM 0xFFFEU

/* Energy state (section 5.2): the firmware's energy_t numbering. */
enum { WS_ENERGY_SURPLUS, WS_ENERGY_NORMAL, WS_ENERGY_CONSERVE, WS_ENERGY_CRITICAL };

typedef struct {
 uint32_t epoch, seq, utc, uptime;   /* utc 0 = time unknown */
 uint8_t energy, cal_rev;
 uint64_t bitmap;                    /* logical field mask: which code[] entries are sent (never bit 31) */
 uint32_t code[WS_FI_COUNT];         /* catalog codes, INVALID = the field's all-ones value */
} ws_obs_t;

/* Width in bytes and INVALID code of field i (0 if i is not a catalog field, EXT included). */
unsigned ws_obs_width(unsigned i);
uint32_t ws_obs_invalid(unsigned i);
/* 1 if code is a legal value of field i: within range, INVALID, or a special code. */
int ws_obs_code_ok(unsigned i, uint32_t code);
/* Serialize. Returns the plaintext length, or -1 if the record is not canonical (empty or
 * reserved mask, EXT in the mask, energy > 3, a code that ws_obs_code_ok rejects, wind direction valid with an
 * INVALID speed) or does not fit in cap bytes. */
int ws_obs_encode(const ws_obs_t *o, uint8_t *out, size_t cap);

/* Length of a stored plaintext from its own field bitmap: WS_OBS_HEAD_LEN + the extension word if EXT
 * is set + the present widths, or -1 if avail is shorter than that, or the record is not canonical:
 * no field, EXT with an empty extension bitmap, or a reserved base or extension bit. */
int ws_obs_plain_len(const uint8_t *plain, size_t avail);

/* Physical value -> code (section 5.3). Out of range gives INVALID; RH is clamped to 0-100 %. */
uint32_t ws_code_temp_centi(int32_t centi_c);
uint32_t ws_code_rh_centi(int32_t centi_pct);
/* Current in mA -> the code of every current field (1 mA, offset binary): -32768 to +32766 mA, the
 * codec's own range (codes 0 to WS_CODE_TOP(2)); anything else gives INVALID (0xFFFF). */
uint32_t ws_code_current_ma(int32_t ma);
#endif
