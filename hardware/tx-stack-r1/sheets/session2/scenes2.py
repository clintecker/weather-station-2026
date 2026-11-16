"""Session 2 (build B4 POWER) illustrations, same pipeline as Session 1 v2 (r3d: hidden lines + ray-cast flat colour).

Geometry comes from the repo, read-only: layout/stack.py (placements, pins, pads, boxes), layout/route.py (every
wire's routed path), the makers' STEP files in render/models/ (INA228, MAX17048, S7V8F3). Card frame = stack's card
frame (X from the left edge along columns 1-30, Y from the FRONT edge, the A side), with the card's top face at
z = 1.6 here (stack's z = 0).

Run: cadx/bin/python -B scenes2.py [name ...]
"""
import math
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "session1" / "v2"))
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")  # live tree, db1936a (clean)
sys.path.insert(0, str(REPO / "layout"))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import stack as st                      # noqa: E402
import route as rt                      # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.SB_T                              # card top face z
HDR = st.HDR                            # 2.5 header plastic
PCB = 1.6

BOARD = {"INA": "#25283A", "MAX": "#25283A", "REG": "#1D6B33"}
WIRE_COL = {"3.3 V supply": "#D7262E", "ground": "#1C1C1C", "I2C clock (SCL)": "#F2C318", "I2C data (SDA)": "#2D6FD0"}
WIRE_NAME = {"3.3 V supply": "RED", "ground": "BLACK", "I2C clock (SCL)": "YELLOW", "I2C data (SDA)": "BLUE"}
LEAD_RED = "#C8222A"
LEAD_OTHER = "#E07A1F"


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    import handed
    handed.card_frame(s)                         # every picture here is drawn in B4's card frame
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


PL = {pl["ref"]: dict(pl, pins=dict(pl["pins"]), pads=dict(pl["pads"])) for pl in st.PLACE["B4"]}

# ------------------------------------------------------------------ wires from route.py
B4_WIRES = []      # dicts: n (B4.md row), a, b, length, line, note, pts (card frame, this z), kind
_net_of_note = {}
for i, (kind, a, b, side, note) in enumerate(st.WIRES):
    r = rt.ROUTES[i]
    if not r or r.get("card") != "B4":
        continue
    B4_WIRES.append(dict(i=i, kind=kind, a=a, b=b, side=side, note=note, cut=rt.cut_length(i),
                         pts=[(x, y, z + T) for x, y, z in r["pts"]], length=r["length"]))
UNDER = [w for w in B4_WIRES if w["side"] == "bottom"]
LEADS = [w for w in B4_WIRES if w["side"] == "top"]
NET = {}
for w in UNDER:
    n = w["note"]
    NET[w["i"]] = ("3.3 V supply" if "3.3 V" in n else "ground" if "ground" in n else
                   "I2C clock (SCL)" if "SCL" in n else "I2C data (SDA)")


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


def lead_solid(w):
    pts = [(x, y, z + 0.75 if abs(z - (0.5 + T)) < 0.01 else z) for x, y, z in w["pts"]]
    return tube(pts, 0.75)


# ------------------------------------------------------------------ parts
def card(s, decals=True, under_pads=True):
    b, p = M.solderful(snapped=True, decals=s if decals else None, part="card")
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    if under_pads:
        _, pb = M.solderful(snapped=True, labels=False)
        pb = pb.mirror("XY", (0, 0, T / 2))
        s.add("padsU", pb, M.GOLD, 0.0)


def hole_xy(h):
    """'e10' -> card XY; 'F+1' / 'F-2' rails."""
    if h.startswith("F+") or h.startswith("F-"):
        return M.col_x(int(h[2:])), M.RAILS_FRONT[0 if h[1] == "+" else 1]
    return M.col_x(int(h[1:])), M.LET_Y[h[0].upper()]


def hole_anchors(s, z, prefix=""):
    for c in "ABCDEFGHIJ":
        for n in range(1, 31):
            s.hole(f"{prefix}{c}{n}", (*hole_xy(f"{c.lower()}{n}"), z))
    for n in range(1, 31):
        s.hole(f"{prefix}F+{n}", (*hole_xy(f"F+{n}"), z))
        s.hole(f"{prefix}F-{n}", (*hole_xy(f"F-{n}"), z))
    for k, (x, y) in (("fl", (0, 0)), ("fr", (M.SB_W, 0)), ("bl", (0, M.SNAP_Y)), ("br", (M.SB_W, M.SNAP_Y))):
        s.anchor(prefix + k, (x, y, z))


