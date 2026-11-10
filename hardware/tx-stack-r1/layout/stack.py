"""TX card cage r2: the physical build, card by card on the SolderFul hole grid, and the cage around them.

Card frame: X along the 30 numbered rows from the card's left edge (row 1 side), Y from the card's FRONT edge
(column a, the lid side) to its BACK edge (column j side, which plugs into the backplane), Z up from the
card's top face. mm throughout; every number comes from ../sources.py.

Box frame (the cage, the backplane, the assembly views): the box hangs on its pole with the back wall on the
pole and the long side vertical. Xb across the box from the inside left wall (seen from the lid), Yb from the
inside back wall toward the lid, Zb up from the inside bottom wall. The cards are horizontal shelves; each
slides toward the back and plugs its right-angle header (column j, rows 1-18) into a socket on the backplane.

Each placement stores its pins (board frame), pads, 3D boxes and the real STEP model to draw, so the checks
(layout_checks.py), the drawings and the renders all read the same geometry.
Hole names: "e5" (column e, row 5), rails "F+5" "F-5" (front); the back rails are snapped off before any
soldering, so the card is CD deep (BH stays the SolderFul grid's reference width). On a card, "B1:e5"; on the
backplane (PAD3U padboard, a separate pad per hole), "BP:s3.12" (line 3, hole 12 along it).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent))
sys.path.append(str(HERE.parent / "schematic"))
import sources as S  # noqa: E402
import model  # noqa: E402

P = S.val("pitch")
BW, BH, BT = S.val("sb_w"), S.val("sb_h"), S.val("sb_t")
X1 = S.val("sb_x1")
LETTER_Y = {c: S.val("sb_ya") + i * P for i, c in enumerate("abcde")}
LETTER_Y.update({c: BH - S.val("sb_ya") - (4 - i) * P for i, c in enumerate("fghij")})
RAIL_Y = {"F+": S.val("sb_rails"), "F-": S.val("sb_rails") + P}   # the back rails are snapped off
CD = S.val("sb_snap_y")                  # card depth after the snap: the new back edge, card frame Y
BOARDS = ["B1", "B2", "B3", "B4"]
ORDER = ["B4", "B2", "B1", "B3"]          # bottom to top in the cage
ROLE = {"B1": "PORTS A", "B2": "PORTS B + METERS", "B3": "CORE", "B4": "POWER"}
HDR = S.val("hdr_plastic")
PCB = S.val("breakout_t")
RAIL_NET = {"F+": "+3V3", "F-": "GND"}    # every card: outer front rail 3.3 V, inner front rail ground


def X(row):
    return X1 + (row - 1) * P


def hole_xy(h):
    """'e5' or 'B+5' -> (X, Y)."""
    for rail in RAIL_Y:
        if h.startswith(rail):
            return X(int(h[len(rail):])), RAIL_Y[rail]
    return X(int(h[1:])), LETTER_Y[h[0]]


ALL_HOLES = [f"{c}{r}" for c in "abcdefghij" for r in range(1, 31)] + \
            [f"{rail}{r}" for rail in RAIL_Y for r in range(1, 31)]


def strip_of(h):
    """The copper a hole belongs to: a row half ('L5' a-e, 'R5' f-j) or a whole rail."""
    for rail in RAIL_Y:
        if h.startswith(rail):
            return rail
    return ("L" if h[0] in "abcde" else "R") + h[1:]


MHOLES = [(BW / 2 - S.val("sb_mhole_span") / 2, BH / 2), (BW / 2, BH / 2), (BW / 2 + S.val("sb_mhole_span") / 2, BH / 2)]


class Box:
    def __init__(self, x0, y0, x1, y1, z0, z1, what, keepout=False, service=False):
        self.x0, self.x1 = sorted((x0, x1))
        self.y0, self.y1 = sorted((y0, y1))
        self.z0, self.z1 = sorted((z0, z1))
        self.what, self.keepout, self.service = what, keepout, service


def tf(rot, x0, y0, x, y):
    """Maker's frame (y up) -> card frame."""
    return {0: (x0 + x, y0 + y), 180: (x0 - x, y0 - y), 90: (x0 - y, y0 + x), 270: (x0 + y, y0 - x)}[rot]


def tbox(rot, x0, y0, b, ref):
    (xa, ya), (xb, yb) = tf(rot, x0, y0, b.x0, b.y0), tf(rot, x0, y0, b.x1, b.y1)
    return Box(xa, ya, xb, yb, b.z0, b.z1, f"{ref} {b.what}", b.keepout, b.service)


