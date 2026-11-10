"""The printed card cage for the TX, parametric. PLA on the Bambu H2D; no print files yet (no STL).

The box (Adafruit #905, a TIBOX 125 x 175 x 75: a 50 mm base and a 25 mm clear lid tray of the same footprint, no
lip into the base; walls not tapered) hangs on its pole by its floor, long side vertical. Box frame: Xb across
from the inside left wall (seen from the open lid), Yb from the inside floor (the back wall as hung) toward the
lid, Zb up from the inside bottom wall. The corner screw posts fill the four corners over the full depth.

The floor (Clint's labelled photo, 2026-11-10; the inputs are named after his measurement sheet M1-M13):
  A1, A2  the maker's mounting-plate posts with brass inserts, on the centre line: the cage base screws to them;
  B1-B4   plain posts with holes in a rectangle, C1, C2 figure-8 posts on the cross rib: kept clear and
          reachable through cut-outs in the cage base;
  D1, D2  locating tabs beside A1 and A2: the base is notched for them;
  ribs    a strip down the centre line and a band across mid-length: the base rests on them.

The cage is one base plate the size of the maker's mounting plate (DS-1217P, 157 x 109), carrying:
  - the left wall with one slot per card (the cards are horizontal shelves, inserted from the lid side);
  - the right corner post that takes each card's back-right corner in a slot;
  - four posts that hold the backplane (PAD3U padboard) off the base, copper side back;
  - the retention bar, screwed across the front-left of the card stack after the cards are in;
  - the power zone below the cards: the BQ25798EVM standing parallel to the floor in an edge cradle, in front of
    the backplane; the battery pack standing in front of it on a tray along the bottom wall, strapped.
The cable glands are in the right wall, below the jacks (the power zone and the corner posts leave no room for
them in the bottom wall).

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
BOX_IN = S.val("box_in")            # inside width x length x depth (floor to closed lid)
W, H, D = BOX_IN
SEAM = S.val("m12_base_depth")      # Yb of the base-lid seam (M12)
CORNER = S.val("corner_keepout")    # corner screw posts, along each wall from the corner
POST_D = S.val("post_d")            # A, B, C post diameter
A_X = W / 2                         # A1, A2 on the centre line
A1_Z = H - S.val("m5_a_wall")       # M5
A2_Z = A1_Z - S.val("m1_a_span")    # M1
A_H = S.val("m8_a_h")               # M8
A_SCREW = S.val("m9_a_thread")      # M9: M4
A_CLEAR = 4.5                       # M4 clearance over the A posts (the head sits on the plate: nothing above it)
B_CLEAR = 3.4                       # over the B posts: M3 (or No. 4) self-tapping screws into the blind bores
_b0x, _bz = S.val("m6_b_wall"), S.val("m3_b_along")
B_POSTS = [(_b0x, H / 2 + _bz / 2), (_b0x + S.val("m2_b_across"), H / 2 + _bz / 2),
           (_b0x, H / 2 - _bz / 2), (_b0x + S.val("m2_b_across"), H / 2 - _bz / 2)]     # B1, B2, B3, B4 (M2, M3, M6)
C_POSTS = [((W - S.val("m4_c_span")) / 2, H / 2), ((W + S.val("m4_c_span")) / 2, H / 2)]  # C1, C2 (M4)
B_H, C_H = S.val("m10_bc_h")        # M10
RIB_H, RIB_W = S.val("m7_rib")      # M7
_d = S.val("d_tab")
D_TABS = [(A_X + _d[0], A1_Z + _d[1]), (A_X + _d[2], A2_Z + _d[3])]
PLATE_W, PLATE_H = S.val("mount_plate")
EVM = S.val("evm")                  # BQ25798EVM board outline x tallest part
SLOT_CLEAR = S.val("slot_clear")    # card slot width over 1.6 mm (print tuning)
PACK = S.val("pack")                # battery pack (sourced)
GLAND = {"PG-7": S.val("gland_pg7"), "PG-9": S.val("gland_pg9")}
GLAND_NUT = {"PG-7": S.val("gland")[1], "PG-9": S.val("gland_pg9_nut")}

# ------------------------------------------------------------------ chosen
PLATE = S.val("cage_plate")         # base plate thickness
Y0 = st.FLOOR_LIFT                  # base underside: on the A, B and C posts (7 mm), over the 1 mm ribs
YP = Y0 + PLATE                     # base top face
WALL = S.val("cage_wall")           # left wall thickness; slots 2 mm deep
BAR = S.val("bar")                  # retention bar thickness
SHELF = 3.0                         # pack tray thickness
CARD_FRONT = st.BP_FRONT + st.Y_BP  # Yb of the cards' front edges
Z_LO = st.card_z("B4") - 8.0        # left wall and post from here ...
Z_HI = min(st.card_z("B3") + 14.0, H - CORNER - 0.5)   # ... to here, under the upper corner posts
RX = st.CAGE_LEFT + st.BW           # cards' right edges
BP_WIN = (st.BP_Z0 - 2 * st.P + 3.0, st.BP_Z0 + (st.BP_HOLES + 1) * st.P - 3.0)   # Zb of the window
# the charger stands parallel to the floor, its parts toward the lid (the terminal screws face the lid), in front
# of the backplane's front pins; turned so its J8 (right-angle, past one edge) points left
EVM_X0, EVM_Z0 = 20.0, SHELF + 0.5
EVM_Y0 = st.BP_FRONT + 8.5 + 0.5    # in front of the charger I2C pins (XJ1) on the backplane
BP_BOTTOM = st.BP_Z0 - 2 * st.P     # Zb of the backplane's lower edge
PACK_X0 = EVM_X0 + (EVM[0] - PACK[0]) / 2
PACK_Y0 = EVM_Y0 + 1.6 + EVM[2] + 1.8   # the pack stands on its long edge: 69 across, 18 deep, 54 up
# glands: two columns of four in the right wall, below the jacks, in the base (short of the seam). Not the bottom
# wall: the pack tray and the charger cover Xb 20-100 there and the corner posts Xb 0-15 and 106-121; the strip left
# (Xb 100-106) is narrower than a gland nut. The two flat weather-meter cables (wind, rain) take PG-9s (#761) with the
# seal out and the gap packed; the six round port cables take PG-7s (#762).
FLAT = {(14.0, 87.5): "wind (flat)", (14.0, 45.5): "rain (flat)"}
GLANDS = [(y, z, "PG-9" if (y, z) in FLAT else "PG-7") for z in (24.5, 45.5, 66.5, 87.5) for y in (14.0, 36.0)]


class Part:
    def __init__(self, name, boxes, holes=(), cuts=(), note=""):
        self.name, self.boxes, self.holes, self.cuts, self.note = name, boxes, list(holes), list(cuts), note


def B(x0, y0, z0, x1, y1, z1, what):
    return st.Box(x0, y0, x1, y1, z0, z1, what)


def sq(x, z, r, y0, y1, what):
    return B(x - r, y0, z - r, x + r, y1, z + r, what)


def parts():
    out = []
    pz0 = (H - PLATE_H) / 2
    c = CORNER + 0.5
    plate = [B(0.5, Y0, pz0, W - 0.5, YP, H - pz0, "back plate")]
    cuts = [B(0.5, Y0, pz0, c, YP, c, "notch: lower left corner post"),
            B(0.5, Y0, H - c, c, YP, H - pz0, "notch: upper left corner post"),
            B(W - c, Y0, pz0, W - 0.5, YP, c, "notch: lower right corner post"),
            B(W - c, Y0, H - c, W - 0.5, YP, H - pz0, "notch: upper right corner post")]
    gz = [z for _y, z, _k in GLANDS]
    cuts.append(B(W - 9.0, Y0, min(gz) - 12.0, W - 0.5, YP, max(gz) + 12.0, "notch: the glands' locknuts"))
    cuts += [sq(x, z, POST_D / 2 + 0.5, Y0, YP, f"notch: {n} tab") for n, (x, z) in zip(("D1", "D2"), D_TABS)]
    # behind the backplane, between its posts: the socket tails, the bus wires and the mux reach down through here
    cuts.append(B(st.strip_x(0) + 3.0, Y0, BP_WIN[0], st.strip_x(20) - 3.0, YP, BP_WIN[1], "window behind the backplane"))
    holes = [(A_X, z, A_CLEAR, "y") for z in (A1_Z, A2_Z)] + [(x, z, B_CLEAR, "y") for x, z in B_POSTS]
    out.append(Part("back plate", plate, cuts=cuts, holes=holes,
                    note=f"base plate {W - 1:g} x {PLATE_H:g} (the maker's DS-1217P length, the box's width) on the A, B "
                         f"and C posts ({A_H:g} mm); an M4 x 10 socket-head screw and washer into each A brass insert "
                         f"(holes {A_CLEAR:g} mm; 3 mm plate + washer + about 6 mm engaged), an M{S.val('b_screw'):g} self-tapper into each B post "
                         f"(holes {B_CLEAR:g} mm, size [TBD-MEASURE]); C1 and C2 bear only; notched for D1, D2 and the "
                         "corner posts; a window behind the backplane"))
    # left wall: solid behind the slots, ribs between them
    wall = [B(0, YP, Z_LO, WALL - 2.0, CARD_FRONT + 1.0, Z_HI, "left wall")]
    slots = []
    for b in st.ORDER:
        z = st.card_z(b)
        slots.append(B(WALL - 2.0, st.BP_FRONT, z - st.BT - SLOT_CLEAR / 2, WALL, CARD_FRONT + 1.0,
                       z + SLOT_CLEAR / 2, f"slot for {b}"))
    wall.append(B(WALL - 2.0, YP, Z_LO, WALL, CARD_FRONT + 1.0, Z_HI, "left wall slot side"))
    out.append(Part("left wall", wall, cuts=slots, note="one 2 mm deep slot per card; cards enter from the lid side"))
    # the right corner post reaches 1.5 mm onto every card's snapped back edge; on B1 and B2 the back RJ11 breakout
    # overhangs that edge, so there the post is cut away around the jack and the plug, and grips the breakout's
    # printed spacer tongue (in the card plane, card Y CD..TONGUE_Y1) instead
    grip = S.val("sb_snap_y") - 1.5
    post_y1 = CARD_FRONT - grip
    post = [B(RX - 2.0, YP, Z_LO, RX + 6.0, post_y1, Z_HI, "right corner post")]
    pslots = [B(RX - 2.0, st.BP_FRONT, st.card_z(b) - st.BT - SLOT_CLEAR / 2, RX + SLOT_CLEAR, post_y1 + 0.1,
                st.card_z(b) + SLOT_CLEAR / 2, f"post slot for {b}") for b in st.ORDER]
    for b in ("B1", "B2"):            # clear over the back jack and plug up to 2 mm under the next card's slot
        z = st.card_z(b)
        nxt = st.ORDER[st.ORDER.index(b) + 1]
        pslots.append(B(RX - 2.0, CARD_FRONT - st.BOB_Y[2] - 0.5, z, RX + 6.0, post_y1 + 0.1,
                        st.card_z(nxt) - st.BT - SLOT_CLEAR / 2 - 2.0, f"post cut round {b}'s back jack and plug"))
    out.append(Part("right corner post", post, cuts=pslots,
                    note=f"takes each card's back-right corner (card Y {grip:.2f}-{st.CD:.2f}); on B1 and B2 the back "
                         f"breakout's spacer tongue (card Y {st.CD:.2f}-{st.TONGUE_Y1:.2f}) instead"))
    posts = []
    for x in (st.strip_x(0), st.strip_x(20)):
        for z in (st.bp_xy(f"s0.{n}")[1] for n in st.BP_SCREW_HOLES):
            posts.append(B(x - 3.0, YP, z - 3.0, x + 3.0, st.BP_BACK, z + 3.0, "backplane post"))
    out.append(Part("backplane posts", posts, note=f"four posts {S.val('bp_posts'):g} mm tall, M3 screws through "
                    f"lines 0 and 20, holes {' and '.join(str(n) for n in st.BP_SCREW_HOLES)} (drilled 3.2 mm)"))
    out.append(Part("retention bar", [B(0, CARD_FRONT + 0.5, Z_LO, 12.0, CARD_FRONT + 0.5 + BAR, Z_HI, "retention bar")],
                    note="two M3 screws into the left wall's front face; off before any card comes out"))
    # power zone
    # the EVM has no mounting holes (TI SLUUCB5 Fig. 4-1): a cradle grips its edges. Its bottom edge drops into a
    # groove on the pack tray, its side edges into two channels open toward the lid, each with a snap clip at the
    # front; the left channel stops under the backplane. The Bumpon feet (H1-H4) come off first: they would stand
    # 5.1 mm behind the board, into the backplane's sockets.
    ch_y0, ch_y1 = YP, EVM_Y0 + 1.6 + 1.5
    out.append(Part("charger cradle", [
        B(EVM_X0 - 2.0, ch_y0, EVM_Z0 - 0.5, EVM_X0 + 2.0, ch_y1, BP_BOTTOM - 1.0, "charger cradle left channel"),
        B(EVM_X0 + EVM[0] - 2.0, ch_y0, EVM_Z0 - 0.5, EVM_X0 + EVM[0] + 2.0, ch_y1, EVM_Z0 + EVM[1],
          "charger cradle right channel")],
        cuts=[B(EVM_X0 - 0.2, EVM_Y0 - 0.1, EVM_Z0 - 0.5, EVM_X0 + EVM[0] + 0.2, EVM_Y0 + 1.7, EVM_Z0 + EVM[1] + 0.1,
                "charger board slot")],
        note=f"two edge channels (the EVM has no mounting holes), the bottom edge in a groove on the pack tray, snap "
             f"clips at the front; the Bumpon feet peeled off first; outline [TBD-MEASURE]"))
    py1 = PACK_Y0 + PACK[2] + 2.0
    out.append(Part("pack tray", [B(PACK_X0 - 3.0, YP, 0.0, PACK_X0 + PACK[0] + 3.0, py1, SHELF, "pack tray"),
                                  B(PACK_X0 - 3.0, py1 - 2.0, SHELF, PACK_X0 + PACK[0] + 3.0, py1, SHELF + 8.0,
                                    "pack tray front lip")],
                    note="a tray along the bottom wall, joined to the base's lower edge; the pack stands on it in front of the charger, "
                         "a hook-and-loop strap through the tray holds it"))
    return out


def box_keepouts():
    """What the box itself puts inside: the four corner screw posts (full depth) and the floor's posts, tabs and
    ribs (A posts excepted, drawn by the renders: the base sits on all the posts and screws to A and B)."""
    c = CORNER
    out = [B(x0, 0, z0, x1, D, z1, "corner screw post")
           for x0, x1 in ((0, c), (W - c, W)) for z0, z1 in ((0, c), (H - c, H))]
    r = POST_D / 2
    out += [sq(x, z, r, 0, B_H, f"floor post {n}") for n, (x, z) in zip(("B1", "B2", "B3", "B4"), B_POSTS)]
    out += [sq(x, z, r, 0, C_H, f"floor post {n}") for n, (x, z) in zip(("C1", "C2"), C_POSTS)]
    out += [sq(x, z, r, 0, A_H, f"floor tab {n}") for n, (x, z) in zip(("D1", "D2"), D_TABS)]
    return out


def floor_ribs():
    return [B(A_X - RIB_W / 2, 0, 0, A_X + RIB_W / 2, RIB_H, H, "floor rib, centre line"),
            B(0, 0, H / 2 - RIB_W / 2, W, RIB_H, H / 2 + RIB_W / 2, "floor rib, across mid-length")]


def gland_boxes():
    """Each gland's inside part (thread and locknut) as a box at the right wall, with its kind and its nut radius."""
    out = []
    for y, z, k in GLANDS:
        r = GLAND_NUT[k] / 2
        out.append((k, r, B(W - GLAND[k][1], y - r, z - r, W, y + r, z + r, f"{k} gland at Yb {y:g}, Zb {z:g}")))
    return out


