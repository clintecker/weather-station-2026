/* Host harness for the RX bridge's event-driven firmware (App/app_rx.c, App/console.c and
 * common/ws_console.c, compiled unchanged; built with -DHOST_RADIO_GETSTATUS).
 *
 * The board is replaced by a deterministic simulation (tests/test_rx_machine.py drives it through
 * ctypes):
 *  - a virtual clock in 1/1024 s RTC ticks. SysTimeGetMcuTime() is ST's TIMER_IF_GetTime (seconds =
 *    ticks >> 10, milliseconds = sub-ticks * 1000 >> 10); HAL_GetTick() counts ticks, as on the board.
 *  - ST's timer server: a period is rounded down to whole ticks, at least 3 (timer_if.c);
 *    UTIL_TIMER_Start on a timer that is already running does nothing; a periodic timer restarts
 *    after its callback, from the time the callback ran.
 *  - the sequencer: interrupt callbacks (timers, radio, UART) run, then the main loop runs every
 *    posted task to completion, unless the test holds the main loop back to see what an interrupt
 *    alone does.
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
 *  - the watchdog: watchdog_start's 1 s check timer posts the check task, which calls the health test
 *    and refreshes the IWDG; 8 s without a refresh is a reset (counted).
 * Checked throughout: interrupts are never left masked by a task, and the main loop settles. */
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console.h"
#include "fault.h"
#include "leds.h"
#include "radio.h"
#include "radio_cfg.h"
#include "stackmon.h"
#include "stm32_seq.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "usart_if.h"
#include "utilities_conf.h"
#include "utilities_def.h"
#include "watchdog.h"
#include "ws_frame.h"
#include "ws_obs.h"

#define TX_AIR_MS 20U   /* a 33-byte ACK at SF7/500 kHz is ~15 ms on air */

/* ---- clock (1/1024 s ticks), CMSIS ---- */
static uint64_t now_ticks;
static uint64_t virt_ms;   /* the test's clock in ms; now_ticks = virt_ms * 1024 / 1000 between events */
DWT_Type host_dwt;
CoreDebug_Type host_coredebug;
uint32_t SystemCoreClock = 48000000U;
uint32_t host_primask;
volatile uint32_t ws_trace_drops;
static uint32_t ms2tick(uint32_t ms) { return (uint32_t)(((uint64_t)ms << 10) / 1000U); }   /* timer_if.c */
static uint64_t ms_to_ticks(uint64_t ms) { return ms * 1024U / 1000U; }
uint32_t HAL_GetTick(void) { return (uint32_t)now_ticks; }   /* ticks, not ms, as on the board */
void NVIC_SystemReset(void) { abort(); }
SysTime_t SysTimeGetMcuTime(void)
{
  return (SysTime_t){ .Seconds = (uint32_t)(now_ticks >> 10), .SubSeconds = (int16_t)(((now_ticks & 1023U) * 1000U) >> 10) };
}
SysTime_t SysTimeGet(void) { return SysTimeGetMcuTime(); }
void SysTimeSet(SysTime_t t) { (void)t; }

/* ---- console output: 640-byte line buffer, 2 KB FIFO drained at 115200 baud ---- */
static char out[1 << 20];
static size_t out_len;
static uint32_t fifo_used, overlong_lines, capture_overflow;
void host_printf(const char *fmt, ...)
{
  char line[UTIL_ADV_TRACE_TMP_BUF_SIZE];
  va_list ap; va_start(ap, fmt);
  int n = vsnprintf(line, sizeof line, fmt, ap);
  va_end(ap);
  if (n < 0) { ws_trace_drops++; return; }
  if ((size_t)n >= sizeof line) { overlong_lines++; n = (int)sizeof line - 1; }   /* cut, as on the board */
  if (fifo_used + (uint32_t)n > UTIL_ADV_TRACE_FIFO_SIZE) { ws_trace_drops++; return; }
  fifo_used += (uint32_t)n;
  if (out_len + (size_t)n >= sizeof out) { capture_overflow++; return; }
  memcpy(out + out_len, line, (size_t)n);
  out_len += (size_t)n;
}
static void drain_fifo(uint64_t ticks)
{
  uint64_t bytes = ticks * 11520U / 1024U;   /* 115200 baud, 8N1 */
  fifo_used = bytes >= fifo_used ? 0 : fifo_used - (uint32_t)bytes;
}