# ------------------------------------------------------------------ geometry of the joint card -> backplane
RA_TIP = S.val("ra_offset") + S.val("ra_insulator") + S.val("ra_mate")       # hole centre to pin tip, 9.90
Y_J = LETTER_Y["j"]
Y_MOUTH = Y_J + RA_TIP - S.val("insertion")                                   # socket mouth, card frame
Y_BP = Y_MOUTH + S.val("socket_h")                                            # backplane face, card frame
PIN_Z = S.val("ra_pin_z")
assert abs(Y_BP - CD - S.val("card_bp_gap")) < 0.01, (Y_BP - CD)
Y_INS = Y_J + S.val("ra_offset") + S.val("ra_insulator")                     # insulator front face, card frame


# ------------------------------------------------------------------ footprints
KIND = {  # kind -> (colour, label, STEP models drawn instead of boxes whose name contains a key)
    "BOB": ("#B5121B", "RJ11"), "PTC": ("#E8A317", "PTC"), "RLY": ("#C9B48A", "R"), "DSTAND": ("#C04000", "D"),
    "CAP": ("#3060C0", "C"), "MINI": ("#1A1A1A", "Wio-E5 mini"), "SHTC3": ("#161616", "SHTC3"),
    "INA": ("#161616", "INA228"), "MAX": ("#161616", "MAX17048"), "REG": ("#1D6B33", "S7V8F3"),
    "RAH": ("#202020", "bus header"), "RAS": ("#202020", "SWD"), "LUG": ("#D4AF37", "lug"),
}


def placed(ref, kind, pins, boxes, note="", pads=None, step=None):
    return dict(ref=ref, fp=kind, pins=pins, pads=pads or {}, boxes=boxes, note=note, step=step or [])


def two_pin(ref, kind, h1, h2, note=""):
    """A two-lead part with lead 1 in hole h1 and lead 2 in h2 (model pins '1', '2').
    RLY lying resistor (DIN0207, 7.62 or more), DSTAND standing DO-35 (body on lead 1's hole),
    PTC standing radial (leads formed to the span), CAP disc."""
    (xa, ya), (xb, yb) = hole_xy(h1), hole_xy(h2)
    xm, ym = (xa + xb) / 2, (ya + yb) / 2
    along_x = abs(xb - xa) > abs(yb - ya)
    span = abs(xb - xa) + abs(yb - ya)

    def body(l, w, z0, z1, what, cx=xm, cy=ym):
        return Box(cx - (l if along_x else w) / 2, cy - (w if along_x else l) / 2,
                   cx + (l if along_x else w) / 2, cy + (w if along_x else l) / 2, z0, z1, f"{ref} {what}")
    if kind == "RLY":
        boxes = [body(6.3, 2.5, 0.1, 0.1 + S.val("r_lying_h"), "resistor body"),
                 body(span, 0.6, 0, 1.0, "resistor leads")]
    elif kind == "DSTAND":
        dl, dd = S.val("do35")
        boxes = [Box(xa - dd / 2, ya - dd / 2, xa + dd / 2, ya + dd / 2, 0.8, 0.8 + dl, f"{ref} diode body"),
                 body(span, 0.6, S.val("diode_stand_h") - 1.2, S.val("diode_stand_h"), "diode lead loop")]
    elif kind == "PTC":
        w, t, h = S.val("ptc")
        boxes = [body(w, t, 1.0, 1.0 + h, "MF-R010 body")]
    elif kind == "CAP":
        boxes = [body(3.8, 2.6, 0.5, S.val("cap_h"), "disc capacitor")]
    else:
        raise ValueError(kind)
    return placed(ref, kind, {"1": (xa, ya), "2": (xb, yb)}, boxes, note)


TONGUE_Y1 = CD + S.val("tongue")[1]


def bob(ref, y_top, note):
    """BOB-14021 + 87180 jack turned so the mouth faces +X, flush with the card's right edge, on a bonded
    printed spacer. Its six holes are pads (flying leads to the card); none of its pins goes into the card."""
    peg = S.val("bob_peg_y")
    mouth = peg + 7.88                                  # KiCad fab: pegs 8.89, mouth 16.77 from pin-1 row
    x0, y0 = BW - mouth, y_top                          # rot 270: maker +y -> +X, maker +x -> -Y
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    sp = S.val("bob_spacer")
    mk = [Box(0, 0, S.val("bob_w"), S.val("bob_d"), 0, sp, "printed spacer"),
          Box(0, 0, S.val("bob_w"), S.val("bob_d"), sp, sp + PCB, "BOB-14021 PCB"),
          Box(7.62 - jw / 2, mouth - jd, 7.62 + jw / 2, mouth, sp + PCB, sp + PCB + jh, "87180-066LF jack"),
          Box(7.62 - S.val("plug_6p")[0] / 2, mouth, 7.62 + S.val("plug_6p")[0] / 2, mouth + S.val("plug_len"),
              sp + PCB + 1, sp + PCB + 1 + S.val("plug_6p")[2], "RJ11 plug (standard 6P body after Cinch 32-5996UL)",
              keepout=True)]
    pads = {str(i): tf(270, x0, y0, 13.97 - (i - 1) * P, 1.27) for i in range(1, 7)}
    boxes = [tbox(270, x0, y0, b, ref) for b in mk]
    if y_top > CD:          # overhangs the snapped back edge: the printed spacer carries a tongue in the card plane
        boxes.append(Box(BW - S.val("tongue")[0], CD, BW, TONGUE_Y1, -BT, 0, f"{ref} printed spacer tongue"))
    return placed(ref, "BOB", {}, boxes, note, pads, step=[("BOB", 270, x0, y0 + 0.0)])


