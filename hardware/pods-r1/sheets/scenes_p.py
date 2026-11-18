"""Session P (the three pod boards and the port cable) illustrations: the TX sheets' pipeline (r3d: OpenCascade hidden
lines + ray-cast flat colour), every object from real 3D geometry (models_p.py).

Geometry comes from the pods tree, read-only: layout/pods.py (every placed part, pin hole, wire end and wire route, the
TH lead's conductors), layout/permaproto.py (holes, strips, outline), layout/pod_checks.py (the copper netlist that
colours the strip maps) and sources.py (sizes). Board frame = permaproto's (x right along columns 1-15, y up along rows
A-J, origin at the lower-left corner with the silk readable); the board's underside is z = 0, its top z = T.

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  $CADPY -B scenes_p.py NAME          (scenes_p.py list: every scene; render_all.sh renders them all)
"""
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PODS = HERE.parent
REPO = PODS.parent.parent
for p in (HERE, PODS / "layout", PODS, REPO / "hardware" / "tx-stack-r1" / "sheets" / "session1" / "v2"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import r3d                              # noqa: E402  (TX sheets, read-only)
import models_p as M                    # noqa: E402
import pods as PD                       # noqa: E402
import permaproto as PPM                # noqa: E402
import pod_checks as PC                 # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.T
HDR = M.HDR
PODS_ = {n: PD.pod(n) for n in PD.POD_NAMES}
SDA_COL = {n: 15 if n == "BARO" else 14 for n in PD.POD_NAMES}
COL_POD = {14: "UV", 15: "BARO"}        # a pod that stands for each wiring (TH is wired as UV: pods.py)
NET_COL = {"3V3": "#D7262E", "GND": "#1C1C1C", "SDA": "#2D6FD0", "SCL": "#F2C318", "WP": "#2E9A48"}
TOP, UNDER = (0, 0, 1), (0, 0, -1)
ISO_F = (-0.6, -1, 0.9)                 # from the front-left: the bottom (gland) edge toward you
MARK = set()


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def mark(s, name, p, on):
    """An anchor a page leader may use; checked visible on `on` when the page asks for it (SCENE_MARKS)."""
    if name in MARK:
        s.anchor(name, p, on=on)
    else:
        s.anchor(name, p)


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    s.placed_by("Perma-Proto board frame (permaproto.py, right-handed); parts placed by pods.tf turns", np.eye(3))
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


def rz(rot):
    a = math.radians(rot)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.0]])


def place(s, prefix, parts, anc, rot=0, t=(0.0, 0.0, 0.0)):
    """Add a maker-frame build to the scene: turned rot about z, then moved by t. Anchors are prefixed 'prefix:'."""
    s.placed_by(f"{prefix}: maker frame turned {rot} about z", rz(rot))
    for name, shp, col, w in parts:
        sh = cq.Shape.cast(shp.wrapped if hasattr(shp, "wrapped") else shp)
        if rot:
            sh = sh.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), rot)
        s.add(f"{prefix}_{name}", sh.translate(cq.Vector(*t)), col, w)
    Rm = rz(rot)
    for k, (p, on) in anc.items():
        q = tuple(Rm @ np.array(p, float) + np.array(t, float))
        if on is None:
            s.anchor(f"{prefix}:{k}", q)
        else:
            ons = (on,) if isinstance(on, str) else on
            mark(s, f"{prefix}:{k}", q, tuple(f"{prefix}_{o}" for o in ons))


# ------------------------------------------------------------------ the board
def board(s, decals=True, strips=True, copper_bottom=True):
    M.permaproto(s, "pp", decals=decals, strips=strips, copper_bottom=copper_bottom)


def hole_anchors(s, z, drawn=True):
    for n, (x, y) in PPM.HOLES.items():
        s.hole(n, (x, y, z), drawn)
    for k, (x, y) in (("ll", (0, 0)), ("lr", (M.W, 0)), ("ul", (0, M.H)), ("ur", (M.W, M.H))):
        s.anchor(k, (x, y, z))
    for i, (x, y) in enumerate(M.MOUNT):
        s.anchor(f"mh{i}", (x, y, z))


# ------------------------------------------------------------------ wires (24 AWG solid, on the copper side)
def wire_solids(wr):
    """Insulated body along the stored route just under the board, stripped ends up through the two holes, a solder
    joint on the TOP pad of each (the wire goes in from the underside and is soldered on the top)."""
    zc = -0.75
    p = M.simplify([(x, y, zc) for x, y in wr.path])

    def pull(q, r, d=0.9):
        v = np.array(r[:2]) - np.array(q[:2])
        L = np.linalg.norm(v)
        return (q[0] + v[0] / L * d, q[1] + v[1] / L * d, q[2])
    p2 = [pull(p[0], p[1])] + p[1:-1] + [pull(p[-1], p[-2])]
    body = M.tube(p2, 0.725)
    ends, fil = [], []
    for h in (wr.hole_a, wr.hole_b):
        x, y = PPM.HOLES[h]
        q = p2[0] if h == wr.hole_a else p2[-1]
        v = np.array(q) - np.array((x, y, zc))
        ends.append(cq.Solid.makeCylinder(0.26, float(np.linalg.norm(v)), cq.Vector(x, y, zc), cq.Vector(*(v / np.linalg.norm(v)))))
        ends.append(cq.Solid.makeCylinder(0.26, T + 0.6 - zc, cq.Vector(x, y, zc), cq.Vector(0, 0, 1)))
        fil.append(M.fillet_cone(x, y, T + 0.05, True, 0.9, 0.3, 0.55))
    return body, cq.Compound.makeCompound(ends), cq.Compound.makeCompound(fil)


