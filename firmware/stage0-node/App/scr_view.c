/* The bench screens' layout C, its packet banner, and the text helpers: see scr_view.h. The rows
 * (design spec, "The screen"):
 *     AIR  23.1C  50.8%        SHT45            (AIR NO SHT45)
 *     BOX  22.9C  52.2%        SHTC3            (BOX NO SHTC3)
 *     P 983.0hPa   UV 0        BMP581, LTR390   (P NO BMP581, UV NO)
 *     WIND 1.3m/s NE G2.7      speed, vane point (- out of the table), gust
 *     RAIN 2 TIPS 0.56mm       tips since boot
 *     BATT +37.6mA 3.85V       the battery INA228 and OUT (NO INA228)
 *     CELL 3.85V 78% CHG       MAX17048, CHG while charging (NO MAX17048)
 *     TX 1233 ACK 58s AGO      the last frame, its outcome, its age
 * The banner inverts the bottom two rows: "  SENDING TX 1234" (or "  TX 1234 +5 BACKLOG", "+HEALTH"
 * for a health report, when frames followed the live one), then the outcome, "  ACK -41DBM SNR 13" or
 * "  NO ACK". A row longer than the 21 columns takes a shorter form (WND for WIND; BKLG, HLTH and no
 * indent in the banner) rather than lose its last characters. */
#include "scr_view.h"
#include <string.h>
#include "oled_draw.h"

#define ROW_PX 8                       /* 7-pixel glyphs and a 1-pixel gap: eight rows */
#define TH_COL 5                       /* AIR and BOX values start here */
#define UV_COL 13                      /* "UV" starts here after a pressure */
#define SCREEN_COLS 21
#define BANNER_ROW 6
#define RAIN_TENTH_UM_PER_TIP 2794     /* 0.2794 mm a tip (SEN-15901), in 10^-4 mm */
#define RAIN_TIPS_MAX 1000000U         /* 279 m of rain: more reads as this */
#define DEC_DIGITS 24                  /* a uint64_t's 20 digits, a point, a sign */
#define DEC_MAX 6U                     /* decimals scr_put_dec takes: the buffer holds 20 digits */

const char *const scr_point_names[16] = { "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" };

void scr_put(char *line, const char *s)
{
  size_t used = strlen(line);
  /* bound: at most SCR_LINE - 1 characters are kept */
  while (*s && used + 1 < SCR_LINE) line[used++] = *s++;
  line[used] = '\0';
}

void scr_put_dec(char *line, int64_t v, unsigned in_dec, unsigned out_dec, int plus)
{
  if (in_dec > DEC_MAX) in_dec = DEC_MAX;
  if (out_dec > in_dec) out_dec = in_dec;
  uint64_t m = v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v, div = 1;
  for (unsigned i = out_dec; i < in_dec; i++) div *= 10U;
  m = (m + div / 2U) / div;
  int negative = v < 0 && m != 0;
  char num[DEC_DIGITS];
  unsigned at = DEC_DIGITS - 1, digits = 0;
  num[at] = '\0';
  /* bound: at most 20 digits and a point; at > 1 throughout, as a uint64_t has 20 digits */
  do
  {
    if (out_dec != 0 && digits == out_dec) num[--at] = '.';
    num[--at] = (char)('0' + m % 10U);
    m /= 10U;
    digits++;
  } while (m != 0 || digits <= out_dec);
  if (negative) num[--at] = '-';
  else if (plus) num[--at] = '+';
  scr_put(line, &num[at]);
}

void scr_put_uint(char *line, uint32_t v) { scr_put_dec(line, v, 0, 0, 0); }

void scr_pad_to(char *line, unsigned col)
{
  size_t used = strlen(line);
  /* bound: at most SCR_LINE - 1 characters */
  while (used < col && used + 1 < SCR_LINE) line[used++] = ' ';
  line[used] = '\0';
}

static void row(oled_fb *fb, int r, const char *text) { (void)oled_text(fb, 0, r * ROW_PX, text, 1); }

/* "<label>  23.1C  50.8%", or "<label> NO <part>". */
static void th_row(oled_fb *fb, int r, const char *label, const char *part, int ok, int32_t centi_c, int32_t centi_rh)
{
  char line[SCR_LINE] = "";
  scr_put(line, label);
  if (!ok) { scr_put(line, " NO "); scr_put(line, part); row(fb, r, line); return; }
  scr_pad_to(line, TH_COL);
  scr_put_dec(line, centi_c, 2, 1, 0);
  scr_put(line, "C  ");
  scr_put_dec(line, centi_rh, 2, 1, 0);
  scr_put(line, "%");
  row(fb, r, line);
}

static void press_row(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE] = "P ";
  if (!v->press_ok) scr_put(line, "NO BMP581 UV ");
  else
  {
    scr_put_dec(line, v->press_dhpa, 1, 1, 0);
    scr_put(line, "hPa ");
    scr_pad_to(line, UV_COL);
    scr_put(line, "UV ");
  }
  if (!v->uv_ok) scr_put(line, "NO");
  else scr_put_dec(line, v->uv_counts, 0, 0, 0);
  row(fb, 2, line);
}

static void wind_line(char *line, const char *label, const scr_view_t *v)
{
  line[0] = '\0';
  scr_put(line, label);
  scr_put_dec(line, v->wind.speed_cms, 2, 1, 0);
  scr_put(line, "m/s ");
  scr_put(line, v->wind.point >= 0 && v->wind.point < 16 ? scr_point_names[v->wind.point] : "-");
  scr_put(line, " G");
  scr_put_dec(line, v->wind.gust_cms, 2, 1, 0);
}

