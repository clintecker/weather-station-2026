/* GENERATED from i2c_bus.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/i2c_bus.lit.md (tests/test_tangle.py checks this file). */
#define WS_CHECK_FILE 12
#include "i2c_bus.h"
#include "busymon.h"
#include "events.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "utilities_def.h"
#include "ws_check.h"

#define SDA_PIN GPIO_PIN_11
#define SCL_PIN GPIO_PIN_12
#define POWER_PIN GPIO_PIN_9
/* No transfer completes later than this. The longest is a 7-byte reply, ~0.8 ms at 100 kHz. The
   guard is longer than a flash page erase (24.5 ms max), which stalls the I2C interrupt. ST's timer
   rounds down to 1/1024 s ticks. */
#define I2C_GUARD_MS 30
#define I2C_IRQ_PRIORITY 2   /* below the radio and the RTC (0), like the console UART */
/* 100 kHz standard mode at PCLK1 = 48 MHz (same value as ST's NUCLEO-WL55JC I2C examples). */
#define I2C_TIMING 0x20303E5DU
#define REG_ADDR_LEN 1U
#define HAL_ADDR(a7) ((uint16_t)((a7) << 1))   /* ST's HAL takes the 7-bit address shifted left */

static I2C_HandleTypeDef hi2c2;

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_I2C2,
                                   .I2c2ClockSelection = RCC_I2C2CLKSOURCE_PCLK1 };
  (void)HAL_RCCEx_PeriphCLKConfig(&clk);   /* selects the I2C2 clock only, so it cannot time out */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_AF_OD, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF4_I2C2 };
  HAL_GPIO_Init(GPIOA, &gpio);
  __HAL_RCC_I2C2_CLK_ENABLE();
  HAL_NVIC_SetPriority(I2C2_EV_IRQn, I2C_IRQ_PRIORITY, 0);
  HAL_NVIC_SetPriority(I2C2_ER_IRQn, I2C_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(I2C2_EV_IRQn);
  HAL_NVIC_EnableIRQ(I2C2_ER_IRQn);
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspDeInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
  HAL_NVIC_DisableIRQ(I2C2_EV_IRQn);
  HAL_NVIC_DisableIRQ(I2C2_ER_IRQn);
  __HAL_RCC_I2C2_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOA, SDA_PIN | SCL_PIN);
}

static void i2c_start(void)
{
  hi2c2.Instance = I2C2;
  hi2c2.Init.Timing = I2C_TIMING;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  /* Both calls fail only for a NULL or busy handle (stm32wlxx_hal_i2c.c). If one fails anyway, the
     HAL refuses the next transfer, and the recovery after it starts the peripheral again. */
  (void)WS_CHECK(HAL_I2C_Init(&hi2c2) == HAL_OK);
  (void)WS_CHECK(HAL_I2CEx_ConfigAnalogFilter(&hi2c2, I2C_ANALOGFILTER_ENABLE) == HAL_OK);
}

typedef struct { const uint8_t *tx; uint8_t *rx; uint8_t addr7, txlen, rxlen; } xfer_t;
static xfer_t xfers[I2C_C_COUNT];
static uint8_t busy[I2C_C_COUNT];      /* 1: the client's transfer is queued or running */
static uint8_t fifo[I2C_C_COUNT];
static unsigned fifo_head, fifo_len;

static void fifo_push(enum i2c_client c)
{
  fifo[(fifo_head + fifo_len) % I2C_C_COUNT] = (uint8_t)c;
  fifo_len++;
}

static enum i2c_client fifo_pop(void)
{
  enum i2c_client c = (enum i2c_client)fifo[fifo_head];
  fifo_head = (fifo_head + 1U) % I2C_C_COUNT;
  fifo_len--;
  return c;
}

typedef enum { S_IDLE, S_XFER, S_DONE, S_RECOVER, S_RECOVERED } bus_state;
static volatile bus_state st = S_IDLE;
static volatile int bus_rc, recover_rc;
static enum i2c_client cur;            /* the client of the transfer on the bus */
static int failed_rc;                  /* the failed transfer's code, reported after the recovery */
static UTIL_TIMER_Object_t guard_timer, step_timer;
static ws_i2c_rec rec;

static void post(void) { UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_I2c, CFG_SEQ_Prio_0); }

static void finish(int rc)
{
  uint32_t primask = irq_lock();
  if (st == S_XFER)
  {
    (void)UTIL_TIMER_Stop(&guard_timer);
    bus_rc = rc; st = S_DONE; post();
  }
  irq_unlock(primask);
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c2) finish(I2C_OK); }
/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c2) finish(I2C_OK); }
/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MemRxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c2) finish(I2C_OK); }
/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c)
{
  if (hi2c == &hi2c2) finish(xfers[cur].txlen == 0 ? I2C_ENACK_DATA : I2C_ENACK_ADDR);
}
static void on_guard(void *ctx) { (void)ctx; finish(I2C_ETIMEOUT); }

