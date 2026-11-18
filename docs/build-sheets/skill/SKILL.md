---
name: illustrated-build-sheets
description: |
  Make illustrated bench build sheets for a hardware project: printable PDF pages, one step per page plus a
  booklet, where every picture is rendered from real CAD geometry (CadQuery + OpenCascade hidden-line art with
  flat colour fills) and every label is a paper chip with a checked leader. Use it when the user asks for
  "build instructions", "assembly instructions", "bench sheets", "soldering guide", "step-by-step PDF",
  "IKEA-style instructions", "flat-pack instructions", "illustrated build guide", "wiring diagram pages for the
  bench", or wants a build document drawn from a CAD model, a layout script or a STEP file. Do not use it for
  schematics, PCB fabrication drawings or marketing renders.
---

# Illustrated build sheets

You will make PDF pages that a person reads at the bench, with a soldering iron in one hand. Each page shows one step. The pictures come from the real geometry of the real parts, so the page matches what lies on the bench. A machine check runs on every page before a person looks at it.

The method comes from the weather-station-2026 repo (`hardware/tx-stack-r1/sheets/` and `hardware/pods-r1/sheets/`). Paths from that repo appear below only as worked examples.

## Before you start

Get these four things. If one is missing, ask for it or mark the gap.

1. The build order. Which board first, which part first on each board (lowest part first, tallest last).
2. The parts as supplied. The maker part number of each board and part, and a photo of anything unusual. A breakout often ships with a fitted terminal block, socket or solder jumper.
3. Geometry. A maker STEP file, an Eagle or KiCad board file, or a datasheet drawing for each part.
4. The connections. A netlist, a layout script or a written build list that says which pin goes to which hole.

Never use an image generator for any picture that shows geometry, holes, wires or parts. A wrong picture costs a rebuild.

## The method

Work in this order. Each stage reads the one before it and adds no numbers of its own.

1. Write the facts table (`sources.py`). Put every dimension in it, each with its source and a status. See "The facts table" below.
2. Write the layout model and its checks. Place every part, pin and wire end on the real hole grid. Route each wire as a person lays it: flat, straight runs, right-angle bends, round the parts. Check that every pin lands on a real hole, that no two nets share copper, and that no parts collide in 3D. Write the text build list (`build/BOARD.md`) from this model.
3. Write the CadQuery models. Load the maker's STEP where it exists. Build the rest from the facts table. Model each board as it ships, with every factory-fitted part.
4. Write the scenes. One function per picture. Each builds a scene, adds parts with colours, adds decals (silkscreen, hole letters) on faces, and names anchors for every label.
5. Render each scene to SVG plus an anchor JSON, one scene per process.
6. Lay out the pages with reportlab and svglib. Put each SVG in a panel, then add chips, leaders, dimensions and captions. Read every caption, table and step list from the build list. Do not type them.
7. Run the checks. The build must exit non-zero on any label overlap or any hole callout that misses its hole.
8. Render every page to PNG and examine each one. Fix what you see, rebuild, and look again. Do not say "done" before this.

`references/starter-skeleton.md` has the file layout and the key function signatures. `references/style-guide.md` has the look. `references/pitfalls.md` lists what went wrong last time.

## The facts table

One Python dict holds every dimension that a model or a page uses. Each row has four fields.

```python
D = {
    # key: (value, what, source, status)
    "sb_w": (81.3, "SolderFul board length", "DKS-SOLDERBREAD-02 drawing p.2", "sourced"),
    "sb_x1": (3.82, "row 1 hole centre from the left edge", "(81.3 - 29 x 2.54) / 2", "derived"),
    "ra_tail": (3.05, "right-angle header solder tail", "Sullins PRPC drawing (.120): check on the part", "TBD"),
}
```

- Use `sourced` for a value read from a datasheet, a maker CAD file or a measurement with a date.
- Use `derived` for a value computed from sourced values. Write the formula in the source field.
- Use `TBD` for anything you could not source. The model can use it as a placeholder, but every label that shows it must carry `[TBD-MEASURE]`.
- Give each source a page number, a file name and line, or a commit, so that a person can find it again.
- Generate the project README's dimension table from the dict, and add a `--check` mode that fails when the README is out of date.

When the user measures a part, change the row to `sourced`, add the date, and rebuild everything downstream.

## Style rules

