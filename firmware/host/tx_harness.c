/* Host harness for the TX node's event-driven firmware (App/app_tx.c and the modules App/tx_node.h
 * lists, compiled unchanged).
 *
 * The board is firmware/host/sim_core.c (clock, ST's timer server and sequencer, the event loop; see
 * there), with timer periods in exact milliseconds (sim_config.timer_exact_ms: the tests state their
 * expectations in whole ms). tests/test_tx_machine.py drives it through ctypes. This file adds the
 * TX node's devices: a radio that finishes a transmission after TX_AIR_MS and times out a receive
 * window on its own, the SHT45 (a measurement ends 10 ms after it starts, with a result the test
 * chooses; App/sensor.c itself is tested by firmware/host/sensor_harness.c), and the flash
 * (firmware/sim_flash.c under the real App/node_store.c).
 *
 * The radio follows ST's SubGHz_Phy (radio.c, stm32wlxx_hal_subghz.c) as
 * written, not an idealised radio:
 *  - Rx(t > 0) arms the driver's software timer (RxTimeoutTimer, a UTIL_TIMER): its timeout calls
 *    RxTimeout and leaves the radio RECEIVING; a CRC error does not stop that timer. Rx(0) in single
 *    mode: the chip's own ~65 s timeout, which puts it in standby.
 *  - A payload CRC failure is RxDone (bytes, CRC flag set in the HAL) then RxError, in one interrupt;
 *    single mode then standby. A header failure is RxTimeout (standby, timer stopped).
 *  - The transmit timeout is a software timer too: TxTimeout leaves the radio TRANSMITTING.
 *
 * h_hold holds the main loop off, so a test can have several interrupts post before process() runs;
 * h_fire_timer raises a timer event in a state that does not expect it; h_burn moves the next
 * durable counter reservation; h_radio_hang makes a transmission that never ends.
 *
 * Checked on every step, not just at the end of a test:
 *  - no flash program or erase while the radio is transmitting or receiving (the CPU stalls
 *    for a flash erase; the firmware must schedule it with the radio idle);
 *  - no blocking (sim_core.c: the clock only moves between tasks);
 *  - no task leaves interrupts masked. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console.h"
#include "node_store.h"
#include "radio.h"
#include "radio_cfg.h"
#include "sensor.h"
#include "sim_core.h"
#include "sim_flash.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"

#define TX_AIR_MS 30U   /* an observation frame at SF7/500 kHz is ~30 ms on air */

static const sim_source radio_source;
const sim_config sim_cfg = { .name = "tx_harness", .sources = (const sim_source *const[]){ &radio_source, NULL },
                             .timer_exact_ms = 1, .primask_leak_fatal = 1 };
/* Not modelled here, deliberately: the watchdog's own 1 s check (the tests call the health test at
   the instants they choose, h_healthy; rx_harness.c models the check). A reset is counted. */
volatile uint8_t ws_flash_ecc_fault;

/* ---- console output: captured whole ---- */
void host_printf(const char *fmt, ...)
{
  char line[4096];
  va_list ap; va_start(ap, fmt);
  int n = vsnprintf(line, sizeof line, fmt, ap);
  va_end(ap);
  if (n < 0 || (size_t)n >= sizeof line || !sim_capture(line, (size_t)n)) ws_trace_drops++;
}

