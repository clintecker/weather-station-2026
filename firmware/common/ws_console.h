#ifndef WS_CONSOLE_H
#define WS_CONSOLE_H
#include <stdint.h>
/* Console input parsing with no hardware dependencies, so the boards and the host fuzzers
 * (firmware/fuzz/) run the same code. App/console.c feeds it from the UART interrupt. */
#define WS_LINE_MAX 256  /* longest accepted line; longer lines are discarded whole */
typedef struct { char buf[WS_LINE_MAX]; uint16_t len; uint8_t overflow; } ws_line_asm;
/* Feed one received byte. '\r' is ignored. On '\n' a non-empty line that did not overflow is
 * copied to out with a terminating NUL, the internal buffer is cleared (a PROVISION key must not
 * linger), and its length is returned; otherwise 0. */
int ws_line_feed(ws_line_asm *a, uint8_t c, char out[WS_LINE_MAX + 1]);
/* Hex text to bytes: byte count, or -1 on odd length, a non-hex digit, or more than max bytes. */
int ws_hex_decode(const char *text, uint8_t *out, int max);
/* RX: a host line that may go on air. Decodes into frame (WS_ACK_FRAME_LEN + 1 bytes) and returns
 * the decoded length (-1 if not hex). The line is acceptable only if that equals WS_ACK_FRAME_LEN
 * and ws_host_reply_ok() says the header is an ACK or NACK of this protocol version. */
int ws_host_reply_ok(const uint8_t *frame, int n);
#endif
