/* Host harness for the TX node's event-driven firmware (App/app_tx.c, compiled unchanged).
 *
 * The board is replaced by a deterministic simulation (tests/test_tx_machine.py drives it through
 * ctypes): a virtual millisecond clock, the UTIL_TIMER server, the UTIL_SEQ sequencer, a radio
 * that finishes a transmission after TX_AIR_MS and times out a receive window on its own, the
 * SHT45 (a measurement ends 10 ms after it starts, with a result the test chooses; App/sensor.c
 * itself is tested by firmware/host/sensor_harness.c), and the flash (firmware/sim_flash.c under
 * the real App/node_store.c).
 *
 * The radio follows ST's SubGHz_Phy (radio.c, stm32wlxx_hal_subghz.c), as the 2026-10-15 reviews
 * read it, not an idealised radio:
 *  - Rx(t > 0) arms the driver's software timer: its timeout calls RxTimeout and leaves the radio
 *    RECEIVING; a CRC error does not stop that timer. Rx(0) in single mode: the chip's own ~65 s
 *    timeout, which puts it in standby.
 *  - A payload CRC failure is RxDone (bytes, CRC flag set in the HAL) then RxError, in one interrupt;
 *    single mode then standby. A header failure is RxTimeout (standby, timer stopped).
 *  - The transmit timeout is a software timer too: TxTimeout leaves the radio TRANSMITTING. Interrupt callbacks (timers, radio)
 * run first, then the sequencer runs every pending task to completion, as on the chip.
 *
 * Timers and sequencer follow ST's Utilities too: starting a running timer is refused and does not
 * restart it; tasks run round robin, highest bit first. h_hold holds the main loop off, so a test can
 * have several interrupts post before process() runs; h_fire_timer raises a timer event in a state
 * that does not expect it; h_burn moves the next durable counter reservation; h_radio_hang makes a
 * transmission that never ends.
 *
 * Checked on every step, not just at the end of a test:
 *  - no flash program or erase while the radio is transmitting or receiving (the CPU stalls
 *    for a flash erase; the firmware must schedule it with the radio idle);
 *  - no blocking: the clock only moves between tasks, never inside one (a task that waits
 *    for time would hang here, and the harness cannot provide HAL_Delay at all). */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "flash_layout.h"
#include "leds.h"
#include "node_store.h"
#include "radio.h"
#include "radio_cfg.h"
#include "rtc.h"
#include "sensor.h"
#include "sim_flash.h"
#include "stackmon.h"
#include "fault.h"
#include "console.h"
#include "watchdog.h"
#include "stm32_seq.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"

#define TX_AIR_MS 30U   /* an observation frame at SF7/500 kHz is ~30 ms on air */

/* ---- clock, CMSIS, RTC ---- */
static uint32_t now_ms;
static uint32_t utc_offset;   /* SysTimeGet = MCU seconds + offset */
DWT_Type host_dwt;
CoreDebug_Type host_coredebug;
uint32_t SystemCoreClock = 48000000U;
uint32_t host_primask;
RTC_HandleTypeDef hrtc;
static uint32_t bkp[RTC_BKP_COUNT];
static int resets;
volatile uint32_t ws_trace_drops;
volatile uint8_t ws_flash_ecc_fault;

/* Like the target: HAL_GetTick counts 1/1024 s RTC ticks, not milliseconds (docs/firmware-event-model.md). */
uint32_t HAL_GetTick(void) { return (uint32_t)((uint64_t)now_ms * 1024U / 1000U); }
void NVIC_SystemReset(void) { resets++; }
uint32_t HAL_RTCEx_BKUPRead(RTC_HandleTypeDef *h, uint32_t reg) { (void)h; return bkp[reg]; }
void HAL_RTCEx_BKUPWrite(RTC_HandleTypeDef *h, uint32_t reg, uint32_t value) { (void)h; bkp[reg] = value; }
SysTime_t SysTimeGetMcuTime(void) { return (SysTime_t){ .Seconds = now_ms / 1000U, .SubSeconds = (int16_t)(now_ms % 1000U) }; }
SysTime_t SysTimeGet(void) { return (SysTime_t){ .Seconds = now_ms / 1000U + utc_offset, .SubSeconds = 0 }; }
void SysTimeSet(SysTime_t t) { utc_offset = t.Seconds - now_ms / 1000U; }

