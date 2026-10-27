/* The bench OLED's layout: see bench_screen.h. */
#include "bench_screen.h"
#include <string.h>
#include "bench_regs.h"

#define NUM_MAX 16U
#define LINE_MAX 24U   /* 21 characters fit across at scale 1 */
#define Y_BUS 0
#define Y_CURRENT 11
#define Y_VBUS 31
#define Y_CELL 42
#define Y_RATE 53
#define BIG 2

/* dst += src, never past n - 1 characters. */
static void append(char *dst, size_t n, const char *src)
{
  size_t used = strlen(dst);
  while (*src && used + 1 < n) dst[used++] = *src++;
  dst[used] = '\0';
}

static void append_hex2(char *dst, size_t n, uint8_t v)
{
  static const char hex[] = "0123456789ABCDEF";
  char two[3] = { hex[v >> 4], hex[v & 0xFU], '\0' };
  append(dst, n, two);
}

void bench_screen(oled_fb *fb, const bench_view *v)
{
  char line[LINE_MAX], num[NUM_MAX];
  oled_clear(fb);

  line[0] = '\0';
  append(line, sizeof line, "I2C");
  if (v->nfound == 0) append(line, sizeof line, " NONE");
  for (unsigned i = 0; i < v->nfound && i < BENCH_SCREEN_MAX_FOUND; i++)
  {
    append(line, sizeof line, " ");
    append_hex2(line, sizeof line, v->found[i]);
  }
  if (v->nfound > BENCH_SCREEN_MAX_FOUND) append(line, sizeof line, " +");
  (void)oled_text(fb, 0, Y_BUS, line, 1);

  if (!v->ina_ok) (void)oled_text(fb, 0, Y_CURRENT, "NO INA228", BIG);
  else
  {
    line[0] = '\0';
    append(line, sizeof line, bench_fixed(num, sizeof num, v->ua, 1, 2, 1));
    append(line, sizeof line, "mA");
    (void)oled_text(fb, 0, Y_CURRENT, line, BIG);

    line[0] = '\0';
    append(line, sizeof line, "VBUS ");
    append(line, sizeof line, bench_fixed(num, sizeof num, v->vbus_uv, 2, 4, 0));
    append(line, sizeof line, "V");
    (void)oled_text(fb, 0, Y_VBUS, line, 1);
  }

  if (!v->gauge_ok) (void)oled_text(fb, 0, Y_CELL, "NO GAUGE", 1);
  else
  {
    line[0] = '\0';
    append(line, sizeof line, "CELL ");
    append(line, sizeof line, bench_fixed(num, sizeof num, v->vcell_uv, 2, 4, 0));
    append(line, sizeof line, "V ");
    append(line, sizeof line, bench_fixed(num, sizeof num, v->soc_mpct, 2, 1, 0));
    append(line, sizeof line, "%");
    (void)oled_text(fb, 0, Y_CELL, line, 1);

    line[0] = '\0';
    append(line, sizeof line, "RATE ");
    append(line, sizeof line, bench_fixed(num, sizeof num, v->crate_mpct_h, 1, 2, 1));
    append(line, sizeof line, "%/h");
    (void)oled_text(fb, 0, Y_RATE, line, 1);
  }
}
