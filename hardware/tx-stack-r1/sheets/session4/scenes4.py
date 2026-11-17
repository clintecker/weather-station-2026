"""Session 4 (build B1 PORTS A) illustrations, same pipeline as Session 2 (r3d: hidden lines + ray-cast flat colour).

Geometry comes from the repo, read-only: layout/stack.py PLACE["B1"] (every part's pins and boxes, the RJ11
breakouts on their 1x6 headers in row a), layout/route.py (route.WIRES: every wire and jumper with its routed ends,
and its routed path), sources.py (DO-35, MF-R010, resistor and header sizes), and SparkFun's BOB-14021 board in render/models/BOB
(the Amphenol 87180 jack is stack's box: Amphenol's model is behind a login). Card frame = stack's card frame (X from
the left edge along columns 1-30, Y from the FRONT edge, the A side), with the card's top face at z = 1.6 here.

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  cadx/bin/python -B scenes4.py NAME
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "session1" / "v2"))
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
sys.path.insert(0, str(REPO / "layout"))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import stack as st                      # noqa: E402
import b1md                             # noqa: E402


def _routes():
    """route.ROUTES and cut lengths for B1's wires. Routing takes ~30 s per process, so the result is cached in
    svg/ (git-ignored), keyed by the SHA-256 of every repo file the routing reads; any change re-routes."""
    import hashlib
    import pickle
    srcs = [REPO / "layout" / "stack.py", REPO / "layout" / "route.py", REPO / "sources.py", REPO / "schematic" / "model.py"]
    key = hashlib.sha256(b"".join(p.read_bytes() for p in srcs)).hexdigest()[:16]
    f = OUT / f".routes-{key}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    import route as rt
    out = {i: (rt.ROUTES[i], rt.cut_length(i), rt.WIRES[i]) for i in range(len(rt.WIRES))
           if rt.ROUTES[i] and rt.ROUTES[i].get("card") == "B1"}
    f.write_bytes(pickle.dumps(out))
    return out

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.SB_T                              # card top face z
HDR = st.HDR
PCB = st.PCB
S = st.S

TIN = "#C8CCD0"
COPPER = "#C87533"
BOB_RED = st.KIND["BOB"][0]
SPACER = "#E6E2D3"
JACK = "#2A2A2A"
WIRE_COL = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "green": "#2E9B4A"}
ZENER_GLASS = "#E07A1F"                 # 1N5232B
SCHOTTKY_GLASS = "#D8B27A"              # BAT85S
PTC_YELLOW = st.KIND["PTC"][0]
R_BODY = "#D9C59A"


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), use=(), **kw):
    """Render scene s. `use`: the anchors this picture's page labels with a leader ON a part; only these keep their
    visibility check (an anchor hidden behind another part fails the render), and the JSON lists them as
    "checked" so make_session4 refuses a part leader to any other anchor."""
    import json
    import handed
    handed.card_frame(s, "B1")                   # every picture here is drawn in B1's card frame
    missing = [k for k in use if k not in s.anchor_on]
    assert not missing, f"{name}: anchors without a part to be seen on: {missing}"
    s.anchor_on = {k: v for k, v in s.anchor_on.items() if k in use}
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)
    f = OUT / f"{name}.json"
    meta = json.loads(f.read_text())
    meta["checked"] = sorted(use)
    f.write_text(json.dumps(meta, indent=1))


PL = {pl["ref"]: dict(pl, pins=dict(pl["pins"]), pads=dict(pl["pads"])) for pl in st.PLACE["B1"]}

# ------------------------------------------------------------------ wires from route.py, in B1.md order
B1_WIRES = []
_RT = _routes()
for i in sorted(_RT):
    r, cut, (kind, a, b, side, note) = _RT[i]          # route.WIRES: the routed ends (a rail end may move)
    B1_WIRES.append(dict(i=i, kind=kind, a=a, b=b, side=side, note=note, cut=cut, pts=r["pts"], length=r["length"]))
UNDER = [w for w in B1_WIRES if w["kind"] == "wire"]          # B1.md "Underside wires", in order
JUMPERS = [w for w in B1_WIRES if w["kind"] == "jumper"]      # B1.md "Bare jumpers"
assert not [w for w in B1_WIRES if w["kind"] not in ("wire", "jumper")], "B1 has leads again: Session 4 draws none"
for _rows, _ws in ((b1md.wires(), UNDER), (b1md.jumpers(), JUMPERS)):
    assert [(w["a"].split(":")[1], w["b"].split(":")[1]) for w in _ws] == [(r["From"], r["To"]) for r in _rows], \
        "route.WIRES and B1.md disagree on a wire's ends"
assert [w["cut"] for w in UNDER] == [int(r["Length"].split()[0]) for r in b1md.wires()]
UNDER_COL = [r["Colour"] for r in b1md.wires()]


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


def pull(q, r, d=0.9):
    """q moved d toward r (in XY): the insulation stops short of the hole."""
    v = np.array(r[:2]) - np.array(q[:2])
    L = np.linalg.norm(v)
    return (q[0] + v[0] / L * d, q[1] + v[1] / L * d, q[2])


def wire_solid(w):
    """Underside wire: its route at the underside plus the stripped ends up through the two holes."""
    p = simplify([(x, y, -0.75) for x, y, _ in w["pts"]])
    pa, pb = p[0], p[-1]
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
    """'e10' -> card XY; 'F+1' / 'F-2' rails (stack's own hole_xy)."""
    return st.hole_xy(h)


def hole_anchors(s, z, prefix="", drawn=True, skip=()):
    for c in "ABCDEFGHIJ":
        for n in range(1, 31):
            nm = f"{c}{n}"
            s.hole(f"{prefix}{nm}", (*hole_xy(f"{c.lower()}{n}"), z), drawn=drawn and nm not in skip)
    for n in range(1, 31):
        for r in ("F+", "F-"):
            nm = f"{r}{n}"
            s.hole(f"{prefix}{nm}", (*hole_xy(nm), z), drawn=drawn and nm not in skip)
    for k, (x, y) in (("fl", (0, 0)), ("fr", (M.SB_W, 0)), ("bl", (0, M.SNAP_Y)), ("br", (M.SB_W, M.SNAP_Y))):
        s.anchor(prefix + k, (x, y, z))


def anchor_name(h):
    """B1.md hole -> anchor name ('e10' -> 'E10', rails unchanged)."""
    return h if h.startswith("F+") or h.startswith("F-") else h[0].upper() + h[1:]


# ------------------------------------------------------------------ XH1, the 1x30 bus header
def add_header(s, ref="XH1"):
    """Generic right-angle 1x30 header in j1-j30 (every pin fitted), mating pins toward the back (+Y)."""
    pins = PL[ref]["pins"]
    assert sorted(int(k) for k in pins) == list(range(1, 31)), "B1's bus header must be a full 1x30"
    x1, y = pins["1"]
    x30 = pins["30"][0]
    off, ins, tail = S.val("ra_offset"), S.val("ra_insulator"), S.val("ra_tail")
    pz = T + st.PIN_Z
    s.add(f"{ref}_ins", M.box(x1 - 1.27, y + off, T, x30 + 1.27, y + off + ins, T + 2 * st.PIN_Z), "#1E1E1E")
    ps = []
    for n in range(1, 31):
        x = pins[str(n)][0]
        ps.append(M.box(x - 0.32, y - 0.32, T - tail, x + 0.32, y + 0.32, pz + 0.32).val())
        ps.append(M.box(x - 0.32, y - 0.32, pz - 0.32, x + 0.32, y + st.RA_TIP, pz + 0.32).val())
    s.add(f"{ref}_pins", cq.Compound.makeCompound(ps), "#D8B24A", 0.4)
    for n in (1, 10, 18, 19, 30):
        x = pins[str(n)][0]
        s.anchor(f"{ref}_p{n}", (x, y + st.RA_TIP - 0.6, pz + 0.32), on=f"{ref}_pins")


# ------------------------------------------------------------------ two-lead parts (stack.two_pin placements)
def _p3(xy, z):
    return (float(xy[0]), float(xy[1]), float(z))


def add_resistor(s, ref):
    """Lying DIN0207 100 ohm (6.3 x 2.5, sources r_lying_h), leads bent at the body down into its two holes."""
    p1, p2 = (np.array(v) for v in (PL[ref]["pins"]["1"], PL[ref]["pins"]["2"]))
    u = (p2 - p1) / np.linalg.norm(p2 - p1)
    mid = (p1 + p2) / 2
    D = S.val("r_lying_h")
    L = 6.3
    zc = T + 0.1 + D / 2
    a = mid - u * L / 2
    body = cq.Solid.makeCylinder(D / 2 - 0.15, L, cq.Vector(a[0], a[1], zc), cq.Vector(u[0], u[1], 0))
    caps = [cq.Solid.makeCylinder(D / 2, 1.5, cq.Vector(*(mid - u * L / 2 + u * o)[:2], zc), cq.Vector(u[0], u[1], 0))
            for o in (0.0, L - 1.5)]
    b = body
    for c_ in caps:
        b = b.fuse(c_)
    s.add(f"{ref}_body", b.clean(), R_BODY, 0.8)
    # colour code 100 ohm 5 %: brown, black, brown, gold (from lead 1's end)
    bands = [(1.9, "#6B3A1E"), (2.6, "#151515"), (3.3, "#6B3A1E"), (4.7, "#C9A23C")]
    for k, (o, col) in enumerate(bands):
        q = mid - u * L / 2 + u * o
        s.add(f"{ref}_band{k}", cq.Solid.makeCylinder(D / 2 - 0.1, 0.45, cq.Vector(q[0], q[1], zc), cq.Vector(u[0], u[1], 0)),
              col, 0.3)
    leads = tube([_p3(p1, T - 1.6), _p3(p1, zc), _p3(mid - u * L / 2, zc)], 0.3).fuse(
        tube([_p3(mid + u * L / 2, zc), _p3(p2, zc), _p3(p2, T - 1.6)], 0.3))
    s.add(f"{ref}_leads", leads, TIN, 0.5)
    s.anchor(f"{ref}_m", (mid[0], mid[1], zc + D / 2), on=(f"{ref}_body",) + tuple(f"{ref}_band{k}" for k in range(4)))


def diode_value(ref):
    return "1N5232B" if b1md.part(ref)["head"].split(" ")[0] == "1N5232B" else "BAT85S"


def band_end(ref):
    """'bottom' when lead 1 (the body's hole) is the cathode, 'top' when it is the anode (B1.md's pin table)."""
    first = b1md.part(ref)["pins"][0]["Pin"]
    return "bottom" if first.startswith("cathode") else "top"


def add_diode(s, ref):
    """Standing DO-35 (sources do35, diode_stand_h): body on lead 1's hole, the other lead looped over to lead 2."""
    p1, p2 = PL[ref]["pins"]["1"], PL[ref]["pins"]["2"]
    dl, dd = S.val("do35")
    sh = S.val("diode_stand_h")
    z0 = T + 0.8
    glass = ZENER_GLASS if diode_value(ref) == "1N5232B" else SCHOTTKY_GLASS
    body = cq.Solid.makeCylinder(dd / 2, dl, cq.Vector(p1[0], p1[1], z0), cq.Vector(0, 0, 1))
    s.add(f"{ref}_body", body, glass, 0.8)
    zb = z0 + 0.25 if band_end(ref) == "bottom" else z0 + dl - 0.95
    s.add(f"{ref}_band", cq.Solid.makeCylinder(dd / 2 + 0.03, 0.7, cq.Vector(p1[0], p1[1], zb), cq.Vector(0, 0, 1)),
          "#151515", 0.4)
    zt = T + sh - 0.3
    lead = tube([_p3(p1, T - 1.6), _p3(p1, z0 + 0.1)], 0.25).fuse(
        tube([_p3(p1, z0 + dl - 0.1), _p3(p1, zt), _p3(p2, zt), _p3(p2, T - 1.6)], 0.25))
    s.add(f"{ref}_lead", lead, TIN, 0.5)
    s.anchor(f"{ref}_m", (p1[0], p1[1] - dd / 2, z0 + dl * 0.5))     # front face (not checked: do not label)
    s.anchor(f"{ref}_top", (p1[0], p1[1] - 0.65, z0 + dl), on=(f"{ref}_body", f"{ref}_band"))          # top cap
    s.anchor(f"{ref}_loop", ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, zt + 0.25))   # not checked: do not label


