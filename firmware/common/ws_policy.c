/* GENERATED from ws_policy.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/common/ws_policy.lit.md (tests/test_tangle.py checks this file). */
#define WS_CHECK_FILE 11
#include "ws_policy.h"
#include "stage0.h"
#include "ws_obs.h"
#include "ws_check.h"
#include <limits.h>

/* Per energy state, in WS_ENERGY_* order: backlog frames and radio time per minute. */
static const char *const energy_name[] = { "surplus", "normal", "conserve", "critical" };
static const uint8_t backlog_limit[] = { WS_BACKLOG_MAX, 5, 0, 0 };
static const uint16_t airtime_cap_ms[] = { 15000, 5000, 2000, 0 };
#define ENERGY_STATES (sizeof energy_name / sizeof energy_name[0])
_Static_assert(ENERGY_STATES == WS_ENERGY_CRITICAL + 1 && sizeof backlog_limit == ENERGY_STATES &&
               sizeof airtime_cap_ms / sizeof airtime_cap_ms[0] == ENERGY_STATES, "one entry per energy state");
#define CONSERVE_INTERVAL_S 300U   /* spec rule R02: CONSERVE reports every 5 minutes */
static const uint16_t probe_interval_s[] = { 120, 240, 480, 900 };
#define PROBE_STEPS (sizeof probe_interval_s / sizeof probe_interval_s[0])

const char *ws_energy_name(int energy)
{
 return energy >= 0 && energy < (int)ENERGY_STATES ? energy_name[energy] : "?";
}

/* Semtech time on air (SX1261/2 datasheet section 6.1.4, AN1200.13), explicit header, CRC on:
 *   T_sym = 2^SF / BW, preamble = (n_preamble + 4.25) T_sym,
 *   payload = 8 + max(ceil((8 PL - 4 SF + 28 + 16 CRC) / (4 (SF - 2 DE))), 0) (CR + 4) symbols.
 * The code counts in quarter symbols, so the 4.25 stays an integer. */
#define LORA_SF_MIN 7U
#define LORA_SF_MAX 12U
#define LORA_BW_MIN_HZ 7800U
#define LORA_CR_MAX 4U              /* 4/8 */
#define LDRO_SYMBOL_US 16000U       /* low data rate optimisation is on above this symbol time */
#define HEADER_FIXED_BITS 28        /* the formula's +28 */
#define CRC_BITS 16
#define PAYLOAD_FIXED_SYMBOLS 8U
#define SYNC_QUARTERS 17U           /* 4.25 symbols of sync word and start of frame */
#define QUARTERS 4U
#define US_PER_MS 1000U
#define US_PER_S 1000000UL
#define AIRTIME_UNKNOWN_MS 60000U   /* a whole minute: room for the live reading only */
uint32_t ws_lora_airtime_ms(uint32_t payload, uint32_t sf, uint32_t bw_hz, uint32_t preamble, uint32_t cr)
{
 /* The arguments are radio_cfg.h's constants. Outside the formula's range, the function returns
    the cautious AIRTIME_UNKNOWN_MS. It never divides by zero. */
 if (!WS_CHECK(sf >= LORA_SF_MIN && sf <= LORA_SF_MAX && bw_hz >= LORA_BW_MIN_HZ && cr >= 1 && cr <= LORA_CR_MAX))
  return AIRTIME_UNKNOWN_MS;
 uint32_t symbol_us_x_bw = US_PER_S << sf;                           /* T_sym in us, times BW */
 uint32_t de = symbol_us_x_bw / bw_hz > LDRO_SYMBOL_US ? 1 : 0;
 int32_t num = CHAR_BIT * (int32_t)payload - 4 * (int32_t)sf + HEADER_FIXED_BITS + CRC_BITS;
 int32_t den = 4 * ((int32_t)sf - 2 * (int32_t)de);
 int32_t blocks = num > 0 ? (num + den - 1) / den : 0;
 uint32_t quarters = (preamble * QUARTERS + SYNC_QUARTERS) + QUARTERS * (PAYLOAD_FIXED_SYMBOLS + (uint32_t)blocks * (cr + 4));
 return (uint32_t)(((uint64_t)quarters * symbol_us_x_bw / bw_hz) / (QUARTERS * US_PER_MS)) + 1;
}

