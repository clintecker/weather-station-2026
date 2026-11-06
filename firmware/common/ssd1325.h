/* The bench OLED's controller, the SSD1325 (Adafruit #2674, 128 x 64, 4 bits a pixel), as data: the set-up
 * sequence, the whole-screen write window, the display on and off commands and the SPI clock it takes. Pure C,
 * shared by the node's DMA driver (stage0-node App/oled_dma.c) and the bench tool's polled one (i2cscan
 * App/oled.c). The set-up is Adafruit's (Adafruit_SSD1325_Library, begin()); the command values are in the
 * SSD1325 datasheet (Solomon Systech, section 9). */
#ifndef SSD1325_H_INCLUDED
#define SSD1325_H_INCLUDED

#include <stdint.h>

#define SSD1325_SETUP_LEN 39U
#define SSD1325_DISPLAY_OFF 0xAEU
#define SSD1325_DISPLAY_ON 0xAFU
#define SSD1325_SPI_MAX_HZ 1000000U   /* Adafruit: "The SSD1325 needs to be slowed down to 1MHz" */

extern const uint8_t ssd1325_setup[SSD1325_SETUP_LEN];   /* commands (DC low), display off first and on last */
extern const uint8_t ssd1325_window[6];                  /* column pairs 0-63, rows 0-63 */
/* The SPI clock's divider as a power of two: the least k in 1..8 with pclk_hz >> k at most SSD1325_SPI_MAX_HZ
   (8 if none is): 6, 750 kHz, from 48 MHz. */
unsigned ssd1325_spi_div_log2(uint32_t pclk_hz);

#endif
