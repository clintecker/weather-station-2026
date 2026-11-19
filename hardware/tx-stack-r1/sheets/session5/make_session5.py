"""Session 5: build B3 CORE. Same flat-pack style and pipeline as Session 2 (B4 POWER).

Source of truth: hardware/tx-stack-r1/build/B3.md, parsed by b3md.py (every wire, part pin, strip and before-power
check on these pages comes from it); geometry from layout/stack.py + layout/route.py via scenes5.py.
Hole names: the board prints COLUMNS as letters (A-J) and ROWS as numbers (1-30). B3.md writes holes as
letter + number ('e10'); here that is shown as printed: E10 = column E, row 10.

Usage: pdfenv/bin/python make_session5.py [OUT_DIR]     (default: ../out; writes session5-all.pdf)
"""
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sheetlib import *          # noqa: F401,F403,E402  (page furniture, chips, leaders, Art, checks)
import sheetlib as SL           # noqa: E402
import b3md                     # noqa: E402

SL.LEADER_INK = True        # every leader black on a white halo: never red or magenta lines on the red card

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
RED = HexColor("#D7262E")
WIRE = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
        "blue": HexColor("#2D6FD0"), "green": HexColor("#2E9E48")}

SLOGANS5 = [
    "B3 CORE THINKS FOR THE OTHERS. IT IS BUILT LAST.",
    "TOP IS THE FACE THAT READS. THE MACHINE CHECKED.",
    "A WIRE UNDER A PART CANNOT BE FIXED LATER.",
    "TWENTY-NINE PINS. ONE KEY. ONE SLOT.",
    "THE RADIO LISTENS. THE SOLDER DOES NOT TALK BACK.",
    "METER FIRST. POWER NEVER. NOT TODAY.",
    "TWENTY-ONE WIRES. ONE AT A TIME. COUNT THEM.",
]

WIRES = b3md.WIRES
WBY = {w["n"]: w for w in WIRES}
GROUPS = [([1, 2, 3], "BUS 3.3 V AND BOTH BUS GROUNDS TO THE FRONT RAILS"),     # == scenes5.GROUPS
          ([5, 6, 10, 12], "THE SHTC3'S POWER, CLOCK AND DATA"),
          ([4, 7, 8], "THE MINI'S 3.3 V AND ITS TWO GROUNDS"),
          ([9, 11, 13], "THE MINI'S I2C CLOCK AND DATA, AND THE MUX RESET"),
          ([14, 15, 16], "CUPS, VANE AND RAIN TO THE MINI"),
          ([17, 21], "SWD 3.3 V AND SWD GROUND"),
          ([18, 19, 20], "SWD DATA, CLOCK AND RESET")]
assert sorted(n for g, _ in GROUPS for n in g) == list(range(1, 22))
PARTS = b3md.PARTS
KEY, COLOUR = b3md.KEY, b3md.COLOUR               # 29, yellow: B3.md section 1 step 4 and XH3's key row
KEY_HOLE = b3md.KEY_HOLE                          # j29
import re as _re
SWD_TIP = _re.search(r"they end at card Y ([\d.]+), \1 mm short of the edge", PARTS["J3"][0]).group(1)   # 1.57
DOT_RGB = {"blue": "#2D6FD0", "green": "#2E9E4F", "yellow": "#FFD400", "red": "#E8202A"}[COLOUR]   # == models.KEY_RGB



def _rail_list(rail):
    """The rail holes B3's wires really end in (B3.md, after routing), as '1, 7, 8 and 21'."""
    cols = sorted({int(h[2:]) for w in b3md.WIRES for h in (w["a"], w["b"]) if h.startswith(rail)})
    return ", ".join(map(str, cols[:-1])) + " and " + str(cols[-1]) if len(cols) > 1 else str(cols[0])

def hole(h):
    """B3.md hole -> as printed on the board."""
    if h.startswith("F+"):
        return f"+ RAIL {h[2:]}"
    if h.startswith("F-"):
        return f"− RAIL {h[2:]}"
    return h[0].upper() + h[1:]


def anchor_name(h):
    return h if h.startswith("F+") or h.startswith("F-") else h[0].upper() + h[1:]


SHORT = {"3.3 V supply": "3V3", "ground": "GND", "I2C clock (SCL)": "SCL", "I2C data (SDA)": "SDA",
         "debug data (SWDIO)": "SWDIO", "debug clock (SWCLK)": "SWCLK", "MCU reset (NRST)": "NRST",
         "mux reset": "MUX RST", "cups (wind speed) pulse": "CUPS", "vane (wind direction) voltage": "VANE",
         "rain gauge pulse": "RAIN", "spare bus line (for the charger interrupt)": "INT",
         "not connected": "NC", "nothing (an unused pin)": "NC"}


def short(line):
    if line in SHORT:
        return SHORT[line]
    import re
    m = re.match(r"sensor port (\d) (data|clock)", line)
    if m:
        return f"S{m.group(1)} {'SDA' if m.group(2) == 'data' else 'SCL'}"
    raise KeyError(line)


def bends_text(b):
    return "STRAIGHT" if b == 0 else f"{b} BEND" + ("S" if b > 1 else "")


