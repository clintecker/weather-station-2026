/* The drawing surface, its text and its lines, boxes and circles: see oled_draw.h. */
#include "oled_draw.h"
#include <string.h>
#include "font5x7.h"

static int on_screen(int x, int y) { return x >= 0 && x < OLED_W && y >= 0 && y < OLED_H; }

/* The byte that holds logical (x, y), on the screen, and the shift of its nibble. */
static uint8_t *cell(const oled_surf *s, int x, int y, unsigned *shift)
{
  if (s->rot180) { x = OLED_W - 1 - x; y = OLED_H - 1 - y; }
  *shift = (x & 1) ? 0U : 4U;   /* the left pixel of a pair in the high nibble */
  return &s->px[(x / 2) * OLED_H + y];
}

oled_surf oled_surf_on(uint8_t px[OLED_FRAME_BYTES], int rot180)
{
  oled_surf s = { px, (uint8_t)(rot180 != 0), OLED_FULL };
  return s;
}

void oled_clear(const oled_surf *s) { memset(s->px, 0, OLED_FRAME_BYTES); }

void oled_level(const oled_surf *s, int x, int y, unsigned level)
{
  if (!on_screen(x, y)) return;
  unsigned shift;
  uint8_t *b = cell(s, x, y, &shift);
  *b = (uint8_t)((*b & ~(0x0FU << shift)) | ((level > 15U ? 15U : level) << shift));
}

unsigned oled_get(const oled_surf *s, int x, int y)
{
  if (!on_screen(x, y)) return 0;
  unsigned shift;
  return (*cell(s, x, y, &shift) >> shift) & 0x0FU;
}

void oled_set(const oled_surf *s, int x, int y, int on) { oled_level(s, x, y, on ? s->ink : 0U); }

static const uint8_t *glyph(char c)
{
  const char *p = strchr(font5x7_chars, c);
  if (c == '\0' || p == NULL) p = strchr(font5x7_chars, '?');
  return font5x7_rows[p - font5x7_chars];
}

int oled_text(const oled_surf *s, int x, int y, const char *str, int scale)
{
  /* bound: the characters of str, one a pass */
  for (; *str; str++, x += OLED_CHAR_ADVANCE * scale)
  {
    const uint8_t *rows = glyph(*str);
    for (int r = 0; r < FONT5X7_H; r++)
      for (int c = 0; c < FONT5X7_W; c++)
      {
        if (!((rows[r] >> (FONT5X7_W - 1 - c)) & 1)) continue;
        for (int dy = 0; dy < scale; dy++)
          for (int dx = 0; dx < scale; dx++) oled_set(s, x + c * scale + dx, y + r * scale + dy, 1);
      }
  }
  return x;
}

static int iabs(int v) { return v < 0 ? -v : v; }

void oled_line(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned dash)
{
  int dx = iabs(x1 - x0), dy = -iabs(y1 - y0);
  int sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  /* bound: at most max(dx, -dy) + 1 pixels: each pass steps x0 or y0 toward the end, which it reaches */
  for (unsigned n = 0;; n++)
  {
    if (dash == 0 || (n / dash) % 2 == 0) oled_set(s, x0, y0, 1);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

void oled_box(const oled_surf *s, int x, int y, int w, int h)
{
  if (w <= 0 || h <= 0) return;
  oled_line(s, x, y, x + w - 1, y, 0);
  oled_line(s, x, y + h - 1, x + w - 1, y + h - 1, 0);
  oled_line(s, x, y, x, y + h - 1, 0);
  oled_line(s, x + w - 1, y, x + w - 1, y + h - 1, 0);
}

void oled_fill(const oled_surf *s, int x, int y, int w, int h, int on)
{
  for (int j = 0; j < h; j++)
    for (int i = 0; i < w; i++) oled_set(s, x + i, y + j, on);
}

void oled_dotgrid(const oled_surf *s, int x, int y, int w, int h, int step)
{
  if (step <= 0) return;
  /* bound: h / step + 1 rows, step > 0 */
  for (int j = 0; j < h; j += step)
    for (int i = 0; i < w; i += 2) oled_set(s, x + i, y + j, 1);
  /* bound: w / step + 1 columns, step > 0 */
  for (int i = 0; i < w; i += step)
    for (int j = 0; j < h; j += 2) oled_set(s, x + i, y + j, 1);
}

void oled_invert(const oled_surf *s, int x, int y, int w, int h)
{
  for (int j = 0; j < h; j++)
    for (int i = 0; i < w; i++) oled_set(s, x + i, y + j, !oled_get(s, x + i, y + j));
}

void oled_circle(const oled_surf *s, int cx, int cy, int r)
{
  if (r < 0) return;
  int x = r, y = 0, err = 1 - r;   /* the midpoint algorithm, one octant mirrored eight ways */
  /* bound: at most r + 1 passes: y rises by one each time and x never rises, until x < y */
  while (x >= y)
  {
    oled_set(s, cx + x, cy + y, 1); oled_set(s, cx - x, cy + y, 1);
    oled_set(s, cx + x, cy - y, 1); oled_set(s, cx - x, cy - y, 1);
    oled_set(s, cx + y, cy + x, 1); oled_set(s, cx - y, cy + x, 1);
    oled_set(s, cx + y, cy - x, 1); oled_set(s, cx - y, cy - x, 1);
    y++;
    if (err < 0) err += 2 * y + 1;
    else { x--; err += 2 * (y - x) + 1; }
  }
}

void oled_disc(const oled_surf *s, int cx, int cy, int r, int on)
{
  if (r < 0) return;
  for (int j = -r; j <= r; j++)
    for (int i = -r; i <= r; i++)
      if (i * i + j * j <= r * r + r) oled_set(s, cx + i, cy + j, on);   /* + r: reaches the outline's pixels */
}

void oled_shift_row(const oled_surf *s, int y, int dx)
{
  uint8_t row[OLED_W];
  for (int x = 0; x < OLED_W; x++) row[x] = (uint8_t)oled_get(s, x, y);
  for (int x = 0; x < OLED_W; x++)
  {
    int from = x - dx;
    oled_level(s, x, y, from >= 0 && from < OLED_W ? row[from] : 0U);
  }
}
