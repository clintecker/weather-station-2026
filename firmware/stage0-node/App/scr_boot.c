/* The boot: the LGTM SYSTEMS splash, then the module checklist (see scr_screens.h; design spec, "The
 * interludes", 5). Original art: the emblem is a diamond with a check through it on a horizon of rules, the
 * wordmark its own lettering (scr_mark.h). Gray levels (each part on a copy of the surface with its own ink)
 * give the glow and the fades. BOOT's 72 frames, 9 s:
 *   0-5    the tube warms up: a dot, a line across, a band of scanlines that fades.
 *   6-17   the emblem: its outline traced an edge a frame, the check, the rules running out; a ring of glow
 *          spreads behind it.
 *   18-29  L, G, T, M, one every 3 frames, each flashing in gray first, in a dim halo; a faint scan line
 *          sweeps down over them.
 *   30-45  SYSTEMS letterspaced fades in between two rules, then LOOKS GOOD TO ME types out, 2 a frame.
 *   46-49  a glitch: rows sliced and a band inverted.
 *   50-71  the terminal: the station, the link, the key, the epoch and the firmware, a row every 3
 *          frames (labels gray, leaders dim, values bright), then "> MODULE SCAN" and a blinking cursor.
 *   modules the checklist that follows: each local port and its mark (scanning dots, OK, a dim NONE, a
 *          blinking FAULT), the active ports of those with a module, and how the wait stands. */
#include "scr_screens.h"
#include "font5x7.h"
#include "scr_mark.h"

#define EMBLEM_AT 6U                   /* the frames each part starts at */
#define WORD_AT 18U
#define SYSTEMS_AT 30U
#define TAG_AT 38U
#define GLITCH_AT 46U
#define TERM_AT 50U
#define CX 64                          /* the emblem's centre */
#define CY 13
#define MARK_X 21                      /* the wordmark: 4 letters on a 24-pixel pitch, 86 wide */
#define MARK_Y 30
#define MARK_PITCH 24
#define LETTER_EVERY 3U
#define TERM_ROWS 5U
#define TERM_EVERY 3U                  /* a terminal row typed in 3 frames, 7 characters a frame */
#define CHECK_DIM 4U                   /* the checklist: a port with no module, dim */
#define CHECK_WAIT_INK 8U              /* and one still waiting */

static const oled_style mark_style = { 1, 1, MARK_PITCH, NULL };
static const oled_style systems_style = { 1, 1, 10, NULL };

/* s with its own ink (1..15). */
static oled_surf inked(const oled_surf *s, unsigned ink)
{
  oled_surf g = *s;
  g.ink = (uint8_t)(ink < 1U ? 1U : ink > OLED_FULL ? OLED_FULL : ink);
  return g;
}

/* A fade in: level 1 at frame `from`, `top` from frames later on. */
static unsigned ramp(unsigned frame, unsigned from, unsigned frames, unsigned top)
{
  unsigned k = frame - from + 1U;
  return k >= frames ? top : 1U + (top - 1U) * k / frames;
}

/* The tube warming up, frames 0-5: the half width and half height of the lit band, and its level. Every
   other row of the band is a third as bright: scanlines. */
static void crt(const oled_surf *s, unsigned f)
{
  static const uint8_t half_w[6] = { 1, 16, 48, 64, 64, 64 }, half_h[6] = { 0, 0, 0, 0, 3, 12 };
  static const uint8_t level[6] = { 15, 15, 15, 15, 8, 3 };
  for (int y = 31 - half_h[f]; y <= 32 + half_h[f]; y++)
  {
    oled_surf g = inked(s, (y & 1) ? level[f] / 3U : level[f]);
    oled_line(&g, CX - half_w[f], y, CX + half_w[f] - 1, y, 0);
  }
  oled_surf glow = inked(s, 3);
  oled_line(&glow, CX - half_w[f] / 2, 30 - half_h[f], CX + half_w[f] / 2, 30 - half_h[f], 0);
  oled_line(&glow, CX - half_w[f] / 2, 33 + half_h[f], CX + half_w[f] / 2, 33 + half_h[f], 0);
}

/* The diamond's outline, radius r, its first `edges` edges (clockwise from the top). */
static void diamond(const oled_surf *s, int r, unsigned edges)
{
  static const int8_t dx[5] = { 0, 1, 0, -1, 0 }, dy[5] = { -1, 0, 1, 0, -1 };
  for (unsigned i = 0; i < edges && i < 4U; i++)
    oled_line(s, CX + dx[i] * r, CY + dy[i] * r, CX + dx[i + 1U] * r, CY + dy[i + 1U] * r, 0);
}

