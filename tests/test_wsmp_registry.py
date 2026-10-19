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

    def test_every_channel_unit_is_canonical(self):
        r = self.r
        for t in r.MODULE_TYPES.values():
            for quantity, kind in t['channels']:
                self.assertIn(quantity, r.QUANTITIES)
                self.assertIn(kind, r.KINDS)

    def test_codes_are_append_only(self):
        lock = {}
        for line in LOCK.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                table, code, name = line.split(None, 2)
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

    @needs_cc
    def test_c_header_compiles_and_agrees(self):
        src = r'''
#include <stdio.h>
#include "wsmp_registry.h"
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
            subprocess.run([*CC_STRICT, '-I', str(HEADER.parent), str(c), '-o', str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split('\n')
        self.assertEqual(out[0], '5 4 17 7 0')        # deg; 4 channels; pulses; gust; minute class = 0
        self.assertEqual(out[1], '666980 279400 0 1')


if __name__ == '__main__':
    unittest.main()
