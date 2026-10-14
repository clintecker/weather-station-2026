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
uint8_t ws_crc8(const uint8_t *, size_t);
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
   digits only (no sign), station 1..65535 (the draft-5 header's u16), epoch floor below WS_EPOCH_FLOOR_MAX so a typo
   cannot exhaust the epoch space. Returns 0 on success; outputs are undefined on error. */
#define WS_EPOCH_FLOOR_MAX 0xFFFF0000UL
/* Health helpers (docs/firmware-review-2026-10-13.md P6, P7). A failure run counts uninterrupted
   failures (any success resets it; saturates); tripped when it exceeds the limit. */
typedef struct { uint32_t n; } ws_failrun;
void ws_failrun_note(ws_failrun *, int ok);
int ws_failrun_tripped(const ws_failrun *, uint32_t limit);
/* 1 if more than limit_ms passed from last_ms to now_ms on a wrapping 32-bit ms tick. Inline so
   the RX role, which does not link stage0.c, can use it. */
static inline int ws_silent_for(uint32_t now_ms, uint32_t last_ms, uint32_t limit_ms)
{ return (uint32_t)(now_ms - last_ms) > limit_ms; }
int ws_parse_provision(const char *args, uint32_t *station, uint8_t key[16], uint32_t *epoch_floor);
/* Run-time stack monitor: unused stack is filled with WS_STACK_PAINT at boot; the peak is the
   distance from the stack top down to the lowest word that no longer holds the paint. lo..top is
   the painted range (lo = lowest address). Inline so both roles can use it. */
#define WS_STACK_PAINT 0xC5C5C5C5u
static inline uint32_t ws_stack_peak(const uint32_t *lo, const uint32_t *top)
{
 const uint32_t *p = lo;
 while (p < top && *p == WS_STACK_PAINT) p++;
 return (uint32_t)((const char *)top - (const char *)p);
}
#endif
