/* Stage-0 RX: transparent radio <-> USB bridge for the indoor receiver.
 *
 * Upstream: every received frame that ws_air_frame_ok() accepts (a current-version observation or
 * health report of a valid length) is written as one lowercase hex line. Downstream: every hex
 * line from the host that ws_host_reply_ok() accepts (a current-version ACK or NACK) is
 * transmitted once. The ACK path
 * uses the same radio_cfg.h power/SF/BW as the uplink (gap G15). This board holds no key and
 * never acknowledges anything itself; the host is the sole ACK authority (docs/protocol.md).
 * All other output lines start with '#' and are diagnostics for the host log. A reception that
 * fails its checks is logged too: `#rx crc ... data=<hex>` keeps every byte the radio received
 * when only the payload CRC failed; `#rx hdr rssi=` is a header that failed (no payload). */
#include <string.h>
#include "busymon.h"
#include "console.h"
#include "leds.h"
#include "stm32wlxx_hal.h"
#include "watchdog.h"
#include "radio.h"
#include "radio_cfg.h"
#include "stage0.h"
#include "usart_if.h"
#include "stackmon.h"
#include "fault.h"
#include "stm32_seq.h"
#include "stm32_systime.h"
#include "stm32_timer.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"
#include "ws_frame.h"

static RadioEvents_t events;
static uint8_t rx_frame[255];
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
/* Radio events from interrupt context, as bits: several can arrive before process() runs, and none
 * is lost (firmware review finding 3: one event slot, cleared at the end of process(), dropped
 * events posted meanwhile; a lost TxDone left `transmitting` set until the watchdog reset). */
#define EV_RX         (1U << 0)
#define EV_RX_CRC     (1U << 1)
#define EV_TX_DONE    (1U << 2)
#define EV_TX_TIMEOUT (1U << 3)
#define EV_RX_HDR     (1U << 4)
static volatile uint32_t pending_ev;
static volatile uint8_t transmitting;
static uint32_t n_forwarded, n_dropped, n_acks;
static uint32_t tx_start_ms;
static UTIL_TIMER_Object_t alive_timer;
static uint32_t n_diag;
static uint32_t boot_ms;
/* Milliseconds from the RTC (MCU time keeps counting through a reset). Not HAL_GetTick: on this
   board that counts 1/1024 s RTC ticks (timer_if.c), not milliseconds. Wraps after 49 days; every
   use is a difference. */
static uint32_t ms_now(void) { SysTime_t t = SysTimeGetMcuTime(); return t.Seconds * 1000U + (uint32_t)t.SubSeconds; }
static int relisten_tries;
/* Review P6: Radio.GetStatus() reports the driver's own state, not the chip's. Real evidence of
 * listening is a radio event (RxDone or RxError). With TX sending every minute, 5 silent
 * minutes means something is wrong: put the radio in standby and start listening again. */
#define SILENCE_RELISTEN_MS (5UL * 60000UL)
static uint32_t last_radio_event_ms, n_relistens;
static volatile uint8_t relisten_due, alive_due;
static void alive(void);
static int uart_rearm_tries;
static void post(uint32_t ev)
{
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  pending_ev |= ev;
  __set_PRIMASK(primask);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0);
}
static uint8_t bad_frame[255];
static uint8_t bad_len;
static int8_t bad_rssi, bad_snr, hdr_rssi;
static uint32_t n_crc, n_hdr, n_fault_overrun;
static void capture_crc(const uint8_t *payload, uint16_t size, int8_t rssi, int8_t snr);
static uint8_t crc_in_done;   /* this packet's RxError follows its RxDone in the same interrupt */
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  last_radio_event_ms = ms_now();
  /* ST's HAL also raises RxDone for a packet whose payload CRC failed: that one is a failed
     reception, never forwarded (stm32wlxx_hal_subghz.c HAL_SUBGHZ_IRQHandler). */
  if (ws_radio_take_crc_error()) { crc_in_done = 1; capture_crc(payload, size, (int8_t)rssi, snr); return; }
  if (pending_ev & EV_RX) n_fault_overrun++;   /* a frame not yet forwarded is replaced */
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX);
}
/* Failed receptions, from the radio interrupt. A payload CRC failure arrives as RxDone (bytes
   included, flagged by the HAL) and then RxError; on_rx_done captures it. RxTimeout cannot be a
   timeout in continuous receive: ST's radio.c reports a header error that way. One capture is kept
   until process() prints it; failures meanwhile are counted, not captured (n_fault_overrun). The
   radio stays in continuous receive through both (radio.c), so nothing re-arms it. */
