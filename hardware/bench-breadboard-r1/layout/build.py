"""Breadboard bench r1, step 4: the physical build as data, checked against the schematic.

Every part's position on the plate, every breadboard hole a pin sits in, every jumper and every lead.
check() rebuilds the copper the build would have (breadboard strips + conductors + each breakout's
internal ties) and proves it equals the schematic model's (../schematic/model.py), then checks the
build rules. outputs.py writes the wiring plan and homes; kicad_layout.py writes the KiCad board and renders.

Coordinates: plate mm in KiCad's frame, x to the right, y towards the FRONT edge (down the page),
origin at the back-left corner. Breadboards are read the way they are printed (Elegoo, photographed
2026-11-03): rows a-e top to bottom in the upper half, f-j in the lower half, column 62 on the left
down to column 1 on the right. Rails: "T+" (outer) and "T-" above row a, "B+" and "B-" (outer)
below row j; rail holes sit beside columns 3-7, 9-13, ... 57-61. Holes: "BB1:a40", rails "BB1:B-52".
Modules that plug in are "seated": one header pin is put in a hole and every other pin must land on
a hole too. Rotations are KiCad's: degrees counter-clockwise as seen from above.
Run: python3 build.py
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "schematic"))
from model import NETS, PARTS  # noqa: E402

P = 2.54
KIT_SPANS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50}   # BOJACK pre-cut lengths, in holes spanned
PART = {p["ref"]: p for p in PARTS}

# ------------------------------------------------------------------ breadboards (Elegoo 830-point)
NCOL = 62
BB_W, BB_H, BB_Z = 165.1, 54.6, 8.5       # outline and height [TBD-MEASURE]
COL_MARGIN = 5.08                          # board left edge to column 62 [TBD-MEASURE]
ROW_Y = {"T+": 5.71, "T-": 8.25, "a": 13.33, "b": 15.87, "c": 18.41, "d": 20.95, "e": 23.49,
         "f": 31.11, "g": 33.65, "h": 36.19, "i": 38.73, "j": 41.27, "B+": 46.35, "B-": 48.89}
ROW_ORDER = list(ROW_Y)
RAILS = ("T+", "T-", "B+", "B-")
BOARDS = {"BB2": (10.0, 5.0), "BB1": (10.0, 100.0), "BB3": (10.0, 230.0)}   # top-left corner on the plate
BOARD_ROLE = {"BB1": "charger and power signals", "BB2": "the four INA228s and the gauge",
              "BB3": "weather meter jacks and the OLED"}
PLATE_W, PLATE_H = 400, 292


def rail_gap(col):
    """True where a rail has no hole: groups of five beside columns 3-7, 9-13, ... 57-61."""
    return not 3 <= col <= 61 or (col - 2) % 6 == 0


def parse(h):
    board, name = h.split(":")
    row = name[:2] if name[:2] in RAILS else name[0]
    return board, row, int(name[len(row):])


def hole_xy(h):
    board, row, col = parse(h)
    x0, y0 = BOARDS[board]
    return x0 + COL_MARGIN + (NCOL - col) * P, y0 + ROW_Y[row], row, col


def hole_exists(h):
    _b, row, col = parse(h)
    return 1 <= col <= NCOL and not (row in RAILS and rail_gap(col))


def strip_of(h):
    board, row, col = parse(h)
    if row in RAILS:
        return (board, row)                     # rails run the full length
    return (board, col, "top" if row in "abcde" else "bottom")


def label(h):
    """A hole as a person reads it: grid holes as printed (j52), rail holes by job and side (GND ↓52, 3V3 ↑18)."""
    _b, row, col = parse(h)
    if row in RAILS:
        return f"{'3V3' if row.endswith('+') else 'GND'} {'↑' if row[0] == 'T' else '↓'}{col}"
    return f"{row}{col}"


def rail_words(h):
    """The plain-words reading of a rail hole's label."""
    _b, row, col = parse(h)
    plus = row.endswith("+")
    return (f"the {'red +' if plus else 'blue −'} rail along the {'top' if row[0] == 'T' else 'bottom'} edge, "
            f"straight {'above' if row[0] == 'T' else 'below'} column {col}")


def span(h1, h2):
    """Holes a jumper spans, or None if it is not a straight run along a row or a column."""
    x1, y1, r1, c1 = hole_xy(h1)
    x2, y2, r2, c2 = hole_xy(h2)
    if r1 == r2:
        return abs(c1 - c2)
    if c1 == c2:
        return round(abs(y1 - y2) / P)
    return None


ALL_HOLES = [f"{bd}:{r}{c}" for bd in BOARDS for r in ROW_ORDER for c in range(1, NCOL + 1)
             if hole_exists(f"{bd}:{r}{c}")]
HOLE_AT = {(round(hole_xy(h)[0], 2), round(hole_xy(h)[1], 2)): h for h in ALL_HOLES}


def hole_at(x, y):
    for dx in (0, -0.01, 0.01):
        for dy in (0, -0.01, 0.01):
            h = HOLE_AT.get((round(x + dx, 2), round(y + dy, 2)))
            if h:
                return h
    return None


