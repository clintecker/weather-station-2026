/* Minimal Mbed TLS 3.6 configuration: AES-128-CCM only (Stage-0 radio frames). */
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
#endif
