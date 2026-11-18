"""Page helpers shared by the pod bench sheets (Session P: pod boards; Session Q: boxes, shield, install).

The TX sheets' page furniture (hardware/tx-stack-r1/sheets/session3/sheetlib.py, read-only) with this unit's name, the
hole ring, the chip lanes (the Session 3 lanes), wrapped text, tick boxes and a dark tag. Every chip, ring and leader is
recorded for the TX label-overlap and hole-callout checks the build runs on each page.
"""
import math
import sys
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TXS = _HERE.parent.parent / "tx-stack-r1" / "sheets"
for _p in (_TXS / "session3", _TXS / "session1" / "v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
sys.dont_write_bytecode = True

from sheetlib import *          # noqa: F401,F403,E402  (TX page furniture, chips, leaders, Art, checks; read-only)
import sheetlib as SL           # noqa: E402


def cap(*sentences, width=96):
    return textwrap.wrap(" ".join(sentences), width)


# ------------------------------------------------------------------ page furniture (sheetlib.page with this unit's name)
def page(c, step_no, title, sub, pg, slogan):
    if pdfmetrics.stringWidth(sub, "MONO", 8) > W - 2 * M - 95:
        raise ValueError(f"page {pg}: subtitle too long for the header: {sub!r}")
    SL.page(c, step_no, title, sub, pg, slogan)
    c.setFillColor(INK)                              # cover sheetlib's unit line (the TX's) with this unit's
    c.rect(W - M - 130, H - 41, 130, 10, stroke=0, fill=1)
    text(c, W - M, H - 38, "UNIT: PODS-R1", 8, "MONO", GREY, "r", rec=False)


def ring(c, x, y, r=4.4, w=1.6):
    """Hole marker that reads on the cream board and its gold pads: magenta on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(NEON)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def art_box(a, pad=2):
    return (a.x - pad, a.y - pad, a.x + a.w + pad, a.y + a.h + pad)


def _halo_line(c, x0, y0, x1, y1):
    c.setStrokeColor(WHITE)
    lw(c, 2.6)
    c.line(x0, y0, x1, y1)
    c.setStrokeColor(INK)
    lw(c, 1.0)
    c.line(x0, y0, x1, y1)


def _end(c, r, sx, sy, px, py, is_hole, ring_r):
    if is_hole:
        d = math.hypot(sx - px, sy - py)
        tx, ty = px + (sx - px) / d * ring_r, py + (sy - py) / d * ring_r
    else:
        tx, ty = px, py
        SL.HC.mark(px, py, "leader dot")
    _halo_line(c, sx, sy, tx, ty)
    if not is_hole:
        c.setFillColor(WHITE)
        c.circle(px, py, 2.6, stroke=0, fill=1)
        c.setFillColor(INK)
        c.circle(px, py, 1.6, stroke=0, fill=1)
    LAB.leaders.append((sx, sy, tx, ty, len(LAB.chips) - 1))


def lanes(c, items, box, size=9, gap=8, color=NEON, font="ALT", ring_r=4.4):
    """Chips in lanes round a drawing (the Session 3 lanes): items [(text, px, py, lane, is_hole)], lane 'up' / 'dn'
    (a row above / below, in the left-to-right order of the targets) or 'lt' / 'rt' (a column beside it)."""
    x0b, y0b, x1b, y1b = box
    asc = size * 0.72
    pan = next(p for p in LAB.panels if p[0] <= x0b + 1 and p[2] >= x1b - 1)
    for k in ("up", "dn"):
        its = sorted((px, s_, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        wd = [pdfmetrics.stringWidth(s_.split("\n")[0], font, size) + 5.2 for _px, s_, _py, _ih in its]
        ideal = [px - w_ / 2 for (px, *_r), w_ in zip(its, wd)]
        xs = ideal[:]
        for _ in range(40):
            for n in range(1, len(xs)):
                xs[n] = max(xs[n], xs[n - 1] + wd[n - 1] + gap)
            lo = pan[0] + 6 - xs[0]
            if lo > 0:
                xs = [v + lo for v in xs]
            hi = xs[-1] + wd[-1] - (pan[2] - 6)
            if hi > 0:
                xs = [v - hi for v in xs]
            n = 0
            while n < len(xs):
                m = n
                while m + 1 < len(xs) and abs(xs[m + 1] - (xs[m] + wd[m] + gap)) < 1e-6:
                    m += 1
                d = sum(xs[q] - ideal[q] for q in range(n, m + 1)) / (m - n + 1)
                for q in range(n, m + 1):
                    xs[q] -= d * 0.5
                n = m + 1
        lo = pan[0] + 6 - xs[0]
        if lo > 0:
            xs = [v + lo for v in xs]
        hi = xs[-1] + wd[-1] - (pan[2] - 6)
        if hi > 0:
            xs = [v - hi for v in xs]
        yb = (y1b + 5) if k == "up" else (y0b - 5 - asc)
        for (px, s_, py, ih), xa, w_ in zip(its, xs, wd):
            r = chip(c, xa + w_ / 2, yb, s_, size, font, color, "c")
            sx, sy = (r[0] + r[2]) / 2, (r[1] if k == "up" else r[3])
            _end(c, r, sx, sy, px, py, ih, ring_r)
    for k in ("lt", "rt"):
        its = sorted((-py, s_, px, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        nl = [s_.count("\n") + 1 for _k, s_, *_r in its]
        ys = [py for *_r, py, _ih in its]
        for _ in range(40):
            for n in range(1, len(ys)):
                ys[n] = min(ys[n], ys[n - 1] - (asc + 5.2 + 3) - size * 1.12 * (nl[n - 1] - 1))
        for (_k, s_, px, py, ih), yy in zip(its, ys):
            if k == "lt":
                r = chip(c, x0b - 6, yy - asc / 2, s_, size, font, color, "r")
                sx, sy = r[2], (r[1] + r[3]) / 2
            else:
                r = chip(c, x1b + 6, yy - asc / 2, s_, size, font, color, "l")
                sx, sy = r[0], (r[1] + r[3]) / 2
            _end(c, r, sx, sy, px, py, ih, ring_r)


def ring_lanes(c, a, holes, names=None, box=None, size=8.5, side=None):
    """Ring every hole and name it in a lane above or below the drawing (by the hole's height on the page); names maps
    an anchor to its chip text (default: the anchor's own name)."""
    cy = a.y + a.h / 2
    items = []
    for h in holes:
        px, py = a.A(h)
        ring(c, px, py)
        lane = side or ("up" if py > cy else "dn")
        items.append(((names or {}).get(h, h), px, py, lane, True))
    lanes(c, items, box or art_box(a), size=size)


def para(c, x, ytop, lines, size=8.6, lead=11.0, font="ALT", color=INK, w=None, what="text"):
    """Wrapped running text as plain text (recorded for the badge check), blocked off for the chips."""
    yy = ytop
    for ln in lines:
        text(c, x, yy, ln, size, font, color)
        yy -= lead
    if w:
        LAB.block(x, yy + lead - 3, x + w, ytop + size, what)
    return yy


def wrap_px(s, width_pt, size, font="ALT"):
    words, out, cur = s.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(t, font, size) > width_pt and cur:
            out.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def tick_box(c, x, y, s=11):
    c.setStrokeColor(NEON)
    lw(c, 1.4)
    c.rect(x, y, s, s, stroke=1, fill=0)
    LAB.block(x, y, x + s, y + s, "tick")


def tag(c, x, y, s, size=12):
    """A dark tag with hazard-yellow capitals (TOP FACE, RIM, BACK FACE ...), blocked off for the chips."""
    w = pdfmetrics.stringWidth(s, "HEAD", size) + 10
    c.setFillColor(INK)
    c.rect(x, y, w, size + 5, stroke=0, fill=1)
    text(c, x + 5, y + size * 0.375, s, size, "HEAD", HAZ)
    LAB.block(x, y, x + w, y + size + 5, s)
    return w
