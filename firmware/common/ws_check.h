#ifndef WS_CHECK_H
#define WS_CHECK_H
#include <stdint.h>
/* Run-time checks with a defined recovery (Power of Ten rule 5, docs/power-of-ten.md).
 *
 * WS_CHECK(cond) is an expression: 1 if cond holds, else 0 after counting the failure. The caller
 * recovers on the spot, with an action written next to the check: return an error, skip the step,
 * or fall back to a safe value. Nothing halts or resets here; a check never replaces the error
 * handling of untrusted input (frames, console lines, flash read back), whose failures are normal
 * events with their own counters. A check states an invariant of our own code: a state-machine
 * precondition, an index or length bound before a buffer is used, a value one of our modules
 * produced, a result ST's code documents as impossible for our arguments. A failed check is a bug.
 * Unlike assert(), WS_CHECK is never compiled out, so its condition may be the call whose result it
 * checks (WS_CHECK(UTIL_TIMER_Start(&t) == UTIL_TIMER_OK)): the result checks of
 * Power of Ten rule 7 (docs/power-of-ten.md) are written so.
 *
 * Cost: no strings. A failure records only how many checks failed since boot and the site of the
 * first one, a 16-bit (file id << 10 | line). TX prints them on #counts, RX on its STATUS reply:
 * check_fails=N check_first=F:L (0:0 while none failed). F is the WS_CHECK_FILE number below.
 *
 * A file that uses WS_CHECK defines its number first: #define WS_CHECK_FILE <n>, then includes this
 * header. tests/test_check.py keeps this table, the numbers and every such file under 1024 lines.
 *    1 App/app_tx.c        2 App/tx_exchange.c   3 App/tx_policy.c     4 App/tx_console.c
 *    5 App/node_store.c    6 App/sensor.c        7 App/app_rx.c        8 App/console.c
 *    9 App/watchdog.c     10 App/busymon.c      11 common/ws_policy.c  12 App/i2c_bus.c
 *   13 App/mod_th.c      14 App/wsmp_local.c   15 App/mod_reg.c */
#ifndef WS_CHECK_FILE
#error "define WS_CHECK_FILE (the file's number, listed above) before including ws_check.h"
#endif

/* Counts one failed check at site (WS_CHECK does this). Callable from interrupts and tasks alike;
   an interrupt that fails a check while preempting a task's failed check can lose one count, never
   both: the count stays nonzero once anything failed. */
void ws_check_fail(uint16_t site) __attribute__((cold));
uint32_t ws_check_count(void);   /* failed checks since boot (saturates) */
uint16_t ws_check_first(void);   /* site of the first failed check, 0 if none */
/* A site is (file << WS_CHECK_LINE_BITS) | line: files 1-63, lines 1-1023. */
#define WS_CHECK_LINE_BITS 10
#define WS_CHECK_LINE_MASK ((1U << WS_CHECK_LINE_BITS) - 1U)
static inline unsigned ws_check_site_file(uint16_t site) { return (unsigned)site >> WS_CHECK_LINE_BITS; }
static inline unsigned ws_check_site_line(uint16_t site) { return (unsigned)site & WS_CHECK_LINE_MASK; }

#define WS_CHECK(cond) \
  (__builtin_expect(!!(cond), 1) ? 1 : (ws_check_fail((uint16_t)((WS_CHECK_FILE << WS_CHECK_LINE_BITS) | __LINE__)), 0))
#endif
