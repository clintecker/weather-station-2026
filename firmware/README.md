# NUCLEO-WL55JC1 firmware groundwork

**Board firmware now lives in [`stage0-node/`](stage0-node/README.md)** (2026-10-12: TX/RX built, flashed, link verified on the bench; sensor not yet wired; H01 NOT RUN).

## Layout

| Path | What |
|---|---|
| `board/nucleo-wl55jc/` | Shared NUCLEO-WL55JC1 board code from ST's CubeWL template (`Core/`, `startup/`, `SubGHz_Phy/Target/`), the linker script (64 KB application region for every project: pages 32–127 hold the node key and journal) and `board.mk`, the common build rules each project Makefile includes. `Core/Inc/sys_conf.h` takes `VERBOSE_LEVEL` and `LOW_POWER_DISABLE` from the project's `DEFS`. |
| `stage0-node/` | The weather-station firmware, TX and RX roles. Keeps its own `Core/Src/stm32wlxx_it.c` (flash-ECC NMI, HardFault record). |
| `rangetest/` | Bench range-test tool (`rangetest/README.md`). |
| `common/` | Frame, observation and console code shared by the firmware and the host tests. |
| `fuzz/` | Host fuzz targets for the input parsers (`fuzz/README.md`). |
| `stage0.c`, `test_*.c`, `sim_flash.*` | Portable sensor and policy code plus the host test drivers run by `tests/`. |

Each project keeps only its application, its sequencer task list (`Core/Inc/utilities_def.h`) and a short
Makefile that sets `TARGET`, `APP_SRC`, `DEFS` and `OPT` before including `../board/nucleo-wl55jc/board.mk`.

`stage0.c` and `stage0.h` provide portable SHT45 acquisition and packet serialization.
They compile with warnings-as-errors in the host tests and are linked unchanged into the
TX firmware. (The original checkpoint note that no ARM build or radio transmission had been
performed is superseded by `stage0-node/`.)

## Existing hardware target

Two ST NUCLEO-WL55JC1 boards: sensor transmitter and powered USB receiver.
SHT45 PTFE breakout: Adafruit 6174, superseding the starter's older 5665 suggestion.
The supplied development boards, their antennas and USB data cables are the Stage-0
platform; custom boards and printed fixtures are not required to validate this link.

## Target integration status

Original plan, in order; status as of 2026-10-13. Done items point to where they live.

1. **Done.** Vendor and toolchain pinned: `tools/fetch-vendor.sh` (STM32CubeWL v1.6.0 at
   commit `f934cd2…` plus submodule commits), xPack arm-none-eabi-gcc 15.2.1-1.1
   (`stage0-node/Makefile` `TOOLCHAIN`), OpenOCD over ST-LINK for flashing.
2. **Done on paper, hardware check open.** Sensor on I2C2, PA11 = SDA and PA12 = SCL
   (`stage0-node/App/sensor.c`), checked against UM2592 Rev 4 Tables 17/18. Wiring:
   `docs/protocol-stack.md` §3.1. The C callback contract uses the 7-bit address 0x44;
   `sensor.c` shifts it for the HAL. Not yet verified with the sensor wired.
3. **Done in firmware, hardware check open.** HAL I2C callbacks with timeouts, one
   high-precision heater-off measurement a minute (`stage0.c`), stuck-bus recovery
   (`sensor.c` `i2c_recover`); CRC or bus failure gives an explicit invalid reading. Unplug
   and restart behaviour still has to be tested on hardware.
4. **Done.** AES-128-CCM with a 16-byte tag through ST's Mbed TLS (`common/ws_frame.c`),
   checked against host-generated known-answer frames at boot (`stage0-node/App/selftest.c`
   `selftest_kat`) and in `tests/test_frame.py`. Wired provisioning: console `PROVISION`, host
   `python -m ws0 provision-node`. Durable counter and epoch: `stage0-node/App/node_store.c`.
5. **Done for Stage 0.** Flash journal of 4,743 observations (about 3.3 days), kept until an
   authenticated ACK; boot epoch reserved before sampling (`stage0-node/README.md`, "Flash
   layout"). Reset-during-write test passed; true power-cut test
   deferred. **Open:** the 30-day/16 MB H11 target (external SPI NOR).
6. **Done.** RX bridge prints frames as hex lines and transmits the host's ACK/NACK
   (`stage0-node/App/app_rx.c`; host side `ws0/link.py`, `ws0 serve`). Host UTC rides in the
   authenticated ACK. TX sends the live reading ahead of a bounded backlog drain.
7. **Open.** Bench RF settings are in `stage0-node/App/radio_cfg.h`: 915.0 MHz, 500 kHz,
   SF7, CR 4/5, 0 dBm. SF and power still have to be tuned for the real placement, and the
   regional configuration, antennas and airtime still need confirming. Do not equate bench
   settings with a qualified regional configuration.
8. **Built and flashed; H01 open.** Binary hashes per release: `stage0-node/RELEASES.md`.
   The H01 checklist (`docs/H01-checklist.md`) has not been run.

## Current measurement preparation

UM2592 documents JP1/I_SoC and separate measurement arrangements involving JP2/I_RF,
JP5/I_SYS and associated bridges. Verify the board revision and manual before changing
jumpers/bridges. USB input power includes debugger/development-board overhead; it is
not a measurement of the final station's pack power. Record supply boundary and
jumper/debugger settings with traces. Normal USB power is appropriate for Stage 0.

References:
- https://github.com/STMicroelectronics/STM32CubeWL
- https://www.st.com/en/evaluation-tools/nucleo-wl55jc.html
- https://www.st.com/resource/en/user_manual/um2592-stm32wl-nucleo64-board-mb1389-stmicroelectronics.pdf
- https://sensirion.com/resource/datasheet/sht4x
- https://www.adafruit.com/product/6174
