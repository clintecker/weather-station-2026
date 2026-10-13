/* Stage-0 RX: transparent radio <-> USB bridge for the indoor receiver.
 *
 * Upstream: every received frame that looks like a current-draft observation (56 bytes, "WS",
 * WS_FRAME_VERSION, kind 1) is written as one lowercase hex line. Downstream: every hex line
 * from the host that looks like a current-draft ACK or NACK is transmitted once. The ACK path
 * uses the same radio_cfg.h power/SF/BW as the uplink (gap G15). This board holds no key and
 * never acknowledges anything itself; the host is the sole ACK authority (docs/protocol.md).
 * All other output lines start with '#' and are diagnostics for the host log. */
#include <string.h>
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
static volatile enum { EV_NONE, EV_RX, EV_RX_ERROR, EV_TX_DONE, EV_TX_TIMEOUT } event;
static volatile uint8_t transmitting;
static uint32_t n_forwarded, n_dropped, n_acks;
static uint32_t tx_start_ms;
static UTIL_TIMER_Object_t alive_timer;
static uint32_t n_diag;
static uint32_t boot_tick; /* HAL_GetTick runs from the RTC here and survives resets */
static int relisten_tries;
/* Review P6: Radio.GetStatus() reports the driver's own state, not the chip's. Real evidence of
 * listening is a radio event (RxDone or RxError). With TX sending every minute, 5 silent
 * minutes means something is wrong: put the radio in standby and start listening again. */
#define SILENCE_RELISTEN_MS (5UL * 60000UL)
static uint32_t last_radio_event_ms, n_relistens;
static volatile uint8_t relisten_due;
static int uart_rearm_tries;
static void post(int ev) { event = ev; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0); }
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  last_radio_event_ms = HAL_GetTick();
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX);
}
static void on_rx_error(void) { last_radio_event_ms = HAL_GetTick(); post(EV_RX_ERROR); }
static void on_rx_timeout(void) { post(EV_RX_ERROR); }
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
  if (transmitting) return HAL_GetTick() - tx_start_ms < 5000;
  if (Radio.GetStatus() == RF_RX_RUNNING) { relisten_tries = 0; return 1; }
  if (relisten_tries++ == 0) { APP_PRINTF("#watchdog radio not listening; re-arming\n"); listen(); return 1; }
  return 0;
}

static void process(void)
{
  if (relisten_due && !transmitting)
  {
    relisten_due = 0;
    n_relistens++;
    APP_PRINTF("#relisten after %u s without a radio event\n", (unsigned)((HAL_GetTick() - last_radio_event_ms) / 1000));
    Radio.Standby();
    listen();
    last_radio_event_ms = HAL_GetTick();
  }
  switch (event)
  {
    case EV_RX:
      if (rx_len == WS_OBS_FRAME_LEN && rx_frame[0] == 'W' && rx_frame[1] == 'S' &&
          rx_frame[2] == WS_FRAME_VERSION && (rx_frame[3] == WS_KIND_OBS || rx_frame[3] == WS_KIND_DIAG))
      {
        n_diag += rx_frame[3] == WS_KIND_DIAG;
        hex_print(rx_frame, rx_len);
        led_flash(LED_BLUE, 400);
        n_forwarded++;
        APP_PRINTF("#rx obs rssi=%d snr=%d\n", rx_rssi, rx_snr);
      }
      else
      {
        n_dropped++;
        led_flash(LED_RED, 400);
        APP_PRINTF("#rx drop len=%u rssi=%d snr=%d\n", rx_len, rx_rssi, rx_snr);
      }
      break;
    case EV_RX_ERROR:
      APP_PRINTF("#rx error\n");
      led_flash(LED_RED, 400);
      if (!transmitting) listen();
      break;
    case EV_TX_DONE:
      listen();
      break;
    case EV_TX_TIMEOUT:
      APP_PRINTF("#tx timeout\n");
      led_flash(LED_RED, 400);
      listen();
      break;
    default:
      break;
  }
  event = EV_NONE;
}

/* Liveness report for the gateway (gap G12): it marks the receiver silent after 180 s. */
static void on_alive(void *ctx)
{
  (void)ctx;
  APP_PRINTF("#alive uptime=%u forwarded=%u dropped=%u acks=%u diag=%u listening=%d relistens=%u uart_errors=%u stack_peak=%u\n",
             (unsigned)((HAL_GetTick() - boot_tick) / 1000), (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks,
             (unsigned)n_diag, Radio.GetStatus() == RF_RX_RUNNING || transmitting, (unsigned)n_relistens,
             (unsigned)vcom_rx_errors(), (unsigned)stackmon_peak());
  /* Timer context: only flag it; the radio is touched from the sequencer task. */
  if (!transmitting && ws_silent_for(HAL_GetTick(), last_radio_event_ms, SILENCE_RELISTEN_MS))
  {
    relisten_due = 1;
    UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0);
  }
}

static void on_line(char *line)
{
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  if (line[0] == '#') return;
  if (!strcmp(line, "TEST-FAULT")) fault_test();
  if (!strcmp(line, "TEST-HANG")) { APP_PRINTF("#test-hang: main loop stops; watchdog must reset in ~8 s\n"); HAL_Delay(50); for (;;) { } }
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
  tx_start_ms = HAL_GetTick();
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
  events.RxDone = on_rx_done;
  events.RxError = on_rx_error;
  events.RxTimeout = on_rx_timeout;
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  boot_tick = HAL_GetTick();
  last_radio_event_ms = boot_tick;
  leds_init();
  watchdog_start(rx_healthy);
  Radio.Init(&events);
  ws_radio_configure(1);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process);
  console_init(on_line);
  APP_PRINTF("#boot role=rx fw=%s reset=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION, watchdog_reset_cause(),
             (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  UTIL_TIMER_Create(&alive_timer, 60000, UTIL_TIMER_PERIODIC, on_alive, NULL);
  UTIL_TIMER_Start(&alive_timer);
  listen();
}
