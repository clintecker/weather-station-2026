#ifndef WS_FRAME_H
#define WS_FRAME_H
#include <stdint.h>
/* Stage-0 transport draft 4 (docs/protocol.md); AES-128-CCM via Mbed TLS. */
#define WS_FRAME_VERSION 4
#define WS_KIND_OBS 1
#define WS_KIND_ACK 2
#define WS_HEADER_LEN 16
#define WS_TAG_LEN 16
#define WS_OBS_PLAIN_LEN 24
#define WS_ACK_PLAIN_LEN 24 /* epoch, seq, host UTC, echoed observation counter */
#define WS_OBS_FRAME_LEN (WS_HEADER_LEN+WS_OBS_PLAIN_LEN+WS_TAG_LEN)
#define WS_ACK_FRAME_LEN (WS_HEADER_LEN+WS_ACK_PLAIN_LEN+WS_TAG_LEN)
/* Caller reserves counter durably before sealing; it must never repeat for this key. */
int ws_seal_obs(const uint8_t key[16], uint32_t station, uint64_t counter,
 const uint8_t plain[WS_OBS_PLAIN_LEN], uint8_t out[WS_OBS_FRAME_LEN]);
/* 0 on success; nonzero for wrong length/header/station or failed authentication. */
int ws_open_ack(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint64_t *utc, uint64_t *echo);
/* Key check value: first 3 bytes of AES-ECB(key, zero block); safe to display. */
int ws_key_check(const uint8_t key[16], uint8_t out[3]);
#endif
