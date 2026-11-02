"""The bench breadboard wiring map (hardware/bench-breadboard-r0, docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md).

The model tests use only the repository Python. The KiCad tests need KiCad 10 and the pinned
KiCadRoutingTools (tools/fetch-router.sh); without them they skip and say why."""
import dataclasses
import os
import re
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
import checks  # noqa: E402
import wiring  # noqa: E402

DATA = HW/'source'/'wiring.toml'
GUIDE = ROOT/'docs'/'hardware'/'bench-station-wiring.md'
FIRMWARE = ROOT/'firmware'
APP = FIRMWARE/'stage0-node'/'App'

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
        self.assertEqual(wiring.check_firmware(self.w, FIRMWARE), [])

    def firmware_problems(self, file, edit):
        """check_firmware over a copy of the checked files, with edit(text) applied to one of them."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for name in wiring.FIRMWARE:
                (Path(tmp)/name).parent.mkdir(parents=True, exist_ok=True)
                text = (FIRMWARE/name).read_text()
                (Path(tmp)/name).write_text(edit(text) if name == file else text)
            return wiring.check_firmware(self.w, tmp)

    def test_a_moved_firmware_pin_is_found(self):
        def move(text):
            line = next(ln for ln in text.splitlines() if ln.startswith('#define RAIN_PIN'))
            return text.replace(line, re.sub(r'GPIO_PIN_\d+', 'GPIO_PIN_6', line, count=1))   # PB4 -> PB6
        problems = self.firmware_problems('stage0-node/App/board_inputs.c', move)
        self.assertTrue(any('RAIN_PIN' in p for p in problems), problems)

    def test_the_bench_link_pins_are_checked(self):
        self.assertIn('benchlink/App/benchlink.c', wiring.FIRMWARE)
        def move(text):
            line = next(ln for ln in text.splitlines() if ln.startswith('#define CHG_PIN'))
            return text.replace(line, line.replace('GPIO_PIN_10', 'GPIO_PIN_11').replace('PB10', 'PB11'))
        problems = self.firmware_problems('benchlink/App/benchlink.c', move)
        self.assertTrue(any('benchlink.c: CHG_PIN is PB11' in p for p in problems), problems)

    def test_the_oled_pins_are_checked_and_pa9_is_not(self):
        # Change C (the PA9 sensor switch) is not part of the breadboard build (record 4.6, 2026-11-02): the breadboard
        # has no SENS_EN net, so no firmware's POWER_PIN is checked against it; i2cscan's oled.c drives the
        # OLED nets the model has (record 6.3).
        for file, constants in wiring.FIRMWARE.items():
            with self.subTest(file=file):
                self.assertNotIn('POWER_PIN', constants)
        self.assertEqual(set(wiring.FIRMWARE['i2cscan/App/oled.c'].values()),
                         {'OLED_SCLK', 'OLED_DIN', 'OLED_CS', 'OLED_DC', 'OLED_RST'})
        def move_dc(text):
            line = next(ln for ln in text.splitlines() if ln.startswith('#define DC_PIN'))
            return text.replace(line, line.replace('GPIO_PIN_2', 'GPIO_PIN_3').replace('PC2', 'PC3'))
        problems = self.firmware_problems('i2cscan/App/oled.c', move_dc)
        self.assertTrue(any('oled.c: DC_PIN is PC3' in p for p in problems), problems)

    def test_pa9_keeps_its_morpho_alias_but_no_net(self):
        # Record 4.2: the PA9 tie stays in [nucleo] ties (UM2592 Tables 17, 18); PA9 is unconnected (4.6, 2026-11-02).
        self.assertIn(('CN5.2', 'CN10.19'), set(self.w.ties))
        self.assertNotIn('SENS_EN', self.w.nets)
        self.assertNotIn('PA9', self.w.mcu.values())

    def test_the_pin_comment_may_go_on(self):
        m = wiring.PIN_DEFINE.search('#define ISET_PIN GPIO_PIN_1         /* PB1 = A0, CN8.1: ADC1_IN5 */')
        self.assertEqual(m.group(1, 2, 3, 4), ('ISET_PIN', '1', 'B', '1'))
        self.assertIn('ADC1_IN5', m.group(5))
        m = wiring.PIN_DEFINE.search('#define VIN_PIN GPIO_PIN_10 /* PA10 */')
        self.assertEqual(m.group(1, 2, 3, 4), ('VIN_PIN', '10', 'A', '10'))
        m = wiring.PIN_DEFINE.search('#define SDA_PIN GPIO_PIN_11')
        self.assertEqual(m.group(1, 2, 3), ('SDA_PIN', '11', None))
        self.assertEqual(wiring.PIN_DEFINE.search('#define CHG_PIN GPIO_PIN_10 /* PB100 */').group(4), '100')   # a mismatch

    def test_a_wrong_header_or_channel_in_a_comment_is_found(self):
        def on_pgood(f):
            def edit(text):
                line = next(ln for ln in text.splitlines() if ln.startswith('#define PGOOD_PIN'))
                return text.replace(line, f(line))
            return edit
        header = on_pgood(lambda ln: ln.replace('*/', 'CN10.29 */'))   # PB5's morpho pin, not PB8's
        problems = self.firmware_problems('benchlink/App/benchlink.c', header)
        self.assertTrue(any('PGOOD_PIN says CN10.29' in p for p in problems), problems)
        channel = on_pgood(lambda ln: ln.replace('*/', 'ADC1_IN5 */'))
        problems = self.firmware_problems('benchlink/App/benchlink.c', channel)
        self.assertTrue(any('PGOOD_PIN says ADC1_IN5' in p for p in problems), problems)

    def test_an_adc_input_needs_its_channel(self):
        # UM2592 Table 17: A0 = PB1 = ADC1_IN5, A1 = PB2 = ADC1_IN4 (the vane), A2 = PA10 = ADC1_IN6.
        self.assertEqual((wiring.ADC_CHANNEL['PB1'], wiring.ADC_CHANNEL['PB2'], wiring.ADC_CHANNEL['PA10']), (5, 4, 6))
        problems = self.firmware_problems('stage0-node/App/board_inputs.c', lambda t: t.replace('ADC_CHANNEL_4', 'ADC_CHANNEL_9'))
        self.assertTrue(any('VANE_PIN is PB2 (ADC1_IN4)' in p for p in problems), problems)

    def test_a_header_the_guide_does_not_list_is_found(self):
        self.w.nets['RAIN'] = ['N:CN10.31' if m == 'N:CN8.4' else m for m in self.w.nets['RAIN']]
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
            for p, q in zip(pts, pts[1:], strict=False):   # consecutive points
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
        # The cups line's pull-up shares the jack pin's strip (record M7), so its only jumper runs to the NUCLEO:
        # take that jumper's breadboard end.
        cups = next(j for j in jumpers if j.net == 'CUPS')
        vane = next(j for j in jumpers if j.net == 'VANE' and j.a[0] != 'N')
        bad = wiring.Jumper(id='WX', net='CUPS', a=cups.a if cups.a[0] != 'N' else cups.b, b=vane.a)
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

    def test_the_required_links_are_one_jumper_each(self):
        # Record 4.4 and 6.1: the links keep stable ids; the W-numbers change on every regeneration.
        jumpers = wiring.plan_jumpers(self.w)
        pairs = {frozenset({wiring.strip(j.a), wiring.strip(j.b)}) for j in jumpers}
        self.assertEqual([k.id for k in self.w.link_info], ['LK_REG_SHUNT', 'LK_3V3_CN6_4', 'LK_QT_GND_CN6_6'])
        for link in self.w.link_info:
            with self.subTest(link=link.id):
                ends = frozenset(wiring.raw_node(self.w, e) for e in (link.a, link.b))
                self.assertIn(ends, pairs)
        self.assertEqual((self.w.link_info[0].a, self.w.link_info[0].b), ('REG.VOUT', 'SHUNT.1'))
        self.assertEqual((self.w.link_info[1].a, self.w.link_info[1].b), ('QT.V+', 'N:CN6.4'))   # as r0.2 (4.6, 2026-11-02)

    def test_no_link_or_jumper_feeds_cn7_16_from_the_shunt(self):
        # Record N3, 6.1: the SHUNT.2 -> N:CN7.16 link is gone; the mode-B feed enters at CN6.4.
        shunt = wiring.strip(self.w.parts['SHUNT'].pins['2'])
        self.assertFalse([k for k in self.w.link_info if {k.a, k.b} == {'SHUNT.2', 'N:CN7.16'}])
        self.assertFalse([j for j in wiring.plan_jumpers(self.w)
                          if {wiring.strip(j.a), wiring.strip(j.b)} == {shunt, 'N:CN7.16'}])
        feed = next(k for k in self.w.leads if k.id == 'L_REG_3V3')
        self.assertEqual(wiring.raw_node(self.w, feed.a), shunt)
        # the board-A 3V3 node: the QT.V+ strip, where LK_3V3_CN6_4 starts (record P1; 4.6, 2026-11-02)
        self.assertEqual(wiring.raw_node(self.w, feed.b), wiring.raw_node(self.w, 'QT.V+'))
        self.assertIn('A:L+', self.w.rails['3V3'])

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
        # Change C (the load switch) is not part of the breadboard build (record 4.6, 2026-11-02): CN6.4 feeds the hub's V+.
        strips = {frozenset({wiring.strip(j.a), wiring.strip(j.b)}) for j in wiring.plan_jumpers(self.w)}
        qt = self.w.parts['QT'].pins
        self.assertIn(frozenset({wiring.strip(qt['GND']), 'N:CN6.6'}), strips)
        self.assertIn(frozenset({wiring.strip(qt['V+']), 'N:CN6.4'}), strips)
        # Record P4, D2: the hub's ground is logic ground. It reaches the power domain (STAR, the pack's
        # minus, the charger's sockets) only through L_TIE: without the TIE the two are apart.
        jumpers = wiring.plan_jumpers(self.w)
        power = {'J:WAGO_STAR', 'PACK.-', 'CHGR.BATT1', 'RLOAD.2'}
        with_tie = next(g for g in wiring.connectivity(self.w, jumpers) if 'QT.GND' in g)
        self.assertTrue(power <= with_tie)
        no_tie = dataclasses.replace(self.w, leads=tuple(k for k in self.w.leads if k.id != 'L_TIE'))
        hub = next(g for g in wiring.connectivity(no_tie, jumpers) if 'QT.GND' in g)
        self.assertFalse(power & hub)
        self.assertTrue({'N:CN6.6', 'N:CN6.7', 'N:CN10.20', 'REG.GND', 'OLED.GND'} <= hub)

# A lead in the change-A schema (record D2): into the BATT joint's spare position, from the INA228's
# VIN- screw terminal, in parallel with the model's own L_INA_BATT.
LEAD = '''
[[lead]]
id = "L_TEST"
a = "INA.X1_VINM"
b = "J:WAGO_BATT.3"
role = "force"
kind = "solid"
gauge = 22
length_mm = 50
note = "test"
'''


def load_text(test, text):
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False) as f:
        f.write(text)
    test.addCleanup(os.unlink, f.name)
    return wiring.load(f.name)


def with_extra(test, extra):
    """The model loaded from wiring.toml with extra TOML appended."""
    return load_text(test, DATA.read_text() + extra)


def model_lead(w, lead_id):
    return next(k for k in w.leads if k.id == lead_id)


def without_leads(w, *ids):
    return dataclasses.replace(w, leads=tuple(k for k in w.leads if k.id not in ids))


class Leads(unittest.TestCase):
    """Leads off the breadboard (record D2): no strip, no hole, unless an end names one."""

    def setUp(self):
        self.w = wiring.load(DATA)

    def test_a_lead_is_parsed(self):
        lead = model_lead(with_extra(self, LEAD), 'L_TEST')
        self.assertEqual(lead, wiring.Lead(id='L_TEST', net='BATT', a='INA.X1_VINM', b='J:WAGO_BATT.3', gauge=22,
                                           length_mm=50.0, note='test', role='force', kind='solid'))
        self.assertEqual(model_lead(self.w, 'L_INA_BATT').net, 'BATT')

    def test_a_lead_joins_its_net_without_a_jumper(self):
        jumpers = wiring.plan_jumpers(self.w)
        self.assertFalse([j for j in jumpers if j.net in ('CELL_POS', 'BATT', 'SYS_OUT')])
        self.assertEqual(wiring.prove(self.w, jumpers), [])
        # Without the lead the same jumpers leave the net open: the proof counts the lead.
        problems = wiring.prove(without_leads(self.w, 'L_INA_BATT'), jumpers)
        self.assertIn('open: BATT is in 2 pieces', problems)

    def test_a_lead_needs_no_free_hole(self):
        # A terminal or a joint end is a node of its own; only a hole or a NUCLEO end reserves a hole.
        lead = model_lead(self.w, 'L_INA_BATT')
        self.assertEqual((wiring.raw_node(self.w, lead.a), wiring.raw_node(self.w, lead.b)),
                         ('T:INA.X1_VINM', 'J:WAGO_BATT'))
        holes = wiring.lead_holes(self.w)
        self.assertIn(('B', 'b', 15), holes)           # L_REG_VIN into the regulator VIN strip
        self.assertIn(('N', 'CN6', 7), holes)          # L_NUC_RET
        ends = {h for j in wiring.plan_jumpers(self.w) for h in (j.a, j.b)}
        self.assertFalse(ends & holes)

    def test_a_bad_lead_is_refused(self):
        for extra, why in ((LEAD.replace('J:WAGO_BATT.3', 'CHGR.OUT'), 'not two members of one net'),
                           (LEAD.replace('gauge = 22', 'gauge = 40'), 'gauge 40'),
                           (LEAD.replace('length_mm = 50', 'length_mm = 0'), 'length_mm 0'),
                           (LEAD.replace('J:WAGO_BATT.3', 'J:WAGO_BATT.4'), 'positions 1 to 3'),
                           # a NUCLEO pin is a valid end (record D2); one of another net is not
                           (LEAD.replace('"INA.X1_VINM"', '"N:CN6.4"'), 'not two members of one net')):
            with self.subTest(why=why), self.assertRaises(ValueError) as e:
                with_extra(self, extra)
            self.assertIn(why, str(e.exception))

    def test_the_build_sheet_lists_leads_apart_from_jumpers(self):
        import make
        sheet = make.build_sheet(self.w, wiring.plan_jumpers(self.w))
        jumpers, leads = sheet.split('## 2. Jumpers', 1)[1].split('## 3. Leads', 1)
        for lead in self.w.leads:
            with self.subTest(lead=lead.id):
                self.assertNotIn(f'| {lead.id} |', jumpers)
                self.assertEqual(leads.count(f'| {lead.id} |'), 1)
        bare = without_leads(self.w, *[k.id for k in self.w.leads])
        self.assertNotIn('## 3. Leads', make.build_sheet(bare, []))

    def test_the_layout_draws_a_lead_end_to_end(self):
        import make
        lay = make.layout(self.w, wiring.plan_jumpers(self.w))
        lead = next(k for k in lay['leads'] if k['id'] == 'L_INA_BATT')
        self.assertEqual((lead['class'], lead['gauge']), ('battery lead', 22))
        self.assertEqual(lead['a'], list(wiring.end_xy(self.w, 'INA.X1_VINM')))
        self.assertEqual(lead['b'], list(wiring.end_xy(self.w, 'J:WAGO_BATT.1')))

    def test_the_schematic_notes_a_lead_without_a_kicad(self):
        import make
        sch = '(kicad_sch (paper "A3")\n(text "x" (at 25.4 20.0 0))\n(sheet_instances (path "/" (page "1"))))\n'
        bare = dataclasses.replace(without_leads(self.w, *[k.id for k in self.w.leads]), joints={})
        self.assertEqual(make.lead_notes(bare, sch), sch)
        noted = make.lead_notes(self.w, sch)   # a table row per lead and per joint, cell by cell
        for lead in self.w.leads:
            with self.subTest(lead=lead.id):
                self.assertEqual(noted.count(f'(text "{lead.id}" '), 1)
        for cell in ('22 AWG solid', '50 mm', 'J:WAGO_BATT.1', 'WAGO 222-413', '26 AWG pigtail, one end insulated'):
            self.assertIn(f'(text "{cell}" ', noted)
        self.assertIn('(text "1: L_INA_BATT; 2: L_BATT_POS; 3: spare" ', noted)
        self.assertTrue(noted.endswith('(sheet_instances (path "/" (page "1"))))\n'))
        # No lead limit: the table grows with the model, and the paper with the table.
        lead = model_lead(self.w, 'L_INA_BATT')
        many = tuple(dataclasses.replace(lead, id=f'L{i}') for i in range(120))
        big = make.lead_notes(dataclasses.replace(self.w, leads=many), sch)
        self.assertEqual(big.count('(text "L119" '), 1)
        self.assertNotIn('(paper "A3")', big)

    def test_the_table_sits_under_the_circuits_on_a_paper_that_holds_it(self):
        import make
        sch = ('(kicad_sch (paper "A3")\n(wire (pts (xy 10 10) (xy 300 200)))\n'
               '(sheet_instances (path "/" (page "1"))))\n')
        noted = make.lead_notes(self.w, sch)
        tops = [float(y) for y in re.findall(r'\(text "[^"]*" \(at [-\d.]+ ([-\d.]+)', noted)]
        self.assertGreater(min(tops), 200 + make.LEAD_NOTES[1] - 0.01)
        right, bottom = make.drawn_extent(noted)
        paper = re.search(r'\(paper "([^"]+)"\)', noted)[1]
        name, width, height = next(p for p in make.PAPERS if p[0] == paper)
        self.assertLessEqual((right, bottom), (width - make.PAGE_FRAME, height - make.PAGE_FRAME))
        with self.assertRaises(ValueError):
            make.paper_for([(0.0, 0.0, 5000.0, 10.0)])

    @needs_kicad
    def test_the_schematic_notes_a_lead_in_free_space_and_passes_erc(self):
        import re
        import tempfile

        import build_schematic
        import make
        w = wiring.load(DATA)   # the model's own leads and joints
        sch = make.lead_notes(w, build_schematic.schematic(w))
        self.assertIn('(text "100 mm" ', sch)
        # The table sits below everything build_schematic draws.
        _right, lowest = make.drawn_extent(build_schematic.schematic(w))
        first = min(float(y) for y in re.findall(r'\(at [-\d.]+ ([-\d.]+) 0\)', sch[sch.rindex('(text "Leads off'):]))
        self.assertGreater(first, lowest + make.LEAD_NOTES[1] - 1.3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'lead.kicad_sch'
            path.write_text(sch)
            subprocess.run([ENV.cli, 'sch', 'erc', '--format', 'json', '--severity-error', '--exit-code-violations',
                            '--output', Path(tmp)/'erc.json', path], capture_output=True, check=True)

    def test_the_3d_lead_is_thicker_than_a_jumper(self):
        import tempfile

        import models
        self.assertGreater(models.lead_radius(18), models.WIRE_R)
        self.assertGreater(models.lead_radius(16), models.lead_radius(18))
        with tempfile.TemporaryDirectory() as tmp:
            models.write_lead(Path(tmp)/'l.wrl', (0.0, 0.0), (10.0, 0.0), 18, (0.5, 0.3, 0.1))
            self.assertTrue((Path(tmp)/'l.wrl').read_text().startswith('#VRML V2.0 utf8'))
            # A joint end stops on the lever connector's top, a NUCLEO end on the header pin; an insulated
            # end has no leg, only its sleeve.
            z = (models.END_Z['joint'], models.END_Z['nucleo'])
            models.write_lead(Path(tmp)/'j.wrl', (0.0, 0.0), (10.0, 0.0), 22, (0.5, 0.3, 0.1), z)
            text = (Path(tmp)/'j.wrl').read_text()
            self.assertIn(f'{models.JOINT_H/2.54:.4f}', text)
            models.write_lead(Path(tmp)/'i.wrl', (0.0, 0.0), (10.0, 0.0), 26, (0.5, 0.3, 0.1), insulated=('b',))
            self.assertIn(' '.join(str(c) for c in models.SLEEVE), (Path(tmp)/'i.wrl').read_text())


class Drawings(unittest.TestCase):
    """The drawing side of change A (record D2, D4, 6.1): joints, places, roles, the 3D boxes."""

    def setUp(self):
        self.w = wiring.load(DATA)

    def test_the_layout_emits_every_joint_lead_and_the_model_hash(self):
        import checklist
        import make
        lay = make.layout(self.w, wiring.plan_jumpers(self.w))
        self.assertEqual(lay['model_hash'], checklist.blob_sha1(DATA))
        self.assertEqual([j['id'] for j in lay['joints']], list(self.w.joints))
        self.assertEqual([k['id'] for k in lay['leads']], [k.id for k in self.w.leads])
        for j in lay['joints']:
            joint = self.w.joints[j['id']]
            with self.subTest(joint=joint.id):
                self.assertEqual((j['kind'], j['positions'], j['place_mm']), (joint.kind, joint.positions,
                                                                              list(joint.place_mm)))
                self.assertEqual(j['xy'], [list(wiring.end_xy(self.w, f'J:{joint.id}.{n}'))
                                           for n in range(1, joint.positions + 1)])
        for k in lay['leads']:
            lead = model_lead(self.w, k['id'])
            with self.subTest(lead=lead.id):
                self.assertEqual((k['role'], k['kind'], k['gauge'], k['insulated']),
                                 (lead.role, lead.kind, lead.gauge, lead.insulated))
                for side, end in (('a', lead.a), ('b', lead.b)):
                    kind = wiring.parse_end(self.w, end)[0]
                    if kind == 'nucleo':
                        self.assertEqual(k[side], list(wiring.hole_xy(wiring.member_hole(self.w, end))))
                    elif kind != 'insulated':
                        self.assertEqual(k[side], list(wiring.end_xy(self.w, end)))
                self.assertEqual(k['a_end'] == 'insulated' or k['b_end'] == 'insulated', lead.insulated)
        # The outline holds every joint and every part off the breadboard; those parts are at place_mm.
        x1, y1, x2, y2 = lay['outline']
        for r in [j['box'] for j in lay['joints']] + [p['box'] for p in lay['parts'] if p['place_mm']]:
            self.assertTrue(x1 <= r[0] and y1 <= r[1] and r[2] <= x2 and r[3] <= y2, r)
        pack = next(p for p in lay['parts'] if p['id'] == 'PACK')
        self.assertEqual(pack['pins']['+'], list(wiring.end_xy(self.w, 'PACK.+')))

    def test_no_footprint_needs_a_hole_for_a_placed_part(self):
        import make
        refs = {m['ref'] for m in make.model_footprints(self.w)}
        for joint in self.w.joints:
            self.assertIn(f'3D_{joint}_0', refs)
        self.assertTrue(any(r.startswith('3D_PACK') for r in refs))
        self.assertTrue(any(r.startswith('3D_RLOAD') for r in refs))

    def test_a_force_lead_is_drawn_wider_than_a_sense_lead(self):
        try:
            import render
        except ImportError:
            self.skipTest('Pillow is not installed')
        import build_schematic
        self.assertGreater(render.lead_width('force'), render.lead_width('signal'))
        self.assertEqual(render.lead_width('signal'), render.lead_width('supply'))
        self.assertGreater(render.lead_width('supply'), render.lead_width('sense'))
        self.assertEqual(set(render.LEAD_WIDTH), set(wiring.ROLES))
        stroke = build_schematic.LEAD_STROKE
        self.assertGreater(stroke['force'], stroke['signal'])
        self.assertGreater(stroke['supply'], stroke['sense'])

    def test_the_wago_and_generic_breakout_boxes(self):
        import models
        for joint in self.w.joints.values():
            boxes = models.joint_boxes(joint, wiring.JOINT_PITCH)
            self.assertEqual(boxes[0][2], joint.positions*wiring.JOINT_PITCH)
        bad = dataclasses.replace(next(iter(self.w.joints.values())), kind='WAGO 221-415')
        with self.assertRaises(ValueError):
            models.joint_boxes(bad, wiring.JOINT_PITCH)
        # A breakout with no maker model and no colour of its own (a later part) is a generic board.
        later = dataclasses.replace(self.w.parts['REG'], id='XBRK', kind='a later breakout')
        boxes = [b for _f, _r, b in models.models_for(later) if b]
        self.assertEqual(boxes[0][6], models.GENERIC_BOARD)

    def test_no_cell_part_is_left_in_the_drawing_code(self):
        # The pack is PACK (record 6.1): CELL+ names the clamp, CELL_POS the net; a bare CELL is the old part.
        for path in sorted((HW/'source').glob('*.py')) + [HW/'source'/'wiring.toml']:
            with self.subTest(file=path.name):
                self.assertEqual(re.findall(r'\bCELL\b(?!\+)', path.read_text()), [])


class Nucleo(unittest.TestCase):
    """CN8 (ARDUINO A0-A5) and room for the flying jumpers (spec 2026-10-29 section 11.1)."""

    def test_cn8_is_a_female_single_row_of_six(self):
        self.assertEqual(wiring.HEADERS['CN8'][1:], (1, 6))
        self.assertIn('CN8', wiring.FEMALE)
        holes = [wiring.hole_xy(('N', 'CN8', pin)) for pin in range(1, 7)]
        self.assertEqual(len({x for x, _y in holes}), 1)
        self.assertEqual([round(y - holes[0][1], 4) for _x, y in holes], [round(i*wiring.PITCH, 4) for i in range(6)])
        with self.assertRaises(ValueError):
            wiring.hole_xy(('N', 'CN8', 7))
        others = {wiring.hole_xy(('N', h, p)) for h, (_x, _c, n) in wiring.HEADERS.items() if h != 'CN8' for p in range(1, n + 1)}
        self.assertFalse(set(holes) & others)

    def test_cn8_is_labelled(self):
        import make
        lay = make.layout(*make.checked())
        self.assertIn('CN8', [t['text'] for t in lay['labels']])
        self.assertIn('CN8.1', [h['name'] for f in lay['footprints'] if f['ref'] == 'NUCLEO' for h in f['holes']])

    def test_there_is_room_for_twenty_flying_jumpers(self):
        self.assertGreaterEqual(flying.lane_capacity(), 20)
        jumpers = [wiring.Jumper(id=f'W{i}', net='X', a=('A', 'j', i + 1), b=('N', 'CN10', i + 1))
                   for i in range(flying.lane_capacity() + 1)]
        self.assertEqual(len(flying.plan(jumpers[:-1])), flying.lane_capacity())
        with self.assertRaises(ValueError):
            flying.plan(jumpers)


class Classes(unittest.TestCase):
    def test_every_class_has_a_colour_and_a_name(self):
        try:
            import render
        except ImportError:
            self.skipTest('Pillow is not installed')
        self.assertEqual(set(render.COLOURS), set(wiring.NET_CLASSES))
        self.assertTrue({'analog', 'battery lead'} <= set(wiring.NET_CLASSES))

    def test_the_build_sheet_names_every_class_colour(self):
        import make
        w = wiring.load(DATA)
        sheet = make.build_sheet(w, wiring.plan_jumpers(w))
        for cls, colour in wiring.NET_CLASSES.items():
            self.assertIn(f'{cls} {colour}', sheet)

    def test_an_unknown_class_is_refused(self):
        with self.assertRaises(ValueError) as e:
            with_extra(self, '\n[[net]]\nname = "X"\nclass = "mystery"\nmembers = ["R1.1"]\n')
        self.assertIn('mystery', str(e.exception))


class KitLengths(unittest.TestCase):
    """The build sheet's Length column (make.kit_length): the BOJACK kit size for a span, the next size up
    for a diagonal, 'cut to fit' when that size would bow off the board, and the NUCLEO jumpers by kind."""

    def length(self, a, b):
        import make
        return make.kit_length(wiring.Jumper(id='W0', net='X', a=a, b=b))

    def test_a_straight_span_takes_its_own_size(self):
        self.assertEqual(self.length(('A', 'b', 5), ('A', 'b', 4)), '2 mm')      # 1 hole
        self.assertEqual(self.length(('B', 'b', 17), ('B', 'b', 8)), '22 mm')    # 9 holes
        self.assertEqual(self.length(('A', 'c', 30), ('A', 'c', 10)), '50 mm')   # 20 holes

    def test_a_diagonal_takes_the_next_size_up(self):
        self.assertEqual(self.length(('A', 'L-', 20), ('A', 'b', 14)), '17 mm')

    def test_a_span_with_no_size_close_above_is_cut(self):
        self.assertEqual(self.length(('A', 'd', 19), ('A', 'd', 2)), 'cut to fit: 17.0 holes (43 mm between the legs)')
        self.assertTrue(self.length(('A', 'c', 63), ('A', 'c', 1)).startswith('cut to fit: 62.0 holes'))

    def test_a_jumper_across_boards_has_no_kit_length(self):
        with self.assertRaisesRegex(ValueError, 'joins boards A and B'):
            self.length(('A', 'b', 5), ('B', 'b', 5))

    def test_nucleo_jumpers_say_what_they_are(self):
        self.assertEqual(self.length(('A', 'e', 41), ('N', 'CN6', 4)), 'cut to fit from 22 AWG solid')
        self.assertEqual(self.length(('C', 'e', 36), ('N', 'CN10', 17)), 'Dupont, about 30 cm')

    def test_the_cut_list_counts_every_jumper(self):
        import make
        jumpers = wiring.plan_jumpers(wiring.load(DATA))
        rows = [r for r in make.cut_list(jumpers) if re.match(r'^\| [^L-]', r)]
        self.assertEqual(sum(int(r.rsplit('|', 2)[1]) for r in rows), len(jumpers))


class Homes(unittest.TestCase):
    """Sections 0a and 0b: the teardown and every part's home, in the current sheet only."""

    def setUp(self):
        import make
        self.make = make
        self.w = wiring.load(DATA)

    def test_every_off_board_part_and_joint_has_a_plate_home(self):
        rows = '\n'.join(self.make.homes_rows(self.w))
        for part in self.w.parts.values():
            self.assertIn(f'| {part.id} (', rows)
            if part.place_mm:
                self.assertIn(self.make.PLATE_HOMES[part.id], rows)
            else:
                self.assertIn(f'| breadboard {part.board} (section 1) |', rows)
        for joint in self.w.joints:
            self.assertIn(f'| {joint} (', rows)
        for what in ('NUCLEO TX', 'NUCLEO RX', 'STEMMA QT hub'):
            self.assertIn(what, rows)

    def test_an_off_board_part_without_a_home_stops_the_sheet(self):
        with mock.patch.dict(self.make.PLATE_HOMES, clear=True):
            with self.assertRaisesRegex(ValueError, 'no base plate home'):
                self.make.homes_rows(self.w)

    def test_teardown_starts_with_the_power_off_and_the_pack_apart(self):
        sheet = self.make.build_sheet(self.w, wiring.plan_jumpers(self.w))
        teardown = sheet.split('## 0a. Teardown', 1)[1].split('\n## ', 1)[0]
        self.assertLess(teardown.index('Power off'), teardown.index('The pack'))
        self.assertLess(teardown.index('The pack'), teardown.index('The jumpers'))
        self.assertIn('## 0b. Homes', sheet)
        for lead in ('X1 screws', 'adapter cable', 'NTC pair'):
            self.assertIn(lead, teardown)

    def test_the_frozen_sheets_have_no_teardown_or_homes(self):
        for rev in ('bench-bb-r0.1', 'bench-bb-r0.2'):
            sheet = (HW/'revisions'/rev/'build-sheet.md').read_text()
            self.assertNotIn('## 0a. Teardown', sheet)
            self.assertNotIn('## 0b. Homes', sheet)


