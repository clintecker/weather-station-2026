"""Session P: build the three pod boards (TH, BARO, UV) and the port cable. The TX sheets' flat-pack style and pipeline:
illustrations rendered from real 3D geometry by scenes_p.py (svg/*.svg + anchors in svg/*.json), every label on a paper
chip whose leader stops at the chip edge, and the TX label-overlap and hole-callout checks run on every page.

Source of truth (read-only): layout/pods.py (every part, pin hole, wire, route and the TH lead), layout/permaproto.py
(holes, strips), layout/pod_checks.py (the copper netlist the strip maps and meter checks are built from; the cable map
that says what a reversed cable does), sources.py (part values). Nothing about holes, nets or wire ends is typed here.

Hole names are the ones printed on the Perma-Proto Quarter #1608: row letter A-J + column number 1-15 (F10 = row F,
column 10). The four rails carry no printed name, only a red line (+) or a blue line (-) beside them; this sheet names
them BOT+ (outer, along the bottom edge, red line), BOT- (inner, blue line), TOP+ (inner, red line) and TOP- (outer,
along the top edge, blue line), each with the column: TOP-8.

Usage: $PDFPY make_session_p.py OUT_DIR      (render first: sh render_all.sh; or sh build.sh)
Writes OUT_DIR/session-p-pods.pdf and OUT_DIR/session-p-manifest.json; exits non-zero on any label or hole issue.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

SHEETS_DIR = Path(__file__).resolve().parent
PODS = SHEETS_DIR.parent
REPO = PODS.parent.parent
TXS = REPO / "hardware" / "tx-stack-r1" / "sheets"
for p in (TXS / "session3", TXS / "session1" / "v2", PODS / "layout", PODS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
sys.dont_write_bytecode = True

from sheetlib import *          # noqa: F401,F403,E402  (TX page furniture, chips, leaders, Art, checks; read-only)
import sheetlib as SL           # noqa: E402
import pods as PD               # noqa: E402
import permaproto as PPM        # noqa: E402
import pod_checks as PC         # noqa: E402
import sources as S             # noqa: E402

SL.SVG = SHEETS_DIR / "svg"
SL.PROTO = "PROTOCOL P // SESSION P // POD BOARDS + PORT CABLE"
SL.LEADER_INK = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else SHEETS_DIR / "out"
INSC = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
        "blue": HexColor("#2D6FD0"), "green": HexColor("#2E9A48")}
NETC = {"3V3": INSC["red"], "GND": INSC["black"], "SCL": INSC["yellow"], "SDA": INSC["blue"], "WP": INSC["green"]}
NET_WORD = {"3V3": "3.3 V", "GND": "GROUND", "SCL": "SCL (CLOCK)", "SDA": "SDA (DATA)", "WP": "WRITE PROTECT"}

PODS_ = {n: PD.pod(n) for n in PD.POD_NAMES}
COL = {"TH": 14, "UV": 14, "BARO": 15}
SENSOR = {"TH": "SHT45 #6174", "BARO": "BMP581 #6407", "UV": "LTR390 #4831"}
SLOGANS_P = [
    "THREE BOARDS. ONE FOOTPRINT. NO EXCUSES.",
    "TOP IS THE FACE THAT READS. THE COPPER SIDE IS SILENT.",
    "A WIRE UNDER A PART CANNOT BE FIXED LATER.",
    "LOWEST FIRST. TALLEST LAST. GRAVITY APPROVES.",
    "THE OUTER RAIL HAS THE BLUE LINE. THE RESISTOR KNOWS.",
    "THE WEATHER WILL READ THIS EEPROM FOR YEARS.",
    "METER FIRST. POWER NEVER. NOT TODAY.",
    "GLAND FIRST. PLUG LAST. THE PLUG DOES NOT FIT THROUGH.",
]


# ------------------------------------------------------------------ names
def hole(h):
    """A hole as this sheet prints it: F10, or TOP-8 / BOT+3 for a rail hole."""
    for r in ("top-", "top+", "bot-", "bot+"):
        if h.startswith(r):
            return r.upper().replace("-", "−") + h[len(r):]
    return h


RAIL_WORD = {"top-": "TOP− (the OUTER rail along the top edge, beside the BLUE line)",
             "top+": "TOP+ (the INNER top rail, beside the RED line)",
             "bot-": "BOT− (the INNER bottom rail, beside the BLUE line)",
             "bot+": "BOT+ (the OUTER rail along the bottom edge, beside the RED line)"}


def board_name(pod):
    return f"the {pod.name} pod's Perma-Proto Quarter #1608"


def wire_len(wr):
    pts = wr.path
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def cut_mm(wr):
    return int(round(wire_len(wr) + 10))


def bends(wr):
    return max(0, len(wr.path) - 2)


def cap(*sentences, width=96):
    return textwrap.wrap(" ".join(sentences), width)


# ------------------------------------------------------------------ page furniture (sheetlib.page with this unit's name)
def page(c, step_no, title, sub, pg, slogan):
    if pdfmetrics.stringWidth(sub, "MONO", 8) > W - 2 * M - 95:
        raise ValueError(f"page {pg}: subtitle too long for the header: {sub!r}")
    SL.page(c, step_no, title, sub, pg, slogan)
    c.setFillColor(INK)                              # cover sheetlib's unit line (the TX's) with this unit's
    c.rect(W - M - 130, H - 41, 130, 10, stroke=0, fill=1)
    text(c, W - M, H - 38, "UNIT: PODS-R1", 8, "MONO", GREY, "r", rec=False)


def ring(c, x, y, r=4.4, w=1.6):
    """Hole marker that reads on the cream board and its gold pads: magenta on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(NEON)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def face_tag(c, x, y, face):
    s = {"top": "TOP FACE", "under": "COPPER SIDE"}[face]
    w = pdfmetrics.stringWidth(s, "HEAD", 12) + 10
    c.setFillColor(INK)
    c.rect(x, y, w, 17, stroke=0, fill=1)
    text(c, x + 5, y + 4.5, s, 12, "HEAD", HAZ)
    LAB.block(x, y, x + w, y + 17, s)
    return w


def art_box(a, pad=2):
    return (a.x - pad, a.y - pad, a.x + a.w + pad, a.y + a.h + pad)


def axis_marks(c, a, fs=8.0):
    """Column numbers and row letters round a copper-side drawing (no print on that face)."""
    for n in (1, 5, 10, 15):
        x, y = a.A(f"J{n}")
        text(c, x, a.y - 8, str(n), fs, "ALT", GREY, "c")
    for L in "ABCDEFGHIJ":
        x, y = a.A(f"{L}1")
        text(c, a.x - 5, y - 3, L, fs, "ALT", GREY, "r")
    for r in ("bot+", "bot-", "top+", "top-"):
        x, y = a.A(f"{r}1")
        text(c, a.x - 5, y - 3, hole(r), fs - 1, "ALT", GREY, "r")
    LAB.block(a.x - 30, a.y - 11, a.x + a.w, a.y - 1, "axis numbers")
    LAB.block(a.x - 30, a.y, a.x - 1, a.y + a.h, "axis letters")


def _halo_line(c, x0, y0, x1, y1):
    c.setStrokeColor(WHITE)
    lw(c, 2.6)
    c.line(x0, y0, x1, y1)
    c.setStrokeColor(INK)
    lw(c, 1.0)
    c.line(x0, y0, x1, y1)


def _end(c, r, sx, sy, px, py, is_hole, ring_r):
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


