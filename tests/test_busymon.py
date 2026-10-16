"""App/busymon.c's accounting on the host (firmware/test_busymon.c): own task time without the
interrupts that ran meanwhile, nested interrupts counted once, the slowest step names the task."""
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
    from toolchain import CC_STRICT, ROOT, SAN, needs_cc
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, SAN, needs_cc


@needs_cc
class Busymon(unittest.TestCase):
    def test_own_time_steps_and_nested_interrupts(self):
        fw = ROOT/'firmware'
        with tempfile.TemporaryDirectory() as tmp:
            exe = str(Path(tmp)/'busymon-test')
            subprocess.run([*CC_STRICT, *SAN, '-I', fw/'host/include', '-I', fw/'stage0-node/App', '-I', fw/'common',
                            fw/'stage0-node/App/busymon.c', fw/'common/ws_check.c', fw/'test_busymon.c', '-o', exe],
                           check=True)
            subprocess.run([exe], check=True)


if __name__ == '__main__':
    unittest.main()
