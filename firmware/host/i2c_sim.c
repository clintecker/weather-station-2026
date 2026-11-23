/* The I2C2 bus with many devices on the host (see i2c_sim.h). A transfer completes through the HAL
 * callbacks that HAL_I2C_EV_IRQHandler would call (I2C2 interrupt, priority 2), after the device's
 * latency. HAL_I2C_DeInit cancels a completion in flight. During the stuck-bus recovery SDA stays low
 * until the held number of SCL rising edges. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "i2c_bus.h"   /* WS_I2C_MUX, the bus profile: the model follows the firmware's */
#include "i2c_sim.h"
#include "stm32wlxx_hal.h"

enum { DONE_NONE, DONE_TX, DONE_RX, DONE_MEMRX, DONE_ERROR, DONE_BUS_ERROR };   /* DONE_ERROR: a NACK */
typedef struct { int kind, mode, present, sda_hold, channel, switched, fail_mode; uint8_t addr7; uint32_t latency_ms, writes, fail_in; } sim_dev;
static sim_dev devs[I2C_SIM_DEVICES];
static int ndevs, i2c_inited, irq_enabled, pending_kind, power_on, mux_dev = -1;
static uint8_t mux_mask;
static uint32_t mux_resets, upstream_with_channel;
#define ADDR_LOG 64
static int addr_log[ADDR_LOG], naddr_log;
static uint64_t pending_due, started_at;
static uint8_t *rx_dest;
static uint8_t rx_buf[I2C_SIM_BUF];
static uint16_t rx_len;
static uint32_t transfers, deinits;
static uint32_t addr_transfers[128];   /* transfers to each 7-bit address, a device there or not */
static I2C_HandleTypeDef *handle;
GPIO_TypeDef host_gpioa;
I2C_TypeDef host_i2c2;

int i2c_sim_add_on(int kind, uint8_t addr7, int channel)
{
  if (ndevs >= I2C_SIM_DEVICES) return -1;
  devs[ndevs] = (sim_dev){ .kind = kind, .mode = DM_OK, .present = 1, .addr7 = addr7, .latency_ms = 1, .channel = channel };
  model_reset(kind, ndevs);
  return ndevs++;
}
/* The static channel map of the mux profile, for a part of the probe table. The upstream kinds (the
   SHTC3, INA228, MAX17048, BQ25798 and the mux itself) never go behind a channel, whatever their address: an
   INA228 strapped to 0x44, 0x46 or 0x47 stays upstream. */
static int port_channel(int kind, uint8_t addr7)
{
  if (kind == DEVK_SHTC3 || kind == DEVK_INA228 || kind == DEVK_MAX17048 || kind == DEVK_BQ25798 || kind == DEVK_MUX)
    return I2C_SIM_UPSTREAM;
  return addr7 == 0x44 ? 0 : addr7 == 0x53 ? 1 : (addr7 == 0x47 || addr7 == 0x46) ? 2 : I2C_SIM_UPSTREAM;
}
int i2c_sim_add(int kind, uint8_t addr7)
{
  return i2c_sim_add_on(kind, addr7, WS_I2C_MUX ? port_channel(kind, addr7) : I2C_SIM_UPSTREAM);
}
/* The board's mux, there from the peripheral's first start (a test may remove it); none on the hub. */
static void board_mux(void)
{
  if (WS_I2C_MUX && mux_dev < 0) mux_dev = i2c_sim_add_on(DEVK_MUX, 0x71, I2C_SIM_UPSTREAM);
}
int i2c_sim_mux_device(void) { return mux_dev; }
uint8_t i2c_sim_mux_mask(void) { return mux_mask; }
void i2c_sim_mux_set_mask(uint8_t mask) { mux_mask = mask; }
uint32_t i2c_sim_mux_resets(void) { return mux_resets; }
uint32_t i2c_sim_upstream_with_channel(void) { return upstream_with_channel; }
int i2c_sim_addr_log(int i) { return i >= 0 && i < naddr_log ? addr_log[i] : -1; }
void i2c_sim_remove(int dev) { if (dev >= 0 && dev < ndevs) devs[dev].present = 0; }
void i2c_sim_restore(int dev) { if (dev >= 0 && dev < ndevs) devs[dev].present = 1; }
void i2c_sim_switched(int dev, int switched) { if (dev >= 0 && dev < ndevs) devs[dev].switched = switched != 0; }
void i2c_sim_mode(int dev, int mode, int sda_hold_edges, uint32_t latency_ms)
{
  if (dev < 0 || dev >= ndevs) return;
  devs[dev].mode = mode; devs[dev].sda_hold = sda_hold_edges; devs[dev].latency_ms = latency_ms;
}
void i2c_sim_fail_nth(int dev, uint32_t n, int mode)
{
  if (dev < 0 || dev >= ndevs) return;
  devs[dev].fail_in = n; devs[dev].fail_mode = mode;
}
/* The device's mode for the transfer starting now: an armed one-shot failure (i2c_sim_fail_nth) when its
   count runs out, else its own. */
