"""The shield remix (hardware/pods-r1/shield/remix.py): the top cap (object_70) with the UV box's screw bosses, and the
L-arm (object_72) with the TH and BARO boxes' mounting faces.

The shield 3MF stays outside git (sources.shield_3mf), and so do the remixed STLs (sources.shield_out). These tests skip
when the 3MF is absent (CI) or when CadQuery / manifold3d are missing (the plain .venv). Run with the CAD venv:
    .venv-cad/bin/python -m unittest tests.test_pods_remix -v
Every check measures the remixed solids and the placed boxes (manifold distances, intersections, ray casts), not the
numbers remix.py built them from.
"""
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"

try:
    import cadquery  # noqa: F401
    import manifold3d as mf
    import numpy as np
except ImportError:                                    # the plain .venv has neither
    mf = None

CLEAR = 5.0        # the brief: the TH and BARO boxes clear the base cup and the pole clamp by 5 mm
EDGE = 3.0         # the brief: every UV mount hole at least 3 mm inside the cap's flat top
SLIVER = 1.0       # mm^3: an intersection smaller than this is two faces touching, not an overlap


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def overlap(a, b):
    return (a ^ b).volume()


def closed_two_manifold(m):
    """Every edge of the exported triangle mesh is shared by exactly two triangles, once in each direction."""
    mesh = m.to_mesh()
    tri = np.asarray(mesh.tri_verts, dtype=np.int64)
    e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    fwd = {tuple(x) for x in e.tolist()}
    return len(fwd) == len(e) and all((b, a) in fwd for a, b in fwd)


