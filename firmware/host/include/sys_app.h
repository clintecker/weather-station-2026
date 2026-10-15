#ifndef HOST_SYS_APP_H
#define HOST_SYS_APP_H
#include <stdint.h>
extern volatile uint32_t ws_trace_drops;
void host_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define APP_PRINTF(...) host_printf(__VA_ARGS__)
int host_print_ok(const char *fmt, ...) __attribute__((format(printf, 1, 2)));   /* rx_harness.c */
#define APP_PRINTF_OK(...) host_print_ok(__VA_ARGS__)
#endif
