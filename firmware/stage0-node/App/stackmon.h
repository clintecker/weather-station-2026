#ifndef STACKMON_H
#define STACKMON_H
#include <stdint.h>
/* Run-time stack high-water mark (both roles). stackmon_paint() at boot fills the unused stack with
 * a pattern; stackmon_peak() returns the deepest use since then, in bytes from the stack top.
 * The bound it should stay under comes from tools/stack_report.py (docs/firmware-budget.md). */
void stackmon_paint(void);
uint32_t stackmon_peak(void);
/* The same for a periodic report (RX #alive): a slice of the scan per call, at most one pass
   (~17 calls on the RX) behind; stackmon_peak() reads the whole range at once (~1.5 ms). */
uint32_t stackmon_peak_step(void);
#endif
