"""How Clint's radiation shield (Stevenson_screen_NFS.3mf) goes together, worked out from the meshes' mating features.

The 3MF is read as DATA ONLY (zipfile + XML: vertices, triangles, objects, build items, transforms). It lives outside
git (sources.shield_3mf: local path + sha256; the hash is checked on every open) and nothing derived from its meshes is
written anywhere: this module only computes numbers.

Frames. Every object's mesh is stored about its own bounding-box centre; the build items place them as PRINTED
(`print_layout()`; the cup and the cap are printed flipped about X). `assembled()` puts every mesh in the SHIELD FRAME:
Z up, the plate axis (the centroid of the three post bores, the same for every part) on the Z axis, and Z = 0 on the
floor of the arm's pocket (the face the base cup's foot lands on). Every placement is a pure translation (the meshes'
own orientation is the assembled one; the three-fold post symmetry would also allow turning the stack 120 degrees,
which changes nothing here), and each translation is DERIVED from a mating feature, never assumed:

  base cup  object_67  xy: its three tube bores (r 2.0, on r 25) centred on the axis; z: its foot underside on the
                       arm's pocket floor. Its disc (flat face up) carries the post sockets; its foot (19 x 54, two
                       r 2.25 holes) is the part that meets the arm.
  arm       object_72  xy: its two r 2.5 holes (42 mm apart) on the cup foot's two holes; z: pocket floor at Z = 0.
  stand     object_68  xy: its three foot holes (r 2.0, on r 25) on the axis (the strip is therefore NOT on the axis:
                       2.0 mm off it); z: foot underside on the cup disc.
  plates    object_79  (x6) xy: bores on the axis; z: plate 1's post bottom face on the stand foot's top face, each next
                       plate's post bottom face on the one below's post top face (15 mm posts, so 15 mm pitch).
  cap       object_70  xy: bores on the axis; z: its post bottom face on plate 6's post top face.

Mate errors are measured AFTER placement: `lateral` = how far apart the facing axes or holes are (mm), `axial` = the gap
or overlap between the faces that touch, `clearance` = the smallest free gap round a part that sits in a pocket.
"""
import hashlib
import sys
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import sources as S                  # noqa: E402  hardware/pods-r1/sources.py

CUP, STAND, CAP, ARM, PLATE = "object_67", "object_68", "object_70", "object_72", "object_79"
PITCH_PLATES = 6
SHT45_DEPTH = 4.8                    # board + parts + PTFE cap, mm: the #6174 product page's 25.5 x 17.7 x 4.8 overall (sources 'sht45' row)
assert "4.8" in S._row("sht45")[1]


# ---------------------------------------------------------------- reading the 3MF (data only)
def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _xf(text):
    """A 3MF transform (12 numbers, row vectors: p' = p @ R + t) as (R 3x3, t 3)."""
    a = np.array([float(x) for x in text.split()]).reshape(4, 3)
    return a[:3], a[3]


def _mesh(root):
    v = np.array([[float(e.get(k)) for k in "xyz"] for e in root.iter() if _local(e.tag) == "vertex"])
    f = np.array([[int(e.get(k)) for k in ("v1", "v2", "v3")] for e in root.iter() if _local(e.tag) == "triangle"])
    return v, f


def open_3mf(path=None):
    """Check the file against sources.shield_3mf's sha256 and read it: {'objects': {stem: (V, F)}, 'items': [...]}.
    Each item is {'id': 'object_79.3', 'stem': 'object_79', 'R': 3x3, 't': 3} (the PRINT pose of that copy)."""
    path = Path(path) if path else S.shield_path()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != S.val("shield_3mf")[1]:
        raise RuntimeError(f"{path}: sha256 {digest} is not the one in sources.shield_3mf")
    z = zipfile.ZipFile(path)
    main = ET.fromstring(z.read("3D/3dmodel.model"))
    wrappers = {}
    for o in main.iter():
        if _local(o.tag) == "object":
            wrappers[o.get("id")] = [(c.get("objectid"), next((val for k, val in c.attrib.items() if _local(k) == "path"), None),
                                      c.get("transform")) for c in o.iter() if _local(c.tag) == "component"]
    cache, objects, items, seen = {}, {}, [], {}
    for it in main.iter():
        if _local(it.tag) != "item":
            continue
        Ri, ti = _xf(it.get("transform"))
        for oid, p, tr in wrappers[it.get("objectid")]:
            Rc, tc = _xf(tr) if tr else (np.eye(3), np.zeros(3))
            stem = Path(p).stem
            if stem not in cache:
                tree = ET.fromstring(z.read(p.lstrip("/")))
                holder = next(o for o in tree.iter() if _local(o.tag) == "object" and o.get("id") == oid)
                cache[stem] = _mesh(holder)
            objects[stem] = cache[stem]
            seen[stem] = seen.get(stem, 0) + 1
            items.append({"stem": stem, "n": seen[stem], "R": Rc @ Ri, "t": tc @ Ri + ti})
    for it in items:
        it["id"] = it["stem"] if seen[it["stem"]] == 1 else f"{it['stem']}.{it['n']}"
    return {"objects": objects, "items": items}


