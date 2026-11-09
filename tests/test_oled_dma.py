"""The bench OLED's DMA driver (firmware/stage0-node/App/oled_dma.c) on the host, and the field build without it.

oled_dma.c is compiled unchanged against a small stand-in for ST's HAL and LL drivers (written below):
the GPIO output levels, SPI1 (enabled, its DMA request, a FIFO the test can hold busy), DMA1 channel 1
(its address, length and enable, the TC and TE flags the test raises before calling the vector), and
ST's UTIL timers, fired by the test. A transfer starts when the channel is enabled and SPI1 requests
DMA; the stand-in records its bytes and the CS and DC levels then. HAL_Delay and HAL_GetTick are not
in the stand-in at all, so a wait in the driver would not even compile.

The field build (WS_BENCH_OLED=0, the default) must link no display code: `make field-check` builds
ROLE=tx and fails on any oled_, scr_, ssd1325_ or font5x7 symbol. It needs the ARM toolchain and
vendor/ (the firmware CI job), and skips without them."""
import ctypes
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

try:
    from toolchain import CC_STRICT, ROOT, fresh_copy, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, fresh_copy, host_library, needs_cc    # python -m unittest tests.<module>

HAL_STUB = r'''
#ifndef STUB_HAL_H
#define STUB_HAL_H
#include <stdint.h>
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t odr; } GPIO_TypeDef;
extern GPIO_TypeDef stub_gpioa, stub_gpioc;
#define GPIOA (&stub_gpioa)
#define GPIOC (&stub_gpioc)
#define GPIO_PIN_1 (1U << 1)
#define GPIO_PIN_2 (1U << 2)
#define GPIO_PIN_4 (1U << 4)
#define GPIO_PIN_5 (1U << 5)
#define GPIO_PIN_7 (1U << 7)
enum { GPIO_MODE_OUTPUT_PP, GPIO_MODE_AF_PP };
enum { GPIO_NOPULL };
enum { GPIO_SPEED_FREQ_LOW };
enum { GPIO_AF5_SPI1 = 5 };
typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init);
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state);
typedef enum { DMA1_Channel1_IRQn = 11, SPI1_IRQn = 34 } IRQn_Type;
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub);
void HAL_NVIC_EnableIRQ(IRQn_Type irq);
uint32_t HAL_RCC_GetPCLK2Freq(void);
#define __HAL_RCC_GPIOA_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOC_CLK_ENABLE() ((void)0)
#define __HAL_RCC_SPI1_CLK_ENABLE() ((void)0)
#define __HAL_RCC_DMAMUX1_CLK_ENABLE() ((void)0)
#define __HAL_RCC_DMA1_CLK_ENABLE() ((void)0)
extern uint32_t stub_primask;
#define __get_PRIMASK() (stub_primask)
#define __disable_irq() (stub_primask = 1U)
#define __set_PRIMASK(m) (stub_primask = (m))
#endif
'''

LL_DMA_STUB = r'''
#ifndef STUB_LL_DMA_H
#define STUB_LL_DMA_H
#include <stdint.h>
typedef struct { int unused; } DMA_TypeDef;
extern DMA_TypeDef stub_dma1;
#define DMA1 (&stub_dma1)
#define LL_DMA_CHANNEL_1 0U
#define LL_DMA_DIRECTION_MEMORY_TO_PERIPH (1U << 4)
#define LL_DMA_MODE_NORMAL 0U
#define LL_DMA_PERIPH_NOINCREMENT 0U
#define LL_DMA_MEMORY_INCREMENT (1U << 7)
#define LL_DMA_PDATAALIGN_BYTE 0U
#define LL_DMA_MDATAALIGN_BYTE 0U
#define LL_DMA_PRIORITY_LOW 0U
#define LL_DMAMUX_REQ_SPI1_TX 8U
void LL_DMA_EnableChannel(DMA_TypeDef *d, uint32_t ch);
void LL_DMA_DisableChannel(DMA_TypeDef *d, uint32_t ch);
void LL_DMA_ConfigTransfer(DMA_TypeDef *d, uint32_t ch, uint32_t config);
void LL_DMA_SetPeriphRequest(DMA_TypeDef *d, uint32_t ch, uint32_t request);
void LL_DMA_SetPeriphAddress(DMA_TypeDef *d, uint32_t ch, uint32_t address);
void LL_DMA_SetMemoryAddress(DMA_TypeDef *d, uint32_t ch, uint32_t address);
void LL_DMA_SetDataLength(DMA_TypeDef *d, uint32_t ch, uint32_t n);
void LL_DMA_EnableIT_TC(DMA_TypeDef *d, uint32_t ch);
void LL_DMA_EnableIT_TE(DMA_TypeDef *d, uint32_t ch);
uint32_t LL_DMA_IsActiveFlag_TC1(DMA_TypeDef *d);
uint32_t LL_DMA_IsActiveFlag_TE1(DMA_TypeDef *d);
void LL_DMA_ClearFlag_GI1(DMA_TypeDef *d);
#endif
'''

