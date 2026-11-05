/* The bench screens' scheduler (App/scr_sched.h). One screen at a time, and its frame: each step
 * shows the current frame, then moves on, so an event that changes the screen takes effect at the
 * next step and never inside a frame. */
#include "scr_sched.h"

#define INTERLUDE_EVERY_MS 120000U   /* one interlude about every 2 minutes (design, "The interludes") */
#define NORMAL_EVERY       8U        /* steps between NORMAL redraws: once a second at 8 a second */

static const enum scr_id rotation[] = { SCR_SCOPE, SCR_VANE, SCR_SYSTEM, SCR_HACK };
#define ROTATION_N (sizeof rotation / sizeof rotation[0])

static enum scr_id cur;
static unsigned frame;           /* of cur, the next to show */
static unsigned normal_steps;    /* steps since NORMAL was last drawn */
static int redraw;               /* NORMAL changed (an ACK or a NO ACK): draw it at the next step */
static uint32_t interlude_at;    /* when the next interlude falls due (clock_ms) */
static unsigned next_interlude;  /* index into rotation */
static unsigned extras;          /* frames sent after the live one */

static int reached(uint32_t now_ms, uint32_t at_ms) { return (int32_t)(now_ms - at_ms) >= 0; }

static void show(enum scr_id id) { cur = id; frame = 0; normal_steps = 0; }

void sched_init(uint32_t now_ms)
{
  show(SCR_BOOT);
  redraw = 0;
  interlude_at = now_ms + INTERLUDE_EVERY_MS;
  next_interlude = 0;
  extras = 0;
}

void sched_event(enum sched_ev e, uint32_t now_ms)
{
  (void)now_ms;
  switch (e)
  {
    case EV_SENT_LIVE: show(SCR_BURST); extras = 0; break;   /* preempts whatever is on */
    case EV_SENT_EXTRA: if (extras < UINT16_MAX) extras++; break;
    case EV_ACK: case EV_NO_ACK: redraw = 1; break;   /* the TX row (NORMAL) and the banner show the outcome */
    default: break;   /* EV_B1..EV_B3: the buttons (Task 7) */
  }
}

/* The screen after cur's last frame. */
static enum scr_id after(enum scr_id id)
{
  if (id == SCR_BOOT) return SCR_HACK;
  if (id == SCR_BURST) return SCR_BANNER;
  return SCR_NORMAL;   /* HACK after the boot splash, the banner and every interlude */
}

int sched_step(uint32_t now_ms, enum scr_id *id, unsigned *out_frame, int *display_on)
{
  *display_on = 1;
  if (cur == SCR_NORMAL && reached(now_ms, interlude_at))
  {
    show(rotation[next_interlude]);
    next_interlude = (next_interlude + 1U) % ROTATION_N;
    interlude_at = now_ms + INTERLUDE_EVERY_MS;
  }
  *id = cur;
  *out_frame = frame;
  if (cur == SCR_NORMAL)
  {
    int draw = normal_steps == 0 || redraw;
    redraw = 0;
    normal_steps = (normal_steps + 1U) % NORMAL_EVERY;
    return draw;
  }
  if (++frame >= scr_frames(cur)) show(after(cur));
  return 1;
}

unsigned sched_extras(void) { return extras; }
