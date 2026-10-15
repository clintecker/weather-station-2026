/* Stage-0 TX: one SHT45 observation per minute, journaled in flash before transmission and
 * retained until an authenticated host ACK (or a NACK / strike-limit abandon). Each minute sends
 * the live observation first, then older pending ones as the energy and link policy allows
 * (docs/radio-energy-policy.md); each frame gets a fresh durably reserved counter and one ACK
 * receive window. This file is boot and the sampling glue; the other TX modules are listed in
 * App/tx_node.h. */
#define WS_CHECK_FILE 1
#include <string.h>
#include "busymon.h"
#include "clock.h"
#include "fault.h"
#include "leds.h"
#include "node_store.h"
#include "radio_cfg.h"
#include "selftest.h"
#include "sensor.h"
#include "stackmon.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "tx_console.h"
#include "tx_exchange.h"
#include "tx_node.h"
#include "tx_policy.h"
#include "tx_time.h"
#include "utilities_def.h"
#include "watchdog.h"
#include "ws_be.h"
#include "ws_check.h"
#include "ws_obs.h"

#define SAMPLE_PERIOD_MS    15000U  /* one T/RH sample; every SAMPLES_PER_REPORT-th builds the minute (PRD 9) */
#define SAMPLES_PER_REPORT  4U
/* Review P7: a TX that keeps failing must not look healthy. Above this many failures in a row,
 * of journal appends (journal_fails) or of transmissions (exchange_counts()->air), the watchdog
 * resets the board (which re-runs Radio.Init). Minutes the policy chose not to send never count. */
#define TX_FAIL_LIMIT       10U
/* A storage failure at boot may be transient: retry once by a reset after 10 minutes. */
#define BOOT_RETRY_MS       (10UL * 60000UL)

static UTIL_TIMER_Object_t sample_timer, boot_retry_timer;
static uint32_t last_sample_s;   /* watchdog progress evidence */
/* This boot's identity and run state: written only here; the other TX modules read it through
   node_state() (docs/power-of-ten.md, rule 6). */
static tx_node_t node;
const tx_node_t *node_state(void) { return &node; }
uint32_t node_uptime_s(void) { return clock_s() - node.boot_s; }
int node_selftest(void) { node.kat_ok = selftest_kat(); return node.kat_ok; }

/* The minute's 15-s samples (PRD section 9: coverage, mean and extrema). */
static ws_th_window th_window;
static unsigned th_ticks;
static int sensor_reported;   /* the first reading after boot is printed as #sensor */
static int stuck;             /* the exchange outlasted its worst case: the watchdog is resetting the board */

void sampling_stop(void)
{
  node.running = 0;
  (void)UTIL_TIMER_Stop(&sample_timer);
}

/* Draft-5 observation (docs/protocol-draft5-design.md 5): out-of-range temperature is INVALID,
   RH is clamped (ws_code_*); a sensor fault sends every field as INVALID, never leaves it out.
   The summary fields are used only if the build's bitmap includes them (WS_F_TH_SUMMARY in
   node_fields.h). */
static void obs_codes(ws_obs_t *o, int valid, int16_t t, uint16_t h)
{
  static const uint8_t th_fields[] = { WS_FI_TEMPERATURE_C, WS_FI_HUMIDITY_PCT, WS_FI_TEMPERATURE_MIN_C,
                                       WS_FI_TEMPERATURE_MAX_C, WS_FI_HUMIDITY_MIN_PCT, WS_FI_HUMIDITY_MAX_PCT };
  o->code[WS_FI_TH_SAMPLES] = th_window.n > 60U ? 60U : th_window.n;
  if (!valid)
  {
    for (unsigned i = 0; i < sizeof th_fields; i++) o->code[th_fields[i]] = ws_obs_invalid(th_fields[i]);
    return;
  }
  o->code[WS_FI_TEMPERATURE_C] = ws_code_temp_centi(t);
  o->code[WS_FI_HUMIDITY_PCT] = ws_code_rh_centi(h);
  o->code[WS_FI_TEMPERATURE_MIN_C] = ws_code_temp_centi(th_window.t_min);
  o->code[WS_FI_TEMPERATURE_MAX_C] = ws_code_temp_centi(th_window.t_max);
  o->code[WS_FI_HUMIDITY_MIN_PCT] = ws_code_rh_centi(th_window.h_min);
  o->code[WS_FI_HUMIDITY_MAX_PCT] = ws_code_rh_centi(th_window.h_max);
}