static void capture_crc(const uint8_t *payload, uint16_t size, int8_t rssi, int8_t snr)
{
  n_crc++;
  if (pending_ev & EV_RX_CRC) { n_fault_overrun++; return; }
  bad_len = (uint8_t)(size > sizeof bad_frame ? sizeof bad_frame : size);
  memcpy(bad_frame, payload, bad_len);
  bad_rssi = rssi; bad_snr = snr;
  post(EV_RX_CRC);
}
static void on_rx_error(void)
{
  if (crc_in_done) { crc_in_done = 0; return; }   /* already captured by on_rx_done */
  /* An RxError without the RxDone before it: read what the radio kept. */
  uint8_t len; int8_t rssi, snr;
  last_radio_event_ms = ms_now();
  if (pending_ev & EV_RX_CRC) { n_crc++; n_fault_overrun++; return; }
  ws_radio_last_packet(bad_frame, &len, &rssi, &snr);
  n_crc++; bad_len = len; bad_rssi = rssi; bad_snr = snr;
  post(EV_RX_CRC);
}
static void on_rx_timeout(void)
{
  last_radio_event_ms = ms_now();   /* a header error is evidence the radio is listening */
  n_hdr++;
  if (pending_ev & EV_RX_HDR) { n_fault_overrun++; return; }
  hdr_rssi = ws_radio_rssi_now();   /* the channel right after the failed header */
  post(EV_RX_HDR);
}
static void on_tx_done(void) { post(EV_TX_DONE); }
static void on_tx_timeout(void) { post(EV_TX_TIMEOUT); }

static void listen(void)
{
  transmitting = 0;
  Radio.Rx(0); /* continuous */
}

/* Watchdog health: the radio must really be listening, or finish a transmission within 5 s.
 * One self-heal attempt (re-arm RX) before the watchdog is allowed to reset the board. */
static int rx_healthy(void)
{
  /* Review P5: the console must be receiving (it carries the ACK downlink). One re-arm first. */
  if (!vcom_rx_armed())
  {
    if (uart_rearm_tries++ == 0) { APP_PRINTF("#watchdog console not receiving; re-arming\n"); vcom_rx_rearm(); return 1; }
    return 0;
  }
  uart_rearm_tries = 0;
  if (transmitting) return ms_now() - tx_start_ms < 5000;
  if (Radio.GetStatus() == RF_RX_RUNNING) { relisten_tries = 0; return 1; }
  if (relisten_tries++ == 0) { APP_PRINTF("#watchdog radio not listening; re-arming\n"); listen(); return 1; }
  return 0;
}

static void process(void)
{
  if (alive_due) { alive_due = 0; alive(); }   /* may set relisten_due, handled just below */
  if (relisten_due && !transmitting)
  {
    relisten_due = 0;
    n_relistens++;
    APP_PRINTF("#relisten after %u s without a radio event\n", (unsigned)((ms_now() - last_radio_event_ms) / 1000));
    Radio.Standby();
    listen();
    last_radio_event_ms = ms_now();
  }
  /* Take the pending events and the received frame in one step with interrupts masked, so a
     second RxDone cannot tear the frame while it is forwarded (it is handled on the next pass). */
  static uint8_t frame[sizeof rx_frame], bad[sizeof bad_frame];
  uint16_t len = 0; int16_t rssi = 0; int8_t snr = 0;
  uint8_t blen = 0; int8_t brssi = 0, bsnr = 0, hrssi = 0;
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  uint32_t ev = pending_ev;
  pending_ev = 0;
  if (ev & EV_RX) { len = rx_len; memcpy(frame, rx_frame, len); rssi = rx_rssi; snr = rx_snr; }
  if (ev & EV_RX_CRC) { blen = bad_len; memcpy(bad, bad_frame, blen); brssi = bad_rssi; bsnr = bad_snr; }
  hrssi = hdr_rssi;
  __set_PRIMASK(primask);
  if (ev & (EV_TX_DONE | EV_TX_TIMEOUT))
  {
    if (ev & EV_TX_TIMEOUT) { APP_PRINTF("#tx timeout\n"); led_flash(LED_RED, 400); }
    listen();
  }
  if (ev & EV_RX)
  {
    if (ws_air_frame_ok(frame, len))
    {
      n_diag += ws_frame_kind(frame, len) == WS_KIND_DIAG;
      hex_print(frame, len);
      led_flash(LED_BLUE, 400);
      n_forwarded++;
      APP_PRINTF("#rx obs rssi=%d snr=%d\n", rssi, snr);
    }
    else
    {
      n_dropped++;
      led_flash(LED_RED, 400);
      APP_PRINTF("#rx drop len=%u rssi=%d snr=%d\n", len, rssi, snr);
    }
  }
  if (ev & EV_RX_CRC)
  {
    static char text[2 * sizeof bad_frame + 1];
    ws_hex_text(bad, blen, text);
    APP_PRINTF("#rx crc len=%u rssi=%d snr=%d data=%s\n", blen, brssi, bsnr, text);
  }
  if (ev & EV_RX_HDR) APP_PRINTF("#rx hdr rssi=%d\n", hrssi);
}
BUSYMON_TASK(process)

