/* The rain screen (scr_view.h), from the view's rain history (mod_rain_history):
 *     RAIN          0.56 mm      since boot
 *     2 tips    last 4m ago      since boot; the last tip's age (last -- if none)
 *     RATE  1.7 mm/h (10m)       the last 10 minutes, this one so far among them
 *     (a bar a minute for the last hour, 2 pixels wide, the newest at the right, between two sides, under
 *      a dotted ceiling and over an axis; the ceiling is the scale, scr_rain_full of the largest minute)
 *     -60m     16/m     now      the scale in tips a minute, centred
 * A row longer than the 21 columns takes a shorter form: the age "last X" (no "ago"), then "X"; the rate one
 * space after RATE, then without "(10m)". */
#include "scr_view.h"
#include "oled_draw.h"
#include "wsmp_registry.h"

#define RATE_MINUTES 10U
#define RAIN_MIN_FULL 4U               /* the scale's floor, in tips a minute; it doubles from there */
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
  unsigned from = n > minutes ? n - minutes : 0U;
  uint32_t sum = 0;
  for (unsigned i = from; i < n; i++) sum += per_min[i];
  return (uint32_t)((uint64_t)sum * WSMP_RAIN_NM_PER_TIP * MIN_PER_H / minutes / NM_PER_UM);
}

unsigned scr_rain_full(unsigned largest)
{
  unsigned full = RAIN_MIN_FULL;
  while (full < largest && full < 256U) full *= 2U;   /* bound: 4 doublings to 64, 6 to 256 (a uint8_t minute) */
  return full;
}

static void row(const oled_surf *s, int r, const char *text) { (void)oled_text(s, 0, r * 8, text, 1); }

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
  oled_put_dec(r, scr_rain_rate_umh(h->per_min, RAIN_HIST_MINUTES, RATE_MINUTES), 3, 1, 0);
  oled_put(r, " mm/h");
  if (form < 2U) oled_put(r, " (10m)");
}

/* The bars; returns the scale they were drawn to. */
static unsigned bars(const oled_surf *s, const rain_hist_t *h)
{
  unsigned largest = 0;
  for (unsigned i = 0; i < RAIN_HIST_MINUTES; i++)
    if (h->per_min[i] > largest) largest = h->per_min[i];
  unsigned full = scr_rain_full(largest);
  oled_line(s, SIDE_L, CEIL_Y, SIDE_L, AXIS_Y, 0);
  oled_line(s, SIDE_R, CEIL_Y, SIDE_R, AXIS_Y, 0);
  oled_line(s, SIDE_L, CEIL_Y, SIDE_R, CEIL_Y, 1);
  oled_line(s, SIDE_L, AXIS_Y, SIDE_R, AXIS_Y, 0);
  for (unsigned i = 0; i < RAIN_HIST_MINUTES; i++)
  {
    int px = (int)scr_bar_px(h->per_min[i], (int32_t)full, BAR_PX);
    oled_fill(s, BARS_X + BAR_W * (int)i, AXIS_Y - px, BAR_W, px, 1);
  }
  return full;
}

void scr_rain(const oled_surf *s, const scr_view_t *v)
{
  const rain_hist_t *h = &v->rain;
  oled_row line = { "" }, mm = { "" }, scale = { "" };
  scr_put_rain_mm(&mm, h->tips, 2);
  oled_put(&mm, " mm");
  (void)oled_put_lr(&line, "RAIN", mm.s, OLED_COLS);   /* at most "279400.00 mm" (RAIN_TIPS_MAX) */
  row(s, 0, line.s);
  (void)oled_fit(&line, count_form, h, 4, OLED_COLS);   /* the last fits any count with an age up to RAIN_AGE_MAX_S */
  row(s, 1, line.s);
  (void)oled_fit(&line, rate_form, h, 3, OLED_COLS);
  row(s, 2, line.s);
  oled_put_uint(&scale, bars(s, h));
  oled_put(&scale, "/m");
  (void)oled_put_lcr(&line, "-60m", scale.s, "now", OLED_COLS);   /* the scale centred */
  row(s, 7, line.s);
}
