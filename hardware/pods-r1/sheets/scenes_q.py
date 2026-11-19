"""Session Q (the printed boxes, the shield and the installation) illustrations, every object from real 3D geometry:
  the pod boxes   box/podbox.py body() and lid() (CadQuery), drawn with the TX sheets' r3d (OpenCascade hidden lines);
  the pod boards  Session P's models (scenes_p.pod_scene: layout/pods.py placements), moved into the box frame;
  loose parts     models_q.py (insert, screws, the PG-7 #762 gland as supplied, cord, window disc, ties);
  the shield      its meshes (shield/assemble.py assembled(), shield/remix.py cap_remixed(), arm_remixed() and the
                  placements box_pose(), uv_mount(), arm_mount(), lead_hole(), th_lead_path()), drawn with mrender.py
                  (the same look, from the triangles). The shield's licence is unknown: these SVGs stay in svg/ and the
                  PDF in out/ (both gitignored).
The box frame is the board frame (podbox): z = 0 on the Perma-Proto's component face; Session P's scenes have the board's
underside at z = 0, so a pod board moves down by its thickness T. The shield frame is assemble.py's (Z up, Z = 0 on the
arm's pocket floor); the pod boxes go into it by remix.box_pose().

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  $CADPY -B scenes_q.py NAME          (scenes_q.py list: every scene; render_q.sh renders them all)
"""
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PODS = HERE.parent
REPO = PODS.parent.parent
for p in (HERE, PODS / "shield", PODS / "box", PODS / "layout", PODS, REPO / "hardware" / "tx-stack-r1" / "sheets" / "session1" / "v2"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import r3d                              # noqa: E402  (TX sheets, read-only)
import mrender as MR                    # noqa: E402
import models_p as M                    # noqa: E402
import models_q as Q                    # noqa: E402
import scenes_p as SP                   # noqa: E402  (Session P: the pod boards)
import podbox as PB                     # noqa: E402
import pods as PD                       # noqa: E402
import permaproto as PPM                # noqa: E402
import sources as S                     # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
T = M.T
POD = ("TH", "BARO", "UV")
L1 = S.val("gland_pg7")[1]
GLAND_DROP = S.val("gland_pg7")[2] + S.val("gland_pg7")[3]     # body + cap outside the wall (remix.GLAND_DROP, its keep-out)
DOME_END = L1 + 14.5 - (L1 - Q.SEAL_T)                          # the drawn gland's dome end past the wall (models_p.gland_pg7)
MOUNT_L = S.val("pod_mount_screw")[1]
LID_L = S.val("pod_screw")[1]


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    s.placed_by("box frame (podbox) / part frames, right-handed", np.eye(3))
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


def MRr(name, s, d, up=(0, 0, 1), fit=(300, 220), **kw):
    s.placed_by("shield frame (assemble.py), right-handed; boxes by remix.box_pose (det +1)", np.eye(3))
    MR.render(s, OUT / name, d, up=up, fit=fit, **kw)


def add_all(s, prefix, parts, w=0.9):
    for nm, shp, col in parts:
        s.add(f"{prefix}_{nm}", shp, col, w)


def turn(shp, R_, t=(0, 0, 0)):
    """A CadQuery shape moved by world = R_ @ p + t (R_ a proper rotation: det +1, checked)."""
    R_ = np.asarray(R_, float)
    assert abs(np.linalg.det(R_) - 1) < 1e-6, "turn() takes rotations only (no mirror)"
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    tr = gp_Trsf()
    tr.SetValues(*[float(v) for row in np.c_[R_, np.asarray(t, float)] for v in row])
    w = shp.wrapped if hasattr(shp, "wrapped") else shp
    return cq.Shape.cast(BRepBuilderAPI_Transform(w, tr, True).Shape())


def axis_to(v):
    """A rotation taking +z onto unit vector v."""
    z = np.asarray(v, float) / np.linalg.norm(v)
    a = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(a, z)
    x /= np.linalg.norm(x)
    return np.c_[x, np.cross(z, x), z]


def shift_scene(s, v):
    """Move every part, anchor and decal of an r3d scene by v (Session P's board frame -> the box frame)."""
    v = np.asarray(v, float)
    s.parts = [(n, cq.Shape.cast(shp).translate(cq.Vector(*v)).wrapped, c, w) for n, shp, c, w in s.parts]
    s.anchors = {k: np.asarray(p) + v for k, p in s.anchors.items()}
    for dc in s.decals:
        if dc["kind"] == "text":
            dc["o"] = dc["o"] + v
        else:
            dc["segs"] = [(a + v, b + v) for a, b in dc["segs"]]
    return s


# ------------------------------------------------------------------ the boxes (box frame)
def d_(name):
    return PB.dims(name)


def lid_top(d):
    """The lid's outer top face (z, box frame): the UV crown's apex flat, or a box lid's outer face."""
    return d.get("z_flat", d["z_rim"] + d["lid_t"])


def crown_pt(d, r, deg, z):
    """A point on a circle of radius r about the UV crown's axis, at deg (box frame, from +x) and height z."""
    cx, cy = d["axis"]
    return (cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg)), z)


def dome_pt(d, frac, deg, lift=0.0):
    """A point on the UV crown's dome (outer face), at frac of its radius out from the axis, at deg (box frame)."""
    z = min(d["z_joint"] + (d["apex"] - d["z_joint"]) * math.sqrt(max(0.0, 1 - frac * frac)), d["z_flat"])
    return crown_pt(d, frac * d["r_out"], deg, z + lift)


def front_slot(d, view):
    """The bayonet entry slot whose angle is nearest the viewer's side (box frame, degrees)."""
    va = math.degrees(math.atan2(view[1], view[0]))
    return min(PB._bayonet_angles(d), key=lambda a: abs((a - va + 180) % 360 - 180))


def banded(d, lid):
    """The UV crown's dome lid as drawn by r3d: the same solid cut into horizontal bands, so the hidden-line drawing
    shades the smooth dome in steps (one smooth face draws as one flat tone). Drawing only: the STL stays smooth."""
    cx, cy = d["axis"]
    bb = lid.BoundingBox()
    zs = [bb.zmin - 1] + [d["z_joint"] + (d["apex"] - d["z_joint"]) * f for f in (0.45, 0.7, 0.86, 0.95)] + [bb.zmax + 1]
    pieces = []
    for z0, z1 in zip(zs, zs[1:]):
        slab = cq.Solid.makeBox(bb.xlen + 20, bb.ylen + 20, z1 - z0, cq.Vector(bb.xmin - 10, bb.ymin - 10, z0))
        pieces.append(lid.intersect(slab))
    return cq.Compound.makeCompound(pieces)


def uv_lid(d=None):
    d = d or d_("UV")
    return banded(d, PB.lid("UV"))


def lid_turned(d, deg, lift=0.0):
    """The UV crown's lid turned deg about its axis (from its locked position) and lifted (banded, as drawn)."""
    cx, cy = d["axis"]
    return banded(d, PB.lid("UV").rotate(cq.Vector(cx, cy, 0), cq.Vector(cx, cy, 1), deg)).translate(cq.Vector(0, 0, lift))


def corner(name, x, y):
    """A lug's corner code in the box frame: B (gland end, y0) / T (far end); L (x0) / R (x1)."""
    d = d_(name)
    return ("B" if y < (d["y0"] + d["y1"]) / 2 else "T") + ("L" if x < (d["x0"] + d["x1"]) / 2 else "R")


def add_body(s, name, lid=False, lid_lift=0.0, prefix=None):
    p = prefix or name.lower()
    s.add(f"{p}_body", PB.body(name), Q.PETG, 1.0)
    if lid:
        shp = uv_lid() if name == "UV" else PB.lid(name)
        s.add(f"{p}_lid", shp.translate(cq.Vector(0, 0, lid_lift)), Q.PETG, 1.0)


