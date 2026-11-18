# Starter skeleton

This is the smallest layout that keeps the method's rules. The signatures come from the worked example in weather-station-2026 (`hardware/tx-stack-r1/sheets/session1/v2/r3d.py`, `holecheck.py`, `session3/sheetlib.py`, `hardware/pods-r1/sheets/`). Copy those files as a start if you can read them. Otherwise, write these pieces from the descriptions.

## File layout

```text
PROJECT/
  sources.py                  facts table: D = {key: (value, what, source, status)}, val(), tbd(), label(), --check
  layout/
    model.py                  every part, pin, pad and 3D box on the hole grid, read from sources.py
    route.py                  every wire's path: flat runs on a half-pitch grid, right-angle bends
    checks.py                 holes, nets against the schematic, 3D clashes; exits non-zero on a failure
    drawings.py               writes build/BOARD.md (the text build list) from model.py and route.py
  build/BOARD.md              generated: wire table, parts in build order, strip map, before-power checks
  sheets/
    env.sh                    sets CADPY and PDFPY; repo-local venvs by default; WARNING when missing
    setup-envs.sh             makes .venv-cad and .venv-pdf, fetches the maker STEP files
    requirements-cad.txt      pinned: cadquery, cadquery-ocp, shapely, contourpy, numpy
    requirements-pdf.txt      pinned: reportlab, svglib
    lib/
      r3d.py                  Scene and render(): hidden lines + ray-cast flat fills -> SVG + anchor JSON
      mrender.py              optional: the same output from triangle meshes (depth buffer)
      models.py               CadQuery models of boards, parts and bench tools
      handed.py               declares each frame map, so render() can refuse mirrored pictures
      holecheck.py            hole callout check
      sheetlib.py             page furniture, Grid, panel, Art, chip, label, leader, dim, LAB checks
    session1/
      boardmd.py              parses build/BOARD.md: WIRES, PARTS, STRIPS, BEFORE
      scenes.py               @scene functions; "list" prints the names; one NAME per process
      make_session.py         PAGES list, build(), manifest; exits non-zero on any issue
      render_all.sh           one scene per process, skips fresh SVGs, then checks every SVG exists
      build.sh                runs make_session.py into out/
    svg/  out/                gitignored
tests/test_sheets.py          renders, builds, reads the manifest, checks page count and tags
```

## r3d.py

```python
class Scene:
    def add(self, name, shape, colour, weight=1.0): ...          # a CadQuery shape or Workplane with a flat colour
    def text(self, part, s, origin, u, v, size, colour="#FFFFFF", font="Helvetica", anchor="middle"): ...
    def lines(self, part, segs, colour=INK, width=0.4, check=True, opacity=1.0, width_mm=None): ...
    def anchor(self, name, p, on=None): ...      # a 3D point for a label; `on` = the part it must be seen on
    def hole(self, name, p, drawn=True): ...     # an anchor that names a hole: holecheck checks callouts on it
    def placed_by(self, what, R): ...            # declare a 3x3 map that carried geometry in; det < 0 is refused

def render(scene, out, direction, up=(0, 0, 1), fit=None, scale=None, margin=6,
           light=(-0.5, 0.35, 0.8), line=0.55, outline=1.1, tones=(1.0, 0.86, 0.72), crop=None) -> float:
    """Write out.svg and out.json ({w, h, scale, anchors, holes}). Returns the scale in pt per mm."""
```

What `render()` does, in order:

1. Assert that every declared frame map has a determinant above zero.
2. Run OpenCascade hidden-line removal (`HLRBRep_Algo`) on a compound of all parts, along `direction`.
3. Turn the visible sharp, smooth and outline edges into 2D polylines.
4. Snap the line ends together (a small tolerance), node them, and polygonize them into closed regions with shapely.
5. For each region, cast a ray through an interior point (`IntCurvesFace_ShapeIntersector`). The nearest face owns the region. For a large region, vote over several interior points.
6. Pick one of three tones from the face normal and the light. Group the fills by colour.
7. Draw decals only where their face is the visible one.
8. Stop if any anchor with `on=` is hidden behind another part.
9. Write fills, decals, thin edges, silhouettes and a heavy outline per part. Write the anchors in SVG points.

## holecheck.py

```python
TOL = 0.15      # mm: a callout must be this close to its hole
NEAR = 2.0      # mm: a free marker this close to a hole, but not on it, is an offset callout

def art(a): ...                     # record a placed picture on this page
def lookup(a, name, xy): ...        # record that a page point came from picture a's anchor `name`
def mark(x, y, kind): ...           # record a ring or leader dot
def check(page) -> list[str]: ...   # every mark on a hole anchor: within TOL of the anchor and of a drawn circle
def reset(): ...
```

## sheetlib.py

