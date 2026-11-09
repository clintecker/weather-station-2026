/* The packet burst, the boot splash and the first interludes of the bench screen (SCOPE, VANE and SYSTEM are
 * detail screens too): see scr_screens.h. Each is the approved mockup (.superpowers/sdd/
 * 2026-11-04-node-oled-and-e2e/oledmock gen.py and hack.py, design spec "The interludes") ported pixel for
 * pixel where the mockup was fixed, drawn from the view where it showed a reading:
 *   burst   header TX <seq> SF<sf> BW<kHz> (inverted); up-chirps sweeping 8 px a frame; from frame 8
 *           the frame's bytes in hex, two rows of seven, a row further each frame; footer AES-CCM
 *           <len>B <MHz> under a dashed rule.
 *   scope   the last 30 s of cup pulses (250 ms bins, newest at the right) on a dotted grid, the
 *           sparkline's trace (scr_trace) from 0 to the largest bin (at least 4); the pulse rate of the last 3 s; speed, gust, seconds shown.
 *   vane    a compass rose with the needle swinging from N to the vane's point (a point a frame),
 *           its name and degrees, raw millivolts, the table's 16 positions, OK or NO POINT.
 *   system  bars of flash, RAM, stack, journal and this minute's airtime, filling over 8 frames.
 *   boot    radio settings, key and epoch, MODULES ...; a progress line across the 64 frames
 *           and a sliced-row glitch at frames 28-29 and 60-63.
 *   modules the boot checklist: each local port and its mark (scanning dots, OK, a dim NONE, a blinking
 *           FAULT), the active ports of those with a module, and how the wait stands.
 *   hack    the eyepatch smiley; HACK at frame 0, THE at 4, PLANET at 8; a wink at 16-17, a glint on
 *           the patch at 18-19, a glitch out at 20-23. */
#include "scr_screens.h"
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
#define SCOPE_MIN_FULL 4               /* the scale's floor, in pulses a bin */
#define ROSE_CX 32                     /* tools/make_scr_art.py */
#define ROSE_CY 33
#define VANE_TEXT_X 66
#define BAR_X 36
#define BAR_W 70
#define BAR_FILL_W 66
#define FACE_CX 31                     /* tools/make_scr_art.py */
#define FACE_CY 32
#define CHECK_DIM 4U                   /* the checklist: a port with no module, dim */
#define CHECK_WAIT_INK 8U              /* and one still waiting */
#define PLANET_PITCH 10                /* PLANET at double height, squeezed to fit beside the face */

static void hex_row(const oled_surf *s, int y, const scr_view_t *v, unsigned from)
{
  oled_row line = { "" };
  unsigned len = v->cipher_len < sizeof v->cipher ? v->cipher_len : sizeof v->cipher;
  for (unsigned i = 0; i < HEX_PER_ROW; i++)
  {
    if (i != 0) oled_put(&line, " ");
    oled_put_hex2(&line, v->cipher[(from + i) % len]);
  }
  scr_label(s, y, line.s, SCR_LEFT);
}

void scr_burst(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  oled_row line = { "TX " };
  oled_put_uint(&line, v->last_seq);
  oled_put(&line, " SF");
  oled_put_uint(&line, v->sf);
  oled_put(&line, " BW");
  oled_put_uint(&line, v->bw_khz_div125 * 125U);
  scr_header(s, line.s);
  int shift = (int)(frame * CHIRP_STEP % CHIRP_W);
  for (int n = 0; n < 5; n++)
  {
    int x0 = n * CHIRP_W - shift;
    oled_line(s, x0, 30, x0 + CHIRP_W - 1, 11, 0);
    oled_line(s, x0 + CHIRP_W - 1, 11, x0 + CHIRP_W - 1, 30, 1);
  }
  if (frame >= BURST_HEX_FRAME && v->cipher_len != 0)
    for (unsigned r = 0; r < 2U; r++) hex_row(s, 35 + 9 * (int)r, v, (frame - BURST_HEX_FRAME + r) * HEX_PER_ROW);
  oled_line(s, 0, 53, OLED_W - 1, 53, 2);
  oled_row foot = { "AES-CCM " };
  oled_put_uint(&foot, v->cipher_len);
  oled_put(&foot, "B ");
  oled_put_dec(&foot, (int32_t)v->freq_khz, 3, 1, 0);
  oled_put(&foot, "MHz");
  scr_label(s, 56, foot.s, SCR_LEFT);
}

