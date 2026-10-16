/* Minimal Mbed TLS 3.6 configuration: AES-128-CCM only (the radio frames). */
#ifndef WS_MBEDTLS_CONFIG_H
#define WS_MBEDTLS_CONFIG_H
#define MBEDTLS_AES_C
#define MBEDTLS_CCM_C
/* No MBEDTLS_CIPHER_C: without the generic cipher layer, Mbed TLS 3.6 enables
 * MBEDTLS_BLOCK_CIPHER_C, so CCM holds its AES context inline. The cipher layer calloc'd a context
 * for every seal/open (cipher_wrap.c); this path uses no heap at all. */
/* Tables in flash, not RAM; one table set. Speed is irrelevant at one frame per minute. */
#define MBEDTLS_AES_ROM_TABLES
#define MBEDTLS_AES_FEWER_TABLES
/* CCM runs AES forward only (CTR + CBC-MAC), for sealing and opening alike, and the key check value
 * is an ECB encryption: no AES decryption or its inverse tables. */
#define MBEDTLS_BLOCK_CIPHER_NO_DECRYPT
/* Keys are AES-128 only (the protocol uses no other size): smaller key schedule code and a smaller AES context
 * on the stack. A 192/256-bit key is refused (MBEDTLS_ERR_AES_INVALID_KEY_LENGTH). */
#define MBEDTLS_AES_ONLY_128_BIT_KEY_LENGTH
#endif
