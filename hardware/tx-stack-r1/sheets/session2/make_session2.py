"""Session 2: build B4 POWER. Same flat-pack style and pipeline as Session 1 v2.

Source of truth: hardware/tx-stack-r1/build/B4.md (and ASSEMBLY.md section 4 for the off-card lead lengths);
geometry from layout/stack.py + layout/route.py via scenes2.py.
Hole names: the board prints ROWS as letters (A-J) and COLUMNS as numbers (1-30). B4.md writes holes as
letter + number ('e10'); here that is shown as printed: E10 = row E, column 10.

Usage: pdfenv/bin/python make_session2.py [OUT_DIR]
"""
import sys
from pathlib import Path

from sheetlib import *          # noqa: F401,F403  (page furniture, chips, leaders, Art, checks)
import sheetlib as SL

SL.LEADER_INK = True        # every leader black on a white halo: never red or magenta lines on the red card

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "out"
RED = HexColor("#D7262E")
WIRE = {"RED": HexColor("#D7262E"), "BLACK": HexColor("#1C1C1C"), "YELLOW": HexColor("#E0B000"),
        "BLUE": HexColor("#2D6FD0")}

SLOGANS2 = [
    "B4 POWER FEEDS THE OTHERS. IT IS BUILT FIRST.",
    "TOP IS THE FACE THAT READS. THE MACHINE CHECKED.",
    "A WIRE UNDER A PART CANNOT BE FIXED LATER.",
    "THIRTY PINS. THIRTY LINES. NONE PULLED.",
    "THE BATTERY GOES WHERE THE MAP SAYS. NOWHERE ELSE.",
    "METER FIRST. POWER NEVER. NOT TODAY.",
    "PINS PULLED ARE PINS THAT CANNOT LIE.",
]


def hole(h):
    """B4.md hole -> as printed on the board."""
    if h.startswith("F+"):
        return f"+ RAIL {h[2:]}"
    if h.startswith("F-"):
        return f"− RAIL {h[2:]}"
    return h[0].upper() + h[1:]


def anchor_name(h):
    return h if h.startswith("F") else h[0].upper() + h[1:]


# B4.md section 2, with the colour this sheet suggests per line (B4.md names no colours for the solid wires)
UNDER = [  # (#, from, to, cut mm, bends, line, colour)  B4.md section 2 (repo 91a5345, unchanged)
    (1, "f1", "F+1", 40, 0, "3.3 V", "RED"),
    (2, "f2", "F-2", 35, 0, "GROUND", "BLACK"),
    (3, "i12", "F-20", 65, 3, "GROUND", "BLACK"),
    (4, "h24", "F+24", 55, 4, "3.3 V", "RED"),
    (5, "a10", "F+10", 20, 0, "3.3 V", "RED"),
    (6, "a20", "F+21", 25, 1, "3.3 V", "RED"),
    (7, "h25", "F-25", 60, 4, "GROUND", "BLACK"),
    (8, "a9", "F-9", 20, 0, "GROUND", "BLACK"),
    (9, "a19", "F-19", 20, 0, "GROUND", "BLACK"),
    (10, "d8", "g7", 40, 3, "I2C CLOCK SCL", "YELLOW"),
    (11, "d18", "h7", 65, 5, "I2C CLOCK SCL", "YELLOW"),
    (12, "d7", "g10", 45, 3, "I2C DATA SDA", "BLUE"),
    (13, "d17", "h10", 50, 3, "I2C DATA SDA", "BLUE"),
]
GROUPS = [([1, 2, 3], "BUS POWER TO THE FRONT RAILS"), ([4, 7], "REGULATOR 3.3 V AND GROUND TO THE RAILS"),
          ([5, 8, 10, 12], "THE INA228'S POWER, CLOCK AND DATA"), ([6, 9, 11, 13], "THE MAX17048'S POWER, CLOCK AND DATA")]