MINI_B_Y, MINI_D_Y, MINI_X0 = 20.4535, 2.6735, 16.1925


def mini(ref, first_row, note):
    """Wio-E5 mini, rot 0, D row in column c and B row in column h (17.78 apart), pins along rows."""
    x0 = X(first_row) - MINI_X0
    y0 = LETTER_Y["c"] - MINI_D_Y
    pins = {f"B{k}": (x0 + MINI_X0 + (k - 1) * P, y0 + MINI_B_Y) for k in range(1, 13)}
    pins.update({f"D{k}": (x0 + MINI_X0 + (12 - k) * P, y0 + MINI_D_Y) for k in range(1, 13)})
    pins = {k: v for k, v in pins.items()}
    w, d, top = S.val("mini_w"), S.val("mini_d"), HDR + PCB
    sma = S.val("mini_sma")
    mk = [Box(MINI_X0 - 1.27, MINI_B_Y - 1.27, MINI_X0 + 11 * P + 1.27, MINI_B_Y + 1.27, 0, HDR, "header plastic B"),
          Box(MINI_X0 - 1.27, MINI_D_Y - 1.27, MINI_X0 + 11 * P + 1.27, MINI_D_Y + 1.27, 0, HDR, "header plastic D"),
          Box(0, 0, w, d, HDR, top, "Wio-E5 mini PCB"),
          Box(27.909, 5.557, 39.909, 17.557, top, top + S.val("mini_module_h"), "LoRa-E5 module"),
          Box(-1.2, 7.15, 6.15, 16.09, top, top + S.val("mini_usbc_h"), "USB-C receptacle"),
          Box(w + S.val("mini_sma_out") - 16.5, 9.3345 - sma / 2, w + S.val("mini_sma_out"), 9.3345 + sma / 2,
              HDR + PCB / 2 - sma / 2, HDR + PCB / 2 + sma / 2, "SMA-K"),
          Box(-21.2, 11.617 - 6, -1.2, 11.617 + 6, top + 1.6 - S.val("usbc_plug") / 2, top + 1.6 + S.val("usbc_plug") / 2,
              "USB-C console plug (lid open)", keepout=True, service=True),
          Box(5.37, 19.16, 9.87, 22.36, top, top + 2.5, "BOOT button"),
          Box(5.37, 0.88, 9.87, 4.08, top, top + 2.5, "RESET button")]
    # the right-angle SMA adapter on the mini's SMA, its free arm pointing toward the lid (maker -y, +Yb), where the
    # deeper printed base leaves room for the plug and the cable's bend in front of the cards
    ax, ay = w + S.val("mini_sma_out"), 9.3345
    arm1, arm2 = S.val("sma_ra")
    mk.append(Box(ax, ay - 4, ax + arm1, ay + 4, HDR + PCB / 2 - 4, HDR + PCB / 2 + 4, "SMA right-angle adapter"))
    mk.append(Box(ax + arm1 - 8, ay - arm2, ax + arm1, ay, HDR + PCB / 2 - 4, HDR + PCB / 2 + 4,
                  "SMA adapter forward arm"))
    return placed(ref, "MINI", pins, [tbox(0, x0, y0, b, ref) for b in mk], note, step=[("MINI", 0, x0, y0)])


def breakout(ref, kind, size, names, x_first, rot, hole, extra=(), note="", pads=None, pin_y=2.54):
    """An Adafruit/Pololu breakout standing on its own header; names[i] at maker (x_first + i P, pin_y)."""
    w, d = size
    mx = {n: (x_first + i * P, pin_y) for i, n in enumerate(names) if n}
    first = next(n for n in names if n)
    hx, hy = hole_xy(hole)
    ax, ay = tf(rot, 0, 0, *mx[first])
    x0, y0 = hx - ax, hy - ay
    mk = [Box(x_first - 1.27, pin_y - 1.27, x_first + (len(names) - 1) * P + 1.27, pin_y + 1.27, 0, HDR, "header plastic"),
          Box(0, 0, w, d, HDR, HDR + PCB, f"{KIND[kind][1]} PCB")] + list(extra)
    pins = {n: tf(rot, x0, y0, *xy) for n, xy in mx.items()}
    return placed(ref, kind, pins, [tbox(rot, x0, y0, b, ref) for b in mk], note,
                  {n: tf(rot, x0, y0, *xy) for n, xy in (pads or {}).items()},
                  step=[(kind, rot, x0, y0)])


