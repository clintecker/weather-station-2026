#include "leds.h"
#include "main.h"
#include "stm32_timer.h"

static GPIO_TypeDef *const port[] = { LED1_GPIO_Port, LED2_GPIO_Port, LED3_GPIO_Port };
static const uint16_t pin[] = { LED1_Pin, LED2_Pin, LED3_Pin };
static UTIL_TIMER_Object_t off_timer[3];
static UTIL_TIMER_Object_t heartbeat_timer;

#define HEARTBEAT_PERIOD_MS 2000U
#define HEARTBEAT_BLIP_MS   40U

static void off(void *ctx) { led_t led = (led_t)(uintptr_t)ctx; HAL_GPIO_WritePin(port[led], pin[led], GPIO_PIN_RESET); }

/* "Alive" blip on blue; skipped while blue is already showing real radio traffic. */
static void heartbeat(void *ctx)
{
  (void)ctx;
  if (HAL_GPIO_ReadPin(port[LED_BLUE], pin[LED_BLUE]) == GPIO_PIN_RESET) led_flash(LED_BLUE, HEARTBEAT_BLIP_MS);
}

void leds_init(void)
{
  for (uintptr_t i = 0; i < 3; i++)
  {
    UTIL_TIMER_Create(&off_timer[i], 100, UTIL_TIMER_ONESHOT, off, (void *)i);
    HAL_GPIO_WritePin(port[i], pin[i], GPIO_PIN_RESET);
  }
  UTIL_TIMER_Create(&heartbeat_timer, HEARTBEAT_PERIOD_MS, UTIL_TIMER_PERIODIC, heartbeat, NULL);
  UTIL_TIMER_Start(&heartbeat_timer);
}

void led_flash(led_t led, uint32_t ms)
{
  HAL_GPIO_WritePin(port[led], pin[led], GPIO_PIN_SET);
  UTIL_TIMER_Stop(&off_timer[led]);
  UTIL_TIMER_SetPeriod(&off_timer[led], ms);
  UTIL_TIMER_Start(&off_timer[led]);
}

void led_set(led_t led, int on)
{
  UTIL_TIMER_Stop(&off_timer[led]);
  HAL_GPIO_WritePin(port[led], pin[led], on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
