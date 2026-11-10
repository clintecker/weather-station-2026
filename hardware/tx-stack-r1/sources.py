"""Every dimension the stack drawings use, with its source.

status: "sourced"  read from a datasheet, a maker's CAD file or this repo
        "derived"  computed from sourced numbers (the formula is in the note)
        "TBD"      [TBD-MEASURE]: not found in any source; the drawings use the value as a labelled
                   placeholder until Clint measures the part
The README's dimension table is generated from this file (python3 sources.py --check keeps it in step).
"""
import sys
from pathlib import Path

SB = "https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf"
SFE = "SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021)"
KRJ = "KiCad 10 footprint RJ12_Amphenol_54601-x06_Horizontal (fab layer)"
SEEED = "Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini"
ADA = "Adafruit Eagle board, github.com/adafruit/Adafruit-{}-PCB"
DOC = "docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md"
SUL = "Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow)"
SULF = "Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com"
G9 = "Adafruit #761 PG-9 gland drawing, cdn-shop.adafruit.com/product-files/761/761diagram.jpg"
G7 = "Adafruit #762 PG-7 gland, adafruit.com/product/762"
UC = "4UCON drawing 14869 (SparkFun PRT-00132 jack), cdn.sparkfun.com/assets/8/6/5/f/1/RJ11-Datasheet.pdf"
PAD = "BusBoard PAD3U Padboard, busboardcom.busboard.us/PAD3U (38 x 62 holes, 0.037 in holes on 0.1 in, 160.02 x 100.08 x 1.6 mm; DigiKey 4526-PAD3U-ND)"
TIB = "TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf"
BOXD = "Adafruit #905 diagram (not to scale), cdn-shop.adafruit.com/datasheets/175mmenclosurediagram.pdf p.1 (inside bottom 135.7 x 90 mm straight walls between the corner bosses)"
KEY = "Keystone solder lugs catalogue p.79, keyelco.com/userAssets/file/K75p79.pdf"

