"""The bench breadboard wiring map (hardware/bench-breadboard-r0, docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md).

The model tests use only the repository Python. The KiCad tests need KiCad 10 and the pinned
KiCadRoutingTools (tools/fetch-router.sh); without them they skip and say why."""
import dataclasses
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT/'hardware'/'bench-breadboard-r0'
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(HW/'source'))
import kicad_env  # noqa: E402
import flying  # noqa: E402
import wiring  # noqa: E402

DATA = HW/'source'/'wiring.toml'
GUIDE = ROOT/'docs'/'hardware'/'bench-station-wiring.md'
APP = ROOT/'firmware'/'stage0-node'/'App'

ENV = kicad_env.find()
needs_kicad = unittest.skipUnless(ENV, kicad_env.missing())


class Toolchain(unittest.TestCase):
    def test_toolchain_reports_what_is_missing(self):
        with mock.patch.dict(os.environ, {'KICAD_APP': '/nonexistent/KiCad.app'}):
            self.assertIsNone(kicad_env.find())
            self.assertIn('KICAD_APP', kicad_env.missing())

    @needs_kicad
    def test_toolchain_found_when_present(self):
        out = subprocess.run([ENV.python, '-c', 'import pcbnew; print(pcbnew.Version())'],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), '10.0.6')
        self.assertTrue((ENV.router/'py_router'/'route.py').exists())
        subprocess.run([ENV.router_python, ENV.router/'py_router'/'route.py', '--help'],
                       capture_output=True, check=True)


class Model(unittest.TestCase):
    def setUp(self):
        self.w = wiring.load(DATA)

    def test_strips_join_five_holes(self):
        self.assertEqual(wiring.strip(('A', 'j', 14)), wiring.strip(('A', 'f', 14)))
        self.assertNotEqual(wiring.strip(('A', 'j', 14)), wiring.strip(('A', 'e', 14)))
        self.assertNotEqual(wiring.strip(('A', 'j', 14)), wiring.strip(('A', 'j', 15)))
        self.assertEqual(wiring.strip(('A', 'e', 14)), 'A:a-e:14')

    def test_split_rails_are_two_nets(self):
        self.assertNotEqual(wiring.strip(('A', 'L+', 1), True), wiring.strip(('A', 'L+', 63), True))
        self.assertEqual(wiring.strip(('A', 'L+', 1), False), wiring.strip(('A', 'L+', 63), False))

    def test_every_part_pin_lands_on_its_own_hole(self):
        holes = [h for part in self.w.parts.values() for h in part.pins.values()]
        self.assertEqual(len(holes), len(set(holes)))

    def test_the_data_loads_and_names_its_sources(self):
        for part in self.w.parts.values():
            self.assertTrue(part.source.startswith('https://') or part.source in ('bench check', 'passive'), part.id)
        for net in ('I2C_SDA', 'I2C_SCL', 'CUPS', 'VANE', 'RAIN', 'PGOOD', 'CHG', '3V3', 'GND'):
            self.assertIn(net, self.w.nets)


