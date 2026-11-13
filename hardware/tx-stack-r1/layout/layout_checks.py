"""Machine checks of the card cage (layout/stack.py) against the schematic model.

  L1 every placed pin lands on a SolderFul hole (cards; the back rails are snapped off) or a padboard hole
     (backplane), no two pins share a hole; every jumper, wire and lead end is a real hole or a real pad; no
     hole takes two conductors; nothing is soldered under an RJ11 breakout's spacer; every backplane bus wire
     is soldered only at real holes of its own line;
  L2 no two different nets share copper: a card's row strip or rail, or a backplane pad joined by a bus wire
     (the PAD3U has no strips: nothing connects unless a wire does); an unconnected pin sits alone;
  L3 the built copper (pins in strips, jumpers, wires, leads, cables and matings, the parts' own ties) is
     exactly the schematic, net for net;
  L4 no battery net touches a strip, a header or a socket: the battery loop is soldered or screwed leads;
  L5 the bus: on every card row-strip i (f-j) carries bus line i and its header pin; on the backplane the bus
     wire on line i carries the same line, each socket pin i on line i; the header pin tip reaches the socket
     mouth (insertion); the socket body clears the snapped card edge and the card's parts;
  L6 parts and keep-outs (plugs, the USB-C console lead, SWD leads) on one card do not collide in 3D;
  L7 the cage: each card's pitch clears the tallest part below plus the header tails and solder tails above;
     no part of one card enters another card's slab, the backplane's front items, the left wall slot, the
     right corner post or the retention bar; each card slides out toward the lid alone; the cage, the
     power zone (pack and charger) and every card fit the box inside; the slot width; the backplane length;
  L8 every routed wire, jumper and lead (layout/route.py) lies on its side of the card in straight runs with
     right-angle bends, never crosses a part's footprint (a pad lead only crosses its own breakout), never
     passes over a used hole that is not its own end, and shares no grid edge with another wire except an
     insulated lead bundle; a bare jumper crosses nothing;
  L9 every mating and fixing (MECH below): how it is held, what takes the force, how it comes apart; the
     numeric ones are checked (slot play against the socket's alignment tolerance, insertion, the latch
     room over each plug, the coax bend room, the SMA path) and the README table is written from it.
Run: python3 layout_checks.py   (exit status 0 only if every check passes)
"""
import sys
from collections import defaultdict
from itertools import combinations

import route
import stack as st
from stack import S, model

sys.path.insert(0, str(st.HERE.parent / "cage"))
import cage  # noqa: E402

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


def bp_ok(h):
    i, n = h[1:].split(".")
    return h[0] == "s" and 0 <= int(i) <= st.BP_STRIPS and 1 <= int(n) <= st.BP_HOLES


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
    for ref, pins, _note in st.BP_PARTS:
        for pin, h in pins.items():
            if (ref, pin) not in PIN:
                fail("L1", f"backplane {ref}.{pin} is not a pin of the model")
            if not bp_ok(h):
                fail("L1", f"backplane {ref}.{pin} at {h} is not a stripboard hole")
            if ("BP", h) in out:
                fail("L1", f"BP:{h} holds {out[('BP', h)]} and {ref}.{pin}")
            out[("BP", h)] = (ref, pin)
    return out


def check_pins_and_ends(ph):
    used = defaultdict(list)
    pads = {(pl["ref"], n) for _b, pl in st.placements() for n in st.pads_of(pl)}
    for kind, a, c, side, note in st.WIRES:
        for e in (a, c):
            if isinstance(e, str):
                b, h = e.split(":")
                if (b == "BP" and not bp_ok(h)) or (b != "BP" and h not in st.ALL_HOLES):
                    fail("L1", f"{kind} end {e} is not a hole")
                if (b, h) in ph:
                    fail("L1", f"{kind} end {e} is a hole already holding {ph[(b, h)]}")
                used[e].append(note)
            elif e not in PIN:
                fail("L1", f"{kind} end {e} is not a model pin")
            elif e[0] in st.board_of_ref() and (e not in pads or PIN[e][3] not in ("solder", "lead", "lever")):
                fail("L1", f"{kind} end {e[0]}.{e[1]} is a placed part's pin that is not a solder pad")
    for e, notes in used.items():
        if len(notes) > 1:
            fail("L1", f"hole {e} takes {len(notes)} conductors: {notes}")
    # nothing soldered under a breakout spacer, nor on the back rails under the socket (rows 1-19)
    ends = set(used) | {f"{b}:{h}" for (b, h) in ph}
    for b, pl in st.placements():
        for bx in st.boxes_of(pl):
            if "spacer" in bx.what:
                for h in st.ALL_HOLES:
                    x, y = st.hole_xy(h)
                    if bx.x0 < x < bx.x1 and bx.y0 < y < bx.y1 and f"{b}:{h}" in ends:
                        fail("L1", f"{b}:{h} is used but lies under {bx.what}")
    for line, holes in st.BP_BUS:
        for n in holes:
            if not bp_ok(f"s{line}.{n}"):
                fail("L1", f"backplane bus wire {line} is soldered at s{line}.{n}, not a padboard hole")
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
    """The copper an end belongs to: a card's row strip or rail, or one backplane pad (no strips there)."""
    if isinstance(e, str):
        b, h = e.split(":")
        return ("strip", b, h if b == "BP" else st.strip_of(h))
    return ("pin",) + tuple(e)