D = {
    # ---------------------------------------------------------------- SolderFul BreadBoard SOLDERBREAD#02
    "sb_w": (81.3, "SolderFul board length", SB + " p.2", "sourced"),
    "sb_h": (50.8, "SolderFul board width", SB + " p.2", "sourced"),
    "sb_t": (1.6, "SolderFul board thickness", SB + " p.1", "sourced"),
    "pitch": (2.54, "hole pitch", SB + " p.1", "sourced"),
    "sb_hole": (1.0, "solder hole diameter", SB + " p.1", "sourced"),
    "sb_mhole": (3.0, "mounting hole and edge-notch diameter", SB + " p.1-2", "sourced"),
    "sb_mhole_span": (71.1, "centre-line mounting holes, outer pair, centre to centre", SB + " p.2", "sourced"),
    "sb_notch_side_y": (8.9, "side notch centre from the long edge", SB + " p.2 (8.9 mm)", "sourced"),
    "sb_notch_side_span": (33.0, "side notches, outer pair, centre to centre", SB + " p.2", "sourced"),
    "sb_notch_end_span": (68.6, "front and back edge notches, centre to centre (X 6.35 and 74.95)", SB + " p.2", "sourced"),
    "sb_centre": (25.4, "centre channel (middle notch, mounting holes) from the front edge", SB + " p.2 (25.4 mm)", "sourced"),
    "sb_x1": (3.82, "row 1 hole centre from the left edge", "(81.3 - 29 x 2.54) / 2, rows centred as drawn on p.2", "derived"),
    "sb_ya": (11.43, "column a from the front edge", "25.4 - 3.81 (half the 0.3 in channel, p.2) - 4 x 2.54", "derived"),
    "sb_snap_y": (41.91, "card depth after the back rails are snapped off: the break line between column j (39.37) and the inner back rail (44.45), on the side notches' centre line (41.9)", "midpoint of the two hole lines; SolderFul p.2 side notches at 50.8 - 8.9; where it actually breaks: measure", "TBD"),
    "sb_rails": (3.81, "outer rail from the edge; inner rail 6.35 mm", "drawing p.2 measured against the 2.54 grid", "derived"),
    # ---------------------------------------------------------------- RJ11 port: BOB-14021 + 87180-066LF
    "bob_w": (15.24, "BOB-14021 width (along the header)", SFE + ": outline 0..15.24", "sourced"),
    "bob_d": (20.32, "BOB-14021 depth (snap-off tab removed)", SFE + ": outline 0..20.32", "sourced"),
    "bob_hdr_y": (1.27, "header row from the BOB back edge", SFE + ": JP4 at y 1.27", "sourced"),
    "bob_peg_y": (15.24, "jack peg line from the BOB back edge", SFE + ": JP3 at y 15.24", "sourced"),
    "jack_w": (13.2, "87180 / 54601 jack body width", KRJ + "; RS 771-0215 listing 13.2", "sourced"),
    "jack_d": (18.0, "jack body depth (peg line + 7.88 to the mouth)", KRJ + ": fab -1.23..16.77; RS 18 mm", "sourced"),
    "jack_h": (11.5, "jack body height above the BOB", "RS Components 771-0215 (87180-066LF) listing, 11.5 x 13.2 x 18 mm; test-fit one jack (" + DOC + ")", "sourced"),
    "jack_4ucon": ((13.34, 20.57, 15.70), "4UCON 14869 jack (on Clint's two existing BOB-14021s): width x length x height (15.00 to the shoulder); pins 1.27 stagger, 6.35 outer, rows 2.54 apart, 8.89 from the pegs; pegs 3.20 at 10.16; tails 4.30", UC + " (SparkFun's STEP is an outdated version: community.sparkfun.com/t/44748)", "sourced"),
    "hdr_plastic": (2.5, "male header plastic (board to breakout)", "standard 0.1 in header; bench r1 kicad_layout.py SEAT_Z", "sourced"),
    "breakout_t": (1.6, "breakout PCB thickness (Adafruit, SparkFun, Seeed)", "Eagle files: 1.6 mm default stack; not stated", "TBD"),
    # ---------------------------------------------------------------- PCA9548 #5626
    "mux_w": (40.64, "PCA9548 #5626 length", ADA.format("PCA9548") + "; adafruit.com/product/5626: 40.6 x 20.2 x 4.8 mm", "sourced"),
    "mux_d": (20.32, "PCA9548 #5626 width", ADA.format("PCA9548"), "sourced"),
    "mux_h": (4.8, "PCA9548 #5626 overall height", "adafruit.com/product/5626", "sourced"),
    "foam": (1.0, "double-sided foam pad under the mux", "not chosen yet", "TBD"),
    # ---------------------------------------------------------------- Wio-E5 mini
    "mini_w": (49.97, "Wio-E5 mini length", SEEED + ": outline", "sourced"),
    "mini_d": (22.99, "Wio-E5 mini width", SEEED + ": outline; wiki 50 x 23 mm", "sourced"),
    "mini_rows": (17.78, "Wio-E5 mini header rows, centre to centre (7 x 2.54)", SEEED + ": J1 pads B and D", "sourced"),
    "mini_module_h": (2.5, "LoRa-E5 module height", SEEED + ": package MOUDLE28P-1.25-12X12X2.5MM", "sourced"),
    "mini_sma": (6.5, "SMA-K body, square", SEEED + ": package SMA5P-SMD-5.1-6.5X6.5X16.5MM", "sourced"),
    "mini_sma_out": (12.3, "SMA beyond the mini's edge", "16.5 mm package length from the ANT pad's inner end at x 45.8 (" + SEEED + "); the brd's doc layer disagrees: measure", "TBD"),
    "mini_usbc_h": (3.2, "USB-C receptacle height above the mini", "typical mid-mount Type-C; part not named in the brd", "TBD"),
    "usbc_plug": (7.0, "USB-C plug overmould thickness (console cable)", "typical cable; measure Clint's", "TBD"),
    # ---------------------------------------------------------------- other breakouts
    "shtc3": ((25.4, 17.78), "SHTC3 #4636 outline", ADA.format("SHTC3"), "sourced"),
    "ina228": ((25.4, 20.32), "INA228 #5832 outline", ADA.format("INA228"), "sourced"),
    "max17048": ((25.4, 20.32), "MAX17048 #5580 outline", ADA.format("MAX17048"), "sourced"),
    "qt_lead_h": (14.0, "QT lead male-pin housing height (#4209)", "premium jumper housing; measure", "TBD"),
    "qt_h": (2.9, "STEMMA QT (JST SH) socket height", "bench r1 kicad_layout.py qt_socket", "TBD"),
    "jstph_h": (6.0, "JST PH 2-pin socket height (MAX17048)", "KiCad JST_PH_B2B-PH-K model; bench r1 model_gauge", "sourced"),
    "s7v8f3": ((11.43, 16.51), "Pololu S7V8F3 outline", "bench r1 build.py SIZE['REG'] (0.45 x 0.65 in); pin order from the board in hand", "sourced"),
    "s7v8f3_h": (3.0, "S7V8F3 tallest part (inductor)", "bench r1 kicad_layout.py model_reg", "TBD"),
    "ptc": ((7.4, 3.1, 12.7), "MF-R010 body W x T x H (max), leads 5.08", "Bourns MF-R datasheet table, via distributor listings", "sourced"),
    "res_v_h": (9.0, "10 kohm standing (P5.08 vertical) height", "KiCad R_Axial_DIN0207 vertical model, L 6.3 + lead", "derived"),
    "cap_h": (6.0, "100 nF disc height", "KiCad C_Disc_D3.8mm model, D 3.8 + lead", "derived"),
    "pack": ((69.0, 54.0, 18.0), "battery pack #353", "INVENTORY.md / docs/current-system.md (SHOP:49)", "sourced"),
    # ---------------------------------------------------------------- card cage and backplane (r2)
    "ra_offset": (1.52, "right-angle header: hole centre to the insulator's back face", SUL + " (.060)", "sourced"),
    "ra_insulator": (2.54, "right-angle header insulator, along the mating pins", SUL + " (.100)", "sourced"),
    "ra_mate": (5.84, "right-angle header mating pin length beyond the insulator", SUL + " code BA (.230)", "sourced"),
    "ra_tail": (3.05, "right-angle header solder tail below the insulator", SUL + " code BA (.120)", "sourced"),
    "ra_pin_z": (1.27, "right-angle header pin centre above the card", SUL + ": insulator .100 square on the board", "derived"),
    "socket_h": (8.5, "Sullins PPPC181LFBN-RC body, backplane face to mouth", SULF, "sourced"),
    "socket_w": (2.54, "Sullins PPPC socket body width (single row)", SULF, "sourced"),
    "socket_tail": (3.0, "socket solder tail beyond the backplane copper", SULF + ": .118 tail; check on the part", "TBD"),
    "insertion": (5.0, "chosen pin insertion into the socket (5.84 available; 0.84 left for print tolerance)", "layout rule", "derived"),
    "card_bp_gap": (10.86, "snapped card back edge to backplane face", "39.37 (column j) + 1.52 + 2.54 + 5.84 - 5.0 + 8.5 - 41.91 (sb_snap_y)", "derived"),
    "pad_pitch": (2.54, "PAD3U hole pitch (a separate pad per hole, no strips)", PAD, "sourced"),
    "strip_size": ((160.02, 100.08, 1.6), "BusBoard PAD3U padboard, 62 holes along 160 mm x 38 along 100 mm; the backplane is a piece 21 x 40 holes cut from it, lines along the 160 mm side", PAD, "sourced"),
    "pad_margin": (1.27, "backplane cut edge to the nearest hole centre (cut midway between two hole lines)", "half the 2.54 pitch", "derived"),
    "bus_wire": (0.64, "tinned copper bus wire for the 18 backplane lines, 22 AWG", "AWG 22 = 0.644 mm", "sourced"),
    "align_tol": (0.5, "header pin to socket misalignment the socket's lead-in takes", "typical 0.1 in female header lead-in; check one card in the cage", "TBD"),
    "finger": (8.0, "vertical room needed over a plug to press its latch", "a fingertip or a small screwdriver", "TBD"),
    "rg316_bend": (12.7, "RG-316 minimum static bend radius (the 135110-01 cable)", "typical 5 x 2.5 mm OD; not in the Amphenol listing", "TBD"),
    "ant_len": (100.0, "ANT-916-CW-HWR length, hinge to tip (render only)", "not looked up: TE page refuses scripts; measure", "TBD"),
    "sma_plug_len": (20.0, "straight SMA plug and its crimp ferrule on the 135110 cable", "typical; measure the cable", "TBD"),
    "bp_posts": (8.0, "backplane copper face off the base's floor (the mux on its foam and the socket tails behind it, 2 mm clear)", "mux 4.8 + foam 1 + 2 = 7.8", "derived"),
    "cage_plate": (0.0, "cage base plate: none (the printed base's floor carries the cage)", "layout choice", "derived"),
    "cage_wall": (8.5, "cage left wall thickness; card slots 2 mm deep", "layout choice: the cards' left edge clears the base's 6 mm rim lip (the full 9 mm land less the 3 mm wall) by 0.5 mm as they slide out", "derived"),
    "slot_clear": (0.3, "card slot width over the 1.6 mm card (print tuning)", "Bambu H2D PLA first-print allowance; tune on a test slot", "TBD"),
    "bar": (2.5, "retention bar thickness in front of the card front edges", "layout choice", "derived"),
    "tails": (1.5, "solder tails and bottom-side wires below a card", "typical; measure after the first card", "TBD"),
    "clear": (0.5, "minimum clearance kept between parts", "layout rule", "derived"),
    "tongue": ((6.0, 8.89), "printed tongue on the back jack's spacer: width x reach past the snapped edge (to the old 50.8 edge)", "layout choice: the right corner post grips its last 1.5 mm", "derived"),
    "bob_spacer": (2.0, "printed spacer under each RJ11 breakout (bonded to the card)", "layout choice", "derived"),
    "do35": ((4.56, 2.0), "DO-35 body length x diameter (1N5232B, BAT85S)", "onsemi 1N5221B series and Vishay BAT85 (doc 88146) outline DO-35/DO-204AH", "sourced"),
    "diode_stand_h": (7.0, "standing DO-35 height (body on one lead, the other looped over)", "4.56 body + 1 lead + loop; check on the part", "TBD"),
    "r_lying_h": (2.5, "lying DIN0207 resistor height (body diameter)", "KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model", "derived"),
    "lug": ((13.5, 0.38), "Keystone 7328 ring solder lug length x thickness (ring for #4 / M3, 3.1 mm hole)", KEY + ": 7328 .531 long, .015 brass, H .120", "sourced"),
    "pack": ((69.0, 54.0, 18.0), "battery pack #353", "INVENTORY.md / docs/current-system.md (SHOP:49)", "sourced"),
    "evm": ((90.0, 90.0, 15.0), "BQ25798EVM (BMS034) board outline x tallest part above it; no mounting holes; feet H1-H4 3M Bumpon SJ-5303 (11.2 x 5.1) peeled off for the rails", "outline: Clint, by hand, 2026-11-10: 90 x 90; parts (SLUUCB5E BOM): J1-J4 On-Shore ED120/2DS, J5 ED120/3DS (5.08 mm terminal blocks), J7 Molex 0393570002, J9 3M N2510-6002-RB, J8 Molex 0022053041, J6 Molex 47346-0001, about 33 jumpers with shunts; 15 covers a 5.08 mm rising-clamp block (about 10-12, makers' drawings not reached)", "TBD"),
    "evm_j8": (6.0, "EVM J8 (right-angle 4-pin, the EV2300 port our I2C lead uses) reach past the board edge", "Clint, by hand, 2026-11-10: 96 across J8, 90 without", "sourced"),
    # ---------------------------------------------------------------- the printed base (PETG) under the #905 lid
    "box_out": ((125.0, 175.0, 75.0), "#905 (TIBOX) outside, for reference: width x length x depth (the printed base replaces its 50 mm body)", TIB + " p.5; adafruit.com/product/905", "sourced"),
    "lid_depth": (25.0, "#905 clear lid tray depth, outside (kept: the printed base mates with it)", TIB + " p.5 D2; Clint, by hand, 2026-11-10: lid about 25 deep, no lip", "sourced"),
    "base_out_depth": (100.0, "printed base depth, outside, rim to back", "Clint, 2026-11-10: 100 mm", "sourced"),
    "base_wall": (3.0, "printed base walls and floor (PETG, about 7 perimeters on a 0.4 nozzle, solid)", "layout choice for a watertight FDM wall", "derived"),
    "gasket": (1.0, "allowance off the closed depth for the lid's O-ring and fit", "assumed until M17", "TBD"),
    "lid_rim": ((3.0, 3.0, 3.0), "#905 lid rim, outside to inside: plastic wall, O-ring channel (white O-ring in it), plastic wall: a 9 mm land; the O-ring path curves in round the four corner bosses", "Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg)", "sourced"),
    "lid_boss": ((22.0, 21.0, 3.0), "#905 lid corner screw boss: along the long side x along the short side (from the outside edges), wall outside the screw hole", "Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg)", "sourced"),
    "rim_tongue": ((2.0, 4.5, 4.0, 3.5), "the base's sealing lip: width, height above the land, centre-line offset from the lid's outside edge on the short sides, and on the long sides; it follows the lid channel's S-curve round each corner boss; the land ends at its inner face", "height 4.5 mm above the land: coupon r3 fit (Clint, 2026-11-10): the land outside the lip lowered 1.5 mm, the lip's top unchanged (the original base's lip is 3 mm, Clint). Offsets: r1 had both at 4.5 (the channel's centre by the sketch); Clint's printed test fit of coupon r1, 2026-11-10 (photo-8533, via the coordinator): the lip moves out 0.5 mm on the short side (4.0) and 1.0 mm on the long side (3.5). Width 2.0 leaves 0.5 mm a side in the 3 mm channel", "derived"),
    "l1_lid_screw": ((8.0, 0.0, 0.0), "L1: the original lid screw: thread diameter, pitch, length (option a, a printed thread to match)", "Clint, 2026-11-10 (photo-8528 rim.jpg and notes, via the coordinator): the original base's corner holes are large moulded threads, about 8 mm (coarse plastic thread in the photo); pitch and length not measured", "TBD"),
    "lid_screw_opt": ("b", "lid screws: (a) a printed thread matching the original screw; (b) M4 stainless screws with washers through the lid's 8 mm holes into M4 heat-set inserts", "layout choice (recommended b: brass inserts survive the lid coming off many times, a printed PETG thread wears; the original screw is not needed)", "derived"),
    "seal_curve_r": ((3.0, 5.5), "radii of the S-curve's bends round each corner boss, on the lip's centre line: the two outer bends (where it leaves the straight legs), the middle bend (round the boss's inner corner); tangent, axis-aligned exits", "photo-8539: outer about R3; Clint's coupon r6 fit, 2026-11-10 (via the coordinator): the middle bend R5.5", "TBD"),
    "seal_s": ((13.5, 14.0), "the full base's S-curve round each corner boss, lip centre line to lip centre line: the segment along the short side sits this far in from the short-side lip line, the segment along the long side this far in from the long-side lip line (both at 17.5 from the outside edges)", "photo-8539: the middle runs 17.5 from both edges; held at r6 on the long side until coupon r8's fit tells more (Clint, 2026-11-10 (via the coordinator))", "sourced"),
    "coupon_bore": (7.0, "the rim coupon's screw hole (the full base keeps the insert's own bore, insert_m4)", "Clint's printed test fit of coupon r1, 2026-11-10 (photo-8533, via the coordinator): 25 % larger than r1's 5.6", "derived"),
    "coupon_long_shift": (2.0, "coupon r8 only, a lip-position test: the long-side edge and its straight lip sit this much further out from the S and the hole than in the base (the S's run along the long side and the hole move with it in the coupon's frame)", "Clint, 2026-11-10 (via the coordinator): the r6 and r7 fits each asked for 1 mm; not applied to the base (the lid's holes are 108-110 apart)", "derived"),
    "coupon_hole": ((12.0, 10.0), "coupon r8's hole centre from the long-side and short-side edges", "the sheet's 10/10 plus coupon_long_shift on the long side; it tests the lip only: check whether it lines up with the lid's hole", "derived"),
    "corner_r_out": (4.0, "the lid's (and the base's) outside corner radius, in plan", "estimated from Clint's photo-8526 at about 13.4 px/mm (about 50 px); measure", "TBD"),
    "coupon_fit": (False, "test-fit coupon (cage.py --coupon): the real lid pressed onto the printed rim corner; the lip in the O-ring along both sides and round the boss's S-curve, the screw hole under the lid's hole", "pending: Clint prints it (about 20 minutes) and fits the lid; set True and sourced when it fits", "TBD"),
    "m4_washer": ((12.0, 1.0), "M4 large (fender) washer, stainless: OD x thickness, for option b, over the lid's 8 mm hole", "ISO 7093-1 size 4 (d2 12, h 1), from the standard's table as remembered: check the ones bought", "TBD"),
    "m4_screw": ((8.0, 3.1, 20.0), "M4 stainless pan-head screw: head diameter, head height, length (option b)", "ISO 7045 M4 head (dk 8, k 3.1), from the standard's table as remembered; length a layout choice: through the lid boss (L1 pending) into the 8 mm insert", "TBD"),
    "lid_pocket": (14.0, "the lid's square corner pocket, inside width (the washer must seat in it); the hole 8 mm through its floor", "pending: Clint's photo-8526 shows a square pocket with a round counterbored hole; width placeholder", "TBD"),
    "l2_screw_pos": ((10.0, 10.5), "L2: lid screw centre from the outside edges: from the short side, from the long side", "Clint, 2026-11-10 (via the coordinator): the lid's two hole centres across the short side are 108-110 apart (first 'exactly 110', then 'could be 108-109'): 109 for now, 10.5 from each long edge of the 130 lid; 10 from the short side (sheet, photo-8539). The coupons' long-edge shifts (r7, r8) are lip tests and are not applied here", "TBD"),
    "l4_oring_proud": (-2.0, "L4: how far the O-ring sits above (+) or below (-) the channel walls", "Clint, 2026-11-10 (lid-measure sheet, via the coordinator): inset about 2 mm below the walls", "sourced"),
    "l5_lid_out": ((175.0, 130.0, 6.0), "L5: lid outside length x width, corner radius (the base matches it; the radius in use is corner_r_out)", "length: Clint, 2026-11-10 (via the coordinator), re-measured 6-14/16 in = 174.6, agreeing with Adafruit's 175 (the earlier 6-3/4 was a misread); width about 130 by Clint's tape (Adafruit 128.5); corner radius a placeholder", "sourced"),
    "base_905": ((175.0, 131.0), "the original #905 base's outside length x width (wider than the lid)", "Adafruit #905 drawing, via the coordinator: base 131 wide against the lid's 128.5", "sourced"),
    "l6_body_rib": ((3.0, 1.5), "L6: the original base's sealing lip: height, and its offset in from the base's outer edge (rough)", "Clint, 2026-11-10 (via the coordinator): 3 mm tall; 1-2 mm in from the base's outer edge, an eyeball estimate (a rough check that disagrees with the channel line)", "sourced"),
    "box_in": ((124.0, 169.0, 120.0), "printed base inside: width x length (up the pole) x depth floor to closed lid (base 97 inside + lid 24 less the gasket allowance)", "from l5_lid_out, base_out_depth, base_wall, lid_depth (its top about 1 mm) and gasket", "derived"),
    "insert_m4": ((5.6, 8.0), "M4 heat-set insert: hole x length", "typical M4 heat-set insert for plastics; check the ones bought", "TBD"),
    "corner_keepout": (20.0, "the insert post's depth below the seam (the corner land's reach comes from seal_s and rim_tongue)", "an M4 heat-set insert (8) with 3 mm of PETG under it, and the screw (L1)", "derived"),
    "evm_under": (4.0, "BQ25798EVM underside: J6 micro-USB (bottom-mounted) and solder tails below the board", "J6 Molex 47346-0001 (SLUUCB5E BOM), right-angle bottom mount; height not reached", "TBD"),
    "vent": (12.5, "M12 pressure-equalising vent: panel hole", "typical M12 x 1.5 vent plug; not chosen yet", "TBD"),
    "power_zone": (82.0, "box bottom to the lowest card's socket row (the EVM shelf in front of the backplane's lower end)", "layout choice: low enough that B3's top clears the lid's upper corner lands by 2 mm", "derived"),
    "gland": ((12.0, 16.6), "PG-7 (#762) gland: panel hole x nut across corners", "hole: the 11.5 mm screw end (" + G7 + ") + 0.5; nut: the PG-9's 22 scaled by 11.5 / 15.2", "derived"),
    "gland_pg7": ((11.5, 6.0, 16.6, 11.4, 3.0, 4.3), "PG-7 (#762): thread, thread length inside (L1), body outside (L2), cap (L3), cable min, max", G7 + ": 11.5 mm screw end, cable 0.118-0.169 in; L1, L2, L3 the PG-9's scaled by 11.5 / 15.2", "derived"),
    "gland_pg9": ((15.2, 7.9, 22.0, 15.1, 4.0, 6.4), "PG-9 (#761): thread D1, thread length inside L1, body outside L2, cap L3, cable min, max", G9 + "; cable 0.158-0.252 in from adafruit.com/product/761", "sourced"),
    "gland_bore": ((7.9, 10.5), "gland bore with the seal out: PG-7, PG-9 (D2)", G9 + ": D2 10.5; PG-7 scaled by 11.5 / 15.2", "derived"),
    "flat_cable": ((2.3, 6.6), "weather-meter flat cable, thickness x width (Clint: the meter cables are flat)", "TE 5-555042-3 flat-cable plug's cable entry, commscope.com/globalassets/digizuite/67464-p360-5-555042-3-external.pdf (not downloaded)", "derived"),
    "sealant": (0.5, "silicone or split grommet round a flat cable in an open gland bore, each side", "assumed", "TBD"),
    "gland_pg9_nut": (22.0, "PG-9 locknut and cap across corners", "not on the drawing (not to scale); typical 19 mm across flats", "TBD"),
    "plug_6p": ((9.65, 6.60, 7.47, 13.34), "6P plug body: width, height, height with the latch, length (latch 5.95 long, 2.77 at its tip; contacts 1.02 pitch)", "Cinch 32-5996UL (AIM-Cambridge) drawing, static.chipdip.ru/lib/750/DOC011750893.pdf (Mouser's copy): drawn for round cable; the standard 6P body for Clint's generic flat-cable 6P6C plugs", "sourced"),
    "plug_len": (25.0, "RJ11 plug beyond the jack mouth, with the flat cable leaving its rear and bending", "the 6P body (plug_6p, 13.34 long, partly inside the jack) and the flat cable's bend (plug_bend); measure one of Clint's plugs", "TBD"),
    "plug_bend": (10.0, "modular cable minimum bend radius behind the plug", "flat 4- or 6-wire modular cable, typical; measure the weather meter's cable", "TBD"),
    "usbc_plug": (7.0, "USB-C plug overmould thickness (console cable)", "typical cable; measure Clint's", "TBD"),
    "sma_ra": ((10.0, 15.0), "Amphenol RF 132172 right-angle adapter: arm lengths", "amphenolrf.com/132172.html drawing; verify", "TBD"),
}


