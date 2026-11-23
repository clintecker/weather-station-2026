"""The printed pod boxes for the three sensor pods (TH, BARO, UV): one parametric box, sized from each pod's board.

Run `python box/podbox.py` (with .venv-cad) to write box/stl/pod-{th,baro,uv}-{body,lid}.stl, in print orientation.

FRAME. The box frame is the pod board's frame (layout/pods.py): millimetres, x to the right along the Perma-Proto's
columns, y up along them (J1's jack mouth faces -y), z out of the board's component face, z = 0 on that face. The body
and the lid are built in place (lid closed), so the parts' boxes from pods.pod(name) can be measured against them.

MOUNTED ORIENTATION (up(name) gives world-up in the box frame).
  TH, BARO  the board stands vertical: world up = +y. The back (-z) is the mount face, bolted to the remixed arm; the
            lid faces out. The port gland is in the bottom wall (-y) on the plug's axis: the cable comes straight up
            into the jack. TH also has the lead gland in the bottom wall for the SHT45's 4-wire lead; BARO has the vent.
  UV        the board lies flat, sensor up: world up = +z. The lid (on top) carries the window over the LTR390's chip.
            The back (-z, now the floor) is the mount face on the remixed cap's bosses, and the port gland goes through
            that floor: the cable rises through it, bends over (plug_bend) and runs level into the jack.

CHOICES (the brief left these to the builder; record of them):
  material, print  PETG, light colour. Body printed back face down (the mount face on the bed), lid printed inner face
                   down (the O-ring groove on the bed, the UV window recess on top). No supports: every hole whose axis
                   lies flat in print (the glands in the TH/BARO bottom wall) is a teardrop capped at 1.1 r, inside
                   the gland's outer seal; the BARO baffle and the standoffs are vertical fins and posts.
  wall             WALL = 3.0 all round, back included. LID_T = 3.0 (the UV lid takes the window recess in that).
  clearance        CLEAR = 2.0 from every part box, the plug and its bend, the board and its copper side to the walls
                   and the lid. The inside is the union of those boxes grown by CLEAR, plus room for the glands' nuts
                   (NUT_GAP = 1.0 from a nut's corners to the nearest wall or the lid; this sets the TH/BARO depth).
  seal             a round O-ring cord (sources pod_oring, d) in a groove cut in the LID's inner face over the body's
                   rim centreline: groove 1.35 d wide, 0.75 d deep (25 % squeeze). The lid lands flat on the 3.0 rim,
                   a hard stop, so the squeeze is set by the groove, not by screw torque.
  lid screws       four M3 x 8 pan head (sources pod_screw) through 3.4 holes in the lid into M3 heat-set inserts
                   (sources insert_m3, bores pod_insert_bore) in four corner lugs outside the walls, outside the seal.
  mount face       the back face (-z). TH/BARO: the same four corner lugs take M3 heat-set inserts from the back (blind: the
                   sealed space is never pierced); mount_face() gives the plane and the four insert centres. The arm
                   and the cap (Task 7) bolt to two or more of them with M3 screws from their side.
                   UV (fix round 1): the floor gland must hang past the cap's edge (the cap's flat top is a disc of
                   r 38.03 with a fused saddle that carries the floor bosses, the gland end overhanging; the cable
                   runs down the outside of the louvers with a drip loop below the gland). So the two lugs at the
                   gland's end keep only their lid inserts, and two blind floor bosses inside the box, inboard of the
                   gland's nut (NUT_GAP clear of it) and BOSS_MARGIN clear of the side walls, take the other two mount
                   inserts (mount_boss_depth() tall from the mount face: the insert bore plus MOUNT_BOSS_CAP, so it
                   grows with the insert and its bore stays blind). mount_face("UV").keepouts gives the gland's
                   keep-out circle (GLAND_KEEP across at least) that the cap must stay clear of.
  board            on two standoffs from the back wall, one under each Perma-Proto mounting hole, no wider than
                   mount_keep (the screw head's circle the layout keeps clear, so they miss every bottom wire and
                   joint); M3 x 8 thread-forming into a pod_pilot_m3 pilot. Standoff height = the copper side's
                   depth (max(tails, two crossing wire24)) + CLEAR.
  BARO vent        a VENT_D hole through the bottom wall (axis down), an adhesive ePTFE vent (sources baro_eptfe, Gore
                   VE70510) in a seat recessed in the inner face (sources eptfe_seat, v1's 12.4 x 0.4), and a baffle: a fin standing off the back wall BAFFLE_GAP above
                   the hole, overhanging it by BAFFLE_OVER on the three open sides, so there is no straight line from
                   outside to the BMP581 (checked by tests/test_pods_box.py with real segments).
  UV window        sources uv_window (material, disc d, t): a recess d + 0.3 across and t deep in the lid's top face,
                   so the disc sits flush (no pond on it), bedded in silicone, over an aperture d - 3.0 across; centred
                   over the LTR390's chip (sources ltr390_sensor). The disc is Edmund #22-694 fused silica, so the
                   recess is 1.0 deep (it was 1.5 for the PTFE disc).
  UV breather      (2026-11-23) the crown breathes, so its window doesn't fog: a sources uv_breather hole, level through
                   the drum wall at CROWN_BREATHER_A (across from the gland), half way up the drum, under a flat seat
                   (sources eptfe_seat) cut into the bore, where the same adhesive ePTFE vent as BARO's sticks on. TH stays
                   sealed (Clint, 2026-11-18): it holds no sensor and nothing optical.
Every TBD value comes from sources.val, so a measurement regenerates the boxes.
"""
import math
import sys
from functools import lru_cache
from pathlib import Path

import cadquery as cq

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent / "layout", _HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import sources as S            # noqa: E402  hardware/pods-r1/sources.py
import pods                    # noqa: E402  hardware/pods-r1/layout/pods.py
import permaproto as PP        # noqa: E402