static int mode_now(sim_dev *d)
{
  if (d->fail_in && --d->fail_in == 0) return d->fail_mode;
  return d->mode;
}

/* ---- NVIC, RCC and the peripheral ---- */
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)irq; (void)pre; (void)sub; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { (void)irq; irq_enabled = 1; }
void HAL_NVIC_DisableIRQ(IRQn_Type irq) { (void)irq; irq_enabled = 0; }
void HAL_NVIC_ClearPendingIRQ(IRQn_Type irq) { (void)irq; pending_kind = DONE_NONE; }
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk) { (void)clk; return HAL_OK; }
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef *hi2c) { board_mux(); handle = hi2c; HAL_I2C_MspInit(hi2c); i2c_inited = 1; return HAL_OK; }
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

/* ---- the mux RESET line (i2c_bus.h): the mask clears, and a held SDA is no longer joined ---- */
void i2c_bus_mux_reset_line(int asserted)
{
  if (!asserted) return;
  mux_resets++;
  mux_mask = 0;
  sda_release_at = scl_edges;
}

/* ---- transfers ---- */
/* On the bus: powered (an unswitched device always; a switched one only while PA9 is high) and
   upstream or behind a selected channel. */
static int on_bus(const sim_dev *d) { return (!d->switched || power_on) && (d->channel < 0 || (mux_mask >> d->channel & 1U)); }
static sim_dev *find(uint16_t addr)
{
  for (int i = 0; i < ndevs; i++)
    if (devs[i].present && devs[i].addr7 == (addr >> 1) && on_bus(&devs[i])) return &devs[i];
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
  return d->mode == DM_HANG || d->mode == DM_NACK_ADDR || d->mode == DM_BUS_ERROR ||
         (is_read && (d->mode == DM_NACK_DATA || d->mode == DM_HANG_READ));
}

/* Counts a transfer: the parts' (not the mux's), each address's, the address log, and an upstream
   part addressed with a channel selected. */
static void count(uint16_t addr, const sim_dev *d)
{
  if ((addr >> 1) != 0x71U) transfers++;
  addr_transfers[(addr >> 1) & 0x7FU]++;
  if (naddr_log < ADDR_LOG) addr_log[naddr_log++] = addr >> 1;
  if (d && d->channel < 0 && d->kind != DEVK_MUX && mux_mask) upstream_with_channel++;
}

static sim_dev *begin(uint16_t addr, int is_read)
{
  sim_dev *d = find(addr);
  int mode = d ? mode_now(d) : DM_NACK_ADDR;
  started_at = sim_now();
  count(addr, d);
  if (d && d->sda_hold && faulty(d, is_read)) sda_release_at = scl_edges + d->sda_hold;
  if (mode == DM_NACK_ADDR) { complete_in(DONE_ERROR, d); return NULL; }
  if (mode == DM_BUS_ERROR) { complete_in(DONE_BUS_ERROR, d); return NULL; }
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
  if (find(addr)) find(addr)->writes++;   /* a write attempt, served or not */
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
  uint16_t at = mem_size == I2C_MEMADD_SIZE_16BIT ? mem : (uint8_t)mem;
  if (!bus_free()) return HAL_BUSY;
  (void)hi2c;
  rx_dest = data; rx_len = size < I2C_SIM_BUF ? size : I2C_SIM_BUF;
  sim_dev *d = begin(addr, 1);
  if (d) read_into(d, data, size, model_mem_read(d->kind, (int)(d - devs), at, rx_buf, rx_len));
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
  else { handle->ErrorCode = kind == DONE_BUS_ERROR ? HAL_I2C_ERROR_BERR : HAL_I2C_ERROR_AF; HAL_I2C_ErrorCallback(handle); }
}
const sim_source i2c_sim_source = { i2c_pending, i2c_fire, SIM_IRQ_I2C2_EV };

uint32_t i2c_sim_transfers(void) { return transfers; }
uint32_t i2c_sim_addr_transfers(int addr7) { return addr_transfers[addr7 & 0x7F]; }
uint32_t i2c_sim_writes(int dev) { return dev >= 0 && dev < ndevs ? devs[dev].writes : 0U; }
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
