# Stage-0 node firmware (NUCLEO-WL55JC1)

One source tree, two roles: **TX** (sensor node, board A `003B00194142500E20353451`) and **RX** (USB receiver bridge, board B `0016001E4142500E20353451`). Built on ST's SubGHz_Phy_PingPong board support (STM32CubeWL v1.6.0). Wire protocol: [`docs/protocol.md`](../../docs/protocol.md) draft 4 (see also [`protocol-stack.md`](../../docs/protocol-stack.md)).

**Status (2026-10-13):**
- Release `a07f498273f7` ([`RELEASES.md`](RELEASES.md)) is on both boards, and the bench link works end to end.
- The SHT45 parts have arrived but are not yet wired, so every reading is an honest `sensor_fault`.
- **H01 NOT RUN.**

## Build and flash

```sh
tools/fetch-vendor.sh                       # pinned STM32CubeWL + submodules, Mbed TLS 3.6.6
cd firmware/stage0-node
make ROLE=rx flash SERIAL=0016001E4142500E20353451
make ROLE=tx flash SERIAL=003B00194142500E20353451
```

Flashing rewrites only the firmware region (pages 0–31). Provisioning, counters and the journal (pages 32–127) survive reflashing; this was verified on 2026-10-12. The binary SHA-256 is printed at the end of each build.

Makefile variables and targets:

| Name | Default | Meaning |
|---|---|---|
| `ROLE` | `tx` | `tx` or `rx`. The output goes to `build/<role>/stage0-<role>.{elf,bin,map}`. |
| `SERIAL` | none | ST-LINK serial of the board to program (`flash` target only). |
| `CUBE` | `../../vendor/STM32CubeWL` | STM32CubeWL checkout created by `tools/fetch-vendor.sh`. |
| `TOOLCHAIN` | `~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin` | Directory that holds `arm-none-eabi-gcc`. |
| `all` (default target) | | Builds the `.elf` and `.bin`, then prints the size and the `.bin` SHA-256. |
| `flash` | | Builds if needed, then programs the `.elf` with OpenOCD (connect under reset) and verifies it. |
| `clean` | | Removes `build/`, for **both** roles. |

The firmware version string (`fw=` in `#boot`/`#status`) is `git describe --always --dirty --abbrev=12` at build time. A build from a modified tree reports `…-dirty`, and every commit changes the binary.

## Provision and run (host)

```sh
python -m ws0 init --hardware --station station-01 --station-id 1 --directory run-hw
python -m ws0 provision-node --directory run-hw --serial /dev/cu.usbmodem<TX port>
python -m ws0 serve --directory run-hw --serial /dev/cu.usbmodem<RX port>
```

`provision-node` sends the station ID and key to an **unprovisioned** TX board over USB, then checks the reply against the key check value (KCV: first 3 bytes of AES(key, 0¹⁶)). It refuses to overwrite a provisioned board.

It also sends an **epoch floor** (`PROVISION <id> <key> <epoch_floor>`). The floor is one above the highest boot epoch the gateway has stored for this station in `observations`, `rejections` and `diagnostics` (`ws0/__main__.py`, `epoch_floor`), or 0 (no floor) for an empty database. The node raises its stored epoch to the floor (`store_epoch_floor`), so every later boot epoch is above it and the observation identities (epoch, seq) of a wiped and re-provisioned node never collide with stored history (gap G5). **The floor raises only the epoch, not the transmission counter.**

To re-provision deliberately, send `WIPE ERASE-ALL-NODE-STATE` on the TX console. That erases the key, the counters, the journal, and the persisted `lost`/`abandoned` totals, then reboots with solid red LED3.

**Re-keying rule:** WIPE resets the transmission counter to 1, and the AES-CCM nonce is kind + station + counter (`firmware/common/ws_frame.c`). Re-provisioning with any key that was used before would therefore repeat nonces. **Always `init` a new run directory, which creates a new key, after a WIPE, and never reuse an old key.** Moving the boards between gateways is covered in [`docs/runbook-moving-boards.md`](../../docs/runbook-moving-boards.md).

For a long run (H01), install the gateway as a LaunchAgent. It restarts if it exits and finds the RX board by its ST-LINK serial number after a replug:

```sh
tools/deploy/macos/install.sh install run-hw 0016001E4142500E20353451
tools/deploy/macos/install.sh status      # uninstall: tools/deploy/macos/install.sh uninstall
```

The Linux equivalent is `tools/deploy/linux/ws0-gateway.service`. Keep the Mac awake during H01.

`run-hw/` holds secrets and live data and is git-ignored. `serve` appends receiver diagnostics and every frame/ACK pair to `run-hw/receiver.log`.

## Console (USB VCP, 115200 8N1)

