#include "ws_frame.h"
#include <string.h>
#include "mbedtls/aes.h"
#include "mbedtls/ccm.h"
#include "mbedtls/platform_util.h"

static void put(uint8_t *out, uint64_t v, unsigned n) {
 for(unsigned i=0;i<n;i++) out[n-1-i]=(uint8_t)(v>>(8*i));
}
static uint64_t get(const uint8_t *in, unsigned n) {
 uint64_t v=0;
 for(unsigned i=0;i<n;i++) v=(v<<8)|in[i];
 return v;
}
/* Header doubles as AAD; nonce = kind + station + counter (13 bytes). */
static void header(uint8_t h[WS_HEADER_LEN], uint8_t nonce[13], uint8_t kind, uint32_t station, uint64_t counter) {
 h[0]='W'; h[1]='S'; h[2]=WS_FRAME_VERSION; h[3]=kind;
 put(h+4,station,4); put(h+8,counter,8);
 nonce[0]=kind; memcpy(nonce+1,h+4,12);
}

int ws_seal_obs(const uint8_t key[16], uint32_t station, uint64_t counter,
 const uint8_t plain[WS_OBS_PLAIN_LEN], uint8_t out[WS_OBS_FRAME_LEN]) {
 return ws_seal_kind(key,station,WS_KIND_OBS,counter,plain,out);
}

int ws_seal_kind(const uint8_t key[16], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t plain[WS_OBS_PLAIN_LEN], uint8_t out[WS_OBS_FRAME_LEN]) {
 uint8_t nonce[13]; mbedtls_ccm_context ccm; int rc;
 header(out,nonce,kind,station,counter);
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,128);
 if(!rc) rc=mbedtls_ccm_encrypt_and_tag(&ccm,WS_OBS_PLAIN_LEN,nonce,13,out,WS_HEADER_LEN,
  plain,out+WS_HEADER_LEN,out+WS_HEADER_LEN+WS_OBS_PLAIN_LEN,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(rc) mbedtls_platform_zeroize(out,WS_OBS_FRAME_LEN);
 return rc;
}

int ws_open_reply(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint64_t *utc, uint64_t *echo) {
 uint8_t expect[WS_HEADER_LEN], nonce[13], plain[WS_ACK_PLAIN_LEN]; mbedtls_ccm_context ccm; int rc;
 if(len!=WS_ACK_FRAME_LEN) return -1;
 if(frame[3]!=WS_KIND_ACK && frame[3]!=WS_KIND_NACK) return -2;
 uint64_t ctr=get(frame+8,8);
 header(expect,nonce,frame[3],station,ctr);
 if(memcmp(expect,frame,8)) return -2; /* magic, version, kind, station */
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,128);
 if(!rc) rc=mbedtls_ccm_auth_decrypt(&ccm,WS_ACK_PLAIN_LEN,nonce,13,frame,WS_HEADER_LEN,
  frame+WS_HEADER_LEN,plain,frame+WS_HEADER_LEN+WS_ACK_PLAIN_LEN,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(!rc) {
  *kind=frame[3]; *counter=ctr; *epoch=(uint32_t)get(plain,4); *seq=(uint32_t)get(plain+4,4); *utc=get(plain+8,8); *echo=get(plain+16,8);
 }
 mbedtls_platform_zeroize(plain,sizeof plain);
 return rc?-3:0;
}

int ws_open_ack(const uint8_t key[16], uint32_t station, const uint8_t *frame, uint32_t len,
 uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint64_t *utc, uint64_t *echo) {
 uint8_t kind;
 if(len>3 && frame[3]!=WS_KIND_ACK) return -2;
 return ws_open_reply(key,station,frame,len,&kind,counter,epoch,seq,utc,echo);
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
