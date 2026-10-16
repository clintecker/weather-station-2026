# Context pack: resume the bench prototype on a new machine

Written 2026-10-13 for picking the work up at the office with the two boards. Updated 2026-10-14
for protocol version 5, and 2026-10-16 for the current release. Give this file to a fresh Claude
Code session first. Links to the deeper documents are at the end.

## 1. What this project is

A home weather station.

- The sensor node is a NUCLEO-WL55JC1 development board (STM32WL microcontroller with a LoRa
  radio). It sends one temperature and relative-humidity (T/RH) reading a minute over encrypted
  LoRa to a receiver board on USB.
- A Python gateway (`ws0`) stores the readings in SQLite. Later it feeds Home Assistant (HA) over
  MQTT.
- The two boards are the transmitter (TX, the sensor node) and the receiver (RX).

The final node runs **unattended on battery and solar, at long range**. Judge every decision for
that node, not for the USB bench. The node must fail cheaply. Push work to the mains-powered
gateway.

**Plan of record:** strict stage order ([`next-stages-plan.md`](next-stages-plan.md)).

```mermaid
flowchart LR
  S0["Stage 0: data path on the bench (now)"] -- "H01 passes" --> S1["Stage 1: main power and pack state"]
  S1 -- "H02 and H03 pass" --> S2["Stage 2: one wired module"]
  S2 -- "H04 passes" --> S3["Stage 3: complete unheated sensing"]
```

- **Stage 0** is the bench data path: TX board → LoRa → RX board → USB → gateway → SQLite, on USB
  power. Stage 0 ends when **H01**, the 24-hour delivery test, passes.
- H01 requires 1,440 one-minute intervals in 24 h, with at least 1,426 valid readings committed
  within 120 s, plus a restart and outage matrix (`docs/H01-checklist.md`).
- **Stage 1** (main battery pack, charger and solar) does not start before H01 passes.
- Stage 2 adds one wired sensor module on an RS-485 port. Stage 3 adds the complete unheated
  sensor set.

## 2. Where things stand (on `master`)

- **Firmware release `260c9ccbe938`** (2026-10-16) is on both boards
  (`firmware/stage0-node/RELEASES.md`). The gateway runs on run directory `run-d6`. The key check
  value (KCV) of its key is `e03059`.
  - Check `STATUS` on each board before you rely on it. **No rebuild is needed** to resume.
  - TX = board A, ST-LINK serial `003B00194142500E20353451`.
  - RX = board B, ST-LINK serial `0016001E4142500E20353451`.
  - Identify boards by serial number. Port names change between machines.
- **Protocol version 5.** Spec: `docs/protocol.md`. Design rationale: `docs/protocol-design.md`.
  - Encryption: AES-128-CCM with an 8-byte header (version and kind, station u16, counter u40)
    and an 8-byte tag.
  - Observation frame: 51 bytes for the T/RH build with the minute summary. It has a 22-byte
    head, a field bitmap and catalog fields. Each field has its own INVALID code.
  - ACK and NACK frames: 33 bytes. The ACK carries the host time.
  - Health report: 48 bytes, every 15 min.
  - **A frame-format change needs a fresh key.** Send `WIPE ERASE-ALL-NODE-STATE` on TX,
    `init` a new run directory, run `provision-node`, and flash both boards. The first
    version-5 release (`bc5e6ede429c`) was installed that way.
  - Keys and run directories from protocol version 4 (`run-hw/`, `run-office/`) are retired.
    `run-d5` is archived as `run-d5-archive-2026-10-15/`.
- **Radio:** 915.0 MHz, 500 kHz bandwidth, spreading factor (SF) 7, coding rate 4/5, 0 dBm (bench).
- **Bench-verified:**
  - the journal: about 2.3 days of outage buffer in internal flash (3,348 records of 56 bytes),
  - durable counters and the watchdog,
  - the reset-during-write test (70 cycles),
  - outage recovery with link back-off, NACK, and gateway auto-reconnect,
  - the host clock check and RX liveness,
  - MQTT against a local broker (currently **disabled**),
  - the H01 scorer `tools/h01_report.py`.
- **Latest soak evidence:** `evidence/soak-a07f498-2026-10-13/`. Over 9 h, 549 of 549 minutes
  arrived on time, with median latency 1.5 s, 0 lost and 0 missed ACKs.
