"""Plan-view routes for the flying wires: every Dupont, the regulator lead, W1, the NTC leads and the two
QT-to-header cables. A route never passes over a used hole, a part or a module, runs between hole rows
when it has to cross a breadboard, and keeps clear of a flat jumper and of earlier routes where it can.

A* on a 0.635 mm grid with a turn penalty, then shortcuts and corner rounding. The routes are how to
dress the wires on the bench, and what the renders draw. Run: python3 routing.py (prints a report).
"""
import heapq
import math

import numpy as np

import build as b

G = 0.635                                  # grid step (mm)
X0, Y0 = -10.0, -10.0
NX, NY = int((b.PLATE_W + 20) / G) + 1, int((b.PLATE_H + 30) / G) + 1
WIRE_R = {"dupont": 0.65, "reg": 0.5, "lead": 0.5, "ntc": 0.3, "qtcable": 0.9}
NUC_Z, QT_Z = 10.0, 6.0
SEAT_TOP = b.BB_Z + 2.5 + 1.6 + 4.0        # top of a seated module's tallest part, near enough for draping
SOCKET_TOP = NUC_Z + 1.6 + 8.5             # NUCLEO Arduino socket top; morpho pins end at the same height
HOUSING = 14.0                             # Dupont housing plus pin above whatever it plugs into


def cell(x, y):
    return int(round((x - X0) / G)), int(round((y - Y0) / G))


def xy(i, j):
    return X0 + i * G, Y0 + j * G


class Plan:
    """Cost, blocked and height maps of the plate in plan view."""

    def __init__(self):
        self.cost = np.zeros((NX, NY))
        self.blocked = np.zeros((NX, NY), bool)
        self.height = np.zeros((NX, NY))
        self.xs = X0 + np.arange(NX) * G
        self.ys = Y0 + np.arange(NY) * G

    def _sl(self, x0, y0, x1, y1):
        i0, j0 = cell(min(x0, x1), min(y0, y1))
        i1, j1 = cell(max(x0, x1), max(y0, y1))
        return slice(max(i0, 0), min(i1 + 1, NX)), slice(max(j0, 0), min(j1 + 1, NY))

    def rect(self, x0, y0, x1, y1, block=False, cost=0.0, height=None):
        si, sj = self._sl(x0, y0, x1, y1)
        if block:
            self.blocked[si, sj] = True
        self.cost[si, sj] += cost
        if height is not None:
            self.height[si, sj] = np.maximum(self.height[si, sj], height)

    def disc(self, x, y, r, block=False, cost=0.0, height=None):
        si, sj = self._sl(x - r, y - r, x + r, y + r)
        X, Y = np.meshgrid(self.xs[si], self.ys[sj], indexing="ij")
        m = (X - x) ** 2 + (Y - y) ** 2 <= r * r
        if block:
            self.blocked[si, sj] |= m
        self.cost[si, sj] += cost * m
        if height is not None:
            self.height[si, sj] = np.where(m, np.maximum(self.height[si, sj], height), self.height[si, sj])

    def line(self, p, q, w, block=False, cost=0.0, height=None):
        n = max(2, int(math.dist(p, q) / (G / 2)))
        seen = np.zeros((NX, NY), bool)
        for k in range(n + 1):
            t = k / n
            x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
            si, sj = self._sl(x - w / 2, y - w / 2, x + w / 2, y + w / 2)
            X, Y = np.meshgrid(self.xs[si], self.ys[sj], indexing="ij")
            seen[si, sj] |= (X - x) ** 2 + (Y - y) ** 2 <= (w / 2) ** 2
        if block:
            self.blocked |= seen
        self.cost += cost * seen
        if height is not None:
            self.height = np.where(seen, np.maximum(self.height, height), self.height)


def used_holes():
    used = set(b.ON_BB.values())
    for c in b.CONDUCTORS:
        used.update(e for e in c[1:3] if isinstance(e, str))
    return used


