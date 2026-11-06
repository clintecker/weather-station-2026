/* Bitmaps, glyphs and text: see oled_font.h. */
#include "oled_font.h"
#include <string.h>
#include "font5x7.h"

const oled_style oled_x1 = { 1, 1, 0, NULL }, oled_x2 = { 2, 2, 0, NULL };

static uint64_t row_at(const void *rows, unsigned bits, unsigned i)
{
  if (bits == 64U) return ((const uint64_t *)rows)[i];
  if (bits == 16U) return ((const uint16_t *)rows)[i];
  return ((const uint8_t *)rows)[i];
}

/* The h rows of w columns from rows[0], each lit font pixel an sx x sy block (or at col_x). */
static void plot(const oled_surf *s, int x, int y, const void *rows, unsigned bits, unsigned w, unsigned h,
                 const oled_style *st)
{
  for (unsigned r = 0; r < h; r++)
  {
    uint64_t row = row_at(rows, bits, r);
    for (unsigned c = 0; c < w; c++)
      if ((row >> (w - 1U - c)) & 1U)
        oled_fill(s, x + (st->col_x ? st->col_x[c] : (int)c * st->sx), y + (int)r * st->sy, st->sx, st->sy, 1);
  }
}

void oled_blit(const oled_surf *s, int x, int y, const oled_bits *b) { plot(s, x, y, b->rows, b->bits, b->w, b->h, &oled_x1); }

int oled_glyph(const oled_font *f, char c)
{
  const char *at = f->chars && c ? strchr(f->chars, c) : NULL;
  if (at == NULL && f->missing && f->chars) at = strchr(f->chars, f->missing);
  return at ? (int)(at - f->chars) : -1;
}

static unsigned glyph_w(const oled_font *f, unsigned g) { return f->widths ? f->widths[g] : f->w; }

static const void *glyph_rows(const oled_font *f, unsigned g)
{
  return (const uint8_t *)f->rows + (size_t)g * f->h * (f->bits / 8U);
}

void oled_draw_glyph(const oled_surf *s, int x, int y, const oled_font *f, unsigned g, const oled_style *st)
{
  if (g < f->n) plot(s, x, y, glyph_rows(f, g), f->bits, glyph_w(f, g), f->h, st);
}

static int advance(const oled_font *f, unsigned g, const oled_style *st)
{
  return st->pitch ? st->pitch : (int)(glyph_w(f, g) + f->gap) * st->sx;
}

int oled_draw_text(const oled_surf *s, int x, int y, const char *str, const oled_font *f, const oled_style *st)
{
  /* bound: the characters of str, one a pass */
  for (; *str; str++)
  {
    int g = oled_glyph(f, *str);
    if (g < 0) continue;
    oled_draw_glyph(s, x, y, f, (unsigned)g, st);
    x += advance(f, (unsigned)g, st);
  }
  return x;
}

int oled_text_w(const char *str, const oled_font *f, const oled_style *st)
{
  int pen = 0, right = 0;
  /* bound: the characters of str, one a pass */
  for (; *str; str++)
  {
    int g = oled_glyph(f, *str);
    if (g < 0) continue;
    unsigned w = glyph_w(f, (unsigned)g);
    right = pen + (st->col_x ? st->col_x[w - 1U] + st->sx : (int)w * st->sx);
    pen += advance(f, (unsigned)g, st);
  }
  return right;
}

int oled_text(const oled_surf *s, int x, int y, const char *str, int scale)
{
  const oled_style st = { (uint8_t)scale, (uint8_t)scale, 0, NULL };
  return oled_draw_text(s, x, y, str, &font5x7, &st);
}