class Checks(unittest.TestCase):
    def setUp(self):
        self.w = wiring.load(DATA)

    def test_the_model_agrees_with_the_wiring_guide(self):
        self.assertEqual(wiring.check_guide(self.w, GUIDE), [])

    def test_the_model_agrees_with_the_firmware(self):
        self.assertEqual(wiring.check_firmware(self.w, APP), [])

    def test_a_moved_firmware_pin_is_found(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            shutil.copy(APP/'i2c_bus.lit.md', app)
            text = (APP/'board_inputs.c').read_text()
            line = next(ln for ln in text.splitlines() if ln.startswith('#define RAIN_PIN'))
            (app/'board_inputs.c').write_text(text.replace(line, line.replace('GPIO_PIN_5', 'GPIO_PIN_6')))
            problems = wiring.check_firmware(self.w, app)
        self.assertTrue(any('RAIN_PIN' in p for p in problems), problems)

    def test_a_header_the_guide_does_not_list_is_found(self):
        self.w.nets['RAIN'] = ['N:CN10.31' if m == 'N:CN10.29' else m for m in self.w.nets['RAIN']]
        problems = wiring.check_guide(self.w, GUIDE)
        self.assertTrue(any('Rain gauge' in p for p in problems), problems)


def with_part(w, part):
    """The model with one part added or replaced."""
    import dataclasses
    return dataclasses.replace(w, parts={**w.parts, part.id: part})


class Jumpers(unittest.TestCase):
    def setUp(self):
        self.w = wiring.load(DATA)

    def test_the_plan_connects_every_net_and_nothing_else(self):
        self.assertEqual(wiring.prove(self.w, wiring.plan_jumpers(self.w)), [])

    def test_flying_wires_go_down_and_over_without_sharing_a_line(self):
        jumpers = wiring.plan_jumpers(self.w)
        paths = flying.plan(jumpers)
        self.assertEqual(set(paths), {j.id for j in jumpers if j.a[0] != j.b[0]})
        segments = []
        for j in jumpers:
            if j.id not in paths:
                continue
            pts = paths[j.id]
            self.assertEqual((pts[0], pts[-1]), (wiring.hole_xy(j.a), wiring.hole_xy(j.b)), j.id)
            for p, q in zip(pts, pts[1:]):
                self.assertTrue(abs(p[0] - q[0]) < 1e-9 or abs(p[1] - q[1]) < 1e-9, f'{j.id}: {p} to {q} is not square')
                segments.append((j.id, p, q))

        def overlap(s, t):   # two collinear segments sharing more than a point
            (_i, p, q), (_k, r, u) = s, t
            for axis in (0, 1):
                other = 1 - axis
                if all(abs(v[other] - p[other]) < 1e-6 for v in (q, r, u)):
                    lo, hi = sorted((p[axis], q[axis])), sorted((r[axis], u[axis]))
                    return min(lo[1], hi[1]) - max(lo[0], hi[0]) > 1e-6
            return False
        clashes = [(s[0], t[0]) for n, s in enumerate(segments) for t in segments[n + 1:] if s[0] != t[0] and overlap(s, t)]
        self.assertEqual(clashes, [])

    def test_no_jumper_lands_on_a_part_pin(self):
        pins = {h for part in self.w.parts.values() for h in part.pins.values()}
        ends = [h for j in wiring.plan_jumpers(self.w) for h in (j.a, j.b)]
        self.assertFalse(pins & {h for h in ends if h[0] != 'N'})
        self.assertEqual(len(ends), len(set(ends)), 'one wire per hole')

    def test_a_shared_strip_is_a_short(self):
        import dataclasses
        r3 = self.w.parts['R3']
        moved = dataclasses.replace(r3, pins={**r3.pins, '1': ('A', 'b', 6)})   # onto the cups strip
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(with_part(self.w, moved))
        self.assertIn('short', str(e.exception))
        for name in ('BOBW.4 (CUPS)', 'R3.1 (VANE)', 'A:a-e:6'):
            self.assertIn(name, str(e.exception))

    def test_prove_finds_a_short_that_a_jumper_makes(self):
        jumpers = wiring.plan_jumpers(self.w)
        cups = next(j for j in jumpers if j.net == 'CUPS' and j.a[0] != 'N' and j.b[0] != 'N')
        vane = next(j for j in jumpers if j.net == 'VANE' and j.a[0] != 'N')
        bad = wiring.Jumper(id='WX', net='CUPS', a=cups.a, b=vane.a)
        problems = wiring.prove(self.w, jumpers + [bad])
        self.assertTrue(any('short' in p and 'CUPS' in p and 'VANE' in p for p in problems), problems)

    def test_a_full_strip_is_refused(self):
        fill = wiring.Part(id='FILL', kind='test', board='A', origin=('A', 'b', 6),
                           pins={str(i): ('A', row, 6) for i, row in enumerate('bcde')},
                           labels=(), source='passive', note='')
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(with_part(self.w, fill))
        self.assertIn('A:a-e:6', str(e.exception))

    def test_split_rails_get_a_bridge(self):
        import dataclasses
        w = dataclasses.replace(self.w, split_rails=True)
        jumpers = wiring.plan_jumpers(w)
        halves = {wiring.strip(j.a, True) for j in jumpers} | {wiring.strip(j.b, True) for j in jumpers}
        bridge = [j for j in jumpers if {wiring.strip(j.a, True), wiring.strip(j.b, True)} == {'A:L+:1', 'A:L+:2'}]
        self.assertTrue(bridge or {'A:L+:1', 'A:L+:2'} <= halves, 'both halves of the 3V3 rail are joined')
        self.assertEqual(wiring.prove(w, jumpers), [])

    def test_a_required_link_is_one_jumper(self):
        # The guide feeds the regulator's output to the NUCLEO's 3V3 pin CN7.16 (section 5).
        jumpers = wiring.plan_jumpers(self.w)
        shunt = wiring.strip(self.w.parts['SHUNT'].pins['2'])
        self.assertTrue(any({wiring.strip(j.a), wiring.strip(j.b)} == {shunt, 'N:CN7.16'} for j in jumpers))

    def test_jumpers_are_numbered_in_build_order(self):
        jumpers = wiring.plan_jumpers(self.w)
        self.assertEqual([j.id for j in jumpers], [f'W{i}' for i in range(1, len(jumpers) + 1)])
        order = [wiring.jumper_stage(j) for j in jumpers]
        self.assertEqual(order, sorted(order))


MAKE = HW/'source'/'make.py'


def build(out):
    """make.py all into out; returns the routed board's path."""
    subprocess.run([sys.executable, MAKE, 'all', '--out', out], check=True, capture_output=True, text=True)
    return Path(out)/'bench-breadboard.kicad_pcb'


@needs_kicad
class Board(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.pcb = build(Path(cls.tmp.name)/'one')
        cls.w = wiring.load(DATA)

    def test_the_routed_board_passes_drc(self):
        import json
        report = Path(self.tmp.name)/'drc.json'
        subprocess.run([ENV.cli, 'pcb', 'drc', '--format', 'json', '--severity-error', '--output', report, self.pcb],
                       check=True, capture_output=True)
        r = json.loads(report.read_text())
        self.assertEqual(r['violations'], [])
        self.assertEqual(r['unconnected_items'], [])

    def test_each_jumper_is_routed_between_its_planned_holes(self):
        import pcb_read
        copper = pcb_read.copper_by_net(self.pcb)
        for j in wiring.plan_jumpers(self.w):
            with self.subTest(jumper=j.id):
                self.assertTrue(pcb_read.joins(copper[j.id], wiring.hole_xy(j.a), wiring.hole_xy(j.b)), j)

    def test_generation_is_deterministic(self):
        again = build(Path(self.tmp.name)/'two')
        self.assertEqual(again.read_bytes(), self.pcb.read_bytes())


class Review(unittest.TestCase):
    """Findings of the final review (2026-10-19)."""
    def setUp(self):
        self.w = wiring.load(DATA)

    def test_the_build_sheet_needs_no_pillow(self):
        # CI runs the model tests without Pillow on macOS: make.py must import it only to render.
        code = (f'import sys; sys.path.insert(0, {str(HW/"source")!r}); sys.modules["PIL"] = None; '
                'import make, wiring; w = wiring.load(make.DATA); make.build_sheet(w, wiring.plan_jumpers(w))')
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])

    def test_no_jumper_lands_under_a_breakout(self):
        covered = {h for part in self.w.parts.values() for h in wiring.covered(part)}
        self.assertTrue(covered, 'the breakouts have bodies')
        ends = {h for j in wiring.plan_jumpers(self.w) for h in (j.a, j.b)}
        self.assertFalse(ends & covered, sorted(ends & covered))

    def test_a_part_under_a_breakout_is_refused(self):
        r1 = self.w.parts['R1']
        bob_body = sorted(wiring.covered(self.w.parts['BOBW']))
        free = next(h for h in bob_body if h not in set(self.w.parts['BOBW'].pins.values()) and h[1] in 'abcdefghij')
        moved = dataclasses.replace(r1, pins={'1': free, '2': r1.pins['2']})
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(with_part(self.w, moved))
        self.assertIn('under BOBW', str(e.exception))

    def test_a_signal_on_a_second_wrong_header_is_found(self):
        self.w.nets['CUPS'].append('N:CN10.31')
        problems = wiring.check_guide(self.w, GUIDE)
        self.assertTrue(any('Anemometer' in p for p in problems), problems)

    def test_a_nucleo_net_without_an_mcu_pin_is_refused(self):
        import tempfile
        text = DATA.read_text().replace('name = "CHG"\nmcu = "PB10"\n', 'name = "CHG"\n')
        with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(ValueError) as e:
            wiring.load(f.name)
        self.assertIn('CHG', str(e.exception))

    def test_the_hub_returns_straight_to_the_nucleo(self):
        # Wiring guide section 2: hub power on CN6.4 and CN6.6, not through the power board's load path.
        strips = {frozenset({wiring.strip(j.a), wiring.strip(j.b)}) for j in wiring.plan_jumpers(self.w)}
        qt = self.w.parts['QT'].pins
        self.assertIn(frozenset({wiring.strip(qt['GND']), 'N:CN6.6'}), strips)
        self.assertIn(frozenset({wiring.strip(qt['V+']), 'N:CN6.4'}), strips)


