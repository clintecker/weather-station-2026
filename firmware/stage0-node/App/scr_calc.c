/* The bench screens' arithmetic and choices (scr_view.h): the display's histories, the dew point, the
 * pressure tendency, HOME's icon, the scales of the sparklines and bars, the fortune cookie and the frog's
 * mood. Pure functions of their arguments (or of the view), integer only. */
#include "scr_view.h"
#include <string.h>

#define Q16 65536
#define Q30 (1LL << 30)
#define LN2_Q30 744261118LL            /* ln 2 x 2^30, rounded */
#define MAGNUS_A_X100 1762             /* Magnus over water: a 17.62, b 243.12 degC */
#define MAGNUS_B_X100 24312
#define DEW_MIN_CENTI_C (-20000)       /* far below the formula's range; keeps b + T well above 0 */
#define RH_FULL 10000                  /* 100 % in 0.01 % */
#define S_PER_DAY 86400L
#define S_PER_H 3600L
#define DAY_FROM_H 6L
#define DAY_TO_H 18L
#define BARS_3_DBM (-85)
#define BARS_2_DBM (-100)
#define BARS_1_DBM (-115)
#define EXCHANGE_S 60U
#define LOW_CELL_X10 200U              /* 20 % */
#define DRY_CENTI_RH 3000

unsigned scr_hist_push(int16_t *s, unsigned cap, unsigned n, int16_t v)
{
  if (cap == 0U) return 0;
  if (n >= cap) { memmove(s, s + 1, (cap - 1U) * sizeof s[0]); n = cap - 1U; }
  s[n] = v;
  return n + 1U;
}

int16_t scr_hist_value(int32_t v)
{
  if (v > INT16_MAX) return INT16_MAX;
  if (v <= SCR_GAP) return (int16_t)(SCR_GAP + 1);
  return (int16_t)v;
}

int scr_hist_due(uint32_t now_ms, uint32_t *at_ms, uint32_t period_ms)
{
  if ((int32_t)(now_ms - *at_ms) < 0) return 0;
  *at_ms += period_ms;
  if ((int32_t)(now_ms - *at_ms) >= 0) *at_ms = now_ms + period_ms;   /* fell behind: from now */
  return 1;
}

/* ln n = k ln 2 + ln m, n = m 2^k with m in [1, 2); ln m = 2 atanh y, y = (m - 1) / (m + 1) <= 1/3, by its
   series to y^9 (the next term is under 2e-6). */
int32_t scr_ln_q16(uint32_t n)
{
  if (n == 0U) return 0;
  int k = 31;
  while (!(n >> k)) k--;   /* bound: at most 31 steps, n is not 0 */
  int64_t m = (int64_t)(((uint64_t)n << 30) >> k);   /* Q30, in [1, 2) */
  int64_t y = ((m - Q30) << 30) / (m + Q30);
  int64_t y2 = (y * y) >> 30, term = y, sum = 0;
  for (int i = 1; i <= 9; i += 2)
  {
    sum += term / i;
    term = (term * y2) >> 30;
  }
  int64_t q30 = k * LN2_Q30 + 2 * sum;
  return (int32_t)((q30 + (1LL << 13)) >> 14);
}

static int64_t div_round(int64_t a, int64_t b)
{
  if (b < 0) { a = -a; b = -b; }
  return a >= 0 ? (a + b / 2) / b : -((-a + b / 2) / b);
}

int scr_dew_point(int32_t centi_c, int32_t centi_rh, int32_t *centi_dew)
{
  if (centi_rh <= 0 || centi_c <= DEW_MIN_CENTI_C) return 0;
  if (centi_rh > RH_FULL) centi_rh = RH_FULL;
  /* gamma = ln(RH) + a T / (b + T), Q16 */
  int64_t g = (int64_t)scr_ln_q16((uint32_t)centi_rh) - scr_ln_q16(RH_FULL)
              + div_round((int64_t)MAGNUS_A_X100 * centi_c * Q16, 100LL * ((int64_t)MAGNUS_B_X100 + centi_c));
  int64_t a = (int64_t)MAGNUS_A_X100 * Q16 / 100;
  if (g >= a) return 0;   /* only a temperature far past the formula's range comes near */
  *centi_dew = (int32_t)div_round((int64_t)MAGNUS_B_X100 * g, a - g);   /* b gamma / (a - gamma); gamma < a */
  return 1;
}

