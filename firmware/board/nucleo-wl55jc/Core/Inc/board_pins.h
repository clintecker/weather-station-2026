#ifndef BOARD_PINS_H
#define BOARD_PINS_H
/* The station's pins on this board (NUCLEO-WL55JC1, MB1389): what the node's App code takes from the board
 * layer instead of naming pins itself (issue #35). The other board, ../../wio-e5/Core/Inc/board_pins.h,
 * defines the same names. Macros only: the file that uses them includes stm32wlxx_hal.h.
 * NUCLEO positions: UM2592 table 17 (ARDUINO) and table 18 (ST morpho); the wiring is
 * docs/hardware/bench-station-wiring.md, the reasons App/board_inputs.c and App/i2c_bus.lit.md. The breadboard
 * model checks the pin constants here against its nets (hardware/bench-breadboard-r0/source/wiring.py,
 * FIRMWARE): keep each as one line, "#define NAME_PIN GPIO_PIN_n", then a comment that starts with its pin. */

/* I2C2, the station bus (App/i2c_bus.lit.md): PA11 SDA (CN5.9 D14), PA12 SCL (CN5.10 D15), AF4. The
   pins share a port, so each step takes both at once. */
#define BOARD_I2C_SDA_PORT GPIOA
#define BOARD_I2C_SDA_PIN GPIO_PIN_11 /* PA11 = D14, CN5.9 */
#define BOARD_I2C_SCL_PORT GPIOA
#define BOARD_I2C_SCL_PIN GPIO_PIN_12 /* PA12 = D15, CN5.10 */
#define BOARD_I2C_GPIO_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define BOARD_I2C_PINS_INIT(init) HAL_GPIO_Init(GPIOA, (init))   /* (init)->Pin holds SDA | SCL */
#define BOARD_I2C_PINS_DEINIT() HAL_GPIO_DeInit(GPIOA, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN)
#define BOARD_I2C_PINS_HIGH() HAL_GPIO_WritePin(GPIOA, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN, GPIO_PIN_SET)

/* The anemometer cups: LPTIM1_IN1 (AF1) on PB5 (CN9.5 D4). BIT is the pin's number (its PUPDR field). */
#define BOARD_CUPS_PORT GPIOB
#define BOARD_CUPS_PIN GPIO_PIN_5 /* PB5 = D4, CN9.5: LPTIM1_IN1 AF1 */
#define BOARD_CUPS_BIT  5U
#define BOARD_CUPS_CLK_ENABLE() __HAL_RCC_GPIOB_CLK_ENABLE()

/* The wind vane divider: PB2 (CN8.2 A1), ADC1_IN4. */
#define BOARD_VANE_PORT    GPIOB
#define BOARD_VANE_PIN GPIO_PIN_2 /* PB2 = A1, CN8.2: ADC1_IN4 */
#define BOARD_VANE_CHANNEL ADC_CHANNEL_4

/* The bq24074 charger pins: PGOOD PB8, CHG PB10 and ISET PB1 (ADC1_IN5); the charger input divider on
   PA10 (ADC1_IN6) is on every board. 1: fitted (App/board_inputs.c, App/power_acq.c). */
#define BOARD_CHARGER_PINS 1
#define BOARD_ISET_PIN GPIO_PIN_1 /* PB1 = A0, CN8.1: ADC1_IN5; on GPIOB, with the vane */
#define BOARD_ISET_CHANNEL ADC_CHANNEL_5

/* The user LEDs, LED1 blue (PB15), LED2 green (PB9), LED3 red (PB11) (Core/Inc/main.h): on when high. */
#define BOARD_LED_PORTS { LED1_GPIO_Port, LED2_GPIO_Port, LED3_GPIO_Port }
#define BOARD_LED_PINS  { LED1_Pin, LED2_Pin, LED3_Pin }
#define BOARD_LED_ON    GPIO_PIN_SET
#define BOARD_LED_OFF   GPIO_PIN_RESET

/* The console: USART2 (PA2 TX, PA3 RX) to the ST-LINK's virtual COM port (Core/Src/usart.c), its TX on
   DMA1 channel 5. The names the node's interrupt file (stage0-node/Core/Src/stm32wlxx_it.c) uses. */
#define BOARD_CONSOLE_UART       huart2
#define BOARD_CONSOLE_DMA_TX     hdma_usart2_tx
#define BOARD_CONSOLE_IRQHandler USART2_IRQHandler
#define BOARD_CONSOLE_NAME       "USART2"
#endif