def wire_len(wr):
    pts = [np.array(p) for p in wr.path]
    return float(sum(np.linalg.norm(b - a) for a, b in zip(pts[:-1], pts[1:])))


def add_wires(s, pod, nums, grey=()):
    for n in grey:
        wr = pod.wires[n - 1]
        pts = M.simplify([(x, y, -0.02) for x, y in wr.path])
        s.lines("pp", list(zip(pts[:-1], pts[1:])), colour="#9C9C9C", check=False, opacity=0.55, width_mm=1.45)
    for n in nums:
        wr = pod.wires[n - 1]
        body, ends, fil = wire_solids(wr)
        s.add(f"w{n}", body, M.INS[wr.colour], 0.9)
        s.add(f"e{n}", ends, M.COPPER, 0.3)
        s.add(f"f{n}", fil, M.TIN, 0.3)
        p = M.simplify([(x, y, -1.47) for x, y in wr.path])
        _L, a, b = max((np.linalg.norm(np.array(b) - np.array(a)), a, b) for a, b in zip(p[:-1], p[1:]))
        mark(s, f"w{n}m", ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, -1.47), f"w{n}")


def add_wire_tops(s, pod):
    """Only what shows from the top once the wires are in: the stripped ends and their joints on the top pads."""
    ends, fil = [], []
    for wr in pod.wires:
        for h in (wr.hole_a, wr.hole_b):
            x, y = PPM.HOLES[h]
            ends.append(cq.Solid.makeCylinder(0.26, 0.6 + 1.0, cq.Vector(x, y, T - 1.0), cq.Vector(0, 0, 1)))
            fil.append(M.fillet_cone(x, y, T + 0.05, True, 0.9, 0.3, 0.55))
    s.add("wends", cq.Compound.makeCompound(ends), M.COPPER, 0.3)
    s.add("wfil", cq.Compound.makeCompound(fil), M.TIN, 0.3)


# ------------------------------------------------------------------ parts, from pods.py's placements
def under_joints(s, name, holes):
    """Solder joints on the underside pads round pins pushed in from the top (header pins, resistor leads)."""
    fil = [M.fillet_cone(*PPM.HOLES[h], -0.05, False, 0.9, 0.36, 0.6) for h in holes]
    s.add(name, cq.Compound.makeCompound(fil), M.TIN, 0.3)


def add_r1(s, pod):
    pl = pod.part("R1")
    parts, anc = M.r1_parts(PPM.HOLES[pl.pins["1"]], PPM.HOLES[pl.pins["2"]], T)
    for name, shp, col, w in parts:
        s.add(f"R1_{name}", shp, col, w)
    mark(s, "R1:body", anc["r1"][0], "R1_rbody")


def add_jp1(s, pod, shunt=True):
    pl = pod.part("JP1")
    x, y = PPM.HOLES[pl.pins["1"]]
    parts, anc = M.jp1_parts(shunt=shunt, z0=T)
    place(s, "JP1", parts, anc, 0, (x, y, 0))


def add_bob(s, pod):
    pl = pod.part("J1")
    pcb = next(b for b in pl.boxes if "BOB-14021 PCB" in b.what)
    parts, anc = M.bob_parts(trimmed=True)
    place(s, "J1", parts, anc, pl.rot, (pl.origin[0], pl.origin[1], T + pcb.z0))
    Rm = rz(pl.rot)
    for i, (x, y) in enumerate(M.HPINS, 1):            # the six header pins really are pods.py's six pins
        q = Rm @ np.array((x, y, 0)) + np.array((*pl.origin, 0))
        assert np.allclose(q[:2], PPM.HOLES[pl.pins[str(i)]], atol=1e-6), (i, q, pl.pins[str(i)])
    under_joints(s, "J1_ufil", pl.pins.values())


def add_breakout(s, pl):
    pcb = next(b for b in pl.boxes if b.what.endswith("PCB"))
    key = pl.source
    n = len(pl.pins)
    parts, anc = M.breakout(key, header=True, hdr_n=n, trimmed_to=-(HDR + T + 1.0))
    t = (pl.origin[0], pl.origin[1], T + pcb.z0)
    place(s, pl.ref, parts, anc, pl.rot, t)
    s.xf = (rz(pl.rot), np.array(t, float))
    M.breakout_silk(s, key, f"{pl.ref}_board")
    s.xf = None
    Rm = rz(pl.rot)
    for (x, y), nm in zip(M.hdr_pads(key), M.S.val(key + "_pins")):
        if nm in pl.pins:
            q = Rm @ np.array((x, y, 0)) + np.array(t)
            assert np.allclose(q[:2], PPM.HOLES[pl.pins[nm]], atol=1e-6), (pl.ref, nm, q, pl.pins[nm])
            s.anchor(f"{pl.ref}:{nm}", (q[0], q[1], t[2] + M.PCB + 0.3))
    under_joints(s, f"{pl.ref}_ufil", pl.pins.values())


LEAD_X = 37.6                          # the TH lead's jacket runs past the right of U1, clear of everything


