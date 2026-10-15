#ifndef CLOCK_H
#define CLOCK_H
#include <stdint.h>
/* The node's clock (both roles), from the RTC: MCU time keeps counting through a reset, and
 * SysTimeSet() (the TX time sync) does not move it. Never HAL_GetTick: on this board that counts
 * 1/1024 s RTC ticks (timer_if.c), not milliseconds (docs/firmware-event-model.md). */
uint32_t clock_ms(void);   /* milliseconds; wraps after 49 days, so every use is a difference */
uint32_t clock_s(void);    /* whole seconds */
#endif
