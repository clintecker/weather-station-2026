/* The bench OLED on SPI1 (oled.h), polled. The pins and SPI1 (transmit only: nothing is received and no
 * receive FIFO can overflow) are board/nucleo-wl55jc/oled_spi1.c's, the set-up sequence common/ssd1325.c's
 * (Adafruit's for this module), as the node's DMA driver has them. */
#include "oled.h"
#include "oled_spi1.h"
#include "ssd1325.h"
#include "stm32wlxx_hal.h"
#include "stm32wlxx_ll_spi.h"

#define WAIT_MS 5U            /* one byte takes ~11 us at 750 kHz */
#define RESET_LOW_MS 10U
#define RESET_SETTLE_MS 500U  /* Adafruit's wait after reset, before the first command */

static unsigned spi_hz;

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
  HAL_GPIO_WritePin(GPIOC, OLED_DC_PIN, dc_data ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, OLED_CS_PIN, GPIO_PIN_RESET);
}

static void deselect(void) { HAL_GPIO_WritePin(GPIOA, OLED_CS_PIN, GPIO_PIN_SET); }

static int commands(const uint8_t *b, unsigned n)
{
  select(0);
  int rc = send(b, n);
  deselect();
  return rc;
}

void oled_init(void)
{
  spi_hz = oled_spi1_init();
  LL_SPI_SetRxFIFOThreshold(SPI1, LL_SPI_RX_FIFO_TH_QUARTER);
  LL_SPI_Enable(SPI1);

  HAL_GPIO_WritePin(GPIOC, OLED_RST_PIN, GPIO_PIN_RESET);   /* boot only: these waits are not in the loop */
  HAL_Delay(RESET_LOW_MS);
  HAL_GPIO_WritePin(GPIOC, OLED_RST_PIN, GPIO_PIN_SET);
  HAL_Delay(RESET_SETTLE_MS);
  (void)commands(ssd1325_setup, SSD1325_SETUP_LEN);
}

int oled_show(const uint8_t frame[OLED_FRAME_BYTES])
{
  if (commands(ssd1325_window, sizeof ssd1325_window)) return -1;
  select(1);
  int rc = 0;
  for (unsigned cp = 0; cp < OLED_COLPAIRS && rc == 0; cp++) rc = send(&frame[cp * OLED_H], OLED_H);
  deselect();
  return rc;
}

unsigned oled_spi_hz(void) { return spi_hz; }