Box = pods.Box
CLEAR = 2.0                 # the brief's minimum clearance
WALL = 3.0                  # every wall, the back included
LID_T = 3.0                 # lid plate
R_IN = 2.0                  # inside corner radius (the groove's centreline turns on R_IN + WALL / 2)
LUG_DIAG = 1.0              # lug centre beyond the outer (square) corner, in x and in y
LUG_WALL = 2.0              # plastic round an insert bore in a lug
SCREW_HOLE = S.val("pod_screw")[0] + 0.4     # M3 clearance through the lid
TEAR = 1.1                  # teardrop cap height, x the hole radius
VENT_D = 4.0                # BARO vent hole
BAFFLE_GAP = 2.5            # baffle fin above the bottom wall's inner face
BAFFLE_OVER = 6.0           # baffle beyond the vent hole's edge, each open side
BAFFLE_T = 1.6              # baffle fin thickness
WINDOW_LEDGE = 1.5          # UV window ledge, each side (aperture = d - 2 x ledge)
NUT_GAP = 1.0               # a gland nut's free gap to the nearest wall
GLAND_KEEP = 18.0           # UV: the floor gland's keep-out circle on the mount face (the gland body 16.6 + margin)
MOUNT_BOSS_CAP = 1.0        # UV: plastic over a floor boss's blind insert bore
BOSS_MARGIN = 2.0           # UV: floor boss clear of the side walls
LID_CHAMFER = 0.8           # v1: the lid's top outer edge (round the whole outline, lugs and webs included)
V1 = _HERE / "v1"           # v1: Clint's printed boxes (his CAD agent, from CAD-BRIEF.md), 2026-11-18; this model matches them
UPS = {"TH": (0.0, 1.0, 0.0), "BARO": (0.0, 1.0, 0.0), "UV": (0.0, 0.0, 1.0)}
# the UV crown (Clint 2026-11-19: "make it look cool"): a round drum and a smooth dome, centred on the shield's axis
CROWN_SP_H = 10.0           # the body's spigot: height (the lid's skirt slides over it)
CROWN_SP_T = 2.4            # spigot: its outside radius beyond the drum's bore (sets the lid's skirt, the drum and the cap)
CROWN_SP_IN = 0.4           # the spigot also steps inward of the drum's bore by this (a 45 deg chamfer under it), so its
                            # wall is 2.8: 1.5 left behind the bayonet's channels and slots, 1.87 behind the groove
CROWN_C = 0.2               # radial clearance, spigot to the lid's skirt bore
CROWN_SKIRT_T = 2.2         # the lid's skirt wall (its outside is flush with the drum's)
CROWN_RISE = 28.0           # the dome's rise above the spigot's top
CROWN_DOME_T = 3.0          # the dome's shell
CROWN_FLAT = 3.0            # the apex flat, beyond the window recess's edge
CROWN_LUGS = 3              # bayonet lugs on the skirt's bore
CROWN_LUG = (8.0, 2.4, 1.0)  # a lug: arc length, height, depth (into the spigot's channel)
CROWN_TURN = -25.0          # the bayonet's twist, degrees about +z: negative = clockwise seen from above, like a jar lid
CROWN_LUG_Z = 3.5           # lug centre below the spigot's top
CROWN_ORING_Z = 7.0         # the radial O-ring groove's centre below the spigot's top
CROWN_BOSS_R = 31.0         # floor bosses for the mount inserts: radius about the crown's axis (inside the cap's flat top)
CROWN_GLAND_FACE = 22.0     # the round spot face for the port gland's seal, outside (and the flat land inside)
LTR_HOLES = (10.16, 6.35)   # LTR390 #4831 corner holes from its centre (x, y); 2.54 in from each edge (Adafruit's usual)
LTR_GAP = 1.0               # chip top to the window's aperture tube (at least)
LTR_QT_H = 2.95             # the LTR390's two factory STEMMA QT sockets (JST SH 4-pin horizontal): height off its top face
LTR_QT_GAP = 0.5            # QT socket tops to the aperture tube's bottom (the tube sits over both sockets)
LTR_DROP = 5.5              # the LTR390's top face below the dome's inner apex (sets the pilots' plastic, see LTR_PILOT_*)
LTR_CU = 0.05               # a boss lands on the breakout's hole ring (copper 0.05 proud of its top face)
LTR_PILOT_PAST = 0.5        # an M2.5 pilot runs this far past the screw's tip, and no further (plastic above it)
CROWN_BREATHER_A = 90.0     # the breather's direction about the crown's axis, degrees from +x (the gland is at 270)
CROWN_DETENT = (0.7, 0.2)   # the bayonet's detent: a round bump in each channel just behind the locked lug (radius,
                            # interference with the lug's inner face); the lug clicks over it, so the lid stays locked


def mount_boss_depth():
    """UV floor boss height from the mount face: the insert bore's depth (sources pod_insert_bore, from the TBD
    insert_m3 length) plus MOUNT_BOSS_CAP, so a longer insert grows the boss and its bore stays blind."""
    return S.val("pod_insert_bore")[1] + MOUNT_BOSS_CAP


MOUNT_BOSS_DEPTH = mount_boss_depth()   # at import, for readers (7.7 with today's insert); _build uses dims()


def up(name):
    """World up, as a unit vector in the box frame, with the box mounted."""
    return UPS[name]


def vent_d():
    return VENT_D


def eptfe_seat():
    """(diameter, depth) of the recess an adhesive ePTFE vent (sources baro_eptfe) sits in: sources eptfe_seat, held to
    Gore's target area (the vent's outer diameter plus the margin) and the vent's thickness."""
    sd, st, margin = S.val("eptfe_seat")
    vd, vt = S.val("baro_eptfe")
    assert sd >= vd + margin - 1e-9, f"the ePTFE seat ({sd}) is smaller than the vent ({vd}) plus Gore's margin ({margin})"
    assert st >= vt - 1e-9, f"the ePTFE seat ({st} deep) is shallower than the vent ({vt})"
    return sd, st


