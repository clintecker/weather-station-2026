"""Route every soldered wire, jumper and lead on a card the way a person would solder it.

A wire lies flat on its side of the card (top for jumpers and leads, the underside for wires), in straight runs
along a half-pitch grid (1.27 mm: the hole lines and the lines midway between them) with right-angle bends, and
enters and leaves the card at its end holes. Every part's footprint (from its boxes, the same boxes the checks
and renders use) is an obstacle on the side it occupies, inflated by the wire's half-width; every used hole that
is not the wire's own end is an obstacle on both sides (a pin's solder joint or another wire's end). Two routed
wires never run along the same grid edge; insulated wires may cross at right angles; a bare jumper crosses nothing.
Two insulated runs never lie side by side on neighbouring grid lines (1.27 apart, less than the 1.45 insulation: one
would hide under the other); parallel runs are 2.54 or more apart. Insulated leads may instead share one grid line,
BUNDLE at most (laid together on purpose). A wire's last grid step into its own end hole is its stripped end (bare
0.5 mm copper: 0.25 + 0.725 < 1.27), so it may lie beside another run (close_runs, L8).

A person lays a wire "across, then straight up": every bend costs BEND (mm of extra wire it is worth avoiding), so
a route has as few bends as the parts allow. Running on the midway lines between hole rows (a free hole under a
wire costs OVER_HOLE) is only a weak tiebreak.

Any rail hole: a front rail (F+ / F-) is one continuous strip, so a wire end named on a rail (stack.WIRES "B1:F+1")
may end at any free hole of that rail; the router picks the one that gives the best route. A rail hole is free when
no pin or other end uses it, no routed wire lies on it, and no underside wire passes within CLEAR of it. WIRES (this
module) is stack.WIRES with every rail end replaced by the hole actually used: the build sheets, drawings, renders
and checks read their ends from it; used_holes() counts the actual holes.

A lead from a pad on a breakout leaves the pad straight across its own board to the nearest edge, then drops to
the card. A lead to a part off the card (the charger, the pack) runs to this card's exit point on its front edge.

Order: each card is routed on its own, TRIES orders (priority, then seeded shuffles); in each, a wire that finds
no clean route gets a rip-up-and-reroute search (route_order, LNS); the order with the fewest failures, then the
fewest side-by-side steps, then the least wire + BEND per bend, wins. Routing takes minutes, so ROUTES is cached in
layout/__pycache__ under a hash of every input (_routes).

ROUTES[i] belongs to stack.WIRES[i]: dict(card, side, pts [(x, y, z)], length, ok, why, grid, ends (as built), ...).
Cards only; the backplane's leads are short and drawn straight (build/BACKPLANE.md).
"""
import hashlib
import heapq
import math
import os
import pathlib
import pickle
import random

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
BUNDLE = 4                                     # insulated leads laid together along one grid line, at most
                                               # (4: B1's J11 leads 2-5 share the front-edge run; 3 put one beside)
FILLET = S.val("fillet_clear")                 # an underside wire's centre keeps OD/2 + this from any used hole
CLEAR = OD / 2 + FILLET                        # but its own end holes: the joint and its fillet stay bare
EXIT = {"B4": 64.0}                            # off-card leads leave B4's front edge from here (X), toward the charger
BEND = 12.0                                    # a bend costs as much as 12 mm of extra wire: few bends, human routes
# Cards where the router finds no route without side-by-side runs, left open for Clint: {card: (mm at most, why)}.
# L8 lists every such run as OPEN and fails if the card's total grows past the mm (and on every other card).
CLOSE_OPEN = {"B3": (6.35, "21 underside wires; wires 45 (3.3 V to the mini), 48, 56 and 62 cross the a-b-c rows "
                           "through the few columns free of used holes (1-3, 9-11, 17-18) and meet there; no order "
                           "or rip-up search found a clean route (best 4-6 steps of 1.27)")}
