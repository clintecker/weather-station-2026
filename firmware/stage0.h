#ifndef WS_STAGE0_H
#define WS_STAGE0_H
#include <stdint.h>
#include <stddef.h>
/* Portable core; board HAL, flash journal, AES-CCM and RF remain integration work. */
typedef struct {
 void *context;
 int (*write)(void *, uint8_t, const uint8_t *, size_t);
 int (*read)(void *, uint8_t, uint8_t *, size_t);
 void (*delay_ms)(void *, uint32_t);
} ws_i2c;
int ws_sht45_read(const ws_i2c *, int16_t *, uint16_t *);
/* Draft 3: invalid readings carry physically impossible fillers, never plausible values.
   The validity flag stays authoritative; fillers only protect flag-blind readers. */
#define WS_TEMP_INVALID ((int16_t)-32768)  /* 0x8000 = -327.68 degC */
#define WS_RH_INVALID   ((uint16_t)0xFFFF) /* 655.35 %RH */
uint8_t ws_crc8(const uint8_t *, size_t);
void ws_pack_observation(uint8_t out[24], uint32_t epoch, uint32_t seq,
 uint64_t utc, int16_t centi_c, uint16_t centi_rh, uint8_t valid, uint8_t synchronized);
#endif