# ------------------------------------------------------------------ the numbers
def _plug(p):
    """The plug's axis (x, z), the jack mouth's y, and how far the plug body and its bend reach beyond the mouth."""
    jack = next(b for b in p.part("J1").boxes if "87180" in b.what)
    plug = next(b for b in p.part("J1").boxes if "RJ11 plug" in b.what)
    body_len = S.val("plug_6p")[3]
    reach = max(plug.y1 - plug.y0, body_len + S.val("plug_bend"))
    return (plug.x0 + plug.x1) / 2, (plug.z0 + plug.z1) / 2, jack.y0, body_len, reach


def _gland(kind):
    return S.val("gland") if kind == "gland" else S.val("th_lead_gland")


def _nut_depth():
    """How far a gland's thread and locknut stand inside the wall (gland_pg7 L1, thread length inside, less the wall)."""
    return max(S.val("gland_pg7")[1] - WALL, 0.0)


@lru_cache(maxsize=None)
def dims(name):
    """Every number the box is built from (box frame, mm)."""
    p = pods.pod(name)
    w, h = S.val("permaproto_q")
    t = S.val("permaproto_q_t")
    cs = max(S.val("tails"), 2 * S.val("wire24")[1])          # copper side: tails, or two crossing bottom wires
    boxes = [b for part in p.parts for b in part.boxes]
    px, pz, mouth, body_len, reach = _plug(p)
    top = max(b.z1 for b in boxes)
    x0 = min(min(b.x0 for b in boxes), 0.0) - CLEAR
    x1 = max(max(b.x1 for b in boxes), w) + CLEAR
    y1 = max(max(b.y1 for b in boxes), h) + CLEAR
    z_bi = -t - cs - CLEAR                                     # back wall, inner face
    plug_end = mouth - reach
    nut_r = S.val("gland")[1] / 2
    z_rim = top + CLEAR                                        # the rim = the lid's inner face
    if name != "UV":                                           # the port gland's nut (on the plug's axis) clears the lid
        z_rim = max(z_rim, pz + nut_r + NUT_GAP)
    d = dict(name=name, t=t, cs=cs, top=top, x0=x0, x1=x1, y1=y1, z_bi=z_bi, z_bo=z_bi - WALL, z_rim=z_rim,
             px=px, pz=pz, mouth=mouth, plug_end=plug_end, lid_t=LID_T, ops=[], boss_depth=mount_boss_depth())
    d["y0"] = plug_end - max(CLEAR, _nut_depth())
    if name == "UV":
        _crown_dims(d, p, nut_r)
    else:
        d["ops"].append(("gland", (px, d["y0"] - WALL, pz), (0.0, -1.0, 0.0)))
    if name != "UV":
        right = px + nut_r                                         # the port gland's nut, right edge
        if name == "TH":
            lx = (right + d["x1"]) / 2
            d["ops"].append(("lead_gland", (lx, d["y0"] - WALL, (z_bi + z_rim) / 2), (0.0, -1.0, 0.0)))
        if name == "BARO":
            seat_d, seat_t = eptfe_seat()
            vx = (right + d["x1"]) / 2
            vz = z_bi + seat_d / 2 + 1.0
            d["ops"].append(("vent", (vx, d["y0"] - WALL, vz), (0.0, -1.0, 0.0)))
            d["seat"] = (seat_d, seat_t)
    if name != "UV":
        d["lugs"] = [(x, y) for x in (d["x0"] - WALL - LUG_DIAG, d["x1"] + WALL + LUG_DIAG)
                     for y in (d["y0"] - WALL - LUG_DIAG, d["y1"] + WALL + LUG_DIAG)]
        d["mount_lugs"], d["floor_bosses"], d["keepouts"] = list(d["lugs"]), [], []
    return d


def inside(name):
    d = dims(name)
    if name == "UV":                       # the crown's bore, as its bounding square (corners outside the drum)
        cx, cy = d["axis"]
        return Box(cx - d["r_in"], cy - d["r_in"], cx + d["r_in"], cy + d["r_in"], d["z_bi"], d["z_joint"], "UV crown inside")
    return Box(d["x0"], d["y0"], d["x1"], d["y1"], d["z_bi"], d["z_rim"], f"{name} pod box inside")


def openings(name):
    """[(kind, centre on the outside face, outward axis)], kinds: gland, lead_gland, vent, window."""
    return list(dims(name)["ops"])


def board_holes():
    """The Perma-Proto's mounting holes (x, y, drill) in the box frame."""
    return list(PP.OUTLINE["mounting_holes"])


class MountFace(tuple):
    """mount_face()'s result: still unpacks as (plane, holes); .keepouts adds the circles (x, y, d) on that plane that
    the mating part (Task 7's arm or cap) must stay clear of (the UV floor gland; none on TH/BARO)."""

    def __new__(cls, plane, holes, keepouts):
        self = super().__new__(cls, (plane, holes))
        self.plane, self.holes, self.keepouts = plane, holes, keepouts
        return self


def mount_face(name):
    """MountFace((origin, normal), [(x, y)], keepouts=[(x, y, d)]): the back face's plane, the M3 insert centres in it
    and the keep-out circles on it (box frame). Unpacks as ((origin, normal), holes) as before."""
    d = dims(name)
    origin = ((d["x0"] + d["x1"]) / 2, (d["y0"] + d["y1"]) / 2, d["z_bo"])
    return MountFace((origin, (0.0, 0.0, -1.0)), d["mount_lugs"] + d["floor_bosses"], list(d["keepouts"]))


def screws(name):
    bd, bdepth = S.val("pod_insert_bore")
    return [dict(xy=xy, bore_d=bd, bore_depth=bdepth, screw=S.val("pod_screw")) for xy in dims(name)["lugs"]]


def wall_t(name, kind):
    """Plastic an opening passes through."""
    d = dims(name)
    if kind == "breather":                      # the drum wall, less the breather's seat
        return d["r_out"] - d["breather"]["r_flat"]
    return d["lid_t"] if kind == "window" else WALL


