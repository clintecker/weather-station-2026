/* The SSD1325's set-up, window and SPI clock: see ssd1325.h. */
#include "ssd1325.h"

const uint8_t ssd1325_setup[SSD1325_SETUP_LEN] = {
  SSD1325_DISPLAY_OFF,
  0xB3, 0xF1,              /* clock: divide ratio and oscillator frequency */
  0xA8, 0x3F,              /* multiplex ratio: 64 rows */
  0xA2, 0x4C,              /* display offset 76 (this panel's COM wiring) */
  0xA1, 0x00,              /* start line 0 */
  0xAD, 0x02,              /* master configuration */
  0xA0, 0x56,              /* re-map: vertical address increment, nibble and COM order for this panel */
  0x86,                    /* full current range (0x84 + 2) */
  0xB8, 0x01, 0x11, 0x22, 0x32, 0x43, 0x54, 0x65, 0x76,   /* grey-scale table */
  0x81, 0x7F,              /* contrast */
  0xB2, 0x51,              /* row period */
  0xB1, 0x55,              /* phase length */
  0xB4, 0x02,              /* pre-charge compensation level */
  0xB0, 0x28,              /* pre-charge compensation enable */
  0xBE, 0x1C,              /* VCOMH */
  0xBF, 0x0F,              /* VSL (0x0D | 0x02) */
  0xA4,                    /* normal display */
  SSD1325_DISPLAY_ON,
};

const uint8_t ssd1325_window[6] = { 0x15, 0x00, 0x3F, 0x75, 0x00, 0x3F };

unsigned ssd1325_spi_div_log2(uint32_t pclk_hz)
{
  unsigned k = 1;
  while (k < 8U && (pclk_hz >> k) > SSD1325_SPI_MAX_HZ) k++;   /* bound: 7 more dividers */
  return k;
}