def val(key):
    return D[key][0]


def tbd(key):
    return D[key][3] == "TBD"


def label(key):
    """Text for a drawing label: the value, and the TBD flag when it is a placeholder."""
    v = D[key][0]
    s = "x".join(f"{x:g}" for x in v) if isinstance(v, tuple) else (v if isinstance(v, str) else f"{v:g}")
    return s + " mm" + (" [TBD-MEASURE]" if tbd(key) else "")


def table():
    rows = ["| Key | Value (mm) | What | Source | Status |", "|---|---|---|---|---|"]
    for k, (v, what, src, st) in D.items():
        vs = " x ".join("?" if x is None else f"{x:g}" for x in v) if isinstance(v, tuple) else (v if isinstance(v, str) else f"{v:g}")
        rows.append(f"| `{k}` | {vs} | {what} | {src} | {'[TBD-MEASURE]' if st == 'TBD' else st} |")
    return "\n".join(rows)


BEGIN, END = "<!-- dimensions:begin (generated by sources.py) -->", "<!-- dimensions:end -->"


def sync_readme(check=False):
    p = Path(__file__).resolve().parent / "README.md"
    text = p.read_text()
    a, b = text.index(BEGIN) + len(BEGIN), text.index(END)
    new = text[:a] + "\n" + table() + "\n" + text[b:]
    if check:
        return new == text
    p.write_text(new)
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        ok = sync_readme(check=True)
        print("README dimension table", "in step" if ok else "OUT OF STEP: run python3 sources.py")
        sys.exit(0 if ok else 1)
    sync_readme()
    print("README dimension table written")
