# Outdoor Sensor Pods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three outdoor I2C pods (TH, baro, UV) buildable: a checked layout model of each Perma-Proto pod
board, a printed pod box per pod, the remixed shield cap and arm, and bench sheets in the TX-card style.

**Architecture:** A new self-contained tree, `hardware/pods-r1/`, mirrors `hardware/tx-stack-r1/`. It has a
dimension table (`sources.py`), a pure-Python board model and checks (`layout/`), CadQuery parts (`box/`, `shield/`),
and reportlab sheets (`sheets/`), all run by `run.sh`. The sheets reuse the TX sheet libraries (`r3d.py`,
`sheetlib.py`, `models.py`) by import. Nothing in `hardware/tx-stack-r1/` is edited: that tree is being changed
for the enclosure 4 shell. The pods only read the TX port model and the shared values from it.

**Tech Stack:** Python 3 (model, checks, pytest), CadQuery + `r3d` hidden-line scenes (`.venv-cad`), reportlab
(`pdfenv`), `manifold3d` for the shield mesh remix.

**Spec:** `docs/superpowers/specs/2026-11-17-sensor-pods-design.md` (approved 2026-11-17)

## Global Constraints

- **Sensor-port pin map** (unchanged from the TX): pin 2 = 3.3 V, 3 = SDA, 4 = GND, 5 = SCL; pins 1 and 6 unused.
- **Pods:**
  - TH = Adafruit SHT45 #6174 (0x44);
  - Baro = Adafruit BMP581 #6407 (0x47);
  - UV = Adafruit LTR390 #4831 (0x53).
- **ID EEPROM:** Adafruit 24LC32 STEMMA QT breakout (#5146 as far as known), at 0x50. Every pod has one, behind
  its own TX mux channel.
- **Pod board:** Adafruit Perma-Proto Quarter #1608. Its outline, hole grid and strips come from Adafruit's own
  PCB file, never from a ruler.
- **Jack:** SparkFun BOB-14021 + Amphenol 87180-066LF on a 1x6 header, built as on the TX cards: tab snapped off,
  jack pins cut flush.
- **No series or protection parts on the pod:** the TX port already has the PTC, the series resistors and the
  clamps.
- **Write protect:** a 2-pin header with a Sullins SPC02SYAN shunt. Shunt on = protected.
- **TH lead:** stranded, coloured red 3.3 V, black GND, yellow SCL, blue SDA. It is soldered to the SHT45's own
  header pads. The only joints inside the shield's measured air are those four pads.
- **Cable:** round straight-through 6-conductor, OD 3.0–4.3 mm for the PG-7 #762 (otherwise that end gets a
  PG-9), under 2 m. Both plugs are crimped after the cable passes the glands.
- **Box:** printed PETG, light colour. The lid seals on an O-ring or gasket and is held by screws into heat-set
  inserts, never glued. One PG-7 at the bottom with a drip loop.
- **Shield:** only the top cap (object_70) and the L-arm (object_72) are remixed. The 3MF and every file derived
  from its meshes stay out of git: record a local path and a sha256.
- **Sheets:** follow the `instruction-sheet-style`, `draw-breakouts-as-supplied` and `name-exact-parts` memories.
  Every breakout is drawn as supplied, every hole is named, every part has its exact name, and every page is
  reviewed as an image before it's called done.
- **Repo rules:** commit to master and push; `hardware/pods-r1/run.sh` must pass before each commit; never touch
  `run*/` folders.

## Review Focus

1. **A reversed (crossover) RJ cable.** It puts 3.3 V on SCL and GND on SDA. Expect the bench sheets to make you
   check the cable pin to pin before it ever touches a port. Task 4 adds `cable_map("reversed")`, which must
   report the 3.3 V↔SCL and SDA↔GND swaps, and Task 8 adds the cable continuity page.
2. **Pull-ups left on every breakout.** The mux's 10 k, the sensor's 10 k and the EEPROM's 10 k give 3.33 k per
   line. Expect the check to state the per-port total and rise time for the longest cable (2 m), not a pass on
   defaults. Task 4 has `test_pullup_budget_two_metres`.
3. **The Adafruit EEPROM board's own WP default** (pulled low or high on the board). Expect "shunt on =
   protected" to stay true whatever the board's resistor does. Task 3 reads it from Adafruit's file; Task 4 has
   `test_wp_shunt_protects`.
