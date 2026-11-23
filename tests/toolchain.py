"""Shared test support: skip rules, host C builds, tool loading and a provisioned station.

Import it before ws0 or gateway, with the dual import every test module uses:

    try:
        from toolchain import needs_cc          # python -m unittest discover -s tests
    except ImportError:
        from tests.toolchain import needs_cc    # python -m unittest tests.<module>

Importing it sets WS0_UNSAFE_FAST_FSYNC=1 (unless already set), so a module run on its own gets the
same fast, non-durable SQLite as the full suite: unit tests do not claim power-loss durability.

The gateway runs on macOS and Linux (Windows is not supported). The C firmware tests need a C
compiler (`cc`) and skip without one. CI sets WS_REQUIRE_CC=1 so a missing compiler fails
instead of silently skipping, and WS_REQUIRE_VENDOR=1 so a
missing vendor/ fails the Mbed TLS tests instead of skipping them.
"""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability

import ctypes
import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HAVE_CC = shutil.which('cc') is not None
REQUIRE_CC = os.environ.get('WS_REQUIRE_CC') == '1'

needs_cc = unittest.skipUnless(HAVE_CC or REQUIRE_CC, 'needs a C compiler (cc) to build firmware C for the host')

MBEDTLS = ROOT/'vendor/STM32CubeWL/Middlewares/Third_Party/mbed-crypto'
REQUIRE_VENDOR = os.environ.get('WS_REQUIRE_VENDOR') == '1'

needs_vendor = unittest.skipUnless(MBEDTLS.exists() or REQUIRE_VENDOR, 'run tools/fetch-vendor.sh to fetch pinned Mbed TLS')

# Host C test programs run under AddressSanitizer + UBSan: an out-of-bounds write or signed overflow
# in the firmware's pure code fails the test instead of passing silently.
# MinGW gcc (Windows; not supported, not in CI) has no sanitizer runtime; there the tests run without them.
SAN = [] if sys.platform == 'win32' else ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                          '-fno-omit-frame-pointer']

CC_STRICT = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror']


def host_library(owner, name, *args, files=None):
    """Compile `args` (flags and sources) into a shared library for ctypes and load it.

    owner is the TestCase class (call from setUpClass); its temp directory is removed by a class
    cleanup. `files` maps file names to C text written into that directory and compiled too.
    Windows cannot delete a library ctypes still has loaded, so cleanup errors are ignored there:
    the OS temp cleanup removes it later."""
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    owner.addClassCleanup(tmp.cleanup)
    extra = []
    for file, text in (files or {}).items():
        path = Path(tmp.name)/file
        path.write_text(text)
        extra.append(str(path))
    lib = Path(tmp.name)/f'{name}.so'
    subprocess.run([*CC_STRICT, '-shared', '-fPIC', *map(str, args), *extra, '-o', str(lib)], check=True)
    return ctypes.CDLL(str(lib))


# The bus and the local modules (firmware/stage0-node/App): every host build of the station side links
# them. A new module is added here, and in the Makefile.
WSMP_APP = ('i2c_bus', 'busymon', 'wsmp_local', 'port_id', 'pod_write', 'mod_th', 'mod_mean', 'mod_reg', 'mod_power', 'power_acq', 'charger', 'mod_wind', 'mod_rain')


def wsmp_sources(app=WSMP_APP, mux=1):
    """The flags and sources of a WSMP harness build (firmware/host/wsmp_harness.c) over these App files.

    mux is the I2C bus profile, WS_I2C_MUX (App/i2c_bus.lit.md section 11). The firmware default is 0
    (the STEMMA QT hub), but these builds pass 1 explicitly so the module, record and calibration tests
    keep the ports board's mux and record EEPROMs; mux=0 is the hub variant, for new tests only."""
    fw = ROOT/'firmware'
    a = fw/'stage0-node/App'
    return [f'-DWS_I2C_MUX={1 if mux else 0}', '-I', fw/'host/include', '-I', fw/'host', '-I', a, '-I', fw/'stage0-node/Core/Inc', '-I', fw,
            '-I', fw/'common', fw/'host/wsmp_harness.c', fw/'host/sim_core.c', fw/'host/i2c_sim.c',
            fw/'host/i2c_models.c', *(a/f'{name}.c' for name in app), fw/'stage0.c', fw/'common/ws_check.c',
            fw/'common/wsmp.c', fw/'common/wsmp_cal.c', fw/'common/wsmp_ident.c', fw/'common/power_regs.c']


def fresh_copy(owner, library):
    """A new copy of a built host library, loaded on its own, so every static starts at zero. owner is
    the TestCase class; its copies share one temp directory, removed by a class cleanup."""
    if '_fresh' not in owner.__dict__:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        owner.addClassCleanup(tmp.cleanup)
        owner._fresh = [Path(tmp.name), 0]
    owner._fresh[1] += 1
    path = owner._fresh[0]/f'{Path(library).stem}-{owner._fresh[1]}.so'
    shutil.copy(library, path)
    return ctypes.CDLL(str(path))


def fresh_station(test, library):
    """fresh_copy of a WSMP harness library for one test, which then fails if the run left a pin error
    on the I2C model or a failed WS_CHECK."""
    lib = fresh_copy(type(test), library)
    test.addCleanup(lambda: test.assertEqual((lib.h_pin_errors(), lib.ws_check_count()), (0, 0)))
    return lib


