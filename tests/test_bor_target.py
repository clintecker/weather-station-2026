"""The brown-out reset target (firmware/stage0-node/Makefile `bor`, `bor-check`), in dry-run mode only:
nothing here talks to a probe. The option-byte layout is written from RM0461 and the STM32WL HAL
(FLASH_OPTR at flash register offset 0x20, BOR_LEV in bits 11:9, OB_BOR_LEVEL_4 = 0x800), not read
from the Makefile."""
import shutil
import subprocess
import unittest
from pathlib import Path

NODE = Path(__file__).resolve().parents[1] / 'firmware' / 'stage0-node'


def make(*args):
    return subprocess.run(['make', '-s', '-C', str(NODE), *args], capture_output=True, text=True)


@unittest.skipUnless(shutil.which('make'), 'make is not installed')
class BorTargetTests(unittest.TestCase):
    def test_dry_run_writes_level_4_into_bits_11_to_9(self):
        r = make('bor', 'DRY_RUN=1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('dry run, nothing sent', r.stdout)
        self.assertIn('-c "stm32l4x option_write 0 0x20 0x800 0xE00"', r.stdout)
        self.assertIn('-c "stm32l4x option_load 0"', r.stdout)
        self.assertIn('-f target/stm32wlx.cfg', r.stdout)

    def test_each_level_maps_to_its_bits(self):
        for level in range(5):
            r = make('bor', 'DRY_RUN=1', f'BOR_LEVEL={level}')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f'option_write 0 0x20 0x{level << 9:X} 0xE00', r.stdout)

    def test_a_bad_level_is_refused(self):
        for level in ('5', '7', 'x', ''):
            r = make('bor', 'DRY_RUN=1', f'BOR_LEVEL={level}')
            self.assertNotEqual(r.returncode, 0, level)
            self.assertNotIn('option_write', r.stdout, level)

    def test_a_real_run_needs_a_serial(self):
        r = make('bor')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('usage: make bor SERIAL=', r.stdout)
        self.assertNotIn('openocd', r.stdout)

    def test_check_only_reads(self):
        r = make('bor-check', 'DRY_RUN=1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('-c "stm32l4x option_read 0 0x20"', r.stdout)
        self.assertNotIn('option_write', r.stdout)
        self.assertNotIn('option_load', r.stdout)


if __name__ == '__main__':
    unittest.main()
