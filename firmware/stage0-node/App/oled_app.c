/* The bench OLED's application (App/oled_app.h): the 125 ms step, and what the exchange's hooks note
 * (App/oled_hooks.h). The timer callback runs in the RTC interrupt, so it only posts the task; the
 * task and the hooks both run in the main loop, so they share this state without a lock. */
#include "oled_app.h"
#include <string.h>
#include "busymon.h"
#include "clock.h"
#include "oled_dma.h"
#include "oled_hooks.h"
#include "oled_view.h"
#include "scr_sched.h"
#include "scr_view.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "utilities_def.h"

#define STEP_MS        125U     /* 8 frames a second */
#define AIRTIME_OF_MS  60000U   /* the system bars' airtime: this minute's exchange, of a minute */

/* RAM2 (NOLOAD: nothing initializes it, so oled_app_start does); the host test builds with it empty. */
#ifndef OLED_APP_RAM2
#define OLED_APP_RAM2 __attribute__((section(".RAM2_region")))
#endif
static oled_fb fb OLED_APP_RAM2;
static scr_view_t view OLED_APP_RAM2;

static UTIL_TIMER_Object_t step_timer;
static uint32_t live_seq, live_s;   /* the minute's live frame and when it went (clock_s) */
static int awaiting;                /* its reply has not come yet */
static uint32_t air_ms;             /* airtime of this minute's frames so far */

void oled_note_sent(uint32_t seq, const uint8_t *frame, uint8_t len, int live)
{
  uint32_t now = clock_ms();
  if (live)
  {
    live_seq = seq; live_s = clock_s(); awaiting = 1; air_ms = 0;
    view.last_seq = seq;
    view.last_acked = SCR_TX_WAIT;
    view.cipher_len = (uint8_t)(len < sizeof view.cipher ? len : sizeof view.cipher);
    memcpy(view.cipher, frame, view.cipher_len);
  }
  else awaiting = 0;   /* the reply that comes next is this frame's */
  air_ms += oled_view_airtime_ms(len);
  sched_event(live ? EV_SENT_LIVE : EV_SENT_EXTRA, now);
}

void oled_note_ack(uint32_t seq, int16_t rssi, int8_t snr)
{
  if (!awaiting || seq != live_seq) return;   /* a backlog frame's ACK: the TX row shows the live frame */
  awaiting = 0;
  view.last_acked = SCR_TX_ACK; view.ack_rssi = rssi; view.ack_snr = snr;
  sched_event(EV_ACK, clock_ms());
}

void oled_note_no_ack(uint32_t seq)
{
  if (!awaiting || seq != live_seq) return;
  awaiting = 0;
  view.last_acked = SCR_TX_NO_ACK;
  sched_event(EV_NO_ACK, clock_ms());
}

/* One step. A busy driver means a frame (or the start-up) is still going out of the send buffer: drawing
   into it now would tear that frame, so the step waits for the next tick, and the scheduler, not
   stepped, shows the same frame then. A faulted display costs nothing: the scheduler runs on, no frame is
   drawn. */
static void step(void)
{
  enum scr_id id; unsigned frame; int on;
  if (oled_dma_busy()) return;
  if (!sched_step(clock_ms(), &id, &frame, &on) || !on || oled_dma_faulted()) return;
  oled_view_fill(&view, id, frame);
  view.extra_frames = sched_extras();
  view.last_age_s = clock_s() - live_s;
  uint32_t air_pct = (air_ms * 100U + AIRTIME_OF_MS - 1U) / AIRTIME_OF_MS;   /* rounded up: any airtime shows */
  view.airtime_pct = (uint8_t)(air_pct > 100U ? 100U : air_pct);
  scr_draw(&fb, id, frame, &view);
  ssd1325_frame(&fb, 1, oled_dma_buffer());
  (void)oled_dma_send(oled_dma_buffer());   /* not busy (above), so only a fault refuses it */
}
BUSYMON_TASK(step)

static void on_step_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Oled, CFG_SEQ_Prio_0); }

void oled_app_start(void)
{
  memset(&fb, 0, sizeof fb);
  memset(&view, 0, sizeof view);
  view.last_acked = SCR_TX_NONE;
  oled_dma_init();
  sched_init(clock_ms());
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Oled, UTIL_SEQ_RFU, step_timed);
  (void)UTIL_TIMER_Create(&step_timer, STEP_MS, UTIL_TIMER_PERIODIC, on_step_timer, NULL);
  (void)UTIL_TIMER_Start(&step_timer);
}
