"""Short fuzz runs of the node's input parsers under AddressSanitizer and UBSan (firmware/fuzz/).

Each target runs its seed corpus plus WS_FUZZ_RUNS mutated inputs (default 20000) from a fixed
seed, so a failure reproduces exactly. Longer coverage-guided runs: firmware/fuzz/README.md.
"""
import os
import shutil
import subprocess
import unittest

try:
    from toolchain import ROOT, needs_cc, needs_vendor          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, needs_cc, needs_vendor    # python -m unittest tests.<module>

FUZZ = ROOT/'firmware/fuzz'
RUNS = os.environ.get('WS_FUZZ_RUNS', '20000')


@needs_cc
@unittest.skipUnless(shutil.which('make'), 'needs make')
@needs_vendor
class Fuzz(unittest.TestCase):
    def run_target(self, target):
        build = subprocess.run(['make', '-C', str(FUZZ), f'build/standalone-{target}'], capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        corpus = sorted(str(p) for p in (FUZZ/'corpus'/target).iterdir())
        run = subprocess.run([str(FUZZ/'build'/f'standalone-{target}'), *corpus, f'-runs={RUNS}', '-seed=1'],
                             capture_output=True, text=True, timeout=600)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr[-4000:])
        self.assertIn(f'fuzz ok: {len(corpus)} corpus files', run.stdout)
        # A corpus file over the driver's input limit, or more files than it keeps as seeds,
        # would be fuzzed only in part: standalone.c warns, and the corpus must not trigger it.
        self.assertNotIn('warning:', run.stderr)

    def test_reply(self):
        self.run_target('reply')

    def test_provision(self):
        self.run_target('provision')

    def test_console(self):
        self.run_target('console')

    def test_obs(self):
        self.run_target('obs')

    def test_wsmp(self):
        self.run_target('wsmp')

    def test_record(self):
        self.run_target('record')

    def test_set(self):
        self.run_target('set')


if __name__ == '__main__':
    unittest.main()
