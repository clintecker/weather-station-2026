#ifndef HOST_STM32_SYSTIME_H
#define HOST_STM32_SYSTIME_H
#include <stdint.h>
typedef struct { uint32_t Seconds; int16_t SubSeconds; } SysTime_t;
SysTime_t SysTimeGet(void);
void SysTimeSet(SysTime_t t);
SysTime_t SysTimeGetMcuTime(void);
#endif