/* ---- console output ---- */
static char out[1 << 16];
static size_t out_len;
void host_printf(const char *fmt, ...)
{
  va_list ap; va_start(ap, fmt);
  int n = vsnprintf(out + out_len, sizeof out - out_len, fmt, ap);
  va_end(ap);
  if (n < 0 || (size_t)n >= sizeof out - out_len) { ws_trace_drops++; return; }
  out_len += (size_t)n;
}

/* ---- timer server, with ST's semantics (Utilities/timer/stm32_timer.c) ----
   UTIL_TIMER_Start on a timer that is already running is refused (UTIL_TIMER_INVALID_PARAM) and changes
   nothing: it does NOT restart it. Refusals are counted; the firmware never relies on one. A periodic
   timer is reloaded after its callback unless the callback stopped it. */
#define TIMER_INVALID_PARAM 1
static UTIL_TIMER_Object_t *timers;
static uint32_t timer_start_refused;
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg)
{
  int known = 0;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next) known |= p == t;
  t->period = period; t->mode = mode; t->cb = cb; t->arg = arg; t->running = 0; t->reload_stopped = 0;
  if (!known) { t->next = timers; timers = t; }
  return 0;
}
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t)
{
  if (t->running) { timer_start_refused++; return TIMER_INVALID_PARAM; }
  t->running = 1; t->reload_stopped = 0; t->due = now_ms + t->period;
  return 0;
}
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t) { t->running = 0; t->reload_stopped = 1; return 0; }
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period) { t->period = period; return 0; }

/* ---- sequencer, picking tasks as ST's UTIL_SEQ_Run does (all tasks here use one priority):
   round robin over the pending set, highest task bit first (SEQ_BitPosition = 31 - clz) ---- */
static void (*tasks[32])(void);
static uint32_t task_pending, round_robin = ~0U;
static uint32_t task_saturations;
static int hold;   /* h_hold: the main loop is held off (a long task); interrupts and timers still post */
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*task)(void)) { (void)flags; tasks[__builtin_ctz(mask)] = task; }
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio) { (void)prio; task_pending |= mask; }
static void run_tasks(void)
{
  if (hold) return;
  /* A task that re-posts itself (TEST-FLASH-STORM) never settles: like UTIL_SEQ, run a bounded
     number of tasks per step and let time move on (counted, so a test can tell). */
  for (int guard = 0; task_pending; guard++)
  {
    if (guard > 1000) { task_saturations++; return; }
    if ((task_pending & round_robin) == 0) round_robin = ~0U;
    int id = 31 - __builtin_clz(task_pending & round_robin);
    round_robin &= ~(1U << id);
    task_pending &= ~(1U << id);
    if (tasks[id]) tasks[id]();
  }
}

