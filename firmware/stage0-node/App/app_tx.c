/* Stage-0 TX: one SHT45 observation per minute, journaled in flash before transmission and
 * retained until an authenticated host ACK (or a NACK / strike-limit abandon). Each minute sends
 * the live observation first, then older pending ones as the energy and link policy allows
 * (docs/radio-energy-policy.md); each frame gets a fresh durably reserved counter and one ACK
 * receive window. Time comes only from an ACK that echoes the counter of the frame just sent
 * (replayed ACKs cannot move the clock). Console lines from this board start with '#';
 * commands: STATUS, KAT, PROVISION <station_id> <32 hex key> [epoch_floor],
 * WIPE ERASE-ALL-NODE-STATE, TEST-HANG, TEST-FAULT, TEST-FLASH-STORM (firmware/stage0-node/README.md). */
#include <stdlib.h>
#include <string.h>
#include "console.h"
#include "leds.h"
#include "watchdog.h"
#include "node_store.h"
#include "radio.h"
#include "radio_cfg.h"
#include "rtc.h"
#include "sensor.h"
#include "stackmon.h"
#include "fault.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32wlxx_hal.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"
#include "ws_frame.h"

#define SAMPLE_PERIOD_MS    15000U  /* one T/RH sample; every SAMPLES_PER_REPORT-th builds the minute (PRD 9) */
#define SAMPLES_PER_REPORT  4U
#define ACK_WINDOW_MS       2000U
#define MIN_RELISTEN_MS     50U     /* less window left than this after a stray packet: give up */
#define INTER_FRAME_MS      50U
#define MAX_QUEUE           21U   /* live + up to 20 backlog (SURPLUS at SF7); RAM 84 B */

/* Transmission policy (docs/radio-energy-policy.md, approved 2026-10-12; gap G13).
 * Energy state: Stage 0 is USB powered, so it is fixed at NORMAL; Stage 1 feeds pack/charger/
 * solar telemetry into energy_state(). Unknown energy must map to CONSERVE (fail closed). */
typedef enum { EN_SURPLUS, EN_NORMAL, EN_CONSERVE, EN_CRITICAL, EN_COUNT } energy_t;
/* The observation's energy-state bits use this numbering (docs/protocol-draft5-design.md 5.2). */
_Static_assert((int)EN_SURPLUS == (int)WS_ENERGY_SURPLUS && (int)EN_NORMAL == (int)WS_ENERGY_NORMAL && (int)EN_CONSERVE == (int)WS_ENERGY_CONSERVE &&
               (int)EN_CRITICAL == (int)WS_ENERGY_CRITICAL, "energy_t matches the wire codes");
#define BACKLOG_SURPLUS 20U                                          /* the largest per-minute backlog */
static const char *const energy_name[] = { "surplus", "normal", "conserve", "critical" };
static const uint8_t backlog_limit[] = { BACKLOG_SURPLUS, 5, 0, 0 }; /* per minute */
static const uint16_t airtime_cap_ms[] = { 15000, 5000, 2000, 0 };   /* radio time per minute */
_Static_assert(sizeof energy_name / sizeof energy_name[0] == EN_COUNT &&
               sizeof backlog_limit == EN_COUNT && sizeof airtime_cap_ms / sizeof airtime_cap_ms[0] == EN_COUNT,
               "one entry per energy state");
_Static_assert(BACKLOG_SURPLUS <= MAX_QUEUE - 1U, "the send queue holds the live reading plus the largest backlog");
#define CONSERVE_INTERVAL_S 300U                                     /* spec R02 */
static energy_t energy_state(void) { return EN_NORMAL; }

/* Link state: K silent minutes -> PROBING: live reading only, no backlog. With healthy energy
 * (SURPLUS, NORMAL) the live reading still goes every minute, so the node relinks within a
 * minute and an outage adds no late readings; only CONSERVE backs off 2, 4, 8, then 15 min
 * (ws_link_may_send in firmware/stage0.c, host-tested). */
#define LINK_K_SILENT       3U
static const uint16_t probe_interval_s[] = { 120, 240, 480, 900 };
#define TURNAROUND_MS       300U   /* gateway commit (fullfsync) + USB both ways, conservative */
#define SYNC_VALID_S        (6UL * 3600UL)          /* trust a sync for 6 h (LSE drift; see gateway DRIFT_PPM) */
/* Option D: time trust survives a system reset (NRST, software, watchdog) through two RTC
 * backup registers. A power loss clears the backup domain, so trust is lost, as it must be.
 * DR0-DR2 belong to ST's timer_if/SysTime. */
#define BKP_TIME_MAGIC      0x57535456UL            /* "WSTV" */
#define BKP_REG_MAGIC       RTC_BKP_DR3
#define BKP_REG_SYNC_MCU    RTC_BKP_DR4
#define MIN_PLAUSIBLE_UTC   1767225600ULL           /* 2026-01-01T00:00:00Z */

/* Draft-5 known-answer vectors, shared with tests/test_frame.py. They were made directly with the
 * cryptography library's AESCCM from the spec's header and nonce, not by ws0/protocol.py. */
static const uint8_t KAT_KEY[16] = { 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 };
/* Observation: the encoder's own known answer (tests/test_obs.py KAT: T -12.34 C, RH 45.67 %, epoch 1,
 * seq 2, UTC 1791991189, uptime 300 s, NORMAL), sealed with counter 0x100000002. */
