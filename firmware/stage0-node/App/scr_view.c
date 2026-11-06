/* The bench screens' dispatch (scr_screens.h) and the text helpers they share (scr_view.h). */
#include "scr_screens.h"
#include "wsmp_registry.h"

#define RAIN_TIPS_MAX 1000000U         /* 279 m of rain: more reads as this */

const char *const scr_point_names[16] = { "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" };

void scr_put_rain_mm(oled_row *r, uint32_t tips, unsigned decimals)
{
  uint32_t t = tips > RAIN_TIPS_MAX ? RAIN_TIPS_MAX : tips;
  oled_put_dec(r, (int64_t)t * (int64_t)WSMP_RAIN_NM_PER_TIP, 6, decimals, 0);   /* 0.2794 mm a tip (SEN-15901) */
}

void scr_put_age(oled_row *r, uint32_t s)
{
  if (s < 100U) { oled_put_uint(r, s); oled_put(r, "s"); }
  else if (s < 6000U) { oled_put_uint(r, s / 60U); oled_put(r, "m"); }
  else { oled_put_uint(r, s / 3600U); oled_put(r, "h"); }
}

void scr_form_lr(oled_row *r, const char *left, const char *right)
{
  if (oled_put_lr(r, left, right, OLED_COLS)) return;
  oled_put(r, left);
  oled_put(r, " ");
  oled_put(r, right);
}

void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v)
{
  const scr_def *d = &scr_defs[(unsigned)id < SCR_COUNT ? id : SCR_HOME];
  oled_clear(s);
  d->draw(s, (d->flags & SCR_F_ENDLESS) || frame < d->frames ? frame : d->frames - 1U, v);
}
