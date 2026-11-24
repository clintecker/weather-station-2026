"""The assembled radiation shield (hardware/pods-r1/shield/assemble.py): placements from the meshes' mating features,
the Ø40 core through the plate stack, and the SHT45 #6174 fit on the stand's inner face. And the remixed arm's pole
interface (hardware/pods-r1/shield/remix.py): the saddle on a 1 in pole and the two strap tunnels (ArmPoleStraps).

The 3MF stays outside git (sources.shield_3mf: local path + sha256), so these tests skip when it is absent (CI) or when
numpy is missing (the plain .venv). Run with the CAD venv: .venv-cad/bin/python -m unittest tests.test_pods_shield -v
"""
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"

try:
    import numpy as np
except ImportError:                                    # the plain .venv has no numpy
    np = None


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@unittest.skipIf(np is None, "numpy missing: run with .venv-cad/bin/python")
class ShieldMath(unittest.TestCase):
    """The slicing helpers on a synthetic mesh: no 3MF needed."""

    @classmethod
    def setUpClass(cls):
        cls.m = load("pods_shield_math", PODS / "shield" / "assemble.py")

    def test_section_and_circle_fit(self):
        t = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        ring = np.c_[3 + 2 * np.cos(t), -1 + 2 * np.sin(t)]
        n = len(ring)
        v = np.r_[np.c_[ring, np.zeros(n)], np.c_[ring, np.ones(n) * 5]]      # a Ø4 tube, z 0..5
        f = []
        for i in range(n):
            j = (i + 1) % n
            f += [[i, j, n + j], [i, n + j, n + i]]
        segs = self.m.section_z(v, np.array(f), 2.5)
        loops = self.m.loops(segs)
        self.assertEqual(len(loops), 1)
        cx, cy, r, res = self.m.fit_circle(loops[0])
        self.assertAlmostEqual(cx, 3, 3)
        self.assertAlmostEqual(cy, -1, 3)
        self.assertAlmostEqual(r, 2, 2)
        self.assertLess(res, 0.01)
        self.assertEqual(len(self.m.section_z(v, np.array(f), 6.0)), 0)

    def test_wrong_hash_is_refused(self):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.3mf"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("3D/3dmodel.model", "<model/>")
            with self.assertRaises(RuntimeError):
                self.m.open_3mf(p)


@unittest.skipIf(np is None, "numpy missing: run with .venv-cad/bin/python")
class ShieldAssembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load("pods_shield", PODS / "shield" / "assemble.py")
        path = cls.m.S.shield_path()
        if not path.exists():
            raise unittest.SkipTest(f"shield 3MF not present at {path} (kept outside git; sources.shield_3mf)")
        cls.mates = cls.m.mates()

    def test_mating_features(self):
        names = [x["mate"] for x in self.mates]
        # the chain: cup -> stand foot -> plates 1..6 -> cap, then the cup's foot in the arm
        self.assertEqual(sum(n.startswith("plate ") and " on plate " in n for n in names), 5)             # plates 2..6 each on the one below
        for want in ("stand foot on cup", "plate 1 on stand foot", "cap on plate 6", "cup foot in arm"):
            self.assertIn(want, names)
        for x in self.mates:
            self.assertLessEqual(x["lateral"], 0.3, x)          # axes / holes line up within 0.3 mm
            self.assertLessEqual(abs(x["axial"]), 0.3, x)       # faces touch within 0.3 mm
            self.assertGreaterEqual(x.get("clearance", 0.0), 0.0, x)   # nothing is an interference fit
        pocket = next(x for x in self.mates if x["mate"] == "cup foot in arm")
        self.assertEqual(pocket["holes"], 2)

    def test_mating_features_measured_on_placed_meshes(self):
        """Facts the placement does not set, re-measured on the assembled vertices."""
        ind = self.m.independent_checks()
        for oid, radii in ind["axis_radius"].items():                   # every bore on the same Ø50 circle
            for r in radii:
                self.assertAlmostEqual(r, 25.0, delta=0.05, msg=oid)
        for name, err in ind["lateral"]:                                 # per bore, not per centroid
            self.assertLessEqual(err, 0.3, name)
        post = ind["post_length"]
        self.assertAlmostEqual(post[0], 15.0, delta=0.05)
        for p in post:
            self.assertAlmostEqual(p, post[0], delta=0.05)
        for p in ind["pitch"]:                                           # measured plate spacing = the post length
            self.assertAlmostEqual(p, post[0], delta=0.3)
        self.assertLessEqual(abs(ind["radial"]), 0.3)                    # foot lobe vs post tube radius
        for name, c in ind["fits"]:                                      # real fits: free, but by less than 0.5 mm a side
            self.assertGreater(c, 0.0, name)
            self.assertLessEqual(c, 0.5, name)
        for pair, n in ind["clash"].items():
            self.assertEqual(n, 0, pair)

    def test_clash_check_can_fail(self):
        """The overlap test sees a misplaced part: plate 2 pushed 5 mm down into plate 1 must clash."""
        a = self.m.assembled()
        v, f = a["object_79.2"]
        self.assertGreater(self.m.clash(a["object_79.1"], (v - [0, 0, 5.0], f)), 0)
        self.assertEqual(self.m.clash(a["object_79.1"], a["object_79.2"]), 0)

    def test_core_clear(self):
        lo, hi = self.m.stack_span()
        self.assertGreater(hi - lo, 85.0)                        # six plates on 15 mm posts
        for z in np.linspace(lo, hi, 91):
            self.assertGreaterEqual(self.m.core_clear(float(z)), 20.0 - 1e-6, z)

    def test_sht45_fits(self):
        fit = self.m.sht45_fit()
        self.assertGreaterEqual(fit, 5.0, fit)
        origin, normal, extent = self.m.stand_face()
        self.assertAlmostEqual(float(np.hypot(*normal[:2])), 1.0, 6)
        self.assertGreaterEqual(extent[1], self.m.S.val("sht45")[0])             # the strip is tall enough for the board's long side

    def test_assembled_ids(self):
        a = self.m.assembled()
        self.assertEqual(set(a), {"object_67", "object_68", "object_70", "object_72"}
                         | {f"object_79.{i}" for i in range(1, 7)})
        for oid, (v, f) in a.items():
            self.assertEqual(v.shape[1], 3, oid)
            self.assertLess(int(f.max()), len(v), oid)


