#include "ws_console.h"
#include <string.h>
#include "ws_frame.h"
#include "ws_obs.h"

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
 if (a->len >= WS_LINE_MAX) {
  /* An over-long line is discarded whole: clear it now, so a long PROVISION line's key does not
     linger in RAM until the next line arrives. */
  if (!a->overflow) memset(a->buf, 0, sizeof a->buf);
  a->overflow = 1;
  return 0;
 }
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

void ws_hex_text(const uint8_t *data, int n, char *text)
{
 static const char digits[] = "0123456789abcdef";
 for (int i = 0; i < n; i++) { text[2 * i] = digits[data[i] >> 4]; text[2 * i + 1] = digits[data[i] & 15]; }
 text[n > 0 ? 2 * n : 0] = 0;
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
 if (n != WS_ACK_FRAME_LEN) return 0;
 int kind = ws_frame_kind(frame, (uint32_t)n);
 return kind == WS_KIND_ACK || kind == WS_KIND_NACK;
}

int ws_air_frame_ok(const uint8_t *frame, uint32_t len)
{
 int kind = ws_frame_kind(frame, len);
 /* The smallest observation carries one 1-byte field; the largest, every catalog field. */
 if (kind == WS_KIND_OBS) return len >= WS_FRAME_OVERHEAD + WS_OBS_HEAD_LEN + 1U && len <= WS_FRAME_OVERHEAD + WS_OBS_PLAIN_ALL;
 return kind == WS_KIND_DIAG && len == WS_DIAG_FRAME_LEN;
}
