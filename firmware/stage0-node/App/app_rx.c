/* Stage-0 RX: transparent radio <-> USB bridge for the indoor receiver.
 *
 * Upstream: every received frame that ws_air_frame_ok() accepts (a current-version observation or
 * health report of a valid length) is written as one lowercase hex line. Downstream: every hex
 * line from the host that ws_host_reply_ok() accepts (a current-version ACK or NACK) is
 * transmitted once. The ACK path
 * uses the same radio_cfg.h power/SF/BW as the uplink (gap G15). This board holds no key and
 * never acknowledges anything itself; the host is the sole ACK authority (docs/protocol.md).
 * All other output lines start with '#' and are diagnostics for the host log. A reception that
 * fails its checks is logged too: `#rx crc ... data=<hex>` keeps every byte the radio received
 * when only the payload CRC failed; `#rx hdr rssi=` is a header that failed (no payload). */
#define WS_CHECK_FILE 7
#include <string.h>
#include "bench.h"
#include "busymon.h"
#include "clock.h"
#include "console.h"
#include "events.h"
#include "leds.h"
#include "stm32wlxx_hal.h"
#include "watchdog.h"
#include "radio.h"
#include "radio_cfg.h"
#include "stage0.h"
#include "usart_if.h"
#include "stackmon.h"
#include "fault.h"
#include "stm32_seq.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"
#include "ws_check.h"
#include "ws_frame.h"

static RadioEvents_t events;
static uint8_t rx_frame[255];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Radio events from interrupt context, as bits (App/events.h): several can arrive before process()
 * runs, and none is lost (a lost TxDone once left `transmitting` set until the watchdog reset). */
#define EV_RX         (1U << 0)
#define EV_RX_CRC     (1U << 1)
#define EV_TX_DONE    (1U << 2)
#define EV_TX_TIMEOUT (1U << 3)
#define EV_RX_HDR     (1U << 4)
static volatile uint32_t pending_ev;
static volatile uint8_t transmitting;
static uint32_t n_forwarded, n_dropped, n_acks;
static uint32_t n_frames_lost, n_frames_lost_told;   /* valid frames replaced before they were forwarded */
static uint32_t tx_start_ms;
static UTIL_TIMER_Object_t alive_timer;
static uint32_t n_diag;
static uint32_t boot_ms;   /* clock_ms() at boot (App/clock.h) */
static int relisten_tries;
/* Review P6: Radio.GetStatus() reports the driver's own state, not the chip's. Real evidence of
 * listening is a radio event (a frame, a failed reception, a header error). The node is silent at
 * most 15 minutes by design (PROBING in CONSERVE, docs/radio-energy-policy.md), so 16 silent minutes
 * means something is wrong: put the radio in standby and listen again. If that does not bring back
 * a single radio event, the radio is not trusted: after QUIET_RELISTEN_LIMIT relistens in a row
 * with none, the health check fails and the watchdog resets the board (2026-10-15 review M1; the
 * bridge holds no state, so a reset costs nothing). */
#define SILENCE_RELISTEN_MS  (16UL * 60000UL)
#define QUIET_RELISTEN_LIMIT 2U
#define TX_HEALTH_MS         (WS_TX_TIMEOUT_MS + 2000UL)   /* an ACK on air longer than this is stuck */
static volatile uint32_t last_radio_event_ms;
static volatile uint32_t quiet_relistens;   /* relistens since the last radio event (any interrupt clears it) */
static uint32_t n_relistens;
static volatile uint8_t relisten_due, alive_due;
static void alive(void);
static int uart_rearm_tries, tx_stall_checks;
static uint32_t tx_done_seen;
/* Failure lines (#rx crc / #rx hdr) per minute at most: a noisy band must not crowd frames out of the
   console (2026-10-15 review m10). Over budget, a failure is counted (fault_overruns), not logged. */
