/* Host harness for the RX bridge's event-driven firmware (App/app_rx.c, App/console.c and
 * common/ws_console.c, compiled unchanged; built with -DHOST_RADIO_GETSTATUS).
 *
 * The board is firmware/host/sim_core.c (see there): a clock in 1/1024 s RTC ticks with ST's timer
 * server (periods rounded down to whole ticks, at least 3), the sequencer, the watchdog's 1 s check
 * timer and 8 s IWDG (a reset is counted), and the event loop. tests/test_rx_machine.py drives it
 * through ctypes; h_advance(ms, 0) holds the main loop back to see what interrupts alone do. This
 * file adds the bridge's devices:
 *  - the radio as ST's SubGHz_Phy drives it in continuous receive (radio.c, stm32wlxx_hal_subghz.c):
 *    a packet is RxDone and the radio keeps receiving; a payload CRC failure is RxDone with the HAL's
 *    CRC flag set (ws_radio_take_crc_error() returns 1 once) followed by RxError in the same
 *    interrupt; a header failure is RxTimeout; the radio stays in receive after both. Send switches to
 *    transmit: TxDone after the air time (the radio is then idle), or the driver's TxTimeoutTimer after
 *    WS_TX_TIMEOUT_MS if the chip never finishes (the radio is still transmitting). GetStatus is the
 *    driver's operating mode. A packet is only received while the radio is receiving.
 *  - the USB console UART: vcom_ReceiveInit registers the per-character callback; characters are
 *    delivered from "interrupt context" while the one-character receive is armed and lost otherwise.
 *  - APP_PRINTF: each line is formatted into the 640-byte trace line buffer (a longer one is cut, as
 *    on the board, and counted here) and queued in the 2 KB trace FIFO, which the UART drains at
 *    115200 baud; a line that does not fit is dropped and counted in ws_trace_drops.
 * Checked throughout: interrupts are never left masked by a task, and the main loop settles. */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "console.h"
#include "radio.h"
#include "radio_cfg.h"
#include "sim_core.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "usart_if.h"
#include "utilities_conf.h"
#include "ws_frame.h"
#include "ws_obs.h"

#define TX_AIR_MS 20U   /* a 33-byte ACK at SF7/500 kHz is ~15 ms on air */

static const sim_source chip_source;
static void drain_fifo(uint64_t from, uint64_t to);
const sim_config sim_cfg = { .name = "rx_harness", .sources = (const sim_source *const[]){ &chip_source, NULL },
                             .on_time = drain_fifo, .watchdog_periodic = 1, .reset_fatal = 1 };

/* ---- console output: 640-byte line buffer, 2 KB FIFO drained at 115200 baud ---- */
static uint32_t fifo_used, overlong_lines, capture_overflow;
static int vprint(const char *fmt, va_list ap)
{
  char line[UTIL_ADV_TRACE_TMP_BUF_SIZE];
  int n = vsnprintf(line, sizeof line, fmt, ap);
  if (n < 0) { ws_trace_drops++; return 0; }
  if ((size_t)n >= sizeof line) { overlong_lines++; n = (int)sizeof line - 1; }   /* cut, as on the board */
  if (fifo_used + (uint32_t)n > UTIL_ADV_TRACE_FIFO_SIZE) { ws_trace_drops++; return 0; }
  fifo_used += (uint32_t)n;
  if (!sim_capture(line, (size_t)n)) capture_overflow++;
  return 1;
}
void host_printf(const char *fmt, ...) { va_list ap; va_start(ap, fmt); vprint(fmt, ap); va_end(ap); }
int host_print_ok(const char *fmt, ...) { va_list ap; va_start(ap, fmt); int ok = vprint(fmt, ap); va_end(ap); return ok; }
static void drain_fifo(uint64_t from, uint64_t to)
{
  uint64_t bytes = (to / SIM_UNITS_PER_TICK - from / SIM_UNITS_PER_TICK) * 11520U / 1024U;   /* 115200 baud, 8N1 */
  fifo_used = bytes >= fifo_used ? 0 : fifo_used - (uint32_t)bytes;
}