/* ---- radio ---- */
enum { R_SLEEP, R_STANDBY, R_TX, R_RX };
static int radio_state = R_SLEEP;
static RadioEvents_t *radio_events;
static uint64_t radio_due;         /* TxDone or RxTimeout time, if radio_timed */
static int radio_timed, radio_send_fails, radio_crc_flag, radio_hang;
static UTIL_TIMER_Object_t sw_rx_timer;   /* the driver's RxTimeoutTimer (Rx(t > 0)) */
#define RADIO_BUF_LEN (WS_FRAME_MAX + 1)   /* room for any length a uint8 can report */
#define SENDS_INITIAL 256                  /* first capacity of the send log; it doubles */
static uint8_t last_frame[RADIO_BUF_LEN];
static int last_frame_len, frames_sent;
static uint32_t last_rx_timeout;
/* Every transmission: its start time and kind (the frame's first byte), for as long as the test runs. */
static struct { uint32_t at; uint8_t kind; } *sends;
static int sends_cap;
static void on_sw_rx_timeout(void *arg) { (void)arg; radio_events->RxTimeout(); }   /* the radio keeps receiving */
static void radio_init(RadioEvents_t *e)
{
  radio_events = e; radio_state = R_STANDBY;
  UTIL_TIMER_Create(&sw_rx_timer, 0, UTIL_TIMER_ONESHOT, on_sw_rx_timeout, NULL);
}
static void record_send(const uint8_t *buf, uint8_t size)
{
  memcpy(last_frame, buf, size); last_frame_len = size;
  if (frames_sent == sends_cap)
  {
    sends_cap = sends_cap ? 2 * sends_cap : SENDS_INITIAL;
    sends = realloc(sends, (size_t)sends_cap * sizeof *sends);
    if (!sends) { fprintf(stderr, "tx_harness: out of memory\n"); abort(); }
  }
  sends[frames_sent].at = (uint32_t)sim_ms(); sends[frames_sent].kind = size ? buf[0] : 0;
  frames_sent++;
}
static radio_status_t radio_send(uint8_t *buf, uint8_t size)
{ sim_radio_command();
  if (radio_send_fails > 0) { radio_send_fails--; return RADIO_STATUS_ERROR; }
  record_send(buf, size);
  /* h_radio_hang: the frame is accepted but never finishes, and the driver's timeout never comes either */
  radio_state = R_TX; radio_timed = !radio_hang; radio_due = sim_now() + TX_AIR_MS * SIM_UNITS_PER_MS;
  return RADIO_STATUS_OK;
}
static void radio_rx(uint32_t timeout)
{ sim_radio_command();
  radio_state = R_RX; last_rx_timeout = timeout;
  radio_timed = 1; radio_due = sim_now() + 65000U * SIM_UNITS_PER_MS;   /* the chip's single-mode timeout */
  /* ST: TimerSetValue (UTIL_TIMER_SetPeriod restarts a running timer), then TimerStart */
  if (timeout) { UTIL_TIMER_SetPeriod(&sw_rx_timer, timeout); if (!sw_rx_timer.running) UTIL_TIMER_Start(&sw_rx_timer); }
  else UTIL_TIMER_Stop(&sw_rx_timer);
}
static void radio_sleep(void) { sim_radio_command(); radio_state = R_SLEEP; radio_timed = 0; }
static void radio_standby(void) { sim_radio_command(); radio_state = R_STANDBY; radio_timed = 0; }
const struct Radio_s Radio = { radio_init, radio_send, radio_rx, radio_sleep, radio_standby };
int ws_radio_take_crc_error(void) { int f = radio_crc_flag; radio_crc_flag = 0; return f; }
void ws_radio_configure(int continuous) { (void)continuous; }
void ws_radio_sleep(void) { ws_radio_irq_hold(); radio_sleep(); ws_radio_irq_release(); }
/* The chip's own interrupts: TxDone after the air time, the single-mode receive timeout. */
static int radio_pending(uint64_t *at) { *at = radio_due; return radio_timed; }
static void radio_fire(void)
{
  radio_timed = 0;
  if (radio_state != R_TX && radio_state != R_RX) return;
  int tx = radio_state == R_TX;
  radio_state = R_STANDBY; UTIL_TIMER_Stop(&sw_rx_timer);
  if (tx) radio_events->TxDone(); else radio_events->RxTimeout();
}
static const sim_source radio_source = { radio_pending, radio_fire, SIM_IRQ_SUBGHZ };

/* ---- flash: the real node_store.c over sim_flash, with the radio-idle check ---- */
static sim_flash S;
static uint32_t flash_ops_during_radio, flash_erases;
static int prog_fails;   /* h_flash_prog_fails: every program is refused like a HAL error */
static void check_radio_idle(void) { if (radio_state == R_TX || radio_state == R_RX) flash_ops_during_radio++; }
int ws_flash_read64(uint32_t a, uint64_t *v) { return sim_flash_read64(&S, a, v); }
int ws_flash_prog64(uint32_t a, uint64_t v) { check_radio_idle(); return prog_fails ? -1 : sim_flash_prog64(&S, a, v); }
int ws_flash_erase(uint32_t p) { check_radio_idle(); flash_erases++; return sim_flash_erase(&S, p); }

/* ---- the USB console: the test hands over whole lines (h_line) ---- */
void console_init(void) {}

/* ---- SHT45: a measurement ends WS-defined 10 ms after it starts, through the sensor task ---- */
static int sensor_busy, sensor_rc, sensor_hang, sensor_starts;
static int16_t sensor_t = 2150;
static uint16_t sensor_h = 4500;
static UTIL_TIMER_Object_t sensor_timer;
static void sensor_task(void)
{
  sensor_busy = 0;
  sensor_done(sensor_rc, sensor_rc ? 0 : sensor_t, sensor_rc ? 0 : sensor_h);
}
static void on_sensor_timer(void *arg) { (void)arg; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sensor, CFG_SEQ_Prio_0); }
void sensor_init(void)
{
  UTIL_TIMER_Create(&sensor_timer, 10, UTIL_TIMER_ONESHOT, on_sensor_timer, NULL);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sensor, UTIL_SEQ_RFU, sensor_task);
}
int sensor_start(void)
{
  if (sensor_busy) return -1;
  sensor_busy = 1; sensor_starts++;
  if (!sensor_hang) UTIL_TIMER_Start(&sensor_timer);
  return 0;
}

