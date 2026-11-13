"""The printed base and its cage for the TX, parametric. PETG on the Bambu H2D.

The base replaces the #905 (TIBOX) body: 100 mm deep outside, 3 mm walls, mating exactly with the #905's clear
lid and its O-ring: a 9 mm land with a tongue pressing into the lid's O-ring channel, corner blocks with M4 heat-set
inserts under the lid's bosses (Clint's photo); the screw (L1) and the rim test ring's fit are not settled, and `--stl` refuses until
those are measured.
It hangs on its pole by its back, long side vertical. Box frame: Xb across from the inside left wall (seen from the
open lid), Yb from the inside floor (the back as hung) toward the lid, Zb up from the inside bottom wall.

Everything is a horizontal shelf in one stack, each sliding toward the back. Bottom to top:
  - the battery pack (the heaviest part) on a tray just above the gland nuts in the bottom wall;
  - the BQ25798EVM on two ledges (it has no mounting holes; its Bumpon feet come off), J8 toward the lid;
  - B4 POWER, B2 PORTS B + METERS, B1 PORTS A, B3 CORE (the SHTC3 on B3, furthest from the charger's heat),
    each card in a left-wall slot and a right corner post, its bus header in a socket on the PAD3U backplane behind;
  - the retention bar across the cards' front-left.
The spare depth in front of the cards (Yb from the bar to the lid) takes the RJ11 cables' service loops down the right
column to the glands, the EVM leads' service loops, and the coax: AD1's arm points toward the lid and the cable bends
to the SMA bulkhead boss high in the right wall.

Moulded into the base: the corner blocks (hung from the walls under the lid's bosses) with M4 heat-set inserts, the card slots, the right corner
post, the backplane posts, the EVM ledges, the pack tray; outside: gland bosses with nut flats in the bottom wall, an
M12 vent boss, the SMA bulkhead boss, two pole lugs on the back (no screws through it), a drip edge over the top seam.

Run:  python3 cage.py           print the parts and check them against the box inside (no CadQuery needed)
      ../../../.venv-cad/bin/python cage.py --solid   also build the solids in CadQuery and check them
      ../../../.venv-cad/bin/python cage.py --stl     export STL: refused until the lid gate is sourced
      ../../../.venv-cad/bin/python cage.py --ring    the rim test ring from lid-rim-spec.md, checked against it: not gated
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import stack as st  # noqa: E402
from stack import S  # noqa: E402

# ------------------------------------------------------------------ the lid interface and the box
LID_KEYS = ["l2_screw_pos", "l4_oring_proud", "l5_lid_out", "l6_body_rib", "ring_fit"]
SCREW_OPT = S.val("lid_screw_opt")
LID_KEYS += ["l1_lid_screw"] if SCREW_OPT == "a" else ["m4_screw", "m4_washer", "lid_pocket", "insert_m4"]
T = S.val("base_wall")
L_OUT, W_OUT, _r = S.val("l5_lid_out")
BASE_D = S.val("base_out_depth")
W, H = W_OUT - 2 * T, L_OUT - 2 * T
SEAM = BASE_D - T                   # Yb of the base-lid seam (the land)
D = SEAM + S.val("lid_depth") - 1.0 - S.val("gasket")
BOX_IN = (W, H, D)
assert tuple(round(v, 3) for v in BOX_IN) == tuple(S.val("box_in")), (BOX_IN, S.val("box_in"))
RIM_OUT, RIM_CH, RIM_IN = S.val("lid_rim")
LAND = RIM_OUT + RIM_CH + RIM_IN    # 9 mm
TONGUE_W, TONGUE_H, TONGUE_CS, TONGUE_CL = S.val("rim_tongue")   # lip centre from the lid's edge: short, long sides
TONGUE_C = max(TONGUE_CS, TONGUE_CL)
S_RISE, S_RUN = S.val("seal_s")     # the S round each boss, lip centre line to lip centre line
CURVE_R, CURVE_RI = S.val("seal_curve_r")   # outer bends, inner bend
# inside the base wall (box frame): the lip centre lines and the S's two segments
LIP_CX, LIP_CZ = TONGUE_CL - T, TONGUE_CS - T            # along the long walls (Xb), the short walls (Zb)
S_X, S_Z = LIP_CX + S_RUN, LIP_CZ + S_RISE               # the S's segment along Zb at Xb S_X, along Xb at Zb S_Z
LIP_XS, LIP_ZS = LIP_CX + TONGUE_W / 2, LIP_CZ + TONGUE_W / 2   # the land ends at the lip's inner face
LIP = max(LIP_XS, LIP_ZS)
LIP_T = 3.0                         # the land's ledge inside the wall: 3 thick, chamfered under for printing
CORNER_H = S.val("corner_keepout")
CORNER_X, CORNER_Z = S_X + TONGUE_W / 2, S_Z + TONGUE_W / 2   # the corner land, to the lip's inner face round the S
THREAD_D, THREAD_P, THREAD_L = S.val("l1_lid_screw")            # option a
HEAD_D, HEAD_K, SCREW_L = S.val("m4_screw")                       # option b
WASHER_D, WASHER_T = S.val("m4_washer")
POCKET = S.val("lid_pocket")
LID_HOLE = 8.0                                                    # the lid's hole (Clint, L1 "8 mm dia")
_sl, _ss = S.val("l2_screw_pos")
SCREWS = [(x, z) for x in (_ss - T, W - (_ss - T)) for z in (_sl - T, H - (_sl - T))]
INSERT_D, INSERT_L = S.val("insert_m4")
_bore = INSERT_D if SCREW_OPT == "b" else THREAD_D
POST = _ss - T + _bore / 2 + 3.0                        # the post, square from the inside corner (3 mm round the bore)
CORNER = CORNER_Z                   # (for the cards' upper limit: unchanged, the blocks stop above the cards)
EVM = S.val("evm")
EVM_J8 = S.val("evm_j8")
SLOT_CLEAR = S.val("slot_clear")
PACK = S.val("pack")
GLAND = {"PG-7": S.val("gland_pg7"), "PG-9": S.val("gland_pg9")}
GLAND_NUT = {"PG-7": S.val("gland")[1], "PG-9": S.val("gland_pg9_nut")}
M = 2.0                             # the margin every fit check asks for
# the backplane mount (cage/backplane-mount-spec.md): two screw posts, plain pads, the left edge in a groove, the right in a slot
BP_POST_D, BP_POST_BL, BP_FLAT, _bd, _bl, _bf = S.val("bp_post")
BP_BORE = (_bd, _bl)
# screw posts: bottom left under the drilled hole (s0.2, with the flat toward the mux), bottom right under the
# PAD3U's lower factory hole; the board's holes they serve, from the layout (the L7 and section 4 checks compare them)
BP_POSTS = [(7.78, 54.06), (84.09, 54.06)]
BP_HOLES_AT = [st.bp_xy(st.BP_SCREWS[0]), st.BP_FACTORY[st.BP_FACTORY_SCREW]]
BP_POST_WHAT = ["bottom-left (drilled s0.2)", "bottom-right (factory hole)"]
BP_POST_DS = [BP_POST_BL, BP_POST_D]
RSLOT_D, RSLOT_H = S.val("bp_slot")
BAR_INS = S.val("bar_inserts")
BP_PAD_D = 6.0                                           # plain support pads (no screw) under st.BP_SUPPORTS                          # Xb, Zb, Zb, the bar's clearance hole

# ------------------------------------------------------------------ chosen
PLATE = 0.0
Y0 = YP = 0.0                       # the floor's inside face: everything stands on it
WALL = S.val("cage_wall")
BAR = S.val("bar")
SHELF = 2.0                         # pack tray, EVM ledge thickness
CARD_FRONT = st.BP_FRONT + st.Y_BP
Z_LO = st.card_z("B4") - 8.0
Z_HI = min(st.card_z("B3") + 14.0, H - 0.5)
RX = st.CAGE_LEFT + st.BW
BP_BOTTOM = st.BP_Z0 - 2 * st.P
# glands: two rows of four in the bottom wall, the flat weather-meter cables in the PG-9s under the right column
FLAT = {(98.0, 25.0): "wind (flat)", (98.0, 60.0): "rain (flat)"}
GLANDS = [(x, y, "PG-9" if (x, y) in FLAT else "PG-7") for y in (25.0, 60.0) for x in (26.0, 50.0, 74.0, 98.0)]
GLAND_IN = max(g[1] for g in GLAND.values())            # thread length inside the wall (L1)
VENT = (50.0, 85.0)                                     # Xb, Yb in the bottom wall
# shelves, bottom to top
PACK_TRAY_Z = GLAND_IN + M                              # tray underside
PACK_X0, PACK_Z0 = M + 4.0, PACK_TRAY_Z + SHELF             # the pack lies flat: 69 across, 54 back-to-lid, 18 up
EVM_X0 = TONGUE_C + RIM_CH / 2 + RIM_IN - T + M         # clear of the lid's inner channel wall (it reaches into the lid)
EVM_Y0 = st.BP_FRONT + M                                # in front of the backplane's lower end; J8 toward the lid
EVM_Z0 = PACK_Z0 + PACK[2] + M + S.val("evm_under")     # board underside
EVM_TOP = EVM_Z0 + 1.6 + EVM[2]
BULKHEAD_NUT = 11.0                                     # SMA bulkhead jack nut across corners [derived: 3/8 in hex]
_gd, _gh, _gt = S.val("bp_groove")
RAIL_Z0 = max(EVM_TOP + M, BP_POSTS[0][1] + BP_POST_BL / 2 + 0.5)   # the groove rail below the left wall: 2 above
#   the EVM, 0.5 above the bottom-left post
RAIL_Y1 = st.BP_FRONT + _gh + _gd + 1.0                 # the rail's front face: the groove roof plus 1
GROOVE = (WALL - _gd, st.BP_BACK, RAIL_Z0, WALL, st.BP_FRONT + _gh, Z_HI)   # Xb, Yb, Zb from / to: the backplane groove
RSLOT = (st.CAGE_LEFT + st.BW - 2.0, st.BP_BACK, Z_LO, st.CAGE_LEFT + st.BW - 2.0 + RSLOT_D, st.BP_BACK + RSLOT_H, Z_HI)
#   the right corner post's backplane slot (Xb, Yb, Zb from / to): the board's factory right edge


class Part:
    def __init__(self, name, boxes, holes=(), cuts=(), note="", solid=None):
        """boxes less cuts is the envelope the checks use; solid, when given, builds the real shape for --solid
        (a callable taking the box-built shape, or None, and returning the CadQuery shape)."""
        self.name, self.boxes, self.holes, self.cuts, self.note = name, boxes, list(holes), list(cuts), note
        self.solid = solid


def B(x0, y0, z0, x1, y1, z1, what):
    return st.Box(x0, y0, x1, y1, z0, z1, what)


def sq(x, z, r, y0, y1, what):
    return B(x - r, y0, z - r, x + r, y1, z + r, what)


def parts():
    out = []
    # left wall: solid behind the slots, ribs between them
    wall = [B(0, YP, Z_LO, WALL - 2.0, CARD_FRONT + 1.0, Z_HI, "left wall")]
    slots = []
    for b in st.ORDER:
        z = st.card_z(b)
        slots.append(B(WALL - 2.0, st.BP_FRONT, z - st.BT - SLOT_CLEAR / 2, WALL, CARD_FRONT + 1.0,
                       z + SLOT_CLEAR / 2, f"slot for {b}"))
    wall.append(B(WALL - 2.0, YP, Z_LO, WALL, CARD_FRONT + 1.0, Z_HI, "left wall slot side"))
    wall.append(B(0, YP, RAIL_Z0, WALL, RAIL_Y1, Z_LO, "groove rail below the left wall"))
    slots.append(B(*GROOVE[:3], *GROOVE[3:], "backplane groove"))
    out.append(Part("left wall", wall, cuts=slots, solid=left_wall_solid,
                    note="moulded in the base: one 2 mm deep slot per card; cards slide in from the lid side toward the "
                         f"back; the backplane's left edge in a groove (Xb {GROOVE[0]:g}-{GROOVE[3]:g}, Yb {GROOVE[1]:g}-"
                         f"{GROOVE[4]:g}, a 45 degree roof) the wall's full length and down a rail to Zb {RAIL_Z0:.2f}, above the bottom-left post"))
    grip = S.val("sb_snap_y") - 1.5
    post_y1 = CARD_FRONT - grip
    post = [B(RX - 2.0, YP, Z_LO, RX + 6.0, post_y1, Z_HI, "right corner post")]
    pslots = [B(RX - 2.0, st.BP_FRONT, st.card_z(b) - st.BT - SLOT_CLEAR / 2, RX + SLOT_CLEAR, post_y1 + 0.1,
                st.card_z(b) + SLOT_CLEAR / 2, f"post slot for {b}") for b in st.ORDER]
    pslots.append(B(*RSLOT[:3], *RSLOT[3:], "backplane slot"))
    for b in ("B1", "B2"):
        z = st.card_z(b)
        nxt = st.ORDER[st.ORDER.index(b) + 1]
        pslots.append(B(RX - 2.0, CARD_FRONT - st.BOB_Y[2] - 0.5, z, RX + 6.0, post_y1 + 0.1,
                        st.card_z(nxt) - st.BT - SLOT_CLEAR / 2 - 2.0, f"post cut round {b}'s back jack and plug"))
    out.append(Part("right corner post", post, cuts=pslots, solid=right_post_solid,
                    note=f"moulded: takes each card's back-right corner (card Y {grip:.2f}-{st.CD:.2f}); on B1 and B2 "
                         f"the back breakout's spacer tongue (card Y {st.CD:.2f}-{st.TONGUE_Y1:.2f}) instead"))
    posts = [B(x - d / 2, YP, z - d / 2, x + (BP_FLAT if i == 0 else d / 2), st.BP_BACK, z + d / 2, "backplane post")
             for i, ((x, z), d) in enumerate(zip(BP_POSTS, BP_POST_DS))]
    r = BP_PAD_D / 2
    out.append(Part("backplane support pads", [B(x - r, YP, z - r, x + r, st.BP_BACK, z + r, "backplane support pad")
                                               for x, z in (st.bp_xy(h) for h in st.BP_SUPPORTS)],
                    note=f"plain \u00d8{BP_PAD_D:g} pads {st.BP_BACK:g} tall under {', '.join(st.BP_SUPPORTS)} (no screw, no "
                         "hole in the board), printed in enclosure 2: they take the cards' push"))
    out.append(Part("backplane posts", posts, solid=bp_post_solids,
                    note=f"two round screw posts {st.BP_BACK:g} tall from the floor (bottom left \u00d8{BP_POST_BL:g} with a "
                         f"flat {BP_FLAT:g} from its centre toward the mux, under the drilled s0.2; bottom right "
                         f"\u00d8{BP_POST_D:g} under the PAD3U's lower factory hole), M3 heat-set inserts (bore "
                         f"\u00d8{BP_BORE[0]:g} x {BP_BORE[1]:g}); the left edge in the left wall's groove and its rail, the "
                         "factory right edge in the right corner post's slot"))
    out.append(Part("retention bar", [B(0, CARD_FRONT + 1.0, Z_LO, 12.0, CARD_FRONT + 1.0 + BAR, Z_HI, "retention bar")],
                    solid=bar_solid,
                    note=f"separate: two M3 screws (\u00d8{BAR_INS[3]:g} holes) into inserts in the left wall's front face at "
                         f"Xb {BAR_INS[0]:g}, Zb {BAR_INS[1]:g} and {BAR_INS[2]:g}; off before any card comes out"))
    # EVM ledges: the board's left and right edges rest on 2 mm ledges, a stop at the back, a snap clip at the front
    ez = EVM_Z0 - SHELF
    out.append(Part("charger ledges", [
        B(0, YP, ez, EVM_X0 + 2.0, SEAM - LIP_T, EVM_Z0, "charger ledge, left wall"),
        B(EVM_X0 + EVM[0] - 2.0, YP, ez, EVM_X0 + EVM[0] + 2.0, SEAM - LIP_T, EVM_Z0, "charger ledge, right rib"),
        B(EVM_X0 + EVM[0] - 2.0, YP, PACK_TRAY_Z + SHELF, EVM_X0 + EVM[0] + 2.0, M, ez, "charger right rib, from the floor")],
        note=f"moulded: the EVM slides back on two 2 mm ledges at Zb {ez:g}-{EVM_Z0:g} (no mounting holes; Bumpons off), "
             "a snap clip at the front; its underside parts (J6) clear the ledges [TBD-MEASURE]"))
    out.append(Part("pack tray", [B(PACK_X0 - 2.0, YP, PACK_TRAY_Z, PACK_X0 + PACK[0] + 2.0, PACK[1] + 4.0,
                                    PACK_TRAY_Z + SHELF, "pack tray"),
                                  B(PACK_X0 - 2.0, PACK[1] + 2.0, PACK_TRAY_Z + SHELF, PACK_X0 + PACK[0] + 2.0,
                                    PACK[1] + 4.0, PACK_TRAY_Z + SHELF + 6.0, "pack tray front lip")],
                    note=f"moulded from the floor, {M:g} mm over the gland nuts; the pack lies flat, slides back, a "
                         "hook-and-loop strap through the tray"))
    return out


def left_wall_solid(shape):
    """The groove's 45 degree roof (from Xb GROOVE x0 at its top up to the wall face, so it prints without support)
    and the retention bar's two insert bores in the wall's front face."""
    import cadquery as cq
    x0, y0, z0, x1, y1, z1 = GROOVE
    tri = (cq.Workplane("XY").polyline([(x0, y1), (x1 + 0.01, y1), (x1 + 0.01, y1 + (x1 + 0.01 - x0))]).close()
           .extrude(z1 - z0).translate((0, 0, z0)))
    shape = shape.cut(tri)
    front = CARD_FRONT + 1.0
    for z in BAR_INS[1:3]:
        shape = shape.cut(cq.Workplane("XZ").circle(BP_BORE[0] / 2).extrude(-BP_BORE[1])
                          .translate((BAR_INS[0], front - BP_BORE[1], z)))
    return shape


def right_post_solid(shape):
    """The backplane slot's 45 degree roof in the right corner post (from the slot's end at its top up to the post's
    face), so it prints without support."""
    import cadquery as cq
    x0, y0, z0, x1, y1, z1 = RSLOT
    tri = (cq.Workplane("XY").polyline([(x1, y1), (x0 - 0.01, y1), (x0 - 0.01, y1 + (x1 - x0))]).close()
           .extrude(z1 - z0).translate((0, 0, z0)))
    return shape.cut(tri)


def bar_solid(shape):
    """The retention bar's clearance holes, through it along Yb."""
    import cadquery as cq
    for z in BAR_INS[1:3]:
        shape = shape.cut(cq.Workplane("XZ").circle(BAR_INS[3] / 2).extrude(-(BAR + 2))
                          .translate((BAR_INS[0], CARD_FRONT - 0.5, z)))
    return shape