def ra_header(ref, n, first_hole, toward, kind="RAH", note="", names=None):
    """Right-angle 1xn male header, pins along +X from first_hole, mating ends pointing +Y ('back') or
    -Y ('front'). Boxes: insulator, mating pins, tails below the card."""
    hx, hy = hole_xy(first_hole)
    names = names or [str(i + 1) for i in range(n)]
    pins = {nm: (hx + i * P, hy) for i, nm in enumerate(names)}
    s = 1 if toward == "back" else -1
    off, ins, mate, tail = S.val("ra_offset"), S.val("ra_insulator"), S.val("ra_mate"), S.val("ra_tail")
    xa, xb = hx - 1.27, hx + (n - 1) * P + 1.27
    boxes = [Box(xa, hy + s * off, xb, hy + s * (off + ins), 0, 2 * PIN_Z, f"{ref} right-angle insulator"),
             Box(xa, hy + s * (off + ins), xb, hy + s * RA_TIP, PIN_Z - 0.32, PIN_Z + 0.32, f"{ref} mating pins"),
             Box(xa, hy - 0.4, xb, hy + s * off, 0, PIN_Z + 0.32, f"{ref} pin bends"),
             Box(xa, hy - 0.4, xb, hy + 0.4, -(tail - BT + BT), -BT, f"{ref} solder tails")]
    if kind == "RAS":
        boxes.append(Box(xa, hy + s * RA_TIP, xb, hy + s * (RA_TIP + 14), 0, 2.6, f"{ref} SWD Dupont housings",
                         keepout=True, service=True))
    return placed(ref, kind, pins, boxes, note)


# ------------------------------------------------------------------ the cards
PLACE = {b: [] for b in BOARDS}
WIRES = []          # (kind, end1, end2, side, note); ends "B1:e5", "BP:s3.12" or (ref, pin) pads / off-card pins


def w(kind, a, b, side="bottom", note=""):
    WIRES.append((kind, a, b, side, note))


def bus_row(net, which=0):
    rows = [i + 1 for i, n in enumerate(model.BUS) if n == net]
    return rows[which]


for b in BOARDS:
    PLACE[b].append(ra_header(model.HEADERS[b], 18, "j1", "back", note="bus header, mating pins toward the backplane"))
    # the bus 3.3 V and both bus grounds to the front rails, on the underside
    w("wire", f"{b}:i{bus_row('+3V3')}", f"{b}:F+1", note="bus 3.3 V supply to the front 3.3 V rail")
    w("wire", f"{b}:i{bus_row('GND')}", f"{b}:F-{2 if b != 'B1' else 3}", note="bus ground to the front ground rail")
    w("wire", f"{b}:i{bus_row('GND', 1)}", f"{b}:F-20", note="second bus ground to the front ground rail")


def port(card, k, p, y_bob):
    """Sensor port k on rows p-1..p+3 (L half): 3.3 V strip p, data p+1, clock p+2, grounds p-1 and p+3;
    data and clock cross the channel on their series resistors to the bus strips of the same rows."""
    assert bus_row(f"P{k}_SDA") == p + 1 and bus_row(f"P{k}_SCL") == p + 2, (k, p)
    pl = PLACE[card]
    pl.append(two_pin(f"F{k}", "PTC", f"F+{p}", f"a{p}", f"port S{k} 3.3 V fuse, standing, leads formed to 7.62"))
    pl.append(two_pin(f"D{k}2", "DSTAND", f"b{p + 1}", f"b{p}", f"port S{k} data to its 3.3 V, body on the data side"))
    pl.append(two_pin(f"D{k}4", "DSTAND", f"c{p + 2}", f"c{p}", f"port S{k} clock to its 3.3 V, body on the clock side"))
    pl.append(two_pin(f"D{k}1", "DSTAND", f"d{p}", f"d{p - 1}", f"port S{k} 3.3 V zener, cathode band to row {p}"))
    pl.append(two_pin(f"D{k}3", "DSTAND", f"d{p + 3}", f"d{p + 1}", f"port S{k} ground to data, band to row {p + 1}"))
    pl.append(two_pin(f"D{k}5", "DSTAND", f"b{p + 3}", f"b{p + 2}", f"port S{k} ground to clock, band to row {p + 2}"))
    pl.append(two_pin(f"R{k}1", "RLY", f"e{p + 1}", f"f{p + 1}", f"port S{k} data series 100, across the channel"))
    pl.append(two_pin(f"R{k}2", "RLY", f"e{p + 2}", f"f{p + 2}", f"port S{k} clock series 100, across the channel"))
    for g in (p - 1, p + 3):
        w("jumper", f"{card}:a{g}", f"{card}:F-{g}", "top", f"port S{k} ground strip to the ground rail")
    jack = f"J1{k}"
    pl.append(bob(jack, y_bob, f"S{k} jack, mouth flush with the right edge"))
    for pin, hole, what in (("2", f"e{p}", "3.3 V"), ("3", f"a{p + 1}", "data (SDA)"), ("4", f"e{p + 3}", "ground"),
                            ("5", f"a{p + 2}", "clock (SCL)")):
        w("lead", (jack, pin), f"{card}:{hole}", "top", f"S{k} jack contact {pin} {what}")