- **Tests:** `WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests` gave **137**
  passing on 2026-10-14. One SNTP test needs the network.
  - Run `tools/fetch-vendor.sh` first. Without `vendor/`, the tests skip the C-against-Python
    crypto tests.
- **Other checks** (all in CI, `.github/workflows/ci.yml`):
  - `ruff check`: Python bug rules only (pyflakes, bugbear, errors, `ruff.toml`). Install it with
    `pip install -r requirements-dev.txt`. CI runs it on Linux only.
  - Fuzzing of the node's input parsers: `make -C firmware/fuzz check`. The targets are `reply`
    (envelope open and seal limits), `provision`, `console` (line assembly, hex decode, RX up/down
    filters) and `obs` (the observation encoder). `tests/test_fuzz.py` runs them on every test
    run. CI also runs libFuzzer for 60 s per target (`firmware/fuzz/README.md`).
  - The C host tests (`test_policy`, `test_sensor`, the flash power-cut tests) and the fuzzers
    run under AddressSanitizer and UndefinedBehaviorSanitizer (not on Windows).
  - Firmware builds: GCC `-fanalyzer` on our files, the worst-case stack bound (`make stack`:
    TX 71 %, RX 32 % of 8 KB for `260c9ccbe938`), and no blocking wait reachable at run time
    (`make waits`, `docs/firmware-budget.md` §Blocking waits).

## 3. Moving the boards: the radio key stays on the gateway machine

The run directory holds the radio key. Git ignores it, and it must never be committed. The
office trip of 2026-10-13 showed what happens when the boards move without it:

- The TX board was provisioned with a key that lived only in `run-hw/` on the home Mac.
- The home gateway's launchd agent kept running and waiting for the boards.
- After TX got a new office key, the home gateway rejected its frames as unauthenticated.

**When the boards move, use one of these** (details and decision chart:
[`runbook-moving-boards.md`](runbook-moving-boards.md)):

- Run the gateway on the machine that holds the matching run directory (for example, take that
  laptop along).
- Copy the run directory by a private route (never git, chat or email), and point the gateway at
  the copy.
- Make a **new** key: `init` a new run directory, `WIPE` TX, `provision-node`.

**For a fresh key:**

1. On the TX console, send `WIPE ERASE-ALL-NODE-STATE`. This erases the key and the journal.
   From release `0f456040fe54` on, it keeps the counter and the epoch.
2. `init` a new run directory, then run `provision-node`.

A new key is always safe. Reuse a key only if the board's counter has never gone back since that
key was first used.

**Never re-provision TX with the old `run-hw` key after a WIPE.** (Corrected 2026-10-13. An
earlier version of this pack suggested it.)

- The AES-CCM nonce is kind + station + the transmission counter (`header()` in
  `firmware/common/ws_frame.c`, `docs/protocol.md` section 1).
- On firmware before release `0f456040fe54`, WIPE reset that counter to 1. The morning office
  wipe of 2026-10-13 did that.
- From `0f456040fe54` on, WIPE keeps the counter. But this board's counter is now far below what
  the home key already used, so the home key stays retired for this board.
- The `PROVISION` epoch floor raises only the epoch, which is the observation identity
  (`App/node_store.c`, `store_epoch_floor`). It does not raise the counter.
- TX had already transmitted with the home key (for example the 9 h soak,
  `evidence/soak-a07f498-2026-10-13/`). Reuse would repeat nonces already sent on air.

## 4. Office setup (fast path: run the bench, no firmware build)

```mermaid
flowchart TD
  C["Clone, make the venv, fetch vendor code"] --> T["Run the tests: expect all OK, none skipped"]
  T --> P["List ports and find TX and RX by ST-LINK serial"]
  P --> W["TX console: WIPE ERASE-ALL-NODE-STATE"]
  W --> I["ws0 init into a new run directory"]
  I --> PR["ws0 provision-node to TX"]
  PR --> S["ws0 serve with the RX serial number"]
  S --> V{"Blue flash then green on TX each minute?"}
  V -- yes --> OK["Link up. For a long run, install the launchd agent"]
  V -- no --> F["See failure-modes.md section 9"]
```

