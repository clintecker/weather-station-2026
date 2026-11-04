# Breadboard mock-up tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reusable engine, `tools/breadboard/`, that turns a short Python bench description plus its netlist into checked, audited, deterministic wiring plans, 2D build cards, KiCad schematics, boards and 3D renders, with bench r1 ported onto it as the golden test and a personal skill that carries the workflow.

**Architecture:** Benches are authored in Python (`author.py` API) and compiled to one canonical, sorted `bench.json`; every later stage (rules, router, plan, cards, KiCad, audit) reads only `bench.json` and `routes.json`. Code is extracted from r1's one-off scripts (`hardware/bench-breadboard-r1/layout/{build,routing,kicad_layout,outputs}.py`, `schematic/{kicad_gen,checks}.py`) and generalised; r1's current outputs are frozen as fixtures first and every task proves it still reproduces them.

**Tech Stack:** Python 3.12, standard library, numpy (router), Pillow (render compositing only), KiCad 10 `kicad-cli` (ERC, netlist, PDF, renders; optional at test time), `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-03-breadboard-tooling-design.md` (approved 2026-11-04). Read it before any task.

## Global Constraints

- Python 3.12; run everything with `.venv/bin/python` from the repo root. Dependencies: stdlib + `numpy` (pin `numpy==2.3.4` in `requirements-dev.txt`) + `Pillow==11.3.0` (already pinned). No matplotlib.
- Package: `tools/breadboard/` with `__init__.py` and `__main__.py`; invoked as `.venv/bin/python -m tools.breadboard <op> <bench dir>`. `tools/` itself stays a script folder (no `tools/__init__.py`; it is an implicit namespace).
- Tests: `unittest`, files `tests/test_bbtool_*.py` (never `test_breadboard*`, which are r0's), fixtures under `tests/fixtures/bbtool/`. Run all: `.venv/bin/python -m unittest discover -s tests -p 'test_bbtool_*.py'`. Tests needing KiCad use `@unittest.skipUnless(shutil.which("kicad-cli"), "needs KiCad 10 (kicad-cli)")`.
- Evidence outputs are byte-identical across runs and hosts: sorted keys and lists, floats `round(x, 4)` with `-0.0` written as `0.0`, `json.dumps(..., sort_keys=True, indent=1, ensure_ascii=False)` + trailing newline, no timestamps, absolute paths or hostnames, KiCad UUIDs from `uuid5`.
- Board convention (Elegoo 830): rows a-e top half, f-j bottom half; column 62 at the left, 1 at the right; rails T+ (outer), T- above row a; B+, B- (outer) below row j; rail holes beside columns 3-7, 9-13 ... 57-61. Hole names `BB1:h24`, `BB1:B-52`.
- Rule IDs exactly: S1, E1, E2, H1, H2, H3, F1, J1, L1, P1, R1, B* (bench rules). Classes: correctness = S1 E1 E2 H1 H2 H3 F1 J1 R1 B*; limit = L1 P1. Correctness failures block every downstream stage; limit failures do not; `check --strict` fails on either.
- Bench r0 (`hardware/bench-breadboard-r0/`), `tools/preflight.py` and `tools/benchlink_log.py` are not touched.
- **No commits.** The user commits when they ask. Each task ends at a checkpoint (tests green, `ruff check` clean); never run `git commit` or `git push`.
- Never read or print anything under `run*/` directories.
- No Mermaid in any generated or written document.

## Review Focus

- A misspelled or impossible hole (`BB1:k5`, `BB1:B-8` in a rail gap, `BB4:a1`, `BB1:a63`) in `bench.py` must give an S1/H1 finding naming the hole and the item, never a Python traceback. Test in Task 3 (`test_bad_hole_names_are_findings`).
- A seat whose header runs off the board end (U1 seated at `BB1:a5` so pins land at columns 4..-5) must give H3 findings per pin, not an exception. Test in Task 5 (`test_seat_off_board_end`).
- A wire the router cannot reach must give an R1 failure naming the wire ID and must block plan/cards/KiCad, with no exception. Test in Task 6 (`test_unroutable_wire_is_r1_failure`).
- A machine without KiCad must still build every evidence output (`all` without `--render`), and KiCad-only steps must print one line saying what was skipped. Test in Task 11 (`test_all_without_kicad`).
- Float output must be stable across macOS and Linux: `-0.0`, `1e-05`-style tiny values and rounding at the 4th decimal. Test in Task 3 (`test_canonical_floats`).

---

### Task 1: Freeze r1's golden outputs

Before any code moves, capture what r1 produces today, so every later task can prove it unchanged.

**Files:**
- Create: `tests/fixtures/bbtool/capture_r1.py` (one-off capture script; kept so the capture is reproducible from the old code until Task 13 deletes that code)
- Create: `tests/fixtures/bbtool/r1/golden.json`, `tests/fixtures/bbtool/r1/wiring-plan.md`, `tests/fixtures/bbtool/r1/homes.md`, `tests/fixtures/bbtool/r1/bench-r1.kicad_sch`
- Create: `tests/test_bbtool_golden_fixture.py`
- Modify: `requirements-dev.txt` (add `numpy==2.3.4  # tools/breadboard router`)

**Interfaces:**
- Produces: `golden.json` with keys `on_bb` (`{"U1.H.VBUS": "BB1:a40", ...}`, every `build.ON_BB` entry as `"REF.PIN": hole`), `conductors` (list of `[id, kind, end1, end2, note]` in r1 order, ends as hole strings or `"REF.PIN"`), `ids` (old `routing` key → new ID, e.g. `"dupont:21": "D1"`), `notes` (the `build.check()` notes list), `routes` (`{ID: {"plan": [[x, y], ...], "mm3d": float}}`, rounded 4 dp), `counts` (`{"pins": 124, "conductors": 113, "jumpers": 16}`).
- Conductor IDs, assigned once here in r1's list order per kind: `D1..D20` dupont, `BJ1..BJ16` jumper, `F1..F5` force (note: the ID prefix `F` is unrelated to rule F1; IDs and rule IDs never share a namespace in output because rules print as `rule F1`), `PG1..PG5` pigtail, `SD1..SD3` solder, `SN1..SN2` sense, `RG1` reg, `LD1..LD3` lead, `Q1..Q10` QT cables (one ID per 4-signal cable; signals as `Q3.SDA`), `MT1..MT2` matings (one per plug, both contacts), `X1..X7` external cables (one per cable). Non-conductor routed items keep their names: `W1`, `W2`, `W3`, `RT1.1`, `RT1.2`.

- [ ] **Step 1:** Add the numpy pin and install it: `.venv/bin/pip install -r requirements-dev.txt`. Expected: `.venv/bin/python -c "import numpy"` exits 0.
- [ ] **Step 2:** Write `capture_r1.py`: imports r1's `build`, `routing`, `outputs` from `hardware/bench-breadboard-r1/layout` (sys.path insert), asserts `build.check()` has no fails, runs `routing.report()` and `routing.drape()` for 3D lengths, assigns IDs as above, writes `golden.json` canonically (Global Constraints format), copies the current `wiring-plan.md`, `homes.md` and `schematic/bench-r1.kicad_sch` into the fixture folder.
- [ ] **Step 3:** Run it: `.venv/bin/python tests/fixtures/bbtool/capture_r1.py`. Expected: prints `golden: 124 pins, 113 conductors, 16 jumpers, 25 routes`.
- [ ] **Step 4:** Write `test_bbtool_golden_fixture.py` asserting: counts as above; `ids` covers every dupont and the reg lead; `routes["D18"]["mm3d"]` rounds to 207 and `routes["W3"]["mm3d"]` to 155 (the known values from the 2026-11-03 run); running `capture_r1.py` again gives byte-identical `golden.json` (determinism of the old code, so a later diff is the new code's fault).
- [ ] **Step 5:** Run: `.venv/bin/python -m unittest tests.test_bbtool_golden_fixture -v`. Expected: PASS.
- [ ] **Step 6:** Checkpoint (no commit).

### Task 2: Board geometry and the part library

**Files:**
- Create: `tools/breadboard/__init__.py` (exports `__version__ = "0.1"`), `tools/breadboard/boards/__init__.py`, `tools/breadboard/boards/elegoo830.py`, `tools/breadboard/geometry.py`
- Create: `tools/breadboard/parts/__init__.py` and one module per r1 part (names below)
- Test: `tests/test_bbtool_geometry.py`, `tests/test_bbtool_parts.py`

**Interfaces:**
- Produces (`boards`): `BoardType(name: str, ncol: int, pitch: float, col_margin: float, size: tuple[float, float], z: float, row_y: dict[str, float], rails: tuple[str, ...], rail_groups: tuple[tuple[int, int], ...], top_rows: str, bottom_rows: str, provenance: dict[str, Prov])` frozen dataclass; `ELEGOO830` with r1's values (`ncol=62, pitch=2.54, col_margin=5.08, size=(165.1, 54.6), z=8.5`, `row_y` exactly r1's `ROW_Y`, `rail_groups=((3,7),(9,13),...,(57,61))`, `top_rows="abcde"`, `bottom_rows="fghij"`; `col_margin`, `size`, `z` provenance `estimate`). `boards.get(name) -> BoardType`.
- Produces (`geometry`): `Layout(boards: dict[str, tuple[BoardType, tuple[float, float]]])` with methods `parse(h) -> tuple[str, str, int]` (raises `HoleError(h, reason)` for bad names), `hole_xy(h) -> tuple[float, float, str, int]`, `hole_exists(h) -> bool`, `strip_of(h) -> tuple`, `span(h1, h2) -> int | None`, `all_holes() -> list[str]` (sorted by board, row order, column), `hole_at(x, y) -> str | None`, `order_key(h) -> tuple` (column descending, then row order). Semantics identical to r1 `build.py` lines 44-95.
- Produces (`parts`): frozen dataclasses `Prov(kind: Literal["datasheet", "photo", "measured", "estimate"], ref: str)`, `Pin(x: float, y: float, contact: str)`, `Part(key: str, maker: str, number: str, name: str, mount: Literal["seat", "at", "mate", "lead"], size: tuple[float, float], height: float, pins: dict[str, Pin], header: tuple[str, ...], ties: tuple[tuple[str, ...], ...], model: dict, provenance: dict[str, Prov])`; `parts.get(key) -> Part`; `parts.ALL: dict[str, Part]`.
- Part keys (module names): `nucleo_wl55jc1`, `adafruit_4755`, `adafruit_5832`, `adafruit_5580`, `pololu_2122`, `sparkfun_bob14021`, `adafruit_2674`, `wago_222_413`, `wago_222_415`, `adafruit_353`, `adafruit_4090`, `adafruit_5978`, `adafruit_368`, `adafruit_369`, `adafruit_5625`, `adafruit_6174`, `adafruit_4636`, `adafruit_6407`, `adafruit_4831`, `adafruit_4209` (QT-to-header cable), `axial_resistor`, `ceramic_cap`, `electrolytic_cap`, `link_2pin`, `ntc_lead`. Pins, sizes and header orders are transcribed from r1 `build.py` `SIZE`, `LOCAL`, `HEADER`, `_nucleo()`; header orders confirmed by photo 2026-11-03 for #4755, #5832, #5580, #2122 get `Prov("photo", "IMG_8442-8444 2026-11-03")`; NUCLEO pins and every `[TBD-MEASURE]` value in r1 get `Prov("estimate", <r1's comment>)`.

- [ ] **Step 1: Write the failing tests.** `test_bbtool_geometry.py`: for every hole in `golden.json["on_bb"]` values and every conductor hole end, `Layout.hole_xy` equals r1's (`build.hole_xy`, imported from the old code while it exists) to 1e-9; `len(all_holes())` equals r1's `len(build.ALL_HOLES)`; `parse("BB1:k5")`, `parse("BB4:a1")`, `parse("BB1:a63")` raise `HoleError`; `hole_exists("BB1:B-8") is False`; `span("BB1:e40", "BB1:f40") == 3`; `order_key` sorts `["BB1:a1", "BB1:a62", "BB1:j62"]` to `["BB1:a62", "BB1:j62", "BB1:a1"]`. `test_bbtool_parts.py`: `parts.get("adafruit_4755").header == ("VBUS", "GND1", "THERM", "ISET", "CE", "PGOOD", "CHG", "OUT", "GND2", "LIPO", "GND3")`; `adafruit_5832.header == ("VCC", "GND", "SCL", "SDA", "VBUS", "VIN-", "VIN+", "ALE")` (r1 naming, left to right as r1 lists); `pololu_2122.header == ("SHDN", "VIN", "GND", "VOUT")`; every pin of every part has an entry in `provenance` (key `pins.<name>` or a group key `pins.*`) and `size` has one; every part's `pins` equals r1 `LOCAL[kind]` for its kind.
- [ ] **Step 2:** Run both test files. Expected: FAIL (`ModuleNotFoundError: tools.breadboard`).
- [ ] **Step 3:** Implement the modules per Interfaces.
- [ ] **Step 4:** Run both test files. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 3: Authoring API, canonical compile, bench model

**Files:**
- Create: `tools/breadboard/author.py`, `tools/breadboard/compile.py`, `tools/breadboard/model.py`
- Test: `tests/test_bbtool_compile.py`

**Interfaces:**
- Consumes: `boards.get`, `Layout`, `parts.get`, `Prov` (Task 2).
- Produces (`author`): `Bench(name: str, plate: tuple[float, float], netlist: str, rules: str | None = None)` where `netlist`/`rules` are paths relative to the bench dir. Methods (all return `None`, all record into the bench; IDs must be unique, else `AuthorError`):
  - `board(name, type_key, at, role)`
  - `part(ref, part_key, *, rot=0, held="", seat=None | (pin, hole), at=None | (x, y), mate=None | (pin, (ref, pin)), holes=None | {pin: hole}, z=None)` — exactly one of `seat`/`at`/`mate`/`holes`; `z` overrides the mounting height (NUCLEO 10.0, QT boards 6.0).
  - `loose(ref, pin, xy)` (r1 `PLUG_XY`), `bead(ref, xy, z)` (r1 `NTC_BEAD`, z 19.0)
  - `jumper(id, h1, h2, note)`
  - `wire(id, kind, end1, end2, note, *, colour=None, route=False)`; kinds: `dupont, force, pigtail, solder, sense, reg, lead, mate, cable`; ends are hole strings or `(ref, pin)`.
  - `qt(id, (ref, port), (ref, port), note)` → four conductors `id.GND`, `id.V+`, `id.SDA`, `id.SCL`.
  - `span(ref, end1, end2, limit_mm, route_kind="lead")` (r1 `PART_SPANS`), `limit(kind, mm)`, `waive(rule, target, reason)`, `colours(**groups)` (`bojack={span: hex}`, `dupont={signal: hex}`, `qt={signal: hex}`), `kit_spans(set)`.
- Produces (`compile`): `compile_bench(bench: Bench) -> dict` (seated header pins expanded to holes via the part's `header` and `Layout.hole_at`; unresolved pins recorded as `seat_errors`, not raised); `dumps(doc: dict) -> str` (Global Constraints format); `load_bench_file(bench_dir: Path) -> Bench` (imports `layout/bench.py`, which must define `BENCH`). Document top keys: `schema` (1), `name`, `plate`, `boards`, `parts`, `on_bb`, `seat_errors`, `conductors` (sorted by ID; each `{id, kind, a, b, note, colour, route}`), `loose`, `beads`, `spans`, `limits`, `kit_spans`, `waivers`, `colours`, `netlist` (`PARTS` and `NETS` serialised: pins, ties, attributes), `inputs` (sha256 of `bench.py`, netlist file, rules file, and each used part module).
- Produces (`model`): `BenchModel.load(doc: dict) -> BenchModel` (frozen); attributes `layout: Layout`, `parts: dict[ref, PlacedPart]`, `on_bb: dict[tuple[str, str], str]`, `conductors: tuple[Conductor, ...]` (`Conductor(id, kind, a, b, note, colour, route)`), `waivers`, `limits`, `netlist`; methods `pin_xy(end) -> tuple[float, float] | None`, `outline(ref) -> tuple[float, float, float, float]`, `covered() -> dict[str, str]`, `occupants() -> dict[str, list]` — semantics of r1 `build.py` `pin_xy`, `outline`, `covered`, `occupants`.

- [ ] **Step 1: Write the failing tests** in `test_bbtool_compile.py` using a 10-line inline bench (one board, one `axial_resistor` by `holes`, one jumper, one dupont to a loose point): `test_compile_is_byte_stable` (two `dumps(compile_bench(b))` equal; a second bench with the same calls in a different order gives the same bytes); `test_canonical_floats` (`dumps({"x": -0.0, "y": 1e-05, "z": 2.00005})` contains `"x": 0.0`, `"y": 0.0`, `"z": 2.0001` or `2.0` per Python `round` — assert the exact string the implementation fixes, written once); `test_duplicate_id_is_error` (`AuthorError`); `test_bad_hole_names_are_findings` (a jumper to `BB1:k5` compiles, and `doc["hole_errors"]` contains `{"item": <id>, "hole": "BB1:k5", "reason": ...}` — add that key to the schema); `test_seat_expands_header` (a `pololu_2122` seated at `SHDN, BB1:f24` yields `on_bb` `U7.VIN = BB1:f23`, `U7.GND = BB1:f22`, `U7.VOUT = BB1:f21`).
- [ ] **Step 2:** Run. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `author.py`, `compile.py`, `model.py` per Interfaces.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 4: Port bench r1's data

**Files:**
- Create: `hardware/bench-breadboard-r1/layout/bench.py` (r1 authored with `author.py`; every placement, hole, conductor and rule from `build.py`, with the Task 1 IDs)
- Rename: `hardware/bench-breadboard-r1/schematic/model.py` → `schematic/netlist.py` (content unchanged except the docstring's file names); update the imports in `schematic/kicad_gen.py`, `schematic/checks.py`, `layout/build.py` so the old scripts keep working until Task 13
- Create: `hardware/bench-breadboard-r1/out/bench.json` (generated)
- Test: `tests/test_bbtool_r1_data.py`

**Interfaces:**
- Consumes: `Bench` API, `compile_bench`, `dumps`, `BenchModel` (Task 3).
- Produces: `BENCH` in `bench.py`; `out/bench.json`. r1 specifics as data: `limit` for every `LIMIT_MM` entry (`force 80, pigtail 60, reg 100, sense 150, dupont 300, qt 200, solder 80`; dupont raised from r1's 200 to 300 because L1 now uses routed length against the longest kit Dupont, as the plan already buys 30 cm), `limit("qtheader", 150)` (Adafruit #4209), `span("W1", ("WG2", "4"), "BB1:j22", 100)`, `waive("F1", "U7.VIN", "regulator supply, the one tolerated breadboard path (design.md C)")`, `waive("F1", "U1.H.GND1", "NTC return on the charger's own GND pin, 75 uA (decision D2)")`, `kit_spans({1..10, 20, 30, 40, 50})`, the colour tables from r1 `kicad_layout.py` `BOJACK`, `DUPONT_COLOUR`, `QT_WIRES`.

- [ ] **Step 1: Write the failing test** `test_bbtool_r1_data.py`: compiling r1 gives `on_bb` equal to `golden["on_bb"]`; conductors equal `golden["conductors"]` as sets of `(id, kind, a, b, note)`; `seat_errors == []`, `hole_errors == []`; `dumps(compile_bench(load_bench_file(r1)))` equals the committed `out/bench.json` bytes.
- [ ] **Step 2:** Run. Expected: FAIL (`bench.py` missing).
- [ ] **Step 3:** Write `bench.py`, rename the netlist and fix the three imports, generate `out/bench.json`.
- [ ] **Step 4:** Run the test, then the old check: `cd hardware/bench-breadboard-r1/layout && ../../../.venv/bin/python build.py`. Expected: test PASS; old check prints `PASS: 0 failure(s)`.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 5: Copper proof and the static rules

**Files:**
- Create: `tools/breadboard/copper.py`, `tools/breadboard/rules/__init__.py`, `rules/schema.py` (S1), `rules/copper.py` (E1), `rules/holes.py` (H1, H2, H3), `rules/force.py` (F1), `rules/jumpers.py` (J1), `rules/plate.py` (P1)
- Test: `tests/test_bbtool_rules.py`

**Interfaces:**
- Consumes: `BenchModel` (Task 3).
- Produces: `copper.built_groups(model) -> Callable[[node], node]` and `copper.netlist_groups(model) -> Callable` (union-find of r1 `physical_groups` / `model_groups`; library ties ∪ netlist ties); `Result(id: str, cls: Literal["correctness", "limit"], status: Literal["pass", "fail", "waived"], evidence: str, findings: tuple[str, ...])`; `Rule(id, cls, statement, check: Callable[[BenchModel, Context], Result])`; `Context(routes: dict | None = None, kicad_netlist: Path | None = None, erc: Path | None = None)`; `rules.REGISTRY: dict[str, Rule]` (ordered by ID); `rules.run(model, ctx, only: set[str] | None = None) -> list[Result]`; `rules.blocking(results) -> list[Result]` (failed correctness results). Waivers: a rule consults `model.waivers` for its ID; a waiver that matches no finding makes that rule fail with finding `"unused waiver <target>"`.
- Evidence strings (exact for r1, asserted in tests): E1 `"124 pins in holes, 113 conductors: built copper partitions the pins exactly as the netlist"`; F1 `"<n> strips hold force-net copper, each alone or waived (2 waivers)"`; J1 `"16 jumpers, all straight kit lengths on one board"`. Other rules: one line in the same style, builder's wording.

- [ ] **Step 1: Write the failing tests:** `test_r1_static_rules_pass` (S1 E1 H1 H2 H3 F1 J1 P1 all `pass` on r1 and evidence for E1, F1, J1 equals the strings above); `test_r1_notes_match_golden` (P1's notes about P1/P2 overlap appear as in `golden["notes"]`); `test_unused_waiver_fails` (add `waive("F1", "U4.H.VCC", "x")` to a copy → F1 fail with `"unused waiver U4.H.VCC"`); `test_seat_off_board_end` (copy with U1 seated at `BB1:a5` → H3 findings, one per pin off the board, no exception).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, porting r1 `check()` sections [1]-[3], [4] (jumpers only) and [5].
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 6: Router, L1 and R1

**Files:**
- Create: `tools/breadboard/router.py`, `rules/leads.py` (L1), `rules/routes.py` (R1)
- Create: `hardware/bench-breadboard-r1/out/routes.json` (generated)
- Test: `tests/test_bbtool_router.py`

**Interfaces:**
- Consumes: `BenchModel`, `Rule`/`Result`/`Context` (Task 5).
- Produces: `router.route_all(model) -> Routes` where `Routes = dict[str, Route]`, `Route(id: str, kind: str, plan: tuple[tuple[float, float], ...], ends: tuple[End, End], plan_mm: float, mm3d: float, problem: str | None)`; `router.drape(model, route) -> list[tuple[float, float, float]]`; `router.dumps(routes) -> str` (canonical). Routed items: conductors with `route=True` (every dupont and the reg lead in r1), every `span`, every `bead` lead, every part with key `adafruit_4209` (kind `qtcable`). Constants from r1 `routing.py`: grid 0.635, `WIRE_R` (`dupont 0.65, reg 0.5, lead 0.5, ntc 0.3, qtcable 0.9`), housing 14.0, lane cost 1.5 width `2r + 0.3`, search margin 70 mm, rise 12.0, slope 1:1. Canonical order: duponts first, then the rest; within each group by straight-line length, then by ID (r1's order; ID tie-break is new and changes nothing for r1). Heap entries `(f, g, cell, dir)`. Heights come from part `height` and placement `z`, not from r1's hard-coded `NUC_Z`/`QT_Z` (those values move into `bench.py` as `z=`).
- L1: every conductor with a `limit` for its kind is measured by routed `mm3d` when routed, else `dist * 1.15 + 10`; `span` items against their own limit; `adafruit_4209` cables against `limit("qtheader")`; finding text `"W3 qtcable routed 155 mm, limit 150 mm"` style. R1: every routed item has a path; no plan vertex within 0.9 mm of a used hole other than its own ends (r1 `report()`); unroutable → finding `"<id>: no route (<note>)"`.

- [ ] **Step 1: Write the failing tests:** `test_r1_routes_match_golden` (for every ID in `golden["routes"]`: same number of plan points, every point within 0.01 mm, `mm3d` within 0.01 mm); `test_routes_json_byte_stable` (two runs, identical `dumps`, equal to committed `out/routes.json`); `test_r1_l1_reports_w3` (L1 `fail`, `cls == "limit"`, exactly one finding, naming `W3` and `155` and `150`; `rules.blocking` is empty); `test_r1_r1_passes`; `test_unroutable_wire_is_r1_failure` (copy of r1 with a dupont to a pin enclosed by a blocked box — add an `at` part `wago_222_415` over the target — gives R1 fail naming the ID, `blocking` non-empty, no exception).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port `routing.py` into `router.py` reading `BenchModel`; implement L1 and R1; generate `out/routes.json`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 7: Mutation tests for every rule

**Files:**
- Create: `tests/test_bbtool_mutations.py`
- Create: `tools/breadboard/mutate.py` (pure functions on a compiled document; also used by `move` in Task 11)

**Interfaces:**
- Consumes: `compile_bench`, `BenchModel.load`, `rules.run`, `router.route_all`.
- Produces: `mutate.apply(doc: dict, op: str, *args) -> dict` (deep copy, recompiles derived fields such as `on_bb` for re-seats). Ops: `seat(ref, pin, hole)`, `end(id, which: Literal["a", "b"], new_end)`, `add_conductor(id, kind, a, b, note)`, `drop_waiver(rule, target)`, `set_limit(kind, mm)`, `move_part(ref, x, y)`, `nudge(ref, dx, dy)` (shifts a seated part's origin; its header pins are re-resolved and may miss holes), `block(x, y, w, h)` (adds an obstacle part).

- [ ] **Step 1: Write the tests**, one per row; each asserts the named rule fails and names the target in a finding:

| Test | Mutation on r1 | Rule |
|---|---|---|
| `test_m_e1_dupont_off_by_one` | `end("D1", "a", "BB1:c36")` | E1 |
| `test_m_h3_seat_off_grid` | `nudge("U5", 1.27, 0)` (seated header half a pitch off the grid) | H3 |
| `test_m_h2_lead_under_charger` | `add_conductor("BJ99", "jumper", "BB1:b38", "BB1:b36", "x")` | H2 |
| `test_m_h1_rail_gap` | `end("BJ2", "b", "BB1:B-50")` (rail gap column 50) | H1 |
| `test_m_f1_lipo_strip_shared` | `add_conductor("BJ98", "jumper", "BB1:e31", "BB1:d31", "x")` | F1 |
| `test_m_f1_waiver_dropped` | `drop_waiver("F1", "U7.VIN")` | F1 |
| `test_m_j1_span_11` | `add_conductor("BJ97", "jumper", "BB3:a2", "BB3:a13", "x")` | J1 |
| `test_m_l1_tie_limit` | `set_limit` on W1's span to 50 | L1 |
| `test_m_p1_pack_off_plate` | `move_part("BT1", 380, 40)` | P1 |
| `test_m_r1_block_gap` | `block(...)` over D8's only approach | R1 |
| `test_m_s1_unknown_pin` | `end("D2", "b", ["A1", "CN99.1"])` | S1 |

- [ ] **Step 2:** Run: `.venv/bin/python -m unittest tests.test_bbtool_mutations -v`. Expected: FAIL (`mutate` missing).
- [ ] **Step 3:** Implement `mutate.py`. If a mutation does not make its rule fail, fix the rule, not the test.
- [ ] **Step 4:** Run. Expected: PASS, 11 tests.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 8: Schematic generation, E2 and bench rules

**Files:**
- Create: `tools/breadboard/kicad/__init__.py`, `tools/breadboard/kicad/schematic.py` (from r1 `schematic/kicad_gen.py`), `tools/breadboard/kicad/netlist_check.py` (from r1 `checks.py`: s-expression reader, round trip, ERC), `tools/breadboard/rules/kicad.py` (E2)
- Create: `hardware/bench-breadboard-r1/schematic/rules.py` (bench rules B1-B6 from r1 `checks.py`: pins, ground, force, I2C, voltage, firmware pins, modes — each returns `Result` with ID `B1`...`B6`, class correctness)
- Test: `tests/test_bbtool_schematic.py`

**Interfaces:**
- Consumes: `BenchModel.netlist`, `Rule`/`Result`/`Context`.
- Produces: `schematic.write(model, out_dir: Path, project: str) -> Path` (the `.kicad_sch`, functional blocks from netlist `block` fields as r1); `netlist_check.export(sch: Path, tmp: Path) -> tuple[Path, Path]` (netlist, ERC JSON via `kicad-cli`; raises `KicadMissing` without it); `rules.load_bench_rules(bench_dir) -> list[Rule]` (imports `schematic/rules.py`, which defines `RULES`). E2 status is `pass` with evidence `"skipped: needs KiCad 10"` and class correctness only when KiCad is absent and the run is not `--strict`; under `--strict` without KiCad it fails.

- [ ] **Step 1: Write the failing tests:** `test_schematic_matches_r1` (`schematic.write` on r1 produces bytes equal to `tests/fixtures/bbtool/r1/bench-r1.kicad_sch`); `test_bench_rules_pass_on_r1` (B1-B6 pass); `test_e2_round_trip` (skip without kicad-cli; E2 pass on r1).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement by moving code; r1's `schematic/run.sh` becomes `python3 -m tools.breadboard schematic hardware/bench-breadboard-r1` (CLI wiring lands in Task 11; here expose `schematic.write`).
- [ ] **Step 4:** Run. Expected: PASS (E2 skipped without KiCad).
- [ ] **Step 5:** Checkpoint (no commit).

### Task 9: Wiring plan and homes

**Files:**
- Create: `tools/breadboard/plan.py` (from r1 `outputs.py`, reading `BenchModel` + `Routes` + rule results)
- Test: `tests/test_bbtool_plan.py`

**Interfaces:**
- Consumes: `BenchModel`, `Routes`, `rules.run` results.
- Produces: `plan.wiring_plan(model, routes, results) -> str`, `plan.homes(model) -> str`. Bench-specific prose (board roles, the "not fixed to the plate" table, NUCLEO pin labels) comes from `bench.py` data: add `Bench.text(key, value)` and `Bench.pin_label(ref, {pin: label})` to `author.py` (and to the compiled document under `text`, `pin_labels`). Generator line reads ``Generated by `python3 -m tools.breadboard plan` from `layout/bench.py` and `schematic/netlist.py`; do not edit by hand.`` Section 7 lists every failing limit rule first (from results), then estimates from provenance.

- [ ] **Step 1: Write the failing test:** `test_plan_matches_golden`: `wiring_plan` for r1 equals the fixture `wiring-plan.md` after exactly these substitutions applied to the fixture: the generator line above, and the section-7 flag line rewritten as the L1 finding text; `homes` equals the fixture `homes.md` after the generator line substitution. Both byte-stable across two runs.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 10: Build cards (2D SVG and HTML step slider)

**Files:**
- Create: `tools/breadboard/draw/__init__.py`, `tools/breadboard/draw/svg.py`, `tools/breadboard/draw/card.py`
- Test: `tests/test_bbtool_cards.py`

**Interfaces:**
- Consumes: `BenchModel`, `Routes`, colours from the model.
- Produces: `svg.Doc(w, h)` with `rect, circle, line, path, text, group` methods and `render() -> str` (fixed attribute order, numbers via the canonical float rule, no ids except explicit ones); `card.steps(model) -> dict[str, list[Step]]` where `Step(n: int, title: str, items: tuple[str, ...])` — board steps 1 jumpers, 2 leaded parts, 3 seated modules, 4 flying-wire ends; plate steps 0 mount, 5 island leads, 6 QT cables, 7 external cables; `card.board_svg(model, routes, board, step) -> str`; `card.plate_svg(model, routes, step) -> str`; `card.index_html(model, svgs) -> str` (one page, inline SVG, a range input per board for the step, links `../renders/<board>-step<n>-iso.png`; no external scripts). Grid cropped to used columns ± 3; holes drawn in the board's numbering with row and column labels; each item labelled with its ID or ref and value; new items in the current step drawn emphasised (stroke width 2x); checklist table beside the grid with one row per item, ID first.

- [ ] **Step 1: Write the failing tests:** `test_cards_byte_stable` (two runs equal); `test_every_item_on_one_step` (every conductor ID, every seated/leaded ref appears in exactly one step's `items` across board and plate steps); `test_labels_clear_used_holes` (parse `card.board_svg(r1, BB1, 4)`: no `<text>` bounding box, estimated as `len * 0.6 * font_size` by `font_size`, contains a used hole centre); `test_checklist_matches_plan_ids` (D1-D20 appear in BB1/BB3 step 4 checklists exactly as in `wiring_plan`); `test_index_html_self_contained` (no `src="http`, no `<script src`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS. Then open `out/cards/index.html` locally (`open hardware/bench-breadboard-r1/out/cards/index.html`) and show the user BB1 steps 1-4 before going on; their corrections are part of this task.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 11: CLI, audit, `--check`

**Files:**
- Create: `tools/breadboard/__main__.py`, `tools/breadboard/cli.py`, `tools/breadboard/audit.py`, `tools/breadboard/ops.py` (`where`, `free`, `move`)
- Test: `tests/test_bbtool_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `cli.main(argv: list[str]) -> int`. Ops and exit codes: `compile`, `check [--strict]` (0 pass; 1 any blocking failure, or with `--strict` any failure or stale output), `route`, `plan`, `cards`, `schematic`, `render [--board BB1] [--step N]`, `where <hole|strip>`, `free <board> --strips N [--half top|bottom] [--near COL] [--no-force]`, `move <op args>` (`seat U5 BB2:j44`, `end D7 b BB1:B-25`, `part BT1 186 40`), `audit`, `all [--render] [--check]`. `<bench>` is the bench dir; outputs go to `<bench>/out/` (`bench.json`, `routes.json`, `wiring-plan.md`, `homes.md`, `cards/`, `schematic/`, `audit.json`, `audit.md`; illustration: `kicad/`, `renders/`, `renders.json`). Downstream ops refuse (exit 1, list blocking results) on blocking failures. `--check` regenerates evidence in memory and exits 1 naming each differing file.
- `audit.build(model, results, outputs: dict[str, bytes], renders: dict | None) -> tuple[str, str]` (JSON, Markdown): input hashes (from `doc["inputs"]`), tool versions (Python `platform.python_version()`, `numpy.__version__`, `kicad-cli version` when present), every result, every waiver with reason, every `estimate` provenance grouped by part with the dimension name, sha256 of each evidence output, and for each render its stamp and `current: bool` (stamp hash equals current `bench.json` hash).
- `ops.where(model, routes, target) -> str`, `ops.free(model, board, strips, half, near, no_force) -> list[str]` (candidate start columns, ranked by distance to `near`, then column), `ops.move(doc, op_args) -> str` (applies `mutate.apply`, reruns rules and router, prints rule status changes, route length changes > 0.5 mm, and the change in words; never writes files).

- [ ] **Step 1: Write the failing tests:** `test_all_twice_no_diff` (`all` then `all --check` on a temp copy of r1 exits 0); `test_check_detects_stale` (edit one character in `out/wiring-plan.md`, `all --check` exits 1 naming it); `test_strict_fails_on_w3` (`check --strict` exits 1 and prints the W3 L1 finding; plain `check` exits 0); `test_where` (`where BB1:h24`-style query on `BB1:h40` prints `R4.1`); `test_free_bb1_bottom` (`free BB1 --strips 2 --half bottom` returns only columns whose two strips are empty and not covered); `test_move_prints_deltas` (`move end D7 b BB1:B-25` output contains `D7: BB1:B-27 -> BB1:B-25` and a length change line, and the bench dir is unchanged byte for byte); `test_audit_lists_estimates` (audit.md lists the NUCLEO header estimate and the 2 waivers); `test_all_without_kicad` (with `PATH` stripped of kicad-cli, `all` exits 0, prints one `skipped:` line per KiCad step, evidence files exist).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, then the whole suite: `.venv/bin/python -m unittest discover -s tests -p 'test_bbtool_*.py'`. Expected: PASS.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 12: KiCad boards, 3D models, step renders

**Files:**
- Create: `tools/breadboard/kicad/models.py` (r1 `kicad_layout.py` `Mesh`, `FONT`, model functions, driven by each part's `model` dict), `tools/breadboard/kicad/board.py` (`.kicad_pcb` per plate and per board), `tools/breadboard/kicad/render.py`
- Test: `tests/test_bbtool_kicad.py`

**Interfaces:**
- Consumes: `BenchModel`, `Routes`, `card.steps` (Task 10), colours.
- Produces: `models.part_mesh(part, placed) -> Mesh`, `models.wires_mesh(model, routes, board=None, upto_step=None) -> Mesh` (routed duponts with housings, QT cables as four coloured wires, flags: a 3 mm white tag with the ID standing 6 mm above each wire end, ref + value labels 4 mm above each part); `board.write(model, routes, out_dir) -> list[Path]` (`plate.kicad_pcb`, `<board>.kicad_pcb`, `<board>-step<n>.kicad_pcb`); `render.run(pcbs, out_dir) -> dict` (kicad-cli `pcb render --quality high --use-board-stackup-colors --background transparent`, composited on white with Pillow, top and iso views as r1; returns stamps `{file: {"bench": sha256, "kicad": version, "step": n, "card": "<board> step <n>"}}` written to `renders.json`).

- [ ] **Step 1: Write the failing tests:** `test_pcb_byte_stable` (two `board.write` runs give identical `.kicad_pcb` bytes); `test_pcb_has_all_parts` (plate pcb contains a footprint per placed ref); `test_step_meshes_grow` (vertex count of `wires_mesh(..., upto_step=n)` strictly increases over steps 1-4 for BB1); `test_render_stamps` (skip without kicad-cli: render BB1 step 4 iso only, stamp `bench` equals `sha256(out/bench.json)`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement by moving r1 code; wire `render` into `cli.py`.
- [ ] **Step 4:** Run, then `.venv/bin/python -m tools.breadboard render hardware/bench-breadboard-r1` (about 15 minutes for all steps). Expected: PASS; renders written. Show the user the plate iso and BB1 step 4 iso.
- [ ] **Step 5:** Checkpoint (no commit).

### Task 13: A second bench, r1 cut-over, docs

**Files:**
- Create: `tests/fixtures/bbtool/led/layout/bench.py`, `tests/fixtures/bbtool/led/schematic/netlist.py` (one board, a NUCLEO at the side, an LED and 330 R in strips, two Duponts from 3V3 and GND; target about 30 lines of authoring); add parts `led_5mm` to the library
- Test: `tests/test_bbtool_second_bench.py`
- Delete (after telling the user and getting a yes): `hardware/bench-breadboard-r1/layout/{build,routing,kicad_layout,outputs}.py`, `hardware/bench-breadboard-r1/schematic/{kicad_gen,checks}.py`, `schematic/run.sh`, the old generated `layout/wiring-plan.md`, `layout/homes.md`, `layout/kicad/`; `tests/fixtures/bbtool/capture_r1.py` (golden.json stays)
- Create: `hardware/bench-breadboard-r1/README.md` (how to build r1's outputs with the CLI)
- Modify: `tools/README.md` (one row for `breadboard/`), `hardware/bench-breadboard-r1/design.md` status line (outputs now in `out/`)

**Interfaces:**
- Consumes: the CLI.

- [ ] **Step 1: Write the failing test** `test_bbtool_second_bench.py`: `all` on the LED bench exits 0; all correctness rules pass; `wiring-plan.md` lists the two Duponts; `grep` of `tools/breadboard/**/*.py` finds none of `U1`, `A1`, `BB1`, `#4755`, `INA228`, `NUCLEO_PIN`, `weather` (no r1 knowledge in the engine).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the LED bench; remove any r1 knowledge the grep finds by moving it into r1's `bench.py`.
- [ ] **Step 4:** Run the whole suite. Expected: PASS.
- [ ] **Step 5:** Tell the user the exact file list to delete and that the golden fixtures keep the old outputs; delete only on their yes. Rewrite the Task 1-9 tests that imported old r1 code to compare against `golden.json` only; run the whole suite again. Expected: PASS.
- [ ] **Step 6:** Update the docs listed above.
- [ ] **Step 7:** Checkpoint (no commit).

### Task 14: The skill

**Files:**
- Create: `~/.claude/skills/breadboard-mockup/SKILL.md`

**Interfaces:**
- Consumes: the CLI, the spec sections 3 and 11.

- [ ] **Step 1:** Write the skill: frontmatter `name: breadboard-mockup`, description "Lay out, check, route and document a breadboarded circuit (wiring plans, build cards, KiCad renders) with tools/breadboard; use when mocking up or reviewing a breadboard build." Body: when to use; the workflow (survey formally; netlist; library gaps with provenance; placement one step at a time with approval; `check`; `route`; `cards`; `render`; `plan`; `audit`); the user's standing rules from spec section 3 verbatim; every CLI op with one example; how to add a part (module under `parts/` with provenance) and a board type; using it from another repo (`PYTHONPATH=<this repo> python3 -m tools.breadboard ...`, record the repo's git hash, which the audit prints).
- [ ] **Step 2:** Verify: run every example command in the skill against r1 (or the LED bench) and confirm each exits as the skill says.
- [ ] **Step 3:** Checkpoint (no commit). Tell the user the skill is in place and the branch is ready for their review and commit.
