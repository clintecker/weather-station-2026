/* The detail screens (scr_screens.h), each a closer look at one part of what HOME sums up:
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
#include "scr_screens.h"
#include "oled_draw.h"
#include "scr_font.h"

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

/* The sparkline of d in the plot (scr_trace), scaled to at least span, in its frame: solid sides, a dotted top
   and bottom. */
static void spark(const oled_surf *s, const scr_series *d, int32_t span, unsigned frame)
{
  scr_frame(s, PLOT_X - 2, PLOT_TOP - 1, PLOT_X + PLOT_W + 1, PLOT_TOP + PLOT_H, 1);
  int32_t lo, hi;
  if (scr_spark_range(d, span, &lo, &hi))
    scr_trace(s, PLOT_X, PLOT_TOP, PLOT_W, PLOT_H, d, lo, hi, scr_grow(d->cap, frame, SCR_GROW_FRAMES));
}

/* "<prefix> lo..hi<unit>" with dec decimals of in_dec, or "<prefix> --". */
static void range_text(oled_row *line, const char *prefix, const scr_series *d, unsigned in_dec, const char *unit)
{
  *line = (oled_row){ "" };
  oled_put(line, prefix);
  int32_t lo = 0, hi = 0;
  if (scr_spark_range(d, 0, &lo, &hi) == 0U) { oled_put(line, "--"); return; }
  oled_put_dec(line, lo, in_dec, 1, 0);
  oled_put(line, "..");
  oled_put_dec(line, hi, in_dec, 1, 0);
  oled_put(line, unit);
}

/* left and right on the row at y, or left alone if they do not fit. */
static void lr_row(const oled_surf *s, int y, const char *left, const char *right)
{
  oled_row line = { "" };
  if (!oled_put_lr(&line, left, right, OLED_COLS)) oled_put(&line, left);
  scr_label(s, y, line.s, SCR_LEFT);
}

void scr_air(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  oled_row line = { "" }, left = { "DEW " }, right = { "BOX " };
  if (v->air_ok)
  {
    oled_put_dec(&line, v->air_c, 2, 1, 0);
    oled_put(&line, "^C");
    (void)oled_draw_text(s, 0, 0, line.s, &scr_big, &oled_x1);
    line.s[0] = '\0';
    oled_put_dec(&line, v->air_rh, 2, 1, 0);
    oled_put(&line, "%");
    scr_label(s, 0, "RH", SCR_RIGHT);
    scr_label(s, 8, line.s, SCR_RIGHT);
  }
  else scr_label(s, 4, "AIR NO SHT45", SCR_LEFT);
  int32_t dew;
  if (v->air_ok && scr_dew_point(v->air_c, v->air_rh, &dew)) { oled_put_dec(&left, dew, 2, 1, 0); oled_put(&left, "C"); }
  else oled_put(&left, "--");
  if (v->box_ok) { oled_put_dec(&right, v->box_c, 2, 1, 0); oled_put(&right, "C"); }
  else oled_put(&right, "--");
  lr_row(s, 18, left.s, right.s);
  scr_series d = scr_series_i16(v->air.s, v->air.n, SCR_AIR_HIST);
  spark(s, &d, AIR_SPAN, frame);
  oled_row foot, uv = { "UV " };
  range_text(&foot, "1h ", &d, 2, "C");
  if (v->uv_ok) oled_put_dec(&uv, v->uv_counts, 0, 0, 0);
  else oled_put(&uv, "NO");
  lr_row(s, FOOT_Y, foot.s, uv.s);
}

static void arrow(const oled_surf *s, enum scr_trend t)
{
  const int x = 116, y = 8;
  if (t == TREND_RISING || t == TREND_FALLING)
  {
    int d = t == TREND_RISING ? -1 : 1;   /* the head's way */
    oled_line(s, x, y - 7 * d, x, y + 7 * d, 0);
    oled_line(s, x - 5, y + 2 * d, x, y + 7 * d, 0);
    oled_line(s, x + 5, y + 2 * d, x, y + 7 * d, 0);
  }
  else if (t == TREND_STEADY)
  {
    oled_line(s, x - 8, y, x + 8, y, 0);
    oled_line(s, x + 3, y - 5, x + 8, y, 0);
    oled_line(s, x + 3, y + 5, x + 8, y, 0);
  }
}

