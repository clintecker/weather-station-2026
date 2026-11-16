"""Hole-callout alignment check, shared by both sessions' page builders.

Every marker (ring, or leader dot) that names a hole must sit on that hole:
  1. the marker centre is within TOL mm of the hole anchor (the hole's model position, projected), and
  2. where the scene draws the hole (top-down views), the anchor is within TOL mm of the centre of the circle
     the hidden-line render actually drew there (fitted from the SVG geometry, independent of the anchors).
A marker that lands within NEAR mm of a hole anchor without being on it also fails (an offset callout).
Scenes declare which anchors are holes with r3d.Scene.hole(); the render writes them to the JSON.
"""
import json
import re
from pathlib import Path

import math

TOL = 0.15          # mm
NEAR = 2.0          # mm: a marker this close to a hole, but not on it, is an offset callout
ARTS = []           # Art objects placed on the current page
LOOKUPS = {}        # (round x, round y) -> (art, anchor) for every Art.A() on the current page
MARKS = []          # (x, y, kind)
_CIRCLES = {}
STATS = {"on_anchor": 0, "vs_drawing": 0, "free": 0}


def reset():
    ARTS.clear()
    LOOKUPS.clear()
    MARKS.clear()


def art(a):
    ARTS.append(a)


def lookup(a, name, xy):
    LOOKUPS[(round(xy[0], 2), round(xy[1], 2))] = (a, name)


def mark(x, y, kind):
    MARKS.append((x, y, kind))


def _solve3(A, b):
    """Least squares for 3 unknowns via the normal equations (Cramer)."""
    M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(3)] for i in range(3)]
    v = [sum(A[k][i] * b[k] for k in range(len(A))) for i in range(3)]
    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    D = det(M)
    if abs(D) < 1e-12:
        return None
    out = []
    for i in range(3):
        Mi = [row[:] for row in M]
        for r in range(3):
            Mi[r][i] = v[r]
        out.append(det(Mi) / D)
    return out


def _fit(pts):
    """Algebraic circle fit: (cx, cy, r, rms residual) or None."""
    A = [(2 * x, 2 * y, 1.0) for x, y in pts]
    b = [x * x + y * y for x, y in pts]
    sol = _solve3(A, b)
    if sol is None:
        return None
    cx, cy, k = sol
    r = math.sqrt(max(k + cx * cx + cy * cy, 0))
    res = math.sqrt(sum((math.hypot(x - cx, y - cy) - r) ** 2 for x, y in pts) / len(pts))
    return cx, cy, r, res


def circles(svg_path, scale):
    """Circles the render drew (hole edges, pad rings, screw heads): [(cx, cy, r)] in SVG points."""
    key = str(svg_path)
    if key in _CIRCLES:
        return _CIRCLES[key]
    txt = Path(svg_path).read_text()
    arcs = []           # (cx, cy, r, sweep): the render splits a circle into several arcs
    for d in re.findall(r'<path d="([^"]*)"', txt):
        for sub in d.split("M")[1:]:
            nums = re.findall(r"-?\d+\.?\d*", sub)
            if len(nums) < 8:
                continue
            f = [float(v) for v in nums]
            p = list(zip(f[0::2], f[1::2]))
            span = max(max(q[0] for q in p) - min(q[0] for q in p), max(q[1] for q in p) - min(q[1] for q in p))
            if not (0.2 * scale < span < 7.0 * scale):
                continue
            fit = _fit(p)
            if fit is None:
                continue
            cx, cy, r, res = fit
            if not (0.35 * scale < r < 3.3 * scale and res < 0.01 * r + 0.02):
                continue
            ang = [math.atan2(y - cy, x - cx) for x, y in p]
            sweep = sum((a1 - a0 + math.pi) % (2 * math.pi) - math.pi for a0, a1 in zip(ang, ang[1:]))
            arcs.append((cx, cy, r, abs(sweep)))
    out = []            # merge arcs of one circle; keep circles drawn round at least 2 rad in total
    tol = 0.05 * scale
    for cx, cy, r, sw in arcs:
        for i, (ox, oy, orr, osw) in enumerate(out):
            if math.hypot(cx - ox, cy - oy) < tol and abs(r - orr) < tol:
                out[i] = (ox, oy, orr, osw + sw)
                break
        else:
            out.append((cx, cy, r, sw))
    out = [(cx, cy, r) for cx, cy, r, sw in out if sw > 2.0]
    _CIRCLES[key] = out
    return out


def check(page):
    """Returns a list of issue strings for the current page, then resets."""
    issues = []
    holes = []          # (art, name, page x, page y)
    for a in ARTS:
        for n, drawn in a.holes.items():
            if n in a.anchors:
                holes.append((a, n) + tuple(a.A_raw(n)))
    for (x, y, kind) in MARKS:
        hit = LOOKUPS.get((round(x, 2), round(y, 2)))
        if hit and hit[1] in hit[0].holes:
            a, n = hit
            STATS["on_anchor"] += 1
            ax, ay = a.A_raw(n)
            mm = a.k * a.scale
            d = math.hypot(x - ax, y - ay) / mm
            if d > TOL:
                issues.append(f"page {page}: {kind} on {a.name}:{n} is {d:.2f} mm off the hole")
            if a.holes[n]:
                STATS["vs_drawing"] += 1
                cs = circles(a.svg, a.scale)
                sx, sy = (ax - a.x) / a.k, a.sh - (ay - a.y) / a.k
                best = min((math.hypot(cx - sx, cy - sy) for cx, cy, r in cs), default=1e9) / a.scale
                if best > TOL:
                    issues.append(f"page {page}: {a.name}:{n}: no drawn hole within {TOL} mm of the anchor "
                                  f"(nearest {best:.2f} mm)")
            continue
        if hit:
            continue    # placed on another named target (a breakout pad, a pin): not a card or board hole
        # placed from no anchor at all: is it sitting near a hole (an offset callout)?
        STATS["free"] += 1
        for (a, n, ax, ay) in holes:
            d = math.hypot(x - ax, y - ay) / (a.k * a.scale)
            if kind == "ring" and TOL < d < NEAR:
                if a.x <= x <= a.x + a.w and a.y <= y <= a.y + a.h:
                    issues.append(f"page {page}: {kind} at ({x:.1f}, {y:.1f}) is {d:.2f} mm from hole "
                                  f"{a.name}:{n} but not on it")
                    break
    reset()
    return issues