def check_site(source, needle):
    """The site a failed WS_CHECK reports (firmware/common/ws_check.h), 'file:line', for the check on the
    one line of firmware/<source> that contains needle: read from the source, so a moved line moves it."""
    text = (ROOT/'firmware'/source).read_text()
    file_id = int(re.search(r'^#define WS_CHECK_FILE (\d+)', text, re.M)[1])
    lines = [n for n, line in enumerate(text.splitlines(), 1) if needle in line and 'WS_CHECK(' in line]
    if len(lines) != 1:
        raise AssertionError(f'{source}: {len(lines)} WS_CHECK lines contain {needle!r}')
    return f'{file_id}:{lines[0]}'


def c_function(source, signature, start=0):
    """The body of the first C function whose definition line is `signature` (as written, without the
    brace), at or after `start` in `source`: the text between its braces. The braces of a function body
    nest only through statements, so counting them finds its end."""
    head = source.index(signature + '\n{', start)
    i, depth = head + len(signature) + 1, 0
    for j in range(i, len(source)):     # bound: the source's length
        depth += {'{': 1, '}': -1}.get(source[j], 0)
        if depth == 0:
            return source[i + 1:j]
    raise ValueError(f'{signature}: no closing brace')


def sensor_power_problems(source, init):
    """Problems with the PA9 sensor power drive of a bench firmware (build-progression record 4.6: with
    per-port power PA9 switches the sensor ports, so a sensor is powered only while PA9 is high; on the breadboard,
    since change C left the breadboard build on 2026-11-02, PA9 is unconnected and the drive is harmless): POWER_PIN is
    GPIO_PIN_9 on PA9; sensors_on() sets it high before it becomes a push-pull output, so it never pulses
    low; the init body `init` calls sensors_on() before its first bus access (bus_start, HAL_I2C_*); and
    nothing ever drives the pin low."""
    problems = []
    if not re.search(r'^#define POWER_PIN GPIO_PIN_9\b.*/\* PA9\b', source, re.M):
        problems.append('POWER_PIN is not GPIO_PIN_9 on PA9')
    body = c_function(source, 'static void sensors_on(void)')
    high = body.find('HAL_GPIO_WritePin(GPIOA, POWER_PIN, GPIO_PIN_SET);')
    output = body.find('HAL_GPIO_Init(GPIOA, &en);')
    if high < 0 or output < 0 or high > output:
        problems.append('sensors_on() does not set PA9 high before making it an output')
    if not re.search(r'\.Pin = POWER_PIN, \.Mode = GPIO_MODE_OUTPUT_PP\b', body):
        problems.append('sensors_on() does not make PA9 a push-pull output')
    call = init.find('sensors_on();')
    bus = [i for i in (init.find('bus_start();'), init.find('HAL_I2C_')) if i >= 0]
    if call < 0 or (bus and call > min(bus)):
        problems.append('sensors_on() is not called before the first bus access')
    if re.search(r'POWER_PIN, GPIO_PIN_RESET|HAL_GPIO_TogglePin\(GPIOA, POWER_PIN', source):
        problems.append('PA9 is driven low somewhere')
    return problems


def load_tool(name):
    """tools/<name>.py as a module (tools/ is scripts, not a package)."""
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def quiet_provision(directory, **kw):
    """ws0 provision without its 'Created ...; secrets stay in gateway.json' line on stdout."""
    from ws0.__main__ import provision
    with redirect_stdout(io.StringIO()):
        provision(directory, **kw)


class Station:
    """A freshly provisioned simulation station in a temporary directory: gateway and node.

    The node starts with a trusted clock (synced) unless synced=False; most tests are not about the
    boot clock. Use as a context manager, or through StationTest."""
    def __init__(self, synced=True, node=True, name='state'):
        from ws0.service import Gateway, load_config
        from ws0.simulator import Node
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/name
        quiet_provision(self.root)
        self.cfg = load_config(self.root/'gateway.json')
        self.gateway = Gateway(self.cfg, self.root)
        self.node = Node(self.cfg, self.root) if node else None
        if self.node:
            self.node.synced = synced

    def close(self):
        self.gateway.close()
        if self.node:
            self.node.close()
        self.tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class StationTest(unittest.TestCase):
    """Each test gets self.root, self.cfg, self.gateway and self.node (synced) from a new Station.

    Tests may replace self.gateway or self.node (a restart); tearDown closes whichever is current."""
    def setUp(self):
        station = Station()
        self.tmp, self.root, self.cfg = station.tmp, station.root, station.cfg
        self.gateway, self.node = station.gateway, station.node

    def tearDown(self):
        self.gateway.close()
        self.node.close()
        self.tmp.cleanup()


class StreamPort:
    """A serial port over a byte stream that reads like pyserial's read_until: up to and
    including the terminator, at most `size` bytes per call; b'' once the stream is empty."""
    def __init__(self, data):
        self.data, self.written, self.closed = bytes(data), [], False

    def read_until(self, terminator, size):
        end = self.data.find(terminator)
        n = size if end < 0 else min(size, end + len(terminator))
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def write(self, data):
        self.written.append(data)

    def close(self):
        self.closed = True
