#ifndef WS_FRAME_H
#define WS_FRAME_H
#include <stddef.h>
#include <stdint.h>
/* Protocol draft 5 envelope (docs/protocol-draft5-design.md sections 3-4); AES-128-CCM via Mbed TLS.
 * The gateway (ws0/protocol.py) builds the same bytes, checked by tests/test_frame.py. */
#define WS_FRAME_VERSION 5
#define WS_KIND_OBS 1
#define WS_KIND_ACK 2
#define WS_KIND_NACK 3 /* authentic but permanently rejected (gap G2) */
#define WS_KIND_DIAG 4 /* node health, fire-and-forget (gap G8) */
#define WS_NACK_COLLISION 1
#define WS_NACK_INVALID 2
#define WS_HEADER_LEN 8          /* version<<4 | kind, station u16, counter u40 */
#define WS_TAG_LEN 8             /* CCM M = 8, fixed (section 3.3) */
#define WS_FRAME_OVERHEAD (WS_HEADER_LEN + WS_TAG_LEN)
#define WS_STATION_MAX 65535U
#define WS_COUNTER_MAX 0xFFFFFFFFFFULL /* 2^40 - 1: the header holds 5 bytes */
#define WS_REPLY_PLAIN_LEN 17    /* ACK/NACK: epoch u32, seq u32, UTC or reason u32, echo u40 */
#define WS_ACK_FRAME_LEN (WS_FRAME_OVERHEAD + WS_REPLY_PLAIN_LEN)
#define WS_FRAME_MAX 255U        /* a LoRa payload */
#define WS_DIAG_PLAIN_LEN 32     /* health report (section 4) */
#define WS_DIAG_FRAME_LEN (WS_FRAME_OVERHEAD + WS_DIAG_PLAIN_LEN)
#define WS_FRAME_BYTE0(kind) ((uint8_t)((WS_FRAME_VERSION << 4) | (kind)))
_Static_assert(WS_HEADER_LEN == 8 && WS_TAG_LEN == 8, "draft-5 header and CCM tag are 8 bytes");
_Static_assert(WS_ACK_FRAME_LEN == 33, "draft-5 ACK/NACK frames are 33 bytes");

/* Seal one node-to-gateway or gateway-to-node frame. The caller reserves counter durably first;
 * it must never repeat for this key. Returns the frame length (plain_len + 16), or a negative
 * value, with out zeroized, if: station is 0 or above WS_STATION_MAX, counter is 0 or above
 * WS_COUNTER_MAX (the 5-byte header field would truncate it and repeat a nonce), kind is not 1-4,
 * the frame would exceed out_cap or WS_FRAME_MAX, or the cipher fails. */
int ws_seal_kind(const uint8_t key[16], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t *plain, uint32_t plain_len, uint8_t *out, uint32_t out_cap);
/* Open an ACK (kind 2) or NACK (kind 3). word = UTC for an ACK, the reason for a NACK.
 * 0 on success; nonzero for a wrong length, version, kind or station, or a failed tag. */
int ws_open_reply(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo);
/* Kind of a frame of this version (1-15), or -1 if it is empty or another version. Inline: the
 * keyless RX bridge uses it without linking the crypto code. */
static inline int ws_frame_kind(const uint8_t *frame, uint32_t len) {
 if(!frame || len<1 || (frame[0]>>4)!=WS_FRAME_VERSION) return -1;
 return frame[0]&0x0F;
}
/* Health report plaintext (kind 4, docs/protocol-draft5-design.md section 4; ws0/protocol.py DIAG,
 * checked byte for byte by tests/test_frame.py). The caller clamps the counts. */
typedef struct {
 uint32_t epoch, uptime, lost, build;               /* build: first 4 bytes of the release commit */
 uint16_t pending, torn, abandoned, no_ack, rejects;
 uint8_t reset_cause, link, crashes, energy;
 int8_t rssi, snr;                                  /* last authentic ACK as heard; -128 = none yet */
} ws_diag_t;
void ws_diag_pack(const ws_diag_t *d, uint8_t out[WS_DIAG_PLAIN_LEN]);
/* Key check value: first 3 bytes of AES-ECB(key, zero block); safe to display. */
int ws_key_check(const uint8_t key[16], uint8_t out[3]);
/* Zero key material. A plain memset of a buffer that is not read again is a dead store the
   compiler may delete; writes through a volatile pointer are kept. */
static inline void ws_wipe(void *p, size_t n) { volatile uint8_t *v = (volatile uint8_t *)p; while (n--) *v++ = 0; }
#endif
