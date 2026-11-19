"""Session 3: build B2 PORTS B + METERS. Same flat-pack style and pipeline as Sessions 1 v2 and 2.

Source of truth: hardware/tx-stack-r1/build/B2.md, read by b2md.py (every table printed here comes from it);
geometry from layout/stack.py + layout/route.py via scenes3.py (anchors in svg/*.json).
Hole names: SolderFul (and layout/stack.py) call the lettered lines A-J COLUMNS and the numbered lines 1-30 ROWS.
B2.md writes holes as letter + number ('e10'); here that is shown as printed: E10 = column E, row 10. Three jacks
share a name with a column-J hole (J14, J21, J22): the sheets always say JACK J14 for the part and HOLE J14 for the hole.

Every caption, table and step list is built from B2.md (b2md.py) and from scenes3.py's step grouping
(svg/groups.json, written by every render): nothing about holes or lengths is typed here.

Usage: pdfenv/bin/python make_session3.py [OUT_DIR]     (renders first: sh render_all.sh)
"""
import json
import re
import sys
from pathlib import Path

from sheetlib import *          # noqa: F401,F403  (page furniture, chips, leaders, Art, checks)
import sheetlib as SL
import b2md as B

SL.LEADER_INK = True        # every leader black on a white halo: never red or magenta lines on the red card

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
RED = HexColor("#D7262E")
INS = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
       "blue": HexColor("#2D6FD0"), "green": HexColor("#2E9A48")}

SLOGANS3 = [
    "B2 HEARS THE WIND, THE RAIN AND PORT S4.",
    "TOP IS THE FACE THAT READS. THE MACHINE CHECKED.",
    "A WIRE UNDER A PART CANNOT BE FIXED LATER.",
    "TWENTY-NINE PINS. ONE KEY. ONE SLOT.",
    "THE BAND IS THE CATHODE. THE CATHODE IS THE LAW.",
    "LOWEST FIRST. TALLEST LAST. GRAVITY APPROVES.",
    "SIX PINS DOWN. ONE MOUTH OUT. NO FLYING LEADS.",
    "METER FIRST. POWER NEVER. NOT TODAY.",
]

# the B2 bus header's spare pins, from B2.md's header table (pins whose line is "not connected")
SPARES = [h.upper() for p, h, l in B.PARTS["XH2"]["pins"] if l == "not connected"]
# the slot key: B2.md's header table ends with the pulled pin's row ("key 28 (28)", hole "none: pulled out ...")
KEYROW = next(r for r in B.PARTS["XH2"]["pins"] if r[0].startswith("key "))
KEY = int(re.search(r"\((\d+)\)", KEYROW[0]).group(1))
FITTED = [r for r in B.PARTS["XH2"]["pins"] if r is not KEYROW]
assert len(FITTED) == 29 and all(h.startswith("j") for _p, h, _l in FITTED), "1x30 less its key pin"
HOW_PULL = KEYROW[1].split(": ", 1)[1].split(";")[0]          # "pulled out of the plastic before fitting (grip ...)"
WHY_KEY = KEYROW[2]                                            # "the slot key: B2's own socket has a key plug in ..."
DOT = next(t for t in B.SNAP if t.startswith("Label it"))      # B2.md section 1 step 4: the colour dot
DOT_COLOUR = re.search(r"a (\w+) paint-pen", DOT).group(1)
KEY_LINE = next(l for l in B.BEFORE if l.startswith("The 1x30 header less its key pin"))
# B2.md section 3's note above the jumper table: the one bare jumper that crosses a bare rail pad
JMP_NOTE = " ".join(ln.strip() for ln in B._sec("Bare jumpers") if ln.strip() and not ln.startswith("|"))
JMP_HOT = int(re.match(r"Jumper (\d+) ", JMP_NOTE).group(1))
JMP_OVER = re.search(r"over hole (F[-+]\d+)", JMP_NOTE).group(1)


def hole(h):
    """B2.md hole -> as printed on the board."""
    if h.startswith("F+"):
        return f"+ RAIL {h[2:]}"
    if h.startswith("F-"):
        return f"− RAIL {h[2:]}"
    return h[0].upper() + h[1:]


def anchor_name(h):
    return h if h.startswith("F") else h[0].upper() + h[1:]


def hole_name(h):
    """A hole in running text: column-J holes that share a jack's name say HOLE."""
    s = hole(h)
    return f"HOLE {s}" if s in ("J14", "J21", "J22") else s


