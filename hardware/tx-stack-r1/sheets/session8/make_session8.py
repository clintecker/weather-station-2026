"""Session 8: into the box. Same flat-pack style and pipeline as Sessions 2-7.

Source of truth: hardware/tx-stack-r1/build/ASSEMBLY.md sections 2-5 (parsed by session7/asmd.py), cage/cage.py
(the glands, the inserts, the shelves, the STL gate) and schematic/model.py (the jacks and ports). Pictures:
scenes8.py.

Starting point: Sessions 1-7 are done. The four cards are built, the backplane is wired, the EVM is set for one cell
with its leads on, the pack is unplugged and JP17 is out (Session 7 left the I2C set-up waiting on charger firmware).
This session prints and fits the base, then loads it: backplane, pack, EVM, cards, cables, coax, lid. The pack stays
unplugged and JP17 out to the end.

Usage: .venv-pdf/bin/python make_session8.py [OUT_DIR]     (default: ../out; writes session8-all.pdf)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "session7"))
from sheetlib import *          # noqa: F401,F403,E402
import sheetlib as SL           # noqa: E402
import asmd                     # noqa: E402

SL.LEADER_INK = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
B = asmd.B
DOTC = {"B1": HexColor("#2D6FD0"), "B2": HexColor("#2E9E4F"), "B3": HexColor("#F2C318"), "B4": HexColor("#D7262E")}
CARDS = [("B4", "POWER"), ("B2", "PORTS B + METERS"), ("B1", "PORTS A"), ("B3", "CORE")]   # bottom to top

# facts the pages print, checked against the docs
assert "B1 blue, B2 green, B3 yellow, B4 red" in asmd.plain(asmd.CARDS)
assert "B4 POWER, B2 PORTS B + METERS, B1 PORTS A, B3 CORE" in asmd.TXT
assert "Print the rim test ring first" in B[1] and "ring_fit" in B[1] and "refuses the full base" in B[1]
assert "two M3 heat-set inserts" in B[3] and "Xb 4.5 and 100.25, Yb 106" in B[3]
assert "Bumpon feet peeled off" in B[5] and "clip at the front" in B[5]
assert "[TBD-MEASURE]" in B[7] and "lid-right corner" in B[7]
assert "hose clamps" in B[8]

SLOGANS8 = [
    "THE PACK STAYS UNPLUGGED. JP17 STAYS OUT.",
    "RING FIRST. THEN THE BASE.",
    "MATCH THE DOTS. NEVER FORCE A CARD.",
    "CABLE IN BARE. PLUG ON INSIDE.",
    "METER THE SOLAR LEAD BEFORE J2.",
]


def para(c, x, y, w, s_, size=9.3, lead=12.4, font="ALT", color=INK):
    """Wrap s_ to width w; returns the y under it."""
    out = []
    for block in s_.split("\n"):
        line = ""
        for wd in block.split():
            t = (line + " " + wd).strip()
            if SL.pdfmetrics.stringWidth(t, font, size) > w and line:
                out.append(line)
                line = wd
            else:
                line = t
        out.append(line)
    for i, ln in enumerate(out):
        text(c, x, y - i * lead, ln, size, font, color)
    LAB.block(x - 2, y - lead * len(out) + size * 0.3, x + w, y + size, "text")
    return y - lead * len(out)


def steps_list(c, x, y, w, items, size=9.3, lead=12.4, gap=4, start=1):
    """Numbered steps; wider than 400 pt, they go in two columns."""
    if w > 400 and len(items) > 2:
        k = (len(items) + 1) // 2
        cw = (w - 16) / 2
        y1 = steps_list(c, x, y, cw, items[:k], size, lead, gap, start)
        y2 = steps_list(c, x + cw + 16, y, cw, items[k:], size, lead, gap, start + k)
        return min(y1, y2)
    for i, s_ in enumerate(items):
        text(c, x, y, f"{i + start}.", size, "HEAD", INK)
        y = para(c, x + 14, y, w - 14, s_, size, lead) - gap
    return y


def col_labels(c, a, items, x, side="l", size=8.6, gap=15, lo=None, hi=None, font="ALT", center=False):
    """Chips in one column at x (side 'l': x is their left edge, right of the art; 'r': x is their right edge),
    each at its anchor's height, pushed apart in anchor order so no two leaders cross. items: (anchor, text[, colour])."""
    pts = []
    for it in items:
        k, t = it[0], it[1]
        col = it[2] if len(it) > 2 else INK
        px, py = a.A(k)
        pts.append([py - 3, px, py, t, col])
    pts.sort(key=lambda p: -p[2])
    for i in range(1, len(pts)):
        pts[i][0] = min(pts[i][0], pts[i - 1][0] - gap)
    if center and pts:
        d = (sum(p_[2] for p_ in pts) / len(pts) - 3) - (pts[0][0] + pts[-1][0]) / 2
        for p_ in pts:
            p_[0] += d
    if lo is not None and pts and pts[-1][0] < lo:
        d = lo - pts[-1][0]
        for p_ in pts:
            p_[0] += d
    if hi is not None:
        for i, p_ in enumerate(pts):
            p_[0] = min(p_[0], hi - gap * i)
    for yy, px, py, t, col in pts:
        r = chip(c, x, yy, t, size, font, col, side)
        leader(c, r, px, py)


