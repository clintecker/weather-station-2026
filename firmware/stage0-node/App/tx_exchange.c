/* GENERATED from tx_exchange.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/tx_exchange.lit.md (tests/test_tangle.py checks this file). */
/* The minute's radio exchange, one state at a time (docs/firmware-event-model.md has the table).
 * Every state is left by an event that is certain to come: the radio's TxDone/TxTimeout
 * (WS_TX_TIMEOUT_MS), the ACK window timer, or the gap timer. Anything else is counted as
 * unexpected. Time comes only from an ACK that echoes the counter of the frame just sent. */
#define WS_CHECK_FILE 2
#include "tx_exchange.h"
#include <string.h>
#include "busymon.h"
#include "clock.h"
#include "events.h"
#include "fault.h"
#include "leds.h"
#include "radio.h"
#include "radio_cfg.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "sys_app.h"
#include "tx_node.h"
#include "tx_policy.h"
#include "tx_time.h"
#include "utilities_def.h"
#include "watchdog.h"
#include "ws_be.h"
#include "ws_check.h"

#define ACK_WINDOW_MS       2000U
#define EXCHANGE_MARGIN_S   5U
#define INTER_FRAME_MS      50U     /* gap before each further frame: the RX is back to listening after its ACK */

/* WS_FW_BUILD_ID: first 8 hex digits of the release commit (WS_FW_VERSION), 0 if they are not
   hex; computed by the Makefile. */
#ifndef WS_FW_BUILD_ID
#error "WS_FW_BUILD_ID comes from the Makefile"
#endif

typedef enum { TX_IDLE, TX_GAP, TX_SENDING, TX_ACK_WAIT, TX_DIAG_SENDING, TX_STATES } tx_state_t;
static const char *const tx_state_name[] = { "idle", "gap", "sending", "ack-wait", "diag-sending" };
_Static_assert(sizeof tx_state_name / sizeof tx_state_name[0] == TX_STATES, "one name per state");
static tx_state_t tx_state = TX_IDLE;
static enum { GAP_FRAME, GAP_DIAG } gap_then;   /* what the gap timer starts */
static UTIL_TIMER_Object_t gap_timer;
/* The ACK window is this firmware's own timer, not the radio driver's: ST's RxTimeoutTimer is left
   running by a CRC error and its timeout leaves the radio receiving. The radio
   listens with no driver timeout (ws_radio_rx(0)); ack_timer ends the window, and every way out of
   ack-wait puts the radio in standby first. */
static UTIL_TIMER_Object_t ack_timer;
static uint32_t batch;      /* this pass's events not yet handled (process) */
static RadioEvents_t events;

static jref_t queue[MAX_QUEUE];
static uint8_t replied[MAX_QUEUE];   /* the gateway answered queue[i] (ACK or NACK) */
static unsigned qn, qi;
static uint32_t exchange_start_s, exchange_limit_s;   /* watchdog progress evidence */
static uint64_t sent_counter;
static uint32_t sent_epoch, sent_seq;
/* Transmission failures: a refused counter reservation, a refused Radio.Send or a
   TxTimeout; only a TxDone (the frame really left) clears the run. Before 2026-10-14 one run mixed
   these with journal appends, and every accepted Send reset it, so a radio that accepted Send but
   never finished a frame was never reset. */
static tx_counts_t tx_counts;
const tx_counts_t *exchange_counts(void) { return &tx_counts; }

/* Provisioning: the key never leaves this file (docs/power-of-ten.md, rule 6). */
static tx_identity_t identity;
static uint8_t key[WS_KEY_LEN];
int exchange_load_identity(void)
{
  identity.provisioned = store_config_load(&identity.station, key, identity.kcv) == 0;
  return identity.provisioned;
}
const tx_identity_t *exchange_identity(void) { return &identity; }

/* Only a WS_ACK_FRAME_LEN reply is ever opened. rx_len keeps the true received size, so a longer
   packet is still rejected (ws_open_reply checks the length before reading) and logged as it was. */
