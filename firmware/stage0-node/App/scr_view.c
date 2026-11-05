/* The bench screens' dispatch, their frame counts and the helpers they share: see scr_view.h. */
#include "scr_view.h"
#include <string.h>
#include "oled_draw.h"
#include "scr_font.h"
#include "wsmp_registry.h"

#define HEADER_PX 8
#define RAIN_TIPS_MAX 1000000U         /* 279 m of rain: more reads as this */
#define DEC_DIGITS 24                  /* a uint64_t's 20 digits, a point, a sign */
#define DEC_MAX 6U                     /* decimals scr_put_dec takes: the buffer holds 20 digits */

const char *const scr_point_names[16] = { "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" };

void scr_put(char *line, const char *s)
{
  size_t used = strlen(line);
  /* bound: at most SCR_LINE - 1 characters are kept */
  while (*s && used + 1 < SCR_LINE) line[used++] = *s++;
  line[used] = '\0';
}

void scr_put_dec(char *line, int64_t v, unsigned in_dec, unsigned out_dec, int plus)
{
  if (in_dec > DEC_MAX) in_dec = DEC_MAX;
  if (out_dec > in_dec) out_dec = in_dec;
  uint64_t m = v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v, div = 1;
  for (unsigned i = out_dec; i < in_dec; i++) div *= 10U;
  m = (m + div / 2U) / div;
  int negative = v < 0 && m != 0;
  char num[DEC_DIGITS];
  unsigned at = DEC_DIGITS - 1, digits = 0;
  num[at] = '\0';
  /* bound: at most 20 digits and a point; at > 1 throughout, as a uint64_t has 20 digits */
  do
  {
    if (out_dec != 0 && digits == out_dec) num[--at] = '.';
    num[--at] = (char)('0' + m % 10U);
    m /= 10U;
    digits++;
  } while (m != 0 || digits <= out_dec);
  if (negative) num[--at] = '-';
  else if (plus) num[--at] = '+';
  scr_put(line, &num[at]);
}

void scr_put_uint(char *line, uint32_t v) { scr_put_dec(line, v, 0, 0, 0); }

void scr_put_rain_mm(char *line, uint32_t tips)
{
  uint32_t t = tips > RAIN_TIPS_MAX ? RAIN_TIPS_MAX : tips;
  scr_put_dec(line, (int64_t)t * (int64_t)WSMP_RAIN_NM_PER_TIP, 6, 2, 0);   /* 0.2794 mm a tip (SEN-15901) */
}

void scr_put_age(char *line, uint32_t s)
{
  if (s < 100U) { scr_put_uint(line, s); scr_put(line, "s"); }
  else if (s < 6000U) { scr_put_uint(line, s / 60U); scr_put(line, "m"); }
  else { scr_put_uint(line, s / 3600U); scr_put(line, "h"); }
}

void scr_pad_to(char *line, unsigned col)
{
  size_t used = strlen(line);
  /* bound: at most SCR_LINE - 1 characters */
  while (used < col && used + 1 < SCR_LINE) line[used++] = ' ';
  line[used] = '\0';
}


int scr_put_lr(char *line, const char *left, const char *right)
{
  size_t l = strlen(left), r = strlen(right);
  if (l + 1U + r > SCR_COLS) return 0;
  line[0] = '\0';
  scr_put(line, left);
  scr_pad_to(line, (unsigned)(SCR_COLS - r));
  scr_put(line, right);
  return 1;
}

void scr_row(oled_fb *fb, int y, const char *text) { (void)oled_text(fb, 0, y, text, 1); }

void scr_row_right(oled_fb *fb, int y, const char *text)
{
  (void)oled_text(fb, OLED_W - OLED_CHAR_ADVANCE * (int)strlen(text) + 1, y, text, 1);
}

void scr_header(oled_fb *fb, const char *text)
{
  (void)oled_text(fb, 0, 0, text, 1);
  oled_invert(fb, 0, 0, OLED_W, HEADER_PX);
}

static int big_glyph(char c)
{
  const char *at = c ? strchr(scr_big_chars, c) : NULL;
  return at ? (int)(at - scr_big_chars) : -1;
}

int scr_big_width(const char *s)
{
  int w = 0;
  /* bound: the characters of s */
  for (; *s; s++)
  {
    int g = big_glyph(*s);
    if (g >= 0) w += (w ? SCR_BIG_GAP : 0) + scr_big_w[g];
  }
  return w;
}

int scr_big_text(oled_fb *fb, int x, int y, const char *s)
{
  int first = 1;
  /* bound: the characters of s */
  for (; *s; s++)
  {
    int g = big_glyph(*s);
    if (g < 0) continue;
    if (!first) x += SCR_BIG_GAP;
    first = 0;
    for (int r = 0; r < SCR_BIG_H; r++)
      for (int c = 0; c < scr_big_w[g]; c++)
        if ((scr_big_rows[g][r] >> (15 - c)) & 1U) oled_set(fb, x + c, y + r, 1);
    x += scr_big_w[g];
  }
  return x;
}

void scr_blit(oled_fb *fb, const scr_art *a, int dx, int dy)
{
  for (unsigned j = 0; j < a->h; j++)
    for (unsigned i = 0; i < 64U; i++)
      if ((a->rows[j] >> (63U - i)) & 1U) oled_set(fb, a->x + dx + (int)i, a->y + dy + (int)j, 1);
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

unsigned scr_frames(enum scr_id id)
{
  switch (id)
  {
  case SCR_HOME: return 1U;
  case SCR_BANNER: return 24U;
  case SCR_BURST: return 16U;
  case SCR_HACK: return 24U;
  case SCR_AIR: case SCR_PRESSURE: case SCR_POWER: case SCR_RADIO: return 8U;
  default: return 64U;
  }
}

int scr_draw_gray(uint8_t *out, enum scr_id id, unsigned frame, const scr_view_t *v, int rotate180)
{
  if (id != SCR_MATRIX) return 0;
  if (frame >= scr_frames(id)) frame = scr_frames(id) - 1U;
  memset(out, 0, OLED_FRAME_BYTES);
  scr_matrix(out, frame, v, rotate180);
  return 1;
}

void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v)
{
  oled_clear(fb);
  if (id != SCR_HOME && id != SCR_BANNER && frame >= scr_frames(id)) frame = scr_frames(id) - 1U;
  switch (id)
  {
  case SCR_BURST: scr_burst(fb, frame, v); break;
  case SCR_BANNER: scr_home(fb, frame, v, 1); break;
  case SCR_AIR: scr_air(fb, frame, v); break;
  case SCR_PRESSURE: scr_pressure(fb, frame, v); break;
  case SCR_POWER: scr_power(fb, frame, v); break;
  case SCR_RADIO: scr_radio(fb, frame, v); break;
  case SCR_SCOPE: scr_scope(fb, v); break;
  case SCR_VANE: scr_vane(fb, frame, v); break;
  case SCR_RAIN: scr_rain(fb, v); break;
  case SCR_SYSTEM: scr_system(fb, frame, v); break;
  case SCR_BOOT: scr_boot(fb, frame, v); break;
  case SCR_HACK: scr_hack(fb, frame); break;
  case SCR_FORTUNE: scr_fortune(fb, frame, v); break;
  case SCR_FROG: scr_frog(fb, frame, v); break;
  case SCR_MATRIX: break;   /* gray: scr_draw_gray */
  case SCR_PINBALL: scr_pinball(fb, frame, v); break;
  default: scr_home(fb, frame, v, 0); break;
  }
}
