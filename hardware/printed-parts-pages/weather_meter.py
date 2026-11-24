"""The SparkFun SEN-15901 weather meter kit (Argent Data Systems 80422 sensors) as simple CadQuery shapes, for the
full-assembly page. Bought, not printed: these are recognisable stand-ins, not the real parts' geometry.

Sources (checked 2026-11-24):
- SparkFun SEN-15901 datasheet, https://cdn.sparkfun.com/assets/d/1/e/0/6/DS-15901-Weather_Meter.pdf, and Argent's
  80422 datasheet, https://www.argentdata.com/files/80422_datasheet.pdf: the wind sensor arm mounts on top of the
  two-piece metal mast and carries the vane and the cups; a short cable joins the two wind sensors, held by clips
  under the arm; the rain gauge mounts lower on the mast on its own arm. Neither gives a single dimension.
- SparkFun's Weather Meter Hookup Guide, https://learn.sparkfun.com/tutorials/weather-meter-hookup-guide: two metal
  tubes that slide together, a center-mount armature (the cross arm) screwed to the top tube, a side-mount armature
  (the rain arm) whose two halves clamp round the tube, two gear clamps to mount the mast, zip ties for the cables.
  No dimensions either.
- The only published size found: about 72.4 x 20.3 cm overall (28.5 x 8 in), from retailer listings (Kiwi
  Electronics), not SparkFun, and not saying whether it's the assembled kit or the box.

So every number below is ESTIMATED, sized to look right and to fit inside that 72.4 cm overall height. Measure the
real kit and change them here.
"""
import math

import cadquery as cq

# ---------------------------------------------------------------- kit dimensions (mm), all ESTIMATED
MAST_D = 19.0              # ESTIMATED: both mast tubes' OD (steel tube, painted)
MAST_TUBE_L = 330.0        # ESTIMATED: each of the two tubes; they slide together over MAST_JOIN
MAST_JOIN = 25.0           # ESTIMATED: the swaged spigot overlap where the two tubes meet
ARM_L = 340.0              # ESTIMATED: the center-mount cross arm, tip to tip
ARM_W, ARM_H = 22.0, 14.0  # ESTIMATED: its section
HUB = (40.0, 30.0, 45.0)   # ESTIMATED: the arm's centre block over the top tube (x, y, z)
SENSOR_AT = 155.0          # ESTIMATED: the cups and the vane this far either side of the mast's axis
BODY_D, BODY_H = 30.0, 60.0   # ESTIMATED: each wind sensor's spindle housing on the arm
CUP_D = 52.0               # ESTIMATED: anemometer cup diameter (three cups)
CUP_R = 70.0               # ESTIMATED: cup centre radius from the spindle (rotor about 190 across)
VANE_L = 180.0             # ESTIMATED: wind vane, tail fin to arrow tip
VANE_TAIL_FROM = 30.0      # ESTIMATED: how far behind the spindle the tail fin starts
VANE_FIN = (80.0, 70.0)    # ESTIMATED: tail fin length x height
GAUGE = (120.0, 60.0, 90.0)   # ESTIMATED: the rain gauge body, along the arm x across x tall
FUNNEL = (110.0, 52.0, 40.0)  # ESTIMATED: the funnel's top opening (along x across) and depth
RAIN_ARM_L = 150.0         # ESTIMATED: the side-mount rain arm, its clamp's axis (here the pole's) to the gauge's centre
RAIN_CLAMP = (36.0, 36.0, 40.0)  # ESTIMATED: the rain arm's two-half clamp block (made for the kit's tube; drawn round the pole)
CLAMP_W, CLAMP_T = 9.0, 0.8      # ESTIMATED: the kit's gear clamps, band width x thickness
WORM = (14.0, 10.0, 8.0)   # ESTIMATED: a gear clamp's worm housing: along the band x tall x proud
CABLE_D = 4.0              # ESTIMATED: the flat RJ11 cables, drawn round
TIE_HEAD = (12.0, 10.5, 7.5)     # ESTIMATED: a Panduit PLT4H zip tie's head: along the band x tall x proud (not measured)


def cyl(d, h, base=(0, 0, 0), axis=(0, 0, 1)):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, h, cq.Vector(*base), cq.Vector(*axis)))