def add_ptc(s, ref):
    """MF-R010 Style 1 (Bourns datasheet: round dipped disc 7.4 x 3.1, kinked leads 5.1 apart, 12.7 top to kinks),
    standing, leads formed out to the 7.62 span (F+n to an)."""
    p1, p2 = np.array(PL[ref]["pins"]["1"]), np.array(PL[ref]["pins"]["2"])
    w, t, h = S.val("ptc")
    f = M.mfr010(p1, p2, T, w=w, t=t, h=h)
    s.add(f"{ref}_body", f["body"], PTC_YELLOW, 0.8)
    s.add(f"{ref}_leads", f["leads"], TIN, 0.5)
    s.anchor(f"{ref}_m", tuple(f["face"]), on=f"{ref}_body")
    s.anchor(f"{ref}_top", tuple(f["top"]), on=f"{ref}_body")


# ------------------------------------------------------------------ RJ11 breakouts (BOB-14021 + 87180 jack + 1x6 header)
STEPS = REPO / "render" / "models"
_bob = []
TAILS = S.val("tails")                  # solder tails left under a board after trimming
HDR_SHORT = S.val("ra_tail")            # the generic male header's short leg (above its plastic)
HDR_LONG = S.val("ra_mate")             # its long leg (below its plastic)
HDR_GOLD = "#D8B24A"


