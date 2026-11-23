"""The printed base and its cage for the TX, parametric. PETG on the Bambu H2D.

The base is enclosure 4 (Clint's print, audited 2026-11-17 in sheets/audit-enc4) with its two fixes: 120 mm deep outside
(a 3 mm floor, walls to Yb 117 with a 2 x 2.5 sealing lip on their inside edge), long walls 4.25 and short walls 4.0
thick, outside corners R9; four corner blocks 15.4 square, floor to wall top, with the lid-screw bores in them; it
mates with the #905's clear lid (whose O-ring and screws are not settled: `--stl` refuses until they are measured).
It hangs on its pole by its back, long side vertical. Box frame: Xb across from the lid frame's left edge (the inside
left wall is at Xb 1.25; seen from the open lid), Yb from the inside floor (the back as hung) toward the lid, Zb up
from the lid frame's bottom edge (the inside bottom wall is at Zb 1.0). The frame is the lid outline less 3 all round
(W x H 123.5 x 169.5), kept so the lid, the sheets and the renders share it.

Everything is a horizontal shelf in one stack, each sliding toward the back. Bottom to top:
  - the battery pack (the heaviest part) on a tray above the gland pockets in the bottom wall;
  - the BQ25798EVM on two ledges (it has no mounting holes; its Bumpon feet come off), J8 toward the lid;
  - B4 POWER, B2 PORTS B + METERS, B1 PORTS A, B3 CORE (the SHTC3 on B3, furthest from the charger's heat),
    each card in a left-wall slot and a right corner post, its bus header in a socket on the PAD3U backplane behind;
  - the retention bar across the cards' front-left.
The spare depth in front of the cards (Yb from the bar to the lid) takes the RJ11 plugs (B1's and B2's jacks face the
lid) and their cables' bends down to the glands, the EVM leads' service loops, and the coax: AD1's arm points toward
the lid and the cable bends right and runs down the right column to the SMA bulkhead low in the right wall (enclosure 4:
Yb 94.14, Zb 60.38).

Moulded into the base: the corner blocks with the lid-screw bores, the card slots, the right corner post, the
backplane's support pads (no screw posts since enclosure 4: the cards hold the backplane), the EVM ledge, keeper, fin
and lid-end block, the pack tray and its support; in the bottom wall the gland and vent holes over 1 mm pockets; the
SMA bulkhead hole in the right wall; outside, two mounting flanges on the short ends (two slots each, a gusset).
No outside bosses and no drip edge (enclosure 4 has none).

Run:  python3 cage.py           print the parts and check them against the box inside (no CadQuery needed)
      ../../../.venv-cad/bin/python cage.py --solid   also build the solids in CadQuery and check them
      ../../../.venv-cad/bin/python cage.py --stl     export STL: refused until the lid gate is sourced
      ../../../.venv-cad/bin/python cage.py --ring    the rim test ring from lid-rim-spec.md, checked against it: not gated
      ../../../.venv-cad/bin/python cage.py --shade   the white lid shade (cage/stl/lid-shade.stl): not gated
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
LID_KEYS += ["l1_lid_screw"] if SCREW_OPT == "a" else ["lid_screw_opt"]   # (c): Clint's printed bolts (2026-11-17)
T = S.val("base_wall")              # the floor, and the lid frame's margin
L_OUT, W_OUT, _r = S.val("l5_lid_out")
BASE_D = S.val("base_out_depth")
W, H = W_OUT - 2 * T, L_OUT - 2 * T   # the lid frame (123.5 x 169.5): to_lid, the sheets and the renders use it
IN_X0, IN_X1, IN_Z0, IN_Z1 = S.val("enc_inside")   # the real inside faces (enclosure 4)
SEAM = S.val("enc_wall_top")        # Yb of the wall top (the base-lid seam)
assert abs(SEAM - (BASE_D - T)) < 1e-6, (SEAM, BASE_D, T)
D = SEAM + S.val("lid_depth") - 1.0 - S.val("gasket")
BOX_IN = (IN_X1 - IN_X0, IN_Z1 - IN_Z0, D)
OUT_R = S.val("enc_outer_r")
BLK, BLK_R, BLK_F = S.val("enc_blocks")             # corner blocks: square, inner corner radius, wall fillet
BORE_D, BORE_Y0, CHAMF_Y0, CHAMF_D = S.val("enc_lid_bores")
LIP_W, LIP_H = S.val("enc_lip")
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
CORNER_X, CORNER_Z = S_X + TONGUE_W / 2, S_Z + TONGUE_W / 2   # the corner land, to the lip's inner face round the S
THREAD_D, THREAD_P, THREAD_L = S.val("l1_lid_screw")            # option a
LID_HOLE = 8.0                                                    # the lid's hole (Clint, L1 "8 mm dia")
_sl, _ss = S.val("l2_screw_pos")
SCREWS = [(x, z) for x in (_ss - T, W - (_ss - T)) for z in (_sl - T, H - (_sl - T))]
CORNER = BLK                        # the corner blocks reach this far in from the inside faces, floor to wall top
EVM = S.val("evm")
EVM_J8 = S.val("evm_j8")
EVM_J8_X = S.val("evm_j8_x")
EVM_OVL, EVM_OVR = S.val("evm_overhang")
SLOT_CLEAR = S.val("slot_clear")
PACK = S.val("pack")
GLAND = {"PG-7": S.val("gland_pg7"), "PG-9": S.val("gland_pg9")}
GLAND_NUT = {"PG-7": S.val("gland")[1], "PG-9": S.val("gland_pg9_nut")}
M = 2.0                             # the margin every fit check asks for
# the backplane mount (cage/backplane-mount-spec.md): two screw posts, plain pads, the left edge in a groove, the right in a slot
# no screw posts since enclosure 4 (Clint, 2026-11-17: the cards plugged into it hold the backplane in place)
BP_BORE = S.val("bar_bore")                              # the retention bar's insert bores
RSLOT_D, RSLOT_H = S.val("bp_slot")
BAR_INS = S.val("bar_inserts")
BP_PAD_D = 6.0                                           # plain support pads (no screw) under st.BP_SUPPORTS                          # Xb, Zb, Zb, the bar's clearance hole

# ------------------------------------------------------------------ chosen
PLATE = 0.0
Y0 = YP = 0.0                       # the floor's inside face: everything stands on it
WALL = S.val("cage_wall")
BAR = S.val("bar")
SHELF = 2.0                         # EVM ledge thickness
TRAY_T = 3.0                        # pack tray thickness: it spans from the left wall to the right fin
LIP_Y0 = S.val("pack")[1] + 2.0     # the tray's front lip starts at the pack's front (it lies at Yb 2-56)
TRAY_Y1 = LIP_Y0 + 6.0              # the 45 degree lip ramp rises 6 to the tray's front edge (enclosure 4 fix 1)
BP_SLAB_CLEAR = 0.3                 # the left ledge's top below the backplane's outline (its install column)
CARD_FRONT = st.BP_FRONT + st.Y_BP
Z_LO = st.card_z("B4") - 8.0
Z_HI = min(st.card_z("B3") + 14.0, H - 0.5)
RX = st.CAGE_LEFT + st.BW
POST_R = 8.0                        # the right corner post reaches this far right of the cards' edge (RX): 3.5 behind
#                                     the 6.5 deep backplane slot
POST_RELIEF, POST_RELIEF_Y0 = (("B2", "B1"), ("B1", "B3")), 15.15   # the right post's front cut back from this Yb,
#                                     from each lower card's top face to 2 below the next card's slot (enclosure 4),
POST_RELIEF_X1 = 89.6               # and stepped back to the backplane slot's roof left of this Xb
BP_BOTTOM = st.BP_Z0 - 2 * st.P
# glands: two rows of four in the bottom wall, the flat weather-meter cables in the PG-9s under the right column
FLAT = {(98.0, 25.0): "wind (flat)", (98.0, 60.0): "rain (flat)"}
GLANDS = [(x, y, "PG-9" if (x, y) in FLAT else "PG-7") for y in (25.0, 60.0) for x in (26.0, 50.0, 74.0, 98.0)
          if (x, y) != (74.0, 60.0)]             # enclosure 4: no spare (G7 gone); the PG-9s go back in (fix 2)
# which gland takes which cable. The port cables run from their jacks (B1 J11-J13, B2 J14) forward, right, down the
# right column (Xb about 101, Yb about 86 at its foot), back and left under the pack tray to their gland, so the
# shortest runs go to the glands nearest that foot: S1 TH the PG-7 at (50, 60), S2 UV (74, 25), S3 BARO (50, 25); the
# spare S4 the farthest, (26, 25). The solar lead goes to J2 on the EVM's left edge, so it takes the left front PG-7,
# (26, 60), the only one in front of the left column. The flat meter cables keep the PG-9s (FLAT).
GLAND_USE = {(50.0, 60.0): "S1 TH", (74.0, 25.0): "S2 UV", (50.0, 25.0): "S3 BARO", (26.0, 25.0): "S4 SPARE",
             (26.0, 60.0): "SOLAR", (98.0, 25.0): "WIND", (98.0, 60.0): "RAIN"}
# S4 has no pod yet (schematic/model.py PORTS: J14 takes none), and a PG-7 with nothing in it doesn't seal: its seal
# closes on a 3.0-4.3 mm cable. So the S4 PG-7 holds a blanking rod (sources gland_blank, README buying list) in its
# seal, cap tightened, until a pod is added; then the rod comes out and the pod's cable goes in.
GLAND_BLANK = {"S4 SPARE": "a 4 x 20 mm stainless dowel pin (ISO 8734, A1) in its seal, cap tightened"}
GLAND_JACK = {"S1 TH": ("B1", "J11"), "S2 UV": ("B1", "J12"), "S3 BARO": ("B1", "J13"), "S4 SPARE": ("B2", "J14"),
              "WIND": ("B2", "J21"), "RAIN": ("B2", "J22"), "SOLAR": ("EVM", "J2")}   # schematic/model.py
COLUMN_FOOT = (101.0, 86.0)                             # Xb, Yb where the port cables leave the right column
SMA = S.val("sma_bulkhead")                             # Yb, Zb of the bulkhead's axis, hole, nut seat (enclosure 4)
GLAND_IN = max(g[1] for g in GLAND.values())            # thread length inside the wall (L1)
VENT = (50.0, 85.0)                                     # Xb, Yb in the bottom wall
PG9_CLEAR, PG9_CLEAR_Z = 24.0, 8.0                      # fix 2: a 24 mm cut round each PG-9 up to Zb 8 (its nut)
FLANGE_SLOT_Z = -18.0                                   # the bottom flange's slot centres (the top's mirror: 187.5)
# shelves, bottom to top
# the shelves stack down from the backplane: the left ledge (EVM board underside) just below the backplane's outline
# (nothing printed may sit in its install column), then the EVM's underside parts, the margin, the pack, the tray;
# what is left above the gland threads is the cable space (Clint's v3 shelves, 2026-11-16)
PACK_TRAY_Z = (st.BP_OUTLINE[1] - BP_SLAB_CLEAR - S.val("evm_under") - M - S.val("pack")[2] - TRAY_T)
CABLE_RISE = PACK_TRAY_Z - GLAND_IN                     # each cable rises out of its gland and turns right here
CORNER_BLOCK_X = 16.5                                   # enclosure 3's bottom-left corner block reaches Xb 16.5
#                                     up to Zb 16.4 (STL audit, sheets/audit-enc3); the tray is above it now, and the
#                                     pack stays right of it, centred under the EVM
PACK_X0, PACK_Z0 = CORNER_BLOCK_X + M, PACK_TRAY_Z + TRAY_T  # the pack lies flat: 69 across, 54 back-to-lid, 18 up
EVM_X0 = TONGUE_C + RIM_CH / 2 + RIM_IN - T + M + EVM_OVL   # J6 clear of the lid's inner channel wall
EVM_Y0 = st.BP_FRONT + M                                # in front of the backplane's lower end; J8 toward the lid
EVM_Z0 = PACK_Z0 + PACK[2] + M + S.val("evm_under")     # board underside
EVM_TOP = EVM_Z0 + 1.6 + EVM[2]
EVM_X1, EVM_Y1 = EVM_X0 + EVM[0], EVM_Y0 + EVM[1]
FIN = (EVM_X1 - SHELF, EVM_X1 + 2.0)                    # the right fin (Xb): its inner 2 is the ledge under the board
LEDGE_H = 10.0                                          # the left ledge and the blocks in front: Zb EVM_Z0-10 to EVM_Z0
LEDGE_Y0 = st.BP_FRONT + 0.5                            # the left ledge's back end at the wall (45 degrees in plan)
LEDGE_Y1 = 103.0                                        # the left ledge's front end, under the keeper
KEEP_X1, KEEP_Y1 = 9.25, 109.0                          # the left keeper's right face; the keeper, fin and block front
KEEP_ROOF = 93.88                                       # the keeper's back: a 45 degree roof, Yb = Xb + 93.88
KEEP_Y0 = IN_X0 + KEEP_ROOF
LEND_Y0 = 92.0                                          # the right lid-end block's back edge at its ends (a V, 103 mid)
CLIP_INS = ((4.5, 106.0), (FIN[1], 106.0))              # the front clip's M3 insert bores (bar_bore), down from the top
LIP_X = (16.5, 89.5)                                    # the tray's front lip, Xb (enclosure 4)
STRAP = (3.0, 20.0, (15.0, 91.0), 19.0)                 # the strap slots: width (Xb) x length (Yb), centres Xb, from Yb
TRAY_SUP = (12.0, 58.0, 5.0)                            # the tray's support block: to Xb, to Yb, height under the tray
#   (all enclosure 4 as printed, sheets/audit-enc4; the tray and its lip to Yb 62 are fix 1)
BULKHEAD_NUT = 11.0                                     # SMA bulkhead jack nut across corners [derived: 3/8 in hex]
_gd, _gh, _gt = S.val("bp_groove")
RAIL_Z0 = EVM_TOP + M                                   # the groove rail below the left wall: 2 above the EVM
RAIL_Y1 = st.BP_FRONT + _gh + _gd + 1.0                 # the rail's front face: the groove roof plus 1
GROOVE = (WALL - _gd, st.BP_BACK, RAIL_Z0, WALL, st.BP_FRONT + _gh, Z_HI)   # Xb, Yb, Zb from / to: the backplane groove
RSLOT = (st.CAGE_LEFT + st.BW - 2.0, st.BP_BACK, Z_LO, st.CAGE_LEFT + st.BW - 2.0 + RSLOT_D, st.BP_BACK + RSLOT_H, Z_HI)
#   the right corner post's backplane slot (Xb, Yb, Zb from / to): the board's factory right edge


def to_lid(xb, yb, zb):
    """Box frame -> the lid-centre frame of lid-rim-spec.md (X toward the top wall, Y toward the LEFT wall as seen
    from the lid, Z from the outside of the back toward the lid): right-handed, the frame the CAD bot and the STL
    use. Y = W/2 - Xb, so the box frame itself is left-handed and Xb runs to the right seen from the lid."""
    return zb - H / 2, W / 2 - xb, yb + T


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
    wall = [B(IN_X0, YP, Z_LO, WALL - 2.0, CARD_FRONT + 1.0, Z_HI, "left wall")]
    slots = []
    for b in st.ORDER:
        z = st.card_z(b)
        slots.append(B(WALL - 2.0, st.BP_FRONT, z - st.BT - SLOT_CLEAR / 2, WALL, CARD_FRONT + 1.0,
                       z + SLOT_CLEAR / 2, f"slot for {b}"))
    wall.append(B(WALL - 2.0, YP, Z_LO, WALL, CARD_FRONT + 1.0, Z_HI, "left wall slot side"))
    wall.append(B(IN_X0, YP, RAIL_Z0, WALL, RAIL_Y1, Z_LO, "groove rail below the left wall"))
    slots.append(B(*GROOVE[:3], *GROOVE[3:], "backplane groove"))
    out.append(Part("left wall", wall, cuts=slots, solid=left_wall_solid,
                    note="moulded in the base: one 2 mm deep slot per card; cards slide in from the lid side toward the "
                         f"back; the backplane's left edge in a groove (Xb {GROOVE[0]:g}-{GROOVE[3]:g}, Yb {GROOVE[1]:g}-"
                         f"{GROOVE[4]:g}, a 45 degree roof) the wall's full length and down a rail to Zb {RAIL_Z0:.2f}"))
    grip = S.val("sb_snap_y") - 1.5
    post_y1 = CARD_FRONT - grip
    post = [B(RX - 2.0, YP, Z_LO, RX + POST_R, post_y1, Z_HI, "right corner post")]
    pslots = [B(RX - 2.0, st.BP_FRONT, st.card_z(b) - st.BT - SLOT_CLEAR / 2, RX + SLOT_CLEAR, post_y1 + 0.1,
                st.card_z(b) + SLOT_CLEAR / 2, f"post slot for {b}") for b in st.ORDER]
    pslots.append(B(*RSLOT[:3], *RSLOT[3:], "backplane slot"))
    for lo, hi in POST_RELIEF:                               # enclosure 4: the post's front cut back over B2 and B1
        pslots.append(B(RX - 2.0 - 0.1, POST_RELIEF_Y0, st.card_z(lo), RX + POST_R + 0.1, post_y1 + 0.1,
                        st.card_z(hi) - st.BT - SLOT_CLEAR / 2 - 2.0, f"post relief over {lo}"))
        pslots.append(B(RX - 2.0 - 0.1, RSLOT[4], st.card_z(lo), POST_RELIEF_X1, POST_RELIEF_Y0 + 0.1,
                        st.card_z(hi) - st.BT - SLOT_CLEAR / 2 - 2.0, f"post relief over {lo}, its step to the slot roof"))
    out.append(Part("right corner post", post, cuts=pslots, solid=right_post_solid,
                    note=f"moulded: takes each card's back-right corner (card Y {grip:.2f}-{st.CD:.2f})"))
    r = BP_PAD_D / 2
    out.append(Part("backplane support pads", [B(x - r, YP, z - r, x + r, st.BP_BACK, z + r, "backplane support pad")
                                               for x, z in (st.bp_xy(h) for h in st.BP_SUPPORTS)],
                    note=f"plain \u00d8{BP_PAD_D:g} pads {st.BP_BACK:g} tall under {', '.join(st.BP_SUPPORTS)} (no screw, no "
                         "hole in the board): they take the cards' push; no screw posts (enclosure 4): the cards plugged "
                         "into its sockets hold the board, its left edge in the groove, its right edge in the post's slot"))
    out.append(Part("retention bar", [B(IN_X0, CARD_FRONT + 1.0, Z_LO, 12.0, CARD_FRONT + 1.0 + BAR, Z_HI, "retention bar")],
                    solid=bar_solid,
                    note=f"separate: two M3 screws (\u00d8{BAR_INS[3]:g} holes) into inserts in the left wall's front face at "
                         f"Xb {BAR_INS[0]:g}, Zb {BAR_INS[1]:g} and {BAR_INS[2]:g}; off before any card comes out"))
    # EVM: the board's left edge rests on a ledge moulded to the left wall (from just in front of the backplane, its
    # back end cut at 45 degrees), its right edge on the top of the right fin, a wall standing on the floor from the
    # tray to the board (it also holds the tray's right end). Both are notched where through-hole tails sit near the
    # edges (evm_edge_tails). In front of the board: the left keeper and the right lid-end block, each with an M3
    # insert bore for the front clip (enclosure 4).
    ez = EVM_Z0 - LEDGE_H
    out.append(Part("charger ledges", [
        B(IN_X0, LEDGE_Y0, ez, EVM_X0 + SHELF, LEDGE_Y1, EVM_Z0, "charger ledge, left wall"),
        B(IN_X0, KEEP_Y0, ez, KEEP_X1, KEEP_Y1, EVM_Z0, "charger keeper, left (clip insert)"),
        B(FIN[0], YP, PACK_TRAY_Z, FIN[1], KEEP_Y1, EVM_Z0, "right fin (charger ledge on its top)"),
        B(FIN[1], LEND_Y0, ez, IN_X1, KEEP_Y1, EVM_Z0, "charger lid-end block, right (clip insert)")],
        solid=charger_solid,
        note=f"moulded: the EVM slides back on a 2 mm ledge (left wall, chamfered under) and the right fin's top at Zb "
             f"{EVM_Z0:g} (no mounting holes; Bumpons off), notched under its edge tails; in front of it a keeper (left) "
             f"and a lid-end block (right) to Yb {KEEP_Y1:g}, an M3 insert bore in each for the front clip (enclosure 4)"))
    out.append(Part("pack tray", [B(IN_X0, YP, PACK_TRAY_Z, FIN[0], TRAY_Y1, PACK_TRAY_Z + TRAY_T, "pack tray"),
                                  B(LIP_X[0], LIP_Y0, PACK_TRAY_Z + TRAY_T, LIP_X[1],
                                    TRAY_Y1, PACK_TRAY_Z + TRAY_T + 6.0, "pack tray front lip (45 degree ramp)"),
                                  B(IN_X0, YP, PACK_TRAY_Z - TRAY_SUP[2], TRAY_SUP[0], TRAY_SUP[1], PACK_TRAY_Z,
                                    "pack tray support (on the bottom-left corner block)")],
                    solid=tray_solid,
                    note=f"moulded to the floor, the left wall and the right fin, {CABLE_RISE:g} mm over the gland "
                         f"threads (the cable space), on a support over the bottom-left corner block; the pack lies flat on "
                         f"Yb 0-{LIP_Y0:g}, slides back, a hook-and-loop strap round it through two {STRAP[0]:g} x "
                         f"{STRAP[1]:g} slots; the front lip a 45 degree ramp from Yb {LIP_Y0:g} (the pack's front) up 6 "
                         f"to Yb {TRAY_Y1:g} (enclosure 4 fix 1: enclosure 4 has the tray to Yb 58 and the ramp from Yb 50, "
                         "under the pack)"))
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


def _prism_xz(pts, y0, y1):
    """A prism of the (Xb, Zb) outline pts from Yb y0 to y1."""
    import cadquery as cq
    return cq.Workplane("XZ").polyline(pts).close().extrude(-(y1 - y0)).translate((0, y0, 0))


def _prism_xy(pts, z0, z1):
    """A prism of the (Xb, Yb) outline pts from Zb z0 to z1."""
    import cadquery as cq
    return cq.Workplane("XY").polyline(pts).close().extrude(z1 - z0).translate((0, 0, z0))


def _prism_yz(pts, x0, x1):
    """A prism of the (Yb, Zb) outline pts from Xb x0 to x1."""
    import cadquery as cq
    return cq.Workplane("YZ").polyline(pts).close().extrude(x1 - x0).translate((x0, 0, 0))


def _cyl_z(x, y, d, z0, z1):
    import cadquery as cq
    return cq.Workplane("XY").center(x, y).circle(d / 2).extrude(z1 - z0).translate((0, 0, z0))


def charger_solid(_shape):
    """The EVM's ledge (45 degrees under, its back end 45 degrees in plan), the left keeper (a 45 degree roof at its
    back), the right fin and the lid-end block (a V back edge), the tail notches and the clip's two insert bores."""
    ez, top, x1 = EVM_Z0 - LEDGE_H, EVM_Z0, EVM_X0 + SHELF
    ch = x1 - IN_X0 - 1.0                                    # the 45 degree chamfer under the ledge
    ledge = _prism_xz([(IN_X0, ez), (IN_X0 + 1.0, ez), (x1, ez + ch), (x1, top), (IN_X0, top)], LEDGE_Y0 - 1, LEDGE_Y1)
    ledge = ledge.cut(_prism_xy([(IN_X0 - 2, LEDGE_Y0 - 2), (x1 + 1, LEDGE_Y0 + x1 + 1 - IN_X0), (x1 + 1, LEDGE_Y0 - 2)],
                                ez - 1, top + 1))                     # its back end, 45 degrees in plan
    keep = _prism_xy([(IN_X0, IN_X0 + KEEP_ROOF), (KEEP_X1, KEEP_X1 + KEEP_ROOF), (KEEP_X1, KEEP_Y1), (IN_X0, KEEP_Y1)],
                     ez, top)
    fin = _prism_xz([(FIN[0], PACK_TRAY_Z), (FIN[1], PACK_TRAY_Z), (FIN[1], top), (FIN[0], top)], YP, KEEP_Y1)
    mid = (FIN[1] + IN_X1) / 2
    vb = LEND_Y0 + (mid - FIN[1])
    lend = _prism_xy([(FIN[1], LEND_Y0), (mid, vb), (IN_X1, LEND_Y0), (IN_X1, KEEP_Y1), (FIN[1], KEEP_Y1)], ez, top)
    shape = ledge.union(keep).union(fin).union(lend)
    t = S.val("evm_edge_tails")
    import cadquery as cq
    for a, b in (t[0:2], t[2:4]):                            # left edge tails: through the ledge's inner 4, the
        ya, yb = EVM_Y0 + a, EVM_Y0 + b                      # notch's front end 45 degrees in plan (enclosure 4)
        shape = shape.cut(_prism_xy([(x1 - 4.0, ya), (x1 + 0.01, ya), (x1 + 0.01, yb + 4.01), (x1 - 4.0, yb)],
                                    ez - 1, top + 1))
    for a, b in (t[4:6], t[6:8]):                            # right edge tails: the fin's inner 2, 3 down
        shape = shape.cut(cq.Workplane("XY").box(SHELF + 0.01, b - a, 3.0 + 1, centered=False)
                          .translate((FIN[0] - 0.01, EVM_Y0 + a, top - 3.0)))
    for x, y in CLIP_INS:
        shape = shape.cut(_cyl_z(x, y, BP_BORE[0], top - BP_BORE[1], top + 1))
    return shape


