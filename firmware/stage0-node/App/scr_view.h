/* The bench OLED's screens (docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md, "The screens"):
 * HOME and its packet banner, the detail screens, the interludes, each drawn from a view of what the TX
 * knows and a frame number. Pure C, no HAL: the host tests check it (tests/test_scr_view.py, test_scr_calc.py)
 * and tools/scr_render.py renders every screen to PNG.
 *   App/scr_view.c        scr_draw, the frame counts, the text and big-digit helpers
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
#include "oled_fb.h"
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
   no module keeps any of it). Each is oldest first, n of cap; SCR_GAP is a sample with no value. */
#define SCR_GAP INT16_MIN
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
  uint8_t air_n, press_n, radio_n;        /* samples in the histories below */
  int16_t air_hist[SCR_AIR_HIST];         /* the SHT45, 0.01 degC */
  int16_t press_hist[SCR_PRESS_HIST];     /* the BMP581, 0.1 hPa */
  int16_t radio_rssi[SCR_RADIO_HIST];     /* each frame's ACK, dBm (SCR_GAP: no ACK) */
  int16_t radio_snr[SCR_RADIO_HIST];      /* and its SNR, dB */
} scr_view_t;

/* Clears fb and draws frame `frame` of screen id (frame counts from 0). HOME and the banner animate for
   ever (their icon); any other screen draws a frame past its last as the last. */
void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v);
/* Frames in one play as an interlude or a packet screen: BURST 16, BANNER 24, HACK 24, HOME 1, AIR,
   PRESSURE, POWER and RADIO 8 (their bars and lines grow in), the others 64. */
unsigned scr_frames(enum scr_id id);

/* The screens, for scr_draw. Each draws on a cleared fb. */
void scr_home(oled_fb *fb, unsigned frame, const scr_view_t *v, int with_banner);   /* scr_home.c */
void scr_air(oled_fb *fb, unsigned frame, const scr_view_t *v);                     /* scr_detail.c */
void scr_pressure(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_power(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_radio(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_burst(oled_fb *fb, unsigned frame, const scr_view_t *v);                   /* scr_interludes.c */
void scr_scope(oled_fb *fb, const scr_view_t *v);
void scr_vane(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_system(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_boot(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_hack(oled_fb *fb, unsigned frame);
void scr_rain(oled_fb *fb, const scr_view_t *v);                                    /* scr_rain.c */
void scr_fortune(oled_fb *fb, unsigned frame, const scr_view_t *v);                 /* scr_silly.c */
void scr_frog(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_matrix(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_pinball(oled_fb *fb, unsigned frame, const scr_view_t *v);

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
/* The sparkline's scale: the least and largest of the n samples that are not gaps, widened about their
   middle to at least min_span. Returns how many samples are not gaps (0: lo and hi untouched). */
unsigned scr_spark_range(const int16_t *s, unsigned n, int32_t min_span, int32_t *lo, int32_t *hi);
/* v's row in a plot of h rows from top (hi at the top, lo at the bottom), rounded, clipped to the plot. */
int scr_spark_y(int32_t v, int32_t lo, int32_t hi, int top, int h);
/* The link line's signal bars for an ACK's RSSI: 3 at -85 dBm or more, 2 at -100, 1 at -115, else 0. */
unsigned scr_signal_bars(int16_t rssi);
unsigned scr_acks(const int16_t *rssi, unsigned n);   /* frames ACKed among n: the samples that are no gap */
/* Seconds to the next minute's exchange (1 to 60) from the time since the last one started; -1 for none. */
int32_t scr_next_tx_s(uint32_t since_exchange_s);

/* The fortune cookie's line, from the readings: the first condition that holds (no ACK, a low cell, rain,
   frost, heat, wind, damp, dry air, falling then rising pressure, else calm), and of its lines the one
   last_seq picks. Each line is up to 3 rows of up to SCR_COLS characters, split at '\n'. */
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
/* A small hash for the screens' noise (the digital rain's glyphs, the pinball's start). */
uint32_t scr_hash(uint32_t a, uint32_t b);

/* scr_rain.c's arithmetic. The rate of the last `minutes` of per_min (n minutes, the newest last; this
   minute so far counts as a whole one; fewer than `minutes` of them: the rest had none), in um/h; 0 for
   0 minutes. */
uint32_t scr_rain_rate_umh(const uint8_t *per_min, unsigned n, unsigned minutes);
unsigned scr_rain_bar_px(unsigned count, unsigned full, unsigned px);   /* 0 for none, else rounded up, at most px */
/* The chart's scale for a largest minute of `largest` tips: 4, doubled until it holds it (at most 256), so
   the scale steps rather than creeps and the label stays a round number. */
unsigned scr_rain_full(unsigned largest);

/* ---- scr_view.c: the helpers the screens share. A line is at most SCR_LINE - 1 characters. ---- */
#define SCR_LINE 24
#define SCR_COLS 21                          /* characters a row */
void scr_put(char *line, const char *s);
/* v, which has in_dec decimals (at most 6), with out_dec <= in_dec of them, rounded half away from
   zero; plus: a '+' on a value that is not negative. */
void scr_put_dec(char *line, int64_t v, unsigned in_dec, unsigned out_dec, int plus);
void scr_put_uint(char *line, uint32_t v);
void scr_pad_to(char *line, unsigned col);   /* spaces up to column col */
void scr_put_age(char *line, uint32_t s);   /* an age in three characters or so: 58s, then minutes, then hours */
void scr_put_rain_mm(char *line, uint32_t tips);   /* tips as mm, 2 decimals, "mm" not included */
/* left, then right ending at the last column, at least a space between; 0 (line untouched) if they do
   not fit. */
int scr_put_lr(char *line, const char *left, const char *right);
void scr_row(oled_fb *fb, int y, const char *text);             /* at (0, y), scale 1 */
void scr_row_right(oled_fb *fb, int y, const char *text);       /* ending at the screen's right edge */
void scr_header(oled_fb *fb, const char *text);                 /* the top row, inverted */
/* The big digits (scr_font.h) with their top-left at (x, y); returns the x after the text. Characters the
   font lacks draw as nothing. scr_big_width: the pixels the text takes. */
int scr_big_text(oled_fb *fb, int x, int y, const char *s);
int scr_big_width(const char *s);
/* The drawing a at its place moved by (dx, dy). */
void scr_blit(oled_fb *fb, const scr_art *a, int dx, int dy);
/* 20 sin(p x 22.5 degrees), rounded, for any point p (wrapped): the screens' 16-point compass. */
int scr_sin20(int p);
extern const char *const scr_point_names[16];   /* the vane's points, 0 N clockwise to 15 NNW */

#endif