def bob_solids():
    """SparkFun's board (imported from RJ11-Breakout.brd) in the maker frame (board bottom z = 0): [(solid, colour)]."""
    if _bob:
        return _bob
    shp = cq.importers.importStep(str(STEPS / "BOB" / "bob14021_board.step"))
    for so in [x for v in shp.vals() for x in v.Solids()]:
        bb = so.BoundingBox()
        if bb.xlen > 15 and bb.ylen > 20:
            _bob.append((so, BOB_RED))
        elif bb.zmax <= 0.001 and bb.zmin > -0.039:
            _bob.append((so, "#F2F2F2"))                 # silkscreen
        else:
            _bob.append((so, M.GOLD))                    # pads, plated holes, bottom copper
    return _bob


def bob_holes():
    """Plated holes of the STEP (maker frame, from the 1.02 mm barrels): header pads (y 1.27) and jack contacts."""
    out = []
    for so, col in bob_solids():
        bb = so.BoundingBox()
        if col == M.GOLD and abs(bb.xlen - 1.02) < 0.05 and bb.zlen > 1.0:
            out.append((round(bb.center.x, 3), round(bb.center.y, 3)))
    return out


BOB_T = max(so.BoundingBox().zmax for so, c in bob_solids() if c == BOB_RED)       # 1.51 (the STEP's board)
HDR_PADS = sorted((h for h in bob_holes() if abs(h[1] - S.val("bob_hdr_y")) < 0.01), key=lambda h: -h[0])
JACK_PINS = [h for h in bob_holes() if h not in HDR_PADS]
PEGS = [(x, S.val("bob_peg_y")) for x in (2.54, 12.7)]           # SparkFun JP3 peg holes (3.2 mm, unplated)
assert len(HDR_PADS) == 6 and len(JACK_PINS) == 6


