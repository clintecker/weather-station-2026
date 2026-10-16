#ifndef CLOCK_H
#define CLOCK_H
#include <stdint.h>
/* The node's clock (both roles), from the RTC: MCU time keeps counting through a reset (except
 * that the board's timer_if.c clears the high word at boot, so after 48.5 days of power a warm
 * reset steps it back by 48.5 days; tx_time.c then refuses to restore time trust), and
 * SysTimeSet() (the TX time sync) does not move it. Never HAL_GetTick: on this board that counts
 * 1/1024 s RTC ticks (timer_if.c), not milliseconds (docs/firmware-event-model.md). */
#define CLOCK_MS_PER_S   1000U
#define CLOCK_MS_PER_MIN 60000UL
#define CLOCK_US_PER_S   1000000UL
uint32_t clock_ms(void);   /* milliseconds; wraps after 49 days, so every use is a difference */
uint32_t clock_s(void);    /* whole seconds */
#endif
