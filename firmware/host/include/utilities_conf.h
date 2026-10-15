/* Host stand-in for the board's utilities_conf.h: the trace sizes App/console.c and the RX harness use
   (same values as firmware/board/nucleo-wl55jc/Core/Inc/utilities_conf.h). */
#ifndef HOST_UTILITIES_CONF_H
#define HOST_UTILITIES_CONF_H
#define UTIL_ADV_TRACE_TMP_BUF_SIZE (640U)   /* one formatted line; a longer one is cut */
#define UTIL_ADV_TRACE_FIFO_SIZE    (2048U)  /* lines waiting for the UART */
#endif