def _groove_path(d, n=24):
    """The groove's centreline (the rim's middle): a rounded rectangle, as points."""
    o, r = WALL / 2, R_IN + WALL / 2
    xa, xb, ya, yb = d["x0"] - o, d["x1"] + o, d["y0"] - o, d["y1"] + o
    pts = []
    for (cx, cy), a0 in (((xb - r, ya + r), -90), ((xb - r, yb - r), 0), ((xa + r, yb - r), 90), ((xa + r, ya + r), 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    out = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        k = max(1, int(math.hypot(bx - ax, by - ay) / 1.0))
        out += [(ax + (bx - ax) * i / k, ay + (by - ay) * i / k) for i in range(k)]
    return out


def groove(name):
    d = dims(name)
    cord = S.val("pod_oring")
    if name == "UV":                       # the crown: a radial groove round the body's spigot, below the bayonet
        cx, cy = d["axis"]
        rc = d["r_sp"] - d["groove_d"] / 2
        path = [(cx + rc * math.cos(2 * math.pi * i / 180), cy + rc * math.sin(2 * math.pi * i / 180)) for i in range(180)]
        return dict(cord=cord, width=d["groove_w"], depth=d["groove_d"], length=2 * math.pi * rc, path=path,
                    z=d["z_joint"] - CROWN_ORING_Z, radial=True, squeeze=round(1 - (d["groove_d"] + CROWN_C) / cord, 3),
                    probes=[(cx + rc * math.cos(a), cy + rc * math.sin(a)) for a in (0.3, 1.9, 3.5, 5.1)])
    o = WALL / 2
    xm, ym = (d["x0"] + d["x1"]) / 2, (d["y0"] + d["y1"]) / 2
    path = _groove_path(d)
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:] + path[:1]))
    return dict(cord=cord, width=round(1.35 * cord, 2), depth=round(0.75 * cord, 2), length=length, path=path,
                probes=[(xm, d["y0"] - o), (xm, d["y1"] + o), (d["x0"] - o, ym), (d["x1"] + o, ym)])


def gland_nut(name, kind):
    """The gland's thread and locknut inside the box, as a solid (for clearance checks)."""
    (c, axis), = [(c, a) for k, c, a in openings(name) if k == kind]
    r = _gland(kind)[1] / 2
    inner = tuple(ci - WALL * ai for ci, ai in zip(c, axis))
    return cq.Solid.makeCylinder(r, _nut_depth(), cq.Vector(*inner), cq.Vector(*(-a for a in axis)))


def baffle_gaps(name):
    """BARO: the smallest free gap round the baffle fin to the side walls and the lid (the air's way in)."""
    d = dims(name)
    bx0, bx1, _y0, _y1, _z0, bz1 = _baffle_box(d)
    return min(bx0 - d["x0"], d["x1"] - bx1, d["z_rim"] - bz1)


# ------------------------------------------------------------------ the solids
def _rrect(x0, y0, x1, y1, r, z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, (y0 + y1) / 2)
            .rect(x1 - x0, y1 - y0).extrude(z1 - z0).edges("|Z").fillet(r))


def _lug_web(d, x, y, lug_r):
    """v1: the web that joins a corner lug to the walls: two flat faces parallel to the corner's diagonal, each
    tangent to the lug and running back to its wall (they fill the notch between the lug and the rounded corner)."""
    xo = d["x1"] + WALL if x > d["x1"] else d["x0"] - WALL       # the outer faces this lug sits beyond
    yo = d["y1"] + WALL if y > d["y1"] else d["y0"] - WALL
    sx, sy = (1.0 if xo > d["x0"] else -1.0), (1.0 if yo > d["y0"] else -1.0)
    k = lug_r / math.sqrt(2)
    t1 = (x + sx * k, y - sy * k)                                  # tangent point on the x-wall side
    t2 = (x - sx * k, y + sy * k)                                  # tangent point on the y-wall side
    a = (xo, t1[1] + sy * sx * (xo - t1[0]))                       # along the diagonal from t1 back to the x-wall
    b = (t2[0] + sx * sy * (yo - t2[1]), yo)                       # along the diagonal from t2 back to the y-wall
    rr = R_IN + WALL
    k0 = (xo - sx * rr, yo - sy * rr)                              # the rounded corner's centre (inside the wall)
    return [a, t1, (x, y), t2, b, k0]


def _outline(d, z0, z1):
    """The outer wall's rounded rectangle plus the four corner lugs and (v1) the webs joining them to the walls."""
    lug_r = S.val("pod_insert_bore")[0] / 2 + LUG_WALL
    s = _rrect(d["x0"] - WALL, d["y0"] - WALL, d["x1"] + WALL, d["y1"] + WALL, R_IN + WALL, z0, z1)
    for x, y in d["lugs"]:
        s = s.union(cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(lug_r).extrude(z1 - z0))
        s = s.union(cq.Workplane("XY").workplane(offset=z0).polyline(_lug_web(d, x, y, lug_r)).close().extrude(z1 - z0))
    return s


def _teardrop_y(cx, cz, r, y_in, length):
    """A hole along -y from y_in, teardrop-capped toward +z (print up) at TEAR x r."""
    k = r / math.sqrt(2)
    prof = (cq.Workplane("XY").circle(r).extrude(length)
            .union(cq.Workplane("XY").polyline([(-k, k), (0, r * math.sqrt(2)), (k, k)]).close().extrude(length))
            .intersect(cq.Workplane("XY").center(0, (TEAR * r - 2 * r) / 2).rect(2 * r + 1, TEAR * r + 2 * r)
                       .extrude(length)))
    s = prof.val().rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90)       # +y -> +z, extrusion +z -> -y
    return cq.Workplane("XY").add(s.translate(cq.Vector(cx, y_in, cz)))


def _baffle_box(d):
    (_k, (vx, _vy, vz), _a), = [o for o in d["ops"] if o[0] == "vent"]
    half = VENT_D / 2 + BAFFLE_OVER
    y = d["y0"] + BAFFLE_GAP
    return vx - half, vx + half, y, y + BAFFLE_T, d["z_bi"], vz + VENT_D / 2 + BAFFLE_OVER


