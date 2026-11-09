#include "leds.h"
#include "board_pins.h"
#include "main.h"
#include "stm32_timer.h"

/* The board's (Core/Inc/board_pins.h): the NUCLEO's three, on when high; the Wio-E5 mini's one (blue), on
   when low, and pin 0 for the others, which makes their writes no-ops (only blue's pin is ever read). */
static GPIO_TypeDef *const port[] = BOARD_LED_PORTS;
static const uint16_t pin[] = BOARD_LED_PINS;
static UTIL_TIMER_Object_t off_timer[LED_COUNT];
static UTIL_TIMER_Object_t heartbeat_timer;

#define HEARTBEAT_PERIOD_MS 2000U
#define HEARTBEAT_BLIP_MS   40U

/* cppcheck-suppress constParameterCallback ; ST's UTIL_TIMER callback signature */
static void off(void *ctx) { led_t led = (led_t)(uintptr_t)ctx; HAL_GPIO_WritePin(port[led], pin[led], BOARD_LED_OFF); }

/* "Alive" blip on blue; skipped while blue is already showing real radio traffic. */
static void heartbeat(void *ctx)
{
  (void)ctx;
  if (HAL_GPIO_ReadPin(port[LED_BLUE], pin[LED_BLUE]) == BOARD_LED_OFF) led_flash(LED_BLUE, HEARTBEAT_BLIP_MS);
}

void leds_init(void)
{
  for (uintptr_t i = 0; i < LED_COUNT; i++)
  {
    (void)UTIL_TIMER_Create(&off_timer[i], LED_FLASH_MS, UTIL_TIMER_ONESHOT, off, (void *)i);   /* led_flash sets the period */
    HAL_GPIO_WritePin(port[i], pin[i], BOARD_LED_OFF);
  }
  (void)UTIL_TIMER_Create(&heartbeat_timer, HEARTBEAT_PERIOD_MS, UTIL_TIMER_PERIODIC, heartbeat, NULL);
  (void)UTIL_TIMER_Start(&heartbeat_timer);
}

void led_flash(led_t led, uint32_t ms)
{
  HAL_GPIO_WritePin(port[led], pin[led], BOARD_LED_ON);
  (void)UTIL_TIMER_Stop(&off_timer[led]);
  (void)UTIL_TIMER_SetPeriod(&off_timer[led], ms);
  (void)UTIL_TIMER_Start(&off_timer[led]);
}

void led_set(led_t led, int on)
{
  (void)UTIL_TIMER_Stop(&off_timer[led]);
  HAL_GPIO_WritePin(port[led], pin[led], on ? BOARD_LED_ON : BOARD_LED_OFF);
}
