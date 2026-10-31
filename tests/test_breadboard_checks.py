"""The build-progression record's model checks (hardware/bench-breadboard-r0/source/checks.py).

Record docs/superpowers/specs/2026-10-29-build-progression-decisions.md, D3 checks 1-6 and 9, check 8's
ISET constants (step 1 exit 7), H7 and M6. Each check runs against a small change-A-shaped fixture model (written to a temporary
wiring.toml and read through wiring.load): once as built, where every check passes, and once broken
in one place, where exactly the check under test fails and every other check stays clean (record 6.2).
The committed model is held to run_all once it carries the change-A joints (record 6.1).
Repository Python only, no KiCad."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT/'hardware'/'bench-breadboard-r0'
sys.path.insert(0, str(HW/'source'))
import checks  # noqa: E402
import wiring  # noqa: E402

P1 = 'P1 regulator'
CHANGE_A_JOINTS = ('WAGO_CELL_POS', 'WAGO_BATT', 'WAGO_SYS_OUT', 'WAGO_STAR')   # record 6.1


def _part(pid, **kw):
    return {'id': pid, 'kind': kw.pop('kind', pid), 'source': 'bench check', **kw}


def _lead(lid, a, b, role, kind, length, gauge=22, **kw):
    return {'id': lid, 'a': a, 'b': b, 'role': role, 'kind': kind, 'gauge': gauge, 'length_mm': length, **kw}


# A change-A-shaped station: the pack and the load off-board, the battery path on lever connectors and
# leads, the regulator chain tagged, L_TIE the one STAR-to-logic crossing, the OLED on its own leads.
# Places are mm from board B's origin; lengths clear H7 and the drawn spans.
BASE = {
    'version': 1, 'revision': 'fixture', 'split_rails': False,
    'nucleo': {'ties': [['CN6.4', 'CN7.16'], ['CN6.6', 'CN6.7', 'CN10.20']]},
    'part': [
        _part('PACK', place_mm=[50.0, -60.0], terminals=['+', '-'], domain='power'),
        _part('GAUGE', place_mm=[90.0, -50.0], terminals=['BAT1+']),
        _part('RLOAD', place_mm=[0.0, -40.0], terminals=['1', '2']),
        _part('NTC', place_mm=[150.0, -50.0], terminals=['1', '2']),
        _part('CHGR', board='B', origin=['a', 50], step=1, pins=['GND', 'LIPO', 'OUT', 'THERM'],
              terminals=['BATT1', 'BATT2', 'SYSOUT2'], internal=[['GND', 'BATT1'], ['LIPO', 'BATT2'], ['OUT', 'SYSOUT2']],
              test_points=['GND', 'LIPO', 'OUT'], iset_ohms=1000),
        _part('INA', board='B', origin=['a', 40], step=1, pins=['VIN+', 'VIN-'],
              terminals=['X1_VINP', 'X1_VINM', 'X1_VBUS'], internal=[['VIN+', 'X1_VINP'], ['VIN-', 'X1_VINM']],
              test_points=['VIN+', 'VIN-']),
        _part('REG', board='B', origin=['a', 30], step=1, pins=['VIN', 'GND', 'VOUT']),
        _part('SHUNT', board='B', origin=['a', 58], step=1, pins=['1', '2'], exception=P1),
        _part('R4', board='B', origin=['f', 5], step=2, pins=['1', '2'], ohms=10000),
        _part('R5', board='B', origin=['f', 9], step=2, pins=['1', '2'], ohms=10000),
        _part('R6', board='B', origin=['f', 13], step=2, pins=['1', '2'], ohms=10000),
        _part('R_ISER', board='B', origin=['f', 17], step=2, pins=['1', '2'], ohms=10000),
        _part('R_IPD', board='B', origin=['f', 21], step=2, pins=['1', '2'], ohms=1000000),
        _part('QT', board='A', origin=['a', 2], step=1, pins=['GND', 'V+']),
        _part('OLED', board='C', origin=['a', 22], step=1, pins=['GND', 'VCC']),
    ],
    'joint': [
        {'id': 'WAGO_STAR', 'kind': 'WAGO 222-415', 'positions': 5, 'place_mm': [30.0, -30.0], 'domain': 'power'},
        {'id': 'WAGO_CELL_POS', 'kind': 'WAGO 222-415', 'positions': 5, 'place_mm': [60.0, -30.0]},
        {'id': 'WAGO_BATT', 'kind': 'WAGO 222-413', 'positions': 3, 'place_mm': [40.0, -10.0]},
        {'id': 'WAGO_SYS_OUT', 'kind': 'WAGO 222-415', 'positions': 5, 'place_mm': [10.0, -10.0]},
    ],
    'link': [
        {'id': 'LK_REG_SHUNT', 'a': 'REG.VOUT', 'b': 'SHUNT.1', 'exception': P1},
        {'id': 'LK_3V3_CN6_4', 'a': 'QT.V+', 'b': 'N:CN6.4', 'exception': P1},
        {'id': 'LK_QT_GND_CN6_6', 'a': 'QT.GND', 'b': 'N:CN6.6'},
    ],
    'net': [
        {'name': 'CELL_POS', 'class': 'battery lead',
         'members': ['PACK.+', 'J:WAGO_CELL_POS', 'INA.X1_VINP', 'INA.VIN+', 'GAUGE.BAT1+']},
        {'name': 'BATT', 'class': 'battery lead',
         'members': ['INA.X1_VINM', 'INA.VIN-', 'J:WAGO_BATT', 'CHGR.BATT2', 'CHGR.LIPO']},
        {'name': 'SYS_OUT', 'class': 'power',
         'members': ['CHGR.SYSOUT2', 'CHGR.OUT', 'J:WAGO_SYS_OUT', 'INA.X1_VBUS', 'REG.VIN', 'RLOAD.1']},
        {'name': 'REG_OUT', 'class': 'power', 'members': ['REG.VOUT', 'SHUNT.1']},
        {'name': '3V3', 'mcu': '3V3', 'class': 'power',
         'members': ['N:CN6.4', 'N:CN7.16', 'QT.V+', 'SHUNT.2', 'OLED.VCC']},
        {'name': 'GND', 'mcu': 'GND', 'class': 'ground', 'rails': ['B:L-'],
         'members': ['PACK.-', 'J:WAGO_STAR', 'CHGR.BATT1', 'CHGR.GND', 'RLOAD.2', 'REG.GND', 'N:CN6.6',
                     'N:CN6.7', 'N:CN10.20', 'QT.GND', 'OLED.GND', 'NTC.2']},
        {'name': 'THERM', 'class': 'charger', 'members': ['CHGR.THERM', 'NTC.1']},
    ],
    'lead': [
        _lead('L_PACK_POS', 'PACK.+', 'J:WAGO_CELL_POS.1', 'force', 'pigtail', 50, 26, segment='PATH_PACK_POS'),
        _lead('L_PACK_NEG', 'PACK.-', 'J:WAGO_STAR.1', 'force', 'pigtail', 50, 26, segment='PATH_PACK_NEG',
              domain='power'),
        _lead('L_CELL_INA', 'J:WAGO_CELL_POS.2', 'INA.X1_VINP', 'force', 'solid', 45),
        _lead('L_INA_BATT', 'INA.X1_VINM', 'J:WAGO_BATT.1', 'force', 'solid', 40),
        _lead('L_BATT_POS', 'J:WAGO_BATT.2', 'CHGR.BATT2', 'force', 'pigtail', 50, 26),
        _lead('L_BATT_NEG', 'CHGR.BATT1', 'J:WAGO_STAR.2', 'force', 'pigtail', 50, 26, domain='power'),
        _lead('L_SYSOUT_POS', 'CHGR.SYSOUT2', 'J:WAGO_SYS_OUT.1', 'force', 'pigtail', 50, 26),
        _lead('L_RLOAD_A', 'RLOAD.1', 'J:WAGO_SYS_OUT.2', 'force', 'solid', 45),
        _lead('L_RLOAD_B', 'RLOAD.2', 'J:WAGO_STAR.3', 'force', 'solid', 45, domain='power'),
        _lead('L_VBUS', 'INA.X1_VBUS', 'J:WAGO_SYS_OUT.3', 'sense', 'solid', 60, 26),
        _lead('L_GAUGE_POS', 'GAUGE.BAT1+', 'J:WAGO_CELL_POS.3', 'sense', 'pigtail', 50, 26),
        _lead('L_REG_VIN', 'J:WAGO_SYS_OUT.4', 'B:c30', 'force', 'solid', 80, exception=P1),
        _lead('L_TIE', 'J:WAGO_STAR.4', 'B:c31', 'force', 'solid', 80, exception=P1),
        _lead('L_NUC_RET', 'N:CN6.7', 'B:d31', 'force', 'solid', 150, exception=P1),
        _lead('L_REG_3V3', 'B:c59', 'A:c3', 'force', 'solid', 150, exception=P1),
        _lead('L_OLED_GND', 'C:c22', 'N:CN10.20', 'supply', 'dupont', 300, 24),
        _lead('L_OLED_VCC', 'C:c23', 'N:CN7.16', 'supply', 'dupont', 300, 24),
        _lead('L_NTC_THERM', 'NTC.1', 'B:c53', 'sense', 'solid', 200, 26),
        _lead('L_NTC_RET', 'NTC.2', 'B:L-5', 'sense', 'solid', 120, 26),
    ],
}


def _value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_value(x) for x in v) + ']'
    return repr(v)


def to_toml(data):
    """The fixture dict as wiring.toml text."""
    lines = [f'{k} = {_value(data[k])}' for k in ('version', 'revision', 'split_rails')]
    lines += ['', '[nucleo]', f'ties = {_value(data["nucleo"]["ties"])}']
    for table in ('part', 'joint', 'link', 'net', 'lead'):
        for item in data.get(table, []):
            lines += ['', f'[[{table}]]'] + [f'{k} = {_value(v)}' for k, v in item.items()]
    return '\n'.join(lines) + '\n'


def item(data, table, iid):
    key = 'name' if table == 'net' else 'id'
    return next(t for t in data[table] if t[key] == iid)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = copy.deepcopy(BASE)

    def load(self, data=None):
        path = Path(self.tmp.name)/'wiring.toml'
        path.write_text(to_toml(self.data if data is None else data))
        return wiring.load(path)

    def lead(self, lid):
        return item(self.data, 'lead', lid)

    def assertOne(self, problems, *words):
        """Exactly one problem, and it names each word."""
        self.assertEqual(len(problems), 1, problems)
        for word in words:
            self.assertIn(word, problems[0])

    def only(self, name, w=None, jumpers=None, root=None):
        """The problems of check `name` on the model (the fixture by default), after asserting that it
        fails and that every other check passes."""
        w = self.load() if w is None else w
        jumpers = wiring.plan_jumpers(w) if jumpers is None else jumpers
        root = write_firmware(self.tmp.name) if root is None else root
        each = checks.run_each(w, jumpers, root)
        others = {k: v for k, v in each.items() if k != name and v}
        self.assertEqual(others, {}, f'only {name} should fail')
        self.assertTrue(each[name], f'{name} should fail')
        return each[name]


class ForceOffBreadboard(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_force_off_breadboard(self.load()), [])

    def test_the_chain_is_the_seven_of_the_record(self):
        self.assertEqual(set(checks.P1_CHAIN), {'L_REG_VIN', 'L_TIE', 'L_NUC_RET', 'LK_REG_SHUNT', 'SHUNT',
                                                'L_REG_3V3', 'LK_3V3_CN6_4'})

    def test_a_force_lead_into_a_hole_fails(self):
        jumpers = wiring.plan_jumpers(self.load())   # the as-built jumpers: the break is the lead alone
        self.lead('L_CELL_INA')['b'] = 'B:c45'   # a breadboard hole instead of the screw terminal
        self.lead('L_CELL_INA')['length_mm'] = 50
        self.assertOne(self.only('check_force_off_breadboard', jumpers=jumpers), 'L_CELL_INA', 'B:c45')

    def test_a_force_member_off_its_test_point_fails(self):
        item(self.data, 'part', 'INA')['test_points'] = ['VIN-']
        self.assertOne(self.only('check_force_off_breadboard'), 'INA.VIN+')

    def test_a_sys_out_member_in_a_hole_fails(self):
        # SYS_OUT is class 'power' but carries the load current (L_SYSOUT_POS, L_RLOAD_A are force).
        self.data['part'].append(_part('CLOAD', board='B', origin=['a', 20], step=1, pins=['1', '2']))
        item(self.data, 'net', 'SYS_OUT')['members'].append('CLOAD.1')
        item(self.data, 'net', 'GND')['members'].append('CLOAD.2')
        self.assertOne(self.only('check_force_off_breadboard'), 'SYS_OUT', 'CLOAD.1')

    def test_a_power_ground_member_in_a_hole_fails(self):
        # The load return plugged into board B: RLOAD.2 is power ground through L_RLOAD_B's domain.
        self.data['part'].append(_part('CLOAD', board='B', origin=['a', 20], step=1, pins=['1', '2']))
        item(self.data, 'net', 'SYS_OUT')['members'].append('CLOAD.1')
        item(self.data, 'net', 'GND')['members'].append('CLOAD.2')
        self.data['lead'].append(_lead('L_CLOAD_RET', 'CLOAD.2', 'J:WAGO_STAR.3', 'sense', 'solid', 60,
                                       domain='power'))
        self.lead('L_RLOAD_B')['b'] = 'J:WAGO_STAR.2'
        problems = checks.check_force_off_breadboard(self.load())
        self.assertTrue(any('GND: CLOAD.2' in p for p in problems), problems)

    def test_the_regulator_pins_pass_only_under_a_tagged_landing(self):
        self.lead('L_REG_VIN')['b'] = 'B:c33'   # the chain lead leaves REG.VIN's strip (a30)
        problems = checks.check_force_off_breadboard(self.load())
        self.assertTrue(any('SYS_OUT: REG.VIN' in p for p in problems), problems)

    def test_an_untagged_chain_member_fails(self):
        for table, iid in (('lead', 'L_REG_VIN'), ('lead', 'L_TIE'), ('lead', 'L_NUC_RET'), ('link', 'LK_REG_SHUNT'),
                           ('part', 'SHUNT'), ('lead', 'L_REG_3V3'), ('link', 'LK_3V3_CN6_4')):
            with self.subTest(iid):
                self.data = copy.deepcopy(BASE)
                del item(self.data, table, iid)['exception']
                problems = self.only('check_force_off_breadboard')
                self.assertTrue(any(iid in p and 'without exception' in p for p in problems), problems)

    def test_a_tag_outside_the_chain_fails(self):
        for table, iid in (('lead', 'L_CELL_INA'), ('part', 'REG')):
            with self.subTest(iid):
                self.data = copy.deepcopy(BASE)
                item(self.data, table, iid)['exception'] = P1
                self.assertOne(self.only('check_force_off_breadboard'), iid, 'outside the P1 chain')

    def test_a_chain_through_a_rail_run_fails(self):
        # P1_ORDER: L_REG_3V3 must land where LK_3V3_CN6_4 starts (the QT.V+ strip here), not on a rail
        # that a planner jumper then joins to that strip.
        item(self.data, 'net', '3V3')['rails'] = ['A:L+']
        self.lead('L_REG_3V3')['b'] = 'A:L+20'
        self.assertOne(self.only('check_force_off_breadboard'), 'L_REG_3V3', 'LK_3V3_CN6_4', 'planner jumper')

    def test_a_missing_chain_member_fails(self):
        self.data['link'] = [k for k in self.data['link'] if k['id'] != 'LK_3V3_CN6_4']
        self.data['link'].append({'id': 'LK_3V3', 'a': 'QT.V+', 'b': 'N:CN6.4'})
        self.assertOne(self.only('check_force_off_breadboard'), 'LK_3V3_CN6_4', 'missing')


class SenseLandings(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_sense_landings(self.load()), [])

    def test_two_lead_ends_on_one_joint_position_fail(self):
        self.lead('L_GAUGE_POS')['b'] = 'J:WAGO_CELL_POS.2'   # the force lead L_CELL_INA's clamp
        self.assertOne(self.only('check_sense_landings'), 'J:WAGO_CELL_POS.2', 'L_CELL_INA', 'L_GAUGE_POS')

    def test_a_sense_lead_on_a_current_strip_fails(self):
        self.lead('L_VBUS')['b'] = 'B:d30'   # the regulator VIN strip: SYS_OUT current
        self.lead('L_VBUS')['length_mm'] = 120
        self.assertOne(self.only('check_sense_landings'), 'L_VBUS', 'B:d30')

    def test_a_sense_lead_off_its_declared_landing_fails(self):
        jumpers = wiring.plan_jumpers(self.load())   # the as-built jumpers: the break is the lead alone
        self.lead('L_NTC_THERM')['b'] = 'B:c45'   # an empty strip, not the THERM pin's
        self.assertOne(self.only('check_sense_landings', jumpers=jumpers), 'L_NTC_THERM', 'declared landing',
                       'THERM')

    def test_a_sense_lead_on_a_test_point_strip_is_check_6s(self):
        self.lead('L_VBUS')['b'] = 'B:d52'   # the charger's OUT test point
        self.lead('L_VBUS')['length_mm'] = 120
        self.assertEqual(checks.check_sense_landings(self.load()), [])
        self.assertOne(self.only('check_test_point_strips'), 'CHGR.OUT', 'L_VBUS')


class SingleTie(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_single_tie(self.load()), [])

    def test_a_second_tie_fails(self):
        self.data['lead'].append(_lead('L_TIE2', 'J:WAGO_STAR.5', 'B:L-20', 'signal', 'dupont', 200))
        problems = self.only('check_single_tie')
        self.assertTrue(any('L_TIE2 also join' in p for p in problems), problems)
        self.assertTrue(any('without L_TIE' in p for p in problems), problems)

    def test_no_tie_fails(self):
        w = self.load()
        w = wiring.dataclasses.replace(w, leads=tuple(k for k in w.leads if k.id != 'L_TIE'))
        problems = checks.check_single_tie(w, wiring.plan_jumpers(self.load()))
        self.assertTrue(any('no lead L_TIE' in p for p in problems), problems)

    def test_the_oled_ground_on_a_b_rail_fails(self):
        self.lead('L_OLED_GND')['a'] = 'B:L-30'
        problems = self.only('check_single_tie')
        self.assertTrue(any('L_OLED_GND: ends on the board-B rail' in p for p in problems), problems)

    def test_the_oled_ground_reaching_the_b_rail_another_way_fails(self):
        w = self.load()
        extra = wiring.Jumper(id='WX', net='GND', a=('C', 'b', 22), b=('B', 'L-', 40))
        self.assertOne(self.only('check_single_tie', w, wiring.plan_jumpers(w) + [extra]), 'OLED.GND', 'N:CN10.20')

    def test_star_position_five_used_fails(self):
        self.data['lead'].append(_lead('L_RLOAD2', 'J:WAGO_STAR.5', 'RLOAD.2', 'sense', 'solid', 100))
        self.assertOne(self.only('check_single_tie'), 'L_RLOAD2', 'position 5')


class GaugeUpstream(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_gauge_upstream(self.load()), [])

    def test_the_gauge_on_batt_fails(self):
        item(self.data, 'net', 'CELL_POS')['members'].remove('GAUGE.BAT1+')
        item(self.data, 'net', 'BATT')['members'].append('GAUGE.BAT1+')
        self.lead('L_GAUGE_POS')['b'] = 'J:WAGO_BATT.3'
        self.lead('L_GAUGE_POS')['length_mm'] = 60
        self.assertOne(self.only('check_gauge_upstream'), 'GAUGE.BAT1+', 'BATT')


class ShuntOnly(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_shunt_only(self.load()), [])

    def test_a_lead_from_vin_plus_to_vin_minus_fails(self):
        # The lead loads only with both sides on one net: the declared nets fail, and so does the joint.
        item(self.data, 'net', 'BATT')['members'].remove('INA.VIN-')
        item(self.data, 'net', 'CELL_POS')['members'].append('INA.VIN-')
        self.data['lead'].append(_lead('L_SHORT', 'B:c40', 'B:c41', 'signal', 'solid', 10))
        problems = checks.check_shunt_only(self.load(), [])
        self.assertTrue(any('both sides are on CELL_POS' in p for p in problems), problems)
        self.assertTrue(any('joined other than through the shunt' in p for p in problems), problems)

    def test_a_jumper_across_the_shunt_fails(self):
        # Also lands on both test-point strips, so check 6 fails with it.
        w = self.load()
        extra = wiring.Jumper(id='WX', net='BATT', a=('B', 'c', 40), b=('B', 'c', 41))
        self.assertOne(checks.check_shunt_only(w, wiring.plan_jumpers(w) + [extra]), 'joined other than')

    def test_a_bypass_off_the_breadboard_fails_only_check_5(self):
        # An off-board part whose two terminals are tied inside it, between the two lever connectors.
        self.data['part'].append(_part('BYP', place_mm=[50.0, -20.0], terminals=['X', 'Y'], internal=[['X', 'Y']]))
        item(self.data, 'net', 'CELL_POS')['members'].append('BYP.X')
        item(self.data, 'net', 'BATT')['members'].append('BYP.Y')
        self.data['lead'] += [_lead('L_BYP_X', 'BYP.X', 'J:WAGO_CELL_POS.4', 'signal', 'solid', 50),
                              _lead('L_BYP_Y', 'BYP.Y', 'J:WAGO_BATT.3', 'signal', 'solid', 50)]
        self.assertOne(self.only('check_shunt_only'), 'joined other than')


class TestPointStrips(Fixture):
    def test_the_fixture_passes(self):
        w = self.load()
        self.assertEqual(checks.check_test_point_strips(w, wiring.plan_jumpers(w)), [])

    def test_a_jumper_into_a_test_point_strip_fails(self):
        w = self.load()
        extra = wiring.Jumper(id='WX', net='BATT', a=('B', 'c', 51), b=('B', 'j', 51))
        self.assertOne(self.only('check_test_point_strips', w, wiring.plan_jumpers(w) + [extra]), 'CHGR.LIPO', 'WX')

    def test_a_lead_into_a_test_point_strip_fails(self):
        self.lead('L_GAUGE_POS')['b'] = 'B:d40'   # the INA VIN+ test point (CELL_POS)
        self.lead('L_GAUGE_POS')['kind'] = 'solid'
        self.lead('L_GAUGE_POS')['length_mm'] = 120
        self.assertOne(self.only('check_test_point_strips'), 'INA.VIN+', 'L_GAUGE_POS')


NODE_ISET = '#define POWER_R_ISET_OHM 1000U\n#define POWER_ISET_GAIN_PPM 990099U\n'
HOST_ISET = 'R_ISET_OHM = 1000.0     # default of --r-iset\nISET_GAIN = 0.990099\n'


def write_firmware(tmp, node=NODE_ISET + '#define POWER_VIN_DIVIDER_PPM 3000000U\n',
                   bench='#define VIN_DIVIDER_PPM 3000000U\n', host=HOST_ISET):
    """A temporary repository root holding the node's ISET and divider defines, benchlink's divider and the
    host logger's ISET defaults (None leaves a file out)."""
    root = Path(tempfile.mkdtemp(dir=tmp))
    files = (checks.DIVIDER_DEFINES[0][0], checks.DIVIDER_DEFINES[1][0], checks.HOST_LOGGER)
    for rel, text in zip(files, (node, bench, host), strict=True):
        if text is not None:
            (root/rel).parent.mkdir(parents=True, exist_ok=True)
            (root/rel).write_text(text)
    return root


