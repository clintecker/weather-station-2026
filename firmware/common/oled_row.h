/* A text row for the 5x7 at scale 1 (oled_font.h), built in place: appends that never overflow, numbers, padding,
 * a left and a right part, a centre between them, and the first of several forms that fits. Pure C, shared by
 * the node's screens and the bench tool (tests/test_scr_view.py, test_i2cscan.py). */
#ifndef OLED_ROW_H_INCLUDED
#define OLED_ROW_H_INCLUDED

#include <stdint.h>

#define OLED_COLS 21                 /* 5x7 characters across at scale 1 */
#define OLED_ROW_CAP 24
typedef struct { char s[OLED_ROW_CAP]; } oled_row;   /* always terminated; appends stop at CAP - 1 */

void oled_put(oled_row *r, const char *s);
/* v with in_dec decimals (<= 6) shown with out_dec (<= in_dec), rounded half away from zero; a '-' only on a
   value that does not round to 0. OLED_PLUS: a '+' on any other. */
#define OLED_PLUS 1U
void oled_put_dec(oled_row *r, int32_t v, unsigned in_dec, unsigned out_dec, unsigned flags);
void oled_put_uint(oled_row *r, uint32_t v);
void oled_put_hex2(oled_row *r, uint8_t b);
void oled_pad_to(oled_row *r, unsigned col);   /* spaces up to column col */
/* r = left, then right ending at column cols; 0 and r untouched if they need more than cols with a space. */
int oled_put_lr(oled_row *r, const char *left, const char *right, unsigned cols);
/* left, right, and centre at (cols - len) / 2 when that leaves a space on each side; else left and right only.
   0 and r untouched if left and right do not fit. */
int oled_put_lcr(oled_row *r, const char *left, const char *centre, const char *right, unsigned cols);
/* Builds form 0, 1, ... n - 1 into r (emptied first) until one fits in cols; the last is kept as built.
   Returns the form. */
typedef void oled_form_fn(oled_row *r, const void *ctx, unsigned form);
unsigned oled_fit(oled_row *r, oled_form_fn *build, const void *ctx, unsigned n, unsigned cols);

#endif
