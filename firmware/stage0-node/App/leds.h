#ifndef LEDS_H
#define LEDS_H
#include <stdint.h>
/* Nucleo user LEDs as activity indicators (meanings: firmware/stage0-node/README.md, LEDs).
 * LED1 blue = radio traffic (400 ms) or 40 ms "alive" blip every 2 s, LED2 green = ACK,
 * LED3 red = problem. */
typedef enum { LED_BLUE, LED_GREEN, LED_RED, LED_COUNT } led_t;
#define LED_FLASH_MS      400U    /* one event: a frame, an ACK, a failure */
#define LED_FLASH_LONG_MS 1000U   /* a record abandoned */
void leds_init(void);
void led_flash(led_t led, uint32_t ms); /* on now, off after ms */
void led_set(led_t led, int on);        /* steady state; cancels a pending flash-off */
#endif
