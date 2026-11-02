#ifndef WATCHDOG_H
#define WATCHDOG_H
/* Independent watchdog (IWDG, LSI clock, ~8 s). A 1 s timer only *requests* a check; the
 * check and the refresh run in the main loop, so a hung main loop is never fed. The role
 * supplies a health test that proves real progress. */
void watchdog_start(void);
/* The role's health test (App/app_tx.c, App/app_rx.c), called by the 1 s check: 1 lets the check
   refresh the IWDG. A link-time call, not a registered function pointer (docs/power-of-ten.md rule 9). */
int watchdog_healthy(void);
/* Reset cause of this boot, read once before the flags are cleared. The codes are the wire
 * numbering of the health report, DIAG (docs/protocol.md, ws0/protocol.py RESET_CAUSES;
 * tests/test_frame.py checks the names).
 * Known limitation (power telemetry design, section 9.8 and risk R7): BROWNOUT is never reported.
 * The brownout-reset (BOR) flag is also set at power-on, and watchdog.c reads it as POWER, so a
 * brown-out (the supply sagging below the BOR threshold, as a flat pack can) reads as a power-on
 * reset. It also restarts the boot counter (fault_boot_note(1), fault.h) even if the backup
 * registers survived the sag, while the crash count and last crash PC (DR5-DR11) are kept then.
 * Telling the two apart needs brown-out detection the firmware does not have (design section 16). */
typedef enum {
  WS_RESET_UNKNOWN, WS_RESET_POWER, WS_RESET_PIN, WS_RESET_BROWNOUT, WS_RESET_SOFTWARE, WS_RESET_WATCHDOG,
  WS_RESET_LOWPOWER, WS_RESET_OPTION_BYTES, WS_RESET_COUNT
} ws_reset_t;
ws_reset_t watchdog_reset_code(void);
const char *watchdog_reset_cause(void); /* its name: "unknown", "power", "pin", ... */
#endif