```sh
git clone https://github.com/clintecker/weather-station-2026 && cd weather-station-2026
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # or: uv venv && uv pip install -r requirements.txt
sh tools/fetch-vendor.sh                                                  # needed for 7 of the tests
WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests   # expect 137 OK, none skipped (needs network for one SNTP test)

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

- `run-office/` matches the `run*/` ignore rule, so nobody can commit it by accident.
- For a long run, install the launchd agent:
  `tools/deploy/macos/install.sh install run-office 0016001E4142500E20353451`.
- Keep the Mac awake (`caffeinate -dimsu`).

## 5. Full setup (only to change or rebuild firmware)

- **Homebrew:** `brew install stlink open-ocd`. `uhubctl` and `mosquitto` are optional.
- **Toolchain:** the xPack arm-none-eabi-gcc **15.2.1-1.1** must be at
  `~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/`. To use another install, set the Makefile's
  `TOOLCHAIN` variable to that install's `bin` directory: `TOOLCHAIN=<root>/bin`.
  - Download: https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/tag/v15.2.1-1.1,
    asset `xpack-arm-none-eabi-gcc-15.2.1-1.1-darwin-arm64.tar.gz`.
  - Expected SHA-256 (from the home machine):
    `574082d35e49a2bcbdc355836b2a3ae5e5bb3b9456c9f5e37177db2ab4aad870`.
  - Do not use the Homebrew `gcc-arm-embedded` cask. Its checksum failed here, and we did not
    bypass the check.
- **Vendor code:** `tools/fetch-vendor.sh` fetches the pinned STM32CubeWL v1.6.0 and its
  submodules into `vendor/` (git-ignored). Mbed TLS 3.6.6 comes in as ST's `mbed-crypto`
  submodule of STM32CubeWL, not as a separate download.
- **Build and flash:**
  - `cd firmware/stage0-node && make ROLE=rx flash SERIAL=0016001E4142500E20353451`. Then do the
    same with `ROLE=tx` and the TX serial.
  - Flashing keeps the provisioning and the journal.
  - Record every release in `firmware/stage0-node/RELEASES.md`. H01 evidence must name a release.

## 6. Next steps, in order

```mermaid
flowchart TD
  A["1. Link at the office (done 2026-10-13)"] --> B["2. SHT45 sensor wired and verified"]
  B --> C["3. Home Assistant connected"]
  C --> D["4. Placement: link checked both ways at the real locations"]
  D --> E["5. H01: 24-hour run and restart/outage matrix"]
