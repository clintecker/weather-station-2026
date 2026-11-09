"""The board layer as data (issue #36): tools/boardgen.py, its pin-map validator and the generated files.

Each board is firmware/board/<name>/board.toml; tools/boardgen.py checks it against ST's pin data
(tools/pinctrl) and writes gen/. These tests: the committed gen/ is what the generator writes; the
validator refuses a planted invalid alternate function, ADC channel, pin, double use and EXTI clash; the
NUCLEO's RF switch table is what ST's BSP does; the generated headers stop a build the board cannot run;
and a made-up third board (tests/fixtures/boards/made-up-e5, never shipped) builds from its own directory
alone, with no file outside it changed."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT    # python -m unittest tests.<module>

sys.path.insert(0, str(ROOT/'tools'))
import boardgen  # noqa: E402

BOARDS = ROOT/'firmware/board'
NUCLEO, WIO = BOARDS/'nucleo-wl55jc', BOARDS/'wio-e5'
FIXTURE = ROOT/'tests/fixtures/boards/made-up-e5'
BSP_RADIO = ROOT/'vendor/STM32CubeWL/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo_radio.c'
ARM_GCC = Path.home()/'.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-gcc'
REQUIRE_ARM = os.environ.get('WS_REQUIRE_ARM') == '1'
# The Wio-E5 mini's header pins (Zephyr boards/seeed/lora_e5_mini pinout; README.md there).
WIO_HEADER = {'PA0', 'PA2', 'PA3', 'PA9', 'PA10', 'PA13', 'PA14', 'PA15', 'PB3', 'PB4', 'PB6', 'PB7', 'PB9', 'PB10',
              'PB13', 'PB14', 'PB15', 'PC0', 'PC1'}


def defines(path):
    names = re.findall(r'^#define (\w+)', path.read_text(), re.M)
    return {n for n in names if not n.endswith('_H')}


class Copy:
    """A board directory copied to a temporary place, with its board.toml edited."""

    def __init__(self, test, board=NUCLEO):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)/board.name
        shutil.copytree(board, self.dir)
        self.toml = self.dir/'board.toml'

    def edit(self, old, new):
        text = self.toml.read_text()
        assert text.count(old) == 1, old
        self.toml.write_text(text.replace(old, new))
        return self

    def problems(self):
        try:
            boardgen.Board(self.dir).check()
        except boardgen.BoardError as e:
            return str(e)
        return ''


class Generated(unittest.TestCase):
    def test_every_board_is_valid_and_its_gen_is_current(self):
        r = subprocess.run([sys.executable, ROOT/'tools/boardgen.py', '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('boards: OK (2 checked', r.stdout)

    def test_a_hand_edit_of_gen_is_stale(self):
        board = Copy(self)
        pins = board.dir/'gen/board_pins.h'
        pins.write_text(pins.read_text().replace('GPIO_PIN_4 /* PB4', 'GPIO_PIN_3 /* PB4'))
        r = subprocess.run([sys.executable, ROOT/'tools/boardgen.py', '--check', '--board', board.dir],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('stale: ', r.stderr)
        self.assertIn('board_pins.h', r.stderr)

    def test_both_boards_define_the_same_station_names(self):
        oled = {n for n in defines(NUCLEO/'gen/board_pins.h') if n.startswith(('BOARD_OLED_', 'BOARD_B1', 'BOARD_B2',
                                                                               'BOARD_B3', 'BOARD_BUTTONS'))}
        self.assertTrue(oled)
        self.assertEqual(defines(NUCLEO/'gen/board_pins.h') - oled, defines(WIO/'gen/board_pins.h'))
        self.assertFalse(any(n.startswith('BOARD_RF_SW_') for n in defines(NUCLEO/'gen/board_caps.h')))   # its BSP
        self.assertIn('BOARD_RF_SW_WRITE', defines(WIO/'gen/board_caps.h'))

    def test_every_fitted_wio_e5_pin_is_on_its_headers(self):
        rows = boardgen.pin_rows(boardgen.Board(WIO).check())
        station = {pin for fn, pin, at, sig, note in rows
                   if pin and not note.startswith('not fitted') and not fn.startswith(('RF switch', 'LED'))}
        self.assertLessEqual(station - {'PB6', 'PB7'}, WIO_HEADER)     # the console is the mini's USB-UART
        text = (WIO/'gen/board_pins.h').read_text()
        for name, n, comment in re.findall(r'^#define (\w+_PIN) GPIO_PIN_(\d+) /\* P[A-C](\d+)', text, re.M):
            with self.subTest(name=name):
                self.assertEqual(n, comment)                           # the comment names the same pin

    def test_the_nucleo_pins_are_the_ones_before_the_board_layer(self):
        # The values the hand-written NUCLEO header had (#35), and the node's own constants before that.
        text = (NUCLEO/'gen/board_pins.h').read_text()
        want = {'BOARD_I2C_SDA_PIN': '11', 'BOARD_I2C_SCL_PIN': '12', 'BOARD_CUPS_PIN': '5', 'BOARD_VANE_PIN': '2',
                'BOARD_ISET_PIN': '1', 'BOARD_VIN_PIN': '10', 'BOARD_RAIN_PIN': '4', 'BOARD_PGOOD_PIN': '8',
                'BOARD_CHG_PIN': '10', 'BOARD_MUX_RESET_PIN': '14', 'BOARD_SENSOR_POWER_PIN': '9'}
        got = dict(re.findall(r'^#define (BOARD_\w+_PIN) GPIO_PIN_(\d+)', text, re.M))
        self.assertEqual({k: got[k] for k in want}, want)
        for macro in ('BOARD_VANE_CHANNEL ADC_CHANNEL_4', 'BOARD_ISET_CHANNEL ADC_CHANNEL_5', 'BOARD_VIN_CHANNEL ADC_CHANNEL_6',
                      'BOARD_CUPS_AF GPIO_AF1_LPTIM1', 'BOARD_I2C_AF GPIO_AF4_I2C2', 'BOARD_RAIN_IRQn EXTI4_IRQn',
                      'BOARD_CONSOLE_UART huart2', 'BOARD_LED_PINS { GPIO_PIN_15, GPIO_PIN_9, GPIO_PIN_11 }'):
            self.assertIn(f'#define {macro}', text)


class Validator(unittest.TestCase):
    def assertRefused(self, board, *words):
        problems = board.problems()
        self.assertTrue(problems, 'accepted')
        for w in words:
            self.assertIn(w, problems)

    def test_both_boards_pass(self):
        for d in (NUCLEO, WIO):
            with self.subTest(board=d.name):
                self.assertEqual(Copy(self, d).problems(), '')

    def test_a_planted_invalid_alternate_function_is_refused(self):
        # PB2 has no LPTIM1_IN1 in ST's pin data (it has LPTIM1_OUT).
        self.assertRefused(Copy(self).edit('cups = { pin = "PB5"', 'cups = { pin = "PB2"')
                           .edit('vane = { pin = "PB2"', 'vane = { pin = "PB3"').edit('adc = 4,', 'adc = 2,'),
                           'cups: PB2 has no alternate function LPTIM1_IN1', 'LPTIM1_OUT')
        # PA10 has no I2C2_SDA; the console on the wrong UART's pins.
        self.assertRefused(Copy(self).edit('sda = { pin = "PA11"', 'sda = { pin = "PA8"'), 'I2C sda: PA8 has no alternate function I2C2_SDA')
        self.assertRefused(Copy(self).edit('uart = "USART2"', 'uart = "USART1"'), 'console tx: PA2 has no alternate function USART1_TX')
        # The OLED's SCK on a pin without SPI1_SCK.
        self.assertRefused(Copy(self).edit('sck = { pin = "PA5"', 'sck = { pin = "PA6"'), 'OLED sck: PA6 has no alternate function SPI1_SCK')

    def test_a_planted_invalid_adc_channel_is_refused(self):
        self.assertRefused(Copy(self).edit('vin = { pin = "PA10", adc = 6', 'vin = { pin = "PA10", adc = 7'),
                           'vin: PA10 is not ADC1_IN7', 'ADC_IN6')

    def test_a_pin_used_twice_or_missing_is_refused(self):
        self.assertRefused(Copy(self).edit('mux_reset = { pin = "PB14"', 'mux_reset = { pin = "PB15"'),
                           'PB15 is used twice: mux_reset and LED1 (blue)')
        self.assertRefused(Copy(self).edit('mux_reset = { pin = "PB14"', 'mux_reset = { pin = "PD3"'), 'PD3 is not a pin')
        self.assertRefused(Copy(self, WIO).edit('mux_reset = { pin = "PB14"', 'mux_reset = { pin = "PA4"'),
                           'PA4 is used twice', 'RF switch CTRL1')

    def test_the_exti_lines_are_checked(self):
        self.assertRefused(Copy(self).edit('rain = { pin = "PB4"', 'rain = { pin = "PB0"'),
                           'EXTI line 0 is used twice: rain and OLED B1')
        self.assertRefused(Copy(self).edit('rain = { pin = "PB4"', 'rain = { pin = "PB7"'),
                           'rain is on EXTI line 7: it needs a vector of its own')

    def test_what_the_node_code_assumes_is_checked(self):
        self.assertRefused(Copy(self).edit('iset = { pin = "PB1", adc = 5', 'iset = { pin = "PA11", adc = 7')
                           .edit('sda = { pin = "PA11"', 'sda = { pin = "PA15"'), "iset must be on the vane's port")
        self.assertRefused(Copy(self).edit('pgood = { pin = "PB8"', 'pgood = { pin = "PB8", fitted = false, why = "x"'),
                           'all fitted or none')
        self.assertRefused(Copy(self).edit('vane = { pin = "PB2", adc = 4', 'vane = { fitted = false, why = "x"'),
                           'vane must be fitted')

    def test_an_unknown_key_is_refused(self):
        self.assertRefused(Copy(self).edit('tcxo_startup_ms = 1', 'tcxo_start_ms = 1'),
                           "[radio] has an unknown key 'tcxo_start_ms'")
        self.assertRefused(Copy(self).edit('rain = { pin = "PB4", exti = true', 'rain = { pin = "PB4", extl = true'),
                           "[pins] rain has unknown keys ['extl']")

    def test_the_cubemx_code_must_agree(self):
        self.assertRefused(Copy(self).edit('pin = "PB15"\ncolour = "blue"', 'pin = "PB0"\ncolour = "blue"'),
                           'LED1 is PB0 here but not in Core/Inc/main.h')

    @unittest.skipUnless(BSP_RADIO.exists(), 'run tools/fetch-vendor.sh (ST BSP source)')
    def test_the_nucleo_switch_table_is_what_st_bsp_does(self):
        """board.toml [radio] for the "st-bsp" driver documents BSP_RADIO_ConfigRFSwitch: check it."""
        body = BSP_RADIO.read_text().split('int32_t BSP_RADIO_ConfigRFSwitch', 1)[1].split('\n}\n', 1)[0]
        ctrl = {'RF_SW_CTRL1': 'PC4', 'RF_SW_CTRL2': 'PC5', 'RF_SW_CTRL3': 'PC3'}
        header = BSP_RADIO.with_suffix('.h').read_text()
        for name, pin in ctrl.items():
            self.assertIn(f'#define {name}_PIN                          GPIO_PIN_{pin[2:]}', header)
            self.assertIn(f'#define {name}_GPIO_PORT                    GPIO{pin[1]}', header)
        radio = boardgen.Board(NUCLEO).check().toml['radio']
        self.assertEqual(radio['switch'], ['PC4', 'PC5', 'PC3'])
        for case, state in (('OFF', 'off'), ('RX', 'rx'), ('RFO_LP', 'tx_lp'), ('RFO_HP', 'tx_hp')):
            block = body.split(f'case RADIO_SWITCH_{case}:', 1)[1].split('break;', 1)[0]
            levels = dict(re.findall(r'HAL_GPIO_WritePin\((RF_SW_CTRL\d)_GPIO_PORT, \w+, GPIO_PIN_(SET|RESET)\)', block))
            with self.subTest(state=state):
                self.assertEqual([int(levels[c] == 'SET') for c in ctrl], radio[state])
        bsp = BSP_RADIO.read_text()
        self.assertIn('return RADIO_CONF_RFO_LP_HP;', bsp)                   # pa = "lp_hp"
        self.assertIn('return RADIO_CONF_TCXO_SUPPORTED;', bsp)              # tcxo = true
        self.assertIn('return RADIO_CONF_DCDC_SUPPORTED;', bsp)              # dcdc = true
        self.assertEqual((radio['pa'], radio['tcxo'], radio['dcdc'], radio['rfo_lp_max_dbm'], radio['rfo_hp_max_dbm']),
                         ('lp_hp', True, True, 15, 22))


@unittest.skipUnless(shutil.which('cc'), 'needs cc')
class Requirements(unittest.TestCase):
    """The capability #errors in gen/board_caps.h, which gen/board_pins.h includes."""

    def preprocess(self, board, *defs):
        return subprocess.run(['cc', '-E', *defs, '-x', 'c', str(board/'gen/board_pins.h')], capture_output=True, text=True)

    def test_the_wio_e5_header_stops_a_bench_oled_build_and_a_receiver(self):
        for defs, ok, why in ((('-DWS_BENCH_OLED=0', '-DWS_ROLE_tx'), True, ''),
                              (('-DWS_BENCH_OLED=1',), False, 'drive the module'),
                              (('-DWS_ROLE_rx',), False, 'ROLE=rx on the wio-e5 board')):
            with self.subTest(defs=defs):
                r = self.preprocess(WIO, *defs)
                self.assertEqual(r.returncode == 0, ok, r.stderr[-500:])
                self.assertIn(why, r.stderr)

    def test_the_nucleo_takes_every_build(self):
        for defs in (('-DWS_BENCH_OLED=1', '-DWS_ROLE_tx'), ('-DWS_ROLE_rx',)):
            with self.subTest(defs=defs):
                self.assertEqual(self.preprocess(NUCLEO, *defs).returncode, 0)


