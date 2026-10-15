#ifndef HOST_RTC_H
#define HOST_RTC_H
#include <stdint.h>
typedef struct { int unused; } RTC_HandleTypeDef;
extern RTC_HandleTypeDef hrtc;
enum { RTC_BKP_DR0, RTC_BKP_DR1, RTC_BKP_DR2, RTC_BKP_DR3, RTC_BKP_DR4, RTC_BKP_COUNT = 20 };
uint32_t HAL_RTCEx_BKUPRead(RTC_HandleTypeDef *h, uint32_t reg);
void HAL_RTCEx_BKUPWrite(RTC_HandleTypeDef *h, uint32_t reg, uint32_t value);
#endif
