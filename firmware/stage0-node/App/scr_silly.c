/* The silly interludes (scr_view.h), original art drawn from the readings:
 *   fortune  a fortune cookie cracks open; its slip types out the line scr_fortune_pick chose from the
 *            weather and the link, three characters a frame; lucky numbers from the readings.
 *   frog     the pocket frog (scr_art_frog) on its lily pad, its mood from the weather (scr_frog_mood):
 *            the mouth, sleepy eyes, rain, frost shivers, sweat, wind streaks. It blinks at frames 20-21
 *            and 52, its eyes follow the fly (the last frame sent), and from frame 40 the tongue catches
 *            the fly if that frame was ACKed (a hop, "ACK! yum") or the fly gets away ("no ACK").
 *   matrix   digital rain: a falling stream of glyphs a column, their heads inverted, the speed
 *            scr_matrix_speed of the tips in the last 10 minutes; the tips and the speed in the footer.
 *   pinball  the frame sent, a small envelope, bounces round the table at a speed and heading the
 *            sequence picks, through the ACK bumper at frame 32; passing the ACK bumper lights it for 3 frames (100 points), the side bumpers score 10; the
 *            flippers kick when it is low on their side. */
#include "scr_view.h"
#include <string.h>
#include "font5x7.h"
#include "oled_draw.h"

#define FORTUNE_ROWS 3U
#define FORTUNE_CPF 3U                 /* characters typed a frame */
#define FROG_EYE_L 22                  /* tools/make_scr_art.py: FROG_CX -+ 10, FROG_CY - 12 */
#define FROG_EYE_R 42
#define FROG_EYE_Y 32
#define FROG_MOUTH_X 32
#define FROG_MOUTH_Y 39
#define FROG_TEXT_X 68
#define FROG_CATCH 40U                 /* the frame the tongue goes out */
#define MATRIX_COLS 21
#define MATRIX_GLYPHS "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#define BALL_X_LO 5
#define BALL_X_HI 122
#define BALL_Y_LO 13
#define BALL_Y_HI 58
#define ACK_X 64
#define ACK_Y 34
#define ACK_R 10
#define SIDE_R 4
#define LIT_FRAMES 3
#define PASS_FRAME 32

/* ---- the fortune cookie ---- */

static void cookie(oled_fb *fb, unsigned frame)
{
  int d = frame < 6U ? (int)frame : 6;   /* the halves part */
  oled_disc(fb, 56 - d, 54, 8, 1);
  oled_disc(fb, 59 - d, 50, 6, 0);
  oled_disc(fb, 72 + d, 54, 8, 1);
  oled_disc(fb, 69 + d, 50, 6, 0);
  if (d == 6) oled_line(fb, 56, 47, 72, 47, 0);   /* the slip between them */
}

void scr_fortune(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  const char *s = scr_fortunes[scr_fortune_pick(v)];
  unsigned typed = frame * FORTUNE_CPF, shown = 0;
  oled_box(fb, 0, 0, OLED_W, 31);
  for (unsigned r = 0; r < FORTUNE_ROWS && *s; r++)
  {
    char line[SCR_LINE] = "";
    size_t n = 0;
    /* bound: up to SCR_LINE - 1 characters of one row */
    while (s[n] && s[n] != '\n' && n + 1U < SCR_LINE) n++;
    for (size_t i = 0; i < n && shown < typed; i++, shown++) line[i] = s[i];
    (void)oled_text(fb, 2, 3 + 9 * (int)r, line, 1);
    s += n;
    if (*s == '\n') s++;
  }
  char lucky[SCR_LINE] = "LUCKY ";
  uint32_t nums[3] = { v->last_seq % 100U, (v->air_c < 0 ? 0U - (uint32_t)v->air_c : (uint32_t)v->air_c) / 100U % 100U,
                       (uint32_t)(v->air_rh < 0 ? 0 : v->air_rh) / 100U % 100U };
  for (unsigned i = 0; i < 3U; i++) { scr_put_uint(lucky, nums[i]); scr_put(lucky, " "); }
  scr_row(fb, 36, lucky);
  cookie(fb, frame);
}

/* ---- the frog ---- */

static void fly_at(unsigned frame, int *x, int *y)
{
  *x = 32 + scr_sin20((int)frame) * 26 / 20;
  *y = 12 + scr_sin20((int)frame * 2 + 4) * 6 / 20;
}

static void fly(oled_fb *fb, int x, int y, unsigned frame)
{
  oled_fill(fb, x, y, 2, 2, 1);
  int up = (frame & 1U) ? -1 : 0;   /* the wings beat */
  oled_set(fb, x - 1, y - 1 + up, 1);
  oled_set(fb, x + 2, y - 1 + up, 1);
}

static int sign(int v) { return v > 0 ? 1 : v < 0 ? -1 : 0; }