@lru_cache(maxsize=1)
def _model():
    return open_3mf()


def print_layout():
    """{id: (V, F)} as printed on the bed (the build items' transforms applied)."""
    m = _model()
    return {it["id"]: (m["objects"][it["stem"]][0] @ it["R"] + it["t"], m["objects"][it["stem"]][1]) for it in m["items"]}


# ---------------------------------------------------------------- slicing
def section_z(v, f, z):
    """Triangle-plane section at height z: an (n, 2, 2) array of xy segments."""
    p = v[f]
    neg = p[:, :, 2] < z
    out = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        c = neg[:, i] != neg[:, j]
        d = p[:, i, 2] - p[:, j, 2]
        t = np.where(c, (p[:, i, 2] - z) / np.where(c, d, 1), 0.0)
        out.append((c, (p[:, i] + t[:, None] * (p[:, j] - p[:, i]))[:, :2]))
    mask = np.stack([c for c, _ in out], 1)
    pts = np.stack([q for _, q in out], 1)                       # (n, 3, 2)
    rows = np.where(mask.sum(1) == 2)[0]
    order = np.argsort(~mask[rows], axis=1, kind="stable")[:, :2]
    a = pts[rows, order[:, 0]]
    b = pts[rows, order[:, 1]]
    return np.stack([a, b], 1) if len(rows) else np.zeros((0, 2, 2))


def loops(segs, nd=3):
    """Chain section segments into closed polylines (a list of (k, 2) arrays)."""
    key = lambda p: (round(float(p[0]), nd), round(float(p[1]), nd))
    adj = {}
    for i, s in enumerate(segs):
        for e in (0, 1):
            adj.setdefault(key(s[e]), []).append((i, e))
    used, out = set(), []
    for i in range(len(segs)):
        if i in used:
            continue
        used.add(i)
        pts, start, end = [segs[i][0], segs[i][1]], key(segs[i][0]), key(segs[i][1])
        while end != start:
            nxt = [(j, e) for j, e in adj.get(end, []) if j not in used]
            if not nxt:
                break
            j, e = nxt[0]
            used.add(j)
            pts.append(segs[j][1 - e])
            end = key(segs[j][1 - e])
        out.append(np.array(pts))
    return out


def fit_circle(p):
    """Kasa least-squares circle: (cx, cy, r, worst radial residual)."""
    a = np.c_[2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))]
    c = np.linalg.lstsq(a, (p ** 2).sum(1), rcond=None)[0]
    r = float(np.sqrt(c[2] + c[0] ** 2 + c[1] ** 2))
    return float(c[0]), float(c[1]), r, float(np.abs(np.hypot(p[:, 0] - c[0], p[:, 1] - c[1]) - r).max())


def circles(v, f, z, rmin, rmax, tol=0.15):
    """Circular loops (centre x, y, radius) of radius rmin..rmax in the section at z, in mesh order of discovery."""
    out = []
    for lp in loops(section_z(v, f, z)):
        if len(lp) >= 16:
            x, y, r, e = fit_circle(lp)
            if rmin <= r <= rmax and e < tol:
                out.append((x, y, r))
    return out