def mux_box():
    """The mux on its foam, behind the backplane, reaching down through the base's window."""
    x0, z0, x1, z1 = st.MUX_BOX
    y1 = st.BP_BACK - S.val("foam")
    return B(x0, y1 - 4.8, z0, x1, y1, z1, "PCA9548 mux on foam")


def contents():
    """The pack and the charger in their places (box frame), for the checks and the drawings."""
    return [B(PACK_X0, PACK_Y0, SHELF, PACK_X0 + PACK[0], PACK_Y0 + PACK[2], SHELF + PACK[1],
                            "battery pack #353 (standing)"),
            B(EVM_X0, EVM_Y0, EVM_Z0, EVM_X0 + EVM[0], EVM_Y0 + 1.6 + EVM[2], EVM_Z0 + EVM[1],
              "BQ25798EVM (standing, outline TBD)"),
            B(EVM_X0 - S.val("evm_j8"), EVM_Y0, EVM_Z0 + EVM[1] - 22.0, EVM_X0, EVM_Y0 + 1.6 + 8.5,
              EVM_Z0 + EVM[1] - 12.0, "BQ25798EVM J8 (past its edge)")]


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
    keep = box_keepouts() + floor_ribs()
    for name, b in fixed_boxes():
        for k in keep:
            if b.x0 < k.x1 - 0.02 and k.x0 < b.x1 - 0.02 and b.y0 < k.y1 - 0.02 and k.y0 < b.y1 - 0.02 and \
                    b.z0 < k.z1 - 0.02 and k.z0 < b.z1 - 0.02:
                bad.append(f"{name}: {b.what} meets the box's {k.what}")
    for k in keep + [b for _n, b in fixed_boxes()]:
        m = mux_box()
        if m.x0 < k.x1 and k.x0 < m.x1 and m.y0 < k.y1 and k.y0 < m.y1 and m.z0 < k.z1 and k.z0 < m.z1:
            bad.append(f"the mux meets the {k.what}")
    gl = gland_boxes()
    for k, r, g in gl:
        if g.y0 < 0 or g.y1 > SEAM - 1.0:
            bad.append(f"{g.what}: its nut leaves the base wall (Yb 0..{SEAM - 1:g})")
        for o in keep + [b for _n, b in fixed_boxes()] + contents():
            if g.x0 < o.x1 and o.x0 < g.x1 and g.y0 < o.y1 and o.y0 < g.y1 and g.z0 < o.z1 and o.z0 < g.z1:
                bad.append(f"{g.what} meets the {o.what}")
    for i, (ka, ra, a) in enumerate(gl):
        for kb, rb, b in gl[i + 1:]:
            ya, za, yb, zb = (a.y0 + a.y1) / 2, (a.z0 + a.z1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2
            dist = ((ya - yb) ** 2 + (za - zb) ** 2) ** 0.5
            if dist < ra + rb + 1.0:
                bad.append(f"gland pitch: {a.what} and {b.what} are {dist:.1f} apart, the nuts need {ra + rb + 1:.1f}")
    pmin = min((((a.y0 + a.y1 - b.y0 - b.y1) ** 2 + (a.z0 + a.z1 - b.z0 - b.z1) ** 2) ** 0.5 / 2 - ra - rb)
               for i, (_ka, ra, a) in enumerate(gl) for _kb, rb, b in gl[i + 1:])
    print(f"glands: {len(gl)} in the right wall, the closest nuts {pmin:.1f} mm apart")
    print(f"mux: Yb {mux_box().y0:.1f}..{mux_box().y1:.1f}, {mux_box().y0 - max(A_H, B_H, C_H):.1f} mm over the posts' tops")
    print(f"box: seam at Yb {SEAM:g} (M12, Clint); inside depth {D:g} (48 + 25 less {S.val('gasket'):g} gasket allowance "
          f"[TBD-MEASURE]); base plate on the posts (underside Yb {Y0:g}), screwed to A1, A2 (Xb {A_X:g}, Zb {A1_Z:g}, "
          f"{A2_Z:g}) and B1-B4; screw sizes [TBD-MEASURE]")
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
