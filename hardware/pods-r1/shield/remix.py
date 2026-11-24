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
        gusset, and three pairs of small slots through the upright (clamp_slots()). No band of any useful width goes
        through those slots, and the upright's flat back face has nothing to seat on a round pole, so the remix fills
        them and adds the pole saddle below. The arm is printed on its base plate in the 3MF.
  cup   radius 30.0 at most; its Ø5 through-hole at (-12, 4) runs down through the disc and opens under it at Z ~22.6,
        beside the cup's column: the TH lead's way out (no new hole in the cup).

CHOICES (Task 7; the brief left these to the builder)
  UV crown on the cap
    The UV pod is a round crown (podbox.py, _crown_body/_crown_lid) with its axis on the plate axis and its floor flat
    on the cap's flat top, turned so its port gland points +x (away from the pole, which is behind the arm's upright
    at -y). The gland comes straight out of the drum wall; the cable runs level out to a drip loop and then down
    outside the louvers to the arm on the BARO side.
    Mount: the crown's four floor bosses (r 31 about its axis) are all on the original flat top. One boss under the
    roof per screw, a Ø BOSS_D column from the roof down to the seat, GRIP below the flat top (so the M3 x 10 grips 5.0
    and leaves 5.0 of thread in the insert). A counterbore (CBORE_D, clear of the head) runs from the seat straight
    down through the inner cone and out of the cap's open bottom: these screws go in with the cap off the stack.
    Skirt: the crown is Ø 2 r_out, wider than the cap, so the cap grows a skirt under it: a shell of revolution SKIRT_T
    thick that starts SKIRT_FOOT outside and above the top louver plate and flares out in one S-curve (vertical at
    both ends, a smoothstep in r against Z) to the crown's drum at the flat top's level, plus a ring there from
    SKIRT_RING_IN out that fuses to the roof. The louvers' outline runs up into the crown without a step, the cap's
    cone is hidden, and nothing hangs in front of the louvers. The cap still prints on its flat top: the ring is on
    the bed with it, and the skirt leans in from there.
  TH and BARO boxes on the arm
    One face per box, on opposite sides of the cup: TH on -x (the side of the cup's lead hole), BARO on +x. Each face is
    a vertical plate FACE_T thick (the base plate's own thickness) parallel to the YZ plane, FACE_GAP outside the cup's
    largest radius, joined to the base plate by a tab of the base plate's thickness. The box hangs on the face's
    outer side, back to the face, lid outward, board vertical, glands down (podbox up() = +y = world up); its top is
    BOX_BELOW_PLATES under the lowest louver plate, so it sits beside the cup, below the plates, and reaches below the arm.
    Four M3 x 10 per box through the face into its lug inserts, from the face's inner (cup) side: fit the boxes before
    the cup goes on the arm.
    Each face runs from the saddle's back plane, and each tab from the upright's back plane, to past the boxes, so that
    the REMIXED ARM PRINTS ON ITS BACK (Y up in print): the faces hang below the base plate, so the 3MF's
    base-plate-down pose no longer works; on its back every face is a wall standing on the bed.
    The TH box's lead gland is in its bottom wall; with the box on the -x face its +x box axis runs along world -y, so
    the lead gland sits 10 mm to -y of the box's middle.
  Pole saddle and strap tunnels (Clint, 2026-11-24: the arm is strapped to the pole like everything else)
    A saddle block on the upright's back face, as wide as the upright (SADDLE_HALF_W) and as tall, with a vertical V
    groove in its back (SADDLE_HALF_ANGLE, 80 degrees included, SADDLE_LIP wide at the back face). Any pole from
    POLE_RANGE seats on the V's two flanks along two vertical lines, so the arm can't rock or spin once strapped;
    pole_axis(d) is where a pole of diameter d sits. Two strap tunnels run straight across the block along X, one near
    the bottom and one near the top of the upright (STRAP_SLOT_Z, STRAP_SLOT_PITCH apart: the wire straps on the pole
    line up with them). Each is STRAP_SLOT clear (Z x Y), between the upright's back face and a STRAP_WALL wall in
    front of the V's apex, so a strap goes through the block, out of both sides, round the block's back corners and
    round the pole: pole and bracket in one loop. The tunnel's rear edges at both exits are rounded (STRAP_EXIT_R) and
    the block's back corners are notched round (SADDLE_CORNER_R) over each tunnel's height, so the strap never bends
    over a sharp edge. A strap is a pole_strap_tie (heavy UV-black nylon 66 zip tie) or a pole_strap_band (SAE 20
    stainless hose clamp, 1/2 in band); two per arm. The original slots are filled. strap_envelope() is where the
    straps, their heads or worm housings and the pole are, for the boxes' clearance check.
    The faces run back to the saddle's back plane, so the arm still prints on its back (now the saddle's back face): the
    saddle's flats and the faces' ends are on the bed, the V's flanks are 50 degrees from straight down, and the
    tunnels' and tabs' undersides are short flat bridges.
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
THREAD_WANT = 5.0                                # screw thread wanted in each pod box insert
INSERT_LEN = S.val("insert_m3")[0]               # the M3 heat-set insert's length (tx-stack-r1 sources, TBD: 5.7)
THREAD = min(THREAD_WANT, INSERT_LEN)            # thread in the insert: never longer than the insert (5.0 today)
assert THREAD <= INSERT_LEN <= S.val("pod_insert_bore")[1], "the mount screw's thread must end inside its insert's bore"
GRIP = S.val("pod_mount_screw")[1] - THREAD      # printed plastic under every mount screw's head: 5.0
BOSS_D = 10.0                                    # cap boss column
CBORE_D = HEAD_D + 1.0                           # head and driver clearance below a cap seat
UV_TURN = 90                                     # degrees about Z: the UV crown's port gland (-y in its frame) to +x
FACE_T = 5.0                                     # arm faces and tabs: the base plate's thickness (checked below)
FACE_GAP = 2.0                                   # a face's inner side outside the cup's largest radius
FACE_MARGIN = 6.0                                # face material past every lug hole centre
SKIRT_T = 2.4                                    # the cap's skirt under the UV crown: shell and top ring thickness
SKIRT_FOOT = (0.6, 0.6)                          # its foot: this far outside the louver plates' radius and above their top
SKIRT_RING_IN = 36.0                             # the top ring reaches in to this radius (it fuses to the flat top's shell)
TAB_IN = 15.0                                    # the tabs reach in to |x| = TAB_IN under the base plate
BOX_BELOW_PLATES = 6.0                           # TH/BARO box top under the lowest louver plate
LEAD_HOLE_D = 6.0                                # the arm lead hole (the lead is OD 3.0-4.3)
LEAD_DROP = 3.5                                  # the lead drops this far below where the cup hole opens, clear of the column
GLAND_DROP = S.val("gland_pg7")[2] + S.val("gland_pg7")[3]      # PG-7 body + cap below the box floor: 28.0
POLE_D = 25.4                                    # the pole: about 1 in (Clint, 2026-11-24)
POLE_RANGE = (22.0, 34.0)                        # the saddle seats any pole from this range on its two flanks
SADDLE_HALF_ANGLE = 40.0                         # degrees: the V's flank from its axis (80 included; 50 from down in print)
SADDLE_HALF_W = 19.5                             # the saddle block's half-width: the upright's back face, sides flush
SADDLE_LIP = 14.0                                # the V's half-width at the saddle's back face
SADDLE_CORNER_R = 3.0                            # the saddle's back corners, rounded where each strap turns to the pole
STRAP_SLOT = (14.5, 3.8)                         # each strap tunnel's clear opening: along Z (strap width) x along Y
STRAP_WALL = 2.0                                 # the wall between each tunnel and the V's apex
STRAP_EXIT_R = 2.0                               # each tunnel's rear edge, rounded at both exits
STRAP_SLOT_Z = (5.0, 51.0)                       # EXPORTED: the two tunnels' centres, shield frame Z (the wire straps align)
STRAP_SLOT_PITCH = STRAP_SLOT_Z[1] - STRAP_SLOT_Z[0]     # EXPORTED: 46.0 between the two tunnels' centres
STRAP_T = 2.0                                    # a strap's thickness in the envelope (the tie 1.9, the band 0.8)
STRAP_HEAD = (20.0, 14.0)                        # a zip tie's head or a clamp's worm housing behind the pole: wide x proud
WALL_MIN = 1.2                                   # the project's thinnest wall
SADDLE_V_DEPTH = SADDLE_LIP / math.tan(math.radians(SADDLE_HALF_ANGLE))
SADDLE_DEPTH = STRAP_SLOT[1] + STRAP_WALL + SADDLE_V_DEPTH      # the saddle block behind the upright's back face
_TIE, _BAND = S.val("pole_strap_tie"), S.val("pole_strap_band")
assert STRAP_SLOT[0] >= max(_TIE[1], _BAND[1]) + 1.0 and STRAP_SLOT[1] >= max(_TIE[2], _BAND[2]) + 1.5, "a strap tunnel is too small"
assert STRAP_WALL >= WALL_MIN
assert POLE_RANGE[1] / 2 * math.cos(math.radians(SADDLE_HALF_ANGLE)) < SADDLE_LIP - 0.5, "the largest pole's contact is off the V"
CAP_PRINT_UP = (0.0, 0.0, -1.0)                  # the cap prints on its flat top (as in the 3MF)
ARM_PRINT_UP = (0.0, 1.0, 0.0)                   # the remixed arm prints on its back: the saddle's back face down
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
    if name == "UV":                                  # the crown: its axis on the plate axis, floor on the flat top
        c, s = round(math.cos(math.radians(UV_TURN))), round(math.sin(math.radians(UV_TURN)))
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        ax, ay = d["axis"]
        z_top, _ = cap_flat_top()
        t = np.array([0.0, 0.0, z_top]) - R @ np.array([ax, ay, d["z_bo"]])
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
    """The UV crown's four mount holes (its floor-boss inserts) in the shield frame, all on the cap's flat top; the
    crown's outer radius; and the screws' seat (GRIP under the top)."""
    z_top, r_flat = cap_flat_top()
    d = P.dims("UV")
    holes = [tuple(map(float, p[:2])) for p in box_points("UV", [(x, y, d["z_bo"]) for x, y in d["floor_bosses"]])]
    return dict(holes=holes, lugs=holes, bosses=[], keepouts=[], top_z=z_top, flat_r=r_flat, seat_z=z_top - GRIP,
                r_out=float(d["r_out"]))


def _ray_hits(v, f, x, y):
    """Every surface Z on the vertical line through (x, y), sorted."""
    p = v[f]
    x0, y0 = p[:, 0, 0], p[:, 0, 1]
    d = (p[:, 1, 0] - x0) * (p[:, 2, 1] - y0) - (p[:, 2, 0] - x0) * (p[:, 1, 1] - y0)
    ok = np.abs(d) > 1e-12
    dd = np.where(ok, d, 1)
    l1 = ((x - x0) * (p[:, 2, 1] - y0) - (p[:, 2, 0] - x0) * (y - y0)) / dd
    l2 = ((p[:, 1, 0] - x0) * (y - y0) - (x - x0) * (p[:, 1, 1] - y0)) / dd
    l0 = 1 - l1 - l2
    ins = ok & (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
    return np.sort((l0 * p[:, 0, 2] + l1 * p[:, 1, 2] + l2 * p[:, 2, 2])[ins])


@lru_cache(maxsize=None)
def skirt():
    """The skirt under the UV crown (a manifold, before it is fused to the cap): a shell of revolution that starts just
    outside the louver plates' radius, just above their top, and flares out in one S-curve (vertical at both ends) to
    the crown's drum, plus a ring at the flat top's level that carries it and fuses to the cap's roof. The louver stack's
    outline runs up into the crown without a step; the cap's cone and the crown's overhang are hidden behind it."""
    m = uv_mount()
    plates = [original(f"{A.PLATE}.{k}").bounding_box() for k in range(1, A.PITCH_PLATES + 1)]
    r0 = max(max(abs(b[0]), abs(b[1]), b[3], b[4]) for b in plates) + SKIRT_FOOT[0]
    z0 = max(b[5] for b in plates) + SKIRT_FOOT[1]
    r1, z1 = m["r_out"], m["top_z"]
    n = 32
    outer, inner = [], []
    for i in range(n + 1):
        u = i / n
        z = z0 + (z1 - z0) * u
        r = r0 + (r1 - r0) * (3 * u * u - 2 * u ** 3)
        slope = (r1 - r0) * (6 * u - 6 * u * u) / (z1 - z0)            # dr/dz
        outer.append((r, z))
        inner.append((r - SKIRT_T * math.sqrt(1 + slope * slope), z))  # the shell's normal thickness, measured across
    inner = [(r, z) for r, z in inner if z <= z1 - SKIRT_T]
    prof = outer + [(SKIRT_RING_IN, z1), (SKIRT_RING_IN, z1 - SKIRT_T)] + inner[::-1]
    return from_cq(cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0)).val(), 0.005)