def maker_boxes(ref="J12"):
    """stack's boxes for a breakout, carried back into the maker frame (rot 180 about (x0, y0)), z from the
    breakout's underside (header plastic below 0)."""
    kind, rot, x0, y0 = PL[ref]["step"][0]
    assert rot == 180
    out = {}
    for key in ("header plastic", "BOB-14021 PCB", "87180-066LF jack"):
        b, = [b for b in PL[ref]["boxes"] if key in b.what]
        out[key] = (x0 - b.x1, y0 - b.y1, b.z0 - HDR, x0 - b.x0, y0 - b.y0, b.z1 - HDR, b.keepout)
    return out


def bob_parts(s, name, xf, board=True, jack=True, header=True, trimmed=True, jack_dz=0.0, hdr_dz=0.0):
    """One breakout in the maker frame, carried into the scene by xf(shape) (a rigid map). Contact i of the header
    (pin i) is pad i of HDR_PADS (pin 1 at maker x 13.97, stack.bob). jack_dz / hdr_dz lift / drop the jack and
    the header apart for an exploded view."""
    mb = maker_boxes()
    if board:
        by = {}
        for so, col in bob_solids():
            by.setdefault(col, []).append(so)
        for col, sols in by.items():
            s.add(f"{name}_{col}", xf(cq.Compound.makeCompound(sols)), col, 1.0 if col == BOB_RED else 0.3)
    if jack:
        x0, y0, z0, x1, y1, z1, _ = mb["87180-066LF jack"]
        z0, z1 = z0 + jack_dz, z1 + jack_dz
        jk = M.box(x0, y0, z0, x1, y1, z1)
        pw, ph = S.val("plug_6p")[0], S.val("plug_6p")[1]
        xc = (x0 + x1) / 2
        mouth = M.box(xc - pw / 2, y1 - 9.0, z0 + 1.0, xc + pw / 2, y1 + 0.1, z0 + 1.0 + ph)
        s.add(f"{name}_jack", xf(jk.cut(mouth).val()), JACK, 1.0)
        tail = (z0 + TAILS) if trimmed else 3.0          # trimmed: TAILS below the board; supplied: about 3 mm
        pins = [M.box(x - 0.25, y - 0.15, z0 - tail, x + 0.25, y + 0.15, z0 + 0.2).val() for x, y in JACK_PINS]
        s.add(f"{name}_jpins", xf(cq.Compound.makeCompound(pins)), TIN, 0.4)
        pegs = [cq.Solid.makeCylinder(1.45, BOB_T + 0.9, cq.Vector(x, y, z0 - BOB_T - 0.8), cq.Vector(0, 0, 1))
                for x, y in PEGS]
        s.add(f"{name}_pegs", xf(cq.Compound.makeCompound(pegs)), JACK, 0.6)
        s.anchor(f"{name}_jtop", xf_pt(xf, (xc, (y0 + y1) / 2, z1)), on=f"{name}_jack")
        s.anchor(f"{name}_mouth", xf_pt(xf, (xc, y1 - 0.6, z1)), on=f"{name}_jack")
        s.anchor(f"{name}_mouthc", xf_pt(xf, (xc, y1, z0 + 1.0 + ph / 2)))
    if header:
        x0, y0, z0, x1, y1, z1, _ = mb["header plastic"]
        pl_ = M.box(x0, y0, z0 + hdr_dz, x1, y1, z1 + hdr_dz)
        s.add(f"{name}_hdr", xf(pl_.val()), "#1E1E1E", 0.8)
        top = z1 + hdr_dz + HDR_SHORT
        bot = z0 + hdr_dz - (T + TAILS if trimmed else HDR_LONG)
        ps = [M.box(x - 0.32, y - 0.32, bot, x + 0.32, y + 0.32, top).val() for x, y in HDR_PADS]
        s.add(f"{name}_pins", xf(cq.Compound.makeCompound(ps)), HDR_GOLD, 0.4)
        for i, (x, y) in enumerate(HDR_PADS, 1):
            s.anchor(f"{name}_c{i}", xf_pt(xf, (x, y, top)))
            s.anchor(f"{name}_c{i}b", xf_pt(xf, (x, y, bot)))
            s.anchor(f"{name}_hc{i}", xf_pt(xf, (x, y0, (z0 + z1) / 2 + hdr_dz)), on=f"{name}_hdr")
    for i, (x, y) in enumerate(HDR_PADS, 1):
        s.anchor(f"{name}_pad{i}", xf_pt(xf, (x, y, BOB_T + 0.04)))


