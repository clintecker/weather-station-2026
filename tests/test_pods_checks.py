"""Pod electrical checks (hardware/pods-r1/layout/pod_checks.py): copper-derived netlists, pin map, port independence,
reversed cable, addresses, pull-up budget and rise time, write-protect shunt."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"
NETS = ("3V3", "GND", "SDA", "SCL")


def load(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class PodChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = load("pod_checks", PODS / "layout" / "pod_checks.py")
        cls.pods = {n: cls.c.pods.pod(n) for n in cls.c.pods.POD_NAMES}

    def test_no_shorts(self):
        for n, p in self.pods.items():
            with self.subTest(pod=n):
                self.assertEqual(self.c.copper_faults(p), [], self.c.copper_faults(p))
                nl = self.c.netlist(p)
                declared = p.nets()
                for net in NETS + ("WP",):
                    self.assertIn(net, nl, f"{net} missing from the copper netlist")
                    self.assertEqual({f"{r}.{pin}" for r, pin in nl[net]}, declared[net],
                                     f"{n} {net}: copper group is not exactly the declared pins")
                # no strip carries two declared nets
                label = {}
                for q in p.parts:
                    for pin, hole in q.pins.items():
                        label.setdefault(self.c.pods.PP.strip_of(hole), set()).add(q.nets.get(pin) or "NC")
                for strip, labs in label.items():
                    self.assertEqual(len(labs), 1, f"{n}: strip {strip} carries {labs}")

    def test_open_is_caught(self):
        for n, p in self.pods.items():
            for i in range(len(p.wires)):
                with self.subTest(pod=n, dropped=i):
                    q = copy.deepcopy(p)
                    gone = q.wires.pop(i)
                    fails = self.c.copper_faults(q)
                    self.assertTrue(any(gone.net in f for f in fails), (gone, fails))

    def test_short_is_caught(self):
        q = copy.deepcopy(self.pods["UV"])
        q.wires.append(self.c.pods.w("GND", "A2", "A4"))      # jack 3.3 V strip to jack ground strip
        self.assertTrue(self.c.copper_faults(q))

    def test_pin_map(self):
        spec = {"2": "3V3", "3": "SDA", "4": "GND", "5": "SCL"}       # the fixed sensor-port map; 1 and 6 unused
        for n, p in self.pods.items():
            with self.subTest(pod=n):
                nl = self.c.netlist(p)
                for pin, net in spec.items():
                    self.assertIn(("J1", pin), nl[net], f"J1 pin {pin} not on {net}")
                for pin in ("1", "6"):
                    self.assertEqual(self.c.net_of(p, "J1", pin), "NC")
                    group = [pins for k, pins in nl.items() if ("J1", pin) in pins][0]
                    self.assertEqual(group, {("J1", pin)}, f"J1 pin {pin} shares copper with {group}")

    def test_pod_port_independent(self):
        for n, p in self.pods.items():
            for port in (1, 2, 3, 4):
                with self.subTest(pod=n, port=port):
                    e = self.c.end_to_end(p, port)
                    self.assertEqual(set(e), {1, 2, 3, 4, 5, 6})
                    for pin, (pod_net, tx_net) in e.items():
                        self.assertEqual(pod_net, tx_net, f"{n} on S{port} pin {pin}")

    def test_mutated_pod_fails_end_to_end(self):
        for n, p in self.pods.items():
            q = copy.deepcopy(p)
            q.wires = [w for w in q.wires if not (w.net == "SDA" and w.hole_a == "C3")]     # the J1 SDA wire
            e = self.c.end_to_end(q, 1)
            self.assertEqual(e[3], ("OPEN(SDA)", "SDA"), n)
            self.assertTrue(self.c.cable_faults(q, "straight"), n)
            q = copy.deepcopy(p)
            q.wires.append(self.c.pods.w("GND", "A2", "A4"))                                 # 3V3 to GND at the jack
            e = self.c.end_to_end(q, 1)
            self.assertTrue(e[2][0].startswith("SHORT("), e[2])
            self.assertTrue(self.c.cable_faults(q, "straight"), n)

    def test_cable_reversed_flagged(self):
        r = self.c.cable_map("reversed")
        self.assertEqual({k: r[k] for k in (2, 5, 3, 4)}, {2: 5, 5: 2, 3: 4, 4: 3})
        self.assertEqual(self.c.cable_map("straight"), {i: i for i in range(1, 7)})
        for n, p in self.pods.items():
            e = self.c.end_to_end(p, 2, "reversed")
            self.assertEqual(e[2], ("SCL", "3V3"))        # TX 3.3 V lands on the pod's SCL
            self.assertEqual(e[5], ("3V3", "SCL"))
            self.assertTrue(self.c.cable_faults(p, "reversed"), "a reversed cable must be reported")
            self.assertFalse(self.c.cable_faults(p, "straight"))

    def test_addresses_unique(self):
        want = {"TH": {0x44, 0x50}, "BARO": {0x47, 0x50}, "UV": {0x53, 0x50}}
        for n, p in self.pods.items():
            with self.subTest(pod=n):
                a = self.c.addresses(p)
                self.assertEqual(len(a), len(set(a)))
                self.assertEqual(set(a), want[n])

    def test_pullup_budget_two_metres(self):
        for n, p in self.pods.items():
            with self.subTest(pod=n):
                self.assertGreaterEqual(self.c.sink_total(p), (3.3 - 0.4) / 3e-3)
                t = self.c.rise_ns(p, 2.0)
                self.assertLessEqual(t, 1000)
                self.assertAlmostEqual(t, 0.8473 * self.c.pullup_total(p) * self.c.bus_pf(p, 2.0) * 1e-3, places=6)
                self.assertEqual(self.c.budget_failures(p), [])
        # the TX mux channel, the sensor breakout and the EEPROM breakout, 10 k each in parallel
        self.assertAlmostEqual(self.c.pullup_total(self.pods["UV"]), 10000 / 3, places=6)

    def test_upstream_pullups_counted(self):
        """The main bus's pull-ups (read from the TX model) load the sink check while the channel is selected."""
        up = dict(self.c.upstream_pullups())
        self.assertEqual(up, {"A1": 4.7, "U1": 10.0, "U2": 10.0, "U4": 10.0, "U5": 10.0, "U6": 10.0})
        p = self.pods["UV"]
        g = 1 / self.c.pullup_total(p) + sum(1 / (1000 * k) for k in up.values())
        self.assertAlmostEqual(self.c.sink_total(p), 1 / g, places=6)
        self.assertLess(self.c.sink_total(p), self.c.pullup_total(p))
        # a fake extra 10 k upstream lowers the sink total and, at today's 2 % margin, fails the check
        base = self.c.sink_total(p)
        more = self.c.sink_total(p, extra_upstream_k=(10.0,))
        self.assertLess(more, base)
        self.assertEqual(self.c.budget_failures(p), [])
        fails = self.c.budget_failures(p, extra_upstream_k=(10.0,))
        self.assertTrue(any("main bus" in f and "< 967" in f for f in fails), fails)
        # the rise time is the port segment's own (see rise_ns): an upstream pull-up does not fail it
        self.assertFalse(any("rise" in f for f in fails), fails)

    def test_budget_names_the_resistor_to_remove(self):
        p = self.pods["BARO"]
        fails = self.c.budget_failures(p, extra_k=(1.0, 1.0))        # pretend two more 1 k pull-ups
        self.assertTrue(fails)
        # the sensor breakout's (U2), never the EEPROM's (U1): the EEPROM is the pod's identity and stays
        self.assertTrue(any("remove" in f and "U2 (bmp581)" in f for f in fails), fails)
        self.assertFalse(any("eeprom" in f for f in fails), fails)
        slow = self.c.budget_failures(p, metres=2000.0)              # an absurd cable: rise time fails
        self.assertTrue(any("rise" in f for f in slow), slow)

    def test_capacitance_counts_everything(self):
        th, uv = self.pods["TH"], self.pods["UV"]
        per_m = self.c.cable_pf_per_m()
        self.assertGreater(per_m, 0)
        # cable, 10 pF per device and the TX port's 60 pF allowance (tx-stack-r1 schematic/checks.py check_outdoor)
        self.assertEqual(self.c.TX_PORT_PF, 60.0)
        self.assertAlmostEqual(self.c.bus_pf(uv, 2.0), 2.0 * per_m + 10 * self.c.device_count(uv) + 60.0)
        self.assertAlmostEqual(self.c.bus_pf(th, 2.0) - self.c.bus_pf(uv, 2.0), th.lead.length_m * per_m)

    def test_tx_port_allowance_still_60pf(self):
        """TX_PORT_PF mirrors a literal in the TX checks' port note; fail if that note changes."""
        src = (Path(__file__).resolve().parent.parent / "hardware" / "tx-stack-r1" / "schematic" / "checks.py").read_text()
        self.assertIn("less a 60 pF allowance: two 10 pF clamps plus an estimated 40 pF of boards and module", src)
        self.assertIn("(cmax - 60)", src)

    def test_wp_shunt_protects(self):
        for n, p in self.pods.items():
            with self.subTest(pod=n):
                self.assertEqual(self.c.wp_level(p, shunt=True), "3V3")
                self.assertEqual(self.c.wp_level(p, shunt=False), "GND")

    def test_tx_port_model_read(self):
        m = self.c.tx_port_map(3)
        self.assertEqual(m, {1: "NC", 2: "3V3", 3: "SDA", 4: "GND", 5: "SCL", 6: "NC"})

    def test_check_all_passes_and_report_runs(self):
        self.assertEqual(self.c.check_all(), [])
        self.assertIn("UV", "\n".join(self.c.report()))


if __name__ == "__main__":
    unittest.main()