def bore_anchors(s, name, which, drawn=True):
    """Hole anchors on the insert bores: which = 'rim' (the lid inserts, from the rim) or 'back' (the mount inserts)."""
    d = d_(name)
    if which == "rim":
        for x, y in d["lugs"]:
            s.hole(f"rim:{corner(name, x, y)}", (x, y, d["z_rim"]), drawn)
    else:
        for x, y in d["mount_lugs"]:
            s.hole(f"back:{corner(name, x, y)}", (x, y, d["z_bo"]), drawn)
        for k, (x, y) in enumerate(d["floor_bosses"]):
            s.hole(f"boss:{k + 1}", (x, y, d["z_bo"]), drawn)


def opening(name, kind):
    return next((c, a) for k, c, a in PB.openings(name) if k == kind)


def face_anchors(s, name, view):
    d = d_(name)
    if name == "UV":                     # the crown: a drum, its spigot (the lid's seat), floor bosses, a gland in the wall
        p = "uv_body"
        x, y = d["floor_bosses"][0]
        gx, gy, gz = opening(name, "gland")[0]
        s.anchor("op:gland", (gx, d["axis"][1] - d["r_out"], gz))
        if view == "front":
            s.anchor("spigot", crown_pt(d, d["r_sp"], 200, d["z_joint"]), on=p)
            s.anchor("boss", (x, y, d["z_bo"] + d["boss_depth"]))
            hx, hy, _dr = PB.board_holes()[0]
            s.anchor("standoff", (hx, hy, -d["t"]))
        else:
            s.anchor("floor", crown_pt(d, 14.0, 150, d["z_bo"]), on=p)
            s.anchor("boss", (x, y, d["z_bo"]))
        return
    xm, ym = (d["x0"] + d["x1"]) / 2, (d["y0"] + d["y1"]) / 2
    p = f"{name.lower()}_body"
    front = view == "front"
    lx, ly = d["lugs"][1]
    s.anchor("rim", (d["x1"] + PB.WALL / 2, ym + 12, d["z_rim"]), on=p if front else None)
    s.anchor("back", (xm + 10, ym, d["z_bo"]), on=None if front else p)
    s.anchor("lug", (lx - 3.0, ly, d["z_rim"] if front else d["z_bo"]), on=p)
    if name == "UV":
        s.anchor("end", (xm + 10, d["y0"] - PB.WALL, (d["z_bo"] + d["z_rim"]) / 2), on=p if front else None)
    else:
        s.anchor("bottom", (xm + 14, d["y0"] - PB.WALL, d["z_bo"] + 2.5), on=p)
    for k, c, a in PB.openings(name):
        if k != "window":
            s.anchor(f"op:{k}", c)


UP = {"TH": (0, 1, 0), "BARO": (0, 1, 0), "UV": (0, 0, 1)}
FRONT = {"TH": (-0.45, -0.55, 1.0), "BARO": (-0.45, -0.55, 1.0), "UV": (-0.35, -0.9, 0.8)}
BACK = {"TH": (0.45, -0.55, -1.0), "BARO": (0.45, -0.55, -1.0), "UV": (0.25, -0.55, -1.0)}


# ------------------------------------------------------------------ parts as supplied (cover)
for _n in POD:
    def _pbox(name=_n):
        s = r3d.Scene()
        d = d_(name)
        add_body(s, name)
        if name == "UV":                 # the crown: the dome lid beside the body, both upright
            s.add("uv_lid", uv_lid(d).translate(cq.Vector(2 * d["r_out"] + 12, 0, d["z_bo"] - d["z_ledge"])), Q.PETG, 1.0)
            R("q_p_box_uv", s, (-0.3, -1.0, 0.45), fit=(170, 130), line=0.3)
            return
        w = d["x1"] - d["x0"] + 2 * PB.WALL + 16
        xm = (d["x0"] + d["x1"]) / 2
        lid = PB.lid(name).rotate(cq.Vector(xm, 0, d["z_rim"]), cq.Vector(xm, 1, d["z_rim"]), 180)
        lid = lid.translate(cq.Vector(w + 6, 0, -d["z_rim"] - d["lid_t"] + d["z_bo"] + d["lid_t"]))
        s.add(f"{name.lower()}_lid", lid, Q.PETG, 1.0)
        R(f"q_p_box_{name.lower()}", s, (-0.45, -0.9, 0.9), fit=(170, 130), line=0.3)
    _pbox.__name__ = f"q_p_box_{_n.lower()}"
    scene(_pbox)


@scene
def q_p_insert():
    s = r3d.Scene()
    for k in range(3):
        s.add(f"ins{k}", Q.insert_m3().translate(cq.Vector(k * 7.0, 0, 0)), Q.BRASS, 0.8)
    R("q_p_insert", s, (-0.4, -1, 0.7), fit=(130, 90), line=0.35)


@scene
def q_p_gland():
    s = r3d.Scene()
    add_all(s, "g", Q.gland())
    R("q_p_gland", s, (-0.5, 0.35, 1.0), up=(0, 1, 0), fit=(110, 120), line=0.35)


@scene
def q_p_cord():
    s = r3d.Scene()
    s.add("cord", Q.cord_coil(), Q.CORD, 0.8)
    R("q_p_cord", s, (0, -0.55, 1.0), fit=(140, 110), line=0.35)


for _L, _nm in ((LID_L, "m3x8"), (MOUNT_L, "m3x10")):
    def _ps(L=_L, nm=_nm):
        s = r3d.Scene()
        for k in range(2):
            s.add(f"s{k}", Q.pan_screw(L).translate(cq.Vector(k * 9.0, 0, 0)), Q.STEEL, 0.8)
        R(f"q_p_{nm}", s, (-0.4, -1, 0.55), fit=(110, 110), line=0.35)
    _ps.__name__ = f"q_p_{_nm}"
    scene(_ps)


@scene
def q_p_m25():
    s = r3d.Scene()
    for k in range(2):
        s.add(f"s{k}", Q.pan_screw(S.val("ltr_screw")[1], S.val("ltr_screw")).translate(cq.Vector(k * 8.0, 0, 0)), Q.STEEL, 0.8)
    R("q_p_m25", s, (-0.4, -1, 0.55), fit=(110, 110), line=0.35)


@scene
def q_p_window():
    s = r3d.Scene()
    s.add("disc", Q.window_disc(), M.PTFE, 0.8)
    s.add("eptfe", Q.eptfe_patch().translate(cq.Vector(24, 0, 0)), Q.EPTFE, 0.8)
    s.anchor("disc", (0, -5, S.val("uv_window")[2]), on="disc")
    s.anchor("eptfe", (24, -3, S.val("baro_eptfe")[1]), on="eptfe")
    R("q_p_window", s, (-0.2, -1, 0.9), fit=(150, 90), line=0.35)


@scene
def q_p_tie():
    s = r3d.Scene()
    for k in range(2):
        s.add(f"t{k}", Q.tie_loose(100).translate(cq.Vector(0, k * 9.0, 0)), Q.TIE, 0.6)
    R("q_p_tie", s, (0, -0.5, 1.0), fit=(160, 60), line=0.3)


def _shield():
    import assemble as A
    import remix as X
    return A, X


@scene
def q_p_cap():
    A, X = _shield()
    s = MR.Scene()
    s.add("cap", X.cap_remixed(), Q.SHIELD)
    MRr("q_p_cap", s, (0.6, -0.9, 0.75), fit=(150, 120), line=0.35)


@scene
def q_p_arm():
    A, X = _shield()
    s = MR.Scene()
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    MRr("q_p_arm", s, (0.7, -0.9, 0.6), fit=(150, 130), line=0.35)


