#define WS_CHECK_FILE 11
#include "ws_policy.h"
#include "stage0.h"
#include "ws_obs.h"
#include "ws_check.h"

/* Per energy state (WS_ENERGY_* order): backlog frames and radio time per minute. */
static const char *const energy_name[] = { "surplus", "normal", "conserve", "critical" };
static const uint8_t backlog_limit[] = { WS_BACKLOG_MAX, 5, 0, 0 };
static const uint16_t airtime_cap_ms[] = { 15000, 5000, 2000, 0 };
#define ENERGY_STATES (sizeof energy_name / sizeof energy_name[0])
_Static_assert(ENERGY_STATES == WS_ENERGY_CRITICAL + 1 && sizeof backlog_limit == ENERGY_STATES &&
               sizeof airtime_cap_ms / sizeof airtime_cap_ms[0] == ENERGY_STATES, "one entry per energy state");
#define CONSERVE_INTERVAL_S 300U   /* spec R02 */
static const uint16_t probe_interval_s[] = { 120, 240, 480, 900 };
#define PROBE_STEPS (sizeof probe_interval_s / sizeof probe_interval_s[0])

const char *ws_energy_name(int energy)
{
 return energy >= 0 && energy < (int)ENERGY_STATES ? energy_name[energy] : "?";
}

uint32_t ws_lora_airtime_ms(uint32_t payload, uint32_t sf, uint32_t bw_hz, uint32_t preamble, uint32_t cr)
{
 /* radio_cfg.h's constants; outside the formula's range the answer is a whole minute, which leaves
    room for the live reading only (the cautious estimate) instead of a division by zero. */
 if (!WS_CHECK(sf >= 7 && sf <= 12 && bw_hz >= 7800 && cr >= 1 && cr <= 4)) return 60000;
 uint32_t de = ((1000000UL << sf) / bw_hz) > 16000 ? 1 : 0;           /* low data rate optimisation: symbol > 16 ms */
 int32_t num = 8 * (int32_t)payload - 4 * (int32_t)sf + 28 + 16;
 int32_t den = 4 * ((int32_t)sf - 2 * (int32_t)de);
 int32_t blocks = num > 0 ? (num + den - 1) / den : 0;
 uint32_t symbols_x4 = (preamble * 4 + 17) + 4 * (8 + (uint32_t)blocks * (cr + 4));
 return (uint32_t)(((uint64_t)symbols_x4 * (1000000UL << sf) / bw_hz) / 4000) + 1;
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
 /* ws_link_minute keeps probe_step below PROBE_STEPS; past it, the longest interval */
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
 if (!WS_CHECK(slots > 0)) return 0;   /* no table: no strike */
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
 int later = 0;   /* a frame after i was answered */
 /* bound: n frames (the exchange's queue, MAX_QUEUE) */
 for (unsigned i = n; i-- > 0;) { struck[i] = (uint8_t)(!replied[i] && later); later |= replied[i]; }
}