OVER_HOLE = 0.15                               # a free hole under a wire (weak tiebreak toward the midway lines)


def rail_of(e):
    """'F+' / 'F-' if the card end e ('B1:F+1') is on a front rail, else None."""
    if not isinstance(e, str) or e.startswith("BP:"):
        return None
    h = e.split(":")[1]
    return next((r for r in st.RAIL_Y if h.startswith(r)), None)


def col_of(x):
    return round((x - st.X1) / st.P) + 1


HOLE_X = {round(st.X(r), 2) for r in range(1, 31)}
HOLE_Y = {round(y, 2) for y in list(st.LETTER_Y.values()) + list(st.RAIL_Y.values())}


def is_hole(n):
    x, y = node_xy(n)
    return round(x, 2) in HOLE_X and round(y, 2) in HOLE_Y


def neighbours(a, b):
    """The two grid edges parallel to a-b, one grid step either side."""
    if a[1] == b[1]:
        return [frozenset(((a[0], a[1] + s), (b[0], b[1] + s))) for s in (-1, 1)]
    return [frozenset(((a[0] + s, a[1]), (b[0] + s, b[1]))) for s in (-1, 1)]


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
    """[(ref, x0, y0, x1, y1, what, z0)] of every part body on this side of the card (keep-outs and service zones excluded)."""
    out = []
    for b, pl in st.placements():
        if b != card:
            continue
        for bx in st.boxes_of(pl):
            if bx.keepout or bx.service:
                continue
            if (side == "top" and bx.z1 > 0.05) or (side == "bottom" and bx.z0 < -0.05):
                out.append((pl["ref"], bx.x0, bx.y0, bx.x1, bx.y1, bx.what, bx.z0))
    return out


def inside(p, r, m=0.0):
    return r[1] - m < p[0] < r[3] + m and r[2] - m < p[1] < r[4] + m


def seg_hits(a, b, r, m=0.0):
    """Does the axis-aligned segment a-b pass through rectangle r grown by m?"""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return x0 < r[3] + m and r[1] - m < x1 and y0 < r[4] + m and r[2] - m < y1


def used_holes(card, fixed_only=False):
    """{(x, y)} of every hole on the card holding a pin or a conductor end (the routed rail holes, from WIRES);
    fixed_only: pins and the ends that are not on a rail (before routing picks the rail holes)."""
    pts = set()
    for b, pl in st.placements():
        if b == card:
            pts |= {(round(x, 2), round(y, 2)) for x, y in st.pins_of(pl).values()}
    for _k, a, c, _s, _n in (st.WIRES if fixed_only else WIRES):
        for e in (a, c):
            if fixed_only and rail_of(e):
                continue
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


_FP_CACHE = {}