def leaded_bodies():
    """(ref, h1, h2) for the resistors, capacitors and link headers that sit in holes."""
    out = []
    for ref in sorted({r for (r, _p) in b.ON_BB if r not in b.PLACE}):
        pins = {p: h for (r, p), h in b.ON_BB.items() if r == ref}
        if len(pins) == 2 and ref[0] in "RCJ":
            h1, h2 = sorted(pins.values())
            out.append((ref, h1, h2))
    return out


def base_plan():
    pl = Plan()
    pl.blocked[:, :] = True                                  # nothing routes off the plate
    pl.blocked[slice(*map(lambda v: cell(v, 0)[0], (0.5, b.PLATE_W - 0.5))),
               slice(*map(lambda v: cell(0, v)[1], (0.5, b.PLATE_H - 0.5)))] = False
    for name, (x, y) in b.BOARDS.items():
        pl.rect(x, y, x + b.BB_W, y + b.BB_H, cost=0.15, height=b.BB_Z)
    for ref, p in b.PLACE.items():
        x, y, w, h = b.outline(ref)
        if ref == "A1":
            pl.rect(x, y, x + w, y + h, cost=0.3, height=NUC_Z + 1.6)
            taken = {e[1] for cd in b.CONDUCTORS for e in cd[1:3] if isinstance(e, tuple) and e[0] == "A1"}
            for pin, (px, py) in ((k, b.pin_xy(("A1", k))) for k in b.LOCAL["NUCLEO"]):
                # a wire leaves its housing 14 mm up, so it may cross a header; never another housing
                pl.rect(px - 1.27, py - 1.27, px + 1.27, py + 1.27, cost=1.5, height=SOCKET_TOP)
                if pin in taken:
                    pl.rect(px - 1.35, py - 1.35, px + 1.35, py + 1.35, block=True, height=SOCKET_TOP + HOUSING)
            continue
        top = {"BT1": 18.0, "WG1": 10.5, "WG2": 10.5, "WG3": 10.5}.get(ref)
        if top is None:
            top = SEAT_TOP if ("seat" in p or "mate" in p) else (QT_Z + 4.5 if p["kind"] == "QT" else 12.0)
        pl.rect(x - 0.7, y - 0.7, x + w + 0.7, y + h + 0.7, block=True, height=top)
    used = used_holes()
    for h in b.ALL_HOLES:
        hx, hy = b.pin_xy(h)
        if h in used:
            pl.disc(hx, hy, 1.15, block=True, height=b.BB_Z + 3.0)
        else:
            pl.disc(hx, hy, 0.75, cost=1.5)
    for ref, h1, h2 in leaded_bodies():
        p, q = b.pin_xy(h1), b.pin_xy(h2)
        wide = {"R": 3.4, "C": 3.6, "J": 3.2}[ref[0]]
        if ref == "C1":
            mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            pl.disc(*mid, 3.9, block=True, height=b.BB_Z + 11.0)
        else:
            pl.line(p, q, wide, block=True, height=b.BB_Z + (3.0 if ref[0] == "R" else 8.0))
    for c in b.CONDUCTORS:
        if c[0] == "jumper":
            pl.line(b.pin_xy(c[1]), b.pin_xy(c[2]), 1.6, cost=5.0, height=b.BB_Z + 0.9)
    return pl