def lanes(c, items, box, size=9, gap=8, color=NEON, font="ALT", ring_r=4.4):
    """Chips in lanes round a drawing (the Session 3 lanes): items [(text, px, py, lane, is_hole)], lane 'up' / 'dn'
    (a row above / below, in the left-to-right order of the targets) or 'lt' / 'rt' (a column beside it)."""
    x0b, y0b, x1b, y1b = box
    asc = size * 0.72
    pan = next(p for p in LAB.panels if p[0] <= x0b + 1 and p[2] >= x1b - 1)
    for k in ("up", "dn"):
        its = sorted((px, s_, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        wd = [pdfmetrics.stringWidth(s_.split("\n")[0], font, size) + 5.2 for _px, s_, _py, _ih in its]
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
        lo = pan[0] + 6 - xs[0]
        if lo > 0:
            xs = [v + lo for v in xs]
        hi = xs[-1] + wd[-1] - (pan[2] - 6)
        if hi > 0:
            xs = [v - hi for v in xs]
        yb = (y1b + 5) if k == "up" else (y0b - 5 - asc)
        for (px, s_, py, ih), xa, w_ in zip(its, xs, wd):
            r = chip(c, xa + w_ / 2, yb, s_, size, font, color, "c")
            sx, sy = (r[0] + r[2]) / 2, (r[1] if k == "up" else r[3])
            _end(c, r, sx, sy, px, py, ih, ring_r)
    for k in ("lt", "rt"):
        its = sorted((-py, s_, px, py, ih) for s_, px, py, ln, ih in items if ln == k)
        if not its:
            continue
        nl = [s_.count("\n") + 1 for _k, s_, *_r in its]
        ys = [py for *_r, py, _ih in its]
        for _ in range(40):
            for n in range(1, len(ys)):
                ys[n] = min(ys[n], ys[n - 1] - (asc + 5.2 + 3) - size * 1.12 * (nl[n - 1] - 1))
        for (_k, s_, px, py, ih), yy in zip(its, ys):
            if k == "lt":
                r = chip(c, x0b - 6, yy - asc / 2, s_, size, font, color, "r")
                sx, sy = r[2], (r[1] + r[3]) / 2
            else:
                r = chip(c, x1b + 6, yy - asc / 2, s_, size, font, color, "l")
                sx, sy = r[0], (r[1] + r[3]) / 2
            _end(c, r, sx, sy, px, py, ih, ring_r)


def ring_lanes(c, a, holes, names=None, box=None, size=8.5, side=None):
    """Ring every hole and name it in a lane above or below the drawing (by the hole's height on the page)."""
    cy = a.y + a.h / 2
    items = []
    for h in holes:
        px, py = a.A(h)
        ring(c, px, py)
        lane = side or ("up" if py > cy else "dn")
        items.append(((names or {}).get(h, hole(h)), px, py, lane, True))
    lanes(c, items, box or art_box(a), size=size)


def para(c, x, ytop, lines, size=8.6, lead=11.0, font="ALT", color=INK, w=None, what="text"):
    """Wrapped running text as plain text (recorded for the badge check), blocked off for the chips."""
    yy = ytop
    for ln in lines:
        text(c, x, yy, ln, size, font, color)
        yy -= lead
    if w:
        LAB.block(x, yy + lead - 3, x + w, ytop + size, what)
    return yy


def wrap_px(s, width_pt, size, font="ALT"):
    words, out, cur = s.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(t, font, size) > width_pt and cur:
            out.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def tick_box(c, x, y, s=11):
    c.setStrokeColor(NEON)
    lw(c, 1.4)
    c.rect(x, y, s, s, stroke=1, fill=0)
    LAB.block(x, y, x + s, y + s, "tick")


# ------------------------------------------------------------------ the pages
PAGES = []          # (step, title, tags, fn)


def add_page(step, title, tags, fn):
    PAGES.append((step, title, tags, fn))


def cover(c, pg):
    page(c, "00", "SESSION P: THE THREE POD BOARDS",
         "TH, BARO, UV: EACH ON A PERMA-PROTO QUARTER #1608, 9 WIRES UNDER. ONE PORT CABLE. NO POWER.",
         pg, SLOGANS_P[0])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), None, cap(
        "PARTS AS SUPPLIED. Every breakout is drawn as it comes: STEMMA QT sockets fitted at the factory, header strip loose.",
        "Lay out one pod's parts at a time. Quantities are for all three pods.", width=100))
    items = [("PERMA-PROTO QUARTER #1608 (3x)\nprinted top, strips underneath", "p_pp"),
             ("24LC32 EEPROM #5146 (3x)\n+ its loose 1x6 header", "p_eep"),
             ("LTR390 UV #4831 (UV pod)\n+ its loose 1x6 header", "p_ltr"),
             ("BMP581 #6407 (BARO pod)\n+ loose header, 1 pin per pad", "p_bmp"),
             ("SHT45 #6174, PTFE CAP (TH pod)\nits header strip: NOT USED", "p_sht"),
             ("PER POD (3x): BOB-14021 (TAB ON)\n+ 87180-066LF JACK + 1x6 HEADER", "p_bob"),
             ("PER POD (3x): SULLINS PRPC002SAAN\n2-PIN HEADER + SPC02SYAN SHUNT", "p_jp1"),
             ("PER POD (3x): R1 10k 1% MFR-25\nBROWN-BLACK-BLACK-RED-BROWN", "p_r1"),
             ("24 AWG SOLID HOOK-UP WIRE\nred, black, yellow, blue", "p_wires"),
             ("TH LEAD: ROUND JACKETED 4-CORE\nstranded: red, black, yellow, blue", "p_lead"),
             ("PORT CABLE: ROUND 6-CONDUCTOR\n+ 2 RJ12 6P6C PLUGS + PG-7 #762", "p_cable")]
    cw, rh = w / 3, h / 4
    for i, (name, art) in enumerate(items):
        col, row = i % 3, i // 3
        X, Y = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X + 8, Y + 30, cw - 16, rh - 36)
        chip(c, X + cw / 2, Y + 18, name, 7.6, "ALT", INK, "c")
    X, Y = x + cw * 2, y
    lines = ["NOT IN THIS SESSION: the boxes, the", "glands' fitting, the shield (Session Q).",
             "", "STILL TO BUY: the TH lead and the port", "cable (sources.py: th_lead_gland, pg7_seal).",
             "", "VALUES: sources.py. HOLES: layout/pods.py."]
    para(c, X + 10, Y + rh - 22, lines, 8.0, 10.5, w=cw - 14, what="notes")


def before(c, pg):
    page(c, "00", "BEFORE YOU START", "TOOLS, THE ORDER OF THE STEPS, AND HOW THIS SHEET NAMES EVERY HOLE.", pg, SLOGANS_P[1])
    g = Grid(2, 2, heights=[1.25, 1])
    x, y, w, h = panel(c, g.cell(0, 0), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (24 AWG; THE LEAD'S CORES)",
             "MULTIMETER: CONTINUITY + OHMS", "PLIERS + VICE OR CLAMP (SNAP THE BOB TABS)", "SMALL FILE",
             "STEEL RULER (WIRE LENGTHS)", "RJ12 6P6C CRIMP TOOL (THE CABLE)", "A SPARE PERMA-PROTO OR BREADBOARD",
             "  (HOLDS A HEADER SQUARE WHILE YOU SOLDER)"]
    for i, s in enumerate(tools):
        text(c, x + 12, y + h - 16 - i * 15, ("-  " if not s.startswith(" ") else "   ") + s.strip(), 9, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 0), None, "THE STEPS. IN THIS ORDER.")
    for i, (n, s) in enumerate(STEP_LIST):
        text(c, x + 12, y + h - 14 - i * min(14.5, (h - 20) / len(STEP_LIST)), f"{n}  {s}", 8.6, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 1, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["EVERY HOLE IS NAMED AS PRINTED ON THE PERMA-PROTO: LETTER = ROW (A-J), NUMBER = COLUMN (1-15). F10 = ROW F, COLUMN 10.",
             "THE FOUR RAILS HAVE NO PRINTED NAME. THIS SHEET CALLS THEM BOT+ AND BOT− (BOTTOM EDGE), TOP+ AND TOP− (TOP EDGE).",
             "TOP− IS THE OUTER RAIL AT THE TOP EDGE, BESIDE THE BLUE LINE. TOP+ IS THE INNER ONE, BESIDE THE RED LINE.",
             "WIRES: 24 AWG SOLID, IN FROM THE COPPER SIDE, SOLDERED ON THE TOP. PART PINS: IN FROM THE TOP, SOLDERED UNDERNEATH.",
             "J1, U1, U2, JP1, R1 ARE PARTS. J5, J10 ... ARE HOLES IN ROW J. THE SHEET ALWAYS SAYS WHICH.",
             "NO POWER IN THIS SESSION. THE METER IS THE ONLY JUDGE. ANYTHING ODD: STOP, PHOTOGRAPH IT, REPORT TO CLAUDE."]
    for i, s in enumerate(rules):
        yy = y + h - 12 - i * (h - 8) / len(rules)
        verdict(c, x + 18, yy, True, 7)
        for k, ln in enumerate(wrap_px(s, w - 44, 8.2)):
            text(c, x + 32, yy - 3 - k * 9.5, ln, 8.2, "ALT", INK)


def faces(c, pg):
    page(c, "01", "KNOW THE PERMA-PROTO'S TWO FACES", "THE QUARTER #1608 HAS A PRINTED TOP AND A COPPER SIDE. EVERY STEP NAMES ONE.",
         pg, SLOGANS_P[1])
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "TOP FACE: the face with print. Column numbers 1-15 read upright along the top and bottom; the row letters A-J are",
        "printed turned on their side beside both long edges, A at the bottom. Hold it like this for every TOP step.",
        width=48))
    face_tag(c, x + 36, y + h - 22, "top")
    a = Art(c, "pp_top", x + 14, y + 40, w - 28, h - 110)
    items = [("TOP− (OUTER, BLUE)", *a.A("top-3"), "up", True), ("F10", *a.A("F10"), "up", True),
             ("TOP+ (INNER, RED)", *a.A("top+13"), "up", True),
             ("BOT− (INNER, BLUE)", *a.A("bot-3"), "dn", True), ("BOT+ (OUTER, RED)", *a.A("bot+13"), "dn", True)]
    for _s, hx, hy, *_r in items:
        ring(c, hx, hy)
    lanes(c, items, art_box(a), 8.0)
    x, y, w, h = panel(c, g.cell(1, 0), 2, cap(
        "COPPER SIDE: turn it over toward you, over its BOTTOM edge. Now row A is at the top, row J at the bottom, and",
        "columns STILL run 1 to 15 left to right. No print here. The strips show: each column's A-E five holes are one strip,",
        "its F-J five another (the two halves NOT joined); each rail is one strip along all 15.", width=48))
    face_tag(c, x + 36, y + h - 22, "under")
    a = Art(c, "pp_under", x + 40, y + 40, w - 50, h - 110)
    axis_marks(c, a)
    items = [("A-E STRIP, COLUMN 7", *a.A("C7"), "up", True), ("F-J STRIP, COLUMN 7", *a.A("H7"), "dn", True),
             ("TOP− RAIL: ONE STRIP", *a.A("top-12"), "dn", True)]
    for _s, hx, hy, *_r in items:
        ring(c, hx, hy)
    lanes(c, items, (a.x, a.y - 12, a.x + a.w, a.y + a.h), 8.0)


