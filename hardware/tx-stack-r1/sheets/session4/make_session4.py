"""Session 4: build B1 PORTS A. Same flat-pack style and pipeline as Session 2 (B4 POWER).

Source of truth: hardware/tx-stack-r1/build/B1.md, parsed by b1md.py (every table on these pages comes from it);
geometry from layout/stack.py + layout/route.py via scenes4.py (render it first, one scene per process).
Hole names: the board prints ROWS as letters (A-J) and COLUMNS as numbers (1-30). B1.md writes holes as
letter + number ('e10'); here that is shown as printed: E10 = row E, column 10.

Usage: pdfenv/bin/python -B make_session4.py [OUT_DIR]     (default ../out)
"""
import re
import sys
from pathlib import Path

from sheetlib import *          # noqa: F401,F403  (page furniture, chips, leaders, Art, checks)
import sheetlib as SL
import b1md

SL.LEADER_INK = True        # every leader black on a white halo: never red or magenta lines on the red card

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "out"
RED = HexColor("#D7262E")
WIRE = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
        "blue": HexColor("#2D6FD0")}
ORANGE = HexColor("#E07A1F")

SLOGANS4 = [
    "B1 PORTS A. THREE PORTS. THREE JACKS. ONE CARD.",
    "TOP IS THE FACE THAT READS. THE MACHINE CHECKED.",
    "A WIRE UNDER A PART CANNOT BE FIXED LATER.",
    "THIRTY PINS. THIRTY LINES. NONE PULLED.",
    "THE BAND IS THE CATHODE. THE CATHODE IS THE BAND.",
    "EVERY PORT IS GUARDED. EVERY GUARD IS LOW.",
    "METER FIRST. POWER NEVER. NOT TODAY.",
    "THE MOUTH FACES THE LID. THE WEATHER COMES IN.",
]


def hole(h):
    """B1.md hole -> as printed on the board."""
    if h.startswith("F+"):
        return f"+ RAIL {h[2:]}"
    if h.startswith("F-"):
        return f"− RAIL {h[2:]}"
    return h[0].upper() + h[1:]


def anchor_name(h):
    return h if h.startswith("F+") or h.startswith("F-") else h[0].upper() + h[1:]


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
    px, py = a.A(anchor_name(h))
    ring(c, px, py, color=color)
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


def axis_marks(c, a, face, fs=8.5):
    """Column numbers and row letters around a card drawing (the underside has no print to read)."""
    for n in (1, 5, 10, 15, 20, 25, 30):
        x, y = a.A(f"J{n}" if face == "under" else f"A{n}")
        text(c, x, a.y - 8, str(n), fs, "ALT", GREY, "c")
    for L in "ABCDEFGHIJ":
        x, y = a.A(f"{L}1")
        text(c, a.x - 6, y - 3, L, fs, "ALT", GREY, "r")
    LAB.block(a.x - 14, a.y - 11, a.x + a.w, a.y - 1, "axis numbers")


def lane_chips(c, items, a, lane, size=9, color=NEON, gap=8, end_off=4.6, dot=False, yb=None, font="ALT"):
    """Chips in one lane outside the card (lane 'up': above the card's back edge, 'dn': below the drawing).
    items: [(text, (px, py))]. Chips keep the left-to-right order of their targets, packed without overlap; each
    leader leaves the chip's inner edge at its centre (white halo, black line) and stops end_off short of a ring
    (or ends on a dot at the target when dot=True)."""
    ys = [a.A(k)[1] for k in ("fl", "fr", "bl", "br")]
    topy = max(ys)
    asc = size * 0.72
    items = sorted(((px, py, s_) for s_, (px, py) in items))
    if not items:
        return
    wd = [max(pdfmetrics.stringWidth(l, font, size) for l in s_.split("\n")) + 5.2 for _, _, s_ in items]
    ideal = [px - w_ / 2 for (px, _, _), w_ in zip(items, wd)]
    xs = ideal[:]
    for _ in range(40):
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
    if yb is None:
        yb = (topy + 12) if lane == "up" else (a.y - 28)
    for (px, py, s_), x0, w_ in zip(items, xs, wd):
        r = chip(c, x0 + w_ / 2, yb, s_, size, font, color, "c")
        sx, sy = (r[0] + r[2]) / 2, (r[1] if lane == "up" else r[3])
        if dot:
            tx, ty = px, py
        else:
            tx, ty = px, py + (end_off if lane == "up" else -end_off)
        c.setStrokeColor(WHITE)
        lw(c, 2.6)
        c.line(sx, sy, tx, ty)
        c.setStrokeColor(INK)
        lw(c, 1.0)
        c.line(sx, sy, tx, ty)
        if dot:
            SL.HC.mark(px, py, "leader dot")
            c.setFillColor(WHITE)
            c.circle(px, py, 2.6, stroke=0, fill=1)
            c.setFillColor(INK)
            c.circle(px, py, 1.6, stroke=0, fill=1)
        LAB.leaders.append((sx, sy, tx, ty, len(LAB.chips) - 1))


def table(c, x, y, rows, cols, size=9, lead=12.5, head=True, fonts=None, colors=None):
    """Plain text table: rows of strings at column x offsets `cols`. Returns the y below the last row."""
    for i, row in enumerate(rows):
        for j, (cell, cx) in enumerate(zip(row, cols)):
            f = "HEAD" if head and i == 0 else (fonts[j] if fonts else "ALT")
            col = INK if head and i == 0 else (colors[j] if colors else INK)
            text(c, x + cx, y - i * lead, cell, size + (1 if head and i == 0 else 0), f, col)
    return y - len(rows) * lead


# ------------------------------------------------------------------ B1.md content
PARTS = b1md.parts()
REF = {p["ref"]: p for p in PARTS}


def pins(ref):
    return REF[ref]["pins"]


def cnt(pred):
    return sum(1 for p in PARTS if pred(p))