def check_item(c, x, y, s_, size=8.6, w=None):
    """A magenta 'CHECK' tag: a guess or an open doc fact, to confirm at the bench."""
    r = chip(c, x, y, "CHECK", 7.5, "HEAD", WHITE, "l", fill=NEON)
    if w:
        return para(c, r[2] + 6, y, w - (r[2] + 6 - x), s_, size, 11, "ALT", NEON)
    text(c, r[2] + 6, y, s_, size, "ALT", NEON)
    return y - 14


def note_box(c, x, y, w, title, lines, colour=NEON, fill="#FFE6F1"):
    h = 22 + 12 * len(lines)
    c.setStrokeColor(colour)
    c.setFillColor(HexColor(fill))
    lw(c, 2)
    c.rect(x, y - h, w, h, stroke=1, fill=1)
    text(c, x + 10, y - 13, title, 10.5, "HEAD", colour)
    for i, s_ in enumerate(lines):
        text(c, x + 10, y - 26 - 12 * i, s_, 8.8, "ALT", INK)
    LAB.block(x, y - h, x + w, y, "note box")
    return y - h


# ------------------------------------------------------------------ 00 cover
def cover(c, pg):
    page(c, "00", "SESSION 8: INTO THE BOX",
         "PRINT AND FIT THE BASE, LOAD IT, RUN THE CABLES, SHUT THE LID. NO POWER IN THIS SESSION.", pg, SLOGANS8[0])
    g = Grid(2, 3, heights=[1.45, 1.05, 0.62])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None, "PARTS (build/ASSEMBLY.md sections 2-4, cage/cage.py, schematic/model.py).")
    items = [("RIM TEST RING, THEN THE BASE\nprinted PETG (cage/cage.py)", "ring"),
             ("5 x PG-7 #762, 2 x PG-9 #761,\nM12 VENT, SMA BULKHEAD", "glands_out"),
             ("6P CRIMP PLUGS + 6P CRIMP TOOL\n(RJ11/RJ12)", "plug_round")]
    cw = w / 3
    for i, (name, art) in enumerate(items):
        X0 = x + cw * i
        Art(c, art, X0 + 12, y + 52, cw - 24, h - 64)
        chip(c, X0 + cw / 2, y + 30, name, 8.2, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "ALSO ON THE BENCH.")
    parts = ["4 x M3 HEAT-SET INSERTS (BAR 2, CLIP 2)", "2 x M3 SCREWS (RETENTION BAR)", "HOOK-AND-LOOP STRAP (PACK)",
             "AD1 AMPHENOL 132172 (SMA R/A)", "CX1 135110-01-06.00 COAX", "VOLTAIC P110 6 V 10 W PANEL",
             "22 AWG RED + BLACK, FERRULES", "4 PRINTED LID BOLTS", "2 HOSE CLAMPS OR STRAPS", "SILICONE OR SPLIT GROMMETS"]
    for i, s in enumerate(parts):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(parts), "-  " + s, 9.6, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  RIM TEST RING", "02  THE BASE, INSERTS, LEAK TEST", "03  GLANDS, VENT, BULKHEAD",
             "04  WRONG-CARD TEST (OFF THE BASE)", "05  DOTS, THEN THE BACKPLANE IN", "06  THE PACK ON ITS TRAY",
             "07  THE EVM ON ITS LEDGES", "08  THE CARDS, THEN THE BAR", "09  CABLE RUNS AND LABELS",
             "10  ROUND CABLES: 6P INSIDE", "11  WIND AND RAIN CABLES", "12  THE SOLAR LEAD TO J2",
             "13  THE COAX", "14  BEFORE POWER, LID, MOUNT", "15  REPORT"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 16 - i * (h - 10) / len(steps), s, 11, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["THE PACK STAYS OFF PG1 AND JP17 STAYS OUT, ALL SESSION (SESSION 7: THE CHARGER WAITS ON FIRMWARE).",
             "NO USB AND NO SUN ON THE PANEL WHILE YOU WIRE. COVER THE PANEL OR LEAVE IT FACE DOWN.",
             "A CARD THAT WON'T GO THE LAST FEW MM IS IN THE WRONG SLOT. NEVER FORCE IT."]
    for i, s in enumerate(rules):
        yy = y + h - 12 - i * (h - 8) / 3
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 8.8, "ALT", INK)


# ------------------------------------------------------------------ 00 what you are building
def built(c, pg):
    page(c, "00", "WHAT YOU ARE BUILDING", "THE BOX, LOADED. THIS IS WHERE THE SESSION ENDS (LID OFF IN THE PICTURE).", pg,
         SLOGANS8[0])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Seen from the lid side, glands down, walls cut low so nothing hides. Bottom to top: the cable space over the",
        "glands, the pack on its tray, the EVM on its ledges, then the four cards in their slots: B4, B2, B1, B3.",
        "The retention bar holds them at the front left. Cables come up through the glands into the right column."])
    a = Art(c, "built", x + 30, y + 20, w - 230, h - 60, align="l")
    for b, nm in reversed(CARDS):
        px, py = a.A(f"{b}_front")
        r = chip(c, a.x + a.w + 30, py - 3, f"{b} {nm}", 9, "ALT", INK)
        leader(c, r, px, py)
    label(c, x + 44, y + h - 30, "RETENTION BAR (2 x M3)", *a.A("bar"), 9)