4. **Rain on the box.** Expect the gland and the baro vent to face down and the lid seam never to sit under
   standing water. Task 6 has `test_openings_face_down`.
5. **A pod plugged into any port, including the spare S4.** Expect it to work with no port-specific wiring.
   Task 4 has `test_pod_port_independent`: every pod's pin map against each of S1–S4 in the TX model.

---

### Task 1: `hardware/pods-r1` scaffold and dimension table

**Files:**
- Create: `hardware/pods-r1/sources.py`, `hardware/pods-r1/run.sh`, `hardware/pods-r1/README.md`
- Test: `tests/test_pods_sources.py`

**Interfaces:**
- Produces:
  - `sources.D: dict[str, tuple[value, what, source, status]]`, with status in {"sourced", "derived", "TBD"},
    the same shape as `hardware/tx-stack-r1/sources.py`;
  - `val(key)`, `tbd(key) -> bool`, `label(key) -> str`;
  - `sync_readme(check: bool)`, which writes or checks the README table between the markers.
  - Shared TX values are re-exported from the TX `sources.val` by key (read-only import), for example `bob`
    and `jack_87180`; nothing is copied by hand.

- [ ] **Step 1: Write the failing test.**
  - `test_keys_present`: the table has `permaproto_q` (outline and grid), `sht45`, `bmp581`, `ltr390`,
    `eeprom_24lc32` (each: outline, pin order, pull-up value, address), `pg7_seal` = (3.0, 4.3), `cable_max_m` = 2.0,
    `cable_pf_per_m` (TBD), `i2c_sink_ma` = 3.0 and `rise_ns_max` = 1000.
  - `test_every_sourced_row_cites`: every row with status "sourced" has a URL or a file path in its source.
  - `test_shield_not_in_git`: no `*.3mf` and nothing derived from the shield is tracked under `hardware/pods-r1/`
    (`git ls-files`).
- [ ] **Step 2:** Run `pytest tests/test_pods_sources.py -v`. Expected: FAIL (no module).
- [ ] **Step 3: Implement `sources.py` with every value cited.**
  - Breakout outlines, pin orders, pull-ups, the EEPROM's WP default and the Perma-Proto grid come from
    Adafruit's PCB repos on GitHub (Eagle `.brd`). Cite the URL and the commit.
  - Cable capacitance stays TBD until the bought cable is measured.
  - Shield: `shield_3mf` = (local path, sha256), status "sourced", with the path outside git.
  - `run.sh` runs `python3 sources.py --check`, the layout checks (Task 4) and the CAD steps (Tasks 5–7), and
    exits non-zero on the first failure.
- [ ] **Step 4:** Run `pytest tests/test_pods_sources.py -v && sh hardware/pods-r1/run.sh`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 scaffold and dimension table`.

### Task 2: Perma-Proto Quarter board model

**Files:**
- Create: `hardware/pods-r1/layout/permaproto.py`
- Test: `tests/test_pods_permaproto.py`

**Interfaces:**
- Produces:
  - `HOLES: dict[str, tuple[float, float]]`, the name of each hole as printed on the board mapped to its (x, y) in
    mm. The origin is the board's lower-left corner with the silkscreen readable.
  - `strip_of(hole: str) -> str`: the copper group each hole belongs to (the 5-hole strips and the rails).
  - `OUTLINE`: polygon and mounting holes.
  - `side_of(hole) -> "top"|"bottom"` is not needed: holes are plated through both sides.

- [ ] **Step 1: Write the failing test.**
  - `test_grid_matches_adafruit`: the hole count, pitch 2.54 and the outline match `sources.val("permaproto_q")`.
  - `test_strips`: each strip holds exactly the holes Adafruit's copper joins, and no hole is in two strips.
  - `test_names_as_printed`: the names on the board's silkscreen exist in `HOLES`.
- [ ] **Step 2:** Run `pytest tests/test_pods_permaproto.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement it from the Eagle file** cited in Task 1 (parse the `.brd` XML for its pads and
  signals). Commit the parsed data, not the `.brd`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 Perma-Proto quarter model from Adafruit's PCB file`.

### Task 3: Pod board layouts (TH, BARO, UV)

**Files:**
- Create: `hardware/pods-r1/layout/pods.py`
- Test: `tests/test_pods_layout.py`

