/* Host stand-in for ST's SubGHz_Phy radio.h: the calls and callbacks app_tx.c uses. */
#ifndef HOST_RADIO_H
#define HOST_RADIO_H
#include <stdint.h>
typedef enum { RADIO_STATUS_OK, RADIO_STATUS_ERROR } radio_status_t;
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
};
extern const struct Radio_s Radio;
#endif