def top_z(v, f, x, y):
    """Highest surface z straight above (x, y) (vertical ray against the triangles), or None."""
    p = v[f]
    x0, y0 = p[:, 0, 0], p[:, 0, 1]
    d = (p[:, 1, 0] - x0) * (p[:, 2, 1] - y0) - (p[:, 2, 0] - x0) * (p[:, 1, 1] - y0)
    ok = np.abs(d) > 1e-12
    dd = np.where(ok, d, 1)
    l1 = ((x - x0) * (p[:, 2, 1] - y0) - (p[:, 2, 0] - x0) * (y - y0)) / dd
    l2 = ((p[:, 1, 0] - x0) * (y - y0) - (x - x0) * (p[:, 1, 1] - y0)) / dd
    l0 = 1 - l1 - l2
    ins = ok & (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
    if not ins.any():
        return None
    return float((l0 * p[:, 0, 2] + l1 * p[:, 1, 2] + l2 * p[:, 2, 2])[ins].max())


def _by_angle(pts):
    pts = np.asarray(pts, float)
    c = pts.mean(0)
    return pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]


# ---------------------------------------------------------------- mating features, in each mesh's own frame
@lru_cache(maxsize=None)
def features(stem):
    """The mating features of one object, in its own mesh frame (mm)."""
    v, f = _model()["objects"][stem]
    ft = {"zmin": float(v[:, 2].min()), "zmax": float(v[:, 2].max())}
    if stem in (PLATE, CAP, CUP):
        z, lo, hi = {PLATE: (1.5, 1.9, 2.1), CAP: (0.0, 1.6, 1.9), CUP: (11.0, 1.9, 2.1)}[stem]
        bores = [(x, y) for x, y, r in circles(v, f, z, lo, hi)]
        tubes = [(x, y, r) for x, y, r in circles(v, f, z, 4.8, 5.2)]
        assert len(bores) == 3 and len(tubes) == 3, (stem, bores, tubes)
        ft["bores"] = _by_angle(bores)
        ft["bore_r"] = float(np.mean([r for _, _, r in circles(v, f, z, lo, hi)]))
        ft["tube_r"] = float(np.mean([r for _, _, r in tubes]))
        near = np.min([np.hypot(v[:, 0] - x, v[:, 1] - y) for x, y in ft["bores"]], axis=0) <= ft["tube_r"] + 0.02
        if stem == CUP:
            near &= v[:, 2] > 0                      # the tube sockets under and in the disc, not the foot's far end
        ft["post_zmin"], ft["post_zmax"] = float(v[near, 2].min()), float(v[near, 2].max())
    if stem == CUP:
        h = [(x, y) for x, y, r in circles(v, f, -12.0, 2.2, 2.3)]
        assert len(h) == 2, h
        ft["holes"] = np.array(sorted(h, key=lambda p: p[1]))
        ft["hole_r"] = circles(v, f, -12.0, 2.2, 2.3)[0][2]
        foot = [lp for lp in loops(section_z(v, f, -14.0)) if 15 < np.ptp(lp[:, 0]) < 25]
        assert len(foot) == 1
        ft["foot_x"] = (float(foot[0][:, 0].min()), float(foot[0][:, 0].max()))
        ft["foot_y"] = (float(foot[0][:, 1].min()), float(foot[0][:, 1].max()))
        ft["foot_z"] = ft["zmin"]                                  # the foot's underside
        ft["disc_top"] = ft["zmax"]                                # the flat face the stand foot lands on
        cab = [(x, y, r) for x, y, r in circles(v, f, 14.0, 2.4, 2.6)]
        assert len(cab) == 1
        ft["cable_hole"] = cab[0]                                  # a Ø5 through-hole, not on a post
    if stem == STAND:
        h = [(x, y) for x, y, r in circles(v, f, -38.5, 1.9, 2.1)]
        assert len(h) == 3, h
        ft["bores"] = _by_angle(h)
        ft["bore_r"] = circles(v, f, -38.5, 1.9, 2.1)[0][2]
        foot = max(loops(section_z(v, f, -38.5)), key=len)
        mid = ft["bores"].mean(0)
        reach = []
        for x, y in ft["bores"]:                                   # how far the foot outline goes past each bore, outward
            u = np.array([x, y]) - mid
            u /= np.hypot(*u)
            reach.append(float(((foot - [x, y]) @ u).max()))
        ft["lobe_r"] = float(np.mean(reach))                       # the foot's rounded lobes, round each bore
        near = np.min([np.hypot(v[:, 0] - x, v[:, 1] - y) for x, y in ft["bores"]], axis=0) <= 4.0
        ft["foot_bottom"], ft["foot_top"] = float(v[near, 2].min()), float(v[near, 2].max())
        strip = [lp for lp in loops(section_z(v, f, -20.0)) if np.ptp(lp[:, 0]) > 10]
        assert len(strip) == 1
        ft["strip_x"] = (float(strip[0][:, 0].min()), float(strip[0][:, 0].max()))
        ft["strip_y"] = (float(strip[0][:, 1].min()), float(strip[0][:, 1].max()))
        ft["strip_top"] = ft["zmax"]
    if stem == ARM:
        h = [(x, y) for x, y, r in circles(v, f, -29.5, 2.4, 2.6)]
        assert len(h) == 2, h
        ft["holes"] = np.array(sorted(h, key=lambda p: p[1]))
        ft["hole_r"] = circles(v, f, -29.5, 2.4, 2.6)[0][2]
        pocket = [lp for lp in loops(section_z(v, f, -27.5)) if 15 < np.ptp(lp[:, 0]) < 25]
        assert len(pocket) == 1
        ft["pocket_x"] = (float(pocket[0][:, 0].min()), float(pocket[0][:, 0].max()))
        ft["pocket_y"] = (float(pocket[0][:, 1].min()), float(pocket[0][:, 1].max()))
        yc = float(np.mean(ft["pocket_y"]))
        ft["pocket_floor"] = top_z(v, f, 5.0, yc)
        ft["rim_top"] = top_z(v, f, 14.0, yc)
        assert ft["pocket_floor"] < ft["rim_top"] - 0.5
    return ft