def add_lead(s, pod, jacket_to=-16.0):
    """The TH lead's pod end: the four stranded cores pushed into their holes from the TOP and soldered underneath,
    rising and gathered into the round jacket, which leaves past the bottom (gland) edge high over the board."""
    zj = T + 11.0
    cores = sorted(pod.lead.conductors, key=lambda c: PPM.HOLES[c.hole][0])
    for k, c in enumerate(cores):
        x, y = PPM.HOLES[c.hole]
        off = (k - 1.5) * 1.15
        pts = [(x, y, -1.0), (x, y, T + 2.0), (x, y - 2.5, T + 6.0), (LEAD_X + off, 30.0, zj), (LEAD_X + off, 24.0, zj)]
        s.add(f"L_{c.colour}", M.tube(pts, 0.6), M.INS[c.colour], 0.7)
        mark(s, f"L:{c.colour}", (x, y - 1.25 + 0.5, T + 4.0 + 0.32), f"L_{c.colour}")
    jk = cq.Solid.makeCylinder(2.0, 24.0 - jacket_to, cq.Vector(LEAD_X, jacket_to, zj), cq.Vector(0, 1, 0))
    s.add("L_jacket", jk, M.JACKET, 1.0)
    mark(s, "L:jacket", (LEAD_X, 8.0, zj + 2.0), "L_jacket")
    under_joints(s, "L_ufil", [c.hole for c in pod.lead.conductors])


STAGES = ["bare", "wires", "low", "jack", "eep", "u2"]


def pod_scene(name, upto, holes=True, decals=True, shunt=True):
    """Pod `name` with every stage up to `upto` done, seen from above (the wires show only as their top joints)."""
    pod = PODS_[name]
    k = STAGES.index(upto)
    s = r3d.Scene()
    board(s, decals=decals)
    if holes:
        hole_anchors(s, T)
    if k >= 1:
        add_wire_tops(s, pod)
    if k >= 2:
        add_r1(s, pod)
        add_jp1(s, pod, shunt=shunt)
    if k >= 3:
        add_bob(s, pod)
    if k >= 4:
        add_breakout(s, pod.part("U1"))
    if k >= 5:
        if pod.lead:
            add_lead(s, pod)
        else:
            add_breakout(s, pod.part("U2"))
    if holes:   # holes under a fitted board are not drawn from above
        covers = [b for p in pod.parts if (p.ref in ("J1",) and k >= 3) or (p.ref == "U1" and k >= 4)
                  or (p.ref == "U2" and k >= 5) for b in p.boxes if b.what.endswith("PCB")]
        for n, (x, y) in PPM.HOLES.items():
            if any(b.x0 - 0.6 < x < b.x1 + 0.6 and b.y0 - 0.6 < y < b.y1 + 0.6 for b in covers):
                s.holes[n] = False
            if k >= 2 and n in (pod.part("JP1").pins["1"], pod.part("JP1").pins["2"]):
                s.holes[n] = False
            if k >= 2 and n in pod.part("R1").pins.values():
                s.holes[n] = False
    return s


def top_render(name, s, fit=(330, 300), **kw):
    R(name, s, TOP, up=(0, 1, 0), fit=fit, line=0.4, outline=1.2, **kw)


def iso_render(name, s, fit=(330, 260), d=ISO_F, **kw):
    probe = None
    jk = next((sh for n, sh, _c, _w in s.parts if n == "J1_jack"), None)
    if jk is not None:
        bb = cq.Shape.cast(jk).BoundingBox()
        probe = (bb.xmin if d[0] < 0 else bb.xmax, (bb.ymin + bb.ymax) / 2, (bb.zmin + bb.zmax) / 2)
        s.anchor("_jack_side", probe)
    R(name, s, d, fit=fit, line=0.32, **kw)
    if probe is not None:
        jack_fill_check(name)


def jack_fill_check(name):
    """Guard against a fill error seen at some view angles: the 87180 jack's side face merged into the board's region
    and painted the board's colour. The side face's centre must lie in a fill of the jack's colour."""
    import re
    from shapely.geometry import Point, Polygon
    tones = {r3d._tone(M.JACK, k) for k in (1.0, 0.86, 0.72)}
    a = Point(json.load(open(OUT / f"{name}.json"))["anchors"]["_jack_side"])
    for m in re.finditer(r'<path d="([^"]*)" fill="(#[0-9A-F]+)"', (OUT / f"{name}.svg").read_text()):
        if m.group(2) not in tones:
            continue
        for sub in m.group(1).split("M")[1:]:
            v = [float(t) for t in re.findall(r"-?\d+\.?\d*", sub)]
            pts = list(zip(v[0::2], v[1::2]))
            if len(pts) >= 3 and Polygon(pts).buffer(0).contains(a):
                return
    (OUT / f"{name}.svg").unlink()
    raise SystemExit(f"{name}: the jack's side face is not filled in the jack's colour (view fill error): pick another view")


# ------------------------------------------------------------------ parts as supplied
@scene
def p_pp():
    s = r3d.Scene()
    board(s)
    R("p_pp", s, (-0.25, -0.75, 1.2), fit=(150, 150), line=0.3)


def _breakout_alone(key, n_hdr, hdrop=7.0):
    s = r3d.Scene()
    parts, anc = M.breakout(key, header=True, hdr_n=n_hdr, hdrop=hdrop, soldered=False)
    place(s, key, parts, anc)
    M.breakout_silk(s, key, f"{key}_board")
    return s


@scene
def p_eep():
    R("p_eep", _breakout_alone("eeprom_24lc32", 6), (-0.3, -0.8, 1.0), fit=(150, 130), line=0.3)


