<!-- GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py. -->
# Seeed Wio-E5 mini (LoRa-E5, STM32WLE5JC): pin map

`wio-e5`: STM32WLE5JC, roles tx, flashed through a NUCLEO's ST-LINK as an external probe over SWD, `make unlock` once per new board. Bench OLED: no (the OLED's SPI1 pins PA4 and PA5 drive the module's RF switch).

| Function | Pin | Where | Signal | Note |
|---|---|---|---|---|
| console TX | PB6 | TX | USART1_TX | the mini's own USB-UART bridge, on its USB-C |
| console RX | PB7 | RX | USART1_RX | the mini's own USB-UART bridge, on its USB-C |
| I2C SDA | PA15 | PA15 | I2C2_SDA |  |
| I2C SCL | PB15 | PB15 | I2C2_SCL |  |
| cups | PC0 | PC0 | LPTIM1_IN1 |  |
| vane | PB3 | PB3 | ADC1_IN2 |  |
| iset | - | - | GPIO | not fitted: PB1 is not on the mini's headers |
| vin | PA10 | PA10 | ADC1_IN6 |  |
| rain | PB4 | PB4 | EXTI4 |  |
| pgood | PB8 | - | GPIO | not fitted: PB8 is not on the mini's headers |
| chg | PB10 | - | EXTI10 | not fitted: CHG means little without PGOOD |
| mux_reset | PB14 | PB14 | GPIO |  |
| sensor_power | PA9 | PA9 | GPIO |  |
| LED1 | PB5 | - | GPIO | blue, active low |
| RF switch CTRL1 | PA4 | - | GPIO | radio_board_if.c |
| RF switch CTRL2 | PA5 | - | GPIO | radio_board_if.c |
| swdio | PA13 | SWDIO | reserved | SWD |
| swclk | PA14 | SWCLK | reserved | SWD |
| boot | PB13 | PB13 | reserved | the BOOT button (no probe output: Core/Inc/sys_debug.h) |

## Radio

Driver: gpio. PA path: hp (RFO_LP max 15 dBm, RFO_HP max 22 dBm). TCXO: 1.7 V, 5 ms start-up. SMPS: yes.

| State | PA4 | PA5 |
|---|---|---|
| off (unverified) | 0 | 0 |
| rx | 1 | 0 |
| tx_hp | 0 | 1 |
| tx_lp | 1 | 1 |