def _centroid(pts):
    return np.asarray(pts, float).mean(0)


# ---------------------------------------------------------------- placements
@lru_cache(maxsize=1)
def placements():
    """{id: (dx, dy, dz)}: the translation from each object's mesh frame to the shield frame, derived as in the header."""
    pl = {}
    cup, stand, plate, cap, arm = (features(s) for s in (CUP, STAND, PLATE, CAP, ARM))
    # base cup: bores on the axis; foot underside on the pocket floor (Z = 0)
    cx, cy = -_centroid(cup["bores"])
    pl[CUP] = np.array([cx, cy, -cup["foot_z"]])
    # arm: its two holes on the cup foot's two holes; pocket floor at Z = 0
    ch = cup["holes"] + [cx, cy]
    ax, ay = (ch - arm["holes"]).mean(0)
    pl[ARM] = np.array([ax, ay, -arm["pocket_floor"]])
    # stand: foot holes on the axis; foot underside on the cup disc
    sx, sy = -_centroid(stand["bores"])
    pl[STAND] = np.array([sx, sy, (cup["disc_top"] + pl[CUP][2]) - stand["foot_bottom"]])
    # plates, bottom to top; then the cap
    z_on = stand["foot_top"] + pl[STAND][2]
    px, py = -_centroid(plate["bores"])
    for k in range(1, PITCH_PLATES + 1):
        pl[f"{PLATE}.{k}"] = np.array([px, py, z_on - plate["post_zmin"]])
        z_on = plate["post_zmax"] + pl[f"{PLATE}.{k}"][2]
    kx, ky = -_centroid(cap["bores"])
    pl[CAP] = np.array([kx, ky, z_on - cap["post_zmin"]])
    return pl


@lru_cache(maxsize=1)
def assembled():
    """{object id: (vertices, faces)} in the shield frame (Z up, plate axis on the Z axis, Z = 0 on the arm's pocket
    floor). The plates are 'object_79.1' (bottom) to 'object_79.6' (top)."""
    m = _model()
    out = {}
    for it in m["items"]:
        stem = it["stem"]
        v, f = m["objects"][stem]
        out[it["id"]] = (v + placements()[it["id"]], f)
    return out


def _axes(oid):
    ft = features(oid.split(".")[0])
    return ft["bores"] + placements()[oid][:2]