def bp_post_solids(_shape):
    """The three backplane posts: round, a fillet at the foot, the insert bore from the top, the bottom-left flat."""
    import cadquery as cq
    f, top = S.val("bp_post")[5], st.BP_BACK
    c = (f * (1 - 0.5 ** 0.5), f * (1 - 0.5 ** 0.5))
    shape = None
    for i, ((x, z), d) in enumerate(zip(BP_POSTS, BP_POST_DS)):
        r = d / 2
        prof = (cq.Workplane("XY").moveTo(0, 0).lineTo(r + f, 0).threePointArc((r + c[0], c[1]), (r, f))
                .lineTo(r, top).lineTo(0, top).close())
        p = prof.revolve(360, (0, 0, 0), (0, 1, 0)).translate((x, YP, z))
        p = p.cut(cq.Workplane("XZ").circle(BP_BORE[0] / 2).extrude(-BP_BORE[1]).translate((x, top - BP_BORE[1], z)))
        if i == 0:
            p = p.cut(cq.Workplane("XY").box(10, top + 2, 20, centered=False).translate((x + BP_FLAT, -1, z - 10)))
        shape = p if shape is None else shape.union(p)
    return shape


def backplane_checks():
    """cage/backplane-mount-spec.md section 4: the post and pad tops, the groove and the slot floors level with the
    copper face; the screw posts on the drilled hole and on the lower factory hole; nothing printed in the board's slab
    but the groove and the slot over its edges; the fit (right edge tilted to the slot's end, the left edge clear of
    the left wall's face on the way down, then slid left into the groove); the screw heads; the mux. Returns
    (lines, faults)."""
    bad = []
    x0, z0, x1, z1 = st.BP_OUTLINE
    yb, yf = st.BP_BACK, st.BP_FRONT
    for p in parts():
        for b in p.boxes:
            if b.what in ("backplane post", "backplane support pad") and abs(b.y1 - yb) > 0.1:
                bad.append(f"a {b.what}'s top is at Yb {b.y1:g}, not the board's {yb:g}")
    for name, fl in (("groove", GROOVE[1]), ("right slot", RSLOT[1])):
        if abs(fl - yb) > 0.1:
            bad.append(f"the {name} floor is at Yb {fl:g}, not the board's {yb:g}")
    for (x, z), (hx, hz), what in zip(BP_POSTS, BP_HOLES_AT, BP_POST_WHAT):
        if abs(x - hx) > 0.01 or abs(z - hz) > 0.01:
            bad.append(f"the {what} post at ({x:.2f}, {z:.2f}) is not on its hole ({hx:.2f}, {hz:.2f})")
    printed = [(n, b) for n, b in fixed_boxes() if n != "retention bar"]   # the bar goes on after the cards

    def hits(ax0, ax1, ay0, ay1, why, az0=z0, az1=z1, what="the backplane outline"):
        out = []
        for n, b in printed:
            if b.x0 < ax1 - 0.02 and ax0 < b.x1 - 0.02 and b.y0 < ay1 - 0.02 and ay0 < b.y1 - 0.02 and \
                    b.z0 < az1 - 0.02 and az0 < b.z1 - 0.02:
                if n == "left wall" and b.x1 <= GROOVE[3] + 0.01 and b.y0 >= GROOVE[4] - 0.01:
                    continue                                   # the groove's roof over the board's left edge
                if n == "right corner post" and b.x0 >= RSLOT[0] - 0.01 and b.y0 >= RSLOT[4] - 0.01:
                    continue                                   # the slot's roof over its right edge
                out.append(f"{n}: {b.what} (Xb {b.x0:.2f}-{b.x1:.2f}, Yb {b.y0:.2f}-{b.y1:.2f}, Zb {b.z0:.2f}-"
                           f"{b.z1:.2f}) is inside {what} {why}")
        return out
    bad += hits(x0, x1, yb, SEAM, "above its copper face (Yb 8), outside the groove and the slot")
    # the fit: tilt the right edge in to the slot's end, lower the left side, slide left into the groove
    ins = RSLOT[3] - x1                                       # how far right the board goes to the slot's end
    left_clear = x0 + ins - WALL
    if left_clear < 0.2:
        bad.append(f"pushed to the right slot's end, the board's left edge (Xb {x0 + ins:.2f}) is {left_clear:.2f} "
                   f"from the left wall's face (Xb {WALL:g}): it cannot come down past it")
    bad += hits(x0 + ins, x1 + ins, yb, SEAM, f"pushed {ins:.2f} to the right (to the slot's end) on its way in")
    engage_r, engage_l = x1 - (RX - 2.0), GROOVE[3] - x0
    if engage_r < 0.8 or engage_l < 0.8:
        bad.append(f"the board's edges sit only {engage_r:.2f} (right, in the slot) and {engage_l:.2f} (left, in the "
                   "groove) under their roofs: at least 0.8 each")
    hd, hk = S.val("m3_button")
    head_notes = []
    for (hx, hz), what in zip(BP_POSTS, BP_POST_WHAT):
        near = sorted((li, ni) for li, ni in st.BP_USED if math.hypot(st.strip_x(li) - hx, st.bp_xy(f"s0.{ni}")[1] - hz)
                      < hd / 2 + 1.0)
        if near:
            bad.append(f"the {what} screw head covers used holes {near}")
        bad += hits(hx - hd / 2, hx + hd / 2, yf, yf + hk, "", hz - hd / 2, hz + hd / 2, f"the {what} screw head")
        if EVM_X0 < hx + hd / 2 and hx - hd / 2 < EVM_X0 + EVM[0] and EVM_Z0 < hz + hd / 2 and hz - hd / 2 < EVM_TOP:
            gap = EVM_Y0 - (yf + hk)
            head_notes.append(f"{what} head {gap:.2f} from the EVM envelope")
            if gap < 0.0:
                bad.append(f"the {what} screw head meets the EVM envelope")
    ring = S.val("pad3u_mount")[1]
    fx, fz = st.BP_FACTORY["upper right"]
    if fx + ring / 2 > x1 or any(math.hypot(st.strip_x(li) - fx, st.bp_xy(f"s0.{ni}")[1] - fz) < ring / 2 + 1.0
                                for li, ni in st.BP_USED):
        bad.append("the unused upper factory hole meets the board's edge or a used pad")
    mx0, mz0, mx1, mz1 = st.MUX_BOX
    gap = 99.0
    for dx in (0.0, ins):
        for p in parts():
            for b in p.boxes:
                if b.what in ("backplane post", "backplane support pad") and b.z0 < mz1 and mz0 < b.z1:
                    g = (b.x0 - (mx1 + dx)) if b.x0 >= mx1 + dx else (mx0 + dx - b.x1)
                    gap = min(gap, g)
                    if g < 0.0:
                        bad.append(f"the mux (moved {dx:.2f}) meets the {b.what} at Xb {b.x0:.2f}-{b.x1:.2f}")
    lines = [f"backplane mount: screw posts " + ", ".join(f"{w} ({x:.2f}, {z:.2f}) \u00d8{d:g}" for (x, z), d, w in
                                                         zip(BP_POSTS, BP_POST_DS, BP_POST_WHAT))
             + f"; plain pads under {', '.join(st.BP_SUPPORTS)}; tops, the groove and the slot floors at Yb {yb:g}; "
             f"outline Xb {x0:.2f}-{x1:.2f}, Zb {z0:.2f}-{z1:.2f}; right edge {engage_r:.2f} into the slot (to Xb "
             f"{RSLOT[3]:.2f}), left {engage_l:.2f} into the groove; the fit: {ins:.2f} to the right, left edge "
             f"{left_clear:.2f} clear of the wall's face coming down; mux {gap:.2f} from a post or pad (both positions); "
             f"groove and rail from Zb {GROOVE[2]:.2f}" + ("; " + ", ".join(head_notes) if head_notes else "")]
    return lines, bad


