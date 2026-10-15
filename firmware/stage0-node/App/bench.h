#ifndef BENCH_H
#define BENCH_H
/* Bench commands (both roles), left out of a field build (-DWS_FIELD_BUILD; review m12):
 *   TEST-FAULT  ends in a recorded HardFault and a reset (fault.h);
 *   TEST-HANG   stops the main loop on purpose, so the watchdog must reset the board.
 * Neither returns; any other line returns at once. Deliberate waits and hangs, classified as
 * TEST_ONLY in tools/blocking_report.py. */
void bench_command(const char *line);
#endif
