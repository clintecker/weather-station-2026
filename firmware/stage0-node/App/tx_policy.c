#define WS_CHECK_FILE 3
#include "tx_policy.h"
#include "clock.h"
#include "leds.h"
#include "radio_cfg.h"
#include "stage0.h"
#include "sys_app.h"
#include "tx_exchange.h"
#include "ws_be.h"
#include "ws_check.h"
#include "ws_frame.h"
#include "ws_obs.h"
#include "ws_policy.h"
#include "power_config.h"
#if POWER_HAS_BQ25798
#include "charger.h"
#include "power_acq.h"
#endif

_Static_assert(WS_BACKLOG_MAX <= MAX_QUEUE - 1U, "the send queue holds the live reading plus the largest backlog");
#define TURNAROUND_MS 300U   /* gateway commit (fullfsync) + USB both ways, conservative */
#define STRIKE_LIMIT  10U
#define STRIKE_SLOTS  6
#define DIAG_PERIOD_S 900U
#define MINUTE_S      60U
#define BEACON_S      3600U   /* CRITICAL: the live reading (and a due health report) once an hour */
_Static_assert(DIAG_PERIOD_S > MINUTE_S, "a health report period longer than a minute");

static ws_link link;
static uint32_t last_send_s;   /* the last minute that sent: the CONSERVE interval and the probe schedule count from it */
static uint32_t exchange_ms;   /* estimated radio time of one answered exchange */
static uint32_t diag_ms;       /* the health report's airtime: reserved in a minute whose report follows */
static ws_strike strikes[STRIKE_SLOTS];
static int diag_due = 1;       /* a health report right after boot */
static uint32_t last_diag_s;
/* CRITICAL's beacon outside its hour: BEACON_NOW on entering CRITICAL (the reading that says so, and the
   health report the change makes due, go at once), BEACON_RETRY the minute after an unanswered beacon
   (once: one lost frame does not make a two-hour gap). beacon_out: the running exchange is a beacon. */
enum { BEACON_NONE, BEACON_NOW, BEACON_RETRY };
static uint8_t beacon_due, beacon_out;

/* The energy state (docs/radio-energy-policy.md section 3, D1; ws_energy_next). The TX stack
   (profile 3) decides it from the gauge, falling back to the charger's VBAT; it starts at CONSERVE
   (fail closed) and the first minute with a reading moves it. The bench builds (profiles 1 and 2)
   stay at NORMAL: their battery is a bench supply or a loose cell, not the field pack. */
#if POWER_HAS_BQ25798
#define VBAT_FRESH_MS 30000U  /* the oldest charger VBAT the energy state uses when the gauge is gone */
#define BATT_IDLE_MA_X100 50  /* -0.5 mA: "not discharging" within the battery INA228's offset */
static int energy = WS_ENERGY_CONSERVE;

static void energy_inputs(ws_energy_in *in, const char **src)
{
  power_live_t p;
  const charger_t *c = charger_state();
  power_acq_live(&p);
  *in = (ws_energy_in){ 0 };
  *src = "none";
  if (p.gauge_ok)
  { in->soc_ok = 1; in->soc_x10 = p.soc_pct_x10; *src = "gauge"; }
  if (p.gauge_ok && p.vcell_mv)
  { in->v_ok = 1; in->v_mv = p.vcell_mv; }
  else if (c->present && c->ok && c->adc_ok && clock_ms() - c->ts_ms < VBAT_FRESH_MS)
  { in->v_ok = 1; in->v_mv = c->vbat; if (!p.gauge_ok) *src = "charger-vbat"; }   /* REG3B: 1 mV a count */
  unsigned stage = (p.charger & WS_CHG_STAGE_MASK) >> WS_CHG_STAGE_SHIFT;
  in->powered = p.charger != POWER_NONE_U8 && (p.charger & POWER_STATUS_POWER_GOOD) && !(p.charger & POWER_STATUS_FAULT);
  in->full = in->powered && (stage == WS_CHG_STAGE_TOPOFF || stage == WS_CHG_STAGE_TERMINATED) &&
             p.batt_ok && p.batt_ma_x100 >= -BATT_IDLE_MA_X100;
}

