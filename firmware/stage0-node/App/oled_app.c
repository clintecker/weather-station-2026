/* The bench OLED's application (App/oled_app.h): the 125 ms step, and what the exchange's hooks note
 * (App/oled_hooks.h). The timer callback runs in the RTC interrupt, so it only posts the task; the
 * task and the hooks both run in the main loop, so they share this state without a lock. */
#include "oled_app.h"
#include <string.h>
#include "board_inputs.h"
#include "busymon.h"
#include "clock.h"
#include "oled_dma.h"
#include "oled_hooks.h"
#include "oled_view.h"
#include "scr_sched.h"
#include "scr_screens.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "utilities_def.h"

#define STEP_MS        125U     /* 8 frames a second */
#define DEBOUNCE_MS    50U      /* edges of one button closer than this are one press (contact bounce) */
#define AIRTIME_OF_MS  60000U   /* the system bars' airtime: this minute's exchange, of a minute */

/* RAM2 (NOLOAD: nothing initializes it, so oled_app_start does); the host test builds with it empty. */
#ifndef OLED_APP_RAM2
#define OLED_APP_RAM2 __attribute__((section(".RAM2_region")))
#endif
static scr_view_t view OLED_APP_RAM2;

static UTIL_TIMER_Object_t step_timer;
static uint32_t live_seq, live_s;   /* the minute's live frame and when it went (clock_s) */
static int awaiting;                /* its reply has not come yet */
static volatile uint32_t pressed;   /* bit b: button b went down (set in the EXTI interrupt) */
static volatile uint32_t edge_ms[4]; /* when button b's last edge came, taken or not */
static uint32_t armed;              /* bit b: a step has read button b up since its last press (main loop only) */
static int powered = 1;             /* what the driver was last told (oled_dma_enable) */
static uint32_t air_ms;             /* airtime of this minute's frames so far */
static unsigned reports;            /* health reports sent since the live frame */
static uint32_t exchange_s;         /* when the minute's exchange last started (clock_s) */
static int exchanged;               /* one has */

void oled_note_exchange(void) { air_ms = 0; exchange_s = clock_s(); exchanged = 1; }

/* The radio history: every frame's outcome, the live one's or not. */
static void radio_note(int16_t rssi, int16_t snr)
{
  unsigned n = view.radio.n;
  (void)scr_hist_push(view.radio.snr, SCR_RADIO_HIST, n, snr);
  view.radio.n = (uint8_t)scr_hist_push(view.radio.rssi, SCR_RADIO_HIST, n, rssi);
}

void oled_note_sent(uint32_t seq, const uint8_t *frame, uint8_t len, int kind)
{
  uint32_t now = clock_ms();
  int live = kind == OLED_SENT_LIVE;
  if (live)
  {
    live_seq = seq; live_s = clock_s(); awaiting = 1; reports = 0;
    view.last_seq = seq;
    view.last_acked = SCR_TX_WAIT;
    view.cipher_len = (uint8_t)(len < sizeof view.cipher ? len : sizeof view.cipher);
    memcpy(view.cipher, frame, view.cipher_len);
  }
  else
  {
    awaiting = 0;   /* the reply that comes next is this frame's */
    if (kind == OLED_SENT_REPORT && reports < UINT16_MAX) reports++;
  }
  air_ms += oled_view_airtime_ms(len);
  sched_event(live ? EV_SENT_LIVE : EV_SENT_EXTRA, now);
}

void oled_note_ack(uint32_t seq, int16_t rssi, int8_t snr)
{
  radio_note(scr_hist_value(rssi), snr);
  if (!awaiting || seq != live_seq) return;   /* a backlog frame's ACK: the TX row shows the live frame */
  awaiting = 0;
  view.last_acked = SCR_TX_ACK; view.ack_rssi = rssi; view.ack_snr = snr;
  sched_event(EV_ACK, clock_ms());
}

void oled_note_no_ack(uint32_t seq)
{
  radio_note(SCR_GAP, SCR_GAP);
  if (!awaiting || seq != live_seq) return;
  awaiting = 0;
  view.last_acked = SCR_TX_NO_ACK;
  sched_event(EV_NO_ACK, clock_ms());
}