@scene
def p_ltr():
    R("p_ltr", _breakout_alone("ltr390", 6), (-0.3, -0.8, 1.0), fit=(150, 130), line=0.3)


@scene
def p_bmp():
    R("p_bmp", _breakout_alone("bmp581", 8), (-0.3, -0.8, 1.0), fit=(150, 130), line=0.3)


@scene
def p_sht():
    R("p_sht", _breakout_alone("sht45", 5), (-0.3, -0.8, 1.0), fit=(150, 130), line=0.3)


@scene
def p_bob():
    s = r3d.Scene()
    parts, anc = M.bob_parts(tab=True, jlift=9.0, hdrop=7.0, soldered=False)
    place(s, "bob", parts, anc)
    R("p_bob", s, (0.55, -1, 0.9), fit=(130, 120), line=0.3)


@scene
def p_jp1():
    s = r3d.Scene()
    parts, anc = M.jp1_parts(shunt=True, shunt_lift=7.0, soldered=False, z0=0.0)
    place(s, "jp", parts, anc)
    R("p_jp1", s, (-0.5, -1, 0.7), fit=(110, 110), line=0.35)


@scene
def p_r1():
    s = r3d.Scene()
    parts, anc = M.r1_parts((0, 0), (10.16, 0), 0.0, tails=4.0)
    place(s, "r", [p for p in parts if p[0] != "rfil"], anc)
    R("p_r1", s, (-0.2, -1, 0.6), fit=(120, 70), line=0.35)


@scene
def p_wires():
    s = r3d.Scene()
    for k, col in enumerate(("red", "black", "yellow", "blue")):
        y = -k * 5
        s.add(f"w{k}", M.tube([(0, y, 0), (60, y, 0)], 0.725), M.INS[col])
        s.add(f"c{k}", cq.Solid.makeCylinder(0.26, 5, cq.Vector(60, y, 0), cq.Vector(1, 0, 0)), M.COPPER)
    R("p_wires", s, TOP, up=(0, 1, 0), fit=(130, 50), line=0.4)


def _lead_end(s, strip=40.0, bare=3.0, length=70.0):
    """A round jacketed 4-core lead along +x, jacket stripped back `strip` mm from the end, cores fanned a little."""
    s.add("jacket", cq.Solid.makeCylinder(2.0, length - strip, cq.Vector(0, 0, 0), cq.Vector(1, 0, 0)), M.JACKET)
    for k, col in enumerate(("red", "black", "yellow", "blue")):
        dy = (k - 1.5) * 1.3
        pts = [(length - strip - 1.0, dy * 0.5, 0), (length - strip + 6, dy, 0), (length - bare, dy * 1.6, 0)]
        s.add(f"core_{col}", M.tube(pts, 0.6), M.INS[col], 0.7)
        s.add(f"tip_{col}", cq.Solid.makeCylinder(0.35, bare, cq.Vector(length - bare, dy * 1.6, 0), cq.Vector(1, 0, 0)),
              M.COPPER, 0.4)
        s.anchor(f"core_{col}", (length - strip + 14, dy * 1.32, 0.6), on=f"core_{col}")
    s.anchor("jacket", (10, 0, 2.0), on="jacket")


@scene
def p_lead():
    s = r3d.Scene()
    _lead_end(s)
    R("p_lead", s, TOP, up=(0, 1, 0), fit=(150, 60), line=0.4)


@scene
def p_cable():
    s = r3d.Scene()
    s.add("cable", cq.Solid.makeCylinder(2.0, 60, cq.Vector(0, 14, 3.3), cq.Vector(0, 1, 0)), M.JACKET)
    parts, anc = M.plug()
    place(s, "plugA", parts, anc, 0, (0, 0, 0))
    for nm, shp, col in M.gland_pg7():
        s.add(f"g_{nm}", shp.translate(cq.Vector(18, 40, 3.3)), col, 0.8)
    s.anchor("cable", (2.0, 60, 3.3 + 2.0))
    s.anchor("plug", (3.0, 8, M.S.val("plug_6p")[1]))
    s.anchor("gland", (18 + 5.0, 40 + 8.0, 3.3 + 5.0))
    R("p_cable", s, (-0.5, -0.6, 1.0), fit=(150, 140), line=0.3)


# ------------------------------------------------------------------ the two faces
@scene
def pp_top():
    s = r3d.Scene()
    board(s)
    hole_anchors(s, T)
    top_render("pp_top", s, fit=(260, 300))


@scene
def pp_under():
    s = r3d.Scene()
    board(s)
    hole_anchors(s, 0)
    R("pp_under", s, UNDER, up=(0, -1, 0), fit=(260, 300), line=0.4, outline=1.2)


# ------------------------------------------------------------------ the jack breakouts (as on the TX cards)
@scene
def bob_kit():
    s = r3d.Scene()
    parts, anc = M.bob_parts(tab=True, jlift=12.0, hdrop=9.0, soldered=False)
    place(s, "bob", parts, anc)
    R("bob_kit", s, (0.45, -0.75, 0.6), fit=(250, 260), line=0.35)


@scene
def bob_snap():
    s = r3d.Scene()
    parts, anc = M.bob_parts(tab=True, jack=False, header=False)
    place(s, "bob", parts, anc)
    R("bob_snap", s, TOP, up=(0, 1, 0), fit=(200, 160), line=0.35)


@scene
def bob_ready():
    s = r3d.Scene()
    parts, anc = M.bob_parts(tab=False, trimmed=False, soldered=True)
    place(s, "bob", parts, anc)
    R("bob_ready", s, (-0.45, 0.8, -0.75), up=(0, 0, -1), fit=(250, 230), line=0.35)


