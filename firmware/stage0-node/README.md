# Stage-0 node firmware (NUCLEO-WL55JC1)

One source tree, two roles: **TX** (sensor node, board A `003B00194142500E20353451`) and **RX** (USB receiver bridge, board B `0016001E4142500E20353451`). Built on ST's SubGHz_Phy_PingPong board support (STM32CubeWL v1.6.0), which lives in [`../board/nucleo-wl55jc`](../board/nucleo-wl55jc/board.mk) and is shared with the bench tools (`firmware/rangetest`, `firmware/pingpong`): `Core/`, `startup/`, `SubGHz_Phy/Target/`, the linker script and the common build rules (`board.mk`). This project keeps only its own `Core/Src/stm32wlxx_it.c` (flash-ECC NMI hook, HardFault record) and `Core/Inc/utilities_def.h` (sequencer tasks). Wire protocol: [`docs/protocol.md`](../../docs/protocol.md) draft 5 (see also [`protocol-stack.md`](../../docs/protocol-stack.md)).

**Status (2026-10-14):**
- Release `bc5e6ede429c` ([`RELEASES.md`](RELEASES.md)), protocol **draft 5** (8-byte header and tag, field catalog, 32-byte health report), is on both boards since 2026-10-14, and the bench link works end to end.
- That release changed the frame format, so it was installed with a **fresh key**: `WIPE ERASE-ALL-NODE-STATE` on the TX, a new run directory (`run-d5`, KCV `5618eb`), then `provision-node` (protocol.md section 2). Any later frame-format change needs the same. Always flash **both** boards: boards of different drafts drop each other's frames.
- The SHT45 is wired (morpho pins) and gave valid readings on 2026-10-14 ([`docs/hardware/nucleo-wl55jc-bringup.md`](../../docs/hardware/nucleo-wl55jc-bringup.md), "SHT45 first light").
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
| `BUILD` | `build/<role>` | Build directory (CI uses separate ones for the analyzer builds). |
| `ANALYZE` | unset | `1` adds GCC's static analyzer (`-fanalyzer`) to our own C, which always builds with a strict warning set and `-Werror`. |
| `all` (default target) | | Builds the `.elf` and `.bin`, then prints the size, the flash budget line and the `.bin` SHA-256. |
| `flash` | | Builds if needed, then programs the `.elf` with OpenOCD (connect under reset) and verifies it. |
| `stack` | | Worst-case stack bound from the GCC call graphs (`tools/stack_report.py`); fails above the linker's 8 KB reservation. |
| `clean` | | Removes `build/`, for **both** roles. |

The firmware version string (`fw=` in `#boot`/`#status`) is `git describe --always --dirty --abbrev=12` at build time. A build from a modified tree reports `…-dirty`, and every commit changes the binary.

## Provision and run (host)

```sh
python -m ws0 init --hardware --station station-01 --station-id 1 --directory run-hw
python -m ws0 provision-node --directory run-hw --serial /dev/cu.usbmodem<TX port>
python -m ws0 serve --directory run-hw --serial /dev/cu.usbmodem<RX port>
```

`provision-node` sends the station ID (1 to 65,535: the draft-5 header holds 2 bytes) and key to an **unprovisioned** TX board over USB, then checks the reply against the key check value (KCV: first 3 bytes of AES(key, 0¹⁶)). It refuses to overwrite a provisioned board.

It also sends an **epoch floor** (`PROVISION <id> <key> <epoch_floor>`). The floor is one above the highest boot epoch the gateway has stored for this station in `observations`, `rejections` and `diagnostics` (`ws0/__main__.py`, `epoch_floor`), or 0 (no floor) for an empty database. The node raises its stored epoch to the floor (`store_epoch_floor`), so every later boot epoch is above it and the observation identities (epoch, seq) of a wiped and re-provisioned node never collide with stored history (gap G5). **The floor raises only the epoch, not the transmission counter.**

