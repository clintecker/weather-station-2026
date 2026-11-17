"""Session 3 (build B2 PORTS B + METERS) illustrations, same pipeline as Sessions 1 v2 and 2 (r3d: hidden lines +
ray-cast flat colour).

Geometry comes from the repo, read-only: layout/stack.py PLACE["B2"] (every placement, pin and box),
layout/route.py WIRES + ROUTES (every wire's and jumper's routed ends and path), schematic/model.py (values, pin
names: which diode lead is the cathode), sources.py (part sizes) and the BOB-14021 board STEP in render/models/BOB
(built from SparkFun's Eagle file by render/fetch_models.py). build/B2.md (b2md.py) gives the numbering, colours and
the step grouping, and is checked against route.py on import. The Amphenol 87180 jack, the 1x6 header and the small
two-lead parts are drawn from stack.py's boxes and sources.py's sizes (MODELS.md: no maker model for the jack).
Card frame = stack's card frame (X from the left edge along columns 1-30, Y from the FRONT edge, the A side), with
the card's top face at z = 1.6 here (stack's z = 0).

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  cadx/bin/python -B scenes3.py NAME          (scenes3.py list: every scene; scenes3.py groups: the steps)
"""
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "session1" / "v2"))
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
sys.path.insert(0, str(REPO / "layout"))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import stack as st                      # noqa: E402
import route as rt                      # noqa: E402

S = st.S
OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.SB_T                              # card top face z
HDR = st.HDR
CARD = "B2"
PCB_STEP = 1.51                         # the BOB-14021 STEP board's thickness

PL = {pl["ref"]: dict(pl, pins=dict(pl["pins"]), pads=dict(pl["pads"])) for pl in st.PLACE[CARD]}
PART = {p["ref"]: p for p in st.model.PARTS if p.get("card") == CARD}

# insulation colour scheme of build/B2.md's heading (drawings.insul): 3.3 V red, ground black, SCL yellow, SDA blue,
# every other signal green
INS = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "green": "#2E9A48"}


def insul(note):
    n = note.lower()
    if "ground" in n:
        return "black"
    if "3.3 v" in n:
        return "red"
    if "scl" in n:
        return "yellow"
    if "sda" in n:
        return "blue"
    return "green"


MARK = set()          # the leader anchors a scene asks for (each checked visible on its part by r3d.render)


def mark(s, name, p, on):
    if name in MARK:
        s.anchor(name, p, on=on)


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    import handed
    handed.card_frame(s, CARD)                   # every picture here is drawn in B2's card frame
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


# ------------------------------------------------------------------ wires and jumpers: route.WIRES (routed ends) + B2.md
import b2md as B                        # noqa: E402  (build/B2.md: colours, numbering, the bench's own tables)

B2_WIRES = []
for i, (kind, a, b, side, note) in enumerate(rt.WIRES):     # the routed ends (a rail end may move along its rail)
    r = rt.ROUTES[i]
    if not r or r.get("card") != CARD:
        continue
    B2_WIRES.append(dict(i=i, kind=kind, a=a.split(":")[1], b=b.split(":")[1], side=side, note=note,
                         cut=rt.cut_length(i), pts=r["pts"], length=r["length"]))
UNDER = [w for w in B2_WIRES if w["kind"] == "wire"]          # B2.md "Underside wires", in order
JUMPERS = [w for w in B2_WIRES if w["kind"] == "jumper"]      # B2.md "Bare jumpers", in order
assert not [w for w in B2_WIRES if w["kind"] not in ("wire", "jumper")], "B2 has no pad leads now"
for mine, md in ((UNDER, B.WIRES), (JUMPERS, B.JUMPERS)):
    assert [(w["a"], w["b"]) for w in mine] == [(m["a"], m["b"]) for m in md], "route.WIRES and B2.md disagree"
    for w, m in zip(mine, md):
        assert m["length"].startswith(f"{w['cut']} mm"), (w, m)
        w["n"] = m["n"]
        w["colour"] = m.get("colour")


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            a, b = np.array(out[-2]), np.array(out[-1])
            d1, d2 = b - a, np.array(p) - b
            if np.linalg.norm(np.cross(d1, d2)) < 1e-6 and d1 @ d2 > 0:
                out[-1] = p
                continue
        if np.linalg.norm(np.array(p) - np.array(out[-1])) > 1e-6:
            out.append(p)
    return out


def tube(pts, r=0.72):
    pts = simplify([tuple(map(float, p)) for p in pts])
    solids = []
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = np.array(a), np.array(b)
        L = np.linalg.norm(b - a)
        solids.append(cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*((b - a) / L))))
    for p in pts[1:-1]:
        solids.append(cq.Solid.makeSphere(r, cq.Vector(*p), angleDegrees1=-90, angleDegrees2=90))
    s = solids[0]
    for x in solids[1:]:
        s = s.fuse(x)
    return s.clean()


def wire_solid(w):
    """Underside wire: its route at the underside plus the stripped ends up through the two holes."""
    p = simplify([(x, y, -0.75) for x, y, _ in w["pts"]])
    pa, pb = p[0], p[-1]

    def pull(q, r, d=0.9):
        v = np.array(r[:2]) - np.array(q[:2])
        L = np.linalg.norm(v)
        return (q[0] + v[0] / L * d, q[1] + v[1] / L * d, q[2])
    p2 = [pull(p[0], p[1])] + p[1:-1] + [pull(p[-1], p[-2])]
    body = tube(p2, 0.725)
    ends = []
    for h, q in ((pa, p2[0]), (pb, p2[-1])):
        v = np.array(q) - np.array(h)
        ends.append(cq.Solid.makeCylinder(0.26, float(np.linalg.norm(v)), cq.Vector(*h), cq.Vector(*(v / np.linalg.norm(v)))))
        ends.append(cq.Solid.makeCylinder(0.26, 3.0, cq.Vector(h[0], h[1], -0.75), cq.Vector(0, 0, 1)))
    return body, cq.Compound.makeCompound(ends)


# ------------------------------------------------------------------ the card
def card(s, decals=True, under_pads=True):
    b, p = M.solderful(snapped=True, decals=s if decals else None, part="card")
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    if under_pads:
        _, pb = M.solderful(snapped=True, labels=False)
        pb = pb.mirror("XY", (0, 0, T / 2))
        s.add("padsU", pb, M.GOLD, 0.0)