def bob_page(c, pg):
    tab_out = -(PODS_["TH"].part("J1").origin[0] - 21.59)      # the tab's far end, turned 180 with the board
    page(c, "02", "BUILD THE 3 JACK BREAKOUTS", "BOB-14021 BARE BOARD + 87180-066LF JACK + 1x6 HEADER. ONE PER POD: TH, BARO, UV.", pg, SLOGANS_P[3])
    g = Grid(2, 2, heights=[1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["AS SUPPLIED: three parts per jack.", "BOB-14021 is a bare board with a",
                                            "snap-off tab; jack and header loose."])
    a = Art(c, "bob_kit", x + 6, y + 6, w - 12, h - 12)
    lanes(c, [("87180 JACK", *a.A("bob:jack"), "lt", False), ("SNAP-OFF TAB", *a.A("bob:tab"), "rt", False),
              ("V-SCORE", *a.A("bob:score"), "rt", False), ("1x6 HEADER", *a.A("bob:hdr"), "lt", False)],
          art_box(a, -6), size=8.5)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["1  SNAP THE TAB OFF: clamp the board along",
                                            "the V-score, bend once. File the edge flat.",
                                            "Board 15.24 mm wide (the header's length)."])
    a = Art(c, "bob_snap", x + 10, y + 46, w - 90, h - 52, align="l")
    lanes(c, [("TAB: OFF", *a.A("bob:tab"), "rt", False), ("V-SCORE", *a.A("bob:score_top"), "up", False)],
          art_box(a, -6), size=8.5)
    for i, s in enumerate(wrap_px(f"Left on, the tab would stand {tab_out:.1f} mm past the Perma-Proto's left edge, "
                                  "into the pod box's wall.", w - 24, 8.0)[:3]):
        text(c, x + 10, y + 32 - i * 10, s, 8.0, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 3, ["2  JACK on the board's top: pegs in the two big",
                                            "holes, pins in the six small ones (one way only).",
                                            "Solder the pins underneath, CUT THEM FLUSH.",
                                            "3  HEADER: plastic under the board, short ends",
                                            "up through the six pads, solder on top.",
                                            "(Drawn turned over: jack down, header up.)"])
    a = Art(c, "bob_ready", x + 70, y + 6, w - 160, h - 12)
    lanes(c, [("JACK PINS: FLUSH", *a.A("bob:jfil"), "rt", False), ("PEG", *a.A("bob:peg"), "lt", False),
              ("1x6 PLASTIC", *a.A("bob:hdr_bot"), "lt", False), ("LONG ENDS", *a.A("bob:hpin_lo"), "rt", False)],
          art_box(a, -6), size=8.5)
    x, y, w, h = panel(c, g.cell(1, 1), 4, ["Done, from above the pad row. Flush jack pins:",
                                            "nothing may stick down past the board's",
                                            "underside. Build all 3 the same."], warn=True)
    a = Art(c, "bob_top", x + 60, y + 6, w - 160, h - 12)
    lanes(c, [("HEADER SOLDERED", *a.A("bob:hfil"), "rt", False), ("87180 JACK", *a.A("bob:jack"), "lt", False)],
          art_box(a, -6), size=8.5)


def bmp_cut(c, pg):
    names = S.val("bmp581_pins")
    page(c, "03", "BARO: CUT THE BMP581'S HEADER TO 6 PINS", "ITS STRIP HAS A PIN PER PAD (8). CS AND INT GET NONE: THEY WOULD LAND PAST THE BOARD'S EDGE.", pg, SLOGANS_P[3])
    g = Grid(1, 2, heights=[0.9, 1.1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "The BMP581 #6407's loose male header strip, as supplied. Count six pins from one end. With flush cutters, cut",
        "through the plastic between pin 6 and pin 7 (the magenta line), then file the cut end flat. Keep the 6-pin piece;",
        "the 2-pin piece is spare. (Your strip longer than 8? Still keep 6, cut after the 6th.)"))
    a = Art(c, "bmp_cut", x + 20, y + 40, w - 40, h - 90)
    items = [(str(i), *a.A(f"pin{i}"), "up", False) for i in range(1, 9)]
    lanes(c, items, art_box(a, -4), size=8.5)
    lanes(c, [("KEEP: 6 PINS", *a.A("keep"), "dn", False), ("CUT OFF: 2 PINS (SPARE)", *a.A("cut"), "dn", False)],
          art_box(a, -4), size=8.5)
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
        "Solder the 6-pin piece into the BMP581's pads 1-6, plastic under the board (the face without the chips), short",
        "ends up from below, soldered on the chip face: " + ", ".join(f"pad {i + 1} {n}" for i, n in enumerate(names[:6])) + ".",
        f"Pads 7 {names[6]} and 8 {names[7]} stay EMPTY. Hold it square: long ends in a spare Perma-Proto while you solder."))
    a = Art(c, "hdr_bmp", x + 20, y + 30, w - 200, h - 70, align="l")
    lanes(c, [("6 PINS SOLDERED ON TOP", *a.A("bmp:hfil"), "up", False), ("1x6 PLASTIC UNDER", *a.A("bmp:hdr"), "dn", False)],
          art_box(a, -4), size=8.5)
    tx = a.x + a.w + 20
    for i, n in enumerate(names):
        yy = y + h - 40 - i * 15
        text(c, tx, yy, f"PAD {i + 1}", 9, "HEAD", INK)
        text(c, tx + 44, yy, n, 9.5, "HEAD", NEON if i < 6 else GREY)
        text(c, tx + 82, yy, "PIN" if i < 6 else "EMPTY", 8.5, "ALT", INK if i < 6 else GREY)
    LAB.block(tx, y + h - 40 - 7 * 15 - 4, x + w - 4, y + h - 30, "pad table")


def headers(c, pg):
    page(c, "04", "HEADERS ONTO THE BREAKOUTS", "24LC32 #5146 (3x) AND LTR390 #4831: A PIN PER PAD. SHT45: NONE, THE TH LEAD GOES ON ITS PADS.", pg, SLOGANS_P[3])
    g = Grid(1, 2, heights=[1, 1])
    for k, (key, art, pre, n) in enumerate((("eeprom_24lc32", "hdr_eep", "eep", "3x: one per pod"),
                                             ("ltr390", "hdr_ltr", "ltr", "the UV pod"))):
        names = S.val(key + "_pins")
        nm = {"eeprom_24lc32": "24LC32 EEPROM #5146", "ltr390": "LTR390 #4831"}[key]
        x, y, w, h = panel(c, g.cell(0, k), k + 1, cap(
            f"{nm} ({n}): its own 1x6 strip, plastic under the board (the face without the chips), short ends up through",
            "the six pads from below, soldered on the chip face. Long ends in a spare Perma-Proto to hold it square; solder",
            "pin 1 first, check it sits flat, then pin 6, then the rest. Pads: " +
            ", ".join(f"{i + 1} {p}" for i, p in enumerate(names)) + "."))
        a = Art(c, art, x + 20, y + 30, w - 200, h - 70, align="l")
        its = [("HEADER SOLDERED ON TOP", *a.A(f"{pre}:hfil"), "up", False), ("1x6 PLASTIC UNDER", *a.A(f"{pre}:hdr"), "dn", False)]
        lanes(c, its, art_box(a, -4), size=8.5)
        tx = a.x + a.w + 20
        para(c, tx, y + h - 50, ["STEMMA QT SOCKETS:", "fitted at the factory,", "both stay, nothing", "plugs in them."],
             8.6, 11, w=x + w - tx - 4, what="qt note")


