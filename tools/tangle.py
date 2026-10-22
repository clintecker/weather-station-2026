#!/usr/bin/env python3
"""Literate sources (noweb-style, in Markdown): tangle the code out, check it, weave a page.

A literate source is a Markdown file, <name>.lit.md, that is the source of truth for one or more
generated files. Its fenced code blocks with a chunk name are the code:

    ```c {#journal-append}
    int store_journal_append(...) {
     <<append-guards>>
     ...
    }
    ```

A line holding only <<name>> (any indentation) is replaced by the chunk of that name, with the
line's indentation put in front of every line of it. A name defined more than once is one chunk,
its definitions joined in document order. A chunk whose name has a dot in it (node_store.c) is a
root: it is written to that path, relative to the .lit.md, under a GENERATED banner. Every other
chunk must be used exactly once; an undefined, unused or recursive chunk is an error. Code blocks
without a name ({#...}) are only shown (diagrams, examples). <<name>> in prose links to the chunk.

    tools/tangle.py DOC.lit.md ...          write the roots (only files whose text changed)
    tools/tangle.py --check [DOC ...]       exit 1 if a committed root differs from its tangle
                                            (no DOC: every *.lit.md under firmware/)
    tools/tangle.py --lines -o OUT DOC      the root with #line directives into the .lit.md, for a
                                            debug build only (see the note below)
    tools/tangle.py --weave OUT.html DOC    a standalone HTML page (inline CSS; the one external asset
                                            is the pinned Mermaid module, for pages with diagrams)

#line: the committed .c carries none. WS_CHECK sites are (file id << 10 | __LINE__) and keep only
10 bits of line (firmware/common/ws_check.h, tests/test_check.py), and a document runs past 1024
lines; tools/blocking_report.py reads call-site lines from GCC's .ci files back out of the source
file they name; lizard, cppcheck and jscpd judge the .c. So the .c is plain C, its line numbers
are its own, and --lines exists for stepping through the document in a debugger.
Python standard library only.
"""
import argparse
import difflib
import html
import keyword
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r'^(`{3,})[ \t]*([\w+-]*)[ \t]*(?:\{#([^}\s]+)\})?[ \t]*$')
REF = re.compile(r'^([ \t]*)<<([^<>\s]+)>>[ \t]*$')


class LitError(Exception):
    pass


def parse(text):
    """Blocks of the document, in order: ('prose', lines, first_line) and
    ('code', lang, name or None, lines, first_line), lines numbered from 1."""
    blocks, prose, lines = [], [], text.split('\n')
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            prose.append(lines[i])
            i += 1
            continue
        if prose:
            blocks.append(('prose', prose, i + 1 - len(prose)))
            prose = []
        start, ticks = i + 1, m[1]
        i += 1
        body = []
        while i < len(lines) and lines[i].rstrip() != ticks:
            body.append(lines[i])
            i += 1
        if i == len(lines):
            raise LitError(f'line {start}: code block never closed')
        blocks.append(('code', m[2], m[3], body, start + 1))
        i += 1
    if prose:
        blocks.append(('prose', prose, len(lines) - len(prose) + 1))
    return blocks


def chunks_of(blocks):
    """{name: [(lines, first_line), ...]} in document order."""
    chunks = {}
    for b in blocks:
        if b[0] == 'code' and b[2]:
            chunks.setdefault(b[2], []).append((b[3], b[4]))
    return chunks


def is_root(name):
    return '.' in name


def uses(chunks):
    """{name: [names of the chunks that reference it]}."""
    used = {}
    for name, defs in chunks.items():
        for lines, _ in defs:
            for line in lines:
                m = REF.match(line)
                if m:
                    used.setdefault(m[2], []).append(name)
    return used