def corners():
    """(x0, x1, z0, z1) of the four inside corners, as (sx, sz) signs: +1 from the low wall, -1 from the high one."""
    return [(sx, sz) for sx in (1, -1) for sz in (1, -1)]


def corner_box(sx, sz, rx, rz, y0, y1, what):
    x0, x1 = (0, rx) if sx > 0 else (W - rx, W)
    z0, z1 = (0, rz) if sz > 0 else (H - rz, H)
    return B(x0, y0, z0, x1, y1, z1, what)


def box_keepouts():
    """What the base and the lid put inside. The base: the corner lands at the seam (a 3 mm shelf under each lid
    boss and its O-ring S-curve), the insert posts hung below them, the rim lip all round, the glands' threads and
    nuts on the bottom wall. The lid (its names start "lid"; off when a card comes out): its inner channel wall and
    its corner bosses, from the seam to the lid's top."""
    yl = SEAM - LIP_T
    out = [corner_box(sx, sz, CORNER_X, CORNER_Z, yl, SEAM, "corner land (lid boss and O-ring curve)") for sx, sz in corners()]
    out += [corner_box(sx, sz, POST, POST, SEAM - CORNER_H, yl, "corner insert post (lid screw)") for sx, sz in corners()]
    out += [B(0, yl, 0, LIP_XS, SEAM, H, "rim lip, left"), B(W - LIP_XS, yl, 0, W, SEAM, H, "rim lip, right"),
            B(0, yl, 0, W, SEAM, LIP_ZS, "rim lip, bottom"), B(0, yl, H - LIP_ZS, W, SEAM, H, "rim lip, top")]
    inner = TONGUE_C + RIM_CH / 2 + RIM_IN - T              # the lid's inner channel wall reaches this far inside
    out += [B(0, SEAM, 0, inner, D, H, "lid inner channel wall"), B(W - inner, SEAM, 0, W, D, H, "lid inner channel wall"),
            B(0, SEAM, 0, W, D, inner, "lid inner channel wall"), B(0, SEAM, H - inner, W, D, H, "lid inner channel wall")]
    out += [corner_box(sx, sz, CORNER_X, CORNER_Z, SEAM, D, "lid corner boss and channel") for sx, sz in corners()]
    for x, y, k in GLANDS:
        r = GLAND_NUT[k] / 2
        out.append(B(x - r, y - r, 0, x + r, y + r, GLAND[k][1], f"{k} gland at Xb {x:g}, Yb {y:g}"))
    return out