def build_copper(ph, ties=True):
    """Union of the built conductors; ties=True adds each part's own copper (model 'ties')."""
    uf = UF()
    for (b, h), (ref, pin) in ph.items():
        uf.u(("pin", ref, pin), node(f"{b}:{h}"))
    for kind, a, c, side, note in st.WIRES:
        uf.u(node(a), node(c))
    for a, c in st.CABLES:
        uf.u(node(a), node(c))
    for line, holes in st.BP_BUS:                       # the tinned bus wires: soldered at every used pad
        for n in holes[1:]:
            uf.u(("strip", "BP", f"s{line}.{holes[0]}"), ("strip", "BP", f"s{line}.{n}"))
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
    strips = [(b, st.strip_of(h)) for b in st.BOARDS for h in st.ALL_HOLES] + \
             [("BP", f"s{line}.{holes[0]}") for line, holes in st.BP_BUS if holes]
    for b, s in strips:
        g = uf.f(("strip", b, s))
        if True:
            nets = {NET_OF[(x[1], x[2])] for x in uf.p if x[0] == "pin" and uf.f(x) == g and (x[1], x[2]) in NET_OF}
            rep[b][s.split(".")[0] if b == "BP" else s] = \
                next(iter(nets)) if len(nets) == 1 else (None if not nets else "/".join(sorted(nets)))
    return rep


def check_bus(ph):
    rep = strip_report(ph)
    for i, line in enumerate(model.BUS, 1):
        for b in st.BOARDS:
            got = rep[b].get(f"R{i}")
            if got != line:
                fail("L5", f"{b} row-strip {i} (f-j) carries {got}, bus line {i} is {line}")
            if ph.get((b, f"j{i}")) != (model.HEADERS[b], str(i)):
                fail("L5", f"{b}:j{i} holds {ph.get((b, f'j{i}'))}, wants header pin {i}")
        if rep["BP"].get(f"s{i}") != line and not (line == "BUS_SPARE" and rep["BP"].get(f"s{i}") is None):
            fail("L5", f"backplane bus wire {i} carries {rep['BP'].get(f's{i}')}, bus line {i} is {line}")
    tip = st.Y_J + st.RA_TIP
    ins = tip - st.Y_MOUTH
    tol = S.val("slot_clear") + 0.5
    if ins - tol < 3.0 or ins > S.val("ra_mate"):
        fail("L5", f"insertion {ins:.2f} mm (minus {tol:.1f} position tolerance) is outside 3.0..{S.val('ra_mate')}")
    gap = st.Y_MOUTH - st.CD
    if gap < S.val("clear"):
        fail("L5", f"the socket mouth is {gap:.2f} mm past the snapped card edge (< {S.val('clear'):g}): it overlaps the card")
    if st.Y_MOUTH - st.Y_INS < 0.5:
        fail("L5", f"the header insulator ends {st.Y_MOUTH - st.Y_INS:.2f} mm short of the socket mouth")
    NOTES.append(f"bus: 18 lines, header column j rows 1-18 on every card, backplane bus wires on lines 1-18; card "
                 f"snapped at Y {st.CD:.2f} [TBD-MEASURE]; header insulator to Y {st.Y_INS:.2f}, mating pins out to Y "
                 f"{tip:.2f} ({tip - st.CD:.2f} past the edge); socket mouth {st.Y_MOUTH:.2f} ({gap:.2f} clear of the card, "
                 f"{st.Y_MOUTH - st.Y_INS:.2f} clear of the insulator); insertion {ins:.2f} mm of {S.val('ra_mate'):g} "
                 f"(>= {ins - tol:.2f} if the card sits {tol:.1f} mm short); card edge {st.Y_BP - st.CD:.2f} mm from the backplane")
    for b in st.BOARDS:
        sock = st.Box(st.X(1) - 1.27, st.Y_MOUTH, st.X(18) + 1.27, st.Y_BP, 0.0, 2 * st.PIN_Z, "socket body")
        if overlap(sock, st.Box(0, 0, st.BW, st.CD, -st.BT, 0, "card"), tol=-S.val("clear")):
            fail("L5", f"{b}: the socket body comes within {S.val('clear'):g} mm of the card")
        for ref, x in board_boxes(b):
            if ref != model.HEADERS[b] and not x.keepout and overlap(sock, x):
                fail("L5", f"{b}: the backplane socket body hits {x.what}")


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


