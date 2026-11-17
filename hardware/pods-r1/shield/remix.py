"""The shield remix: Clint's top cap (object_70) with screw bosses for the UV pod box, and his L-arm (object_72) with
mounting faces for the TH and BARO pod boxes.

Run `python shield/remix.py` (with .venv-cad) to print the checks and write the two remixed STLs to sources.shield_out
(a local folder OUTSIDE git: they are derived from the shield's meshes, whose licence is not known). Nothing derived from
the meshes is written anywhere else. The added solids are built with CadQuery, then fused to (or cut from) the original
meshes with manifold3d booleans.

FRAME. The shield frame of shield/assemble.py: Z up, the plate axis on the Z axis, Z = 0 on the arm's pocket floor. The
pod boxes come from box/podbox.py in their own box frame; box_placed() turns them (quarter turns only) and moves them.

WHAT THE MESHES SAY (measured here, not assumed)
  cap   its flat top is a DISC of radius 38.0 at Z 145.75 (the roof then falls away all round to the 100 x 100 rim),
        a 2.4 mm roof. Under the roof an inner cone (a funnel, r 25.5 at the cap's bottom face to r 35.5 where it meets
        the roof) leaves only r < 25 with a straight way up to the roof's underside from below.
  arm   a 5.0 mm base plate (Z -4..1) round the cup's pocket, an upright at its -y end (Y -89..-84, Z up to 60) with a
        gusset, and two pairs of hose-clamp slots through the upright (the pole clamp: the band runs through them, round
        the pole behind the upright and round the gusset in front). The arm is printed on its base plate in the 3MF.
  cup   radius 30.0 at most; its Ø5 through-hole at (-12, 4) runs down through the disc and opens under it at Z ~22.6,
        beside the cup's column: the TH lead's way out (no new hole in the cup).

CHOICES (Task 7; the brief left these to the builder)
  UV box on the cap
    No placement puts all four of the UV box's mount holes on the Ø76 flat top with the gland keep-out off the cap:
    the far-end lugs are 94.6 mm from the gland and 57.7 mm apart, and a lug and a floor boss are at least 77 mm apart
    (more than the flat top's usable Ø70). Moving the floor bosses inboard cannot fix that either (lug-to-boss distance),
    and bolting only the floor bosses would need them moved about 15.5 mm inboard (to y ~ -5 in the box frame), a
    redesign of the box's gland end rather than a nudge. So the cap bolts the UV box by its
    two FAR-END LUG inserts only, both on the flat top, and the box's flat back rests on the flat top between them and
    the rim; the floor bosses stay as built, unused here. podbox.py is unchanged.
    The box is turned so its gland end points +x (away from the pole, which is behind the arm's upright at -y): the
    gland and its cable hang outside the cap and the louvers on the BARO side, and the cable runs down to the arm there.
    Lug line at x = UV_LUG_X, centred on y = 0.
    Bosses: one under the roof per screw, a Ø BOSS_D column from the roof down to the seat, GRIP below the flat top (so
    the M3 x 10 grips 5.0 and leaves 5.0 of thread in the insert). The lugs are past the inner cone (r 31), so a
    counterbore (CBORE_D, clear of the head) runs from the seat straight down through the cone and out of the cap's
    open bottom: the screws go in with the cap off the stack. The flat top is the print bed, so nothing is added on top.
  TH and BARO boxes on the arm
    One face per box, on opposite sides of the cup: TH on -x (the side of the cup's lead hole), BARO on +x. Each face is
    a vertical plate FACE_T thick (the base plate's own thickness) parallel to the YZ plane, FACE_GAP outside the cup's
    largest radius, joined to the base plate by a tab of the base plate's thickness. The box hangs on the face's
    outer side, back to the face, lid outward, board vertical, glands down (podbox up() = +y = world up); its top is
    BOX_BELOW_PLATES under the lowest louver plate, so it sits beside the cup, below the plates, and reaches below the arm.
    Four M3 x 10 per box through the face into its lug inserts, from the face's inner (cup) side: fit the boxes before
    the cup goes on the arm.
    Each face and tab runs from the upright's back plane (Y -89) to past the boxes so that the REMIXED ARM PRINTS ON
    THE UPRIGHT'S BACK FACE (Y up in print): the faces hang below the base plate, so the 3MF's base-plate-down pose no
    longer works; on its back face every face and tab is a wall standing on the bed.
    The TH box's lead gland is in its bottom wall; with the box on the -x face its +x box axis runs along world -y, so
    the lead gland sits 10 mm to -y of the box's middle.
  TH lead
    From the SHT45's header pads down the stand, through the cup's own Ø5 hole, out under the cup's disc, down through
    a new Ø LEAD_HOLE_D hole in the TH tab (the arm lead hole, beside the face's inner side), down the face's inner side,
    under the face's bottom edge and into the TH box's lead gland from below (a drip loop).
"""
import math
import sys
from functools import lru_cache
from pathlib import Path