/* ---- radio ---- */
static RadioEvents_t *radio_events;
static RadioState_t radio_state = RF_IDLE;
static int continuous = -1, tx_mode, send_fails, rx_ignored, crc_flag;
static uint32_t rx_calls, standby_calls, sleep_calls, send_calls, sends_ok, last_rx_timeout;
static int chip_tx_pending;            /* TxDone due at chip_tx_due */
static uint64_t chip_tx_due;
static UTIL_TIMER_Object_t tx_timeout_timer;   /* ST's TxTimeoutTimer (radio.c) */
static uint8_t last_sent[256], chip_buf[256], chip_len;
static int last_sent_len;
static int8_t chip_rssi = -110, chip_snr = -15, rssi_now = -120;
static uint8_t rx_scratch[256];        /* the radio's buffer as RxDone passes it */
/* Observations for the review findings: a Send while the chip still transmits (it is cut short), an
   Rx straight after a TxTimeout with no Standby first (the chip is still in TX), and the LoRa packet
   length parameter: ST's RadioSend sets it to the frame size and RadioRx does not restore it. */
static uint32_t sends_while_tx, rx_after_timeout_no_standby;
static int timed_out_in_tx, pkt_len = -1;
/* How long the radio stays out of receive after whatever last took it out (a Send restarts the
   count: a second transmission is the host's doing, not a radio that failed to come back). */
static uint64_t not_rx_since, max_not_rx_ticks;
static void set_state(RadioState_t s)
{
  uint64_t now = sim_ticks();
  if ((radio_state == RF_RX_RUNNING && s != RF_RX_RUNNING) || s == RF_TX_RUNNING) not_rx_since = now;
  if (radio_state != RF_RX_RUNNING && s == RF_RX_RUNNING && now - not_rx_since > max_not_rx_ticks)
    max_not_rx_ticks = now - not_rx_since;
  radio_state = s;
}
static void on_tx_timeout_timer(void *arg) { (void)arg; timed_out_in_tx = 1; radio_events->TxTimeout(); }   /* the chip is still transmitting */
static void radio_init(RadioEvents_t *e)
{
  radio_events = e;
  UTIL_TIMER_Create(&tx_timeout_timer, WS_TX_TIMEOUT_MS, UTIL_TIMER_ONESHOT, on_tx_timeout_timer, NULL);
}
static radio_status_t radio_send(uint8_t *buf, uint8_t size)
{ sim_radio_command();
  send_calls++;
  if (send_fails > 0) { send_fails--; return RADIO_STATUS_ERROR; }
  if (radio_state == RF_TX_RUNNING) sends_while_tx++;
  pkt_len = size;
  timed_out_in_tx = 0;
  memcpy(last_sent, buf, size); last_sent_len = size; sends_ok++;
  set_state(RF_TX_RUNNING);
  chip_tx_pending = tx_mode == 0;
  chip_tx_due = (sim_ticks() + sim_ms_to_ticks(TX_AIR_MS) + 1U) * SIM_UNITS_PER_TICK;
  UTIL_TIMER_Stop(&tx_timeout_timer);
  if (tx_mode != 2) UTIL_TIMER_Start(&tx_timeout_timer);   /* mode 2: not even the driver's timer fires */
  return RADIO_STATUS_OK;
}
static void chip_idle(void) { chip_tx_pending = 0; UTIL_TIMER_Stop(&tx_timeout_timer); }
static void radio_rx(uint32_t timeout)
{ sim_radio_command();
  rx_calls++; last_rx_timeout = timeout;
  if (timed_out_in_tx) rx_after_timeout_no_standby++;
  timed_out_in_tx = 0;
  if (rx_ignored) return;
  chip_idle();
  set_state(RF_RX_RUNNING);
}
static void radio_sleep(void) { sim_radio_command(); sleep_calls++; chip_idle(); set_state(RF_IDLE); }
static void radio_standby(void) { sim_radio_command(); standby_calls++; timed_out_in_tx = 0; chip_idle(); set_state(RF_IDLE); }
static RadioState_t radio_get_status(void) { return radio_state; }
const struct Radio_s Radio = { radio_init, radio_send, radio_rx, radio_sleep, radio_standby, radio_get_status };
int ws_radio_take_crc_error(void) { int f = crc_flag; crc_flag = 0; return f; }
void ws_radio_configure(int c) { continuous = c; pkt_len = 255; }
void ws_radio_rx_full_length(void) { pkt_len = 255; }
void ws_radio_sleep(void) { ws_radio_irq_hold(); radio_sleep(); ws_radio_irq_release(); }
void ws_radio_last_packet(uint8_t buf[255], uint8_t *len, int8_t *rssi, int8_t *snr)
{
  memcpy(buf, chip_buf, chip_len); *len = chip_len; *rssi = chip_rssi; *snr = chip_snr;
}
int8_t ws_radio_rssi_now(void) { return rssi_now; }
/* The chip's TxDone interrupt, the air time after a Send. */
static int chip_pending(uint64_t *at) { *at = chip_tx_due; return chip_tx_pending; }
static void chip_fire(void)
{
  chip_idle();
  set_state(RF_IDLE);           /* ST: standby after TX_DONE */
  radio_events->TxDone();
}
static const sim_source chip_source = { chip_pending, chip_fire, SIM_IRQ_SUBGHZ };

