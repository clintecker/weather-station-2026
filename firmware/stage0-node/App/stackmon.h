#ifndef STACKMON_H
#define STACKMON_H
#include <stdint.h>
/* Run-time stack high-water mark (both roles). stackmon_paint() at boot fills the unused stack with
 * a pattern; stackmon_peak() returns the deepest use since then, in bytes from the stack top.
 * The bound it should stay under comes from tools/stack_report.py (docs/firmware-budget.md). */
void stackmon_paint(void);
uint32_t stackmon_peak(void);
#endif