def tallest(b, keepouts=False):
    zs = [(x.z1, x.what) for _r, x in board_boxes(b) if (keepouts or not x.keepout) and not x.service]
    return max(zs) if zs else (0.0, "nothing")


def lowest(b):
    zs = [(x.z0, x.what) for _r, x in board_boxes(b) if not x.service]
    return min(zs + [(-S.val("tails") - S.val("sb_t"), "solder tails and underside wires")])


def to_box(b, x):
    """A card-frame Box in the box frame."""
    xa, ya, za = st.card_to_box(b, x.x0, x.y0, x.z0)
    xb, yb, zb = st.card_to_box(b, x.x1, x.y1, x.z1)
    return st.Box(xa, ya, xb, yb, za, zb, f"{b} {x.what}", x.keepout, x.service)


def card_slab(b):
    return to_box(b, st.Box(0, 0, st.BW, st.CD, -st.BT, 0, "card"))


def cage_boxes():
    """The fixed cage in the box frame (../cage/cage.py), less its slots."""
    return [st.Box(b.x0, b.y0, b.x1, b.y1, b.z0, b.z1, f"cage {name}") for name, b in cage.fixed_boxes()] + \
        [st.Box(c.x0, c.y0, c.x1, c.y1, c.z0, c.z1, c.what) for c in cage.contents()]


