/* The bench screens' widgets: labels, series over any history, scales, plot frames, bars, the sparkline's
 * trace, gauges, and the motion the screens share (a ray at a compass point, the glitch, falling drops). Each
 * draws into a place from data: plain functions, no state. Pure C (tests/test_scr_calc.py, test_scr_view.py).
 * Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_WIDGET_H
#define SCR_WIDGET_H

#include <stdint.h>
#include "oled_draw.h"

#define SCR_ROW_PX 8                   /* a 5x7 row and its gap */
#define SCR_GROW_FRAMES 8U             /* the bars and lines grow in over 8 frames; the screens' table reads it too */
#define SCR_GAP INT16_MIN              /* a sample with no value */

enum scr_align { SCR_LEFT, SCR_RIGHT, SCR_CENTRE };
void scr_label(const oled_surf *s, int y, const char *text, enum scr_align a);   /* 5x7, x1, across the screen */
void scr_header(const oled_surf *s, const char *text);                           /* row 0, inverted */

/* A read-only series over any history: n samples, newest last, in cap slots (slot of i = cap - n + i). */
typedef struct { const void *v; uint8_t i16, n, cap; } scr_series;   /* i16: int16_t with SCR_GAP; else uint8_t */
scr_series scr_series_i16(const int16_t *v, unsigned n, unsigned cap);   /* clamps n to cap */
scr_series scr_series_u8(const uint8_t *v, unsigned n, unsigned cap);
int32_t scr_at(const scr_series *d, unsigned i);                         /* SCR_GAP for a gap */
int32_t scr_sum_last(const scr_series *d, unsigned k);                   /* of the last k samples, gaps left out */
int32_t scr_max(const scr_series *d);                                    /* of the samples that are not gaps; 0 if none */

/* Scales (pure). floor doubled until it holds largest, at most cap: it steps rather than creeps. */
unsigned scr_scale_steps(unsigned largest, unsigned floor, unsigned cap);
/* The least and largest of the samples that are not gaps, widened about their middle to at least min_span.
   Returns how many samples are not gaps (0: lo and hi untouched). */
unsigned scr_spark_range(const scr_series *d, int32_t min_span, int32_t *lo, int32_t *hi);
/* v grown in over frames: its share after frame `frame` (counted from 0), all of it from frames - 1 on. */
static inline unsigned scr_grow(unsigned v, unsigned frame, unsigned frames)
{ return v * (frame + 1U < frames ? frame + 1U : frames) / frames; }

/* A plot's frame: a top and bottom edge from x0 to x1 (none, solid, dotted from x0), and solid sides from y0 to y1
   if sides. */
enum { SCR_EDGE_NONE, SCR_EDGE_SOLID, SCR_EDGE_DOTTED };
void scr_frame(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned top, unsigned bottom, int sides);

/* Bars standing on base_y, up to px tall: bar i at x + pitch * slot(i), bar_w wide, height scr_bar_px(v - floor,
   span, px), grown by frame if grows. A gap: an x across the bar's foot (gap_x) or nothing. */
typedef struct { uint8_t bar_w, pitch, gap_x, grows; } scr_bars_style;
void scr_bars(const oled_surf *s, int x, int base_y, unsigned px, const scr_series *d, int32_t floor, int32_t span,
              unsigned frame, const scr_bars_style *st);

/* The sparkline: sample i at x + slot(i) (w - 1) / (cap - 1), at scr_spark_y in [top, top + h), joined to the one
   before unless a gap breaks the line, only the first scr_grow(cap, frame) slots drawn. */
void scr_trace(const oled_surf *s, int x, int top, int w, int h, const scr_series *d, int32_t lo, int32_t hi,
               unsigned frame);

/* A gauge of w x h at (x, y) filled fill_px from x + inset: boxed, the box around it; else a dotted track along
   its bottom row. POWER's {128, 2, 0, 2, 0}, SYSTEM's {70, 7, 2, 3, 1}. */
typedef struct { uint8_t w, h, inset, fill_h, boxed; } scr_gauge_style;
void scr_gauge(const oled_surf *s, int x, int y, unsigned fill_px, const scr_gauge_style *st);

/* 20 sin(p x 22.5 degrees), rounded, for any point p (wrapped): the screens' 16-point compass. */
int scr_sin20(int p);
/* From r0 to r1 out from (cx, cy) toward compass point p (0 up, clockwise), dash as oled_line. */
void scr_ray(const oled_surf *s, int cx, int cy, int r0, int r1, int p, unsigned dash);
/* Rows rows[0..n) + dy moved dx pixels across, and the band_h rows from band_y inverted. */
void scr_glitch(const oled_surf *s, const int8_t *rows, unsigned n, int dy, int dx, int band_y, int band_h);
/* n drops, each a 4-pixel slant: drop i at x0 + dx i, y0 + (t + phase i) % span. */
void scr_drops(const oled_surf *s, unsigned n, int x0, int dx, int y0, unsigned t, unsigned phase, unsigned span);
/* A triangle wave: p folded into lo..hi and back (a bounce off two walls). */
static inline int scr_tri(int p, int lo, int hi)
{
  int span = hi - lo, m = (p - lo) % (2 * span);
  if (m < 0) m += 2 * span;
  return lo + (m < span ? m : 2 * span - m);
}

#endif