/* The horizon: a bright rule out from each side of the diamond, a dim one under it, ticks at their ends. */
static void rules(const oled_surf *s, unsigned f, unsigned ink)
{
  int len = (int)scr_grow(44, f - (EMBLEM_AT + 6U), 6), under = len * 2 / 3;
  oled_surf g = inked(s, ink), dim = inked(s, ink / 3U);
  oled_line(&g, CX - 13, CY, CX - 13 - len, CY, 0);
  oled_line(&g, CX + 13, CY, CX + 13 + len, CY, 0);
  oled_line(&dim, CX - 16, CY + 3, CX - 16 - under, CY + 3, 2);
  oled_line(&dim, CX + 16, CY + 3, CX + 16 + under, CY + 3, 2);
  oled_line(&g, CX - 13 - len, CY - 2, CX - 13 - len, CY + 2, 0);
  oled_line(&g, CX + 13 + len, CY - 2, CX + 13 + len, CY + 2, 0);
}

/* The emblem from frame 6: the ring of glow spreading (to frame 17), the outline traced, the check, the rules;
   the inner outline breathes once it is all there. */
static void emblem(const oled_surf *s, unsigned f)
{
  if (f < EMBLEM_AT) return;
  unsigned ink = ramp(f, EMBLEM_AT, 6, OLED_FULL);
  if (f < WORD_AT)
  {
    oled_surf ring = inked(s, f < 14U ? 3U : 2U);
    oled_circle(&ring, CX, CY, 12 + 6 * (int)(f - EMBLEM_AT));
  }
  oled_surf g = inked(s, ink), inner = inked(s, (unsigned)scr_tri((int)f, 3, 7));
  diamond(&g, 12, f - EMBLEM_AT + 1U);
  if (f >= EMBLEM_AT + 4U) diamond(&inner, 9, 4);
  if (f >= EMBLEM_AT + 5U) for (int t = 0; t < 2; t++) oled_line(&g, CX - 6, CY + t, CX - 2, CY + 4 + t, 0);
  if (f >= EMBLEM_AT + 6U)
  {
    for (int t = 0; t < 2; t++) oled_line(&g, CX - 2, CY + 4 + t, CX + 6, CY - 5 + t, 0);
    rules(s, f, ink);
  }
}

/* The wordmark from frame 18: a letter every 3 frames, the newest in gray for its first frame, all in a dim
   halo; a faint line sweeps down over them until it is all there. */
static void wordmark(const oled_surf *s, unsigned f)
{
  static const char word[] = "LGTM";
  if (f < WORD_AT) return;
  unsigned n = (f - WORD_AT) / LETTER_EVERY + 1U;
  oled_row shown = { "" };
  oled_put(&shown, word);
  if (n < 4U) shown.s[n] = '\0'; else n = 4U;
  if (f < SYSTEMS_AT)
  {
    oled_surf sweep = inked(s, 4);
    int y = MARK_Y - 2 + (int)((f - WORD_AT) * 16U / 12U);
    oled_line(&sweep, MARK_X - 6, y, MARK_X + 3 * MARK_PITCH + SCR_MARK_W + 5, y, 0);
  }
  oled_surf halo = inked(s, 2), g = inked(s, OLED_FULL);
  static const int8_t ox[4] = { -1, 1, 0, 0 }, oy[4] = { 0, 0, -1, 1 };
  for (unsigned i = 0; i < 4U; i++) (void)oled_draw_text(&halo, MARK_X + ox[i], MARK_Y + oy[i], shown.s, &scr_mark, &mark_style);
  (void)oled_draw_text(&g, MARK_X, MARK_Y, shown.s, &scr_mark, &mark_style);
  if ((f - WORD_AT) % LETTER_EVERY == 0U && f < SYSTEMS_AT)
  {
    oled_surf fresh = inked(s, 7);
    char one[2] = { word[n - 1U], '\0' };
    (void)oled_draw_text(&fresh, MARK_X + MARK_PITCH * (int)(n - 1U), MARK_Y, one, &scr_mark, &mark_style);
  }
}

/* SYSTEMS fading in between two rules from frame 30, then the tagline typed from frame 38, 2 a frame, a
   cursor blinking at its end. */
