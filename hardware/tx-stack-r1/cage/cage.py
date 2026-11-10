"""The printed base and its cage for the TX, parametric. PETG on the Bambu H2D.

The base replaces the #905 (TIBOX) body: 100 mm deep outside, 3 mm walls, mating exactly with the #905's clear
lid and its O-ring: a 9 mm land with a tongue pressing into the lid's O-ring channel, corner blocks with M4 heat-set
inserts under the lid's bosses (Clint's photo); the screw (L1) and the rim coupon's fit are not settled, and `--stl` refuses until
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
      ../../../.venv-cad/bin/python cage.py --coupon  the rim test-fit coupon (one corner, 45 x 45 x 8): not gated
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import stack as st  # noqa: E402
from stack import S  # noqa: E402

# ------------------------------------------------------------------ the lid interface and the box
LID_KEYS = ["l2_screw_pos", "l4_oring_proud", "l5_lid_out", "l6_body_rib", "coupon_fit"]
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


class Part:
    def __init__(self, name, boxes, holes=(), cuts=(), note=""):
        self.name, self.boxes, self.holes, self.cuts, self.note = name, boxes, list(holes), list(cuts), note


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
    out.append(Part("left wall", wall, cuts=slots, note="moulded in the base: one 2 mm deep slot per card; cards slide "
                    "in from the lid side toward the back"))
    grip = S.val("sb_snap_y") - 1.5
    post_y1 = CARD_FRONT - grip
    post = [B(RX - 2.0, YP, Z_LO, RX + 6.0, post_y1, Z_HI, "right corner post")]
    pslots = [B(RX - 2.0, st.BP_FRONT, st.card_z(b) - st.BT - SLOT_CLEAR / 2, RX + SLOT_CLEAR, post_y1 + 0.1,
                st.card_z(b) + SLOT_CLEAR / 2, f"post slot for {b}") for b in st.ORDER]
    for b in ("B1", "B2"):
        z = st.card_z(b)
        nxt = st.ORDER[st.ORDER.index(b) + 1]
        pslots.append(B(RX - 2.0, CARD_FRONT - st.BOB_Y[2] - 0.5, z, RX + 6.0, post_y1 + 0.1,
                        st.card_z(nxt) - st.BT - SLOT_CLEAR / 2 - 2.0, f"post cut round {b}'s back jack and plug"))
    out.append(Part("right corner post", post, cuts=pslots,
                    note=f"moulded: takes each card's back-right corner (card Y {grip:.2f}-{st.CD:.2f}); on B1 and B2 "
                         f"the back breakout's spacer tongue (card Y {st.CD:.2f}-{st.TONGUE_Y1:.2f}) instead"))
    posts = []
    for x in (st.strip_x(0), st.strip_x(20)):
        for z in (st.bp_xy(f"s0.{n}")[1] for n in st.BP_SCREW_HOLES):
            posts.append(B(x - 3.0, YP, z - 3.0, x + 3.0, st.BP_BACK, z + 3.0, "backplane post"))
    out.append(Part("backplane posts", posts, note=f"four posts {st.BP_BACK:g} mm tall from the floor, M3 heat-set "
                    f"inserts, screws through lines 0 and 20, holes {' and '.join(str(n) for n in st.BP_SCREW_HOLES)}"))
    out.append(Part("retention bar", [B(0, CARD_FRONT + 0.5, Z_LO, 12.0, CARD_FRONT + 0.5 + BAR, Z_HI, "retention bar")],
                    note="separate: two M3 screws into the left wall's front face; off before any card comes out"))
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
    cx, cz, bx, bz = LIP_CX, LIP_CZ, S_X, S_Z              # (square corners here: the coupon has the R bends)
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


COUPON = (45.0, 45.0, 8.0)          # the test-fit coupon (r3): one rim corner, outside footprint x height; at least
CORNER_R = S.val("corner_r_out")    #   10 mm of straight lip past each outer bend
COUPON_GHOST = dict(cs=4.0, cl=3.5, rise=20.0, run=30.0, r=10.0)   # r2's lip, ghosted on the drawing


def coupon_seal_points(cs=None, cl=None, rise=None, run=None, far=90.0):
    """The seal's centre line in the coupon frame (x along the short side, z along the long side, from the lid's
    outside corner; the base's outside is the lid's): up the long-side leg cl in, along the S's segment at
    z = cs + rise, down the S's segment at x = cl + run, out along the short-side leg cs in. Returned as the
    corners of the region on the box's inside of the line (closed far outside the coupon)."""
    cs = TONGUE_CS if cs is None else cs
    cl = TONGUE_CL if cl is None else cl
    rise = S_RISE if rise is None else rise
    run = S_RUN if run is None else run
    return [(cl, far), (cl, cs + rise), (cl + run, cs + rise), (cl + run, cs), (far, cs), (far, far)]