def tray_solid(_shape):
    """The pack tray, its 45 degree front lip ramp, the two strap slots and the support block under its left end."""
    z0, z1 = PACK_TRAY_Z, PACK_TRAY_Z + TRAY_T
    import cadquery as cq
    tray = cq.Workplane("XY").box(FIN[0] - IN_X0, TRAY_Y1 - YP, TRAY_T, centered=False).translate((IN_X0, YP, z0))
    lip = _prism_yz([(LIP_Y0, z1), (TRAY_Y1, z1), (TRAY_Y1, z1 + TRAY_Y1 - LIP_Y0)], LIP_X[0], LIP_X[1])
    sup = cq.Workplane("XY").box(TRAY_SUP[0] - IN_X0, TRAY_SUP[1] - YP, TRAY_SUP[2], centered=False) \
        .translate((IN_X0, YP, z0 - TRAY_SUP[2]))
    shape = tray.union(lip).union(sup)
    w, ln, xs, y0 = STRAP
    for x in xs:
        shape = shape.cut(cq.Workplane("XY").box(w, ln, TRAY_T + 2, centered=False).translate((x - w / 2, y0, z0 - 1)))
    return shape


def bar_solid(shape):
    """The retention bar's clearance holes, through it along Yb."""
    import cadquery as cq
    for z in BAR_INS[1:3]:
        shape = shape.cut(cq.Workplane("XZ").circle(BAR_INS[3] / 2).extrude(-(BAR + 2))
                          .translate((BAR_INS[0], CARD_FRONT - 0.5, z)))
    return shape


