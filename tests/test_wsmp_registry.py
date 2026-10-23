"""The WSMP registry (docs/module-protocol.md section 4): one TOML file, generated C and Python.

The expected values below are copied from the protocol document, not read from the generator.
"""
import importlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import CC_STRICT, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, needs_cc    # python -m unittest tests.<module>

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools' / 'wsmp_registry.py'
HEADER = ROOT / 'firmware' / 'common' / 'wsmp_registry.h'
LOCK = ROOT / 'tools' / 'wsmp_registry.lock'


def run_tool(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True, text=True)


class Registry(unittest.TestCase):
    def setUp(self):
        self.r = importlib.import_module('ws0.wsmp_registry')

    def test_tables_match_wsmp_section_4(self):
        r = self.r
        self.assertEqual(r.QUANTITIES[1]['unit'], 1)                  # air temperature, Cel
        self.assertEqual(r.QUANTITIES[6]['unit'], 5)                  # wind from direction, deg
        self.assertEqual(r.QUANTITIES[17]['ucum'], '{pulse}')
        self.assertEqual(r.UNITS[13]['ucum'], '{pulse}')
        self.assertEqual(r.KINDS[7]['name'], 'gust')
        self.assertEqual(sorted(r.MODULE_TYPES), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(r.MODULE_TYPES[5]['report_class'], 'health')
        self.assertEqual(r.MODULE_TYPES[1]['report_class'], 'minute')
        self.assertEqual([tuple(c) for c in r.MODULE_TYPES[1]['channels']], [(1, 2), (2, 2)])
        self.assertEqual([tuple(c) for c in r.MODULE_TYPES[5]['channels']],
                         [(9, 2), (11, 6), (12, 6), (13, 6), (14, 6), (15, 1), (16, 10)])
        self.assertEqual([tuple(c) for c in r.MODULE_TYPES[6]['channels']], [(17, 6), (5, 7), (6, 8), (6, 9)])
        self.assertEqual(r.MODULE_TYPES[6]['factors'], {'ums_per_hz': 666980, 'gust_ms': 3000})
        self.assertEqual(r.MODULE_TYPES[7]['factors'], {'nm_per_tip': 279400})   # 0.2794 mm per tip; the unit is in the name
        self.assertAlmostEqual(r.MODULE_TYPES[7]['factors']['nm_per_tip'] * 1e-6, 0.2794)
        self.assertEqual(r.REGISTRY_VERSION, 1)

    def test_calibration_table_of_record_major_1(self):
        # Spec 2026-10-21 section 6.9, frozen for major 1: bounds at the channel's scale, the physical
        # range (WSMP section 4.1) at that scale, and the crop margins.
        cal = self.r.CALIBRATION
        self.assertEqual(sorted(cal), [1, 2, 3, 8])
        self.assertEqual(cal[1], {'scale': -2, 'offset_bound': 200, 'gain_min': 980_000, 'gain_max': 1_020_000,
                                  'range_min': -8_000, 'range_max': 6_000, 'margin_below': 0, 'margin_above': 0})
        self.assertEqual(cal[2], {'scale': -2, 'offset_bound': 1_000, 'gain_min': 900_000, 'gain_max': 1_100_000,
                                  'range_min': 0, 'range_max': 10_000, 'margin_below': 300, 'margin_above': 300})
        self.assertEqual(cal[3], {'scale': -1, 'offset_bound': 50, 'gain_min': 990_000, 'gain_max': 1_010_000,
                                  'range_min': 3_000, 'range_max': 11_000, 'margin_below': 0, 'margin_above': 0})
        self.assertEqual(cal[8], {'scale': 0, 'offset_bound': 16, 'gain_min': 100_000, 'gain_max': 10_000_000,
                                  'range_min': 0, 'range_max': 1_048_576, 'margin_below': 16, 'margin_above': 0})

    def test_every_channel_names_a_known_quantity_and_kind(self):
        r = self.r
        for t in r.MODULE_TYPES.values():
            for quantity, kind in t['channels']:
                self.assertIn(quantity, r.QUANTITIES)
                self.assertIn(kind, r.KINDS)

    def test_every_quantity_has_a_known_canonical_unit(self):
        for code, q in self.r.QUANTITIES.items():
            self.assertIn(q['unit'], self.r.UNITS, f'quantity {code}')

    def test_codes_are_append_only(self):
        lock = {}
        for line in LOCK.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                table, code, name = line.split(None, 2)
                if table in ('quantity', 'unit', 'kind', 'module_type'):   # the names; the rest pins meaning
                    lock[(table, int(code))] = name
        tables = {'quantity': self.r.QUANTITIES, 'unit': self.r.UNITS, 'kind': self.r.KINDS,
                  'module_type': self.r.MODULE_TYPES}
        for (table, code), name in lock.items():
            self.assertIn(code, tables[table], f'{table} {code} was removed')
            self.assertEqual(tables[table][code]['name'], name, f'{table} {code} changed its name')

    def test_generated_files_are_current(self):
        p = run_tool('--check')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_check_detects_a_stale_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'repo'
            for rel in ('firmware/common/wsmp_registry.toml', 'firmware/common/wsmp_registry.h',
                        'ws0/wsmp_registry.py', 'tools/wsmp_registry.py', 'tools/wsmp_registry.lock'):
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, copy / rel)
            h = copy / 'firmware/common/wsmp_registry.h'
            h.write_text(h.read_text().replace('WSMP_Q_AIR_TEMPERATURE 1', 'WSMP_Q_AIR_TEMPERATURE 9'))
            p = subprocess.run([sys.executable, str(copy / 'tools/wsmp_registry.py'), '--check'],
                               cwd=copy, capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_lock_refuses_a_renamed_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'repo'
            for rel in ('firmware/common/wsmp_registry.toml', 'tools/wsmp_registry.py', 'tools/wsmp_registry.lock'):
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, copy / rel)
            t = copy / 'firmware/common/wsmp_registry.toml'
            t.write_text(t.read_text().replace('name = "air temperature"', 'name = "air temp"', 1))
            p = subprocess.run([sys.executable, str(copy / 'tools/wsmp_registry.py'), '--check'],
                               cwd=copy, capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertIn('append-only', p.stderr)

    def edited(self, *edits, args=('--check',)):
        """Runs the tool on a copy of the registry with each (old, new) text edit applied to the TOML."""
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'repo'
            for rel in ('firmware/common/wsmp_registry.toml', 'firmware/common/wsmp_registry.h',
                        'ws0/wsmp_registry.py', 'tools/wsmp_registry.py', 'tools/wsmp_registry.lock'):
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, copy / rel)
            t = copy / 'firmware/common/wsmp_registry.toml'
            text = t.read_text()
            for old, new in edits:
                self.assertIn(old, text)
                text = text.replace(old, new, 1)
            t.write_text(text)
            return subprocess.run([sys.executable, str(copy / 'tools/wsmp_registry.py'), *args],
                                  cwd=copy, capture_output=True, text=True)

    def test_lock_refuses_a_new_unit_for_a_quantity(self):
        # WSMP-G1: a change of unit is a change of meaning, which needs a new quantity code.
        p = self.edited(('name = "air temperature"\nid = "AIR_TEMPERATURE"\nunit = 1',
                         'name = "air temperature"\nid = "AIR_TEMPERATURE"\nunit = 2'))
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn('append-only', p.stderr)

    def test_lock_refuses_new_channels_without_a_new_schema(self):
        p = self.edited(('schema = 1\nreport_class = "minute"\nrole = "outside air"\nchannels = [[1, 2], [2, 2]]',
                         'schema = 1\nreport_class = "minute"\nrole = "outside air"\nchannels = [[1, 2], [2, 1]]'))
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn('append-only', p.stderr)

    def test_a_new_schema_may_change_the_channels(self):
        p = self.edited(('schema = 1\nreport_class = "minute"\nrole = "outside air"\nchannels = [[1, 2], [2, 2]]',
                         'schema = 2\nreport_class = "minute"\nrole = "outside air"\nchannels = [[1, 2], [2, 1]]'),
                        args=())
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_a_quantity_with_an_unknown_unit_is_refused_cleanly(self):
        p = self.edited(('id = "AIR_TEMPERATURE"\nunit = 1', 'id = "AIR_TEMPERATURE"\nunit = 99'))
        self.assertEqual(p.returncode, 1)
        self.assertIn('unknown unit', p.stderr)
        self.assertNotIn('Traceback', p.stderr)

    def test_a_calibration_row_with_an_unknown_quantity_is_refused_cleanly(self):
        # A valid row comes first, so the bounds checks must not run before every row's quantity is checked.
        p = self.edited(('quantity = 2        # relative humidity', 'quantity = 999      # relative humidity'))
        self.assertEqual(p.returncode, 1)
        self.assertIn('a known quantity', p.stderr)
        self.assertNotIn('Traceback', p.stderr)

    def test_a_negative_margin_on_an_earlier_row_is_refused(self):
        p = self.edited(('quantity = 2        # relative humidity', 'quantity = 2        # relative humidity'),
                        ('margin = [300, 300]', 'margin = [-1, 300]'))
        self.assertEqual(p.returncode, 1)
        self.assertIn('bounds out of order or negative', p.stderr)

    def test_kind_codes_without_a_gap(self):
        # wsmp.c checks a kind as 1..WSMP_KIND_MAX, so a gap would pass a code with no name.
        p = self.edited(('[[kind]]\ncode = 2\n', '[[kind]]\ncode = 20\n'))
        self.assertEqual(p.returncode, 1)
        self.assertIn('kind codes', p.stderr)

    def test_an_unknown_argument_is_refused(self):
        p = run_tool('--chek')
        self.assertEqual(p.returncode, 2)
        self.assertIn('usage', p.stderr)

    def test_the_header_holds_no_tables(self):
        # A static const table in a header is copied into every file that uses it: the tables are
        # initializer macros here, and wsmp.c holds the one copy.
        self.assertNotIn('static const', HEADER.read_text())

    @needs_cc
    def test_c_header_compiles_and_agrees(self):
        src = r'''
#include <stdio.h>
#include "wsmp.h"
int main(void) {
  const wsmp_type_entry *t = wsmp_type(WSMP_T_WIND);
  printf("%u %u %u %u %u\n", (unsigned)wsmp_canonical_unit(WSMP_Q_WIND_FROM_DIRECTION), (unsigned)t->channels,
         (unsigned)t->ch[0].quantity, (unsigned)t->ch[1].kind, (unsigned)t->report_class);
  printf("%lu %lu %u %d\n", (unsigned long)WSMP_WIND_UMS_PER_HZ, (unsigned long)WSMP_RAIN_NM_PER_TIP,
         (unsigned)wsmp_canonical_unit(99), wsmp_type(99) == 0);
  return 0;
}'''
        with tempfile.TemporaryDirectory() as tmp:
            c, exe = Path(tmp) / 'p.c', Path(tmp) / 'p'
            c.write_text(src)
            subprocess.run([*CC_STRICT, '-I', str(HEADER.parent), str(c), str(HEADER.parent / 'wsmp.c'), '-o', str(exe)],
                           check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split('\n')
        self.assertEqual(out[0], '5 4 17 7 0')        # deg; 4 channels; pulses; gust; minute class = 0
        self.assertEqual(out[1], '666980 279400 0 1')


if __name__ == '__main__':
    unittest.main()
