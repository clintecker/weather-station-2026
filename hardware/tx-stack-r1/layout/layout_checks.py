"""Machine checks of the physical stack (layout/stack.py) against the schematic model.

  L1 every placed pin lands on a SolderFul hole (within 0.05 mm), and no two pins share a hole;
     every jumper and wire end is a real hole or a real pad, and no hole takes two conductors;
  L2 no two different nets share a strip (the breadboard-pattern trap); an unconnected pin sits on a
     strip of its own;
  L3 the built copper (pins in strips, jumpers, wires, leads, cables, the parts' own ties) is exactly
     the schematic, net for net;
  L4 no battery net touches a strip or a header: the battery loop is soldered leads only;
  L5 the bus: on B2, B3 and B4 the bus nets sit on the same rows (f-j 23..30, model.BUS order), the
     B3 socket and the B4 pins line up hole for hole; B1 carries no bus net through the column;
  L6 parts, keep-outs (plugs, the USB-C console lead, SWD leads) and standoffs do not collide in 3D;
  L7 heights: every gap clears the tallest part below it plus the solder tails above it; the B3-B4
     pins reach the socket; the whole stack fits the box depth.
Run: python3 layout_checks.py   (exit status 0 only if every check passes)
"""
import sys
from collections import defaultdict
from itertools import combinations

import stack as st
from stack import S, model

FAILS, NOTES = [], []
PIN = {(p["ref"], pin[0]): pin for p in model.PARTS for pin in p["pins"]}
NET_OF = {m: n for n, (ms, _a) in model.NETS.items() for m in ms}


def fail(c, m):
    FAILS.append(f"[{c}] {m}")


def near(a, b, tol=0.05):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


HOLE_AT = {}


def hole_at(xy):
    for h in st.ALL_HOLES:
        if near(st.hole_xy(h), xy):
            return h
    return None


def pin_holes():
    """{(board, hole): (ref, pin)} for every placed pin, failing L1 on misses and doubles."""
    out = {}
    for b, pl in st.placements():
        for pin, xy in st.pins_of(pl).items():
            if (pl["ref"], pin) not in PIN:
                fail("L1", f"{b} {pl['ref']} footprint pin {pin} is not a pin of the model")
                continue
            h = hole_at(xy)
            if h is None:
                fail("L1", f"{b} {pl['ref']}.{pin} at ({xy[0]:.2f}, {xy[1]:.2f}) is not on a hole")
                continue
            if (b, h) in out:
                fail("L1", f"{b}:{h} holds {out[(b, h)]} and {pl['ref']}.{pin}")
            out[(b, h)] = (pl["ref"], pin)
    return out


def check_pins_and_ends(ph):
    used = defaultdict(list)
    pads = {(pl["ref"], n) for _b, pl in st.placements() for n in st.pads_of(pl)}
    for kind, a, c, side, note in st.WIRES:
        for e in (a, c):
            if isinstance(e, str):
                b, h = e.split(":")
                if h not in st.ALL_HOLES:
                    fail("L1", f"{kind} end {e} is not a hole")
                if (b, h) in ph:
                    fail("L1", f"{kind} end {e} is a hole already holding {ph[(b, h)]}")
                used[e].append(note)
            elif e not in PIN:
                fail("L1", f"{kind} end {e} is not a model pin")
            elif e[0] in st.board_of_ref() and (e not in pads or PIN[e][3] != "solder"):
                fail("L1", f"{kind} end {e[0]}.{e[1]} is a placed part's pin that is not a solder pad")
    for e, notes in used.items():
        if len(notes) > 1:
            fail("L1", f"hole {e} takes {len(notes)} conductors: {notes}")
    n = sum(len(st.pins_of(pl)) for _b, pl in st.placements())
    NOTES.append(f"{n} pins placed on holes, {len(st.WIRES)} jumpers, wires and leads, {len(st.CABLES)} cable and mating links")