| Board | Output | Commands |
|---|---|---|
| TX | Lines starting with `#` (glossary below) | `STATUS`, `KAT`, `PROVISION <station_id> <32 hex key> [epoch_floor]` (decimal ID ≥ 1; only when unprovisioned; reboots on success), `WIPE ERASE-ALL-NODE-STATE` (reboots), `TEST-HANG` (bench: proves the watchdog), `TEST-FLASH-STORM` (bench: continuous flash writes for power-cut tests; pauses sampling; ends at reboot) |
| RX | One lowercase hex line per received observation **or health-report** frame (kinds 1 and 4), plus `#` diagnostics (below) | `STATUS`, `TEST-HANG`, or one hex **ACK or NACK** line from the host. Lines starting with `#` are ignored. |

### TX console glossary (`App/app_tx.c`)

`#status` (on `STATUS`, and at boot) has these fields:

| Field | Meaning |
|---|---|
| `fw` | Firmware version string (git commit, see Build) |
| `reset` | Last reset cause: `watchdog`, `power`, `software`, `lowpower`, `option-bytes`, `pin` or `unknown` |
| `provisioned`, `station`, `kcv` | Provisioning state, station ID, and the key check value |
| `kat` | Boot self-test result, `pass` or `FAIL` |
| `epoch`, `next_seq` | This boot's epoch, and the next observation sequence number |
| `ctr` | Next transmission counter (the nonce counter) |
| `ecc` | Double-ECC flash read faults seen since boot |
| `link`, `silent` | Link state (`linked` or `probing`), and consecutive minutes with no reply |
| `energy` | Energy state. Always `normal` in Stage 0 (USB power). |
| `time`, `utc` | `synchronized` or `unknown`, and the UTC seconds (0 when unknown) |
| `uptime` | RTC seconds since boot |
| `pending` | Journaled readings not yet acknowledged |
| `lost` | Cumulative readings dropped by journal overflow (persisted across resets) |
| `burned` | Journal slots found torn or unusable since boot |
| `abandoned` | Cumulative records given up by NACK or the strike limit (persisted) |
| `sent`, `acked`, `no_ack`, `ack_rejects`, `sensor_faults` | Counters since boot. `acked` counts ACKs that matched a journal record. `ack_rejects` counts replies that failed authentication, plus NACKs that were not for the frame just sent. |

Other lines:

| Line | Meaning |
|---|---|
| `#boot role=tx fw= reset= kat= freq= bw= sf= power=` | Printed at every boot. `bw` is the index (2 = 500 kHz). |
| `#sample epoch= seq= uptime= valid= t= rh= time= utc= journal= pending= lost=` | One per minute. `journal=ERROR` means the reading could not be journaled. |
| `#ack epoch= seq= found= time_sync= rssi= snr= pending=` | Authentic ACK. `time_sync=1`: the clock was set from it. |
| `#ack none epoch= seq=` | No reply within the 2 s window. The reading stays journaled, and this minute's backlog drain stops. |
| `#ack reject len= rssi= snr=` | A reply failed authentication |
| `#nack epoch= seq= reason= abandoned=` | Authentic NACK for the frame just sent; the record is abandoned. Reason 1 = collision, 2 = invalid (`ws_frame.h`). |
| `#nack ignored: …` | NACK that was not for the frame just sent |
| `#abandon epoch= seq= after 10 unanswered tries …` | Strike limit: the record was abandoned |
| `#link probing: …`, `#link probe unanswered; …`, `#link linked after N silent minutes` | Link-state changes (see Transmission policy) |
| `#diag sent pending= lost= torn= abandoned= no_ack=` | Health report (kind 4) sent. `torn` is `burned`. |
| `#time restored utc= sync_age=` | Time trust kept across a warm reset |
| `#busy previous exchange still running` | The minute's sample was journaled but not sent |
| `#kat pass\|FAIL`, `#wipe ok\|ERROR`, `#provisioned station= kcv= epoch_floor=`, `#unprovisioned: …`, `#test-hang: …` | Command replies |
| `#storm start ctr=`, `#storm writes= ctr= burned=`, `#storm-scrub dropped=` | TEST-FLASH-STORM progress (every 256 writes); boot cleanup of storm slots |
| `#error <what>` | `journal-read`, `counter-reserve`, `seal`, `radio-busy`, `journal-ack`, `tx-timeout`, `store-init`, `epoch-reserve`, `self-test failed; not transmitting`, plus the command errors `already-provisioned`, `usage: …`, `bad key`, `epoch-floor`, `provision rc=`, `unknown command` |

### RX console glossary (`App/app_rx.c`)

| Line | Meaning |
|---|---|
| `<hex>` | A received frame for the host (observation or health report) |
| `#rx obs rssi= snr=` | Follows each forwarded frame |
| `#rx drop len= rssi= snr=` | Received something that is not a current-draft observation or health report |
| `#rx error` | Radio receive error |
| `#host reject len=` | A host line that is not a valid ACK/NACK hex line |
| `#tx timeout`, `#tx busy` | ACK/NACK transmission failed |
| `#alive uptime= forwarded= dropped= acks= diag= listening=` | Every 60 s. The gateway marks the receiver silent after 180 s without `#alive` or `#boot` (gap G12). |
| `#watchdog radio not listening; re-arming` | Self-heal attempt before the watchdog may reset the board |
| `#status role=rx forwarded= dropped= acks=` | Reply to `STATUS`. `acks` counts ACK/NACK lines handed to the radio. |
| `#boot role=rx fw= reset= freq= bw= sf= power=`, `#test-hang: …` | Boot line and command reply |