# ------------------------------------------------------------------ per pod
def wires_panel(c, cell, k, pod, nums, first):
    col = COL[pod.name]
    if first:
        cp = cap(f"{board_name(pod).upper()}, COPPER SIDE (row A at the top). Wires {nums[0]}-{nums[-1]} of 9: 24 AWG solid.",
                 "Cut each to the length shown (route + 10 mm), strip 3 mm at both ends, lay it flat on its drawn route, bends",
                 "square. Push each end through its hole from the COPPER SIDE, solder it on the TOP, trim. Wires go FIRST:",
                 "parts cover some of these holes later.", width=100)
    else:
        cp = cap(f"{board_name(pod).upper()}, COPPER SIDE. Wires {nums[0]}-{nums[-1]}. Grey = wires already in. Same method:",
                 "cut, strip 3 mm, lay flat on the drawn route, ends in from the copper side, soldered on the TOP, trimmed.", width=100)
    x, y, w, h = panel(c, cell, k, cp)
    a = Art(c, f"u{col}_{(nums[0] - 1) // 3 + 1}", x + 40, y + 34, 250, h - 64, align="l", valign="b")
    axis_marks(c, a)
    tx = a.x + a.w + 14
    face_tag(c, tx, y + h - 24, "under")
    for j, n in enumerate(nums):
        wr = pod.wires[n - 1]
        yy = y + h - 50 - j * 44
        c.setFillColor(INSC[wr.colour])
        c.rect(tx, yy - 26, 6, 34, stroke=0, fill=1)
        text(c, tx + 12, yy, f"{n}  {hole(wr.hole_a)} TO {hole(wr.hole_b)}", 11.5, "HEAD", INK)
        text(c, tx + 12, yy - 12, f"{cut_mm(wr)} MM, {bends(wr)} BEND{'S' if bends(wr) != 1 else ''}, "
             f"{wr.colour.upper()} 24 AWG SOLID", 8.2, "ALT", INK)
        text(c, tx + 12, yy - 23, NET_WORD[wr.net], 8, "ALT", GREY)
        LAB.block(tx, yy - 27, x + w - 4, yy + 10, f"row {n}")
    items = []
    cy = a.A("E1")[1] / 2 + a.A("F1")[1] / 2
    for n in nums:
        wr = pod.wires[n - 1]
        for hn in (wr.hole_a, wr.hole_b):
            px, py = a.A(hn)
            ring(c, px, py)
            items.append((f"{n}: {hole(hn)}", px, py, "up" if py > cy else "dn", True))
    lanes(c, items, (a.x, a.y - 12, a.x + a.w, a.y + a.h), size=8.2)


def wires_page1(pod, step):
    def f(c, pg):
        page(c, step, f"{pod.name} POD: 9 WIRES UNDERNEATH 1/2", "24 AWG SOLID INSULATED, IN FROM THE COPPER SIDE, SOLDERED "
             "ON THE TOP. THEY GO FIRST.", pg, SLOGANS_P[2])
        g = Grid(1, 2)
        wires_panel(c, g.cell(0, 0), 1, pod, [1, 2, 3], True)
        wires_panel(c, g.cell(0, 1), 2, pod, [4, 5, 6], False)
    return f


def wires_page2(pod, step):
    def f(c, pg):
        page(c, step, f"{pod.name} POD: 9 WIRES UNDERNEATH 2/2", "WIRE 7 ENDS IN TOP−8: THE OUTER RAIL AT THE TOP EDGE, "
             "BESIDE THE BLUE LINE.", pg, SLOGANS_P[4])
        g = Grid(1, 2)
        wires_panel(c, g.cell(0, 0), 1, pod, [7, 8, 9], False)
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            f"All 9 wires of {board_name(pod)}, in order. Tick each when both ends are soldered on the TOP and trimmed.",
            "Wire 7's far end is TOP−8: the rail along the top edge, the one beside the BLUE line (not TOP+, the red-line one).",
            width=100))
        text(c, x + 30, y + h - 30, "#   FROM    TO       CUT      COLOUR   CARRIES   WHAT IT JOINS", 8.5, "MONO", GREY)
        step_ = min(26.0, (h - 52) / 9)
        for i, wr in enumerate(pod.wires):
            yy = y + h - 48 - i * step_
            c.setFillColor(INSC[wr.colour])
            c.rect(x + 8, yy - 2, 16, 9, stroke=0, fill=1)
            text(c, x + 30, yy, str(i + 1), 10, "HEAD", INK)
            text(c, x + 50, yy, hole(wr.hole_a), 10, "HEAD", NEON)
            text(c, x + 92, yy, hole(wr.hole_b), 10, "HEAD", NEON)
            text(c, x + 140, yy, f"{cut_mm(wr)} MM", 8.5, "ALT", INK)
            text(c, x + 192, yy, wr.colour.upper(), 8.5, "ALT", INK)
            text(c, x + 240, yy, wr.net, 8.5, "ALT", INK)
            nl_ = wrap_px(wr.note, w - 326, 7.2)
            if len(nl_) > 2:
                raise ValueError(f"wire {i + 1} note needs {len(nl_)} lines: {wr.note!r}")
            for k_, ln in enumerate(nl_):
                text(c, x + 290, yy + 3.5 - k_ * 8, ln, 7.2, "ALT", GREY)
            tick_box(c, x + w - 22, yy - 2, 10)
        LAB.block(x + 6, y + h - 48 - 9 * step_, x + w - 24, y + h - 22, "wire table")
    return f


def low_page(pod, step):
    col = COL[pod.name]
    r1, jp = pod.part("R1"), pod.part("JP1")

    def f(c, pg):
        page(c, step, f"{pod.name} POD: R1 AND THE WP HEADER JP1", "THE LOWEST PARTS FIRST. R1 LIES FLAT; JP1 STANDS. "
             "SOLDERED ON THE COPPER SIDE.", pg, SLOGANS_P[4])
        g = Grid(1, 2, heights=[1.25, 1])
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            f"{board_name(pod).upper()}, TOP FACE. R1 (Yageo MFR-25 10k 1 %, blue body, brown-black-black-red-brown) lies",
            f"flat along column 5: one lead in {hole(r1.pins['1'])}, the other in {hole(r1.pins['2'])}, the OUTER rail at the "
            "top edge, beside the BLUE line. Its body lies across TOP+5 (the red-line rail): that hole stays EMPTY.",
            f"No polarity. JP1, the Sullins 2-pin header: short ends down through {hole(jp.pins['1'])} (pin 1, 3.3 V) and "
            f"{hole(jp.pins['2'])} (pin 2, WP), plastic flat on the board. Solder both parts on the COPPER SIDE, trim.",
            width=100))
        face_tag(c, x + 36, y + h - 24, "top")
        a = Art(c, f"t{col}_low", x + 124, y + 34, 230, h - 64, align="l")
        hs = [r1.pins["1"], r1.pins["2"], jp.pins["1"], jp.pins["2"]]
        items = []
        for hh in hs:
            px, py = a.A(hh)
            ring(c, px, py)
        items = [(f"R1: {hole(r1.pins['1'])}", *a.A(r1.pins["1"]), "lt", True),
                 (f"R1: {hole(r1.pins['2'])}\n(outer, blue line)", *a.A(r1.pins["2"]), "lt", True),
                 (f"JP1 PIN 1: {hole(jp.pins['1'])}", *a.A(jp.pins["1"]), "lt", True),
                 (f"JP1 PIN 2: {hole(jp.pins['2'])}", *a.A(jp.pins["2"]), "lt", True),
                 ("R1 BODY: TOP+5 EMPTY", *a.A("R1:body"), "lt", False)]
        lanes(c, items, art_box(a), size=8.5)
        tx = a.x + a.w + 30
        rows = [("R1", "10k 1 %, LYING"), (f"  LEAD", f"{hole(r1.pins['1'])}  WP"), ("  LEAD", f"{hole(r1.pins['2'])}  GROUND"),
                ("JP1", "SULLINS 2-PIN"), ("  PIN 1", f"{hole(jp.pins['1'])}  3.3 V"), ("  PIN 2", f"{hole(jp.pins['2'])}  WP")]
        for i, (k_, v) in enumerate(rows):
            yy = y + h - 60 - i * 14
            text(c, tx, yy, k_, 9.5, "HEAD", INK)
            text(c, tx + 48, yy, v, 9, "ALT", NEON if k_.strip() in ("LEAD", "PIN 1", "PIN 2") else GREY)
        LAB.block(tx, y + h - 60 - 6 * 14, x + w - 4, y + h - 48, "part table")
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            "Close-up from the front-left: R1 over TOP+5, its second lead in TOP−5; JP1 with its Sullins SPC02SYAN shunt",
            "pushed down over BOTH posts. Shunt ON = the EEPROM is write-protected (WP at 3.3 V). Shunt OFF = R1 pulls WP",
            "to ground = writable. Fit the shunt now; the meter page takes it off once and puts it back.", width=100))
        b = Art(c, f"i{col}_low", x + 40, y + 22, w - 240, h - 56, align="l")
        lanes(c, [("R1 (10k)", *b.A("R1:body"), "up", False), ("SHUNT ON = PROTECTED", *b.A("JP1:shunt"), "rt", False)],
              art_box(b, -2), size=8.5)
    return f


