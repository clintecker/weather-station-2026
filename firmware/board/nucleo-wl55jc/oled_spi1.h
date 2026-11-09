/* The bench OLED's pins and SPI1 on the NUCLEO-WL55JC1, shared by the node's DMA driver (stage0-node
 * App/oled_dma.c) and the bench tool's polled one (i2cscan App/oled.c), which differ in everything after
 * this. The wiring: i2cscan App/oled.h. Not in Core/Src, whose every file goes into every project. */
#ifndef OLED_SPI1_H_INCLUDED
#define OLED_SPI1_H_INCLUDED

#include "stm32wlxx_hal.h"
#include "board_pins.h"   /* the pins: board.toml [bench_oled], generated (issue #36) */

#define OLED_CS_PORT BOARD_OLED_CS_PORT
#define OLED_CS_PIN BOARD_OLED_CS_PIN       /* a GPIO, low while sending */
#define OLED_SCK_PIN BOARD_OLED_SCK_PIN     /* SPI1_SCK, on CS's port */
#define OLED_MOSI_PIN BOARD_OLED_MOSI_PIN   /* SPI1_MOSI, on CS's port */
#define OLED_RST_PORT BOARD_OLED_RST_PORT
#define OLED_RST_PIN BOARD_OLED_RST_PIN     /* low resets */
#define OLED_DC_PORT BOARD_OLED_DC_PORT
#define OLED_DC_PIN BOARD_OLED_DC_PIN       /* low command, high data; on RST's port */

/* The clocks, CS, RST and DC high as outputs, SCLK and DIN on SPI1, and SPI1 disabled and set up: master,
   transmit only (half duplex, nothing received, no receive overrun), mode 0 as Adafruit's driver, 8 bits
   MSB first, software NSS, the SSD1325's clock (ssd1325_spi_div_log2 of PCLK2: SPI1 is on APB2). Returns
   that clock in Hz. The caller enables SPI1. */
unsigned oled_spi1_init(void);

#endif