class Iset(Fixture):
    """D3 check 8's ISET constants (record step 1 exit 7, M2, 1.4)."""
    def node(self, r_iset='1000U', gain='990099U'):
        return write_firmware(self.tmp.name, node=f'#define POWER_R_ISET_OHM {r_iset}\n'
                              f'#define POWER_ISET_GAIN_PPM {gain}\n#define POWER_VIN_DIVIDER_PPM 3000000U\n')

    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_iset(self.load(), write_firmware(self.tmp.name)), [])

    def test_the_old_890_ohm_fails(self):
        self.assertOne(self.only('check_iset', root=self.node(r_iset='890U')), 'POWER_R_ISET_OHM', '890', '1000')

    def test_a_gain_one_ppm_off_fails(self):
        self.assertOne(self.only('check_iset', root=self.node(gain='990100U')), 'POWER_ISET_GAIN_PPM', '990100',
                       '990099')

    def test_a_network_change_fails_the_gain(self):
        item(self.data, 'part', 'R_IPD')['ohms'] = 470000   # 470k / 480k = 979167 ppm
        problems = self.only('check_iset')
        self.assertEqual(len(problems), 2, problems)
        self.assertIn('POWER_ISET_GAIN_PPM', problems[0])
        self.assertIn('979167', problems[0])
        self.assertIn('ISET_GAIN', problems[1])

    def test_a_measured_r_iset_moves_the_model_first(self):
        item(self.data, 'part', 'CHGR')['iset_ohms'] = 1010
        problems = self.only('check_iset')
        self.assertEqual(len(problems), 2, problems)
        self.assertIn('POWER_R_ISET_OHM 1000 does not equal the model\'s 1010', problems[0])
        self.assertIn('R_ISET_OHM', problems[1])

    def test_the_m2_fit_moves_the_model_first(self):
        # Record M2: the per-board fit goes on the charger part (iset_gain_ppm), then into both copies.
        item(self.data, 'part', 'CHGR')['iset_gain_ppm'] = 1012345
        problems = self.only('check_iset')
        self.assertEqual(len(problems), 2, problems)
        self.assertIn('POWER_ISET_GAIN_PPM 990099 does not equal the model\'s 1012345', problems[0])
        self.assertIn('the M2 fit', problems[0])
        root = write_firmware(self.tmp.name, node=f'{NODE_ISET.replace("990099", "1012345")}'
                              '#define POWER_VIN_DIVIDER_PPM 3000000U\n',
                              host=HOST_ISET.replace('0.990099', '1.012345'))
        self.assertEqual(checks.check_iset(self.load(), root), [])

    def test_a_fit_far_from_the_network_fails(self):
        item(self.data, 'part', 'CHGR')['iset_gain_ppm'] = 1200000   # 21 % above 990099
        root = write_firmware(self.tmp.name, node=f'{NODE_ISET.replace("990099", "1200000")}'
                              '#define POWER_VIN_DIVIDER_PPM 3000000U\n',
                              host=HOST_ISET.replace('0.990099', '1.2'))
        self.assertOne(self.only('check_iset', root=root), 'iset_gain_ppm', '1200000', '10%')

    def test_the_host_logger_is_held_too(self):
        root = write_firmware(self.tmp.name, host='R_ISET_OHM = 890.0\nISET_GAIN = 0.990099\n')
        self.assertOne(self.only('check_iset', root=root), 'tools/benchlink_log.py', 'R_ISET_OHM', '890')

    def test_missing_values_name_their_source(self):
        problems = checks.check_iset(self.load(), write_firmware(self.tmp.name, host=None))
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(all('tools/benchlink_log.py' in p for p in problems))
        del item(self.data, 'part', 'CHGR')['iset_ohms']
        self.assertOne(self.only('check_iset'), 'CHGR', 'iset_ohms')


