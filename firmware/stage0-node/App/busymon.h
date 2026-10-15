#ifndef BUSYMON_H
#define BUSYMON_H
#include <stdint.h>
#include "stm32wlxx.h"
/* Run-time timing monitor (both roles). Nothing in this firmware waits: every step is an interrupt,
 * a timer or a main-loop task that runs to completion. This measures how long each of them really
 * keeps the CPU, with the Cortex-M4 cycle counter (DWT CYCCNT, 48 MHz, wraps after 89 s):
 *  - BM_TASK: one sequencer task (the main loop cannot run anything else meanwhile);
 *  - BM_ISR: one interrupt handler, including any it was preempted by;
 *  - BM_ERASE / BM_PROG: one flash page erase / double-word program. The CPU stalls while the
 *    single-bank flash is busy (RM0453 section 3.3); these are inside a task's time as well.
 * Peaks since boot, with the name of the slowest, are printed on #timing (TX) and #alive (RX). */
typedef enum { BM_TASK, BM_ISR, BM_ERASE, BM_PROG, BM_KINDS } bm_kind;
void busymon_init(void);
static inline uint32_t busymon_now(void) { return DWT->CYCCNT; }
void busymon_end(bm_kind kind, uint32_t start, const char *name);
uint32_t busymon_peak_us(bm_kind kind);
const char *busymon_peak_name(bm_kind kind);
/* A timed wrapper for a sequencer task: register fn_timed instead of fn. */
#define BUSYMON_TASK(fn) static void fn##_timed(void) { uint32_t t0_ = busymon_now(); fn(); busymon_end(BM_TASK, t0_, #fn); }
/* Interrupt handler body, timed. */
#define BUSYMON_ISR(name, body) do { uint32_t t0_ = busymon_now(); body; busymon_end(BM_ISR, t0_, name); } while (0)
#endif