def check_cage(ph):
    t, tl, cl = st.BT, S.val("tails"), S.val("clear")
    order = st.ORDER
    tails = max(tl, S.val("ra_tail") - t)
    for lo, hi in zip(order, order[1:]):
        space = st.card_z(hi) - t - st.card_z(lo)
        top, what = tallest(lo, keepouts=True)
        need = top + tails + cl
        NOTES.append(f"pitch {lo}-{hi} {st.card_z(hi) - st.card_z(lo):.2f} mm: {space:.2f} mm between cards; tallest on "
                     f"{lo} {top:.1f} mm ({what}) + tails {tails:.2f} + clearance {cl:g} = {need:.1f} mm, "
                     + ("ok" if need <= space else "CLASH"))
        if need > space:
            fail("L7", f"{lo}-{hi}: {space:.2f} mm between cards < {need:.1f} mm needed by {what}")
    # everything in the box frame
    items = []
    for b in st.BOARDS:
        items += [(b, to_box(b, x)) for _r, x in board_boxes(b) if not x.service]
        items.append((b, card_slab(b)))
    fixed = cage_boxes() + [st.Box(k.x0, k.y0, k.x1, k.y1, k.z0, k.z1, f"box {k.what}") for k in cage.box_keepouts()]
    for ref, pins, note in st.BP_PARTS:            # the QT lead housings and charger pins standing on the backplane
        if ref.startswith("W") or ref == "XJ1":
            for pin, h in pins.items():
                x, z = st.bp_xy(h)
                hh = S.val("qt_lead_h") if ref.startswith("W") else 8.5
                fixed.append(st.Box(x - 1.27, st.BP_FRONT, x + 1.27, st.BP_FRONT + hh, z - 1.27, z + 1.27, f"{ref} {pin} housing"))
    for b, x in items:
        for f in fixed:
            if overlap(x, f):
                fail("L7", f"{x.what} hits the {f.what}")
    for (ba, a), (bb, c) in combinations(items, 2):
        if ba != bb and not (a.keepout and c.keepout) and overlap(a, c):
            fail("L7", f"{a.what} collides with {c.what}")
    # pull-out: each card slides toward the lid (+Yb) alone; the swept volume must stay clear of the cage
    # (the retention bar is off) and of every other card
    lid = sorted({x.what.split(" ", 1)[0] + " " + x.what.split(" ", 1)[1].split(" ")[0] for _b, x in items
                  if x.y1 > cage.SEAM and not x.keepout})
    NOTES.append(f"depth: the base-lid seam is at Yb {cage.SEAM:g} (printed base 100 deep outside)"
                 + ("; in the lid tray (past the seam): " + ", ".join(lid) if lid else "; nothing reaches the lid tray")
                 + "; the base's corner lands, insert posts, rim lip and gland nuts are keep-outs (the lid's wall and "
                 "bosses too, with the lid on)")
    for b in st.BOARDS:
        mine = [x for bb, x in items if bb == b and not x.keepout]
        others = [x for bb, x in items if bb != b] + [f for f in fixed if "retention" not in f.what
                                                       and not f.what.startswith("box lid")]
        for x in mine:
            swept = st.Box(x.x0, x.y0 + 0.5, x.x1, 1e3, x.z0, x.z1, x.what)
            for o in others:
                if overlap(swept, o):
                    fail("L7", f"{b} cannot slide out: {x.what} meets {o.what}")
    # the box inside
    w, h, d = S.val("box_in")
    xs = [x for _b, x in items] + fixed
    ext = (min(x.x0 for x in xs), max(x.x1 for x in xs), min(x.y0 for x in xs), max(x.y1 for x in xs),
           min(x.z0 for x in xs), max(x.z1 for x in xs))
    NOTES.append(f"cage and cards span Xb {ext[0]:.1f}..{ext[1]:.1f}, Yb {ext[2]:.1f}..{ext[3]:.1f}, "
                 f"Zb {ext[4]:.1f}..{ext[5]:.1f} mm; box inside {w:g} x {d:g} x {h:g} [TBD-MEASURE]")
    front_y = max(x.y1 for x in [x for _b, x in items] + cage_boxes())
    FLAGS.append(f"depth: the front of the stack is at Yb {front_y:.1f}, {d - front_y:.1f} mm short of the "
                 f"closed lid ({d:g}: base 97 + lid 24 less a {S.val('gasket'):g} mm gasket allowance [TBD-MEASURE])") \
        if d - front_y < 3.0 else None
    if ext[0] < 0 or ext[1] > w or ext[2] < 0 or ext[3] > d or ext[5] > h:
        fail("L7", f"the cage does not fit the box inside {w:g} x {h:g} x {d:g}")
    top_power = max(c.z1 for c in cage.contents())
    under_b4 = st.card_z("B4") + lowest("B4")[0]
    ev = S.val("evm")
    margin_b4 = under_b4 - top_power
    shtc3 = [lc_b for lc_b in [to_box(bb, x) for bb in st.BOARDS for r, x in board_boxes(bb) if r == "U5"]]
    heat = (min(x.z0 for x in shtc3) - cage.EVM_TOP) if shtc3 else 0.0
    NOTES.append(f"shelves: pack {cage.PACK_Z0:g}-{cage.PACK_Z0 + S.val('pack')[2]:g}, the EVM ({ev[0]:g} x {ev[1]:g}, "
                 f"J8 {S.val('evm_j8'):g} toward the lid; Clint) board at Zb {cage.EVM_Z0:g}, its top {cage.EVM_TOP:g}, "
                 f"its back edge {cage.EVM_Y0 - st.BP_FRONT:.1f} mm in front of the backplane's lower end (from Zb "
                 f"{cage.BP_BOTTOM:.1f}), {margin_b4:.1f} under B4 (the terminal "
                 f"screws and the EVM's leads use that room); the SHTC3 is {heat:.0f} mm above the EVM")
    if cage.EVM_TOP > cage.BP_BOTTOM and cage.EVM_Y0 - st.BP_FRONT < 2.0:
        fail("L7", "the EVM is less than 2 mm in front of the backplane")
    bp = st.Box(st.strip_x(0) - 1.27, 0.0, st.strip_x(20) + 1.27, st.BP_FRONT,
                st.BP_Z0 - 2 * st.P, st.BP_Z0 + (st.BP_HOLES + 1) * st.P, "backplane, its posts and the mux behind it")
    for c in cage.contents():
        if overlap(c, bp):
            fail("L7", f"{c.what} hits the {bp.what}")
    if top_power + cl > under_b4:
        fail("L7", f"the charger ({top_power:.1f}) reaches B4's underside ({under_b4:.1f})")
    span = (st.BP_HOLES - 1) * st.P
    NOTES.append(f"backplane: PAD3U piece {st.BP_STRIPS + 1} x {st.BP_HOLES} holes ({(st.BP_STRIPS + 1) * st.P:.1f} x "
                 f"{span + st.P:.1f} mm), 18 bus wires, sockets at holes " + ", ".join(f"{b} {st.SOCKET_HOLE[b]}" for b in st.ORDER)
                 + f"; copper face {st.BP_BACK:g} mm off the back wall")
    if max(st.SOCKET_HOLE.values()) > st.BP_HOLES:
        fail("L7", "a socket is past the end of the backplane")
    mx = st.MUX_BOX
    for b in st.BOARDS:
        z = st.bp_xy(f"s1.{st.SOCKET_HOLE[b]}")[1]
        if mx[1] - 1.27 < z < mx[3] + 1.27:
            fail("L7", f"the mux behind the backplane covers {b}'s socket tails")
    sc = S.val("slot_clear")
    NOTES.append(f"slots: {t + sc:.1f} mm for the {t:g} mm card ({sc:g} mm print allowance [TBD-MEASURE]); "
                 f"retention bar {S.val('bar'):g} mm, front left; right corner post grips card Y {S.val('sb_snap_y') - 1.5:.2f}-{st.CD:.2f}, on B1 and B2 the back breakout's spacer tongue")