def backplane_checks():
    """cage/backplane-mount-spec.md section 4: the pad tops, the groove and the slot floors level with the copper face;
    no screw posts (enclosure 4); nothing printed in the board's slab but the groove and the slot over its edges; the
    fit (right edge tilted to the slot's end, the left edge clear of the left wall's face on the way down, then slid
    left into the groove); the mux. Returns (lines, faults)."""
    bad = []
    x0, z0, x1, z1 = st.BP_OUTLINE
    yb, yf = st.BP_BACK, st.BP_FRONT
    for p in parts():
        for b in p.boxes:
            if b.what == "backplane support pad" and abs(b.y1 - yb) > 0.1:
                bad.append(f"a {b.what}'s top is at Yb {b.y1:g}, not the board's {yb:g}")
    for name, fl in (("groove", GROOVE[1]), ("right slot", RSLOT[1])):
        if abs(fl - yb) > 0.1:
            bad.append(f"the {name} floor is at Yb {fl:g}, not the board's {yb:g}")
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
                if b.what == "backplane support pad" and b.z0 < mz1 and mz0 < b.z1:
                    g = (b.x0 - (mx1 + dx)) if b.x0 >= mx1 + dx else (mx0 + dx - b.x1)
                    gap = min(gap, g)
                    if g < 0.0:
                        bad.append(f"the mux (moved {dx:.2f}) meets the {b.what} at Xb {b.x0:.2f}-{b.x1:.2f}")
    lines = [f"backplane mount: no screws (the cards hold it)"
             + f"; plain pads under {', '.join(st.BP_SUPPORTS)}; tops, the groove and the slot floors at Yb {yb:g}; "
             f"outline Xb {x0:.2f}-{x1:.2f}, Zb {z0:.2f}-{z1:.2f}; right edge {engage_r:.2f} into the slot (to Xb "
             f"{RSLOT[3]:.2f}), left {engage_l:.2f} into the groove; the fit: {ins:.2f} to the right, left edge "
             f"{left_clear:.2f} clear of the wall's face coming down; mux {gap:.2f} from a pad (both positions); "
             f"groove and rail from Zb {GROOVE[2]:.2f}"]
    return lines, bad


def corners():
    """(x0, x1, z0, z1) of the four inside corners, as (sx, sz) signs: +1 from the low wall, -1 from the high one."""
    return [(sx, sz) for sx in (1, -1) for sz in (1, -1)]


