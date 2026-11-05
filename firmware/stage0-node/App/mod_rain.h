#ifndef MOD_RAIN_H
#define MOD_RAIN_H
/* The rain module (WSMP module type 7): the SEN-15901 tipping bucket on the PB4 interrupt (EXTI4).
 * A bucket tip closes a reed switch once; a closure within 100 ms of the counted one is its bounce.
 * The gauge is a bare switch, so the station cannot see it: the stored setting (store_rain_enabled)
 * is its presence (WSMP-P1). The channel is the tip counter since boot. */
#include <stdint.h>
#include "wsmp.h"

void mod_rain_init(uint32_t boot_id, int enabled, uint32_t now_ms);
void mod_rain_set_enabled(int on);
uint32_t mod_rain_tips_since_boot(void);   /* the counted tips, as the window reports them; read-only */
void mod_rain_tip(uint32_t now_ms);   /* from the EXTI4 interrupt (App/board_inputs.c) */

/* The bench screen's rain history, read from the module's own state (like mod_*_live; read-only, main
   loop). tips: the counter since boot. last_age_s: seconds since the last counted tip at now_ms, at most
   RAIN_AGE_MAX_S (an older tip reads as that: the ms clock wraps in 49 days); RAIN_AGE_NONE if none since
   boot. per_min: the tips of each of the last RAIN_HIST_MINUTES minutes, oldest first, each saturated at
   255; the last is this minute so far, as of the last mod_rain_tick. The minutes start a whole number of
   minutes after mod_rain_init; a tick counts the tips since the one before into the minute it falls in. */
#define RAIN_HIST_MINUTES 60U
#define RAIN_AGE_NONE UINT32_MAX
#define RAIN_AGE_MAX_S (99UL * 3600UL)
typedef struct { uint32_t tips, last_age_s; uint8_t per_min[RAIN_HIST_MINUTES]; } rain_hist_t;
void mod_rain_history(uint32_t now_ms, rain_hist_t *out);
void mod_rain_tick(uint32_t now_ms);
int mod_rain_probe(uint16_t *seq);
void mod_rain_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_rain_latch(uint16_t token, uint32_t now_ms);
void mod_rain_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]);
#endif
