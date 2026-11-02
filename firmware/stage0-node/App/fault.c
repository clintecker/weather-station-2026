#include "fault.h"
#include "stm32wlxx.h"
#include "sys_app.h"

/* RTC backup registers (TAMP->BKPxR), kept while the board has power:
 *   DR0-DR2   SysTime (Core/Src/timer_if.c)
 *   DR3-DR4   the TX time trust (App/tx_time.c)
 *   DR5-DR11  the crash record below (DR6 the PC, DR11 the crash count)
 *   DR12      the boot counter, shared by the node roles and benchlink (bl_guard.c links this file);
 *             fault_boot_note() is its only writer
 * Written directly, not through the HAL: fault_record runs in a fault. */
enum { BKP_MAGIC = 5, BKP_PC, BKP_LR, BKP_CFSR, BKP_HFSR, BKP_BFAR, BKP_COUNT, BKP_BOOTS };
_Static_assert(BKP_BOOTS == 12, "the boot counter is DR12 (power telemetry design, section 6.2)");
#define FAULT_MAGIC_HARD 0x57534601UL   /* "WSF" + kind */
#define FAULT_MAGIC_NMI  0x57534602UL
#define BKP(n) ((&TAMP->BKP0R)[n])
/* The exception frame the core stacks: r0-r3, r12, lr, pc, xPSR (ARMv7-M Architecture
 * Reference Manual, B1.5.6). */
enum { FRAME_LR = 5, FRAME_PC = 6, FRAME_WORDS = 8 };
#define BOOTS_MAX 0xFFFFUL   /* the health report's u16 field saturates here */
#define PRINT_DRAIN_MS 50U   /* lets the console send the line before the fault */

/* An address with nothing behind it: RAM (SRAM1 and SRAM2, 64 KB) ends at 0x20010000. A read there is a precise bus
 * error, which escalates to HardFault because the separate BusFault handler is not enabled. */
#define UNMAPPED_ADDRESS 0x20040000UL

void fault_record(const uint32_t *frame, uint32_t exc_return, uint32_t kind)
{
  /* Only trust the stacked frame if it lies in RAM; a fault while
   * stacking (a stack overflow) leaves the stack pointer anywhere. */
  uint32_t sp = (uint32_t)frame;
  int ok = sp >= SRAM1_BASE && sp + FRAME_WORDS * sizeof(uint32_t) <= SRAM2_BASE + SRAM2_SIZE && sp % sizeof(uint32_t) == 0;
  BKP(BKP_PC) = ok ? frame[FRAME_PC] : UINT32_MAX;
  BKP(BKP_LR) = ok ? frame[FRAME_LR] : exc_return;
  BKP(BKP_CFSR) = SCB->CFSR;
  BKP(BKP_HFSR) = SCB->HFSR;
  BKP(BKP_BFAR) = SCB->BFAR;
  BKP(BKP_COUNT) = BKP(BKP_COUNT) + 1u;
  BKP(BKP_MAGIC) = kind == FAULT_KIND_NMI ? FAULT_MAGIC_NMI : FAULT_MAGIC_HARD;
  NVIC_SystemReset();
}

void fault_report(void)
{
  uint32_t magic = BKP(BKP_MAGIC);
  if (magic != FAULT_MAGIC_HARD && magic != FAULT_MAGIC_NMI) return;
  /* CFSR bit 15 (BFARVALID) says whether bfar holds the faulting address. */
  APP_PRINTF("#fault kind=%s pc=%08x lr=%08x cfsr=%08x hfsr=%08x bfar=%08x count=%u\n",
             magic == FAULT_MAGIC_NMI ? "nmi" : "hard", (unsigned)BKP(BKP_PC), (unsigned)BKP(BKP_LR),
             (unsigned)BKP(BKP_CFSR), (unsigned)BKP(BKP_HFSR), (unsigned)BKP(BKP_BFAR), (unsigned)BKP(BKP_COUNT));
  BKP(BKP_MAGIC) = 0;
}

uint32_t fault_count(void) { return BKP(BKP_COUNT); }

/* fault_report clears only the magic, so DR6 keeps the latest crash's PC until the next crash or a
   power loss. UINT32_MAX (the frame was not in RAM) passes through: it means "untrusted frame". */
uint32_t fault_last_pc(void) { return fault_count() ? BKP(BKP_PC) : 0U; }

void fault_boot_note(int power_on)
{
  if (power_on) BKP(BKP_BOOTS) = 0;
  if (BKP(BKP_BOOTS) < BOOTS_MAX) BKP(BKP_BOOTS) = BKP(BKP_BOOTS) + 1U;
}

uint32_t fault_boots(void) { return BKP(BKP_BOOTS); }

void fault_test(void)
{
  APP_PRINTF("#test-fault: reading %08x; expect a reset and #fault with bfar=%08x\n",
             (unsigned)UNMAPPED_ADDRESS, (unsigned)UNMAPPED_ADDRESS);
  HAL_Delay(PRINT_DRAIN_MS);
  (void)*(volatile uint32_t *)UNMAPPED_ADDRESS;
  for (;;) { }   /* bound: none; never reached: the read above faults (TEST-FAULT only) */
}