static const char KAT_OBS_HEX[] = "5100010100000002bd50c6be3400a750d40cca5aadad57b716f16658a09d968acf9a212d7f2e95a5e34f";
static const char KAT_ACK_HEX[] = "52000100000000050e1eb4544766f4e6e0ffdbb3f6d1413d06f6369500199b8fe2";
static const char KAT_NACK_HEX[] = "5300010000000006849addbf88d9aadd884aa3bb89136575374521c5e416a1d0c9";
#define KAT_OBS_PLAIN_LEN WS_OBS_PLAIN_LEN(WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT)
#define KAT_OBS_FRAME_LEN (KAT_OBS_PLAIN_LEN + WS_FRAME_OVERHEAD)
#define OBS_FRAME_MAX (WS_OBS_PLAIN_MAX + WS_FRAME_OVERHEAD)

static RadioEvents_t events;
static UTIL_TIMER_Object_t sample_timer;
static uint32_t station;
static uint8_t key[16];
static uint8_t kcv[3];
static int provisioned, kat_ok, running;
static uint32_t boot_epoch, next_seq;
static int synced;
static uint32_t last_sync_mcu;   /* RTC (MCU) seconds at the last accepted time sync */
static uint32_t boot_mcu;        /* RTC (MCU) seconds at boot: uptime origin */
static uint32_t last_sample_mcu, exchange_start_mcu; /* watchdog progress evidence */

static jref_t queue[MAX_QUEUE];
static unsigned qn, qi;
static int busy;
static uint64_t sent_counter;
static uint32_t sent_epoch, sent_seq;
static uint32_t n_sent, n_acked, n_no_ack, n_ack_rejects, n_sensor_faults;
/* Gap G2 safety net: a record that stays unanswered while other frames in the same exchange are
 * answered (the gateway is up) gets a strike; at STRIKE_LIMIT it is abandoned and counted. */
#define STRIKE_LIMIT 10
#define STRIKE_SLOTS 6
/* Keyed by the record's identity, not its journal slot: a slot is reused after the ring wraps, and
 * a record can leave the journal (an ACK that was not for the frame just sent, a ring loss)
 * without its slot's entry being cleared (firmware review finding 5). */
static struct { uint32_t epoch, seq; uint8_t n; } strikes[STRIKE_SLOTS];
static uint8_t replied[MAX_QUEUE];
static enum { LINK_LINKED, LINK_PROBING } link_state = LINK_LINKED;
static uint32_t silent_minutes, probe_step, next_probe_mcu, last_send_mcu;
static uint32_t exchange_ms; /* estimated radio time of one answered exchange */
/* Review P7: a TX that keeps failing must not look healthy. Two runs of uninterrupted failures;
 * above the limit on either, the watchdog resets the board (which re-runs Radio.Init).
 *  - tx_fail: the minute's journal append.
 *  - tx_air: transmissions. A failure is a refused counter reservation, a refused Radio.Send or a
 *    TxTimeout; only a TxDone (the frame really left) clears it. Before 2026-10-14 one run mixed
 *    both and every successful append or accepted Send reset it, so a radio that accepted Send but
 *    never finished a frame was never reset (firmware review, finding 1).
 * Minutes the policy chose not to send never count. */
#define TX_FAIL_LIMIT 10U
static ws_failrun tx_fail, tx_air;
/* A storage failure at boot may be transient: retry once by a reset after 10 minutes. */
#define BOOT_RETRY_MS (10UL * 60000UL)
static UTIL_TIMER_Object_t boot_retry_timer;

/* Health report (kind 4, gap G8): every 15 min and at each link-state change, sent after a
 * minute's exchange (also while probing, so the link field can read "probing").
 * Fire-and-forget: no journal entry, no receive window. */
#define DIAG_PERIOD_S 900U
static int diag_due = 1, diag_in_flight;
static uint32_t ack_window_end;   /* HAL_GetTick() at which the current ACK window closes */
static uint32_t last_diag_mcu;

static uint8_t rx_frame[255];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Signal of the last authentic ACK, as the node heard it (DIAG, design section 4): the uplink and
   downlink can differ (gap G15). -128 = none yet. */
static int8_t ack_rssi = -128, ack_snr = -128;
static volatile enum { EV_NONE, EV_TX_DONE, EV_TX_TIMEOUT, EV_RX_DONE, EV_RX_TIMEOUT, EV_RX_ERROR } event;

static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
/* RTC-based monotonic seconds; SysTimeSet() does not change it. */
static uint32_t mcu_seconds(void) { return SysTimeGetMcuTime().Seconds; }
static int time_valid(void) { return synced && (mcu_seconds() - last_sync_mcu) < SYNC_VALID_S; }

/* Option D: restore time trust after a reset if the RTC kept counting and the sync is recent. */
static void restore_time_trust(void)
{
  uint32_t magic = HAL_RTCEx_BKUPRead(&hrtc, BKP_REG_MAGIC);
  uint32_t at = HAL_RTCEx_BKUPRead(&hrtc, BKP_REG_SYNC_MCU);
  uint32_t now = mcu_seconds();
  if (magic == BKP_TIME_MAGIC && now >= at && now - at < SYNC_VALID_S && SysTimeGet().Seconds >= MIN_PLAUSIBLE_UTC)
  {
    synced = 1;
    last_sync_mcu = at;
    APP_PRINTF("#time restored utc=%u sync_age=%u\n", (unsigned)SysTimeGet().Seconds, (unsigned)(now - at));
  }
  else
  {
    HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_MAGIC, 0);
  }
}