def jack_page(pod, step):
    col = COL[pod.name]
    j1 = pod.part("J1")
    pins = [(str(i), j1.pins[str(i)], j1.nets[str(i)]) for i in range(1, 7)]

    def f(c, pg):
        page(c, step, f"{pod.name} POD: JACK J1 IN A1-A6", "THE STEP 02 BREAKOUT ON ITS 1x6 HEADER. MOUTH TO THE BOTTOM EDGE, TOWARD THE BOX'S GLAND.", pg, SLOGANS_P[3])
        g = Grid(1, 2, heights=[1.3, 1])
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            f"{board_name(pod).upper()}, TOP FACE. J1's header long ends go down through A1 to A6 from the TOP: header pin 1",
            "in A1 (the left), pin 6 in A6. The jack's mouth faces the BOTTOM edge and the breakout overhangs it. Hold the",
            "breakout level, solder A1 on the COPPER SIDE, check, then the other five; trim to 1 mm.", width=100))
        face_tag(c, x + 36, y + h - 24, "top")
        a = Art(c, f"t{col}_jack", x + 124, y + 34, 230, h - 64, align="l")
        items = []
        for pn, hh, net in pins:
            px, py = a.A(hh)
            ring(c, px, py)
        lanes(c, [(f"PIN 1: {hole(pins[0][1])}", *a.A(pins[0][1]), "lt", True),
                  (f"PIN 6: {hole(pins[5][1])}", *a.A(pins[5][1]), "lt", True),
                  ("87180 JACK:\nMOUTH DOWN", *a.A("J1:jack"), "lt", False)], art_box(a), size=8.5)
        tx = a.x + a.w + 30
        text(c, tx, y + h - 50, "PIN  HOLE  LINE", 8.5, "MONO", GREY)
        for i, (pn, hh, net) in enumerate(pins):
            yy = y + h - 66 - i * 16
            text(c, tx, yy, pn, 10, "HEAD", INK)
            text(c, tx + 28, yy, hole(hh), 10, "HEAD", NEON)
            text(c, tx + 62, yy, NET_WORD[net] if net else "NOT CONNECTED", 8.5, "ALT", INK if net else GREY)
        LAB.block(tx, y + h - 66 - 6 * 16, x + w - 4, y + h - 40, "pin table")
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            "From the front-left: the mouth over the bottom edge, where the cable comes up from the box's gland. Pins 1 and",
            "6 still get soldered (they hold the breakout); nothing else connects to them.", width=100))
        b = Art(c, f"i{col}_jack", x + 30, y + 22, w - 60, h - 56)
        lanes(c, [("J1 MOUTH", *b.A("J1:mouth"), "rt", False)], art_box(b, -2), size=8.5)
    return f


def eep_page(pod, step):
    col = COL[pod.name]
    u1 = pod.part("U1")
    names = S.val("eeprom_24lc32_pins")

    def f(c, pg):
        page(c, step, f"{pod.name} POD: EEPROM U1 IN F5-F10", "24LC32 #5146 (HEADER FROM STEP 04), CHIPS UP, TURNED: ITS BOARD "
             "COVERS ROWS B-G.", pg, SLOGANS_P[5])
        g = Grid(1, 2, heights=[1.3, 1])
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            f"{board_name(pod).upper()}, TOP FACE. U1, chips UP, turned so its printed pad names read upside down and its",
            f"board hangs DOWN toward the jack: VIN in {hole(u1.pins['VIN'])}, then " +
            ", ".join(f"{n} {hole(u1.pins[n])}" for n in names[1:]) + ".",
            "Long ends down through row F from the TOP. Solder on the COPPER SIDE (F10 first, check it sits level), trim.",
            width=100))
        face_tag(c, x + 36, y + h - 24, "top")
        a = Art(c, f"t{col}_eep", x + 124, y + 34, 230, h - 64, align="l")
        lanes(c, [("U1 24LC32", *a.A("U1:chip"), "lt", False), ("QT SOCKET: EMPTY", *a.A("U1:qtL"), "lt", False)],
              art_box(a), size=8.5)
        tx = a.x + a.w + 30
        text(c, tx, y + h - 50, "PAD  HOLE  LINE", 8.5, "MONO", GREY)
        for i, n in enumerate(names):
            yy = y + h - 66 - i * 16
            text(c, tx, yy, n, 10, "HEAD", INK)
            text(c, tx + 34, yy, hole(u1.pins[n]), 10, "HEAD", NEON)
            net = u1.nets[n]
            text(c, tx + 66, yy, NET_WORD[net] if net else "NOT CONNECTED", 8.2, "ALT", INK if net else GREY)
        LAB.block(tx, y + h - 66 - 6 * 16, x + w - 4, y + h - 40, "pin table")
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            "From the front-left: U1 stands 2.5 mm up on its header plastic, its board over the wire ends under it (they are",
            "already soldered: that is why the wires went first). The 3Vo pad's pin goes in F9 and connects to nothing.", width=100))
        b = Art(c, f"i{col}_eep", x + 30, y + 22, w - 60, h - 56)
        lanes(c, [("U1", *b.A("U1:chip"), "rt", False)], art_box(b, -2), size=8.5)
    return f


def sensor_page(pod, step):
    u2 = pod.part("U2")
    key = u2.source
    names = S.val(key + "_pins")
    over_r = {"ltr390": 2.54, "bmp581": 5.08}[key]

    def f(c, pg):
        page(c, step, f"{pod.name} POD: SENSOR U2 IN J10-J15", f"{SENSOR[pod.name]}, CHIPS UP, UPRIGHT. TALLEST PART: LAST.",
             pg, SLOGANS_P[3])
        g = Grid(1, 2, heights=[1.3, 1])
        empt = [n for n in names if n not in u2.pins]
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            f"{board_name(pod).upper()}, TOP FACE. U2 {SENSOR[pod.name]}, chips UP, its pad names readable: " +
            ", ".join(f"{n} {hole(u2.pins[n])}" for n in names if n in u2.pins) + "." +
            (f" Pads {' and '.join(empt)} have no pin (step 03): they hang past the right edge." if empt else ""),
            f"Its board overhangs the top edge 3.8 mm and the right edge {over_r:.1f} mm. Long ends down through row J from the",
            "TOP; solder on the COPPER SIDE (J10 first, check it is level), trim.", width=100))
        face_tag(c, x + 36, y + h - 24, "top")
        a = Art(c, f"t_{pod.name.lower()}_u2", x + 124, y + 34, 230, h - 64, align="l")
        lanes(c, [(f"U2 {SENSOR[pod.name].split(' #')[0]}", *a.A("U2:sensor"), "lt", False),
                  ("QT SOCKET: EMPTY", *a.A("U2:qtR"), "lt", False)], art_box(a), size=8.5)
        tx = a.x + a.w + 30
        text(c, tx, y + h - 50, "PAD  HOLE  LINE", 8.5, "MONO", GREY)
        for i, n in enumerate(names):
            yy = y + h - 66 - i * 15
            text(c, tx, yy, n, 10, "HEAD", INK)
            fitted = n in u2.pins
            text(c, tx + 34, yy, hole(u2.pins[n]) if fitted else "—", 10, "HEAD", NEON if fitted else GREY)
            net = u2.nets.get(n) if fitted else None
            text(c, tx + 66, yy, NET_WORD[net] if net else ("NOT CONNECTED" if fitted else "NO PIN"), 8.2, "ALT",
                 INK if net else GREY)
        LAB.block(tx, y + h - 66 - len(names) * 15, x + w - 4, y + h - 40, "pin table")
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            "From the front-left, finished: J1 lowest at the front, U1 behind it, U2 at the back over the top edge. Its sensor",
            "faces UP" + (" toward the box lid's window." if key == "ltr390" else ", toward the box's vent side.")
            + " Next: the strip map, then the meter.", width=100))
        b = Art(c, f"i_{pod.name.lower()}_u2", x + 30, y + 22, w - 60, h - 56)
        lanes(c, [("SENSOR", *b.A("U2:sensor"), "rt", False)], art_box(b, -2), size=8.5)
    return f