def ring(c, x, y, r=4.2, color=None, w=1.6):
    """Hole marker that reads on the red card: hazard yellow on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(HAZ)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def ring_label(c, a, h, s=None, dx=0, dy=14, size=9, color=NEON):
    """Ring hole h on Art a and put its printed name on a chip offset by (dx, dy)."""
    px, py = a.A(anchor_name(h))
    ring(c, px, py, color=color)
    r = chip(c, px + dx, py + dy - size * 0.36, s or hole(h), size, "ALT", color, "c")
    leader(c, r, px, py + (4.2 if dy > 0 else -4.2) if abs(dx) < 1 else py, color, dot=False, w=0.8)
    return r


def face_tag(c, x, y, face):
    """Black tag naming the face shown."""
    s = "TOP FACE" if face == "top" else "UNDERSIDE"
    w = pdfmetrics.stringWidth(s, "HEAD", 12) + 10
    c.setFillColor(INK)
    c.rect(x, y, w, 17, stroke=0, fill=1)
    text(c, x + 5, y + 4.5, s, 12, "HEAD", HAZ)
    LAB.block(x, y, x + w, y + 17, s)
    return w


def axis_marks(c, a, face, fs=8.5):
    """Column numbers and row letters around a card drawing (the underside has no print to read)."""
    for n in (1, 5, 10, 15, 20, 25, 30):
        x, y = a.A(f"J{n}" if face == "under" else f"A{n}")
        yy = a.y - 9 if True else 0
        text(c, x, a.y - 8, str(n), fs, "ALT", GREY, "c")
    for L in "ABCDEFGHIJ":
        x, y = a.A(f"{L}1")
        text(c, a.x - 6, y - 3, L, fs, "ALT", GREY, "r")
    LAB.block(a.x - 14, a.y - 11, a.x + a.w, a.y - 1, "axis numbers")


def _ov(a, b, pad=1.0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


def _seg_hits(r, x0, y0, x1, y1):
    for k in range(1, 20):
        t = k / 20
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        if r[0] < x < r[2] and r[1] < y < r[3]:
            return True
    return False


def place_chips(c, ends, a, size=9, color=NEON, gap=12):
    """Endpoint chips go OUTSIDE the card: one lane above it (ends in the upper half) and one below the column
    numbers (lower half). Chips keep the left-to-right order of their holes and are packed without overlap;
    each leader leaves the chip's inner edge at its centre (white halo, black line), so leaders never cross."""
    ys = [a.A(k)[1] for k in ("fl", "fr", "bl", "br")]
    top, bot, mid = max(ys), min(ys), (max(ys) + min(ys)) / 2
    asc = size * 0.72
    for k in ("up", "dn"):
        items = sorted((px, py, s_) for s_, (px, py) in ends if (py > mid) == (k == "up"))
        if not items:
            continue
        wd = [pdfmetrics.stringWidth(s_, "ALT", size) + 5.2 for _, _, s_ in items]
        ideal = [px - w_ / 2 for (px, _, _), w_ in zip(items, wd)]
        xs = ideal[:]
        for _ in range(30):                       # pack, then pull each cluster back toward its holes
            for n in range(1, len(xs)):
                xs[n] = max(xs[n], xs[n - 1] + wd[n - 1] + gap)
            n = 0
            while n < len(xs):
                m = n
                while m + 1 < len(xs) and abs(xs[m + 1] - (xs[m] + wd[m] + gap)) < 1e-6:
                    m += 1
                d = sum(xs[q] - ideal[q] for q in range(n, m + 1)) / (m - n + 1)
                for q in range(n, m + 1):
                    xs[q] -= d * 0.5
                n = m + 1
        yb = (top + 12) if k == "up" else (a.y - 28)
        shift = 0.0
        for x0, w_ in zip(xs, wd):                # keep clear of the face tag and other blocks
            for q in LAB.blocks:
                if q[0] < x0 + w_ + shift and x0 + shift < q[2] and q[1] < yb + asc + 2.6 and yb - 2.6 < q[3]:
                    shift = max(shift, q[2] + 3 - x0)
        for (px, py, s_), x0, w_ in zip(items, xs, wd):
            r = chip(c, x0 + shift + w_ / 2, yb, s_, size, "ALT", color, "c")
            sx, sy = (r[0] + r[2]) / 2, (r[1] if k == "up" else r[3])
            ty = py + (4.6 if k == "up" else -4.6)
            c.setStrokeColor(WHITE)
            lw(c, 2.6)
            c.line(sx, sy, px, ty)
            c.setStrokeColor(INK)
            lw(c, 1.0)
            c.line(sx, sy, px, ty)
            LAB.leaders.append((sx, sy, px, ty, len(LAB.chips) - 1))