int ws_link_minute(ws_link *l, int answered, uint32_t sent_s)
{
 if (answered) {
  int was_probing = l->probing;
  l->probing = 0; l->silent = 0; l->probe_step = 0;
  return was_probing ? WS_LINK_RELINKED : WS_LINK_SAME;
 }
 l->silent++;
 if (!l->probing && l->silent < WS_LINK_K_SILENT) return WS_LINK_SAME;
 int started = !l->probing;
 if (started) { l->probing = 1; l->probe_step = 0; }
 else if (l->probe_step + 1U < PROBE_STEPS) l->probe_step++;
 l->next_probe_s = sent_s + probe_interval_s[l->probe_step];
 return started ? WS_LINK_PROBING : WS_LINK_PROBE_MISSED;
}

uint32_t ws_link_probe_interval(const ws_link *l)
{
 /* ws_link_minute keeps probe_step below PROBE_STEPS. Past it, return the longest interval. */
 return probe_interval_s[WS_CHECK(l->probe_step < PROBE_STEPS) ? l->probe_step : PROBE_STEPS - 1U];
}

/* The energy and link gates: may this minute send at all? */
static int minute_may_send(int energy, const ws_link *l, uint32_t now_s, uint32_t last_send_s)
{
 if (energy < 0 || energy >= WS_ENERGY_CRITICAL) return 0;
 if (energy == WS_ENERGY_CONSERVE && now_s - last_send_s < CONSERVE_INTERVAL_S) return 0;
 return ws_link_may_send(energy, l->probing, (int32_t)(l->next_probe_s - now_s));
}

int ws_minute_backlog(int energy, const ws_link *l, uint32_t now_s, uint32_t last_send_s, uint32_t exchange_ms,
                      unsigned max_backlog)
{
 if (!minute_may_send(energy, l, now_s, last_send_s)) return -1;
 unsigned backlog = l->probing ? 0U : backlog_limit[energy];          /* a probe is the live reading */
 unsigned by_airtime = exchange_ms ? airtime_cap_ms[energy] / exchange_ms : 0;
 if (by_airtime == 0) by_airtime = 1;                                  /* the live reading always fits */
 if (backlog + 1 > by_airtime) backlog = by_airtime - 1;
 if (backlog > max_backlog) backlog = max_backlog;
 return (int)backlog;
}

static int same_record(const ws_strike *s, uint32_t epoch, uint32_t seq) { return s->n && s->epoch == epoch && s->seq == seq; }

int ws_strike_note(ws_strike *t, unsigned slots, uint32_t epoch, uint32_t seq, unsigned limit)
{
 unsigned use = slots, low = 0;
 if (!WS_CHECK(slots > 0)) return 0;   /* no table, so no strike */
 for (unsigned i = 0; i < slots; i++) {
  if (same_record(&t[i], epoch, seq)) { use = i; break; }
  if (t[i].n < t[low].n) low = i;
 }
 if (use == slots) { use = low; t[use].epoch = epoch; t[use].seq = seq; t[use].n = 0; }
 if (++t[use].n < limit) return 0;
 t[use].n = 0;
 return 1;
}

void ws_strike_forget(ws_strike *t, unsigned slots, uint32_t epoch, uint32_t seq)
{
 for (unsigned i = 0; i < slots; i++)
  if (same_record(&t[i], epoch, seq)) t[i].n = 0;
}

void ws_strike_targets(const uint8_t *replied, unsigned n, uint8_t *struck)
{
 int later = 0;   /* 1 when a frame after i got a reply */
 /* bound: n frames (the exchange's queue, MAX_QUEUE) */
 for (unsigned i = n; i-- > 0;) { struck[i] = (uint8_t)(!replied[i] && later); later |= replied[i]; }
}
