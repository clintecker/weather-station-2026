"""Session 5 (build B3 CORE) illustrations, same pipeline as Session 2 (r3d: hidden lines + ray-cast flat colour).

Geometry comes from the repo, read-only: layout/stack.py PLACE["B3"] (placements, pins, boxes), st.WIRES +
layout/route.py (every wire's routed path), the makers' files in render/models/ (Adafruit SHTC3 STEP; the Wio-E5 mini
board STEP built from Seeed's Eagle file by render/fetch_models.py; its module, USB-C, buttons and SMA are stack's
boxes). Card frame = stack's card frame (X from the left edge along rows 1-30, Y from the FRONT edge, the A side),
with the card's top face at z = 1.6 here (stack's z = 0). build/B3.md (via b3md.py) gives the wire colours and is
cross-checked against stack/route on import.

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  cadx/bin/python -B scenes5.py NAME
  cadx/bin/python -B scenes5.py list        (prints every scene name)
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "session1" / "v2"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V2))
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
sys.path.insert(0, str(REPO / "layout"))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import stack as st                      # noqa: E402
import route as rt                      # noqa: E402
import b3md                             # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.SB_T                              # card top face z
HDR = st.HDR                            # 2.5 header plastic
PCB = 1.6
CARD = "B3"

WIRE_COL = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "green": "#2E9E48"}
ADA_BOARD = "#25283A"
MINI_BOARD = "#1A1A1A"
SILVER = "#B8BCC2"
SMA_GOLD = "#D4AF37"


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    import handed
    handed.card_frame(s, CARD)                   # every picture here is drawn in B3's card frame
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


PL = {pl["ref"]: dict(pl, pins=dict(pl["pins"]), pads=dict(pl["pads"])) for pl in st.PLACE[CARD]}
HDR_REF = next(r for r, p in PL.items() if p["fp"] == "RAH")      # XH3
KEY = st.model.KEY[CARD]                                           # 29: pulled from XH3 (the slot key)
assert HDR_REF == "XH3" and len(PL[HDR_REF]["pins"]) == 29 and str(KEY) not in PL[HDR_REF]["pins"], \
    "B3's bus header: a 1x30 less its key pin"
assert KEY == b3md.KEY and st.model.KEY_COLOUR[CARD] == b3md.COLOUR, (KEY, b3md.KEY, b3md.COLOUR)

# ------------------------------------------------------------------ wires: st.WIRES + route.py, checked against B3.md
WIRES = []
for i, (kind, a, b, side, note) in enumerate(rt.WIRES):   # the routed ends (a rail end may move along its rail)
    r = rt.ROUTES[i]
    if not r or r.get("card") != CARD:
        continue
    WIRES.append(dict(i=i, kind=kind, a=a.split(":")[1], b=b.split(":")[1], side=side, note=note,
                      cut=rt.cut_length(i), pts=[(x, y, z + T) for x, y, z in r["pts"]], length=r["length"]))
assert len(WIRES) == len(b3md.WIRES), (len(WIRES), len(b3md.WIRES))
for w, m in zip(WIRES, b3md.WIRES):
    assert (w["a"], w["b"], w["cut"]) == (m["a"], m["b"], m["cut"]), (w, m)
    assert w["side"] == "bottom"
    w.update(n=m["n"], colour=m["colour"], line=m["line"])
BYN = {w["n"]: w for w in WIRES}


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


def bends(n):
    return len(simplify(BYN[n]["pts"])) - 2


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

    def pull(q, r, d=0.9):                 # insulation stops d short of the hole centre
        v = np.array(r[:2]) - np.array(q[:2])
        L = np.linalg.norm(v)
        return (q[0] + v[0] / L * d, q[1] + v[1] / L * d, q[2])
    p2 = [pull(p[0], p[1])] + p[1:-1] + [pull(p[-1], p[-2])]
    body = tube(p2, 0.725)                 # 24 AWG solid, insulated: OD 1.45
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
    """'e10' -> card XY; 'F+1' / 'F-2' rails (stack's own hole_xy: the same grid)."""
    return st.hole_xy(h)


def hole_anchors(s, z, prefix=""):
    for c in "ABCDEFGHIJ":
        for n in range(1, 31):
            s.hole(f"{prefix}{c}{n}", (*hole_xy(f"{c.lower()}{n}"), z))
    for n in range(1, 31):
        s.hole(f"{prefix}F+{n}", (*hole_xy(f"F+{n}"), z))
        s.hole(f"{prefix}F-{n}", (*hole_xy(f"F-{n}"), z))
    for k, (x, y) in (("fl", (0, 0)), ("fr", (M.SB_W, 0)), ("bl", (0, M.SNAP_Y)), ("br", (M.SB_W, M.SNAP_Y))):
        s.anchor(prefix + k, (x, y, z))


# ------------------------------------------------------------------ makers' models
STEPS = REPO / "render" / "models"      # git-ignored vendor files (render/fetch_models.py)
_cache = {}


def _solids(f):
    if f not in _cache:
        shp = cq.importers.importStep(str(STEPS / f))
        _cache[f] = [x for v in shp.vals() for x in v.Solids()]
    return _cache[f]


def shtc3_parts():
    """Adafruit 4636 STEP in its maker frame (pins at y = 2.54, x 7.62 ... 17.78): [(solid, colour)]."""
    out = []
    for so in _solids("SHTC3/4636_SHTC3.step"):
        bb = so.BoundingBox()
        if bb.xlen > 20 and bb.zlen < 1.7:
            col = ADA_BOARD
        elif bb.zmax > 3.2:
            col = "#E9E6DC"                            # STEMMA QT sockets
        else:
            col = "#4A4A4A"
        out.append((so, col))
    return out


def mini_parts():
    """Seeed Wio-E5 mini board STEP (built by fetch_models.py from LoRa-E5 mini v1.0.brd), maker frame = stack's
    mini() frame (pins B at y 20.45, D at y 2.67, from x 16.19). Board + plated holes; tracks/silk left out."""
    board, pth = [], []
    for so in _solids("MINI/wio_e5_mini_board.step"):
        bb = so.BoundingBox()
        if bb.xlen > 40:
            board.append(so)
        elif bb.zmin < -0.02 and bb.zmax > 1.5:        # plated through holes (both faces)
            pth.append(so)
    return [(cq.Compound.makeCompound(board), MINI_BOARD), (cq.Compound.makeCompound(pth), M.GOLD)]


def stack_box(b, dz=T):
    return M.box(b.x0, b.y0, b.z0 + dz, b.x1, b.y1, b.z1 + dz)


def _pins_down(xy, z_top, alone):
    """A breakout's header pins: from z_top (through its board) down through the card."""
    z_bot = -3.0 if not alone else z_top - PCB - HDR - 3.0
    return [M.box(x - 0.32, y - 0.32, z_bot, x + 0.32, y + 0.32, z_top + 1.0).val() for x, y in xy]


def add_shtc3(s, alone=False, anchors=True):
    pl = PL["U5"]
    kind, rot, x0, y0 = pl["step"][0]
    if alone:
        rot, x0, y0 = 0, 0.0, 0.0
    z0 = 0.0 if alone else T + HDR

    def tfm(sh):
        sh = sh.rotate((0, 0, 0), (0, 0, 1), rot) if rot else sh
        return sh.translate((x0, y0, z0))
    comp = {}
    for so, col in shtc3_parts():
        comp.setdefault(col, []).append(tfm(so))
    for col, sols in comp.items():
        s.add(f"U5_{col}", cq.Compound.makeCompound(sols), col, 1.0 if col == ADA_BOARD else 0.6)
    names = ["VIN", "3V", "GND", "SCL", "SDA"]
    plast = [M.box(7.62 + k * M.P - 1.27, 2.54 - 1.27, -HDR, 7.62 + k * M.P + 1.27, 2.54 + 1.27, 0).val() for k in range(5)]
    s.add("U5_hdr", tfm(cq.Compound.makeCompound(plast)), "#1E1E1E", 0.6)
    pins = [M.box(7.62 + k * M.P - 0.32, 2.54 - 0.32, -HDR - (T + 2.8 if not alone else 3.0),
                  7.62 + k * M.P + 0.32, 2.54 + 0.32, PCB + 1.0).val() for k in range(5)]
    s.add("U5_pins", tfm(cq.Compound.makeCompound(pins)), "#D8B24A", 0.4)
    for k, nm in enumerate(names if anchors else []):
        x, y = (7.62 + k * M.P, 2.54)
        if not alone:
            x, y = st.tf(rot, x0, y0, x, y)
        s.anchor(f"U5:{nm}", (x, y, z0 + PCB + 1.0), on="U5_pins")
    if alone:
        for k, nm in enumerate(names):
            s.anchor(f"U5pin:{nm}", (7.62 + k * M.P, 2.54, -HDR - 3.0))
    # the two STEMMA QT sockets: anchors on their top faces
    for k, xq in ((("qtL", 2.6), ("qtR", 22.8)) if anchors else ()):
        x, y = (xq, 8.9) if alone else st.tf(rot, x0, y0, xq, 8.9)
        s.anchor(f"U5:{k}", (x, y, z0 + 1.57 + 2.96), on=f"U5_#E9E6DC")
    return pl


def add_mini(s, alone=False, anchors=True):
    """A1 Wio-E5 mini: the board STEP, stack's boxes for the module, USB-C, buttons and SMA-K, its two 1x12 header
    pieces (plastic under the board) and 24 pins down through the card."""
    pl = PL["A1"]
    kind, rot, x0, y0 = pl["step"][0]
    assert rot == 0
    dx, dy = (-x0, -y0) if alone else (0.0, 0.0)
    dz = -HDR if alone else T                     # stack z (card top 0, mini board HDR) -> this scene
    zb = HDR + dz                                 # board underside
    for so, col in mini_parts():
        s.add(f"A1_{'board' if col == MINI_BOARD else 'pth'}", so.translate(cq.Vector(x0 + dx, y0 + dy, zb)), col,
              1.0 if col == MINI_BOARD else 0.3)
    bx = {b.what.split(" ", 1)[1]: b for b in pl["boxes"]}

    def sb(what, col, name, wt=0.8):
        b = bx[what]
        s.add(name, M.box(b.x0 + dx, b.y0 + dy, b.z0 + dz, b.x1 + dx, b.y1 + dy, b.z1 + dz), col, wt)
        return b
    sb("header plastic B", "#1E1E1E", "A1_hdrB", 0.6)
    sb("header plastic D", "#1E1E1E", "A1_hdrD", 0.6)
    m = sb("LoRa-E5 module", SILVER, "A1_module")
    sb("USB-C receptacle", SILVER, "A1_usb")
    sb("BOOT button", "#444444", "A1_boot", 0.6)
    sb("RESET button", "#444444", "A1_reset", 0.6)
    k = bx["SMA-K"]                               # SMA-K edge jack: a gold cylinder along +X (stack's box)
    r_ = (k.y1 - k.y0) / 2
    cy, cz = (k.y0 + k.y1) / 2 + dy, (k.z0 + k.z1) / 2 + dz
    sma = cq.Solid.makeCylinder(r_ * 0.75, k.x1 - k.x0, cq.Vector(k.x0 + dx, cy, cz), cq.Vector(1, 0, 0))
    nut = (cq.Workplane("YZ").polygon(6, 2 * r_ / np.cos(np.pi / 6)).extrude(3.0)
           .translate((k.x0 + dx + 6.0, cy, cz)).val())
    s.add("A1_sma", sma.fuse(nut).clean(), SMA_GOLD, 0.8)
    s.text("A1_module", "LoRa-E5", ((m.x0 + m.x1) / 2 + dx, (m.y0 + m.y1) / 2 + dy - 0.6, m.z1 + dz + 0.002),
           (1, 0, 0), (0, 1, 0), 1.9, colour="#30343A", font="Helvetica-Bold")
    pins = []
    for nm, (x, y) in pl["pins"].items():
        pins.append((x + dx, y + dy))
    zt = HDR + PCB + dz
    s.add("A1_pins", cq.Compound.makeCompound(_pins_down(pins, zt, alone)), "#D8B24A", 0.4)
    if not anchors:
        return pl
    s.anchor("A1:module", ((m.x0 + m.x1) / 2 + dx, m.y0 + 2.0 + dy, m.z1 + dz), on="A1_module")
    s.anchor("A1:sma", (k.x1 - 2.0 + dx, cy, cz + r_ * 0.75), on="A1_sma")
    u = bx["USB-C receptacle"]
    s.anchor("A1:usb", ((u.x0 + u.x1) / 2 + dx, (u.y0 + u.y1) / 2 + dy, u.z1 + dz), on="A1_usb")
    for nm, (x, y) in pl["pins"].items():
        s.anchor(f"A1:{nm}", (x + dx, y + dy, zt + 1.0), on="A1_pins")
    return pl


def add_ra(s, ref, alone=False):
    """A right-angle 1xn header from stack's placement (XH3: toward the back; J3: toward the front edge)."""
    pl = PL[ref]
    pins = pl["pins"]
    xs = sorted(x for x, _ in pins.values())
    y = next(iter(pins.values()))[1]
    ins = next(b for b in pl["boxes"] if "insulator" in b.what)
    mate = next(b for b in pl["boxes"] if "mating pins" in b.what)
    s_ = 1 if mate.y0 > y else -1
    tip = mate.y1 if s_ > 0 else mate.y0
    tail = st.S.val("ra_tail")
    pz = T + st.PIN_Z
    s.add(f"{ref}_ins", M.box(ins.x0, ins.y0, T + ins.z0, ins.x1, ins.y1, T + ins.z1), "#1E1E1E")
    ps = []
    for x in xs:
        ps.append(M.box(x - 0.32, y - 0.32, T - tail, x + 0.32, y + 0.32, pz + 0.32).val())
        y0, y1 = sorted((y, tip))
        ps.append(M.box(x - 0.32, y0 - (0.32 if s_ < 0 else 0), pz - 0.32, x + 0.32, y1 + (0.32 if s_ > 0 else 0), pz + 0.32).val())
    s.add(f"{ref}_pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.4)
    s.anchor(f"{ref}:tip", (xs[len(xs) // 2], tip - s_ * 0.6, pz + 0.32), on=f"{ref}_pins")
    s.anchor(f"{ref}:ins", ((xs[0] + xs[-1]) / 2, (ins.y0 + ins.y1) / 2, T + ins.z1), on=f"{ref}_ins")
    return pl


# ------------------------------------------------------------------ cover / parts renders
@scene
def p_card():
    s = r3d.Scene()
    card(s, under_pads=False)
    R("p_card", s, (-0.3, -0.9, 1.2), fit=(150, 110), line=0.3)


@scene
def p_header():
    s = r3d.Scene()
    off, ins = st.S.val("ra_offset"), st.S.val("ra_insulator")
    tail = st.S.val("ra_tail")
    ps, key = [], []
    for n in range(30):                                        # 1x30 less the key pin: it is drawn pulled out,
        x = n * M.P                                            # lifted 7 mm above its empty place
        dz = 7.0 if n + 1 == KEY else 0.0
        (key if dz else ps).append(M.box(x - 0.32, -0.32, -tail + dz, x + 0.32, 0.32, 1.27 + 0.32 + dz).val())
        (key if dz else ps).append(M.box(x - 0.32, -0.32, 1.27 - 0.32 + dz, x + 0.32, st.RA_TIP, 1.27 + 0.32 + dz).val())
    s.add("ins", M.box(-1.27, off, 0, 29 * M.P + 1.27, off + ins, 2.54), "#1E1E1E")
    s.anchor("p1", (0, off + ins / 2, 2.6))
    s.anchor("p30", (29 * M.P, off + ins / 2, 2.6))
    s.anchor("gap", ((KEY - 1) * M.P, off + ins / 2, 2.6))
    s.add("pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.5)
    s.add("keypin", cq.Compound.makeCompound(key), "#D8B24A", 0.5)
    s.anchor("key", ((KEY - 1) * M.P, st.RA_TIP * 0.6, 1.27 + 0.32 + 7.0), on="keypin")
    R("p_header", s, (-0.5, -1, 0.8), fit=(150, 60), line=0.3)


@scene
def p_swd():
    s = r3d.Scene()
    off, ins = st.S.val("ra_offset"), st.S.val("ra_insulator")
    tail = st.S.val("ra_tail")
    ps = []
    for n in range(5):
        x = n * M.P
        ps.append(M.box(x - 0.32, -0.32, -tail, x + 0.32, 0.32, 1.27 + 0.32).val())
        ps.append(M.box(x - 0.32, -0.32, 1.27 - 0.32, x + 0.32, st.RA_TIP, 1.27 + 0.32).val())
    s.add("ins", M.box(-1.27, off, 0, 4 * M.P + 1.27, off + ins, 2.54), "#1E1E1E")
    s.add("pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.5)
    R("p_swd", s, (-0.5, -1, 0.8), fit=(90, 70), line=0.35)


@scene
def p_shtc3():
    s = r3d.Scene()
    add_shtc3(s, alone=True)
    R("p_shtc3", s, (-0.35, -1, 0.75), fit=(110, 100), line=0.35)


@scene
def p_mini():
    s = r3d.Scene()
    add_mini(s, alone=True)
    R("p_mini", s, (-0.35, -1, 0.85), fit=(170, 110), line=0.3)


@scene
def p_wires():
    s = r3d.Scene()
    for k, col in enumerate(("red", "black", "yellow", "blue", "green")):
        y = -k * 6
        s.add(f"w{k}", tube([(0, y, 0), (70, y, 0)], 0.72), WIRE_COL[col])
        s.add(f"c{k}", cq.Solid.makeCylinder(0.25, 6, cq.Vector(70, y, 0), cq.Vector(1, 0, 0)), "#C87533")
    R("p_wires", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 50), line=0.4)


# ------------------------------------------------------------------ orientation
@scene
def b3_top():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    R("b3_top", s, (0, 0, 1), up=(0, 1, 0), fit=(320, 170), line=0.4, outline=1.2)


@scene
def b3_under():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    R("b3_under", s, (0, 0, -1), up=(0, -1, 0), fit=(320, 170), line=0.4, outline=1.2)


# ------------------------------------------------------------------ underside wires (B3.md section 2)
GROUPS = [([1, 2, 3], "BUS 3.3 V AND BOTH BUS GROUNDS TO THE FRONT RAILS"),
          ([5, 6, 10, 12], "THE SHTC3'S POWER, CLOCK AND DATA"),
          ([4, 7, 8], "THE MINI'S 3.3 V AND ITS TWO GROUNDS"),
          ([9, 11, 13], "THE MINI'S I2C CLOCK AND DATA, AND THE MUX RESET"),
          ([14, 15, 16], "CUPS, VANE AND RAIN TO THE MINI"),
          ([17, 21], "SWD 3.3 V AND SWD GROUND"),
          ([18, 19, 20], "SWD DATA, CLOCK AND RESET")]
assert sorted(n for g, _ in GROUPS for n in g) == list(range(1, 22))


def under_scene(done, now):
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    for n in done:                       # already in: light grey, half transparent, true width, holes show through
        pts = simplify([(x, y, -0.02) for x, y, _ in BYN[n]["pts"]])
        s.lines("card", list(zip(pts[:-1], pts[1:])), colour="#9C9C9C", check=False, opacity=0.5, width_mm=1.45)
    for n in now:
        w = BYN[n]
        body, ends = wire_solid(w)
        s.add(f"w{n}", body, WIRE_COL[w["colour"]], 0.9)
        s.add(f"e{n}", ends, "#C87533", 0.3)
        hp = simplify([(x, y, -0.9) for x, y, _ in w["pts"]])   # glossy centre stripe: lifts red off the red card

        def _trim(a, b, d=1.4):
            L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            return a if L <= d else (a[0] + (b[0] - a[0]) * d / L, a[1] + (b[1] - a[1]) * d / L, a[2])
        hp = [_trim(hp[0], hp[1])] + hp[1:-1] + [_trim(hp[-1], hp[-2])]
        s.lines(f"w{n}", list(zip(hp[:-1], hp[1:])), colour="#FFFFFF" if w["colour"] != "yellow" else "#5A4A00",
                check=False, opacity=0.6, width_mm=0.32)
    return s


for gi, (grp, _t) in enumerate(GROUPS):
    def _f(gi=gi, grp=grp):
        done = [n for g, _ in GROUPS[:gi] for n in g]
        s = under_scene(done, grp)
        R(f"u{gi + 1}", s, (0, 0, -1), up=(0, -1, 0), fit=(520, 290), line=0.4, outline=1.2)
    _f.__name__ = f"u{gi + 1}"
    scene(_f)


# ------------------------------------------------------------------ parts on the top (B3.md section 3, lowest first)
ORDER = ["J3", "XH3", "U5", "A1"]


def top_scene(parts, under=True, decals=True, anchors=True):
    s = r3d.Scene()
    card(s, decals=decals)
    hole_anchors(s, T)
    if under:
        for n in range(1, 22):
            body, ends = wire_solid(BYN[n])
            s.add(f"w{n}", body, WIRE_COL[BYN[n]["colour"]], 0.5)
            s.add(f"e{n}", ends, "#C87533", 0.3)
    for ref in ("J3", "XH3"):
        if ref in parts:
            add_ra(s, ref)
    if "XH3" in parts:                   # the slot key's colour dot (B3.md step 1.4) goes on with the header
        M.key_dot(s, st.model.KEY_COLOUR[CARD])
    if "U5" in parts:
        add_shtc3(s, anchors=anchors)
    if "A1" in parts:
        add_mini(s, anchors=anchors)
    return s


def _top(name, parts, fit=(330, 200)):
    def f():
        R(name, top_scene(parts), (0, 0, 1), up=(0, 1, 0), fit=fit, line=0.4, outline=1.2)
    f.__name__ = name
    scene(f)


_top("t_swd", ["J3"], fit=(520, 260))
_top("t_header", ["J3", "XH3"], fit=(520, 260))
_top("t_shtc3", ["J3", "XH3", "U5"], fit=(520, 260))
_top("t_mini", ["J3", "XH3", "U5", "A1"], fit=(520, 300))
_top("t_strips", [], fit=(520, 300))


@scene
def t_swd_iso():
    s = top_scene(["J3"], under=False, decals=False)
    R("t_swd_iso", s, (-0.45, -1, 0.8), fit=(240, 160), line=0.35, crop=((36.8, 9, 1.5), 14, 9))


@scene
def t_header_iso():
    s = top_scene(["J3", "XH3"], under=False, decals=False)
    R("t_header_iso", s, (0.7, 1, 0.8), fit=(240, 170), line=0.3, crop=((25, 40, 2), 34, 22))


@scene
def t_shtc3_iso():
    s = top_scene(["J3", "XH3", "U5"], under=False, decals=True, anchors=False)
    R("t_shtc3_iso", s, (-0.4, -1, 0.8), fit=(240, 160), line=0.35, crop=((16, 12, 4), 19, 13))


@scene
def t_mini_iso():
    s = top_scene(["J3", "XH3", "U5", "A1"], under=False, decals=False, anchors=False)
    R("t_mini_iso", s, (0.35, -1, 0.9), fit=(300, 200), line=0.3, crop=((60, 22, 4), 42, 20))


@scene
def t_final():
    s = top_scene(ORDER, under=False, decals=False, anchors=False)
    R("t_final", s, (-0.35, -1, 0.85), fit=(300, 200), line=0.3)


# ------------------------------------------------------------------ shared pictures, rendered into this folder
def _shared(mod, fn):
    def f():
        import importlib
        m = importlib.import_module(mod)
        m.OUT = OUT                     # write here, never into session1/v2/svg
        getattr(m, fn)() if mod == "assembly" else m.SCENES[fn]()
    f.__name__ = fn
    scene(f)


for _n in ("s3_card", "s3_score", "s3_snap", "s3_edge_ok", "s3_edge_bad", "s3_check", "tool_file"):
    _shared("scenes", _n)
for _n in ("asm_iso", "asm_lid"):
    _shared("assembly", _n)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if names == ["bends"]:
        for w in b3md.WIRES:
            print(w["n"], w["a"], w["b"], "B3.md", w["bends"], "route", bends(w["n"]))
        sys.exit()
    for n in names:
        SCENES[n]()