# ------------------------------------------------------------------ pages
def cover(c, pg):
    page(c, "00", "SESSION 2: B4 POWER", "ONE CARD. FOUR PARTS. 13 WIRES UNDER, 2 JUMPERS, 3 LEADS. NO POWER TODAY.", pg,
         SLOGANS2[0])
    g = Grid(2, 3, heights=[1.35, 1.0, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS FOR B4 POWER. ALL OF THEM ARE WITH YOU AT THE OFFICE. LAY THEM OUT BEFORE YOU HEAT THE IRON.")
    items = [("B4 POWER CARD\n(rails snapped, Session 1)", "p_card"),
             ("XH4 RIGHT-ANGLE HEADER\n1x30, every pin fitted", "p_header"),
             ("U7 S7V8F3 3.3 V\nPololu #2122", "p_reg"),
             ("U2 INA228\nAdafruit #5832", "p_ina"),
             ("U6 MAX17048\nAdafruit #5580", "p_max"),
             ("BARE TINNED WIRE\n2 jumpers, 15 mm each", "p_jumper"),
             ("24 AWG SOLID, INSULATED\nred, black, yellow, blue", "p_wires"),
             ("24 AWG STRANDED, red + white\nheat-shrink bands", "p_leads")]
    cw, rh = w / 4, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 4, i // 4
        X, Y = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X + 6, Y + 30, cw - 12, rh - 36)
        chip(c, X + cw / 2, Y + 18, name, 9, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (24 AWG)", "MULTIMETER (CONTINUITY)",
             "PLIERS (PULL 3 U2 PINS)", "SOLDER WICK OR SUCKER (U2's X1)", "STEEL RULER (WIRE LENGTHS)", "SHARPIE", "HEAT GUN OR LIGHTER (HEAT-SHRINK)"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 11, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  KNOW THE TWO FACES", "02  13 WIRES ON THE UNDERSIDE", "03  TWO BARE JUMPERS",
             "04  BUS HEADER, ROW J", "05  REGULATOR U7", "06  INA228 U2: X1 OFF, SJ1", "07  MAX17048 U6", "08  THREE LEADS",
             "09  METER BEFORE POWER"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 16 - i * (h - 10) / len(steps), s, 13, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["EVERY HOLE IS NAMED AS PRINTED: LETTER = ROW (A-J), NUMBER = COLUMN (1-30). E10 = ROW E, COLUMN 10.",
             "TOP = THE FACE WHERE \"DigiKey\" READS. A ROW TOWARD YOU. COLUMNS 1 TO 30 LEFT TO RIGHT.",
             "BATTERY LINES ONLY IN STRIPS 19-23 (HEADER PINS 19-23), JUMPERS JMP1-JMP2 AND LEADS L1-L3.",
             "NO POWER IN THIS SESSION. THE METER IS THE ONLY JUDGE."]
    for i, s in enumerate(rules):
        yy = y + h - 10 - i * (h - 6) / 4
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 9.5, "ALT", INK)


def know(c, pg):
    page(c, "01", "KNOW THE TWO FACES", "B4 POWER HAS A TOP AND AN UNDERSIDE. EVERY INSTRUCTION NAMES ONE.", pg,
         SLOGANS2[1])
    g = Grid(1, 3, heights=[1.1, 1.1, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "TOP FACE: \"DigiKey\" and \"SolderFul BreadBoard\" read correctly, row A toward you, columns 1 to 30 left to",
        "right. Rows are LETTERS (A-J), columns are NUMBERS (1-30). Example: E10 is row E, column 10 (ringed)."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "b4_top", x + 96, y + 24, 330, h - 28, align="l", valign="t")
    _, py = a.A("E10")              # chip below the card's front edge: labels never sit on holes
    ring_label(c, a, "e10", "E10 = ROW E, COLUMN 10", dx=0, dy=a.A("fl")[1] - 16 - py, size=10)
    r = chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "ROW A\n(toward you)", 9, "ALT", INK)
    leader(c, r, a.A("A30")[0] + 3, a.A("A30")[1], INK, dot=False)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "ROW J\n(header row)", 9, "ALT", INK)
    chip(c, x + 8, y + 20, "FRONT EDGE\n= A SIDE", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "UNDERSIDE: turn the card over toward you, over its FRONT edge. Now row J is toward you, row A away, and",
        "columns STILL run 1 to 30 left to right. No print here: count from the left end. E10 is ringed again."])
    face_tag(c, x + 4, y + h - 40, "under")
    a = Art(c, "b4_under", x + 96, y + 14, 330, h - 40, align="l", valign="b")
    axis_marks(c, a, "under")
    _, py = a.A("E10")              # chip above the card's front edge (the front is away in this view)
    ring_label(c, a, "e10", "E10", dx=0, dy=a.A("fl")[1] + 10 - py, size=10)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "ROW J\n(toward you)", 9, "ALT", INK)
    chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "ROW A\n(away from you)", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 2), 3, ["The build sheet (B4.md) writes holes in lower case: e10. It is the same hole: E10.",
                                            "Rails: F+1 = the + RAIL at column 1 (outer front rail). F-2 = the − RAIL at column 2."])
    rows = [("B4.md", "THIS SHEET", "ON THE BOARD"), ("e10", "E10", "row E, column 10"),
            ("i12", "I12", "row I, column 12"), ("F+1", "+ RAIL 1", "outer front rail, column 1"),
            ("F-20", "− RAIL 20", "inner front rail, column 20")]
    for i, (a_, b_, c_) in enumerate(rows):
        yy = y + h - 16 - i * 17
        f = "HEAD" if i == 0 else "ALT"
        text(c, x + 50, yy, a_, 11, f, GREY if i else INK)
        text(c, x + 130, yy, b_, 11, f, NEON if i else INK)
        text(c, x + 230, yy, c_, 11, f, INK)


