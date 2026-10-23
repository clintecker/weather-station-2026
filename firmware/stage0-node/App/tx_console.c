#define WS_CHECK_FILE 4
#include "tx_console.h"
#include <string.h>
#include "bench.h"
#include "busymon.h"
#include "clock.h"
#include "console.h"
#include "node_store.h"
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
#include "ws_check.h"
#include "mod_rain.h"
#include "wsmp_host.h"
#include "ws_obs.h"
#include "ws_policy.h"

#define REBOOT_DELAY_MS 200U   /* a commanded reboot lets the console finish its line first */
static UTIL_TIMER_Object_t reboot_timer;

/* Decimal text of a 64-bit counter: the console's tiny_vsnprintf has no 64-bit format, and a
   (unsigned) cast printed only the low 32 bits. */
#define U64_DIGITS 20   /* 2^64 - 1 has 20 decimal digits */
static const char *u64_text(uint64_t v, char buf[U64_DIGITS + 1])
{
  char *p = buf + U64_DIGITS; *p = 0;
  do { *--p = (char)('0' + (int)(v % 10U)); v /= 10U; } while (v);   /* bound: U64_DIGITS digits */
  return p;
}

/* Separate lines: one long line was once cut off at the old 256-byte print buffer (now 640) and
 * used to be cut off mid-field. #status keeps the fields provision-node and the gateway parse. */
static void status_line(void)
{
  char ctr_buf[U64_DIGITS + 1], kcv[WS_HEX_PER_BYTE * WS_KCV_LEN + 1];
  const tx_identity_t *id = exchange_identity();
  const tx_node_t *n = node_state();
  ws_hex_text(id->kcv, WS_KCV_LEN, kcv);
  APP_PRINTF("#status role=tx fw=%s reset=%s provisioned=%d station=%u kcv=%s kat=%s epoch=%u next_seq=%u "
             "ctr=%s ecc=%u link=%s silent=%u energy=%s time=%s utc=%u uptime=%u\n",
             WS_FW_VERSION, watchdog_reset_cause(), id->provisioned, (unsigned)id->station, kcv,
             n->kat_ok ? "pass" : "FAIL", (unsigned)n->boot_epoch, (unsigned)n->next_seq,
             u64_text(store_counter_next(), ctr_buf), (unsigned)store_ecc_faults(),
             policy_probing() ? "probing" : "linked", (unsigned)policy_silent_minutes(), ws_energy_name(energy_state()),
             time_valid() ? "synchronized" : "unknown", (unsigned)time_utc(), (unsigned)node_uptime_s());
}

static void counts_line(void)
{
  const tx_counts_t *c = exchange_counts();
  const tx_node_t *n = node_state();
  uint16_t site = ws_check_first();
  APP_PRINTF("#counts pending=%u lost=%u burned=%u abandoned=%u sent=%u acked=%u no_ack=%u ack_rejects=%u "
             "sensor_faults=%u held_lost=%u tx_fail_run=%u tx_air_run=%u stack_peak=%u check_fails=%u check_first=%u:%u\n",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost(),
             (unsigned)store_journal_burned(), (unsigned)store_abandoned_total(), (unsigned)c->sent, (unsigned)c->acked,
             (unsigned)c->no_ack, (unsigned)c->ack_rejects, (unsigned)n->sensor_faults, (unsigned)n->held_lost,
             (unsigned)n->journal_fails.n, (unsigned)c->air.n, (unsigned)stackmon_peak(), (unsigned)ws_check_count(),
             ws_check_site_file(site), ws_check_site_line(site));
}

static void timing_line(void)
{
  APP_PRINTF("#timing state=%s task_peak_us=%u task_peak=%s task_wall_us=%u isr_peak_us=%u isr_peak=%s erase_peak_us=%u "
             "prog_peak_us=%u trace_drops=%u unexpected=%u\n", exchange_state_name(),
             (unsigned)busymon_peak_us(BM_TASK), busymon_peak_name(BM_TASK), (unsigned)busymon_peak_us(BM_TASK_WALL),
             (unsigned)busymon_peak_us(BM_ISR),
             busymon_peak_name(BM_ISR), (unsigned)busymon_peak_us(BM_ERASE), (unsigned)busymon_peak_us(BM_PROG),
             (unsigned)ws_trace_drops, (unsigned)exchange_counts()->unexpected);
}

