# Context pack: resume Stage 0 on a new machine

Written 2026-10-13 for picking the work up at the office with the two boards. Hand this file to a fresh Claude Code session first. The deeper docs are linked at the end.

## 1. What this project is
A home weather station. The sensor node is a NUCLEO-WL55JC1 (STM32WL, LoRa) that sends one temperature/RH reading a minute over encrypted LoRa to a USB receiver board. A Python gateway (`ws0`) stores the readings in SQLite and later feeds Home Assistant over MQTT.

The eventual node runs **unattended on battery and solar, at long range**. Judge every decision for that node, not for the USB bench. The node should fail cheaply, and work should be pushed to the mains-powered gateway.

**Plan of record:** strict stage order. Stage 0 means passing **H01**: 24 h, 1,440 intervals, at least 1,426 valid readings committed within 120 s, plus a restart/outage matrix (`docs/H01-checklist.md`). Stage 1 (solar, batteries, RS-485, heaters) does not start before H01 passes.

## 2. Where things stand (on `master`)
- **Firmware release `9e3d38f08e8b`** is on both boards (`firmware/stage0-node/RELEASES.md`; flashed 2026-10-13, office key `b7142e` kept). Check `STATUS` on each board before relying on it. **No rebuild is needed** to resume.
  - TX = board A, ST-LINK serial `003B00194142500E20353451`
  - RX = board B, ST-LINK serial `0016001E4142500E20353451`
  - Identify boards by serial number. Port names change between machines.
- **Protocol draft 4.** Every frame is 56 bytes with AES-128-CCM: observation, ACK carrying host time, NACK, and a health report every 15 min. Spec: `docs/protocol.md`.
- **Radio:** 915.0 MHz, 500 kHz bandwidth, SF7, CR 4/5, 0 dBm (bench).
- **Bench-verified:**
  - journal (3.3 days of outage buffer in internal flash)
  - durable counters, watchdog
  - reset-during-write test (G7 part A, 70 cycles)
  - outage recovery (G13), NACK, gateway auto-reconnect
  - host clock check, RX liveness
  - MQTT against a local broker (currently **disabled**)
  - H01 scorer `tools/h01_report.py`
- **Latest evidence:** `evidence/soak-a07f498-2026-10-13/`. Over 9 h, 549 of 549 minutes arrived on time, median latency 1.5 s, 0 lost, 0 missed ACKs.
- **Tests:** `.venv/bin/python -m unittest discover -s tests` should give 83 passing (needs network for one SNTP test). Run `tools/fetch-vendor.sh` first: without `vendor/`, 7 C-vs-Python crypto tests are skipped, not run.

## 3. Important: the radio key did NOT come with you
- The TX board is provisioned with a key that lives only in `run-hw/` on the home Mac. That folder is git-ignored and must never be committed.
- The home gateway's launchd agent is still running and waiting for the boards. When they come home, it will reconnect on its own, as long as TX still has the home key.

**For the office, use a fresh key (recommended):**
1. On the TX console, send `WIPE ERASE-ALL-NODE-STATE`. This erases the key, counters and journal.
2. `init` a new run directory, then `provision-node`.

A new key is always safe. Reusing a key is safe only if the board's counter has never gone back since that key was first used (see `docs/runbook-moving-boards.md`).

**Consequence:** once TX is re-provisioned at the office, the **home** gateway will reject its frames as unauthenticated. When the boards go home, use one of these (details: `docs/runbook-moving-boards.md`):
- run the gateway on the machine that holds `run-office/` (for example, take that laptop home), or
- copy `run-office/` to the home Mac by a private route (never git, chat or email) and point the gateway at it, or
- create a **new** key: `init` a new run directory, `WIPE` TX, `provision-node`.

**Never re-provision TX with `run-hw`'s existing key after a WIPE.** (Corrected 2026-10-13; an earlier version of this pack suggested it.) The AES-CCM nonce is kind + station + the 64-bit transmission counter (`firmware/common/ws_frame.c:15`, `docs/protocol.md`), and on firmware before release `0f456040fe54` WIPE reset that counter to 1 (the morning office wipe did). From `0f456040fe54` on, WIPE keeps the counter (gap G17), but this board's counter is now far below what the home key already used, so the home key stays retired for this board. The `PROVISION` epoch floor raises only the epoch, the observation identity (`App/node_store.c`, `store_epoch_floor`), not the counter. TX had already transmitted with the home key (for example the 9 h soak, `evidence/soak-a07f498-2026-10-13/`), so reuse would repeat nonces already sent on air.