def hole_xy(h):
    """'e10' -> card XY; 'F+1' / 'F-2' rails (stack's own hole positions)."""
    return st.hole_xy(h)


def hole_anchors(s, z, drawn=True):
    for c in "abcdefghij":
        for n in range(1, 31):
            s.hole(f"{c.upper()}{n}", (*hole_xy(f"{c}{n}"), z), drawn)
    for n in range(1, 31):
        s.hole(f"F+{n}", (*hole_xy(f"F+{n}"), z), drawn)
        s.hole(f"F-{n}", (*hole_xy(f"F-{n}"), z), drawn)
    for k, (x, y) in (("fl", (0, 0)), ("fr", (M.SB_W, 0)), ("bl", (0, M.SNAP_Y)), ("br", (M.SB_W, M.SNAP_Y))):
        s.anchor(k, (x, y, z))


# ------------------------------------------------------------------ parts: two-lead parts from stack's pins + boxes
def ycyl(r, y0, y1, x, z):
    return cq.Solid.makeCylinder(r, y1 - y0, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))


def zcyl(r, z0, z1, x, y):
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))


DIGIT = ["#1C1C1C", "#7A4A23", "#D7262E", "#F07C1A", "#F2D21A", "#2E9A48", "#2D6FD0", "#8E44AD", "#8C8C8C", "#F4F4F4"]
GOLD_BAND = "#C9A43A"


def band_colours(value, five):
    """Resistor colour code from model.py's value: '10k', '1k', '100'. five: 1 % (3 digits + multiplier + brown)."""
    v = float(value.lower().replace("k", "")) * (1000 if "k" in value.lower() else 1)
    nd = 3 if five else 2
    e = int(math.floor(math.log10(v))) - (nd - 1)
    digits = str(int(round(v / 10 ** e)))
    cols = [DIGIT[int(d)] for d in digits] + [DIGIT[e] if e >= 0 else GOLD_BAND]
    return cols + ([DIGIT[1]] if five else [GOLD_BAND])


def res_kind(ref):
    p = PART[ref]["part"]
    five = p.startswith("MFR-25")                     # Yageo MFR-25: metal film, 1 %, five bands, blue body
    return five, ("#8FB2DA" if five else "#D8C49A")


def _res_length(ref):
    """The body length stack gives the lying resistor (one box along an axis, or slices along a slant)."""
    bodies = [b for b in PL[ref]["boxes"] if "resistor body" in b.what]
    if len(bodies) == 1:
        b = bodies[0]
        return max(b.x1 - b.x0, b.y1 - b.y0)
    c0 = np.array([(bodies[0].x0 + bodies[0].x1) / 2, (bodies[0].y0 + bodies[0].y1) / 2])
    cn = np.array([(bodies[-1].x0 + bodies[-1].x1) / 2, (bodies[-1].y0 + bodies[-1].y1) / 2])
    return float(np.linalg.norm(cn - c0)) * len(bodies) / (len(bodies) - 1)


def add_resistor(s, ref):
    """Lying resistor along its two holes (along a row, a column or on a slant): leads up from the holes and bent
    in at the body ends; colour bands start at lead 1's end."""
    pl = PL[ref]
    p1, p2 = np.array(pl["pins"]["1"], float), np.array(pl["pins"]["2"], float)
    u = (p2 - p1) / np.linalg.norm(p2 - p1)
    body = next(b for b in pl["boxes"] if "resistor body" in b.what)
    r = (body.z1 - body.z0) / 2
    zc = T + body.z0 + r
    L = _res_length(ref)
    a = (p1 + p2) / 2 - u * L / 2
    b_ = a + u * L
    cyl = cq.Solid.makeCylinder(r, L, cq.Vector(a[0], a[1], zc), cq.Vector(u[0], u[1], 0))
    cyl = cq.Workplane().add(cyl).edges().fillet(r * 0.45).val()
    five, col = res_kind(ref)
    s.add(f"{ref}_body", cyl, col, 0.8)
    cols = band_colours(PART[ref]["value"], five)
    pos = [0.16, 0.27, 0.38, 0.49, 0.80] if five else [0.18, 0.31, 0.44, 0.78]
    for k, (c, f) in enumerate(zip(cols, pos)):
        q = a + u * (f * L - 0.28)
        s.add(f"{ref}_b{k}", cq.Solid.makeCylinder(r + 0.03, 0.56, cq.Vector(q[0], q[1], zc), cq.Vector(u[0], u[1], 0)),
              c, 0.3)
    e1, e2 = a + u * 0.3, b_ - u * 0.3
    lead = tube([(*p1, T - 1.6), (*p1, zc), (*e1, zc)], 0.3).fuse(tube([(*p2, T - 1.6), (*p2, zc), (*e2, zc)], 0.3))
    s.add(f"{ref}_leads", lead, M.TIN, 0.4)
    q = a + u * 0.65 * L                                   # between the bands: plain body
    mark(s, f"@{ref}", (q[0], q[1], zc + r), f"{ref}_body")


DO35 = S.val("do35")                                   # (4.56 long, 2.0 diameter)
GLASS = "#E58A3A"


def add_diode(s, ref):
    """Standing DO-35: body on lead 1's hole, the other lead looped over. The band sits at the cathode end."""
    pl = PL[ref]
    (x1, y1), (x2, y2) = pl["pins"]["1"], pl["pins"]["2"]
    bodyb = next(b for b in pl["boxes"] if "diode body" in b.what)
    loop = next(b for b in pl["boxes"] if "lead loop" in b.what)
    dl, dd = DO35
    z0, z1 = T + bodyb.z0, T + bodyb.z1
    zl = T + (loop.z0 + loop.z1) / 2
    s.add(f"{ref}_body", cq.Workplane().add(zcyl(dd / 2, z0, z1, x1, y1)).edges().fillet(0.35).val(), GLASS, 0.8)
    bz = band_z(ref)
    s.add(f"{ref}_band", zcyl(dd / 2 + 0.03, bz[0], bz[1], x1, y1), "#1C1C1C", 0.4)
    lead = tube([(x1, y1, T - 1.6), (x1, y1, z0 + 0.2)], 0.25)
    lead = lead.fuse(tube([(x1, y1, z1 - 0.2), (x1, y1, zl), (x2, y2, zl), (x2, y2, T - 1.6)], 0.25))
    s.add(f"{ref}_leads", lead, M.TIN, 0.4)
    dx = 0.6 if x1 >= x2 else -0.6                    # on the body's flat top, away from the loop's lead
    mark(s, f"@{ref}", (x1 + dx, y1, z1), (f"{ref}_body", f"{ref}_band"))
    mark(s, f"{ref}_bandp", (x1, y1 - dd / 2 - 0.03, (bz[0] + bz[1]) / 2), f"{ref}_band")
    mark(s, f"{ref}_bandq", (x1, y1 + dd / 2 + 0.03, (bz[0] + bz[1]) / 2), f"{ref}_band")


