/* HOME, the base screen, and its packet banner (scr_view.h). The rows:
 *     (icon)        21.9^C      the SHT45 in big digits (^ the degree sign); --^C with none
 *                   46% RH      its RH (NO SHT45)
 *                986.5 hPa      the BMP581 (NO BMP581)
 *     WIND calm  RAIN 0.0       the wind (calm under 0.5 m/s, else m/s and point), the last hour's mm
 *     #1233 ACK -41dBm  |||     the last frame, its outcome, and the ACK's signal bars (scr_signal_bars)
 * The icon (scr_icon_pick) animates at HOME's frame / 2: the sun's rays turn, the moon's stars twinkle,
 * the cloud drifts, the rain and the snow fall, the wind's streaks blow. The banner inverts the bottom two
 * rows: "  SENDING TX 1234" (or "  TX 1234 +5 BACKLOG", "+HEALTH" for a health report, when frames
 * followed the live one), then the outcome, "  ACK -41DBM SNR 13" or "  NO ACK". A row longer than its
 * columns takes a shorter form (BKLG, HLTH and no indent in the banner; W and R, then no dBm, on the
 * lower rows) rather than lose its last characters. */
#include "scr_view.h"
#include "oled_draw.h"
#include "scr_font.h"

#define ICON_CX 20
#define ICON_CY 19
#define TEMP_Y 1
#define RH_Y 20
#define PRESS_Y 30
#define WIND_Y 48
#define LINK_Y 56
#define LINK_COLS 18U                  /* the signal bars take the last three columns */
#define BARS_X 113
#define BANNER_Y 48

/* ---- the icons, each around (ICON_CX, ICON_CY) ---- */

static int at_r(int r, int p) { return r * scr_sin20(p) / 20; }   /* r along x at compass point p */

static void sun(const oled_surf *s, unsigned tick)
{
  oled_disc(s, ICON_CX, ICON_CY, 6, 1);
  for (int k = 0; k < 8; k++)
  {
    int p = 2 * k + (int)(tick & 1U), r1 = (k & 1) ? 13 : 15;
    oled_line(s, ICON_CX + at_r(9, p), ICON_CY - at_r(9, p + 4), ICON_CX + at_r(r1, p), ICON_CY - at_r(r1, p + 4), 0);
  }
}

static void star(const oled_surf *s, int x, int y, int big)
{
  oled_set(s, x, y, 1);
  if (!big) return;
  oled_line(s, x - 2, y, x + 2, y, 0);
  oled_line(s, x, y - 2, x, y + 2, 0);
}

static void moon(const oled_surf *s, unsigned tick)
{
  static const int8_t stars[3][2] = { { 38, 5 }, { 3, 30 }, { 35, 31 } };
  oled_disc(s, ICON_CX - 2, ICON_CY, 11, 1);
  oled_disc(s, ICON_CX + 4, ICON_CY - 4, 10, 0);   /* the crescent */
  for (unsigned i = 0; i < 3U; i++) star(s, stars[i][0], stars[i][1], (tick + i) % 3U == 0U);
}

static void cloud(const oled_surf *s, int cx, int cy)
{
  oled_disc(s, cx - 8, cy + 2, 5, 1);
  oled_disc(s, cx, cy - 3, 7, 1);
  oled_disc(s, cx + 8, cy + 1, 6, 1);
  oled_fill(s, cx - 8, cy + 2, 17, 6, 1);
}

static int drift(unsigned tick) { static const int8_t d[4] = { -1, 0, 1, 0 }; return d[tick % 4U]; }

static void rain(const oled_surf *s, unsigned tick)
{
  cloud(s, ICON_CX + drift(tick), ICON_CY - 6);
  for (unsigned i = 0; i < 4U; i++)
  {
    int x = ICON_CX - 9 + 6 * (int)i, y = ICON_CY + 5 + (int)((tick * 3U + i * 5U) % 12U);
    oled_line(s, x, y, x - 1, y + 3, 0);
  }
}

static void snow(const oled_surf *s, unsigned tick)
{
  int turn = (int)((tick / 2U) & 1U);
  for (int k = 0; k < 8; k++)   /* eight arms, each with two twigs; a sixteenth of a turn each other tick */
  {
    int p = 2 * k + turn, bx = ICON_CX + at_r(6, p), by = ICON_CY - at_r(6, p + 4);
    oled_line(s, ICON_CX, ICON_CY, ICON_CX + at_r(11, p), ICON_CY - at_r(11, p + 4), 0);
    oled_line(s, bx, by, bx + at_r(3, p + 2), by - at_r(3, p + 6), 0);
    oled_line(s, bx, by, bx + at_r(3, p - 2), by - at_r(3, p + 2), 0);
  }
  for (unsigned i = 0; i < 3U; i++)
    oled_set(s, 4 + 18 * (int)i, (int)((tick * 2U + i * 13U) % 38U), 1);   /* flakes falling past it */
}

static void wind(const oled_surf *s, unsigned tick)
{
  static const int8_t len[3] = { 30, 40, 26 };
  int shift = (int)(tick * 2U % 12U);
  for (int i = 0; i < 3; i++)
  {
    int y = ICON_CY - 9 + 9 * i;
    oled_line(s, -shift, y, len[i], y, 6);
  }
  oled_circle(s, 40, ICON_CY - 3, 3);
  oled_set(s, 40, ICON_CY, 0);
}

static void icon(const oled_surf *s, enum scr_icon i, unsigned tick)
{
  switch (i)
  {
  case ICON_MOON: moon(s, tick); break;
  case ICON_CLOUD: cloud(s, ICON_CX + drift(tick), ICON_CY); break;
  case ICON_RAIN: rain(s, tick); break;
  case ICON_SNOW: snow(s, tick); break;
  case ICON_WIND: wind(s, tick); break;
  default: sun(s, tick); break;
  }
}

