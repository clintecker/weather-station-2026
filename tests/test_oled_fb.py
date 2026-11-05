"""The shared OLED library (firmware/common/oled_fb.c, font5x7.c, oled_draw.c): frame buffer, text, drawing
primitives and the SSD1325 pixel order. Pure C, compiled for the host; the bench tool and the node both
link it. What the panel shows is checked by eye on the bench."""
import ctypes
import subprocess
import sys
import unittest
try:
    from toolchain import ROOT, host_library, needs_cc   # discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc

COMMON = ROOT/'firmware/common'
OLED_W, OLED_H = 128, 64


@needs_cc
class OledFb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = lib = host_library(cls, 'oled_fb', '-I', COMMON, COMMON/'oled_fb.c', COMMON/'font5x7.c',
                                     COMMON/'oled_draw.c')
        i, p, u = ctypes.c_int, ctypes.c_void_p, ctypes.c_uint
        lib.oled_text.argtypes = [p, i, i, ctypes.c_char_p, i]
        lib.oled_set.argtypes = [p, i, i, i]
        lib.oled_get.argtypes = [p, i, i]
        lib.ssd1325_column.argtypes = [p, u, p]
        lib.oled_rotate180.argtypes = [p, p]
        lib.oled_line.argtypes = [p, i, i, i, i, u]
        lib.oled_box.argtypes = [p, i, i, i, i]
        lib.oled_fill.argtypes = [p, i, i, i, i, i]
        lib.oled_dotgrid.argtypes = [p, i, i, i, i, i]
        lib.oled_invert.argtypes = [p, i, i, i, i]
        lib.oled_circle.argtypes = [p, i, i, i]
        lib.oled_disc.argtypes = [p, i, i, i, i]
        lib.oled_shift_row.argtypes = [p, i, i]
        lib.ssd1325_frame.argtypes = [p, i, p]

    def fb(self):
        return ctypes.create_string_buffer(OLED_W*OLED_H//8)

    def lit(self, fb):
        return {(x, y) for y in range(OLED_H) for x in range(OLED_W) if self.lib.oled_get(fb, x, y)}

    def test_font_file_is_current(self):
        script = COMMON/'tools/make_font.py'
        self.assertEqual(subprocess.run([sys.executable, script, '--check']).returncode, 0)

    def test_glyph_pixels(self):
        fb = self.fb()
        self.assertEqual(self.lib.oled_text(fb, 10, 20, b'1', 1), 16)
        art = '..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.'.split()
        want = {(10 + c, 20 + r) for r, row in enumerate(art) for c, ch in enumerate(row) if ch == '#'}
        self.assertEqual(self.lit(fb), want)

    def test_screen_glyphs_are_in_the_font(self):
        # The node's screens draw these: none may fall back to '?'.
        q = self.fb()
        self.lib.oled_text(q, 0, 0, b'?', 1)
        for ch in 'z#><:*|dbgoinptelcurk':
            fb = self.fb()
            self.lib.oled_text(fb, 0, 0, ch.encode(), 1)
            self.assertNotEqual(fb.raw, q.raw, ch)
            self.assertTrue(self.lit(fb), ch)

    def test_scale_and_unknown_characters(self):
        fb, ref = self.fb(), self.fb()
        self.assertEqual(self.lib.oled_text(fb, 0, 0, b'x~', 2), 24)     # neither is in the font
        self.lib.oled_text(ref, 0, 0, b'??', 2)
        self.assertEqual(fb.raw, ref.raw)
        self.assertEqual(len(self.lit(ref)), 2*4*len(self.lit_of(b'?')))  # each font pixel is 2 x 2

    def lit_of(self, text):
        fb = self.fb()
        self.lib.oled_text(fb, 0, 0, text, 1)
        return self.lit(fb)

    def test_off_screen_is_ignored(self):
        fb = self.fb()
        for x, y in ((-1, 0), (0, -1), (OLED_W, 0), (0, OLED_H), (10**6, 10**6)):
            self.lib.oled_set(fb, x, y, 1)
            self.assertEqual(self.lib.oled_get(fb, x, y), 0)
        self.assertEqual(fb.raw, bytes(len(fb.raw)))
        self.lib.oled_text(fb, 120, 60, b'888', 2)                       # clipped, not wrapped
        self.assertTrue(all(x >= 120 and y >= 60 for x, y in self.lit(fb)))

    def test_ssd1325_column_order(self):
        fb = self.fb()
        for x, y in ((0, 0), (1, 5), (126, 63), (127, 63)):
            self.lib.oled_set(fb, x, y, 1)
        col = ctypes.create_string_buffer(OLED_H)
        self.lib.ssd1325_column(fb, 0, col)
        self.assertEqual(col.raw[0], 0xF0)          # x = 0: the left pixel, high nibble
        self.assertEqual(col.raw[5], 0x0F)          # x = 1: the right pixel, low nibble
        self.assertEqual(sum(1 for b in col.raw if b), 2)
        self.lib.ssd1325_column(fb, 63, col)
        self.assertEqual(col.raw[63], 0xFF)
        self.assertEqual(sum(1 for b in col.raw if b), 1)

    def test_rotate180(self):
        fb, out = self.fb(), self.fb()
        self.lib.oled_set(fb, 0, 0, 1)
        self.lib.oled_set(fb, 10, 3, 1)
        self.lib.oled_rotate180(out, fb)
        self.assertEqual(self.lit(out), {(OLED_W - 1, OLED_H - 1), (OLED_W - 11, OLED_H - 4)})

    def test_line_endpoints_and_dash(self):
        fb = self.fb()
        self.lib.oled_line(fb, 0, 0, 9, 0, 0)
        self.assertEqual(self.lit(fb), {(x, 0) for x in range(10)})
        fb = self.fb()
        self.lib.oled_line(fb, 0, 0, 9, 0, 2)
        self.assertEqual(self.lit(fb), {(x, 0) for x in (0, 1, 4, 5, 8, 9)})
        fb = self.fb()                                   # either direction, diagonal and vertical
        self.lib.oled_line(fb, 5, 5, 0, 0, 0)
        self.assertEqual(self.lit(fb), {(i, i) for i in range(6)})
        fb = self.fb()
        self.lib.oled_line(fb, 3, 7, 3, 2, 0)
        self.assertEqual(self.lit(fb), {(3, y) for y in range(2, 8)})

    def test_box_is_outline_only(self):
        fb = self.fb()
        self.lib.oled_box(fb, 2, 2, 5, 4)
        self.assertEqual(len(self.lit(fb)), 14)
        self.assertEqual(self.lib.oled_get(fb, 4, 3), 0)
        for x, y in ((2, 2), (6, 2), (2, 5), (6, 5), (4, 2), (4, 5), (2, 3), (6, 4)):
            self.assertEqual(self.lib.oled_get(fb, x, y), 1, (x, y))

    def test_fill_and_clear(self):
        fb = self.fb()
        self.lib.oled_fill(fb, 1, 1, 3, 2, 1)
        self.assertEqual(self.lit(fb), {(x, y) for x in range(1, 4) for y in (1, 2)})
        self.lib.oled_fill(fb, 2, 1, 1, 2, 0)
        self.assertEqual(self.lit(fb), {(x, y) for x in (1, 3) for y in (1, 2)})

    def test_invert_twice_is_identity(self):
        fb = self.fb()
        self.lib.oled_text(fb, 3, 3, b'AB1', 1)
        before = fb.raw
        self.lib.oled_invert(fb, 2, 2, 20, 10)
        self.assertNotEqual(fb.raw, before)
        self.assertEqual(self.lib.oled_get(fb, 2, 2), 1)       # a dark pixel lit
        self.lib.oled_invert(fb, 2, 2, 20, 10)
        self.assertEqual(fb.raw, before)

    def test_dotgrid_spacing(self):
        fb = self.fb()
        self.lib.oled_dotgrid(fb, 0, 0, 32, 16, 16)
        for x, y in ((0, 0), (16, 0), (0, 2), (2, 0)):
            self.assertEqual(self.lib.oled_get(fb, x, y), 1, (x, y))
        self.assertEqual(self.lib.oled_get(fb, 1, 1), 0)

    def test_circle_and_disc(self):
        fb = self.fb()
        self.lib.oled_circle(fb, 20, 20, 5)
        lit = self.lit(fb)
        for p in ((25, 20), (15, 20), (20, 25), (20, 15)):
            self.assertIn(p, lit)
        self.assertNotIn((20, 20), lit)
        fb = self.fb()
        self.lib.oled_disc(fb, 20, 20, 5, 1)
        disc = self.lit(fb)
        self.assertTrue(lit <= disc)
        self.assertIn((20, 20), disc)
        self.lib.oled_disc(fb, 20, 20, 5, 0)
        self.assertEqual(self.lit(fb), set())

    def test_shift_row(self):
        fb = self.fb()
        self.lib.oled_set(fb, 10, 5, 1)
        self.lib.oled_set(fb, 10, 4, 1)
        self.lib.oled_shift_row(fb, 5, 4)
        self.assertEqual(self.lit(fb), {(14, 5), (10, 4)})
        self.lib.oled_shift_row(fb, 5, -9)
        self.assertEqual(self.lit(fb), {(5, 5), (10, 4)})
        self.lib.oled_shift_row(fb, 5, OLED_W)                # shifted off the screen
        self.assertEqual(self.lit(fb), {(10, 4)})

    def test_ssd1325_frame_matches_columns(self):
        fb = self.fb()
        self.lib.oled_text(fb, 1, 1, b'TX 0123', 2)
        self.lib.oled_set(fb, 127, 63, 1)
        out = ctypes.create_string_buffer(4096)
        self.lib.ssd1325_frame(fb, 0, out)
        col = ctypes.create_string_buffer(OLED_H)
        for cp in range(OLED_W//2):
            self.lib.ssd1325_column(fb, cp, col)
            self.assertEqual(out.raw[cp*64:(cp + 1)*64], col.raw, cp)

    def test_ssd1325_frame_rotated(self):
        fb, rot = self.fb(), self.fb()
        self.lib.oled_set(fb, 0, 0, 1)
        self.lib.oled_rotate180(rot, fb)
        out, want = ctypes.create_string_buffer(4096), ctypes.create_string_buffer(OLED_H)
        self.lib.ssd1325_frame(fb, 1, out)
        self.lib.ssd1325_column(rot, 63, want)              # (127, 63) is the right pixel of the last pair
        self.assertEqual(out.raw[63*64:], want.raw)
        self.assertEqual(want.raw[63], 0x0F)
        self.assertEqual(sum(1 for b in out.raw if b), 1)


if __name__ == '__main__':
    unittest.main()
