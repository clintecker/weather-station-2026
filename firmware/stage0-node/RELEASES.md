# Stage-0 firmware releases

Each release is built from a clean commit (no `-dirty`), built twice from scratch with identical
hashes, flashed to both boards, and recorded here. H01 evidence must name a release from this file.

## How to cut a release

1. Commit everything. `git status --short` must print nothing, or the build is labeled `-dirty`.
2. Run `tools/fetch-vendor.sh`. It verifies every pinned vendor commit. Use xPack arm-none-eabi-gcc 15.2.1-1.1 (the Makefile `TOOLCHAIN` default).
3. In `firmware/stage0-node`, run `make clean && make ROLE=rx && make ROLE=tx`. Note the two `.bin` SHA-256 values printed at the end of each build. Each build also prints `flash budget (<role>): N of 194560 B` and fails above 90 % (`docs/firmware-budget.md`).
4. Run `make clean && make ROLE=rx && make ROLE=tx` again. Both `.bin` hashes must be identical to step 3.
5. Flash RX, then TX: `make ROLE=rx flash SERIAL=<RX serial>`, then the same with `ROLE=tx`. Check that both `#boot` lines show `fw=<12-character commit>`.
6. Add a section below with the commit, date, hashes, inputs, flash record and radio settings, and commit it.

**When the release changes a format** (the protocol version, the observation catalog, the health report, the journal slot or the flash layout; for example protocol version 5 to 6), steps 5 and 6 become these (the power telemetry spec [`2026-10-29-power-telemetry-design.md`](../../docs/superpowers/specs/2026-10-29-power-telemetry-design.md) section 4; it replaces `docs/protocol-design.md` section 7 for this and every later format change). The TX and RX roles share `WS_FRAME_VERSION`, so a board left on the old version drops every frame of the new one.

| Step | Do | Check |
|---|---|---|
| a | **Drain the journal** on the old release: keep the old gateway running until the TX console shows `pending=0` (`STATUS`, `#counts`). | `pending=0`. A WIPE, and the new journal slot size (a new page magic), discard pending records for good. |
| b | **WIPE** the TX: `WIPE ERASE-ALL-NODE-STATE` (Clint runs it). | `#wipe ok`; the TX reboots with solid red LED3. The counter, epoch and `lost`/`abandoned` totals stay. |
| c | **Flash both boards from the same release**: RX, then TX (`make ROLE=rx flash SERIAL=<RX serial>`, then `ROLE=tx`). | Both `#boot` lines show the same `fw=`; TX `kat=pass` (the known-answer vectors change with the version byte). |
| d | **`init` a new run directory** (`python -m ws0 init …`). The old run directory and its database stay with the old release; there is no migration. Never reuse the live run directory or an evidence directory. | A new key; the old directory is untouched. |
| e | **Provision** the TX: `python -m ws0 provision-node` with the new key. | `#provisioned station= kcv=`; the epoch floor comes from the new run's empty database (0). |
| f | **Start the gateway** of the same release on the new run directory (`RECORD_VERSION` matches `WS_FRAME_VERSION`). | Seq 0 of the new epoch is stored and acknowledged, 0 rejections. |
| g | **Record the release below** with, besides step 6's items: the **protocol version**, the **field set** (`WS_NODE_FIELDS` and its plaintext length), the **power wiring phase** (`WS_POWER_PROFILE`: A, B or C) and the **monitored rails** (which of battery, load, charger input, solar and USB-C the build measures), the I2C profile (`WS_I2C_MUX`), the old and new run directories, and the release notes' one-time actions (for example Home Assistant entities to remove). | The entry names all of them. |

A release whose power wiring changes (a new phase, a moved jumper or shunt) also records the bench acceptance drill (power spec section 12.2) and its new evidence run directory.

**Which hashes are reproducible:** the `.bin` hashes are the release identity. They match any clean build of the same commit with the same inputs; a rebuild of a07f498 in another checkout matched (see `docs/hardware/nucleo-wl55jc-bringup.md`, Office session). The `.elf` hashes are informational only. The Makefile compiles with `-g3`, so the ELF debug info embeds absolute source and toolchain paths, and the ELF hash changes with the checkout location. Every build also embeds the commit (`-DWS_FW_VERSION` from `git describe`), so a later commit never reproduces an earlier release.

## Next release (not cut yet): power telemetry, protocol version 6

The branch `feat/power-telemetry` changes formats, so its release follows the format-change steps
above (drain, WIPE, flash both boards, new run directory, provision, record). What it changes
(power spec [`2026-10-29-power-telemetry-design.md`](../../docs/superpowers/specs/2026-10-29-power-telemetry-design.md)):

- **Protocol version 6**: byte 0 is 0x61 (observation), 0x62 (ACK), 0x63 (NACK), 0x64 (health
  report). Version 5 boards and gateways drop its frames; the records wait in the journal until both
  ends match. Time sync becomes version 7.