def corner_box(sx, sz, rx, rz, y0, y1, what, lid=False):
    """A box rx x rz in one corner: from the base's inside faces, or (lid) from the lid frame's edges."""
    lo_x, hi_x, lo_z, hi_z = (0, W, 0, H) if lid else (IN_X0, IN_X1, IN_Z0, IN_Z1)
    x0, x1 = (lo_x, lo_x + rx) if sx > 0 else (hi_x - rx, hi_x)
    z0, z1 = (lo_z, lo_z + rz) if sz > 0 else (hi_z - rz, hi_z)
    return B(x0, y0, z0, x1, y1, z1, what)


def box_keepouts():
    """What the base and the lid put inside. The base: the four corner blocks (floor to wall top, with the lid-screw
    bores; the sealing lip is flush with the inside faces, so it adds nothing inside), the glands' threads and nuts on
    the bottom wall. The lid (its names start "lid"; off when a card comes out): its inner channel wall and its corner
    bosses, from the seam to the lid's top (in the lid frame: not settled, unchanged)."""
    out = [corner_box(sx, sz, BLK, BLK, YP, SEAM, "corner block (lid-screw bore)") for sx, sz in corners()]
    inner = TONGUE_C + RIM_CH / 2 + RIM_IN - T              # the lid's inner channel wall reaches this far inside
    out += [B(0, SEAM, 0, inner, D, H, "lid inner channel wall"), B(W - inner, SEAM, 0, W, D, H, "lid inner channel wall"),
            B(0, SEAM, 0, W, D, inner, "lid inner channel wall"), B(0, SEAM, H - inner, W, D, H, "lid inner channel wall")]
    out += [corner_box(sx, sz, CORNER_X, CORNER_Z, SEAM, D, "lid corner boss and channel", lid=True) for sx, sz in corners()]
    for x, y, k in GLANDS:
        r = GLAND_NUT[k] / 2
        out.append(B(x - r, y - r, 0, x + r, y + r, GLAND[k][1], f"{k} gland at Xb {x:g}, Yb {y:g}"))
        cb = S.val("gland_bore")[0 if k == "PG-7" else 1] / 2 + 1.0
        out.append(B(x - cb, y - cb, GLAND[k][1], x + cb, y + cb, GLAND_IN + CABLE_RISE,
                     f"{k} cable rise above the gland at Xb {x:g}, Yb {y:g}"))
    return out


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
            B(EVM_X0 - EVM_OVL, EVM_Y0, EVM_Z0 + 1.6, EVM_X1 + EVM_OVR, EVM_Y1, EVM_TOP,
              "BQ25798EVM parts above the board (J6, J3, J5 past its edges)"),
            B(EVM_X0 + EVM_J8_X[0], EVM_Y1, EVM_Z0, EVM_X0 + EVM_J8_X[1], EVM_Y1 + EVM_J8, EVM_Z0 + 10.0,
              "BQ25798EVM J8 (toward the lid)"),
            B(EVM_X0, EVM_Y0, EVM_Z0 - S.val("evm_under"), EVM_X0 + EVM[0], EVM_Y0 + EVM[1], EVM_Z0,
              "BQ25798EVM underside (J6, tails)")]


def gland_runs():
    """Each gland's run under the tray from the right column's foot (Xb + Yb, the way the cables go), by gland."""
    return {(x, y): abs(COLUMN_FOOT[0] - x) + abs(COLUMN_FOOT[1] - y) for x, y, _k in GLANDS}


# ------------------------------------------------------------------ the EVM's layout (SLUUCB5E Figure 4-1)
def evm_at(x, y, z=0.0):
    """A point on the EVM (x from its left (J6) edge, y from its back edge, z above the board's top face) in the box."""
    return EVM_X0 + x, EVM_Y0 + y, EVM_Z0 + 1.6 + z


def evm_term(block, net):
    """(Xb, Yb, Zb) of a terminal's wire entry on the EVM: the block's outer face, the screw's Yb, 3.6 above the board."""
    order = dict((b[0], b[1:]) for b in S.val("evm_terms"))[block]
    ys = dict((b[0], b[1:]) for b in S.val("evm_term_y"))[block]
    y = ys[order.index(net)]
    x = 2.4 if block in ("J1", "J2") else EVM[0] + EVM_OVR      # left blocks' outer face; right blocks past the edge
    return evm_at(x, y, 3.6)


def evm_part_boxes():
    """The EVM's parts this build touches, as boxes in the box frame (Fig 4-1 places, heights assumed: a 2.54 header
    with its pins 8.5, the J7 block 10)."""
    out = []
    for nm, x, y, n, ax in S.val("evm_jp"):
        hx, hy = (1.27 * n, 1.27) if ax == "x" else (1.27, 1.27 * n)
        a, b = evm_at(x - hx, y - hy), evm_at(x + hx, y + hy, 8.5)
        out.append(B(*a, *b, f"EVM {nm}"))
    x0, x1, y0, y1 = S.val("evm_j7")
    out.append(B(*evm_at(x0, y0), *evm_at(x1, y1, 10.0), "EVM J7"))
    j6 = S.val("evm_j6_y")
    out.append(B(EVM_X0 - EVM_OVL, EVM_Y0 + j6[0], EVM_Z0 - S.val("evm_under"), EVM_X0 + 5.0, EVM_Y0 + j6[1],
                 EVM_Z0 + 1.6 + 6.0, "EVM J6 (micro-B and its plug)"))
    for blk, x0, x1 in (("J2", 2.4, 11.7), ("J1", 2.0, 10.0), ("J3", 78.0, EVM[0] + EVM_OVR), ("J5", 78.1, EVM[0] + EVM_OVR)):
        ys = dict((b[0], b[1:]) for b in S.val("evm_term_y"))[blk]
        out.append(B(*evm_at(x0, min(ys) - 2.6), *evm_at(x1, max(ys) + 2.6, 10.0), f"EVM {blk}"))
    return out


# ------------------------------------------------------------------ the EVM's front clips (two printed parts)
# Each clip is an L: a plate on the keeper (left) or the lid-end block (right), its M3 screw into the insert there
# (CLIP_INS), and a lip 2 mm over the board's front edge that stops it lifting; the plate's back face is the stop that
# keeps the board from sliding forward. Two clips, not one bar: J8 (Xb 23-35) sits on the front edge between them.
CLIP_T = 4.0                        # the plate's height above the keeper top (EVM_Z0)
CLIP_LIP = 2.0                      # how far the lip reaches over the board
CLIP_GAP = 0.3                      # the plate's back face off the board's front edge
CLIP_ABOVE = 0.2                    # the lip's underside above the board's top face
CLIP_HOLE = 3.4                     # M3 clearance
CLIP_SCREW = (5.5, 3.0, 8.0)        # M3 x 8 socket cap: head diameter, head height, length (into the 5.7 insert)
CLIP_X = ((IN_X0 + 0.5, EVM_X0 + 3.75), (EVM_X1 - 3.75, 106.0))   # left clip, right clip (Xb)


def clip_boxes(k):
    """Clip k (0 left, 1 right) as its plate and its lip (box frame)."""
    x0, x1 = CLIP_X[k]
    top = EVM_Z0 + CLIP_T
    return [B(x0, EVM_Y1 + CLIP_GAP, EVM_Z0, x1, KEEP_Y1 + 0.5, top, f"EVM clip {'left right'.split()[k]}, plate"),
            B(x0, EVM_Y1 - CLIP_LIP, EVM_Z0 + 1.6 + CLIP_ABOVE, x1, EVM_Y1 + CLIP_GAP, top,
              f"EVM clip {'left right'.split()[k]}, lip over the board")]


def clip_screw_box(k):
    x, y = CLIP_INS[k]
    r = CLIP_SCREW[0] / 2
    top = EVM_Z0 + CLIP_T
    return B(x - r, y - r, top, x + r, y + r, top + CLIP_SCREW[1], f"EVM clip {'left right'.split()[k]}, M3 head")


def clip_solid(k):
    """Clip k in the box frame: the L, its corners rounded off in plan, the M3 clearance hole."""
    import cadquery as cq
    shape = None
    for b in clip_boxes(k):
        s_ = cq.Workplane("XY").box(b.x1 - b.x0, b.y1 - b.y0, b.z1 - b.z0, centered=False).translate((b.x0, b.y0, b.z0))
        shape = s_ if shape is None else shape.union(s_)
    x, y = CLIP_INS[k]
    return shape.cut(_cyl_z(x, y, CLIP_HOLE, EVM_Z0 - 1, EVM_Z0 + CLIP_T + 1))


def true_frame(sh):
    """The box frame is left-handed (Xb right, Yb toward the lid, Zb up, seen with the box on the pole), so a part's
    box-frame solid is its mirror image: (Xb, Yb, Zb) -> (Xb, Zb, Yb) is the real part (sheets/session1/v2/assembly.V);
    every print file goes through this."""
    return sh.rotate((0, 0, 0), (1, 0, 0), 90).mirror("XZ")


def clip_print():
    """Both clips (real hand) turned onto their top faces (flat on the bed, the lip flush with it), side by side."""
    out = None
    for k in (0, 1):
        sh = true_frame(clip_solid(k)).rotate((0, 0, 0), (1, 0, 0), -90)
        bb = sh.val().BoundingBox()
        sh = sh.translate((-bb.xmin + 16.0 * k, -bb.ymin, -bb.zmin))
        out = sh if out is None else out.union(sh)
    return out