#define FAILURE_LINES_PER_MIN 20U
static uint32_t failure_lines;
static void post(uint32_t ev) { events_post(&pending_ev, ev); }
static uint8_t bad_frame[255];
static uint8_t bad_len;
static int8_t bad_rssi, bad_snr, hdr_rssi;
static uint32_t n_crc, n_hdr, n_fault_overrun;
static void capture_crc(const uint8_t *payload, uint16_t size, int8_t rssi, int8_t snr);
static uint8_t crc_in_done;   /* this packet's RxError follows its RxDone in the same interrupt */
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;
  /* ST's HAL also raises RxDone for a packet whose payload CRC failed: that one is a failed
     reception, never forwarded (stm32wlxx_hal_subghz.c HAL_SUBGHZ_IRQHandler). */
  if (ws_radio_take_crc_error()) { crc_in_done = 1; capture_crc(payload, size, (int8_t)rssi, snr); return; }
  if (pending_ev & EV_RX) n_frames_lost++;   /* a valid frame not yet forwarded is replaced */
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX);
}
/* Failed receptions, from the radio interrupt. (RxTimeout in continuous receive is a header error;
   ST's radio.c would also call it for a hardware RX timeout, which continuous receive never arms.) A payload CRC failure arrives as RxDone (bytes
   included, flagged by the HAL) and then RxError; on_rx_done captures it. RxTimeout cannot be a
   timeout in continuous receive: ST's radio.c reports a header error that way. One capture is kept
   until process() prints it; failures meanwhile are counted, not captured (n_fault_overrun). The
   radio stays in continuous receive through both (radio.c), so nothing re-arms it. */
static void capture_crc(const uint8_t *payload, uint16_t size, int8_t rssi, int8_t snr)
{
  n_crc++;
  if (pending_ev & EV_RX_CRC) { n_fault_overrun++; return; }
  bad_len = (uint8_t)(size > sizeof bad_frame ? sizeof bad_frame : size);
  memcpy(bad_frame, payload, bad_len);
  bad_rssi = rssi; bad_snr = snr;
  post(EV_RX_CRC);
}
static void on_rx_error(void)
{
  if (crc_in_done) { crc_in_done = 0; return; }   /* already captured by on_rx_done */
  /* An RxError without the RxDone before it: read what the radio kept. */
  uint8_t len; int8_t rssi, snr;
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;
  if (pending_ev & EV_RX_CRC) { n_crc++; n_fault_overrun++; return; }
  ws_radio_last_packet(bad_frame, &len, &rssi, &snr);
  n_crc++; bad_len = len; bad_rssi = rssi; bad_snr = snr;
  post(EV_RX_CRC);
}
static void on_rx_timeout(void)
{
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;   /* a header error is evidence the radio is listening */
  n_hdr++;
  if (pending_ev & EV_RX_HDR) { n_fault_overrun++; return; }
  hdr_rssi = ws_radio_rssi_now();   /* the channel right after the failed header */
  post(EV_RX_HDR);
}
static void on_tx_done(void) { post(EV_TX_DONE); }
static void on_tx_timeout(void) { post(EV_TX_TIMEOUT); }

static void listen(void)
{
  transmitting = 0;
  ws_radio_rx_full_length();   /* Radio.Send left the LoRa payload length at the ACK's (review m4) */
  ws_radio_rx(0); /* continuous */
}

/* Watchdog health: the radio must really be listening, or finish a transmission within 5 s.
 * One self-heal attempt (re-arm RX) before the watchdog is allowed to reset the board. */
int watchdog_healthy(void)
{
  /* Review P5: the console must be receiving (it carries the ACK downlink). One re-arm first. */
  if (!vcom_rx_armed())
  {
    if (uart_rearm_tries++ == 0) { APP_PRINTF("#watchdog console not receiving; re-arming\n"); vcom_rx_rearm(); return 1; }
    return 0;
  }
  uart_rearm_tries = 0;
  /* Review m9: console output that stopped moving (a trace DMA transfer started and never finished)
     silences frames and #alive alike. Three checks (3 s) without progress: unhealthy. */
  uint32_t started, done;
  vcom_tx_progress(&started, &done);
  if (started != done && done == tx_done_seen) { if (++tx_stall_checks >= 3) return 0; }
  else tx_stall_checks = 0;
  tx_done_seen = done;
  if (quiet_relistens >= QUIET_RELISTEN_LIMIT) return 0;
  if (transmitting) return clock_ms() - tx_start_ms < TX_HEALTH_MS;
  if (Radio.GetStatus() == RF_RX_RUNNING) { relisten_tries = 0; return 1; }
  if (relisten_tries++ == 0) { APP_PRINTF("#watchdog radio not listening; re-arming\n"); listen(); return 1; }
  return 0;
}

