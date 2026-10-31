/* The wind module (mod_wind.h).
 *   Cups: the LPTIM1 counter runs on the reed pulses. Its clock is the pulses, so a read can tear: the
 *   counter is read until two reads agree (RM0453, LPTIM), at most three times. The wrapped difference
 *   from the previous read is that tick's bin. The gust is the largest sum of 12 consecutive bins (3 s)
 *   in the window, times 0.66698 m/s per Hz (registry factor), divided by 3 s.
 *   Vane: 16 positions of the SEN-15901 resistor network with a 10 kOhm pull-up to 3.3 V, decoded to
 *   the nearest position. A reading above 3.2 V is an open vane: absent (WSMP-P1). Each sample adds
 *   100 sin and 100 cos of its direction to the sums (WSMP kinds 8 and 9, scale -2). Each position has
 *   a tolerance band: its resistance +-VANE_TOL_PCT, then +-VANE_ADC_MV (an assumed bench starting
 *   value: the datasheet gives no tolerance). A reading outside every band stays out of the sums and
 *   makes the vane slots suspect; it also flags the wind cable or jack (#status
 *   meter_link=vane-out-of-table), the open vane pair at the pull-up rail included.
 *   The cups link (build-progression record M7, rows R-6 and R-16): BOARD_LINK_LOWS probes in a row
 *   that read the link low with no cup pulse since are suspect only (the rotor can stop with the
 *   magnet holding the reed closed in calm air); they become an open link (fault) when, while they
 *   last, an in-table vane reading moves to another position (wind but no cup pulse), or after 24 h of
 *   such probes. Cups and gust slots take the verdict as their quality. */
#include "mod_wind.h"
#include <string.h>
#include "board_inputs.h"
#include "mod_mean.h"
#include "wsmp_local.h"

#define POSITIONS 16U
#define GUST_BINS 12U                 /* 3 s of 250 ms bins */
#define GUST_S 3U
#define CENTI_UMS 10000U              /* um/s in 0.01 m/s */
#define VANE_PERIOD_MS 1000U
#define VANE_OPEN_MV 3200U
#define PULL_UP_OHM 10000UL
#define SUPPLY_MV 3300UL
#define COUNTER_READS 3U
#define CHANNELS 4U
#define VANE_TOL_PCT 5UL              /* the band: the network's resistance +-5 % ... */
#define VANE_ADC_MV 10U               /* ... then +-10 mV for the ADC */
#define CUPS_LOWS_DAY (86400000UL / BOARD_LINK_PROBE_MS + 1U)   /* probes in a row spanning 24 h */
#define VANE_MV(r) ((uint16_t)((SUPPLY_MV * (r) + ((r) + PULL_UP_OHM) / 2U) / ((r) + PULL_UP_OHM)))

/* SEN-15901 datasheet: the resistance at each position, clockwise from north in 22.5 degree steps. */
#define VANE_OHMS(X) X(33000UL) X(6570UL) X(8200UL) X(891UL) X(1000UL) X(688UL) X(2200UL) X(1410UL) X(3900UL) \
                     X(3140UL) X(16000UL) X(14120UL) X(120000UL) X(42120UL) X(64900UL) X(21880UL)
#define VANE_NOMINAL(r) VANE_MV(r),
#define VANE_LOW(r) (uint16_t)(VANE_MV((r) * (100UL - VANE_TOL_PCT) / 100UL) - VANE_ADC_MV),
#define VANE_HIGH(r) (uint16_t)(VANE_MV((r) * (100UL + VANE_TOL_PCT) / 100UL) + VANE_ADC_MV),
static const uint16_t vane_mv[POSITIONS] = { VANE_OHMS(VANE_NOMINAL) };
static const uint16_t vane_low[POSITIONS] = { VANE_OHMS(VANE_LOW) };
static const uint16_t vane_high[POSITIONS] = { VANE_OHMS(VANE_HIGH) };
/* 100 sin and 100 cos of each position, rounded to the nearest integer. */
static const int8_t east[POSITIONS] = { 0, 38, 71, 92, 100, 92, 71, 38, 0, -38, -71, -92, -100, -92, -71, -38 };
static const int8_t north[POSITIONS] = { 100, 92, 71, 38, 0, -38, -71, -92, -100, -92, -71, -38, 0, 38, 71, 92 };