class Sheet(unittest.TestCase):
    def setUp(self):
        import make
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)
        self.sheet = make.build_sheet(self.w, self.jumpers)

    def test_the_build_sheet_lists_every_jumper_once(self):
        import make
        lines = [ln for ln in self.sheet.splitlines() if ln.startswith('| W')]
        self.assertEqual([ln.split('|')[1].strip() for ln in lines], [j.id for j in self.jumpers])
        for ln, j in zip(lines, self.jumpers, strict=True):
            self.assertIn(f'{make.where(j.a)} | {make.where(j.b)}', ln)
            self.assertIn(j.net, ln)

    def test_the_build_sheet_lists_every_bench_check(self):
        checks = self.sheet.split('## Bench checks', 1)[1]
        for part in self.w.parts.values():
            if part.source == 'bench check':
                self.assertIn(part.id, checks)
        self.assertIn('split', checks)
        self.assertIn('UM2592', checks)

    def test_the_committed_build_sheet_is_current(self):
        self.assertEqual((HW/'build-sheet.md').read_text(), self.sheet)


@needs_kicad
class Outputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)
        build(cls.out)

    def test_the_schematic_passes_erc(self):
        import json
        report = self.out/'erc.json'
        subprocess.run([ENV.cli, 'sch', 'erc', '--format', 'json', '--severity-error', '--output', report,
                        self.out/'bench-breadboard.kicad_sch'], check=True, capture_output=True)
        errors = [v for sheet in json.loads(report.read_text())['sheets'] for v in sheet['violations']]
        self.assertEqual(errors, [])

    def test_the_schematic_nets_equal_the_model(self):
        import re
        net = self.out/'n.net'
        subprocess.run([ENV.cli, 'sch', 'export', 'netlist', '--output', net, self.out/'bench-breadboard.kicad_sch'],
                       check=True, capture_output=True)
        text = net.read_text().split('(nets', 1)[1]
        got = {}
        for block in text.split('(net\n')[1:]:
            name = re.search(r'\(name "([^"]+)"\)', block)[1].lstrip('/')
            if not name.startswith('unconnected'):
                got[name] = set(re.findall(r'\(ref "([^"]+)"\)', block))
        import build_schematic
        w = wiring.load(DATA)
        want = {build_schematic.NET_POWER.get(n, n).lstrip('+'):
                {('NUCLEO' if m.startswith('N:') else m.split('.')[0]) for m in members} for n, members in w.nets.items()}
        # The meter's own switches and vane resistors are drawn across the breakout pins: not breadboard parts.
        got = {n.lstrip('+'): refs - set(build_schematic.METER) for n, refs in got.items()}
        self.assertEqual(got, want)

    def test_renders_exist_and_are_current(self):
        for name in ('board-a.png', 'board-b.png', 'board-c.png', 'overview.png', 'schematic.pdf', '3d-top.png', '3d-angle.png'):
            with self.subTest(name=name):
                self.assertTrue((self.out/'renders'/name).stat().st_size > 1000)
        for name in ('board-a.png', 'board-b.png', 'board-c.png', 'overview.png'):
            with self.subTest(current=name):
                self.assertEqual((self.out/'renders'/name).read_bytes(), (HW/'renders'/name).read_bytes())


if __name__ == '__main__':
    unittest.main()