# ------------------------------------------------------------------ know the three boxes
for _n in POD:
    def _ff(name=_n):
        s = r3d.Scene()
        add_body(s, name)
        face_anchors(s, name, "front")
        R(f"q_face_{name.lower()}_front", s, FRONT[name], up=UP[name], fit=(170, 220), line=0.32)

    def _fb(name=_n):
        s = r3d.Scene()
        add_body(s, name)
        face_anchors(s, name, "back")
        R(f"q_face_{name.lower()}_back", s, BACK[name], up=UP[name], fit=(170, 220), line=0.32)
    _ff.__name__, _fb.__name__ = f"q_face_{_n.lower()}_front", f"q_face_{_n.lower()}_back"
    scene(_ff)
    scene(_fb)


# ------------------------------------------------------------------ heat-set inserts
for _n in POD:
    def _ir(name=_n):
        s = r3d.Scene()
        add_body(s, name)
        bore_anchors(s, name, "rim")
        R(f"q_ins_{name.lower()}_rim", s, (0, 0, 1), up=(0, 1, 0), fit=(220, 300), line=0.35, outline=1.1)

    def _ib(name=_n):
        s = r3d.Scene()
        add_body(s, name)
        bore_anchors(s, name, "back")
        if name == "UV":
            gx, gy, gz = opening(name, "gland")[0]
            s.anchor("op:gland", (gx, d_(name)["axis"][1] - d_(name)["r_out"], gz))
        R(f"q_ins_{name.lower()}_back", s, (0, 0, -1), up=(0, 1, 0), fit=(220, 300), line=0.35, outline=1.1)

    def _il(name=_n):
        """One corner lug (the far end, x1 side): an insert over its rim bore, square, before the iron pushes it in."""
        s = r3d.Scene()
        d = d_(name)
        add_body(s, name)
        if name == "UV":                 # a floor boss from below (box turned over): the insert under its bore, pointing up
            x, y = d["floor_bosses"][0]
            z = d["z_bo"]
            flip = np.diag([1.0, -1.0, -1.0])
            s.add("ins", turn(Q.insert_m3(), flip, (x, y, z - 4.0)), Q.BRASS, 0.8)
            u = np.array((0.55, -0.9)) / np.hypot(0.55, 0.9)
            s.anchor("ins", (x + u[0] * Q.INSERT_D / 2, y + u[1] * Q.INSERT_D / 2, z - 4.0 - 1.5), on="ins")
            s.anchor("bore", (x, y, z))
            s.anchor("lug", (x + 4.0, y + 3.0, z), on="uv_body")
            R("q_ins_uv_lug", s, (0.55, -0.9, -0.75), up=(0, 0, -1), fit=(200, 200), line=0.35,
              crop=((x, y, z - 1.0), 13.0, 13.0))
            return
        x, y = d["lugs"][3]
        s.add("ins", Q.insert_m3().translate(cq.Vector(x, y, d["z_rim"] + 4.0)), Q.BRASS, 0.8)
        s.add("ins2", Q.insert_m3().translate(cq.Vector(x, y, d["z_rim"] - Q.INSERT_L)), Q.BRASS, 0.8)
        u = np.array((0.55, -0.9)) / np.hypot(0.55, 0.9)
        s.anchor("ins", (x + u[0] * Q.INSERT_D / 2, y + u[1] * Q.INSERT_D / 2, d["z_rim"] + 4.0 + 1.5), on="ins")
        s.anchor("bore", (x, y, d["z_rim"]))
        s.anchor("lug", (x + 2.9, y, d["z_rim"]), on=f"{name.lower()}_body")
        R(f"q_ins_{name.lower()}_lug", s, (0.55, -0.9, 0.75), up=(0, 0, 1), fit=(200, 200), line=0.35,
          crop=((x, y, d["z_rim"] + 1.0), 13.0, 13.0))
    _ir.__name__, _ib.__name__, _il.__name__ = f"q_ins_{_n.lower()}_rim", f"q_ins_{_n.lower()}_back", f"q_ins_{_n.lower()}_lug"
    if _n != "UV":                       # the crown has no rim inserts: its lid is a bayonet
        scene(_ir)
    scene(_ib)
    scene(_il)


# ------------------------------------------------------------------ the PG-7 #762 gland
def _gland_x(parts, x=0.0):
    """Turn the gland's +y axis onto -x (dome to the left, thread end to the right), moved x along it."""
    return [(nm, shp.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90).translate(cq.Vector(x, 0, 0)), col)
            for nm, shp, col in parts]


def _gland_anchors(s, lock_off=0.0):
    th, L1_, nut, L3 = S.val("gland_pg7")[:4]
    s.anchor("dome", (-(L1_ + 9.0), 0, nut * 0.42))
    s.anchor("hex", (-(L1_ + 1.5), 0, nut / 2 * 0.86))
    s.anchor("seal", (-(L1_ - Q.SEAL_T / 2), 0, 7.2))
    s.anchor("lock", (lock_off - 1.6, 0, nut / 2 * 0.86))
    s.anchor("thread", (-(L1_ - 3.0), 0, th / 2))


@scene
def q_gland_sup():
    s = r3d.Scene()
    add_all(s, "g", _gland_x(Q.gland()))
    _gland_anchors(s)
    R("q_gland_sup", s, (0.0, -1.0, 0.5), fit=(230, 140), line=0.35)


@scene
def q_gland_off():
    s = r3d.Scene()
    off = 12.0
    add_all(s, "g", _gland_x(Q.gland(lock_off=off)))
    _gland_anchors(s, lock_off=off)
    R("q_gland_off", s, (0.0, -1.0, 0.5), fit=(300, 140), line=0.35)


def add_glands(s, name, prefix="gl"):
    for k, c, a in PB.openings(name):
        if k in ("gland", "lead_gland"):
            add_all(s, f"{prefix}{k}", Q.gland_in_wall(c, a))


def gland_scene(name, fitted=True, patch=False):
    s = r3d.Scene()
    add_body(s, name)
    if fitted:
        add_glands(s, name)
    d = d_(name)
    for k, c, a in PB.openings(name):
        if k == "window":
            continue
        s.anchor(f"op:{k}", c if name != "UV" else (c[0], d["axis"][1] - d["r_out"], c[2] + 4.0))
        if fitted and k in ("gland", "lead_gland"):
            ca, aa = np.asarray(c), np.asarray(a)
            nut = S.val("gland_pg7")[2]
            side = np.array((0, 0, 1.0))
            s.anchor(f"dome:{k}", tuple(ca + aa * (DOME_END - 5.5) + side * nut * 0.95 / 2 * 0.86))
            inner = ca - aa * PB.WALL
            s.anchor(f"lock:{k}", tuple(inner - aa * 1.2 + side * nut / 2 * 0.86))
    if name == "BARO":
        (c, a) = opening(name, "vent")
        sd, st = d["seat"]
        inner = np.asarray(c) - np.asarray(a) * PB.WALL
        if patch:
            pt = S.val("baro_eptfe")[1]
            s.add("eptfe", Q.eptfe_patch().rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90)
                  .translate(cq.Vector(inner[0], inner[1] + st - 0.01 + pt, inner[2])), Q.EPTFE, 0.7)
            s.anchor("eptfe", (inner[0] + 3.0, inner[1] + st + pt, inner[2] + 3.0))
        bx0, bx1, by0, by1, bz0, bz1 = PB._baffle_box(d)
        s.anchor("baffle", ((bx0 + bx1) / 2 + 4, by1, bz1 - 3.0))
    return s