static uint8_t rx_frame[WS_ACK_FRAME_LEN];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Signal of the last authentic ACK, as the node heard it (DIAG, design section 4): the uplink and
   downlink can differ. */
static int8_t ack_rssi = WS_SIGNAL_NONE, ack_snr = WS_SIGNAL_NONE;

/* Events from interrupt and timer context, as bits (App/events.h). */
#define EV_TX_DONE    (1U << 0)
#define EV_TX_TIMEOUT (1U << 1)
#define EV_RX_DONE    (1U << 2)
#define EV_RX_TIMEOUT (1U << 3)
#define EV_RX_ERROR   (1U << 4)
#define EV_GAP        (1U << 5)
#define EV_ACK_END    (1U << 6)
#define EV_COUNT      7U
#define EV_ALL        ((1U << EV_COUNT) - 1U)
static const char *const ev_name[EV_COUNT] = { "tx-done", "tx-timeout", "rx-done", "rx-timeout", "rx-error", "gap", "ack-end" };
static volatile uint32_t pending_ev;

static void post(uint32_t ev) { events_post(&pending_ev, ev); }
static void on_gap(void *ctx) { (void)ctx; post(EV_GAP); }
static void on_ack_end(void *ctx) { (void)ctx; post(EV_ACK_END); }
static void on_tx_done(void) { post(EV_TX_DONE); }
static void on_tx_timeout(void) { post(EV_TX_TIMEOUT); }
static void on_rx_timeout(void) { post(EV_RX_TIMEOUT); }
static void on_rx_error(void) { post(EV_RX_ERROR); }
/* ST's HAL raises RxDone for a packet whose payload CRC failed, then RxError (stm32wlxx_hal_subghz.c
   HAL_SUBGHZ_IRQHandler): such a packet is only the RxError. */
/* cppcheck-suppress constParameterCallback ; ST's RadioEvents_t RxDone signature */
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  if (ws_radio_take_crc_error()) return;
  rx_len = size;
  memcpy(rx_frame, payload, size > sizeof rx_frame ? sizeof rx_frame : size);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX_DONE);
}

int exchange_busy(void) { return tx_state != TX_IDLE; }
int exchange_overdue(uint32_t now_s) { return exchange_busy() && now_s - exchange_start_s > exchange_limit_s; }
const char *exchange_state_name(void) { return tx_state_name[tx_state]; }

/* The exchange (and any health report in flight) is over: the radio sleeps until the next minute,
   and a reading that a minute produced meanwhile is journaled now, first. */
static void radio_idle(void) { tx_state = TX_IDLE; ws_radio_sleep(); held_flush(); }

/* The exchange outlasted its worst case (a radio that never finishes): stop the radio, then journal
   any held reading while it is idle, so a watchdog reset loses nothing (app_tx.c watchdog_healthy). */
void exchange_abort(void)
{
  (void)UTIL_TIMER_Stop(&gap_timer);
  (void)UTIL_TIMER_Stop(&ack_timer);
  ws_radio_standby();
  tx_state = TX_IDLE;
  held_flush();
}

/* The next frame goes after INTER_FRAME_MS, from the gap timer: nothing waits meanwhile. */
static void gap_before(int then)
{
  gap_then = then; tx_state = TX_GAP;
  (void)WS_CHECK(UTIL_TIMER_Start(&gap_timer) == UTIL_TIMER_OK);   /* refused only if running: its EV_GAP still comes */
}

static uint16_t clamp16(uint32_t v) { return v > UINT16_MAX ? UINT16_MAX : (uint16_t)v; }
static int8_t clamp8(int v) { return (int8_t)(v < -INT8_MAX ? -INT8_MAX : v > INT8_MAX ? INT8_MAX : v); }  /* INT8_MIN means "none" */

