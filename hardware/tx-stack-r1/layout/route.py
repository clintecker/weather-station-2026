"""Route every soldered wire, jumper and lead on a card the way a person would solder it.

A wire lies flat on its side of the card (top for jumpers and leads, the underside for wires), in straight runs
along a half-pitch grid (1.27 mm: the hole lines and the lines midway between them) with right-angle bends, and
enters and leaves the card at its end holes. Every part's footprint (from its boxes, the same boxes the checks
and renders use) is an obstacle on the side it occupies, inflated by the wire's half-width; every used hole that
is not the wire's own end is an obstacle on both sides (a pin's solder joint or another wire's end). Two routed
wires never run along the same grid edge; insulated wires may cross at right angles; a bare jumper crosses nothing.

A lead from a pad on a breakout leaves the pad straight across its own board to the nearest edge, then drops to
the card. A lead to a part off the card (the charger, the pack) runs to this card's exit point on its front edge.

ROUTES[i] belongs to stack.WIRES[i]: dict(card, side, pts [(x, y, z)], length, ok, why). Cards only; the
backplane's leads are short and drawn straight (build/BACKPLANE.md).
"""
import heapq
import math

import stack as st
from stack import S

G = st.P / 2                                   # 1.27 mm grid
X_MIN, X_MAX = 2.6, st.BW - 2.0                # stay out of the left wall slot and off the right edge
Y_MIN, Y_MAX = 1.2, st.CD - 1.0
NX = [st.X1 + k * G for k in range(-2, 64) if X_MIN <= st.X1 + k * G <= X_MAX]
NY = [k * G for k in range(0, 40) if Y_MIN <= k * G <= Y_MAX]
OD = S.val("wire24")[1]                        # 24 AWG insulated: card wires solid, flying leads stranded
HALF = {"wire": OD / 2 + 0.05, "jumper": 0.35, "lead": OD / 2 + 0.05}   # half-width + clearance; jumper: bare
Z_TOP, Z_BOT = 0.5, -st.BT - 0.5
BUNDLE = 3                                     # insulated leads laid side by side along one grid line, at most
EXIT = {"B4": 64.0}                            # off-card leads leave B4's front edge from here (X), toward the charger


def node_xy(n):
    return NX[n[0]], NY[n[1]]


def nearest(x, y):
    ix = min(range(len(NX)), key=lambda i: abs(NX[i] - x))
    iy = min(range(len(NY)), key=lambda i: abs(NY[i] - y))
    return ix, iy


def on_node(x, y):
    n = nearest(x, y)
    return n if math.dist(node_xy(n), (x, y)) < 0.05 else None


def footprints(card, side):
    """[(ref, x0, y0, x1, y1)] of every part body on this side of the card (keep-outs and service zones excluded)."""
    out = []
    for b, pl in st.placements():
        if b != card:
            continue
        for bx in st.boxes_of(pl):
            if bx.keepout or bx.service:
                continue
            if (side == "top" and bx.z1 > 0.05) or (side == "bottom" and bx.z0 < -0.05):
                out.append((pl["ref"], bx.x0, bx.y0, bx.x1, bx.y1, bx.what))
    return out


def inside(p, r, m=0.0):
    return r[1] - m < p[0] < r[3] + m and r[2] - m < p[1] < r[4] + m


def seg_hits(a, b, r, m=0.0):
    """Does the axis-aligned segment a-b pass through rectangle r grown by m?"""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return x0 < r[3] + m and r[1] - m < x1 and y0 < r[4] + m and r[2] - m < y1


def used_holes(card):
    """{(x, y)} of every hole on the card holding a pin or a conductor end."""
    pts = set()
    for b, pl in st.placements():
        if b == card:
            pts |= {(round(x, 2), round(y, 2)) for x, y in st.pins_of(pl).values()}
    for _k, a, c, _s, _n in st.WIRES:
        for e in (a, c):
            if isinstance(e, str) and e.split(":")[0] == card:
                x, y = st.hole_xy(e.split(":")[1])
                pts.add((round(x, 2), round(y, 2)))
    return pts


def pad_of(e, card):
    for b, pl in st.placements():
        if b == card and pl["ref"] == e[0] and e[1] in st.pads_of(pl):
            bx = [x for x in st.boxes_of(pl) if not x.keepout and x.z1 > 0]
            pcb = [x for x in bx if "PCB" in x.what] or bx
            top = max(x.z1 for x in pcb)
            return st.pads_of(pl)[e[1]], top, pl["ref"]
    return None


