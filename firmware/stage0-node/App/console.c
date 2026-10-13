#include "console.h"
#include <string.h>
#include "stm32_seq.h"
#include "sys_app.h"
#include "usart_if.h"
#include "utilities_def.h"

static ws_line_asm isr_line;
static char line[WS_LINE_MAX + 1];
static volatile uint8_t line_ready;
static void (*handler)(char *line);

/* UART receive interrupt, one character at a time. While a completed line waits for the
 * main loop, further input is dropped (the host sends one line per exchange). */
static void on_char(uint8_t *c, uint16_t size, uint8_t error)
{
  (void)size;
  if (error || line_ready) return;
  if (ws_line_feed(&isr_line, *c, line) > 0)
  {
    line_ready = 1;
    UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Console, CFG_SEQ_Prio_0);
  }
}

static void console_task(void)
{
  if (line_ready && handler) handler(line);
  line_ready = 0;
}

void console_init(void (*on_line)(char *line))
{
  handler = on_line;
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Console, UTIL_SEQ_RFU, console_task);
  vcom_ReceiveInit(on_char);
}

void hex_print(const uint8_t *data, int len)
{
  static const char digits[] = "0123456789abcdef";
  char text[2 * 64 + 1];
  if (len > 64) len = 64;
  for (int i = 0; i < len; i++)
  {
    text[2 * i] = digits[data[i] >> 4];
    text[2 * i + 1] = digits[data[i] & 15];
  }
  text[2 * len] = 0;
  APP_PRINTF("%s\n", text);
}