/* Readings a minute produced while the previous minute's exchange was still running. Flash is only
 * written with the radio idle (docs/firmware-event-model.md), so such a reading waits here, encoded,
 * and held_flush() journals it the moment the radio goes idle, before anything else runs; the next
 * minute sends it as backlog. A normal exchange ends well within its minute; only a hung radio
 * keeps it busy longer, and then the watchdog resets the board once the exchange outlasts its bound
 * (at most 116 s, with 21 frames) plus the IWDG's ~8 s, so at most HELD_MAX minutes can be waiting.
 * Should one more come anyway, the oldest held reading is dropped and counted (held_lost) and the
 * newest kept. A reset loses what is held: those sequence numbers are never sent, so the gateway
 * sees the gap. */
#define HELD_MAX 2U
static uint8_t held[HELD_MAX][WS_OBS_PLAIN_MAX];
static unsigned held_n;

static uint32_t plain_seq(const uint8_t *plain) { return ws_get_be32(plain + 4); }

/* hold() makes room before it adds, so held_n never exceeds HELD_MAX; a count that did is clamped. */
static unsigned held_count(void)
{
  if (!WS_CHECK(held_n <= HELD_MAX)) held_n = HELD_MAX;
  return held_n;
}

static void hold(const uint8_t *plain)
{
  if (held_count() == HELD_MAX)
  {
    node.held_lost++;
    APP_PRINTF("#error held-lost seq=%u (a newer reading replaced it; held_lost=%u)\n", (unsigned)plain_seq(held[0]),
               (unsigned)node.held_lost);
    memmove(held[0], held[1], (HELD_MAX - 1U) * sizeof held[0]);
    held_n--;
  }
  memcpy(held[held_n++], plain, sizeof held[0]);
}

void held_flush(void)
{
  jref_t r;
  for (unsigned i = 0, n = held_count(); i < n; i++)
  {
    int rc = store_journal_append(held[i], &r);
    ws_failrun_note(&node.journal_fails, rc == 0);
    APP_PRINTF("#held journaled seq=%u rc=%d pending=%u\n", (unsigned)plain_seq(held[i]), rc, (unsigned)store_journal_pending());
  }
  held_n = 0;
}

/* What this minute may send, if anything: the live reading (NULL if its journal append failed)
   and the backlog the policy allows. A refused minute's reading stays journaled. */
static void minute_send(const jref_t *live)
{
  int backlog = policy_minute_backlog();
  if (backlog >= 0) exchange_start(live, (unsigned)backlog);
}

/* The minute's observation, from its samples. */
typedef struct { int valid; int16_t t; uint16_t h; uint32_t utc, uptime; unsigned samples; } minute_t;

/* Build and encode the minute's observation into plain (WS_OBS_PLAIN_MAX bytes); 0 if it did not
   encode. Starts the next minute's window. */
static int minute_encode(minute_t *m, uint8_t *plain)
{
  m->t = 0; m->h = 0;
  m->valid = ws_th_mean_t(&th_window, &m->t) && ws_th_mean_h(&th_window, &m->h);
  m->utc = time_utc();
  m->uptime = node_uptime_s(); /* always sent: the gateway reconstructs time from it */
  if (!m->valid) node.sensor_faults++;
  /* static: this runs only from the sequencer, never re-entered, and it is on the deepest callback
     chain, which tools/stack_report.py counts four times (a 104-byte record cost ~416 B). */
  static ws_obs_t o;
  o = (ws_obs_t){ .epoch = node.boot_epoch, .seq = node.next_seq, .utc = m->utc, .uptime = m->uptime,
                  .energy = (uint8_t)energy_state(), .bitmap = WS_NODE_FIELDS };
  obs_codes(&o, m->valid, m->t, m->h);
  m->samples = th_window.n;
  ws_th_reset(&th_window);
  return ws_obs_encode(&o, plain, WS_OBS_PLAIN_MAX) == (int)WS_OBS_PLAIN_MAX;
}

/* Journal the encoded reading now, or hold it while the radio is busy (a held reading's append
   is counted when the radio goes idle). 0: journaled or held; else the error (-3: not encoded). */
static int journal_or_hold(const uint8_t *plain, int encoded, int busy, jref_t *live)
{
  int rc = encoded ? 0 : -3;
  if (!rc && busy) hold(plain);
  else if (!rc) rc = store_journal_append(plain, live);
  if (rc || !busy) ws_failrun_note(&node.journal_fails, rc == 0);
  return rc;
}

static void sample_line(const minute_t *m, int src, int rc, int busy)
{
  APP_PRINTF("#sample epoch=%u seq=%u uptime=%u valid=%d rc=%d n=%u t=%d rh=%u time=%s utc=%u journal=%s pending=%u lost=%u\n",
             (unsigned)node.boot_epoch, (unsigned)node.next_seq, (unsigned)m->uptime, m->valid, src, m->samples,
             m->valid ? m->t : 0, m->valid ? m->h : 0U, m->utc ? "synchronized" : "unknown", (unsigned)m->utc,
             rc ? "ERROR" : busy ? "held" : "ok", (unsigned)store_journal_pending(), (unsigned)store_journal_lost());
}