static int run_kat(void)
{
  uint8_t plain[KAT_OBS_PLAIN_LEN], frame[KAT_OBS_FRAME_LEN], expect[KAT_OBS_FRAME_LEN], ack[WS_ACK_FRAME_LEN];
  uint64_t ctr, echo; uint32_t ep, sq, word; uint8_t kind;
  ws_obs_t o = { .epoch = 1, .seq = 2, .utc = 1791991189UL, .uptime = 300, .energy = WS_ENERGY_NORMAL,
                 .bitmap = WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT };
  o.code[WS_FI_TEMPERATURE_C] = ws_code_temp_centi(-1234);
  o.code[WS_FI_HUMIDITY_PCT] = ws_code_rh_centi(4567);
  if (ws_obs_encode(&o, plain, sizeof plain) != (int)sizeof plain) return 0;
  if (ws_hex_decode(KAT_OBS_HEX, expect, sizeof expect) != KAT_OBS_FRAME_LEN) return 0;
  if (ws_seal_kind(KAT_KEY, 1, WS_KIND_OBS, 0x100000002ULL, plain, sizeof plain, frame, sizeof frame) != KAT_OBS_FRAME_LEN ||
      memcmp(frame, expect, sizeof frame)) return 0;
  if (ws_hex_decode(KAT_ACK_HEX, ack, sizeof ack) != WS_ACK_FRAME_LEN) return 0;
  if (ws_open_reply(KAT_KEY, 1, ack, sizeof ack, &kind, &ctr, &ep, &sq, &word, &echo)) return 0;
  if (kind != WS_KIND_ACK || ctr != 5 || ep != 17 || sq != 42 || word != 1760000000UL || echo != 0x100000002ULL) return 0;
  ack[sizeof ack - 1] ^= 1; /* tampered tag must fail */
  if (ws_open_reply(KAT_KEY, 1, ack, sizeof ack, &kind, &ctr, &ep, &sq, &word, &echo) == 0) return 0;
  if (ws_hex_decode(KAT_NACK_HEX, ack, sizeof ack) != WS_ACK_FRAME_LEN) return 0;
  if (ws_open_reply(KAT_KEY, 1, ack, sizeof ack, &kind, &ctr, &ep, &sq, &word, &echo)) return 0;
  /* The counter limit is part of the self-test: 2^40 must be refused, never truncated. */
  if (ws_seal_kind(KAT_KEY, 1, WS_KIND_OBS, WS_COUNTER_MAX + 1ULL, plain, sizeof plain, frame, sizeof frame) >= 0) return 0;
  return kind == WS_KIND_NACK && ctr == 6 && ep == 17 && sq == 42 && word == WS_NACK_COLLISION && echo == 0x100000002ULL;
}

/* Decimal text of a 64-bit counter: the console's tiny_vsnprintf has no 64-bit format, and a
   (unsigned) cast printed only the low 32 bits. */
static const char *u64_text(uint64_t v, char buf[21])
{
  char *p = buf + 20; *p = 0;
  do { *--p = (char)('0' + (int)(v % 10U)); v /= 10U; } while (v);
  return p;
}

static void status(void)
{
  char ctr_buf[21];
  /* Two lines: the console print buffer is 256 bytes (UTIL_ADV_TRACE_TMP_BUF_SIZE) and one line
   * used to be cut off mid-field. #status keeps the fields provision-node and the gateway parse. */
  APP_PRINTF("#status role=tx fw=%s reset=%s provisioned=%d station=%u kcv=%02x%02x%02x kat=%s epoch=%u next_seq=%u "
             "ctr=%s ecc=%u link=%s silent=%u energy=%s time=%s utc=%u uptime=%u\n",
             WS_FW_VERSION, watchdog_reset_cause(), provisioned, (unsigned)station, kcv[0], kcv[1], kcv[2], kat_ok ? "pass" : "FAIL",
             (unsigned)boot_epoch, (unsigned)next_seq, u64_text(store_counter_next(), ctr_buf), (unsigned)store_ecc_faults(),
             link_state == LINK_LINKED ? "linked" : "probing",
             (unsigned)silent_minutes, energy_name[energy_state()], time_valid() ? "synchronized" : "unknown",
             (unsigned)(time_valid() ? SysTimeGet().Seconds : 0), (unsigned)(mcu_seconds() - boot_mcu));
  APP_PRINTF("#counts pending=%u lost=%u burned=%u abandoned=%u sent=%u acked=%u no_ack=%u ack_rejects=%u "
             "sensor_faults=%u tx_fail_run=%u tx_air_run=%u stack_peak=%u\n",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost(),
             (unsigned)store_journal_burned(), (unsigned)store_abandoned_total(), (unsigned)n_sent, (unsigned)n_acked,
             (unsigned)n_no_ack, (unsigned)n_ack_rejects, (unsigned)n_sensor_faults, (unsigned)tx_fail.n, (unsigned)tx_air.n,
             (unsigned)stackmon_peak());
}

static void post(int ev) { event = ev; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0); }
static void on_tx_done(void) { post(EV_TX_DONE); }
static void on_tx_timeout(void) { post(EV_TX_TIMEOUT); }
static void on_rx_timeout(void) { post(EV_RX_TIMEOUT); }
static void on_rx_error(void) { post(EV_RX_ERROR); }
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX_DONE);
}

static void finish_exchange(void);

