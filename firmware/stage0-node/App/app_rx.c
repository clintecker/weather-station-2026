/* Stage-0 RX: transparent radio <-> USB bridge for the indoor receiver.
 *
 * Upstream: every received frame that looks like a draft-2 observation (56 bytes, "WS",
 * version 2, kind 1) is written as one lowercase hex line. Downstream: every hex line from
 * the host that looks like a draft-2 ACK is transmitted once. This board holds no key and
 * never acknowledges anything itself; the host is the sole ACK authority (docs/protocol.md).
 * All other output lines start with '#' and are diagnostics for the host log. */
#include <string.h>
#include "console.h"
#include "leds.h"
#include "radio.h"
#include "radio_cfg.h"
#include "stm32_seq.h"
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

static void post(int ev) { event = ev; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0); }
static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  rx_len = size > sizeof rx_frame ? sizeof rx_frame : size;
  memcpy(rx_frame, payload, rx_len);
  rx_rssi = rssi;
  rx_snr = snr;
  post(EV_RX);
}
static void on_rx_error(void) { post(EV_RX_ERROR); }
static void on_rx_timeout(void) { post(EV_RX_ERROR); }
static void on_tx_done(void) { post(EV_TX_DONE); }
static void on_tx_timeout(void) { post(EV_TX_TIMEOUT); }

static void listen(void)
{
  transmitting = 0;
  Radio.Rx(0); /* continuous */
}

static void process(void)
{
  switch (event)
  {
    case EV_RX:
      if (rx_len == WS_OBS_FRAME_LEN && rx_frame[0] == 'W' && rx_frame[1] == 'S' &&
          rx_frame[2] == WS_FRAME_VERSION && rx_frame[3] == WS_KIND_OBS)
      {
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

static void on_line(char *line)
{
  uint8_t frame[WS_ACK_FRAME_LEN + 1];
  if (line[0] == '#') return;
  if (!strcmp(line, "STATUS"))
  {
    APP_PRINTF("#status role=rx forwarded=%u dropped=%u acks=%u\n",
               (unsigned)n_forwarded, (unsigned)n_dropped, (unsigned)n_acks);
    return;
  }
  int n = hex_decode(line, frame, sizeof frame);
  if (n != WS_ACK_FRAME_LEN || frame[0] != 'W' || frame[1] != 'S' ||
      frame[2] != WS_FRAME_VERSION || frame[3] != WS_KIND_ACK)
  {
    APP_PRINTF("#host reject len=%d\n", n);
    led_flash(LED_RED, 400);
    return;
  }
  transmitting = 1;
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
  events.RxDone = on_rx_done;
  events.RxError = on_rx_error;
  events.RxTimeout = on_rx_timeout;
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  leds_init();
  Radio.Init(&events);
  ws_radio_configure(1);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, UTIL_SEQ_RFU, process);
  console_init(on_line);
  APP_PRINTF("#boot role=rx fw=%s freq=%u bw=%u sf=%u\n", WS_FW_VERSION,
             (unsigned)WS_RF_FREQUENCY_HZ, WS_LORA_BANDWIDTH, WS_LORA_SF);
  listen();
}