LL_SPI_STUB = r'''
#ifndef STUB_LL_SPI_H
#define STUB_LL_SPI_H
#include <stdint.h>
typedef struct { int unused; } SPI_TypeDef;
extern SPI_TypeDef stub_spi1;
#define SPI1 (&stub_spi1)
enum { LL_SPI_MODE_MASTER = 1, LL_SPI_HALF_DUPLEX_TX = 2, LL_SPI_POLARITY_LOW = 0, LL_SPI_PHASE_1EDGE = 0, LL_SPI_MSB_FIRST = 0,
       LL_SPI_NSS_SOFT = 1, LL_SPI_DATAWIDTH_8BIT = 7, LL_SPI_TX_FIFO_EMPTY = 0 };
/* The BR field codes, 0-7 (DIV2 ... DIV256). */
enum { LL_SPI_BAUDRATEPRESCALER_DIV2, LL_SPI_BAUDRATEPRESCALER_DIV4, LL_SPI_BAUDRATEPRESCALER_DIV8, LL_SPI_BAUDRATEPRESCALER_DIV16,
       LL_SPI_BAUDRATEPRESCALER_DIV32, LL_SPI_BAUDRATEPRESCALER_DIV64, LL_SPI_BAUDRATEPRESCALER_DIV128, LL_SPI_BAUDRATEPRESCALER_DIV256 };
void LL_SPI_Enable(SPI_TypeDef *s);
void LL_SPI_Disable(SPI_TypeDef *s);
void LL_SPI_SetMode(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetTransferDirection(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetClockPolarity(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetClockPhase(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetTransferBitOrder(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetNSSMode(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetDataWidth(SPI_TypeDef *s, uint32_t v);
void LL_SPI_SetBaudRatePrescaler(SPI_TypeDef *s, uint32_t v);
void LL_SPI_ClearFlag_MODF(SPI_TypeDef *s);
void LL_SPI_EnableIT_ERR(SPI_TypeDef *s);
void LL_SPI_DisableIT_ERR(SPI_TypeDef *s);
void LL_SPI_EnableDMAReq_TX(SPI_TypeDef *s);
void LL_SPI_DisableDMAReq_TX(SPI_TypeDef *s);
uint32_t LL_SPI_DMA_GetRegAddr(SPI_TypeDef *s);
uint32_t LL_SPI_GetTxFIFOLevel(SPI_TypeDef *s);
uint32_t LL_SPI_IsActiveFlag_BSY(SPI_TypeDef *s);
#endif
'''

TIMER_STUB = r'''
#ifndef STUB_TIMER_H
#define STUB_TIMER_H
#include <stdint.h>
typedef enum { UTIL_TIMER_ONESHOT, UTIL_TIMER_PERIODIC } UTIL_TIMER_Mode_t;
typedef enum { UTIL_TIMER_OK, UTIL_TIMER_INVALID_PARAM, UTIL_TIMER_HW_ERROR, UTIL_TIMER_UNKNOWN_ERROR } UTIL_TIMER_Status_t;
typedef struct { uint32_t period; UTIL_TIMER_Mode_t mode; void (*callback)(void *); void *argument; int running; } UTIL_TIMER_Object_t;
UTIL_TIMER_Status_t UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*callback)(void *),
                                      void *argument);
UTIL_TIMER_Status_t UTIL_TIMER_Start(UTIL_TIMER_Object_t *t);
UTIL_TIMER_Status_t UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t);
UTIL_TIMER_Status_t UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period);
#endif
'''

# The node's console output (sys_app.h); and the CMSIS device header as far as App/busymon.h needs it
# (its interrupt timing functions are in the shim).
SYS_APP_STUB = r'''
#ifndef STUB_SYS_APP_H
#define STUB_SYS_APP_H
void stub_print(const char *s);
#define APP_PRINTF(s) stub_print(s)
#endif
'''
DEVICE_STUB = r'''
#include <stdint.h>
typedef struct { uint32_t CYCCNT; } DWT_Type;
extern DWT_Type stub_dwt;
#define DWT (&stub_dwt)
'''

