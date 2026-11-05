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
#include <string.h>
#include "oled_draw.h"
#include "wsmp_registry.h"

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

static void sun(oled_fb *fb, unsigned tick)
{
  oled_disc(fb, ICON_CX, ICON_CY, 6, 1);
  for (int k = 0; k < 8; k++)
  {
    int p = 2 * k + (int)(tick & 1U), r1 = (k & 1) ? 13 : 15;
    oled_line(fb, ICON_CX + at_r(9, p), ICON_CY - at_r(9, p + 4), ICON_CX + at_r(r1, p), ICON_CY - at_r(r1, p + 4), 0);
  }
}

static void star(oled_fb *fb, int x, int y, int big)
{
  oled_set(fb, x, y, 1);
  if (!big) return;
  oled_line(fb, x - 2, y, x + 2, y, 0);
  oled_line(fb, x, y - 2, x, y + 2, 0);
}

static void moon(oled_fb *fb, unsigned tick)
{
  static const int8_t stars[3][2] = { { 38, 5 }, { 3, 30 }, { 35, 31 } };
  oled_disc(fb, ICON_CX - 2, ICON_CY, 11, 1);
  oled_disc(fb, ICON_CX + 4, ICON_CY - 4, 10, 0);   /* the crescent */
  for (unsigned i = 0; i < 3U; i++) star(fb, stars[i][0], stars[i][1], (tick + i) % 3U == 0U);
}

static void cloud(oled_fb *fb, int cx, int cy)
{
  oled_disc(fb, cx - 8, cy + 2, 5, 1);
  oled_disc(fb, cx, cy - 3, 7, 1);
  oled_disc(fb, cx + 8, cy + 1, 6, 1);
  oled_fill(fb, cx - 8, cy + 2, 17, 6, 1);
}

static int drift(unsigned tick) { static const int8_t d[4] = { -1, 0, 1, 0 }; return d[tick % 4U]; }

static void rain(oled_fb *fb, unsigned tick)
{
  cloud(fb, ICON_CX + drift(tick), ICON_CY - 6);
  for (unsigned i = 0; i < 4U; i++)
  {
    int x = ICON_CX - 9 + 6 * (int)i, y = ICON_CY + 5 + (int)((tick * 3U + i * 5U) % 12U);
    oled_line(fb, x, y, x - 1, y + 3, 0);
  }
}

static void snow(oled_fb *fb, unsigned tick)
{
  int turn = (int)((tick / 2U) & 1U);
  for (int k = 0; k < 8; k++)   /* eight arms, each with two twigs; a sixteenth of a turn each other tick */
  {
    int p = 2 * k + turn, bx = ICON_CX + at_r(6, p), by = ICON_CY - at_r(6, p + 4);
    oled_line(fb, ICON_CX, ICON_CY, ICON_CX + at_r(11, p), ICON_CY - at_r(11, p + 4), 0);
    oled_line(fb, bx, by, bx + at_r(3, p + 2), by - at_r(3, p + 6), 0);
    oled_line(fb, bx, by, bx + at_r(3, p - 2), by - at_r(3, p + 2), 0);
  }
  for (unsigned i = 0; i < 3U; i++)
    oled_set(fb, 4 + 18 * (int)i, (int)((tick * 2U + i * 13U) % 38U), 1);   /* flakes falling past it */
}

static void wind(oled_fb *fb, unsigned tick)
{
  static const int8_t len[3] = { 30, 40, 26 };
  int shift = (int)(tick * 2U % 12U);
  for (int i = 0; i < 3; i++)
  {
    int y = ICON_CY - 9 + 9 * i;
    oled_line(fb, -shift, y, len[i], y, 6);
  }
  oled_circle(fb, 40, ICON_CY - 3, 3);
  oled_set(fb, 40, ICON_CY, 0);
}

static void icon(oled_fb *fb, enum scr_icon i, unsigned tick)
{
  switch (i)
  {
  case ICON_MOON: moon(fb, tick); break;
  case ICON_CLOUD: cloud(fb, ICON_CX + drift(tick), ICON_CY); break;
  case ICON_RAIN: rain(fb, tick); break;
  case ICON_SNOW: snow(fb, tick); break;
  case ICON_WIND: wind(fb, tick); break;
  default: sun(fb, tick); break;
  }
}

/* ---- the rows ---- */

static void readings(oled_fb *fb, const scr_view_t *v)
{
  char t[SCR_LINE] = "", rh[SCR_LINE] = "", p[SCR_LINE] = "";
  if (v->air_ok) { scr_put_dec(t, v->air_c, 2, 1, 0); scr_put(t, "^C"); }
  else scr_put(t, "--^C");
  (void)scr_big_text(fb, OLED_W - scr_big_width(t), TEMP_Y, t);
  if (v->air_ok) { scr_put_dec(rh, v->air_rh, 2, 0, 0); scr_put(rh, "% RH"); }
  else scr_put(rh, "NO SHT45");
  scr_row_right(fb, RH_Y, rh);
  if (v->press_ok) { scr_put_dec(p, v->press_dhpa, 1, 1, 0); scr_put(p, " hPa"); }
  else scr_put(p, "NO BMP581");
  scr_row_right(fb, PRESS_Y, p);
}

