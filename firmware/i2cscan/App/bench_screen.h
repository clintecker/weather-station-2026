/* What the bench OLED shows: the latest readings laid out on the 128 x 64 frame buffer. Pure C. */
#ifndef BENCH_SCREEN_H
#define BENCH_SCREEN_H

#include <stdint.h>
#include "oled_fb.h"

#define BENCH_SCREEN_MAX_FOUND 6   /* addresses shown on the top line (21 characters wide) */

typedef struct {
  uint8_t found[BENCH_SCREEN_MAX_FOUND];   /* the last scan's addresses, ascending */
  unsigned nfound;                         /* how many answered (may exceed what fits) */
  int ina_ok;                              /* the INA228 answered with its ids this second */
  int32_t ua, vbus_uv;
  int gauge_ok;                            /* the MAX17048 answered with its version */
  int32_t vcell_uv, soc_mpct, crate_mpct_h;
} bench_view;

/* Draws the view: the bus on top, the battery current large, then the voltages and the gauge.
     I2C 36 40
     +37.60mA          (twice the size)
     VBUS 3.8459V
     CELL 3.8460V 78.4%
     RATE -0.62%/h */
void bench_screen(oled_fb *fb, const bench_view *v);

#endif
