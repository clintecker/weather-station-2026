#include "clock.h"
#include "stm32_systime.h"

uint32_t clock_ms(void) { SysTime_t t = SysTimeGetMcuTime(); return t.Seconds * CLOCK_MS_PER_S + (uint32_t)t.SubSeconds; }
uint32_t clock_s(void) { return SysTimeGetMcuTime().Seconds; }
