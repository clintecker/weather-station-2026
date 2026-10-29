/* Bench link supervision (both roles), after firmware/stage0-node/App/watchdog.c: the independent
 * watchdog (IWDG, ~8 s), the reset cause, a boot count and the crash record (stage0-node/App/fault.c).
 * A 1 s timer only *requests* a check; the check runs in the main loop, asks the role whether it made
 * real progress (bl_role_check) and only then refreshes the IWDG. A hung loop, a stopped timer or a
 * role that reports no progress ends in a reset within about 8 s. */
#ifndef BL_GUARD_H
#define BL_GUARD_H

#include <stdint.h>

/* The reset codes, numbered as stage0-node's ws_reset_t (watchdog.h). */
enum { BL_RESET_UNKNOWN, BL_RESET_POWER, BL_RESET_PIN, BL_RESET_BROWNOUT, BL_RESET_SOFTWARE, BL_RESET_WATCHDOG,
       BL_RESET_LOWPOWER, BL_RESET_OPTION_BYTES, BL_RESET_COUNT };

/* Reads and clears the reset flags, counts the boot, prints "#bl boot ..." and any crash record, then
   starts the IWDG and the 1 s check. Call once, before the role starts. */
void bl_guard_start(const char *role);
/* The role's 1 s check (App/benchlink.c): its housekeeping, then 1 when it made progress. */
int bl_role_check(void);

uint8_t bl_guard_reset_code(void);
const char *bl_guard_reset_name(void);
uint16_t bl_guard_boots(void);     /* since the board last lost power */
uint8_t bl_guard_faults(void);     /* crashes since the board last lost power, saturating */
uint32_t bl_guard_fault_pc(void);  /* program counter of the latest crash since power-on, 0 for none */

#endif