class Grid:
    def __init__(self, card, side, extra=()):
        self.card, self.side = card, side
        self.fp = footprints(card, side)
        self.holes = set()
        # footprint-only verdicts, shared by every routing order: (node, kind, own) / (a, b, kind, own) -> free
        self._fpn, self._fpe = _FP_CACHE.setdefault((card, side), ({}, {}))
        self.near = {}           # underside: node -> the used holes whose fillet it is too close to
        for h in used_holes(card, fixed_only=True) | set(extra):
            self.add_hole(h)
        self.edges = {}          # frozenset(n1, n2) -> [(wire index, kind)]: insulated leads may run bundled
        self.bare = set()        # (wire index, edge): a wire's last step into its end hole (stripped, no insulation)
        self.nodes = {}          # node -> list of (wire index, kind, how) how: 'h', 'v', 'end', 'bend'

    def remove_hole(self, h):
        self.holes.discard(h)
        for n in [n for n, hs in self.near.items() if h in hs]:
            self.near[n].discard(h)
            if not self.near[n]:
                del self.near[n]

    def add_hole(self, h):
        """A hole now holds a pin or an end: an obstacle, and on the underside its fillet zone too."""
        self.holes.add(h)
        if self.side == "bottom":
            ix, iy = nearest(*h)
            for jx in range(max(0, ix - 2), min(len(NX), ix + 3)):
                for jy in range(max(0, iy - 2), min(len(NY), iy + 3)):
                    if math.dist(h, node_xy((jx, jy))) < CLEAR - 1e-6:
                        self.near.setdefault((jx, jy), set()).add(h)

    def free_node(self, n, kind, ends, own=()):
        x, y = node_xy(n)
        if n in ends:
            return True
        if (round(x, 2), round(y, 2)) in self.holes:
            return False
        hs = self.near.get(n)
        if hs and not hs <= {tuple(round(v, 2) for v in node_xy(e)) for e in ends}:
            return False                 # over another joint's solder fillet
        k = (n, kind, own)
        if k not in self._fpn:
            m = HALF[kind]
            self._fpn[k] = not any(inside((x, y), r, m) for r in self.fp if r[0] not in own)
        return self._fpn[k]

    def free_edge(self, a, b, kind, own=()):
        users = self.edges.get(frozenset((a, b)), [])
        if users and (not kind.startswith("lead") or len(users) >= BUNDLE or
                      any(not k.startswith("lead") for _w, k in users)):
            return False
        k = (a, b, kind, own)
        if k not in self._fpe:
            pa, pb = node_xy(a), node_xy(b)
            m = HALF[kind] - 0.05
            self._fpe[k] = not any(seg_hits(pa, pb, r, m) for r in self.fp if r[0] not in own)
        return self._fpe[k]

    def pass_ok(self, n, how, kind):
        for _w, k2, h2 in self.nodes.get(n, []):
            if kind == "jumper" or k2 == "jumper" or h2 == "end" or how == "end":
                return False
            if kind.startswith("lead") and k2.startswith("lead"):
                continue                     # insulated leads: a bundle may bend together
            if h2 == "bend" or how == "bend" or h2 == how:
                return False
        return True

    def route(self, starts, goals, kind, own=(), strict=True, term=(), holes=()):
        """Dijkstra over (node, direction) from any start to any goal node; returns the node list or None.
        term: start nodes a path may only begin at, never pass through (the other free holes of a rail).
        holes: the start and goal nodes that are holes (the wire's last step into one is its bare stripped end).
        strict: no insulated run side by side with another (1.27 apart, see close_runs); otherwise allowed at a
        cost (the last resort in route_order: L8 fails on it)."""
        goals = set(goals)
        starts = set(starts)
        ends = starts | goals
        term = set(term) & starts
        holes = set(holes)
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
                if m in term or not self.free_node(m, kind, ends, own) or not self.free_edge(n, m, kind, own):
                    continue
                how = "h" if dx else "v"
                bend = d is not None and (d < 2) != (dd < 2)
                if n not in ends and not self.pass_ok(n, "bend" if bend else how, kind):
                    continue
                if m not in ends and self.nodes.get(m) and not self.pass_ok(m, how, kind):
                    continue
                shared = frozenset((n, m)) in self.edges
                side_by = not ((n in starts or m in goals) and {n, m} & holes) and self.side_by(n, m, kind)
                if side_by and strict:
                    continue                 # never side by side with another insulated run
                c = cost + G + (BEND if bend else 0.0) + (2.0 if self.nodes.get(m) else 0.0) + (1.0 if shared else 0.0) \
                    + (OVER_HOLE if m not in ends and is_hole(m) else 0.0) \
                    + (50.0 if side_by else 0.0)
                heapq.heappush(pq, (c, m, dd, path + (m,)))
        return None

    def side_by(self, n, m, kind):
        """The nodes of the insulated runs on the grid lines 1.27 either side of edge n-m (empty if none, or a jumper)."""
        if kind == "jumper":
            return set()
        out = set()
        for e in neighbours(n, m):
            if any(k2 != "jumper" and (w2, e) not in self.bare for w2, k2 in self.edges.get(e, [])):
                out |= set(e)
        return out

    def commit(self, path, wi, kind, holes=(True, True)):
        for e in bare_edges(path, holes):
            self.bare.add((wi, e))
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
    (x, y), top, _r = pad
    m = HALF[kind]
    own = [r for r in grid.fp if r[0] == ref]
    hdr = st.model.HEADERS[grid.card]
    # the bus header runs along the back edge (column j, rows 1-30): a lead from the overhanging breakout (its pads
    # above the header and the socket) crosses it in the air at the pad's height and touches down in front of it
    y_back = min([Y_MAX] + [r[2] - m for r in grid.fp if r[0] == hdr])
    # the parts standing on the breakout's own top (its sockets, terminal footprints): the lead lies on the board
    # and goes round them, with at most one jog sideways off the pad into a channel between them
    tall = [r for r in own if r[6] >= top - 0.05 and not inside((x, y), r)]   # not the pad's own joint zone
    best = None
    for (dx, dy), o in ((d, o) for d in ((-1, 0), (1, 0), (0, -1), (0, 1))
                        for o in (0.0, 1.27, -1.27, 1.905, -1.905, 2.54, -2.54, 3.175, -3.175)):
        j = (x + dy * o, y + dx * o)                  # the jog runs across the exit direction
        t = 0.0
        while t < 40 and any(inside((j[0] + dx * t, j[1] + dy * t), r, m) for r in own):
            t += 0.25
        q = (j[0] + dx * t, j[1] + dy * t)
        if any(seg_hits(a, b, r, m + 0.6) for a, b in (((x, y), j), (j, q)) for r in tall):   # no squeezing between sockets
            continue
        via = ([j] if o else []) + [q]
        t += abs(o)
        if dx and q[1] > y_back:                      # beside the overhanging breakout: come back over the card
            q = (q[0], y_back)
            via.append(q)
            t += abs(via[-2][1] - q[1])
        if not (X_MIN <= q[0] <= X_MAX and Y_MIN <= q[1] <= Y_MAX):
            continue
        if any(inside(v, r, m) for v in via for r in grid.fp if r[0] != ref and not (r[0] == hdr and v is not q)):
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


