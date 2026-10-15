/* Stage-0 TX: one SHT45 observation per minute, journaled in flash before transmission and
 * retained until an authenticated host ACK (or a NACK / strike-limit abandon). Each minute sends
 * the live observation first, then older pending ones as the energy and link policy allows
 * (docs/radio-energy-policy.md); each frame gets a fresh durably reserved counter and one ACK
 * receive window. This file is boot and the sampling glue; the other TX modules are listed in
 * App/tx_node.h. */
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
#include "ws_obs.h"

#define SAMPLE_PERIOD_MS    15000U  /* one T/RH sample; every SAMPLES_PER_REPORT-th builds the minute (PRD 9) */
#define SAMPLES_PER_REPORT  4U
/* Review P7: a TX that keeps failing must not look healthy. Above this many failures in a row,
 * of journal appends (tx_node.journal_fails) or of transmissions (tx_counts.air), the watchdog
 * resets the board (which re-runs Radio.Init). Minutes the policy chose not to send never count. */
#define TX_FAIL_LIMIT       10U
/* A storage failure at boot may be transient: retry once by a reset after 10 minutes. */
#define BOOT_RETRY_MS       (10UL * 60000UL)

tx_node_t tx_node;
static UTIL_TIMER_Object_t sample_timer, boot_retry_timer;
static uint32_t last_sample_s;   /* watchdog progress evidence */

/* The minute's 15-s samples (PRD section 9: coverage, mean and extrema). */
static ws_th_window th_window;
static unsigned th_ticks;
static int sensor_reported;   /* the first reading after boot is printed as #sensor */

void sampling_stop(void)
{
  tx_node.running = 0;
  UTIL_TIMER_Stop(&sample_timer);
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

/* What this minute may send, if anything: the live reading (NULL if its journal append failed)
   and the backlog the policy allows. A refused minute's reading stays journaled. */
static void minute_send(const jref_t *live)
{
  int backlog = policy_minute_backlog();
  if (backlog >= 0) exchange_start(live, (unsigned)backlog);
}

/* The minute's report, from its samples: journaled, then sent as the policy allows. */
static void minute_report(int src)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t live;
  int16_t t = 0; uint16_t h = 0;
  int valid = ws_th_mean_t(&th_window, &t) && ws_th_mean_h(&th_window, &h);
  uint32_t utc = time_utc();
  uint32_t uptime = clock_s() - tx_node.boot_s; /* always sent: the gateway reconstructs time from it */
  if (!valid) tx_node.sensor_faults++;
  /* static: minute_report() runs only from the sequencer, never re-entered, and it is on the deepest
     callback chain, which tools/stack_report.py counts four times (a 104-byte record cost ~416 B). */
  static ws_obs_t o;
  o = (ws_obs_t){ .epoch = tx_node.boot_epoch, .seq = tx_node.next_seq, .utc = utc, .uptime = uptime,
                  .energy = (uint8_t)energy_state(), .bitmap = WS_NODE_FIELDS };
  obs_codes(&o, valid, t, h);
  unsigned samples = th_window.n;
  ws_th_reset(&th_window);
  int rc = ws_obs_encode(&o, plain, sizeof plain) == (int)WS_OBS_PLAIN_MAX ? store_journal_append(plain, &live) : -3;
  ws_failrun_note(&tx_node.journal_fails, rc == 0);
  APP_PRINTF("#sample epoch=%u seq=%u uptime=%u valid=%d rc=%d n=%u t=%d rh=%u time=%s utc=%u journal=%s pending=%u lost=%u\n",
             (unsigned)tx_node.boot_epoch, (unsigned)tx_node.next_seq, (unsigned)uptime, valid, src, samples, valid ? t : 0,
             valid ? h : 0, utc ? "synchronized" : "unknown", (unsigned)utc, rc ? "ERROR" : "ok",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost());
  tx_node.next_seq++; /* identity is never reused, even if the journal write failed */
  if (exchange_busy()) { APP_PRINTF("#busy previous exchange still running\n"); return; }
  minute_send(rc ? NULL : &live);
}

static void sampled(int src, int16_t t, uint16_t h)
{
  if (tx_node.rebooting || tx_node.storming) return;   /* a measurement that finishes after either stops sampling */
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

/* Every 15 s: start a measurement; sampled() gets its result from the sensor task ~10 ms later. */
static void sample(void)
{
  last_sample_s = clock_s();
  if (sensor_start(sampled)) sampled(-1, 0, 0);   /* the previous one never finished: a missed sample */
}
BUSYMON_TASK(sample)

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }

/* Watchdog health: real progress, not just a running main loop (failure-modes.md G1). */
static int tx_healthy(void)
{
  uint32_t now = clock_s();
  if (!tx_node.running) return 1;                             /* not sampling by design */
  if (now - last_sample_s > 150) return 0;                    /* sampling stopped */
  if (exchange_overdue(now)) return 0;                        /* radio exchange stuck */
  if (ws_failrun_tripped(&tx_node.journal_fails, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u journal failures in a row\n", (unsigned)tx_node.journal_fails.n); return 0; }
  if (ws_failrun_tripped(&tx_counts.air, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u transmit failures in a row\n", (unsigned)tx_counts.air.n); return 0; }
  return 1;
}

static void on_boot_retry(void *ctx) { (void)ctx; NVIC_SystemReset(); }

/* Never for an unprovisioned board or a failed self-test: those need an operator, not a reset. */
static void boot_retry(void)
{
  if (!tx_node.kat_ok) return;
  APP_PRINTF("#boot-retry: reset in %u s\n", (unsigned)(BOOT_RETRY_MS / 1000));
  UTIL_TIMER_Create(&boot_retry_timer, BOOT_RETRY_MS, UTIL_TIMER_ONESHOT, on_boot_retry, NULL);
  UTIL_TIMER_Start(&boot_retry_timer);
}

/* Storage, key, self-test and a durable epoch: 1 if the node may sample and transmit. */
static int boot_ready(void)
{
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); boot_retry(); return 0; }
  uint32_t scrubbed = store_journal_scrub(STORM_EPOCH);
  if (scrubbed) APP_PRINTF("#storm-scrub dropped=%u (test slots a power cut left pending)\n", (unsigned)scrubbed);
  tx_node.provisioned = store_config_load(&tx_node.station, tx_node.key, tx_node.kcv) == 0;
  if (!tx_node.provisioned) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return 0; }
  time_restore();
  if (!tx_node.kat_ok) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return 0; }
  /* Durable epoch before the first sample: observation identities never repeat. */
  if (store_next_epoch(&tx_node.boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); boot_retry(); return 0; }
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

  tx_node.boot_s = clock_s();
  policy_init();
  watchdog_start(tx_healthy);
  tx_node.kat_ok = selftest_kat();
  APP_PRINTF("#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             watchdog_reset_cause(), tx_node.kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  if (!boot_ready()) return;
  sensor_init();
  tx_node.running = 1;
  last_sample_s = clock_s();
  tx_status();
  UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
