/* The bench screens' scheduler (App/scr_sched.h). One screen at a time, and its frame: each step
 * shows the current frame, then moves on, so an event that changes the screen takes effect at the
 * next step and never inside a frame. A screen is up as a base screen (HOME and the detail screens: its
 * 15 s, redrawn as sched_anim and sched_every say) or as a play (an interlude, a packet or boot screen:
 * scr_frames(id) frames, each drawn). */
#include "scr_sched.h"

#define INTERLUDE_EVERY_MS 120000U   /* one interlude about every 2 minutes (design, "The interludes") */

static const enum scr_id details[] = { SCR_AIR, SCR_PRESSURE, SCR_POWER, SCR_RADIO, SCR_SCOPE, SCR_VANE, SCR_RAIN,
                                       SCR_SYSTEM };
static const enum scr_id interludes[] = { SCR_FORTUNE, SCR_SCOPE, SCR_FROG, SCR_VANE, SCR_MATRIX, SCR_RAIN, SCR_PINBALL,
                                          SCR_SYSTEM, SCR_HACK };
static const enum scr_id b1_order[] = { SCR_HOME, SCR_AIR, SCR_PRESSURE, SCR_POWER, SCR_RADIO, SCR_SCOPE, SCR_VANE,
                                        SCR_RAIN, SCR_SYSTEM, SCR_FORTUNE, SCR_FROG, SCR_MATRIX, SCR_PINBALL, SCR_HACK };
#define N_OF(a) (sizeof (a) / sizeof (a)[0])

static enum scr_id cur;
static unsigned frame;           /* of cur, the next to show */
static unsigned steps;           /* cur's length: its dwell or its frames */
static int base;                 /* cur is up as a base screen */
static int redraw;               /* the link changed (an ACK, a NO ACK) or B3 on: draw a base screen at the next step */
static uint32_t interlude_at;    /* when the next interlude falls due (clock_ms) */
static unsigned next_interlude;  /* index into interludes */
static unsigned next_detail;     /* index into details */
static unsigned extras;          /* frames sent after the live one */
static int paused;               /* B2: no base cycle, no interludes (packets still show) */
static enum scr_id held;         /* while paused: the screen that stays (one of b1_order) */
static int on;                   /* B3: the display is on */

static int reached(uint32_t now_ms, uint32_t at_ms) { return (int32_t)(now_ms - at_ms) >= 0; }

static int in_list(enum scr_id id, const enum scr_id *list, unsigned n)
{
  for (unsigned i = 0; i < n; i++)
    if (list[i] == id) return 1;
  return 0;
}

static int is_base(enum scr_id id) { return (scr_def_of(id)->flags & SCR_F_BASE) != 0U; }

static void play(enum scr_id id) { cur = id; frame = 0; base = 0; steps = scr_frames(id); }

static void dwell(enum scr_id id) { cur = id; frame = 0; base = 1; steps = SCHED_DWELL_STEPS; }

/* A screen B1 picks (or a held one): a base screen dwells, the others play. */
static void pick(enum scr_id id)
{
  if (is_base(id)) dwell(id);
  else play(id);
}

unsigned sched_anim(enum scr_id id) { return scr_def_of(id)->anim; }

unsigned sched_every(enum scr_id id) { return scr_def_of(id)->every; }

void sched_init(uint32_t now_ms)
{
  play(SCR_BOOT);
  redraw = 0;
  interlude_at = now_ms + INTERLUDE_EVERY_MS;
  next_interlude = 0;
  next_detail = 0;
  extras = 0;
  paused = 0;
  held = SCR_HOME;
  on = 1;
}

/* B1: the screen after id in b1_order, round to HOME. A packet or boot screen has no place in it: B1 skips
   to HOME. */
static enum scr_id next_screen(enum scr_id id)
{
  for (unsigned i = 0; i < N_OF(b1_order); i++)
    if (b1_order[i] == id) return b1_order[(i + 1U) % N_OF(b1_order)];
  return SCR_HOME;
}

void sched_event(enum sched_ev e, uint32_t now_ms)
{
  switch (e)
  {
    case EV_SENT_LIVE: play(SCR_BURST); extras = 0; break;   /* preempts whatever is on */
    case EV_SENT_EXTRA: if (extras < UINT16_MAX) extras++; break;
    case EV_ACK: case EV_NO_ACK: redraw = 1; break;   /* the link line and the banner show the outcome */
    case EV_B1:   /* paused: the held screen moves on, from the held one (a packet screen up or not) */
      if (!on) break;
      if (paused) { held = next_screen(held); pick(held); }
      else pick(next_screen(cur));
      break;
    case EV_B2:
      if (!on) break;
      paused = !paused;
      if (paused) held = in_list(cur, b1_order, N_OF(b1_order)) ? cur : SCR_HOME;   /* a packet or boot one ends first */
      else interlude_at = now_ms + INTERLUDE_EVERY_MS;      /* resumes a full period from now */
      break;
    case EV_B3:
      on = !on;
      if (on) redraw = 1;   /* the panel was dark: the screen comes back at its next step */
      break;
    default: break;
  }
}

/* What follows cur's end. While paused the held screen comes back (from its frame 0) after the banner and
   after itself. */
static void after(void)
{
  if (cur == SCR_BOOT) { play(SCR_HACK); return; }
  if (cur == SCR_BURST) { play(SCR_BANNER); return; }
  if (paused) { pick(held); return; }
  if (cur == SCR_HOME && base)
  {
    dwell(details[next_detail]);
    next_detail = (next_detail + 1U) % N_OF(details);
    return;
  }
  dwell(SCR_HOME);   /* after HACK, the banner, every interlude and every detail screen */
}

int sched_step(uint32_t now_ms, enum scr_id *id, unsigned *out_frame, int *display_on)
{
  *display_on = on;
  if (cur == SCR_HOME && !paused && reached(now_ms, interlude_at))
  {
    play(interludes[next_interlude]);
    next_interlude = (next_interlude + 1U) % N_OF(interludes);
    interlude_at += INTERLUDE_EVERY_MS;   /* a fixed phase: the wait for HOME does not drift it */
    if (reached(now_ms, interlude_at)) interlude_at = now_ms + INTERLUDE_EVERY_MS;   /* far behind: no burst of them */
  }
  *id = cur;
  *out_frame = frame;
  int draw = 1;
  if (base)
  {
    draw = frame < sched_anim(cur) || frame % sched_every(cur) == 0U || redraw;
    redraw = 0;
  }
  if (++frame >= steps) after();
  return draw;
}

unsigned sched_extras(void) { return extras; }

int sched_display_on(void) { return on; }
