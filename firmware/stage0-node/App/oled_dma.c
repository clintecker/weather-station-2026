/* The bench OLED on SPI1 by DMA (oled_dma.h). The panel set-up is the bench tool's
 * (firmware/i2cscan/App/oled.c: Adafruit_SSD1325_Library begin(), SSD1325 datasheet section 9), with
 * every wait turned into a step of the state machine below:
 *
 *   OFF -init/enable(1)-> RESET_LOW -10 ms-> RESET_SETTLE -500 ms-> SETUP -+
 *   IDLE <-------------------------------------------------------------------+ (DMA done, drained)
 *   IDLE -send-> WINDOW (DC low) -drained-> PIXELS (DC high) -drained-> IDLE
 *   IDLE -enable(0/1)-> POWER (display off/on command) -drained-> IDLE
 *   any -DMA TE, SPI error, or no DMA end within DMA_TIMEOUT_MS-> OFF, faulted
 *
 * A transfer is one DMA1 channel 1 run of bytes into SPI1's data register (CS low throughout). The
 * DMA's transfer-complete interrupt only means the last byte entered SPI1's FIFO: up to 4 bytes and
 * the shift register are still to go (53 us at 750 kHz), and CS and DC may change only after them.
 * So the interrupt arms a 1 ms one-shot, which finds the FIFO empty and SPI1 idle, raises CS and starts
 * the next step; a FIFO still not empty after DRAIN_TRIES of them is a fault, not a wait. While the DMA
 * runs the same timer is its timeout: a transfer-complete interrupt that never comes is a fault too, so
 * oled_dma_enable(1) can restart the display. */
#include <string.h>
#include "busymon.h"
#include "oled_dma.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "stm32wlxx_ll_dma.h"
#include "stm32wlxx_ll_spi.h"
#include "sys_app.h"
#include "sys_conf.h"

/* Sleep only, never Stop 2: Stop 2 stops SPI1's clock and DMA1, so a frame under way would stall with CS
   low, and the drain timers would find a FIFO that never empties (a fault). */
_Static_assert(LOW_POWER_DISABLE == 1, "the bench OLED needs LOW_POWER_DISABLE 1: Stop 2 would stall SPI1 and its DMA mid-frame");
_Static_assert(DEBUG_SUBGHZSPI_MONITORING_ENABLED == 0, "DEBUG_SUBGHZSPI_MONITORING drives PA4-PA7, the OLED's SPI1 pins");

#define CS_PIN GPIO_PIN_4      /* PA4 */
#define SCK_PIN GPIO_PIN_5     /* PA5, SPI1_SCK AF5 */
#define MOSI_PIN GPIO_PIN_7    /* PA7, SPI1_MOSI AF5 */
#define RST_PIN GPIO_PIN_1     /* PC1 */
#define DC_PIN GPIO_PIN_2      /* PC2 */
#define SPI_MAX_HZ 1000000U    /* Adafruit: "The SSD1325 needs to be slowed down to 1MHz" */
#define RESET_LOW_MS 10U
#define RESET_SETTLE_MS 500U   /* Adafruit's wait after reset, before the first command */
#define DRAIN_MS 1U            /* the FIFO and the shift register after the DMA's last byte: 53 us */
#define DRAIN_TRIES 3U
#define DMA_TIMEOUT_MS 200U    /* a frame's 4 KB take 44 ms at 750 kHz */
#define OLED_IRQ_PRIORITY 2U   /* as the console's DMA and the board inputs: below the radio and the RTC */
#define DMA_CH LL_DMA_CHANNEL_1
#define CMD_DISPLAY_OFF 0xAEU
#define CMD_DISPLAY_ON 0xAFU
#define CMD_MAX 48U

/* Both buffers in RAM2 (RAM1 is nearly full; design, "Bandwidth and memory"). The host test, whose
   object format has no such section, passes -DOLED_DMA_RAM2= . */
#ifndef OLED_DMA_RAM2
#define OLED_DMA_RAM2 __attribute__((section(".RAM2_region")))
#endif
static uint8_t txbuf[OLED_FRAME_BYTES] OLED_DMA_RAM2;
static uint8_t cmdbuf[CMD_MAX] OLED_DMA_RAM2;

