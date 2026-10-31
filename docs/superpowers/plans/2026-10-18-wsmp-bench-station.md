# WSMP Bench Station Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run every Plan B part on one TX board at the same time as WSMP local modules, hot-pluggable, with every reading reaching the gateway on today's radio protocol.

**Architecture:** A generated registry gives the WSMP codes to C and Python. A portable WSMP core packs and checks the blocks. Seven local module drivers share one interrupt-driven I2C bus layer and three board inputs (pulse counter, ADC, pin interrupt). A station host runs presence, admission and the minute latch. An interim map turns snapshots into today's catalog fields, so `app_tx` sends them as now.

**Tech Stack:** C11 on STM32WL55JC (HAL, ST sequencer and timer server), host builds under ASan/UBSan driven by Python `unittest` + ctypes, Python 3.12 (`tomllib`) for the registry generator and the gateway.

**Spec:** `docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md`, implementing the station side of `docs/module-protocol.md` (WSMP 1.0).

> **Amended 2026-10-29 (power telemetry).** The power part of this plan is superseded by
> `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` and its plan
> `docs/superpowers/plans/2026-10-29-power-telemetry.md`. The changes that touch this plan:
>
> | Item | Was (this plan) | Now |
> |---|---|---|
> | Pins | no power ADC | PB1 = ISET (ADC1_IN5, CN8.1, A0) and PA10 = charger VBUS divider 20 kΩ / 10 kΩ (ADC1_IN6, CN8.3, A2), VIN = 3 × the pin; both analog, no pull (pin table below). *Amended 2026-10-30 (BP M2): ISET reaches PB1 through 10 kΩ at the charger, with 100 nF and 1 MΩ to logic ground at PB1 (gain 990099 ppm until the per-board fit); VIN = the pin × the measured ratio (`POWER_VIN_DIVIDER_PPM`, 3 nominal)* |
> | Pack | battery of the bench station | 1S3P Li-ion, 3 × 2,200 mAh = 6,600 mAh, 3.0–4.2 V |
> | Task 6 module | `mod_power`, type 5 "battery and charger", port `P_POWER`, health class | drivers in `App/power_acq.{c,h}` (rail table in `App/power_config.h`), WSMP face in `App/mod_power.{c,h}`: type 8 battery (port `P_BATTERY` 5) and type 9 power rails (port `P_RAILS` 8), both minute class; type 5 frozen in the registry |
> | Slow battery items | WSMP health channels | the version 6 health report, through `mod_power_health()` |
> | WSMP | 1.0, `WSMP_RADIO_BUDGET 58` | 1.1 (quality 6 "not fitted"), `WSMP_RADIO_BUDGET 60` (WSMP-A1) |
> | I2C topology | one I2C2 bus (PA11/PA12) | the same bus through a passive STEMMA QT hub: `WS_I2C_MUX` 0 is the default (official phase A); the mux profile of the 2026-10-21 ports work is `WS_I2C_MUX` 1 |
>
> Bench lessons that apply to every power task: keep the battery path short and low resistance (a
> 0.2 Ω breadboard path ended 1 A charges early); the MAX17048 senses the cell, not OUT; the INA228
> VBUS jumper goes to OUT. CHG (PB10) and PGOOD (PB8) are FT_f inputs with the internal pull-ups on:
> the pin must stay below VDD + 0.3 V (the bench measured at most 2.9 V).

> **Superseded pins, 2026-10-30** (build-progression record
> `docs/superpowers/specs/2026-10-29-build-progression-decisions.md` decision N2, approved by Clint on
> 2026-10-30 in its section 7.1; change B). Cups: PC0 → **PB5** (LPTIM1_IN1 on AF1; Arduino D4,
> CN9.5). Rain: PB5 → **PB4** (EXTI4; Arduino A3, CN8.4), so the rain handler is `EXTI4_IRQHandler`,
> not `EXTI9_5_IRQHandler`. The pin table and Tasks 8 and 10 below keep the 2026-10-18 pins as
> history. The firmware (`firmware/stage0-node/App/board_inputs.c`) and the breadboard model use the
> new pins.

## Global Constraints