- **Observation catalog version 2**: new fields 26 `load_mv`, 27 `load_current_ma`, 28
  `charger_input_mv`, 29 `solar_mv`, 30 `solar_current_ma`, 32 `usb_mv`, 33 `usb_current_ma`;
  bitmap bit 31 is EXT, followed by a 2-byte extension bitmap; field 12 `batt_current_ma` is now
  1 mA and sent; fields 11 and 13–16 have corrected meanings (the cell voltage from the gauge; energy
  from ΔQ × VCELL; the sign fixed, see the addendum under `04fcc656938d`); fields 17
  `soc_gauge_pct` and 18 `charger_pins` are retired (no longer sent).
- **Health report version 6**: 64 bytes (80 B on air): last crash PC, boots since power-up (DR12),
  TX timeouts, I2C recoveries, MCU supply (VDDA from VREFINT), power-monitor die temperature, gauge
  SOC and rate, the charger status byte, the fitted byte (byte 51: which slots the build has a source
  for, 0x2F in phases A and B, so a `null` is told apart as "not measured" or "sensor fault") and
  slots for charger-reported values (phase C). A due report's airtime is reserved from the minute's
  cap.
- **Field set and journal**: the node field set is 77 B (93 B on air) in every power phase; the
  journal slot grows from 80 to 96 B (21 a page, 1,449 records, 24.15 h) and the page magic changes,
  so the first boot recycles every old page.
- **Node firmware**: `WS_POWER_PROFILE` (phase A default; B builds; C stops), `App/power_acq.c`
  (INA228 rails, MAX17048, the board ADC, CHG/PGOOD), `firmware/common/power_regs.c` (shared with
  i2cscan and benchlink), the four-channel ADC sequence (vane, ISET on PB1, charger input on PA10,
  VREFINT), CHG edges on EXTI10, `WS_I2C_MUX` 0 (the STEMMA QT hub, default), the DR12 boot counter
  (`fault_boot_note`). The energy state stays NORMAL (thresholds deferred).
- **WSMP**: registry version 2 (quantities 18–24, types 8 battery and 9 power rails; type 5 frozen),
  WSMP 1.1 snapshot quality "not fitted", `WSMP_RADIO_BUDGET` 60.
- **Local serials of ports 5 and 8 change**: port 5 goes from type 5 to type 8
  (`0x575300000505` to `0x575300000508`) and port 8 is new (`0x575300000809`, type 9)
  (`App/wsmp_local.h:48-54`). Each starts a new counter series (WSMP-C3).
- **Home Assistant cleanup**: the retained discovery configs of `soc_gauge_pct` and `charger_pins`
  from older runs stay in the broker; remove those two entities in Home Assistant by hand. The new
  health-report entities use their own unique-ID namespace, are advertised only for the keys the
  build measures (8 in phase A) and go unavailable 1,900 s after the newest health report
  (`…/diagnostics/availability`).
- **I2C timing**: `I2C_TIMING` is `0x20323E5D` (SDADEL 2, 146 ns data hold) in the node, i2cscan and
  benchlink, for the INA228 SDA strap of the phase B USB-C rail (power spec section 9.2).
- **Sizes, measured 2026-10-29 on the uncommitted branch** ([`docs/firmware-budget.md`](../../docs/firmware-budget.md)):
  TX 88,160 B (78.3 %, over the 75 % headroom target, under the 90 % guard), RX 34,904 B (31.0 %).
  Stack bound: TX 6,056 B (74 %), RX 2,780 B (34 %). `make waits`: OK on both, no heap. The release
  entry records its own numbers.
- **The entry records**: protocol version 6, field set `WS_F_WSMP_BENCH` (77 B), power wiring phase
  A (`WS_POWER_PROFILE` 1, the official bench wiring of 2026-10-28/29), I2C profile hub
  (`WS_I2C_MUX` 0), monitored rails: battery (current, counters; voltage from the gauge), load voltage
  (OUT) and charger input voltage; load current, solar and USB-C not measured in phase A.

## 04fcc656938d — 2026-10-19 (bench, review fixes; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,832 B) | `63cc60294ab098a4694c12b2e6374de0c7242cc6325ee70e7efd13b7028a82a7` |
| `build/tx/stage0-tx.bin` (74,464 B) | `c6f48dd4a12ad435270a4f35451b434c6a6d35932df1f8d0a80586e4064eee6c` |