static const uint8_t setup[] = {
  CMD_DISPLAY_OFF,
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
  CMD_DISPLAY_ON,
};
_Static_assert(sizeof setup <= CMD_MAX, "the set-up sequence fits the command buffer");

/* The whole screen as the write window: column pairs 0-63, rows 0-63. */
static const uint8_t window[] = { 0x15, 0x00, OLED_COLPAIRS - 1, 0x75, 0x00, OLED_H - 1 };

typedef enum { ST_OFF, ST_RESET_LOW, ST_RESET_SETTLE, ST_SETUP, ST_IDLE, ST_WINDOW, ST_PIXELS, ST_POWER } oled_state;

/* Written by the caller's task only while state is ST_IDLE or ST_OFF (no interrupt of ours pending),
   and by our interrupts only while a step is under way; enable() and send() claim a state with
   interrupts off. */
static volatile oled_state state;
static volatile uint8_t enabled, faulted, power_pending;
static volatile uint8_t in_dma;   /* a DMA run is under way: the step timer is its timeout */
static uint8_t drain_tries;
static UTIL_TIMER_Object_t step_timer;

static void fault(void)
{
  LL_DMA_DisableChannel(DMA1, DMA_CH);
  LL_SPI_DisableDMAReq_TX(SPI1);
  LL_SPI_DisableIT_ERR(SPI1);   /* an error flag left set cannot raise the interrupt again */
  LL_SPI_Disable(SPI1);
  (void)UTIL_TIMER_Stop(&step_timer);
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_SET);
  state = ST_OFF;
  enabled = 0;
  power_pending = 0;
  in_dma = 0;
  if (faulted) return;
  faulted = 1;
  APP_PRINTF("#oled fault\n");
}

static void arm(uint32_t ms)
{
  (void)UTIL_TIMER_Stop(&step_timer);
  if (UTIL_TIMER_SetPeriod(&step_timer, ms) != UTIL_TIMER_OK || UTIL_TIMER_Start(&step_timer) != UTIL_TIMER_OK) fault();
}

static void start_dma(uint8_t *buf, uint32_t n)
{
  LL_DMA_DisableChannel(DMA1, DMA_CH);
  LL_DMA_ClearFlag_GI1(DMA1);
  LL_DMA_SetMemoryAddress(DMA1, DMA_CH, (uint32_t)(uintptr_t)buf);
  LL_DMA_SetDataLength(DMA1, DMA_CH, n);
  in_dma = 1;
  arm(DMA_TIMEOUT_MS);
  LL_DMA_EnableChannel(DMA1, DMA_CH);
  LL_SPI_EnableDMAReq_TX(SPI1);   /* SPI1's empty FIFO requests the first bytes at once */
}

static void select_start(int dc_data, uint8_t *buf, uint32_t n)
{
  HAL_GPIO_WritePin(GPIOC, DC_PIN, dc_data ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_RESET);
  start_dma(buf, n);
}

static void commands(oled_state next, const uint8_t *b, uint32_t n)
{
  state = next;
  memcpy(cmdbuf, b, n);
  select_start(0, cmdbuf, n);
}

static void start_power(void)
{
  static const uint8_t off[] = { CMD_DISPLAY_OFF }, on[] = { CMD_DISPLAY_ON };
  power_pending = 0;
  commands(ST_POWER, enabled ? on : off, 1U);
}

/* The last byte of a transfer has left: CS up, then the next step. */
static void transfer_done(void)
{
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_SET);
  if (state == ST_WINDOW) { state = ST_PIXELS; select_start(1, txbuf, OLED_FRAME_BYTES); return; }
  state = ST_IDLE;
  if (power_pending) start_power();
}