/* Health report (kind 4), sent after a minute's exchange (also while probing, so the link
   field can read "probing"). Fire-and-forget: no journal entry, no receive window. Returns 1 if it
   went on air (its TxDone or TxTimeout ends the exchange). */
static int send_diag(void)
{
  uint8_t plain[WS_DIAG_PLAIN_LEN], frame[WS_DIAG_FRAME_LEN]; uint64_t ctr;
  uint32_t now = clock_s();
  uint32_t crashes = fault_count();
  ws_diag_t d = { .epoch = node_state()->boot_epoch, .uptime = node_uptime_s(), .lost = store_journal_lost(),
                  .build = (uint32_t)WS_FW_BUILD_ID, .pending = clamp16(store_journal_pending()),
                  .torn = clamp16(store_journal_burned()), .abandoned = clamp16(store_abandoned_total()),
                  .no_ack = clamp16(tx_counts.no_ack), .rejects = clamp16(tx_counts.ack_rejects),
                  .reset_cause = (uint8_t)watchdog_reset_code(), .link = (uint8_t)policy_probing(),
                  .crashes = (uint8_t)(crashes > UINT8_MAX ? UINT8_MAX : crashes), .energy = (uint8_t)energy_state(),
                  .rssi = ack_rssi, .snr = ack_snr };
  ws_diag_pack(&d, plain);
  if (store_next_counter(&ctr)) { ws_failrun_note(&tx_counts.air, 0); return 0; }
  if (!WS_CHECK(ws_seal_kind(key, identity.station, WS_KIND_DIAG, ctr, plain, sizeof plain, frame, sizeof frame) >= 0)) return 0;
  if (ws_radio_send(frame, sizeof frame) != RADIO_STATUS_OK) { ws_failrun_note(&tx_counts.air, 0); return 0; }
  policy_diag_sent(now);   /* only a report the radio took: a refused one is due again next minute */
  tx_state = TX_DIAG_SENDING;
  APP_PRINTF("#diag sent pending=%u lost=%u torn=%u abandoned=%u no_ack=%u\n", d.pending, (unsigned)d.lost, d.torn, d.abandoned, d.no_ack);
  return 1;
}

static void finish_exchange(void)
{
  policy_exchange_end(queue, replied, qn);
  if (policy_diag_due()) { gap_before(GAP_DIAG); return; }
  radio_idle();
}

static void next_item(void)
{
  if (++qi < qn) { gap_before(GAP_FRAME); return; }
  finish_exchange();
}

/* A missed reply ends this minute's drain, after one more frame: a failing link does not burn the
   allowance, and the one more frame tells a record the gateway refuses (the next one is answered,
   so the missed one earns a strike) from a lossy link (strike rule, ws_policy.h). A second miss in a
   row, or a transmit failure, ends it at once. */
#define FRAMES_AFTER_MISS 1U   /* one more frame after a miss tells a refused record from a lost one */
static int missed_last;   /* the frame before this one got no reply */
static void stop_drain(void) { qn = qi + 1; }
static void drain_after_miss(void)
{
  if (missed_last) stop_drain();
  else if (qn > qi + 1U + FRAMES_AFTER_MISS) qn = qi + 1U + FRAMES_AFTER_MISS;
  missed_last = 1;
}

/* Seal and send one journaled plaintext. 1: on air (its TxDone follows); 0: a local failure (the
   exchange moves on); -1: the counter reservation was refused, which ends the exchange. */