## 4. Office setup (fast path: run the bench, no firmware build)
```sh
git clone https://github.com/clintecker/weather-station-2026 && cd weather-station-2026
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # or: uv venv && uv pip install -r requirements.txt
sh tools/fetch-vendor.sh                                                  # needed for 7 of the tests
WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests   # expect 83 OK, none skipped (needs network for one SNTP test)

# Plug both boards in, then find their ports. Each board is one /dev/cu.usbmodem*.
# This lists each port with its ST-LINK serial (SER=...):
.venv/bin/python -m serial.tools.list_ports -v

# Wipe and re-provision TX with a new key (115200 8N1 console):
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodem<TX> 115200
#   type: WIPE ERASE-ALL-NODE-STATE   (TX reboots with solid red LED3 = unprovisioned). Ctrl-] to quit.
.venv/bin/python -m ws0 init --hardware --station station-01 --station-id 1 --directory run-office
.venv/bin/python -m ws0 provision-node --directory run-office --serial /dev/cu.usbmodem<TX>
.venv/bin/python -m ws0 serve --directory run-office --serial-number 0016001E4142500E20353451
# API: http://127.0.0.1:8088/v1/status. One reading a minute; blue LED flash, then green = ACKed.
```
- `run-office/` matches the `run*/` ignore rule, so it can't be committed by accident.
- For a long run, install the launchd agent: `tools/deploy/macos/install.sh install run-office 0016001E4142500E20353451`.
- Keep the Mac awake (`caffeinate -dimsu`).

## 5. Full setup (only if you need to change or rebuild firmware)
- **Homebrew:** `brew install stlink open-ocd`. `uhubctl` and `mosquitto` are optional.
- **Toolchain:** the xPack arm-none-eabi-gcc **15.2.1-1.1** must sit at `~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/`. To use another install, override the Makefile's `TOOLCHAIN` variable with that install's `bin` directory: `TOOLCHAIN=<root>/bin`.
  - Download: https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/tag/v15.2.1-1.1, asset `xpack-arm-none-eabi-gcc-15.2.1-1.1-darwin-arm64.tar.gz`.
  - Expected SHA-256 (from the home machine): `574082d35e49a2bcbdc355836b2a3ae5e5bb3b9456c9f5e37177db2ab4aad870`.
  - Do not use the Homebrew `gcc-arm-embedded` cask: its checksum failed here, and that was deliberately not bypassed.
- **Vendor code:** `tools/fetch-vendor.sh` fetches pinned STM32CubeWL v1.6.0 plus its submodules into `vendor/` (git-ignored). Mbed TLS 3.6.6 comes in as ST's `mbed-crypto` submodule of STM32CubeWL, not as a separate download.
- **Build and flash:**
  - `cd firmware/stage0-node && make ROLE=rx flash SERIAL=0016001E4142500E20353451`, then the same with `ROLE=tx` and the TX serial.
  - Flashing keeps provisioning and the journal.
  - A release must be recorded in `firmware/stage0-node/RELEASES.md`. H01 evidence must name a release.

## 6. Next steps, in order
1. **Re-establish the link at the office.** Steps above. Confirm green ACK LEDs and `/v1/status`. *Done 2026-10-13: office key KCV `b7142e` in `run-office/` (see `docs/hardware/nucleo-wl55jc-bringup.md`, "Office session").*
2. **SHT45 (Adafruit 6174), delivered 2026-10-13** with a 4397 STEMMA QT-to-female-socket cable, 1954 female/male jumpers and a spare Micro-B cable.
   - Wiring (Arduino headers): SDA → CN5.9 (D14/PA11), SCL → CN5.10 (D15/PA12), 3V3 → CN6.4, GND → CN6.6. Bus is I2C2 at 100 kHz.
   - **The 4397's female sockets do not fit the female Arduino headers.** No-solder route: plug them onto the male ST morpho pins: yellow SCL → CN10.3, blue SDA → CN10.5, black GND → CN10.9, red 3V3 → CN7.16 (not CN7.18 = 5 V). Positions and source: `docs/protocol-stack.md` §3.1. Alternative: solder the breakout's header strip and use the 1954 jumpers on CN5/CN6. Wire with TX unplugged.
   - Firmware sensor driver: **already written** (`firmware/stage0-node/App/sensor.c`: I2C2, stuck-bus recovery; CRC and fault handling unit-tested) and in release a07f498. Untested on hardware: wire it, then verify.
   - Verify a CRC-checked reading, plus the unplug and fault behaviour. Then cut a new release.
