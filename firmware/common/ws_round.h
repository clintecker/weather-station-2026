#ifndef WS_ROUND_H
#define WS_ROUND_H
/* The one rounding helper of the station (docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md
 * section 6.9, "Rounding"): num / den rounded half up, floor((2 num + den) / (2 den)), for den > 0.
 * The window mean (stage0-node/App/mod_mean.c) and the record calibration (wsmp_cal.c) both use it.
 * Golden vectors shared with the Python reference: tests/ws_div_round_vectors.csv.
 *
 * C's '/' truncates toward zero, so a negative quotient that is not exact is moved down by one: that
 * is floor. Range: |num| and den below 2^62, so 2 num + den does not overflow; the callers stay far
 * inside it (a window sum is int32, a calibration product below 2^55). */
#include <stdint.h>

static inline int64_t ws_div_round(int64_t num, int64_t den)
{
  int64_t n2 = 2 * num + den, d2 = 2 * den;
  int64_t q = n2 / d2;
  if (n2 % d2 != 0 && n2 < 0) q--;
  return q;
}
#endif