# ------------------------------------------------------------------ 01 the rim ring
def ring(c, pg):
    page(c, "01", "PRINT THE RIM TEST RING FIRST", "ASSEMBLY.md 2.1. CAGE.PY --RING: CAGE/STL/RIM-RING.STL. ABOUT AN HOUR.",
         pg, SLOGANS8[1])
    g = Grid(1, 2, heights=[1.0, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["The whole rim: 175.5 x 129.5 x 8 mm. Print it flat on its land."])
    a = Art(c, "ring", x + 40, y + 10, w - 180, h - 44, align="l")
    label(c, x + w - 12, y + h - 30, "SEALING LIP", *a.A("lip"), 9.5, anchor="r")
    label(c, x + w - 12, y + 40, "BOLT HOLE (ONE OF 4)", *a.A("hole"), 9.5, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["When it fits: set ring_fit True in the sources. The base waits until then."])
    yy = steps_list(c, x + 44, y + h - 18, w - 70, [
        "Press the real lid onto the ring.",
        "The lid's lip drops into the O-ring channel all the way round, through all four S-curves.",
        "All four holes sit under the lid's four at once.",
        "The outer edge is flush on all four sides.",
        "If any of that fails: correct cage/lid-rim-spec.md, reprint the ring, try again."])
    yy = note_box(c, x + 44, yy - 6, w - 70, "THE BASE STL IS GATED", [
        "cage.py --stl refuses the full base until ring_fit and l2_screw_pos (the lid bolt positions) are",
        "sourced. Right now both are open, so there is no base file to print yet. Don't hand-edit around it."],
        colour=NEON)
    check_item(c, x + 44, yy - 16, "evm and evm_under (the EVM's part heights, J6 under it) are TBD too: measure them.")


# ------------------------------------------------------------------ 02 the base
def base_page(c, pg):
    page(c, "02", "THE BASE: COUPON, PRINT, INSERTS, LEAK TEST", "ASSEMBLY.md 2.2-2.3. ONLY AFTER THE RING FITS.", pg,
         SLOGANS8[1])
    g = Grid(2, 2, heights=[1.15, 0.85])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Iso from the lid side. The insert spots in brass."])
    a = Art(c, "base_ins", x + 6, y + 10, w - 84, h - 46, align="l")
    col_labels(c, a, [("bar_ins1", "BAR INSERT"), ("bar_ins0", "BAR INSERT"), ("clip_ins1", "CLIP INSERT"),
                      ("clip_ins0", "CLIP INSERT")], a.x + a.w + 6, lo=y + 16)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["The four inserts, with the iron."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Retention bar: two M3 heat-set inserts in the left wall's front face (Xb 5, Zb 76.5 and 146.5).",
        "EVM clip: two M3 inserts straight down into the left keeper and the right lid-end block (Xb 4.5 and 100.25, "
        "Yb 106).",
        "No inserts in the four corner posts: the lid's printed bolts thread their bores."], 9)
    check_item(c, x + 14, yy - 8, "The clip part itself isn't in cage.py yet: only its two insert bores are.", w=w - 24)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "From ASSEMBLY.md 2.2 and 2.3. The coupon's shape isn't in the repo yet: cage.py has no coupon mode."])
    yy = steps_list(c, x + 44, y + h - 18, w / 2 - 50, [
        "Test coupon: one card slot (tune slot_clear until a card slides with light friction), one lid bolt post "
        "(try a printed bolt in it), one lid corner of land and tongue, and a 30 mm square of wall to leak-test.",
        "Fit the lid on the coupon's corner: the lip presses the O-ring with the lid's walls down on the land."], 9)
    check_item(c, x + 44, yy - 6, "Coupon shape: design it from the list above.", w=w / 2 - 50)
    steps_list(c, x + w / 2 + 10, y + h - 18, w / 2 - 22, [
        "Print the base in light PETG, floor on the bed (Yb up), not rim down. Solid walls: about 9-10 perimeters at "
        "a 0.42 mm line.",
        "Leak test: water in the bare base, or soapy water with the lid on and a little pressure through the vent "
        "hole. Coat the inside only if it leaks.",
        "Paint or clear-coat the outside against UV."], 9)


# ------------------------------------------------------------------ 03 glands
GLAND_ORDER = ["S1 TH", "S2 UV", "S3 BARO", "S4 SPARE", "SOLAR", "WIND", "RAIN"]


