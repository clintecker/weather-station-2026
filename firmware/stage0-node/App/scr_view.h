/* The bench OLED's screens (docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md, "The screens"):
 * HOME and its packet banner, the detail screens, the interludes, each drawn from a view of what the TX
 * knows and a frame number. Pure C, no HAL: the host tests check it (tests/test_scr_view.py, test_scr_calc.py)
 * and tools/scr_render.py renders every screen to PNG.
 *   App/scr_view.c        scr_draw, the frame counts, the text helpers
 *   App/scr_widget.c      labels, series, scales, frames, bars, the trace, gauges, rays, the glitch, drops
 *   App/scr_calc.c        the arithmetic and the choices: histories, dew point, tendency, icon, scales, fortune
 *   App/scr_home.c        HOME, its condition icons and the banner
 *   App/scr_detail.c      AIR, PRESSURE, POWER, RADIO and their sparklines and bars
 *   App/scr_interludes.c  the packet burst, SCOPE, VANE, SYSTEM, the boot splash, HACK THE PLANET
 *   App/scr_rain.c        RAIN
 *   App/scr_silly.c       the fortune cookie, the frog, the digital rain, the packet pinball
 * Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_VIEW_H
#define SCR_VIEW_H

#include <stdint.h>
#include "oled_draw.h"
#include "oled_font.h"
#include "oled_row.h"
#include "scr_widget.h"
#include "mod_rain.h"
#include "mod_wind.h"
#include "power_acq.h"
#include "scr_art.h"

enum scr_id { SCR_HOME, SCR_BURST, SCR_BANNER, SCR_AIR, SCR_PRESSURE, SCR_POWER, SCR_RADIO, SCR_SCOPE, SCR_VANE,
              SCR_RAIN, SCR_SYSTEM, SCR_BOOT, SCR_HACK, SCR_FORTUNE, SCR_FROG, SCR_MATRIX, SCR_PINBALL, SCR_COUNT };

/* last_acked: the outcome of the last frame sent. */
#define SCR_TX_NONE   (-2)   /* nothing sent since boot */
#define SCR_TX_WAIT   (-1)   /* sent, its reply not in yet */
#define SCR_TX_NO_ACK 0
#define SCR_TX_ACK    1

/* The histories the display keeps itself (App/oled_view.c and oled_app.c sample the live values into them;
   no module keeps any of it). Each is oldest first, its count n of cap next to it; SCR_GAP (scr_widget.h) is a
   sample with no value. A screen reads one through a scr_series. */
#define SCR_HIST(cap) struct { uint8_t n; int16_t s[cap]; }
#define SCR_AIR_HIST 60U          /* the SHT45 a minute: the last hour */
#define SCR_PRESS_HIST 36U        /* the BMP581 every 5 minutes: the last 3 h */
#define SCR_RADIO_HIST 30U        /* the last 30 frames' ACKs */
#define SCR_NONE_S UINT32_MAX     /* since_exchange_s before the first exchange */
/* The bench's offset from UTC, for HOME's sun and moon (America/Chicago standard time; no daylight saving). */
#ifndef SCR_UTC_OFFSET_MIN
#define SCR_UTC_OFFSET_MIN (-360)
#endif

/* What the screens show. A value whose *_ok (or batt_ok, gauge_ok) is 0 is not drawn: its row says
   "NO <part>". */
