"""The Perma-Proto Quarter model (hardware/pods-r1/layout/permaproto.py) against sources.py and Adafruit's own .brd."""
import importlib.util
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"
SCRATCH = ("/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/"
           "692bc986-c73f-47d7-a8f2-60ffe3bf60e8/scratchpad")
BRD = Path(os.environ.get("PERMAPROTO_BRD", SCRATCH + "/dl-adafruit/pq.brd"))


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def r(x):
    return round(x, 3)


class Permaproto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load("pods_sources", PODS / "sources.py")
        sys.path.insert(0, str(PODS))
        try:
            cls.p = load("pods_permaproto", PODS / "layout" / "permaproto.py")
        finally:
            sys.path.remove(str(PODS))

    def test_grid_matches_adafruit(self):
        s, p = self.s, self.p
        w, h = s.val("permaproto_q")
        self.assertEqual(len(p.HOLES), 210)
        self.assertEqual(len(set(p.HOLES.values())), 210)
        xs = sorted({x for x, _ in p.HOLES.values()})
        self.assertEqual(len(xs), s.val("permaproto_q_cols")[0])
        for a, b in zip(xs, xs[1:], strict=False):
            self.assertAlmostEqual(b - a, 2.54, places=3)
        self.assertEqual((r(p.OUTLINE["width"]), r(p.OUTLINE["height"])), (w, h))
        # lower-left origin: the outline spans 0..w, 0..h and every hole is inside it
        for x, y in p.HOLES.values():
            self.assertTrue(0 < x < w and 0 < y < h, (x, y))
        self.assertAlmostEqual(p.HOLES["A1"][0], 21.59 - 17.78, places=3)
        self.assertAlmostEqual(p.HOLES["A1"][1], 25.4 - 13.97, places=3)
        poly = p.OUTLINE["polygon"]
        self.assertAlmostEqual(min(x for x, _ in poly), 0, places=3)
        self.assertAlmostEqual(max(x for x, _ in poly), w, places=3)
        self.assertAlmostEqual(min(y for _, y in poly), 0, places=3)
        self.assertAlmostEqual(max(y for _, y in poly), h, places=3)
        d, mx, my = s.val("permaproto_q_mount")
        self.assertEqual(p.OUTLINE["mounting_holes"],
                         [(r(w / 2 - mx), r(h / 2 + my), d), (r(w / 2 + mx), r(h / 2 + my), d)])

    def test_strips(self):
        p = self.p
        groups = defaultdict(set)
        for hole in p.HOLES:
            groups[p.strip_of(hole)].add(hole)
        self.assertEqual(sum(len(g) for g in groups.values()), 210)      # no hole in two strips
        self.assertEqual(len(groups), 30 + 4)
        for c in range(1, 16):
            self.assertEqual(groups[f"A-E{c}"], {f"{L}{c}" for L in "ABCDE"})
            self.assertEqual(groups[f"F-J{c}"], {f"{L}{c}" for L in "FGHIJ"})
            self.assertNotEqual(p.strip_of(f"E{c}"), p.strip_of(f"F{c}"))
        for rail in ("bot+", "bot-", "top+", "top-"):
            self.assertEqual(groups[f"rail {rail}"], {f"{rail}{c}" for c in range(1, 16)})
        with self.assertRaises(KeyError):
            p.strip_of("K1")

    def test_names_as_printed(self):
        p = self.p
        for L in "ABCDEFGHIJ":
            for c in range(1, 16):
                self.assertIn(f"{L}{c}", p.HOLES)
        # row letters rise with y (A at the bottom), columns rise with x (1 at the left)
        self.assertLess(p.HOLES["A1"][1], p.HOLES["E1"][1])
        self.assertLess(p.HOLES["E1"][1], p.HOLES["F1"][1])
        self.assertLess(p.HOLES["F1"][1], p.HOLES["J1"][1])
        self.assertLess(p.HOLES["A1"][0], p.HOLES["A15"][0])
        self.assertLess(p.HOLES["bot+1"][1], p.HOLES["bot-1"][1])
        self.assertLess(p.HOLES["bot-1"][1], p.HOLES["A1"][1])
        self.assertLess(p.HOLES["J1"][1], p.HOLES["top+1"][1])
        self.assertLess(p.HOLES["top+1"][1], p.HOLES["top-1"][1])

    def test_matches_brd(self):
        """Every hole position and strip against Adafruit's .brd, read as plain XML data (never executed)."""
        if not BRD.is_file():
            self.skipTest(f"Adafruit's Eagle file is not at {BRD}: download adafruit permaproto quarterbreadboard.brd "
                          "(commit 6a11bc3bbf, see sources.py) into a new folder and set PERMAPROTO_BRD")
        p = self.p
        root = ET.parse(BRD).getroot()
        board = root.find("drawing/board")
        sx, sy = 21.59, 25.4                                   # file origin is the board centre
        # holes and strips: one signal = one strip, its vias are its holes
        file_strips = []
        for sig in board.findall("signals/signal"):
            vias = [(r(float(v.get("x")) + sx), r(float(v.get("y")) + sy)) for v in sig.findall("via")]
            self.assertTrue(vias, sig.get("name"))
            file_strips.append(frozenset(vias))
        ours = defaultdict(set)
        for name, (x, y) in p.HOLES.items():
            ours[p.strip_of(name)].add((r(x), r(y)))
        self.assertEqual({frozenset(v) for v in ours.values()}, set(file_strips))
        self.assertEqual(len(file_strips), len(set(file_strips)))
        self.assertEqual({(r(x), r(y)) for x, y in p.HOLES.values()},
                         set().union(*[set(f) for f in file_strips]))
        # mounting holes
        mh = sorted((r(float(h.get("x")) + sx), r(float(h.get("y")) + sy), float(h.get("drill")))
                    for h in board.findall("plain/hole"))
        self.assertEqual(mh, sorted(p.OUTLINE["mounting_holes"]))
        # outline extremes
        xs = [float(w.get(a)) + sx for w in board.findall("plain/wire") if w.get("layer") == "20" for a in ("x1", "x2")]
        ys = [float(w.get(a)) + sy for w in board.findall("plain/wire") if w.get("layer") == "20" for a in ("y1", "y2")]
        self.assertEqual((r(min(xs)), r(max(xs)), r(min(ys)), r(max(ys))),
                         (0.0, r(p.OUTLINE["width"]), 0.0, r(p.OUTLINE["height"])))
        # silkscreen: every printed letter and number sits beside the row or column it names
        texts = [(t.text, float(t.get("x")) + sx, float(t.get("y")) + sy)
                 for t in board.findall("plain/text") if t.get("layer") == "21" and t.text]
        letters = [t for t in texts if re.fullmatch("[A-J]", t[0])]
        numbers = [t for t in texts if re.fullmatch(r"\d+", t[0])]
        self.assertEqual((len(letters), len(numbers)), (20, 30))
        for L, x, y in letters:
            near = min("ABCDEFGHIJ", key=lambda k: abs(p.HOLES[k + "1"][1] - y))
            self.assertEqual(near, L, (L, x, y))
        for n, x, y in numbers:
            near = min(range(1, 16), key=lambda c: abs(p.HOLES[f"A{c}"][0] - x - 0.254 * (len(n) - 1)))
            self.assertEqual(str(near), n, (n, x, y))
        # rails: red (layer 112) line beside the + rails, blue (113) beside the - rails
        for lay, names in (("112", ("bot+", "top+")), ("113", ("bot-", "top-"))):
            lines = [float(w.get("y1")) + sy for w in board.findall("plain/wire")
                     if w.get("layer") == lay and w.get("y1") == w.get("y2")]
            self.assertEqual(len(lines), 2)
            for nm in names:
                y = p.HOLES[nm + "1"][1]
                self.assertEqual(min(abs(y - ly) for ly in lines) < 2.0, True, nm)


if __name__ == "__main__":
    unittest.main()
