/* The detail screens (scr_view.h), each a closer look at one part of what HOME sums up:
 *   AIR       the SHT45 in big digits and its RH; the dew point (scr_dew_point) and the SHTC3; the last
 *             hour, a sample a minute, as a sparkline; its least and largest, and the UV counts.
 *   PRESSURE  the BMP581 in big digits and the 3-hour tendency's arrow (scr_tendency); the change; the
 *             last 3 h, a sample every 5 minutes, as a sparkline; its least and largest.
 *   POWER     the charger's state; the cell, the battery current and the load, solar and USB-C rails, each
 *             a row and a bar under it (pending: fitted but not answering; --: not in the profile).
 *   RADIO     the radio settings; the last 30 frames' ACK RSSI and SNR as bars, an x for no ACK; the ACK
 *             rate, the backlog; the last ACK's signal and the seconds to the next exchange.
 * A sparkline is scaled to its samples (scr_spark_range, at least 1.0 degC or 1.0 hPa tall), the newest at
 * the right, broken at a gap; the lines and bars grow in over the screen's 8 frames. */
#include "scr_view.h"
#include <string.h>
#include "oled_draw.h"

#define GROW_FRAMES 8U
#define PLOT_TOP 28
#define PLOT_H 24
#define PLOT_X 4
#define PLOT_W 120
#define FOOT_Y 56
#define AIR_SPAN 100                   /* 1.0 degC */
#define PRESS_SPAN 10                  /* 1.0 hPa */
#define POWER_ROW0 9
#define POWER_PITCH 11
#define POWER_FULL_MA_X100 50000       /* 500 mA: every current bar's full scale */
#define SOC_FULL_X10 1000
#define RSSI_FLOOR (-130)              /* the RSSI bars: -130 to -30 dBm */
#define RSSI_SPAN 100
#define RSSI_TOP 10
#define RSSI_PX 24
#define SNR_FLOOR (-20)                /* the SNR bars: -20 to +15 dB */
#define SNR_SPAN 35
#define SNR_TOP 36
#define SNR_PX 10
#define RADIO_X 4
#define RADIO_PITCH 4

static unsigned grown(unsigned frame) { return frame + 1U < GROW_FRAMES ? frame + 1U : GROW_FRAMES; }

static unsigned upto(unsigned n, unsigned cap) { return n > cap ? cap : n; }   /* a count no larger than its history */

/* The sparkline of s (n of cap samples) in the plot, the first `frame`'s share of its slots drawn; the
   sides and a dotted top and bottom around it. Returns how many samples are not gaps, and their range. */
static unsigned spark(oled_fb *fb, const int16_t *s, unsigned n, unsigned cap, int32_t span, unsigned frame,
                      int32_t *lo, int32_t *hi)
{
  oled_line(fb, PLOT_X - 2, PLOT_TOP - 1, PLOT_X + PLOT_W + 1, PLOT_TOP - 1, 1);
  oled_line(fb, PLOT_X - 2, PLOT_TOP + PLOT_H, PLOT_X + PLOT_W + 1, PLOT_TOP + PLOT_H, 1);
  oled_line(fb, PLOT_X - 2, PLOT_TOP - 1, PLOT_X - 2, PLOT_TOP + PLOT_H, 0);
  oled_line(fb, PLOT_X + PLOT_W + 1, PLOT_TOP - 1, PLOT_X + PLOT_W + 1, PLOT_TOP + PLOT_H, 0);
  n = upto(n, cap);
  unsigned valid = scr_spark_range(s, n, span, lo, hi);
  if (valid == 0U) return 0;
  unsigned shown = cap * grown(frame) / GROW_FRAMES;
  int px = 0, py = 0, prev = 0;
  for (unsigned i = 0; i < n; i++)
  {
    unsigned slot = cap - n + i;
    if (slot >= shown) break;
    if (s[i] == SCR_GAP) { prev = 0; continue; }
    int x = PLOT_X + (int)(slot * (PLOT_W - 1U) / (cap - 1U)), y = scr_spark_y(s[i], *lo, *hi, PLOT_TOP, PLOT_H);
    if (prev) oled_line(fb, px, py, x, y, 0);
    else oled_set(fb, x, y, 1);
    px = x; py = y; prev = 1;
  }
  return valid;
}