typedef struct {
  int air_ok, box_ok, press_ok, uv_ok;
  int32_t air_c, air_rh, box_c, box_rh;   /* SHT45 and SHTC3: 0.01 degC, 0.01 % (mod_th_live) */
  int32_t press_dhpa, uv_counts;          /* BMP581 0.1 hPa, LTR390 raw counts (mod_reg_live) */
  wind_live_t wind;                       /* mod_wind_live */
  rain_hist_t rain;                       /* mod_rain_history: tips, the last one's age, an hour of minutes */
  power_live_t power;                     /* power_acq_live */
  uint32_t last_seq, last_age_s;          /* the last frame sent and how long ago */
  int last_acked;                         /* SCR_TX_* */
  int16_t ack_rssi;                       /* the ACK's RSSI, dBm */
  int8_t ack_snr;                         /* and SNR, dB */
  unsigned pending, extra_frames;         /* readings still queued; backlog frames sent after the live one */
  unsigned reports;                       /* health reports sent after the live one (0 or 1) */
  uint8_t cipher[96]; uint8_t cipher_len; /* the last frame's bytes, for the burst */
  uint8_t sf, bw_khz_div125; uint32_t freq_khz;   /* radio settings */
  uint8_t flash_pct, ram_pct, stack_pct, journal_pct, airtime_pct;   /* 0..100 */
  uint16_t station; uint32_t epoch;
  unsigned modules, modules_active;       /* modules known, modules answering */
  int key_ok;                             /* the node has its key (the boot splash) */
  uint32_t utc;                           /* time_utc(): UTC seconds, 0 while the clock is not synchronized */
  uint32_t since_exchange_s;              /* since the minute's exchange last started, or SCR_NONE_S */
  SCR_HIST(SCR_AIR_HIST) air;             /* the SHT45, 0.01 degC */
  SCR_HIST(SCR_PRESS_HIST) press;         /* the BMP581, 0.1 hPa */
  struct { uint8_t n; int16_t rssi[SCR_RADIO_HIST], snr[SCR_RADIO_HIST]; } radio;   /* each frame's ACK, dBm and dB
                                                                                       (SCR_GAP both: no ACK) */
} scr_view_t;

/* Clears the surface s and draws frame `frame` of screen id (frame counts from 0). HOME and the banner animate for
   ever (their icon); any other screen draws a frame past its last as the last. */
void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v);
/* Frames in one play as an interlude or a packet screen: BURST 16, BANNER 24, HACK 24, HOME 1, AIR,
   PRESSURE, POWER and RADIO 8 (their bars and lines grow in), the others 64. */
unsigned scr_frames(enum scr_id id);

/* The screens, for scr_draw. Each draws on a cleared surface. */
void scr_home(const oled_surf *s, unsigned frame, const scr_view_t *v, int with_banner);   /* scr_home.c */
void scr_air(const oled_surf *s, unsigned frame, const scr_view_t *v);                     /* scr_detail.c */
void scr_pressure(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_power(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_radio(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_burst(const oled_surf *s, unsigned frame, const scr_view_t *v);                   /* scr_interludes.c */
void scr_scope(const oled_surf *s, const scr_view_t *v);
void scr_vane(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_system(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_boot(const oled_surf *s, unsigned frame, const scr_view_t *v);
void scr_hack(const oled_surf *s, unsigned frame);
void scr_rain(const oled_surf *s, const scr_view_t *v);                                    /* scr_rain.c */
void scr_fortune(const oled_surf *s, unsigned frame, const scr_view_t *v);                 /* scr_silly.c */
void scr_frog(const oled_surf *s, unsigned frame, const scr_view_t *v);
/* The digital rain, in gray: each glyph at its own level, on a copy of s with its own ink. scr_matrix_glyph: the glyph (scr_kana.h) at (c, r),
   each changing now and then on its own, the head's every frame. */
void scr_matrix(const oled_surf *s, unsigned frame, const scr_view_t *v);
unsigned scr_matrix_glyph(unsigned c, unsigned r, unsigned frame, int head);
void scr_pinball(const oled_surf *s, unsigned frame, const scr_view_t *v);

/* ---- scr_calc.c: the arithmetic and the choices, every one pure. ---- */

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

/* ---- scr_view.c: the helpers the screens share. Rows are oled_row (oled_row.h). ---- */
void scr_put_age(oled_row *r, uint32_t s);   /* an age in three characters or so: 58s, then minutes, then hours */
void scr_put_rain_mm(oled_row *r, uint32_t tips, unsigned decimals);   /* tips as mm, "mm" not included */
/* A form for oled_fit: left and right on one row (oled_put_lr, OLED_COLS), or if they do not fit, both with a
   space between, too long for the row, so that oled_fit goes on to the next form. */
void scr_form_lr(oled_row *r, const char *left, const char *right);
extern const char *const scr_point_names[16];   /* the vane's points, 0 N clockwise to 15 NNW */

#endif