void tx_status(void) { status_line(); counts_line(); timing_line(); }

/* A commanded reboot: sampling stops now, the reset comes from a timer once the console has had
   REBOOT_DELAY_MS to send the reply line. */
static void on_reboot(void *ctx) { (void)ctx; NVIC_SystemReset(); }
static int rebooting;   /* a commanded reboot is pending */
static void reboot_soon(void)
{
  if (rebooting) return;
  rebooting = 1;
  sampling_stop();
  /* Refused only if already running, which rebooting excludes; should it be, reset now (the reply
     line may be cut short). */
  if (!WS_CHECK(UTIL_TIMER_Start(&reboot_timer) == UTIL_TIMER_OK)) NVIC_SystemReset();
}

/* Bench-only power-cut test load. Writes journal slots that are acknowledged on the
 * board at once (epoch STORM_EPOCH, never transmitted) and reserves counters, so that a
 * random power cut almost always lands inside a flash program or erase. Not persistent: a
 * reboot ends it, and the boot scrub drops any storm slot that a cut left pending. */
static uint32_t storm_writes;
static int storming;   /* sampling stopped for the load */
/* At most this many slots per boot (~30 s): enough for a power cut to land in a write, far from
   wearing out the journal (70 pages, 10 k erase cycles each). */
#define STORM_MAX_WRITES 24000U
#define STORM_WRITES_PER_PASS 16U      /* journal writes per task pass */
#define STORM_COUNTERS_PER_WRITE 4U   /* counter reservations per write: meta-log appends too */
#define STORM_REPORT_EVERY 256U       /* writes between #storm lines */
static void storm(void)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t r; uint64_t c;
  if (!storming) return;
  /* At the cap the load stops; sampling stays stopped until the reboot that ends a storm. */
  if (storm_writes >= STORM_MAX_WRITES) { APP_PRINTF("#storm done writes=%u (cap; reboot to resume)\n", (unsigned)storm_writes); return; }
  for (unsigned i = 0; i < STORM_WRITES_PER_PASS; i++)
  {
    ws_obs_t o = { .epoch = STORM_EPOCH, .seq = storm_writes++, .energy = WS_ENERGY_NORMAL, .bitmap = WS_NODE_FIELDS };
    for (unsigned f = 0; f < WS_FI_COUNT; f++) o.code[f] = ws_obs_invalid(f);
    (void)ws_obs_encode(&o, plain, sizeof plain);
    /* A load, not data: a failed write or reservation is simply one less flash operation. */
    if (store_journal_append(plain, &r) == 0) (void)store_journal_ack(r);
    for (unsigned k = 0; k < STORM_COUNTERS_PER_WRITE; k++) (void)store_next_counter(&c);
  }
  if (storm_writes % STORM_REPORT_EVERY == 0)
    { char ctr_buf[U64_DIGITS + 1];
      APP_PRINTF("#storm writes=%u ctr=%s burned=%u\n", (unsigned)storm_writes,
                 u64_text(store_counter_next(), ctr_buf), (unsigned)store_journal_burned()); }
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Storm, CFG_SEQ_Prio_0);
}
BUSYMON_TASK(storm)

static void storm_start(void)
{
  char ctr_buf[U64_DIGITS + 1];
  APP_PRINTF("#storm start ctr=%s (bench only: cut power now)\n", u64_text(store_counter_next(), ctr_buf));
  /* Sampling stops, so no exchange starts; the watchdog must not count a stopped sampler. */
  storming = 1;
  sampling_stop();
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Storm, CFG_SEQ_Prio_0);
}