def ring(c, x, y, r=4.2, w=1.6):
    """Hole marker that reads on the red card: hazard yellow on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(HAZ)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def face_tag(c, x, y, face):
    s = "TOP FACE" if face == "top" else "UNDERSIDE"
    w = pdfmetrics.stringWidth(s, "HEAD", 12) + 10
    c.setFillColor(INK)
    c.rect(x, y, w, 17, stroke=0, fill=1)
    text(c, x + 5, y + 4.5, s, 12, "HEAD", HAZ)
    LAB.block(x, y, x + w, y + 17, s)
    return w


def axis_marks(c, a, face, fs=8.5):
    """Row numbers and column letters around a card drawing (the underside has no print to read)."""
    for n in (1, 5, 10, 15, 20, 25, 30):
        x, y = a.A(f"J{n}" if face == "under" else f"A{n}")
        text(c, x, a.y - 8, str(n), fs, "ALT", GREY, "c")
    for L in "ABCDEFGHIJ":
        x, y = a.A(f"{L}1")
        text(c, a.x - 6, y - 3, L, fs, "ALT", GREY, "r")
    LAB.block(a.x - 14, a.y - 11, a.x + a.w, a.y - 1, "axis numbers")


def _halo_line(c, x0, y0, x1, y1):
    c.setStrokeColor(WHITE)
    lw(c, 2.6)
    c.line(x0, y0, x1, y1)
    c.setStrokeColor(INK)
    lw(c, 1.0)
    c.line(x0, y0, x1, y1)


def lanes(c, items, box, size=9, gap=8, color=NEON, font="ALT", ring_r=4.6):
    """Chips in lanes around a drawing. items: [(text, px, py, lane, is_hole)]; lane 'up' / 'dn' (a row of chips
    above / below the drawing, kept in the left-to-right order of their targets and packed without overlap) or
    'lt' / 'rt' (a column beside it, in top-to-bottom order). box = (x0, y0, x1, y1): the lane lines sit just
    outside it. Each leader leaves its chip's inner edge and stops at the hole's ring (is_hole) or at the point."""
    x0b, y0b, x1b, y1b = box
    asc = size * 0.72
    pan = next(p for p in LAB.panels if p[0] <= x0b + 1 and p[2] >= x1b - 1)
    for k in ("up", "dn"):
        its = sorted((px, -py if k == "dn" else py, s_, px, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        wd = [pdfmetrics.stringWidth(s_, font, size) + 5.2 for *_x, s_, _a, _b, _c in its]
        ideal = [px - w_ / 2 for (px, *_r), w_ in zip(its, wd)]
        xs = ideal[:]
        for _ in range(40):
            for n in range(1, len(xs)):
                xs[n] = max(xs[n], xs[n - 1] + wd[n - 1] + gap)
            lo = pan[0] + 6 - xs[0]
            if lo > 0:
                xs = [v + lo for v in xs]
            hi = xs[-1] + wd[-1] - (pan[2] - 6)
            if hi > 0:
                xs = [v - hi for v in xs]
            n = 0
            while n < len(xs):
                m = n
                while m + 1 < len(xs) and abs(xs[m + 1] - (xs[m] + wd[m] + gap)) < 1e-6:
                    m += 1
                d = sum(xs[q] - ideal[q] for q in range(n, m + 1)) / (m - n + 1)
                for q in range(n, m + 1):
                    xs[q] -= d * 0.5
                n = m + 1
        lo = pan[0] + 6 - xs[0]                    # the centring pass may have pulled the row past a panel edge
        if lo > 0:
            xs = [v + lo for v in xs]
        hi = xs[-1] + wd[-1] - (pan[2] - 6)
        if hi > 0:
            xs = [v - hi for v in xs]
        yb = (y1b + 5) if k == "up" else (y0b - 5 - asc)
        for _ in range(3):                         # keep the lane clear of face tags, tables and other blocks
            push = 0.0
            for xa, w_ in zip(xs, wd):
                for q in LAB.blocks:
                    if q[0] < xa + w_ and xa < q[2] and q[1] < yb + asc + 2.6 and yb - 2.6 < q[3]:
                        push = max(push, q[2] + 3 - xa) if (q[0] + q[2]) / 2 < xa + w_ / 2 else min(push, q[0] - 3 - (xa + w_))
            if not push:
                break
            xs = [v + push for v in xs]
        for (_s, _t, s_, px, py, ih), xa, w_ in zip(its, xs, wd):
            r = chip(c, xa + w_ / 2, yb, s_, size, font, color, "c")
            sx, sy = (r[0] + r[2]) / 2, (r[1] if k == "up" else r[3])
            _end(c, r, sx, sy, px, py, ih, ring_r)
    for k in ("lt", "rt"):
        its = sorted((-py, s_, px, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        hgt = asc + 5.2
        ys = [py for *_r, py, _ih in its]
        for _ in range(40):
            for n in range(1, len(ys)):
                ys[n] = min(ys[n], ys[n - 1] - hgt - 3)
        for (_k, s_, px, py, ih), yy in zip(its, ys):
            if k == "lt":
                r = chip(c, x0b - 6, yy - asc / 2, s_, size, font, color, "r")
                sx, sy = r[2], (r[1] + r[3]) / 2
            else:
                r = chip(c, x1b + 6, yy - asc / 2, s_, size, font, color, "l")
                sx, sy = r[0], (r[1] + r[3]) / 2
            _end(c, r, sx, sy, px, py, ih, ring_r)


def _end(c, r, sx, sy, px, py, is_hole, ring_r):
    import math
    if is_hole:
        d = math.hypot(sx - px, sy - py)
        tx, ty = px + (sx - px) / d * ring_r, py + (sy - py) / d * ring_r
    else:
        tx, ty = px, py
        SL.HC.mark(px, py, "leader dot")
    _halo_line(c, sx, sy, tx, ty)
    if not is_hole:
        c.setFillColor(WHITE)
        c.circle(px, py, 2.6, stroke=0, fill=1)
        c.setFillColor(INK)
        c.circle(px, py, 1.6, stroke=0, fill=1)
    LAB.leaders.append((sx, sy, tx, ty, len(LAB.chips) - 1))


def art_box(a, pad=2):
    return (a.x - pad, a.y - pad, a.x + a.w + pad, a.y + a.h + pad)


def short(ln):
    """A B2.md line name, shortened for narrow tables (same words, fewer of them)."""
    return (ln.replace("sensor port ", "port S").replace(" (wind speed)", "").replace(" (wind direction)", "")
            .replace(" at the jack", " (jack side)"))


def pin_rows(ref):
    """B2.md's pin table for ref: [(pin name, hole, line)]."""
    return [(p.split(" (")[0], h, l) for p, h, l in B.PARTS[ref]["pins"]]


def part_table(c, x, ytop, refs, w, size=8.5, note=None):
    """Each part's B2.md pins: REF value, then pin -> hole (as printed) -> line."""
    yy = ytop
    for ref in refs:
        val = B.PARTS[ref]["head"].split(" (")[0]
        text(c, x, yy, ref, 12, "HEAD", INK)
        text(c, x + 34, yy, val.upper(), 9, "ALT", GREY)
        yy -= 11
        for pn, h, ln in pin_rows(ref):
            text(c, x + 4, yy, pn.upper(), size, "ALT", INK)
            text(c, x + 46, yy, hole(h), size + 1, "HEAD", NEON)
            fs = size - 0.5
            ln = short(ln)
            room = w - 92
            while pdfmetrics.stringWidth(ln, "ALT", fs) > room and fs > 6.5:
                fs -= 0.25
            while pdfmetrics.stringWidth(ln, "ALT", fs) > room:
                ln = ln[:-1]
            text(c, x + 92, yy, ln, fs, "ALT", GREY)
            yy -= 10
        if note and ref in note:
            text(c, x + 4, yy, note[ref], size - 0.5, "ALT", INK)
            yy -= 10
        yy -= 5
    LAB.block(x, yy, x + w, ytop + 10, "part table")
    return yy


def ring_holes(c, a, holes):
    for h in holes:
        ring(c, *a.A(anchor_name(h)))



# ------------------------------------------------------------------ text from B2.md
import textwrap  # noqa: E402

GROUPS = json.load(open(SL.SVG / "groups.json"))      # scenes3.py's step grouping (from B2.md + stack), written on render
G = GROUPS["groups"]
JACKS = G["JACKS"]


def cap(*sentences, width=96):
    """Caption lines from sentences (wrapped to the panel)."""
    return textwrap.wrap(" ".join(sentences), width)


def val(ref):
    return B.PARTS[ref]["head"].split(" (")[0]


def fit_of(ref):
    """'R1: + RAIL 5 TO A5' from B2.md's pin table."""
    hs = [hole_name(h) for _p, h, _l in pin_rows(ref)]
    return f"{ref} {hs[0]} TO {hs[1]}" if len(hs) == 2 else f"{ref} {hs[0]}-{hs[-1]}"


def where(ref):
    """B2.md's placement note for ref (the first clause after the colon)."""
    return B.PARTS[ref]["head"].split("): ", 1)[1].split(";")[0]


def jack_name(ref):
    return f"JACK {ref} ({val(ref).replace('RJ11 ', '')})"


def jack_holes(ref):
    hs = [h for _p, h, _l in pin_rows(ref)]
    return hs, f"{hole(hs[0])}-{hole(hs[-1])}"


def hole_lane(a, h, cy):
    """A hole's chip goes above the drawing if the hole is in the drawing's upper half, else below."""
    return "up" if a.A(anchor_name(h))[1] > cy else "dn"


def art_has(a, name):
    return name in a.anchors


