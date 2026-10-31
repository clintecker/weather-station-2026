#ifndef FAULT_H
#define FAULT_H
#include <stdint.h>
/* Crash record (both roles). A HardFault, or an NMI that is not a flash ECC error, saves the
 * faulting PC, LR and the fault status registers in RTC backup registers DR5-DR11, which survive a
 * reset while the board keeps power, then resets at once. The next boot prints `#fault ...` and
 * clears the record; the fault count stays until power is lost. */
void fault_report(void);
/* Crashes recorded since the board last lost power (the backup domain is cleared then). */
uint32_t fault_count(void);
/* The PC of the latest crash since power-up: 0 when fault_count() is 0, else the stacked PC kept
 * in DR6 (fault_report does not clear it). 0xFFFFFFFF means the stacked frame was not in RAM, so
 * no PC could be trusted. */
uint32_t fault_last_pc(void);
/* The boot counter in backup register DR12, whose only writer this is. Called exactly once a boot
 * (app_tx, app_rx, benchlink's bl_guard), before fault_report: power_on (the reset cause is
 * power-on; a brown-out reads as one too, watchdog.h) zeroes it first, then it adds one,
 * saturating at 0xFFFF. */
void fault_boot_note(int power_on);
/* Boots since the board last powered up, counting this one: DR12, at most 0xFFFF. */
uint32_t fault_boots(void);
/* Bench: TEST-FAULT reads an address with no memory behind it, which must end in a recorded
 * HardFault and a reset. */
void fault_test(void) __attribute__((noreturn));
/* Called from the exception handlers (Core/Src/stm32wlxx_it.c) with the stacked exception frame
 * and the EXC_RETURN value. The HardFault handler's assembly passes FAULT_KIND_HARD as an immediate. */
#define FAULT_KIND_HARD 1U
#define FAULT_KIND_NMI  2U
void fault_record(const uint32_t *frame, uint32_t exc_return, uint32_t kind) __attribute__((noreturn));
#endif
