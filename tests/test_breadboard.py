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


if __name__ == '__main__':
    unittest.main()
