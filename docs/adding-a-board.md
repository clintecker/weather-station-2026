# Adding a board

A new hardware format in the STM32WL family (a module board, the custom PCB) is one directory,
`firmware/board/<name>/`. You don't change anything else (issue #36).

The node's code (`firmware/stage0-node/App`, `firmware/common`) names no pin and no GPIO port, ADC pin
channel, LPTIM, I2C, UART or EXTI instance. It gets them from the board layer. `tools/boardgen.py`
generates that layer from the board's `board.toml`, and `tools/board_lint.py` keeps it that way in CI.

There's one exception: the bench OLED. `App/oled_dma.c` still drives SPI1 and DMA1 channel 1 directly.
That's why boardgen requires `spi = "SPI1"` for the OLED. `board_lint` doesn't check SPI or DMA.

Use the two boards so far as worked examples:

| Board | Directory | What it shows |
|---|---|---|
| NUCLEO-WL55JC1 | [`firmware/board/nucleo-wl55jc`](../firmware/board/nucleo-wl55jc/board.toml) | ST's BSP drives the RF switch (`driver = "st-bsp"`); both roles; the bench OLED |
| Seeed Wio-E5 mini | [`firmware/board/wio-e5`](../firmware/board/wio-e5/board.toml) | the generic RF-switch driver (`driver = "gpio"`); TX only; charger pins not fitted; `unlock` |

## What a board directory holds

| Path | Written by | What |
|---|---|---|
| `board.toml` | you | every hardware fact the station's code uses (below) |
| `gen/board_pins.h` | `tools/boardgen.py` | the station's pins by function (`BOARD_RAIN_PORT`, `BOARD_I2C`, `BOARD_RAIN_IRQn`, ...) |
| `gen/board_caps.h` | `tools/boardgen.py` | the capabilities, the radio front end, and the `#error`s that stop a build the board cannot run |
| `gen/board.mk` | `tools/boardgen.py` | the MCU define, the startup file, the linker script, the ST BSP if any, the roles, the bench OLED capability and the `unlock` rule |
| `gen/pins.md`, `gen/pins.json` | `tools/boardgen.py` | the pin table, for people and for the hardware checkers |
| `board.mk` | you (three lines, plus comments) | sets `ROOT ?= ../..`, then includes `$(BOARD_DIR)/gen/board.mk` and `$(ROOT)/firmware/board/stm32wl/rules.mk` |
| `Core/`, `startup/`, the linker script | you (from CubeMX or the nearest board) | the board's clock, HAL set-up, console UART, LEDs and low power |

We commit `gen/`, so a plain `make` needs only make and the compiler. Don't edit `gen/` by hand. Edit
`board.toml` and run `python3 tools/boardgen.py`. In CI (and in `tools/code_shape.sh`),
`tools/boardgen.py --check` fails when a board is invalid or its `gen/` is stale.

Everything the boards share is in `firmware/board/stm32wl/`. That's the build rules (`rules.mk`) and
`SubGHz_Phy/`, which has one `radio_board_if.c` driven by `gen/board_caps.h`.

## The checklist

1. **Make the directory.** Copy the nearest board's `Core/`, `startup/`, linker script and `board.mk` into
   `firmware/board/<name>/`. For an STM32WLE5 module, copy `wio-e5`. For a WL55 board, copy `nucleo-wl55jc`.
   Keep the linker script's memory layout: the 190 KB application region, and pages 95 to 127 for the
   node key and journal (`firmware/stage0-node/App/flash_layout.h`).
