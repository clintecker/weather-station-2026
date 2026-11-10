"""Machine checks of the card cage (layout/stack.py) against the schematic model.

  L1 every placed pin lands on a SolderFul hole (cards) or a stripboard hole (backplane), no two pins share
     a hole; every jumper, wire and lead end is a real hole or a real pad; no hole takes two conductors;
     nothing is soldered under an RJ11 breakout's spacer or on the back rails under the socket;
  L2 no two different nets share a strip, on a card or on the backplane; an unconnected pin sits alone;
  L3 the built copper (pins in strips, jumpers, wires, leads, cables and matings, the parts' own ties) is
     exactly the schematic, net for net;
  L4 no battery net touches a strip, a header or a socket: the battery loop is soldered or screwed leads;
  L5 the bus: on every card row-strip i (f-j) carries bus line i and its header pin; on the backplane strip i
     carries the same line, each socket pin i in strip i; the header pin tip reaches the socket mouth
     (insertion) and the socket body clears the card's parts;
  L6 parts and keep-outs (plugs, the USB-C console lead, SWD leads) on one card do not collide in 3D;
  L7 the cage: each card's pitch clears the tallest part below plus the header tails and solder tails above;
     no part of one card enters another card's slab, the backplane's front items, the left wall slot, the
     right corner post or the retention bar; each card slides out toward the lid alone; the cage, the
     power zone (pack and charger) and every card fit the box inside; the slot width; the backplane length.
Run: python3 layout_checks.py   (exit status 0 only if every check passes)
"""
import sys
from collections import defaultdict
from itertools import combinations

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
            elif e[0] in st.board_of_ref() and (e not in pads or PIN[e][3] not in ("solder", "lead")):
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
    for e in ends:
        b, h = e.split(":")
        if b != "BP" and h[:2] in ("B+", "B-") and int(h[2:]) <= 19:
            fail("L1", f"{e} is under the backplane socket (back rails, rows 1-19 stay bare)")
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
        return ("strip", b, h.split(".")[0] if b == "BP" else st.strip_of(h))
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
    for i in range(0, st.BP_STRIPS + 1):
        uf.f(("strip", "BP", f"s{i}"))
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
             [("BP", f"s{i}") for i in range(0, st.BP_STRIPS + 1)]
    for b, s in strips:
        if True:
            g = uf.f(("strip", b, s))
            nets = {NET_OF[(x[1], x[2])] for x in uf.p if x[0] == "pin" and uf.f(x) == g and (x[1], x[2]) in NET_OF}
            rep[b][s] = next(iter(nets)) if len(nets) == 1 else (None if not nets else "/".join(sorted(nets)))
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
        if rep["BP"].get(f"s{i}") != line:
            fail("L5", f"backplane strip {i} carries {rep['BP'].get(f's{i}')}, bus line {i} is {line}")
    tip = st.Y_J + st.RA_TIP
    ins = tip - st.Y_MOUTH
    tol = S.val("slot_clear") + 0.5
    if ins - tol < 3.0 or ins > S.val("ra_mate"):
        fail("L5", f"insertion {ins:.2f} mm (minus {tol:.1f} position tolerance) is outside 3.0..{S.val('ra_mate')}")
    NOTES.append(f"bus: 18 lines, header column j rows 1-18 on every card, backplane strips 1-18; pin tip at card Y "
                 f"{tip:.2f}, socket mouth {st.Y_MOUTH:.2f}, insertion {ins:.2f} mm of {S.val('ra_mate'):g} "
                 f"(>= {ins - tol:.2f} if the card sits {tol:.1f} mm short); card back edge "
                 f"{st.Y_BP - st.BH:.2f} mm from the backplane")
    for b in st.BOARDS:
        sock = st.Box(st.X(1) - 1.27, st.Y_MOUTH, st.X(18) + 1.27, st.Y_BP, 0.0, 2 * st.PIN_Z, "socket body")
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
    return to_box(b, st.Box(0, 0, st.BW, st.BH, -st.BT, 0, "card"))


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
    fixed = cage_boxes()
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
    for b in st.BOARDS:
        mine = [x for bb, x in items if bb == b and not x.keepout]
        others = [x for bb, x in items if bb != b] + [f for f in fixed if "retention" not in f.what]
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
    if ext[0] < 0 or ext[1] > w or ext[2] < 0 or ext[3] > d or ext[5] > h:
        fail("L7", f"the cage does not fit the box inside {w:g} x {h:g} x {d:g}")
    top_power = max(c.z1 for c in cage.contents())
    under_b4 = st.card_z("B4") + lowest("B4")[0]
    NOTES.append(f"power zone: pack shelf at Zb {cage.PACK_Z:g}, charger rails at Zb {cage.EVM_Z:g} (outline "
                 f"{'x'.join(f'{v:g}' for v in S.val('evm'))} [TBD-MEASURE]); top of the charger {top_power:.1f}, "
                 f"B4's underside {under_b4:.1f} mm")
    bp = st.Box(st.strip_x(0) - 1.27, S.val("cage_plate"), st.strip_x(20) + 1.27, st.BP_FRONT,
                st.BP_Z0 - 2 * st.P, st.BP_Z0 + (st.BP_HOLES + 1) * st.P, "backplane, its posts and the mux behind it")
    for c in cage.contents():
        if overlap(c, bp):
            fail("L7", f"{c.what} hits the {bp.what}")
    if top_power + cl > under_b4:
        fail("L7", f"the charger ({top_power:.1f}) reaches B4's underside ({under_b4:.1f})")
    span = (st.BP_HOLES - 1) * st.P
    NOTES.append(f"backplane: ST2 cut to {st.BP_STRIPS + 1} strips x {st.BP_HOLES} holes ({(st.BP_STRIPS + 1) * st.P:.1f} x "
                 f"{span + st.P:.1f} mm), sockets at holes " + ", ".join(f"{b} {st.SOCKET_HOLE[b]}" for b in st.ORDER)
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
                 f"retention bar {S.val('bar'):g} mm, front left; right corner post grips card Y 49.3-50.8")


def run():
    ph = pin_holes()
    check_pins_and_ends(ph)
    check_copper(ph)
    check_bus(ph)
    check_3d()
    check_cage(ph)
    return ph


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