def check_routes():
    """L8: the routed wires (layout/route.py) checked from their points, not from the router's own bookkeeping."""
    n_ok = n_all = 0
    total = 0.0
    edges = {}
    nodes = {}
    for i, (kind, a, c, side, note) in enumerate(st.WIRES):
        if side == "copper":
            continue
        r = route.ROUTES[i]
        if r is None:
            continue                                   # a backplane lead (drawn straight)
        n_all += 1
        if not r["ok"]:
            fail("L8", f"wire {i} ({kind} {a} - {c}) on {r['card']}: {r['why']}")
            continue
        n_ok += 1
        if r.get("bundled"):
            continue                                   # laid beside the first lead from the same pad
        total += r["length"]
        z = route.Z_TOP if side == "top" else route.Z_BOT
        own = set(r["own"])
        fp = route.footprints(r["card"], side)
        holes = route.used_holes(r["card"])
        flat = [p for p in r["pts"]]
        for p, q in zip(flat, flat[1:]):
            if abs(p[2] - z) > 1e-6 or abs(q[2] - z) > 1e-6:
                continue                               # the climb onto a breakout pad and the run across its own board
            if abs(p[0] - q[0]) > 1e-6 and abs(p[1] - q[1]) > 1e-6:
                fail("L8", f"wire {i} on {r['card']} runs diagonally from ({p[0]:.2f},{p[1]:.2f}) to ({q[0]:.2f},{q[1]:.2f})")
            for f in fp:
                if f[0] not in own and route.seg_hits(p, q, f, -0.05):
                    fail("L8", f"wire {i} on {r['card']} {side} crosses {f[0]} ({f[5]})")
        g = r["grid"]
        for n in g[1:-1]:
            x, y = route.node_xy(n)
            if (round(x, 2), round(y, 2)) in holes:
                fail("L8", f"wire {i} on {r['card']} passes over the used hole at ({x:.2f},{y:.2f})")
        for u, v in zip(g, g[1:]):
            edges.setdefault((r["card"], side, frozenset((u, v))), []).append((i, r["kind"]))
        for n in g:
            nodes.setdefault((r["card"], side, n), []).append((i, r["kind"]))
    for (card, side, _e), users in edges.items():
        if len(users) > 1 and not all(k.startswith("lead") for _i, k in users):
            fail("L8", f"{card} {side}: wires {', '.join(str(i) for i, _k in users)} share a grid run")
        if len(users) > route.BUNDLE:
            fail("L8", f"{card} {side}: {len(users)} leads bundled on one grid run (> {route.BUNDLE})")
    for (card, side, n), users in nodes.items():
        if len(users) > 1 and any(k == "jumper" for _i, k in users):
            fail("L8", f"{card} {side}: a bare jumper meets wire(s) "
                       f"{', '.join(str(i) for i, _k in users)} at ({route.node_xy(n)[0]:.2f},{route.node_xy(n)[1]:.2f})")
    NOTES.append(f"routing: {n_ok} of {n_all} wires, jumpers and leads routed on the 1.27 mm grid, right-angle runs "
                 f"around every part, {total:.0f} mm of wire laid (bundled leads counted once)")


MECH = []       # (mating or fixing, how it is held, what takes the force, how it comes apart, flag or "")
FLAGS = []


def mech(what, held, force, apart, flag=""):
    MECH.append((what, held, force, apart, flag))
    if flag:
        FLAGS.append(f"{what}: {flag}")


def room_above(box, items, ceiling):
    """Free height over a box-frame box: up to the lowest thing above that overlaps it in X and Y."""
    zs = [o.z0 for o in items if o is not box and o.x0 < box.x1 - 0.02 and box.x0 < o.x1 - 0.02 and
          o.y0 < box.y1 - 0.02 and box.y0 < o.y1 - 0.02 and o.z0 >= box.z1 - 0.02]
    return min(zs + [ceiling]) - box.z1


