/* The rain screen (scr_screens.h), from the view's rain history (mod_rain_history):
 *     RAIN          0.56 mm      since boot
 *     2 tips    last 4m ago      since boot; the last tip's age (last -- if none)
 *     RATE  1.7 mm/h (10m)       the last 10 minutes, this one so far among them
 *     (a bar a minute for the last hour, 2 pixels wide, the newest at the right, between two sides, under
 *      a dotted ceiling and over an axis; the ceiling is the scale, scr_scale_steps of the largest minute)
 *     -60m     16/m     now      the scale in tips a minute, centred
 * A row longer than the 21 columns takes a shorter form: the age "last X" (no "ago"), then "X"; the rate one
 * space after RATE, then without "(10m)". */
#include "scr_screens.h"
#include "oled_draw.h"
#include "wsmp_registry.h"

#define RATE_MINUTES 10U
#define RAIN_MIN_FULL 4U               /* the scale's floor, in tips a minute; it doubles from there */
#define RAIN_FULL_MAX 256U             /* a uint8_t minute's most: 6 doublings */
#define BARS_X 4                       /* the oldest minute's bar; the newest ends at x 123 */
#define BAR_W 2
#define SIDE_L 2
#define SIDE_R 125
#define CEIL_Y 26                      /* the dotted ceiling: a full-scale bar stops a pixel under it */
#define PLOT_TOP 28
#define AXIS_Y 52                      /* the bars stand on it: PLOT_TOP to AXIS_Y - 1 */
#define BAR_PX ((unsigned)(AXIS_Y - PLOT_TOP))
#define NM_PER_UM 1000U
#define MIN_PER_H 60U

uint32_t scr_rain_rate_umh(const uint8_t *per_min, unsigned n, unsigned minutes)
{
  if (minutes == 0U) return 0;
  uint32_t sum = scr_rain_tips(per_min, n, minutes);
  return (uint32_t)((uint64_t)sum * WSMP_RAIN_NM_PER_TIP * MIN_PER_H / minutes / NM_PER_UM);
}

/* form 0 "2 tips    last 4m ago", 1 "last 4m", 2 "4m", 3 the count alone. */
static void count_form(oled_row *r, const void *ctx, unsigned form)
{
  const rain_hist_t *h = ctx;
  oled_row left = { "" }, age = { "" };
  oled_put_uint(&left, h->tips);
  oled_put(&left, h->tips == 1U ? " tip" : " tips");
  if (form == 3U) { oled_put(r, left.s); return; }
  int none = h->last_age_s == RAIN_AGE_NONE;
  if (form < 2U) oled_put(&age, "last ");
  if (none) oled_put(&age, "--");
  else scr_put_age(&age, h->last_age_s);
  if (form == 0U && !none) oled_put(&age, " ago");
  scr_form_lr(r, left.s, age.s);
}

/* form 0 "RATE  1.7 mm/h (10m)", 1 one space after RATE, 2 without "(10m)". */
static void rate_form(oled_row *r, const void *ctx, unsigned form)
{
  const rain_hist_t *h = ctx;
  oled_put(r, form == 1U ? "RATE " : "RATE  ");
  oled_put_dec(r, (int32_t)scr_rain_rate_umh(h->per_min, RAIN_HIST_MINUTES, RATE_MINUTES), 3, 1, 0);
  oled_put(r, " mm/h");
  if (form < 2U) oled_put(r, " (10m)");
}

static const scr_bars_style minute_bars = { BAR_W, BAR_W, 0, 0 };

void scr_rain(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  (void)frame;
  const rain_hist_t *h = &v->rain;
  oled_row line = { "" }, mm = { "" }, scale = { "" };
  scr_put_rain_mm(&mm, h->tips, 2);
  oled_put(&mm, " mm");
  (void)oled_put_lr(&line, "RAIN", mm.s, OLED_COLS);   /* at most "279400.00 mm" (RAIN_TIPS_MAX) */
  scr_label(s, 0, line.s, SCR_LEFT);
  (void)oled_fit(&line, count_form, h, 4, OLED_COLS);   /* the last fits any count with an age up to RAIN_AGE_MAX_S */
  scr_label(s, SCR_ROW_PX, line.s, SCR_LEFT);
  (void)oled_fit(&line, rate_form, h, 3, OLED_COLS);
  scr_label(s, 2 * SCR_ROW_PX, line.s, SCR_LEFT);
  scr_series d = scr_series_u8(h->per_min, RAIN_HIST_MINUTES, RAIN_HIST_MINUTES);
  unsigned full = scr_scale_steps((unsigned)scr_max(&d), RAIN_MIN_FULL, RAIN_FULL_MAX);
  scr_frame(s, SIDE_L, CEIL_Y, SIDE_R, AXIS_Y, SCR_EDGE_DOTTED, SCR_EDGE_SOLID, 1);
  scr_bars(s, BARS_X, AXIS_Y, BAR_PX, &d, 0, (int32_t)full, 0, &minute_bars);
  oled_put_uint(&scale, full);
  oled_put(&scale, "/m");
  (void)oled_put_lcr(&line, "-60m", scale.s, "now", OLED_COLS);   /* the scale centred */
  scr_label(s, 7 * SCR_ROW_PX, line.s, SCR_LEFT);
}
