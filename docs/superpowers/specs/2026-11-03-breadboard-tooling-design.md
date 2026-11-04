# Breadboard mock-up tooling: design

Date 2026-11-03. Status: draft for approval.

## 1. Intent

Bench r1 (`hardware/bench-breadboard-r1/`) was laid out with about 3,000 lines of one-off Python:
`schematic/` (model, KiCad generator, checks), `layout/build.py` (placement, copper, rules),
`layout/routing.py` (wire router), `layout/kicad_layout.py` (3D models, KiCad boards, renders) and
`layout/outputs.py` (wiring plan). It worked, but the next bench would start from a copy.

Make it reusable: a package in this repo that turns a short bench description into **checked,
audited, deterministic** schematics, wiring diagrams and renders, and a personal Claude skill that
carries the workflow so any future breadboard mock-up (in this repo or another) uses it.

What "excellent" means here (the user's words: perfect, deterministic, checked, audited, easy to read):

- **Checked:** the build's copper is proved equal to the schematic, and every build rule passes.
- **Audited:** every rule reports what it checked and why it passed, not only failures; every dimension
  says where it came from; every output is tied by hash to the inputs that made it.
- **Deterministic:** the same inputs give byte-identical evidence outputs on any run.
- **Easy to read:** a person can build the bench from the outputs without asking what a wire is.

## 2. Goals, non-goals, anti-goals

Goals

- G1 One engine, `tools/breadboard/`, used by every bench from r1 on; a bench is a small authored file
  plus its netlist. Bench r0 (`hardware/bench-breadboard-r0/`) keeps its own tooling unchanged (user,
  2026-11-03): it is the built bench, and `tools/preflight.py` and `tools/benchlink_log.py` hash its
  `wiring.toml` and `build-sheet.md`.
- G2 Bench r1 is ported first and is the golden test (section 8).
- G3 Operations: `check`, `route`, `render`, `plan`, `where`, plus `free` (suggest free strips) and
  `move` (move and re-check).
- G4 Two main build views, both first class: a 2D build card per board and 3D step renders, matched
  step for step.
- G5 A personal skill, `~/.claude/skills/breadboard-mockup/`, holding the workflow and the user's rules.

Non-goals

- Auto-placement of any kind (the user chose check and route only).
- A KiCad schematic importer (the input is the Python netlist).
- A web editor; a BOM generator; a photo-to-part guide (not chosen).
- Porting or changing bench r0.
- Hand-tuned, prettier schematics than the generated functional-block drawing.

Anti-goals (failure even if it runs)

- A check that cannot catch the defect it is named for.
- An output that silently disagrees with another (card vs render vs plan vs netlist).
- A hidden estimate: a dimension used without its provenance showing up in the audit.
- Bench-specific knowledge (part numbers, refs, this project's rules) baked into engine code.

## 3. Constraints

- Python 3.12, standard library plus numpy (router). No matplotlib (not installed, not byte-stable).
  PIL only where a raster is unavoidable (compositing renders).
- KiCad 10 (`kicad-cli`, 10.0.7 here) for ERC, netlist export, PDF and 3D renders. CI has no KiCad:
  tests that need it skip with a clear message; all evidence-tier outputs must build without it.
- Repo conventions: tools run from the root; tests are `unittest` under `tests/` (run by `tools/gates.sh`
  and CI); ruff clean; generated files committed with a `--check` mode that fails when stale (as
  `tangle.py` and `wsmp_registry.py` do).
- Board convention (Elegoo full-size, photographed 2026-11-03): rows a-e upper half top to bottom, f-j
  lower half; column 62 at the left, 1 at the right; rails T+ (outer) and T- above row a, B+ and B-
  (outer) below row j; rail holes in groups of five beside columns 3-7, 9-13 ... 57-61.
- The user's standing rules carried by the skill: one step at a time with approval; survey formally
  (AskUserQuestion, recommended option first, explained); no Mermaid; real outlines and pinouts; force
  currents never through shared breadboard contacts; reuse firmware pin choices; as much as possible on
  the breadboards; never commit or push until asked; never read anything under `run*/`.

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | **Extract the engine from r1; benches authored in Python; r1 is the first user** | Proven shapes; the format inherits r1's (dicts, (ref, pin) tuples) |
| B | Fresh library with a declarative TOML/YAML bench format, then port r1 | Cleanest data, about twice the work; loses r1's helpers (`qt()`, `ina228()`, computed pin lists); hard to prove r1 unchanged |
| C | A template forked per bench, plus the skill | Almost free; nothing shared, so a router or rule fix never reaches other benches |

**Chosen: A, with B's auditability added** (the outcome of the debate, 2026-11-03): benches are
*authored* in Python, then *compiled* to one canonical, sorted `bench.json`. Every downstream stage
reads only `bench.json`. It is committed, it is what review diffs, and its hash stamps every output.

## 5. Architecture

```
tools/breadboard/
  __init__.py
  boards/elegoo830.py     board geometry as data: rows, row y, columns, column pitch, trench, rail gaps,
                          outline, height. A new make or size is a new table, not new code.
  parts/                  the part library, one module per part (section 6)
  author.py               the authoring API a bench file imports (part(), seat(), at(), mate(), hole(),
                          jumper(), dupont(), lead(), qt_chain(), waive(), ...)
  compile.py              bench file -> canonical bench.json (sorted keys and lists, fixed float format)
  model.py                loads bench.json into frozen dataclasses; geometry queries (hole_xy, strip_of,
                          pin_xy, outline, covered holes, occupants)
  copper.py               union-find of built copper and of the netlist; the equivalence proof
  rules/                  one module per rule (section 7)
  router.py               deterministic routing; routes written back into routes.json
  draw/svg.py             a tiny deterministic SVG writer (no dependencies)
  draw/card.py            2D build cards: SVG per board per step, and one HTML page with a step slider
  kicad/schematic.py      netlist -> .kicad_sch (r1's kicad_gen.py, generalised); ERC; netlist round trip
  kicad/board.py          bench -> .kicad_pcb per plate and per board, with VRML/STEP models
  kicad/models.py         Mesh, stroke font, parametric module models (r1's kicad_layout.py, generalised)
  kicad/render.py         kicad-cli renders, plate and per board, per step; stamps each render
  plan.py                 wiring-plan.md and homes.md
  audit.py                audit.json and audit.md (section 9)
  cli.py                  python3 -m tools.breadboard <op> <bench> [...]
tests/test_breadboard_*.py
~/.claude/skills/breadboard-mockup/SKILL.md
```

A bench directory after the port (r1 as the example):

```
hardware/bench-breadboard-r1/
  schematic/netlist.py        PARTS and NETS (today's model.py, unchanged in meaning)
  schematic/rules.py          bench-only electrical checks (firmware pins, I2C addresses, modes)
  layout/bench.py             the authored layout (placements, holes, conductors, waivers, colours)
  out/                        everything generated (sections 8-9); committed
```

Pipeline: `netlist.py` + `bench.py` -> `compile` -> `bench.json` -> `check` -> `route` (`routes.json`)
-> `plan` / cards / KiCad / renders -> `audit`. Each stage reads files, never the authoring Python, so
each is testable alone.

**Gating (builder's call).** Rules have a class. *Correctness* rules (S1, E1, E2, H1-H3, F1, J1, R1,
B*) block every downstream stage, as `kicad_layout.py` and `outputs.py` refuse today. *Limit* rules (L1,
P1) report fail but do not block generation: the outputs are made, the failure is printed at the top of
`wiring-plan.md` section 7 and in the audit, and `check --strict` exits non-zero. So a 5 mm-long cable
never hides the plan that shows it.

### 5.1 Determinism rules

- Every collection is emitted sorted by a documented key; floats are written with a fixed format
  (`%.4f` mm); no timestamps, no absolute paths, no hostnames in evidence outputs.
- The router keeps r1's order and tie-break, which are already deterministic (builder's call): Duponts
  first, then the rest, each group by straight-line length, then by conductor ID; the A* heap orders on
  (f, g, cell, direction). Order matters beyond ties, because each finished route raises the cost of
  its lane for later ones. It is documented as the canonical order and never taken from dict order.
- Every conductor has an explicit, stable ID in `bench.py` (`D7`, `J3`, `W1`; builder's call). Route
  keys, the plan's numbering, card labels and 3D flags all use it, so sorting `bench.json` never
  renumbers a wire on the bench. r1's IDs are assigned once in today's order, so D1-D20 keep their
  meaning.
- UUIDs in KiCad files come from `uuid5` of stable names (as `kicad_gen.py` already does).
- A `--check` mode regenerates every evidence output in memory and fails if any committed file differs.

### 5.2 Two tiers of output

| Tier | Outputs | Guarantee |
|---|---|---|
| Evidence | `bench.json`, `routes.json`, netlist and KiCad schematic, `check` report, `wiring-plan.md`, `homes.md`, build-card SVGs and HTML, `audit.json`/`audit.md` | byte-identical; hashed in the audit; `--check` enforced; no KiCad needed except the schematic ERC/round trip |
| Illustration | KiCad `.kicad_pcb` boards, PNG renders, schematic PDF | not hashed (raytracer and KiCad versions vary); each stamped with the `bench.json` hash and the KiCad version in a sidecar `renders.json`; the audit flags a stale stamp |

## 6. The part library

One module per part under `tools/breadboard/parts/`, exporting a `Part` with:

- identity: maker, number, name (`Adafruit #5832 INA228`)
- `outline` (w, h mm), `height`, and how it mounts (`seat` by header, `at` on the plate, `mate` into a
  connector, `lead` for axial/radial parts)
- `pins`: name -> local (x, y) mm in the part frame (origin top-left, y down, before rotation), plus
  contact type (header, screw, jst, qt, usb, barrel, rj11, wago, solder) as in r1's model
- `header`: pin names in physical order, left to right as printed
- `ties`: pins joined on the board itself (r1's `ties`)
- `model`: parameters for the parametric 3D model (colour, components, connectors) or a STEP path
- **`provenance`** for every number that matters: `datasheet <url/section>`, `photo <date>`,
  `measured <date>`, or `estimate <reason>`; estimates are what r1 marks [TBD-MEASURE]

Electrical pin data (types, voltage limits, I2C addresses) stays in the bench netlist, because it
depends on how the part is configured (r1's `ina228(ref, addr, note, sj1)`). The library holds only
physical facts, so a part is reusable across benches with different configurations.

r1's parts become the first library: NUCLEO-WL55JC1, #4755, #5832, #5580, S7V8F3, BOB-14021, #2674,
WAGO 222-413/415, #353 pack, #4090, #5978, #368/#369, QT boards (#5625, #6174, #4636, #6407, #4831),
axial resistor, ceramic and electrolytic capacitors, 2-pin link, QT-to-header cable.

## 7. Checks

Each rule is a module with an ID, a one-line statement, and a function returning
`Result(id, status, evidence, findings)`. `status` is pass, fail or waived; `evidence` counts what was
examined ("14 force strips, each alone"); `findings` name exact holes, pins and nets.

| ID | Rule | From r1 |
|---|---|---|
| S1 | bench.json validates against the schema; every ref and pin exists in the library and netlist | new |
| E1 | built copper (strips + conductors + part ties) partitions the pins exactly as the netlist does | `check()` [1] |
| E2 | the netlist round trip: KiCad's exported netlist equals the model; ERC clean (needs KiCad) | `checks.py` |
| H1 | every occupied hole exists (not a rail gap, not past the end) | [2] |
| H2 | one thing per hole; no hole under a seated board, a plug, a flat jumper or a lying part | [2] |
| H3 | every seated header pin lands on a hole | `SEAT_ERRORS` |
| F1 | a force-current net may sit in a breadboard strip only alone | [3] |
| J1 | jumpers are straight, on one board, and a kit length | [4] |
| L1 | every lead within its kind's limit, by routed 3D length where routed | [4], `outputs.py` |
| P1 | parts inside the plate and not overlapping (with declared exceptions such as stacked plugs) | [5] |
| R1 | every routed wire found a path; none passes over a used hole, a part or another wire's end | `routing.report()` |
| B* | bench-specific rules from `schematic/rules.py` (r1: firmware pins, I2C addresses and pull-ups, ground domains, modes) | `checks.py` |

**Waivers** are written in `bench.py` with `waive(rule, target, reason)` (r1's `FORCE_STRIP_OK`
becomes two waivers: the regulator VIN strip and the NTC return). A waiver that matches nothing fails.
The audit lists every waiver with its reason.

**Mutation tests** prove the checks: the test suite loads r1's `bench.json`, applies a named mutation,
and asserts the named rule fails. At least one mutation per rule, for example: move a Dupont end one
hole (E1), seat U5 one column off (H3 or E1), put a resistor lead under the charger (H2), add a second
pin to the LIPO strip (F1), make a jumper span 11 (J1), shorten the W1 limit (L1), push the pack off
the plate (P1), block a route's only gap (R1), drop a waiver (F1 fails).

## 8. Outputs

All under the bench's `out/`, regenerated by `python3 -m tools.breadboard all <bench>`.

- **`wiring-plan.md`**: today's structure (boards, board by board in build order, BOJACK cut list,
  Duponts with routed length and buy size, limited leads, everything else, open items).
- **`homes.md`**: everything off the breadboards.
- **Build cards** (`cards/BB1.svg`, `cards/BB1-step2.svg`, ..., `cards/index.html`):
  - the real hole grid in the board's own numbering, cropped to the columns in use plus a margin,
    at a scale that prints on A4/Letter landscape
  - steps in build order: 1 jumpers, 2 leaded parts, 3 seated modules, 4 flying wires; each step's
    SVG shows everything placed so far, the new items emphasised
  - every item labelled in place (R4 10k, U1 #4755 with its header pin names, D7 to CN6.6 GND)
  - a checklist table beside the grid, one row per item, matching the plan's numbering
  - `index.html`: one page per board with a step slider (plain HTML and inline SVG, no external
    scripts), linking each step to its 3D render
- **Plate card** (`cards/plate.svg` and steps; builder's call): everything off the breadboards, in the
  same style and numbering. Step 0 mount the boards and off-board parts (outlines and holders from
  `homes.md`); step 5 power-island leads (pigtails, force, solder, sense, WAGO leads); step 6 QT cables;
  step 7 external cables. Board steps 1-4 sit between 0 and 5, so the whole bench has one build order.
- **3D renders** (illustration tier): plate top and iso; per board top and iso; per board per step
  (the same steps, and plate steps 0, 5, 6, 7). Wire-end flags and ref labels stand above the boards in the 3D model. Each
  render's caption names its card step and the `bench.json` hash.
- **Colours** are set once in `bench.py` (BOJACK span colours from the kit, Dupont colours, QT wire
  colours) and used identically by cards, plan and renders.
- **Schematic**: `.kicad_sch` and PDF from the netlist (r1's generator), functional blocks as today.

## 9. Audit

`audit.json` (evidence tier) and `audit.md` (the same, readable):

- input hashes: `netlist.py`, `bench.py`, `bench.json`, every library part used
- tool versions: Python, numpy, KiCad (when used), the package's git blob hash
- every rule's Result, every waiver with its reason
- every estimate the bench depends on, from provenance, grouped by part: the measurement to-do list
- the hash of every evidence output; for illustration outputs, their stamp and whether it is current

`python3 -m tools.breadboard check <bench> --strict` fails on any failing rule or a stale output.

## 10. Operations

| Op | Does | Prints |
|---|---|---|
| `check` | compile and run every rule | one line per rule (status, evidence); findings |
| `route` | route all flying wires, write `routes.json` | per wire: kind, plan mm, 3D mm, buy size |
| `render` | KiCad boards and renders; `--board BB1 --step 2` for one view | files written |
| `plan` | wiring plan, homes, build cards | files written |
| `where` | what is in a hole or strip, and what is free on it | `BB1:h24 -> R4.2 (10k); strip h-j 24: 2 free` |
| `free` | free strips on a board for a need (n adjacent strips, rows, near a column, not force-adjacent) | ranked candidates |
| `move` | apply one change to an in-memory copy of `bench.json` (`seat U5 BB2:j44`, `end D7 BB1:B-25`), check and route it | rule deltas, route and length deltas, and the change in words (`D7: BB1:B-27 -> BB1:B-25`) |
| `all` | compile, check, route, plan, audit (and render with `--render`) | summary |

`move` never edits the authored file and has no `--apply` (builder's call): once the user approves a
move, the edit to `bench.py` is made by hand or by Claude as a normal reviewed change. That keeps
`author.py` free of source-line tracking.

## 11. The skill

`~/.claude/skills/breadboard-mockup/SKILL.md`: when to use it (laying out or reviewing a breadboarded
circuit), the workflow (survey; netlist; parts and library gaps with provenance; placement step by
step with approval; check; route; cards and renders; plan; audit), the user's standing rules (section
3), how to run each op, and how to add a part or a board. It points at `tools/breadboard/` in this repo
and says how to use it from another repo (run with this repo's path, or copy the package and pin the
git hash in the audit).

## 12. Port of r1 and acceptance

1. Move r1's schematic model to `schematic/netlist.py` unchanged in meaning; move bench checks to
   `schematic/rules.py`.
2. Write `layout/bench.py` with the authoring API, reproducing today's `build.py` data.
3. Golden test: the ported r1 must reproduce today's results: every correctness rule passes, with 124 pins in holes, 113
   conductors, 16 jumpers; the same routes (every wire's plan within 0.01 mm) and 3D lengths; the same
   Dupont buy sizes; and a `wiring-plan.md` with the same content (wording may change only where this
   design changes it, and the diff is reviewed once).
4. Today's W3 flag (routed 155 mm against the 150 mm QT-header cable) must still be reported, as an L1
   failure (a limit rule, so it does not block the outputs), until the bench is changed.
5. Delete r1's one-off scripts only after the golden test passes; tell the user first.
6. Acceptance: golden test passes; every rule has a passing mutation test; `--check` passes twice in a
   row with no diff; a tiny second bench (LED, resistor, NUCLEO 3V3) builds end to end from about 30
   lines of authoring, proving nothing r1-specific is in the engine.

## 13. Left to the builder

Builder's calls already made in this document (marked above): rule gating by class (section 5), r1's
route order as canonical and explicit conductor IDs (5.1), the plate card (8), `move` without
`--apply` (10). Also: numpy becomes a pinned dev dependency so CI can run the router tests; new tests
are named `test_bbtool_*.py` to avoid r0's `test_breadboard*.py`.


- Exact module boundaries and dataclass shapes within the architecture above.
- The bench.json schema details, provided it is sorted, versioned (`"schema": 1`) and complete enough
  that no stage needs the authoring Python.
- Card layout details (margins, fonts, label placement), provided labels never overlap holes in use and
  the SVG is byte-stable.
- Router internals, provided r1's routes are reproduced and ties are broken deterministically.
