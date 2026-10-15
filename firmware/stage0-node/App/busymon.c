#define WS_CHECK_FILE 10
#include "busymon.h"
#include "ws_check.h"

static uint32_t peak[BM_KINDS];
static const char *peak_name[BM_KINDS];

void busymon_init(void)
{
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

/* Called from tasks and from interrupts: the compare-and-store is one critical section. */
void busymon_end(bm_kind kind, uint32_t start, const char *name)
{
  uint32_t cycles = DWT->CYCCNT - start;
  if (!WS_CHECK(kind < BM_KINDS)) return;   /* every caller passes a BM_* constant */
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  if (cycles > peak[kind]) { peak[kind] = cycles; peak_name[kind] = name; }
  __set_PRIMASK(primask);
}

/* A debugger can turn the cycle counter off when it attaches or detaches; reading the peaks turns it
   back on, so a report never repeats stale peaks for long. */
uint32_t busymon_peak_us(bm_kind kind)
{
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  return peak[kind] / (SystemCoreClock / 1000000U);
}
const char *busymon_peak_name(bm_kind kind) { return peak_name[kind] ? peak_name[kind] : "none"; }
