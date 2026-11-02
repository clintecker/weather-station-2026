# Power Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the station's power system, send it, store it and show it, with one wire format
that every later hardware phase fills without a redesign. The node firmware (not only the bench
tool) reads the official phase A wiring: bq24074 ISET on PB1, the charger input divider on PA10,
CHG on PB10, PGOOD on PB8, the battery INA228 at 0x40 and the MAX17048 at 0x36 on the cell. The
observation carries voltage and current of four rails (battery, signed; solar input; USB-C input;
load) every minute, and the 15-minute health report carries the slow items. The gateway decodes,
stores and exposes every value.

**Architecture:** Protocol version 6 carries all format changes: observation catalog version 2
(an EXT bit announces a 16-bit extension bitmap for fields 32–47) and a fixed 64-byte health
report. The WSMP registry gains rail quantities 18–24 and module types 8 (battery) and 9 (power
rails). `App/power_acq.c` reads every INA228 rail, the gauge and the board ADC sequence from a rail
table in `App/power_config.h` (profiles A and B). `App/mod_power.c` is the WSMP face and the health
accessor. The interim catalog map turns the two modules into fields 11–16, 26–30, 32 and 33. A slot
that the phase cannot fill is "not fitted" and absent from the record; a fitted part that fails
gives INVALID.

