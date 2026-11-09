#!/usr/bin/env python3
"""The board boundary (issue #36): the node's application code names no pin and no peripheral instance.

    python3 tools/board_lint.py [PATH ...]    default: firmware/stage0-node/App firmware/common

Every hardware fact the station's code needs comes from the board layer: the board's board.toml,
generated into gen/board_pins.h and gen/board_caps.h (tools/boardgen.py). So a new board is one board
directory and no change here. This reads every .c and .h file under the paths, drops comments, string
and character literals, and fails on any identifier that names:

  GPIOx        a GPIO port (GPIOA, __HAL_RCC_GPIOB_CLK_ENABLE)
  GPIO_PIN_n   a pin number
  ADC_CHANNEL_n an ADC channel (ADC_CHANNEL_VREFINT and the other internal ones are the MCU's: allowed)
  LPTIMx       a low-power timer instance (LPTIM1, RCC_LPTIM1CLKSOURCE_LSE, Lptim1ClockSelection)
  I2Cx         an I2C instance (I2C2, GPIO_AF4_I2C2, I2c2ClockSelection)
  USARTx, LPUARTx  a UART instance
  EXTIx        an EXTI line or its vector (EXTI4_IRQn, EXTI15_10_IRQHandler, LL_EXTI_LINE_4)

Use the board's name instead (BOARD_RAIN_PORT, BOARD_I2C, BOARD_RAIN_IRQn; docs/adding-a-board.md).
The tangled i2c_bus.c is checked, not its .lit.md: its prose may name the NUCLEO's pins. Exit status 1
on any finding.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ('firmware/stage0-node/App', 'firmware/common')
RULES = (
    ('a GPIO port', re.compile(r'(^|_)GPIO[A-H](_|$)')),
    ('a pin number', re.compile(r'(^|_)GPIO_PIN_\d+$')),
    ('an ADC channel', re.compile(r'(^|_)ADC_CHANNEL_\d+$')),
    ('an LPTIM instance', re.compile(r'(^|_)LPTIM\d|(^|_)Lptim\d')),
    ('an I2C instance', re.compile(r'(^|_)I2C\d|(^|_)I2c\d')),
    ('a UART instance', re.compile(r'(^|_)(LP)?USART\d|(^|_)LPUART\d|(^|_)(Usart|Lpuart)\d')),
    ('an EXTI line', re.compile(r'(^|_)EXTI\d|EXTI_LINE_\d')),
)
# Comments, then string and character literals (with their escapes), each replaced by spaces of the
# same shape so line numbers stay.
LITERALS = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
IDENT = re.compile(r'[A-Za-z_]\w*')


def blank(m):
    return re.sub(r'[^\n]', ' ', m.group(0))


def findings(path):
    """(line, identifier, what) for each identifier in the file that names hardware."""
    code = LITERALS.sub(blank, path.read_text())
    out = []
    for n, line in enumerate(code.splitlines(), 1):
        for ident in IDENT.findall(line):
            for what, rule in RULES:
                if rule.search(ident):
                    out.append((n, ident, what))
                    break
    return out


def sources(paths):
    for p in paths:
        p = Path(p) if Path(p).is_absolute() else ROOT / p
        yield from sorted(f for f in ([p] if p.is_file() else p.rglob('*')) if f.suffix in ('.c', '.h'))


def main(argv):
    paths = argv or DEFAULT
    files = list(sources(paths))
    bad = 0
    for f in files:
        for n, ident, what in findings(f):
            rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else f
            print(f'{rel}:{n}: {ident} names {what}: take it from the board layer (gen/board_pins.h)')
            bad += 1
    if bad:
        print(f'board boundary: FAIL ({bad} finding(s); tools/board_lint.py, docs/adding-a-board.md)')
        return 1
    print(f'board boundary: OK ({len(files)} files in {", ".join(map(str, paths))} name no pin or peripheral instance)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
