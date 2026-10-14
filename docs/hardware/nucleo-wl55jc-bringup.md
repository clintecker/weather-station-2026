# NUCLEO-WL55JC1 bring-up log

Date: 2026-10-12 · Host: macOS (Apple Silicon), Homebrew 7.0.9

Two brand-new NUCLEO-WL55JC1 boards, straight from ST, default jumpers, factory firmware.

## TL;DR

- **Current state (2026-10-13): the boards run the Stage-0 firmware, release `9e3d38f08e8b`** (TX on board A, RX on board B; see [`firmware/stage0-node/RELEASES.md`](../../firmware/stage0-node/RELEASES.md)). During the office range walk they ran the bench tool `firmware/rangetest` instead (see [Office session](#office-session-2026-10-13)). PingPong was the first smoke test (2026-10-12, 915.0 MHz, LoRa SF7 / 500 kHz, 0 dBm; RSSI about −27 dBm, SNR 12 dB at about 30 cm). See [PingPong link test](#pingpong-link-test).
- Factory firmware backups (both boards, byte-identical) are in `docs/hardware/factory-firmware/`.
- Both boards are healthy. STLINK-V3, SWD, NRST, the 3.3 V target supply and the virtual COM port all work.
- **No jumper changes are needed.** The default configuration is correct for USB-powered development (evidence below).
- The factory firmware is ST's **"Concentrator" v1.0** AT-command app. Its console runs at **9600 8N1**, not 115200.
- The factory firmware **switches the SWD pins to analog within milliseconds of boot**. A plain debugger connect fails, so always **connect under reset** (OpenOCD config below).
- A **red** COM LED (LED6, the bicolor STLINK LED) is normal and means idle. It blinks red/green during a debug session. UM2592 says it turns green when communication finishes successfully; here both boards settled on red after OpenOCD sessions (see [LED meanings](#led-meanings-led6-stlink-com)). It is not a fault. Do not confuse it with LED4, which is the red USB overcurrent fault LED.

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

A backup of the factory image is in `docs/hardware/factory-firmware/nucleo-wl55jc-factory-concentrator-v1.0.bin`. It is a full 256 KB (262,144-byte) flash dump, so restoring it overwrites pages 32–127 as well. **That erases the Stage-0 node state (key, counters, journal).** Afterwards the TX board must be provisioned with a **new** key (never reuse a key once its counter has been reset; see `docs/runbook-moving-boards.md`). Restore it with:

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

## LED meanings (LED6, STLINK COM)

UM2592 Rev 4 §6.6.1 names the bicolor STLINK COM LED as LED6. LED4 is the red USB overcurrent fault LED, and LED5 is the green 5V_PWR LED.

| Observed | Meaning |
|---|---|
| Solid red | STLINK enumerated with the PC, no debug session active (idle) |
| Blinking red/green | Debug or programming session talking to the target |
| Solid green | Last target communication succeeded |

Timeline: one board was green after its STLINK had talked to the target at plug-in, and the other was red (idle). After my OpenOCD sessions, both blinked red/green and settled on red. That is expected. (UM2592 says green after a successful communication.)

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
| `vendor/STM32CubeWL` (git-ignored) | STM32CubeWL v1.6.0 (`--depth 1`) with the HAL, CMSIS-device, Nucleo-BSP and SubGHz_Phy submodules. Created and verified by `tools/fetch-vendor.sh`. At the time of this test it lived in `~/code/vendor/STM32CubeWL`; it was later moved (see Stage-0 trial and error, item 6). |
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
- About one round trip every 1.3–1.5 s (see the `BALL_HOLD_MS` row and the 500 kHz smoke test above), no RX timeouts after the link formed, RSSI −26 to −28 dBm, SNR 12–13 dB.
- Which board becomes master depends on the random listen time at boot (`rand=` in the log), so it can swap after a reset.

### Trial and error during the build
1. **`brew install --cask gcc-arm-embedded` failed its checksum check.** The download's SHA-256 (`779972fa…`) didn't match the cask's expected value (`284f16b9…`). I **did not bypass the check**. I used the xPack build of the same GNU Arm toolchain from GitHub releases instead, verified against its published `.sha` (`574082d3…`, `OK`).
2. **Build error: `stm32wlxx_hal.h: No such file`.** STM32CubeWL keeps its drivers in **git submodules**, and a `--depth 1` clone leaves them empty. I fetched only the ones needed: `Drivers/STM32WLxx_HAL_Driver`, `Drivers/CMSIS/Device/ST/STM32WLxx`, `Drivers/BSP/STM32WLxx_Nucleo`.
3. **Build error: `radio.h: No such file`.** `Middlewares/Third_Party/SubGHz_Phy` is also a submodule. Fetching it fixed the build: 33,864 bytes of code, no warnings.
4. **Shell gotcha:** in zsh, `for pair in "A B"; do set -- $pair` doesn't word-split, so the serial and port arrived as one argument. I ran those loops under `bash -c`.

## Next steps (as of the PingPong test, 2026-10-12)

1. ~~Move from PingPong toward real weather-station traffic.~~ **Done 2026-10-12:** raw SubGHz_Phy with our own packet format, see [Stage-0 firmware bring-up](#stage-0-firmware-bring-up-2026-10-12). (Options considered: ST's `LocalNetwork` Concentrator + Sensor demo, raw SubGHz_Phy, LoRaWAN.)
2. Check range with more TX power and real placement. Stay within the FCC Part 15.247 limits for 902–928 MHz. **Started 2026-10-13** with `firmware/rangetest`, see [Office session](#office-session-2026-10-13); placement work remains.
3. Open: investigate the missing MSC drive on board A (step 2 of the log above). This log has no later entry on it.
4. To go back to factory firmware: run the restore command in [Board inventory](#board-inventory). This erases the Stage-0 key, counters and journal.

## Stage-0 firmware bring-up (2026-10-12)

The PingPong smoke test was replaced by [`firmware/stage0-node`](../../firmware/stage0-node/README.md): TX on board A, RX on board B. The host runs `python -m ws0 serve` against the RX port.

### Verified on hardware
- **Sensor wiring checked against UM2592 Rev 4 (Nov 2025), Table 17** (supplied by Clint): CN5.9 = D14 = PA11 = I2C2_SDA, CN5.10 = D15 = PA12 = I2C2_SCL, CN6.4 = 3V3, CN6.6 = GND. No solder bridge in the path. ST's I2C example uses PA15 for SDA; that was that example's own choice and is not the Arduino D14 pin.
- **Board variant checked against data brief DB3933 Rev 1:** NUCLEO-WL55JC1 = high band, 865–928 MHz, so 915.0 MHz is in band.
- **End-to-end link:** TX reading → LoRa → RX → USB hex line → gateway authenticates, commits to SQLite, ACKs → RX → LoRa → TX clears the journal and syncs its clock. Epoch 2 delivered seq 0–12 with `pending=0`; every reading after the first ACK carried synchronized UTC; RSSI −23/−24 dBm, SNR 12–13 dB.
- **Reboot behaviour:** epoch advanced 1 → 2 → 3 and the counter skipped the unused reservation (8 → 257). Backlogged readings from the previous epoch were delivered first-in-first-out, at most two per minute. Provisioning survived reflashing.
- **Crypto:** the TX boot self-test passes on target; the C frame code matches Python on fixed vectors and 200 random frames per direction (`tests/test_frame.py`).

### Trial and error
1. **ACK window closed after 1.3 ms.** The first run showed `sent=9 acked=0 no_ack=9`, and backlog frames were lost while RX was busy sending ACKs. Cause: ST's default `LORA_SYMBOL_TIMEOUT` of 5 symbols, which at SF7/500 kHz (0.256 ms per symbol) ends a single RX window after about 1.3 ms unless a preamble has already started. Fix: symbol timeout 0, so the 2 s window timer bounds RX. After the fix: `sent=3 acked=3 no_ack=0`.
2. **`%lu` printed literally.** ST's `tiny_vsnprintf` is built with `TINY_PRINTF`, which drops the `l` length modifier (widths and zero-padding still work). All console formats now use `%u` with `(unsigned)` casts.
3. **Board A dropped off USB once** while still powered and transmitting: the RX bridge kept hearing its 64-byte PingPong packets. Replugging fixed it. One TX flash failed mid-verify (`jtag status contains invalid mode value`) during the replug; a retry verified OK.
4. **ACK design change during implementation:** draft 2 originally added only host UTC (48-byte ACK). That allows a recorded ACK to be replayed to move the clock, so the ACK now also echoes the observation frame's counter, and the node accepts time only from the reply to the frame it just sent (56-byte ACK).
5. **Mbed TLS choice:** ST's pinned `mbed-crypto` submodule is Mbed TLS **3.6.6 LTS**. It is used for AES-CCM on target and is compiled on the host for the agreement tests. No hand-written AES; the STM32WL hardware AES is not used.
6. **Vendor checkout moved** into `vendor/` (git-ignored). `tools/fetch-vendor.sh` re-creates and verifies every pinned commit.

### Build record
| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` | `37d79f7b05b60ca007b99b533087e931d69c97129aeb5181477d95eaab7d58c4` |
| `build/tx/stage0-tx.bin` | `508677c7811de80975705b23d5bc2368b0d1d2e4cb0c95e57f5faaf71e4c1298` |

Built from working tree `6dd6b54-dirty`; the commit that adds this section is the source of record. Rebuild from that commit and compare the hashes (the embedded version string changes them).

### Protocol draft 3: impossible fillers for invalid readings (2026-10-12)
Clint asked if a 0 filler is wise for a sensor fault, because 0.00 °C is a real Chicago temperature. The decision: the validity flag stays authoritative, and an invalid reading now carries `0x8000` (−327.68 °C) and `0xFFFF` (655.35 % RH). A reader that ignores the flag can no longer see a plausible value. Version byte 2 → 3.

Switch-over order on the live bench:
1. Confirm TX `pending=0`, so no draft-2 plaintext with 0 filler stays in the journal.
2. Flash RX, then TX.
3. Restart the gateway.

As expected, TX's first draft-3 frame reached the old gateway and was rejected (`Unexpected frame header`). It stayed journaled. The next minute delivered it and the live reading, both with `8000ffff` on air and stored as `null`/`sensor_fault`.

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (draft 3) | `1d859a309dde70317cb323a6a31f2cb78d94a76d913dffd9befedc055c15fc1f` |
| `build/tx/stage0-tx.bin` (draft 3) | `4d7f3c7a5fb5ed8f238804820762c5cb87cdeeee8fef02d241b6ecd55b74bdf4` |

### Protocol draft 4: reconstructed time (C) and time across resets (D) (2026-10-12)
Clint approved C and D, and agreed that a reconstructed time counts toward H01 when it meets the 5 s tolerance.

- **Wire:** UTC is u32 seconds plus a u32 **uptime** (seconds since boot, always present). Version byte 4. The gateway keeps the payload immutable and stores `effective_at`, `time_basis` and `time_uncertainty_s` in derived columns. It migrated the existing bench database (draft-2/3 rows) in place.
- **Firmware:** uptime and the 6 h trust window now use RTC seconds (`SysTimeGetMcuTime`), not `HAL_GetTick`. Time trust survives a reset through RTC backup registers DR3/DR4. Finding: ST's `TIMER_IF_Init` zeroes the RTC high tick count at every boot. That only matters after ~48.5 days of uptime, and the trust check rejects it (RTC must count forward).
- **Bench, warm reset (NRST):** `#time restored utc=1791861315 sync_age=11`. Epoch 7 reading 0 was synchronized. Board−host clock difference was −1.0 s (whole-second truncation + serial latency).
- **Bench, simulated power loss** (debugger pulsed `RCC_BDCR.BDRST`, then reset): no restore. Epoch 8 reading 0 was `time=unknown uptime=0`. After reading 1 synced, the gateway reconstructed reading 0 as **03:15:34Z ± 2.009 s**; the board log shows 03:15:35Z.
- **Residual case seen:** epoch 6 ended (my warm-reset test) before its first sync. Its 2 readings stay `unknown`, because there is no reference. This is documented in protocol-stack.md 11.3.2.
- **Switch-over:** same order as draft 3 (`pending=0` → RX → TX → gateway). Again, the first draft-4 frame reached the old gateway, was rejected, and was delivered the next minute.

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (draft 4) | `a919c177d0bc6eb5820f5b9251bf3a00dd14f05a71cce8a11abe0725e109e220` |
| `build/tx/stage0-tx.bin` (draft 4) | `5bb7690fcdbc85288643a5ccd46528cabaeac462a4d642b71c48bf8d96cfebfd` |

### G1 watchdog and G2 NACK on hardware (2026-10-12)
- **G1:** `TEST-HANG` on TX → `#boot … reset=watchdog` after 7.9 s, time trust restored (D), next reading ACKed. On RX → `reset=watchdog` after 7 s. The first boot after the update showed `reset=power` because the old firmware never cleared the reset flags; the new firmware clears them.
- **G2:** I planted a conflicting database row for TX's next identity (epoch 11, seq 1). The gateway authenticated the frame, stored it in `rejections` (112 hex characters), and sent a NACK. TX: `#nack epoch=11 seq=1 reason=1 abandoned=1`, `pending=0`. Cleanup: I deleted the planted row and recovered the genuine reading from `rejections.frame_hex` with `Store.ingest` (returned `True`). The rejection row stays as evidence.

## Office session (2026-10-13)

### Office setup
- Fresh Mac: venv via `uv`, `tools/fetch-vendor.sh` (unlocked the 7 C-vs-Python crypto tests that skip without `vendor/`), `brew install open-ocd` (0.12.0), xPack arm-none-eabi-gcc 15.2.1-1.1 (tarball SHA-256 matched `574082d3…aad870`).
- TX was wiped (`WIPE ERASE-ALL-NODE-STATE`, discarding 18 office-time readings) and provisioned with a fresh office key: KCV `b7142e`, run directory `run-office/`. **The home gateway will now reject TX.** Do **not** re-provision TX with the `run-hw` key: the WIPE reset the transmission counter, and the nonce is built from that counter, so reusing that key would repeat nonces (corrected the same day). Move the gateway or the run directory, or use a new key: `docs/runbook-moving-boards.md`.
- Release `a07f498` rebuilt here from a worktree at that commit: both `.bin` hashes matched `RELEASES.md`. A build from a later commit does not match, because the firmware embeds the commit.

### Range walks
- Walk 1 (weather-station firmware, 1 reading/min, SF7 / 0 dBm, boards hanging loose): `evidence/range-walk-office-2026-10-13/`. A 2-minute dropout lost nothing (journal backfill), but the first backfilled reading arrived after 121.6 s, over the H01 120 s limit.
- Walk 2 (new bench tool `firmware/rangetest`, both directions every ~1 s, button-selected SF and power): `evidence/rangetest-office-2026-10-13/`. SF12 / +22 dBm reached the far side of the building. Noise floor about −100 dBm at both ends. Losses are bursty and start near 0 dB SNR, far above SF12's −20 dB limit; one window showed RSSI up and SNR down together (in-band interference). Hypothesis, not confirmed: bursty 902–928 MHz sources such as UHF RFID.

### Trial and error
- **`firmware/rangetest` v1 settings gap:** a restarted board came back at the defaults while the other kept its settings, so they ran at different power, or could not hear each other at all if the SF differed. Fixed in v2: a restarted board adopts the first settings it hears; about 30 s without contact returns both to the defaults.
- **v2 defaults were the weakest setting (SF7 / 0 dBm).** Walking out of range at SF12 / +22 dropped both boards to the setting with the shortest reach, so they could not reconnect from where the link was lost (Clint's catch). v3: boot and fallback are SF12 / +22 dBm, and the buttons step down. Built and tested on the host, **not yet flashed** (as of 2026-10-13, about 17:00Z). The packet version byte (`RT_VERSION`) is still 1 in v1–v3, so boards running different tool versions interoperate without any warning: flash both boards with the same build.
- **Logger crashes:** a mark went through a code path that assumed settings fields (KeyError); the logger also died on a USB disconnect and logged the wrong board after the port names swapped. Fixed: the logger finds the board by ST-LINK serial number and reconnects.
- **Spontaneous restarts are USB dropouts.** Both boards restarted when their USB port vanished for about 1 s (TX 4 times, RX twice; one episode during handling). `RCC_CSR` after clearing: `PINRSTF` only, no `BORRSTF`, so no power loss. The ST-LINK pulses the target's reset pin when it re-enumerates. Earlier I blamed board A alone; RX did the same. Bench-only (no ST-LINK on the field node), but H01 on USB needs secured cables.
- **My own debugger sessions reset TX twice** (16:22:02 and 16:22:18) while I read and cleared `RCC_CSR` with OpenOCD. A later read-only session did not. Avoid debugger sessions during runs whose restarts are being counted.
- **Close-range readings are unreliable at higher power** (receiver overload with antennas a few cm apart). Compare power only with the boards apart.

### SHT45 parts arrived; wiring plan (2026-10-13)
- Delivered: Adafruit 6174 (SHT45 with PTFE), 4397 (STEMMA QT to female sockets, 150 mm), 1954 (female/male jumpers), 592 (USB A to Micro-B, 3 ft).
- **Connector mismatch found before wiring:** the 4397 ends in female sockets and the Nucleo Arduino headers (CN5, CN6) are female; the 1954 jumpers do not bridge that either. Chose the ST morpho male pins instead: CN10.3 = PA12/SCL, CN10.5 = PA11/SDA, CN10.9 = GND, CN7.16 = 3V3, from UM2592 Rev 4 Table 18 and Figure 24 (Clint supplied the PDF; ST's site timed out for automated downloads). No solder bridges on PA11/PA12. Full table in `docs/protocol-stack.md` §3.1.
- Hazard noted: CN7.18 (5 V) sits directly below CN7.16 (3V3).
- Hardware verification still to do: CRC-checked reading, unplug while running (expect `sensor_fault`, then recovery), then cut a release.
- The spare 592 cable allows the planned USB cable-swap test for the board-reset dropouts.

### Release 0f456040fe54 (2026-10-13 evening)
- Built twice from a clean tree (identical `.bin` hashes) and flashed RX, then TX. The flash kept TX's node state: `kcv=b7142e`, counter 7427, `kat=pass`.
- Trial and error: `make clean` removes both roles' builds, so the release loop must clean once and then build both roles; cleaning per role deleted the other role's binary.
- First minute on the bench: `#sample … valid=0 rc=-2` (no sensor wired: address NACK with the new internal pull-ups), both pending readings ACKed, gateway 2 accepted / 0 rejected.
- Not yet exercised on hardware: the new WIPE (keeps counter and epoch), the probing-every-minute path, health reports while probing, and bus recovery with a real stuck sensor.

### SHT45 first light and anomaly review (2026-10-14)
- Wired on the morpho pins (CN10.3/5/9, CN7.16) with TX unplugged. First sample after power-up: `valid=1 rc=0 t=2611 rh=4733` (26.11 °C, 47.33 %), `sensor_faults=0`.
- The RX board had been unplugged since 2026-10-13 21:42:57Z (`serial-lost`), so the first three TX samples got no ACK. They stayed in the TX journal (`pending` rose, `lost=0`). When the RX came back (15:18:22Z) all of session 34, seq 0–9, was stored with no gaps. Seq 0–3 were sampled before the TX had time from an ACK, so the gateway reconstructed their timestamps (about ±2 s); seq 4 onward is `synchronized`.
- **Gateway bug: the serve log showed the wrong reading.** After each ACK it printed the newest stored observation, so the backlog burst (live seq 4, then seq 0–2) logged "seq 4" four times. It now prints the observation in the frame just ACKed (key `observation`, with `duplicate`).
- **Gateway bug: the host clock check timed the DNS lookup.** `sendto()` resolved `pool.ntp.org` after the start timestamp, so lookup time read as offset = rtt/2: +0.554 s (rtt 1.104 s) on 10-13 17:01Z, and +1.114 s (rtt 2.099 s) at 20:44Z, which wrongly marked the clock `bad` for an hour (ACKs carried no time). Fixed: resolve first; call a clock bad only when it is wrong by more than 1 s even at the edge of the rtt/2 uncertainty; retry after 5 min when a check fails or cannot decide. The two hourly `TimeoutError`s overnight were single lost UDP queries; they now retry sooner.
- **Gateway bug: traceback on a second stop signal.** A repeated SIGTERM during shutdown raised inside `server.shutdown()` (seen in `serve.log` on 10-13). Only the first SIGINT, SIGTERM or SIGBREAK now interrupts.
- **Not bugs:** `node_diagnostics.journal_pending=3` in `/v1/status` for several minutes after the backlog drained. The TX sends its health report every 15 min (`DIAG_PERIOD_S`), and the one at 15:18:50Z correctly counted seq 0–2 as pending; check `received_at` for its age. The `#sample` line truncated at `utc=…` in a console read was stale bytes the ST-LINK buffered while no program had the TX port open, not a firmware fault.
- **RX `uart_errors=1`** (first time nonzero): it appeared within the first minute after the RX was plugged in. Restarting the gateway, which closes and reopens the port, did not increase it (still 1 at 15:31:09Z), so the port opening is not the cause. Most likely a line glitch while the ST-LINK and target powered up. The error handler re-armed the receiver (ACKs kept flowing: 16 of 16 delivered). Watch whether it rises during H01; an unchanged 1 is harmless.

### Release bc5e6ede429c (protocol draft 5) on the bench (2026-10-14)
- TX wiped by Clint (`pending=0` checked first; counter kept, 8622 → 8705), both boards flashed at 17:58Z, fresh run directory `run-d5`, new key `kcv=5618eb`. Boot self-test `kat=pass` on hardware.
- On air: 42 B observations, 33 B ACKs. The reading taken before the gateway started arrived from the backlog.
- **Sensor unplug test:** SHT45 STEMMA cable unplugged about 18:01:30Z, replugged about 18:13Z. Readings seq 4–14 (11 minutes) arrived as `temperature_c`/`humidity_pct` null with `quality=sensor_fault`, each ACKed, frames still 42 B (a fault does not change the length). Epoch stayed 35: no reboot. seq 15 was valid again (29.13 °C: probably warmed by handling). TX `sensor_faults=11`, `pending=0`, `lost=0`; no sequence gaps, including across a gateway restart at 18:12Z (dashboard deployed).