**Interfaces:**
- Consumes: `permaproto.HOLES` and `strip_of`, and `sources.val`.
- Produces:
  - `POD_NAMES = ("TH", "BARO", "UV")`;
  - `pod(name) -> Pod`.
- A `Pod` has:
  - `parts: list[Placed]` (ref, kind, pins `{pin_name: hole}`, 3D boxes, note);
  - `wires: list[Wire]` (net, hole_a, hole_b, side, colour);
  - `lead: Lead | None`, used by TH only: the SHT45 pad names, conductor colours and length;
  - `nets() -> dict[str, set[str]]`.
- The parts are J1 (BOB-14021 on 1x6, pins 1–6), U1 (EEPROM breakout), JP1 (WP 2-pin header) and U2 (the sensor
  breakout; absent on TH, where the lead lands on pads instead).

- [ ] **Step 1: Write the failing test.**
  - `test_parts_named_exactly`: each pod's parts carry their maker numbers (#6174, #6407, #4831, #5146, BOB-14021,
    87180-066LF, SPC02SYAN).
  - `test_all_pins_on_holes`: every pin sits on an existing hole, and no two parts share a hole unless the model
    marks it as a joint.
  - `test_breakouts_as_supplied`: each breakout's outline and pin order equal its `sources` row, with no rotation
    that would mirror the pin order.
  - `test_th_lead_colours`: the TH lead runs red→3V3, black→GND, yellow→SCL and blue→SDA, and lands on the SHT45's
    VIN, GND, SCL and SDA pads.
- [ ] **Step 2:** Run `pytest tests/test_pods_layout.py -v`. Expected: FAIL.
- [ ] **Step 3: Lay out the three boards by hand as data in `pods.py`.**
  - The jack faces the box's gland side.
  - The EEPROM's WP pad goes to JP1, wired so that shunt on = protected, using the board's WP default from Task 1.
  - The same footprint and wiring are used for all three where possible: only U2 or the lead differs.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 board layouts for TH, BARO, UV`.

### Task 4: Pod electrical checks

**Files:**
- Create: `hardware/pods-r1/layout/pod_checks.py`, which runs P1–P7 and prints a report;
  `run.sh` calls it.
- Test: `tests/test_pods_checks.py`

**Interfaces:**
- Consumes:
  - `pods.pod(name).nets()` and `permaproto.strip_of`;
  - the TX port model, read-only: `hardware/tx-stack-r1/schematic/model.py`, giving each S1–S4 jack's pin → net
    and the mux channel's pull-up.
- Produces:
  - `netlist(pod) -> dict[net, set[(ref, pin)]]`, built from the strips plus the wires;
  - `cable_map(kind: "straight"|"reversed") -> dict[int, int]`;
  - `end_to_end(pod, port) -> dict[int, tuple[pod_net, tx_net]]`;
  - `pullup_total(pod) -> float` (ohms);
  - `rise_ns(pod, metres) -> float`;
  - `check_all() -> list[str]` (failures).

- [ ] **Step 1: Write the failing test.**
  - `test_no_shorts`: no two nets share a strip, and every one of 3V3, GND, SDA and SCL is one connected group.
  - `test_pin_map`: jack pin 2→3V3, 3→SDA, 4→GND and 5→SCL; pins 1 and 6 are unconnected.
  - `test_pod_port_independent`: `end_to_end(pod, port)` gives matching nets for every pod against each of S1–S4.
  - `test_cable_reversed_flagged`: `cable_map("reversed")` maps 2↔5 and 3↔4, and `end_to_end` with it reports
    3V3→SCL.
  - `test_addresses_unique`: TH has {0x44, 0x50}, BARO {0x47, 0x50} and UV {0x53, 0x50}.
  - `test_pullup_budget_two_metres`: `pullup_total ≥ (3.3-0.4)/3 mA = 967 Ω`, and
    `rise_ns(pod, 2.0) = 0.8473·R·C ≤ 1000`. C counts the cable pF/m × 2 m, 10 pF per device and the TH lead. If
    the budget fails, the check names which breakout's pull-up jumper to cut, and the pod model records it.
  - `test_wp_shunt_protects`: with the shunt on, the EEPROM's WP is at 3V3; with it off, WP is at the board's
    default.
- [ ] **Step 2:** Run `pytest tests/test_pods_checks.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement it.** Union-find over the strips and the wires, the same method as TX `layout_checks`
  `build_copper`.