#define PROVISION_ARGS (sizeof "PROVISION " - 1U)
static void provision(char *line)
{
  uint8_t new_key[WS_KEY_LEN], check[WS_KCV_LEN]; uint32_t id, floor; int rc, done = 0;
  if (exchange_identity()->provisioned) { APP_PRINTF("#error already-provisioned (WIPE first)\n"); }
  /* Pending records belong to an old key or an old flash layout: a new key must start empty. */
  else if (store_journal_pending()) { APP_PRINTF("#error journal-not-empty (WIPE first)\n"); }
  else if (ws_parse_provision(line + PROVISION_ARGS, &id, new_key, &floor))
  { APP_PRINTF("#error usage: PROVISION <station_id> <32 hex key> [epoch_floor]\n"); }
  else if (floor && store_epoch_floor(floor)) { APP_PRINTF("#error epoch-floor\n"); }
  else if ((rc = store_config_write(id, new_key, check)) != 0) { APP_PRINTF("#error provision rc=%d\n", rc); }
  else
  {
    char kcv[WS_HEX_PER_BYTE * WS_KCV_LEN + 1];
    ws_hex_text(check, WS_KCV_LEN, kcv);
    APP_PRINTF("#provisioned station=%u kcv=%s epoch_floor=%u\n", (unsigned)id, kcv, (unsigned)floor);
    done = 1;
  }
  ws_wipe(new_key, sizeof new_key); ws_wipe(line, strlen(line)); /* the key never lingers in RAM */
  if (done) reboot_soon();
}

/* From CMD_STORM on, a command writes flash: never during a radio exchange or a pending reboot
   (flash is only written with the radio idle, docs/firmware-event-model.md); the operator retries. */
enum { CMD_STATUS, CMD_KAT, CMD_MODULES, CMD_STORM, CMD_WIPE, CMD_PROVISION, CMD_RAIN_ON, CMD_RAIN_OFF, CMD_COUNT };
static const char *const command[CMD_COUNT] = { "STATUS", "KAT", "MODULES", "TEST-FLASH-STORM", "WIPE ERASE-ALL-NODE-STATE",
                                                "PROVISION ", "SENSOR rain on", "SENSOR rain off" };

/* SENSOR rain on|off: the rain gauge cannot be detected, so the operator sets it (WSMP-P1). The node
   stores the setting and applies it at once; the station host admits the module after two probes. */
static void rain_setting(int on)
{
  int rc = store_rain_set(on);
  if (rc) { APP_PRINTF("#error sensor rc=%d\n", rc); return; }
  mod_rain_set_enabled(on);
  APP_PRINTF("#sensor rain=%s\n", on ? "on" : "off");
}

static void modules_line(void)
{
  static char line[WSMP_MODULES_LINE_MAX];   /* static: off the stack; only the console task prints it */
  (void)wsmp_host_modules_line(line, sizeof line);
  APP_PRINTF("%s\n", line);
}

static int refused(int cmd, char *line)
{
  if (cmd < CMD_STORM || !(exchange_busy() || rebooting)) return 0;
  ws_wipe(line, strlen(line));   /* a refused PROVISION's key does not linger either */
  APP_PRINTF("#error busy (radio exchange or reboot in progress); retry\n");
  return 1;
}

/* The commands that only read (before CMD_STORM in the table). */
static void read_command(int cmd)
{
  switch (cmd)
  {
    case CMD_STATUS: tx_status(); break;
    case CMD_KAT: APP_PRINTF("#kat %s\n", node_selftest() ? "pass" : "FAIL"); break;
    case CMD_MODULES: modules_line(); break;
    default: APP_PRINTF("#error unknown command\n"); break;
  }
}

/* The commands that write flash (from CMD_STORM on): refused() already kept them off a busy radio. */
static void flash_command(int cmd, char *line)
{
  switch (cmd)
  {
#ifndef WS_FIELD_BUILD   /* bench only: a field image has no flash write load */
    case CMD_STORM: storm_start(); break;
#endif
    case CMD_WIPE: APP_PRINTF("#wipe %s\n", store_wipe() ? "ERROR" : "ok"); reboot_soon(); break;
    case CMD_PROVISION: provision(line); break;
    case CMD_RAIN_ON: case CMD_RAIN_OFF: rain_setting(cmd == CMD_RAIN_ON); break;
    default: APP_PRINTF("#error unknown command\n"); break;
  }
}

void console_line(char *line)
{
  bench_command(line);   /* TEST-FAULT, TEST-HANG (not in a field build) */
  int cmd = ws_cmd_find(command, CMD_COUNT, line);
  if (refused(cmd, line)) return;
  if (cmd < CMD_STORM) read_command(cmd);
  else flash_command(cmd, line);
}

void tx_console_init(void)
{
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Storm, UTIL_SEQ_RFU, storm_timed);
  (void)UTIL_TIMER_Create(&reboot_timer, REBOOT_DELAY_MS, UTIL_TIMER_ONESHOT, on_reboot, NULL);
  console_init();
}
