/* What the bench OLED shows: the latest readings laid out on the 128 x 64 drawing surface. Pure C. */
#ifndef BENCH_SCREEN_H
#define BENCH_SCREEN_H

#include <stdint.h>
#include "oled_draw.h"

#define BENCH_SCREEN_MAX_FOUND 5   /* addresses on the top line: "I2C", five, and " +" fit its 21 characters */

typedef struct {
  uint8_t found[BENCH_SCREEN_MAX_FOUND];   /* the last scan's addresses, ascending */
  unsigned nfound;                         /* how many answered (may exceed what fits) */
  int ina_ok;                              /* the INA228 answered with its ids this second */
  int32_t ua, vbus_uv;
  int gauge_ok;                            /* the MAX17048 answered with its version */
  int32_t vcell_uv, soc_mpct, crate_mpct_h;
  int meters_ok;                           /* the wind and rain lines have been read */
  int32_t wind_ums;                        /* wind speed over the last 3 s, um/s */
  const char *vane;                        /* bench_vane_point(), or "ADC?" */
  uint32_t tips;                           /* rain tips since start */
  int air_ok, box_ok, press_ok, uv_ok;     /* SHT45, SHTC3, BMP581, LTR390 read this second */
  int32_t air_centi_c, air_centi_rh, box_centi_c, box_centi_rh, press_dhpa;
  uint32_t uv_counts;
} bench_view;

/* Draws the view, eight rows of text, each part's row saying "NO <part>" when it did not answer:
     I2C 44 47 53 70
     BATT +37.60mA 3.846V   (INA228 0x40: current, OUT)
     CELL 3.846V 78.4%      (MAX17048)
     AIR 21.34C 45.21%      (SHT45)
     BOX 22.10C 40.02%      (SHTC3, the enclosure)
     P 1013.2hPa UV 123     (BMP581; LTR390 counts)
     WIND 1.33m/s SE
     RAIN 2 TIPS 0.56mm */
void bench_screen(const oled_surf *s, const bench_view *v);

#endif