def block(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def hull_pts(circles, n=72):
    """Points on the convex hull of some circles [(x, y, r)], counter-clockwise."""
    pts = [(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n))
           for x, y, r in circles for k in range(n)]
    pts = sorted(set((round(a, 4), round(b, 4)) for a, b in pts))
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cr(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def perimeter(pts):
    return sum(math.dist(pts[i], pts[i - 1]) for i in range(len(pts)))


def gear_clamp(circles, z, worm_dir, w=CLAMP_W, t=CLAMP_T, head=WORM):
    """A band w wide and t thick round the hull of `circles` at height z (centred), with its worm housing (or a zip
    tie's head: `head` = along the band x tall x proud) on the side `worm_dir` (x, y). Returns (shape, the loop's
    inner length as a circle's diameter, the inner length)."""
    inner = hull_pts(circles)
    outer = hull_pts([(x, y, r + t) for x, y, r in circles])
    band = (cq.Workplane("XY").workplane(offset=z - w / 2).polyline(outer).close().extrude(w)
            .cut(cq.Workplane("XY").workplane(offset=z - w / 2 - 1).polyline(inner).close().extrude(w + 2)))
    far = max(outer, key=lambda p: p[0] * worm_dir[0] + p[1] * worm_dir[1])
    a = math.atan2(worm_dir[1], worm_dir[0])
    hd = (cq.Workplane("XY").box(head[2], head[0], head[1]).rotate((0, 0, 0), (0, 0, 1), math.degrees(a))
          .translate((far[0] + math.cos(a) * head[2] / 2, far[1] + math.sin(a) * head[2] / 2, z)))
    return band.union(hd), perimeter(inner) / math.pi, perimeter(inner)


def anemometer(x, z_arm):
    """The cups on the arm's end at x. Returns (housing, rotor, pivot): the spindle housing stays put; the rotor (hub,
    three spokes, three hollow cups) turns about the vertical line through pivot (x, 0, top of the housing).

    Each cup's open (concave) face looks along +t, the anticlockwise tangent seen from above. A cup catches more wind
    on its concave face than on its round back, so the cup whose concave face is upwind gets pushed downwind, and the
    rotor turns towards the cups' round backs: clockwise seen from above (negative about +Z)."""
    z0 = z_arm + ARM_H / 2
    housing = cyl(BODY_D, BODY_H, (x, 0, z0))
    zt = z0 + BODY_H
    s = cyl(BODY_D * 1.2, 12.0, (x, 0, zt))
    zc = zt + 6.0
    for k in range(3):
        a = 2 * math.pi * k / 3
        ux, uy = math.cos(a), math.sin(a)
        s = s.union(cyl(5.0, CUP_R, (x, 0, zc), (ux, uy, 0)))
        cx, cy = x + CUP_R * ux, CUP_R * uy
        # a hemisphere shell opening tangentially (all three the same way round)
        tx, ty = -uy, ux
        ball = cq.Workplane("XY").sphere(CUP_D / 2).cut(cq.Workplane("XY").sphere(CUP_D / 2 - 1.5))
        half = ball.cut(cq.Workplane("XY").box(CUP_D * 2, CUP_D * 2, CUP_D * 2).translate((CUP_D, 0, 0)))
        half = half.rotate((0, 0, 0), (0, 0, 1), math.degrees(math.atan2(ty, tx))).translate((cx, cy, zc))
        s = s.union(half)
    return housing, s, (x, 0.0, zt)


def vane(x, z_arm):
    """The vane on the arm's end at x. Returns (housing, rotor, pivot): the spindle housing stays put; the rotor (a
    collar, a boom along y, a tail fin behind and an arrowhead in front, the arrow at +y) turns about the vertical line
    through pivot (x, 0, top of the housing). Tail downwind, so the arrow points where the wind comes from."""
    z0 = z_arm + ARM_H / 2
    zb = z0 + BODY_H + 8.0
    housing = cyl(BODY_D, BODY_H, (x, 0, z0))
    s = cyl(BODY_D * 0.8, 10.0, (x, 0, z0 + BODY_H))
    front = VANE_L - VANE_TAIL_FROM - VANE_FIN[0]            # the arrow's tip this far in front of the spindle
    back = VANE_TAIL_FROM + VANE_FIN[0]
    s = s.union(cyl(6.0, front + back - 30.0, (x, -back + 10.0, zb), (0, 1, 0)))
    fl, fh = VANE_FIN
    fin = (cq.Workplane("YZ").polyline([(-VANE_TAIL_FROM, -8.0), (-back, -fh / 2), (-back, fh / 2),
                                       (-VANE_TAIL_FROM, 8.0)]).close().extrude(2.0).translate((x - 1.0, 0, zb)))
    tip = (cq.Workplane("YZ").polyline([(front - 35.0, -12.0), (front, 0), (front - 35.0, 12.0)]).close()
           .extrude(6.0).translate((x - 3.0, 0, zb)))
    return housing, s.union(fin).union(tip), (x, 0.0, z0 + BODY_H)


def rain_gauge(cx, cy, z_top_of_arm):
    """A box with a funnel recess on top, standing level on the rain arm's end."""
    L, W, H = GAUGE
    fl, fw, fd = FUNNEL
    z0 = z_top_of_arm
    body = cq.Workplane("XY").box(W, L, H, centered=(True, True, False)).edges("|Z").fillet(8.0)
    funnel = (cq.Workplane("XY").workplane(offset=H - fd).rect(8.0, 8.0).workplane(offset=fd + 0.01)
              .rect(fw, fl).loft())
    return body.cut(funnel).translate((cx, cy, z0))


HOSE_CLAMP = (12.0, 0.8, (16.0, 12.0, 9.0))   # ESTIMATED: an SAE 20 worm-drive clamp: band w x t, the worm housing
PLAIN_TIE = (4.8, 1.3, (8.0, 6.0, 5.0))       # ESTIMATED: a plain UV-black wire tie: band w x t, its head


def tube_path(path, d=CABLE_D):
    """A round cable of diameter d along the polyline `path` [(x, y, z)], with a ball at each bend, as a manifold3d
    solid (OCC's booleans drop pieces of a long chain of cylinders). Returns (solid, its length)."""
    import manifold3d as m3d
    import numpy as np
    parts, length = [m3d.Manifold.sphere(d / 2, 24).translate(tuple(path[0]))], 0.0
    for a, b in zip(path, path[1:]):
        v = np.subtract(b, a, dtype=float)
        L = float(np.linalg.norm(v))
        if L < 1e-6:
            continue
        length += L
        u = v / L
        z = np.array([0.0, 0.0, 1.0])
        k = np.cross(z, u)
        sn, c = np.linalg.norm(k), float(z @ u)
        if sn < 1e-9:
            R = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
        else:
            k = k / sn
            K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
            R = np.eye(3) + sn * K + (1 - c) * K @ K
        M = np.c_[R, np.asarray(a, float)]
        parts.append(m3d.Manifold.cylinder(L, d / 2, d / 2, 24).transform(M.tolist()))
        parts.append(m3d.Manifold.sphere(d / 2, 24).translate(tuple(b)))
    return m3d.Manifold.batch_boolean(parts, m3d.OpType.Add), length


def build(p):
    """p (from build.py, the assembly frame: mm, Z up from the ground, the pole's axis on Z at x = y = 0, north +y,
    east +x). build.py does the layout; this draws the kit and the bought bits round it:
      pole_r; mast = dict(y, foot): the kit's mast beside the pole's top end, its axis at (0, y), its foot at z foot;
      rain = dict(z, side): the rain arm's top face at z, its clamp round the pole, the arm out along (0, side);
      bands = [dict(key, circles=[(x, y, r)], z, w, t, head=(along, tall, proud), dir=(x, y))]: clamps and ties, each a
        band round the hull of its circles (meter-clamps: the kit's gear clamps; pole-straps: the bracket's two zip
        ties; pole-ties: plain ties on the cable bundle; tx-clamps: the TX base's hose clamps);
      cables = {key: {name: [polyline, ...]}}: the RJ11 runs (the first polyline is the run, any more are jumpers).
    Returns [(key, shape, info)].

    The two parts that move with the wind (meter-cups, the cup rotor; meter-vane, the vane) are their own meshes, and
    their info carries pivot = {at: [x, y, z], axis: [0, 0, 1]} in the assembly frame; their spindle housings are the
    static meter-cups-housing and meter-vane-housing. The rain gauge is one closed box here (no tipping bucket inside),
    so nothing in it moves. The cups are on +x (east), the vane on -x (west)."""
    my, m0 = p["mast"]["y"], p["mast"]["foot"]
    mast_top = m0 + 2 * MAST_TUBE_L - MAST_JOIN
    out = []
    lower = cyl(MAST_D, MAST_TUBE_L, (0, my, m0))
    upper = cyl(MAST_D, MAST_TUBE_L, (0, my, m0 + MAST_TUBE_L - MAST_JOIN)).union(
        cyl(MAST_D + 2.0, 8.0, (0, my, m0 + MAST_TUBE_L - MAST_JOIN)))       # the join, drawn as a small collar
    out.append(("meter-mast", lower.union(upper), dict(z=[round(m0, 1), round(mast_top, 1)], y=round(my, 2))))

    # the cross arm on top: a hub over the top tube, the bar along x (east-west)
    za = arm_z(m0)
    hx, hy, hz = HUB
    arm = block(-hx / 2, hx / 2, my - hy / 2, my + hy / 2, za - hz + ARM_H / 2, za + ARM_H / 2)
    arm = arm.union(block(-ARM_L / 2, ARM_L / 2, my - ARM_W / 2, my + ARM_W / 2, za - ARM_H / 2, za + ARM_H / 2))
    arm = arm.cut(cyl(MAST_D, mast_top - (za - hz) + ARM_H / 2, (0, my, za - hz + ARM_H / 2 - 1.0)))  # its socket
    out.append(("meter-arm", arm, dict(z=round(za, 1))))
    # the two wind sensors: a static spindle housing each, and the part that moves, with its pivot (a vertical axis)
    for key, fn, x in (("meter-cups", anemometer, SENSOR_AT), ("meter-vane", vane, -SENSOR_AT)):
        housing, rotor, (px, py, pz) = fn(x, za)
        out.append((key + "-housing", housing.translate((0, my, 0)), dict(x=x)))
        out.append((key, rotor.translate((0, my, 0)),
                    dict(x=x, pivot=dict(at=[round(px, 3), round(py + my, 3), round(pz, 3)], axis=[0, 0, 1]))))

    # the rain arm, level, its clamp round the pole, out along (0, side) to the gauge
    zr, sd = p["rain"]["z"], p["rain"]["side"]
    cx, cy, cz = RAIN_CLAMP
    rarm = block(-cx / 2, cx / 2, -cy / 2, cy / 2, zr - cz, zr)
    y0, y1 = sorted((0.0, sd * (RAIN_ARM_L + 20.0)))
    rarm = rarm.union(block(-10.0, 10.0, y0, y1, zr - 12.0, zr)).cut(cyl(2 * p["pole_r"], cz + 2.0, (0, 0, zr - cz - 1.0)))
    out.append(("meter-rain-arm", rarm, dict(z=round(zr, 1), reach=RAIN_ARM_L)))
    gy = sd * RAIN_ARM_L
    out.append(("meter-rain", rain_gauge(0, gy, zr), dict(z=round(zr, 1), funnel=dict(
        c=[0.0, gy], size=[FUNNEL[1], FUNNEL[0]], top=round(zr + GAUGE[2], 2)))))

    # the bands: clamps and ties, one mesh per key
    bands = {}
    for b in p["bands"]:
        c, loop, L = gear_clamp([tuple(x) for x in b["circles"]], b["z"], tuple(b["dir"]), w=b["w"], t=b["t"],
                                head=tuple(b["head"]))
        k = bands.setdefault(b["key"], dict(shape=None, z=[], loop_d=[], loop_mm=[]))
        k["shape"] = c if k["shape"] is None else k["shape"].union(c)
        k["z"].append(round(b["z"], 1))
        k["loop_d"].append(round(loop, 1))
        k["loop_mm"].append(round(L))
    for key, k in bands.items():
        out.append((key, k.pop("shape"), k))

    # the RJ11 cables (manifold3d solids: meshes.py takes their mesh as it is)
    import manifold3d as m3d
    for key, runs in p["cables"].items():
        pieces, lengths = [], {}
        for name, paths in runs.items():
            for i, path in enumerate(paths):
                s, L = tube_path(path)
                pieces.append(s)
                if i == 0:
                    lengths[name] = round(L)
        out.append((key, m3d.Manifold.batch_boolean(pieces, m3d.OpType.Add), dict(run_mm=lengths)))
    return out


def arm_z(mast_foot):
    """The cross arm bar's centre height for a mast whose foot is at mast_foot: the hub sits over the top tube's end."""
    return mast_foot + 2 * MAST_TUBE_L - MAST_JOIN + 10.0
