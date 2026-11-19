"""The preflight tool (tools/preflight.py, decision record D6) and the shared checklist (checklist.py).

Every fixture is written to a temporary directory: no git history, no KiCad, no evidence/ runs."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
try:
    from toolchain import load_tool
except ImportError:
    from tests.toolchain import load_tool

preflight = load_tool('preflight')
checklist = preflight.checklist

MODEL = '''version = 1
revision = "bench-bb-r0.1"

[[joint]]
id = "WAGO_CELL_POS"

[[joint]]
id = "WAGO_STAR"

[[lead]]
id = "L_PACK_POS"
from = "PACK.+"
to = "WAGO_CELL_POS"

[[link]]
id = "LK_REG_SHUNT"
a = "REG.VOUT"
b = "SHUNT.1"
'''
SHEET = '# Build sheet\n\nfixture\n'

MODE_A = [
    'check = "C1"\nvalue = "open"',
    'check = "C2"\nlever = "open"\nvalue = 1010000.0',   # R9, R_ISER and R_IPD (record 4.3 C2)
    'check = "C2"\nvalue = 0.2',
    'check = "C3"\nvalue = "pass"',
    'check = "C4"\nvalue = "pass"',
    'check = "C5"\nma = 38.6\nvalue = 38.1',
    'check = "C6"\nlead = "L_PACK_POS"\nmv = 4.1',
    'check = "C7"\njoint = "WAGO_STAR"\nmv = 0.4',
    'check = "C8"\nmv = 0.3',
    'check = "C9"\nma = -0.2',
    'check = "C10"\nmv = -3.0',
    'check = "C11"\nmv = 0.31',
    'check = "C19"\nvalue = "pass"',
]
ONE_A = [
    'check = "C12"\nspan = "PATH_POS"\nmv = 54.0\nma = 900.0',             # 60 mOhm
    'check = "C13"\nspan = "PATH_NEG"\nmv = 27.0\nma = 900.0',             # 30 mOhm
    'check = "C14"\nspan = "PATH_PACK_POS"\nmv = 18.0\nma = 900.0',        # 20 mOhm
    'check = "C14"\nspan = "PATH_PACK_NEG"\nmv = 9.0\nma = 900.0',         # 10 mOhm
    'check = "C14"\njoint = "WAGO_CELL_POS"\nmv = 2.7\nma = 900.0',        # 3 mOhm, a clamp
    'check = "C14"\nlead = "L_PACK_POS"\ncontact = "ph"\nmv = 13.5\nma = 900.0',  # 15 mOhm, a PH mating
    'check = "C16"\nma = 900.0\nvalue = 880.0',
    'check = "C17"\nsignal = "VBUS"\nmv = 4950.0\nma = 900.0',
    'check = "C17"\nsignal = "CHG"\nmv = 3300.0',
    'check = "C17"\nsignal = "PGOOD"\nmv = 3310.0',
    'check = "C18"\nmv = 0.6\nma = 900.0',
]
MODE_B = [
    'check = "C15"\nmv = 0.2',
    'check = "C20"\nmv = 1.1',
    'check = "C21"\nlink = "LK_REG_SHUNT"\nmv = 6.0',
    'check = "C22"\nmv = 3.9',
    'check = "C23"\nmv = 0.8\nvalue = "no reset"',
]


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.model = self.dir/'wiring.toml'
        self.sheet = self.dir/'build-sheet.md'
        self.notes = self.dir/'notes.md'
        self.model.write_text(MODEL)
        self.sheet.write_text(SHEET)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, readings=MODE_A, **top):
        """Run notes whose block states the current hashes unless top overrides a key."""
        keys = dict(model_hash=checklist.blob_sha1(self.model), sheet_hash=checklist.blob_sha1(self.sheet),
                    revision='bench-bb-r0.1', power_mode='A', meter=checklist.METER, date='2026-10-30',
                    photo='preflight.jpg', wiggle='pass', rewire=False, step_exit=False, deviations=[],
                    dv0_mv=4.2)
        keys.update(top)
        lines = [f'{k} = {self.toml(v)}' for k, v in keys.items() if v is not None]
        tables = ''.join(f'\n[[reading]]\n{r}\n' for r in readings)
        self.notes.write_text('# Run notes\n\n```sh\n```toml preflight\n```\n\n```toml preflight\n'
                              + '\n'.join(lines) + '\n' + tables + '```\n\nThe run started at 10:00.\n')

    @staticmethod
    def toml(value):
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, list):
            return '[' + ', '.join(f'"{v}"' for v in value) + ']'
        return repr(value)

    def run_status(self):
        return preflight.status(self.notes, self.model, self.sheet)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = preflight.main([str(self.notes), '--model', str(self.model), '--sheet', str(self.sheet)])
        return code, out.getvalue()

    def assertFailing(self, needle):
        state, problems = self.run_status()
        self.assertEqual(state, 'failing', problems)
        self.assertTrue(any(needle in line for line in problems), problems)

    def test_a_valid_block(self):
        self.write()
        self.assertEqual(self.run_status(), ('valid', []))
        self.assertEqual(self.run_main(), (0, 'preflight: valid\n'))

    def test_a_frozen_revision_is_checked_against_its_own_files(self):
        # Record 6.1: change A's block names bench-bb-r0.1, whose model and sheet are frozen under revisions/.
        hw = preflight.HW
        model, sheet = hw/'source'/'revisions'/'bench-bb-r0.1.toml', hw/'revisions'/'bench-bb-r0.1'/'build-sheet.md'
        self.assertEqual(preflight.files_for('bench-bb-r0.1'), (model, sheet))
        for other in ('bench-bb-r0.3', 'bench-bb-r0.9', '../../wiring', None, 3):
            with self.subTest(revision=other):
                self.assertEqual(preflight.files_for(other), (preflight.MODEL, preflight.SHEET))
        self.write(model_hash=checklist.blob_sha1(model), sheet_hash=checklist.blob_sha1(sheet))
        _state, problems = preflight.status(self.notes)
        self.assertEqual([p for p in problems if p.startswith(('model_hash', 'sheet_hash', 'revision'))], [])
        _state, problems = preflight.status(self.notes, self.model, self.sheet)   # explicit files still win
        self.assertTrue(any(p.startswith('model_hash') for p in problems), problems)

    def test_a_valid_step_exit_and_mode_b_block(self):
        self.write(MODE_A + ONE_A, step_exit=True, r_pack_mohm=30.0)
        self.assertEqual(self.run_status(), ('valid', []))
        self.write(MODE_B, power_mode='B', dv0_mv=3.9)
        self.assertEqual(self.run_status(), ('valid', []))

    def test_a_missing_joint_id_fails(self):
        self.write(MODE_A + ['check = "C7"\njoint = "WAGO_NOPE"\nmv = 0.4'])
        self.assertFailing("joint 'WAGO_NOPE' is not in the model")
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertTrue(out.endswith('preflight: failing; run marked wiring unverified\n'))

    def test_a_list_where_a_name_belongs_fails_without_raising(self):
        for extra in ('check = ["C1"]', 'check = "C7"\njoint = ["x"]\nmv = 0.4',
                      'check = "C17"\nsignal = ["VBUS"]\nmv = 4500.0\nma = 900.0',
                      'check = "C14"\nspan = ["PATH_PACK_POS"]\nmv = 1.0\nma = 900.0',
                      'check = "C14"\nspan = "PATH_POS"\ncontact = ["ph"]\nmv = 1.0\nma = 900.0'):
            with self.subTest(extra=extra):
                self.write(MODE_A + [extra])
                self.assertFailing('must be a string, not list')
                code, out = self.run_main()
                self.assertEqual(code, 1)
                self.assertTrue(out.endswith('preflight: failing; run marked wiring unverified\n'))

    def test_c12_at_90_mohm_fails(self):
        self.write(MODE_A + ['check = "C12"\nspan = "PATH_POS"\nmv = 81.0\nma = 900.0'])
        self.assertFailing('90.00 mOhm outside the limit')

    def test_a_hash_mismatch_is_stale_not_failing(self):
        self.write(model_hash='0' * 40)
        state, problems = self.run_status()
        self.assertEqual(state, 'stale')
        self.assertTrue(any(line.startswith('model_hash:') for line in problems), problems)
        code, out = self.run_main()
        self.assertEqual(code, 3)
        self.assertTrue(out.endswith('preflight: stale; the model changed since the run\n'))

    def test_a_changed_sheet_is_stale(self):
        self.write()
        self.sheet.write_text(SHEET + 'regenerated\n')
        self.assertEqual(self.run_status()[0], 'stale')

    def test_a_stale_block_of_another_revision_leaves_ids_unchecked(self):
        self.write(MODE_A + ['check = "C7"\njoint = "WAGO_GONE"\nmv = 0.4'],
                   model_hash='0' * 40, revision='bench-bb-r0.0')
        state, problems = self.run_status()
        self.assertEqual(state, 'stale', problems)
        self.assertIn("reading 14 (C7): joint 'WAGO_GONE': unchecked (revision differs)", problems)

    def test_a_stale_block_still_meets_the_limits(self):
        self.write(MODE_A + ['check = "C8"\nmv = 2.0'], model_hash='0' * 40, revision='bench-bb-r0.0')
        self.assertFailing('outside the limit')

    def test_a_missing_block(self):
        self.notes.write_text('# Run notes\n\n```toml\nmodel_hash = "x"\n```\n')
        self.assertEqual(self.run_status()[0], 'missing')
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertTrue(out.endswith('preflight: missing; run marked wiring unverified\n'))

    def test_a_block_that_does_not_parse_is_missing(self):
        self.notes.write_text('```toml preflight\nmodel_hash = \n```\n')
        self.assertEqual(self.run_status()[0], 'missing')
        self.notes.write_text('```toml preflight\nmodel_hash = "x"\n')        # never closed
        self.assertEqual(self.run_status()[0], 'missing')

    def test_a_1a_reading_outside_0_8_to_1_0_a_fails(self):
        self.write(MODE_A + ['check = "C13"\nspan = "PATH_NEG"\nmv = 36.0\nma = 1200.0'])
        self.assertFailing('1 A row: ma 1200.0 outside 800-1000 mA')
        self.write(MODE_A + ['check = "C18"\nmv = 0.5\nma = 600.0'])
        self.assertFailing('1 A row')

    def test_a_mode_b_block_missing_c21_fails(self):
        self.write([r for r in MODE_B if 'C21' not in r], power_mode='B', dv0_mv=3.9)
        self.assertFailing('C21: required for this run and missing')

    def test_step_exit_without_c12_fails(self):
        self.write(MODE_A + [r for r in ONE_A if 'C12' not in r], step_exit=True, r_pack_mohm=30.0)
        self.assertFailing('C12: required for this run and missing')
        self.write(MODE_A + ONE_A, rewire=True, r_pack_mohm=30.0)
        self.assertEqual(self.run_status(), ('valid', []))

    def test_r_pack_must_be_the_sum_of_the_pack_spans(self):
        self.write(MODE_A + ONE_A, step_exit=True, r_pack_mohm=35.0)
        self.assertFailing('is not the sum of the pack-side spans (30.00 mOhm)')
        self.write(MODE_A + ONE_A, step_exit=True)
        self.assertFailing('r_pack_mohm not recorded')

    def test_wiggle_fail_and_c14_contacts(self):
        self.write(wiggle='fail')
        self.assertFailing('wiggle is \'fail\'')
        self.write(MODE_A + ['check = "C14"\nlead = "L_PACK_POS"\nmv = 13.5\nma = 900.0'])
        self.assertFailing('needs contact')
        self.write(MODE_A + ['check = "C14"\njoint = "WAGO_STAR"\nmv = 5.4\nma = 900.0'])   # 6 > 5 mOhm clamp
        self.assertFailing('6.00 mOhm outside the limit')

    def test_text_rows_and_tolerances(self):
        self.write(MODE_A + ['check = "C5"\nma = 42.0\nvalue = 38.0'])                    # 4 > 2.76 mA
        self.assertFailing('more than 2 % + 2 mA apart')
        self.write(MODE_A + ['check = "C1"\nvalue = "0.4 ohm"'])
        self.assertFailing("value must be 'open'")
        self.write(MODE_A + ['check = "C17"\nsignal = "VBUS"\nmv = 4500.0\nma = 900.0'])
        self.assertFailing('VBUS 4500 mV outside the limit')
        self.write(MODE_A + ['check = "C99"\nmv = 1.0'])
        self.assertFailing('unknown check')

    def test_c2_lever_open_is_a_floor(self):
        others = [r for r in MODE_A if not r.startswith('check = "C2"\nlever')]
        for reading in ('lever = "open"\nvalue = 11500.0', 'lever = "open"\nunit = "ohm"\nvalue = 100.0'):
            with self.subTest(reading):
                self.write(others + [f'check = "C2"\n{reading}'])
                self.assertEqual(self.run_status(), ('valid', []))
        self.write(others + ['check = "C2"\nlever = "open"\nvalue = 0.3'])
        self.assertFailing('under 100 ohm')
        self.write(others + ['check = "C2"\nlever = "open"\nvalue = "open"'])
        self.assertFailing('needs a numeric value')
        self.write(others + ['check = "C2"\nunit = "open"\nvalue = "open"'])
        self.assertFailing('reads OL with the lever open')
        self.write(MODE_A + ['check = "C8"\nlever = "open"\nmv = 0.3'])
        self.assertFailing('on C2 only')

    def test_values(self):
        self.write(MODE_A + ONE_A, step_exit=True, r_pack_mohm=30.0)
        self.assertEqual(preflight.values(self.notes), {'dv0_mv': {'A': 4.2}, 'r_pack_mohm': 30.0})
        self.write(MODE_A + ONE_A, step_exit=True)
        self.assertAlmostEqual(preflight.values(self.notes)['r_pack_mohm'], 30.0)
        self.notes.write_text('no block\n')
        self.assertEqual(preflight.values(self.notes), {'dv0_mv': {}, 'r_pack_mohm': None})

    def test_model_ids_come_from_joints_leads_and_links(self):
        doc = preflight.tomllib.loads(MODEL)
        self.assertEqual(preflight.model_ids(doc), {'WAGO_CELL_POS', 'WAGO_STAR', 'L_PACK_POS', 'LK_REG_SHUNT'})


class ChecklistTests(unittest.TestCase):
    def test_blob_sha1_matches_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'hello.txt'
            path.write_bytes(b'hello\n')
            # sha1(b"blob 6\0hello\n"), which `git hash-object` prints for this file
            self.assertEqual(checklist.blob_sha1(path), 'ce013625030ba8dba906f756967f9e9ca394464a')
            path.write_bytes(b'')
            self.assertEqual(checklist.blob_sha1(path), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_rows_and_limits_follow_the_record(self):
        self.assertEqual([r['id'] for r in checklist.CHECKS], [f'C{n}' for n in range(1, 24)])
        self.assertEqual({r['id'] for r in checklist.CHECKS if r['mode'] == 'B'},
                         {'C15', 'C20', 'C21', 'C22', 'C23'})
        limits = {r['id']: r['limit_value'] for r in checklist.CHECKS}
        self.assertEqual((limits['C6'], limits['C7'], limits['C8'], limits['C9'], limits['C10'], limits['C11']),
                         (10.0, 1.0, 1.0, 1.0, 10.0, 1.0))
        self.assertEqual((limits['C12'], limits['C13'], limits['C15'], limits['C20'], limits['C21']),
                         (75.0, 40.0, 1.0, 3.0, 10.0))
        self.assertEqual(limits['C14'], {'ph': 20.0, 'clamp': 5.0, 'screw': 5.0, 'pack_span': 28.0})
        self.assertEqual((limits['C5'], limits['C16'], limits['C18'], limits['C23']),
                         ((2.0, 2.0), (10.0, 20.0), 2.0, 2.0))
        self.assertEqual(limits['C17'], {'VBUS': 4600.0, 'CHG': 3600.0, 'PGOOD': 3600.0})
        self.assertTrue(all(r['unit'] in checklist.UNITS for r in checklist.CHECKS))
        self.assertEqual(checklist.REQUIRED_MODE_A, ('C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9',
                                                     'C10', 'C11', 'C19'))
        self.assertEqual(checklist.REQUIRED_1A, ('C12', 'C13', 'C14', 'C16', 'C17', 'C18'))

    def test_budgets(self):
        self.assertEqual(checklist.BUDGETS, {'PATH_POS': 75.0, 'PATH_NEG': 40.0, 'PATH_PACK_POS': 28.0,
                                             'PATH_PACK_NEG': 28.0})
        self.assertEqual(checklist.PATH_CELL_OUT_FLAG_MV, 20.0)
        self.assertAlmostEqual(checklist.implied_mv(75.0, 1000.0), 75.0)
        self.assertAlmostEqual(checklist.implied_mv(75.0, 38.0), 2.85)
        self.assertIn('PATH_CELL_OUT covers CELL+ to OUT only', checklist.COVERAGE_NOTE)
        self.assertTrue(checklist.METER.startswith('Fluke 87V'))


if __name__ == '__main__':
    unittest.main()