### Transmission policy (TX)

This is summarized from `App/app_tx.c`; the approved policy is in [`docs/radio-energy-policy.md`](../../docs/radio-energy-policy.md).
- **Each minute:** the live reading goes first, then at most 5 older pending readings (energy state NORMAL). The total is also capped at about 5 s of estimated radio time per minute. Each frame gets one 2 s ACK window. A missed reply ends that minute's drain.
- **Link probing:** after 3 minutes with no reply the link state becomes `probing`. Only the live reading is sent then, as a probe at 2, 4 and 8 minutes, then every 15 minutes. All readings stay journaled. Any reply returns the state to `linked`.
- **Health report** (kind 4): sent every 15 min and at each link-state change, only while linked. It is fire-and-forget, with no journal entry and no ACK.
- **Strike limit:** a record that stays unanswered 10 times while the gateway answers other frames in the same exchange is abandoned (`#abandon`).

**Watchdog:** independent watchdog, ~8 s. It is refreshed only from the main loop, and only while the role shows real progress: TX samples every ≤150 s and no exchange runs >30 s; RX is listening or finishes a transmission in <5 s, with one re-arm attempt. The reset cause is printed on every boot.

TX runs a boot self-test (`kat=pass`): it seals and opens fixed vectors and compares them with Python-generated bytes (`tests/test_frame.py`). A failed self-test means the board refuses to transmit.

## LEDs

| LED | TX | RX |
|---|---|---|
| LED1 blue | 400 ms: sending a reading; 40 ms blip every 2 s: alive | 400 ms: frame forwarded to host; 40 ms blip every 2 s: alive |
| LED2 green | ACK received (reading committed on host) | Host ACK or NACK handed to the radio |
| LED3 red | Flash 400 ms: no ACK / rejected ACK / TX timeout (reading stays queued). Flash 1 s: NACK or abandoned record. **Solid**: not running (unprovisioned, self-test failed, flash error) | Flash 400 ms: radio error, TX timeout, unusable frame, bad host line |
| LED6 (COM) | ST-LINK status, not this firmware (red = idle) | same |

## Flash layout and outage capacity (TX)

| Pages | Use |
|---|---|
| 0–31 (64 KB) | Firmware; the linker script enforces this (TX image about 52 KB, RX about 30 KB at a07f498) |
| 32 | Config: station ID, key, KCV. The magic double-word is written last |
| 33–34 | Monotonic log, A/B: boot epoch, counter reservations (blocks of 256), cumulative `lost`/`abandoned` totals. Recovery takes the maximum. Compaction writes its header last |
| 35–127 | Journal ring: 93 pages × 51 slots of 40 bytes |

**Capacity: 4,743 observations ≈ 79 h ≈ 3.3 days** of one-minute readings without an ACK. When full, the oldest page is erased and its unacknowledged records are counted in `lost`. The agreed target was "about 4 days"; the actual layout gives 3.3 days because each slot needs a separately programmed ACK double-word. The 30-day/16 MB requirement remains H11 work (external SPI NOR).

Power-fail behaviour. Resets during flash writes were tested 70 cycles (G7 part A, pass, `evidence/g7-reset-during-write-2026-10-13/`). **True power removal has not been tested yet** (G7 part B, deferred; see `docs/failure-modes.md`).
- Each slot is committed by a final CRC double-word.
- A torn write reads back as erased, uncommitted, or a double-ECC error. `NMI_Handler` catches the ECC error, and the slot is counted as `burned`, never used. Exception: a torn **ACK** word counts as acknowledged, because the host had already committed the record.
- The epoch is reserved before the first sample of each boot.
- Counters are reserved in blocks before use, so a reset skips the rest of the block. Observed: counter 8 → 257 after a restart (reflash or reboot; the bring-up log files it under reboot behaviour, unverified which).

## Known limits

The full failure analysis, the loss budget, and the ranked gap list are in [`docs/failure-modes.md`](../../docs/failure-modes.md).


- The key is stored in plain internal flash at RDP level 0 (anyone with SWD can read it). Stage-0 bench only.
- Time-sync accuracy: the node is set to the host's commit time, up to about 1 s behind. It is trusted for 6 h, then marked unknown.
- Time across resets: a warm reset keeps time trust (RTC backup registers DR3/DR4; ST's SysTime uses DR0–DR2). A power loss clears it; the gateway then reconstructs times from the always-present `uptime` field.
- `LOW_POWER_DISABLE=1` (USB-powered Stage 0). Power work belongs to Stage 1.
- The SHT45 driver uses I2C2 on PA11/PA12 at 100 kHz with stuck-bus recovery. It is untested on hardware until the sensor arrives.