2. **Fix the CubeMX code for the board.** `Core/` holds the parts the station's code doesn't touch:
   - the clocks (`main.c`, `SystemClock_Config`: MSI plus LSE on both boards so far, no HSE)
   - the console UART (`usart.c`, `usart_if.c`, `stm32wlxx_it.c`)
   - the LEDs and any buttons (`main.h`, `gpio.c`)
   - the probe pins (`sys_debug.h`: set `DISABLE_PROBE_GPIO` when the board has none)
   - `platform.h`: set `USE_BSP_DRIVER` only with `driver = "st-bsp"`

   The TCXO doesn't go in `main.c`. Put it in `board.toml` `[radio]`: `tcxo` (does the radio have one),
   `tcxo_mv` (its voltage) and `tcxo_startup_ms` (its start-up time).
   `tools/boardgen.py` checks that `Core/Inc/main.h` names the same LEDs as `board.toml`. It also checks
   that `Core/Src/usart.c` sets up the console UART that `board.toml` names.
3. **Write `board.toml`.** The format is below. Take every pin, alternate function and ADC channel from
   the board's schematic, and put the source in a comment.
4. **Run `python3 tools/boardgen.py`.** It checks the board against ST's pin data, then writes `gen/`.
   Fix what it reports (see [What the validator checks](#what-the-validator-checks)).
5. **Build:** `make -C firmware/stage0-node ROLE=tx BOARD=<name>`. The link prints the flash and RAM
   budget lines. `python3 tools/board_matrix.py` builds every board, role and power profile with the
   analyzer, the stack bound and the blocking-wait report. CI runs it and picks up the new board by itself.
6. **Write `README.md` for the board.** Cover the wiring, how to flash it, its sources, and the checks
   still open on the hardware.
7. **Bring it up on the bench.** Check what the data can't prove:
   - the RF switch states (RX hears TX, TX hears ACKs, and the sleep current in OFF)
   - the TCXO start-up (no HSE32 or radio-busy timeouts)
   - the console and the LEDs
   - every station input
   - the sleep current

While you're writing a board, it can live outside the tree. Use `make BOARD=<name> BOARD_DIR=/path/to/<name>`
and `tools/boardgen.py --board /path/to/<name>`. `tests/test_boardgen.py` builds a made-up board
(`tests/fixtures/boards/made-up-e5`) this way. It checks that no file outside that directory changes.

## `board.toml`

```toml
[board]
name = "my-board"                 # = the directory name; BOARD=my-board
title = "My board (STM32WLE5JC)"
mcu = "STM32WLE5JC"
mcu_define = "STM32WLE5xx"        # the CMSIS device define
pinctrl = "stm32wle5jcix"         # tools/pinctrl/<pinctrl>-pinctrl.dtsi: ST's pin data for the package
startup = "startup/startup_stm32wle5xx.s"
ldscript = "STM32WLE5JCIX_FLASH.ld"
roles = ["tx"]                    # "tx", "rx" or both; make refuses the others
flash = "nucleo-stlink-swd"       # "onboard-stlink", or "nucleo-stlink-swd" (a NUCLEO's ST-LINK over SWD)
unlock = "openocd-stm32l4x"       # "none", or "openocd-stm32l4x": `make unlock` (RDP level 1 to 0)

[console]                         # the console UART: its pins need <uart>_TX and <uart>_RX
uart = "USART1"
tx = { pin = "PB6" }
rx = { pin = "PB7" }
to = "a USB-UART bridge"

[i2c]                             # the station bus: both pins need <instance>_SDA/SCL on one AF
instance = "I2C2"
sda = { pin = "PA15" }
scl = { pin = "PB15" }

[pins]                            # the station's functions; "at" is where the pin is (a header pin)
cups = { pin = "PC0", af = "LPTIM1_IN1" }       # LPTIMx_IN1: the counter input
vane = { pin = "PB3", adc = 2 }                 # an ADC1 channel of the pin
iset = { pin = "PB1", adc = 5 }                 # on the vane's port
vin = { pin = "PA10", adc = 6 }
rain = { pin = "PB4", exti = true }             # EXTI line 0 to 4: a vector of its own
pgood = { pin = "PB8" }
chg = { pin = "PB10", exti = true }             # EXTI line 5 to 15: a shared vector
mux_reset = { pin = "PB14" }
sensor_power = { pin = "PA9" }

[[led]]                           # one to three, in the order blue, green, red; one active level for all
pin = "PB5"
colour = "blue"
active = "low"

[reserved]                        # pins the board's own code drives: nothing else may take them
swdio = { pin = "PA13", why = "SWD" }

[bench_oled]                      # the bench display (WS_BENCH_OLED=1)
ok = false
why = "its SPI1 pins drive the RF switch"     # the #error text
# ok = true needs spi = "SPI1", cs, sck, mosi, rst, dc and the buttons b1, b2, b3 (see nucleo-wl55jc)

[radio]
driver = "gpio"                   # "gpio": radio_board_if.c drives the switch; "st-bsp": ST's BSP does
switch = ["PA4", "PA5"]           # the switch's control pins, CTRL1 first (one to three)
off = [0, 0]                      # the level of each control pin in each state
rx = [1, 0]
tx_hp = [0, 1]
tx_lp = [1, 1]
pa = "hp"                         # the PA path: "lp_hp", "lp" or "hp"
rfo_lp_max_dbm = 15
rfo_hp_max_dbm = 22
tcxo = true
tcxo_mv = 1700                    # the radio's VDDTCXO (DIO3) voltage
tcxo_startup_ms = 5               # RF_WAKEUP_TIME: how long the radio waits for the TCXO
dcdc = true                       # the SMPS is fitted
```

If the board doesn't connect a charger pin, give that pin `fitted = false` and a `why`. The charger pins
(`iset`, `pgood`, `chg`) are all fitted or none. Without them, the node reports the charger status and its
battery current as none. The board has to fit every other station function.

You can mark a table entry you haven't verified, like the Wio-E5 mini's `off_verified = false`. The
generated header and pin table then say so.

## What the validator checks

`tools/boardgen.py` refuses a board, and writes nothing, when:

- a pin isn't on the package (`tools/pinctrl`), or two functions use one pin
- an alternate function or ADC channel doesn't exist on its pin in ST's pin data
- an alternate function names the wrong peripheral (the I2C instance, the console UART, `LPTIMx_IN1` for
  the cups, `SPI1` for the OLED)
- two EXTI inputs share a line
- the rain gauge, OLED button B1 or OLED button B2 isn't on lines 0 to 4
- CHG or OLED button B3 isn't on lines 5 to 15
- something the node's code assumes doesn't hold:
  - ISET on the vane's port
  - B1 and B2 on one port
  - the OLED's CS, SCK and MOSI on one port, and RST and DC on another
  - the I2C pins on one alternate function
  - the charger pins all fitted or none
  - one active level for the LEDs
- the CubeMX code disagrees about the LEDs or the console UART
- a file it names (startup, linker script) is missing
- a key or section is unknown

Most missing keys get refused too. A few aren't: a missing `[console]` `tx`/`rx` or `[i2c]` `sda`/`scl`
pin, a missing `[radio]` `dcdc`, or a missing LED `colour`. The check passes these, and then the renderer
stops with a Python `KeyError`. It still writes nothing, but you get a traceback instead of a message.

A new package needs its ST pin data. Add its `dts/st/wl/*-pinctrl.dtsi` from the same `hal_stm32` commit
(`tools/pinctrl/README.md`).

## What the build stops

`gen/board_pins.h` includes `gen/board_caps.h`. That header stops the compile for a role the board doesn't
allow. It also stops `WS_BENCH_OLED=1` on a board that can't drive the OLED.
`firmware/stage0-node/Makefile` stops earlier, for the same reasons, from `gen/board.mk`. It also refuses a
`BOARD` with no `board.toml`.

## Limits

The board layer covers the STM32WL family, which shares the core, the radio and the HAL. The node's code
fixes the station's own wiring:

- one I2C bus
- the cups on an LPTIM input
- three ADC inputs and the VREFINT reference
- the rain and CHG interrupts
- up to three LEDs

So a board with a different sensor set means a change to the node, not only a new board.