class UF:
    def __init__(self):
        self.p = {}

    def f(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def u(self, a, b):
        self.p[self.f(a)] = self.f(b)


def node(e):
    if isinstance(e, str):
        b, h = e.split(":")
        return ("strip", b, st.strip_of(h))
    return ("pin",) + tuple(e)


def build_copper(ph, ties=True):
    """Union of the built conductors; ties=True adds each part's own copper (model 'ties')."""
    uf = UF()
    for (b, h), (ref, pin) in ph.items():
        uf.u(("pin", ref, pin), ("strip", b, st.strip_of(h)))
    for kind, a, c, side, note in st.WIRES:
        uf.u(node(a), node(c))
    for a, c in st.CABLES:
        uf.u(node(a), node(c))
    if ties:
        for p in model.PARTS:
            for tie in p.get("ties", []):
                for x in tie[1:]:
                    uf.u(("pin", p["ref"], tie[0]), ("pin", p["ref"], x))
    for key in PIN:
        uf.f(("pin",) + key)
    for b in st.BOARDS:
        for h in st.ALL_HOLES:
            uf.f(("strip", b, st.strip_of(h)))
    return uf


def net_classes():
    """Model nets joined by a part's own copper (the EVM ground plane, a cable's conductor): one class each."""
    uf = UF()
    for net in model.NETS:
        uf.f(net)
    for p in model.PARTS:
        for tie in p.get("ties", []):
            nets = [NET_OF[(p["ref"], t)] for t in tie if (p["ref"], t) in NET_OF]
            for n in nets[1:]:
                uf.u(nets[0], n)
    return {n: uf.f(n) for n in model.NETS}


def groups_of(uf):
    g = defaultdict(set)
    for x in list(uf.p):
        g[uf.f(x)].add(x)
    return g


def check_copper(ph):
    cls = net_classes()
    full = build_copper(ph, ties=True)
    # L3: each model net is one piece of copper, and no piece joins two classes
    for net, (members, _a) in model.NETS.items():
        pieces = defaultdict(list)
        for m in members:
            pieces[full.f(("pin",) + m)].append(f"{m[0]}.{m[1]}")
        if len(pieces) != 1:
            fail("L3", f"net {net} is built as {len(pieces)} separate pieces: {list(pieces.values())}")
    for g, items in groups_of(full).items():
        nets = {NET_OF[(x[1], x[2])] for x in items if x[0] == "pin" and (x[1], x[2]) in NET_OF}
        if len({cls[n] for n in nets}) > 1:
            fail("L3", f"nets {sorted(nets)} are joined in the build")
    # L2 and L4 on the conductors alone (a strip is copper, a part's insides are not ours to count)
    bare = build_copper(ph, ties=False)
    tied = ties_of_net()
    for g, items in groups_of(bare).items():
        nets = sorted({eff_net((x[1], x[2])) for x in items if x[0] == "pin" and eff_net((x[1], x[2]))})
        strips = sorted(f"{x[1]}:{x[2]}" for x in items if x[0] == "strip")
        if len(nets) > 1:
            fail("L2" if strips else "L3", f"nets {nets} are joined" + (f" through strips {strips}" if strips else ""))
        loose = [f"{x[1]}.{x[2]}" for x in items if x[0] == "pin" and (x[1], x[2]) not in NET_OF
                 and (x[1], x[2]) not in tied]
        if loose and nets:
            fail("L2", f"unconnected pin(s) {loose} share copper with net {nets} ({strips})")
        if strips and any(model.NETS[n][1].get("battery") for n in nets):
            fail("L4", f"battery net {nets} touches strips {strips}")
        if len(loose) > 1:
            fail("L2", f"unconnected pins {loose} share a strip {strips}")
    merged = defaultdict(list)
    for n, c in cls.items():
        merged[c].append(n)
    NOTES.append("copper = schematic: every net is one piece and no strip carries two nets; joined only inside "
                 "parts: " + "; ".join("+".join(sorted(v)) for v in merged.values() if len(v) > 1))


_TIED = None
_EFF = None


def eff_net(pin):
    """A pin's net, or for an unconnected pin the net it is tied to inside its part (its copper is there)."""
    global _EFF
    if _EFF is None:
        _EFF = dict(NET_OF)
        for p in model.PARTS:
            for tie in p.get("ties", []):
                nets = sorted({NET_OF[(p["ref"], t)] for t in tie if (p["ref"], t) in NET_OF})
                for t in tie:
                    _EFF.setdefault((p["ref"], t), nets[0] if nets else None)
    return _EFF.get(pin)


def ties_of_net():
    """Pins tied inside their part to a pin that is on a net (a QT V+ beside a header VIN)."""
    global _TIED
    if _TIED is None:
        _TIED = set()
        for p in model.PARTS:
            for tie in p.get("ties", []):
                if any((p["ref"], t) in NET_OF for t in tie):
                    _TIED |= {(p["ref"], t) for t in tie}
    return _TIED


def strip_report(ph):
    """{board: {strip: net}} for the drawings and the build list."""
    uf = build_copper(ph, ties=False)
    rep = defaultdict(dict)
    for b in st.BOARDS:
        for h in st.ALL_HOLES:
            s = st.strip_of(h)
            g = uf.f(("strip", b, s))
            nets = {NET_OF[(x[1], x[2])] for x in uf.p if x[0] == "pin" and uf.f(x) == g and (x[1], x[2]) in NET_OF}
            rep[b][s] = next(iter(nets)) if len(nets) == 1 else (None if not nets else "/".join(sorted(nets)))
    return rep


def check_bus(ph):
    rep = strip_report(ph)
    for b in ("B2", "B3", "B4"):
        for i, sig in enumerate(model.BUS):
            row = st.BUS_ROW0 + i
            got = rep[b].get(f"R{row}")
            if got != model.BUS_NET[sig]:
                fail("L5", f"{b} bus row {row} carries {got}, wants {model.BUS_NET[sig]} ({sig})")
    for i in range(8):
        a = [h for (b, h), (r, p) in ph.items() if r == "XS1" and p == str(i + 1)]
        c = [h for (b, h), (r, p) in ph.items() if r == "XP1" and p == str(i + 1)]
        if a != c or not a:
            fail("L5", f"bus pin {i + 1}: B3 socket at {a}, B4 pins at {c}")
    b1 = {s: n for s, n in rep["B1"].items() if s.startswith("R") and st.BUS_ROW0 <= int(s[1:]) <= 30 and n}
    if any(r in ("XS1", "XP1") for (b, _h), (r, _p) in ph.items() if b == "B1"):
        fail("L5", "B1 has bus socket or pins, but no bus column is planned there")
    NOTES.append(f"B1 rows {st.BUS_ROW0}-30 (f-j) are port S4's strips: {b1}")
    NOTES.append(f"bus rows f-j {st.BUS_ROW0}-30 on B2, B3, B4: " + ", ".join(model.BUS) +
                 "; B1 takes only 3V3 (back + rail) and the four QT leads, not the bus column")


def overlap(a, b, tol=0.02):
    return (a.x0 < b.x1 - tol and b.x0 < a.x1 - tol and a.y0 < b.y1 - tol and b.y0 < a.y1 - tol
            and a.z0 < b.z1 - tol and b.z0 < a.z1 - tol)


def board_boxes(b):
    out = []
    for bb, pl in st.placements():
        if bb == b:
            out += [(pl["ref"], x) for x in st.boxes_of(pl)]
    return out


def check_3d():
    for b in st.BOARDS:
        bx = board_boxes(b)
        for (ra, a), (rb, c) in combinations(bx, 2):
            if ra == rb or (a.keepout and c.keepout):
                continue
            if overlap(a, c):
                fail("L6", f"{b}: {a.what} collides with {c.what}")
    # standoffs through each gap, against the lower board's top and the upper board's underside
    r = st.STANDOFF_R
    for (lo, hi), gap in st.GAPS.items():
        for name, sx, sy in st.STANDOFFS:
            cyl = st.Box(sx - r, sy - r, sx + r, sy + r, 0, gap, f"standoff {name}")
            for ref, a in board_boxes(lo):
                if overlap(cyl, a) and circle_hits(sx, sy, r, a):
                    fail("L6", f"{lo}-{hi} standoff at {name} hits {a.what}")
    NOTES.append("standoffs: " + ", ".join(f"{n} ({x:.2f}, {y:.2f})" for n, x, y in st.STANDOFFS) +
                 f"; hex corner radius {r:.2f} mm")


def circle_hits(cx, cy, r, a):
    nx, ny = min(max(cx, a.x0), a.x1), min(max(cy, a.y0), a.y1)
    return (nx - cx) ** 2 + (ny - cy) ** 2 < r * r


def tallest(b, keepouts=False):
    zs = [(x.z1, x.what) for _r, x in board_boxes(b) if (keepouts or not x.keepout) and not x.what.startswith("XS1")
          and not getattr(x, "service", False)]
    return max(zs) if zs else (0.0, "nothing")


def check_heights():
    t, tl, cl = S.val("sb_t"), S.val("tails"), S.val("clear")
    order = st.BOARDS
    for (lo, hi), gap in st.GAPS.items():
        top, what = tallest(lo, keepouts=True)
        need = top + tl + cl
        brief = st.BRIEF_GAPS[(lo, hi)]
        verdict = "ok" if need <= gap else "CLASH"
        NOTES.append(f"gap {lo}-{hi} {gap:g} mm: tallest below {top:.1f} mm ({what}) + tails {tl:g} + clearance {cl:g}"
                     f" = {need:.1f} mm, {verdict}; the brief's {brief:g} mm " +
                     ("fits" if need <= brief else f"does not (short by {need - brief:.1f} mm)"))
        if need > gap:
            fail("L7", f"gap {lo}-{hi} {gap} mm < {need:.1f} mm needed by {what}")
    gap34 = st.GAPS[("B3", "B4")]
    ins = S.val("pin_below") - (gap34 - S.val("socket_h"))
    if ins < 5.0 or S.val("socket_h") > gap34:
        fail("L7", f"B4 pins reach {ins:.1f} mm into the B3 socket (want >= 5)")
    NOTES.append(f"B3-B4 bus: socket {S.val('socket_h'):g} mm, pins {S.val('pin_below'):g} mm below B4, insertion {ins:.1f} mm")
    top4, what4 = tallest("B4")
    total = S.val("floor") + 4 * t + sum(st.GAPS.values()) + top4
    inside = S.val("box_depth_out") - 2 * S.val("box_wall")
    NOTES.append(f"stack: floor {S.val('floor'):g} [TBD] + 4 x {t:g} + gaps {'/'.join(f'{g:g}' for g in st.GAPS.values())}"
                 f" + {top4:.1f} above B4 ({what4}) = {total:.1f} mm; box 75 outside, about {inside:g} inside [TBD]")
    if total > inside:
        fail("L7", f"stack {total:.1f} mm is deeper than the box inside {inside:g} mm")
    for b in st.BOARDS:
        bx = [x for _r, x in board_boxes(b) if "jack" in x.what]
        for x in bx:
            if x.y0 > 0:
                fail("L7", f"{b}: {x.what} front at Y {x.y0:.2f} does not reach the front edge")
        if bx:
            NOTES.append(f"{b}: jacks overhang the front edge by {-min(x.y0 for x in bx):.2f} mm")
    return total


def run():
    ph = pin_holes()
    check_pins_and_ends(ph)
    check_copper(ph)
    check_bus(ph)
    check_3d()
    total = check_heights()
    return ph, total


def main():
    run()
    for n in NOTES:
        print("note ", n)
    for f in FAILS:
        print("FAIL ", f)
    print(f"layout {'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