class Grid:
    def __init__(self, card, side):
        self.card, self.side = card, side
        self.fp = footprints(card, side)
        self.holes = used_holes(card)
        self.edges = {}          # frozenset(n1, n2) -> [(wire index, kind)]: insulated leads may run bundled
        self.nodes = {}          # node -> list of (wire index, kind, how) how: 'h', 'v', 'end', 'bend'

    def free_node(self, n, kind, ends, own=()):
        x, y = node_xy(n)
        if n in ends:
            return True
        if (round(x, 2), round(y, 2)) in self.holes:
            return False
        m = HALF[kind]
        return not any(inside((x, y), r, m) for r in self.fp if r[0] not in own)

    def free_edge(self, a, b, kind, own=()):
        users = self.edges.get(frozenset((a, b)), [])
        if users and (not kind.startswith("lead") or len(users) >= BUNDLE or
                      any(not k.startswith("lead") for _w, k in users)):
            return False
        pa, pb = node_xy(a), node_xy(b)
        m = HALF[kind] - 0.05
        return not any(seg_hits(pa, pb, r, m) for r in self.fp if r[0] not in own)

    def pass_ok(self, n, how, kind):
        for _w, k2, h2 in self.nodes.get(n, []):
            if kind == "jumper" or k2 == "jumper" or h2 == "end" or how == "end":
                return False
            if kind.startswith("lead") and k2.startswith("lead"):
                continue                     # insulated leads: a bundle may bend together
            if h2 == "bend" or how == "bend" or h2 == how:
                return False
        return True

    def route(self, starts, goals, kind, own=()):
        """Dijkstra over (node, direction) from any start to any goal node; returns the node list or None."""
        goals = set(goals)
        ends = set(starts) | goals
        pq, seen = [], {}
        for s in starts:
            heapq.heappush(pq, (0.0, s, None, (s,)))
        while pq:
            cost, n, d, path = heapq.heappop(pq)
            if n in goals:
                return list(path)
            if seen.get((n, d), 1e9) <= cost:
                continue
            seen[(n, d)] = cost
            for dd, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
                m = (n[0] + dx, n[1] + dy)
                if not (0 <= m[0] < len(NX) and 0 <= m[1] < len(NY)):
                    continue
                if not self.free_node(m, kind, ends, own) or not self.free_edge(n, m, kind, own):
                    continue
                how = "h" if dx else "v"
                bend = d is not None and (d < 2) != (dd < 2)
                if n not in ends and not self.pass_ok(n, "bend" if bend else how, kind):
                    continue
                if m not in ends and self.nodes.get(m) and not self.pass_ok(m, how, kind):
                    continue
                shared = frozenset((n, m)) in self.edges
                c = cost + G + (1.5 if bend else 0.0) + (2.0 if self.nodes.get(m) else 0.0) + (1.0 if shared else 0.0)
                heapq.heappush(pq, (c, m, dd, path + (m,)))
        return None

    def commit(self, path, wi, kind):
        for a, b in zip(path, path[1:]):
            self.edges.setdefault(frozenset((a, b)), []).append((wi, kind))
        for i, n in enumerate(path):
            if i in (0, len(path) - 1):
                how = "end"
            else:
                a, b = path[i - 1], path[i + 1]
                how = "h" if a[1] == b[1] == n[1] else ("v" if a[0] == b[0] == n[0] else "bend")
            self.nodes.setdefault(n, []).append((wi, kind, how))


def pad_exit(grid, pad, kind, ref):
    """Leave a breakout pad straight across its own board to its edge: (via points at the pad's height, the
    grid nodes to drop to). A pad past the card's back edge (the overhanging jack) leaves sideways and then runs
    along the breakout's inner edge back over the card."""
    (x, y), _top, _r = pad
    m = HALF[kind]
    own = [r for r in grid.fp if r[0] == ref]
    best = None
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        t = 0.0
        while t < 40 and any(inside((x + dx * t, y + dy * t), r, m) for r in own):
            t += 0.25
        q = (x + dx * t, y + dy * t)
        via = [q]
        if dx and q[1] > Y_MAX:                       # beside the overhanging breakout: come back over the card
            q = (q[0], Y_MAX)
            via.append(q)
            t += abs(via[0][1] - q[1])
        if not (X_MIN <= q[0] <= X_MAX and Y_MIN <= q[1] <= Y_MAX):
            continue
        if any(inside(v, r, m) for v in via for r in grid.fp if r[0] != ref):
            continue
        if best is None or t < best[0]:
            best = (t, via)
    if best is None:
        return [], []
    via = best[1]
    q = via[-1]
    cand = sorted(((ix, iy) for ix in range(len(NX)) for iy in range(len(NY))
                   if abs(NX[ix] - q[0]) < 3.0 and abs(NY[iy] - q[1]) < 3.0),
                  key=lambda n: math.dist(node_xy(n), q))
    cand = [n for n in cand if grid.free_node(n, kind, set()) and corner(grid, q, n, kind) is not None]
    return via, cand[:4]