static int send_obs(const uint8_t *plain, int plen)
{
  uint8_t frame[OBS_FRAME_MAX];
  /* No durable counter reservation, no transmission (nonce reuse would break CCM). */
  if (store_next_counter(&sent_counter)) { ws_failrun_note(&tx_counts.air, 0); APP_PRINTF("#error counter-reserve\n"); return -1; }
  int flen = ws_seal_kind(key, identity.station, WS_KIND_OBS, sent_counter, plain, (uint32_t)plen, frame, sizeof frame);
  if (!WS_CHECK(flen >= 0)) { APP_PRINTF("#error seal\n"); return 0; }   /* a valid station and counter always seal */
  sent_epoch = ws_obs_epoch(plain);
  sent_seq = ws_obs_seq(plain);
  tx_counts.sent++;
  led_flash(LED_BLUE, LED_FLASH_MS);
  if (ws_radio_send(frame, (uint8_t)flen) == RADIO_STATUS_OK) { tx_state = TX_SENDING; return 1; }
  ws_failrun_note(&tx_counts.air, 0); APP_PRINTF("#error radio-busy\n");
  return 0;
}

/* Send queue[qi]. A local failure (journal read, seal, radio busy) moves on to the next item after
 * a gap, like a sent frame; a refused counter reservation ends the exchange, after the policy has seen
 * the replies so far (test_a_refused_counter_reservation_still_reports_the_answers). */
static void send_current(void)
{
  uint8_t plain[WS_OBS_PLAIN_MAX];
  int plen = -1, rc = 0;
  if (!WS_CHECK(qi < qn)) { finish_exchange(); return; }   /* gap_before(GAP_FRAME) comes only with an item left */
  if (store_journal_read(queue[qi], plain) || (plen = ws_obs_plain_len(plain, sizeof plain)) < 0) { APP_PRINTF("#error journal-read\n"); }
  else rc = send_obs(plain, plen);
  if (rc < 0) { policy_exchange_end(queue, replied, qn); radio_idle(); }
  else if (rc == 0) next_item();
}

void exchange_start(const jref_t *live, unsigned backlog)
{
  if (!WS_CHECK(!exchange_busy())) return;   /* app_tx.c holds the reading while an exchange runs */
  if (!WS_CHECK(backlog <= MAX_QUEUE - 1U)) backlog = MAX_QUEUE - 1U;   /* the queue's room */
  qn = 0;
  if (live) queue[qn++] = *live;
  qn += store_journal_oldest(queue + qn, backlog + (live ? 0U : 1U), live);
  qi = 0;
  missed_last = 0;
  memset(replied, 0, sizeof replied);
  /* The longest this exchange can take: every frame and the health report hit their transmit
     timeout or wait out the whole ACK window, plus the gaps; then a margin. */
  exchange_limit_s = ((qn + 1U) * (WS_TX_TIMEOUT_MS + ACK_WINDOW_MS + INTER_FRAME_MS)) / CLOCK_MS_PER_S + EXCHANGE_MARGIN_S;
  /* The first frame, like every other, goes after the gap: the radio may have been put to sleep
     moments ago (the last exchange ended this main-loop pass), and the chip needs time to enter
     sleep before it is woken (ST's RadioSleep waited 2 ms; radio_cfg.c ws_radio_sleep). */
  if (qn) { exchange_start_s = clock_s(); gap_before(GAP_FRAME); }
}

/* No reply to the frame just sent; it stays journaled for a later retry. */
static void no_reply(int flash_red)
{
  tx_counts.no_ack++;
  if (flash_red) led_flash(LED_RED, LED_FLASH_MS);
  APP_PRINTF("#ack none epoch=%u seq=%u\n", (unsigned)sent_epoch, (unsigned)sent_seq);
  drain_after_miss();
  next_item();
}

/* An authentic reply, opened. */
typedef struct { uint64_t ctr, echo; uint32_t epoch, seq, word; uint8_t kind; } reply_t;

/* The gateway answered the frame just sent (queue[qi]). */
static void mark_replied(void)
{
  if (WS_CHECK(qi < MAX_QUEUE)) replied[qi] = 1;
  missed_last = 0;
}

