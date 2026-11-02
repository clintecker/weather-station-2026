# Bench Breadboard Wiring Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A generated KiCad 10 model of the bench station's breadboard build (board A signals, board B power), with jumpers routed by KiCadRoutingTools, checked, rendered, and written up as a hole-by-hole build sheet.

**Architecture:** One data file (`wiring.toml`) holds the parts, their holes and the nets. A stdlib model in the repo's Python 3.12 (`wiring.py`) checks it against the wiring guide and the firmware, plans the jumpers on free holes, and proves the connectivity. It then writes `layout.json`. KiCad 10's own Python (3.9, `pcbnew`) turns `layout.json` into a PCB. Each jumper is a two-pad net between its two planned holes, and every other hole is a netless obstacle. KiCadRoutingTools routes those jumper nets. A Pillow renderer draws the routed board by net class, and the model writes the build sheet.

**Tech Stack:** Python 3.12 (repo `.venv`, stdlib `tomllib`), KiCad 10.0.6 (`pcbnew`, `kicad-cli`), KiCadRoutingTools v0.23.1 (its own venv: numpy, scipy, shapely, Pillow), Pillow for renders.

**Spec:** `docs/superpowers/specs/2026-10-19-bench-breadboard-wiring-design.md`

> **Amended 2026-10-29 (power telemetry).** The bench power wiring of 2026-10-28/29
> (`firmware/benchlink/README.md` "Wiring") is now the official phase A design
> (`docs/superpowers/specs/2026-10-29-power-telemetry-design.md` sections 2 and 11.1). The model
> gains these items; tasks B09 (tooling) and B14 (wiring content) of
> `docs/superpowers/plans/2026-10-29-power-telemetry.md` hold the work.
>
> | Item | Change |
> |---|---|
> | Nets | `ISET` (bq24074 ISET → PB1, ADC1_IN5, `N:CN8.1`) and `VIN_SENSE` (the 20 kΩ (two 10 kΩ in series) over 10 kΩ divider from `CHGR_VBUS` → PA10, ADC1_IN6, `N:CN8.3`; VIN = 3 × the pin), both class `analog`; `INA.VBUS` in `SYS_OUT` (the VBUS jumper on OUT); the MAX17048 `GBAT` on the cell node, not OUT |
> | Header | CN8 (1 × 6, female; UM2592 table 17: CN8.1 = A0 = PB1, CN8.3 = A2 = PA10) |
> | Battery path | short heavy `[[lead]]` entries (cell → INA228 VIN+ → VIN− → charger LIPO), never a breadboard strip: a 0.2 Ω breadboard path ended 1 A charges early |
> | Firmware check | `check_firmware` also reads `ISET_PIN` and `VIN_PIN` in `stage0-node/App/board_inputs.c` and `benchlink/App/benchlink.c`, and checks that each ADC pin's file selects its channel (`ADC_CHANNEL` in `wiring.py`: PB1 = 5, PB2 = 4, PA10 = 6) |
> | Parts | three more 10 kΩ (the divider), the 10 kΩ NTC on THERM, the 1S3P 6,600 mAh pack |
> | Build sheet | checks for ISET and VIN_SENSE before power, the shunt verified against a series reference, the battery-path span limits (+ span ≤ 75 mΩ, − span ≤ 40 mΩ; this said "the shunt resistance" and "the battery-path drop at 1 A (≤ 50 mV)" before PT records M1 and P8), the gauge VCELL against a meter on the cell, INA VBUS = OUT, and a 1 A charge that ends in a normal termination |
>
> The PGOOD/CHG pull-up rule replaces "5 V tolerant": PB8 and PB10 are FT_f with the internal
> pull-ups on, so the pin must stay below VDD + 0.3 V (the bench measured at most 2.9 V).

