/* Stage-0 TX: one SHT45 observation per minute, journaled in flash before transmission and
 * retained until an authenticated host ACK. Each minute sends the live observation first,
 * then at most two older pending ones; each frame gets a fresh durably reserved counter and
 * one ACK receive window. Time comes only from an ACK that echoes the counter of the frame
 * just sent (replayed ACKs cannot move the clock). Console lines from this board start
 * with '#'; commands: STATUS, KAT, PROVISION <station_id> <32 hex key>,
 * WIPE ERASE-ALL-NODE-STATE. */
#include <stdlib.h>
#include <string.h>
#include "console.h"
#include "leds.h"
#include "node_store.h"
#include "radio.h"
#include "radio_cfg.h"
#include "sensor.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32wlxx_hal.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"
#include "ws_frame.h"

#define SAMPLE_PERIOD_MS    60000U
#define ACK_WINDOW_MS       2000U
#define INTER_FRAME_MS      50U
#define MAX_BACKFILL        2U
#define SYNC_VALID_MS       (6UL * 3600UL * 1000UL) /* ~20 ppm LSE: <0.5 s drift */
#define MIN_PLAUSIBLE_UTC   1767225600ULL           /* 2026-01-01T00:00:00Z */

/* Known-answer vectors shared with tests/test_frame.py (Python-generated). */
static const uint8_t KAT_KEY[16] = { 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 };
static const char KAT_OBS_HEX[] = "57530301000000010000000100000002bd50c6ae3400a778bec357cf"
                                  "adacd03beedf778fa19f9c447992145b5e7537758039b13149e7f512";
static const char KAT_ACK_HEX[] = "575303020000000100000000000000050e1eb4544766f4e68818a3b3"
                                  "9f36393d04a393ebcf0d38785a76634d1c45687d9476ed40fa1d3e46";

static RadioEvents_t events;
static UTIL_TIMER_Object_t sample_timer;
static uint32_t station;
static uint8_t key[16];
static uint8_t kcv[3];
static int provisioned, kat_ok, running;
static uint32_t boot_epoch, next_seq;
static int synced;
static uint32_t last_sync_ms;

static jref_t queue[1 + MAX_BACKFILL];
static unsigned qn, qi;
static int busy;
static uint64_t sent_counter;
static uint32_t sent_epoch, sent_seq;
static uint32_t n_sent, n_acked, n_no_ack, n_ack_rejects, n_sensor_faults;

static uint8_t rx_frame[255];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
static volatile enum { EV_NONE, EV_TX_DONE, EV_TX_TIMEOUT, EV_RX_DONE, EV_RX_TIMEOUT, EV_RX_ERROR } event;

static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
static int time_valid(void) { return synced && (HAL_GetTick() - last_sync_ms) < SYNC_VALID_MS; }

static int run_kat(void)
{
  uint8_t plain[24], frame[WS_OBS_FRAME_LEN], expect[WS_OBS_FRAME_LEN], ack[WS_ACK_FRAME_LEN];
  uint64_t ctr, utc, echo; uint32_t ep, sq;
  ws_pack_observation(plain, 17, 42, 100000, -1234, 4567, 1, 1);
  if (hex_decode(KAT_OBS_HEX, expect, sizeof expect) != WS_OBS_FRAME_LEN) return 0;
  if (ws_seal_obs(KAT_KEY, 1, 0x100000002ULL, plain, frame) || memcmp(frame, expect, sizeof frame)) return 0;
  if (hex_decode(KAT_ACK_HEX, ack, sizeof ack) != WS_ACK_FRAME_LEN) return 0;
  if (ws_open_ack(KAT_KEY, 1, ack, sizeof ack, &ctr, &ep, &sq, &utc, &echo)) return 0;
  if (ctr != 5 || ep != 17 || sq != 42 || utc != 1760000000ULL || echo != 0x100000002ULL) return 0;
  ack[sizeof ack - 1] ^= 1; /* tampered tag must fail */
  return ws_open_ack(KAT_KEY, 1, ack, sizeof ack, &ctr, &ep, &sq, &utc, &echo) != 0;
}

