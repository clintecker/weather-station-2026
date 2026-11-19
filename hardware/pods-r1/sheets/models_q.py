"""Session Q's loose parts, as CadQuery solids (every size from sources.py, the box geometry from box/podbox.py):
the M3 heat-set insert, M3 pan-head screws, the PG-7 #762 gland as supplied (body, seal, dome nut, locknut), the
O-ring cord, the UV window disc, the BARO ePTFE patch and cable ties.

Frames are each part's own (stated per function); scenes_q.py places them.
"""
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PODS = HERE.parent
for p in (HERE, PODS / "box", PODS / "layout", PODS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import sources as S                     # noqa: E402
import podbox as PB                     # noqa: E402
import models_p as M                    # noqa: E402

PETG = "#E3E5DF"                # the pod boxes: PETG, light colour (podbox: "PETG, light colour")
SHIELD = "#F3F3EF"              # the radiation shield's printed parts (white)
BRASS = "#C9A54A"               # heat-set inserts
STEEL = "#B7BCC2"               # A2 stainless screws
GLAND = "#2B2B2B"               # the #762 gland's black nylon
SEAL = "#5A6066"                # its rubber seal ring (drawn a shade lighter than the nylon so it reads)
CORD = "#2A2A2A"                # NBR / EPDM O-ring cord
TIE = "#1E1E1E"                 # UV-resistant black cable ties
EPTFE = "#F7F7F5"
SILICONE = "#DADADA"

INSERT_L, INSERT_D = S.val("insert_m3")            # 5.7 long, 4.6 knurl (TX row, TBD)
BORE_D, BORE_DEPTH = S.val("pod_insert_bore")
SEAL_T = 0.8                                       # the gland's seal ring thickness (drawn; not in sources)


def insert_m3():
    """An M3 heat-set insert, axis +z, its lead-in end at z = 0 (that end goes into the bore first), top at INSERT_L."""
    r = INSERT_D / 2
    body = cq.Workplane("XY").circle(r).extrude(INSERT_L)
    for z0 in (0.9, 3.2):                                           # two knurl bands with a groove between
        body = body.cut(cq.Workplane("XY").workplane(offset=z0 + 1.1).circle(r + 1).circle(r - 0.35).extrude(0.7))
    body = body.faces("<Z").chamfer(0.45)
    body = body.cut(cq.Workplane("XY").workplane(offset=-1).circle(1.25).extrude(INSERT_L + 2))
    return body.val()


def pan_screw(length, size=None):
    """An ISO 7045 pan-head screw, axis +z: the head's underside at z = 0, the shank down to z = -length; a cross recess
    in the head. size: (thread, length, head) as sources gives it (default pod_screw, M3: head 5.5, 2.4 tall; the
    LTR390's ltr_screw, M2.5, draws a head 1.9 tall)."""
    d, _l, dk = size or S.val("pod_screw")
    k = 2.4 * d / 3.0 if d < 3.0 else 2.4
    head = cq.Workplane("XY").circle(dk / 2).extrude(k).faces(">Z").edges().fillet(0.9)
    for a in (0, 90):
        head = head.cut(cq.Workplane("XY").workplane(offset=k - 1.2).rect(dk * 0.55, 0.6).extrude(2).rotate((0, 0, 0), (0, 0, 1), a))
    shank = cq.Workplane("XY").workplane(offset=-length).circle(d / 2).extrude(length + 0.2)
    shank = shank.faces("<Z").chamfer(0.3)
    return head.union(shank).val()


def gland(apart=0.0, lock_off=0.0):
    """The Adafruit #762 PG-7 gland as supplied: body (thread + hex flange + the dome's thread), its seal ring on the
    thread against the hex, the dome nut on the body, the locknut on the thread's end. models_p.gland_pg7()'s parts
    plus the seal. Axis +y from y = 0 (the thread's inner end) to the dome's end. lock_off: the locknut moved this far
    off the thread's end (-y); apart: the dome nut moved off (+y) as well.
    Returns [(name, shape, colour)]."""
    th, L1 = S.val("gland_pg7")[:2]
    out = []
    for nm, shp, col in M.gland_pg7():
        if nm == "gdome":
            shp = shp.translate(cq.Vector(0, apart, 0))
        if nm == "glock":
            shp = shp.translate(cq.Vector(0, -lock_off, 0))
        out.append((nm, shp, col))
    seal = cq.Solid.makeCylinder(7.4, SEAL_T, cq.Vector(0, L1 - SEAL_T, 0), cq.Vector(0, 1, 0)).cut(
        cq.Solid.makeCylinder(th / 2 + 0.05, SEAL_T + 1, cq.Vector(0, L1 - SEAL_T - 0.5, 0), cq.Vector(0, 1, 0)))
    out.append(("gseal", seal, SEAL))
    return out


def gland_in_wall(centre, axis, wall=PB.WALL):
    """The gland fitted in a box wall: its hex and seal on the wall's outside face (centre = the opening's centre on the
    outer face, axis = outward), the locknut tight on the inside face. [(name, shape, colour)] in the box frame."""
    th, L1 = S.val("gland_pg7")[:2]
    a = np.asarray(axis, float)
    c = np.asarray(centre, float)
    out = []
    for nm, shp, col in gland():
        if nm == "glock":                         # the locknut moves up the thread to the inside face
            shp = shp.translate(cq.Vector(0, (L1 - SEAL_T - wall) - 3.0, 0))
        shp = shp.translate(cq.Vector(0, -(L1 - SEAL_T), 0))      # the seal's inner face on y = 0 (the outer face)
        shp = _turn_y_to(shp, a).translate(cq.Vector(*c))
        out.append((nm, shp, col))
    return out


def _turn_y_to(shp, a):
    """Rotate a shape so its +y axis points along unit vector a (a is a principal axis)."""
    a = tuple(int(round(v)) for v in a)
    rot = {(0, 1, 0): None, (0, -1, 0): ((0, 0, 1), 180), (0, 0, -1): ((1, 0, 0), -90), (0, 0, 1): ((1, 0, 0), 90),
           (1, 0, 0): ((0, 0, 1), -90), (-1, 0, 0): ((0, 0, 1), 90)}[a]
    if rot is None:
        return shp
    return shp.rotate(cq.Vector(0, 0, 0), cq.Vector(*rot[0]), rot[1])


def cord_coil(turns=2.4, r=16.0):
    """The O-ring cord as supplied: a loose coil, cord d = sources pod_oring."""
    d = S.val("pod_oring")
    pts = []
    n = int(turns * 36)
    for i in range(n + 1):
        a = 2 * math.pi * i / 36
        rr = r * (1 - 0.06 * i / n)
        pts.append((rr * math.cos(a), rr * math.sin(a), d * 1.05 * i / 36))
    return _sweep(pts, d / 2)


def _sweep(pts, r, closed=False):
    """A round section (radius r) swept along a 3D polyline (smoothed by a spline)."""
    vs = [cq.Vector(*p) for p in pts]
    path = cq.Wire.assembleEdges([cq.Edge.makeSpline(vs, periodic=closed)])
    t = path.tangentAt(0)
    prof = cq.Wire.makeCircle(r, vs[0], t)
    return cq.Solid.sweep(prof, [], path, makeSolid=True, isFrenet=False)


def cord_in_groove(name, cut_gap=0.0):
    """The cord seated in the lid's groove (box frame): its centreline on the groove's (podbox.groove: the rim's middle,
    a rounded rectangle turning on R_IN + WALL / 2), its centre the cord's radius above the groove's floor, so it stands
    proud of the lid's inner face by (cord - depth). Four straight runs and four quarter-tori. cut_gap: leave a gap of
    that length at the join (the middle of the gland-end run), to show the butt joint before it closes."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    g = PB.groove(name)
    d = PB.dims(name)
    r = g["cord"] / 2
    if g.get("radial"):                     # the UV crown: a ring round the spigot, in its groove, standing proud of it
        cx, cy = d["axis"]
        rc = d["r_sp"] - g["depth"] + r
        ax = gp_Ax2(gp_Pnt(cx, cy, g["z"]), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
        return cq.Shape.cast(BRepPrimAPI_MakeTorus(ax, rc, r).Shape())
    zc = d["z_rim"] + g["depth"] - r
    o, rc = PB.WALL / 2, PB.R_IN + PB.WALL / 2
    xa, xb, ya, yb = d["x0"] - o, d["x1"] + o, d["y0"] - o, d["y1"] + o
    xm = (xa + xb) / 2
    runs = [((xa + rc, yb, zc), (xb - rc, yb, zc)), ((xa, ya + rc, zc), (xa, yb - rc, zc)),
            ((xb, ya + rc, zc), (xb, yb - rc, zc))]
    if cut_gap:
        runs += [((xa + rc, ya, zc), (xm - cut_gap / 2, ya, zc)), ((xm + cut_gap / 2, ya, zc), (xb - rc, ya, zc))]
    else:
        runs += [((xa + rc, ya, zc), (xb - rc, ya, zc))]
    sols = []
    for a, b in runs:
        a, b = np.array(a), np.array(b)
        L = np.linalg.norm(b - a)
        sols.append(cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*((b - a) / L))))
    for (cx, cy), a0 in (((xb - rc, ya + rc), -90), ((xb - rc, yb - rc), 0), ((xa + rc, yb - rc), 90), ((xa + rc, ya + rc), 180)):
        xd = (math.cos(math.radians(a0)), math.sin(math.radians(a0)), 0.0)
        ax = gp_Ax2(gp_Pnt(cx, cy, zc), gp_Dir(0, 0, 1), gp_Dir(*xd))
        sols.append(cq.Shape.cast(BRepPrimAPI_MakeTorus(ax, rc, r, math.pi / 2).Shape()))
    s = sols[0]
    for x in sols[1:]:
        s = s.fuse(x)
    return s.clean()


def window_disc():
    """The UV window disc (sources uv_window: material, d, t), axis +z, its underside at z = 0."""
    _m, wd, wt = S.val("uv_window")
    return cq.Solid.makeCylinder(wd / 2, wt, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))


def eptfe_patch():
    """The BARO vent's optional adhesive ePTFE patch (sources baro_eptfe: d, t), axis +z."""
    pd, pt = S.val("baro_eptfe")
    return cq.Solid.makeCylinder(pd / 2, pt, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))