# ---------------------------------------------------------------- mates
def mates():
    """The mating features of the shield, measured after placement. One dict per mate:
    mate (name), lateral (mm, axes/holes), axial (mm, gap between touching faces; + = gap, - = overlap), and where it
    applies clearance (smallest free gap), radial (lobe vs tube radius)."""
    pl = placements()
    cup, stand, plate, cap, arm = (features(s) for s in (CUP, STAND, PLATE, CAP, ARM))
    out = []

    def lateral(a, b):
        return float(np.hypot(*(np.asarray(a) - np.asarray(b)).T).max())

    cup_axes = cup["bores"] + pl[CUP][:2]
    stand_axes = stand["bores"] + pl[STAND][:2]
    out.append({"mate": "stand foot on cup", "lateral": lateral(stand_axes, cup_axes),
                "axial": stand["foot_bottom"] + pl[STAND][2] - (cup["disc_top"] + pl[CUP][2]),
                "radial": stand["lobe_r"] - cup["tube_r"]})
    prev_axes, prev_top, prev_name = stand_axes, stand["foot_top"] + pl[STAND][2], "stand foot"
    for k in range(1, PITCH_PLATES + 1):
        oid = f"{PLATE}.{k}"
        out.append({"mate": f"plate {k} on {prev_name}", "lateral": lateral(_axes(oid), prev_axes),
                    "axial": plate["post_zmin"] + pl[oid][2] - prev_top})
        prev_axes, prev_top, prev_name = _axes(oid), plate["post_zmax"] + pl[oid][2], f"plate {k}"
    out.append({"mate": f"cap on {prev_name}", "lateral": lateral(_axes(CAP), prev_axes),
                "axial": cap["post_zmin"] + pl[CAP][2] - prev_top})
    # the cup's foot in the arm's pocket, bolted through two holes
    holes_cup = cup["holes"] + pl[CUP][:2]
    holes_arm = arm["holes"] + pl[ARM][:2]
    foot_x = np.array(cup["foot_x"]) + pl[CUP][0]
    foot_y = np.array(cup["foot_y"]) + pl[CUP][1]
    pk_x = np.array(arm["pocket_x"]) + pl[ARM][0]
    pk_y = np.array(arm["pocket_y"]) + pl[ARM][1]
    centre = np.array([np.mean(foot_x) - np.mean(pk_x), np.mean(foot_y) - np.mean(pk_y)])
    gaps = [foot_x[0] - pk_x[0], pk_x[1] - foot_x[1], foot_y[0] - pk_y[0], pk_y[1] - foot_y[1]]
    out.append({"mate": "cup foot in arm", "holes": len(holes_cup),
                "lateral": max(lateral(holes_cup, holes_arm), float(np.hypot(*centre))),
                "axial": cup["foot_z"] + pl[CUP][2] - (arm["pocket_floor"] + pl[ARM][2]),
                "clearance": float(min(gaps)), "gaps_xxyy": [float(g) for g in gaps],
                "bolt_clearance": float(arm["hole_r"] - cup["hole_r"])})
    return out


# ---------------------------------------------------------------- independent checks on the PLACED meshes
# The placements above set each part's bore centroid and one face; these re-measure the assembled vertices themselves
# (sections of the placed meshes, not features + translation), and test things the placement never sets.
_BORE_PROBE = {PLATE: (1.5, 1.9, 2.1), CAP: (0.0, 1.6, 1.9), CUP: (11.0, 1.9, 2.1), STAND: (-38.5, 1.9, 2.1)}


def placed_axes(oid):
    """The three bore centres of a placed part, measured on its placed mesh (sorted by angle about the axis)."""
    stem = oid.split(".")[0]
    z, lo, hi = _BORE_PROBE[stem]
    v, f = assembled()[oid]
    c = circles(v, f, z + placements()[oid][2], lo, hi)
    assert len(c) == 3, (oid, c)
    return _by_angle([(x, y) for x, y, _ in c])


def placed_post_faces(oid):
    """(bottom z, top z) of a placed plate's or cap's post tubes, from its placed vertices."""
    v = assembled()[oid][0]
    ax = placed_axes(oid)
    r = features(oid.split(".")[0])["tube_r"] + 0.02
    near = np.min([np.hypot(v[:, 0] - x, v[:, 1] - y) for x, y in ax], axis=0) <= r
    return float(v[near, 2].min()), float(v[near, 2].max())


def _inside(pts, segs):
    """Even-odd: which of pts (n, 2) lie inside material bounded by segs (m, 2, 2) (a ray along +x)."""
    a, b = segs[:, 0], segs[:, 1]
    ab = b - a
    n = np.zeros(len(pts), int)
    for i in range(0, len(pts), 256):
        q = pts[i:i + 256]
        cross = (a[None, :, 1] > q[:, None, 1]) != (b[None, :, 1] > q[:, None, 1])
        xs = a[None, :, 0] + (q[:, None, 1] - a[None, :, 1]) * ab[None, :, 0] / np.where(ab[None, :, 1] == 0, 1, ab[None, :, 1])
        n[i:i + 256] = (cross & (xs > q[:, None, 0])).sum(1)
    return n % 2 == 1


