#ifndef EVENTS_H
#define EVENTS_H
#include <stdint.h>
#include "stm32wlxx_hal.h"
/* Interrupt-safe building blocks (both roles and the sensor driver).
 *
 * irq_lock / irq_unlock: a critical section that restores the previous interrupt mask, so it may
 * be used where interrupts are already masked (UTIL_TIMER callbacks run that way). */
static inline uint32_t irq_lock(void) { uint32_t primask = __get_PRIMASK(); __disable_irq(); return primask; }
static inline void irq_unlock(uint32_t primask) { __set_PRIMASK(primask); }

/* Radio and timer events for the role's process task (CFG_SEQ_Task_SubGHz_Phy_App_Process), as
 * bits: several events can arrive before the task runs and none is lost (firmware review finding
 * 3: one event slot, cleared at the end of process(), dropped events posted meanwhile).
 * events_post sets bits from any context and posts the task; events_take returns the pending bits
 * and clears them in one step. */
void events_post(volatile uint32_t *pending, uint32_t bits);
uint32_t events_take(volatile uint32_t *pending);
void events_clear(volatile uint32_t *pending, uint32_t bits);   /* drop bits no longer wanted */
#endif