@scene
def bob_top():
    s = r3d.Scene()
    parts, anc = M.bob_parts(tab=False, soldered=True)
    place(s, "bob", parts, anc)
    R("bob_top", s, (-0.5, -0.9, 0.9), fit=(250, 230), line=0.35)


# ------------------------------------------------------------------ headers onto the breakouts
@scene
def hdr_eep():
    s = r3d.Scene()
    parts, anc = M.breakout("eeprom_24lc32", header=True, hdr_n=6)
    place(s, "eep", parts, anc)
    M.breakout_silk(s, "eeprom_24lc32", "eep_board")
    R("hdr_eep", s, (-0.35, -0.9, 0.75), fit=(200, 170), line=0.32)


@scene
def hdr_ltr():
    s = r3d.Scene()
    parts, anc = M.breakout("ltr390", header=True, hdr_n=6)
    place(s, "ltr", parts, anc)
    M.breakout_silk(s, "ltr390", "ltr_board")
    R("hdr_ltr", s, (-0.35, -0.9, 0.75), fit=(200, 170), line=0.32)


@scene
def hdr_bmp():
    s = r3d.Scene()
    parts, anc = M.breakout("bmp581", header=True, hdr_n=6)
    place(s, "bmp", parts, anc)
    M.breakout_silk(s, "bmp581", "bmp_board")
    R("hdr_bmp", s, (-0.35, -0.9, 0.75), fit=(200, 170), line=0.32)


@scene
def bmp_cut():
    """The BMP581's header strip as supplied (one pin per pad: 8), cut between its 6th and 7th pins: the two-pin piece
    (the CS and INT end) moved off to the right."""
    s = r3d.Scene()
    plast, pins = M.loose_header(8)
    keep = plast.intersect(M.box(-2, -2, -1, 5 * M.P + 1.27, 2, 5))
    off = 6.0
    cut = plast.intersect(M.box(5 * M.P + 1.27, -2, -1, 8 * M.P, 2, 5)).translate((off, 0, 0))
    pk = [p for i, p in enumerate(pins.Solids()) if i < 6]
    pc = [p.translate(cq.Vector(off, 0, 0)) for i, p in enumerate(pins.Solids()) if i >= 6]
    s.add("keep", keep, M.HDR_BLACK, 0.8)
    s.add("kpins", cq.Compound.makeCompound(pk), M.PIN, 0.5)
    s.add("cut", cut, "#6A6A6A", 0.8)
    s.add("cpins", cq.Compound.makeCompound(pc), "#B8B8B8", 0.5)
    s.lines("keep", [((5 * M.P + 1.27 + off / 2, -3.2, M.HDR + 0.01), (5 * M.P + 1.27 + off / 2, 3.2, M.HDR + 0.01))],
            colour="#FF2E88", check=False, width=1.6)
    for i in range(8):
        x = i * M.P + (off if i >= 6 else 0)
        s.anchor(f"pin{i + 1}", (x, 0, M.HDR + M.H_SHORT))
    s.anchor("keep", (2.5 * M.P, -1.27, M.HDR / 2), on="keep")
    s.anchor("cut", (6.5 * M.P + off, -1.27, M.HDR / 2), on="cut")
    R("bmp_cut", s, (-0.25, -1, 0.55), fit=(330, 120), line=0.35)


# ------------------------------------------------------------------ per wiring (SDA strip 14: TH and UV; 15: BARO)
def _u_scene(col, grp):
    pod = PODS_[COL_POD[col]]
    s = r3d.Scene()
    board(s)
    hole_anchors(s, 0)
    done = [n for g in UGROUPS if g[0] < grp[0] for n in g]
    add_wires(s, pod, grp, grey=done)
    return s


UGROUPS = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
assert all(len(p.wires) == 9 for p in PODS_.values())
for _c in (14, 15):
    for _gi, _g in enumerate(UGROUPS):
        def _f(col=_c, gi=_gi, g=_g):
            R(f"u{col}_{gi + 1}", _u_scene(col, g), UNDER, up=(0, -1, 0), fit=(300, 330), line=0.4, outline=1.2)
        _f.__name__ = f"u{_c}_{_gi + 1}"
        scene(_f)

    def _low(col=_c):
        top_render(f"t{col}_low", pod_scene(COL_POD[col], "low", shunt=False))
    _low.__name__ = f"t{_c}_low"
    scene(_low)

    def _ilow(col=_c):
        s = pod_scene(COL_POD[col], "low", holes=False, decals=True, shunt=True)
        c = np.array(PPM.HOLES["J5"])
        iso_render(f"i{col}_low", s, fit=(250, 230), d=(-0.9, -0.55, 0.8),
                   crop=((c[0] - 2.0, c[1] + 1.5, T + 3.0), 11.0, 9.0))
    _ilow.__name__ = f"i{_c}_low"
    scene(_ilow)

    def _jack(col=_c):
        top_render(f"t{col}_jack", pod_scene(COL_POD[col], "jack"), fit=(330, 360))
    _jack.__name__ = f"t{_c}_jack"
    scene(_jack)

    def _ijack(col=_c):
        iso_render(f"i{col}_jack", pod_scene(COL_POD[col], "jack", holes=False), fit=(300, 260))
    _ijack.__name__ = f"i{_c}_jack"
    scene(_ijack)

    def _eep(col=_c):
        top_render(f"t{col}_eep", pod_scene(COL_POD[col], "eep"), fit=(330, 360))
    _eep.__name__ = f"t{_c}_eep"
    scene(_eep)

    def _ieep(col=_c):
        iso_render(f"i{col}_eep", pod_scene(COL_POD[col], "eep", holes=False), fit=(300, 260))
    _ieep.__name__ = f"i{_c}_eep"
    scene(_ieep)