@unittest.skipIf(mf is None, "CadQuery / manifold3d / numpy missing: run with .venv-cad/bin/python")
class PodsRemix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = load("pods_remix", PODS / "shield" / "remix.py")
        path = cls.r.S.shield_path()
        if not path.exists():
            raise unittest.SkipTest(f"shield 3MF not present at {path} (kept outside git; sources.shield_3mf)")
        cls.asm = cls.r.A.assembled()
        cls.orig = {k: cls.r.as_manifold(*cls.asm[k]) for k in cls.asm}

    def assert_part_is_good(self, new, old):
        """A closed 2-manifold in one piece (nothing added is floating), larger than the original, and the original kept
        except where the screw and lead holes go through it."""
        self.assertEqual(new.status(), mf.Error.NoError)
        self.assertTrue(closed_two_manifold(new))
        self.assertEqual(len(new.decompose()), 1, "an added boss or face is floating")
        self.assertGreater(new.volume(), old.volume())
        lost = (old - new).volume()
        self.assertLess(lost, 0.02 * old.volume(), lost)

    # ------------------------------------------------------------------ the cap: UV box on screw bosses
    def test_cap_bosses(self):
        r = self.r
        cap = r.cap_remixed()
        old = self.orig[r.A.CAP]
        self.assert_part_is_good(cap, old)
        top_z, flat_r = r.cap_flat_top()
        # the flat top really is flat and round at that radius, measured on the remixed mesh with vertical rays
        for a in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            self.assertAlmostEqual(r.top_z(cap, (flat_r - 0.5) * math.cos(a), (flat_r - 0.5) * math.sin(a)), top_z, 2)
            self.assertLess(r.top_z(cap, (flat_r + 1.0) * math.cos(a), (flat_r + 1.0) * math.sin(a)), top_z - 0.5)
        self.assertLess(overlap(cap, self.orig["object_79.6"]), SLIVER)        # the bosses stay out of the top plate
        m = r.uv_mount()
        head = r.S.val("pod_mount_screw")[2]
        self.assertGreaterEqual(len(m["holes"]), 2)
        for x, y in m["holes"]:
            edge = flat_r - math.hypot(x, y)
            self.assertGreaterEqual(edge, EDGE, (x, y, edge))
            self.assertGreaterEqual(edge, head / 2, (x, y, edge))
            # a clear M3 hole through the cap, a flat seat for the whole head, and a straight way up to it from below
            pin = r.cyl((x, y), 2.9, m["seat_z"] - 0.01, top_z + 1)
            self.assertLess(overlap(pin, cap), 1e-3)
            ring = r.cyl((x, y), head, m["seat_z"], m["seat_z"] + 0.4) - r.cyl((x, y), r.HOLE_D, m["seat_z"] - 1, m["seat_z"] + 1)
            self.assertAlmostEqual(overlap(ring, cap), ring.volume(), delta=0.02 * ring.volume())
            reach = r.cyl((x, y), head, old.bounding_box()[2] - 5, m["seat_z"] - 0.01)
            self.assertLess(overlap(reach, cap), 1e-3)
            grip = top_z - m["seat_z"]
            length = r.S.val("pod_mount_screw")[1]
            bore_d, bore_depth = r.S.val("pod_insert_bore")
            self.assertGreaterEqual(length - grip, 4.0)                  # thread in the insert
            self.assertLessEqual(length - grip, bore_depth - 0.5)        # the screw does not bottom in the bore
        # the UV box sits on the cap's flat top and overlaps nothing; its holes are the box's own mount-face holes
        box = r.box_placed("UV")
        self.assertLess(overlap(box, cap), SLIVER)
        self.assertAlmostEqual(box.bounding_box()[2], top_z, 3)
        placed = [tuple(np.round(p[:2], 3)) for p in r.box_points("UV", [(*h, r.P.dims("UV")["z_bo"]) for h in r.P.mount_face("UV").holes])]
        for h in m["holes"]:
            self.assertIn(tuple(np.round(h, 3)), placed)
        # the gland keep-out is entirely off the cap (and the louvers), and the gland and its cable meet nothing
        footprint = [cap.bounding_box()] + [self.orig[f"object_79.{i}"].bounding_box() for i in range(1, 7)]
        for x, y, d in m["keepouts"]:
            self.assertGreaterEqual(d, 18.0)
            for b in footprint:
                dx = max(b[0] - x, 0, x - b[3])
                dy = max(b[1] - y, 0, y - b[4])
                self.assertGreaterEqual(math.hypot(dx, dy), d / 2, (x, y, b))
        drop = r.uv_cable_envelope()
        for k in [r.A.CAP] + [f"object_79.{i}" for i in range(1, 7)] + [r.A.CUP]:
            self.assertGreater(drop.min_gap(self.orig[k] if k != r.A.CAP else cap, 50.0), 1.0, k)
        self.assertGreater(drop.min_gap(r.arm_remixed(), 50.0), 1.0)
        # printable on its flat top as before: no more steep downward area than the original, bar the new holes' roofs
        self.assertLessEqual(r.overhang_area(cap, r.CAP_PRINT_UP), r.overhang_area(old, r.CAP_PRINT_UP) + 30.0 * len(m["holes"]))

    # ------------------------------------------------------------------ the arm: TH and BARO faces
    def test_arm_faces(self):
        r = self.r
        arm = r.arm_remixed()
        old = self.orig[r.A.ARM]
        self.assert_part_is_good(arm, old)
        cup = self.orig[r.A.CUP]
        plate1 = self.orig["object_79.1"]
        clamp = r.clamp_envelope()
        slots, y_back, y_front = r.clamp_slots()                         # the hose-clamp slots, measured in the upright
        self.assertGreaterEqual(len(slots), 2)
        for x0, x1, z0, z1 in slots:                                     # the envelope holds the band in every slot
            probe = r.cyl(((x0 + x1) / 2, (y_back + y_front) / 2), 0.5, (z0 + z1) / 2 - 0.25, (z0 + z1) / 2 + 0.25)
            self.assertAlmostEqual(overlap(probe, clamp), probe.volume(), delta=1e-3)
        cz = cup.bounding_box()
        self.assertLess(overlap(arm, cup), SLIVER)
        self.assertGreaterEqual((arm - old).min_gap(cup, 20.0), 1.0)      # the new faces and tabs leave the cup free to go on
        boxes = {}
        for n in ("TH", "BARO"):
            box = r.box_placed(n)
            boxes[n] = box
            bb = box.bounding_box()
            self.assertGreaterEqual(box.min_gap(cup, 50.0), CLEAR, n)
            self.assertGreaterEqual(box.min_gap(clamp, 50.0), CLEAR, n)
            self.assertLess(bb[5], plate1.bounding_box()[2], n)          # below the plates ...
            self.assertGreaterEqual(box.min_gap(plate1, 50.0), CLEAR, n)
            self.assertLess(bb[2], cz[5])                                   # ... and beside the base cup: their heights overlap
            self.assertGreater(bb[5], cz[2])
            self.assertLess(overlap(box, arm), SLIVER, n)
            self.assertLess(overlap(box, cup), SLIVER, n)
            m = r.arm_mount(n)
            head = r.S.val("pod_mount_screw")[2]
            self.assertGreaterEqual(len(m["holes"]), 4)
            nrm = np.array(m["normal"])                                   # from the box's back face into the arm
            placed = [tuple(np.round(p, 3)) for p in r.box_points(n, [(*h, r.P.dims(n)["z_bo"]) for h in r.P.mount_face(n).holes])]
            for h in m["holes"]:
                h = np.array(h)
                self.assertIn(tuple(np.round(h, 3)), placed)
                t = m["thickness"]
                pin = r.cyl_axis(h - nrm * 1.0, h + nrm * (t + 1.0), 2.9)
                self.assertLess(overlap(pin, arm), 1e-3, (n, h))
                ring = r.cyl_axis(h + nrm * (t - 0.4), h + nrm * t, head) - r.cyl_axis(h, h + nrm * (t + 1), r.HOLE_D)
                self.assertAlmostEqual(overlap(ring, arm), ring.volume(), delta=0.02 * ring.volume())
                length = r.S.val("pod_mount_screw")[1]
                self.assertGreaterEqual(length - t, 4.0)
                self.assertLessEqual(length - t, r.S.val("pod_insert_bore")[1] - 0.5)
        self.assertGreaterEqual(boxes["TH"].min_gap(boxes["BARO"], 50.0), CLEAR)
        # the TH lead: down the stand, out of the base cup through its existing Ø5 hole, through the arm to the TH box
        hole = r.A.features(r.A.CUP)["cable_hole"]
        self.assertAlmostEqual(hole[2], 2.5, delta=0.1)
        lead_d = r.S.val("pg7_seal")[1]                                  # the lead's largest OD the gland takes
        self.assertLess(lead_d, 2 * hole[2])
        path = r.th_lead_path()
        tube = r.tube(path, lead_d)
        self.assertLess(overlap(tube, cup), 1e-3)
        self.assertLess(overlap(tube, arm), 1e-3)
        self.assertLess(overlap(tube, boxes["TH"]), 1e-3)
        cx, cy = r.A.placements()[r.A.CUP][:2] + np.array(hole[:2])
        self.assertLess(math.hypot(path[0][0] - cx, path[0][1] - cy), 0.01)          # it starts in the cup's own hole
        self.assertGreater(path[0][2], cz[5] - 0.01)
        gland = [o for o in r.P.openings("TH") if o[0] == "lead_gland"][0]
        g = r.box_points("TH", [gland[1]])[0]
        self.assertLess(path[-1][2], g[2])                               # it ends below the TH box's lead gland (a drip loop)
        self.assertLess(math.hypot(path[-1][0] - g[0], path[-1][1] - g[1]), 30.0)
        self.assertLessEqual(r.lead_length(), r.S.val("th_lead_m") * 1000)
        # printable on the upright's back face: no more steep downward area than the original arm in its own 3MF pose
        # (base plate down), bar the roofs of the nine new horizontal holes (eight screw holes and the lead hole)
        self.assertLessEqual(r.overhang_area(arm, r.ARM_PRINT_UP), r.overhang_area(old, (0.0, 0.0, 1.0)) + 30.0 * 9)


if __name__ == "__main__":
    unittest.main()