/* ---- timer server (ST semantics), times in ticks ---- */
static UTIL_TIMER_Object_t *timers;
static uint32_t now32(void) { return (uint32_t)now_ticks; }
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg)
{
  int known = 0;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next) known |= p == t;
  t->period = period; t->mode = mode; t->cb = cb; t->arg = arg; t->running = 0;
  if (!known) { t->next = timers; timers = t; }
  return 0;
}
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t)
{
  if (t->running) return 0;   /* ST: a timer already in the list is not restarted */
  uint32_t ticks = ms2tick(t->period);
  if (ticks < 3) ticks = 3;
  t->running = 1; t->due = now32() + ticks;
  return 0;
}
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t) { t->running = 0; return 0; }
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period) { t->period = period; return 0; }

/* ---- sequencer ---- */
static void (*tasks[32])(void);
static uint32_t task_pending, task_saturations, primask_leaks, task_runs;
static jmp_buf fault_jump;
static int fault_tests;
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*task)(void)) { (void)flags; tasks[__builtin_ctz(mask)] = task; }
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio) { (void)prio; task_pending |= mask; }
static void run_tasks(void)
{
  if (fault_tests) return;   /* the board is resetting */
  if (setjmp(fault_jump)) return;
  for (int guard = 0; task_pending; guard++)
  {
    if (guard > 1000) { task_saturations++; return; }
    int id = __builtin_ctz(task_pending);
    task_pending &= ~(1U << id);
    if (tasks[id]) { tasks[id](); task_runs++; }
    if (host_primask) { primask_leaks++; host_primask = 0; }
  }
}

/* ---- radio ---- */
static RadioEvents_t *radio_events;
static RadioState_t radio_state = RF_IDLE;
static int continuous = -1, tx_mode, send_fails, rx_ignored, crc_flag;
static uint32_t rx_calls, standby_calls, sleep_calls, send_calls, sends_ok, last_rx_timeout;
static int chip_tx_pending;            /* TxDone due at chip_tx_due */
static uint32_t chip_tx_due;
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
  if ((radio_state == RF_RX_RUNNING && s != RF_RX_RUNNING) || s == RF_TX_RUNNING) not_rx_since = now_ticks;
  if (radio_state != RF_RX_RUNNING && s == RF_RX_RUNNING && now_ticks - not_rx_since > max_not_rx_ticks)
    max_not_rx_ticks = now_ticks - not_rx_since;
  radio_state = s;
}
static void on_tx_timeout_timer(void *arg) { (void)arg; timed_out_in_tx = 1; radio_events->TxTimeout(); }   /* the chip is still transmitting */
static void radio_init(RadioEvents_t *e)
{
  radio_events = e;
  UTIL_TIMER_Create(&tx_timeout_timer, WS_TX_TIMEOUT_MS, UTIL_TIMER_ONESHOT, on_tx_timeout_timer, NULL);
}
static radio_status_t radio_send(uint8_t *buf, uint8_t size)
{
  send_calls++;
  if (send_fails > 0) { send_fails--; return RADIO_STATUS_ERROR; }
  if (radio_state == RF_TX_RUNNING) sends_while_tx++;
  pkt_len = size;
  timed_out_in_tx = 0;
  memcpy(last_sent, buf, size); last_sent_len = size; sends_ok++;
  set_state(RF_TX_RUNNING);
  chip_tx_pending = tx_mode == 0; chip_tx_due = now32() + (uint32_t)ms_to_ticks(TX_AIR_MS) + 1U;
  UTIL_TIMER_Stop(&tx_timeout_timer);
  if (tx_mode != 2) UTIL_TIMER_Start(&tx_timeout_timer);   /* mode 2: not even the driver's timer fires */
  return RADIO_STATUS_OK;
}
static void radio_rx(uint32_t timeout)
{
  rx_calls++; last_rx_timeout = timeout;
  if (timed_out_in_tx) rx_after_timeout_no_standby++;
  timed_out_in_tx = 0;
  if (rx_ignored) return;
  chip_tx_pending = 0; UTIL_TIMER_Stop(&tx_timeout_timer);
  set_state(RF_RX_RUNNING);
}
static void radio_sleep(void) { sleep_calls++; chip_tx_pending = 0; UTIL_TIMER_Stop(&tx_timeout_timer); set_state(RF_IDLE); }
static void radio_standby(void) { standby_calls++; timed_out_in_tx = 0; chip_tx_pending = 0; UTIL_TIMER_Stop(&tx_timeout_timer); set_state(RF_IDLE); }
static RadioState_t radio_get_status(void) { return radio_state; }
const struct Radio_s Radio = { radio_init, radio_send, radio_rx, radio_sleep, radio_standby, radio_get_status };
int ws_radio_take_crc_error(void) { int f = crc_flag; crc_flag = 0; return f; }
void ws_radio_configure(int c) { continuous = c; pkt_len = 255; }
void ws_radio_sleep(void) { radio_sleep(); }
void ws_radio_last_packet(uint8_t buf[255], uint8_t *len, int8_t *rssi, int8_t *snr)
{
  memcpy(buf, chip_buf, chip_len); *len = chip_len; *rssi = chip_rssi; *snr = chip_snr;
}
int8_t ws_radio_rssi_now(void) { return rssi_now; }