STEPS = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1/render/models")  # untracked vendor STEPs
_step_cache = {}


X1_GREEN = "#2E9E4F"


def step_parts(kind):
    """The maker's STEP as [(solid, colour)], in the maker frame used by stack.breakout (pins at y = pin_y)."""
    if kind in _step_cache:
        return _step_cache[kind]
    f = {"INA": "INA/5832_INA228.step", "MAX": "MAX/5580_MAX17048.step", "REG": "REG/pololu_s7v8fx.step"}[kind]
    shp = cq.importers.importStep(str(STEPS / f))
    out = []
    for so in [x for v in shp.vals() for x in v.Solids()]:
        bb = so.BoundingBox()
        if kind == "INA" and bb.zmin < -0.5:          # X1, the screw terminal block: fitted as supplied, desoldered
            out.append((so, "X1"))                     # before U2 goes on the card (it would hit B2's header tails)
            continue
        if kind == "REG":
            so = so.rotate((11.43 / 2, 16.51 / 2, 0), (11.43 / 2, 16.51 / 2, 1), 180)   # pins to the maker's top
        if bb.xlen > 20 and bb.zlen < 1.7 or kind == "REG":
            col = BOARD[kind]
        elif bb.zmax > 3.2:
            col = "#E9E6DC"                            # sockets
        else:
            col = "#4A4A4A"
        out.append((so, col))
    _step_cache[kind] = out
    return out


def add_breakout(s, ref, pulled=(), alone=False, x1=False):
    """A breakout from stack's placement: maker STEP, header plastic, pins. alone: in its own maker frame, not on the
    card (x0, y0 = 0, rot 0, z = 0)."""
    pl = PL[ref]
    kind, rot, x0, y0 = pl["step"][0]
    if alone:
        rot, x0, y0 = 0, 0.0, 0.0
    z0 = 0.0 if alone else T + HDR

    def tfm(sh):
        sh = sh.rotate((0, 0, 0), (0, 0, 1), rot) if rot else sh
        return sh.translate((x0, y0, z0))
    comp = {}
    for so, col in step_parts(kind):
        if col == "X1":
            if not x1:
                continue
            col = X1_GREEN
        comp.setdefault(col, []).append(tfm(so))
    for col, sols in comp.items():
        s.add(f"{ref}_{col}", cq.Compound.makeCompound(sols), col, 1.0 if col == BOARD[kind] else 0.6)
    # header: maker pin positions = stack's names
    names = {"INA": ["H.VIN", "H.GND", "H.SCL", "H.SDA", "P5", "P6", "P7", "H.ALRT"],
             "MAX": ["H.VIN", "H.GND", "H.SCL", "H.SDA", "H.INT", "H.QST"],
             "REG": ["VOUT", "GND", "VIN", "SHDN"]}[kind]
    xf = {"INA": 3.81, "MAX": 6.35, "REG": 1.905}[kind]
    py = 15.24 if kind == "REG" else 2.54
    plast, pins = [], []
    for k, nm in enumerate(names):
        mx = xf + k * M.P
        plast.append(M.box(mx - 1.27, py - 1.27, -HDR, mx + 1.27, py + 1.27, 0).val())
        if nm in pulled:
            continue
        pins.append(M.box(mx - 0.32, py - 0.32, -HDR - (T + 2.8 if not alone else 3.0), mx + 0.32, py + 0.32, PCB + 1.0).val())
    hp = cq.Compound.makeCompound(plast)
    pn = cq.Compound.makeCompound(pins)
    s.add(f"{ref}_hdr", tfm(hp), "#1E1E1E", 0.6).add(f"{ref}_pins", tfm(pn), "#D8B24A", 0.4)
    return pl


