/* The bench OLED's layout: see bench_screen.h. */
#include "bench_screen.h"
#include <string.h>
#include "bench_regs.h"

#define NUM_MAX 16U
#define LINE_MAX 24U   /* 21 characters fit across at scale 1 */
#define ROW_PX 8       /* 7-pixel glyphs and a 1-pixel gap: eight rows */
#define RAIN_TENTH_UM_PER_TIP 2794   /* 0.2794 mm a tip (SEN-15901), in 10^-4 mm */
enum { ROW_BUS, ROW_BATT, ROW_CELL, ROW_AIR, ROW_BOX, ROW_PRESS, ROW_WIND, ROW_RAIN };

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

static void append_fixed(char *dst, size_t n, int32_t value, unsigned drop, unsigned decimals, int sign)
{
  char num[NUM_MAX];
  append(dst, n, bench_fixed(num, sizeof num, value, drop, decimals, sign));
}

static void append_uint(char *dst, size_t n, uint32_t v)
{
  append_fixed(dst, n, (int32_t)(v > INT32_MAX ? INT32_MAX : v), 0, 0, 0);
}

static void row(oled_fb *fb, int r, const char *text) { (void)oled_text(fb, 0, r * ROW_PX, text, 1); }

/* "<label> " then the temperature and humidity, or "<label> NO <part>". */
static void th_row(oled_fb *fb, int r, const char *label, const char *part, int ok, int32_t centi_c, int32_t centi_rh)
{
  char line[LINE_MAX] = "";
  append(line, sizeof line, label);
  if (!ok) { append(line, sizeof line, " NO "); append(line, sizeof line, part); row(fb, r, line); return; }
  append(line, sizeof line, " ");
  append_fixed(line, sizeof line, centi_c, 0, 2, 0);
  append(line, sizeof line, "C ");
  append_fixed(line, sizeof line, centi_rh, 0, 2, 0);
  append(line, sizeof line, "%");
  row(fb, r, line);
}

void bench_screen(oled_fb *fb, const bench_view *v)
{
  char line[LINE_MAX];
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
  row(fb, ROW_BUS, line);

  line[0] = '\0';
  append(line, sizeof line, "BATT ");
  if (!v->ina_ok) append(line, sizeof line, "NO INA228");
  else
  {
    append_fixed(line, sizeof line, v->ua, 1, 2, 1);
    append(line, sizeof line, "mA ");
    append_fixed(line, sizeof line, v->vbus_uv, 3, 3, 0);   /* the INA228 VBUS: its sense lead on OUT (P5) */
    append(line, sizeof line, "V");
  }
  row(fb, ROW_BATT, line);

  line[0] = '\0';
  append(line, sizeof line, "CELL ");
  if (!v->gauge_ok) append(line, sizeof line, "NO MAX17048");
  else
  {
    append_fixed(line, sizeof line, v->vcell_uv, 3, 3, 0);
    append(line, sizeof line, "V ");
    append_fixed(line, sizeof line, v->soc_mpct, 2, 1, 0);
    append(line, sizeof line, "%");
  }
  row(fb, ROW_CELL, line);

  th_row(fb, ROW_AIR, "AIR", "SHT45", v->air_ok, v->air_centi_c, v->air_centi_rh);
  th_row(fb, ROW_BOX, "BOX", "SHTC3", v->box_ok, v->box_centi_c, v->box_centi_rh);

  line[0] = '\0';
  append(line, sizeof line, "P ");
  if (!v->press_ok) append(line, sizeof line, "NO BMP581");
  else { append_fixed(line, sizeof line, v->press_dhpa, 0, 1, 0); append(line, sizeof line, "hPa"); }
  append(line, sizeof line, " UV ");
  if (!v->uv_ok) append(line, sizeof line, "NO");
  else append_uint(line, sizeof line, v->uv_counts);
  row(fb, ROW_PRESS, line);

  if (!v->meters_ok) return;
  line[0] = '\0';
  append(line, sizeof line, "WIND ");
  append_fixed(line, sizeof line, v->wind_ums, 4, 2, 0);
  append(line, sizeof line, "m/s ");
  append(line, sizeof line, v->vane ? v->vane : "?");
  row(fb, ROW_WIND, line);

  line[0] = '\0';
  append(line, sizeof line, "RAIN ");
  append_uint(line, sizeof line, v->tips);
  append(line, sizeof line, " TIPS ");
  append_fixed(line, sizeof line, (int32_t)(v->tips > 100000U ? 100000U : v->tips) * RAIN_TENTH_UM_PER_TIP, 2, 2, 0);
  append(line, sizeof line, "mm");
  row(fb, ROW_RAIN, line);
}