class Sheet(unittest.TestCase):
    def setUp(self):
        import make
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)
        self.sheet = make.build_sheet(self.w, self.jumpers)

    def test_the_build_sheet_lists_every_jumper_once(self):
        import make
        lines = [ln for ln in self.sheet.splitlines() if re.match(r'^\| W\d+ \|', ln)]
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
        """`make.py sheet`'s own code path (write_sheets) beside a copy of the committed layout.json: the sheets
        and connections.json it writes, the current revision's and each frozen revision's under revisions/,
        equal the committed ones (record D4, 6.1)."""
        import shutil
        import tempfile

        import make
        with tempfile.TemporaryDirectory() as tmp:
            if (HW/'layout.json').exists():
                shutil.copy(HW/'layout.json', Path(tmp)/'layout.json')
            make.write_sheets(tmp)
            for rel in ('', *(f'revisions/{r}/' for r in make.HISTORY)):
                for name in ('build-sheet.md', make.CONNECTIONS):
                    with self.subTest(file=rel + name):
                        self.assertEqual((HW/rel/name).read_text(), (Path(tmp)/rel/name).read_text())
        self.assertEqual((HW/'build-sheet.md').read_text(), self.sheet)   # build_sheet's default: the committed tree


class PhaseAPower(unittest.TestCase):
    """The power checks the build sheet carries (record 4.3; spec 2026-10-29 sections 11.1 to 11.3)."""

    def setUp(self):
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)

    def test_the_firmware_reads_iset_and_vin_on_their_adc_channels(self):
        for file in ('stage0-node/App/board_inputs.c', 'benchlink/App/benchlink.c'):
            self.assertEqual((wiring.FIRMWARE[file]['ISET_PIN'], wiring.FIRMWARE[file]['VIN_PIN']), ('ISET', 'VIN_SENSE'))
        self.assertTrue({'ISET', 'VIN_SENSE'} <= set(wiring.ADC_NETS))
        problems = Checks.firmware_problems(self, 'stage0-node/App/board_inputs.c',
                                            lambda t: t.replace('ADC_CHANNEL_5,', 'ADC_CHANNEL_7,'))
        self.assertTrue(any('ISET_PIN is PB1 (ADC1_IN5)' in p for p in problems), problems)
        problems = Checks.firmware_problems(self, 'benchlink/App/benchlink.c',
                                            lambda t: t.replace('pin_uv(ADC_CHANNEL_6,', 'pin_uv(ADC_CHANNEL_7,'))
        self.assertTrue(any('VIN_PIN is PA10 (ADC1_IN6)' in p for p in problems), problems)

    def test_the_build_sheet_has_power_checks_1_to_10(self):
        import make
        sheet = make.build_sheet(self.w, self.jumpers)
        self.assertNotIn('up to about 5 V', sheet)
        self.assertNotIn('5 V tolerant (FT)', sheet)
        checks = sheet.split('## Power checks', 1)[1]
        for n in range(1, 11):
            self.assertIn(f'\n{n}. **', checks)
        for text in ('SLUS810 section 9.3.5.1', '+-10 %', 'never an ohm range', '0.375 V', 'min(VDD, VDDA) + 0.3 V',
                     'at most 75 mOhm', 'at most 40 mOhm', 'within 10 mV', '4.3-4.5 V', 'at least 100 mV', 'not flashing',
                     'TMR reads 0 ohm to GND', '0.20-0.40 A', 'no RTMR is fitted (record P9)'):
            self.assertIn(text, checks)
        self.assertNotIn('at most 50 mV', checks)   # the old loop budget (spec section 11.2, amended 2026-10-29)
        self.assertNotIn('whole loop', sheet)
        self.assertNotIn('RTMR = 72', sheet)        # record P9: TMR is tied to GND; no RTMR is fitted

    def test_the_build_sheet_has_phase_b_checks(self):
        """Phase B (spec section 11.3, power-metering.md): the rail shunts are verified like check 3, EN2 high
        with EN1 low is recorded, and every rail address of power_config.h is named."""
        import make
        checks = make.build_sheet(self.w, self.jumpers).split('## Step 1b power checks', 1)[1]
        for n in range(1, 7):
            self.assertIn(f'\nB{n}. **', checks)
        cfg = (ROOT/'firmware/stage0-node/App/power_config.h').read_text()
        for name in ('LOAD', 'SOLAR', 'USB'):
            addr = re.search(rf'#define POWER_ADDR_{name}\s+(0x[0-9A-F]+)U', cfg).group(1)
            self.assertIn(addr.lower(), checks.lower())
        for text in ('EN2 high and EN1 low', 'standby', 'within 2 % + 2 mA', 'POWER_SHUNT_UOHM_LOAD', '0.97 kOhm',
                     'never solar and USB-C together', 'section 5.4'):
            self.assertIn(text, checks)

    def test_the_step_1b_checks_follow_the_record(self):
        # Record S1 (on the breadboard build), P10 (no fallback join), step 1b exits (e) and
        # (f), 7.1 Q1 (the 0x48 ADDR1-to-SDA wire is allowed module preparation).
        import make
        checks = make.build_sheet(self.w, self.jumpers).split('## Step 1b power checks', 1)[1]
        self.assertIn("Step 1b, on the breadboard build (record S1)",
                      checks)
        self.assertNotIn('fallback', checks)
        b = {ln.split('.', 1)[0]: ln for ln in checks.splitlines() if re.match(r'^B\d\. ', ln)}
        self.assertIn('2.8 V', b['B4'])
        self.assertIn('0.97 kOhm', b['B4'])
        self.assertIn('ADDR1-to-SDA wire, allowed', b['B2'])
        self.assertIn('7.1 Q1', b['B2'])
        self.assertEqual(b['B5'].count('|I| <= 1 mA'), 2)
        self.assertEqual(b['B5'].count('<= 0.5 V'), 2)
        self.assertIn('10 kOhm test load', b['B5'])