def glands(c, pg):
    page(c, "03", "GLANDS, VENT, SMA BULKHEAD", "ASSEMBLY.md 2.4. THE BOTTOM WALL'S BOSSES, AND THE RIGHT WALL.", pg,
         SLOGANS8[3])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["Outside, from below and in front.", "Write each label on its gland's",
                                             "boss before you fit it."])
    a = Art(c, "glands_out", x + 130, y + 10, w - 260, h - 46)
    g_ = lambda n: "g_" + n.replace(" ", "_")
    col_labels(c, a, [(g_(n), n) for n in ("S4 SPARE", "SOLAR", "S1 TH", "S2 UV")], a.x - 6, side="r", font="HEAD",
               lo=y + 16)
    col_labels(c, a, [(g_(n), n) for n in ("S3 BARO", "RAIN", "WIND")] + [("vent", "M12 VENT"),
                      ("sma_bh", "SMA BULKHEAD")], a.x + a.w + 6, font="HEAD", lo=y + 16)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Seven glands, no spare hole. The vent and", "the bulkhead go in now too."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Five 13 mm holes take PG-7s (#762): the four port cables S1-S4 and the solar lead.",
        "Two 15.5 mm holes take PG-9s (#761), under the right column: the flat wind and rain cables.",
        "Body from outside, nut inside, tight. Leave each cap loose with its seal in: the cables go through later "
        "(pages 10-12).",
        "The M12 vent in its hole in the bottom wall.",
        "The SMA bulkhead low in the right wall (Yb 94.14, Zb 60.38), nut inside."], 9)
    yy = para(c, x + 44, yy - 4, w - 56, "PG-7 bore 7.9 mm, PG-9 10.5 mm: no 6P plug passes either one, even with the "
              "seal out. Every cable goes in bare and gets its plug inside.", 9)
    check_item(c, x + 14, yy - 10, "Which PG-7 takes which cable isn't in the docs. This sheet's split: back row "
               "S1, S2, S3 left to right; lid row S4, then the solar lead.", w=w - 24)


# ------------------------------------------------------------------ 04 the wrong-card test
def keytest(c, pg):
    page(c, "04", "THE WRONG-CARD TEST, OFF THE BASE", "BACKPLANE.md 2 KEY PLUGS. ON THE BENCH, BEFORE ANY CARD GOES IN.",
         pg, SLOGANS8[2])
    g = Grid(1, 2, heights=[1.15, 0.85])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "The backplane flat on the bench, sockets up, the EVM resting beside it on its leads. Tick every box."])
    para(c, x + 44, y + h - 22, w - 70, "Each card goes into each of the three sockets that aren't its own, by hand, "
         "straight in. The key plugs must stop it at the socket mouth: the header pins don't enter. Twelve tries. "
         "Then each card into its own socket, all the way, and back out.", 9.5)
    cw, x0, y0 = 88, x + 140, y + h - 92
    text(c, x0 - 120, y0 + 4, "CARD  \\  SOCKET", 9.5, "HEAD", INK)
    for j, (b, _n) in enumerate(CARDS):
        c.setFillColor(DOTC[b])
        c.circle(x0 + cw * j + 18, y0 + 8, 4, stroke=0, fill=1)
        text(c, x0 + cw * j + 26, y0 + 4, f"{b} SOCKET", 9.5, "HEAD", INK)
    for i, (b, nm) in enumerate(CARDS):
        yy = y0 - 30 - 30 * i
        c.setFillColor(DOTC[b])
        c.circle(x0 - 112, yy + 4, 4, stroke=0, fill=1)
        text(c, x0 - 102, yy, f"{b} {nm}", 9.5, "HEAD", INK)
        for j, (s_, _n) in enumerate(CARDS):
            bxl = x0 + cw * j + 18
            c.setStrokeColor(INK if s_ != b else NEON)
            lw(c, 1.2)
            c.rect(bxl, yy - 6, 18, 18, stroke=1, fill=0)
            text(c, bxl + 24, yy, "STOPS" if s_ != b else "GOES IN", 8, "ALT", GREY if s_ != b else NEON)
    LAB.block(x0 - 125, y0 - 30 * 4 - 10, x0 + cw * 4 + 10, y0 + 16, "table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["If a wrong card goes in: stop. The key plug on that socket is missing or loose."])
    steps_list(c, x + 44, y + h - 18, w - 70, [
        "Look at the socket: one pin in one contact per socket (Session 6, page 01). Refit it, then redo that row.",
        "Push gently. You're testing the plug, not the socket. A card that's stopped needs no force to come back out.",
        "No card into any socket at an angle: the pins bend."], 9.5)


# ------------------------------------------------------------------ 05 dots and the backplane
def dots_bp(c, pg):
    page(c, "05", "DOTS BESIDE THE SLOTS, THEN THE BACKPLANE IN", "ASSEMBLY.md 3 (THE SLOT KEY) AND 2.4.", pg, SLOGANS8[2])
    g = Grid(2, 2, heights=[1.3, 0.7])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["A dot of each card's colour on the left wall,", "beside its slot, in front of the cards."])
    a = Art(c, "dots", x + 8, y + 10, w - 110, h - 46, align="l")
    for b, nm in reversed(CARDS):
        px, py = a.A(f"dot_{b}")
        r = chip(c, a.x + a.w + 12, py - 3, f"{b}", 9.5, "HEAD", INK)
        leader(c, r, px, py)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["Tilt the right edge in, lower, slide left."])
    a = Art(c, "bp_in", x + 10, y + 10, w - 20, h - 46)
    label(c, x + 40, y + h - 22, "LEFT EDGE: INTO THE LEFT WALL'S GROOVE", *a.A("bp_left"), 8.5)
    label(c, x + w - 10, y + 22, "FACTORY RIGHT EDGE: RIGHT POST'S SLOT", *a.A("bp_right"), 8.5, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 1), 3, ["The same colours as on the card edges and the sockets."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "B1 blue, B2 green, B3 yellow, B4 red. Top to bottom: B3, B1, B2, B4.",
        "If a card's front edge has no dot yet (Session 1), add it now."], 9)
    x, y, w, h = panel(c, g.cell(1, 1), 4, ["It comes out again only after every card is out."])
    steps_list(c, x + 44, y + h - 18, w - 56, [
        "No screws: the cards hold it. Fit them straight after (page 08).",
        "The EVM and the pack lead come along on their leads. Rest the EVM in front of the base meanwhile."], 9)


