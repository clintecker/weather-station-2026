/* Host harness for the interrupt-driven SHT45 driver (App/sensor.c, compiled unchanged).
 *
 * Simulated: a virtual clock with ST's timer server rounding (1/1024 s ticks, rounded down, at
 * least 3 ticks: timer_if.c, as the 2026-10-15 reviews read it), the sequencer, and an I2C bus with
 * one SHT45 whose behaviour the test chooses. A transfer completes through the HAL callbacks
 * HAL_I2C_EV_IRQHandler would call; HAL_I2C_DeInit (with NVIC disable / clear-pending) cancels a
 * completion still in flight. During the stuck-bus recovery SDA stays low until a chosen number of
 * SCL rising edges. tests/test_sensor_machine.py drives it through ctypes. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sensor.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "utilities_def.h"

/* ---- clock, CMSIS ---- */
static uint32_t now_ms;
DWT_Type host_dwt;
CoreDebug_Type host_coredebug;
uint32_t SystemCoreClock = 48000000U;
uint32_t host_primask;
uint32_t HAL_GetTick(void) { return now_ms; }
void NVIC_SystemReset(void) { abort(); }

/* ---- timer server: ST rounds ms down to 1/1024 s ticks, minimum 3 ticks ---- */
static UTIL_TIMER_Object_t *timers;
static uint32_t effective_ms(uint32_t ms)
{
  uint32_t ticks = ms * 1024U / 1000U;
  if (ticks < 3) ticks = 3;
  return (ticks * 1000U + 1023U) / 1024U;   /* back to whole ms, rounded up (never longer than ST) */
}
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg)
{
  int known = 0;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next) known |= p == t;
  t->period = period; t->mode = mode; t->cb = cb; t->arg = arg; t->running = 0;
  if (!known) { t->next = timers; timers = t; }
  return 0;
}
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t) { t->running = 1; t->due = now_ms + effective_ms(t->period); return 0; }
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t) { t->running = 0; return 0; }
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period) { t->period = period; return 0; }

/* ---- sequencer ---- */
static void (*tasks[32])(void);
static uint32_t task_pending;
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*task)(void)) { (void)flags; tasks[__builtin_ctz(mask)] = task; }
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio) { (void)prio; task_pending |= mask; }
static void run_tasks(void)
{
  for (int guard = 0; task_pending; guard++)
  {
    if (guard > 1000) { fprintf(stderr, "sensor_harness: tasks never settle\n"); abort(); }
    int id = __builtin_ctz(task_pending);
    task_pending &= ~(1U << id);
    if (tasks[id]) tasks[id]();
  }
}

/* ---- the SHT45 and its bus ---- */
enum { DEV_OK, DEV_NACK_CMD, DEV_NACK_READ, DEV_BAD_CRC, DEV_HANG_CMD, DEV_HANG_READ, DEV_BUSY };
enum { DONE_NONE, DONE_TX, DONE_RX, DONE_ERROR };
static int dev_mode, i2c_inited, i2c_irq_enabled;
static uint32_t i2c_latency_ms = 1;
static int pending_kind;          /* a transfer completion in flight */
static uint32_t pending_due;
static uint8_t *rx_dest;
static uint32_t transfers, deinits;
static I2C_HandleTypeDef *handle;   /* sensor.c's hi2c2, as HAL_I2C_Init saw it */
GPIO_TypeDef host_gpioa;
I2C_TypeDef host_i2c2;

void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)irq; (void)pre; (void)sub; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { (void)irq; i2c_irq_enabled = 1; }
void HAL_NVIC_DisableIRQ(IRQn_Type irq) { (void)irq; i2c_irq_enabled = 0; }
void HAL_NVIC_ClearPendingIRQ(IRQn_Type irq) { (void)irq; pending_kind = DONE_NONE; }
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk) { (void)clk; return HAL_OK; }
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef *hi2c) { handle = hi2c; HAL_I2C_MspInit(hi2c); i2c_inited = 1; return HAL_OK; }
HAL_StatusTypeDef HAL_I2C_DeInit(I2C_HandleTypeDef *hi2c)
{
  HAL_I2C_MspDeInit(hi2c); i2c_inited = 0; deinits++;
  pending_kind = DONE_NONE;   /* the peripheral is off: a transfer in flight never completes */
  return HAL_OK;
}
HAL_StatusTypeDef HAL_I2CEx_ConfigAnalogFilter(I2C_HandleTypeDef *hi2c, uint32_t f) { (void)hi2c; (void)f; return HAL_OK; }
static void complete_in(int kind) { pending_kind = kind; pending_due = now_ms + i2c_latency_ms; }
HAL_StatusTypeDef HAL_I2C_Master_Transmit_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size)
{
  (void)hi2c;
  if (!i2c_inited || dev_mode == DEV_BUSY || pending_kind != DONE_NONE) return HAL_BUSY;
  if (addr != (WS_SHT45_ADDR << 1) || size != 1 || data[0] != WS_SHT45_MEASURE) { fprintf(stderr, "bad command\n"); abort(); }
  transfers++;
  if (dev_mode == DEV_NACK_CMD) complete_in(DONE_ERROR);
  else if (dev_mode != DEV_HANG_CMD) complete_in(DONE_TX);
  return HAL_OK;
}
static uint32_t measure_started, read_started;
static int read_too_early;
HAL_StatusTypeDef HAL_I2C_Master_Receive_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size)
{
  (void)hi2c;
  if (!i2c_inited || pending_kind != DONE_NONE) return HAL_BUSY;
  if (addr != (WS_SHT45_ADDR << 1) || size != WS_SHT45_REPLY_LEN) { fprintf(stderr, "bad read\n"); abort(); }
  transfers++;
  if (now_ms - measure_started < 9) read_too_early = 1;   /* the SHT45 needs up to 8.3 ms (Table 4) */
  rx_dest = data; read_started = now_ms;
  if (dev_mode == DEV_NACK_READ) complete_in(DONE_ERROR);
  else if (dev_mode != DEV_HANG_READ) complete_in(DONE_RX);
  return HAL_OK;
}
void HAL_I2C_EV_IRQHandler(I2C_HandleTypeDef *hi2c) { (void)hi2c; }
void HAL_I2C_ER_IRQHandler(I2C_HandleTypeDef *hi2c) { (void)hi2c; }

