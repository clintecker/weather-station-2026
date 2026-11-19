# ST pin data for the board validator

`tools/boardgen.py` checks every board's pin map (`firmware/board/<name>/board.toml`) against these
files. Each alternate function and ADC channel a board names must exist on that pin.

| File | Package |
|---|---|
| `stm32wl55jcix-pinctrl.dtsi` | STM32WL55JC, UFBGA73 (NUCLEO-WL55JC1) |
| `stm32wle5jcix-pinctrl.dtsi` | STM32WLE5JC, UFBGA73 (Seeed LoRa-E5 module) |

The two files are byte-identical. The two parts share a package and its pinout.

They come from Zephyr's `hal_stm32` module, https://github.com/zephyrproject-rtos/hal_stm32, commit
`9dd7ccaefb5df6bf750d4d52cfd4b88eed2d0923` (2026-11-06), `dts/st/wl/`. We didn't change them
(SHA-256 `dc61cb238fb8811538532fd6b28dad6bf6f55b2a2fc98d2e766f27ab34f13248`). ST generates them with
`genpinctrl.py` from its own pin database.

Licence: Apache-2.0. The files carry `SPDX-License-Identifier: Apache-2.0`. `hal_stm32`'s `LICENSE`
puts its whole `dts/` folder under Apache-2.0. We copied that `LICENSE` here unchanged, and it holds
the Apache-2.0 text.

If you add a board on another package, take its file from the same commit. If you bump the commit,
bump it for every file at once and update this note.