def corner(grid, q, n, kind):
    """The right-angle drop from a pad lead's touch-down point q to grid node n: [q, bend, n] (or [q, n] when they
    line up), both legs clear of every footprint; None if neither bend works."""
    p = node_xy(n)
    m = HALF[kind] - 0.05
    if abs(q[0] - p[0]) < 1e-6 or abs(q[1] - p[1]) < 1e-6:
        legs = [[q, p]]
    else:
        legs = [[q, (p[0], q[1]), p], [q, (q[0], p[1]), p]]
    for pts in legs:
        if not any(seg_hits(a, b, r, m) for a, b in zip(pts, pts[1:]) for r in grid.fp):
            return pts
    return None


def route_all():
    """Route in priority order; a wire that fails moves to the front and everything is routed again."""
    first = []
    for _attempt in range(8):
        routes = route_order(first + [i for i in sorted(range(len(st.WIRES)), key=_prio) if i not in first])
        bad = [i for i, r in enumerate(routes) if r and not r["ok"]]
        if not bad:
            break
        first = first + [i for i in bad if i not in first]
    return routes


def route_order(order):
    routes = [None] * len(st.WIRES)
    grids = {}
    bundles = {}            # (card, pad) -> route of the first lead from that pad off the card
    for wi in order:
        kind, a, c, side, note = st.WIRES[wi]
        if side == "copper":
            continue
        cards = {e.split(":")[0] if isinstance(e, str) else st.board_of_ref().get(e[0]) for e in (a, c)} - {None, "BP"}
        if not cards:
            continue
        card = next(iter(cards))
        g = grids.setdefault((card, side), Grid(card, side))
        z = Z_TOP if side == "top" else Z_BOT
        sets, own, offcard, pads = [], [], False, []
        for e in (a, c):
            if isinstance(e, str) and e.split(":")[0] == card:
                sets.append(([nearest(*st.hole_xy(e.split(":")[1]))], None))
            elif isinstance(e, tuple) and pad_of(e, card):
                h = pad_of(e, card)
                via, cand = pad_exit(g, h, kind, h[2])
                own.append(h[2])
                pads.append(e)
                sets.append((cand, ("pad", h, via)))
            else:
                offcard = True
        if offcard and len(pads) == 1 and (card, pads[0]) in bundles:
            r0 = bundles[(card, pads[0])]
            routes[wi] = dict(r0, bundled=True)
            continue
        if offcard:
            goals = [(ix, 0) for ix in range(len(NX)) if 30.0 <= NX[ix] <= EXIT.get(card, 75.0) + 10 and
                     g.free_node((ix, 0), kind, set())]
            sets.append((goals, ("edge",)))
        if len(sets) != 2 or not sets[0][0] or not sets[1][0]:
            routes[wi] = dict(card=card, side=side, pts=[], length=None, ok=False, why="no free grid node next to an end")
            continue
        path = g.route(sets[0][0], sets[1][0], kind, own=tuple(own))
        if path is None:
            routes[wi] = dict(card=card, side=side, pts=[], length=None, ok=False, why="no route around the parts")
            continue
        g.commit(path, wi, kind)
        pts = [(*node_xy(n), z) for n in path]
        for i, (_c, tail) in enumerate(sets):
            if tail is None:
                continue
            if tail[0] == "edge":
                ext = [(pts[-1][0] if i else pts[0][0], 0.0, z)]
            else:
                _t, (pxy, top, _r), via = tail
                hz = top + 0.4
                node = path[0] if i == 0 else path[-1]
                bend = corner(g, via[-1], node, kind)[1:-1]
                ext = [(pxy[0], pxy[1], hz)] + [(v[0], v[1], hz) for v in via] + [(via[-1][0], via[-1][1], z)] + \
                    [(b[0], b[1], z) for b in bend]
            pts = ext + pts if i == 0 else pts + ext[::-1]
        L = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        routes[wi] = dict(card=card, side=side, pts=pts, length=L, ok=True, why="", grid=path, own=own, kind=kind)
        if offcard and len(pads) == 1:
            bundles[(card, pads[0])] = routes[wi]
    return routes


def _prio(i):
    kind, a, c, side, note = st.WIRES[i]
    pa = st.hole_xy(a.split(":")[1]) if isinstance(a, str) and not a.startswith("BP") else None
    pc = st.hole_xy(c.split(":")[1]) if isinstance(c, str) and not c.startswith("BP") else None
    d = abs(pa[0] - pc[0]) + abs(pa[1] - pc[1]) if pa and pc else 50.0
    return ({"jumper": 0, "wire": 1, "lead": 2}[kind], d)



ROUTES = route_all()


def cut_length(i):
    """Cut length of wire i: the routed path plus 10 mm for the stripped ends, rounded up to 5 mm."""
    r = ROUTES[i]
    if not r or r["length"] is None:
        return None
    return int(math.ceil((r["length"] + 10) / 5) * 5)