> **Amended 2026-10-30** (build-progression record
> `docs/superpowers/specs/2026-10-29-build-progression-decisions.md`, decisions D1–D4, N2, N3, P1–P5,
> and Clint's answers in its section 7.1). The 2026-10-29 block above stays as history. The current
> design is the dated 2026-10-30 amendment of the spec. In short:
>
> | Item | Change (2026-10-30) |
> |---|---|
> | Battery path | not to the charger's LIPO pin: the pack → the cut #1131 pigtail → WAGO CELL+ → INA228 terminal → WAGO BATT → the charger's BATT socket (7.1 P3, change A as written); no current through any breadboard contact except the tagged P1 regulator chain |
> | Joints and leads | `[[joint]]` (the WAGOs) and role-tagged `[[lead]]`s (force, sense, signal, supply); the gauge on the CELL+ node by its own lead, its minus unconnected, ground over STEMMA QT (not a Kelvin pair on the cell) |
> | Checks | the D3 checks in `source/checks.py`, all without KiCad |
> | Headers | station signals on the Arduino female headers CN5, CN6, CN8 and CN9; mode B feeds CN6.4 |
> | Regeneration | two tiers: `make.py sheet` (no KiCad) on every model commit, `make.py all` at step exits and net changes; the sheet opens with "Changes from the previous revision" |
> | R_ISET | R9 = 1 kΩ (record 1.4); adopted with change A, read by this workflow from 7.1 P3 "change A as written"; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5) |
>
> **Superseded pins, 2026-10-30** (N2, approved by Clint on 2026-10-30): cups PC0 → **PB5**
> (LPTIM1_IN1 on AF1; D4, CN9.5), rain PB5 → **PB4** (EXTI4; A3, CN8.4). The task text below keeps the
> 2026-10-19 pins as history.

## Global Constraints

- KiCad: 10.0.6. Default app path `/Users/clint/Documents/Codex/2026-10-09/referenced-chatgpt-conversation-this-is-an/work/tools/mount-kicad/KiCad/KiCad.app`, overridable with `KICAD_APP`. Its Python is `Contents/Frameworks/Python.framework/Versions/3.9/bin/python3`, and its CLI is `Contents/MacOS/kicad-cli`.
- KiCadRoutingTools: release v0.23.1, tag commit `a26048ab714e29e56b901fc1962e40eebba100a5`, prebuilt `grid_router-macos-arm64.so` pinned by SHA-256 (recorded in Task 1). Fetched by `tools/fetch-vendor.sh` into `vendor/KiCadRoutingTools` (git-ignored).
- The electrical source of truth is `docs/hardware/bench-station-wiring.md`. No new circuit.
- Breadboard: 830 points, 63 columns, strips a–e and f–j of 5 holes, two rails on each long edge, 2.54 mm grid. A `split_rails` setting covers boards whose rails break at the centre.
- Every output lives in `hardware/bench-breadboard-r0/`. Generation is deterministic: two runs give byte-identical files (UUIDs from `uuid5`).
- Nothing is ordered. Writing standard: ASD-STE100 (sentences of 25 words or fewer, no prose semicolons). Diagrams in Mermaid.
- Commit straight to master and push.

## Rulings (spec gaps settled here)

- **PA9:** not on the breadboard. The wiring guide (section 2) and `App/i2c_bus.lit.md` both say the load switch is protoboard only. Board A carries no PA9 net; the README says so. Cost if wrong: one jumper to add later.
- **PGOOD and CHG** jumper from board B straight to the NUCLEO, not through board A. Fewer hops; the same nets. Cost if wrong: none electrically.
- **Jumper model:** a PCB router connects pads of a net, and a strip's 5 holes are one net, so it could end a jumper on a part's hole. Instead the model picks two free holes per jumper, each jumper becomes its own net (`W1`, `W2`, …) of exactly two pads, and every other hole is a netless pad. The router only finds the path. The electrical proof is the model's connectivity check (strips, jumpers and part pins with union-find), plus KiCad DRC for clearance and completion. The spec's "netlist equals wiring.toml" check becomes this connectivity check. Cost if wrong: none; the check is stricter than a KiCad netlist compare.
- **NUCLEO headers:** drawn beside board A as CN5, CN6, CN7 and CN10. Their pin numbering follows UM2592 (morpho: odd pins in one column, even in the other, pin 1 at the top). Their spacing is schematic, not mechanical, and the render says "not to scale". Cost if wrong: none for wiring.
- **TOML in two Pythons:** KiCad's Python 3.9 has no `tomllib`. Only the repo Python reads `wiring.toml`. The pcbnew script reads `layout.json`.

