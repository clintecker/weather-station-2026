/* Power register and ADC conversions: see power_regs.h for the parts, their registers and units. */
#include "power_regs.h"
#include "ws_round.h"

#define INA228_MANUFACTURER 0x5449U   /* "TI" */
#define INA228_DEVICE 0x228U
#define INA228_SHUNT_CAL_MAX 0x7FFFU  /* SHUNT_CAL is bits 14..0 */
#define INA228_CAL_NUM 131072         /* 13107.2 x 10^6 x 10^-6 (uA) x 10^-6 (uohm) x 10^7 */
#define INA228_CAL_DEN 10000000
#define INA228_VSHUNT_PA 312500       /* VSHUNT pV a count: nV x 1000 / uohm = uA */
#define MAX17048_VERSION 0x0010U
#define MAX17048_VERSION_MASK 0xFFF0U
#define MAX17048_SOC_NONE 0xFFFFU
#define UV_PER_MV 1000
#define PPM 1000000
#define UV_PPM_PER_MV 1000000000   /* uV x ppm in a mV */

static int32_t sat32(int64_t v)
{
  if (v > INT32_MAX) return INT32_MAX;
  if (v < INT32_MIN) return INT32_MIN;
  return (int32_t)v;
}

/* num / den rounded half up, for num >= 0 and den > 0, at any int64 num: from the remainder, so no
   2 num + den that could overflow (ws_div_round needs |num| below 2^62). */
static int64_t div_half_up(int64_t num, int64_t den)
{
  int64_t r = num % den;
  return num / den + (r >= den - r ? 1 : 0);
}

/* The INA228's 20-bit two's-complement count from the top 20 of 24 bits (the low 4 are reserved). */
int32_t ina228_count(uint32_t raw24)
{
  int32_t count = (int32_t)((raw24 >> 4) & 0xFFFFFU);
  return count >= 0x80000 ? count - 0x100000 : count;
}

uint32_t ina228_raw24(int32_t count) { return ((uint32_t)count & 0xFFFFFU) << 4; }

int32_t ina228_vshunt_nv(uint32_t raw24) { return (int32_t)((int64_t)ina228_count(raw24) * 3125 / 10); }

int32_t ina228_vbus_uv(uint32_t raw24) { return (int32_t)((int64_t)ina228_count(raw24) * 3125 / 16); }

int32_t ina228_current_ua(uint32_t vshunt_raw24, int32_t shunt_uohm)
{
  if (shunt_uohm <= 0) return 0;
  return sat32((int64_t)ina228_count(vshunt_raw24) * INA228_VSHUNT_PA / shunt_uohm);
}

uint16_t ina228_shunt_cal(uint32_t shunt_uohm, uint32_t current_lsb_ua)
{
  uint64_t lsb_r = (uint64_t)current_lsb_ua * shunt_uohm;   /* below 2^64: two 32-bit factors */
  if (lsb_r > UINT32_MAX) return 0;                          /* far past the 15-bit field */
  uint64_t cal = INA228_CAL_NUM * lsb_r / INA228_CAL_DEN;    /* below 2^49 */
  return cal > INA228_SHUNT_CAL_MAX ? 0 : (uint16_t)cal;
}

int64_t ina228_charge_uas(int64_t delta_counts, uint32_t current_lsb_ua) { return delta_counts * current_lsb_ua; }

int32_t ina228_dietemp_mc(uint16_t raw16) { return (int32_t)(int16_t)raw16 * 125 / 16; }

int ina228_ids_match(uint16_t manufacturer, uint16_t device)
{
  return manufacturer == INA228_MANUFACTURER && (device >> 4) == INA228_DEVICE;
}

int32_t max17048_vcell_uv(uint16_t raw16) { return (int32_t)raw16 * 625 / 8; }

uint16_t max17048_soc_256(uint16_t raw16) { return raw16 == MAX17048_SOC_NONE ? MAX17048_SOC_NONE - 1U : raw16; }

int32_t max17048_soc_mpct(uint16_t raw16) { return (int32_t)raw16 * 1000 / 256; }

int32_t max17048_crate_mpct_h(uint16_t raw16) { return (int32_t)(int16_t)raw16 * 208; }

int max17048_version_match(uint16_t version) { return (version & MAX17048_VERSION_MASK) == MAX17048_VERSION; }

uint32_t adc_vdda_mv(uint16_t vrefint_raw, uint16_t vrefint_cal)
{
  if (vrefint_raw == 0) return 0;
  return POWER_VREFINT_CAL_MV * vrefint_cal / vrefint_raw;
}

int32_t adc_pin_uv(uint16_t raw12, uint32_t vdda_mv)
{
  uint64_t raw = raw12 > POWER_ADC_FULL_SCALE ? POWER_ADC_FULL_SCALE : raw12;
  return sat32((int64_t)(raw * vdda_mv * UV_PER_MV / POWER_ADC_FULL_SCALE));
}

int adc_clipped(uint16_t raw12) { return raw12 >= POWER_ADC_CLIP_RAW; }

int32_t iset_charge_ua(int32_t v_iset_uv, uint32_t r_iset_ohm)
{
  if (r_iset_ohm == 0 || v_iset_uv <= 0) return 0;
  return sat32((int64_t)v_iset_uv * POWER_ISET_RATIO / r_iset_ohm);
}

int32_t divider_mv(int32_t pin_uv, uint32_t ratio)
{
  if (pin_uv <= 0) return 0;
  return sat32(ws_div_round((int64_t)pin_uv * ratio, UV_PER_MV));
}

/* Positive tap times a ratio in ppm, over den (1e6 for uV, 1e9 for mV); 0 for a ratio of 0 or a tap <= 0.
   (2^31 - 1) x (2^32 - 1) is below 2^63, so the product fits int64 for every argument. */
static int32_t scale_ppm(int32_t pin_uv, uint32_t ratio_ppm, int64_t den)
{
  if (ratio_ppm == 0 || pin_uv <= 0) return 0;
  return sat32(div_half_up((int64_t)pin_uv * ratio_ppm, den));
}

int32_t divider_mv_ppm(int32_t pin_uv, uint32_t ratio_ppm) { return scale_ppm(pin_uv, ratio_ppm, UV_PPM_PER_MV); }

int32_t divider_uv_ppm(int32_t pin_uv, uint32_t ratio_ppm) { return scale_ppm(pin_uv, ratio_ppm, PPM); }

int32_t unscale_ppm(int32_t uv, uint32_t gain_ppm)
{
  if (gain_ppm == 0 || uv <= 0) return 0;
  return sat32(div_half_up((int64_t)uv * PPM, gain_ppm));
}
