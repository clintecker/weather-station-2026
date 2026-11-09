"""The flash layout (firmware/stage0-node/App/flash_layout.h) agrees with the linker script and the
build's flash budget, and keeps about 10 hours of the build's widest observation record."""
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
 printf("%lu %u %u %u %u %u %u %u %u\n", (unsigned long)WS_FIRMWARE_BYTES, (unsigned)WS_JOURNAL_FIRST, (unsigned)WS_JOURNAL_PAGES,
        (unsigned)WS_META_PAGE_A, (unsigned)WS_META_PAGE_B, (unsigned)WS_CONFIG_PAGE, (unsigned)JOURNAL_SLOTS_PER_PAGE,
        (unsigned)WS_OBS_PLAIN_MAX, (unsigned)WS_PAGE_SIZE);
 return 0;
}
'''


def layout(*defines):
    """(firmware bytes, journal first, journal pages, meta A, meta B, config page, slots per page,
    the build's widest plaintext, page size)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp)/'p.c', Path(tmp)/'p'
        src.write_text(PRINT)
        subprocess.run([*CC_STRICT, *defines, f'-I{APP}', f'-I{ROOT}/firmware/common', str(src), '-o', str(exe)],
                       check=True, capture_output=True, text=True)
        return tuple(int(x) for x in subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split())


@needs_cc
class FlashLayout(unittest.TestCase):
    def test_firmware_region_agrees_everywhere(self):
        self.assertEqual(layout()[0], 95*2048)
        self.assertEqual(95 + 30 + 2 + 1, 128)    # firmware, journal, meta A and B, provisioning
        self.assertEqual(layout()[:6], (194560, 95, 30, 125, 126, 127))
        ld = (ROOT/'firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld').read_text()
        self.assertEqual(re.search(r'^\s*FLASH\s+\(rx\)\s*:.*LENGTH\s*=\s*(\d+)K', ld, re.M)[1], '190')
        mk = (ROOT/'firmware/board/stm32wl/rules.mk').read_text()
        self.assertEqual(re.search(r'^APP_FLASH_BYTES \?= (\d+)', mk, re.M)[1], '194560')

    def test_the_default_build_keeps_about_10_hours(self):
        """The default field set (node_fields.h): the slot is the widest plaintext rounded up to
        double-words plus the commit and ACK double-words, and 29 pages hold at least 9.5 hours of it
        (the journal moves to the SPI flash later, so the on-chip ring is only an outage buffer)."""
        _, _, pages, _, _, _, slots, plain_max, page = layout()
        dw, header = 8, 8
        slot = (-(-plain_max // dw) + 2) * dw
        self.assertEqual(slots, (page - header) // slot)
        self.assertEqual(pages, 30)
        self.assertGreaterEqual((pages - 1) * slots, 570)    # 9.5 h at one record a minute
        self.assertLessEqual(plain_max, 80)    # the per-build ceiling (a 96-byte frame)


if __name__ == '__main__':
    unittest.main()
