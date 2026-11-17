"""Adafruit Perma-Proto Quarter #1608: hole grid, copper strips and outline, built from sources.py (never a ruler).

Coordinates are millimetres, x to the right, y up, ORIGIN AT THE BOARD'S LOWER-LEFT CORNER with the silkscreen
readable (the column numbers 1-15 upright along the top and bottom edges, 1 at the left; row letters beside both long
edges, A at the bottom, J at the top). Adafruit's Eagle file has its origin at the board centre with the same
orientation, so the conversion is a pure shift of (+21.59, +25.4); nothing is mirrored or rotated.

Hole names are the ones printed on the board: row letter A-J then column number ("A1", "J15"). The four rails carry no
printed names (only a red + line and a blue - line), so they are named by position and polarity: "bot+", "bot-"
(below row A) and "top-", "top+" (above row J), each followed by the column number ("bot+3"); see sources.py
permaproto_q_silk. Every hole is plated through both sides.

Strips (copper joined on the bottom layer), from sources.py permaproto_q_strips and permaproto_q_rails:
  "A-E<c>", "F-J<c>"   the five holes of one column half (the halves of a column are NOT joined), 30 strips
  "rail bot+" ...      one continuous 15-hole strip per rail, 4 strips
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import sources as _src            # noqa: E402  hardware/pods-r1/sources.py


def _build():
    s = _src
    w, h = s.val("permaproto_q")
    cx, cy = w / 2, h / 2                       # the file's origin (board centre) in lower-left coordinates
    letters = s.val("permaproto_q_silk")
    rows = s.val("permaproto_q_rows")
    n, pitch, x0 = s.val("permaproto_q_cols")
    # rail polarity: + at y -21.59 and 19.05 (outer bottom, inner top), - at -19.05 and 21.59 (sources.py silk row)
    names = {-21.59: "bot+", -19.05: "bot-", 19.05: "top+", 21.59: "top-"}
    assert set(names) == set(s.val("permaproto_q_rails")), "rails in sources.py moved: update the polarity map"
    holes, strip = {}, {}
    for x, y, sid in s.permaproto_q_holes():
        if sid.startswith("rail"):
            rail = names[float(sid[4:])]
            name, sid = f"{rail}{round((x - x0) / pitch) + 1}", f"rail {rail}"
        else:
            col = int(sid.split("-")[1][1:])
            name = f"{letters[rows.index(y)]}{col}"
        assert name not in holes, name
        holes[name] = (round(x + cx, 4), round(y + cy, 4))
        strip[name] = sid
    return holes, strip


def _outline():
    import math
    w, h = _src.val("permaproto_q")
    r = _src.val("permaproto_q_corner_r")
    d, mx, my = _src.val("permaproto_q_mount")
    pts = []
    for (ox, oy), a0 in (((w - r, r), -90), ((w - r, h - r), 0), ((r, h - r), 90), ((r, r), 180)):
        for i in range(0, 91, 10):
            a = math.radians(a0 + i)
            pts.append((round(ox + r * math.cos(a), 4), round(oy + r * math.sin(a), 4)))
    return {"polygon": pts, "width": w, "height": h, "corner_r": r,
            "mounting_holes": [(round(w / 2 - mx, 4), round(h / 2 + my, 4), d), (round(w / 2 + mx, 4), round(h / 2 + my, 4), d)]}


HOLES, _STRIP = _build()
OUTLINE = _outline()


def strip_of(hole: str) -> str:
    """The copper group the named hole belongs to ("A-E7", "F-J7", "rail top+"); KeyError for a name not on the board."""
    return _STRIP[hole]