# ------------------------------------------------------------------ per pod: the sensor (or the TH lead), the final view
for _n in PD.POD_NAMES:
    def _u2(name=_n):
        top_render(f"t_{name.lower()}_u2", pod_scene(name, "u2"), fit=(330, 380))
    _u2.__name__ = f"t_{_n.lower()}_u2"
    scene(_u2)

    def _iu2(name=_n):
        iso_render(f"i_{name.lower()}_u2", pod_scene(name, "u2", holes=False), fit=(330, 300))
    _iu2.__name__ = f"i_{_n.lower()}_u2"
    scene(_iu2)


# ------------------------------------------------------------------ strip maps: the copper side, each used strip in its net's colour
def strip_nets(pod):
    """{strip id: net} for every strip a pin, wire end or lead end uses, cross-checked against pod_checks.netlist (the
    copper-derived netlist: one name per group, no shorts, no opens)."""
    out = {}
    for p in pod.parts:
        for pin, h in p.pins.items():
            net = p.nets.get(pin)
            if net:
                out.setdefault(PPM.strip_of(h), set()).add(net)
    for wr in pod.wires:
        for h in (wr.hole_a, wr.hole_b):
            out.setdefault(PPM.strip_of(h), set()).add(wr.net)
    if pod.lead:
        for c in pod.lead.conductors:
            out.setdefault(PPM.strip_of(c.hole), set()).add(c.net)
    bad = {k: v for k, v in out.items() if len(v) != 1}
    assert not bad, f"{pod.name}: strips with two nets {bad}"
    nl = PC.netlist(pod)
    assert all("+" not in k and ("#" not in k or k.startswith("NC")) for k in nl), f"{pod.name}: netlist {list(nl)}"
    return {k: next(iter(v)) for k, v in out.items()}


def strip_solids(sid, z0=-0.11, z1=-0.051):
    sw = 1.25
    if sid.startswith("rail "):
        r = sid.split()[1]
        (x0, y), (x1, _y) = PPM.HOLES[f"{r}1"], PPM.HOLES[f"{r}15"]
        b = M.box(x0 - 0.9, y - sw / 2, z0, x1 + 0.9, y + sw / 2, z1)
    else:
        half, c = sid[:3], int(sid[3:])
        lo, hi = ("A", "E") if half == "A-E" else ("F", "J")
        (x, y0), (_x, y1) = PPM.HOLES[f"{lo}{c}"], PPM.HOLES[f"{hi}{c}"]
        b = M.box(x - sw / 2, y0 - 0.9, z0, x + sw / 2, y1 + 0.9, z1)
    holes = [PPM.HOLES[h] for h in PPM.HOLES if PPM.strip_of(h) == sid]
    return b.faces("<Z").workplane(origin=(0, 0, z0)).pushPoints(holes).hole(M.DRILL)


for _c in (14, 15):
    def _sm(col=_c):
        pod = PODS_[COL_POD[col]]
        s = r3d.Scene()
        board(s)
        hole_anchors(s, 0)
        sn = strip_nets(pod)
        by = {}
        for sid, net in sn.items():
            by.setdefault(net, []).append(strip_solids(sid).val())
        for net, sols in by.items():
            s.add(f"net_{net}", cq.Compound.makeCompound(sols), NET_COL[net], 0.6)
        for wr in pod.wires:
            pts = M.simplify([(x, y, -0.2) for x, y in wr.path])
            s.lines("pp", list(zip(pts[:-1], pts[1:])), colour="#FFFFFF", check=False, width_mm=1.0)
            s.lines("pp", list(zip(pts[:-1], pts[1:])), colour=NET_COL[wr.net], check=False, width_mm=0.55)
        R(f"strip{col}", s, UNDER, up=(0, -1, 0), fit=(300, 340), line=0.4, outline=1.2)
    _sm.__name__ = f"strip{_c}"
    scene(_sm)


for _n in PD.POD_NAMES:
    def _fin(name=_n):
        s = pod_scene(name, "u2", holes=False, decals=False)
        iso_render(f"fin_{name.lower()}", s, fit=(330, 230), d=(-0.45, -1, 1.1))
    _fin.__name__ = f"fin_{_n.lower()}"
    scene(_fin)