def band_z(ref):
    pl = PL[ref]
    bodyb = next(b for b in pl["boxes"] if "diode body" in b.what)
    z0, z1 = T + bodyb.z0, T + bodyb.z1
    pins = {p[0]: p[1] for p in PART[ref]["pins"]}
    band_low = pins["1"] == "cathode"                   # lead 1 under the body: its end is the body's bottom
    return (z0 + 0.35, z0 + 1.15) if band_low else (z1 - 1.15, z1 - 0.35)


def _ray_hits(p, d, boxes, t0=0.3, t1=40.0):
    """Does the ray p + t d (t0 < t < t1, card frame, stack z) pass through any of the boxes?"""
    for bx in boxes:
        lo, hi = t0, t1
        for k, (a0, a1) in enumerate(((bx.x0, bx.x1), (bx.y0, bx.y1), (bx.z0, bx.z1))):
            if abs(d[k]) < 1e-12:
                if not a0 <= p[k] <= a1:
                    lo, hi = 1, 0
                continue
            ta, tb = sorted(((a0 - p[k]) / d[k], (a1 - p[k]) / d[k]))
            lo, hi = max(lo, ta), min(hi, tb)
        if lo < hi:
            return True
    return False


def band_side(ref, present):
    """Which side of a standing diode its band is seen from in the iso close-up: 'p' (from the front, ISO_F) unless
    a part already fitted stands in the way (a ray from the band toward the viewer through its body box), then 'q'
    (from behind, ISO_B). Thin lead loops do not count (the render checks the real view anyway)."""
    x1, y1 = PL[ref]["pins"]["1"]
    dd = DO35[1]
    zb = (band_z(ref)[0] + band_z(ref)[1]) / 2 - T
    boxes = [bx for o in present if o != ref for bx in PL[o]["boxes"]
             if not bx.keepout and "lead" not in bx.what]
    for side, d, sg in (("p", ISO_F, -1), ("q", ISO_B, 1)):
        d = np.array(d, float) / np.linalg.norm(d)
        if not _ray_hits((x1, y1 + sg * (dd / 2 + 0.03), zb), d, boxes):
            return side
    raise SystemExit(f"{ref}: band hidden from the front and from behind")


ISO_F = (-0.3, -1, 0.75)          # from the front-left (row A side)
ISO_B = (-0.3, 1, 0.75)           # from behind-left (row J side)


CAP_COL = "#D9A441"


def add_cap(s, ref):
    pl = PL[ref]
    (x1, y1), (x2, y2) = pl["pins"]["1"], pl["pins"]["2"]
    assert abs(y1 - y2) < 1e-6                         # every B2 disc stands on two holes of one row
    box = next(b for b in pl["boxes"] if "disc" in b.what)
    d = box.x1 - box.x0
    t = box.y1 - box.y0
    zc = T + box.z1 - d / 2
    xm = (x1 + x2) / 2
    disc = ycyl(d / 2, y1 - t / 2, y1 + t / 2, xm, zc)
    disc = cq.Workplane().add(disc).edges().fillet(t * 0.42).val()
    s.add(f"{ref}_body", disc, CAP_COL, 0.8)
    lead = tube([(x1, y1, T - 1.6), (x1, y1, zc - 0.5)], 0.25).fuse(tube([(x2, y2, T - 1.6), (x2, y2, zc - 0.5)], 0.25))
    s.add(f"{ref}_leads", lead, M.TIN, 0.4)
    mark(s, f"@{ref}", (xm, y1, T + box.z1), f"{ref}_body")
    mark(s, f"{ref}_face", (xm, y1 - t / 2, zc), f"{ref}_body")


PTC_COL = "#E8A317"


def add_ptc(s, ref):
    pl = PL[ref]
    (x1, y1), (x2, y2) = pl["pins"]["1"], pl["pins"]["2"]
    assert abs(x1 - x2) < 1e-6                         # F4 stands along a column (rail to row A)
    box = next(b for b in pl["boxes"] if "MF-R010" in b.what)
    b = cq.Workplane().add(M.box(box.x0, box.y0, T + box.z0, box.x1, box.y1, T + box.z1).val()).edges("|Z").fillet(1.0)
    b = b.edges(">Z").fillet(0.8).val()
    s.add(f"{ref}_body", b, PTC_COL, 0.8)
    ym = (y1 + y2) / 2
    sg = 1 if y2 > y1 else -1
    zb = T + box.z0 + 0.3
    lead = tube([(x1, ym - sg * 2.54, zb + 1.0), (x1, ym - sg * 2.54, T + 0.6), (x1, y1, T + 0.6), (x1, y1, T - 1.6)], 0.3)
    lead = lead.fuse(tube([(x2, ym + sg * 2.54, zb + 1.0), (x2, ym + sg * 2.54, T + 0.6), (x2, y2, T + 0.6), (x2, y2, T - 1.6)], 0.3))
    s.add(f"{ref}_leads", lead, M.TIN, 0.4)
    s.text(f"{ref}_body", "R010", (box.x0 - 0.01, ym, T + box.z0 + 6.5), (0, -1, 0), (0, 0, 1), 1.6, colour="#1C1C1C")
    mark(s, f"@{ref}", (x1, ym, T + box.z1), f"{ref}_body")
    mark(s, f"{ref}_face", (box.x0, ym, T + box.z0 + 9.5), f"{ref}_body")