@lru_cache(maxsize=None)
def _build(name, standoffs=True, baffle=True):
    d = dims(name)
    if name == "UV":
        return _solid(_crown_body(d, standoffs), "UV body")
    bd, bdepth = S.val("pod_insert_bore")
    s = _outline(d, d["z_bo"], d["z_rim"])
    s = s.cut(_rrect(d["x0"], d["y0"], d["x1"], d["y1"], R_IN, d["z_bi"], d["z_rim"] + 1))
    for x, y in d["lugs"]:                    # lid inserts from the rim
        s = s.cut(cq.Workplane("XY").workplane(offset=d["z_rim"] - bdepth).center(x, y).circle(bd / 2).extrude(bdepth + 1))
    for x, y in d["floor_bosses"]:            # UV: blind floor bosses for two of the mount inserts
        s = s.union(cq.Workplane("XY").workplane(offset=d["z_bi"] - 0.5).center(x, y).circle(bd / 2 + LUG_WALL)
                    .extrude(d["z_bo"] + d["boss_depth"] - d["z_bi"] + 0.5))
    for x, y in d["mount_lugs"] + d["floor_bosses"]:     # mount inserts from the back
        s = s.cut(cq.Workplane("XY").workplane(offset=d["z_bo"] - 1).center(x, y).circle(bd / 2).extrude(bdepth + 1))
    if standoffs:
        keep, pilot = S.val("mount_keep"), S.val("pod_pilot_m3")
        assert S.val("pod_screw")[2] / 2 <= keep + 1e-9, "the board screw's head is wider than mount_keep"
        for x, y, _dr in board_holes():
            s = s.union(cq.Workplane("XY").workplane(offset=d["z_bi"] - 0.5).center(x, y).circle(keep)
                        .extrude(-d["t"] - d["z_bi"] + 0.5))
            s = s.cut(cq.Workplane("XY").workplane(offset=d["z_bo"] + 1.0).center(x, y).circle(pilot / 2)
                      .extrude(-d["t"] - d["z_bo"]))
    for kind, (cx, cy, cz), axis in d["ops"]:
        if kind in ("gland", "lead_gland") and axis[1] < 0:
            s = s.cut(_teardrop_y(cx, cz, _gland(kind)[0] / 2, d["y0"] + 1.0, WALL + 2.0))
        elif kind == "gland":                                       # UV: through the floor (flat on the bed)
            s = s.cut(cq.Workplane("XY").workplane(offset=d["z_bo"] - 1).center(cx, cy)
                      .circle(S.val("gland")[0] / 2).extrude(WALL + 2))
        elif kind == "vent":
            s = s.cut(_teardrop_y(cx, cz, VENT_D / 2, d["y0"] + 1, WALL + 2))       # v1: teardrop, as the glands
            sd, st = d["seat"]
            s = s.cut(_teardrop_y(cx, cz, sd / 2, d["y0"] + 1, st + 1))             # v1: the seat too
            if baffle:
                bx0, bx1, by0, by1, bz0, bz1 = _baffle_box(d)
                s = s.union(cq.Workplane("XY").add(cq.Solid.makeBox(bx1 - bx0, by1 - by0, bz1 - bz0 + 0.5,
                                                                    cq.Vector(bx0, by0, bz0 - 0.5))))
    v = s.val()
    if not isinstance(v, cq.Solid):
        sols = v.Solids()
        assert len(sols) == 1, f"{name} body is {len(sols)} solids"
        v = sols[0]
    return v


def body(name, baffle=True):
    return _build(name, True, baffle)


def walls(name):
    """The body without the board's standoffs (the board and its copper side are checked against this)."""
    return _build(name, False, True)


@lru_cache(maxsize=None)
def lid(name):
    d = dims(name)
    if name == "UV":
        return _solid(_crown_lid(d), "UV lid")
    g = groove(name)
    z0, z1 = d["z_rim"], d["z_rim"] + d["lid_t"]
    s = _outline(d, z0, z1)
    top = s.faces(">Z").val()
    s = s.newObject(top.outerWire().Edges()).chamfer(LID_CHAMFER)     # v1: the top outer edge
    o, r = WALL / 2, R_IN + WALL / 2
    xa, xb, ya, yb = d["x0"] - o, d["x1"] + o, d["y0"] - o, d["y1"] + o
    hw = g["width"] / 2
    ring = (_rrect(xa - hw, ya - hw, xb + hw, yb + hw, r + hw, z0 - 1, z0 + g["depth"])
            .cut(_rrect(xa + hw, ya + hw, xb - hw, yb - hw, r - hw, z0 - 2, z0 + g["depth"] + 1)))
    s = s.cut(ring)
    for x, y in d["lugs"]:
        s = s.cut(cq.Workplane("XY").workplane(offset=z0 - 1).center(x, y).circle(SCREW_HOLE / 2).extrude(d["lid_t"] + 2))
    if "window" in d:
        wdw = d["window"]
        cx, cy = wdw["c"]
        s = s.cut(cq.Workplane("XY").workplane(offset=z1 - wdw["depth"]).center(cx, cy).circle(wdw["recess_d"] / 2)
                  .extrude(wdw["depth"] + 1))
        s = s.cut(cq.Workplane("XY").workplane(offset=z0 - 1).center(cx, cy).circle(wdw["aperture"] / 2)
                  .extrude(d["lid_t"] + 2))
    v = s.val()
    if not isinstance(v, cq.Solid):
        sols = v.Solids()
        assert len(sols) == 1, f"{name} lid is {len(sols)} solids"
        v = sols[0]
    return v


def _solid(s, what):
    v = s.val()
    if not isinstance(v, cq.Solid):
        sols = v.Solids()
        assert len(sols) == 1, f"{what} is {len(sols)} solids"
        v = sols[0]
    return v


