/* The minute window of a mean-type local module (mod_mean.h). */
#include "mod_mean.h"
#include <string.h>
#include "ws_round.h"
#include "wsmp_local.h"

void mean_reset(mean_win *w, uint32_t now_ms)
{
  memset(w, 0, sizeof *w);
  w->start_ms = now_ms;   /* the board clock does not start at 0 after a warm reset */
}

int mean_due(uint32_t *next_ms, uint32_t now_ms, uint32_t period_ms)
{
  if ((int32_t)(now_ms - *next_ms) < 0) return 0;
  *next_ms += period_ms;
  if ((int32_t)(now_ms - *next_ms) >= 0) *next_ms = now_ms + period_ms;   /* fell behind: resync */
  return 1;
}

void mean_add_q(mean_win *w, const int32_t v[MEAN_CHANNELS], const uint8_t q[MEAN_CHANNELS])
{
  for (unsigned i = 0; i < MEAN_CHANNELS; i++)
  {
    if (q[i] != WSMP_QUAL_GOOD) { w->suspect[i] = 1; continue; }
    if (w->n[i] == UINT8_MAX) continue;   /* 255 samples is far above a window's 4 (or 60 for the vane) */
    w->sum[i] += v[i];
    w->n[i]++;
  }
}

void mean_add(mean_win *w, const int32_t v[MEAN_CHANNELS])
{
  static const uint8_t good[MEAN_CHANNELS] = { WSMP_QUAL_GOOD, WSMP_QUAL_GOOD };
  mean_add_q(w, v, good);
}

/* The mean rounded half up, also for a negative sum: the station's one rounding helper (ws_round.h).
   |sum / n| <= |sum|, so the result fits int32. */
static int32_t mean_of(int32_t sum, uint8_t n) { return (int32_t)ws_div_round(sum, n); }

/* A channel's quality: missing without a sample in its sum, else suspect if a sample was (over
   partial), else partial in the first window or short of samples, else good. */
static uint8_t quality(const mean_win *w, unsigned ch, uint32_t window_ms)
{
  uint32_t period = w->period_ms ? w->period_ms : WSMP_SAMPLE_MS;
  if (w->n[ch] == 0) return WSMP_QUAL_MISSING;
  if (w->suspect[ch]) return WSMP_QUAL_SUSPECT;
  if (!w->latched || w->n[ch] < window_ms / period) return WSMP_QUAL_PARTIAL;
  return WSMP_QUAL_GOOD;
}

uint8_t mean_quality(const wsmp_snapshot *snap, unsigned samples)
{
  if (samples == 0) return WSMP_QUAL_MISSING;
  return (snap->flags & WSMP_FLAG_FIRST_WINDOW) ? WSMP_QUAL_PARTIAL : WSMP_QUAL_GOOD;
}

static void header(const mean_win *w, wsmp_snapshot *snap, uint16_t token, uint32_t window_ms, uint32_t boot_id,
                   const uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  memset(snap, 0, sizeof *snap);
  snap->token = token;
  snap->boot16 = (uint16_t)boot_id;
  snap->window_ms = window_ms > UINT16_MAX ? UINT16_MAX : (uint16_t)window_ms;
  /* Long: a length its u16 field cannot hold (WSMP section 6). That also covers WSMP-T3, no latch
     for more than 90 s. */
  int is_long = window_ms > UINT16_MAX;
  snap->flags = (uint8_t)((w->latched ? 0U : WSMP_FLAG_FIRST_WINDOW) | (is_long ? WSMP_FLAG_LONG_WINDOW : 0U));
  snap->desc_tag = (uint8_t)wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN);
}

int mean_close(mean_win *w, uint16_t token, uint32_t now_ms, uint32_t boot_id, const uint8_t desc[WSMP_DESC_BLOCK_LEN],
               unsigned channels, wsmp_snapshot *snap)
{
  if (w->latched && token == w->last_token) return 0;   /* WSMP-L3: a retry */
  uint32_t window_ms = now_ms - w->start_ms;
  header(w, snap, token, window_ms, boot_id, desc);
  for (unsigned i = 0; i < channels && i < MEAN_CHANNELS; i++)
    snap->slot[i] = w->n[i] ? (wsmp_slot){ .value = (uint32_t)mean_of(w->sum[i], w->n[i]), .count = w->n[i],
                                           .quality = quality(w, i, window_ms) }
                            : (wsmp_slot){ .quality = WSMP_QUAL_MISSING };
  memset(w->sum, 0, sizeof w->sum);
  memset(w->n, 0, sizeof w->n);
  memset(w->suspect, 0, sizeof w->suspect);
  w->start_ms = now_ms;
  w->last_token = token;
  w->latched = 1;
  return 1;
}

void mean_store(mean_win *w, const wsmp_snapshot *snap) { wsmp_pack_snapshot(snap, w->frozen); }

void mean_latch(mean_win *w, uint16_t token, uint32_t now_ms, uint32_t boot_id, const uint8_t desc[WSMP_DESC_BLOCK_LEN],
                unsigned channels)
{
  wsmp_snapshot snap;
  if (mean_close(w, token, now_ms, boot_id, desc, channels, &snap)) mean_store(w, &snap);
}