def wires_page(c, pg, part, gids):
    page(c, "02", f"13 WIRES ON THE UNDERSIDE  {part}/2",
         "24 AWG SOLID INSULATED. B4 POWER UNDERSIDE. THEY GO FIRST: PARTS COVER THESE HOLES LATER.", pg, SLOGANS2[2])
    g = Grid(1, 2)
    for k, gi in enumerate(gids):
        nums, title = GROUPS[gi]
        cap = ([f"B4 POWER, UNDERSIDE (row J toward you). {title}. Grey = wires already in.",
                "Cut each wire to the length shown, strip 3 mm at both ends, lay it flat along the drawn route with"
                ,"right-angle bends. Push each end through its hole from the UNDERSIDE, solder it on the TOP, trim."]
               if k == 0 else
               [f"B4 POWER, UNDERSIDE (row J toward you). {title}. Grey = wires already in.",
                "Same method: cut, strip 3 mm, route flat with right-angle bends, ends through from the underside,",
                "solder on the top, trim. Colours as B4.md: red 3.3 V, black ground, yellow SCL, blue SDA."])
        x, y, w, h = panel(c, g.cell(0, k), gi + 1 if False else None, cap)
        face_tag(c, x + 4, y + h - 20, "under")
        a = Art(c, f"u{gi + 1}", x + 14, y + 40, 330, h - 72, align="l", valign="b")
        axis_marks(c, a, "under")
        tx = a.x + a.w + 10
        text(c, tx, y + h - 14, "#   FROM       TO", 9, "MONO", GREY)
        for j, n in enumerate(nums):
            _, fa, fb, cut, bends, line, col = UNDER[n - 1]
            yy = y + h - 34 - j * 46
            c.setFillColor(WIRE[col])
            c.rect(tx, yy - 26, 6, 34, stroke=0, fill=1)
            text(c, tx + 12, yy, f"{n}  {hole(fa)}  TO  {hole(fb)}", 12, "HEAD", INK)
            text(c, tx + 12, yy - 12, f"{cut} MM CUT, " + ("STRAIGHT" if bends == 0 else f"{bends} BEND" + ("S" if bends > 1 else "")), 9, "ALT", INK)
            text(c, tx + 12, yy - 23, f"{col} · {line}", 9, "ALT", WIRE[col] if col != "YELLOW" else INK)
            LAB.block(tx, yy - 27, x + w, yy + 10, f"row {n}")
            for hname, dy in ((fa, 1), (fb, 1)):
                pass
        for n in nums:
            _, fa, fb, *_ = UNDER[n - 1]
            for hname in (fa, fb):
                px, py = a.A(anchor_name(hname))
                ring(c, px, py)
        # number badges at each wire's ends
        ends = [(hole(h_), a.A(anchor_name(h_))) for n in nums for h_ in UNDER[n - 1][1:3]]
        place_chips(c, ends, a)


def reg(c, pg):
    page(c, "05", "REGULATOR U7: S7V8F3", "POLOLU #2122. FOUR PINS IN F24-F27. ITS BOARD LIES TOWARD ROW A.", pg,
         SLOGANS2[0])
    g = Grid(1, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B4 POWER, TOP FACE. U7 stands on its 4-pin header: pins in F24, F25, F26, F27 (row F, columns 24-27),",
        "its board reaching toward row A. Read the pin labels on U7 itself: VOUT must land in F24 and SHDN in F27.",
        "Solder on the UNDERSIDE. SHDN (F27) connects to nothing else."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_reg", x + 96, y + 4, 330, h - 8, align="l")
    for hname, s, dx in (("f24", "F24 VOUT", -30), ("f25", "F25 GND", -6), ("f26", "F26 VIN", 18), ("f27", "F27 SHDN", 44)):
        px, py = a.A(anchor_name(hname))
        ring(c, px, py)
    tx = a.x + a.w + 10
    for i, s in enumerate(["F24  VOUT  3.3 V out", "F25  GND", "F26  VIN  SYS (pin 26)", "F27  SHDN  not connected"]):
        text(c, tx, y + h - 40 - i * 16, s, 10, "ALT", INK)
    LAB.block(tx, y + h - 40 - 3 * 16 - 4, x + w, y + h - 30, "pin table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Close-up. U7's pins sit in the same columns as wires 4 and 7 underneath: H24 (3.3 V) and H25 (ground)",
        "are in U7's strips, as are J24 and J25. F26 (VIN) shares its strip with J26, header pin 26: SYS."])
    Art(c, "t_reg_iso", x + 40, y + 4, 300, h - 8)