def col_of(h):
    return int(h[1:]) if h[0] in "abcdefghij" else int(h[2:])


N_R = cnt(lambda p: p["ref"].startswith("R"))
N_Z = cnt(lambda p: p["head"].startswith("1N5232B"))
N_S = cnt(lambda p: p["head"].startswith("BAT85S"))
N_F = cnt(lambda p: p["ref"].startswith("F"))
JACKS = [p["ref"] for p in PARTS if p["ref"].startswith("J1")]
N_J = len(JACKS)
WIRES_MD = b1md.wires()
JUMP_MD = b1md.jumpers()
assert not b1md.has_leads(), "B1.md has a leads section again: Session 4 has no leads page"
assert len(pins("XH1")) == 30 and [p["Hole"] for p in pins("XH1")] == [f"j{n}" for n in range(1, 31)], \
    "B1.md: XH1 must be the full 1x30 in j1-j30"


def port_of_jack(ref):
    """'J11' -> 'S1' (B1.md: '**J11** RJ11 S1 (...)')."""
    return re.match(r"RJ11 (S\d)", REF[ref]["head"]).group(1)


def jack_cols(ref):
    hs = [q["Hole"] for q in pins(ref)]
    assert all(h[0] == "a" for h in hs), f"{ref}: header not in row a"
    return col_of(hs[0]), col_of(hs[-1])


JACK_ORDER = sorted(JACKS, key=lambda j: jack_cols(j)[0])     # left to right on the card
STEP_NO = {}


# ------------------------------------------------------------------ pages
def cover(c, pg):
    page(c, "00", "SESSION 4: B1 PORTS A",
         f"ONE CARD. {len(PARTS)} PARTS. {len(WIRES_MD)} WIRES UNDER, {len(JUMP_MD)} JUMPERS. NO POWER TODAY.",
         pg, SLOGANS4[0])
    g = Grid(2, 3, heights=[1.55, 0.95, 0.72])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS FOR B1 PORTS A. LAY THEM OUT BEFORE YOU HEAT THE IRON. COUNTS FROM B1.md (PARTS, LOWEST FIRST).")
    items = [("B1 PORTS A CARD\n(rails snapped, Session 1)", "p_card"),
             ("XH1 RIGHT-ANGLE HEADER\n1x30, every pin fitted", "p_header"),
             (f"{N_R}x 100 OHM 1/4 W\nStackpole CF14JT100R", "p_res"),
             (f"{N_Z}x 1N5232B ZENER (left)\n{N_S}x BAT85S SCHOTTKY (right)", "p_diodes"),
             (f"{N_F}x MF-R010 PTC FUSE\nBourns, 100 mA", "p_ptc"),
             (f"{N_J}x SPARKFUN BOB-14021\nRJ11 breakout, bare board", "p_bob"),
             (f"{N_J}x AMPHENOL 87180-066LF\nRJ11 6P6C jack", "p_jack"),
             (f"{N_J}x 1x6 MALE HEADER\nstraight, 2.54 mm", "p_hdr6"),
             (f"BARE TINNED WIRE\n{len(JUMP_MD)} jumpers, 20 mm each", "p_jumper"),
             (f"24 AWG SOLID, INSULATED\nred, black, blue, yellow ({len(WIRES_MD)})", "p_wires")]
    cw, rh = w / 5, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 5, i // 5
        X, Y = x + cw * col, y + h - rh * (row + 1)
        nl = name.count("\n")
        Art(c, art, X + 5, Y + 26 + nl * 10, cw - 10, rh - 32 - nl * 10)
        chip(c, X + cw / 2, Y + 14 + nl * 10, name, 8.5, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (24 AWG)", "MULTIMETER (CONTINUITY + OHMS)",
             "SMALL PLIERS (FORM THE LEADS)", "STEEL RULER (WIRE LENGTHS)", "HELPING HANDS (THE BREAKOUTS)"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 10.5, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER. LOWEST PARTS FIRST.")
    steps = ["01  KNOW THE TWO FACES", f"02  {len(WIRES_MD)} WIRES ON THE UNDERSIDE", f"03  {len(JUMP_MD)} BARE JUMPERS",
             "04  BUS HEADER XH1, ROW J", f"05  {N_R} RESISTORS", f"06  {N_Z + N_S} DIODES, PORT BY PORT", f"07  {N_F} FUSES",
             f"08  BUILD {N_J} JACK BREAKOUTS", f"09  JACKS {', '.join(JACK_ORDER)} IN ROW A", "10  STRIP MAP",
             "11  METER BEFORE POWER"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 14 - i * (h - 8) / len(steps), s, 11, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    js = ", ".join(f"{j} ({port_of_jack(j)}) A{jack_cols(j)[0]}-A{jack_cols(j)[1]}" for j in JACK_ORDER)
    rules = ["EVERY HOLE IS NAMED AS PRINTED: LETTER = ROW (A-J), NUMBER = COLUMN (1-30). E10 = ROW E, COLUMN 10.",
             "TOP = THE FACE WHERE \"DigiKey\" READS. ROW A TOWARD YOU. COLUMNS 1 TO 30 LEFT TO RIGHT.",
             f"JACKS ON ROW A: {js}. MOUTHS OUT OVER THE FRONT EDGE.",
             "NO POWER IN THIS SESSION. THE METER IS THE ONLY JUDGE."]
    for i, s in enumerate(rules):
        yy = y + h - 10 - i * (h - 6) / 4
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 9, "ALT", INK)


def know(c, pg):
    page(c, "01", "KNOW THE TWO FACES", "B1 PORTS A HAS A TOP AND AN UNDERSIDE. EVERY INSTRUCTION NAMES ONE.", pg,
         SLOGANS4[1])
    g = Grid(1, 3, heights=[1.1, 1.1, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "TOP FACE: \"DigiKey\" and \"SolderFul BreadBoard\" read correctly, row A toward you, columns 1 to 30 left to",
        "right. Rows are LETTERS (A-J), columns are NUMBERS (1-30). Example: E10 is row E, column 10 (ringed)."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "b1_top", x + 96, y + 24, 330, h - 28, align="l", valign="t")
    _, py = a.A("E10")
    ring_label(c, a, "e10", "E10 = ROW E, COLUMN 10", dx=0, dy=a.A("fl")[1] - 16 - py, size=10)
    r = chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "ROW A\n(toward you)", 9, "ALT", INK)
    leader(c, r, a.A("A30")[0] + 3, a.A("A30")[1], INK, dot=False)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "ROW J\n(header row)", 9, "ALT", INK)
    chip(c, x + 8, y + 20, "FRONT EDGE\n= A SIDE", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "UNDERSIDE: turn the card over toward you, over its FRONT edge. Now row J is toward you, row A away, and",
        "columns STILL run 1 to 30 left to right. No print here: count from the left end. E10 is ringed again."])
    face_tag(c, x + 4, y + h - 40, "under")
    a = Art(c, "b1_under", x + 96, y + 14, 330, h - 40, align="l", valign="b")
    axis_marks(c, a, "under")
    _, py = a.A("E10")
    ring_label(c, a, "e10", "E10", dx=0, dy=a.A("fl")[1] + 10 - py, size=10)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "ROW J\n(toward you)", 9, "ALT", INK)
    chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "ROW A\n(away from you)", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 2), 3, ["The build sheet (B1.md) writes holes in lower case: e10. It is the same hole: E10.",
                                            "Rails: F+1 = the + RAIL at column 1 (outer front rail, 3.3 V). F-3 = the − RAIL at column 3 (ground)."])
    rows = [("B1.md", "THIS SHEET", "ON THE BOARD"), ("e10", "E10", "row E, column 10"),
            ("i12", "I12", "row I, column 12"), ("F+1", "+ RAIL 1", "outer front rail, column 1"),
            ("F-23", "− RAIL 23", "inner front rail, column 23")]
    for i, (a_, b_, c_) in enumerate(rows):
        yy = y + h - 16 - i * 17
        f = "HEAD" if i == 0 else "ALT"
        text(c, x + 50, yy, a_, 11, f, GREY if i else INK)
        text(c, x + 130, yy, b_, 11, f, NEON if i else INK)
        text(c, x + 230, yy, c_, 11, f, INK)


