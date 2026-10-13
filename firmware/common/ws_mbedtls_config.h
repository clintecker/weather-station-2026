/* Minimal Mbed TLS 3.6 configuration: AES-128-CCM only (Stage-0 radio frames). */
#ifndef WS_MBEDTLS_CONFIG_H
#define WS_MBEDTLS_CONFIG_H
#define MBEDTLS_AES_C
#define MBEDTLS_CCM_C
#define MBEDTLS_CIPHER_C
/* Tables in flash, not RAM; one table set. Speed is irrelevant at one frame per minute. */
#define MBEDTLS_AES_ROM_TABLES
#define MBEDTLS_AES_FEWER_TABLES
#endif