# ------------------------------------------------------------------ pages
def cover(c, pg):
    nparts = len(B.PARTS)
    page(c, "00", "SESSION 3: B2 PORTS B + METERS",
         f"ONE CARD. {nparts} PARTS ({len(JACKS)} OF THEM JACKS). {len(B.WIRES)} WIRES UNDER, {len(B.JUMPERS)} JUMPERS. "
         f"NO POWER TODAY.", pg, SLOGANS3[0])
    g = Grid(2, 3, heights=[1.55, 1.05, 0.62])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS FOR B2 PORTS B + METERS. LAY THEM OUT BY REF BEFORE YOU HEAT THE IRON.")
    by_val = {}
    for ref in B.PARTS:
        by_val.setdefault(val(ref), []).append(ref)

    def refs_of(pred):
        return [(v, rs) for v, rs in by_val.items() if pred(rs[0])]
    res = refs_of(lambda r: r.startswith("R"))
    dio = refs_of(lambda r: r.startswith("D"))
    cols = sorted({w_["colour"] for w_ in B.WIRES})
    items = [("B2 CARD\n(back rails snapped)", "p_card"),
             (f"XH2 RIGHT-ANGLE HEADER\n1x30, PIN {KEY} PULLED (SLOT KEY)", "p_header"),
             (f"PER JACK ({len(JACKS)}x): BOB-14021 (BARE,\nTAB ON) + 87180 JACK + 1x6 HEADER", "p_bob"),
             ("\n".join(f"{' '.join(rs)}: {v}" for v, rs in res), "p_res"),
             ("\n".join(f"{v}: {' '.join(rs)}" for v, rs in dio), "p_diode"),
             ("\n".join(f"{v} DISC '104': {' '.join(rs)}" for v, rs in refs_of(lambda r: r.startswith("C"))), "p_cap"),
             ("\n".join(f"{' '.join(rs)} {v} PTC FUSE" for v, rs in refs_of(lambda r: r.startswith("F"))), "p_ptc"),
             (f"BARE TINNED WIRE\n{len(B.JUMPERS)} jumpers", "p_jumper"),
             (f"24 AWG SOLID, INSULATED\n{', '.join(cols)} ({len(B.WIRES)} wires)", "p_wires")]
    cw, rh = w / 3, h / 3
    for i, (name, art) in enumerate(items):
        col, row = i % 3, i // 3
        X, Y = x + cw * col, y + h - rh * (row + 1)
        nl = name.count("\n") + 1
        Art(c, art, X + 6, Y + 14 + 10 * nl, cw - 12, rh - 18 - 10 * nl)
        chip(c, X + cw / 2, Y + 6 + 10 * (nl - 1), name, 7.5, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (24 AWG)", "MULTIMETER (CONTINUITY)",
             f"PLIERS (F4'S LEADS, PULL PIN {KEY})", f"{DOT_COLOUR.upper()} PAINT PEN OR DOT STICKER", "STEEL RULER (WIRE LENGTHS)", "VICE OR CLAMP (SNAP THE TABS)", "SMALL FILE"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 10, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = [(n, t) for n, t in STEP_TITLES if n not in ("00",)]
    for i, (n, s) in enumerate(steps):
        text(c, x + 14, y + h - 14 - i * (h - 8) / len(steps), f"{n}  {s}", 9.5, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["EVERY HOLE IS NAMED AS PRINTED: LETTER = COLUMN (A-J), NUMBER = ROW (1-30). E10 = COLUMN E, ROW 10.",
             "TOP = THE FACE WHERE \"DigiKey\" READS. COLUMN A TOWARD YOU. ROWS 1 TO 30 LEFT TO RIGHT.",
             "JACK J14 / J21 / J22 ARE PARTS. HOLE J14 / J21 / J22 ARE COLUMN-J HOLES. THE SHEET ALWAYS SAYS WHICH.",
             "NO POWER IN THIS SESSION. THE METER IS THE ONLY JUDGE."]
    for i, s in enumerate(rules):
        yy = y + h - 9 - i * (h - 4) / 4
        verdict(c, x + 20, yy, True, 8)
        text(c, x + 34, yy - 3.5, s, 8.2, "ALT", INK)


def know(c, pg):
    page(c, "01", "KNOW THE TWO FACES", "B2 PORTS B + METERS HAS A TOP AND AN UNDERSIDE. EVERY INSTRUCTION NAMES ONE.",
         pg, SLOGANS3[1])
    g = Grid(2, 3, heights=[1.1, 1.1, 0.95])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "TOP FACE: \"DigiKey\" and \"SolderFul BreadBoard\" read correctly, column A toward you, rows 1 to 30",
        "left to right. Columns are LETTERS (A-J), rows NUMBERS (1-30). E10 = column E, row 10 (ringed)."])
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "b2_top", x + 96, y + 24, 330, h - 28, align="l", valign="t")
    px, py = a.A("E10")
    ring(c, px, py)
    lanes(c, [("E10 = COLUMN E, ROW 10", px, py, "dn", True)], (a.x, a.A("fl")[1] - 6, a.x + a.w, a.y + a.h), 10)
    chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "COLUMN A\n(toward you)", 9, "ALT", INK)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "COLUMN J\n(header)", 9, "ALT", INK)
    chip(c, x + 8, y + 20, "FRONT EDGE\n= A SIDE", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, [
        "UNDERSIDE: turn the card over toward you, over its FRONT edge. Now column J is toward you, column A away,",
        "and rows STILL run 1 to 30 left to right. No print here: count from the left end. E10 is ringed."])
    face_tag(c, x + 4, y + h - 40, "under")
    a = Art(c, "b2_under", x + 96, y + 14, 330, h - 40, align="l", valign="b")
    axis_marks(c, a, "under")
    px, py = a.A("E10")
    ring(c, px, py)
    lanes(c, [("E10", px, py, "up", True)], (a.x, a.y, a.x + a.w, a.A("fl")[1] + 4), 10)
    chip(c, a.x + a.w + 10, a.A("J1")[1] - 4, "COLUMN J\n(toward you)", 9, "ALT", INK)
    chip(c, a.x + a.w + 10, a.A("A1")[1] - 4, "COLUMN A\n(away from you)", 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 2), 3, ["B2.md writes holes in lower case:", "e10 = E10. F+5 = + RAIL at row 5",
                                            "(outer front), F-4 = − RAIL, row 4."])
    rows = [("B2.md", "THIS SHEET", "ON THE BOARD"), ("e10", "E10", "column E, row 10"),
            ("i12", "I12", "column I, row 12"), ("F+5", "+ RAIL 5", "outer front rail"),
            ("F-4", "− RAIL 4", "inner front rail"), ("j14", "HOLE J14", "column J, row 14")]
    for i, (a_, b_, c_) in enumerate(rows):
        yy = y + h - 12 - i * 15
        f = "HEAD" if i == 0 else "ALT"
        text(c, x + 32, yy, a_, 9.5, f, GREY if i else INK)
        text(c, x + 70, yy, b_, 9.5, f, NEON if i else INK)
        text(c, x + 134, yy, c_, 8.5, f, INK)
    x, y, w, h = panel(c, g.cell(1, 2), 4, ["Back rails off (B2.md step 1).", "Done in Session 1? Check, go on."],
                       warn=True)
    lines = [ln for s in B.SNAP for ln in textwrap.wrap(s, 50)]
    fs, lead = 8.0, min(10.0, (h - 14) / len(lines))
    for i, s in enumerate(lines):
        text(c, x + 34, y + h - 12 - i * lead, s, fs if lead >= 9 else 7.2, "ALT", INK)