U_PAGES = [[[1], [2, 3]], [[4, 5], [6, 7]], [[8, 9], [10, 11]]]
assert sorted(n for pg_ in U_PAGES for g_ in pg_ for n in g_) == list(range(1, len(WIRES_MD) + 1))


def wires_page(c, pg, part):
    groups = U_PAGES[part - 1]
    page(c, "02", f"{len(WIRES_MD)} WIRES ON THE UNDERSIDE  {part}/{len(U_PAGES)}",
         "24 AWG SOLID INSULATED. B1 PORTS A UNDERSIDE. THEY GO FIRST: PARTS COVER THESE HOLES LATER.", pg, SLOGANS4[2])
    g = Grid(1, 2)
    gi0 = sum(len(p_) for p_ in U_PAGES[:part - 1])
    for k, nums in enumerate(groups):
        first = gi0 + k == 0
        cap = [f"B1 PORTS A, UNDERSIDE (row J toward you). Wire{'s' if len(nums) > 1 else ''} "
               f"{', '.join(map(str, nums))} of {len(WIRES_MD)}." + ("" if first else " Grey = wires already in."),
               "Cut each wire to the length shown, strip 3 mm at both ends, lay it flat along the drawn route with",
               "right-angle bends. Push each end through its hole from the UNDERSIDE, solder it on the TOP, trim."]
        x, y, w, h = panel(c, g.cell(0, k), None, cap)
        face_tag(c, x + 4, y + h - 20, "under")
        a = Art(c, f"u{gi0 + k + 1}", x + 14, y + 40, 330, h - 72, align="l", valign="b")
        axis_marks(c, a, "under")
        tx = a.x + a.w + 10
        text(c, tx, y + h - 14, "#   FROM       TO", 9, "MONO", GREY)
        for j, n in enumerate(nums):
            r = WIRES_MD[n - 1]
            col = r["Colour"]
            yy = y + h - 34 - j * 62
            c.setFillColor(WIRE[col])
            c.rect(tx, yy - 47, 6, 55, stroke=0, fill=1)
            text(c, tx + 12, yy, f"{n}  {hole(r['From'])}  TO  {hole(r['To'])}", 12, "HEAD", INK)
            text(c, tx + 12, yy - 12, r["Length"].upper().replace("MM,", "MM CUT,"), 9, "ALT", INK)
            text(c, tx + 12, yy - 23, f"{col.upper()} · {short_line(r['Line']).upper()}", 8.5, "ALT", INK)
            for q, ln in enumerate(wrap(r["What"], 44)[:2]):
                text(c, tx + 12, yy - 34 - q * 10, ln, 8, "ALT", GREY)
            LAB.block(tx, yy - 48, x + w, yy + 10, f"row {n}")
        for n in nums:
            for hn in (WIRES_MD[n - 1]["From"], WIRES_MD[n - 1]["To"]):
                ring(c, *a.A(anchor_name(hn)))
        ends = [(hole(h_), a.A(anchor_name(h_))) for n in nums for h_ in (WIRES_MD[n - 1]["From"], WIRES_MD[n - 1]["To"])]
        up = [e for e in ends if e[1][1] > (a.A("fl")[1] + a.A("bl")[1]) / 2]
        dn = [e for e in ends if e not in up]
        lane_chips(c, up, a, "up")
        lane_chips(c, dn, a, "dn")


def short_line(line):
    return line.replace("sensor port ", "S").replace(" (SDA)", "").replace(" (SCL)", "")


