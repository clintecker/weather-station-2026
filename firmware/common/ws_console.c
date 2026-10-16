#include "ws_console.h"
#include <string.h>
#include "ws_frame.h"
#include "ws_obs.h"

int ws_line_feed(ws_line_asm *a, uint8_t c, char out[WS_LINE_MAX + 1])
{
 if (c == '\r') return 0;
 if (c == '\n') {
  int n = 0;
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
 /* An over-long line, or one with a byte outside printable ASCII (a NUL would end the C string
    early: "ACKHEX\0junk" must not decode as an ACK), is discarded whole. */
 if (a->overflow) return 0;
 if (a->len >= WS_LINE_MAX || c < ' ' || c > '~') { ws_line_discard(a); return 0; }   /* printable ASCII only */
 a->buf[a->len++] = (char)c;
 return 0;
}

/* Clear it now, so a PROVISION line's key does not linger in RAM until the next line arrives. */
void ws_line_discard(ws_line_asm *a)
{
 memset(a->buf, 0, sizeof a->buf);
 a->len = 0;
 a->overflow = 1;
}

int ws_cmd_find(const char *const names[], unsigned n, const char *line)
{
 for (unsigned i = 0; i < n; i++) {
  const char *name = names[i];
  size_t len = strlen(name);
  if (!strncmp(line, name, len) && (name[len - 1] == ' ' || line[len] == 0)) return (int)i;
 }
 return -1;
}

void ws_hex_text(const uint8_t *data, int n, char *text)
{
 static const char digits[] = "0123456789abcdef";
 for (int i = 0; i < n; i++, text += WS_HEX_PER_BYTE) {
  text[0] = digits[data[i] >> WS_HEX_DIGIT_BITS];
  text[1] = digits[data[i] & WS_HEX_DIGIT_MASK];
 }
 *text = 0;
}

int ws_hex_decode(const char *text, uint8_t *out, int max)
{
 int n = 0;
 /* bound: at most max + 1 passes: each one stores a byte or returns */
 while (text[0] && text[1]) {
  int b = ws_hex_byte(text);
  if (b < 0 || n >= max) return -1;
  out[n++] = (uint8_t)b;
  text += WS_HEX_PER_BYTE;
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