SHIM = r'''
#include <string.h>
#include "stm32wlxx_hal.h"
#include "stm32wlxx_ll_dma.h"
#include "stm32wlxx_ll_spi.h"
#include "stm32_timer.h"
#include "oled_dma.h"
#include "busymon.h"
DWT_Type stub_dwt;
uint32_t busymon_isr_enter(void) { return 0; }
void busymon_isr_exit(uint32_t t0, const char *name) { (void)t0; (void)name; }
GPIO_TypeDef stub_gpioa, stub_gpioc;
DMA_TypeDef stub_dma1;
SPI_TypeDef stub_spi1;
uint32_t stub_primask;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init) { (void)port; (void)init; }
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
  if (state == GPIO_PIN_SET) port->odr |= pin; else port->odr &= ~(uint32_t)pin;
}
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)irq; (void)pre; (void)sub; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { (void)irq; }
uint32_t HAL_RCC_GetPCLK2Freq(void) { return 48000000U; }
/* Console lines. */
static int fault_lines, other_lines;
void stub_print(const char *s) { if (strcmp(s, "#oled fault\n") == 0) fault_lines++; else other_lines++; }
/* DMA1 channel 1 and SPI1. The DMA's 32-bit memory address is the low half of a pointer into this
   library's own data, where txbuf and cmdbuf are: the high half is oled_dma_buffer()'s. */
static uint32_t dma_mem, dma_len, dma_request, dma_config, dma_tc, dma_te;
static int dma_on, spi_on, spi_dmareq, spi_err_it, spi_fifo_busy;
static uint32_t spi_br;
static uint8_t last[4096];
static uint32_t last_len, transfers, last_cs, last_dc;
static void maybe_start(void)
{
  if (!(dma_on && spi_on && spi_dmareq)) return;
  const uint8_t *p = (const uint8_t *)(((uintptr_t)oled_dma_buffer() & ~(uintptr_t)0xFFFFFFFFu) | dma_mem);
  last_len = dma_len < sizeof last ? dma_len : sizeof last;
  memcpy(last, p, last_len);
  transfers++;
  last_cs = (stub_gpioa.odr >> 4) & 1U;
  last_dc = (stub_gpioc.odr >> 2) & 1U;
}
void LL_DMA_EnableChannel(DMA_TypeDef *d, uint32_t ch) { (void)d; (void)ch; dma_on = 1; maybe_start(); }
void LL_DMA_DisableChannel(DMA_TypeDef *d, uint32_t ch) { (void)d; (void)ch; dma_on = 0; }
void LL_DMA_ConfigTransfer(DMA_TypeDef *d, uint32_t ch, uint32_t config) { (void)d; (void)ch; dma_config = config; }
void LL_DMA_SetPeriphRequest(DMA_TypeDef *d, uint32_t ch, uint32_t request) { (void)d; (void)ch; dma_request = request; }
void LL_DMA_SetPeriphAddress(DMA_TypeDef *d, uint32_t ch, uint32_t address) { (void)d; (void)ch; (void)address; }
void LL_DMA_SetMemoryAddress(DMA_TypeDef *d, uint32_t ch, uint32_t address) { (void)d; (void)ch; dma_mem = address; }
void LL_DMA_SetDataLength(DMA_TypeDef *d, uint32_t ch, uint32_t n) { (void)d; (void)ch; dma_len = n; }
void LL_DMA_EnableIT_TC(DMA_TypeDef *d, uint32_t ch) { (void)d; (void)ch; }
void LL_DMA_EnableIT_TE(DMA_TypeDef *d, uint32_t ch) { (void)d; (void)ch; }
uint32_t LL_DMA_IsActiveFlag_TC1(DMA_TypeDef *d) { (void)d; return dma_tc; }
uint32_t LL_DMA_IsActiveFlag_TE1(DMA_TypeDef *d) { (void)d; return dma_te; }
void LL_DMA_ClearFlag_GI1(DMA_TypeDef *d) { (void)d; dma_tc = dma_te = 0; }
void LL_SPI_Enable(SPI_TypeDef *s) { (void)s; spi_on = 1; maybe_start(); }
void LL_SPI_Disable(SPI_TypeDef *s) { (void)s; spi_on = 0; }
void LL_SPI_SetMode(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetTransferDirection(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetClockPolarity(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetClockPhase(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetTransferBitOrder(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetNSSMode(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetDataWidth(SPI_TypeDef *s, uint32_t v) { (void)s; (void)v; }
void LL_SPI_SetBaudRatePrescaler(SPI_TypeDef *s, uint32_t v) { (void)s; spi_br = v; }
void LL_SPI_ClearFlag_MODF(SPI_TypeDef *s) { (void)s; }
void LL_SPI_EnableIT_ERR(SPI_TypeDef *s) { (void)s; spi_err_it = 1; }
void LL_SPI_DisableIT_ERR(SPI_TypeDef *s) { (void)s; spi_err_it = 0; }
void LL_SPI_EnableDMAReq_TX(SPI_TypeDef *s) { (void)s; spi_dmareq = 1; maybe_start(); }
void LL_SPI_DisableDMAReq_TX(SPI_TypeDef *s) { (void)s; spi_dmareq = 0; }
uint32_t LL_SPI_DMA_GetRegAddr(SPI_TypeDef *s) { (void)s; return 0x4001300CU; }
uint32_t LL_SPI_GetTxFIFOLevel(SPI_TypeDef *s) { (void)s; return spi_fifo_busy ? 3U : LL_SPI_TX_FIFO_EMPTY; }
uint32_t LL_SPI_IsActiveFlag_BSY(SPI_TypeDef *s) { (void)s; return (uint32_t)spi_fifo_busy; }
/* The one timer oled_dma.c creates; the test fires it. */
static UTIL_TIMER_Object_t *timer;
UTIL_TIMER_Status_t UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*callback)(void *),
                                      void *argument)
{
  *t = (UTIL_TIMER_Object_t){ .period = period, .mode = mode, .callback = callback, .argument = argument };
  timer = t;
  return UTIL_TIMER_OK;
}
UTIL_TIMER_Status_t UTIL_TIMER_Start(UTIL_TIMER_Object_t *t) { t->running = 1; return UTIL_TIMER_OK; }
UTIL_TIMER_Status_t UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t) { t->running = 0; return UTIL_TIMER_OK; }
UTIL_TIMER_Status_t UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period) { t->period = period; return UTIL_TIMER_OK; }
/* The running timer's period after it fires (one-shot: stopped first, as ST's), 0 if none runs. */
uint32_t t_fire(void)
{
  if (!timer || !timer->running) return 0;
  uint32_t period = timer->period;
  timer->running = 0;
  timer->callback(timer->argument);
  return period;
}
uint32_t t_timer_running(void) { return timer && timer->running ? timer->period : 0U; }
void DMA1_Channel1_IRQHandler(void);
void SPI1_IRQHandler(void);
void t_dma_complete(void) { dma_tc = 1; DMA1_Channel1_IRQHandler(); }
void t_dma_error(void) { dma_te = 1; DMA1_Channel1_IRQHandler(); }
void t_spi_irq(void) { SPI1_IRQHandler(); }
void t_fifo_busy(int busy) { spi_fifo_busy = busy; }
uint32_t t_transfers(void) { return transfers; }
uint32_t t_last_len(void) { return last_len; }
uint32_t t_last_byte(uint32_t i) { return last[i]; }
uint32_t t_last_cs(void) { return last_cs; }
uint32_t t_last_dc(void) { return last_dc; }
uint32_t t_cs(void) { return (stub_gpioa.odr >> 4) & 1U; }
uint32_t t_rst(void) { return (stub_gpioc.odr >> 1) & 1U; }
int t_dma_on(void) { return dma_on; }
int t_spi_on(void) { return spi_on; }
int t_spi_err_it(void) { return spi_err_it; }
uint32_t t_spi_br(void) { return spi_br; }
uint32_t t_dma_request(void) { return dma_request; }
uint32_t t_primask(void) { return stub_primask; }
int t_fault_lines(void) { return fault_lines; }
int t_other_lines(void) { return other_lines; }
'''