void scr_scope(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  (void)frame;
  const wind_live_t *w = &v->wind;
  scr_series d = scr_series_u8(w->bins, w->nbins, WIND_LIVE_BINS);
  unsigned n = d.n, recent = n < SCOPE_RATE_BINS ? n : SCOPE_RATE_BINS;
  uint32_t sum = (uint32_t)scr_sum_last(&d, SCOPE_RATE_BINS);
  oled_row line = { "SCOPE CUPS" };
  oled_pad_to(&line, 13);
  oled_put_dec(&line, (int32_t)(recent ? sum * 40U / recent : 0U), 1, 1, 0);   /* pulses over recent / 4 s, in 0.1 Hz */
  oled_put(&line, "Hz");
  scr_label(s, 0, line.s, SCR_LEFT);
  oled_box(s, 0, 9, OLED_W, 46);
  oled_dotgrid(s, PLOT_X, PLOT_TOP, PLOT_RIGHT, 44, 16);
  int32_t most = scr_max(&d), full = most > SCOPE_MIN_FULL ? most : SCOPE_MIN_FULL;
  scr_trace(s, PLOT_X, PLOT_TOP, PLOT_RIGHT - PLOT_X + 1, PLOT_BOTTOM - PLOT_TOP + 1, &d, 0, full, d.cap);
  oled_row foot = { "" };
  oled_put_dec(&foot, w->speed_cms, 2, 1, 0);
  oled_put(&foot, "m/s  G");
  oled_put_dec(&foot, w->gust_cms, 2, 1, 0);
  oled_put(&foot, "  ");
  oled_put_uint(&foot, n / 4U);
  oled_put(&foot, "s");
  scr_label(s, 57, foot.s, SCR_LEFT);
}

static void vane_text(const oled_surf *s, int point, const scr_view_t *v)
{
  oled_row line = { "-" };
  if (point >= 0) { line.s[0] = '\0'; oled_put(&line, scr_point_names[point]); oled_put(&line, " "); oled_put_uint(&line, (unsigned)point * 45U / 2U); }
  (void)oled_text(s, VANE_TEXT_X, 4, "VANE", 1);
  (void)oled_text(s, VANE_TEXT_X, 16, line.s, 1);
  oled_row mv = { "" };
  oled_put_uint(&mv, v->wind.vane_mv);
  oled_put(&mv, "mV");
  (void)oled_text(s, VANE_TEXT_X, 32, mv.s, 1);
  (void)oled_text(s, VANE_TEXT_X, 44, "16 POS", 1);
  (void)oled_text(s, VANE_TEXT_X, 56, point >= 0 ? "OK" : "NO POINT", 1);
}

void scr_vane(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  int point = v->wind.point >= 0 && v->wind.point < 16 ? v->wind.point : -1;
  oled_blit(s, scr_art_rose.x, scr_art_rose.y, &scr_art_rose.bits);
  (void)oled_text(s, ROSE_CX - 2, 1, "N", 1);
  if (point >= 0)
  {
    int shown = frame < (unsigned)point ? (int)frame : point;   /* swinging round from N */
    scr_ray(s, ROSE_CX, ROSE_CY, 0, 20, shown, 0);
  }
  oled_fill(s, ROSE_CX - 1, ROSE_CY - 1, 3, 3, 1);
  vane_text(s, point, v);
}