# ------------------------------------------------------------------ 06 the pack
def pack_page(c, pg):
    page(c, "06", "THE PACK ON ITS TRAY", "ASSEMBLY.md 2.5 AND 1.3. THE BOTTOM SHELF. THE PACK STAYS UNPLUGGED.", pg,
         SLOGANS8[0])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["Lid side, walls cut low. The pack lies flat,", "label up toward the lid."])
    a = Art(c, "pack_in", x + 150, y + 10, w - 96, h - 46, align="l")
    col_labels(c, a, [("strap", "STRAP"), ("pack", "#353 PACK"), ("rt1", "RT1, TAPED"), ("pg1", "PLUG: NOT IN PG1", NEON)],
               a.x + a.w + 6, lo=y + 16)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Session 7 made these leads. Nothing new", "is soldered here."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Thread the hook-and-loop strap through the tray's two slots (3 x 20 mm, either side of the pack).",
        "Slide the pack back onto the tray, flat, until it meets the back. The tray's front lip ramps up in front "
        "of it.",
        "Strap it down, snug.",
        "Tape RT1 (the #372 thermistor bead on its leads to J7) flat to the pack's face, with a square of tape over "
        "the bead.",
        "The pack's plug stays apart from PG1's socket, taped. Its - lead goes up to J5 GND, its + lead (via PG1) "
        "to backplane line 21: both from Session 7.",
        "Leave slack on every lead: the EVM goes on the shelf above next."], 9)
    check_item(c, x + 14, yy - 8, "Where on the pack RT1 sits isn't set. This sheet puts it on the face toward the lid, "
               "middle.", w=w - 24)


# ------------------------------------------------------------------ 07 the EVM
def evm_page(c, pg):
    page(c, "07", "THE EVM ON ITS LEDGES", "ASSEMBLY.md 2.5. BUMPONS OFF, SLID BACK TO THE STOP, CLIP AT THE FRONT.", pg,
         SLOGANS8[0])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["The EVM over the pack: its left edge on the", "left wall's ledge, its right "
                                             "edge on the fin."])
    a = Art(c, "evm_in", x + 130, y + 10, w - 92, h - 46, align="l")
    col_labels(c, a, [("J2", "J2 (SOLAR)"), ("J8", "J8 TO XJ1"), ("J3", "J3 (SYS)"), ("J5", "J5 (BATT.)"),
                      ("clip_ins1", "CLIP INSERT"), ("clip_ins0", "CLIP INSERT")], a.x + a.w + 6, lo=y + 16)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["J6, the USB, is under the left edge. It's for", "the bench only: no gland, "
                                             "no cable in the box."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Peel the four Bumpon feet off the EVM's underside.",
        "Top face up, J8 toward the lid, J3/J5 on the right. Lower it over the pack and slide it back on the "
        "ledges until it meets the stop. The ledges are notched under its edge tails.",
        "Fit the front clip with two M3 screws into the inserts in front of the board.",
        "Every lead keeps a service loop: the EVM must slide out on them.",
        "JP17 stays out. Look for it before you move on."], 9)
    check_item(c, x + 14, yy - 8, "The front clip isn't drawn anywhere in the repo (cage.py only has its insert bores). "
               "Until it's designed, the EVM rests on its ledges with nothing in front.", w=w - 24)


