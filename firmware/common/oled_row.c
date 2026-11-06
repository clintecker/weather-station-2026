/* Text rows: see oled_row.h. */
#include "oled_row.h"
#include <string.h>

#define DEC_DIGITS 24                  /* a uint64_t's 20 digits, a point, a sign */
#define DEC_MAX 6U                     /* decimals oled_put_dec takes: the buffer holds 20 digits */

void oled_put(oled_row *r, const char *s)
{
  size_t used = strlen(r->s);
  /* bound: at most OLED_ROW_CAP - 1 characters are kept */
  while (*s && used + 1 < OLED_ROW_CAP) r->s[used++] = *s++;
  r->s[used] = '\0';
}

void oled_put_dec(oled_row *r, int64_t v, unsigned in_dec, unsigned out_dec, unsigned flags)
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
  else if (flags & OLED_PLUS) num[--at] = '+';
  oled_put(r, &num[at]);
}

void oled_put_uint(oled_row *r, uint32_t v) { oled_put_dec(r, v, 0, 0, 0); }

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