/* Liveness report for the gateway (gap G12): it marks the receiver silent after 180 s. Printed
   from the main loop: the timer interrupt only asks for it. */
static void alive(void)
{
  APP_PRINTF("#alive uptime=%u forwarded=%u dropped=%u acks=%u diag=%u listening=%d relistens=%u uart_errors=%u stack_peak=%u "
             "crc_errors=%u hdr_errors=%u fault_overruns=%u task_peak_us=%u task_peak=%s isr_peak_us=%u isr_peak=%s trace_drops=%u\n",
             (unsigned)((ms_now() - boot_ms) / 1000), (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks,
             (unsigned)n_diag, Radio.GetStatus() == RF_RX_RUNNING || transmitting, (unsigned)n_relistens,
             (unsigned)vcom_rx_errors(), (unsigned)stackmon_peak(), (unsigned)n_crc, (unsigned)n_hdr, (unsigned)n_fault_overrun,
             (unsigned)busymon_peak_us(BM_TASK), busymon_peak_name(BM_TASK), (unsigned)busymon_peak_us(BM_ISR),
             busymon_peak_name(BM_ISR), (unsigned)ws_trace_drops);
  if (!transmitting && ws_silent_for(ms_now(), last_radio_event_ms, SILENCE_RELISTEN_MS)) relisten_due = 1;
}
static void on_alive(void *ctx)
{
  (void)ctx;
  alive_due = 1;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0);
}

/* Bench: TEST-HANG stops the main loop on purpose, so the watchdog must reset the board
   (tools/blocking_report.py TEST_ONLY). */
static void test_hang(void) __attribute__((noreturn));
static void test_hang(void)
{
  APP_PRINTF("#test-hang: main loop stops; watchdog must reset in ~8 s\n");
  for (;;) { }
}

static void on_line(char *line)
{
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  if (line[0] == '#') return;
  if (!strcmp(line, "TEST-FAULT")) fault_test();
  if (!strcmp(line, "TEST-HANG")) test_hang();
  if (!strcmp(line, "STATUS"))
  {
    APP_PRINTF("#status role=rx forwarded=%u dropped=%u acks=%u relistens=%u uart_errors=%u\n",
               (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks, (unsigned)n_relistens, (unsigned)vcom_rx_errors());
    return;
  }
  int n = ws_hex_decode(line, frame, sizeof frame);
  if (!ws_host_reply_ok(frame, n))
  {
    APP_PRINTF("#host reject len=%d\n", n);
    led_flash(LED_RED, 400);
    return;
  }
  transmitting = 1;
  tx_start_ms = ms_now();
  if (Radio.Send(frame, WS_ACK_FRAME_LEN) != RADIO_STATUS_OK)
  {
    APP_PRINTF("#tx busy\n");
    listen();
    return;
  }
  n_acks++;
  led_flash(LED_GREEN, 400);
}

void SubghzApp_Init(void)
{
  stackmon_paint();
  busymon_init();
  events.RxDone = on_rx_done;
  events.RxError = on_rx_error;
  events.RxTimeout = on_rx_timeout;
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  boot_ms = ms_now();
  last_radio_event_ms = boot_ms;
  leds_init();
  watchdog_start(rx_healthy);
  Radio.Init(&events);
  ws_radio_configure(1);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process_timed);
  console_init(on_line);
  APP_PRINTF("#boot role=rx fw=%s reset=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION, watchdog_reset_cause(),
             (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  UTIL_TIMER_Create(&alive_timer, 60000, UTIL_TIMER_PERIODIC, on_alive, NULL);
  UTIL_TIMER_Start(&alive_timer);
  listen();
}