import cadquery as cq
import manifold3d as mf
import numpy as np

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent / "box", _HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import sources as S            # noqa: E402  hardware/pods-r1/sources.py
import assemble as A           # noqa: E402  hardware/pods-r1/shield/assemble.py
import podbox as P             # noqa: E402  hardware/pods-r1/box/podbox.py

HOLE_D = S.val("pod_mount_screw")[0] + 0.4       # M3 clearance through the cap and the faces
HEAD_D = S.val("pod_mount_screw")[2]
THREAD = 5.0                                     # screw thread left in the insert (insert 5.7 long, bore 6.7 deep)
GRIP = S.val("pod_mount_screw")[1] - THREAD      # printed plastic under every mount screw's head: 5.0
BOSS_D = 10.0                                    # cap boss column
CBORE_D = HEAD_D + 1.0                           # head and driver clearance below a cap seat
UV_TURN = 90                                     # degrees about Z: the UV box's gland end (-y in its frame) to +x
UV_LUG_X = -12.0                                 # the UV box's far-end lug line on the cap (shield frame x)
FACE_T = 5.0                                     # arm faces and tabs: the base plate's thickness (checked below)
FACE_GAP = 2.0                                   # a face's inner side outside the cup's largest radius
FACE_MARGIN = 6.0                                # face material past every lug hole centre
TAB_IN = 15.0                                    # the tabs reach in to |x| = TAB_IN under the base plate
BOX_BELOW_PLATES = 6.0                           # TH/BARO box top under the lowest louver plate
LEAD_HOLE_D = 6.0                                # the arm lead hole (the lead is OD 3.0-4.3)
LEAD_DROP = 3.5                                  # the lead drops this far below where the cup hole opens, clear of the column
GLAND_DROP = S.val("gland_pg7")[2] + S.val("gland_pg7")[3]      # PG-7 body + cap below the box floor: 28.0
CLAMP_WORM = 12.0                                # hose-clamp worm housing and band, in front of the gusset
CAP_PRINT_UP = (0.0, 0.0, -1.0)                  # the cap prints on its flat top (as in the 3MF)
ARM_PRINT_UP = (0.0, 1.0, 0.0)                   # the remixed arm prints on the upright's back face (Y = -89)
SEG = 96                                         # circle segments for the probes and tubes


# ------------------------------------------------------------------ mesh plumbing
def as_manifold(v, f):
    m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(v, np.float32), tri_verts=np.asarray(f, np.uint32)))
    assert m.status() == mf.Error.NoError, m.status()
    return m


def arrays(m):
    mesh = m.to_mesh()
    return np.asarray(mesh.vert_properties, float)[:, :3], np.asarray(mesh.tri_verts, np.int64)