TRIES = 4                                     # routing orders tried per card (deterministic: seeded by the card)


def card_of(wi):
    """The card wire wi is routed on, or None (the backplane's copper side, or nothing on a card)."""
    kind, a, c, side, note = st.WIRES[wi]
    if side == "copper":
        return None
    cards = {e.split(":")[0] if isinstance(e, str) else st.board_of_ref().get(e[0]) for e in (a, c)} - {None, "BP"}
    return next(iter(cards)) if cards else None


def n_bends(path):
    return sum(1 for a, b, c in zip(path, path[1:], path[2:]) if (a[0] == b[0]) != (b[0] == c[0]))


def bare_edges(path, holes):
    """The grid edges of a path that are its last step into an end hole: the stripped end, bare copper (0.5 mm),
    which clears an insulated run on the next line (0.25 + 0.725 < 1.27)."""
    out = []
    if len(path) > 1 and holes[0]:
        out.append(frozenset(path[:2]))
    if len(path) > 1 and holes[1]:
        out.append(frozenset(path[-2:]))
    return out


def close_runs(routes, idx):
    """{(i, j, card, side): {frozenset(edge of one, edge of the other)}}: insulated runs of wires i < j on neighbouring grid lines 1.27
    apart (closer than the insulation OD), on the same side of the same card; a wire's bare stripped step into
    its own end hole does not count; jumpers (bare) and the bundled copies of a lead are left out."""
    seen = {}
    for i in idx:
        r = routes[i]
        if not r or not r.get("ok") or not r.get("grid") or r.get("bundled") or r["kind"] == "jumper":
            continue
        bare = set(bare_edges(r["grid"], r.get("holes", (True, True))))
        for a, b in zip(r["grid"], r["grid"][1:]):
            e = frozenset((a, b))
            if e not in bare:
                seen.setdefault((r["card"], r["side"], e), set()).add(i)
    out = {}
    for (card, side, e), ws in seen.items():
        for nb in neighbours(*tuple(e)):
            for j in seen.get((card, side, nb), ()):
                for i in ws:
                    if j not in ws:
                        out.setdefault((min(i, j), max(i, j), card, side), set()).add(frozenset((e, nb)))
    return out


