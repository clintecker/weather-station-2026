"""Session 7: the charger (BQ25798EVM) and the pack, on the bench. Same flat-pack style and pipeline as Sessions 2-6.

Source of truth: hardware/tx-stack-r1/build/ASSEMBLY.md (sections 1 and 4, parsed by asmd.py) and BACKPLANE.md
(the leads Session 6 soldered at the board end). Pictures: scenes7.py.

Starting point: Session 6 is done. The backplane is wired; five 24 AWG leads hang off it with their far ends flagged
and taped (PACK +, J5 BAT, J3 SYS, J3 GND, J5 SNS). The EVM is as supplied (set for two cells).

First power here is a meter-only check: USB into J6, no pack, JP17 out. Nothing in the repo can talk to the BQ25798
yet (firmware/stage0-node/App/power_config.h: charger support is a later phase), so section 1's I2C reads, the TS
check and the ICHG write are a WAITS ON FIRMWARE item, and the pack is never connected in this session.

Usage: .venv-pdf/bin/python make_session7.py [OUT_DIR]     (default: ../out; writes session7-all.pdf)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sheetlib import *          # noqa: F401,F403,E402
import sheetlib as SL           # noqa: E402
import asmd                     # noqa: E402

SL.LEADER_INK = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
WIRE = {"red": HexColor("#D7262E"), "black": HexColor("#1C1C1C"), "yellow": HexColor("#E0B000"),
        "blue": HexColor("#2D6FD0"), "white": HexColor("#F2F2F2")}

SLOGANS7 = [
    "THE PACK STAYS UNPLUGGED. ALL SESSION.",
    "SENSE LEAD FIRST. THEN JP9 OFF.",
    "READ THE SILK. TRUST THE SILK.",
    "SYS AND ITS GROUND RUN TOGETHER.",
    "METER FIRST. POWER LATER.",
]
LEAD = asmd.LEAD
C = asmd.C


def bullets(c, x, y, lines, size=9.5, lead=13, font="ALT", color=INK):
    for i, s_ in enumerate(lines):
        text(c, x, y - i * lead, s_, size, font, color)
    LAB.block(x - 2, y - lead * len(lines), x + 4 + max(len(s) for s in lines) * size * 0.5, y + size, "text")
    return y - lead * len(lines)


def check_item(c, x, y, s_, size=9):
    """A magenta 'CHECK' tag: a guess or an open doc fact, to confirm at the bench."""
    r = chip(c, x, y, "CHECK", 7.5, "HEAD", WHITE, "l", fill=NEON)
    text(c, r[2] + 6, y, s_, size, "ALT", NEON)


def wait_box(c, x, y, w, lines):
    """The WAITS ON FIRMWARE item."""
    h = 24 + 12 * len(lines)
    c.setStrokeColor(NEON)
    c.setFillColor(HexColor("#FFE6F1"))
    lw(c, 2)
    c.rect(x, y - h, w, h, stroke=1, fill=1)
    text(c, x + 10, y - 13, "THE CHARGER CHECK: AFTER SESSION 8, WITH THE CARDS IN", 10.5, "HEAD", NEON)
    for i, s_ in enumerate(lines):
        text(c, x + 10, y - 27 - 12 * i, s_, 8.8, "ALT", INK)
    LAB.block(x, y - h, x + w, y, "wait box")
    return y - h


# ------------------------------------------------------------------ 00 cover
def cover(c, pg):
    page(c, "00", "SESSION 7: THE CHARGER AND THE PACK",
         "EVM JUMPERS FOR ONE CELL, THE LEADS' FAR ENDS, THE THERMISTOR, THE J8 LEAD. A METER-ONLY FIRST POWER.", pg,
         SLOGANS7[0])
    g = Grid(2, 3, heights=[1.3, 1.05, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None,
                       "PARTS (build/ASSEMBLY.md sections 1 and 4). THE FIVE BACKPLANE LEADS ARE ALREADY ON (SESSION 6).")
    items = [("U1 BQ25798EVM (TI BMS034)\nas supplied: set for 2 cells", "p_evm"),
             ("RT1 10 KOHM NTC, B 3950\nAdafruit #372", "p_rt1"),
             ("Adafruit #353 PACK + PG1\nJST PH socket on leads", "p_pack"),
             ("MOLEX KK 2695 4-WAY + 3 CRIMPS,\n1 x 3 0.1 in HOUSING (XJ1 END)", "p_kk"),
             ("24 AWG STRANDED BLACK 150 mm,\n3 x 26 AWG 150 mm, HEAT SHRINK", "p_wires")]
    cw, rh = w / 3, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 3, i // 3
        X0, Y0 = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X0 + 10, Y0 + 40, cw - 20, rh - 48)
        chip(c, X0 + cw / 2, Y0 + 26, name, 8.2, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "TOOLS.")
    tools = ["SOLDERING IRON + SOLDER", "SMALL FLAT SCREWDRIVER (TERMINALS)", "WIRE STRIPPER (24-26 AWG)",
             "KK CRIMP TOOL (OR FINE PLIERS)", "HEAT GUN OR LIGHTER (SHRINK)", "MULTIMETER (OHMS, VOLTS)",
             "TWEEZERS (JUMPER SHUNTS)", "USB-C TO MICRO-B CABLE + 2 A ADAPTER", "TAPE + A PEN", "THIS SHEET, PRINTED"]
    for i, s in enumerate(tools):
        text(c, x + 14, y + h - 16 - i * (h - 12) / len(tools), "-  " + s, 10.5, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 1), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  THE EVM AS SUPPLIED", "02  JP24 OFF, JP22 ON", "03  SENSE LEAD TO J5, THEN JP9 OFF",
             "04  JP18 OFF, THERMISTOR ON J7", "05  J5 BAT, J3 SYS + J3 GND", "06  THE PACK LEADS (PACK UNPLUGGED)",
             "07  THE J8 LEAD TO XJ1", "08  METER, NO POWER", "09  FIRST POWER: USB, NO PACK", "10  REPORT"]
    for i, s in enumerate(steps):
        text(c, x + 14, y + h - 16 - i * (h - 10) / len(steps), s, 12.5, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["THE PACK NEVER PLUGS INTO PG1 IN THIS SESSION. ITS PLUG STAYS APART FROM PG1'S SOCKET, TAPED.",
             "NOTHING IS POWERED UNTIL PAGE 09. EVERY SOLDER AND SCREW JOB HAPPENS WITH THE USB CABLE OUT.",
             "JUMPERS AND J7: READ THEIR NAMES OFF THE EVM'S SILK. THIS SHEET DOESN'T KNOW WHERE THEY SIT.",
             "SENSE LEAD INTO J5 BEFORE JP9 COMES OFF (ASSEMBLY.md 1.2): BATP MUST NEVER FLOAT."]
    for i, s in enumerate(rules):
        yy = y + h - 10 - i * (h - 6) / 4
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 8.8, "ALT", INK)


# ------------------------------------------------------------------ 00 what you are building
def built(c, pg):
    page(c, "00", "WHAT YOU ARE BUILDING", "THE EVM, SET FOR ONE CELL, ITS LEADS ON. THIS IS WHERE THE SESSION ENDS.", pg,
         SLOGANS7[0])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "TOP FACE, the backplane edge at the top, the lid edge (J8) at the bottom: how it will sit in the box, seen from",
        "the lid. J3 and J5 take the leads from the backplane (up the page) and the pack - lead (down the page). The J8",
        "lead goes to XJ1 on the backplane. RT1 on J7 is left out of the drawing: J7's place isn't in the repo."])
    a = Art(c, "evm_done", x + 60, y + 30, w - 220, h - 80)
    names = {"J5 BAT": "J5 BAT (from line 19)", "J5 SNS": "J5 SNS (from R7, line 24)", "J3 SYS": "J3 SYS (from line 26)",
             "J3 GND": "J3 GND (from line 12)", "J5 GND": "J5 GND (PG1 - lead, from the pack)"}
    order = ["J3 SYS", "J3 GND", "J5 BAT", "J5 SNS"]
    for k in order + ["J5 GND"]:
        px, py = a.A(f"lead_{k}")
        r = chip(c, a.x + a.w + 26, py - 3, names[k], 8.5, "ALT", INK)
        leader(c, r, px, py)
    label(c, x + 14, a.y + 30, "J8 LEAD TO XJ1", *a.A("kk_plug"), 9)
    label(c, x + 14, a.y + a.h - 30, "J6 (USB, BENCH ONLY)", *a.A("J6"), 9)


# ------------------------------------------------------------------ 01 as supplied
JP_TABLE = [("JP24", "OFF", "PROG: the two-cell setting"), ("JP22", "ON", "PROG: one cell, 1.5 MHz (the only PROG jumper)"),
            ("JP9", "OFF", "only AFTER the J5 SNS_BATP lead is in"), ("JP18", "OFF", "the thermistor RT1 goes on J7 instead"),
            ("JP12", "STAYS IN", ""), ("JP17", "STAYS IN", "out only for first power (page 09)"),
            ("JP30", "STAYS IN", "the 3.3 V PULLUP rail: I2C pull-ups R39, R40"),
            ("JP32", "AS SHIPPED", "D13, the STAT LED (0.6-0.7 mA lit): leave it, or pull it"),
            ("JP7", "AS SHIPPED", "VIN1 = J6, the micro-B USB")]


def supplied(c, pg):
    page(c, "01", "THE EVM AS SUPPLIED", "TI BQ25798EVM (SLUUCB5). IT SHIPS SET FOR TWO CELLS. NOTHING CONNECTED.", pg,
         SLOGANS7[2])
    g = Grid(2, 1, heights=[1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["TOP FACE. Drawn: the board and the parts this",
                                             "session uses whose place the repo knows.",
                                             "J1, J2: inputs (J2 = solar, Session 8). J3: SYS.",
                                             "J5: the battery. J6: USB. J8: I2C."])
    a = Art(c, "evm_top", x + 10, y + 70, w - 20, h - 120)
    check_item(c, x + 14, y + 52, "J6's place along the left edge is a guess.")
    check_item(c, x + 14, y + 38, "Terminal order in J3 and J5: read the silk.")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["The jumpers by name. Find each one by its",
                                             "silk label: their places aren't in the repo.",
                                             "Keep every pulled shunt in a bag."])
    yy = y + h - 44
    text(c, x + 14, yy, "JUMPER", 9.5, "HEAD", INK)
    text(c, x + 64, yy, "SET", 9.5, "HEAD", INK)
    text(c, x + 136, yy, "WHY", 9.5, "HEAD", INK)
    yy -= 16
    for nm, st_, why in JP_TABLE:
        text(c, x + 14, yy, nm, 10, "HEAD", INK)
        text(c, x + 64, yy, st_, 9, "HEAD", NEON if st_ in ("OFF", "ON") else INK)
        words, line, k = why.split(), "", 0
        for wd in words:
            if len(line) + len(wd) > 30:
                text(c, x + 136, yy - 11 * k, line, 8.4, "ALT", INK)
                line, k = "", k + 1
            line += ("" if not line else " ") + wd
        if line:
            text(c, x + 136, yy - 11 * k, line, 8.4, "ALT", INK)
        yy -= 14 + 11 * k
    LAB.block(x + 8, yy, x + w - 4, y + h - 10, "jumper table")
    bullets(c, x + 14, yy - 10, ["Steps 02-04 change four of them,", "in that order. The rest stay as shipped."], 9)


# ------------------------------------------------------------------ 02 JP24 off, JP22 on
def jp1(c, pg):
    page(c, "02", "JP24 OFF, JP22 ON", "ASSEMBLY.md 1.1: PROG SET FOR ONE CELL, 1.5 MHZ. NOTHING CONNECTED TO THE EVM.", pg,
         SLOGANS7[2])
    g = Grid(2, 2, heights=[1.2, 0.8])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["JP24: pull the shunt straight up with", "tweezers. Both pins bare."])
    a = Art(c, "jp_pull", x + 20, y + 10, w - 40, h - 50)
    label(c, x + w - 10, y + h - 18, "JP24: SHUNT OFF", *a.A("shunt"), 10, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["JP22: push a shunt (the one off JP24 will", "do) fully down over both pins."])
    a = Art(c, "jp_fit", x + 20, y + 10, w - 40, h - 50)
    label(c, x + w - 10, y + h - 18, "JP22: SHUNT ON", *a.A("shunt"), 10, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, ["JP22 is the only PROG jumper fitted when you're done."])
    bullets(c, x + 44, y + h - 22, [
        "The EVM ships set for two cells. Our pack (Adafruit #353) is one cell, 3.7 V, three cells in parallel.",
        "PROG is read when the charger powers up, so set it now, with nothing connected.",
        "Look along the PROG jumper row on the silk: after this step only JP22 has a shunt on it."], 9.5)


# ------------------------------------------------------------------ 03 sense lead, then JP9
def sense(c, pg):
    page(c, "03", "SENSE LEAD TO J5, THEN JP9 OFF", "ASSEMBLY.md 1.2. IN THIS ORDER, SO BATP NEVER FLOATS.", pg, SLOGANS7[1])
    g = Grid(2, 2, heights=[1.25, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "J5, from outside the right edge. Untape the J5 SNS lead (white, red band) that runs from R7's free leg on the",
        "backplane (line 24, hole 7). Trim it to reach J5 with a little slack, strip 6 mm, twist, in to the stop, screw down."])
    a = Art(c, "j5_sns", x + 40, y + 10, w - 240, h - 50, align="l")
    label(c, a.x + a.w + 20, y + h - 30, "J5 SNS_BATP: LEAD IN", *a.A("J5_1"), 9.5, color=NEON)
    label(c, a.x + a.w + 20, y + 40, "WHITE, RED BAND: FROM R7", *a.A("sns"), 9)
    check_item(c, a.x + a.w + 20, y + 22, "Which J5 position is SNS_BATP: the silk.")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Only now: JP9 shunt off.", "Into the bag with JP24's spare."])
    a = Art(c, "jp_pull", x + 30, y + 6, w - 60, h - 40)
    label(c, x + w - 10, y + h - 18, "JP9: SHUNT OFF", *a.A("shunt"), 10, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["The doc says solder: J5 is a screw block."], warn=True)
    bullets(c, x + 14, y + h - 42, ["ASSEMBLY.md says to solder the lead to", "J5 SNS_BATP. On the BOM, J5 is an",
                                     "ED120/3DS screw block, so it's screwed.", "If your EVM has a SNS_BATP pad",
                                     "instead, solder it there."], 9)


# ------------------------------------------------------------------ 04 thermistor
def therm(c, pg):
    page(c, "04", "JP18 OFF, THERMISTOR ON J7", "ASSEMBLY.md 1.3-1.6. THE PACK'S TEMPERATURE, AND WHAT STAYS AS SHIPPED.",
         pg, SLOGANS7[2])
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["RT1, Adafruit #372 (10 kohm, B 3950).",
                                             "Splice 26 AWG to each leg to make 150 mm,",
                                             "shrink over each joint. Into J7, screw down.",
                                             "Then JP18's shunt off. Bead taped to the pack."])
    a = Art(c, "rt1_j7", x + 30, y + 70, w - 60, h - 130)
    label(c, x + w - 10, y + h - 20, "BEAD: TAPE IT TO THE PACK", *a.A("bead"), 9, anchor="r")
    label(c, x + 14, y + h * 0.5, "SPLICE + SHRINK", *a.A("splice"), 9)
    label(c, x + w - 10, y + 76, "J7 (2 x 3.5 mm)", *a.A("J7"), 9, anchor="r")
    check_item(c, x + 14, y + 56, "J7's place on the board: read the silk.")
    check_item(c, x + 14, y + 42, "No polarity: either leg in either J7 position.")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["Everything else stays as it came."])
    yy = bullets(c, x + 44, y + h - 24, [
        "JP12, JP17 and JP30 stay in. JP30 feeds the EVM's",
        "3.3 V PULLUP rail: the I2C pull-ups R39 (SCL) and",
        "R40 (SDA), 10 kohm each, plus R41, R42 on /INT, /CE.",
        "", "D13, the STAT LED, sits on JP32, fitted as shipped.",
        "It draws about 0.6-0.7 mA when lit. Leave it, or pull",
        "JP32 to save that. Write down which on page 10.",
        "", "USB in is J6, micro-B (JP7 on VIN1). It's for the",
        "bench only: no gland is planned for a USB cable."], 9.3)
    wait_box(c, x + 12, yy - 14, w - 24, [
        "Read the TS percentage over I2C at room temperature",
        "and check it sits in the normal band (ASSEMBLY.md 1.3).",
        "The EVM's TS divider is set for a 103AT (B 3435): with",
        "the B 3950 part the cold and hot limits move a few",
        "degrees. Nothing in the repo reads it yet."])


# ------------------------------------------------------------------ 05 J5 BAT, J3 SYS + GND
def power_leads(c, pg):
    page(c, "05", "J5 BAT, J3 SYS AND J3 GND", "THE BACKPLANE LEADS' FAR ENDS. 24 AWG STRANDED, SCREWED.", pg, SLOGANS7[3])
    g = Grid(2, 1, heights=[1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["TOP FACE, backplane edge up. Each lead comes",
                                             "from the backplane: untape it, trim it, strip",
                                             "6 mm, twist, in, screw down. Tug-test each."])
    a = Art(c, "evm_done", x + 8, y + 40, w - 70, h - 90, align="l")
    for k, nm in enumerate(("J3 SYS", "J3 GND", "J5 BAT")):
        px, py = a.A(f"lead_{nm}")
        r = chip(c, a.x + a.w + 8, py - 3, nm, 8, "ALT", INK, "l")
        leader(c, r, px, py)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["From ASSEMBLY.md section 4."])
    rows = [(LEAD["U1 battery + (J5 BATTERY)"], "J5 BAT", "line 19, hole 6"),
            (LEAD["U1 system out (J3 SYS)"], "J3 SYS", "line 26, hole 6"),
            (LEAD["U1 system ground (J3 GND)"], "J3 GND", "line 12, hole 11")]
    yy = y + h - 44
    for r_, nm, frm in rows:
        text(c, x + 14, yy, nm, 12, "HEAD", INK)
        text(c, x + 90, yy, f"from {frm}", 9, "ALT", INK)
        text(c, x + 90, yy - 12, r_[3].split(", ")[-1], 8.5, "ALT", GREY)
        text(c, x + 90, yy - 24, r_[2], 8.5, "ALT", GREY)
        yy -= 44
    LAB.block(x + 8, yy, x + w - 4, y + h - 10, "lead table")
    yy = bullets(c, x + 14, yy - 6, [
        "J3 SYS and J3 GND are a pair: trim them to",
        "the same length and run them side by side,",
        "twisted loosely, J3 to the backplane. The",
        "3.3 V regulator's load and the radio's",
        "transmit peaks come back on that black lead.",
        "", "Leave a service loop on all three: the EVM",
        "slides out of its shelf on these leads."], 9.3)
    check_item(c, x + 14, yy - 14, "J3: SYS and GND positions from the silk.")


# ------------------------------------------------------------------ 06 the pack leads
def pack_leads(c, pg):
    page(c, "06", "THE PACK LEADS. PACK UNPLUGGED.", "PG1 IS THE PACK'S SOCKET ON ITS OWN LEADS. THE PACK ITSELF STAYS APART.",
         pg, SLOGANS7[0])
    g = Grid(1, 2, heights=[1.0, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "PG1 (a JST PH 2-pin socket with leads) and the pack's plug, apart. PG1's red lead joins the backplane's PACK +",
        "lead (red, black band, soldered at line 21, hole 6). PG1's black lead goes to J5 GND, 150 mm, trim to fit."])
    a = Art(c, "pack_pg1", x + 20, y + 20, w - 40, h - 60)
    label(c, x + w * 0.42, y + h - 18, "PACK PLUG: NOT IN PG1", *a.A("ph_plug"), 9, color=NEON, anchor="r")
    label(c, x + w * 0.5, y + h - 18, "PG1 SOCKET", *a.A("pg1"), 9)
    label(c, x + w - 10, y + h - 34, "TO J5 GND", *a.A("minus"), 9, anchor="r")
    label(c, x + w - 10, y + 30, "PACK + LEAD (FROM LINE 21)", *a.A("plus"), 9, anchor="r")
    label(c, x + w * 0.5, y + 30, "SPLICE + SHRINK", *a.A("splice"), 9, anchor="r")
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["The pack's plug and PG1 meet only at the very end of Session 8."], warn=True)
    yy = bullets(c, x + 44, y + h - 24, [
        "1. Slide heat shrink onto the PACK + lead first. Untape its end, strip 8 mm.",
        "2. Strip 8 mm off PG1's red lead. Twist them in line, solder, shrink over the joint.",
        "3. PG1's black lead to J5 GND: extend it with 24 AWG black to 150 mm if it's short (same splice), strip 6 mm,",
        "   into J5's GND position, screw down. It never touches the backplane.",
        "4. Put a strip of tape over PG1's socket mouth. The pack's plug stays loose beside it, taped too."], 9.5)
    check_item(c, x + 44, yy - 16, "PG1's own lead length isn't in the repo: splice only if you need the length.")
    check_item(c, x + 44, yy - 32, "Red to red: PG1's red lead must sit on the pack's + pin. Meter it on page 08.")


# ------------------------------------------------------------------ 07 J8 lead
def j8(c, pg):
    page(c, "07", "THE J8 LEAD TO XJ1", "THE CHARGER'S I2C: GROUND, CLOCK, DATA. 150 MM.", pg, SLOGANS7[2])
    g = Grid(2, 2, heights=[0.9, 1.1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "Three 26 AWG wires, 150 mm. EVM end: KK crimps in positions 1-3 of the 4-way KK 2695 housing, 4 empty.",
        "Backplane end: crimps in a 1 x 3 0.1 in housing that pushes onto XJ1's three pins."])
    a = Art(c, "kk_lead", x + 30, y + 20, w - 60, h - 54)
    label(c, x + w - 10, y + h - 16, "KK HOUSING: TO EVM J8", *a.A("kk"), 9, anchor="r")
    label(c, x + 30, y + h - 16, "1 x 3 HOUSING: TO XJ1", *a.A("du"), 9)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Pin by pin (ASSEMBLY.md 4, BACKPLANE.md 3)."])
    rows = [("J8-1", "ground", "black", "XJ1 ground: line 2, hole 11"),
            ("J8-2", "clock", "yellow", "XJ1 clock: line 7, hole 11"),
            ("J8-3", "data", "blue", "XJ1 data: line 10, hole 11"),
            ("J8-4", "pull-up rail", None, "empty: not wired")]
    yy = y + h - 46
    for pin, what, colr, to in rows:
        if colr:
            c.setFillColor(WIRE[colr])
            c.setStrokeColor(INK)
            lw(c, 0.6)
            c.rect(x + 14, yy - 2, 9, 9, stroke=1, fill=1)
        text(c, x + 30, yy, pin, 11, "HEAD", INK)
        text(c, x + 74, yy, what, 9.5, "ALT", INK)
        text(c, x + 74, yy - 12, to, 8.5, "ALT", GREY)
        yy -= 32
    LAB.block(x + 8, yy, x + w - 4, y + h - 10, "pin table")
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["J8 is a right-angle KK header on the", "EVM's lid edge, about 12 mm proud."])
    yy = bullets(c, x + 44, y + h - 24, [
        "Pin 1: find the silk's 1 next to J8.",
        "Match the housing's 1 to it, then the",
        "1 x 3 end: black on line 2 (nearest", "line 0), yellow 7, blue 10.",
        "", "J8 pin 1 is also tied to the EVM's",
        "ground, so it carries a small share", "of SYS's return. J3 GND carries most."], 9.3)
    check_item(c, x + 14, yy - 14, "The XJ1-end housing isn't named in the repo.")


# ------------------------------------------------------------------ 08 meter, no power
def meter(c, pg):
    page(c, "08", "METER, NO POWER", "OHMS / CONTINUITY. NO USB, NO PACK. THE BACKPLANE AND THE EVM ON THE BENCH.", pg,
         SLOGANS7[4])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Tick each box. Anything else: stop, take a photo, tell Claude."], warn=True)
    rows = [("1", "J5 BAT TO LINES 19, 20", "Its screw to line 19's wire: BEEP. Line 20 too (joined at hole 5)."),
            ("2", "J3 SYS TO LINE 26", "Its screw to line 26's wire: BEEP."),
            ("3", "J3 GND TO LINES 12, 2", "BEEP to both (2 and 12 are joined at hole 38)."),
            ("4", "J5 SNS TO THE JUNCTION", "J5's SNS screw to line 21: about 100 ohm (R7). Not 0, not open."),
            ("5", "PG1 + TO LINE 21", "A probe in PG1's + contact to line 21's wire: BEEP."),
            ("6", "PG1 - TO J5 GND", "PG1's - contact to J5's GND screw: BEEP."),
            ("7", "J7: RT1", "Across J7's two screws: about 10 kohm at room temperature."),
            ("8", "J8 LEAD", "Each XJ1 housing contact to its J8 pin: black 1, yellow 2, blue 3. BEEP each."),
            ("9", "NO SHORTS", "J3 SYS to J3 GND: OPEN. J5 BAT to J5 GND: OPEN. Line 1 to line 2: OPEN.")]
    rh = (h - 40) / len(rows)
    for i, (n, t, s) in enumerate(rows):
        yy = y + h - 44 - i * rh
        badge(c, x + 40, yy + 4, n, 10)
        text(c, x + 58, yy, t, 11.5, "HEAD", INK)
        text(c, x + 236, yy + 1, s, 8.8, "ALT", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.rect(x + w - 26, yy - 4, 14, 14, stroke=1, fill=0)


# ------------------------------------------------------------------ 09 first power
def first_power(c, pg):
    page(c, "09", "FIRST POWER: USB, NO PACK", "ASSEMBLY.md 1.7, THE METER HALF. JP17 OUT: CHARGE DISABLED. NO CARDS.", pg,
         SLOGANS7[4])
    g = Grid(2, 2, heights=[1.1, 0.9])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["JP17's shunt off. The pack's plug is not in", "PG1. No card is in any socket."])
    a = Art(c, "jp_pull", x + 30, y + 10, w - 60, h - 46)
    label(c, x + w - 10, y + h - 18, "JP17: SHUNT OFF", *a.A("shunt"), 10, color=NEON, anchor="r")
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["USB in, read, USB out."])
    bullets(c, x + 44, y + h - 24, [
        "1. The 2 A adapter, USB-C to micro-B, into J6.",
        "2. DC volts, J3 SYS to J3 GND. Write it down.",
        "   No pack and charge off: SYS sits at the",
        "   charger's minimum system voltage, a little",
        "   over 3.5 V for one cell. Write what you see.",
        "3. The same at the backplane: line 26 to line 12.",
        "4. D13, the STAT LED: on, off or blinking?",
        "5. Line 1 to line 2: 0 V (B4 isn't in, so",
        "   nothing makes 3.3 V yet).",
        "6. USB out."], 9.3)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "JP17 stays OUT and the pack stays unplugged until the CHARGER check passes. Session 8 boxes it up that way."])
    wait_box(c, x + 44, y + h - 14, w - 60, [
        "The firmware does the I2C part (App/charger.c; build with WS_POWER_PROFILE=3 WS_I2C_MUX=1). At every",
        "start it writes 4.2 V (REG0x01-0x02) and ICHG " + asmd.ICHG + " A (issue #34), reads them back, and checks REG0x0A",
        "says one cell. ICHG goes back to its 1 A default on a power cycle, so it writes them again after any reset.",
        "Charge stays off until a fresh TS reading (page 06) is neither COLD nor HOT.",
        "It needs the cards, so check it after Session 8: USB in J6, no pack, JP17 out. Type CHARGER on the TX",
        "console. Look for cells=1 vreg_mv=4200 ichg_ma=900 ts=NORMAL hold=none. Write down ts_pct.",
        "Then refit JP17 and connect the pack LAST."])


REPORT_ROWS = [("SYS, J3, USB IN, NO PACK", "V", "page 09 step 2"),
               ("SYS AT THE BACKPLANE (26 TO 12)", "V", "page 09 step 3"),
               ("STAT LED (D13)", "ON/OFF/BLINK", "and JP32 kept or pulled"),
               ("RT1 ACROSS J7", "kohm", "about 10 at room temperature"),
               ("METER CHECKS 1-9 ALL PASS", "Y / N", "page 08"),
               ("J3, J5 ORDER ON THE SILK", "WRITE", "e.g. J5: BAT SNS GND"),
               ("PHOTO OF THE EVM, TOP", "SENT", "jumpers readable")]


def report(c, pg):
    page(c, "10", "REPORT THE CHARGER.", "THE EVM IS SET FOR ONE CELL AND WIRED. SEND THE NUMBERS.", pg, SLOGANS7[4])
    g = Grid(1, 2, heights=[1.55, 0.45])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Send these to Claude. They fix the drawing's guesses (J6, J7, the silk order)."])
    for i, (lab, unit, exp) in enumerate(REPORT_ROWS):
        yy = y + h - 22 - i * (h - 16) / len(REPORT_ROWS)
        text(c, x + 44, yy, lab, 13, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.8)
        c.rect(x + 330, yy - 8, 110, 24, stroke=1, fill=0)
        text(c, x + 448, yy, unit, 11, "HEAD", INK)
        text(c, x + 44, yy - 12, exp, 8.5, "MONO", GREY)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Next: Session 8, into the box."])
    for i, s_ in enumerate(["The pack on its tray (RT1 taped to it), the EVM on its shelf, the backplane, the cards.",
                            "The glands, the cables and their plugs, the solar lead into J2, the coax.",
                            "The pack still stays unplugged and JP17 out until the firmware item is done."]):
        text(c, x + 44, y + h - 22 - i * 16, "-  " + s_, 10, "ALT", INK)


PAGES = [cover, built, supplied, jp1, sense, therm, power_leads, pack_leads, j8, meter, first_power, report]
HOLE_ISSUES = []


def build(path, fns):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 7: the charger and the pack")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(cv, i + 1)
        issues += len(LAB.check())
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
    bad = build(OUT / "session7-all.pdf", PAGES)
    print("ok", len(PAGES), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
