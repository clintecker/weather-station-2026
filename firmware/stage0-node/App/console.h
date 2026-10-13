#ifndef CONSOLE_H
#define CONSOLE_H
#include <stdint.h>
#include "ws_console.h"
/* USB virtual COM (USART2, 115200 8N1). Input: newline-terminated lines of at most
 * WS_LINE_MAX bytes, assembled by ws_line_feed (firmware/common/ws_console.c); longer lines are
 * discarded whole. Output: APP_PRINTF. Hex input: ws_hex_decode. */
void console_init(void (*on_line)(char *line));
void hex_print(const uint8_t *data, int len); /* one line, lowercase, newline-terminated */
#endif