## Review Focus

1. Two parts whose pins share a strip but belong to different nets: a short. The model must refuse it and name both pins.
2. A strip with no free hole left for a jumper: the model must refuse it and name the strip, not silently reuse a part's hole.
3. Rails split at the centre: with `split_rails = true`, the model must treat each half as its own net and plan bridging jumpers.
4. A wiring-guide header that the model does not use, or a firmware pin constant that moved: the checks must fail with the row and file named.
5. KiCad or the router missing: the KiCad tests must skip with a reason, and the model tests must still run.

---

### Task 1: Toolchain: pinned router, its venv, KiCad discovery

**Files:**
- Modify: `tools/fetch-vendor.sh` (add the KiCadRoutingTools pin after the STM32CubeWL block)
- Create: `tools/kicad_env.py`
- Create: `hardware/bench-breadboard-r0/requirements-router.txt`
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Produces: `tools/kicad_env.py` with `find() -> Env | None`, where `Env` is a frozen dataclass with `python: Path` (KiCad Python), `cli: Path` (kicad-cli), `router: Path` (`vendor/KiCadRoutingTools`) and `router_python: Path` (`vendor/krt-venv/bin/python`), and `missing() -> str` (why `find()` returned None). Tests import `needs_kicad`, a `unittest.skipUnless(find(), missing())` decorator, from `tests/test_breadboard.py`.

- [ ] **Step 1: Write the failing test** `test_toolchain_reports_what_is_missing`: with `KICAD_APP` set to a path that does not exist, `kicad_env.find()` is None and `kicad_env.missing()` contains `KICAD_APP`. Also `test_toolchain_found_when_present`, decorated `@needs_kicad`: `subprocess.run([env.python, '-c', 'import pcbnew; print(pcbnew.Version())'])` prints `10.0.6`, and `env.router/'py_router'/'route.py'` exists.
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_breadboard -v`. Expected: ImportError (no `tools/kicad_env.py`).
- [ ] **Step 3: Pin the router in `tools/fetch-vendor.sh`.** Clone `https://github.com/drandyhaas/KiCadRoutingTools.git` at tag `v0.23.1` into `vendor/KiCadRoutingTools`, verify `HEAD` is `a26048ab714e29e56b901fc1962e40eebba100a5`, download the release asset `grid_router-macos-arm64.so` into the location `build_router.py` installs it to (read that script at the tag), and verify its SHA-256 against a constant. Record the hash from the first download in the script. Then create `vendor/krt-venv` and install `hardware/bench-breadboard-r0/requirements-router.txt`, which pins exact versions of `numpy`, `scipy`, `shapely` and `Pillow` that meet the tool's `requirements.txt` floors (numpy ≥ 1.22, scipy ≥ 1.7, shapely ≥ 2.0, Pillow ≥ 9.2). Skip this block on a platform other than macOS arm64, with a message.
- [ ] **Step 4: Implement `tools/kicad_env.py`.** `KICAD_APP` overrides the default path in Global Constraints. `find()` checks that all four paths exist.
- [ ] **Step 5: Run** `tools/fetch-vendor.sh`, then the tests. Expected: both pass. `vendor/KiCadRoutingTools/py_router/route.py --help` runs in `vendor/krt-venv`.
- [ ] **Step 6: Commit** `tools/fetch-vendor.sh tools/kicad_env.py hardware/bench-breadboard-r0/requirements-router.txt tests/test_breadboard.py`: "Toolchain: KiCadRoutingTools v0.23.1 pinned, KiCad 10 discovery".