void scr_pressure(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  static const char *const words[4] = { "TENDENCY -- (3h)", "FALLING ", "STEADY ", "RISING " };
  oled_row line = { "" };
  int32_t delta;
  enum scr_trend t = scr_tendency(v, &delta);
  if (v->press_ok)
  {
    oled_put_dec(&line, v->press_dhpa, 1, 1, 0);
    int x = oled_draw_text(s, 0, 0, line.s, &scr_big, &oled_x1);   /* the pen: after the digits' gap */
    (void)oled_text(s, x + 1, 9, "hPa", 1);
  }
  else scr_label(s, 4, "P NO BMP581", SCR_LEFT);
  arrow(s, t);
  line.s[0] = '\0';
  oled_put(&line, words[t]);
  if (t != TREND_NONE) { oled_put_dec(&line, delta, 1, 1, OLED_PLUS); oled_put(&line, "hPa/3h"); }
  scr_label(s, 18, line.s, SCR_LEFT);
  scr_series d = scr_series_i16(v->press.s, v->press.n, SCR_PRESS_HIST);
  spark(s, &d, PRESS_SPAN, frame);
  oled_row foot;
  range_text(&foot, "", &d, 1, "");
  (void)oled_put_lcr(&line, "-3h", foot.s, "now", OLED_COLS);   /* the range centred, if it leaves a space each side */
  scr_label(s, FOOT_Y, line.s, SCR_LEFT);
}

/* A gauge two rows tall across the screen, px of it filled (grown in), on a dotted track along its bottom row. */
static void bar(const oled_surf *s, int y, unsigned px, unsigned frame)
{
  oled_line(s, 0, y + 1, OLED_W - 1, y + 1, 1);
  oled_fill(s, 0, y, (int)scr_grow(px, frame, SCR_GROW_FRAMES), 2, 1);
}

static int32_t iabs32(int32_t v) { return v < 0 ? (v == INT32_MIN ? INT32_MAX : -v) : v; }

/* "<name> 12.3mA 3.30V" (plus: signed, + into the cell), or pending, or --; its bar, by the current. */
static void rail_row(const oled_surf *s, int r, const char *name, const power_rail_live_t *l, int plus, unsigned frame)
{
  oled_row line = { "" };
  int y = POWER_ROW0 + POWER_PITCH * r;
  oled_put(&line, name);
  oled_pad_to(&line, 6);
  if (!l->fitted) oled_put(&line, "--");
  else if (!l->ok) oled_put(&line, "pending");
  else
  {
    oled_put_dec(&line, l->ma_x100, 2, 1, plus ? OLED_PLUS : 0U);
    oled_put(&line, "mA");
    if (l->mv != 0) { oled_put(&line, " "); oled_put_dec(&line, l->mv, 3, 2, 0); oled_put(&line, "V"); }
  }
  scr_label(s, y, line.s, SCR_LEFT);
  bar(s, y + 8, l->fitted && l->ok ? scr_bar_px(iabs32(l->ma_x100), POWER_FULL_MA_X100, OLED_W) : 0U, frame);
}

void scr_power(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  const power_live_t *p = &v->power;
  oled_row line = { "" };
  const char *state = (p->charger & POWER_STATUS_FAULT) ? "CHGR FAULT" : (p->charger & POWER_STATUS_CHARGING) ? "CHARGING"
                      : (p->charger & POWER_STATUS_POWER_GOOD) ? "INPUT OK" : "ON BATTERY";
  (void)oled_put_lr(&line, "POWER", state, OLED_COLS);
  scr_header(s, line.s);
  line.s[0] = '\0';
  oled_put(&line, "CELL  ");
  if (!p->gauge_ok) oled_put(&line, "pending");
  else
  {
    oled_put_dec(&line, p->vcell_mv, 3, 2, 0);
    oled_put(&line, "V ");
    oled_put_dec(&line, p->soc_pct_x10, 1, 0, 0);
    oled_put(&line, "%");
  }
  scr_label(s, POWER_ROW0, line.s, SCR_LEFT);
  bar(s, POWER_ROW0 + 8, p->gauge_ok ? scr_bar_px(p->soc_pct_x10, SOC_FULL_X10, OLED_W) : 0U, frame);
  power_rail_live_t batt = { 1, p->batt_ok, p->batt_ma_x100, p->out_mv };
  rail_row(s, 1, "BATT", &batt, 1, frame);
  static const char *const names[PL_RAILS] = { "LOAD", "SOLAR", "USB" };
  for (unsigned k = 0; k < PL_RAILS; k++) rail_row(s, 2 + (int)k, names[k], &p->rail[k], 0, frame);
}