void policy_energy_minute(void)
{
  ws_energy_in in;
  const char *src;
  energy_inputs(&in, &src);
  int next = ws_energy_next(energy, &in);
  if (next == energy) return;
  APP_PRINTF("#energy %s -> %s soc_x10=%d v_mv=%d full=%u src=%s\n", ws_energy_name(energy), ws_energy_name(next),
             in.soc_ok ? (int)in.soc_x10 : -1, in.v_ok ? (int)in.v_mv : -1, (unsigned)in.full, src);
  energy = next;
  diag_due = 1;   /* the health report carries the energy state: send one at the next exchange */
  beacon_due = next == WS_ENERGY_CRITICAL ? BEACON_NOW : BEACON_NONE;   /* a retry ends with CRITICAL */
}
int energy_state(void) { return energy; }
#else
void policy_energy_minute(void) {}
int energy_state(void) { return WS_ENERGY_NORMAL; }
#endif
int policy_probing(void) { return link.probing; }
uint32_t policy_silent_minutes(void) { return link.silent; }

void policy_init(void)
{
  static const uint32_t bw_hz[] = { 125000, 250000, 500000 };
  _Static_assert(WS_LORA_BANDWIDTH < sizeof bw_hz / sizeof bw_hz[0], "a LoRa bandwidth index radio_cfg.h knows");
  uint32_t bw = bw_hz[WS_LORA_BANDWIDTH];
  exchange_ms = ws_lora_airtime_ms(OBS_FRAME_MAX, WS_LORA_SF, bw, WS_LORA_PREAMBLE, WS_LORA_CR) +
                ws_lora_airtime_ms(WS_ACK_FRAME_LEN, WS_LORA_SF, bw, WS_LORA_PREAMBLE, WS_LORA_CR) + TURNAROUND_MS;
  diag_ms = ws_lora_airtime_ms(WS_DIAG_FRAME_LEN, WS_LORA_SF, bw, WS_LORA_PREAMBLE, WS_LORA_CR);
  /* As if the last send were an hour ago: the first minute after boot may send in every energy
     state but CRITICAL's quiet hours (CONSERVE's 5 minutes and the beacon count from it). */
  last_send_s = clock_s() - BEACON_S;
}

/* Will a health report follow this minute's exchange? Due now, or due before the next minute
   starts: last_diag_s is stamped after an exchange, so 15 minutes later the minute starts a few
   seconds before the report falls due, and the report goes at that exchange's end
   (finish_exchange, tx_exchange.c). A link-state change decides at the exchange's end: no reserve. */
static int diag_follows(uint32_t now_s) { return diag_due || now_s - last_diag_s > DIAG_PERIOD_S - MINUTE_S; }

int policy_minute_backlog(void)
{
  uint32_t now = clock_s();
  uint32_t reserve_ms = diag_follows(now) ? diag_ms : 0U;   /* power telemetry design 6.4 */
  int en = energy_state();
  /* CRITICAL sends nothing, but for a beacon: once an hour (and right after boot, policy_init), on
     entering CRITICAL and once after an unanswered beacon, the minute goes as a CONSERVE minute (the live
     reading only, CONSERVE's 5 minutes waived), so the gateway still hears the station. */
  uint32_t since = last_send_s;
  uint8_t out = BEACON_NONE;
  /* cppcheck-suppress knownConditionTrueFalse ; the bench profiles (1, 2) stay NORMAL, profile 3 does not */
  if (en == WS_ENERGY_CRITICAL && (beacon_due || now - last_send_s >= BEACON_S))
  {
    en = WS_ENERGY_CONSERVE;
    since = now - BEACON_S;
    out = beacon_due == BEACON_RETRY ? BEACON_RETRY : BEACON_NOW;
  }
  int backlog = ws_minute_backlog(en, &link, now, since, exchange_ms, reserve_ms, MAX_QUEUE - 1U);
  if (backlog < 0) return backlog;
  last_send_s = now;
  beacon_out = out;
  beacon_due = BEACON_NONE;
  return backlog;
}

