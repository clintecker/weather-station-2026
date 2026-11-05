#ifndef OLED_DMA_H
#define OLED_DMA_H
/* The bench OLED (Adafruit #2674, SSD1325, 128 x 64, 4 bits a pixel) on SPI1, driven by DMA, in the
 * bench build only (WS_BENCH_OLED=1; docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md).
 * A field build compiles none of this and leaves its pins as reset left them.
 *   PA4 CS, PA5 SCLK (SPI1, AF5), PA7 DIN (SPI1, AF5), PC2 DC, PC1 RST; SPI1 mode 0, transmit only,
 *   at most 1 MHz (750 kHz from the 48 MHz PCLK2); DMA1 channel 1 on DMAMUX request SPI1_TX
 *   (channel 5 is the console's USART2 TX).
 * Nothing waits: the reset pulse, the settle time and the end of each transfer are UTIL timer
 * callbacks, each transfer a DMA whose transfer-complete interrupt starts the next step. One frame is
 * a window command (DC low), then OLED_FRAME_BYTES of pixels (DC high): about 44 ms at 750 kHz.
 * A DMA transfer error or an SPI error stops the transfers, disables SPI1, prints "#oled fault" once
 * and leaves the display off until oled_dma_enable(1), which starts again from the reset pulse. */
#include <stdint.h>
#include "oled_draw.h"

/* Pins, SPI1 and DMA, then the reset pulse and Adafruit's set-up sequence, on timers: it returns at
   once, and oled_dma_busy() is 1 until the panel is ready (about 0.5 s). */
void oled_dma_init(void);
/* Starts sending one frame (the SSD1325 layout of ssd1325_frame, oled_draw.h): 0 started, -1 busy
   (a frame, a command or the start-up still under way), -2 disabled or faulted. The frame is copied
   first, unless it is oled_dma_buffer() itself, so the caller may reuse it at once. */
int oled_dma_send(const uint8_t frame[OLED_FRAME_BYTES]);
/* The driver's send buffer (in RAM2): render into it while oled_dma_busy() is 0, then send it, so the
   display needs no second 4 KB frame. Writing it while a frame is under way tears that frame. */
uint8_t *oled_dma_buffer(void);
int oled_dma_busy(void);
/* 0: the display-off command (after a frame under way), then no SPI traffic; 1: the display-on
   command, or after a fault the whole start-up again. */
void oled_dma_enable(int on);
int oled_dma_faulted(void);   /* 1 from a fault until oled_dma_enable(1) */
#endif
