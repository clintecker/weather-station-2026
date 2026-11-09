"""The board selection of the node build (firmware/stage0-node/Makefile, BOARD=; issue #35) and the two
board layers' pin headers (firmware/board/<board>/Core/Inc/board_pins.h).

make is run with a small extra makefile that prints the variables the selection sets, so nothing is
compiled: the NUCLEO stays the default with its build directory and its usage and budget lines, the
Wio-E5 mini builds the TX only, in its own directory, without the bench OLED, and an unknown board is
refused. The headers: both boards define the same names; every pin the mini's names is on its headers;
the mini's #error stops a bench OLED build; and its linker script keeps the NUCLEO's memory layout."""
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
# The Wio-E5 mini's header pins (Zephyr boards/seeed/lora_e5_mini pinout; README.md there).
WIO_HEADER = {'PA0', 'PA2', 'PA3', 'PA9', 'PA10', 'PA13', 'PA14', 'PA15', 'PB3', 'PB4', 'PB6', 'PB7', 'PB9', 'PB10',
              'PB13', 'PB14', 'PB15', 'PC0', 'PC1'}


def make(*args):
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp)/'show.mk'
        show.write_text(SHOW)
        return subprocess.run(['make', '-s', '-C', str(NODE), '-f', 'Makefile', '-f', str(show), *args, 'show'],
                              capture_output=True, text=True)


def defines(path):
    """The macro names a header defines (its include guard aside)."""
    names = re.findall(r'^#define (\w+)', path.read_text(), re.M)
    return {n for n in names if n != 'BOARD_PINS_H'}


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
                              (('ROLE=tx', 'BOARD=wio-e5', 'WS_BENCH_OLED=1'), 'drive the RF switch'),
                              (('ROLE=tx', 'BOARD=rak3172'), 'BOARD must be nucleo-wl55jc or wio-e5')):
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


class BoardPins(unittest.TestCase):
    NUCLEO = BOARDS/'nucleo-wl55jc/Core/Inc/board_pins.h'
    WIO = BOARDS/'wio-e5/Core/Inc/board_pins.h'

    def test_both_boards_define_the_same_names(self):
        self.assertEqual(defines(self.NUCLEO), defines(self.WIO))

    def test_every_wio_e5_pin_is_on_its_headers(self):
        text = self.WIO.read_text()
        pins = {f'P{port}{n}' for port, n in re.findall(r'_PORT GPIO([A-C])\n#define \w+_PIN GPIO_PIN_(\d+)', text)}
        self.assertEqual(pins, {'PA15', 'PB15', 'PC0', 'PB3'})        # SDA, SCL, cups, vane
        self.assertLessEqual(pins, WIO_HEADER)
        for name, n, comment in re.findall(r'^#define (\w+_PIN) GPIO_PIN_(\d+) /\* P[A-C](\d+)', text, re.M):
            with self.subTest(name=name):
                self.assertEqual(n, comment)                           # the comment names the same pin

    def test_the_wio_e5_header_stops_a_bench_oled_build(self):
        cc = shutil.which('cc')
        if cc is None:
            self.skipTest('needs cc')
        for oled, ok in ((0, True), (1, False)):
            with self.subTest(oled=oled):
                r = subprocess.run([cc, '-E', f'-DWS_BENCH_OLED={oled}', '-x', 'c', str(self.WIO)], capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr[-500:])

    def test_the_wio_e5_keeps_the_nucleo_memory_layout(self):
        def memory(path):
            text = path.read_text()
            return re.findall(r'^\s*(\w+)\s+\((\w+)\)\s*:\s*ORIGIN = (\w+), LENGTH = (\w+)', text, re.M), \
                re.findall(r'^_Min_\w+\s*=\s*\w+', text, re.M)
        self.assertEqual(memory(BOARDS/'nucleo-wl55jc/STM32WL55JCIX_FLASH.ld'), memory(BOARDS/'wio-e5/STM32WLE5JCIX_FLASH.ld'))


if __name__ == '__main__':
    unittest.main()
