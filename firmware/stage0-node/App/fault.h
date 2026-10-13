#ifndef FAULT_H
#define FAULT_H
#include <stdint.h>
/* Crash record (both roles). A HardFault, or an NMI that is not a flash ECC error, saves the
 * faulting PC, LR and the fault status registers in RTC backup registers DR5-DR11, which survive a
 * reset while the board keeps power, then resets at once. The next boot prints `#fault ...` and
 * clears the record; the fault count stays until power is lost. */
void fault_report(void);
/* Bench: TEST-FAULT reads an address with no memory behind it, which must end in a recorded
 * HardFault and a reset. */
void fault_test(void) __attribute__((noreturn));
/* Called from the exception handlers (Core/Src/stm32wlxx_it.c) with the stacked exception frame
 * and the EXC_RETURN value; kind 1 = HardFault, 2 = NMI. */
void fault_record(const uint32_t *frame, uint32_t exc_return, uint32_t kind) __attribute__((noreturn));
#endif
