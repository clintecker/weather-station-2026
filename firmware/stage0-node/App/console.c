#include "console.h"
#include <string.h>
#include "stm32_seq.h"
#include "sys_app.h"
#include "usart_if.h"
#include "utilities_def.h"

static char isr_buf[CONSOLE_MAX_LINE];
static uint16_t isr_len;
static uint8_t isr_overflow;
static char line[CONSOLE_MAX_LINE + 1];
static volatile uint8_t line_ready;
static void (*handler)(char *line);

/* UART receive interrupt, one character at a time. While a completed line waits for the
 * main loop, further input is dropped (the host sends one line per exchange). */
static void on_char(uint8_t *c, uint16_t size, uint8_t error)
{
  (void)size;
  if (error || line_ready) return;
  if (*c == '\r') return;
  if (*c == '\n')
  {
    if (!isr_overflow && isr_len)
    {
      memcpy(line, isr_buf, isr_len);
      line[isr_len] = 0;
      memset(isr_buf, 0, isr_len); /* a PROVISION key must not linger in the ISR buffer */
      line_ready = 1;
      UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Console, CFG_SEQ_Prio_0);
    }
    isr_len = 0;
    isr_overflow = 0;
    return;
  }
  if (isr_len >= CONSOLE_MAX_LINE) { isr_overflow = 1; return; }
  isr_buf[isr_len++] = (char)*c;
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

static int nibble(char c)
{
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int hex_decode(const char *text, uint8_t *out, int max)
{
  int n = 0;
  while (text[0] && text[1])
  {
    int hi = nibble(text[0]), lo = nibble(text[1]);
    if (hi < 0 || lo < 0 || n >= max) return -1;
    out[n++] = (uint8_t)(hi << 4 | lo);
    text += 2;
  }
  return text[0] ? -1 : n;
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