enum scr_trend scr_tendency(const scr_view_t *v, int32_t *delta_dhpa)
{
  *delta_dhpa = 0;
  if (!v->press_ok || v->press_n < SCR_PRESS_HIST || v->press_hist[0] == SCR_GAP) return TREND_NONE;
  int64_t d = (int64_t)v->press_dhpa - v->press_hist[0];
  *delta_dhpa = (int32_t)(d > INT32_MAX ? INT32_MAX : d < -INT32_MAX ? -INT32_MAX : d);
  if (*delta_dhpa >= SCR_TREND_DHPA) return TREND_RISING;
  if (*delta_dhpa <= -SCR_TREND_DHPA) return TREND_FALLING;
  return TREND_STEADY;
}

int scr_is_day(uint32_t utc, int32_t offset_min)
{
  if (utc == 0U) return -1;
  int64_t local = ((int64_t)utc + (int64_t)offset_min * 60) % S_PER_DAY;
  if (local < 0) local += S_PER_DAY;
  int64_t h = local / S_PER_H;
  return h >= DAY_FROM_H && h < DAY_TO_H;
}

unsigned scr_rain_tips(const uint8_t *per_min, unsigned n, unsigned minutes)
{
  unsigned sum = 0;
  for (unsigned i = n > minutes ? n - minutes : 0U; i < n; i++) sum += per_min[i];
  return sum;
}

enum scr_icon scr_icon_pick(const scr_view_t *v)
{
  int frost = v->air_ok && v->air_c < 0;
  if (scr_rain_tips(v->rain.per_min, RAIN_HIST_MINUTES, SCR_RAIN_RECENT_MIN) != 0U) return frost ? ICON_SNOW : ICON_RAIN;
  if (frost) return ICON_SNOW;
  if (v->wind.speed_cms > SCR_WINDY_CMS) return ICON_WIND;
  if (v->air_ok && v->air_rh >= SCR_CLOUDY_CENTI_RH) return ICON_CLOUD;
  return scr_is_day(v->utc, SCR_UTC_OFFSET_MIN) == 0 ? ICON_MOON : ICON_SUN;
}

unsigned scr_bar_px(int32_t v, int32_t full, unsigned px)
{
  if (v <= 0) return 0;
  if (full <= 0 || v >= full) return px;
  return (unsigned)(((uint64_t)v * px + (uint64_t)full - 1U) / (uint64_t)full);
}

unsigned scr_spark_range(const int16_t *s, unsigned n, int32_t min_span, int32_t *lo, int32_t *hi)
{
  unsigned valid = 0;
  int32_t a = 0, b = 0;
  for (unsigned i = 0; i < n; i++)
  {
    if (s[i] == SCR_GAP) continue;
    if (valid == 0U || s[i] < a) a = s[i];
    if (valid == 0U || s[i] > b) b = s[i];
    valid++;
  }
  if (valid == 0U) return 0;
  if (b - a < min_span)
  {
    a = (a + b - min_span) / 2;   /* about the middle */
    b = a + min_span;
  }
  *lo = a; *hi = b;
  return valid;
}

int scr_spark_y(int32_t v, int32_t lo, int32_t hi, int top, int h)
{
  if (h <= 1 || hi <= lo) return top + (h > 1 ? h / 2 : 0);
  if (v > hi) v = hi;
  if (v < lo) v = lo;
  return top + (int)div_round((int64_t)(hi - v) * (h - 1), (int64_t)hi - lo);
}

unsigned scr_signal_bars(int16_t rssi)
{
  if (rssi >= BARS_3_DBM) return 3;
  if (rssi >= BARS_2_DBM) return 2;
  return rssi >= BARS_1_DBM ? 1U : 0U;
}

unsigned scr_acks(const int16_t *rssi, unsigned n)
{
  unsigned acks = 0;
  for (unsigned i = 0; i < n; i++) acks += rssi[i] != SCR_GAP;
  return acks;
}

int32_t scr_next_tx_s(uint32_t since_exchange_s)
{
  if (since_exchange_s == SCR_NONE_S) return -1;
  return (int32_t)(EXCHANGE_S - since_exchange_s % EXCHANGE_S);
}

/* The fortune cookie's conditions, in the order they are tried; its lines in the same order. */
enum fortune_cond { F_NO_ACK, F_LOW_CELL, F_RAIN, F_FROST, F_HOT, F_WIND, F_DAMP, F_DRY, F_FALLING, F_RISING, F_CALM,
                    F_CONDS };
