#include "sensor.h"
#include "stm32wlxx_hal.h"
#include "stage0.h"

#define SDA_PIN GPIO_PIN_11
#define SCL_PIN GPIO_PIN_12
#define I2C_TIMEOUT_MS 50
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
}

void HAL_I2C_MspDeInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
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
  HAL_I2C_Init(&hi2c2);
  HAL_I2CEx_ConfigAnalogFilter(&hi2c2, I2C_ANALOGFILTER_ENABLE);
}

/* Stuck-bus recovery: a sensor reset mid-byte can hold SDA low. The pin sequence (clock SCL
 * until SDA is free, then a real STOP) is ws_i2c_recover() in firmware/stage0.c, host-tested in
 * firmware/test_policy.c. Both lines are released (output register high) before they become
 * outputs, so taking them over never drives SCL low by accident. */
static void pin_scl(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SCL_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static void pin_sda(void *c, int level) { (void)c; HAL_GPIO_WritePin(GPIOA, SDA_PIN, level ? GPIO_PIN_SET : GPIO_PIN_RESET); }
static int pin_read_sda(void *c) { (void)c; return HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET; }
static void pin_wait(void *c, uint32_t us) { (void)c; (void)us; HAL_Delay(1); } /* >= one half period */

static int i2c_recover(void)
{
  HAL_I2C_DeInit(&hi2c2);
  HAL_GPIO_WritePin(GPIOA, SDA_PIN | SCL_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_OUTPUT_OD, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &gpio);
  const ws_i2c_pins pins = { 0, pin_scl, pin_sda, pin_read_sda, pin_wait };
  int rc = ws_i2c_recover(&pins);
  i2c_start();
  return rc;
}

/* ws_i2c callbacks take the 7-bit address; the STM32 HAL wants it shifted left. */
static int bus_write(void *ctx, uint8_t addr, const uint8_t *data, size_t n)
{
  (void)ctx;
  /* ST's HAL takes a non-const buffer it only reads; copy instead of casting const away. */
  uint8_t buf[8];
  if (n > sizeof buf) return 1;
  for (size_t i = 0; i < n; i++) buf[i] = data[i];
  return HAL_I2C_Master_Transmit(&hi2c2, (uint16_t)(addr << 1), buf, (uint16_t)n, I2C_TIMEOUT_MS) != HAL_OK;
}
static int bus_read(void *ctx, uint8_t addr, uint8_t *data, size_t n)
{
  (void)ctx;
  return HAL_I2C_Master_Receive(&hi2c2, (uint16_t)(addr << 1), data, (uint16_t)n, I2C_TIMEOUT_MS) != HAL_OK;
}
static void bus_delay(void *ctx, uint32_t ms) { (void)ctx; HAL_Delay(ms); }

void sensor_init(void) { i2c_start(); }

int sensor_read(int16_t *centi_c, uint16_t *centi_rh)
{
  const ws_i2c bus = { 0, bus_write, bus_read, bus_delay };
  int rc = ws_sht45_read(&bus, centi_c, centi_rh);
  if (rc && i2c_recover()) rc = SENSOR_BUS_STUCK;
  return rc;
}