/* Identity of a journaled record (its first 8 bytes); 0 if the slot cannot be read. */
static int record_id(jref_t r, uint32_t *epoch, uint32_t *seq)
{
  uint8_t plain[WS_OBS_PLAIN_MAX];
  if (store_journal_read(r, plain)) return 0;
  *epoch = ws_obs_epoch(plain); *seq = ws_obs_seq(plain);
  return 1;
}

static void strike(jref_t r)
{
  uint32_t epoch, seq; jref_t now;
  if (!record_id(r, &epoch, &seq) || !ws_strike_note(strikes, STRIKE_SLOTS, epoch, seq, STRIKE_LIMIT)) return;
  /* Abandon only a record that is still pending under this identity. */
  if (store_journal_find(epoch, seq, &now) || store_journal_ack(now)) return;
  (void)store_note_abandoned();   /* a total that failed to persist is only a count: the record is acknowledged */
  led_flash(LED_RED, LED_FLASH_LONG_MS);
  APP_PRINTF("#abandon epoch=%u seq=%u after %u unanswered tries while the gateway answered a later frame; abandoned=%u\n",
             (unsigned)epoch, (unsigned)seq, STRIKE_LIMIT, (unsigned)store_abandoned_total());
}

void policy_strike_forget(uint32_t epoch, uint32_t seq) { ws_strike_forget(strikes, STRIKE_SLOTS, epoch, seq); }

static void link_report(int change, uint32_t was_silent)
{
  int en = energy_state();
  uint32_t wait = ws_link_probe_interval(&link);
  int live_every_minute = ws_link_may_send(en, 1, (int32_t)wait);
  if (change == WS_LINK_RELINKED || change == WS_LINK_PROBING) diag_due = 1;   /* the report carries the link state */
  if (change == WS_LINK_RELINKED) { APP_PRINTF("#link linked after %u silent minutes\n", (unsigned)was_silent); }
  else if (change == WS_LINK_PROBING && live_every_minute)
  { APP_PRINTF("#link probing: %u silent minutes; live reading every minute, no backlog (energy %s)\n",
               (unsigned)link.silent, ws_energy_name(en)); }
  else if (change == WS_LINK_PROBING)
  { APP_PRINTF("#link probing: %u silent minutes; next probe in %u s (live readings stay journaled)\n",
               (unsigned)link.silent, (unsigned)wait); }
  else if (change == WS_LINK_PROBE_MISSED && !live_every_minute)
  { APP_PRINTF("#link probe unanswered; next probe in %u s\n", (unsigned)wait); }
}

void policy_exchange_end(const jref_t *queue, const uint8_t *replied, unsigned n)
{
  int any = 0; /* did the gateway answer anything in this exchange? */
  uint8_t struck[MAX_QUEUE];
  if (!WS_CHECK(n <= MAX_QUEUE)) n = MAX_QUEUE;   /* the exchange's queue: struck[] has its size */
  ws_strike_targets(replied, n, struck);
  for (unsigned i = 0; i < n; i++)
  {
    uint32_t epoch, seq;
    any |= replied[i];
    if (struck[i]) strike(queue[i]);
    else if (replied[i] && record_id(queue[i], &epoch, &seq)) policy_strike_forget(epoch, seq);
  }
  if (beacon_out == BEACON_NOW && !any) beacon_due = BEACON_RETRY;   /* the first try only */
  beacon_out = BEACON_NONE;
  uint32_t was_silent = link.silent;
  link_report(ws_link_minute(&link, any, last_send_s), was_silent);
}

int policy_diag_due(void) { return diag_due || clock_s() - last_diag_s >= DIAG_PERIOD_S; }
void policy_diag_sent(uint32_t now_s) { diag_due = 0; last_diag_s = now_s; }
