/* GENERATED from ws_frame.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/common/ws_frame.lit.md (tests/test_tangle.py checks this file). */
#include "ws_frame.h"
#include <string.h>
#include "ws_be.h"
#include "mbedtls/aes.h"
#include "mbedtls/ccm.h"
#include "mbedtls/platform_util.h"

#define KEY_BITS (WS_KEY_LEN * CHAR_BIT)
#define AES_BLOCK_LEN 16
/* CCM nonce: kind u8, station u32, counter u64. */
#define NONCE_STATION_BYTES 4
#define NONCE_COUNTER_BYTES 8
#define NONCE_LEN (1 + NONCE_STATION_BYTES + NONCE_COUNTER_BYTES)
_Static_assert(NONCE_LEN == 13, "CCM with a 2-byte length field takes a 13-byte nonce (15 - L)");

/* Writes the header (also the AAD) and the nonce. The nonce comes from the integers, not from
 * the header bytes. The callers refuse a counter that the 5-byte field cannot hold. The nonce
 * must not depend on how the header packs the fields. */
static void header(uint8_t h[WS_HEADER_LEN], uint8_t nonce[NONCE_LEN], uint8_t kind, uint32_t station, uint64_t counter) {
 uint8_t *p = ws_write_u8(h, WS_FRAME_BYTE0(kind));
 p = ws_write_be(p, station, WS_STATION_BYTES);
 (void)ws_write_be(p, counter, WS_COUNTER_BYTES);
 p = ws_write_u8(nonce, kind);
 p = ws_write_be(p, station, NONCE_STATION_BYTES);
 (void)ws_write_be(p, counter, NONCE_COUNTER_BYTES);
}

/* Returns 1 if ws_seal_kind can seal these arguments: a plaintext that fits the frame and the
 * output, a valid station and counter, and a kind that the node or the gateway seals. */
static int seal_ok(uint32_t station, uint8_t kind, uint64_t counter, const uint8_t *plain, uint32_t plain_len, uint32_t out_cap) {
 if(plain_len>WS_FRAME_MAX-WS_FRAME_OVERHEAD || plain_len+WS_FRAME_OVERHEAD>out_cap || (!plain && plain_len)) return 0;
 if(station==0 || station>WS_STATION_MAX || counter==0 || counter>WS_COUNTER_MAX) return 0;
 return kind>=WS_KIND_OBS && kind<=WS_KIND_DIAG;
}

int ws_seal_kind(const uint8_t key[WS_KEY_LEN], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t *plain, uint32_t plain_len, uint8_t *out, uint32_t out_cap) {
 uint8_t nonce[NONCE_LEN]; mbedtls_ccm_context ccm; int rc;
 uint32_t len=plain_len+WS_FRAME_OVERHEAD;
 if(!out) return WS_FRAME_EINVAL;
 /* Every refusal wipes the whole output buffer. A caller that ignores the result then cannot
    send a stale or half-built frame. */
 if(!seal_ok(station,kind,counter,plain,plain_len,out_cap)) {
  mbedtls_platform_zeroize(out,out_cap);
  return WS_FRAME_EINVAL;
 }
 header(out,nonce,kind,station,counter);
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,KEY_BITS);
 if(!rc) rc=mbedtls_ccm_encrypt_and_tag(&ccm,plain_len,nonce,NONCE_LEN,out,WS_HEADER_LEN,
  plain,out+WS_HEADER_LEN,out+WS_HEADER_LEN+plain_len,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(rc) { mbedtls_platform_zeroize(out,out_cap); return WS_FRAME_ECRYPTO; }
 return (int)len;
}

/* The reply plaintext: epoch u32, seq u32, word u32 (UTC or NACK reason), echo u40. */
static void reply_unpack(const uint8_t plain[WS_REPLY_PLAIN_LEN], uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo) {
 const uint8_t *p = ws_read_be32(plain, epoch);
 p = ws_read_be32(p, seq);
 p = ws_read_be32(p, word);
 (void)ws_read_be(p, echo, WS_COUNTER_BYTES);
}

int ws_open_reply(const uint8_t key[WS_KEY_LEN], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo) {
 uint8_t expect[WS_HEADER_LEN], nonce[NONCE_LEN], plain[WS_REPLY_PLAIN_LEN]; mbedtls_ccm_context ccm; int rc;
 if(len!=WS_ACK_FRAME_LEN) return WS_FRAME_EINVAL;
 int k=ws_frame_kind(frame,len);
 if(k!=WS_KIND_ACK && k!=WS_KIND_NACK) return WS_FRAME_EHEADER;
 if(station==0 || station>WS_STATION_MAX) return WS_FRAME_EINVAL;   /* the caller's station, not the frame's */
 uint64_t ctr=ws_get_be64(frame+WS_COUNTER_OFF,WS_COUNTER_BYTES);
 header(expect,nonce,(uint8_t)k,station,ctr);
 if(memcmp(expect,frame,WS_COUNTER_OFF)) return WS_FRAME_EHEADER; /* version, kind, station */
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,KEY_BITS);
 if(!rc) rc=mbedtls_ccm_auth_decrypt(&ccm,WS_REPLY_PLAIN_LEN,nonce,NONCE_LEN,frame,WS_HEADER_LEN,
  frame+WS_HEADER_LEN,plain,frame+WS_HEADER_LEN+WS_REPLY_PLAIN_LEN,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(!rc) { *kind=(uint8_t)k; *counter=ctr; reply_unpack(plain,epoch,seq,word,echo); }
 mbedtls_platform_zeroize(plain,sizeof plain);
 return rc?WS_FRAME_EAUTH:WS_FRAME_OK;
}

int ws_key_check(const uint8_t key[WS_KEY_LEN], uint8_t out[WS_KCV_LEN]) {
 uint8_t block[AES_BLOCK_LEN]; mbedtls_aes_context aes; int rc;
 mbedtls_aes_init(&aes);
 rc=mbedtls_aes_setkey_enc(&aes,key,KEY_BITS);
 if(!rc) { const uint8_t zero[AES_BLOCK_LEN]={0}; rc=mbedtls_aes_crypt_ecb(&aes,MBEDTLS_AES_ENCRYPT,zero,block); }
 mbedtls_aes_free(&aes);
 if(!rc) memcpy(out,block,WS_KCV_LEN);
 mbedtls_platform_zeroize(block,sizeof block);   /* only 3 bytes of AES(key, 0) may leave */
 return rc;
}

/* Field order and widths: docs/protocol-design.md section 4 and ws0/protocol.py DIAG. */
void ws_diag_pack(const ws_diag_t *d, uint8_t out[WS_DIAG_PLAIN_LEN]) {
 uint8_t *p = ws_write_be32(out, d->epoch);
 p = ws_write_be32(p, d->uptime);
 p = ws_write_be16(p, d->pending);
 p = ws_write_be32(p, d->lost);
 p = ws_write_be16(p, d->torn);
 p = ws_write_be16(p, d->abandoned);
 p = ws_write_be16(p, d->no_ack);
 p = ws_write_be16(p, d->rejects);
 p = ws_write_u8(p, d->reset_cause);
 p = ws_write_u8(p, d->link);
 p = ws_write_be32(p, d->build);
 p = ws_write_u8(p, (uint8_t)d->rssi);
 p = ws_write_u8(p, (uint8_t)d->snr);
 p = ws_write_u8(p, d->crashes);
 (void)ws_write_u8(p, d->energy);
}