def score(routes, idx):
    """(failed wires, side-by-side grid steps, cost): cost = wire laid + BEND per bend."""
    fails = sum(1 for i in idx if routes[i] and not routes[i]["ok"])
    cost = sum(r["length"] + BEND * n_bends(r["grid"]) for r in (routes[i] for i in idx)
               if r and r["ok"] and not r.get("bundled"))
    return fails, sum(len(v) for v in close_runs(routes, idx).values()), cost


def route_all():
    """Route each card on its own: the priority order, then that order with the wires that failed moved to the
    front, then shuffled orders (jumpers, wires, leads kept in that order); keep the order with the fewest failures
    and the least wire + bends."""
    routes = [None] * len(st.WIRES)
    by_card = {}
    for i in range(len(st.WIRES)):
        if card_of(i):
            by_card.setdefault(card_of(i), []).append(i)
    for card, idx in sorted(by_card.items()):
        base = sorted(idx, key=_prio)
        rng = random.Random(card)
        best, first, order = None, [], base
        for t in range(TRIES):
            rs = route_order(order)
            sc = score(rs, idx)
            if best is None or sc < best[0]:
                best = (sc, rs)
            bad = [i for i in idx if rs[i] and not rs[i]["ok"]]
            if t < 6 and bad:
                first = first + [i for i in bad if i not in first]
                order = first + [i for i in base if i not in first]
            else:
                groups = {}
                for i in base:
                    groups.setdefault(st.WIRES[i][0], []).append(i)
                order = []
                for k in ("jumper", "wire", "lead"):
                    g = groups.get(k, [])
                    rng.shuffle(g)
                    order += g
        for i in idx:
            routes[i] = best[1][i]
    return routes


def rail_holes(grids, extra, card, side, e, kind):
    """The grid nodes of every free hole on end e's rail: no pin or end in it, no routed wire on it (either side),
    no underside wire within CLEAR of it, not under a breakout spacer, clear of this side's parts (but the named one)."""
    rail = rail_of(e)
    g = grids[(card, side)]
    named = nearest(*st.hole_xy(e.split(":")[1]))
    spacers = [bx for b, pl in st.placements() if b == card for bx in st.boxes_of(pl) if "spacer" in bx.what]
    out = []
    for col in range(1, 31):
        xy = st.hole_xy(f"{rail}{col}")
        h = (round(xy[0], 2), round(xy[1], 2))
        n = nearest(*xy)
        if h in g.holes or h in extra.get(card, ()) or any(bx.x0 < xy[0] < bx.x1 and bx.y0 < xy[1] < bx.y1 for bx in spacers):
            continue
        if any(n in gg.nodes for (c2, _s2), gg in grids.items() if c2 == card):
            continue
        if any(math.dist(h, node_xy(m)) < CLEAR - 1e-6 for (c2, s2), gg in grids.items() if c2 == card and s2 == "bottom"
               for m in gg.nodes):
            continue
        if n != named and not g.free_node(n, kind, set()):
            continue
        out.append(n)
    return out


def built_end(e, n):
    """The end actually used: a rail end becomes the rail hole at grid node n."""
    if not rail_of(e):
        return e
    return f"{e.split(':')[0]}:{rail_of(e)}{col_of(NX[n[0]])}"


TRACE = False
LNS = 600                                      # rip-up-and-reroute moves per routing order, while a wire fails
LNS_RIP = 5                                    # wires ripped up per move, at most


