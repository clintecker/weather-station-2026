#!/usr/bin/env python3
"""Check each board's pin map and generate its board layer (issue #36).

    tools/boardgen.py                 check and write gen/ for every firmware/board/*/board.toml
    tools/boardgen.py --check         exit 1 if a board is invalid or its gen/ is stale
    tools/boardgen.py --board DIR     only the board in DIR (any directory with a board.toml)

The source is firmware/board/<name>/board.toml (docs/adding-a-board.md has the format). From it this
writes, into firmware/board/<name>/gen/:
  board_pins.h  the station's pins by function, as the node's App/ code uses them (BOARD_*); the
                hardware checkers (hardware/bench-breadboard-r0/source/wiring.py) read its pin lines
  board_caps.h  the capabilities, the radio front end (RF switch truth table, TCXO, PA path) and the
                #error lines that stop a build the board cannot run (a role, the bench OLED)
  board.mk      the MCU, its startup file and linker script, the ST BSP if any, the roles, the bench OLED
                capability and the `unlock` rule, for firmware/board/stm32wl/rules.mk
  pins.md       the pin table for the docs
  pins.json     the same table as data (hardware/bench-breadboard-r1/schematic/checks.py)
The generated files are committed, so a plain `make` needs nothing but make and the compiler;
tools/code_shape.sh runs --check, so a stale gen/ fails CI.

The checks (any failure stops before anything is written):
  - every pin exists on the package, and none is used twice (fitted pins, LEDs, the console, the I2C
    bus, the RF switch, the bench OLED and the board's reserved pins);
  - every alternate function and ADC channel exists on its pin in ST's pin data
    (tools/pinctrl/<pinctrl>-pinctrl.dtsi, Zephyr hal_stm32; tools/pinctrl/README.md), and names the
    peripheral the function needs (the I2C instance, the console UART, LPTIMx_IN1 for the cups, SPIx for
    the OLED);
  - the EXTI lines: no two EXTI inputs on one line; the rain gauge and the OLED's B1 and B2 each own a
    vector (lines 0 to 4), CHG and B3 are on the shared ones (5 to 15), which App/board_inputs.c serves;
  - what the node's code assumes: ISET on the vane's port, B1 and B2 on one port, the charger pins all
    fitted or none, one active level for the LEDs;
  - the board's CubeMX code agrees: Core/Inc/main.h names the same LEDs, Core/Src/usart.c the console;
  - every section and key is one this knows (a typo is an error, not an ignored fact).
"""
import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARDS = ROOT / 'firmware' / 'board'
PINCTRL = ROOT / 'tools' / 'pinctrl'
GEN = 'gen'
BANNER = 'GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.'

ROLES = ('tx', 'rx')
FLASH = {'onboard-stlink': 'its own ST-LINK',
         'nucleo-stlink-swd': "a NUCLEO's ST-LINK as an external probe over SWD"}
UNLOCK = ('none', 'openocd-stm32l4x')
DRIVERS = ('st-bsp', 'gpio')
PA = {'lp_hp': 'RBI_CONF_RFO_LP_HP', 'lp': 'RBI_CONF_RFO_LP', 'hp': 'RBI_CONF_RFO_HP'}
TCXO_MV = {1600: '1_6V', 1700: '1_7V', 1800: '1_8V', 2200: '2_2V', 2400: '2_4V', 2700: '2_7V', 3000: '3_0V',
           3300: '3_3V'}                                   # radio_driver.h TCXO_CTRL_*
SWITCH_STATES = ('off', 'rx', 'tx_hp', 'tx_lp')
BSP_FILES = {'STM32WLxx_Nucleo': ('stm32wlxx_nucleo_radio.c', 'stm32wlxx_nucleo.c')}
# The station's functions (board.toml [pins]): each with what it needs.
STATION = {
    'cups': {'af': r'LPTIM[12]_IN1'},                      # App/board_inputs.c counts on input 1
    'vane': {'adc': True},
    'iset': {'adc': True, 'charger': True},
    'vin': {'adc': True},
    'rain': {'exti': True},
    'pgood': {'charger': True},
    'chg': {'exti': True, 'charger': True},
    'mux_reset': {},
    'sensor_power': {},
}
OLED_PINS = ('cs', 'sck', 'mosi', 'rst', 'dc')
BUTTONS = ('b1', 'b2', 'b3')
PIN_RE = re.compile(r'^P([A-H])(\d{1,2})$')
# The keys board.toml may use (a typo is an error, not a silently ignored fact).
KEYS = {
    'board': {'name', 'title', 'mcu', 'mcu_define', 'pinctrl', 'startup', 'ldscript', 'roles', 'flash', 'unlock'},
    'console': {'uart', 'tx', 'rx', 'to'},
    'i2c': {'instance', 'sda', 'scl'},
    'pins': set(STATION),
    'led': {'pin', 'colour', 'active', 'at'},
    'reserved': None,
    'bench_oled': {'ok', 'why', 'spi', *OLED_PINS, *BUTTONS},
    'radio': {'driver', 'bsp', 'switch', *SWITCH_STATES, 'off_verified', 'pa', 'rfo_lp_max_dbm', 'rfo_hp_max_dbm',
              'tcxo', 'tcxo_mv', 'tcxo_startup_ms', 'dcdc'},
}
PIN_KEYS = {'pin', 'af', 'adc', 'exti', 'at', 'fitted', 'why'}


class BoardError(Exception):
    pass


# ---- ST's pin data ----