# ------------------------------------------------------------------ the TH lead: the SHT45 end, the gland order
@scene
def sht_lead():
    """The SHT45 #6174 with the lead's four cores soldered to its own header pads (no header): each core in from the
    back (bare face), soldered on the front, 3Vo left empty. Seen straight at the front (the PTFE cap's face)."""
    pod = PODS_["TH"]
    s = r3d.Scene()
    parts, anc = M.breakout("sht45")
    place(s, "sht", parts, anc)
    M.breakout_silk(s, "sht45", "sht_board")
    pads = dict(zip(M.S.val("sht45_pins"), M.hdr_pads("sht45")))
    fil = []
    for k, c in enumerate(pod.lead.conductors):
        x, y = pads[c.pad]
        pts = [(x, y, M.PCB + 0.6), (x, y, -1.5), (x, y - 2.0, -3.0), (x, -8.0, -3.0), (10.16 + (k - 1.5) * 1.3, -16.0, -3.0)]
        s.add(f"L_{c.colour}", M.tube(pts[1:], 0.6), M.INS[c.colour], 0.7)
        s.add(f"T_{c.colour}", cq.Solid.makeCylinder(0.35, M.PCB + 0.6 + 1.5, cq.Vector(x, y, -1.5), cq.Vector(0, 0, 1)),
              M.COPPER, 0.3)
        fil.append(M.fillet_cone(x, y, M.PCB + 0.05, True, 0.85, 0.4, 0.55))
        s.anchor(f"pad:{c.pad}", (x, y, M.PCB + 0.3))
        mark(s, f"L:{c.colour}", (x + 0.0, -6.0, -3.0 + 0.6), f"L_{c.colour}")
    s.add("sfil", cq.Compound.makeCompound(fil), M.TIN, 0.4)
    s.anchor("pad:3Vo", (*pads["3Vo"], M.PCB + 0.05))
    s.add("jacket", cq.Solid.makeCylinder(2.0, 14.0, cq.Vector(10.16, -16.0, -3.0), cq.Vector(0, -1, 0)), M.JACKET)
    mark(s, "jacket", (10.16, -24.0, -1.0), "jacket")
    R("sht_lead", s, TOP, up=(0, 1, 0), fit=(260, 300), line=0.35)


@scene
def sht_lead_iso():
    pod = PODS_["TH"]
    s = r3d.Scene()
    parts, anc = M.breakout("sht45")
    place(s, "sht", parts, anc)
    M.breakout_silk(s, "sht45", "sht_board")
    pads = dict(zip(M.S.val("sht45_pins"), M.hdr_pads("sht45")))
    fil = []
    for k, c in enumerate(pod.lead.conductors):
        x, y = pads[c.pad]
        pts = [(x, y, -1.5), (x, y - 2.0, -3.0), (x, -8.0, -3.0), (10.16 + (k - 1.5) * 1.3, -16.0, -3.0)]
        s.add(f"L_{c.colour}", M.tube(pts, 0.6), M.INS[c.colour], 0.7)
        s.add(f"T_{c.colour}", cq.Solid.makeCylinder(0.35, M.PCB + 0.6 + 1.5, cq.Vector(x, y, -1.5), cq.Vector(0, 0, 1)),
              M.COPPER, 0.3)
        fil.append(M.fillet_cone(x, y, M.PCB + 0.05, True, 0.85, 0.4, 0.55))
    s.add("sfil", cq.Compound.makeCompound(fil), M.TIN, 0.4)
    s.add("jacket", cq.Solid.makeCylinder(2.0, 14.0, cq.Vector(10.16, -16.0, -3.0), cq.Vector(0, -1, 0)), M.JACKET)
    mark(s, "back", (20.0, 12.0, 0.0), "sht_board")
    R("sht_lead_iso", s, (-0.3, -0.7, -0.75), up=(0, 0, 1), fit=(260, 220), line=0.32)


@scene
def th_gland():
    """The TH lead's pod end and the TH box's second PG-7, in threading order along the lead: the dome nut first, then
    the gland body (in the box's bottom wall, its lock nut inside), the stripped cores last."""
    s = r3d.Scene()
    L = 120.0
    s.add("jacket", cq.Solid.makeCylinder(2.0, L - 40, cq.Vector(0, 0, 0), cq.Vector(1, 0, 0)), M.JACKET)
    for k, col in enumerate(("red", "black", "yellow", "blue")):
        dy = (k - 1.5) * 1.3
        pts = [(L - 41, dy * 0.4, 0), (L - 34, dy, 0), (L - 3, dy * 1.6, 0)]
        s.add(f"core_{col}", M.tube(pts, 0.6), M.INS[col], 0.7)
        s.add(f"tip_{col}", cq.Solid.makeCylinder(0.35, 3.0, cq.Vector(L - 3, dy * 1.6, 0), cq.Vector(1, 0, 0)),
              M.COPPER, 0.4)
    g = {nm: (shp, col) for nm, shp, col in M.gland_pg7()}
    # the gland's axis is +y in models_p: turn it onto +x (dome toward the SHT45 end, -x)
    def onx(shp, x):
        return shp.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90).translate(cq.Vector(x, 0, 0))
    th, L1 = M.S.val("gland_pg7")[0], M.S.val("gland_pg7")[1]
    s.add("dome", onx(g["gdome"][0], 30.0), g["gdome"][1], 0.9)
    s.add("body", onx(g["gbody"][0], 72.0), g["gbody"][1], 0.9)
    s.add("lock", onx(g["glock"][0], 72.0), g["glock"][1], 0.9)
    s.anchor("dome", (30.0 - (L1 + 9), 0, 6.0))
    s.anchor("body", (72.0 - (L1 + 1.5), 0, 6.5))
    s.anchor("lock", (72.0 - 1.8, 0, 6.5))
    s.anchor("cores", (L - 12, 0, 0.8))
    s.anchor("jacket", (8.0, 0, 2.0), on="jacket")
    R("th_gland", s, (0.0, -1.0, 0.55), fit=(470, 140), line=0.32)


# ------------------------------------------------------------------ the port cable
CABLE_L = 150.0


