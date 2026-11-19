# Seeed Wio-E5 mini: the TX board (issue #35)

The Wio-E5 mini carries Seeed's LoRa-E5 module. That module is an STM32WLE5JC: the single-core WL55,
with the same Cortex-M4, 256 KB flash, 64 KB RAM and sub-GHz radio. The mini also has 2.54 mm headers,
an SMA connector, a USB-UART bridge on its USB-C, an LDO, and RESET and BOOT buttons. This directory is
its board layer for `firmware/stage0-node`. It builds the TX only, as the field build (no bench OLED).
The RX stays on the NUCLEO.

```sh
cd firmware/stage0-node
make ROLE=tx BOARD=wio-e5                                    # build/tx-wio-e5/stage0-tx.{elf,bin}
make BOARD=wio-e5 unlock SERIAL=<NUCLEO ST-LINK serial>      # once per new board (below)
make ROLE=tx BOARD=wio-e5 flash SERIAL=<NUCLEO ST-LINK serial>
```

We wrote and compiled all of this before the boards arrived. None of it ran on hardware yet. See
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

The pins come from `board.toml` in this directory (issue #36). `tools/boardgen.py` checks them against
ST's pin data. It then writes `gen/board_pins.h`, `gen/board_caps.h` and the pin table `gen/pins.md`.
The NUCLEO has its own `board.toml` (`../nucleo-wl55jc`). So `App/board_inputs.c`, `App/i2c_bus.lit.md`,
`App/leds.c`, `App/power_acq.c` and `Core/Src/stm32wlxx_it.c` name no pin themselves.

`tools/board_lint.py` runs in CI. It keeps App/ and `firmware/common` free of pin names. In App/ that
means `board_inputs.c`, `leds.c`, `power_acq.c` and the `i2c_bus.c` tangled from `i2c_bus.lit.md`.
`Core/Src/stm32wlxx_it.c` is outside its default paths. It names no pin today, but nothing checks it.
The NUCLEO images are byte-identical to the ones built before either change.

The headers expose 5V, 3V3, GND, RST, PA13 (SWDIO), PA14 (SWCLK), PA0, PA2, PA3, PA9, PA10, PA15, PB3,
PB4, PB6, PB7, PB9, PB10, PB13 (the BOOT button, active low), PB14, PB15, PC0 and PC1. Source: Zephyr
`boards/seeed/lora_e5_mini` (pinout). The alternate functions and ADC channels come from Zephyr
`hal_stm32` `dts/st/wl/stm32wle5jcix-pinctrl.dtsi` (commit 9dd7ccae). These pins are free for later
use: PA0, PA2, PA3, PB9, PB10, PB13 (with the button) and PC1.

## Power profile

The node builds with `WS_POWER_PROFILE` 1 (phase A, the default). That profile reads the battery INA228
(0x40) and the MAX17048 (0x36), both over I2C.

- **Profile 2** needs three more INA228s. That's a different build of the hardware. The board doesn't
  decide it.
- **Profile 3** (BQ25798) is a later phase.

Both existing profiles read the bq24074's PGOOD, CHG and ISET pins. Two of those pins aren't on the
mini's headers, so the board layer sets `BOARD_CHARGER_PINS 0`. With that setting:

- The firmware never configures PGOOD and CHG. `board_charger_pins()` returns 0.
- The health report gives the none code (0xFF) for charger status, not "no input". It also gives none
  for the charger's battery current (ISET), not 0 mA (`App/power_acq.c`).
- The ADC keeps its four-rank sequence. The ISET rank converts VREFINT, and nothing reads it.
- The firmware still reads the charger input divider on PA10. It reports what's on that pin. So wire
  the divider, or ignore that slot.

So this is profile 1 with the charger pins absent. It's the nearest existing profile to "battery
INA228 and MAX17048 with no charger pins". PB10 (CHG) is on a header. But CHG means little without
PGOOD, so we leave it unused.

## Wiring: SWD from the NUCLEO's ST-LINK

The mini has no debug probe. You flash it through the NUCLEO-WL55JC1's on-board STLINK-V3E, used as an
external probe.

The left column gives generic SWD signal names, not NUCLEO connector pins. We don't know the
NUCLEO-side pin-out yet (see "To be confirmed on the hardware" below). The right column is the mini's
header pin, from `board.toml`.

| NUCLEO ST-LINK | Wio-E5 mini |
|---|---|
| SWDIO | PA13 (DIO) |
| SWCLK | PA14 (CLK) |
| NRST (target reset) | RST |
| GND | GND |
| VDD target sense (3V3) | 3V3 |

Power the mini from its own USB-C, which also carries the console. `flash` and `unlock` use OpenOCD
(`interface/stlink.cfg`, `target/stm32wlx.cfg`) with `connect_assert_srst`. So you need the RST wire.

**To be confirmed on the hardware.** We haven't found the NUCLEO (MB1389, STLINK-V3E) setting that
disconnects its own STM32WL from the ST-LINK's SWD lines. We also haven't found the connector that
brings those lines out for an external target. Issue #35 says "remove the CN2 jumpers". That's the
older ST-LINK/V2-1 Nucleo-64 design, though. UM2592 covers the other direction: an external debugger
programming the on-board STM32WL.

An ST community thread (community.st.com, "Using the ST-Link V3E on the STM32WL-Nucleo Board") asks
this exact question, and the visible replies don't answer it. Find the setting and the connector on the
board and in the MB1389 schematic before you wire anything. The other option is a standalone ST-LINK or any CMSIS-DAP
probe, with the same OpenOCD target.

## Unlock (once per board) and flash

Seeed ships the module with its AT firmware under read-out protection (RDP) level 1. BOOT0 isn't
accessible.

**Caution:** when you take RDP back to level 0, the chip mass-erases its flash. The AT firmware goes
with it.

```sh
make BOARD=wio-e5 unlock SERIAL=<serial>
```

This runs `stm32l4x unlock 0`, then `stm32l4x option_load 0`. The commands come from the OpenOCD 0.12.0
manual, Flash Commands, stm32l4x driver. `target/stm32wlx.cfg` uses that driver for bank 0. The manual
says `unlock` "Unlocks the entire stm32 device". It also says "To apply the protection change
immediately, use 'stm32l4x option_load'", which "will cause a system reset of the device". OpenOCD may
report a lost connection after the reset.

**To be confirmed on the first board.** If `unlock` fails, STM32CubeProgrammer's "RDP = AA" (option
bytes) does the same thing. Then run `make ROLE=tx BOARD=wio-e5 flash SERIAL=<serial>`, as on the
NUCLEO. The board needs a new key: greenfield, no migration.

