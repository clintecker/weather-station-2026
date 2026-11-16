# TX card cage: context pack for a fresh session (2026-11-16)

Read this first, then `README.md`, `build/ASSEMBLY.md` and the three cage specs. Every dimension is in mm.

## What we're building

- **What it is:** the weather-station transmitter (TX), hand-built from protoboards.
- **The cards:** four SolderFul half-size breadboards (DigiKey DKS-SOLDERBREAD-02, 81.3 × 50.8) with their back rails
  snapped off. The cards are:
  - **B1** PORTS A;
  - **B2** PORTS B + METERS;
  - **B3** CORE (NUCLEO/Wio-E5 side);
  - **B4** POWER (regulator, INA228, MAX17048, battery and SYS leads).
- **How they fit:** the cards are horizontal shelves in a 3D-printed base. Each one plugs into a **backplane**, which is the
  plated end of a BusBoard PAD3U padboard lying on printed posts 8 mm off the floor.
- **How the box hangs:** on a pole, long side vertical, glands on the bottom wall.
- **Where the truth lives:** the electrical source of truth is `model.py`. Layout and geometry live in `layout/stack.py`
  and `cage/cage.py`, the measured dimensions in `sources.py`, and the bench build lists in `build/*.md`.
- **Checks:** `sh run.sh` rebuilds everything and runs schematic checks 1–10 plus layout checks L1–L12. It must pass
  before any commit.
  - Running it churns the renders. Revert what you didn't mean to change with
    `git checkout -- hardware/tx-stack-r1/renders hardware/tx-stack-r1/schematic/tx-stack-r1.pdf`.

## Clint's standing rules

- **Commits:** commit straight to master and push without asking. Agents commit; the controller re-runs run.sh,
  reverts the render churn, then pushes.
- **Don't touch:**
  - never read or print anything under `run*/` directories;
  - never print Clint's email, address or passwords;
  - never flash boards or run `ws0 serve` in auto mode.
- **Downloads:** each downloaded file (STLs from `~/Downloads`) goes in its own empty folder. Python that reads them
  runs with `-I`.
- **Talking to Clint:**
  - be brief, with emoji status lines;
  - ask multi-choice questions with AskUserQuestion, recommended option first;
  - always name the exact board, face, hole, line and wire, never "the card";
  - review every PDF page yourself before saying it's cleared;
  - never invent agent results.
- **Each card comes out on its own.** Any card can be pulled without moving another. Nothing leaves a card except
  through the backplane header or a plug on that card (RJ11, STEMMA QT, SMA).
- **Full 1×30 (emphatic).** Every card has a full 1×30 right-angle header in J1–J30, plugged into a 1×30 socket on the
  backplane. Never 18 or 26 pins, and no pulled pins.
- **Act on measurements:** apply Clint's fit corrections and ship the next print. Don't stall on conflicts.

## The decisions that are settled

### Box frame

**Box frame (Xb, Yb, Zb)**, looking in from the lid with the glands down:
- Xb runs from the inside of the **left** wall, the card-block / retention-bar wall;
- Zb runs from the gland wall upward;
- Yb runs from the floor toward the lid.