To re-provision deliberately, send `WIPE ERASE-ALL-NODE-STATE` on the TX console. From release `0f456040fe54` that erases the key and the journal and keeps the counter, the epoch and the `lost`/`abandoned` totals (gap G17); earlier releases erased those too. It then reboots with solid red LED3.

**Re-keying rule:** the AES-CCM nonce is kind + station + transmission counter (`firmware/common/ws_frame.c`). From release `0f456040fe54`, WIPE erases only the key and the journal and keeps the counter and epoch (gap G17); earlier releases reset the counter to 1. A key used before `0f456040fe54`, or on another board, could therefore repeat nonces. **After a WIPE, `init` a new run directory (a new key).** Moving the boards between gateways is covered in [`docs/runbook-moving-boards.md`](../../docs/runbook-moving-boards.md).

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
| TX | Lines starting with `#` (glossary below) | `STATUS`, `KAT`, `PROVISION <station_id> <32 hex key> [epoch_floor]` (decimal ID 1–65535; only when unprovisioned; reboots on success), `WIPE ERASE-ALL-NODE-STATE` (reboots), `TEST-HANG` (bench: proves the watchdog), `TEST-FAULT` (bench: proves crash recording), `TEST-FLASH-STORM` (bench: continuous flash writes for power-cut tests; pauses sampling; ends at reboot) |
| RX | One lowercase hex line per received draft-5 observation (39–85 bytes; 42 for the T/RH build) **or health-report** frame (48 bytes), plus `#` diagnostics (below) | `STATUS`, `TEST-HANG`, `TEST-FAULT`, or one hex **ACK or NACK** line from the host (exactly 33 bytes = 66 hex digits). Lines starting with `#` are ignored. |

### TX console glossary (`App/app_tx.c`)

`STATUS` (and every boot) prints two lines, `#status` then `#counts`. One line used to be cut off
at the console's 256-byte print buffer (`UTIL_ADV_TRACE_TMP_BUF_SIZE`), which hid the last counters.

`#status` (identity and state; `ws0 provision-node` reads it) has these fields:

| Field | Meaning |
|---|---|
| `fw` | Firmware version string (git commit, see Build) |
| `reset` | Last reset cause: `watchdog`, `power`, `software`, `lowpower`, `option-bytes`, `pin` or `unknown` |
| `provisioned`, `station`, `kcv` | Provisioning state, station ID, and the key check value |
| `kat` | Boot self-test result, `pass` or `FAIL` |
| `epoch`, `next_seq` | This boot's epoch, and the next observation sequence number |
| `ctr` | Next transmission counter (the nonce counter). The counter is 40-bit on the wire; this line prints its low 32 bits, which is exact below 2^32 |
| `ecc` | Double-ECC flash read faults seen since boot |
| `link`, `silent` | Link state (`linked` or `probing`), and consecutive minutes with no reply |
| `energy` | Energy state. Always `normal` in Stage 0 (USB power). |
| `time`, `utc` | `synchronized` or `unknown`, and the UTC seconds (0 when unknown) |
| `uptime` | RTC seconds since boot |

`#counts` has these fields:

| Field | Meaning |
|---|---|
| `pending` | Journaled readings not yet acknowledged |
| `lost` | Cumulative readings dropped by journal overflow (persisted across resets) |
| `burned` | Journal slots found torn or unusable since boot |
| `abandoned` | Cumulative records given up by NACK or the strike limit (persisted) |
| `sent`, `acked`, `no_ack`, `ack_rejects`, `sensor_faults` | Counters since boot. `acked` counts ACKs that matched a journal record. `ack_rejects` counts replies that failed authentication, plus NACKs that were not for the frame just sent. |
| `tx_fail_run` | Consecutive journal, counter or radio failures; the watchdog resets the board above 10 (review P7) |
| `stack_peak` | Most stack bytes ever used since boot. The stack is filled with a pattern at start-up and the deepest overwritten byte is found on demand (`App/stackmon.c`). The linker reserves 8192 B; `make stack` gives the worst-case estimate. |