/* Send queue[qi]. A local failure (journal read, seal, radio busy) skips to the next item in this
 * loop, never by calling next_item(): no recursion, so the stack stays bounded (tools/stack_report.py).
 * Returns once a frame is on air (its TxDone or reply drives next_item) or the exchange is over. */
static void send_current(void)
{
  for (;;)
  {
    uint8_t plain[WS_OBS_PLAIN_MAX], frame[OBS_FRAME_MAX];
    int plen = -1;
    if (store_journal_read(queue[qi], plain) || (plen = ws_obs_plain_len(plain, sizeof plain)) < 0) { APP_PRINTF("#error journal-read\n"); }
    else
    {
      /* No durable counter reservation, no transmission (nonce reuse would break CCM). */
      if (store_next_counter(&sent_counter)) { ws_failrun_note(&tx_air, 0); APP_PRINTF("#error counter-reserve\n"); busy = 0; Radio.Sleep(); return; }
      int flen = ws_seal_kind(key, station, WS_KIND_OBS, sent_counter, plain, (uint32_t)plen, frame, sizeof frame);
      if (flen < 0) { APP_PRINTF("#error seal\n"); }
      else
      {
        sent_epoch = be32(plain);
        sent_seq = be32(plain + 4);
        n_sent++;
        led_flash(LED_BLUE, 400);
        if (Radio.Send(frame, (uint8_t)flen) == RADIO_STATUS_OK) return;  /* success is its TxDone */
        ws_failrun_note(&tx_air, 0); APP_PRINTF("#error radio-busy\n");
      }
    }
    if (++qi >= qn) { finish_exchange(); return; }
    HAL_Delay(INTER_FRAME_MS);
  }
}

/* Identity of a journaled record (its first 8 bytes); 0 if the slot cannot be read. */
static int record_id(jref_t r, uint32_t *epoch, uint32_t *seq)
{
  uint8_t plain[WS_OBS_PLAIN_MAX];
  if (store_journal_read(r, plain)) return 0;
  *epoch = be32(plain); *seq = be32(plain + 4);
  return 1;
}

static void forget_strikes(uint32_t epoch, uint32_t seq)
{
  for (unsigned i = 0; i < STRIKE_SLOTS; i++)
    if (strikes[i].n && strikes[i].epoch == epoch && strikes[i].seq == seq) strikes[i].n = 0;
}

static void strike(jref_t r)
{
  uint32_t epoch, seq; jref_t now;
  if (!record_id(r, &epoch, &seq)) return;
  unsigned use = STRIKE_SLOTS, low = 0;
  for (unsigned i = 0; i < STRIKE_SLOTS; i++)
  {
    if (strikes[i].n && strikes[i].epoch == epoch && strikes[i].seq == seq) { use = i; break; }
    if (strikes[i].n < strikes[low].n) low = i;
  }
  if (use == STRIKE_SLOTS) { use = low; strikes[use].epoch = epoch; strikes[use].seq = seq; strikes[use].n = 0; }
  if (++strikes[use].n < STRIKE_LIMIT) return;
  strikes[use].n = 0;
  /* Abandon only a record that is still pending under this identity. */
  if (store_journal_find(epoch, seq, &now) || store_journal_ack(now)) return;
  store_note_abandoned();
  led_flash(LED_RED, 1000);
  APP_PRINTF("#abandon epoch=%u seq=%u after %u unanswered tries while the gateway answered other frames; abandoned=%u\n",
             (unsigned)epoch, (unsigned)seq, STRIKE_LIMIT, (unsigned)store_abandoned_total());
}

/* End of an exchange: strikes only count when the gateway answered something in it. */
static void settle_strikes(void)
{
  int any = 0;
  for (unsigned i = 0; i < qn; i++) any |= replied[i];
  if (!any) return; /* link or gateway down: never abandon data for that */
  for (unsigned i = 0; i < qn; i++)
  {
    uint32_t epoch, seq;
    if (!replied[i]) strike(queue[i]);
    else if (record_id(queue[i], &epoch, &seq)) forget_strikes(epoch, seq);
  }
}
/* LoRa time on air (Semtech formula), explicit header, CRC on, for the configured radio. */
static uint32_t airtime_ms(uint32_t payload)
{
  static const uint32_t bw_hz[] = { 125000, 250000, 500000 };
  uint32_t sf = WS_LORA_SF, bw = bw_hz[WS_LORA_BANDWIDTH];
  uint32_t de = ((1000000UL << sf) / bw) > 16000 ? 1 : 0;           /* symbol > 16 ms */
  int32_t num = 8 * (int32_t)payload - 4 * (int32_t)sf + 28 + 16;
  int32_t den = 4 * ((int32_t)sf - 2 * (int32_t)de);
  int32_t blocks = num > 0 ? (num + den - 1) / den : 0;
  uint32_t symbols_x4 = (WS_LORA_PREAMBLE * 4 + 17) + 4 * (8 + (uint32_t)blocks * (WS_LORA_CR + 4));
  return (uint32_t)(((uint64_t)symbols_x4 * (1000000UL << sf) / bw) / 4000) + 1;
}