def tongue():
    """The tongue's centre line (x, z) points, closed: along each wall at TONGUE_C - T inside, and round each corner
    boss in the lid's S-curve (in along the boss's inner face, round its corner, out to the next wall)."""
    cx, cz, bx, bz = LIP_CX, LIP_CZ, S_X, S_Z              # (square corners here: the ring has the R bends)
    return [(cx, bz), (bx, bz), (bx, cz),                  # bottom-left corner (Zb 0 is the bottom wall)
            (W - bx, cz), (W - bx, bz), (W - cx, bz),
            (W - cx, H - bz), (W - bx, H - bz), (W - bx, H - cz),
            (bx, H - cz), (bx, H - bz), (cx, H - bz), (cx, bz)]


def floor_ribs():
    return []


def gland_boxes():
    return [(k, GLAND_NUT[k] / 2, B(x - GLAND_NUT[k] / 2, y - GLAND_NUT[k] / 2, 0, x + GLAND_NUT[k] / 2,
                                     y + GLAND_NUT[k] / 2, GLAND[k][1], f"{k} gland at Xb {x:g}, Yb {y:g}"))
            for x, y, k in GLANDS]


def mux_box():
    x0, z0, x1, z1 = st.MUX_BOX
    y1 = st.BP_BACK - S.val("foam")
    return B(x0, y1 - 4.8, z0, x1, y1, z1, "PCA9548 mux on foam")