static void eyes(oled_fb *fb, int dx, int dy, int fx, int fy, int closed)
{
  static const int ex[2] = { FROG_EYE_L, FROG_EYE_R };
  for (unsigned i = 0; i < 2U; i++)
  {
    int x = ex[i] + dx, y = FROG_EYE_Y + dy;
    if (closed) { oled_line(fb, x - 3, y + 1, x + 3, y + 1, 0); continue; }
    oled_disc(fb, x + 2 * sign(fx - x), y + 2 * sign(fy - y), 2, 1);
  }
}

static void mouth(oled_fb *fb, int dx, int dy, enum scr_mood m)
{
  int smile = m == MOOD_HAPPY || m == MOOD_TOASTY || m == MOOD_BREEZY, flat = m == MOOD_SLEEPY;
  int px = 0, py = 0;
  for (int i = -7; i <= 7; i++)
  {
    int bend = flat ? 0 : i * i / 12;
    int x = FROG_MOUTH_X + i + dx, y = FROG_MOUTH_Y + dy + (smile ? 3 - bend : bend);
    if (i > -7) oled_line(fb, px, py, x, y, 0);
    px = x; py = y;
  }
}

static void weather(oled_fb *fb, enum scr_mood m, unsigned frame)
{
  switch (m)
  {
  case MOOD_SOGGY:
    for (unsigned i = 0; i < 6U; i++)
    {
      int x = 4 + 11 * (int)i, y = (int)((frame * 4U + i * 17U) % 60U);
      oled_line(fb, x, y, x - 1, y + 3, 0);
    }
    break;
  case MOOD_SLEEPY:
    for (unsigned i = 0; i < 3U; i++)
      (void)oled_text(fb, 48 + 5 * (int)i, 20 - (int)((frame / 4U + i * 3U) % 10U) - 4 * (int)i, "z", 1);
    break;
  case MOOD_TOASTY:
    oled_line(fb, 52, 27 + (int)(frame / 2U % 4U), 52, 29 + (int)(frame / 2U % 4U), 0);   /* a sweat drop */
    break;
  case MOOD_BREEZY:
    for (int i = 0; i < 2; i++) oled_line(fb, -(int)(frame * 3U % 12U), 6 + 8 * i, 60, 6 + 8 * i, 6);
    break;
  default: break;
  }
}

void scr_frog(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  static const int8_t hop[8] = { 0, -2, -4, -5, -5, -4, -2, 0 };
  enum scr_mood m = scr_frog_mood(v);
  int acked = v->last_acked == SCR_TX_ACK, caught = acked && frame >= FROG_CATCH + 2U;
  int dx = m == MOOD_CHILLY ? (int)(frame & 1U) : 0;   /* shivering */
  int dy = caught && frame < FROG_CATCH + 10U ? hop[frame - FROG_CATCH - 2U] : 0;
  int fx, fy;
  fly_at(frame, &fx, &fy);
  if (!acked && frame >= FROG_CATCH) fx += (int)(frame - FROG_CATCH) * 4;   /* away */
  scr_blit(fb, &scr_art_frog, dx, dy);
  int blink = frame == 20U || frame == 21U || frame == 52U;
  eyes(fb, dx, dy, fx, fy, blink || m == MOOD_SLEEPY);
  mouth(fb, dx, dy, m);
  if (acked && (frame == FROG_CATCH || frame == FROG_CATCH + 1U))
    oled_line(fb, FROG_MOUTH_X, FROG_MOUTH_Y + 1, fx, fy, 0);   /* the tongue */
  if (!caught) fly(fb, fx, fy, frame);
  weather(fb, m, frame);
  char line[SCR_LINE] = "is ";
  scr_put(line, scr_mood_names[m]);
  (void)oled_text(fb, FROG_TEXT_X, 4, "FROG", 1);
  (void)oled_text(fb, FROG_TEXT_X, 14, line, 1);
  line[0] = '\0';
  if (v->air_ok) { scr_put_dec(line, v->air_c, 2, 1, 0); scr_put(line, "C "); scr_put_dec(line, v->air_rh, 2, 0, 0); scr_put(line, "%"); }
  (void)oled_text(fb, FROG_TEXT_X, 28, line, 1);
  const char *said = frame < FROG_CATCH ? "watching" : caught ? "ACK! yum" : acked ? "..." : "no ACK";
  (void)oled_text(fb, FROG_TEXT_X, 50, said, 1);
}

/* ---- the digital rain ---- */