class Divider(Fixture):
    def firmware(self, **kw):
        return write_firmware(self.tmp.name, **kw)

    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_divider(self.load(), self.firmware()), [])

    def test_one_ppm_off_fails(self):
        # D3 check 9: the firmware ratio equals the model's; no tolerance.
        root = self.firmware(bench='#define VIN_DIVIDER_PPM 3000001\n')
        self.assertOne(self.only('check_divider', root=root), 'VIN_DIVIDER_PPM', '3000001', '3000000')

    def test_a_ratio_with_a_fraction_is_rounded_to_the_ppm(self):
        item(self.data, 'part', 'R6')['ohms'] = 30000   # (20000 + 30000) / 30000 = 1.6666667
        root = self.firmware(node='#define POWER_VIN_DIVIDER_PPM 1666667U\n',
                             bench='#define VIN_DIVIDER_PPM 1666667U\n')
        self.assertEqual(checks.check_divider(self.load(), root), [])

    def test_a_resistor_change_fails(self):
        item(self.data, 'part', 'R6')['ohms'] = 9700   # (20000 + 9700) / 9700 = 3.062
        problems = self.only('check_divider')
        self.assertEqual(len(problems), 2, problems)
        self.assertIn('POWER_VIN_DIVIDER_PPM', problems[0])
        self.assertIn('VIN_DIVIDER_PPM', problems[1])

    def test_the_measured_ratio_moves_the_model_first(self):
        # Record M2: each resistor's DMM reading goes on its part (measured_ohms), then into both copies.
        for pid, ohms in (('R4', 10012), ('R5', 9987), ('R6', 10004)):
            item(self.data, 'part', pid)['measured_ohms'] = ohms   # (10012 + 9987 + 10004) / 10004
        problems = self.only('check_divider')
        self.assertEqual(len(problems), 2, problems)
        self.assertIn('2999100', problems[0])
        root = self.firmware(node='#define POWER_VIN_DIVIDER_PPM 2999100U\n',
                             bench='#define VIN_DIVIDER_PPM 2999100U\n')
        self.assertEqual(checks.check_divider(self.load(), root), [])

    def test_some_measured_and_some_not_fails(self):
        item(self.data, 'part', 'R6')['measured_ohms'] = 10004
        self.assertOne(self.only('check_divider'), 'R6', 'measured_ohms', 'all three')

    def test_a_missing_define_names_the_file(self):
        self.assertOne(checks.check_divider(self.load(), self.firmware(bench='#define VIN_DIVIDER 3\n')),
                       'firmware/benchlink/App/benchlink.c', 'VIN_DIVIDER_PPM')
        self.assertOne(checks.check_divider(self.load(), self.firmware(node=None)), 'power_config.h')

    def test_a_resistor_without_ohms_fails(self):
        del item(self.data, 'part', 'R5')['ohms']
        self.assertOne(self.only('check_divider'), 'R5', 'ohms')