def clip_checks():
    """Each clip on its seat round its insert, clear of the board's edge and top, of the EVM's parts, the walls and the
    coax; the screw's thread reaches into the insert."""
    lines, bad = [], []
    seats = {0: B(IN_X0, KEEP_Y0, EVM_Z0 - LEDGE_H, KEEP_X1, KEEP_Y1, EVM_Z0, "the left keeper"),
             1: B(FIN[0], LEND_Y0, EVM_Z0 - LEDGE_H, IN_X1, KEEP_Y1, EVM_Z0, "the fin and the lid-end block")}
    board = B(EVM_X0, EVM_Y0, EVM_Z0, EVM_X1, EVM_Y1, EVM_Z0 + 1.6, "EVM board")
    parts_ = evm_part_boxes() + [contents()[2]]                  # J8 too
    keep = box_keepouts()
    for k in (0, 1):
        plate, lip = clip_boxes(k)
        x, y = CLIP_INS[k]
        sd = seats[k]
        edge = min(x - sd.x0, sd.x1 - x, y - sd.y0, sd.y1 - y)
        if edge < BP_BORE[0] / 2 + 1.0:
            bad.append(f"clip {k}: its insert is {edge:.1f} from its seat's edge (needs {BP_BORE[0] / 2 + 1:g})")
        hole_edge = min(x - plate.x0, plate.x1 - x, y - plate.y0, plate.y1 - y)
        if hole_edge < CLIP_SCREW[0] / 2 - 0.01:
            bad.append(f"clip {k}: the screw head overhangs the plate ({hole_edge:.1f} from the hole to its edge)")
        if plate.y0 - board.y1 < CLIP_GAP - 0.01 or lip.z0 - board.z1 < CLIP_ABOVE - 0.01:
            bad.append(f"clip {k}: meets the board")
        over = min(lip.x1, board.x1) - max(lip.x0, board.x0)
        if over < 2.0:
            bad.append(f"clip {k}: its lip covers only {over:.1f} of the board's front edge")
        thread = CLIP_SCREW[2] - CLIP_T
        if not 3.0 <= thread <= BP_BORE[1] - 0.5:
            bad.append(f"clip {k}: an M3 x {CLIP_SCREW[2]:g} leaves {thread:g} of thread in the {BP_BORE[1]:g} bore")
        for c in (plate, lip, clip_screw_box(k)):
            if c.x0 < IN_X0 - 0.01 or c.x1 > IN_X1 + 0.01:
                bad.append(f"{c.what}: leaves the box inside")
            for o in parts_ + keep:
                gap = box_gap(c, o)
                if gap < 1.0:
                    bad.append(f"{c.what}: {gap:.1f} mm to the {o.what} (needs 1)")
        gaps = sorted((box_gap(c, o), o.what) for c in (plate, lip, clip_screw_box(k)) for o in parts_)
        lines.append(f"EVM clip {'left right'.split()[k]}: Xb {plate.x0:g}-{plate.x1:g}, Yb {lip.y0:g}-{plate.y1:g}, "
                     f"Zb {plate.z0:g}-{plate.z1:g}, the lip {over:.2f} over the board and {CLIP_ABOVE:g} above it, "
                     f"M3 x {CLIP_SCREW[2]:g} into the insert at ({x:g}, {y:g}) ({thread:g} of thread); nearest EVM "
                     f"part {gaps[0][1]} {gaps[0][0]:.1f} away")
    return lines, bad


def box_gap(a, b):
    """The clearance between two boxes (0 if they touch or overlap)."""
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
    dz = max(b.z0 - a.z1, a.z0 - b.z1, 0.0)
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def seg_gap(p, q, b):
    """The clearance between the segment p-q and box b (sampled every 0.5 mm along the segment)."""
    n = max(2, int(math.dist(p, q) / 0.5) + 1)
    best = 1e9
    for i in range(n):
        t = i / (n - 1)
        x, y, z = (p[j] + (q[j] - p[j]) * t for j in range(3))
        dx = max(b.x0 - x, x - b.x1, 0.0)
        dy = max(b.y0 - y, y - b.y1, 0.0)
        dz = max(b.z0 - z, z - b.z1, 0.0)
        best = min(best, (dx * dx + dy * dy + dz * dz) ** 0.5)
    return best


# ------------------------------------------------------------------ the lid shade (a printed part over the clear lid)
# The #905 lid is clear. Sun through it lands on the dark cards, the EVM and the pack inside, and that heat has nowhere
# to go but out through the walls: shade_estimate() puts it at 15-25 K over the air on a clear day, enough to reach the
# charger's 41.8 C WARM charge stop and on hot days its 55 C HOT cut-off. The shade is a white PETG cap over the lid:
# a plate 12 mm above the lid's top face (over the printed bolt heads), standing on four feet, and a skirt down the
# lid's sides with a 3 mm gap. Air comes in at the skirt's open bottom, rises past the lid's sides and leaves through
# windows in the skirt above the lid's top, so the plate's own heat goes into moving air, not into the lid. Crush ribs
# on the skirt's inside hold it on the lid's sides; it pulls off by hand before the lid bolts come out. It's a cap,
# not a pole sunshade, because the lid faces away from the pole (the box hangs by its back) and a cap needs no arm.
SHADE_GAP, SHADE_T, SHADE_AIR, SHADE_SKIRT, SHADE_FOOT = S.val("shade")
SHADE_RIB = S.val("shade_rib_fit")
LID_TOP = SEAM + S.val("lid_depth")                     # Yb of the lid's top face (outside)
LID_R = S.val("corner_r_out")                           # the lid's corner radius in plan
LID_BOX = (-T, -T, W + T, H + T)                        # the lid's outline (Xb, Zb from / to)
SHADE_WIN = (20.0, 12.0)                                # window width, the post between windows (min)
SHADE_RIBS = {"long": 3, "short": 2}                    # ribs per side: the long sides run along Zb
SHADE_FEET = [(W / 2 + dx, H / 2 + dz) for dx in (-35.0, 35.0) for dz in (-50.0, 50.0)]
SHADE_HEAD_R = S.val("lid_bolt")[0] / 2                 # the printed bolt's head radius


def shade_outline():
    """(x0, z0, x1, z1, corner radius) of the skirt's inside and outside, box frame."""
    x0, z0, x1, z1 = LID_BOX
    g, t = SHADE_GAP, SHADE_T
    return (x0 - g, z0 - g, x1 + g, z1 + g, LID_R + g), (x0 - g - t, z0 - g - t, x1 + g + t, z1 + g + t, LID_R + g + t)