/* End of a minute's exchange: update the link state from whether the gateway answered. */
static void link_update(void)
{
  int any = 0;
  for (unsigned i = 0; i < qn; i++) any |= replied[i];
  if (any)
  {
    if (link_state == LINK_PROBING) diag_due = 1;
    if (link_state == LINK_PROBING) APP_PRINTF("#link linked after %u silent minutes\n", (unsigned)silent_minutes);
    link_state = LINK_LINKED; silent_minutes = 0; probe_step = 0;
    return;
  }
  silent_minutes++;
  if (link_state == LINK_LINKED && silent_minutes >= LINK_K_SILENT)
  {
    link_state = LINK_PROBING; probe_step = 0; diag_due = 1;
    next_probe_mcu = last_send_mcu + probe_interval_s[0]; /* from the exchange start: on the minute grid */
    if (ws_link_may_send(energy_state(), 1, (int32_t)probe_interval_s[0]))
    { APP_PRINTF("#link probing: %u silent minutes; live reading every minute, no backlog (energy %s)\n",
                 (unsigned)silent_minutes, energy_name[energy_state()]); }
    else
    { APP_PRINTF("#link probing: %u silent minutes; next probe in %u s (live readings stay journaled)\n",
                 (unsigned)silent_minutes, (unsigned)probe_interval_s[0]); }
  }
  else if (link_state == LINK_PROBING)
  {
    if (probe_step + 1 < sizeof probe_interval_s / sizeof probe_interval_s[0]) probe_step++;
    next_probe_mcu = last_send_mcu + probe_interval_s[probe_step];
    if (!ws_link_may_send(energy_state(), 1, (int32_t)probe_interval_s[probe_step]))
    { APP_PRINTF("#link probe unanswered; next probe in %u s\n", (unsigned)probe_interval_s[probe_step]); }
  }
}

static uint8_t reset_code(void)
{
  static const char *const causes[] = { "unknown", "power", "pin", "brownout", "software", "watchdog", "lowpower", "option-bytes" };
  for (uint8_t i = 0; i < sizeof causes / sizeof causes[0]; i++)
    if (!strcmp(causes[i], watchdog_reset_cause())) return i;
  return 0;
}

static uint16_t clamp16(uint32_t v) { return v > 0xFFFF ? 0xFFFF : (uint16_t)v; }
static int8_t clamp8(int v) { return (int8_t)(v < -127 ? -127 : v > 127 ? 127 : v); }  /* -128 means "none" */

/* First 8 hex digits of the release commit (WS_FW_VERSION, Makefile), 0 if it is not hex. */
static uint32_t fw_build_id(void)
{
  uint32_t id = 0;
  for (int i = 0; i < 8; i++)
  {
    char c = WS_FW_VERSION[i];
    int v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
    if (v < 0) return 0;
    id = id << 4 | (uint32_t)v;
  }
  return id;
}

/* Returns 1 if a health report went on air (the caller then waits for TxDone). */
static int send_diag(void)
{
  uint8_t plain[WS_DIAG_PLAIN_LEN], frame[WS_DIAG_FRAME_LEN]; uint64_t ctr;
  uint32_t now = mcu_seconds();
  if (now - last_diag_mcu >= DIAG_PERIOD_S) diag_due = 1;
  if (!diag_due) return 0;
  uint32_t up = now - boot_mcu, lost = store_journal_lost();
  uint16_t f[] = { clamp16(store_journal_pending()), clamp16(store_journal_burned()), clamp16(store_abandoned_total()),
                   clamp16(n_no_ack), clamp16(n_ack_rejects) };
  plain[0] = (uint8_t)(boot_epoch >> 24); plain[1] = (uint8_t)(boot_epoch >> 16); plain[2] = (uint8_t)(boot_epoch >> 8); plain[3] = (uint8_t)boot_epoch;
  plain[4] = (uint8_t)(up >> 24); plain[5] = (uint8_t)(up >> 16); plain[6] = (uint8_t)(up >> 8); plain[7] = (uint8_t)up;
  plain[8] = (uint8_t)(f[0] >> 8); plain[9] = (uint8_t)f[0];
  plain[10] = (uint8_t)(lost >> 24); plain[11] = (uint8_t)(lost >> 16); plain[12] = (uint8_t)(lost >> 8); plain[13] = (uint8_t)lost;
  for (int i = 1; i < 5; i++) { plain[12 + 2 * i] = (uint8_t)(f[i] >> 8); plain[13 + 2 * i] = (uint8_t)f[i]; }
  plain[22] = reset_code();
  plain[23] = (uint8_t)link_state;
  uint32_t build = fw_build_id(), crashes = fault_count();
  plain[24] = (uint8_t)(build >> 24); plain[25] = (uint8_t)(build >> 16); plain[26] = (uint8_t)(build >> 8); plain[27] = (uint8_t)build;
  plain[28] = (uint8_t)ack_rssi;
  plain[29] = (uint8_t)ack_snr;
  plain[30] = (uint8_t)(crashes > 0xFF ? 0xFF : crashes);
  plain[31] = (uint8_t)energy_state();
  if (store_next_counter(&ctr) || ws_seal_kind(key, station, WS_KIND_DIAG, ctr, plain, sizeof plain, frame, sizeof frame) < 0) return 0;
  diag_due = 0; last_diag_mcu = now;
  HAL_Delay(INTER_FRAME_MS);
  if (Radio.Send(frame, sizeof frame) != RADIO_STATUS_OK) { ws_failrun_note(&tx_air, 0); return 0; }
  diag_in_flight = 1;
  APP_PRINTF("#diag sent pending=%u lost=%u torn=%u abandoned=%u no_ack=%u\n", f[0], (unsigned)lost, f[1], f[2], f[3]);
  return 1;
}

static void finish_exchange(void)
{
  settle_strikes();
  link_update();
  if (send_diag()) return; /* busy until its TxDone */
  busy = 0;
  Radio.Sleep();
}