# ------------------------------------------------------------------ 08 the cards
def cards_page(c, pg):
    page(c, "08", "THE CARDS, THEN THE BAR", "ASSEMBLY.md 3. BOTTOM TO TOP: B4, B2, B1, B3. MATCH THE DOTS.", pg,
         SLOGANS8[2])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["Each card in from the lid side, along its", "left-wall slot and right-post slot."])
    a = Art(c, "cards_in", x + 130, y + 10, w - 260, h - 46)
    for b, nm in reversed(CARDS):
        px, py = a.A(f"{b}_front")
        r = chip(c, a.x + a.w + 8, py - 3, b, 9.5, "HEAD", INK)
        leader(c, r, px, py)
    label(c, x + 30, y + 40, "RETENTION BAR, 2 x M3, LAST", *a.A("bar"), 9)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["To take one out: bar off, unplug its own plugs,", "slide it out. No card needs "
                                             "another out first."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Back rails snapped off and the edge filed flat on every card (step 1 of each card's sheet).",
        "B4 POWER first, at the bottom. Then B2 PORTS B + METERS, B1 PORTS A, and B3 CORE on top.",
        "Slide it in until the header pins enter the socket (4.96 mm), then on until the header's plastic meets "
        "the socket (0.84 mm further).",
        "Won't go the last few mm? Wrong slot. Out, check the dots, never force it.",
        "On B1 and B2 the RJ11 jacks overhang the front edge, mouths toward the lid.",
        "The retention bar last: front left, two M3 screws into the inserts."], 9)


# ------------------------------------------------------------------ 09 cable runs
def runs(c, pg):
    page(c, "09", "CABLE RUNS AND LABELS", "ASSEMBLY.md 2.6. PLUG, RIGHT COLUMN, DOWN, LEFT UNDER THE TRAY, ITS GLAND.", pg,
         SLOGANS8[3])
    g = Grid(2, 2, heights=[1.25, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["From the lid. Each cable from its jack's plug to its gland (drawn bundled)."])
    a = Art(c, "cables", x + 150, y + 10, w - 300, h - 46)
    names = [("S1_TH", "S1 TH (J11, B1)"), ("S2_UV", "S2 UV (J12, B1)"), ("S3_BARO", "S3 BARO (J13, B1)"),
             ("S4_SPARE", "S4 SPARE (J14, B2)"), ("WIND", "WIND (J21, B2)"), ("RAIN", "RAIN (J22, B2)")]
    left = [("plug_" + k, nm) for k, nm in names if a.A("plug_" + k)[0] < a.x + a.w * 0.45]
    right = [("plug_" + k, nm) for k, nm in names if a.A("plug_" + k)[0] >= a.x + a.w * 0.45]
    col_labels(c, a, left + [("c_SOLAR", "SOLAR LEAD TO J2")], a.x - 8, side="r", lo=y + 16)
    col_labels(c, a, right, a.x + a.w + 8, lo=y + 16)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Label each cable at its gland, outside,", "before it goes through."])
    yy = para(c, x + 44, y + h - 22, w - 56, "Flag labels, a hand's width out from the gland:", 9.3)
    for i, nm in enumerate(GLAND_ORDER):
        text(c, x + 60 + (i % 2) * 100, yy - 6 - 15 * (i // 2), nm, 10.5, "HEAD", INK)
    LAB.block(x + 56, yy - 6 - 15 * 3 - 4, x + 260, yy + 4, "names")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["The USB (J6) has no gland: bench only."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Port numbers come from the schematic: S1 TH on J11, S2 UV on J12, S3 baro on J13, S4 spare on J14.",
        "Inside: a " + asmd.LOOP + " mm service loop in the space in front of the cards, then down the right column "
        "and left under the pack tray to the gland.",
        "Outside: a drip loop below each gland before the cable is tied to the pole."], 8.8, lead=11.6, gap=2)
    check_item(c, x + 14, yy - 4, "No spec routes the solar lead. Drawn: up the right column, over the EVM, "
               "down the left side to J2.", w=w - 24)


# ------------------------------------------------------------------ 10 round cables
def round_page(c, pg):
    page(c, "10", "ROUND PORT CABLES: PLUG ON INSIDE", "ASSEMBLY.md 2.6. S1-S4 THROUGH THEIR PG-7S, BARE END FIRST.", pg,
         SLOGANS8[3])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["A 6P plug, contacts up, cable toward you.", "Conductors in positions 2-5."])
    a = Art(c, "plug_round", x + 170, y + 20, w - 200, h - 56, align="l")
    col_labels(c, a, [(f"pin{pin}", f"{pin}  {what}") for pin, what in asmd.PORT_PINS] +
               [("pin1", "1  empty", GREY), ("pin6", "6  empty", GREY)], a.x - 50, side="r", gap=16, center=True)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Same pin order as the module end:", "2 3.3 V, 3 data, 4 ground, 5 clock."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "From outside, slide the gland's cap, then its seal, then the body's bore over the cable's bare end.",
        "Pull the length through: the plug, a " + asmd.LOOP + " mm loop, the run to the gland.",
        "Lay the cable's module-end plug next to the new plug, both the same way up. Copy the colours position by "
        "position.",
        "Strip the jacket, trim the conductors square, push them to the end, crimp with the 6P tool.",
        "Plug it into its jack. Tighten the cap until the seal grips."], 9)
    check_item(c, x + 14, yy - 8, "The conductor colours aren't in the docs. The picture shows them grey: copy your "
               "module end.", w=w - 24)
    check_item(c, x + 14, yy - 36, "PG-7 cable range is 3.0-4.3 mm. Measure the cable: if it's bigger, it won't seal.",
               w=w - 24)