def git_status():
    """The working tree's changes where a build or the generator could write (git-ignored build/ aside)."""
    return subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all', '--', 'firmware', 'tools', 'tests',
                           'docs', 'hardware/bench-breadboard-r0', 'hardware/bench-breadboard-r1'], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout


@unittest.skipUnless((ARM_GCC.exists() and (ROOT/'vendor/STM32CubeWL').exists()) or REQUIRE_ARM,
                     'needs the xPack arm-none-eabi-gcc and vendor/ (tools/fetch-vendor.sh)')
class MadeUpBoard(unittest.TestCase):
    """docs/adding-a-board.md, followed for a board that does not exist: copy the nearest board's CubeMX
    code (Core/, startup/, the linker script, board.mk), write board.toml, run tools/boardgen.py, build. The
    node builds for it, and nothing outside the board's directory changed."""

    def test_a_third_board_builds_from_its_own_directory(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        board = Path(tmp.name)/'made-up-e5'
        board.mkdir()
        for part in ('Core', 'startup'):
            shutil.copytree(WIO/part, board/part)
        for part in ('STM32WLE5JCIX_FLASH.ld', 'board.mk'):
            shutil.copy(WIO/part, board/part)
        shutil.copy(FIXTURE/'board.toml', board/'board.toml')
        before = git_status()
        r = subprocess.run([sys.executable, ROOT/'tools/boardgen.py', '--board', board], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        caps = (board/'gen/board_caps.h').read_text()
        self.assertIn('#define BOARD_RF_SW_PARAMS GPIO_PinState ctrl1, GPIO_PinState ctrl2, GPIO_PinState ctrl3', caps)
        make = ['make', '-s', '-C', str(ROOT/'firmware/stage0-node'), f'-j{os.cpu_count() or 2}', 'ROLE=tx',
                'BOARD=made-up-e5', f'BOARD_DIR={board}', f'BUILD={tmp.name}/build']
        r = subprocess.run(make, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.assertRegex(r.stdout, r'flash budget \(tx, made-up-e5\): \d+ of 194560 B')
        self.assertTrue((Path(tmp.name)/'build/stage0-tx.bin').stat().st_size > 50000)
        r = subprocess.run(make[:5] + ['ROLE=rx', 'BOARD=made-up-e5', f'BOARD_DIR={board}', f'BUILD={tmp.name}/rx'],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('BOARD=made-up-e5 is for ROLE=tx', r.stderr)
        self.assertEqual(git_status(), before)


if __name__ == '__main__':
    unittest.main()