def ring(c, x, y, r=4.2, w=1.6):
    """Hole marker that reads on the red card: hazard yellow on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(HAZ)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def ring_label(c, a, h, s=None, dx=0, dy=14, size=9, color=NEON):
    px, py = a.A(anchor_name(h))
    ring(c, px, py)
    r = chip(c, px + dx, py + dy - size * 0.36, s or hole(h), size, "ALT", color, "c")
    leader(c, r, px, py + (4.2 if dy > 0 else -4.2) if abs(dx) < 1 else py, color, dot=False, w=0.8)
    return r


def face_tag(c, x, y, face):
    s = "TOP FACE" if face == "top" else "UNDERSIDE"
    w = pdfmetrics.stringWidth(s, "HEAD", 12) + 10
    c.setFillColor(INK)
    c.rect(x, y, w, 17, stroke=0, fill=1)
    text(c, x + 5, y + 4.5, s, 12, "HEAD", HAZ)
    LAB.block(x, y, x + w, y + 17, s)
    return w


def axis_marks(c, a, face, fs=8.5, nums_y=None):
    """Row numbers and column letters around a card drawing (the underside has no print to read)."""
    for n in (1, 5, 10, 15, 20, 25, 30):
        x, y = a.A(f"J{n}" if face == "under" else f"A{n}")
        text(c, x, (a.y - 8) if nums_y is None else nums_y, str(n), fs, "ALT", GREY, "c")
    lx = min(a.A("fl")[0], a.A("bl")[0]) - 6
    for L in "ABCDEFGHIJ":
        x, y = a.A(f"{L}1")
        text(c, lx, y - 3, L, fs, "ALT", GREY, "r")
    yy = (a.y - 8) if nums_y is None else nums_y
    LAB.block(lx - 8, yy - 3, a.x + a.w, yy + 7, "axis numbers")


def place_chips(c, ends, a, size=9, color=NEON, gap=10, up_y=None, dn_y=None):
    """Endpoint chips go OUTSIDE the card: one lane above it (ends in the upper half) and one below the row
    numbers (lower half). Chips keep the left-to-right order of their holes and are packed without overlap;
    each leader leaves the chip's inner edge at its centre (white halo, black line), so leaders never cross."""
    ys = [a.A(k)[1] for k in ("fl", "fr", "bl", "br")]
    top, bot, mid = max(ys), min(ys), (max(ys) + min(ys)) / 2
    asc = size * 0.72
    for k in ("up", "dn"):
        items = sorted((px, py, s_) for s_, (px, py) in ends if (py > mid) == (k == "up"))
        if not items:
            continue
        wd = [max(pdfmetrics.stringWidth(l, "ALT", size) for l in s_.split("\n")) + 5.2 for _, _, s_ in items]
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
        nl = max(s_.count("\n") for _, _, s_ in items)
        if k == "up":
            yb = (top + 12 + nl * size * 1.12) if up_y is None else up_y
        else:
            yb = (a.y - 28) if dn_y is None else dn_y
        for (px, py, s_), x0, w_ in zip(items, xs, wd):
            r = chip(c, x0 + w_ / 2, yb, s_, size, "ALT", color, "c")
            sx, sy = (r[0] + r[2]) / 2, (r[1] if k == "up" else r[3])
            ty = py + (4.6 if k == "up" else -4.6)
            c.setStrokeColor(WHITE)
            lw(c, 2.6)
            c.line(sx, sy, px, ty)
            c.setStrokeColor(INK)
            lw(c, 1.0)
            c.line(sx, sy, px, ty)
            LAB.leaders.append((sx, sy, px, ty, len(LAB.chips) - 1))


def swatch(c, x, y, col, h=34):
    c.setFillColor(WIRE[col])
    c.rect(x, y, 6, h, stroke=0, fill=1)