/* cppcheck-suppress constParameterCallback ; ST's UTIL_TIMER callback signature */
static void on_step(void *ctx)
{
  (void)ctx;
  switch (state)
  {
    case ST_RESET_LOW:
      HAL_GPIO_WritePin(GPIOC, RST_PIN, GPIO_PIN_SET);
      state = ST_RESET_SETTLE;
      arm(RESET_SETTLE_MS);
      break;
    case ST_RESET_SETTLE:
      commands(ST_SETUP, setup, sizeof setup);
      break;
    case ST_SETUP: case ST_WINDOW: case ST_PIXELS: case ST_POWER:   /* draining after the DMA */
      if (in_dma) { fault(); break; }   /* the DMA's timeout: its transfer-complete interrupt never came */
      if (LL_SPI_GetTxFIFOLevel(SPI1) == LL_SPI_TX_FIFO_EMPTY && !LL_SPI_IsActiveFlag_BSY(SPI1)) { transfer_done(); break; }
      if (++drain_tries >= DRAIN_TRIES) { fault(); break; }
      arm(DRAIN_MS);
      break;
    case ST_OFF: case ST_IDLE:
    default:
      break;   /* a timer left over from before a fault */
  }
}

/* The slowest prescaler not above SPI_MAX_HZ from PCLK2 (SPI1 is on APB2): DIV64, 750 kHz at 48 MHz. */
static uint32_t prescaler(void)
{
  static const uint32_t div[] = { LL_SPI_BAUDRATEPRESCALER_DIV2, LL_SPI_BAUDRATEPRESCALER_DIV4,
                                  LL_SPI_BAUDRATEPRESCALER_DIV8, LL_SPI_BAUDRATEPRESCALER_DIV16,
                                  LL_SPI_BAUDRATEPRESCALER_DIV32, LL_SPI_BAUDRATEPRESCALER_DIV64,
                                  LL_SPI_BAUDRATEPRESCALER_DIV128, LL_SPI_BAUDRATEPRESCALER_DIV256 };
  uint32_t pclk = HAL_RCC_GetPCLK2Freq();
  unsigned k;
  for (k = 0; k < 7U && (pclk >> (k + 1U)) > SPI_MAX_HZ; k++) {}
  return div[k];
}