static void next_item(void)
{
  if (++qi < qn) { HAL_Delay(INTER_FRAME_MS); send_current(); return; }
  finish_exchange();
}

/* A missed reply ends this minute's drain: a failing link does not burn the allowance. */
static void stop_drain(void) { qn = qi + 1; }

/* Returns 1 for the authentic reply (ACK or NACK) to the frame just sent; 0 for anything else. */
static int handle_reply(void)
{
  uint64_t ctr, echo; uint32_t ep, sq, utc; jref_t ref; uint8_t kind;
  if (ws_open_reply(key, station, rx_frame, rx_len, &kind, &ctr, &ep, &sq, &utc, &echo))
  {
    n_ack_rejects++;
    led_flash(LED_RED, 400);
    APP_PRINTF("#ack reject len=%u rssi=%d snr=%d\n", rx_len, rx_rssi, rx_snr);
    return 0;
  }
  ack_rssi = clamp8(rx_rssi);   /* authentic reply only: a forged frame cannot set these */
  ack_snr = clamp8(rx_snr);
  int mine = echo == sent_counter && ep == sent_epoch && sq == sent_seq;
  if (kind == WS_KIND_NACK)
  {
    /* Authentic permanent rejection (gap G2). Accept it only for the frame just sent. */
    if (!mine) { n_ack_rejects++; APP_PRINTF("#nack ignored: not for the frame just sent\n"); return 0; }
    replied[qi] = 1;
    if (store_journal_find(ep, sq, &ref) == 0 && store_journal_ack(ref) == 0) store_note_abandoned();
    led_flash(LED_RED, 1000);
    APP_PRINTF("#nack epoch=%u seq=%u reason=%u abandoned=%u\n", (unsigned)ep, (unsigned)sq,
               (unsigned)utc, (unsigned)store_abandoned_total());
    return 1;
  }
  int found = store_journal_find(ep, sq, &ref) == 0;
  if (found && store_journal_ack(ref)) APP_PRINTF("#error journal-ack\n");
  forget_strikes(ep, sq);   /* any authentic ACK for a record ends its strikes */
  if (mine) replied[qi] = 1;
  int fresh = mine && utc >= MIN_PLAUSIBLE_UTC;
  if (fresh)
  {
    SysTime_t now = { .Seconds = utc, .SubSeconds = 0 };
    SysTimeSet(now);
    synced = 1;
    last_sync_mcu = mcu_seconds();
    HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_SYNC_MCU, last_sync_mcu);
    HAL_RTCEx_BKUPWrite(&hrtc, BKP_REG_MAGIC, BKP_TIME_MAGIC);
  }
  if (found) n_acked++;
  led_flash(LED_GREEN, 400); /* authentic host ACK: reading is committed */
  APP_PRINTF("#ack epoch=%u seq=%u found=%d time_sync=%d rssi=%d snr=%d pending=%u\n",
             (unsigned)ep, (unsigned)sq, found, fresh, rx_rssi, rx_snr,
             (unsigned)store_journal_pending());
  return mine;
}

static void process(void)
{
  int ev = event;
  event = EV_NONE;
  switch (ev)
  {
    case EV_TX_DONE:
      ws_failrun_note(&tx_air, 1);   /* the frame left: the radio works */
      if (diag_in_flight) { diag_in_flight = 0; busy = 0; Radio.Sleep(); break; } /* no reply expected */
      ack_window_end = HAL_GetTick() + ACK_WINDOW_MS;
      Radio.Rx(ACK_WINDOW_MS);
      break;
    case EV_RX_DONE:
      if (handle_reply()) { next_item(); break; }
      /* Not the reply to this frame (foreign, forged, or another frame's ACK): keep listening for
         the rest of the window instead of moving on and missing the real ACK (firmware review,
         finding 2). Too little time left counts as no reply. */
      {
        uint32_t now = HAL_GetTick(), left = (int32_t)(ack_window_end - now) > 0 ? ack_window_end - now : 0;
        if (left > MIN_RELISTEN_MS) { Radio.Rx(left); break; }
      }
      n_no_ack++;
      APP_PRINTF("#ack none epoch=%u seq=%u\n", (unsigned)sent_epoch, (unsigned)sent_seq);
      stop_drain();
      next_item();
      break;
    case EV_RX_TIMEOUT:
    case EV_RX_ERROR:
      n_no_ack++;
      led_flash(LED_RED, 400); /* stays journaled for a later retry */
      APP_PRINTF("#ack none epoch=%u seq=%u\n", (unsigned)sent_epoch, (unsigned)sent_seq);
      stop_drain();
      next_item();
      break;
    case EV_TX_TIMEOUT:
      ws_failrun_note(&tx_air, 0);
      led_flash(LED_RED, 400); APP_PRINTF("#error tx-timeout\n");
      if (diag_in_flight) { diag_in_flight = 0; busy = 0; Radio.Sleep(); break; }
      stop_drain(); next_item();
      break;
    default: break;
  }
}

/* The minute's 15-s samples (PRD section 9: coverage, mean and extrema). */
static ws_th_window th_window;
static unsigned th_ticks;