/* Trace DMA progress: transfers finish unless a test stalls them (h_tx_stall). */
static int tx_stalled;
static uint32_t tx_started_n, tx_done_n;
void vcom_tx_progress(uint32_t *started, uint32_t *done)
{
  if (!tx_stalled) tx_done_n = tx_started_n;
  *started = tx_started_n; *done = tx_done_n;
}

/* ---- console UART ---- */
static void (*uart_cb)(uint8_t *, uint16_t, uint8_t);
static int uart_armed, uart_rearm_fails;
static uint32_t uart_errors, uart_lost, uart_rearms;
UTIL_ADV_TRACE_Status_t vcom_ReceiveInit(void (*cb)(uint8_t *, uint16_t, uint8_t)) { uart_cb = cb; uart_armed = 1; return UTIL_ADV_TRACE_OK; }
uint32_t vcom_rx_errors(void) { return uart_errors; }
int vcom_rx_armed(void) { return uart_armed; }
void vcom_rx_rearm(void) { uart_rearms++; if (!uart_rearm_fails) uart_armed = 1; }

/* ---- the API tests/test_rx_machine.py uses ---- */
/* Move the clock forward ms, raising every timer and radio interrupt due on the way; after each,
   the main loop runs its tasks unless run == 0 (a main loop held back). */
void h_advance(uint32_t ms, int run) { sim_set_hold(!run); sim_advance(ms); sim_set_hold(0); }
void h_poll(void) { sim_run_tasks(); }
void h_boot(uint32_t start_s)
{
  sim_set_ms((uint64_t)start_s * 1000U); not_rx_since = sim_ticks();
  SubghzApp_Init();
  sim_run_tasks();
}
uint64_t h_now_ms(void) { return sim_ms(); }
uint64_t h_now_ticks(void) { return sim_ticks(); }
int h_radio_state(void) { return radio_state; }
int h_continuous(void) { return continuous; }
uint32_t h_rx_calls(void) { return rx_calls; }
uint32_t h_standby_calls(void) { return standby_calls; }
uint32_t h_sleep_calls(void) { return sleep_calls; }
uint32_t h_send_calls(void) { return send_calls; }
uint32_t h_sends(void) { return sends_ok; }
uint32_t h_last_rx_timeout(void) { return last_rx_timeout; }
uint32_t h_sends_while_tx(void) { return sends_while_tx; }
uint32_t h_rx_after_timeout_no_standby(void) { return rx_after_timeout_no_standby; }
int h_pkt_len(void) { return pkt_len; }
int h_last_sent(uint8_t *buf) { memcpy(buf, last_sent, (size_t)last_sent_len); return last_sent_len; }
void h_tx_mode(int mode) { tx_mode = mode; }   /* 0 TxDone after the air time, 1 chip stuck (TxTimeout), 2 nothing */
void h_send_fails(int n) { send_fails = n; }
void h_rx_ignored(int on) { rx_ignored = on; }
void h_radio_force_idle(void) { set_state(RF_IDLE); }
uint32_t h_max_not_rx_ms(void)
{
  uint64_t gap = max_not_rx_ticks, now = sim_ticks();
  if (radio_state != RF_RX_RUNNING && now - not_rx_since > gap) gap = now - not_rx_since;
  return (uint32_t)(gap * 1000U / 1024U);
}

