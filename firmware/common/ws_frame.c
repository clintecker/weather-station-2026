#include "ws_frame.h"
#include <string.h>
#include "ws_be.h"
#include "mbedtls/aes.h"
#include "mbedtls/ccm.h"
#include "mbedtls/platform_util.h"

/* Header (also the AAD) and nonce. The nonce is built from the integers, kind + station u32 +
 * counter u64 (13 bytes), never copied from the header: a counter the 5-byte field cannot hold
 * must not reach here (callers check), and the nonce must not depend on how the header packs it. */
static void header(uint8_t h[WS_HEADER_LEN], uint8_t nonce[13], uint8_t kind, uint32_t station, uint64_t counter) {
 h[0]=WS_FRAME_BYTE0(kind); ws_put_be64(h+1,station,2); ws_put_be64(h+3,counter,5);
 nonce[0]=kind; ws_put_be64(nonce+1,station,4); ws_put_be64(nonce+5,counter,8);
}

/* What ws_seal_kind can seal: a plaintext that fits the frame and the output, a valid station,
 * counter and sealed kind. */
static int seal_ok(uint32_t station, uint8_t kind, uint64_t counter, const uint8_t *plain, uint32_t plain_len, uint32_t out_cap) {
 if(plain_len>WS_FRAME_MAX-WS_FRAME_OVERHEAD || plain_len+WS_FRAME_OVERHEAD>out_cap || (!plain && plain_len)) return 0;
 if(station==0 || station>WS_STATION_MAX || counter==0 || counter>WS_COUNTER_MAX) return 0;
 return kind>=WS_KIND_OBS && kind<=WS_KIND_DIAG;
}

int ws_seal_kind(const uint8_t key[16], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t *plain, uint32_t plain_len, uint8_t *out, uint32_t out_cap) {
 uint8_t nonce[13]; mbedtls_ccm_context ccm; int rc;
 uint32_t len=plain_len+WS_FRAME_OVERHEAD;
 if(!out) return -1;
 /* Every refusal wipes the whole output buffer, so a caller that ignores the result cannot send
    a stale or half-built frame. */
 if(!seal_ok(station,kind,counter,plain,plain_len,out_cap)) {
  mbedtls_platform_zeroize(out,out_cap);
  return -1;
 }
 header(out,nonce,kind,station,counter);
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,128);
 if(!rc) rc=mbedtls_ccm_encrypt_and_tag(&ccm,plain_len,nonce,13,out,WS_HEADER_LEN,
  plain,out+WS_HEADER_LEN,out+WS_HEADER_LEN+plain_len,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(rc) { mbedtls_platform_zeroize(out,out_cap); return -2; }
 return (int)len;
}

int ws_open_reply(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo) {
 uint8_t expect[WS_HEADER_LEN], nonce[13], plain[WS_REPLY_PLAIN_LEN]; mbedtls_ccm_context ccm; int rc;
 if(len!=WS_ACK_FRAME_LEN) return -1;
 int k=ws_frame_kind(frame,len);
 if(k!=WS_KIND_ACK && k!=WS_KIND_NACK) return -2;
 if(station==0 || station>WS_STATION_MAX) return -2;
 uint64_t ctr=ws_get_be64(frame+3,5);
 header(expect,nonce,(uint8_t)k,station,ctr);
 if(memcmp(expect,frame,3)) return -2; /* version, kind, station */
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,128);
 if(!rc) rc=mbedtls_ccm_auth_decrypt(&ccm,WS_REPLY_PLAIN_LEN,nonce,13,frame,WS_HEADER_LEN,
  frame+WS_HEADER_LEN,plain,frame+WS_HEADER_LEN+WS_REPLY_PLAIN_LEN,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(!rc) {
  *kind=(uint8_t)k; *counter=ctr; *epoch=ws_get_be32(plain); *seq=ws_get_be32(plain+4);
  *word=ws_get_be32(plain+8); *echo=ws_get_be64(plain+12,5);
 }
 mbedtls_platform_zeroize(plain,sizeof plain);
 return rc?-3:0;
}

int ws_key_check(const uint8_t key[16], uint8_t out[3]) {
 uint8_t zero[16]={0}, block[16]; mbedtls_aes_context aes; int rc;
 mbedtls_aes_init(&aes);
 rc=mbedtls_aes_setkey_enc(&aes,key,128);
 if(!rc) rc=mbedtls_aes_crypt_ecb(&aes,MBEDTLS_AES_ENCRYPT,zero,block);
 mbedtls_aes_free(&aes);
 if(!rc) memcpy(out,block,3);
 return rc;
}

void ws_diag_pack(const ws_diag_t *d, uint8_t out[WS_DIAG_PLAIN_LEN]) {
 ws_put_be32(out,d->epoch); ws_put_be32(out+4,d->uptime); ws_put_be16(out+8,d->pending);
 ws_put_be32(out+10,d->lost); ws_put_be16(out+14,d->torn); ws_put_be16(out+16,d->abandoned);
 ws_put_be16(out+18,d->no_ack); ws_put_be16(out+20,d->rejects);
 out[22]=d->reset_cause; out[23]=d->link; ws_put_be32(out+24,d->build);
 out[28]=(uint8_t)d->rssi; out[29]=(uint8_t)d->snr; out[30]=d->crashes; out[31]=d->energy;
}