BOB_Y = [S.val("bob_w"), 2 * S.val("bob_w") + 0.5, 3 * S.val("bob_w") + 1.0]   # back-most edge of the three breakouts
# Three 15.24 mm breakouts need 46.72 mm of the 41.91 mm card: the front one is flush with the front edge and the
# back one overhangs the snapped back edge by 4.8 mm, its spacer's tongue held in the right corner post
# B1: ports S1-S3
port("B1", 1, 2, BOB_Y[2])
port("B1", 2, 7, BOB_Y[1])
port("B1", 3, 12, BOB_Y[0])
# B2: port S4 and the weather meters
port("B2", 4, 16, BOB_Y[2])
for name, jack_net, r_pull, cap, zen, r_ser, gnd_row, line in (
        ("cups", "CUPS_J", "R1", "C1", "D51", "R4", 4, "CUPS"),
        ("vane", "VANE_J", "R2", "C3", "D52", "R5", 7, "VANE"),
        ("rain", "RAIN_J", "R3", "C2", "D53", "R6", 10, "RAIN")):
    m = bus_row(line)
    PLACE["B2"] += [two_pin(r_pull, "RLY", f"F+{m}", f"a{m}", f"{name} pull-up 10k, lying over the ground rail"),
                    two_pin(cap, "CAP", f"b{m}", f"b{gnd_row}", f"{name} filter 100 nF"),
                    two_pin(zen, "DSTAND", f"c{m}", f"c{gnd_row}", f"{name} clamp zener, band to row {m}"),
                    two_pin(r_ser, "RLY", f"e{m}", f"f{m}", f"{name} series 1k, across the channel")]
for g in (4, 7, 10):
    w("jumper", f"B2:a{g}", f"B2:F-{g}", "top", "meter ground strip to the ground rail")
PLACE["B2"].append(bob("J21", BOB_Y[1], "wind jack, mouth flush with the right edge"))
PLACE["B2"].append(bob("J22", BOB_Y[0], "rain jack, mouth flush with the right edge"))
w("lead", ("J21", "2"), "B2:e4", "top", "wind jack contact 2 ground")
w("lead", ("J21", "3"), "B2:d4", "top", "wind jack contact 3 ground")
w("lead", ("J21", "4"), f"B2:d{bus_row('CUPS')}", "top", "wind jack contact 4 cups")
w("lead", ("J21", "5"), f"B2:d{bus_row('VANE')}", "top", "wind jack contact 5 vane")
w("lead", ("J22", "3"), "B2:d10", "top", "rain jack contact 3 ground")
w("lead", ("J22", "4"), f"B2:d{bus_row('RAIN')}", "top", "rain jack contact 4 rain")

# B3: CORE
PLACE["B3"].append(mini("A1", 19, "on its own header; D row column c, B row column h, rows 19-30; SMA past the right edge"))
PLACE["B3"].append(ra_header("J3", 5, "a12", "front", "RAS", "SWD, right angle, pins out over the front edge"))
PLACE["B3"].append(breakout("U5", "SHTC3", S.val("shtc3"), ["VIN", "3V", "GND", "SCL", "SDA"], 7.62, 180, "c8",
                            [Box(20.5, 5.9, 25.4, 11.9, HDR + PCB, HDR + PCB + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 4.9, 11.9, HDR + PCB, HDR + PCB + S.val("qt_h"), "QT socket")],
                            "enclosure air sensor, top card, away from the charger"))