typedef struct {
  uint16_t last_raw;
  int have_raw;
  uint32_t total, ring_sum, gust_max, ticks, ring_count, next_vane_ms;
  uint16_t ring[GUST_BINS];
  unsigned ring_pos;
  int32_t east_sum, north_sum;
  uint32_t vane_n;
  int probe;
  uint16_t probe_seq;
  uint8_t have_pos, last_pos;   /* the last in-table position */
  uint8_t vane_out;             /* the last vane reading was outside every band */
  uint8_t cups_open;            /* the vane moved while the cups link was suspect */
  uint32_t vane_out_n;          /* out-of-table readings in the window */
  mean_win win;   /* the window header and the latch rule; it holds no means */
} wind_t;

static wind_t wd;
static uint32_t boot;

void mod_wind_init(uint32_t boot_id, uint32_t now_ms)
{
  boot = boot_id;
  memset(&wd, 0, sizeof wd);
  mean_reset(&wd.win, now_ms);
  wd.next_vane_ms = now_ms;
}

/* Two reads that agree, of at most three. Returns 0 if the counter moved between every read. */
static int read_counter(uint16_t *raw)
{
  uint16_t prev = board_pulse_count();
  for (unsigned i = 1; i < COUNTER_READS; i++)
  {
    uint16_t now = board_pulse_count();
    if (now == prev) { *raw = now; return 1; }
    prev = now;
  }
  return 0;
}

static void bin(uint16_t pulses)
{
  wd.ring_sum = wd.ring_sum - wd.ring[wd.ring_pos] + pulses;
  wd.ring[wd.ring_pos] = pulses;
  wd.ring_pos = (wd.ring_pos + 1U) % GUST_BINS;
  if (wd.ring_count < GUST_BINS) wd.ring_count++;
  if (wd.ring_count == GUST_BINS && wd.ring_sum > wd.gust_max) wd.gust_max = wd.ring_sum;
}

static void cups(void)
{
  uint16_t raw;
  wd.ticks++;
  if (!read_counter(&raw)) { bin(0); return; }   /* the next agreed read counts these pulses */
  uint16_t pulses = wd.have_raw ? (uint16_t)(raw - wd.last_raw) : 0U;   /* wraps at 16 bits */
  wd.last_raw = raw;
  wd.have_raw = 1;
  wd.total += pulses;
  bin(pulses);
}

static unsigned position_of(uint16_t mv)
{
  unsigned best = 0;
  for (unsigned i = 1; i < POSITIONS; i++)
  {
    unsigned d = (unsigned)(mv > vane_mv[i] ? mv - vane_mv[i] : vane_mv[i] - mv);
    unsigned b = (unsigned)(mv > vane_mv[best] ? mv - vane_mv[best] : vane_mv[best] - mv);
    if (d < b) best = i;
  }
  return best;
}

static int in_table(uint16_t mv)
{
  for (unsigned i = 0; i < POSITIONS; i++)
  {
    if (mv >= vane_low[i] && mv <= vane_high[i]) return 1;
  }
  return 0;
}

/* The cups link verdict (M7): ok, suspect, or open. */
static enum meter_link cups_verdict(void)
{
  unsigned lows = board_link_lows(BOARD_LINK_CUPS);
  if (lows < BOARD_LINK_LOWS || board_link_edge_seen(BOARD_LINK_CUPS)) return METER_LINK_OK;
  return wd.cups_open || lows >= CUPS_LOWS_DAY ? METER_LINK_CUPS_OPEN : METER_LINK_CUPS_SUSPECT;
}

/* A vane move while the cups link is suspect is wind with no cup pulse: the link is open. The mark
   lasts as long as the suspect run. */
static void cups_link(int moved)
{
  if (cups_verdict() == METER_LINK_OK) wd.cups_open = 0;
  else if (moved) wd.cups_open = 1;
}

/* One in-table sample at position p into the sums; 1 if the vane moved since the last one. */
static int vane_sample(unsigned p)
{
  int moved = wd.have_pos && p != wd.last_pos;
  wd.have_pos = 1;
  wd.last_pos = (uint8_t)p;
  wd.east_sum += east[p];
  wd.north_sum += north[p];
  wd.vane_n++;
  return moved;
}

static void vane(void)
{
  uint16_t mv;
  int moved = 0;
  if (!board_vane_mv(&mv)) return;
  wd.probe_seq++;
  wd.probe = mv <= VANE_OPEN_MV;
  wd.vane_out = (uint8_t)!in_table(mv);
  if (wd.probe && wd.vane_out) wd.vane_out_n++;
  else if (wd.probe) moved = vane_sample(position_of(mv));
  cups_link(moved);
}