# ------------------------------------------------------------------ pages
def cover(c, pg):
    page(c, "00", "SESSION 5: B3 CORE",
         f"ONE CARD. FOUR PARTS. {len(WIRES)} WIRES ON THE UNDERSIDE. NO POWER TODAY.", pg, SLOGANS5[0])
    g = Grid(2, 3, heights=[1.35, 1.0, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS FOR B3 CORE (build/B3.md section 3). LAY THEM OUT BEFORE YOU HEAT THE IRON.")
    items = [("B3 CORE CARD\n(back rails snapped)", "p_card"),
             (f"XH3 RIGHT-ANGLE HEADER\n1x30, pin {KEY} pulled (slot key)", "p_header"),
             ("J3 SWD 1x5 RIGHT-ANGLE\n(bus header stock, cut 1x5)", "p_swd"),
             ("U5 SHTC3\nAdafruit #4636", "p_shtc3"),
             ("A1 WIO-E5 MINI\nSeeed 113990939", "p_mini"),
             ("24 AWG SOLID, INSULATED\nred, black, yellow, blue, green", "p_wires")]
    cw, rh = w / 3, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 3, i // 3
        X, Y = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X + 8, Y + 30, cw - 16, rh - 36)
        chip(c, X + cw / 2, Y + 18, name, 9, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (24 AWG)", "MULTIMETER (CONTINUITY)",
             "STEEL RULER (WIRE LENGTHS)", "FLAT FILE (THE SNAPPED EDGE)", f"PLIERS (PULL XH3 PIN {KEY})",
             f"{COLOUR.upper()} PAINT PEN OR DOT STICKER", "SHARPIE", "THIS SHEET, PRINTED"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 11, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  SNAP THE BACK RAILS (OR CHECK)", "02  KNOW THE TWO FACES", "03  21 WIRES ON THE UNDERSIDE",
             "04  SWD HEADER J3, COLUMN A", f"05  BUS HEADER XH3 (KEY), {COLOUR.upper()} DOT", "06  SHTC3 U5", "07  WIO-E5 MINI A1",
             "08  THE STRIP MAP", "09  METER BEFORE POWER"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 16 - i * (h - 10) / len(steps), s, 13, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["EVERY HOLE IS NAMED AS PRINTED: LETTER = COLUMN (A-J), NUMBER = ROW (1-30). E10 = COLUMN E, ROW 10.",
             "TOP = THE FACE WHERE \"DigiKey\" READS. COLUMN A TOWARD YOU. ROWS 1 TO 30 LEFT TO RIGHT.",
             "ALL 21 UNDERSIDE WIRES GO IN BEFORE ANY PART: THE MINI AND U5 COVER THEIR HOLES.",
             f"XH3: 1x30 WITH PIN {KEY} PULLED (THE SLOT KEY), {KEY_HOLE.upper()} EMPTY. NO POWER IN THIS SESSION."]
    for i, s in enumerate(rules):
        yy = y + h - 10 - i * (h - 6) / 4
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 9.5, "ALT", INK)


def built_page(c, pg):
    import builtpage
    builtpage.built(c, pg, SL, "00", SLOGANS5[0])


def snap(c, pg):
    page(c, "01", "SNAP THE BACK RAILS", "B3 CORE. B3.md SECTION 1. BEFORE ANY SOLDER. ALREADY SNAPPED IN SESSION 1? DO PANEL 5.",
         pg, SLOGANS5[2])
    g = Grid(2, 3, heights=[1.35, 1, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "B3 CORE, TOP FACE. Score both faces along the line between column J and the inner back rail: card Y 41.91 mm",
        "from the FRONT edge (model value, TBD-MEASURE: measure it on the card). Clamp along the line and snap the",
        "two back rails off. If B3 was already snapped in Session 1, skip to panel 5 and check it."])
    a = Art(c, "s3_card", x + 96, y + 2, 290, h - 4, align="l")
    (sl, sly), (sr, sry) = a.A("snapL"), a.A("snapR")
    dashed(c, sl - 10, sly, sr + 10, sry, color=HAZ, w=2.4, halo=INK)
    flx, fly = a.A("fl")
    frx, fry = a.A("fr")
    brx, bry = a.A("br")
    label(c, sr + 22, sry + 16, "SNAP LINE", sr + 10, sry, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    dim(c, sr + 34, fry, sr + 34, sry, "", 12)
    chip(c, sr + 42, sry - 34, "MEASURE", 13, "HEAD", NEON)
    chip(c, sr + 42, sry - 50, "model: 41.91 mm", 9, "MONO", NEON)
    c.setStrokeColor(INK)
    lw(c, 1.4)
    c.line(flx - 8, sly + 2, flx - 8, bry)
    c.line(flx - 8, sly + 2, flx - 4, sly + 2)
    c.line(flx - 8, bry, flx - 4, bry)
    chip(c, flx - 12, (sly + bry) / 2 - 4, "COMES OFF", 9, "ALT", INK, "r")
    label(c, flx - 12, sly - 30, "J-SIDE\nNUMBERS", *a.A("numJ"), 9, anchor="r")
    chip(c, flx - 12, fly + 16, "FRONT EDGE\n(A SIDE)", 9, "ALT", INK, "r")
    c.setStrokeColor(INK)
    lw(c, 3)
    c.line(flx, fly - 3, frx, fry - 3)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Ruler on the keep side of the line.", "Score x10. Flip. Score x10 on the same line."])
    Art(c, "s3_score", x + 32, y + 2, w - 98, h - 4, align="l")
    times(c, x + w - 34, y + h - 40, "x10", 26)
    curved_arrow(c, x + w - 34, y + h - 68, 13, 200, -60)
    times(c, x + w - 34, y + 12, "x10", 26)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Snap line on the table edge, scrap wood on", "top, clamped. Push the rails down. Snap."])
    s = Art(c, "s3_snap", x + 2, y + 2, w - 4, h - 4)
    px, py = s.A("push")
    arrow(c, px, py + 40, px, py + 6, HAZ, 3.5, 12, halo=INK)
    chip(c, px, py + 46, "SNAP", 12, "HEAD", NEON, "c")
    label(c, x + 8, y + 40, "SCRAP WOOD", *s.A("wood"), 9)
    x, y, w, h = panel(c, g.cell(0, 2), 4, ["File the edge flat and square to the front", "edge. STOP at the line: column J holes stay shut."])
    Art(c, "tool_file", x + 40, y + h - 24, 150, 22, align="l")
    ok = Art(c, "s3_edge_ok", x + 8, y + 16, 110, h - 54, frame=True)
    verdict(c, ok.x + ok.w - 2, ok.y + ok.h + 2, True)
    chip(c, ok.x + ok.w / 2, ok.y - 13, "COLUMN J WHOLE", 9, "ALT", INK, "c")
    bad = Art(c, "s3_edge_bad", x + w - 120, y + 16, 110, h - 54, frame=True)
    verdict(c, bad.x + bad.w - 2, bad.y + bad.h + 2, False)
    chip(c, bad.x + bad.w / 2, bad.y - 13, "FILED INTO THE PADS", 9, "ALT", NEON, "c")
    x, y, w, h = panel(c, g.cell(1, 2), 5, ["CHECK: 41.91 mm deep everywhere (or your", "number). Slides in a test slot, no catch."])
    s = Art(c, "s3_check", x + 30, y + 6, 160, h - 12, align="l")
    for nm in ("A", "B"):
        (ax, ay), (bx, by) = s.A(nm + "0"), s.A(nm + "1")
        dim(c, ax, ay, bx, by, nm, 13, INK)
    chip(c, s.x + s.w / 2, s.y + s.h / 2 - 8, "A = B", 18, "HEAD", INK, "c")


def know(c, pg):
    page(c, "02", "KNOW THE TWO FACES", "B3 CORE HAS A TOP AND AN UNDERSIDE. EVERY INSTRUCTION NAMES ONE.", pg,
         SLOGANS5[1])
    g = Grid(1, 3, heights=[1.1, 1.1, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "TOP FACE: \"DigiKey\" and \"SolderFul BreadBoard\" read correctly, column A toward you, rows 1 to 30 left to",
        "right. Columns are LETTERS (A-J), rows are NUMBERS (1-30). Example: E10 is column E, row 10 (ringed)."])
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "b3_top", x + 96, y + 24, 330, h - 28, align="l", valign="t")
    _, py = a.A("E10")
    ring_label(c, a, "e10", "E10 = COLUMN E, ROW 10", dx=0, dy=a.A("fl")[1] - 16 - py, size=10)
    r = chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "COLUMN A\n(toward you)", 9, "ALT", INK)
    leader(c, r, a.A("A30")[0] + 3, a.A("A30")[1], INK, dot=False)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "COLUMN J\n(header column)", 9, "ALT", INK)
    chip(c, x + 8, y + 20, "FRONT EDGE\n= A SIDE", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "UNDERSIDE: turn B3 over toward you, over its FRONT edge. Now column J is toward you, column A away, and",
        "rows STILL run 1 to 30 left to right. No print here: count from the left end. E10 is ringed again."])
    face_tag(c, x + 4, y + h - 40, "under")
    a = Art(c, "b3_under", x + 96, y + 14, 330, h - 40, align="l", valign="b")
    axis_marks(c, a, "under")
    _, py = a.A("E10")
    ring_label(c, a, "e10", "E10", dx=0, dy=a.A("fl")[1] + 10 - py, size=10)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "COLUMN J\n(toward you)", 9, "ALT", INK)
    chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "COLUMN A\n(away from you)", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 2), 3, ["The build sheet (B3.md) writes holes in lower case: e21. It is the same hole: E21.",
                                            "Rails: F+21 = the + RAIL at row 21 (outer front rail). F-17 = the − RAIL at row 17."])
    rows = [("B3.md", "THIS SHEET", "ON THE BOARD"), ("e21", "E21", "column E, row 21"),
            ("i24", "I24", "column I, row 24"), ("F+21", "+ RAIL 21", "outer front rail, row 21: 3.3 V"),
            ("F-17", "− RAIL 17", "inner front rail, row 17: ground")]
    for i, (a_, b_, c_) in enumerate(rows):
        yy = y + h - 16 - i * 17
        f = "HEAD" if i == 0 else "ALT"
        text(c, x + 50, yy, a_, 11, f, GREY if i else INK)
        text(c, x + 130, yy, b_, 11, f, NEON if i else INK)
        text(c, x + 230, yy, c_, 11, f, INK)