3. **Home Assistant.** Steps ready in `docs/runbook-home-assistant.md`; needs Clint's broker host, port, TLS on/off and user name (the password goes in a private file, not chat). H01 requires an HA entity.
4. **Placement.** Check the link in both directions at the real TX/RX locations, then tune SF and power.
5. **H01:** the 24 h run plus the restart/outage matrix, scored with `tools/h01_report.py --db run-office/observations.sqlite3 --station station-01 --start <UTC> --hours 24 --output evidence/h01-<date>` (use the run directory the gateway actually served; `--db` defaults to `run-hw/`).

**Tonight's SHT45 test plan:** `docs/firmware-review-2026-10-13.md` §2.

**Deliberately open:**
- G10: flash read-out protection (field use).
- G14: brown-out reset level (Stage 1).
- H11: 30-day buffer, which needs SPI NOR.
- G16: timed ACK slot.
- G18: code space for the final station (`docs/firmware-budget.md`): keep the STM32WL55JC, plan flash layout v2 with H11, final image ≤ 75 % of its region. Keep an eye on the flash guard in every build.
- **G7 part B** (true USB power-cut testing) is **deferred by Clint**. Don't raise it.

**Bench note (2026-10-13):** a USB dropout of about 1 s makes the ST-LINK reset its board (both boards seen). For H01 on USB, secure the cables and keep hands and debugger sessions off them. Range-test tool and findings: `firmware/rangetest/README.md`, `evidence/rangetest-office-2026-10-13/`.

**Minor:** the simulator still models a 2-per-minute backlog drain, while the firmware drains 5 per minute.

## 7. Working rules (from Clint)
- Do routine authorized work autonomously, and ask only for decisions that are Clint's. Explain electronics plainly: he's a strong software developer who is new to embedded.
- Never loosen a test criterion. Never claim H01 from a smoke test or simulation.
- No purchases, emails, sharing, or destructive resets without his OK. Re-setting up at the office was Clint's call (2026-10-13).
- Never commit keys, tokens or run databases.
- Document trials and errors (`docs/hardware/nucleo-wl55jc-bringup.md`).
- Keep bench tests short: minutes, not hours, unless it's H01 itself.
- **Bench quirks:**
  - The factory ST firmware disables SWD, so connect-under-reset is needed. Ours keeps SWD enabled.
  - Generic USB hubs that claim per-port power switching don't actually cut VBUS.

## 8. Map of the docs
| File | What |
|---|---|
| `docs/protocol.md` | Wire format, draft 4 |
| `docs/protocol-stack.md` | Layered explanation with diagrams |
| `docs/failure-modes.md` | FMEA, loss budget, runbook R1–R8, gaps G1–G16 |
| `docs/radio-energy-policy.md` | Approved send and back-off policy for battery/solar |
| `docs/H01-checklist.md` | The gate |
| `docs/hardware/nucleo-wl55jc-bringup.md` | Board bring-up trial-and-error log |
| `firmware/stage0-node/README.md` | Build, console commands, LEDs, flash layout |
| `firmware/stage0-node/RELEASES.md` | Release hashes |
| `docs/firmware-review-2026-10-13.md` | Firmware review roadmap (§2: SHT45 test plan) |
| `docs/firmware-budget.md` | Flash/RAM/radio budget, measured; layout v2 and payload plan |
| `docs/runbook-home-assistant.md` | MQTT / Home Assistant setup, password file, running the gateway on macOS, Linux, Windows |
| `docs/runbook-moving-boards.md` | Moving boards between gateways without key or nonce reuse |
| `docs/simulation-harness.md` | Simulation harness model and limits |
| `docs/openapi.json` | Gateway HTTP API |
| `firmware/rangetest/README.md` | Range-test bench tool |
| `hardware/chicago-test-hardware-r0/` | Chicago test hardware R0: build/order guide and manufacturing files |
| `tools/README.md` | Every tool in `tools/` |
| `evidence/` | Every bench run, dated |