def from_cq(shape, tol=0.01):
    """A CadQuery solid as a manifold (vertices welded at 1e-5 mm)."""
    shape = shape.val() if isinstance(shape, cq.Workplane) else shape
    vs, ts = shape.tessellate(tol, 0.1)
    v = np.array([(p.x, p.y, p.z) for p in vs])
    t = np.array(ts, np.int64)
    key = np.round(v / 1e-5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    t = inv.reshape(-1)[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 2] != t[:, 0])]
    return as_manifold(v[first], t)


@lru_cache(maxsize=None)
def original(oid):
    return as_manifold(*A.assembled()[oid])


def cyl(xy, d, z0, z1):
    """A vertical probe cylinder (manifold primitive)."""
    return mf.Manifold.cylinder(z1 - z0, d / 2, -1.0, SEG).translate((xy[0], xy[1], z0))


def _align(p0, p1):
    """3x4 transform taking the +Z unit segment from the origin onto p0 -> p1 (rotation only, then translation)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    z = d / np.linalg.norm(d)
    a = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(a, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.c_[x, y, z, p0]


def cyl_axis(p0, p1, d):
    length = float(np.linalg.norm(np.asarray(p1, float) - np.asarray(p0, float)))
    return mf.Manifold.cylinder(length, d / 2, -1.0, SEG).transform(_align(p0, p1))


def tube(points, d):
    """A round tube of diameter d along a polyline (hulls of spheres)."""
    s = [mf.Manifold.sphere(d / 2, 32).translate(tuple(map(float, p))) for p in points]
    return mf.Manifold.batch_boolean([mf.Manifold.batch_hull([a, b]) for a, b in zip(s, s[1:])], mf.OpType.Add)


def top_z(m, x, y):
    v, f = arrays(m)
    z = A.top_z(v, f, x, y)
    return -1e9 if z is None else z


def overhang_area(m, up):
    """Area (mm^2) facing within 45 degrees of straight down when printed with `up` as the print's up, not counting
    faces on the bed: what would print in the air."""
    v, f = arrays(m)
    up = np.asarray(up, float)
    p = v[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    a = np.linalg.norm(n, axis=1)
    h = p @ up
    down = (n @ up) < -math.cos(math.radians(45)) * a
    off_bed = h.min(1) > h.min() + 0.2
    return float(a[down & off_bed].sum() / 2)


# ------------------------------------------------------------------ what the meshes say
@lru_cache(maxsize=None)
def cap_flat_top():
    """(Z, radius) of the cap's flat top: its up-facing facets at the top, radius from the plate axis."""
    v, f = A.assembled()[A.CAP]
    p = v[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    z = float(v[:, 2].max())
    flat = (n[:, 2] > 0.999) & (np.abs(p[:, :, 2] - z).max(1) < 1e-3)
    return z, float(np.hypot(p[flat][:, :, 0], p[flat][:, :, 1]).max())


@lru_cache(maxsize=None)
def arm_plate():
    """The arm's base plate: (bottom Z, top Z) and its thickness, measured round the pocket."""
    ft = A.features(A.ARM)
    dz = A.placements()[A.ARM][2]
    lo, hi = ft["zmin"] + dz, ft["rim_top"] + dz
    return lo, hi, hi - lo


@lru_cache(maxsize=None)
def cup_radius():
    v = A.assembled()[A.CUP][0]
    return float(np.hypot(v[:, 0], v[:, 1]).max())


@lru_cache(maxsize=None)
def plates_bottom():
    return min(float(A.assembled()[f"{A.PLATE}.{k}"][0][:, 2].min()) for k in range(1, A.PITCH_PLATES + 1))


@lru_cache(maxsize=None)
def cup_hole():
    """(x, y, r) of the cup's Ø5 cable hole in the shield frame, and the Z where it opens under the disc."""
    hx, hy, hr = A.features(A.CUP)["cable_hole"]
    dx, dy, _ = A.placements()[A.CUP]
    x, y = hx + dx, hy + dy
    v, f = A.assembled()[A.CUP]
    top = float(v[:, 2].max())
    probe = np.array([[x - hr - 0.4, y]])                 # just outside the bore, on the side away from the axis
    z = top
    while z > 0 and A._inside(probe, A.section_z(v, f, z))[0]:
        z -= 0.25
    return x, y, hr, z


# ------------------------------------------------------------------ box placements
@lru_cache(maxsize=None)
def box_local(name):
    """The pod box (body and lid, closed) as a manifold in its own box frame."""
    return from_cq(P.body(name)) + from_cq(P.lid(name))


@lru_cache(maxsize=None)
def box_pose(name):
    """(R, t): world = R @ box + t."""
    lo = box_local(name).bounding_box()
    d = P.dims(name)
    holes = P.mount_face(name).holes
    if name == "UV":
        c, s = round(math.cos(math.radians(UV_TURN))), round(math.sin(math.radians(UV_TURN)))
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        far = sorted(holes, key=lambda h: h[1])[-2:]                       # the two far-end lugs
        mid = np.mean(far, 0)
        z_top, _ = cap_flat_top()
        t = np.array([UV_LUG_X, 0.0, z_top]) - R @ np.array([mid[0], mid[1], d["z_bo"]])
        return R, t
    side = -1.0 if name == "TH" else 1.0
    # box +z (the lid's side) points away from the arm: TH -x, BARO +x; box +y is world up; box +x follows (right hand)
    ez = np.array([side, 0.0, 0.0])
    ey = np.array([0, 0, 1.0])
    ex = np.cross(ey, ez)
    R = np.c_[ex, ey, ez]
    outer = cup_radius() + FACE_GAP + FACE_T
    mid_x = float(np.mean([h[0] for h in holes]))
    box_top = plates_bottom() - BOX_BELOW_PLATES
    t = np.array([side * outer, 0.0, box_top]) - R @ np.array([mid_x, lo[4], d["z_bo"]])
    return R, t


def box_points(name, pts):
    R, t = box_pose(name)
    return [R @ np.asarray(p, float) + t for p in pts]


@lru_cache(maxsize=None)
def box_placed(name):
    R, t = box_pose(name)
    return box_local(name).transform(np.c_[R, t])


# ------------------------------------------------------------------ the cap
@lru_cache(maxsize=None)
def uv_mount():
    z_top, r_flat = cap_flat_top()
    far = sorted(P.mount_face("UV").holes, key=lambda h: h[1])[-2:]
    d = P.dims("UV")
    holes = [tuple(map(float, p[:2])) for p in box_points("UV", [(x, y, d["z_bo"]) for x, y in far])]
    keep = [(*map(float, box_points("UV", [(x, y, d["z_bo"])])[0][:2]), kd) for x, y, kd in P.mount_face("UV").keepouts]
    return dict(holes=holes, keepouts=keep, top_z=z_top, flat_r=r_flat, seat_z=z_top - GRIP)


@lru_cache(maxsize=None)
def cap_remixed():
    m = uv_mount()
    cap = original(A.CAP)
    lo = cap.bounding_box()[2]
    add, cut = [], []
    for x, y in m["holes"]:
        add.append(cq.Workplane("XY").workplane(offset=m["seat_z"]).center(x, y).circle(BOSS_D / 2)
                   .extrude(m["top_z"] - 0.5 - m["seat_z"]))
        cut.append(cq.Workplane("XY").workplane(offset=m["seat_z"] - 0.5).center(x, y).circle(HOLE_D / 2)
                   .extrude(GRIP + 2.0))
        cut.append(cq.Workplane("XY").workplane(offset=lo - 2.0).center(x, y).circle(CBORE_D / 2)
                   .extrude(m["seat_z"] - lo + 2.0))
    for w in add:
        cap = cap + from_cq(w)
    for w in cut:
        cap = cap - from_cq(w)
    return cap


def uv_cable_envelope():
    """The UV box's floor gland (its keep-out circle, GLAND_DROP below the floor) and the cable straight down from it
    (the largest cable OD plus 2 mm all round) to below the arm."""
    m = uv_mount()
    x, y, kd = m["keepouts"][0]
    gland = cyl((x, y), kd, m["top_z"] - GLAND_DROP, m["top_z"])
    low = arm_plate()[0] - 120.0
    cable = cyl((x, y), S.val("pg7_seal")[1] + 4.0, low, m["top_z"] - GLAND_DROP + 0.5)
    return gland + cable


# ------------------------------------------------------------------ the arm
@lru_cache(maxsize=None)
def arm_mount(name):
    """The face for one box: holes (world points on the box's back plane), normal (box back -> arm), thickness, and the
    face's extent (x0, x1, y0, y1, z0, z1)."""
    d = P.dims(name)
    holes = [tuple(map(float, p)) for p in box_points(name, [(x, y, d["z_bo"]) for x, y in P.mount_face(name).holes])]
    side = -1.0 if name == "TH" else 1.0
    inner = cup_radius() + FACE_GAP
    hy = [h[1] for h in holes]
    hz = [h[2] for h in holes]
    y0 = float(original(A.ARM).bounding_box()[1])                        # the upright's back plane: the print bed
    y1 = max(hy) + FACE_MARGIN
    z0 = min(hz) - FACE_MARGIN
    z1 = min(max(hz) + FACE_MARGIN, plates_bottom() - 5.0)
    x0, x1 = sorted((side * inner, side * (inner + FACE_T)))
    return dict(holes=holes, normal=(-side, 0.0, 0.0), thickness=FACE_T, face=(x0, x1, y0, y1, z0, z1))


def _block(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


@lru_cache(maxsize=None)
def lead_hole():
    """(x, y) of the arm lead hole: in the TH tab, beside the TH face's inner side, on the cup hole's y."""
    x0, x1, *_ = arm_mount("TH")["face"]
    _hx, hy, _hr, _z = cup_hole()
    return x1 + LEAD_HOLE_D / 2 + 1.0, hy


@lru_cache(maxsize=None)
def arm_remixed():
    lo, hi, t = arm_plate()
    assert abs(t - FACE_T) < 0.05, f"the arm's base plate is {t:.2f} thick, FACE_T is {FACE_T}"
    arm = original(A.ARM)
    for name in ("TH", "BARO"):
        m = arm_mount(name)
        x0, x1, y0, y1, z0, z1 = m["face"]
        tx0, tx1 = (x0, -TAB_IN) if x0 < 0 else (TAB_IN, x1)
        arm = arm + from_cq(_block(x0, x1, y0, y1, z0, z1)) + from_cq(_block(tx0, tx1, y0, y1, lo, hi))
        nrm = np.array(m["normal"])
        for h in m["holes"]:
            a, b = np.array(h) - nrm * 1.0, np.array(h) + nrm * (FACE_T + 1.0)
            arm = arm - from_cq(cq.Workplane("XY").add(cq.Solid.makeCylinder(HOLE_D / 2, FACE_T + 2.0, cq.Vector(*a),
                                                                              cq.Vector(*(b - a)))))
    lx, ly = lead_hole()
    arm = arm - from_cq(cq.Workplane("XY").workplane(offset=lo - 1.0).center(lx, ly).circle(LEAD_HOLE_D / 2)
                        .extrude(t + 2.0))
    return arm


@lru_cache(maxsize=None)
def clamp_slots():
    """The hose-clamp slots through the arm's upright, measured: [(x0, x1, z0, z1)], and the upright's faces (y)."""
    v, f = A.assembled()[A.ARM]
    vy = v[(v[:, 1] < v[:, 1].min() + 5.5)]
    y_back = float(v[:, 1].min())
    y_front = y_back + 5.0
    ym = y_back + 2.5
    xs = np.arange(-25.0, 25.01, 0.25)
    open_ = []
    for z in np.arange(0.0, float(vy[:, 2].max()) - 0.5, 0.25):
        seg = A.section_z(v, f, z)
        ins = A._inside(np.c_[xs, np.full_like(xs, ym)], seg)
        mat = xs[ins]
        if not len(mat):
            continue
        lo, hi = mat.min(), mat.max()
        gaps = xs[(~ins) & (xs > lo) & (xs < hi)]
        for g in gaps:
            open_.append((float(g), float(z)))
    slots = []
    for sgn in (-1, 1):
        pts = np.array([p for p in open_ if p[0] * sgn > 0])
        if not len(pts):
            continue
        zs = np.unique(pts[:, 1])
        runs, cur = [], [zs[0]]
        for z in zs[1:]:
            if z - cur[-1] > 0.3:
                runs.append(cur)
                cur = [z]
            else:
                cur.append(z)
        runs.append(cur)
        for r in runs:
            sel = pts[(pts[:, 1] >= r[0]) & (pts[:, 1] <= r[-1])]
            slots.append((float(sel[:, 0].min()), float(sel[:, 0].max()), float(r[0]), float(r[-1])))
    return slots, y_back, y_front


@lru_cache(maxsize=None)
def clamp_envelope():
    """Where the pole clamp is (it is not in the 3MF): the pole and the band behind the upright (everything past its
    back plane), and the band through each slot pair round the arm's front (gusset) with its worm housing (CLAMP_WORM)."""
    slots, y_back, y_front = clamp_slots()
    v, f = A.assembled()[A.ARM]
    big = 200.0
    env = from_cq(_block(-big, big, y_back - big, y_back, -big, big))
    for z0, z1 in sorted({(s[2], s[3]) for s in slots}):
        xo = max(max(abs(s[0]), abs(s[1])) for s in slots if (s[2], s[3]) == (z0, z1))
        near = v[(np.abs(v[:, 0]) <= xo) & (v[:, 2] >= z0 - 1) & (v[:, 2] <= z1 + 1) & (v[:, 1] < 0)]
        front = float(near[:, 1].max()) if len(near) else y_front
        env = env + from_cq(_block(-xo - 2.0, xo + 2.0, y_back, front + CLAMP_WORM, z0 - 2.0, z1 + 2.0))
    return env


# ------------------------------------------------------------------ the TH lead
@lru_cache(maxsize=None)
def th_lead_path():
    """The lead's centreline from the cup's top face (in its Ø5 hole) to the bottom of its drip loop under the TH box's
    lead gland: [(x, y, z)]."""
    hx, hy, _hr, z_open = cup_hole()
    top = float(original(A.CUP).bounding_box()[5])
    lo, hi, _t = arm_plate()
    lx, ly = lead_hole()
    face = arm_mount("TH")["face"]
    gland = [o for o in P.openings("TH") if o[0] == "lead_gland"][0]
    g = box_points("TH", [gland[1]])[0]
    return [(hx, hy, top), (hx, hy, z_open - LEAD_DROP), (lx, ly, hi + 3.0), (lx, ly, lo - 3.0), (lx, ly, face[4] - 8.0),
            (float(g[0]), float(g[1]), float(g[2]) - GLAND_DROP - 15.0)]


def lead_length():
    """mm, SHT45 header pads to the TH board: down the stand to the cup, the path, up into the gland and to the board."""
    (x0, x1), (y0, y1), (z0, z1) = A.sht45_box()
    pads = np.array([(x0 + x1) / 2, (y0 + y1) / 2, z0])
    path = np.array(th_lead_path())
    run = float(np.linalg.norm(path[0] - pads) + np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
    d = P.dims("TH")
    inside = (d["y1"] - d["y0"]) + (d["x1"] - d["x0"])                  # gland to the board, worst case round the box
    return run + GLAND_DROP + 15.0 + inside


# ------------------------------------------------------------------ checks and output
def _part_lines(tag, new, old, up, old_up):
    v, f = arrays(new)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    fwd = {tuple(x) for x in e.tolist()}
    closed = len(fwd) == len(e) and all((b, a) in fwd for a, b in fwd)
    comps = len(new.decompose())
    lost = (old - new).volume()
    oh, oh0 = overhang_area(new, up), overhang_area(old, old_up)
    ok = new.status() == mf.Error.NoError and closed and comps == 1
    return ok, [f"{tag}: manifold {new.status().name}, every edge shared by two triangles: {closed}, components {comps}, "
                f"genus {new.genus()}, volume {old.volume() / 1000:.2f} -> {new.volume() / 1000:.2f} cm3 "
                f"(holes take {lost:.1f} mm3 of the original)",
                f"{tag}: steep overhang printed up={up}: {oh:.0f} mm2 (the original in its 3MF pose: {oh0:.0f} mm2)"]


def remix_checks():
    """Every check, as report lines; the last line says whether all pass."""
    out, bad = [], False
    asm = {k: original(k) for k in A.assembled()}
    cap, arm = cap_remixed(), arm_remixed()
    ok, lines = _part_lines("cap", cap, asm[A.CAP], CAP_PRINT_UP, CAP_PRINT_UP)
    out += lines
    bad |= not ok
    m = uv_mount()
    out.append(f"cap flat top: Z {m['top_z']:.2f}, a disc of radius {m['flat_r']:.2f}; UV box turned {UV_TURN} deg "
               f"(gland end to +x), far-end lugs bolted, back flat on the top")
    for x, y in m["holes"]:
        edge = m["flat_r"] - math.hypot(x, y)
        out.append(f"  UV hole ({x:.2f}, {y:.2f}): {edge:.2f} mm inside the flat top's edge (needs 3.0; head {HEAD_D / 2:.2f})")
        bad |= edge < 3.0
    out.append(f"  cap bosses: Ø{BOSS_D:g} under the roof, seat Z {m['seat_z']:.2f} (grip {GRIP:.1f}), "
               f"counterbore Ø{CBORE_D:g} down and out of the cap's bottom")
    cb = cap.bounding_box()
    for x, y, kd in m["keepouts"]:
        dx, dy = max(cb[0] - x, 0, x - cb[3]), max(cb[1] - y, 0, y - cb[4])
        out.append(f"  gland keep-out ({x:.2f}, {y:.2f}) Ø{kd:g}: its edge {math.hypot(dx, dy) - kd / 2:.2f} mm off the cap")
        bad |= math.hypot(dx, dy) < kd / 2
    env = uv_cable_envelope()
    gaps = {k: env.min_gap(cap if k == A.CAP else asm[k], 50.0) for k in [A.CAP] + [f"{A.PLATE}.{i}" for i in range(1, 7)]}
    k = min(gaps, key=gaps.get)
    out.append(f"  gland ({GLAND_DROP:g} below the floor) and cable drop: nearest {k} at {gaps[k]:.2f} mm")
    bad |= gaps[k] <= 1.0
    uv = box_placed("UV")
    out.append(f"  UV box on the cap: overlap {(uv ^ cap).volume():.3f} mm3")
    ok, lines = _part_lines("arm", arm, asm[A.ARM], ARM_PRINT_UP, (0.0, 0.0, 1.0))
    out += lines
    bad |= not ok
    lo, hi, t = arm_plate()
    out.append(f"arm base plate Z {lo:.2f}..{hi:.2f} ({t:.2f} thick); cup radius {cup_radius():.2f}; lowest louver plate Z "
               f"{plates_bottom():.2f}")
    clamp = clamp_envelope()
    slots, yb, yf = clamp_slots()
    out.append("  pole clamp slots (x0, x1, z0, z1): " + "; ".join(f"({a:.1f}, {b:.1f}, {c:.1f}, {d:.1f})" for a, b, c, d in slots))
    boxes = {}
    for n in ("TH", "BARO"):
        mm = arm_mount(n)
        b = box_placed(n)
        boxes[n] = b
        bb = b.bounding_box()
        x0, x1, y0, y1, z0, z1 = mm["face"]
        g_cup, g_clamp, g_pl = b.min_gap(asm[A.CUP], 50.0), b.min_gap(clamp, 50.0), b.min_gap(asm[f"{A.PLATE}.1"], 50.0)
        out.append(f"  {n} face x {x0:.1f}..{x1:.1f}, y {y0:.1f}..{y1:.1f}, z {z0:.1f}..{z1:.1f}; box x {bb[0]:.1f}..{bb[3]:.1f} "
                   f"y {bb[1]:.1f}..{bb[4]:.1f} z {bb[2]:.1f}..{bb[5]:.1f}")
        out.append(f"  {n} clearances: cup {g_cup:.2f}, pole clamp {g_clamp:.2f}, plate 1 {g_pl:.2f} (each needs 5.0); "
                   f"overlap with the arm {(b ^ arm).volume():.3f} mm3")
        out.append(f"  {n} screws (M3 x {S.val('pod_mount_screw')[1]:g} from the face's inner side): "
                   + ", ".join(f"({h[0]:.1f}, {h[1]:.1f}, {h[2]:.1f})" for h in mm["holes"]))
        bad |= min(g_cup, g_clamp, g_pl) < 5.0
    out.append(f"  TH to BARO box gap {boxes['TH'].min_gap(boxes['BARO'], 200.0):.1f}")
    hx, hy, hr, zo = cup_hole()
    lx, ly = lead_hole()
    tb = tube(th_lead_path(), S.val("pg7_seal")[1])
    hits = {"cup": (tb ^ asm[A.CUP]).volume(), "arm": (tb ^ arm).volume(), "TH box": (tb ^ boxes["TH"]).volume()}
    out.append(f"TH lead (OD up to {S.val('pg7_seal')[1]:g}): the cup's own Ø{2 * hr:.1f} hole at ({hx:.2f}, {hy:.2f}), "
               f"open under the disc at Z {zo:.1f}; the new arm lead hole Ø{LEAD_HOLE_D:g} at ({lx:.2f}, {ly:.2f}); "
               f"tube overlaps " + ", ".join(f"{k} {v:.4f}" for k, v in hits.items()) + f" mm3; length about "
               f"{lead_length():.0f} mm (th_lead_m {S.val('th_lead_m') * 1000:.0f})")
    bad |= max(hits.values()) > 1e-3 or lead_length() > S.val("th_lead_m") * 1000
    out.append("remix: every check passes" if not bad else "remix: FAILED (see above)")
    return out


def _write_stl(m, path, up):
    """Binary STL, turned to its print pose (`up` = the print's +Z) and set on Z = 0."""
    v, f = arrays(m)
    poses = {(0, 0, 1): np.eye(3), (0, 0, -1): np.diag([1.0, -1.0, -1.0]),     # turned 180 deg about X
             (0, 1, 0): np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])}   # turned +90 deg about X: +y to +z
    R = poses[tuple(int(round(c)) for c in up)]
    w = v @ R.T
    w[:, 2] -= w[:, 2].min()
    p = w[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, p
    with open(path, "wb") as fh:
        fh.write(b"pods-r1 shield remix (derived from a local mesh; not for git)".ljust(80, b" "))
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(rec.tobytes())
    return path


def write_stls():
    out = S.shield_out_path()
    return [_write_stl(cap_remixed(), out / "cap_remixed.stl", CAP_PRINT_UP),
            _write_stl(arm_remixed(), out / "arm_remixed.stl", ARM_PRINT_UP)]


def main():
    path = S.shield_path()
    if not path.exists():
        print(f"shield 3MF not present at {path}: skipped")
        return 0
    lines = remix_checks()
    print("\n".join(lines))
    for p in write_stls():
        print(f"wrote {p.name} to sources.shield_out ({S.val('shield_out')})")
    return 0 if lines[-1].endswith("every check passes") else 1


if __name__ == "__main__":
    sys.exit(main())