try:
    import cadquery  # noqa: F401
    import manifold3d as mf
except ImportError:                                    # the plain .venv has neither
    mf = None


@unittest.skipIf(np is None or mf is None, "numpy / CadQuery / manifold3d missing: run with .venv-cad/bin/python")
class ArmPoleStraps(unittest.TestCase):
    """The remixed arm is strapped to the pole (Clint, 2026-11-24): a V saddle on its back seats the pole, and two strap
    tunnels across the saddle take a heavy zip tie or a 1/2 in hose-clamp band round pole and bracket. Measured on the
    remixed solid, not on the numbers remix.py built it from."""

    SLOT_MIN = (14.0, 3.5)      # the brief: each strap tunnel at least 14 (strap width) x 3.5 (strap thickness) clear
    WALL = 1.2                  # the project's thinnest wall, round every tunnel

    @classmethod
    def setUpClass(cls):
        cls.r = load("pods_remix_pole", PODS / "shield" / "remix.py")
        if not cls.r.S.shield_path().exists():
            raise unittest.SkipTest("shield 3MF not present (kept outside git; sources.shield_3mf)")
        cls.arm = cls.r.arm_remixed()
        cls.u = cls.r.upright()

    def box(self, x0, x1, y0, y1, z0, z1):
        return mf.Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))

    def test_slot_opening(self):
        r = self.r
        self.assertEqual(len(r.STRAP_SLOT_Z), 2)
        self.assertAlmostEqual(r.STRAP_SLOT_PITCH, r.STRAP_SLOT_Z[1] - r.STRAP_SLOT_Z[0])
        w, t = self.SLOT_MIN
        for sl in r.strap_slots():
            zc, yc = (sl["z0"] + sl["z1"]) / 2, (sl["y0"] + sl["y1"]) / 2
            # a 14 x 3.5 bar passes straight through the saddle and out of both sides: nothing of the arm in its way
            bar = self.box(sl["x0"] - 3, sl["x1"] + 3, yc - t / 2, yc + t / 2, zc - w / 2, zc + w / 2)
            self.assertLess((bar ^ self.arm).volume(), 1e-3, sl)
            # the strap really goes round the pole: the tunnel is behind the upright and in front of the V's apex
            yb, ya, yr = r.saddle_planes()
            self.assertLessEqual(sl["y1"], yb + 1e-6)
            self.assertGreater(sl["y0"], ya)
            # and its exits are rounded, not a sharp edge: just inside each rear exit edge is air
            for sx in (-1, 1):
                p = self.box(sx * sl["x1"] - 0.4, sx * sl["x1"] + 0.4, sl["y0"] - 0.6, sl["y0"] - 0.2, zc - 1, zc + 1)
                self.assertLess((p ^ self.arm).volume(), 1e-3, (sl, sx))
        # the two straps as far apart as the upright allows: each tunnel within a wall or two of the upright's ends
        self.assertLess(r.strap_slots()[0]["z0"] - self.u["z0"], 2 * self.WALL + 0.5)
        self.assertLess(self.u["z1"] - r.strap_slots()[1]["z1"], 2 * self.WALL + 0.5)

    def test_walls_round_the_slots(self):
        r = self.r
        m = self.WALL
        for sl in r.strap_slots():
            x0, x1 = sl["x0"] + r.STRAP_EXIT_R + 0.5, sl["x1"] - r.STRAP_EXIT_R - 0.5
            inner = self.box(x0, x1, sl["y0"], sl["y1"], sl["z0"], sl["z1"])
            shell = self.box(x0, x1, sl["y0"] - m, sl["y1"] + m, sl["z0"] - m, sl["z1"] + m) - inner
            self.assertAlmostEqual((shell ^ self.arm).volume(), shell.volume(), delta=1e-3 * shell.volume())

    def test_saddle_seats_a_1in_pole(self):
        r = self.r
        z0, z1 = self.u["z0"] + 0.5, self.u["z1"] - 0.5
        for d in (25.4, r.POLE_RANGE[0], r.POLE_RANGE[1]):
            px, py = r.pole_axis(d)
            self.assertAlmostEqual(px, 0.0)
            # no interference: the pole, 0.02 under size (the probe is a 96-sided polygon), overlaps nothing ...
            pole = r.cyl((px, py), d - 0.02, z0, z1)
            self.assertLess((pole ^ self.arm).volume(), 1e-3, d)
            self.assertLess(pole.min_gap(self.arm, 5.0), 0.05, d)              # ... and sits ON the saddle
            # contact on two lines: a 0.2 larger pole meets the arm in exactly two thin strips, one per flank, along
            # the whole saddle, on the contacts pole_contacts() names
            touch = (r.cyl((px, py), d + 0.2, z0, z1) ^ self.arm).decompose()
            self.assertEqual(len(touch), 2, d)
            want = sorted(r.pole_contacts(d))
            for t, (cx, cy) in zip(sorted(touch, key=lambda m: m.bounding_box()[0]), want, strict=True):
                bb = t.bounding_box()
                strip = 2 * (d * 0.1) ** 0.5 + 0.3                           # a 0.1 interference on a line contact
                self.assertLess(math.hypot(bb[3] - bb[0], bb[4] - bb[1]), strip, d)      # a line, not a face
                self.assertAlmostEqual((bb[0] + bb[3]) / 2, cx, delta=0.5)
                self.assertAlmostEqual((bb[1] + bb[4]) / 2, cy, delta=0.5)
                self.assertGreater(bb[5] - bb[2], 0.9 * (z1 - z0))        # along the whole saddle
            self.assertLess(want[0][0], 0.0)
            self.assertGreater(want[1][0], 0.0)

    def test_no_pole_screw_holes_left(self):
        r = self.r
        u, arm = self.u, self.arm
        # the original's small slots were there (measured on the original), and each one is now solid
        slots, y_back, y_front = r.clamp_slots()
        self.assertGreaterEqual(len(slots), 2)
        for x0, x1, sz0, sz1 in slots:
            p = self.box(x0, x1, y_back + 0.1, y_front - 0.1, sz0, sz1)
            self.assertAlmostEqual((p ^ arm).volume(), p.volume(), delta=1e-3 * p.volume())
        # and nothing at all goes through the upright: the whole slab is solid
        w = r.SADDLE_HALF_W - 0.5
        slab = self.box(-w, w, u["y_back"] + 0.2, u["y_front"] - 0.2, u["z0"] + 0.5, u["z1"] - 2.5)
        self.assertAlmostEqual((slab ^ arm).volume(), slab.volume(), delta=1e-4 * slab.volume())
        # the only ways through the saddle along Y are none: from its back to the upright, solid round the V
        for x in (-17.0, 17.0):
            col = self.box(x - 0.5, x + 0.5, r.saddle_planes()[2] + 0.2, u["y_back"] - r.STRAP_SLOT[1] - 0.2,
                           u["z0"] + 0.5, u["z1"] - 0.5)
            self.assertAlmostEqual((col ^ arm).volume(), col.volume(), delta=1e-3 * col.volume())


if __name__ == "__main__":
    unittest.main()
