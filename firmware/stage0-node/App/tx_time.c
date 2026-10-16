#include "tx_time.h"
#include "clock.h"
#include "rtc.h"
#include "stm32_systime.h"
#include "stm32wlxx_hal.h"
#include "sys_app.h"

#define SYNC_VALID_S        (6UL * 3600UL)          /* trust a sync for 6 h (32 kHz crystal drift; see gateway DRIFT_PPM) */
/* DR0-DR2 belong to ST's timer_if/SysTime. */
#define BKP_TIME_MAGIC      0x57535456UL            /* "WSTV" */
#define BKP_REG_MAGIC       RTC_BKP_DR3
#define BKP_REG_SYNC_MCU    RTC_BKP_DR4
#define MIN_PLAUSIBLE_UTC   1767225600ULL           /* 2026-01-01T00:00:00Z */

static int synced;
static uint32_t last_sync_s;   /* clock_s() at the last accepted time sync */

int time_valid(void) { return synced && (clock_s() - last_sync_s) < SYNC_VALID_S; }

uint32_t time_utc(void) { return time_valid() ? SysTimeGet().Seconds : 0; }

void time_restore(void)
{
  uint32_t magic = HAL_RTCEx_BKUPRead(&hrtc, BKP_REG_MAGIC);
  uint32_t at = HAL_RTCEx_BKUPRead(&hrtc, BKP_REG_SYNC_MCU);
  uint32_t now = clock_s();
  if (magic == BKP_TIME_MAGIC && now >= at && now - at < SYNC_VALID_S && SysTimeGet().Seconds >= MIN_PLAUSIBLE_UTC)
  {
    synced = 1;
    last_sync_s = at;
    APP_PRINTF("#time restored utc=%u sync_age=%u\n", (unsigned)SysTimeGet().Seconds, (unsigned)(now - at));
  }
  else
  {
    HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_MAGIC, 0);
  }
}

int time_sync(uint32_t utc)
{
  if (utc < MIN_PLAUSIBLE_UTC) return 0;
  SysTime_t now = { .Seconds = utc, .SubSeconds = 0 };
  SysTimeSet(now);
  synced = 1;
  last_sync_s = clock_s();
  HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_SYNC_MCU, last_sync_s);
  HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_MAGIC, BKP_TIME_MAGIC);
  return 1;
}
