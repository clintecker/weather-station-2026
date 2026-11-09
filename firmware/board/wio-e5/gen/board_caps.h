#ifndef BOARD_CAPS_H
#define BOARD_CAPS_H
/* GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
 * What the Seeed Wio-E5 mini (LoRa-E5, STM32WLE5JC) can do, and its radio front end: the generic
 * firmware/board/stm32wl/SubGHz_Phy/Target/radio_board_if.c reads the RF switch, TCXO and PA path here. */

#define BOARD_NAME "wio-e5"
#define BOARD_ROLE_TX 1
#define BOARD_ROLE_RX 0
#define BOARD_BENCH_OLED_OK 0
#define BOARD_LED_COUNT 1

/* Feature requirements: a build the board cannot run stops here. */
#if defined(WS_BENCH_OLED) && WS_BENCH_OLED && !BOARD_BENCH_OLED_OK
#error "WS_BENCH_OLED=1 on the wio-e5 board: the OLED's SPI1 pins PA4 and PA5 drive the module's RF switch"
#endif
#if defined(WS_ROLE_rx)
#error "ROLE=rx on the wio-e5 board: its board.toml roles are tx"
#endif

/* The radio: the RF switch on PA4, PA5 (CTRL1..CTRL2), driven by radio_board_if.c. Truth table (levels in that order):
     off    0  0   UNVERIFIED on the hardware (board.toml)
     rx     1  0
     tx_hp  0  1
     tx_lp  1  1
   */
#define BOARD_RF_SWITCH_BSP 0
#define BOARD_RFO RBI_CONF_RFO_HP /* PA path: hp */
#define BOARD_RFO_LP_MAX_DBM 15
#define BOARD_RFO_HP_MAX_DBM 22
#define BOARD_TCXO 1U
#define BOARD_TCXO_CTRL_VOLTAGE TCXO_CTRL_1_7V
#define BOARD_TCXO_STARTUP_MS ( 5UL )
#define BOARD_DCDC 1U
/* For radio_board_if.c: the switch pins, the rf_switch() parameters and body, and each state's levels. */
#define BOARD_RF_SW_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define BOARD_RF_SW_PINS_INIT(init) do { (init)->Pin = GPIO_PIN_4; HAL_GPIO_Init(GPIOA, (init)); (init)->Pin = GPIO_PIN_5; HAL_GPIO_Init(GPIOA, (init)); } while (0)
#define BOARD_RF_SW_PINS_DEINIT() do { HAL_GPIO_DeInit(GPIOA, GPIO_PIN_4); HAL_GPIO_DeInit(GPIOA, GPIO_PIN_5); } while (0)
#define BOARD_RF_SW_PARAMS GPIO_PinState ctrl1, GPIO_PinState ctrl2
#define BOARD_RF_SW_WRITE() do { HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, ctrl1); HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, ctrl2); } while (0)
#define BOARD_RF_SW_OFF GPIO_PIN_RESET, GPIO_PIN_RESET
#define BOARD_RF_SW_RX GPIO_PIN_SET, GPIO_PIN_RESET
#define BOARD_RF_SW_TX_HP GPIO_PIN_RESET, GPIO_PIN_SET
#define BOARD_RF_SW_TX_LP GPIO_PIN_SET, GPIO_PIN_SET

#endif
