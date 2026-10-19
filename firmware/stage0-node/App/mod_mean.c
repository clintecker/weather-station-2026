/* The minute window of a mean-type local module (mod_mean.h). */
#include "mod_mean.h"
#include <string.h>
#include "wsmp_local.h"

void mean_reset(mean_win *w, uint32_t now_ms)
{
  memset(w, 0, sizeof *w);
  w->start_ms = now_ms;   /* the board clock does not start at 0 after a warm reset */
}

void mean_add(mean_win *w, const int32_t v[MEAN_CHANNELS])
{
  if (w->n == UINT8_MAX) return;   /* 255 samples is far above a window's 4 (or 60 for the vane) */
  for (unsigned i = 0; i < MEAN_CHANNELS; i++) w->sum[i] += v[i];
  w->n++;
}

/* floor((2 sum + n) / (2 n)): the mean rounded half up, also for a negative sum. */
static int32_t mean_of(int32_t sum, uint8_t n)
{
  int64_t num = 2 * (int64_t)sum + n, den = 2 * (int64_t)n;
  int64_t q = num / den;
  if (num % den != 0 && num < 0) q--;
  return (int32_t)q;
}

static uint8_t quality(const mean_win *w, uint32_t window_ms)
{
  uint32_t period = w->period_ms ? w->period_ms : WSMP_SAMPLE_MS;
  if (w->n == 0) return WSMP_QUAL_MISSING;
  if (!w->latched || w->n < window_ms / period) return WSMP_QUAL_PARTIAL;
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
  uint8_t q = quality(w, window_ms);
  for (unsigned i = 0; i < channels && i < MEAN_CHANNELS; i++)
    snap->slot[i] = w->n ? (wsmp_slot){ .value = (uint32_t)mean_of(w->sum[i], w->n), .count = w->n, .quality = q }
                         : (wsmp_slot){ .quality = WSMP_QUAL_MISSING };
  memset(w->sum, 0, sizeof w->sum);
  w->n = 0;
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