def wire_rows(c, tx, ytop, nums, right):
    for j, n in enumerate(nums):
        wr = B.WIRES[n - 1]
        yy = ytop - j * 46
        c.setFillColor(INS[wr["colour"]])
        c.rect(tx, yy - 26, 6, 34, stroke=0, fill=1)
        text(c, tx + 12, yy, f"{n}  {hole(wr['a'])} TO {hole(wr['b'])}", 11.5, "HEAD", INK)
        text(c, tx + 12, yy - 12, f"{wr['length'].upper()} · {wr['colour'].upper()}", 8.5, "ALT", INK)
        what = short(wr["line"]).upper()
        text(c, tx + 12, yy - 23, what[:34], 8, "ALT", GREY)
        LAB.block(tx, yy - 27, right, yy + 10, f"row {n}")


def wires_panel(c, cell, k, nums, first):
    if first:
        cp = cap(f"B2, UNDERSIDE (column J toward you). Wires {nums[0]}-{nums[-1]} of {len(B.WIRES)}.",
                 "Cut each to the length shown (route + 10 mm), strip 3 mm at both ends, lay it flat on the drawn route,",
                 "bends square. Push each end through its hole from the UNDERSIDE, solder it on the TOP, trim.")
    else:
        cp = cap(f"B2, UNDERSIDE. Wires {nums[0]}-{nums[-1]}. Grey = wires already in. Same method: cut, strip,",
                 "route flat on its own drawn path, ends through from the underside, solder on the top, trim.")
    x, y, w, h = panel(c, cell, k, cp)
    a = Art(c, f"u{UG.index(nums) + 1}", x + 14, y + 40, 330, h - 72, align="l", valign="b")
    axis_marks(c, a, "under")
    tx = a.x + a.w + 10
    face_tag(c, tx, y + h - 22, "under")
    wire_rows(c, tx, y + h - 50, nums, x + w)
    items = []
    cy = a.A("E1")[1]
    for n in nums:
        wr = B.WIRES[n - 1]
        for hn in (wr["a"], wr["b"]):
            px, py = a.A(anchor_name(hn))
            ring(c, px, py)
            items.append((f"{n}: {hole(hn)}", px, py, "up" if py > cy else "dn", True))
    yt = a.A("fl")[1]
    lanes(c, items, (a.x, a.y - 12, a.x + a.w, yt + 4), size=8.5)


def wires_page(c, pg, part):
    groups = UG[2 * (part - 1): 2 * part]
    page(c, "02", f"{len(B.WIRES)} WIRES ON THE UNDERSIDE  {part}/{(len(UG) + 1) // 2}",
         "24 AWG SOLID INSULATED. B2 UNDERSIDE. THEY GO FIRST: PARTS COVER THESE HOLES LATER.", pg, SLOGANS3[2])
    g = Grid(1, 2)
    for k, nums in enumerate(groups):
        wires_panel(c, g.cell(0, k), k + 1, nums, part == 1 and k == 0)
    if len(groups) == 1:                       # the last page's spare panel: every wire at a glance
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(f"All {len(B.WIRES)} underside wires, B2.md order. Tick each one when its "
                                                   "two ends are soldered and trimmed."))
        text(c, x + 30, y + h - 40, "#   FROM     TO        CUT               COLOUR   LINE", 8.5, "MONO", GREY)
        step = min(17.0, (h - 60) / len(B.WIRES))
        for i, wr in enumerate(B.WIRES):
            yy = y + h - 58 - i * step
            c.setFillColor(INS[wr["colour"]])
            c.rect(x + 8, yy - 2, 16, 9, stroke=0, fill=1)
            text(c, x + 30, yy, str(wr["n"]), 10, "HEAD", INK)
            text(c, x + 50, yy, hole(wr["a"]), 10, "HEAD", NEON)
            text(c, x + 96, yy, hole(wr["b"]), 10, "HEAD", NEON)
            text(c, x + 150, yy, wr["length"].upper(), 8.5, "ALT", INK)
            text(c, x + 250, yy, wr["colour"].upper(), 8.5, "ALT", INK)
            text(c, x + 300, yy, short(wr["line"])[:40], 8, "ALT", INK)
            c.setStrokeColor(NEON)
            lw(c, 1.2)
            c.rect(x + w - 22, yy - 2, 10, 10, stroke=1, fill=0)
        LAB.block(x + 6, y + h - 58 - len(B.WIRES) * step, x + w, y + h - 30, "wire table")