/* Pins: SCL rising edges during recovery release SDA after `sda_hold_edges`. */
static int scl = 1, sda_out = 1, scl_edges, sda_hold_edges, pin_errors;
static uint32_t pin_mode;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init) { (void)port; pin_mode = init->Mode; }
void HAL_GPIO_DeInit(GPIO_TypeDef *port, uint32_t pins) { (void)port; (void)pins; }
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint32_t pins, GPIO_PinState state)
{
  (void)port;
  if (pins & GPIO_PIN_12) { if (!scl && state && pin_mode == GPIO_MODE_OUTPUT_OD) scl_edges++; scl = state; }
  if (pins & GPIO_PIN_11) sda_out = state;
}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint32_t pin)
{
  (void)port;
  if (pin != GPIO_PIN_11) pin_errors++;
  int held = scl_edges < sda_hold_edges;
  return (sda_out && !held) ? GPIO_PIN_SET : GPIO_PIN_RESET;
}

/* ---- the event loop: timers and I2C completions, then tasks ---- */
static UTIL_TIMER_Object_t *next_timer(void)
{
  UTIL_TIMER_Object_t *best = NULL;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next)
    if (p->running && (!best || (int32_t)(p->due - best->due) < 0)) best = p;
  return best;
}
static uint8_t reply_bytes[WS_SHT45_REPLY_LEN];
void h_advance(uint32_t ms)
{
  uint32_t until = now_ms + ms;
  run_tasks();
  for (;;)
  {
    UTIL_TIMER_Object_t *t = next_timer();
    /* On a tie the timer runs first: RTC alarm is priority 0, I2C2 priority 2. */
    int i2c_first = pending_kind != DONE_NONE && (!t || (int32_t)(pending_due - t->due) < 0);
    uint32_t due = i2c_first ? pending_due : t ? t->due : until;
    if ((int32_t)(due - until) > 0 || (!i2c_first && !t)) break;
    now_ms = due;
    if (i2c_first)
    {
      int kind = pending_kind; pending_kind = DONE_NONE;
      if (!i2c_irq_enabled) continue;
      if (kind == DONE_TX) { measure_started = now_ms; HAL_I2C_MasterTxCpltCallback(handle); }
      else if (kind == DONE_RX) { memcpy(rx_dest, reply_bytes, sizeof reply_bytes); HAL_I2C_MasterRxCpltCallback(handle); }
      else HAL_I2C_ErrorCallback(handle);
    }
    else
    {
      if (t->mode == UTIL_TIMER_PERIODIC) t->due += effective_ms(t->period); else t->running = 0;
      t->cb(t->arg);
    }
    /* Interrupts due at the same instant all run before the main loop does, as on the chip. */
    UTIL_TIMER_Object_t *n = next_timer();
    if ((pending_kind != DONE_NONE && pending_due == now_ms) || (n && n->due == now_ms)) continue;
    run_tasks();
  }
  run_tasks();
  now_ms = until;
}

/* ---- the API tests/test_sensor_machine.py uses ---- */
static int done_calls, done_rc;
static int16_t done_t;
static uint16_t done_h;
static uint32_t done_at, started_at;
static void on_done(int rc, int16_t t, uint16_t h) { done_calls++; done_rc = rc; done_t = t; done_h = h; done_at = now_ms; }
void h_init(void)
{
  reply_bytes[0] = 0x80; reply_bytes[1] = 0; reply_bytes[2] = ws_crc8(reply_bytes, 2);
  reply_bytes[3] = 0x80; reply_bytes[4] = 0; reply_bytes[5] = ws_crc8(reply_bytes + 3, 2);
  sensor_init();
}
void h_device(int mode, int sda_hold, uint32_t latency_ms)
{
  dev_mode = mode; sda_hold_edges = sda_hold; scl_edges = 0; i2c_latency_ms = latency_ms;
  reply_bytes[5] = ws_crc8(reply_bytes + 3, 2) ^ (mode == DEV_BAD_CRC);
}
int h_start(void) { started_at = now_ms; return sensor_start(on_done); }
int h_done_calls(void) { return done_calls; }
int h_done_rc(void) { return done_rc; }
int h_done_t(void) { return done_t; }
int h_done_h(void) { return done_h; }
uint32_t h_done_after(void) { return done_at - started_at; }
uint32_t h_transfers(void) { return transfers; }
uint32_t h_deinits(void) { return deinits; }
int h_scl_edges(void) { return scl_edges; }
int h_i2c_ready(void) { return i2c_inited && i2c_irq_enabled; }
int h_read_too_early(void) { return read_too_early; }
int h_pin_errors(void) { return pin_errors; }
/* A read left hanging now ends exactly when its 30 ms guard expires (sensor.c I2C_GUARD_MS):
   completes (error = 0) or fails with an I2C error (error = 1). */
int h_complete_read_at_guard(int error)
{
  if (pending_kind != DONE_NONE || !rx_dest) return 0;
  pending_kind = error ? DONE_ERROR : DONE_RX; pending_due = read_started + effective_ms(30);
  return 1;
}