def wires_page(c, pg, gi):
    nums, title = GROUPS[gi]
    page(c, "03", f"{len(WIRES)} WIRES ON THE UNDERSIDE  {gi + 1}/{len(GROUPS)}",
         "24 AWG SOLID INSULATED. B3 CORE UNDERSIDE. THEY GO FIRST: PARTS COVER THESE HOLES LATER.", pg, SLOGANS5[6])
    g = Grid(1, 2, heights=[2.1, 1])
    done = sum(len(gg) for gg, _ in GROUPS[:gi])
    x, y, w, h = panel(c, g.cell(0, 0), None, [
        f"B3 CORE, UNDERSIDE (column J toward you). {title}.",
        f"Grey = the {done} wires already in." if done else "First wires: the card is bare.",
        "Each wire lies flat along its drawn route with right-angle bends, around every hole it does not use."])
    face_tag(c, x + 4, y + h - 20, "under")
    a = Art(c, f"u{gi + 1}", x + 30, y + 46, w - 60, h - 46 - 46, align="c", valign="b")
    axis_marks(c, a, "under")
    for n in nums:
        for hname in (WBY[n]["a"], WBY[n]["b"]):
            ring(c, *a.A(anchor_name(hname)))
    ends = [(f"{n}: {hole(h_)}", a.A(anchor_name(h_))) for n in nums for h_ in (WBY[n]["a"], WBY[n]["b"])]
    place_chips(c, ends, a, size=9.5, dn_y=a.y - 30)
    x, y, w, h = panel(c, g.cell(0, 1), None, [
        "Cut to the length shown (route + 10 mm). Strip 3 mm at both ends. Push each end through its hole from the",
        "UNDERSIDE, solder it on the TOP, trim. Colours as B3.md: red 3.3 V, black ground, yellow SCL, blue SDA,",
        "green every other signal."])
    cols = 2
    cw = (w - 12) / cols
    for j, n in enumerate(nums):
        wd = WBY[n]
        tx = x + 10 + (j % cols) * cw
        yy = y + h - 22 - (j // cols) * 62
        swatch(c, tx, yy - 38, wd["colour"], 50)
        text(c, tx + 14, yy, f"{n}   {hole(wd['a'])}  TO  {hole(wd['b'])}", 14, "HEAD", INK)
        text(c, tx + 14, yy - 13, f"{wd['cut']} MM CUT, {bends_text(wd['bends'])}", 10, "ALT", INK)
        text(c, tx + 14, yy - 25, f"{wd['colour'].upper()} · {wd['line'].upper()}", 9.5, "ALT",
             WIRE[wd["colour"]] if wd["colour"] not in ("yellow",) else INK)
        text(c, tx + 14, yy - 37, wd["what"], 8.5, "ALT", GREY)
        LAB.block(tx, yy - 40, tx + cw - 6, yy + 12, f"row {n}")


def ra_pin_table(c, x, y, rows, size=11, step=17):
    for i, (pin, hh, line) in enumerate(rows):
        yy = y - i * step
        text(c, x, yy, hh.upper(), size + 1, "HEAD", NEON)
        text(c, x + 38, yy, pin, size, "ALT", INK)
        text(c, x + 38, yy - size * 0.95, line, size - 2.5, "ALT", GREY)


def swd(c, pg):
    head, pins = PARTS["J3"]
    page(c, "04", "SWD HEADER J3, COLUMN A", "5 PINS IN A12-A16. LOWEST PART: IT GOES ON FIRST. THE DEBUG PORT.", pg,
         SLOGANS5[4])
    g = Grid(2, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "B3 CORE, TOP FACE. J3's short legs go down through A12, A13, A14, A15, A16 (column A, rows 12-16) from the",
        f"top; the long pins lie flat toward the FRONT edge and end at card Y {SWD_TIP} mm, {SWD_TIP} mm short of the edge, over",
        "the rails: the ST-LINK Dupont housings push on there, past the edge, lid open. Solder on the UNDERSIDE: A12",
        "first, check it lies flat and square, then the rest. Wires 17-21 already reach B12-B16 underneath."])
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "t_swd", x + 30, y + 34, w - 180, h - 34 - 34, align="l", valign="b")
    for _, hh, _ in pins:
        ring(c, *a.A(anchor_name(hh)))
    ends = [(f"{hole(hh)}\n{short(line)}", a.A(anchor_name(hh))) for _, hh, line in pins]
    place_chips(c, ends, a, size=9, dn_y=a.y - 16)
    tx = a.x + a.w + 14
    text(c, tx, y + h - 20, "HOLE  PIN", 9, "MONO", GREY)
    ra_pin_table(c, tx, y + h - 38, pins, 11, 26)
    LAB.block(tx, y + h - 38 - 4 * 26 - 14, x + w, y + h - 10, "pin table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Close-up from the front left. The pins", f"stop over the rails, {SWD_TIP} mm inside the edge."])
    a = Art(c, "t_swd_iso", x + 4, y + 4, w - 8, h - 8)
    label(c, a.x + 8, a.y + a.h - 10, "J3 PINS: TOWARD THE FRONT EDGE", *a.A("J3:tip"), 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), 3, [
        "J3 (B3.md): a generic right-angle male", "header, the bus header stock, cut to 1x5.",
        f"Pins end {SWD_TIP} mm short of the front edge."])
    Art(c, "p_swd", x + 30, y + 6, w - 60, h - 12)