# ------------------------------------------------------------------ part outlines and pins
# Local frame of each outline: origin top-left, x right, y down, before rotation. Positions from the makers'
# board files where they give them; the rest are [TBD-MEASURE] estimates (marked).
SIZE = {"NUCLEO": (70.0, 64.5), "CHG": (38.1, 33.02), "INA": (25.4, 20.32), "GAUGE": (25.4, 17.78),
        "REG": (11.43, 16.51), "BOB": (21.59, 20.57), "OLED": (85.0, 58.0), "WAGO3": (17.0, 20.5),
        "WAGO5": (26.6, 20.5), "PACK": (69.0, 54.0), "USBF": (20.32, 13.97), "USBM": (13.97, 12.7),
        "BARREL": (30.0, 15.0), "QT": (25.4, 17.78),
        "LOADR": (62.0, 30.0)}   # 50 W aluminium-housed resistor: 50 x 15 x 15 housing + terminals; tabs 7.5 mm out each side
_ina = ["VIN", "GND", "SCL", "SDA", "VBUS", "VIN-", "VIN+", "ALRT"]   # header, left to right, silkscreen names (2026-11-04)
_gauge = ["VIN", "GND", "SCL", "SDA", "INT", "QST"]
_chg = ["VBUS", "GND1", "THERM", "ISET", "CE", "PGOOD", "CHG", "OUT", "GND2", "LIPO", "GND3"]
_reg = ["VOUT", "GND", "VIN", "SHDN"]   # left to right with the board above its pins (board in hand, 2026-11-04)
_qt = ("GND", "V+", "SDA", "SCL")


