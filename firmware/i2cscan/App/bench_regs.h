/* Bench-only helpers of the I2C bench tool (firmware/i2cscan) and the bench telemetry link
 * (firmware/benchlink): the part names on the bench's bus, an average and fixed-point text. The INA228,
 * MAX17048, ADC and bq24074 ISET conversions are shared with the node in firmware/common/power_regs.h
 * (included here). Pure C, checked on the host (tests/test_i2cscan.py). */
#ifndef BENCH_REGS_H
#define BENCH_REGS_H

#include <stddef.h>
#include <stdint.h>

#include "power_regs.h"

#define BENCH_SHUNT_UOHM 15000   /* the INA228 breakout's shunt: 0.015 ohm ("R015"), for ina228_current_ua */
#define BENCH_SHUNT_MOHM 15      /* the same in milli-ohm, for text only: ina228_current_ua takes micro-ohm */

/* The part normally at a 7-bit address on this bench, or "?" (bench-station-wiring.md). */
const char *bench_part_name(uint8_t addr7);

/* sum / n rounded to the nearest whole number, halves away from zero; 0 when n is 0. */
int32_t bench_mean(int64_t sum, unsigned n);

#define BENCH_FIXED_MAX_DIGITS 9U   /* the most decimals, or dropped digits, bench_fixed takes */

/* value / 10^decimals as text with that many decimals and a '-' when negative ("+" when sign is set and
   value > 0), rounded to the last digit shown from `value` in units of 10^-(decimals + drop). Writes at
   most n bytes including the terminator; returns out. "?" when drop or decimals exceed
   BENCH_FIXED_MAX_DIGITS. */
char *bench_fixed(char *out, size_t n, int32_t value, unsigned drop, unsigned decimals, int sign);

#endif