/* form 0 "WIND 1.3 NE  RAIN 0.6", 1 with one space between, 2 "W 1.3 NE R 0.6". */
static void wind_rain_line(char *line, const scr_view_t *v, unsigned form)
{
  line[0] = '\0';
  scr_put(line, form < 2U ? "WIND " : "W ");
  if (v->wind.speed_cms < SCR_CALM_CMS) scr_put(line, "calm");
  else
  {
    scr_put_dec(line, v->wind.speed_cms, 2, 1, 0);
    if (v->wind.point >= 0 && v->wind.point < 16) { scr_put(line, " "); scr_put(line, scr_point_names[v->wind.point]); }
  }
  scr_put(line, form == 0U ? "  RAIN " : form == 1U ? " RAIN " : " R ");
  uint32_t tips = scr_rain_tips(v->rain.per_min, RAIN_HIST_MINUTES, RAIN_HIST_MINUTES);
  scr_put_dec(line, (int64_t)tips * WSMP_RAIN_NM_PER_TIP, 6, 1, 0);
}

static void wind_rain_row(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE];
  for (unsigned form = 0; form < 3U; form++)   /* bound: 3 forms; the last is drawn as it is */
  {
    wind_rain_line(line, v, form);
    if (strlen(line) <= SCR_COLS) break;
  }
  scr_row(fb, WIND_Y, line);
}

/* form 0 "#1233 ACK -41dBm", 1 "#1233 ACK -41", 2 "#1233 ACK". */
static void link_line(char *line, const scr_view_t *v, unsigned form)
{
  line[0] = '\0';
  if (v->last_acked == SCR_TX_NONE) { scr_put(line, "NO TX YET"); return; }
  scr_put(line, "#");
  scr_put_uint(line, v->last_seq);
  if (v->last_acked == SCR_TX_WAIT) { scr_put(line, " SENT"); return; }
  if (v->last_acked != SCR_TX_ACK) { scr_put(line, " NO ACK"); return; }
  scr_put(line, " ACK");
  if (form < 2U) { scr_put(line, " "); scr_put_dec(line, v->ack_rssi, 0, 0, 0); }
  if (form == 0U) scr_put(line, "dBm");
}

static void signal_bars(oled_fb *fb, const scr_view_t *v)
{
  unsigned lit = v->last_acked == SCR_TX_ACK ? scr_signal_bars(v->ack_rssi) : 0U;
  for (unsigned b = 0; b < 3U; b++)
  {
    int x = BARS_X + 5 * (int)b, h = 3 + 2 * (int)b;
    if (b < lit) oled_fill(fb, x, LINK_Y + 7 - h, 3, h, 1);
    else oled_line(fb, x, LINK_Y + 6, x + 2, LINK_Y + 6, 0);   /* an unlit bar: its foot */
  }
}

static void link_row(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE];
  for (unsigned form = 0; form < 3U; form++)   /* bound: 3 forms; the last is drawn as it is */
  {
    link_line(line, v, form);
    if (strlen(line) <= LINK_COLS) break;
  }
  scr_row(fb, LINK_Y, line);
  signal_bars(fb, v);
}

/* The banner's first row in form 0 (full), 1 (short words) or 2 (short words, no indent). */
static void banner_line(char *line, const scr_view_t *v, unsigned form)
{
  line[0] = '\0';
  if (form < 2U) scr_put(line, "  ");
  if (v->extra_frames == 0 && v->reports == 0) scr_put(line, "SENDING ");
  scr_put(line, "TX ");
  scr_put_uint(line, v->last_seq);
  if (v->extra_frames != 0) { scr_put(line, " +"); scr_put_uint(line, v->extra_frames); scr_put(line, form ? " BKLG" : " BACKLOG"); }
  if (v->reports != 0) scr_put(line, form ? " +HLTH" : " +HEALTH");
}

static void banner(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE];
  for (unsigned form = 0; form < 3U; form++)   /* bound: 3 forms; the last is drawn as it is */
  {
    banner_line(line, v, form);
    if (strlen(line) <= SCR_COLS) break;
  }
  scr_row(fb, BANNER_Y, line);
  char outcome[SCR_LINE] = "  ";
  if (v->last_acked == SCR_TX_ACK)
  {
    scr_put(outcome, "ACK ");
    scr_put_dec(outcome, v->ack_rssi, 0, 0, 0);
    scr_put(outcome, "DBM SNR ");
    scr_put_dec(outcome, v->ack_snr, 0, 0, 0);
  }
  else if (v->last_acked == SCR_TX_NO_ACK) scr_put(outcome, "NO ACK");
  scr_row(fb, BANNER_Y + 8, outcome);
  oled_invert(fb, 0, BANNER_Y, OLED_W, 16);
}

void scr_home(oled_fb *fb, unsigned frame, const scr_view_t *v, int with_banner)
{
  icon(fb, scr_icon_pick(v), frame / 2U);
  readings(fb, v);
  if (with_banner) { banner(fb, v); return; }
  wind_rain_row(fb, v);
  link_row(fb, v);
}
