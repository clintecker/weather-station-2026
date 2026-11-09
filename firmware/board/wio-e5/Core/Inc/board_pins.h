#ifndef BOARD_PINS_H
#define BOARD_PINS_H
/* The station's pins on the Seeed Wio-E5 mini (LoRa-E5 module, STM32WLE5JC; issue #35): the same names as
 * ../../nucleo-wl55jc/Core/Inc/board_pins.h. Macros only: the file that uses them includes stm32wlxx_hal.h.
 * The mini's headers carry 5V, 3V3, GND, RST, PA13 SWDIO, PA14 SWCLK and PA0, PA2, PA3, PA9, PA10, PA15,
 * PB3, PB4, PB6, PB7, PB9, PB10, PB13 (the BOOT button), PB14, PB15, PC0, PC1 (Zephyr
 * boards/seeed/lora_e5_mini pinout). Alternate functions and ADC channels: Zephyr hal_stm32
 * dts/st/wl/stm32wle5jcix-pinctrl.dtsi, commit 9dd7ccae (i2c2_sda_pa15 AF4, i2c2_scl_pb15 AF4,
 * lptim1_in1_pc0 AF1, adc_in2_pb3, adc_in6_pa10, usart1_tx_pb6 AF7, usart1_rx_pb7 AF7). README.md here
 * has the pin map. Unchanged from the NUCLEO: rain PB4 (EXTI4), mux RESET PB14, sensor power PA9, the
 * charger input divider PA10 (ADC1_IN6). */

#if defined(WS_BENCH_OLED) && WS_BENCH_OLED
#error "WS_BENCH_OLED=1 on the Wio-E5 mini: the OLED's SPI1 pins PA4 and PA5 drive the module's RF switch"
#endif

/* I2C2, the station bus: PA15 SDA and PB15 SCL, AF4. Two ports, so each step takes one pin at a time. PA15
   is JTDI after reset; the debug link is SWD only (PA13, PA14), so taking it costs nothing. */
#define BOARD_I2C_SDA_PORT GPIOA
#define BOARD_I2C_SDA_PIN GPIO_PIN_15 /* PA15 */
#define BOARD_I2C_SCL_PORT GPIOB
#define BOARD_I2C_SCL_PIN GPIO_PIN_15 /* PB15 */
#define BOARD_I2C_GPIO_CLK_ENABLE() do { __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); } while (0)
#define BOARD_I2C_PINS_INIT(init) do { GPIO_InitTypeDef *bp_ = (init); \
    bp_->Pin = BOARD_I2C_SDA_PIN; HAL_GPIO_Init(BOARD_I2C_SDA_PORT, bp_); \
    bp_->Pin = BOARD_I2C_SCL_PIN; HAL_GPIO_Init(BOARD_I2C_SCL_PORT, bp_); } while (0)
#define BOARD_I2C_PINS_DEINIT() do { HAL_GPIO_DeInit(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN); \
    HAL_GPIO_DeInit(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN); } while (0)
#define BOARD_I2C_PINS_HIGH() do { HAL_GPIO_WritePin(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN, GPIO_PIN_SET); \
    HAL_GPIO_WritePin(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN, GPIO_PIN_SET); } while (0)

/* The anemometer cups: LPTIM1_IN1 (AF1) on PC0 (PB5, the NUCLEO's pin, is the mini's LED and not on a
   header). BIT is the pin's number (its PUPDR field). */
#define BOARD_CUPS_PORT GPIOC
#define BOARD_CUPS_PIN GPIO_PIN_0 /* PC0 */
#define BOARD_CUPS_BIT 0U
#define BOARD_CUPS_CLK_ENABLE() __HAL_RCC_GPIOC_CLK_ENABLE()

/* The wind vane divider: PB3, ADC1_IN2 (PB2 is not on a header). PB3 is JTDO/SWO after reset. */
#define BOARD_VANE_PORT GPIOB
#define BOARD_VANE_PIN GPIO_PIN_3 /* PB3 */
#define BOARD_VANE_CHANNEL ADC_CHANNEL_2

/* No bq24074 charger pins: PB1 (ISET) and PB8 (PGOOD) are not on the mini's headers, so the charger
   status and its battery current are reported as none (App/power_acq.c). The ISET rank of the ADC
   sequence converts VREFINT instead, a reading nobody uses; the sequence keeps its four ranks. */
#define BOARD_CHARGER_PINS 0
#define BOARD_ISET_PIN 0U
#define BOARD_ISET_CHANNEL ADC_CHANNEL_VREFINT

/* One user LED, PB5, on when low (Zephyr boards/seeed/lora_e5_mini: led_0 on PB5, GPIO_ACTIVE_LOW;
   Core/Inc/main.h). It is the blue one: radio traffic and the 2 s heartbeat. Green and red have no LED:
   pin 0 makes their writes no-ops (HAL_GPIO_WritePin writes a zero mask to BSRR or BRR). Only blue's pin is
   ever read (App/leds.c, the heartbeat). */
#define BOARD_LED_PORTS { LED1_GPIO_Port, LED1_GPIO_Port, LED1_GPIO_Port }
#define BOARD_LED_PINS  { LED1_Pin, 0U, 0U }
#define BOARD_LED_ON    GPIO_PIN_RESET
#define BOARD_LED_OFF   GPIO_PIN_SET

/* The console: USART1 (PB6 TX, PB7 RX) to the mini's own USB-UART bridge, on its USB-C (Core/Src/usart.c),
   its TX on DMA1 channel 5. */
#define BOARD_CONSOLE_UART       huart1
#define BOARD_CONSOLE_DMA_TX     hdma_usart1_tx
#define BOARD_CONSOLE_IRQHandler USART1_IRQHandler
#define BOARD_CONSOLE_NAME       "USART1"
#endif