def ina(c, pg):
    page(c, "06", "INA228 U2: X1 OFF, 3 PINS OUT, SJ1 CLOSED", "ADAFRUIT #5832. BATTERY MONITOR. ALL THREE JOBS BEFORE IT GOES ON THE CARD.",
         pg, SLOGANS2[6])
    g = Grid(2, 2, heights=[1, 1.15])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Desolder the GREEN TERMINAL BLOCK X1 (it hits", "B2's header tails above B4); wick its 3 holes",
        "open. Then pull header pins 5, 6, 7 (VBUS,", "VIN−, VIN+) out of U2's 8-pin header."])
    a = Art(c, "p_ina", x + 4, y + 4, w / 2 - 8, h - 8)
    b = Art(c, "p_ina_pulled", x + w / 2 + 4, y + 4, w / 2 - 8, h - 8)
    for k in (5, 6, 7):
        ring(c, *a.A(f"pin{k}"), r=3.6)
    chip(c, a.x + a.w / 2, y + 6, "AS SUPPLIED", 9, "ALT", INK, "c")
    chip(c, b.x + b.w / 2, y + 6, "X1 OFF, PINS 5-7 OUT", 9, "ALT", NEON, "c")
    label(c, a.x + 6, a.y + a.h + 4, "X1: OFF", *a.A("x1"), 9, "ALT", NEON, lcolor=INK)
    arrow(c, a.x + a.w - 4, a.y + a.h / 2, b.x + 6, b.y + b.h / 2, NEON, 2)
    x, y, w, h = panel(c, g.cell(1, 0), 2, [
        "U2's BACK (the face the pins come out of),", "far edge: bridge SJ1's two pads with solder.",
        "Meter X1 VBUS to X1 VIN+: BEEP."])
    a = Art(c, "p_sj1_board", x + 6, y + 30, w * 0.52, h - 60, valign="c")
    ring(c, *a.A("SJ1"), r=7.0)
    chip(c, a.x + a.w / 2, y + 16, "BACK OF U2, HEADER AWAY", 9, "ALT", INK, "c")
    zx = x + w * 0.56
    zh = (h - 58) / 2
    o = Art(c, "p_sj1_open", zx, y + 30 + zh + 8, w - (zx - x) - 8, zh - 14, valign="t")
    k = Art(c, "p_sj1_closed", zx, y + 24, w - (zx - x) - 8, zh - 14, valign="t")
    chip(c, o.x + o.w / 2, o.y - 8, "AS SHIPPED: OPEN", 9, "ALT", INK, "c")
    chip(c, k.x + k.w / 2, k.y - 8, "SOLDERED: CLOSED", 9, "ALT", NEON, "c")
    label(c, o.x + o.w * 0.2, o.y + o.h + 8, "X1 VBUS", *o.A("X1_VBUS"), 9, "ALT", INK, "c", dot=False)
    label(c, o.x + o.w * 0.8, o.y + o.h + 8, "X1 VIN+", *o.A("X1_VINP"), 9, "ALT", INK, "c", dot=False)
    sx, sy = a.A("SJ1")
    arrow(c, sx + 9, sy + 3, zx - 3, o.y + o.h * 0.3, NEON, 1.6)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "B4 POWER, TOP FACE. U2's header in row E: E10, E9, E8, E7, then a gap (E4, E5, E6 empty), then E3. Its board",
        "reaches toward row A, over the front rails. Solder on the UNDERSIDE. X1 VIN+ and VIN− take leads L2 and L1 in",
        "step 08. The middle X1 hole (VBUS) gets no lead: SJ1 joins it to VIN+. Check the pins against U2's own labels."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_ina", x + 70, y + 4, 330, h - 8, align="l")
    for hname in ("e10", "e9", "e8", "e7", "e3"):
        ring(c, *a.A(anchor_name(hname)))
    chip(c, a.A("E10")[0] + 8, a.A("E10")[1] + 12, "E10", 9, "ALT", NEON)
    chip(c, a.A("E3")[0] - 10, a.A("E3")[1] + 12, "E3", 9, "ALT", NEON, "r")
    for kk in ("U2:X1.VIN+", "U2:X1.VIN-"):
        ring(c, *a.A(kk), r=5.0)
    vp, vb, vm = a.A("U2:X1.VIN+"), a.A("U2:X1.VBUS"), a.A("U2:X1.VIN-")
    label(c, vp[0] - 14, vp[1] - 44, "X1 VIN+ (LEAD L2)", *vp, 9, "ALT", INK, "r", dot=False)
    label(c, vb[0], vb[1] - 62, "X1 VBUS: NO LEAD (SJ1)", *vb, 9, "ALT", INK, "c", dot=False)
    label(c, vm[0] + 14, vm[1] - 44, "X1 VIN− (LEAD L1)", *vm, 9, "ALT", INK, dot=False)
    tx = a.x + a.w + 10
    rows = [("E10", "VIN", "3.3 V"), ("E9", "GND", "ground"), ("E8", "SCL", "I2C clock"), ("E7", "SDA", "I2C data"),
            ("E4-6", "-", "empty"), ("E3", "ALRT", "not connected")]
    for i, (hh, nm, ln) in enumerate(rows):
        yy = y + h - 30 - i * 26
        text(c, tx, yy, hh, 12, "HEAD", NEON)
        text(c, tx + 36, yy, nm, 12, "HEAD", INK)
        text(c, tx, yy - 10, ln, 8.5, "ALT", GREY)
    LAB.block(tx, y + h - 30 - 5 * 26 - 14, x + w, y + h - 18, "pin table")