/* "<prefix> lo..hi<unit>" with dec decimals of in_dec, or "<prefix> --". */
static void range_text(char *line, const char *prefix, unsigned valid, const int16_t *s, unsigned n, unsigned in_dec,
                       const char *unit)
{
  line[0] = '\0';
  scr_put(line, prefix);
  int32_t lo = 0, hi = 0;
  if (valid == 0U || scr_spark_range(s, n, 0, &lo, &hi) == 0U) { scr_put(line, "--"); return; }
  scr_put_dec(line, lo, in_dec, 1, 0);
  scr_put(line, "..");
  scr_put_dec(line, hi, in_dec, 1, 0);
  scr_put(line, unit);
}

void scr_air(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  char line[SCR_LINE] = "", left[SCR_LINE] = "DEW ", right[SCR_LINE] = "BOX ";
  if (v->air_ok)
  {
    scr_put_dec(line, v->air_c, 2, 1, 0);
    scr_put(line, "^C");
    (void)scr_big_text(fb, 0, 0, line);
    line[0] = '\0';
    scr_put_dec(line, v->air_rh, 2, 1, 0);
    scr_put(line, "%");
    scr_row_right(fb, 0, "RH");
    scr_row_right(fb, 8, line);
  }
  else scr_row(fb, 4, "AIR NO SHT45");
  int32_t dew;
  if (v->air_ok && scr_dew_point(v->air_c, v->air_rh, &dew)) { scr_put_dec(left, dew, 2, 1, 0); scr_put(left, "C"); }
  else scr_put(left, "--");
  if (v->box_ok) { scr_put_dec(right, v->box_c, 2, 1, 0); scr_put(right, "C"); }
  else scr_put(right, "--");
  if (scr_put_lr(line, left, right)) scr_row(fb, 18, line);
  else scr_row(fb, 18, left);
  int32_t lo, hi;
  unsigned valid = spark(fb, v->air_hist, v->air_n, SCR_AIR_HIST, AIR_SPAN, frame, &lo, &hi);
  char foot[SCR_LINE], uv[SCR_LINE] = "UV ";
  range_text(foot, "1h ", valid, v->air_hist, upto(v->air_n, SCR_AIR_HIST), 2, "C");
  if (v->uv_ok) scr_put_dec(uv, v->uv_counts, 0, 0, 0);
  else scr_put(uv, "NO");
  if (scr_put_lr(line, foot, uv)) scr_row(fb, FOOT_Y, line);
  else scr_row(fb, FOOT_Y, foot);
}

static void arrow(oled_fb *fb, enum scr_trend t)
{
  const int x = 116, y = 8;
  if (t == TREND_RISING || t == TREND_FALLING)
  {
    int d = t == TREND_RISING ? -1 : 1;   /* the head's way */
    oled_line(fb, x, y - 7 * d, x, y + 7 * d, 0);
    oled_line(fb, x - 5, y + 2 * d, x, y + 7 * d, 0);
    oled_line(fb, x + 5, y + 2 * d, x, y + 7 * d, 0);
  }
  else if (t == TREND_STEADY)
  {
    oled_line(fb, x - 8, y, x + 8, y, 0);
    oled_line(fb, x + 3, y - 5, x + 8, y, 0);
    oled_line(fb, x + 3, y + 5, x + 8, y, 0);
  }
}

