#ifndef HOST_STM32_TIMER_H
#define HOST_STM32_TIMER_H
#include <stdint.h>
typedef enum { UTIL_TIMER_ONESHOT, UTIL_TIMER_PERIODIC } UTIL_TIMER_Mode_t;
typedef struct UTIL_TIMER_Object_s {
  uint32_t period, due; int running; UTIL_TIMER_Mode_t mode;
  void (*cb)(void *); void *arg; struct UTIL_TIMER_Object_s *next;
} UTIL_TIMER_Object_t;
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg);
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t);
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t);
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period);
#endif
