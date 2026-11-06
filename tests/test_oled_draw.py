"""The shared OLED library (firmware/common/oled_draw.c, oled_font.c, oled_row.c, font5x7.c): the drawing surface in the
SSD1325's pixel order, drawing primitives, bitmaps, fonts and text, and the text row builder. Pure C, compiled for the host; the bench tool and the node both link it. What
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
class OledDraw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = lib = host_library(cls, 'oled_draw', '-I', COMMON, COMMON/'oled_draw.c', COMMON/'oled_font.c',
                                          COMMON/'font5x7.c')
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
        lib.oled_disc_r2.argtypes = [p, i, i, i, i, i]
        lib.oled_glyph.argtypes = [p, ctypes.c_char]
        lib.oled_draw_text.argtypes = [p, i, i, ctypes.c_char_p, p, p]
        lib.oled_text_w.argtypes = [ctypes.c_char_p, p, p]
        lib.oled_blit.argtypes = [p, i, i, p]

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

    def test_disc_r2(self):
        # oled_disc is r2 = r^2 + r; a smaller r2 leaves the four tips off (HACK's eye: r 4, r2 16).
        a, b = self.fb(), self.fb()
        self.lib.oled_disc(a, 20, 20, 4, 1)
        self.lib.oled_disc_r2(b, 20, 20, 4, 20, 1)
        self.assertEqual(a.raw, b.raw)
        c = self.fb()
        self.lib.oled_disc_r2(c, 20, 20, 4, 16, 1)
        self.assertEqual(self.lit(c), {(20 + i, 20 + j) for i in range(-4, 5) for j in range(-4, 5) if i*i + j*j <= 16})

    def sym(self, name):
        return ctypes.addressof(ctypes.c_char.in_dll(self.lib, name))

    def test_one_text_renderer(self):
        # oled_text is oled_draw_text with font5x7 at x1 or x2; the pen includes the gap, the width does not.
        a, b = self.fb(), self.fb()
        self.assertEqual(self.lib.oled_text(a, 3, 4, b'Hi?', 2), 3 + 36)
        self.assertEqual(self.lib.oled_draw_text(b, 3, 4, b'Hi?', self.sym('font5x7'), self.sym('oled_x2')), 3 + 36)
        self.assertEqual(a.raw, b.raw)
        self.assertEqual(self.lib.oled_text_w(b'Hi?', self.sym('font5x7'), self.sym('oled_x1')), 17)
        self.assertEqual(self.lib.oled_text_w(b'', self.sym('font5x7'), self.sym('oled_x1')), 0)
        self.assertEqual(self.lib.oled_glyph(self.sym('font5x7'), b'`'), self.lib.oled_glyph(self.sym('font5x7'), b'?'))

    def test_blit_leftmost_is_bit_w_minus_1(self):
        rows = (ctypes.c_uint16 * 2)(0b100000001, 0b010000000)   # 9 wide

        class Bits(ctypes.Structure):
            _fields_ = [('w', ctypes.c_uint8), ('h', ctypes.c_uint8), ('bits', ctypes.c_uint8), ('rows', ctypes.c_void_p)]
        fb = self.fb()
        self.lib.oled_blit(fb, 10, 20, ctypes.byref(Bits(9, 2, 16, ctypes.addressof(rows))))
        self.assertEqual(self.lit(fb), {(10, 20), (18, 20), (11, 21)})

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

    def test_level_nibbles(self):
        # Send order: column pair, then row; the left pixel of a pair in the high nibble. Each level sets its
        # own nibble only; a level past 15 is 15; off the screen is ignored.
        fb = self.fb()
        self.lib.oled_level(fb, 4, 3, 9)
        self.lib.oled_level(fb, 5, 3, 6)
        self.lib.oled_level(fb, 127, 63, 99)
        for x, y in ((-1, 0), (128, 0), (0, -1), (0, 64)):
            self.lib.oled_level(fb, x, y, 15)
        self.assertEqual((fb.raw[2*64 + 3], fb.raw[63*64 + 63]), (0x96, 0x0F))
        self.assertEqual(sum(1 for b in fb.raw if b), 2)
        self.lib.oled_level(fb, 4, 3, 0)
        self.assertEqual(fb.raw[2*64 + 3], 0x06)

    def test_level_rotated(self):
        # Turned half a turn: (0, 0) is stored as (127, 63), the right pixel of the last pair.
        fb = self.fb(rot180=1)
        self.lib.oled_level(fb, 0, 0, 7)
        self.lib.oled_level(fb, 1, 0, 3)
        self.assertEqual(fb.raw[63*64 + 63], 0x37)
        self.assertEqual(sum(1 for b in fb.raw if b), 1)

    def test_a_turned_surface_is_the_picture_turned(self):
        # Anything drawn on a turned surface is, read back, what an unturned one shows, at the same levels.
        for ink in (15, 4):
            pics = [self.fb(rot, ink) for rot in (0, 1)]
            for pic in pics:
                self.lib.oled_text(pic, 1, 1, b'TX 0123 ~', 2)
                self.lib.oled_circle(pic, 90, 40, 20)
                self.lib.oled_set(pic, 127, 63, 1)
            self.assertEqual(self.levels(pics[1]), self.levels(pics[0]))
            self.assertEqual(set(self.levels(pics[0]).values()), {ink})

    def levels(self, fb):
        return {(x, y): self.lib.oled_get(fb, x, y) for y in range(OLED_H) for x in range(OLED_W) if self.lib.oled_get(fb, x, y)}



class Row(ctypes.Structure):
    _fields_ = [('s', ctypes.c_char * 24)]   # oled_row (oled_row.h)


FORM = ctypes.CFUNCTYPE(None, ctypes.POINTER(Row), ctypes.c_void_p, ctypes.c_uint)


@needs_cc
class OledRow(unittest.TestCase):
    """The text row builder (firmware/common/oled_row.c), shared by the node's screens and the bench tool."""
    @classmethod
    def setUpClass(cls):
        cls.lib = lib = host_library(cls, 'oled_row', '-I', COMMON, COMMON/'oled_row.c')
        r, s, u = ctypes.POINTER(Row), ctypes.c_char_p, ctypes.c_uint
        lib.oled_put.argtypes = [r, s]
        lib.oled_put_dec.argtypes = [r, ctypes.c_int32, u, u, u]
        lib.oled_put_uint.argtypes = [r, ctypes.c_uint32]
        lib.oled_put_hex2.argtypes = [r, ctypes.c_uint8]
        lib.oled_pad_to.argtypes = [r, u]
        lib.oled_put_lr.argtypes = [r, s, s, u]
        lib.oled_put_lcr.argtypes = [r, s, s, s, u]
        lib.oled_fit.argtypes = [r, FORM, ctypes.c_void_p, u, u]
        lib.oled_fit.restype = u

    def dec(self, v, i, o, plus=0):
        r = Row()
        self.lib.oled_put_dec(r, v, i, o, plus)
        return r.s.decode()

    def test_put_never_overflows(self):
        r = Row()
        self.lib.oled_put(r, b'x' * 40)
        self.assertEqual(r.s, b'x' * 23)
        self.lib.oled_pad_to(r, 30)
        self.assertEqual(len(r.s), 23)

    def test_dec(self):
        self.assertEqual([self.dec(1234, 2, 1), self.dec(-1235, 2, 1), self.dec(-4, 2, 1), self.dec(0, 2, 2, 1),
                          self.dec(-4, 2, 1, 1), self.dec(5, 1, 0), self.dec(7, 0, 0, 1)],
                         ['12.3', '-12.4', '0.0', '+0.00', '+0.0', '1', '+7'])
        self.assertEqual([self.dec(-2**31, 0, 0), self.dec(2**31 - 1, 6, 6), self.dec(-2**31, 6, 2)],
                         ['-2147483648', '2147.483647', '-2147.48'])
        r = Row()
        self.lib.oled_put_uint(r, 2**32 - 1)
        self.assertEqual(r.s, b'4294967295')
        r = Row()
        self.lib.oled_put_hex2(r, 0xA4)
        self.assertEqual(r.s, b'A4')

    def lr(self, left, right, cols=21, centre=None):
        r = Row(b'old')
        ok = (self.lib.oled_put_lr(r, left, right, cols) if centre is None
              else self.lib.oled_put_lcr(r, left, centre, right, cols))
        return ok, r.s.decode()

    def test_left_right_and_centre(self):
        self.assertEqual(self.lr(b'RAIN', b'0.56 mm'), (1, 'RAIN' + ' ' * 10 + '0.56 mm'))
        self.assertEqual(self.lr(b'x' * 10, b'y' * 10), (1, 'x' * 10 + ' ' + 'y' * 10))
        self.assertEqual(self.lr(b'x' * 11, b'y' * 10), (0, 'old'))                     # untouched
        self.assertEqual(self.lr(b'-60m', b'now', centre=b'16/m'), (1, '-60m    16/m      now'))
        self.assertEqual(self.lr(b'-3h', b'now', centre=b'c' * 13), (1, '-3h ' + 'c' * 13 + ' now'))
        self.assertEqual(self.lr(b'-3h', b'now', centre=b'c' * 14), (1, '-3h' + ' ' * 15 + 'now'))   # no space: left out

    def test_fit_takes_the_first_form_that_fits(self):
        built = []

        @FORM
        def build(r, ctx, form):
            built.append(form)
            self.lib.oled_put(r, b'x' * (25 - 3 * form))
        r = Row(b'junk')
        self.assertEqual(self.lib.oled_fit(r, build, None, 4, 18), 3)   # 25, 22, 19 too long; 16 fits
        self.assertEqual((built, r.s), ([0, 1, 2, 3], b'x' * 16))
        built.clear()
        self.assertEqual(self.lib.oled_fit(r, build, None, 2, 10), 1)   # none fits: the last, as built
        self.assertEqual((built, len(r.s)), ([0, 1], 22))

if __name__ == '__main__':
    unittest.main()