void scr_pressure(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  static const char *const words[4] = { "TENDENCY -- (3h)", "FALLING ", "STEADY ", "RISING " };
  char line[SCR_LINE] = "";
  int32_t delta;
  enum scr_trend t = scr_tendency(v, &delta);
  if (v->press_ok)
  {
    scr_put_dec(line, v->press_dhpa, 1, 1, 0);
    int x = scr_big_text(fb, 0, 0, line);
    (void)oled_text(fb, x + 3, 9, "hPa", 1);
  }
  else scr_row(fb, 4, "P NO BMP581");
  arrow(fb, t);
  line[0] = '\0';
  scr_put(line, words[t]);
  if (t != TREND_NONE) { scr_put_dec(line, delta, 1, 1, 1); scr_put(line, "hPa/3h"); }
  scr_row(fb, 18, line);
  int32_t lo, hi;
  unsigned valid = spark(fb, v->press_hist, v->press_n, SCR_PRESS_HIST, PRESS_SPAN, frame, &lo, &hi);
  char foot[SCR_LINE];
  range_text(foot, "", valid, v->press_hist, upto(v->press_n, SCR_PRESS_HIST), 1, "");
  if (!scr_put_lr(line, "-3h", "now")) line[0] = '\0';
  size_t at = (SCR_COLS - strlen(foot)) / 2U;   /* the range centred between -3h and now, a space each side */
  if (strlen(foot) + 8U <= SCR_COLS) memcpy(line + at, foot, strlen(foot));
  scr_row(fb, FOOT_Y, line);
}

static void bar(oled_fb *fb, int y, unsigned px, unsigned frame)
{
  oled_line(fb, 0, y + 1, OLED_W - 1, y + 1, 1);   /* the track */
  oled_fill(fb, 0, y, (int)(px * grown(frame) / GROW_FRAMES), 2, 1);
}

static int32_t iabs32(int32_t v) { return v < 0 ? (v == INT32_MIN ? INT32_MAX : -v) : v; }

/* "<name> 12.3mA 3.30V" (plus: signed, + into the cell), or pending, or --; its bar, by the current. */
static void rail_row(oled_fb *fb, int r, const char *name, const power_rail_live_t *l, int plus, unsigned frame)
{
  char line[SCR_LINE] = "";
  int y = POWER_ROW0 + POWER_PITCH * r;
  scr_put(line, name);
  scr_pad_to(line, 6);
  if (!l->fitted) scr_put(line, "--");
  else if (!l->ok) scr_put(line, "pending");
  else
  {
    scr_put_dec(line, l->ma_x100, 2, 1, plus);
    scr_put(line, "mA");
    if (l->mv != 0) { scr_put(line, " "); scr_put_dec(line, l->mv, 3, 2, 0); scr_put(line, "V"); }
  }
  scr_row(fb, y, line);
  bar(fb, y + 8, l->fitted && l->ok ? scr_bar_px(iabs32(l->ma_x100), POWER_FULL_MA_X100, OLED_W) : 0U, frame);
}

void scr_power(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  const power_live_t *p = &v->power;
  char line[SCR_LINE] = "";
  const char *state = (p->charger & POWER_STATUS_FAULT) ? "CHGR FAULT" : (p->charger & POWER_STATUS_CHARGING) ? "CHARGING"
                      : (p->charger & POWER_STATUS_POWER_GOOD) ? "INPUT OK" : "ON BATTERY";
  (void)scr_put_lr(line, "POWER", state);
  scr_header(fb, line);
  line[0] = '\0';
  scr_put(line, "CELL  ");
  if (!p->gauge_ok) scr_put(line, "pending");
  else
  {
    scr_put_dec(line, p->vcell_mv, 3, 2, 0);
    scr_put(line, "V ");
    scr_put_dec(line, p->soc_pct_x10, 1, 0, 0);
    scr_put(line, "%");
  }
  scr_row(fb, POWER_ROW0, line);
  bar(fb, POWER_ROW0 + 8, p->gauge_ok ? scr_bar_px(p->soc_pct_x10, SOC_FULL_X10, OLED_W) : 0U, frame);
  power_rail_live_t batt = { 1, p->batt_ok, p->batt_ma_x100, p->out_mv };
  rail_row(fb, 1, "BATT", &batt, 1, frame);
  static const char *const names[PL_RAILS] = { "LOAD", "SOLAR", "USB" };
  for (unsigned k = 0; k < PL_RAILS; k++) rail_row(fb, 2 + (int)k, names[k], &p->rail[k], 0, frame);
}

