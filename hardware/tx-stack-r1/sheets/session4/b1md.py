"""build/B1.md, parsed (the content source of truth for every table on the Session 4 sheets). Pure Python: used by
both scenes4.py (CAD venv) and make_session4.py (PDF venv), so no table on a page is typed by hand.

  sections()  -> {heading: [lines]}
  wires(), jumpers(), strips()  -> lists of dicts keyed by the table's header
Sections are found by their heading's words ("Underside wires", "Bare jumpers", "Parts", "Strip map"), not numbers.
  parts()     -> [dict(ref, head, pins=[dict(Pin, Hole, Line)])] in B1.md order (lowest first)
  before()    -> the "Before power" bullet lines
"""
import re
from pathlib import Path

REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
MD = REPO / "build" / "B1.md"


def _text():
    return MD.read_text()


def sections():
    out, cur = {}, None
    for ln in _text().splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return out


def _sec(words):
    hits = [v for k, v in sections().items() if words.lower() in k.lower()]
    assert len(hits) == 1, f"B1.md: {len(hits)} sections named like {words!r}"
    return hits[0]


def _tables(lines):
    """Every markdown table in lines: [(header, [row dicts])], in order."""
    out, hdr, rows = [], None, []
    for ln in lines + [""]:
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if hdr is None:
                hdr = cells
            elif set("".join(cells)) <= set("-: "):
                continue
            else:
                rows.append(dict(zip(hdr, cells)))
        elif hdr is not None:
            out.append((hdr, rows))
            hdr, rows = None, []
    return out


def wires():
    return _tables(_sec("Underside wires"))[0][1]


def jumpers():
    return _tables(_sec("Bare jumpers"))[0][1]


def strips():
    return _tables(_sec("Strip map"))[0][1]


def has_leads():
    return any("lead" in k.lower() and "first" not in k.lower() for k in sections())


def before():
    return [ln[2:].strip() for ln in _sec("Before power") if ln.startswith("- ")]


def parts():
    lines = _sec("Parts, lowest first")
    out, cur = [], None
    for ln in lines:
        m = re.match(r"\*\*(\S+)\*\* (.*)", ln)
        if m:
            cur = dict(ref=m.group(1), head=m.group(2), pins=[])
            out.append(cur)
        elif ln.startswith("|") and cur is not None:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells[0] in ("Pin",) or set("".join(cells)) <= set("-: "):
                continue
            cur["pins"].append(dict(Pin=cells[0], Hole=cells[1], Line=cells[2]))
    return out


def part(ref):
    return next(p for p in parts() if p["ref"] == ref)


def top_mm(ref):
    m = re.search(r"top ([\d.]+) mm above the card", part(ref)["head"])
    return float(m.group(1)) if m else None


if __name__ == "__main__":
    print(len(wires()), "wires", len(jumpers()), "jumpers", len(strips()), "strips")
    for p in parts():
        print(p["ref"], len(p["pins"]), top_mm(p["ref"]))
    for b in before():
        print("-", b)
