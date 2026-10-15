#ifndef CONSOLE_H
#define CONSOLE_H
#include <stdint.h>
#include "ws_console.h"
/* USB virtual COM (USART2, 115200 8N1). Input: newline-terminated lines of at most
 * WS_LINE_MAX bytes, assembled by ws_line_feed (firmware/common/ws_console.c); longer lines are
 * discarded whole. Output: APP_PRINTF. Hex input: ws_hex_decode. */
void console_init(void);
/* Each complete input line, from the console task (main loop). Defined by the role (App/tx_console.c,
   App/app_rx.c): a link-time call, not a registered function pointer (docs/power-of-ten.md rule 9). */
void console_line(char *line);
int hex_print(const uint8_t *data, int len); /* one line, lowercase, newline-terminated; 0 if it was not queued */
#endif
