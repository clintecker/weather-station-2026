#include "stackmon.h"
#include <stdint.h>
#include "stm32wlxx.h"
#include "stage0.h"

/* Linker symbols (STM32WL55JCIX_FLASH.ld): end of .bss, reserved heap size, top of the stack. */
extern uint32_t _end[];
extern char _Min_Heap_Size[];
extern uint32_t _estack[];

static uint32_t *lowest(void)
{
  uintptr_t lo = (uintptr_t)_end + (uintptr_t)_Min_Heap_Size;
  return (uint32_t *)((lo + 3u) & ~(uintptr_t)3u);
}

void stackmon_paint(void)
{
  /* Leave 64 bytes below the current stack pointer untouched: this function's own frame. */
  uint32_t *stop = (uint32_t *)((__get_MSP() - 64u) & ~(uint32_t)3u);
  for (uint32_t *p = lowest(); p < stop; p++) *p = WS_STACK_PAINT;
}

uint32_t stackmon_peak(void) { return ws_stack_peak(lowest(), _estack); }