/* ---- radio ---- */
enum { R_SLEEP, R_STANDBY, R_TX, R_RX };
static int radio_state = R_SLEEP;
static RadioEvents_t *radio_events;
static uint32_t radio_due;         /* TxDone or RxTimeout time, if radio_timed */
static int radio_timed, radio_send_fails, radio_crc_flag, radio_hang;
static uint32_t sw_rx_due;          /* the driver's RxTimeoutTimer (Rx(t > 0)), if sw_rx_armed */
static int sw_rx_armed;
static uint8_t last_frame[256];
static int last_frame_len, frames_sent;
static uint32_t last_send_ms, last_rx_timeout;
/* Every transmission: its start time and kind (the frame's first byte), for as long as the test runs. */
static struct { uint32_t at; uint8_t kind; } *sends;
static int sends_cap;
static void radio_init(RadioEvents_t *e) { radio_events = e; radio_state = R_STANDBY; }
static radio_status_t radio_send(uint8_t *buf, uint8_t size)
{
  if (radio_send_fails > 0) { radio_send_fails--; return RADIO_STATUS_ERROR; }
  memcpy(last_frame, buf, size); last_frame_len = size;
  if (frames_sent == sends_cap)
  {
    sends_cap = sends_cap ? 2 * sends_cap : 256;
    sends = realloc(sends, (size_t)sends_cap * sizeof *sends);
    if (!sends) { fprintf(stderr, "tx_harness: out of memory\n"); abort(); }
  }
  sends[frames_sent].at = now_ms; sends[frames_sent].kind = size ? buf[0] : 0;
  frames_sent++; last_send_ms = now_ms;
  /* h_radio_hang: the frame is accepted but never finishes, and the driver's timeout never comes either */
  radio_state = R_TX; radio_timed = !radio_hang; radio_due = now_ms + TX_AIR_MS;
  return RADIO_STATUS_OK;
}
static void radio_rx(uint32_t timeout)
{
  radio_state = R_RX; last_rx_timeout = timeout;
  radio_timed = 1; radio_due = now_ms + 65000U;   /* the chip's single-mode timeout */
  sw_rx_armed = timeout != 0; sw_rx_due = now_ms + timeout;
}
static void radio_sleep(void) { radio_state = R_SLEEP; radio_timed = 0; }
static void radio_standby(void) { radio_state = R_STANDBY; radio_timed = 0; }
const struct Radio_s Radio = { radio_init, radio_send, radio_rx, radio_sleep, radio_standby };
int ws_radio_take_crc_error(void) { int f = radio_crc_flag; radio_crc_flag = 0; return f; }
void ws_radio_configure(int continuous) { (void)continuous; }
void ws_radio_sleep(void) { radio_sleep(); }

/* ---- flash: the real node_store.c over sim_flash, with the radio-idle check ---- */
static sim_flash S;
static uint32_t flash_ops_during_radio, flash_erases;
static void check_radio_idle(void) { if (radio_state == R_TX || radio_state == R_RX) flash_ops_during_radio++; }
static int h_read64(void *c, uint32_t a, uint64_t *v) { return sim_flash_read64(c, a, v); }
static int h_prog64(void *c, uint32_t a, uint64_t v) { check_radio_idle(); return sim_flash_prog64(c, a, v); }
static int h_erase(void *c, uint32_t p) { check_radio_idle(); flash_erases++; return sim_flash_erase(c, p); }
const ws_flash ws_flash_internal = { &S, h_read64, h_prog64, h_erase };

/* ---- board stubs ---- */
void leds_init(void) {}
void led_flash(led_t led, uint32_t ms) { (void)led; (void)ms; }
void led_set(led_t led, int on) { (void)led; (void)on; }
static int (*healthy_fn)(void);
void watchdog_start(int (*healthy)(void)) { healthy_fn = healthy; }
ws_reset_t watchdog_reset_code(void) { return WS_RESET_POWER; }
const char *watchdog_reset_cause(void) { return "power"; }
void fault_report(void) {}
uint32_t fault_count(void) { return 0; }
void fault_test(void) { fprintf(stderr, "tx_harness: TEST-FAULT\n"); abort(); }
void stackmon_paint(void) {}
uint32_t stackmon_peak(void) { return 0; }
static void (*line_handler)(char *);
void console_init(void (*on_line)(char *)) { line_handler = on_line; }

