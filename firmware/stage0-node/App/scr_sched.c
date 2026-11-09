/* The bench screens' scheduler (App/scr_sched.h). One screen at a time, and its frame: each step
 * shows the current frame, then moves on, so an event that changes the screen takes effect at the
 * next step and never inside a frame. A screen is up as a base screen (HOME and the detail screens: its
 * 15 s, redrawn as sched_anim and sched_every say) or as a play (an interlude, a packet or boot screen:
 * scr_frames(id) frames, each drawn; the boot checklist until the modules settle). */
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
static int redraw;               /* the link changed (a packet, an ACK, a NO ACK) or B3 on: draw a base screen at the next step */
static uint32_t interlude_at;    /* when the next interlude falls due (clock_ms) */
static unsigned next_interlude;  /* index into interludes */
static unsigned next_detail;     /* index into details */
static unsigned extras;          /* frames sent after the live one */
static int paused;               /* B2: no base cycle, no interludes, no packet screens */
static enum scr_id held;         /* while paused: the screen that stays (one of b1_order) */
static int on;                   /* B3: the display is on */
static uint32_t boot_ms;         /* sched_init's clock: the checklist's cap counts from it */
static int settled;              /* EV_SETTLED came: every port has its verdict */
static enum scr_check check;     /* how the checklist's wait ended */

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
  boot_ms = now_ms;
  settled = 0;
  check = SCR_CHECK_WAIT;
}

/* B1: the screen after id in b1_order, round to HOME. A packet or boot screen has no place in it: B1 skips
   to HOME. */
static enum scr_id next_screen(enum scr_id id)
{
  for (unsigned i = 0; i < N_OF(b1_order); i++)
    if (b1_order[i] == id) return b1_order[(i + 1U) % N_OF(b1_order)];
  return SCR_HOME;
}

/* The boot splash or its checklist is up. The first latch admits the modules and sends the first packet at
   once: a burst over the checklist would hide the moment it settles. */
static int booting(void) { return cur == SCR_BOOT || cur == SCR_MODULES; }

/* B1, B2 and B3; while the display is off B1 and B2 do nothing. */
static void button(enum sched_ev e, uint32_t now_ms)
{
  if (e == EV_B3)
  {
    on = !on;
    if (on) redraw = 1;   /* the panel was dark: the screen comes back at its next step */
    return;
  }
  if (!on) return;
  if (e == EV_B1)   /* paused: the held screen moves on, from the held one (a packet screen up or not) */
  {
    if (paused) { held = next_screen(held); pick(held); }
    else pick(next_screen(cur));
    return;
  }
  paused = !paused;
  if (paused) held = in_list(cur, b1_order, N_OF(b1_order)) ? cur : SCR_HOME;   /* a packet or boot one ends first */
  else interlude_at = now_ms + INTERLUDE_EVERY_MS;      /* resumes a full period from now */
}

void sched_event(enum sched_ev e, uint32_t now_ms)
{
  switch (e)
  {
    case EV_SENT_LIVE:   /* preempts whatever is on; paused or booting, the screen up stays and shows it */
      if (paused || booting()) redraw = 1;
      else play(SCR_BURST);
      extras = 0;
      break;
    case EV_SENT_EXTRA: if (extras < UINT16_MAX) extras++; break;
    case EV_ACK: case EV_NO_ACK: redraw = 1; break;   /* the link line and the banner show the outcome */
    case EV_SETTLED: settled = 1; break;
    default: button(e, now_ms); break;   /* EV_B1..EV_B3 */
  }
}

/* What follows cur's end. While paused the held screen comes back (from its frame 0) after itself, and after
   a packet's banner that was up at the press. */
static void after(void)
{
  if (cur == SCR_BOOT) { play(SCR_MODULES); steps = UINT32_MAX; return; }   /* held until check_modules ends it */
  if (cur == SCR_MODULES) { play(SCR_HACK); return; }
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

/* The checklist holds until every port has its verdict (EV_SETTLED) or the cap, then shows the outcome for
   its scr_frames, its frame counting on. */
static void check_modules(uint32_t now_ms)
{
  if (cur != SCR_MODULES || check != SCR_CHECK_WAIT) return;
  if (!settled && !reached(now_ms, boot_ms + SCHED_MODULES_CAP_MS)) return;
  check = settled ? SCR_CHECK_DONE : SCR_CHECK_TIMEOUT;
  steps = frame + scr_frames(SCR_MODULES);
}

int sched_step(uint32_t now_ms, enum scr_id *id, unsigned *out_frame, int *display_on)
{
  *display_on = on;
  check_modules(now_ms);
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

enum scr_check sched_check(void) { return check; }

int sched_display_on(void) { return on; }
