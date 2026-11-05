/* The rain module (mod_rain.h). The interrupt only counts, and notes when the counted tip came (that
 * first, then the count); the main loop reads both 32-bit words, each in one access on the Cortex-M4.
 * The tick keeps the per-minute history (mod_rain_history): the tips since the last tick go into the
 * ring's current minute, after it rolls the ring on by the whole minutes gone (all of it cleared after an
 * hour or more without a tick).
 * The link (build-progression record M7): the reed is open at rest, so a link probe that reads low
 * BOARD_LINK_LOWS times in a row with no tip since is an open link between the jack-end pull-up and
 * the MCU: the slot's quality is fault and #status says meter_link=rain-open, while the gauge is on.
 * An open beyond the pull-up (the cable, the jack contacts) reads like a dry day: not detectable. */
#include "mod_rain.h"
#include <string.h>
#include "board_inputs.h"
#include "mod_mean.h"
#include "wsmp_local.h"

#define LOCKOUT_MS 100U
#define PROBE_PERIOD_MS 1000U
#define MINUTE_MS 60000U
#define AGE_MAX_MS (RAIN_AGE_MAX_S * 1000UL)

static volatile uint32_t tips, last_edge_ms, last_tip_ms;
static volatile int have_tip;
static int enabled;
static uint16_t probe_seq;
static uint32_t next_probe_ms, boot;
static mean_win win;   /* the window header and the latch rule; it holds no means */
static uint8_t per_min[RAIN_HIST_MINUTES];   /* a ring; per_min[now_at] is this minute */
static unsigned now_at;
static uint32_t minute_ms;   /* when this minute started */
static uint32_t tips_seen;   /* the tips the ring has */
static uint32_t aged_tips;   /* the count when a tick found its last tip RAIN_AGE_MAX_S old (0: none) */

void mod_rain_init(uint32_t boot_id, int on, uint32_t now_ms)
{
  boot = boot_id;
  tips = 0; have_tip = 0; last_edge_ms = 0; last_tip_ms = 0;
  memset(per_min, 0, sizeof per_min);
  now_at = 0; minute_ms = now_ms; tips_seen = 0; aged_tips = 0;
  enabled = on;
  probe_seq = 0; next_probe_ms = now_ms;
  mean_reset(&win, now_ms);
}

void mod_rain_set_enabled(int on) { enabled = on; }
uint32_t mod_rain_tips_since_boot(void) { return tips; }

void mod_rain_tip(uint32_t now_ms)
{
  /* The lockout runs from the last edge, counted or not: a contact that chatters (on closing or on a
     slow release) counts once, however long it chatters with gaps under 100 ms. */
  int bounce = have_tip && now_ms - last_edge_ms < LOCKOUT_MS;
  have_tip = 1;
  last_edge_ms = now_ms;
  if (!bounce) { last_tip_ms = now_ms; tips++; }
}

/* The ring on to now_ms's minute. A now_ms before this minute's start (an older reading of the clock)
   moves nothing. */
static void roll(uint32_t now_ms)
{
  uint32_t since = now_ms - minute_ms;
  if ((int32_t)since < 0) return;
  uint32_t gone = since / MINUTE_MS;
  if (gone >= RAIN_HIST_MINUTES) memset(per_min, 0, sizeof per_min);
  else
    for (uint32_t i = 0; i < gone; i++)   /* bound: gone < RAIN_HIST_MINUTES */
    {
      now_at = (now_at + 1U) % RAIN_HIST_MINUTES;
      per_min[now_at] = 0;
    }
  minute_ms += gone * MINUTE_MS;   /* gone x MINUTE_MS <= since: no overflow */
}

/* The tips since the last tick into this minute; and a last tip RAIN_AGE_MAX_S old stops ageing (read
   after the count: a tip in between is a newer last_tip_ms, too young to be aged). */
static void take_tips(uint32_t now_ms)
{
  uint32_t t = tips, add = t - tips_seen;
  tips_seen = t;
  uint32_t sum = per_min[now_at] + (add > UINT8_MAX ? UINT8_MAX : add);
  per_min[now_at] = (uint8_t)(sum > UINT8_MAX ? UINT8_MAX : sum);
  if (t != 0 && now_ms - last_tip_ms >= AGE_MAX_MS) aged_tips = t;
}

/* The setting is probed once a second, so the station debounces it like any presence (WSMP-P2). */
void mod_rain_tick(uint32_t now_ms)
{
  roll(now_ms);
  take_tips(now_ms);
  if ((int32_t)(now_ms - next_probe_ms) < 0) return;
  next_probe_ms = now_ms + PROBE_PERIOD_MS;
  probe_seq++;
}

/* The count first: a tip after it is a newer last_tip_ms, an age of about 0. */
void mod_rain_history(uint32_t now_ms, rain_hist_t *out)
{
  uint32_t t = tips, age = (now_ms - last_tip_ms) / 1000U;
  out->tips = t;
  out->last_age_s = t == 0 ? RAIN_AGE_NONE : t == aged_tips || age > RAIN_AGE_MAX_S ? RAIN_AGE_MAX_S : age;
  for (unsigned i = 0; i < RAIN_HIST_MINUTES; i++)   /* oldest first: the minute after this one's slot */
    out->per_min[i] = per_min[(now_at + 1U + i) % RAIN_HIST_MINUTES];
}

int mod_rain_probe(uint16_t *seq)
{
  *seq = probe_seq;
  return enabled;
}

static void desc_block(uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  const wsmp_desc d = { .quantity = WSMP_Q_RAIN_TIPS, .unit = WSMP_U_TIP, .scale = 0, .width = 2, .kind = WSMP_K_COUNTER };
  wsmp_pack_desc(&d, 1, desc);
}

void mod_rain_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  desc_block(desc);
  local_pack_identity(P_RAIN, WSMP_T_RAIN, 1, boot, desc, id);
}

void mod_rain_latch(uint16_t token, uint32_t now_ms)
{
  uint8_t desc[WSMP_DESC_BLOCK_LEN];
  wsmp_snapshot snap;
  desc_block(desc);
  if (!mean_close(&win, token, now_ms, boot, desc, 0, &snap)) return;
  uint8_t q = mod_rain_link() == METER_LINK_RAIN_OPEN ? (uint8_t)WSMP_QUAL_FAULT : mean_quality(&snap, enabled ? 1U : 0U);
  snap.slot[0] = (wsmp_slot){ .value = tips, .count = (uint16_t)(enabled ? 1 : 0), .quality = q };
  mean_store(&win, &snap);
}

enum meter_link mod_rain_link(void)
{
  int open = board_link_lows(BOARD_LINK_RAIN) >= BOARD_LINK_LOWS && !board_link_edge_seen(BOARD_LINK_RAIN);
  return enabled && open ? METER_LINK_RAIN_OPEN : METER_LINK_OK;
}

void mod_rain_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, win.frozen, WSMP_SNAPSHOT_LEN); }