def lead_sht_page(pod, step):
    lead = pod.lead
    cores = {cc.colour: cc for cc in lead.conductors}

    def f(c, pg):
        page(c, step, "TH POD: THE LEAD, SHT45 END", "ROUND JACKETED 4-CORE, STRANDED. SOLDERED TO THE SHT45 #6174'S OWN HEADER "
             "PADS. NO HEADER.", pg, SLOGANS_P[5])
        g = Grid(1, 2, heights=[1.35, 1])
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            "The SHT45 #6174's FRONT: the face with the white PTFE cap and the printed pad names. Strip the jacket back 30 mm",
            "at this end, strip each core 3 mm, twist and tin it. Each core goes IN FROM THE BACK (the bare face) and is",
            "soldered on the FRONT: " + ", ".join(f"{cc.colour.upper()} to {cc.pad}" for cc in lead.conductors) +
            ". The 3Vo pad stays EMPTY. Trim the ends.", width=100))
        a = Art(c, "sht_lead", x + 20, y + 24, 240, h - 90, align="l", valign="b")
        items = [(f"{cc.pad}: {cc.colour.upper()}", *a.A(f"pad:{cc.pad}"), "up", False) for cc in lead.conductors]
        items.append(("3Vo: EMPTY", *a.A("pad:3Vo"), "up", False))
        lanes(c, items, art_box(a), size=8.0)
        lanes(c, [("4-CORE JACKET", *a.A("jacket"), "rt", False)], art_box(a), size=8.5)
        tx = x + w - 190
        text(c, tx, y + h - 50, "CORE     PAD    LINE", 8.5, "MONO", GREY)
        for i, cc in enumerate(lead.conductors):
            yy = y + h - 68 - i * 18
            c.setFillColor(INSC[cc.colour])
            c.rect(tx, yy - 2, 14, 10, stroke=0, fill=1)
            text(c, tx + 20, yy, cc.colour.upper(), 9.5, "HEAD", INK)
            text(c, tx + 70, yy, cc.pad, 10, "HEAD", NEON)
            text(c, tx + 104, yy, NET_WORD[cc.net], 8.2, "ALT", INK)
        LAB.block(tx, y + h - 68 - 4 * 18, x + w - 4, y + h - 40, "core table")
        para(c, tx, y + h - 68 - 4 * 18 - 14, wrap_px("In the shield, this board sits on the stand strip's inner face, "
                                                     "zip-tied (Session Q). The four pads are the only joints in the shield's air.",
                                                     x + w - tx - 8, 8.2), 8.2, 10.5, w=x + w - tx - 4, what="note")
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            "From below and behind: the four cores enter through the BACK, bend down along the board and gather into the",
            f"jacket. Check each joint on the FRONT is a shiny cone, no strand outside its pad. Lead length {lead.length_m} m "
            "(sources.py th_lead_m, TBD: the shield sets it). The other end stays BARE until the next page.", width=100))
        b = Art(c, "sht_lead_iso", x + 30, y + 22, w - 60, h - 56)
        lanes(c, [("BACK (BARE FACE): CORES IN HERE", *b.A("back"), "rt", False)], art_box(b, -2), size=8.5)
    return f


def lead_pod_page(pod, step):
    lead = pod.lead

    def f(c, pg):
        page(c, step, "TH POD: THE LEAD, POD END", "THREAD IT FIRST, SOLDER IT LAST: THE PERMA-PROTO WILL NOT PASS A GLAND.",
             pg, SLOGANS_P[7])
        g = Grid(1, 2, heights=[0.75, 1.35])
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            "THREADING ORDER for the lead's BARE pod end, before any soldering at this end: 1 down through the base cup's",
            "5 mm hole (from the stand side); 2 down through the remixed arm's 6 mm lead hole; 3 through the TH box's",
            "SECOND PG-7 #762: its dome nut first, then in through the gland body (fitted in the box's bottom wall, lock nut",
            "inside: Session Q). Not printed yet? Stop here; finish this page in Session Q.", width=100), warn=True)
        a = Art(c, "th_gland", x + 20, y + 14, w - 40, h - 74)
        lanes(c, [("3a DOME NUT", *a.A("dome"), "up", False), ("3b GLAND BODY (BOX WALL)", *a.A("body"), "up", False),
                  ("LOCK NUT (INSIDE)", *a.A("lock"), "up", False), ("TO THE SHT45 (SOLDERED)", *a.A("jacket"), "dn", False),
                  ("BARE CORES: INTO THE BOX", *a.A("cores"), "dn", False)], art_box(a, -2), size=8.0)
        x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
            f"{board_name(pod).upper()}, TOP FACE, everything else fitted. Strip the jacket back 40 mm inside the box, each",
            "core 3 mm. Each core goes DOWN through its hole from the TOP and is soldered on the COPPER SIDE: " +
            ", ".join(f"{cc.colour.upper()} in {hole(cc.hole)}" for cc in lead.conductors) + ". J11 stays EMPTY (on the",
            "UV pod it is the LTR390's 3Vo). The jacket runs down past U1's right end, off the bottom edge, to the gland.",
            width=100))
        face_tag(c, x + 36, y + h - 24, "top")
        a = Art(c, "t_th_u2", x + 30, y + 30, 260, h - 80, align="l")
        items = []
        for cc in lead.conductors:
            px, py = a.A(cc.hole)
            ring(c, px, py)
            items.append((f"{cc.colour.upper()}: {hole(cc.hole)}", px, py, "up", True))
        lanes(c, items, art_box(a), size=8.2)
        lanes(c, [("JACKET: DOWN TO THE GLAND", *a.A("L:jacket"), "rt", False)], art_box(a), size=8.5)
        tx = a.x + a.w + 150
        text(c, tx, y + h - 60, "CORE     HOLE   LINE", 8.5, "MONO", GREY)
        for i, cc in enumerate(lead.conductors):
            yy = y + h - 78 - i * 18
            c.setFillColor(INSC[cc.colour])
            c.rect(tx, yy - 2, 14, 10, stroke=0, fill=1)
            text(c, tx + 20, yy, cc.colour.upper(), 9.5, "HEAD", INK)
            text(c, tx + 70, yy, hole(cc.hole), 10, "HEAD", NEON)
            text(c, tx + 104, yy, NET_WORD[cc.net], 8.2, "ALT", INK)
        LAB.block(tx, y + h - 78 - 4 * 18, x + w - 4, y + h - 50, "core table")
    return f


def strip_rows(pod):
    """[(strip label, net, what lands in it)] for every strip a pin, wire end or lead end uses, from the pod's holes."""
    used = pod.holes_used()
    by = {}
    for hh, whats in used.items():
        by.setdefault(PPM.strip_of(hh), []).append((hh, whats))
    nl = PC.netlist(pod)
    pins = PC._pins(pod)
    net_of_strip = {}
    for net, grp in nl.items():
        for rp in grp:
            net_of_strip[PPM.strip_of(pins[rp][0])] = "NC" if net.startswith("NC") else net
    for wr in pod.wires:
        for hh in (wr.hole_a, wr.hole_b):
            net_of_strip.setdefault(PPM.strip_of(hh), wr.net)

    def label(sid):
        if sid.startswith("rail "):
            return hole(sid.split()[1]) + " RAIL"
        return f"COL {sid[3:]} {sid[:3]}"

    def key(sid):
        if sid.startswith("rail "):
            return (2, sid)
        return (0 if sid.startswith("A") else 1, int(sid[3:]))
    out = []
    for sid in sorted(by, key=key):
        bits = []
        for hh, whats in sorted(by[sid], key=lambda t: t[0]):
            for wt in whats:
                if wt.startswith("wire"):
                    n = next(i + 1 for i, wr in enumerate(pod.wires) if hh in (wr.hole_a, wr.hole_b)
                             and f"wire {wr.net} {wr.hole_a}-{wr.hole_b}" == wt)
                    bits.append(f"{hole(hh)} wire {n}")
                elif wt.startswith("lead"):
                    bits.append(f"{hole(hh)} lead {wt.split()[1]}")
                else:
                    bits.append(f"{hole(hh)} {wt}")
        out.append((label(sid), net_of_strip.get(sid, "NC"), ", ".join(bits)))
    return out