def clash(a, b, levels=7, margin=0.05):
    """Sampled cross-section overlap of two placed meshes a, b = (V, F): at `levels` heights through the Z range they
    share, the number of section-segment midpoints of one lying inside the material of the other. 0 = no clash."""
    lo, hi = max(a[0][:, 2].min(), b[0][:, 2].min()) + margin, min(a[0][:, 2].max(), b[0][:, 2].max()) - margin
    if hi <= lo:
        return 0
    hits = 0
    for z in np.linspace(lo, hi, levels):
        sa, sb = section_z(*a, z), section_z(*b, z)
        if not len(sa) or not len(sb):
            continue
        for p, q in ((sa, sb), (sb, sa)):
            mid = p.mean(1)
            near = (mid[:, 0] > q[:, :, 0].min() - 1) & (mid[:, 0] < q[:, :, 0].max() + 1) & \
                   (mid[:, 1] > q[:, :, 1].min() - 1) & (mid[:, 1] < q[:, :, 1].max() + 1)
            hits += int(_inside(mid[near], q).sum())
    return hits


def clash_pairs():
    """The pairs of neighbouring placed parts that must not overlap: the post chain, the stand against every plate and
    the cap (its strip runs up the core), and the cup against the arm."""
    chain = [CUP, STAND] + [f"{PLATE}.{k}" for k in range(1, PITCH_PLATES + 1)] + [CAP]
    pairs = list(zip(chain, chain[1:])) + [(CUP, ARM)]
    pairs += [(STAND, i) for i in chain[2:]]
    return pairs


def independent_checks():
    """Facts measured on the placed meshes that no placement sets:
    axis_radius: distance of every measured bore centre from the axis, per part (all should be 25.0);
    lateral: per-bore distance between the facing bores of each mating pair of parts, (name, mm);
    pitch: spacing between consecutive plates' post bottom faces; post_length: each plate's post length (should agree);
    radial: stand foot lobe radius minus the post tube radius (mm);
    fits: (name, per-side clearance mm) for the cup foot's holes in the arm's holes and the foot in its pocket;
    clash: {pair: count} from `clash`."""
    chain = [CUP, STAND] + [f"{PLATE}.{k}" for k in range(1, PITCH_PLATES + 1)] + [CAP]
    ax = {i: placed_axes(i) for i in chain}
    out = {"axis_radius": {i: [float(np.hypot(*p)) for p in a] for i, a in ax.items()}}
    out["lateral"] = [(f"{b} on {a}", float(np.hypot(*(ax[a] - ax[b]).T).max())) for a, b in zip(chain, chain[1:])]
    plates = [f"{PLATE}.{k}" for k in range(1, PITCH_PLATES + 1)]
    faces = [placed_post_faces(i) for i in plates]
    out["pitch"] = [faces[k + 1][0] - faces[k][0] for k in range(len(faces) - 1)]
    out["post_length"] = [t - b for b, t in faces]
    out["radial"] = features(STAND)["lobe_r"] - features(CUP)["tube_r"]
    cup, arm = features(CUP), features(ARM)
    pl = placements()
    gaps = [g for x in mates() if x["mate"] == "cup foot in arm" for g in x["gaps_xxyy"]]
    out["fits"] = [("bolt hole radius, arm minus cup foot", float(arm["hole_r"] - cup["hole_r"]))] + \
                  [(f"pocket wall {n}", float(g)) for n, g in zip(("x-", "x+", "y-", "y+"), gaps)]
    asm = assembled()
    out["clash"] = {f"{a} / {b}": clash(asm[a], asm[b]) for a, b in clash_pairs()}
    return out


# ---------------------------------------------------------------- the clear core
def _core_ids():
    return [i for i in assembled() if i.startswith(PLATE) or i in (CAP, CUP)]


def _sections(z, ids):
    return [section_z(*assembled()[i], z) for i in ids]


