#ifndef WATCHDOG_H
#define WATCHDOG_H
/* Independent watchdog (IWDG, LSI clock, ~8 s). A 1 s timer only *requests* a check; the
 * check and the refresh run in the main loop, so a hung main loop is never fed. The role
 * supplies a health test that proves real progress (failure-modes.md gap G1). */
void watchdog_start(int (*healthy)(void));
/* Reset cause of this boot, read once before the flags are cleared: "power", "pin",
 * "brownout", "software", "watchdog", "lowpower", "option-bytes" or "unknown". */
const char *watchdog_reset_cause(void);
#endif