/* ---- SHT45: a measurement ends WS-defined 10 ms after it starts, through the sensor task ---- */
static void (*sensor_cb)(int, int16_t, uint16_t);
static int sensor_busy, sensor_rc, sensor_hang, sensor_starts;
static int16_t sensor_t = 2150;
static uint16_t sensor_h = 4500;
static UTIL_TIMER_Object_t sensor_timer;
static void sensor_task(void)
{
  sensor_busy = 0;
  sensor_cb(sensor_rc, sensor_rc ? 0 : sensor_t, sensor_rc ? 0 : sensor_h);
}
static void on_sensor_timer(void *arg) { (void)arg; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sensor, CFG_SEQ_Prio_0); }
void sensor_init(void)
{
  UTIL_TIMER_Create(&sensor_timer, 10, UTIL_TIMER_ONESHOT, on_sensor_timer, NULL);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sensor, UTIL_SEQ_RFU, sensor_task);
}
int sensor_start(void (*done)(int, int16_t, uint16_t))
{
  if (sensor_busy) return -1;
  sensor_busy = 1; sensor_cb = done; sensor_starts++;
  if (!sensor_hang) UTIL_TIMER_Start(&sensor_timer);
  return 0;
}

/* ---- the event loop ---- */
static UTIL_TIMER_Object_t *next_timer(void)
{
  UTIL_TIMER_Object_t *best = NULL;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next)
    if (p->running && (!best || (int32_t)(p->due - best->due) < 0)) best = p;
  return best;
}

/* Move the clock to `until`, firing every timer and radio event due on the way. */
void h_advance(uint32_t ms)
{
  uint32_t until = now_ms + ms;
  run_tasks();
  for (;;)
  {
    UTIL_TIMER_Object_t *t = next_timer();
    int sw_first = sw_rx_armed && (!t || (int32_t)(sw_rx_due - t->due) <= 0) &&
                   (!radio_timed || (int32_t)(sw_rx_due - radio_due) <= 0);
    int radio_first = !sw_first && radio_timed && (!t || (int32_t)(radio_due - t->due) <= 0);
    uint32_t due = sw_first ? sw_rx_due : radio_first ? radio_due : t ? t->due : until;
    if ((int32_t)(due - until) > 0) break;
    if (!sw_first && !radio_first && !t) break;
    now_ms = due;
    if (sw_first)
    {
      sw_rx_armed = 0;
      radio_events->RxTimeout();          /* ST's RxTimeoutTimer: the radio keeps receiving */
    }
    else if (radio_first)
    {
      radio_timed = 0;
      if (radio_state == R_TX) { radio_state = R_STANDBY; sw_rx_armed = 0; radio_events->TxDone(); }
      else if (radio_state == R_RX) { radio_state = R_STANDBY; sw_rx_armed = 0; radio_events->RxTimeout(); }
    }
    else
    {
      t->running = 0;
      t->cb(t->arg);
      if (t->mode == UTIL_TIMER_PERIODIC && !t->reload_stopped) UTIL_TIMER_Start(t);
    }
    run_tasks();
  }
  now_ms = until;
}

/* ---- the API tests/test_tx_machine.py uses ---- */
void h_reset(void) { sim_flash_reset(&S); }
int h_provision(uint32_t station, const uint8_t key[16])
{
  uint8_t kcv[3];
  return store_meta_init() || store_config_write(station, key, kcv);
}
void h_boot(void) { SubghzApp_Init(); run_tasks(); }
uint32_t h_now(void) { return now_ms; }
int h_radio_state(void) { return radio_state; }
int h_frames_sent(void) { return frames_sent; }
static void check_send_index(int i)
{
  if (i < 0 || i >= frames_sent) { fprintf(stderr, "tx_harness: no transmission %d (%d sent)\n", i, frames_sent); abort(); }
}
uint32_t h_send_at(int i) { check_send_index(i); return sends[i].at; }
int h_send_kind(int i) { check_send_index(i); return sends[i].kind; }
uint32_t h_tx_air_ms(void) { return TX_AIR_MS; }
uint32_t h_last_rx_timeout(void) { return last_rx_timeout; }
int h_last_frame(uint8_t *buf) { memcpy(buf, last_frame, (size_t)last_frame_len); return last_frame_len; }
uint32_t h_flash_ops_during_radio(void) { return flash_ops_during_radio; }
uint32_t h_flash_erases(void) { return flash_erases; }
int h_resets(void) { return resets; }
int h_healthy(void) { return healthy_fn(); }
int h_sensor_starts(void) { return sensor_starts; }
void h_sensor(int rc, int hang) { sensor_rc = rc; sensor_hang = hang; }
void h_radio_send_fails(int n) { radio_send_fails = n; }
void h_radio_hang(int on) { radio_hang = on; }
/* Hold the main loop: interrupts (timers, radio callbacks) still post, nothing runs until released. */
void h_hold(int on) { hold = on; run_tasks(); }
/* Consume k transmission counters through the store, as the firmware does (moves the next durable
   reservation, CTR_BLOCK counters apart, to where a test wants it). Returns how many it got. */
