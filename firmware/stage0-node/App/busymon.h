#ifndef BUSYMON_H
#define BUSYMON_H
#include <stdint.h>
#include "stm32wlxx.h"
/* Run-time timing monitor (both roles). Nothing in this firmware waits: every step is an interrupt,
 * a timer or a main-loop task that runs to completion. This measures how long each of them really
 * keeps the CPU, with the Cortex-M4 cycle counter (DWT CYCCNT, 48 MHz, wraps after 89 s):
 *  - BM_TASK: one sequencer task's OWN time, interrupts that ran meanwhile taken out, named after
 *    its slowest timed step when it has steps ("process.alive"), else after the task;
 *  - BM_TASK_WALL: the same task start to end, interrupts included (what the main loop waited);
 *  - BM_ISR: one interrupt handler, including any it was preempted by;
 *  - BM_ERASE / BM_PROG: one flash page erase / double-word program. The CPU stalls while the
 *    single-bank flash is busy (RM0453 section 3.3); these are inside a task's time as well.
 * Interrupt time is summed once per outermost handler (a nested one is inside its preempted
 * one's time), so own time = wall time - interrupt time during the task.
 * Peaks since boot, with the name of the slowest, are printed on #timing (TX) and #alive / STATUS (RX). */
typedef enum { BM_TASK, BM_ISR, BM_ERASE, BM_PROG, BM_TASK_WALL, BM_KINDS } bm_kind;
typedef struct { uint32_t t0, isr0; } bm_span;   /* a task or step under way */
void busymon_init(void);
static inline uint32_t busymon_now(void) { return DWT->CYCCNT; }
void busymon_end(bm_kind kind, uint32_t start, const char *name);   /* flash ops */
bm_span busymon_begin(void);
void busymon_step_end(bm_span s, const char *step);   /* a timed step inside the running task */
void busymon_task_end(bm_span s, const char *task);
uint32_t busymon_isr_enter(void);
void busymon_isr_exit(uint32_t t0, const char *name);
uint32_t busymon_peak_us(bm_kind kind);
const char *busymon_peak_name(bm_kind kind);
/* A timed wrapper for a sequencer task: register fn_timed instead of fn. */
#define BUSYMON_TASK(fn) static void fn##_timed(void) { bm_span s_ = busymon_begin(); fn(); busymon_task_end(s_, #fn); }
/* Interrupt handler body, timed. */
#define BUSYMON_ISR(name, body) do { uint32_t t0_ = busymon_isr_enter(); body; busymon_isr_exit(t0_, name); } while (0)
#endif