def strip_page(pod, step):
    col = COL[pod.name]

    def f(c, pg):
        page(c, step, f"{pod.name} POD: STRIP MAP", "EVERY USED STRIP OF THE COPPER SIDE, COLOURED BY WHAT IT CARRIES. THE METER CHECKS IT NEXT.", pg, SLOGANS_P[6])
        g = Grid(2, 1)
        cx, cy, cw, ch = g.cell(0, 0)
        x, y, w, h = panel(c, (cx, cy, cw * 1.15, ch), 1, cap(
            f"{board_name(pod).upper()}, COPPER SIDE (row A at the top). Coloured: the strips in use, by line;",
            "white-edged lines: the 9 wires. Uncoloured strips carry nothing.", width=56))
        face_tag(c, x + 36, y + h - 22, "under")
        a = Art(c, f"strip{col}", x + 34, y + 60, w - 44, h - 110)
        axis_marks(c, a)
        yy = y + 46
        xx = x + 10
        for net in ("3V3", "GND", "SDA", "SCL", "WP"):
            c.setFillColor(NETC[net])
            c.rect(xx, yy - 1, 12, 8, stroke=0, fill=1)
            text(c, xx + 15, yy, net, 8.2, "ALT", INK)
            xx += 50
        LAB.block(x + 8, yy - 3, xx, yy + 9, "legend")
        rows = strip_rows(pod)
        x2 = cx + cw * 1.15 + 8
        x, y, w, h = panel(c, (x2, cy, cx + 2 * cw + 10 - x2, ch), 2, ["Strip, line, and what lands in it", "(holes as printed)."])
        pitch = min(26.0, (h - 44) / len(rows))
        for i, (lab, net, bits) in enumerate(rows):
            yy = y + h - 40 - i * pitch
            if net in NETC:
                c.setFillColor(NETC[net])
                c.rect(x + 8, yy - 1, 6, 8, stroke=0, fill=1)
            text(c, x + 18, yy, lab, 8.6, "HEAD", INK)
            text(c, x + 96, yy, net, 8.4, "HEAD", NEON if net != "NC" else GREY)
            ln = wrap_px(bits, w - 30, 7.0)
            for k, l_ in enumerate(ln[:2]):
                text(c, x + 18, yy - 8.6 - k * 8, l_, 7.0, "ALT", GREY)
        LAB.block(x + 6, y + 4, x + w - 4, y + h - 4, "strip table")
    return f


def meter_rows(pod):
    """The checks, built from the copper netlist: [(title, text)]."""
    pins = PC._pins(pod)
    nl = PC.netlist(pod)
    j1 = pod.part("J1")
    hj = {n: j1.pins[n] for n in j1.pins}
    rows = []
    neigh = []
    for p in pod.parts:
        if p.kind in ("BOB", "BREAKOUT"):
            hs = sorted(p.pins.values(), key=lambda q: int(q[1:]))
            neigh.append(f"{hole(hs[0])}-{hole(hs[-1])}")
    rows.append(("NEIGHBOURS", "COPPER SIDE: touch every pair of neighbouring header joints along " + ", ".join(neigh) +
                 ": NO beep between any two."))
    rows.append(("3.3 V vs GROUND", f"{hole(hj['2'])} (J1 pin 2, 3.3 V) to {hole(hj['4'])} (pin 4, ground): NO steady beep. "
                 "A short chirp that dies away is the breakouts' capacitors charging: fine."))
    for net, pin in (("3V3", "2"), ("SDA", "3"), ("GND", "4"), ("SCL", "5")):
        grp = sorted(nl[net] - {("J1", pin)})
        tg = []
        for ref, pn in grp:
            hh = pins[(ref, pn)][0]
            if pod.lead and ref == pod.lead.ref:
                tg.append(f"the SHT45's {pn} pad (lead {next(c.colour for c in pod.lead.conductors if c.pad == pn)})")
            else:
                nm = f"{ref}'s lead" if ref == "R1" else (f"{ref} pin {pn}" if pn.isdigit() else f"{ref} {pn}")
                tg.append(f"{nm} ({hole(hh)})")
        rows.append((NET_WORD[net], f"{hole(hj[pin])} (J1 pin {pin}) BEEPS to each of: " + ", ".join(tg) + "."))
    jp, u1, r1 = pod.part("JP1"), pod.part("U1"), pod.part("R1")
    rows.append(("WRITE PROTECT", f"Shunt ON: {hole(u1.pins['WP'])} (U1 WP) BEEPS to {hole(hj['2'])} (3.3 V). Pull the shunt OFF: "
                 f"{hole(u1.pins['WP'])} to {hole(hj['4'])} reads 10 kOhm on the ohms range (R1) and no beep to {hole(hj['2'])}. "
                 "Push the shunt back ON."))
    rows.append(("PINS 1 AND 6", f"{hole(hj['1'])} and {hole(hj['6'])} (J1 pins 1, 6) beep to NOTHING: try {hole(hj['2'])}-"
                 f"{hole(hj['5'])} and the four rails."))
    return rows


def meter_page(pod, step):
    def f(c, pg):
        page(c, step, f"{pod.name} POD: METER BEFORE POWER", "CONTINUITY MODE. THE BOARD ALONE ON THE BENCH. NOTHING PLUGGED "
             "INTO J1.", pg, SLOGANS_P[6])
        g = Grid(1, 2, heights=[1.0, 1.2])
        x, y, w, h = panel(c, g.cell(0, 0), 1, [f"{board_name(pod)}, finished, from the front-left. Do the checks below in order."])
        a = Art(c, f"fin_{pod.name.lower()}", x + 40, y + 4, w - 260, h - 34, align="l")
        its = [("J1", *a.A("J1:mouth"), "rt", False), ("U1", *a.A("U1:chip"), "rt", False),
               ("JP1 SHUNT ON", *a.A("JP1:shunt"), "rt", False)]
        if pod.lead:
            its.append(("TH LEAD", *a.A("L:jacket"), "rt", False))
        else:
            its.append(("U2", *a.A("U2:sensor"), "rt", False))
        lanes(c, its, art_box(a, -2), size=8.5)
        x, y, w, h = panel(c, g.cell(0, 1), 2, ["Any beep where it says NO, or silence where it says BEEPS: stop. Photograph it.",
                                                "Report to Claude. Probe the joints on the COPPER SIDE."], warn=True)
        rows = meter_rows(pod)
        yy = y + h - 42
        for i, (t, s) in enumerate(rows):
            badge(c, x + 22, yy + 4, str(i + 1), 10)
            text(c, x + 40, yy, t, 11, "HEAD", INK)
            lines = wrap_px(s, w - 200, 8.4)
            for k, ln in enumerate(lines):
                text(c, x + 150, yy + 1 - 10.5 * k, ln, 8.4, "ALT", INK)
            tick_box(c, x + w - 24, yy - 3, 13)
            yy -= max(2, len(lines)) * 10.5 + 12
    return f


# ------------------------------------------------------------------ the port cable
def cable_crimp(c, pg):
    th = S.val("plug_6p")[0]
    lo, hi = S.val("pg7_seal")
    page(c, "C1", "PORT CABLE: GLANDS FIRST, THEN CRIMP", f"ROUND 6-CONDUCTOR, STRAIGHT THROUGH, UNDER {S.val('cable_max_m'):g} M. "
         f"A {th} MM PLUG WILL NOT PASS A PG-7.", pg, SLOGANS_P[7])
    g = Grid(2, 3, heights=[0.8, 0.8, 1.15])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, cap(
        f"1  Each end's gland body is in its wall first: the pod box's PG-7 #762 (Session Q) and the TX port's gland. The cable's",
        f"round jacket must be {lo:g}-{hi:g} mm across for a PG-7 to seal (else that end gets a PG-9). 2  Cut to length. 3  Push each",
        "BARE end in through its dome nut and gland body from OUTSIDE the box. No plug yet.", width=100))
    a = Art(c, "cab_glands", x + 20, y + 24, w - 40, h - 68)
    lanes(c, [("POD END: PG-7, DOME OUT", *a.A("pod_gland"), "up", False), ("TX END: ITS GLAND", *a.A("tx_gland"), "up", False),
              ("BARE END (POD BOX)", *a.A("pod_end"), "dn", False), ("BARE END (TX BOX)", *a.A("tx_end"), "dn", False)],
          art_box(a, -2), size=8.2)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, cap(
        "4  Only now crimp a 6P6C plug on each end, inside its box: strip the jacket to the crimp tool's gauge, lay the six",
        "conductors flat in the SAME colour order at both ends (hold each plug as below), push them to the tip, crimp.", width=100))
    a = Art(c, "cab_crimped", x + 20, y + 4, w - 40, h - 44)
    lanes(c, [("POD-END PLUG", *a.A("pod_plug"), "up", False), ("TX-END PLUG", *a.A("tx_plug"), "up", False)],
          art_box(a, -2), size=8.2)
    x, y, w, h = panel(c, g.cell(0, 2), 3, ["HOLD EVERY PLUG LIKE THIS: tip UP,", "gold contacts toward you, latch away.",
                                            "Contact 1 is on the LEFT."])
    a = Art(c, "plug_face", x + 40, y + 10, w - 80, h - 50)
    lanes(c, [(str(n), *a.A(f"P:c{n}"), "up", False) for n in range(1, 7)], art_box(a, -2), size=8.5)
    x, y, w, h = panel(c, g.cell(1, 2), 4, ["Write the colour at each contact,", "pod end first. The TX end must match."])
    for hx, hs_ in ((x + 40, "CONTACT"), (x + 96, "POD END"), (x + 186, "TX END")):
        text(c, hx, y + h - 40, hs_, 8.5, "MONO", GREY)
    for n in range(1, 7):
        yy = y + h - 60 - (n - 1) * 22
        text(c, x + 56, yy, str(n), 11, "HEAD", INK)
        c.setStrokeColor(INK)
        lw(c, 0.6)
        c.line(x + 96, yy - 3, x + 166, yy - 3)
        c.line(x + 186, yy - 3, x + 256, yy - 3)
    LAB.block(x + 38, y + h - 60 - 5 * 22 - 6, x + w - 6, y + h - 30, "colour table")