/* ---- console UART ---- */
static void (*uart_cb)(uint8_t *, uint16_t, uint8_t);
static int uart_armed, uart_rearm_fails;
static uint32_t uart_errors, uart_lost, uart_rearms;
UTIL_ADV_TRACE_Status_t vcom_ReceiveInit(void (*cb)(uint8_t *, uint16_t, uint8_t)) { uart_cb = cb; uart_armed = 1; return UTIL_ADV_TRACE_OK; }
uint32_t vcom_rx_errors(void) { return uart_errors; }
int vcom_rx_armed(void) { return uart_armed; }
void vcom_rx_rearm(void) { uart_rearms++; if (!uart_rearm_fails) uart_armed = 1; }

/* ---- board stubs ---- */
static uint32_t led_flashes[3];
void leds_init(void) {}
void led_flash(led_t led, uint32_t ms) { (void)ms; led_flashes[led]++; }
void led_set(led_t led, int on) { (void)led; (void)on; }
void fault_report(void) {}
uint32_t fault_count(void) { return 0; }
void fault_test(void) { fault_tests++; longjmp(fault_jump, 1); }   /* the board records a HardFault and resets */
void stackmon_paint(void) {}
uint32_t stackmon_peak(void) { return 0; }

/* ---- watchdog: 1 s check timer -> check task -> health test -> refresh; 8 s unrefreshed = reset ---- */
static int (*healthy_fn)(void);
static UTIL_TIMER_Object_t wd_timer;
static uint64_t wd_refreshed;
static uint32_t wd_resets, wd_unhealthy, wd_checks;
static void wd_check(void)
{
  wd_checks++;
  if (healthy_fn()) wd_refreshed = now_ticks; else wd_unhealthy++;
}
static void wd_request(void *arg) { (void)arg; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Watchdog, CFG_SEQ_Prio_0); }
void watchdog_start(int (*healthy)(void))
{
  healthy_fn = healthy;
  wd_refreshed = now_ticks;
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Watchdog, UTIL_SEQ_RFU, wd_check);
  UTIL_TIMER_Create(&wd_timer, 1000, UTIL_TIMER_PERIODIC, wd_request, NULL);
  UTIL_TIMER_Start(&wd_timer);
}
ws_reset_t watchdog_reset_code(void) { return WS_RESET_POWER; }
const char *watchdog_reset_cause(void) { return "power"; }

/* ---- the event loop ---- */
static UTIL_TIMER_Object_t *next_timer(void)
{
  UTIL_TIMER_Object_t *best = NULL;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next)
    if (p->running && (!best || (int32_t)(p->due - best->due) < 0)) best = p;
  return best;
}
static void move_to(uint64_t t)
{
  drain_fifo(t - now_ticks);
  now_ticks = t;
  if (now_ticks - wd_refreshed > 8U * 1024U) { wd_resets++; wd_refreshed = now_ticks; }   /* IWDG: 4000 / 500 Hz */
}

/* Move the clock forward ms, raising every timer and radio interrupt due on the way; after each,
   the main loop runs its tasks unless run == 0 (a main loop held back). */
void h_advance(uint32_t ms, int run)
{
  uint64_t target_ms = virt_ms + ms, until = ms_to_ticks(target_ms);
  if (run) run_tasks();
  for (;;)
  {
    UTIL_TIMER_Object_t *t = next_timer();
    int chip_first = chip_tx_pending && (!t || (int32_t)(chip_tx_due - t->due) <= 0);
    if (!chip_first && !t) break;
    uint32_t due = chip_first ? chip_tx_due : t->due;
    uint64_t at = now_ticks + (uint32_t)(due - now32());
    if ((int32_t)(due - now32()) < 0) at = now_ticks;
    if (at > until) break;
    move_to(at);
    if (chip_first)
    {
      chip_tx_pending = 0;
      UTIL_TIMER_Stop(&tx_timeout_timer);
      set_state(RF_IDLE);           /* ST: standby after TX_DONE */
      radio_events->TxDone();
    }
    else
    {
      t->running = 0;
      t->cb(t->arg);
      if (t->mode == UTIL_TIMER_PERIODIC) UTIL_TIMER_Start(t);   /* ST restarts it after the callback */
    }
    if (run) run_tasks();
  }
  move_to(until);
  virt_ms = target_ms;
  if (run) run_tasks();
}
void h_poll(void) { run_tasks(); }

