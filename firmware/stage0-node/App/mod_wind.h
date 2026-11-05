#ifndef MOD_WIND_H
#define MOD_WIND_H
/* The wind module (WSMP module type 6): the SparkFun SEN-15901 cups and vane. Every tick (250 ms) it
 * reads the cup pulse counter; every second it reads the vane. Channels: the pulse counter since
 * boot, the 3-s gust, and the east and north sums of the vane's unit vectors. */
#include <stdint.h>
#include "wsmp.h"

/* Board seams (link-time, App/board_inputs.c on the board, a host harness on the host):
   the LPTIM1 counter of cup pulses (16 bits, free running; one read, which may tear), and the vane
   ADC: 1 and the latest completed conversion in mV, with the next conversion started; 0 if none. */
uint16_t board_pulse_count(void);
int board_vane_mv(uint16_t *mv);

/* What the bench screen shows, read from the module's own state. speed: the last 3 s of pulses; gust:
   the largest 3 s so far in this window; both in cm/s. vane_mv: the latest vane reading; point: its
   position 0 (N) to 15 clockwise in 22.5 degree steps, or -1 out of the table (or none yet). bins: the
   last 30 s of 250 ms pulse counts (each saturated at 255), oldest first; nbins of them. */
#define WIND_LIVE_BINS 120U
typedef struct { uint16_t speed_cms, gust_cms; uint16_t vane_mv; int8_t point; uint8_t bins[WIND_LIVE_BINS]; uint8_t nbins; } wind_live_t;
int mod_wind_live(wind_live_t *w);   /* 1 always; read-only */

void mod_wind_init(uint32_t boot_id, uint32_t now_ms);
void mod_wind_tick(uint32_t now_ms);
int mod_wind_probe(uint16_t *seq);
void mod_wind_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_wind_latch(uint16_t token, uint32_t now_ms);
void mod_wind_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]);
#endif
