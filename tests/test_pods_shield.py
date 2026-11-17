"""The assembled radiation shield (hardware/pods-r1/shield/assemble.py): placements from the meshes' mating features,
the Ø40 core through the plate stack, and the SHT45 #6174 fit on the stand's inner face.

The 3MF stays outside git (sources.shield_3mf: local path + sha256), so these tests skip when it is absent (CI) or when
numpy is missing (the plain .venv). Run with the CAD venv: .venv-cad/bin/python -m unittest tests.test_pods_shield -v
"""
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
