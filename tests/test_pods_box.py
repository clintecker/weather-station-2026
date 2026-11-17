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
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))))


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
                    if kind in ("gland", "lead_gland", "vent"):
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
                    a = tuple(ci + 1.0 * ai for ci, ai in zip(c, axis))           # 1 mm outside
                    depth = self.box.wall_t(n, kind) + 0.5                        # through the wall, 0.5 beyond
                    b = tuple(ci - depth * ai for ci, ai in zip(c, axis))
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
        starts = [tuple(ci + 0.05 * ai for ci, ai in zip(c, axis))]
        for k in range(8):
            a = k * math.pi / 4
            starts.append(tuple(ci + 0.05 * ai + r * (math.cos(a) * ui + math.sin(a) * vi)
                                for ci, ai, ui, vi in zip(c, axis, u, v)))
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

    def test_lid_not_glued(self):
        S = self.S
        cord = S.val("pod_oring")
        bore_d, bore_depth = S.val("pod_insert_bore")
        for n in self.names:
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

    def test_uv_window_recorded(self):
        S = self.S
        self.assertIn("uv_window", S.D)
        material, d, t = S.val("uv_window")
        self.assertTrue(isinstance(material, str) and material.strip())
        self.assertGreater(d, 0)
        self.assertGreater(t, 0)
        # the window sits over the LTR390's sensor, flush in the UV lid's top face
        (_k, c, _axis), = [o for o in self.box.openings("UV") if o[0] == "window"]
        lid = self.built["UV"][1]
        self.assertAlmostEqual(c[2], lid.BoundingBox().zmax, places=6)
        u2 = self.pods.pod("UV").part("U2")
        sx, sy = S.val("ltr390_sensor")
        self.assertAlmostEqual(c[0], u2.origin[0] + sx, places=6)
        self.assertAlmostEqual(c[1], u2.origin[1] + sy, places=6)
        self.assertFalse(lid.isInside(cq.Vector(c[0], c[1], c[2] - t / 2)), "no window recess")

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

    def test_stls_written(self):
        out = PODS / "box" / "stl"
        for n in self.names:
            for part in ("body", "lid"):
                p = out / f"pod-{n.lower()}-{part}.stl"
                self.assertTrue(p.exists(), p)
                self.assertGreater(p.stat().st_size, 1000, p)


if __name__ == "__main__":
    unittest.main()
