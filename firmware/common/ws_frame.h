#ifndef WS_FRAME_H
#define WS_FRAME_H
#include <stdint.h>
/* Stage-0 transport draft 4 (docs/protocol.md); AES-128-CCM via Mbed TLS. */
#define WS_FRAME_VERSION 4
#define WS_KIND_OBS 1
#define WS_KIND_ACK 2
#define WS_KIND_NACK 3 /* authentic but permanently rejected (gap G2) */
#define WS_KIND_DIAG 4 /* node health counters, fire-and-forget (gap G8) */
#define WS_NACK_COLLISION 1
#define WS_NACK_INVALID 2
#define WS_HEADER_LEN 16
#define WS_TAG_LEN 16
#define WS_OBS_PLAIN_LEN 24
#define WS_ACK_PLAIN_LEN 24 /* epoch, seq, host UTC, echoed observation counter */
#define WS_OBS_FRAME_LEN (WS_HEADER_LEN+WS_OBS_PLAIN_LEN+WS_TAG_LEN)
#define WS_ACK_FRAME_LEN (WS_HEADER_LEN+WS_ACK_PLAIN_LEN+WS_TAG_LEN)
/* Protocol draft 4 sizes (docs/protocol.md); the gateway (ws0/protocol.py) packs the same layout,
   checked by the C-vs-Python agreement tests. A change here is a protocol change, not a tweak. */
_Static_assert(WS_HEADER_LEN == 16 && WS_TAG_LEN == 16, "draft-4 header and CCM tag are 16 bytes");
_Static_assert(WS_OBS_PLAIN_LEN == 24 && WS_ACK_PLAIN_LEN == 24, "draft-4 plaintexts are 24 bytes");
_Static_assert(WS_OBS_FRAME_LEN == 56 && WS_ACK_FRAME_LEN == 56, "draft-4 frames are 56 bytes");
_Static_assert(WS_OBS_FRAME_LEN <= 255, "a LoRa payload is at most 255 bytes");
/* Caller reserves counter durably before sealing; it must never repeat for this key.
   ws_seal_kind seals any node-to-gateway kind (observation or diagnostics). */
int ws_seal_kind(const uint8_t key[16], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t plain[WS_OBS_PLAIN_LEN], uint8_t out[WS_OBS_FRAME_LEN]);
int ws_seal_obs(const uint8_t key[16], uint32_t station, uint64_t counter,
 const uint8_t plain[WS_OBS_PLAIN_LEN], uint8_t out[WS_OBS_FRAME_LEN]);
/* 0 on success; nonzero for wrong length/header/station or failed authentication. */
int ws_open_ack(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint64_t *utc, uint64_t *echo);
/* Opens an ACK (kind 2) or NACK (kind 3). word = bytes 8..15 of the plaintext: host UTC
   for an ACK; (reason << 32) for a NACK. 0 on success. */
int ws_open_reply(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint64_t *word, uint64_t *echo);
/* Key check value: first 3 bytes of AES-ECB(key, zero block); safe to display. */
int ws_key_check(const uint8_t key[16], uint8_t out[3]);
#endif