TIE_W, TIE_T = 2.5, 1.0                 # a small cable tie: 2.5 wide, 1.0 thick (drawn; sources has no tie row)


def tie_loop(x0, x1, y0, y1, zc):
    """A cable tie pulled tight round the rectangle x0..x1 by y0..y1 (its inside), horizontal at height zc, its head on
    the +x side."""
    t, w = TIE_T, TIE_W
    parts = [M.box(x0 - t, y0 - t, zc - w / 2, x1 + t, y0, zc + w / 2), M.box(x0 - t, y1, zc - w / 2, x1 + t, y1 + t, zc + w / 2),
             M.box(x0 - t, y0 - t, zc - w / 2, x0, y1 + t, zc + w / 2), M.box(x1, y0 - t, zc - w / 2, x1 + t, y1 + t, zc + w / 2),
             M.box(x1 + t, (y0 + y1) / 2 - 2.0, zc - w / 2 - 0.6, x1 + t + 3.2, (y0 + y1) / 2 + 2.0, zc + w / 2 + 0.6)]
    s = parts[0]
    for p in parts[1:]:
        s = s.union(p)
    return s.val()


def tie_loose(length=100.0):
    """A cable tie as supplied: a straight strip along +x with its head at x = 0."""
    s = M.box(0, -TIE_W / 2, 0, length, TIE_W / 2, TIE_T).union(M.box(-4.0, -3.0, -0.6, 0.2, 3.0, 2.4))
    s = s.cut(M.box(-3.2, -TIE_W / 2 - 0.1, -1, -0.8, TIE_W / 2 + 0.1, 3))
    return s.val()


def tube(pts, r):
    """A cable or lead along a 3D polyline (models_p.tube: cylinders with ball joints)."""
    return M.tube(pts, r)
