# NUCLEO-WL55JC1 bring-up log

Date: 2026-10-12 · Host: macOS (Apple Silicon), Homebrew 7.0.9

Two brand-new NUCLEO-WL55JC1 boards, straight from ST, default jumpers, factory firmware.

## TL;DR

- **Current state: both boards run SubGHz_Phy_PingPong (915.0 MHz, LoRa SF7 / **500 kHz** per the RF decision below, 0 dBm, blue LED shows who holds the ball) and are exchanging packets.** RSSI is about −27 dBm and SNR 12 dB with stub antennas about 30 cm apart. See [PingPong link test](#pingpong-link-test).
- Factory firmware backups (both boards, byte-identical) are in `docs/hardware/factory-firmware/`.
- Both boards are healthy. STLINK-V3, SWD, NRST, the 3.3 V target supply and the virtual COM port all work.
- **No jumper changes are needed.** The default configuration is correct for USB-powered development (evidence below).
- The factory firmware is ST's **"Concentrator" v1.0** AT-command app. Its console runs at **9600 8N1**, not 115200.
- The factory firmware **switches the SWD pins to analog within milliseconds of boot**. A plain debugger connect fails, so always **connect under reset** (OpenOCD config below).
- A **red** COM LED (LD4) is normal and means idle. It turns green after a successful debug session and blinks red/green during one. It is not a fault.

## Board inventory

Identify boards by **STLINK serial number**, never by `/dev/cu.usbmodem*` name. The port name comes from the USB location ID and changes when a cable moves to another port (observed: `usbmodem122303` belonged to board A, then to board B after a cable swap).

| Label | Stage-0 role | STLINK serial | MCU UID (96-bit) | Port at time of writing |
|---|---|---|---|---|
| A | **TX** (sensor node) | `003B00194142500E20353451` | `003a0011 4c42500d 20363552` | `/dev/cu.usbmodem1122303` |
| B | **RX** (indoor USB receiver) | `0016001E4142500E20353451` | `000b0016 4c42500d 20363552` | `/dev/cu.usbmodem122303` |

Roles assigned 2026-10-12. Physically label the boards TX and RX.

Both boards:

| Item | Value |
|---|---|
| STLINK | V3J7M3, USB `0483:374e` |
| Target voltage | 3.276–3.290 V |
| MCU | STM32WL55JC, DBGMCU_IDCODE `0x10036497` (dev `0x497`, rev `0x1003`) |
| Flash | 256 KB, 128 × 2 KB pages, no write protection |
| FLASH_OPTR | `0x3FFFF0AA` → RDP Level 0 (unprotected) |
| Firmware | identical on both, SHA-256 `d6365d91…5cf5f8c`, 57,836 bytes used |

A backup of the factory image is in `docs/hardware/factory-firmware/nucleo-wl55jc-factory-concentrator-v1.0.bin`. Restore it with:

```sh
openocd -f interface/stlink.cfg -c "adapter serial <SERIAL>" -f target/stm32wlx.cfg \
  -c "reset_config srst_only srst_nogate connect_assert_srst" \
  -c "program docs/hardware/factory-firmware/nucleo-wl55jc-factory-concentrator-v1.0.bin 0x08000000 verify reset exit"
```

## Tools installed

| Tool | How | Version | Verdict |
|---|---|---|---|
| stlink (`st-info`, `st-flash`) | `brew install stlink` | v1.9.0 | Lists probes and target voltage. **Cannot attach** to the factory firmware (no connect-under-reset in `st-info --probe`). |
| OpenOCD | `brew install open-ocd` | 0.12.0 | **Works** with `connect_assert_srst`. Main tool. |
| pyOCD | `uv tool install pyocd` | 0.45.1 | Lists both boards as NUCLEO-WL55JC. Needs `pyocd pack install stm32wl55jcix` before it can attach (not done yet). |

STM32CubeProgrammer was not installed (it needs an ST account download). Nothing so far has required it.

## Working OpenOCD invocation

```sh
openocd -f interface/stlink.cfg -c "adapter serial <SERIAL>" -f target/stm32wlx.cfg \
  -c "reset_config srst_only srst_nogate connect_assert_srst" \
  -c "init" -c "reset halt" ...
```

`connect_assert_srst` holds NRST low while the debugger attaches, so the core is caught before the firmware disables SWD. OpenOCD reports "Unable to match requested speed 500 kHz, using 200 kHz". That is harmless.

## Trial-and-error log

Steps in order, including the dead ends.

### 1. "Can you see the boards?" — no ST device at all
- `system_profiler SPUSBDataType` / `ioreg -p IOUSB`: no vendor `0x0483`. No `NOD_WL55JC` volume.
- The only USB serial port was `/dev/cu.usbmodem21201`, which is a **WCH CH34x adapter (`1a86:fe0c`), not a Nucleo**. Don't mistake it for one.
- **Cause:** cables or ports. Swapping cables made board A appear, then board B. One of the original cables appears to be charge-only. Mark it or throw it away.

### 2. Only one `NOD_WL55JC` mass-storage drive
- With both boards attached, only board B's STLINK exposed a mounted MSC volume (`disk8`). Board A had shown its drive earlier, when it was the only board plugged in through a different hub.
- This doesn't affect SWD or the VCP. It's only needed for drag-and-drop flashing. **Open item:** replug board A directly into the Mac and check whether its drive returns.

### 3. `st-info --probe` → `ENTER_SWD error (0x09)` on both boards
- The probes, firmware V3J7 and target voltage were all fine, but chip ID read as `0x000`.
- At this point I suspected cabling or jumpers on one board. The fact that it failed on **both** boards pointed to a shared cause, the firmware.

### 4. OpenOCD plain `init` → `init mode failed (unable to connect to the target)` on both
- Same symptom, different tool, so it was not a stlink-tool bug.

### 5. OpenOCD with `connect_assert_srst` → **success** on both
- Both halt at the reset handler `pc=0x0800014c`, `msp=0x20000aa0`.
- Read IDCODE, flash size, UID, OPTR and flash SR. See the inventory table.
- Gotcha: OpenOCD stops processing all remaining `-c` commands after the first error, without saying which one failed. Wrap commands in a Tcl `catch` (see `tools/nucleo/trace-swd-disable.tcl`).

### 6. Dumped and hashed both flash images
- Byte-identical SHA-256 on both boards, so this is the same factory image. Strings show an AT-command app titled "Concentrator" with LoRa/FSK, region, subregion and beacon commands.

### 7. Serial console at 115200 → silence
- Opened both VCPs at 115200, sent `AT`, `AT+VER`, `AT?`: no bytes back.
- Opened the port, then reset the MCU via NRST to catch a boot banner: still nothing.

### 8. Tried to find why: halting the running firmware
- `DBGMCU_CR = 0x7` (keep debug alive in Sleep/Stop/Standby), then resume and halt after 3 s → `jtag status contains invalid mode value - communication failure`. Debug was lost even with the low-power debug bits set.
- Halting after 5 / 100 / 1000 ms also failed. Debug is gone within 5 ms of reset release.
- **Watchpoint on `GPIOA_MODER` (0x48000000) writes**, run with `tools/nucleo/trace-swd-disable.tcl`:
  - Hit 0 (`pc=0x08002f58`): MODER initialised to reset value `0xABFFFFFF`.
  - Hit 13: `0xABFFFFFF → 0xEBFFFFFF` (PA15 → analog).
  - Hit 14: link lost. The next pins configured were PA14/PA13 (SWCLK/SWDIO) set to analog.
  - No USART1/USART2/LPUART1 was enabled at that point.
- **Conclusion:** the firmware sets every unused GPIO to analog, including the SWD pins, for low power. This is the STM32CubeWL `DEBUGGER_ENABLED=0` pattern. It's normal factory behaviour, not a fault.

### 9. Baud-rate sweep → **9600 baud works**
- Swept 9600 / 19200 / 38400 / 57600 / 115200 / 230400 while resetting via NRST.
- At 9600 the board printed:
  ```
  --------------------------
      Concentrator Reset
       v1:0
  --------------------------
  ```
- Other rates gave framing garbage (19200–57600) or nothing.

### 10. AT console works on both boards
- Syntax: `AT+<CMD>=?` gets a value and `AT+<CMD>?` shows help. So `AT+VER` → `AT_ERROR`, but `AT+VER=?` → `v1:0`.
- Both boards returned the full help listing and `v1:0`.
- **No transmit commands were sent** (`AT+BEACON_ON`, `AT+MOD_TEST_*`). Attach an antenna before keying the radio.

## LED meanings (LD4, STLINK COM)

| Observed | Meaning |
|---|---|
| Solid red | STLINK enumerated with the PC, no debug session active (idle) |
| Blinking red/green | Debug or programming session talking to the target |
| Solid green | Last target communication succeeded |

Timeline: one board was green after its STLINK had talked to the target at plug-in, and the other was red (idle). After my OpenOCD sessions, both blinked red/green and settled on red. That is expected.

## Jumpers

Left at factory default. Evidence that the defaults are correct:
- STLINK measures 3.28 V on the target, so the board takes power from STLINK USB and the IDD measurement jumper is fitted.
- SWD and NRST connect-under-reset work, so the STLINK-to-MCU debug and reset links are connected.
- The VCP carries the MCU's UART, so the STLINK-to-MCU UART links are connected.

Change jumpers only for a specific reason, such as measuring MCU current on the IDD header or powering from an external supply. Check ST user manual UM2592 for the exact jumper before moving anything.

## Helpers

- `tools/nucleo/at.py` sends AT commands at 9600 baud: `python3 tools/nucleo/at.py /dev/cu.usbmodemXXXX "AT+VER=?"`
- `tools/nucleo/trace-swd-disable.tcl` is the OpenOCD watchpoint script from step 8.
- List probes: `st-info --probe` or `pyocd list`.

## PingPong link test

### What and why
Goal: make the two boards talk to each other. The factory Concentrator firmware can't do this by itself, because it expects the `LocalNetwork` Sensor firmware on the other node. I used ST's canonical two-node test instead, `Projects/NUCLEO-WL55JC/Applications/SubGHz_Phy/SubGHz_Phy_PingPong` from STM32CubeWL **v1.6.0**. The same firmware goes on both boards. Each listens for a random time, and whichever times out first becomes master and sends `PING`. The other becomes slave and answers `PONG`.

### Where things live
| Path | What |
|---|---|
| `firmware/pingpong/` | Copy of ST's app sources plus our `Makefile`. The vendor tree is not modified. |
| `~/code/vendor/STM32CubeWL` | STM32CubeWL v1.6.0 (`--depth 1`) with the HAL, CMSIS-device, Nucleo-BSP and SubGHz_Phy submodules |
| `~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1` | Arm GCC 15.2.1 (xPack) |

Build and flash:
```sh
cd firmware/pingpong
make -j8
make flash SERIAL=003B00194142500E20353451   # board A
make flash SERIAL=0016001E4142500E20353451   # board B
```

### Changes from ST's example (all marked `weather-station-2026` in source)
| Setting | ST default | Ours | Why |
|---|---|---|---|
| `RF_FREQUENCY` | 868 MHz (EU) | **915 MHz** | US location (America/Chicago). 868 MHz is not a US ISM band. |
| `TX_OUTPUT_POWER` | 14 dBm | **0 dBm** | Desk test. The boards are about 30 cm apart, so more power isn't needed and it's gentler on the PA. |
| `DEBUGGER_ENABLED` | 0 | **1** | Keeps SWD alive, so OpenOCD can attach without connect-under-reset (verified: plain `halt` worked). |
| LEDs | Master toggles red, slave toggles green, on every packet | **Blue LD1 = "I have the ball"** (`CatchBall()` on RX, off at `OnTxDone`). Red and green still blink together while searching for a partner. | Lets you watch the rally. |
| `BALL_HOLD_MS` | n/a | **400 ms** extra hold before returning the ball | Slows the rally to about 1.46 s per round trip, with each blue LED on for about 0.7 s, alternating. Keep well under `RX_TIMEOUT_VALUE` (3000 ms). |

| `LORA_BANDWIDTH` | 0 (125 kHz) | **2 (500 kHz)** | US regulatory class, see [RF configuration decision](#rf-configuration-decision). |

The rest is ST's default: LoRa, SF7, CR 4/5, 8-symbol preamble, 64-byte payload.

### RF configuration decision
Decided 2026-10-12, approved by Clint: **LoRa, 500 kHz bandwidth, 915.0 MHz, under FCC §15.247(a)(2) (digital modulation, 6 dB bandwidth ≥ 500 kHz).**

| Rule | 902–928 MHz allowance | Fixed-channel 125 kHz LoRa at 0 dBm |
|---|---|---|
| §15.249 | ≤ 50 mV/m at 3 m ≈ −1.25 dBm EIRP | About −1 to +2 dBm EIRP with an unknown 0–2 dBi antenna. **Probably over by up to 3 dB.** The first PingPong runs (125 kHz) used this; they were desk-only and lasted minutes. |
| §15.247(a)(1) hopping | ≥ 50 channels if 20 dB bandwidth < 250 kHz | Not applicable (one channel) |
| §15.247(a)(2) digital modulation | 6 dB bandwidth ≥ 500 kHz; ≤ +30 dBm conducted (≤ 6 dBi); PSD ≤ 8 dBm/3 kHz | **500 kHz LoRa fits this class.** At 0 dBm the PSD is about −22 dBm/3 kHz. |

Not yet verified: the measured 6 dB bandwidth of these boards' 500 kHz LoRa signal (needs a spectrum analyzer) and the gain of the supplied antenna. This is an engineering reading of Part 15, not a compliance certification. The trade-off is about 6 dB less receive sensitivity than 125 kHz; recover it with SF and/or power during H01 placement link-budget work.

Smoke test at 500 kHz: rally re-formed immediately, RSSI −26 to −28 dBm, SNR 12–13 dB, no timeouts, about 1.28 s per round trip.

### Pinned build inputs (smoke test)
| Input | Version |
|---|---|
| STM32CubeWL | `v1.6.0` @ `f934cd298bf82d45f96aac2f335c0bbd26d0b946` |
| ↳ STM32WLxx_HAL_Driver | `v1.6.0` @ `5c87cf00992c6e4ecf56c7c129b8dcfc6aa6f88e` |
| ↳ CMSIS Device STM32WLxx | `v1.4.0` @ `71a0b7860e700f7ca11afe4c4afd6cef684ad9bb` |
| ↳ BSP STM32WLxx_Nucleo | `v1.3.1` @ `90cb4924568890bce20cf5ed701f67486619cd6f` |
| ↳ SubGHz_Phy middleware | `v1.5.0` @ `7dc059f353f359ec65c60a0549d53c1ebeaafa79` |
| Toolchain | xPack arm-none-eabi-gcc `15.2.1-1.1` (tarball SHA-256 `574082d3…aad870`) |
| Programmer | OpenOCD 0.12.0 (Homebrew `open-ocd`) |
| Host | MacBookPro18,4 (M1 Max), macOS 26.7.1, Apple clang 17.0.0, Python 3.12.7, Node 22.22.2 |
| `build/pingpong.bin` (500 kHz, blue-LED build) | SHA-256 `baed948b7377ab6f01eb14a1841328c0c2cbcb96d36416fab45452ef8af7151f`, flashed to A and B |

This is a diagnostic smoke test only. It is **not H01** and not the Stage-0 protocol. The console is **115200 8N1**. That differs from the factory firmware's 9600.

### Result (captured 20 s after resetting both)
- Board A (`003B…`) won the election and became **master** (`Master Tx start` → `OnRxDone` → `...PING`).
- Board B (`0016…`) became **slave** (`...PONG`, `Slave Tx start`).
- About 1.5 round trips per second, no RX timeouts after the link formed, RSSI −26 to −28 dBm, SNR 12–13 dB.
- Which board becomes master depends on the random listen time at boot (`rand=` in the log), so it can swap after a reset.

### Trial and error during the build
1. **`brew install --cask gcc-arm-embedded` failed its checksum check.** The download's SHA-256 (`779972fa…`) didn't match the cask's expected value (`284f16b9…`). I **did not bypass the check**. I used the xPack build of the same GNU Arm toolchain from GitHub releases instead, verified against its published `.sha` (`574082d3…`, `OK`).
2. **Build error: `stm32wlxx_hal.h: No such file`.** STM32CubeWL keeps its drivers in **git submodules**, and a `--depth 1` clone leaves them empty. I fetched only the ones needed: `Drivers/STM32WLxx_HAL_Driver`, `Drivers/CMSIS/Device/ST/STM32WLxx`, `Drivers/BSP/STM32WLxx_Nucleo`.
3. **Build error: `radio.h: No such file`.** `Middlewares/Third_Party/SubGHz_Phy` is also a submodule. Fetching it fixed the build: 33,864 bytes of code, no warnings.
4. **Shell gotcha:** in zsh, `for pair in "A B"; do set -- $pair` doesn't word-split, so the serial and port arrived as one argument. I ran those loops under `bash -c`.

## Next steps

1. Move from PingPong toward real weather-station traffic. Options are ST's `LocalNetwork` Concentrator + Sensor demo (the factory image is the Concentrator half), raw SubGHz_Phy with our own packet format, or LoRaWAN.
2. Check range with more TX power and real placement. Stay within the FCC Part 15.247 limits for 902–928 MHz.
3. Investigate the missing MSC drive on board A (step 2 of the log above).
4. To go back to factory firmware: run the restore command in [Board inventory](#board-inventory).