_XF = {}


def xf_pt(xf, p):
    v = xf(cq.Vertex.makeVertex(*map(float, p)))
    return (v.X, v.Y, v.Z)


def on_card(ref):
    """The rigid map from the maker frame (board bottom z = 0) to the card frame for breakout ref (stack.bob)."""
    kind, rot, x0, y0 = PL[ref]["step"][0]

    def f(sh):
        return sh.rotate((0, 0, 0), (0, 0, 1), rot).translate((x0, y0, T + HDR))
    return f


def add_bob(s, ref):
    pl = PL[ref]
    bob_parts(s, ref, on_card(ref))
    pins = pl["pins"]
    for i in range(1, 7):                            # header pin i sits in stack's hole for contact i
        p = xf_pt(on_card(ref), (*HDR_PADS[i - 1], 0))
        assert abs(p[0] - pins[str(i)][0]) < 1e-6 and abs(p[1] - pins[str(i)][1]) < 1e-6, (ref, i, p, pins[str(i)])
    return pl


# ------------------------------------------------------------------ jumpers
def jumper_solid(w):
    """Bare tinned jumper: legs down the two holes, a low bridge 1 mm over the card (across the number row)."""
    (x1, y1, _), (x2, y2, _) = w["pts"][0], w["pts"][-1]
    h = T + 1.0
    return tube([(x1, y1, T - 1.6), (x1, y1, h), (x2, y2, h), (x2, y2, T - 1.6)], 0.3)


def add_jumpers(s, which=None):
    for k, w in enumerate(JUMPERS, 1):
        if which and k not in which:
            continue
        s.add(f"JMP{k}", jumper_solid(w), TIN, 0.6)
        (x1, y1, _), (x2, y2, _) = w["pts"][0], w["pts"][-1]
        s.anchor(f"JMP{k}m", ((x1 + x2) / 2, (y1 + y2) / 2, T + 1.3), on=f"JMP{k}")


# ------------------------------------------------------------------ assembled states
PORT_DIODES = {k: [f"D{k}{j}" for j in range(1, 6)] for k in (1, 2, 3)}
RESISTORS = [p["ref"] for p in b1md.parts() if p["ref"].startswith("R")]
FUSES = [p["ref"] for p in b1md.parts() if p["ref"].startswith("F")]
JACKS = [p["ref"] for p in b1md.parts() if p["ref"].startswith("J1")]
STAGES = ["under", "jumpers", "XH1", "R", "D1", "D2", "D3", "F", "J"]


def build(s, upto, under=True):
    """Everything fitted up to and including stage `upto` (B1.md order: lowest first)."""
    on = set(STAGES[:STAGES.index(upto) + 1])
    if under and "under" in on:
        for n, w in enumerate(UNDER, 1):
            body, ends = wire_solid(w)
            s.add(f"w{n}", body, WIRE_COL[UNDER_COL[n - 1]], 0.5)
    if "jumpers" in on:
        add_jumpers(s)
    if "XH1" in on:
        add_header(s)
    if "R" in on:
        for r in RESISTORS:
            add_resistor(s, r)
    for p in (1, 2, 3):
        if f"D{p}" in on:
            for d in PORT_DIODES[p]:
                add_diode(s, d)
    if "F" in on:
        for f in FUSES:
            add_ptc(s, f)
    if "J" in on:
        for j in JACKS:
            add_bob(s, j)


