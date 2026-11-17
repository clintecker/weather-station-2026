"""Read build/B2.md (the bench content's source of truth) into plain Python: every table the sheets print comes
from here, never retyped.

  WIRES    [dict(n, a, b, length, line, colour, what)]           section 2
  JUMPERS  [dict(n, a, b, length, line, what)]                   section 3
  PARTS    {ref: dict(ref, head, pins=[(pin, hole, line)])}      section 4, in B2.md's order (lowest first)
  LEADS    [dict(n, a, b, length, line, colour, what)]           the leads section, if B2.md has one
  STRIPS   [(strip, line, holes used)]                           strip map
Sections are found by their titles, not their numbers (the numbering moves when B2.md is regenerated).
  BEFORE   [str]                                                 "Before power"
"""
import re
from pathlib import Path

REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
SRC = REPO / "build" / "B2.md"


def _rows(lines):
    out = []
    for ln in lines:
        if ln.startswith("|") and not re.match(r"^\|[-| ]+\|$", ln):
            out.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return out[1:]          # drop the header row


def _sections(text):
    secs, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^## (.*)", ln)
        if m:
            cur = m.group(1)
            secs[cur] = []
        elif cur:
            secs[cur].append(ln)
    return secs


TEXT = SRC.read_text()
SEC = _sections(TEXT)


def _sec(word, need=True):
    for k, v in SEC.items():
        if word.lower() in k.lower():
            return v
    if need:
        raise KeyError(f"B2.md has no section titled like {word!r}")
    return []


WIRES = [dict(n=int(r[0]), a=r[1], b=r[2], length=r[3], line=r[4], colour=r[5], what=r[6])
         for r in _rows(_sec("Underside wires"))]
JUMPERS = [dict(n=int(r[0]), a=r[1], b=r[2], length=r[3], line=r[4], what=r[5]) for r in _rows(_sec("Bare jumpers"))]
LEADS = [dict(n=int(r[0]), a=r[1], b=r[2], length=r[3], line=r[4], colour=r[5], what=r[6]) for r in _rows(_sec("Leads", need=False))]
STRIPS = [tuple(r) for r in _rows(_sec("Strip map"))]
BEFORE = [ln[2:] for ln in _sec("Before power") if ln.startswith("- ")]

PARTS = {}
_cur = None
for ln in _sec("Parts, lowest first"):
    m = re.match(r"^\*\*(\S+)\*\* (.*)", ln)
    if m:
        _cur = m.group(1)
        PARTS[_cur] = dict(ref=_cur, head=m.group(2), pins=[])
    elif _cur and ln.startswith("|") and not re.match(r"^\|[-| ]+\|$", ln) and not ln.startswith("| Pin "):
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        PARTS[_cur]["pins"].append((c[0], c[1], c[2]))


SNAP = [ln.split(". ", 1)[1] for ln in _sec("Snap off") if re.match(r"^\d\. ", ln)]


def top_mm(ref):
    m = re.search(r"top ([\d.]+) mm above the card", PARTS[ref]["head"])
    return float(m.group(1))


def hole_of(ref, pin_name):
    """The hole a named pin goes in: hole_of('D41', 'cathode') -> 'd16'."""
    return next(h for p, h, _l in PARTS[ref]["pins"] if p.split(" (")[0] == pin_name or p.endswith(f"({pin_name})"))


if __name__ == "__main__":
    print(len(WIRES), "wires", len(JUMPERS), "jumpers", len(PARTS), "parts", len(LEADS), "leads", len(STRIPS), "strips")
    for r, p in PARTS.items():
        print(r, top_mm(r), p["pins"][:2])
    print(BEFORE)