def wrap(s, n):
    out, cur = [], ""
    for wd in s.split():
        if cur and len(cur) + 1 + len(wd) > n:
            out.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    return out + [cur]


def port_in(what):
    m = re.search(r"port (S\d)", what)
    return m.group(1) if m else "?"


def jumpers(c, pg):
    page(c, "03", f"{len(JUMP_MD)} BARE JUMPERS ON TOP",
         "TINNED BARE WIRE. B1 PORTS A TOP FACE. EACH PORT BLOCK'S GROUND STRIP TO THE − RAIL.", pg, SLOGANS4[5])
    g = Grid(1, 2, heights=[1.2, 1])
    cols = ", ".join(str(col_of(r["From"])) for r in JUMP_MD)
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B1 PORTS A, TOP FACE. Each jumper joins a row-A hole to the − RAIL hole in the same column, across the",
        "printed number row. Cut 20 mm of bare tinned wire, bend a U, legs down through the two holes from the TOP,",
        f"bridge 1 mm above the card, solder underneath, trim. Strips {cols} (rows A-E) become ground."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_jumpers", x + 70, y + 30, 330, h - 34, align="l")
    for r in JUMP_MD:
        ring(c, *a.A(anchor_name(r["From"])))
        ring(c, *a.A(anchor_name(r["To"])))
    lane_chips(c, [(f"JMP{r['#']}", a.A(f"JMP{r['#']}m")) for r in JUMP_MD], a, "dn", color=INK, dot=True,
               yb=a.y - 18)
    tx = a.x + a.w + 12
    text(c, tx, y + h - 50, "#     FROM   TO", 9, "MONO", GREY)
    for i, r in enumerate(JUMP_MD):
        yy = y + h - 66 - i * 25
        text(c, tx, yy, f"JMP{r['#']}  {hole(r['From'])} TO {hole(r['To'])}", 11, "HEAD", INK)
        text(c, tx, yy - 10, f"{r['Length'].upper()} BARE · PORT {port_in(r['What'])}", 8.5, "ALT", GREY)
    LAB.block(tx, y + h - 66 - (len(JUMP_MD) - 1) * 25 - 14, x + w, y + h - 44, "jumper table")
    lo, hi = min(col_of(r["From"]) for r in JUMP_MD), max(col_of(r["From"]) for r in JUMP_MD)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        f"Close-up from the front-left, columns {lo}-{hi}. The U-shaped bridges stand 1 mm proud and cross the printed",
        "number row. The fuses (step 07) stand in the columns between them, from the + RAIL to row A."])
    a = Art(c, "t_jumpers_iso", x + 60, y + 28, w - 120, h - 32)
    lane_chips(c, [(f"JMP{r['#']}: {hole(r['From'])} TO {hole(r['To'])}", a.A(f"JMP{r['#']}m")) for r in JUMP_MD],
               a, "dn", color=INK, dot=True, yb=a.y - 14)


def header(c, pg):
    page(c, "04", "BUS HEADER XH1, ROW J", "GENERIC 2.54 MM RIGHT-ANGLE MALE HEADER, CUT TO 1x30. ALL 30 PINS STAY IN.", pg,
         SLOGANS4[3])
    g = Grid(1, 2, heights=[1.0, 1.15])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B1 PORTS A, TOP FACE. Short legs down through J1 to J30 (row J, columns 1-30) from the top: every hole in",
        "row J takes a pin. The long pins point AWAY from row A, out past the snapped back edge. Solder on the",
        "UNDERSIDE: J1 first, check it sits flat and square, then J30, then the rest."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_header", x + 96, y + 4, 330, h - 8, align="l")
    for hname in ("j1", "j30"):
        ring(c, *a.A(anchor_name(hname)))
    j1, j30 = a.A("J1"), a.A("J30")
    label(c, a.x - 6, j1[1] + 4, "J1: PIN 1", j1[0] - 4.2, j1[1], 9, "ALT", INK, "r", dot=False)
    label(c, a.x + a.w + 6, j30[1] + 4, "J30: PIN 30", j30[0] + 4.2, j30[1], 9, "ALT", INK, dot=False)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Every pin and its line (B1.md, XH1). Pin n plugs into backplane line n. Spare pins carry no net on B1,",
        "and they stay in: the 1x30 is full, always. Cut 1x30 from a longer strip: pull the 31st pin, cut through",
        "its empty place, file flat."])
    rows = pins("XH1")
    colw = (w - 50) / 2
    for half in (0, 1):
        tx = x + 44 + half * colw
        text(c, tx, y + h - 22, "PIN  HOLE  LINE", 9, "MONO", GREY)
        for i, p in enumerate(rows[half * 15:(half + 1) * 15]):
            n = half * 15 + i + 1
            yy = y + h - 38 - i * 15.2
            line = p["Line"]
            spare = line == "not connected"
            text(c, tx, yy, f"{n:>2}", 10, "HEAD", INK)
            text(c, tx + 26, yy, hole(p["Hole"]), 10, "HEAD", NEON)
            text(c, tx + 62, yy, "spare: no net on B1 (pin stays in)" if spare else line, 9, "ALT", GREY if spare else INK)


