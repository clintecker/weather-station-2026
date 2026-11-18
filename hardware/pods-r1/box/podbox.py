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
  BARO vent        a VENT_D hole through the bottom wall (axis down), an optional ePTFE membrane seat recessed in the
                   inner face (sources baro_eptfe), and a baffle: a fin standing off the back wall BAFFLE_GAP above
                   the hole, overhanging it by BAFFLE_OVER on the three open sides, so there is no straight line from
                   outside to the BMP581 (checked by tests/test_pods_box.py with real segments).
  UV window        sources uv_window (material, disc d, t): a recess d + 0.3 across and t deep in the lid's top face,
                   so the disc sits flush (no pond on it), bedded in silicone, over an aperture d - 3.0 across; centred
                   over the LTR390's chip (sources ltr390_sensor).
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
UPS = {"TH": (0.0, 1.0, 0.0), "BARO": (0.0, 1.0, 0.0), "UV": (0.0, 0.0, 1.0)}


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
    if name == "UV":
        # the cable rises through the floor, bends over at plug_bend and runs level into the jack
        gy = mouth - body_len - S.val("plug_bend")
        d["y0"] = min(plug_end - CLEAR, gy - nut_r - NUT_GAP)
        d["ops"].append(("gland", (px, gy, d["z_bo"]), (0.0, 0.0, -1.0)))
        mat, wd, wt = S.val("uv_window")
        sx, sy = S.val("ltr390_sensor")
        u2 = p.part("U2")
        cx, cy = u2.origin[0] + sx, u2.origin[1] + sy
        rr = wd / 2 + 0.15
        d["x1"] = max(d["x1"], cx + rr + 1.0)
        d["y1"] = max(d["y1"], cy + rr + 1.0)
        d["lid_t"] = max(LID_T, wt + 1.2)
        d["window"] = dict(c=(cx, cy), recess_d=wd + 0.3, depth=wt, aperture=wd - 2 * WINDOW_LEDGE, material=mat)
        d["ops"].append(("window", (cx, cy, z_rim + d["lid_t"]), (0.0, 0.0, 1.0)))
    else:
        d["y0"] = plug_end - max(CLEAR, _nut_depth())
        d["ops"].append(("gland", (px, d["y0"] - WALL, pz), (0.0, -1.0, 0.0)))
        right = px + nut_r                                         # the port gland's nut, right edge
        if name == "TH":
            lx = (right + d["x1"]) / 2
            d["ops"].append(("lead_gland", (lx, d["y0"] - WALL, (z_bi + z_rim) / 2), (0.0, -1.0, 0.0)))
        if name == "BARO":
            seat_d = S.val("baro_eptfe")[0] + 0.4
            vx = (right + d["x1"]) / 2
            vz = z_bi + seat_d / 2 + 1.0
            d["ops"].append(("vent", (vx, d["y0"] - WALL, vz), (0.0, -1.0, 0.0)))
            d["seat"] = (seat_d, S.val("baro_eptfe")[1])
    d["lugs"] = [(x, y) for x in (d["x0"] - WALL - LUG_DIAG, d["x1"] + WALL + LUG_DIAG)
                 for y in (d["y0"] - WALL - LUG_DIAG, d["y1"] + WALL + LUG_DIAG)]
    d["mount_lugs"], d["floor_bosses"], d["keepouts"] = list(d["lugs"]), [], []
    if name == "UV":
        (_k, (gx, gy, _gz), _a), = [o for o in d["ops"] if o[0] == "gland"]
        br = S.val("pod_insert_bore")[0] / 2 + LUG_WALL
        by = gy + nut_r + NUT_GAP + br                          # inboard of the gland's nut
        d["floor_bosses"] = [(d["x0"] + BOSS_MARGIN + br, by), (d["x1"] - BOSS_MARGIN - br, by)]
        d["mount_lugs"] = [xy for xy in d["lugs"] if xy[1] > gy]          # the far end's two lugs
        d["keepouts"] = [(gx, gy, max(GLAND_KEEP, S.val("gland_pg7")[2] + 1.4))]
    return d


def inside(name):
    d = dims(name)
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
    return dims(name)["lid_t"] if kind == "window" else WALL


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


def _outline(d, z0, z1):
    """The outer wall's rounded rectangle plus the four corner lugs."""
    lug_r = S.val("pod_insert_bore")[0] / 2 + LUG_WALL
    s = _rrect(d["x0"] - WALL, d["y0"] - WALL, d["x1"] + WALL, d["y1"] + WALL, R_IN + WALL, z0, z1)
    for x, y in d["lugs"]:
        s = s.union(cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(lug_r).extrude(z1 - z0))
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
            s = s.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(VENT_D / 2, WALL + 2, cq.Vector(cx, d["y0"] + 1, cz),
                                                                   cq.Vector(0, -1, 0))))
            sd, st = d["seat"]
            s = s.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(sd / 2, st + 1, cq.Vector(cx, d["y0"] + 1, cz),
                                                                   cq.Vector(0, -1, 0))))
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
    g = groove(name)
    z0, z1 = d["z_rim"], d["z_rim"] + d["lid_t"]
    s = _outline(d, z0, z1)
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


# ------------------------------------------------------------------ output
STL = _HERE / "stl"


def write_stls():
    STL.mkdir(exist_ok=True)
    out = []
    for n in pods.POD_NAMES:
        d = dims(n)
        for part, shape, z in (("body", body(n), d["z_bo"]), ("lid", lid(n), d["z_rim"])):
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