def add_header(s):
    """XH4: generic right-angle 1x30 header in j1-j30 (every pin fitted), mating pins toward the back (+Y)."""
    pins = PL["XH4"]["pins"]
    x1, y = pins["1"]
    x18 = x1 + 29 * M.P
    off, ins, mate, tail = st.S.val("ra_offset"), st.S.val("ra_insulator"), st.S.val("ra_mate"), st.S.val("ra_tail")
    pz = T + st.PIN_Z
    insul = M.box(x1 - 1.27, y + off, T, x18 + 1.27, y + off + ins, T + 2 * st.PIN_Z)
    s.add("XH4_ins", insul, "#1E1E1E")
    ps = []
    for n in (k for k in range(1, 31) if str(k) in pins):
        x = pins[str(n)][0]
        ps.append(M.box(x - 0.32, y - 0.32, T - tail, x + 0.32, y + 0.32, pz + 0.32).val())
        ps.append(M.box(x - 0.32, y - 0.32, pz - 0.32, x + 0.32, y + st.RA_TIP, pz + 0.32).val())
    s.add("XH4_pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.4)


# ------------------------------------------------------------------ jumpers and leads (B4.md sections 3 and 5, d9fa90a)
TIN = "#C8CCD0"
BAND = {"red, black band": ("#C8222A", "#1C1C1C"), "white, red band": ("#F4F4F4", "#C8222A")}
JUMPERS = [w for w in B4_WIRES if w["kind"] == "jumper"]
LEADS = [w for w in B4_WIRES if w["kind"] == "lead"]
LEAD_COL = {"B4:g20": "red, black band", "B4:g21": "red, black band", "B4:g23": "white, red band"}
LEAD_NO = {"B4:g20": 1, "B4:g21": 2, "B4:g23": 3}


def jumper_solid(w):
    """Bare tinned jumper between two neighbouring holes: legs down the holes, a low bridge 1 mm over the card."""
    (x1, y1, _), (x2, y2, _) = w["pts"][0], w["pts"][-1]
    h = T + 1.0
    return tube([(x1, y1, T - 1.6), (x1, y1, h), (x2, y2, h), (x2, y2, T - 1.6)], 0.3)


def subpath(pts, d0, d1):
    """The part of polyline pts between arc lengths d0 and d1."""
    out, acc = [], 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = np.array(a), np.array(b)
        L = np.linalg.norm(b - a)
        if L == 0:
            continue
        for d in (d0, d1):
            pass
        lo, hi = max(d0, acc), min(d1, acc + L)
        if lo < hi:
            p0 = a + (b - a) * (lo - acc) / L
            p1 = a + (b - a) * (hi - acc) / L
            if not out or np.linalg.norm(np.array(out[-1]) - p0) > 1e-6:
                out.append(tuple(p0))
            out.append(tuple(p1))
        acc += L
    return out


def lead_path(w):
    """Route.py's path with the lead resting ON the card (centre one radius up), climbing to the breakout's pad
    and ending down in it; the start goes down into its hole (stripped, soldered on the underside)."""
    zt = T + HDR + PCB
    pts = []
    for x, y, z in simplify(w["pts"]):
        pts.append((x, y, T + 0.72 if z < T + 1.0 else zt + 0.72))
    x0, y0, _ = pts[0]
    xe, ye, _ = pts[-1]
    return [(x0, y0, T - 1.6)] + pts + [(xe, ye, zt - 0.2)]


def add_leads(s):
    for w in LEADS:
        n = LEAD_NO[w["a"]]
        body, band = BAND[LEAD_COL[w["a"]]]
        p = lead_path(w)
        Ltot = sum(np.linalg.norm(np.array(b) - np.array(a)) for a, b in zip(p[:-1], p[1:]))
        q = p[1:-1]
        Lq = sum(np.linalg.norm(np.array(b) - np.array(a)) for a, b in zip(q[:-1], q[1:]))
        strip = 2.5                                   # the stripped end, lying on the breakout's top into its pad
        s.add(f"L{n}", tube(subpath(q, 0, Lq - strip), 0.72), body, 0.8)
        bare = subpath(q, Lq - strip, Lq)
        bare = [(x_, y_, p[-1][2] + 0.45) for x_, y_, _ in bare] + [p[-1]]   # flat on the pad, then down its hole
        s.add(f"L{n}cu", tube([p[0], p[1]], 0.26).fuse(tube(bare, 0.26)), "#C87533", 0.4)
        xe, ye, ze = p[-1]
        s.add(f"L{n}joint", cq.Solid.makeCone(1.05, 0.3, 0.75, cq.Vector(xe, ye, ze + 0.2)), TIN, 0.4)
        bands = [tube(subpath(p, 2.2, 8.0), 0.95), tube(subpath(p, Ltot - 9.5, Ltot - 2.4), 0.95)]
        s.add(f"L{n}band", bands[0].fuse(bands[1]), band, 0.8)
        s.anchor(f"L{n}a", (p[1][0], p[1][1], T))
        s.anchor(f"L{n}b", p[-1])
        mid = p[len(p) // 2]
        s.anchor(f"L{n}m", mid)


def add_jumpers(s):
    for k, w in enumerate(JUMPERS, 1):
        s.add(f"J{k}", jumper_solid(w), TIN, 0.6)
        s.anchor(f"J{k}m", ((w["pts"][0][0] + w["pts"][-1][0]) / 2, w["pts"][0][1], T + 1.3))



# ------------------------------------------------------------------ cover renders
@scene
def p_card():
    s = r3d.Scene()
    card(s, under_pads=False)
    R("p_card", s, (-0.3, -0.9, 1.2), fit=(150, 110), line=0.3)


@scene
def p_header():
    s = r3d.Scene()
    off, ins, mate, tail = st.S.val("ra_offset"), st.S.val("ra_insulator"), st.S.val("ra_mate"), st.S.val("ra_tail")
    ps = []
    for n in range(30):                                        # 1x30, every pin fitted (repo 91a5345)
        x = n * M.P
        ps.append(M.box(x - 0.32, -0.32, -tail, x + 0.32, 0.32, 1.27 + 0.32).val())
        ps.append(M.box(x - 0.32, -0.32, 1.27 - 0.32, x + 0.32, st.RA_TIP, 1.27 + 0.32).val())
    s.add("ins", M.box(-1.27, off, 0, 29 * M.P + 1.27, off + ins, 2.54), "#1E1E1E")
    s.anchor("p1", (0, off + ins / 2, 2.6))
    s.anchor("p30", (29 * M.P, off + ins / 2, 2.6))
    s.add("pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.5)
    R("p_header", s, (-0.5, -1, 0.8), fit=(150, 60), line=0.3)


@scene
def p_reg():
    s = r3d.Scene()
    add_breakout(s, "U7", alone=True)
    R("p_reg", s, (-0.4, -1, 1.1), fit=(80, 80), line=0.35)


@scene
def p_ina():
    s = r3d.Scene()
    add_breakout(s, "U2", alone=True, x1=True)
    s.anchor("x1", (7.45, 16.0, 6.0), on=f"U2_{X1_GREEN}")
    s.anchor("p5", (3.81 + 4 * M.P, 2.54, -HDR - 3))
    s.anchor("p7", (3.81 + 6 * M.P, 2.54, -HDR - 3))
    for k in range(8):
        s.anchor(f"pin{k + 1}", (3.81 + k * M.P, 2.54, -HDR - 3.0))
    R("p_ina", s, (-0.35, -1, 0.75), fit=(110, 100), line=0.35)


@scene
def p_ina_pulled():
    s = r3d.Scene()
    add_breakout(s, "U2", pulled=("P5", "P6", "P7"), alone=True)
    for k in range(8):
        s.anchor(f"pin{k + 1}", (3.81 + k * M.P, 2.54, -HDR - 3.0))
    R("p_ina_pulled", s, (-0.35, -1, 0.75), fit=(110, 100), line=0.35)


# SJ1 on U2's back (Adafruit-INA228-PCB .brd: SJ1 SOLDERJUMPER_ARROW_NOPASTE at (14.478, 18.669) MR0, bottom copper;
# pad 1 = VIN+, pad 2 = VBUS). Package polygons, mirrored for the bottom side.
SJ1_XY = (14.478, 18.669)
SJ1_POLYS = [[(-1.293, 0.6866), (-0.6715, 0.6866), (-0.0349, 0), (-0.7215, -0.6866), (-1.293, -0.6866)],
             [(-0.077, 0.6866), (0.5842, 0), (-0.077, -0.6866), (1.293, -0.6866), (1.293, 0.6866)]]
SJ1_SILK = [((1.397, -1.016), (-1.397, -1.016)), ((-1.397, 1.016), (1.397, 1.016)),
            ((1.651, -0.762), (1.651, 0.762)), ((-1.651, -0.762), (-1.651, 0.762))]


def _sj1_xy(lx, ly):
    return SJ1_XY[0] - lx, SJ1_XY[1] + ly          # MR0: mirrored in X


def sj1_scene(closed):
    s = r3d.Scene()
    add_breakout(s, "U2", pulled=("P5", "P6", "P7"), alone=True)
    pads = []
    for poly in SJ1_POLYS:
        pts = [_sj1_xy(*v) for v in poly]
        pads.append(cq.Workplane("XY").workplane(offset=-0.05).polyline(pts).close().extrude(0.05).val())
    s.add("sj1", cq.Compound.makeCompound(pads), M.GOLD, 0.3)
    bname = f"U2_{BOARD['INA']}"
    s.lines(bname, [((*_sj1_xy(*a), -0.01), (*_sj1_xy(*b), -0.01)) for a, b in SJ1_SILK], colour="#FFFFFF",
            check=False, width_mm=0.2)
    if closed:
        blob = (cq.Workplane("XY").box(2.0, 1.15, 0.35).edges().fillet(0.15)
                .translate((SJ1_XY[0], SJ1_XY[1], -0.05 - 0.17)).val())
        s.add("sj1_blob", blob, TIN, 0.4)
    s.anchor("SJ1", (*SJ1_XY, -0.3))
    s.anchor("SJ1_VINP", (*_sj1_xy(-1.016, 0), -0.3))     # pad 1 (VIN+)
    s.anchor("SJ1_VBUS", (*_sj1_xy(1.016, 0), -0.3))      # pad 2 (VBUS)
    for k, xx in (("X1_VINM", 9.2), ("X1_VBUS", 12.7), ("X1_VINP", 16.2)):
        s.anchor(k, (xx, 16.383, -0.1))
    s.anchor("pin1", (3.81, 2.54, -HDR - 3.0))
    return s


@scene
def p_sj1_board():
    R("p_sj1_board", sj1_scene(False), (0, 0, -1), up=(0, -1, 0), fit=(170, 140), line=0.35)


@scene
def p_sj1_open():
    R("p_sj1_open", sj1_scene(False), (0, 0, -1), up=(0, -1, 0), fit=(150, 100), line=0.35,
      crop=((14.4, 17.6, 0), 4.6, 3.0))


@scene
def p_sj1_closed():
    R("p_sj1_closed", sj1_scene(True), (0, 0, -1), up=(0, -1, 0), fit=(150, 100), line=0.35,
      crop=((14.4, 17.6, 0), 4.6, 3.0))


@scene
def p_max():
    s = r3d.Scene()
    add_breakout(s, "U6", alone=True)
    R("p_max", s, (-0.35, -1, 0.75), fit=(110, 100), line=0.35)


@scene
def p_wires():
    s = r3d.Scene()
    for k, (net, col) in enumerate(WIRE_COL.items()):
        y = k * 7
        s.add(f"w{k}", tube([(0, y, 0), (70, y, 0)], 0.72), col)
        s.add(f"c{k}", cq.Solid.makeCylinder(0.25, 6, cq.Vector(70, y, 0), cq.Vector(1, 0, 0)), "#C87533")
    R("p_wires", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 50), line=0.4)


@scene
def p_leads():
    s = r3d.Scene()
    for k, (body, band) in enumerate((BAND["red, black band"], BAND["white, red band"])):
        y = -k * 5.0
        s.add(f"lead{k}", tube([(0, y, 0), (70, y, 0)], 0.72), body, 0.8)
        s.add(f"band{k}", tube([(2, y, 0), (9, y, 0)], 0.95).fuse(tube([(61, y, 0), (68, y, 0)], 0.95)), band, 0.8)
    R("p_leads", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 40), line=0.4)


# ------------------------------------------------------------------ orientation
@scene
def b4_top():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    R("b4_top", s, (0, 0, 1), up=(0, 1, 0), fit=(320, 170), line=0.4, outline=1.2)


@scene
def b4_under():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    R("b4_under", s, (0, 0, -1), up=(0, -1, 0), fit=(320, 170), line=0.4, outline=1.2)


@scene
def b4_flip():
    """The card mid-flip over its front edge (iso), to show which way to turn it."""
    s = r3d.Scene()
    b, p = M.solderful(snapped=True, decals=s, part="card")
    ang = 120
    s.add("card", b.rotate((0, 0, 0), (1, 0, 0), -ang), M.RED_PCB)
    s.add("pads", p.rotate((0, 0, 0), (1, 0, 0), -ang), M.GOLD, 0.0)
    s.decals = []
    R("b4_flip", s, (-0.35, -1, 0.6), fit=(150, 110), line=0.3)


# ------------------------------------------------------------------ underside wires
GROUPS = [[1, 2, 3], [4, 7], [5, 8, 10, 12], [6, 9, 11, 13]]       # B4.md section 2 rows


def by_row(n):
    order = ["f1", "f2", "i12", "h24", "a10", "a20", "h25", "a9", "a19", "d8", "d18", "d7", "d17"]   # B4.md 3ca734c
    a = order[n - 1]
    return next(w for w in UNDER if w["a"] == f"B4:{a}")


def under_scene(done, now):
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    for n in done:                       # already in: light grey, half transparent, true width, holes show through
        pts = simplify([(x, y, -0.02) for x, y, _ in by_row(n)["pts"]])
        s.lines("card", list(zip(pts[:-1], pts[1:])), colour="#9C9C9C", check=False, opacity=0.5, width_mm=1.45)
    for n in now:
        w = by_row(n)
        body, ends = wire_solid(w)
        s.add(f"w{n}", body, WIRE_COL[NET[w["i"]]], 0.9)
        s.add(f"e{n}", ends, "#C87533", 0.3)
        hp = simplify([(x, y, -0.9) for x, y, _ in w["pts"]])   # glossy centre stripe: lifts red off the red card
        def _trim(a, b, d=1.4):
            L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            return a if L <= d else (a[0] + (b[0] - a[0]) * d / L, a[1] + (b[1] - a[1]) * d / L, a[2])
        hp = [_trim(hp[0], hp[1])] + hp[1:-1] + [_trim(hp[-1], hp[-2])]
        s.lines(f"w{n}", list(zip(hp[:-1], hp[1:])), colour="#FFFFFF", check=False, opacity=0.6, width_mm=0.32)
        pts = w["pts"]
        mid = pts[len(pts) // 2]
        s.anchor(f"mid{n}", (mid[0], mid[1], -1.5))
    return s


for gi, grp in enumerate(GROUPS):
    def _f(gi=gi, grp=grp):
        done = [n for g in GROUPS[:gi] for n in g]
        s = under_scene(done, grp)
        R(f"u{gi + 1}", s, (0, 0, -1), up=(0, -1, 0), fit=(330, 180), line=0.4, outline=1.2)
    _f.__name__ = f"u{gi + 1}"
    scene(_f)


@scene
def u_iso():
    s = under_scene([], [n for g in GROUPS for n in g])
    R("u_iso", s, (-0.4, -0.7, -1), up=(0, 1, 0), fit=(200, 140), line=0.3)


# ------------------------------------------------------------------ parts on the top
def top_scene(parts, leads=False, under=True, decals=True):
    s = r3d.Scene()
    card(s, decals=decals)
    hole_anchors(s, T)
    if under:
        for n in range(1, 14):
            body, ends = wire_solid(by_row(n))
            s.add(f"w{n}", body, WIRE_COL[NET[by_row(n)["i"]]], 0.5)
    if "XH4" in parts:
        add_header(s)
    for ref, pulled in (("U7", ()), ("U2", ("P5", "P6", "P7")), ("U6", ())):
        if ref in parts:
            add_breakout(s, ref, pulled)
    if "J" in parts:
        add_jumpers(s)
    if leads:
        add_leads(s)
    for ref in ("U2", "U6", "U7"):
        if ref in parts:
            pl = PL[ref]
            for k, v in pl["pads"].items():
                s.anchor(f"{ref}:{k}", (v[0], v[1], T + HDR + PCB))
    return s


@scene
def t_header():
    s = top_scene(["J", "XH4"])
    R("t_header", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 190), line=0.4, outline=1.2)


@scene
def t_header_iso():
    s = top_scene(["XH4"], under=False, decals=False)
    s.anchor("tip", (PL["XH4"]["pins"]["9"][0], PL["XH4"]["pins"]["9"][1] + st.RA_TIP, T + st.PIN_Z))
    s.anchor("edge", (60, M.SNAP_Y, T))
    R("t_header_iso", s, (0.7, 1, 0.8), fit=(240, 170), line=0.3, crop=((25, 40, 2), 34, 22))


@scene
def t_reg():
    s = top_scene(["J", "XH4", "U7"])
    R("t_reg", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 190), line=0.4, outline=1.2)