# ------------------------------------------------------------------ what gets routed
def wires():
    """(key, kind, end1, end2, note): ends are (x, y, z_exit, free_radius)."""
    out = []

    def hole_end(h, solid=False):
        x, y = b.pin_xy(h)
        return (x, y, b.BB_Z + (3.0 if solid else HOUSING), 1.3)

    def pin_end(ref, pin, free=8.0, z=None):
        x, y = b.pin_xy((ref, pin))
        return (x, y, z if z is not None else 6.0, free)

    for k, c in enumerate(b.CONDUCTORS):
        kind, e1, e2, note = c
        if kind == "dupont":
            ends = []
            for e in (e1, e2):
                if isinstance(e, str):
                    ends.append(hole_end(e))
                else:
                    morpho = e[1].startswith(("CN7", "CN10"))
                    z = (NUC_Z + 1.6 + 2.5 + HOUSING) if morpho else (SOCKET_TOP + HOUSING)
                    ends.append(pin_end(*e, free=1.7, z=z))
            out.append((f"dupont:{k}", "dupont", ends[0], ends[1], note))
        elif kind == "reg":
            out.append((f"reg:{k}", "reg", pin_end(*e1, z=6.0), hole_end(e2, solid=True), note))
    a, z = b.PART_SPANS["W1"][:2]
    out.append(("W1", "lead", pin_end(*a, z=6.0), hole_end(z, solid=True), "the ground tie W1"))
    for pin in ("1", "2"):
        out.append((f"RT1:{pin}", "ntc", (*b.NTC_BEAD, 19.0, 12.0), hole_end(b.ON_BB[("RT1", pin)], solid=True),
                    "NTC lead, bead taped to the pack"))
    for cable, to in (("W2", ("U8", "P1.GND")), ("W3", ("U3", "QT1.GND"))):
        start = hole_end(b.ON_BB[(cable, "H.GND")])
        out.append((cable, "qtcable", start, pin_end(*to, free=7.0, z=b.BB_Z + 6.5),
                    "QT-to-header cable, four header pins on BB1"))
    return out


# ------------------------------------------------------------------ search
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def astar(pl, a, z, box):
    """Cheapest grid path from cell a to cell z inside box (i0, j0, i1, j1)."""
    i0, j0, i1, j1 = box
    cost, blocked = pl.cost, pl.blocked
    TURN = 2.0
    start = (a, -1)
    g = {start: 0.0}
    prev = {}
    heap = [(0.0, 0.0, a, -1)]
    done = set()
    while heap:
        _f, gc, cur, d = heapq.heappop(heap)
        if (cur, d) in done:
            continue
        done.add((cur, d))
        if cur == z:
            path = [cur]
            st = (cur, d)
            while st in prev:
                st = prev[st]
                path.append(st[0])
            return path[::-1]
        ci, cj = cur
        for nd, (di, dj) in enumerate(DIRS):
            ni, nj = ci + di, cj + dj
            if not (i0 <= ni <= i1 and j0 <= nj <= j1) or blocked[ni, nj]:
                continue
            step = (1.4142 if di and dj else 1.0) * (1.0 + cost[ni, nj])
            if d >= 0 and nd != d:
                step += TURN
            ng = gc + step
            st = ((ni, nj), nd)
            if ng < g.get(st, 1e18):
                g[st] = ng
                prev[st] = (cur, d)
                h = math.hypot(ni - z[0], nj - z[1])
                heapq.heappush(heap, (ng + h, ng, (ni, nj), nd))
    return None


