"""The v1 pod boxes (hardware/pods-r1/box/v1/): Clint's printed STLs, made by his CAD agent from box/CAD-BRIEF.md.

box/podbox.py is the model the sheets draw. These tests hold it to the printed files: each v1 STL is one closed
solid, and the model's TH and BARO bodies and lids differ from them by no more than a tessellation's worth of volume
in each direction (any real feature change, a moved hole or a missing web, is tens to hundreds of mm3). The UV v1
box is retired: the UV pod is the crown now (Clint 2026-11-19); its v1 files stay in box/v1 as a record.

Needs CadQuery and manifold3d, so it skips in the plain .venv (CI). Run with the CAD venv from the repo root:
    .venv-cad/bin/python -m unittest tests.test_pods_v1 -v
"""
import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"
V1 = PODS / "box" / "v1"

try:
    import cadquery as cq
    import manifold3d as m3
    import numpy as np
except ImportError:                                    # the plain .venv has no CadQuery
    cq = None

TOL = 20.0          # mm3, each direction: measured 0.2 to 7.7 at the v1 import (2026-11-18)


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_stl(p):
    b = p.read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(b, dt, n, 84)["v"].astype(float)


def manifold(tri):
    k = np.round(tri.reshape(-1, 3) / 1e-4).astype(np.int64)
    u, inv = np.unique(k, axis=0, return_inverse=True)
    mesh = m3.Mesh(vert_properties=(u * 1e-4).astype(np.float32), tri_verts=inv.reshape(-1, 3).astype(np.uint32))
    return m3.Manifold(mesh)


def tri_of(shape):
    vs, ts = shape.tessellate(0.02, 0.1)
    v = np.array([(p.x, p.y, p.z) for p in vs])
    return v[np.array(ts)]


@unittest.skipIf(cq is None, "needs CadQuery and manifold3d (.venv-cad)")
class V1Boxes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p in (PODS / "layout", PODS):
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
        cls.PB = load("podbox", PODS / "box" / "podbox.py")

    def test_v1_files_are_closed_solids(self):
        for n in ("th", "baro", "uv"):
            for part in ("body", "lid"):
                with self.subTest(pod=n, part=part):
                    m = manifold(read_stl(V1 / f"pod-{n}-{part}.stl"))
                    self.assertEqual(m.status(), m3.Error.NoError)
                    self.assertEqual(len(m.decompose()), 1)

    def test_model_matches_v1(self):
        PB = self.PB
        for n in ("TH", "BARO"):
            d = PB.dims(n)
            for part, shape, z in (("body", PB.body(n), d["z_bo"]), ("lid", PB.lid(n), d["z_rim"])):
                with self.subTest(pod=n, part=part):
                    model = manifold(tri_of(shape.translate(cq.Vector(0, 0, -z))))   # the STLs' print frame
                    v1 = manifold(read_stl(V1 / f"pod-{n.lower()}-{part}.stl"))
                    extra, missing = (model - v1).volume(), (v1 - model).volume()
                    self.assertLess(extra, TOL, f"model has {extra:.1f} mm3 that v1 lacks")
                    self.assertLess(missing, TOL, f"v1 has {missing:.1f} mm3 that the model lacks")


if __name__ == "__main__":
    unittest.main()