class LeadLengths(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_lead_lengths(self.load()), [])

    def test_a_70_mm_pigtail_fails(self):
        self.lead('L_BATT_POS')['length_mm'] = 70
        self.assertOne(self.only('check_lead_lengths'), 'L_BATT_POS', '60 mm')

    def test_a_60_mm_solid_force_lead_fails(self):
        self.lead('L_CELL_INA')['length_mm'] = 60
        self.assertOne(self.only('check_lead_lengths'), 'L_CELL_INA', '50 mm')

    def test_a_120_mm_tie_fails(self):
        self.lead('L_TIE')['length_mm'] = 120
        self.assertOne(self.only('check_lead_lengths'), 'L_TIE', '100 mm')

    def test_a_150_mm_routed_lead_passes(self):
        self.lead('L_REG_3V3')['length_mm'] = 150
        self.lead('L_NUC_RET')['length_mm'] = 400
        self.assertEqual(checks.check_lead_lengths(self.load()), [])

    def test_a_routed_lead_is_judged_by_c20_c21_not_100_mm(self):
        # 6.2: L_REG_3V3 and L_NUC_RET are bounded by C20/C21 at preflight, not by H7's 100 mm here; an
        # untagged one fails D3 check 1 (its tag), not this check.
        self.lead('L_REG_3V3')['length_mm'] = 250
        del self.lead('L_REG_3V3')['exception']
        problems = self.only('check_force_off_breadboard')
        self.assertTrue(any('L_REG_3V3' in p and 'without exception' in p for p in problems), problems)
        self.assertEqual(checks.check_lead_lengths(self.load()), [])

    def test_signal_and_supply_caps(self):
        self.lead('L_OLED_VCC')['length_mm'] = 400
        self.assertOne(self.only('check_lead_lengths'), 'L_OLED_VCC', '350 mm')

    def test_sense_leads_and_cables_have_no_cap(self):
        self.lead('L_NTC_THERM')['length_mm'] = 2000
        self.assertEqual(checks.check_lead_lengths(self.load()), [])


