/* The bench OLED's layout: see bench_screen.h. */
#include "bench_screen.h"
#include "oled_font.h"
#include "oled_row.h"
#include "wsmp_registry.h"

#define ROW_PX 8                       /* 7-pixel glyphs and a 1-pixel gap: eight rows */
#define RAIN_TIPS_MAX 100000U          /* 27.94 m of rain: more reads as this */
enum { ROW_BUS, ROW_BATT, ROW_CELL, ROW_AIR, ROW_BOX, ROW_PRESS, ROW_WIND, ROW_RAIN };

static void row(const oled_surf *s, int r, const oled_row *line) { (void)oled_text(s, 0, r * ROW_PX, line->s, 1); }

/* "<label> " then the temperature and humidity, or "<label> NO <part>". */
static void th_row(const oled_surf *s, int r, const char *label, const char *part, int ok, int32_t centi_c, int32_t centi_rh)
{
  oled_row line = { "" };
  oled_put(&line, label);
  if (!ok) { oled_put(&line, " NO "); oled_put(&line, part); row(s, r, &line); return; }
  oled_put(&line, " ");
  oled_put_dec(&line, centi_c, 2, 2, 0);
  oled_put(&line, "C ");
  oled_put_dec(&line, centi_rh, 2, 2, 0);
  oled_put(&line, "%");
  row(s, r, &line);
}

void bench_screen(const oled_surf *s, const bench_view *v)
{
  oled_clear(s);

  oled_row line = { "I2C" };
  if (v->nfound == 0) oled_put(&line, " NONE");
  for (unsigned i = 0; i < v->nfound && i < BENCH_SCREEN_MAX_FOUND; i++)
  {
    oled_put(&line, " ");
    oled_put_hex2(&line, v->found[i]);
  }
  if (v->nfound > BENCH_SCREEN_MAX_FOUND) oled_put(&line, " +");
  row(s, ROW_BUS, &line);

  line = (oled_row){ "BATT " };
  if (!v->ina_ok) oled_put(&line, "NO INA228");
  else
  {
    oled_put_dec(&line, v->ua, 3, 2, OLED_PLUS);   /* a zero as +0.00mA, the node's rule */
    oled_put(&line, "mA ");
    oled_put_dec(&line, v->vbus_uv, 6, 3, 0);   /* the INA228 VBUS: its sense lead on OUT (P5) */
    oled_put(&line, "V");
  }
  row(s, ROW_BATT, &line);

  line = (oled_row){ "CELL " };
  if (!v->gauge_ok) oled_put(&line, "NO MAX17048");
  else
  {
    oled_put_dec(&line, v->vcell_uv, 6, 3, 0);
    oled_put(&line, "V ");
    oled_put_dec(&line, v->soc_mpct, 3, 1, 0);
    oled_put(&line, "%");
  }
  row(s, ROW_CELL, &line);

  th_row(s, ROW_AIR, "AIR", "SHT45", v->air_ok, v->air_centi_c, v->air_centi_rh);
  th_row(s, ROW_BOX, "BOX", "SHTC3", v->box_ok, v->box_centi_c, v->box_centi_rh);

  line = (oled_row){ "P " };
  if (!v->press_ok) oled_put(&line, "NO BMP581");
  else { oled_put_dec(&line, v->press_dhpa, 1, 1, 0); oled_put(&line, "hPa"); }
  oled_put(&line, " UV ");
  if (!v->uv_ok) oled_put(&line, "NO");
  else oled_put_uint(&line, v->uv_counts);
  row(s, ROW_PRESS, &line);

  if (!v->meters_ok) return;
  line = (oled_row){ "WIND " };
  oled_put_dec(&line, v->wind_ums, 6, 2, 0);
  oled_put(&line, "m/s ");
  oled_put(&line, v->vane ? v->vane : "?");
  row(s, ROW_WIND, &line);

  line = (oled_row){ "RAIN " };
  oled_put_uint(&line, v->tips);
  oled_put(&line, " TIPS ");
  oled_put_dec(&line, (int64_t)(v->tips > RAIN_TIPS_MAX ? RAIN_TIPS_MAX : v->tips) * (int64_t)WSMP_RAIN_NM_PER_TIP, 6,
               2, 0);
  oled_put(&line, "mm");
  row(s, ROW_RAIN, &line);
}
