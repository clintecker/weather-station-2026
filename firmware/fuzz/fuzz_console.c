/* Console byte stream, as the UART interrupt delivers it on either board: bytes go through the
 * line assembler (ws_line_feed); each completed line goes through what the boards do with it:
 * RX decodes an ACK/NACK hex line for transmission, TX parses PROVISION arguments.
 * Properties: no memory error; a line is never longer than WS_LINE_MAX, never empty and never
 * contains '\n' or '\r'; a hex decode is exactly half the line; only a 33-byte version-5 ACK/NACK
 * passes the RX downstream check, and only valid observation/health-report lengths the upstream one. */
#include <string.h>
#include "fuzz.h"
#include "stage0.h"
#include "ws_console.h"
#include "ws_frame.h"

#define PROVISION "PROVISION "

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
 static ws_line_asm a;            /* static like the firmware's; reset per input */
 char line[WS_LINE_MAX + 1];
 memset(&a, 0, sizeof a);
 for (size_t i = 0; i < size; i++) {
  int n = ws_line_feed(&a, data[i], line);
  FUZZ_CHECK(n >= 0 && n <= WS_LINE_MAX && a.len <= WS_LINE_MAX);
  if (a.overflow) for (int k = 0; k < WS_LINE_MAX; k++) FUZZ_CHECK(a.buf[k] == 0);   /* over-long line wiped */
  if (n == 0) continue;
  FUZZ_CHECK(strlen(line) == (size_t)n);   /* no NUL inside: such a line is discarded */
  for (int k = 0; k < n; k++) FUZZ_CHECK(line[k] >= ' ' && line[k] <= '~');   /* printable ASCII only */
  FUZZ_CHECK(!memchr(line, '\n', (size_t)n) && !memchr(line, '\r', (size_t)n));
  for (int k = 0; k < n; k++) FUZZ_CHECK(a.buf[k] == 0);   /* key hygiene: buffer cleared */
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  int got = ws_hex_decode(line, frame, (int)sizeof frame);
  FUZZ_CHECK(got == -1 || ((size_t)got * SPEC_HEX_PER_BYTE == strlen(line) && got <= (int)sizeof frame));
  if (got >= 0) {   /* hex out (the #rx crc capture) and back in is the identity */
   char text[SPEC_HEX_PER_BYTE * (WS_ACK_FRAME_LEN + 1) + 1]; uint8_t back[WS_ACK_FRAME_LEN + 1];
   ws_hex_text(frame, got, text);
   FUZZ_CHECK(strlen(text) == (size_t)got * SPEC_HEX_PER_BYTE && ws_hex_decode(text, back, (int)sizeof back) == got && !memcmp(back, frame, (size_t)got));
  }
  if (ws_host_reply_ok(frame, got))
   FUZZ_CHECK(got == WS_ACK_FRAME_LEN && (frame[0] == SPEC_BYTE0(WS_KIND_ACK) || frame[0] == SPEC_BYTE0(WS_KIND_NACK)));
  /* The same bytes as a received radio frame: only a version-5 observation within the catalog's
     length range, or a health report of its fixed length, is forwarded upstream. */
  if (got > 0 && ws_air_frame_ok(frame, (uint32_t)got))
   FUZZ_CHECK((frame[0] == SPEC_BYTE0(WS_KIND_OBS) && got >= SPEC_OBS_FRAME_MIN && got <= SPEC_OBS_FRAME_MAX) ||
             (frame[0] == SPEC_BYTE0(WS_KIND_DIAG) && got == SPEC_DIAG_FRAME_LEN));
  uint32_t station, floor; uint8_t key[WS_KEY_LEN];
  if (!strncmp(line, PROVISION, sizeof PROVISION - 1) && !ws_parse_provision(line + sizeof PROVISION - 1, &station, key, &floor))
   FUZZ_CHECK(station != 0);
 }
 return 0;
}