def add_header(s, ref="XH2"):
    """Generic right-angle 1x30 header in j1-j30 (every pin fitted), mating pins toward the back (+Y)."""
    pins = PL[ref]["pins"]
    assert len(pins) == 30, "B2's bus header must be a full 1x30"
    x1, y = pins["1"]
    x30 = pins["30"][0]
    off, ins = S.val("ra_offset"), S.val("ra_insulator")
    tail = S.val("ra_tail")
    pz = T + st.PIN_Z
    s.add(f"{ref}_ins", M.box(x1 - 1.27, y + off, T, x30 + 1.27, y + off + ins, T + 2 * st.PIN_Z), "#1E1E1E")
    ps = []
    for n in range(1, 31):
        x = pins[str(n)][0]
        ps.append(M.box(x - 0.32, y - 0.32, T - tail, x + 0.32, y + 0.32, pz + 0.32).val())
        ps.append(M.box(x - 0.32, y - 0.32, pz - 0.32, x + 0.32, y + st.RA_TIP, pz + 0.32).val())
    s.add(f"{ref}_pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.4)
    for n in (1, 30):
        mark(s, f"{ref}_p{n}", (pins[str(n)][0], y + st.RA_TIP - 0.5, pz + 0.32), f"{ref}_pins")


# ------------------------------------------------------------------ RJ11 breakouts: BOB-14021 STEP + 87180 jack + 1x6
STEPS = REPO / "render" / "models"
_bob = []
BOB_RED = "#B5121B"
JACK = "#33363B"
PIN = "#D8B24A"
HDR_BLACK = "#1E1E1E"


def bob_step():
    if not _bob:
        shp = cq.importers.importStep(str(STEPS / "BOB" / "bob14021_board.step"))
        sols = [x for v in shp.vals() for x in v.Solids()]
        board = max(sols, key=lambda so: so.Volume())
        cu = [so for so in sols if so is not board]                                      # pads and tracks, both faces
        _bob.extend([board, cu])
    return _bob


# BOB-14021 as SparkFun sells it: the bare board (SparkFun RJ11-Breakout.brd, Edge.Cuts layer 20) with a 5.84 mm
# snap-off tab on its maker +x side (x 15.748-21.59, beyond a V-score at x 15.24): "V-score for the end user if they
# want to remove". The jack (Amphenol 87180-066LF) and the 1x6 male header are separate parts. The jack's six pins
# and two plastic pegs go in the board's holes (the STEP's holes: pins at y 6.35 / 8.89, pegs r 1.63 at y 15.24);
# the header goes in the six pads at y 1.27 (stack.bob: pin i at maker x 13.97 - (i - 1) 2.54).
BOB_TAB = (15.24, 21.59)
JACK_PINS = [(5.71, 6.35), (8.25, 6.35), (10.79, 6.35), (4.45, 8.89), (6.99, 8.89), (9.52, 8.89)]
JACK_PEGS = [(2.54, 15.24), (12.7, 15.24)]
HY = S.val("bob_hdr_y")
HPINS = [(13.97 - (i - 1) * M.P, HY) for i in range(1, 7)]
H_PL = HDR                                   # header plastic, 2.5 (stack: the board's height above the card)
H_SHORT, H_LONG = 3.0, 6.0                   # generic 1x6 male header: pin ends above / below the plastic [typical]


def bob_parts(tab=False, jack=True, jlift=0.0, header=True, hdrop=0.0, trimmed=False, soldered=True, flush=None):
    """One BOB-14021 build in its own maker frame (board bottom at z 0): [(name, shape, colour, weight)] and
    {anchor: (point, on)}. jlift / hdrop: the jack lifted above / the header dropped below its seat (exploded kit).
    trimmed: the header's long ends cut 1 mm below the card (fitted); flush: jack pins cut flush under the board
    (default: when soldered and not exploded)."""
    if flush is None:
        flush = soldered and not jlift
    board, cu = bob_step()
    parts = [("pcb", board, BOB_RED, 1.0), ("cu", cq.Compound.makeCompound(cu), M.GOLD, 0.3)]
    anc = {}
    bd = S.val("bob_d")
    if tab:
        parts.append(("tab", M.box(BOB_TAB[0] + 0.51, 0, 0, BOB_TAB[1], bd, PCB_STEP).val(), BOB_RED, 1.0))
        parts.append(("score", M.box(BOB_TAB[0], 0, 0.45, BOB_TAB[0] + 0.51, bd, PCB_STEP - 0.45).val(), BOB_RED, 0.3))
        anc["tab"] = (((BOB_TAB[0] + BOB_TAB[1]) / 2 + 0.6, 12.0, PCB_STEP), "tab")
        anc["score"] = ((BOB_TAB[0] + 0.25, 0.0, PCB_STEP / 2), "score")
        anc["score_top"] = ((BOB_TAB[0] + 0.25, 6.0, PCB_STEP - 0.45), "score")
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    mouth = S.val("bob_peg_y") + 7.88                    # stack.bob: the jack's front face (mouth), maker +y
    pw, ph = S.val("plug_6p")[0], S.val("plug_6p")[1]
    if jack:
        z0 = PCB_STEP + jlift
        j = M.box(7.62 - jw / 2, mouth - jd, z0, 7.62 + jw / 2, mouth, z0 + jh)
        j = j.cut(M.box(7.62 - pw / 2, mouth - 9.0, z0 + 1.0, 7.62 + pw / 2, mouth + 1, z0 + 1.0 + ph))
        parts.append(("jack", j.val(), JACK, 1.0))
        tail = (0.6 if flush else 3.0)
        pins = [zcyl(0.3, z0 - PCB_STEP - tail, z0, x, y) for x, y in JACK_PINS]
        pegs = [zcyl(1.4, z0 - PCB_STEP - 1.0, z0, x, y) for x, y in JACK_PEGS]
        parts.append(("jpins", cq.Compound.makeCompound(pins), PIN, 0.4))
        parts.append(("jpegs", cq.Compound.makeCompound(pegs), JACK, 0.6))
        if soldered and not jlift:
            fil = [cq.Solid.makeCone(0.95, 0.32, 0.55, cq.Vector(x, y, 0.0), cq.Vector(0, 0, -1)) for x, y in JACK_PINS]
            parts.append(("jfil", cq.Compound.makeCompound(fil), M.TIN, 0.4))
            anc["jfil"] = ((JACK_PINS[1][0] + 0.62, JACK_PINS[1][1], -0.2), ("jfil", "jpins"))
        anc["jack"] = ((7.62, mouth - jd / 2, z0 + jh), "jack")
        anc["mouth"] = ((7.62, mouth, z0 + 1.0 + ph + 1.5), "jack")
        anc["jpin"] = ((JACK_PINS[1][0], JACK_PINS[1][1], z0 - PCB_STEP - tail), "jpins")
        anc["peg"] = ((JACK_PEGS[0][0], JACK_PEGS[0][1], z0 - PCB_STEP - 1.0), "jpegs")
    if header:
        zt = -hdrop                                       # header plastic top (against the board's underside)
        plast = M.box(0, HY - 1.27, zt - H_PL, S.val("bob_w"), HY + 1.27, zt).val()
        bot = (-H_PL - M.SB_T - 1.0) if trimmed else (zt - H_PL - H_LONG)
        top = zt + H_SHORT
        hp = [M.box(x - 0.32, y - 0.32, bot, x + 0.32, y + 0.32, top).val() for x, y in HPINS]
        parts.append(("hdr", plast, HDR_BLACK, 0.6))
        parts.append(("hpins", cq.Compound.makeCompound(hp), PIN, 0.4))
        if soldered and not hdrop:
            fil = [cq.Solid.makeCone(0.95, 0.38, 0.6, cq.Vector(x, y, PCB_STEP)) for x, y in HPINS]
            parts.append(("hfil", cq.Compound.makeCompound(fil), M.TIN, 0.4))
            anc["hfil"] = ((HPINS[0][0], HPINS[0][1] - 0.62, PCB_STEP + 0.2), ("hfil", "hpins"))
        anc["hdr"] = ((7.62, HY - 1.27, zt - H_PL / 2), "hdr")
        anc["hdr_bot"] = ((HPINS[2][0] - 1.27, HY + 0.8, zt - H_PL), "hdr")
        anc["hpin_lo"] = ((HPINS[0][0], HPINS[0][1], bot), "hpins")
    for i, (x, y) in enumerate(HPINS, 1):
        anc[f"pad{i}"] = ((x, y, PCB_STEP), None)
    anc["board"] = ((7.62 + 3.0, 3.6, PCB_STEP), ("pcb", "cu"))
    return parts, anc


def bob_alone(s, **kw):
    parts, anc = bob_parts(**kw)
    for name, shp, col, w in parts:
        s.add(name, shp, col, w)
    for k, (p, on) in anc.items():
        if on is None:
            s.anchor(k, p)
        else:
            mark(s, k, p, on)


def add_bob(s, ref):
    """A BOB-14021 build from stack's placement (stack.bob: rot 180, header in row a, mouth to the front edge),
    soldered on its 1x6 header, jack pins trimmed flush."""
    pl = PL[ref]
    kind, rot, x0, y0 = pl["step"][0]
    pcb = next(b for b in pl["boxes"] if "BOB-14021 PCB" in b.what)
    zb = T + pcb.z0
    parts, anc = bob_parts(trimmed=True)

    def tfm(sh):
        return sh.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), rot).translate(cq.Vector(x0, y0, zb))
    for name, shp, col, w in parts:
        s.add(f"{ref}_{name}", tfm(shp), col, w)
    for k, (p, on) in anc.items():
        q = (*st.tf(rot, x0, y0, p[0], p[1]), p[2] + zb)
        if on is None:
            s.anchor(f"{ref}:{k}", q)
        else:
            mark(s, f"{ref}_{k}", q, tuple(f"{ref}_{o}" for o in ((on,) if isinstance(on, str) else on)))
    # the six header pins really are stack's six pins (row a, columns col..col+5)
    for i, (x, y) in enumerate(HPINS, 1):
        q = st.tf(rot, x0, y0, x, y)
        assert np.allclose(q, pl["pins"][str(i)], atol=1e-6), (ref, i, q, pl["pins"][str(i)])


