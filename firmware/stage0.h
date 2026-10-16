#ifndef WS_STAGE0_H
#define WS_STAGE0_H
#include <stdint.h>
#include <stddef.h>
/* Portable core; board HAL, flash journal, AES-CCM and RF remain integration work. */
/* SHT45 (SHT4x datasheet, Table 4: high repeatability 6.9 ms typ, 8.3 ms max): write
   WS_SHT45_MEASURE to WS_SHT45_ADDR, wait WS_SHT45_MEASURE_MS, then read WS_SHT45_REPLY_LEN bytes.
   11 ms: ST's timer rounds down to 1/1024 s ticks and can start up to a tick late, so this waits
   at least ~9.8 ms. The firmware
   does each step from an interrupt or timer (App/sensor.c); ws_sht45_parse checks both CRCs and
   converts: 0, or -4 on a CRC mismatch (outputs untouched). */
#define WS_SHT45_ADDR       0x44
#define WS_SHT45_MEASURE    0xfd
#define WS_SHT45_MEASURE_MS 11
#define WS_SHT45_REPLY_LEN  6
int ws_sht45_parse(const uint8_t bytes[WS_SHT45_REPLY_LEN], int16_t *centi_c, uint16_t *centi_rh);
uint8_t ws_crc8(const uint8_t *, size_t);
/* One minute of 15-s T/RH samples (PRD section 9: coverage, mean and extrema). Samples whose
   temperature is outside the SHT45 range (-40.00..125.00 C) are not counted; RH is clamped to
   0..100 % first. The mean rounds half up, in integers, like the catalog (protocol.md). */
typedef struct { int32_t t_sum, h_sum; int16_t t_min, t_max; uint16_t h_min, h_max; uint8_t n; } ws_th_window;
void ws_th_reset(ws_th_window *w);
void ws_th_add(ws_th_window *w, int valid, int16_t centi_c, uint16_t centi_rh);
/* Mean of the counted samples in 0.01 units; 0 if none were counted (then all values are INVALID). */
int ws_th_mean_t(const ws_th_window *w, int16_t *centi_c);
int ws_th_mean_h(const ws_th_window *w, uint16_t *centi_rh);
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
/* The same sequence one half period at a time, for a timer to drive (no busy-wait): begin, wait,
   then step and wait while it returns 1; it ends with 0 (bus free) or -1. ws_i2c_recover runs
   it with wait_us between steps (host tests). */
#define WS_I2C_HALF_US 5   /* 100 kHz */
/* Steps of one recovery, the last included: 9 clock pulses of 2 steps, the STOP's 4, the result. */
#define WS_I2C_RECOVER_STEPS 23
typedef struct { uint8_t phase, pulses, held; } ws_i2c_rec;
void ws_i2c_recover_begin(ws_i2c_rec *, const ws_i2c_pins *);
int ws_i2c_recover_step(ws_i2c_rec *, const ws_i2c_pins *);
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
/* Health helpers (TX failure runs, RX radio silence). A failure run counts uninterrupted
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
 while (p < top && *p == WS_STACK_PAINT) p++;   /* bound: top - lo words */
 return (uint32_t)((const char *)top - (const char *)p);
}
/* The same scan a slice at a time, for a periodic report: reading the whole painted range (about
   17 KB on the RX) took 1.5 ms of a 1.7 ms #alive (measured 2026-10-16). Each call reads at most
   `slice` words from where the last one stopped; a pass runs from lo up to the deepest word found
   so far and then starts again at lo, so a deeper use is seen within one pass. Returns the peak
   found so far (bytes from the top), at most one pass old. Zero-initialise the state. */
typedef struct { const uint32_t *cursor, *deepest; } ws_stack_scan;
static inline uint32_t ws_stack_scan_step(ws_stack_scan *s, const uint32_t *lo, const uint32_t *top, uint32_t slice)
{
 if (!s->deepest) { s->deepest = top; s->cursor = lo; }
 const uint32_t *end = (uint32_t)(s->deepest - s->cursor) > slice ? s->cursor + slice : s->deepest;
 const uint32_t *p = s->cursor;
 while (p < end && *p == WS_STACK_PAINT) p++;   /* bound: slice words */
 if (p < end) { s->deepest = p; s->cursor = lo; }          /* deeper than before: the next pass starts over */
 else s->cursor = end == s->deepest ? lo : end;            /* this pass is done, or goes on next call */
 return (uint32_t)((const char *)top - (const char *)s->deepest);
}
#endif