static const scr_bars_style rssi_bars = { 3, RADIO_PITCH, 1, 1 }, snr_bars = { 3, RADIO_PITCH, 0, 1 };

static void radio_bars(const oled_surf *s, const scr_view_t *v, unsigned frame)
{
  scr_series rssi = scr_series_i16(v->radio.rssi, v->radio.n, SCR_RADIO_HIST);
  scr_series snr = scr_series_i16(v->radio.snr, v->radio.n, SCR_RADIO_HIST);
  oled_line(s, 0, RSSI_TOP + RSSI_PX, OLED_W - 1, RSSI_TOP + RSSI_PX, 1);   /* the RSSI bars' floor, dotted */
  scr_bars(s, RADIO_X, RSSI_TOP + RSSI_PX, RSSI_PX, &rssi, RSSI_FLOOR, RSSI_SPAN, frame, &rssi_bars);   /* x: no ACK */
  scr_bars(s, RADIO_X, SNR_TOP + SNR_PX, SNR_PX, &snr, SNR_FLOOR, SNR_SPAN, frame, &snr_bars);
}

/* form 0 "ACK 28/30 93% BKLG 0", 1 without the percentage, 2 "28/30 Q 0". */
static void ack_form(oled_row *r, const void *ctx, unsigned form)
{
  const scr_view_t *v = ctx;
  scr_series d = scr_series_i16(v->radio.rssi, v->radio.n, SCR_RADIO_HIST);
  unsigned n = d.n, acks = scr_acks(v->radio.rssi, n);
  if (form < 2U) oled_put(r, "ACK ");
  oled_put_uint(r, acks);
  oled_put(r, "/");
  oled_put_uint(r, n);
  if (form == 0U && n != 0U) { oled_put(r, " "); oled_put_uint(r, (acks * 100U + n / 2U) / n); oled_put(r, "%"); }
  oled_put(r, form < 2U ? " BKLG " : " Q ");
  oled_put_uint(r, v->pending);
}

/* The last ACK's signal and the seconds to the next exchange: form 0 "-41dBm SNR 13", 1 "-41dBm 13dB", 2 "-41 13"
   (or the outcome), each with "NEXT 34s" at the right; form 3 form 2's signal alone. */
static void signal_form(oled_row *r, const void *ctx, unsigned form)
{
  const scr_view_t *v = ctx;
  oled_row sig = { "" }, next = { "NEXT " };
  if (v->last_acked != SCR_TX_ACK)
    oled_put(&sig, v->last_acked == SCR_TX_NONE ? "NO TX YET" : v->last_acked == SCR_TX_WAIT ? "SENT" : "NO ACK");
  else
  {
    oled_put_dec(&sig, v->ack_rssi, 0, 0, 0);
    oled_put(&sig, form == 0U ? "dBm SNR " : form == 1U ? "dBm " : " ");
    oled_put_dec(&sig, v->ack_snr, 0, 0, 0);
    if (form == 1U) oled_put(&sig, "dB");
  }
  if (form == 3U) { oled_put(r, sig.s); return; }
  int32_t secs = scr_next_tx_s(v->since_exchange_s);
  if (secs < 0) oled_put(&next, "--");
  else { oled_put_uint(&next, (uint32_t)secs); oled_put(&next, "s"); }
  scr_form_lr(r, sig.s, next.s);
}

void scr_radio(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  oled_row line = { "RADIO SF" };
  oled_put_uint(&line, v->sf);
  oled_put(&line, " BW");
  oled_put_uint(&line, v->bw_khz_div125 * 125U);
  oled_put(&line, " ");
  oled_put_dec(&line, (int32_t)v->freq_khz, 3, 1, 0);
  scr_header(s, line.s);
  radio_bars(s, v, frame);
  (void)oled_fit(&line, ack_form, v, 3, OLED_COLS);
  scr_label(s, 47, line.s, SCR_LEFT);
  (void)oled_fit(&line, signal_form, v, 4, OLED_COLS);   /* the last always fits */
  scr_label(s, FOOT_Y, line.s, SCR_LEFT);
}
