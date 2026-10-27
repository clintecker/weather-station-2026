/* The bench OLED on SPI1: Adafruit #2674, 2.7" 128 x 64, SSD1325, in SPI mode (R19 and R21 fitted).
 *   OLED pin 7 SCLK  <- CN5.6  D13 PA5 (SPI1_SCK)
 *   OLED pin 8 DIN   <- CN5.4  D11 PA7 (SPI1_MOSI)
 *   OLED pin 15 CS   <- CN5.3  D10 PA4 (a GPIO, low while sending)
 *   OLED pin 4 DC    <- CN5.1  D8  PC2 (low: command, high: data)
 *   OLED pin 16 RST  <- CN9.8  D7  PC1 (low: reset)
 * UM2592 Rev 4 Table 17. Write only: the SSD1325 sends nothing back over SPI, so the tool cannot tell
 * whether a display is there. */
#ifndef OLED_H_INCLUDED
#define OLED_H_INCLUDED

#include "oled_fb.h"

void oled_init(void);                    /* the pins, SPI1, a reset pulse and the SSD1325 set-up */
int oled_show(const oled_fb *fb);       /* one frame (4096 bytes, about 45 ms); 0 or -1 on an SPI timeout */
unsigned oled_spi_hz(void);              /* the SPI clock chosen, for the start line */

#endif
