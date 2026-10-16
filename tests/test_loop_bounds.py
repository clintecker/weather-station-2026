"""tools/loop_bounds.py: every firmware loop is a counting loop or says what bounds it (Power of Ten rule 2)."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
try:
    from toolchain import ROOT, load_tool          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, load_tool    # python -m unittest tests.<module>

loop_bounds = load_tool('loop_bounds')


class LoopBounds(unittest.TestCase):
    def flagged(self, code):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'t.c'
            path.write_text(code)
            return [msg.split(': ', 1)[1] for msg in loop_bounds.check(path)]

    def test_counting_loops_need_nothing(self):
        for head in ('unsigned i = 0; i < n; i++', 'uint32_t s = 0; s < X && n < max; s++', 'int i=0;i<16;i++,p+=2',
                     'uint32_t k = 1; k <= WS_JOURNAL_PAGES; k++', 'uint32_t *p = lo; p < stop; p++',
                     'unsigned k = 0; k < EV_COUNT && batch; k++, bit <<= 1'):
            self.assertEqual(self.flagged(f'void f(void) {{ for ({head}) g(); }}\n'), [], head)

    def test_a_counting_header_that_cannot_end_needs_a_bound_comment(self):
        # Review 2026-10-15: wrong step direction, a zero or variable step, a literal bound past a
        # narrow counter, and a body that moves the loop variable are not counting loops.
        for code in ('for (unsigned i = 0; i < n; i--) g();', 'for (unsigned i = 10; i > 0; i++) g();',
                     'for (uint8_t i = 0; i < 300; i++) g();', 'for (unsigned i = 0; i < n; i += 0) g();',
                     'for (unsigned i = 0; i < n; i += k) g();', 'for (unsigned i = 0; i < n; i++) { i = 0; }',
                     'for (unsigned i = 0; i < n; i++) { g(i--); }', 'for (unsigned i = 0; i < n; i++) i -= 1;'):
            self.assertEqual(len(self.flagged(f'void f(void) {{ {code} }}\n')), 1, code)
        for code in ('for (unsigned i = 0; i < n; i += 2) g(i);', 'for (uint8_t i = 0; i < 255; i++) a[i] = b == i;',
                     'for (unsigned i = n; i > 0; i--) g(i);', 'for (unsigned i = 0; i < n; i += STEP) g(i + 1);'):
            self.assertEqual(self.flagged(f'void f(void) {{ {code} }}\n'), [], code)

    def test_other_loops_need_a_bound_comment(self):
        for code in ('while (n--) g();', 'do { g(); } while (v);', 'for (;;) { }', 'for (i = n; i-- > 0;) g();',
                     'for (unsigned i = 0; j < n; i++) g();', 'for (unsigned i = 0; i < n; j++) g();'):
            self.assertEqual(len(self.flagged(f'void f(void) {{\n {code}\n}}\n')), 1, code)
            self.assertEqual(self.flagged(f'void f(void) {{\n {code}   /* bound: n */\n}}\n'), [], code)
            self.assertEqual(self.flagged(f'void f(void) {{\n /* bound: n */\n {code}\n}}\n'), [], code)

    def test_comments_strings_and_do_while_0_are_not_loops(self):
        code = ('/* wait for the bus,\n   while it is held for\n   ever */\n'
                'void f(void) { puts("while (1)"); }\n#define M(x) do { x; } while (0)\n')
        self.assertEqual(self.flagged(code), [])

    def test_the_firmware_passes(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop_bounds.main([]), 0, out.getvalue())


if __name__ == '__main__':
    unittest.main()