def route_order(order):
    """Route the wires in this order, each against the ones before it and never side by side with another; then,
    while some wire finds no such route, rip up a few routed wires on its card side, route the failed one first
    and the others after it, and keep the change unless more wires fail (a seeded large-neighbourhood search,
    LNS moves). A wire still without a clean route at the end is routed side by side (L8 then fails on it)."""
    routes = [None] * len(st.WIRES)
    grids, extra, bundles = {}, {}, {}      # extra: card -> {(x, y)} rail holes picked; bundles: (card, pad) -> wire
    for wi in order:
        route_one(wi, routes, grids, extra, bundles)
    rng = random.Random(len(order))
    for _it in range(LNS):
        failed = [wi for wi in order if routes[wi] and not routes[wi]["ok"] and not routes[wi].get("bundled")]
        if not failed:
            break
        f = rng.choice(failed)
        card, side = card_of(f), st.WIRES[f][3]
        pool = [w for w in order if w != f and routes[w] and routes[w]["ok"] and not routes[w].get("bundled")
                and routes[w]["card"] == card and routes[w]["side"] == side and routes[w]["kind"] != "jumper"]
        if not pool:
            continue
        rip = rng.sample(pool, rng.randint(1, min(LNS_RIP, len(pool))))
        group = [f] + rip
        old = {w: routes[w] for w in group}
        before = sum(1 for w in group if not old[w]["ok"])
        for w in rip:
            unroute(w, routes, grids, extra)
        routes[f] = None
        rng.shuffle(rip)
        for w in [f] + rip:
            route_one(w, routes, grids, extra, bundles)
        after = sum(1 for w in group if not routes[w]["ok"])
        if TRACE:
            print("lns", _it, f, rip, before, "->", after)
        if after > before:                               # worse: put the old routes back
            for w in group:
                if routes[w]["ok"]:
                    unroute(w, routes, grids, extra)
            for w in group:
                if old[w]["ok"]:
                    recommit(w, old[w], routes, grids, extra)
                else:
                    routes[w] = old[w]
    for wi in order:                                     # no clean route: lay it side by side (L8 fails on it)
        if routes[wi] and not routes[wi]["ok"] and not routes[wi].get("bundled"):
            routes[wi] = None
            route_one(wi, routes, grids, extra, bundles, strict=False)
    # then the same moves to shorten what runs side by side (each step of it costs 50 mm in the reroute)
    for _it in range(LNS if close_runs(routes, order) else 0):
        close = close_runs(routes, order)
        if not close:
            break
        f = rng.choice(sorted({w for k in close for w in k[:2]}))
        card, side = card_of(f), st.WIRES[f][3]
        pool = [w for w in order if w != f and routes[w] and routes[w]["ok"] and not routes[w].get("bundled")
                and routes[w]["card"] == card and routes[w]["side"] == side and routes[w]["kind"] != "jumper"]
        rip = rng.sample(pool, rng.randint(1, min(LNS_RIP, len(pool)))) if pool else []
        group = [f] + rip
        old = {w: routes[w] for w in group}
        before = score(routes, order)
        for w in group:
            unroute(w, routes, grids, extra)
        rng.shuffle(rip)
        for w in [f] + rip:
            route_one(w, routes, grids, extra, bundles, strict=False)
        after = score(routes, order)
        if after > before:
            for w in group:
                if routes[w]["ok"]:
                    unroute(w, routes, grids, extra)
            for w in group:
                if old[w]["ok"]:
                    recommit(w, old[w], routes, grids, extra)
                else:
                    routes[w] = old[w]
    for wi in order:                                    # bundled leads follow their first lead's final route
        r = routes[wi]
        if r and r.get("bundled"):
            routes[wi] = dict(routes[r["master"]], bundled=True, master=r["master"], ends=r["ends"])
    return routes


