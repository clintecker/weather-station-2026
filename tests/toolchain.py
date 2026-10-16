"""Shared test support: skip rules, host C builds, tool loading and a provisioned station.

Import it before ws0 or gateway, with the dual import every test module uses:

    try:
        from toolchain import needs_cc          # python -m unittest discover -s tests
    except ImportError:
        from tests.toolchain import needs_cc    # python -m unittest tests.<module>

Importing it sets WS0_UNSAFE_FAST_FSYNC=1 (unless already set), so a module run on its own gets the
same fast, non-durable SQLite as the full suite: unit tests do not claim power-loss durability.

The gateway must run on macOS, Linux and Windows. The C firmware tests need a C compiler (`cc`),
which a Windows host usually lacks, so they skip there. CI sets WS_REQUIRE_CC=1 on Linux and
macOS so a missing compiler fails instead of silently skipping, and WS_REQUIRE_VENDOR=1 so a
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
# MinGW gcc (the Windows CI runner's cc) has no sanitizer runtime; there the tests run without them.
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


def check_site(source, needle):
    """The site a failed WS_CHECK reports (firmware/common/ws_check.h), 'file:line', for the check on the
    one line of firmware/<source> that contains needle: read from the source, so a moved line moves it."""
    text = (ROOT/'firmware'/source).read_text()
    file_id = int(re.search(r'^#define WS_CHECK_FILE (\d+)', text, re.M)[1])
    lines = [n for n, line in enumerate(text.splitlines(), 1) if needle in line and 'WS_CHECK(' in line]
    if len(lines) != 1:
        raise AssertionError(f'{source}: {len(lines)} WS_CHECK lines contain {needle!r}')
    return f'{file_id}:{lines[0]}'


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