for a, b_, n in (("g1", "g20", "3.3 V supply to the mini (B2) and SWD"), ("d8", "h1", "3.3 V supply to the SHTC3"),
                 ("g2", "g24", "ground to the mini (B6)"), ("d6", "h2", "ground to the SHTC3"),
                 ("g12", "d19", "ground to the mini (D12)"), ("i24", "h12", "ground: mini B6 and D12 joined"),
                 (f"g{bus_row('I2C_SCL')}", "d20", "I2C clock (SCL) to the mini (PB15)"),
                 ("d5", f"h{bus_row('I2C_SCL')}", "I2C clock (SCL) to the SHTC3"),
                 (f"g{bus_row('I2C_SDA')}", "d21", "I2C data (SDA) to the mini (PA15)"),
                 ("d4", f"h{bus_row('I2C_SDA')}", "I2C data (SDA) to the SHTC3"),
                 (f"g{bus_row('MUX_RST')}", "g26", "mux reset from the mini (PB14)"),
                 (f"g{bus_row('CUPS')}", "d27", "cups pulse to the mini (PC0)"),
                 (f"g{bus_row('VANE')}", "d23", "vane voltage to the mini (PB3)"),
                 (f"g{bus_row('RAIN')}", "d22", "rain pulse to the mini (PB4)"),
                 ("f20", "b12", "SWD 3.3 V"), ("f21", "b13", "SWD debug data (PA13)"),
                 ("f22", "b14", "SWD debug clock (PA14)"), ("f23", "b15", "SWD reset (NRST)"), ("f24", "b16", "SWD ground")):
    w("wire", f"B3:{a}", f"B3:{b_}", "bottom", n)