/* Authentic permanent rejection. Accepted only for the frame just sent. */
static int on_nack(const reply_t *r, int mine)
{
  jref_t ref;
  if (!mine) { tx_counts.ack_rejects++; APP_PRINTF("#nack ignored: not for the frame just sent\n"); return 0; }
  mark_replied();
  /* A total that failed to persist is only a count: the record is acknowledged either way. */
  if (store_journal_find(r->epoch, r->seq, &ref) == 0 && store_journal_ack(ref) == 0) (void)store_note_abandoned();
  led_flash(LED_RED, LED_FLASH_LONG_MS);
  APP_PRINTF("#nack epoch=%u seq=%u reason=%u abandoned=%u\n", (unsigned)r->epoch, (unsigned)r->seq,
             (unsigned)r->word, (unsigned)store_abandoned_total());
  return 1;
}

/* Any authentic ACK commits its record, wherever it is; only the ACK for the frame just sent ends
   the window or sets the clock (a replayed ACK cannot move it). */
static int on_ack(const reply_t *r, int mine)
{
  jref_t ref;
  int found = store_journal_find(r->epoch, r->seq, &ref) == 0;
  if (found && store_journal_ack(ref)) APP_PRINTF("#error journal-ack\n");
  policy_strike_forget(r->epoch, r->seq);   /* any authentic ACK for a record ends its strikes */
  if (mine) mark_replied();
  int fresh = mine && time_sync(r->word);
  if (found) tx_counts.acked++;
  led_flash(LED_GREEN, LED_FLASH_MS); /* authentic host ACK: reading is committed */
  APP_PRINTF("#ack epoch=%u seq=%u found=%d time_sync=%d rssi=%d snr=%d pending=%u\n",
             (unsigned)r->epoch, (unsigned)r->seq, found, fresh, rx_rssi, rx_snr,
             (unsigned)store_journal_pending());
  return mine;
}

/* Returns 1 for the authentic reply (ACK or NACK) to the frame just sent; 0 for anything else. */
static int handle_reply(void)
{
  reply_t r;
  if (ws_open_reply(key, identity.station, rx_frame, rx_len, &r.kind, &r.ctr, &r.epoch, &r.seq, &r.word, &r.echo))
  {
    tx_counts.ack_rejects++;
    led_flash(LED_RED, LED_FLASH_MS);
    APP_PRINTF("#ack reject len=%u rssi=%d snr=%d\n", rx_len, rx_rssi, rx_snr);
    return 0;
  }
  ack_rssi = clamp8(rx_rssi);   /* authentic reply only: a forged frame cannot set these */
  ack_snr = clamp8(rx_snr);
  int mine = r.echo == sent_counter && r.epoch == sent_epoch && r.seq == sent_seq;
  return r.kind == WS_KIND_NACK ? on_nack(&r, mine) : on_ack(&r, mine);
}

/* The reply ended the window: stop its timer, and drop an ack-end it already posted, in this pass
   or the next (a race, not a bug: `unexpected` stays a bug indicator). */
static void window_closed(void)
{
  (void)UTIL_TIMER_Stop(&ack_timer);
  batch &= ~EV_ACK_END;
  events_clear(&pending_ev, EV_ACK_END);
}

/* The state handlers: 1 if the event is one this state expects (and was handled), else 0. */
static int in_sending(uint32_t ev)
{
  if (ev == EV_TX_DONE)
  {
    ws_failrun_note(&tx_counts.air, 1);   /* the frame left: the radio works */
    tx_state = TX_ACK_WAIT;
    (void)WS_CHECK(UTIL_TIMER_Start(&ack_timer) == UTIL_TIMER_OK);   /* refused only if running: it still ends the window */
    ws_radio_rx(0);
    return 1;
  }
  if (ev != EV_TX_TIMEOUT) return 0;
  ws_radio_standby();               /* the driver's timeout leaves the radio transmitting */
  ws_failrun_note(&tx_counts.air, 0);
  led_flash(LED_RED, LED_FLASH_MS); APP_PRINTF("#error tx-timeout\n");
  stop_drain(); next_item();
  return 1;
}