def header(c, pg):
    head, pins = PARTS["XH3"]
    K = KEY_HOLE.upper()
    page(c, "05", "BUS HEADER XH3, COLUMN J", f"GENERIC RIGHT-ANGLE MALE HEADER, CUT TO 1x30. PIN {KEY} PULLED: THE SLOT KEY.",
         pg, SLOGANS5[3])
    g = Grid(2, 2, heights=[1.3, 1.25])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, textwrap.wrap(
        f"B3 CORE, TOP FACE. Short legs down through column J, from the top: every hole J1-J30 takes a pin (ringed) but "
        f"{K}. Pin {KEY} is pulled before fitting: the slot key, so B3 seats only in its own slot. The long pins point "
        "AWAY from column A, out past the snapped back edge. Solder on the UNDERSIDE: J1 first, check it sits flat, J30, "
        "the rest. " + b3md.DOT.split(" The header's")[0], 106))
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "t_header", x + 80, y + 22, w - 160, h - 22 - 30, align="c", valign="b")
    for n in range(1, 31):
        if n != KEY:
            ring(c, *a.A(f"J{n}"), r=3.9, w=1.4)
    j1, j30, jk = a.A("J1"), a.A("J30"), a.A(K)
    label(c, a.x - 8, j1[1] - 3, "J1: PIN 1", j1[0] - 4.2, j1[1], 9, "ALT", INK, "r", dot=False)
    label(c, a.x + a.w + 8, j30[1] - 3, "J30: PIN 30", j30[0] + 4.2, j30[1], 9, "ALT", INK, "l", dot=False)
    label(c, a.x + a.w + 8, j30[1] + 22, f"{K}: EMPTY\n(PIN {KEY} PULLED)", jk[0], jk[1] + 2, 9, "ALT", NEON, "l", dot=False)
    dx, dy = a.A("keydot")
    label(c, a.x - 8, dy + 14, f"{COLOUR.upper()} DOT:\nFRONT EDGE,\nNEAR ROW 1", dx - 3, dy, 9, "ALT", INK, "r", dot=False)
    chip(c, a.x + a.w / 2, y + 8, f"COLUMN J: 29 PINS. {K} EMPTY: PIN {KEY} PULLED (THE SLOT KEY)", 10, "HEAD", NEON, "c")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Pin n plugs into backplane line n. B3.md section 3."])
    colw = (w - 8) / 2
    import re as re_
    for i, (pin, hh, line) in enumerate(sorted(pins, key=lambda r: int(re_.search(r"\((\d+)\)$", r[0]).group(1)))):
        col, row = i // 15, i % 15
        tx = x + 6 + col * colw
        yy = y + h - 40 - row * ((h - 44) / 15)
        if pin.startswith("key "):
            text(c, tx, yy, K, 9.5, "HEAD", NEON)
            text(c, tx + 22, yy, "PULLED: SLOT KEY", 9, "HEAD", NEON)
            continue
        text(c, tx, yy, hh.upper(), 9.5, "HEAD", NEON)
        text(c, tx + 22, yy, short(line), 9, "ALT", INK if line != "not connected" else GREY)
    LAB.block(x, y, x + w, y + h, "pin table")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Cut 1x30 from a longer strip, file flat.",
                                            *textwrap.wrap(f"Then pin {KEY} out: {b3md.KEY_HOW}.", 42)])
    hd = Art(c, "p_header", x + 6, y + 30, w - 12, h - 70)
    for k in ("p1", "p30"):
        ring(c, *hd.A(k), r=4.0)
    kx, ky = hd.A("key")
    label(c, kx - 30, hd.y + hd.h + 6, f"PIN {KEY}: OUT", kx, ky, 9, "ALT", NEON, "r", dot=False)
    chip(c, hd.x + hd.w / 2, y + 14, f"PIN {KEY} PULLED: THE SLOT KEY", 10, "ALT", INK, "c")


