/* What the bench OLED's screens show (docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md, "The
 * screens"): a view of what the TX knows, filled by App/oled_view.c and oled_app.c, and the text helpers the
 * screens share (App/scr_view.c). The screens themselves: scr_screens.h; their arithmetic: scr_calc.h; their
 * widgets: scr_widget.h. Pure C, no HAL. Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_VIEW_H
#define SCR_VIEW_H

#include <stdint.h>
#include "oled_row.h"
#include "scr_widget.h"
#include "mod_rain.h"
#include "mod_wind.h"
#include "power_acq.h"

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

/* The text helpers the screens share (scr_view.c). Rows are oled_row (oled_row.h). */
void scr_put_age(oled_row *r, uint32_t s);   /* an age in three characters or so: 58s, then minutes, then hours */
void scr_put_rain_mm(oled_row *r, uint32_t tips, unsigned decimals);   /* tips as mm, "mm" not included */
/* A form for oled_fit: left and right on one row (oled_put_lr, OLED_COLS), or if they do not fit, both with a
   space between, too long for the row, so that oled_fit goes on to the next form. */
void scr_form_lr(oled_row *r, const char *left, const char *right);
extern const char *const scr_point_names[16];   /* the vane's points, 0 N clockwise to 15 NNW */

#endif
