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
ST2 = "BusBoard ST2 stripboard, busboardcom.busboard.us/ST2 (DigiKey 4526-ST2-ND)"

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
    "sb_rails": (3.81, "outer rail from the edge; inner rail 6.35 mm", "drawing p.2 measured against the 2.54 grid", "derived"),
    # ---------------------------------------------------------------- RJ11 port: BOB-14021 + 87180-066LF
    "bob_w": (15.24, "BOB-14021 width (along the header)", SFE + ": outline 0..15.24", "sourced"),
    "bob_d": (20.32, "BOB-14021 depth (snap-off tab removed)", SFE + ": outline 0..20.32", "sourced"),
    "bob_hdr_y": (1.27, "header row from the BOB back edge", SFE + ": JP4 at y 1.27", "sourced"),
    "bob_peg_y": (15.24, "jack peg line from the BOB back edge", SFE + ": JP3 at y 15.24", "sourced"),
    "jack_w": (13.2, "87180 / 54601 jack body width", KRJ + "; RS 771-0215 listing 13.2", "sourced"),
    "jack_d": (18.0, "jack body depth (peg line + 7.88 to the mouth)", KRJ + ": fab -1.23..16.77; RS 18 mm", "sourced"),
    "jack_h": (11.5, "jack body height above the BOB", "RS Components 771-0215 (87180-066LF) listing, 11.5 x 13.2 x 18 mm; test-fit one jack (" + DOC + ")", "sourced"),
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
    "evm": ((None, None, None), "BQ25798EVM outline and tallest part", DOC + " 'Measurements still needed' 2", "TBD"),
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
    "card_bp_gap": (1.97, "card back edge to backplane face", "39.37 (column j) + 1.52 + 2.54 + 5.84 - 5.0 + 8.5 - 50.8", "derived"),
    "strip_pitch": (2.54, "BusBoard ST2 stripboard: hole pitch, strips run the length", ST2, "sourced"),
    "strip_size": ((100.0, 80.0, 1.6), "BusBoard ST2 stripboard, 31 strips x 39 holes (cut to 21 strips wide)", ST2, "sourced"),
    "bp_posts": (7.0, "backplane copper face above the cage back plate (mux, foam and socket tails behind it)", "layout choice", "derived"),
    "cage_plate": (3.0, "cage back plate thickness (PLA)", "layout choice", "derived"),
    "cage_wall": (4.0, "cage left wall thickness; card slots 2 mm deep", "layout choice", "derived"),
    "slot_clear": (0.3, "card slot width over the 1.6 mm card (print tuning)", "Bambu H2D PLA first-print allowance; tune on a test slot", "TBD"),
    "bar": (3.0, "retention bar thickness in front of the card front edges", "layout choice", "derived"),
    "tails": (1.5, "solder tails and bottom-side wires below a card", "typical; measure after the first card", "TBD"),
    "clear": (0.5, "minimum clearance kept between parts", "layout rule", "derived"),
    "bob_spacer": (2.0, "printed spacer under each RJ11 breakout (bonded to the card)", "layout choice", "derived"),
    "do35": ((4.56, 2.0), "DO-35 body length x diameter (1N5232B, BAT85S)", "onsemi 1N5221B series and Vishay BAT85 (doc 88146) outline DO-35/DO-204AH", "sourced"),
    "diode_stand_h": (7.0, "standing DO-35 height (body on one lead, the other looped over)", "4.56 body + 1 lead + loop; check on the part", "TBD"),
    "r_lying_h": (2.5, "lying DIN0207 resistor height (body diameter)", "KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model", "derived"),
    "lug": ((13.5, 1.93), "Keystone 7328 ring solder lug length x thickness", "DigiKey 36-7328-ND listing (verify on the part)", "TBD"),
    "pack": ((69.0, 54.0, 18.0), "battery pack #353", "INVENTORY.md / docs/current-system.md (SHOP:49)", "sourced"),
    "evm": ((88.9, 63.5, 15.0), "BQ25798EVM outline and tallest part (placeholder until measured)", DOC + " 'Measurements still needed' 2", "TBD"),
    "box_out": ((125.0, 175.0, 75.0), "#905 box outside: width x height (hanging, long side up) x depth", DOC + "; adafruit.com/product/905", "sourced"),
    "box_in": ((119.0, 169.0, 69.0), "#905 box inside: width x height x depth back wall to closed lid", "assumed 3 mm walls: measure", "TBD"),
    "boss": ((8.0, 8.0, 6.0), "#905 inside corner bosses: centre from the side walls (x, z) and diameter", "not published: measure", "TBD"),
    "power_zone": (92.0, "box bottom to the lowest card (pack cradle, charger slot, glands' cable bend)", "layout choice", "derived"),
    "gland": ((12.5, 19.0), "PG-7 cable gland: panel hole x nut across corners", "typical PG-7 (12.5 mm hole); confirm with the glands bought", "TBD"),
    "plug_len": (25.0, "RJ11 plug and cable bend beyond the jack mouth", "mechanical review M6 (service loop); measure a plug", "TBD"),
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
    s = "x".join(f"{x:g}" for x in v) if isinstance(v, tuple) else f"{v:g}"
    return s + " mm" + (" [TBD-MEASURE]" if tbd(key) else "")


def table():
    rows = ["| Key | Value (mm) | What | Source | Status |", "|---|---|---|---|---|"]
    for k, (v, what, src, st) in D.items():
        vs = " x ".join("?" if x is None else f"{x:g}" for x in v) if isinstance(v, tuple) else f"{v:g}"
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