def rounded_wire(pts, r, bends=(1, 2, 3)):
    """r is one radius, or one per bend (in the order of bends)."""
    rs = dict(zip(bends, r if isinstance(r, (tuple, list)) else [r] * len(bends)))
    return _rounded_wire(pts, rs)


def _rounded_wire(pts, rs):
    """A closed CadQuery wire through pts, the 90-degree corners at the indices in rs rounded at rs[i] (tangent
    arcs between straights parallel to the edges)."""
    import cadquery as cq
    n = len(pts)

    def unit(a, b):
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)

    w = None
    seq = []
    for i, p in enumerate(pts):
        if i in rs:
            r = rs[i]
            d1, d2 = unit(pts[i - 1], p), unit(p, pts[(i + 1) % n])
            p1 = (p[0] - r * d1[0], p[1] - r * d1[1])
            p2 = (p[0] + r * d2[0], p[1] + r * d2[1])
            c = (p1[0] + r * d2[0], p1[1] + r * d2[1])
            k = ((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2) ** 0.5
            mid = (c[0] + r * (p[0] - c[0]) / k, c[1] + r * (p[1] - c[1]) / k)
            seq.append(("arc", p1, mid, p2))
        else:
            seq.append(("pt", p))
    start = seq[0][1]
    w = cq.Workplane("XY").moveTo(*start)
    cur = start
    for item in seq[1:] + [seq[0]]:
        if item[0] == "pt":
            if item[1] != cur:
                w = w.lineTo(*item[1])
            cur = item[1]
        else:
            _k, p1, mid, p2 = item
            if (abs(p1[0] - cur[0]) + abs(p1[1] - cur[1])) > 1e-9:
                w = w.lineTo(*p1)
            w = w.threePointArc(mid, p2)
            cur = p2
    return w.close().wires().val()


def seal_region(off, z0, h, **geom):
    """The box-inside region of the seal line (its bends rounded), grown by off (shrunk if < 0), as a prism."""
    import cadquery as cq
    r = geom.pop("r", (CURVE_R, CURVE_RI, CURVE_R))
    wire = rounded_wire(coupon_seal_points(**geom), r).offset2D(off, "arc")[0]
    return cq.Workplane("XY").add(wire).toPending().extrude(h).translate((0, 0, z0))


def coupon_solid():
    """The coupon (r2) as a CadQuery solid: the land from the outside edge to the lip's inner face (nothing inside
    the lip, round the S too), solid from the underside (it prints flat), the 2 x 3 sealing lip on its centre line
    (4.0 in on the short side, 3.5 on the long, the S's outer bends at CURVE_R, its inner bend at CURVE_RI), the outside corner at CORNER_R, and the
    7 mm screw hole. Its own frame: x, y in plan from the outside corner, z up from the underside."""
    import cadquery as cq
    cx, cz, ch = COUPON
    land_h = ch - TONGUE_H
    sq = (cq.Workplane("XY").rect(cx, cz, centered=False).extrude(ch).edges("|Z")
          .edges(cq.selectors.NearestToPointSelector((0, 0, ch / 2))).fillet(CORNER_R))
    land = sq.cut(seal_region(-TONGUE_W / 2, -1.0, ch + 2.0))                 # to the lip's inner face
    land = land.cut(cq.Workplane("XY").box(cx + 10, cz + 10, TONGUE_H + 1, centered=False).translate((-5, -5, land_h)))
    lip = seal_region(TONGUE_W / 2, land_h, TONGUE_H).cut(seal_region(-TONGUE_W / 2, land_h - 1, TONGUE_H + 2))
    shape = land.union(lip.intersect(sq))
    sx, sz = SCREWS[0]
    return shape.cut(cq.Workplane("XY").circle(S.val("coupon_bore") / 2).extrude(ch).translate((sx + T, sz + T, 0)))


def write_coupon():
    import cadquery as cq
    out = HERE / "stl" / "rim-coupon.stl"
    out.parent.mkdir(exist_ok=True)
    cq.exporters.export(coupon_solid(), str(out))
    return out


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
          f"{TONGUE_CL:g} on the long (coupon r1 fit), its S {S_RISE:g} x {S_RUN:g} with R {CURVE_R:g} outer and R {CURVE_RI:g} inner bends, into the "
          f"lid's O-ring channel (about "
          f"{TONGUE_H + S.val('l4_oring_proud'):g} mm squeeze on an assumed 3 mm round cord set 2 mm down); corner lands {CORNER_Z:g} x {CORNER_X:g}, insert posts "
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
          f"(0-{RIM_OUT:g}): it disagrees; the coupon settles it")
    if "--coupon" in sys.argv:
        out = write_coupon()
        print(f"coupon STL written: {out} (not gated)")
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
                                + " (L1 the screw, and the rim coupon's fit on the real lid)"))
    for b in bad:
        print("FAIL ", b)
    print(f"cage {'PASS' if not bad else 'FAIL'}: base inside {W:g} x {H:g} x {D:g} mm [TBD-MEASURE: the lid gate]")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
