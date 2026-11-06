"""The shared OLED library (firmware/common/oled_draw.c, font5x7.c): the drawing surface in the SSD1325's pixel
order, text and drawing primitives. Pure C, compiled for the host; the bench tool and the node both link it. What
the panel shows is checked by eye on the bench."""
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


class SurfStruct(ctypes.Structure):
    _fields_ = [('px', ctypes.c_void_p), ('rot180', ctypes.c_uint8), ('ink', ctypes.c_uint8)]   # oled_surf


class Surf:
    """An oled_surf over a cleared frame of its own; passed to the library as a pointer to it. raw: the frame."""
    def __init__(self, rot180=0, ink=15):
        self.buf = ctypes.create_string_buffer(OLED_W*OLED_H//2)
        self.s = SurfStruct(ctypes.addressof(self.buf), rot180, ink)
        self._as_parameter_ = ctypes.byref(self.s)

    @property
    def raw(self):
        return self.buf.raw


@needs_cc
class OledFb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = lib = host_library(cls, 'oled_draw', '-I', COMMON, COMMON/'oled_draw.c', COMMON/'font5x7.c')
        i, p, u = ctypes.c_int, ctypes.c_void_p, ctypes.c_uint
        lib.oled_text.argtypes = [p, i, i, ctypes.c_char_p, i]
        lib.oled_set.argtypes = [p, i, i, i]
        lib.oled_get.argtypes = [p, i, i]
        lib.oled_get.restype = u
        lib.oled_level.argtypes = [p, i, i, u]
        lib.oled_line.argtypes = [p, i, i, i, i, u]
        lib.oled_box.argtypes = [p, i, i, i, i]
        lib.oled_fill.argtypes = [p, i, i, i, i, i]
        lib.oled_dotgrid.argtypes = [p, i, i, i, i, i]
        lib.oled_invert.argtypes = [p, i, i, i, i]
        lib.oled_circle.argtypes = [p, i, i, i]
        lib.oled_disc.argtypes = [p, i, i, i, i]
        lib.oled_shift_row.argtypes = [p, i, i]
        lib.ssd1325_put4.argtypes = [p, i, i, u, i]
        lib.ssd1325_blit4.argtypes = [p, i, i, ctypes.c_char_p, i, i, u, i]
        lib.ssd1325_text4.argtypes = [p, i, i, ctypes.c_char_p, u, i]

    def fb(self, rot180=0, ink=15):
        return Surf(rot180, ink)

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
        for ch in "z#><:*|dbgoinptelcurkw()fjqvxy,!'":
            fb = self.fb()
            self.lib.oled_text(fb, 0, 0, ch.encode(), 1)
            self.assertNotEqual(fb.raw, q.raw, ch)
            self.assertTrue(self.lit(fb), ch)

    def test_scale_and_unknown_characters(self):
        fb, ref = self.fb(), self.fb()
        self.assertEqual(self.lib.oled_text(fb, 0, 0, b'`~', 2), 24)     # neither is in the font
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
            self.assertEqual(self.lib.oled_get(fb, x, y), 15, (x, y))

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
        self.assertEqual(self.lib.oled_get(fb, 2, 2), 15)      # a dark pixel lit, at the ink
        self.lib.oled_invert(fb, 2, 2, 20, 10)
        self.assertEqual(fb.raw, before)

    def test_dotgrid_spacing(self):
        fb = self.fb()
        self.lib.oled_dotgrid(fb, 0, 0, 32, 16, 16)
        for x, y in ((0, 0), (16, 0), (0, 2), (2, 0)):
            self.assertEqual(self.lib.oled_get(fb, x, y), 15, (x, y))
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

    def test_send_order(self):
        # Column pair, then row; the left pixel of a pair in the high nibble, a lit pixel at the ink.
        fb = self.fb()
        for x, y in ((0, 0), (1, 5), (126, 63), (127, 63)):
            self.lib.oled_set(fb, x, y, 1)
        self.assertEqual((fb.raw[0], fb.raw[5], fb.raw[63*64 + 63]), (0xF0, 0x0F, 0xFF))
        self.assertEqual(sum(1 for b in fb.raw if b), 3)

    def test_rotated(self):
        # Turned half a turn: (0, 0) is stored as (127, 63), the right pixel of the last pair; (10, 3) as (117, 60).
        # Drawing and reading back are in logical coordinates either way.
        fb = self.fb(rot180=1)
        self.lib.oled_set(fb, 0, 0, 1)
        self.lib.oled_set(fb, 10, 3, 1)
        self.assertEqual((fb.raw[63*64 + 63], fb.raw[58*64 + 60]), (0x0F, 0x0F))
        self.assertEqual(sum(1 for b in fb.raw if b), 2)
        self.assertEqual(self.lit(fb), {(0, 0), (10, 3)})

    def test_levels_and_ink(self):
        # oled_level sets one nibble (more than 15 is 15, off the screen ignored); oled_set writes the ink or 0;
        # invert takes a lit pixel dark and a dark one to the ink; a shifted row keeps its levels.
        fb = self.fb(ink=6)
        self.lib.oled_level(fb, 4, 3, 9)
        self.lib.oled_set(fb, 5, 3, 1)
        self.lib.oled_level(fb, 127, 63, 99)
        self.lib.oled_level(fb, -1, 0, 15)
        self.assertEqual((fb.raw[2*64 + 3], fb.raw[63*64 + 63], self.lib.oled_get(fb, 4, 3)), (0x96, 0x0F, 9))
        self.assertEqual(sum(1 for b in fb.raw if b), 2)
        self.lib.oled_invert(fb, 4, 3, 3, 1)
        self.assertEqual([self.lib.oled_get(fb, x, 3) for x in (4, 5, 6)], [0, 0, 6])
        self.lib.oled_level(fb, 4, 3, 9)
        self.lib.oled_shift_row(fb, 3, 1)
        self.assertEqual([self.lib.oled_get(fb, x, 3) for x in (4, 5, 6, 7)], [0, 9, 0, 6])

    def frame(self):
        return ctypes.create_string_buffer(4096)

    def test_put4_nibbles(self):
        # Send order: column pair, then row; the left pixel of a pair in the high nibble. Each put sets its
        # own nibble only; a level past 15 is 15; off the screen is ignored.
        out = self.frame()
        self.lib.ssd1325_put4(out, 4, 3, 9, 0)
        self.lib.ssd1325_put4(out, 5, 3, 6, 0)
        self.lib.ssd1325_put4(out, 127, 63, 99, 0)
        for x, y in ((-1, 0), (128, 0), (0, -1), (0, 64)):
            self.lib.ssd1325_put4(out, x, y, 15, 0)
        self.assertEqual((out.raw[2*64 + 3], out.raw[63*64 + 63]), (0x96, 0x0F))
        self.assertEqual(sum(1 for b in out.raw if b), 2)
        self.lib.ssd1325_put4(out, 4, 3, 0, 0)
        self.assertEqual(out.raw[2*64 + 3], 0x06)

    def test_put4_rotated(self):
        # Turned half a turn: (0, 0) is sent as (127, 63), the right pixel of the last pair, as a turned surface holds it.
        out = self.frame()
        self.lib.ssd1325_put4(out, 0, 0, 7, 1)
        self.lib.ssd1325_put4(out, 1, 0, 3, 1)
        self.assertEqual(out.raw[63*64 + 63], 0x37)
        self.assertEqual(sum(1 for b in out.raw if b), 1)

    def test_put4_matches_the_surface(self):
        # A 1-bit picture put pixel by pixel at full level is the frame a surface holds, either way up.
        pic = self.fb()
        self.lib.oled_text(pic, 1, 1, b'TX 0123', 2)
        self.lib.oled_circle(pic, 90, 40, 20)
        self.lib.oled_set(pic, 127, 63, 1)
        for rot in (0, 1):
            want, got = self.fb(rot), self.frame()
            for x, y in self.lit(pic):
                self.lib.oled_set(want, x, y, 1)
                self.lib.ssd1325_put4(got, x, y, 15, rot)
            self.assertEqual(got.raw, want.raw, rot)

    def test_blit4_and_text4(self):
        # blit4 puts a bitmap's lit pixels at its level (bit w - 1 the leftmost column), clipped; text4 is
        # oled_text's pixels, '?' for a character the font lacks.
        out = self.frame()
        self.lib.ssd1325_blit4(out, 126, 0, bytes([0b101, 0b010]), 3, 2, 5, 0)
        self.assertEqual(self.levels(out), {(126, 0): 5, (127, 1): 5})
        fb, out = self.fb(), self.frame()
        self.lib.oled_text(fb, 3, 50, b'SPEED x2 ~', 1)
        self.lib.ssd1325_text4(out, 3, 50, b'SPEED x2 ~', 4, 0)
        self.assertEqual(self.levels(out), dict.fromkeys(self.lit(fb), 4))

    @staticmethod
    def levels(out):
        got = {}
        for i, b in enumerate(out.raw):
            cp, y = divmod(i, OLED_H)
            for x, v in ((2*cp, b >> 4), (2*cp + 1, b & 15)):
                if v:
                    got[(x, y)] = v
        return got


if __name__ == '__main__':
    unittest.main()
