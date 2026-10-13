#include "radio_cfg.h"
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
