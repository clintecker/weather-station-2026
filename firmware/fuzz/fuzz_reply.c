/* The draft-5 envelope (firmware/common/ws_frame.c), both directions, under the self-test key.
 * Opening: any bytes from the air go through ws_open_reply as the TX node receives them. Nothing
 * opens except the two genuine frames (the self-test vectors in App/app_tx.c and
 * tests/test_frame.py); anything else would be a forgery.
 * Sealing: the input also chooses a station, counter, kind and plaintext, biased to the edges
 * (0, 1, the 16-bit station and 40-bit counter limits and one past them). Out-of-range values must
 * be refused with the output zeroized, never truncated into the 2- and 5-byte header fields (that
 * would repeat a nonce); accepted ones must give exactly the spec's header and length, and an
 * ACK/NACK must open again to the same values. */
#include <string.h>
#include "fuzz.h"
#include "ws_frame.h"

static const uint8_t KEY[16] = { 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 };
static const uint8_t ACK[WS_ACK_FRAME_LEN] = {
 0x52,0x00,0x01,0x00,0x00,0x00,0x00,0x05,0x0e,0x1e,0xb4,0x54,0x47,0x66,0xf4,0xe6,0xe0,0xff,0xdb,0xb3,0xf6,0xd1,0x41,0x3d,
 0x06,0xf6,0x36,0x95,0x00,0x19,0x9b,0x8f,0xe2 };
static const uint8_t NACK[WS_ACK_FRAME_LEN] = {
 0x53,0x00,0x01,0x00,0x00,0x00,0x00,0x06,0x84,0x9a,0xdd,0xbf,0x88,0xd9,0xaa,0xdd,0x88,0x4a,0xa3,0xbb,0x89,0x13,0x65,0x75,
 0x37,0x45,0x21,0xc5,0xe4,0x16,0xa1,0xd0,0xc9 };

static uint64_t edge(uint8_t sel, uint64_t raw, uint64_t max)
{
 switch (sel % 6U) {
  case 0: return 0;
  case 1: return 1;
  case 2: return max;
  case 3: return max + 1U;
  case 4: return raw;
  default: return raw % (max + 2U);
 }
}

static uint64_t be(const uint8_t *p, unsigned n)
{
 uint64_t v = 0;
 for (unsigned i = 0; i < n; i++) v = v << 8 | p[i];
 return v;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
 uint8_t kind; uint64_t counter, echo; uint32_t epoch, seq, word;
 if (size > WS_FRAME_MAX) return 0;
 int rc = ws_open_reply(KEY, 1, data, (uint32_t)size, &kind, &counter, &epoch, &seq, &word, &echo);
 if (rc == 0) {
  FUZZ_CHECK(size == WS_ACK_FRAME_LEN);
  FUZZ_CHECK(!memcmp(data, ACK, size) || !memcmp(data, NACK, size));
  FUZZ_CHECK(kind == (data[0] & 0x0F));
 }

 if (size < 16) return 0;
 uint32_t station = (uint32_t)edge(data[0], be(data + 1, 4), WS_STATION_MAX);
 uint64_t ctr = edge(data[5], be(data + 6, 8), WS_COUNTER_MAX);
 uint8_t k = (uint8_t)(data[14] % 6U);                /* 0-5: two invalid kinds */
 uint32_t plen = (uint32_t)(size - 15U);
 const uint8_t *plain = data + 15;
 uint8_t out[WS_FRAME_MAX + 8];
 memset(out, 0xA5, sizeof out);
 int n = ws_seal_kind(KEY, station, k, ctr, plain, plen, out, (uint32_t)sizeof out);
 int valid = station >= 1 && station <= WS_STATION_MAX && ctr >= 1 && ctr <= WS_COUNTER_MAX && k >= 1 && k <= 4 &&
             plen + WS_FRAME_OVERHEAD <= WS_FRAME_MAX;
 if (!valid) {
  FUZZ_CHECK(n < 0);
  for (size_t i = 0; i < sizeof out; i++) FUZZ_CHECK(out[i] == 0);   /* nothing usable left behind */
  return 0;
 }
 FUZZ_CHECK(n == (int)(plen + WS_FRAME_OVERHEAD));
 FUZZ_CHECK(out[0] == (uint8_t)(WS_FRAME_VERSION << 4 | k) && be(out + 1, 2) == station && be(out + 3, 5) == ctr);
 if ((k == WS_KIND_ACK || k == WS_KIND_NACK) && plen == WS_REPLY_PLAIN_LEN && station == 1) {
  FUZZ_CHECK(ws_open_reply(KEY, 1, out, (uint32_t)n, &kind, &counter, &epoch, &seq, &word, &echo) == 0);
  FUZZ_CHECK(kind == k && counter == ctr && epoch == be(plain, 4) && seq == be(plain + 4, 4) &&
             word == be(plain + 8, 4) && echo == be(plain + 12, 5));
 }
 return 0;
}