APP = ROOT/'firmware/stage0-node/App'
SOURCE = APP/'oled_dma.c'
BOARD = ROOT/'firmware/board/nucleo-wl55jc'
DRIVER = [SOURCE, BOARD/'oled_spi1.c', ROOT/'firmware/common/ssd1325.c']   # the driver, its pins and SPI1, the panel data
NODE = ROOT/'firmware/stage0-node'
TOOLCHAIN_GCC = Path.home()/'.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-gcc'
HAVE_ARM = TOOLCHAIN_GCC.exists() and (ROOT/'vendor/STM32CubeWL').exists()
RESET_LOW_MS, RESET_SETTLE_MS, DRAIN_MS, DMA_TIMEOUT_MS = 10, 500, 1, 200
FRAME = 4096
WINDOW = [0x15, 0x00, 0x3F, 0x75, 0x00, 0x3F]


def setup_bytes():
    """Adafruit's set-up sequence for this panel (Adafruit_SSD1325_Library, begin()), which the bench tool sends too
    (firmware/common/ssd1325.c): display off, clock, multiplex, offset, start line, master configuration, re-map,
    current range, grey-scale table, contrast, row period, phase length, pre-charge, VCOMH, VSL, normal, on."""
    return [0xAE, 0xB3, 0xF1, 0xA8, 0x3F, 0xA2, 0x4C, 0xA1, 0x00, 0xAD, 0x02, 0xA0, 0x56, 0x86,
            0xB8, 0x01, 0x11, 0x22, 0x32, 0x43, 0x54, 0x65, 0x76, 0x81, 0x7F, 0xB2, 0x51, 0xB1, 0x55,
            0xB4, 0x02, 0xB0, 0x28, 0xBE, 0x1C, 0xBF, 0x0F, 0xA4, 0xAF]


