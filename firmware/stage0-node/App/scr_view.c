/* The bench screens' dispatch, their frame counts and the helpers they share: see scr_view.h. */
#include "scr_view.h"
#include <string.h>
#include "oled_draw.h"
#include "wsmp_registry.h"

#define HEADER_PX 8
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

void scr_row(const oled_surf *s, int y, const char *text) { (void)oled_text(s, 0, y, text, 1); }

void scr_row_right(const oled_surf *s, int y, const char *text)
{
  (void)oled_text(s, OLED_W - OLED_CHAR_ADVANCE * (int)strlen(text) + 1, y, text, 1);
}

void scr_header(const oled_surf *s, const char *text)
{
  (void)oled_text(s, 0, 0, text, 1);
  oled_invert(s, 0, 0, OLED_W, HEADER_PX);
}

int scr_sin20(int p)
{
  static const int8_t quarter[5] = { 0, 8, 14, 18, 20 };
  p &= 15;
  if (p <= 4) return quarter[p];
  if (p <= 8) return quarter[8 - p];
  if (p <= 12) return -quarter[p - 8];
  return -quarter[16 - p];
}

unsigned scr_frames(enum scr_id id)
{
  switch (id)
  {
  case SCR_HOME: return 1U;
  case SCR_BANNER: return 24U;
  case SCR_BURST: return 16U;
  case SCR_HACK: return 24U;
  case SCR_AIR: case SCR_PRESSURE: case SCR_POWER: case SCR_RADIO: return 8U;
  default: return 64U;
  }
}

void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v)
{
  oled_clear(s);
  if (id != SCR_HOME && id != SCR_BANNER && frame >= scr_frames(id)) frame = scr_frames(id) - 1U;
  switch (id)
  {
  case SCR_BURST: scr_burst(s, frame, v); break;
  case SCR_BANNER: scr_home(s, frame, v, 1); break;
  case SCR_AIR: scr_air(s, frame, v); break;
  case SCR_PRESSURE: scr_pressure(s, frame, v); break;
  case SCR_POWER: scr_power(s, frame, v); break;
  case SCR_RADIO: scr_radio(s, frame, v); break;
  case SCR_SCOPE: scr_scope(s, v); break;
  case SCR_VANE: scr_vane(s, frame, v); break;
  case SCR_RAIN: scr_rain(s, v); break;
  case SCR_SYSTEM: scr_system(s, frame, v); break;
  case SCR_BOOT: scr_boot(s, frame, v); break;
  case SCR_HACK: scr_hack(s, frame); break;
  case SCR_FORTUNE: scr_fortune(s, frame, v); break;
  case SCR_FROG: scr_frog(s, frame, v); break;
  case SCR_MATRIX: scr_matrix(s, frame, v); break;
  case SCR_PINBALL: scr_pinball(s, frame, v); break;
  default: scr_home(s, frame, v, 0); break;
  }
}
