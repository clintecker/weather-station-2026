"""build/B3.md, parsed (read-only): the content source of truth for Session 5's pages and scenes.

WIRES: section 2 rows (n, from, to, cut mm, bends, line, colour, what).
PARTS: section 3, {ref: (heading text, [(pin, hole, line)])} in build order (lowest first).
STRIPS: section 4 rows (strip, line, holes used).
BEFORE: the "Before power" bullets.
"""
import re
from pathlib import Path

REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
SRC = REPO / "build" / "B3.md"
TEXT = SRC.read_text()


def _section(title_re):
    m = re.search(r"^## " + title_re + r".*?$(.*?)(?=^## |\Z)", TEXT, re.S | re.M)
    return m.group(1)


def _rows(block):
    out = []
    for ln in block.splitlines():
        if ln.startswith("|") and not ln.startswith("|---"):
            out.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return out[1:]          # drop the header row


WIRES = []
for r in _rows(_section(r"2\. Underside wires")):
    n, a, b, length, line, colour, what = r
    cut, bends = re.match(r"(\d+) mm, (\d+) bends?", length).groups()
    WIRES.append(dict(n=int(n), a=a, b=b, cut=int(cut), bends=int(bends), line=line, colour=colour, what=what))

PARTS = {}
_s3 = _section(r"3\. Parts")
for m in re.finditer(r"^\*\*(\S+)\*\* (.*?)$\n\n(\|.*?)(?=\n\n|\Z)", _s3, re.S | re.M):
    ref, head, table = m.groups()
    PARTS[ref] = (head, [tuple(r) for r in _rows(table)])

STRIPS = [tuple(r) for r in _rows(_section(r"4\. Strip map"))]
BEFORE = [ln[2:].strip() for ln in _section(r"Before power").splitlines() if ln.startswith("- ")]
SNAP = [re.sub(r"^\d+\. ", "", ln).strip() for ln in _section(r"1\. Snap").splitlines() if re.match(r"^\d+\. ", ln)]

assert len(WIRES) == 21 and [w["n"] for w in WIRES] == list(range(1, 22)), WIRES
assert list(PARTS) == ["J3", "XH3", "U5", "A1"], list(PARTS)
# the slot key: one row of XH3's table is the pulled pin ("key 29 (29)", hole "none: pulled out of ..."), the
# other 29 are fitted
_keys = [r for r in PARTS["XH3"][1] if r[0].startswith("key ")]
assert len(_keys) == 1 and len(PARTS["XH3"][1]) == 30, "XH3: a 1x30 with exactly one pin pulled (the slot key)"
KEY_ROW = _keys[0]
KEY = int(re.match(r"key (\d+)", KEY_ROW[0]).group(1))                     # 29
KEY_HOW = re.search(r"\((grip .*?)\)", KEY_ROW[1]).group(1).split(";")[0]    # pliers, heat, push it out
KEY_WHY = KEY_ROW[2]                                                         # the slot key: ...
KEY_HOLE = f"j{KEY}"
FITTED = [r for r in PARTS["XH3"][1] if r is not KEY_ROW]
DOT = next(s for s in SNAP if s.startswith("Label it"))                     # section 1 step 4: the colour dot
COLOUR = re.match(r"Label it: an? (\w+) paint-pen", DOT).group(1)            # yellow
KEY_CHECK = next(l for l in BEFORE if l.startswith("The 1x30 header less its key pin"))

if __name__ == "__main__":
    for w in WIRES:
        print(w)
    for k, (h, pins) in PARTS.items():
        print(k, h[:60], len(pins))
    print("key", KEY, COLOUR, KEY_HOW, "|", KEY_CHECK[:60])
    print(len(STRIPS), "strips;", len(BEFORE), "before-power bullets;", len(SNAP), "snap steps")