def contents():
    """The pack and the charger in their places (box frame), for the checks and the drawings."""
    return [B(PACK_X0, YP + 2.0, PACK_Z0, PACK_X0 + PACK[0], YP + 2.0 + PACK[1], PACK_Z0 + PACK[2],
              "battery pack #353 (shelf)"),
            B(EVM_X0, EVM_Y0, EVM_Z0, EVM_X0 + EVM[0], EVM_Y0 + EVM[1], EVM_TOP, "BQ25798EVM (shelf)"),
            B(EVM_X0 + 30.0, EVM_Y0 + EVM[1], EVM_Z0, EVM_X0 + 45.0, EVM_Y0 + EVM[1] + EVM_J8, EVM_Z0 + 10.0,
              "BQ25798EVM J8 (toward the lid)"),
            B(EVM_X0, EVM_Y0, EVM_Z0 - S.val("evm_under"), EVM_X0 + EVM[0], EVM_Y0 + EVM[1], EVM_Z0,
              "BQ25798EVM underside (J6, tails)")]


def shell():
    """The printed base's walls and outside features (box frame; outside the inside volume)."""
    out = [B(-T, -T, -T, W + T, 0, H + T, "floor (back)"),
           B(-T, 0, -T, 0, SEAM, H + T, "left wall"), B(W, 0, -T, W + T, SEAM, H + T, "right wall"),
           B(0, 0, -T, W, SEAM, 0, "bottom wall"), B(0, 0, H, W, SEAM, H + T, "top wall")]
    yl = SEAM - LIP_T
    out += [B(0, yl, 0, LIP_XS, SEAM, H, "rim lip"), B(W - LIP_XS, yl, 0, W, SEAM, H, "rim lip"),
            B(LIP_XS, yl, 0, W - LIP_XS, SEAM, LIP_ZS, "rim lip"), B(LIP_XS, yl, H - LIP_ZS, W - LIP_XS, SEAM, H, "rim lip")]
    out += [corner_box(sx, sz, CORNER_X, CORNER_Z, yl, SEAM, "corner land") for sx, sz in corners()]
    out += [corner_box(sx, sz, POST, POST, SEAM - CORNER_H, yl, "corner post (lid screw)") for sx, sz in corners()]
    h, pts = TONGUE_W / 2, tongue()
    for (xa, za), (xb, zb) in zip(pts, pts[1:]):
        out.append(B(min(xa, xb) - h, SEAM, min(za, zb) - h, max(xa, xb) + h, SEAM + TONGUE_H, max(za, zb) + h,
                     "tongue into the lid's O-ring channel"))
    for z in (30.0, H - 30.0):
        out.append(B(W / 2 - 15, -T - 10.0, z - 6, W / 2 + 15, -T, z + 6, "pole lug (hose-clamp slot)"))
    out.append(B(-T - 2.0, SEAM - 6.0, H + T, W + T + 2.0, SEAM, H + T + 2.0, "drip edge over the top seam"))
    for x, y, k in GLANDS:
        r = GLAND_NUT[k] / 2 + 1.0
        out.append(B(x - r, y - r, -T - 3.0, x + r, y + r, -T, f"{k} gland boss (nut flats)"))
    out.append(B(VENT[0] - 8, VENT[1] - 8, -T - 3.0, VENT[0] + 8, VENT[1] + 8, -T, "vent boss"))
    return out


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
        if p.solid is not None:
            shape = p.solid(shape)
        res.append((p.name, shape))
    return res


