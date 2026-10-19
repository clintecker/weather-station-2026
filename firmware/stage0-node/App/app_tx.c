/* GENERATED from app_tx.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/app_tx.lit.md (tests/test_tangle.py checks this file). */
/* TX node of the bench station: one observation per minute from its WSMP local modules
 * (docs/module-protocol.md, App/wsmp_host.h). The node journals each
 * observation in flash before it transmits it. The journal keeps the record until the gateway
 * sends an authenticated ACK or NACK, or until the strike rule abandons it (ws_policy.h). Each
 * minute sends the live observation first. Then it sends older pending records as the energy and
 * link policy allows (docs/radio-energy-policy.md). Each frame gets a new counter, reserved
 * durably, and one ACK receive window. This file holds boot and the sampling glue. App/tx_node.h
 * lists the other TX modules. */
#define WS_CHECK_FILE 1
#include <string.h>
#include "board_inputs.h"
#include "busymon.h"
#include "clock.h"
#include "fault.h"
#include "leds.h"
#include "node_store.h"
#include "radio_cfg.h"
#include "selftest.h"
#include "mod_rain.h"
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
#include "wsmp_catalog_map.h"
#include "wsmp_host.h"
#include "wsmp_local.h"

#define SAMPLE_PERIOD_MS    15000U  /* the minute's ticks; the modules sample on their own (product spec, section 9) */
#define SAMPLES_PER_REPORT  4U
/* A TX node that keeps failing must not look healthy. Above this many failures in a row, the
 * watchdog resets the board, and the reset runs Radio.Init again. The two runs are journal appends
 * (journal_fails) and transmissions (exchange_counts()->air). Minutes that the policy chose not to
 * send never count. */
#define TX_FAIL_LIMIT       10U
/* A storage failure at boot can be transient. A reset after 10 minutes retries the boot once. */
#define BOOT_RETRY_MS       (10UL * CLOCK_MS_PER_MIN)

static UTIL_TIMER_Object_t sample_timer, module_timer, boot_retry_timer;
static uint32_t last_sample_s;   /* the watchdog check reads it as proof of progress */
/* This boot's identity and run state. Only this file writes it. The other TX modules read it
   through node_state() (docs/power-of-ten.md, rule 6). */
static tx_node_t node;
const tx_node_t *node_state(void) { return &node; }
uint32_t node_uptime_s(void) { return clock_s() - node.boot_s; }
int node_selftest(void) { node.kat_ok = selftest_kat(); return node.kat_ok; }

static unsigned sample_ticks;
static int modules_reported;   /* the first report prints the #modules line */
static int stuck;              /* the exchange outlasted its bound. The watchdog resets the board */

void sampling_stop(void)
{
  node.running = 0;
  (void)UTIL_TIMER_Stop(&sample_timer);
  (void)UTIL_TIMER_Stop(&module_timer);
}

/* Readings that a minute produced while the previous minute's exchange still ran. The firmware
 * writes flash only with the radio idle (docs/firmware-event-model.md). Such a reading therefore
 * waits here, encoded. held_flush() journals it the moment the radio goes idle, before anything
 * else runs. The next minute sends it as backlog. A normal exchange ends well within its minute.
 * Only a hung radio keeps it busy longer. The watchdog then resets the board after the exchange
 * outlasts its bound (at most 116 s, with 21 frames) plus the independent watchdog's ~8 s. So at
 * most HELD_MAX minutes can wait. If one more comes anyway, hold() drops the oldest held reading,
 * counts it in held_lost and keeps the newest. A reset loses what is held. Those sequence numbers
 * are never sent, so the gateway sees the gap. */
#define HELD_MAX 2U
#define SAMPLING_STALL_S 150U   /* 10 sample periods without a sample: the sampler stopped */
static uint8_t held[HELD_MAX][WS_OBS_PLAIN_MAX];
static unsigned held_n;


/* hold() makes room first, so held_n never exceeds HELD_MAX. held_count() clamps a count that did. */
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
    APP_PRINTF("#error held-lost seq=%u (a newer reading replaced it; held_lost=%u)\n", (unsigned)ws_obs_seq(held[0]),
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
    APP_PRINTF("#held journaled seq=%u rc=%d pending=%u\n", (unsigned)ws_obs_seq(held[i]), rc, (unsigned)store_journal_pending());
  }
  held_n = 0;
}

/* Sends what this minute may send: the live reading and the backlog that the policy allows. live
   is NULL if its journal append failed. A refused minute's reading stays journaled. */
static void minute_send(const jref_t *live)
{
  if (exchange_busy()) return;   /* journal_or_hold held the reading. Ask the policy only for a sending minute */
  int backlog = policy_minute_backlog();
  if (backlog >= 0) exchange_start(live, (unsigned)backlog);
}

/* The minute's observation, built from the modules' snapshots. */
typedef struct { int valid; int16_t t; uint16_t h; uint32_t utc, uptime; unsigned samples; } minute_t;

/* Builds and encodes the minute's observation into plain (WS_OBS_PLAIN_MAX bytes). Returns 0 if
   it did not encode. */