/* Radio interrupts. Each returns 1 if the packet was received, 0 if the radio was not receiving. The
   main loop does not run: the test calls h_poll (several interrupts can come first). */
static int latch(const uint8_t *frame, int len, int rssi, int snr)   /* the packet into the chip's buffer */
{
  if (radio_state != RF_RX_RUNNING) return 0;
  memcpy(chip_buf, frame, (size_t)len); chip_len = (uint8_t)len; chip_rssi = (int8_t)rssi; chip_snr = (int8_t)snr;
  return 1;
}
static void deliver(const uint8_t *frame, int len, int rssi, int snr)
{
  memcpy(rx_scratch, frame, (size_t)len);
  radio_events->RxDone(rx_scratch, (uint16_t)len, (int16_t)rssi, (int8_t)snr);
  memset(rx_scratch, 0xEE, sizeof rx_scratch);   /* the radio's buffer is reused for the next packet */
}
int h_rx(const uint8_t *frame, int len, int rssi, int snr)
{
  if (!latch(frame, len, rssi, snr)) return 0;
  deliver(frame, len, rssi, snr);
  return 1;
}
int h_rx_crc(const uint8_t *frame, int len, int rssi, int snr)
{
  if (!latch(frame, len, rssi, snr)) return 0;
  crc_flag = 1;
  deliver(frame, len, rssi, snr);
  radio_events->RxError();
  return 1;
}
int h_rx_error_only(const uint8_t *frame, int len, int rssi, int snr)   /* RxError with no RxDone before it */
{
  if (!latch(frame, len, rssi, snr)) return 0;
  radio_events->RxError();
  return 1;
}
int h_rx_hdr(int rssi)
{
  if (radio_state != RF_RX_RUNNING) return 0;
  rssi_now = (int8_t)rssi;
  radio_events->RxTimeout();
  return 1;
}

/* UART receive interrupts, one per character; run_each: the main loop keeps up between characters. */
int h_uart(const uint8_t *data, int n, int run_each)
{
  int taken = 0;
  for (int i = 0; i < n; i++)
  {
    if (!uart_armed || !uart_cb) { uart_lost++; continue; }
    uint8_t c = data[i];
    uart_cb(&c, 1, 0);
    taken++;
    if (run_each) sim_run_tasks();
  }
  return taken;
}
/* A receive error, as the board's HAL_UART_ErrorCallback reports it (usart_if.c): counted, the line
   in progress discarded through the callback's error flag, the receive re-armed at once. */
void h_uart_error(void) { uint8_t c = 0; uart_errors++; if (uart_cb) uart_cb(&c, 0, 1); }
void h_uart_deaf(void) { uart_armed = 0; }   /* the receive was aborted and not re-armed */
void h_uart_rearm_fails(int on) { uart_rearm_fails = on; }
int h_uart_armed(void) { return uart_armed; }
uint32_t h_uart_rearms(void) { return uart_rearms; }

void h_tx_stall(int on) { tx_stalled = on; if (on) tx_started_n++; }
uint32_t h_overlong(void) { return overlong_lines; }
uint32_t h_capture_overflow(void) { return capture_overflow; }
int h_const(int which)
{
  switch (which)
  {
  case 0: return WS_FRAME_OVERHEAD + WS_OBS_HEAD_LEN + 1;   /* shortest observation */
  case 1: return WS_FRAME_OVERHEAD + WS_OBS_PLAIN_ALL;      /* longest observation */
  case 2: return WS_DIAG_FRAME_LEN;
  case 3: return WS_ACK_FRAME_LEN;
  case 4: return WS_LINE_MAX;
  case 5: return WS_FRAME_VERSION;
  default: return -1;
  }
}
