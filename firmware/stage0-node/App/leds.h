#ifndef LEDS_H
#define LEDS_H
#include <stdint.h>
/* Nucleo user LEDs as activity indicators (meanings: docs/hardware/nucleo-wl55jc-bringup.md).
 * LED1 blue = radio traffic (400 ms) or 40 ms "alive" blip every 2 s, LED2 green = ACK,
 * LED3 red = problem. */
typedef enum { LED_BLUE, LED_GREEN, LED_RED } led_t;
void leds_init(void);
void led_flash(led_t led, uint32_t ms); /* on now, off after ms */
void led_set(led_t led, int on);        /* steady state; cancels a pending flash-off */
#endif