- [ ] **Step 4:** Run the same command, then `sh hardware/pods-r1/run.sh`. Expected: PASS, with the report
  printing the pull-up total and rise time for each pod.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 electrical checks P1-P7`.

### Task 5: Assembled shield and the SHT45 fit

**Files:**
- Create: `hardware/pods-r1/shield/assemble.py`. It reads the local 3MF named by `sources.shield_3mf`, checks its
  sha256, and writes nothing into git.
- Test: `tests/test_pods_shield.py`. It is skipped with a clear reason when the 3MF isn't present, as in CI.

**Interfaces:**
- Produces:
  - `assembled() -> dict[object_id, (vertices, faces)]`, each placed in the shield frame: Z up and the plate axis
    at the origin;
  - `core_clear(z) -> float`, the clear radius at a height;
  - `stand_face() -> (origin, normal, extent)`;
  - `sht45_fit() -> float`, the minimum clearance to any post or plate in mm.

- [ ] **Step 1: Write the failing test.**
  - `test_mating_features`: the plates stack on their post bosses, the stand's foot sits in the base cup, and the
    cup meets the arm's holes. Each mate is within 0.3 mm.
  - `test_core_clear`: `core_clear` is ≥ 20 (the Ø40 core) through the plate stack.
  - `test_sht45_fits`: `sht45_fit()` ≥ 5.0 with the board on the stand's inner face. This replaces the
    provisional fit in the spec.
- [ ] **Step 2:** Run `pytest tests/test_pods_shield.py -v`. Expected: FAIL.
- [ ] **Step 3: Derive each part's placement** from the meshes' mating features, using the slicing from the
  2026-11-17 `shieldtools/fit.py` (triangle–plane sections). Don't assume the stand is on the axis.
- [ ] **Step 4:** Run the same command. Expected: PASS, or a reported misfit. If it misfits, record it in the
  spec's "Constraints and facts" and ask Clint before moving the SHT45.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 assembled shield and SHT45 fit`.

### Task 6: Pod box family

**Files:**
- Create: `hardware/pods-r1/box/podbox.py` (CadQuery). It writes `box/stl/pod-{th,baro,uv}-{body,lid}.stl`, and
  those files are committed: they are our own geometry.
- Test: `tests/test_pods_box.py`, which runs under `.venv-cad`. `run.sh` calls the box checks.

**Interfaces:**
- Consumes: `pods.pod(name)` (board, parts' 3D boxes, jack position) and `sources.val` (the PG-7 hole, the M3
  insert, the O-ring).
- Produces:
  - `body(name)` and `lid(name)`, both CadQuery solids;
  - `inside(name) -> Box`;
  - `openings(name) -> list[(kind, centre, axis)]`;
  - `mount_face(name) -> (plane, hole_xy list)`.

- [ ] **Step 1: Write the failing test.**
  - `test_board_fits`: the board, every part's box and the crimped plug in the jack (the plug's body plus
    `plug_bend`) clear the inside by ≥ 2.0. The lid closes over the tallest part with ≥ 2.0 to spare.
  - `test_openings_face_down`: the gland's axis and the baro vent's are within 10° of straight down in the mounted
    orientation. The baro vent has a baffle, so there's no straight line from outside to the sensor. The UV
    window's normal is within 5° of straight up.
  - `test_lid_not_glued`: the lid has an O-ring groove and ≥ 4 screws into heat-set insert bores sized from
    `sources`.
  - `test_uv_window_recorded`: the UV window's material key exists in `sources`. It may be TBD, but it may not be
    absent.
- [ ] **Step 2:** Run `.venv-cad/bin/python -m pytest tests/test_pods_box.py -v`. Expected: FAIL.
- [ ] **Step 3: Build one parametric box** whose size comes from the board, with per-pod options: the baro's
  downward vent and baffle (ePTFE membrane seat optional) and the UV's lid window recess.