class LeadGeometry(Fixture):
    def test_the_fixture_passes(self):
        self.assertEqual(checks.check_lead_geometry(self.load()), [])

    def test_a_lead_shorter_than_its_drawn_span_fails(self):
        self.lead('L_CELL_INA')['length_mm'] = 20
        self.assertOne(self.only('check_lead_geometry'), 'L_CELL_INA', 'shorter')

    def test_a_nucleo_end_is_skipped(self):
        self.lead('L_NUC_RET')['length_mm'] = 5
        self.assertEqual(checks.check_lead_geometry(self.load()), [])


class Segments(Fixture):
    def test_the_power_path_segments(self):
        seg = checks.power_path_segments(self.load())
        self.assertEqual(seg['PATH_POS'], [('lead', 'L_PACK_POS'), ('joint', 'WAGO_CELL_POS'), ('lead', 'L_CELL_INA'),
                                           ('part', 'INA'), ('lead', 'L_INA_BATT'), ('joint', 'WAGO_BATT'),
                                           ('lead', 'L_BATT_POS')])
        self.assertEqual(seg['PATH_NEG'], [('lead', 'L_BATT_NEG'), ('joint', 'WAGO_STAR'), ('lead', 'L_PACK_NEG')])
        self.assertEqual(seg['PATH_PACK_POS'], [('lead', 'L_PACK_POS'), ('joint', 'WAGO_CELL_POS')])
        self.assertEqual(seg['PATH_PACK_NEG'], [('lead', 'L_PACK_NEG'), ('joint', 'WAGO_STAR')])
        self.assertEqual(seg['PATH_CELL_OUT'], [('joint', 'WAGO_CELL_POS'), ('lead', 'L_CELL_INA'), ('part', 'INA'),
                                                ('lead', 'L_INA_BATT'), ('joint', 'WAGO_BATT'), ('lead', 'L_BATT_POS'),
                                                ('part', 'CHGR'), ('lead', 'L_SYSOUT_POS'), ('joint', 'WAGO_SYS_OUT')])

    def test_a_segment_the_model_cannot_trace_is_left_out(self):
        self.data['lead'] = [k for k in self.data['lead'] if k['id'] != 'L_SYSOUT_POS']
        del self.lead('L_PACK_POS')['segment']
        seg = checks.power_path_segments(self.load())
        self.assertEqual(sorted(seg), ['PATH_NEG', 'PATH_PACK_NEG', 'PATH_POS'])