def includes(owner):
    """The include flags of an oled_dma.c host build: the stand-ins (written into a directory the owner, a
    TestCase class, removes), then the node's App, the board's generated pins (gen/) and its Core/Inc
    (its sys_conf.h)."""
    import tempfile
    stub = tempfile.TemporaryDirectory()
    owner.addClassCleanup(stub.cleanup)
    for name, text in (('stm32wlxx_hal.h', HAL_STUB), ('stm32wlxx_ll_dma.h', LL_DMA_STUB), ('stm32wlxx_ll_spi.h', LL_SPI_STUB),
                       ('stm32_timer.h', TIMER_STUB), ('sys_app.h', SYS_APP_STUB), ('stm32wlxx.h', DEVICE_STUB)):
        (Path(stub.name)/name).write_text(text)
    return ['-I', stub.name, '-I', APP, '-I', ROOT/'firmware/common', '-I', BOARD, '-I', BOARD/'gen', '-I', BOARD/'Core/Inc']


@needs_cc
class OledDma(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = host_library(cls, 'oleddma', '-DOLED_DMA_RAM2=', *includes(cls), *DRIVER, files={'shim.c': SHIM})

    def setUp(self):
        self.lib = fresh_copy(type(self), self.built._name)
        self.lib.oled_dma_send.argtypes = [ctypes.c_char_p]

    def ready(self):
        """oled_dma_init, then the reset pulse, the settle time and the set-up transfer to the end."""
        self.lib.oled_dma_init()
        self.assertEqual(self.lib.t_fire(), RESET_LOW_MS)
        self.assertEqual(self.lib.t_fire(), RESET_SETTLE_MS)
        self.finish()
        self.assertEqual(self.lib.oled_dma_busy(), 0)

    def finish(self):
        """The DMA's transfer-complete interrupt, then the drain timer."""
        self.lib.t_dma_complete()
        self.assertEqual(self.lib.t_fire(), DRAIN_MS)

    def last(self):
        return bytes(self.lib.t_last_byte(i) for i in range(self.lib.t_last_len()))

    def test_init_uses_no_busy_wait(self):
        # oled_dma_init returns with RST low and a 10 ms timer running, nothing sent: each later step
        # is a timer callback or the DMA interrupt.
        self.lib.oled_dma_init()
        self.assertEqual((self.lib.t_rst(), self.lib.t_timer_running(), self.lib.t_transfers()), (0, RESET_LOW_MS, 0))
        self.assertEqual(self.lib.oled_dma_busy(), 1)
        self.assertEqual(self.lib.t_fire(), RESET_LOW_MS)
        self.assertEqual((self.lib.t_rst(), self.lib.t_timer_running(), self.lib.t_transfers()), (1, RESET_SETTLE_MS, 0))
        self.assertEqual(self.lib.t_fire(), RESET_SETTLE_MS)
        # Adafruit's set-up, as the bench tool sends it, in one DMA transfer: commands (DC low), CS low.
        self.assertEqual(self.lib.t_transfers(), 1)
        self.assertEqual(list(self.last()), setup_bytes())
        self.assertEqual((self.lib.t_last_dc(), self.lib.t_last_cs()), (0, 0))
        self.assertEqual(self.lib.t_timer_running(), DMA_TIMEOUT_MS)   # the DMA's interrupt is the next step; the timer its timeout
        self.finish()
        self.assertEqual((self.lib.oled_dma_busy(), self.lib.t_cs()), (0, 1))
        self.assertEqual(self.lib.t_spi_br(), 5)               # DIV64: 750 kHz from 48 MHz, at most 1 MHz
        self.assertEqual(self.lib.t_dma_request(), 8)          # LL_DMAMUX_REQ_SPI1_TX
        self.assertEqual(self.lib.t_primask(), 0)              # interrupts back on
        # And no wait primitive in the source at all (the stand-in has none: it would not compile).
        text = SOURCE.read_text()
        for wait in (r'\bHAL_Delay\b', r'\bHAL_GetTick\b', r'\bwhile\s*\(', r'for\s*\(\s*;\s*;'):
            with self.subTest(wait=wait):
                self.assertIsNone(re.search(wait, text))

    def test_send_while_busy_is_refused(self):
        self.ready()
        frame = bytes((i * 7) & 0xFF for i in range(FRAME))
        self.assertEqual(self.lib.oled_dma_send(frame), 0)
        self.assertEqual(list(self.last()), WINDOW)            # the window first, as commands
        self.assertEqual(self.lib.t_last_dc(), 0)
        self.assertEqual(self.lib.oled_dma_send(frame), -1)    # before the TC interrupt
        self.assertEqual(self.lib.oled_dma_busy(), 1)
        self.finish()
        self.assertEqual(self.last(), frame)                   # then the pixels, as data
        self.assertEqual((self.lib.t_last_dc(), self.lib.t_last_cs()), (1, 0))
        self.assertEqual(self.lib.oled_dma_send(frame), -1)
        self.finish()
        self.assertEqual((self.lib.oled_dma_busy(), self.lib.t_cs()), (0, 1))
        self.assertEqual(self.lib.oled_dma_send(frame), 0)

    def test_a_frame_waits_for_the_fifo_to_drain(self):
        # The TC interrupt only means the last byte entered SPI1's FIFO: CS stays low until it is out.
        self.ready()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)
        self.lib.t_fifo_busy(1)
        self.lib.t_dma_complete()
        self.assertEqual(self.lib.t_fire(), DRAIN_MS)
        self.assertEqual((self.lib.t_cs(), self.lib.t_transfers()), (0, 2))   # still the window
        self.lib.t_fifo_busy(0)
        self.assertEqual(self.lib.t_fire(), DRAIN_MS)
        self.assertEqual(self.lib.t_last_len(), FRAME)

    def test_a_fifo_that_never_drains_is_a_fault(self):
        self.ready()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)
        self.lib.t_fifo_busy(1)
        self.lib.t_dma_complete()
        fired = 0
        while self.lib.t_fire():
            fired += 1
            self.assertLess(fired, 10)
        self.assertEqual((self.lib.oled_dma_faulted(), self.lib.t_fault_lines()), (1, 1))

    def test_a_dma_that_never_ends_is_a_fault_and_enable_restarts(self):
        # A transfer-complete interrupt that never comes: the timeout faults the driver, so it is no longer
        # busy, and oled_dma_enable(1) (B3 off and on) starts the display again.
        for during in ('window', 'pixels'):
            with self.subTest(during=during):
                self.setUp()
                self.ready()
                self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)
                if during == 'pixels':
                    self.finish()
                self.assertEqual(self.lib.oled_dma_busy(), 1)
                self.assertEqual(self.lib.t_fire(), DMA_TIMEOUT_MS)
                self.assertEqual((self.lib.oled_dma_faulted(), self.lib.oled_dma_busy(), self.lib.t_fault_lines()), (1, 0, 1))
                self.assertEqual((self.lib.t_dma_on(), self.lib.t_cs(), self.lib.t_timer_running()), (0, 1, 0))
                self.lib.oled_dma_enable(0)
                self.lib.oled_dma_enable(1)
                self.assertEqual(self.lib.t_fire(), RESET_LOW_MS)
                self.assertEqual(self.lib.t_fire(), RESET_SETTLE_MS)
                self.finish()
                self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)

    def test_dma_error_disables_display_once(self):
        self.ready()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)
        self.lib.t_dma_error()
        self.assertEqual((self.lib.oled_dma_faulted(), self.lib.t_fault_lines(), self.lib.t_other_lines()), (1, 1, 0))
        self.assertEqual((self.lib.t_dma_on(), self.lib.t_spi_on(), self.lib.t_spi_err_it(), self.lib.t_cs()), (0, 0, 0, 1))
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), -2)
        self.assertEqual(self.lib.t_timer_running(), 0)        # no retry
        self.lib.t_dma_error()                                 # a second error, or an SPI one: still one line
        self.lib.t_spi_irq()
        self.assertEqual(self.lib.t_fault_lines(), 1)
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), -2)
        # oled_dma_enable(1) starts again from the reset pulse.
        self.lib.oled_dma_enable(1)
        self.assertEqual((self.lib.oled_dma_faulted(), self.lib.t_rst(), self.lib.t_timer_running()), (0, 0, RESET_LOW_MS))
        self.assertEqual(self.lib.t_fire(), RESET_LOW_MS)
        self.assertEqual(self.lib.t_fire(), RESET_SETTLE_MS)
        self.finish()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)

    def test_a_second_enable_during_the_restart_starts_nothing_more(self):
        # After a fault, enable(1) claims the start-up (busy at once); enabling again, or off, during the reset
        # pulse does not start a second one.
        self.ready()
        sent = self.lib.t_transfers()
        self.lib.t_dma_error()
        self.lib.oled_dma_enable(1)
        self.assertEqual(self.lib.oled_dma_busy(), 1)
        self.lib.oled_dma_enable(1)
        self.assertEqual((self.lib.t_rst(), self.lib.t_timer_running(), self.lib.t_transfers()), (0, RESET_LOW_MS, sent))
        self.assertEqual(self.lib.t_fire(), RESET_LOW_MS)
        self.assertEqual(self.lib.t_fire(), RESET_SETTLE_MS)

    def test_an_spi_error_is_a_fault(self):
        self.ready()
        self.lib.t_spi_irq()
        self.assertEqual((self.lib.oled_dma_faulted(), self.lib.t_fault_lines(), self.lib.t_spi_err_it()), (1, 1, 0))

    def test_off_sends_display_off_then_nothing(self):
        self.ready()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)
        self.lib.oled_dma_enable(0)                            # during a frame: the frame ends first
        self.assertEqual(self.lib.t_transfers(), 2)
        self.finish()
        self.finish()
        self.assertEqual(list(self.last()), [0xAE])
        self.assertEqual(self.lib.t_last_dc(), 0)
        self.finish()
        sent = self.lib.t_transfers()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), -2)
        self.assertEqual((self.lib.t_transfers(), self.lib.t_timer_running(), self.lib.oled_dma_busy()), (sent, 0, 0))
        self.lib.oled_dma_enable(1)
        self.assertEqual(list(self.last()), [0xAF])
        self.finish()
        self.assertEqual(self.lib.oled_dma_send(bytes(FRAME)), 0)

    def test_the_buffer_is_sent_without_a_copy(self):
        self.ready()
        buf = self.lib.oled_dma_buffer
        buf.restype = ctypes.POINTER(ctypes.c_uint8 * FRAME)
        pixels = buf().contents
        for i in range(FRAME):
            pixels[i] = (i * 3) & 0xFF
        self.lib.oled_dma_send.argtypes = [ctypes.c_void_p]
        self.assertEqual(self.lib.oled_dma_send(ctypes.addressof(pixels)), 0)
        self.finish()
        self.assertEqual(self.last(), bytes(pixels))