def shade_windows():
    """[(side, centre along the side, width)] of the vent windows in the skirt's band above the lid's top."""
    (ix0, iz0, ix1, iz1, ir), _o = shade_outline()
    out = []
    for side, a0, a1 in (("left", iz0, iz1), ("right", iz0, iz1), ("bottom", ix0, ix1), ("top", ix0, ix1)):
        usable = (a1 - a0) - 2 * (ir + SHADE_WIN[1])
        n = int((usable + SHADE_WIN[1]) // (SHADE_WIN[0] + SHADE_WIN[1]))
        pitch = SHADE_WIN[0] + SHADE_WIN[1]
        c0 = (a0 + a1) / 2 - (n - 1) * pitch / 2
        out += [(side, c0 + i * pitch, SHADE_WIN[0]) for i in range(n)]
    return out


def shade_ribs():
    """[(side, centre along the side)] of the crush ribs on the skirt's inside."""
    (ix0, iz0, ix1, iz1, _r), _o = shade_outline()
    out = []
    for side, a0, a1, n in (("left", iz0, iz1, SHADE_RIBS["long"]), ("right", iz0, iz1, SHADE_RIBS["long"]),
                            ("bottom", ix0, ix1, SHADE_RIBS["short"]), ("top", ix0, ix1, SHADE_RIBS["short"])):
        out += [(side, a0 + (a1 - a0) * (i + 1) / (n + 1)) for i in range(n)]
    return out


def shade_estimate():
    """The sun's heat through the clear lid, roughly, and what the shade leaves. Assumptions, none measured:
    800 W/m2 of clear-sky sun square onto the lid (the lid faces sideways as the box hangs, so this is a low morning
    or evening sun, or winter; at summer noon a sideways face gets less); the lid's top face only (its 25 mm sides
    take the sun at a slant and are ignored); 85 % through clear polycarbonate and 90 % of that absorbed by the dark
    boards inside; 4-6 W/m2K from the inside air out through the PETG walls to moving outside air, over the box's
    whole outside skin. With the shade: its white plate absorbs about 25 % on its own face and gives roughly a
    tenth of that to the lid by radiation across the 12 mm gap and the four feet; the rest leaves in the air."""
    area = (LID_BOX[2] - LID_BOX[0]) * (LID_BOX[3] - LID_BOX[1]) / 1e6           # m2
    sun = 800.0
    q_clear = area * sun * 0.85 * 0.90
    _i, (ox0, oz0, ox1, oz1, _r) = shade_outline()
    q_shade = (ox1 - ox0) * (oz1 - oz0) / 1e6 * sun * 0.25 * 0.10
    out_w, out_h, out_d = W_OUT, L_OUT, BASE_D + S.val("lid_depth")
    skin = (2 * out_w * out_h + 2 * (out_w + out_h) * out_d) / 1e6
    rise = [(q / (skin * u)) for q in (q_clear, q_shade) for u in (6.0, 4.0)]
    return dict(area=area, q_clear=q_clear, q_shade=q_shade, skin=skin, clear=(rise[0], rise[1]),
                shaded=(rise[2], rise[3]))


def shade_checks():
    lines, bad = [], []
    (ix0, iz0, ix1, iz1, ir), (ox0, oz0, ox1, oz1, orr) = shade_outline()
    under = LID_TOP + SHADE_AIR
    head = LID_TOP + S.val("lid_head_proud")
    if under - head < 2.0:
        bad.append(f"lid shade: its plate is {under - head:.1f} over the bolt heads (needs 2)")
    for fx, fz in SHADE_FEET:
        for sx, sz in SCREWS:
            d = math.hypot(fx - sx, fz - sz) - SHADE_FOOT / 2 - SHADE_HEAD_R
            if d < 2.0:
                bad.append(f"lid shade: the foot at ({fx:g}, {fz:g}) is {d:.1f} from a bolt head (needs 2)")
        if not (LID_BOX[0] + 10 < fx < LID_BOX[2] - 10 and LID_BOX[1] + 10 < fz < LID_BOX[3] - 10):
            bad.append(f"lid shade: the foot at ({fx:g}, {fz:g}) is off the lid's flat top")
    skirt_y0 = LID_TOP - SHADE_SKIRT
    if skirt_y0 - (SEAM + LIP_H) < 5.0:
        bad.append(f"lid shade: its skirt ends {skirt_y0 - SEAM:.1f} above the seam (needs 5 over the lip)")
    if SMA[0] + BULKHEAD_NUT / 2 + 2.0 > skirt_y0:
        bad.append("lid shade: its skirt reaches down to the SMA bulkhead")
    if not 0.0 < SHADE_RIB <= 0.6:
        bad.append(f"lid shade: rib interference {SHADE_RIB:g} (0-0.6)")
    if SHADE_T < 1.6:
        bad.append(f"lid shade: {SHADE_T:g} walls are under four perimeters")
    inlet = 2 * ((ix1 - ix0) + (iz1 - iz0)) * SHADE_GAP
    wins = shade_windows()
    outlet = sum(w for _s, _c, w in wins) * (SHADE_AIR - 4.0)
    if outlet < inlet:
        bad.append(f"lid shade: windows {outlet:.0f} mm2, less than the {inlet:.0f} mm2 the skirt's gap lets in")
    e = shade_estimate()
    lines.append(f"lid shade: white PETG cap {ox1 - ox0:.1f} x {oz1 - oz0:.1f}, plate {SHADE_T:g} thick at Yb "
                 f"{under:g}-{under + SHADE_T:g} ({SHADE_AIR:g} over the lid, {under - head:.0f} over the bolt heads "
                 f"[TBD-MEASURE]), skirt {SHADE_GAP:g} off the lid's sides down to Yb {skirt_y0:g} "
                 f"({skirt_y0 - SEAM:g} above the seam), {len(shade_ribs())} crush ribs ({SHADE_RIB:g} into the lid "
                 f"[TBD-MEASURE]), {len(wins)} windows {SHADE_WIN[0]:g} x {SHADE_AIR - 4:g} ({outlet:.0f} mm2 out, "
                 f"{inlet:.0f} mm2 in at the skirt), 4 feet \u00d8{SHADE_FOOT:g} clear of the bolt heads")
    lines.append(f"lid shade, sun: about {e['q_clear']:.0f} W in through the clear lid ({e['area']:.4f} m2 at 800 W/m2) "
                 f"over {e['skin']:.3f} m2 of skin is {e['clear'][0]:.0f}-{e['clear'][1]:.0f} K over the air; "
                 f"shaded about {e['q_shade']:.1f} W, {e['shaded'][0]:.1f}-{e['shaded'][1]:.1f} K (assumptions in "
                 "shade_estimate)")
    return lines, bad


def shade_solid():
    """The shade in the real hand (X = Xb, Y = Zb, Z = Yb), plate up as it sits on the box."""
    import cadquery as cq
    (ix0, iz0, ix1, iz1, ir), (ox0, oz0, ox1, oz1, orr) = shade_outline()
    under = LID_TOP + SHADE_AIR
    y0 = LID_TOP - SHADE_SKIRT

    def rrect(x0, z0, x1, z1, r, za, zb):
        return (cq.Workplane("XY").workplane(offset=za).center((x0 + x1) / 2, (z0 + z1) / 2)
                .rect(x1 - x0, z1 - z0).extrude(zb - za).edges("|Z").fillet(r))
    shade = rrect(ox0, oz0, ox1, oz1, orr, y0, under + SHADE_T).cut(rrect(ix0, iz0, ix1, iz1, ir, y0 - 1, under))
    wz0, wz1 = LID_TOP + 2.0, under - 2.0
    for side, c, w in shade_windows():
        if side in ("left", "right"):
            x = ox0 - 1 if side == "left" else ix1 - 1
            cut = cq.Workplane("XY").box(SHADE_T + 2 + SHADE_GAP, w, wz1 - wz0, centered=False).translate(
                (x if side == "right" else x, c - w / 2, wz0))
        else:
            z = oz0 - 1 if side == "bottom" else iz1 - 1
            cut = cq.Workplane("XY").box(w, SHADE_T + 2 + SHADE_GAP, wz1 - wz0, centered=False).translate(
                (c - w / 2, z, wz0))
        shade = shade.cut(cut)
    rz0, rz1 = y0 + 2.0, LID_TOP - 2.0
    reach = SHADE_GAP + SHADE_RIB
    for side, c in shade_ribs():
        if side == "left":
            rib = cq.Workplane("XY").box(reach + 0.5, 3.0, rz1 - rz0, centered=False).translate((ix0 - 0.5, c - 1.5, rz0))
        elif side == "right":
            rib = cq.Workplane("XY").box(reach + 0.5, 3.0, rz1 - rz0, centered=False).translate((ix1 - reach, c - 1.5, rz0))
        elif side == "bottom":
            rib = cq.Workplane("XY").box(3.0, reach + 0.5, rz1 - rz0, centered=False).translate((c - 1.5, iz0 - 0.5, rz0))
        else:
            rib = cq.Workplane("XY").box(3.0, reach + 0.5, rz1 - rz0, centered=False).translate((c - 1.5, iz1 - reach, rz0))
        shade = shade.union(rib)
    for fx, fz in SHADE_FEET:
        shade = shade.union(cq.Workplane("XY").workplane(offset=LID_TOP).center(fx, fz).circle(SHADE_FOOT / 2)
                            .extrude(SHADE_AIR + 0.5))
    return shade


def shade_print():
    """Plate down on the bed, skirt and feet up."""
    sh = shade_solid().rotate((0, 0, 0), (1, 0, 0), 180)
    bb = sh.val().BoundingBox()
    return sh.translate((-bb.xmin, -bb.ymin, -bb.zmin))


# ------------------------------------------------------------------ the solar lead
# The panel's own cable ends at its gland: its 3.5 x 1.1 plug is cut off outside, the cable comes in through the
# left front PG-7 and is joined just above the nut to a 22 AWG red/black pair (solder, heat-shrink), which runs to
# J2 VIN2 / GND. 22 AWG: the panel gives 1.67 A at its maximum power point and about 1.9 A into a short (solar_p110);
# 22 AWG drops about 0.05 V there over the pair's two legs (wire22). The route keeps clear of the cards, the pack, the EVM
# and the clips: up out of the gland, forward under the EVM to the front strip, up between the left keeper's clip and
# J8, left over the clip's screw head, back along the gap between the left wall and the EVM's left edge, into J2.
SOLAR_R = 1.6                       # the twisted 22 AWG pair's radius
SOLAR_Z = (18.5, 59.0)              # Zb of its run under the EVM (above the bottom-left corner block, below the tray) and
#                                     of its run back over the clip (above the clip's screw head)
SOLAR_XY = (19.5, 4.5, 113.0)       # Xb of its rise (between the left clip and J8), Xb of its run back (between the
#                                     left wall and the board's edge), Yb of the front strip (in front of the keeper)


def solar_route():
    """The solar lead's centre line, gland to J2 VIN2 (box frame)."""
    (gx, gy), = [g for g, n in GLAND_USE.items() if n == "SOLAR"]
    ex, ey, ez = evm_term("J2", "VIN2")
    zr, zt = SOLAR_Z
    xr, xb, yf = SOLAR_XY
    return [(gx, gy, GLAND_IN), (gx, gy, zr), (gx, yf, zr), (xr, yf, zr), (xr, yf, zt), (xb, yf, zt), (xb, ey, zt),
            (xb, ey, ez), (ex + 3.0, ey, ez)]


def solar_len():
    pts = solar_route()
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def solar_checks():
    """Every segment of the solar route at least 1 mm (plus the pair's radius) clear of the base's keepouts, the moulded
    parts, the pack, the EVM (its board, its underside, its parts), the clips and their screws and the cards (in fixed_boxes); the last segment is J2's entry."""
    lines, bad = [], []
    pts = solar_route()
    (gx, gy), = [g for g, n in GLAND_USE.items() if n == "SOLAR"]
    obst = [k for k in box_keepouts() if f"Xb {gx:g}, Yb {gy:g}" not in k.what]
    obst += [b for _n, b in fixed_boxes()]
    c = contents()
    obst += [c[0], c[2], c[3], B(EVM_X0, EVM_Y0, EVM_Z0, EVM_X1, EVM_Y1, EVM_TOP, "EVM board and its parts")]
    obst += [b for k in (0, 1) for b in clip_boxes(k) + [clip_screw_box(k)]]
    j2 = [b for b in evm_part_boxes() if b.what == "EVM J2"][0]
    worst = (1e9, "")
    for i, (p, q) in enumerate(zip(pts, pts[1:])):
        last = i == len(pts) - 2
        for o in obst + ([] if last else [j2]):
            if last and o.what == "EVM board and its parts":
                continue
            g = seg_gap(p, q, o) - SOLAR_R
            worst = min(worst, (g, o.what))
            if g < 1.0:
                bad.append(f"solar lead, segment {i}: {g:.1f} mm to the {o.what} (needs 1)")
    ln = solar_len()
    lines.append(f"solar lead: gland ({gx:g}, {gy:g}) to J2 VIN2 at Yb {pts[-1][1]:.1f}, route {ln:.0f} mm, nearest "
                 f"{worst[1]} {worst[0]:.1f} mm; cut the pair to {math.ceil((ln + 70.0) / 10.0) * 10:.0f} mm (route + "
                 "a 60-80 mm service loop)")
    return lines, bad


def coax_corner_check():
    """The straight plug on the bulkhead's inner end over the EVM's lid-right corner: what Fig 4-1 puts under it."""
    yb, zb, _hole, _seat = SMA
    r = S.val("sma_plug_d") / 2 if "sma_plug_d" in S.D else 4.0
    plug = B(IN_X1 - 9.0 - S.val("sma_plug_len"), yb - r, zb - r, IN_X1, yb + r, zb + r, "the bulkhead's straight plug")
    near = sorted((box_gap(plug, o), o.what) for o in evm_part_boxes() + [clip_screw_box(1)] + clip_boxes(1))
    board_gap = plug.z0 - (EVM_Z0 + 1.6)
    ok = near[0][0] >= 1.0
    return (f"coax: the straight plug on the bulkhead (Xb {plug.x0:.1f}-{plug.x1:g}, Zb {plug.z0:.1f}-{plug.z1:.1f}) "
            f"{board_gap:.1f} above the EVM's top face over its lid-right corner, where Fig 4-1 has only silk; nearest "
            f"part {near[0][1]} {near[0][0]:.1f} away"), ([] if ok else [f"coax plug: {near[0][0]:.1f} to {near[0][1]}"])


# ------------------------------------------------------------------ the test coupon (ASSEMBLY.md 2.2)
# The base's top-left corner, cut out of the real model: the left wall with the top card's slot (B3) and the
# backplane-side ribs, the top-left corner block with its lid-bolt bore, the wall top's land and its sealing lip round
# that corner (the lid's corner fits it), and enough of the left and top walls for a 30 x 30 leak-test patch.
COUPON = (-T - 1.0, 45.0, 130.0, 26.0, SEAM + LIP_H + 1.0, H + T + 1.0)   # Xb, Yb, Zb from / to (cut from the base)
COUPON_CM3 = 35.1                   # its volume (cage.py --coupon checks it), for the print time without CadQuery


def coupon_solid():
    import cadquery as cq
    x0, y0, z0, x1, y1, z1 = COUPON
    region = cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))
    shape = shell_solid()
    for name, s_ in solids():
        if name == "left wall":
            shape = shape.union(s_)
    return shape.intersect(region)