def coax(arm):
    """The coax from AD1's forward arm: the straight plug toward the lid, the RG-316 bend to the right, a straight
    run (dropping under the upper corner post if it must) to the bulkhead boss in the right wall. Returns (plug end Yb, bulkhead Yb, bulkhead Zb, axis Xb)."""
    ax, az = (arm.x0 + arm.x1) / 2, (arm.z0 + arm.z1) / 2
    pe = arm.y1 + S.val("sma_plug_len")
    zb = min(az, H - CORNER_Z - BULKHEAD_NUT / 2 - M - 1.0)    # the cable drops to clear the corner block
    yb = min(pe + S.val("rg316_bend"), SEAM - LIP_T - BULKHEAD_NUT / 2 - M - 0.5)   # and stays under the rim lip
    return pe, yb, zb, ax


# ------------------------------------------------------------------ the rim test ring, straight from cage/lid-rim-spec.md
# (the spec's frame: origin at the lid centre, X along the long side, Y along the short side, Z up from the bed)
import lid_rim_spec as RS  # noqa: E402

RING_PRINT = 3.6                    # min per cm3 on the H2D: coupon r1, 5.6 cm3 in about 20 minutes (Clint)
H2D_BED = (325.0, 320.0)            # Bambu H2D build plate, one nozzle (bambulab.com H2D specs)


def ring_path():
    """The lip centre line, closed and anticlockwise from the +X short side at Y 0: the spec's quadrant, then mirrored
    about Y, both, and X. Each segment is ("line", a, b) or ("arc", a, b, centre, r, sense); a mirror and a reversal
    each flip an arc's sense, so every arc keeps the sense the table gives it."""
    q = RS.load()["quadrant"]

    def f(seg, fx, fy, rev):
        m = [(p[0] * fx, p[1] * fy) for p in seg[1:4 if seg[0] == "arc" else 3]]
        a, b = (m[1], m[0]) if rev else (m[0], m[1])
        return ("line", a, b) if seg[0] == "line" else ("arc", a, b, m[2], seg[4], seg[5])
    return ([f(x, 1, 1, False) for x in q] + [f(x, -1, 1, True) for x in reversed(q)]
            + [f(x, -1, -1, False) for x in q] + [f(x, 1, -1, True) for x in reversed(q)])


def ring_edges():
    import cadquery as cq
    out = []
    for sg in ring_path():
        a, b = cq.Vector(*sg[1], 0), cq.Vector(*sg[2], 0)
        if sg[0] == "line":
            out.append(cq.Edge.makeLine(a, b))
        else:
            c = cq.Vector(*sg[3], 0)
            mid = c + ((a + b) * 0.5 - c).normalized() * sg[4]
            out.append(cq.Edge.makeThreePointArc(a, mid, b))
    return out


def ring_prism(off, z0, h):
    """The region inside the lip centre line grown by off (outward +), from z0, h tall."""
    import cadquery as cq
    w = cq.Wire.assembleEdges(ring_edges())
    if off:
        w = w.offset2D(off, "arc")[0]
    return cq.Workplane("XY").add(cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), cq.Vector(0, 0, h))).translate((0, 0, z0))


def ring_solid():
    """The ring: the land (Z 0-3.5) from the outline in to the lip's inner face, nothing inside it; the 2 x 4.5 lip on
    top; four 7 mm holes."""
    import cadquery as cq
    sp = RS.load()
    L, Wd = sp["outline"]
    lw, _lh = sp["lip_w"], sp["lip_h"]
    land_h, top = sp["land_z"][1], sp["lip_z"][1]
    outer = cq.Workplane("XY").rect(L, Wd).extrude(top).edges("|Z").fillet(sp["corner_r"])
    land = outer.intersect(cq.Workplane("XY").rect(L + 10, Wd + 10).extrude(land_h)).cut(ring_prism(-lw / 2, -1, top + 2))
    lip = ring_prism(lw / 2, land_h, top - land_h).cut(ring_prism(-lw / 2, land_h - 1, top)).intersect(outer)
    shape = land.union(lip)
    hx, hy = sp["holes"]
    for x in (hx, -hx):
        for y in (hy, -hy):
            shape = shape.cut(cq.Workplane("XY").circle(sp["hole_d"] / 2).extrude(top + 2).translate((x, y, -1)))
    return shape


