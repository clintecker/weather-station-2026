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
sys.path.insert(0, str(ROOT/'tools'))
import kicad_env  # noqa: E402

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


if __name__ == '__main__':
    unittest.main()
