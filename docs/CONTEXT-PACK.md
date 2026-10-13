# Context pack: resume Stage 0 on a new machine

Written 2026-10-13 for picking the work up at the office with the two boards. Hand this file to a fresh Claude Code session first. The deeper docs are linked at the end.

## 1. What this project is
A home weather station. The sensor node is a NUCLEO-WL55JC1 (STM32WL, LoRa) that sends one temperature/RH reading a minute over encrypted LoRa to a USB receiver board. A Python gateway (`ws0`) stores the readings in SQLite and later feeds Home Assistant over MQTT.

The eventual node runs **unattended on battery and solar, at long range**. Judge every decision for that node, not for the USB bench. The node should fail cheaply, and work should be pushed to the mains-powered gateway.

**Plan of record:** strict stage order. Stage 0 means passing **H01**: 24 h, 1,440 intervals, at least 1,426 valid readings committed within 120 s, plus a restart/outage matrix (`docs/H01-checklist.md`). Stage 1 (solar, batteries, RS-485, heaters) does not start before H01 passes.

## 2. Where things stand (commit on `master`, pushed)
- **Firmware release `a07f498273f7`** is already flashed on both boards. **No rebuild is needed** to resume.
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
- **Tests:** `.venv/bin/python -m unittest discover -s tests` should give 61/61 passing.

## 3. Important: the radio key did NOT come with you
- The TX board is provisioned with a key that lives only in `run-hw/` on the home Mac. That folder is git-ignored and must never be committed.
- The home gateway's launchd agent is still running and waiting for the boards. When they come home, it will reconnect on its own, as long as TX still has the home key.

**For the office, use a fresh key (recommended):**
1. On the TX console, send `WIPE ERASE-ALL-NODE-STATE`. This erases the key, counters and journal.
2. `init` a new run directory, then `provision-node`.

A new key with reset counters is safe. Reusing an old key with reset counters is not.

**Consequence:** once TX is re-provisioned at the office, the **home** gateway will reject its frames as unauthenticated. When the boards go home, either:
- re-provision TX again against `run-hw`'s key with the next epoch floor, or
- copy the office run directory home by a private route (never git, chat or email).

## 4. Office setup (fast path: run the bench, no firmware build)
```sh
git clone https://github.com/clintecker/weather-station-2026 && cd weather-station-2026
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # or: uv venv && uv pip install -r requirements.txt
WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests   # expect 61 OK

# Plug both boards in, then find their ports. Each board is one /dev/cu.usbmodem*.
ls /dev/cu.usbmodem*
# Map port to serial: `ioreg -p IOUSB -l | grep -E '"USB Serial Number"|IODialinDevice'`
# or `pyserial`'s tools: .venv/bin/python -m serial.tools.list_ports -v

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
- **Toolchain:** the xPack arm-none-eabi-gcc **15.2.1-1.1** must sit at `~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/`. The Makefile `TOOLCHAIN` variable can override that path.
  - Download: https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/tag/v15.2.1-1.1, asset `xpack-arm-none-eabi-gcc-15.2.1-1.1-darwin-arm64.tar.gz`.
  - Expected SHA-256 (from the home machine): `574082d35e49a2bcbdc355836b2a3ae5e5bb3b9456c9f5e37177db2ab4aad870`.
  - Do not use the Homebrew `gcc-arm-embedded` cask: its checksum failed here, and that was deliberately not bypassed.
- **Vendor code:** `tools/fetch-vendor.sh` fetches pinned STM32CubeWL v1.6.0 plus its submodules and Mbed TLS 3.6.6 into `vendor/` (git-ignored).
- **Build and flash:**
  - `cd firmware/stage0-node && make ROLE=rx flash SERIAL=0016001E4142500E20353451`, then the same with `ROLE=tx` and the TX serial.
  - Flashing keeps provisioning and the journal.
  - A release must be recorded in `firmware/stage0-node/RELEASES.md`. H01 evidence must name a release.

## 6. Next steps, in order
1. **Re-establish the link at the office.** Steps above. Confirm green ACK LEDs and `/v1/status`.
2. **SHT45 (Adafruit 6174), expected ~Oct 14.**
   - Wiring: SDA → CN5.9 (D14/PA11), SCL → CN5.10 (D15/PA12), 3V3 → CN6.4, GND → CN6.6. Bus is I2C2 at 100 kHz.
   - Firmware sensor driver: TODO.
   - Verify a CRC-checked reading, plus the unplug and fault behaviour. Then cut a new release.
3. **Home Assistant.** Needs Clint's real MQTT broker details: host, port, TLS, user. H01 requires an HA entity.
4. **Placement.** Check the link in both directions at the real TX/RX locations, then tune SF and power.
5. **H01:** the 24 h run plus the restart/outage matrix, scored with `tools/h01_report.py --start <UTC> --hours 24 --output evidence/h01-<date>`.

**Deliberately open:**
- G10: flash read-out protection (field use).
- G14: brown-out reset level (Stage 1).
- H11: 30-day buffer, which needs SPI NOR.
- G16: timed ACK slot.
- **G7 part B** (true USB power-cut testing) is **deferred by Clint**. Don't raise it.

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
| `evidence/` | Every bench run, dated |
