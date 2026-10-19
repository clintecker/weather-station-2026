/* The I2C2 bus with many devices on the host (see i2c_sim.h). A transfer completes through the HAL
 * callbacks that HAL_I2C_EV_IRQHandler would call (I2C2 interrupt, priority 2), after the device's
 * latency. HAL_I2C_DeInit cancels a completion in flight. During the stuck-bus recovery SDA stays low
 * until the held number of SCL rising edges. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "i2c_sim.h"
#include "stm32wlxx_hal.h"

enum { DONE_NONE, DONE_TX, DONE_RX, DONE_MEMRX, DONE_ERROR };
typedef struct { int kind, mode, present, sda_hold; uint8_t addr7; uint32_t latency_ms; } sim_dev;
static sim_dev devs[I2C_SIM_DEVICES];
static int ndevs, i2c_inited, irq_enabled, pending_kind, power_on;
static uint64_t pending_due, started_at;
static uint8_t *rx_dest;
static uint8_t rx_buf[I2C_SIM_BUF];
static uint16_t rx_len;
static uint32_t transfers, deinits;
static I2C_HandleTypeDef *handle;
GPIO_TypeDef host_gpioa;
I2C_TypeDef host_i2c2;

int i2c_sim_add(int kind, uint8_t addr7)
{
  if (ndevs >= I2C_SIM_DEVICES) return -1;
  devs[ndevs] = (sim_dev){ .kind = kind, .mode = DM_OK, .present = 1, .addr7 = addr7, .latency_ms = 1 };
  model_reset(kind, ndevs);
  return ndevs++;
}
void i2c_sim_remove(int dev) { if (dev >= 0 && dev < ndevs) devs[dev].present = 0; }
void i2c_sim_restore(int dev) { if (dev >= 0 && dev < ndevs) devs[dev].present = 1; }
void i2c_sim_mode(int dev, int mode, int sda_hold_edges, uint32_t latency_ms)
{
  if (dev < 0 || dev >= ndevs) return;
  devs[dev].mode = mode; devs[dev].sda_hold = sda_hold_edges; devs[dev].latency_ms = latency_ms;
}

/* ---- NVIC, RCC and the peripheral ---- */
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)irq; (void)pre; (void)sub; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { (void)irq; irq_enabled = 1; }
void HAL_NVIC_DisableIRQ(IRQn_Type irq) { (void)irq; irq_enabled = 0; }
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
void HAL_I2C_EV_IRQHandler(I2C_HandleTypeDef *hi2c) { (void)hi2c; }
void HAL_I2C_ER_IRQHandler(I2C_HandleTypeDef *hi2c) { (void)hi2c; }

/* ---- pins: SCL rising edges during the recovery release a held SDA ---- */
static int scl = 1, sda_out = 1, scl_edges, sda_release_at, pin_errors;
static uint32_t pin_mode;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init) { (void)port; if (init->Pin & (GPIO_PIN_11 | GPIO_PIN_12)) pin_mode = init->Mode; }
void HAL_GPIO_DeInit(GPIO_TypeDef *port, uint32_t pins) { (void)port; (void)pins; }
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint32_t pins, GPIO_PinState state)
{
  (void)port;
  if (pins & GPIO_PIN_12) { if (!scl && state && pin_mode == GPIO_MODE_OUTPUT_OD) scl_edges++; scl = state; }
  if (pins & GPIO_PIN_11) sda_out = state;
  if (pins & GPIO_PIN_9) power_on = state;
}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint32_t pin)
{
  (void)port;
  if (pin != GPIO_PIN_11) pin_errors++;
  return (sda_out && scl_edges >= sda_release_at) ? GPIO_PIN_SET : GPIO_PIN_RESET;
}

/* ---- transfers ---- */
static sim_dev *find(uint16_t addr)
{
  for (int i = 0; i < ndevs; i++)
    if (devs[i].present && devs[i].addr7 == (addr >> 1)) return &devs[i];
  return NULL;
}

static void complete_in(int kind, const sim_dev *d)
{
  pending_kind = kind;
  pending_due = sim_now() + (uint64_t)(d ? d->latency_ms : 1U) * SIM_UNITS_PER_MS;
}

/* Common start of a transfer: refuses a busy bus, counts it, and applies the device's fault. Returns
   the device to serve, or NULL if the fault decides the outcome. */
