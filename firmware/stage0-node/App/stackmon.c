#include "stackmon.h"
#include <stdint.h>
#include "stm32wlxx.h"
#include "stage0.h"

/* Linker symbols (STM32WL55JCIX_FLASH.ld): end of .bss, reserved heap size, top of the stack. */
extern uint32_t _end[];
extern char _Min_Heap_Size[];
extern uint32_t _estack[];

#define WORD_ALIGN (sizeof(uint32_t) - 1U)   /* round a byte address to a word */
#define OWN_FRAME_BYTES 64U
static uint32_t *lowest(void)
{
  uintptr_t lo = (uintptr_t)_end + (uintptr_t)_Min_Heap_Size;
  return (uint32_t *)((lo + WORD_ALIGN) & ~(uintptr_t)WORD_ALIGN);
}

void stackmon_paint(void)
{
  /* Leave OWN_FRAME_BYTES below the current stack pointer untouched: this function's own frame. */
  const uint32_t *stop = (const uint32_t *)((__get_MSP() - OWN_FRAME_BYTES) & ~(uint32_t)WORD_ALIGN);
  for (uint32_t *p = lowest(); p < stop; p++) *p = WS_STACK_PAINT;
}

uint32_t stackmon_peak(void) { return ws_stack_peak(lowest(), _estack); }

/* 256 words (1 KB, ~0.1 ms) per call: the RX's 17 KB painted range is one pass every ~17 calls. */
#define SCAN_SLICE_WORDS 256U
static ws_stack_scan scan;
uint32_t stackmon_peak_step(void) { return ws_stack_scan_step(&scan, lowest(), _estack, SCAN_SLICE_WORDS); }

/* One whole scan at boot (not a timed task), so the first reports show the peak so far, not 0
   while the slices climb to it. */
void stackmon_seed(void)
{
  scan.deepest = _estack - stackmon_peak() / sizeof(uint32_t);   /* the peak is whole words */
  scan.cursor = lowest();
}
