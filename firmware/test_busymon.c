/* Host test of App/busymon.c's accounting (tests/test_busymon.py): a task's own time leaves out the
   interrupts that ran meanwhile, a nested interrupt is counted once, and the task's peak is named
   after its slowest step. The cycle counter is set by hand (firmware/host/include/stm32wlxx.h). */
#include <assert.h>
#include <string.h>
#include "busymon.h"
DWT_Type host_dwt;
CoreDebug_Type host_coredebug;
uint32_t SystemCoreClock = 48000000U;
uint32_t host_primask;
void NVIC_SystemReset(void) {}
static void at(uint32_t us) { host_dwt.CYCCNT = us * 48U; }

int main(void)
{
  busymon_init();
  /* A 1000 us task with an 800 us interrupt inside (which itself was preempted by a 300 us one). */
  at(0); bm_span task = busymon_begin();
  at(100); bm_span alive = busymon_begin();
  at(150); uint32_t outer = busymon_isr_enter();
  at(300); uint32_t inner = busymon_isr_enter();
  at(600); busymon_isr_exit(inner, "inner");
  at(950); busymon_isr_exit(outer, "outer");
  at(400 + 800); busymon_step_end(alive, "process.alive");   /* 1100 us wall, 300 us own */
  at(1100 + 800); bm_span fwd = busymon_begin();
  at(1300 + 800); busymon_step_end(fwd, "process.forward");  /* 200 us own */
  at(1500 + 800); busymon_task_end(task, "process");         /* 2300 wall, 1500 own */
  assert(busymon_peak_us(BM_TASK_WALL) == 2300 && !strcmp(busymon_peak_name(BM_TASK_WALL), "process"));
  assert(busymon_peak_us(BM_TASK) == 1500 && !strcmp(busymon_peak_name(BM_TASK), "process.alive"));
  assert(busymon_peak_us(BM_ISR) == 800 && !strcmp(busymon_peak_name(BM_ISR), "outer"));   /* 150..950 */
  /* A task without steps is named after itself; a shorter one does not replace the peak. */
  at(10000); bm_span t2 = busymon_begin();
  at(10100); busymon_task_end(t2, "console_task");
  assert(!strcmp(busymon_peak_name(BM_TASK), "process.alive"));
  at(20000); bm_span t3 = busymon_begin();
  at(22000); busymon_task_end(t3, "console_task");
  assert(busymon_peak_us(BM_TASK) == 2000 && !strcmp(busymon_peak_name(BM_TASK), "console_task"));
  return 0;
}
