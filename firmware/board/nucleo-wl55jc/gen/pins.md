<!-- GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py. -->
# NUCLEO-WL55JC1 (MB1389): pin map

`nucleo-wl55jc`: STM32WL55JC, roles tx, rx, flashed through its own ST-LINK. Bench OLED: yes.

| Function | Pin | Where | Signal | Note |
|---|---|---|---|---|
| console TX | PA2 | ST-LINK VCP | USART2_TX | the ST-LINK's virtual COM port |
| console RX | PA3 | ST-LINK VCP | USART2_RX | the ST-LINK's virtual COM port |
| I2C SDA | PA11 | D14, CN5.9 | I2C2_SDA |  |
| I2C SCL | PA12 | D15, CN5.10 | I2C2_SCL |  |
| cups | PB5 | D4, CN9.5 | LPTIM1_IN1 |  |
| vane | PB2 | A1, CN8.2 | ADC1_IN4 |  |
| iset | PB1 | A0, CN8.1 | ADC1_IN5 |  |
| vin | PA10 | A2, CN8.3 | ADC1_IN6 |  |
| rain | PB4 | A3, CN8.4 | EXTI4 |  |
| pgood | PB8 | D5, CN9.6 | GPIO |  |
| chg | PB10 | D6, CN9.7 | EXTI10 |  |
| mux_reset | PB14 | A4, CN8.5 | GPIO |  |
| sensor_power | PA9 | D9, CN5.2 | GPIO |  |
| LED1 | PB15 | - | GPIO | blue, active high |
| LED2 | PB9 | - | GPIO | green, active high |
| LED3 | PB11 | - | GPIO | red, active high |
| bench OLED CS | PA4 | CN10.17 | GPIO | WS_BENCH_OLED=1 only |
| bench OLED SCK | PA5 | CN10.11 | SPI1_SCK | WS_BENCH_OLED=1 only |
| bench OLED MOSI | PA7 | CN10.15 | SPI1_MOSI | WS_BENCH_OLED=1 only |
| bench OLED RST | PC1 | CN10.23 | GPIO | WS_BENCH_OLED=1 only |
| bench OLED DC | PC2 | CN10.21 | GPIO | WS_BENCH_OLED=1 only |
| bench OLED B1 | PA0 | B1 | EXTI0 | WS_BENCH_OLED=1 only |
| bench OLED B2 | PA1 | B2 | EXTI1 | WS_BENCH_OLED=1 only |
| bench OLED B3 | PC6 | B3 | EXTI6 | WS_BENCH_OLED=1 only |
| RF switch CTRL1 | PC4 | - | GPIO | ST BSP |
| RF switch CTRL2 | PC5 | - | GPIO | ST BSP |
| RF switch CTRL3 | PC3 | - | GPIO | ST BSP |
| probe1 | PB12 | D2, CN9.3 | reserved | DBG_Init's probe output (Core/Src/sys_debug.c) |
| probe2 | PB13 | A5, CN8.6 | reserved | DBG_Init's probe output (Core/Src/sys_debug.c) |
| swdio | PA13 | - | reserved | SWD |
| swclk | PA14 | - | reserved | SWD |

## Radio

Driver: st-bsp. PA path: lp_hp (RFO_LP max 15 dBm, RFO_HP max 22 dBm). TCXO: 1.7 V, 1 ms start-up. SMPS: yes.

| State | PC4 | PC5 | PC3 |
|---|---|---|---|
| off | 0 | 0 | 0 |
| rx | 1 | 0 | 1 |
| tx_hp | 0 | 1 | 1 |
| tx_lp | 1 | 1 | 1 |
