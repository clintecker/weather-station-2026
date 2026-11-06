/* The bench OLED's drawing surface (Adafruit #2674, SSD1325, 128 x 64, 4 bits a pixel) and everything drawn
 * on it: pixels at a level, lines, boxes, fills, a dot grid, circles, a row shift for the glitch effect, and
 * the 5x7 text; and gray pixels, bitmaps and text straight into a frame in send order, for a screen that
 * draws its own levels. Pure C: the host tests check it (tests/test_oled_fb.py). Everything clips to the
 * screen.
 *   A surface is a frame in the SSD1325's send order, the order the panel takes it: two pixels a byte (the
 *   left one in the high nibble) and, with the re-map Adafruit's driver sets (0x56: vertical address
 *   increment), each byte after the first one row down, then on to the next column pair: 64 column pairs x
 *   64 rows = 4096 bytes. A panel mounted upside down takes it turned (rot180): logical (x, y) is stored at
 *   (127 - x, 63 - y), so a frame drawn on the send buffer goes out as it is. */
#ifndef OLED_DRAW_H_INCLUDED
#define OLED_DRAW_H_INCLUDED

#include <stdint.h>

#define OLED_W 128
#define OLED_H 64
#define OLED_COLPAIRS (OLED_W / 2)
#define OLED_FRAME_BYTES (OLED_COLPAIRS * OLED_H)   /* 4096 */
#define OLED_FULL 15U
#define OLED_CHAR_ADVANCE 6   /* 5 columns and a gap */

typedef struct {
  uint8_t *px;       /* OLED_FRAME_BYTES in the SSD1325's send order */
  uint8_t rot180;    /* panel upside down: logical (x, y) is stored at (127 - x, 63 - y) */
  uint8_t ink;       /* the level oled_set(.., 1) writes: 1..15 */
} oled_surf;

oled_surf oled_surf_on(uint8_t px[OLED_FRAME_BYTES], int rot180);   /* ink OLED_FULL; does not clear */
void oled_clear(const oled_surf *s);
void oled_level(const oled_surf *s, int x, int y, unsigned level);   /* 0..15, more is 15; off screen ignored */
unsigned oled_get(const oled_surf *s, int x, int y);                 /* the level; 0 off screen */
void oled_set(const oled_surf *s, int x, int y, int on);             /* on: s->ink, else 0 */
/* Draws str with its top-left at (x, y), each font pixel scale x scale; returns the x after the text.
   Characters the font lacks draw as '?'. */
int oled_text(const oled_surf *s, int x, int y, const char *str, int scale);

/* A line from (x0, y0) to (x1, y1), both ends lit. dash 0 is solid; otherwise runs of dash lit pixels
   alternate with runs of dash dark ones, counted from (x0, y0). */
void oled_line(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned dash);
/* The outline of the w x h rectangle with its top-left at (x, y). */
void oled_box(const oled_surf *s, int x, int y, int w, int h);
/* The w x h rectangle at (x, y), lit (on 1) or dark (on 0). */
void oled_fill(const oled_surf *s, int x, int y, int w, int h, int on);
/* Dotted grid lines every step pixels across the w x h rectangle at (x, y), starting on its top and left
   edges, a dot every second pixel. */
void oled_dotgrid(const oled_surf *s, int x, int y, int w, int h, int step);
/* The w x h rectangle at (x, y) inverted: a lit pixel goes dark, a dark one takes the ink. */
void oled_invert(const oled_surf *s, int x, int y, int w, int h);
/* A circle of radius r around (cx, cy): the outline, and the filled disc (on 1 lit, on 0 dark). */
void oled_circle(const oled_surf *s, int cx, int cy, int r);
void oled_disc(const oled_surf *s, int cx, int cy, int r, int on);
/* Moves row y dx pixels right (left if negative), levels and all; what leaves the screen is lost, the gap
   is dark. */
void oled_shift_row(const oled_surf *s, int y, int dx);
/* Gray, in a frame in send order: pixel (x, y) at level 0 (dark) to 15 (full; more is 15), turned if
   rotate180. put4 sets the level; blit4 puts the lit pixels of the w x h bitmap rows (w at most 8, bit w - 1
   the leftmost column) at (x, y), and text4 the 5x7 text s (oled_text's font and spacing), all at level. */
void ssd1325_put4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, unsigned level, int rotate180);
void ssd1325_blit4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const uint8_t *rows, int w, int h, unsigned level,
                   int rotate180);
void ssd1325_text4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const char *s, unsigned level, int rotate180);

#endif