static void radio_bars(oled_fb *fb, const scr_view_t *v, unsigned frame)
{
  unsigned n = upto(v->radio_n, SCR_RADIO_HIST), g = grown(frame);
  oled_line(fb, 0, RSSI_TOP + RSSI_PX, OLED_W - 1, RSSI_TOP + RSSI_PX, 1);
  for (unsigned i = 0; i < n; i++)
  {
    int x = RADIO_X + RADIO_PITCH * (int)(SCR_RADIO_HIST - n + i);
    if (v->radio_rssi[i] == SCR_GAP)
    {
      oled_line(fb, x, RSSI_TOP + RSSI_PX - 3, x + 2, RSSI_TOP + RSSI_PX - 1, 0);
      oled_line(fb, x + 2, RSSI_TOP + RSSI_PX - 3, x, RSSI_TOP + RSSI_PX - 1, 0);
      continue;
    }
    int r = (int)(scr_bar_px(v->radio_rssi[i] - RSSI_FLOOR, RSSI_SPAN, RSSI_PX) * g / GROW_FRAMES);
    int s = (int)(scr_bar_px(v->radio_snr[i] - SNR_FLOOR, SNR_SPAN, SNR_PX) * g / GROW_FRAMES);
    oled_fill(fb, x, RSSI_TOP + RSSI_PX - r, 3, r, 1);
    oled_fill(fb, x, SNR_TOP + SNR_PX - s, 3, s, 1);
  }
}

/* form 0 "ACK 28/30 93% BKLG 0", 1 without the percentage, 2 "28/30 Q 0". */
static void ack_line(char *line, const scr_view_t *v, unsigned form)
{
  unsigned n = upto(v->radio_n, SCR_RADIO_HIST), acks = scr_acks(v->radio_rssi, n);
  line[0] = '\0';
  if (form < 2U) scr_put(line, "ACK ");
  scr_put_uint(line, acks);
  scr_put(line, "/");
  scr_put_uint(line, n);
  if (form == 0U && n != 0U) { scr_put(line, " "); scr_put_uint(line, (acks * 100U + n / 2U) / n); scr_put(line, "%"); }
  scr_put(line, form < 2U ? " BKLG " : " Q ");
  scr_put_uint(line, v->pending);
}

/* The last ACK's signal: form 0 "-41dBm SNR 13", 1 "-41dBm 13dB", 2 "-41 13"; or the outcome. */
static void signal_text(char *sig, const scr_view_t *v, unsigned form)
{
  sig[0] = '\0';
  if (v->last_acked != SCR_TX_ACK)
  {
    scr_put(sig, v->last_acked == SCR_TX_NONE ? "NO TX YET" : v->last_acked == SCR_TX_WAIT ? "SENT" : "NO ACK");
    return;
  }
  scr_put_dec(sig, v->ack_rssi, 0, 0, 0);
  scr_put(sig, form < 2U ? (form == 0U ? "dBm SNR " : "dBm ") : " ");
  scr_put_dec(sig, v->ack_snr, 0, 0, 0);
  if (form == 1U) scr_put(sig, "dB");
}

void scr_radio(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  char line[SCR_LINE] = "RADIO SF";
  scr_put_uint(line, v->sf);
  scr_put(line, " BW");
  scr_put_uint(line, v->bw_khz_div125 * 125U);
  scr_put(line, " ");
  scr_put_dec(line, v->freq_khz, 3, 1, 0);
  scr_header(fb, line);
  radio_bars(fb, v, frame);
  for (unsigned form = 0; form < 3U; form++)   /* bound: 3 forms; the last is drawn as it is */
  {
    ack_line(line, v, form);
    if (strlen(line) <= SCR_COLS) break;
  }
  scr_row(fb, 47, line);
  char next[SCR_LINE] = "NEXT ";
  int32_t s = scr_next_tx_s(v->since_exchange_s);
  if (s < 0) scr_put(next, "--");
  else { scr_put_uint(next, (uint32_t)s); scr_put(next, "s"); }
  char sig[SCR_LINE] = "";
  for (unsigned form = 0; form < 3U; form++)   /* bound: 3 forms; the last always fits */
  {
    signal_text(sig, v, form);
    if (scr_put_lr(line, sig, next)) break;
    line[0] = '\0';
    scr_put(line, sig);
  }
  scr_row(fb, FOOT_Y, line);
}
