/* Host stand-in for ST's SubGHz_Phy radio.h: the calls and callbacks app_tx.c and app_rx.c use. */
#ifndef HOST_RADIO_H
#define HOST_RADIO_H
#include <stdint.h>
typedef enum { RADIO_STATUS_OK, RADIO_STATUS_ERROR } radio_status_t;
typedef enum { RF_IDLE = 0, RF_RX_RUNNING, RF_TX_RUNNING, RF_CAD } RadioState_t;   /* ST's order */
typedef struct {
  void (*TxDone)(void);
  void (*TxTimeout)(void);
  void (*RxDone)(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr);
  void (*RxTimeout)(void);
  void (*RxError)(void);
} RadioEvents_t;
struct Radio_s {
  void (*Init)(RadioEvents_t *events);
  radio_status_t (*Send)(uint8_t *buffer, uint8_t size);
  void (*Rx)(uint32_t timeout);
  void (*Sleep)(void);
  void (*Standby)(void);
#ifdef HOST_RADIO_GETSTATUS   /* rx_harness.c; tx_harness.c's positional initializer lists only the members above */
  RadioState_t (*GetStatus)(void);
#endif
};
extern const struct Radio_s Radio;
#endif
