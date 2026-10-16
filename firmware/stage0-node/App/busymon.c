#define WS_CHECK_FILE 10
#include "busymon.h"
#include "ws_check.h"

static uint32_t peak[BM_KINDS];
static const char *peak_name[BM_KINDS];
static volatile uint32_t isr_total;   /* cycles in outermost interrupt handlers since boot (wraps) */
static uint32_t isr_depth;            /* handlers running now, nested ones included */
static const char *run_step;          /* the running task's slowest timed step so far */
static uint32_t run_step_cycles;

void busymon_init(void)
{
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static void note_peak(bm_kind kind, uint32_t cycles, const char *name)
{
  if (cycles > peak[kind]) { peak[kind] = cycles; peak_name[kind] = name; }
}

/* Called from tasks and from interrupts: the compare-and-store is one critical section. */
void busymon_end(bm_kind kind, uint32_t start, const char *name)
{
  uint32_t cycles = DWT->CYCCNT - start;
  if (!WS_CHECK(kind < BM_KINDS)) return;   /* every caller passes a BM_* constant */
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  note_peak(kind, cycles, name);
  __set_PRIMASK(primask);
}

uint32_t busymon_isr_enter(void)
{
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  isr_depth++;
  __set_PRIMASK(primask);
  return DWT->CYCCNT;
}

void busymon_isr_exit(uint32_t t0, const char *name)
{
  uint32_t cycles = DWT->CYCCNT - t0;
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  note_peak(BM_ISR, cycles, name);
  if (WS_CHECK(isr_depth > 0U)) isr_depth--;   /* every exit has its enter */
  if (isr_depth == 0U) isr_total += cycles;    /* the outermost handler's time covers the nested ones */
  __set_PRIMASK(primask);
}

bm_span busymon_begin(void) { bm_span s = { DWT->CYCCNT, isr_total }; return s; }

/* Cycles of s without the interrupts that ran meanwhile. */
static uint32_t own_cycles(bm_span s, uint32_t *wall)
{
  *wall = DWT->CYCCNT - s.t0;
  uint32_t isr = isr_total - s.isr0;
  return isr < *wall ? *wall - isr : 0U;
}

void busymon_step_end(bm_span s, const char *step)
{
  uint32_t wall, own = own_cycles(s, &wall);
  if (own > run_step_cycles) { run_step_cycles = own; run_step = step; }
}

void busymon_task_end(bm_span s, const char *task)
{
  uint32_t wall, own = own_cycles(s, &wall);
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  note_peak(BM_TASK, own, run_step ? run_step : task);
  note_peak(BM_TASK_WALL, wall, task);
  __set_PRIMASK(primask);
  run_step = 0; run_step_cycles = 0;
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