static const uint8_t fortune_cond[SCR_FORTUNES] = { F_NO_ACK, F_LOW_CELL, F_RAIN, F_RAIN, F_FROST, F_HOT, F_WIND, F_DAMP,
                                                    F_DRY, F_FALLING, F_RISING, F_CALM, F_CALM, F_CALM, F_CALM };
const char *const scr_fortunes[SCR_FORTUNES] = {
  "The gateway is\nsilent. It is only\nthinking of you.",
  "Low battery.\nRest is also\na feature.",
  "Rain is falling.\nThe bucket keeps\ncount so you don't.",
  "Wet outside. Your\nsocks have been\nwarned.",
  "Below zero.\nCold hands,\nwarm firmware.",
  "It is hot. Even\nthe electrons are\nsweating.",
  "A great wind blows.\nHold on to your\nhat. And packets.",
  "The air is soup.\nDo not drink it.",
  "Dry air ahead.\nTouch a doorknob,\nmake a spark.",
  "The barometer sinks.\nAn umbrella would\nnot hurt.",
  "Pressure rises.\nSo will your mood.",
  "Calm air, clear\nlink. A fine day\nto solder.",
  "No news is good\nnews. Also, no wind.",
  "Your future holds\n60 more packets\nan hour.",
  "A watched sensor\nnever drifts.",
};

static int fortune_holds(enum fortune_cond c, const scr_view_t *v)
{
  int32_t delta;
  switch (c)
  {
  case F_NO_ACK: return v->last_acked == SCR_TX_NO_ACK;
  case F_LOW_CELL: return v->power.gauge_ok && v->power.soc_pct_x10 < LOW_CELL_X10;
  case F_RAIN: return scr_rain_tips(v->rain.per_min, RAIN_HIST_MINUTES, SCR_RAIN_RECENT_MIN) != 0U;
  case F_FROST: return v->air_ok && v->air_c < 0;
  case F_HOT: return v->air_ok && v->air_c >= SCR_HOT_CENTI_C;
  case F_WIND: return v->wind.speed_cms > SCR_WINDY_CMS;
  case F_DAMP: return v->air_ok && v->air_rh >= SCR_CLOUDY_CENTI_RH;
  case F_DRY: return v->air_ok && v->air_rh < DRY_CENTI_RH;
  case F_FALLING: return scr_tendency(v, &delta) == TREND_FALLING;
  case F_RISING: return scr_tendency(v, &delta) == TREND_RISING;
  default: return 1;
  }
}

unsigned scr_fortune_pick(const scr_view_t *v)
{
  enum fortune_cond c = F_CALM;
  for (unsigned i = 0; i < F_CONDS; i++)
    if (fortune_holds((enum fortune_cond)i, v)) { c = (enum fortune_cond)i; break; }
  unsigned first = 0, count = 0;
  for (unsigned i = 0; i < SCR_FORTUNES; i++)
    if (fortune_cond[i] == c) { if (count == 0U) first = i; count++; }
  return first + v->last_seq % count;   /* every condition has a line */
}

const char *const scr_mood_names[7] = { "happy", "sleepy", "mopey", "soggy", "chilly", "breezy", "toasty" };

enum scr_mood scr_frog_mood(const scr_view_t *v)
{
  enum scr_icon i = scr_icon_pick(v);
  if (i == ICON_RAIN) return MOOD_SOGGY;
  if (i == ICON_SNOW) return MOOD_CHILLY;
  if (i == ICON_WIND) return MOOD_BREEZY;
  if (v->air_ok && v->air_c >= SCR_HOT_CENTI_C) return MOOD_TOASTY;
  if (i == ICON_CLOUD) return MOOD_MOPEY;
  return i == ICON_MOON ? MOOD_SLEEPY : MOOD_HAPPY;
}

unsigned scr_matrix_speed(unsigned tips10)
{
  if (tips10 == 0U) return 1;
  return tips10 < 5U ? 2U : 3U;
}

uint32_t scr_hash(uint32_t a, uint32_t b)
{
  uint32_t h = a * 0x9E3779B1U ^ (b + 0x7F4A7C15U) * 0x85EBCA77U;
  h ^= h >> 15;
  h *= 0x2C1B3C6DU;
  return h ^ (h >> 13);
}