def top_scene(upto, **kw):
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    build(s, upto, **kw)
    return s


TOP = dict(d=(0, 0, 1), up=(0, 1, 0), line=0.4, outline=1.2)


def top(name, s, fit=(330, 190), **kw):
    R(name, s, TOP["d"], up=TOP["up"], fit=fit, line=TOP["line"], outline=TOP["outline"], **kw)


def holes_box(holes, mx=3.0, my=2.6):
    """Crop window (centre, half width, half height) round a set of B1.md holes, margins mx, my (mm)."""
    xy = np.array([st.hole_xy(h) for h in holes])
    lo, hi = xy.min(0), xy.max(0)
    return ((lo + hi) / 2, (hi - lo)[0] / 2 + mx, (hi - lo)[1] / 2 + my)


def part_holes(refs):
    return [q["Hole"] for r in refs for q in b1md.part(r)["pins"]]


# ------------------------------------------------------------------ cover renders
@scene
def p_card():
    s = r3d.Scene()
    card(s, under_pads=False)
    R("p_card", s, (-0.3, -0.9, 1.2), fit=(150, 110), line=0.3)


@scene
def p_header():
    s = r3d.Scene()
    off, ins, tail = S.val("ra_offset"), S.val("ra_insulator"), S.val("ra_tail")
    ps = []
    for n in range(30):
        x = n * M.P
        ps.append(M.box(x - 0.32, -0.32, -tail, x + 0.32, 0.32, 1.27 + 0.32).val())
        ps.append(M.box(x - 0.32, -0.32, 1.27 - 0.32, x + 0.32, st.RA_TIP, 1.27 + 0.32).val())
    s.add("ins", M.box(-1.27, off, 0, 29 * M.P + 1.27, off + ins, 2.54), "#1E1E1E")
    s.add("pins", cq.Compound.makeCompound(ps), HDR_GOLD, 0.5)
    R("p_header", s, (-0.5, -1, 0.8), fit=(150, 60), line=0.3)


@scene
def p_res():
    s = r3d.Scene()
    add_resistor(s, "R11")
    R("p_res", s, (-0.6, -0.5, 0.6), fit=(110, 80), line=0.4)


@scene
def p_diodes():
    s = r3d.Scene()
    add_diode(s, "D11")
    add_diode(s, "D12")
    R("p_diodes", s, (-0.3, -1, 0.5), fit=(110, 90), line=0.4)


@scene
def p_ptc():
    s = r3d.Scene()
    add_ptc(s, "F1")
    R("p_ptc", s, (-1, -0.5, 0.45), fit=(90, 90), line=0.4)


def ident(sh):
    return sh


@scene
def p_bob():
    """BOB-14021 as SparkFun ships it: the bare board."""
    s = r3d.Scene()
    bob_parts(s, "B", ident, jack=False, header=False)
    R("p_bob", s, (-0.4, -0.7, 1.0), fit=(110, 90), line=0.35)


@scene
def p_jack():
    """Amphenol 87180-066LF as supplied: tails and pegs full length."""
    s = r3d.Scene()
    bob_parts(s, "B", ident, board=False, header=False, trimmed=False)
    R("p_jack", s, (-0.6, 0.8, 0.5), fit=(110, 90), line=0.35)


@scene
def p_hdr6():
    """A 1x6 straight male header (cut from a strip)."""
    s = r3d.Scene()
    bob_parts(s, "B", ident, board=False, jack=False, trimmed=False)
    R("p_hdr6", s, (-0.4, -1, 0.5), fit=(110, 60), line=0.4)


@scene
def p_jumper():
    s = r3d.Scene()
    s.add("j", tube([(0, 0, -6), (0, 0, 0), (12, 0, 0), (12, 0, -6)], 0.3), TIN)
    R("p_jumper", s, (-0.3, -1, 0.6), fit=(110, 60), line=0.4)


@scene
def p_wires():
    s = r3d.Scene()
    for k, col in enumerate(("red", "black", "blue", "yellow")):
        y = -k * 5.0
        s.add(f"w{k}", tube([(0, y, 0), (70, y, 0)], 0.72), WIRE_COL[col])
        s.add(f"c{k}", cq.Solid.makeCylinder(0.25, 4, cq.Vector(70, y, 0), cq.Vector(1, 0, 0)), COPPER)
    R("p_wires", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 50), line=0.4)


# ------------------------------------------------------------------ orientation
@scene
def b1_top():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    top("b1_top", s, fit=(320, 170))