@lru_cache(maxsize=None)
def cap_remixed():
    m = uv_mount()
    cap = original(A.CAP)
    lo = cap.bounding_box()[2]
    add, cut = [], []
    for x, y in m["holes"]:                    # a boss under the roof per screw: GRIP of plastic under the head
        add.append(cq.Workplane("XY").workplane(offset=m["seat_z"]).center(x, y).circle(BOSS_D / 2)
                   .extrude(m["top_z"] - 0.5 - m["seat_z"]))
        cut.append(cq.Workplane("XY").workplane(offset=m["seat_z"] - 0.5).center(x, y).circle(HOLE_D / 2)
                   .extrude(GRIP + 2.0))
        cut.append(cq.Workplane("XY").workplane(offset=lo - 2.0).center(x, y).circle(CBORE_D / 2)
                   .extrude(m["seat_z"] - lo + 2.0))
    for w in add:
        cap = cap + from_cq(w)
    cap = cap + skirt()
    for w in cut:
        cap = cap - from_cq(w)
    return cap


def skirt_cover():
    """How much of the louvers' face the skirt stands in front of: (area of the skirt below the top louver plate's
    top, seen from the side, mm^2; that side's louver face, mm^2). The skirt's foot is above the plates: 0."""
    top6 = float(original(f"{A.PLATE}.{A.PITCH_PLATES}").bounding_box()[5])
    low = skirt().trim_by_plane((0.0, 0.0, -1.0), -top6)
    area = low.rotate((0.0, -90.0, 0.0)).project().area() if low.volume() > 1e-6 else 0.0
    return area, (top6 - plates_bottom()) * 100.0