@scene
def t_reg_iso():
    s = top_scene(["XH4", "U7"], under=False, decals=False)
    R("t_reg_iso", s, (-0.5, -1, 0.9), fit=(200, 150), line=0.35, crop=((66, 26, 4), 16, 12))


@scene
def t_ina():
    s = top_scene(["J", "XH4", "U7", "U2"])
    R("t_ina", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 190), line=0.4, outline=1.2)


@scene
def t_ina_iso():
    s = top_scene(["XH4", "U7", "U2"], under=False, decals=True)
    R("t_ina_iso", s, (-0.4, -1, 0.8), fit=(220, 160), line=0.35, crop=((18, 16, 4), 20, 15))


@scene
def t_max():
    s = top_scene(["J", "XH4", "U7", "U2", "U6"])
    R("t_max", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 190), line=0.4, outline=1.2)


@scene
def t_jumpers():
    s = top_scene(["J"])
    R("t_jumpers", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 200), line=0.4, outline=1.2)


@scene
def t_jumpers_iso():
    s = top_scene(["J"], under=False, decals=False)
    R("t_jumpers_iso", s, (-0.35, -1, 0.9), fit=(230, 150), line=0.35, crop=((53.3, 36.8, 1.5), 9, 6))


@scene
def p_jumper():
    s = r3d.Scene()
    s.add("j", tube([(0, 0, -6), (0, 0, 0), (12, 0, 0), (12, 0, -6)], 0.3), TIN)
    R("p_jumper", s, (-0.3, -1, 0.6), fit=(110, 60), line=0.4)