### Task 2: The wiring data and the breadboard model

**Files:**
- Create: `hardware/bench-breadboard-r0/source/wiring.toml`
- Create: `hardware/bench-breadboard-r0/source/wiring.py`
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Produces, in `wiring.py` (stdlib only):
  - `Hole = tuple[str, str, int]`: (board `'A'|'B'`, row `'a'..'j'|'L+'|'L-'|'R+'|'R-'`, column 1..63). Off-board pins are `('N', 'CN10', 14)` for the NUCLEO and `('X', '<part id>', <pin number>)` for a part on a cable.
  - `load(path: Path) -> Wiring`. `Wiring` has `parts: dict[str, Part]`, `nets: dict[str, list[str]]` (net name to `'PART.PIN'` members), `split_rails: bool`, `net_class: dict[str, str]` (net to `i2c|wind|rain|charger|power|ground`).
  - `Part` has `id, kind, board, origin: Hole, pins: dict[str, Hole]` (computed from origin, the pin order and the orientation), and `source: str` (the manufacturer page the pin order came from, or `'bench check'`).
  - `strip(h: Hole, split_rails: bool) -> str`: the strip id of a hole. `'A:J14'` and `'A:F14'` give `'A:f-j:14'`; `'A:E14'` gives `'A:a-e:14'`; rail holes give `'A:L+'` (or `'A:L+:1'`/`'A:L+:2'` when split, the halves meeting between columns 31 and 32).
  - `hole_xy(h: Hole) -> tuple[float, float]` in mm. Columns are 2.54 mm apart. Boards A and B sit side by side with a 20 mm gap. Rows a–e and f–j have a 7.62 mm channel between e and f. The rails are 5.08 mm outside a and j.
- `wiring.toml` holds `[[part]]` tables (id, kind, board, origin, orientation, pins in order, source) and `[[net]]` tables (name, class, members). Pin orders come from the manufacturer pages listed under Step 3. Placements follow the spec's section 2 split.