def cable_meter(c, pg):
    straight, rev = PC.cable_map("straight"), PC.cable_map("reversed")
    tx = PC.tx_port_map(1)
    e2e = PC.end_to_end(PODS_["UV"], 1, "reversed")
    bad = [f"TX pin {t} ({tx[t]}) lands on the pod's {pn}" for t, (pn, txn) in e2e.items() if pn != txn]
    page(c, "C2", "PORT CABLE: PIN TO PIN BEFORE POWER", "CONTINUITY MODE. THE CABLE ALONE, NO POD, NO TX. A REVERSED CABLE "
         "IS CAUGHT HERE OR NEVER.", pg, SLOGANS_P[6])
    g = Grid(2, 2, heights=[1.3, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Both plugs held the same way (tip UP,", "contacts toward you, latch away). Meter",
                                            "probe on one gold contact of each."])
    a = Art(c, "plug_face", x + 10, y + 10, w / 2 - 16, h - 60)
    b = Art(c, "plug_face", x + w / 2 + 6, y + 10, w / 2 - 16, h - 60)
    text(c, a.x + a.w / 2, a.y + a.h + 4, "POD END", 9, "HEAD", INK, "c")
    text(c, b.x + b.w / 2, b.y + b.h + 4, "TX END", 9, "HEAD", INK, "c")
    pa, pb = a.A("P:c1"), b.A("P:c1")
    c.setStrokeColor(NEON)
    lw(c, 1.6)
    p = c.beginPath()
    p.moveTo(*pa)
    p.curveTo(pa[0], pa[1] - 60, pb[0], pb[1] - 60, *pb)
    c.drawPath(p, stroke=1, fill=0)
    SL.HC.mark(*pa, "leader dot")
    SL.HC.mark(*pb, "leader dot")
    chip(c, (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2 - 50, "1 TO 1: BEEP", 9, "ALT", NEON, "c")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["Six checks, then six that must be silent.", "Tick each."])
    text(c, x + 40, y + h - 22, "POD CONTACT -> TX CONTACT", 8.5, "MONO", GREY)
    for i, n in enumerate(range(1, 7)):
        yy = y + h - 40 - i * 17
        text(c, x + 20, yy, f"{n}  ->  {straight[n]}", 11, "HEAD", INK)
        text(c, x + 96, yy, "BEEP", 9, "HEAD", NEON)
        text(c, x + 140, yy, f"{n}  ->  {rev[n]}", 11, "HEAD", INK)
        text(c, x + 216, yy, "SILENT", 9, "HEAD", GREY)
        tick_box(c, x + w - 20, yy - 2, 10)
    LAB.block(x + 14, y + h - 40 - 6 * 17, x + w - 24, y + h - 26, "table")
    yy = y + h - 40 - 6 * 17 - 6
    para(c, x + 14, yy, wrap_px("Also: no two neighbouring contacts of one plug beep (1-2, 2-3 ... 5-6).", w - 30, 8.4),
         8.4, 10.5, w=w - 20, what="also")
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, ["REVERSED (ROLLED) CABLE: the two plugs crimped as mirror images. Contact n then meets",
                                               "contact 7 - n at the far end (pod_checks.cable_map('reversed'))."], warn=True)
    text(c, x + 40, y + h - 22, "WHAT IT WOULD DO ON A PORT (pod_checks.end_to_end, reversed):", 9, "HEAD", INK)
    yy = y + h - 40
    for s in bad:
        text(c, x + 30, yy, "-  " + s, 9, "ALT", INK)
        yy -= 13
    para(c, x + 20, yy - 6, wrap_px("That puts 3.3 V on the clock line and ground on the data line. If 1 beeps to 6: cut BOTH "
                                    "plugs off, check the colour table on page C1, crimp again, meter again. Only a cable "
                                    "that passes every line above goes on a pod.", w - 40, 9.0), 9.0, 11.5, w=w - 30, what="fix")
    LAB.block(x + 20, yy, x + w - 10, y + h - 30, "bad")


# ------------------------------------------------------------------ the page list
def build_pages():
    PAGES.clear()
    add_page("00", "SESSION P: THE THREE POD BOARDS",
             ["parts-as-supplied", "parts:permaproto", "parts:eeprom_24lc32", "parts:ltr390", "parts:bmp581", "parts:sht45",
              "parts:bob", "parts:shunt", "parts:r1", "parts:wire", "parts:lead", "parts:cable"], cover)
    add_page("00", "BEFORE YOU START", ["tools", "steps"], before)
    add_page("01", "KNOW THE PERMA-PROTO'S TWO FACES", ["faces"], faces)
    add_page("02", "BUILD THE 3 JACK BREAKOUTS", ["bob-build"], bob_page)
    add_page("03", "BARO: CUT THE BMP581'S HEADER TO 6 PINS", ["BARO:header-cut"], bmp_cut)
    add_page("04", "HEADERS ONTO THE BREAKOUTS", ["headers"], headers)
    n = 5
    for name in ("TH", "BARO", "UV"):
        pod = PODS_[name]
        seq = [(f"{name} POD: 9 WIRES UNDERNEATH 1/2", [f"{name}:wires"] + [f"{name}:wire:w{i}" for i in (1, 2, 3, 4, 5, 6)],
                wires_page1),
               (f"{name} POD: 9 WIRES UNDERNEATH 2/2", [f"{name}:wires"] + [f"{name}:wire:w{i}" for i in (7, 8, 9)], wires_page2),
               (f"{name} POD: R1 AND THE WP HEADER JP1", [f"{name}:wp-header", f"{name}:r1"], low_page),
               (f"{name} POD: JACK J1 IN A1-A6", [f"{name}:jack-header", f"{name}:jack"], jack_page),
               (f"{name} POD: EEPROM U1 IN F5-F10", [f"{name}:eeprom"], eep_page)]
        if pod.lead:
            seq += [("TH POD: THE LEAD, SHT45 END", ["TH:lead", "TH:lead-sht45-end"], lead_sht_page),
                    ("TH POD: THE LEAD, POD END", ["TH:lead", "TH:lead-gland-order"], lead_pod_page)]
        else:
            seq += [(f"{name} POD: SENSOR U2 IN J10-J15", [f"{name}:sensor"], sensor_page)]
        seq += [(f"{name} POD: STRIP MAP", [f"{name}:strip-map"], strip_page),
                (f"{name} POD: METER BEFORE POWER", [f"{name}:meter"], meter_page)]
        for title, tags, mk in seq:
            st = f"{n:02d}"
            add_page(st, title, tags, mk(pod, st))
            n += 1
    add_page("C1", "PORT CABLE: GLANDS FIRST, THEN CRIMP", ["cable", "cable:crimp-order"], cable_crimp)
    add_page("C2", "PORT CABLE: PIN TO PIN BEFORE POWER", ["cable", "cable:continuity", "cable:reversed"], cable_meter)


build_pages()
STEP_LIST = []
for _st, _t, _tags, _fn in PAGES:
    if _st != "00" and (not STEP_LIST or STEP_LIST[-1][0] != _st):
        STEP_LIST.append((_st, _t))


def build(path, report=True):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session P: the three pod boards and the port cable")
    cv.setAuthor("PODS-R1")
    labels, holes, man = 0, [], []
    for i, (st, title, tags, fn) in enumerate(PAGES):
        pg = i + 1
        fn(cv, pg)
        iss = LAB.check() if report else []
        hi = SL.HC.check(pg) if report else []
        for m in hi:
            print("  HOLE", m)
        labels += len(iss)
        holes += hi
        SL.HC.reset()
        cv.showPage()
        man.append({"page": pg, "step": st, "title": title, "tags": tags, "label_issues": len(iss), "hole_issues": len(hi)})
    cv.save()
    return labels, holes, man


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "session-p-pods.pdf"
    bad, hole_issues, man = build(dest)
    stats = dict(SL.HC.STATS)
    json.dump({"pdf": dest.name, "page_count": len(man), "label_issues": bad, "hole_issues": len(hole_issues),
               "hole_stats": stats, "pages": man}, open(OUT / "session-p-manifest.json", "w"), indent=1)
    print("ok", len(man), "pages,", bad, "label issues,", len(hole_issues), "hole-alignment issues", stats)
    if hole_issues or bad:
        sys.exit("BUILD FAILED: label or hole-callout issues")
