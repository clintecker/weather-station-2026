/* GENERATED from app_rx.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/app_rx.lit.md (tests/test_tangle.py checks this file). */
/* Indoor receiver (RX): a transparent bridge between the radio and the USB console.
 *
 * Upstream: each received frame that ws_air_frame_ok() accepts goes out as one lowercase hex
 * line. It accepts an observation or a health report of the current version and a valid length.
 * Downstream: each host hex line that ws_host_reply_ok() accepts is transmitted once. It accepts
 * an ACK or a NACK of the current version. The ACK uses the uplink's radio_cfg.h power, spreading
 * factor and bandwidth, so the downlink has the same margin as the uplink. This board holds no
 * key and never acknowledges a frame itself. The host is the only ACK authority (docs/protocol.md).
 * Each other output line starts with '#' and is a diagnostic for the host log. The bridge also
 * logs a failed reception. `#rx crc ... data=<hex>` keeps every received byte when only the
 * payload CRC failed. `#rx hdr rssi=` reports a failed header, which has no payload. */
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
static uint8_t rx_frame[WS_FRAME_MAX];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Radio events from interrupt context, as bits (App/events.h). Several can arrive before process()
 * runs, and the bits keep each one. A lost TxDone once left `transmitting` set until a reset. */
#define EV_RX         (1U << 0)
#define EV_RX_CRC     (1U << 1)
#define EV_TX_DONE    (1U << 2)
#define EV_TX_TIMEOUT (1U << 3)
#define EV_RX_HDR     (1U << 4)
static volatile uint32_t pending_ev;
static volatile uint8_t transmitting;
static uint32_t n_forwarded, n_dropped, n_acks;
static uint32_t n_frames_lost, n_frames_lost_told;   /* valid frames replaced before forwarding */
static uint32_t tx_start_ms;
static UTIL_TIMER_Object_t alive_timer;
static uint32_t n_diag;
static uint32_t boot_ms;   /* clock_ms() at boot (App/clock.h) */
static int relisten_tries;
/* Radio.GetStatus() reports the driver's own state, not the chip's state. Only a radio event (a
 * frame, a failed reception, a header error) shows that the radio listens. By design a node is
 * silent for at most 15 minutes (PROBING in CONSERVE, docs/radio-energy-policy.md). So 16 silent
 * minutes means a fault: the bridge puts the radio in standby and listens again. If no radio event
 * follows, the bridge does not trust the radio. After QUIET_RELISTEN_LIMIT relistens in a row with
 * no radio event, the health check fails and the watchdog resets the board. The bridge holds no
 * state, so a reset loses nothing. */
#define SILENCE_RELISTEN_MS  (16UL * CLOCK_MS_PER_MIN)
#define QUIET_RELISTEN_LIMIT 2U
#define TX_STALL_CHECKS      3U   /* watchdog health checks with console output stalled */
#define ALIVE_PERIOD_MS      CLOCK_MS_PER_MIN
#define TX_HEALTH_MS         (WS_TX_TIMEOUT_MS + 2UL * CLOCK_MS_PER_S)   /* an ACK on air for longer is stuck */
static volatile uint32_t last_radio_event_ms;
static volatile uint32_t quiet_relistens;   /* relistens since the last radio event (each radio event clears it) */
static uint32_t n_relistens;
static volatile uint8_t relisten_due, alive_due;
static void alive(void);
static int uart_rearm_tries;
static uint32_t tx_stall_checks;
static uint32_t tx_done_seen;
/* At most this many failure lines (#rx crc, #rx hdr) per minute. A noisy band must not push frames
   out of the console. Over the budget, the bridge counts a failure (fault_overruns) and logs nothing. */
#define FAILURE_LINES_PER_MIN 20U
static uint32_t failure_lines;
static void post(uint32_t ev) { events_post(&pending_ev, ev); }
static uint8_t bad_frame[WS_FRAME_MAX];
static uint8_t bad_len;
static int8_t bad_rssi, bad_snr, hdr_rssi;
static uint32_t n_crc, n_hdr, n_fault_overrun;
static void capture_crc(const uint8_t *payload, uint16_t size, int8_t rssi, int8_t snr);
static uint8_t crc_in_done;   /* RxError for this packet follows its RxDone in this interrupt */
/* cppcheck-suppress constParameterCallback ; ST's RadioEvents_t RxDone signature */
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;
  /* ST's HAL also calls RxDone for a packet whose payload CRC failed. That packet is a failed
     reception and is never forwarded (stm32wlxx_hal_subghz.c HAL_SUBGHZ_IRQHandler). */
  if (ws_radio_take_crc_error()) { crc_in_done = 1; capture_crc(payload, size, (int8_t)rssi, snr); return; }
  if (pending_ev & EV_RX) n_frames_lost++;   /* this frame replaces one not yet forwarded */
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX);
}
/* Failed receptions, from the radio interrupt. A payload CRC failure arrives as RxDone with the
   bytes and the HAL's flag, then as RxError. on_rx_done captures it. Continuous receive never arms
   the hardware receive timer, so RxTimeout is not a timeout. ST's radio.c reports a header error
   as RxTimeout. One capture stays
   until process() prints it. Later failures are counted in n_fault_overrun, not captured. The
   radio stays in continuous receive through both (radio.c), so no callback re-arms it. */
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
  if (crc_in_done) { crc_in_done = 0; return; }   /* on_rx_done captured this packet */
  /* An RxError without an RxDone before it: read the packet that the radio kept. */
  uint8_t len; int8_t rssi, snr;
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;
  if (pending_ev & EV_RX_CRC) { n_crc++; n_fault_overrun++; return; }
  ws_radio_last_packet(bad_frame, &len, &rssi, &snr);
  n_crc++; bad_len = len; bad_rssi = rssi; bad_snr = snr;
  post(EV_RX_CRC);
}
static void on_rx_timeout(void)
{
  last_radio_event_ms = clock_ms(); quiet_relistens = 0;   /* a header error shows that the radio listens */
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
  ws_radio_rx_full_length();   /* Radio.Send left the LoRa payload length at the ACK's length */
  ws_radio_rx(0); /* continuous */
}

