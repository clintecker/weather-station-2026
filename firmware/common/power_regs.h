/* Power register and ADC conversions, shared by the node (firmware/stage0-node), the I2C bench tool
 * (firmware/i2cscan) and the bench telemetry link (firmware/benchlink): one copy, so the bench and the
 * field read a register the same way (docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * section 9.4). Pure C, integer arithmetic, no HAL: the host tests check every scale factor against
 * the datasheets (tests/test_i2cscan.py). Values come out in micro- or milli-units: the bench console's
 * printf (newlib nano) has no %f and no 64-bit conversions.
 *
 * No function asserts (WS_CHECK): a register image or an ADC count is input that can legitimately be
 * anything, so each function returns a defined value for every argument (docs/power-of-ten.md rule 5).
 * A zero divisor gives 0; a result past int32 saturates.
 *
 *   INA228 (TI SBOS904): VSHUNT 0x04 and VBUS 0x05 are 24-bit registers whose top 20 bits hold a
 *   two's-complement value, 312.5 nV and 195.3125 uV a count (ADCRANGE = 0, the reset value).
 *   CURRENT 0x07 and so CHARGE 0x0A count CURRENT_LSB (A) and CURRENT_LSB x 1 s (C).
 *   SHUNT_CAL 0x02 = 13107.2 x 10^6 x CURRENT_LSB x R_SHUNT (ADCRANGE = 0), a 15-bit
 *   field. DIETEMP 0x06 is 16-bit two's complement, 7.8125 m degC a count. MANUFACTURER_ID 0x3E =
 *   0x5449, DEVICE_ID 0x3F >> 4 = 0x228.
 *   MAX17048 (Analog Devices): VCELL 0x02 78.125 uV a count, SOC 0x04 1/256 % a count, CRATE 0x16
 *   two's complement 0.208 %/h a count, VERSION 0x08 & 0xFFF0 = 0x0010.
 *   STM32WL55 ADC (ST DS13293 Rev 5): VREFINT_CAL (0x1FFF75AA) is the VREFINT count taken at
 *   VDDA = VREF+ = 3.3 V (table 14), so VDDA = 3300 mV x VREFINT_CAL / VREFINT_raw; 12-bit full scale is
 *   VDDA at the pin.
 *   bq24074 (TI SLUS810): V_ISET = I_CHARGE / 400 x R_ISET (eq. 3), so I = 400 x V_ISET / R_ISET; the
 *   1/400 monitor ratio is +-10 % (section 9.3.5.1), plus R_ISET's own tolerance.
 *   BQ25798 (TI SLUSDV2C, rev. June 2026, section 7.5.1): a 16-bit register's high byte is at the lower
 *   address. VREG REG01 bits 10:0, 10 mV a count (table 7-15); ICHG REG03 bits 8:0, 10 mA a count
 *   (table 7-16); ITERM REG09 bits 4:0, 40 mA a count, 40-1000 mA (table 7-20); CELL REG0A bits 7:6, 0 = 1s (table 7-21); CHG_STAT REG1C bits 7:5 (table 7-37); IBUS
 *   REG31, IBAT REG33 two's complement, 1 mA (+ charging); VBUS REG35, VBAT REG3B, VSYS REG3D, 1 mV
 *   (tables 7-58 to 7-64); TS REG3F 0.0976563 % (= 100/1024 %) a count (table 7-65); TDIE REG41 two's
 *   complement, 0.5 degC (table 7-66); PN REG48 bits 5:3 = 3 for the BQ25798 (table 7-70). */
#ifndef POWER_REGS_H
#define POWER_REGS_H

#include <stdint.h>

#define POWER_ADC_FULL_SCALE 4095U     /* 12-bit result */
#define POWER_ADC_CLIP_RAW 4080U       /* 99.6 % of full scale: out of range (spec section 9.5) */
#define POWER_VREFINT_CAL_MV 3300U     /* VDDA at which VREFINT_CAL was taken (DS13293 table 14) */
#define POWER_ISET_RATIO 400           /* charge current / ISET current (SLUS810 eq. 3) */

/* INA228 */
int32_t ina228_count(uint32_t raw24);   /* the 20-bit two's-complement count of a 24-bit register */
uint32_t ina228_raw24(int32_t count);   /* and back: a register image of a count (an average) */
int32_t ina228_vshunt_nv(uint32_t raw24);
int32_t ina228_vbus_uv(uint32_t raw24);
/* The shunt voltage over the shunt (micro-ohm), in uA: + = into VIN+, out through VIN-. 0 for a shunt
   <= 0. From the count, so the nV rounding does not add to the current's. */
int32_t ina228_current_ua(uint32_t vshunt_raw24, int32_t shunt_uohm);
/* SHUNT_CAL for a CURRENT_LSB (uA) and a shunt (micro-ohm): 131072 x lsb x R / 10^7, truncated
   (10 uA, 15000 -> 1966; 20 uA -> 3932). 0 when an input is 0 or the value does not fit the 15-bit
   field: never write 0, it disables the current and charge results. */