- [ ] **Step 1: Write the failing tests:**
  - `test_strips_join_five_holes`: `strip(('A','j',14))` equals `strip(('A','f',14))` and differs from `strip(('A','e',14))` and `strip(('A','j',15))`.
  - `test_split_rails_are_two_nets`: `strip(('A','L+',1), True)` differs from `strip(('A','L+',63), True)`. With `False` they are equal.
  - `test_every_part_pin_lands_on_its_own_hole`: no two pins of all parts share a hole.
  - `test_the_data_loads_and_names_its_sources`: `load()` succeeds, every `Part.source` is a URL or `'bench check'`, and the nets include `I2C_SDA`, `I2C_SCL`, `CUPS`, `VANE`, `RAIN`, `PGOOD`, `CHG`, `3V3`, `GND`. *Amended 2026-10-29:* and `ISET` and `VIN_SENSE` (PB1 on `N:CN8.1`, PA10 on `N:CN8.3`, class `analog`), now checked by `test_iset_and_vin_sense_are_named_on_cn8` and `test_the_divider_is_20k_over_10k`.
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_breadboard -v`. Expected: ImportError (no `wiring.py`).
- [ ] **Step 3: Write `wiring.toml`.** Take each pin order from its manufacturer page and record the URL in `source`: SparkFun BOB-14021 and the SEN-15901 datasheet (the RJ11 conductors), Adafruit #4755 (bq24074), #5832 (INA228), #5580 (MAX17048), #5625 (STEMMA QT hub) and the Adafruit STEMMA QT to male header cable (its product page), and Pololu #2122 (S7V8F3). A pin order the page does not show gets `source = "bench check"`. The circuits are those of the wiring guide sections 3 and 4: cups and rain each with a 10 kΩ pull-up to 3V3 and 100 nF to GND, and the vane with a 10 kΩ pull-up only. The INA228 shunt sits in the cell's positive lead, and the 100 Ω ½ W load is across the bq24074 output.
- [ ] **Step 4: Implement `wiring.py`** to the Interfaces above.
- [ ] **Step 5: Run** the tests. Expected: PASS.
- [ ] **Step 6: Commit** "Breadboard model: wiring data and strip geometry".

### Task 3: Checks against the wiring guide and the firmware

**Files:**
- Modify: `hardware/bench-breadboard-r0/source/wiring.py`
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Produces `check_guide(w: Wiring, guide: Path) -> list[str]` and `check_firmware(w: Wiring, app: Path) -> list[str]`. Each returns problems (empty if none).
  - `check_guide` reads the section 2 table rows of `bench-station-wiring.md` (Function | Pin | Header | Wiring). For each row the model uses, the NUCLEO header the model picked must appear in the row's Header column. The PA9 row is exempt (ruling). The function also returns a problem for an MCU pin of the model that has no row.
  - `check_firmware` reads `App/board_inputs.c` (`CUPS_PIN`, `VANE_PIN`, `RAIN_PIN`, `PGOOD_PIN`, `CHG_PIN`: the `GPIO_PIN_<n>` value and the `/* P<port><n> */` comment) and `App/i2c_bus.lit.md` (`SDA_PIN`, `SCL_PIN` on GPIOA). The model's MCU pin for each net must match.
  - *Amended 2026-10-29:* `check_firmware(w, firmware)` takes the `firmware/` directory and reads the files of `wiring.FIRMWARE`: `stage0-node/App/board_inputs.c` also gives `ISET_PIN` → `ISET` and `VIN_PIN` → `VIN_SENSE`, and `benchlink/App/benchlink.c` gives the same pins. The comment may carry trailing text (`/* PB1 = A0, CN8.1: ADC1_IN5 */`). For an ADC pin the check also requires that the file selects the pin's channel (`ADC_CHANNEL_5` for PB1, `ADC_CHANNEL_4` for PB2, `ADC_CHANNEL_6` for PA10), and a comment that names another channel is a problem. Tests: `test_the_model_agrees_with_the_firmware`, `test_an_adc_input_needs_its_channel`, `test_the_firmware_reads_iset_and_vin_on_their_adc_channels`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_model_agrees_with_the_wiring_guide`: `check_guide(load(...), GUIDE) == []`.
  - `test_the_model_agrees_with_the_firmware`: `check_firmware(load(...), APP) == []`.
  - `test_a_moved_firmware_pin_is_found`: copy `board_inputs.c` to a temporary directory with `GPIO_PIN_5` changed to `GPIO_PIN_6` on the `RAIN_PIN` line. The result names `RAIN_PIN`.
  - `test_a_header_the_guide_does_not_list_is_found`: a model with the rain net moved to `CN10.31`. The result names the rain gauge row.
- [ ] **Step 2: Run them.** Expected: AttributeError (no `check_guide`).
- [ ] **Step 3: Implement** both functions.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit** "Breadboard model: checked against the wiring guide and the firmware pins".

### Task 4: Jumper planning and the connectivity proof

