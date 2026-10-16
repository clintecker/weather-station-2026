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
/* The line being assembled lost a character: discard it whole (up to its '\n'). A line with a byte
   outside printable ASCII (NUL, control characters, 8-bit) is discarded the same way by ws_line_feed. */
void ws_line_discard(ws_line_asm *a);
/* Console command lookup: the index of the first name the line equals, or starts with if the name
 * ends in a space (a command with arguments, "PROVISION "); -1 if none matches. */
int ws_cmd_find(const char *const names[], unsigned n, const char *line);
/* One hex digit's value (either case), or -1. Inline: firmware/stage0.c uses it too. */
static inline int ws_hex_nibble(char c)
{
 if (c >= '0' && c <= '9') return c - '0';
 if (c >= 'a' && c <= 'f') return c - 'a' + 10;
 if (c >= 'A' && c <= 'F') return c - 'A' + 10;
 return -1;
}
#define WS_HEX_DIGIT_BITS 4
#define WS_HEX_DIGIT_MASK 0x0FU
#define WS_HEX_PER_BYTE 2     /* hex digits per byte */
/* The byte two hex digits spell, or -1. The second digit is read only when the first is a digit, so
   a NUL ends the parse before the byte after it is read. */
static inline int ws_hex_byte(const char *p)
{
 int hi = ws_hex_nibble(p[0]), lo = hi < 0 ? -1 : ws_hex_nibble(p[1]);
 return lo < 0 ? -1 : hi << WS_HEX_DIGIT_BITS | lo;
}
/* Hex text to bytes: byte count, or -1 on odd length, a non-hex digit, or more than max bytes. */
int ws_hex_decode(const char *text, uint8_t *out, int max);
/* Bytes to lowercase hex: writes 2n digits and a NUL to text (room for 2n + 1); n < 0 counts as 0. */
void ws_hex_text(const uint8_t *data, int n, char *text);
/* RX downstream: a host line that may go on air. The caller hex-decodes it into frame (room for
 * WS_ACK_FRAME_LEN + 1 bytes) and passes the decoded length (-1 if not hex). Acceptable only as a
 * WS_ACK_FRAME_LEN-byte ACK or NACK of this protocol version. The bridge holds no key. */
int ws_host_reply_ok(const uint8_t *frame, int n);
/* RX upstream: a received radio frame worth forwarding to the host: an observation whose length is
 * in the range the field catalog allows, or a health report of its fixed length, of this version. */
int ws_air_frame_ok(const uint8_t *frame, uint32_t len);
#endif