# B4: POWER
T_ = HDR + PCB
PLACE["B4"].append(breakout("U2", "INA", S.val("ina228"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", None, None, None, "H.ALRT"],
                            3.81, 180, "e10",
                            [Box(20.1, 5.9, 25.4, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 5.3, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(7.7, 14.6, 17.7, 18.2, T_, T_ + 6.0, "soldered battery leads at X1")],
                            "battery monitor; header pins 5-7 pulled; battery leads on the X1 pads",
                            pads={"X1.VIN-": (9.2, 16.383), "X1.VIN+": (16.2, 16.383)}))
PLACE["B4"].append(breakout("U6", "MAX", S.val("max17048"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", "H.INT", "H.QST"],
                            6.35, 180, "e20",
                            [Box(14.0, 14.5, 20.0, 19.0, T_, T_ + S.val("jstph_h"), "JST PH socket (unused)"),
                             Box(5.4, 14.5, 11.4, 19.0, T_, T_ + S.val("jstph_h"), "JST PH socket (unused)"),
                             Box(20.1, 5.9, 25.4, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 5.3, 11.9, T_, T_ + S.val("qt_h"), "QT socket")],
                            "fuel gauge; cell sense on its JP2 VBAT pad", pads={"JP2.VBAT": (11.43, 11.43)}))
_rw, _rd = S.val("s7v8f3")
PLACE["B4"].append(breakout("U7", "REG", (_rw, _rd), ["VOUT", "GND", "VIN", "SHDN"], 1.905, 0, "f24",
                            [Box(2.2, 3.0, 9.2, 10.0, T_, T_ + S.val("s7v8f3_h"), "inductor")],
                            "3.3 V regulator; pins in row-strips 24-27, board toward the front", pin_y=15.24))
_lx, _ly = MHOLES[2]
PLACE["B4"].append(placed("E1", "LUG", {}, [Box(_lx - 3, _ly - 3, _lx + 3, _ly + 3, 0, 4.5, "E1 M3 nylon screw, nut and lug"),
                                             Box(_lx - 1.5, _ly - 13.5, _lx + 1.5, _ly - 3, 0, 1.93, "E1 lug tail")],
                          "battery + junction: Keystone 7328 on an M3 nylon screw in the right centre hole",
                          pads={"1": (_lx, _ly - 9)}))
for a, b_, n in (("g1", "g24", "3.3 V supply from the regulator"), ("d10", "h1", "3.3 V supply to the INA228"),
                 ("d20", "f1", "3.3 V supply to the MAX17048"), ("g2", "g25", "ground to the regulator"),
                 ("d9", "h2", "ground to the INA228"), ("d19", "f2", "ground to the MAX17048"),
                 ("d8", f"g{bus_row('I2C_SCL')}", "I2C clock (SCL) to the INA228"),
                 ("d18", f"h{bus_row('I2C_SCL')}", "I2C clock (SCL) to the MAX17048"),
                 ("d7", f"g{bus_row('I2C_SDA')}", "I2C data (SDA) to the INA228"),
                 ("d17", f"h{bus_row('I2C_SDA')}", "I2C data (SDA) to the MAX17048")):
    w("wire", f"B4:{a}", f"B4:{b_}", "bottom", n)
w("lead", ("U1", "SYS"), "B4:g26", "top", "charger system output (J3 SYS) to the regulator in, 22 AWG")
# the battery loop: soldered or screwed end to end, never a strip, a header or a socket
w("lead", ("PG1", "L+"), ("E1", "1"), "top", "pack + (pigtail) to the lug, 22 AWG")
w("lead", ("E1", "1"), ("U2", "X1.VIN+"), "top", "lug to the shunt in (X1 VIN+), 22 AWG")
w("lead", ("U2", "X1.VIN-"), ("U1", "BAT"), "top", "shunt out (X1 VIN-) to charger battery + (J5 BATTERY), 22 AWG")
w("lead", ("PG1", "L-"), ("U1", "BATN"), "top", "pack - to charger battery - (J5 GND), 22 AWG")
w("lead", ("E1", "1"), ("R7", "1"), "top", "lug to the charger sense resistor (100 ohm, at the lug, sleeved)")
w("lead", ("R7", "2"), ("U1", "BATP"), "top", "charger battery sense (J5 SNS_BATP), 26 AWG")
w("lead", ("E1", "1"), ("R8", "1"), "top", "lug to the gauge sense resistor (100 ohm, at the lug, sleeved)")
w("lead", ("R8", "2"), ("U6", "JP2.VBAT"), "top", "fuel gauge cell sense (JP2 VBAT), 26 AWG")
w("lead", ("RT1", "1"), ("U1", "TS"), "top", "thermistor to EVM J7")
w("lead", ("RT1", "2"), ("U1", "TSN"), "top", "thermistor return to EVM J7")

# ------------------------------------------------------------------ the backplane (BusBoard PAD3U padboard)
# A piece 21 x 40 holes cut from a PAD3U (a separate plated pad per hole, no strips). Hole lines run vertically
# (along Zb); on line i (1..18) a tinned bus wire on the back (copper) face is soldered at every used pad and
# carries bus line i; line 19 is spare, lines 0 and 20 take the mounting screws. Hole n along a line is at
# Zb = BP_Z0 + (n - 1) P. Each card's socket pins sit in one hole row. Nothing connects unless a wire does.
BP_STRIPS = 20       # lines 0..20 (cut 21 wide)
BP_HOLES = 39
BP_SCREW_HOLES = (2, 36)   # on lines 0 and 20: drilled 3.2 mm for the M3 screws to the cage posts
CAGE_LEFT = S.val("cage_wall") - 2.0              # card left edge, box frame (slots 2 mm deep in the left wall)
BP_X0 = CAGE_LEFT + X(1) - 2 * P                  # backplane left edge: strip 1 under card row 1, two holes margin
FLOOR_LIFT = 0.0                   # the printed base's floor is the cage's: everything stands on it
BP_BACK = FLOOR_LIFT + S.val("cage_plate") + S.val("bp_posts")   # backplane copper face, Yb
BP_FRONT = BP_BACK + S.val("strip_size")[2]        # component face (sockets), Yb
CARD_DY = BP_FRONT - Y_BP                          # Yb = CARD_DY + (Y_BP - Y) ... see card_to_box
PITCH = {("B4", "B2"): 6, ("B2", "B1"): 8, ("B1", "B3"): 8}   # in backplane holes (2.54 mm)
SOCKET_HOLE = {"B4": 13}                           # the mux sits behind holes 1-10, below the cards
BP_Z0 = S.val("power_zone") - (SOCKET_HOLE["B4"] - 1) * P   # first backplane hole, Zb
for lo, hi in PITCH:
    SOCKET_HOLE[hi] = SOCKET_HOLE[lo] + PITCH[(lo, hi)]


def card_z(b):
    """Zb of a card's top face: its header pins (PIN_Z above the face) sit on its socket's hole row."""
    return BP_Z0 + (SOCKET_HOLE[b] - 1) * P - PIN_Z


def card_to_box(b, x, y, z):
    return CAGE_LEFT + x, BP_FRONT + (Y_BP - y), card_z(b) + z


def strip_x(i):
    """Xb of backplane strip i: under card row i (the header pins are on rows 1-18)."""
    return CAGE_LEFT + X(i)


def bp_hole(i, n):
    return f"BP:s{i}.{n}"


def bp_xy(h):
    """'s3.12' -> (Xb, Zb)."""
    i, n = h[1:].split(".")
    return strip_x(int(i)), BP_Z0 + (int(n) - 1) * P


BP_PARTS = []   # (ref, {pin: hole}, note)
for b in BOARDS:
    BP_PARTS.append((model.SOCKETS[b], {str(i): f"s{i}.{SOCKET_HOLE[b]}" for i in range(1, 19)},
                     f"socket for {b} ({ROLE[b]})"))
_free = SOCKET_HOLE["B2"] + 2          # QT lead pins between the B2 and B1 sockets, above B2's header
for k in range(1, 5):
    BP_PARTS.append((f"W{k}", {"H.GND": f"s{bus_row('GND', 1)}.{_free + k - 1}",
                               "H.SDA": f"s{bus_row(f'P{k}_SDA')}.{_free + k - 1}",
                               "H.SCL": f"s{bus_row(f'P{k}_SCL')}.{_free + k - 1}"},
                     f"QT lead S{k}: pins from the front, soldered on the copper side"))
BP_PARTS.append(("XJ1", {"GND": f"s{bus_row('GND')}.11", "SCL": f"s{bus_row('I2C_SCL')}.11",
                         "SDA": f"s{bus_row('I2C_SDA')}.11"}, "charger I2C pins (lead to EVM J8)"))
MUX_HOLES = {"H.VCC": f"s{bus_row('+3V3')}.10", "H.GND": f"s{bus_row('GND')}.10", "H.SCL": f"s{bus_row('I2C_SCL')}.10",
             "H.SDA": f"s{bus_row('I2C_SDA')}.10", "H.RST": f"s{bus_row('MUX_RST')}.10"}
for pad, h in MUX_HOLES.items():
    w("wire", ("U4", pad), f"BP:{h}", "copper", f"mux {pad[2:]} pad lead to its strip")
w("wire", f"BP:s{bus_row('GND')}.38", f"BP:s{bus_row('GND', 1)}.38", "copper",
  "the two bus ground strips joined")
BP_BUS = []          # (line, [holes the tinned bus wire is soldered at]): every used pad on lines 1-18
_used = {}
for _ref, _pins, _n in BP_PARTS:
    for _h in _pins.values():
        _i, _k = (int(v) for v in _h[1:].split("."))
        _used.setdefault(_i, set()).add(_k)
for _k, _a, _c, _s, _n in WIRES:
    for _e in (_a, _c):
        if isinstance(_e, str) and _e.startswith("BP:"):
            _i, _m = (int(v) for v in _e[4:].split("."))
            _used.setdefault(_i, set()).add(_m)
for _i in range(1, 19):
    BP_BUS.append((_i, sorted(_used.get(_i, ()))))
MUX_BOX = (strip_x(2) - 1.27, BP_Z0 + 0.5 * P, strip_x(2) - 1.27 + S.val("mux_w"),
           BP_Z0 + 0.5 * P + S.val("mux_d"))   # on foam on the copper side behind holes 1.5-9.5: Xb and Zb extents

# ------------------------------------------------------------------ cables and matings (off the cards)
CABLES = [(("BT1", "+"), ("PG1", "M+")), (("BT1", "-"), ("PG1", "M-")),
          (("PS1", "VBUS"), ("U1", "VIN1")), (("PS1", "GND"), ("U1", "PGND1")),
          (("PV1", "+"), ("U1", "VIN2")), (("PV1", "-"), ("U1", "PGND2")),
          (("A1", "ANT"), ("AD1", "P")), (("AD1", "J"), ("CX1", "P")), (("CX1", "J"), ("AE1", "RF")),
          (("U1", "J8.1"), ("XJ1", "GND")), (("U1", "J8.2"), ("XJ1", "SCL")), (("U1", "J8.3"), ("XJ1", "SDA"))]
for k in range(1, 5):
    for s in ("GND", "V+", "SDA", "SCL"):
        CABLES.append(((f"W{k}", f"Q.{s}"), ("U4", f"CH{k - 1}.{s}")))
for k, mod in ((1, "MOD1"), (2, "MOD2"), (3, "MOD3")):
    for n in "2345":
        CABLES.append(((f"J1{k}", n), (mod, n)))
for n in "2345":
    CABLES.append((("J21", n), ("M1", n)))
for n in "34":
    CABLES.append((("J22", n), ("M2", n)))
for b in BOARDS:
    for i in range(1, 19):
        CABLES.append(((model.HEADERS[b], str(i)), (model.SOCKETS[b], str(i))))


def placements():
    for b in BOARDS:
        for pl in PLACE[b]:
            yield b, pl


def board_of_ref():
    return {pl["ref"]: b for b, pl in placements()}


def pins_of(pl):
    return dict(pl["pins"])


def pads_of(pl):
    return dict(pl["pads"])


def boxes_of(pl):
    return list(pl["boxes"])


def outline_of(pl):
    bx = [b for b in pl["boxes"] if not b.keepout]
    return min(b.x0 for b in bx), min(b.y0 for b in bx), max(b.x1 for b in bx), max(b.y1 for b in bx)
