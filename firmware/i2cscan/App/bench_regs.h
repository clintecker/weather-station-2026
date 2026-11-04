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

/* The wind vane's compass point from its divider reading in "ratio mV" (the ADC count x 3300 / 4095:
   SEN-15901 network under a 10 kOhm pull-up to 3.3 V, the node's table and bands, stage0-node/App/mod_wind.c):
   "N" .. "NNW" clockwise; "OPEN" above 3200 mV (no vane, or the cable or jack open); "?" outside every band. */
const char *bench_vane_point(uint16_t mv);

/* A Sensirion reply: two 16-bit words (temperature, then humidity), each followed by its CRC-8 (poly
   0x31, init 0xFF). 0 with *centi_c and *centi_rh (0.01 C, 0.01 %RH) set; -1 on a CRC mismatch.
     shtc3 = 0: SHT45  T = -45 + 175 raw / 65535, RH = -6 + 125 raw / 65535, cropped to 0..100 %
     shtc3 = 1: SHTC3  T = -45 + 175 raw / 65536, RH = 100 raw / 65536 (its "T first" read, 0x7866) */
int bench_sht_parse(const uint8_t b[6], int shtc3, int32_t *centi_c, int32_t *centi_rh);

/* The BMP581's PRESS_DATA (0x20-0x22, little-endian, Pa x 64) in 0.1 hPa, rounded half up (as mod_reg.c). */
int32_t bench_bmp581_dhpa(const uint8_t b[3]);

/* The LTR390's UVS_DATA (0x10-0x12, little-endian): 20 bits of counts. */
uint32_t bench_ltr390_counts(const uint8_t b[3]);

#endif