/* Pins, SPI1 (mode 0, transmit only, master), DMA1 channel 1 on SPI1_TX, the two interrupts. */
static void hardware(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_SPI1_CLK_ENABLE();
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOC, RST_PIN | DC_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef out = { .Pin = CS_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &out);
  out.Pin = RST_PIN | DC_PIN;
  HAL_GPIO_Init(GPIOC, &out);
  GPIO_InitTypeDef spi = { .Pin = SCK_PIN | MOSI_PIN, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_NOPULL,
                           .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF5_SPI1 };
  HAL_GPIO_Init(GPIOA, &spi);

  LL_SPI_Disable(SPI1);
  LL_SPI_SetMode(SPI1, LL_SPI_MODE_MASTER);
  LL_SPI_SetTransferDirection(SPI1, LL_SPI_HALF_DUPLEX_TX);   /* nothing received, no receive overrun */
  LL_SPI_SetClockPolarity(SPI1, LL_SPI_POLARITY_LOW);         /* SPI mode 0, as Adafruit's driver */
  LL_SPI_SetClockPhase(SPI1, LL_SPI_PHASE_1EDGE);
  LL_SPI_SetTransferBitOrder(SPI1, LL_SPI_MSB_FIRST);
  LL_SPI_SetNSSMode(SPI1, LL_SPI_NSS_SOFT);
  LL_SPI_SetDataWidth(SPI1, LL_SPI_DATAWIDTH_8BIT);
  LL_SPI_SetBaudRatePrescaler(SPI1, prescaler());
  LL_SPI_ClearFlag_MODF(SPI1);
  LL_SPI_EnableIT_ERR(SPI1);
  LL_SPI_Enable(SPI1);

  LL_DMA_DisableChannel(DMA1, DMA_CH);
  LL_DMA_ConfigTransfer(DMA1, DMA_CH, LL_DMA_DIRECTION_MEMORY_TO_PERIPH | LL_DMA_MODE_NORMAL | LL_DMA_PERIPH_NOINCREMENT |
                        LL_DMA_MEMORY_INCREMENT | LL_DMA_PDATAALIGN_BYTE | LL_DMA_MDATAALIGN_BYTE | LL_DMA_PRIORITY_LOW);
  LL_DMA_SetPeriphRequest(DMA1, DMA_CH, LL_DMAMUX_REQ_SPI1_TX);
  LL_DMA_SetPeriphAddress(DMA1, DMA_CH, LL_SPI_DMA_GetRegAddr(SPI1));
  LL_DMA_ClearFlag_GI1(DMA1);
  LL_DMA_EnableIT_TC(DMA1, DMA_CH);
  LL_DMA_EnableIT_TE(DMA1, DMA_CH);
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, OLED_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_SetPriority(SPI1_IRQn, OLED_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(SPI1_IRQn);
}

/* From OFF: the hardware, then RST low for RESET_LOW_MS (on_step does the rest). */
static void start_up(void)
{
  faulted = 0;
  enabled = 1;
  power_pending = 0;
  hardware();
  HAL_GPIO_WritePin(GPIOC, RST_PIN, GPIO_PIN_RESET);
  state = ST_RESET_LOW;
  arm(RESET_LOW_MS);
}

void oled_dma_init(void)
{
  (void)UTIL_TIMER_Create(&step_timer, RESET_LOW_MS, UTIL_TIMER_ONESHOT, on_step, NULL);   /* arm() sets each period */
  start_up();
}

int oled_dma_send(const uint8_t frame[OLED_FRAME_BYTES])
{
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  int rc = faulted || !enabled ? -2 : state != ST_IDLE ? -1 : 0;
  if (rc == 0) state = ST_WINDOW;   /* claimed: nothing else starts a transfer now */
  __set_PRIMASK(primask);
  if (rc) return rc;
  if (frame != txbuf) memcpy(txbuf, frame, OLED_FRAME_BYTES);
  commands(ST_WINDOW, window, sizeof window);
  return 0;
}

uint8_t *oled_dma_buffer(void) { return txbuf; }

int oled_dma_busy(void) { oled_state s = state; return s != ST_IDLE && s != ST_OFF; }

void oled_dma_enable(int on)
{
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  int restart = on && state == ST_OFF;   /* after a fault */
  if (restart) state = ST_RESET_LOW;     /* claimed, as in oled_dma_send: start_up() runs with interrupts on */
  int change = !restart && (on ? !enabled : enabled);
  if (change) enabled = (uint8_t)(on != 0);
  int now = change && state == ST_IDLE;
  if (now) state = ST_POWER;             /* claimed, as in oled_dma_send */
  else if (change) power_pending = 1;    /* sent when the step under way ends */
  __set_PRIMASK(primask);
  if (restart) start_up();
  if (now) start_power();
}

int oled_dma_faulted(void) { return faulted; }

/* DMA1 channel 1: the end of a transfer, or a transfer error (a fault). */
static void dma_irq(void)
{
  int te = (int)LL_DMA_IsActiveFlag_TE1(DMA1), tc = (int)LL_DMA_IsActiveFlag_TC1(DMA1);
  LL_DMA_ClearFlag_GI1(DMA1);
  if (te) { fault(); return; }
  if (!tc || state == ST_OFF) return;
  LL_DMA_DisableChannel(DMA1, DMA_CH);
  LL_SPI_DisableDMAReq_TX(SPI1);
  in_dma = 0;
  drain_tries = 0;
  arm(DRAIN_MS);
}

/* SPI1: only its error interrupt is enabled (mode fault, overrun, CRC or frame error), so any entry
   is a fault; fault() masks it again. */
static void spi_irq(void) { fault(); }

void DMA1_Channel1_IRQHandler(void);   /* vector table names (startup_stm32wl55jcix.s, weak there) */
void SPI1_IRQHandler(void);
void DMA1_Channel1_IRQHandler(void) { BUSYMON_ISR("DMA1_CH1", dma_irq()); }
void SPI1_IRQHandler(void) { BUSYMON_ISR("SPI1", spi_irq()); }