static void status(void)
{
  APP_PRINTF("#status role=tx fw=%s provisioned=%d station=%u kcv=%02x%02x%02x kat=%s epoch=%u next_seq=%u "
             "time=%s pending=%u lost=%u burned=%u sent=%u acked=%u no_ack=%u ack_rejects=%u sensor_faults=%u\n",
             WS_FW_VERSION, provisioned, (unsigned)station, kcv[0], kcv[1], kcv[2], kat_ok ? "pass" : "FAIL",
             (unsigned)boot_epoch, (unsigned)next_seq, time_valid() ? "synchronized" : "unknown",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost(),
             (unsigned)store_journal_burned(), (unsigned)n_sent, (unsigned)n_acked,
             (unsigned)n_no_ack, (unsigned)n_ack_rejects, (unsigned)n_sensor_faults);
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

static void next_item(void);

static void send_current(void)
{
  uint8_t plain[24], frame[WS_OBS_FRAME_LEN];
  if (store_journal_read(queue[qi], plain)) { APP_PRINTF("#error journal-read\n"); next_item(); return; }
  /* No durable counter reservation, no transmission (nonce reuse would break CCM). */
  if (store_next_counter(&sent_counter)) { APP_PRINTF("#error counter-reserve\n"); busy = 0; Radio.Sleep(); return; }
  if (ws_seal_obs(key, station, sent_counter, plain, frame)) { APP_PRINTF("#error seal\n"); next_item(); return; }
  sent_epoch = be32(plain);
  sent_seq = be32(plain + 4);
  n_sent++;
  led_flash(LED_BLUE, 400);
  if (Radio.Send(frame, sizeof frame) != RADIO_STATUS_OK) { APP_PRINTF("#error radio-busy\n"); next_item(); }
}

static void next_item(void)
{
  if (++qi < qn) { HAL_Delay(INTER_FRAME_MS); send_current(); return; }
  busy = 0;
  Radio.Sleep();
}

static void handle_ack(void)
{
  uint64_t ctr, utc, echo; uint32_t ep, sq; jref_t ref;
  if (ws_open_ack(key, station, rx_frame, rx_len, &ctr, &ep, &sq, &utc, &echo))
  {
    n_ack_rejects++;
    led_flash(LED_RED, 400);
    APP_PRINTF("#ack reject len=%u rssi=%d snr=%d\n", rx_len, rx_rssi, rx_snr);
    return;
  }
  int found = store_journal_find(ep, sq, &ref) == 0;
  if (found && store_journal_ack(ref)) APP_PRINTF("#error journal-ack\n");
  int fresh = echo == sent_counter && ep == sent_epoch && sq == sent_seq && utc >= MIN_PLAUSIBLE_UTC;
  if (fresh)
  {
    SysTime_t now = { .Seconds = (uint32_t)utc, .SubSeconds = 0 };
    SysTimeSet(now);
    synced = 1;
    last_sync_ms = HAL_GetTick();
  }
  if (found) n_acked++;
  led_flash(LED_GREEN, 400); /* authentic host ACK: reading is committed */
  APP_PRINTF("#ack epoch=%u seq=%u found=%d time_sync=%d rssi=%d snr=%d pending=%u\n",
             (unsigned)ep, (unsigned)sq, found, fresh, rx_rssi, rx_snr,
             (unsigned)store_journal_pending());
}

static void process(void)
{
  int ev = event;
  event = EV_NONE;
  switch (ev)
  {
    case EV_TX_DONE: Radio.Rx(ACK_WINDOW_MS); break;
    case EV_RX_DONE: handle_ack(); next_item(); break;
    case EV_RX_TIMEOUT:
    case EV_RX_ERROR:
      n_no_ack++;
      led_flash(LED_RED, 400); /* stays journaled for a later retry */
      APP_PRINTF("#ack none epoch=%u seq=%u\n", (unsigned)sent_epoch, (unsigned)sent_seq);
      next_item();
      break;
    case EV_TX_TIMEOUT: led_flash(LED_RED, 400); APP_PRINTF("#error tx-timeout\n"); next_item(); break;
    default: break;
  }
}

static void sample(void)
{
  int16_t t = 0; uint16_t h = 0; uint8_t plain[24]; jref_t live;
  int valid = sensor_read(&t, &h) == 0;
  int timed = time_valid();
  uint64_t utc = timed ? SysTimeGet().Seconds : 0;
  if (!valid) n_sensor_faults++;
  ws_pack_observation(plain, boot_epoch, next_seq, utc, t, h, (uint8_t)valid, (uint8_t)timed);
  int rc = store_journal_append(plain, &live);
  APP_PRINTF("#sample epoch=%u seq=%u valid=%d t=%d rh=%u time=%s utc=%u journal=%s pending=%u lost=%u\n",
             (unsigned)boot_epoch, (unsigned)next_seq, valid, valid ? t : 0, valid ? h : 0,
             timed ? "synchronized" : "unknown", (unsigned)utc, rc ? "ERROR" : "ok",
             (unsigned)store_journal_pending(), (unsigned)store_journal_lost());
  next_seq++; /* identity is never reused, even if the journal write failed */
  if (busy) { APP_PRINTF("#busy previous exchange still running\n"); return; }
  qn = 0;
  if (!rc) queue[qn++] = live;
  qn += store_journal_oldest(queue + qn, MAX_BACKFILL, rc ? NULL : &live);
  qi = 0;
  if (qn) { busy = 1; send_current(); }
}

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }

