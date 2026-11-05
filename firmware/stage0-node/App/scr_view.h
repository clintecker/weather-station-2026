/* The bench OLED's screens (docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md, "The screen"
 * and "The interludes"): layout C, its packet banner, and the six interludes, each drawn from a view of
 * what the TX knows and a frame number. Pure C, no HAL: the host tests check it (tests/test_scr_view.py)
 * and tools/scr_render.py renders every screen to PNG. App/scr_view.c draws layout C and the banner,
 * App/scr_interludes.c the interludes. Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_VIEW_H
#define SCR_VIEW_H

#include <stdint.h>
#include "oled_fb.h"
#include "mod_wind.h"
#include "power_acq.h"

enum scr_id { SCR_NORMAL, SCR_BURST, SCR_BANNER, SCR_SCOPE, SCR_VANE, SCR_SYSTEM, SCR_BOOT, SCR_HACK, SCR_COUNT };

/* last_acked: the outcome of the last frame sent. */
#define SCR_TX_NONE   (-2)   /* nothing sent since boot */
#define SCR_TX_WAIT   (-1)   /* sent, its reply not in yet */
#define SCR_TX_NO_ACK 0
#define SCR_TX_ACK    1

/* What the screens show. A value whose *_ok (or batt_ok, gauge_ok) is 0 is not drawn: its row says
   "NO <part>". */
typedef struct {
  int air_ok, box_ok, press_ok, uv_ok;
  int32_t air_c, air_rh, box_c, box_rh;   /* SHT45 and SHTC3: 0.01 degC, 0.01 % (mod_th_live) */
  int32_t press_dhpa, uv_counts;          /* BMP581 0.1 hPa, LTR390 raw counts (mod_reg_live) */
  wind_live_t wind;                       /* mod_wind_live */
  uint32_t tips;                          /* rain tips since boot */
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
} scr_view_t;

/* Clears fb and draws frame `frame` of screen id (frame counts from 0; scr_frames(id) in one play,
   a larger one draws as the last). */
void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v);
/* Frames in one play: NORMAL 1, BANNER 24, BURST 16, HACK 24, the others 64. */
unsigned scr_frames(enum scr_id id);

/* scr_interludes.c, for scr_draw. Each draws on a cleared fb. */
void scr_burst(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_scope(oled_fb *fb, const scr_view_t *v);
void scr_vane(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_system(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_boot(oled_fb *fb, unsigned frame, const scr_view_t *v);
void scr_hack(oled_fb *fb, unsigned frame);

/* The text helpers both files use (scr_view.c). A line is at most SCR_LINE - 1 characters. */
#define SCR_LINE 24
void scr_put(char *line, const char *s);
/* v, which has in_dec decimals (at most 6), with out_dec <= in_dec of them, rounded half away from
   zero; plus: a '+' on a value that is not negative. */
void scr_put_dec(char *line, int64_t v, unsigned in_dec, unsigned out_dec, int plus);
void scr_put_uint(char *line, uint32_t v);
void scr_pad_to(char *line, unsigned col);   /* spaces up to column col */
extern const char *const scr_point_names[16];   /* the vane's points, 0 N clockwise to 15 NNW */

#endif