enum meter_link mod_wind_link(void)
{
  enum meter_link v = cups_verdict();
  if (v == METER_LINK_CUPS_OPEN) return v;
  return wd.vane_out ? METER_LINK_VANE_OUT : v;
}

void mod_wind_tick(uint32_t now_ms)
{
  cups();
  if ((int32_t)(now_ms - wd.next_vane_ms) < 0) return;
  wd.next_vane_ms = now_ms + VANE_PERIOD_MS;
  vane();
}

int mod_wind_probe(uint16_t *seq)
{
  *seq = wd.probe_seq;
  return wd.probe;
}

static void desc_block(uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  const wsmp_desc d[CHANNELS] = {
    { .quantity = WSMP_Q_ANEMOMETER_PULSES, .unit = WSMP_U_PULSE, .scale = 0, .width = 2, .kind = WSMP_K_COUNTER },
    { .quantity = WSMP_Q_WIND_GUST, .unit = WSMP_U_M_PER_S, .scale = -2, .width = 2, .kind = WSMP_K_GUST },
    { .quantity = WSMP_Q_WIND_FROM_DIRECTION, .unit = WSMP_U_DEG, .scale = -2, .width = 2, .is_signed = 1, .kind = WSMP_K_VEC_EAST },
    { .quantity = WSMP_Q_WIND_FROM_DIRECTION, .unit = WSMP_U_DEG, .scale = -2, .width = 2, .is_signed = 1, .kind = WSMP_K_VEC_NORTH } };
  wsmp_pack_desc(d, CHANNELS, desc);
}

void mod_wind_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  desc_block(desc);
  local_pack_identity(P_WIND, WSMP_T_WIND, CHANNELS, boot, desc, id);
}

/* A slot's quality under a link verdict: fault for an open link; suspect over good or partial
   for a suspect cups link or an out-of-table vane; otherwise as it was. */
static uint8_t link_quality(uint8_t q, enum meter_link v)
{
  if (v == METER_LINK_CUPS_OPEN) return WSMP_QUAL_FAULT;
  if (v != METER_LINK_OK && (q == WSMP_QUAL_GOOD || q == WSMP_QUAL_PARTIAL)) return WSMP_QUAL_SUSPECT;
  return q;
}

static uint8_t vane_quality(const wsmp_snapshot *snap)
{
  if (wd.vane_n == 0) return WSMP_QUAL_MISSING;
  if (wd.vane_out_n) return WSMP_QUAL_SUSPECT;
  if (wd.vane_n < snap->window_ms / VANE_PERIOD_MS) return WSMP_QUAL_PARTIAL;
  return mean_quality(snap, wd.vane_n);
}

void mod_wind_latch(uint16_t token, uint32_t now_ms)
{
  uint8_t desc[WSMP_DESC_BLOCK_LEN];
  wsmp_snapshot snap;
  desc_block(desc);
  if (!mean_close(&wd.win, token, now_ms, boot, desc, 0, &snap)) return;
  uint8_t q = link_quality(mean_quality(&snap, wd.ticks), cups_verdict());
  uint32_t gust = (uint32_t)(((uint64_t)wd.gust_max * WSMP_WIND_UMS_PER_HZ * 2U + GUST_S * CENTI_UMS) / (2U * GUST_S * CENTI_UMS));
  uint8_t qv = vane_quality(&snap);
  snap.slot[0] = (wsmp_slot){ .value = wd.total, .count = (uint16_t)wd.ticks, .quality = q };
  snap.slot[1] = (wsmp_slot){ .value = gust, .count = (uint16_t)wd.ticks,
                              .quality = wd.ring_count < GUST_BINS ? (uint8_t)WSMP_QUAL_MISSING : q };
  snap.slot[2] = (wsmp_slot){ .value = (uint32_t)wd.east_sum, .count = (uint16_t)wd.vane_n, .quality = qv };
  snap.slot[3] = (wsmp_slot){ .value = (uint32_t)wd.north_sum, .count = (uint16_t)wd.vane_n, .quality = qv };
  mean_store(&wd.win, &snap);
  wd.gust_max = 0; wd.ticks = 0; wd.east_sum = 0; wd.north_sum = 0; wd.vane_n = 0; wd.vane_out_n = 0;
}

void mod_wind_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, wd.win.frozen, WSMP_SNAPSHOT_LEN); }