```

1. **Re-establish the link at the office.** Steps above. Confirm green ACK LEDs and
   `/v1/status`. *Done 2026-10-13: office key KCV `b7142e` in `run-office/` (see
   `docs/hardware/nucleo-wl55jc-bringup.md`, "Office session").*
2. **SHT45 sensor (Adafruit 6174), delivered 2026-10-13** with a 4397 STEMMA QT-to-female-socket
   cable, 1954 female/male jumpers and a spare Micro-B cable. *Wired 2026-10-14 on the morpho
   pins, with valid readings (`docs/hardware/nucleo-wl55jc-bringup.md`, "SHT45 first light").
   Release `bc5e6ede429c` still had two open checks: the sensor-unplug behaviour (`null` T/RH,
   `quality=sensor_fault`) and the first health report (build ID, ACK RSSI/SNR).*
   - Wiring (Arduino headers): SDA → CN5.9 (D14/PA11), SCL → CN5.10 (D15/PA12), 3V3 → CN6.4,
     GND → CN6.6. The bus is I2C2 at 100 kHz.
   - **The 4397's female sockets do not fit the female Arduino headers.** No-solder route: plug
     them onto the male ST morpho pins. Yellow SCL → CN10.3, blue SDA → CN10.5, black GND →
     CN10.9, red 3V3 → CN7.16 (not CN7.18, which is 5 V). Positions and source:
     `docs/protocol-stack.md` §3.1. Alternative: solder the breakout's header strip and use the
     1954 jumpers on CN5/CN6. Wire with TX unplugged.
   - The firmware sensor driver exists (`firmware/stage0-node/App/sensor.c`: I2C2, stuck-bus
     recovery). Its CRC and fault handling are unit-tested.
   - Verify a CRC-checked reading, plus the unplug and fault behaviour. Then cut a new release.
3. **Home Assistant.** The steps are in `docs/runbook-home-assistant.md`. They need Clint's
   broker host, port, TLS on/off and user name. The password goes in a private file, not in chat.
   H01 requires an HA entity.
4. **Placement.** Check the link in both directions at the real TX and RX locations. Then tune
   SF and power.
5. **H01:** the 24-hour run plus the restart and outage matrix. Score it with
   `tools/h01_report.py --db <run dir>/observations.sqlite3 --station station-01 --start <UTC> --hours 24 --output evidence/h01-<date>`.
   Use the run directory that the gateway actually served. `--db` defaults to `run-hw/`.

**SHT45 test plan:** `docs/firmware-review-2026-10-13.md` §2.

**Deliberately open:**

- Flash read-out protection (for field use).
- Brown-out reset level (Stage 1).
- H11, the 30-day storage test: it needs external SPI NOR flash.
- A timed ACK receive slot.
- Code space for the final station (`docs/firmware-budget.md`). Keep the STM32WL55JC. Plan flash
  layout v2 with H11. The final image must be ≤ 75 % of its region. Watch the flash guard in
  every build.
- **True USB power-cut testing** is **deferred by Clint**. Do not raise it.

**Bench note (2026-10-13):** a USB dropout of about 1 s makes the ST-LINK reset its board (seen
on both boards). For H01 on USB, secure the cables. Keep hands and debugger sessions off them.
Range-test tool and findings: `firmware/rangetest/README.md`,
`evidence/rangetest-office-2026-10-13/`.

**Minor:** the simulator drains 5 backlog records per minute, like the firmware in the NORMAL
energy state. It does not model the drain stop or the PROBING link state
(`docs/protocol-stack.md` §9.4).

## 7. Working rules (from Clint)

- Do routine authorized work on your own. Ask only for decisions that are Clint's.
- Explain electronics plainly. Clint is a strong software developer who is new to embedded work.
- Never loosen a test criterion. Never claim H01 from a smoke test or a simulation.
- No purchases, emails, sharing, or destructive resets without his OK. Setting up again at the
  office was Clint's call (2026-10-13).
- Never commit keys, tokens or run databases.
- Document trials and errors (`docs/hardware/nucleo-wl55jc-bringup.md`).
- Keep bench tests short: minutes, not hours, unless the test is H01 itself.
- **Bench quirks:**
  - The factory ST firmware disables the debug port (SWD), so flashing needs connect-under-reset.
    Our firmware keeps SWD enabled.
  - Generic USB hubs that claim per-port power switching do not actually cut the USB supply
    (VBUS).

## 8. Map of the docs

| File | What |
|---|---|
| `docs/protocol.md` | Wire format, protocol version 5 (normative) |
| `docs/protocol-design.md` | Why the format looks the way it does (design rationale, reviews) |
| `docs/protocol-stack.md` | Layered explanation with diagrams |
| `docs/failure-modes.md` | Failure modes and effects (FMEA), loss budget, recovery runbook, open issues |
| `docs/radio-energy-policy.md` | Approved send and back-off policy for battery and solar |
| `docs/H01-checklist.md` | The 24-hour delivery test |
| `docs/next-stages-plan.md` | Stages 1–3: parts and plan |
| `docs/hardware/nucleo-wl55jc-bringup.md` | Board bring-up trial-and-error log |
| `firmware/stage0-node/README.md` | Build, console commands, LEDs, flash layout |
| `firmware/stage0-node/RELEASES.md` | Release hashes |
| `docs/firmware-review-2026-10-13.md` | Firmware review roadmap (§2: SHT45 test plan) |
| `docs/firmware-budget.md` | Flash, RAM and radio budget, measured. Layout v2 and payload plan |
| `docs/runbook-home-assistant.md` | MQTT and Home Assistant setup, password file, running the gateway on macOS, Linux, Windows |
| `docs/runbook-moving-boards.md` | Moving boards between gateways without key or nonce reuse |
| `docs/simulation-harness.md` | Simulation harness model and limits |
| `docs/web-dashboard.md` | Live dashboard served by the gateway |
| `docs/openapi.json` | Gateway HTTP API |
| `firmware/rangetest/README.md` | Range-test bench tool |
| `hardware/chicago-test-hardware-r0/` | Chicago test hardware, revision 0: build and order guide, manufacturing files |
| `tools/README.md` | Every tool in `tools/` |
| `evidence/` | Every bench run, dated |