def _nucleo():
    """NUCLEO-WL55JC1 header positions: estimates good to about 10 mm (UM2592 gives no mm)."""
    # Local y = 0 is the antenna (SMA) end, y = 64.5 the ST-LINK USB end. Order confirmed on the board
    # (2026-11-04, antenna on the left): CN5 at the antenna end with D15/SCL (pin 10) outermost, then CN9
    # (D7 ... D0) after the Arduino 160 mil gap; CN6 likewise starts at the antenna end, CN8 after it.
    # Morpho pin 1 is taken to be at the same end as D15 (as on other NUCLEO-64s) [TBD-MEASURE].
    pins = {}
    for i in range(1, 11):
        pins[f"CN5.{i}"] = (58.0, 2.7 + (10 - i) * P)
    for i in range(1, 9):
        pins[f"CN9.{i}"] = (58.0, 2.7 + 9 * P + 4.064 + (8 - i) * P)
        pins[f"CN6.{i}"] = (12.0, 6.0 + (i - 1) * P)
    for i in range(1, 7):
        pins[f"CN8.{i}"] = (12.0, 6.0 + 7 * P + 5.08 + (i - 1) * P)
    for i in range(1, 39):
        pins[f"CN7.{i}"] = (3.0 + (i + 1) % 2 * P, 6.78 + (i - 1) // 2 * P)
        pins[f"CN10.{i}"] = (64.5 + (i + 1) % 2 * P, 6.78 + (i - 1) // 2 * P)
    pins["USB.VBUS"] = pins["USB.GND"] = (35.0, 64.5)
    return pins


LOCAL = {
    "INA": {**{f"H.{n}": (3.81 + i * P, 17.78) for i, n in enumerate(_ina)},
            "X1.VIN-": (9.2, 0.0), "X1.VBUS": (12.7, 0.0), "X1.VIN+": (16.2, 0.0),
            **{f"QT1.{s}": (0.0, 11.43) for s in _qt}, **{f"QT2.{s}": (25.4, 11.43) for s in _qt}},
    "GAUGE": {**{f"H.{n}": (6.35 + i * P, 15.24) for i, n in enumerate(_gauge)},      # header y [TBD-MEASURE]
              "BAT1.+": (8.0, 0.0), "BAT1.-": (8.0, 0.0), "BAT2.+": (17.4, 0.0), "BAT2.-": (17.4, 0.0),
              **{f"QT1.{s}": (0.0, 8.89) for s in _qt}, **{f"QT2.{s}": (25.4, 8.89) for s in _qt}},
    "CHG": {**{f"H.{n}": (6.35 + i * P, 30.48) for i, n in enumerate(_chg)},
            "USB.VBUS": (0.0, 22.86), "USB.GND": (0.0, 22.86), "DC.+": (0.0, 11.30), "DC.-": (0.0, 11.30),
            "BATT.+": (38.1, 22.23), "BATT.-": (38.1, 22.23), "SYS.+": (38.1, 10.79), "SYS.-": (38.1, 10.79)},
    "REG": {n: (1.905 + i * P, 15.24) for i, n in enumerate(_reg)},
    "BOB": {str(i): (4.445 + (i - 1) * P, 1.905) for i in range(1, 7)},       # pin 1 left, jack at the bottom [TBD-MEASURE: silk]
    "OLED": {str(i): (12.0 + (i - 1) * P, 2.5) for i in range(1, 21)},
    "NUCLEO": _nucleo(),
    "LOADR": {"1": (0.0, 15.0), "2": (62.0, 15.0),                            # its two solder terminals
              "TAB1": (11.0, 27.5), "TAB2": (51.0, 2.5)},   # 3 mm tab holes: 40 mm apart along, 25 mm across (measured 2026-11-04)
    "WAGO3": {str(i): ((i - 0.5) * 17.0 / 3, 0.0) for i in range(1, 4)},     # wire entries along the top edge
    "WAGO5": {str(i): ((i - 0.5) * 26.6 / 5, 0.0) for i in range(1, 6)},
    "USBF": {"VBUS": (16.51, 11.43), "GND": (19.05, 11.43), "IN.VBUS": (10.16, 0.0), "IN.GND": (10.16, 0.0)},
    "USBM": {"VBUS": (1.91, 10.16), "GND": (12.07, 10.16), "OUT.VBUS": (6.99, 0.0), "OUT.GND": (6.99, 0.0)},
    "BARREL": {"+": (3.0, 11.0), "-": (3.0, 4.0), "IN.+": (30.0, 7.5), "IN.-": (30.0, 7.5),
               "OUT.+": (30.0, 7.5), "OUT.-": (30.0, 7.5)},
    "QT": {**{f"QT1.{s}": (0.0, 8.89) for s in _qt}, **{f"QT2.{s}": (25.4, 8.89) for s in _qt},
           **{f"P{i}.{s}": (2.9 + (i - 1) * 4.9, 17.78) for i in range(1, 6) for s in _qt}},
}
HEADER = {"INA": [f"H.{n}" for n in _ina], "GAUGE": [f"H.{n}" for n in _gauge], "CHG": [f"H.{n}" for n in _chg],
          "REG": _reg, "BOB": [str(i) for i in range(1, 7)], "OLED": [str(i) for i in range(1, 21)]}


def rot_vec(x, y, rot):
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot % 360]


# ref: kind, rot, one of at=(x, y) (outline top-left after rotation) / seat=(pin, hole) / mate=(pin, (ref, pin)),
# and how it is held.
PLACE = {
    # --- BB2: the meters, headers in row j, boards hanging over the front edge, terminals facing BB1
    "U4": dict(kind="INA", rot=180, seat=("H.ALRT", "BB2:j62"), held="seated on BB2 (solar 0x45)"),
    "U5": dict(kind="INA", rot=180, seat=("H.ALRT", "BB2:j51"), held="seated on BB2 (USB-C 0x48)"),
    "U6": dict(kind="GAUGE", rot=180, seat=("H.QST", "BB2:j40"), held="seated on BB2 (gauge 0x36)"),
    "U2": dict(kind="INA", rot=180, seat=("H.ALRT", "BB2:j29"), held="seated on BB2 (battery 0x40)"),
    "U3": dict(kind="INA", rot=180, seat=("H.ALRT", "BB2:j18"), held="seated on BB2 (load 0x41)"),
    # --- BB1: the charger, header in row a, board over the back rails and edge
    "U1": dict(kind="CHG", rot=0, seat=("H.VBUS", "BB1:a40"), held="seated on BB1"),
    "P1": dict(kind="USBM", rot=270, mate=("OUT.VBUS", ("U1", "USB.VBUS")), held="rides in the #4755 USB-C"),
    "P2": dict(kind="BARREL", rot=0, mate=("OUT.+", ("U1", "DC.+")), held="rides in the #4755 DC jack"),
    "U7": dict(kind="REG", rot=0, seat=("VOUT", "BB1:f24"), held="seated on BB1"),
    # --- BB3: RJ11 breakouts in row j (jacks over the front edge), OLED in row a (board over the back)
    "J1": dict(kind="BOB", rot=0, seat=("1", "BB3:j22"), held="seated on BB3, jack over the front edge"),
    "J2": dict(kind="BOB", rot=0, seat=("1", "BB3:j11"), held="seated on BB3, jack over the front edge"),
    "DS1": dict(kind="OLED", rot=180, seat=("1", "BB3:a37"), held="seated on BB3; M2.5 standoffs (2) under the far edge"),
    # --- power island between BB2 and BB1
    # J3 above J4 at the left edge, so the adapter's USB-C plug and the panel plug sit side by side (2026-11-04)
    "J4": dict(kind="BARREL", rot=180, at=(1, 84.8), held="clip; panel cable in from the left, zip-tied to the plate's edge ear"),
    "J3": dict(kind="USBF", rot=90, at=(6, 64.3), held="M2.5 standoffs (2); USB-C cable in from the left"),
    "WG1": dict(kind="WAGO3", rot=0, at=(104, 68), held="WAGO holder, entries towards BB2"),
    "WG2": dict(kind="WAGO5", rot=180, at=(123, 68), held="WAGO holder, entries towards BB1"),
    "WG3": dict(kind="WAGO5", rot=180, at=(151.6, 68), held="WAGO holder, entries towards BB1"),
    "BT1": dict(kind="PACK", rot=0, at=(186, 40), held="pack cradle; its 100 mm lead brings the plug to the WAGOs"),
    # --- TX NUCLEO between BB1 and BB3, ST-LINK USB facing right; right column for the rest
    "A1": dict(kind="NUCLEO", rot=90, at=(105, 158), held="corner ledges + snap lips (4; no mounting holes); ST-LINK USB facing right"),
    "A2": dict(kind="NUCLEO", rot=180, at=(322, 5), held="corner ledges + snap lips (4; no mounting holes); ST-LINK USB at the back edge"),
    "R9": dict(kind="LOADR", rot=0, at=(262, 80), held="2 × M3 screws through its tabs; its own leads to the WAGOs"),
    "U8": dict(kind="QT", rot=0, at=(186, 118), held="M2.5 standoffs (2)"),
    "U9": dict(kind="QT", rot=0, at=(216, 118), held="M2.5 standoffs (2)"),
    "U10": dict(kind="QT", rot=0, at=(246, 118), held="M2.5 standoffs (2)"),
    "U11": dict(kind="QT", rot=0, at=(216, 143), held="M2.5 standoffs (2)"),
    "U12": dict(kind="QT", rot=0, at=(246, 143), held="M2.5 standoffs (2)"),
}
# Loose ends: the pack's plug at the end of its own 100 mm lead; the NTC bead taped on the pack.
PLUG_XY = {("BT1", "+"): (127.0, 95.0), ("BT1", "-"): (131.0, 95.0)}
NTC_BEAD = (190.0, 88.0)
UNPLACED_OK = {"W1", "W2", "W3"}   # length checked elsewhere (PART_SPANS, QT_HEADER_MM)


def _bbox(kind, rot):
    w, h = SIZE[kind]
    pts = [rot_vec(x, y, rot) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def origin(ref):
    """Where the part's local (0, 0) lands on the plate."""
    pl = PLACE[ref]
    kind, rot = pl["kind"], pl["rot"]
    if "at" in pl:
        x0, y0, _x1, _y1 = _bbox(kind, rot)
        return pl["at"][0] - x0, pl["at"][1] - y0
    pin, target = pl["seat"] if "seat" in pl else pl["mate"]
    tx, ty = hole_xy(target)[:2] if isinstance(target, str) else local_xy(*target)
    lx, ly = rot_vec(*LOCAL[kind][pin], rot)
    return tx - lx, ty - ly


def outline(ref):
    kind, rot = PLACE[ref]["kind"], PLACE[ref]["rot"]
    ox, oy = origin(ref)
    x0, y0, x1, y1 = _bbox(kind, rot)
    return ox + x0, oy + y0, x1 - x0, y1 - y0


def local_xy(ref, pin):
    kind, rot = PLACE[ref]["kind"], PLACE[ref]["rot"]
    ox, oy = origin(ref)
    lx, ly = rot_vec(*LOCAL[kind][pin], rot)
    return ox + lx, oy + ly


# ------------------------------------------------------------------ what sits in breadboard holes
# Leaded parts and wire ends by hand; seated modules are added below from their header geometry.
ON_BB = {
    # BB1, bottom half: VBUS divider (cols 40-52), ISET network (37-29), S7V8F3 + BATTERY link (24-18),
    # I2C junction (12-9). Top half: the charger's own strips (40-30) and the NTC.
    ("R4", "1"): "BB1:h40", ("R4", "2"): "BB1:h44", ("R5", "1"): "BB1:i44", ("R5", "2"): "BB1:i48",
    ("R6", "1"): "BB1:h48", ("R6", "2"): "BB1:h52",
    ("R7", "1"): "BB1:h37", ("R7", "2"): "BB1:h33", ("C4", "1"): "BB1:g33", ("C4", "2"): "BB1:g31",
    ("R8", "1"): "BB1:i33", ("R8", "2"): "BB1:i29",
    ("RT1", "1"): "BB1:c38", ("RT1", "2"): "BB1:c39",
    ("W1", "2"): "BB1:j23",
    ("JP1", "1"): "BB1:h19", ("JP1", "2"): "BB1:h18",
    ("W2", "H.SDA"): "BB1:f12", ("W3", "H.SDA"): "BB1:g12", ("W2", "H.SCL"): "BB1:f11", ("W3", "H.SCL"): "BB1:g11",
    ("W2", "H.V+"): "BB1:B+10", ("W3", "H.V+"): "BB1:B+9", ("W2", "H.GND"): "BB1:B-10", ("W3", "H.GND"): "BB1:B-9",
    # BB3: weather meter conditioning above the RJ11 pins, OLED supply under the OLED's first pins
    ("R2", "2"): "BB3:h19", ("R2", "1"): "BB3:h15", ("R1", "2"): "BB3:g18", ("R1", "1"): "BB3:g15",
    ("C2", "1"): "BB3:g19", ("C2", "2"): "BB3:g20",
    ("R3", "2"): "BB3:h8", ("R3", "1"): "BB3:h4", ("C3", "1"): "BB3:g8", ("C3", "2"): "BB3:g9",
    ("C1", "+"): "BB3:d38", ("C1", "-"): "BB3:d37",
    ("JP2", "2"): "BB3:h38", ("JP2", "1"): "BB3:h37",
}
SEAT_ERRORS = []
for _ref, _pl in PLACE.items():
    if "seat" in _pl:
        for _pin in HEADER[_pl["kind"]]:
            _h = hole_at(*local_xy(_ref, _pin))
            if _h is None:
                SEAT_ERRORS.append(f"{_ref}.{_pin} does not land on a hole")
            else:
                ON_BB[(_ref, _pin)] = _h
LYING = ("R",)   # axial parts lie flat: the holes between their leads are under the body

PART_SPANS = {"W1": (("WG2", "4"), "BB1:j23", 100)}   # wire parts: their two ends, and the length limit (mm)

# ------------------------------------------------------------------ conductors
# (kind, end1, end2, note). Ends: a hole "BB1:a6" or a pin (ref, pin). Kinds:
#   jumper   BOJACK pre-cut, flat on one breadboard   force   20 AWG stranded, force current, <= 80 mm
#   reg      22 AWG solid, regulator supply, <= 100   sense   22 AWG solid, sense lead (no current)
#   pigtail  half of a #1131 JST PH cable, <= 60      solder  22 AWG soldered to a breakout pad
#   dupont   jumper wire, M = pin end, F = socket end (signals only)
#   qt       STEMMA QT cable                          mate    connector into connector (no wire)
#   cable    a source or USB cable                    lead    a component's own lead into a WAGO lever


def qt(a, ap, b, bp, note):
    return [("qt", (a, f"{ap}.{s}"), (b, f"{bp}.{s}"), note) for s in _qt]


CONDUCTORS = [
    # --- pack and battery path
    ("pigtail", ("BT1", "+"), ("WG1", "1"), "pack-side half (socket), red: pack + to CELL+"),
    ("pigtail", ("BT1", "-"), ("WG2", "1"), "pack-side half, black: pack - to STAR"),
    ("force", ("WG1", "2"), ("U2", "X1.VIN+"), "CELL+ to battery INA228 VIN+"),
    ("sense", ("WG1", "3"), ("U6", "BAT1.+"), "gauge sense: board-side half (plug) in the gauge BAT socket, red only; black insulated"),
    ("pigtail", ("U2", "X1.VIN-"), ("U1", "BATT.+"), "board-side half in the #4755 BATT socket, red: to INA228 VIN-"),
    ("pigtail", ("U1", "BATT.-"), ("WG2", "2"), "same half, black: #4755 BATT - to STAR"),
    ("pigtail", ("U1", "SYS.+"), ("U3", "X1.VIN+"), "board-side half in the #4755 SYSOUT socket, red; black insulated"),
    ("force", ("U3", "X1.VIN-"), ("WG3", "4"), "load INA228 VIN- to LOAD"),
    ("sense", ("U3", "X1.VBUS"), ("WG3", "2"), "load INA228 VBUS sense to LOAD (SJ1 open on this board)"),
    ("lead", ("R9", "1"), ("WG3", "3"), "100R test load (mode A): one lead in LOAD"),
    ("lead", ("R9", "2"), ("WG2", "3"), "the other lead in STAR (adjacent WAGO)"),
    ("reg", ("WG3", "5"), "BB1:j22", "LOAD to the S7V8F3 VIN strip"),
    ("lead", ("W1", "1"), ("WG2", "4"), "the ground tie W1 (22 AWG, <= 100 mm): STAR end; other end in BB1:j23"),
    # --- USB-C source metering
    ("cable", ("PS1", "VBUS"), ("J3", "IN.VBUS"), "adapter USB-C cable into the #4090"),
    ("cable", ("PS1", "GND"), ("J3", "IN.GND"), "same cable"),
    ("solder", ("J3", "VBUS"), ("U5", "X1.VIN+"), "#4090 VBUS pad to USB-C INA228 VIN+"),
    ("solder", ("U5", "X1.VIN-"), ("P1", "VBUS"), "USB-C INA228 VIN- to #5978 VBUS pad"),
    ("solder", ("J3", "GND"), ("P1", "GND"), "#4090 GND pad to #5978 GND pad"),
    ("mate", ("P1", "OUT.VBUS"), ("U1", "USB.VBUS"), "#5978 plug in the #4755 USB-C"),
    ("mate", ("P1", "OUT.GND"), ("U1", "USB.GND"), "same mating"),
    # --- solar metering
    ("cable", ("PV1", "+"), ("J4", "IN.+"), "panel plug into the #368 jack"),
    ("cable", ("PV1", "-"), ("J4", "IN.-"), "same plug"),
    ("force", ("J4", "+"), ("U4", "X1.VIN+"), "#368 + to solar INA228 VIN+"),
    ("force", ("U4", "X1.VIN-"), ("P2", "+"), "solar INA228 VIN- to #369 +"),
    ("force", ("J4", "-"), ("P2", "-"), "#368 - to #369 -"),
    ("mate", ("P2", "OUT.+"), ("U1", "DC.+"), "#369 plug in the #4755 DC jack"),
    ("mate", ("P2", "OUT.-"), ("U1", "DC.-"), "same mating"),
    # --- BB1 jumpers
    ("jumper", "BB1:e40", "BB1:f40", "charger VBUS across the trench to the divider"),
    ("jumper", "BB1:j52", "BB1:B-52", "divider bottom to ground"),
    ("jumper", "BB1:e37", "BB1:f37", "charger ISET across the trench to its network"),
    ("jumper", "BB1:j31", "BB1:B-31", "C4 to ground"),
    ("jumper", "BB1:j29", "BB1:B-29", "R8 to ground"),
    ("jumper", "BB1:g24", "BB1:g19", "S7V8F3 VOUT to the BATTERY link"),
    ("jumper", "BB1:j18", "BB1:B+18", "BATTERY link out (3V3) to the 3V3 rail"),
    # --- BB1 to the TX NUCLEO (Arduino sockets take an M end)
    ("dupont", "BB1:c35", ("A1", "CN9.6"), "M-M: charger PGOOD to D5 (PB8)"),
    ("dupont", "BB1:c34", ("A1", "CN9.7"), "M-M: charger CHG to D6 (PB10)"),
    ("dupont", "BB1:g48", ("A1", "CN8.3"), "M-M: VIN_SENSE to A2 (PA10)"),
    ("dupont", "BB1:f33", ("A1", "CN8.1"), "M-M: ISET node to A0 (PB1)"),
    ("dupont", "BB1:i18", ("A1", "CN6.4"), "M-M: 3V3 strip to CN6.4 (mode B: into the NUCLEO; mode A: out of it)"),
    ("dupont", "BB1:i23", ("A1", "CN6.7"), "M-M: S7V8F3 GND strip to GND (mode-B return, never moves)"),
    ("dupont", "BB1:B-27", ("A1", "CN6.6"), "M-M: BB1 ground rail to GND (analog reference, QT grounds)"),
    ("dupont", "BB1:h12", ("A1", "CN5.9"), "M-M: SDA to D14 (PA11)"),
    ("dupont", "BB1:h11", ("A1", "CN5.10"), "M-M: SCL to D15 (PA12)"),
    # --- BB3 jumpers
    ("jumper", "BB3:f21", "BB3:f20", "wind: the two returns together"),
    ("jumper", "BB3:g21", "BB3:g25", "wind returns out past the jack"),
    ("jumper", "BB3:j25", "BB3:B-25", "wind returns to ground"),
    ("jumper", "BB3:j15", "BB3:B+15", "3V3 to the wind pull-ups"),
    ("jumper", "BB3:i9", "BB3:i13", "rain return out past the jack"),
    ("jumper", "BB3:j13", "BB3:B-13", "rain return to ground"),
    ("jumper", "BB3:j4", "BB3:B+4", "3V3 to the rain pull-up"),
    ("jumper", "BB3:e38", "BB3:f38", "OLED 3V3 pin across the trench to its link"),
    ("jumper", "BB3:j37", "BB3:B+37", "3V3 to the OLED link"),
    # --- BB3 to the TX NUCLEO (morpho pins take an F end)
    ("dupont", "BB3:i19", ("A1", "CN9.5"), "M-M: cups to D4 (PB5)"),
    ("dupont", "BB3:i18", ("A1", "CN8.2"), "M-M: vane to A1 (PB2)"),
    ("dupont", "BB3:f8", ("A1", "CN8.4"), "M-M: rain to A3 (PB4)"),
    ("dupont", "BB3:B+28", ("A1", "CN7.16"), "M-F: 3V3 from the morpho 3V3 pin"),
    ("dupont", "BB3:B-28", ("A1", "CN5.7"), "M-M: BB3 ground rail to GND"),
    ("dupont", "BB3:c37", ("A1", "CN10.20"), "M-F: OLED GND strip straight to CN10.20"),
    ("dupont", "BB3:e43", ("A1", "CN10.11"), "M-F: OLED SCLK (PA5)"),
    ("dupont", "BB3:e44", ("A1", "CN10.15"), "M-F: OLED DIN (PA7)"),
    ("dupont", "BB3:e51", ("A1", "CN10.17"), "M-F: OLED CS (PA4)"),
    ("dupont", "BB3:e40", ("A1", "CN10.21"), "M-F: OLED DC (PC2)"),
    ("dupont", "BB3:e52", ("A1", "CN10.23"), "M-F: OLED RST (PC1)"),
    # --- weather meter cables into the RJ11 jacks
    *[("cable", ("M1", p), ("J1", p), "wind cable in the RJ11 wind jack") for p in ("2", "3", "4", "5")],
    *[("cable", ("M2", p), ("J2", p), "rain cable in the RJ11 rain jack") for p in ("3", "4")],
    # --- I2C: sensor branch (W2) and power branch (W3), header ends seated on BB1
    *qt("W2", "Q", "U8", "P1", "sensor branch: QT-to-header cable into hub port 1"),
    *qt("U8", "P2", "U9", "QT1", "hub to SHT45"), *qt("U8", "P3", "U10", "QT1", "hub to SHTC3"),
    *qt("U8", "P4", "U11", "QT1", "hub to BMP581"), *qt("U8", "P5", "U12", "QT1", "hub to LTR390"),
    *qt("W3", "Q", "U3", "QT1", "power branch: QT-to-header cable into the load INA228"),
    *qt("U3", "QT2", "U2", "QT1", "load INA228 to battery INA228"),
    *qt("U2", "QT2", "U6", "QT1", "battery INA228 to the gauge"),
    *qt("U6", "QT2", "U5", "QT1", "gauge to USB-C INA228"),
    *qt("U5", "QT2", "U4", "QT1", "USB-C INA228 to solar INA228"),
    # --- USB to the Mac
    ("cable", ("H1", "P1.VBUS"), ("A1", "USB.VBUS"), "TX ST-LINK USB (stays in, modes A and B)"),
    ("cable", ("H1", "P1.GND"), ("A1", "USB.GND"), "same cable"),
    ("cable", ("H1", "P2.VBUS"), ("A2", "USB.VBUS"), "RX ST-LINK USB, its own direct Mac port"),
    ("cable", ("H1", "P2.GND"), ("A2", "USB.GND"), "same cable"),
]
# Force leads (20 AWG, 33 mohm/m): 80 mm is 2.7 mohm, 4 mV and 6 mW at 1.5 A; the limit keeps the island tidy.
LIMIT_MM = {"force": 80, "pigtail": 60, "reg": 100, "sense": 150, "dupont": 200, "qt": 200, "solder": 80}
QT_HEADER_MM = 150   # Adafruit #4209
# Strips that may hold force-net copper with more than one thing in them: the regulator supply (the one
# tolerated breadboard path) and the NTC return on the charger's own GND pin (75 uA, decision D2).
FORCE_STRIP_OK = {("U7", "VIN"): 2, ("U1", "H.GND1"): 2}


# ------------------------------------------------------------------ geometry queries
def pin_xy(end):
    if isinstance(end, str):
        x, y, _r, _c = hole_xy(end)
        return x, y
    ref, pin = end
    if (ref, pin) in PLUG_XY:
        return PLUG_XY[(ref, pin)]
    if (ref, pin) in ON_BB:
        x, y, _r, _c = hole_xy(ON_BB[(ref, pin)])
        return x, y
    if ref not in PLACE or pin not in LOCAL[PLACE[ref]["kind"]]:
        return None
    return local_xy(ref, pin)


def between(h1, h2):
    """Holes strictly between two holes on a straight run (under a flat jumper or a lying resistor)."""
    b1, r1, c1 = parse(h1)
    _b2, r2, c2 = parse(h2)
    if r1 == r2:
        lo, hi = sorted((c1, c2))
        out = [f"{b1}:{r1}{c}" for c in range(lo + 1, hi)]
    elif c1 == c2:
        i1, i2 = sorted((ROW_ORDER.index(r1), ROW_ORDER.index(r2)))
        out = [f"{b1}:{r}{c1}" for r in ROW_ORDER[i1 + 1:i2]]
    else:
        out = []
    return [h for h in out if hole_exists(h)]


def covered():
    """Holes nobody can use: under a module's board (except its own pins), a plug hovering over a board,
    a flat jumper or a lying resistor."""
    out = {}
    own = defaultdict(set)
    for (ref, _pin), h in ON_BB.items():
        own[ref].add(h)
    for ref, pl in PLACE.items():
        if "seat" not in pl and "mate" not in pl:
            continue
        x, y, w, h = outline(ref)
        for hole in ALL_HOLES:
            hx, hy, _r, _c = hole_xy(hole)
            if x - 0.1 <= hx <= x + w + 0.1 and y - 0.1 <= hy <= y + h + 0.1 and hole not in own[ref]:
                out.setdefault(hole, f"{ref} body")
    for ref in sorted({r for (r, _p) in ON_BB}):
        if ref.startswith(LYING) and (ref, "1") in ON_BB and (ref, "2") in ON_BB:
            for hole in between(ON_BB[(ref, "1")], ON_BB[(ref, "2")]):
                out.setdefault(hole, f"{ref} body")
    for kind, a, b, _n in CONDUCTORS:
        if kind == "jumper":
            for hole in between(a, b):
                out.setdefault(hole, f"jumper {a.split(':')[1]}-{b.split(':')[1]}")
    return out


COVERED = covered()


def physical_groups():
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def node(end):
        return ("hole", strip_of(end)) if isinstance(end, str) else end

    for pin, hole in ON_BB.items():
        union(pin, ("hole", strip_of(hole)))
    for _k, a, b, _n in CONDUCTORS:
        union(node(a), node(b))
    for p in PARTS:
        for tie in p.get("ties", []):
            for t in tie[1:]:
                union((p["ref"], tie[0]), (p["ref"], t))
    return find


def model_groups():
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for net, (members, _a) in NETS.items():
        for m in members:
            parent[find(m)] = find(("net", net))
    for p in PARTS:
        for tie in p.get("ties", []):
            for t in tie[1:]:
                parent[find((p["ref"], tie[0]))] = find((p["ref"], t))
    return find


def occupants():
    """Every hole in use, with what is in it."""
    occ = defaultdict(list)
    for pin, h in ON_BB.items():
        occ[h].append(pin)
    for k, a, b, _n in CONDUCTORS:
        for e, other in ((a, b), (b, a)):
            if isinstance(e, str):
                occ[e].append((k, other))
    return occ


# ------------------------------------------------------------------ checks
def check():
    fails, notes = [], []
    fails += [f"[2] {e}" for e in SEAT_ERRORS]
    occ = occupants()
    for h in occ:
        if not hole_exists(h):
            fails.append(f"[2] {h}: there is no hole there (rail gap or past the end)")
    pins = [(p["ref"], pin[0]) for p in PARTS for pin in p["pins"]]
    fp, fm = physical_groups(), model_groups()
    # 1 same partition of every model pin
    phys, mod = defaultdict(set), defaultdict(set)
    for pin in pins:
        phys[fp(pin)].add(pin)
        mod[fm(pin)].add(pin)
    as_sets = lambda d: {frozenset(s) for s in d.values()}   # noqa: E731
    model_sets = {s for s in as_sets(mod) if len(s) > 1 or any(fm(p) != p for p in s)}
    for s in as_sets(phys) - as_sets(mod):
        fails.append(f"[1] built copper differs from the schematic: {sorted(s)[:8]}{' ...' if len(s) > 8 else ''}")
    for s in model_sets - as_sets(phys):
        fails.append(f"[1] schematic group not reproduced by the build: {sorted(s)[:8]}{' ...' if len(s) > 8 else ''}")
    # 2 holes: one occupant each, never under a board, a plug, a jumper or a resistor
    for h, things in occ.items():
        if len(things) > 1:
            fails.append(f"[2] hole {h} holds {len(things)} things: {things}")
        if h in COVERED:
            fails.append(f"[2] hole {h} is under the {COVERED[h]}")
    # 3 force-net copper may sit in a strip only alone (no current can flow through the strip)
    force_nets = [n for n, (_m, a) in NETS.items() if a.get("force")]
    per_strip = defaultdict(list)
    for h, things in occ.items():
        per_strip[strip_of(h)] += things
    for strip, things in per_strip.items():
        g = fp(("hole", strip))
        hit = [net for net in force_nets if any(fp(m) == g for m in NETS[net][0])]
        if not hit:
            continue
        ok = [lim for pin, lim in FORCE_STRIP_OK.items() if pin in things]
        if len(things) > (ok[0] if ok else 1):
            fails.append(f"[3] force net {hit[0]} on breadboard strip {strip} with {len(things)} things in it")
    # 4 jumpers straight and in the kit; lead lengths
    for kind, a, b, note in CONDUCTORS:
        if kind == "jumper":
            s = span(a, b)
            if a.split(":")[0] != b.split(":")[0] or s is None or s not in KIT_SPANS:
                fails.append(f"[4] jumper {a}-{b} ({note}) spans {s}: not a straight kit length on one board")
        if kind in LIMIT_MM:
            pa, pb = pin_xy(a), pin_xy(b)
            if (pa is None or pb is None) and not {a[0], b[0]} & UNPLACED_OK:
                fails.append(f"[4] {kind} {a} -> {b}: an end has no plate position, length unchecked")
            if pa and pb:
                d = math.dist(pa, pb) * 1.15 + 10      # routing slack and strip-back
                if d > LIMIT_MM[kind]:
                    fails.append(f"[4] {kind} {a} -> {b} about {d:.0f} mm, limit {LIMIT_MM[kind]} mm ({note})")
    for ref, (a, b, limit) in PART_SPANS.items():
        d = math.dist(pin_xy(a), pin_xy(b)) * 1.15 + 10
        if d > limit:
            fails.append(f"[4] {ref} about {d:.0f} mm, limit {limit} mm")
        notes.append(f"{ref} (the ground tie) about {d:.0f} mm")
    for cable in ("W2", "W3"):
        head = pin_xy((cable, "H.SDA"))
        far = next(pin_xy(b if a == (cable, "Q.SDA") else a) for k, a, b, _n in CONDUCTORS
                   if k == "qt" and (cable, "Q.SDA") in (a, b))
        d = math.dist(head, far) * 1.15 + 10
        if d > QT_HEADER_MM:
            fails.append(f"[4] QT-to-header cable {cable} needs about {d:.0f} mm, it is {QT_HEADER_MM} mm")
    ntc = max(math.dist(NTC_BEAD, pin_xy(("RT1", p))) for p in ("1", "2")) * 1.15 + 10
    notes.append(f"NTC leads need about {ntc:.0f} mm from the pack to BB1 [TBD-MEASURE: #372 lead length]")
    # 5 parts inside the plate and not overlapping
    rects = {r: outline(r) for r in PLACE}
    rects.update({b: (x, y, BB_W, BB_H) for b, (x, y) in BOARDS.items()})
    for r, (x, y, w, h) in rects.items():
        if x < 0 or y < 0 or x + w > PLATE_W or y + h > PLATE_H:
            fails.append(f"[5] {r} leaves the plate")
    host = {r: (pl["seat"][1].split(":")[0] if "seat" in pl else pl["mate"][1][0])
            for r, pl in PLACE.items() if "seat" in pl or "mate" in pl}
    names = sorted(rects)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if host.get(a) == b or host.get(b) == a:
                continue
            if (a in ("P1", "P2") and b in BOARDS) or (b in ("P1", "P2") and a in BOARDS):
                continue      # the plugs hover at the charger's height
            if {a, b} == {"P1", "P2"}:
                notes.append("P1 and P2 outlines overlap in plan by a few mm; they sit at different heights "
                             "[TBD-MEASURE: fit both plugs in the #4755 together]")
                continue
            ax, ay, aw, ah = rects[a]
            bx, by, bw, bh = rects[b]
            if ax < bx + bw - 0.5 and bx < ax + aw - 0.5 and ay < by + bh - 0.5 and by < ay + ah - 0.5:
                fails.append(f"[5] {a} overlaps {b}")
    notes.append(f"{len(ON_BB)} pins in breadboard holes, {len(CONDUCTORS)} conductors, "
                 f"{sum(1 for c in CONDUCTORS if c[0] == 'jumper')} BOJACK jumpers")
    return fails, notes


if __name__ == "__main__":
    fails, notes = check()
    for n in notes:
        print("note ", n)
    for f in fails:
        print("FAIL ", f)
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} failure(s)")
    sys.exit(1 if fails else 0)