- Source: commit `04fcc656938d`. Changes since cc2766a38c61, from a four-reviewer review of the
  branch (GitHub issues #1–#11):
  - d3f84bb: modules start their windows and schedules at init. A warm reset late in the clock's
    range had stopped every module until the clock wrapped. 6925f2a fixed the first window.
  - The INA228 charge and energy come from its accumulators (#2). The ADC calibrates (#3). The
    cup input filters bounce (#4). Each still needs its bench check.
  - Map, host, bus and module fixes (#5, #6, #11): fault qualities are missing, admission is
    pure and checks the digest, a saturated window is long, I2C bus errors are bus faults, and
    the gauge, vane and rain module items.
  - Registry tables are stored once (#7, −176 B). Serial ports are held exclusively (#8).
  - CI is green again: a GCC sign-compare in a fuzz target, and a reverse DNS lookup at HTTP
    bind.
- Inputs: as a07f498. Flash budget: TX 66.1 %, RX 30.9 %. Stack bound: TX 6,360 B (78 %).
  `make waits`: OK on both, no heap.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed by Clint: d3f84bb (TX only, epoch 2, seq 0 had its temperature: 22.30 °C), then
  04fcc65 (TX only, 2026-10-19 ~17:28Z). The RX stays on cc2766a38c61, and its code did not
  change. TX after the flash: `fw=04fcc656938d`, `kcv=6e30cf`, `kat=pass`, `epoch=3`,
  `check_fails=0`. Epoch 3 seq 0 was acknowledged at 23.34 °C (partial: the first window).
  The gateway (`run-d7`) shows 0 rejections across epochs 1–3.
- Not an H01 release: radio settings are bench values.

### Addendum 2026-10-29: battery current sign and the INA228 bench check

- **The battery current sign of this release is reversed for the official wiring.** On 2026-10-28/29
  the bench telemetry link (`firmware/benchlink`, plain LoRa every 5 s) logged the power breadboard and
  found the convention: with the official orientation (the cell on the INA228's VIN+, the charger's
  LIPO terminal on VIN−; [`../benchlink/README.md`](../benchlink/README.md), "Wiring") the INA228
  counts VIN+ to VIN− as positive, which is current **out of** the cell. This release adds every
  positive CHARGE delta to "charge in" and its energy to "energy in" (`App/mod_power.c:145-150` at
  `04fcc656938d`, unchanged up to c7e8860). So with that orientation fields 15 and 16
  (`charge_in_mah`, `charge_out_mah`) and 13 and 14 (`energy_in_mwh`, `energy_out_mwh`) of this
  release count a discharge as a charge and the reverse. The energy counters integrate the ENERGY
  register, VBUS × current, and the official wiring puts VBUS on the charger OUT, not the cell; field
  11 (`batt_mv`) of this release is the INA228 VBUS of whatever net its jumper sensed (OUT in the
  official wiring). The finding came from benchlink, not from this node release; this file does not
  record which stored version 5 records, if any, were taken with that orientation, so read every
  protocol version 5 power value with this in mind. The fix ships with protocol version 6 (power spec section 3.1): the battery rail's
  sign is −1 in the rail table (`App/power_config.h`), so + is into the cell; field 11 comes from the
  MAX17048 on the cell; energy is ΔQ × VCELL.
- **INA228 bench check: still open.** The charge and energy accumulators of this release (#2) have
  not been checked with current through the shunt. On 2026-10-28/29 the cell sat in the charger's own
  LIPO socket, so the INA228's shunt carried no current (`ishunt_ma` about 0 while the cell charged
  and discharged). The shunt in the battery path is the part of the phase A wiring still to prove: phase
  A exit criteria 3 and 4 (the node-against-benchlink acceptance drill and a 1 A charge that terminates
  normally with the shunt in the path; power spec sections 2 and 12.2). The shunt value (15 mΩ) is
  nominal: build-sheet power check 3 verifies it against a series reference (within 2 % + 2 mA), and
  only a failed check replaces it (power spec section 8.6, amended 2026-10-29).

## cc2766a38c61 — 2026-10-19 (bench, DATAVANE5K local modules, new flash layout; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,832 B) | `2ee8dfdec48fb6addd68d51e5c3ef3ba4032e97bcab481465037fcb1ffcc4f6a` |
| `build/tx/stage0-tx.bin` (73,976 B) | `874b0b2cffe2c70173584717276b9023eb6970870441c6b168a827dbd2b93bca` |

The `.elf` hashes were not recorded. They are path-dependent and informational only.

- Source: commit `cc2766a38c61`. Changes since 260c9ccbe938:
  - Flash layout: firmware pages 0–54 (110 KB), journal 55–124, meta 125–126, provisioning 127.
    The budget base is now 112,640 B.
  - The TX reads its sensors as DATAVANE5K (WSMP 1.0) local modules (`docs/module-protocol.md`):
    a shared interrupt-driven I2C bus, seven local modules, the station host (presence, admission,
    latch) and a map onto today's catalog. The old sensor driver is removed.
  - Console: `MODULES`, `SENSOR rain on` and `SENSOR rain off`.
- Inputs: as a07f498 (vendor pins verified). Flash budget: TX 65.7 %, RX 30.9 %. Stack bound: TX
  6,360 B (78 %). `make waits`: OK on both; no heap.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-19 by Clint, with the flash-layout migration (`docs/runbook-moving-boards.md`,
  "Changing the flash layout"): `run-d6` archived as `run-d6-archive-2026-10-19`; RX → board B
  `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`; TX `WIPE`; `ws0 init run-d7`;
  TX provisioned with a new key (`kcv=6e30cf`, `epoch=1`); gateway started on `run-d7` at
  15:07:13Z.
- Bench check (only an SHT45 on the bus): epoch 1 seq 0–2 accepted, 0 rejects, no
  `counter-regression` lines. Seq 1: 20.88 °C, 33.99 %. Seq 2: 20.89 °C, 34.2 %, quality valid.
  `#modules air_th=active … wind=active rain=absent`.
- Two faults found on the bench:
  - Seq 0 had no temperature (`sensor_fault`). The modules opened their first window at clock 0,
    but the clock keeps counting across a warm reset. The first window looked longer than 90 s, so
    the map sent no means. Fixed in the next commit (`test_first_reading_after_a_warm_reset_is_a_minute`).
    This release keeps the fault: one reading after each reset.
  - `wind=active` with no vane wired. PB2 floats without the vane's 10 kΩ pull-up, so its reading
    looks like a vane position. Not a firmware fault: see `docs/hardware/bench-station-wiring.md`, section 8.
- Not an H01 release: radio settings are bench values.

## 260c9ccbe938 — 2026-10-16 (bench, named constants, literate sources; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,832 B) | `daa9bf1dd9cdef93c15966509d6a1247ff5ebccd435206528764ce105b70f063` |
| `build/rx/stage0-rx.elf` (path-dependent) | `bb7af038655fe5dfe63c17ea1228a65d31a87a93d92abe8cd83968919d488ad2` |
| `build/tx/stage0-tx.bin` (58,264 B) | `d9ba8546abfa0b96db890a227f58f899bc7b048c9446d7a9f36517371ebe36b0` |
| `build/tx/stage0-tx.elf` (path-dependent) | `cf2281d879358cd73cb442bb2456c29c87fd84a866c632222f1807994c4b3d8f` |

- Source: commit `260c9ccbe938`. Changes since 809230951ae1:
  - Magic numbers replaced by named constants and helpers across the firmware, the gateway and the
    tests; packing uses cursor writes in field order. Frame and flash formats unchanged.
  - Review and gap IDs removed from comments and live docs.
  - Literate sources (`*.lit.md`, tangled by `tools/tangle.py`) for node_store, tx_exchange, app_tx,
    sensor, app_rx, ws_frame and ws_policy, and for the gateway's protocol.py and gateway.py. The
    generated code is the committed code.
  - Fixes found on the way: a refused counter reservation now still feeds the link and strike
    policy with the minute's answers; a health report the radio refused stays due; its refused
    counter counts as a transmit failure; `ws_key_check` wipes the AES block; `ws_open_reply`
    returns `WS_FRAME_EINVAL` for a bad station argument. New tests for each, and for five gaps a
    mutation pass found.
- Inputs: as a07f498 (vendor pins verified). Flash budget: TX 88.9 %, RX 53.1 %. Stack bound: TX
  5,784 B (71 %), RX 2,652 B (32 %). `make waits`: OK on both; no heap.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-16 ~19:06Z: RX → board B `0016001E4142500E20353451`, TX → board A
  `003B00194142500E20353451`; gateway restarted on `run-d6` at the same commit. TX after flashing:
  `fw=260c9ccbe938`, `kcv=e03059` (key kept), `kat=pass`, `epoch=46`, `ctr=14081`, time trust
  restored, `check_fails=0`; `#timing` task peak 53 µs, interrupt peak 44 µs, program 93 µs.
- Bench check 19:07–19:09Z: epoch 46 seq 0–2 stored valid and acknowledged; the reading pending at
  the flash (epoch 45 seq 214) delivered from the journal. RX `#alive` at 120 s: forwarded 4, acks 3,
  no drops or failed receptions, task peak 401 µs (`console_task`), interrupt peak 216 µs.
- Not an H01 release: radio settings are bench values.

## 809230951ae1 — 2026-10-16 (bench, timing attribution; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,832 B) | `282e04eecba988a03ed10ba8dbbf38da5bcfd9f5013e57e60fd56ac50017c075` |
| `build/rx/stage0-rx.elf` (path-dependent) | `feb187ef903b7476ff03d555ff4b3fd41f070340bd8e7fb1f8ba6c3617a759b2` |
| `build/tx/stage0-tx.bin` (58,192 B) | `0ae2c1eb16636bc0d90d984efc31329572ab45f633734eab0762ec465b3f14f0` |
| `build/tx/stage0-tx.elf` (path-dependent) | `70abf0b144efbc868be6338bbaa6524679b488e0ad93f06cc1fefcdcd077ca17` |

(Table repaired 2026-10-16: the four hashes had been recorded in one cell. A clean rebuild of
809230951ae1 reproduced both `.bin` hashes; the `.elf` rows keep the recorded order, rx then tx.)

- Source: commit `809230951ae1`. Changes since 7eb79f64f2bd:
  - Timing attribution (busymon): a task's peak is its own time with the interrupts that ran meanwhile taken out (interrupt time summed once per outermost handler), named after its slowest timed step (`process.alive`, `.relisten`, `.listen`, `.forward`, `.crc`; `report.journal`, `report.send`); the wall time is `task_wall_us` (TX `#timing`, RX STATUS). Host-tested (`firmware/test_busymon.c`).
  - The RX's 1.7-1.9 ms `process` peak explained and removed: it was every `#alive`. Measured on the RX with a throwaway bench build (not released): the whole-RAM stack high-water scan 1,472 µs, line formatting ~260 µs. The scan now reads 256 words (1 KB) per report, at most one pass (~17 reports) behind, seeded by one whole scan at boot.
- Inputs: as a07f498. Flash budget: TX 88.8 %, RX 53.2 %. Stack bound: TX 5,744 B (70 %), RX 2,652 B (32 %). `make waits`: OK on both.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-16 ~15:45Z to both boards (`run-d6` gateway running). Before (release d1998d142fd0, same instrumentation, whole scan): RX task peak 1,740-1,744 µs `process.alive`, every report. After: RX task peak 391 µs (`console_task`, an ACK line), interrupt peak 219 µs, `stack_peak=272` from the first report.
- The lab rehearsal of 7eb79f64f2bd was ended at 16 h (Clint): evidence/h01-rehearsal-2026-10-15/. Not an H01 release: radio settings are bench values.

## 7eb79f64f2bd — 2026-10-15 (bench, strike rule A, Power of Ten; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,248 B) | `67de0491b97f03b453bf9d655281cb4882d5ec03296fa305796b765a4ef6e7f0` |
| `build/rx/stage0-rx.elf` (path-dependent) | `c16075519b94b9892d2bbd812f3e995f03df54b76c80b95bd8720babaa7b0b38` |
| `build/tx/stage0-tx.bin` (57,816 B) | `cc5c662ab6a9e537429504d6de21c291fac0f8bd42ee8d081691727b8a064e44` |
| `build/tx/stage0-tx.elf` (path-dependent) | `77779d55378ee0ee31ec95f3f0ce09b2434bdada7cf378b50c4e8c199e45c1c5` |

- Source: commit `7eb79f64f2bd`. Changes since ddb469680a30:
  - Strike rule A (Clint): a record earns a strike only when a frame sent after it in the same exchange is answered; after a missed reply the drain sends one more frame (a second miss in a row stops it). A lone refused record is retried each minute, never abandoned by luck.
  - NASA/JPL Power of Ten pass (docs/power-of-ten.md): link-time seams instead of our own function pointers; narrowed TX node state (the AES key only in `tx_exchange.c`); every loop bounded (`tools/loop_bounds.py`, in CI); `WS_CHECK` run-time checks with a defined recovery (35 sites; `check_fails`/`check_first` on TX `#counts` and RX STATUS); every discarded result explicit; ~20 more warning flags, Cppcheck in CI, a no-heap link check. Reviewed; review fixes included.
- Inputs: as a07f498 (vendor pins verified). Flash budget: TX 88.2 %, RX 52.3 %. Stack bound: TX 5,744 B (70 %), RX 2,588 B (32 %). `make waits`: OK on both; no heap.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-15 ~22:33Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`; gateway restarted on `run-d6` at the same commit. TX after flashing: `fw=7eb79f64f2bd`, `kcv=e03059` (key kept), `kat=pass`, `epoch=42`, `ctr=12033`, time trust restored, `pending=0`, `check_fails=0`; `#timing` task peak 51 µs, interrupt peak 43 µs, program 93 µs.
- Bench check 22:35Z: epoch 42 seq 0 and 1 stored and acknowledged. RX `#alive`: forwarded 2, no failed receptions, task peak 387 µs (`console_task`), interrupt peak 216 µs. (The previous RX release's last `#alive`, after 103 min: `hdr_errors=5`, `dropped=1`, `frames_lost=0`, task peak 1,746 µs in `process`.)
- 24-hour lab rehearsal started 2026-10-15T22:37:00Z (evidence/h01-rehearsal-2026-10-15/). Not an H01 release: radio settings are bench values.

## ddb469680a30 — 2026-10-15 (bench, refactored and reviewed; protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (34,080 B) | `73e8423ba987ab3ce2cad5e5e632218fc3148054279dcf9dee99dbd4f7a7e82e` |
| `build/rx/stage0-rx.elf` (path-dependent) | `db5df4d7b5969188828e3251e54abcff7b7340da1f0dadd32913fb3f02dc252f` |
| `build/tx/stage0-tx.bin` (57,048 B) | `718278c804fbc206d15a2a0d1a3062d3c7f11c3120cbdb472f11159d0d3fb046` |
| `build/tx/stage0-tx.elf` (path-dependent) | `fdf9842a0d617b61673f0c1256545abe34804ea6ca9f8721ad868f664cfcd819` |

- Source: commit `ddb469680a30`. Changes since 586001994b09:
  - RX: independent whole-file review, all findings fixed with failing tests first (dead radio reset after two quiet 16-min relistens; one ACK on air at a time; standby before listening after a TX timeout; full payload length before listening; `#boot` on a fresh line; a line that lost a character or has a non-printable byte discarded whole; stalled console output fails the health check; `frames_lost` and `#rx frame-lost`; failure lines limited to 20 a minute; TEST-* out of a field build; watchdog after the console).
  - Refactor (both roles): shared clock, event posting and bench modules; `app_tx.c` split into exchange, policy (`firmware/common/ws_policy.c`, unit-tested), time, console and self-test; every function in our C at most CCN 10 and 60 lines, no duplicated code (`tools/code_shape.sh`, in CI).
  - Flash only with the radio idle, without exception: a reading made during an exchange is held in RAM and journaled when the radio goes idle; a stuck exchange is stopped and its held readings journaled before the watchdog reset.
  - Review of the refactored firmware: every main-loop radio command runs with the radio interrupt masked (ST's HAL refuses a radio interrupt's commands while a main-loop command holds the driver); the first frame of an exchange also waits for the gap; two benign races dropped instead of counted as unexpected; TEST-FLASH-STORM bench-only and capped.
  - Host test strength: TX 91/93 and RX 46/47 planted bugs caught; one shared simulation core under all harnesses.
- Inputs: as a07f498 (vendor pins verified). Flash budget: TX 87.1 %, RX 52.0 %. Stack bound: TX 5,648 B (69 %), RX 2,588 B (32 %). `make waits`: OK on both.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-15 ~20:50Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`, gateway `serve --directory run-d6` left running. TX after flashing: `fw=ddb469680a30`, `kcv=e03059` (run-d6 key kept), `kat=pass`, `epoch=41`, `ctr=11777`, time trust restored after the reset (`time=synchronized`), `pending=0`; `#timing` task peak 52 µs (`sensor_task`), interrupt peak 43 µs (`I2C2_EV`), program 93 µs.
- Bench check 20:52Z: epoch 41 seq 0 and 1 stored and acknowledged, RX -27 dBm / SNR 13. RX `#alive`: forwarded 2, dropped 0, no failed receptions, `frames_lost=0`, task peak 389 µs (`console_task`), interrupt peak 219 µs (`SUBGHZ_Radio`), `trace_drops=0`.
- Not an H01 release: radio settings are bench values. Pending decision: the strike rule (review M2: strikes cannot tell a refused record from a lossy link); this release keeps the existing rule.

## 586001994b09 — 2026-10-15 (bench, interrupt-driven, protocol draft 5)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (33,224 B) | `deb34fc06eb2217593dfc1f909dadd3cdc266cd1ffda1f1848363fa4bc24dafb` |
| `build/rx/stage0-rx.elf` (path-dependent) | `884fd5eed59c69706b2d212cf988080e02e57f13c1414993a1b0ebb0851d5834` |
| `build/tx/stage0-tx.bin` (55,744 B) | `6d88406f25323050fa5346d6364ee1b788a06ea8f2409ea940a7b712f5b50a65` |
| `build/tx/stage0-tx.elf` (path-dependent) | `a5ecbd5ff5f15b74138b2ee5f5069e0874696e17e4ffd44bbc3bd1c27891e35e` |

- Source: commit `586001994b09`. Changes since bc5e6ede429c: 15-s T/RH sampling with a minute summary (35-byte plaintext, 56-byte journal slots: a new journal format; older pages are ignored); review fixes FW2-FW8; TX flash 54,832 -> 51,080 B before the rework; key wipes; and the **interrupt-driven rework** (docs/firmware-event-model.md): no run-time busy-wait (`make waits`), explicit TX exchange state machine with the firmware's own ACK window, interrupt-mode SHT45 driver, run-time timing (`#timing`, RX `#alive`), every failed reception logged with its bytes (`#rx crc`, `#rx hdr`), flash-writing commands refused during an exchange. Reviewed by five independent reviewers before release.
- Inputs: as a07f498 (vendor pins verified by `tools/fetch-vendor.sh`). Flash budget: TX 85.1 %, RX 50.7 %. Stack bound: TX 5,952 B (73 %), RX 2,588 B (32 %).
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-15 ~19:00Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451` (on the gateway Mac's USB for flashing). TX first booted with the run-d5 key (`kcv=5618eb`, epoch 39, ctr 11265, `kat=pass`); one reading pending from the old firmware (taken after the rehearsal, while the gateway was stopped) was not carried over by the new journal format.
- First hardware timings (`#timing`, TX): flash page erase **22,057 µs**, double-word program **93 µs**, longest task 56 µs (`sensor_task`), longest interrupt 39 µs (I2C2_EV).
- Fresh start (Clint): `run-d5` archived intact as `run-d5-archive-2026-10-15/`; new run directory `run-d6` (new key, same station 1, same MQTT settings). TX `WIPE ERASE-ALL-NODE-STATE` run by Clint (`#wipe ok`, counter kept at 11521), then `provision-node`: `kcv=e03059`, `epoch=40`, `ctr=11521`, `kat=pass`, `#sensor ok t=2343 rh=5191`.
- Bench check 19:08Z: gateway `serve --directory run-d6`; the first two readings (epoch 40, seq 0 from the journal and seq 1) stored and acknowledged, RX -29 dBm / SNR 13. Startup rejections: 4 `InvalidTag` (old-key frames the RX had queued) and 1 partial line at port open.
- Not an H01 release: radio settings are bench values.

## bc5e6ede429c — 2026-10-14 (bench, protocol draft 5, SHT45 wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (31,696 B) | `27d6a013b442fffcf8d5d2e8c7aa9a1d2b8e55db49d33cab6119ca44650ffa6c` |
| `build/rx/stage0-rx.elf` (path-dependent) | `77ed90ab4f7a9c73de17bcb1954cbd07c3ffc5e7916eab078c99dfba8b9127ff` |
| `build/tx/stage0-tx.bin` (53,752 B) | `89726d99a486e6c31600ac643e4bf108911d57e753d1f4f025118f83aac0c03b` |
| `build/tx/stage0-tx.elf` (path-dependent) | `66bb1327d3a617d697d1050ba6bf6692894d818e714e5e26ae077cda6bb3ae4a` |

- Source: commit `bc5e6ede429c`. **Protocol draft 5** (`docs/protocol-draft5-design.md`, commits 6f52a51..bc5e6ed): 8-byte header and CCM tag, u40 counter (refused past 2^40-1 in the allocator and the sealer), u16 station, 33-byte ACK/NACK, byte-aligned observation with a field bitmap (T/RH build: 26-byte plaintext, 42-byte frame), 32-byte health report (build ID, ACK RSSI/SNR, crash count, energy state). Journal slots sized by the build's fields (48 B, 3,906 records); page magic "WSJ" + slot size. RX forwards frames up to the largest catalog frame (`hex_print` truncated above 64 B before).
- Built from a clean `git worktree` of the commit (the main checkout had uncommitted docs). Inputs: as a07f498. Flash budget: TX 82.0 %, RX 48.4 %. Stack bound: TX 80 %, RX 27 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Release procedure for the format change: TX `WIPE ERASE-ALL-NODE-STATE` (run by Clint; `pending=0` checked first, counter kept: 8622 before, 8705 after), flash, new run directory `run-d5`, `provision-node` with a **new key**.
- Flashed 2026-10-14 17:58Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX after provisioning: `fw=bc5e6ede429c`, `kcv=5618eb`, `kat=pass` (draft-5 encoder vector, sealed frame, 2^40 refusal), `epoch=35`, `ctr=8705`, `#sensor ok t=2607 rh=4059`.
- Bench check 17:59Z: on air a 42 B observation and a 33 B ACK; the live reading and the one taken before the gateway started both stored (version 5, T/RH valid, availability per field); 2 accepted / 0 rejected, `alarm` null, counter mark 8708, `replays=0`; RX `uart_errors=0`.
- Not yet an H01 release: radio settings are bench values; the sensor-unplug check and the first health report on this release are still to be seen.

## 45f43e78fe91 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (31,584 B) | `d81863d8641c939271b611bec9cd67003534bb5afd85e652820219f1afbd6956` |
| `build/rx/stage0-rx.elf` (path-dependent) | `520b795909c553b2a3c8a2fb325e7bc25e7194eb1ca03e53424b3d5aacc7a113` |
| `build/tx/stage0-tx.bin` (52,896 B) | `b254929cd3f507fec5ba43d7bc2fd3476941b48d4ac21836b4e9ee18ba08bd68` |
| `build/tx/stage0-tx.elf` (path-dependent) | `f074ba8e02397bc54be4f5ec0433267c9d93d3db609435198dc42a40c1665913` |

- Source: commit `45f43e78fe91`. Changes since 9e3d38f08e8b: strict warnings with `-Werror` for our C; stack reservation 2 → 8 KB after a worst-case bound (`make stack`: TX 6,408 B, RX 2,020 B); Mbed TLS cipher layer removed (no heap use, −1.7 KB); `stack_peak` reported; TX `STATUS` split into `#status` + `#counts` (the single line was truncated); HardFault/NMI crash records (`#fault`, `TEST-FAULT`); `_Static_assert`s on frame and flash geometry; console parsing moved to `firmware/common/ws_console.c` (fuzzed). Protocol and flash layout unchanged (draft 4).
- Inputs: as a07f498. Flash budget: TX 80.7 %, RX 48.2 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13 21:31Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=45f43e78fe91`, `kcv=b7142e`, `kat=pass`, `epoch=32`, `ctr=7939`, `stack_peak=1240`.
- Crash test: `TEST-FAULT` on TX gave `#fault kind=hard pc=0800109a lr=080008a7 cfsr=00008200 hfsr=40000000 bfar=20040000 count=1`, with `reset=software` at once; `pc` is the faulting load in `fault_test` (`fault.c:48`). It also gave `epoch=33` and `ctr=8193` (both moved forward). On RX: the same record, with `pc=080010fa` (its `fault_test` load).
- Gateway after the restart: 6 accepted / 0 rejected, `alarm` null, counter high-water mark 8200, `counter_regression=0`, RX `relistens=0 uart_errors=0 stack_peak=392`.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

## 9e3d38f08e8b — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (30,912 B) | `c7239804707461eceee901fea1252c9cbc3e4fdba0324162acd9fed8e14bfa5c` |
| `build/rx/stage0-rx.elf` (path-dependent) | `511fed32ff6dd5c4bc6b5ace7e5024a906a7c8c98c31a9f5b4497c4514549cc3` |
| `build/tx/stage0-tx.bin` (53,880 B) | `91d8e5479fb44295e08006e0e1243fcb38f510d6cdf6a15afc9cb6a7193f4135` |
| `build/tx/stage0-tx.elf` (path-dependent) | `63535ce267939f3c9b615e7189a4c34c866461a94d5604643086ddc63487564f` |

- Source: commit `9e3d38f08e8b`. Changes since 0f456040fe54: flash store over a `ws_flash` ops struct with host power-cut tests (P3) and four store fixes they found; UART receive errors re-armed and counted (P5); RX relisten after 5 silent minutes (P6); TX consecutive-failure watchdog and boot retry (P7). Protocol and flash layout unchanged.
- Inputs: as a07f498. Flash budget: TX 82.2 %, RX 47.2 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=9e3d38f08e8b`, `kcv=b7142e`, `kat=pass`, `epoch=31`, `ctr=7683`. Gateway: 2 accepted / 0 rejected, `alarm` null, counter high-water mark 7684, RX `relistens=0 uart_errors=0`.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

## 0f456040fe54 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (30,360 B) | `5dd14d59c3c053d94146808422c8d82b865ae34ff52a9a16780def7d7e65629a` |
| `build/rx/stage0-rx.elf` (path-dependent) | `39244ffa8354c93d75ed7cb437d834aff39802bacb5c32fc25eb6d200fcb13b2` |
| `build/tx/stage0-tx.bin` (53,176 B) | `0bd4e94575634bf792993d73c5fafff67f1bc20624445de98625da67c0057f60` |
| `build/tx/stage0-tx.elf` (path-dependent) | `8a920d899646d27da38d7af8ba6e7524dd57a2e1f144a49b8e05f4502855b38e` |

- Source: commit `0f456040fe54`. Changes since a07f498: sensor `rc=` on `#sample` and `#sensor` boot check; internal I2C pull-ups; I2C bus-recovery STOP fix (`ws_i2c_recover`); WIPE keeps counter and epoch (gap G17); strict PROVISION parser with key cleared from console buffers; while probing, SURPLUS/NORMAL send the live reading every minute (only CONSERVE backs off); health reports also while probing. Protocol and flash layout unchanged (draft 4).
- Inputs: as a07f498 (`tools/fetch-vendor.sh`, xPack arm-none-eabi-gcc 15.2.1-1.1, OpenOCD 0.12.0).
- Reproducibility: two clean builds (`make clean`, then both roles) gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=0f456040fe54`, `provisioned=1`, `kcv=b7142e` (office key kept across the flash), `kat=pass`. First minute: `#sample … valid=0 rc=-2` (no sensor wired: address NACK, as intended), both pending readings ACKed, gateway accepted 2, rejected 0.
- Radio (bench): 915.0 MHz, LoRa 500 kHz, SF7, CR 4/5, 0 dBm.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

## a07f498273f7 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` | `ed2f0d3516a59e960a39d2e2a1ec93736790d14f41e2810a413565e77f8262c1` |
| `build/rx/stage0-rx.elf` | `78a199714633e44da8d36a84a21158b77ba14ef6494497b00946364143308b7e` |
| `build/tx/stage0-tx.bin` | `3d4ad22f0842219bf947a6ce0d9eb9d50adc0c8240ced6c90072e23fbaac4e79` |
| `build/tx/stage0-tx.elf` | `4425d77b8454aaa6c41f6d9408a3846404165caddc9550ddd76615dce37a6155` |

- Source: commit `a07f498273f7` (protocol draft 4 + NACK + health report). Build: `make ROLE=rx`, `make ROLE=tx` in `firmware/stage0-node`.
- Inputs: `tools/fetch-vendor.sh` (STM32CubeWL v1.6.0 `f934cd2` + pinned submodules, Mbed TLS 3.6.6), xPack arm-none-eabi-gcc 15.2.1-1.1, OpenOCD 0.12.0.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. Both boot lines report `fw=a07f498273f7`.
- Radio (bench): 915.0 MHz, LoRa 500 kHz, SF7, CR 4/5, 0 dBm.
- Not an H01 release: the SHT45 is not connected, and the radio settings are bench values.