def load_pinctrl(name):
    """{pin: {signal: af}} from a hal_stm32 pinctrl file: af is the AF number, or 'ANALOG' for an ADC
    input (signal ADC_IN<n>). Every pin of the package appears in it."""
    path = PINCTRL / f'{name}-pinctrl.dtsi'
    if not path.exists():
        raise BoardError(f'no ST pin data {path.relative_to(ROOT)} (tools/pinctrl/README.md)')
    pins = {}
    entry = re.compile(r"(\w+)_p([a-h])(\d+): \w+ \{\s*pinmux = <STM32_PINMUX\('([A-H])', (\d+), (AF\d+|ANALOG)\)>")
    for label, port, num, port2, num2, mux in entry.findall(path.read_text()):
        pin = f'P{port.upper()}{int(num)}'
        if pin != f'P{port2}{int(num2)}':
            raise BoardError(f'{path.name}: {label}_p{port}{num} has pinmux {port2}{num2}')
        pins.setdefault(pin, {})[label.upper()] = mux if mux == 'ANALOG' else int(mux[2:])
    return pins


# ---- the board ----

class Board:
    """board.toml, checked. pins: every pin the board uses, {pin: what}."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.toml = tomllib.loads((self.dir / 'board.toml').read_text())
        self.problems = []
        b = self.toml.get('board', {})
        self.name = b.get('name', self.dir.name)
        self.pinctrl = load_pinctrl(b.get('pinctrl', ''))
        self.used = {}

    def fail(self, msg):
        self.problems.append(f'{self.name}: {msg}')

    # helpers
    def pin(self, spec, what):
        """The pin of a {pin = ...} entry (or a bare string), checked to exist; None if it has none."""
        pin = spec if isinstance(spec, str) else spec.get('pin')
        if pin is None:
            return None
        if not PIN_RE.match(pin) or pin not in self.pinctrl:
            self.fail(f'{what}: {pin} is not a pin of the {self.toml["board"]["pinctrl"]} package')
            return None
        return pin

    def take(self, pin, what):
        if pin is None:
            return
        if pin in self.used:
            self.fail(f'{pin} is used twice: {self.used[pin]} and {what}')
        else:
            self.used[pin] = what

    def af(self, pin, signal, what):
        """The AF number of `signal` on `pin` (ST's pin data), or None with a problem."""
        signals = self.pinctrl.get(pin, {})
        if signal not in signals or signals[signal] == 'ANALOG':
            have = ', '.join(sorted(s for s, a in signals.items() if a != 'ANALOG')) or 'none'
            self.fail(f'{what}: {pin} has no alternate function {signal} (ST pin data: {have})')
            return None
        return signals[signal]

    def adc(self, pin, channel, what):
        if self.pinctrl.get(pin, {}).get(f'ADC_IN{channel}') != 'ANALOG':
            have = ', '.join(sorted(s for s, a in self.pinctrl.get(pin, {}).items() if a == 'ANALOG')) or 'none'
            self.fail(f'{what}: {pin} is not ADC1_IN{channel} (ST pin data: {have})')

    # sections
    def check_keys(self):
        for section in self.toml:
            if section not in KEYS:
                self.fail(f'unknown section [{section}]')
        for section, allowed in KEYS.items():
            tables = self.toml.get(section, [])
            for table in tables if isinstance(tables, list) else [tables]:
                for key, value in table.items():
                    if allowed is not None and key not in allowed:
                        self.fail(f'[{section}] has an unknown key {key!r}')
                    if isinstance(value, dict) and not set(value) <= PIN_KEYS:
                        self.fail(f'[{section}] {key} has unknown keys {sorted(set(value) - PIN_KEYS)}')

    def check(self):
        self.check_keys()
        self.check_board()
        self.check_console()
        self.check_i2c()
        self.check_station()
        self.check_leds()
        self.check_reserved()
        self.check_oled()
        self.check_radio()
        self.check_exti()
        self.check_core()
        if self.problems:
            raise BoardError('\n'.join(self.problems))
        return self

    def check_board(self):
        b = self.toml.get('board', {})
        for key in ('name', 'title', 'mcu', 'mcu_define', 'pinctrl', 'startup', 'ldscript', 'roles', 'flash', 'unlock'):
            if key not in b:
                self.fail(f'[board] needs {key}')
        if b.get('name') != self.dir.name:
            self.fail(f'[board] name is {b.get("name")!r}, its directory {self.dir.name!r}')
        if not b.get('roles') or not set(b.get('roles', ())) <= set(ROLES):
            self.fail(f'[board] roles must be some of {ROLES}')
        if b.get('flash') not in FLASH:
            self.fail(f'[board] flash must be one of {tuple(FLASH)}')
        if b.get('unlock') not in UNLOCK:
            self.fail(f'[board] unlock must be one of {UNLOCK}')
        for key in ('startup', 'ldscript'):
            if key in b and not (self.dir / b[key]).exists():
                self.fail(f'[board] {key} {b[key]} is not in the board directory')

    def check_console(self):
        c = self.toml.get('console', {})
        uart = c.get('uart', '')
        if not re.fullmatch(r'(US|LPU)ART\d', uart):
            self.fail(f'[console] uart {uart!r} is not a USARTn or LPUARTn')
        for end in ('tx', 'rx'):
            pin = self.pin(c.get(end, {}), f'console {end}')
            self.take(pin, f'console {end.upper()}')
            if pin:
                self.af(pin, f'{uart}_{end.upper()}', f'console {end}')

    def check_i2c(self):
        i = self.toml.get('i2c', {})
        inst = i.get('instance', '')
        if not re.fullmatch(r'I2C\d', inst):
            self.fail(f'[i2c] instance {inst!r} is not an I2Cn')
        afs = set()
        for line in ('sda', 'scl'):
            pin = self.pin(i.get(line, {}), f'I2C {line}')
            self.take(pin, f'I2C {line.upper()}')
            if pin:
                afs.add(self.af(pin, f'{inst}_{line.upper()}', f'I2C {line}'))
        if len(afs) > 1:
            self.fail(f'[i2c] SDA and SCL need one alternate function (App/i2c_bus.lit.md sets one): {sorted(afs, key=str)}')

    def check_station(self):
        pins = self.toml.get('pins', {})
        for fn, need in STATION.items():
            spec = pins.get(fn)
            if spec is None:
                self.fail(f'[pins] needs {fn}')
                continue
            fitted = spec.get('fitted', True)
            pin = self.pin(spec, fn)
            if fitted and pin is None:
                self.fail(f'[pins] {fn} is fitted but has no pin')
            if not fitted:
                if 'why' not in spec:
                    self.fail(f'[pins] {fn}: fitted = false needs a why')
                if not need.get('charger'):
                    self.fail(f'[pins] {fn} must be fitted: the station has no build without it')
                continue
            self.take(pin, fn)
            if 'af' in need:
                if not re.fullmatch(need['af'], spec.get('af', '')):
                    self.fail(f'[pins] {fn} needs af matching {need["af"]}, not {spec.get("af")!r}')
                elif pin:
                    self.af(pin, spec['af'], fn)
            if need.get('adc'):
                if 'adc' not in spec:
                    self.fail(f'[pins] {fn} needs its ADC channel (adc = n)')
                elif pin:
                    self.adc(pin, spec['adc'], fn)
            if need.get('exti') and not spec.get('exti'):
                self.fail(f'[pins] {fn} needs exti = true (App/board_inputs.c takes its interrupt)')
        charger = [pins.get(f, {}).get('fitted', True) for f in STATION if STATION[f].get('charger')]
        if any(charger) and not all(charger):
            self.fail('[pins] the charger pins (iset, pgood, chg) are all fitted or none (BOARD_CHARGER_PINS)')
        if all(charger) and pins.get('iset', {}).get('pin', 'P?')[1] != pins.get('vane', {}).get('pin', 'P!')[1]:
            self.fail('[pins] iset must be on the vane\'s port (App/board_inputs.c sets both up in one call)')

    def check_leds(self):
        leds = self.toml.get('led', [])
        if not 1 <= len(leds) <= 3:
            self.fail('[[led]]: one to three LEDs (App/leds.h: blue, green, red)')
        if len({led.get('active') for led in leds}) > 1 or not {led.get('active') for led in leds} <= {'high', 'low'}:
            self.fail('[[led]]: every LED is active "high", or every LED "low"')
        for n, led in enumerate(leds, 1):
            self.take(self.pin(led, f'LED{n}'), f'LED{n} ({led.get("colour")})')

    def check_reserved(self):
        for what, spec in self.toml.get('reserved', {}).items():
            self.take(self.pin(spec, what), f'{what} ({spec.get("why", "reserved")})')

    def check_oled(self):
        o = self.toml.get('bench_oled', {})
        if not o.get('ok'):
            if not o.get('why'):
                self.fail('[bench_oled] ok = false needs a why (the #error text)')
            return
        spi = o.get('spi', '')
        for p in OLED_PINS + BUTTONS:
            pin = self.pin(o.get(p, {}), f'OLED {p}')
            if pin is None:
                self.fail(f'[bench_oled] needs {p}')
                continue
            self.take(pin, f'bench OLED {p.upper()}')
            if p in ('sck', 'mosi'):
                self.af(pin, f'{spi}_{p.upper()}', f'OLED {p}')
        ports = {p: o.get(p, {}).get('pin', 'P?')[1] for p in OLED_PINS + BUTTONS}
        if spi != 'SPI1':
            self.fail('[bench_oled] spi must be SPI1 (oled_spi1.c and App/oled_dma.c drive SPI1)')
        if not ports['cs'] == ports['sck'] == ports['mosi'] or ports['rst'] != ports['dc']:
            self.fail('[bench_oled] CS, SCK and MOSI share a port, and RST and DC another (oled_spi1.c)')
        if ports['b1'] != ports['b2']:
            self.fail('[bench_oled] b1 and b2 must share a port (App/board_inputs.c sets both up in one call)')

    def check_radio(self):
        r = self.toml.get('radio', {})
        if r.get('driver') not in DRIVERS:
            self.fail(f'[radio] driver must be one of {DRIVERS}')
        if r.get('driver') == 'st-bsp' and r.get('bsp') not in BSP_FILES:
            self.fail(f'[radio] driver "st-bsp" needs bsp, one of {tuple(BSP_FILES)}')
        switch = r.get('switch', [])
        if not 1 <= len(switch) <= 3:
            self.fail('[radio] switch: one to three control pins')
        for n, spec in enumerate(switch, 1):
            self.take(self.pin(spec, f'RF switch CTRL{n}'), f'RF switch CTRL{n}')
        for state in SWITCH_STATES:
            levels = r.get(state)
            if not isinstance(levels, list) or len(levels) != len(switch) or not set(levels) <= {0, 1}:
                self.fail(f'[radio] {state}: one level (0 or 1) per switch pin')
        if r.get('pa') not in PA:
            self.fail(f'[radio] pa must be one of {tuple(PA)}')
        if r.get('tcxo') and r.get('tcxo_mv') not in TCXO_MV:
            self.fail(f'[radio] tcxo_mv must be one of {tuple(TCXO_MV)}')
        for key in ('rfo_lp_max_dbm', 'rfo_hp_max_dbm', 'tcxo_startup_ms'):
            if not isinstance(r.get(key), int):
                self.fail(f'[radio] needs {key}')

    def exti_users(self):
        """(line, what, own vector needed) for every EXTI input."""
        users = []
        pins = self.toml.get('pins', {})
        for fn in ('rain', 'chg'):
            spec = pins.get(fn, {})
            if spec.get('fitted', True) and spec.get('pin'):
                users.append((int(spec['pin'][2:]), fn, fn == 'rain'))
        o = self.toml.get('bench_oled', {})
        if o.get('ok'):
            for b in BUTTONS:
                if o.get(b, {}).get('pin'):
                    users.append((int(o[b]['pin'][2:]), f'OLED {b.upper()}', b != 'b3'))
        return users

    def check_exti(self):
        lines = {}
        for line, what, own in self.exti_users():
            if line in lines:
                self.fail(f'EXTI line {line} is used twice: {lines[line]} and {what}')
            lines[line] = what
            if own and line > 4:
                self.fail(f'{what} is on EXTI line {line}: it needs a vector of its own (lines 0 to 4)')
            if not own and line <= 4:
                self.fail(f'{what} is on EXTI line {line}: App/board_inputs.c serves only lines 5 to 15 for it')

    def check_core(self):
        """The board's CubeMX code (Core/) drives the LEDs and the console itself: it must agree."""
        main_h = self.dir / 'Core/Inc/main.h'
        if main_h.exists():
            text = main_h.read_text()
            for n, led in enumerate(self.toml.get('led', []), 1):
                pin = led.get('pin', 'P?0')
                want = (f'#define LED{n}_Pin GPIO_PIN_{pin[2:]}', f'#define LED{n}_GPIO_Port GPIO{pin[1]}')
                if not all(w in text for w in want):
                    self.fail(f'LED{n} is {pin} here but not in Core/Inc/main.h')
        usart_c = self.dir / 'Core/Src/usart.c'
        if usart_c.exists():
            uart = self.toml.get('console', {}).get('uart', '')
            text = usart_c.read_text()
            if f'UART_HandleTypeDef {handle(uart)};' not in text or f'{handle(uart)}.Instance = {uart};' not in text:
                self.fail(f'the console is {uart} here but Core/Src/usart.c does not set up {handle(uart)} on it')


def handle(uart):
    """CubeMX's handle name: huart2 for USART2, hlpuart1 for LPUART1."""
    return 'h' + uart.lower().replace('usart', 'uart')


# ---- rendering ----

def port(pin):
    return f'GPIO{pin[1]}'


def gpio_pin(pin):
    return f'GPIO_PIN_{int(pin[2:])}'


def clk(ports):
    calls = [f'__HAL_RCC_{p}_CLK_ENABLE()' for p in sorted(set(ports))]
    return calls[0] if len(calls) == 1 else 'do { ' + '; '.join(calls) + '; } while (0)'


def comment(spec, detail=''):
    """/* PB5 = D4, CN9.5: LPTIM1_IN1 AF1 */: the pin first (wiring.py reads it), then where it is."""
    pin, at = spec['pin'], spec.get('at')
    text = pin if not at or at == pin else f'{pin} = {at}'
    if detail:
        text += f': {detail}'
    return f'/* {text} */'


def exti_vector(line):
    if line <= 4:
        return f'EXTI{line}'
    return 'EXTI9_5' if line <= 9 else 'EXTI15_10'


class Render:
    def __init__(self, board):
        self.b = board
        self.t = board.toml
        self.lines = []

    def out(self, *lines):
        self.lines.extend(lines)

    def define(self, name, value, note=''):
        self.out(f'#define {name} {value}' + (f' {note}' if note else ''))

    def pin_pair(self, prefix, spec, detail='', bit=False, clock=False):
        self.define(f'{prefix}_PORT', port(spec['pin']))
        self.define(f'{prefix}_PIN', gpio_pin(spec['pin']), comment(spec, detail))
        if bit:
            self.define(f'{prefix}_BIT', f'{int(spec["pin"][2:])}U')
        if clock:
            self.define(f'{prefix}_CLK_ENABLE()', clk([port(spec['pin'])]))

    def text(self):
        return '\n'.join(self.lines) + '\n'


def render_pins(board):
    t, r = board.toml, Render(board)
    title = t['board']['title']
    r.out('#ifndef BOARD_PINS_H', '#define BOARD_PINS_H',
          f'/* {BANNER}',
          f' * The station\'s pins on the {title}, by function: the names the node\'s App/ code uses instead of',
          ' * naming pins itself (tools/board_lint.py). Macros only: the file that uses them includes',
          ' * stm32wlxx_hal.h. Every *_PIN line is "#define NAME GPIO_PIN_n", then a comment that starts with',
          ' * the pin and says where it is: hardware/bench-breadboard-r0/source/wiring.py checks them against its',
          ' * nets. */',
          '#include "board_caps.h"', '')
    render_i2c(r)
    render_station(r)
    render_exti(r)
    render_leds(r)
    render_console(r)
    if t.get('bench_oled', {}).get('ok'):
        render_oled(r)
    r.out('#endif')
    return r.text()


def render_i2c(r):
    i = r.t['i2c']
    inst, sda, scl = i['instance'], i['sda'], i['scl']
    af = r.b.af(sda['pin'], f'{inst}_SDA', 'I2C sda')
    n = inst[3:]
    r.out(f'/* {inst}, the station bus (App/i2c_bus.lit.md): SDA {sda["pin"]}, SCL {scl["pin"]}, AF{af}. */')
    r.pin_pair('BOARD_I2C_SDA', sda)
    r.pin_pair('BOARD_I2C_SCL', scl)
    if port(sda['pin']) == port(scl['pin']):
        p = port(sda['pin'])
        r.out('/* One port: each step takes both pins at once. */')
        r.define('BOARD_I2C_GPIO_CLK_ENABLE()', clk([p]))
        r.define('BOARD_I2C_PINS_INIT(init)', f'HAL_GPIO_Init({p}, (init))', '/* (init)->Pin holds SDA | SCL */')
        r.define('BOARD_I2C_PINS_DEINIT()', f'HAL_GPIO_DeInit({p}, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN)')
        r.define('BOARD_I2C_PINS_HIGH()', f'HAL_GPIO_WritePin({p}, BOARD_I2C_SDA_PIN | BOARD_I2C_SCL_PIN, GPIO_PIN_SET)')
    else:
        r.out('/* Two ports: each step takes one pin at a time. */')
        r.define('BOARD_I2C_GPIO_CLK_ENABLE()', clk([port(sda['pin']), port(scl['pin'])]))
        r.out('#define BOARD_I2C_PINS_INIT(init) do { GPIO_InitTypeDef *bp_ = (init); \\',
              '    bp_->Pin = BOARD_I2C_SDA_PIN; HAL_GPIO_Init(BOARD_I2C_SDA_PORT, bp_); \\',
              '    bp_->Pin = BOARD_I2C_SCL_PIN; HAL_GPIO_Init(BOARD_I2C_SCL_PORT, bp_); } while (0)',
              '#define BOARD_I2C_PINS_DEINIT() do { HAL_GPIO_DeInit(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN); \\',
              '    HAL_GPIO_DeInit(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN); } while (0)',
              '#define BOARD_I2C_PINS_HIGH() do { HAL_GPIO_WritePin(BOARD_I2C_SDA_PORT, BOARD_I2C_SDA_PIN, GPIO_PIN_SET); \\',
              '    HAL_GPIO_WritePin(BOARD_I2C_SCL_PORT, BOARD_I2C_SCL_PIN, GPIO_PIN_SET); } while (0)')
    r.define('BOARD_I2C', inst)
    r.define('BOARD_I2C_AF', f'GPIO_AF{af}_{inst}')
    r.define('BOARD_I2C_PERIPHCLK', f'RCC_PERIPHCLK_{inst}')
    r.define('BOARD_I2C_CLKSEL', f'I2c{n}ClockSelection')
    r.define('BOARD_I2C_CLKSRC_PCLK1', f'RCC_{inst}CLKSOURCE_PCLK1')
    r.define('BOARD_I2C_CLK_ENABLE()', f'__HAL_RCC_{inst}_CLK_ENABLE()')
    r.define('BOARD_I2C_CLK_DISABLE()', f'__HAL_RCC_{inst}_CLK_DISABLE()')
    for kind in ('EV', 'ER'):
        r.define(f'BOARD_I2C_{kind}_IRQn', f'{inst}_{kind}_IRQn')
        r.define(f'BOARD_I2C_{kind}_IRQHandler', f'{inst}_{kind}_IRQHandler')
    r.out('')


def render_station(r):
    p = r.t['pins']
    cups = p['cups']
    lptim = cups['af'].split('_')[0]
    af = r.b.af(cups['pin'], cups['af'], 'cups')
    r.out(f'/* The anemometer cups: {cups["af"]} (AF{af}) on {cups["pin"]}. BIT is the pin\'s number (its PUPDR field). */')
    r.pin_pair('BOARD_CUPS', cups, f'{cups["af"]} AF{af}', bit=True, clock=True)
    r.define('BOARD_CUPS_AF', f'GPIO_AF{af}_{lptim}')
    r.define('BOARD_CUPS_LPTIM', lptim)
    r.define('BOARD_CUPS_LPTIM_PERIPHCLK', f'RCC_PERIPHCLK_{lptim}')
    r.define('BOARD_CUPS_LPTIM_CLKSEL', f'Lptim{lptim[5:]}ClockSelection')
    r.define('BOARD_CUPS_LPTIM_CLKSRC_LSE', f'RCC_{lptim}CLKSOURCE_LSE')
    r.define('BOARD_CUPS_LPTIM_CLK_ENABLE()', f'__HAL_RCC_{lptim}_CLK_ENABLE()')
    r.out('')
    vane, iset, vin = p['vane'], p['iset'], p['vin']
    r.out('/* The ADC inputs: the wind vane divider, the charger\'s ISET node (on the vane\'s port) and the charger',
          '   input divider. */')
    r.pin_pair('BOARD_VANE', vane, f'ADC1_IN{vane["adc"]}')
    r.define('BOARD_VANE_CHANNEL', f'ADC_CHANNEL_{vane["adc"]}')
    if iset.get('fitted', True):
        r.define('BOARD_ISET_PIN', gpio_pin(iset['pin']), comment(iset, f'ADC1_IN{iset["adc"]}'))
        r.define('BOARD_ISET_CHANNEL', f'ADC_CHANNEL_{iset["adc"]}')
    else:
        r.out(f'/* ISET is not fitted ({iset["why"]}): its rank of the ADC sequence converts VREFINT, a reading',
              '   nobody uses; the sequence keeps its four ranks. */')
        r.define('BOARD_ISET_PIN', '0U')
        r.define('BOARD_ISET_CHANNEL', 'ADC_CHANNEL_VREFINT')
    r.pin_pair('BOARD_VIN', vin, f'ADC1_IN{vin["adc"]}')
    r.define('BOARD_VIN_CHANNEL', f'ADC_CHANNEL_{vin["adc"]}')
    adc_ports = [port(vane['pin']), port(vin['pin'])]
    r.define('BOARD_ADC_GPIO_CLK_ENABLE()', clk(adc_ports))
    r.out('')
    rain = p['rain']
    line = int(rain['pin'][2:])
    r.out(f'/* The rain gauge: {rain["pin"]}, EXTI line {line} on its own vector. */')
    r.pin_pair('BOARD_RAIN', rain, f'EXTI{line}', bit=True)
    r.define('BOARD_RAIN_EXTI_LINE', f'LL_EXTI_LINE_{line}')
    r.define('BOARD_RAIN_IRQn', f'{exti_vector(line)}_IRQn')
    r.define('BOARD_RAIN_IRQHandler', f'{exti_vector(line)}_IRQHandler')
    r.out('')
    charger = all(p[f].get('fitted', True) for f in ('iset', 'pgood', 'chg'))
    r.out('/* The bq24074 charger pins (PGOOD, CHG and ISET above). 1: fitted (App/board_inputs.c, App/power_acq.c);',
          '   0: the charger status and its battery current are none, and the pins are never configured. */')
    r.define('BOARD_CHARGER_PINS', '1' if charger else '0')
    for fn in ('pgood', 'chg'):
        spec = p[fn]
        detail = '' if spec.get('fitted', True) else f'not fitted ({spec["why"]})'
        if fn == 'chg':
            detail = (f'EXTI{int(spec["pin"][2:])}' + (f', {detail}' if detail else '')) if spec.get('pin') else detail
        if spec.get('pin'):
            r.pin_pair(f'BOARD_{fn.upper()}', spec, detail)
        else:
            r.define(f'BOARD_{fn.upper()}_PORT', port(rain['pin']), f'/* not fitted ({spec["why"]}) */')
            r.define(f'BOARD_{fn.upper()}_PIN', '0U')
    r.out('')
    mux, power = p['mux_reset'], p['sensor_power']
    r.out('/* The mux RESET (active low, WS_I2C_MUX=1) and the sensor power switch. */')
    r.pin_pair('BOARD_MUX_RESET', mux)
    r.pin_pair('BOARD_SENSOR_POWER', power, clock=True)
    inputs = [port(rain['pin']), port(mux['pin'])] + [port(p[f]['pin']) for f in ('pgood', 'chg') if p[f].get('pin')]
    r.out('/* The clocks of the digital inputs\' ports (rain, PGOOD, CHG) and the mux RESET\'s. */')
    r.define('BOARD_INPUTS_CLK_ENABLE()', clk(inputs))
    r.out('')


def render_exti(r):
    r.out('/* The shared EXTI vectors, which App/board_inputs.c serves whole: a pending line it skipped would re-enter',
          '   that interrupt forever. */')
    for name, lines, vec in (('5TO9', range(5, 10), 'EXTI9_5'), ('10TO15', range(10, 16), 'EXTI15_10')):
        r.define(f'BOARD_EXTI_{name}_IRQn', f'{vec}_IRQn')
        r.define(f'BOARD_EXTI_{name}_IRQHandler', f'{vec}_IRQHandler')
        r.define(f'BOARD_EXTI_{name}_LINES', '{ ' + ', '.join(f'GPIO_PIN_{n}' for n in lines) + ' }')
    r.out('')


def render_leds(r):
    leds = r.t['led']
    first = leds[0]['pin']
    names = ', '.join(f'{led["colour"]} {led["pin"]}' for led in leds)
    r.out(f'/* The user LEDs, blue, green and red (App/leds.h): {names}; on when {leds[0]["active"]}.')
    if len(leds) < 3:
        r.out('   A missing LED is pin 0 on the first LED\'s port: its writes are no-ops (HAL_GPIO_WritePin writes a',
              '   zero mask to BSRR or BRR). Only blue\'s pin is ever read (App/leds.c, the heartbeat). */')
    else:
        r.out('   The order is App/leds.h\'s. */')
    ports = [port(led['pin']) for led in leds] + [port(first)] * (3 - len(leds))
    pins = [gpio_pin(led['pin']) for led in leds] + ['0U'] * (3 - len(leds))
    r.define('BOARD_LED_PORTS', '{ ' + ', '.join(ports) + ' }')
    r.define('BOARD_LED_PINS', '{ ' + ', '.join(pins) + ' }')
    on, off = ('GPIO_PIN_SET', 'GPIO_PIN_RESET') if leds[0]['active'] == 'high' else ('GPIO_PIN_RESET', 'GPIO_PIN_SET')
    r.define('BOARD_LED_ON', on)
    r.define('BOARD_LED_OFF', off)
    r.out('')


def render_console(r):
    c = r.t['console']
    uart = c['uart']
    r.out(f'/* The console: {uart} ({c["tx"]["pin"]} TX, {c["rx"]["pin"]} RX) to {c["to"]} (Core/Src/usart.c), its',
          '   TX on DMA. The names the node\'s interrupt file (stage0-node/Core/Src/stm32wlxx_it.c) uses. */')
    r.define('BOARD_CONSOLE_UART', handle(uart))
    r.define('BOARD_CONSOLE_DMA_TX', f'hdma_{uart.lower()}_tx')
    r.define('BOARD_CONSOLE_IRQHandler', f'{uart}_IRQHandler')
    r.define('BOARD_CONSOLE_NAME', f'"{uart}"')
    r.out('')


def render_oled(r):
    o = r.t['bench_oled']
    spi = o['spi']
    af = r.b.af(o['sck']['pin'], f'{spi}_SCK', 'OLED sck')
    r.out(f'/* The bench OLED (WS_BENCH_OLED=1; oled_spi1.c): CS, RST and DC are GPIOs, SCK and MOSI {spi} AF{af}. */')
    for p in OLED_PINS:
        detail = f'{spi}_{p.upper()} AF{af}' if p in ('sck', 'mosi') else ''
        r.pin_pair(f'BOARD_OLED_{p.upper()}', o[p], detail)
    r.define('BOARD_OLED_SPI', spi)
    r.define('BOARD_OLED_SPI_AF', f'GPIO_AF{af}_{spi}')
    r.define('BOARD_OLED_GPIO_CLK_ENABLE()', clk([port(o[p]['pin']) for p in OLED_PINS]))
    r.out('/* Its buttons: B1 and B2 on vectors of their own, B3 on a shared one. */')
    for b in BUTTONS:
        line = int(o[b]['pin'][2:])
        r.pin_pair(f'BOARD_{b.upper()}', o[b], f'EXTI{line}')
        if b != 'b3':
            r.define(f'BOARD_{b.upper()}_IRQn', f'{exti_vector(line)}_IRQn')
            r.define(f'BOARD_{b.upper()}_IRQHandler', f'{exti_vector(line)}_IRQHandler')
    r.define('BOARD_BUTTONS_CLK_ENABLE()', clk([port(o['b1']['pin'])]))
    r.out('')


def render_caps(board):
    t, r = board.toml, Render(board)
    b, radio, oled = t['board'], t['radio'], t.get('bench_oled', {})
    roles = b['roles']
    r.out('#ifndef BOARD_CAPS_H', '#define BOARD_CAPS_H',
          f'/* {BANNER}',
          f' * What the {b["title"]} can do, and its radio front end: the generic',
          ' * firmware/board/stm32wl/SubGHz_Phy/Target/radio_board_if.c reads the RF switch, TCXO and PA path here. */',
          '')
    r.define('BOARD_NAME', f'"{b["name"]}"')
    for role in ROLES:
        r.define(f'BOARD_ROLE_{role.upper()}', '1' if role in roles else '0')
    r.define('BOARD_BENCH_OLED_OK', '1' if oled.get('ok') else '0')
    r.define('BOARD_LED_COUNT', str(len(t['led'])))
    r.out('')
    r.out('/* Feature requirements: a build the board cannot run stops here. */',
          '#if defined(WS_BENCH_OLED) && WS_BENCH_OLED && !BOARD_BENCH_OLED_OK',
          f'#error "WS_BENCH_OLED=1 on the {b["name"]} board: {oled.get("why", "")}"',
          '#endif')
    for role in (r_ for r_ in ROLES if r_ not in roles):
        r.out(f'#if defined(WS_ROLE_{role})',
              f'#error "ROLE={role} on the {b["name"]} board: its board.toml roles are {", ".join(roles)}"',
              '#endif')
    r.out('')
    render_radio(r, radio)
    r.out('#endif')
    return r.text()


def render_radio(r, radio):
    switch = radio['switch']
    r.out(f'/* The radio: the RF switch on {", ".join(switch)} (CTRL1..CTRL{len(switch)}), driven by '
          + ('ST\'s BSP' if radio['driver'] == 'st-bsp' else 'radio_board_if.c') + '. Truth table (levels in that order):')
    for state in SWITCH_STATES:
        note = '   UNVERIFIED on the hardware (board.toml)' if state == 'off' and radio.get('off_verified') is False else ''
        r.out(f'     {state:<6} ' + '  '.join(str(v) for v in radio[state]) + note)
    r.out('   */')
    r.define('BOARD_RF_SWITCH_BSP', '1' if radio['driver'] == 'st-bsp' else '0')
    r.define('BOARD_RFO', PA[radio['pa']], f'/* PA path: {radio["pa"]} */')
    r.define('BOARD_RFO_LP_MAX_DBM', str(radio['rfo_lp_max_dbm']))
    r.define('BOARD_RFO_HP_MAX_DBM', str(radio['rfo_hp_max_dbm']))
    r.define('BOARD_TCXO', '1U' if radio['tcxo'] else '0U')
    r.define('BOARD_TCXO_CTRL_VOLTAGE', f'TCXO_CTRL_{TCXO_MV.get(radio.get("tcxo_mv"), "1_7V")}')
    r.define('BOARD_TCXO_STARTUP_MS', f'( {radio["tcxo_startup_ms"]}UL )')
    r.define('BOARD_DCDC', '1U' if radio['dcdc'] else '0U')
    if radio['driver'] == 'gpio':
        n = len(switch)
        r.out('/* For radio_board_if.c: the switch pins, the rf_switch() parameters and body, and each state\'s levels. */')
        r.define('BOARD_RF_SW_CLK_ENABLE()', clk([port(p) for p in switch]))
        init = ' '.join(f'(init)->Pin = {gpio_pin(p)}; HAL_GPIO_Init({port(p)}, (init));' for p in switch)
        r.define('BOARD_RF_SW_PINS_INIT(init)', f'do {{ {init} }} while (0)')
        deinit = ' '.join(f'HAL_GPIO_DeInit({port(p)}, {gpio_pin(p)});' for p in switch)
        r.define('BOARD_RF_SW_PINS_DEINIT()', f'do {{ {deinit} }} while (0)')
        r.define('BOARD_RF_SW_PARAMS', ', '.join(f'GPIO_PinState ctrl{i}' for i in range(1, n + 1)))
        write = ' '.join(f'HAL_GPIO_WritePin({port(p)}, {gpio_pin(p)}, ctrl{i});' for i, p in enumerate(switch, 1))
        r.define('BOARD_RF_SW_WRITE()', f'do {{ {write} }} while (0)')
        for state in SWITCH_STATES:
            r.define(f'BOARD_RF_SW_{state.upper()}', ', '.join('GPIO_PIN_SET' if v else 'GPIO_PIN_RESET' for v in radio[state]))
    r.out('')


def render_mk(board):
    t = board.toml
    b, radio, oled = t['board'], t['radio'], t.get('bench_oled', {})
    lines = [f'# {BANNER}', f'# The {b["title"]}: what firmware/board/stm32wl/rules.mk and the project Makefiles take',
             '# from the board.', 'ifndef BOARD_GEN_MK', 'BOARD_GEN_MK := 1',
             f'BOARD_NAME          := {b["name"]}',
             f'BOARD_ROLES         := {" ".join(b["roles"])}',
             f'BOARD_BENCH_OLED_OK := {1 if oled.get("ok") else 0}',
             f'BOARD_BENCH_OLED_WHY := {oled.get("why", "")}',
             f'BOARD_FLASH         := {b["flash"]}',
             f'MCU_DEF  = {b["mcu_define"]}',
             f'ASM_SRC  = $(BOARD_DIR)/{b["startup"]}',
             f'LDSCRIPT = $(BOARD_DIR)/{b["ldscript"]}']
    if radio['driver'] == 'st-bsp':
        bsp = f'$(CUBE)/Drivers/BSP/{radio["bsp"]}'
        lines += ['BSP_SRC  = ' + ' '.join(f'{bsp}/{f}' for f in BSP_FILES[radio['bsp']]), f'BSP_INC  = {bsp}']
    else:
        lines += ['BSP_SRC  =', 'BSP_INC  =']
    if b['unlock'] == 'openocd-stm32l4x':
        lines += ['',
                  '# RDP level 1 to 0 (mass-erases the flash): OpenOCD\'s stm32l4x driver, which target/stm32wlx.cfg uses',
                  '# for bank 0. "stm32l4x option_load" applies it at once (a system reset).',
                  'unlock:',
                  f'\t@test -n "$(SERIAL)" || (echo "usage: make BOARD={b["name"]} unlock SERIAL=<ST-LINK serial>"; exit 1)',
                  '\topenocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \\',
                  '\t  -c "reset_config srst_only srst_nogate connect_assert_srst" \\',
                  '\t  -c "init" -c "reset halt" -c "stm32l4x unlock 0" -c "stm32l4x option_load 0" -c "shutdown"',
                  '.PHONY: unlock']
    lines.append('endif')
    return '\n'.join(lines) + '\n'


def pin_rows(board):
    """Every pin of the board: (function, pin, at, signal, note)."""
    t, rows = board.toml, []
    c, i = t['console'], t['i2c']
    for end in ('tx', 'rx'):
        rows.append((f'console {end.upper()}', c[end]['pin'], c[end].get('at', ''), f'{c["uart"]}_{end.upper()}', c['to']))
    for line in ('sda', 'scl'):
        rows.append((f'I2C {line.upper()}', i[line]['pin'], i[line].get('at', ''), f'{i["instance"]}_{line.upper()}', ''))
    for fn, spec in t['pins'].items():
        signal = spec.get('af') or (f'ADC1_IN{spec["adc"]}' if 'adc' in spec else '') or \
            (f'EXTI{int(spec["pin"][2:])}' if spec.get('exti') and spec.get('pin') else 'GPIO')
        note = '' if spec.get('fitted', True) else f'not fitted: {spec["why"]}'
        rows.append((fn, spec.get('pin', ''), spec.get('at', ''), signal, note))
    for n, led in enumerate(t['led'], 1):
        rows.append((f'LED{n}', led['pin'], led.get('at', ''), 'GPIO', f'{led["colour"]}, active {led["active"]}'))
    o = t.get('bench_oled', {})
    if o.get('ok'):
        for p in OLED_PINS + BUTTONS:
            signal = f'{o["spi"]}_{p.upper()}' if p in ('sck', 'mosi') else ('EXTI' + o[p]['pin'][2:] if p in BUTTONS else 'GPIO')
            rows.append((f'bench OLED {p.upper()}', o[p]['pin'], o[p].get('at', ''), signal, 'WS_BENCH_OLED=1 only'))
    radio = t['radio']
    for n, p in enumerate(radio['switch'], 1):
        rows.append((f'RF switch CTRL{n}', p, '', 'GPIO', 'ST BSP' if radio['driver'] == 'st-bsp' else 'radio_board_if.c'))
    for what, spec in t.get('reserved', {}).items():
        rows.append((what, spec['pin'], spec.get('at', ''), 'reserved', spec.get('why', '')))
    return rows


def render_md(board):
    t = board.toml
    b, radio, oled = t['board'], t['radio'], t.get('bench_oled', {})
    out = [f'<!-- {BANNER} -->', f'# {b["title"]}: pin map', '',
           f'`{b["name"]}`: {b["mcu"]}, roles {", ".join(b["roles"])}, flashed through {FLASH[b["flash"]]}'
           + (', `make unlock` once per new board' if b['unlock'] != 'none' else '') + '. '
           + ('Bench OLED: yes.' if oled.get('ok') else f'Bench OLED: no ({oled["why"]}).'), '',
           '| Function | Pin | Where | Signal | Note |', '|---|---|---|---|---|']
    out += [f'| {fn} | {pin or "-"} | {at or "-"} | {sig} | {note} |' for fn, pin, at, sig, note in pin_rows(board)]
    out += ['', '## Radio', '', f'Driver: {radio["driver"]}. PA path: {radio["pa"]} (RFO_LP max {radio["rfo_lp_max_dbm"]} dBm, '
            f'RFO_HP max {radio["rfo_hp_max_dbm"]} dBm). TCXO: '
            + (f'{radio["tcxo_mv"] / 1000:.1f} V, {radio["tcxo_startup_ms"]} ms start-up.' if radio['tcxo'] else 'none.')
            + f' SMPS: {"yes" if radio["dcdc"] else "no"}.', '',
            '| State | ' + ' | '.join(radio['switch']) + ' |', '|---|' + '---|' * len(radio['switch'])]
    for state in SWITCH_STATES:
        mark = ' (unverified)' if state == 'off' and radio.get('off_verified') is False else ''
        out.append(f'| {state}{mark} | ' + ' | '.join(str(v) for v in radio[state]) + ' |')
    return '\n'.join(out) + '\n'


def render_json(board):
    rows = [dict(zip(('function', 'pin', 'at', 'signal', 'note'), row, strict=True)) for row in pin_rows(board)]
    return json.dumps({'generated': BANNER, 'board': board.name, 'pins': rows}, indent=1) + '\n'


def generate(board):
    """{path: text} of the board's generated files."""
    gen = board.dir / GEN
    return {gen / 'board_pins.h': render_pins(board), gen / 'board_caps.h': render_caps(board),
            gen / 'board.mk': render_mk(board), gen / 'pins.md': render_md(board), gen / 'pins.json': render_json(board)}


def board_dirs():
    return sorted(p.parent for p in BOARDS.glob('*/board.toml'))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true', help='exit 1 if a board is invalid or its gen/ is stale')
    ap.add_argument('--board', action='append', type=Path, help='a board directory (default: every firmware/board/*)')
    args = ap.parse_args(argv)
    stale, failed = [], False
    for d in args.board or board_dirs():
        try:
            files = generate(Board(d).check())
        except BoardError as e:
            print(e, file=sys.stderr)
            failed = True
            continue
        for path, text in files.items():
            if path.exists() and path.read_text() == text:
                continue
            if args.check:
                stale.append(path)
            else:
                path.parent.mkdir(exist_ok=True)
                path.write_text(text)
                print(f'wrote {path}')
    for path in stale:
        print(f'stale: {path} (run tools/boardgen.py)', file=sys.stderr)
    if failed or stale:
        return 1
    if args.check:
        print(f'boards: OK ({len(args.board or board_dirs())} checked against ST\'s pin data; gen/ is current)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