def top_edge(cap, x, y):
    """(distance from (x, y) to the edge of the cap's top face, whether a whole M3 head round it lies on that face),
    measured on a section of the given cap just under its top (the hole's own rim is not an edge)."""
    v, f = arrays(cap)
    z = float(v[:, 2].max()) - 0.02
    seg = A.section_z(v, f, z)
    a, b = seg[:, 0], seg[:, 1]
    ab = b - a
    q = np.array([x, y])
    t = np.clip(((q - a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-18), 0, 1)
    d = np.hypot(*(a + t[:, None] * ab - q).T)
    edge = float(d[d > HOLE_D / 2 + 0.3].min())
    ring = np.array([(x + HEAD_D / 2 * math.cos(u), y + HEAD_D / 2 * math.sin(u)) for u in np.linspace(0, 2 * math.pi, 24, endpoint=False)])
    return edge, bool(A._inside(ring, seg).all())


def outline_gap(m, x, y):
    """Distance (mm) from (x, y) to the part's real outline seen from above (its projection on XY); negative inside."""
    q = np.array([x, y])
    best, inside = float("inf"), False
    for poly in m.project().to_polygons():
        a = np.asarray(poly, float)
        b = np.roll(a, -1, axis=0)
        ab = b - a
        t = np.clip(((q - a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-18), 0, 1)
        best = min(best, float(np.hypot(*(a + t[:, None] * ab - q).T).min()))
        cross = (a[:, 1] > y) != (b[:, 1] > y)
        xs = a[:, 0] + (y - a[:, 1]) * ab[:, 0] / np.where(cross, ab[:, 1], 1)
        inside ^= bool((cross & (xs > x)).sum() % 2)
    return -best if inside else best


def uv_cable_envelope():
    """The UV crown's port gland (its body, GLAND_DROP long, straight out of the drum along +x), the cable's level
    run out to a drip loop, and the cable straight down from there (the largest cable OD plus 2 mm all round) to
    below the arm."""
    d = P.dims("UV")
    (_k, c, a), = [o for o in P.openings("UV") if o[0] == "gland"]
    (p0,) = box_points("UV", [c])
    R, _t = box_pose("UV")
    u = R @ np.asarray(a, float)
    od = S.val("pg7_seal")[1] + 4.0
    p1 = p0 + u * GLAND_DROP
    gland = cyl_axis(p0, p1, S.val("gland_pg7")[2])
    loop = p1 + u * (od / 2 + 6.0)                                   # the cable bends down here
    low = arm_plate()[0] - 120.0
    cable = tube([p1, loop], od) + cyl((loop[0], loop[1]), od, low, loop[2])
    return gland + cable


# ------------------------------------------------------------------ the arm
@lru_cache(maxsize=None)
def upright():
    """The arm's upright, measured: its back plane (y), front plane (y) and its Z span."""
    bb = original(A.ARM).bounding_box()
    _slots, y_back, y_front = clamp_slots()
    return dict(y_back=float(bb[1]), y_front=y_front, z0=float(bb[2]), z1=float(bb[5]))


def saddle_planes():
    """(the upright's back plane, the V's apex, the saddle's back plane): Y in the shield frame."""
    yb = upright()["y_back"]
    return yb, yb - STRAP_SLOT[1] - STRAP_WALL, yb - SADDLE_DEPTH


def pole_axis(d=POLE_D):
    """(x, y) of a pole of diameter d seated in the saddle's V (its axis is vertical)."""
    _yb, ya, _yr = saddle_planes()
    return 0.0, ya - d / 2 / math.sin(math.radians(SADDLE_HALF_ANGLE))


def pole_contacts(d=POLE_D):
    """The two lines where a pole of diameter d touches the V's flanks: [(x, y)], one per flank."""
    a = math.radians(SADDLE_HALF_ANGLE)
    _yb, ya, _yr = saddle_planes()
    s = d / 2 / math.tan(a)                                      # apex to the contact, along a flank
    return [(sg * s * math.sin(a), ya - s * math.cos(a)) for sg in (-1, 1)]


def strap_slots():
    """The two strap tunnels: [dict(x0, x1, y0, y1, z0, z1)], their clear openings in the shield frame."""
    yb, _ya, _yr = saddle_planes()
    w, t = STRAP_SLOT
    return [dict(x0=-SADDLE_HALF_W, x1=SADDLE_HALF_W, y0=yb - t, y1=yb, z0=zc - w / 2, z1=zc + w / 2) for zc in STRAP_SLOT_Z]


def _round_off(x_edge, y_edge, sx, sy, r, z0, z1):
    """A cutter that rounds a convex vertical edge at (x_edge, y_edge) with radius r: the material lies at -sx, -sy."""
    cx, cy = x_edge - sx * r, y_edge - sy * r
    box = _block(min(cx, x_edge + sx), max(cx, x_edge + sx), min(cy, y_edge + sy), max(cy, y_edge + sy), z0, z1)
    return box.cut(cq.Workplane("XY").workplane(offset=z0 - 1).center(cx, cy).circle(r).extrude(z1 - z0 + 2))


@lru_cache(maxsize=None)
def saddle():
    """The pole saddle on the upright's back (a manifold, before it is fused to the arm): a block as wide and tall as the
    upright, a vertical V in its back for the pole, two strap tunnels across it along X, rounded where the straps bend."""
    u = upright()
    yb, ya, yr = saddle_planes()
    w, lip, z0, z1 = SADDLE_HALF_W, SADDLE_LIP, u["z0"], u["z1"]
    prof = [(-w, yb + 0.5), (w, yb + 0.5), (w, yr), (lip, yr), (0.0, ya), (-lip, yr), (-w, yr)]
    blk = cq.Workplane("XY").workplane(offset=z0).polyline(prof).close().extrude(z1 - z0)
    for sl in strap_slots():
        sz0, sz1 = sl["z0"], sl["z1"]
        blk = blk.cut(_block(-w - 1.0, w + 1.0, sl["y0"], yb + 1.0, sz0, sz1))       # the tunnel (the upright is its front wall)
        for sx in (-1, 1):
            blk = blk.cut(_round_off(sx * w, sl["y0"], sx, 1, STRAP_EXIT_R, sz0, sz1))          # its rear edge at the exit
            blk = blk.cut(_round_off(sx * w, yr, sx, -1, SADDLE_CORNER_R, sz0, sz1))            # the back corner
    return from_cq(blk)


@lru_cache(maxsize=None)
def strap_envelope():
    """Where the straps, their heads (or worm housings) and the pole are, for the smallest, the nominal and the largest
    pole the saddle takes: the pole as a long cylinder, each strap as the loop round the saddle's back and the pole
    (STRAP_T thick, a tunnel's width tall), and a STRAP_HEAD behind the pole at each strap."""
    yb, _ya, yr = saddle_planes()
    w, big = SADDLE_HALF_W + STRAP_T, 400.0
    env = None
    for d in (POLE_RANGE[0], POLE_D, POLE_RANGE[1]):
        px, py = pole_axis(d)
        part = cyl((px, py), d, -big, big)
        for sl in strap_slots():
            z0, z1 = sl["z0"], sl["z1"]
            pts = [mf.Manifold.cube((2 * w, 0.01, z1 - z0)).translate((-w, yb - 0.01, z0)),
                   mf.Manifold.cube((2 * w, 0.01, z1 - z0)).translate((-w, yr - STRAP_T, z0)),
                   cyl((px, py), d + 2 * STRAP_T, z0, z1)]
            hw, hp = STRAP_HEAD
            head = from_cq(_block(px - hw / 2, px + hw / 2, py - d / 2 - hp, py, z0 - 1.0, z1 + 1.0))
            part = part + mf.Manifold.batch_hull(pts) + head
        env = part if env is None else env + part
    return env


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
    y0 = saddle_planes()[2]                                              # the saddle's back plane: the print bed
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
    u = upright()
    for zc in STRAP_SLOT_Z:                                              # each tunnel inside the upright's height, walled
        assert u["z0"] + WALL_MIN <= zc - STRAP_SLOT[0] / 2 and zc + STRAP_SLOT[0] / 2 <= u["z1"] - WALL_MIN, zc
    arm = original(A.ARM)
    slots, y_back, y_front = clamp_slots()
    for x0, x1, z0, z1 in slots:                                         # fill the original's small slots
        arm = arm + from_cq(_block(x0 - 0.5, x1 + 0.5, y_back, y_front, z0 - 0.5, z1 + 0.5))
    arm = arm + saddle()
    for name in ("TH", "BARO"):
        m = arm_mount(name)
        x0, x1, y0, y1, z0, z1 = m["face"]
        tx0, tx1 = (x0, -TAB_IN) if x0 < 0 else (TAB_IN, x1)
        arm = arm + from_cq(_block(x0, x1, y0, y1, z0, z1)) + from_cq(_block(tx0, tx1, y_back, y1, lo, hi))
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
    """The ORIGINAL arm's small slots through its upright, measured: [(x0, x1, z0, z1)], and the upright's faces (y).
    The remix fills them (arm_remixed); the straps go through strap_slots() instead."""
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
    out.append(f"cap flat top: Z {m['top_z']:.2f}, a disc of radius {m['flat_r']:.2f}; UV crown (Ø{2 * m['r_out']:.1f}) "
               f"on its axis, port gland to +x, floor flat on the top, four screws up through the cap")
    for x, y in m["holes"]:
        edge, head = top_edge(cap, x, y)
        out.append(f"  UV hole ({x:.2f}, {y:.2f}): {edge:.2f} mm inside the remixed top's edge (needs 3.0); "
                   f"whole Ø{HEAD_D:g} head on it: {head}")
        bad |= edge < 3.0 or not head
    low, face = skirt_cover()
    out.append(f"  skirt: flares out to Ø{2 * m['r_out']:.1f} under the crown; {low:.0f} mm2 of it below the top louver "
               f"plate's top (louver face {face:.0f} mm2)")
    bad |= low > 1.0
    out.append(f"  cap bosses: Ø{BOSS_D:g} under the roof, seat Z {m['seat_z']:.2f} (grip {GRIP:.1f}), "
               f"counterbore Ø{CBORE_D:g} down and out of the cap's bottom")
    env = uv_cable_envelope()
    parts = [A.CAP] + [f"{A.PLATE}.{i}" for i in range(1, 7)] + [A.CUP]
    gaps = {k: env.min_gap(cap if k == A.CAP else asm[k], 50.0) for k in parts}
    gaps["arm"] = env.min_gap(arm, 50.0)
    gaps["BARO box"] = env.min_gap(box_placed("BARO"), 50.0)
    k = min(gaps, key=gaps.get)
    out.append(f"  gland ({GLAND_DROP:g} out of the drum) and cable drop: nearest {k} at {gaps[k]:.2f} mm")
    bad |= gaps[k] <= 1.0
    uv = box_placed("UV")
    out.append(f"  UV box on the cap: overlap {(uv ^ cap).volume():.3f} mm3")
    ok, lines = _part_lines("arm", arm, asm[A.ARM], ARM_PRINT_UP, (0.0, 0.0, 1.0))
    out += lines
    bad |= not ok
    lo, hi, t = arm_plate()
    out.append(f"arm base plate Z {lo:.2f}..{hi:.2f} ({t:.2f} thick); cup radius {cup_radius():.2f}; lowest louver plate Z "
               f"{plates_bottom():.2f}")
    clamp = strap_envelope()
    _yb, ya, yr = saddle_planes()
    out.append(f"  pole saddle: a {2 * SADDLE_HALF_ANGLE:g} degree V, {2 * SADDLE_LIP:g} wide at its back, apex Y {ya:.2f}, "
               f"back Y {yr:.2f}; poles Ø{POLE_RANGE[0]:g}-{POLE_RANGE[1]:g}")
    for d in (POLE_RANGE[0], POLE_D, POLE_RANGE[1]):
        px, py = pole_axis(d)
        pole = cyl((px, py), d - 0.02, upright()["z0"], upright()["z1"])
        touch = cyl((px, py), d + 0.2, upright()["z0"], upright()["z1"]) ^ arm
        lines = len(touch.decompose()) if touch.volume() > 0 else 0
        out.append(f"    Ø{d:g} pole: axis ({px:.2f}, {py:.2f}), overlap {(pole ^ arm).volume():.4f} mm3, touches on {lines} lines")
        bad |= (pole ^ arm).volume() > 1e-3 or lines != 2
    for sl in strap_slots():
        out.append(f"  strap tunnel Z {sl['z0']:.2f}..{sl['z1']:.2f} (centre {(sl['z0'] + sl['z1']) / 2:g}), Y {sl['y0']:.2f}..{sl['y1']:.2f}, "
                   f"{STRAP_SLOT[0]:g} x {STRAP_SLOT[1]:g} clear across X {sl['x0']:g}..{sl['x1']:g}")
        probe = from_cq(_block(sl["x0"] - 2, sl["x1"] + 2, sl["y0"] + 0.01, sl["y1"] - 0.01, sl["z0"] + 0.01, sl["z1"] - 0.01))
        bad |= (probe ^ arm).volume() > 1e-3
    out.append(f"  strap tunnels {STRAP_SLOT_PITCH:g} apart (STRAP_SLOT_PITCH); the original's {len(clamp_slots()[0])} small slots filled")
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
        out.append(f"  {n} clearances: cup {g_cup:.2f}, pole and straps {g_clamp:.2f}, plate 1 {g_pl:.2f} (each needs 5.0); "
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
