"""Session 6: wire the backplane. Same flat-pack style and pipeline as Sessions 2-5.

Source of truth: hardware/tx-stack-r1/build/BACKPLANE.md, parsed by bpmd.py (every socket, key plug, part pin, bus
wire, lead and before-power check on these pages comes from it); geometry from layout/stack.py and
layout/muxleads.py via scenes6.py. Holes are named the way BACKPLANE.md names them: line, hole ("line 21, hole 7").
Lines 0-30 run along the board (line 0 at the cut edge), holes 1-38 across it (hole 1 at the lower long edge).

Starting point (Clint, 2026-11-19): the PAD3U is cut and the four 1x30 sockets are soldered at holes 13, 19, 27, 35.
Nothing else is on it. It sits loose in the base: lift it out.

Usage: .venv-pdf/bin/python make_session6.py [OUT_DIR]     (default: ../out; writes session6-all.pdf)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sheetlib import *          # noqa: F401,F403,E402  (page furniture, chips, leaders, Art, checks)
import sheetlib as SL           # noqa: E402
import bpmd                     # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / "layout"))
import evmleads as EL           # noqa: E402  (each EVM / pack lead's lane, as drawn and as layout check L7 tests it)

SL.LEADER_INK = True

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
WIRE = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
        "blue": HexColor("#2D6FD0"), "green": HexColor("#2E9E48"), "white": HexColor("#F2F2F2")}
DOT_RGB = {"blue": "#2D6FD0", "green": "#2E9E4F", "yellow": "#FFD400", "red": "#E8202A"}

FOOT6 = "SESSION 6: WIRE THE BACKPLANE. FROM build/BACKPLANE.md AND layout/stack.py."   # plain footer, every page

ORDER = ["XB4", "XB2", "XB1", "XB3"]                       # bottom to top: holes 13, 19, 27, 35
SOCK = bpmd.SOCKETS
MUXL = {p: (ln, hl, cut) for p, ln, hl, cut in bpmd.MUX_LEADS}
SILK = {"RESET": "RST", **{f"CH{k}.{s}": f"CH{k} {s}" for k in range(4) for s in ("SDA", "SCL")}}
MUX_COL = {"VIN": "red", "GND": "black", "SCL": "yellow", "SDA": "blue", "RESET": "green",
           **{f"CH{k}.SDA": "blue" for k in range(4)}, **{f"CH{k}.SCL": "yellow" for k in range(4)}}   # == scenes6.MUX_COL
NET_SHORT = {"3.3 V supply": "3.3 V", "ground": "GROUND", "I2C clock (SCL)": "SCL", "I2C data (SDA)": "SDA",
             "mux reset": "MUX RST", "cups (wind speed) pulse": "CUPS", "vane (wind direction) voltage": "VANE",
             "rain gauge pulse": "RAIN", "spare bus line (for the charger interrupt)": "SPARE (INT)",
             "charger battery + (after the shunt)": "CHG BAT +", "battery + junction (backplane lines 21-22)": "BAT + JUNCTION",
             "fuel gauge cell sense (VBAT)": "GAUGE SENSE", "charger system output (SYS)": "SYS"}


def short(net):
    if net in NET_SHORT:
        return NET_SHORT[net]
    import re
    m = re.match(r"sensor port (\d) (data|clock)", net)
    assert m, net
    return f"S{m.group(1)} {'SDA' if m.group(2) == 'data' else 'SCL'}"


def lh(ln, hl):
    return f"LINE {ln}, HOLE {hl}"


def ring(c, x, y, r=4.2, w=1.6):
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(HAZ)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def axis(c, a, lines=(), holes=(), side="l", fs=7.5, ly=None):
    """Line numbers under the drawing and hole numbers down one side ('l' or 'r'). x of each line number and y of
    each hole number come from the scene's L/H anchors; the row and column sit just outside the drawing (ly: the
    baseline of the line numbers, default just under the art). Blocks both strips for chips."""
    ly = a.y - 9 if ly is None else ly
    for n in lines:
        x = a.A(f"L{n}")[0]
        text(c, x, ly, str(n), fs, "ALT", GREY, "c")
    if lines:
        LAB.block(a.x, ly - 2, a.x + a.w, ly + fs, "line numbers")
    hx = a.x - 4 if side == "l" else a.x + a.w + 4
    for n in holes:
        y = a.A(f"H{n}")[1]
        text(c, hx, y - fs * 0.36, str(n), fs, "ALT", GREY, "r" if side == "l" else "l")
    if holes:
        x0 = hx - 12 if side == "l" else hx
        LAB.block(x0, a.y, x0 + 12, a.y + a.h, "hole numbers")


def table(c, x, y, cols, rows, size=8.6, lead=11.2, head=True, colours=None):
    """Plain table: cols = [(title, x offset, anchor)], rows = lists of strings. Returns the y below it."""
    yy = y
    if head:
        for t, dx, an in cols:
            text(c, x + dx, yy, t, size, "HEAD", INK, an)
        yy -= lead + 1
    for i, r in enumerate(rows):
        for k, ((t, dx, an), v) in enumerate(zip(cols, r)):
            if colours and k == 0 and colours[i]:
                c.setFillColor(WIRE[colours[i]])
                c.setStrokeColor(INK)
                lw(c, 0.6)
                c.rect(x + dx - 12, yy - 1, 8, 7.5, stroke=1, fill=1)
            text(c, x + dx, yy, v, size, "ALT", INK, an)
        yy -= lead
    return yy


# ------------------------------------------------------------------ 00 cover
def cover(c, pg):
    page(c, "00", "SESSION 6: WIRE THE BACKPLANE",
         "SOCKETS ARE ON. NOW KEY PLUGS, PARTS, THE MUX, LINKS, LEADS AND 24 BUS WIRES. NO POWER TODAY.", pg, FOOT6)
    g = Grid(2, 3, heights=[1.3, 1.05, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS (build/BACKPLANE.md sections 2-5). LAY THEM OUT BEFORE YOU HEAT THE IRON.")
    bus_mm = sum(r[4] for r in bpmd.BUS)
    lead_mm = sum(v[2] for p, v in MUXL.items() if not p.startswith("CH")) + sum(j[3] for j in bpmd.JUMPERS)
    items = [("MALE HEADER STOCK\n7 pins: 4 key plugs, XJ1 x 3", "p_header"),
             ("R7, R8: 100 OHM AXIAL\n(brown black brown)", "p_res"),
             ("U4 PCA9548 MUX\nAdafruit #5626", "p_mux"),
             ("4 x QT CABLE, Adafruit #4209\nJST SH to male pins, 150 mm", "p_qt"),
             ("DOUBLE-SIDED FOAM PAD\n1 mm thick, about 32 x 11 mm", "p_foam"),
             (f"22 AWG SOLID, Adafruit 1311\nbare {bus_mm} mm; 8 insulated\nleads, {lead_mm} mm", "p_wire22"),
             ("24 AWG STRANDED, 5 x 100 mm\n3 red/black band, black,\nwhite/red", "p_wire24")]
    cw, rh = w / 4, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 4, i // 4
        X0, Y0 = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X0 + 10, Y0 + 40, cw - 20, rh - 48)
        chip(c, X0 + cw / 2, Y0 + 26, name, 8.2, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "FLUSH CUTTERS", "WIRE STRIPPER (22 AND 24 AWG)", "MULTIMETER (CONTINUITY)",
             "STEEL RULER (CUT LENGTHS)", "SMALL FLAT FILE", "PLIERS (PULL HEADER PINS)",
             "PAINT PENS OR DOTS: BLUE GREEN YELLOW RED", "MASKING TAPE + A PEN (FLAGS)", "THIS SHEET, PRINTED"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 10.5, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  KEY PLUGS AND COLOUR DOTS", "02  XJ1, R7 AND R8 ON THE FRONT", "03  THE MUX: A0, SW1, 5 LEADS, 4 CABLES",
             "04  THE MUX ON FOAM, ITS LEADS IN", "05  THREE LINKS ON THE COPPER SIDE",
             "06  EVM AND PACK LEADS (BOARD END)", "07  BUS WIRES, LINES 1-18", "08  BUS WIRES, LINES 19-23, 26",
             "09  METER CHECKS", "10  REPORT"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 16 - i * (h - 10) / len(steps), s, 12.5, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["HOLES ARE NAMED BY LINE AND HOLE, AS IN BACKPLANE.md: LINE 21, HOLE 7. LINES 0-30 ALONG, HOLES 1-38 ACROSS.",
             "FRONT = THE FACE WITH THE SOCKETS. COPPER SIDE = THE OTHER FACE. SEEN FROM THE COPPER SIDE, LINE 0 IS ON THE RIGHT.",
             "LEADS BEFORE BUS WIRES: EACH LEAD GOES IN FROM THE COPPER SIDE AND IS SOLDERED ON THE FRONT.",
             "THE PACK IS NEVER CONNECTED TODAY. THE EVM AND PACK ENDS OF THE LEADS WAIT FOR THE EVM SESSION."]
    for i, s in enumerate(rules):
        yy = y + h - 10 - i * (h - 6) / 4
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 8.8, "ALT", INK)


# ------------------------------------------------------------------ 00 what you are building
def top_lines(a):
    """Baseline for line numbers along the top edge of a whole-board view (the leads hang off the bottom)."""
    return a.A("Lt0")[1] + 1


def built(c, pg):
    page(c, "00", "WHAT YOU ARE BUILDING", "THE BACKPLANE, DONE: BOTH FACES. THIS IS WHERE THE SESSION ENDS.", pg,
         FOOT6)
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["FRONT (the socket face). Key plugs,",
                                             "colour dots, XJ1, R7 and R8."])
    a = Art(c, "ov_front", x + 22, y + 14, w - 36, h - 66, valign="t")
    axis(c, a, range(0, 31, 5), range(5, 39, 5), side="l", ly=top_lines(a))
    for ref in ORDER:
        px, py = a.A(f"sock_{ref}")
        chip(c, a.x + a.w * 0.62, py + 5, f"{ref} ({SOCK[ref]['card']})", 8.5, "ALT", INK, "c")
    label(c, a.x + a.w - 6, a.y + a.h * 0.12, "R7, R8", *a.A("R7"), 8.5, anchor="r")
    label(c, a.x + 6, a.y + a.h * 0.12, "XJ1", *a.A("xj_7"), 8.5)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["COPPER SIDE (turned over: line 0 is", "on the right). Bus wires, mux, leads."])
    a = Art(c, "ov_copper", x + 14, y + 14, w - 36, h - 66, valign="t")
    axis(c, a, range(0, 31, 5), range(5, 39, 5), side="r", ly=top_lines(a))
    label(c, a.x + 4, a.y + a.h * 0.08, "U4 MUX ON FOAM", *a.A("mux"), 8.5)


# ------------------------------------------------------------------ 01 key plugs and dots
def keys(c, pg):
    page(c, "01", "KEY PLUGS AND COLOUR DOTS", "BACKPLANE.md SECTION 2. ONE PIN IN ONE CONTACT PER SOCKET. NO SOLDER.",
         pg, FOOT6)
    g = Grid(3, 3, heights=[1.55, 0.95, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 3), 1, [
        "FRONT. Each socket gets a key plug in the contact its own card is missing. Contact n is on line n.",
        "Only that card fits. Any other card stubs on the plug and stops at the mouth."])
    a = Art(c, "k_front", x + 44, y + 16, 260, h - 24, align="l")
    axis(c, a, range(0, 31, 5), [13, 19, 27, 35], side="l")
    for ref in ORDER[::-1]:
        d = SOCK[ref]
        px, py = a.A(f"kc_{ref}")
        r = chip(c, a.x + a.w + 16, py - 3, f"{ref}: CONTACT {d['key']} (LINE {d['key']})", 9.5, "ALT", NEON)
        leader(c, r, px + 2, py, dot=True)
    tx = a.x + a.w + 16
    yy = a.y + 40
    text(c, tx, yy + 14, "SOCKET  CARD  KEY  DOT", 9, "HEAD", INK)
    for i, ref in enumerate(ORDER):
        d = SOCK[ref]
        text(c, tx, yy - i * 11, f"{ref}  {d['card']}  {d['key']}  {d['colour']}", 9, "ALT", INK)
    LAB.block(tx - 2, yy - 36, tx + 150, yy + 24, "key table")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Pull one pin out of the male", "header stock with pliers."])
    a = Art(c, "k_pin", x + 6, y + 4, w - 12, h - 30, valign="b")
    label(c, x + w - 8, y + h - 16, "ONE PIN", *a.A("loose"), 9, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Long end down into the contact.", "Push until it bottoms."])
    a = Art(c, "k_push", x + 6, y + 4, w - 12, h - 30, valign="b")
    label(c, x + w - 8, y + h - 16, "XB4 CONTACT 30", *a.A("mouth"), 9, anchor="r")
    x, y, w, h = panel(c, g.cell(2, 1), 4, ["Cut flush with the mouth. File", "the cut flat. Nothing stands proud."])
    a = Art(c, "k_flush", x + 6, y + 4, w - 12, h - 30, valign="b")
    label(c, x + w - 8, y + h - 16, "FLUSH", *a.A("plug_top"), 9, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 2, 3), 5, [
        "Colour dots: paint or stick one beside each socket on the front, and one on the base beside that card's slot.",
        "Same colour as the dot on the card's front edge. Then, if your cards have headers, try each card in each wrong",
        "socket by hand, off the base. Each one must stop at the mouth. The plug's pad gets no solder, no wire, no lead."])
    for i, ref in enumerate(ORDER):
        d = SOCK[ref]
        cx = x + 60 + i * (w - 70) / 4
        cy = y + h / 2 + 2
        c.setFillColor(HexColor(DOT_RGB[d["colour"]]))
        c.setStrokeColor(INK)
        lw(c, 1)
        c.circle(cx, cy, 9, stroke=1, fill=1)
        text(c, cx + 16, cy + 2, f"{ref} / {d['card']}", 11, "HEAD", INK)
        text(c, cx + 16, cy - 10, d["colour"].upper(), 9, "ALT", GREY)


# ------------------------------------------------------------------ 02 front parts
def front_parts(c, pg):
    page(c, "02", "XJ1, R7 AND R8 ON THE FRONT", "BACKPLANE.md SECTION 3. PARTS ON THE FRONT, SOLDERED ON THE COPPER SIDE.",
         pg, FOOT6)
    g = Grid(2, 2, heights=[1.3, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "FRONT, lines 0-26, holes 4-14 (XB4 along hole 13). Ringed: every hole that gets a part today. XJ1 is three",
        "single pins (the charger I2C lead from EVM J8 plugs on later). R7 lies flat, R8 lies on a slant."])
    a = Art(c, "f_parts", x + 22, y + 16, w - 30, h - 62, valign="b")
    axis(c, a, range(0, 27), range(4, 15), side="l")
    k = 0
    for ref, note, pin, ln, hl, net in bpmd.FRONT:
        px, py = a.A(f"h{ln}_{hl}")
        ring(c, px, py)
        if ref == "XJ1":
            r = chip(c, px, a.y + a.h + 10 + 16 * (k % 2), f"XJ1 {pin.upper()}: {ln}, {hl}", 8, "ALT", INK, "c")
            k += 1
            leader(c, r, px, py + 4.2, dot=False)
    r = chip(c, a.A("h17_14")[0] if "h17_14" in a.anchors else a.x + a.w * 0.62, a.y + a.h + 26,
             "R7: 21, 7 TO 24, 7", 8, "ALT", INK, "c")
    leader(c, r, *a.A("R7"))
    r = chip(c, a.x + a.w - 4, a.y + a.h + 26, "R8: 22, 8 TO 23, 11", 8, "ALT", INK, "r")
    leader(c, r, *a.A("R8"))
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["XJ1: three pins from the header stock, the",
                                             "short end through, plastic on the front.",
                                             "Solder on the copper side. Lines 2, 7, 10."])
    Art(c, "f_xj_iso", x + 36, y + 4, w - 42, h - 8)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["R7 21,7 to 24,7. R8 22,8 to 23,11, legs bent",
                                             "to the span. Solder on the copper side, trim.",
                                             "Leave R7's leg at 24,7 about 5 mm long."])
    a = Art(c, "f_res_iso", x + 36, y + 4, w - 42, h - 8)
    label(c, x + w - 8, y + 18, "24, 7: LEAVE 5 MM", *a.A("r7_free"), 9, color=NEON, anchor="r")


# ------------------------------------------------------------------ 03 the mux on the bench
CH_PADS = [f"CH{k}.{s}" for k in range(4) for s in ("SDA", "SCL")]
HDR_PADS = ["VIN", "GND", "SCL", "SDA", "RESET"]
HDR_TOP = max(MUXL[p][1] for p in HDR_PADS)            # the header leads' rows (BACKPLANE.md section 5): 14-18
HDR_ROWS = f"holes {min(MUXL[p][1] for p in HDR_PADS)}-{HDR_TOP}"


def mux1(c, pg):
    page(c, "03", "THE MUX  1/2: AS SUPPLIED", "ADAFRUIT #5626, PCA9548. BRIDGE A0 (ADDRESS 0x71). SW1 TO V+.", pg, FOOT6)
    g = Grid(2, 2, heights=[1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["TOP FACE, as it comes. Set SW1 to the V+",
                                             "side (read the silk beside it). The",
                                             "upstream port and channels 4-7 stay empty."])
    a = Art(c, "m_top", x + 10, y + 10, w - 20, h - 50)
    label(c, x + 44, y + h - 18, "UPSTREAM QT", *a.A("up_qt"), 9)
    label(c, x + w - 10, y + h - 18, "SW1", *a.A("sw1"), 9, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["BACK FACE, as it comes. Bridge A0 with a",
                                             "blob of solder: address 0x71. Leave A1, A2.",
                                             "Nothing else on this face gets solder."])
    a = Art(c, "m_back", x + 10, y + 10, w - 20, h - 50)
    label(c, x + w - 10, y + h - 18, "A0: BRIDGE IT", *a.A("a0"), 9, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "TOP FACE. Five header holes take 22 AWG leads. Channels 0-3 are the four QT ports on the header's VIN side:",
        "each takes a #4209 cable. Places from Adafruit's own board file (layout/muxleads.py). Cut lengths: the lead",
        "end to end; the cable from the back of its plug."])
    a = Art(c, "m_top", x + 30, y + 10, 230, h - 50, align="l")
    for k in range(4):
        px, py = a.A(f"qt_{k}")
        r = chip(c, px, a.y - 2, f"CH{k}", 8, "ALT", INK, "c")
        leader(c, r, px, py)
    for pad in HDR_PADS:
        px, py = a.A(f"jp_{pad}")
        r = chip(c, a.x + a.w + 6, py - 3, SILK.get(pad, pad), 8, "ALT", INK, "l")
        leader(c, r, px, py)
    tx = a.x + a.w + 50
    cols = [("WHAT", 0, "l"), ("TO", 70, "l"), ("CUT", 190, "r")]
    rows = [[SILK.get(p, p) + " lead", lh(*MUXL[p][:2]).lower(), f"{MUXL[p][2]} mm"] for p in HDR_PADS]
    rows += [[f"CH{k} cable", f"lines {MUXL[f'CH{k}.SDA'][0]}, {MUXL[f'CH{k}.SCL'][0]}, hole 10", f"{MUXL[f'CH{k}.SDA'][2]} mm"]
             for k in range(4)]
    table(c, tx + 14, y + h - 14, cols, rows, 8, 11.5, colours=[MUX_COL[p] for p in HDR_PADS] + [None] * 4)
    LAB.block(tx, y + 20, x + w, y + h, "lead table")


def mux2(c, pg):
    page(c, "03", "THE MUX  2/2: 5 LEADS, 4 CABLES", "HEADER: 22 AWG SOLID (ADAFRUIT 1311). CHANNELS 0-3: QT CABLES #4209. STRIP 3 MM.",
         pg, FOOT6)
    g = Grid(2, 2, heights=[1.35, 0.65])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["ONE CABLE. Cut the pin end off at the length",
                                             "in the table, from the plug's back. Strip",
                                             "3 mm off blue and yellow. Cut red and black",
                                             "off 3 mm from the plug, tape them together."])
    a = Art(c, "c_cable", x + 36, y + 30, w - 46, h - 60)
    label(c, x + w - 8, y + h - 16, "PLUG", *a.A("plug_0"), 9, anchor="r")
    label(c, x + 44, y + h - 16, "RED + BLACK, TAPED", *a.A("tape_0"), 9, color=NEON)
    label(c, x + 8, y + 18, "BLUE SDA, YELLOW SCL: 3 MM BARE", *a.A("end_CH0.SCL"), 9)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["TOP FACE, done. Header leads in from the top,",
                                             "out past the end, tails cut flush on the",
                                             "back. The four cables plug in now or after",
                                             "the foam: push each plug fully home."])
    Art(c, "m_top_done", x + 36, y + 10, w - 46, h - 46)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "Header lead colours: VIN red, GND black, SCL yellow, SDA blue, RST green. Nothing else gets soldered to the mux.",
        "Mark each cable with its channel: four cables look alike."])
    rows = [("CH0 CABLE", "sensor port 1 (S1): blue to line 3, yellow to line 4"),
            ("CH1 CABLE", "sensor port 2 (S2): blue to line 8, yellow to line 9"),
            ("CH2 CABLE", "sensor port 3 (S3): blue to line 13, yellow to line 14"),
            ("CH3 CABLE", "sensor port 4 (S4): blue to line 17, yellow to line 18"),
            ("VIN GND SCL SDA RST", "the main bus (line, hole): " + ", ".join(f"{MUXL[p][0]},{MUXL[p][1]}" for p in HDR_PADS))]
    for k in range(4):
        assert (MUXL[f"CH{k}.SDA"][0], MUXL[f"CH{k}.SCL"][0]) == ((3, 4), (8, 9), (13, 14), (17, 18))[k]
    for i, (k, v) in enumerate(rows):
        yy = y + h - 16 - i * (h - 14) / 5
        text(c, x + 50, yy, k, 11, "HEAD", INK)
        text(c, x + 230, yy, v, 10, "ALT", INK)


# ------------------------------------------------------------------ 04 mux on foam

def stack_chips(labs, rows=4, gap=2.0):
    """Rows and anchors for chips over a row of leaders. labs: (leader x, chip width). Returns one
    (row, anchor) per label so no chip overlaps another and no leader runs through a chip below it."""
    span = {"c": lambda x, w: (x - w / 2, x + w / 2), "l": lambda x, w: (x - 4 - 2.6, x - 4 - 2.6 + w),
            "r": lambda x, w: (x + 4 + 2.6 - w, x + 4 + 2.6)}
    out = []

    def ok(row, x0, x1, px):
        for (rw, anc), (q, w) in zip(out, labs):
            a0, a1 = span[anc](q, w)
            if rw == row and a0 - gap < x1 and x0 < a1 + gap:
                return False
            if rw < row and a0 - gap < px < a1 + gap:
                return False
            if rw > row and x0 - gap < q < x1 + gap:
                return False
        return True

    def go(k):
        if k == len(labs):
            return True
        px, w = labs[k]
        for row in range(rows):
            for anc in "clr":
                x0, x1 = span[anc](px, w)
                if ok(row, x0, x1, px):
                    out.append((row, anc))
                    if go(k + 1):
                        return True
                    out.pop()
        return False

    if not go(0):
        raise SystemExit("stack_chips: no layout fits")
    return out

def mux_mount(c, pg):
    page(c, "04", "THE MUX ON FOAM. ITS LEADS AND CABLES IN", "COPPER SIDE. BACKPLANE.md SECTION 5. LEADS IN FROM THE COPPER SIDE.",
         pg, FOOT6)
    g = Grid(2, 2, heights=[1.45, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        f"COPPER SIDE, lines 0-20, holes 1-{HDR_TOP} (line 0 on the right). The mux over holes 2-9, back face down on the",
        "foam, the channel 0-3 edge toward hole 10. Each cable wire (SDA0 = channel 0's blue) into its ringed hole 10.",
        f"Each header lead up its own line over XB4's tails, then along its own row ({HDR_ROWS}) to its ringed hole.",
        "Solder on the front. Chips name the line."])
    a = Art(c, "m_mounted", x + 26, y + 18, w - 50, h - 60, valign="b")
    axis(c, a, range(0, 21), range(1, HDR_TOP + 1), side="r")
    items = sorted(((a.A(f"h{ln}_{hl}")[0], p, ln, hl) for p, (ln, hl, cut) in MUXL.items()), reverse=True)
    top = a.y + a.h + 6
    labs = []
    for px, p, ln, hl in items:
        py = a.A(f"h{ln}_{hl}")[1]
        ring(c, px, py, 3.4, 1.3)
        tag = f"{p[4:]}{p[2]}" if p.startswith("CH") else SILK.get(p, p)
        s = f"{tag} {ln}"
        labs.append((px, py, s, pdfmetrics.stringWidth(s, "ALT", 7.6) + 5.2))
    for (px, py, s, wd), (row, anc) in zip(labs, stack_chips([(l[0], l[3]) for l in labs])):
        tx = {"c": px, "l": px - 4, "r": px + 4}[anc]
        r = chip(c, tx, top + row * 12, s, 7.6, "ALT", INK, anc)
        leader(c, (px - 0.01, r[1], px + 0.01, r[3]), px, py + 3.4, dot=False)   # straight down from the chip
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Foam in the middle of the back face, clear of",
                                             "the header holes. 1 mm, no thicker: the mux",
                                             "and its plugs must clear the floor."])
    a = Art(c, "m_iso", x + 40, y + 4, w - 46, h - 8)
    label(c, x + 8, y + 16, "FOAM", *a.A("foam"), 9)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Order: stick it down, plug the cables in,",
                                             "route each wire as drawn, push it through",
                                             "its hole, solder on the front, clip."])
    rows = [[SILK.get(p, p), f"{MUXL[p][0]}, {MUXL[p][1]}"] for p in CH_PADS + HDR_PADS]
    half = (len(rows) + 1) // 2
    for col in range(2):
        rs = rows[col * half:(col + 1) * half]
        table(c, x + 44 + col * 120, y + h - 14, [("WIRE", 0, "l"), ("LINE, HOLE", 50, "l")], rs, 9, 11.5)


# ------------------------------------------------------------------ 05 links
def links(c, pg):
    page(c, "05", "THREE LINKS ON THE COPPER SIDE", "22 AWG SOLID, INSULATED. IN FROM THE COPPER SIDE, SOLDERED ON THE FRONT.",
         pg, FOOT6)
    g = Grid(2, 2, heights=[1.3, 0.9])
    J = {a: (b, what, cut) for a, b, what, cut in bpmd.JUMPERS}
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["COPPER SIDE, lines 17-24, holes 2-9.",
                                             f"19,5 to 20,5 and 21,5 to 22,5: {J[(19, 5)][2]} mm each.",
                                             "Red. Lie them flat."])
    a = Art(c, "l_power", x + 22, y + 18, w - 50, h - 50)
    axis(c, a, range(17, 25), range(2, 10), side="r")
    for (ln, hl) in ((19, 5), (20, 5), (21, 5), (22, 5)):
        ring(c, *a.A(f"h{ln}_{hl}"))
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["The same two, from above the copper side."])
    Art(c, "l_iso", x + 6, y + 4, w - 12, h - 36, valign="b")
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        f"COPPER SIDE, lines 0-14, holes 35-38. 2,38 to 12,38: {J[(2, 38)][2]} mm, black. It joins the two bus ground lines",
        "(2 and 12). Hole 38 is also where those two bus wires end."])
    a = Art(c, "l_ground", x + 50, y + 22, w - 100, h - 34)
    axis(c, a, range(0, 15), range(35, 39), side="r")
    for (ln, hl) in ((2, 38), (12, 38)):
        ring(c, *a.A(f"h{ln}_{hl}"))


# ------------------------------------------------------------------ 06 EVM and pack leads
EVM_TXT = {"F5 lead +": ("PACK +", "red", "black"), "U1 battery + (J5 BATTERY)": ("J5 BAT", "red", "black"),
           "U1 system out (J3 SYS)": ("J3 SYS", "red", "black"), "U1 system ground (J3 GND)": ("J3 GND", "black", None),
           "U1 battery sense (J5 SNS_BATP)": ("J5 SNS", "white", "red")}


def evm(c, pg):
    page(c, "06", "EVM AND PACK LEADS: BOARD END ONLY", "24 AWG STRANDED, 100 MM EACH. THE FAR ENDS STAY LOOSE, FLAGGED AND TAPED.",
         pg, FOOT6)
    g = Grid(3, 2, heights=[1.2, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0, 3), 1, [
        f"COPPER SIDE, lines 0-30, holes 1-{HDR_TOP}. Four leads in from this side, soldered on the front (ringed). J5 SNS",
        "has no hole of its own: lap it onto R7's long leg at line 24, hole 7, and solder. The leads hang off the",
        "hole-1 edge."])
    a = Art(c, "e_leads", x + 40, y + 6, w - 120, h - 22, valign="t")
    axis(c, a, range(0, 31, 2), range(1, HDR_TOP + 1, 2), side="r", ly=a.A(f"H{HDR_TOP}")[1] + 8)
    for frm, ln, hl, what, to in bpmd.EVM:
        if hl != 7:
            ring(c, *a.A(f"h{ln}_{hl}"))
    label(c, x + 8, a.y + a.h * 0.55, "R7'S LONG LEG", *a.A("r7_free"), 8.5)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["The five, from BACKPLANE.md", "section 3."])
    yy = y + h - 34
    for frm, ln, hl, what, to in bpmd.EVM:
        flag, body, band = EVM_TXT[frm]
        c.setFillColor(WIRE[body])
        c.setStrokeColor(INK)
        lw(c, 0.6)
        c.rect(x + 14, yy - 22, 7, 30, stroke=1, fill=1)
        if band:
            c.setFillColor(WIRE[band])
            c.rect(x + 14, yy - 4, 7, 5, stroke=1, fill=1)
        text(c, x + 30, yy, flag, 11, "HEAD", INK)
        where = f"line {ln}, hole {hl}" if hl != 7 else "R7's leg, line 24, hole 7"
        text(c, x + 30, yy - 11, where, 8.5, "ALT", INK)
        text(c, x + 30, yy - 21, EL.WAY[(ln, hl)], 7.5, "ALT", GREY)
        yy -= (h - 40) / 5
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Each far end: a tape flag with its",
                                             "name, the bare end taped over.",
                                             "Session 7 cuts and fits them."])
    a = Art(c, "e_flag", x + 6, y + 6, w - 12, h - 40, valign="b")
    label(c, x + w - 8, y + h - 18, "TAPE OVER THE END", *a.A("tape"), 8.5, anchor="r")
    x, y, w, h = panel(c, g.cell(2, 1), 4, ["The pack is never connected", "today. Nothing goes to the", "EVM yet either."],
                       warn=True)
    for i, s_ in enumerate(["Cut each lead 100 mm.", "Strip 3 mm at the board end.",
                            "Leave the far end in its", "insulation, taped over.", "",
                            "Keep each lead in its own lane", "as drawn. The backplane sits on", "the base's support pad under",
                            "line 20, hole 2: no lead", "runs over it."]):
        text(c, x + 14, y + h - 46 - i * 13, s_, 9.5, "ALT", INK)


# ------------------------------------------------------------------ 07-08 bus wires
def bus1(c, pg):
    page(c, "07", "BUS WIRES  1/2: LINES 1-18", "BARE 22 AWG SOLID (ADAFRUIT 1311, STRIPPED). COPPER SIDE. SOLDER AT EVERY LISTED HOLE.",
         pg, FOOT6)
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["COPPER SIDE. Top: lines 0-20, holes 8-20,",
                                             "each wire's first hole ringed. Bottom:",
                                             "all done, each wire straight along its line."])
    a = Art(c, "b_start", x + 12, y + h - 196, w - 34, 176)
    axis(c, a, range(0, 21, 2), range(8, 21, 2), side="r")
    for ln, _n, a_, _b, _c, _h in bpmd.BUS:
        if ln <= 18:
            ring(c, *a.A(f"bot{ln}"), 2.6, 1.1)
    a = Art(c, "b_all", x + 12, y + 6, w - 34, h - 236)
    axis(c, a, range(0, 31, 5), range(5, 39, 5), side="r", ly=top_lines(a))
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["Cut = span + 10 mm. Lay, tack the first",
                                             "and last hole, then every hole listed."])
    rows = [[str(ln), short(net), f"{a_}-{b_}", f"{cut}", ", ".join(map(str, holes))]
            for ln, net, a_, b_, cut, holes in bpmd.BUS if ln <= 18]
    yy = table(c, x + 10, y + h - 44, [("LINE", 0, "l"), ("BUS", 24, "l"), ("HOLES", 84, "l"), ("MM", 128, "r"),
                                       ("SOLDER AT", 136, "l")], rows, 7.6, 11.6)
    yy -= 16
    at13 = [ln for ln, _n, a_, _b, _c, _h in bpmd.BUS if ln <= 18 and a_ == 13]
    for s_ in ["Strip the 1311 wire bare. Pull it straight", "with pliers before you cut it.",
               f"Lines {', '.join(map(str, at13[:-1]))} and {at13[-1]} start at hole 13.",
               "The rest start at hole 10 or 11, where", "the mux cables and XJ1 pins already sit.",
               "Where a mux wire or XJ1 pin is in a listed", "hole, the wire's joint takes it too.",
               "No wire touches its neighbour."]:
        text(c, x + 10, yy, s_, 9, "ALT", INK)
        yy -= 12


def bus2(c, pg):
    page(c, "08", "BUS WIRES  2/2: LINES 19-23 AND 26", "B4'S POWER LINES. EVERY OTHER CONTACT ON LINES 19-30 IS AN ISOLATED PAD.",
         pg, FOOT6)
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["COPPER SIDE, lines 17-30. Short wires",
                                             "from hole 5 or 6 (11 on line 23) to XB4",
                                             "at hole 13. Ringed: isolated pads,",
                                             "no wire, nothing joined to them."])
    a = Art(c, "b_power", x + 30, y + 16, w - 44, h - 50, valign="b")
    axis(c, a, range(17, 31), [3, 5, 7, 9, 11, 13, 19, 27, 35], side="l")
    for ref, lines in bpmd.ISOLATED.items():
        for ln in lines:
            ring(c, *a.A(f"h{ln}_{SOCK[ref]['hole']}"), 3.2, 1.1)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["The six wires (BACKPLANE.md section 4)."])
    rows = [[str(ln), short(net), f"{a_}-{b_}", f"{cut}", ", ".join(map(str, holes))]
            for ln, net, a_, b_, cut, holes in bpmd.BUS if ln > 18]
    yy = table(c, x + 10, y + h - 44, [("LINE", 0, "l"), ("BUS", 24, "l"), ("HOLES", 112, "l"), ("MM", 150, "r"),
                                       ("AT", 158, "l")], rows, 8, 12)
    yy -= 14
    text(c, x + 10, yy, "ISOLATED PADS (soldered to their", 10, "HEAD", INK)
    text(c, x + 10, yy - 12, "contact only):", 10, "HEAD", INK)
    yy -= 30
    for ref in ORDER:
        lines = bpmd.ISOLATED[ref]
        s_ = f"{ref} (hole {SOCK[ref]['hole']}): lines " + (
            "19-30" if lines == list(range(19, 31)) else ", ".join(map(str, lines)))
        text(c, x + 10, yy, s_, 9, "ALT", INK)
        yy -= 13
    yy -= 8
    for s_ in ["The key plugs' contacts are isolated", "pads too: XB4 30, XB2 28, XB1 27, XB3 29.",
               "Lines 19 and 20 join at hole 5, and so do", "21 and 22 (step 05)."]:
        text(c, x + 10, yy, s_, 9, "ALT", INK)
        yy -= 12


# ------------------------------------------------------------------ 09 meter checks, 10 report
def checks(c, pg):
    page(c, "09", "METER BEFORE ANY CARD", "CONTINUITY MODE. THE BACKPLANE ALONE ON THE BENCH. NO CARD, NO EVM, NO PACK.",
         pg, FOOT6)
    g = Grid(1, 2, heights=[0.3, 1.7])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Probe the solder joints on the copper side. Hole numbers as in steps 07-08."])
    text(c, x + 44, y + h - 20, "From build/BACKPLANE.md, \"Before power\".", 10, "ALT", INK)
    text(c, x + 44, y + h - 34, "A beep where it says OPEN, or silence where it says BEEP: stop, take a photo, tell Claude.",
         10, "ALT", NEON)
    rows = [("1", "EACH BUS WIRE", "End to end: its first soldered hole to its last. BEEP. All 24."),
            ("2", "NEIGHBOURS", "Each line against the line beside it: OPEN. Except 19-20 and\n"
                                "21-22 (BEEP, joined at hole 5) and 22-23 (about 100 ohm, R8)."),
            ("3", "LINE 2 TO LINE 12", "BEEP, reads 0 ohm: both ground, joined at hole 38."),
            ("4", "3.3 V TO GROUND", "Line 1 against line 2: OPEN. A short chirp that dies away is the\n"
                                     "mux's capacitor charging: that's fine."),
            ("5", "LINES 19-30", "B4's contacts on 19-23 and 26 beep to their line's wire.\n"
                                 "Every other contact there, key plugs included, beeps to nothing."),
            ("6", "J3 GND LEAD", "Peel the tape off its far end for a moment: it beeps to line 12 and line 2.")]
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Tick each box as you go."], warn=True)
    rh = (h - 46) / len(rows)
    for i, (n, t, s) in enumerate(rows):
        yy = y + h - 50 - i * rh
        badge(c, x + 52, yy + 4, n, 10)
        text(c, x + 70, yy, t, 13, "HEAD", INK)
        for k, ln in enumerate(s.split("\n")):
            text(c, x + 200, yy + 1 - 12 * k, ln, 9.3, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 26, yy - 4, 14, 14, stroke=1, fill=0)


REPORT_ROWS = [("KEY PLUGS IN, FLUSH, NO SOLDER", "Y / N", "the wrong-card test is Session 8 step 04"),
               ("FOUR QT CABLES SEATED", "Y / N", "red and black taped, nothing bare near the mux"),
               ("FOAM THICKNESS UNDER THE MUX", "mm", "1 mm or less"),
               ("METER CHECKS 1-6 ALL PASS", "Y / N", "step 09"),
               ("ANY LEAD CUT TOO LONG OR SHORT", "mm", "which one, and the length that fit"),
               ("PHOTO OF EACH FACE", "SENT", "front and copper side")]


def report(c, pg):
    page(c, "10", "REPORT THE BACKPLANE.", "THE BACKPLANE IS WIRED. SEND THE NUMBERS.", pg, FOOT6)
    g = Grid(1, 2, heights=[1.5, 0.5])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Send these to Claude. The backplane goes back in the base (BACKPLANE.md section 6) when the cards are ready."])
    for i, (lab, unit, exp) in enumerate(REPORT_ROWS):
        yy = y + h - 22 - i * (h - 16) / max(len(REPORT_ROWS), 4)
        text(c, x + 44, yy, lab, 14, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.8)
        c.rect(x + 330, yy - 8, 110, 26, stroke=1, fill=0)
        text(c, x + 448, yy, unit, 12, "HEAD", INK)
        if exp:
            text(c, x + 44, yy - 13, exp, 9, "MONO", GREY)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Next: the EVM and pack session."])
    for i, s_ in enumerate(["The five leads' far ends: cut, strip and fit to the EVM's J3 and J5, and to the pack lead.",
                            "The charger jumpers on the EVM (ASSEMBLY.md section 1).",
                            "The J8 lead from the EVM onto XJ1's three pins.",
                            "Until then the pack stays off the bench and every far end stays taped."]):
        text(c, x + 44, y + h - 22 - i * 18, "-  " + s_, 10.5, "ALT", INK)


PAGES = [("00-cover", [cover]), ("00-what-you-are-building", [built]), ("01-keys", [keys]),
         ("02-front-parts", [front_parts]), ("03-mux", [mux1, mux2]), ("04-mux-mount", [mux_mount]),
         ("05-links", [links]), ("06-evm-leads", [evm]), ("07-bus", [bus1, bus2]), ("09-checks", [checks]),
         ("10-report", [report])]

HOLE_ISSUES = []


def build(path, fns, start=1, report_=False):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 6: wire the backplane")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(cv, start + i)
        if report_:
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
    bad = build(OUT / "session6-all.pdf", allfns, 1, report_=True)
    print("ok", len(allfns), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
