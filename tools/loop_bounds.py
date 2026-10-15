"""Every loop in our firmware C has a fixed upper bound (Power of Ten rule 2, docs/power-of-ten.md).

    python3 tools/loop_bounds.py [paths...]     (default: our firmware C, as tools/code_shape.sh)

A counting loop states its bound in its header and needs nothing else:
    for (<type> i = <start>; i < <bound> [&& ...]; i++)     (also <=, >, >=, and --, += n, -= n)
Every other loop (while, do ... while, a for loop of another shape, for (;;)) must say what bounds
it in a comment on its own line or the line above, starting `bound:` (for example
`/* bound: at most JOURNAL_CAPACITY calls, each moves i on */`). do { ... } while (0) in a macro is
not a loop. Exit status 1 with one line per unannotated loop.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ['firmware/stage0-node/App', 'firmware/common', 'firmware/stage0.c', 'firmware/stage0.h']
LOOP = re.compile(r'\b(for|while|do)\b\s*([({]|$)')
COUNTING = re.compile(r'^\s*(?:[\w\s*]+?\s)?\**(\w+)\s*=[^;]*;\s*(\w+)\s*(<|<=|>|>=)\s*[^;]+;\s*'
                      r'(?:(\w+)\s*(\+\+|--|\+=\s*\w+|-=\s*\w+)|(\+\+|--)\s*(\w+))\s*$')


def header(text, start):
    """The text between the parentheses that open at or after start (None if unbalanced)."""
    i = text.index('(', start)
    depth = 0
    for j in range(i, len(text)):
        depth += {'(': 1, ')': -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j]
    return None


def counting(head):
    """1 if a for-header is `v = a; v < bound...; v++` with one loop variable."""
    parts = head.split(';')
    if len(parts) != 3:
        return False
    cond = parts[1].split('&&')[0]
    parts[2] = parts[2].split(',')[0]           # i++, p += 2: the first step is the loop variable's
    m = COUNTING.match(f'{parts[0]};{cond};{parts[2]}')
    if not m:
        return False
    var = m[1]
    return m[2] == var and var in (m[4], m[7])


def annotated(lines, n):
    return 'bound:' in lines[n] or (n > 0 and 'bound:' in lines[n - 1])


def strip(text):
    """The code with comments and string literals blanked out, line breaks kept."""
    blank = lambda m: re.sub(r'[^\n]', ' ', m[0])
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', blank, text, flags=re.S)


def check(path):
    lines = path.read_text().splitlines()
    code = strip(path.read_text())
    code_lines = code.splitlines()
    offsets = [0]
    for line in code_lines:
        offsets.append(offsets[-1] + len(line) + 1)
    found = []
    for n, line in enumerate(code_lines):
        for m in LOOP.finditer(line):
            kind = m[1]
            if kind == 'while' and (re.search(r'}\s*while\b', line) or re.search(r'while\s*\(\s*0\s*\)', line)):
                continue                                  # the tail of do ... while, or do-while(0)
            if kind == 'do' and re.search(r'while\s*\(\s*0\s*\)', line):
                continue
            if kind == 'for':
                head = header(code, offsets[n] + m.start())
                if head is not None and counting(head):
                    continue
            if not annotated(lines, n):
                found.append(f'{path.relative_to(ROOT)}:{n + 1}: {kind} loop without a counting header or a "bound:" comment')
    return found


def files(paths):
    for p in paths:
        p = ROOT/p
        yield from sorted(p.rglob('*.[ch]')) if p.is_dir() else [p]


def main(argv):
    problems = [msg for f in files(argv or DEFAULT) for msg in check(f)]
    for msg in problems:
        print(msg)
    print(f'loop bounds: {"FAIL" if problems else "OK"} ({len(problems)} unannotated)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
