/* Host harness for the interrupt-driven SHT45 driver (App/sensor.c, compiled unchanged).
 *
 * The board is firmware/host/sim_core.c (see there): ST's timer server in 1/1024 s ticks (rounded
 * down, at least 3 ticks: timer_if.c), the sequencer and the event loop; tasks that never settle
 * abort the test. This file adds an I2C bus with one SHT45 whose behaviour the test chooses. A
 * transfer completes through the HAL callbacks HAL_I2C_EV_IRQHandler would call (I2C2 interrupt,
 * priority 2: after the RTC alarm, priority 0, when both are due together); HAL_I2C_DeInit (with
 * NVIC disable / clear-pending) cancels a completion still in flight. During the stuck-bus recovery
 * SDA stays low until a chosen number of SCL rising edges. tests/test_sensor_machine.py drives it
 * through ctypes. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sensor.h"
#include "sim_core.h"
#include "stage0.h"
#include "stm32wlxx_hal.h"

static const sim_source i2c_source;
const sim_config sim_cfg = { .name = "sensor_harness", .sources = (const sim_source *const[]){ &i2c_source, NULL },
                             .reset_fatal = 1, .saturation_fatal = 1, .primask_leak_fatal = 1 };

/* ---- the SHT45 and its bus ---- */
enum { DEV_OK, DEV_NACK_CMD, DEV_NACK_READ, DEV_BAD_CRC, DEV_HANG_CMD, DEV_HANG_READ, DEV_BUSY };
enum { DONE_NONE, DONE_TX, DONE_RX, DONE_ERROR };
static int dev_mode, i2c_inited, i2c_irq_enabled;
static uint32_t i2c_latency_ms = 1;
static int pending_kind;          /* a transfer completion in flight */
static uint64_t pending_due;
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
static void complete_in(int kind) { pending_kind = kind; pending_due = sim_now() + (uint64_t)i2c_latency_ms * SIM_UNITS_PER_MS; }
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
static uint64_t measure_started, read_started;
static int read_too_early;
HAL_StatusTypeDef HAL_I2C_Master_Receive_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size)
{
  (void)hi2c;
  if (!i2c_inited || pending_kind != DONE_NONE) return HAL_BUSY;
  if (addr != (WS_SHT45_ADDR << 1) || size != WS_SHT45_REPLY_LEN) { fprintf(stderr, "bad read\n"); abort(); }
  transfers++;
  if (sim_now() - measure_started < 9U * SIM_UNITS_PER_MS) read_too_early = 1;   /* the SHT45 needs up to 8.3 ms (Table 4) */
  rx_dest = data; read_started = sim_now();
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

/* The I2C2 interrupt: a transfer completion, unless the interrupt is disabled. */
static uint8_t reply_bytes[WS_SHT45_REPLY_LEN];
static int i2c_pending(uint64_t *at) { *at = pending_due; return pending_kind != DONE_NONE; }
static void i2c_fire(void)
{
  int kind = pending_kind; pending_kind = DONE_NONE;
  if (!i2c_irq_enabled) return;
  if (kind == DONE_TX) { measure_started = sim_now(); HAL_I2C_MasterTxCpltCallback(handle); }
  else if (kind == DONE_RX) { memcpy(rx_dest, reply_bytes, sizeof reply_bytes); HAL_I2C_MasterRxCpltCallback(handle); }
  else HAL_I2C_ErrorCallback(handle);
}
static const sim_source i2c_source = { i2c_pending, i2c_fire, SIM_IRQ_I2C2_EV };

/* ---- the API tests/test_sensor_machine.py uses ---- */
static int done_calls, done_rc;
static int16_t done_t;
static uint16_t done_h;
static uint64_t done_at, started_at;
static void on_done(int rc, int16_t t, uint16_t h) { done_calls++; done_rc = rc; done_t = t; done_h = h; done_at = sim_now(); }
void h_advance(uint32_t ms) { sim_advance(ms); }
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
int h_start(void) { started_at = sim_now(); return sensor_start(on_done); }
int h_done_calls(void) { return done_calls; }
int h_done_rc(void) { return done_rc; }
int h_done_t(void) { return done_t; }
int h_done_h(void) { return done_h; }
uint32_t h_done_after(void) { return (uint32_t)((done_at - started_at) / SIM_UNITS_PER_MS); }   /* whole ms */
uint32_t h_transfers(void) { return transfers; }
uint32_t h_deinits(void) { return deinits; }
int h_scl_edges(void) { return scl_edges; }
int h_i2c_ready(void) { return i2c_inited && i2c_irq_enabled; }
int h_read_too_early(void) { return read_too_early; }
int h_pin_errors(void) { return pin_errors; }
/* A read left hanging now ends exactly when its 30 ms guard expires (sensor.c I2C_GUARD_MS, started
   with the read): completes (error = 0) or fails with an I2C error (error = 1). */
int h_complete_read_at_guard(int error)
{
  if (pending_kind != DONE_NONE || !rx_dest) return 0;
  pending_kind = error ? DONE_ERROR : DONE_RX; pending_due = sim_timer_due(read_started, 30);
  return 1;
}
