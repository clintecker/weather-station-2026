#ifndef BOARD_PINS_H
#define BOARD_PINS_H
/* GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
 * The station's pins on the Seeed Wio-E5 mini (LoRa-E5, STM32WLE5JC), by function: the names the node's App/ code uses instead of
 * naming pins itself (tools/board_lint.py). Macros only: the file that uses them includes
 * stm32wlxx_hal.h. Every *_PIN line is "#define NAME GPIO_PIN_n", then a comment that starts with
 * the pin and says where it is: hardware/bench-breadboard-r0/source/wiring.py checks them against its
 * nets. */
#include "board_caps.h"

/* I2C2, the station bus (App/i2c_bus.lit.md): SDA PA15, SCL PB15, AF4. */
#define BOARD_I2C_SDA_PORT GPIOA
#define BOARD_I2C_SDA_PIN GPIO_PIN_15 /* PA15 */
#define BOARD_I2C_SCL_PORT GPIOB
#define BOARD_I2C_SCL_PIN GPIO_PIN_15 /* PB15 */
/* Two ports: each step takes one pin at a time. */
#define BOARD_I2C_GPIO_CLK_ENABLE() do { __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); } while (0)
#define BOARD_I2C_PINS_INIT(init) do { GPIO_InitTypeDef *bp_ = (init); \
    bp_->Pin = BOARD_I2C_SDA_PIN; HAL_GPIO_Init(BOARD_I2C_SDA_PORT, bp_); \
    bp_->Pin = BOARD_I2C_SCL_PIN; HAL_GPIO_Init(BOARD_I2C_SCL_PORT, bp_); } while (0)
#define BOARD_I2C_PINS_DEINIT() do { HAL_GPIO_DeInit(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN); \
    HAL_GPIO_DeInit(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN); } while (0)
#define BOARD_I2C_PINS_HIGH() do { HAL_GPIO_WritePin(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN, GPIO_PIN_SET); \
    HAL_GPIO_WritePin(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN, GPIO_PIN_SET); } while (0)
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

/* The anemometer cups: LPTIM1_IN1 (AF1) on PC0. BIT is the pin's number (its PUPDR field). */
#define BOARD_CUPS_PORT GPIOC
#define BOARD_CUPS_PIN GPIO_PIN_0 /* PC0: LPTIM1_IN1 AF1 */
#define BOARD_CUPS_BIT 0U
#define BOARD_CUPS_CLK_ENABLE() __HAL_RCC_GPIOC_CLK_ENABLE()
#define BOARD_CUPS_AF GPIO_AF1_LPTIM1
#define BOARD_CUPS_LPTIM LPTIM1
#define BOARD_CUPS_LPTIM_PERIPHCLK RCC_PERIPHCLK_LPTIM1
#define BOARD_CUPS_LPTIM_CLKSEL Lptim1ClockSelection
#define BOARD_CUPS_LPTIM_CLKSRC_LSE RCC_LPTIM1CLKSOURCE_LSE
#define BOARD_CUPS_LPTIM_CLK_ENABLE() __HAL_RCC_LPTIM1_CLK_ENABLE()

/* The ADC inputs: the wind vane divider, the charger's ISET node (on the vane's port) and the charger
   input divider. */
#define BOARD_VANE_PORT GPIOB
#define BOARD_VANE_PIN GPIO_PIN_3 /* PB3: ADC1_IN2 */
#define BOARD_VANE_CHANNEL ADC_CHANNEL_2
/* ISET is not fitted (PB1 is not on the mini's headers): its rank of the ADC sequence converts VREFINT, a reading
   nobody uses; the sequence keeps its four ranks. */
#define BOARD_ISET_PIN 0U
#define BOARD_ISET_CHANNEL ADC_CHANNEL_VREFINT
#define BOARD_VIN_PORT GPIOA
#define BOARD_VIN_PIN GPIO_PIN_10 /* PA10: ADC1_IN6 */
#define BOARD_VIN_CHANNEL ADC_CHANNEL_6
#define BOARD_ADC_GPIO_CLK_ENABLE() do { __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); } while (0)

/* The rain gauge: PB4, EXTI line 4 on its own vector. */
#define BOARD_RAIN_PORT GPIOB
#define BOARD_RAIN_PIN GPIO_PIN_4 /* PB4: EXTI4 */
#define BOARD_RAIN_BIT 4U
#define BOARD_RAIN_EXTI_LINE LL_EXTI_LINE_4
#define BOARD_RAIN_IRQn EXTI4_IRQn
#define BOARD_RAIN_IRQHandler EXTI4_IRQHandler

/* The bq24074 charger pins (PGOOD, CHG and ISET above). 1: fitted (App/board_inputs.c, App/power_acq.c);
   0: the charger status and its battery current are none, and the pins are never configured. */
#define BOARD_CHARGER_PINS 0
#define BOARD_PGOOD_PORT GPIOB
#define BOARD_PGOOD_PIN GPIO_PIN_8 /* PB8: not fitted (PB8 is not on the mini's headers) */
#define BOARD_CHG_PORT GPIOB
#define BOARD_CHG_PIN GPIO_PIN_10 /* PB10: EXTI10, not fitted (CHG means little without PGOOD) */

/* The mux RESET (active low, WS_I2C_MUX=1) and the sensor power switch. */
#define BOARD_MUX_RESET_PORT GPIOB
#define BOARD_MUX_RESET_PIN GPIO_PIN_14 /* PB14 */
#define BOARD_SENSOR_POWER_PORT GPIOA
#define BOARD_SENSOR_POWER_PIN GPIO_PIN_9 /* PA9 */
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

/* The user LEDs, blue, green and red (App/leds.h): blue PB5; on when low.
   A missing LED is pin 0 on the first LED's port: its writes are no-ops (HAL_GPIO_WritePin writes a
   zero mask to BSRR or BRR). Only blue's pin is ever read (App/leds.c, the heartbeat). */
#define BOARD_LED_PORTS { GPIOB, GPIOB, GPIOB }
#define BOARD_LED_PINS { GPIO_PIN_5, 0U, 0U }
#define BOARD_LED_ON GPIO_PIN_RESET
#define BOARD_LED_OFF GPIO_PIN_SET

/* The console: USART1 (PB6 TX, PB7 RX) to the mini's own USB-UART bridge, on its USB-C (Core/Src/usart.c), its
   TX on DMA. The names the node's interrupt file (stage0-node/Core/Src/stm32wlxx_it.c) uses. */
#define BOARD_CONSOLE_UART huart1
#define BOARD_CONSOLE_DMA_TX hdma_usart1_tx
#define BOARD_CONSOLE_IRQHandler USART1_IRQHandler
#define BOARD_CONSOLE_NAME "USART1"

#endif