def jumpers(c, pg):
    page(c, "03", f"{len(B.JUMPERS)} BARE JUMPERS ON TOP", "TINNED BARE WIRE. B2 TOP FACE. LOW BRIDGES, 1 MM OVER THE CARD.",
         pg, SLOGANS3[2])
    g = Grid(1, 2, heights=[1.6, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        f"B2, TOP FACE. {len(B.JUMPERS)} bare jumpers, each between the two holes in the table. Cut the length shown,",
        "bend a U to the hole spacing, legs down through both holes from the TOP, bridge 1 mm above the card,",
        "solder on the UNDERSIDE, trim. Jumper numbers are drawn at each bridge. Jumper 4 is different: see the red note."))
    face_tag(c, x + 30, y + h - 22, "top")
    a = Art(c, "t_jumpers", x + 14, y + 30, 340, h - 62, align="l", valign="c")
    holes = [hh for j in B.JUMPERS for hh in (j["a"], j["b"])]
    ring_holes(c, a, holes)
    cy = a.A("E1")[1]
    items = []
    for j in B.JUMPERS:
        pa, pb = a.A(anchor_name(j["a"])), a.A(anchor_name(j["b"]))
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        items.append((f"JMP{j['n']}", mx, my, "up" if my > cy else "dn", False))
    lanes(c, items, (a.x, a.y, a.x + a.w, a.y + a.h))
    tx = a.x + a.w + 12
    for i, j in enumerate(B.JUMPERS):
        yy = y + h - 44 - i * 30
        text(c, tx, yy, f"JMP{j['n']}  {hole(j['a'])} TO {hole(j['b'])}", 10.5, "HEAD", INK)
        if j["n"] == JMP_HOT:
            text(c, tx, yy - 11, f"{j['length'].upper()} · SLEEVE IT OR ARCH IT CLEAR OF {hole(JMP_OVER)}", 8, "HEAD", RED)
        else:
            text(c, tx, yy - 11, f"{j['length'].upper()} BARE · {j['line'].upper()}", 8, "ALT", GREY)
    LAB.block(tx, y + h - 44 - (len(B.JUMPERS) - 1) * 30 - 16, x + w, y + h - 34, "jumper table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap("What each jumper ties (B2.md). Each bridge lies flat, 1 mm over the card."))
    yy = y + h - 16
    for j in B.JUMPERS:
        text(c, x + 40, yy, f"JMP{j['n']}", 10, "HEAD", INK)
        text(c, x + 82, yy, f"{hole(j['a'])} TO {hole(j['b'])}", 9.5, "HEAD", NEON)
        for k_, ln in enumerate(textwrap.wrap(j["what"], 58)):
            text(c, x + 190, yy - 10 * k_, ln, 8.6, "ALT", INK)
        yy -= 10 * max(1, len(textwrap.wrap(j["what"], 58))) + 9
    LAB.block(x + 38, yy, x + w, y + h - 4, "jumper what")
    for k_, ln in enumerate(textwrap.wrap("WATCH OUT: " + re.sub(r"\b([a-j]\d+|F[-+]\d+)\b", lambda m: hole(m.group(1)), JMP_NOTE), 110)):
        text(c, x + 40, yy - 4 - 10 * k_, ln, 8.6, "HEAD", RED)
    LAB.block(x + 38, yy - 4 - 10 * k_ - 3, x + w, yy + 6, "jumper warning")


def header(c, pg):
    page(c, "04", "BUS HEADER XH2, COLUMN J",
         f"GENERIC RIGHT-ANGLE MALE HEADER, CUT TO 1x30. PIN {KEY} PULLED: THE SLOT KEY. {DOT_COLOUR.upper()} DOT ON THE FRONT.",
         pg, SLOGANS3[3])
    g = Grid(1, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        f"B2, TOP FACE. Short legs down through HOLES J1 to J30 (column J, rows 1-30), from the top: every hole in column J",
        f"takes a pin except HOLE J{KEY}, which stays empty (pin {KEY} pulled: the slot key). The long pins point AWAY",
        "from column A, out past the snapped back edge (toward the backplane). Solder on the UNDERSIDE: J1 first, check",
        f"it sits flat and square, then J30, then the rest. {DOT}"))
    face_tag(c, x + 4, y + h - 40, "top")
    a = Art(c, "t_header", x + 96, y + 4, 330, h - 8, align="l")
    ring_holes(c, a, ["j1", f"j{KEY}", "j30"])
    box = (a.x, a.y, a.x + a.w, a.y + a.h)
    lanes(c, [("HOLE J1: PIN 1", *a.A("J1"), "lt", True)], box)
    lanes(c, [(f"HOLE J{KEY}: EMPTY (KEY)", *a.A(f"J{KEY}"), "up", True)], (a.x, a.y, a.x + a.w, a.A("J1")[1] + 8))
    lanes(c, [("HOLE J30: PIN 30", *a.A("J30"), "rt", True)], box)
    dx_, dy_ = a.A("keydot")
    label(c, x + 8, dy_ + 16, f"{DOT_COLOUR.upper()} DOT:\nB2'S COLOUR", dx_ - 3, dy_ + 1, 9, "ALT", NEON, lcolor=INK, dot=False)
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
        f"Cut 1x30 from a longer strip: pull the 31st pin, cut through its empty place, file flat. Then pin {KEY}:",
        f"{HOW_PULL}. Why: {WHY_KEY}. B2.md, pin by pin: pin n carries backplane bus line n."))
    hd = Art(c, "p_header", x + 30, y + 70, 220, h - 80, align="c", valign="c")
    ring(c, *hd.A("p1"), r=4.0)
    ring(c, *hd.A("p30"), r=4.0)
    kx, ky = hd.A("key_pin")
    label(c, kx - 30, hd.y + hd.h + 2, f"PIN {KEY}: OUT", kx, ky, 9, "ALT", NEON, "r", lcolor=INK, dot=False)
    rows = FITTED + [KEYROW]
    cx0 = x + 262
    colw = (x + w - cx0) / 2
    for i, (p, hh, ln) in enumerate(rows):
        col, r_ = divmod(i, 15)
        xx, yy = cx0 + col * colw, y + h - 12 - r_ * 10.6
        if p is KEYROW[0]:
            text(c, xx, yy, f"J{KEY}", 8.5, "HEAD", NEON)
            text(c, xx + 26, yy, "PULLED: THE SLOT KEY", 7.8, "HEAD", INK)
            continue
        text(c, xx, yy, f"{hole(hh)}", 8.5, "HEAD", NEON)
        sh = (ln.replace("sensor port ", "S").replace(" (SDA)", " SDA").replace(" (SCL)", " SCL")
              .replace("(wind speed) ", "").replace("(wind direction) ", "")
              .replace("spare bus line (for the charger interrupt)", "spare bus line"))
        text(c, xx + 26, yy, sh, 7.8, "ALT", INK if ln != "not connected" else GREY)
    LAB.block(cx0, y + h - 12 - 14 * 10.6 - 4, x + w, y + h - 2, "pin table")
    text(c, x + 14, y + 36, f"1x30 LESS PIN {KEY}: 29 PINS, HOLE J{KEY} EMPTY.", 11, "HEAD", INK)
    text(c, x + 14, y + 22, f"SPARES (FITTED, NO NET): {', '.join(SPARES)}.", 8, "ALT", INK)


# --------------------------------------------- parts pages: full top view + close-up + B2.md pin table
def part_lane(ref, a, mid):
    return "up" if a.A("@" + ref)[1] > mid else "dn"


def parts_page(c, pg, step, title, sub, slogan, refs, top, cap1, cap2, close=None, close_items=None, notes=None,
               h1=1.15):
    page(c, step, title, sub, pg, slogan)
    g = Grid(1, 2, heights=[h1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap1)
    face_tag(c, x + 30, y + h - 22, "top")
    a = Art(c, top, x + 14, y + 26, 340, h - 52, align="l", valign="c")
    holes = [hh for r in refs for _p, hh, _l in pin_rows(r)]
    ring_holes(c, a, holes)
    mid = a.A("E1")[1]
    items = [(r, *a.A("@" + r), part_lane(r, a, mid), False) for r in refs]
    lanes(c, items, (a.x, a.y, a.x + a.w, a.y + a.h))
    part_table(c, a.x + a.w + 10, y + h - 18, refs, x + w - (a.x + a.w + 10), note=notes)
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap2)
    if close:
        b = Art(c, close, x + 20, y + 24, w - 40, h - 48)
        close_items(c, b)
    return a


def ring_lanes(c, b, holes):
    """Ring every hole of a close-up and name it in a lane above or below (by the hole's height on the page)."""
    cy = b.y + b.h / 2
    items = []
    for hh in holes:
        px, py = b.A(anchor_name(hh))
        ring(c, px, py)
        items.append((hole_name(hh), px, py, "up" if py > cy else "dn", True))
    lanes(c, items, art_box(b))


def holes_of(refs):
    return [hh for r in refs for _p, hh, _l in pin_rows(r)]


def fits_sentence(refs):
    return "; ".join(fit_of(r) for r in refs) + "."