@needs_cc
class PanelClock(unittest.TestCase):
    """ssd1325_spi_div_log2 (firmware/common/ssd1325.c), which both drivers' SPI1 clock comes from."""
    def test_the_fastest_clock_at_most_1_mhz(self):
        lib = host_library(type(self), 'ssd1325', ROOT/'firmware/common/ssd1325.c')
        div = lib.ssd1325_spi_div_log2
        div.argtypes, div.restype = [ctypes.c_uint32], ctypes.c_uint
        self.assertEqual([div(hz) for hz in (48_000_000, 2_000_000, 2_000_002, 1_000_000, 0, 4_000_000_000)], [6, 1, 2, 1, 1, 8])


@needs_cc
class StopTwo(unittest.TestCase):
    """Stop 2 stops SPI1 and DMA1: the driver does not compile with LOW_POWER_DISABLE 0."""
    def test_low_power_disable_0_does_not_compile(self):
        flags = [str(f) for f in includes(type(self))]
        for value, ok in ((1, True), (0, False)):
            with self.subTest(LOW_POWER_DISABLE=value):
                r = subprocess.run([*CC_STRICT, '-fsyntax-only', '-DOLED_DMA_RAM2=', f'-DLOW_POWER_DISABLE={value}', *flags, str(SOURCE)],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr[-800:])
                if not ok:
                    self.assertIn('Stop 2 would stall SPI1', r.stderr)


