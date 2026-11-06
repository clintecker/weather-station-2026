/* Text rows: see oled_row.h. */
#include "oled_row.h"
#include <string.h>

#define DEC_DIGITS 13                  /* a uint32_t's 10 digits, a point, a sign, the end */
#define DEC_MAX 6U                     /* decimals oled_put_dec takes */

void oled_put(oled_row *r, const char *s)
{
  size_t used = strlen(r->s);
  /* bound: at most OLED_ROW_CAP - 1 characters are kept */
  while (*s && used + 1 < OLED_ROW_CAP) r->s[used++] = *s++;
  r->s[used] = '\0';
}

/* m (the magnitude, minus: of a negative value) as oled_put_dec. m + div / 2 cannot wrap: m is at most 2^31
   with decimals to drop (oled_put_dec), and div is 1 without (oled_put_uint). */
static void put_mag(oled_row *r, uint32_t m, int minus, unsigned in_dec, unsigned out_dec, unsigned flags)
{
  if (in_dec > DEC_MAX) in_dec = DEC_MAX;
  if (out_dec > in_dec) out_dec = in_dec;
  uint32_t div = 1;
  for (unsigned i = out_dec; i < in_dec; i++) div *= 10U;
  m = (m + div / 2U) / div;
  int negative = minus && m != 0;
  char num[DEC_DIGITS];
  unsigned at = DEC_DIGITS - 1, digits = 0;
  num[at] = '\0';
  /* bound: at most 10 digits and a point (or out_dec + 1 digits, out_dec <= 6); at > 1 throughout */
  do
  {
    if (out_dec != 0 && digits == out_dec) num[--at] = '.';
    num[--at] = (char)('0' + m % 10U);
    m /= 10U;
    digits++;
  } while (m != 0 || digits <= out_dec);
  if (negative) num[--at] = '-';
  else if (flags & OLED_PLUS) num[--at] = '+';
  oled_put(r, &num[at]);
}

void oled_put_dec(oled_row *r, int32_t v, unsigned in_dec, unsigned out_dec, unsigned flags)
{
  put_mag(r, v < 0 ? 0U - (uint32_t)v : (uint32_t)v, v < 0, in_dec, out_dec, flags);
}

void oled_put_uint(oled_row *r, uint32_t v) { put_mag(r, v, 0, 0, 0, 0); }

void oled_put_hex2(oled_row *r, uint8_t b)
{
  static const char hex[] = "0123456789ABCDEF";
  char two[3] = { hex[b >> 4], hex[b & 0xFU], '\0' };
  oled_put(r, two);
}

void oled_pad_to(oled_row *r, unsigned col)
{
  size_t used = strlen(r->s);
  /* bound: at most OLED_ROW_CAP - 1 characters */
  while (used < col && used + 1 < OLED_ROW_CAP) r->s[used++] = ' ';
  r->s[used] = '\0';
}

int oled_put_lr(oled_row *r, const char *left, const char *right, unsigned cols)
{
  size_t l = strlen(left), n = strlen(right);
  if (l + 1U + n > cols) return 0;
  r->s[0] = '\0';
  oled_put(r, left);
  oled_pad_to(r, (unsigned)(cols - n));
  oled_put(r, right);
  return 1;
}

int oled_put_lcr(oled_row *r, const char *left, const char *centre, const char *right, unsigned cols)
{
  if (!oled_put_lr(r, left, right, cols)) return 0;
  size_t c = strlen(centre), at = c <= cols ? (cols - c) / 2U : 0U;
  if (at >= strlen(left) + 1U && at + c + 1U + strlen(right) <= cols) memcpy(r->s + at, centre, c);   /* over the spaces */
  return 1;
}

unsigned oled_fit(oled_row *r, oled_form_fn *build, const void *ctx, unsigned n, unsigned cols)
{
  unsigned form = 0;
  /* bound: n - 1 forms tried, then the last */
  for (; form + 1U < n; form++)
  {
    r->s[0] = '\0';
    build(r, ctx, form);
    if (strlen(r->s) <= cols) return form;
  }
  r->s[0] = '\0';
  build(r, ctx, form);   /* the last (or only) form, as built */
  return form;
}