/* ---- the API tests/test_rx_machine.py uses ---- */
void h_boot(uint32_t start_s)
{
  virt_ms = (uint64_t)start_s * 1000U; now_ticks = ms_to_ticks(virt_ms); not_rx_since = now_ticks;
  SubghzApp_Init();
  run_tasks();
}
uint64_t h_now_ms(void) { return virt_ms; }
uint64_t h_now_ticks(void) { return now_ticks; }
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
  uint64_t gap = max_not_rx_ticks;
  if (radio_state != RF_RX_RUNNING && now_ticks - not_rx_since > gap) gap = now_ticks - not_rx_since;
  return (uint32_t)(gap * 1000U / 1024U);
}

/* Radio interrupts. Each returns 1 if the packet was received, 0 if the radio was not receiving. The
   main loop does not run: the test calls h_poll (several interrupts can come first). */
static int receiving(void) { return radio_state == RF_RX_RUNNING; }
static void deliver(const uint8_t *frame, int len, int rssi, int snr)
{
  memcpy(rx_scratch, frame, (size_t)len);
  radio_events->RxDone(rx_scratch, (uint16_t)len, (int16_t)rssi, (int8_t)snr);
  memset(rx_scratch, 0xEE, sizeof rx_scratch);   /* the radio's buffer is reused for the next packet */
}
int h_rx(const uint8_t *frame, int len, int rssi, int snr)
{
  if (!receiving()) return 0;
  memcpy(chip_buf, frame, (size_t)len); chip_len = (uint8_t)len; chip_rssi = (int8_t)rssi; chip_snr = (int8_t)snr;
  deliver(frame, len, rssi, snr);
  return 1;
}
int h_rx_crc(const uint8_t *frame, int len, int rssi, int snr)
{
  if (!receiving()) return 0;
  memcpy(chip_buf, frame, (size_t)len); chip_len = (uint8_t)len; chip_rssi = (int8_t)rssi; chip_snr = (int8_t)snr;
  crc_flag = 1;
  deliver(frame, len, rssi, snr);
  radio_events->RxError();
  return 1;
}
int h_rx_error_only(const uint8_t *frame, int len, int rssi, int snr)   /* RxError with no RxDone before it */
{
  if (!receiving()) return 0;
  memcpy(chip_buf, frame, (size_t)len); chip_len = (uint8_t)len; chip_rssi = (int8_t)rssi; chip_snr = (int8_t)snr;
  radio_events->RxError();
  return 1;
}
int h_rx_hdr(int rssi)
{
  if (!receiving()) return 0;
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
    if (run_each) run_tasks();
  }
  return taken;
}
void h_uart_error(void) { uart_errors++; }   /* counted; the HAL error callback re-arms at once */
void h_uart_deaf(void) { uart_armed = 0; }   /* the receive was aborted and not re-armed */
void h_uart_rearm_fails(int on) { uart_rearm_fails = on; }
int h_uart_armed(void) { return uart_armed; }
uint32_t h_uart_rearms(void) { return uart_rearms; }

/* Console output since the last call (NUL-terminated, valid until the next call). */
const char *h_output(void)
{
  static char copy[sizeof out + 1];
  memcpy(copy, out, out_len); copy[out_len] = 0; out_len = 0;
  return copy;
}
int h_healthy(void) { return healthy_fn(); }
uint32_t h_wd_resets(void) { return wd_resets; }
uint32_t h_wd_unhealthy(void) { return wd_unhealthy; }
uint32_t h_wd_checks(void) { return wd_checks; }
uint32_t h_trace_drops(void) { return ws_trace_drops; }
uint32_t h_overlong(void) { return overlong_lines; }
uint32_t h_capture_overflow(void) { return capture_overflow; }
uint32_t h_primask_leaks(void) { return primask_leaks; }
uint32_t h_task_saturations(void) { return task_saturations; }
uint32_t h_task_pending(void) { return task_pending; }
uint32_t h_task_runs(void) { return task_runs; }
uint32_t h_led_flashes(int led) { return led_flashes[led]; }
int h_fault_tests(void) { return fault_tests; }
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