# ------------------------------------------------------------------ 11 wind and rain
def flat_page(c, pg):
    page(c, "11", "WIND AND RAIN: CUT, PASS, RE-CRIMP", "ASSEMBLY.md 2.6. SEN-15901 FLAT CABLES THROUGH THE PG-9S.", pg,
         SLOGANS8[3])
    g = Grid(2, 2, heights=[1.1, 0.9])
    for col, (art, nm, pins) in enumerate((("plug_wind", "WIND (M1): POSITIONS 2-5", (2, 3, 4, 5)),
                                           ("plug_rain", "RAIN (M2): POSITIONS 3-4", (3, 4)))):
        x, y, w, h = panel(c, g.cell(col, 0), col + 1, [nm])
        a = Art(c, art, x + 130, y + 20, w - 140, h - 56, align="l")
        col_labels(c, a, [(f"w{p_}", f"{p_}: COLOUR ____") for p_ in pins], a.x - 30, side="r", gap=18, center=True)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "If the crimp plugs won't hold the narrower flat cable with each conductor on its position, use 6P4C plugs."])
    yy = steps_list(c, x + 44, y + h - 18, w / 2 - 50, [
        "The meters' cables come with plugs. Before you cut: write down which colour sits at which position "
        "(wind 2-5, rain 3-4). Use the boxes above.",
        "Cut the plug off outside the box.",
        "Take the PG-9's seal out. Pass the cable in through it."], 9)
    steps_list(c, x + w / 2 + 10, y + h - 18, w / 2 - 22, [
        "Crimp a new 6P plug inside, same order as the old one.",
        "Plug wind into J21 and rain into J22, both on B2.",
        "Once the cable's place is final, seal the gap round it with silicone or a split grommet. After that it "
        "comes out only if you cut the seal, and the plug."], 9, gap=4)


# ------------------------------------------------------------------ 12 solar
def solar(c, pg):
    page(c, "12", "THE SOLAR LEAD TO J2 (VIN2)", "VOLTAIC P110, 6 V 10 W. ITS BARREL CUT AT THE GLAND. INTO EVM J2.", pg,
         SLOGANS8[4])
    g = Grid(1, 2, heights=[1.0, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["EVM top face, lid edge down. J2 is on the left edge, below J1."])
    a = Art(c, "solar_j2", x + 30, y + 10, w * 0.5, h - 46, align="l")
    col_labels(c, a, [("J2", "J2: VIN2 (SOLAR +) AND GND"), ("sol0", "RED: PANEL +"), ("sol1", "BLACK: PANEL -")],
               a.x + a.w + 20, size=9, gap=18)
    yy = check_item(c, a.x + a.w + 20, y + 56, "Which J2 position is VIN2: read the silk.", w=w - a.w - 70)
    check_item(c, a.x + a.w + 20, yy - 4, "22 AWG red/black, bootlace ferrules.", w=w - a.w - 70)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Panel face down or covered while you wire. Meter BEFORE the ends go into J2."])
    yy = steps_list(c, x + 44, y + h - 18, w / 2 - 50, [
        "Cut the P110's barrel plug off, outside the box.",
        "Slide cap, seal and body over the bare end; pull it through the SOLAR PG-7. Leave a " + asmd.LOOP +
        " mm loop inside.",
        "If the panel's own lead doesn't reach J2, splice 22 AWG red and black inside, under heat shrink.",
        "Strip 6 mm, crimp a ferrule on each end."], 9)
    yy = note_box(c, x + w / 2 + 6, y + h - 14, w / 2 - 18, "POLARITY, BEFORE J2", [
        "Meter on DC volts. Ends apart, not in J2.",
        "Turn the panel to the light.",
        "Red probe on the red end, black on black:",
        "it reads positive, about 6-7 V in sun.",
        "Negative? The colours are swapped. Fix",
        "them before anything goes into J2.",
        "Panel face down again, then screw the ends",
        "into J2 and tighten the gland's cap."], colour=INK, fill="#FFF6D6")


# ------------------------------------------------------------------ 13 coax
def coax(c, pg):
    page(c, "13", "THE COAX TO THE BULKHEAD", "ASSEMBLY.md 2.7. AD1 ON THE WIO-E5 MINI, 135110 PLUG, RIGHT COLUMN.", pg,
         SLOGANS8[3])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["From the lid side, a little from the right."])
    a = Art(c, "coax", x + 130, y + 10, w - 96, h - 46, align="l")
    col_labels(c, a, [("ad1", "AD1 132172"), ("plug", "135110 PLUG"), ("coax", "COAX"), ("bh_plug", "BULKHEAD PLUG"),
                      ("evm_corner", "EVM CORNER", NEON)], a.x + a.w + 6, size=8.3, lo=y + 16)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Clint checked the length on 2026-11-17: it fits", "the low bulkhead with "
                                             "no tight bend."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Fit AD1 on the Wio-E5 mini's SMA (on B3), its arm toward the lid.",
        "Screw the 135110 cable's plug onto AD1.",
        "Bend the cable right, in front of the cards, and run it down the right column.",
        "Screw the other plug onto the bulkhead's inner end. Clip the cable to the right corner post.",
        "To take B3 out later, this is its plug: unscrew it at AD1."], 9)
    check_item(c, x + 14, yy - 8, "TBD-MEASURE: does the straight plug on the bulkhead's inner end clear the EVM's "
               "lid-right corner? If not, use a right-angle plug.", w=w - 24)