def pullups(c, pg):
    refs = G["RPULL"]
    parts_page(c, pg, "05", "PULL-UPS " + " ".join(refs), f"{val(refs[0]).upper()}, 1 %, BLUE BODY: BROWN-BLACK-BLACK-RED-BROWN. LYING FLAT.",
               SLOGANS3[5], refs, "t_rpull",
               cap("B2, TOP FACE. Each pull-up lies flat between its two holes: leads bent down at the body ends, body",
                   "touching the card. " + fits_sentence(refs), "No polarity. Solder on the UNDERSIDE, trim."),
               cap("Close-up, straight down, every hole ringed. " + " ".join(f"{r}: {where(r)}." for r in refs)),
               "z_rpull", lambda c, b: ring_lanes(c, b, holes_of(refs)))


def series(c, pg):
    refs = G["RSER"]
    vals = {}
    for r in refs:
        vals.setdefault(val(r), []).append(r)
    bands = {"1k": "BROWN-BLACK-RED-GOLD", "100": "BROWN-BLACK-BROWN-GOLD"}
    parts_page(c, pg, "06", "SERIES " + " ".join(refs), "ACROSS THE CENTRE CHANNEL, COLUMN E TO COLUMN F. LYING FLAT.",
               SLOGANS3[5], refs, "t_rser",
               cap("B2, TOP FACE. Each resistor lies flat across the centre channel. " +
                   " ".join(f"{v} ({bands.get(v, '')}): {' '.join(rs)}." for v, rs in vals.items()),
                   "1k and 100 look alike: check the third band. " + fits_sentence(refs) + " Solder on the UNDERSIDE, trim."),
               cap("Close-up, straight down. " + " ".join(f"{r}: {where(r)}." for r in refs if "slant" in where(r)) +
                   " The column-F ends are the bus side of each strip, the column-E ends the jack side."),
               "z_rser", lambda c, b: ring_lanes(c, b, holes_of(refs)))


def caps(c, pg):
    refs = G["CAPS"]

    def close(c, b):
        lanes(c, [(f"{r}: {val(r).upper()}, MARKED 104", *b.A(f"{r}_face"), "up", False) for r in refs], art_box(b, -4))
    parts_page(c, pg, "07", "FILTER DISCS " + " ".join(refs), "100 nF CERAMIC DISCS, MARKED 104. STANDING.",
               SLOGANS3[5], refs, "t_caps",
               cap("B2, TOP FACE. Each disc stands on two neighbouring holes in one column: one on the jack line, one on a",
                   "ground strip. " + fits_sentence(refs), f"Push down until the coating just clears the card "
                   f"(top {B.top_mm(refs[0])} mm). No polarity. Solder on the UNDERSIDE, trim."),
               cap("From the front-left. " + " ".join(f"{r}: {where(r)}." for r in refs)),
               "i_caps", close)


def band_word(ref):
    return "BAND DOWN (BODY ON CATHODE)" if pin_rows(ref)[0][0] == "cathode" else "BAND UP (BODY ON ANODE)"


def diode_page(c, pg, step, key, title, sub, slogan):
    refs = G[key]
    page(c, step, title, sub, pg, slogan)
    g = Grid(2, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, cap(
        "B2, TOP FACE. Each diode stands with its BODY on its FIRST hole and the other lead looped over into the",
        "second. The band is the cathode: " + "; ".join(f"{r} body on {hole_name(pin_rows(r)[0][1])}, "
                                                       f"{band_word(r).split(' (')[0].lower()}" for r in refs) + ".",
        "Solder on the UNDERSIDE, trim."))
    face_tag(c, x + 30, y + h - 22, "top")
    a = Art(c, f"t_{key.lower()}", x + 14, y + 26, 340, h - 52, align="l", valign="c")
    holes = holes_of(refs)
    ring_holes(c, a, holes)
    mid = a.A("E1")[1]
    lanes(c, [(r, *a.A("@" + r), part_lane(r, a, mid), False) for r in refs], (a.x, a.y, a.x + a.w, a.y + a.h))
    part_table(c, a.x + a.w + 10, y + h - 18, refs, x + w - (a.x + a.w + 10), size=8,
               note={r: band_word(r) for r in refs})
    cx, cy, cw_, ch = g.cell(0, 1, 2)
    wl = cw_ * 0.4
    x, y, w, h = panel(c, (cx, cy, wl - 5, ch), 2, ["Straight down: every hole", "of these diodes, as printed."])
    b = Art(c, f"z_{key.lower()}", x + 16, y + 22, w - 32, h - 50)
    ring_lanes(c, b, holes)
    sides = [s for s in "pq" if (SL.SVG / f"i_{key.lower()}_{s}.json").exists()]
    x, y, w, h = panel(c, (cx + wl + 5, cy, cw_ - wl - 5, ch), 3, [
        "The bands, from where each one shows: " + " / ".join({"p": "front-left", "q": "behind-left"}[s] for s in sides) + ".",
        "Band = cathode. Tick each before you solder."])
    for k, s in enumerate(sides):
        hh = (h - 30) / len(sides)
        yb = y + h - 30 - hh * (k + 1)
        tag = "FROM THE FRONT" if s == "p" else "FROM BEHIND"
        text(c, x + 40, yb + hh + 14, tag, 8, "HEAD", GREY)
        LAB.block(x + 38, yb + hh + 10, x + 42 + pdfmetrics.stringWidth(tag, "HEAD", 8), yb + hh + 23, "tag")
        b = Art(c, f"i_{key.lower()}_{s}", x + 6, yb + 16, w - 12, hh - 18)
        its = [(f"{r} BAND", *b.A(f"{r}_band{s}"), "up" if k == 0 else "dn", False) for r in refs
               if art_has(b, f"{r}_band{s}")]
        lanes(c, its, art_box(b, -4), size=8)


def s4diodes(c, pg):
    diode_page(c, pg, "08", "S4D", "PORT S4 DIODES " + " ".join(G["S4D"]),
               "ONE ZENER (SUPPLY CLAMP), FOUR SCHOTTKY CLAMPS. STANDING. WATCH EVERY BAND.", SLOGANS3[4])


def zeners(c, pg):
    diode_page(c, pg, "09", "ZEN", "METER ZENERS " + " ".join(G["ZEN"]),
               "1N5232B, 5.6 V. STANDING. BAND (CATHODE) DOWN, ON THE JACK LINE.", SLOGANS3[4])


def fuse(c, pg):
    refs = G["F4"]

    def close(c, b):
        lanes(c, [(f"{r}: MF-R010 (R010 MARKING)", *b.A(f"{r}_face"), "lt", False) for r in refs], art_box(b, -4))
    parts_page(c, pg, "10", "PORT S4 FUSE " + " ".join(refs), "BOURNS MF-R010, 100 mA PTC. STANDING, LEADS FORMED OUT TO 7.62 MM.",
               SLOGANS3[5], refs, "t_f4",
               cap("B2, TOP FACE. Bend the two leads out with pliers so they land 7.62 mm apart (three holes), then stand",
                   "it: " + fits_sentence(refs), f"Flat faces along the row. Top {B.top_mm(refs[0])} mm. "
                   "No polarity. Solder on the UNDERSIDE, trim."),
               cap("From the front-left. Its leads go only into the two holes named; the − RAIL hole between stays empty."),
               "i_f4", close, h1=1.1)


