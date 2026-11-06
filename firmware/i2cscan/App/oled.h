/* The bench OLED on SPI1: Adafruit #2674, 2.7" 128 x 64, SSD1325, in SPI mode (R19 and R21 fitted).
 * The signals land on the morpho CN10 male pins (female-to-male Dupont leads), UM2592 Rev 4 Table 18;
 * their ARDUINO aliases in brackets stay empty, one landing per MCU pin (build-progression record N1,
 * N3; hardware/bench-breadboard-r0/source/wiring.toml, the OLED nets):
 *   OLED pin 7 SCLK  <- CN10.11 PA5 (SPI1_SCK)   [CN5.6, D13]
 *   OLED pin 8 DIN   <- CN10.15 PA7 (SPI1_MOSI)  [CN5.4, D11]
 *   OLED pin 15 CS   <- CN10.17 PA4 (a GPIO, low while sending)   [CN5.3, D10]
 *   OLED pin 4 DC    <- CN10.21 PC2 (low: command, high: data)    [CN5.1, D8]
 *   OLED pin 16 RST  <- CN10.23 PC1 (low: reset)  [CN9.8, D7]
 * Its supply is its own pair straight from the NUCLEO, off every breadboard rail: VCC from CN7.16
 * (3V3), GND to CN10.20 (L_OLED_VCC and L_OLED_GND; unplug VCC in mode B). Write only: the SSD1325
 * sends nothing back over SPI, so the tool cannot tell whether a display is there. */
#ifndef OLED_H_INCLUDED
#define OLED_H_INCLUDED

#include <stdint.h>
#include "oled_draw.h"

void oled_init(void);                    /* the pins, SPI1, a reset pulse and the SSD1325 set-up */
int oled_show(const uint8_t frame[OLED_FRAME_BYTES]);   /* one frame in send order (about 45 ms); 0 or -1 on an SPI timeout */
unsigned oled_spi_hz(void);              /* the SPI clock chosen, for the start line */

#endif