# ------------------------------------------------------------------ jumpers
TIN = M.TIN


def jumper_solid(w):
    (x1, y1, _), (x2, y2, _) = w["pts"][0], w["pts"][-1]
    h = T + 1.0
    return tube([(x1, y1, T - 1.6), (x1, y1, h), (x2, y2, h), (x2, y2, T - 1.6)], 0.3)


def add_jumpers(s):
    for w in JUMPERS:
        k = w["n"]
        s.add(f"JMP{k}", jumper_solid(w), TIN, 0.6)
        (x1, y1, _), (x2, y2, _) = w["pts"][0], w["pts"][-1]
        mark(s, f"JMP{k}m", ((x1 + x2) / 2, (y1 + y2) / 2, T + 1.3), f"JMP{k}")


# ------------------------------------------------------------------ the build order (B2.md "Parts, lowest first")
REFS = list(B.PARTS)
assert set(REFS) == set(PL), (set(REFS) ^ set(PL))
FP = {r: PL[r]["fp"] for r in REFS}
GROUP = {
    "XH2": [r for r in REFS if FP[r] == "HDR" or r.startswith("XH")],
    "RPULL": [r for r in REFS if FP[r] == "RLY" and "pull-up" in B.PARTS[r]["head"]],
    "CAPS": [r for r in REFS if FP[r] == "CAP"],
    "S4D": [r for r in REFS if FP[r] == "DSTAND" and PART[r]["block"] == "ports"],
    "ZEN": [r for r in REFS if FP[r] == "DSTAND" and PART[r]["block"] != "ports"],
    "F4": [r for r in REFS if FP[r] == "PTC"],
    "JACKS": [r for r in REFS if FP[r] == "BOB"],
}
GROUP["RSER"] = [r for r in REFS if FP[r] == "RLY" and r not in GROUP["RPULL"]]
assert sorted(sum(GROUP.values(), [])) == sorted(REFS), "every B2 part in one step"
STAGES = ["J"] + sorted(GROUP, key=lambda g: min(REFS.index(r) for r in GROUP[g]))   # B2.md's order
ADD = {"RLY": add_resistor, "DSTAND": add_diode, "CAP": add_cap, "PTC": add_ptc, "BOB": add_bob}