def validate(chunks):
    used = uses(chunks)
    errors = [f'<<{n}>> is used but never defined' for n in sorted(used) if n not in chunks]
    for name in chunks:
        if is_root(name):
            if name in used:
                errors.append(f'root {name} is used as a chunk')
        elif name not in used:
            errors.append(f'chunk {name} is defined but never used')
        elif len(used[name]) > 1:
            errors.append(f'chunk {name} is used {len(used[name])} times (once only)')
    if not errors:     # used once each, but a cycle of chunks can still hang off no root
        seen, todo = set(), [n for n in chunks if is_root(n)]
        while todo:
            name = todo.pop()
            if name not in seen:
                seen.add(name)
                todo += [m[2] for lines, _ in chunks[name] for m in map(REF.match, lines) if m]
        errors = [f'chunk {n} is not reachable from a root (a cycle of chunks?)' for n in chunks if n not in seen]
    if errors:
        raise LitError('\n'.join(errors))


def expand(chunks, name, doc, lines_mode, stack=()):
    """The chunk's lines with every reference replaced, recursively."""
    if name in stack:
        raise LitError('recursive chunk: ' + ' -> '.join((*stack, name)))
    out = []
    for lines, first in chunks[name]:
        if lines_mode:
            out.append(f'#line {first} "{doc}"')
        for k, line in enumerate(lines):
            m = REF.match(line)
            if not m:
                out.append(line)
                continue
            for sub in expand(chunks, m[2], doc, lines_mode, (*stack, name)):
                out.append(m[1] + sub if sub and not sub.startswith('#line ') else sub)
            if lines_mode and k + 1 < len(lines):
                out.append(f'#line {first + k + 1} "{doc}"')
    return out


def banner(doc_path, root):
    """Two comment lines in the root's language: C (/* */) or Python (#)."""
    rel = doc_path.resolve().relative_to(ROOT) if doc_path.resolve().is_relative_to(ROOT) else doc_path
    first = f'GENERATED from {rel.name} by tools/tangle.py: do not edit. Edit the document, then run'
    second = f'tools/tangle.py {rel.as_posix()} (tests/test_tangle.py checks this file).'
    if str(root).endswith('.py'):
        return [f'# {first}', f'# {second}']
    return [f'/* {first}', f' * {second} */']


def tangle(doc_path, lines_mode=False):
    """{root path: text} for every root chunk of the document."""
    chunks = chunks_of(parse(doc_path.read_text(encoding='utf-8')))
    validate(chunks)
    roots = [n for n in chunks if is_root(n)]
    if not roots:
        raise LitError(f'{doc_path}: no root chunk (a name with a dot, e.g. {{#node_store.c}})')
    # --lines names the document by its absolute path, so a debugger finds it from any build directory.
    # Forward slashes: a backslash in a #line string is a C escape (C:\Users -> unknown escape '\U').
    name = doc_path.resolve().as_posix() if lines_mode else doc_path.name
    return {doc_path.parent/r: '\n'.join(banner(doc_path, r) + squeeze(expand(chunks, r, name, lines_mode))) + '\n'
            for r in roots}


def squeeze(lines):
    """Drops a #line directive that another follows at once (only the last one counts)."""
    return [line for k, line in enumerate(lines)
            if not (line.startswith('#line ') and k + 1 < len(lines) and lines[k + 1].startswith('#line '))]


def check(docs):
    stale = 0
    for doc in docs:
        for path, text in tangle(doc).items():
            have = path.read_text(encoding='utf-8') if path.exists() else ''
            if have != text:
                stale += 1
                diff = difflib.unified_diff(have.splitlines(), text.splitlines(), str(path), f'{doc} (tangled)', lineterm='', n=1)
                print('\n'.join(list(diff)[:40]))
                print(f'{path}: differs from {doc}; run tools/tangle.py {doc}', file=sys.stderr)
    return stale


# ---- weave ---------------------------------------------------------------------------------------

C_KEYWORDS = ('auto break case char const continue default do double else enum extern float for goto if '
              'inline int long register restrict return short signed sizeof static struct switch typedef '
              'union unsigned void volatile while _Static_assert _Bool').split()
