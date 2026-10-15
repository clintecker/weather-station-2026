#define WS_CHECK_FILE 8
#include "busymon.h"
#include "console.h"
#include <string.h>
#include "stm32_seq.h"
#include "sys_app.h"
#include "usart_if.h"
#include "utilities_def.h"
#include "utilities_conf.h"
#include "ws_check.h"
#include "ws_frame.h"
#include "ws_obs.h"

static ws_line_asm isr_line;
static char line[WS_LINE_MAX + 1];
static volatile uint8_t line_ready;

/* UART receive interrupt, one character at a time. While a completed line waits for the
 * main loop, further input is dropped (the host sends one line per exchange). A dropped or damaged
 * character (a receive error) discards the whole line it belongs to, so its tail never becomes a
 * line of its own. */
static void on_char(uint8_t *c, uint16_t size, uint8_t error)
{
  (void)size;
  if (error) { ws_line_discard(&isr_line); return; }
  if (line_ready)
  {
    ws_line_discard(&isr_line);
    if (*c == '\n') isr_line.overflow = 0;   /* the dropped line ended here; the next one is whole */
    return;
  }
  if (ws_line_feed(&isr_line, *c, line) > 0)
  {
    line_ready = 1;
    UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Console, CFG_SEQ_Prio_0);
  }
}

static void console_task(void)
{
  if (line_ready) console_line(line);
  line_ready = 0;
}
BUSYMON_TASK(console_task)

void console_init(void)
{
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Console, UTIL_SEQ_RFU, console_task_timed);
  /* The board's vcom_ReceiveInit always reports OK (usart_if.c); should it not, re-arm the receive
     once now. RX also re-arms a console that is not receiving from its health check. */
  if (!WS_CHECK(vcom_ReceiveInit(on_char) == UTIL_ADV_TRACE_OK)) vcom_rx_rearm();
}

/* The longest frame the protocol allows (every catalog field) must print whole: a truncated line
 * would reach the gateway as a malformed frame, get no ACK, and never be delivered. The line, its
 * newline and NUL must fit the trace buffer. */
#define HEX_FRAME_MAX (WS_FRAME_OVERHEAD + WS_OBS_PLAIN_ALL)
_Static_assert(2U * HEX_FRAME_MAX + 2U <= UTIL_ADV_TRACE_TMP_BUF_SIZE, "longest frame fits one console line");

int hex_print(const uint8_t *data, int len)
{
  char text[2 * HEX_FRAME_MAX + 1];
  /* The callers pass frames ws_air_frame_ok accepted; anything longer is never printed truncated. */
  if (!WS_CHECK(len >= 0 && len <= (int)HEX_FRAME_MAX)) return 0;
  ws_hex_text(data, len, text);
  return APP_PRINTF_OK("%s\n", text);
}