@needs_cc
class SubGhzSpiMonitor(unittest.TestCase):
    """DEBUG_SUBGHZSPI_MONITORING takes PA4-PA7, the OLED's SPI1 pins: the driver does not compile with it."""
    def test_subghzspi_monitoring_does_not_compile(self):
        import tempfile
        conf = (ROOT/'firmware/board/nucleo-wl55jc/Core/Inc/sys_conf.h').read_text()
        flags = [str(f) for f in includes(type(self))]
        for value, ok in ((0, True), (1, False)):
            with self.subTest(DEBUG_SUBGHZSPI_MONITORING_ENABLED=value), tempfile.TemporaryDirectory() as tmp:
                text = re.sub(r'(#define DEBUG_SUBGHZSPI_MONITORING_ENABLED\s+)0', rf'\g<1>{value}', conf)
                self.assertIn('DEBUG_SUBGHZSPI_MONITORING_ENABLED', text)
                (Path(tmp)/'sys_conf.h').write_text(text)
                r = subprocess.run([*CC_STRICT, '-fsyntax-only', '-DOLED_DMA_RAM2=', '-I', tmp, *flags, str(SOURCE)],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr[-800:])
                if not ok:
                    self.assertIn('PA4-PA7', r.stderr)


class FieldBuild(unittest.TestCase):
    @unittest.skipUnless(HAVE_ARM or os.environ.get('WS_REQUIRE_ARM') == '1', 'needs the ARM toolchain and vendor/')
    def test_field_build_has_no_display_symbols(self):
        # make field-check builds ROLE=tx with WS_BENCH_OLED=0 and fails on any display symbol.
        r = subprocess.run(['make', '-C', str(NODE), 'field-check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        self.assertIn('field build: no display symbols', r.stdout)

    @unittest.skipUnless(HAVE_ARM or os.environ.get('WS_REQUIRE_ARM') == '1', 'needs the ARM toolchain and vendor/')
    def test_bench_build_puts_the_buffers_in_ram2(self):
        # WS_BENCH_OLED=1 links the driver; its 4 KB send buffer is in RAM2 (0x20008000, 32 KB), not
        # RAM1, and takes no flash: the .bin stays the size of the code.
        r = subprocess.run(['make', '-C', str(NODE), 'ROLE=tx', 'WS_BENCH_OLED=1'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        elf = NODE/'build/tx-oled/stage0-tx.elf'
        nm = subprocess.run([str(TOOLCHAIN_GCC.with_name('arm-none-eabi-nm')), '-S', str(elf)], capture_output=True, text=True, check=True)
        symbols = {f[3]: (int(f[0], 16), int(f[1], 16)) for f in (line.split() for line in nm.stdout.splitlines()) if len(f) == 4}
        address, size = symbols['txbuf']
        self.assertEqual(size, FRAME)
        self.assertTrue(0x20008000 <= address and address + size <= 0x20010000, hex(address))
        self.assertIn('oled_dma_init', symbols)
        self.assertLess((NODE/'build/tx-oled/stage0-tx.bin').stat().st_size, 194560)

    def test_ram2_is_not_loaded(self):
        # Without NOLOAD, a buffer in RAM2 made objcopy -O binary fill the 400 MB from flash to RAM2.
        self.assertIn('RAM2_region (NOLOAD) :', (ROOT/'firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld').read_text())

    @unittest.skipUnless(shutil.which('make'), 'needs make')
    def test_the_flags_are_named_where_they_matter(self):
        # make keeps no memory of WS_BENCH_OLED or WS_POWER_PROFILE: the flash usage line and the budget line
        # name them, and field-check builds into its own directory, never over a build in build/tx.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            show = Path(tmp)/'show.mk'
            show.write_text('show:\n\t@echo "$(strip $(USAGE_ARGS))|$(BUDGET_LABEL)|$(FIELD_CHECK)"\n')
            for flags, usage, label in (([], 'ROLE=tx', 'tx'),
                                        (['WS_BENCH_OLED=1'], 'ROLE=tx WS_BENCH_OLED=1', 'tx, bench OLED'),
                                        (['WS_POWER_PROFILE=2', 'WS_BENCH_OLED=1'], 'ROLE=tx WS_BENCH_OLED=1 WS_POWER_PROFILE=2',
                                         'tx, profile 2, bench OLED')):
                with self.subTest(flags=flags):
                    r = subprocess.run(['make', '-s', '-C', str(NODE), '-f', 'Makefile', '-f', str(show), 'ROLE=tx', *flags,
                                        f'BUILD={tmp}/build', 'show'], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(r.stdout.strip(), f'{usage}|{label}|build/tx-fieldcheck')
        board = (ROOT/'firmware/board/stm32wl/rules.mk').read_text()
        self.assertIn('printf "flash budget%s: ', board)
        self.assertIn('usage: make $(strip $(USAGE_ARGS) flash)', board)

    def test_the_field_check_greps_every_display_prefix(self):
        # The check itself, read from the Makefile: a renamed prefix must not slip past it.
        text = (NODE/'Makefile').read_text()
        rule = text[text.index('field-check:'):]
        for prefix in ('oled_', 'scr_', 'ssd1325_', 'font5x7'):
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, rule[:rule.index('\n\n')])


if __name__ == '__main__':
    unittest.main()