def check_mech():
    """L9: every mating and fixing, with the numbers that can be checked now."""
    w_in, h_in, d_in = S.val("box_in")
    items = [to_box(b, x) for b in st.BOARDS for _r, x in board_boxes(b) if not x.service] + \
        [card_slab(b) for b in st.BOARDS] + cage_boxes()
    sc, tol = S.val("slot_clear"), S.val("align_tol")
    if sc > tol:
        fail("L9", f"slot play {sc:g} mm is more than the socket lead-in takes ({tol:g} mm)")
    stop = st.Y_MOUTH - st.Y_INS
    ins = st.Y_INS + S.val("ra_mate") - st.Y_MOUTH
    mech("Card in its slot", "left wall slot (2 mm deep) and the right corner post slot; the retention bar across "
         "the front left", "the slots take the card's weight and any knock across it; the bar stops it backing out",
         "two M3 screws: bar off, card slides out toward the lid",
         "")
    mech("Bus header into the backplane socket", f"18 contacts' friction; axis Yb (in the card plane, toward the back "
         f"wall); insertion {ins:.2f} mm of "
         f"{S.val('ra_mate'):g}; the insulator meets the socket {stop:.2f} mm further in (the depth stop)",
         f"the socket; side play is the slot's {sc:g} mm, inside the socket lead-in ({tol:g} mm [TBD-MEASURE])",
         "pull the card straight out toward the lid (bar off first)", "")
    # breakouts
    for b in st.BOARDS:
        for pl in st.PLACE[b]:
            if pl["fp"] in ("INA", "MAX", "REG", "SHTC3"):
                qt = any("QT socket" in x.what for x in st.boxes_of(pl))
                mech(f"{b} {pl['ref']} breakout ({pl['note'].split(';')[0]})",
                     "its own header, soldered in the breakout and in the card (one row)",
                     "the header pins; a QT plug's push goes through the breakout into the header" if qt else
                     "the header pins",
                     "desolder the header row (or cut the pins and fit a new header)",
                     "held by solder alone on one header row")
    for b in ("B1", "B2"):
        for pl in st.PLACE[b]:
            if pl["fp"] == "BOB":
                back = any("tongue" in x.what for x in st.boxes_of(pl))
                mech(f"{b} {pl['ref']} RJ11 breakout", "bonded to its printed spacer, the spacer bonded to the card; "
                     "its six pads take flying leads to the card (no pin goes into the card)"
                     + ("; the spacer's tongue sits in the right corner post slot" if back else ""),
                     "the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the "
                     "two bonds" + (" and the post" if back else "") + "; the latch takes the pull",
                     "unsolder the six leads at the card; cut the spacer bond",
                     "held by adhesive alone" + (" (the post takes the push on this one)" if back else
                                                 ": the plug's push and pull load the bond"))
    # latch access and the cable path
    plugs = [x for x in items if "RJ11 plug" in x.what]
    rooms = sorted((room_above(pg, items, h_in), pg.what) for pg in plugs)
    worst = rooms[0]
    fin = S.val("finger")
    tight = [f"{w_.split(' RJ11')[0]} {r_:.1f}" for r_, w_ in rooms if r_ < fin]
    col = w_in - max(pg.x1 for pg in plugs)
    flag = "" if not tight else (f"less than {fin:g} mm [TBD-MEASURE] over the plug to press its latch from above: "
                                 + ", ".join(tight) + " mm (a small screwdriver from the front instead)")
    mech("RJ11 plug latch and cable", f"the jack latch; the latch is on the plug, {worst[0]:.1f} mm free over the "
         f"tightest plug ({worst[1]}); each cable turns down beyond the plug in the {col:.1f} mm column to the right "
         "wall and runs down past the charger to its PG-7 gland in the right wall, below the jacks", "the latch, then the gland's seal (strain relief)",
         "press the latch (lid open, from the front), pull; loosen the gland nut to pull the cable through", flag)
    # the mini, its USB-C and SMA, the coax
    a1 = [to_box("B3", x) for _r, x in board_boxes("B3") if _r == "A1"]
    usb = [to_box("B3", x) for x in st.boxes_of(next(pl for pl in st.PLACE["B3"] if pl["ref"] == "A1"))
           if x.service]
    mech("Wio-E5 mini on B3", "soldered on its own 2 x 12 header (not in sockets)", "the header pins",
         "desolder 24 pins", "held by solder alone; cannot come off without desoldering 24 pins")
    if usb:
        u = usb[0]
        mech("Wio-E5 mini USB-C console", "the receptacle's friction; cable plugged from the left with the lid open",
             "the mini's receptacle and its header", "pull the plug",
             "" if u.x0 >= 0 else "the console plug reaches the left wall")
    sma = next(x for x in a1 if x.what.endswith("SMA-K"))
    arm = next(x for x in a1 if x.what.endswith("SMA adapter forward arm"))
    hits = sorted({k.what for k in cage.box_keepouts() for x in a1 if "adapter" in x.what and overlap(x, k)})
    plug_l, bend = S.val("sma_plug_len"), S.val("rg316_bend")
    straight = w_in - sma.x1
    pe, yb, zb, ax = cage.coax(arm)
    nut = cage.BULKHEAD_NUT / 2
    probs = []
    if yb + nut + 2.0 > cage.SEAM:
        probs.append(f"the bulkhead (Yb {yb:.1f}) is within 2 mm of the seam ({cage.SEAM:g})")
    if zb + nut + 2.0 > h_in - cage.CORNER:
        probs.append(f"the bulkhead (Zb {zb:.1f}) meets the upper corner land")
    if w_in - ax < bend + 2.0:
        probs.append("no room for the bend to the right wall")
    if pe > d_in - 2.0:
        probs.append("the plug reaches the lid")
    if hits:
        probs.append("AD1 meets the " + ", ".join(hits))
    NOTES.append(f"SMA: a straight plug on the mini's SMA would need {plug_l + bend:.1f} mm to the right wall "
                 f"(plug {plug_l:g} + bend {bend:g} [TBD-MEASURE]), there are {straight:.1f}: AD1 is needed, its arm "
                 f"toward the lid; the plug ends at Yb {pe:.1f}, the cable bends right to the bulkhead boss at Yb "
                 f"{yb:.1f}, Zb {zb:.1f} in the right wall ({cage.SEAM - yb - nut:.1f} mm to the seam, "
                 f"{h_in - cage.CORNER - zb - nut:.1f} under the upper corner land)")
    for p_ in probs:
        fail("L9", "coax: " + p_)
    cflag = ""
    mech("SMA, adapter and coax to the bulkhead", "AD1 screwed on the mini's SMA-K, its arm toward the lid; the "
         "135110 plug screwed on AD1; the cable bends right in front of the cards to the bulkhead jack in the right "
         "wall's boss",
         "the coax is clipped to the cage at its bend so a pull on it reaches the bulkhead, not the mini's SMA",
         "unscrew the plug at AD1 (8 mm spanner), then lift B3 out", cflag)
    # power
    mech("Battery junction E1 on B4", "WAGO 222-415 hot-glued to B4's top, front-right corner (overhanging the front edge)",
         "the glue; the 24 AWG stranded leads and the R7/R8 legs clamped (strip 9-10 mm)", "lever up to free a lead; warm the glue to lift it",
         "")
    mech("Battery pack", "lies flat on the pack tray, the lowest shelf (the heaviest part low); a hook-and-loop "
         "strap through the tray", "the tray's front lip and the strap", "open the strap, unplug the JST PH, slide it out")
    mech("Charger (BQ25798EVM)", "a shelf: its side edges on two moulded ledges, a stop at the back, a snap clip at "
         "the front (the board has no mounting holes); the Bumpon feet (H1-H4, 3M SJ-5303) peeled off first",
         "the ledges; the terminal screws are tightened from above, in the room under B4",
         "unscrew its leads, flex the clip, slide it toward the lid on its service loops",
         "its underside parts (J6, tails: 4 mm [TBD-MEASURE]) must clear the 2 mm ledges at the edges")
    mech("B4 and the charger", "B4's battery and sense leads are screwed into the EVM terminals",
         "the terminal screws", "unscrew the leads at the EVM before B4 slides out",
         "B4 is tethered to the charger by its leads: unscrew them first")
    mech("Backplane on its posts", "three M3 screws (s0.2, s20.2, s20.36) into heat-set inserts in three round floor "
         "posts; the top-left corner's edge in the left wall's groove (lowered 2.5 right, slid left into it)",
         "the posts and the groove floor take the card insertion push", "undo the three screws, slide it 2.5 right, "
         "lift it out, after every card is out", "removable only after all four cards are out")
    mech("Lid to the printed base", f"four M4 stainless screws on {S.val('m4_washer')[0]:g} mm washers through the "
         f"lid's 8 mm holes into M4 heat-set inserts ({S.val('insert_m4')[0]:g} mm holes, 3 mm of wall round each) in "
         "the base's corner posts, 156 x 109 apart (9.75 / 10.25 in from the lid's edges, cage/lid-rim-spec.md; option b, recommended over a printed "
         f"copy of the original 8 mm plastic thread); the base's 9 mm land under the lid's rim, its "
         f"{S.val('rim_tongue')[0]:g} x {S.val('rim_tongue')[1]:g} sealing lip in the lid's O-ring channel",
         "the screws squeeze the O-ring; the lid's rim takes a knock", "undo the four lid screws",
         "not settled: the screw and the lid's corner pocket (L1), and the rim test ring's fit on the real lid: no "
         "full STL until they are")
    mech("Base to the pole", "two moulded lugs on the back, a hose clamp or U-bolt through each; no screw through "
         "the back into the box", "the lugs' roots in the 3 mm floor", "open the clamps", "")
    mech("Cables through the glands", "six round port cables in PG-7s (#762, seal 3.0-4.3 mm) in the bottom wall's bosses; the flat "
         "wind and rain cables in PG-9s (#761) with the seal out and the gap packed with silicone or a split grommet",
         "the gland's seal (round) or the sealant (flat); a drip loop below each gland outside, so water runs off "
         "the loop and not along the cable into the gland", "loosen the cap (round); cut the sealant (flat)",
         "a flat cable is sealed once its position is final and then comes out only by cutting the seal")
    gap = min(st.card_z(st.ORDER[i + 1]) - st.BT - st.card_z(st.ORDER[i]) for i in range(len(st.ORDER) - 1)
              if st.ORDER[i] in ("B1", "B2"))
    need = S.val("bob_spacer") + S.val("breakout_t") + S.val("jack_4ucon")[2] + S.val("tails") + 0.5
    if need > gap:
        FLAGS.append(f"Clint's two existing BOB-14021s carry the 4UCON 14869 jack ({S.val('jack_4ucon')[2]:g} high): "
                     f"under the next card they need {need:.1f} mm, there are {gap:.2f}; the build uses new BOBs with "
                     f"the 87180-066LF ({S.val('jack_h'):g} high, RS listing; no Amphenol drawing in hand)")
    NOTES.append("glands: " + ", ".join(f"{k} at Xb {x:g}, Yb {y:g}" for x, y, k in cage.GLANDS)
                 + " (bottom wall); the cables rise in the right column, Xb "
                 f"{cage.EVM_X0 + S.val('evm')[0] + 2:g}-{cage.W:g}, past the EVM and the pack to the jacks")
    ft, fw = S.val("flat_cable")
    diag = (ft ** 2 + fw ** 2) ** 0.5
    for k, bore in zip(("PG-7", "PG-9"), S.val("gland_bore")):
        need = diag + 2 * S.val("sealant")
        kinds = {(xx, yy): kk for xx, yy, kk in cage.GLANDS}
        uses = [v for xy, v in cage.FLAT.items() if kinds[xy] == k]
        if uses and need > bore:
            fail("L9", f"a flat cable ({ft:g} x {fw:g}, {diag:.1f} across) and its sealant need {need:.1f} mm; the {k} "
                       f"bore is {bore:g}")
        NOTES.append(f"glands: a flat cable {ft:g} x {fw:g} ({diag:.1f} across) and {S.val('sealant'):g} mm of "
                     f"sealant each side need {need:.1f}: the {k} bore (seal out) is {bore:g}"
                     + (f", used for {', '.join(uses)}" if uses else ""))
    FLAGS.append(f"the flat weather-meter cables ({ft:g} x {fw:g}) are wider than a PG-9's round seal "
                 f"({S.val('gland_pg9')[4]:g}-{S.val('gland_pg9')[5]:g}): they go through with the seal out, the gap "
                 "packed with silicone or a split grommet; sealed once the cable's position is final, the cable comes "
                 "out only by cutting the seal")
    for f in FLAGS:
        NOTES.append(f"flag: {f}")


def mech_table():
    rows = ["| Mating or fixing | Held by | Force path | Taken apart | Flag |", "|---|---|---|---|---|"]
    for r in MECH:
        rows.append("| " + " | ".join(c.replace("|", "/") for c in r) + " |")
    return "\n".join(rows)


def readme_mech(write):
    p = st.HERE.parent / "README.md"
    t = p.read_text()
    a, b = "<!-- mechanical:begin (generated by layout/layout_checks.py --write) -->", "<!-- mechanical:end -->"
    if a not in t:
        fail("L9", "README has no mechanical table markers")
        return
    new = t[:t.index(a) + len(a)] + "\n" + mech_table() + "\n" + t[t.index(b):]
    if write:
        p.write_text(new)
    elif new != t:
        fail("L9", "README mechanical table out of step: run python3 layout/layout_checks.py --write")


def run():
    ph = pin_holes()
    check_pins_and_ends(ph)
    check_copper(ph)
    check_bus(ph)
    check_3d()
    check_cage(ph)
    check_routes()
    check_mech()
    return ph


def main():
    run()
    readme_mech("--write" in sys.argv)
    for n in NOTES:
        print("note ", n)
    for f in FAILS:
        print("FAIL ", f)
    print(f"layout {'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