def coupon_checks(sol=None):
    """What the coupon must hold: a card slot, a lid-bolt bore, the lip round a corner, a 30 x 30 wall patch."""
    x0, y0, z0, x1, y1, z1 = COUPON
    lines, bad = [], []
    slots = [b for b in st.ORDER if z0 < st.card_z(b) - st.BT - SLOT_CLEAR / 2 and st.card_z(b) + SLOT_CLEAR / 2 < z1]
    slot_y = (st.BP_FRONT, CARD_FRONT + 1.0)
    if not slots or slot_y[1] - max(slot_y[0], y0) < 15.0:
        bad.append("coupon: no card slot (15 mm long at least) inside it")
    bores = [(x, z) for x, z in SCREWS if x0 < x - BORE_D / 2 and x + BORE_D / 2 < x1 and z0 < z - BORE_D / 2
             and z + BORE_D / 2 < z1]
    if not bores or BORE_Y0 < y0:
        bad.append("coupon: no whole lid-bolt bore inside it")
    if x1 < CORNER_X + 2.0 or H - z0 < CORNER_Z + 2.0 or y1 < SEAM + LIP_H:
        bad.append("coupon: it doesn't hold the lip's whole S round the corner")
    if min(x1 - x0, z1 - z0) < 30.0 or (y1 - y0) < 30.0:
        bad.append("coupon: no 30 x 30 wall patch")
    vol = None
    if sol is not None:
        v = sol.val() if hasattr(sol, "val") else sol
        vol = v.Volume() / 1000
        if abs(vol - COUPON_CM3) > 0.5:
            bad.append(f"the coupon is {vol:.1f} cm3: set COUPON_CM3")
        if not v.isValid():
            bad.append("the coupon is not a valid solid")
    lines.append(f"coupon: Xb {x0:g}-{x1:g}, Yb {y0:g}-{y1:g}, Zb {z0:g}-{z1:g} (the base's top-left corner): "
                 f"{', '.join(slots)} slot (slot_clear {SLOT_CLEAR:g}), the lid-bolt bore at "
                 + ", ".join(f"({x:g}, {z:g})" for x, z in bores) + f", the lip round the corner, the left wall "
                 f"{y1 - y0 - LIP_H - 1:.0f} x {z1 - z0 - 1:.0f} for the leak patch"
                 + (f"; {vol:.1f} cm3, about {vol * RING_PRINT:.0f} min on the H2D" if vol else ""))
    return lines, bad


def write_stl(name, shape):
    import cadquery as cq
    out = HERE / "stl" / name
    out.parent.mkdir(exist_ok=True)
    cq.exporters.export(shape, str(out), tolerance=0.02, angularTolerance=0.1)
    return out


def shell():
    """The printed base's walls, corner blocks, lip and outside features as boxes (box frame), for the drawings and
    the renders; shell_solid() is the real shape."""
    o0x, o1x, o0z, o1z = -T, W + T, -T, H + T                # outside faces: Xb -3 / 126.5, Zb -3 / 172.5
    out = [B(o0x, -T, o0z, o1x, 0, o1z, "floor (back)"),
           B(o0x, 0, o0z, IN_X0, SEAM, o1z, "left wall"), B(IN_X1, 0, o0z, o1x, SEAM, o1z, "right wall"),
           B(IN_X0, 0, o0z, IN_X1, SEAM, IN_Z0, "bottom wall"), B(IN_X0, 0, IN_Z1, IN_X1, SEAM, o1z, "top wall")]
    out += [corner_box(sx, sz, BLK, BLK, 0, SEAM, "corner block (lid-screw bore)") for sx, sz in corners()]
    y1 = SEAM + LIP_H
    out += [B(IN_X0 - LIP_W, SEAM, IN_Z0 + BLK, IN_X0, y1, IN_Z1 - BLK, "sealing lip"),
            B(IN_X1, SEAM, IN_Z0 + BLK, IN_X1 + LIP_W, y1, IN_Z1 - BLK, "sealing lip"),
            B(IN_X0 + BLK, SEAM, IN_Z0 - LIP_W, IN_X1 - BLK, y1, IN_Z0, "sealing lip"),
            B(IN_X0 + BLK, SEAM, IN_Z1, IN_X1 - BLK, y1, IN_Z1 + LIP_W, "sealing lip")]
    for sx, sz in corners():                                 # round each block's two inside faces
        out.append(corner_box(sx, sz, BLK + LIP_W, BLK + LIP_W, SEAM, y1, "sealing lip (round the corner block)"))
    fx0, fx1, reach, ft = S.val("mount_flange")[:4]                # in the floor plane, past each end wall
    out.append(B(fx0, -T, o0z - reach, fx1, -T + ft, o0z, "mounting flange, bottom end (two slots)"))
    out.append(B(fx0, -T, o1z, fx1, -T + ft, o1z + reach, "mounting flange, top end (two slots)"))
    return out


def cavity_outline(n=12):
    """The inside outline (Xb, Zb), anticlockwise from the bottom-left corner block: the inside faces, each corner
    block's two faces with its R BLK_R inner corner, an R BLK_F fillet where a block meets a wall. Arcs as n chords."""
    def arc(c, r, a0, a1):
        return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
                 c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]
    f, R = BLK_F, BLK_R
    loc = (arc((f, BLK + f), f, 180, 270) + arc((BLK - R, BLK - R), R, 90, 0) + arc((BLK + f, f), f, 180, 270))
    out = []
    for sx, sz in ((1, 1), (-1, 1), (-1, -1), (1, -1)):      # BL, BR, TR, TL: anticlockwise
        pts = [(IN_X0 + u if sx > 0 else IN_X1 - u, IN_Z0 + v if sz > 0 else IN_Z1 - v) for u, v in loc]
        out += pts[::-1] if sx * sz < 0 else pts
    return out


def shell_solid():
    """The printed base as enclosure 4 (+ fix 2) built it, in CadQuery: the R9 outside, the 3 floor, the walls and the
    four corner blocks to Yb 117, the 2 x 2.5 lip round the inside edge, the lid-screw bores (and their 45 degree
    chamfers) in the blocks, the gland pockets and holes in the bottom wall (fix 2: the PG-9s and their 24 mm clearance
    cuts), the SMA hole and its nut seat in the right wall, the two mounting flanges with their slots and gussets."""
    import cadquery as cq
    o0x, o1x, o0z, o1z = -T, W + T, -T, H + T
    outer = (cq.Workplane("XZ").center((o0x + o1x) / 2, (o0z + o1z) / 2).rect(o1x - o0x, o1z - o0z)
             .extrude(-(SEAM + T)).edges("|Y").fillet(OUT_R).translate((0, -T, 0)))
    cav = cavity_outline()
    shape = outer.cut(_prism_xz(cav, 0, SEAM + 1))
    lip = (cq.Workplane("XZ").polyline(cav).close().offset2D(LIP_W).extrude(-LIP_H).translate((0, SEAM, 0))
           .cut(_prism_xz(cav, SEAM - 1, SEAM + LIP_H + 1)))
    shape = shape.union(lip)
    for x, z in SCREWS:                                      # the lid-screw bores, chamfered at the top
        shape = shape.cut(cq.Workplane("XZ").center(x, z).circle(BORE_D / 2).extrude(-(SEAM + 1 - BORE_Y0))
                          .translate((0, BORE_Y0, 0)))
        h = (CHAMF_D - BORE_D) / 2 + 0.5
        shape = shape.cut(cq.Workplane("XY").add(cq.Solid.makeCone(BORE_D / 2, BORE_D / 2 + h, h,
                                                                   cq.Vector(x, CHAMF_Y0, z), cq.Vector(0, 1, 0))))
    for (xa, xb), apex, step in S.val("enc_pockets"):        # 1 mm pockets in the bottom wall's inside face
        xc, half = (xa + xb) / 2, (xb - xa) / 2
        if step is None:
            pts = [(xa, -0.5), (xb, -0.5), (xb, apex - half), (xc, apex), (xa, apex - half)]
        else:                                                # narrowing at 45 degrees to the vent's land
            ys, h2 = step
            pts = [(xa, -0.5), (xb, -0.5), (xb, ys), (xc + h2, ys + half - h2), (xc + h2, apex - h2), (xc, apex),
                   (xc - h2, apex - h2), (xc - h2, ys + half - h2), (xa, ys)]
        shape = shape.cut(_prism_xy(pts, IN_Z0 - 1.0, IN_Z0 + 0.01))
        if xa < IN_X0 + BLK + BLK_F:                         # no fillet at the block's foot along this pocket
            shape = shape.cut(cq.Workplane("XY").box(BLK_F + 0.01, apex - half, BLK_F, centered=False)
                              .translate((IN_X0 + BLK, 0, IN_Z0)))
    pg7, vent, pg9 = S.val("enc_glands")
    for x, y, k in GLANDS:
        d = pg7 if k == "PG-7" else pg9
        shape = shape.cut(_cyl_z(x, y, d, o0z - 1, IN_Z0 + 1))
        if k == "PG-9":                                      # fix 2: clear the land and the corner block round it
            shape = shape.cut(_cyl_z(x, y, PG9_CLEAR, IN_Z0 - 1.0, PG9_CLEAR_Z))
    shape = shape.cut(_cyl_z(VENT[0], VENT[1], vent, o0z - 1, IN_Z0 + 1))
    yb, zb, hole, seat = SMA                                 # the SMA bulkhead hole and its inner nut seat
    shape = shape.cut(cq.Workplane("YZ").center(yb, zb).circle(hole / 2).extrude(o1x - IN_X1 + 2).translate((IN_X1 - 1, 0, 0)))
    shape = shape.cut(cq.Workplane("YZ").center(yb, zb).circle(seat / 2).extrude(S.val("enc_sma_seat") + 0.5)
                      .translate((IN_X1 - 0.5, 0, 0)))
    fx0, fx1, reach, ft, sw, sl, s1, s2, fr, gus = S.val("mount_flange")
    fl = (cq.Workplane("XY").box(fx1 - fx0, ft, reach + 1, centered=False).translate((fx0, -T, o0z - reach))
          .edges("|Y").edges("<Z").fillet(fr))
    for sxc in (s1, s2):
        fl = fl.cut(cq.Workplane("XZ").center(sxc, FLANGE_SLOT_Z).slot2D(sl, sw, 90).extrude(-(ft + 2)).translate((0, -T - 1, 0)))
    fl = fl.union(_prism_yz([(-T + ft, o0z + 0.5), (-T + ft + gus, o0z + 0.5), (-T + ft + gus, o0z), (-T + ft, o0z - gus)],
                            fx0, fx1))
    shape = shape.union(fl).union(fl.mirror("XY", (0, 0, H / 2)))
    return shape


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
    """The coax from AD1's forward arm: the straight plug toward the lid, the RG-316 bend to the right, then down the
    right column to the bulkhead where enclosure 4 put it (sma_bulkhead: low in the right wall). Returns (plug end
    Yb, bulkhead Yb, bulkhead Zb, axis Xb)."""
    ax = (arm.x0 + arm.x1) / 2
    pe = arm.y1 + S.val("sma_plug_len")
    return pe, SMA[0], SMA[1], ax


