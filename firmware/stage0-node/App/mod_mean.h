#ifndef MOD_MEAN_H
#define MOD_MEAN_H
/* The minute window of a local module whose channels are means of its samples (WSMP kinds "mean"):
 * the sums, the latch with its retry rule (WSMP-L1 to L3), the quality of the window (WSMP section 9)
 * and the frozen snapshot. The temperature, humidity, pressure and UVA modules use it. Each channel
 * keeps its own sample count and suspect flag (sensor module ports design, section 6.9): a suspect
 * sample stays out of its channel's sum and makes the channel suspect, and leaves the other channel. */
#include <stdint.h>
#include "wsmp.h"

#define MEAN_CHANNELS 2U
typedef struct {
  int32_t sum[MEAN_CHANNELS];
  uint8_t n[MEAN_CHANNELS], suspect[MEAN_CHANNELS], latched;
  uint16_t last_token;
  uint32_t start_ms;
  uint32_t period_ms;   /* the sample period behind the quality: 0 means WSMP_SAMPLE_MS */
  uint8_t frozen[WSMP_SNAPSHOT_LEN];
} mean_win;

/* Empty, never latched, open from now_ms; also the bind of a driver to a new module (section 6.7). Every module also starts its schedule at now_ms: the clock
   is compared signed, and after a warm reset it can be anywhere in its 49-day range. */
void mean_reset(mean_win *w, uint32_t now_ms);
/* 1 when a periodic sample is due at now_ms, and moves *next_ms one period on (or to a period after
   now_ms, when the module fell behind). The comparison is signed, so the 49-day clock wrap is safe. */
int mean_due(uint32_t *next_ms, uint32_t now_ms, uint32_t period_ms);
void mean_add(mean_win *w, const int32_t v[MEAN_CHANNELS]);   /* one valid sample of every channel */
/* One sample of every channel with its quality from wsmp_cal_crop: a good value goes into its
   channel's sum, a suspect one only flags the channel. */
void mean_add_q(mean_win *w, const int32_t v[MEAN_CHANNELS], const uint8_t q[MEAN_CHANNELS]);
/* WSMP-L1 to L3. A retry (the last token again) changes nothing. Otherwise the window freezes into
   the snapshot (token, boot ID, length, flags, the channel means and their quality) and the next
   window starts at now_ms. desc is the module's descriptor block (for the descriptor tag). */
void mean_latch(mean_win *w, uint16_t token, uint32_t now_ms, uint32_t boot_id, const uint8_t desc[WSMP_DESC_BLOCK_LEN],
                unsigned channels);
/* The two halves of mean_latch, for a module with more slots than means: mean_close returns 0 for a
   retry; otherwise it fills snap (header, the mean slots) and starts the next window. The module
   adds its other slots, then mean_store packs snap as the frozen snapshot. */
int mean_close(mean_win *w, uint16_t token, uint32_t now_ms, uint32_t boot_id, const uint8_t desc[WSMP_DESC_BLOCK_LEN],
               unsigned channels, wsmp_snapshot *snap);
void mean_store(mean_win *w, const wsmp_snapshot *snap);
/* The quality of a slot that is not a mean, for the window just closed: good, partial in the first
   window, missing without a sample. */
uint8_t mean_quality(const wsmp_snapshot *snap, unsigned samples);
#endif
