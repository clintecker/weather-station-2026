# TX card cage: context pack for a fresh session (2026-11-16)

Read this first. Then read `README.md`, `build/ASSEMBLY.md` and the four cage specs (backplane-mount,
external-openings, shelves and lid-rim). `backplane-snap-mount-spec.md` is marked not used. Every dimension is in mm.

## What we're building

- **What it is:** the weather-station transmitter (TX), hand-built from protoboards.
- **The cards:** four SolderFul half-size breadboards (DigiKey DKS-SOLDERBREAD-02, 81.3 × 50.8) with their back rails
  snapped off. The cards are:
  - **B1** PORTS A
  - **B2** PORTS B + METERS
  - **B3** CORE: the Wio-E5 mini (A1), the SWD header J3, the SHTC3 (U5) and the SMA (AD1). There's no NUCLEO on
    B3. The NUCLEO is only the off-card SWD programmer.
  - **B4** POWER (regulator, INA228, MAX17048, battery and SYS leads)
- **How they fit:** the cards are horizontal shelves in a 3D-printed base. Each one plugs into a **backplane**, which is the
  plated end of a BusBoard PAD3U padboard lying on printed posts 8 mm off the floor.
- **How the box hangs:** on a pole, long side vertical, glands on the bottom wall.
- **Where the truth lives:** the electrical source of truth is `model.py`. Layout and geometry live in `layout/stack.py`
  and `cage/cage.py`, the measured dimensions in `sources.py`, and the bench build lists in `build/*.md`.
- **Checks:** `sh run.sh` rebuilds everything and runs schematic checks 1–10 plus layout checks L1–L13. It must pass
  before any commit.
  - Each run churns the renders. Revert what you didn't mean to change with
    `git checkout -- hardware/tx-stack-r1/renders hardware/tx-stack-r1/schematic/tx-stack-r1.pdf`.

## Clint's standing rules

- **Commits:** commit straight to master and push without asking. Agents commit. Then the controller re-runs run.sh,
  reverts the render churn and pushes.
- **Don't touch:**
  - never read or print anything under `run*/` directories
  - never print Clint's email, address or passwords
  - never flash boards or run `ws0 serve` in auto mode
- **Downloads:** each downloaded file (STLs from `~/Downloads`) goes in its own empty folder. Python that reads them
  runs with `-I`.
- **How to talk to Clint:**
  - be brief, with emoji status lines
  - ask multi-choice questions with AskUserQuestion, recommended option first
  - always name the exact board, face, hole, line and wire, never "the card"
  - review every PDF page yourself before you say it's cleared
  - never invent agent results
- **Each card comes out on its own.** You can pull any card without moving another. Nothing leaves a card except
  through its backplane header or a plug on that card (RJ11, SMA, SWD or USB-C).
- **Full 1×30 (emphatic).** Every card has a 1×30 right-angle header (j1–j30) in a 1×30 socket on the backplane.
  Never 18 or 26 pins. Each card has one spare pin pulled as its slot key (B1 27, B2 28, B3 29, B4 30).
- **Act on measurements:** apply Clint's fit corrections and ship the next print. Don't stall on conflicts.

## The decisions that are settled

### Box frame

**Box frame (Xb, Yb, Zb)**, as you look in from the lid with the glands down:
- Xb runs from the lid frame's left edge (the lid outline less 3). Enclosure 4's inside left wall face is at Xb 1.25.
  That's the wall with the card slots and the retention bar.
- Zb runs from the gland wall upward.
- Yb runs from the floor toward the lid.

Lid-centre frame (the CAD bot's): **X = Zb − 84.75, Y = 61.75 − Xb, Z = Yb + 3**.
- The box frame is left-handed on purpose, so card→box alone has det −1. L12 checks that card→box→lid
  (`stack.card_to_box`, then `cage.to_lid`) has det +1. It also checks every rendered view (`stack.VIEWS`,
  `MESH_AXES`, through `cage.to_lid`) for det +1.

### The base must be the MIRROR of the CAD bot's enclosure 2

- The CAD bot built the enclosure 2 STL from an older, mirror-image layout. From the lid with the glands down, it had
  the bar on the **right**.
- Real cards go component side up, front edge (column a) toward the lid. In the un-mirrored box, B3's SMA (past the
  card's right edge) would point into the bar wall. So would the RJ11 mouths of the layout before 2026-11-16, which
  sat flush with the 30 edge. Today the RJ11 mouths face the lid.
- **Settled on 2026-11-14:** the base is a mirror image, so the bar is on the **LEFT** from the lid and the corner post
  on the **RIGHT**. Every spec and PDF shows it that way.
- Clint said once that "the bar is on the right in real life", but he had the un-mirrored STL in front of him. He
  accepted the mirror after we explained it.
- We rejected the other options: cards component side down, or the jacks moved to the row-1 edge.
- **Check every new STL (enclosure 3 and later) for this first.**

### Backplane

- **The board:** the PAD3U's plated end, **31 lines (0–30) × 38 holes**. Line n sits under header pin n.
- **Cut:** score only the left edge, midway, 1.27 from line 0.
- **Outline when seated:** Xb 6.51–89.46, Zb 48.71–148.31.
- **Holes:** the factory holes are Ø2.80 drill with a Ø3.75 ring, on holes 2 and 37 (88.9 apart), 2.65 beyond the
  end row. **You don't drill anything** (enclosure 4, 2026-11-17).
- **Fixings: none.** Enclosure 4 has no screw posts. Clint: "When the cards are plugged into it, they hold it in
  place." The backplane is loose until the cards go in. (Enclosures 2 and 3 had two M3 screws at (7.78, 54.06) and
  (86.63, 54.06).)