static void wind_rain_rows(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE];
  wind_line(line, "WIND ", v);
  if (strlen(line) > SCREEN_COLS) wind_line(line, "WND ", v);   /* 10 m/s or more both, and a 3-letter point */
  row(fb, 3, line);

  char rain[SCR_LINE] = "RAIN ";
  uint32_t tips = v->tips > RAIN_TIPS_MAX ? RAIN_TIPS_MAX : v->tips;
  scr_put_uint(rain, v->tips);
  scr_put(rain, " TIPS ");
  scr_put_dec(rain, (int64_t)tips * RAIN_TENTH_UM_PER_TIP, 4, 2, 0);
  scr_put(rain, "mm");
  row(fb, 4, rain);
}

static void batt_row(oled_fb *fb, const power_live_t *p)
{
  char line[SCR_LINE] = "BATT ";
  if (!p->batt_ok) scr_put(line, "NO INA228");
  else
  {
    scr_put_dec(line, p->batt_ma_x100, 2, 1, 1);
    scr_put(line, "mA");
    if (p->out_mv != 0) { scr_put(line, " "); scr_put_dec(line, p->out_mv, 3, 2, 0); scr_put(line, "V"); }
  }
  row(fb, 5, line);
}

static void cell_row(oled_fb *fb, const power_live_t *p)
{
  char line[SCR_LINE] = "CELL ";
  if (!p->gauge_ok) scr_put(line, "NO MAX17048");
  else
  {
    scr_put_dec(line, p->vcell_mv, 3, 2, 0);
    scr_put(line, "V ");
    scr_put_dec(line, p->soc_pct_x10, 1, 0, 0);
    scr_put(line, "%");
    if (p->charging) scr_put(line, " CHG");
  }
  row(fb, 6, line);
}

/* An age in three characters or so: 58s, then minutes, then hours. */
static void put_age(char *line, uint32_t s)
{
  if (s < 100U) { scr_put_uint(line, s); scr_put(line, "s"); }
  else if (s < 6000U) { scr_put_uint(line, s / 60U); scr_put(line, "m"); }
  else { scr_put_uint(line, s / 3600U); scr_put(line, "h"); }
}

static void tx_row(oled_fb *fb, const scr_view_t *v)
{
  char line[SCR_LINE] = "TX ";
  if (v->last_acked == SCR_TX_NONE) { scr_put(line, "NONE YET"); row(fb, 7, line); return; }
  scr_put_uint(line, v->last_seq);
  scr_put(line, v->last_acked == SCR_TX_ACK ? " ACK " : v->last_acked == SCR_TX_NO_ACK ? " NO ACK " : " SENT ");
  put_age(line, v->last_age_s);
  if (strlen(line) + 4U <= SCREEN_COLS) scr_put(line, " AGO");
  row(fb, 7, line);
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
  /* bound: 3 forms; the last is drawn as it is */
  for (unsigned form = 0; form < 3U; form++)
  {
    banner_line(line, v, form);
    if (strlen(line) <= SCREEN_COLS) break;
  }
  row(fb, BANNER_ROW, line);

  char outcome[SCR_LINE] = "  ";
  if (v->last_acked == SCR_TX_ACK)
  {
    scr_put(outcome, "ACK ");
    scr_put_dec(outcome, v->ack_rssi, 0, 0, 0);
    scr_put(outcome, "DBM SNR ");
    scr_put_dec(outcome, v->ack_snr, 0, 0, 0);
  }
  else if (v->last_acked == SCR_TX_NO_ACK) scr_put(outcome, "NO ACK");
  row(fb, BANNER_ROW + 1, outcome);
  oled_invert(fb, 0, BANNER_ROW * ROW_PX, OLED_W, 2 * ROW_PX);
}

/* Layout C; with_banner: the bottom two rows are the banner's. */
static void layout_c(oled_fb *fb, const scr_view_t *v, int with_banner)
{
  th_row(fb, 0, "AIR", "SHT45", v->air_ok, v->air_c, v->air_rh);
  th_row(fb, 1, "BOX", "SHTC3", v->box_ok, v->box_c, v->box_rh);
  press_row(fb, v);
  wind_rain_rows(fb, v);
  batt_row(fb, &v->power);
  if (with_banner) { banner(fb, v); return; }
  cell_row(fb, &v->power);
  tx_row(fb, v);
}

unsigned scr_frames(enum scr_id id)
{
  switch (id)
  {
  case SCR_NORMAL: return 1U;
  case SCR_BANNER: return 24U;
  case SCR_BURST: return 16U;
  case SCR_HACK: return 24U;
  default: return 64U;
  }
}

void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v)
{
  oled_clear(fb);
  if (frame >= scr_frames(id)) frame = scr_frames(id) - 1U;
  switch (id)
  {
  case SCR_BURST: scr_burst(fb, frame, v); break;
  case SCR_BANNER: layout_c(fb, v, 1); break;
  case SCR_SCOPE: scr_scope(fb, v); break;
  case SCR_VANE: scr_vane(fb, frame, v); break;
  case SCR_SYSTEM: scr_system(fb, frame, v); break;
  case SCR_BOOT: scr_boot(fb, frame, v); break;
  case SCR_HACK: scr_hack(fb, frame); break;
  default: layout_c(fb, v, 0); break;
  }
}