def maxg(c, pg):
    page(c, "07", "MAX17048 U6", "ADAFRUIT #5580. FUEL GAUGE. SIX PINS IN E15-E20.", pg, SLOGANS2[1])
    g = Grid(2, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "B4 POWER, TOP FACE. U6 stands on its 6-pin header in row E: E20 VIN, E19 GND, E18 SCL, E17 SDA, E16 INT,",
        "E15 QST. Its board reaches toward row A, beside U2. Check against U6's own labels. Solder on the UNDERSIDE.",
        "INT (E16) and QST (E15) connect to nothing else. The JP2 VBAT pad takes lead L3 in step 08."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_max", x + 96, y + 4, 330, h - 8, align="l")
    for hname in ("e20", "e19", "e18", "e17", "e16", "e15"):
        ring(c, *a.A(anchor_name(hname)))
    chip(c, a.A("E20")[0] + 8, a.A("E20")[1] + 12, "E20", 9, "ALT", NEON)
    chip(c, a.A("E15")[0] - 8, a.A("E15")[1] + 12, "E15", 9, "ALT", NEON, "r")
    vb = a.A("U6:JP2.VBAT")
    label(c, vb[0] + 12, a.A("A1")[1] - 58, "JP2 VBAT PAD (LEAD L3, STEP 08)", *vb, 9, "ALT", INK, dot=False)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Pin by pin. Every hole as printed."])
    rows = [("E20", "VIN", "3.3 V"), ("E19", "GND", "ground"), ("E18", "SCL", "I2C clock"), ("E17", "SDA", "I2C data"),
            ("E16", "INT", "not connected"), ("E15", "QST", "not connected")]
    for i, (hh, nm, ln) in enumerate(rows):
        yy = y + h - 22 - i * 24
        text(c, x + 50, yy, hh, 15, "HEAD", NEON)
        text(c, x + 110, yy, nm, 15, "HEAD", INK)
        text(c, x + 174, yy, ln, 10, "ALT", GREY)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["U6 alone, header down."])
    Art(c, "p_max", x + 4, y + 4, w - 8, h - 8)


def jumpers(c, pg):
    page(c, "03", "TWO BARE JUMPERS ON TOP", "TINNED BARE WIRE. B4 POWER TOP FACE. THE BATTERY CURRENT RUNS IN THESE.", pg,
         SLOGANS2[4])
    g = Grid(1, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B4 POWER, TOP FACE. JMP1: I19 to I20. JMP2: I21 to I22. Each joins two neighbouring strips that",
        "carry the same battery line (19-20 charger battery +, 21-22 battery + junction). Cut 15 mm of bare tinned",
        "wire, bend a U, legs down through the two holes from the TOP, bridge 1 mm above the card, solder underneath."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_jumpers", x + 60, y + 4, 330, h - 8, align="l")
    for hname in ("i19", "i20", "i21", "i22"):
        ring(c, *a.A(anchor_name(hname)))
    tx = x + w - 150
    rows = [("JMP1", "I19 TO I20", "charger battery +"), ("JMP2", "I21 TO I22", "battery + junction")]
    for i, (n, hh, ln) in enumerate(rows):
        yy = y + h - 60 - i * 40
        text(c, tx, yy, f"{n}  {hh}", 12, "HEAD", INK)
        text(c, tx, yy - 13, "15 MM BARE, TINNED", 9, "ALT", GREY)
        text(c, tx, yy - 24, ln.upper(), 9, "ALT", GREY)
    LAB.block(tx, y + h - 60 - 40 - 28, x + w, y + h - 46, "jumper table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Close-up, from the front-left. The two U-shaped bridges sit on the top, between row I's holes. Nothing else",
        "goes in I19-I22. These strips also hold header pins J19-J22 (next step): the pairs are joined on the card too."])
    a = Art(c, "t_jumpers_iso", x + 40, y + 4, 300, h - 8)
    for k, t in (("J1m", "JMP1: I19 TO I20"), ("J2m", "JMP2: I21 TO I22")):
        px, py = a.A(k)
        label(c, px - 40, a.y + a.h + 4, t, px, py, 9, "ALT", INK)