uint16_t ina228_shunt_cal(uint32_t shunt_uohm, uint32_t current_lsb_ua);
/* A change of the CHARGE register (counts) in uA x s: one count is CURRENT_LSB x 1 s. CHARGE is 40
   bits, so |delta| < 2^41; with a CURRENT_LSB below 2^22 uA the product stays inside int64. */
int64_t ina228_charge_uas(int64_t delta_counts, uint32_t current_lsb_ua);
int32_t ina228_dietemp_mc(uint16_t raw16);
int ina228_ids_match(uint16_t manufacturer, uint16_t device);

/* MAX17048 */
int32_t max17048_vcell_uv(uint16_t raw16);
/* SOC as read, 1/256 %: can exceed 100 % near full. 0xFFFF (the health report's none code, and a
   stuck-high bus) becomes 0xFFFE. */
uint16_t max17048_soc_256(uint16_t raw16);
int32_t max17048_soc_mpct(uint16_t raw16);    /* milli-percent */
int32_t max17048_crate_mpct_h(uint16_t raw16); /* milli-percent an hour; negative while discharging */
int max17048_version_match(uint16_t version);

/* STM32WL ADC */
uint32_t adc_vdda_mv(uint16_t vrefint_raw, uint16_t vrefint_cal);   /* truncated, as the HAL; 0 for raw 0 */
int32_t adc_pin_uv(uint16_t raw12, uint32_t vdda_mv);               /* raw x VDDA / 4095, truncated */
/* With x16 oversampling an input just above full scale averages to 4090-4094, not 4095, so anything
   at or above POWER_ADC_CLIP_RAW is out of range (spec section 9.5). */
int adc_clipped(uint16_t raw12);

/* bq24074 */
int32_t iset_charge_ua(int32_t v_iset_uv, uint32_t r_iset_ohm);    /* 0 for R 0 or V <= 0 */
/* The voltage above a divider (mV, rounded half up) from its tap (uV) and its ratio (3 for 20k/10k);
   0 for a tap <= 0. */
int32_t divider_mv(int32_t pin_uv, uint32_t ratio);
/* The same with a measured ratio in ppm (3000000 for an exact 20k/10k): pin x ratio_ppm / 1e6, rounded
   half up, in mV (divider_mv_ppm) or uV (divider_uv_ppm, for benchlink's vin_uv). Any int32 tap and any
   uint32 ratio: the product stays below 2^63 in int64, and a result past INT32_MAX saturates. 0 for a
   ratio of 0 or a tap <= 0. */
int32_t divider_mv_ppm(int32_t pin_uv, uint32_t ratio_ppm);
int32_t divider_uv_ppm(int32_t pin_uv, uint32_t ratio_ppm);
/* A voltage before a gain (ppm): uv x 1e6 / gain_ppm, rounded half up (the ISET pin behind its
   10k/1M network back to V_ISET, gain 990099). Any int32 input and any uint32 gain (the product stays
   below 2^51); a result past INT32_MAX saturates. 0 for a gain of 0 or an input <= 0. */
int32_t unscale_ppm(int32_t uv, uint32_t gain_ppm);

/* BQ25798 */
#define BQ25798_VREG_MV_STEP 10U       /* REG01 (table 7-15) */
#define BQ25798_ICHG_MA_STEP 10U       /* REG03 (table 7-16) */
#define BQ25798_ITERM_MASK 0x1FU       /* REG09 bits 4:0 (table 7-20) */
#define BQ25798_ITERM_MA_STEP 40U      /* REG09 bits 4:0, 40 mA a count, 40-1000 mA, clamped low (table 7-20) */
uint16_t bq25798_vreg_mv(uint16_t raw16);    /* REG01 bits 10:0 x 10 mV */
uint16_t bq25798_ichg_ma(uint16_t raw16);    /* REG03 bits 8:0 x 10 mA */
uint16_t bq25798_vreg_raw(uint16_t mv);      /* the REG01 image for mv (truncated to 10 mV; 0 past the field) */
uint16_t bq25798_ichg_raw(uint16_t ma);      /* the REG03 image for ma (truncated to 10 mA; 0 past the field) */
uint16_t bq25798_iterm_ma(uint8_t reg09);   /* REG09 bits 4:0 x 40 mA */
/* The ITERM code nearest ma (half up), 1 (40 mA, the floor) to 25 (1000 mA): 90 mA gives 2 (80 mA). */
uint8_t bq25798_iterm_code(uint16_t ma);
unsigned bq25798_cells(uint8_t reg0a);       /* the cell count CELL selects, 1 to 4 */
int bq25798_pn_match(uint8_t reg48);         /* PN (bits 5:3) is 3, the BQ25798 */
/* TS in 0.1 % of REGN (the TS ADC count x 1000 / 1024, rounded half up): 0 to 999. */
uint16_t bq25798_ts_permille(uint16_t raw16);
int16_t bq25798_tdie_dc(uint16_t raw16);    /* the die temperature in 0.1 degC (count x 5, saturating at +-32767) */

#endif
