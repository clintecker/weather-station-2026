"""The printed card cage for the TX, parametric. PLA on the Bambu H2D; no print files yet (no STL).

The box (Adafruit #905) hangs on its pole by the back wall, long side vertical. Box frame: Xb across from the
inside left wall (seen from the open lid), Yb from the inside back wall toward the lid, Zb up from the inside
bottom wall. The cage is one back plate screwed to the back wall's corner bosses, carrying:
  - the left wall with one slot per card (the cards are horizontal shelves, inserted from the lid side);
  - the right corner post that takes each card's back-right corner in a slot;
  - four posts that hold the backplane (stripboard) off the back plate, copper side back;
  - the retention bar, screwed across the front-left of the card stack after the cards are in;
  - the power zone below the cards: the pack shelf with side lips and the charger slot (two rails).

The inputs that depend on parts not yet measured are named here first; every value comes from ../sources.py
(where each is marked sourced, derived or TBD) or from ../layout/stack.py (the card positions).

Run:  python3 cage.py           print the parts and check them against the box inside (no CadQuery needed)
      ../../../.venv-cad/bin/python cage.py --solid   also build the solids in CadQuery and check them
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import stack as st  # noqa: E402
from stack import S  # noqa: E402

# ------------------------------------------------------------------ inputs Clint must measure [TBD-MEASURE]
BOX_IN = S.val("box_in")            # inside width x height x depth (back wall to closed lid)
BOSS = S.val("boss")                # corner boss centre from the side walls (x, z) and diameter
EVM = S.val("evm")                  # BQ25798EVM outline length x width x tallest part
SLOT_CLEAR = S.val("slot_clear")    # card slot width over 1.6 mm (print tuning)
PACK = S.val("pack")                # battery pack (sourced)

# ------------------------------------------------------------------ chosen
PLATE = S.val("cage_plate")         # back plate thickness
WALL = S.val("cage_wall")           # left wall thickness; slots 2 mm deep
BAR = S.val("bar")                  # retention bar thickness
M3_CLEAR = 3.4                      # M3 clearance hole
SHELF = 3.0                         # pack shelf and charger rail thickness
W, H, D = BOX_IN
CARD_FRONT = st.BP_FRONT + st.Y_BP  # Yb of the cards' front edges
Z_LO = st.card_z("B4") - 8.0        # left wall and post from here ...
Z_HI = min(st.card_z("B3") + 14.0, H - 1.0)   # ... to here
PACK_Z = 18.0                       # pack shelf top: room below for the gland nuts
EVM_Z = PACK_Z + PACK[2] + 4.0      # charger rails: the charger's underside
RX = st.CAGE_LEFT + st.BW           # cards' right edges


class Part:
    def __init__(self, name, boxes, holes=(), cuts=(), note=""):
        self.name, self.boxes, self.holes, self.cuts, self.note = name, boxes, list(holes), list(cuts), note


def B(x0, y0, z0, x1, y1, z1, what):
    return st.Box(x0, y0, x1, y1, z0, z1, what)


def parts():
    out = []
    bosses = [(BOSS[0], BOSS[1]), (W - BOSS[0], BOSS[1]), (BOSS[0], H - BOSS[1]), (W - BOSS[0], H - BOSS[1])]
    out.append(Part("back plate", [B(0, 0, 0, W, PLATE, H, "back plate")],
                    holes=[(x, z, M3_CLEAR, "y") for x, z in bosses],
                    note=f"screws to the four corner bosses at {BOSS[0]:g}/{BOSS[1]:g} mm from the walls [TBD-MEASURE]"))
    # left wall: solid behind the slots, ribs between them
    wall = [B(0, PLATE, Z_LO, WALL - 2.0, CARD_FRONT + 1.0, Z_HI, "left wall")]
    slots = []
    for b in st.ORDER:
        z = st.card_z(b)
        slots.append(B(WALL - 2.0, st.BP_FRONT, z - st.BT - SLOT_CLEAR / 2, WALL, CARD_FRONT + 1.0,
                       z + SLOT_CLEAR / 2, f"slot for {b}"))
    wall.append(B(WALL - 2.0, PLATE, Z_LO, WALL, CARD_FRONT + 1.0, Z_HI, "left wall slot side"))
    out.append(Part("left wall", wall, cuts=slots, note="one 2 mm deep slot per card; cards enter from the lid side"))
    post_y1 = st.BP_FRONT + st.Y_BP - 49.3
    post = [B(RX - 2.0, PLATE, Z_LO, RX + 6.0, post_y1, Z_HI, "right corner post")]
    pslots = [B(RX - 2.0, st.BP_FRONT, st.card_z(b) - st.BT - SLOT_CLEAR / 2, RX + SLOT_CLEAR, post_y1 + 0.1,
                st.card_z(b) + SLOT_CLEAR / 2, f"post slot for {b}") for b in st.ORDER]
    # the post must not stand in front of the backplane socket region: it sits beyond strip 18
    out.append(Part("right corner post", post, cuts=pslots, note="takes each card's back-right corner (card Y 49.3-50.8)"))
    bx0 = st.strip_x(0) - 1.27
    bx1 = st.strip_x(20) + 1.27
    bz0, bz1 = st.BP_Z0 - 2 * st.P, st.BP_Z0 + (st.BP_HOLES + 1) * st.P
    posts = []
    for x in (st.strip_x(0), st.strip_x(20)):
        for z in (bz0 + 4.0, bz1 - 4.0):
            posts.append(B(x - 3.0, PLATE, z - 3.0, x + 3.0, st.BP_BACK, z + 3.0, "backplane post"))
    out.append(Part("backplane posts", posts, note=f"four posts {S.val('bp_posts'):g} mm tall, M3 screws through "
                    "strips 0 and 20 (spare, drilled 3.2 mm)"))
    out.append(Part("retention bar", [B(0, CARD_FRONT + 1.0, Z_LO, 12.0, CARD_FRONT + 1.0 + BAR, Z_HI, "retention bar")],
                    note="two M3 screws into the left wall's front face; off before any card comes out"))
    # power zone
    px1 = 4.0 + PACK[0]
    out.append(Part("pack shelf", [B(2.0, PLATE, PACK_Z - SHELF, px1 + 2.0, PLATE + PACK[1] + 4.0, PACK_Z, "pack shelf"),
                                   B(2.0, PLATE, PACK_Z, 4.0, PLATE + PACK[1] + 4.0, PACK_Z + 8.0, "pack lip left"),
                                   B(px1, PLATE, PACK_Z, px1 + 2.0, PLATE + PACK[1] + 4.0, PACK_Z + 8.0, "pack lip right")],
                    note="ribbed shelf from the back plate; a hook-and-loop strap holds the pack"))
    ex1 = 4.0 + EVM[0]
    out.append(Part("charger rails", [B(2.0, PLATE, EVM_Z - SHELF, 6.0, PLATE + EVM[1] + 2.0, EVM_Z, "charger rail left"),
                                      B(ex1 - 4.0, PLATE, EVM_Z - SHELF, ex1 + 2.0, PLATE + EVM[1] + 2.0, EVM_Z,
                                        "charger rail right")],
                    note="the charger board slides in on two rails; outline [TBD-MEASURE]"))
    return out


def contents():
    """The pack and the charger in their places (box frame), for the checks and the drawings."""
    return [B(4.0, PLATE + 2.0, PACK_Z, 4.0 + PACK[0], PLATE + 2.0 + PACK[1], PACK_Z + PACK[2], "battery pack #353"),
            B(4.0, PLATE + 1.0, EVM_Z, 4.0 + EVM[0], PLATE + 1.0 + EVM[1], EVM_Z + EVM[2],
              "BQ25798EVM (outline TBD)")]


def minus(a, c):
    """Box a less box c, as up to six boxes."""
    if not (a.x0 < c.x1 and c.x0 < a.x1 and a.y0 < c.y1 and c.y0 < a.y1 and a.z0 < c.z1 and c.z0 < a.z1):
        return [a]
    out = []
    x0, x1, y0, y1 = a.x0, a.x1, a.y0, a.y1
    if c.x0 > a.x0:
        out.append(B(a.x0, a.y0, a.z0, c.x0, a.y1, a.z1, a.what))
        x0 = c.x0
    if c.x1 < a.x1:
        out.append(B(c.x1, a.y0, a.z0, a.x1, a.y1, a.z1, a.what))
        x1 = c.x1
    if c.y0 > a.y0:
        out.append(B(x0, a.y0, a.z0, x1, c.y0, a.z1, a.what))
        y0 = c.y0
    if c.y1 < a.y1:
        out.append(B(x0, c.y1, a.z0, x1, a.y1, a.z1, a.what))
        y1 = c.y1
    if c.z0 > a.z0:
        out.append(B(x0, y0, a.z0, x1, y1, c.z0, a.what))
    if c.z1 < a.z1:
        out.append(B(x0, y0, c.z1, x1, y1, a.z1, a.what))
    return out


def fixed_boxes():
    """Material a card must not meet: every cage box less its slots (the slots are where the cards go)."""
    out = []
    for p in parts():
        bx = list(p.boxes)
        for c in p.cuts:
            bx = [r for a in bx for r in minus(a, c)]
        out += [(p.name, b) for b in bx]
    return out


def solids():
    import cadquery as cq
    res = []
    for p in parts():
        shape = None
        for b in p.boxes:
            s = cq.Workplane("XY").box(b.x1 - b.x0, b.y1 - b.y0, b.z1 - b.z0, centered=False).translate((b.x0, b.y0, b.z0))
            shape = s if shape is None else shape.union(s)
        for c in p.cuts:
            shape = shape.cut(cq.Workplane("XY").box(c.x1 - c.x0, c.y1 - c.y0, c.z1 - c.z0, centered=False)
                              .translate((c.x0, c.y0, c.z0)))
        for x, z, d, _axis in p.holes:
            shape = shape.cut(cq.Workplane("XZ").circle(d / 2).extrude(-PLATE - 1).translate((x, -0.5, z)))
        res.append((p.name, shape))
    return res


def main():
    bad = []
    for p in parts():
        for b in p.boxes:
            if b.x0 < -0.01 or b.x1 > W + 0.01 or b.y0 < -0.01 or b.y1 > D + 0.01 or b.z0 < -0.01 or b.z1 > H + 0.01:
                bad.append(f"{p.name}: {b.what} leaves the box inside")
        print(f"{p.name:18s} {p.note}")
    for c in contents():
        if c.x1 > W or c.y1 > D:
            bad.append(f"{c.what} does not fit the box inside")
    if "--solid" in sys.argv:
        for name, s in solids():
            v = s.val()
            print(f"  solid {name}: valid {v.isValid()}, {v.Volume() / 1000:.1f} cm3")
            if not v.isValid():
                bad.append(f"{name} is not a valid solid")
    for b in bad:
        print("FAIL ", b)
    print(f"cage {'PASS' if not bad else 'FAIL'}: box inside {W:g} x {H:g} x {D:g} mm [TBD-MEASURE]")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