def side_by_edges(routes, order):
    """{(card, side, edge)} of every grid edge in a side-by-side run (close_runs)."""
    return {(k[2], k[3], e) for k, ps in close_runs(routes, order).items() for p in ps for e in p}


def unroute(wi, routes, grids, extra):
    r = routes[wi]
    g = grids[(r["card"], r["side"])]
    for a, b in zip(r["grid"], r["grid"][1:]):
        e = frozenset((a, b))
        g.edges[e] = [u for u in g.edges[e] if u[0] != wi]
        if not g.edges[e]:
            del g.edges[e]
    g.bare = {u for u in g.bare if u[0] != wi}
    for n in set(r["grid"]):
        g.nodes[n] = [u for u in g.nodes[n] if u[0] != wi]
        if not g.nodes[n]:
            del g.nodes[n]
    for h in r.get("rail", ()):
        extra[r["card"]].discard(h)
        for (c2, _s2), gg in grids.items():
            if c2 == r["card"]:
                gg.remove_hole(h)
    routes[wi] = None


def recommit(wi, r, routes, grids, extra):
    grids[(r["card"], r["side"])].commit(r["grid"], wi, r["kind"], r["holes"])
    for h in r.get("rail", ()):
        extra.setdefault(r["card"], set()).add(h)
        for (c2, _s2), gg in grids.items():
            if c2 == r["card"]:
                gg.add_hole(h)
    routes[wi] = r


def route_one(wi, routes, grids, extra, bundles, strict=True):
    """Route wire wi against everything already on its card and commit it: routes[wi] = dict(card, side, pts,
    length, ok, why, grid, own, kind, ends (as built), rail (the rail holes it took))."""
    kind, a, c, side, note = st.WIRES[wi]
    card = card_of(wi)
    if card is None:
        return
    for s2 in ("top", "bottom"):
        if (card, s2) not in grids:
            grids[(card, s2)] = Grid(card, s2, extra.get(card, ()))
    g = grids[(card, side)]
    z = Z_TOP if side == "top" else Z_BOT
    sets, own, offcard, pads, term = [], [], False, [], []
    for e in (a, c):
        if rail_of(e) and e.split(":")[0] == card:
            cand = rail_holes(grids, extra, card, side, e, kind)
            term += cand
            sets.append((cand, None))
        elif isinstance(e, str) and e.split(":")[0] == card:
            sets.append(([nearest(*st.hole_xy(e.split(":")[1]))], None))
        elif isinstance(e, tuple) and pad_of(e, card):
            h = pad_of(e, card)
            via, cand = pad_exit(g, h, kind, h[2])
            own.append(h[2])
            pads.append(e)
            sets.append((cand, ("pad", h, via)))
        else:
            offcard = True
    if offcard and len(pads) == 1 and (card, pads[0]) in bundles and bundles[(card, pads[0])] != wi:
        m = bundles[(card, pads[0])]
        routes[wi] = dict(routes[m], bundled=True, master=m, ends=(a, c))
        return
    if offcard:
        goals = [(ix, 0) for ix in range(len(NX)) if 30.0 <= NX[ix] <= EXIT.get(card, 75.0) + 10 and
                 g.free_node((ix, 0), kind, set())]
        sets.append((goals, ("edge",)))
    if len(sets) != 2 or not sets[0][0] or not sets[1][0]:
        routes[wi] = dict(card=card, side=side, pts=[], length=None, ok=False, why="no free grid node next to an end")
        return
    hf = (sets[0][1] is None, sets[1][1] is None)          # which ends are holes (not a pad, not the card edge)
    holes = [n for (cand, tail) in sets if tail is None for n in cand]
    kw = dict(own=tuple(own), term=term, holes=holes)
    path = g.route(sets[0][0], sets[1][0], kind, strict=strict, **kw)
    if path is None:
        routes[wi] = dict(card=card, side=side, pts=[], length=None, ok=False, why="no route around the parts")
        return
    g.commit(path, wi, kind, hf)
    built, rail = [a, c], []
    for k, (e, n) in enumerate(((a, path[0]), (c, path[-1]))):
        if rail_of(e) and e.split(":")[0] == card:
            built[k] = built_end(e, n)
            xy = st.hole_xy(built[k].split(":")[1])
            h = (round(xy[0], 2), round(xy[1], 2))
            rail.append(h)
            extra.setdefault(card, set()).add(h)
            for (c2, _s2), gg in grids.items():
                if c2 == card:
                    gg.add_hole(h)
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
    routes[wi] = dict(card=card, side=side, pts=pts, length=L, ok=True, why="", grid=path, own=own, kind=kind,
                      ends=tuple(built), rail=rail, holes=hf)
    if offcard and len(pads) == 1:
        bundles[(card, pads[0])] = wi