## Console

USART1 on PB6 (TX) and PB7 (RX) goes to the mini's own USB-UART bridge, on its USB-C, at 115200 8N1.
It's the same console as the NUCLEO's VCP, with the same commands. It also wakes on a start bit the same
way (EXTI line 26, USART1's, in `Core/Src/usart_if.c`).

## Radio

`board.toml` `[radio]` holds the RF switch truth table, its sources and the one point where they
disagree. The generic `../stm32wl/SubGHz_Phy/Target/radio_board_if.c` drives the switch. The table
comes from Seeed's own STM32CubeWL port (`Seeed-Studio/LoRaWan-E5-Node`, commit 163c0537,
`stm32wlxx_LoRa_E5_mini_radio.c`, `BSP_RADIO_ConfigRFSwitch`):

| State | PA4 | PA5 |
|---|---|---|
| OFF | 0 | 0 |
| RX | 1 | 0 |
| RFO_HP (TX) | 0 | 1 |

Zephyr (`lora-e5.dtsi`: PA4 TX enable, PA5 RX enable, both active low) agrees on RX and TX. For OFF,
Zephyr would leave both pins high. Only RFO_HP is wired (max 22 dBm).

The TCXO (32 MHz) runs from the radio's VDDTCXO at 1.7 V. Its startup allowance is 5 ms
(`tcxo_startup_ms` in `board.toml`, which becomes `RF_WAKEUP_TIME`). That's Zephyr's value. Seeed's
port keeps ST's 1 ms. The SMPS (DCDC) is on, because Seeed's BSP reports it fitted.

## Open hardware checks

1. The NUCLEO STLINK-V3E's external-target setting (jumpers or solder bridges, and the connector), above.
2. `unlock` takes RDP from 1 to 0 and erases the AT firmware. Then `flash` and `verify` pass.
3. The console on USB-C: the banner, then `#status`. A character wakes it from Stop (EXTI 26).
4. The LED (PB5) blinks the heartbeat, and its sense is right (active low).
5. RF switch: the RX hears the TX, and the TX hears ACKs (RFO_HP, RX). Then compare the sleep current
   with the switch at OFF (0, 0) against (1, 1). Nobody checked the OFF state yet.
6. TCXO: no HSE32 or radio-busy timeouts at boot or after Stop. Try `tcxo_startup_ms` 1 against 5.
7. I2C2 on PA15/PB15: TEST-SENSOR-POWER's `#test` lines show the INA228 (ack bit 0x010) and the
   MAX17048 (ack bit 0x100) answering. Ignore the first line, whose half is empty. `#counts` shows
   `i2c_recoveries` and `i2c_stuck` staying at 0.
8. Cups on PC0 count (LPTIM1), the vane on PB3 reads, the rain tips on PB4 count, and the link probe
   verdicts are right.
9. The sleep current against the NUCLEO TX on the same INA228. The mini's USB-UART bridge and LDO draw
   current too.
10. The range and link test against the NUCLEO RX (issue #35).