void scr_system(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  static const char *const names[5] = { "FLASH", "RAM", "STACK", "JRNL", "AIR" };
  const uint8_t pct[5] = { v->flash_pct, v->ram_pct, v->stack_pct, v->journal_pct, v->airtime_pct };
  oled_row line = { "SYS  WS-NODE  ID " };
  oled_put_uint(&line, v->station);
  scr_header(s, line.s);
  for (unsigned i = 0; i < 5U; i++)
  {
    int y = 11 + 10 * (int)i;
    unsigned p = pct[i] > 100U ? 100U : pct[i];
    oled_row num = { "" };
    oled_put_uint(&num, p);
    scr_label(s, y, names[i], SCR_LEFT);
    oled_box(s, BAR_X, y, BAR_W, 7);   /* a boxed gauge, filled 3 rows tall inside a 2-pixel margin */
    oled_fill(s, BAR_X + 2, y + 2, (int)scr_grow(BAR_FILL_W * p / 100U, frame, SCR_GROW_FRAMES), 3, 1);
    (void)oled_text(s, 110, y, num.s, 1);
  }
}

static void boot_text(const oled_surf *s, const scr_view_t *v)
{
  oled_row link = { "LINK " };
  oled_put_dec(&link, (int32_t)v->freq_khz, 3, 1, 0);
  oled_put(&link, " SF");
  oled_put_uint(&link, v->sf);
  oled_row key = { "" };
  oled_put(&key, v->key_ok ? "KEY OK  EPOCH " : "NO KEY  EPOCH ");
  oled_put_uint(&key, v->epoch);
  (void)oled_text(s, 10, 6, "WS-NODE  BOOT", 1);
  (void)oled_text(s, 10, 18, link.s, 1);
  (void)oled_text(s, 10, 30, key.s, 1);
  (void)oled_text(s, 10, 42, "MODULES ...", 1);
}

void scr_boot(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  static const int8_t sliced[5] = { 8, 9, 20, 21, 33 };
  boot_text(s, v);
  if (frame == 28U || frame == 29U || frame >= 60U)
  {
    scr_glitch(s, sliced, 5, 0, 5, 27, 3);
  }
  oled_line(s, 0, 62, (int)(frame * (OLED_W - 1U) / 63U), 62, 0);
}

/* The checklist: the ports in two columns of four, each with its mark; the header counts the ports with a
   module that are active; the footer says how the wait stands. A port waiting shows dots that scan. */
static const char *const port_names[SCR_PORTS] = { "AIR", "PRES", "UVA", "ENCL", "BATT", "WIND", "RAIN", "RAIL" };

static void port_row(const oled_surf *s, unsigned i, unsigned frame, unsigned mark)
{
  static const char *const marks[] = { "", "OK", "NONE", "FAULT" };
  static const char *const dots[4] = { ".", "..", "...", "" };
  int x = i < 4U ? 1 : 67, y = 11 + 10 * (int)(i % 4U);
  oled_surf g = *s;
  (void)oled_text(s, x, y, port_names[i], 1);
  const char *m = mark == SCR_PORT_WAIT ? dots[(frame / 2U + i) % 4U] : marks[mark < 4U ? mark : 0U];
  g.ink = mark == SCR_PORT_ABSENT ? CHECK_DIM : mark == SCR_PORT_WAIT ? CHECK_WAIT_INK : OLED_FULL;
  if (mark == SCR_PORT_FAULT && frame % 8U >= 6U) return;   /* a fault blinks */
  (void)oled_text(&g, x + 60 - oled_text_w(m, &font5x7, &oled_x1), y, m, 1);
}

