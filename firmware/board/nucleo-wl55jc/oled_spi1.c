/* The bench OLED's pins and SPI1: see oled_spi1.h. */
#include "oled_spi1.h"
#include "ssd1325.h"
#include "stm32wlxx_ll_spi.h"

unsigned oled_spi1_init(void)
{
  static const uint32_t div[8] = { LL_SPI_BAUDRATEPRESCALER_DIV2, LL_SPI_BAUDRATEPRESCALER_DIV4,
                                   LL_SPI_BAUDRATEPRESCALER_DIV8, LL_SPI_BAUDRATEPRESCALER_DIV16,
                                   LL_SPI_BAUDRATEPRESCALER_DIV32, LL_SPI_BAUDRATEPRESCALER_DIV64,
                                   LL_SPI_BAUDRATEPRESCALER_DIV128, LL_SPI_BAUDRATEPRESCALER_DIV256 };
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_SPI1_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA, OLED_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOC, OLED_RST_PIN | OLED_DC_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef out = { .Pin = OLED_CS_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &out);
  out.Pin = OLED_RST_PIN | OLED_DC_PIN;
  HAL_GPIO_Init(GPIOC, &out);
  GPIO_InitTypeDef spi = { .Pin = OLED_SCK_PIN | OLED_MOSI_PIN, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_NOPULL,
                           .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF5_SPI1 };
  HAL_GPIO_Init(GPIOA, &spi);

  uint32_t pclk = HAL_RCC_GetPCLK2Freq();
  unsigned k = ssd1325_spi_div_log2(pclk);
  LL_SPI_Disable(SPI1);
  LL_SPI_SetMode(SPI1, LL_SPI_MODE_MASTER);
  LL_SPI_SetTransferDirection(SPI1, LL_SPI_HALF_DUPLEX_TX);
  LL_SPI_SetClockPolarity(SPI1, LL_SPI_POLARITY_LOW);
  LL_SPI_SetClockPhase(SPI1, LL_SPI_PHASE_1EDGE);
  LL_SPI_SetTransferBitOrder(SPI1, LL_SPI_MSB_FIRST);
  LL_SPI_SetNSSMode(SPI1, LL_SPI_NSS_SOFT);
  LL_SPI_SetDataWidth(SPI1, LL_SPI_DATAWIDTH_8BIT);
  LL_SPI_SetBaudRatePrescaler(SPI1, div[k - 1U]);
  return (unsigned)(pclk >> k);
}