void I2C2_EV_IRQHandler(void);   /* vector table names (startup_stm32wl55jcix.s) */
void I2C2_ER_IRQHandler(void);
void I2C2_EV_IRQHandler(void) { BUSYMON_ISR("I2C2_EV", HAL_I2C_EV_IRQHandler(&hi2c2)); }
void I2C2_ER_IRQHandler(void) { BUSYMON_ISR("I2C2_ER", HAL_I2C_ER_IRQHandler(&hi2c2)); }

static HAL_StatusTypeDef hal_start(const xfer_t *x)
{
  uint16_t a = HAL_ADDR(x->addr7);
  if (x->rxlen == 0) return HAL_I2C_Master_Transmit_IT(&hi2c2, a, (uint8_t *)(uintptr_t)x->tx, x->txlen);
  if (x->txlen == 0) return HAL_I2C_Master_Receive_IT(&hi2c2, a, x->rx, x->rxlen);
  return HAL_I2C_Mem_Read_IT(&hi2c2, a, x->tx[0], I2C_MEMADD_SIZE_8BIT, x->rx, x->rxlen);
}

static void recover_begin(void);

static void kick(void)
{
  if (st != S_IDLE || fifo_len == 0) return;
  cur = fifo_pop();
  if (xfers[cur].txlen == 0 && xfers[cur].rxlen == 0) { failed_rc = I2C_OK; recover_begin(); return; }
  st = S_XFER;
  (void)WS_CHECK(UTIL_TIMER_Start(&guard_timer) == UTIL_TIMER_OK);   /* stopped by finish() */
  if (hal_start(&xfers[cur]) != HAL_OK) finish(I2C_ENACK_ADDR);
}

/* The four forms of i2c_bus.h: write, read, a register address and then a read, or recover only. */
static int form_ok(const uint8_t *tx, uint8_t txlen, const uint8_t *rx, uint8_t rxlen)
{
  if (rxlen == 0) return txlen == 0 || tx != NULL;
  if (txlen == 0) return rx != NULL;
  return txlen == REG_ADDR_LEN && tx && rx;
}

int i2c_bus_submit(enum i2c_client c, uint8_t addr7, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen)
{
  if ((unsigned)c >= I2C_C_COUNT || !form_ok(tx, txlen, rx, rxlen) || busy[c]) return -1;
  xfers[c] = (xfer_t){ .tx = tx, .rx = rx, .addr7 = addr7, .txlen = txlen, .rxlen = rxlen };
  busy[c] = 1;
  fifo_push(c);
  kick();
  return 0;
}

static void pin_scl(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SCL_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static void pin_sda(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SDA_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static int pin_read_sda(void *c) { (void)c; return HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET; }
static const ws_i2c_pins pins = { 0, pin_scl, pin_sda, pin_read_sda, 0 };

static void on_step(void *ctx)
{
  (void)ctx;
  int rc = ws_i2c_recover_step(&rec, &pins);
  if (rc > 0) { (void)WS_CHECK(UTIL_TIMER_Start(&step_timer) == UTIL_TIMER_OK); return; }
  recover_rc = rc; st = S_RECOVERED; post();
}

static void recover_begin(void)
{
  (void)HAL_I2C_DeInit(&hi2c2);   /* fails only for a NULL handle. The code below takes the pins over anyway */
  /* An abandoned transfer can leave its interrupt pending and its handler set. Neither may run on
     the re-initialised peripheral. */
  HAL_NVIC_ClearPendingIRQ(I2C2_EV_IRQn); HAL_NVIC_ClearPendingIRQ(I2C2_ER_IRQn);
  hi2c2.XferISR = NULL;
  HAL_GPIO_WritePin(GPIOA, SDA_PIN | SCL_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_OUTPUT_OD, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &gpio);
  st = S_RECOVER;
  ws_i2c_recover_begin(&rec, &pins);
  (void)WS_CHECK(UTIL_TIMER_Start(&step_timer) == UTIL_TIMER_OK);
}

static void deliver(int rc)
{
  enum i2c_client c = cur;
  busy[c] = 0;
  st = S_IDLE;
  i2c_bus_done(c, rc);
  kick();
}

static void bus_task(void)
{
  if (st == S_DONE)
  {
    if (bus_rc != I2C_OK) { failed_rc = bus_rc; recover_begin(); return; }
    deliver(I2C_OK);
  }
  else if (WS_CHECK(st == S_RECOVERED))   /* the task is posted only with S_DONE or S_RECOVERED */
  {
    i2c_start();
    deliver(recover_rc ? I2C_ESTUCK : failed_rc);
  }
}
BUSYMON_TASK(bus_task)

void i2c_bus_power(int on) { HAL_GPIO_WritePin(GPIOA, POWER_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET); }

void i2c_bus_init(void)
{
  (void)UTIL_TIMER_Create(&guard_timer, I2C_GUARD_MS, UTIL_TIMER_ONESHOT, on_guard, NULL);
  (void)UTIL_TIMER_Create(&step_timer, 1, UTIL_TIMER_ONESHOT, on_step, NULL);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_I2c, UTIL_SEQ_RFU, bus_task_timed);
  GPIO_InitTypeDef gpio = { .Pin = POWER_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  __HAL_RCC_GPIOA_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA, POWER_PIN, GPIO_PIN_SET);
  HAL_GPIO_Init(GPIOA, &gpio);
  i2c_start();
}