def prep_jacks(c, pg):
    page(c, "11", f"BUILD THE {len(JACKS)} JACK BREAKOUTS",
         "BOB-14021 (BARE BOARD) + 87180-066LF JACK + 1x6 HEADER, " +
         f"{len(JACKS)} TIMES: " + ", ".join(JACKS) + ".", pg, SLOGANS3[5])
    g = Grid(2, 2, heights=[1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["AS SUPPLIED: three parts per jack.", "BOB-14021 is a bare board with a",
                                            "snap-off tab; jack and header loose."])
    a = Art(c, "p_bob_kit", x + 6, y + 6, w - 12, h - 12)
    lanes(c, [("87180 JACK", *a.A("jack"), "lt", False), ("SNAP-OFF TAB", *a.A("tab"), "rt", False),
              ("V-SCORE", *a.A("score"), "rt", False), ("1x6 HEADER", *a.A("hdr"), "lt", False)], art_box(a, -6), size=8.5)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["1  SNAP THE TAB OFF: clamp the board along",
                                            "the V-score, bend once. File the edge flat.",
                                            "Board 15.24 mm wide (the header's length)."])
    a = Art(c, "p_bob_snap", x + 10, y + 50, w - 90, h - 56, align="l")
    lanes(c, [("TAB: OFF", *a.A("tab"), "rt", False), ("V-SCORE", *a.A("score_top"), "up", False)], art_box(a, -6),
          size=8.5)
    why = "Left on, each tab would land on a neighbour: " + "; ".join(
        f"{r}'s on {' '.join(GROUPS['tab_hits'][r])}" for r in JACKS if GROUPS["tab_hits"][r]) + "."
    for i, s in enumerate(textwrap.wrap(why, 52)[:3]):
        text(c, x + 10, y + 34 - i * 10, s, 8.0, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 3, ["2  JACK on the board's top: pegs in the two big",
                                            "holes, pins in the six small ones (one way only).",
                                            "Solder the pins underneath, CUT THEM FLUSH.",
                                            "3  HEADER: plastic under the board, short ends",
                                            "up through the six pads, solder on top."])
    a = Art(c, "p_bob_ready", x + 70, y + 6, w - 160, h - 12)
    lanes(c, [("JACK PINS: FLUSH", *a.A("jfil"), "rt", False), ("PEG", *a.A("peg"), "lt", False),
              ("1x6 PLASTIC", *a.A("hdr_bot"), "lt", False), ("LONG ENDS", *a.A("hpin_lo"), "rt", False)],
          art_box(a, -6), size=8.5)
    x, y, w, h = panel(c, g.cell(1, 1), 4, ["Done, from above the pad row. Flush jack pins:",
                                            "they stand 2.5 mm over the + and − RAILS.",
                                            f"Build all {len(JACKS)} the same."], warn=True)
    a = Art(c, "p_bob_top", x + 60, y + 6, w - 160, h - 12)
    lanes(c, [("HEADER SOLDERED", *a.A("hfil"), "rt", False),
              ("87180 JACK", *a.A("jack"), "lt", False)], art_box(a, -6), size=8.5)


def fit_jacks(c, pg):
    page(c, "12", f"FIT THE {len(JACKS)} JACKS IN COLUMN A", "EACH BREAKOUT ON ITS 1x6 HEADER. MOUTH TO THE FRONT EDGE. "
         "TALLEST PARTS: LAST.", pg, SLOGANS3[5])
    g = Grid(1, 2, heights=[1.45, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "B2, TOP FACE. Each breakout's header long ends go down through six column-A holes from the TOP, jack mouth",
        "toward the FRONT edge (the board overhangs it). " + "; ".join(f"{jack_name(r)} in {jack_holes(r)[1]}"
                                                                     for r in JACKS) + ". Contact 1 at the LEFT hole.",
        "Hold the board level, solder one end pin on the UNDERSIDE, check, then the other five; trim."))
    face_tag(c, x + 30, y + h - 22, "top")
    a = Art(c, "t_f4", x + 14, y + 26, 340, h - 52, align="l", valign="c")
    items = []
    for r in JACKS:
        hs, span = jack_holes(r)
        ring_holes(c, a, hs)
        p1, p6 = a.A(anchor_name(hs[0])), a.A(anchor_name(hs[-1]))
        items.append((f"{r}: {span}", (p1[0] + p6[0]) / 2, p1[1], "dn", False))
    lanes(c, items, (a.x, a.y, a.x + a.w, a.y + a.h), size=8.5)
    tx = a.x + a.w + 10
    yy = y + h - 20
    for i, s in enumerate(["CONTACT n = HEADER PIN n.", "PIN 1 = THE LEFT-MOST HOLE", "(LOWEST ROW NUMBER).", "",
                           "MOUTH: TOWARD COLUMN A AND", "PAST THE FRONT EDGE.", "", "THE BOARD COVERS THE",
                           "+ AND − RAILS UNDER IT:", "NOTHING IS SOLDERED THERE."]):
        text(c, tx, yy - i * 11, s, 8.2, "ALT", INK)
    LAB.block(tx, yy - 10 * 11, x + w, yy + 10, "notes")
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap("B2.md pin tables: every contact, its hole and its line. Contacts "
                                               "marked NOT CONNECTED still get their header pin soldered."))
    cw = (w - 16) / len(JACKS)
    for k, r in enumerate(JACKS):
        xx = x + 8 + k * cw
        yy = y + h - 44
        text(c, xx, yy, jack_name(r), 11, "HEAD", INK)
        yy -= 16
        for pn, hh, ln in pin_rows(r):
            text(c, xx, yy, pn.replace("contact ", "C").upper(), 9, "HEAD", INK)
            text(c, xx + 22, yy, hole(hh), 10, "HEAD", NEON)
            s_ = short(ln)
            fs = 7.6
            while pdfmetrics.stringWidth(s_, "ALT", fs) > cw - 60 and fs > 6.4:
                fs -= 0.2
            text(c, xx + 52, yy, s_, fs, "ALT", GREY if ln == "not connected" else INK)
            yy -= 15
        LAB.block(xx, yy, xx + cw - 4, y + h - 32, f"table {r}")


def jacks_done(c, pg):
    page(c, "13", f"THE {len(JACKS)} JACKS, FITTED", "CHECK THEM AGAINST THESE TWO VIEWS BEFORE THE METER.", pg,
         SLOGANS3[5])
    g = Grid(1, 2, heights=[1.1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "B2, TOP FACE, all parts in. The breakouts sit side by side along column A, boards over the front rails, jacks",
        "overhanging the front edge. Each header's soldered short ends show in the pad row behind its jack."))
    face_tag(c, x + 30, y + h - 22, "top")
    a = Art(c, "t_jacks", x + 14, y + 26, 360, h - 52, align="l", valign="c")
    items = [(jack_name(r), *a.A(f"{r}_jack"), "dn", False) for r in JACKS]
    items += [(f"{r} C1", *a.A(f"{r}_hfil"), "up", False) for r in JACKS]
    lanes(c, items, (a.x, a.y, a.x + a.w, a.y + a.h), size=8.5)
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap("From the front-left: every mouth faces the front edge, the plug goes in "
                                               "from the lid side. Nothing else on B2 stands as tall."))
    b = Art(c, "i_jacks", x + 20, y + 22, w - 40, h - 40)
    lanes(c, [(f"{r} MOUTH", *b.A(f"{r}_mouth"), "up", False) for r in JACKS], art_box(b, -6), size=8.5)


