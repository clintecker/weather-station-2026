/* The bench screens' dispatch (scr_screens.h) and the text helpers they share (scr_view.h). */
#include "scr_screens.h"
#include "wsmp_registry.h"

#define RAIN_TIPS_MAX 1000000U         /* 279 m of rain: more reads as this */

const char *const scr_point_names[16] = { "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" };

#define TIP_UM10 (WSMP_RAIN_NM_PER_TIP / 100U)   /* 0.2794 mm a tip (SEN-15901): 2794 in 0.1 um */
_Static_assert(WSMP_RAIN_NM_PER_TIP % 100U == 0U && RAIN_TIPS_MAX * TIP_UM10 + 5000U <= UINT32_MAX, "in 32 bits");

/* Rounded once, at the decimals shown, as oled_put_dec rounds: the same text as from the nanometres. */
void scr_put_rain_mm(oled_row *r, uint32_t tips, unsigned decimals)
{
  static const uint16_t per[5] = { 10000U, 1000U, 100U, 10U, 1U };   /* 0.1 um in the last decimal shown */
  unsigned d = decimals < 4U ? decimals : 4U;
  uint32_t t = tips > RAIN_TIPS_MAX ? RAIN_TIPS_MAX : tips;
  oled_put_dec(r, (int32_t)((t * TIP_UM10 + per[d] / 2U) / per[d]), d, d, 0);
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