def clear_line(pl, p, q, blocked_only=False):
    n = max(2, int(math.dist(p, q) / (G / 4)))
    for k in range(n + 1):
        t = k / n
        i, j = cell(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
        if pl.blocked[i, j] or (not blocked_only and pl.cost[i, j] > 1.0):
            return False
    return True


def shortcut(pl, pts):
    """Drop points while the straight line stays on free, cheap ground (string pulling)."""
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not clear_line(pl, pts[i], pts[j]):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def chaikin(pts, n=3):
    for _ in range(n):
        new = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            new.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            new.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        new.append(pts[-1])
        pts = new
    return pts


def length(pts):
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def route_all():
    """{key: dict(kind, note, plan=[(x, y)], ends=(e1, e2), mm=plan length)}; also a list of problems."""
    pl = base_plan()
    todo = wires()
    todo.sort(key=lambda w: (w[1] != "dupont", math.dist(w[2][:2], w[3][:2])))
    routes, problems = {}, []
    for key, kind, e1, e2, note in todo:
        saved_b = pl.blocked.copy()
        for x, y, _z, free in (e1, e2):
            pl.disc(x, y, free)
            si, sj = pl._sl(x - free, y - free, x + free, y + free)
            X, Y = np.meshgrid(pl.xs[si], pl.ys[sj], indexing="ij")
            pl.blocked[si, sj] &= ~((X - x) ** 2 + (Y - y) ** 2 <= free * free)
        a, z = cell(*e1[:2]), cell(*e2[:2])
        m = int(70 / G)
        box = (max(min(a[0], z[0]) - m, 0), max(min(a[1], z[1]) - m, 0),
               min(max(a[0], z[0]) + m, NX - 1), min(max(a[1], z[1]) + m, NY - 1))
        path = astar(pl, a, z, box)
        if path is None:
            problems.append(f"{key}: no route ({note})")
            pl.blocked = saved_b
            continue
        raw = [e1[:2]] + [xy(*c) for c in path[1:-1]] + [e2[:2]]
        pulled = shortcut(pl, raw)
        for pts in (chaikin(pulled), pulled, raw):          # rounded corners only where they clip nothing
            if all(clear_line(pl, p, q, blocked_only=True) for p, q in zip(pts, pts[1:])):
                break
        pl.blocked = saved_b
        r = WIRE_R[kind]
        for p, q in zip(pts, pts[1:]):                      # later wires keep out of this one's lane
            pl.line(p, q, 2 * r + 0.3, cost=1.5)     # on top of another wire, not beside it
        routes[key] = dict(kind=kind, note=note, plan=pts, ends=(e1, e2), mm=length(pts))
    return routes, problems, pl


def drape(pl, route):
    """3D points (plate frame, z up) for a route: out of the first end's housing, over what is under it,
    into the second end."""
    pts = route["plan"]
    r = WIRE_R[route["kind"]]
    e1, e2 = route["ends"]
    # resample every 1 mm
    dense = [pts[0]]
    for p, q in zip(pts, pts[1:]):
        n = max(1, int(math.dist(p, q) / 1.0))
        dense += [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(1, n + 1)]
    s = [0.0]
    for p, q in zip(dense, dense[1:]):
        s.append(s[-1] + math.dist(p, q))
    L = s[-1] or 1.0
    zs = []
    for (x, y) in dense:
        si, sj = pl._sl(x - 2.0, y - 2.0, x + 2.0, y + 2.0)
        zs.append(float(pl.height[si, sj].max()) + r + 0.3)
    for k in range(1, len(zs)):                             # no steeper than 1:1
        zs[k] = max(zs[k], zs[k - 1] - (s[k] - s[k - 1]))
    for k in range(len(zs) - 2, -1, -1):
        zs[k] = max(zs[k], zs[k + 1] - (s[k + 1] - s[k]))
    rise = 12.0
    for k, sk in enumerate(s):                              # stand up out of each end
        for d, e in ((sk, e1), (L - sk, e2)):
            if d < rise:
                t = d / rise
                zs[k] = max(zs[k], e[2] + 1.0 - (e[2] + 1.0 - zs[k]) * (3 * t * t - 2 * t ** 3))
    out = [(x, y, z) for (x, y), z in zip(dense, zs)]
    return [(e1[0], e1[1], e1[2])] + out + [(e2[0], e2[1], e2[2])]


def report():
    routes, problems, _pl = route_all()
    used = used_holes()
    for key, rt in sorted(routes.items()):
        own = {h for h in b.ALL_HOLES if math.dist(b.pin_xy(h), rt["ends"][0][:2]) < 0.1 or
               math.dist(b.pin_xy(h), rt["ends"][1][:2]) < 0.1}
        for (x, y) in rt["plan"][1:-1]:
            near = [h for h in used - own if math.dist(b.pin_xy(h), (x, y)) < 0.9]
            if near:
                problems.append(f"{key}: passes over used hole {near[0]}")
                break
    return routes, problems


if __name__ == "__main__":
    routes, problems = report()
    for key, rt in sorted(routes.items(), key=lambda kv: kv[0]):
        print(f"{key:10s} {rt['kind']:8s} {rt['mm']:6.0f} mm  {rt['note'][:70]}")
    print("\n".join(problems) if problems else "routes: all clear")