# ------------------------------------------------------------------ the UV crown
def _crown_dims(d, p, nut_r):
    """The UV crown's numbers, added to d (box frame). The contents are the TH box's (the board, its parts, the plug
    and the port gland's nut, each grown by CLEAR); the crown's axis runs through the plug's axis (x = px) so the port
    gland points straight out of the drum, and sits where the smallest circle round the contents is centred."""
    pts = []
    for b in [b for part in p.parts for b in part.boxes]:
        pts += [(x, y) for x in (b.x0 - CLEAR, b.x1 + CLEAR) for y in (b.y0 - CLEAR, b.y1 + CLEAR)]
    pts += [(x, y) for x in (d["x0"], d["x1"]) for y in (-CLEAR, d["y1"])]
    pts += [(d["px"] + s * (nut_r + NUT_GAP), d["y0"]) for s in (-1.0, 1.0)]
    cx = d["px"]
    best = min((max(math.hypot(x - cx, y - cy) for x, y in pts), cy) for cy in [i * 0.125 for i in range(-80, 240)])
    r_in = float(math.ceil(best[0] + 0.5))
    cy = best[1]
    r_sp = r_in + CROWN_SP_T
    r_out = r_sp + CROWN_C + CROWN_SKIRT_T
    z_ledge = max(d["top"] + CLEAR, d["pz"] + CROWN_GLAND_FACE / 2 + 1.0)    # the gland's spot face stays under it
    z_joint = z_ledge + CROWN_SP_H
    apex = z_joint + CROWN_RISE
    cord = S.val("pod_oring")
    mat, wd, wt = S.val("uv_window")
    flat = apex - 0.6                                           # the apex is cut flat here, so the disc sits flush
    d.update(axis=(cx, cy), r_in=r_in, r_sp=r_sp, r_out=r_out, z_ledge=z_ledge, z_joint=z_joint, apex=apex, z_flat=flat,
             z_rim=z_joint, z_lid0=z_ledge, lid_t=CROWN_DOME_T, lugs=[], mount_lugs=[], keepouts=[],
             groove_d=round(0.75 * cord - CROWN_C, 2), groove_w=round(1.35 * cord, 2))
    d["window"] = dict(c=(cx, cy), recess_d=wd + 0.3, depth=wt, aperture=wd - 2 * WINDOW_LEDGE, material=mat)
    d["ops"].append(("window", (cx, cy, flat), (0.0, 0.0, 1.0)))
    y_land = d["y0"]                                            # the nut's flat land inside (as the TH box's wall)
    d["y_land"] = y_land
    d["ops"].append(("gland", (d["px"], y_land - WALL, d["pz"]), (0.0, -1.0, 0.0)))
    a = math.radians(CROWN_BREATHER_A)
    u = (math.cos(a), math.sin(a), 0.0)
    zb = (d["z_bi"] + z_ledge) / 2
    d["breather"] = dict(axis=u, z=zb, d=S.val("uv_breather"), seat=eptfe_seat(), r_flat=r_in + eptfe_seat()[1])
    d["ops"].append(("breather", (cx + r_out * u[0], cy + r_out * u[1], zb), u))
    # the LTR390, sensor up under the window's aperture tube, on two M2.5 screws into bosses under the dome
    z_b = apex - CROWN_DOME_T - LTR_DROP
    d["ltr"] = dict(c=(cx, cy), z=z_b, holes=[(cx - LTR_HOLES[0], cy - LTR_HOLES[1]), (cx + LTR_HOLES[0], cy + LTR_HOLES[1])],
                    size=S.val("ltr390"))
    # the aperture tube's bottom: over the chip by LTR_GAP and over both factory QT sockets (whose tops reach past the
    # tube's outside radius) by LTR_QT_GAP. The pilots stop LTR_PILOT_PAST past the M2.5 screw's tip (the screw passes
    # breakout_t of board), so the plastic over them and beside the window recess stays thick
    d["ltr"]["tube_bot"] = z_b + max(0.8 + LTR_GAP, LTR_QT_H + LTR_QT_GAP)
    d["ltr"]["pilot_top"] = z_b + S.val("ltr_screw")[1] - S.val("breakout_t") + LTR_PILOT_PAST
    # four floor bosses for the mount inserts, on a circle of CROWN_BOSS_R, clear of the board and its copper side
    br = S.val("pod_insert_bore")[0] / 2 + LUG_WALL
    w, h = S.val("permaproto_q")

    def ok(a):
        x, y = cx + CROWN_BOSS_R * math.cos(math.radians(a)), cy + CROWN_BOSS_R * math.sin(math.radians(a))
        return not (-CLEAR - br < x < w + CLEAR + br and -CLEAR - br < y < h + CLEAR + br)
    good = [a for a in range(0, 360) if ok(a)]
    assert good, "no room for the UV floor bosses"
    pick = [max(good, key=lambda a: min(abs(((a - 270) + 180) % 360 - 180), 999))]
    while len(pick) < 4:
        pick.append(max(good, key=lambda a: min(abs((a - b + 180) % 360 - 180) for b in pick)))
    d["floor_bosses"] = [(cx + CROWN_BOSS_R * math.cos(math.radians(a)), cy + CROWN_BOSS_R * math.sin(math.radians(a)))
                         for a in sorted(pick)]


def _ring(d, r0, r1, z0, z1, a0=0.0, a1=360.0):
    """A ring (or a sector of one, degrees a0..a1) about the crown's axis."""
    cx, cy = d["axis"]
    if a1 - a0 >= 360.0:
        s = cq.Workplane("XY").workplane(offset=z0).circle(r1).circle(r0).extrude(z1 - z0)
    else:
        s = (cq.Workplane("XZ").center((r0 + r1) / 2, (z0 + z1) / 2).rect(r1 - r0, z1 - z0)
             .revolve(a1 - a0, (-(r0 + r1) / 2, -(z0 + z1) / 2), (-(r0 + r1) / 2, 1 - (z0 + z1) / 2)))
        s = s.rotate((0, 0, 0), (0, 0, 1), a0)
    return s.translate((cx, cy, 0))


def _bayonet_angles(d):
    return [360.0 * k / CROWN_LUGS + 90.0 for k in range(CROWN_LUGS)]      # entry slots (none over the gland at 270);
                                                                             # the lugs lock CROWN_TURN on


