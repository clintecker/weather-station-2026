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
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_AF_OD, .Pull = GPIO_NOPULL,
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

/* Stuck-bus recovery: a sensor reset mid-byte can hold SDA low. Clock SCL up to nine
 * times by hand until SDA is released, then issue a STOP and restart the peripheral. */
static void i2c_recover(void)
{
  HAL_I2C_DeInit(&hi2c2);
  GPIO_InitTypeDef gpio = { .Pin = SCL_PIN, .Mode = GPIO_MODE_OUTPUT_OD, .Pull = GPIO_NOPULL,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = SDA_PIN;
  HAL_GPIO_Init(GPIOA, &gpio);
  HAL_GPIO_WritePin(GPIOA, SDA_PIN, GPIO_PIN_SET);
  for (int i = 0; i < 9 && HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_RESET; i++)
  {
    HAL_GPIO_WritePin(GPIOA, SCL_PIN, GPIO_PIN_RESET); HAL_Delay(1);
    HAL_GPIO_WritePin(GPIOA, SCL_PIN, GPIO_PIN_SET); HAL_Delay(1);
  }
  HAL_GPIO_WritePin(GPIOA, SDA_PIN, GPIO_PIN_RESET); HAL_Delay(1); /* STOP: SDA rises while SCL high */
  HAL_GPIO_WritePin(GPIOA, SDA_PIN, GPIO_PIN_SET); HAL_Delay(1);
  i2c_start();
}

/* ws_i2c callbacks take the 7-bit address; the STM32 HAL wants it shifted left. */
static int bus_write(void *ctx, uint8_t addr, const uint8_t *data, size_t n)
{
  (void)ctx;
  return HAL_I2C_Master_Transmit(&hi2c2, (uint16_t)(addr << 1), (uint8_t *)data, (uint16_t)n, I2C_TIMEOUT_MS) != HAL_OK;
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
  if (rc) i2c_recover();
  return rc;
}