static int faulty(const sim_dev *d, int is_read)
{
  return d->mode == DM_HANG || d->mode == DM_NACK_ADDR || (is_read && (d->mode == DM_NACK_DATA || d->mode == DM_HANG_READ));
}

static sim_dev *begin(uint16_t addr, int is_read)
{
  sim_dev *d = find(addr);
  transfers++; started_at = sim_now();
  if (d && d->sda_hold && faulty(d, is_read)) sda_release_at = scl_edges + d->sda_hold;
  if (!d || d->mode == DM_NACK_ADDR) { complete_in(DONE_ERROR, d); return NULL; }
  if (d->mode == DM_HANG || (is_read && d->mode == DM_HANG_READ)) return NULL;
  return d;
}

static int bus_free(void)
{
  if (!i2c_inited || pending_kind != DONE_NONE) return 0;
  for (int i = 0; i < ndevs; i++)
    if (devs[i].present && devs[i].mode == DM_BUSY) return 0;
  return 1;
}

HAL_StatusTypeDef HAL_I2C_Master_Transmit_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size)
{
  (void)hi2c;
  if (!bus_free()) return HAL_BUSY;
  sim_dev *d = begin(addr, 0);
  if (d) complete_in(model_write(d->kind, (int)(d - devs), data, size) ? DONE_ERROR : DONE_TX, d);
  return HAL_OK;
}

static void read_into(sim_dev *d, uint8_t *data, uint16_t size, int rc)
{
  rx_dest = data; rx_len = size < I2C_SIM_BUF ? size : I2C_SIM_BUF;
  if (d->mode == DM_NACK_DATA || rc) complete_in(DONE_ERROR, d);
  else complete_in(DONE_RX, d);
}

HAL_StatusTypeDef HAL_I2C_Master_Receive_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size)
{
  (void)hi2c;
  if (!bus_free()) return HAL_BUSY;
  rx_dest = data; rx_len = size < I2C_SIM_BUF ? size : I2C_SIM_BUF;
  sim_dev *d = begin(addr, 1);
  if (d) read_into(d, data, size, model_read(d->kind, (int)(d - devs), rx_buf, rx_len));
  return HAL_OK;
}

HAL_StatusTypeDef HAL_I2C_Mem_Read_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint16_t mem, uint16_t mem_size,
                                      uint8_t *data, uint16_t size)
{
  (void)hi2c; (void)mem_size;
  if (!bus_free()) return HAL_BUSY;
  rx_dest = data; rx_len = size < I2C_SIM_BUF ? size : I2C_SIM_BUF;
  sim_dev *d = begin(addr, 1);
  if (d) read_into(d, data, size, model_mem_read(d->kind, (int)(d - devs), (uint8_t)mem, rx_buf, rx_len));
  if (pending_kind == DONE_RX) pending_kind = DONE_MEMRX;
  return HAL_OK;
}

/* ---- the I2C2 interrupt ---- */
static int i2c_pending(uint64_t *at) { *at = pending_due; return pending_kind != DONE_NONE; }
static void i2c_fire(void)
{
  int kind = pending_kind; pending_kind = DONE_NONE;
  if (!irq_enabled) return;
  if (kind == DONE_TX) HAL_I2C_MasterTxCpltCallback(handle);
  else if (kind == DONE_RX || kind == DONE_MEMRX)
  {
    memcpy(rx_dest, rx_buf, rx_len);
    if (kind == DONE_RX) HAL_I2C_MasterRxCpltCallback(handle);
    else HAL_I2C_MemRxCpltCallback(handle);
  }
  else HAL_I2C_ErrorCallback(handle);
}
const sim_source i2c_sim_source = { i2c_pending, i2c_fire, SIM_IRQ_I2C2_EV };

uint32_t i2c_sim_transfers(void) { return transfers; }
uint32_t i2c_sim_deinits(void) { return deinits; }
int i2c_sim_scl_edges(void) { return scl_edges; }
int i2c_sim_ready(void) { return i2c_inited && irq_enabled; }
int i2c_sim_pin_errors(void) { return pin_errors; }
int i2c_sim_power(void) { return power_on; }
int i2c_sim_complete_at_guard(int error)
{
  if (pending_kind != DONE_NONE || !rx_dest) return 0;
  pending_kind = error ? DONE_ERROR : DONE_RX; pending_due = sim_timer_due(started_at, 30);
  return 1;
}