/* Radio silence (review P6): standby, listen again, and count it; the health check fails after
   QUIET_RELISTEN_LIMIT of these in a row with no radio event between them. */
static void relisten(void)
{
  relisten_due = 0;
  n_relistens++;
  quiet_relistens++;
  APP_PRINTF("#relisten after %u s without a radio event\n", (unsigned)((clock_ms() - last_radio_event_ms) / 1000));
  ws_radio_standby();
  listen();
  last_radio_event_ms = clock_ms();   /* the next silence is measured from here, the quiet count kept */
  if (quiet_relistens >= QUIET_RELISTEN_LIMIT) APP_PRINTF("#watchdog radio silent after %u relistens; reset\n", (unsigned)quiet_relistens);
}

/* What process() took from the interrupts (static: two 255-byte frames). */
static struct {
  uint8_t frame[sizeof rx_frame], bad[sizeof bad_frame];
  uint16_t len; int16_t rssi; int8_t snr;
  uint8_t blen; int8_t brssi, bsnr, hrssi;
} got;

/* Take the pending events and the received frames in one step with interrupts masked, so a
   second RxDone cannot tear the frame while it is forwarded (it is handled on the next pass). */
static uint32_t take_events(void)
{
  uint32_t primask = irq_lock();
  uint32_t ev = pending_ev;
  pending_ev = 0;
  if (ev & EV_RX) { got.len = rx_len; memcpy(got.frame, rx_frame, got.len); got.rssi = rx_rssi; got.snr = rx_snr; }
  if (ev & EV_RX_CRC) { got.blen = bad_len; memcpy(got.bad, bad_frame, got.blen); got.brssi = bad_rssi; got.bsnr = bad_snr; }
  got.hrssi = hdr_rssi;
  irq_unlock(primask);
  return ev;
}

/* The host ACK's transmission ended. The driver's TX timeout is a software timer: the chip may
   still be transmitting (review m3). */
static void tx_ended(uint32_t ev)
{
  if (ev & EV_TX_TIMEOUT) { APP_PRINTF("#tx timeout\n"); led_flash(LED_RED, 400); ws_radio_standby(); }
  listen();
}

static void forward(void)
{
  if (!ws_air_frame_ok(got.frame, got.len))
  {
    n_dropped++;
    led_flash(LED_RED, 400);
    APP_PRINTF("#rx drop len=%u rssi=%d snr=%d\n", got.len, got.rssi, got.snr);
    return;
  }
  n_diag += ws_frame_kind(got.frame, got.len) == WS_KIND_DIAG;
  led_flash(LED_BLUE, 400);
  if (hex_print(got.frame, got.len)) n_forwarded++;   /* a line the full console queue dropped is not forwarded (m10) */
  APP_PRINTF("#rx obs rssi=%d snr=%d\n", got.rssi, got.snr);
}

/* Within this minute's budget of failure lines; over it, the failure is only counted. */
static int failure_line_ok(void)
{
  if (failure_lines++ < FAILURE_LINES_PER_MIN) return 1;
  n_fault_overrun++;
  return 0;
}

static void log_crc(void)
{
  static char text[2 * sizeof bad_frame + 1];
  if (!failure_line_ok()) return;
  ws_hex_text(got.bad, got.blen, text);
  APP_PRINTF("#rx crc len=%u rssi=%d snr=%d data=%s\n", got.blen, got.brssi, got.bsnr, text);
}

static void process(void)
{
  if (alive_due) { alive_due = 0; alive(); }   /* may set relisten_due, handled just below */
  if (relisten_due && !transmitting) relisten();
  uint32_t ev = take_events();
  if (ev & (EV_TX_DONE | EV_TX_TIMEOUT)) tx_ended(ev);
  if (ev & EV_RX) forward();
  if (ev & EV_RX_CRC) log_crc();
  if ((ev & EV_RX_HDR) && failure_line_ok()) APP_PRINTF("#rx hdr rssi=%d\n", got.hrssi);
  if (n_frames_lost != n_frames_lost_told)   /* real data loss: told at once, not only on #alive */
  {
    n_frames_lost_told = n_frames_lost;
    APP_PRINTF("#rx frame-lost total=%u (a valid frame replaced before it was forwarded)\n", (unsigned)n_frames_lost);
  }
}
BUSYMON_TASK(process)

