/* The OLED's frame buffer, text and SSD1325 pixel order: see oled_fb.h. */
#include "oled_fb.h"
#include <string.h>
#include "font5x7.h"

#define ROW_BYTES (OLED_W / 8)

void oled_clear(oled_fb *fb) { memset(fb->px, 0, sizeof fb->px); }

static int on_screen(int x, int y) { return x >= 0 && x < OLED_W && y >= 0 && y < OLED_H; }

void oled_set(oled_fb *fb, int x, int y, int on)
{
  if (!on_screen(x, y)) return;
  uint8_t bit = (uint8_t)(0x80U >> (x % 8));
  uint8_t *b = &fb->px[y * ROW_BYTES + x / 8];
  *b = on ? (uint8_t)(*b | bit) : (uint8_t)(*b & (uint8_t)~bit);
}

int oled_get(const oled_fb *fb, int x, int y)
{
  if (!on_screen(x, y)) return 0;
  return (fb->px[y * ROW_BYTES + x / 8] >> (7 - x % 8)) & 1;
}

static const uint8_t *glyph(char c)
{
  const char *p = strchr(font5x7_chars, c);
  if (c == '\0' || p == NULL) p = strchr(font5x7_chars, '?');
  return font5x7_rows[p - font5x7_chars];
}

int oled_text(oled_fb *fb, int x, int y, const char *s, int scale)
{
  /* bound: the characters of s, one a pass */
  for (; *s; s++, x += OLED_CHAR_ADVANCE * scale)
  {
    const uint8_t *rows = glyph(*s);
    for (int r = 0; r < FONT5X7_H; r++)
      for (int c = 0; c < FONT5X7_W; c++)
      {
        if (!((rows[r] >> (FONT5X7_W - 1 - c)) & 1)) continue;
        for (int dy = 0; dy < scale; dy++)
          for (int dx = 0; dx < scale; dx++) oled_set(fb, x + c * scale + dx, y + r * scale + dy, 1);
      }
  }
  return x;
}