def coax_route(arm):
    """The coax's length from AD1's plug to the bulkhead's inner plug (the path the render draws: a quarter bend of
    rg316_bend to the right, dropping as it goes, then straight to the plug on the bulkhead's inner end) and where that
    straight plug ends (Xb). Returns (length, plug end Xb)."""
    ax, az = (arm.x0 + arm.x1) / 2, (arm.z0 + arm.z1) / 2
    pe, yb, zb, _ = coax(arm)
    r = S.val("rg316_bend")
    pts = [(ax, pe, az)] + [(ax + r - r * math.cos(math.radians(90 * k / 9)), pe + r * math.sin(math.radians(90 * k / 9)),
                             az + (zb - az) * k / 9) for k in range(1, 10)]
    inner = IN_X1 - 9.0 - S.val("sma_plug_len")               # the jack's inner end, then the straight plug on it
    pts.append((inner, yb, zb))
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:])), inner


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


def write_audit_stl(out):
    import cadquery as cq
    shape = shell_solid()
    for name, s in solids():
        if name != "retention bar":
            shape = shape.union(s)
    cq.exporters.export(shape, str(out), tolerance=0.02, angularTolerance=0.1)


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
            if b.x0 < IN_X0 - 0.01 or b.x1 > IN_X1 + 0.01 or b.y0 < -0.01 or b.y1 > D + 0.01 or \
                    b.z0 < IN_Z0 - 0.01 or b.z1 > IN_Z1 + 0.01:
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
        if c.x0 < IN_X0 + M - 0.01 or c.x1 > IN_X1 - M + 0.01 or c.y0 < M - 0.01 or c.y1 > D - M + 0.01 or \
                c.z0 < IN_Z0 + M - 0.01:
            bad.append(f"{c.what}: less than {M:g} mm to a wall")
        for o in keep + [b for n, b in fixed_boxes() if n not in ("charger ledges", "pack tray")]:
            g = B(o.x0 - M, o.y0 - M, o.z0 - M, o.x1 + M, o.y1 + M, o.z1 + M, o.what)
            if c.x0 < g.x1 and g.x0 < c.x1 and c.y0 < g.y1 and g.y0 < c.y1 and c.z0 < g.z1 and g.z0 < c.z1:
                bad.append(f"{c.what}: less than {M:g} mm to the {o.what}")
    runs = gland_runs()
    used = [g for g, n in GLAND_USE.items() if n in ("S1 TH", "S2 UV", "S3 BARO")]
    pg7 = [(x, y) for x, y, k in GLANDS if k == "PG-7" and GLAND_USE[(x, y)] != "SOLAR"]
    if sorted(GLAND_USE) != sorted((x, y) for x, y, _k in GLANDS) or \
            any(GLAND_USE[g].split()[0].lower() != v.split()[0] for g, v in FLAT.items()):
        bad.append("GLAND_USE does not cover the glands, or a flat cable isn't in its PG-9")
    if max(runs[g] for g in used) > min(runs[g] for g in pg7 if g not in used):
        bad.append("a port cable in use has a longer run than the spare's gland")
    print("glands: " + "; ".join(f"{n} ({x:g}, {y:g}" + (f", run {runs[(x, y)]:.0f})" if n != "SOLAR" else ")")
                                for (x, y), n in sorted(GLAND_USE.items(), key=lambda t: runs[t[0]])))
    for fn in (clip_checks, solar_checks, shade_checks):
        ln_, b_ = fn()
        for ln in ln_:
            print(ln)
        bad += b_
    ln, b_ = coax_corner_check()
    print(ln)
    bad += b_
    ln_, b_ = coupon_checks()
    for ln in ln_:
        print(ln)
    bad += b_
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
    print(f"base (enclosure 4 + fixes): outside {W + 2 * T:g} x {H + 2 * T:g} x {BASE_D:g} (PETG, R{OUT_R:g} corners; "
          f"floor {T:g}, long walls {IN_X0 + T:g}, short walls {IN_Z0 + T:g}), inside {BOX_IN[0]:g} x {BOX_IN[1]:g} "
          f"(Xb {IN_X0:g}-{IN_X1:g}, Zb {IN_Z0:g}-{IN_Z1:g}), wall top (seam) at Yb {SEAM:g}, a {LIP_W:g} x {LIP_H:g} lip "
          f"on its inside edge, closed depth {D:g}; corner blocks {BLK:g} square (R{BLK_R:g}, R{BLK_F:g} fillets), floor "
          f"to wall top, \u00d8{BORE_D:g} lid-bolt bores from Yb {BORE_Y0:g} (chamfered to \u00d8{CHAMF_D:g}) at "
          + ", ".join(f"({x:g}, {z:g})" for x, z in SCREWS)
          + "; lid fastening: Clint's 3D-printed bolts in the four bores, no heat-set inserts (2026-11-17)")
    for x, z in SCREWS:                       # each bore inside its corner block and the walls behind it
        if min(x + T, W + T - x, z + T, H + T - z) < BORE_D / 2 + 1.0 or \
                max(min(x - IN_X0, IN_X1 - x), min(z - IN_Z0, IN_Z1 - z)) + BORE_D / 2 > BLK:
            bad.append(f"the lid-screw bore at ({x:g}, {z:g}) leaves its corner block and wall")
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
    if "--clip" in sys.argv:                                # the EVM's two front clips: not gated (no lid part)
        sol = clip_print()
        out = write_stl("evm-clips.stl", sol)
        v = sol.val()
        print(f"clip STL written: {out} (not gated; both clips on their top faces, {v.Volume() / 1000:.1f} cm3)")
        if not v.isValid():
            bad.append("the clips are not a valid solid")
    if "--shade" in sys.argv:                               # the lid shade: not gated (it sits on the lid, not the rim)
        sol = shade_print()
        out = write_stl("lid-shade.stl", sol)
        v = sol.val()
        bb = v.BoundingBox()
        print(f"shade STL written: {out} (not gated; plate on the bed, {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}, "
              f"{v.Volume() / 1000:.1f} cm3)")
        if not v.isValid():
            bad.append("the lid shade is not a valid solid")
    if "--coupon" in sys.argv:                              # the test coupon: not gated (it is what settles the gate)
        sol = coupon_solid()
        pr = true_frame(sol)
        bb = pr.val().BoundingBox()
        out = write_stl("coupon.stl", pr.translate((-bb.xmin, -bb.ymin, -bb.zmin)))
        print(f"coupon STL written: {out} (not gated; real hand, Yb up: the cut face at Yb {COUPON[1]:g} on the bed, "
              f"{bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f})")
        ln_, b_ = coupon_checks(sol)
        for ln in ln_:
            print(ln)
        bad += b_
    if "--stl" in sys.argv and stl_gate():
        print("STL REFUSED: the lid interface is not settled yet: " + ", ".join(stl_gate()))
        sys.exit(2)
    if "--audit-stl" in sys.argv:                           # the printed base as one STL in the box frame, for the
        out = Path(sys.argv[sys.argv.index("--audit-stl") + 1])   # voxel diff against the enclosure STL (audit-enc4)
        out.write_text("")
        write_audit_stl(out)
        print(f"audit STL written: {out} (box frame; shell and moulded parts, no retention bar; not a print file)")
    if "--solid" in sys.argv or "--stl" in sys.argv:
        sh = shell_solid().val()
        print(f"  solid shell: valid {sh.isValid()}, {sh.Volume() / 1000:.1f} cm3")
        if not sh.isValid():
            bad.append("the shell is not a valid solid")
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
    print(f"cage {'PASS' if not bad else 'FAIL'}: base inside {BOX_IN[0]:g} x {BOX_IN[1]:g} x {D:g} mm "
          "[TBD-MEASURE: the lid gate]")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