def _cable_scene(plugs, glands_at):
    """The port cable drawn short (its two ends), each end through its gland: pod end at x 0 (left), TX end at the right.
    plugs: draw the crimped plugs. glands_at: the gland body positions along the cable from each end."""
    s = r3d.Scene()
    s.add("cable", cq.Solid.makeCylinder(2.0, CABLE_L, cq.Vector(0, 0, 0), cq.Vector(1, 0, 0)), M.JACKET)
    g = {nm: (shp, col) for nm, shp, col in M.gland_pg7()}
    for end, (x, sgn) in (("pod", (0.0, 1)), ("tx", (CABLE_L, -1))):
        for nm in ("gdome", "gbody"):
            shp = g[nm][0].rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90 if sgn < 0 else -90)
            s.add(f"{end}_{nm}", shp.translate(cq.Vector(x + sgn * glands_at, 0, 0)), g[nm][1], 0.9)
        s.anchor(f"{end}_gland", (x + sgn * (glands_at + 3), 0, M.S.val("gland_pg7")[0] / 2), on=f"{end}_gbody")
        if plugs:
            parts, anc = M.plug()
            pw, ph = M.S.val("plug_6p")[:2]
            pl_ = M.S.val("plug_6p")[3]
            place(s, f"{end}P", parts, anc, -90 if sgn > 0 else 90, (x - sgn * pl_, 0, -ph / 2))
            s.anchor(f"{end}_plug", (x - sgn * 6.0, 0, ph / 2 + 0.2))
        else:
            s.anchor(f"{end}_end", (x, 0, 2.0))
    return s


@scene
def cab_glands():
    R("cab_glands", _cable_scene(False, 22.0), (0.0, -1.0, 0.6), fit=(500, 120), line=0.32)


@scene
def cab_crimped():
    R("cab_crimped", _cable_scene(True, 22.0), (0.0, -1.0, 0.6), fit=(500, 120), line=0.32)


@scene
def plug_face():
    """A crimped plug held tip UP, its gold contacts toward you, latch away: contact 1 on the LEFT (TIA-968)."""
    s = r3d.Scene()
    parts, anc = M.plug()
    place(s, "P", parts, anc)
    s.add("cable", cq.Solid.makeCylinder(2.0, 18, cq.Vector(0, 13.34, 3.3), cq.Vector(0, 1, 0)), M.JACKET)
    R("plug_face", s, (0, 0, 1), up=(0, -1, 0), fit=(150, 200), line=0.35)


# ------------------------------------------------------------------ which anchors each page's leaders need
SCENE_MARKS = {
    "p_eep": ["eeprom_24lc32:qtR", "eeprom_24lc32:hdr", "eeprom_24lc32:chip"],
    "p_ltr": ["ltr390:qtR", "ltr390:hdr", "ltr390:sensor"],
    "p_bmp": ["bmp581:qtR", "bmp581:hdr", "bmp581:sensor"],
    "p_sht": ["sht45:qtR", "sht45:hdr", "sht45:sensor"],
    "p_bob": ["bob:tab", "bob:jack", "bob:hdr"],
    "p_jp1": ["jp:jp1", "jp:shunt"],
    "bob_kit": ["bob:tab", "bob:score", "bob:jack", "bob:hdr"], "bob_snap": ["bob:tab", "bob:score_top"],
    "bob_ready": ["bob:jfil", "bob:hdr_bot", "bob:hpin_lo", "bob:peg"], "bob_top": ["bob:hfil", "bob:jack"],
    "hdr_eep": ["eep:hfil", "eep:hdr", "eep:hpin_lo"], "hdr_ltr": ["ltr:hfil", "ltr:hdr"],
    "hdr_bmp": ["bmp:hfil", "bmp:hdr"],
    "sht_lead": [f"L:{c}" for c in ("red", "black", "yellow", "blue")] + ["jacket"],
    "sht_lead_iso": ["back"],
}
for _c in (14, 15):
    for _gi, _g in enumerate(UGROUPS):
        SCENE_MARKS[f"u{_c}_{_gi + 1}"] = [f"w{n}m" for n in _g]
    SCENE_MARKS[f"t{_c}_low"] = ["R1:body", "JP1:top"]
    SCENE_MARKS[f"i{_c}_low"] = ["R1:body", "JP1:shunt"]
    SCENE_MARKS[f"t{_c}_jack"] = ["J1:jack", "J1:hfil"]
    SCENE_MARKS[f"i{_c}_jack"] = ["J1:mouth"]
    SCENE_MARKS[f"t{_c}_eep"] = ["U1:chip", "U1:qtR", "U1:qtL"]
    SCENE_MARKS[f"i{_c}_eep"] = ["U1:chip"]
for _n in PD.POD_NAMES:
    k = _n.lower()
    if _n == "TH":
        SCENE_MARKS[f"t_{k}_u2"] = [f"L:{c}" for c in ("red", "black", "yellow", "blue")] + ["L:jacket"]
        SCENE_MARKS[f"i_{k}_u2"] = ["L:jacket"]
    else:
        SCENE_MARKS[f"t_{k}_u2"] = ["U2:sensor", "U2:qtR"]
        SCENE_MARKS[f"i_{k}_u2"] = ["U2:sensor"]
    SCENE_MARKS[f"fin_{k}"] = ["J1:mouth", "U1:chip", "JP1:shunt"] + (["L:jacket"] if _n == "TH" else ["U2:sensor"])


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if len(names) != 1:
        sys.exit("render ONE scene per process: scenes_p.py NAME   (scenes_p.py list)")
    MARK.update(SCENE_MARKS.get(names[0], []))
    SCENES[names[0]]()
