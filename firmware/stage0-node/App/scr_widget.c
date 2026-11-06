/* The bench screens' widgets: see scr_widget.h. */
#include "scr_widget.h"
#include <string.h>
#include "oled_font.h"
#include "scr_calc.h"

#define HEADER_PX 8

void scr_label(const oled_surf *s, int y, const char *text, enum scr_align a)
{
  int w = OLED_CHAR_ADVANCE * (int)strlen(text) - 1;
  (void)oled_text(s, a == SCR_LEFT ? 0 : a == SCR_RIGHT ? OLED_W - w : (OLED_W - w) / 2, y, text, 1);
}

void scr_header(const oled_surf *s, const char *text)
{
  scr_label(s, 0, text, SCR_LEFT);
  oled_invert(s, 0, 0, OLED_W, HEADER_PX);
}

static scr_series series(const void *v, int i16, unsigned n, unsigned cap)
{
  scr_series d = { v, (uint8_t)(i16 != 0), (uint8_t)(n > cap ? cap : n), (uint8_t)cap };
  return d;
}

scr_series scr_series_i16(const int16_t *v, unsigned n, unsigned cap) { return series(v, 1, n, cap); }
scr_series scr_series_u8(const uint8_t *v, unsigned n, unsigned cap) { return series(v, 0, n, cap); }

int32_t scr_at(const scr_series *d, unsigned i)
{
  return d->i16 ? ((const int16_t *)d->v)[i] : ((const uint8_t *)d->v)[i];
}

int32_t scr_sum_last(const scr_series *d, unsigned k)
{
  int32_t sum = 0;
  for (unsigned i = d->n > k ? d->n - k : 0U; i < d->n; i++)
    if (scr_at(d, i) != SCR_GAP) sum += scr_at(d, i);
  return sum;
}

int32_t scr_max(const scr_series *d)
{
  int32_t m = 0;
  int any = 0;
  for (unsigned i = 0; i < d->n; i++)
  {
    int32_t v = scr_at(d, i);
    if (v != SCR_GAP && (!any || v > m)) { m = v; any = 1; }
  }
  return m;
}

unsigned scr_scale_steps(unsigned largest, unsigned floor, unsigned cap)
{
  unsigned full = floor ? floor : 1U;
  while (full < largest && full < cap) full *= 2U;   /* bound: at most 32 doublings, each before cap */
  return full;
}

unsigned scr_spark_range(const scr_series *d, int32_t min_span, int32_t *lo, int32_t *hi)
{
  unsigned valid = 0;
  int32_t a = 0, b = 0;
  for (unsigned i = 0; i < d->n; i++)
  {
    int32_t v = scr_at(d, i);
    if (v == SCR_GAP) continue;
    if (valid == 0U || v < a) a = v;
    if (valid == 0U || v > b) b = v;
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

void scr_frame(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned bottom_dash)
{
  oled_line(s, x0, y0, x1, y0, 1);
  oled_line(s, x0, y1, x1, y1, bottom_dash);
  oled_line(s, x0, y0, x0, y1, 0);
  oled_line(s, x1, y0, x1, y1, 0);
}

void scr_bars(const oled_surf *s, int x, int base_y, unsigned px, const scr_series *d, int32_t floor, int32_t span,
              unsigned frame, const scr_bars_style *st)
{
  for (unsigned i = 0; i < d->n; i++)
  {
    int bx = x + st->pitch * (int)(d->cap - d->n + i);
    int32_t v = scr_at(d, i);
    if (v == SCR_GAP)
    {
      if (!st->gap_x) continue;
      oled_line(s, bx, base_y - 3, bx + st->bar_w - 1, base_y - 1, 0);
      oled_line(s, bx + st->bar_w - 1, base_y - 3, bx, base_y - 1, 0);
      continue;
    }
    unsigned h = scr_bar_px(v - floor, span, px);
    if (st->grows) h = scr_grow(h, frame, SCR_GROW_FRAMES);
    oled_fill(s, bx, base_y - (int)h, st->bar_w, (int)h, 1);
  }
}

void scr_trace(const oled_surf *s, int x, int top, int w, int h, const scr_series *d, int32_t lo, int32_t hi,
               unsigned slots)
{
  int px = 0, py = 0, prev = 0;
  for (unsigned i = 0; i < d->n; i++)
  {
    unsigned slot = d->cap - d->n + i;
    if (slot >= slots) break;
    int32_t v = scr_at(d, i);
    if (v == SCR_GAP) { prev = 0; continue; }
    int sx = x + (int)(slot * (unsigned)(w - 1) / (d->cap - 1U)), sy = scr_spark_y(v, lo, hi, top, h);
    if (prev) oled_line(s, px, py, sx, sy, 0);
    else oled_set(s, sx, sy, 1);
    px = sx; py = sy; prev = 1;
  }
}

void scr_gauge(const oled_surf *s, int x, int y, unsigned fill_px, const scr_gauge_style *st)
{
  if (st->boxed) oled_box(s, x, y, st->w, st->h);
  else oled_line(s, x, y + st->h - 1, x + st->w - 1, y + st->h - 1, 1);   /* the track */
  oled_fill(s, x + st->inset, y + st->inset, (int)fill_px, st->fill_h, 1);
}

int scr_sin20(int p)
{
  static const int8_t quarter[5] = { 0, 8, 14, 18, 20 };
  p &= 15;
  if (p <= 4) return quarter[p];
  if (p <= 8) return quarter[8 - p];
  if (p <= 12) return -quarter[p - 8];
  return -quarter[16 - p];
}

void scr_ray(const oled_surf *s, int cx, int cy, int r0, int r1, int p, unsigned dash)
{
  int sx = scr_sin20(p), cy20 = scr_sin20(p + 4);
  oled_line(s, cx + r0 * sx / 20, cy - r0 * cy20 / 20, cx + r1 * sx / 20, cy - r1 * cy20 / 20, dash);
}

void scr_glitch(const oled_surf *s, const int8_t *rows, unsigned n, int dy, int dx, int band_y, int band_h)
{
  for (unsigned i = 0; i < n; i++) oled_shift_row(s, rows[i] + dy, dx);
  oled_invert(s, 0, band_y, OLED_W, band_h);
}

void scr_drops(const oled_surf *s, unsigned n, int x0, int dx, int y0, unsigned t, unsigned phase, unsigned span)
{
  for (unsigned i = 0; i < n; i++)
  {
    int x = x0 + dx * (int)i, y = y0 + (int)((t + i * phase) % span);
    oled_line(s, x, y, x - 1, y + 3, 0);
  }
}