/* ---- the rows ---- */

static void readings(const oled_surf *s, const scr_view_t *v)
{
  oled_row t = { "" }, rh = { "" }, p = { "" };
  if (v->air_ok) { oled_put_dec(&t, v->air_c, 2, 1, 0); oled_put(&t, "^C"); }
  else oled_put(&t, "--^C");
  (void)oled_draw_text(s, OLED_W - oled_text_w(t.s, &scr_big, &oled_x1), TEMP_Y, t.s, &scr_big, &oled_x1);
  if (v->air_ok) { oled_put_dec(&rh, v->air_rh, 2, 0, 0); oled_put(&rh, "% RH"); }
  else oled_put(&rh, "NO SHT45");
  scr_row_right(s, RH_Y, rh.s);
  if (v->press_ok) { oled_put_dec(&p, v->press_dhpa, 1, 1, 0); oled_put(&p, " hPa"); }
  else oled_put(&p, "NO BMP581");
  scr_row_right(s, PRESS_Y, p.s);
}

/* form 0 "WIND 1.3 NE  RAIN 0.6", 1 with one space between, 2 "W 1.3 NE R 0.6". */
static void wind_rain_form(oled_row *r, const void *ctx, unsigned form)
{
  const scr_view_t *v = ctx;
  oled_put(r, form < 2U ? "WIND " : "W ");
  if (v->wind.speed_cms < SCR_CALM_CMS) oled_put(r, "calm");
  else
  {
    oled_put_dec(r, v->wind.speed_cms, 2, 1, 0);
    if (v->wind.point >= 0 && v->wind.point < 16) { oled_put(r, " "); oled_put(r, scr_point_names[v->wind.point]); }
  }
  oled_put(r, form == 0U ? "  RAIN " : form == 1U ? " RAIN " : " R ");
  scr_put_rain_mm(r, scr_rain_tips(v->rain.per_min, RAIN_HIST_MINUTES, RAIN_HIST_MINUTES), 1);
}

/* form 0 "#1233 ACK -41dBm", 1 "#1233 ACK -41", 2 "#1233 ACK". */
static void link_form(oled_row *r, const void *ctx, unsigned form)
{
  const scr_view_t *v = ctx;
  if (v->last_acked == SCR_TX_NONE) { oled_put(r, "NO TX YET"); return; }
  oled_put(r, "#");
  oled_put_uint(r, v->last_seq);
  if (v->last_acked == SCR_TX_WAIT) { oled_put(r, " SENT"); return; }
  if (v->last_acked != SCR_TX_ACK) { oled_put(r, " NO ACK"); return; }
  oled_put(r, " ACK");
  if (form < 2U) { oled_put(r, " "); oled_put_dec(r, v->ack_rssi, 0, 0, 0); }
  if (form == 0U) oled_put(r, "dBm");
}

static void signal_bars(const oled_surf *s, const scr_view_t *v)
{
  unsigned lit = v->last_acked == SCR_TX_ACK ? scr_signal_bars(v->ack_rssi) : 0U;
  for (unsigned b = 0; b < 3U; b++)
  {
    int x = BARS_X + 5 * (int)b, h = 3 + 2 * (int)b;
    if (b < lit) oled_fill(s, x, LINK_Y + 7 - h, 3, h, 1);
    else oled_line(s, x, LINK_Y + 6, x + 2, LINK_Y + 6, 0);   /* an unlit bar: its foot */
  }
}

/* The banner's first row in form 0 (full), 1 (short words) or 2 (short words, no indent). */
static void banner_form(oled_row *r, const void *ctx, unsigned form)
{
  const scr_view_t *v = ctx;
  if (form < 2U) oled_put(r, "  ");
  if (v->extra_frames == 0 && v->reports == 0) oled_put(r, "SENDING ");
  oled_put(r, "TX ");
  oled_put_uint(r, v->last_seq);
  if (v->extra_frames != 0) { oled_put(r, " +"); oled_put_uint(r, v->extra_frames); oled_put(r, form ? " BKLG" : " BACKLOG"); }
  if (v->reports != 0) oled_put(r, form ? " +HLTH" : " +HEALTH");
}

static void banner(const oled_surf *s, const scr_view_t *v)
{
  oled_row line;
  (void)oled_fit(&line, banner_form, v, 3, OLED_COLS);
  scr_row(s, BANNER_Y, line.s);
  oled_row outcome = { "  " };
  if (v->last_acked == SCR_TX_ACK)
  {
    oled_put(&outcome, "ACK ");
    oled_put_dec(&outcome, v->ack_rssi, 0, 0, 0);
    oled_put(&outcome, "DBM SNR ");
    oled_put_dec(&outcome, v->ack_snr, 0, 0, 0);
  }
  else if (v->last_acked == SCR_TX_NO_ACK) oled_put(&outcome, "NO ACK");
  scr_row(s, BANNER_Y + 8, outcome.s);
  oled_invert(s, 0, BANNER_Y, OLED_W, 16);
}

void scr_home(const oled_surf *s, unsigned frame, const scr_view_t *v, int with_banner)
{
  icon(s, scr_icon_pick(v), frame / 2U);
  readings(s, v);
  if (with_banner) { banner(s, v); return; }
  oled_row line;
  (void)oled_fit(&line, wind_rain_form, v, 3, OLED_COLS);
  scr_row(s, WIND_Y, line.s);
  (void)oled_fit(&line, link_form, v, 3, LINK_COLS);
  scr_row(s, LINK_Y, line.s);
  signal_bars(s, v);
}