static void sample(void)
{
  int16_t t = 0; uint16_t h = 0; uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t live;
  last_sample_mcu = mcu_seconds();
  int src = sensor_read(&t, &h);
  ws_th_add(&th_window, src == 0, t, h);
  if (++th_ticks < SAMPLES_PER_REPORT) return;   /* the minute's report follows its last sample */
  th_ticks = 0;
  int valid = ws_th_mean_t(&th_window, &t) && ws_th_mean_h(&th_window, &h);
  int timed = time_valid();
  uint32_t utc = timed ? SysTimeGet().Seconds : 0;
  uint32_t uptime = mcu_seconds() - boot_mcu; /* always sent: the gateway reconstructs time from it */
  if (!valid) n_sensor_faults++;
  /* Draft-5 observation (docs/protocol-draft5-design.md 5): out-of-range temperature is INVALID,
     RH is clamped (ws_code_*); a sensor fault sends both fields as INVALID, never leaves them out. */
  /* static: sample() runs only from the sequencer, never re-entered, and it is the deepest
     callback chain, which tools/stack_report.py counts four times (a 104-byte record cost ~416 B). */
  static ws_obs_t o;
  o = (ws_obs_t){ .epoch = boot_epoch, .seq = next_seq, .utc = utc, .uptime = uptime,
                  .energy = (uint8_t)energy_state(), .bitmap = WS_NODE_FIELDS };
  o.code[WS_FI_TEMPERATURE_C] = valid ? ws_code_temp_centi(t) : ws_obs_invalid(WS_FI_TEMPERATURE_C);
  o.code[WS_FI_HUMIDITY_PCT] = valid ? ws_code_rh_centi(h) : ws_obs_invalid(WS_FI_HUMIDITY_PCT);
  /* Used only if the build's bitmap includes them (WS_F_TH_SUMMARY in node_fields.h). */
  o.code[WS_FI_TEMPERATURE_MIN_C] = valid ? ws_code_temp_centi(th_window.t_min) : ws_obs_invalid(WS_FI_TEMPERATURE_MIN_C);
  o.code[WS_FI_TEMPERATURE_MAX_C] = valid ? ws_code_temp_centi(th_window.t_max) : ws_obs_invalid(WS_FI_TEMPERATURE_MAX_C);
  o.code[WS_FI_HUMIDITY_MIN_PCT] = valid ? ws_code_rh_centi(th_window.h_min) : ws_obs_invalid(WS_FI_HUMIDITY_MIN_PCT);
  o.code[WS_FI_HUMIDITY_MAX_PCT] = valid ? ws_code_rh_centi(th_window.h_max) : ws_obs_invalid(WS_FI_HUMIDITY_MAX_PCT);
  o.code[WS_FI_TH_SAMPLES] = th_window.n > 60U ? 60U : th_window.n;
  unsigned samples = th_window.n;
  ws_th_reset(&th_window);
  int rc = ws_obs_encode(&o, plain, sizeof plain) == (int)WS_OBS_PLAIN_MAX ? store_journal_append(plain, &live) : -3;
  ws_failrun_note(&tx_fail, rc == 0);
  APP_PRINTF("#sample epoch=%u seq=%u uptime=%u valid=%d rc=%d n=%u t=%d rh=%u time=%s utc=%u journal=%s pending=%u lost=%u\n",
             (unsigned)boot_epoch, (unsigned)next_seq, (unsigned)uptime, valid, src, samples, valid ? t : 0, valid ? h : 0,
             timed ? "synchronized" : "unknown", (unsigned)utc, rc ? "ERROR" : "ok",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost());
  next_seq++; /* identity is never reused, even if the journal write failed */
  if (busy) { APP_PRINTF("#busy previous exchange still running\n"); return; }
  /* What may this minute send? The stricter of the energy and link states wins. */
  energy_t en = energy_state();
  uint32_t now = mcu_seconds();
  if (en == EN_CRITICAL) return;
  if (en == EN_CONSERVE && now - last_send_mcu < CONSERVE_INTERVAL_S) return;
  if (!ws_link_may_send(en, link_state == LINK_PROBING, (int32_t)(next_probe_mcu - now))) return; /* stays journaled */
  unsigned backlog = backlog_limit[en];
  if (link_state == LINK_PROBING) backlog = 0;                       /* a probe is the live reading */
  unsigned by_airtime = exchange_ms ? airtime_cap_ms[en] / exchange_ms : 0;
  if (by_airtime == 0) by_airtime = 1;                                 /* the live reading always fits */
  if (backlog + 1 > by_airtime) backlog = by_airtime - 1;
  if (backlog > MAX_QUEUE - 1) backlog = MAX_QUEUE - 1;
  qn = 0;
  if (!rc) queue[qn++] = live;
  qn += store_journal_oldest(queue + qn, backlog + (rc ? 1 : 0), rc ? NULL : &live);
  qi = 0;
  last_send_mcu = now;
  memset(replied, 0, sizeof replied);
  if (qn) { busy = 1; exchange_start_mcu = mcu_seconds(); send_current(); }
}

/* Watchdog health: real progress, not just a running main loop (failure-modes.md G1). */
static int tx_healthy(void)
{
  uint32_t now = mcu_seconds();
  if (!running) return 1;                                   /* not sampling by design */
  if (now - last_sample_mcu > 150) return 0;                /* sampling stopped */
  if (busy && now - exchange_start_mcu > 30) return 0;      /* radio exchange stuck */
  if (ws_failrun_tripped(&tx_fail, TX_FAIL_LIMIT)) { APP_PRINTF("#watchdog %u journal failures in a row\n", (unsigned)tx_fail.n); return 0; }
  if (ws_failrun_tripped(&tx_air, TX_FAIL_LIMIT)) { APP_PRINTF("#watchdog %u transmit failures in a row\n", (unsigned)tx_air.n); return 0; }
  return 1;
}