/* The minute's report: journaled and sent as the policy allows, or held while the previous
   minute's exchange is still running (the radio is transmitting or listening: no flash write). */
static void minute_report(int src)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t live; minute_t m;
  int encoded = WS_CHECK(minute_encode(&m, plain));   /* our own codes always encode */
  int busy = exchange_busy();
  int rc = journal_or_hold(plain, encoded, busy, &live);
  sample_line(&m, src, rc, busy);
  node.next_seq++; /* identity is never reused, even if the journal write failed */
  if (busy) { APP_PRINTF("#busy previous exchange still running; reading held until it ends\n"); return; }
  minute_send(rc ? NULL : &live);
}

void sensor_done(int src, int16_t t, uint16_t h)
{
  if (!node.running || stuck) return;   /* a measurement that finishes after sampling stopped (reboot, storm, stuck radio) */
  if (!sensor_reported)
  {
    sensor_reported = 1;
    if (src) { APP_PRINTF("#sensor fault rc=%d (see sensor.h for codes)\n", src); }
    else { APP_PRINTF("#sensor ok t=%d rh=%u\n", t, h); }
  }
  ws_th_add(&th_window, src == 0, t, h);
  if (++th_ticks < SAMPLES_PER_REPORT) return;   /* the minute's report follows its last sample */
  th_ticks = 0;
  minute_report(src);
}

/* Every 15 s: start a measurement; sensor_done() gets its result from the sensor task ~10 ms later. */
static void sample(void)
{
  last_sample_s = clock_s();
  if (sensor_start()) sensor_done(-1, 0, 0);   /* the previous one never finished: a missed sample */
}
BUSYMON_TASK(sample)

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }

/* Watchdog health: real progress, not just a running main loop (failure-modes.md G1). */
int watchdog_healthy(void)
{
  uint32_t now = clock_s();
  if (stuck) return 0;
  if (!node.running) return 1;                             /* not sampling by design */
  if (now - last_sample_s > 150) return 0;                    /* sampling stopped */
  if (exchange_overdue(now))                                  /* radio exchange stuck */
  {
    /* Stop sampling and the radio, journal any held reading with the radio idle, then let the
       watchdog reset the board: the reset loses no reading. */
    stuck = 1;
    (void)UTIL_TIMER_Stop(&sample_timer);
    exchange_abort();
    APP_PRINTF("#watchdog radio exchange stuck; radio stopped, held readings journaled, resetting\n");
    return 0;
  }
  if (ws_failrun_tripped(&node.journal_fails, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u journal failures in a row\n", (unsigned)node.journal_fails.n); return 0; }
  const ws_failrun *air = &exchange_counts()->air;
  if (ws_failrun_tripped(air, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u transmit failures in a row\n", (unsigned)air->n); return 0; }
  return 1;
}

static void on_boot_retry(void *ctx) { (void)ctx; NVIC_SystemReset(); }

/* Never for an unprovisioned board or a failed self-test: those need an operator, not a reset. */
static void boot_retry(void)
{
  if (!node.kat_ok) return;
  APP_PRINTF("#boot-retry: reset in %u s\n", (unsigned)(BOOT_RETRY_MS / 1000));
  (void)UTIL_TIMER_Create(&boot_retry_timer, BOOT_RETRY_MS, UTIL_TIMER_ONESHOT, on_boot_retry, NULL);
  (void)UTIL_TIMER_Start(&boot_retry_timer);
}

/* Storage, key, self-test and a durable epoch: 1 if the node may sample and transmit. */
static int boot_ready(void)
{
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); boot_retry(); return 0; }
  uint32_t scrubbed = store_journal_scrub(STORM_EPOCH);
  if (scrubbed) APP_PRINTF("#storm-scrub dropped=%u (test slots a power cut left pending)\n", (unsigned)scrubbed);
  if (!exchange_load_identity()) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return 0; }
  time_restore();
  if (!node.kat_ok) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return 0; }
  /* Durable epoch before the first sample: observation identities never repeat. */
  if (store_next_epoch(&node.boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); boot_retry(); return 0; }
  return 1;
}

void SubghzApp_Init(void)
{
  stackmon_paint();
  busymon_init();
  leds_init();
  exchange_init();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sample, UTIL_SEQ_RFU, sample_timed);
  tx_console_init();

  node.boot_s = clock_s();
  policy_init();
  watchdog_start();
  node.kat_ok = selftest_kat();
  APP_PRINTF("#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             watchdog_reset_cause(), node.kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, (unsigned)WS_LORA_BANDWIDTH, (unsigned)WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  if (!boot_ready()) return;
  sensor_init();
  node.running = 1;
  last_sample_s = clock_s();
  tx_status();
  (void)UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  (void)UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
