#ifndef CONSOLE_H
#define CONSOLE_H
#include <stdint.h>
/* USB virtual COM (USART2, 115200 8N1). Input: newline-terminated lines of at most
 * CONSOLE_MAX_LINE bytes; longer lines are discarded whole. Output: APP_PRINTF. */
#define CONSOLE_MAX_LINE 256
void console_init(void (*on_line)(char *line));
/* Hex helpers. decode returns byte count, or -1 on odd length/bad digit/overflow. */
int hex_decode(const char *text, uint8_t *out, int max);
void hex_print(const uint8_t *data, int len); /* one line, lowercase, newline-terminated */
#endif
