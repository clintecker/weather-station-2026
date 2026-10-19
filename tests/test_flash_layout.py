"""The flash layout (firmware/stage0-node/App/flash_layout.h) agrees with the linker script and the
build's flash budget, and keeps 24 hours of observations for a full station."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
    from toolchain import CC_STRICT, ROOT, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, needs_cc    # python -m unittest tests.<module>

APP = ROOT/'firmware/stage0-node/App'
PRINT = r'''#include <stdio.h>
#include "node_store.h"
int main(void) {
 printf("%lu %u %u %u %u %u %u\n", (unsigned long)WS_FIRMWARE_BYTES, (unsigned)WS_JOURNAL_FIRST, (unsigned)WS_JOURNAL_PAGES,
        (unsigned)WS_META_PAGE_A, (unsigned)WS_META_PAGE_B, (unsigned)WS_CONFIG_PAGE, (unsigned)JOURNAL_SLOTS_PER_PAGE);
 return 0;
}
'''


def layout(*defines):
    """(firmware bytes, journal first, journal pages, meta A, meta B, config page, slots per page)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp)/'p.c', Path(tmp)/'p'
        src.write_text(PRINT)
        subprocess.run([*CC_STRICT, *defines, f'-I{APP}', f'-I{ROOT}/firmware/common', str(src), '-o', str(exe)],
                       check=True, capture_output=True, text=True)
        return tuple(int(x) for x in subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split())


@needs_cc
class FlashLayout(unittest.TestCase):
    def test_firmware_region_agrees_everywhere(self):
        self.assertEqual(layout()[:6], (112640, 55, 70, 125, 126, 127))
        ld = (ROOT/'firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld').read_text()
        self.assertEqual(re.search(r'^\s*FLASH\s+\(rx\)\s*:.*LENGTH\s*=\s*(\d+)K', ld, re.M)[1], '110')
        mk = (ROOT/'firmware/board/nucleo-wl55jc/board.mk').read_text()
        self.assertEqual(re.search(r'^APP_FLASH_BYTES \?= (\d+)', mk, re.M)[1], '112640')

    def test_a_full_station_keeps_24_hours(self):
        full = layout('-DWS_NODE_FIELDS=WS_FIELDS_DEFINED')
        pages, slots = full[2], full[6]
        self.assertEqual(slots, 21)
        self.assertGreaterEqual((pages - 1) * slots, 1440)


if __name__ == '__main__':
    unittest.main()