/* ---- the API tests/test_tx_machine.py uses ---- */
/* Move the clock ms forward, firing every timer and radio event due on the way. */
void h_advance(uint32_t ms) { sim_advance(ms); }
void h_reset(void) { sim_flash_reset(&S); }
int h_provision(uint32_t station, const uint8_t key[WS_KEY_LEN])
{
  uint8_t kcv[WS_KCV_LEN];
  return store_meta_init() || store_config_write(station, key, kcv);
}
void h_boot(void) { SubghzApp_Init(); sim_run_tasks(); }
uint32_t h_now(void) { return (uint32_t)sim_ms(); }
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
int h_sensor_starts(void) { return sensor_starts; }
void h_sensor(int rc, int hang) { sensor_rc = rc; sensor_hang = hang; }
void h_radio_send_fails(int n) { radio_send_fails = n; }
void h_flash_prog_fails(int on) { prog_fails = on; }
void h_radio_hang(int on) { radio_hang = on; }
/* Hold the main loop: interrupts (timers, radio callbacks) still post, nothing runs until released. */
void h_hold(int on) { sim_set_hold(on); sim_run_tasks(); }
/* Consume k transmission counters through the store, as the firmware does (moves the next durable
   reservation, CTR_BLOCK counters apart, to where a test wants it). Returns how many it got. */
int h_burn(int k)
{
  int got = 0; uint64_t c;
  while (got < k && store_next_counter(&c) == 0) got++;
  return got;
}
static UTIL_TIMER_Object_t *firmware_timer(uint32_t period)
{
  for (UTIL_TIMER_Object_t *p = sim_timers(); p; p = p->next)
    if (p != &sw_rx_timer && p->period == period) return p;
  return NULL;
}
/* Call the callback of the firmware timer with this period now, running or not: a stale timer event
   in a state that does not expect it. Returns 0 if there is no such timer. */
int h_fire_timer(uint32_t period)
{
  UTIL_TIMER_Object_t *p = firmware_timer(period);
  if (!p) return 0;
  p->cb(p->arg); sim_run_tasks();
  return 1;
}
/* Start the firmware timer with this period now, so that the firmware's own start of it is refused
   (a running timer: ST ignores the start), the WS_CHECK test. Returns 0 if there is no such timer. */
int h_start_timer(uint32_t period)
{
  UTIL_TIMER_Object_t *p = firmware_timer(period);
  return p && UTIL_TIMER_Start(p) == UTIL_TIMER_OK;
}
void h_line(const char *line)
{
  char buf[WS_LINE_MAX + 1];
  snprintf(buf, sizeof buf, "%s", line);
  console_line(buf);
  sim_run_tasks();
}
/* Radio callbacks as the chip would raise them (interrupt context, then the main loop runs). */
static void rx_done(const uint8_t *frame, int len, int rssi, int snr)
{
  uint8_t buf[RADIO_BUF_LEN];
  memcpy(buf, frame, (size_t)len);
  radio_state = R_STANDBY; radio_timed = 0;
  radio_events->RxDone(buf, (uint16_t)len, (int16_t)rssi, (int8_t)snr);
}
void h_rx(const uint8_t *frame, int len, int rssi, int snr)
{
  UTIL_TIMER_Stop(&sw_rx_timer);   /* RX_DONE stops the driver's timer */
  rx_done(frame, len, rssi, snr);
  sim_run_tasks();
}
/* A payload CRC failure, as ST delivers it: RxDone with the damaged bytes, then RxError; the
   driver's RX timer is NOT stopped. */
void h_rx_crc(const uint8_t *frame, int len)
{
  radio_crc_flag = 1;
  rx_done(frame, len, -110, -15);
  radio_events->RxError();
  sim_run_tasks();
}
/* A header failure: ST reports it as RxTimeout (standby, timer stopped). */
void h_rx_hdr(void)
{
  radio_state = R_STANDBY; radio_timed = 0; UTIL_TIMER_Stop(&sw_rx_timer);
  radio_events->RxTimeout();
  sim_run_tasks();
}
/* The driver's transmit timeout: the radio is still transmitting (stuck), no TxDone will come. */
void h_tx_timeout(void)
{
  radio_timed = 0;
  radio_events->TxTimeout();
  sim_run_tasks();
}
/* A stray radio callback (0 TxDone, 1 TxTimeout, 2 RxTimeout, 3 RxError, 4 RxDone of an ACK's length
   of zero bytes), radio state untouched. The numbers are tests/test_tx_machine.py's. */
enum { RAW_RX_DONE = 4 };
void h_raw_event(int which)
{
  void (*cb[])(void) = { radio_events->TxDone, radio_events->TxTimeout, radio_events->RxTimeout, radio_events->RxError };
  uint8_t junk[WS_ACK_FRAME_LEN] = { 0 };
  if (which < 0 || which > RAW_RX_DONE) { fprintf(stderr, "tx_harness: no raw event %d\n", which); abort(); }
  if (which == RAW_RX_DONE) radio_events->RxDone(junk, sizeof junk, -100, -5);
  else cb[which]();
  sim_run_tasks();
}
int h_sw_rx_armed(void) { return sw_rx_timer.running; }