/* Watchdog health: the radio must listen, or finish a transmission within 5 s. Each fault gets
 * one repair attempt (re-arm) before the watchdog may reset the board. */
int watchdog_healthy(void)
{
  /* The console must receive, because it carries the ACK downlink. Re-arm it once first. */
  if (!vcom_rx_armed())
  {
    if (uart_rearm_tries++ == 0) { APP_PRINTF("#watchdog console not receiving; re-arming\n"); vcom_rx_rearm(); return 1; }
    return 0;
  }
  uart_rearm_tries = 0;
  /* Stalled console output stops frames and #alive alike (a trace DMA transfer that never ended).
     No progress for TX_STALL_CHECKS checks, 1 s apart, makes the board unhealthy. */
  uint32_t started, done;
  vcom_tx_progress(&started, &done);
  if (started != done && done == tx_done_seen) { if (++tx_stall_checks >= TX_STALL_CHECKS) return 0; }
  else tx_stall_checks = 0;
  tx_done_seen = done;
  if (quiet_relistens >= QUIET_RELISTEN_LIMIT) return 0;
  if (transmitting) return clock_ms() - tx_start_ms < TX_HEALTH_MS;
  if (Radio.GetStatus() == RF_RX_RUNNING) { relisten_tries = 0; return 1; }
  if (relisten_tries++ == 0) { APP_PRINTF("#watchdog radio not listening; re-arming\n"); listen(); return 1; }
  return 0;
}

/* Radio silence: put the radio in standby, listen again, and count the relisten. The health check
   fails after QUIET_RELISTEN_LIMIT relistens in a row with no radio event between them. */
static void relisten(void)
{
  relisten_due = 0;
  n_relistens++;
  quiet_relistens++;
  APP_PRINTF("#relisten after %u s without a radio event\n", (unsigned)((clock_ms() - last_radio_event_ms) / CLOCK_MS_PER_S));
  ws_radio_standby();
  listen();
  last_radio_event_ms = clock_ms();   /* the next silence starts here, and the quiet count stays */
  if (quiet_relistens >= QUIET_RELISTEN_LIMIT) APP_PRINTF("#watchdog radio silent after %u relistens; reset\n", (unsigned)quiet_relistens);
}

/* What process() took from the interrupts. Static, because it holds two 255-byte frames. */
static struct {
  uint8_t frame[sizeof rx_frame], bad[sizeof bad_frame];
  uint16_t len; int16_t rssi; int8_t snr;
  uint8_t blen; int8_t brssi, bsnr, hrssi;
} got;

/* Take the pending events and the received frames in one step, with interrupts masked. A second
   RxDone then cannot tear the frame during forwarding. The next pass handles the second frame. */
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

/* The transmission of the host's ACK ended. The driver's transmit timeout is a software timer,
   so the chip can still be transmitting. */
static void tx_ended(uint32_t ev)
{
  if (ev & EV_TX_TIMEOUT) { APP_PRINTF("#tx timeout\n"); led_flash(LED_RED, LED_FLASH_MS); ws_radio_standby(); }
  listen();
}

static void forward(void)
{
  if (!ws_air_frame_ok(got.frame, got.len))
  {
    n_dropped++;
    led_flash(LED_RED, LED_FLASH_MS);
    APP_PRINTF("#rx drop len=%u rssi=%d snr=%d\n", got.len, got.rssi, got.snr);
    return;
  }
  n_diag += ws_frame_kind(got.frame, got.len) == WS_KIND_DIAG;
  led_flash(LED_BLUE, LED_FLASH_MS);
  if (hex_print(got.frame, got.len)) n_forwarded++;   /* a line that the full queue dropped is not forwarded */
  APP_PRINTF("#rx obs rssi=%d snr=%d\n", got.rssi, got.snr);
}

/* 1 within this minute's budget of failure lines. Over the budget, count the failure only. */
static int failure_line_ok(void)
{
  if (failure_lines++ < FAILURE_LINES_PER_MIN) return 1;
  n_fault_overrun++;
  return 0;
}