**Build-progression record (2026-10-29).** The decision record
`docs/superpowers/specs/2026-10-29-build-progression-decisions.md` lists, in its section 6, files
that change for the bench rebuild. This plan does not take them over wholesale: the design's
section 17 (and the record's section 8) settles each row. Adopted rows are in this plan's scope as
documentation amendments and, where they touch code, as completeness fixes (the fitted byte of the
health report, the I2C SDADEL hold, the HA freshness rule). Deferred rows
(R_ISET 1 kΩ, the ISET network M2, the cups/rain remap N2 and the M7 link probe) and the record's
own work package (the step 1 model commit, D1–D7, the host path metric M6) stay outside this plan
until Clint answers or the record's step starts.
*Amended 2026-10-30 (record 7.1; spec §15, §17):* N2 (cups PC0 → PB5, rain PB5 → PB4) was approved
by Clint on 2026-10-30 (record 7.1) and is owned by step 1 change B (record 4.5), not by this plan.
The M7 counter link probe is an H01 precondition (it runs before the H01 run;
bench status field `meter_link=`). R_ISET 1 kΩ and the M2 ISET network and measured divider are
adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4
steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet
check 2 (spec §8.6, §9.5, D4, D5; Clint to confirm). The `power_config.h` constants are
`POWER_R_ISET_OHM 1000`, `POWER_ISET_GAIN_PPM 990099` (nominal until fitted) and
`POWER_VIN_DIVIDER_PPM 3000000` (nominal until the three divider resistors are measured).

**Tech Stack:** C11 on STM32WL55JC (HAL, interrupt-driven ADC and I2C), host builds under
ASan/UBSan driven by Python `unittest` + ctypes, Python 3.12 for the gateway (`ws0`), literate
sources with `tools/tangle.py`, the generated WSMP registry (`tools/wsmp_registry.py`), KiCad 10
for the breadboard model.

**Spec:** [`docs/superpowers/specs/2026-10-29-power-telemetry-design.md`](../specs/2026-10-29-power-telemetry-design.md)
("spec §n" below). Section 13 lists the documents, section 14 the tests and the wave gate.

**Amends:** [`2026-10-16-flash-layout.md`](2026-10-16-flash-layout.md) (24 h of the build's widest
record), [`2026-10-18-wsmp-bench-station.md`](2026-10-18-wsmp-bench-station.md) (pin table, Task 6),
[`2026-10-19-bench-breadboard-wiring.md`](2026-10-19-bench-breadboard-wiring.md) (nets ISET and
VIN_SENSE, the ADC firmware check). Each carries a dated note.

## Global Constraints

- **Decisions are fixed** (Clint, 2026-10-29, spec §1): the 1S3P pack (3 × 2,200 mAh, 6,600 mAh,
  3.0–4.2 V); phase A = bq24074 #4755 at 1.0 A (R_ISET about 890 Ω, I = 400 × V_ISET ÷ R_ISET);
  the bench wiring of 2026-10-28/29 is official; four rails is the final goal; USB-C is bench and
  backup only, never with solar; the wire format is source-agnostic.
  *Amended 2026-10-30 (record 1.4, 7.1 P3; spec §1, D4):* R_ISET = 1 kΩ (R9 behind the 1A jumper),
  ICHG 0.89 A typ; ISET currents logged earlier with 890 Ω read 12 % high. Adopted with change A,
  read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the
  ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2. Clint to
  confirm (spec §15, D4).
- **One shared protocol version.** Both ends match version 6 or they drop each other's frames
  (spec §4). The TX and RX roles share `WS_FRAME_VERSION`.
- **Generated files only through their generator.** `*.lit.md` with
  `python3 tools/tangle.py <that .lit.md>`; the WSMP registry with `tools/wsmp_registry.py` from
  `firmware/common/wsmp_registry.toml`; the lock file is append-only (never reuse or change a code);
  the breadboard files with `hardware/bench-breadboard-r0/source/make.py all` through
  `tools/kicad_env.py`.
- Power of Ten as [`docs/power-of-ten.md`](../../power-of-ten.md) applies it: complexity ≤ 10 and
  ≤ 60 lines a function, no copies (`tools/code_shape.sh`), bounded loops, no heap, `WS_CHECK`.
  Strict C warnings. No blocking waits (`tools/blocking_report.py`).
- Firmware builds go to a private directory: `make -C firmware/stage0-node ROLE=tx BUILD=<scratch>/build-<task>-tx`
  (and `ROLE=rx`), never the default build directory. Only the Gates stage runs `tools/gates.sh`.
- Workers run only their targeted tests: `.venv/bin/python -m unittest tests.<module>`.
- Never touch the main checkout, a `run*/` directory or `evidence/` (a live run logs there). No
  serial port, flash, `openocd` or `launchctl` action in a task. No board, release or gateway-state
  action without Clint's OK.
- Never assume RJ45. Writing standard: plain, precise docs with tables and `file:line` references;
  Mermaid only where a document already uses it.
- No commit, push, stash, reset or branch switch inside a task; the orchestrator commits.

## Phases (spec §2)

| Phase | Charger | Monitors | Status |
|---|---|---|---|
| A (current) | bq24074, one VBUS input | battery INA228 0x40 (VBUS on OUT), MAX17048 0x36 on the cell; ISET → PB1, divider → PA10, CHG → PB10, PGOOD → PB8, VREFINT | this plan: firmware, protocol, gateway, docs |
| B (four rails) | bq24074 | phase A plus load 0x41, solar 0x45, USB-C 0x48 INA228s, upstream of the join | host tests only (`WS_POWER_PROFILE` B) |

## Waves

Each task below is one batch of the work. A wave's batches own disjoint files and run in parallel.
A wave starts only after the previous wave's gate.

| Wave | Tasks | Theme |
|---|---|---|
| 1 | B01–B06 | foundations: catalog v2 and journal floor, registry, WSMP 1.1, shared decoders, board ADC, bench logger |
| 2 | B07–B09 | version 6 frames and health report, host device models, breadboard tooling |
| 3 | B10–B14 | I2C hub profile, fuzz, RX consumers, gateway decode and HA, breadboard wiring |
| 4 | B15–B17 | power acquisition, station health sources, simulation harness |
| 5 | B18–B19 | WSMP power modules, web API and dashboard |
| 6 | B20–B22 | catalog map and field set, health report sending, OpenAPI and gateway docs |
| 7 | B23 | health airtime in the minute budget |
| 8 | B24–B32 | documents: protocol, WSMP, energy, planning, hardware, bench, spec and plan amendments |
| 9 | B33–B34 | measured budgets, READMEs, RELEASES.md, test and tool docs |
| after 9 | G1, R1, R2 | the Gates stage, the release, the bench acceptance drill |

## Wave gate (spec §14)

The gate keeps a wave from blaming another wave's unfinished work, and keeps a red test from hiding.

- [ ] **After each wave**, the orchestrator runs the whole host suite once:
  `WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests` (as `tests/README.md`
  runs it; never `tools/gates.sh`).
- [ ] It records the **expected-red set**: every red test, each with the batch that owns its fix.
  A red test is expected only if a later batch owns its fix. A red test whose owner is in the
  wave just finished, or in an earlier wave, is a failure of that wave: the orchestrator sends it
  back to its owner before the next wave starts.
- [ ] It passes the recorded set to every batch of the next wave.
- [ ] Each batch's **must-pass list** holds only (a) the tests that batch owns and (b) tests that
  were green at the previous gate. A test in the expected-red set that the batch does not own is not
  that batch's failure; the batch reports it and leaves it alone.
- [ ] A batch that edits a test file another batch of the same wave also edits is not allowed: the
  wave table above keeps test ownership disjoint inside a wave (`tests/test_breadboard.py`: B09 in
  wave 2, B14 in wave 3; `tests/test_tx_machine.py`: B21 in wave 6, B23 in wave 7;
  `tests/toolchain.py`: B04 in wave 1, B10 in wave 3, B15 in wave 4).
- [ ] **The final gate** (after wave 9) has an **empty** expected-red set. Only then does the Gates
  stage (task G1) run `tools/gates.sh`.

**Expected-red sets.** The table gives the set predicted from test ownership. The orchestrator's
recorded set replaces it at each gate; a test that is red but not listed, and not owned by a later
batch, stops the wave.

| Gate | Predicted expected-red (owning batch) | Why |
|---|---|---|
| after wave 1 | `test_fuzz` (B11); `test_wsmp_host` (B18); `test_stage0`, `test_mqtt_config`, `test_gateway` (B13) where they pin the catalog v1 field set; `test_web`, `test_dashboard_js` (B19); `test_harness` (B17) | catalog v2 (33 fields and EXT) and WSMP 1.1 (budget 60, minor 1) land before their consumers |
| after wave 2 | as wave 1, plus `test_rx_machine`, `test_rx_faults_tool`, `test_counter_regression`, `test_h01_report` (B12); `test_tx_machine` where it unpacks the health report positionally (B21) | byte 0 becomes 0x61–0x64; the health report becomes 64 B |
| after wave 3 | `test_harness` (B17); `test_wsmp_host` (B18); `test_web`, `test_dashboard_js` (B19); `test_tx_machine` health-report cases (B21) | gateway, fuzz and RX consumers are done |
| after wave 4 | `test_wsmp_host`, `test_modules` power cases (B18); `test_web`, `test_dashboard_js` (B19); `test_tx_machine` health-report cases (B21) | `power_acq` exists; the WSMP face is wave 5 |
| after wave 5 | `test_wsmp_map` (B20); `test_tx_machine` health-report cases (B21) | B18 leaves field 12 and the rails to B20 |
| after wave 6 | `test_tx_machine` and `test_stage0` cases that pin the SF12 minute backlog (B23) | the health airtime reserve is wave 7 |
| after wave 7 | empty | waves 8 and 9 own no test file |
| after wave 8 | empty | documents only; the doc-reading tests (`test_breadboard` reads `docs/hardware/bench-station-wiring.md`, `test_i2cscan` reads `firmware/benchlink/README.md`, `test_openapi` reads the gateway docs) must stay green |
| after wave 9 (final) | **empty (required)** | then task G1 |

---

## Wave 1

### Task B01: Observation catalog v2 and the journal floor

**Governs:** spec §5.1–5.3, §7. **Issues:** PT-001 – PT-008.

**Files:** `firmware/common/ws_obs.h`, `firmware/common/ws_obs.c`, `ws0/fields.py`,
`tests/test_obs.py`, `firmware/stage0-node/App/node_store.lit.md` (tangles
`firmware/stage0-node/App/node_store.c`), `firmware/stage0-node/App/flash_layout.h`,
`tests/test_flash_layout.py`.

- [ ] Catalog v2: fields 26 `load_mv`, 27 `load_current_ma`, 28 `charger_input_mv`, 29 `solar_mv`,
  30 `solar_current_ma`, 31 = EXT (not a field), 32 `usb_mv`, 33 `usb_current_ma`; `WS_FI_COUNT` 34.
  `WS_F(i)` is a `uint64_t` mask, so `WS_F(32)` is defined behaviour. Voltages u16 1 mV; currents
  2 B, 1 mA, offset 32768. Field 12 changes from 0.1 mA to 1 mA. Fields 17 and 18 stay decodable,
  retired from version 6 builds.
- [ ] The extension word: bit 31 set on the wire announces a u16 bitmap at offset 22. Canonical
  rules: EXT with an empty extension word, an extension bit for an undefined field (34–47), or an
  empty record are rejected; an extension-only record is legal.
- [ ] `ws0/fields.py` is the Python twin (`BY_INDEX`, `DEFINED` without bit 31, labels of spec §10.1).
- [ ] Journal: the 24 h assertion uses `WS_OBS_PLAIN_MAX` (the build's widest record), not every
  catalog field (`node_store.c:71`); `flash_layout.h` comment follows.

**Tests:** C/Python agreement for the 33 fields and EXT (34 bitmap positions); EXT rules; field 34 rejected; current edges
−32,768 and +32,766 mA valid, beyond INVALID; `WS_FIELDS_DEFINED` = `fields.DEFINED`; no chip
names in field names; `test_the_default_build_keeps_24_hours` (≥ 1,440 records, slot from the
formula).

**Verify:** `tests.test_obs tests.test_flash_layout tests.test_store_powercut tests.test_stage0 tests.test_tangle`;
ruff `ws0/fields.py`; TX and RX builds.

### Task B02: WSMP registry: quantities 18–24, types 8 and 9, locked type meta

**Governs:** spec §8.1, §8.2. **Issues:** PT-009 – PT-012.

**Files:** `firmware/common/wsmp_registry.toml`, `tools/wsmp_registry.py`,
`tools/wsmp_registry.lock`, `firmware/common/wsmp_registry.h` (generated),
`ws0/wsmp_registry.py` (generated), `tests/test_wsmp_registry.py`. The independent oracles follow
the spec table, not the generated header: `tests/wsmp_record_ref.py`, `tests/test_wsmp_record.py`,
`firmware/fuzz/fuzz_wsmp.c`, `firmware/fuzz/fuzz_record.c`, the seeds under
`firmware/fuzz/corpus/wsmp/` and `firmware/fuzz/corpus/record/`.

- [ ] Registry version 2. Quantities 18 load voltage, 19 load current, 20 charger input voltage,
  21 solar voltage, 22 solar current, 23 USB-C voltage, 24 USB-C current. Quantity 9 = the cell
  terminal voltage; quantity 10 used for the first time.
- [ ] Types 8 battery (`BATTERY`, minute) and 9 power rails (`POWER_RAILS`, minute). Type 5 stays,
  frozen.
- [ ] The lock records `type_meta <type>.<schema> <class> <role> [states]` for every type; `--check`
  refuses a change.

**Tests:** new codes locked; `type_meta` lines; type 5 still decodes; the record reference knows
types 8 and 9, and type 10 is "not in the registry".

**Verify:** `tests.test_wsmp_registry tests.test_wsmp_set tests.test_descsets tests.test_wsmp_core tests.test_modules tests.test_wsmp_record`;
`tools/wsmp_registry.py --check`; TX build.

### Task B03: WSMP core: "not fitted" quality 6, WSMP 1.1, budget 60

**Governs:** spec §8.3, §8.4. **Issues:** PT-013, PT-014.

**Files:** `firmware/common/wsmp.h`, `firmware/common/wsmp.lit.md` (prose only; `wsmp.c` does not
change), `tests/test_wsmp_core.py`, `ws0/wsmp_set.py`, `tests/test_wsmp_set.py`.

- [ ] `WSMP_QUAL_NOT_FITTED` 6 (carried as missing (3) on the radio), `WSMP_VERSION_MINOR` 1,
  `WSMP_RADIO_BUDGET` 60.
- [ ] `python3 tools/tangle.py --check firmware/common/wsmp.lit.md` stays clean.

**Tests:** quality 6 → air 3; budget 60; minor 1; a higher minor still accepted.

**Verify:** `tests.test_wsmp_core tests.test_wsmp_set tests.test_descsets tests.test_tangle`; TX build.
`tests.test_wsmp_host` pins 58 and minor 0 until B18 (expected red).

### Task B04: Shared power register decoders

**Governs:** spec §9.4 (shared decoders), §9.5 (conversions). **Issue:** PT-015.

**Files:** `firmware/common/power_regs.c`, `firmware/common/power_regs.h` (new),
`firmware/i2cscan/App/bench_regs.c`, `firmware/i2cscan/App/bench_regs.h`,
`firmware/benchlink/App/benchlink.c`, `firmware/i2cscan/Makefile`, `firmware/benchlink/Makefile`,
`tests/test_i2cscan.py`, `tests/toolchain.py`.

- [ ] One copy of the INA228, MAX17048, ISET, divider and VREFINT conversions for the node,
  i2cscan and benchlink: `ina228_shunt_cal` (15,000 µΩ → 1966), `ina228_current_ua` (shunt in µΩ),
  `adc_vdda_mv` (VREFINT_CAL at 3.3 V), `adc_pin_uv`, `iset_charge_ua` (2.225 V at 890 Ω → 1.000 A),
  `divider_mv` (× 3).

**Tests:** every datasheet vector of `tests/test_i2cscan.py` against the shared module, plus the new
vectors; no caller passes a shunt in mΩ.

**Verify:** i2cscan and benchlink builds into private BUILD directories; `tests.test_i2cscan tests.test_benchlink`.

### Task B05: Board ADC: one interrupt-driven sequence, VDDA, CHG edges

**Governs:** spec §9.5. **Issues:** PT-016 – PT-021.

**Files:** `firmware/stage0-node/App/board_inputs.c`, `firmware/stage0-node/App/board_inputs.h`,
`tools/blocking_report.py`, `tests/test_board_inputs.py`, `firmware/host/wsmp_harness.c`,
`firmware/host/tx_harness.c`.

- [ ] One regular sequence from the 250 ms vane tick: IN4 (PB2 vane), IN5 (PB1 ISET), IN6 (PA10
  divider), VREFINT; 160.5 cycles; oversampling × 16, shift 4; no polling.
- [ ] `#define ISET_PIN GPIO_PIN_1 /* PB1 */` and `#define VIN_PIN GPIO_PIN_10 /* PA10 */`, analog,
  no pull. VDDA from VREFINT; the vane stays ratiometric (fixed 3300).
- [ ] CHG (PB10) counts both edges on EXTI10; PB8/PB10 keep the pull-ups (FT_f: below VDD + 0.3 V).
- [ ] Seams `board_power_adc()` and `board_charger_edges()`; debug outputs on PA10, PA11, PA12 and
  PB2 asserted off.

**Tests:** the sequence of four channels; VDDA from a VREFINT pair; ISET and VIN conversion; 4085
is out of range; pin modes; vane unchanged.

**Verify:** `tests.test_board_inputs tests.test_blocking_report tests.test_modules tests.test_tx_machine tests.test_breadboard`;
TX build, then `tools/blocking_report.py` on it.

### Task B06: Benchlink logger and dashboard: one sign conversion

**Governs:** spec §3.1, §12.1. **Issue:** PT-022.

**Files:** `tools/benchlink_dash.py`, `tools/benchlink_dash.html`, `tools/benchlink_log.py`,
`tests/test_benchlink.py`, `firmware/benchlink/App/bl_pkt.h` (comments only).

- [ ] The logger converts the raw INA228 current once: `battery_ma = −ishunt_ma` (+ into the cell).
  The dashboard uses it from `--shunt-from` on, and keeps ISET − load as a marked fallback.
  R_ISET (890), K (400) and R_LOAD (100) become options. *Amended 2026-10-30 (record 1.4, 6.4;
  spec D4):* the R_ISET default becomes 1000 Ω with change A (record 6.4 `tools/benchlink_log.py`);
  the 890 Ω vector of the shared conversion test above stays a valid arithmetic vector.

**Tests:** both paths (shunt present, fallback) and the sign.

**Verify:** `tests.test_benchlink`; ruff on the Python files.

## Wave 2

### Task B07: Protocol version 6 and the 64-byte health report

**Governs:** spec §4, §6.1, §6.3. **Issues:** PT-023 – PT-026.

**Files:** `firmware/common/ws_frame.lit.md` (tangles `ws_frame.h`, `ws_frame.c`),
`ws0/protocol.lit.md` (tangles `ws0/protocol.py`), `gateway.lit.md` (tangles `gateway.py`),
`tests/test_frame.py`, `firmware/stage0-node/App/selftest.c` (boot KAT).

- [ ] `WS_FRAME_VERSION` 6 (byte 0 = 0x61–0x64); `WS_DIAG_PLAIN_LEN` 64 in the order of spec §6.1;
  none codes (u16 0xFFFF, i16 `INT16_MIN`, charger status 0xFF); charger status bits of spec §6.3.
- [ ] Python `pack_diag(**fields)` and `unpack_diag(payload)` by C member name; nothing unpacks by
  position. `RECORD_VERSION` 6.
- [ ] Regenerated known-answer vectors, the same arrays in `selftest.c`.

**Tests:** byte 0; the 64-byte layout C ↔ Python field by field with none codes and extremes;
non-canonical vectors (fitted bit 7 set, stage 7; byte 51 became the fitted byte on 2026-10-29,
design section 6.1); active input 3 decodes as `no_input` (canonical since 2026-10-29, section 6.3); kind 5 still refused; KAT.

**Verify:** `tests.test_frame tests.test_tangle`; TX and RX builds.

### Task B08: Host device models for the INA228 and the MAX17048

**Governs:** spec §9.4, §14 (Acquisition). **Issue:** PT-027.

**Files:** `firmware/host/i2c_models.c`, `firmware/host/i2c_sim.h`.

- [ ] Per-device INA228 shunt (µΩ) and true current: VSHUNT, CURRENT from the written SHUNT_CAL,
  CHARGE and ENERGY per conversion, VBUS, DIETEMP; several instances at distinct addresses.
  MAX17048 VERSION, VCELL, 1/256 % SOC, signed CRATE. Existing setters keep their meaning.

**Verify:** `tests.test_modules tests.test_wsmp_map tests.test_i2c_bus tests.test_tx_machine tests.test_wsmp_host`
pass as at the previous gate.

### Task B09: Breadboard tooling: CN8, heavy leads, lanes, ADC firmware check

**Governs:** spec §11.1 (CN8, battery path, firmware check). **Issues:** PT-028 – PT-030.

**Files:** `hardware/bench-breadboard-r0/source/wiring.py`, `.../source/flying.py`,
`.../source/models.py`, `.../source/render.py`, `.../source/make.py`, `tests/test_breadboard.py`,
and the files `make.py all` writes (`bench-breadboard.kicad_pcb`, `bench-breadboard-3d.kicad_pcb`,
`bench-breadboard.kicad_sch`, `layout.json`, `build-sheet.md`, `models/`, `renders/`).

- [ ] Header CN8 (1 × 6, UM2592 table 17); the `[[lead]]` construct (no strip); room for at least
  20 flying jumpers; `check_firmware` reads `firmware/benchlink/App` as well and checks ADC
  channels (`ADC_CHANNEL`: PB1 = 5, PB2 = 4, PA10 = 6); colours for `analog` and battery leads.
- [ ] Regenerate with `make.py all`; DRC and ERC clean.

**Tests:** CN8 holes; lead parsing and connectivity; lane capacity ≥ 20; the pin regex with a
trailing comment; `test_an_adc_input_needs_its_channel`.

**Verify:** `tests.test_breadboard`.

## Wave 3

### Task B10: I2C bus: hub profile, rail clients, recovery counters

**Governs:** spec §9.1, §9.2, §6.2. **Issues:** PT-031 – PT-033.

**Files:** `firmware/stage0-node/App/i2c_bus.lit.md` (tangles `i2c_bus.c`, `i2c_bus.h`),
`firmware/host/i2c_sim.c`, `firmware/host/i2c_sim.h`, `tests/test_i2c_bus.py`,
`tests/toolchain.py`, `firmware/stage0-node/App/wsmp_local.c` (minimal routing).

- [ ] `WS_I2C_MUX` 0 by default (the STEMMA QT hub): every client upstream, no mux job; `1` keeps
  the mux profile unchanged. Clients `I2C_C_INA_LOAD`, `I2C_C_INA_SOLAR`, `I2C_C_INA_USB`.
- [ ] `i2c_bus_recoveries()`, `i2c_bus_stuck()`, `i2c_bus_mux_resets()`, saturating u16.

**Tests:** hub-only boot reads INA228 0x40, MAX17048 0x36, SHT45 0x44 with no mux; the mux tests
on the mux build; one recovery counted per recovery, saturating; 0x40, 0x41, 0x45, 0x48 distinct and
outside the reserved set.

**Verify:** `tests.test_i2c_bus tests.test_modules tests.test_wsmp_host tests.test_wsmp_map tests.test_tx_machine tests.test_tangle`;
TX build with the default profile and with `WS_I2C_MUX=1`.

### Task B11: Fuzz targets, spec constants and seeds for version 6

**Governs:** spec §4, §5.1, §5.2, §5.4, §6.1. **Issue:** PT-034.

**Files:** `firmware/fuzz/fuzz.h`, `firmware/fuzz/fuzz_obs.c`, `firmware/fuzz/fuzz_console.c`,
`firmware/fuzz/fuzz_reply.c`, `firmware/fuzz/corpus/obs/`, `firmware/fuzz/corpus/console/`,
`firmware/fuzz/corpus/reply/`, `firmware/fuzz/README.md`, `tests/test_fuzz.py`.

- [ ] Hand-written spec constants: byte 0 = 0x60 | kind, observation frame ≤ 110 B, health frame
  80 B, the EXT word. The obs oracle covers 34 indexes and the EXT rules. Seeds regenerated
  (full-catalog 94 B record, EXT seeds, power edges).
- [ ] A planted off-by-one in a new field's range is caught, then removed.

**Verify:** `tests.test_fuzz` with no `warning:` lines.

### Task B12: Version 6 consumers on the RX side

**Governs:** spec §4, §6.1. **Issues:** PT-035, PT-036.

**Files:** `tests/test_rx_machine.py`, `tests/test_rx_faults_tool.py`, `tools/rx_faults.py`,
`tests/test_counter_regression.py`, `firmware/host/rx_harness.c` (only if a constant there is not
derived), `tests/test_h01_report.py` (record version from `gateway.RECORD_VERSION`).

- [ ] No hard-coded 0x51–0x55; values come from `ws0.protocol` constants. `rx_faults.py` classifies
  version 5 captures as "previous version". Health reports built with `pack_diag`.

**Verify:** `tests.test_rx_machine tests.test_rx_faults_tool tests.test_counter_regression tests.test_h01_report`.

### Task B13: Gateway: health report decode, Home Assistant entities, simulator

**Governs:** spec §5.3, §6.1–6.3, §10.1, §10.2. **Issues:** PT-037 – PT-040.

**Files:** `ws0/service.py`, `ws0/simulator.py`, `tests/test_stage0.py`,
`tests/test_mqtt_config.py`, `tests/test_gateway.py`.

- [ ] `receive_diagnostic` stores every key of spec §6.1 with none → null (`last_crash_pc` as hex,
  null for 0); charger booleans and stage from the status byte.
- [ ] HA discovery for the power health keys (diagnostic category, binary sensors for the three
  booleans); station counters in JSON only; no topic generated twice.
- [ ] The simulator sends a phase A power set and 15-minute health reports through `pack_diag`.

**Tests:** new keys and nulls; health keys disjoint from `fields.MEASURED`; a healthy phase A record
is "valid"; the discovery payloads.

**Verify:** `tests.test_stage0 tests.test_mqtt_config tests.test_gateway tests.test_counter_regression`; ruff.

### Task B14: Breadboard model: the official phase A power wiring

**Governs:** spec §11.1, §11.2, §3.1. **Issues:** PT-041 – PT-050.

**Files:** `hardware/bench-breadboard-r0/source/wiring.toml`, `.../source/wiring.py`,
`.../source/build_schematic.py`, `.../source/make.py`, `hardware/bench-breadboard-r0/README.md`,
`tests/test_breadboard.py`, `docs/hardware/bench-station-wiring.md` (section 2 rows for PB1 and
PA10 only), and the files `make.py all` writes.

- [ ] Nets `ISET` (PB1, `N:CN8.1`) and `VIN_SENSE` (PA10, `N:CN8.3`) with R4 + R5 (10 kΩ each) over
  R6 (10 kΩ); `INA.VBUS` in `SYS_OUT`; `GBAT` on the cell; the battery path and the charger input as
  `[[lead]]`s; the 10 kΩ NTC on THERM; the 1S3P pack.
- [ ] `wiring.FIRMWARE` maps `ISET_PIN` and `VIN_PIN` in `board_inputs.c` and `benchlink.c`.
- [ ] Build sheet: the VDD + 0.3 V pull-up rule; checks for ISET and VIN_SENSE, the shunt verified
  against a series reference (within 2 % + 2 mA, spec §8.6), the battery-path span limits at 0.8–1.0 A
  (+ span ≤ 75 mΩ, − span ≤ 40 mΩ, each pack-side span ≤ 28 mΩ; spec §11.2, build-sheet check 7; this
  said "the battery-path drop at 1 A (≤ 50 mV)" before PT record P8), gauge VCELL against a meter,
  INA VBUS = OUT, a 1 A charge that terminates normally.

**Tests:** `test_iset_and_vin_sense_are_named_on_cn8`, `test_the_divider_is_20k_over_10k`,
`test_ina_vbus_reads_out`, `test_the_gauge_senses_the_cell_kelvin`,
`test_the_firmware_reads_iset_and_vin_on_their_adc_channels`, no battery-path or charger-input net
on a strip, `test_renders_exist_and_are_current`.

**Verify:** `tests.test_breadboard`.

## Wave 4

### Task B15: Power acquisition driver

**Governs:** spec §3.1–3.3, §6.3, §8.6, §9.2–9.5. **Issues:** PT-051 – PT-061.

**Files:** `firmware/stage0-node/App/power_config.h`, `firmware/stage0-node/App/power_acq.c`,
`firmware/stage0-node/App/power_acq.h` (new), `firmware/host/power_harness.c` (new),
`tests/test_power_acq.py` (new), `firmware/stage0-node/Makefile`, `tests/toolchain.py`,
`firmware/common/ws_check.h`, `tests/test_check.py`.

- [ ] `WS_POWER_PROFILE` (A default, B, C → `#error`) and the fixed rail table of spec §9.3 (battery
  0x40, 15,000 µΩ nominal, sign −1, VBUS on OUT; phase B adds 0x41, 0x45, 0x48 at sign +1);
  addresses asserted distinct and outside 0x36, 0x44, 0x46, 0x47, 0x50, 0x53, 0x70, 0x71.
- [ ] Non-blocking step machines: each rail every 1 s (SHUNT_CAL check, VBUS, CHARGE), DIETEMP every
  60 s; the gauge every 15 s; the ADC values every 1 s; CHG/PGOOD every 250 ms (fault = 3 CHG edges
  in 2 s, cleared after 4 s). Window time from `clock_ms()`, never `HAL_GetTick`.
- [ ] Battery energy = ΔQ × VCELL (at most 20 s old), else charge only and energy missing.

**Tests:** `test_a_current_from_vin_plus_to_vin_minus_is_a_discharge`, steady ± means, burst mean
exact, reset mid-window, energy from VCELL and missing when stale, OUT ≠ cell kept apart, ISET with
VDDA scaling and 0 mA without PGOOD, a partially clipped result out of range, CHG flashing → fault,
`test_four_rails_and_one_absent` (profile B).

**Verify:** `tests.test_power_acq tests.test_check tests.test_i2cscan tests.test_modules`; TX build;
`tools/code_shape.sh` if it runs standalone.

### Task B16: Station health sources

**Governs:** spec §6.2, §9.8. **Issues:** PT-062, PT-063.

**Files:** `firmware/stage0-node/App/fault.c`, `firmware/stage0-node/App/fault.h`,
`firmware/stage0-node/App/watchdog.h`, `firmware/host/sim_core.c`,
`firmware/benchlink/App/bl_guard.c`; the boot note in `firmware/stage0-node/App/app_tx.lit.md` and
`firmware/stage0-node/App/app_rx.lit.md` (tangled); `tests/test_fault.py` (new).

- [ ] `fault_last_pc()` (0 with no crash, 0xFFFFFFFF for an untrusted frame); `fault_boots()` from
  backup register DR12, one increment a boot, saturating, restarted by a power-on; benchlink shares
  the meaning. A brown-out reads as power-on (spec R7).
- [ ] `sim_core.c` setters for reset cause, crash count, last PC and boots.

**Tests:** `test_no_crash_gives_pc_zero`, `test_one_increment_per_boot`,
`test_a_power_on_restarts_the_count`, `test_the_count_saturates_at_0xffff`,
`test_no_other_firmware_writes_dr12_or_calls_the_note`.

**Verify:** TX, RX and benchlink builds; `tests.test_fault tests.test_tx_machine tests.test_rx_machine tests.test_tangle`.

### Task B17: Simulation harness: phase A power fields and health reports

**Governs:** spec §10.2. **Issue:** PT-064.

**Files:** `ws0/harness.py`, `docs/simulation-harness.md`, `tests/test_harness.py`.

- [ ] The harness carries the simulator's phase A power set, sends 15-minute health reports through
  the real receive path and checks their storage; options for a faulted INA228 and absent phase B
  rails. The doc says the values are synthetic.

**Verify:** `tests.test_harness`; ruff `ws0/harness.py`.

## Wave 5

### Task B18: Battery and power-rails WSMP modules and the health accessor

**Governs:** spec §8.1, §8.3–8.5, §9.6. **Issues:** PT-065 – PT-069.

**Files:** `firmware/stage0-node/App/mod_power.c`, `firmware/stage0-node/App/mod_power.h`,
`firmware/stage0-node/App/wsmp_local.c`, `firmware/stage0-node/App/wsmp_local.h`,
`firmware/stage0-node/App/wsmp_host.lit.md` (tangles `wsmp_host.c`), `firmware/host/wsmp_harness.c`,
`firmware/stage0-node/App/wsmp_catalog_map.c` (minimal), `tests/test_modules.py`,
`tests/test_wsmp_host.py`.

- [ ] Battery module (type 8, port `P_BATTERY` 5, 6 channels) and rails module (type 9, port
  `P_RAILS` 8, 7 channels) over `power_acq`; empty profile slots are `WSMP_QUAL_NOT_FITTED`; both
  modules always present in profile A.
- [ ] `mod_power_health(power_health_t *)` returns the cached slow values with their none codes.

**Tests:** conformance for both modules; the gauge without the INA228; not-fitted slots in profile
A; a faulted part affects only its slots; budget 60 and minor 1 in `test_wsmp_host`.

**Verify:** `tests.test_modules tests.test_wsmp_host tests.test_wsmp_set tests.test_descsets tests.test_tangle`;
TX build. `tests.test_wsmp_map` may stay red until B20 (expected red).

### Task B19: Web API and dashboard: power view and health keys

**Governs:** spec §10.1, §10.2. **Issues:** PT-070 – PT-072.

**Files:** `ws0/web.py`, `ws0/static/app.js`, `ws0/static/index.html`, `ws0/static/app.css`,
`tests/test_web.py`, `tests/test_dashboard_js.py`.

- [ ] A power chart group (rail V and I, battery current signed with a zero line, SOC with its rate,
  the charger status band); rails absent from every recent record say "not measured in this build";
  the node health table adds VDDA, die temperature, boots, crashes, last PC, TX timeouts, I2C
  recoveries.

**Tests:** version 6 byte values; the new fields through `/v1/observations`, `/latest`,
`/v1/history` and the CSV; health keys through `/v1/diagnostics`; nulls stay null; dashboard
fixtures and the "not measured" rendering.

**Verify:** `tests.test_web tests.test_dashboard_js`; ruff `ws0/web.py`.

## Wave 6

### Task B20: Interim catalog map and the version 6 field set

**Governs:** spec §3.2, §5.2–5.4, §9.7. **Issues:** PT-073 – PT-077.

**Files:** `firmware/stage0-node/App/wsmp_catalog_map.c`, `firmware/stage0-node/App/wsmp_catalog_map.h`,
`firmware/stage0-node/App/node_fields.h`, `tests/test_wsmp_map.py`, `firmware/fuzz/corpus/set/`.

- [ ] Battery module → fields 11–16 (12 with offset; outside ±32,766 mA INVALID); rails module →
  26–30, 32, 33; a not-fitted slot leaves its field out; missing or fault → INVALID.
- [ ] `WS_F_WSMP_BENCH` = the 77 B set (v5 bench set without 17 and 18, plus 12, 26–30, 32, 33).

**Tests:** each new field and its INVALID case; the sign and range clamp; the phase matrix (charger
off, charging, done; USB-C vs solar, never both); profile B with every rail and the extension word.

**Verify:** `tests.test_wsmp_map tests.test_modules tests.test_flash_layout tests.test_fuzz tests.test_tx_machine`;
TX build; `WS_OBS_PLAIN_MAX` = 77.

### Task B21: Health report sending and the TX timeout counter

**Governs:** spec §6.1, §6.2, §9.8. **Issues:** PT-078 – PT-080.

**Files:** `firmware/stage0-node/App/tx_exchange.lit.md` (tangles `tx_exchange.c`,
`tx_exchange.h`), `firmware/stage0-node/App/tx_console.c`, `firmware/host/tx_harness.c`,
`tests/test_tx_machine.py`.

- [ ] `send_diag` fills all 64 bytes from cached accessors only (`fault_last_pc`, `fault_boots`,
  `tx_timeouts`, `i2c_bus_recoveries`, `mod_power_health`); both `EV_TX_TIMEOUT` paths count;
  `#diag sent` and `#status` lines gain the new keys.

**Tests:** a health report opened with `ws0.protocol.unseal` and decoded with `unpack_diag`: every
field, none codes with the gauge absent, saturation, a counted TX timeout.

**Verify:** `tests.test_tx_machine tests.test_rx_machine tests.test_tangle`; TX build;
`tools/blocking_report.py` on it.

### Task B22: OpenAPI schemas and gateway-facing docs

**Governs:** spec §5.3, §10. **Issues:** PT-081 – PT-083.

**Files:** `docs/openapi.json`, `docs/web-dashboard.md`, `docs/runbook-home-assistant.md`,
`ws0/README.md`, `tests/test_openapi.py` (new).

- [ ] Schemas `Observation` (every catalog field, "absent = not measured in this build, null =
  invalid"), `HealthReport` (every stored key), `Status.node_diagnostics`, `/v1/history`; version
  bumped. Dashboard and HA docs: power view, per-phase availability, battery current sign, field
  11's meaning, removal of the retired `soc_gauge_pct` and `charger_pins` entities.

**Tests:** property sets equal `fields.MEASURED` plus base keys and the keys `receive_diagnostic`
stores; every key named in the gateway docs.

**Verify:** `tests.test_openapi`; `python -m json.tool docs/openapi.json`.

## Wave 7

### Task B23: Health airtime in the minute budget; energy state deferred

**Governs:** spec §6.4, §9.9. **Issues:** PT-084 – PT-086.

**Files:** `firmware/common/ws_policy.lit.md` (tangles `ws_policy.c`, `ws_policy.h`),
`firmware/stage0-node/App/tx_policy.c`, `firmware/stage0-node/App/tx_policy.h`,
`firmware/test_tx_policy.c`, `tests/test_tx_machine.py`,
`firmware/board/nucleo-wl55jc/Core/Inc/sys_conf.h` (comment only).

- [ ] `ws_minute_backlog` takes `reserve_ms` (the health frame's airtime when a report is due); the
  live reading always goes. CONSERVE at SF12 exceeds the 2 s cap by 272 ms once a report (R3).
  `energy_state()` stays NORMAL, thresholds deferred (D1).

**Tests:** vectors at SF7 (unchanged), SF12 NORMAL (3 exchanges, 2 in a health minute), CONSERVE
(live only); exchange 821.2 + 411.6 + 300 = 1,532.8 ms; the minute observation carries fields 11–16,
26, 28.

**Verify:** `tests.test_stage0 tests.test_tx_machine tests.test_tangle`; TX build.

## Wave 8 (documents)

No wave 8 task owns a test file. Each keeps the doc-reading tests green (Wave gate).

### Task B24: protocol.md and protocol-design.md for version 6

**Governs:** spec §3–§7, §12.1. **Issues:** PT-087, PT-088.
**Files:** `docs/protocol.md`, `docs/protocol-design.md`.

- [ ] Version 6 byte 0; health report table of spec §6.1 with the charger status byte; EXT word and
  its canonical rules; catalog v2 rows and field notes (`charger_input_mv` at VIN-DPM, SOC over-read
  while charging); sizes and airtime (spec §5.4); the 96 B per-build ceiling; the presence rule; the
  release procedure with the drain step; health reports are not journaled.

**Verify:** grep both files for `0x5`, `version 5`, `catalog, version 1`, `78 B`, `94-byte`, `48 B`
and resolve each; `tests.test_obs tests.test_frame` stay green.

### Task B25: protocol-stack.md for version 6

**Governs:** spec §4–§7. **Issue:** PT-089. **Files:** `docs/protocol-stack.md`.

- [ ] Version, catalog and sizes, journal, byte-0 values, frame sizes and airtime, the §7.3.2 health
  report offsets (64 B).

**Verify:** grep for `version 5`, `0x5`, `32 B`, `48 B`, `77 B`, `78 B` and resolve each against the spec.

### Task B26: module-protocol.md (WSMP) for the power modules

**Governs:** spec §8, §3. **Issues:** PT-090, PT-091. **Files:** `docs/module-protocol.md`.

- [ ] Registry version 2, quantities 18–24, types 8 and 9, type 5 frozen; the multi-rail rule and
  the fill table; quality 6 and WSMP 1.1; A1 = 60; rule 7, G8, §11.3, §15: the slow power items are
  health-report fields; H8 row; RJ45 marked as the unscheduled v2.

**Verify:** `tests.test_wsmp_registry` stays green; grep for `battery and charger` and
`health report carries the 7 battery channels` and resolve.

### Task B27: Energy policy and failure modes

**Governs:** spec §1, §2, §3, §6.4, §9.9, §15. **Issues:** PT-092 – PT-094.
**Files:** `docs/radio-energy-policy.md`, `docs/failure-modes.md`.

- [ ] 1S3P pack facts (about 24.4 Wh), D1 open; per-phase inputs; the kind-4 question closed; the
  health airtime rule; airtime tables with the 93 B widest frame; new failure rows (monitor absent,
  VBUS jumper or gauge on the wrong net, high-resistance battery path, USB-C with solar, FT_f limit,
  address clash, recovery storms, brown-out as power-on).

**Verify:** figures match the spec; no test edits.

### Task B28: Planning docs: phases, stage order, 1S3P, four rails, USB-C rule

**Governs:** spec §1, §2, §3, §15. **Issues:** PT-095 – PT-104.
**Files:** `docs/CONTEXT-PACK.md`, `docs/H01-checklist.md`, `README.md` (and the stage plan, removed
2026-11-02).

- [ ] One authoritative phase section with exit criteria; the order of the power work against H01;
  4S4P statements restated for 1S3P; D1 and D2 open; document index rows for the spec, this plan and
  `docs/hardware/power-metering.md`.

**Verify:** links resolve; no figure contradicts the spec.

### Task B29: Hardware docs: power metering, wiring guide, bring-up, shopping list

**Governs:** spec §3, §9.2, §9.5, §11. **Issues:** PT-105 – PT-108.
**Files:** `docs/hardware/power-metering.md` (new), `docs/hardware/bench-station-wiring.md`,
`docs/hardware/nucleo-wl55jc-bringup.md`, `docs/poc-shopping-list.md`.

- [ ] Rail table per phase, phase B topology upstream of the join, address and pull-up rules;
  the battery chain section, the analog notes, the UM2592 checklist and pin budget; the dated
  2026-10-28/29 bring-up entry; parts.

**Verify:** `tests.test_breadboard` (`check_guide` reads `bench-station-wiring.md`) stays green.

### Task B30: Bench docs

**Governs:** spec §11, §12. **Issues:** PT-110.
**Files:** `firmware/benchlink/README.md`, `firmware/i2cscan/README.md`,
`firmware/i2cscan/App/bench_screen.c` (and two later-stage hardware documents, removed 2026-11-02).

- [ ] The benchlink wiring is official; the acceptance drill (spec §12.2); the raw INA228 sign and
  the logger's conversion; i2cscan VBUS = OUT.

**Verify:** i2cscan build into a private BUILD directory; `tests.test_i2cscan` (it reads
`firmware/benchlink/README.md`) stays green; links resolve.

### Task B31: Dated amendments to the 2026-10-18 and 10-19 specs

**Governs:** spec §4, §8.4, §9.1, §9.2, §11. **Issues:** PT-113 – PT-115.
**Files:** `docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md`,
`docs/superpowers/specs/2026-10-19-bench-breadboard-wiring-design.md` (and the two later-stage
designs, removed 2026-11-02; their implemented sections are in `docs/firmware-current-design.md`).

- [ ] The pin table and lessons; nets ISET and VIN_SENSE; the INA228 address plan; the hub profile.

**Verify:** links resolve; no figure contradicts the spec.

### Task B32: Plans: amendments and this plan

**Governs:** the whole spec, §13, §14. **Issues:** PT-117, PT-154.
**Files:** `docs/superpowers/plans/2026-10-29-power-telemetry.md` (this file),
`docs/superpowers/plans/2026-10-18-wsmp-bench-station.md`,
`docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md`,
`docs/superpowers/plans/2026-10-16-flash-layout.md`.

- [ ] This plan with the wave gate and the expected-red sets; dated notes in the three older plans
  (pin table PB1/PA10 and Task 6 → `power_acq`/`mod_power`; nets ISET and VIN_SENSE and the ADC
  firmware check; 24 h of the build's widest record).

**Verify:** every path named in this plan exists (new files of a later task exist after that task).

## Wave 9

### Task B33: Firmware budget (measured), firmware READMEs, RELEASES.md

**Governs:** spec §4, §5.4, §7, §9, §12.2. **Issues:** PT-118 – PT-121.
**Files:** `docs/firmware-budget.md`, `firmware/README.md`, `firmware/stage0-node/README.md`,
`firmware/stage0-node/RELEASES.md`.

- [ ] Measured TX/RX flash and stack from this wave's builds (`make stack`, `tools/stack_report.py`);
  per-phase power rows; the journal rows (1,449 records); the field set; `WS_I2C_MUX` and
  `WS_POWER_PROFILE`; the release steps; a dated addendum under release 04fcc656938d for the
  battery current sign finding.

**Verify:** the numbers come from this session's builds; `FLASH_BUDGET_PCT` not exceeded.

### Task B34: Test, tool and Power of Ten docs

**Governs:** spec §14. **Issue:** PT-122.
**Files:** `tests/README.md`, `tools/README.md`, `docs/power-of-ten.md`.

- [ ] A current test count with date and commit base (one read-only discovery run); rows for
  `test_power_acq`, `test_openapi`, `test_fault`, `test_board_inputs`; the host variants
  (`WS_I2C_MUX`, `WS_POWER_PROFILE`); `rx_faults` versions 5 and 6; benchlink logger options;
  Power of Ten references to `power_acq`, `power_regs` and the ADC sequence.

**Verify:** the count is from this run; links resolve.

## After the final gate

### Task G1: The Gates stage

- [ ] The final wave gate has an empty expected-red set (Wave gate).
- [ ] Run `tools/gates.sh` once, from the worktree. Every gate passes (`tools/gates.sh:18-46`):
  ruff; code shape (lizard, jscpd, loop bounds, tangle, registry); cppcheck; two clean builds with
  identical `.bin` (budget, no heap); the bench firmware (rangetest, i2cscan, benchlink);
  `gcc -fanalyzer`; the stack bound; no blocking waits; the unit tests; the fuzz targets; Power of
  Ten rule 1.
- [ ] A failing gate goes back to the task that owns the file; the orchestrator re-runs the wave
  gate and then this task.

### Task R1: Release version 6 (spec §4)

Needs Clint's OK and the boards. Not run by a worker.

- [ ] Step 0: drain the journal: wait for `pending=0` on the TX console (a WIPE discards pending
  records).
- [ ] Step 1: WIPE the node.
- [ ] Step 2: flash the RX board and the TX board from the same release (TX and RX share
  `WS_FRAME_VERSION`; the boot KAT vectors change with the version byte).
- [ ] Step 3: `init` a new run directory. The old run directory and its database stay with the old
  release.
- [ ] Step 4: run `provision-node` with the new key.
- [ ] Step 5: start the gateway (`RECORD_VERSION` 6).
- [ ] Step 6: record the release in `firmware/stage0-node/RELEASES.md`: protocol version 6, the
  field set (77 B), the power wiring phase (A) and the monitored rails (battery; load voltage;
  charger input voltage).
- [ ] Home Assistant: remove the retained `soc_gauge_pct` and `charger_pins` entities of older runs.
- [ ] D2 (open for Clint): whether H01 runs on this release; the recommendation is yes.

### Task R2: Bench acceptance drill (spec §12.2) and phase A exit

Needs Clint's OK, the breadboard and one pack with the cell through the shunt.

- [ ] Flash benchlink and log a known-state window: USB-C charging, solar charging, discharging into
  the 100 Ω load. Then flash the node and repeat the same states.
- [ ] Pass criteria:

| Check | Pass |
|---|---|
| battery current sign and magnitude | within 2 % + 2 mA of a separate reference (a calibrated shunt or a DC clamp meter); a DMM in series only in a short steady window, never in a termination run |
| ISET | within 10 % |
| divider ratio, VCELL | against a DMM: within 1 % and 10 mV |
| CHG, PGOOD | equal between benchlink and the node |
| die temperature, VDDA | plausible |
| `load_mv` (OUT) during a charge with the cell below 4.1 V | 4.3–4.5 V and at least 100 mV above VCELL (build-sheet check 9) |

- [ ] Phase A exit criterion 4: a 1 A charge with the shunt in the path ends in a normal termination
  (CHG off and steady, not flashing), and the battery path meets the span limits
  of spec §11.2 and build-sheet check 7: + span ≤ 75 mΩ, − span ≤ 40 mΩ, each pack-side span ≤ 28 mΩ
  (this was "the battery-path drop at 1 A is at most 50 mV" before PT record P8).
  Start at a cell voltage of at least 3.85 V, or confirm the safety timer is off or lengthened
  (spec R11, build-sheet check 10).
- [ ] Results go in a new evidence run directory (never the live one) and in the release's
  `RELEASES.md` entry.
- [ ] Phase A is done when exit criteria 1–4 of spec §2 all hold.