/* The checklist's footer: the ports still waiting, then how the wait ended (a fault named, else all well). */
static void check_foot(const oled_surf *s, unsigned check, unsigned waiting, unsigned faults)
{
  oled_row foot = { "" };
  if (check == SCR_CHECK_WAIT || (check == SCR_CHECK_TIMEOUT && waiting != 0U))
  {
    oled_put(&foot, check == SCR_CHECK_WAIT ? "SCANNING  " : "TIMEOUT  ");
    oled_put_uint(&foot, waiting);
    oled_put(&foot, " PENDING");
  }
  else if (faults != 0U)
  {
    oled_put(&foot, "ATTENTION  ");
    oled_put_uint(&foot, faults);
    oled_put(&foot, faults == 1U ? " FAULT" : " FAULTS");
  }
  else oled_put(&foot, "ALL MODULES NOMINAL");
  oled_line(s, 0, 52, OLED_W - 1, 52, 2);
  scr_label(s, 56, foot.s, SCR_CENTRE);
}

void scr_modules(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  unsigned ok = 0, fitted = 0, waiting = 0, faults = 0;
  for (unsigned i = 0; i < SCR_PORTS; i++)
  {
    unsigned m = v->port_mark[i];
    ok += m == SCR_PORT_OK;
    fitted += m != SCR_PORT_ABSENT;
    waiting += m == SCR_PORT_WAIT;
    faults += m == SCR_PORT_FAULT;
    port_row(s, i, frame, m);
  }
  oled_row head = { "" };
  oled_row count = { "" };
  oled_put_uint(&count, ok);
  oled_put(&count, "/");
  oled_put_uint(&count, fitted);
  (void)oled_put_lr(&head, "MODULE SCAN", count.s, OLED_COLS);
  scr_header(s, head.s);
  check_foot(s, v->check, waiting, faults);
}

/* The 5x7 at x2, each glyph 9 pixels wide (its last column overlapping the one before) on a 10-pixel
   pitch: PLANET fits the 62 pixels beside the face. */
static const uint8_t squeezed_x[FONT5X7_W] = { 0, 2, 4, 6, 7 };
static const oled_style squeezed = { 2, 2, PLANET_PITCH, squeezed_x };

static void face_eye(const oled_surf *s, int wink, int glint)
{
  if (wink)
  {
    oled_line(s, FACE_CX - 15, FACE_CY - 8, FACE_CX - 7, FACE_CY - 8, 0);
    oled_line(s, FACE_CX - 15, FACE_CY - 7, FACE_CX - 7, FACE_CY - 7, 0);
  }
  else oled_disc_r2(s, FACE_CX - 11, FACE_CY - 8, 4, 16, 1);   /* the mockup's eye: r^2, not oled_disc's r^2 + r */
  if (glint)
  {
    oled_set(s, FACE_CX + 8, FACE_CY - 11, 0);
    oled_set(s, FACE_CX + 9, FACE_CY - 11, 0);
    oled_set(s, FACE_CX + 8, FACE_CY - 10, 0);
  }
}

/* Frame 20 is the mockup's glitch; 21-23 slice other rows the other way. */
static void hack_glitch(const oled_surf *s, unsigned g)
{
  static const int8_t sliced[5] = { 8, 9, 30, 31, 50 };
  static const struct { int8_t dy, dx, band; } step[4] = { { 0, 4, 36 }, { 6, -3, 22 }, { 3, 5, 46 }, { -4, -6, 28 } };
  scr_glitch(s, sliced, 5, step[g].dy, step[g].dx, step[g].band, 2);
}

void scr_hack(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  (void)v;
  oled_blit(s, scr_art_face.x, scr_art_face.y, &scr_art_face.bits);
  face_eye(s, frame == 16U || frame == 17U, frame == 18U || frame == 19U);
  (void)oled_text(s, 68, 2, "HACK", 2);
  if (frame >= 4U) (void)oled_text(s, 74, 21, "THE", 2);
  if (frame >= 8U) (void)oled_draw_text(s, 64, 42, "PLANET", &font5x7, &squeezed);
  if (frame >= 20U && frame < 24U) hack_glitch(s, frame - 20U);
}
