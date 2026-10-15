#ifndef HOST_STM32_SEQ_H
#define HOST_STM32_SEQ_H
#include <stdint.h>
#define UTIL_SEQ_RFU 0
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*task)(void));
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio);
#endif
