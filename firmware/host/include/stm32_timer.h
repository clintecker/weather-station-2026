/* Host stand-in for ST's stm32_timer.h, implemented by firmware/host/sim_core.c with ST's semantics. */
#ifndef HOST_STM32_TIMER_H
#define HOST_STM32_TIMER_H
#include <stdint.h>
typedef enum { UTIL_TIMER_ONESHOT, UTIL_TIMER_PERIODIC } UTIL_TIMER_Mode_t;
typedef struct UTIL_TIMER_Object_s {
  uint32_t period;            /* ms, as given to Create / SetPeriod */
  uint64_t due;               /* expiry in sim_core time units, while running */
  int running, reload_stopped; UTIL_TIMER_Mode_t mode;
  void (*cb)(void *); void *arg;
  struct UTIL_TIMER_Object_s *next;        /* every timer ever created (the harness's bookkeeping) */
  struct UTIL_TIMER_Object_s *list_next;   /* ST's TimerListHead list: the running timers, by expiry */
} UTIL_TIMER_Object_t;
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg);
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t);
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t);
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period);
#endif