class SheetTier(unittest.TestCase):
    """`make.py sheet` (record D4): no KiCad, the D3 checks in checked(), the revision and both hashes, the
    changes section against the previous revision (6.1, 4.4), and the sheet's content (6.1 make.py row)."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        import make
        cls.make = make
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)/'sheet'
        make.main(['sheet', '--out', str(cls.out)])
        cls.sheet = (cls.out/'build-sheet.md').read_text()
        cls.w = wiring.load(DATA)

    def section(self, title):
        return self.sheet.split(f'\n## {title}', 1)[1].split('\n## ', 1)[0]

    def test_sheet_runs_without_kicad(self):
        out = Path(self.tmp.name)/'no-kicad'
        code = (f'import sys; sys.modules["kicad_env"] = None; sys.modules["pcbnew"] = None; sys.modules["PIL"] = None; '
                f'sys.path.insert(0, {str(HW/"source")!r}); import make; assert make.kicad_env is None; '
                f'make.main(["sheet", "--out", {str(out)!r}])')
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual((out/'build-sheet.md').read_text(), self.sheet)
        self.assertTrue((out/'connections.json').exists())

    def test_all_without_kicad_says_so(self):
        with mock.patch.object(self.make, 'kicad_env', None), self.assertRaises(SystemExit) as e:
            self.make.main(['all', '--out', str(Path(self.tmp.name)/'none')])
        self.assertIn('`sheet` does not', str(e.exception))

    def test_checked_runs_the_d3_checks_and_the_guide_both_ways(self):
        for target, problem in ((checks, 'run_all'), (wiring, 'check_guide_reverse')):
            with self.subTest(check=problem), mock.patch.object(target, problem, return_value=[f'{problem} broke']):
                with self.assertRaises(SystemExit) as e:
                    self.make.checked()
                self.assertIn(f'{problem} broke', str(e.exception))

    def test_the_sheet_carries_the_revision_and_both_hashes(self):
        import checklist
        model = checklist.blob_sha1(DATA)
        head = self.sheet.split('\n## ', 1)[0]
        self.assertIn(f'| Revision | {self.w.revision} |', head)
        self.assertTrue(self.w.revision.startswith('bench-bb-r0.'))
        self.assertIn(f'`{model}`', head)
        self.assertIn('renders predate hashing', head)   # no layout.json in the output directory
        jumpers = wiring.plan_jumpers(self.w)
        for drawn, lag in ((model, False), ('0' * 40, True)):
            with self.subTest(drawn=drawn):
                out = Path(self.tmp.name)/f'hash-{drawn[:4]}'
                out.mkdir()
                (out/'layout.json').write_text(f'{{"model_hash": "{drawn}"}}')
                sheet = self.make.build_sheet(self.w, jumpers, out).split('\n## ', 1)[0]
                self.assertIn(f'| Renders (`layout.json` model_hash) | `{drawn}` |', sheet)
                self.assertEqual('Renders lag the model' in sheet, lag)

    def test_every_joint_and_lead_appears_once(self):
        rows = [ln.split('|')[1].strip() for ln in self.sheet.splitlines() if ln.startswith('| ')]
        self.assertTrue(self.w.joints and self.w.leads)
        for name in [*self.w.joints, *(k.id for k in self.w.leads)]:
            with self.subTest(name=name):
                self.assertEqual(rows.count(name), 1)
        joints = self.section('4. Joints')
        self.assertIn('| WAGO_STAR | WAGO 222-415 | GND | 1: L_PACK_NEG; 2: L_BATT_NEG; 3: L_RLOAD_B; 4: L_TIE; 5: spare |',
                      joints)
        lead = next(ln for ln in self.section('3. Leads').splitlines() if ln.startswith('| L_TIE |'))
        for cell in ('force', '22 AWG solid', '100 mm', 'J:WAGO_STAR.4', 'B:b16', 'P1 regulator'):
            self.assertIn(cell, lead)

    def test_the_power_path_table(self):
        import checklist
        path = self.section('5. Power path')
        self.assertIn(f'Coverage: {checklist.COVERAGE_NOTE}.', path)
        rows = {ln.split('|')[1].strip(): ln for ln in path.splitlines() if ln.startswith('| ')}
        self.assertIn('R_pack', rows)
        self.assertIn('| 56 |', rows['R_pack'])
        for seg, budget in checklist.BUDGETS.items():
            with self.subTest(segment=seg):   # the budget, the implied mV at 38 mA and at 1 A
                self.assertIn(f'| {budget:g} | {budget*0.038:.2f} | {budget:g} |', rows[seg])
        self.assertIn('flag: drop - dV0 > 20 mV', rows['PATH_CELL_OUT'])

    def test_the_checklist_c1_to_c23(self):
        import checklist
        section = self.section('6. Pre-run checklist (C1-C23)')
        self.assertIn(checklist.METER, section)
        self.assertIn('Fluke 87V', section)
        mode_b = section.split('### Mode B', 1)[1]
        for n in range(1, 24):
            with self.subTest(row=f'C{n}'):
                self.assertEqual(sum(ln.startswith(f'| C{n} |') for ln in section.splitlines()), 1)
        for cid in ('C15', 'C20', 'C21', 'C22', 'C23'):
            self.assertIn(f'| {cid} |', mode_b)

    def test_no_old_meter_range_and_no_soldered_lead(self):
        # Only module preparation (record H5, 7.1 Q6), the breakouts' solder jumpers and "no solder" may say it.
        self.assertNotIn('200 mV', self.sheet)
        for text in ('solder pad', 'soldered', 'CE, ISET and THERM stay unconnected', 'up to about 5 V', 'W-number '):
            self.assertNotIn(text, self.sheet)
        for line in self.sheet.splitlines():
            if 'solder' in line.lower():
                with self.subTest(line=line[:80]):
                    self.assertTrue(any(ok in line.lower() for ok in ('solder jumper', 'no solder', 'module preparation')))

    def test_the_power_checks_stay_numbered(self):
        # About 21 documents cite "build-sheet check N": 1-10 keep their numbers and order.
        checks_ = self.section('Power checks')
        starts = [checks_.index(f'\n{n}. **') for n in range(1, 11)]
        self.assertEqual(starts, sorted(starts))
        line = {n: next(ln for ln in checks_.splitlines() if ln.startswith(f'{n}. **')) for n in range(1, 11)}
        self.assertIn('R9, 1 kOhm expected (POWER_R_ISET_OHM 1000)', line[2])
        self.assertIn('the L_VBUS sense lead into the OUT joint', line[1])
        self.assertIn('x the measured ratio (POWER_VIN_DIVIDER_PPM / 1e6', line[4])
        self.assertIn('within 1 %', line[4])
        for header in ('CN9.7', 'alias CN10.25', 'CN9.6', 'alias CN10.27', '2.9 V', 'VDD + 0.3 V'):
            self.assertIn(header, line[6])
        for text in ('the CELL+ clamp to the STAR clamp', 'I x R_pack + 10 mV', 'at the pack plug'):
            self.assertIn(text, line[8])

    def test_the_modes_the_no_5v_list_and_the_bob_preparation(self):
        modes = self.section('7. Mode A and mode B')
        for text in ("1. Unplug the NUCLEO's USB.", 'Open the load\'s two levers', "Unplug the OLED's VCC lead (L_OLED_VCC) "
                     'from CN7.16', 'Fit the BATTERY POWER shunt', 'the shunt out before the USB goes in',
                     'The TIE (L_TIE) and the CN6.7 lead (L_NUC_RET) never move', 'never touches ground'):
            self.assertIn(text, modes)
        bench = self.section('Bench checks')
        no_5v = next(ln for ln in bench.splitlines() if 'NO 5V' in ln)
        for pin in ('CN6.5', 'CN6.8', 'CN7.18', 'CN7.24', 'CN7.6', 'CN10.8'):
            self.assertIn(pin, no_5v)
        self.assertIn("In mode B unplug the OLED's VCC lead from CN7.16", bench)
        self.assertIn('**BOB-14021 preparation** (module preparation, record H5, 7.1 Q6)', bench)
        self.assertIn('per-conductor continuity check', bench)
        cn = next(ln for ln in bench.splitlines() if ln.startswith('- **CN5 (D8-D15), CN8 (A0-A5) and CN9 (D0-D7):**'))
        for pin in ('CN8.1 (A0, PB1, ISET)', 'CN8.3 (A2, PA10, VIN_SENSE)', 'CN9.7 (D6, PB10, CHG)', 'CN9.6 (D5, PB8, PGOOD)',
                    'CN5.9 (D14, PA11, I2C_SDA)', 'CN5.10 (D15, PA12, I2C_SCL)'):
            self.assertIn(pin, cn)
        aliases = cn.split('The morpho aliases of these pins (', 1)[1].split(')', 1)[0].split(', ')
        for pin in ('CN10.5', 'CN10.3', 'CN10.25', 'CN7.28'):
            self.assertIn(pin, aliases)
        self.assertNotIn('CN5.2', cn)   # PA9: change C is not built (record 4.6, 2026-11-02)
        self.assertNotIn('CN10.19', aliases)
        oled = next(ln for ln in bench.splitlines() if ln.startswith('- **OLED wires:**'))
        self.assertIn('Their ARDUINO aliases (CN5.1, CN5.3, CN5.4, CN5.6, CN9.8) stay empty', oled)
        # Record 4.4 step 3, P3, 1.4: the charger's jumpers before power at step 1, not first at step 1b.
        chgr = next(ln for ln in bench.splitlines() if ln.startswith('- **Charger jumpers**'))
        for text in ('1A solder jumper is closed', '0.5A and 1.5A solder jumpers are open', 'never the 1.5A',
                     'EN1 (SJ2) and EN2 (SJ1)', 'EN2 = 1, EN1 = 0', 'C12-C18'):
            self.assertIn(text, chgr)
        self.assertLess(self.sheet.index('- **Charger jumpers**'), self.sheet.index('## Power checks'))

    def frozen(self, revision):
        return (self.out/'revisions'/revision/'build-sheet.md').read_text()

    @staticmethod
    def changes_of(sheet, previous):
        changes = sheet.split(f'\n## Changes from the previous revision ({previous})', 1)[1].split('\n## ', 1)[0]
        return (changes, *changes.split('### Remove', 1)[1].split('### Add', 1))

    def test_the_changes_section_against_the_2026_10_29_baseline(self):
        # Change A's own sheet (bench-bb-r0.1, frozen): against the bootstrap baseline, the r0 sheet the bench was
        # built from, so its Remove list is record 4.4 step 5's.
        changes, removed, added = self.changes_of(self.frozen('bench-bb-r0.1'), 'r0, 2026-10-29')
        self.assertIn('| jumper | 3V3 | B:e9 (SHUNT.2) | NUCLEO CN7.16 |', removed)        # record 4.4 step 5
        self.assertIn('| jumper | 3V3 | B:c9 (SHUNT.2) | C:c23 (COLED.+, OLED.VCC) |', removed)
        self.assertIn('| jumper | GND | A:c4 (BOBW.2) | B:L-63 |', removed)   # r0 W29, step 5's dated note
        self.assertIn('| lead L_REG_3V3 | 3V3 | B:c9 (SHUNT.2) | A:c41 (QT.V+) |', added)
        self.assertIn('| lead L_OLED_VCC | 3V3 | NUCLEO CN7.16 | C:c23 (COLED.+, OLED.VCC) |', added)
        self.assertIn('| jumper | CUPS | A:d6 (BOBW.4, C_CUPS.1, R1.1) | NUCLEO CN10.14 |', added)   # same MCU pin
        self.assertNotIn('LK_REG_SHUNT', changes)    # kept: the same two holes in both revisions
        self.assertLess(changes.index('### Remove'), changes.index('### Add'))
        self.assertIsNone(re.search(r'\bW\d+\b', changes))   # never by W-number

    def test_each_revision_is_its_own_change(self):
        # Record 6.1: r0.1 = change A (no load switch, the meter on its r0 pins), r0.2 = change B (the two meter
        # jumpers move), r0.3 = the second QT cable (QTM); change C, the load switch, was taken out of r0.3 before it
        # was built (record 4.6, 2026-11-02). Each sheet against the one before.
        r01, r02 = self.frozen('bench-bb-r0.1'), self.frozen('bench-bb-r0.2')
        for sheet in (r01, r02, self.sheet):
            self.assertNotIn('| LSW |', sheet)
            self.assertNotIn('SENS_EN', sheet)
        for sheet in (r01, r02):
            self.assertIn('frozen earlier revision', sheet)
        self.assertIn('| CUPS | wind |', r01)
        self.assertIn('NUCLEO CN10.14 | Dupont, about 30 cm | CUPS |', r01)   # a morpho male pin: Dupont
        _changes, removed, added = self.changes_of(r02, 'bench-bb-r0.1')
        self.assertEqual(re.findall(r'^\| jumper \| (\w+) \| [^|]+ \| NUCLEO (\S+) \|$', removed, re.M),
                         [('CUPS', 'CN10.14'), ('RAIN', 'CN10.29')])
        self.assertEqual(re.findall(r'^\| jumper \| (\w+) \| [^|]+ \| NUCLEO (\S+) \|$', added, re.M),
                         [('CUPS', 'CN9.5'), ('RAIN', 'CN8.4')])
        _changes, removed, added = self.changes_of(self.sheet, 'bench-bb-r0.2')
        self.assertNotIn('LK_3V3_CN6_4', removed + added)   # the P1 chain is r0.2's (record 4.6, 2026-11-02)
        self.assertNotIn('L_REG_3V3', removed + added)
        self.assertEqual(sorted(re.findall(r'^\| jumper \| (\w+) \| [^|]+ \| [^|]+\((QTM\.[\w+]+)\) \|$', added, re.M)),
                         [('3V3', 'QTM.V+'), ('GND', 'QTM.GND'), ('I2C_SCL', 'QTM.SCL'), ('I2C_SDA', 'QTM.SDA')])
        self.assertIn('Nothing.', removed)
        self.assertNotIn('CUPS', removed + added)

    def test_station_signals_on_morpho_male_pins_are_dupont_leads(self):
        # Until change B the cups and rain jumpers land on morpho male pins (r0.1): a solid wire cannot go
        # onto a male pin, so the sheet names them Dupont leads in section 2 and in a bench check, with their
        # ARDUINO alias (CN9.5) left empty. From r0.2 every station signal is on an ARDUINO female header.
        r01 = self.frozen('bench-bb-r0.1')
        jumpers = r01.split('\n## 2. Jumpers', 1)[1].split('\n## ', 1)[0]
        cups = re.search(r'^\| (W\d+) \| [^|]+ \| NUCLEO CN10\.14 \| Dupont, about 30 cm \| CUPS \|', jumpers, re.M).group(1)
        rain = re.search(r'^\| (W\d+) \| [^|]+ \| NUCLEO CN10\.29 \| Dupont, about 30 cm \| RAIN \|', jumpers, re.M).group(1)
        self.assertIn(f'the station signals still on the morpho\'s male pins ({cups} (CUPS, CN10.14), {rain} (RAIN, '
                      'CN10.29)) are female-to-male Dupont jumpers too', jumpers)
        check = next(ln for ln in r01.splitlines() if ln.startswith('- **Morpho signal pins:**'))
        for text in (f'{cups} to CN10.14 (PC0, CUPS)', f'{rain} to CN10.29 (PB5, RAIN)', 'female-to-male Dupont',
                     'Their ARDUINO aliases (CN9.5) stay empty'):
            self.assertIn(text, check)
        for sheet in (self.frozen('bench-bb-r0.2'), self.sheet):
            self.assertNotIn('Morpho signal pins', sheet)
            self.assertNotIn('still on the morpho', sheet)

    def test_the_baseline_is_the_revision_before(self):
        import json
        doc = json.loads((self.out/'connections.json').read_text())
        self.assertEqual(doc['revision'], self.w.revision)
        self.assertEqual(doc['baseline']['revision'], self.make.HISTORY[-1])
        self.assertEqual(sorted(doc), ['baseline', 'connections', 'revision'])
        self.assertTrue({c['kind'] for c in doc['connections']} == {'jumper', 'link', 'lead'})
        self.assertEqual({c['id'] for c in doc['connections'] if c['kind'] == 'link'},
                         {k.id for k in self.w.link_info})
        first = json.loads((self.out/'revisions'/'bench-bb-r0.1'/'connections.json').read_text())
        self.assertEqual(first['baseline']['revision'], 'r0, 2026-10-29')
        r02 = json.loads((self.out/'revisions'/'bench-bb-r0.2'/'connections.json').read_text())
        self.assertEqual(doc['baseline']['connections'], r02['connections'])
        self.assertEqual(r02['baseline']['connections'], first['connections'])
        self.make.write_sheets(self.out)        # a second run: the same files
        self.assertEqual((self.out/'build-sheet.md').read_text(), self.sheet)
        self.assertEqual(json.loads((self.out/'connections.json').read_text()), doc)
        bumped = dataclasses.replace(self.w, revision='bench-bb-r0.99')
        self.assertEqual(self.make.load_baseline(bumped.revision)['revision'], self.make.HISTORY[-1])
        # wiring.toml may not carry a frozen revision; a frozen model must carry its file's
        self.assertTrue(self.make._revision_problems(dataclasses.replace(self.w, revision='bench-bb-r0.2'), self.make.DATA))
        self.assertEqual(self.make._revision_problems(self.w, self.make.DATA), [])
        frozen = self.make.frozen_model('bench-bb-r0.1')
        self.assertTrue(self.make._revision_problems(self.w, frozen))
        self.assertEqual(self.make._revision_problems(wiring.load(frozen), frozen), [])


# UM2592 Rev 4 Table 17 (ARDUINO) and Table 18 (morpho), read from the manual's text: the MCU pin or the
# supply on each header pin the model names or ties.
UM2592 = {'CN6.4': '3V3', 'CN7.16': '3V3', 'CN6.6': 'GND', 'CN6.7': 'GND', 'CN10.20': 'GND',
          'CN9.7': 'PB10', 'CN10.25': 'PB10', 'CN9.6': 'PB8', 'CN10.27': 'PB8', 'CN8.2': 'PB2', 'CN7.30': 'PB2',
          'CN9.5': 'PB5', 'CN10.29': 'PB5', 'CN8.4': 'PB4', 'CN7.34': 'PB4', 'CN8.1': 'PB1', 'CN7.28': 'PB1',
          'CN8.3': 'PA10', 'CN7.32': 'PA10', 'CN8.5': 'PB14', 'CN7.36': 'PB14',
          'CN5.9': 'PA11', 'CN5.10': 'PA12', 'CN5.2': 'PA9', 'CN10.14': 'PC0', 'CN10.11': 'PA5', 'CN10.15': 'PA7',
          'CN10.17': 'PA4', 'CN10.21': 'PC2', 'CN10.23': 'PC1',
          'CN10.19': 'PA9', 'CN10.5': 'PA11', 'CN10.3': 'PA12', 'CN5.6': 'PA5', 'CN5.4': 'PA7', 'CN5.3': 'PA4',
          'CN5.1': 'PC2', 'CN9.8': 'PC1'}

# Record 6.1 and 4.4 steps 7-13: each lead's ends, role, kind and gauge. None: an end in a hole, checked
# by its node in test_the_hole_ends_land_on_their_strips.
CHANGE_A_LEADS = {
    'L_PACK_POS': ('PACK.+', 'J:WAGO_CELL_POS.1', 'force', 'pigtail', 26),
    'L_PACK_NEG': ('PACK.-', 'J:WAGO_STAR.1', 'force', 'pigtail', 26),
    'L_CELL_INA': ('J:WAGO_CELL_POS.2', 'INA.X1_VINP', 'force', 'solid', 22),
    'L_INA_BATT': ('INA.X1_VINM', 'J:WAGO_BATT.1', 'force', 'solid', 22),
    'L_BATT_POS': ('J:WAGO_BATT.2', 'CHGR.BATT2', 'force', 'pigtail', 26),
    'L_BATT_NEG': ('CHGR.BATT1', 'J:WAGO_STAR.2', 'force', 'pigtail', 26),
    'L_SYSOUT_POS': ('CHGR.SYSOUT2', 'J:WAGO_SYS_OUT.1', 'force', 'pigtail', 26),
    'L_SYSOUT_NEG': ('CHGR.SYSOUT1', 'insulated', 'force', 'pigtail', 26),
    'L_RLOAD_A': ('J:WAGO_SYS_OUT.2', 'RLOAD.1', 'force', 'solid', 22),
    'L_RLOAD_B': ('RLOAD.2', 'J:WAGO_STAR.3', 'force', 'solid', 22),
    'L_GAUGE_POS': ('GAUGE.BAT1+', 'J:WAGO_CELL_POS.3', 'sense', 'pigtail', 26),
    'L_GAUGE_NEG': ('GAUGE.BAT1-', 'insulated', 'sense', 'pigtail', 26),
    'L_VBUS': ('INA.X1_VBUS', 'J:WAGO_SYS_OUT.3', 'sense', 'solid', 22),
    'L_REG_VIN': ('J:WAGO_SYS_OUT.4', None, 'force', 'solid', 22),
    'L_TIE': ('J:WAGO_STAR.4', None, 'force', 'solid', 22),
    'L_NUC_RET': ('N:CN6.7', None, 'force', 'solid', 22),
    'L_REG_3V3': (None, None, 'force', 'solid', 22),
    'L_OLED_VCC': ('N:CN7.16', None, 'supply', 'dupont', 26),
    'L_OLED_GND': ('N:CN10.20', None, 'supply', 'dupont', 26),
    'L_NTC_THERM': ('NTC.1', None, 'sense', 'solid', 22),
    'L_NTC_RET': ('NTC.2', None, 'sense', 'solid', 22),
    'L_USB_IN': ('ADAPTER.+', 'CHGR.USBC', 'force', 'cable', 22),
}

# Record P3, P4, P6 and 4.4 steps 7-10: what each lever-connector position holds (None: free).
JOINT_POSITIONS = {
    'WAGO_CELL_POS': ('L_PACK_POS', 'L_CELL_INA', 'L_GAUGE_POS', None, None),   # 4: step 1b, 5: spare
    'WAGO_BATT': ('L_INA_BATT', 'L_BATT_POS', None),
    'WAGO_SYS_OUT': ('L_SYSOUT_POS', 'L_RLOAD_A', 'L_VBUS', 'L_REG_VIN', None),
    'WAGO_STAR': ('L_PACK_NEG', 'L_BATT_NEG', 'L_RLOAD_B', 'L_TIE', None),           # 5: step 1b exit (g)
}


class ChangeA(unittest.TestCase):
    """The committed model is step 1 v2, changes A and B and the QTM cable (record 4.4-4.6, 6.1; bench-bb-r0.3,
    without change C, which is not part of the breadboard build: record 4.6, 2026-11-02)."""

    def setUp(self):
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)

    def node(self, end):
        return wiring.raw_node(self.w, end)

    def test_the_committed_model_passes_every_check(self):
        # Record 6.2: the D3 checks, H7 and the lead geometry (checks.run_each), the proof, the guide both
        # ways and the firmware pins, all on the committed model.
        self.assertEqual(wiring.prove(self.w, self.jumpers), [])
        each = checks.run_each(self.w, self.jumpers, ROOT)
        self.assertEqual({name: problems for name, problems in each.items() if problems}, {})
        self.assertEqual(wiring.check_guide(self.w, GUIDE), [])
        self.assertEqual(wiring.check_guide_reverse(self.w, GUIDE), [])
        self.assertEqual(wiring.check_firmware(self.w, FIRMWARE), [])

    def test_the_revision_and_the_parts(self):
        self.assertEqual(self.w.revision, 'bench-bb-r0.3')
        for gone in ('CELL', 'GBAT', 'SRC'):
            self.assertNotIn(gone, self.w.parts)
        for pid in ('PACK', 'RLOAD', 'NTC', 'ADAPTER'):
            with self.subTest(part=pid):
                part = self.w.parts[pid]
                self.assertEqual((part.pins, part.origin), ({}, None))
                self.assertIsNotNone(part.place_mm)
        pack = self.w.parts['PACK']
        for text in ('1S3P 6600 mAh, 3.0-4.2 V', '3 x 2200 mAh', '#353'):
            self.assertIn(text, pack.kind)
        self.assertEqual(pack.terminals, ('+', '-'))
        self.assertIn('100 Ohm 1/2 W', self.w.parts['RLOAD'].kind)
        self.assertIn('#372', self.w.parts['NTC'].kind)
        self.assertIn('5 V >= 2 A, floating', self.w.parts['ADAPTER'].kind)
        self.assertEqual({j.id: (j.kind, j.positions) for j in self.w.joints.values()},
                         {'WAGO_CELL_POS': ('WAGO 222-415', 5), 'WAGO_BATT': ('WAGO 222-413', 3),
                          'WAGO_SYS_OUT': ('WAGO 222-415', 5), 'WAGO_STAR': ('WAGO 222-415', 5)})
        self.assertEqual(self.w.joints['WAGO_STAR'].domain, 'power')

    def test_the_breakouts_have_sockets_terminals_and_test_points(self):
        chgr, ina, gauge = (self.w.parts[p] for p in ('CHGR', 'INA', 'GAUGE'))
        self.assertEqual(chgr.terminals, ('BATT1', 'BATT2', 'SYSOUT1', 'SYSOUT2', 'USBC'))
        self.assertEqual(chgr.internal, (('LIPO', 'BATT2'), ('OUT', 'SYSOUT2'), ('GND', 'GND2', 'GND3', 'BATT1', 'SYSOUT1')))
        self.assertEqual(chgr.test_points, ('GND', 'LIPO', 'GND2', 'OUT', 'GND3'))
        self.assertEqual(ina.terminals, ('X1_VINP', 'X1_VBUS', 'X1_VINM'))
        self.assertEqual(ina.internal, (('VIN+', 'X1_VINP'), ('VIN-', 'X1_VINM'), ('VBUS', 'X1_VBUS')))
        self.assertEqual(ina.test_points, ('VIN+', 'VIN-', 'VBUS'))
        self.assertEqual(gauge.terminals, ('BAT1+', 'BAT1-'))
        # The INA228's header GND and VCC are in no net (record P4: power and ground over STEMMA QT).
        members = {m for ms in self.w.nets.values() for m in ms}
        self.assertFalse({'INA.GND', 'INA.VCC', 'GBAT.-'} & members)

    def test_the_leads_of_change_a(self):
        leads = {k.id: k for k in self.w.leads}
        self.assertEqual(set(leads), set(CHANGE_A_LEADS))
        for lid, (a, b, role, kind, gauge) in CHANGE_A_LEADS.items():
            with self.subTest(lead=lid):
                k = leads[lid]
                self.assertEqual((k.role, k.kind, k.gauge), (role, kind, gauge))
                for want, got in ((a, k.a), (b, k.b)):
                    if want is not None:
                        self.assertEqual(got, want)
        tagged = {k.segment: k.id for k in self.w.leads if k.segment in ('PATH_PACK_POS', 'PATH_PACK_NEG')}
        self.assertEqual(tagged, {'PATH_PACK_POS': 'L_PACK_POS', 'PATH_PACK_NEG': 'L_PACK_NEG'})
        segments = checks.power_path_segments(self.w)
        self.assertEqual(set(segments), set(wiring.SEGMENTS))
        self.assertEqual((segments['PATH_CELL_OUT'][0], segments['PATH_CELL_OUT'][-1]),
                         (('joint', 'WAGO_CELL_POS'), ('joint', 'WAGO_SYS_OUT')))

    def test_the_hole_ends_land_on_their_strips(self):
        leads = {k.id: k for k in self.w.leads}
        pin = {m: self.node(m) for m in ('REG.VIN', 'REG.GND', 'SHUNT.2', 'OLED.VCC', 'OLED.GND', 'CHGR.THERM')}
        self.assertEqual(self.node(leads['L_REG_VIN'].b), pin['REG.VIN'])
        self.assertEqual(self.node(leads['L_TIE'].b), pin['REG.GND'])
        self.assertEqual(self.node(leads['L_NUC_RET'].b), pin['REG.GND'])
        self.assertEqual(self.node(leads['L_REG_3V3'].a), pin['SHUNT.2'])
        self.assertEqual(self.node(leads['L_REG_3V3'].b), self.node('QT.V+'))   # P1: no rail run
        self.assertEqual(self.node(leads['L_OLED_VCC'].b), pin['OLED.VCC'])
        self.assertEqual(self.node(leads['L_OLED_GND'].b), pin['OLED.GND'])
        self.assertEqual(self.node(leads['L_NTC_THERM'].b), pin['CHGR.THERM'])
        self.assertEqual(self.node(leads['L_NTC_RET'].b), 'B:L-')   # logic ground, not STAR (record D2)
        self.assertEqual(leads['L_NTC_RET'].domain, 'logic')

    def test_the_joint_positions(self):
        held = {}
        for k in self.w.leads:
            for end in (k.a, k.b):
                e = wiring.parse_end(self.w, end)
                if e[0] == 'joint':
                    held[(e[1], e[2])] = k.id
        for joint, want in JOINT_POSITIONS.items():
            with self.subTest(joint=joint):
                self.assertEqual(tuple(held.get((joint, n)) for n in range(1, len(want) + 1)), want)

    def test_the_p1_chain_is_tagged_member_by_member(self):
        items = list(self.w.parts.values()) + list(self.w.link_info) + list(self.w.leads)
        tagged = {i.id for i in items if i.exception == 'P1 regulator'}
        self.assertEqual(tagged, set(checks.P1_CHAIN))
        self.assertNotIn('REG', tagged)

    def test_the_regulator_supply_leads_fit_h7(self):
        import math
        for lid in ('L_REG_VIN', 'L_TIE'):
            with self.subTest(lead=lid):
                k = model_lead(self.w, lid)
                span = math.dist(wiring.end_xy(self.w, k.a), wiring.end_xy(self.w, k.b))
                self.assertLessEqual(span, k.length_mm)
                self.assertLessEqual(k.length_mm, 100)
        for k in self.w.leads:
            if k.kind == 'pigtail':
                self.assertLessEqual(k.length_mm, 60, k.id)
        routed = model_lead(self.w, 'L_REG_3V3')
        self.assertGreaterEqual(routed.length_mm, math.dist(wiring.end_xy(self.w, routed.a), wiring.end_xy(self.w, routed.b)))

    def test_the_battery_path_estimate_meets_p8(self):
        # Record P8's estimate of each span: the leads' copper, the 15 mOhm shunt, each JST PH mating at
        # its 10 mOhm initial maximum, about 1 mOhm per lever clamp or screw; each pack-side span is one
        # mating at its 20 mOhm limit plus its lead.
        import make
        leads = {k.id: k for k in self.w.leads}
        seg = checks.power_path_segments(self.w)

        def copper(name):
            return sum(make.lead_mohm(leads[i]) for kind, i in seg[name] if kind == 'lead')
        self.assertLess(copper('PATH_POS') + 15 + 2*10 + 6, 75)
        self.assertLess(copper('PATH_NEG') + 2*10 + 2, 40)
        for name in ('PATH_PACK_POS', 'PATH_PACK_NEG'):   # P8 rounds 60 mm of 26 AWG (8.03 mOhm) to 8
            self.assertLessEqual(round(copper(name)) + 20, 28, name)

    def test_iset_and_vin_sense(self):
        # Record M2: ISET -> 10 kOhm 1 % at the charger -> the PB1 node with 100 nF and 1 MOhm to logic ground;
        # the divider 20 kOhm over 10 kOhm on PA10, its bottom to the board-B ground rail.
        nets, parts = self.w.nets, self.w.parts
        self.assertEqual((self.w.mcu['ISET'], self.w.mcu['VIN_SENSE']), ('PB1', 'PA10'))
        self.assertEqual(sorted(nets['ISET_CHGR']), ['CHGR.ISET', 'R_ISER.1'])
        self.assertEqual(sorted(nets['ISET']), ['C_ISET.1', 'N:CN8.1', 'R_IPD.1', 'R_ISER.2'])
        self.assertTrue({'C_ISET.2', 'R_IPD.2', 'R6.2'} <= set(nets['GND']))
        self.assertEqual((parts['R_ISER'].ohms, parts['R_IPD'].ohms), (10000, 1000000))
        self.assertIn('100 nF', parts['C_ISET'].kind)
        # R_ISER is the first part after the charger's ISET pin: its jumper only crosses the centre channel.
        iset = [j for j in self.jumpers if j.net == 'ISET_CHGR']
        self.assertEqual(len(iset), 1)
        self.assertEqual({iset[0].a[2], iset[0].b[2]}, {parts['CHGR'].pins['ISET'][2]})
        self.assertEqual(sorted(nets['VIN_SENSE']), ['N:CN8.3', 'R5.2', 'R6.1'])
        self.assertEqual(sorted(nets['VIN_DIV']), ['R4.2', 'R5.1'])
        self.assertEqual(sorted(nets['CHGR_VBUS']), ['CHGR.VBUS', 'R4.1'])
        ohms = [parts[p].ohms for p in ('R4', 'R5', 'R6')]
        self.assertEqual(ohms, [10000, 10000, 10000])
        self.assertEqual(sum(ohms)/ohms[2], 3.0)   # VIN = 3 x the pin
        on = {}
        for p in parts.values():
            for n, h in p.pins.items():
                on.setdefault(wiring.strip(h), []).append(f'{p.id}.{n}')
        self.assertEqual(sorted(on[wiring.strip(parts['CHGR'].pins['VBUS'])]), ['CHGR.VBUS', 'R4.1'])
        self.assertEqual(on[wiring.strip(parts['CHGR'].pins['GND3'])], ['CHGR.GND3'])   # R6 is off the a59 strip
        to_cn8 = {(j.net, j.b if j.b[0] == 'N' else j.a) for j in self.jumpers if 'CN8' in (j.a[1], j.b[1])}
        self.assertEqual(to_cn8, {('ISET', ('N', 'CN8', 1)), ('VANE', ('N', 'CN8', 2)), ('VIN_SENSE', ('N', 'CN8', 3)),
                                  ('RAIN', ('N', 'CN8', 4))})   # rain on A3 since change B (record N2)

    def test_the_nucleo_header_moves(self):
        # Record N3, 4.4 step 13: CHG, PGOOD and the vane on the Arduino headers; change B (N2, 4.5,
        # bench-bb-r0.2) moves the cups to D4 and the rain gauge to A3.
        heads = {net: wiring.nucleo_headers(self.w, net) for net in ('CHG', 'PGOOD', 'VANE', 'CUPS', 'RAIN', 'ISET', 'VIN_SENSE')}
        self.assertEqual(heads, {'CHG': ['CN9.7'], 'PGOOD': ['CN9.6'], 'VANE': ['CN8.2'], 'CUPS': ['CN9.5'],
                                 'RAIN': ['CN8.4'], 'ISET': ['CN8.1'], 'VIN_SENSE': ['CN8.3']})
        self.assertEqual((self.w.mcu['CUPS'], self.w.mcu['RAIN']), ('PB5', 'PB4'))

    def test_the_alias_ties_agree_with_um2592(self):
        want = {('CN6.4', 'CN7.16'), ('CN6.6', 'CN6.7', 'CN10.20'), ('CN9.7', 'CN10.25'), ('CN9.6', 'CN10.27'),
                ('CN8.2', 'CN7.30'), ('CN9.5', 'CN10.29'), ('CN8.4', 'CN7.34'), ('CN8.1', 'CN7.28'),
                ('CN8.3', 'CN7.32'), ('CN8.5', 'CN7.36'),
                # PA9, the I2C pins and the OLED's ARDUINO aliases (Tables 17 and 18; record 4.2)
                ('CN5.2', 'CN10.19'), ('CN5.9', 'CN10.5'), ('CN5.10', 'CN10.3'), ('CN10.11', 'CN5.6'),
                ('CN10.15', 'CN5.4'), ('CN10.17', 'CN5.3'), ('CN10.21', 'CN5.1'), ('CN10.23', 'CN9.8')}
        self.assertEqual(set(self.w.ties), want)
        for tie in self.w.ties:
            with self.subTest(tie=tie):
                self.assertEqual(len({UM2592[p] for p in tie}), 1)
        for net, mcu in self.w.mcu.items():
            for header in wiring.nucleo_headers(self.w, net):
                self.assertEqual(UM2592[header], mcu, f'{net} on {header}')

    def test_no_jumper_lands_on_an_alias_a_lead_end_or_a_test_point(self):
        named = {m[2:] for ms in self.w.nets.values() for m in ms if m.startswith('N:')}
        aliases = {p for tie in self.w.ties for p in tie} - named
        self.assertTrue({'CN10.25', 'CN10.27', 'CN7.30', 'CN7.28', 'CN7.32', 'CN10.29', 'CN7.34'} <= aliases)
        ends = [(j, h) for j in self.jumpers for h in (j.a, j.b)]
        for j, h in ends:
            if h[0] == 'N':
                self.assertIn(f'N:{h[1]}.{h[2]}', self.w.nets[j.net], j)
        holes = {h for _j, h in ends}
        self.assertFalse(holes & wiring.lead_holes(self.w))
        test_points = {wiring.strip(p.pins[n]) for p in self.w.parts.values() for n in p.test_points}
        self.assertEqual(len(test_points), 8)   # CHGR LIPO, OUT, GND x3; INA VIN+, VIN-, VBUS (record P2, D3 check 6)
        self.assertFalse({wiring.strip(h) for h in holes} & test_points)

    def test_the_oled_has_its_own_supply_pair(self):
        # Record N3, R-3: VCC from CN7.16 and GND to CN10.20 on their own leads; no jumper brings board C
        # its supply or ground.
        vcc, gnd = model_lead(self.w, 'L_OLED_VCC'), model_lead(self.w, 'L_OLED_GND')
        self.assertEqual((vcc.a, vcc.net, gnd.a, gnd.net), ('N:CN7.16', '3V3', 'N:CN10.20', 'GND'))
        self.assertEqual({(k.role, k.kind) for k in (vcc, gnd)}, {('supply', 'dupont')})
        on_c = {j.net for j in self.jumpers if 'C' in (j.a[0], j.b[0])}
        self.assertTrue(on_c <= {'OLED_SCLK', 'OLED_DIN', 'OLED_CS', 'OLED_DC', 'OLED_RST'}, on_c)

    def test_the_meter_conditioning_sits_at_the_jack_end(self):
        # Record M7: each pull-up and filter within 10 columns of its BOB-14021's pins, on board A, with its
        # line-side lead in the jack pin's own strip: no jumper between the jack pin and its pull-up.
        for part, bob in (('R1', 'BOBW'), ('C_CUPS', 'BOBW'), ('R3', 'BOBW'), ('R2', 'BOBR'), ('C_RAIN', 'BOBR')):
            cols = [h[2] for h in self.w.parts[bob].pins.values()]
            for h in self.w.parts[part].pins.values():
                with self.subTest(part=part, hole=h):
                    self.assertEqual(h[0], 'A')
                    self.assertLessEqual(min(abs(h[2] - c) for c in cols), 10)
        self.assertEqual(checks.check_meter_at_jack(self.w), [])
        for net, jack, conditioning in checks.METER_JACK:
            strip = wiring.strip(wiring.member_hole(self.w, jack))
            for m in conditioning:
                with self.subTest(member=m):
                    self.assertEqual(wiring.strip(wiring.member_hole(self.w, m)), strip)
            # so every jumper on the line starts at the jack-end strip and runs toward the MCU
            for j in self.jumpers:
                if j.net == net:
                    self.assertIn(strip, {wiring.strip(j.a), wiring.strip(j.b)}, j)
        moved = dataclasses.replace(self.w.parts['R2'], pins={'1': ('A', 'g', 15), '2': ('A', 'g', 19)})
        problems = checks.check_meter_at_jack(dataclasses.replace(self.w, parts={**self.w.parts, 'R2': moved}))
        self.assertTrue(any(p.startswith("RAIN: R2.1 is not in BOBR.4's strip") for p in problems), problems)

    def test_no_part_id_is_a_checklist_row(self):
        # The pre-run checklist's rows are C1-C23 (record 4.3): no part may carry one of those ids.
        import checklist
        rows = {c['id'] for c in checklist.CHECKS}
        self.assertTrue({'C1', 'C2'} <= rows, rows)
        self.assertEqual(set(self.w.parts) & rows, set())

    def test_the_thermistor_and_the_input_are_off_board(self):
        self.assertEqual(sorted(self.w.nets['THERM']), ['CHGR.THERM', 'NTC.1'])
        self.assertIn('NTC.2', self.w.nets['GND'])
        note = self.w.parts['NTC'].note
        for text in ("Remove or cut the breakout's fixed 10 kOhm TS resistor first", '+3.5 C', '+47 C', 'record D2'):
            self.assertIn(text, note)
        usb = model_lead(self.w, 'L_USB_IN')
        self.assertEqual((usb.net, usb.kind), ('CHGR_IN', 'cable'))
        self.assertEqual(self.w.parts['ADAPTER'].terminals, ('+',))   # no ground lead: no second tie (P4)

    def test_the_notes(self):
        notes = {pid: p.note for pid, p in self.w.parts.items()}
        for pid, texts in (('CHGR', ('R_ISET is 1 kOhm', '0.89 A typ', 'TMR is tied to GND', 'timers disabled',
                                     'ITERM is 0.30 A typ (0.225-0.375 A', 'zero-current test points',
                                     'LED anodes', 'on OUT')),
                           ('INA', ('SJ1', 'continuity', 'one 10 kOhm resistor pack', '15 mOhm 1 % 2 W', 'L_VBUS',
                                    'header GND and VCC')),
                           ('GAUGE', ('CELL+ position 3', 'insulated', 'STEMMA QT')),
                           ('PACK', ('#1131 pack-mating half, at most 60 mm, no solder',)),
                           ('REG', ('feeds CN6.4 through the SHUNT, L_REG_3V3 and the QT.V+ strip, the board-A 3V3 node',)),
                           ('BOBW', ('PRT-00132', 'continuity', '3/4', '2/5')),
                           ('BOBR', ('PRT-00132', 'continuity', '3/4'))):
            for text in texts:
                with self.subTest(part=pid, text=text):
                    self.assertIn(text, notes[pid])
        text = DATA.read_text()
        self.assertNotIn('CE, ISET and THERM stay unconnected', text)
        comments = '\n'.join(ln for ln in text.splitlines() if ln.lstrip().startswith('#')).lower()
        self.assertNotIn('official phase a', comments)
        self.assertNotIn('solder', comments)


OFF_PART = '''
[[part]]
id = "PROBE"
kind = "test part drawn at its hole"
board = "B"
origin = ["f", 40]
step = 1
pins = ["1"]
source = "passive"
off_board = true
'''

PROBE_LEAD = '''
[[lead]]
id = "L_PROBE"
a = "PROBE.1"
b = "NTC.1"
role = "sense"
kind = "solid"
gauge = 22
length_mm = 300
'''


class ChangeB(unittest.TestCase):
    """Change B (record N2, approved 2026-10-30 in 7.1; section 4.5): the cups on PB5 (D4, CN9.5,
    LPTIM1_IN1 AF1) and the rain gauge on PB4 (A3, CN8.4, EXTI4), both on the Arduino headers."""

    def setUp(self):
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)

    def test_cups_is_pb5_at_cn9_5(self):
        self.assertEqual(self.w.mcu['CUPS'], 'PB5')
        self.assertEqual(sorted(self.w.nets['CUPS']), ['BOBW.4', 'C_CUPS.1', 'N:CN9.5', 'R1.1'])
        self.assertEqual(UM2592['CN9.5'], 'PB5')

    def test_rain_is_pb4_at_cn8_4(self):
        self.assertEqual(self.w.mcu['RAIN'], 'PB4')
        self.assertEqual(sorted(self.w.nets['RAIN']), ['BOBR.4', 'C_RAIN.1', 'N:CN8.4', 'R2.1'])
        self.assertEqual(UM2592['CN8.4'], 'PB4')

    def test_no_meter_input_is_on_a_morpho_pin(self):
        for net in ('CUPS', 'RAIN'):
            with self.subTest(net=net):
                ends = {h for j in self.jumpers if j.net == net for h in (j.a, j.b) if h[0] == 'N'}
                self.assertTrue(ends)
                self.assertTrue(all(h[1] in ('CN8', 'CN9') for h in ends), ends)
        self.assertNotIn('PC0', self.w.mcu.values())

    def test_the_firmware_agrees(self):
        self.assertEqual(wiring.check_firmware(self.w, FIRMWARE), [])


class ChangeCDeferred(unittest.TestCase):
    """Change C (record 4.6, R-11, PORT-9) is not part of the breadboard build (user's decision 2026-11-02;
    bench-bb-r0.3 redefined in place before it was built): the bench has no sensor power switch. The
    hub's QT cable and the power monitors' QTM cable are both on the unswitched 3V3; the P1 chain lands on
    the QT.V+ strip as in r0.2; PA9 is unconnected (the firmware may drive it: harmless)."""

    def setUp(self):
        self.w = wiring.load(DATA)
        self.jumpers = wiring.plan_jumpers(self.w)

    def node(self, end):
        return wiring.raw_node(self.w, end)

    def test_there_is_no_sensor_switch(self):
        self.assertEqual(self.w.revision, 'bench-bb-r0.3')
        self.assertNotIn('LSW', self.w.parts)
        for net in ('3V3_SW', 'SENS_EN'):
            self.assertNotIn(net, self.w.nets)
        self.assertNotIn('PA9', self.w.mcu.values())
        ends = {h for j in self.jumpers for h in (j.a, j.b) if h[0] == 'N'}
        self.assertFalse(ends & {('N', 'CN5', 2), ('N', 'CN10', 19)}, ends)   # PA9 stays empty

    def test_the_qtm_branch_is_kept_and_unswitched(self):
        qtm, qt = self.w.parts['QTM'], self.w.parts['QT']
        self.assertEqual((qtm.board, tuple(qtm.pins)), ('A', ('GND', 'V+', 'SDA', 'SCL')))
        nets = self.w.nets
        self.assertTrue({'QT.V+', 'QTM.V+'} <= set(nets['3V3']))
        self.assertTrue({'QTM.GND', 'QT.GND'} <= set(nets['GND']))
        self.assertTrue({'QT.SDA', 'QTM.SDA'} <= set(nets['I2C_SDA']))
        self.assertTrue({'QT.SCL', 'QTM.SCL'} <= set(nets['I2C_SCL']))
        cols = [h[2] for h in qt.pins.values()]
        self.assertLessEqual(min(abs(h[2] - c) for h in qtm.pins.values() for c in cols), 10)
        groups = wiring.connectivity(self.w, self.jumpers)
        hub = next(g for g in groups if 'QT.V+' in g)
        self.assertTrue({'QTM.V+', 'N:CN6.4', 'SHUNT.2'} <= hub)   # one unswitched 3V3
        self.assertEqual(wiring.prove(self.w, self.jumpers), [])

    def test_the_p1_chain_lands_on_the_qt_v_plus_strip(self):
        link = next(k for k in self.w.link_info if k.id == 'LK_3V3_CN6_4')
        lead = model_lead(self.w, 'L_REG_3V3')
        self.assertEqual(self.node(lead.b), self.node(link.a))   # P1: the lead lands where the link starts
        self.assertEqual(self.node(link.a), self.node('QT.V+'))
        self.assertEqual(lead.b, 'A:c41')
        self.assertEqual((lead.net, link.exception, lead.exception), ('3V3', 'P1 regulator', 'P1 regulator'))
        self.assertEqual(checks.check_lead_geometry(self.w), [])

    def test_the_firmware_keeps_pa9(self):
        # i2c_bus, benchlink and i2cscan still name POWER_PIN = PA9 (the port power enable, CN10.19);
        # the breadboard model does not check it, as it has no SENS_EN.
        for file in ('stage0-node/App/i2c_bus.lit.md', 'benchlink/App/benchlink.c', 'i2cscan/App/i2cscan.c'):
            with self.subTest(file=file):
                found = {m.group(1): m for m in wiring.PIN_DEFINE.finditer((FIRMWARE/file).read_text())}
                self.assertEqual(found['POWER_PIN'].group(2), '9')
                self.assertNotIn('POWER_PIN', wiring.FIRMWARE[file])
        self.assertEqual(wiring.check_firmware(self.w, FIRMWARE), [])

    def test_every_check_is_clean(self):
        self.assertEqual(checks.run_all(self.w, self.jumpers, ROOT), [])
        self.assertEqual(wiring.check_guide(self.w, GUIDE), [])
        self.assertEqual(wiring.check_guide_reverse(self.w, GUIDE), [])


class OffBoard(unittest.TestCase):
    """A part drawn at holes but not plugged in: on leads only, its strips left alone."""

    def with_probe(self, lead=PROBE_LEAD):
        text = DATA.read_text().replace('members = ["CHGR.THERM", "NTC.1"]', 'members = ["CHGR.THERM", "NTC.1", "PROBE.1"]')
        return load_text(self, text + OFF_PART + lead)

    def test_an_off_board_pin_needs_a_lead(self):
        self.assertEqual(self.with_probe().parts['PROBE'].off_board, True)
        with self.assertRaises(ValueError) as e:
            self.with_probe(lead='')
        self.assertIn('PROBE.1 is off the breadboard', str(e.exception))

    def test_a_part_on_an_off_board_strip_is_a_short(self):
        w = self.with_probe()
        self.assertEqual(wiring.prove(w, wiring.plan_jumpers(w)), [])
        col = w.parts['PROBE'].pins['1'][2]
        r = dataclasses.replace(w.parts['R4'], pins={'1': w.parts['R4'].pins['1'], '2': ('B', 'j', col)})
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(with_part(w, r))
        self.assertIn('off the breadboard PROBE.1', str(e.exception))

    def test_an_open_breakout_pin_cannot_share_a_strip(self):
        w = wiring.load(DATA)
        ce = w.parts['CHGR'].pins['CE']
        r = dataclasses.replace(w.parts['R6'], pins={'1': w.parts['R6'].pins['1'], '2': ('B', 'e', ce[2])})
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(with_part(w, r))
        self.assertIn('unconnected CHGR.CE', str(e.exception))


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

        def ref(m):
            return 'NUCLEO' if m.startswith('N:') else m[2:] if m.startswith('J:') else m.split('.')[0]
        want = {build_schematic.NET_POWER.get(n, n).lstrip('+'): {ref(m) for m in members} for n, members in w.nets.items()}
        # The meter's own switches and vane resistors are drawn across the breakout pins: not breadboard parts.
        got = {n.lstrip('+'): refs - set(build_schematic.METER) for n, refs in got.items()}
        # The power-domain ground (record P4) is its own net, tied to GND by L_TIE alone.
        power = got.pop(build_schematic.POWER_GROUND)
        self.assertEqual(power, {'PACK', 'CHGR', 'RLOAD', 'WAGO_STAR', 'L_TIE'})
        self.assertEqual(power & got['GND'], {'L_TIE'})
        got['GND'] = (got['GND'] | power) - {'L_TIE'}
        self.assertEqual(got, want)

    def test_the_schematic_labels_the_pack_and_draws_heavy_leads(self):
        import build_schematic
        w = wiring.load(DATA)
        sch = (self.out/'bench-breadboard.kicad_sch').read_text()
        self.assertIn('"1S3P 6600 mAh, 3.0-4.2 V"', sch)
        self.assertIn(f'(rev "{w.revision}")', sch)
        for role in ('force', 'sense', 'supply'):
            self.assertIn(f'(stroke (width {build_schematic.LEAD_STROKE[role]})', sch)
        self.assertGreaterEqual(sch.count(f'(stroke (width {build_schematic.HEAVY})'), 10)
        for net in ('ISET', 'ISET_CHGR', 'VIN_SENSE', 'VIN_DIV', 'CHGR_VBUS', 'THERM', 'SYS_OUT', 'GAUGE_BAT_NEG'):
            self.assertIn(f'(label "{net}"', sch)
        for item in [*w.joints, *(k.id for k in w.leads), 'L_OLED_VCC from CN7.16', 'L_OLED_GND to CN10.20']:
            self.assertIn(item, sch)
        self.assertIn('(symbol (lib_id "Device:NetTie_2")', sch)
        self.assertEqual(sch.count('(lib_id "Device:NetTie_2")'), 1)   # L_TIE, the only tie
        self.assertIn('SJ1 (VBUS-VIN+) open', sch)

    def test_the_committed_schematic_is_current(self):
        self.assertEqual((self.out/'bench-breadboard.kicad_sch').read_text(),
                         (HW/'bench-breadboard.kicad_sch').read_text())

    def test_renders_exist_and_are_current(self):
        for name in ('board-a.png', 'board-b.png', 'board-c.png', 'overview.png', 'schematic.pdf', '3d-top.png', '3d-angle.png'):
            with self.subTest(name=name):
                self.assertTrue((self.out/'renders'/name).stat().st_size > 1000)
        for name in ('board-a.png', 'board-b.png', 'board-c.png', 'overview.png'):
            with self.subTest(current=name):
                self.assertEqual((self.out/'renders'/name).read_bytes(), (HW/'renders'/name).read_bytes())


# ---- the record D2 schema: joints, terminals, internal ties, roles, domains, place_mm ----

# A small model in the shape of change A (build-progression record 4.4): the charger's sockets are
# terminals tied inside it to its header test points, the pack is off the breadboard (place_mm), the
# battery path runs through two lever-connector joints, and the TIE lead lands on a NUCLEO GND pin.
MINI = '''
split_rails = false
revision = "fixture"

[nucleo]
ties = [["CN8.2", "CN7.30"], ["CN6.6", "CN6.7"]]

[[joint]]
id = "STAR"
kind = "WAGO 222-415"
positions = 5
place_mm = [0.0, 60.0]
domain = "power"

[[joint]]
id = "BATTJ"
kind = "WAGO 222-413"
positions = 3
place_mm = [30.0, 60.0]
domain = "power"

[[part]]
id = "CHGR"
kind = "bq24074 breakout"
board = "B"
origin = ["a", 50]
step = 1
pins = ["GND", "LIPO", "GND2", "OUT", "CHG", "GND3"]
terminals = ["BATT1", "BATT2", "SYSOUT1", "SYSOUT2", "USBC"]
internal = [["LIPO", "BATT2"], ["OUT", "SYSOUT2"], ["GND", "GND2", "GND3", "BATT1", "SYSOUT1"]]
test_points = ["GND", "LIPO", "GND2", "OUT", "GND3"]
source = "passive"

[[part]]
id = "PACK"
kind = "1S3P pack"
place_mm = [10.0, 70.0]
terminals = ["+", "-"]
domain = "power"
source = "bench check"

[[part]]
id = "RPU"
kind = "10 kOhm pull-up"
board = "B"
origin = ["f", 40]
step = 4
pins = ["1", "2"]
ohms = 10000
source = "passive"

[[part]]
id = "VR"
kind = "vane resistor"
board = "A"
origin = ["g", 60]
step = 1
pins = ["1", "2"]
source = "passive"

[[net]]
name = "BATT"
class = "battery lead"
members = ["PACK.+", "J:BATTJ", "CHGR.BATT2", "CHGR.LIPO"]

[[net]]
name = "SYS_OUT"
class = "power"
members = ["CHGR.OUT", "CHGR.SYSOUT2"]

[[net]]
name = "GND"
mcu = "GND"
class = "ground"
members = ["PACK.-", "J:STAR", "CHGR.BATT1", "CHGR.SYSOUT1", "CHGR.GND", "CHGR.GND2", "CHGR.GND3", "N:CN6.6", "N:CN6.7"]

[[net]]
name = "CHG"
class = "charger"
members = ["CHGR.CHG", "RPU.1"]

[[net]]
name = "PULL"
mcu = "3V3"
class = "power"
members = ["RPU.2", "N:CN6.4"]

[[net]]
name = "VANE"
mcu = "PB2"
class = "wind"
members = ["N:CN8.2", "VR.1"]

[[lead]]
id = "L_PACK_POS"
a = "PACK.+"
b = "J:BATTJ.1"
role = "force"
gauge = 26
kind = "pigtail"
length_mm = 60
segment = "PATH_PACK_POS"

[[lead]]
id = "L_BATT_POS"
a = "J:BATTJ.2"
b = "CHGR.BATT2"
role = "force"
gauge = 26
kind = "pigtail"
length_mm = 60

[[lead]]
id = "L_PACK_NEG"
a = "PACK.-"
b = "J:STAR.1"
role = "force"
gauge = 26
kind = "pigtail"
length_mm = 60
segment = "PATH_PACK_NEG"

[[lead]]
id = "L_BATT_NEG"
a = "J:STAR.2"
b = "CHGR.BATT1"
role = "force"
gauge = 26
kind = "pigtail"
length_mm = 60

[[lead]]
id = "L_SYSOUT_NEG"
a = "CHGR.SYSOUT1"
b = "insulated"
insulated = true
role = "force"
gauge = 26
kind = "pigtail"
length_mm = 60

[[lead]]
id = "L_TIE"
a = "J:STAR.4"
b = "N:CN6.6"
role = "force"
gauge = 22
kind = "solid"
length_mm = 100
exception = "P1 regulator"
domain = "logic"
'''

# A logic part on GND that a jumper must reach: the NUCLEO GND pins or, without the TIE, the charger.
LOGIC_GND = '''
[[part]]
id = "RG"
kind = "logic part on GND"
board = "A"
origin = ["g", 20]
step = 1
pins = ["1", "2"]
source = "passive"
'''


def mini(test, edit=lambda t: t, extra=''):
    """The MINI model, with edit(text) applied and extra TOML appended."""
    return load_text(test, edit(MINI) + extra)


def with_gnd_member(text, member):
    return text.replace('"N:CN6.6", "N:CN6.7"]', f'"N:CN6.6", "N:CN6.7", "{member}"]')


def without_lead(text, lead_id):
    head, rest = text.split(f'[[lead]]\nid = "{lead_id}"\n', 1)
    return head + ('[[lead]]' + rest.split('[[lead]]', 1)[1] if '[[lead]]' in rest else '')


def jumper_ends(jumpers, net):
    return {h for j in jumpers if j.net == net for h in (j.a, j.b)}


class Schema(unittest.TestCase):
    """Record D2: the model can say what change A builds."""

    def test_the_fixture_loads_plans_and_proves(self):
        w = mini(self)
        self.assertEqual(w.revision, 'fixture')
        self.assertEqual(w.joints['STAR'], wiring.Joint('STAR', 'WAGO 222-415', 5, (0.0, 60.0), 'power'))
        self.assertEqual(w.parts['CHGR'].terminals, ('BATT1', 'BATT2', 'SYSOUT1', 'SYSOUT2', 'USBC'))
        self.assertEqual(w.parts['RPU'].ohms, 10000)
        tie = next(k for k in w.leads if k.id == 'L_TIE')
        self.assertEqual((tie.net, tie.role, tie.kind, tie.gauge, tie.exception, tie.domain),
                         ('GND', 'force', 'solid', 22, 'P1 regulator', 'logic'))
        self.assertEqual(next(k for k in w.leads if k.id == 'L_PACK_POS').segment, 'PATH_PACK_POS')
        jumpers = wiring.plan_jumpers(w)
        self.assertEqual(sorted(j.net for j in jumpers), ['CHG', 'PULL', 'VANE'])
        self.assertEqual(wiring.prove(w, jumpers), [])

    def test_an_unknown_key_is_refused_by_name(self):
        for edit, where in ((lambda t: t.replace('ohms = 10000', 'ohms = 10000\ncolour = "red"'), 'part RPU'),
                            (lambda t: t.replace('segment = "PATH_PACK_NEG"', 'segment = "PATH_PACK_NEG"\nawg = 26'),
                             'lead L_PACK_NEG'),
                            (lambda t: t.replace('positions = 3', 'positions = 3\nlevers = 3'), 'joint BATTJ'),
                            (lambda t: 'mystery = 1\n' + t, 'wiring.toml')):
            with self.subTest(where=where), self.assertRaises(ValueError) as e:
                mini(self, edit)
            self.assertIn(where, str(e.exception))
            self.assertIn('unknown key', str(e.exception))

    def test_a_bad_value_is_refused_by_name(self):
        for old, new, why in (('kind = "solid"', 'kind = "braid"', 'kind'),
                              ('exception = "P1 regulator"', 'exception = "convenience"', 'exception'),
                              ('segment = "PATH_PACK_POS"', 'segment = "PATH_ELSEWHERE"', 'segment'),
                              ('b = "J:STAR.1"', 'b = "J:STAR.6"', 'positions 1 to 5'),
                              ('b = "CHGR.BATT2"', 'b = "CHGR.NOPE"', "no pin or terminal 'NOPE'")):
            with self.subTest(why=why), self.assertRaises(ValueError) as e:
                mini(self, lambda t, o=old, n=new: t.replace(o, n, 1))
            self.assertIn(why, str(e.exception))
        with self.assertRaises(ValueError) as e:   # a bad role, on the TIE only
            mini(self, lambda t: t.replace('role = "force"\ngauge = 22', 'role = "heavy"\ngauge = 22'))
        self.assertIn('lead L_TIE', str(e.exception))
        self.assertIn("role 'heavy'", str(e.exception))

    def test_lead_lengths_are_not_checked_on_load(self):
        # H7 belongs to checks.py: a 1000 mm pigtail still loads.
        w = mini(self, lambda t: t.replace('length_mm = 60', 'length_mm = 1000', 1))
        self.assertEqual(w.leads[0].length_mm, 1000.0)

    def test_joints_and_internal_ties_join_in_connectivity_and_prove(self):
        w = mini(self)
        jumpers = wiring.plan_jumpers(w)
        batt = next(g for g in wiring.connectivity(w, jumpers) if 'PACK.+' in g)
        self.assertEqual(batt, {'PACK.+', 'J:BATTJ', 'CHGR.BATT2', 'CHGR.LIPO'})
        gnd = next(g for g in wiring.connectivity(w, jumpers) if 'J:STAR' in g)
        self.assertTrue({'PACK.-', 'CHGR.GND', 'CHGR.GND3', 'CHGR.SYSOUT1', 'N:CN6.6', 'N:CN6.7'} <= gnd)
        # Without the tie inside the charger, or without the joint's second lead, BATT is in pieces.
        chgr = w.parts['CHGR']
        untied = with_part(w, dataclasses.replace(chgr, internal=chgr.internal[1:]))
        self.assertIn('open: BATT is in 2 pieces', wiring.prove(untied, jumpers))
        no_lead = dataclasses.replace(w, leads=tuple(k for k in w.leads if k.id != 'L_BATT_POS'))
        self.assertIn('open: BATT is in 2 pieces', wiring.prove(no_lead, jumpers))

    def test_an_internal_tie_of_two_nets_is_a_short(self):
        w = mini(self)
        chgr = w.parts['CHGR']
        bad = with_part(w, dataclasses.replace(chgr, internal=(*chgr.internal, ('OUT', 'CHG'))))
        problems = wiring.prove(bad, wiring.plan_jumpers(w))
        self.assertTrue(any(p.startswith('short: CHG and SYS_OUT') for p in problems), problems)

    def test_an_insulated_end_joins_nothing(self):
        w = mini(self)
        lead = next(k for k in w.leads if k.id == 'L_SYSOUT_NEG')
        self.assertTrue(lead.insulated)
        self.assertIsNone(wiring.raw_node(w, 'insulated'))
        self.assertEqual(wiring.prove(w, wiring.plan_jumpers(w)), [])
        for old, new, why in (('b = "insulated"\ninsulated = true', 'b = "CHGR.SYSOUT2"', 'not two members of one net'),
                              ('b = "insulated"\ninsulated = true', 'b = "CHGR.GND"\ninsulated = true',
                               'needs an end "insulated"'),
                              ('a = "CHGR.SYSOUT1"', 'a = "insulated"', 'not two members of one net')):
            with self.subTest(why=why), self.assertRaises(ValueError) as e:
                mini(self, lambda t, o=old, n=new: t.replace(o, n))
            self.assertIn(why, str(e.exception))

    def test_a_terminal_joins_only_by_leads(self):
        w = mini(self)
        groups = wiring.connectivity(w, wiring.plan_jumpers(w))
        self.assertIn({'CHGR.USBC'}, groups)   # no lead: alone, though its part sits on the breadboard
        self.assertEqual(wiring.raw_node(w, 'CHGR.BATT2'), 'T:CHGR.BATT2')
        self.assertEqual(wiring.raw_node(w, 'CHGR.LIPO'), 'B:a-e:51')
        with self.assertRaises(ValueError) as e:
            mini(self, lambda t: t.replace('terminals = ["BATT1"', 'terminals = ["GND", "BATT1"'))
        self.assertIn('repeats a pin name', str(e.exception))
        with self.assertRaises(ValueError) as e:
            mini(self, lambda t: t.replace('test_points = ["GND"', 'test_points = ["BATT1", "GND"'))
        self.assertIn('not header pins', str(e.exception))

    def test_a_place_mm_part_reserves_no_strip(self):
        w = mini(self)
        pack = w.parts['PACK']
        self.assertEqual((pack.pins, pack.origin, pack.place_mm, pack.off_board), ({}, None, (10.0, 70.0), True))
        self.assertEqual(wiring.off_board_holes(w), set())
        # The model's own off-board parts (change A) are all placed by place_mm: they reserve no strip.
        real = wiring.load(DATA)
        self.assertTrue(all(p.place_mm for p in real.parts.values() if p.off_board))
        self.assertEqual(wiring.off_board_holes(real), set())
        with self.assertRaises(ValueError) as e:
            mini(self, lambda t: t.replace('place_mm = [10.0, 70.0]', 'place_mm = [10.0, 70.0]\norigin = ["f", 1]'))
        self.assertIn('part PACK', str(e.exception))

    def test_end_xy(self):
        w = mini(self)
        bx = wiring.BOARD_X['B']
        self.assertEqual(wiring.end_xy(w, 'B:j44'), wiring.hole_xy(('B', 'j', 44)))
        self.assertEqual(wiring.end_xy(w, 'RPU.1'), wiring.hole_xy(('B', 'f', 40)))
        self.assertEqual(wiring.end_xy(w, 'J:STAR.1'), (bx, 60.0))
        self.assertEqual(wiring.end_xy(w, 'J:STAR.4'), (bx + 3*wiring.JOINT_PITCH, 60.0))
        self.assertEqual(wiring.end_xy(w, 'CHGR.BATT2'), wiring.hole_xy(('B', 'a', 50)))   # its part's origin
        self.assertEqual(wiring.end_xy(w, 'PACK.+'), (bx + 10.0, 70.0))
        self.assertIsNone(wiring.end_xy(w, 'N:CN6.6'))


class Planner(unittest.TestCase):
    """Build-progression BP-061: a jumper lands only where the model allows it."""

    def test_a_tie_offers_only_the_pins_the_net_names(self):
        # (a) CN8.2 and CN7.30 are both PB2; VANE names CN8.2 only, so the jumper may not take CN7.30,
        # which is nearer to VR on the drawing.
        w = mini(self)
        strip_holes = [h for h in wiring.board_holes('A') if wiring.strip(h) == wiring.strip(w.parts['VR'].pins['1'])]
        near = min(strip_holes, key=lambda h: wiring._distance(h, ('N', 'CN8', 2)))
        self.assertLess(wiring._distance(near, ('N', 'CN7', 30)), wiring._distance(near, ('N', 'CN8', 2)))
        ends = jumper_ends(wiring.plan_jumpers(w), 'VANE')
        self.assertIn(('N', 'CN8', 2), ends)
        self.assertNotIn(('N', 'CN7', 30), ends)

    def test_a_lead_end_is_never_a_jumper_end(self):
        # (b) the TIE holds CN6.6, so the logic ground jumper takes CN6.7 though CN6.6 is nearer.
        w = mini(self, lambda t: with_gnd_member(t, 'RG.1'), LOGIC_GND)
        rg = w.parts['RG'].pins['1']
        self.assertLess(wiring._distance(rg, ('N', 'CN6', 6)), wiring._distance(rg, ('N', 'CN6', 7)))
        ends = jumper_ends(wiring.plan_jumpers(w), 'GND')
        self.assertIn(('N', 'CN6', 7), ends)
        self.assertNotIn(('N', 'CN6', 6), ends)
        # A lead parked in hole j44 (the PULL strip's nearest to the NUCLEO) keeps the jumper off it.
        probe = '\n[[lead]]\nid = "L_PROBE"\na = "B:j44"\nb = "insulated"\nrole = "sense"\ngauge = 22\nkind = "solid"\nlength_mm = 100\n'
        self.assertIn(('B', 'j', 44), jumper_ends(wiring.plan_jumpers(mini(self)), 'PULL'))
        w = mini(self, extra=probe)
        self.assertEqual(next(k.net for k in w.leads if k.id == 'L_PROBE'), 'PULL')
        ends = jumper_ends(wiring.plan_jumpers(w), 'PULL')
        self.assertNotIn(('B', 'j', 44), ends)
        self.assertEqual(wiring.prove(w, wiring.plan_jumpers(w)), [])

    def test_a_test_point_strip_is_never_a_jumper_end(self):
        # (c) without the TIE, logic ground could reach STAR only through a charger GND strip: refused.
        def no_tie(t):
            return with_gnd_member(without_lead(t, 'L_TIE'), 'RG.1')
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(mini(self, no_tie, LOGIC_GND))
        self.assertIn('no free hole', str(e.exception))
        # The same model without the test points plans a jumper into a charger GND strip.
        w = mini(self, lambda t: no_tie(t).replace('test_points = ["GND", "LIPO", "GND2", "OUT", "GND3"]\n', ''), LOGIC_GND)
        gnd_strips = {wiring.strip(w.parts['CHGR'].pins[n]) for n in ('GND', 'GND2', 'GND3')}
        self.assertTrue({wiring.strip(h) for h in jumper_ends(wiring.plan_jumpers(w), 'GND')} & gnd_strips)

    def test_a_power_only_strip_is_never_a_jumper_end(self):
        load_part = ('\n[[part]]\nid = "RL"\nkind = "load"\nboard = "B"\norigin = ["f", 20]\nstep = 4\n'
                     'pins = ["1", "2"]\nsource = "passive"\n')
        def edit(t):
            return with_gnd_member(t, 'RL.2')
        w = mini(self, edit, load_part)
        self.assertIn('B:f-j:24', {wiring.strip(h) for h in jumper_ends(wiring.plan_jumpers(w), 'GND')})
        powered = load_part.replace('source = "passive"', 'source = "passive"\ndomain = "power"')
        w = mini(self, edit, powered)
        self.assertIn('B:f-j:24', wiring.forbidden_strips(w))
        with self.assertRaises(wiring.PlanError) as e:
            wiring.plan_jumpers(w)
        self.assertIn('B:f-j:24', str(e.exception))


REVERSE_GUIDE = '''# Guide

## 2. The connections

| Function | Pin | Header | Wiring |
|---|---|---|---|
| bq24074 CHG | PB10 | CN9.7 | direct |
| Sensor switch | PA9 | CN5.2 | protoboard only: not on the breadboard |
| Mux reset | PB14 | CN8.5 | carrier only |
| Bench OLED CS | PA4 | CN5.3 | bench only |
| Bench probe | PB15 | CN10.28 | bench only |
| Hub power | 3V3, GND | CN6.4, CN6.6 | 3.3 V only |

## 3. Next
'''


class GuideBothWays(unittest.TestCase):
    """Record D3 check 7: the guide's rows map to model nets."""

    def guide(self, text):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_the_reverse_check_reads_the_real_columns(self):
        rows = wiring.guide_table(GUIDE)
        self.assertTrue(rows)
        self.assertTrue({'Function', 'Pin', 'Wiring'} <= set(rows[0]))

    def test_exempt_rows_and_bench_only_rows(self):
        w = wiring.load(DATA)
        problems = wiring.check_guide_reverse(w, self.guide(REVERSE_GUIDE))
        self.assertEqual(problems, ['Bench probe (PB15): the guide wires it; the model has no net with mcu = PB15'])

    def test_a_deleted_net_is_found(self):
        w = wiring.load(DATA)
        nets = {k: v for k, v in w.nets.items() if k != 'CHG'}
        mcu = {k: v for k, v in w.mcu.items() if k != 'CHG'}
        problems = wiring.check_guide_reverse(dataclasses.replace(w, nets=nets, mcu=mcu), GUIDE)
        self.assertTrue(any('(PB10)' in p for p in problems), problems)
        self.assertFalse(any('(PA9)' in p for p in problems), 'the PA9 row is exempt (change C not built)')

    def test_the_pa9_row_is_exempt(self):
        # Record 4.6 (2026-11-02): change C is not part of the breadboard build, so the guide's PA9 row is exempt and the
        # model, which has no SENS_EN, passes; were the row not exempt, the reverse check would catch it.
        w = wiring.load(DATA)
        row = next(r for r in wiring.guide_table(GUIDE) if r['Pin'] == 'PA9')
        self.assertIn('carrier only', row['Wiring'].lower())
        self.assertNotIn('SENS_EN', w.nets)
        self.assertFalse(any('(PA9)' in p for p in wiring.check_guide_reverse(w, GUIDE)))
        text = Path(GUIDE).read_text()
        line = next(ln for ln in text.splitlines() if ln.startswith('| Sensor power enable | PA9 |'))
        bare = self.guide(text.replace(line, '| Sensor power enable | PA9 | D9, CN5.2 | a jumper |'))
        self.assertTrue(any('(PA9)' in p for p in wiring.check_guide_reverse(w, bare)))

    def test_a_tied_header_in_a_comment_is_accepted(self):
        w = wiring.load(DATA)
        m = wiring.PIN_DEFINE.search('#define CHG_PIN GPIO_PIN_10 /* PB10, CN10.25: CHG */')
        self.assertEqual(wiring._check_comment(w, 'f.c', 'CHG_PIN', 'CHG', m), [])   # the morpho alias of CN9.7
        self.assertIn('CN10.25', wiring.tied_headers(w, 'CHG'))
        untied = dataclasses.replace(w, ties=tuple(t for t in w.ties if 'CN10.25' not in t))
        self.assertTrue(wiring._check_comment(untied, 'f.c', 'CHG_PIN', 'CHG', m))