**Files:**
- Modify: `hardware/bench-breadboard-r0/source/wiring.py`
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Produces:
  - `Jumper` (frozen dataclass): `id: str` (`'W1'…`, in build order: board A first, then board B, then the NUCLEO links, each ordered by net name), `net: str`, `a: Hole`, `b: Hole`.
  - `plan_jumpers(w: Wiring) -> list[Jumper]`. For each net, it groups the strips and the off-board pins that the net's part pins touch. It joins the groups with a minimum spanning tree by `hole_xy` distance. Each tree edge becomes one jumper between a free hole of each group: the hole nearest the other end, never a hole a part pin uses. A rail net with `split_rails` gets a bridging jumper between its halves. It raises `PlanError` naming the strip when a group has no free hole.
  - `connectivity(w: Wiring, jumpers: list[Jumper]) -> dict[str, frozenset[str]]`: union-find over holes, which joins strip members, a jumper's two holes, and a part pin's hole. It returns, for each component that holds a part pin, the set of `'PART.PIN'` it holds, keyed by the declared net of its first member.
  - `prove(w, jumpers) -> list[str]`: problems where `connectivity` differs from `w.nets`. That covers a missing link, a short (one component holding pins of two nets, named both), and a stray pin.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_plan_connects_every_net_and_nothing_else`: `prove(w, plan_jumpers(w)) == []`.
  - `test_no_jumper_lands_on_a_part_pin`: no jumper end equals any part pin hole.
  - `test_a_shared_strip_is_a_short`: move the VANE pull-up's lower pin onto the CUPS strip. `prove` names both nets.
  - `test_a_full_strip_is_refused`: fill a strip of a net with part pins so that it has no free hole. `plan_jumpers` raises `PlanError` naming `'A:a-e:<n>'`.
  - `test_split_rails_get_a_bridge`: with `split_rails = True`, the plan has a jumper whose ends lie in the two halves of the 3V3 rail, and `prove` is still empty.
- [ ] **Step 2: Run them.** Expected: AttributeError.
- [ ] **Step 3: Implement.** Use Prim's algorithm on at most a few dozen groups, with a deterministic tie-break by strip id.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit** "Breadboard model: jumper plan and connectivity proof".

### Task 5: The PCB, routed and checked

**Files:**
- Create: `hardware/bench-breadboard-r0/source/build_pcb.py` (KiCad Python 3.9, reads `layout.json`)
- Create: `hardware/bench-breadboard-r0/source/make.py` (repo Python: model, layout, KiCad, router, checks)
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Consumes: `load`, `plan_jumpers`, `prove`, `check_guide`, `check_firmware`, `hole_xy` (Tasks 2–4), and `kicad_env.find` (Task 1).
- Produces:
  - `make.py layout <out.json>`: it writes the boards, every hole with its xy, and the parts with their pin holes. Each jumper end hole is tagged with its jumper net. It stops if any check returns a problem.
  - `build_pcb.py <layout.json> <out.kicad_pcb>`: a 2-layer board. Each hole is a 1.2 mm round through-hole pad with a 0.8 mm drill. The pad has the jumper net if it is a jumper end, else no net. Each part is a silkscreen outline with its id. The board outline is each breadboard's rectangle plus the NUCLEO header area. The net classes are Default (0.4 mm track, 0.2 mm clearance) and one class per jumper net class, with the colour kept in `layout.json` for the renderer.
  - `make.py route <unrouted.kicad_pcb> <routed.kicad_pcb>`: it runs `py_router/route.py` in `vendor/krt-venv` with `--nets "W*" --grid-step 0.635 --track-width 0.4 --clearance 0.2 --layers F.Cu B.Cu`. A jumper the router leaves unconnected is drawn by `make.py` as a straight segment on `B.Cu` (the spec's fallback), and the run says which.
  - `make.py all`: layout, then PCB, then route, then `kicad-cli pcb drc --exit-code-violations`, writing `hardware/bench-breadboard-r0/bench-breadboard.kicad_pcb` and `.kicad_pro`.

- [ ] **Step 1: Write the failing tests** (decorated `@needs_kicad`):
  - `test_the_routed_board_passes_drc`: after `make.py all` into a temporary directory, the DRC JSON report has 0 violations and 0 unconnected items.
  - `test_each_jumper_is_routed_between_its_planned_holes`: each `W` net in the routed PCB has copper that touches exactly its two planned pads.
  - `test_generation_is_deterministic`: two `make.py all` runs give identical `.kicad_pcb` bytes.
- [ ] **Step 2: Run them.** Expected: FAIL (no `make.py`).
- [ ] **Step 3: Implement** `make.py layout`, `build_pcb.py` and `make.py route`/`all` to the Interfaces.
- [ ] **Step 4: Run them.** Expected: PASS. Note how many jumpers used the fallback. Zero is the goal. More than zero passes, but the README records the count.
- [ ] **Step 5: Commit** the sources, the generated `.kicad_pcb` and `.kicad_pro`, and the tests: "Breadboard map: KiCad 10 PCB, jumpers routed by KiCadRoutingTools, DRC clean".

### Task 6: Schematic, renders, build sheet, README

**Files:**
- Create: `hardware/bench-breadboard-r0/source/build_schematic.py` (repo Python, writes KiCad S-expression text as `chicago-test-hardware-r0/source/build_schematic.py` does)
- Create: `hardware/bench-breadboard-r0/source/render.py` (Pillow)
- Modify: `hardware/bench-breadboard-r0/source/make.py` (`all` also writes the schematic, its PDF, the renders and the build sheet)
- Create (generated): `bench-breadboard.kicad_sch`, `renders/board-a.png`, `renders/board-b.png`, `renders/schematic.pdf`, `build-sheet.md`
- Create: `hardware/bench-breadboard-r0/README.md`
- Modify: `docs/hardware/bench-station-wiring.md` (section 1, step 1: link the renders and the build sheet)
- Modify: `requirements-dev.txt` (add `Pillow` at an exact version, if absent)
- Test: `tests/test_breadboard.py`

**Interfaces:**
- Consumes: `layout.json`, the routed `.kicad_pcb` (segments by net), and `Wiring`/`Jumper` (Tasks 2–5).
- Produces:
  - `build_schematic.py`: one symbol per part with its pins in the manufacturer's order, and a global label of the net name on each connected pin. ERC passes with `kicad-cli sch erc --exit-code-violations`.
  - `render.py <layout.json> <routed.kicad_pcb> <board> <out.png>`: it draws the board's holes (grey), part outlines with ids, and each jumper's routed segments in its net-class colour. It labels each jumper with its id at its midpoint. The NUCLEO headers are labelled "check against UM2592, not to scale". The colours are I2C blue, wind green, rain cyan, charger orange, power red and ground black.
  - `build-sheet.md`: first the parts, in placement order (part, board, holes, source, and "bench check" items). Then the jumpers in `W` order, one line each: `W7  A:J14 → NUCLEO CN10.14  CUPS (wind)` (*superseded 2026-10-30, N2 and N3: CUPS lands on CN9.5, PB5; the sheet now opens with "Changes from the previous revision" and adds the leads, joints and the pre-run checklist*). It ends with a "Bench checks" list: every part with `source = "bench check"`, the split-rail question, and the UM2592 header check.
  - `README.md`: how to regenerate (`tools/fetch-vendor.sh`, then `.venv/bin/python hardware/bench-breadboard-r0/source/make.py all`), what each check proves, the fallback-jumper count, the PA9 ruling, and "Parts still to get" (three 10 kΩ, two 100 nF, one 100 Ω ½ W, jumper wires, a STEMMA QT to header cable, a second BOB-14021).

- [ ] **Step 1: Write the failing tests:**
  - `test_the_schematic_passes_erc` (`@needs_kicad`): the ERC JSON report has 0 errors.
  - `test_the_build_sheet_lists_every_jumper_once`: the `W` lines of `build-sheet.md` equal `plan_jumpers(load(...))` ids, in order, with the planned holes.
  - `test_the_build_sheet_lists_every_bench_check`: every part with `source = "bench check"` appears under "Bench checks".
  - `test_renders_exist_and_are_current` (`@needs_kicad`): `make.py all` into a temporary directory gives PNGs byte-identical to the committed ones.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the schematic, the renderer, the build sheet and the README, and run `make.py all` into `hardware/bench-breadboard-r0/`.
- [ ] **Step 4: Run** the whole file and `tools/gates.sh`. Expected: all pass. Without KiCad, the `@needs_kicad` tests skip with the reason from `kicad_env.missing()`.
- [ ] **Step 5: Look at both renders.** Check that each jumper is visible and labelled and that no label hides another. Fix the renderer if not.
- [ ] **Step 6: Commit** everything: "Breadboard map: schematic, renders, build sheet". Push.
