/* A 128 x 64 one-bit frame buffer for the bench OLED (Adafruit #2674, SSD1325), its 5x7 text, and the
 * SSD1325's pixel order. Pure C: the host tests check it (tests/test_oled_fb.py).
 *   The buffer is row-major, 16 bytes a row, bit 7 the leftmost pixel.
 *   The SSD1325 takes 4 bits a pixel, two pixels a byte (the left one in the high nibble). With the
 *   re-map Adafruit's driver sets (0x56: vertical address increment), each byte after the first moves
 *   down one row, then on to the next column pair: 64 column pairs x 64 rows = 4096 bytes a frame. */
#ifndef OLED_FB_H_INCLUDED
#define OLED_FB_H_INCLUDED

#include <stdint.h>

#define OLED_W 128
#define OLED_H 64
#define OLED_COLPAIRS (OLED_W / 2)
#define OLED_CHAR_ADVANCE 6   /* 5 columns and a gap */

typedef struct { uint8_t px[OLED_W * OLED_H / 8]; } oled_fb;

void oled_clear(oled_fb *fb);
void oled_set(oled_fb *fb, int x, int y, int on);   /* outside the screen: ignored */
int oled_get(const oled_fb *fb, int x, int y);      /* outside the screen: 0 */
/* Draws s with its top-left at (x, y), each font pixel scale x scale; returns the x after the text.
   Characters the font lacks draw as '?'. */
int oled_text(oled_fb *fb, int x, int y, const char *s, int scale);
/* dst = src turned 180 degrees: (x, y) -> (OLED_W - 1 - x, OLED_H - 1 - y). dst and src must differ. */
void oled_rotate180(oled_fb *dst, const oled_fb *src);
/* The 64 bytes of column pair cp (pixels 2cp and 2cp + 1), top row first, full brightness for a lit
   pixel. */
void ssd1325_column(const oled_fb *fb, unsigned cp, uint8_t out[OLED_H]);

#endif
