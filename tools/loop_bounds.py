"""Every loop in our firmware C has a fixed upper bound (Power of Ten rule 2, docs/power-of-ten.md).

    python3 tools/loop_bounds.py [paths...]     (default: our firmware C, as tools/code_shape.sh)

A counting loop states its bound in its header and needs nothing else:
    for (<type> i = <start>; i < <bound> [&& ...]; i++)     (also <=, >, >=, and --, += n, -= n)
where the step moves toward the bound (< and <= with ++ or += a positive literal or CONSTANT; > and
>= with -- or -= one), the body never assigns the loop variable, and a literal bound fits a declared
8- or 16-bit counter. This is a syntactic check: what a symbolic bound (a parameter, a constant) is
worth is reviewed, not proven; a `bound:` comment is trusted as written.
Every other loop (while, do ... while, a for loop of another shape, for (;;)) must say what bounds
it in a comment on its own line or the line above, starting `bound:` (for example
`/* bound: at most JOURNAL_CAPACITY calls, each moves i on */`). do { ... } while (0) in a macro is
not a loop. Exit status 1 with one line per unannotated loop.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ['firmware/stage0-node/App', 'firmware/common', 'firmware/stage0.c', 'firmware/stage0.h',
           'firmware/stage0-node/Core/Src/stm32wlxx_it.c']
LOOP = re.compile(r'\b(for|while|do)\b\s*([({]|$)')
COUNTING = re.compile(r'^\s*(?:[\w\s*]+?\s)?\**(\w+)\s*=[^;]*;\s*(\w+)\s*(<|<=|>|>=)\s*[^;]+;\s*'
                      r'(?:(\w+)\s*(\+\+|--|\+=\s*\w+|-=\s*\w+)|(\+\+|--)\s*(\w+))\s*$')


def header(text, start):
    """(the text between the parentheses that open at or after start, the index after them);
    (None, None) if unbalanced."""
    i = text.index('(', start)
    depth = 0
    for j in range(i, len(text)):
        depth += {'(': 1, ')': -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j], j + 1
    return None, None


TYPE_MAX = {'uint8_t': 255, 'int8_t': 127, 'uint16_t': 65535, 'int16_t': 32767}
UP, DOWN = ('<', '<='), ('>', '>=')


def step_ok(step, var, op):
    """The step moves the variable toward the bound: up for < and <=, down for > and >=."""
    step = step.replace(' ', '')
    if op in UP:
        return step in (f'{var}++', f'++{var}') or bool(re.fullmatch(rf'{var}\+=([1-9]\d*U?|[A-Z][A-Z0-9_]*)', step))
    return step in (f'{var}--', f'--{var}') or bool(re.fullmatch(rf'{var}-=([1-9]\d*U?|[A-Z][A-Z0-9_]*)', step))


def fits(init, cond):
    """A literal bound fits a declared narrow counter (uint8_t i < 300 would never end)."""
    t = re.match(r'\s*(?:const\s+)?(\w+)\s+\w+\s*=', init)
    b = re.search(r'(?:<|<=|>|>=)\s*(\d+)U?\s*$', cond.strip())
    return not (t and b and t[1] in TYPE_MAX and int(b[1]) > TYPE_MAX[t[1]])


def counting(head, body=''):
    """1 if a for-header is `v = a; v < bound...; v++` with one loop variable that only the header moves."""
    parts = head.split(';')
    if len(parts) != 3:
        return False
    cond = parts[1].split('&&')[0]
    step = parts[2].split(',')[0]               # i++, p += 2: the first step is the loop variable's
    m = COUNTING.match(f'{parts[0]};{cond};{step}')
    if not m:
        return False
    var = m[1]
    if m[2] != var or var not in (m[4], m[7]) or not step_ok(step, var, m[3]) or not fits(parts[0], cond):
        return False
    # `*p = x` writes through the variable, not to it; `a.i`, `a->i` are other variables.
    return not re.search(rf'(?<![\w.>])(\+\+|--)\s*{var}\b|(?<![\w.>*])\b{var}\s*(\+\+|--|[-+*/%&|^]?=(?!=))', body)


def body_after(text, head_end):
    """The loop body after the header's closing parenthesis: a braced block or one statement."""
    rest = text[head_end:]
    m = re.match(r'\s*\{', rest)
    if not m:
        return rest.split(';', 1)[0]
    depth = 0
    for j in range(m.end() - 1, len(rest)):
        depth += {'{': 1, '}': -1}.get(rest[j], 0)
        if depth == 0:
            return rest[:j]
    return rest


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
                head, end = header(code, offsets[n] + m.start())
                if head is not None and counting(head, body_after(code, end)):
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
