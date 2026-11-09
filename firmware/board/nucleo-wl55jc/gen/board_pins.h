#ifndef BOARD_PINS_H
#define BOARD_PINS_H
/* GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
 * The station's pins on the NUCLEO-WL55JC1 (MB1389), by function: the names the node's App/ code uses instead of
 * naming pins itself (tools/board_lint.py). Macros only: the file that uses them includes
 * stm32wlxx_hal.h. Every *_PIN line is "#define NAME GPIO_PIN_n", then a comment that starts with
 * the pin and says where it is: hardware/bench-breadboard-r0/source/wiring.py checks them against its
 * nets. */
#include "board_caps.h"

/* I2C2, the station bus (App/i2c_bus.lit.md): SDA PA11, SCL PA12, AF4. */
#define BOARD_I2C_SDA_PORT GPIOA
#define BOARD_I2C_SDA_PIN GPIO_PIN_11 /* PA11 = D14, CN5.9 */
#define BOARD_I2C_SCL_PORT GPIOA
#define BOARD_I2C_SCL_PIN GPIO_PIN_12 /* PA12 = D15, CN5.10 */
/* One port: each step takes both pins at once. */
#define BOARD_I2C_GPIO_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define BOARD_I2C_PINS_INIT(init) HAL_GPIO_Init(GPIOA, (init)) /* (init)->Pin holds SDA | SCL */
#define BOARD_I2C_PINS_DEINIT() HAL_GPIO_DeInit(GPIOA, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN)
#define BOARD_I2C_PINS_HIGH() HAL_GPIO_WritePin(GPIOA, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN, GPIO_PIN_SET)
#define BOARD_I2C I2C2
#define BOARD_I2C_AF GPIO_AF4_I2C2
#define BOARD_I2C_PERIPHCLK RCC_PERIPHCLK_I2C2
#define BOARD_I2C_CLKSEL I2c2ClockSelection
#define BOARD_I2C_CLKSRC_PCLK1 RCC_I2C2CLKSOURCE_PCLK1
#define BOARD_I2C_CLK_ENABLE() __HAL_RCC_I2C2_CLK_ENABLE()
#define BOARD_I2C_CLK_DISABLE() __HAL_RCC_I2C2_CLK_DISABLE()
#define BOARD_I2C_EV_IRQn I2C2_EV_IRQn
#define BOARD_I2C_EV_IRQHandler I2C2_EV_IRQHandler
#define BOARD_I2C_ER_IRQn I2C2_ER_IRQn
#define BOARD_I2C_ER_IRQHandler I2C2_ER_IRQHandler

/* The anemometer cups: LPTIM1_IN1 (AF1) on PB5. BIT is the pin's number (its PUPDR field). */
#define BOARD_CUPS_PORT GPIOB
#define BOARD_CUPS_PIN GPIO_PIN_5 /* PB5 = D4, CN9.5: LPTIM1_IN1 AF1 */
#define BOARD_CUPS_BIT 5U
#define BOARD_CUPS_CLK_ENABLE() __HAL_RCC_GPIOB_CLK_ENABLE()
#define BOARD_CUPS_AF GPIO_AF1_LPTIM1
#define BOARD_CUPS_LPTIM LPTIM1
#define BOARD_CUPS_LPTIM_PERIPHCLK RCC_PERIPHCLK_LPTIM1
#define BOARD_CUPS_LPTIM_CLKSEL Lptim1ClockSelection
#define BOARD_CUPS_LPTIM_CLKSRC_LSE RCC_LPTIM1CLKSOURCE_LSE
#define BOARD_CUPS_LPTIM_CLK_ENABLE() __HAL_RCC_LPTIM1_CLK_ENABLE()

/* The ADC inputs: the wind vane divider, the charger's ISET node (on the vane's port) and the charger
   input divider. */
#define BOARD_VANE_PORT GPIOB
#define BOARD_VANE_PIN GPIO_PIN_2 /* PB2 = A1, CN8.2: ADC1_IN4 */
#define BOARD_VANE_CHANNEL ADC_CHANNEL_4
#define BOARD_ISET_PIN GPIO_PIN_1 /* PB1 = A0, CN8.1: ADC1_IN5 */
#define BOARD_ISET_CHANNEL ADC_CHANNEL_5
#define BOARD_VIN_PORT GPIOA
#define BOARD_VIN_PIN GPIO_PIN_10 /* PA10 = A2, CN8.3: ADC1_IN6 */
#define BOARD_VIN_CHANNEL ADC_CHANNEL_6
#define BOARD_ADC_GPIO_CLK_ENABLE() do { __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); } while (0)

/* The rain gauge: PB4, EXTI line 4 on its own vector. */
#define BOARD_RAIN_PORT GPIOB
#define BOARD_RAIN_PIN GPIO_PIN_4 /* PB4 = A3, CN8.4: EXTI4 */
#define BOARD_RAIN_BIT 4U
#define BOARD_RAIN_EXTI_LINE LL_EXTI_LINE_4
#define BOARD_RAIN_IRQn EXTI4_IRQn
#define BOARD_RAIN_IRQHandler EXTI4_IRQHandler

/* The bq24074 charger pins (PGOOD, CHG and ISET above). 1: fitted (App/board_inputs.c, App/power_acq.c);
   0: the charger status and its battery current are none, and the pins are never configured. */