def _crown_body(d, standoffs=True):
    cx, cy = d["axis"]
    bd, bdepth = S.val("pod_insert_bore")
    s = (cq.Workplane("XY").workplane(offset=d["z_bo"]).center(cx, cy).circle(d["r_out"]).extrude(d["z_ledge"] - d["z_bo"])
         .union(cq.Workplane("XY").workplane(offset=d["z_ledge"] - 0.5).center(cx, cy).circle(d["r_sp"])
                .extrude(d["z_joint"] - d["z_ledge"] + 0.5)))
    ri, k, zl0 = d["r_in"], CROWN_SP_IN, d["z_ledge"]
    bore = (cq.Workplane("XZ").polyline([(0, d["z_bi"]), (ri, d["z_bi"]), (ri, zl0 - k), (ri - k, zl0), (ri - k, d["z_joint"] + 1),
                                         (0, d["z_joint"] + 1)]).close()
            .revolve(360, (0, 0, 0), (0, 1, 0)).translate((cx, cy, 0)))
    s = s.cut(bore)
    # the port gland: a flat land inside (the nut's seat, as the TH wall), a round spot face outside, the hole
    px, pz, F, yl = d["px"], d["pz"], CROWN_GLAND_FACE, d["y_land"]
    land = (cq.Workplane("XY").add(cq.Solid.makeBox(F, yl - (cy - d["r_out"]), d["z_ledge"] - d["z_bi"],
                                                    cq.Vector(px - F / 2, cy - d["r_out"], d["z_bi"])))
            .intersect(cq.Workplane("XY").workplane(offset=d["z_bi"] - 1).center(cx, cy).circle(d["r_out"]).extrude(60)))
    s = s.union(land)
    s = s.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(F / 2, 20.0, cq.Vector(px, yl - WALL, pz), cq.Vector(0, -1, 0))))
    s = s.cut(_teardrop_y(px, pz, S.val("gland")[0] / 2, yl + 1.0, WALL + 2.0))
    s = s.cut(_breather_cut(d))
    # floor bosses: blind M3 mount inserts from below
    for x, y in d["floor_bosses"]:
        s = s.union(cq.Workplane("XY").workplane(offset=d["z_bi"] - 0.5).center(x, y).circle(bd / 2 + LUG_WALL)
                    .extrude(d["z_bo"] + d["boss_depth"] - d["z_bi"] + 0.5))
        s = s.cut(cq.Workplane("XY").workplane(offset=d["z_bo"] - 1).center(x, y).circle(bd / 2).extrude(bdepth + 1))
    if standoffs:
        keep, pilot = S.val("mount_keep"), S.val("pod_pilot_m3")
        for x, y, _dr in board_holes():
            s = s.union(cq.Workplane("XY").workplane(offset=d["z_bi"] - 0.5).center(x, y).circle(keep)
                        .extrude(-d["t"] - d["z_bi"] + 0.5))
            s = s.cut(cq.Workplane("XY").workplane(offset=d["z_bo"] + 1.0).center(x, y).circle(pilot / 2)
                      .extrude(-d["t"] - d["z_bo"]))
    # the radial O-ring groove, then the bayonet: an entry slot down from the spigot's top and a channel round
    zj, rs = d["z_joint"], d["r_sp"]
    zo = zj - CROWN_ORING_Z
    s = s.cut(_ring(d, rs - d["groove_d"], rs + 1, zo - d["groove_w"] / 2, zo + d["groove_w"] / 2))
    lw, lh, ld = CROWN_LUG
    dep, zl = ld + 0.3, zj - CROWN_LUG_Z
    for a in _bayonet_angles(d):
        half = math.degrees((lw / 2 + 0.3) / rs)
        s = s.cut(_ring(d, rs - dep, rs + 1, zl - lh / 2 - 0.3, zj + 1, a - half, a + half))
        s = s.cut(_ring(d, rs - dep, rs + 1, zl - lh / 2 - 0.3, zl + lh / 2 + 0.3, min(a, a + CROWN_TURN) - half,
                         max(a, a + CROWN_TURN) + half))
    for x, y in detents(d):                 # the detent bumps: round posts on the channel floor, the lug rides over them
        s = s.union(cq.Workplane("XY").workplane(offset=zl - lh / 2 - 0.3).center(x, y).circle(CROWN_DETENT[0])
                    .extrude(lh + 0.6))
    return s


def _breather_cut(d):
    """The breather: a flat-bottomed seat cut from the bore out to r_flat, and the hole on through the drum wall."""
    cx, cy = d["axis"]
    b = d["breather"]
    u, zb = b["axis"], b["z"]
    sd, r0 = b["seat"][0], d["r_in"] - 1.0             # from just inside the bore, so nothing else inside is cut
    at = cq.Vector(cx + r0 * u[0], cy + r0 * u[1], zb)
    seat = cq.Solid.makeCylinder(sd / 2, b["r_flat"] - r0, at, cq.Vector(*u))
    hole = cq.Solid.makeCylinder(b["d"] / 2, d["r_out"] - r0 + 1.0, at, cq.Vector(*u))
    return cq.Workplane("XY").add(seat).union(cq.Workplane("XY").add(hole))


def detents(d):
    """The bayonet detents (x, y): one per channel on its floor (r_sp - lug depth - 0.3), just behind the locked lug
    (0.3 clear of its trailing end, toward the entry slot), so turning the lid to lock rides the lug over it."""
    cx, cy = d["axis"]
    lw, _lh, ld = CROWN_LUG
    rf = d["r_sp"] - ld - 0.3
    lug_half = math.degrees((lw / 2) / d["r_sp"])
    step = math.degrees((0.3 + CROWN_DETENT[0]) / rf)
    sgn = 1.0 if CROWN_TURN < 0 else -1.0                     # from the locked lug back toward the entry slot
    out = []
    for a in _bayonet_angles(d):
        t = math.radians(a + CROWN_TURN + sgn * (lug_half + step))
        out.append((cx + rf * math.cos(t), cy + rf * math.sin(t)))
    return out