def core_clear(z):
    """Radius (mm) of the largest circle about the plate axis, at height z, that touches no plate, cap or cup material
    (the stand and the arm are not part of the core). 0 if the axis itself is inside material; inf if nothing is cut."""
    best = float("inf")
    for zz in (z - 1e-4, z + 1e-4):             # a plane exactly on a face (a post end) cuts nothing: look just either side
        segs = [s for s in _sections(zz, _core_ids()) if len(s)]
        if segs:
            best = min(best, _clear_in(np.concatenate(segs)))
    return best


def _clear_in(s):
    a, b = s[:, 0], s[:, 1]
    ab = b - a
    t = np.clip(-(a * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-18), 0, 1)
    d = float(np.hypot(*(a + t[:, None] * ab).T).min())
    # even-odd test: a ray from the axis along +x crosses the section's segments an odd number of times when inside material
    cross = ((a[:, 1] > 0) != (b[:, 1] > 0))
    xs = a[:, 0] + (0 - a[:, 1]) * ab[:, 0] / np.where(cross, ab[:, 1], 1)
    inside = int((cross & (xs > 0)).sum()) % 2 == 1
    return 0.0 if inside else d


def stack_span():
    """(low, high) Z of the plate stack: plate 1's post bottom face to plate 6's post top face."""
    plate = features(PLATE)
    return (plate["post_zmin"] + placements()[f"{PLATE}.1"][2],
            plate["post_zmax"] + placements()[f"{PLATE}.{PITCH_PLATES}"][2])


# ---------------------------------------------------------------- the stand and the SHT45
def _strip():
    st, p = features(STAND), placements()[STAND]
    return (np.array(st["strip_x"]) + p[0], np.array(st["strip_y"]) + p[1],
            st["foot_top"] + p[2], st["strip_top"] + p[2])


def stand_face(side="inner"):
    """The strip's flat face the SHT45 goes on: (origin, normal, extent). origin = the face's centre (shield frame),
    normal = outward unit vector, extent = (width along X, height along Z). 'inner' is the face on the side of the strip's
    middle where the plate axis lies (the strip is 2.0 mm off the axis, so the axis is in its thickness, 0.5 mm behind this
    face); 'outer' is the face turned away."""
    xs, ys, z0, z1 = _strip()
    toward_axis = 1.0 if (0.0 - float(ys.mean())) >= 0 else -1.0       # which way the plate axis lies from the strip's middle
    n = toward_axis if side == "inner" else -toward_axis
    y = float(ys.max()) if n > 0 else float(ys.min())
    return (np.array([float(xs.mean()), y, (z0 + z1) / 2]), np.array([0.0, n, 0.0]),
            (float(xs[1] - xs[0]), float(z1 - z0)))


def sht45_box(side="inner"):
    """The SHT45 #6174 as a box on the stand face, long side vertical, its centre at the middle of the plate stack:
    ((x0, x1), (y0, y1), (z0, z1)) in the shield frame."""
    w, h = S.val("sht45")                                     # 25.4 x 17.78: width x height
    origin, normal, extent = stand_face(side)
    lo, hi = stack_span()
    xs, ys, z0, z1 = _strip()
    zc = (lo + hi) / 2
    assert z0 <= zc - w / 2 and zc + w / 2 <= z1, "the board does not fit on the strip at mid-stack"
    y0, y1 = sorted((origin[1], origin[1] + normal[1] * SHT45_DEPTH))
    return ((origin[0] - h / 2, origin[0] + h / 2), (y0, y1), (zc - w / 2, zc + w / 2))


def _rect_dist(pts, x0, x1, y0, y1):
    dx = np.maximum(np.maximum(x0 - pts[:, 0], pts[:, 0] - x1), 0)
    dy = np.maximum(np.maximum(y0 - pts[:, 1], pts[:, 1] - y1), 0)
    return np.hypot(dx, dy)


