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
/* Draft 4: utc = UTC seconds (sent only when synchronized); uptime = seconds since boot,
   always sent, so the gateway can reconstruct the time of unsynchronized samples. */
void ws_pack_observation(uint8_t out[24], uint32_t epoch, uint32_t seq,
 uint32_t utc, uint32_t uptime, int16_t centi_c, uint16_t centi_rh, uint8_t valid, uint8_t synchronized);
/* Stuck-bus recovery as a pin sequence, so the waveform is host-tested (I2C-bus spec UM10204
   section 3.1.16). Pins are open-drain: level 1 releases the line. The caller sets both lines
   released before handing over. Clocks SCL until SDA is free (at most 9), then makes a STOP:
   SDA low while SCL is low, SCL high, then SDA high. Returns -1 if SDA is still held low. */
typedef struct {
 void *context;
 void (*set_scl)(void *, int);
 void (*set_sda)(void *, int);
 int (*read_sda)(void *);
 void (*wait_us)(void *, uint32_t);
} ws_i2c_pins;
int ws_i2c_recover(const ws_i2c_pins *);
/* Link gate for one minute (docs/radio-energy-policy.md section 6). energy: 0 SURPLUS,
   1 NORMAL, 2 CONSERVE, 3 CRITICAL. While probing, healthy energy (SURPLUS, NORMAL) still
   sends the live reading every minute, so the node relinks within a minute; only CONSERVE
   waits for the back-off schedule (secs_until_probe <= 0). CRITICAL never transmits. */
int ws_link_may_send(int energy, int probing, int32_t secs_until_probe);
/* PROVISION arguments "<station_id> <32 hex key> [epoch_floor]": exact single spaces, decimal
   digits only (no sign), station 1..4294967295, epoch floor below WS_EPOCH_FLOOR_MAX so a typo
   cannot exhaust the epoch space. Returns 0 on success; outputs are undefined on error. */
#define WS_EPOCH_FLOOR_MAX 0xFFFF0000UL
int ws_parse_provision(const char *args, uint32_t *station, uint8_t key[16], uint32_t *epoch_floor);
#endif
