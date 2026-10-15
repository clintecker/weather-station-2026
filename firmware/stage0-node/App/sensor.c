#define WS_CHECK_FILE 6
#include "sensor.h"
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
/* No transfer completes later than this: a command is 2 bytes, a reply 7, ~0.7 ms at 100 kHz. Longer
   than a flash page erase (24.5 ms max), which stalls the I2C interrupt, so an erase that overlaps a
   transfer does not read as a sensor timeout. ST's timer rounds down to 1/1024 s ticks. */
#define I2C_GUARD_MS 30
#define I2C_IRQ_PRIORITY 2   /* below the radio and the RTC (0), like the console UART */
/* 100 kHz standard mode at PCLK1 = 48 MHz (same value as ST's NUCLEO-WL55JC I2C examples). */
#define I2C_TIMING 0x20303E5DU

static I2C_HandleTypeDef hi2c2;

void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_I2C2,
                                   .I2c2ClockSelection = RCC_I2C2CLKSOURCE_PCLK1 };
  HAL_RCCEx_PeriphCLKConfig(&clk);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  /* Internal pull-ups (~40 kOhm) only define the lines when the breakout (and its 10 kOhm
     pull-ups) is unplugged, so an absent sensor reads as a clean address NACK, not noise. */
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_AF_OD, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF4_I2C2 };
  HAL_GPIO_Init(GPIOA, &gpio);
  __HAL_RCC_I2C2_CLK_ENABLE();
  HAL_NVIC_SetPriority(I2C2_EV_IRQn, I2C_IRQ_PRIORITY, 0);
  HAL_NVIC_SetPriority(I2C2_ER_IRQn, I2C_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(I2C2_EV_IRQn);
  HAL_NVIC_EnableIRQ(I2C2_ER_IRQn);
}

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
  /* Both fail only for a NULL or busy handle (stm32wlxx_hal_i2c.c). Should one fail anyway, the next
     transfer is refused (rc -2) and the bus recovery that follows initialises the peripheral again. */
  (void)WS_CHECK(HAL_I2C_Init(&hi2c2) == HAL_OK);
  (void)WS_CHECK(HAL_I2CEx_ConfigAnalogFilter(&hi2c2, I2C_ANALOGFILTER_ENABLE) == HAL_OK);
}

/* One measurement as a chain of interrupts and timers; nothing waits:
 *   sensor_start: command write (I2C interrupt mode)       S_CMD
 *   write complete (I2C IRQ): measurement timer             S_MEASURE
 *   timer (RTC IRQ): reply read (I2C interrupt mode)       S_READ
 *   read complete (I2C IRQ): sensor task                   S_DONE
 *   sensor task (main loop): CRC check, then sensor_done(), or the stuck-bus recovery first: one pin step
 *   per timer tick (S_RECOVER; ST's timer makes it ~2-3 ms), then sensor_done().
 * A guard timer bounds S_CMD and S_READ; an I2C error ends either. finish() is the one way out of
 * a bus state, under a critical section, so a late completion and the guard cannot both count. */
typedef enum { S_IDLE, S_CMD, S_MEASURE, S_READ, S_DONE, S_RECOVER, S_RECOVERED } sensor_state;
static volatile sensor_state st = S_IDLE;
static volatile int bus_rc, recover_rc;
static uint8_t reply[WS_SHT45_REPLY_LEN];
static UTIL_TIMER_Object_t measure_timer, guard_timer, step_timer;
static ws_i2c_rec rec;

static void post(void) { UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sensor, CFG_SEQ_Prio_0); }

static void finish(int rc)
{
  uint32_t primask = irq_lock();
  if (st == S_CMD || st == S_MEASURE || st == S_READ)
  {
    UTIL_TIMER_Stop(&guard_timer); UTIL_TIMER_Stop(&measure_timer);
    bus_rc = rc; st = S_DONE; post();
  }
  irq_unlock(primask);
}

/* Compare-and-set of the state: the I2C interrupt (priority 2) can be preempted by the guard
 * timer (RTC, priority 0), so a step is taken only if the state is still the expected one. */
static int advance(sensor_state from, sensor_state to)
{
  uint32_t primask = irq_lock();
  int ok = st == from;
  if (ok) st = to;
  irq_unlock(primask);
  return ok;
}

void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c)
{
  if (hi2c != &hi2c2) return;
  /* State change and timers in one critical section: the guard cannot fire in between. */
  uint32_t primask = irq_lock();
  if (st == S_CMD) { st = S_MEASURE; UTIL_TIMER_Stop(&guard_timer); (void)WS_CHECK(UTIL_TIMER_Start(&measure_timer) == UTIL_TIMER_OK); }
  irq_unlock(primask);
}