for _n in POD:
    def _gh(name=_n):
        s = gland_scene(name, fitted=False)
        R(f"q_gl_{name.lower()}_holes", s, (0, -1, 0), up=(0, 0, 1), fit=(260, 160), line=0.35)

    def _go(name=_n):
        s = gland_scene(name)
        R(f"q_gl_{name.lower()}_out", s, (-0.35, -1, 0.55), up=(0, 0, 1), fit=(260, 220), line=0.32)

    def _gi(name=_n):
        s = gland_scene(name, patch=(name == "BARO"))
        d = d_(name)
        if name == "UV":                 # from above, into the open drum: the locknut on its flat land
            gx, gy, gz = opening(name, "gland")[0]
            R("q_gl_uv_in", s, (0.0, 0.75, 1), up=(0, 0, 1), fit=(260, 220), line=0.32,
              crop=((gx, d["y_land"] + 4, gz), 26.0, 20.0))
        else:
            R(f"q_gl_{name.lower()}_in", s, (0.0, 0.75, 1), up=(0, 0, 1), fit=(260, 220), line=0.32,
              crop=(((d["x0"] + d["x1"]) / 2, d["y0"] + 6, (d["z_bi"] + d["z_rim"]) / 2), (d["x1"] - d["x0"]) / 2 + 6, 20.0))
    _gh.__name__, _go.__name__, _gi.__name__ = f"q_gl_{_n.lower()}_holes", f"q_gl_{_n.lower()}_out", f"q_gl_{_n.lower()}_in"
    scene(_gh)
    scene(_go)
    scene(_gi)


# ------------------------------------------------------------------ the UV window
@scene
def q_win_iso():
    s = r3d.Scene()
    d = d_("UV")
    s.add("uv_lid", uv_lid(d), Q.PETG, 1.0)
    w = d["window"]
    z1 = lid_top(d)
    s.add("disc", Q.window_disc().translate(cq.Vector(*w["c"], z1 + 9.0)), M.PTFE, 0.8)
    s.anchor("disc", (w["c"][0] - S.val("uv_window")[1] / 2 + 1.0, w["c"][1], z1 + 9.0 + S.val("uv_window")[2]), on="disc")
    s.anchor("recess", (w["c"][0] + w["recess_d"] / 2 - 0.6, w["c"][1] - 3.0, z1 - w["depth"]))
    s.anchor("aperture", (w["c"][0], w["c"][1] - w["aperture"] / 2, z1 - d["lid_t"]))
    R("q_win_iso", s, (-0.35, -0.9, 0.9), fit=(300, 230), line=0.32, crop=((*w["c"], z1 - 3.0), 30.0, 24.0))


@scene
def q_win_top():
    s = r3d.Scene()
    d = d_("UV")
    add_body(s, "UV", lid=True)
    w = d["window"]
    z1 = lid_top(d)
    s.add("disc", Q.window_disc().translate(cq.Vector(*w["c"], z1 - w["depth"])), M.PTFE, 0.8)
    s.anchor("disc", (w["c"][0] + 4.0, w["c"][1] + 4.0, z1), on="disc")
    s.anchor("lid", dome_pt(d, 0.7, -60), on="uv_lid")
    R("q_win_top", s, (0, 0, 1), up=(0, 1, 0), fit=(200, 300), line=0.35)


# ------------------------------------------------------------------ boards into their boxes
def plug_in_j1(s, name):
    """The port cable's crimped 6P6C plug in J1 (pushed 9 mm into the jack), its cable straight down the plug's axis
    and out through the port gland (box frame)."""
    d = d_(name)
    pw, ph, phl, pl = S.val("plug_6p")
    jack = next(b for b in PD.pod(name).part("J1").boxes if "87180" in b.what)
    tip = d["mouth"] + 9.0
    parts, anc = M.plug()
    z0 = jack.z0 + 1.0
    for nm, shp, col, w in parts:
        sh = cq.Shape.cast(shp.wrapped if hasattr(shp, "wrapped") else shp).rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 180).translate(cq.Vector(d["px"], tip, z0))
        s.add(f"plug_{nm}", sh, col, w)
    (c, a) = opening(name, "gland")
    end = tip - pl
    zc = z0 + ph / 2
    pts = [(d["px"], end + 0.5, zc), (c[0], c[1] + 4.0, c[2]), (c[0], c[1] - GLAND_DROP - 22.0, c[2])]
    s.add("cable", Q.tube(pts, 2.0), M.JACKET, 1.0)
    s.anchor("plug", (d["px"], end + 2.0, z0 + ph))
    s.anchor("cable", (pts[1][0], (pts[0][1] + pts[1][1]) / 2, pts[1][2] + 2.0))
    return pts


def th_lead_in_box(s):
    """The TH lead's pod end: the four cores from J10, J12, J13, J14 (Session P's add_lead route, soldered on the
    copper side) into the round jacket, which runs down past U1 to the lead gland and out (box frame)."""
    pod = PD.pod("TH")
    zj = 11.0
    cores = sorted(pod.lead.conductors, key=lambda c: PPM.HOLES[c.hole][0])
    for k, c in enumerate(cores):
        x, y = PPM.HOLES[c.hole]
        off = (k - 1.5) * 1.15
        pts = [(x, y, -T - 1.0), (x, y, 2.0), (x, y - 2.5, 6.0), (SP.LEAD_X + off, 30.0, zj), (SP.LEAD_X + off, 24.0, zj)]
        s.add(f"L_{c.colour}", M.tube(pts, 0.6), M.INS[c.colour], 0.7)
    (c, a) = opening("TH", "lead_gland")
    pts = [(SP.LEAD_X, 25.0, zj), (SP.LEAD_X, -14.0, zj), (c[0], c[1] + 6.0, c[2]), (c[0], c[1] - GLAND_DROP - 22.0, c[2])]
    s.add("L_jacket", Q.tube(pts, 2.0), M.JACKET, 1.0)
    s.anchor("L:jacket", (SP.LEAD_X, 5.0, zj + 2.0))
    s.anchor("L:out", (c[0], c[1] - GLAND_DROP - 12.0, c[2] + 2.0))


def uv_lead_in_box(s, rise=30.0):
    """The UV lead's board end: the four cores from J10, J12, J13, J14 (soldered on the copper side, as TH's) up into
    the round jacket, which rises out of the open drum toward the lid (box frame). Returns the jacket's top."""
    pod = PD.pod("UV")
    d = d_("UV")
    cores = sorted(pod.lead.conductors, key=lambda c: PPM.HOLES[c.hole][0])
    xs = [PPM.HOLES[c.hole] for c in cores]
    jx, jy = float(np.mean([p[0] for p in xs])), float(np.mean([p[1] for p in xs])) + 4.0
    zj = 9.0
    for k, c in enumerate(cores):
        x, y = PPM.HOLES[c.hole]
        off = (k - 1.5) * 1.15
        pts = [(x, y, -T - 1.0), (x, y, 2.0), (x, y + 1.5, 5.0), (jx + off, jy, zj)]
        s.add(f"L_{c.colour}", M.tube(pts, 0.6), M.INS[c.colour], 0.7)
    top = (jx, jy, d["z_joint"] + rise)
    s.add("L_jacket", Q.tube([(jx, jy, zj), (jx, jy, zj + 6.0), top], 2.0), M.JACKET, 1.0)
    s.anchor("L:out", (jx + 2.0, jy, d["z_joint"] + rise * 0.6))
    return top


def ltr_in_lid(s, lead=True, screws=True):
    """The LTR390 #4831 on its two bosses under the crown's dome (box frame, lid as it sits on the body): sensor UP
    under the window's aperture tube, two M2.5 x 6 up through its corner holes; its lead's cores off the header pads
    on the copper side, into the jacket hanging down into the drum."""
    import models_p as MP
    d = d_("UV")
    L_ = d["ltr"]
    sx, sy = S.val("ltr390_sensor")
    t = np.array((L_["c"][0] - sx, L_["c"][1] - sy, L_["z"] - MP.PCB))
    parts, anc = MP.breakout("ltr390")
    for nm, shp, col, w in parts:
        s.add(f"ltr_{nm}", turn(shp, np.eye(3), t), col, w)
    s.anchor("ltr", tuple(t + (3.0, 13.0, MP.PCB)))
    if screws:
        size = S.val("ltr_screw")
        for k, (x, y) in enumerate(L_["holes"]):
            s.add(f"m25_{k}", turn(Q.pan_screw(size[1], size), np.diag([1.0, -1.0, -1.0]), (x, y, L_["z"] - MP.PCB)),
                  Q.STEEL, 0.8)
            s.anchor(f"m25_{k}", (x + 1.0, y, L_["z"] - MP.PCB - 1.9))
    if lead:
        pads = dict(zip(S.val("ltr390_pins"), MP.hdr_pads("ltr390")))
        ends = []
        for k, c in enumerate(PD.pod("UV").lead.conductors):
            px, py = pads[c.pad]
            pts = [(px, py, MP.PCB + 0.5), (px, py, -0.6), (px, py - 1.0, -3.0), (10.0 + k * 1.0, 5.0, -6.0)]
            w_ = [tuple(np.array(p) + t) for p in pts]
            s.add(f"core_{c.colour}", M.tube(w_, 0.6), M.INS[c.colour], 0.6)
            ends.append(w_[-1])
        e = np.mean(ends, 0)
        s.add("ltr_jacket", Q.tube([tuple(e), tuple(e + (0, 0, -18.0))], 2.0), M.JACKET, 1.0)
        s.anchor("ltr_lead", tuple(e + (2.0, 0, -12.0)))