Other lines:

| Line | Meaning |
|---|---|
| `#boot role=tx fw= reset= kat= freq= bw= sf= power=` | Printed at every boot. `bw` is the index (2 = 500 kHz). |
| `#sample epoch= seq= uptime= valid= rc= t= rh= time= utc= journal= pending= lost=` | One per minute. (Next release: the node samples every 15 s and the line gains `n=`, the minute's valid samples; `t`/`rh` are then the minute's mean, `rc` the last sample's result.) `t` and `rh` are the sensor values in 0.01 °C and 0.01 % (0 when `valid=0`). The journaled record comes from the draft-5 encoder (`ws_obs_encode`): `t` outside −40.00…125.00 °C goes out as INVALID, `rh` is clamped to 0–100 %, and `valid=0` sends both fields as INVALID (never omitted). `rc` is the sensor result (`App/sensor.h`): 0 ok, −2 address NACK (sensor absent or wiring), −3 read NACK, −4 CRC mismatch, −5 bus still stuck after recovery. `journal=ERROR` means the record could not be encoded or journaled. |
| `#fault kind= pc= lr= cfsr= hfsr= bfar= count=` | Both roles, after `#boot`, only if the previous run crashed (see Crash records) |
| `#sensor ok t= rh=` / `#sensor fault rc=` | Once at boot, from one test reading. |
| `#watchdog N failures in a row` | TX: more than 10 consecutive failures of journal append, counter reservation or `Radio.Send`; the watchdog then resets the board (review P7) |
| `#boot-retry: reset in 600 s` | TX: storage init or epoch reservation failed at boot; one automatic reset after 10 minutes (only if the self-test passed) |
| `#ack epoch= seq= found= time_sync= rssi= snr= pending=` | Authentic ACK. `time_sync=1`: the clock was set from it. |
| `#ack none epoch= seq=` | No reply within the 2 s window. The reading stays journaled, and this minute's backlog drain stops. |
| `#ack reject len= rssi= snr=` | A reply failed authentication |
| `#nack epoch= seq= reason= abandoned=` | Authentic NACK for the frame just sent; the record is abandoned. Reason 1 = collision, 2 = invalid (`ws_frame.h`). |
| `#nack ignored: …` | NACK that was not for the frame just sent |
| `#abandon epoch= seq= after 10 unanswered tries …` | Strike limit: the record was abandoned |
| `#link probing: …`, `#link probe unanswered; …`, `#link linked after N silent minutes` | Link-state changes (see Transmission policy) |
| `#diag sent pending= lost= torn= abandoned= no_ack=` | Health report (kind 4, 32-byte plaintext) sent. `torn` is `burned`. The report also carries the rejected-reply count, reset cause, link state, firmware build ID, the RSSI/SNR of the last authentic ACK, the crash count and the energy state (protocol.md section 4); this line does not print them. The gateway shows them in `/v1/status` (`node_diagnostics`). |
| `#time restored utc= sync_age=` | Time trust kept across a warm reset |
| `#busy previous exchange still running` | The minute's sample was journaled but not sent |
| `#kat pass\|FAIL`, `#wipe ok\|ERROR`, `#provisioned station= kcv= epoch_floor=`, `#unprovisioned: …`, `#test-hang: …` | Command replies |
| `#storm start ctr=`, `#storm writes= ctr= burned=`, `#storm-scrub dropped=` | TEST-FLASH-STORM progress (every 256 writes); boot cleanup of storm slots |
| `#error <what>` | `journal-read`, `counter-reserve`, `seal`, `radio-busy`, `journal-ack`, `tx-timeout`, `store-init`, `epoch-reserve`, `self-test failed; not transmitting`, plus the command errors `already-provisioned`, `usage: …`, `bad key`, `epoch-floor`, `provision rc=`, `unknown command` |

### Crash records (`App/fault.c`, both roles)

A crash (a Cortex-M4 HardFault, or an NMI other than a flash ECC error) used to stop the board
in an endless loop until the watchdog reset it, with no trace of why. Now the fault handler saves
a few registers in RTC backup registers DR5–DR11, which survive a reset as long as the board keeps
power, and resets at once (`reset=software`). The next boot prints a line like this one, from
`TEST-FAULT` on TX with release `45f43e78fe91` (`pc` and `lr` depend on the build):

`#fault kind=hard pc=0800109a lr=080008a7 cfsr=00008200 hfsr=40000000 bfar=20040000 count=1`

| Field | Meaning |
|---|---|
| `kind` | `hard` (HardFault; bus, usage and memory faults all end here) or `nmi` |
| `pc` | The instruction that faulted. Find it with `arm-none-eabi-addr2line -e build/<role>/stage0-<role>.elf <pc>` on the exact release, or in `objdump -d`. `ffffffff` means the stack pointer was not in RAM (likely a stack overflow) or the fault was an NMI. |
| `lr` | The link register at the fault: the return address of the most recent call (bit 0 set, Thumb). Often the caller, but not always: in the line above it points into `TIMER_IF_DelayMs`, which `fault_test` had just called. |
| `cfsr`, `hfsr` | Configurable and HardFault status registers (Armv7-M Architecture Reference Manual, system control block). Common `cfsr` values: `00008200` precise bus error with `bfar` valid; `00010000` undefined instruction; `00020000` invalid state (for example a call through a corrupted function pointer). `hfsr=40000000` (FORCED) means a bus, usage or memory fault escalated to HardFault. |
| `bfar` | Faulting data address; meaningful only when `cfsr` bit 15 is set |
| `count` | Crashes since the board last lost power |

`TEST-FAULT` reads address `0x20040000`, where no memory is mapped, so the expected record is
`cfsr=00008200 hfsr=40000000 bfar=20040000` with `pc` inside `fault_test`.

### RX console glossary (`App/app_rx.c`)

| Line | Meaning |
|---|---|
| `<hex>` | A received frame for the host (observation or health report) |
| `#rx obs rssi= snr=` | Follows each forwarded frame |
| `#rx drop len= rssi= snr=` | Received something that is not a current-draft observation or health report |
| `#rx crc len= rssi= snr= data=` | Bad reception: the header decoded but the payload CRC failed. `data` is the lowercase hex of all `len` (0–255) bytes the radio kept (empty when `len=0`). The gateway stores each in `rx_faults` and counts them; `tools/rx_faults.py` classifies the captures |
| `#rx hdr rssi=` | Bad reception: the header CRC failed, no payload. `rssi` is the channel RSSI read right after the failure |
| `#host reject len=` | A host line that is not a valid ACK/NACK hex line |
| `#tx timeout`, `#tx busy` | ACK/NACK transmission failed |
| `#alive uptime= forwarded= dropped= acks= diag= listening= relistens= uart_errors= stack_peak= crc_errors= hdr_errors= task_peak_us= task_peak= isr_peak_us= isr_peak= trace_drops=` | Every 60 s. `stack_peak` as on TX (`#counts`). `crc_errors`/`hdr_errors`: bad receptions since boot (`#rx crc`/`#rx hdr`). `task_peak_us`/`isr_peak_us`: longest task and interrupt since boot, with the name of the one that set it (`task_peak`, `isr_peak`: words such as `process`, `SUBGHZ_Radio`, not numbers). `trace_drops`: trace records lost. The gateway marks the receiver silent after 180 s without `#alive` or `#boot` (gap G12). `relistens`: times the radio was restarted after 5 minutes without any radio event (review P6). `uart_errors`: console receive errors, each followed by a re-arm (review P5). |
| `#watchdog radio not listening; re-arming`, `#watchdog console not receiving; re-arming` | Self-heal attempt before the watchdog may reset the board |
| `#relisten after N s without a radio event` | Radio put in standby and listening restarted (review P6) |
| `#status role=rx forwarded= dropped= acks= relistens= uart_errors=` | Reply to `STATUS`. `acks` counts ACK/NACK lines handed to the radio. |
| `#boot role=rx fw= reset= freq= bw= sf= power=`, `#test-hang: …`, `#test-fault: …` | Boot line and command replies |
| `#fault …` | As on TX: the previous run crashed (see Crash records) |

### Transmission policy (TX)

This is summarized from `App/app_tx.c`; the approved policy is in [`docs/radio-energy-policy.md`](../../docs/radio-energy-policy.md).
- **Each minute:** the live reading goes first, then at most 5 older pending readings (energy state NORMAL). The total is also capped at about 5 s of estimated radio time per minute. Each frame gets one 2 s ACK window. A missed reply ends that minute's drain.
- **Link probing:** after 3 minutes with no reply the link state becomes `probing`: only the live reading is sent, with no backlog. In SURPLUS and NORMAL (always, in Stage 0) it still goes every minute; only CONSERVE probes at 2, 4 and 8 minutes, then every 15 minutes (since `0f456040fe54`; `ws_link_may_send()` in `firmware/stage0.c`). All other readings stay journaled. Any reply returns the link to `linked`.
- **Health report** (kind 4): sent every 15 min and at each link-state change, also while probing (since `0f456040fe54`). It is fire-and-forget, with no journal entry and no ACK.
- **Strike limit:** a record that stays unanswered 10 times while the gateway answers other frames in the same exchange is abandoned (`#abandon`).

**Watchdog:** independent watchdog, ~8 s. It is refreshed only from the main loop, and only while the role shows real progress: TX samples every ≤150 s and no exchange runs >30 s; RX is listening or finishes a transmission in <5 s, with one re-arm attempt. The reset cause is printed on every boot.

TX runs a boot self-test (`kat=pass`, also on demand with `KAT`; `run_kat` in `App/app_tx.c`). The vectors are shared with `tests/test_frame.py` and `tests/test_obs.py` and were made directly with the `cryptography` library from the specified header and nonce. The test:
- encodes the known-answer observation (T −12.34 °C, RH 45.67 %) with the draft-5 encoder `ws_obs_encode`, seals it with counter 0x100000002, and compares all 42 bytes with the vector. This covers the encoder, the 8-byte header, the nonce and the 8-byte tag;
- opens a known ACK and a known NACK and checks every field, and checks that an ACK with a changed tag fails;
- checks that `ws_seal_kind` refuses counter 2^40 instead of truncating it.

A failed self-test means the board refuses to transmit.

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
| 0–31 (64 KB) | Firmware; the linker script enforces this (TX image 53,752 B, RX 31,696 B at release bc5e6ede429c; `docs/firmware-budget.md`) |
| 32 | Config: station ID, key, KCV. The magic double-word is written last |
| 33–34 | Monotonic log, A/B: boot epoch, counter reservations (blocks of 256), cumulative `lost`/`abandoned` totals. Recovery takes the maximum. Compaction writes its header last |
| 35–127 | Journal ring: 93 pages × 42 slots of 48 bytes (T/RH build) |

**Slot:** the observation plaintext rounded up to whole 8-byte double-words, then a commit double-word (magic + CRC-16 of the plaintext) and an ACK double-word. For T/RH: 26 → 32 + 8 + 8 = **48 bytes**, and (2048 − 8) / 48 = **42 slots** per page after the 8-byte page header.

**Capacity: 93 × 42 = 3,906 observations ≈ 65 h ≈ 2.7 days** of one-minute readings without an ACK. When full, the oldest page is erased and its unacknowledged records are counted in `lost`. Draft 4 had 40-byte slots, 4,743 observations, about 3.3 days. The agreed target was "about 4 days"; each slot needs a separately programmed ACK double-word, and the draft-5 record is 2 bytes longer, which pushes it past a double-word boundary. The 30-day/16 MB requirement remains H11 work (external SPI NOR).

**Page magic:** `"WSJ"` + the slot size in the low byte (`0x57534A30`, `WSJ0`, for 48-byte slots). At boot, a page with any other magic (a draft-4 `WSJ1` page, or a page from a build with another field set) is ignored and later recycled. It is never misread. Pending draft-4 records on the board are therefore dropped at the first draft-5 boot; the WIPE that the draft-5 release required erased the journal anyway.

### Field set of a build (`App/node_fields.h`)

One constant names the catalog fields that this build measures:

```c
#define WS_NODE_FIELDS (WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT)   /* Stage 0 */
```

Everything else follows at compile time: `WS_OBS_PLAIN_MAX` (the record length, 22 + the field widths; 26 B now), the frame length (+ 16 B), the journal slot size and slots per page (`App/node_store.h`), the page magic, and the airtime estimate per exchange. To add a sensor: add its `WS_F_…` bit here and fill its `o.code[…]` in `sample()` (`App/app_tx.c`); the catalog itself (`firmware/common/ws_obs.c`, `ws0/fields.py`) already defines all 21 fields. The gateway needs no change.

What a different field set does to the journal:
- if the slot size changes, the page magic changes, so **every journal page of the old build is ignored at the first boot and recycled**, and records still pending in it are never sent;
- if the slot size stays the same (a small addition: one 1-byte field makes 27 bytes, which still rounds up to a 48-byte slot), old pages are read, but each old record's CRC is checked over the new record length and almost always fails, so the record is counted as `burned` and not sent;
- either way: drain the journal (`pending=0` in `STATUS`) before flashing a build with another field set;
- capacity falls as records grow. For example, the full proof-of-concept field set (62-byte record) gives 80-byte slots, 25 per page, 2,325 records, about 1.6 days;
- the static asserts in `node_store.c` stop the build if a slot no longer fits the page magic's low byte (under 256 B) or a page.

Power-fail behaviour. Resets during flash writes were tested 70 cycles (G7 part A, pass, `evidence/g7-reset-during-write-2026-10-13/`). **True power removal has not been tested yet** (G7 part B, deferred; see `docs/failure-modes.md`).
- Each slot is committed by a final CRC double-word.
- A torn write reads back as erased, uncommitted, or a double-ECC error. `NMI_Handler` catches the ECC error, and the slot is counted as `burned`, never used. Exception: a torn **ACK** word counts as acknowledged, because the host had already committed the record.
- The epoch is reserved before the first sample of each boot.
- Counters are reserved in blocks before use, so a reset skips the rest of the block. Observed: counter 8 → 257 after a reboot (`docs/hardware/nucleo-wl55jc-bringup.md`, "Reboot behaviour").

## Known limits

The full failure analysis, the loss budget, and the ranked gap list are in [`docs/failure-modes.md`](../../docs/failure-modes.md).


- The key is stored in plain internal flash at RDP level 0 (anyone with SWD can read it). Stage-0 bench only.
- Time-sync accuracy: the node is set to the host's commit time, up to about 1 s behind. It is trusted for 6 h, then marked unknown.
- Time across resets: a warm reset keeps time trust (RTC backup registers DR3/DR4; ST's SysTime uses DR0–DR2). When the backup domain is cleared (simulated with a backup-domain reset, `docs/hardware/nucleo-wl55jc-bringup.md`, draft 4), the gateway reconstructs times from the always-present `uptime` field. Open: whether a real power loss clears it on this board (`docs/protocol-stack.md` §11.3.1).
- `LOW_POWER_DISABLE=1` (USB-powered Stage 0). Power work belongs to Stage 1.
- The SHT45 driver uses I2C2 on PA11/PA12 at 100 kHz with stuck-bus recovery. It is untested on hardware until the sensor arrives.
