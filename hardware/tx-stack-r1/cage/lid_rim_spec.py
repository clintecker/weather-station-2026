"""Read cage/lid-rim-spec.md (the lid rim measured off Clint's 300 dpi lid scans, 2026-11-11) into numbers.

The spec is the single source for the rim: sources.py takes the base's rim keys from it, and cage.py --ring builds
the test ring straight from its segment table. Pure Python (no CadQuery). Frame: the spec's own, origin at the lid
centre, X along the long side, Y along the short side.

    python3 lid_rim_spec.py      print what was read and the spec's own checks
"""
import math
import re
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "lid-rim-spec.md"
_N = r"(-?\d+(?:\.\d+)?)"
_P = r"\(" + _N + r", " + _N + r"\)"


def _one(pat, text, what):
    m = re.search(pat, text)
    if not m:
        raise ValueError(f"lid-rim-spec.md: {what} not found ({pat})")
    return tuple(float(g) for g in m.groups())


def load(path=SPEC):
    t = Path(path).read_text()
    out = {}
    out["outline"] = _one(r"Rectangle \*\*" + _N + r" × " + _N + r"\*\*", t, "the outline")      # X, Y
    out["corner_r"] = _one(r"Corners rounded \*\*R" + _N + r"\*\*", t, "the corner radius")[0]
    out["lip_w"], out["lip_h"] = _one(r"\*\*Section:\*\* " + _N + r" wide .*? × " + _N + r" tall", t, "the lip section")
    out["lip_z"] = _one(r"lip stands on top of the land, from Z " + _N + r" to Z " + _N, t, "the lip's Z")
    out["land_z"] = _one(r"\*\*Thickness:\*\* Z " + _N + r" to " + _N, t, "the land's thickness")
    out["hole_d"], n = _one(r"Ø" + _N + r" through-holes, (\d+) of them", t, "the holes")
    out["holes"] = _one(r"\*\*Centres:\*\* \(±" + _N + r", ±" + _N + r"\)", t, "the hole centres")
    out["n_holes"] = int(n)
    out["spans_stated"] = _one(r"straight lips are " + _N + r" apart along X and " + _N + r" apart along Y", t, "the spans check")
    out["inset_stated"] = _one(r"\*\*Inset:\*\* the straight lip sits " + _N + r" in", t, "the inset check")[0]
    out["s_stated"] = _one(r"\*\*S depth:\*\* each middle run is " + _N + r" in", t, "the S depth check")[0]
    out["r_mid_stated"] = _one(r"\*\*Middle bend:\*\* R" + _N, t, "the middle bend check")[0]
    out["r_outer_stated"] = _one(r"\*\*Outer bends:\*\* R" + _N, t, "the outer bends check")[0]
    out["clear_stated"] = _one(r"at least " + _N + r" of plastic to the lip", t, "the hole clearance")[0]
    segs = []
    row = re.compile(r"^\| (\d+) \| (line|arc R" + _N + r", turning (left|right) \((CCW|CW)\)) \| " + _P + r" \| " + _P
                     + r" \|(.*)\|\s*$", re.M)
    for m in row.finditer(t):
        a, b = (float(m.group(6)), float(m.group(7))), (float(m.group(8)), float(m.group(9)))
        if m.group(2) == "line":
            segs.append(("line", a, b))
        else:
            c = _one(r"centre " + _P, m.group(10), f"segment {m.group(1)}'s centre")
            segs.append(("arc", a, b, c, float(m.group(3)), m.group(5)))
    if len(segs) != 7:
        raise ValueError(f"lid-rim-spec.md: {len(segs)} segments read, 7 expected")
    out["quadrant"] = segs
    return out


def derived(sp=None):
    """The base's rim numbers from the spec (for sources.py), each with the formula."""
    sp = sp or load()
    L, Wd = sp["outline"]
    q = sp["quadrant"]
    short_lip, long_lip = q[0][1][0], q[6][1][1]          # x of the short-side straight, y of the long-side straight
    run_x, run_y = q[4][1][0], q[2][1][1]                  # the S's two middle runs: x of #5, y of #3
    hx, hy = sp["holes"]
    return dict(
        lid_out=(L, Wd), corner_r=sp["corner_r"],
        inset_short=L / 2 - short_lip, inset_long=Wd / 2 - long_lip,
        spans=(2 * short_lip, 2 * long_lip),
        s_short=short_lip - run_x, s_long=long_lip - run_y,       # middle run in from the short-side / long-side lip
        r_outer=(q[1][4], q[5][4]), r_mid=q[3][4],
        hole_from_short=L / 2 - hx, hole_from_long=Wd / 2 - hy, hole_span=(2 * hx, 2 * hy),
        lip=(sp["lip_w"], sp["lip_h"]), land_h=sp["land_z"][1], top=sp["lip_z"][1], hole_d=sp["hole_d"])


def check(sp=None):
    """The segment table against itself: continuity, arc radii, tangency, turning sense; returns a list of faults."""
    sp = sp or load()
    bad = []
    q = sp["quadrant"]
    for i in range(len(q) - 1):
        if math.dist(q[i][2], q[i + 1][1]) > 1e-6:
            bad.append(f"segments {i + 1} and {i + 2} do not meet: {q[i][2]} vs {q[i + 1][1]}")

    def tan_end(s, at_start):
        if s[0] == "line":
            d = (s[2][0] - s[1][0], s[2][1] - s[1][1])
        else:
            p = s[1] if at_start else s[2]
            c, ccw = s[3], s[5] == "CCW"
            rx, ry = p[0] - c[0], p[1] - c[1]
            d = (-ry, rx) if ccw else (ry, -rx)
        n = math.hypot(*d)
        return d[0] / n, d[1] / n
    for i, s in enumerate(q):
        if s[0] == "arc":
            for p in (s[1], s[2]):
                if abs(math.dist(p, s[3]) - s[4]) > 1e-6:
                    bad.append(f"segment {i + 1}: {p} is {math.dist(p, s[3]):.4f} from its centre, not R{s[4]:g}")
    for i in range(len(q) - 1):
        a, b = tan_end(q[i], False), tan_end(q[i + 1], True)
        if abs(a[0] * b[1] - a[1] * b[0]) > 1e-6 or a[0] * b[0] + a[1] * b[1] < 0:
            bad.append(f"segments {i + 1} -> {i + 2} are not tangent ({a} vs {b})")
    if q[0][1][1] != 0 or q[-1][2][0] != 0:
        bad.append("the quadrant does not start on Y 0 and end on X 0 (the mirrors would not close)")
    return bad


if __name__ == "__main__":
    sp = load()
    for k, v in derived(sp).items():
        print(f"{k:16s} {v}")
    print("segment table:", "; ".join(check(sp)) or "continuous, every arc on its radius and tangent")