- Greenfield: no back-compat, every board reflashed together.
- Power of Ten as `docs/power-of-ten.md` applies it: complexity ≤ 10 and ≤ 60 lines a function (`tools/code_shape.sh`), bounded loops (`tools/loop_bounds.py`), no heap, **no function pointers of our own** (rule 9: module dispatch is a `switch`, completions are link-time named functions such as today's `sensor_done`), `WS_CHECK` for invariants.
- No blocking waits (`make waits`). Flash is written only while the radio is idle.
- The WSMP core, the I2C bus layer and the station host are literate sources (`*.lit.md`, `tools/tangle.py`); their `.c`/`.h` are generated and committed.
- Writing standard: ASD-STE100 for docs and comments (≤ 25 words a sentence, active voice, no semicolons in prose). Mermaid for state machines and byte layouts.
- Budget: TX flash under the Makefile's 90 % guard of 112,640 B, target about 72 KB (65 %). The final image must stay ≤ 75 %.
- Never loosen a test criterion. Never claim H01 or acceptance from a simulation or smoke test.
- Commit straight to `master` and push. No board, release or gateway-state action without Clint's OK.
- Use the module and register facts below verbatim:

| Part | Address | Identity check | Data |
|---|---|---|---|
| SHT45 | 0x44 | serial command 0x89 answers with CRC-valid words | measure 0xFD, 10 ms, 6 bytes |
| SHTC3 | 0x70 | read ID command 0xEFC8, `(id & 0x083F) == 0x0807` | wake 0x3517, measure 0x7866 (12 ms), sleep 0xB098 |
| BMP581 | 0x47 (0x46 by jumper) | register 0x01 == 0x50 | forced mode, pressure registers 0x20–0x22 (24 bit, Pa × 64) |
| LTR390 | 0x53 | register 0x06 == 0xB2 | UVS mode, data registers 0x10–0x12 (20 bit) |
| INA228 | 0x40 | 0x3E == 0x5449 and `(0x3F >> 4) == 0x228` | VBUS 0x05, CURRENT 0x07 |
| MAX17048 | 0x36 | `(VERSION 0x08 & 0xFFF0) == 0x0010` | VCELL 0x02, SOC 0x04 |

| Function | Pin |
|---|---|
| I2C2 SDA / SCL | PA11 / PA12 (AF4) |
| anemometer, LPTIM1 IN1 | PC0 (AF1); *superseded 2026-10-30 (N2): PB5 (LPTIM1_IN1 AF1, D4, CN9.5)* |
| rain, EXTI5 | PB5; *superseded 2026-10-30 (N2): PB4 (EXTI4, A3, CN8.4)* |
| vane, ADC IN4 | PB2 |
| bq24074 ISET, ADC1_IN5 (added 2026-10-29) | PB1 (CN8.1, A0), analog, no pull. *Amended 2026-10-30 (BP M2): through 10 kΩ at the charger end, with 100 nF and 1 MΩ to logic ground at PB1* |
| charger VBUS divider 20 kΩ / 10 kΩ, ADC1_IN6 (added 2026-10-29) | PA10 (CN8.3, A2), analog, no pull; VIN = 3 × pin. *Amended 2026-10-30 (BP M2): × the measured ratio, `POWER_VIN_DIVIDER_PPM` (3 nominal)* |
| bq24074 PGOOD / CHG | PB8 / PB10, inputs with pull-up (FT_f: stay below VDD + 0.3 V; CHG also counts edges on EXTI10 since 2026-10-29) |
| sensor 3.3 V switch | PA9, output |

## Ruling for Clint (spec deviation, to confirm at the plan review)

The spec (section 4) latches at second 50 of the UTC minute. Today the minute report follows the
fourth 15-s sample after boot, and `tests/test_tx_machine.py` pins that timing. Moving the minute to
UTC is sub-project 4's change ("UTC-aligned sampling", 16-station spec §6.2). **This plan keeps the
existing minute grid as the latch clock.** The latch at :50 UTC arrives with sub-project 4. Task 9
updates the spec text to say so. Cost if wrong: one later timing change, which sub-project 4 makes
anyway.

## Review Focus

1. **A sensor unplugged in the middle of an I2C transfer.** The bus recovers, the other modules keep reading, and only the unplugged module's channels go missing. Test: Task 3 `test_unplug_mid_transfer_recovers_and_spares_other_clients`.
2. **A sample in flight when the latch comes.** The sample lands in exactly one window, never in both, never lost. Test: Task 4 `test_sample_straddling_latch_counts_once`.
3. **LPTIM wrap and asynchronous reads at high pulse rates.** No pulse is lost across a 16-bit wrap between 250 ms reads, and a torn counter read is retried. Test: Task 7 `test_counter_wrap_and_torn_read`.
4. **Modules coming and going while the station runs.** Each reading's bitmap and length match the modules active at its latch, with no stale field from a removed module. Test: Task 10 `test_bitmap_follows_active_modules`.
5. **A power cut during the rain setting's meta append.** The setting recovers to the last committed value. Test: Task 8 `test_rain_setting_survives_torn_append`.

---

### Task 1: The registry and its generator

**Files:**
- Create: `firmware/common/wsmp_registry.toml` (WSMP section 4 tables), `tools/wsmp_registry.py`, `tools/wsmp_registry.lock`
- Create (generated, committed): `firmware/common/wsmp_registry.h`, `ws0/wsmp_registry.py`
- Modify: `tools/code_shape.sh` (run `tools/wsmp_registry.py --check` beside `tangle --check`)
- Test: `tests/test_wsmp_registry.py`

**Interfaces:**
- Produces (C): enums `WSMP_Q_*` (quantities 1–17), `WSMP_U_*` (units 1–13), `WSMP_K_*` (kinds 1–10), `WSMP_T_*` (module types 1–7), `WSMP_RC_MINUTE`/`WSMP_RC_HEALTH`; `uint8_t wsmp_canonical_unit(uint16_t quantity)` (0 if unknown); `const wsmp_type_entry *wsmp_type(uint16_t type)` (NULL if unknown) with `struct wsmp_type_entry { uint16_t type; uint8_t schema, channels, report_class; struct { uint16_t quantity; uint8_t kind; } ch[8]; }`; factors as integers: `WSMP_WIND_UMS_PER_HZ 666980` (µm/s per Hz), `WSMP_WIND_GUST_MS 3000`, `WSMP_RAIN_UM_PER_TIP 279400`; `WSMP_REGISTRY_VERSION 1`.
- Produces (Python): `QUANTITIES`, `UNITS`, `KINDS`, `MODULE_TYPES` dicts keyed by code, with names, CF/UCUM strings, Home Assistant `device_class`/`state_class`, factors; `REGISTRY_VERSION`.

- [ ] **Step 1: Write the failing tests**

```python
class Registry(unittest.TestCase):
    def test_tables_match_wsmp_section_4(self):
        from ws0 import wsmp_registry as r
        self.assertEqual(r.QUANTITIES[6]['unit'], 5)              # wind from direction, deg
        self.assertEqual(r.QUANTITIES[17]['ucum'], '{pulse}')
        self.assertEqual(r.MODULE_TYPES[5]['report_class'], 'health')
        self.assertEqual([tuple(c) for c in r.MODULE_TYPES[6]['channels']], [(17, 6), (5, 7), (6, 8), (6, 9)])
        self.assertEqual(r.MODULE_TYPES[7]['factors']['um_per_tip'], 279400)
    def test_codes_are_append_only(self):   # every code in tools/wsmp_registry.lock keeps its name
    def test_generated_files_are_current(self):   # tools/wsmp_registry.py --check exits 0
    def test_check_detects_a_stale_header(self):  # edit a copy of the header in a temp dir: --check exits 1
    def test_c_header_compiles_and_agrees(self):  # compile a printer against wsmp_registry.h, compare with the Python tables
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m unittest tests.test_wsmp_registry -v` → `ModuleNotFoundError: ws0.wsmp_registry`.
- [ ] **Step 3: Write the TOML** with exactly the WSMP section 4 rows (codes, names, CF names, UCUM, physical ranges, module types, channel lists, report classes, roles, factors). The lock file lists `table code name` per line.
- [ ] **Step 4: Write `tools/wsmp_registry.py`** — reads the TOML with `tomllib`, refuses a lock violation, writes both outputs with a `GENERATED from firmware/common/wsmp_registry.toml` banner, `--check` compares without writing (same exit convention as `tools/tangle.py`).
- [ ] **Step 5: Generate, run the tests, expect PASS** — `.venv/bin/python tools/wsmp_registry.py && .venv/bin/python -m unittest tests.test_wsmp_registry -v`.
- [ ] **Step 6: Commit** — `git add firmware/common/wsmp_registry.* tools/wsmp_registry.* ws0/wsmp_registry.py tools/code_shape.sh tests/test_wsmp_registry.py && git commit -m "WSMP registry: one TOML file, generated C and Python, append-only lock"`.

### Task 2: The WSMP core

**Files:**
- Create: `firmware/common/wsmp.lit.md` → `wsmp.c`, `wsmp.h`
- Create: `firmware/fuzz/fuzz_wsmp.c`, `firmware/fuzz/corpus/wsmp/*` (one valid file per block)
- Modify: `firmware/fuzz/Makefile` (`TARGETS += wsmp`)
- Test: `tests/test_wsmp_core.py`

**Interfaces:**
- Consumes: Task 1's `wsmp_registry.h`.
- Produces:
  - sizes `WSMP_IDENTITY_LEN 32`, `WSMP_DESC_LEN 6`, `WSMP_DESC_BLOCK_LEN 48`, `WSMP_SNAPSHOT_LEN 72`, `WSMP_STATUS_LEN 32`, `WSMP_MAX_CHANNELS 8`, `WSMP_RADIO_BUDGET 58`;
  - `typedef struct { uint16_t quantity; uint8_t unit; int8_t scale; uint8_t width, is_signed, kind; } wsmp_desc;`
  - `typedef struct { uint16_t type; uint8_t schema, channels, fw_major, fw_minor; uint16_t fw_build, caps; uint64_t serial; uint32_t boot_id, desc_digest; } wsmp_identity;`
  - `typedef struct { uint32_t value; uint16_t count; uint8_t quality; } wsmp_slot;` and `typedef struct { uint16_t token, boot16, window_ms; uint8_t flags, desc_tag; wsmp_slot slot[WSMP_MAX_CHANNELS]; } wsmp_snapshot;`
  - `void wsmp_pack_identity(const wsmp_identity *, uint8_t out[WSMP_IDENTITY_LEN]); int wsmp_unpack_identity(const uint8_t in[WSMP_IDENTITY_LEN], wsmp_identity *);` and the same pair for `desc` (`n` descriptors into the 48-byte block, zero-filled) and `snapshot`;
  - `int wsmp_desc_check(const wsmp_desc *d, unsigned n, uint16_t type, uint8_t schema);`
  - `uint32_t wsmp_crc32c(const uint8_t *p, size_t n);`
  - `uint8_t wsmp_quality_air(uint8_t q);` (the WSMP section 9 table)
  - `unsigned wsmp_values_bytes(const wsmp_desc *d, unsigned n);` and `unsigned wsmp_quality_bytes(unsigned channels);` (`(2 × channels + 7) / 8`)
  - `int wsmp_text_ok(const uint8_t *p, size_t n);`
  - errors `WSMP_OK 0, WSMP_EMAGIC -1, WSMP_EVERSION -2, WSMP_ECODE -3, WSMP_EUNIT -4, WSMP_ESCALE -5, WSMP_ERESERVED -6, WSMP_ETYPE -7, WSMP_ELEN -8, WSMP_ETEXT -9`.

- [ ] **Step 1: Write the failing tests** (host library built with `toolchain.host_library`, ASan/UBSan):

```python
def test_snapshot_round_trip_matches_the_wsmp_layout(self):
    raw = pack_snapshot(token=0x1234, boot16=7, window_ms=60000, flags=1, desc_tag=0xAB, slots=[(0xFFFFFF38, 4, 0)])
    self.assertEqual(raw[:8].hex(), '12340007ea6001ab')
    self.assertEqual(raw[8:16].hex(), 'ffffff3800040000')
    self.assertEqual(len(raw), 72); self.assertEqual(raw[16:], bytes(56))
def test_desc_check_refuses_each_wsmp_d7_case(self):
    # unknown quantity -> ECODE, unit != canonical -> EUNIT, scale 7 -> ESCALE, reserved bit -> ERESERVED,
    # channel list != registry entry for the type -> ETYPE; the registry entry itself -> OK
def test_crc32c_known_vector(self): self.assertEqual(crc32c(b'123456789'), 0xE3069283)
def test_quality_air_table(self): self.assertEqual([qa(q) for q in range(6)], [0, 1, 2, 3, 1, 3])
def test_identity_refuses_bad_magic_and_major(self)
def test_budget_bytes_for_the_bench_station(self):   # the WSMP 11.3 table: 23 value bytes, 3 quality bytes
def test_text_ok_charset(self)                      # WSMP-M1
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m unittest tests.test_wsmp_core -v` → build error, `wsmp.c` missing.
- [ ] **Step 3: Write `wsmp.lit.md`** (prose per WSMP sections 5–6, packet diagrams, code chunks), tangle it. Big-endian with the `ws_be.h` cursor helpers. Every length checked before a read.
- [ ] **Step 4: Run, expect PASS**; then the fuzz target: `make -C firmware/fuzz check RUNS=1000000` → `fuzz wsmp` passes with no fault.
- [ ] **Step 5: Commit** — `git add firmware/common/wsmp.* firmware/fuzz tests/test_wsmp_core.py && git commit -m "WSMP core: blocks, descriptor checks, CRC-32C, quality, budget; fuzzed"`.

### Task 3: The shared I2C bus layer and its host model

**Files:**
- Create: `firmware/stage0-node/App/i2c_bus.lit.md` → `i2c_bus.c`, `i2c_bus.h` (the bus parts of `sensor.lit.md`: HAL setup, interrupt callbacks, guard timer, stuck-bus recovery through `ws_i2c_recover_step`)
- Create: `firmware/host/i2c_sim.{c,h}` (a multi-device bus model; devices register by address with read/write handlers selected by a `switch` on a device kind)
- Create: `firmware/host/wsmp_harness.c` (sim board for Tasks 3–9: `sim_core`, `i2c_sim`, later the GPIO/LPTIM/ADC fakes)
- Test: `tests/test_i2c_bus.py`

**Interfaces:**
- Produces: `enum i2c_client { I2C_C_SHT45, I2C_C_BMP581, I2C_C_LTR390, I2C_C_SHTC3, I2C_C_INA228, I2C_C_MAX17048, I2C_C_COUNT };`
  `void i2c_bus_init(void);`
  `int i2c_bus_submit(enum i2c_client c, uint8_t addr7, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen);` (0 queued, -1 client already has a transfer)
  `void i2c_bus_done(enum i2c_client c, int rc);` — a link-time seam defined by the module layer (Task 4); rc `0`, `I2C_ENACK_ADDR -2`, `I2C_ENACK_DATA -3`, `I2C_ECRC -4` (modules only), `I2C_ESTUCK -5`, `I2C_ETIMEOUT -6`.
  `void i2c_bus_power(int on);` (PA9).
- One transfer on the bus at a time, served in submission order. A 30 ms guard per transfer. After a stuck bus: recovery, then `I2C_ESTUCK` to the client whose transfer failed and a fresh start for the queue.
- Note: `i2c_bus.c` defines the HAL I2C callbacks, as `sensor.c` does now. The firmware link takes it only in Task 10, when `sensor.c` goes. Until then it builds in host tests only.

- [ ] **Step 1: Port the six cases of `tests/test_sensor_machine.py` to the bus (one client), then write the new ones:**

```python
def test_clients_are_served_in_order_one_at_a_time(self)
def test_a_second_submit_from_a_busy_client_is_refused(self)          # -1
def test_guard_timeout_reports_etimeout(self)
def test_unplug_mid_transfer_recovers_and_spares_other_clients(self):  # Review Focus 1
    # three clients queued; device of client 1 vanishes holding SDA low mid-read:
    # client 1 gets I2C_ESTUCK, clients 0 and 2 complete with 0, the queue keeps going
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m unittest tests.test_i2c_bus -v`.
- [ ] **Step 3: Write `i2c_bus.lit.md`** and `i2c_sim.c`. Tangle.
- [ ] **Step 4: Run, expect PASS**, and `tests.test_sensor_machine` still passes (sensor.c untouched).
- [ ] **Step 5: Commit** — `git commit -m "I2C bus layer for many clients, with a multi-device host model"`.

### Task 4: The local module layer and the two temperature-humidity modules

**Files:**
- Create: `firmware/stage0-node/App/wsmp_local.{c,h}`, `App/mod_sht45.{c,h}`, `App/mod_shtc3.{c,h}`
- Modify: `firmware/host/i2c_sim.c` (SHT45 and SHTC3 models), `firmware/host/wsmp_harness.c`
- Test: `tests/test_modules.py` (a `Conformance` mixin with the WSMP section 14 checks that every module class reuses)

**Interfaces:**
- Consumes: Task 2 core, Task 3 bus.
- Produces: ports `enum wsmp_port { P_AIR_TH = 1, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN, P_COUNT };` and, each a `switch` on the port:
  `void local_tick(enum wsmp_port p, uint32_t now_ms);` (called every 250 ms; the module samples and probes on its own schedule)
  `int local_probe_result(enum wsmp_port p, uint16_t *seq);` (`1` present, `0` absent, `-1` bus fault; `seq` increases with each probe)
  `void local_identity(enum wsmp_port p, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);`
  `void local_latch(enum wsmp_port p, uint16_t token, uint32_t utc);`
  `void local_snapshot(enum wsmp_port p, uint8_t snap[WSMP_SNAPSHOT_LEN]);`
  `i2c_bus_done(c, rc)` defined here, dispatching to `mod_*_i2c_done(rc)`.
- Each module samples every 15 s on the 250 ms tick in two steps (start, then fetch after the measurement time). Probing happens only in the module's own probe slot, never during a measurement (WSMP-B2). Boot ID = `node.boot_epoch` (WSMP-I2). Serial: the SHT45 serial; for parts without one, `0x5753_0000_0000 | (port << 8) | type` (never 0).

- [ ] **Step 1: Write the failing tests:**

```python
class Sht45(Conformance, unittest.TestCase):   # Conformance: identity fields, desc_check OK, latch/read twice same bytes,
    PORT = 1                                   # repeated token does not open a window, slots after the last are zero
    def test_minute_mean_of_four_samples(self):    # model gives 20.00,20.10,20.20,20.30 °C -> value 2015 (scale -2), count 4, quality 0
    def test_three_samples_is_partial(self)        # quality 1
    def test_absent_is_missing(self)               # quality 3, count 0
    def test_nack_during_measurement_is_not_absence(self)  # probe result stays 1 (WSMP-B2)
    def test_sample_straddling_latch_counts_once(self):     # Review Focus 2: latch between start and fetch;
        # the fetched sample appears in exactly one snapshot
class Shtc3(Conformance, unittest.TestCase): PORT = 4
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m unittest tests.test_modules -v`.
- [ ] **Step 3: Implement** `wsmp_local.c` (switch dispatch), `mod_sht45.c` (the SHT45 logic of `sensor.lit.md` on the bus; means with `ws_th_*` from `stage0.c`), `mod_shtc3.c`, the two models.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "WSMP local modules: dispatch layer, SHT45 and SHTC3"`.

### Task 5: Pressure and UVA modules

**Files:** Create `App/mod_bmp581.{c,h}`, `App/mod_ltr390.{c,h}`; modify `firmware/host/i2c_sim.c`; test `tests/test_modules.py`.

**Interfaces:** Consumes Task 4's layer (ports `P_PRESSURE`, `P_UVA`). BMP581: forced mode every 15 s, pressure channel at scale −1 hPa, air width 2. LTR390: UVS mode, gain and resolution fixed, mean counts, air width 3.

- [ ] **Step 1: Failing tests:** `class Bmp581(Conformance)`: `test_pressure_mean_scale` (model 101,325 Pa → value 10133, i.e. 1013.3 hPa), `test_wrong_chip_id_is_absent` (0x51 → probe 0). `class Ltr390(Conformance)`: `test_uva_mean_counts`, `test_wrong_part_id_is_absent`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** both drivers and models.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "WSMP modules: BMP581 pressure and LTR390 UVA"`.

### Task 6: The battery and charger module

> **Amended 2026-10-29.** This task is superseded. The power drivers are `App/power_acq.{c,h}` with
> the rail table in `App/power_config.h` (INA228 rails read every second through SHUNT_CAL check,
> VBUS and CHARGE; MAX17048 every 15 s; ISET, the charger input divider and VREFINT from the
> board ADC sequence in `App/board_inputs.c`). `App/mod_power.{c,h}` is now only the WSMP face: the
> battery module (type 8, port `P_BATTERY`) and the power rails module (type 9, port `P_RAILS`),
> both minute class, plus `mod_power_health()` for the health report. The battery current sign is
> + into the cell (the phase A INA228 counts the other way, so the rail table applies sign −1). The
> charge and energy counters now come from the INA228 CHARGE register and the cell voltage, not from
> V × I sums of VBUS. Tasks B15 and B18 of `docs/superpowers/plans/2026-10-29-power-telemetry.md`
> hold the current work; the text below is the record of the original task.

**Files:** Create `App/mod_power.{c,h}`; modify `i2c_sim.c` (INA228, MAX17048), `wsmp_harness.c` (GPIO fake for PB8/PB10); test `tests/test_modules.py`.

**Interfaces:** Port `P_POWER`, module type 5, health class. Once a second: read VBUS and CURRENT; integrate signed V × I × dt into energy in/out and I × dt into charge in/out (counters since boot at scale −3: 1 mWh and 1 mAh. The module keeps the remainder below one step internally, so no charge is lost to rounding; the INA228 CHARGE register is a cross-check only). At the latch: voltage mean (scale −3 V), the four counters, SoC point (MAX17048, 1 %), charger state from PGOOD/CHG (0 off: PGOOD high; 1 charging: both low; 2 done: PGOOD low, CHG high; 3 fault: not decodable). The module is present when INA228 is present; MAX17048 absent makes only SoC missing.

- [ ] **Step 1: Failing tests:** `test_charge_and_discharge_counters` (model +500 mA for 60 s, then −250 mA for 120 s: charge in = 8 and charge out = 8 (8.33 mAh each, the remainder kept), then another +500 mA for 60 s makes charge in = 16 (16.67 mAh)), `test_counters_never_reset_at_latch`, `test_charger_states_from_pins` (all four pin combinations), `test_soc_missing_without_gauge`, `Conformance`.
- [ ] **Step 2–4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** — `git commit -m "WSMP module: battery and charger (INA228, MAX17048, bq24074 pins)"`.

### Task 7: The wind module

**Files:** Create `App/mod_wind.{c,h}`, `tests/wsmp_wind_ref.py` (Python reference); modify `firmware/host/include` (LPTIM and ADC stand-ins), `wsmp_harness.c` (pulse and vane injection); test `tests/test_modules.py`.

**Interfaces:** Port `P_WIND`, type 6. Every 250 ms read LPTIM1's 16-bit counter (read until two reads agree, at most 3 reads) and add the wrapped difference to a 32-bit pulse total. Gust: the largest sum of 12 consecutive quarter-second bins × `WSMP_WIND_UMS_PER_HZ` ÷ 3 s, scale −2 m/s. Vane: one ADC conversion a second through the interrupt API (`HAL_ADC_Start_IT`), decoded by 16 voltage windows (a table in `mod_wind.c`, measured on the bench in Task 11), adding sin θ and cos θ at scale −2 to the east and north sums. A reading at the rail (> 3.2 V) means no vane: probe result 0.

- [ ] **Step 1: Failing tests:**

```python
def test_pulse_counter_and_gust_match_reference(self)   # pulse trains from wsmp_wind_ref.py
def test_vector_sums_for_each_of_16_positions(self)
def test_350_and_10_degrees_average_to_0(self)          # from the sums, never by averaging angles
def test_counter_wrap_and_torn_read(self):              # Review Focus 3: 70,000 pulses between reads across a wrap,
    # plus a counter read that changes between the two reads: total exact
def test_no_vane_is_absent(self)
```

- [ ] **Step 2–4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** — `git commit -m "WSMP module: wind (LPTIM pulses, 3-s gust, vane vector sums)"`.

### Task 8: The rain module and its stored setting

**Files:** Create `App/mod_rain.{c,h}`; modify `firmware/stage0-node/App/node_store.lit.md` (regenerate `node_store.{c,h}`), `firmware/test_store.c`, `tests/test_store_powercut.py`; test `tests/test_modules.py`.

**Interfaces:** Port `P_RAIN`, type 7. EXTI5 (*superseded 2026-10-30, N2: EXTI4 on PB4*) counts tips with a 100 ms lockout; counter since boot, air width 2. Presence = the stored setting (WSMP-P1).
- `node_store`: a new meta record `META_RAIN 0xA1`, kept like the other maxima. `int store_rain_set(int on);` writes the next value whose bit 0 equals `on` (the smallest value above the current maximum with that parity), so the max-only meta log keeps "latest wins". `int store_rain_enabled(void);` returns bit 0 of the maximum. Compaction carries it like the others.

- [ ] **Step 1: Failing tests:** `test_twenty_tips_count_twenty`, `test_bounce_inside_lockout_is_one_tip`, `test_disabled_is_absent`; in `test_store.c` + `tests/test_store_powercut.py`: `test_rain_setting_latest_wins` and `test_rain_setting_survives_torn_append` (Review Focus 5: the power-cut sweep over the append keeps either the old or the new setting, never a third state).
- [ ] **Step 2–4:** run FAIL, implement, run PASS (`tests.test_store_powercut`, `tests.test_modules`).
- [ ] **Step 5: Commit** — `git commit -m "WSMP module: rain, with a latest-wins setting in the meta log"`.

### Task 9: The station host

**Files:** Create `firmware/stage0-node/App/wsmp_host.lit.md` → `wsmp_host.{c,h}`; modify the spec (`docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md` section 4: the latch follows the existing minute until sub-project 4); test `tests/test_wsmp_host.py`.

**Interfaces:**
- Consumes: Tasks 2 and 4–8.
- Produces: `void wsmp_host_init(void);` `void wsmp_host_tick(uint32_t now_ms);` (the 250 ms tick: module ticks, probe accounting, the state machine) `void wsmp_host_latch(uint32_t utc);` (token + 1, latch every Active port, read its snapshot, count misses) `const wsmp_snapshot *wsmp_host_snapshot(enum wsmp_port p);` (NULL unless Active) `int wsmp_host_state(enum wsmp_port p);` (Absent, Probing, Identifying, Admitted, Active, Suspect, Quarantined, Refused) `unsigned wsmp_host_modules_line(char *buf, unsigned len);` (the `MODULES` text).
- Rules: two good probes in a row before Identifying; three latches without a good read to Absent; a bus fault sets quality 3 and keeps the port Active; a new module joins at the next latch; more than 4 descriptor-set changes from one port in an hour → Quarantined for one hour; admission refuses a module when `Σ wsmp_values_bytes + wsmp_quality_bytes(Σ channels)` over the minute-class modules would pass `WSMP_RADIO_BUDGET`.

- [ ] **Step 1: Failing tests:** `test_two_probes_then_admitted_at_next_latch`, `test_three_missed_latches_then_absent`, `test_bus_fault_keeps_layout`, `test_flap_limit_quarantines_for_an_hour`, `test_admission_refuses_over_budget` (shrink the budget in a test build), `test_bad_descriptor_quarantines`, `test_modules_line_lists_every_port`.
- [ ] **Step 2–4:** run FAIL, write `wsmp_host.lit.md` with the WSMP section 7 state diagram, tangle, run PASS.
- [ ] **Step 5: Commit** — `git commit -m "WSMP station host: presence, admission, latch, flap limit"`.

### Task 10: Integration into the TX firmware

**Files:**
- Create: `firmware/stage0-node/App/wsmp_catalog_map.{c,h}`
- Modify: `App/app_tx.lit.md` (replace `sensor_start`/`sensor_done`/`th_window` with a 250 ms module tick and the minute latch on the existing fourth-tick phase; encode with the reading's own bitmap and compare with `ws_obs_plain_len`), `App/node_fields.h` (`WS_NODE_FIELDS` = every field of spec section 5), `App/tx_console.c` (`MODULES`, `SENSOR rain on|off`), board init (`Core/Src/gpio.c` and a new `App/board_inputs.c` for PC0 AF1 LPTIM1, PB2 analog, PB5 EXTI with `EXTI9_5_IRQHandler` (*superseded pins 2026-10-30, N2: PB5 AF1 LPTIM1 and PB4 EXTI with `EXTI4_IRQHandler`*), PB8/PB10 inputs, PA9 output), `Core/Inc/stm32wlxx_hal_conf.h` (enable ADC and LPTIM), `firmware/stage0-node/Makefile` (`HAL_EXTRA += adc adc_ex lptim`, the new sources, drop `App/sensor.c`), `firmware/host/tx_harness.c` and `tests/test_tx_machine.py` (the SHT45 now through `i2c_sim`)
- Delete: `App/sensor.lit.md`, `sensor.c`, `sensor.h`, `firmware/host/sensor_harness.c`, `tests/test_sensor_machine.py` (its cases live in `tests/test_i2c_bus.py` and `tests/test_modules.py`)
- Test: `tests/test_wsmp_map.py`, `tests/test_tx_machine.py`

**Interfaces:** `void wsmp_map_obs(ws_obs_t *o);` fills `o->bitmap` and `o->code[]` from the Active snapshots by the spec section 5 table (CALM below 0.5 m/s; INVALID for quality 3).

- [ ] **Step 1: Failing tests:** `test_map_round_trip_through_the_gateway_decoder` (snapshots → `wsmp_map_obs` → `ws_obs_encode` → `ws0.fields.decode` gives the expected values for every field of the table), `test_bitmap_follows_active_modules` (Review Focus 4: remove a module, then the next reading has neither its fields nor a stale value, and its length matches `ws_obs_plain_len`), `test_calm_direction`, `test_battery_current_from_charge_increment`; in `tests/test_tx_machine.py`, keep every existing test green with the SHT45 behind the bus and add `test_modules_console_line`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**, tangle `app_tx.lit.md`.
- [ ] **Step 4: Run the whole gate suite:** `tools/gates.sh` (ruff, code shape, cppcheck, two identical builds with the flash budget and no heap, rangetest, analyzer, stack bound, waits, unit tests, fuzz 1M, rule 1). Expected: every gate PASS; `make ROLE=tx` prints `flash budget: N of 112640 B` with N ≤ about 74,000 (if larger, record the size and the reason in the ledger, do not raise the guard).
- [ ] **Step 5: Commit** — `git commit -m "TX firmware on WSMP local modules, mapped onto today's catalog"`.

### Task 11: Wiring guide and documentation

**Files:** Create `docs/hardware/bench-station-wiring.md`; modify `firmware/stage0-node/README.md` (pin table, console commands `MODULES` and `SENSOR`), `docs/module-protocol.md` (a status line: station side implemented for local modules), `docs/protocol-design.md` (this build does not send fields 21–24).

- `bench-station-wiring.md` holds: the breadboard and protoboard wiring per spec section 2 (with the resistor and filter values), the power modes and the switching table of spec section 3, the UM2592 checklist (every pin, header position, solder bridge, the CN7.16 power jumpers; *amended 2026-10-30, record N3: the mode-B entry at steps 1 and 2 is CN6.4, the same 3V3 net*), and the vane window measurement procedure. Mermaid for the wiring blocks.

- [ ] **Step 1:** Write the docs. **Step 2:** validate the Mermaid blocks with Mermaid 11.4.1 (the version `tools/tangle.py` loads; a Node + jsdom check) → `0 failed`; the STE checks (sentences ≤ 25 words, no prose semicolons). **Step 3: Commit** — `git commit -m "Docs: bench station wiring, power modes, console commands"`.

### Task 12: Bench check and acceptance (needs Clint and the hardware)

Not automated. Each step needs Clint's OK for any board action.

- [ ] **Step 1:** Clint checks the pin map against UM2592 with the checklist of Task 11.
- [ ] **Step 2:** Cut a release (`firmware/stage0-node/RELEASES.md`, "How to cut a release") and flash both boards after Clint's OK.
- [ ] **Step 3: Breadboard check** (spec section 6, items 1–5). Record the results and the measured vane windows; put the windows into `mod_wind.c` with a test, commit.
- [ ] **Step 4: Protoboard 24-hour run.** Acceptance per spec section 6: ≥ 99 % of minutes committed within 120 s, every channel good in ≥ 99 % of minutes, no `WS_CHECK` failure, no unexpected reset. Record it in `RELEASES.md` and `evidence/`.