def header(c, pg):
    page(c, "04", "BUS HEADER XH4, ROW J", "GENERIC RIGHT-ANGLE MALE HEADER, CUT TO 1x30. ALL 30 PINS STAY IN.", pg,
         SLOGANS2[3])
    g = Grid(1, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B4 POWER, TOP FACE. Short legs down through J1 to J30 (row J, columns 1-30), from the top: every hole in row J",
        "takes a pin. The long pins point AWAY from row A, out past the snapped back edge. Solder on the UNDERSIDE:",
        "J1 first, check it sits flat and square, then J30, then the rest."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_header", x + 96, y + 4, 330, h - 8, align="l")
    for hname in ("j1", "j30"):
        ring(c, *a.A(anchor_name(hname)))
    j1, j30 = a.A("J1"), a.A("J30")
    label(c, a.x - 4, j1[1] + 30, "J1: PIN 1", *j1, 9, "ALT", INK, "r")
    label(c, j30[0] + 6, a.y + a.h + 8, "J30: PIN 30", *j30, 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Cut 1x30 from a longer strip: pull the 31st pin, cut through its empty place, file flat. Pins 1-18: 3.3 V,",
        "ground, I2C and sensor lines. 19-20 charger battery +, 21-22 battery + junction, 23 gauge sense, 24 3.3 V and",
        "25 ground (from U7's strips), 26 SYS, 27-30 spare. They plug into B4's backplane socket (line n = pin n)."])
    hd = Art(c, "p_header", x + 20, y + 10, 300, h - 20, align="l")
    for k in ("p1", "p30"):
        ring(c, *hd.A(k), r=4.0)
    label(c, hd.x + hd.w + 12, hd.y + hd.h / 2, "1x30: PIN 1 TO PIN 30,\nNONE PULLED", *hd.A("p30"), 10, "ALT", INK)


def leads(c, pg):
    page(c, "08", "THREE LEADS ON THE TOP", "24 AWG STRANDED. EACH FROM ITS ROW-G HOLE TO A BREAKOUT PAD. NOTHING LEAVES THE CARD.",
         pg, SLOGANS2[4])
    g = Grid(1, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B4 POWER, TOP FACE. Each lead starts in a row-G hole (strip end soldered underneath), lies flat on the top",
        "along its drawn route, climbs up the edge of its breakout and is soldered into the pad. Slide a heat-shrink",
        "band onto each end before soldering: black on the red leads, red on the white lead."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_leads", x + 96, y + 4, 330, h - 8, align="l")
    for hname in ("g20", "g21", "g23"):
        ring(c, *a.A(anchor_name(hname)))
    for k in ("U2:X1.VIN-", "U2:X1.VIN+", "U6:JP2.VBAT"):
        ring(c, *a.A(k), r=4.6)
    band = (a.A("F20")[1] + a.A("E20")[1]) / 2 - 4
    for n, hn, dx in (("L1", "G20", -34), ("L2", "G21", -12), ("L3", "G23", 6)):
        hx, hy = a.A(hn)
        label(c, hx + dx, band, n, hx, hy, 9, "HEAD", INK, "c", dot=False)
    vp, vm, vb = a.A("U2:X1.VIN+"), a.A("U2:X1.VIN-"), a.A("U6:JP2.VBAT")
    bot = a.A("A1")[1] - 58
    label(c, vp[0] - 12, bot, "L2 END: X1 VIN+", *vp, 9, "ALT", INK, "r", dot=False)
    label(c, vm[0] + 12, bot - 16, "L1 END: X1 VIN−", *vm, 9, "ALT", INK, dot=False)
    label(c, vb[0] + 12, bot, "L3 END: U6 JP2 VBAT", *vb, 9, "ALT", INK, dot=False)
    tx = a.x + a.w + 12
    for i, t in enumerate(("L1 STARTS IN G20", "L2 STARTS IN G21", "L3 STARTS IN G23")):
        text(c, tx, a.y + a.h - 30 - i * 16, t, 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The three leads (B4.md section 5). Cut to the length shown. Strip 3 mm at the G end (through the hole) and",
        "2 mm at the pad end. U2's middle X1 hole (VBUS) gets no lead: SJ1 (step 06) joins it to VIN+."])
    rows = [("L1", "G20", "U2 X1 VIN− (shunt out)", "80 MM", "charger battery +", "RED, BLACK BANDS"),
            ("L2", "G21", "U2 X1 VIN+ (shunt in)", "95 MM", "battery + junction", "RED, BLACK BANDS"),
            ("L3", "G23", "U6 JP2 VBAT (cell sense)", "70 MM", "gauge sense from R8", "WHITE, RED BANDS")]
    text(c, x + 44, y + h - 14, "LEAD  FROM  TO                         CUT    LINE                COLOUR", 8.5, "MONO", GREY)
    for i, (n, fa, fb, ln, line, col) in enumerate(rows):
        yy = y + h - 46 - i * 30
        body, band = (RED, INK) if col.startswith("RED") else (HexColor("#E8E8E8"), RED)
        c.setFillColor(body)
        c.rect(x + 10, yy - 4, 26, 12, stroke=0, fill=1)
        c.setFillColor(band)
        c.rect(x + 12, yy - 4, 5, 12, stroke=0, fill=1)
        c.rect(x + 29, yy - 4, 5, 12, stroke=0, fill=1)
        text(c, x + 44, yy, n, 13, "HEAD", INK)
        text(c, x + 74, yy, fa, 12, "HEAD", NEON)
        text(c, x + 110, yy, fb, 10, "ALT", INK)
        text(c, x + 250, yy, ln, 10, "ALT", INK)
        text(c, x + 300, yy, line, 9, "ALT", GREY)
        text(c, x + 400, yy, col, 9, "ALT", INK)
    LAB.block(x + 10, y + h - 46 - 2 * 30 - 8, x + w, y + h - 6, "lead table")
    Art(c, "p_leads", x + 60, y + 36, w - 120, y + h - 46 - 2 * 30 - 20 - (y + 36))
    text(c, x + 60, y + 28, "TOP: L1 OR L2 (RED, BLACK BANDS). BOTTOM: L3 (WHITE, RED BANDS). BANDED BEFORE SOLDERING. NOT TO SCALE.", 8.5, "ALT", GREY)