/* From the EXTI interrupt: an edge within DEBOUNCE_MS of the button's previous edge is bounce and is dropped
   (the time is updated either way, so a long bounce train stays one press); otherwise it is a press. */
void oled_app_button(unsigned b)
{
  if (b < 1U || b > 3U) return;
  uint32_t now = clock_ms();
  if (now - edge_ms[b] >= DEBOUNCE_MS) pressed |= 1U << b;
  edge_ms[b] = now;
}

/* The presses since the last step, to the scheduler: one per button however many came. The EXTI lines see
   falling edges only, and a contact bounces on release too: a bounce edge more than DEBOUNCE_MS after the
   press would pass the interrupt's filter as a second press. So a press counts only if a step has read the
   button up (board_button_up) since the last press it took. The pin is read after the presses are taken: an
   edge that comes between the two (bit b set again) may be the release bouncing, and the button stays
   disarmed until a later step reads it up with no edge since. */
static void take_buttons(uint32_t now)
{
  uint32_t m = __atomic_exchange_n(&pressed, 0U, __ATOMIC_RELAXED);
  for (unsigned b = 1; b <= 3U; b++)   /* bound: 3 buttons */
  {
    uint32_t bit = 1U << b;
    if ((m & bit) && (armed & bit)) { armed &= ~bit; sched_event((enum sched_ev)(EV_B1 + (b - 1U)), now); }
    if (board_button_up(b) && !(__atomic_load_n(&pressed, __ATOMIC_RELAXED) & bit)) armed |= bit;
  }
}

/* One step. B3 reaches the driver first, busy or not: the panel's power command follows a frame under way,
   and after a fault (a DMA that never ended, too) on is the whole start-up again. A busy driver means a
   frame, a power command or the start-up is still going out of the send buffer: drawing into it now would
   tear that frame, so the step waits for the next tick, and the scheduler, not stepped, shows the same
   frame then (after B3 on, NORMAL's redraw). A faulted display costs nothing: the scheduler runs on, no
   frame is drawn. */
static void step(void)
{
  enum scr_id id; unsigned frame; int on;
  uint32_t now = clock_ms();
  take_buttons(now);
  oled_view_sample(&view, now);   /* the histories go on, drawn or not */
  int want = sched_display_on();
  if (want != powered) { powered = want; oled_dma_enable(want); }
  if (oled_dma_busy()) return;
  int draw = sched_step(now, &id, &frame, &on);
  if (!draw || !on || oled_dma_faulted()) return;
  oled_view_fill(&view, id, frame);
  unsigned extras = sched_extras();   /* every frame after the live one: the backlog and the reports */
  view.reports = reports;
  view.extra_frames = extras > reports ? extras - reports : 0U;
  view.last_age_s = clock_s() - live_s;
  view.since_exchange_s = exchanged ? clock_s() - exchange_s : SCR_NONE_S;
  uint32_t air_pct = (air_ms * 100U + AIRTIME_OF_MS - 1U) / AIRTIME_OF_MS;   /* rounded up: any airtime shows */
  view.airtime_pct = (uint8_t)(air_pct > 100U ? 100U : air_pct);
  uint8_t *out = oled_dma_buffer();
  oled_surf s = oled_surf_on(out, 1);   /* drawn into the send buffer, turned: the panel is upside down */
  scr_draw(&s, id, frame, &view);
  (void)oled_dma_send(out);   /* not busy (above), so only a fault refuses it */
}
BUSYMON_TASK(step)

static void on_step_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Oled, CFG_SEQ_Prio_0); }

void oled_app_start(void)
{
  memset(&view, 0, sizeof view);
  view.last_acked = SCR_TX_NONE;
  oled_view_build(&view);
  oled_dma_init();
  sched_init(clock_ms());
  for (unsigned b = 1; b <= 3U; b++) edge_ms[b] = clock_ms() - DEBOUNCE_MS;   /* bound: 3 buttons */
  pressed = 0; armed = 0; powered = 1;   /* armed by the first step that reads each button up */
  exchanged = 0;
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Oled, UTIL_SEQ_RFU, step_timed);
  (void)UTIL_TIMER_Create(&step_timer, STEP_MS, UTIL_TIMER_PERIODIC, on_step_timer, NULL);
  (void)UTIL_TIMER_Start(&step_timer);
}
