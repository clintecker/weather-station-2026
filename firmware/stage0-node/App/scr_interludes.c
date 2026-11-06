/* The packet burst, the boot splash and the first interludes of the bench screen (SCOPE, VANE and SYSTEM are
 * detail screens too): see scr_view.h. Each is the approved mockup (.superpowers/sdd/
 * 2026-11-04-node-oled-and-e2e/oledmock gen.py and hack.py, design spec "The interludes") ported pixel for
 * pixel where the mockup was fixed, drawn from the view where it showed a reading:
 *   burst   header TX <seq> SF<sf> BW<kHz> (inverted); up-chirps sweeping 8 px a frame; from frame 8
 *           the frame's bytes in hex, two rows of seven, a row further each frame; footer AES-CCM
 *           <len>B <MHz> under a dashed rule.
 *   scope   the last 30 s of cup pulses (250 ms bins, newest at the right) on a dotted grid, scaled to
 *           the largest bin (at least 4); the pulse rate of the last 3 s; speed, gust, seconds shown.
 *   vane    a compass rose with the needle swinging from N to the vane's point (a point a frame),
 *           its name and degrees, raw millivolts, the table's 16 positions, OK or NO POINT.
 *   system  bars of flash, RAM, stack, journal and this minute's airtime, filling over 8 frames.
 *   boot    radio settings, key and epoch, modules answering; a progress line across the 64 frames
 *           and a sliced-row glitch at frames 28-29 and 60-63.
 *   hack    the eyepatch smiley; HACK at frame 0, THE at 4, PLANET at 8; a wink at 16-17, a glint on
 *           the patch at 18-19, a glitch out at 20-23. */
#include "scr_view.h"
#include <string.h>
#include "oled_draw.h"
#include "font5x7.h"
#include "scr_art.h"

#define CHIRP_W 32                     /* one up-chirp, then the next */
#define CHIRP_STEP 8                   /* pixels the chirps move a frame */
#define BURST_HEX_FRAME 8              /* the bytes follow the chirps */
#define HEX_PER_ROW 7U
#define PLOT_X 1                       /* the scope's plot area, inside its box */
#define PLOT_TOP 10
#define PLOT_BOTTOM 53
#define PLOT_RIGHT 126
#define SCOPE_RATE_BINS 12U            /* 3 s of 250 ms bins */
#define SCOPE_MIN_FULL 4U              /* the scale's floor, in pulses a bin */
#define ROSE_CX 32                     /* tools/make_scr_art.py */
#define ROSE_CY 33
#define VANE_TEXT_X 66
#define BAR_X 36
#define BAR_W 70
#define BAR_FILL_W 66
#define BAR_FILL_FRAMES 8U
#define FACE_CX 31                     /* tools/make_scr_art.py */
#define FACE_CY 32
#define PLANET_PITCH 10                /* PLANET at double height, squeezed to fit beside the face */

static void put_hex2(char *line, uint8_t b)
{
  static const char hex[] = "0123456789ABCDEF";
  char two[3] = { hex[b >> 4], hex[b & 0xFU], '\0' };
  scr_put(line, two);
}

static void hex_row(oled_fb *fb, int y, const scr_view_t *v, unsigned from)
{
  char line[SCR_LINE] = "";
  unsigned len = scr_upto(v->cipher_len, sizeof v->cipher);
  for (unsigned i = 0; i < HEX_PER_ROW; i++)
  {
    if (i != 0) scr_put(line, " ");
    put_hex2(line, v->cipher[(from + i) % len]);
  }
  (void)oled_text(fb, 0, y, line, 1);
}

void scr_burst(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  char line[SCR_LINE] = "TX ";
  scr_put_uint(line, v->last_seq);
  scr_put(line, " SF");
  scr_put_uint(line, v->sf);
  scr_put(line, " BW");
  scr_put_uint(line, v->bw_khz_div125 * 125U);
  scr_header(fb, line);
  int shift = (int)(frame * CHIRP_STEP % CHIRP_W);
  for (int n = 0; n < 5; n++)
  {
    int x0 = n * CHIRP_W - shift;
    oled_line(fb, x0, 30, x0 + CHIRP_W - 1, 11, 0);
    oled_line(fb, x0 + CHIRP_W - 1, 11, x0 + CHIRP_W - 1, 30, 1);
  }
  if (frame >= BURST_HEX_FRAME && v->cipher_len != 0)
    for (unsigned r = 0; r < 2U; r++) hex_row(fb, 35 + 9 * (int)r, v, (frame - BURST_HEX_FRAME + r) * HEX_PER_ROW);
  oled_line(fb, 0, 53, OLED_W - 1, 53, 2);
  char foot[SCR_LINE] = "AES-CCM ";
  scr_put_uint(foot, v->cipher_len);
  scr_put(foot, "B ");
  scr_put_dec(foot, v->freq_khz, 3, 1, 0);
  scr_put(foot, "MHz");
  (void)oled_text(fb, 0, 56, foot, 1);
}