/* Liveness report for the gateway (gap G12): it marks the receiver silent after 180 s. Printed
   from the main loop: the timer interrupt only asks for it. */
static void alive(void)
{
  APP_PRINTF("#alive uptime=%u forwarded=%u dropped=%u acks=%u diag=%u listening=%d relistens=%u uart_errors=%u stack_peak=%u "
             "crc_errors=%u hdr_errors=%u fault_overruns=%u task_peak_us=%u task_peak=%s isr_peak_us=%u isr_peak=%s trace_drops=%u "
             "frames_lost=%u\n",
             (unsigned)((clock_ms() - boot_ms) / 1000), (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks,
             (unsigned)n_diag, Radio.GetStatus() == RF_RX_RUNNING || transmitting, (unsigned)n_relistens,
             (unsigned)vcom_rx_errors(), (unsigned)stackmon_peak(), (unsigned)n_crc, (unsigned)n_hdr, (unsigned)n_fault_overrun,
             (unsigned)busymon_peak_us(BM_TASK), busymon_peak_name(BM_TASK), (unsigned)busymon_peak_us(BM_ISR),
             busymon_peak_name(BM_ISR), (unsigned)ws_trace_drops, (unsigned)n_frames_lost);
  failure_lines = 0;
  if (!transmitting && ws_silent_for(clock_ms(), last_radio_event_ms, SILENCE_RELISTEN_MS)) relisten_due = 1;
}
static void on_alive(void *ctx)
{
  (void)ctx;
  alive_due = 1;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0);
}

void console_line(char *line)
{
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  static const char *const commands[] = { "STATUS" };
  if (line[0] == '#') return;
  bench_command(line);   /* TEST-FAULT, TEST-HANG (not in a field build) */
  if (ws_cmd_find(commands, 1, line) == 0)
  {
    uint16_t site = ws_check_first();
    APP_PRINTF("#status role=rx forwarded=%u dropped=%u acks=%u relistens=%u uart_errors=%u check_fails=%u check_first=%u:%u\n",
               (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks, (unsigned)n_relistens, (unsigned)vcom_rx_errors(),
               (unsigned)ws_check_count(), WS_CHECK_FILE_OF(site), WS_CHECK_LINE(site));
    return;
  }
  int n = ws_hex_decode(line, frame, sizeof frame);
  if (!ws_host_reply_ok(frame, n))
  {
    APP_PRINTF("#host reject len=%d\n", n);
    led_flash(LED_RED, 400);
    return;
  }
  /* One ACK on air at a time: a second would be cut short when the first one's TxDone re-arms the
     receiver (review m1). The node retries a frame it got no ACK for. */
  if (transmitting) { APP_PRINTF("#tx busy\n"); return; }
  transmitting = 1;
  tx_start_ms = clock_ms();
  if (ws_radio_send(frame, WS_ACK_FRAME_LEN) != RADIO_STATUS_OK)
  {
    APP_PRINTF("#tx busy\n");
    listen();
    return;
  }
  n_acks++;
  led_flash(LED_GREEN, 400);
}

void SubghzApp_Init(void)
{
  stackmon_paint();
  busymon_init();
  events.RxDone = on_rx_done;
  events.RxError = on_rx_error;
  events.RxTimeout = on_rx_timeout;
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  boot_ms = clock_ms();
  last_radio_event_ms = boot_ms;
  leds_init();
  Radio.Init(&events);
  ws_radio_configure(1);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process_timed);
  console_init();
  /* After console_init: vcom_ReceiveInit waits for the UART to be idle, which a host streaming
     without gaps could stretch past the watchdog (review m13). */
  watchdog_start();
  /* A leading newline ends any line a reset cut off, so the host sees #boot on a line of its own (m7). */
  APP_PRINTF("\n#boot role=rx fw=%s reset=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION, watchdog_reset_cause(),
             (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  (void)UTIL_TIMER_Create(&alive_timer, 60000, UTIL_TIMER_PERIODIC, on_alive, NULL);
  (void)WS_CHECK(UTIL_TIMER_Start(&alive_timer) == UTIL_TIMER_OK);   /* created just above, so not running */
  listen();
}
