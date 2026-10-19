"""The bench breadboard wiring map (hardware/bench-breadboard-r0, docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md).

The model tests use only the repository Python. The KiCad tests need KiCad 10 and the pinned
KiCadRoutingTools (tools/fetch-router.sh); without them they skip and say why."""
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


if __name__ == '__main__':
    unittest.main()