def fitted(upto):
    k = STAGES.index(upto)
    return [r for g in STAGES[1:k + 1] for r in GROUP[g]]


def top_scene(upto, under=True, decals=True, holes=True):
    """The card with every stage up to and including `upto` fitted."""
    s = r3d.Scene()
    card(s, decals=decals)
    if holes:
        hole_anchors(s, T)
    if under:
        for w in UNDER:
            body, ends = wire_solid(w)
            s.add(f"w{w['n']}", body, INS[w["colour"]], 0.5)
    add_jumpers(s)
    for ref in fitted(upto):
        if ref in GROUP["XH2"]:
            add_header(s, ref)
        else:
            ADD[FP[ref]](s, ref)
    for ref in fitted(upto) if holes else []:         # a standing disc hides both its holes from straight above
        if FP[ref] == "CAP":
            for hx, hy in PL[ref]["pins"].values():
                nm = next(n for n, v in s.anchors.items() if n in s.holes and abs(v[0] - hx) < 1e-6
                          and abs(v[1] - hy) < 1e-6)
                s.holes[nm] = False
    if holes and "JACKS" in STAGES[:STAGES.index(upto) + 1]:
        for ref in GROUP["JACKS"]:                    # the breakouts cover their header holes and the rails under them
            pcb = next(b for b in PL[ref]["boxes"] if "BOB-14021 PCB" in b.what)
            for n, v in s.anchors.items():
                if n in s.holes and pcb.x0 < v[0] < pcb.x1 and pcb.y0 < v[1] < pcb.y1:
                    s.holes[n] = False
    return s


def top_render(name, s, fit=(330, 190), **kw):
    R(name, s, (0, 0, 1), up=(0, 1, 0), fit=fit, line=0.4, outline=1.2, **kw)


def pin_box(refs, pad=3.0):
    """Centre and half sizes of the holes of refs (card XY), padded."""
    pts = np.array([p for r in refs for p in PL[r]["pins"].values()])
    lo, hi = pts.min(0), pts.max(0)
    return (lo + hi) / 2, (hi - lo) / 2 + pad


# ------------------------------------------------------------------ cover renders: every part as supplied
def _moved(s, sub, dx, dy, dz=0.0):
    for name, shp, col, w in sub.parts:
        s.add(name, cq.Shape.cast(shp).translate((dx, dy, dz)), col, w)


@scene
def p_card():
    s = r3d.Scene()
    card(s, under_pads=False)
    R("p_card", s, (-0.3, -0.9, 1.2), fit=(150, 110), line=0.3)


@scene
def p_header():
    s = r3d.Scene()
    off, ins = S.val("ra_offset"), S.val("ra_insulator")
    tail = S.val("ra_tail")
    ps = []
    for n in range(30):
        x = n * M.P
        ps.append(M.box(x - 0.32, -0.32, -tail, x + 0.32, 0.32, 1.27 + 0.32).val())
        ps.append(M.box(x - 0.32, -0.32, 1.27 - 0.32, x + 0.32, st.RA_TIP, 1.27 + 0.32).val())
    s.add("ins", M.box(-1.27, off, 0, 29 * M.P + 1.27, off + ins, 2.54), "#1E1E1E")
    s.anchor("p1", (0, off + ins / 2, 2.6))
    s.anchor("p30", (29 * M.P, off + ins / 2, 2.6))
    s.add("pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.5)
    R("p_header", s, (-0.5, -1, 0.8), fit=(150, 60), line=0.3)


@scene
def p_bob():
    """As supplied: the bare breakout (tab on), the loose jack and the loose 1x6 header (three parts)."""
    s = r3d.Scene()
    bob_alone(s, tab=True, jlift=9.0, hdrop=7.0, soldered=False)
    R("p_bob", s, (0.55, -1, 0.9), fit=(130, 100), line=0.3)


@scene
def p_res():
    s = r3d.Scene()
    for k, ref in enumerate((GROUP["RPULL"][0], GROUP["RSER"][0], next(r for r in GROUP["RSER"] if PART[r]["value"] == "100"))):
        sub = r3d.Scene()
        p1, p2 = PL[ref]["pins"]["1"], PL[ref]["pins"]["2"]
        add_resistor(sub, ref)
        # turn each into the same direction (along +Y) side by side
        ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        for name, shp, col, w in sub.parts:
            sh = cq.Shape.cast(shp).translate((-p1[0], -p1[1], 0)).rotate((0, 0, 0), (0, 0, 1), 90 - ang)
            s.add(name, sh.translate((k * 5.0, 0, 0)), col, w)
    R("p_res", s, (0, -0.5, 1), up=(0, 1, 0), fit=(130, 100), line=0.3)


@scene
def p_diode():
    s = r3d.Scene()
    for k, ref in enumerate((GROUP["ZEN"][0], next(r for r in GROUP["S4D"] if "BAT85" in PART[r]["part"]))):
        sub = r3d.Scene()
        add_diode(sub, ref)
        p1, p2 = PL[ref]["pins"]["1"], PL[ref]["pins"]["2"]
        ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        for name, shp, col, w in sub.parts:
            sh = cq.Shape.cast(shp).translate((-p1[0], -p1[1], 0)).rotate((0, 0, 0), (0, 0, 1), -ang)
            s.add(name, sh.translate((0, k * 6.0, 0)), col, w)
    R("p_diode", s, (-0.3, -1, 0.5), fit=(130, 100), line=0.3)


@scene
def p_cap():
    s = r3d.Scene()
    sub = r3d.Scene()
    ref = GROUP["CAPS"][0]
    add_cap(sub, ref)
    x1, y1 = PL[ref]["pins"]["1"]
    _moved(s, sub, -x1, -y1)
    R("p_cap", s, (-0.3, -1, 0.5), fit=(130, 100), line=0.3)


@scene
def p_ptc():
    s = r3d.Scene()
    sub = r3d.Scene()
    ref = GROUP["F4"][0]
    add_ptc(sub, ref)
    x1, y1 = PL[ref]["pins"]["1"]
    _moved(s, sub, -x1, -y1)
    R("p_ptc", s, (-1, -0.4, 0.5), fit=(130, 100), line=0.3)


@scene
def p_wires():
    s = r3d.Scene()
    cols = sorted({w["colour"] for w in UNDER}, key=lambda c: list(INS).index(c))
    for k, col in enumerate(cols):
        y = -k * 5
        s.add(f"w{k}", tube([(0, y, 0), (70, y, 0)], 0.72), INS[col])
        s.add(f"c{k}", cq.Solid.makeCylinder(0.25, 6, cq.Vector(70, y, 0), cq.Vector(1, 0, 0)), "#C87533")
    R("p_wires", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 50), line=0.4)


