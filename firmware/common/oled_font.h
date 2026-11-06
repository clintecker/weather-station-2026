/* Bitmaps and fonts on the drawing surface (oled_draw.h): one bit convention, one glyph walker, one text
 * renderer for every font (the 5x7, the node's big digits and kana). Pure C: tests/test_oled_draw.py.
 *   A bitmap row is a uint8_t, uint16_t or uint64_t (bits 8, 16 or 64) and bit w - 1 is its leftmost
 *   column. A font is n glyphs of h such rows, each w wide (or widths[g]), gap pixels after each; a
 *   style scales a font pixel to sx x sy and can fix the advance or place each column itself. */
#ifndef OLED_FONT_H_INCLUDED
#define OLED_FONT_H_INCLUDED

#include <stddef.h>
#include <stdint.h>
#include "oled_draw.h"

#define OLED_CHAR_ADVANCE 6   /* the 5x7 at scale 1: 5 columns and a gap */

typedef struct {
  uint8_t w, h;
  uint8_t bits;        /* the row type: 8, 16 or 64 */
  const void *rows;    /* h rows of that type */
} oled_bits;

typedef struct {
  uint8_t h, w;              /* w: every glyph's width, unless widths */
  uint8_t bits, gap;         /* row type; pixels after each glyph */
  uint8_t n;
  const char *chars;         /* the glyphs' characters in order; NULL: by number only (the kana) */
  const uint8_t *widths;     /* NULL: all w */
  const void *rows;          /* n * h rows */
  char missing;              /* drawn for a character not in chars; '\0': nothing, no advance */
} oled_font;

typedef struct {
  uint8_t sx, sy;            /* a font pixel is sx x sy */
  uint8_t pitch;             /* 0: (glyph w + gap) * sx; else a fixed advance */
  const uint8_t *col_x;      /* NULL: column c at c * sx; else at col_x[c] (the squeezed PLANET) */
} oled_style;
extern const oled_style oled_x1, oled_x2;

void oled_blit(const oled_surf *s, int x, int y, const oled_bits *b);           /* the lit pixels, at ink */
int oled_glyph(const oled_font *f, char c);                                      /* -1: none and no missing */
void oled_draw_glyph(const oled_surf *s, int x, int y, const oled_font *f, unsigned g, const oled_style *st);
/* Returns the pen x after the last glyph and its gap. oled_text_w: from the first glyph's left to the
   last one's right edge (no trailing gap); 0 for none. */
int oled_draw_text(const oled_surf *s, int x, int y, const char *str, const oled_font *f, const oled_style *st);
int oled_text_w(const char *str, const oled_font *f, const oled_style *st);
/* str in the 5x7 (font5x7.h), each font pixel scale x scale, characters it lacks as '?'; returns the x after
   the text. */
int oled_text(const oled_surf *s, int x, int y, const char *str, int scale);

#endif
