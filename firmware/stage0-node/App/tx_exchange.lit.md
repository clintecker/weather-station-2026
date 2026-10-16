# tx_exchange: the minute's radio exchange

`tx_exchange.c` runs the TX node's radio exchange for one minute. It sends the live observation,
then older pending observations as the policy allows. It seals each one with a freshly reserved
counter and follows it with its own ACK window. Then it sends the health report if one is due. One
explicit state machine does this, driven by radio and timer events. This file also holds the AES key
and is the only module that seals and opens frames.

This document is the source. `tools/tangle.py` generates `tx_exchange.c` from the code chunks below.
The repository also holds the generated file, so the build, the static analysers and the host tests
read ordinary C. Edit this file, then regenerate and check:

```sh
python3 tools/tangle.py firmware/stage0-node/App/tx_exchange.lit.md                       # write tx_exchange.c
python3 tools/tangle.py --check                                                          # CI: committed .c == tangle
python3 tools/tangle.py --weave /tmp/tx_exchange.html firmware/stage0-node/App/tx_exchange.lit.md   # render
```

A chunk is a fenced ` ```c {#name} ` block. A line `<<name>>` inside a chunk includes chunk
`name`. Chunks appear in reading order. The root chunk (section 11) puts them in C order.
`docs/firmware-event-model.md` describes the same state machine for the whole firmware.

## 1. Behaviour

| Behaviour | Mechanism | Checked by (`tests/test_tx_machine.py`) |
|---|---|---|
| Every state ends | each state waits only for an event that is certain to come: TxDone or TxTimeout (`WS_TX_TIMEOUT_MS`, 3000 ms), the ACK window timer (2000 ms) or the gap timer (50 ms) | `test_no_reply_closes_the_window_by_its_own_timeout`, `test_a_transmit_timeout_puts_the_stuck_radio_in_standby` |
| Unexpected events change nothing | a (state, event) pair outside the table in section 2 is counted in `unexpected` and printed | `test_every_unlisted_state_event_pair_is_only_counted` |
| Events posted together are all handled | events are bits, handled lowest bit first. Two known races are dropped, not counted | `test_two_events_before_the_main_loop_are_both_handled_in_bit_order` |
| Each frame gets a full window | the window timer is stopped when a reply ends the window | `test_every_frame_gets_its_own_full_window` |
| Damaged or foreign packets do not end the window | the radio listens again until the window timer fires | `test_stray_and_damaged_packets_keep_the_rest_of_the_window`, `test_a_damaged_reply_does_not_end_the_window_early` |
| Only the reply to the frame just sent ends the window or sets the clock | the reply must echo the counter, epoch and sequence of that frame | `test_an_authentic_ack_for_another_frame_keeps_the_window_open`, `test_a_nack_for_another_frame_is_ignored`, `test_only_an_ack_for_the_frame_just_sent_sets_the_clock` |
| No frame without a durable counter | `store_next_counter` must succeed before a frame is sealed | `test_counter_reservations_never_meet_a_busy_radio` (the reservation's flash write) |
| No flash write while the radio is busy | counters are reserved in the gap state. Readings made during an exchange are journaled when the radio goes idle | every test (`h_flash_ops_during_radio`), `test_a_reading_made_during_an_exchange_is_journaled_when_the_radio_goes_idle` |
| A failing link sends little | after a missed reply one more frame goes, then the drain stops | `test_a_missed_reply_allows_one_more_frame_then_stops_the_drain` |
| A hung radio is detected | the exchange has a time limit. The watchdog check aborts it | `test_a_radio_that_never_finishes_trips_the_exchange_bound` |

## 2. State machine

### States

| `tx_state` | Name (`STATUS`) | Radio | Waits for |
|---|---|---|---|
| `TX_IDLE` | `idle` | sleep | nothing: `exchange_start` leaves it |
| `TX_GAP` | `gap` | standby or sleep | `EV_GAP` |
| `TX_SENDING` | `sending` | transmitting an observation | `EV_TX_DONE`, `EV_TX_TIMEOUT` |
| `TX_ACK_WAIT` | `ack-wait` | receiving | `EV_RX_DONE`, `EV_RX_ERROR`, `EV_RX_TIMEOUT`, `EV_ACK_END` |
| `TX_DIAG_SENDING` | `diag-sending` | transmitting the health report | `EV_TX_DONE`, `EV_TX_TIMEOUT` |

### Events

| Bit | Event | Name | Source |
|---|---|---|---|
| 0 | `EV_TX_DONE` | `tx-done` | radio TxDone: the frame left |
| 1 | `EV_TX_TIMEOUT` | `tx-timeout` | radio TxTimeout, the driver's 3000 ms software timer |
| 2 | `EV_RX_DONE` | `rx-done` | radio RxDone with a good payload CRC |
| 3 | `EV_RX_TIMEOUT` | `rx-timeout` | radio RxTimeout. ST's `radio.c` reports a header error this way |
| 4 | `EV_RX_ERROR` | `rx-error` | radio RxError: payload CRC failed |
| 5 | `EV_GAP` | `gap` | `gap_timer`, 50 ms one-shot |
| 6 | `EV_ACK_END` | `ack-end` | `ack_timer`, 2000 ms one-shot: the ACK window is over |

### Transitions

"Next item" means: the next queued frame after a gap if one is left, else the end of the exchange.
The end of the exchange is the health report after a gap if one is due, else `idle`.

| State | Event | Action | Next state |
|---|---|---|---|
| `gap` | `EV_GAP`, frame | read `queue[qi]`, reserve a counter, seal, send | `sending`. Local failure: next item. Counter refused: `idle` |
| `gap` | `EV_GAP`, health report | reserve a counter, seal, send | `diag-sending`. Any failure: `idle` |
| `sending` | `EV_TX_DONE` | clear the transmit failure run, start `ack_timer`, listen | `ack-wait` |
| `sending` | `EV_TX_TIMEOUT` | radio to standby, note a transmit failure, stop the drain | next item (the end of the exchange) |
| `ack-wait` | `EV_RX_DONE`, the reply to this frame | ACK or NACK the record, close the window | next item |
| `ack-wait` | `EV_RX_DONE` other, `EV_RX_ERROR`, `EV_RX_TIMEOUT` | listen again | `ack-wait` |
| `ack-wait` | `EV_ACK_END` | radio to standby, count no reply, apply the drain rule | next item |
| `diag-sending` | `EV_TX_DONE` or `EV_TX_TIMEOUT` | note the transmit result (timeout: radio to standby first) | `idle` |
| any | any other | count `unexpected`, print `#error unexpected` | unchanged |

```text
idle --exchange_start--> gap --EV_GAP, frame--> sending --EV_TX_DONE--> ack-wait
                          ^ |                      |                        |
                          | |                      | EV_TX_TIMEOUT          | reply or EV_ACK_END
                          | |                      v                        |
                          | |                  next item <------------------+
                          | |                      |  frame left or report due: gap
                          | |                      |  else: idle
                          +-|----------------------+
                            |
                            +--EV_GAP, report--> diag-sending --EV_TX_DONE, EV_TX_TIMEOUT--> idle
```

### Timing constants

| Constant | Value | Use |
|---|---|---|
| `ACK_WINDOW_MS` | 2000 ms | the ACK window, from TxDone |
| `INTER_FRAME_MS` | 50 ms | the gap before every frame, the first one included |
| `EXCHANGE_MARGIN_S` | 5 s | added to the exchange time limit |
| `WS_TX_TIMEOUT_MS` (`radio_cfg.h`) | 3000 ms | the driver's transmit timeout |

The gap gives the gateway's receiver time to listen again after it sent its ACK.

The generated file opens with a summary:

```c {#abstract}
/* The minute's radio exchange, one state at a time (docs/firmware-event-model.md has the table).
 * Every state is left by an event that is certain to come: the radio's TxDone/TxTimeout
 * (WS_TX_TIMEOUT_MS), the ACK window timer, or the gap timer. Anything else is counted as
 * unexpected. Time comes only from an ACK that echoes the counter of the frame just sent. */
```

The constants:

```c {#timing}
#define ACK_WINDOW_MS       2000U
#define EXCHANGE_MARGIN_S   5U
#define INTER_FRAME_MS      50U     /* gap before each further frame: the RX is back to listening after its ACK */
```

The health report carries the build id. The Makefile computes it, and the file refuses to build
without it:

```c {#build-id}
/* WS_FW_BUILD_ID: first 8 hex digits of the release commit (WS_FW_VERSION), 0 if they are not
   hex; computed by the Makefile. */
#ifndef WS_FW_BUILD_ID
#error "WS_FW_BUILD_ID comes from the Makefile"
#endif
```

## 3. State

`tx_state` is the current state. `tx_state_name` gives the name that `STATUS` prints, and a
compile-time check keeps one name per state.

```c {#states}
typedef enum { TX_IDLE, TX_GAP, TX_SENDING, TX_ACK_WAIT, TX_DIAG_SENDING, TX_STATES } tx_state_t;
static const char *const tx_state_name[] = { "idle", "gap", "sending", "ack-wait", "diag-sending" };
_Static_assert(sizeof tx_state_name / sizeof tx_state_name[0] == TX_STATES, "one name per state");
static tx_state_t tx_state = TX_IDLE;
```

One gap timer serves both kinds of gap. `gap_then` says what the gap starts: the next frame or the
health report.

```c {#gap-timer}
static enum { GAP_FRAME, GAP_DIAG } gap_then;   /* what the gap timer starts */
static UTIL_TIMER_Object_t gap_timer;
```

The ACK window has its own timer. ST's driver timeout is not used because a CRC error leaves its
`RxTimeoutTimer` running, and its timeout leaves the radio receiving. The radio listens with
`ws_radio_rx(0)` (no driver timeout). Every way out of `ack-wait` puts the radio in standby.
`batch` holds the events of the current `process` pass that are not yet handled. `events` is the
callback table given to the radio driver.

```c {#ack-timer}
/* The ACK window is this firmware's own timer, not the radio driver's: ST's RxTimeoutTimer is left
   running by a CRC error and its timeout leaves the radio receiving. The radio
   listens with no driver timeout (ws_radio_rx(0)); ack_timer ends the window, and every way out of
   ack-wait puts the radio in standby first. */
static UTIL_TIMER_Object_t ack_timer;
static uint32_t batch;      /* this pass's events not yet handled (process) */
static RadioEvents_t events;
```

The exchange queue. `queue[0..qn)` holds journal references, `qi` is the frame being sent, and
`replied[i]` records that the gateway answered `queue[i]` with an ACK or a NACK. `MAX_QUEUE` is 21
(`tx_exchange.h`): the live frame and up to 20 backlog frames. `exchange_start_s` and
`exchange_limit_s` give the watchdog its evidence. `sent_counter`, `sent_epoch` and `sent_seq`
identify the frame just sent, which a reply must echo.

```c {#queue}
static jref_t queue[MAX_QUEUE];
static uint8_t replied[MAX_QUEUE];   /* the gateway answered queue[i] (ACK or NACK) */
static unsigned qn, qi;
static uint32_t exchange_start_s, exchange_limit_s;   /* watchdog progress evidence */
static uint64_t sent_counter;
static uint32_t sent_epoch, sent_seq;
```

### Counts

`tx_counts` is written only here. Other modules read it through `exchange_counts()`.

| Field | Incremented when |
|---|---|
| `sent` | an observation frame is sealed, before the send (a refused send counts too) |
| `acked` | an authentic ACK names a record found in the journal |
| `no_ack` | an ACK window ends with no reply |
| `ack_rejects` | a packet fails `ws_open_reply`, or a NACK is not for the frame just sent |
| `unexpected` | an event arrives in a state that does not expect it |
| `air` | a failure run: a refused counter reservation, a refused send or a TxTimeout adds one, a TxDone clears it |

Only a TxDone proves that the radio works. `watchdog_healthy` (`app_tx.c`) fails when the `air`
run exceeds `TX_FAIL_LIMIT` (10), so a radio that accepts sends but never finishes a frame leads to
a reset.

```c {#counts}
/* Transmission failures: a refused counter reservation, a refused Radio.Send or a
   TxTimeout; only a TxDone (the frame really left) clears the run. Before 2026-10-14 one run mixed
   these with journal appends, and every accepted Send reset it, so a radio that accepted Send but
   never finished a frame was never reset. */
static tx_counts_t tx_counts;
const tx_counts_t *exchange_counts(void) { return &tx_counts; }
```

## 4. Identity and key

`exchange_load_identity` loads the provisioning record from `node_store.c` once at boot. The key
stays in this file. Other modules see only the station id and the key check value through
`exchange_identity()`. A failed load leaves `provisioned` at 0.

```c {#identity}
/* Provisioning: the key never leaves this file (docs/power-of-ten.md, rule 6). */
static tx_identity_t identity;
static uint8_t key[WS_KEY_LEN];
int exchange_load_identity(void)
{
  identity.provisioned = store_config_load(&identity.station, key, identity.kcv) == 0;
  return identity.provisioned;
}
const tx_identity_t *exchange_identity(void) { return &identity; }
```

## 5. Events

### Receive buffer

The RxDone callback copies at most `WS_ACK_FRAME_LEN` (33) bytes. `rx_len` keeps the received
size, so `ws_open_reply` still rejects a longer packet by its length. `ack_rssi` and `ack_snr` keep
the signal of the last authentic reply for the health report. They start at `WS_SIGNAL_NONE`
(`INT8_MIN`).

```c {#rx-buffer}
/* Only a WS_ACK_FRAME_LEN reply is ever opened. rx_len keeps the true received size, so a longer
   packet is still rejected (ws_open_reply checks the length before reading) and logged as it was. */
static uint8_t rx_frame[WS_ACK_FRAME_LEN];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Signal of the last authentic ACK, as the node heard it (DIAG, design section 4): the uplink and
   downlink can differ. */
static int8_t ack_rssi = WS_SIGNAL_NONE, ack_snr = WS_SIGNAL_NONE;
```

### Event bits

Interrupt and timer callbacks post events as bits into `pending_ev` (`App/events.h`).
`events_post` sets bits with interrupts masked and schedules the process task. Several events can
therefore arrive before the task runs, and none is lost.

```c {#event-bits}
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
```

### Callbacks

Each callback only posts its bit. `on_rx_done` also copies the packet and its signal. ST's HAL
raises RxDone and then RxError for a packet whose payload CRC failed. `on_rx_done` asks
`ws_radio_take_crc_error()` and drops such a packet, so only its `EV_RX_ERROR` is posted.

```c {#callbacks}
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
```

### The process task

`process` takes all pending bits in one step and handles them lowest bit first. Before the loop it
applies two rules:

| Rule | Why |
|---|---|
| `EV_TX_DONE` and `EV_TX_TIMEOUT` in one batch: drop the timeout | the frame left. ST stops the timeout on TxDone, so a later one cannot come |
| bits outside `EV_ALL`: `WS_CHECK` fails, the bits are dropped | only `post()` sets bits, and only `EV_*` bits |

`batch` is a file variable, so a handler can remove a later bit from the current pass
(`window_closed`, section 7). `BUSYMON_TASK(process)` defines `process_timed`, which times each
pass (`busymon.h`). `exchange_init` registers `process_timed` with the sequencer.

```c {#process}
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
```

`handle` passes one event to the handler of the current state. A handler returns 1 if the state
expects the event, else 0. A 0 increments `unexpected` and prints
`#error unexpected event=<name> state=<name>`, and nothing else changes. `idle` expects no event.
An out-of-range `tx_state` fails a `WS_CHECK` and is reset to `TX_IDLE`.

```c {#dispatch}
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
```

## 6. Sending frames

### Start

`app_tx.c` calls `exchange_start` once per minute that may send.

| Step | Action |
|---|---|
| 1 | `WS_CHECK` that no exchange runs. If one does, return. `app_tx.c` holds the reading instead |
| 2 | clamp `backlog` to `MAX_QUEUE - 1` (20) with a `WS_CHECK` |
| 3 | queue the live reference first if `live` is not NULL |
| 4 | append the oldest pending records from `store_journal_oldest`, excluding `live`. Without a live reference the backlog may use its slot too |
| 5 | reset `qi`, the drain flag (`missed_last`) and `replied[]` |
| 6 | compute the exchange time limit |
| 7 | if the queue is not empty: record the start time and enter `gap` before the first frame. Else stay `idle` |

The exchange time limit assumes the worst case for every frame and the health report. Each uses its
full transmit timeout, its full ACK window and a gap:

```text
exchange_limit_s = (qn + 1) * (WS_TX_TIMEOUT_MS + ACK_WINDOW_MS + INTER_FRAME_MS) / 1000 + EXCHANGE_MARGIN_S
                 = (qn + 1) * 5050 ms / 1000 + 5 s
qn = 1:   15 s
qn = 21: 116 s
```

`exchange_overdue(now_s)` is true when the exchange is busy and more than `exchange_limit_s` has
passed since `exchange_start_s`. `watchdog_healthy` (`app_tx.c`) then calls `exchange_abort`
(section 9) and lets the watchdog reset the board.

The first frame also waits for the gap. The previous exchange may have put the radio to sleep in the
same main-loop pass. The chip needs time to enter sleep before the firmware wakes it.

```c {#exchange-start}
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
```

### Gap

`gap_before` records what the gap starts and enters `gap`. ST's `UTIL_TIMER_Start` refuses a timer
that is already running. That refusal fails a `WS_CHECK` but needs no other recovery: the running
timer still posts `EV_GAP`.

```c {#gap-before}
/* The next frame goes after INTER_FRAME_MS, from the gap timer: nothing waits meanwhile. */
static void gap_before(int then)
{
  gap_then = then; tx_state = TX_GAP;
  (void)WS_CHECK(UTIL_TIMER_Start(&gap_timer) == UTIL_TIMER_OK);   /* refused only if running: its EV_GAP still comes */
}
```

`in_gap` handles `EV_GAP`. For a frame it calls `send_current`. For the health report it calls
`send_diag`, and if the report did not go on air the exchange ends.

```c {#in-gap}
static int in_gap(uint32_t ev)
{
  if (ev != EV_GAP) return 0;
  if (gap_then == GAP_FRAME) send_current();
  else if (!send_diag()) radio_idle();
  return 1;
}
```

### Send the current item

`send_current` reads `queue[qi]` from the journal and checks its plaintext length. The results:

| Outcome | Print | Next |
|---|---|---|
| journal read or length check failed | `#error journal-read` | next item, after a gap |
| `send_obs` returns 1 | | `sending` |
| `send_obs` returns 0 (seal failed, radio refused) | its own `#error` | next item, after a gap |
| `send_obs` returns -1 (counter refused) | `#error counter-reserve` | the policy sees the replies so far, then `idle` at once (no health report: it needs a counter too) |

A local failure does not count as a missed reply and does not change the drain. The `WS_CHECK` on
`qi < qn` guards an index: the code calls `gap_before(GAP_FRAME)` only while an item is left.

```c {#send-current}
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
```

`send_obs` seals and sends one plaintext. Order of operations:

1. Reserve a counter with `store_next_counter`. On failure note a transmit failure and return -1.
   A frame without a durable counter could repeat a CCM nonce.
2. Seal with `ws_seal_kind`. A valid station and counter always seal, so a failure is a `WS_CHECK`
   failure and returns 0.
3. Record the counter, epoch and sequence that a reply must echo. Increment `sent`. Flash the blue
   LED.
4. `ws_radio_send`. Accepted: enter `sending`, return 1. Refused: note a transmit failure, print
   `#error radio-busy`, return 0.

The counter reservation can write flash. It runs in the gap state, while the radio is in standby
or asleep.

```c {#send-obs}
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
```

### Frame sent

`in_sending` waits for the radio. On TxDone it clears the transmit failure run, starts `ack_timer`
and listens with no driver timeout. On TxTimeout it puts the radio in standby, because the driver
leaves it transmitting. Then it notes a transmit failure, flashes red, prints `#error tx-timeout`
and stops the drain, so the exchange ends after this frame.

```c {#in-sending}
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
```

## 7. The ACK window

`in_ack_wait` handles the window:

| Event | Action |
|---|---|
| `EV_ACK_END` | radio to standby, then `no_reply` |
| `EV_RX_DONE`, `handle_reply` returns 1 | `window_closed`, then the next item |
| `EV_RX_DONE`, `handle_reply` returns 0 | listen again |
| `EV_RX_ERROR` | print `#ack damaged payload; still listening`, listen again |
| `EV_RX_TIMEOUT` | print `#ack damaged header; still listening`, listen again |

After a single reception the radio is in standby, so every "listen again" calls `ws_radio_rx(0)`.
The window keeps its original end. A damaged packet could be a damaged copy of the real ACK, and
the real one may still come.

```c {#in-ack-wait}
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
```

`window_closed` stops `ack_timer`. If the timer already fired, the code removes its `EV_ACK_END`
from the current `batch` and from `pending_ev`. That event is a race the reply already settled, so
it must not count as `unexpected`.

```c {#window-closed}
/* The reply ended the window: stop its timer, and drop an ack-end it already posted, in this pass
   or the next (a race, not a bug: `unexpected` stays a bug indicator). */
static void window_closed(void)
{
  (void)UTIL_TIMER_Stop(&ack_timer);
  batch &= ~EV_ACK_END;
  events_clear(&pending_ev, EV_ACK_END);
}
```

### Opening a reply

`handle_reply` opens `rx_frame` with `ws_open_reply`, which checks length, version, kind, station
and tag. A failure increments `ack_rejects`, flashes red, prints `#ack reject` and returns 0. An
authentic reply sets `ack_rssi` and `ack_snr`, clamped to -127..127, so a forged frame cannot set
them. The reply is "mine" when it echoes `sent_counter`, `sent_epoch` and `sent_seq`. The kind
selects `on_nack` or `on_ack`.

```c {#handle-reply}
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
```

`reply_t` holds the opened fields. `mark_replied` sets `replied[qi]` and clears the drain flag.

```c {#reply}
/* An authentic reply, opened. */
typedef struct { uint64_t ctr, echo; uint32_t epoch, seq, word; uint8_t kind; } reply_t;

/* The gateway answered the frame just sent (queue[qi]). */
static void mark_replied(void)
{
  if (WS_CHECK(qi < MAX_QUEUE)) replied[qi] = 1;
  missed_last = 0;
}
```

`on_ack` acts on any authentic ACK:

| Step | Applies to |
|---|---|
| find the record by (epoch, sequence) and acknowledge it in the journal (`#error journal-ack` on failure) | any ACK |
| `policy_strike_forget`: the record's strikes end | any ACK |
| `mark_replied` | mine only |
| `time_sync(word)`: set the clock from the ACK's time | mine only |
| increment `acked` if the record was found | any ACK |
| green LED, print `#ack ... found= time_sync= ...` | any ACK |

It returns `mine`. An ACK for another frame commits its record but keeps the window open, and a
replayed ACK cannot move the clock. `time_sync` returns 0 for an implausible time (`tx_time.h`).

```c {#on-ack}
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
```

`on_nack` accepts a NACK only for the frame just sent. Another NACK increments `ack_rejects`, prints
`#nack ignored: not for the frame just sent` and keeps the window open. An accepted NACK marks the
frame replied. If the search finds the record and its journal ACK succeeds, the abandoned total goes
up by one. The code ignores a total that fails to persist, because the journal acknowledges the
record either way. The red LED flashes for `LED_FLASH_LONG_MS` (1000 ms).

```c {#on-nack}
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
```

### No reply

`no_reply` runs when the window ends without a reply. It increments `no_ack`, flashes red, prints
`#ack none`, applies the drain rule and moves to the next item. The record stays journaled for a
later minute.

```c {#no-reply}
/* No reply to the frame just sent; it stays journaled for a later retry. */
static void no_reply(int flash_red)
{
  tx_counts.no_ack++;
  if (flash_red) led_flash(LED_RED, LED_FLASH_MS);
  APP_PRINTF("#ack none epoch=%u seq=%u\n", (unsigned)sent_epoch, (unsigned)sent_seq);
  drain_after_miss();
  next_item();
}
```

## 8. Drain and end of exchange

### Drain rule

A missed reply ends the minute's drain after `FRAMES_AFTER_MISS` (1) more frame. The one more frame
separates two cases for the strike rule (`ws_policy.h`):

| After a miss at `queue[qi]` | Meaning |
|---|---|
| the next frame is answered | the link works, so the gateway refused `queue[qi]`: it earns a strike |
| the next frame is missed too | the link is failing. The drain stops at once |

`drain_after_miss` implements this with `missed_last`, which `mark_replied` clears:

| `missed_last` | Action on a miss |
|---|---|
| 0 | cap `qn` at `qi + 1 + FRAMES_AFTER_MISS`, set `missed_last` |
| 1 | `stop_drain`: `qn = qi + 1`, so this frame is the last |

A TxTimeout also calls `stop_drain`. A failing link therefore does not use up the minute's backlog
allowance.

```c {#drain}
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
```

### Next item and end

`next_item` moves to the next queued frame after a gap, or ends the exchange. `finish_exchange`
passes `queue`, `replied` and `qn` to `policy_exchange_end`, which applies strikes and updates the
link state. Then it starts the gap before the health report if `policy_diag_due()`, else it makes
the radio idle.

```c {#finish}
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
```

## 9. Health report and idle

### Health report

The health report (kind 4, `WS_KIND_DIAG`) goes after the minute's exchange, also while the link
is probing, so its link field can say so. It has no journal entry and no ACK window. `clamp16`
saturates totals to the 16-bit fields. `clamp8` keeps a signal value in -127..127, because
`INT8_MIN` means "none".

```c {#clamps}
static uint16_t clamp16(uint32_t v) { return v > UINT16_MAX ? UINT16_MAX : (uint16_t)v; }
static int8_t clamp8(int v) { return (int8_t)(v < -INT8_MAX ? -INT8_MAX : v > INT8_MAX ? INT8_MAX : v); }  /* INT8_MIN means "none" */
```

`send_diag` fills a `ws_diag_t` from the node state, the journal and meta totals and `tx_counts`. It
adds the reset cause, the link state, the fault count, the energy state and the last ACK signal.

| Step | Failure |
|---|---|
| reserve a counter | note a transmit failure, return 0 |
| seal (`WS_CHECK`) | return 0 |
| `ws_radio_send` | note a transmit failure, return 0 |
| `policy_diag_sent(now)`: the report is no longer due | |
| enter `diag-sending`, print `#diag sent`, return 1 | |

A report that failed at any step stays due, so the next minute's exchange tries again.

A return of 0 ends the exchange (`in_gap`).

```c {#send-diag}
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
```

`in_diag_sending` ends the exchange on TxDone or TxTimeout. A TxTimeout puts the radio in standby
first and prints `#error tx-timeout`. Both note the transmit result, so a report that leaves clears
the failure run.

```c {#in-diag-sending}
static int in_diag_sending(uint32_t ev)
{
  if (ev != EV_TX_DONE && ev != EV_TX_TIMEOUT) return 0;
  if (ev == EV_TX_TIMEOUT) ws_radio_standby();
  ws_failrun_note(&tx_counts.air, ev == EV_TX_DONE);
  if (ev == EV_TX_TIMEOUT) { led_flash(LED_RED, LED_FLASH_MS); APP_PRINTF("#error tx-timeout\n"); }
  radio_idle();
  return 1;
}
```

### Idle

`radio_idle` ends the exchange: state `idle`, radio asleep, then `held_flush()` (`app_tx.c`). A
minute that ended while the exchange ran could not write flash, so `app_tx.c` held its reading in
RAM (at most `HELD_MAX`, 2). `held_flush` journals the held readings now, before anything else
runs, and the next minute sends them as backlog.

```c {#radio-idle}
/* The exchange (and any health report in flight) is over: the radio sleeps until the next minute,
   and a reading that a minute produced meanwhile is journaled now, first. */
static void radio_idle(void) { tx_state = TX_IDLE; ws_radio_sleep(); held_flush(); }
```

`exchange_abort` ends an exchange that outlasted its time limit. It stops both timers, puts the
radio in standby, enters `idle` and journals the held readings with the radio stopped. A watchdog
reset that follows then loses no reading.

```c {#abort}
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
```

The status accessors for `app_tx.c` and the console:

```c {#status}
int exchange_busy(void) { return tx_state != TX_IDLE; }
int exchange_overdue(uint32_t now_s) { return exchange_busy() && now_s - exchange_start_s > exchange_limit_s; }
const char *exchange_state_name(void) { return tx_state_name[tx_state]; }
```

## 10. Init

`exchange_init` runs once at boot:

1. Fill the radio callback table and call `Radio.Init`.
2. Configure the radio (`ws_radio_configure`) and put it to sleep.
3. Register `process_timed` as the sequencer task `CFG_SEQ_Task_SubGHz_Phy_App_Process`.
4. Create the gap timer (50 ms) and the ACK window timer (2000 ms), both one-shot.

```c {#init}
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
```

## 11. The file

The generated file orders the chunks for C. The order is: the summary, the includes, constants,
state, the event callbacks, then the functions, each after the functions it calls.

```c {#tx_exchange.c}
<<abstract>>
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

<<timing>>

<<build-id>>

<<states>>
<<gap-timer>>
<<ack-timer>>

<<queue>>
<<counts>>

<<identity>>

<<rx-buffer>>

<<event-bits>>

<<callbacks>>

<<status>>

<<radio-idle>>

<<abort>>

<<gap-before>>

<<clamps>>

<<send-diag>>

<<finish>>

<<drain>>

<<send-obs>>

<<send-current>>

<<exchange-start>>

<<no-reply>>

<<reply>>

<<on-nack>>

<<on-ack>>

<<handle-reply>>

<<window-closed>>

<<in-sending>>

<<in-ack-wait>>

<<in-diag-sending>>

<<in-gap>>

<<dispatch>>

<<process>>

<<init>>
```

## 12. Tests

`tests/test_tx_machine.py` builds the real `app_tx.c`, `tx_exchange.c` and the other TX modules
against `firmware/host/tx_harness.c`. The harness simulates the clock, ST's timers and sequencer, a
radio that follows ST's driver, the SHT45 and the flash under the real `node_store.c`. The test
build adds UBSan to the library. `TxUnderAddressSanitizer` reruns the suite under ASan where the
platform allows preloading its runtime. At its end, every test also checks four things. No flash
operation ran while the radio was busy, and the firmware started no running timer again. No radio
command ran without the radio interrupt masked, and no `WS_CHECK` failed.

| Area | Tests |
|---|---|
| exchange steps | `test_minute_exchange_then_health_report_after_a_gap`, `test_no_reply_closes_the_window_by_its_own_timeout`, `test_backlog_frames_follow_the_live_one_after_timer_gaps`, `test_every_frame_gets_its_own_full_window` |
| damaged packets, radio timeouts | `test_stray_and_damaged_packets_keep_the_rest_of_the_window`, `test_a_damaged_reply_does_not_end_the_window_early`, `test_a_transmit_timeout_puts_the_stuck_radio_in_standby` |
| events together or unexpected | `test_two_events_before_the_main_loop_are_both_handled_in_bit_order`, `test_every_unlisted_state_event_pair_is_only_counted`, `test_a_failed_check_is_counted_reported_and_recovered` |
| whose reply it is | `test_an_authentic_ack_for_another_frame_keeps_the_window_open`, `test_a_nack_for_another_frame_is_ignored`, `test_a_nack_for_this_frame_abandons_the_record`, `test_only_an_ack_for_the_frame_just_sent_sets_the_clock` |
| flash with the radio idle | `test_counter_reservations_never_meet_a_busy_radio`, `test_flash_commands_wait_for_the_radio_exchange` |
| drain and failures | `test_a_missed_reply_allows_one_more_frame_then_stops_the_drain`, `test_after_a_miss_only_one_more_frame_goes_even_if_it_is_answered`, `test_a_transmit_timeout_stops_the_drain`, `test_a_send_failure_on_a_backlog_frame_moves_on`, `test_a_failed_health_report_ends_the_exchange`, `test_a_health_report_that_leaves_clears_the_transmit_failure_run`, `test_transmit_failures_in_a_row_trip_the_watchdog_and_a_tx_done_clears_them` |
| time limit, held readings | `test_a_radio_that_never_finishes_trips_the_exchange_bound`, `test_a_reading_made_during_an_exchange_is_journaled_when_the_radio_goes_idle`, `test_held_readings_keep_the_newest_when_more_minutes_wait` |
| policy | `test_three_silent_minutes_mean_probing_with_no_backlog_until_a_reply`, `test_a_health_report_at_least_every_15_minutes`, `test_strikes_need_an_answer_after_the_missed_record`, `test_a_lone_refused_record_is_retried_never_abandoned_by_luck`, `test_no_strikes_while_nothing_is_answered` |
| randomized | `test_three_hours_of_mixed_link_keep_every_invariant`: 3 h with 5 seeds of lost ACKs, NACKs, junk, CRC and header failures, another frame's ACK, transmit timeouts and refused sends. The radio state must match the exchange state at every step, and no event may be unexpected |

```sh
.venv/bin/python -m unittest tests.test_tx_machine tests.test_tangle
```