def board_screws(s):
    for k, (x, y, _dr) in enumerate(PPM.OUTLINE["mounting_holes"]):
        s.add(f"bscrew{k}", Q.pan_screw(LID_L).translate(cq.Vector(x, y, 0.0)), Q.STEEL, 0.8)
        s.anchor(f"bscrew{k}", (x + 1.2, y + 1.2, 2.4))


P_LEAD = ("L_red", "L_black", "L_yellow", "L_blue", "L_jacket")   # Session P's bench-pose lead (cores + jacket)


def bib_scene(name, holes=False):
    s = SP.pod_scene(name, "u2", holes=holes, decals=True)
    if name in ("TH", "UV"):             # in the box the lead takes its box route (th_ / uv_lead_in_box below): drop
        s.parts = [p for p in s.parts if p[0] not in P_LEAD]       # Session P's bench pose so it is drawn once
        for k in [k for k in s.anchors if k.startswith("L:")]:      # (its solder joints underneath, L_ufil, stay)
            s.anchors.pop(k)
            s.anchor_on.pop(k, None)
    shift_scene(s, (0, 0, -T))
    add_body(s, name)
    add_glands(s, name)
    board_screws(s)
    plug_in_j1(s, name)
    if name == "TH":
        th_lead_in_box(s)
    if name == "UV":
        uv_lead_in_box(s)
    return s


for _n in POD:
    def _bt(name=_n):
        s = bib_scene(name)
        s.anchor("standoff", (*PPM.OUTLINE["mounting_holes"][0][:2], -T))
        kw = {}
        if name == "UV":                 # the crown is wide: crop to the board, the plug and the gland
            w, h = S.val("permaproto_q")
            kw["crop"] = ((w / 2, h / 2 - 12.0, 0.0), w / 2 + 14.0, h / 2 + 26.0)
        R(f"q_bib_{name.lower()}_top", s, (0, 0, 1), up=(0, 1, 0), fit=(260, 380), line=0.32, outline=1.1, **kw)

    def _bi(name=_n):
        if name == "UV":                 # the lid upside down on the bench: the LTR390 onto its bosses, chip down
            s = r3d.Scene()
            d = d_(name)
            s.add("uv_lid", uv_lid(d), Q.PETG, 1.0)
            ltr_in_lid(s)
            L_ = d["ltr"]
            s.anchor("boss", (L_["holes"][1][0] + 2.5, L_["holes"][1][1], L_["z"] + 3.0))
            s.placed_by("box frame (podbox), the lid seen from below", np.eye(3))
            r3d.render(s, OUT / "q_bib_uv_iso", (0.35, -0.8, -1.0), up=(0, 1, 0), fit=(300, 300), line=0.3,
                       crop=((*L_["c"], L_["z"] - 6.0), 24.0, 24.0))
            return
        s = bib_scene(name)
        R(f"q_bib_{name.lower()}_iso", s, (-0.45, -0.7, 1.0), up=(0, 1, 0), fit=(300, 300), line=0.3)
    _bt.__name__, _bi.__name__ = f"q_bib_{_n.lower()}_top", f"q_bib_{_n.lower()}_iso"
    scene(_bt)
    scene(_bi)


# ------------------------------------------------------------------ the shunt check (TH drawn; the three are alike)
def _probe_points(s, name):
    pod = PD.pod(name)
    j1 = pod.part("J1")
    pcb = next(b for b in j1.boxes if "BOB-14021 PCB" in b.what)
    x, y = PPM.HOLES[j1.pins["2"]]
    s.anchor("probe:3v3", (x, y, pcb.z1 + 0.5))
    u1 = pod.part("U1")
    x, y = PPM.HOLES[u1.pins["WP"]]
    ub = next(b for b in u1.boxes if b.what.endswith("PCB"))
    s.anchor("probe:wp", (x, y, ub.z1 + 0.5))


@scene
def q_shunt_top():
    s = bib_scene("TH")
    _probe_points(s, "TH")
    c = PPM.HOLES["H4"]
    R("q_shunt_top", s, (0, 0, 1), up=(0, 1, 0), fit=(280, 300), line=0.35, outline=1.1,
      crop=((c[0] + 6.0, c[1] - 12.0, 0.0), 24.0, 28.0))


# ------------------------------------------------------------------ the O-ring cord and the lid
for _n in POD:
    def _or(name=_n):
        s = r3d.Scene()
        if name == "UV":                 # the crown: the cord round the BODY's spigot, below the bayonet slots
            d = d_(name)
            g = PB.groove(name)
            add_body(s, name)
            s.add("cord", Q.cord_in_groove(name), Q.CORD, 0.8)
            s.anchor("cord", crown_pt(d, d["r_sp"] - g["depth"] + g["cord"], 235, g["z"]), on="cord")
            R("q_oring_uv", s, (-0.35, -0.9, 0.45), up=(0, 0, 1), fit=(160, 230), line=0.32)
            return
        s.add(f"{name.lower()}_lid", PB.lid(name), Q.PETG, 1.0)
        s.add("cord", Q.cord_in_groove(name), Q.CORD, 0.8)
        d = d_(name)
        g = PB.groove(name)
        x, y = g["probes"][3]
        s.anchor("cord", (x, y + 10.0, d["z_rim"] - (g["cord"] - g["depth"])), on="cord")
        R(f"q_oring_{name.lower()}", s, (0, 0, -1), up=(0, 1, 0), fit=(160, 230), line=0.32)

    def _lid(name=_n):
        s = r3d.Scene()
        d = d_(name)
        if name == "UV":                 # the bayonet: the lid lifted over the body, its lugs over the entry slots
            add_body(s, name)
            s.add("uv_lid", lid_turned(d, -PB.CROWN_TURN, 16.0), Q.PETG, 1.0)
            w = d["window"]
            s.add("disc", Q.window_disc().translate(cq.Vector(*w["c"], lid_top(d) - w["depth"] + 16.0)), M.PTFE, 0.8)
            add_glands(s, name)
            a = front_slot(d, FRONT[name])
            s.anchor("slot", crown_pt(d, d["r_sp"] - PB.CROWN_LUG[2] - 0.25, a, d["z_joint"] - 1.5))
            s.anchor("lid", dome_pt(d, 0.8, 250, 16.0), on="uv_lid")
            R("q_lid_uv", s, FRONT[name], up=UP[name], fit=(170, 230), line=0.3)
            return
        add_body(s, name, lid=True)
        z1 = d["z_rim"] + d["lid_t"]
        for x, y in d["lugs"]:
            k = corner(name, x, y)
            s.add(f"ls_{k}", Q.pan_screw(LID_L).translate(cq.Vector(x, y, z1)), Q.STEEL, 0.8)
            s.anchor(f"ls:{k}", (x + 1.2, y + 1.2, z1 + 2.4))
        add_glands(s, name)
        R(f"q_lid_{name.lower()}", s, FRONT[name], up=UP[name], fit=(170, 230), line=0.3)
    _or.__name__, _lid.__name__ = f"q_oring_{_n.lower()}", f"q_lid_{_n.lower()}"
    scene(_or)
    scene(_lid)


