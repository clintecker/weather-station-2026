#define WS_CHECK_FILE 0   /* this file has no checks of its own; 0 is no site */
#include "ws_check.h"

static uint32_t fails;
static uint16_t first;

void ws_check_fail(uint16_t site)
{
 if (!fails) first = site;
 if (fails < UINT32_MAX) fails++;
}
uint32_t ws_check_count(void) { return fails; }
uint16_t ws_check_first(void) { return first; }
