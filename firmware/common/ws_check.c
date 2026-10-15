#define WS_CHECK_FILE 0   /* this file has no checks of its own; 0 is no site */
#include "ws_check.h"

#include <stdatomic.h>

/* Counted from tasks and interrupts (busymon_end): one atomic add (LDREX/STREX on the M4), and only
   the failure that took the count from 0 records its site. */
static _Atomic uint32_t fails;
static uint16_t first;

void ws_check_fail(uint16_t site)
{
 if (atomic_fetch_add(&fails, 1U) == 0U) first = site;
}
uint32_t ws_check_count(void) { return atomic_load(&fails); }
uint16_t ws_check_first(void) { return first; }
