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
RAIN_ARM_L = 150.0         # ESTIMATED: the side-mount rain arm, mast axis to the gauge's centre
RAIN_CLAMP = (36.0, 36.0, 40.0)  # ESTIMATED: the rain arm's two-half clamp block round the tube
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


def build(p):
    """p (from build.py, assembly frame: mm, Z up, the pole's axis on Z at x = y = 0, the TX box and the shield on
    the -y side): pole_r, pole_top, mast_overlap, mast_clamps (two depths below the pole's top), rain_below (the
    rain arm's top this far under the cross arm's top), glands {name: [x, y, z]} (the outside end of each meter
    cable's PG-9 gland), drip (the drip loop's depth below a gland), and optionally ties: the shield bracket's two
    pole straps, dict(z=[two heights], circles=[(x, y, r)] (the saddle's rounded strap edges, which the loop wraps
    with the pole), w, t). Returns [(key, shape, info)].

    With ties, the two straps are one loop each round the saddle, the pole, the mast and the two RJ11 cables, which
    run down the pole's +x side from near its top, so the straps that bind the bracket also hold the cables and the
    mast (key "pole-straps": its shape comes from the shield's numbers, so it only goes on restricted pages).

    The two parts that move with the wind (meter-cups, the cup rotor; meter-vane, the vane) are their own meshes, and
    their info carries pivot = {at: [x, y, z], axis: [0, 0, 1]} in the assembly frame; their spindle housings are the
    static meter-cups-housing and meter-vane-housing. The rain gauge is one closed box here (no tipping bucket inside),
    so nothing in it moves."""
    r = p["pole_r"]
    my = r + MAST_D / 2                                    # the mast against the pole, behind it (+y)
    m0 = p["pole_top"] - p["mast_overlap"]                 # the mast's foot
    mast_top = m0 + 2 * MAST_TUBE_L - MAST_JOIN
    out = []
    lower = cyl(MAST_D, MAST_TUBE_L, (0, my, m0))
    upper = cyl(MAST_D, MAST_TUBE_L, (0, my, m0 + MAST_TUBE_L - MAST_JOIN)).union(
        cyl(MAST_D + 2.0, 8.0, (0, my, m0 + MAST_TUBE_L - MAST_JOIN)))       # the join, drawn as a small collar
    out.append(("meter-mast", lower.union(upper), dict(z=[round(m0, 1), round(mast_top, 1)], y=round(my, 2))))

    # the cross arm on top: a hub over the top tube, the bar along x
    za = mast_top + 10.0                                    # the bar's centre: the hub sits over the tube's end
    hx, hy, hz = HUB
    arm = block(-hx / 2, hx / 2, my - hy / 2, my + hy / 2, za - hz + ARM_H / 2, za + ARM_H / 2)
    arm = arm.union(block(-ARM_L / 2, ARM_L / 2, my - ARM_W / 2, my + ARM_W / 2, za - ARM_H / 2, za + ARM_H / 2))
    out.append(("meter-arm", arm, dict(z=round(za, 1))))
    # the two wind sensors: a static spindle housing each, and the part that moves, with its pivot (a vertical axis)
    for key, fn, x in (("meter-cups", anemometer, SENSOR_AT), ("meter-vane", vane, -SENSOR_AT)):
        housing, rotor, (px, py, pz) = fn(x, za)
        out.append((key + "-housing", housing.translate((0, my, 0)), dict(x=x)))
        out.append((key, rotor.translate((0, my, 0)),
                    dict(x=x, pivot=dict(at=[round(px, 3), round(py + my, 3), round(pz, 3)], axis=[0, 0, 1]))))

    # the rain arm, level, out along +y (away from the pole, the TX box and the shield) lower on the mast
    zr = za + ARM_H / 2 - p["rain_below"]                   # the rain arm's top face
    cx, cy, cz = RAIN_CLAMP
    rarm = block(-cx / 2, cx / 2, my - cy / 2, my + cy / 2, zr - cz, zr)
    rarm = rarm.union(block(-10.0, 10.0, my, my + RAIN_ARM_L + 20.0, zr - 12.0, zr))
    out.append(("meter-rain-arm", rarm, dict(z=round(zr, 1), reach=RAIN_ARM_L)))
    out.append(("meter-rain", rain_gauge(0, my + RAIN_ARM_L, zr), dict(z=round(zr, 1))))

    # the two RJ11 cables up the pole's +x side, side by side against it: WIND on +x, RAIN turned a little toward +y,
    # both on the +y side of the bracket saddle's back plane (y = 0 and up), clear of the TX box's back
    rc = CABLE_D / 2
    pc = r + rc + 0.5
    ca = 2 * math.asin((rc + 0.3) / pc)
    on_pole = {"WIND": (pc, 0.0), "RAIN": (pc * math.cos(ca), pc * math.sin(ca))}
    cable_circ = [(x, y, rc) for x, y in on_pole.values()]

    # the kit's two gear clamps: mast to pole (and the cables beside them); with the bracket's straps, any clamp
    # build.py dropped is one of those straps now
    circ = [(0, 0, r), (0, my, MAST_D / 2)] + cable_circ
    clamps, loops = None, []
    for d in p["mast_clamps"]:
        c, loop, _L = gear_clamp(circ, p["pole_top"] - d, (1, 0))
        clamps = c if clamps is None else clamps.union(c)
        loops.append(round(loop, 1))
    if clamps is not None:
        out.append(("meter-clamps", clamps, dict(loop_d=loops)))

    # the shield bracket's two pole straps: zip ties through the saddle's tunnels, round the pole, the mast and cables
    ties = p.get("ties")
    if ties:
        tcirc = [tuple(c) for c in ties["circles"]] + [(0, 0, r), (0, my, MAST_D / 2)] + cable_circ
        straps, lengths = None, []
        for z in ties["z"]:
            c, _d, L = gear_clamp(tcirc, z, (0, 1), w=ties["w"], t=ties["t"], head=TIE_HEAD)
            straps = c if straps is None else straps.union(c)
            lengths.append(round(L))
        out.append(("pole-straps", straps, dict(z=[round(z, 1) for z in ties["z"]], loop_mm=lengths)))

    # the RJ11 cables: from each meter down the mast and the pole to its gland, with a drip loop under the gland.
    # With the bracket's straps they step from the mast onto the pole near its top and run down through both straps.
    cables, runs = None, {}
    zpole = (p["pole_top"] - 10.0 if ties else
             p["pole_top"] - p["mast_overlap"] + 30.0)    # where the cables step from the mast onto the pole
    for name, dx in (("WIND", -1.0), ("RAIN", 1.0)):
        gx, gy, gz = p["glands"][name]
        off = dx * (rc + 0.6)
        px, py = on_pole[name]
        mx = MAST_D / 2 + rc + 0.5
        pts = [(gx, gy, gz), (gx, gy, gz - p["drip"]), (gx * 0.4, gy * 0.5, gz - p["drip"] + 20.0),
               (px, py, gz + 10.0), (px, py, zpole), (mx, my + off, zpole + 40.0)]
        if name == "WIND":
            pts += [(mx, my + off, za - ARM_H / 2 - 4.0), (-SENSOR_AT + 25.0, my, za - ARM_H / 2 - rc - 0.5),
                    (-SENSOR_AT, my, za - ARM_H / 2 - rc - 0.5)]        # into the vane's base, under the arm
            # the short cups-to-vane jumper under the arm
            jump = [(SENSOR_AT, my + ARM_W / 2 - rc, za - ARM_H / 2 - rc - 0.5),
                    (-SENSOR_AT + 10.0, my + ARM_W / 2 - rc, za - ARM_H / 2 - rc - 0.5)]
        else:
            pts += [(mx, my + off, zr - 16.0), (0, my + RAIN_ARM_L * 0.5, zr - 14.0),
                    (0, my + RAIN_ARM_L - GAUGE[1] / 2, zr - 14.0), (0, my + RAIN_ARM_L, zr + 5.0)]
        segs = [pts] + ([jump] if name == "WIND" else [])
        length = 0.0
        for path in segs:
            for a, b in zip(path, path[1:]):
                v = [b[i] - a[i] for i in range(3)]
                L = math.sqrt(sum(c * c for c in v))
                if L < 1e-6:
                    continue
                length += L if path is pts else 0.0
                s = cyl(CABLE_D, L, a, v).union(cq.Workplane("XY").sphere(rc).translate(b))
                cables = s if cables is None else cables.union(s)
        runs[name] = round(length)
    out.append(("meter-cables", cables, dict(run_mm=runs)))
    return out