def resistors(c, pg):
    rs = [p for p in PARTS if p["ref"].startswith("R")]
    slant = [p["ref"] for p in rs if col_of(p["pins"][0]["Hole"]) != col_of(p["pins"][1]["Hole"])]
    page(c, "05", f"{N_R} RESISTORS ACROSS THE CHANNEL", "100 OHM, LYING FLAT. EACH PORT'S DATA AND CLOCK, ROW E TO ROW F.",
         pg, SLOGANS4[5])
    g = Grid(1, 2, heights=[1.25, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B1 PORTS A, TOP FACE. Each 100 ohm resistor lies flat across the centre channel: lead 1 in row E, lead 2 in",
        f"row F, same column, except {' and '.join(slant)}: one column over, on a slant. Bend both leads at the body to",
        "the two holes' spacing, push down, body on the card, solder on the UNDERSIDE, trim. No polarity."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_res", x + 70, y + 32, 330, h - 36, align="l", valign="t")
    for p in rs:
        for q in p["pins"]:
            ring(c, *a.A(anchor_name(q["Hole"])))
    lane_chips(c, [(p["ref"], a.A(f"{p['ref']}_m")) for p in rs], a, "dn", color=INK, dot=True, yb=a.y - 16)
    tx = a.x + a.w + 12
    text(c, tx, y + h - 50, "REF  ROW E  ROW F", 9, "MONO", GREY)
    for i, p in enumerate(rs):
        yy = y + h - 66 - i * 25
        e_, f_ = p["pins"][0]["Hole"], p["pins"][1]["Hole"]
        text(c, tx, yy, f"{p['ref']}   {hole(e_)}  TO  {hole(f_)}", 11, "HEAD", INK)
        k, what = p["ref"][1], "DATA" if p["ref"][2] == "1" else "CLOCK"
        text(c, tx, yy - 10, f"PORT S{k} {what}" + ("  · SLANT" if p["ref"] in slant else ""), 8.5, "ALT", GREY)
    LAB.block(tx, y + h - 66 - (len(rs) - 1) * 25 - 14, x + w, y + h - 44, "resistor table")
    r1, r2 = "R21", "R22"
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        f"Close-up from the front-left: {r1} ({hole(pins(r1)[0]['Hole'])} to {hole(pins(r1)[1]['Hole'])}, on its slant) and "
        f"{r2} ({hole(pins(r2)[0]['Hole'])} to {hole(pins(r2)[1]['Hole'])}), port S2.",
        "Body down on the card, leads square. The bands read brown, black, brown, gold: 100 ohm, 5 %."])
    a = Art(c, "t_res_iso", x + 60, y + 4, w - 120, h - 8)
    for ref in (r1, r2):
        px, py = a.A(f"{ref}_m")
        label(c, a.x + a.w + 6 if ref == r2 else a.x - 6, py + 30, ref, px, py, 10, "HEAD", INK,
              "l" if ref == r2 else "r")


def diode_row(ref):
    p = REF[ref]
    a1, a2 = p["pins"]
    band = "BAND DOWN" if a1["Pin"].startswith("cathode") else "BAND UP"
    return dict(ref=ref, value=p["head"].split(" ")[0], body=a1["Hole"], body_pin=a1["Pin"].split(" ")[0],
                loop=a2["Hole"], loop_pin=a2["Pin"].split(" ")[0], band=band)


def diodes(c, pg, k):
    refs = [f"D{k}{j}" for j in range(1, 6)]
    rows = [diode_row(r) for r in refs]
    cs = sorted({col_of(r[w]) for r in rows for w in ("body", "loop")})
    cr = f"{cs[0]}-{cs[-1]}"
    nz = sum(r["value"] == "1N5232B" for r in rows)
    page(c, "06", f"PORT S{k} DIODES: D{k}1-D{k}5  ({k}/3)",
         f"STANDING DO-35. COLUMNS {cr}, ROWS B-D. BODY ON THE FIRST HOLE, OTHER LEAD LOOPED OVER.",
         pg, SLOGANS4[4])
    g = Grid(2, 2, heights=[1.0, 1.05])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        f"B1 PORTS A, TOP FACE, columns {cr}. Where each diode goes: ● = the body's hole (it stands on it),",
        "○ = the hole its looped lead goes to. The BAND marks the cathode: BAND DOWN = against the card, BAND UP =",
        f"at the top, where the loop leaves. {nz} zener (1N5232B) and {len(rows) - nz} BAT85S Schottkys for port S{k}."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, f"t_d{k}_before", x + 92, y + 22, 290, h - 50, align="l")
    tx = a.x + a.w + 12
    rowsy = {}
    for r in rows:
        (bx, by), (lx, ly) = a.A(anchor_name(r["body"])), a.A(anchor_name(r["loop"]))
        rowsy.setdefault(round(by, 1), []).append((r, bx, lx, by))
    ys = sorted(rowsy)                              # page y, low to high: row B, row C, row D
    for yk in ys:
        for r, bx, lx, by in rowsy[yk]:
            ring(c, bx, by)
            ring(c, lx, by)
            c.setFillColor(HAZ)                     # the body's hole: filled
            c.setStrokeColor(INK)
            lw(c, 1.2)
            c.circle(bx, by, 4.4, stroke=1, fill=1)
            sgn = -1 if yk == ys[0] else 1          # the bar between the two holes: below row B, above C and D
            yb = by + sgn * 8.0
            dashed(c, bx, yb, lx, yb, NEON, 1.6, (3, 2))
            c.setStrokeColor(NEON)
            lw(c, 1.6)
            c.line(bx, yb, bx, by + sgn * 4.6)
            c.line(lx, yb, lx, by + sgn * 4.6)
    lanes = {"up": [], "dn": [], "lt": []}
    for yk in ys:
        for r, bx, lx, by in rowsy[yk]:
            lane = "up" if (yk == ys[-1] and len(ys) > 1) else ("dn" if yk == ys[0] else "lt")
            sgn = -1 if yk == ys[0] else 1
            lanes[lane].append((f"{r['ref']} {r['value']}", ((bx + lx) / 2, by + sgn * 8.0)))
    lane_chips(c, lanes["up"], a, "up", color=INK, dot=False, end_off=0, yb=a.y + a.h + 5)
    lane_chips(c, lanes["dn"], a, "dn", color=INK, dot=False, end_off=0, yb=a.y - 13)
    for s_, (mx, yb) in lanes["lt"]:
        rr = chip(c, a.x - 8, yb - 3, s_, 9, "ALT", INK, "r")
        leader(c, rr, mx - 10, yb, INK, dot=False, w=0.8)
    text(c, tx, y + h - 22, "REF  BODY ON  LOOP TO  BAND", 8.5, "MONO", GREY)
    for i, r in enumerate(rows):
        yy = y + h - 40 - i * 24
        text(c, tx, yy, f"{r['ref']}  {hole(r['body'])}  {hole(r['loop'])}  {r['band']}", 11, "HEAD", INK)
        text(c, tx, yy - 10, f"{r['value']}: {r['body_pin']} in {hole(r['body'])}, {r['loop_pin']} in {hole(r['loop'])}",
             8.5, "ALT", GREY)
    LAB.block(tx, y + h - 40 - 4 * 24 - 14, x + w, y + h - 12, "diode table")
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, [
        "Fitted, from the front-left. Each body stands on its ● hole, 0.8 mm off the card; the other lead goes up,",
        "over (about 7 mm above the card) and down into its ○ hole. Solder on the UNDERSIDE, trim. Check every band",
        "against the table before you solder: a zener in backwards clamps the port's 3.3 V to 0.7 V."])
    a = Art(c, f"t_d{k}_iso", x + 30, y + 26, w - 60, h - 52)
    front = [r for r in rows if r["body"][0] == "b"]          # bodies in row B: nearest you, chips below
    back = [r for r in rows if r["body"][0] != "b"]
    lane_chips(c, [(f"{r['ref']} {r['band']}", a.A(f"{r['ref']}_top")) for r in back], a, "up", color=INK, dot=True,
               yb=a.y + a.h + 6)
    lane_chips(c, [(f"{r['ref']} {r['band']}", a.A(f"{r['ref']}_top")) for r in front], a, "dn", color=INK, dot=True,
               yb=a.y - 12)


