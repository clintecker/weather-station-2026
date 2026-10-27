/* Register decoding for the I2C bench tool (firmware/i2cscan): pure C, so the host tests check every
 * scale factor against the datasheets (tests/test_i2cscan.py). Values come out as integers in micro- or
 * milli-units: the console's printf (newlib nano) has no %f and no 64-bit conversions.
 *   INA228 (TI SBOS904): VSHUNT 0x04 and VBUS 0x05 are 24-bit registers whose top 20 bits hold a
 *   two's-complement value, 312.5 nV and 195.3125 uV a count (ADCRANGE = 0, the reset value).
 *   DIETEMP 0x06 is 16-bit two's complement, 7.8125 m degC a count. MANUFACTURER_ID 0x3E = 0x5449,
 *   DEVICE_ID 0x3F >> 4 = 0x228.
 *   MAX17048 (Analog Devices): VCELL 0x02 78.125 uV a count, SOC 0x04 1/256 % a count, CRATE 0x16
 *   two's complement 0.208 %/h a count, VERSION 0x08 & 0xFFF0 = 0x0010. */
#ifndef BENCH_REGS_H
#define BENCH_REGS_H

#include <stddef.h>
#include <stdint.h>

#define BENCH_SHUNT_MOHM 15   /* the INA228 breakout's shunt: 0.015 ohm ("R015") */

int32_t ina228_count(uint32_t raw24);   /* the 20-bit two's-complement count of a 24-bit register */
uint32_t ina228_raw24(int32_t count);   /* and back: a register image of a count (an average) */
int32_t ina228_vshunt_nv(uint32_t raw24);
int32_t ina228_vbus_uv(uint32_t raw24);
int32_t ina228_current_ua(uint32_t vshunt_raw24, int32_t shunt_mohm);
int32_t ina228_dietemp_mc(uint16_t raw16);
int ina228_ids_match(uint16_t manufacturer, uint16_t device);

int32_t max17048_vcell_uv(uint16_t raw16);
int32_t max17048_soc_mpct(uint16_t raw16);    /* milli-percent */
int32_t max17048_crate_mpct_h(uint16_t raw16); /* milli-percent an hour; negative while discharging */
int max17048_version_match(uint16_t version);

/* The part normally at a 7-bit address on this bench, or "?" (bench-station-wiring.md). */
const char *bench_part_name(uint8_t addr7);

/* value / 10^decimals as text with that many decimals and a '-' when negative ("+" when sign is set and
   value > 0), rounded to the last digit shown from `value` in units of 10^-(decimals + drop). Writes at
   most n bytes including the terminator; returns out. */
char *bench_fixed(char *out, size_t n, int32_t value, unsigned drop, unsigned decimals, int sign);

#endif
