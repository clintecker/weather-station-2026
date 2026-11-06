/* The bench screens' arithmetic and choices (App/scr_calc.c), every one pure: histories, dew point,
 * tendency, the icon, scales, the fortune, the frog's mood, the digital rain. tests/test_scr_calc.py.
 * Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_CALC_H
#define SCR_CALC_H

#include <stdint.h>
#include "scr_view.h"

/* The history s (n of cap samples, oldest first) with v added as the newest; the oldest goes when it is
   full. Returns the new n. */
unsigned scr_hist_push(int16_t *s, unsigned cap, unsigned n, int16_t v);
int16_t scr_hist_value(int32_t v);   /* v as a sample: clipped to int16_t, never SCR_GAP */
/* 1 when a sample is due at now_ms, and the next time (*at_ms, one period on); a clock that fell a period
   or more behind starts again from now, so there is no burst of samples. Wraps safely. */
int scr_hist_due(uint32_t now_ms, uint32_t *at_ms, uint32_t period_ms);

/* ln(n) for n >= 1 in 1/65536 (Q16), to about 1e-5; 0 for n 0. */
int32_t scr_ln_q16(uint32_t n);
/* The dew point (Magnus, a 17.62, b 243.12 degC: WMO-No. 8, 2018, annex 4.B) of centi_c and centi_rh, in
   0.01 degC: 1 with *centi_dew, 0 for no humidity (RH <= 0) or a temperature at or below -200 degC. RH
   above 100 % counts as 100 %. Integer arithmetic only. */
int scr_dew_point(int32_t centi_c, int32_t centi_rh, int32_t *centi_dew);

/* The 3-hour pressure tendency: the live pressure against the oldest of a full 5-minute history (175 to 180
   minutes before it). RISING at +1.0 hPa or more, FALLING at -1.0 hPa or less, else STEADY (the
   thresholds of the "steady" band around zero in the WMO 3-hour tendency, characteristic 4); NONE while
   the history is not full, its oldest is a gap, or the live value is missing. *delta_dhpa: the change. */
enum scr_trend { TREND_NONE, TREND_FALLING, TREND_STEADY, TREND_RISING };
#define SCR_TREND_DHPA 10   /* 1.0 hPa */
enum scr_trend scr_tendency(const scr_view_t *v, int32_t *delta_dhpa);

/* 1 by day (06:00 to 18:00 at offset_min from UTC), 0 by night, -1 with no time (utc 0). */
int scr_is_day(uint32_t utc, int32_t offset_min);
/* Tips in the last `minutes` of per_min (n minutes, the newest last). */
unsigned scr_rain_tips(const uint8_t *per_min, unsigned n, unsigned minutes);
/* HOME's condition icon, the first that holds:
     RAIN  a tip in the last 10 minutes (SNOW instead if the air is below 0 degC)
     SNOW  the air below 0 degC
     WIND  the wind above 5.0 m/s
     CLOUD the air's RH at 85 % or more
     MOON  by night with the clock synchronized (scr_is_day at SCR_UTC_OFFSET_MIN), else SUN. */
enum scr_icon { ICON_SUN, ICON_MOON, ICON_CLOUD, ICON_RAIN, ICON_SNOW, ICON_WIND };
#define SCR_RAIN_RECENT_MIN 10U
#define SCR_WINDY_CMS 500U
#define SCR_CLOUDY_CENTI_RH 8500
#define SCR_CALM_CMS 50U    /* under 0.5 m/s is calm (the protocol's CALM, docs/protocol-design.md) */
enum scr_icon scr_icon_pick(const scr_view_t *v);

/* A bar of v on a scale of full to px pixels: 0 for v <= 0, px at full or more (or full <= 0), otherwise
   rounded up (anything is a pixel). */
unsigned scr_bar_px(int32_t v, int32_t full, unsigned px);
/* v's row in a plot of h rows from top (hi at the top, lo at the bottom), rounded, clipped to the plot. */
int scr_spark_y(int32_t v, int32_t lo, int32_t hi, int top, int h);
/* The link line's signal bars for an ACK's RSSI: 3 at -85 dBm or more, 2 at -100, 1 at -115, else 0. */
unsigned scr_signal_bars(int16_t rssi);
unsigned scr_acks(const int16_t *rssi, unsigned n);   /* frames ACKed among n: the samples that are no gap */
/* Seconds to the next minute's exchange (1 to 60) from the time since the last one started; -1 for none. */
int32_t scr_next_tx_s(uint32_t since_exchange_s);

/* The fortune cookie's line, from the readings: the first condition that holds (no ACK, a low cell, rain,
   frost, heat, wind, damp, dry air, falling then rising pressure, else calm), and of its lines the one
   last_seq picks. Each line is up to 3 rows of up to OLED_COLS characters, split at '\n'. */
extern const char *const scr_fortunes[];
#define SCR_FORTUNES 15U
unsigned scr_fortune_pick(const scr_view_t *v);
/* The frog's mood, from HOME's icon: SOGGY in rain, CHILLY in frost, BREEZY in wind, TOASTY at 30 degC or
   more, MOPEY under cloud, SLEEPY by night, else HAPPY. */
enum scr_mood { MOOD_HAPPY, MOOD_SLEEPY, MOOD_MOPEY, MOOD_SOGGY, MOOD_CHILLY, MOOD_BREEZY, MOOD_TOASTY };
#define SCR_HOT_CENTI_C 3000
enum scr_mood scr_frog_mood(const scr_view_t *v);
extern const char *const scr_mood_names[7];
/* The digital rain's speed: 1 when dry, 2 with 1 to 4 tips in the last 10 minutes, 3 with more. */
unsigned scr_matrix_speed(unsigned tips10);
/* The digital rain's streams, on a grid of SCR_MATRIX_COLS x SCR_MATRIX_ROWS glyphs. Each column has a
   stream, half of them a second; each stream falls at its own rate (half a glyph to 1.25 a frame when dry,
   (speed + 1) / 2 times that), then starts again after its own delay with a new length. scr_matrix_stream:
   stream s of column c at the frame, its head's row (negative: still to come; at least SCR_MATRIX_ROWS:
   gone) and its length in glyphs (SCR_MATRIX_LEN_MIN to MAX); 0 if the column has no stream s. scr_matrix_fade: the level of the
   glyph d behind the head of a len-glyph trail, 15 at the head, 10 behind it down to 1 at its tail, 0 off
   the trail. scr_matrix_level: the level of the glyph at (c, r), the brighter of its column's streams. */
#define SCR_MATRIX_COLS 21U
#define SCR_MATRIX_ROWS 7U
#define SCR_MATRIX_STREAMS 2U
#define SCR_MATRIX_LEN_MIN 4U
#define SCR_MATRIX_LEN_MAX 9U
#define SCR_MATRIX_HEAD 15U
int scr_matrix_stream(unsigned c, unsigned s, unsigned frame, unsigned speed, int *head, unsigned *len);
unsigned scr_matrix_fade(int d, unsigned len);
unsigned scr_matrix_level(unsigned c, unsigned r, unsigned frame, unsigned speed);
/* A small hash for the screens' noise (the digital rain's glyphs, the pinball's start). */
uint32_t scr_hash(uint32_t a, uint32_t b);

/* scr_rain.c's arithmetic. The rate of the last `minutes` of per_min (n minutes, the newest last; this
   minute so far counts as a whole one; fewer than `minutes` of them: the rest had none), in um/h; 0 for
   0 minutes. */
uint32_t scr_rain_rate_umh(const uint8_t *per_min, unsigned n, unsigned minutes);

#endif