def fuses(c, pg):
    fs = [p for p in PARTS if p["ref"].startswith("F")]
    cs = sorted(col_of(q["Hole"]) for p in fs for q in p["pins"])
    page(c, "07", f"{N_F} FUSES: {', '.join(p['ref'] for p in fs)}",
         "BOURNS MF-R010 PTC, STANDING. + RAIL TO ROW A. EACH PORT'S 3.3 V.", pg, SLOGANS4[5])
    g = Grid(1, 2, heights=[0.8, 1.2])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        f"B1 PORTS A, TOP FACE, columns {cs[0]}-{cs[-1]}, front. Each fuse goes from the + RAIL (outer front rail, 3.3 V",
        "supply) to row A in the same column: its port's 3.3 V strip. Form the leads out to 7.62 mm (the rail-to-",
        "row-A pitch). No polarity. Solder on the UNDERSIDE, trim. The jumpers (step 03) sit between them."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_fuse_before", x + 10, y + 4, w - 20, h - 64, valign="b")
    for p in fs:
        for q in p["pins"]:
            ring(c, *a.A(anchor_name(q["Hole"])))
    lane_chips(c, [(f"{p['ref']}: {hole(p['pins'][0]['Hole'])} TO {hole(p['pins'][1]['Hole'])}",
                    a.A(anchor_name(p["pins"][1]["Hole"]))) for p in fs], a, "up", color=NEON, end_off=4.2,
               yb=a.y + a.h + 6)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Fitted, from the front-left. The yellow discs stand 13.7 mm tall, broad faces toward the card's ends,",
        "between the + RAIL and row A. Their kinked leads keep the body off the card. The zeners stand behind."])
    a = Art(c, "t_fuse_iso", x + 20, y + 4, w - 40, h - 8)
    lane_chips(c, [(f"{p['ref']}: {hole(p['pins'][0]['Hole'])} TO {hole(p['pins'][1]['Hole'])}", a.A(f"{p['ref']}_top"))
                   for p in fs], a, "up", color=INK, dot=True, yb=a.y + a.h - 4)


def contact_labels(c, a, x, w, dy):
    """CONTACT 1 / CONTACT 6 on the header plastic's face, each label on its own end's side (no crossing)."""
    p1, p6 = a.A("B_hc1"), a.A("B_hc6")
    for i, (px, py) in ((1, p1), (6, p6)):
        left = px <= (p6 if i == 1 else p1)[0]
        label(c, x + 12 if left else x + w - 12, py + dy, f"CONTACT {i}", px, py, 9, "ALT", INK, "l" if left else "r")


def prep_jacks(c, pg):
    page(c, "08", f"BUILD {N_J} JACK BREAKOUTS", "SPARKFUN BOB-14021 COMES AS A BARE BOARD: FIT THE JACK, THEN THE 1x6 HEADER.",
         pg, SLOGANS4[7])
    g = Grid(2, 2, heights=[0.62, 1.2])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        f"As supplied, {N_J} of each. {', '.join(JACK_ORDER)} are identical: build all {N_J} now, off the card."])
    cw = (w - 40) / 3
    for i, (art, name) in enumerate((("p_bob", "BOB-14021: BARE BOARD\n6 pads in a row + 6 jack holes"),
                                     ("p_jack", "87180-066LF JACK\n6 pins, 2 pegs, mouth"),
                                     ("p_hdr6", "1x6 MALE HEADER\nshort end, plastic, long end"))):
        X = x + 40 + cw * i
        Art(c, art, X + 6, y + 36, cw - 12, h - 44)
        chip(c, X + cw / 2, y + 16, name, 8.5, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "1. JACK: six pins into the six staggered",
        "holes, two pegs into the two big holes.",
        "It fits from one face only. Seat it flat,",
        "solder the six pins on the other face.",
        "2. HEADER: SHORT ends up through the six",
        "pads in a row, plastic on the face AWAY",
        "from the jack. Solder on the jack's face."])
    a = Art(c, "bob_kit", x + 10, y + 34, w - 20, h - 64)
    label(c, x + w - 8, a.A("B_jtop")[1] + 18, "87180-066LF", *a.A("B_jtop"), 9, "ALT", INK, "r")
    contact_labels(c, a, x, w, -26)
    x, y, w, h = panel(c, g.cell(1, 1), 3, [
        "3. CLIP the jack's six pin tails to 1.5 mm",
        "under the board: on the card they stand",
        "over the + RAIL and − RAIL, 2.5 mm up.",
        "The header's long ends stay full length",
        "(they go through the card).",
        f"Make all {N_J}. Contact 1 is the header",
        "pin marked; contact 6 the other end."])
    a = Art(c, "bob_done", x + 10, y + 34, w - 20, h - 64)
    contact_labels(c, a, x, w, -30)
    px, py = a.A("B_jtop")
    label(c, x + w - 8, py + 14, "JACK ON TOP", px, py, 9, "ALT", INK, "r")


