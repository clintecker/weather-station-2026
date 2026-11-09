"""The board selection of the node build (firmware/stage0-node/Makefile, BOARD=; issues #35 and #36).

make is run with a small extra makefile that prints the variables the selection sets, so nothing is
compiled: the NUCLEO stays the default with its build directory and its usage and budget lines, the
Wio-E5 mini builds the TX only, in its own directory, without the bench OLED, and an unknown board is
refused. What the build takes from a board (its roles, the bench OLED, the MCU, the unlock rule) comes
from its generated gen/board.mk (tools/boardgen.py; tests/test_boardgen.py has the pin headers). The
Wio-E5 mini's linker script keeps the NUCLEO's memory layout."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT    # python -m unittest tests.<module>

NODE = ROOT/'firmware/stage0-node'
BOARDS = ROOT/'firmware/board'
SHOW = 'show:\n\t@echo "$(BOARD_DIR)|$(BUILD)|$(strip $(USAGE_ARGS))|$(BUDGET_LABEL)|$(MCU_DEF)|$(notdir $(LDSCRIPT))|$(CLEAN_DIR)"\n'


def make(*args):
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp)/'show.mk'
        show.write_text(SHOW)
        return subprocess.run(['make', '-s', '-C', str(NODE), '-f', 'Makefile', '-f', str(show), *args, 'show'],
                              capture_output=True, text=True)


@unittest.skipUnless(shutil.which('make'), 'needs make')
class BoardSelection(unittest.TestCase):
    def show(self, *args):
        r = make(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().split('|')

    def test_the_nucleo_is_the_default_and_unchanged(self):
        for args in ((), ('BOARD=nucleo-wl55jc',)):
            with self.subTest(args=args):
                self.assertEqual(self.show('ROLE=tx', *args),
                                 ['../board/nucleo-wl55jc', 'build/tx', 'ROLE=tx', 'tx', 'STM32WL55xx',
                                  'STM32WL55JCIX_FLASH.ld', 'build'])
        self.assertEqual(self.show('ROLE=rx')[:3], ['../board/nucleo-wl55jc', 'build/rx', 'ROLE=rx'])

    def test_the_wio_e5_tx_builds_in_its_own_directory_and_names_itself(self):
        self.assertEqual(self.show('ROLE=tx', 'BOARD=wio-e5'),
                         ['../board/wio-e5', 'build/tx-wio-e5', 'ROLE=tx BOARD=wio-e5', 'tx, wio-e5', 'STM32WLE5xx',
                          'STM32WLE5JCIX_FLASH.ld', 'build'])

    def test_refused_combinations(self):
        for args, message in ((('ROLE=rx', 'BOARD=wio-e5'), 'BOARD=wio-e5 is for ROLE=tx'),
                              (('ROLE=tx', 'BOARD=wio-e5', 'WS_BENCH_OLED=1'), "drive the module's RF switch"),
                              (('ROLE=tx', 'BOARD=rak3172'), 'BOARD must be one of: nucleo-wl55jc wio-e5')):
            with self.subTest(args=args):
                r = make(*args)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)

    def test_the_wio_e5_has_unlock_and_the_nucleo_does_not(self):
        for board, ok in (('wio-e5', True), ('nucleo-wl55jc', False)):
            with self.subTest(board=board):
                r = subprocess.run(['make', '-s', '-n', '-C', str(NODE), 'ROLE=tx', f'BOARD={board}', 'unlock', 'SERIAL=X'],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr)
                if ok:
                    self.assertIn('stm32l4x unlock 0', r.stdout)
                    self.assertIn('adapter serial X', r.stdout)


class LinkerLayout(unittest.TestCase):
    def test_the_wio_e5_keeps_the_nucleo_memory_layout(self):
        def memory(path):
            text = path.read_text()
            return re.findall(r'^\s*(\w+)\s+\((\w+)\)\s*:\s*ORIGIN = (\w+), LENGTH = (\w+)', text, re.M), \
                re.findall(r'^_Min_\w+\s*=\s*\w+', text, re.M)
        self.assertEqual(memory(BOARDS/'nucleo-wl55jc/STM32WL55JCIX_FLASH.ld'), memory(BOARDS/'wio-e5/STM32WLE5JCIX_FLASH.ld'))


if __name__ == '__main__':
    unittest.main()