C_TOKEN = re.compile(r'(?P<comment>/\*.*?\*/|//[^\n]*)|(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')'
                     r'|(?P<pre>^[ \t]*#[ \t]*\w+)|(?P<ref>\x00\d+\x00)'
                     r'|(?P<num>\b(?:0[xX][0-9a-fA-F]+|\d+)[uUlL]*\b)|(?P<word>\b[A-Za-z_]\w*\b)', re.S | re.M)


PY_KEYWORDS = tuple(keyword.kwlist) + ('self', 'cls')
PY_TOKEN = re.compile(r'(?P<comment>#[^\n]*)|(?P<string>(?:[rbfRBF]{1,2})?(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\''
                      r'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'))|(?P<pre>^[ \t]*@[\w.]+)|(?P<ref>\x00\d+\x00)'
                      r'|(?P<num>\b(?:0[xXoObB][0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:e-?\d+)?)\b)|(?P<word>\b[A-Za-z_]\w*\b)', re.M)
LANGS = {'c': (C_TOKEN, C_KEYWORDS), 'h': (C_TOKEN, C_KEYWORDS), 'python': (PY_TOKEN, PY_KEYWORDS),
         'py': (PY_TOKEN, PY_KEYWORDS)}


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'


class Weaver:
    def __init__(self, doc_path):
        self.doc = doc_path
        self.blocks = parse(doc_path.read_text(encoding='utf-8'))
        self.chunks = chunks_of(self.blocks)
        validate(self.chunks)
        self.used = uses(self.chunks)
        self.seen = {}
        self.mermaid = False   # a ```mermaid block makes the page load Mermaid

    def anchor(self, name, k=0):
        return 'chunk-' + slug(name) + (f'-{k + 1}' if k else '')

    def ref(self, name):
        return f'<a class="ref" href="#{self.anchor(name)}">⟨{html.escape(name)}⟩</a>'

    def inline(self, text):
        parts = re.split(r'(`[^`]+`)', text)
        out = []
        for p in parts:
            if p.startswith('`') and p.endswith('`') and len(p) > 1:
                out.append('<code>' + html.escape(p[1:-1]) + '</code>')
                continue
            s = html.escape(p, quote=False)
            s = re.sub(r'&lt;&lt;([^&\s]+)&gt;&gt;', lambda m: self.ref(html.unescape(m[1])), s)
            s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
            s = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', s)
            s = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', s)
            out.append(s)
        return ''.join(out)

    def highlight(self, lines, lang='c'):
        token, keywords = LANGS[lang]
        refs = []

        def stash(m):
            refs.append((m[1], m[2]))
            return f'{m[1]}\x00{len(refs) - 1}\x00'
        text = '\n'.join(REF.sub(stash, line) for line in lines)
        out, pos = [], 0
        for m in token.finditer(text):
            out.append(html.escape(text[pos:m.start()]))
            kind, tok = m.lastgroup, m[0]
            if kind == 'ref':
                out.append(self.ref(refs[int(tok.strip('\x00'))][1]))
            elif kind == 'word':
                cls = 'kw' if tok in keywords else 'ty' if tok.endswith('_t') else ''
                out.append(f'<span class="{cls}">{tok}</span>' if cls else tok)
            else:
                cls = {'comment': 'cm', 'string': 'st', 'pre': 'pp', 'num': 'nu'}[kind]
                out.append(f'<span class="{cls}">{html.escape(tok)}</span>')
            pos = m.end()
        out.append(html.escape(text[pos:]))
        return ''.join(out)

    def code(self, lang, name, lines, first):
        if not name and lang == 'mermaid':
            self.mermaid = True
            return f'<figure class="diagram"><pre class="mermaid">{html.escape(chr(10).join(lines))}</pre></figure>'
        if not name:
            return f'<pre class="plain">{html.escape(chr(10).join(lines))}</pre>'
        k = self.seen.get(name, 0)
        self.seen[name] = k + 1
        defs = len(self.chunks[name])
        sign = '+≡' if k else '≡'
        notes = []
        if is_root(name):
            notes.append(f'Root: tangled to <code>{html.escape(name)}</code>.')
        for parent in sorted(set(self.used.get(name, []))):
            notes.append(f'Used in {self.ref(parent)}.')
        if defs > 1:
            others = [f'<a href="#{self.anchor(name, j)}">{j + 1}</a>' for j in range(defs) if j != k]
            notes.append(f'Part {k + 1} of {defs} (also {", ".join(others)}).')
        notes.append(f'<span class="src">{html.escape(self.doc.name)}:{first}</span>')
        body = self.highlight(lines, lang) if lang in LANGS else html.escape('\n'.join(lines))
        return (f'<figure class="chunk" id="{self.anchor(name, k)}"><figcaption>'
                f'<a class="name" href="#{self.anchor(name, k)}">⟨{html.escape(name)}⟩</a> {sign}</figcaption>'
                f'<pre>{body}</pre><div class="xref">{" ".join(notes)}</div></figure>')

    def table(self, rows):
        cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
        head, body = cells[0], [r for r in cells[2:]] if len(cells) > 1 and set(''.join(cells[1])) <= set('-: ') else cells[1:]
        out = ['<div class="table"><table><thead><tr>', *(f'<th>{self.inline(c)}</th>' for c in head), '</tr></thead><tbody>']
        for r in body:
            out.append('<tr>' + ''.join(f'<td>{self.inline(c)}</td>' for c in r) + '</tr>')
        return ''.join(out) + '</tbody></table></div>'

    def prose(self, lines, toc):
        out, para, i = [], [], 0

        def flush():
            if para:
                out.append('<p>' + self.inline(' '.join(para)) + '</p>')
                para.clear()
        while i < len(lines):
            line = lines[i]
            h = re.match(r'^(#{1,4})\s+(.*)$', line)
            if not line.strip():
                flush()
            elif h:
                flush()
                level, title = len(h[1]), h[2].strip()
                hid = slug(title)
                if level in (2, 3):
                    toc.append((level, hid, title))
                out.append(f'<h{level} id="{hid}">{self.inline(title)}</h{level}>')
            elif line.startswith('|'):
                flush()
                rows = []
                while i < len(lines) and lines[i].startswith('|'):
                    rows.append(lines[i])
                    i += 1
                out.append(self.table(rows))
                continue
            elif re.match(r'^\s*(?:[-*]|\d+\.)\s', line):
                flush()
                ordered = bool(re.match(r'^\s*\d+\.', line))
                items = []
                while i < len(lines) and lines[i].strip():
                    if re.match(r'^\s*(?:[-*]|\d+\.)\s', lines[i]):
                        items.append(re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', lines[i]))
                    else:
                        items[-1] += ' ' + lines[i].strip()
                    i += 1
                tag = 'ol' if ordered else 'ul'
                out.append(f'<{tag}>' + ''.join(f'<li>{self.inline(t)}</li>' for t in items) + f'</{tag}>')
                continue
            elif line.startswith('>'):
                flush()
                quote = []
                while i < len(lines) and lines[i].startswith('>'):
                    quote.append(lines[i][1:].strip())
                    i += 1
                out.append('<blockquote><p>' + self.inline(' '.join(quote)) + '</p></blockquote>')
                continue
            elif re.match(r'^-{3,}\s*$', line):
                flush()
                out.append('<hr>')
            else:
                para.append(line.strip())
            i += 1
        flush()
        return out

    def page(self):
        toc, body = [], []
        for b in self.blocks:
            if b[0] == 'prose':
                body += self.prose(b[1], toc)
            else:
                body.append(self.code(*b[1:]))
        title = next((t for lvl, _, t in toc), self.doc.stem)
        h1 = re.search(r'^#\s+(.*)$', self.doc.read_text(encoding='utf-8'), re.M)
        title = h1[1].strip() if h1 else title
        nav = ''.join(f'<li class="l{lvl}"><a href="#{hid}">{self.inline(t)}</a></li>' for lvl, hid, t in toc)
        index = ''.join(f'<li>{self.ref(n)}' + (f' <span class="muted">used in {", ".join(self.ref(p) for p in sorted(set(self.used[n])))}</span>' if n in self.used else ' <span class="muted">root</span>') + '</li>'
                        for n in sorted(self.chunks, key=str.lower))
        return PAGE.format(title=html.escape(re.sub(r'`', '', title)), css=CSS, nav=nav, body='\n'.join(body), index=index,
                           src=html.escape(str(self.doc)), scripts=MERMAID_SCRIPT if self.mermaid else '')


CSS = """
:root{--bg:#fbfaf7;--fg:#1f1d1a;--muted:#6b665e;--rule:#e4dfd5;--code-bg:#f3f0e8;--chunk-head:#ebe5d8;
--link:#1d5a8a;--kw:#7a2e8a;--ty:#1d6b5a;--cm:#7a7468;--st:#9a4a12;--pp:#8a2a2a;--nu:#2f5f9a;--ref:#1d5a8a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17191c;--fg:#e6e2da;--muted:#9c978d;--rule:#2c3035;
--code-bg:#1f2226;--chunk-head:#272b30;--link:#7fb6e6;--kw:#d199e0;--ty:#7fd1bd;--cm:#8b877f;--st:#e0a070;--pp:#e88a8a;--nu:#9ab8f0;--ref:#7fb6e6}}
:root[data-theme="dark"]{--bg:#17191c;--fg:#e6e2da;--muted:#9c978d;--rule:#2c3035;--code-bg:#1f2226;--chunk-head:#272b30;
--link:#7fb6e6;--kw:#d199e0;--ty:#7fd1bd;--cm:#8b877f;--st:#e0a070;--pp:#e88a8a;--nu:#9ab8f0;--ref:#7fb6e6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 Charter,"Iowan Old Style","Palatino Linotype",Georgia,serif}
.wrap{display:grid;grid-template-columns:16rem minmax(0,1fr);gap:3rem;max-width:86rem;margin:0 auto;padding:2.5rem 1.5rem 6rem}
nav{position:sticky;top:1.5rem;align-self:start;max-height:calc(100vh - 3rem);overflow:auto;font:14px/1.45 system-ui,-apple-system,sans-serif}
nav ul{list-style:none;margin:0;padding:0}nav li{margin:.25rem 0}nav li.l3{padding-left:1rem;font-size:13px}
nav a{color:var(--muted);text-decoration:none}nav a:hover{color:var(--link)}
nav .title{font-weight:600;color:var(--fg);margin-bottom:.75rem}
main{max-width:58rem;min-width:0}
h1{font-size:2.1rem;line-height:1.2;margin:0 0 1rem}h2{font-size:1.5rem;margin:2.8rem 0 .6rem;padding-top:.6rem;border-top:1px solid var(--rule)}
h3{font-size:1.15rem;margin:2rem 0 .4rem}h4{font-size:1rem;margin:1.5rem 0 .3rem}
a{color:var(--link)}p{margin:.7rem 0}ul,ol{padding-left:1.4rem}li{margin:.25rem 0}
blockquote{margin:1rem 0;padding:.2rem 1rem;border-left:3px solid var(--rule);color:var(--muted)}
code,pre{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
code{font-size:.86em;background:var(--code-bg);padding:.08em .3em;border-radius:3px}
pre{margin:0;padding:.8rem 1rem;overflow-x:auto;font-size:13.5px;line-height:1.5;background:var(--code-bg)}
pre.plain{margin:1rem 0;border-radius:6px;border:1px solid var(--rule)}
figure.chunk{margin:1.2rem 0;border:1px solid var(--rule);border-radius:6px;overflow:hidden;scroll-margin-top:1rem}
figure.chunk figcaption{background:var(--chunk-head);padding:.3rem 1rem;font:600 13.5px/1.5 ui-monospace,"SF Mono",Menlo,monospace}
figure.chunk figcaption a.name{color:var(--fg);text-decoration:none}
figure.chunk:target{outline:2px solid var(--link)}
.xref{padding:.3rem 1rem;font:12.5px/1.5 system-ui,-apple-system,sans-serif;color:var(--muted);border-top:1px solid var(--rule)}
.xref .src{float:right;font-family:ui-monospace,Menlo,monospace}
a.ref{color:var(--ref);text-decoration:none;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:.95em}
a.ref:hover{text-decoration:underline}
.kw{color:var(--kw);font-weight:600}.ty{color:var(--ty)}.cm{color:var(--cm);font-style:italic}.st{color:var(--st)}.pp{color:var(--pp)}.nu{color:var(--nu)}
.table{overflow-x:auto;margin:1rem 0}table{border-collapse:collapse;font-size:15px;min-width:60%}
th,td{border-bottom:1px solid var(--rule);padding:.35rem .7rem;text-align:left;vertical-align:top}th{font-family:system-ui,-apple-system,sans-serif;font-size:13px;color:var(--muted)}
figure.diagram{margin:1.2rem 0;padding:1rem;border:1px solid var(--rule);border-radius:6px;background:var(--code-bg);overflow-x:auto;text-align:center}
figure.diagram pre.mermaid{background:none;padding:0;font-size:13px;white-space:pre}
.muted{color:var(--muted);font-size:.9em}#index ul{columns:2;font-size:14px}
footer{margin-top:4rem;color:var(--muted);font:13px/1.5 system-ui,sans-serif}
@media (max-width:900px){.wrap{display:block;padding:1.5rem 16px 4rem}nav{position:static;max-height:none;margin-bottom:2rem;
border-bottom:1px solid var(--rule);padding-bottom:1rem}#index ul{columns:1}body{font-size:16px}}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="wrap"><nav><div class="title">{title}</div><ul>{nav}<li class="l2"><a href="#index">Chunk index</a></li></ul></nav>
<main>{body}
<h2 id="index">Chunk index</h2><ul>{index}</ul>
<footer>Woven by tools/tangle.py from {src}. The code shown is exactly what tangles into the generated file.</footer>
</main></div>{scripts}</body></html>
"""

# Diagrams: ```mermaid blocks (state, flow, sequence and packet-beta diagrams), rendered in the page by
# Mermaid, pinned. GitHub renders the same blocks in the .md file.
MERMAID_SCRIPT = """<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';
const dark = matchMedia('(prefers-color-scheme: dark)').matches;
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'neutral' });
await mermaid.run({ querySelector: 'pre.mermaid' });
</script>"""


DOC_DIRS = ('firmware', 'ws0')   # plus the repository root itself (gateway.lit.md)


def all_docs():
    return sorted([d for top in DOC_DIRS for d in (ROOT/top).rglob('*.lit.md')] + list(ROOT.glob('*.lit.md')))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('docs', nargs='*', type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='fail if a committed root differs from its tangle')
    mode.add_argument('--weave', metavar='OUT.html', type=Path, help='write a standalone HTML page')
    mode.add_argument('--lines', action='store_true', help='tangle with #line directives (needs -o)')
    ap.add_argument('-o', '--output', type=Path, help='with --lines: where to write the root')
    a = ap.parse_args(argv)
    try:
        if a.check:
            docs = a.docs or all_docs()
            stale = check(docs)
            if not stale:
                print(f'tangle: OK ({len(docs)} literate source(s) match their generated files)')
            return 1 if stale else 0
        if len(a.docs) < 1:
            ap.error('name a .lit.md document')
        if a.weave:
            if len(a.docs) != 1:
                ap.error('--weave takes one document')
            a.weave.write_text(Weaver(a.docs[0]).page(), encoding='utf-8')
            print(f'woven: {a.weave}')
            return 0
        if a.lines:
            roots = tangle(a.docs[0], lines_mode=True)
            if not a.output or len(roots) != 1 or len(a.docs) != 1:
                ap.error('--lines writes one root of one document to -o OUT (never over the committed file)')
            a.output.write_text(next(iter(roots.values())), encoding='utf-8')
            return 0
        for doc in a.docs:
            for path, text in tangle(doc).items():
                if not path.exists() or path.read_text(encoding='utf-8') != text:
                    path.write_text(text, encoding='utf-8')
                    print(f'tangled: {path}')
        return 0
    except LitError as e:
        print(f'tangle: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