- [ ] **Step 4:** Run the same command, then `sh hardware/pods-r1/run.sh`. Expected: PASS, with the STLs written.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 pod boxes (TH, BARO, UV)`.

### Task 7: Shield remix: the cap with UV bosses, the arm with pod faces

**Files:**
- Create: `hardware/pods-r1/shield/remix.py`. It writes the remixed STLs to a local folder outside git
  (`sources.shield_out`), because they are derived from the unlicensed meshes.
- Modify: `hardware/pods-r1/sheets/requirements` to add `manifold3d`.
- Test: `tests/test_pods_remix.py`, skipped when the 3MF is absent.

**Interfaces:**
- Consumes: `assemble.assembled()` and `podbox.mount_face(name)`.
- Produces: `cap_remixed()` and `arm_remixed()` (manifold meshes) and `remix_checks() -> list[str]`.

- [ ] **Step 1: Write the failing test.**
  - `test_cap_bosses`: the UV box's mount holes land on the cap's flat top, ≥ 3 mm from its edge, and the result is
    a closed manifold.
  - `test_arm_faces`: the TH and BARO box faces sit beside the base cup, below the plates. Their boxes clear the
    cup and the pole clamp by ≥ 5. The TH lead from the stand exits the base cup through an existing opening, or
    through a new hole named in the report.
- [ ] **Step 2:** Run `.venv-cad/bin/python -m pytest tests/test_pods_remix.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement it.** Use manifold unions and differences of CadQuery-built bosses and faces with the
  original meshes, then export.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit** (the code only) with the message
  `hardware: pods-r1 shield remix (cap bosses, arm pod faces)`.

### Task 8: Bench sheets, Session P: the pod boards

**Files:**
- Create: `hardware/pods-r1/sheets/scenes_p.py`, `make_session_p.py` and `out/` (gitignored). These import TX
  `sheets/session1/v2/{r3d,models}.py` and `sheets/session3/sheetlib.py` read-only.
- Test: the existing pipeline's label and hole checks run inside `make_session_p.py` and fail the build. Add
  `tests/test_pods_sheets.py`, which asserts the PDF builds and reports 0 label issues and 0 hole issues.

**Interfaces:**
- Consumes: `permaproto` and `pods` (every hole and wire), and `pod_checks.netlist`.
- Produces: `out/session-p-pods.pdf`.

- [ ] **Step 1: Write the failing test** `test_session_p_builds`. Its pages include: parts as supplied (each
  breakout, the jack board, the shunt); then, per pod, the jack header, the jack, the EEPROM, the WP header, the
  sensor or the TH lead, each wire, and the strip map; meters-before-power for each pod; and the cable page (crimp
  order and a pin-to-pin continuity check, so a reversed cable is caught before power).
- [ ] **Step 2:** Run `pytest tests/test_pods_sheets.py -v`. Expected: FAIL.
- [ ] **Step 3: Build the scenes and pages** in the Session 3–5 style. The TH lead page shows the SHT45 on its
  stand pads with the colours.
- [ ] **Step 4:** Run the same command. Expected: PASS. Then look at every page as an image (via `pdftoppm`) and fix
  anything wrong before calling it done.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 Session P sheets (pod boards, cable)`.

### Task 9: Bench sheets, Session Q: boxes, shield and installation

**Files:**
- Create: `hardware/pods-r1/sheets/scenes_q.py` and `make_session_q.py`.
- Test: `tests/test_pods_sheets.py::test_session_q_builds`.

**Interfaces:**
- Consumes: `podbox` (`body`, `lid`, `openings`), `remix` (the remixed cap and arm, from local files) and
  `assemble`.
- Produces: `out/session-q-install.pdf`.

- [ ] **Step 1: Write the failing test.** Its pages: inserts in each box; the gland; the board in its box; lid and
  O-ring; the SHT45 on the stand; the lead through the base cup; the UV box on the cap; TH and BARO on the arm; the
  drip loops; and the shunt checked on before closing.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Build the pages.
- [ ] **Step 4:** Run it. Expected: PASS. Then review every page as an image.
- [ ] **Step 5: Commit** with the message `hardware: pods-r1 Session Q sheets (boxes, shield, install)`, then add
  Sessions P and Q to the TX sheets artifact page.

## Self-review notes

- **Spec coverage.** Decided items 1–10 map to tasks as follows: 1 → T3/T4; 2 → T3/T5/T8; 3 → T6 (vent);
  4 → T6/T7; 5 → T3/T4; 6 → T1/T3; 7 → T6; 8 → T4/T8; 9 → T8/T9; 10 → T2–T4/T6. The "Left to the builder" items
  are covered in T3, T5, T6, T7 and T4 (pull-ups). The non-goals (the programming fixture, PCBs) have no task.
- The coverage check found only one gap: cable lengths can't be set until Clint mounts the shield on the pole. T4
  checks the 2 m worst case.
