#include "bench.h"
#include <string.h>
#include "fault.h"
#include "sys_app.h"

#ifndef WS_FIELD_BUILD
static void test_hang(void) __attribute__((noreturn));
static void test_hang(void)
{
  APP_PRINTF("#test-hang: main loop stops; watchdog must reset in ~8 s\n");
  for (;;) { }
}
#endif

void bench_command(const char *line)
{
#ifndef WS_FIELD_BUILD
  if (!strcmp(line, "TEST-FAULT")) fault_test();
  if (!strcmp(line, "TEST-HANG")) test_hang();
#else
  (void)line;
#endif
}