static void reboot_soon(void) { HAL_Delay(200); NVIC_SystemReset(); }

static void on_line(char *line)
{
  if (!strcmp(line, "STATUS")) { status(); return; }
  if (!strcmp(line, "KAT")) { APP_PRINTF("#kat %s\n", run_kat() ? "pass" : "FAIL"); return; }
  if (!strcmp(line, "WIPE ERASE-ALL-NODE-STATE"))
  {
    APP_PRINTF("#wipe %s\n", store_wipe() ? "ERROR" : "ok");
    reboot_soon();
    return;
  }
  if (!strncmp(line, "PROVISION ", 10))
  {
    uint8_t new_key[17]; char *end; uint8_t check[3];
    if (provisioned) { APP_PRINTF("#error already-provisioned (WIPE first)\n"); return; }
    unsigned long id = strtoul(line + 10, &end, 10);
    if (end == line + 10 || *end != ' ' || id == 0 || id > 0xFFFFFFFFUL ||
        hex_decode(end + 1, new_key, sizeof new_key) != 16)
    {
      APP_PRINTF("#error usage: PROVISION <station_id> <32 hex key>\n");
      return;
    }
    int rc = store_config_write((uint32_t)id, new_key);
    ws_key_check(new_key, check);
    memset(new_key, 0, sizeof new_key);
    if (rc) { APP_PRINTF("#error provision rc=%d\n", rc); return; }
    APP_PRINTF("#provisioned station=%u kcv=%02x%02x%02x\n", (unsigned)id, check[0], check[1], check[2]);
    reboot_soon();
    return;
  }
  APP_PRINTF("#error unknown command\n");
}

void SubghzApp_Init(void)
{
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
  console_init(on_line);

  kat_ok = run_kat();
  APP_PRINTF("#boot role=tx fw=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); return; }
  provisioned = store_config_load(&station, key) == 0;
  if (!provisioned) { led_set(LED_RED, 1); status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return; }
  ws_key_check(key, kcv);
  if (!kat_ok) { led_set(LED_RED, 1); status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return; }
  /* Durable epoch before the first sample: observation identities never repeat. */
  if (store_next_epoch(&boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); return; }
  sensor_init();
  running = 1;
  status();
  UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