class MeterAtJack(Fixture):
    """Record M7's placement rule: the rain line's pull-up and filter in the jack pin's own strip."""

    def setUp(self):
        super().setUp()
        self.data['part'] += [
            _part('BOBR', board='A', origin=['a', 20], step=1, pins=['1', '2', '3', '4']),
            _part('R2', board='A', origin=['c', 23], step=3, pins=['1', '2']),
            _part('C_RAIN', board='A', origin=['e', 23], step=-1, pins=['1', '2'])]
        self.data['net'].append({'name': 'RAIN', 'class': 'rain', 'members': ['BOBR.4', 'R2.1', 'C_RAIN.1']})
        item(self.data, 'net', '3V3')['members'].append('R2.2')
        item(self.data, 'net', 'GND')['members'] += ['BOBR.3', 'C_RAIN.2']

    def test_the_fixture_passes(self):
        w = self.load()
        self.assertEqual(checks.check_meter_at_jack(w), [])
        self.assertEqual(checks.run_all(w, wiring.plan_jumpers(w), write_firmware(self.tmp.name)), [])

    def test_a_pull_up_across_the_channel_fails(self):
        item(self.data, 'part', 'R2')['origin'] = ['g', 23]     # a planner jumper now joins the jack pin to it
        self.assertOne(self.only('check_meter_at_jack'), 'RAIN', 'R2.1', "BOBR.4's strip", 'M7')

    def test_a_line_without_its_jack_pin_fails(self):
        net = item(self.data, 'net', 'RAIN')
        net['members'] = [m for m in net['members'] if m != 'BOBR.4']
        item(self.data, 'net', 'GND')['members'].append('BOBR.4')
        problems = checks.check_meter_at_jack(self.load())
        self.assertOne(problems, 'RAIN', 'BOBR.4', 'not on the net')


class RunAll(Fixture):
    def test_the_fixture_passes_every_check(self):
        w = self.load()
        root = write_firmware(self.tmp.name)
        self.assertEqual(checks.run_all(w, wiring.plan_jumpers(w), root), [])

    def test_the_committed_model(self):
        """Record 6.2: the committed model passes every check. Until the change-A model (6.1, the four
        lever connectors) lands, the test is skipped and says how many problems run_all finds."""
        w = wiring.load(HW/'source'/'wiring.toml')
        if not set(CHANGE_A_JOINTS) <= set(w.joints):
            try:
                count = len(checks.run_all(w, wiring.plan_jumpers(w), ROOT))
            except wiring.PlanError as e:
                count = f'unplannable ({e})'
            self.skipTest(f'the model is not change A yet (record 6.1); run_all problems: {count}')
        self.assertEqual(checks.run_all(w, wiring.plan_jumpers(w), ROOT), [])


if __name__ == '__main__':
    unittest.main()