These rules come from the person who uses the sheets. `references/style-guide.md` has the palette, fonts and page grid.

- Draw every part from real geometry. A picture that does not match the part on the bench is a bug.
- Draw each breakout as supplied. If the build does not use a factory-fitted part, show it fitted and add a step to remove it. Run the 3D clash check with the part fitted, so you learn why it must come off.
- Draw a lead soldered to a pad as a solder joint on that pad. It must not look as if it goes into a nearby socket.
- Draw the copper as it is. On stripboard or a breadboard-style card, show the strips joined as on the real board.
- Name the exact part every time: the board's name, the face, and how to recognise that face. Never write "the card" or "the board" when there is more than one.
- Give holes as the board prints them (row letter and column number, such as E10). If the board prints nothing, define names once on the "know the faces" page and use only those.
- Name each wire by gauge, type and colour, with its cut length in mm.
- Put every label on a solid paper chip. The leader starts at the chip edge and ends on a dot on the part. On a busy or coloured background, draw leaders black on a white halo.
- One step per page. Also build one booklet with all pages. Start with a cover (parts as supplied, tools, the steps) and a "what you are building" page. End each board with a "meter before power" page of continuity checks.
- Keep the voice deadpan and short. One footer slogan per page, such as "METER FIRST. POWER NEVER. NOT TODAY."

## Quality gates

Do not hand over a sheet until all of these pass.

1. The facts table check passes, and every TBD value on a page shows `[TBD-MEASURE]`.
2. The layout checks pass (holes, nets, 3D clashes).
3. Every scene renders, and every expected SVG exists and is not empty. A render process can crash and still exit 0.
4. The renderer refuses mirrored pictures. Each scene declares each map that carried its geometry, and the render stops on a determinant below zero.
5. Every anchor that a leader names is visible on the part it names. The render stops if another part hides it.
6. The label check passes on every page. No chip overlaps a chip, a panel edge, a badge or a caption. No leader crosses another chip.
7. The hole check passes on every page. Each callout is within 0.15 mm of its hole's model position, and of the hole circle that the render drew.
8. The build exits non-zero on any failure in gates 6 and 7.
9. A manifest lists each page with its title and tags, and a test checks that every required step has a page.
10. You rendered every page to PNG and looked at every one.

## Make the environments

Use two Python environments. CadQuery and reportlab pin different versions of their dependencies, and two environments keep each one clean.

```sh
uv venv --python 3.12 .venv-cad
uv pip install --python .venv-cad/bin/python cadquery==2.7.0 shapely contourpy numpy
uv venv --python 3.13 .venv-pdf
uv pip install --python .venv-pdf/bin/python reportlab svglib
```

Pin the exact versions in `requirements-cad.txt` and `requirements-pdf.txt` once the first sheet builds. The worked example pins cadquery 2.7.0, cadquery-ocp 7.8.1.1.post1, shapely 2.2.0, reportlab 5.1.0 and svglib 2.4.0. Add an `env.sh` that sets `CADPY` and `PDFPY`, uses the repo-local venvs by default, and prints a loud WARNING when one is missing. Put the venvs in `.gitignore`. Install `pdftoppm` (poppler) for the page review.

If the pages use system fonts, name the font files in one place and check that they exist. The worked example uses macOS fonts, so its layout step runs only on macOS.

## Worked example

In weather-station-2026, see:

- `hardware/tx-stack-r1/sources.py`: the facts table.
- `hardware/tx-stack-r1/layout/stack.py`, `route.py`, `layout_checks.py`: the layout model, the wire router and checks L1 to L13.
- `hardware/tx-stack-r1/sheets/session1/v2/r3d.py`: the hidden-line renderer.
- `hardware/tx-stack-r1/sheets/session1/v2/holecheck.py`: the hole callout check.
- `hardware/tx-stack-r1/sheets/session3/sheetlib.py`: page furniture, chips, leaders and the label check.
- `hardware/tx-stack-r1/sheets/session5/`: a complete session (`b3md.py`, `scenes5.py`, `make_session5.py`, `render_all.sh`).
- `hardware/pods-r1/sheets/`: the same method in a second unit, with `env.sh`, `setup-envs.sh`, a manifest, and `mrender.py` for triangle meshes.
- `tests/test_pods_sheets.py`: the test that builds Session P and reads its manifest.
