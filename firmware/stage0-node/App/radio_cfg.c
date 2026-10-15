#include "radio_cfg.h"
#include "radio_driver.h"
#include "radio.h"

void ws_radio_configure(int continuous)
{
  Radio.SetChannel(WS_RF_FREQUENCY_HZ);
  Radio.SetTxConfig(MODEM_LORA, WS_TX_POWER_DBM, 0, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_LORA_CR,
                    WS_LORA_PREAMBLE, false, true, 0, 0, false, WS_TX_TIMEOUT_MS);
  Radio.SetRxConfig(MODEM_LORA, WS_LORA_BANDWIDTH, WS_LORA_SF, WS_LORA_CR, 0, WS_LORA_PREAMBLE,
                    WS_LORA_SYMBOL_TO, false, 0, true, 0, 0, false, continuous ? true : false);
  Radio.SetMaxPayloadLength(MODEM_LORA, 255);
}

void ws_radio_last_packet(uint8_t buf[255], uint8_t *len, int8_t *rssi, int8_t *snr)
{
  uint8_t start = 0; PacketStatus_t ps;
  SUBGRF_GetRxBufferStatus(len, &start);
  SUBGRF_ReadBuffer(start, buf, *len);
  SUBGRF_GetPacketStatus(&ps);
  *rssi = ps.Params.LoRa.RssiPkt; *snr = ps.Params.LoRa.SnrPkt;
}

int8_t ws_radio_rssi_now(void) { return SUBGRF_GetRssiInst(); }

/* ST's RadioSleep() (radio.c) is SUBGRF_SetSleep + RADIO_DELAY_MS(2), a 2 ms HAL_Delay busy-wait
   (radio_conf.h) after every exchange. The wait only guards a command sent right after sleep; the
   next one here comes at the next minute's exchange, and SUBGRF wakes the chip and waits on its
   BUSY line first (SUBGHZ_CheckDeviceReady). Same sleep (warm start), no wait. */
void ws_radio_sleep(void)
{
  SleepParams_t params = { 0 };
  params.Fields.WarmStart = 1;
  SUBGRF_SetSleep(params);
}
