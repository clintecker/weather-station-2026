/* Drawing on the oled_fb frame buffer (oled_fb.h) beyond text: lines, boxes, fills, a dot grid, circles,
 * a row shift for the glitch effect, and the whole frame in the SSD1325's send order; and gray pixels,
 * bitmaps and text straight into a frame in that order, for a screen that draws its own levels. Pure C:
 * the host tests check it (tests/test_oled_fb.py). Everything clips to the screen. */
#ifndef OLED_DRAW_H_INCLUDED
#define OLED_DRAW_H_INCLUDED

#include <stdint.h>
#include "oled_fb.h"

#define OLED_FRAME_BYTES (OLED_COLPAIRS * OLED_H)   /* 4096 */

/* A line from (x0, y0) to (x1, y1), both ends lit. dash 0 is solid; otherwise runs of dash lit pixels
   alternate with runs of dash dark ones, counted from (x0, y0). */
void oled_line(oled_fb *fb, int x0, int y0, int x1, int y1, unsigned dash);
/* The outline of the w x h rectangle with its top-left at (x, y). */
void oled_box(oled_fb *fb, int x, int y, int w, int h);
/* The w x h rectangle at (x, y), lit (on 1) or dark (on 0). */
void oled_fill(oled_fb *fb, int x, int y, int w, int h, int on);
/* Dotted grid lines every step pixels across the w x h rectangle at (x, y), starting on its top and left
   edges, a dot every second pixel. */
void oled_dotgrid(oled_fb *fb, int x, int y, int w, int h, int step);
/* Flips every pixel of the w x h rectangle at (x, y). */
void oled_invert(oled_fb *fb, int x, int y, int w, int h);
/* A circle of radius r around (cx, cy): the outline, and the filled disc (on 1 lit, on 0 dark). */
void oled_circle(oled_fb *fb, int cx, int cy, int r);
void oled_disc(oled_fb *fb, int cx, int cy, int r, int on);
/* Moves row y dx pixels right (left if negative); what leaves the screen is lost, the gap is dark. */
void oled_shift_row(oled_fb *fb, int y, int dx);
/* All 64 column pairs, in send order (oled_fb.h), 64 bytes each. rotate180 sends the frame turned
   half a turn, for a panel mounted upside down, without a second buffer. */
void ssd1325_frame(const oled_fb *fb, int rotate180, uint8_t out[OLED_FRAME_BYTES]);
/* Gray, in a frame in send order: pixel (x, y) at level 0 (dark) to 15 (full; more is 15), turned as
   ssd1325_frame turns it. put4 sets the level; blit4 puts the lit pixels of the w x h bitmap rows (w at
   most 8, bit w - 1 the leftmost column) at (x, y), and text4 the 5x7 text s (oled_text's font and
   spacing), all at level. */
void ssd1325_put4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, unsigned level, int rotate180);
void ssd1325_blit4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const uint8_t *rows, int w, int h, unsigned level,
                   int rotate180);
void ssd1325_text4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const char *s, unsigned level, int rotate180);

#endif