def _crown_lid(d):
    cx, cy = d["axis"]
    ro, zl, zj, apex = d["r_out"], d["z_ledge"], d["z_joint"], d["apex"]
    ai, bi = ro - CROWN_DOME_T, CROWN_RISE - CROWN_DOME_T
    n = 8                                       # quarter-ellipses as splines (one smooth face each, not 40 bands)
    ts = [math.pi / 2 * i / n for i in range(n + 1)]
    outer = [(ro * math.cos(t), zj + CROWN_RISE * math.sin(t)) for t in ts]
    inner = [(ai * math.cos(t), zj + bi * math.sin(t)) for t in ts]
    outer[-1], inner[-1] = (0.0, apex), (0.0, zj + bi)
    bore = d["r_sp"] + CROWN_C
    w = (cq.Workplane("XZ").moveTo(bore, zl).lineTo(ro, zl).lineTo(*outer[0])
         .spline(outer[1:], tangents=[(0, 1), (-1, 0)], includeCurrent=True)
         .lineTo(*inner[-1]).spline(inner[::-1][1:], tangents=[(1, 0), (0, -1)], includeCurrent=True)
         .lineTo(bore, zj).close())
    s = w.revolve(360, (0, 0, 0), (0, 1, 0)).translate((cx, cy, 0))
    s = s.cut(cq.Workplane("XY").workplane(offset=d["z_flat"]).center(cx, cy).circle(ro + 5).extrude(10))   # apex flat
    wdw, L = d["window"], d["ltr"]
    tube_bot = L["tube_bot"]
    s = s.union(cq.Workplane("XY").workplane(offset=tube_bot).center(cx, cy).circle(wdw["aperture"] / 2 + 2.0)
                .extrude(apex - tube_bot - 1.0))
    for x, y in L["holes"]:
        s = s.union(cq.Workplane("XY").workplane(offset=L["z"] + LTR_CU).center(x, y).circle(2.5)
                    .extrude(apex - L["z"] - LTR_CU - 1.5))
        s = s.cut(cq.Workplane("XY").workplane(offset=L["z"] - 1).center(x, y).circle(S.val("pod_pilot_m25") / 2)
                  .extrude(L["pilot_top"] - L["z"] + 1))
    s = s.cut(cq.Workplane("XY").workplane(offset=d["z_flat"] - wdw["depth"]).center(cx, cy)
              .circle(wdw["recess_d"] / 2).extrude(5))
    s = s.cut(cq.Workplane("XY").workplane(offset=tube_bot - 1).center(cx, cy).circle(wdw["aperture"] / 2)
              .extrude(apex - tube_bot + 2))
    lw, lh, ld = CROWN_LUG
    zc = zj - CROWN_LUG_Z
    for a in _bayonet_angles(d):
        half = math.degrees((lw / 2) / d["r_sp"])
        b = a + CROWN_TURN
        s = s.union(_ring(d, bore - ld, bore + 0.5, zc - lh / 2, zc + lh / 2, b - half, b + half))
    return s


# ------------------------------------------------------------------ output
STL = _HERE / "stl"


def write_stls():
    STL.mkdir(exist_ok=True)
    out = []
    for n in pods.POD_NAMES:
        d = dims(n)
        for part, shape, z in (("body", body(n), d["z_bo"]), ("lid", lid(n), d.get("z_lid0", d["z_rim"]))):
            p = STL / f"pod-{n.lower()}-{part}.stl"
            cq.exporters.export(shape.translate(cq.Vector(0, 0, -z)), str(p), tolerance=0.05, angularTolerance=0.2)
            out.append(p)
    return out


def report():
    lines = []
    for n in pods.POD_NAMES:
        d = dims(n)
        ins = inside(n)
        bb = body(n).BoundingBox()
        g = groove(n)
        lines.append(f"== {n}  (up = {up(n)})")
        lines.append(f"  inside   {ins.x1 - ins.x0:.2f} x {ins.y1 - ins.y0:.2f} x {ins.z1 - ins.z0:.2f}  "
                     f"(x {ins.x0:.2f}..{ins.x1:.2f}, y {ins.y0:.2f}..{ins.y1:.2f}, z {ins.z0:.2f}..{ins.z1:.2f})")
        if n == "UV":
            lines.append(f"  crown    Ø{2 * d['r_out']:.1f} x {d['z_flat'] - d['z_bo']:.1f} tall (drum to the ledge "
                         f"{d['z_ledge'] - d['z_bo']:.1f}, lid skirt {CROWN_SP_H:g}, dome rise {CROWN_RISE:g}); bayonet "
                         f"{CROWN_LUGS} lugs, {abs(CROWN_TURN):g} deg twist, clockwise from above to lock, a detent "
                         f"({CROWN_DETENT[1]:g} catch) at the locked end")
            lines.append(f"  seal     cord {g['cord']} in a {g['width']} x {g['depth']} groove round the spigot (radial, "
                         f"squeeze {g['squeeze']:.0%}), centreline {g['length']:.1f} long")
            lines.append(f"  LTR390   on 2 M2.5 bosses under the window, board top Z {d['ltr']['z']:.2f}; aperture tube "
                         f"from Z {d['ltr']['tube_bot']:.2f}; pilots to Z {d['ltr']['pilot_top']:.2f}")
        else:
            lines.append(f"  outside  {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen + d['lid_t']:.2f} with the lid "
                         f"(walls {WALL}, lid {d['lid_t']}, lugs included)")
            lines.append(f"  seal     cord {g['cord']} in a {g['width']} x {g['depth']} lid groove, centreline {g['length']:.1f} long")
        for k, c, a in openings(n):
            lines.append(f"  {k:<10} at ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}) axis {a}")
        (o, nrm), holes = mount_face(n)
        lines.append(f"  mount    plane z {o[2]:.2f} normal {nrm}; M3 inserts at "
                     + ", ".join(f"({x:.2f}, {y:.2f})" for x, y in holes)
                     + "".join(f"; keep-out ({x:.2f}, {y:.2f}) d {kd:.1f}" for x, y, kd in mount_face(n).keepouts))
        if n == "BARO":
            lines.append(f"  baffle   {_baffle_box(d)}; free gap round it {baffle_gaps(n):.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
    for p in write_stls():
        print("wrote", p.relative_to(_HERE.parent))