int h_burn(int k)
{
  int got = 0; uint64_t c;
  while (got < k && store_next_counter(&c) == 0) got++;
  return got;
}
uint32_t h_timer_start_refused(void) { return timer_start_refused; }
/* Call the callback of the firmware timer with this period now, running or not: a stale timer event
   in a state that does not expect it. Returns 0 if there is no such timer. */
int h_fire_timer(uint32_t period)
{
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next)
    if (p->period == period) { p->cb(p->arg); run_tasks(); return 1; }
  return 0;
}
/* Console output since the last call (NUL-terminated, valid until the next call). */
const char *h_output(void)
{
  static char copy[sizeof out];
  memcpy(copy, out, out_len); copy[out_len] = 0; out_len = 0;
  return copy;
}
void h_line(const char *line)
{
  char buf[WS_LINE_MAX + 1];
  snprintf(buf, sizeof buf, "%s", line);
  line_handler(buf);
  run_tasks();
}
/* Radio callbacks as the chip would raise them (interrupt context, then the main loop runs). */
void h_rx(const uint8_t *frame, int len, int rssi, int snr)
{
  uint8_t buf[256];
  memcpy(buf, frame, (size_t)len);
  radio_state = R_STANDBY; radio_timed = 0; sw_rx_armed = 0;   /* RX_DONE stops the driver's timer */
  radio_events->RxDone(buf, (uint16_t)len, (int16_t)rssi, (int8_t)snr);
  run_tasks();
}
/* A payload CRC failure, as ST delivers it: RxDone with the damaged bytes, then RxError; the
   driver's RX timer is NOT stopped. */
void h_rx_crc(const uint8_t *frame, int len)
{
  uint8_t buf[256];
  memcpy(buf, frame, (size_t)len);
  radio_state = R_STANDBY; radio_timed = 0;
  radio_crc_flag = 1;
  radio_events->RxDone(buf, (uint16_t)len, -110, -15);
  radio_events->RxError();
  run_tasks();
}
/* A header failure: ST reports it as RxTimeout (standby, timer stopped). */
void h_rx_hdr(void)
{
  radio_state = R_STANDBY; radio_timed = 0; sw_rx_armed = 0;
  radio_events->RxTimeout();
  run_tasks();
}
/* The driver's transmit timeout: the radio is still transmitting (stuck), no TxDone will come. */
void h_tx_timeout(void)
{
  radio_timed = 0;
  radio_events->TxTimeout();
  run_tasks();
}
/* A stray radio callback (0 TxDone, 1 TxTimeout, 2 RxTimeout, 3 RxError, 4 RxDone of 33 zero bytes),
   radio state untouched. */
void h_raw_event(int which)
{
  void (*cb[])(void) = { radio_events->TxDone, radio_events->TxTimeout, radio_events->RxTimeout, radio_events->RxError };
  uint8_t junk[33] = { 0 };
  if (which < 0 || which > 4) { fprintf(stderr, "tx_harness: no raw event %d\n", which); abort(); }
  if (which == 4) radio_events->RxDone(junk, sizeof junk, -100, -5);
  else cb[which]();
  run_tasks();
}
int h_sw_rx_armed(void) { return sw_rx_armed; }
uint32_t h_task_saturations(void) { return task_saturations; }
