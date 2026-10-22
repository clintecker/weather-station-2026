"""tools/tangle.py: literate sources (*.lit.md) and the generated C committed beside them.

The check CI relies on: every committed root (firmware/stage0-node/App/node_store.c) is exactly what
its document tangles to, so the document is the source of truth and nobody edits the C by hand.
The rest pins the tangler's rules (references, joined definitions, errors) and the two outputs
that are not committed: the #line build for debugging and the woven HTML page."""
import re
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path
try:
    from toolchain import CC_STRICT, ROOT, load_tool, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, load_tool, needs_cc    # python -m unittest tests.<module>

tangle = load_tool('tangle')
F = '```'


class Committed(unittest.TestCase):
    def test_every_generated_file_matches_its_document(self):
        docs = tangle.all_docs()
        self.assertIn(ROOT/'firmware/stage0-node/App/node_store.lit.md', docs)
        for doc in docs:
            for path, text in tangle.tangle(doc).items():
                self.assertTrue(path.exists(), f'{path} is not committed; run tools/tangle.py {doc}')
                self.assertEqual(path.read_text(encoding='utf-8'), text, f'{path} differs from {doc}: edit the document and '
                                 f'run tools/tangle.py {doc.relative_to(ROOT)}')
                self.assertTrue(text.startswith(('/* GENERATED from ', '# GENERATED from ')), 'the banner says where the file comes from')


class Rules(unittest.TestCase):
    def tangled(self, doc, lines=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'t.lit.md'
            path.write_text(doc, encoding='utf-8')
            return {p.name: t.split('\n', 2)[2] for p, t in tangle.tangle(path, lines).items()}

    def test_references_are_indented_and_definitions_joined_in_document_order(self):
        doc = (f'Prose.\n\n{F}c {{#out.c}}\nint f(void) {{\n <<body>>\n}}\n{F}\n\n'
               f'{F}c {{#body}}\nint x = 1 << 2;\n{F}\n\nMore.\n\n{F}c {{#body}}\nreturn x;\n{F}\n'
               f'{F}text\nnot code\n{F}\n')
        self.assertEqual(self.tangled(doc), {'out.c': 'int f(void) {\n int x = 1 << 2;\n return x;\n}\n'})

    def test_errors(self):
        cases = {'never defined': f'{F}c {{#a.c}}\n<<missing>>\n{F}\n',
                 'never used': f'{F}c {{#a.c}}\nx\n{F}\n{F}c {{#spare}}\ny\n{F}\n',
                 'used 2 times': f'{F}c {{#a.c}}\n<<b>>\n<<b>>\n{F}\n{F}c {{#b}}\ny\n{F}\n',
                 'not reachable': f'{F}c {{#a.c}}\nx\n{F}\n{F}c {{#b}}\n<<c>>\n{F}\n{F}c {{#c}}\n<<b>>\n{F}\n',
                 'never closed': f'{F}c {{#a.c}}\nx\n',
                 'no root': f'{F}c\nx\n{F}\n'}
        for message, doc in cases.items():
            with self.assertRaisesRegex(tangle.LitError, message):
                self.tangled(doc)

    def test_mermaid_blocks_become_diagrams_and_load_mermaid_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'t.lit.md'
            path.write_text(f'# T\n\n{F}mermaid\nstateDiagram-v2\n  a --> b\n{F}\n\n{F}c {{#t.c}}\nint x;\n{F}\n', encoding='utf-8')
            page = tangle.Weaver(path).page()
        self.assertIn('<pre class="mermaid">stateDiagram-v2\n  a --&gt; b</pre>', page)
        self.assertEqual(page.count('mermaid@'), 1)

    def test_a_python_root_gets_a_python_banner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'t.lit.md'
            path.write_text(f'{F}python {{#out.py}}\nx = 1 << 2\n{F}\n', encoding='utf-8')
            (text,) = tangle.tangle(path).values()
        first, second, body = text.split('\n', 2)
        self.assertTrue(first.startswith('# GENERATED from t.lit.md') and second.startswith('# tools/tangle.py'))
        self.assertEqual(body, 'x = 1 << 2\n')

    def test_line_directives_point_into_the_document(self):
        doc = f'# T\n\n{F}c {{#a.c}}\n<<b>>\nint y;\n{F}\n\n{F}c {{#b}}\nint x;\n{F}\n'
        out = self.tangled(doc, lines=True)['a.c'].splitlines()
        self.assertEqual([line.split(' "')[0] for line in out], ['#line 9', 'int x;', '#line 5', 'int y;'])

    def test_check_reports_a_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp)/'t.lit.md'
            doc.write_text(f'{F}c {{#t.c}}\nint x;\n{F}\n', encoding='utf-8')
            (Path(tmp)/'t.c').write_text('int x; /* edited by hand */\n', encoding='utf-8')
            with open(Path(tmp)/'log', 'w') as log, unittest.mock.patch('sys.stdout', log), \
                 unittest.mock.patch('sys.stderr', log):
                self.assertEqual(tangle.main(['--check', str(doc)]), 1)
                self.assertEqual(tangle.main([str(doc)]), 0)
                self.assertEqual(tangle.main(['--check', str(doc)]), 0)


class Woven(unittest.TestCase):
    def test_page_is_standalone_with_cross_references(self):
        page = tangle.Weaver(ROOT/'firmware/stage0-node/App/node_store.lit.md').page()
        # The only script is the pinned Mermaid module, for the diagrams; nothing else loads from outside.
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', page, re.S)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(re.findall(r'https://[^\'"]+', scripts[0]),
                         ['https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs'])
        self.assertNotRegex(page, r'<link\b|src="http', 'no other external assets')
        self.assertIn('id="chunk-journal-append"', page)
        self.assertIn('Used in <a class="ref" href="#chunk-node-store-c">', page)
        self.assertIn('<table>', page)


@needs_cc
class LineBuild(unittest.TestCase):
    def test_the_line_directive_build_compiles(self):
        """The #line build is for a debugger only (the committed .c has none: WS_CHECK sites keep 10
        bits of line, and the document is longer than 1024 lines), but it must stay valid C."""
        app = ROOT/'firmware/stage0-node/App'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'node_store_lines.c'
            self.assertEqual(tangle.main(['--lines', '-o', str(out), str(app/'node_store.lit.md')]), 0)
            self.assertIn('#line ', out.read_text(encoding='utf-8'))
            subprocess.run([*CC_STRICT, '-fsyntax-only', '-I', str(app), '-I', str(ROOT/'firmware/common'),
                            '-I', str(ROOT/'firmware'), str(out)], check=True)


if __name__ == '__main__':
    unittest.main()
