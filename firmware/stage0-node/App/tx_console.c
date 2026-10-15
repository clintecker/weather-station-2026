#include "tx_console.h"
#include <string.h>
#include "bench.h"
#include "busymon.h"
#include "clock.h"
#include "console.h"
#include "node_store.h"
#include "selftest.h"
#include "stackmon.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "sys_app.h"
#include "tx_exchange.h"
#include "tx_node.h"
#include "tx_policy.h"
#include "tx_time.h"
#include "utilities_def.h"
#include "watchdog.h"
#include "ws_obs.h"
#include "ws_policy.h"

#define REBOOT_DELAY_MS 200U   /* a commanded reboot lets the console finish its line first */
static UTIL_TIMER_Object_t reboot_timer;

/* Decimal text of a 64-bit counter: the console's tiny_vsnprintf has no 64-bit format, and a
   (unsigned) cast printed only the low 32 bits. */
static const char *u64_text(uint64_t v, char buf[21])
{
  char *p = buf + 20; *p = 0;
  do { *--p = (char)('0' + (int)(v % 10U)); v /= 10U; } while (v);
  return p;
}

/* Separate lines: one long line was once cut off at the old 256-byte print buffer (now 640) and
 * used to be cut off mid-field. #status keeps the fields provision-node and the gateway parse. */
static void status_line(void)
{
  char ctr_buf[21];
  const tx_node_t *n = &tx_node;
  APP_PRINTF("#status role=tx fw=%s reset=%s provisioned=%d station=%u kcv=%02x%02x%02x kat=%s epoch=%u next_seq=%u "
             "ctr=%s ecc=%u link=%s silent=%u energy=%s time=%s utc=%u uptime=%u\n",
             WS_FW_VERSION, watchdog_reset_cause(), n->provisioned, (unsigned)n->station, n->kcv[0], n->kcv[1], n->kcv[2],
             n->kat_ok ? "pass" : "FAIL", (unsigned)n->boot_epoch, (unsigned)n->next_seq,
             u64_text(store_counter_next(), ctr_buf), (unsigned)store_ecc_faults(),
             policy_probing() ? "probing" : "linked", (unsigned)policy_silent_minutes(), ws_energy_name(energy_state()),
             time_valid() ? "synchronized" : "unknown", (unsigned)time_utc(), (unsigned)(clock_s() - n->boot_s));
}

static void counts_line(void)
{
  const tx_counts_t *c = &tx_counts;
  APP_PRINTF("#counts pending=%u lost=%u burned=%u abandoned=%u sent=%u acked=%u no_ack=%u ack_rejects=%u "
             "sensor_faults=%u tx_fail_run=%u tx_air_run=%u stack_peak=%u\n",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost(),
             (unsigned)store_journal_burned(), (unsigned)store_abandoned_total(), (unsigned)c->sent, (unsigned)c->acked,
             (unsigned)c->no_ack, (unsigned)c->ack_rejects, (unsigned)tx_node.sensor_faults,
             (unsigned)tx_node.journal_fails.n, (unsigned)c->air.n, (unsigned)stackmon_peak());
}

static void timing_line(void)
{
  APP_PRINTF("#timing state=%s task_peak_us=%u task_peak=%s isr_peak_us=%u isr_peak=%s erase_peak_us=%u prog_peak_us=%u "
             "trace_drops=%u unexpected=%u\n", exchange_state_name(),
             (unsigned)busymon_peak_us(BM_TASK), busymon_peak_name(BM_TASK), (unsigned)busymon_peak_us(BM_ISR),
             busymon_peak_name(BM_ISR), (unsigned)busymon_peak_us(BM_ERASE), (unsigned)busymon_peak_us(BM_PROG),
             (unsigned)ws_trace_drops, (unsigned)tx_counts.unexpected);
}

void tx_status(void) { status_line(); counts_line(); timing_line(); }

/* A commanded reboot: sampling stops now, the reset comes from a timer once the console has had
   REBOOT_DELAY_MS to send the reply line. */
static void on_reboot(void *ctx) { (void)ctx; NVIC_SystemReset(); }
static void reboot_soon(void)
{
  if (tx_node.rebooting) return;
  tx_node.rebooting = 1;
  sampling_stop();
  UTIL_TIMER_Start(&reboot_timer);
}

/* Bench-only power-cut test load (gap G7). Writes journal slots that are acknowledged on the
 * board at once (epoch STORM_EPOCH, never transmitted) and reserves counters, so that a
 * random power cut almost always lands inside a flash program or erase. Not persistent: a
 * reboot ends it, and the boot scrub drops any storm slot that a cut left pending. */