@scene
def b1_under():
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    R("b1_under", s, (0, 0, -1), up=(0, -1, 0), fit=(320, 170), line=0.4, outline=1.2)


# ------------------------------------------------------------------ underside wires
U_GROUPS = [[1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]]
assert sorted(n for g in U_GROUPS for n in g) == list(range(1, len(UNDER) + 1))


def under_scene(done, now):
    s = r3d.Scene()
    card(s)
    hole_anchors(s, 0)
    for n in done:                       # already in: light grey, half transparent, true width
        pts = simplify([(x, y, -0.02) for x, y, _ in UNDER[n - 1]["pts"]])
        s.lines("card", list(zip(pts[:-1], pts[1:])), colour="#9C9C9C", check=False, opacity=0.5, width_mm=1.45)
    for n in now:
        w = UNDER[n - 1]
        body, ends = wire_solid(w)
        s.add(f"w{n}", body, WIRE_COL[UNDER_COL[n - 1]], 0.9)
        s.add(f"e{n}", ends, COPPER, 0.3)
        hp = simplify([(x, y, -1.5) for x, y, _ in w["pts"]])     # glossy centre stripe
        hp = [pull(hp[0], hp[1], 1.4)] + hp[1:-1] + [pull(hp[-1], hp[-2], 1.4)]
        s.lines(f"w{n}", list(zip(hp[:-1], hp[1:])), colour="#FFFFFF", check=False, opacity=0.6, width_mm=0.32)
    return s


for _gi, _grp in enumerate(U_GROUPS):
    def _f(gi=_gi, grp=_grp):
        done = [n for g in U_GROUPS[:gi] for n in g]
        R(f"u{gi + 1}", under_scene(done, grp), (0, 0, -1), up=(0, -1, 0), fit=(330, 180), line=0.4, outline=1.2)
    _f.__name__ = f"u{_gi + 1}"
    scene(_f)


# ------------------------------------------------------------------ top-face steps
@scene
def t_jumpers():
    top("t_jumpers", top_scene("jumpers"), use=[f"JMP{k}m" for k in range(1, len(JUMPERS) + 1)])


@scene
def t_jumpers_iso():
    s = top_scene("jumpers", under=False)
    (cx, cy), hw, hh = holes_box([h for r in b1md.jumpers() for h in (r["From"], r["To"])], 11, 7)
    R("t_jumpers_iso", s, (-1, -0.4, 0.75), fit=(320, 150), line=0.35, crop=((cx, cy, 1.5), hw, hh),
      use=[f"JMP{k}m" for k in range(1, len(JUMPERS) + 1)])


@scene
def t_header():
    top("t_header", top_scene("XH1"), fit=(330, 200))


@scene
def t_header_iso():
    s = top_scene("XH1", under=False)
    R("t_header_iso", s, (0.7, 1, 0.8), fit=(240, 170), line=0.3, crop=((10, 40, 2), 14, 9))


@scene
def t_res():
    top("t_res", top_scene("R"), use=[f"{r}_m" for r in RESISTORS])


ISO_RES = ["R21", "R22"]                 # the close-up: port S2, one slanted, one straight


@scene
def t_res_iso():
    s = top_scene("R", under=False)
    (cx, cy), hw, hh = holes_box(part_holes(ISO_RES), 13, 9)
    R("t_res_iso", s, (-1, -0.45, 0.9), fit=(280, 170), line=0.35, crop=((cx, cy, 2), hw, hh),
      use=[f"{r}_m" for r in ISO_RES])


for _k in (1, 2, 3):
    def _before(k=_k):
        prev = {1: "R", 2: "D1", 3: "D2"}[k]
        s = top_scene(prev)
        (cx, cy), hw, hh = holes_box(part_holes(PORT_DIODES[k]), 2.6, 2.4)
        top(f"t_d{k}_before", s, fit=(300, 150), crop=((cx, cy, T), hw, hh))

    def _iso(k=_k):
        s = top_scene(f"D{k}", under=False)
        (cx, cy), hw, hh = holes_box(part_holes(PORT_DIODES[k]), 3.6, 4.6)
        R(f"t_d{k}_iso", s, (-0.3, -1, 1.1), fit=(300, 190), line=0.35, crop=((cx, cy + 0.5, T + 3.5), hw, hh),
          use=[f"{d}_top" for d in PORT_DIODES[k]])
    _before.__name__ = f"t_d{_k}_before"
    _iso.__name__ = f"t_d{_k}_iso"
    scene(_before)
    scene(_iso)


@scene
def t_fuse_before():
    s = top_scene("D3")
    (cx, cy), hw, hh = holes_box(part_holes(FUSES), 16, 3.5)
    top("t_fuse_before", s, fit=(480, 120), crop=((cx, cy, T), hw, hh))