static void scope_trace(oled_fb *fb, const wind_live_t *w)
{
  unsigned n = scr_upto(w->nbins, WIND_LIVE_BINS), full = SCOPE_MIN_FULL;
  for (unsigned i = 0; i < n; i++)
    if (w->bins[i] > full) full = w->bins[i];
  int px = 0, py = 0;
  for (unsigned i = 0; i < n; i++)
  {
    int x = PLOT_RIGHT - (int)((n - 1U - i) * (PLOT_RIGHT - PLOT_X) / (WIND_LIVE_BINS - 1U));
    int y = PLOT_BOTTOM - (int)(w->bins[i] * (unsigned)(PLOT_BOTTOM - PLOT_TOP) / full);
    if (i == 0) oled_set(fb, x, y, 1);
    else oled_line(fb, px, py, x, y, 0);
    px = x; py = y;
  }
}

void scr_scope(oled_fb *fb, const scr_view_t *v)
{
  const wind_live_t *w = &v->wind;
  unsigned n = scr_upto(w->nbins, WIND_LIVE_BINS), recent = n < SCOPE_RATE_BINS ? n : SCOPE_RATE_BINS;
  uint32_t sum = 0;
  for (unsigned i = n - recent; i < n; i++) sum += w->bins[i];
  char line[SCR_LINE] = "SCOPE CUPS";
  scr_pad_to(line, 13);
  scr_put_dec(line, recent ? sum * 40U / recent : 0U, 1, 1, 0);   /* pulses over recent / 4 s, in 0.1 Hz */
  scr_put(line, "Hz");
  (void)oled_text(fb, 0, 0, line, 1);
  oled_box(fb, 0, 9, OLED_W, 46);
  oled_dotgrid(fb, PLOT_X, PLOT_TOP, PLOT_RIGHT, 44, 16);
  scope_trace(fb, w);
  char foot[SCR_LINE] = "";
  scr_put_dec(foot, w->speed_cms, 2, 1, 0);
  scr_put(foot, "m/s  G");
  scr_put_dec(foot, w->gust_cms, 2, 1, 0);
  scr_put(foot, "  ");
  scr_put_uint(foot, n / 4U);
  scr_put(foot, "s");
  (void)oled_text(fb, 0, 57, foot, 1);
}

static void vane_text(oled_fb *fb, int point, const scr_view_t *v)
{
  char line[SCR_LINE] = "-";
  if (point >= 0) { line[0] = '\0'; scr_put(line, scr_point_names[point]); scr_put(line, " "); scr_put_uint(line, (unsigned)point * 45U / 2U); }
  (void)oled_text(fb, VANE_TEXT_X, 4, "VANE", 1);
  (void)oled_text(fb, VANE_TEXT_X, 16, line, 1);
  char mv[SCR_LINE] = "";
  scr_put_uint(mv, v->wind.vane_mv);
  scr_put(mv, "mV");
  (void)oled_text(fb, VANE_TEXT_X, 32, mv, 1);
  (void)oled_text(fb, VANE_TEXT_X, 44, "16 POS", 1);
  (void)oled_text(fb, VANE_TEXT_X, 56, point >= 0 ? "OK" : "NO POINT", 1);
}

void scr_vane(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  int point = v->wind.point >= 0 && v->wind.point < 16 ? v->wind.point : -1;
  scr_blit(fb, &scr_art_rose, 0, 0);
  (void)oled_text(fb, ROSE_CX - 2, 1, "N", 1);
  if (point >= 0)
  {
    int shown = frame < (unsigned)point ? (int)frame : point;   /* swinging round from N */
    oled_line(fb, ROSE_CX, ROSE_CY, ROSE_CX + scr_sin20(shown), ROSE_CY - scr_sin20(shown + 4), 0);
  }
  oled_fill(fb, ROSE_CX - 1, ROSE_CY - 1, 3, 3, 1);
  vane_text(fb, point, v);
}

void scr_system(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  static const char *const names[5] = { "FLASH", "RAM", "STACK", "JRNL", "AIR" };
  const uint8_t pct[5] = { v->flash_pct, v->ram_pct, v->stack_pct, v->journal_pct, v->airtime_pct };
  char line[SCR_LINE] = "SYS  WS-NODE  ID ";
  scr_put_uint(line, v->station);
  scr_header(fb, line);
  for (unsigned i = 0; i < 5U; i++)
  {
    int y = 11 + 10 * (int)i;
    unsigned p = pct[i] > 100U ? 100U : pct[i];
    char num[SCR_LINE] = "";
    scr_put_uint(num, p);
    (void)oled_text(fb, 0, y, names[i], 1);
    oled_box(fb, BAR_X, y, BAR_W, 7);
    oled_fill(fb, BAR_X + 2, y + 2, (int)scr_grow(BAR_FILL_W * p / 100U, frame, BAR_FILL_FRAMES), 3, 1);
    (void)oled_text(fb, 110, y, num, 1);
  }
}

