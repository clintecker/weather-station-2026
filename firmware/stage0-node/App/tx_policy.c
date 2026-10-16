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

_Static_assert(WS_BACKLOG_MAX <= MAX_QUEUE - 1U, "the send queue holds the live reading plus the largest backlog");
#define TURNAROUND_MS 300U   /* gateway commit (fullfsync) + USB both ways, conservative */
#define STRIKE_LIMIT  10U
#define STRIKE_SLOTS  6
#define DIAG_PERIOD_S 900U

static ws_link link;
static uint32_t last_send_s;   /* the last minute that sent: the CONSERVE interval and the probe schedule count from it */
static uint32_t exchange_ms;   /* estimated radio time of one answered exchange */
static ws_strike strikes[STRIKE_SLOTS];
static int diag_due = 1;       /* a health report right after boot */
static uint32_t last_diag_s;

int energy_state(void) { return WS_ENERGY_NORMAL; }
int policy_probing(void) { return link.probing; }
uint32_t policy_silent_minutes(void) { return link.silent; }

void policy_init(void)
{
  static const uint32_t bw_hz[] = { 125000, 250000, 500000 };
  _Static_assert(WS_LORA_BANDWIDTH < sizeof bw_hz / sizeof bw_hz[0], "a LoRa bandwidth index radio_cfg.h knows");
  uint32_t bw = bw_hz[WS_LORA_BANDWIDTH];
  exchange_ms = ws_lora_airtime_ms(OBS_FRAME_MAX, WS_LORA_SF, bw, WS_LORA_PREAMBLE, WS_LORA_CR) +
                ws_lora_airtime_ms(WS_ACK_FRAME_LEN, WS_LORA_SF, bw, WS_LORA_PREAMBLE, WS_LORA_CR) + TURNAROUND_MS;
}

int policy_minute_backlog(void)
{
  uint32_t now = clock_s();
  int backlog = ws_minute_backlog(energy_state(), &link, now, last_send_s, exchange_ms, MAX_QUEUE - 1U);
  if (backlog >= 0) last_send_s = now;
  return backlog;
}

/* Identity of a journaled record (its first 8 bytes); 0 if the slot cannot be read. */
static int record_id(jref_t r, uint32_t *epoch, uint32_t *seq)
{
  uint8_t plain[WS_OBS_PLAIN_MAX];
  if (store_journal_read(r, plain)) return 0;
  *epoch = ws_get_be32(plain); *seq = ws_get_be32(plain + 4);
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
  uint32_t was_silent = link.silent;
  link_report(ws_link_minute(&link, any, last_send_s), was_silent);
}

int policy_diag_due(void) { return diag_due || clock_s() - last_diag_s >= DIAG_PERIOD_S; }
void policy_diag_sent(uint32_t now_s) { diag_due = 0; last_diag_s = now_s; }