def checks(c, pg):
    page(c, "09", "METER BEFORE POWER", "CONTINUITY MODE. B4 POWER ALONE ON THE BENCH. NOTHING PLUGGED IN.", pg,
         SLOGANS2[5])
    g = Grid(2, 2, heights=[1.0, 1.1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["B4 POWER, finished, seen from above. Do the checks below in order."])
    a = Art(c, "t_final", x + 4, y + 4, w - 8, h - 8)
    label(c, x + w - 12, y + 34, "L3, WHITE: SOLDERED ON U6's JP2 VBAT PAD,\nBEHIND THE WHITE SOCKETS (NOT PLUGGED IN)",
          *a.A("L3riser"), 9, "ALT", INK, "r")
    label(c, x + 12, y + 30, "U2: NO GREEN X1 BLOCK (OFF IN STEP 06)", *a.A("X1spot+2"), 9, "ALT", NEON, lcolor=INK)
    checks = [("1", "NEIGHBOURS", "Each used strip (B4.md strip map) against the strips beside it: NO BEEP.\nExpected BEEPS: 19-20 and 21-22 (jumpers), 20-21 (through U2's shunt)."),
              ("2", "3.3 V vs GROUND", "+ RAIL against − RAIL: NO steady BEEP.\nA short chirp as the capacitors charge is fine."),
              ("3", "HEADER PINS", "Each pin Jn beeps to F n (same column, its own strip) and to NO other\nheader pin, except the three groups in check 4."),
              ("4", "PIN GROUPS", "J1 and J24 beep (3.3 V). J2, J12 and J25 beep (ground).\nJ19, J20, J21 and J22 all beep to each other."),
              ("5", "SJ1 + LEAD ENDS", "X1 VBUS to X1 VIN+: BEEP (SJ1). X1 VIN− to G20, X1 VIN+ to G21,\nJP2 VBAT to G23: BEEP."),
              ("6", "ALL 30 PINS", "J1-J30 all fitted, none pulled. Spares J27-J30 beep to no other\nheader pin (J27's strip also holds U7 SHDN, unused).")]
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Any beep where it says NO BEEP, or silence where it says BEEP: stop. Photograph it. Report to Claude."],
                       warn=True)
    for i, (n, t, s) in enumerate(checks):
        yy = y + h - 46 - i * (h - 52) / 6
        badge(c, x + 52, yy + 4, n, 10)
        text(c, x + 70, yy, t, 13, "HEAD", INK)
        for k, ln in enumerate(s.split("\n")):
            text(c, x + 200, yy + 1 - 12 * k, ln, 9.5, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 26, yy - 4, 14, 14, stroke=1, fill=0)


def built_page(c, pg):
    import builtpage
    builtpage.built(c, pg, SL, "00", SLOGANS2[0])


PAGES = [("00-cover", [cover]), ("00-what-you-are-building", [built_page]), ("01-know-the-faces", [know]),
         ("02-underside-wires", [lambda c, pg: wires_page(c, pg, 1, [0, 1]), lambda c, pg: wires_page(c, pg, 2, [2, 3])]),
         ("03-jumpers", [jumpers]), ("04-bus-header", [header]), ("05-regulator", [reg]), ("06-ina228", [ina]),
         ("07-max17048", [maxg]), ("08-leads", [leads]), ("09-meter-checks", [checks])]


HOLE_ISSUES = []


def build(path, fns, start=1, report=False):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 2: build B4 POWER")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(cv, start + i)
        if report:
            issues += len(LAB.check())
            hi = SL.HC.check(start + i)
            for m in hi:
                print("  HOLE", m)
            HOLE_ISSUES.extend(hi)
        SL.HC.reset()
        cv.showPage()
    cv.save()
    return issues


OUT.mkdir(parents=True, exist_ok=True)
allfns, n = [], 1
for name, fns in PAGES:
    build(OUT / f"session2-{name}.pdf", fns, n)
    allfns += fns
    n += len(fns)
bad = build(OUT / "session2-all.pdf", allfns, 1, report=True)
print("ok", n - 1, "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
if HOLE_ISSUES:
    sys.exit("BUILD FAILED: hole callouts off their holes")