@scene
def t_fuse_iso():
    s = top_scene("F", under=False)
    (cx, cy), hw, hh = holes_box(part_holes(FUSES), 15, 11)
    R("t_fuse_iso", s, (-0.35, -1, 0.75), fit=(300, 170), line=0.35, crop=((cx, cy + 3, 6.0), hw, hh),
      use=[f"{f}_top" for f in FUSES])


# ------------------------------------------------------------------ the jack breakouts
def bench_xf(dx=0.0, rz=0.0):
    def f(sh):
        sh = sh.rotate((0, 0, 0), (0, 0, 1), rz) if rz else sh
        return sh.translate((dx, 0, 0))
    return f


@scene
def bob_kit():
    """Fit the jack and the header on the bare breakout: exploded, the jack above, the header below."""
    s = r3d.Scene()
    bob_parts(s, "B", ident, trimmed=False, jack_dz=9.0, hdr_dz=-7.0)
    R("bob_kit", s, (-0.55, -0.8, 0.45), fit=(170, 210), line=0.35,
      use=["B_jtop", "B_hc1", "B_hc6"])


@scene
def bob_done():
    """The finished breakout, low from the header end: header plastic under the board, jack on top."""
    s = r3d.Scene()
    bob_parts(s, "B", ident, trimmed=False)
    R("bob_done", s, (-0.6, -1.0, 0.35), up=(0, 0, 1), fit=(200, 170), line=0.35,
      use=["B_hc1", "B_hc6", "B_jtop"])


@scene
def t_jacks_before():
    s = top_scene("F")
    (cx, cy), hw, hh = holes_box(part_holes(JACKS), 3.5, 0)
    lo, hi = -1.5, cy + 2.2                              # the front edge (Y 0) to just behind row a
    top("t_jacks_before", s, fit=(520, 130), crop=((cx, (lo + hi) / 2, T), hw, (hi - lo) / 2))


@scene
def t_jacks():
    s = top_scene("J")
    top("t_jacks", s, fit=(330, 220), use=[f"{j}_jtop" for j in JACKS])


@scene
def t_jacks_iso():
    s = top_scene("J", under=False)
    R("t_jacks_iso", s, (-0.35, -1, 0.7), fit=(330, 200), line=0.3, use=[f"{j}_mouth" for j in JACKS])


# ------------------------------------------------------------------ strip map, finished card
@scene
def t_strips():
    """The strip map: every used strip half (5 holes) and both rails under a translucent band in its line's colour."""
    s = r3d.Scene()
    card(s)
    hole_anchors(s, T)
    for row in b1md.strips():
        col = strip_colour(row["Line"])
        st_ = row["Strip"]
        if st_.startswith("rail"):
            r = st_.split()[1]
            y = st.RAIL_Y[r]
            segs = [((st.X(1) - 1.0, y, T + 0.08), (st.X(30) + 1.0, y, T + 0.08))]
        else:
            n = int(st_.split(",")[0].split()[1])
            half = "abcde" if "A-E" in st_ else "fghij"
            segs = [((st.X(n), st.LETTER_Y[half[0]] - 1.0, T + 0.08), (st.X(n), st.LETTER_Y[half[-1]] + 1.0, T + 0.08))]
        s.lines("card", segs, colour="#FFFFFF", check=False, opacity=0.9, width_mm=2.2)      # white edge: reads on red
        s.lines("card", segs, colour=col, check=False, opacity=0.85, width_mm=1.5)
    top("t_strips", s, fit=(330, 200))


def strip_colour(line):
    """Colour key for the strip map (make_session4 prints the same key)."""
    for key, col in STRIP_KEY:
        if key(line):
            return col
    return "#2E9B4A"


STRIP_KEY = [
    (lambda l: l == "3.3 V supply", "#D7262E"),
    (lambda l: l == "ground", "#1C1C1C"),
    (lambda l: l.startswith("sensor port") and l.endswith("3.3 V"), "#F08A1C"),
    (lambda l: "data (SDA) at the jack" in l, "#7FB0F0"),
    (lambda l: "data (SDA)" in l, "#2D6FD0"),
    (lambda l: "clock (SCL) at the jack" in l, "#F7E07A"),
    (lambda l: "clock (SCL)" in l, "#E0B000"),
    (lambda l: l.startswith("nothing"), "#9A9A9A"),
]


@scene
def t_final():
    s = top_scene("J", under=False)
    R("t_final", s, (-0.35, -1, 0.85), fit=(300, 200), line=0.3)


if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENES)
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    for n in names:
        SCENES[n]()