void scr_matrix(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  unsigned tips = scr_rain_tips(v->rain.per_min, RAIN_HIST_MINUTES, SCR_RAIN_RECENT_MIN), speed = scr_matrix_speed(tips);
  const unsigned nglyphs = sizeof MATRIX_GLYPHS - 1U;
  for (unsigned c = 0; c < MATRIX_COLS; c++)
  {
    unsigned len = 3U + scr_hash(c, 1) % 5U, period = OLED_H + len * 8U + 8U;
    unsigned fall = (1U + scr_hash(c, 2) % 2U) * speed;
    int head = (int)((scr_hash(c, 3) % period + frame * fall) % period) - 8;
    int x = (int)c * OLED_CHAR_ADVANCE + 1;
    for (unsigned k = 0; k < len; k++)
    {
      int y = head - 8 * (int)k;
      if (y < -7 || y >= OLED_H - 8) continue;
      char g[2] = { MATRIX_GLYPHS[scr_hash(c * 97U + (unsigned)(y + 8) / 8U, frame / 3U + k) % nglyphs], '\0' };
      (void)oled_text(fb, x, y, g, 1);
      if (k == 0U) oled_invert(fb, x - 1, y - 1, 7, 9);   /* the head */
    }
  }
  char line[SCR_LINE] = "TIPS ";
  scr_put_uint(line, tips);
  scr_put(line, "/10m");
  scr_pad_to(line, 13);
  scr_put(line, "SPEED x");
  scr_put_uint(line, speed);
  oled_fill(fb, 0, OLED_H - 8, OLED_W, 8, 0);
  scr_row(fb, OLED_H - 8, line);
  oled_invert(fb, 0, OLED_H - 8, OLED_W, 8);
}

/* ---- the packet pinball ---- */

static int bounce(int p, int lo, int hi)
{
  int span = hi - lo, m = (p - lo) % (2 * span);
  if (m < 0) m += 2 * span;
  return lo + (m < span ? m : 2 * span - m);
}

/* The ball crosses the ACK bumper's centre at PASS_FRAME, its speed and heading from the sequence. */
static void ball_at(const scr_view_t *v, unsigned t, int *x, int *y)
{
  uint32_t h = scr_hash(v->last_seq, 7);
  int vx = (int)(2U + h % 2U) * ((h & 4U) ? -1 : 1), vy = (h & 8U) ? 3 : -3, dt = (int)t - PASS_FRAME;
  *x = bounce(ACK_X + vx * dt, BALL_X_LO, BALL_X_HI);
  *y = bounce(ACK_Y + vy * dt, BALL_Y_LO, BALL_Y_HI);
}

static int near(int x, int y, int cx, int cy, int r) { return (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r; }

/* What the ball touches at frame t: bit 0 the ACK bumper, bit 1 a side one. */
static unsigned touches(const scr_view_t *v, unsigned t)
{
  int x, y;
  ball_at(v, t, &x, &y);
  unsigned hit = near(x, y, ACK_X, ACK_Y, ACK_R + 3) ? 1U : 0U;
  if (near(x, y, 30, 24, SIDE_R + 3) || near(x, y, 98, 24, SIDE_R + 3)) hit |= 2U;
  return hit;
}

static void flipper(oled_fb *fb, int side, int up)
{
  int x0 = side < 0 ? 34 : 93, x1 = side < 0 ? 54 : 73;
  oled_line(fb, x0, 58, x1, up ? 53 : 61, 0);
  oled_line(fb, x0, 59, x1, up ? 54 : 62, 0);
}

void scr_pinball(oled_fb *fb, unsigned frame, const scr_view_t *v)
{
  unsigned score = 0, prev = 0, lit = 0;
  for (unsigned t = 0; t <= frame; t++)   /* frame < 64: scr_draw caps it */
  {
    unsigned h = touches(v, t);
    if ((h & 1U) && !(prev & 1U)) score += 100U;
    if ((h & 2U) && !(prev & 2U)) score += 10U;
    if (h & 1U) lit = LIT_FRAMES;
    else if (lit) lit--;
    prev = h;
  }
  char line[SCR_LINE] = "", num[SCR_LINE] = "SCORE ";
  scr_put_uint(num, score);
  (void)scr_put_lr(line, "PINBALL", num);
  scr_header(fb, line);
  oled_box(fb, 0, 9, OLED_W, OLED_H - 9);
  oled_circle(fb, 30, 24, SIDE_R);
  oled_circle(fb, 98, 24, SIDE_R);
  oled_circle(fb, ACK_X, ACK_Y, ACK_R);
  (void)oled_text(fb, ACK_X - 8, ACK_Y - 3, "ACK", 1);
  if (lit)
  {
    oled_disc(fb, ACK_X, ACK_Y, ACK_R - 1, 1);
    (void)oled_text(fb, ACK_X - 8, ACK_Y - 3, "ACK", 1);
    oled_invert(fb, ACK_X - 8, ACK_Y - 3, 17, 7);
    for (int p = 0; p < 16; p += 2)
      oled_line(fb, ACK_X + scr_sin20(p) * 13 / 20, ACK_Y - scr_sin20(p + 4) * 13 / 20, ACK_X + scr_sin20(p) * 16 / 20,
                ACK_Y - scr_sin20(p + 4) * 16 / 20, 0);
  }
  int x, y;
  ball_at(v, frame, &x, &y);
  flipper(fb, -1, y > 46 && x < 64);
  flipper(fb, 1, y > 46 && x >= 64);
  oled_fill(fb, x - 3, y - 2, 7, 5, 0);   /* the envelope: dark inside, its flap */
  oled_box(fb, x - 3, y - 2, 7, 5);
  oled_line(fb, x - 3, y - 2, x, y, 0);
  oled_line(fb, x + 3, y - 2, x, y, 0);
}