@scene
def p_jumper():
    s = r3d.Scene()
    s.add("j", tube([(0, 0, -6), (0, 0, 0), (5.08, 0, 0), (5.08, 0, -6)], 0.3), TIN)
    R("p_jumper", s, (-0.3, -1, 0.6), fit=(110, 60), line=0.4)


# ------------------------------------------------------------------ orientation
@scene
def b2_top():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    R("b2_top", s, (0, 0, 1), up=(0, 1, 0), fit=(320, 170), line=0.4, outline=1.2)


@scene
def b2_under():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    R("b2_under", s, (0, 0, -1), up=(0, -1, 0), fit=(320, 170), line=0.4, outline=1.2)


# ------------------------------------------------------------------ underside wires (2-4 per drawing)
def _ugroups():
    n = len(UNDER)
    k = math.ceil(n / 3)
    base, extra = divmod(n, k)
    out, i = [], 1
    for g in range(k):
        m = base + (1 if g < extra else 0)
        out.append(list(range(i, i + m)))
        i += m
    assert all(2 <= len(g) <= 4 for g in out), out
    return out


UGROUPS = _ugroups()


def under_scene(done, now):
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    for n in done:
        w = UNDER[n - 1]
        pts = simplify([(x, y, -0.02) for x, y, _ in w["pts"]])
        s.lines("card", list(zip(pts[:-1], pts[1:])), colour="#9C9C9C", check=False, opacity=0.5, width_mm=1.45)
    for n in now:
        w = UNDER[n - 1]
        body, ends = wire_solid(w)
        s.add(f"w{n}", body, INS[w["colour"]], 0.9)
        s.add(f"e{n}", ends, "#C87533", 0.3)
        hp = simplify([(x, y, -0.9) for x, y, _ in w["pts"]])

        def _trim(a, b, d=1.4):
            L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            return a if L <= d else (a[0] + (b[0] - a[0]) * d / L, a[1] + (b[1] - a[1]) * d / L, a[2])
        hp = [_trim(hp[0], hp[1])] + hp[1:-1] + [_trim(hp[-1], hp[-2])]
        s.lines(f"w{n}", list(zip(hp[:-1], hp[1:])), colour="#FFFFFF", check=False, opacity=0.6, width_mm=0.32)
        # a point on the wire's longest run, for its number tag
        p = simplify([(x, y, -1.47) for x, y, _ in w["pts"]])
        L, a, b = max((np.linalg.norm(np.array(b) - np.array(a)), a, b) for a, b in zip(p[:-1], p[1:]))
        mark(s, f"w{n}m", ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, -1.47), f"w{n}")
    return s


for _gi, _grp in enumerate(UGROUPS):
    def _f(gi=_gi, grp=_grp):
        done = [n for g in UGROUPS[:gi] for n in g]
        R(f"u{gi + 1}", under_scene(done, grp), (0, 0, -1), up=(0, -1, 0), fit=(330, 180), line=0.4, outline=1.2)
    _f.__name__ = f"u{_gi + 1}"
    scene(_f)


# ------------------------------------------------------------------ jumpers, header
def _bare_card():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    return s


@scene
def t_jumpers():
    s = _bare_card()
    add_jumpers(s)
    top_render("t_jumpers", s)


@scene
def t_header():
    top_render("t_header", top_scene("XH2"))


# ------------------------------------------------------------------ parts: full top view + close-up per stage
def _zoom_top(name, upto, refs, fit=(500, 210), pad=3.2):
    c, h = pin_box(refs, pad)
    R(name, top_scene(upto, under=False), (0, 0, 1), up=(0, 1, 0), fit=fit, line=0.45, outline=1.3,
      crop=((c[0], c[1], T), h[0], h[1]))


def _iso(name, upto, refs, d, fit=(460, 200), zmid=3.0, pad=4.0):
    """An iso close-up of refs, cropped round their holes (half sizes from the holes' spread, seen at d)."""
    c, h = pin_box(refs, pad)
    v = r3d.View(d)
    corners = [(c[0] + sx * h[0], c[1] + sy * h[1], T + z) for sx in (-1, 1) for sy in (-1, 1) for z in (0, 2 * zmid)]
    uv = np.array([v.p2(p) for p in corners])
    hw, hh = (uv.max(0) - uv.min(0)) / 2
    R(name, top_scene(upto, under=False, decals=False), d, fit=fit, line=0.35, crop=((c[0], c[1], T + zmid), hw, hh))


for _st, _z in (("RPULL", "z"), ("RSER", "z"), ("CAPS", "i"), ("F4", "i")):
    def _t(stg=_st):
        top_render(f"t_{stg.lower()}", top_scene(stg))
    _t.__name__ = f"t_{_st.lower()}"
    scene(_t)

    def _c(stg=_st, z=_z):
        name = f"{z}_{stg.lower()}"
        if z == "z":
            _zoom_top(name, stg, GROUP[stg])
        else:
            _iso(name, stg, GROUP[stg], ISO_F if stg == "CAPS" else (-0.8, -1, 0.6),
                 zmid=3.0 if stg == "CAPS" else 7.0, fit=(460, 200) if stg == "CAPS" else (300, 220))
    _c.__name__ = f"{_z}_{_st.lower()}"
    scene(_c)


# standing diodes: one top view, one close-up straight down, and the band seen from the side it can be seen from
BAND_SIDE = {r: band_side(r, fitted(g)) for g in ("S4D", "ZEN") for r in GROUP[g]}