def ring_checks(solid=None):
    """The ring against the spec: the segment table, the mirrors, the spans and the spec's stated checks, tangency on
    the built edges, the hole-to-lip clearance. Returns (lines to print, faults)."""
    import cadquery as cq
    sp = RS.load()
    d = RS.derived(sp)
    bad = ["spec table: " + x for x in RS.check(sp)]
    path = ring_path()
    pts = [p for sg in path for p in (sg[1:4] if sg[0] == "arc" else sg[1:3])]
    key = {(round(x, 6), round(y, 6)) for x, y in pts}
    for x, y in key:
        for m in ((-x, y), (x, -y), (-x, -y)):
            if (round(m[0], 6) + 0.0, round(m[1], 6) + 0.0) not in {(a + 0.0, b + 0.0) for a, b in key}:
                bad.append(f"mirror: ({x:g}, {y:g}) has no partner at ({m[0]:g}, {m[1]:g})")
    for i in range(len(path)):
        if math.dist(path[i][2], path[(i + 1) % len(path)][1]) > 1e-6:
            bad.append(f"path: segment {i} does not meet segment {(i + 1) % len(path)}")
    edges = ring_edges()
    worst = 0.0
    for i, e in enumerate(edges):
        t0, t1 = e.tangentAt(1.0), edges[(i + 1) % len(edges)].tangentAt(0.0)
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, t0.dot(t1))))))
    if worst > 1e-3:
        bad.append(f"tangency: a {worst:.4f} degree kink in the built path")
    xs = max(abs(sg[1][0]) for sg in path if sg[0] == "line" and sg[1][0] == sg[2][0])
    ys = max(abs(sg[1][1]) for sg in path if sg[0] == "line" and sg[1][1] == sg[2][1])
    if abs(2 * xs - sp["spans_stated"][0]) > 1e-6 or abs(2 * ys - sp["spans_stated"][1]) > 1e-6:
        bad.append(f"spans: built {2 * xs:g} x {2 * ys:g}, the spec says {sp['spans_stated'][0]:g} x {sp['spans_stated'][1]:g}")
    spec_notes = []
    for side, v in (("short", d["inset_short"]), ("long", d["inset_long"])):
        if abs(v - sp["inset_stated"]) > 1e-6:
            spec_notes.append(f"the {side}-side straight lip is {v:g} in from the outline, the spec's check says "
                              f"{sp['inset_stated']:g}")
    for what, v in (("S depth, short side", d["s_short"]), ("S depth, long side", d["s_long"])):
        if abs(v - sp["s_stated"]) > 1e-6:
            spec_notes.append(f"{what} {v:g}, the spec's check says {sp['s_stated']:g}")
    if abs(d["r_mid"] - sp["r_mid_stated"]) > 1e-6 or any(abs(r - sp["r_outer_stated"]) > 1e-6 for r in d["r_outer"]):
        spec_notes.append("a bend radius differs from the spec's stated check")
    lip = (ring_prism(sp["lip_w"] / 2, 0, 1).cut(ring_prism(-sp["lip_w"] / 2, -1, 3))).val()
    hx, hy = sp["holes"]
    clr = [lip.distance(cq.Vertex.makeVertex(x, y, 0.5)) - sp["hole_d"] / 2 for x in (hx, -hx) for y in (hy, -hy)]
    if min(clr) < sp["clear_stated"] - 1e-6:
        bad.append(f"hole to lip: {min(clr):.2f}, the spec asks at least {sp['clear_stated']:g}")
    L, Wd = sp["outline"]
    edge = min(L / 2 - hx, Wd / 2 - hy) - sp["hole_d"] / 2
    lines = [f"ring path: {len(path)} segments, {sum(1 for sg in path if sg[0] == 'arc')} arcs, the worst joint "
             f"{worst:.1e} degrees off tangent; spans {2 * xs:g} x {2 * ys:g} centre to centre",
             "hole to lip: " + ", ".join(f"{c:.2f}" for c in clr) + f" (spec: at least {sp['clear_stated']:g}); "
             f"hole to the outline {edge:.2f}"]
    if solid is not None:
        v = solid.val().Volume() / 1000
        bb = solid.val().BoundingBox()
        fits = bb.xlen <= H2D_BED[0] and bb.ylen <= H2D_BED[1]
        lines.append(f"ring: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, {v:.1f} cm3, about "
                     f"{v * RING_PRINT:.0f} min on the H2D; flat on its {H2D_BED[0]:g} x {H2D_BED[1]:g} bed: "
                     f"{'yes' if fits else 'NO'}")
        if not solid.val().isValid():
            bad.append("the ring is not a valid solid")
    return lines + ["SPEC INCONSISTENT: " + n for n in spec_notes], bad


def write_ring():
    import cadquery as cq
    sol = ring_solid()
    out = HERE / "stl" / "rim-ring.stl"
    out.parent.mkdir(exist_ok=True)
    cq.exporters.export(sol, str(out))
    return out, sol