@scene
def q_oring_join():
    s = r3d.Scene()
    name = "TH"
    s.add("th_lid", PB.lid(name), Q.PETG, 1.0)
    s.add("cord", Q.cord_in_groove(name, cut_gap=2.5), Q.CORD, 0.8)
    g = PB.groove(name)
    d = d_(name)
    x = (d["x0"] + d["x1"]) / 2                          # the join: the middle of the gland-end run (models_q)
    y = d["y0"] - PB.WALL / 2
    zc = d["z_rim"] + g["depth"] - g["cord"] / 2
    s.anchor("join", (x + 1.25 + 0.4, y, zc - g["cord"] / 2))
    s.anchor("groove", (x, y, d["z_rim"] + g["depth"]))
    R("q_oring_join", s, (0.2, -0.8, -1.0), up=(0, 0, -1), fit=(220, 160), line=0.35, crop=((x, y, zc), 9.0, 6.0))


# ------------------------------------------------------------------ the shield (meshes)
def box_mesh(s, X, name, glands=True, lid=True, screws=()):
    """A pod box (body + lid, closed) placed in the shield frame by remix.box_pose, with its glands."""
    Rm, t = X.box_pose(name)
    p = name.lower()
    s.add(f"{p}_box", turn(PB.body(name), Rm, t), Q.PETG, 1.0)
    if lid:
        s.add(f"{p}_lid", turn(PB.lid(name), Rm, t), Q.PETG, 1.0)
        if name == "UV":
            d = d_(name)
            w = d["window"]
            z1 = lid_top(d)
            s.add("uv_disc", turn(Q.window_disc().translate(cq.Vector(*w["c"], z1 - w["depth"])), Rm, t), M.PTFE, 0.8)
    if glands:
        for k, c, a in PB.openings(name):
            if k in ("gland", "lead_gland"):
                for nm, shp, col in Q.gland_in_wall(c, a):
                    s.add(f"{p}_{k}_{nm}", turn(shp, Rm, t), col, 0.8)
    return Rm, t


def gland_tip(X, name, kind):
    """World point at the dome nut's outer end of a pod box's gland, and the gland's outward axis (world)."""
    Rm, t = X.box_pose(name)
    c, a = opening(name, kind)
    a_w = Rm @ np.asarray(a, float)
    return Rm @ np.asarray(c, float) + t + a_w * DOME_END, a_w


def mount_screw(axis, head_at):
    """An M3 x 10 pan head, its head's underside at head_at, the shank along `axis` (unit) into the part below."""
    Rm = axis_to(-np.asarray(axis, float))
    return turn(Q.pan_screw(MOUNT_L), Rm, head_at)


def arm_screws(s, X, name):
    m = X.arm_mount(name)
    nrm = np.asarray(m["normal"], float)                     # box back -> arm
    for k, h in enumerate(m["holes"]):
        head = np.asarray(h) + nrm * m["thickness"]
        s.add(f"{name.lower()}_ms{k}", mount_screw(-nrm, head), Q.STEEL, 0.8)


@scene
def q_sh_order():
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    gap = {"arm": 0.0, "cup": 40.0, "stand": 80.0, "plates": 175.0, "cap": 230.0}
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    for n in ("TH", "BARO"):
        box_mesh(s, X, n)
    s.add("cup", (asm[A.CUP][0] + (0, 0, gap["cup"]), asm[A.CUP][1]), Q.SHIELD)
    s.add("stand", (asm[A.STAND][0] + (0, 0, gap["stand"]), asm[A.STAND][1]), Q.SHIELD)
    for k in range(1, A.PITCH_PLATES + 1):
        v, f = asm[f"{A.PLATE}.{k}"]
        s.add(f"plate{k}", (v + (0, 0, gap["plates"] + 10.0 * (k - 1)), f), Q.SHIELD)
    cap = X.cap_remixed().translate((0, 0, gap["cap"] + 50.0))
    s.add("cap", cap, Q.SHIELD)
    Rm, t = X.box_pose("UV")
    t2 = t + (0, 0, gap["cap"] + 50.0)
    s.add("uv_box", turn(PB.body("UV"), Rm, t2), Q.PETG, 1.0)
    s.add("uv_lid", turn(PB.lid("UV"), Rm, t2), Q.PETG, 1.0)
    for nm, (p, on) in {"arm": ((10, -86.5, 50), "arm"), "th": (None, "th_box"), "baro": (None, "baro_box"),
                        "cup": ((25.0, -12.0, 16.0 + gap["cup"]), "cup"),
                        "stand": ((0.0, -4.6, 90.0 + gap["stand"]), "stand"),
                        "plate1": ((40.0, -30.0, 46.6 + gap["plates"]), "plate1"),
                        "plate6": ((40.0, -30.0, 121.6 + gap["plates"] + 50.0), "plate6"),
                        "cap": ((0.0, -56.5, 141.0 + gap["cap"] + 50.0), "cap")}.items():
        if p is None:
            bb = s.parts[[q[0] for q in s.parts].index(on)][1][0]
            p = bb.mean(0)
            p = (p[0] + (-15.6 if nm == "th" else 15.6), p[1], p[2])
        s.anchor(nm, p, on="stand" if nm == "stand" else None)
    MRr("q_sh_order", s, (0.9, -1.0, 0.45), fit=(330, 560), line=0.3, outline=0.9)


@scene
def q_lead_iso():
    """The TH lead's route from the stand side of the base cup to the TH box's lead gland (remix.th_lead_path)."""
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    s.add("cup", asm[A.CUP], Q.SHIELD)
    box_mesh(s, X, "TH")
    path = [np.array((-12.0, 4.0, 60.0))] + [np.asarray(p, float) for p in X.th_lead_path()]
    tip, ax = gland_tip(X, "TH", "lead_gland")
    path.append(tip + ax * 2.0)
    s.add("lead", Q.tube([tuple(p) for p in path], 2.0), M.JACKET, 1.0)
    hx, hy, hr, zo = X.cup_hole()
    lx, ly = X.lead_hole()
    lo, hi, _t = X.arm_plate()
    s.anchor("cuphole", (hx, hy, 32.6))
    s.anchor("armhole", (lx, ly, lo))
    s.anchor("loop", tuple(np.asarray(X.th_lead_path()[-1]) + (0, 0, -2.0)))
    s.anchor("gland", tuple(tip - ax * 6.0))
    MRr("q_lead_iso", s, (0.35, 1.0, 0.25), fit=(330, 400), line=0.3)


@scene
def q_lead_cup():
    """The base cup from above: its Ø5 lead hole beside the three post sockets."""
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    s.add("cup", asm[A.CUP], Q.SHIELD)
    hx, hy, hr, zo = X.cup_hole()
    top = float(asm[A.CUP][0][:, 2].max())
    s.hole("cuphole", (hx, hy, top), drawn=False)
    s.anchor("disc", (18.0, -18.0, top), on="cup")
    MRr("q_lead_cup", s, (0, 0, 1), up=(0, 1, 0), fit=(200, 200), line=0.35)


@scene
def q_lead_arm():
    """The remixed arm from below: the new Ø6 arm lead hole in the TH tab."""
    A, X = _shield()
    s = MR.Scene()
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    lx, ly = X.lead_hole()
    lo, hi, _t = X.arm_plate()
    s.hole("armhole", (lx, ly, lo), drawn=False)
    m = X.arm_mount("TH")
    s.anchor("thface", (m["face"][0], 0.0, -30.0))
    MRr("q_lead_arm", s, (0, 0, -1), up=(0, 1, 0), fit=(220, 260), line=0.35)