static void on_measured(void *ctx)
{
  (void)ctx;
  if (!advance(S_MEASURE, S_READ)) return;
  (void)WS_CHECK(UTIL_TIMER_Start(&guard_timer) == UTIL_TIMER_OK);
  if (HAL_I2C_Master_Receive_IT(&hi2c2, (uint16_t)(WS_SHT45_ADDR << 1), reply, sizeof reply) != HAL_OK) finish(-3);
}

void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c2 && st == S_READ) finish(0); }
/* A NACK (no sensor at the address, or not ready) or a bus error. */
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c2) finish(st == S_CMD ? -2 : -3); }
static void on_guard(void *ctx) { (void)ctx; finish(SENSOR_TIMEOUT); }

void I2C2_EV_IRQHandler(void);   /* vector table names (startup_stm32wl55jcix.s) */
void I2C2_ER_IRQHandler(void);
void I2C2_EV_IRQHandler(void) { BUSYMON_ISR("I2C2_EV", HAL_I2C_EV_IRQHandler(&hi2c2)); }
void I2C2_ER_IRQHandler(void) { BUSYMON_ISR("I2C2_ER", HAL_I2C_ER_IRQHandler(&hi2c2)); }

/* Stuck-bus recovery: a sensor reset mid-byte can hold SDA low. The pin sequence (clock SCL
 * until SDA is free, then a real STOP) is ws_i2c_recover_step() in firmware/stage0.c, host-tested
 * in firmware/test_policy.c. Both lines are released (output register high) before they become
 * outputs, so taking them over never drives SCL low by accident. */
static void pin_scl(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SCL_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static void pin_sda(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SDA_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static int pin_read_sda(void *c) { (void)c; return HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET; }
static const ws_i2c_pins pins = { 0, pin_scl, pin_sda, pin_read_sda, 0 };

/* One recovery step per timer tick; the chain ends within WS_I2C_RECOVER_STEPS ticks (stage0.h). The timer asks for 1 ms; ST's timer server makes it at least 3
   RTC ticks (~2-3 ms, timer_if.c MIN_ALARM_DELAY). I2C's 100 kHz half period is 5 us (UM10204
   t_LOW >= 4.7 us); slower is fine. The whole recovery takes ~15-70 ms. */
static void on_step(void *ctx)
{
  (void)ctx;
  int rc = ws_i2c_recover_step(&rec, &pins);
  if (rc > 0) { (void)WS_CHECK(UTIL_TIMER_Start(&step_timer) == UTIL_TIMER_OK); return; }
  recover_rc = rc; st = S_RECOVERED; post();
}

static void recover_begin(void)
{
  (void)HAL_I2C_DeInit(&hi2c2);   /* fails only for a NULL handle; the pins are taken over below either way */
  /* An abandoned transfer can leave its interrupt pending and its handler set; neither may run on
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

static int failed_rc;   /* the reading's failure, reported once the recovery has run */
static void sensor_task(void)
{
  int16_t t = 0; uint16_t h = 0;
  if (st == S_DONE)
  {
    int rc = bus_rc;
    if (rc == 0) rc = ws_sht45_parse(reply, &t, &h);
    if (rc) { failed_rc = rc; recover_begin(); return; }
    st = S_IDLE;
    sensor_done(0, t, h);
  }
  else if (WS_CHECK(st == S_RECOVERED))   /* the task is posted only with S_DONE or S_RECOVERED */
  {
    i2c_start();
    st = S_IDLE;
    sensor_done(recover_rc ? SENSOR_BUS_STUCK : failed_rc, 0, 0);
  }
}
BUSYMON_TASK(sensor_task)

void sensor_init(void)
{
  UTIL_TIMER_Create(&measure_timer, WS_SHT45_MEASURE_MS, UTIL_TIMER_ONESHOT, on_measured, NULL);
  UTIL_TIMER_Create(&guard_timer, I2C_GUARD_MS, UTIL_TIMER_ONESHOT, on_guard, NULL);
  UTIL_TIMER_Create(&step_timer, 1, UTIL_TIMER_ONESHOT, on_step, NULL);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sensor, UTIL_SEQ_RFU, sensor_task_timed);
  i2c_start();
}

int sensor_start(void)
{
  static const uint8_t command[1] = { WS_SHT45_MEASURE };
  if (st != S_IDLE) return -1;
  st = S_CMD;
  (void)WS_CHECK(UTIL_TIMER_Start(&guard_timer) == UTIL_TIMER_OK);   /* stopped by finish() or the write's completion */
  /* ST's HAL takes a non-const buffer it only reads (the static array outlives the transfer). */
  if (HAL_I2C_Master_Transmit_IT(&hi2c2, (uint16_t)(WS_SHT45_ADDR << 1), (uint8_t *)(uintptr_t)command, 1) != HAL_OK) finish(-2);
  return 0;
}