def shtc3(c, pg):
    head, pins = PARTS["U5"]
    page(c, "06", "SHTC3 U5", "ADAFRUIT #4636. ENCLOSURE AIR SENSOR. FIVE PINS IN C4-C8. ITS BOARD REACHES THE FRONT EDGE.",
         pg, SLOGANS5[1])
    g = Grid(2, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "B3 CORE, TOP FACE. U5 stands on its 5-pin header in column C: C8 VIN, C7 3V, C6 GND, C5 SCL, C4 SDA. Its board",
        "reaches toward column A and over the front rails. Check the pins against U5's own labels: VIN must land in C8.",
        "Solder on the UNDERSIDE. 3V (C7) connects to nothing else. Wires 5, 6, 10, 12 already serve its strips."])
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "t_shtc3", x + 40, y + 34, w - 190, h - 34 - 34, align="l", valign="b")
    for _, hh, _ in pins:
        ring(c, *a.A(anchor_name(hh)))
    ends = [(f"{hole(hh)} {pin.split(' ')[0]}", a.A(anchor_name(hh))) for pin, hh, line in pins]
    place_chips(c, ends, a, size=9, up_y=a.A("J1")[1] + 8)
    tx = a.x + a.w + 14
    text(c, tx, y + h - 20, "HOLE  PIN", 9, "MONO", GREY)
    ra_pin_table(c, tx, y + h - 38, pins, 11, 26)
    LAB.block(tx, y + h - 38 - 4 * 26 - 14, x + w, y + h - 10, "pin table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Close-up from the front left: U5 over", "the rails, J3 on its right."])
    Art(c, "t_shtc3_iso", x + 4, y + 4, w - 8, h - 8)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["U5 alone, header down. The two STEMMA QT", "sockets stay empty."])
    a = Art(c, "p_shtc3", x + 4, y + 4, w - 8, h - 8)


def mini1(c, pg):
    head, pins = PARTS["A1"]
    page(c, "07", "WIO-E5 MINI A1  1/2", "SEEED 113990939. THE RADIO AND THE MCU. 24 PINS: D1-D12 IN COLUMN C, B1-B12 IN COLUMN H.",
         pg, SLOGANS5[4])
    g = Grid(1, 2, heights=[1.7, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B3 CORE, TOP FACE. A1 stands on its own two 12-pin headers: its D pins in C19-C30, its B pins in H19-H30.",
        "USB-C at its LEFT end, the SMA past the card's RIGHT edge. All 24 pins are fitted and soldered on the UNDERSIDE;",
        "the 12 that carry a line are named. The rest sit on strips that carry nothing (B3.md strip map)."])
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "t_mini", x + 70, y + 56, w - 170, h - 56 - 46, align="l", valign="b")
    for _, hh, _ in pins:
        ring(c, *a.A(anchor_name(hh)), r=3.9, w=1.4)
    wired = [(p, hh, line) for p, hh, line in pins if line != "not connected"]
    ends = [(f"{hole(hh)} {short(line)}", a.A(anchor_name(hh))) for p, hh, line in wired]
    place_chips(c, ends, a, size=9, gap=6, dn_y=a.y - 22)
    sx, sy = a.A("A1:sma")
    label(c, a.x + a.w + 10, sy - 40, "SMA-K: PAST\nTHE RIGHT EDGE", sx, sy, 9, "ALT", INK, "l")
    ux, uy = a.A("A1:usb")
    label(c, a.x - 10, uy - 3, "USB-C\n(CONSOLE)", ux, uy, 9, "ALT", INK, "r")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Fit A1 last: its board covers G20, E21, F21, F22, F23 and G26 (the top joints of wires 4, 11, 18, 19, 20, 13).",
        "Seat both headers fully, solder C19 and H30, check A1 sits level, then the other 22. AD1 (the right-angle SMA",
        "adapter) is NOT fitted today: it goes on at assembly (build/ASSEMBLY.md step 7), its arm toward the lid."])
    Art(c, "t_mini_iso", x + 36, y + 4, w * 0.58, h - 8, align="l")
    pa = Art(c, "p_mini", x + w * 0.64, y + 4, w * 0.36 - 8, h - 8)


