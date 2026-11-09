# Seeed Wio-E5 mini: the TX board (issue #35)

The Wio-E5 mini carries Seeed's LoRa-E5 module (STM32WLE5JC: the single-core WL55, the same Cortex-M4,
256 KB flash, 64 KB RAM and sub-GHz radio), 2.54 mm headers, an SMA connector, a USB-UART bridge on its
USB-C, an LDO, and RESET and BOOT buttons. This directory is its board layer for `firmware/stage0-node`.
It builds the TX only, as the field build (no bench OLED). The RX stays on the NUCLEO.

```sh
cd firmware/stage0-node
make ROLE=tx BOARD=wio-e5                                    # build/tx-wio-e5/stage0-tx.{elf,bin}
make BOARD=wio-e5 unlock SERIAL=<NUCLEO ST-LINK serial>      # once per new board (below)
make ROLE=tx BOARD=wio-e5 flash SERIAL=<NUCLEO ST-LINK serial>
```

Written and compiled before the boards arrived. Nothing here has run on hardware yet: see
[Open hardware checks](#open-hardware-checks).

## Pin map

| Function | NUCLEO-WL55JC1 | Wio-E5 mini | Notes |
|---|---|---|---|
| I2C2 SDA / SCL | PA11 / PA12 | **PA15 / PB15** | AF4 on both. PA15 is JTDI after reset (SWD only, so it is free) |
| Cups (LPTIM1_IN1, AF1) | PB5 | **PC0** | PB5 is the mini's LED and is not on a header |
| Vane (ADC) | PB2, ADC1_IN4 | **PB3, ADC1_IN2** | PB3 is JTDO/SWO after reset |
| Rain (EXTI4) | PB4 | PB4 | |
| Mux RESET | PB14 | PB14 | |
| Sensor power enable | PA9 | PA9 | |
| Charger input divider (ADC1_IN6) | PA10 | PA10 | |
| bq24074 PGOOD, CHG, ISET | PB8, PB10, PB1 | **none** | PB1 and PB8 are not on the headers; see [Power profile](#power-profile) |
| Console | USART2 PA2/PA3, ST-LINK VCP | **USART1 PB6/PB7**, the mini's USB-C | 115200 8N1, as before |
| Status LED | LED1 blue, LED2 green, LED3 red | **PB5 only, active low = blue** | green and red are no-ops |
| RF switch | ST BSP (PC3, PC4, PC5) | **PA4, PA5** (module-internal) | the generic `../stm32wl/SubGHz_Phy/Target/radio_board_if.c` |

The pins come from `board.toml` here (issue #36): `tools/boardgen.py` checks them against ST's pin data and
writes `gen/board_pins.h`, `gen/board_caps.h` and the pin table `gen/pins.md`. The NUCLEO has its own
`board.toml` (`../nucleo-wl55jc`), so `App/board_inputs.c`, `App/i2c_bus.lit.md`, `App/leds.c`,
`App/power_acq.c` and `Core/Src/stm32wlxx_it.c` name no pin themselves (`tools/board_lint.py` keeps it so).
The NUCLEO images are byte-identical to the ones built before either change.

The headers expose 5V, 3V3, GND, RST, PA13 (SWDIO), PA14 (SWCLK), PA0, PA2, PA3, PA9, PA10, PA15, PB3,
PB4, PB6, PB7, PB9, PB10, PB13 (the BOOT button, active low), PB14, PB15, PC0 and PC1. Source: Zephyr
`boards/seeed/lora_e5_mini` (pinout). The alternate functions and ADC channels come from Zephyr
`hal_stm32` `dts/st/wl/stm32wle5jcix-pinctrl.dtsi` (commit 9dd7ccae). Free for later: PA0, PA2, PA3,
PB9, PB10, PB13 (with the button) and PC1.

## Power profile

The node is built with `WS_POWER_PROFILE` 1 (phase A, the default): the battery INA228 (0x40) and the
MAX17048 (0x36), both over I2C.

- **Profile 2** needs three more INA228s. That is a different build of the hardware, not something the
  board decides.
- **Profile 3** (BQ25798) is a later phase.

Both existing profiles read the bq24074's PGOOD, CHG and ISET pins. Two of those pins are not on the
mini's headers, so the board layer sets `BOARD_CHARGER_PINS 0`. With that setting:

- PGOOD and CHG are never configured. `board_charger_pins()` returns 0.
- The charger status in the health report is the none code (0xFF), not "no input". The charger's
  battery current (ISET) is none, not 0 mA (`App/power_acq.c`).
- The ADC keeps its four-rank sequence. The ISET rank converts VREFINT, and nothing reads it.
- The charger input divider on PA10 is still read. It reports what is on that pin: wire the divider,
  or ignore the slot.

So this is profile 1 with the charger pins absent. It is the nearest existing profile to "battery
INA228 and MAX17048 with no charger pins". PB10 (CHG) is on a header, but CHG means little without
PGOOD, so it is left unused.

## Wiring: SWD from the NUCLEO's ST-LINK

The mini has no debug probe. Flash it through the NUCLEO-WL55JC1's on-board STLINK-V3E used as an
external probe:

| NUCLEO ST-LINK | Wio-E5 mini |
|---|---|
| SWDIO | PA13 (DIO) |
| SWCLK | PA14 (CLK) |
| NRST (target reset) | RST |
| GND | GND |
| VDD target sense (3V3) | 3V3 |

Power the mini from its own USB-C, which also carries the console. `flash` and `unlock` use OpenOCD
(`interface/stlink.cfg`, `target/stm32wlx.cfg`) with `connect_assert_srst`, so the RST wire is needed.

**To be confirmed on the hardware.** We have not found the NUCLEO (MB1389, STLINK-V3E) setting that
disconnects its own STM32WL from the ST-LINK's SWD lines, or the connector that brings those lines out
for an external target. Issue #35 says "remove the CN2 jumpers", but that is the older ST-LINK/V2-1
Nucleo-64 design. UM2592 covers the other direction: an external debugger programming the on-board
STM32WL. An ST community thread
(community.st.com, "Using the ST-Link V3E on the STM32WL-Nucleo Board") asks this exact question and
gets no answer in the visible replies. Find it on the board and in the MB1389 schematic before you
wire anything. The other option is a standalone ST-LINK or any CMSIS-DAP probe, with the same OpenOCD
target.

## Unlock (once per board) and flash

Seeed ships the module with its AT firmware under read-out protection (RDP) level 1, and BOOT0 is not
accessible. Regressing RDP to level 0 mass-erases the flash, the AT firmware with it:

```sh
make BOARD=wio-e5 unlock SERIAL=<serial>
```

This runs `stm32l4x unlock 0`, then `stm32l4x option_load 0`. The commands come from OpenOCD 0.12.0's
manual, Flash Commands, stm32l4x driver, which `target/stm32wlx.cfg` uses for bank 0: "Unlocks the
entire stm32 device", and "To apply the protection change immediately, use 'stm32l4x option_load'",
which "will cause a system reset of the device". OpenOCD may report a lost connection after the reset.

**To be confirmed on the first board.** If it fails, STM32CubeProgrammer's "RDP = AA" (option bytes)
does the same. Then `make ROLE=tx BOARD=wio-e5 flash SERIAL=<serial>`, as on the NUCLEO. The board needs
a new key: greenfield, no migration.

## Console

USART1 on PB6 (TX) and PB7 (RX) goes to the mini's own USB-UART bridge, on its USB-C, at 115200 8N1.
It is the same console as the NUCLEO's VCP, with the same commands and the same wake on a start bit
(EXTI line 26, USART1's, in `Core/Src/usart_if.c`).

## Radio

`board.toml` `[radio]` holds the RF switch truth table, its sources and the one point where they disagree;
the generic `../stm32wl/SubGHz_Phy/Target/radio_board_if.c` drives it. The table is Seeed's own STM32CubeWL port (`Seeed-Studio/LoRaWan-E5-Node`, commit 163c0537,
`stm32wlxx_LoRa_E5_mini_radio.c`, `BSP_RADIO_ConfigRFSwitch`):

| State | PA4 | PA5 |
|---|---|---|
| OFF | 0 | 0 |
| RX | 1 | 0 |
| RFO_HP (TX) | 0 | 1 |

Zephyr (`lora-e5.dtsi`: PA4 TX enable, PA5 RX enable, both active low) agrees on RX and TX. For OFF it
would leave both pins high. Only RFO_HP is wired (max 22 dBm).

The TCXO (32 MHz) is powered from the radio's VDDTCXO at 1.7 V. Its startup allowance is
5 ms (`tcxo_startup_ms` in `board.toml`, which becomes `RF_WAKEUP_TIME`; Zephyr's value, Seeed's port keeps ST's 1 ms).
The SMPS (DCDC) is on, as Seeed's BSP reports it fitted.

## Open hardware checks

1. The NUCLEO STLINK-V3E's external-target setting (jumpers or solder bridges, and the connector), above.
2. `unlock` regresses RDP 1 to 0 and the AT firmware is gone. Then `flash` and `verify` pass.
3. The console on USB-C: the banner, then `#status`. A character wakes it from Stop (EXTI 26).
4. The LED (PB5) blinks the heartbeat, and its sense is right (active low).
5. RF switch: the RX hears the TX, and the TX hears ACKs (RFO_HP, RX). Then the sleep current with the
   switch OFF (0, 0) compared with (1, 1) (the OFF state is unverified).
6. TCXO: no HSE32 or radio-busy timeouts at boot or after Stop. Try `tcxo_startup_ms` 1 against 5.
7. I2C2 on PA15/PB15: `#status` shows the INA228 and the MAX17048 answering.
8. Cups on PC0 count (LPTIM1), the vane on PB3 reads, the rain tips on PB4 count, and the link probe
   verdicts are right.
9. The sleep current against the NUCLEO TX on the same INA228. The mini's USB-UART bridge and LDO draw
   current too.
10. The range and link test against the NUCLEO RX (issue #35).
