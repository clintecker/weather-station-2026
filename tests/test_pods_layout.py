"""The pod board layouts (hardware/pods-r1/layout/pods.py): named parts, pins on holes, breakouts as supplied, the TH lead."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def overlap(a, b):
    return a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1 and a.z0 < b.z1 and b.z0 < a.z1


class PodLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load("pods_layout", PODS / "layout" / "pods.py")
        cls.S, cls.PP = cls.m.S, cls.m.PP
        cls.pods = {n: cls.m.pod(n) for n in cls.m.POD_NAMES}

    def texts(self, p):
        t = [part.part for part in p.parts]
        if p.lead:
            t.append(p.lead.part)
        return " | ".join(t)

    def test_parts_named_exactly(self):
        self.assertEqual(self.m.POD_NAMES, ("TH", "BARO", "UV"))
        sensor = {"TH": "#6174", "BARO": "#6407", "UV": "#4831"}
        for n, p in self.pods.items():
            t = self.texts(p)
            for num in ("#5146", "BOB-14021", "87180-066LF", "SPC02SYAN", "PRPC002SAAN-RC", "MFR-25FBF52-10K",
                        sensor[n]):
                self.assertIn(num, t, (n, num))
            for other in set(sensor.values()) - {sensor[n]}:
                self.assertNotIn(other, t, (n, other))
            refs = [part.ref for part in p.parts]
            self.assertEqual(len(refs), len(set(refs)), n)
            expect = {"J1", "U1", "JP1", "R1"} | ({"U2"} if n == "BARO" else set())
            self.assertEqual(set(refs), expect, n)
            self.assertEqual(p.lead is not None, n != "BARO")

    def test_all_pins_on_holes(self):
        for n, p in self.pods.items():
            used = p.holes_used()
            for h, users in used.items():
                self.assertIn(h, self.PP.HOLES, (n, h, users))
                if len(users) > 1:
                    self.assertIn(h, p.joints, f"{n}: {h} used by {users} and not marked as a joint")
            for part in p.parts:                       # the pin's hole is where the part's geometry puts it
                for pin, h in part.pins.items():
                    self.assertIn(h, self.PP.HOLES, (n, part.ref, pin))
            for w in p.wires:
                self.assertIn(w.side, ("top", "bottom"))
                self.assertNotEqual(w.hole_a, w.hole_b)

    def test_breakouts_as_supplied(self):
        S, P = self.S, self.m.P
        for n, p in self.pods.items():
            for part in p.parts:
                if part.kind != "BREAKOUT":
                    continue
                key = part.source
                names = S.val(key + "_pins")
                x1, y1, pitch = S.val(key + "_hdr")
                self.assertIn(part.rot, (0, 180), (n, part.ref))          # a turn, never a mirror
                pcb = next(b for b in part.boxes if b.what.endswith("PCB"))
                w, d = S.val(key)
                self.assertAlmostEqual(pcb.x1 - pcb.x0, w, places=3)
                self.assertAlmostEqual(pcb.y1 - pcb.y0, d, places=3)
                fitted = list(part.pins)
                self.assertEqual(tuple(fitted) + part.unfitted, tuple(names), (n, part.ref))   # pad order kept
                x0, y0 = part.origin
                s = 1 if part.rot == 0 else -1
                for i, nm in enumerate(fitted):
                    hx, hy = self.PP.HOLES[part.pins[nm]]
                    self.assertAlmostEqual(hx, x0 + s * (x1 + i * pitch), places=3, msg=(n, part.ref, nm))
                    self.assertAlmostEqual(hy, y0 + s * y1, places=3, msg=(n, part.ref, nm))
                    self.assertAlmostEqual(pitch, P)
                # the outline sits where the pads say: pad 1 at (x1, y1) from the maker's lower-left corner
                corner = (pcb.x0, pcb.y0) if part.rot == 0 else (pcb.x1, pcb.y1)
                self.assertAlmostEqual(corner[0], x0, places=3)
                self.assertAlmostEqual(corner[1], y0, places=3)
            j1 = p.part("J1")
            self.assertEqual([j1.pins[str(i)] for i in range(1, 7)], [f"A{i}" for i in range(1, 7)])

    def test_th_lead_colours(self):
        p = self.pods["TH"]
        lead = p.lead
        got = {c.colour: (c.net, c.pad) for c in lead.conductors}
        self.assertEqual(got, {"red": ("3V3", "VIN"), "black": ("GND", "GND"), "yellow": ("SCL", "SCL"),
                               "blue": ("SDA", "SDA")})
        self.assertTrue(set(c.pad for c in lead.conductors) <= set(self.S.val("sht45_pins")))
        self.assertIn("#6174", lead.part)
        self.assertEqual(lead.length_m, self.S.val("th_lead_m"))
        for c in lead.conductors:
            self.assertIn(c.hole, self.PP.HOLES)
        # the lead's pod end lands where the BARO pod's BMP581 has the same nets (SDA aside: BARO's is strip 15)
        baro = self.pods["BARO"].part("U2")
        by_net = {baro.nets[pin]: h for pin, h in baro.pins.items() if baro.nets[pin]}
        for c in lead.conductors:
            if c.net != "SDA":
                self.assertEqual(c.hole, by_net[c.net], c)

    def test_uv_lead_matches_th(self):
        th, uv = self.pods["TH"].lead, self.pods["UV"].lead
        self.assertEqual([(c.colour, c.net, c.pad, c.hole) for c in uv.conductors],
                         [(c.colour, c.net, c.pad, c.hole) for c in th.conductors])
        self.assertTrue(set(c.pad for c in uv.conductors) <= set(self.S.val("ltr390_pins")))
        self.assertIn("#4831", uv.part)
        self.assertEqual(uv.length_m, self.S.val("uv_lead_m"))

    # ---------------------------------------------------------------- beyond the plan's four
    def test_jack_faces_gland_edge(self):
        for n, p in self.pods.items():
            j1 = p.part("J1")
            jack = next(b for b in j1.boxes if "87180-066LF" in b.what)
            plug = next(b for b in j1.boxes if b.keepout)
            self.assertEqual(self.m.GLAND_EDGE, "bottom")
            self.assertLess(jack.y0, 0, n)                        # the mouth is at or past the bottom edge
            self.assertAlmostEqual(plug.y1, jack.y0, places=3)    # the plug goes in from below
            self.assertLess(plug.y0, jack.y0)

    def test_parts_clear_each_other_and_the_mounting_holes(self):
        keep = self.S.val("mount_keep")
        holes = self.PP.OUTLINE["mounting_holes"]
        for n, p in self.pods.items():
            boxes = [(part.ref, b) for part in p.parts for b in part.boxes]
            for i, (ra, a) in enumerate(boxes):
                for rb, b in boxes[i + 1:]:
                    if ra != rb:
                        self.assertFalse(overlap(a, b), f"{n}: {a.what} hits {b.what}")
                for hx, hy, _d in holes:
                    cx, cy = min(max(hx, a.x0), a.x1), min(max(hy, a.y0), a.y1)
                    self.assertGreaterEqual(((cx - hx) ** 2 + (cy - hy) ** 2) ** 0.5, keep, f"{n}: {a.what} over a mounting hole")

    def test_each_strip_carries_one_net(self):
        for n, p in self.pods.items():
            on = {}
            for part in p.parts:
                for pin, h in part.pins.items():
                    on.setdefault(self.PP.strip_of(h), set()).add(part.nets[pin] or f"nc:{part.ref}.{pin}")
            for w in p.wires:
                for h in (w.hole_a, w.hole_b):
                    on.setdefault(self.PP.strip_of(h), set()).add(w.net)
            if p.lead:
                for c in p.lead.conductors:
                    on.setdefault(self.PP.strip_of(c.hole), set()).add(c.net)
            for strip, nets in on.items():
                self.assertEqual(len(nets), 1, f"{n}: {strip} carries {nets}")
            for net in ("3V3", "GND", "SDA", "SCL", "WP"):
                self.assertIn(net, p.nets(), n)
            self.assertIn("J1.1", p.unconnected())
            self.assertIn("J1.6", p.unconnected())

    def test_wp_strap(self):
        for _n, p in self.pods.items():
            u1, jp, r1 = p.part("U1"), p.part("JP1"), p.part("R1")
            wp = self.PP.strip_of(u1.pins["WP"])
            self.assertEqual(self.PP.strip_of(jp.pins["2"]), wp)
            self.assertEqual(self.PP.strip_of(r1.pins["1"]), wp)
            self.assertEqual((jp.nets["1"], jp.nets["2"]), ("3V3", "WP"))
            self.assertEqual((r1.nets["1"], r1.nets["2"]), ("WP", "GND"))
            self.assertEqual(self.S.val("eeprom_24lc32_wp"), "floating")

    def test_same_footprint_and_wiring(self):
        def sig(p):
            return [(q.ref, tuple(sorted(q.pins.items()))) for q in p.parts if q.ref != "U2"]

        def wires(p):
            return [(w.net, w.hole_a, w.hole_b, w.side, w.colour) for w in p.wires]
        th, baro, uv = (self.pods[k] for k in ("TH", "BARO", "UV"))
        self.assertEqual(sig(th), sig(uv))
        self.assertEqual(sig(baro), sig(uv))
        self.assertEqual(wires(th), wires(uv))
        diff = [(a, b) for a, b in zip(wires(baro), wires(uv), strict=True) if a != b]
        self.assertEqual(len(wires(baro)), len(wires(uv)))
        self.assertEqual({a[0] for a, _b in diff}, {"SDA"})            # only the SDA wires follow the sensor's SDA pad
        self.assertEqual(baro.part("U2").pins["VIN"], uv.lead.conductors[0].hole)

    def test_wire_routes(self):
        """Each wire's stored route: starts and ends at its holes, right-angle runs on the 1.27 grid, OD/2 +
        fillet_clear from every used hole but its own ends, clear of the mounting holes, on the board, and never
        beside (1.27) or along another wire on the same side; crossings only at right angles."""
        S, PP = self.S, self.PP
        g = self.m.P / 2
        od = S.val("wire24")[1]
        clear = od / 2 + S.val("fillet_clear")
        mkeep = S.val("mount_keep") + od / 2
        w_, h_ = S.val("permaproto_q")

        def nodes(wr):
            pts = [(round(x / g), round(y / g)) for x, y in wr.path]
            out = []
            for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
                self.assertTrue(ax == bx or ay == by, wr)
                n = max(abs(bx - ax), abs(by - ay))
                for k in range(n):
                    out.append((ax + (bx - ax) * k // n, ay + (by - ay) * k // n))
            out.append(pts[-1])
            return out

        for n, p in self.pods.items():
            used = p.holes_used()
            nn = {}
            for wr in p.wires:
                self.assertGreaterEqual(len(wr.path), 2, wr)
                self.assertEqual(wr.path[0], PP.HOLES[wr.hole_a], wr)
                self.assertEqual(wr.path[-1], PP.HOLES[wr.hole_b], wr)
                ns = nodes(wr)
                nn[id(wr)] = ns
                for (i, j) in ns:
                    x, y = i * g, j * g
                    self.assertTrue(0.725 <= x <= w_ - 0.725 and 0.725 <= y <= h_ - 0.725, (n, wr.note))
                    for mx, my, _d in PP.OUTLINE["mounting_holes"]:
                        self.assertGreaterEqual(((x - mx) ** 2 + (y - my) ** 2) ** 0.5, mkeep, (n, wr.note))
                    for hole in used:
                        if hole in (wr.hole_a, wr.hole_b):
                            continue
                        hx, hy = PP.HOLES[hole]
                        self.assertGreaterEqual(((x - hx) ** 2 + (y - hy) ** 2) ** 0.5, clear - 1e-6,
                                                f"{n}: {wr.net} {wr.hole_a}-{wr.hole_b} passes {hole}")
            for a in range(len(p.wires)):
                for b in range(a + 1, len(p.wires)):
                    wa, wb = p.wires[a], p.wires[b]
                    if wa.side != wb.side:
                        continue
                    na, nb = nn[id(wa)], nn[id(wb)]
                    shared = set(na) & set(nb)
                    for c in shared:              # a crossing: straight and perpendicular in both, never an end
                        ka, kb = na.index(c), nb.index(c)
                        self.assertTrue(0 < ka < len(na) - 1 and 0 < kb < len(nb) - 1, (n, wa.note, wb.note))
                        da = (na[ka + 1][0] - na[ka - 1][0], na[ka + 1][1] - na[ka - 1][1])
                        db = (nb[kb + 1][0] - nb[kb - 1][0], nb[kb + 1][1] - nb[kb - 1][1])
                        self.assertEqual(da[0] * db[0] + da[1] * db[1], 0, (n, wa.note, wb.note))
                    near = {c for c in shared for d in ((1, 0), (-1, 0), (0, 1), (0, -1))
                            for c in [(c[0] + d[0], c[1] + d[1])]} | shared
                    for p_ in na:
                        for q in nb:
                            if abs(p_[0] - q[0]) + abs(p_[1] - q[1]) == 1:
                                self.assertTrue(p_ in near or q in near,
                                                f"{n}: {wa.hole_a}-{wa.hole_b} runs beside {wb.hole_a}-{wb.hole_b}")

    def test_wire_colours(self):
        tx = {"3V3": "red", "GND": "black", "SCL": "yellow", "SDA": "blue"}
        for n, p in self.pods.items():
            for w in p.wires:
                self.assertEqual(w.colour, tx.get(w.net, "green"), (n, w))

    def test_three_vo_left_open(self):
        for n, p in self.pods.items():
            for part in p.parts:
                if part.kind == "BREAKOUT":
                    self.assertIsNone(part.nets["3Vo"], (n, part.ref))
                    self.assertEqual(part.nets["VIN"], "3V3", (n, part.ref))


if __name__ == "__main__":
    unittest.main()
