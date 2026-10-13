#include "ws_console.h"
#include <string.h>
#include "ws_frame.h"

int ws_line_feed(ws_line_asm *a, uint8_t c, char out[WS_LINE_MAX + 1])
{
 int n = 0;
 if (c == '\r') return 0;
 if (c == '\n') {
  if (!a->overflow && a->len) {
   memcpy(out, a->buf, a->len);
   out[a->len] = 0;
   memset(a->buf, 0, a->len);
   n = a->len;
  }
  a->len = 0;
  a->overflow = 0;
  return n;
 }
 if (a->len >= WS_LINE_MAX) { a->overflow = 1; return 0; }
 a->buf[a->len++] = (char)c;
 return 0;
}

static int nibble(char c)
{
 if (c >= '0' && c <= '9') return c - '0';
 if (c >= 'a' && c <= 'f') return c - 'a' + 10;
 if (c >= 'A' && c <= 'F') return c - 'A' + 10;
 return -1;
}

int ws_hex_decode(const char *text, uint8_t *out, int max)
{
 int n = 0;
 while (text[0] && text[1]) {
  int hi = nibble(text[0]), lo = nibble(text[1]);
  if (hi < 0 || lo < 0 || n >= max) return -1;
  out[n++] = (uint8_t)(hi << 4 | lo);
  text += 2;
 }
 return text[0] ? -1 : n;
}

int ws_host_reply_ok(const uint8_t *frame, int n)
{
 return n == WS_ACK_FRAME_LEN && frame[0] == 'W' && frame[1] == 'S' && frame[2] == WS_FRAME_VERSION &&
        (frame[3] == WS_KIND_ACK || frame[3] == WS_KIND_NACK);
}