static void log_crc(void)
{
  static char text[WS_HEX_PER_BYTE * sizeof bad_frame + 1];
  if (!failure_line_ok()) return;
  ws_hex_text(got.bad, got.blen, text);
  APP_PRINTF("#rx crc len=%u rssi=%d snr=%d data=%s\n", got.blen, got.brssi, got.bsnr, text);
}

/* busymon times each step on its own, so the task's peak names the step that caused it. */
static void process(void)
{
  bm_span s;
  if (alive_due) { alive_due = 0; s = busymon_begin(); alive(); busymon_step_end(s, "process.alive"); }   /* can set relisten_due */
  if (relisten_due && !transmitting) { s = busymon_begin(); relisten(); busymon_step_end(s, "process.relisten"); }
  uint32_t ev = take_events();
  if (ev & (EV_TX_DONE | EV_TX_TIMEOUT)) { s = busymon_begin(); tx_ended(ev); busymon_step_end(s, "process.listen"); }
  if (ev & EV_RX) { s = busymon_begin(); forward(); busymon_step_end(s, "process.forward"); }
  if (ev & EV_RX_CRC) { s = busymon_begin(); log_crc(); busymon_step_end(s, "process.crc"); }
  if ((ev & EV_RX_HDR) && failure_line_ok()) APP_PRINTF("#rx hdr rssi=%d\n", got.hrssi);
  if (n_frames_lost != n_frames_lost_told)   /* real data loss: report it now, not only in #alive */
  {
    n_frames_lost_told = n_frames_lost;
    APP_PRINTF("#rx frame-lost total=%u (a valid frame replaced before it was forwarded)\n", (unsigned)n_frames_lost);
  }
}
BUSYMON_TASK(process)

/* Liveness report for the gateway, which marks the receiver silent after 180 s. The main loop
   prints it. The timer interrupt only asks for it. */
static void alive(void)
{
  APP_PRINTF("#alive uptime=%u forwarded=%u dropped=%u acks=%u diag=%u listening=%d relistens=%u uart_errors=%u stack_peak=%u "
             "crc_errors=%u hdr_errors=%u fault_overruns=%u task_peak_us=%u task_peak=%s isr_peak_us=%u isr_peak=%s trace_drops=%u "
             "frames_lost=%u\n",
             (unsigned)((clock_ms() - boot_ms) / CLOCK_MS_PER_S), (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks,
             (unsigned)n_diag, Radio.GetStatus() == RF_RX_RUNNING || transmitting, (unsigned)n_relistens,
             (unsigned)vcom_rx_errors(), (unsigned)stackmon_peak_step(), (unsigned)n_crc, (unsigned)n_hdr, (unsigned)n_fault_overrun,
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

/* cppcheck-suppress constParameterPointer ; console.h's signature: TX wipes a PROVISION line in place */
void console_line(char *line)
{
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  static const char *const commands[] = { "STATUS" };
  if (line[0] == '#') return;
  bench_command(line);   /* TEST-FAULT, TEST-HANG (not in a field build) */
  if (ws_cmd_find(commands, 1, line) == 0)
  {
    uint16_t site = ws_check_first();
    APP_PRINTF("#status role=rx forwarded=%u dropped=%u acks=%u relistens=%u uart_errors=%u check_fails=%u check_first=%u:%u "
               "task_wall_us=%u task_wall=%s\n",
               (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks, (unsigned)n_relistens, (unsigned)vcom_rx_errors(),
               (unsigned)ws_check_count(), ws_check_site_file(site), ws_check_site_line(site),
               (unsigned)busymon_peak_us(BM_TASK_WALL), busymon_peak_name(BM_TASK_WALL));
    return;
  }
  int n = ws_hex_decode(line, frame, sizeof frame);
  if (!ws_host_reply_ok(frame, n))
  {
    APP_PRINTF("#host reject len=%d\n", n);
    led_flash(LED_RED, LED_FLASH_MS);
    return;
  }
  /* One ACK on air at a time. The first ACK's TxDone re-arms the receiver and would cut a second
     ACK short. The node retries a frame that got no ACK. */
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
  led_flash(LED_GREEN, LED_FLASH_MS);
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
  /* After console_init: vcom_ReceiveInit waits until the UART is idle. A host that streams
     without gaps could make that wait longer than the watchdog period. */
  watchdog_start();
  /* A leading newline ends any line that a reset cut off, so #boot starts on a new line. */
  APP_PRINTF("\n#boot role=rx fw=%s reset=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION, watchdog_reset_cause(),
             (unsigned)WS_RF_FREQUENCY_HZ, (unsigned)WS_LORA_BANDWIDTH, (unsigned)WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  (void)UTIL_TIMER_Create(&alive_timer, ALIVE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_alive, NULL);
  (void)WS_CHECK(UTIL_TIMER_Start(&alive_timer) == UTIL_TIMER_OK);   /* created just above, so not running */
  listen();
  stackmon_seed();
}