#define BOARD_CHARGER_PINS 1
#define BOARD_PGOOD_PORT GPIOB
#define BOARD_PGOOD_PIN GPIO_PIN_8 /* PB8 = D5, CN9.6 */
#define BOARD_CHG_PORT GPIOB
#define BOARD_CHG_PIN GPIO_PIN_10 /* PB10 = D6, CN9.7: EXTI10 */

/* The mux RESET (active low, WS_I2C_MUX=1) and the sensor power switch. */
#define BOARD_MUX_RESET_PORT GPIOB
#define BOARD_MUX_RESET_PIN GPIO_PIN_14 /* PB14 = A4, CN8.5 */
#define BOARD_SENSOR_POWER_PORT GPIOA
#define BOARD_SENSOR_POWER_PIN GPIO_PIN_9 /* PA9 = D9, CN5.2 */
#define BOARD_SENSOR_POWER_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
/* The clocks of the digital inputs' ports (rain, PGOOD, CHG) and the mux RESET's. */
#define BOARD_INPUTS_CLK_ENABLE() __HAL_RCC_GPIOB_CLK_ENABLE()

/* The shared EXTI vectors, which App/board_inputs.c serves whole: a pending line it skipped would re-enter
   that interrupt forever. */
#define BOARD_EXTI_5TO9_IRQn EXTI9_5_IRQn
#define BOARD_EXTI_5TO9_IRQHandler EXTI9_5_IRQHandler
#define BOARD_EXTI_5TO9_LINES { GPIO_PIN_5, GPIO_PIN_6, GPIO_PIN_7, GPIO_PIN_8, GPIO_PIN_9 }
#define BOARD_EXTI_10TO15_IRQn EXTI15_10_IRQn
#define BOARD_EXTI_10TO15_IRQHandler EXTI15_10_IRQHandler
#define BOARD_EXTI_10TO15_LINES { GPIO_PIN_10, GPIO_PIN_11, GPIO_PIN_12, GPIO_PIN_13, GPIO_PIN_14, GPIO_PIN_15 }

/* The user LEDs, blue, green and red (App/leds.h): blue PB15, green PB9, red PB11; on when high.
   The order is App/leds.h's. */
#define BOARD_LED_PORTS { GPIOB, GPIOB, GPIOB }
#define BOARD_LED_PINS { GPIO_PIN_15, GPIO_PIN_9, GPIO_PIN_11 }
#define BOARD_LED_ON GPIO_PIN_SET
#define BOARD_LED_OFF GPIO_PIN_RESET

/* The console: USART2 (PA2 TX, PA3 RX) to the ST-LINK's virtual COM port (Core/Src/usart.c), its
   TX on DMA. The names the node's interrupt file (stage0-node/Core/Src/stm32wlxx_it.c) uses. */
#define BOARD_CONSOLE_UART huart2
#define BOARD_CONSOLE_DMA_TX hdma_usart2_tx
#define BOARD_CONSOLE_IRQHandler USART2_IRQHandler
#define BOARD_CONSOLE_NAME "USART2"

/* The bench OLED (WS_BENCH_OLED=1; oled_spi1.c): CS, RST and DC are GPIOs, SCK and MOSI SPI1 AF5. */
#define BOARD_OLED_CS_PORT GPIOA
#define BOARD_OLED_CS_PIN GPIO_PIN_4 /* PA4 = CN10.17 */
#define BOARD_OLED_SCK_PORT GPIOA
#define BOARD_OLED_SCK_PIN GPIO_PIN_5 /* PA5 = CN10.11: SPI1_SCK AF5 */
#define BOARD_OLED_MOSI_PORT GPIOA
#define BOARD_OLED_MOSI_PIN GPIO_PIN_7 /* PA7 = CN10.15: SPI1_MOSI AF5 */
#define BOARD_OLED_RST_PORT GPIOC
#define BOARD_OLED_RST_PIN GPIO_PIN_1 /* PC1 = CN10.23 */
#define BOARD_OLED_DC_PORT GPIOC
#define BOARD_OLED_DC_PIN GPIO_PIN_2 /* PC2 = CN10.21 */
#define BOARD_OLED_SPI SPI1
#define BOARD_OLED_SPI_AF GPIO_AF5_SPI1
#define BOARD_OLED_GPIO_CLK_ENABLE() do { __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOC_CLK_ENABLE(); } while (0)
/* Its buttons: B1 and B2 on vectors of their own, B3 on a shared one. */
#define BOARD_B1_PORT GPIOA
#define BOARD_B1_PIN GPIO_PIN_0 /* PA0 = B1: EXTI0 */
#define BOARD_B1_IRQn EXTI0_IRQn
#define BOARD_B1_IRQHandler EXTI0_IRQHandler
#define BOARD_B2_PORT GPIOA
#define BOARD_B2_PIN GPIO_PIN_1 /* PA1 = B2: EXTI1 */
#define BOARD_B2_IRQn EXTI1_IRQn
#define BOARD_B2_IRQHandler EXTI1_IRQHandler
#define BOARD_B3_PORT GPIOC
#define BOARD_B3_PIN GPIO_PIN_6 /* PC6 = B3: EXTI6 */
#define BOARD_BUTTONS_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()

#endif