def sht45_fit_detail(side="inner"):
    """Minimum clearance (mm) from the SHT45 box to the posts, plates, cap and cup, with what is nearest and where."""
    (x0, x1), (y0, y1), (z0, z1) = sht45_box(side)
    best = (float("inf"), None, None)
    ids = _core_ids()
    for z in np.arange(z0, z1 + 1e-9, 1.0):
        for i, s in zip(ids, _sections(float(z), ids)):
            if not len(s):
                continue
            a, b = s[:, 0], s[:, 1]
            n = np.maximum(1, np.ceil(np.hypot(*(b - a).T) / 0.5)).astype(int)
            for k in range(int(n.max()) + 1):                  # points along every segment, at most 0.5 mm apart
                t = np.minimum(k / n, 1.0)[:, None]
                d = _rect_dist(a + t * (b - a), x0, x1, y0, y1)
                j = int(d.argmin())
                if d[j] < best[0]:
                    best = (float(d[j]), i, float(z))
    return {"fit": best[0], "nearest": best[1], "at_z": best[2], "box": ((x0, x1), (y0, y1), (z0, z1))}


def sht45_fit():
    """Minimum clearance (mm) from the SHT45 on the stand's inner face to any post or plate (and the cap and cup)."""
    return sht45_fit_detail("inner")["fit"]


# ---------------------------------------------------------------- report
def main():
    path = S.shield_path()
    if not path.exists():
        print(f"shield 3MF not present at {path}: skipped")
        return 0
    print(f"shield 3MF {path} sha256 ok ({S.val('shield_3mf')[1][:8]}...)")
    print("placements (shield frame, Z = 0 on the arm pocket floor):")
    for oid, p in placements().items():
        print(f"  {oid:12s} dx {p[0]:8.3f} dy {p[1]:8.3f} dz {p[2]:8.3f}")
    print("mates:")
    bad = False
    for x in mates():
        extra = "".join(f" {k} {v:.3f}" for k, v in x.items() if k in ("radial", "clearance", "bolt_clearance"))
        print(f"  {x['mate']:24s} lateral {x['lateral']:.3f} axial {x['axial']:+.3f}{extra}")
        bad |= x["lateral"] > 0.3 or abs(x["axial"]) > 0.3 or x.get("clearance", 0) < 0
    lo, hi = stack_span()
    cc = [core_clear(float(z)) for z in np.linspace(lo, hi, 91)]
    print(f"plate stack Z {lo:.1f}..{hi:.1f}: core clear radius min {min(cc):.3f} (needs 20), max {max(cc):.3f}")
    o, n, e = stand_face()
    xs, ys, _, top = _strip()
    print(f"stand strip: x {xs[0]:.2f}..{xs[1]:.2f}, y {ys[0]:.2f}..{ys[1]:.2f} (centre {ys.mean():+.2f} mm off the axis), "
          f"reaches r {np.hypot(max(abs(xs)), max(abs(ys))):.1f} of the core's 20; top Z {top:.1f}, cap ceiling Z "
          f"{features(CAP)['post_zmax'] + placements()[CAP][2]:.1f}")
    print(f"stand face (inner): origin {o.round(2).tolist()} normal {n.tolist()} extent {e[0]:.1f} x {e[1]:.1f}")
    for side in ("inner", "outer"):
        d = sht45_fit_detail(side)
        print(f"SHT45 on the {side} face: clearance {d['fit']:.2f} mm to {d['nearest']} at Z {d['at_z']:.1f} (needs 5.0)")
    ind = independent_checks()
    print("independent (placed-mesh) checks:")
    print("  bore radius from axis, all parts: %.3f..%.3f" % (min(min(v) for v in ind["axis_radius"].values()),
                                                           max(max(v) for v in ind["axis_radius"].values())))
    print("  per-bore lateral, worst pair: %s %.3f" % max(ind["lateral"], key=lambda t: t[1]))
    print("  plate pitch %s, post length %s" % ([round(x, 3) for x in ind["pitch"]], [round(x, 3) for x in ind["post_length"]]))
    print("  foot lobe vs post tube radius: %+.3f; " % ind["radial"] + "; ".join(f"{n} {g:.2f}" for n, g in ind["fits"]))
    print("  clashes: %d over %d pairs" % (sum(ind["clash"].values()), len(ind["clash"])))
    bad |= (any(g > 0.3 for _, g in ind["lateral"]) or any(abs(p - ind["post_length"][0]) > 0.3 for p in ind["pitch"])
            or abs(ind["radial"]) > 0.3 or any(not 0 < g <= 0.5 for _, g in ind["fits"]) or any(ind["clash"].values()))
    ok = not bad and min(cc) >= 20.0 - 1e-6 and sht45_fit() >= 5.0
    print("shield: every check passes" if ok else "shield: MISFIT (see numbers above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