def strip_map(c, pg):
    page(c, "14", "STRIP MAP", "WHAT EVERY USED STRIP OF B2 CARRIES (B2.md STRIP MAP). THE METER CHECKS THIS NEXT.", pg,
         SLOGANS3[7])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), None, [
        "Columns A-E of a row are one strip; columns F-J of the same row are another. Rails run the full length.",
        "Each strip carries one line only."])
    rows = B.STRIPS
    half = (len(rows) + 1) // 2
    cw = (w - 20) / 2
    pitch = min(22.5, (h - 16) / half)
    for i, (strip, line, used) in enumerate(rows):
        col, r = divmod(i, half)
        xx, yy = x + 10 + col * cw, y + h - 12 - r * pitch
        if strip.startswith("rail "):
            st_ = {"F+": "+ RAIL", "F-": "− RAIL"}[strip.split()[1]]
        else:
            st_ = strip.replace(", columns ", " ").upper()
        text(c, xx, yy, st_, 9, "HEAD", NEON)
        ln = short(line)
        fs = 8.2
        while pdfmetrics.stringWidth(ln, "ALT", fs) > cw - 70 and fs > 6.5:
            fs -= 0.2
        text(c, xx + 64, yy, ln, fs, "ALT", INK if "nothing" not in line else GREY)
        u = used
        for k_, v in (("F+", "+RAIL "), ("F-", "−RAIL ")):
            u = u.replace(k_, v)
        fs = 7.2
        while pdfmetrics.stringWidth(u, "ALT", fs) > cw - 70 and fs > 6.0:
            fs -= 0.2
        text(c, xx + 64, yy - 8.5, u, fs, "ALT", GREY)


def checks(c, pg):
    page(c, "15", "METER BEFORE POWER", "CONTINUITY MODE. B2 ALONE ON THE BENCH. NOTHING PLUGGED IN.", pg, SLOGANS3[7])
    g = Grid(1, 2, heights=[0.85, 1.25])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["B2 PORTS B + METERS, finished, from the front-left. Do the checks below in order."])
    Art(c, "t_final", x + 4, y + 4, w - 8, h - 8)
    grounds = []
    for r in JACKS:
        cs = [pn.replace("contact ", "") for pn, _h, ln in pin_rows(r) if ln == "ground"]
        grounds.append(f"{r} C{'+C'.join(cs)}")
    rows = [("1", "NEIGHBOURS", B.BEFORE[0]), ("2", "3.3 V vs GROUND", B.BEFORE[1]),
            ("3", "HEADER PINS", B.BEFORE[2].replace("Jn", "HOLE Jn").replace("Fn", "HOLE Fn")),
            ("4", "GROUND PINS", B.BEFORE[3].replace("Header pins J2, J12", "The header pins in HOLES J2 and J12")),
            ("5", f"KEY PIN {KEY}", KEY_LINE.replace(f"hole j{KEY}", f"HOLE J{KEY}")),
            ("6", "JACK GROUNDS", "On the UNDERSIDE, each jack's ground header pin beeps to the − RAIL: " +
             ", ".join(grounds) + ".")]
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Any beep where it says no continuity, or silence where it says beep: stop.",
                                            "Photograph it. Report to Claude."], warn=True)
    yy = y + h - 46
    for n, t, s in rows:
        badge(c, x + 22, yy + 4, n, 10)
        text(c, x + 40, yy, t, 11.5, "HEAD", INK)
        lines = textwrap.wrap(s, 62)
        for k, ln in enumerate(lines):
            text(c, x + 170, yy + 1 - 11 * k, ln, 8.6, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 24, yy - 4, 14, 14, stroke=1, fill=0)
        yy -= max(2, len(lines)) * 11 + 16
    assert len(B.BEFORE) == 5, B.BEFORE        # rows 1-5 are B2.md's "Before power"; row 6 is this sheet's addition


def built_page(c, pg):
    import builtpage
    builtpage.built(c, pg, SL, "00", SLOGANS3[0])


def _wrap(fn):
    def f(c, pg):
        c_glob[0] = c
        fn(c, pg)
    return f


c_glob = [None]
UG = GROUPS["ugroups"]
NWP = (len(UG) + 1) // 2
STEP_TITLES = [("01", "KNOW THE TWO FACES"), ("02", f"{len(B.WIRES)} WIRES ON THE UNDERSIDE"),
               ("03", f"{len(B.JUMPERS)} BARE JUMPERS"), ("04", f"BUS HEADER XH2 (PIN {KEY} OUT), {DOT_COLOUR.upper()} DOT"),
               ("05", "PULL-UPS " + " ".join(G["RPULL"])), ("06", "SERIES " + " ".join(G["RSER"])),
               ("07", "DISCS " + " ".join(G["CAPS"])), ("08", "PORT S4 DIODES " + G["S4D"][0] + "-" + G["S4D"][-1]),
               ("09", "ZENERS " + " ".join(G["ZEN"])), ("10", "FUSE " + " ".join(G["F4"])),
               ("11", f"BUILD THE {len(JACKS)} JACK BREAKOUTS"), ("12", "FIT THE JACKS IN COLUMN A"),
               ("13", "THE JACKS, FITTED"), ("14", "STRIP MAP"), ("15", "METER BEFORE POWER")]

PAGES = [("00-cover", [cover]), ("00-what-you-are-building", [built_page]), ("01-know-the-faces", [know]),
         ("02-underside-wires", [lambda c, pg, k=k: wires_page(c, pg, k) for k in range(1, NWP + 1)]),
         ("03-jumpers", [jumpers]), ("04-bus-header", [header]),
         ("05-pullups", [pullups]), ("06-series", [series]), ("07-discs", [caps]), ("08-s4-diodes", [s4diodes]),
         ("09-zeners", [zeners]), ("10-fuse", [fuse]), ("11-build-jacks", [prep_jacks]), ("12-fit-jacks", [fit_jacks]),
         ("13-jacks-fitted", [jacks_done]), ("14-strip-map", [strip_map]), ("15-meter-checks", [checks])]

HOLE_ISSUES = []


def build(path, fns, start=1, report=False):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 3: build B2 PORTS B + METERS")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        _wrap(fn)(cv, start + i)
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
    import os
    only = os.environ.get("S3_ONLY")          # review aid: S3_ONLY=00,01,02 builds just those pages to a scratch file
    allfns = [f for _n, fns in PAGES for f in fns if not only or _n[:2] in only.split(",")]
    dest = OUT / ("session3-all.pdf" if not only else "session3-partial.pdf")
    bad = build(dest, allfns, 1, report=True)
    print("ok", len(allfns), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if HOLE_ISSUES or bad:
        sys.exit("BUILD FAILED: label or hole-callout issues")