def st_top_boxes():
    """B3's parts in the box frame (the top card)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "layout"))
    import layout_checks as lc
    return [lc.to_box("B3", x) for _r, x in lc.board_boxes("B3") if not x.service] + [lc.card_slab("B3")]


def stl_gate():
    """The lid interface must be measured (sourced) before any print file is made."""
    return [k for k in LID_KEYS if S.D[k][3] != "sourced"]


def main():
    bad = []
    for p in parts():
        for b in p.boxes:
            if b.x0 < -0.01 or b.x1 > W + 0.01 or b.y0 < -0.01 or b.y1 > D + 0.01 or b.z0 < -0.01 or b.z1 > H + 0.01:
                bad.append(f"{p.name}: {b.what} leaves the box inside")
        print(f"{p.name:18s} {p.note}")
    keep = box_keepouts()
    items = [b for _n, b in fixed_boxes()]
    for name, b in fixed_boxes():
        for k in keep:
            if b.x0 < k.x1 - 0.02 and k.x0 < b.x1 - 0.02 and b.y0 < k.y1 - 0.02 and k.y0 < b.y1 - 0.02 and \
                    b.z0 < k.z1 - 0.02 and k.z0 < b.z1 - 0.02:
                bad.append(f"{name}: {b.what} meets the base's {k.what}")
    # the shelves: each content clear of the walls, the corner posts, the glands, the cage parts and each other by M
    cont = contents()
    for c in cont:
        if c.x0 < M - 0.01 or c.x1 > W - M + 0.01 or c.y0 < M - 0.01 or c.y1 > D - M + 0.01 or c.z0 < M - 0.01:
            bad.append(f"{c.what}: less than {M:g} mm to a wall")
        for o in keep + [b for n, b in fixed_boxes() if n not in ("charger ledges", "pack tray")]:
            g = B(o.x0 - M, o.y0 - M, o.z0 - M, o.x1 + M, o.y1 + M, o.z1 + M, o.what)
            if c.x0 < g.x1 and g.x0 < c.x1 and c.y0 < g.y1 and g.y0 < c.y1 and c.z0 < g.z1 and g.z0 < c.z1:
                bad.append(f"{c.what}: less than {M:g} mm to the {o.what}")
    blines, bbad = backplane_checks()
    for ln in blines:
        print(ln)
    bad += bbad
    m = mux_box()
    if m.y0 < M - 0.01:
        bad.append(f"the mux is {m.y0:.1f} mm off the floor (needs {M:g})")
    if EVM_TOP + M > BP_BOTTOM + 0.01 and EVM_Y0 < st.BP_FRONT + M - 0.01:
        bad.append(f"the EVM (top {EVM_TOP:.1f}) meets the backplane's lower end (from {BP_BOTTOM:.1f}): move it forward")
    if EVM_TOP + M > st.card_z("B4") - st.BT - S.val("tails") + 0.01:
        bad.append("the EVM is within 2 mm of B4's underside")
    under_b4 = st.card_z("B4") - st.BT - S.val("tails")
    gl = gland_boxes()
    for i, (ka, ra, a) in enumerate(gl):
        for kb, rb, b in gl[i + 1:]:
            xa, ya, xb, yb = (a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2, (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            dist = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
            if dist < ra + rb + 1.0:
                bad.append(f"gland pitch: {a.what} and {b.what} are {dist:.1f} apart, the nuts need {ra + rb + 1:.1f}")
        if a.y1 > SEAM - M:
            bad.append(f"{a.what}: past the seam")
    pmin = min((((a.x0 + a.x1 - b.x0 - b.x1) ** 2 + (a.y0 + a.y1 - b.y0 - b.y1) ** 2) ** 0.5 / 2 - ra - rb)
               for i, (_ka, ra, a) in enumerate(gl) for _kb, rb, b in gl[i + 1:])
    print(f"glands: {len(gl)} in the bottom wall, the closest nuts {pmin:.1f} mm apart; vent at Xb {VENT[0]:g}, Yb {VENT[1]:g}")
    print(f"shelves (Zb): glands to {GLAND_IN:g}; pack tray {PACK_TRAY_Z:g}, pack {PACK_Z0:g}-{PACK_Z0 + PACK[2]:g}; "
          f"EVM underside parts {EVM_Z0 - S.val('evm_under'):g}, board {EVM_Z0:g}, top {EVM_TOP:g}; backplane from "
          f"{BP_BOTTOM:.1f}; B4 underside {under_b4:.1f}; top card B3 {st.card_z('B3'):.1f}")
    print(f"base: outside {L_OUT:g} x {W_OUT:g} x {BASE_D:g} (PETG, {T:g} mm walls), inside {W:g} x {H:g}, seam at Yb "
          f"{SEAM:g}, closed depth {D:g}; a {LAND:g} mm land ({RIM_OUT:g} + {RIM_CH:g} channel + {RIM_IN:g}, Clint) with a "
          f"{TONGUE_W:g} x {TONGUE_H:g} sealing lip {TONGUE_CS:g} in from the outside edge on the short sides, "
          f"{TONGUE_CL:g} on the long (lid-rim-spec.md), its S {S_RISE:g} x {S_RUN:g} with R {CURVE_R:g} outer and R {CURVE_RI:g} inner bends, into the "
          f"lid's O-ring channel (its top "
          f"where r3 had it, about 1 mm into the O-ring set 2 mm down, an assumed 3 mm round cord; the land 1.5 lower); corner lands {CORNER_Z:g} x {CORNER_X:g}, insert posts "
          f"{POST:g} square, {CORNER_H:g} deep; lid "
          + (f"screws: option (b), M4 stainless, {WASHER_D:g} mm washers over the lid's {LID_HOLE:g} mm holes, into M4 "
             "heat-set inserts at " if SCREW_OPT == "b" else f"screws: option (a), a printed M{THREAD_D:g} thread at ")
          + ", ".join(f"({x:g}, {z:g})" for x, z in SCREWS) + " [TBD-MEASURE]")
    for x, z in SCREWS:
        if min(x, W - x) + INSERT_D / 2 + 3.0 > POST + 0.01:
            bad.append(f"the lid screw at ({x:g}, {z:g}) needs more than the corner post")
        if min(x, W - x) - INSERT_D / 2 < -T + 0.01:
            bad.append(f"the lid screw at ({x:g}, {z:g}) is in the wall")
    if INSERT_L + 3.0 > CORNER_H:
        bad.append("the corner block is shorter than the insert and 3 mm under it")
    if SCREW_OPT == "b":
        if WASHER_D < LID_HOLE + 2.0:
            bad.append(f"the {WASHER_D:g} mm washer seats less than 1 mm round the lid's {LID_HOLE:g} mm hole")
        if WASHER_D + 1.0 > POCKET:
            bad.append(f"the {WASHER_D:g} mm washer does not fit the lid's {POCKET:g} mm corner pocket")
        if HEAD_D > WASHER_D:
            bad.append("the screw head is wider than its washer")
        print(f"lid screws (b): M4 x {SCREW_L:g} stainless pan head ({HEAD_D:g} head) on a {WASHER_D:g} x {WASHER_T:g} "
              f"washer: {(WASHER_D - LID_HOLE) / 2:g} mm of seat round the lid's {LID_HOLE:g} mm hole, "
              f"{(POCKET - WASHER_D) / 2:g} mm to the {POCKET:g} mm pocket's walls [TBD-MEASURE]; outside the O-ring, "
              "so no seal at the holes")
    lip6 = S.val("l6_body_rib")[1] - (S.val("base_905")[1] - W_OUT) / 2
    print(f"sealing lip: {TONGUE_CS:g} / {TONGUE_CL:g} in from the lid's edge (short / long sides); Clint's rough 1-2 mm in "
          f"from the original base's edge would be about {lip6:.2f} in from the lid's edge, under its outer wall "
          f"(0-{RIM_OUT:g}): it disagrees; the scan (lid-rim-spec.md) settles it")
    if "--ring" in sys.argv:
        out, sol = write_ring()
        print(f"ring STL written: {out} (not gated)")
        lines, rbad = ring_checks(sol)
        for ln in lines:
            print(ln)
        bad += rbad
    if "--stl" in sys.argv and stl_gate():
        print("STL REFUSED: the lid interface is not settled yet: " + ", ".join(stl_gate()))
        sys.exit(2)
    if "--solid" in sys.argv or "--stl" in sys.argv:
        for name, s in solids():
            v = s.val()
            print(f"  solid {name}: valid {v.isValid()}, {v.Volume() / 1000:.1f} cm3")
            if not v.isValid():
                bad.append(f"{name} is not a valid solid")
    if "--stl" in sys.argv:
        missing = stl_gate()
        if missing:
            print("STL REFUSED: the lid interface is not measured yet: " + ", ".join(missing))
            sys.exit(2)
    else:
        missing = stl_gate()
        print("STL gate: " + ("open" if not missing else "closed until these are sourced: " + ", ".join(missing)
                                + " (L1 the screw, and the rim test ring's fit on the real lid)"))
    for b in bad:
        print("FAIL ", b)
    print(f"cage {'PASS' if not bad else 'FAIL'}: base inside {W:g} x {H:g} x {D:g} mm [TBD-MEASURE: the lid gate]")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