@scene
def q_arm_iso():
    A, X = _shield()
    s = MR.Scene()
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    for n in ("TH", "BARO"):
        box_mesh(s, X, n)
        arm_screws(s, X, n)
    for n in ("TH", "BARO"):
        m = X.arm_mount(n)
        s.anchor(f"{n.lower()}face", ((m["face"][0] + m["face"][1]) / 2, 20.0, m["face"][5]))
        bb = s.parts[[q[0] for q in s.parts].index(f"{n.lower()}_lid")][1][0]
        s.anchor(f"{n.lower()}box", tuple(bb.mean(0)))
    s.anchor("upright", (0.0, -84.0, 55.0))
    MRr("q_arm_iso", s, (0.25, 1.0, 0.75), fit=(330, 330), line=0.3)


for _n, _sg in (("TH", -1.0), ("BARO", 1.0)):
    def _af(name=_n, sg=_sg):
        """One face from the cup's side, the arm drawn cut at its middle (x = 0) so that face's inner side shows."""
        A, X = _shield()
        s = MR.Scene()
        arm = X.arm_remixed().trim_by_plane((sg, 0.0, 0.0), 0.0)
        s.add("arm", arm, Q.SHIELD)
        box_mesh(s, X, name)
        arm_screws(s, X, name)
        m = X.arm_mount(name)
        nrm = np.asarray(m["normal"], float)
        for k, h in enumerate(m["holes"]):
            s.anchor(f"ms{k}", tuple(np.asarray(h) + nrm * (m["thickness"] + 2.4)))
        MRr(f"q_arm_{name.lower()}_face", s, (-sg, -0.25, 0.15), fit=(260, 300), line=0.32)
    _af.__name__ = f"q_arm_{_n.lower()}_face"
    scene(_af)


def sht45_on_stand(s, X, A):
    """The SHT45 #6174 on the stand's inner face, long side vertical, centred at mid-stack (assemble.sht45_box), its
    back standing off the face by the lead's four cores (Session P: in from the back, along it to the edge), two cable
    ties round it and the strip over its two STEMMA QT sockets; the lead's jacket hangs beside the strip to the cup's
    Ø5 hole. Returns the lead's top point."""
    import models_p as MP
    (x0, x1), (y0, y1), (z0, z1) = A.sht45_box()
    origin, normal, extent = A.stand_face()
    core_d = 1.2
    yb = origin[1] + core_d + 0.1                      # the board's back face
    Rm = np.array([[0, 1.0, 0], [0, 0, 1.0], [1.0, 0, 0]])     # maker x -> world z, maker y -> world x, maker z -> world y
    t = np.array([x0, yb, z0])
    parts, anc = MP.breakout("sht45")
    for nm, shp, col, w in parts:
        s.add(f"sht_{nm}", turn(shp, Rm, t), col, w)
    pads = dict(zip(S.val("sht45_pins"), MP.hdr_pads("sht45")))
    pod = PD.pod("TH")
    ends = []
    for k, c in enumerate(pod.lead.conductors):
        px, py = pads[c.pad]
        pts = [(px, py, MP.PCB + 0.5), (px, py, -0.6), (px, -1.5, -0.6), (6.0 + k * 1.0, -3.5, -0.6)]
        w_ = [tuple(Rm @ np.array(p) + t) for p in pts]
        s.add(f"core_{c.colour}", M.tube(w_, 0.6), M.INS[c.colour], 0.6)
        ends.append(w_[-1])
    (sx0, sx1), (sy0, sy1) = (-7.0, 7.0), (-4.5, origin[1])
    xs, ys, zs0, zs1 = A._strip()
    sx0, sx1, sy0 = float(xs[0]), float(xs[1]), float(ys[0])
    bb = cq.Compound.makeCompound([turn(shp, Rm, t) for nm, shp, col, w in parts]).BoundingBox()
    for k, (qx, qy) in enumerate(M.QT["sht45"]):
        zc = float((Rm @ np.array((qx, qy, 0)) + t)[2])
        s.add(f"tie{k}", Q.tie_loop(min(sx0, bb.xmin), max(sx1, bb.xmax), sy0, bb.ymax, zc), Q.TIE, 0.6)
        s.anchor(f"tie{k}", (bb.xmax + Q.TIE_T + 3.2, (sy0 + bb.ymax) / 2, zc))
    s.anchor("ptfe", tuple(Rm @ np.array(anc["sensor"][0]) + t))
    s.anchor("board", tuple(Rm @ np.array((12.7, 15.5, MP.PCB)) + t))
    top = np.mean(ends, 0)
    return top, (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax)


@scene
def q_sht_stand():
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    s.add("stand", asm[A.STAND], Q.SHIELD)
    s.add("cup", asm[A.CUP], Q.SHIELD)
    top, bb = sht45_on_stand(s, X, A)
    hx, hy, hr, zo = X.cup_hole()
    path = [tuple(top), (hx + 0.5, hy, top[2] - 6.0), (hx, hy, 40.0), (hx, hy, 20.0)]
    s.add("lead", Q.tube(path, 2.0), M.JACKET, 1.0)
    s.anchor("lead", (hx, hy + 2.0, 50.0))
    s.anchor("strip", (4.0, 0.5, 108.0))
    s.anchor("cuphole", (hx, hy, 32.6))
    MRr("q_sht_stand", s, (0.55, 1.0, 0.3), fit=(300, 420), line=0.3, bounds_parts=None)


@scene
def q_sht_close():
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    s.add("stand", asm[A.STAND], Q.SHIELD)
    top, bb = sht45_on_stand(s, X, A)
    hx, hy, hr, zo = X.cup_hole()
    path = [tuple(top), (hx + 0.5, hy, top[2] - 6.0), (hx, hy, 40.0)]
    s.add("lead", Q.tube(path, 2.0), M.JACKET, 1.0)
    keep = [p[0] for p in s.parts if p[0].startswith(("sht_", "tie", "core_"))]
    MRr("q_sht_close", s, (0.2, 1.0, 0.12), fit=(260, 330), line=0.32, bounds_parts=keep)


def _uv_on_cap(s, X, flip=False, lid=True):
    """The remixed cap with the UV crown on it (shield frame), and the four M3 x 10 up through the cap into the floor
    inserts. flip: both turned over (180 about x) for the bench, the cap's flat top at z = 0; lid: the dome lid on."""
    cap = X.cap_remixed()
    Rm, t = X.box_pose("UV")
    F = np.diag([1.0, -1.0, -1.0]) if flip else np.eye(3)
    z_top = X.uv_mount()["top_z"]
    shift = np.array([0, 0, -z_top]) if flip else np.zeros(3)
    v, f = MR._weld(*__import__("remix").arrays(cap))
    s.add("cap", ((v + shift) @ F.T, f), Q.SHIELD)
    t2 = F @ (t + shift)
    R2 = F @ Rm
    s.add("uv_box", turn(PB.body("UV"), R2, t2), Q.PETG, 1.0)
    d = d_("UV")
    if lid:
        s.add("uv_lid", turn(PB.lid("UV"), R2, t2), Q.PETG, 1.0)
        w = d["window"]
        s.add("uv_disc", turn(Q.window_disc().translate(cq.Vector(*w["c"], lid_top(d) - w["depth"])), R2, t2), M.PTFE, 0.8)
    for nm, shp, col in Q.gland_in_wall(*opening("UV", "gland")):
        s.add(f"uv_gland_{nm}", turn(shp, R2, t2), col, 0.8)
    m = X.uv_mount()
    heads = []
    for k, (x, y) in enumerate(m["holes"]):
        head = F @ (np.array((x, y, m["seat_z"])) + shift)
        ax = F @ np.array((0, 0, 1.0))                    # the shank points up (world) into the crown's floor
        s.add(f"cs{k}", mount_screw(ax, head), Q.STEEL, 0.8)
        heads.append((k, head, ax))
    return m, F, shift, heads