static int in_ack_wait(uint32_t ev)
{
  if (ev == EV_ACK_END) { ws_radio_standby(); no_reply(1); return 1; }
  if (ev == EV_RX_DONE && handle_reply()) { window_closed(); next_item(); return 1; }
  if (ev != EV_RX_DONE && ev != EV_RX_ERROR && ev != EV_RX_TIMEOUT) return 0;
  /* Not the reply to this frame: foreign, forged, another frame's ACK, a payload CRC failure
     (rx-error) or a header failure (rx-timeout: ST's radio.c reports IRQ_HEADER_ERROR so).
     Keep listening until the window ends rather than miss the real ACK.
     After a single-window reception the radio is in standby; listen again. */
  if (ev != EV_RX_DONE) APP_PRINTF("#ack damaged %s; still listening\n", ev == EV_RX_ERROR ? "payload" : "header");
  ws_radio_rx(0);
  return 1;
}

static int in_diag_sending(uint32_t ev)
{
  if (ev != EV_TX_DONE && ev != EV_TX_TIMEOUT) return 0;
  if (ev == EV_TX_TIMEOUT) ws_radio_standby();
  ws_failrun_note(&tx_counts.air, ev == EV_TX_DONE);
  if (ev == EV_TX_TIMEOUT) { led_flash(LED_RED, LED_FLASH_MS); APP_PRINTF("#error tx-timeout\n"); }
  radio_idle();
  return 1;
}

static int in_gap(uint32_t ev)
{
  if (ev != EV_GAP) return 0;
  if (gap_then == GAP_FRAME) send_current();
  else if (!send_diag()) radio_idle();
  return 1;
}

/* One event in one state. Every pair not listed is a bug or a stray radio callback: counted and
   printed, never acted on (docs/firmware-event-model.md has the full table). */
static void handle(uint32_t ev)
{
  int done = 0;
  switch (tx_state)
  {
    case TX_SENDING: done = in_sending(ev); break;
    case TX_ACK_WAIT: done = in_ack_wait(ev); break;
    case TX_DIAG_SENDING: done = in_diag_sending(ev); break;
    case TX_GAP: done = in_gap(ev); break;
    default: if (!WS_CHECK(tx_state == TX_IDLE)) tx_state = TX_IDLE; break;   /* idle expects nothing */
  }
  if (done) return;
  tx_counts.unexpected++;
  APP_PRINTF("#error unexpected event=%s state=%s\n", ev_name[__builtin_ctz(ev)], tx_state_name[tx_state]);
}

static void process(void)
{
  batch = events_take(&pending_ev);
  /* A TxTimeout that fired with its TxDone in the same pass is a race, not a bug: the frame left
     (ST stops the timeout on TxDone, so a later one cannot come). Dropped, like a stale ack-end. */
  if ((batch & EV_TX_DONE) && (batch & EV_TX_TIMEOUT)) batch &= ~EV_TX_TIMEOUT;
  if (!WS_CHECK(!(batch & ~EV_ALL))) batch &= EV_ALL;   /* only post() sets bits, and only EV_* ones */
  uint32_t bit = 1;
  for (unsigned k = 0; k < EV_COUNT && batch; k++, bit <<= 1)   /* lowest bit first */
    if (batch & bit) { batch &= ~bit; handle(bit); }
}
BUSYMON_TASK(process)

void exchange_init(void)
{
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  events.RxDone = on_rx_done;
  events.RxTimeout = on_rx_timeout;
  events.RxError = on_rx_error;
  Radio.Init(&events);
  ws_radio_configure(0);
  ws_radio_sleep();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process_timed);
  (void)UTIL_TIMER_Create(&gap_timer, INTER_FRAME_MS, UTIL_TIMER_ONESHOT, on_gap, NULL);
  (void)UTIL_TIMER_Create(&ack_timer, ACK_WINDOW_MS, UTIL_TIMER_ONESHOT, on_ack_end, NULL);
}
