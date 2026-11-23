"""The three printed pod boxes (hardware/pods-r1/box/podbox.py): board fit, openings, lid fastening, UV window.

Needs CadQuery, so it skips in the plain .venv (CI). Run with the CAD venv from the repo root:
    .venv-cad/bin/python -m unittest tests.test_pods_box -v
Every check measures the built solids (OCC distances, point probes, segment intersections), not the numbers the module
used to build them.
"""
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"

try:
    import cadquery as cq
except ImportError:                                    # the plain .venv has no CadQuery
    cq = None

MIN = 2.0          # the brief's minimum clearance, mm
EPS = 1e-6


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def solid(b):
    return cq.Solid.makeBox(b.x1 - b.x0, b.y1 - b.y0, b.z1 - b.z0, cq.Vector(b.x0, b.y0, b.z0))


def angle(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)))))


def blocked_length(shape, a, b):
    """Length of the segment a-b that runs through the solid."""
    common = shape.intersect(cq.Edge.makeLine(cq.Vector(*a), cq.Vector(*b)))
    return sum(e.Length() for e in common.Edges())


@unittest.skipIf(cq is None, "CadQuery missing: run with .venv-cad/bin/python")
class PodBox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = load("pods_sources", PODS / "sources.py")
        cls.pods = load("pods", PODS / "layout" / "pods.py")
        cls.box = load("podbox", PODS / "box" / "podbox.py")
        cls.names = cls.pods.POD_NAMES
        cls.built = {n: (cls.box.body(n), cls.box.lid(n), cls.box.walls(n)) for n in cls.names}

    # ------------------------------------------------------------ helpers
    def _top_side(self, name):
        """Every part's box from the pod layout, plus the crimped plug: its body and plug_bend beyond the jack mouth."""
        S, Box = self.S, self.pods.Box
        p = self.pods.pod(name)
        boxes = [b for part in p.parts for b in part.boxes]
        jack = next(b for b in p.part("J1").boxes if "87180" in b.what)
        plug = next(b for b in p.part("J1").boxes if "RJ11 plug" in b.what)
        pw, ph, _pl, plen = S.val("plug_6p")
        xm, zm = (plug.x0 + plug.x1) / 2, (plug.z0 + plug.z1) / 2      # the plug's axis, as the layout has it
        mouth = jack.y0                                            # the mouth faces -y (the gland edge)
        boxes.append(Box(xm - pw / 2, mouth - plen - S.val("plug_bend"), xm + pw / 2, mouth, zm - ph / 2, zm + ph / 2,
                         "6P plug body + plug_bend", keepout=True))
        return boxes

    def _under_side(self):
        """The Perma-Proto itself and its copper side: solder tails and the bottom wires (two crossing at most)."""
        S, Box = self.S, self.pods.Box
        w, h = S.val("permaproto_q")
        t = S.val("permaproto_q_t")
        cs = max(S.val("tails"), 2 * S.val("wire24")[1])
        return [Box(0, 0, w, h, -t, 0, "Perma-Proto Quarter #1608"),
                Box(0, 0, w, h, -t - cs, -t, "copper side: tails and bottom wires", keepout=True)]

    # ------------------------------------------------------------ the brief's tests
    def test_board_fits(self):
        for n in self.names:
            body, lid, walls = self.built[n]
            ins = self.box.inside(n)
            with self.subTest(pod=n):
                for b in self._top_side(n) + self._under_side():
                    for lo, hi, a, c in ((b.x0, b.x1, ins.x0, ins.x1), (b.y0, b.y1, ins.y0, ins.y1),
                                         (b.z0, b.z1, ins.z0, ins.z1)):
                        self.assertGreaterEqual(lo - a, MIN - EPS, f"{n}: {b.what} too near the inside's low face")
                        self.assertGreaterEqual(c - hi, MIN - EPS, f"{n}: {b.what} too near the inside's high face")
                for b in self._top_side(n):
                    s = solid(b)
                    self.assertGreaterEqual(s.distance(body), MIN - EPS, f"{n}: {b.what} to the body")
                    self.assertGreaterEqual(s.distance(lid), MIN - EPS, f"{n}: {b.what} to the lid")
                for b in self._under_side():                        # the standoffs carry the board: test the walls
                    self.assertGreaterEqual(solid(b).distance(walls), MIN - EPS, f"{n}: {b.what} to the walls")
                # the lid closes over the tallest part with 2.0 to spare
                tallest = max(b.z1 for b in self._top_side(n))
                lid_in = lid.BoundingBox().zmin
                self.assertGreaterEqual(lid_in - tallest, MIN - EPS, n)
                # the board's standoffs touch only the mount_keep ring round each mounting hole
                body_bb = body.BoundingBox()
                t = self.S.val("permaproto_q_t")
                keep, pilot = self.S.val("mount_keep"), self.S.val("pod_pilot_m3")
                for (mx, my, _d) in self.box.board_holes():
                    for k in range(8):
                        a = k * math.pi / 4
                        ri, ro = (keep + pilot / 2) / 2, keep + 0.05
                        self.assertTrue(body.isInside(cq.Vector(mx + ri * math.cos(a), my + ri * math.sin(a), -t - 0.05)),
                                        f"{n}: no standoff under hole ({mx}, {my})")
                        self.assertFalse(body.isInside(cq.Vector(mx + ro * math.cos(a), my + ro * math.sin(a), -t - 0.05)),
                                         f"{n}: standoff wider than mount_keep")
                    self.assertFalse(body.isInside(cq.Vector(mx, my, -t - 3.0)), f"{n}: no pilot hole")
                self.assertGreater(body_bb.zlen, 0)
                # each gland's locknut and thread inside the box clear the plug body, the jack and the lid
                jack = next(b for b in self.pods.pod(n).part("J1").boxes if "87180" in b.what)
                for kind, _c, _axis in self.box.openings(n):
                    if kind not in ("gland", "lead_gland"):
                        continue
                    nut = self.box.gland_nut(n, kind)
                    for b in (self._plug_body_only(n), jack):
                        self.assertGreater(nut.distance(solid(b)), 0.5, f"{n} {kind} nut to {b.what}")
                    self.assertGreater(nut.distance(lid), 0.2, f"{n} {kind} nut to the lid")
                    # and nothing in the body (a wall, a boss, the baffle) stands within 0.5 of the nut's side
                    (c, axis), = [(c, a) for k, c, a in self.box.openings(n) if k == kind]
                    nb = nut.BoundingBox()
                    r = max(nb.xlen, nb.ylen, nb.zlen) / 2 if axis[2] else max(nb.xlen, nb.zlen) / 2
                    r += 0.5
                    mid = tuple(ci - (self.box.wall_t(n, kind) + 1.5) * ai for ci, ai in zip(c, axis, strict=True))
                    for k in range(24):
                        a = k * math.pi / 12
                        if axis[2]:
                            pt = (mid[0] + r * math.cos(a), mid[1] + r * math.sin(a), mid[2])
                        else:
                            pt = (mid[0] + r * math.cos(a), mid[1], mid[2] + r * math.sin(a))
                        self.assertFalse(body.isInside(cq.Vector(*pt)), f"{n} {kind}: body within 0.5 of the nut at {pt}")

    def _plug_body_only(self, name):
        S, Box = self.S, self.pods.Box
        jack = next(b for b in self.pods.pod(name).part("J1").boxes if "87180" in b.what)
        plug = next(b for b in self.pods.pod(name).part("J1").boxes if "RJ11 plug" in b.what)
        pw, ph, _pl, plen = S.val("plug_6p")
        xm, zm = (plug.x0 + plug.x1) / 2, (plug.z0 + plug.z1) / 2
        return Box(xm - pw / 2, jack.y0 - plen, xm + pw / 2, jack.y0, zm - ph / 2, zm + ph / 2, "plug body only")

    def test_openings_face_down(self):
        for n in self.names:
            up = self.box.up(n)
            down = tuple(-u for u in up)
            ops = self.box.openings(n)
            kinds = [k for k, _c, _a in ops]
            with self.subTest(pod=n):
                self.assertEqual(kinds.count("gland"), 1, n)
                for kind, _c, axis in ops:
                    if kind == "gland" and n == "UV":                 # the crown's port gland: level, straight out
                        self.assertAlmostEqual(angle(axis, down), 90.0, places=6)
                        ax, ay = self.box.dims("UV")["axis"]
                        out = (_c[0] - ax, _c[1] - ay)
                        self.assertLess(abs(out[0] * axis[1] - out[1] * axis[0]), 1e-6, "UV gland not radial")
                        self.assertGreater(out[0] * axis[0] + out[1] * axis[1], 0)
                    elif kind in ("gland", "lead_gland", "vent"):
                        self.assertLessEqual(angle(axis, down), 10.0, f"{n} {kind}")
                    if kind == "window":
                        self.assertLessEqual(angle(axis, up), 5.0, f"{n} window")
                self.assertEqual("vent" in kinds, n == "BARO")
                self.assertEqual("window" in kinds, n == "UV")
                self.assertEqual("lead_gland" in kinds, n == "TH")
                # each opening really is a hole: a short probe along its axis through the wall meets no material
                body, lid, _w = self.built[n]
                for kind, c, axis in ops:
                    shape = lid if kind == "window" else body
                    a = tuple(ci + 1.0 * ai for ci, ai in zip(c, axis, strict=True))           # 1 mm outside
                    depth = self.box.wall_t(n, kind) + 0.5                        # through the wall, 0.5 beyond
                    b = tuple(ci - depth * ai for ci, ai in zip(c, axis, strict=True))
                    self.assertLess(blocked_length(shape, a, b), 1e-6, f"{n} {kind} is not open")

    def test_baro_vent_baffled(self):
        """No straight line from the vent's outside opening to the BMP581 board; without the baffle there is one."""
        n = "BARO"
        body = self.built[n][0]
        open_body = self.box.body(n, baffle=False)
        (_k, c, axis), = [o for o in self.box.openings(n) if o[0] == "vent"]
        r = self.box.vent_d() / 2 * 0.9
        u = (1.0, 0.0, 0.0)
        v = tuple(axis[(i + 1) % 3] * u[(i + 2) % 3] - axis[(i + 2) % 3] * u[(i + 1) % 3] for i in range(3))
        starts = [tuple(ci + 0.05 * ai for ci, ai in zip(c, axis, strict=True))]
        for k in range(8):
            a = k * math.pi / 4
            starts.append(tuple(ci + 0.05 * ai + r * (math.cos(a) * ui + math.sin(a) * vi)
                                for ci, ai, ui, vi in zip(c, axis, u, v, strict=True)))
        u2 = self.pods.pod(n).part("U2")
        pcb = next(b for b in u2.boxes if "PCB" in b.what)
        ends = [(x, y, z) for x in (pcb.x0, pcb.x1) for y in (pcb.y0, pcb.y1) for z in (pcb.z0, pcb.z1)]
        ends.append(((pcb.x0 + pcb.x1) / 2, (pcb.y0 + pcb.y1) / 2, pcb.z1))
        sight = 0
        for a in starts:
            for b in ends:
                self.assertGreater(blocked_length(body, a, b), 0.1, f"line of sight {a} -> {b}")
                if blocked_length(open_body, a, b) < 1e-6:
                    sight += 1
        self.assertGreater(sight, 0, "the check is vacuous: even without the baffle nothing sees the sensor")
        # the air path stays open: the baffle is clear of the side walls and the lid
        self.assertGreaterEqual(self.box.baffle_gaps(n), 2.0)

    def test_eptfe_seats(self):
        """Both adhesive ePTFE vents (BARO's vent, the UV crown's breather) sit on a seat at least Gore's target area
        across and at least the vent's thickness deep, measured on the built bodies."""
        S = self.S
        vd, vt = S.val("baro_eptfe")
        _sd, _st, margin = S.val("eptfe_seat")
        d = self.box.dims("BARO")
        body = self.built["BARO"][0]
        (_k, (vx, vy, vz), _a), = [o for o in self.box.openings("BARO") if o[0] == "vent"]
        y_in = d["y0"]                                                   # the bottom wall's inner face
        r = (vd + margin) / 2 - 0.05
        for k in range(8):                                               # the seat's floor, round its edge
            a = k * math.pi / 4
            p = cq.Vector(vx + r * math.cos(a), y_in - vt + 0.01, vz + r * math.sin(a))
            self.assertFalse(body.isInside(p), f"BARO seat too small at {k * 45} deg")
        self.assertTrue(body.isInside(cq.Vector(vx + r, y_in - d["seat"][1] - 0.2, vz)), "BARO seat runs through")

    def test_uv_breather(self):
        """The crown's breather: a level hole through the drum wall, behind a flat ePTFE seat inside, across the crown
        from the gland, under the ledge, and the drum wall left round it at least WALL thick."""
        S, d = self.S, self.box.dims("UV")
        body = self.built["UV"][0]
        (_k, c, u), = [o for o in self.box.openings("UV") if o[0] == "breather"]
        self.assertAlmostEqual(u[2], 0.0)
        (_g, gc, ga), = [o for o in self.box.openings("UV") if o[0] == "gland"]
        self.assertGreater(angle(u, ga), 150.0, "the breather is not across from the gland")
        vd, vt = S.val("baro_eptfe")
        margin = S.val("eptfe_seat")[2]
        b = d["breather"]
        r_flat = b["r_flat"]
        self.assertGreaterEqual(d["r_out"] - r_flat, self.box.WALL, "too little drum wall behind the seat")
        zb = c[2]
        half = (vd + margin) / 2
        self.assertGreater(zb - half, d["z_bi"], "the seat runs into the floor")
        self.assertLess(zb + half, d["z_ledge"], "the seat runs over the ledge")
        # the seat's floor is flat: open just inside r_flat across Gore's target area, plastic just beyond it
        v = (-u[1], u[0], 0.0)
        for s in (-1.0, 1.0):
            for w in ((s * (half - 0.05), 0.0), (0.0, s * (half - 0.05))):
                q = [d["axis"][i] + (r_flat - vt + 0.01) * u[i] + w[0] * v[i] for i in range(2)]
                self.assertFalse(body.isInside(cq.Vector(q[0], q[1], zb + w[1])), "the breather seat is not flat")
                q = [d["axis"][i] + (r_flat + 0.3) * u[i] + w[0] * v[i] for i in range(2)]
                self.assertTrue(body.isInside(cq.Vector(q[0], q[1], zb + w[1])), "the seat runs into the wall")
        # the hole: open all the way out, and narrower than the vent's effective 5.5
        a = tuple(d["axis"][i] + (d["r_in"] - 0.5) * u[i] for i in range(2)) + (zb,)
        e = tuple(c[i] + 1.0 * u[i] for i in range(3))
        self.assertLess(blocked_length(body, a, e), 1e-6, "the breather hole is blocked")
        self.assertLessEqual(b["d"], 5.5)

    def test_lid_not_glued(self):
        S = self.S
        cord = S.val("pod_oring")
        bore_d, bore_depth = S.val("pod_insert_bore")
        for n in self.names:
            if n == "UV":
                continue                                        # the crown: test_uv_crown_seal_and_bayonet
            body, lid, _w = self.built[n]
            g = self.box.groove(n)
            with self.subTest(pod=n):
                self.assertAlmostEqual(g["width"], round(1.35 * cord, 2))
                self.assertAlmostEqual(g["depth"], round(0.75 * cord, 2))
                self.assertGreater(g["depth"], 0)
                self.assertLess(g["depth"], cord)                     # the cord stands proud: it is squeezed
                # the groove is cut into the lid's inner face along its centreline; the lid is solid beside it
                for (x, y) in g["probes"]:
                    z_in = lid.BoundingBox().zmin
                    self.assertFalse(lid.isInside(cq.Vector(x, y, z_in + g["depth"] / 2)), f"{n}: no groove at {x, y}")
                    self.assertTrue(lid.isInside(cq.Vector(x, y, z_in + g["depth"] + 0.3)), f"{n}: lid holed at {x, y}")
                # the groove sits over the body's rim
                rim_z = body.BoundingBox().zmax
                for (x, y) in g["probes"]:
                    self.assertTrue(body.isInside(cq.Vector(x, y, rim_z - 0.3)), f"{n}: groove off the rim at {x, y}")
                scr = self.box.screws(n)
                self.assertGreaterEqual(len(scr), 4)
                for s in scr:
                    x, y = s["xy"]
                    self.assertEqual((s["bore_d"], s["bore_depth"]), (bore_d, bore_depth))
                    top = body.BoundingBox().zmax
                    self.assertFalse(body.isInside(cq.Vector(x, y, top - bore_depth / 2)), f"{n}: no insert bore")
                    self.assertFalse(body.isInside(cq.Vector(x + bore_d / 2 - 0.1, y, top - bore_depth + 0.2)))
                    self.assertTrue(body.isInside(cq.Vector(x + bore_d / 2 + 0.3, y, top - bore_depth / 2)),
                                    f"{n}: insert bore wider than {bore_d}")
                    self.assertTrue(body.isInside(cq.Vector(x, y, top - bore_depth - 0.3)), f"{n}: bore through")
                    zl = lid.BoundingBox().center.z
                    self.assertFalse(lid.isInside(cq.Vector(x, y, zl)), f"{n}: no screw hole in the lid")
                    # the screw passes outside the O-ring
                    self.assertGreater(min(math.hypot(x - px, y - py) for px, py in g["path"]),
                                       bore_d / 2 + g["width"] / 2 + 0.5, f"{n}: insert breaks into the groove")

    def test_uv_crown_seal_and_bayonet(self):
        """The crown's lid: a radial O-ring in a groove round the body's spigot (squeezed about 25 %), held down by a
        bayonet (lugs in the spigot's channels); no glue, no screws; the lid and the body never overlap."""
        cord = self.S.val("pod_oring")
        d = self.box.dims("UV")
        body, lid, _w = self.built["UV"]
        g = self.box.groove("UV")
        self.assertTrue(g["radial"])
        self.assertAlmostEqual(g["width"], round(1.35 * cord, 2))
        self.assertGreater(g["squeeze"], 0.2)
        self.assertLess(g["squeeze"], 0.3)
        for x, y in g["probes"]:
            self.assertFalse(body.isInside(cq.Vector(x, y, g["z"])), f"no groove at {x, y}")
        ax, ay = d["axis"]
        for a in (0.3, 1.9, 3.5, 5.1):
            r = d["r_sp"] - g["depth"] - 0.4
            self.assertTrue(body.isInside(cq.Vector(ax + r * math.cos(a), ay + r * math.sin(a), g["z"])), "spigot holed")
            rb = d["r_sp"] + self.box.CROWN_C + 0.3                     # the lid's skirt over the groove
            self.assertTrue(lid.isInside(cq.Vector(ax + rb * math.cos(a), ay + rb * math.sin(a), g["z"])), "no skirt")
        self.assertEqual(self.box.screws("UV"), [])
        self.assertLess(lid.intersect(body).Volume(), 1e-3)            # closed and locked, nothing overlaps
        # each bayonet lug is in its channel: the lid has material there, the body has none
        lw, lh, ld = self.box.CROWN_LUG
        for a in self.box._bayonet_angles(d):
            t = math.radians(a + self.box.CROWN_TURN)
            r = d["r_sp"] + self.box.CROWN_C - ld / 2
            p = cq.Vector(ax + r * math.cos(t), ay + r * math.sin(t), d["z_joint"] - self.box.CROWN_LUG_Z)
            self.assertTrue(lid.isInside(p), f"no lug at {a}")
            self.assertFalse(body.isInside(p), f"lug at {a} not in a channel")
        # the lid's skirt is flush with the drum, and the lid lands on the spigot's top (the axial stop)
        self.assertAlmostEqual(lid.BoundingBox().xlen, body.BoundingBox().ylen, delta=0.5)

    def test_uv_window_recorded(self):
        S = self.S
        self.assertIn("uv_window", S.D)
        material, dw, t = S.val("uv_window")
        self.assertTrue(isinstance(material, str) and material.strip())
        self.assertGreater(dw, 0)
        self.assertGreater(t, 0)
        # the window is centred on the crown's axis, flush in the apex flat; the LTR390 sits under its aperture
        d = self.box.dims("UV")
        (_k, c, _axis), = [o for o in self.box.openings("UV") if o[0] == "window"]
        lid = self.built["UV"][1]
        self.assertAlmostEqual(c[2], lid.BoundingBox().zmax, places=6)
        self.assertAlmostEqual(c[0], d["axis"][0], places=6)
        self.assertAlmostEqual(c[1], d["axis"][1], places=6)
        self.assertFalse(lid.isInside(cq.Vector(c[0], c[1], c[2] - t / 2)), "no window recess")
        self.assertFalse(lid.isInside(cq.Vector(c[0], c[1], d["ltr"]["z"] + 2.0)), "the aperture is blocked")
        L = d["ltr"]
        lw, lh = L["size"]
        board = cq.Solid.makeBox(lw, lh, 1.6, cq.Vector(L["c"][0] - lw / 2, L["c"][1] - lh / 2, L["z"] - 1.6))
        self.assertLess(board.intersect(lid).Volume(), 1e-3)
        for x, y in L["holes"]:                                          # M2.5 pilots in bosses over the corner holes
            self.assertTrue(lid.isInside(cq.Vector(x + 1.6, y, L["z"] + 1.0)), "no LTR390 boss")
            self.assertFalse(lid.isInside(cq.Vector(x, y, L["z"] + 1.0)), "no pilot")
        # the LTR390's chip is under the window's centre
        sx, sy = S.val("ltr390_sensor")
        self.assertAlmostEqual(L["c"][0] - lw / 2 + sx, c[0], places=6)
        self.assertAlmostEqual(L["c"][1] - lh / 2 + sy, c[1], places=6)

    # ------------------------------------------------------------ mounting and the written files
    def test_mount_face(self):
        for n in self.names:
            (origin, normal), holes = self.box.mount_face(n)
            body = self.built[n][0]
            with self.subTest(pod=n):
                self.assertGreaterEqual(len(holes), 2)
                bb = body.BoundingBox()
                self.assertEqual(normal, (0.0, 0.0, -1.0))
                self.assertAlmostEqual(origin[2], bb.zmin, places=6)
                d, depth = self.S.val("pod_insert_bore")
                for x, y in holes:
                    self.assertFalse(body.isInside(cq.Vector(x, y, bb.zmin + depth / 2)), f"{n}: no mount insert bore")
                    self.assertTrue(body.isInside(cq.Vector(x, y, bb.zmin + depth + 0.3)), f"{n}: mount bore through")

    def _breakthroughs(self, name, body):
        """[(kind, x, y, mm3)] of every M3 insert bore (mount bores from the back, lid bores from the rim) that reaches
        the sealed space: the largest solid of the box's inside() less the body. A blind bore's own void inside a boss
        is a separate solid, so only a bore that breaks through overlaps the cavity."""
        d = self.box.dims(name)
        bd, bdepth = self.box.S.val("pod_insert_bore")
        cav = max(solid(self.box.inside(name)).cut(body).Solids(), key=lambda v: v.Volume())
        bores = ([("mount", x, y, d["z_bo"]) for x, y in self.box.mount_face(name).holes]
                 + [("lid", x, y, d["z_rim"] - bdepth) for x, y in d["lugs"]])
        out = []
        for kind, x, y, z0 in bores:
            v = cq.Solid.makeCylinder(bd / 2, bdepth, cq.Vector(x, y, z0)).intersect(cav).Volume()
            if v > 1e-3:
                out.append((kind, round(x, 2), round(y, 2), round(v, 3)))
        return out

    def test_insert_bores_blind(self):
        """No mount or lid insert bore opens into the sealed box, on every pod."""
        for n in self.names:
            with self.subTest(pod=n):
                self.assertEqual(self._breakthroughs(n, self.built[n][0]), [])

    def test_insert_bores_blind_with_a_longer_insert(self):
        """Mutation proof: a 9.0 mm insert (bore 10.0) still leaves the UV floor bosses blind, because the boss is the
        bore plus MOUNT_BOSS_CAP; the old fixed 7.7 mm boss would let that bore through (so the check has teeth)."""
        box, D = self.box, self.box.S.D
        keep, keep_fn = D["pod_insert_bore"], box.mount_boss_depth

        def rebuild():
            for f in (box.dims, box._build, box.lid):
                f.cache_clear()
        try:
            D["pod_insert_bore"] = ((keep[0][0], 10.0),) + tuple(keep[1:])
            rebuild()
            self.assertAlmostEqual(box.dims("UV")["boss_depth"], 11.0)
            self.assertEqual(self._breakthroughs("UV", box.body("UV")), [])
            box.mount_boss_depth = lambda: 7.7                     # the old hard-coded height
            rebuild()
            leaks = self._breakthroughs("UV", box.body("UV"))
            self.assertEqual(sorted(k for k, *_ in leaks), ["mount"] * len(box.dims("UV")["floor_bosses"]), leaks)
        finally:
            D["pod_insert_bore"], box.mount_boss_depth = keep, keep_fn
            rebuild()

    def test_uv_crown_mount(self):
        """The crown stands on the cap's flat top (r 38): four floor bosses within CROWN_BOSS_R of its axis, nothing to
        keep clear on the mount face (the port gland is in the drum's wall), the gland's spot face under the lid."""
        d = self.box.dims("UV")
        mf = self.box.mount_face("UV")
        self.assertEqual(mf.keepouts, [])
        self.assertEqual(len(mf.holes), 4)
        ax, ay = d["axis"]
        for x, y in mf.holes:
            self.assertAlmostEqual(math.hypot(x - ax, y - ay), self.box.CROWN_BOSS_R, places=6)
        self.assertLessEqual(self.box.CROWN_BOSS_R + self.S.val("pod_mount_screw")[2] / 2 + 1.0, 38.0)
        (_k, gc, _a), = [o for o in self.box.openings("UV") if o[0] == "gland"]
        self.assertLessEqual(gc[2] + self.box.CROWN_GLAND_FACE / 2, d["z_ledge"])
        for n in ("TH", "BARO"):
            self.assertEqual(self.box.mount_face(n).keepouts, [])

    def test_uv_ltr390_clears_lid(self):
        """Every modelled LTR390 part (Session Q's ltr_in_lid: the board, its copper, chips, passives, LED and the two
        factory STEMMA QT sockets) misses the lid. The two M2.5 screws only cut into their pilots: inside the thread's
        radius round each hole and no higher than the pilot's top."""
        sheets = str(PODS / "sheets")
        if sheets not in sys.path:
            sys.path.insert(0, sheets)
        import scenes_q                 # noqa: E402  (it puts the TX sheets' r3d on the path)
        import r3d
        lid = self.built["UV"][1]
        L = self.box.dims("UV")["ltr"]
        s = r3d.Scene()
        scenes_q.ltr_in_lid(s, lead=False, screws=True)
        names = [p[0] for p in s.parts]
        self.assertIn("ltr_qt", names)
        thread = self.S.val("ltr_screw")[0] / 2
        for nm, shp, *_ in s.parts:
            shp = shp if isinstance(shp, cq.Shape) else cq.Shape.cast(shp)
            common = lid.intersect(shp)
            if nm.startswith("m25_"):
                k = int(nm[4:])
                x, y = L["holes"][k]
                bb = common.BoundingBox()
                self.assertLessEqual(bb.zmax, L["pilot_top"] + EPS, f"{nm} runs past its pilot")
                for v in common.Vertices():
                    self.assertLessEqual(math.hypot(v.X - x, v.Y - y), thread + 1e-3, f"{nm} cuts beyond its thread")
            else:
                self.assertLess(common.Volume(), 1e-6, f"{nm} overlaps the lid")

    def test_uv_crown_walls(self):
        """Printed plastic at least WALL_MIN: over and beside the LTR390's M2.5 pilots (the dome's outer face and the
        window recess), and behind the bayonet's channels and entry slots in the spigot. The detent bumps catch each
        lug by CROWN_DETENT's interference, and the locked lug clears its bump."""
        WALL_MIN = 1.2
        body, lid, _w = self.built["UV"]
        d = self.box.dims("UV")
        L = d["ltr"]
        pr = self.S.val("pod_pilot_m25") / 2
        for x, y in L["holes"]:
            # a cylinder WALL_MIN round the pilot and WALL_MIN over its top: all lid plastic but the pilot itself
            # (it starts on the boss's face, where the pilot opens)
            z0 = L["z"] + self.box.LTR_CU + 0.01
            shell = cq.Solid.makeCylinder(pr + WALL_MIN, L["pilot_top"] + WALL_MIN - z0, cq.Vector(x, y, z0))
            pilot = cq.Solid.makeCylinder(pr, L["pilot_top"] - z0, cq.Vector(x, y, z0))
            self.assertLess(shell.cut(pilot).cut(lid).Volume(), 1e-3, f"thin plastic round the pilot at {x, y}")
            self.assertFalse(lid.isInside(cq.Vector(x, y, L["pilot_top"] - 0.2)), "no pilot")
        ax, ay = d["axis"]
        lw, lh, ld = self.box.CROWN_LUG
        zl = d["z_joint"] - self.box.CROWN_LUG_Z
        for a in self.box._bayonet_angles(d):
            for ang, z in ((a, zl), (a, d["z_joint"] - 0.5), (a + self.box.CROWN_TURN / 2, zl)):   # slot, channel
                t = math.radians(ang)
                rs = [r / 50 for r in range(int(d["r_in"] * 50) - 50, int(d["r_sp"] * 50) + 50)
                      if body.isInside(cq.Vector(ax + r / 50 * math.cos(t), ay + r / 50 * math.sin(t), z))]
                self.assertGreaterEqual(max(rs) - min(rs) + 0.02, WALL_MIN, f"thin spigot at {ang:.1f} deg, z {z:.2f}")
                self.assertLess(max(rs), d["r_sp"] - ld, "no channel")
        # the detents: each bump reaches into the lug's path by the interference, and sits clear of the locked lug
        r_lug = d["r_sp"] + self.box.CROWN_C - ld                    # the lug's inner face
        for x, y in self.box.detents(d):
            reach = math.hypot(x - ax, y - ay) + self.box.CROWN_DETENT[0]
            self.assertAlmostEqual(reach - r_lug, self.box.CROWN_DETENT[1], places=6)
            self.assertTrue(body.isInside(cq.Vector(x, y, zl)), "no detent bump")
        self.assertLess(lid.intersect(body).Volume(), 1e-3)

    def test_stls_written(self):
        out = PODS / "box" / "stl"
        for n in self.names:
            for part in ("body", "lid"):
                p = out / f"pod-{n.lower()}-{part}.stl"
                self.assertTrue(p.exists(), p)
                self.assertGreater(p.stat().st_size, 1000, p)


if __name__ == "__main__":
    unittest.main()