```python
W, H, M = 612, 792, 30
LEADER_INK = False                     # True: every leader black on a white halo

class Labels:                          # LAB: records chips, leaders, panels, texts, arts per page
    def reset(self, pg): ...
    def block(self, x0, y0, x1, y1, what): ...
    def check(self) -> list[str]: ... # chip/chip, chip/block, chip outside its panel, chip in the caption,
                                       # text or art under a badge, leader across another chip

def page(c, step_no, title, sub, pg, slogan): ...               # header band, stripe, footer; calls LAB.reset
class Grid:
    def __init__(self, cols, rows, top=H - 112, bottom=44, gap=10, heights=None): ...
    def cell(self, col, row, span=1) -> tuple: ...
def panel(c, cell, n, caption, warn=False) -> tuple: ...        # returns the free area above the caption
class Art:                                                      # an SVG from svg/ placed in a box
    def __init__(self, c, name, x, y, w, h, align="c", valign="c", clip_circle=False, frame=False): ...
    def A(self, anchor) -> tuple: ...                          # anchor -> page point (records it for holecheck)
    def mm(self) -> float: ...                                 # page points per model mm
def chip(c, x, y, s, size=9, font="ALT", color=INK, anchor="l", pad=2.6, fill=WHITE, border=None) -> tuple: ...
def leader(c, r, px, py, color=INK, dot=True, w=1.0): ...     # from the chip edge to the point
def label(c, x, y, s, px, py, size=9, ...): ...                # chip + leader
def dim(c, x1, y1, x2, y2, s, size=12, color=NEON, ...): ...   # dimension line with a chip
```

## scenes.py

```python
SCENES = {}

def scene(fn):
    SCENES[fn.__name__] = fn
    return fn

def R(name, s, direction, up=(0, 0, 1), fit=(300, 220), **kw):
    handed.board_frame(s)                       # declare the frame, every time
    r3d.render(s, OUT / name, direction, up=up, fit=fit, **kw)

@scene
def p_sensor():                                 # "parts as supplied": one breakout alone
    s = r3d.Scene()
    for solid, colour in sensor_parts():        # the maker STEP, split into solids, coloured by size or height
        s.add("sensor", solid, colour)
    s.anchor("qt_socket", (12.0, 8.0, 3.2), on="sensor")
    R("p_sensor", s, (-0.35, -1, 0.75), fit=(110, 100), line=0.35)

if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if len(names) != 1:
        sys.exit("render ONE scene per process: scenes.py NAME   (scenes.py list)")
    SCENES[names[0]]()
```

## make_session.py

```python
PAGES = []                                      # (step, title, tags, fn)

def add_page(step, title, tags, fn):
    PAGES.append((step, title, tags, fn))

def build(path):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    manifest, bad = [], 0
    for pg, (step, title, tags, fn) in enumerate(PAGES, 1):
        fn(cv, pg)
        iss, hi = LAB.check(), HC.check(pg)
        HC.reset()
        bad += len(iss) + len(hi)
        manifest.append({"page": pg, "step": step, "title": title, "tags": tags,
                         "label_issues": len(iss), "hole_issues": len(hi)})
        cv.showPage()
    cv.save()
    json.dump({"page_count": len(PAGES), "pages": manifest}, open(OUT / "manifest.json", "w"), indent=1)
    if bad:
        sys.exit(f"BUILD FAILED: {bad} label or hole issues")
```

Build one PDF per step too if the reader wants loose pages. Use the same page functions.

## render_all.sh

```sh
#!/bin/sh
# One scene per process (a multi-scene run can segfault and still exit 0). Re-render a scene when its SVG is
# missing or older than a source. FORCE=1 re-renders all. JOBS=n runs n at once. Then check every SVG exists.
cd "$(dirname "$0")"
. ../env.sh
mkdir -p svg
NAMES=${*:-$("$CADPY" -B scenes.py list)}
[ -n "$NAMES" ] || { echo "scenes.py list failed"; exit 1; }
SRC="scenes.py ../lib/models.py ../../layout/model.py ../../sources.py"
TODO=""
for n in $NAMES; do
  stale=0
  [ -s svg/$n.svg ] || stale=1
  [ "${FORCE:-0}" = 1 ] && stale=1
  [ $stale = 0 ] && for f in $SRC; do [ "$f" -nt svg/$n.svg ] && stale=1; done
  [ $stale = 1 ] && { rm -f svg/$n.svg svg/$n.json; TODO="$TODO $n"; }
done
[ -n "$TODO" ] && echo $TODO | tr ' ' '\n' | xargs -P "${JOBS:-6}" -I{} sh -c \
  '"$0" -B scenes.py {} > svg/{}.log 2>&1 || echo "FAILED {}"' "$CADPY"
miss=0
for n in $NAMES; do [ -s svg/$n.svg ] || { echo "MISSING svg/$n.svg"; miss=1; }; done
exit $miss
```

## Page review

```sh
mkdir -p out/review
pdftoppm -r 110 -png out/session1.pdf out/review/p
```

Open every PNG and read it as the builder will. Is each part named exactly? Does each leader land on the thing that its chip names? Does the picture match the part on the bench?
