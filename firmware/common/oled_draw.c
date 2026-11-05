/* Lines, boxes, circles and the whole-frame SSD1325 order: see oled_draw.h. */
#include "oled_draw.h"
#include <string.h>
#include "font5x7.h"

#define LIT_LEFT 0xF0U    /* full brightness in the high nibble: the left pixel of the pair */
#define LIT_RIGHT 0x0FU

static int iabs(int v) { return v < 0 ? -v : v; }

void oled_line(oled_fb *fb, int x0, int y0, int x1, int y1, unsigned dash)
{
  int dx = iabs(x1 - x0), dy = -iabs(y1 - y0);
  int sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  /* bound: at most max(dx, -dy) + 1 pixels: each pass steps x0 or y0 toward the end, which it reaches */
  for (unsigned n = 0;; n++)
  {
    if (dash == 0 || (n / dash) % 2 == 0) oled_set(fb, x0, y0, 1);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

void oled_box(oled_fb *fb, int x, int y, int w, int h)
{
  if (w <= 0 || h <= 0) return;
  oled_line(fb, x, y, x + w - 1, y, 0);
  oled_line(fb, x, y + h - 1, x + w - 1, y + h - 1, 0);
  oled_line(fb, x, y, x, y + h - 1, 0);
  oled_line(fb, x + w - 1, y, x + w - 1, y + h - 1, 0);
}

void oled_fill(oled_fb *fb, int x, int y, int w, int h, int on)
{
  for (int j = 0; j < h; j++)
    for (int i = 0; i < w; i++) oled_set(fb, x + i, y + j, on);
}

void oled_dotgrid(oled_fb *fb, int x, int y, int w, int h, int step)
{
  if (step <= 0) return;
  /* bound: h / step + 1 rows, step > 0 */
  for (int j = 0; j < h; j += step)
    for (int i = 0; i < w; i += 2) oled_set(fb, x + i, y + j, 1);
  /* bound: w / step + 1 columns, step > 0 */
  for (int i = 0; i < w; i += step)
    for (int j = 0; j < h; j += 2) oled_set(fb, x + i, y + j, 1);
}

void oled_invert(oled_fb *fb, int x, int y, int w, int h)
{
  for (int j = 0; j < h; j++)
    for (int i = 0; i < w; i++) oled_set(fb, x + i, y + j, !oled_get(fb, x + i, y + j));
}

void oled_circle(oled_fb *fb, int cx, int cy, int r)
{
  if (r < 0) return;
  int x = r, y = 0, err = 1 - r;   /* the midpoint algorithm, one octant mirrored eight ways */
  /* bound: at most r + 1 passes: y rises by one each time and x never rises, until x < y */
  while (x >= y)
  {
    oled_set(fb, cx + x, cy + y, 1); oled_set(fb, cx - x, cy + y, 1);
    oled_set(fb, cx + x, cy - y, 1); oled_set(fb, cx - x, cy - y, 1);
    oled_set(fb, cx + y, cy + x, 1); oled_set(fb, cx - y, cy + x, 1);
    oled_set(fb, cx + y, cy - x, 1); oled_set(fb, cx - y, cy - x, 1);
    y++;
    if (err < 0) err += 2 * y + 1;
    else { x--; err += 2 * (y - x) + 1; }
  }
}

void oled_disc(oled_fb *fb, int cx, int cy, int r, int on)
{
  if (r < 0) return;
  for (int j = -r; j <= r; j++)
    for (int i = -r; i <= r; i++)
      if (i * i + j * j <= r * r + r) oled_set(fb, cx + i, cy + j, on);   /* + r: reaches the outline's pixels */
}

void oled_shift_row(oled_fb *fb, int y, int dx)
{
  uint8_t row[OLED_W];
  for (int x = 0; x < OLED_W; x++) row[x] = (uint8_t)oled_get(fb, x, y);
  for (int x = 0; x < OLED_W; x++)
  {
    int from = x - dx;
    oled_set(fb, x, y, from >= 0 && from < OLED_W ? row[from] : 0);
  }
}

void ssd1325_frame(const oled_fb *fb, int rotate180, uint8_t out[OLED_FRAME_BYTES])
{
  for (int cp = 0; cp < OLED_COLPAIRS; cp++)
    for (int y = 0; y < OLED_H; y++)
    {
      int xl = cp * 2, xr = xl + 1, sy = y;
      if (rotate180) { xl = OLED_W - 1 - xl; xr = OLED_W - 1 - xr; sy = OLED_H - 1 - y; }
      out[cp * OLED_H + y] = (uint8_t)((oled_get(fb, xl, sy) ? LIT_LEFT : 0U) | (oled_get(fb, xr, sy) ? LIT_RIGHT : 0U));
    }
}

void ssd1325_put4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, unsigned level, int rotate180)
{
  if (x < 0 || x >= OLED_W || y < 0 || y >= OLED_H) return;
  if (rotate180) { x = OLED_W - 1 - x; y = OLED_H - 1 - y; }
  uint8_t v = (uint8_t)(level > 15U ? 15U : level), *b = &frame[(x / 2) * OLED_H + y];
  *b = (x & 1) ? (uint8_t)((*b & 0xF0U) | v) : (uint8_t)((*b & 0x0FU) | (uint8_t)(v << 4));
}

void ssd1325_blit4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const uint8_t *rows, int w, int h, unsigned level,
                   int rotate180)
{
  if (w > 8) w = 8;
  /* bound: h rows of at most 8 columns */
  for (int r = 0; r < h; r++)
    for (int c = 0; c < w; c++)
      if ((rows[r] >> (w - 1 - c)) & 1U) ssd1325_put4(frame, x + c, y + r, level, rotate180);
}

void ssd1325_text4(uint8_t frame[OLED_FRAME_BYTES], int x, int y, const char *s, unsigned level, int rotate180)
{
  /* bound: the characters of s, one a pass */
  for (; *s; s++, x += OLED_CHAR_ADVANCE)
  {
    const char *p = strchr(font5x7_chars, *s);
    if (p == NULL) p = strchr(font5x7_chars, '?');
    ssd1325_blit4(frame, x, y, font5x7_rows[p - font5x7_chars], FONT5X7_W, FONT5X7_H, level, rotate180);
  }
}