for _st in ("S4D", "ZEN"):
    def _t(stg=_st):
        top_render(f"t_{stg.lower()}", top_scene(stg))
    _t.__name__ = f"t_{_st.lower()}"
    scene(_t)

    def _z(stg=_st):
        _zoom_top(f"z_{stg.lower()}", stg, GROUP[stg], fit=(330, 200))
    _z.__name__ = f"z_{_st.lower()}"
    scene(_z)
    for _side in "pq":
        _refs = [r for r in GROUP[_st] if BAND_SIDE[r] == _side]
        if not _refs:
            continue

        def _i(stg=_st, side=_side, refs=tuple(_refs)):
            _iso(f"i_{stg.lower()}_{side}", stg, list(refs), ISO_F if side == "p" else ISO_B, fit=(360, 170), zmid=4.0, pad=2.4)
        _i.__name__ = f"i_{_st.lower()}_{_side}"
        scene(_i)


# ------------------------------------------------------------------ the jacks: prepare (bench), then fit in row a
@scene
def p_bob_kit():
    """Exploded, as supplied: bare board with its tab, jack above, 1x6 header below."""
    s = r3d.Scene()
    bob_alone(s, tab=True, jlift=12.0, hdrop=9.0, soldered=False)
    R("p_bob_kit", s, (0.45, -0.75, 0.6), fit=(250, 260), line=0.35)


@scene
def p_bob_snap():
    """The bare board, tab on, straight down: the V-score line."""
    s = r3d.Scene()
    bob_alone(s, tab=True, jack=False, header=False)
    R("p_bob_snap", s, (0, 0, 1), up=(0, 1, 0), fit=(200, 160), line=0.35)


@scene
def p_bob_ready():
    """Built: jack soldered on top, pins trimmed flush underneath, 1x6 header soldered in the pad row (seen from
    below, the side that faces the card)."""
    s = r3d.Scene()
    bob_alone(s, tab=False, trimmed=False, soldered=True)
    R("p_bob_ready", s, (-0.45, 0.8, -0.75), up=(0, 0, -1), fit=(250, 230), line=0.35)


@scene
def p_bob_top():
    """Built, from above and in front of the mouth: the header's short ends soldered on the pads."""
    s = r3d.Scene()
    bob_alone(s, tab=False, soldered=True)
    R("p_bob_top", s, (-0.5, -0.9, 0.9), fit=(250, 230), line=0.35)


@scene
def t_jacks():
    top_render("t_jacks", top_scene("JACKS"), fit=(330, 230))


@scene
def i_jacks():
    s = top_scene("JACKS", under=False, decals=False)
    R("i_jacks", s, (-0.35, -1, 0.7), fit=(330, 220), line=0.3)


@scene
def t_final():
    s = top_scene("JACKS", under=False, decals=False, holes=False)
    R("t_final", s, (-0.35, -1, 0.85), fit=(330, 190), line=0.3)


SCENE_MARKS = {
    "t_jumpers": [], "u1": [], "t_header": [],
    "t_caps": ["@" + r for r in GROUP["CAPS"]], "t_f4": ["@" + r for r in GROUP["F4"]],
    "t_rpull": ["@" + r for r in GROUP["RPULL"]], "t_rser": ["@" + r for r in GROUP["RSER"]],
    "t_s4d": ["@" + r for r in GROUP["S4D"]], "t_zen": ["@" + r for r in GROUP["ZEN"]],
    "i_caps": [f"{r}_face" for r in GROUP["CAPS"]], "i_f4": [f"{r}_face" for r in GROUP["F4"]],
    "p_bob_kit": ["tab", "score", "jack", "hdr"], "p_bob_snap": ["tab", "score_top"],
    "p_bob_ready": ["jfil", "hdr_bot", "hpin_lo", "peg"], "p_bob_top": ["hfil", "jack"],
    "t_jacks": [f"{r}_jack" for r in GROUP["JACKS"]] + [f"{r}_hfil" for r in GROUP["JACKS"]],
    "i_jacks": [f"{r}_mouth" for r in GROUP["JACKS"]],
}
for _gi, _grp in enumerate(UGROUPS):
    SCENE_MARKS[f"u{_gi + 1}"] = [f"w{n}m" for n in _grp]
for _st in ("S4D", "ZEN"):
    for _side in "pq":
        SCENE_MARKS[f"i_{_st.lower()}_{_side}"] = [f"{r}_band{_side}" for r in GROUP[_st] if BAND_SIDE[r] == _side]


def tab_hits():
    """What each breakout's snap-off tab would land on if it were left on (card frame, stack's boxes)."""
    out = {}
    for ref in GROUP["JACKS"]:
        kind, rot, x0, y0 = PL[ref]["step"][0]
        pcb = next(b for b in PL[ref]["boxes"] if "BOB-14021 PCB" in b.what)
        (xa, ya), (xb, yb) = st.tf(rot, x0, y0, BOB_TAB[0], 0), st.tf(rot, x0, y0, BOB_TAB[1], S.val("bob_d"))
        lo, hi = (min(xa, xb), min(ya, yb)), (max(xa, xb), max(ya, yb))
        hits = []
        for o in REFS:
            if o == ref:
                continue
            for bx in PL[o]["boxes"]:
                if (not bx.keepout and bx.x0 < hi[0] and bx.x1 > lo[0] and bx.y0 < hi[1] and bx.y1 > lo[1]
                        and bx.z0 < pcb.z1 and bx.z1 > pcb.z0 and o not in hits):
                    hits.append(o)
        out[ref] = hits
    return out


if __name__ == "__main__":
    import json
    json.dump(dict(groups={g: GROUP[g] for g in STAGES[1:]}, ugroups=UGROUPS, bands=BAND_SIDE, tab_hits=tab_hits()),
              open(OUT / "groups.json", "w"), indent=1)
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if names == ["groups"]:
        for g in STAGES[1:]:
            print(g, GROUP[g])
        print("bands", BAND_SIDE, "ugroups", UGROUPS)
        sys.exit()
    if len(names) != 1:
        sys.exit("render ONE scene per process: scenes3.py NAME   (scenes3.py list)")
    MARK.update(SCENE_MARKS.get(names[0], []))
    SCENES[names[0]]()
