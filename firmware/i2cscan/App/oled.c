/* The bench OLED on SPI1 (oled.h). ST's LL SPI functions drive SPI1 transmit-only (half duplex, the
 * data line an output), so nothing is received and no receive FIFO can overflow. The set-up sequence
 * is Adafruit's for this module (Adafruit_SSD1325_Library, begin()); the command values are in the
 * SSD1325 datasheet (Solomon Systech, section 9). */
#include "oled.h"
#include "stm32wlxx_hal.h"
#include "stm32wlxx_ll_spi.h"

#define CS_PIN GPIO_PIN_4     /* PA4 */
#define SCK_PIN GPIO_PIN_5    /* PA5 */
#define MOSI_PIN GPIO_PIN_7   /* PA7 */
#define RST_PIN GPIO_PIN_1    /* PC1 */
#define DC_PIN GPIO_PIN_2     /* PC2 */
#define SPI_MAX_HZ 1000000U   /* Adafruit: "The SSD1325 needs to be slowed down to 1MHz" */
#define WAIT_MS 5U            /* one byte takes ~11 us at 750 kHz */
#define RESET_LOW_MS 10U
#define RESET_SETTLE_MS 500U  /* Adafruit's wait after reset, before the first command */

static unsigned spi_hz;

static const uint8_t setup[] = {
  0xAE,                    /* display off */
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
  0xAF,                    /* display on */
};

/* The whole screen as the write window: column pairs 0-63, rows 0-63. */
static const uint8_t window[] = { 0x15, 0x00, 0x3F, 0x75, 0x00, 0x3F };

static int wait_flag(uint32_t (*flag)(const SPI_TypeDef *), uint32_t want)
{
  uint32_t start = HAL_GetTick();
  while (flag(SPI1) != want)
    if (HAL_GetTick() - start > WAIT_MS) return -1;
  return 0;
}

static int send(const uint8_t *b, unsigned n)
{
  for (unsigned i = 0; i < n; i++)
  {
    if (wait_flag(LL_SPI_IsActiveFlag_TXE, 1U)) return -1;
    LL_SPI_TransmitData8(SPI1, b[i]);
  }
  if (wait_flag(LL_SPI_IsActiveFlag_TXE, 1U)) return -1;
  return wait_flag(LL_SPI_IsActiveFlag_BSY, 0U);   /* the last byte has left before CS rises */
}

static void select(int dc_data)
{
  HAL_GPIO_WritePin(GPIOC, DC_PIN, dc_data ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_RESET);
}

static void deselect(void) { HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_SET); }

static int commands(const uint8_t *b, unsigned n)
{
  select(0);
  int rc = send(b, n);
  deselect();
  return rc;
}

/* The slowest prescaler not above SPI_MAX_HZ from PCLK2 (SPI1 is on APB2). */
static uint32_t prescaler(void)
{
  static const uint32_t div[] = { LL_SPI_BAUDRATEPRESCALER_DIV2, LL_SPI_BAUDRATEPRESCALER_DIV4,
                                  LL_SPI_BAUDRATEPRESCALER_DIV8, LL_SPI_BAUDRATEPRESCALER_DIV16,
                                  LL_SPI_BAUDRATEPRESCALER_DIV32, LL_SPI_BAUDRATEPRESCALER_DIV64,
                                  LL_SPI_BAUDRATEPRESCALER_DIV128, LL_SPI_BAUDRATEPRESCALER_DIV256 };
  uint32_t pclk = HAL_RCC_GetPCLK2Freq();
  unsigned k = 0;
  while (k + 1 < sizeof div / sizeof div[0] && (pclk >> (k + 1)) > SPI_MAX_HZ) k++;
  spi_hz = (unsigned)(pclk >> (k + 1));
  return div[k];
}

void oled_init(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_SPI1_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA, CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOC, RST_PIN | DC_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef out = { .Pin = CS_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL,
                           .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &out);
  out.Pin = RST_PIN | DC_PIN;
  HAL_GPIO_Init(GPIOC, &out);
  GPIO_InitTypeDef spi = { .Pin = SCK_PIN | MOSI_PIN, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_NOPULL,
                           .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF5_SPI1 };
  HAL_GPIO_Init(GPIOA, &spi);

  LL_SPI_SetMode(SPI1, LL_SPI_MODE_MASTER);
  LL_SPI_SetTransferDirection(SPI1, LL_SPI_HALF_DUPLEX_TX);
  LL_SPI_SetClockPolarity(SPI1, LL_SPI_POLARITY_LOW);   /* SPI mode 0, as Adafruit's driver */
  LL_SPI_SetClockPhase(SPI1, LL_SPI_PHASE_1EDGE);
  LL_SPI_SetTransferBitOrder(SPI1, LL_SPI_MSB_FIRST);
  LL_SPI_SetNSSMode(SPI1, LL_SPI_NSS_SOFT);
  LL_SPI_SetDataWidth(SPI1, LL_SPI_DATAWIDTH_8BIT);
  LL_SPI_SetRxFIFOThreshold(SPI1, LL_SPI_RX_FIFO_TH_QUARTER);
  LL_SPI_SetBaudRatePrescaler(SPI1, prescaler());
  LL_SPI_Enable(SPI1);

  HAL_GPIO_WritePin(GPIOC, RST_PIN, GPIO_PIN_RESET);   /* boot only: these waits are not in the loop */
  HAL_Delay(RESET_LOW_MS);
  HAL_GPIO_WritePin(GPIOC, RST_PIN, GPIO_PIN_SET);
  HAL_Delay(RESET_SETTLE_MS);
  (void)commands(setup, sizeof setup);
}

int oled_show(const uint8_t frame[OLED_FRAME_BYTES])
{
  if (commands(window, sizeof window)) return -1;
  select(1);
  int rc = 0;
  for (unsigned cp = 0; cp < OLED_COLPAIRS && rc == 0; cp++) rc = send(&frame[cp * OLED_H], OLED_H);
  deselect();
  return rc;
}

unsigned oled_spi_hz(void) { return spi_hz; }