def fit_jacks(c, pg):
    page(c, "09", f"JACKS {', '.join(JACK_ORDER)} IN ROW A", "EACH BREAKOUT ON ITS 1x6 HEADER. MOUTHS OUT OVER THE FRONT EDGE, TOWARD THE LID.",
         pg, SLOGANS4[7])
    g = Grid(1, 3, heights=[0.92, 0.98, 0.95])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B1 PORTS A, TOP FACE, row A: " + "; ".join(f"{j} (port {port_of_jack(j)}) A{jack_cols(j)[0]}-A{jack_cols(j)[1]}"
                                                   for j in JACK_ORDER) + ".",
        "Contact 1 in the LEFT hole of each six. Long ends down from the TOP; solder on the UNDERSIDE, trim."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_jacks_before", x + 20, y + 28, w - 40, h - 72)
    for j in JACK_ORDER:
        for q in pins(j):
            ring(c, *a.A(anchor_name(q["Hole"])))
    lane_chips(c, [(f"{j} C1: {hole(pins(j)[0]['Hole'])}", a.A(anchor_name(pins(j)[0]["Hole"]))) for j in JACK_ORDER],
               a, "up", size=8.5, end_off=4.2, yb=a.y + a.h + 8)
    lane_chips(c, [(f"{j} C6: {hole(pins(j)[-1]['Hole'])}", a.A(anchor_name(pins(j)[-1]["Hole"]))) for j in JACK_ORDER],
               a, "dn", size=8.5, end_off=4.2, yb=a.y - 18)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Fitted, from above. Each breakout stands 2.5 mm up on its header plastic and reaches OUT past the front",
        "edge: the jack's mouth faces the lid. Press it square (board level, mouth straight out), solder one end",
        "pin, check, then the other five."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_jacks", x + 90, y + 4, 330, h - 30, align="l", valign="b")
    lane_chips(c, [(f"{j}: PORT {port_of_jack(j)}", a.A(f"{j}_jtop")) for j in JACK_ORDER], a, "up", color=INK, dot=True,
               yb=a.y + a.h + 6)
    fe = a.A("fl")
    chip(c, a.x - 6, fe[1] - 4, "FRONT\nEDGE", 9, "ALT", INK, "r")
    x, y, w, h = panel(c, g.cell(0, 2), 3, [
        "From the front-left: the three mouths overhang the front edge, open toward the lid. Top of each jack:",
        f"{b1md.top_mm(JACK_ORDER[0])} mm above the card. The jack's contacts reach the card only through the header."])
    a = Art(c, "t_jacks_iso", x + 20, y + 4, w - 40, h - 30)
    lane_chips(c, [(f"{j} MOUTH", a.A(f"{j}_mouth")) for j in JACK_ORDER], a, "up", color=INK, dot=True,
               yb=a.y + a.h + 6)


STRIP_KEY = [("3.3 V supply", "#D7262E"), ("ground", "#1C1C1C"), ("port 3.3 V (after its fuse)", "#F08A1C"),
             ("data at the jack", "#7FB0F0"), ("data (bus side)", "#2D6FD0"), ("clock at the jack", "#F7E07A"),
             ("clock (bus side)", "#E0B000"), ("other bus line", "#2E9B4A"), ("spare: no net", "#9A9A9A")]


