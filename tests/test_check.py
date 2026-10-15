"""The run-time check facility (firmware/common/ws_check.h, docs/power-of-ten.md rule 5).

The facility itself: a failed check is counted and the first site kept. The site numbering: every file
that uses WS_CHECK defines a unique WS_CHECK_FILE listed in ws_check.h's table, and stays under 1024
lines (the site keeps the line in 10 bits). That checks fail, are reported and recovered from in the
firmware is tested by the harnesses (test_tx_machine, test_rx_machine, test_store_powercut)."""
import ctypes
import re
import unittest
try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

FW = ROOT/'firmware'
SCOPE = [*sorted((FW/'stage0-node/App').glob('*.c')), *sorted((FW/'common').glob('*.c')), FW/'stage0.c']


def users():
    """{path: WS_CHECK_FILE number} of every firmware file that uses WS_CHECK."""
    found = {}
    for path in SCOPE:
        text = path.read_text()
        if 'WS_CHECK(' in text:
            m = re.search(r'^#define WS_CHECK_FILE (\d+)', text, re.M)
            found[path] = int(m[1]) if m else None
    return found


class Sites(unittest.TestCase):
    def test_every_user_has_a_unique_listed_number_and_fits_the_site(self):
        table = (FW/'common/ws_check.h').read_text()
        listed = {int(n): name for n, name in re.findall(r'(\d+) ((?:App|common)/\w+\.c)', table)}
        found = users()
        self.assertTrue(found)
        for path, number in found.items():
            name = str(path.relative_to(FW/'stage0-node' if 'stage0-node' in path.parts else FW))
            self.assertIsNotNone(number, f'{name} uses WS_CHECK without #define WS_CHECK_FILE')
            self.assertEqual(listed.get(number), name, f'{name} is not number {number} in ws_check.h')
            self.assertLess(len(path.read_text().splitlines()), 1024, f'{name}: a site keeps 10 bits of line')
        self.assertEqual(len(set(found.values())), len(found), 'two files share a number')
        self.assertEqual(set(listed), set(found.values()), 'ws_check.h lists a file that has no checks')


@needs_cc
class Facility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = host_library(cls, 'check', '-I', FW/'common', FW/'common/ws_check.c')
        cls.lib.ws_check_count.restype = ctypes.c_uint32
        cls.lib.ws_check_first.restype = ctypes.c_uint16
        cls.lib.ws_check_fail.argtypes = [ctypes.c_uint16]

    def test_a_failure_is_counted_and_the_first_site_kept(self):
        lib = self.lib
        self.assertEqual((lib.ws_check_count(), lib.ws_check_first()), (0, 0))
        lib.ws_check_fail(5 << 10 | 321)
        lib.ws_check_fail(2 << 10 | 7)
        self.assertEqual((lib.ws_check_count(), lib.ws_check_first()), (2, 5 << 10 | 321))


if __name__ == '__main__':
    unittest.main()