@scene
def q_cap_bench():
    """At the bench: the crown's body upside down on its spigot (lid off), the cap turned over onto its floor; the four
    M3 x 10 go down the cap's counterbores into the floor inserts."""
    A, X = _shield()
    s = MR.Scene()
    m, F, shift, heads = _uv_on_cap(s, X, flip=True, lid=False)
    for k, head, ax in heads:
        s.anchor(f"cs{k}", tuple(head - ax * 2.4))
    s.anchor("skirt", tuple(F @ (np.array((0.0, -54.0, m["top_z"] - 6.0)) + shift)))
    MRr("q_cap_bench", s, (0.35, -0.7, 1.0), fit=(330, 300), line=0.3)


@scene
def q_cap_under():
    """The remixed cap seen from below (from inside the shield): the four screw holes up their counterbores through
    the inner cone."""
    A, X = _shield()
    s = MR.Scene()
    s.add("cap", X.cap_remixed(), Q.SHIELD)
    m = X.uv_mount()
    for k, (x, y) in enumerate(m["holes"]):
        s.hole(f"cs{k}", (x, y, m["seat_z"]), drawn=False)
    MRr("q_cap_under", s, (0, 0, -1), up=(1, 0, 0), fit=(260, 260), line=0.32)


@scene
def q_cap_iso():
    A, X = _shield()
    s = MR.Scene()
    m, F, shift, heads = _uv_on_cap(s, X)
    tip, ax = gland_tip(X, "UV", "gland")
    s.add("uv_cable", Q.tube([tuple(tip - ax * 6.0), tuple(tip + ax * 6.0), tuple(tip + ax * 12.0 + (0, 0, -8.0)),
                              tuple(tip + ax * 12.0 + (0, 0, -40.0))], 2.0), M.JACKET, 1.0)
    d = d_("UV")
    s.anchor("uvbox", tuple(X.box_points("UV", [dome_pt(d, 0.75, 200)])[0]), on="uv_lid")
    s.anchor("gland", tuple(tip - ax * 8.0))
    s.anchor("skirt", (0.0, -54.0, m["top_z"] - 6.0))
    s.anchor("window", tuple(X.box_points("UV", [(*d["window"]["c"], lid_top(d))])[0]))
    MRr("q_cap_iso", s, (0.8, -0.9, 0.7), fit=(330, 280), line=0.3)


def smooth(pts, n=8):
    """A centripetal Catmull-Rom curve through pts, sampled n per span: it passes every point and never overshoots, so
    the overlap check on the samples is the check on the cable as drawn."""
    P = [np.asarray(p, float) for p in pts]
    P = [2 * P[0] - P[1]] + P + [2 * P[-1] - P[-2]]
    out = [P[1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5
        t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
        for t in np.linspace(t1, t2, n + 1)[1:]:
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return [tuple(p) for p in out]


def cable_route(tip, ax, side, low=45.0, pole_y=-105.0):
    """A port cable from its gland's dome straight down, a drip loop (its low point `low` below the dome), then up and
    back toward the pole (behind the arm's upright at -y) and down the pole."""
    tip = np.asarray(tip, float)
    return [tuple(tip), tuple(tip + (0, 0, -low * 0.55)), tuple(tip + (side * 6.0, -10.0, -low)),
            tuple(tip + (side * 10.0, -30.0, -low + 14.0)), (tip[0] * 0.4 + side * 4.0, pole_y + 6.0, tip[2] - low + 18.0),
            (side * 6.0, pole_y, tip[2] - low - 10.0), (side * 6.0, pole_y, tip[2] - low - 70.0)]


@scene
def q_drip():
    import manifold3d as mf
    A, X = _shield()
    asm = A.assembled()
    s = MR.Scene()
    s.add("arm", X.arm_remixed(), Q.SHIELD)
    s.add("cup", asm[A.CUP], Q.SHIELD)
    s.add("stand", asm[A.STAND], Q.SHIELD)
    for k in range(1, A.PITCH_PLATES + 1):
        s.add(f"plate{k}", asm[f"{A.PLATE}.{k}"], Q.SHIELD)
    s.add("cap", X.cap_remixed(), Q.SHIELD)
    for n in ("TH", "BARO", "UV"):
        box_mesh(s, X, n)
    solids = X.arm_remixed() + X.cap_remixed() + X.box_placed("TH") + X.box_placed("BARO") + X.box_placed("UV")
    for k in range(1, A.PITCH_PLATES + 1):
        solids = solids + X.original(f"{A.PLATE}.{k}")
    solids = solids + X.original(A.CUP)
    routes = {}
    for n, side in (("TH", -1.0), ("BARO", 1.0)):
        tip, ax = gland_tip(X, n, "gland")
        routes[f"{n.lower()}_cable"] = cable_route(tip, ax, side)
    tip, ax = gland_tip(X, "UV", "gland")
    lo, hi, _t = X.arm_plate()
    out = tip + ax * 12.0                                  # level out of the drum, then over and down outside the louvers
    routes["uv_cable"] = [tuple(tip), tuple(out + (0, 0, -6.0)), (out[0] + 2.0, out[1], lo - 140.0), (out[0], out[1], lo - 95.0),
                          (out[0] + 2.0, out[1] - 34.0, lo - 128.0), (14.0, -99.0, lo - 120.0), (6.0, -105.0, lo - 135.0),
                          (6.0, -105.0, lo - 190.0)]
    lead = [np.array((-12.0, 4.0, 60.0))] + [np.asarray(p, float) for p in X.th_lead_path()]
    tip_l, ax_l = gland_tip(X, "TH", "lead_gland")
    lead.append(tip_l + ax_l * 2.0)
    routes["th_lead"] = [tuple(p) for p in lead]
    loops = {k: v[2] for k, v in routes.items() if k != "th_lead"}           # each drip loop's low point (raw)
    for nm in list(routes):
        if nm != "th_lead":
            routes[nm] = smooth(routes[nm])
    for nm, pts in routes.items():
        s.add(nm, Q.tube(pts, 2.0), M.JACKET, 1.0)
        tb = X.tube(pts[1:-1] if nm != "th_lead" else pts[4:-1], 4.3)
        hit = (tb ^ solids).volume()
        print(f"{nm}: overlap with the shield and the boxes {hit:.3f} mm3")
        assert hit < 1e-3, f"{nm} runs through a part"
    low = {k: min(v, key=lambda p: p[2]) for k, v in routes.items()}
    for k, p in low.items():
        if k == "th_lead":
            p = tuple(np.asarray(X.th_lead_path()[-1]))
        s.anchor(f"low:{k}", (p[0], p[1], p[2] - 2.0) if k == "th_lead" else tuple(np.asarray(loops[k]) + (0, 0, -2.0)))
    for n in ("TH", "BARO", "UV"):
        tip, ax = gland_tip(X, n, "gland")
        s.anchor(f"gland:{n}", tuple(tip - ax * 6.0))
    MRr("q_drip", s, (0.35, 1.0, -0.12), fit=(400, 600), line=0.28, outline=0.9)


def write_facts():
    """svg/q_facts.json: the per-pod numbers the page builder prints (it runs on .venv-pdf, without CadQuery)."""
    import json
    out = {}
    for n in POD:
        d, g = d_(n), PB.groove(n)
        out[n] = {"inserts": len(d["lugs"]) + len(d["mount_lugs"]) + len(d["floor_bosses"]),
                  "groove": round(g["length"], 1), "cut": int(round(g["length"])), "depth": round(g["depth"], 3)}
    (HERE / "svg").mkdir(exist_ok=True)
    json.dump(out, open(HERE / "svg" / "q_facts.json", "w"), indent=1)
    print("svg/q_facts.json", out)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if names == ["facts"]:
        write_facts()
        sys.exit()
    if len(names) != 1:
        sys.exit("render ONE scene per process: scenes_q.py NAME   (scenes_q.py list)")
    SCENES[names[0]]()
