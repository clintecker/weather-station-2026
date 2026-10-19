/* The rain module (mod_rain.h). The interrupt only counts; the main loop reads the 32-bit count,
 * which the Cortex-M4 reads in one access. */
#include "mod_rain.h"
#include <string.h>
#include "mod_mean.h"
#include "wsmp_local.h"

#define LOCKOUT_MS 100U
#define PROBE_PERIOD_MS 1000U

static volatile uint32_t tips, last_tip_ms;
static volatile int have_tip;
static int enabled;
static uint16_t probe_seq;
static uint32_t next_probe_ms, boot;
static mean_win win;   /* the window header and the latch rule; it holds no means */

void mod_rain_init(uint32_t boot_id, int on, uint32_t now_ms)
{
  boot = boot_id;
  tips = 0; have_tip = 0; last_tip_ms = 0;
  enabled = on;
  probe_seq = 0; next_probe_ms = 0;
  mean_reset(&win, now_ms);
}

void mod_rain_set_enabled(int on) { enabled = on; }

void mod_rain_tip(uint32_t now_ms)
{
  if (have_tip && now_ms - last_tip_ms < LOCKOUT_MS) return;   /* the bounce of the counted closure */
  have_tip = 1;
  last_tip_ms = now_ms;
  tips++;
}

/* The setting is probed once a second, so the station debounces it like any presence (WSMP-P2). */
void mod_rain_tick(uint32_t now_ms)
{
  if ((int32_t)(now_ms - next_probe_ms) < 0) return;
  next_probe_ms = now_ms + PROBE_PERIOD_MS;
  probe_seq++;
}

int mod_rain_probe(uint16_t *seq)
{
  *seq = probe_seq;
  return enabled;
}

void mod_rain_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  const wsmp_desc d = { .quantity = WSMP_Q_RAIN_TIPS, .unit = WSMP_U_TIP, .scale = 0, .width = 2, .kind = WSMP_K_COUNTER };
  wsmp_pack_desc(&d, 1, desc);
  wsmp_identity ident = { .type = WSMP_T_RAIN, .schema = 1, .channels = 1, .fw_major = 1, .fw_minor = 0,
                          .serial = WSMP_LOCAL_SERIAL(P_RAIN, WSMP_T_RAIN), .boot_id = boot,
                          .desc_digest = wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN) };
  wsmp_pack_identity(&ident, id);
}

void mod_rain_latch(uint16_t token, uint32_t now_ms)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  wsmp_snapshot snap;
  mod_rain_identity(id, desc);
  if (!mean_close(&win, token, now_ms, boot, desc, 0, &snap)) return;
  snap.slot[0] = (wsmp_slot){ .value = tips, .count = (uint16_t)(enabled ? 1 : 0),
                              .quality = mean_quality(&snap, enabled ? 1U : 0U) };
  mean_store(&win, &snap);
}

void mod_rain_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, win.frozen, WSMP_SNAPSHOT_LEN); }
