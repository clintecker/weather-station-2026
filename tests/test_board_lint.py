"""The board boundary lint (tools/board_lint.py; issue #36): the node's App/ and firmware/common name no pin
and no peripheral instance. The real tree passes; a planted violation in a copy of App/board_inputs.c
fails; every rule fires on its own example; comments and strings do not count."""
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
import board_lint  # noqa: E402

LINT = ROOT/'tools/board_lint.py'


def lint(*paths):
    return subprocess.run([sys.executable, LINT, *map(str, paths)], capture_output=True, text=True)


class BoardLint(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, name, text):
        path = self.tmp/name
        path.write_text(text)
        return path

    def test_the_node_and_common_pass(self):
        r = lint()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('board boundary: OK', r.stdout)

    def test_a_planted_violation_fails(self):
        app = self.tmp/'App'
        shutil.copytree(ROOT/'firmware/stage0-node/App', app)
        path = app/'board_inputs.c'
        text = path.read_text()
        self.assertEqual(text.count('HAL_GPIO_Init(RAIN_PORT, &rain);'), 1)
        path.write_text(text.replace('HAL_GPIO_Init(RAIN_PORT, &rain);', 'HAL_GPIO_Init(GPIOB, &rain);'))
        self.assertEqual(lint(ROOT/'firmware/stage0-node/App').returncode, 0)
        r = lint(app)
        self.assertEqual(r.returncode, 1)
        line = text[:text.index('HAL_GPIO_Init(RAIN_PORT, &rain);')].count('\n') + 1
        self.assertIn(f'board_inputs.c:{line}: GPIOB names a GPIO port', r.stdout)
        self.assertIn('board boundary: FAIL (1 finding(s)', r.stdout)

    def test_every_rule_fires(self):
        cases = {'GPIOA': 'a GPIO port', '__HAL_RCC_GPIOC_CLK_ENABLE': 'a GPIO port', 'GPIO_PIN_4': 'a pin number',
                 'ADC_CHANNEL_6': 'an ADC channel', 'LPTIM1': 'an LPTIM instance', 'RCC_LPTIM1CLKSOURCE_LSE': 'an LPTIM instance',
                 'Lptim1ClockSelection': 'an LPTIM instance', 'I2C2': 'an I2C instance', 'GPIO_AF4_I2C2': 'an I2C instance',
                 'I2c2ClockSelection': 'an I2C instance', 'USART2_IRQHandler': 'a UART instance', 'LPUART1': 'a UART instance',
                 'EXTI4_IRQn': 'an EXTI line', 'EXTI15_10_IRQHandler': 'an EXTI line', 'LL_EXTI_LINE_4': 'an EXTI line'}
        for ident, what in cases.items():
            with self.subTest(ident=ident):
                found = board_lint.findings(self.write('x.c', f'int f(void) {{ return (int){ident}; }}\n'))
                self.assertEqual(found, [(1, ident, what)])

    def test_board_names_comments_and_strings_pass(self):
        text = ('/* PB4 on GPIOB, EXTI4, I2C2 */\n'
                '// GPIO_PIN_4 ADC_CHANNEL_6\n'
                'static const char *n = "I2C2_EV USART2";\n'
                "static const char c = 'A';\n"
                'void f(void) { HAL_GPIO_Init(BOARD_RAIN_PORT, 0); (void)BOARD_I2C; (void)BOARD_RAIN_IRQn; '
                '(void)GPIO_PIN_SET; (void)ADC_CHANNEL_VREFINT; (void)LPTIM_INPUT1SOURCE_GPIO; (void)hi2c2; '
                '(void)BOARD_EXTI_10TO15_IRQn; (void)__HAL_GPIO_EXTI_CLEAR_IT; }\n')
        self.assertEqual(board_lint.findings(self.write('ok.c', text)), [])

    def test_line_numbers_survive_a_multi_line_comment(self):
        found = board_lint.findings(self.write('m.c', '/* one\n   two\n   three */\nint x = GPIO_PIN_2;\n'))
        self.assertEqual(found, [(4, 'GPIO_PIN_2', 'a pin number')])


if __name__ == '__main__':
    unittest.main()
