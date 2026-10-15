#ifndef RADIO_CFG_H
#define RADIO_CFG_H
#include <stdint.h>
/* Stage-0 RF configuration (docs/hardware/nucleo-wl55jc-bringup.md, "RF configuration
 * decision"): 915.0 MHz LoRa, 500 kHz bandwidth = FCC 15.247(a)(2) digital-modulation
 * class. Power and spreading factor are bench values; tune SF/power for the H01
 * placement link budget, never bandwidth below 500 kHz. Both boards must match. */
#define WS_RF_FREQUENCY_HZ   915000000UL
#define WS_TX_POWER_DBM      0
#define WS_LORA_BANDWIDTH    2      /* 0:125 1:250 2:500 kHz */
#define WS_LORA_SF           7
#define WS_LORA_CR           1      /* 4/5 */
#define WS_LORA_PREAMBLE     8
#define WS_LORA_SYMBOL_TO    0      /* off: at SF7/500 kHz 5 symbols = 1.3 ms would close the ACK window early; the window timer bounds RX instead */
#define WS_TX_TIMEOUT_MS     3000
/* continuous=1 keeps receiving after each packet (RX bridge); 0 for single windows (TX node). */
void ws_radio_configure(int continuous);
/* For a reception that failed its checks (radio interrupt context): the packet the radio stored
   (length, bytes, packet RSSI/SNR), valid after a payload CRC error; and the channel RSSI now. */
void ws_radio_last_packet(uint8_t buf[255], uint8_t *len, int8_t *rssi, int8_t *snr);
int8_t ws_radio_rssi_now(void);
/* In an RxDone callback: 1 (and cleared) if this "received" packet failed its payload CRC; RxError
   follows it in the same interrupt (radio_cfg.c). */
int ws_radio_take_crc_error(void);
/* Radio.Sleep() without its 2 ms busy-wait (radio_cfg.c). */
void ws_radio_sleep(void);
#endif