class Cn9(unittest.TestCase):
    """CN9 (ARDUINO D0-D7): a female single row of eight on CN5's line, above it, with the 160 mil gap
    between D7 (CN9.8) and D8 (CN5.1) (UM2592 Table 17, Figure 24)."""

    def test_cn9_is_a_female_single_row_of_eight_above_cn5(self):
        self.assertEqual(wiring.HEADERS['CN9'][1:], (1, 8))
        self.assertIn('CN9', wiring.FEMALE)
        holes = [wiring.hole_xy(('N', 'CN9', pin)) for pin in range(1, 9)]
        cn5 = [wiring.hole_xy(('N', 'CN5', pin)) for pin in range(1, 11)]
        self.assertEqual({x for x, _y in holes}, {cn5[0][0]})
        self.assertEqual([round(y - holes[0][1], 4) for _x, y in holes], [round(i*wiring.PITCH, 4) for i in range(8)])
        self.assertAlmostEqual(cn5[0][1] - holes[-1][1], 4.064)   # D7 (CN9.8) to D8 (CN5.1): 160 mil
        self.assertEqual([round(y - cn5[0][1], 4) for _x, y in cn5], [round(i*wiring.PITCH, 4) for i in range(10)])
        self.assertAlmostEqual(holes[0][1], wiring.NUCLEO_Y)   # the band above the headers is untouched
        d15_side = min(abs(y - cn5[-1][1]) for _x, y in holes)
        self.assertGreater(d15_side, 4*wiring.PITCH)            # D0 is nowhere near SCL/D15
        with self.assertRaises(ValueError):
            wiring.hole_xy(('N', 'CN9', 9))
        others = {wiring.hole_xy(('N', h, p)) for h, (_x, _c, n) in wiring.HEADERS.items() if h != 'CN9' for p in range(1, n + 1)}
        self.assertFalse(set(holes) & others)
        bottom = max(wiring.hole_xy(('N', 'CN7', p))[1] for p in range(1, 39))
        self.assertLess(holes[-1][1], bottom)

    def test_cn9_wires_share_cn5s_approach_columns(self):
        jumpers = [wiring.Jumper(id='W1', net='X', a=('A', 'j', 5), b=('N', 'CN5', 9)),
                   wiring.Jumper(id='W2', net='X', a=('A', 'j', 7), b=('N', 'CN9', 7)),
                   wiring.Jumper(id='W3', net='X', a=('A', 'j', 9), b=('N', 'CN9', 5))]
        paths = flying.plan(jumpers)
        cn5x = wiring.hole_xy(('N', 'CN5', 1))[0]
        columns = [paths[j][-2][0] for j in ('W3', 'W2', 'W1')]   # shallowest pin first: CN9 is above CN5
        self.assertEqual(columns, [cn5x - flying.APPROACH_FIRST - k*flying.APPROACH_PITCH for k in range(3)])

    def test_overlapping_approach_columns_are_refused(self):
        # Eight wires into CN8 reach past CN6's column, into the band CN6's own wires use.
        jumpers = [wiring.Jumper(id=f'W{i}', net='X', a=('A', 'j', i + 1), b=('N', 'CN8', 1 + i % 6)) for i in range(8)]
        jumpers.append(wiring.Jumper(id='W9', net='X', a=('A', 'j', 30), b=('N', 'CN6', 4)))
        with self.assertRaises(ValueError) as e:
            flying.plan(jumpers)
        self.assertIn('overlap', str(e.exception))


if __name__ == '__main__':
    unittest.main()