# ------------------------------------------------------------------ 14 before power, lid, mount
def close(c, pg):
    page(c, "14", "BEFORE POWER, THE LID, THE MOUNT", "ASSEMBLY.md 5 AND 2.8. STILL NO PACK, STILL NO USB.", pg,
         SLOGANS8[0])
    g = Grid(2, 2, heights=[1.1, 0.9])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["ASSEMBLY.md section 5 word for word (its section 1 is Session 7), then this session's own checks."])
    rows = asmd.BEFORE + ["Every gland cap tight; the wind and rain gaps sealed; the vent in.",
                          "The retention bar on, both screws. The EVM on its ledges, JP17 still out.",
                          "No USB in J6, no sun on the panel, the pack's plug still apart from PG1."]
    for i, s_ in enumerate(rows):
        yy = y + h - 24 - i * 19
        c.setStrokeColor(INK)
        lw(c, 1.2)
        c.rect(x + 44, yy - 4, 12, 12, stroke=1, fill=0)
        text(c, x + 64, yy, s_, 9.5, "ALT", INK)
    LAB.block(x + 40, y + h - 24 - len(rows) * 19, x + w - 10, y + h - 10, "checklist")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["From the back: a flange at each short end."])
    a = Art(c, "mount", x + 8, y + 10, w - 120, h - 46, align="l")
    label(c, x + w - 10, y + h - 26, "FLANGE, 2 SLOTS", *a.A("flange_top"), 8.6, anchor="r")
    label(c, x + w - 10, y + 24, "FLANGE, 2 SLOTS", *a.A("flange_bot"), 8.6, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Glands down, always."])
    steps_list(c, x + 44, y + h - 18, w - 56, [
        "The lid on, with its four printed bolts.",
        "Hose clamps or straps through the two slots in each flange.",
        "Drip loops below each gland, then tie the cables to the pole.",
        "J6 USB stays inside: to use it, the lid comes off."], 9)


REPORT_ROWS = [("RIM RING FITS (RING_FIT)", "Y / N", "page 01: lip, 4 holes, flush"),
               ("WRONG-CARD TEST: 12 STOPS", "Y / N", "page 04"),
               ("LEAK TEST, BARE BASE", "Y / N", "page 02"),
               ("SOLAR, OPEN CIRCUIT IN SUN", "V", "page 12, before J2"),
               ("WIND / RAIN COLOURS", "WRITE", "page 11, before you cut"),
               ("COAX PLUG CLEARS THE EVM", "Y / N", "page 13 (TBD-MEASURE)"),
               ("3.3 V TO GROUND, BACKPLANE", "kohm", "page 14: more than 1"),
               ("PHOTO, LID OFF, FROM THE LID", "SENT", "every label readable")]


def report(c, pg):
    page(c, "15", "REPORT THE BOX.", "LOADED AND SHUT. SEND THE NUMBERS.", pg, SLOGANS8[0])
    g = Grid(1, 2, heights=[1.6, 0.4])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Send these to Claude. They close the CHECK items on pages 01-13."])
    for i, (lab, unit, exp) in enumerate(REPORT_ROWS):
        yy = y + h - 22 - i * (h - 16) / len(REPORT_ROWS)
        text(c, x + 44, yy, lab, 13, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.8)
        c.rect(x + 330, yy - 8, 110, 24, stroke=1, fill=0)
        text(c, x + 448, yy, unit, 11, "HEAD", INK)
        text(c, x + 44, yy - 12, exp, 8.5, "MONO", GREY)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Next: the CHARGER check (Session 7 page 09). The firmware is ready."])
    for i, s_ in enumerate(["Flash the TX built with WS_POWER_PROFILE=3 WS_I2C_MUX=1. USB in J6, no pack, JP17 out. Type CHARGER:",
                            "cells=1 vreg_mv=4200 ichg_ma=900 ts=NORMAL hold=none. Then refit JP17 and plug the pack into PG1, last."]):
        text(c, x + 44, y + h - 22 - i * 16, "-  " + s_, 10, "ALT", INK)


PAGES = [cover, built, ring, base_page, glands, keytest, dots_bp, pack_page, evm_page, cards_page, runs, round_page,
         flat_page, solar, coax, close, report]
HOLE_ISSUES = []


def build(path, fns):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 8: into the box")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(cv, i + 1)
        n = LAB.check()
        issues += len(n)
        hi = SL.HC.check(i + 1)
        for m in hi:
            print("  HOLE", m)
        HOLE_ISSUES.extend(hi)
        SL.HC.reset()
        cv.showPage()
    cv.save()
    return issues


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    bad = build(OUT / "session8-all.pdf", PAGES)
    print("ok", len(PAGES), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