/* Bench-only power-cut test load (gap G7). Writes journal slots that are acknowledged on the
 * board at once (epoch STORM_EPOCH, never transmitted) and reserves counters, so that a
 * random power cut almost always lands inside a flash program or erase. Not persistent: a
 * reboot ends it, and the boot scrub drops any storm slot that a cut left pending. */
#define STORM_EPOCH 0xFFFFFFFFUL
static int storming;
static uint32_t storm_writes;
static void storm(void)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t r; uint64_t c;
  if (!storming) return;
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

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }

static void reboot_soon(void) { HAL_Delay(200); NVIC_SystemReset(); }

static void on_line(char *line)
{
  if (!strcmp(line, "STATUS")) { status(); return; }
  if (!strcmp(line, "TEST-FAULT")) fault_test();
  if (!strcmp(line, "TEST-HANG")) { APP_PRINTF("#test-hang: main loop stops; watchdog must reset in ~8 s\n"); HAL_Delay(50); for (;;) { } }
  if (!strcmp(line, "TEST-FLASH-STORM"))
  {
    { char ctr_buf[21];
      APP_PRINTF("#storm start ctr=%s (bench only: cut power now)\n", u64_text(store_counter_next(), ctr_buf)); }
    storming = 1; running = 0; /* sampling paused: the watchdog must not count a stopped sampler */
    UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Storm, CFG_SEQ_Prio_0);
    return;
  }
  if (!strcmp(line, "KAT")) { APP_PRINTF("#kat %s\n", run_kat() ? "pass" : "FAIL"); return; }
  if (!strcmp(line, "WIPE ERASE-ALL-NODE-STATE"))
  {
    APP_PRINTF("#wipe %s\n", store_wipe() ? "ERROR" : "ok");
    reboot_soon();
    return;
  }
  if (!strncmp(line, "PROVISION ", 10))
  {
    uint8_t new_key[16], check[3]; uint32_t id, floor; int rc;
    if (provisioned) { APP_PRINTF("#error already-provisioned (WIPE first)\n"); }
    else if (ws_parse_provision(line + 10, &id, new_key, &floor))
    { APP_PRINTF("#error usage: PROVISION <station_id> <32 hex key> [epoch_floor]\n"); }
    else if (floor && store_epoch_floor(floor)) { APP_PRINTF("#error epoch-floor\n"); }
    else if ((rc = store_config_write(id, new_key)) != 0) { APP_PRINTF("#error provision rc=%d\n", rc); }
    else
    {
      ws_key_check(new_key, check);
      APP_PRINTF("#provisioned station=%u kcv=%02x%02x%02x epoch_floor=%u\n", (unsigned)id, check[0], check[1], check[2], (unsigned)floor);
      memset(new_key, 0, sizeof new_key); memset(line, 0, strlen(line));
      reboot_soon();
      return;
    }
    memset(new_key, 0, sizeof new_key); memset(line, 0, strlen(line)); /* the key never lingers in RAM */
    return;
  }
  APP_PRINTF("#error unknown command\n");
}

static void on_boot_retry(void *ctx) { (void)ctx; NVIC_SystemReset(); }

/* Never for an unprovisioned board or a failed self-test: those need an operator, not a reset. */
static void boot_retry(void)
{
  if (!kat_ok) return;
  APP_PRINTF("#boot-retry: reset in %u s\n", (unsigned)(BOOT_RETRY_MS / 1000));
  UTIL_TIMER_Create(&boot_retry_timer, BOOT_RETRY_MS, UTIL_TIMER_ONESHOT, on_boot_retry, NULL);
  UTIL_TIMER_Start(&boot_retry_timer);
}

void SubghzApp_Init(void)
{
  stackmon_paint();
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  events.RxDone = on_rx_done;
  events.RxTimeout = on_rx_timeout;
  events.RxError = on_rx_error;
  leds_init();
  Radio.Init(&events);
  ws_radio_configure(0);
  Radio.Sleep();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sample, UTIL_SEQ_RFU, sample);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Storm, UTIL_SEQ_RFU, storm);
  console_init(on_line);

  boot_mcu = mcu_seconds();
  exchange_ms = airtime_ms(OBS_FRAME_MAX) + airtime_ms(WS_ACK_FRAME_LEN) + TURNAROUND_MS;
  watchdog_start(tx_healthy);
  kat_ok = run_kat();
  APP_PRINTF("#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             watchdog_reset_cause(), kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); boot_retry(); return; }
  uint32_t scrubbed = store_journal_scrub(STORM_EPOCH);
  if (scrubbed) APP_PRINTF("#storm-scrub dropped=%u (test slots a power cut left pending)\n", (unsigned)scrubbed);
  provisioned = store_config_load(&station, key) == 0;
  if (!provisioned) { led_set(LED_RED, 1); status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return; }
  ws_key_check(key, kcv);
  restore_time_trust();
  if (!kat_ok) { led_set(LED_RED, 1); status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return; }
  /* Durable epoch before the first sample: observation identities never repeat. */
  if (store_next_epoch(&boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); boot_retry(); return; }
  sensor_init();
  {
    int16_t t; uint16_t h; int src = sensor_read(&t, &h);
    if (src) { APP_PRINTF("#sensor fault rc=%d (see sensor.h for codes)\n", src); }
    else { APP_PRINTF("#sensor ok t=%d rh=%u\n", t, h); }
  }
  running = 1;
  last_sample_mcu = mcu_seconds();
  status();
  UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
