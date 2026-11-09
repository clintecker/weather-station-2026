# Adding a board

A new hardware format in the STM32WL family (a module board, the custom PCB) is one directory,
`firmware/board/<name>/`, and no change anywhere else (issue #36). The node's code (`firmware/stage0-node/App`,
`firmware/common`) names no pin and no peripheral instance. It takes them from the board layer, which
`tools/boardgen.py` generates from the board's `board.toml`. `tools/board_lint.py` keeps it that way in CI.

The two boards so far are worked examples:

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
| `board.mk` | you (two lines) | includes `gen/board.mk`, then `../stm32wl/rules.mk` |
| `Core/`, `startup/`, the linker script | you (from CubeMX or the nearest board) | the board's clock, HAL set-up, console UART, LEDs and low power |

`gen/` is committed, so a plain `make` needs only make and the compiler. Never edit it by hand: edit
`board.toml` and run `python3 tools/boardgen.py`. `tools/boardgen.py --check` in CI (and in
`tools/code_shape.sh`) fails when a board is invalid or its `gen/` is stale.

What every board shares lives in `firmware/board/stm32wl/`: the build rules (`rules.mk`) and
`SubGHz_Phy/` (one `radio_board_if.c`, driven by `gen/board_caps.h`).

## The checklist

1. **Make the directory.** Copy the nearest board's `Core/`, `startup/`, linker script and `board.mk` into
   `firmware/board/<name>/`. For an STM32WLE5 module that is `wio-e5`; for a WL55 board, `nucleo-wl55jc`.
   Keep the linker script's memory layout: the 190 KB application region and pages 95 to 127 for the node
   key and journal (`firmware/stage0-node/App/flash_layout.h`).
2. **Fix the CubeMX code for the board.** `Core/` holds what the station's code does not touch:
   - the clocks (`main.c`: HSE from the TCXO, or not);
   - the console UART (`usart.c`, `usart_if.c`, `stm32wlxx_it.c`);
   - the LEDs and any buttons (`main.h`, `gpio.c`);
   - the probe pins (`sys_debug.h`: `DISABLE_PROBE_GPIO` when the board has none);
   - `platform.h`: `USE_BSP_DRIVER` only with `driver = "st-bsp"`.
   `tools/boardgen.py` checks that `Core/Inc/main.h` names the same LEDs as `board.toml` and that
   `Core/Src/usart.c` sets up the console UART it names.
3. **Write `board.toml`** (the format is below). Take every pin, alternate function and ADC channel from
   the board's schematic, and give the source in a comment.
4. **Run `python3 tools/boardgen.py`.** It checks the board against ST's pin data, then writes `gen/`.
   Fix what it reports (see [What the validator checks](#what-the-validator-checks)).
5. **Build:** `make -C firmware/stage0-node ROLE=tx BOARD=<name>`. The link prints the flash and RAM
   budget lines. `python3 tools/board_matrix.py` builds every board, role and power profile with the
   analyzer, the stack bound and the blocking-wait report. CI runs it, and picks the new board up by itself.
6. **Write `README.md`** for the board: the wiring, how to flash it, its sources, and the checks still
   open on the hardware.
7. **Bring it up on the bench.** Check what the data cannot prove: the RF switch states (RX hears TX, TX
   hears ACKs, and the sleep current in OFF), the TCXO start-up (no HSE32 or radio-busy timeouts), the
   console, the LEDs, every station input, and the sleep current.

A board being written can live outside the tree: `make BOARD=<name> BOARD_DIR=/path/to/<name>` and
`tools/boardgen.py --board /path/to/<name>`. `tests/test_boardgen.py` builds a made-up board
(`tests/fixtures/boards/made-up-e5`) this way, and checks that no file outside its directory changes.

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

A charger pin the board does not connect is `fitted = false` with a `why`. The charger pins (`iset`,
`pgood`, `chg`) are all fitted or none: without them the node reports the charger status and its battery
current as none. Every other station function must be fitted. An unverified table entry can be marked, as
the Wio-E5 mini's `off_verified = false`; the generated header and pin table then say so.

## What the validator checks

`tools/boardgen.py` refuses a board, and writes nothing, when:

- a pin is not on the package (`tools/pinctrl`), or two functions use one pin;
- an alternate function or ADC channel does not exist on its pin in ST's pin data, or names the wrong
  peripheral (the I2C instance, the console UART, `LPTIMx_IN1` for the cups, `SPI1` for the OLED);
- two EXTI inputs share a line, the rain gauge or OLED button B1 or B2 is not on lines 0 to 4, or CHG or B3
  is not on lines 5 to 15;
- what the node's code assumes does not hold: ISET on the vane's port, B1 and B2 on one port, the OLED's
  CS, SCK and MOSI on one port and RST and DC on another, the I2C pins on one alternate function, the
  charger pins all fitted or none, one active level for the LEDs;
- the CubeMX code disagrees about the LEDs or the console UART;
- a file it names (startup, linker script) is missing, or a key is missing or unknown.

A new package needs its ST pin data: add its `dts/st/wl/*-pinctrl.dtsi` from the same `hal_stm32` commit
(`tools/pinctrl/README.md`).

## What the build stops

`gen/board_caps.h`, which `gen/board_pins.h` includes, stops the compile for a role the board does not
allow and for `WS_BENCH_OLED=1` on a board that cannot drive the OLED. `firmware/stage0-node/Makefile`
stops earlier with the same reasons, from `gen/board.mk`, and refuses a `BOARD` with no `board.toml`.

## Limits

The board layer covers the STM32WL family: the same core, radio and HAL. The station's own wiring is
fixed by the node's code: one I2C bus, the cups on an LPTIM input, three ADC inputs and the VREFINT
reference, the rain and CHG interrupts, and up to three LEDs. A board with a different sensor set is a
change to the node, not only a new board.