static uint32_t storm_writes;
static void storm(void)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t r; uint64_t c;
  if (!tx_node.storming) return;
  for (int i = 0; i < 16; i++)
  {
    ws_obs_t o = { .epoch = STORM_EPOCH, .seq = storm_writes++, .energy = WS_ENERGY_NORMAL, .bitmap = WS_NODE_FIELDS };
    for (unsigned f = 0; f < WS_FI_COUNT; f++) o.code[f] = ws_obs_invalid(f);
    (void)ws_obs_encode(&o, plain, sizeof plain);
    if (store_journal_append(plain, &r) == 0) store_journal_ack(r);
    for (int k = 0; k < 4; k++) store_next_counter(&c);
  }
  if ((storm_writes & 255) == 0)
    { char ctr_buf[21];
      APP_PRINTF("#storm writes=%u ctr=%s burned=%u\n", (unsigned)storm_writes,
                 u64_text(store_counter_next(), ctr_buf), (unsigned)store_journal_burned()); }
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Storm, CFG_SEQ_Prio_0);
}
BUSYMON_TASK(storm)

static void storm_start(void)
{
  char ctr_buf[21];
  APP_PRINTF("#storm start ctr=%s (bench only: cut power now)\n", u64_text(store_counter_next(), ctr_buf));
  /* Sampling stops, so no exchange starts; the watchdog must not count a stopped sampler. */
  tx_node.storming = 1;
  sampling_stop();
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Storm, CFG_SEQ_Prio_0);
}

#define PROVISION_ARGS (sizeof "PROVISION " - 1U)
static void provision(char *line)
{
  uint8_t new_key[16], check[3]; uint32_t id, floor; int rc, done = 0;
  if (tx_node.provisioned) { APP_PRINTF("#error already-provisioned (WIPE first)\n"); }
  else if (ws_parse_provision(line + PROVISION_ARGS, &id, new_key, &floor))
  { APP_PRINTF("#error usage: PROVISION <station_id> <32 hex key> [epoch_floor]\n"); }
  else if (floor && store_epoch_floor(floor)) { APP_PRINTF("#error epoch-floor\n"); }
  else if ((rc = store_config_write(id, new_key, check)) != 0) { APP_PRINTF("#error provision rc=%d\n", rc); }
  else
  {
    APP_PRINTF("#provisioned station=%u kcv=%02x%02x%02x epoch_floor=%u\n", (unsigned)id, check[0], check[1], check[2], (unsigned)floor);
    done = 1;
  }
  ws_wipe(new_key, sizeof new_key); ws_wipe(line, strlen(line)); /* the key never lingers in RAM */
  if (done) reboot_soon();
}

/* From CMD_STORM on, a command writes flash: never during a radio exchange or a pending reboot
   (flash is only written with the radio idle, docs/firmware-event-model.md); the operator retries. */
enum { CMD_STATUS, CMD_KAT, CMD_STORM, CMD_WIPE, CMD_PROVISION, CMD_COUNT };
static const char *const command[CMD_COUNT] = { "STATUS", "KAT", "TEST-FLASH-STORM", "WIPE ERASE-ALL-NODE-STATE", "PROVISION " };

static int refused(int cmd, char *line)
{
  if (cmd < CMD_STORM || !(exchange_busy() || tx_node.rebooting)) return 0;
  ws_wipe(line, strlen(line));   /* a refused PROVISION's key does not linger either */
  APP_PRINTF("#error busy (radio exchange or reboot in progress); retry\n");
  return 1;
}

static void on_line(char *line)
{
  bench_command(line);   /* TEST-FAULT, TEST-HANG (not in a field build) */
  int cmd = ws_cmd_find(command, CMD_COUNT, line);
  if (refused(cmd, line)) return;
  switch (cmd)
  {
    case CMD_STATUS: tx_status(); break;
    case CMD_KAT: APP_PRINTF("#kat %s\n", selftest_kat() ? "pass" : "FAIL"); break;
    case CMD_STORM: storm_start(); break;
    case CMD_WIPE: APP_PRINTF("#wipe %s\n", store_wipe() ? "ERROR" : "ok"); reboot_soon(); break;
    case CMD_PROVISION: provision(line); break;
    default: APP_PRINTF("#error unknown command\n"); break;
  }
}

void tx_console_init(void)
{
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Storm, UTIL_SEQ_RFU, storm_timed);
  UTIL_TIMER_Create(&reboot_timer, REBOOT_DELAY_MS, UTIL_TIMER_ONESHOT, on_reboot, NULL);
  console_init(on_line);
}