def _prio(i):
    kind, a, c, side, note = st.WIRES[i]
    pa = st.hole_xy(a.split(":")[1]) if isinstance(a, str) and not a.startswith("BP") else None
    pc = st.hole_xy(c.split(":")[1]) if isinstance(c, str) and not c.startswith("BP") else None
    d = abs(pa[0] - pc[0]) + abs(pa[1] - pc[1]) if pa and pc else 50.0
    return ({"jumper": 0, "wire": 1, "lead": 2}[kind], d)



def _inputs_key():
    """A hash of everything routing reads: this file, the wires and every part's pins, pads and boxes."""
    parts = [(b, pl["ref"], sorted(st.pins_of(pl).items()), sorted(st.pads_of(pl).items()),
              [(x.x0, x.y0, x.z0, x.x1, x.y1, x.z1, x.what, x.keepout, x.service) for x in st.boxes_of(pl)])
             for b, pl in st.placements()]
    blob = repr((pathlib.Path(__file__).read_text(), st.WIRES, parts, st.model.HEADERS, OD, FILLET)).encode()
    return hashlib.sha256(blob).hexdigest()


def _routes():
    """route_all(), cached in layout/__pycache__ (git-ignored) under _inputs_key(): routing takes minutes and
    every script that imports this module would otherwise redo it."""
    path = pathlib.Path(__file__).parent / "__pycache__" / "route-cache.pkl"
    key = _inputs_key()
    try:
        k, routes = pickle.loads(path.read_bytes())
        if k == key:
            return routes
    except Exception:          # no cache yet, or an unreadable one: route
        pass
    routes = route_all()
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(pickle.dumps((key, routes)))
    return routes


ROUTES = _routes() if not os.environ.get("ROUTE_LAZY") else None
# stack.WIRES with each rail end at the hole the router used (the build sheets, drawings, renders and checks read this)
WIRES = None if ROUTES is None else [(k, *(ROUTES[i]["ends"] if ROUTES[i] and ROUTES[i].get("ends") else (a, c)), s, n)
         for i, (k, a, c, s, n) in enumerate(st.WIRES)]


def stats():
    """(insulated wires lying over free holes: {wire index: [hole nodes]}, side-by-side runs closer than the
    insulation (close_runs): sorted [(i, j, card, side, mm)]) after routing."""
    over = {}
    for i, r in enumerate(ROUTES):
        if not r or not r.get("ok") or not r.get("grid") or r["kind"] == "jumper" or r.get("bundled"):
            continue
        hs = [n for n in r["grid"][1:-1] if is_hole(n)]
        if hs:
            over[i] = hs
    pairs = close_runs(ROUTES, range(len(ROUTES)))
    return over, sorted(k + (round(len(v) * G, 2),) for k, v in pairs.items())


def cut_length(i):
    """Cut length of wire i: the routed path plus 10 mm for the stripped ends, rounded up to 5 mm."""
    r = ROUTES[i]
    if not r or r["length"] is None:
        return None
    return int(math.ceil((r["length"] + 10) / 5) * 5)