static void subtitle(const oled_surf *s, unsigned f)
{
  static const char tag[] = "LOOKS GOOD TO ME";
  if (f < SYSTEMS_AT) return;
  unsigned ink = ramp(f, SYSTEMS_AT, 8, 12);
  oled_surf g = inked(s, ink), rule = inked(s, ink / 2U);
  (void)oled_draw_text(&g, 32, 46, "SYSTEMS", &font5x7, &systems_style);
  oled_line(&rule, 8, 49, 27, 49, 0);
  oled_line(&rule, 100, 49, 119, 49, 0);
  if (f < TAG_AT) return;
  unsigned n = (f - TAG_AT) * 2U + 2U;
  oled_row typed = { "" };
  oled_put(&typed, tag);
  if (n < sizeof tag - 1U) typed.s[n] = '\0';
  oled_surf t = inked(s, 9);
  int end = oled_text(&t, 16, 56, typed.s, 1);
  if (f % 4U < 2U) oled_fill(&t, end, 56, 5, 7, 1);
}

static unsigned text_len(const char *t)
{
  unsigned n = 0;
  while (t[n] != '\0' && n < OLED_ROW_CAP) n++;   /* bound: OLED_ROW_CAP characters */
  return n;
}

/* A terminal row: the label, dim leader dots, the value ending at the right edge (OLED_COLS); the value is
   never pushed past it (FIRMWARE and its 12 characters fill the row). */
static void leader(oled_row *r, const char *label, const char *value)
{
  unsigned at = OLED_COLS - text_len(value);   /* where the value starts */
  oled_put(r, label);
  oled_put(r, " ");
  for (unsigned c = text_len(label) + 1U; c + 1U < at; c++) oled_put(r, ".");   /* bound: OLED_COLS columns */
  if (text_len(r->s) < at) oled_put(r, " ");
  oled_put(r, value);
}

/* Row text typed up to n characters at x 0, y, in ink. */
static void typed(const oled_surf *s, int y, const char *text, unsigned from, unsigned to, unsigned n, unsigned ink)
{
  oled_row part = { "" };
  for (unsigned c = from; c < to && c < n && text[c]; c++)   /* bound: OLED_ROW_CAP characters */
  {
    char one[2] = { text[c], '\0' };
    oled_put(&part, one);
  }
  oled_surf g = inked(s, ink);
  (void)oled_text(&g, (int)from * OLED_CHAR_ADVANCE, y, part.s, 1);
}

/* Terminal row i, typed from its frame on: the label gray, the leader dim, the value bright. */
static void term_row(const oled_surf *s, unsigned i, unsigned f, const char *label, const char *value)
{
  if (f < TERM_AT + TERM_EVERY * i) return;
  oled_row r = { "" };
  leader(&r, label, value);
  unsigned n = (f - TERM_AT - TERM_EVERY * i + 1U) * 7U, lab = text_len(label), val = OLED_COLS - text_len(value);
  int y = 10 + 9 * (int)i;
  typed(s, y, r.s, 0, lab, n, 8);
  typed(s, y, r.s, lab, val, n, 3);
  typed(s, y, r.s, val, OLED_COLS, n, OLED_FULL);
}

/* The terminal from frame 50: the header, the readouts, the hand-over to the checklist. */
static void terminal(const oled_surf *s, unsigned f, const scr_view_t *v)
{
  oled_row head = { "" }, station = { "" }, link = { "" }, epoch = { "" };
  (void)oled_put_lr(&head, "LGTM SYSTEMS", "WS-NODE", OLED_COLS);
  scr_header(s, head.s);
  oled_put_uint(&station, v->station);
  oled_put_dec(&link, (int32_t)v->freq_khz, 3, 1, 0);
  oled_put(&link, " SF");
  oled_put_uint(&link, v->sf);
  oled_put(&link, " BW");
  oled_put_uint(&link, v->bw_khz_div125 * 125U);
  oled_put_uint(&epoch, v->epoch);
  term_row(s, 0, f, "STATION", station.s);
  term_row(s, 1, f, "LINK", link.s);
  term_row(s, 2, f, "KEY", v->key_ok ? "LOADED" : "MISSING");
  term_row(s, 3, f, "EPOCH", epoch.s);
  term_row(s, 4, f, "FIRMWARE", v->fw[0] ? v->fw : "?");
  if (f < TERM_AT + TERM_EVERY * TERM_ROWS) return;
  int end = oled_text(s, 0, 56, "> MODULE SCAN", 1);
  if (f % 4U < 2U) oled_fill(s, end + 1, 56, 5, 7, 1);
}

void scr_boot(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  static const int8_t sliced[5] = { 31, 32, 38, 39, 47 };
  if (frame >= TERM_AT) { terminal(s, frame, v); return; }
  if (frame < EMBLEM_AT) { crt(s, frame); return; }
  emblem(s, frame);
  wordmark(s, frame);
  subtitle(s, frame);
  if (frame >= GLITCH_AT) scr_glitch(s, sliced, 5, 0, frame % 2U ? -5 : 4, 22 + 5 * (int)(frame - GLITCH_AT), 2);
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