static int minute_encode(minute_t *m, uint8_t *plain)
{
  wsmp_map_summary sum;
  m->utc = time_utc();
  m->uptime = node_uptime_s(); /* always sent: the gateway reconstructs time from it */
  /* static: only the sequencer runs this, and it never re-enters. It is on the deepest callback
     chain, which tools/stack_report.py counts four times (a 104-byte record cost ~416 B). */
  static ws_obs_t o;
  o = (ws_obs_t){ .epoch = node.boot_epoch, .seq = node.next_seq, .utc = m->utc, .uptime = m->uptime,
                  .energy = (uint8_t)energy_state() };
  wsmp_map_obs(&o, &sum);
  m->valid = sum.th_valid; m->t = sum.t; m->h = sum.h; m->samples = sum.th_samples;
  if (!m->valid) node.sensor_faults++;
  if (!modules_reported)
  {
    char line[WSMP_MODULES_LINE_MAX];
    modules_reported = 1;
    (void)wsmp_host_modules_line(line, sizeof line);
    APP_PRINTF("%s\n", line);
  }
  return ws_obs_encode(&o, plain, WS_OBS_PLAIN_MAX) == (int)WS_OBS_PLAIN_LEN(o.bitmap);
}

/* Journals the encoded reading now, or holds it while the radio is busy. held_flush() counts a
   held reading's append when the radio goes idle. Returns 0 if it journaled or held the reading.
   Otherwise returns the error: REC_ENOTENCODED or a STORE_E* code. */
#define REC_ENOTENCODED (-100)   /* outside the STORE_E* range */
static int journal_or_hold(const uint8_t *plain, int encoded, int busy, jref_t *live)
{
  int rc = encoded ? 0 : REC_ENOTENCODED;
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

/* The minute's report. The node journals it and sends it as the policy allows. If the previous
   minute's exchange still runs, the radio transmits or listens, and no flash write may happen.
   The node then holds the report in RAM. */
static void minute_report(int src)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t live; minute_t m;
  int encoded = WS_CHECK(minute_encode(&m, plain));   /* this file's codes always encode */
  int busy = exchange_busy();
  bm_span s = busymon_begin();
  int rc = journal_or_hold(plain, encoded, busy, &live);   /* a new journal page erases ~22 ms */
  busymon_step_end(s, "report.journal");
  sample_line(&m, src, rc, busy);
  node.next_seq++; /* a sequence number is never reused, even after a failed journal write */
  if (busy) { APP_PRINTF("#busy previous exchange still running; reading held until it ends\n"); return; }
  s = busymon_begin();
  minute_send(rc ? NULL : &live);
  busymon_step_end(s, "report.send");
}

/* Every 15 s; the 4th tick latches every module and makes the minute's report. */
static void sample(void)
{
  last_sample_s = clock_s();
  if (++sample_ticks < SAMPLES_PER_REPORT) return;
  sample_ticks = 0;
  if (!node.running || stuck) return;   /* no report after sampling stopped (reboot, storm, stuck radio) */
  wsmp_host_latch(time_utc(), clock_ms());
  minute_report(0);
}
BUSYMON_TASK(sample)

static void module_tick(void) { if (node.running && !stuck) wsmp_host_tick(clock_ms()); }
BUSYMON_TASK(module_tick)

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }
static void on_module_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sensor, CFG_SEQ_Prio_0); }

/* Watchdog health: the node must make real progress, not only run its main loop. */
int watchdog_healthy(void)
{
  uint32_t now = clock_s();
  if (stuck) return 0;
  if (!node.running) return 1;                             /* not sampling by design */
  if (now - last_sample_s > SAMPLING_STALL_S) return 0;       /* sampling stopped */
  if (exchange_overdue(now))                                  /* radio exchange stuck */
  {
    /* Stop sampling and the radio, and journal any held reading with the radio idle. Then the
       watchdog resets the board, and the reset loses no reading. */
    stuck = 1;
    sampling_stop();
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

/* A failed self-test needs an operator, not a reset, so it never retries. An unprovisioned board
   never calls this. */
static void boot_retry(void)
{
  if (!node.kat_ok) return;
  APP_PRINTF("#boot-retry: reset in %u s\n", (unsigned)(BOOT_RETRY_MS / CLOCK_MS_PER_S));
  (void)UTIL_TIMER_Create(&boot_retry_timer, BOOT_RETRY_MS, UTIL_TIMER_ONESHOT, on_boot_retry, NULL);
  (void)UTIL_TIMER_Start(&boot_retry_timer);
}

/* Returns 1 if the node may sample and transmit: storage, key, self-test and a durable epoch. */
static int boot_ready(void)
{
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); boot_retry(); return 0; }
  uint32_t scrubbed = store_journal_scrub(STORM_EPOCH);
  if (scrubbed) APP_PRINTF("#storm-scrub dropped=%u (test slots a power cut left pending)\n", (unsigned)scrubbed);
  if (!exchange_load_identity()) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return 0; }
  time_restore();
  if (!node.kat_ok) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return 0; }
  /* A durable epoch before the first sample keeps every observation identity unique. */
  if (store_next_epoch(&node.boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); boot_retry(); return 0; }
  return 1;
}

static void modules_start(void)
{
  board_inputs_init();
  local_init(node.boot_epoch, clock_ms());
  mod_rain_set_enabled(store_rain_enabled());
  wsmp_host_init();
  (void)UTIL_TIMER_Create(&module_timer, WSMP_TICK_MS, UTIL_TIMER_PERIODIC, on_module_timer, NULL);
  (void)UTIL_TIMER_Start(&module_timer);
}

void SubghzApp_Init(void)
{
  stackmon_paint();
  busymon_init();
  leds_init();
  exchange_init();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sample, UTIL_SEQ_RFU, sample_timed);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sensor, UTIL_SEQ_RFU, module_tick_timed);
  tx_console_init();

  node.boot_s = clock_s();
  policy_init();
  watchdog_start();
  node.kat_ok = selftest_kat();
  APP_PRINTF("#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             watchdog_reset_cause(), node.kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, (unsigned)WS_LORA_BANDWIDTH, (unsigned)WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  if (!boot_ready()) return;
  modules_start();
  node.running = 1;
  last_sample_s = clock_s();
  tx_status();
  (void)UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  (void)UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