def mini2(c, pg):
    head, pins = PARTS["A1"]
    page(c, "07", "WIO-E5 MINI A1  2/2", "EVERY PIN, EVERY HOLE. CHECK EACH AGAINST THE PRINT ON A1 BEFORE YOU SOLDER.",
         pg, SLOGANS5[4])
    g = Grid(2, 1)
    for k, (rowname, sel) in enumerate((("COLUMN H: A1's B PINS (B1-B12)", "B"), ("COLUMN C: A1's D PINS (D1-D12)", "D"))):
        x, y, w, h = panel(c, g.cell(k, 0), k + 1, [rowname, "B3.md section 3. Grey: not connected."])
        rows = [(p, hh, line) for p, hh, line in pins if p.rsplit("(", 1)[1].startswith(sel)]
        text(c, x + 40, y + h - 16, "HOLE   PIN", 9, "MONO", GREY)
        for i, (p, hh, line) in enumerate(rows):
            yy = y + h - 40 - i * (h - 48) / 12
            nc = line == "not connected"
            pid = p.rsplit("(", 1)[1].rstrip(")")
            text(c, x + 40, yy, hh.upper(), 14, "HEAD", GREY if nc else NEON)
            text(c, x + 82, yy, pid, 14, "HEAD", GREY if nc else INK)
            text(c, x + 116, yy + 3, p.rsplit(" (", 1)[0], 8.5, "ALT", GREY if nc else INK)
            text(c, x + 116, yy - 7, line, 8.5, "ALT", GREY)
        LAB.block(x + 34, y, x + w, y + h - 6, "pin table")


STRIP_COL = {"3V3": "#D7262E", "GND": "#1C1C1C", "SCL": "#E0B000", "SDA": "#2D6FD0", "NC": "#9C9C9C",
             "CUPS": "#2E9E48", "VANE": "#2E9E48", "RAIN": "#2E9E48", "SWDIO": "#12A3A3", "SWCLK": "#12A3A3",
             "NRST": "#12A3A3", "MUX RST": "#E07A1F", "INT": "#E07A1F"}


def strip_col(code):
    return HexColor(STRIP_COL.get(code, "#8E5BD0"))         # sensor-port lines S1 SDA ... S4 SCL: purple


def strips(c, pg):
    page(c, "08", "THE STRIP MAP", "B3.md SECTION 4. WHAT EVERY USED STRIP CARRIES, SEEN FROM THE TOP FACE.", pg, SLOGANS5[5])
    g = Grid(1, 2, heights=[1.55, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B3 CORE, TOP FACE, no parts drawn. Each row has two strips: columns A-E (below the channel) and columns F-J",
        "(above it). The bar colour and the code name the line it carries (codes above for F-J, below for A-E).",
        "Grey NC: the strip holds only an unused pin. No bar: the strip is not used. Rails: + = 3.3 V, − = ground."])
    face_tag(c, x + 34, y + h - 26, "top")
    a = Art(c, "t_strips", x + 40, y + 52, w - 80, h - 52 - 60, align="c", valign="b")
    pitch = a.A("A2")[0] - a.A("A1")[0]
    used = {}
    import re
    assert any(re.match(r"row \d+, columns [AF]-[EJ]", st) for st, _, _ in b3md.STRIPS), \
        "B3.md strip names changed: no 'row N, columns A-E/F-J' entries, the strip map would be empty"
    for strip, line, holes_ in b3md.STRIPS:
        m = re.match(r"row (\d+), columns ([AF])-[EJ]", strip)
        if not m:
            continue
        n, half = int(m.group(1)), m.group(2)
        code = short(line)
        used[(n, half)] = code
        r0, r1 = ("A", "E") if half == "A" else ("F", "J")
        (x0, y0), (_, y1) = a.A(f"{r0}{n}"), a.A(f"{r1}{n}")
        c.saveState()
        c.setFillColor(strip_col(code))
        c.setFillAlpha(0.28)
        c.setStrokeColor(strip_col(code))
        lw(c, 2.2)
        c.roundRect(x0 - pitch * 0.42, min(y0, y1) - pitch * 0.48, pitch * 0.84, abs(y1 - y0) + pitch * 0.96, 2,
                    stroke=1, fill=1)
        c.restoreState()
    top_y = max(a.A("bl")[1], a.A("br")[1]) + 6
    bot_y = min(a.A("fl")[1], a.A("fr")[1]) - 6
    for (n, half), code in used.items():
        px = a.A(f"A{n}")[0]
        c.saveState()
        if half == "F":
            c.translate(px + 3, top_y)
            c.rotate(90)
            c.setFillColor(INK if code != "NC" else GREY)
            c.setFont("ALT", 8)
            c.drawString(0, 0, code)
        else:
            c.translate(px + 3, bot_y)
            c.rotate(90)
            c.setFillColor(INK if code != "NC" else GREY)
            c.setFont("ALT", 8)
            c.drawRightString(0, 0, code)
        c.restoreState()
    LAB.block(a.x, top_y, a.x + a.w, top_y + 36, "codes F-J")
    LAB.block(a.x, bot_y - 36, a.x + a.w, bot_y, "codes A-E")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Rails (B3.md): + RAIL 3.3 V: wires from + RAIL " + _rail_list("F+") + ". − RAIL ground: wires from − RAIL "
        + _rail_list("F-") + ".",
        "Use this map for check 1 of step 09: every strip against its neighbours."])
    legend = [("3V3", "3.3 V supply"), ("GND", "ground"), ("SCL", "I2C clock (SCL)"), ("SDA", "I2C data (SDA)"),
              ("S1 SDA ... S4 SCL", "sensor port lines (header only)"),
              ("CUPS VANE RAIN", "meter lines to the mini"), ("SWDIO SWCLK NRST", "SWD lines"),
              ("MUX RST  INT", "mux reset; spare bus line"), ("NC", "only an unused pin")]
    for i, (k, s_) in enumerate(legend):
        col, row = i // 5, i % 5
        tx = x + 12 + col * (w / 2)
        yy = y + h - 40 - row * 22
        code = {"S1": "S1 SDA", "MUX": "MUX RST"}.get(k.split()[0], k.split()[0])
        c.saveState()
        c.setFillAlpha(0.55)
        c.setFillColor(strip_col(code))
        c.setStrokeColor(strip_col(code))
        c.setFillAlpha(0.28)
        lw(c, 2.2)
        c.roundRect(tx, yy - 3, 16, 12, 2, stroke=1, fill=1)
        c.restoreState()
        text(c, tx + 22, yy, k, 10, "HEAD", INK)
        text(c, tx + 130, yy, s_, 9, "ALT", GREY)
    LAB.block(x + 34, y + h - 40 - 4 * 22 - 6, x + w, y + h - 28, "legend")


