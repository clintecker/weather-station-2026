/* Host stand-in for the board's usart_if.h (firmware/board/nucleo-wl55jc/Core/Inc): the USART2 receive
   calls App/console.c and App/app_rx.c use. Implemented by firmware/host/rx_harness.c. */
#ifndef HOST_USART_IF_H
#define HOST_USART_IF_H
#include <stdint.h>
typedef enum { UTIL_ADV_TRACE_OK = 0, UTIL_ADV_TRACE_INVALID_PARAM = -1 } UTIL_ADV_TRACE_Status_t;
UTIL_ADV_TRACE_Status_t vcom_ReceiveInit(void (*RxCb)(uint8_t *rxChar, uint16_t size, uint8_t error));
uint32_t vcom_rx_errors(void);
int vcom_rx_armed(void);       /* 1 while a one-character receive is pending */
void vcom_rx_rearm(void);
void vcom_tx_progress(uint32_t *started, uint32_t *done);
#endif