static void boot_text(oled_fb *fb, const scr_view_t *v)
{
  char link[SCR_LINE] = "LINK ";
  scr_put_dec(link, v->freq_khz, 3, 1, 0);
  scr_put(link, " SF");
  scr_put_uint(link, v->sf);
  char key[SCR_LINE] = "";
  scr_put(key, v->key_ok ? "KEY OK  EPOCH " : "NO KEY  EPOCH ");
  scr_put_uint(key, v->epoch);
  char mods[SCR_LINE] = "MODULES ";
  scr_put_uint(mods, v->modules_active);
  scr_put(mods, "/");
  scr_put_uint(mods, v->modules);
  (void)oled_text(fb, 10, 6, "WS-NODE  BOOT", 1);
  (void)oled_text(fb, 10, 18, link, 1);
  (void)oled_text(fb, 10, 30, key, 1);
  (void)oled_text(fb, 10, 42, mods, 1);
}

void scr_boot(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  static const int8_t sliced[5] = { 8, 9, 20, 21, 33 };
  boot_text(fb, v);
  if (frame == 28U || frame == 29U || frame >= 60U)
  {
    for (unsigned i = 0; i < 5U; i++) oled_shift_row(fb, sliced[i], 5);
    oled_invert(fb, 0, 27, OLED_W, 3);
  }
  oled_line(fb, 0, 62, (int)(frame * (OLED_W - 1U) / 63U), 62, 0);
}

/* s at double height, each glyph 9 pixels wide (its last column overlapping the one before) on a
   10-pixel pitch: PLANET fits the 62 pixels beside the face. */
static void squeezed_text(oled_fb *fb, int x, int y, const char *s)
{
  static const uint8_t col_x[FONT5X7_W] = { 0, 2, 4, 6, 7 };
  /* bound: the characters of s, one a pass */
  for (; *s; s++, x += PLANET_PITCH)
  {
    const char *at = strchr(font5x7_chars, *s);
    if (at == NULL) continue;
    const uint8_t *rows = font5x7_rows[at - font5x7_chars];
    for (int r = 0; r < FONT5X7_H; r++)
      for (int c = 0; c < FONT5X7_W; c++)
        if ((rows[r] >> (FONT5X7_W - 1 - c)) & 1U) oled_fill(fb, x + col_x[c], y + 2 * r, 2, 2, 1);
  }
}

static void face_eye(oled_fb *fb, int wink, int glint)
{
  if (wink)
  {
    oled_line(fb, FACE_CX - 15, FACE_CY - 8, FACE_CX - 7, FACE_CY - 8, 0);
    oled_line(fb, FACE_CX - 15, FACE_CY - 7, FACE_CX - 7, FACE_CY - 7, 0);
  }
  else
    for (int j = -4; j <= 4; j++)
      for (int i = -4; i <= 4; i++)
        if (i * i + j * j <= 16) oled_set(fb, FACE_CX - 11 + i, FACE_CY - 8 + j, 1);
  if (glint)
  {
    oled_set(fb, FACE_CX + 8, FACE_CY - 11, 0);
    oled_set(fb, FACE_CX + 9, FACE_CY - 11, 0);
    oled_set(fb, FACE_CX + 8, FACE_CY - 10, 0);
  }
}

/* Frame 20 is the mockup's glitch; 21-23 slice other rows the other way. */
static void hack_glitch(oled_fb *fb, unsigned g)
{
  static const int8_t sliced[5] = { 8, 9, 30, 31, 50 };
  static const struct { int8_t dy, dx, band; } step[4] = { { 0, 4, 36 }, { 6, -3, 22 }, { 3, 5, 46 }, { -4, -6, 28 } };
  for (unsigned i = 0; i < 5U; i++) oled_shift_row(fb, sliced[i] + step[g].dy, step[g].dx);
  oled_invert(fb, 0, step[g].band, OLED_W, 2);
}

void scr_hack(oled_fb *fb, unsigned frame)
{
  scr_blit(fb, &scr_art_face, 0, 0);
  face_eye(fb, frame == 16U || frame == 17U, frame == 18U || frame == 19U);
  (void)oled_text(fb, 68, 2, "HACK", 2);
  if (frame >= 4U) (void)oled_text(fb, 74, 21, "THE", 2);
  if (frame >= 8U) squeezed_text(fb, 64, 42, "PLANET");
  if (frame >= 20U && frame < 24U) hack_glitch(fb, frame - 20U);
}