def checks(c, pg):
    page(c, "09", "METER BEFORE POWER", "CONTINUITY MODE. B3 CORE ALONE ON THE BENCH. NOTHING PLUGGED IN.", pg, SLOGANS5[5])
    g = Grid(1, 2, heights=[0.85, 1.25])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["B3 CORE, finished, seen from the front left. Do the checks below in order."])
    a = Art(c, "t_final", x + 4, y + 4, w - 8, h - 8)
    groups = [l for l in b3md.BEFORE if l.startswith("Header pins")]
    full = b3md.KEY_CHECK
    spares = full.split("Spare pins", 1)[1]
    import re
    sp = re.findall(r"J(\d+) \(its strip also holds A1 ", spares)
    assert len(sp) == spares.count("unused)"), spares
    beeps = [re.match(r"Header pins (.+?) beep to each other: all (.+)\.", gg).groups() for gg in groups]
    rows = [("1", "NEIGHBOURS", "Each used strip (step 08) against the strips beside it: NO BEEP."),
            ("2", "3.3 V vs GROUND", "+ RAIL against − RAIL: NO steady BEEP."),
            ("3", "HEADER PINS", "Each pin Jn beeps to Fn (same row, its own strip) and to NO\nother header pin, except the groups in check 4."),
            ("4", "PIN GROUPS", "\n".join(f"{p.replace(', ', ' + ')} beep: {ln}." for p, ln in beeps)),
            ("5", f"KEY PIN {KEY}", f"J{KEY} pulled (hole J{KEY} empty: the slot key), every other pin fitted.\nSpares (no net on B3): "
             + ", ".join(f"J{n}" for n in sp) + ".\nEach shares its strip only with an unused A1 pin.")]
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Any beep where it says NO BEEP, or silence where it says BEEP: stop. Photograph it. Report to Claude.",
                                            "Source: build/B3.md, \"Before power\"."], warn=True)
    rh = (h - 52) / len(rows)
    for i, (n, t, s) in enumerate(rows):
        yy = y + h - 46 - i * rh
        badge(c, x + 52, yy + 4, n, 10)
        text(c, x + 70, yy, t, 13, "HEAD", INK)
        for k, ln in enumerate(s.split("\n")):
            text(c, x + 190, yy + 1 - 12 * k, ln, 9.5, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 26, yy - 4, 14, 14, stroke=1, fill=0)


PAGES = [("00-cover", [cover]), ("00-what-you-are-building", [built_page]), ("01-snap", [snap]),
         ("02-know-the-faces", [know]),
         ("03-underside-wires", [(lambda c, pg, gi=gi: wires_page(c, pg, gi)) for gi in range(len(GROUPS))]),
         ("04-swd-header", [swd]), ("05-bus-header", [header]), ("06-shtc3", [shtc3]),
         ("07-wio-e5-mini", [mini1, mini2]), ("08-strip-map", [strips]), ("09-meter-checks", [checks])]

HOLE_ISSUES = []


def build(path, fns, start=1, report=False):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 5: build B3 CORE")
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


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    allfns = [f for _, fns in PAGES for f in fns]
    bad = build(OUT / "session5-all.pdf", allfns, 1, report=True)
    print("ok", len(allfns), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