Lid-centre frame (the CAD bot's): **X = Zb − 84.75, Y = 61.75 − Xb, Z = Yb + 3**.
- The box frame is left-handed, and that's deliberate. L12 checks that card→box and every rendered view are proper
  (det +1).

### The base must be the MIRROR of the CAD bot's enclosure 2

- The CAD bot's enclosure 2 STL was built from an older, mirror-image layout. Seen from the lid with the glands down,
  it had the bar on the **right**.
- Real cards go component side up, front edge (column a) toward the lid. In that box the RJ11 mouths (flush with the
  row-30 edge) and B3's SMA would point into the bar wall.
- **Settled on 2026-11-14:** the base is mirrored, so the bar is on the **LEFT** from the lid and the corner post on
  the **RIGHT**. Every spec and PDF shows it that way.
- Clint briefly said "the bar is on the right in real life", but he was looking at the un-mirrored STL. He accepted the
  mirror once that was explained.
- The alternatives were rejected: cards component side down, or moving the jacks to the row-1 edge.
- **Any new STL (enclosure 3 and later) must be checked for this first.**

### Backplane

- **The board:** the PAD3U's plated end, **31 lines (0–30) × 38 holes**. Line n sits under header pin n.
- **Cut:** only the left edge is scored, midway, 1.27 from line 0.
- **Outline when seated:** Xb 6.51–89.46, Zb 48.71–148.31.
- **Holes:**
  - the factory holes are Ø2.80 drill with a Ø3.75 ring, on holes 2 and 37 (88.9 apart), 2.65 beyond the end row;
  - one hole is drilled: line 0 hole 2, Ø3.2, **before** the snap;
  - the lower factory hole is opened to 3.2.
- **Fixings:** two **M3** screws into heat-set inserts. M4 heads would hit the EVM.
- **Printed posts:**
  - screw posts: bottom left at (7.78, 54.06), Ø8 with a flat; bottom right at (86.63, 54.06), Ø7; insert bore
    Ø4.0 × 6.5;
  - plain supports, Ø6: (58.58, 54.06), (78.90, 89.62) and (68.74, 127.72).
- **Edges:** the left edge sits in the groove in the bar wall. The upper right sits in a slot in the right corner post
  (Xb 85.8–92.3, Yb 8.0–10.1). The post is widened to Xb 95.8.
- **Fitting:** tilt the right edge into the slot, lower the board, then slide it 2.84 left.
- **On the bench:** FRONT up and hole 1 nearest you puts the big holes on the RIGHT. FRONT faces the lid.

### Cards and nets

- **Sockets:** 1×30 sockets at backplane holes 13, 19, 27 and 35.
- **Shared nets:**
  - lines 1–18: the bus, with GND on lines 2 and 12;
  - lines 19–20: BAT_P;
  - lines 21–22: CELL_P;
  - line 23: GAUGE_S;
  - line 26: SYS.
  - Every other contact is an isolated pad (L11).
- **B1 and B2:** the back RJ11 breakouts sit on a 3.04 spacer.
- **B4:** SJ1 on U2 (INA228) is soldered closed, which joins VBUS to VIN+. Beep groups: J1+J24, J2+J12+J25, and
  J19–J22.
- **Routing:**
  - every wire end gets its own hole;
  - underside wires keep at least 1.325 from used holes (L8);
  - posts keep at least 1.5 from joints and bus wires (L7).

## Files

### Repo: `hardware/tx-stack-r1/`

- **Cage specs for the CAD bot:**
  - `cage/backplane-mount-spec.md`: step 0 is MIRROR, followed by the post, slot and corner-post changes, and the card
    guides in section 6;
  - `cage/external-openings-spec.md`: 8 glands, a vent and the SMA, after the mirror;
  - `cage/shelves-spec.md`: the pack tray and charger ledges (the EVM dimensions are still TBD);
  - `cage/lid-rim-spec.md`.
- **Instruction-PDF pipeline:** `sheets/`, a copy of the scratchpad pipeline committed for persistence:
  - `sheets/session1/v2/`: `r3d.py`, `models.py`, `scenes.py`, `assembly.py`, `make_session1_v2.py`, plus the
    `handed.py` mirror check and the `holecheck.py` callout check (label to hole within 0.15);
  - `sheets/session2/`: B4 POWER, with `scenes2.py`, `make_session2.py` and `sheetlib.py`;
  - venvs: `requirements-cad.txt` (CadQuery 2.7, Python 3.12) and `requirements-pdf.txt` (reportlab and svglib,
    Python 3.13).
  - Scripts reach the repo at `/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1` and resolve
    `session2` → `../session1/v2`.
  - **Style:** "cyberpunk IKEA". All geometry comes from real CadQuery models drawn as hidden-line art. Labels sit on
    paper chips, and the overlap check runs on every build.
  - The scenes use the vendor STEP files in `render/models/` (git-ignored; fetch them with `render/fetch_models.py`).
- **STL tools:**
  - `sheets/tools/stlinfo.py STL` prints the bounds and writes `verts.npy`;
  - `sheets/tools/hmap.py` prints a height map in the box frame;
  - `sheets/tools/sma_probe.py`.
  - Run them with `.venv-cad/bin/python -I` from a scratch folder.

### Old session scratchpad (may be wiped)

`/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/`:
- `session1/v2/out/session1-all.pdf` (11 pages) and `session2/out/session2-all.pdf` (12 pages);
- the `cadx` and `pdfenv` venvs;
- `cadbot/`: the three specs plus `README-FOR-CADBOT.md`;
- `stl-enc2/enc2.stl` (un-mirrored) and `stl-enc3/enc3.stl` (copied from `~/Downloads/enclosure 3.stl` on
  2026-11-16).

Both PDFs, as page images, are also at https://claude.ai/artifact/SDZWoCHYXDoJhXiDKyWPd5. Republish that page when the
PDFs change.

## Where things stand (2026-11-16)

- **Enclosure 3** (`~/Downloads/enclosure 3.stl`) is **printing now**. It was audited on 2026-11-16 (scripts and
  images in `sheets/audit-enc3/`).
  - **Verdict:** nothing stops a card or the backplane from fitting. It is mirrored (bar LEFT from the lid).
  - **Matches the spec to 0.01:**
    - all five posts, the bores and the Ø8 post's flat;
    - the groove;
    - the corner post (Xb 85.8–95.8) and its slot;
    - the card slots: B4 Zb 78.98, B2 94.22, B1 114.54 and B3 134.86, each 1.9 tall;
    - the cut-backs;
    - the glands, the vent and the SMA hole. These are printed 0.2 undersize, so **ream them to size**.
  - The fit check found zero interference. That covers the cards, the parts, the plugs and the backplane, including
    the 2.84 slide.
  - **Changes needed in the docs and PDFs:**
    1. **Retention-bar inserts moved.** The STL has them at **Xb 5.00, Zb 76.50 and 146.50**; the model had 3.25,
       76.0 and 147.0.
       - Drill the bar's Ø3.4 holes there, and update `sources.bar_inserts`, the bar spec and the PDFs.
       - The lower insert bore has only **0.48** of plastic to the floor of the B4 slot. Add a bench step: set that
         insert gently, then slide a 1.6 offcut through the front of the B4 slot and file it if it binds.
    2. **The shell differs from the model** (enclosure 2 was the same):
       - the walls are 4.25 on the long sides and 4.0 on the short ones, so the inside is 121.0 × 167.5;
       - the corner blocks are solid from the floor up to Yb ≈ 80;
       - the wall top is at Yb 117 with a 2.0 lip, and there is no seam land at Yb 97.
       - The cards clear all of this by at least 2.0, but `cage.py`'s shell should be updated to match the STL.
    3. **No shelves in enclosure 3.** ✅ Done 2026-11-16: the pack and tray moved 12.5 right (`cage.CORNER_BLOCK_X`),
       so the pack is now at Xb 18.5–87.5 and the tray at 16.5–89.5, clear of the bottom-left corner block
       (Xb 0–16.5, Zb 0–16.4). `shelves-spec.md` is updated.
    4. The **SMA nut seat** sits 1.5 from the top-right corner block (the spec asks for 2.0). The nut fits, but tell
       the PDF to use an open spanner on the 3/8 in nut.
    5. The bar is 2.5 thick (`sources.bar`) and sits 1.00 in front of the card front edges, which is OK.
- **PDFs (re-split 2026-11-16, cards first):**
  - **Session 1: CARDS** (4 pages): cover, what you are building, snap the card rails, label/photo/report.
  - **Session 2: B4 POWER** (12 pages), unchanged apart from the shared built page, which now says enclosure 3.
  - **Session 3: BASE** (10 pages): cover, built page, measure the insert, backplane 1–6, report.
    **These are still the enclosure 2 pages.** Revise them for enclosure 3 (items 1, 2 and 4 above) before Clint
    builds the base.
  - `make_session1_v2.py` builds both Session 1 and Session 3. The rendered SVGs (`svg/`) and `out/` are git-ignored;
    copy them from the old scratchpad or re-render with `scenes.py`.
- **Clint still owes:**
  - whether the backplane was already cut at 30 lines (it needs 31: lines 0–30);
  - the distance from the PAD3U plated edge to line 30 (TBD-MEASURE, about 5.48 and at most 6.13);
  - the M3 insert test;
  - the card snap-line distance;
  - the EVM dimensions;
  - the gland and SMA thread lengths.
- **Parts to get:** four 1×30 right-angle headers, four 1×30 female sockets, a BAT85 and a 1N5232B (DigiKey).