def strips(c, pg):
    page(c, "10", "STRIP MAP", "WHAT EVERY USED STRIP CARRIES (B1.md STRIP MAP). CHECK AGAINST IT BEFORE THE METER.", pg,
         SLOGANS4[6])
    g = Grid(1, 2, heights=[1.0, 1.15])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "B1 PORTS A, TOP FACE. Each used strip (five holes: rows A-E or rows F-J of one column) and both front rails,",
        "shaded by the line it carries. Unshaded strips carry nothing."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_strips", x + 70, y + 4, 330, h - 8, align="l")
    kx = a.x + a.w + 12
    for i, (s_, col) in enumerate(STRIP_KEY):
        yy = y + h - 52 - i * 15
        c.setFillColor(HexColor(col))
        c.rect(kx, yy - 2, 16, 9, stroke=0, fill=1)
        text(c, kx + 22, yy, s_, 8.5, "ALT", INK)
    LAB.block(kx, y + h - 52 - 8 * 15 - 6, x + w, y + h - 40, "key")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["The map, column by column. A-E = the front half of the column, F-J = the back half."])
    rows = b1md.strips()
    cols = 3
    per = (len(rows) + cols - 1) // cols
    cw = (w - 44) / cols
    for i, r in enumerate(rows):
        cx = x + 40 + (i // per) * cw
        yy = y + h - 16 - (i % per) * ((h - 34) / per)
        s_ = r["Strip"].replace("column ", "COL ").replace(", rows ", " ").replace("rail F+", "+ RAIL").replace("rail F-", "− RAIL")
        line = (r["Line"].replace("sensor port ", "S").replace(" (SDA)", "").replace(" (SCL)", "")
                .replace("nothing (an unused pin)", "spare").replace(" (for the charger interrupt)", ""))
        text(c, cx, yy, s_, 8.5, "HEAD", INK)
        text(c, cx + 56, yy, line, 8, "ALT", INK)


def spare_range(s):
    """'J19, J20, ... J30' -> 'J19-J30' when consecutive (B1.md's before-power list)."""
    ns = [int(v.strip()[1:]) for v in s.split(",")]
    return f"J{ns[0]}-J{ns[-1]}" if ns == list(range(ns[0], ns[-1] + 1)) else s


def jack_checks():
    """Per jack, what each contact should read (from B1.md: the contact's line, the strip map, the resistors, the
    fuses and XH1's pins). Returns [(jack, [(contact, expectation)])]."""
    out = []
    for j in JACK_ORDER:
        exp = []
        for q in pins(j):
            n = q["Pin"].split()[1]
            line = q["Line"]
            if line == "not connected":
                exp.append((n, "beeps to NOTHING else"))
            elif line == "ground":
                exp.append((n, "BEEPS to the − RAIL"))
            elif line.endswith("3.3 V"):
                f = next(p["ref"] for p in PARTS if p["ref"].startswith("F") and p["pins"][1]["Line"] == line)
                exp.append((n, f"a few ohms to the + RAIL (fuse {f})"))
            else:
                r = next(p for p in PARTS if p["ref"].startswith("R") and p["pins"][0]["Line"] == line)
                bus = r["pins"][1]["Line"]
                xp = next(p["Pin"].split()[1] for p in pins("XH1") if p["Line"] == bus)
                exp.append((n, f"100 ohm to XH1 pin {xp} ({r['ref']})"))
        out.append((j, exp))
    return out


def checks(c, pg):
    page(c, "11", "METER BEFORE POWER", "CONTINUITY AND OHMS. B1 PORTS A ALONE ON THE BENCH. NOTHING PLUGGED IN.", pg,
         SLOGANS4[6])
    g = Grid(2, 3, heights=[0.85, 1.0, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, ["B1 PORTS A, finished, seen from the front-left. Do the checks below in order."])
    Art(c, "t_final", x + 4, y + 4, w - 8, h - 8)
    bp = b1md.before()
    spares = next(b for b in bp if b.startswith("The full 1x30")).split(":")[-1].strip().rstrip(".")
    groups = [b for b in bp if b.startswith("Header pins ") and "beep to each other" in b]
    gtxt = "; ".join(b.split(":")[0].replace("Header pins ", "").replace(" beep to each other", "") for b in groups)
    fs = [p for p in PARTS if p["ref"].startswith("F")]
    fcols = ", ".join(str(col_of(p["pins"][1]["Hole"])) for p in fs)
    checks = [("1", "NEIGHBOURS", "Each used strip (step 10) against the strips beside it: NO BEEP.\n"
                                  "Row E to row F through a 100 ohm resistor: some meters beep. That is fine."),
              ("2", "3.3 V vs GROUND", "+ RAIL against − RAIL: NO BEEP (the zeners read as diodes, not a short).\n"
                                       f"+ RAIL to row A, columns {fcols}: a few ohms (the fuses)."),
              ("3", "HEADER PINS", "Each pin Jn beeps to Fn (row F, same column: its own strip) and to NO\n"
                                   f"other header pin, except: {gtxt} (all ground)."),
              ("4", "RAIL PINS", "J1 beeps to the + RAIL. The ground pins beep to the − RAIL."),
              ("5", "ALL 30 PINS", f"J1-J30 all fitted, none pulled. Spares (no net on B1): {spare_range(spares)}.\n"
                                   "Each spare beeps to no other header pin.")]
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, ["Any beep where it says NO BEEP, or silence where it says BEEP: stop. Photograph it. Report to Claude."],
                       warn=True)
    for i, (n, t, s) in enumerate(checks):
        yy = y + h - 34 - i * (h - 44) / len(checks)
        badge(c, x + 52, yy + 4, n, 10)
        text(c, x + 70, yy, t, 12, "HEAD", INK)
        for k, ln in enumerate(s.split("\n")):
            text(c, x + 180, yy + 1 - 11 * k, ln, 9, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 24, yy - 4, 14, 14, stroke=1, fill=0)
    x, y, w, h = panel(c, g.cell(0, 2, 2), 3, [
        "6. JACK CONTACTS: probe each header pin ON TOP of the breakout (the short ends). Ohms range."])
    for i, (j, exp) in enumerate(jack_checks()):
        cx = x + 44 + i * (w - 54) / len(JACK_ORDER)
        text(c, cx, y + h - 34, f"{j} (PORT {port_of_jack(j)})", 10.5, "HEAD", INK)
        for k, (n, e) in enumerate(exp):
            yy = y + h - 50 - k * 12.5
            text(c, cx, yy, f"C{n}", 9, "HEAD", NEON)
            text(c, cx + 18, yy, e, 8, "ALT", INK)


def built_page(c, pg):
    import builtpage
    builtpage.built(c, pg, SL, "00", SLOGANS4[0])


PAGES = [("00-cover", [cover]), ("00-what-you-are-building", [built_page]), ("01-know-the-faces", [know]),
         ("02-underside-wires", [lambda c, pg, k=k: wires_page(c, pg, k) for k in range(1, len(U_PAGES) + 1)]),
         ("03-jumpers", [jumpers]), ("04-bus-header", [header]), ("05-resistors", [resistors]),
         ("06-diodes", [lambda c, pg: diodes(c, pg, 1), lambda c, pg: diodes(c, pg, 2), lambda c, pg: diodes(c, pg, 3)]),
         ("07-fuses", [fuses]), ("08-jack-breakouts", [prep_jacks]), ("09-jacks-on-row-a", [fit_jacks]),
         ("10-strip-map", [strips]), ("11-meter-checks", [checks])]

HOLE_ISSUES = []


def build(path, fns, start=1, report=False):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 4: build B1 PORTS A")
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
    allfns = [f for _n, fns in PAGES for f in fns]
    bad = build(OUT / "session4-all.pdf", allfns, 1, report=True)
    print("ok", len(allfns), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