- **Printed supports:** plain pads, Ø6: (58.58, 54.06), (78.90, 89.62) and (68.74, 127.72). The groove rail starts
  at Zb 67.
- **Edges:** the left edge sits in the groove in the bar wall. The upper right sits in a slot in the right corner post
  (Xb 85.8–92.3, Yb 8.0–10.1). The post now reaches Xb 95.8.
- **How to fit it:** tilt the right edge into the slot, lower the board, then slide it 2.84 left.
- **On the bench:** with FRONT up and hole 1 nearest you, the big holes are on the RIGHT. FRONT faces the lid.
- **Pads (Clint's photos IMG_8592–8594, 2026-11-16):** most pads are round. Every 5th line (29, 24 … 4, but line 30 is
  round) and every 5th hole row (holes 5, 10 … 35 from hole 1's edge) has square pads. Line 30 also has one lone
  square at hole 4. The pattern isn't symmetric, so FRONT is the face with the "PadBoard-3U … BusBoard.net" legend
  (`models.b_copper`).
- **Rendering:** render one scene per process (`scenes.py NAME`). A multi-scene run segfaults partway through and
  still exits 0.

### Cards and nets

- **Sockets:** 1×30 sockets at backplane holes 13, 19, 27 and 35.
- **Shared nets:**
  - lines 1–18: the bus, with GND on lines 2 and 12
  - lines 19–20: BAT_P
  - lines 21–22: CELL_P
  - line 23: GAUGE_S
  - line 26: SYS
  - Every other contact is an isolated pad (L11).
- **B1 and B2:** each RJ11 breakout stands on a soldered 1x6 male header in row a (six columns, six strips). The
  breakout overhangs the front (a) edge with its mouth toward the lid. There are no spacers and no flying leads.
  Before b9ae3ee (2026-11-16), the mouths sat flush with the 30 (right) edge.
- **B4:** SJ1 on U2 (INA228) is soldered closed, which joins VBUS to VIN+. Beep groups: J1+J24, J2+J12+J25, and
  J19–J22.
- **Routing:**
  - every wire end gets its own hole
  - underside wires keep at least 1.325 from used holes (L8)
  - the backplane support pads keep at least 1.5 from every copper-face joint (a 1.27 fillet round its hole) and
    from every bus wire (L7). Enclosure 4 has no screw posts.

## Files

### Repo: `hardware/tx-stack-r1/`

- **Cage specs for the CAD bot:**
  - `cage/backplane-mount-spec.md`: step 0 is MIRROR. After that come the post, slot and corner-post changes, and the
    card guides in section 6.
  - `cage/external-openings-spec.md`: 7 glands (five PG-7 and two PG-9, G7 removed), a vent and the SMA, after the
    mirror. Its section 1 heading still says "eight cable glands", which is a leftover.
  - `cage/shelves-spec.md`: the pack tray, right fin, charger ledge and keepers. The EVM outline is measured (90 x 90,
    J8 12 out). Its part heights, underside parts, J8 plug reach and tail positions are still TBD-MEASURE.
  - `cage/lid-rim-spec.md`.
  - `cage/backplane-snap-mount-spec.md` is marked not used (2026-11-13).
- **Instruction-PDF pipeline:** `sheets/` is a copy of the scratchpad pipeline, committed so it survives:
  - `sheets/session1/v2/`: `r3d.py`, `models.py`, `scenes.py`, `assembly.py`, `make_session1_v2.py`, plus the
    `handed.py` mirror check and the `holecheck.py` callout check (label to hole within 0.15)
  - `sheets/session2/`: B4 POWER, with `scenes2.py`, `make_session2.py` and `sheetlib.py`
  - venvs: `requirements-cad.txt` (CadQuery 2.7, Python 3.12) and `requirements-pdf.txt` (reportlab and svglib,
    Python 3.13)
  - The scripts reach the repo at `/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1` and resolve
    `session2` → `../session1/v2`.
  - **Style:** "cyberpunk IKEA". All geometry comes from real CadQuery models drawn as hidden-line art. Labels sit on
    paper chips, and every build runs the overlap check.
  - The scenes use the vendor STEP files in `render/models/` (git-ignored). Fetch them with `render/fetch_models.py`.
- **STL tools:**
  - `sheets/tools/stlinfo.py STL` prints the bounds and writes `verts.npy`
  - `sheets/tools/hmap.py` prints a height map in the box frame
  - `sheets/tools/sma_probe.py`
  - Run them with `.venv-cad/bin/python -I` from a scratch folder.

### Old session scratchpad (may be wiped)

`/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/`:
- `session1/v2/out/session1-all.pdf` (11 pages) isn't there any more. The build now puts it in
  `hardware/tx-stack-r1/sheets/session1/v2/out/` (also `sheets/out/`), which is git-ignored.
- `session2/out/session2-all.pdf` (12 pages)
- the `cadx` and `pdfenv` venvs
- `cadbot/` is empty now. Use the specs in `hardware/tx-stack-r1/cage/`.
- `stl-enc2/enc2.stl` is gone (the folder is empty). `stl-enc3/enc3.stl` is still there. It's a copy of
  `~/Downloads/enclosure 3.stl` from 2026-11-16.

Both PDFs, as page images, are also at https://claude.ai/artifact/SDZWoCHYXDoJhXiDKyWPd5. Republish that page when the
PDFs change.

## Where things stand (2026-11-17)

- **Enclosure 4** (`~/Downloads/enclosure 4.stl`) came in on 2026-11-17, and we audited it the same day
  (`sheets/audit-enc4/README.md`). It keeps enclosure 3's walls. The changes:
  - mounting flanges on both short ends
  - the v3 shelves
  - no backplane screw posts (the cards hold the backplane)
  - five PG-7 holes at Ø13.0 (G7 and both PG-9s gone)
  - the SMA bulkhead moved to Yb 94.14, Zb 60.38
  - a new 1 mm inside land (Zb 0–1) from about Xb 80 to the right wall
  - the right corner block's left face at Xb 106.85 for Zb 0–8

  Everything fits except the pack, which rides the tray lip's ramp.
  - **Two fixes asked of Clint** ("enclosure 4 + fixes", which the repo models):
    1. tray to Yb 62, with the lip's 45° ramp from Yb 56 to 62
    2. the two PG-9 holes back at (98, 25) and (98, 60), the right corner block back to Xb ≥ 110, and the 1 mm
       inside land cut away inside each Ø24 locknut keep-out

    **Re-audit the new STL when it comes.**
  - **Coax resolved (Clint, 2026-11-17):** the 6-inch coax fits the low bulkhead. It was worse at the old high one,
    where the cable had to bend to fit. **Session 6 check [TBD]:** a straight plug on the bulkhead's inner end reaches
    about Xb 93, above the EVM's lid-right corner.
  - **cage.py now models enclosure 4 + fixes** (2026-11-17). It has:
    - the R9 shell, 120 deep, with walls 4.25 / 4.0 (inside faces Xb 1.25 / 122.25, Zb 1 / 168.5)
    - four 15.4 corner blocks with Ø10 lid-bolt bores, and the 2 x 2.5 lip
    - the gland pockets and the flanges
    - the real EVM ledge, keeper, fin and lid-end block
    - the tray slots and support
    - the right post's relief over B2 and B1

    `cage.py --audit-stl` voxel-diffs clean against enclosure 4, except for the two fixes and the outside lettering
    (`sheets/audit-enc4/README.md`). The frame W x H stays the lid frame (123.5 x 169.5). box_in is now the real
    inside, 121 x 167.5 x 140.
  - Session 1 drops the drilling page (11 pages now). BACKPLANE.md and ASSEMBLY.md have no backplane screws.
  - **Lid fastening settled (Clint, 2026-11-17):** the four corner posts take Clint's 3D-printed bolts in their Ø10
    bores, with **no heat-set inserts** (`sources.lid_screw_opt` = c, and the M4 rows are gone). The only inserts are four
    M3s:
    - retention bar: Xb 5.0, Zb 76.5 / 146.5
    - EVM clip: Xb 4.5 / 100.25, Yb 106, down into the left keeper and the right lid-end block

    ASSEMBLY.md step 3 and Session 1 page 9 set all four. The pods keep their inserts.

- **Enclosure 3** (`~/Downloads/enclosure 3.stl`) is **printing now**. We audited it on 2026-11-16 (scripts and
  images in `sheets/audit-enc3/`).
  - **Verdict:** nothing stops a card or the backplane from fitting. It's mirrored (bar LEFT from the lid).
  - **Matches the spec to 0.01:**
    - all five posts, the bores and the Ø8 post's flat
    - the groove
    - the corner post (Xb 85.8–95.8) and its slot
    - the card slots: B4 Zb 78.98, B2 94.22, B1 114.54 and B3 134.86, each 1.9 tall
    - the cut-backs
    - the glands, the vent and the SMA hole. The printer made these 0.2 undersize, so **ream them to size**.
  - The fit check found zero interference. That covers the cards, the parts, the plugs and the backplane, including
    the 2.84 slide.
  - **Changes needed in the docs and PDFs:**
    1. **Retention-bar inserts moved.** The STL has them at **Xb 5.00, Zb 76.50 and 146.50**. The model had 3.25,
       76.0 and 147.0.
       - Drill the bar's Ø3.4 holes there, and update `sources.bar_inserts`, the bar spec and the PDFs.
       - The lower insert bore has only **0.48** of plastic to the floor of the B4 slot. Add a bench step: set that
         insert gently, then slide a 1.6 offcut through the front of the B4 slot. File the slot if the offcut binds.
    2. **The shell differs from the model** (enclosure 2 was the same):
       - the walls are 4.25 on the long sides and 4.0 on the short ones, so the inside is 121.0 × 167.5
       - the corner blocks are solid from the floor up to Yb ≈ 80
       - the wall top is at Yb 117 with a 2.0 lip, and there's no seam land at Yb 97
       - The cards clear all of this by at least 2.0, but `cage.py`'s shell should match the STL.
    3. **No shelves in enclosure 3.** Done: we redesigned them on 2026-11-16 for the next print (v3), in
       `cage/shelves-spec.md`. The enclosure 2 shelves blocked every gland cable. The tray was 1.9 over the nuts,
       and the right ledge sat over the PG-9 bores.
       - **Now:** the left ledge top sits 0.3 under the backplane's install column (Zb 48.41). The EVM's underside,
         the pack and a 3 mm tray stack down from it. That leaves a 13.5 cable space over the gland threads.
       - **Right side:** a floor-standing right fin carries the board's right edge and the tray's right end. The
         cables turn right under the tray and go up a right column (Xb 100.25–122.25).
       - **v3 also needs:** the left-wall rail from Zb 67, notches for the edge tails, two M3 keeper bosses with
         stepped tabs, and strap slots.
       - **EVM:** Clint measured it at 90 x 90, with J8 sticking out 12 (photo IMG_8591). The overhangs and tail
         positions are scaled from the photo (`sources`: evm_j8, evm_j8_x, evm_j8_lead, evm_overhang,
         evm_edge_tails).
       - **Model gap (closed 2026-11-17):** `cage.py`'s shell is now enclosure 4's (walls to Yb 117).
    4. The **SMA nut seat** sat 1.5 from the top-right corner block (the spec asks for 2.0). That gap applied to
       enclosure 3's SMA at Zb 144.6. Enclosure 4 moved the bulkhead low (Yb 94.14, Zb 60.38), so the old spanner
       note doesn't apply any more. No PDF carries it.
    5. The bar is 2.5 thick (`sources.bar`) and sits 1.00 in front of the card front edges, which is OK.
- **PDFs (2026-11-16):**
  - **Session 1: PREP** is 11 pages, cards first, then the base. We dropped the drilling page. The pages are:
    - cover
    - what you are building
    - 01 snap the card rails
    - 02 label/photo/report
    - 03 measure the insert
    - 04 backplane 1/5–5/5 (five pages)
    - 05 report the base

    Steps 03–05 are revised, first for enclosure 3 (5df6efc) and now for enclosure 4 (no backplane screws, four M3
    inserts, B4-slot offcut check).
  - **Session 2: B4 POWER** (12 pages).
  - The built page's BACKPLANE leader used to point at B4, because B4 hid the anchor at line 4. The leader now sits
    between lines 27 and 28. `r3d.Scene.anchor(..., on=part)` fails the render if another part hides an anchor.
  - The rendered SVGs (`svg/`) and `out/` are git-ignored. Copy them from the old scratchpad or re-render.
- **Clint still owes:**
  - if he already cut the backplane at 30 lines (it needs 31: lines 0–30)
  - the distance from the PAD3U plated edge to line 30 (TBD-MEASURE, about 5.48 and at most 6.13)
  - the M3 insert test
  - the card snap-line distance
  - the rest of the EVM dimensions (the outline is in, and the shelves spec lists what's still TBD-MEASURE)
  - the gland and SMA thread lengths
- **Parts to get** (README "Not yet ordered"):
  - from DigiKey: 20 x BAT85S-TR, 10 x 1N5232BTR and 15 x CF14JT100R
  - the 132172 SMA adapter
  - the glands
  - 2 hose clamps
  - an M12 vent
  - a JST PH pigtail
  - a USB-C to micro-B cable
  - a strap and foam tape

  You cut the 1×30 headers and sockets from generic stock that's already on hand.