@scene
def t_leads():
    s = top_scene(["J", "XH4", "U7", "U2", "U6"], leads=True)
    R("t_leads", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 250), line=0.4, outline=1.2)


@scene
def t_final():
    s = top_scene(["J", "XH4", "U7", "U2", "U6"], leads=True, under=False, decals=False)
    # page 09's leader: on U2's board beside X1's holes
    for dy in (2.0, -2.0):
        vx, vy = PL["U2"]["pads"]["X1.VBUS"]
        s.anchor(f"X1spot{dy:+.0f}", (vx, vy + dy, T + HDR + PCB), on=f"U2_{BOARD['INA']}")
    R("t_final", s, (-0.35, -1, 0.85), fit=(260, 190), line=0.3)


def check_pins():
    """Report where each breakout's STEP header holes land against stack's pin holes."""
    from OCP.GeomAbs import GeomAbs_Circle
    for ref in ("U2", "U6", "U7"):
        pl = PL[ref]
        kind, rot, x0, y0 = pl["step"][0]
        board = [so for so, col in step_parts(kind) if col == BOARD[kind]][0]
        cs = []
        for e in board.Edges():
            if e.geomType() == "CIRCLE" and 0.4 < e.radius() < 0.7:
                c = e.Center()
                cs.append((round(c.x, 2), round(c.y, 2)))
        cs = sorted(set(cs))
        names = {"INA": 8, "MAX": 6, "REG": 4}[kind]
        print(ref, kind, "STEP holes r 0.4-0.7:", cs[:12])


if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENES)
    if names == ["check"]:
        check_pins()
        sys.exit()
    for n in names:
        SCENES[n]()
