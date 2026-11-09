"""TX stack r1: the physical build, board by board, on the SolderFul hole grid.

Frame: X along the 30 numbered rows from the board's left edge (row 1 side), Y from the FRONT edge (the
jack side, column a side), Z up from the board's top face. mm throughout. Every number comes from
../sources.py. Each part is a footprint (pins in its maker's Eagle frame, from the sourced board files)
placed by a rotation and an origin; layout/checks.py proves that every placed pin lands on a hole, that no
strip carries two nets, and that the copper equals ../schematic/model.py.

Hole names: "e5" (column e, row 5), rails "F+5" "F-5" (front) and "B+5" "B-5" (back); on a board, "B1:e5".
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
RAIL_Y = {"F+": S.val("sb_rails"), "F-": S.val("sb_rails") + P, "B+": BH - S.val("sb_rails") - P,
          "B-": BH - S.val("sb_rails")}
BOARDS = ["B1", "B2", "B3", "B4"]
ROLE = {"B1": "PORTS", "B2": "METERS", "B3": "CORE", "B4": "POWER"}
HDR = S.val("hdr_plastic")
PCB = S.val("breakout_t")


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
    """The copper group a hole belongs to: a row half ('L5' a-e, 'R5' f-j) or a whole rail."""
    for rail in RAIL_Y:
        if h.startswith(rail):
            return rail
    return ("L" if h[0] in "abcde" else "R") + h[1:]


# mounting: SolderFul centre-line holes (3.0 mm) and edge half-holes (notches), from the datasheet p.2
MHOLES = [(BW / 2 - S.val("sb_mhole_span") / 2, BH / 2), (BW / 2, BH / 2), (BW / 2 + S.val("sb_mhole_span") / 2, BH / 2)]
_ny = S.val("sb_notch_side_y")
_ne = S.val("sb_notch_end_span")
NOTCHES = [(0, _ny), (0, BH / 2), (0, BH - _ny), (BW, _ny), (BW, BH / 2), (BW, BH - _ny),
           (BW / 2 - _ne / 2, 0), (BW / 2 + _ne / 2, 0), (BW / 2 - _ne / 2, BH), (BW / 2 + _ne / 2, BH)]
STANDOFFS = [("left side notch", 0.0, BH - _ny), ("right centre hole", BW / 2 + S.val("sb_mhole_span") / 2, BH / 2),
             ("right side notch", BW, _ny)]
STANDOFF_R = S.val("standoff_af") / 2 / 0.8660254   # hex corner radius
GAPS = {("B1", "B2"): S.val("standoff_20"), ("B2", "B3"): S.val("standoff_20"), ("B3", "B4"): S.val("standoff_10")}
BRIEF_GAPS = {("B1", "B2"): 20.0, ("B2", "B3"): 10.0, ("B3", "B4"): 10.0}


# ------------------------------------------------------------------ footprints (maker's frame, y up)
class Box:
    def __init__(self, x0, y0, x1, y1, z0, z1, what, keepout=False, service=False):
        self.x0, self.x1 = sorted((x0, x1))
        self.y0, self.y1 = sorted((y0, y1))
        self.z0, self.z1 = sorted((z0, z1))
        self.what, self.keepout, self.service = what, keepout, service


def fp_bob():
    pins = {str(i): (13.97 - (i - 1) * P, 1.27) for i in range(1, 7)}
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    peg = S.val("bob_peg_y")
    front = peg + 7.88                       # KiCad fab: pegs 8.89, mouth 16.77 from pin 1 row
    boxes = [Box(0, 0, 15.24, 2.54, 0, HDR, "header plastic"),
             Box(0, 0, S.val("bob_w"), S.val("bob_d"), HDR, HDR + PCB, "BOB-14021 PCB"),
             Box(7.62 - jw / 2, front - jd, 7.62 + jw / 2, front, HDR + PCB, HDR + PCB + jh, "87180-066LF jack"),
             Box(7.62 - 5.5, front, 7.62 + 5.5, front + 25, HDR + PCB + 1, HDR + PCB + 9, "RJ11 plug", keepout=True)]
    return dict(pins=pins, outline=(0, 0, S.val("bob_w"), S.val("bob_d")), boxes=boxes, colour="#B5121B",
                label="RJ11")


def fp_ptc():
    w, t, h = S.val("ptc")
    return dict(pins={"2": (0, 0), "1": (0, 5.08)}, outline=(-t / 2, 2.54 - w / 2, t / 2, 2.54 + w / 2),
                boxes=[Box(-t / 2, 2.54 - w / 2, t / 2, 2.54 + w / 2, 1.0, 1.0 + h, "MF-R010 body")],
                colour="#E8A317", label="PTC")


def fp_res_v():
    return dict(pins={"2": (0, 0), "1": (0, 5.08)}, outline=(-1.25, -1.25, 1.25, 6.4),
                boxes=[Box(-1.25, -1.25, 1.25, 1.25, 0, S.val("res_v_h"), "resistor body"),
                       Box(-0.4, -0.4, 0.4, 5.5, S.val("res_v_h") - 1.5, S.val("res_v_h"), "resistor lead loop")],
                colour="#C9B48A", label="10k")


def fp_cap():
    return dict(pins={"1": (0, 0), "2": (-P, 0)}, outline=(-3.17, -1.3, 0.63, 1.3),
                boxes=[Box(-3.17, -1.3, 0.63, 1.3, 1.0, S.val("cap_h"), "disc capacitor")],
                colour="#3060C0", label="100n")


def fp_qtlead():
    hh = S.val("qt_lead_h")
    return dict(pins={"H.SDA": (0, 0), "H.GND": (P, 0), "H.SCL": (2 * P, 0)}, outline=(-1.27, -1.27, 2 * P + 1.27, 1.27),
                boxes=[Box(-1.27, -1.27, 2 * P + 1.27, 1.27, 0, hh, "QT lead pin housings")],
                colour="#202020", label="QT")


def fp_mux():
    pads = {f"H.{n}": (38.1, 5.08 + i * P) for i, n in enumerate(["VCC", "GND", "SCL", "SDA", "RST"])}
    foam = S.val("foam")
    boxes = [Box(0, 0, 40.64, 20.32, 0, foam, "foam pad"),
             Box(0, 0, 40.64, 20.32, foam, foam + PCB, "PCA9548 PCB")]
    chans = {}
    for k, x in enumerate((8.89, 16.51, 24.13, 31.75)):
        chans[k] = (x, 0)
        boxes.append(Box(x - 2.1, 0, x + 2.1, 4.25, foam + PCB, foam + PCB + S.val("qt_h"), f"QT socket ch{k}"))
        boxes.append(Box(x - 2.1, -6, x + 2.1, 0, foam + PCB, foam + PCB + S.val("qt_h"), f"QT plug ch{k}", keepout=True))
    boxes.append(Box(36.5, 3.5, 39.7, 16.8, foam + PCB, foam + PCB + 3.0, "pad leads"))
    return dict(pins={}, pads=pads, chans=chans, outline=(0, 0, 40.64, 20.32), boxes=boxes, colour="#161616",
                label="PCA9548 0x71")


MINI_B_Y, MINI_D_Y, MINI_X0 = 20.4535, 2.6735, 16.1925


def fp_mini():
    pins = {f"B{k}": (MINI_X0 + (k - 1) * P, MINI_B_Y) for k in range(1, 13)}
    pins.update({f"D{k}": (MINI_X0 + (12 - k) * P, MINI_D_Y) for k in range(1, 13)})
    w, d, top = S.val("mini_w"), S.val("mini_d"), HDR + PCB
    sma, out = S.val("mini_sma"), S.val("mini_sma_out")
    mid = HDR + PCB / 2
    boxes = [Box(MINI_X0 - 1.27, MINI_B_Y - 1.27, MINI_X0 + 11 * P + 1.27, MINI_B_Y + 1.27, 0, HDR, "header plastic B"),
             Box(MINI_X0 - 1.27, MINI_D_Y - 1.27, MINI_X0 + 11 * P + 1.27, MINI_D_Y + 1.27, 0, HDR, "header plastic D"),
             Box(0, 0, w, d, HDR, top, "Wio-E5 mini PCB"),
             Box(27.909, 5.557, 39.909, 17.557, top, top + S.val("mini_module_h"), "LoRa-E5 module"),
             Box(-1.2, 7.15, 6.15, 16.09, top, top + S.val("mini_usbc_h"), "USB-C receptacle"),
             Box(w + out - 16.5, 9.3345 - sma / 2, w + out, 9.3345 + sma / 2, mid - sma / 2, mid + sma / 2, "SMA-K"),
             Box(w + out, 9.3345 - 4.5, w + out + 20, 9.3345 + 4.5, mid - 4.5, mid + 4.5, "SMA plug, RG-316", keepout=True),
             Box(-21.2, 11.617 - 6, -1.2, 11.617 + 6, top + 1.6 - S.val("usbc_plug") / 2, top + 1.6 + S.val("usbc_plug") / 2,
                 "USB-C console plug (service: B4 lifted off)", keepout=True, service=True),
             Box(5.37, 19.16, 9.87, 22.36, top, top + 2.5, "BOOT button"),
             Box(5.37, 0.88, 9.87, 4.08, top, top + 2.5, "RESET button")]
    return dict(pins=pins, outline=(0, 0, w, d), boxes=boxes, colour="#1A1A1A", label="Wio-E5 mini")


def fp_breakout(name, size, names, x0, extra=(), colour="#161616"):
    w, d = size
    pins = {n: (x0 + i * P, 2.54) for i, n in enumerate(names) if n}
    boxes = [Box(x0 - 1.27, 1.27, x0 + (len(names) - 1) * P + 1.27, 3.81, 0, HDR, "header plastic"),
             Box(0, 0, w, d, HDR, HDR + PCB, f"{name} PCB")] + list(extra)
    return dict(pins=pins, outline=(0, 0, w, d), boxes=boxes, colour=colour, label=name)


def fp_shtc3():
    t = HDR + PCB
    return fp_breakout("SHTC3", S.val("shtc3"), ["VIN", "3V", "GND", "SCL", "SDA"], 7.62,
                       [Box(20.5, 5.9, 25.4, 11.9, t, t + S.val("qt_h"), "QT socket"),
                        Box(0, 5.9, 4.9, 11.9, t, t + S.val("qt_h"), "QT socket")])


def fp_ina():
    t = HDR + PCB
    f = fp_breakout("INA228", S.val("ina228"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", None, None, None, "H.ALRT"], 3.81,
                    [Box(20.1, 5.9, 25.4, 11.9, t, t + S.val("qt_h"), "QT socket"),
                     Box(0, 5.9, 5.3, 11.9, t, t + S.val("qt_h"), "QT socket"),
                     Box(7.7, 14.6, 17.7, 18.2, t, t + 6.0, "soldered battery leads at X1", keepout=True)])
    f["pads"] = {"X1.VIN-": (9.2, 16.383), "X1.VIN+": (16.2, 16.383)}
    f["removed"] = {"H.VBUS": (13.97, 2.54), "H.VIN-": (16.51, 2.54), "H.VIN+": (19.05, 2.54)}
    return f


def fp_max():
    t = HDR + PCB
    f = fp_breakout("MAX17048", S.val("max17048"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", "H.INT", "H.QST"], 6.35,
                    [Box(14.0, 14.5, 20.0, 19.0, t, t + S.val("jstph_h"), "JST PH socket (unused)"),
                     Box(5.4, 14.5, 11.4, 19.0, t, t + S.val("jstph_h"), "JST PH socket (unused)"),
                     Box(20.1, 5.9, 25.4, 11.9, t, t + S.val("qt_h"), "QT socket"),
                     Box(0, 5.9, 5.3, 11.9, t, t + S.val("qt_h"), "QT socket")])
    f["pads"] = {"JP2.VBAT": (11.43, 11.43)}
    return f


def fp_reg():
    w, d = S.val("s7v8f3")
    t = HDR + PCB
    pins = {n: (1.905 + i * P, 15.24) for i, n in enumerate(["VOUT", "GND", "VIN", "SHDN"])}
    boxes = [Box(0.6, 13.97, w - 0.6, 16.51, 0, HDR, "header plastic"), Box(0, 0, w, d, HDR, t, "S7V8F3 PCB"),
             Box(2.2, 3.0, 9.2, 10.0, t, t + S.val("s7v8f3_h"), "inductor")]
    return dict(pins=pins, outline=(0, 0, w, d), boxes=boxes, colour="#1D6B33", label="S7V8F3")


def fp_row(n, names, h, what, colour, below=False):
    pins = {nm: (i * P, 0) for i, nm in enumerate(names)}
    z0, z1 = (-S.val("pin_below"), 0) if below else (0, h)
    return dict(pins=pins, outline=(-1.27, -1.27, (n - 1) * P + 1.27, 1.27),
                boxes=[Box(-1.27, -1.27, (n - 1) * P + 1.27, 1.27, z0, z1, what)], colour=colour, label=what)


def fp_swd():
    """Right-angle 1x5: pin n+1 one pitch to the left of pin n; plastic and pins run toward -y (the front)."""
    pins = {str(i + 1): (-i * P, 0) for i in range(5)}
    x0, x1 = -4 * P - 1.27, 1.27
    boxes = [Box(x0, -4.0, x1, -1.5, 0, 2.54, "SWD right-angle plastic"),
             Box(x0, -10.2, x1, -4.0, 0.9, 1.7, "SWD pins"),
             Box(x0, -24.2, x1, -10.2, 0, 2.6, "SWD Dupont housings", keepout=True)]
    return dict(pins=pins, outline=(x0, -10.2, x1, 1.27), boxes=boxes, colour="#202020", label="SWD")


FP = {"BOB": fp_bob(), "PTC": fp_ptc(), "RV": fp_res_v(), "CAP": fp_cap(), "QTL": fp_qtlead(), "MUX": fp_mux(),
      "MINI": fp_mini(), "SHTC3": fp_shtc3(), "INA": fp_ina(), "MAX": fp_max(), "REG": fp_reg(),
      "SOCKET": fp_row(8, [str(i) for i in range(1, 9)], S.val("socket_h"), "PPPC081 socket", "#202020"),
      "PINS": fp_row(8, [str(i) for i in range(1, 9)], 0, "bus pins", "#D4AF37", below=True),
      "SWD": fp_swd()}


def tf(rot, x0, y0, x, y):
    """Maker's frame (y up) -> board frame."""
    if rot == 0:
        return x0 + x, y0 + y
    if rot == 180:
        return x0 - x, y0 - y
    if rot == 90:
        return x0 - y, y0 + x
    if rot == 270:
        return x0 + y, y0 - x
    raise ValueError(rot)


def anchor(fp, pin, hole, rot):
    """Origin that puts footprint pin `pin` on `hole`."""
    hx, hy = hole_xy(hole)
    px, py = FP[fp]["pins"][pin]
    ax, ay = tf(rot, 0, 0, px, py)
    return hx - ax, hy - ay


# ------------------------------------------------------------------ placements
def place(ref, fp, pin, hole, rot, note=""):
    x0, y0 = anchor(fp, pin, hole, rot)
    return dict(ref=ref, fp=fp, rot=rot, x0=x0, y0=y0, note=note)


PORT_START = {1: 1, 2: 8, 3: 15, 4: 22}      # Clint's layout: jack pins in column e rows 1-6, 8-13, 15-20, 22-27
BUS_ROW0 = 23                                 # bus strips: f-j rows 23..30 in model.BUS order

PLACE = {"B1": [], "B2": [], "B3": [], "B4": []}
for k, s in PORT_START.items():
    PLACE["B1"].append(place(f"J1{k}", "BOB", "1", f"e{s}", 180, f"S{k} jack, mouth over the front edge"))
    PLACE["B1"].append(place(f"F{k}", "PTC", "2", f"j{s + 1}", 0, f"S{k} 3V3 PTC"))
    PLACE["B1"].append(place(f"W1{k}", "QTL", "H.SDA", f"g{s + 2}", 0, f"S{k} QT lead from mux ch{k - 1}"))
PLACE["B2"] += [place("J21", "BOB", "1", "e1", 180, "WIND jack"), place("J22", "BOB", "1", "e8", 180, "RAIN jack"),
                place("R1", "RV", "2", "j4", 0, "cups pull-up"), place("R2", "RV", "2", "j5", 0, "vane pull-up"),
                place("R3", "RV", "2", "j11", 0, "rain pull-up"), place("C1", "CAP", "1", "g4", 0, "cups filter"),
                place("C2", "CAP", "1", "g11", 0, "rain filter")]
_mux = dict(ref="U4", fp="MUX", rot=180, x0=77.0, y0=21.82, note="foam pad on empty a-e strips; channels face the centre")
PLACE["B2"].append(_mux)
PLACE["B3"] += [dict(ref="A1", fp="MINI", rot=180, x0=X(13) + MINI_X0, y0=LETTER_Y["c"] + MINI_B_Y,
                     note="soldered on its own header (plastic between); SMA over the left edge"),
                place("J3", "SWD", "1", "a12", 0, "SWD, right angle, pins toward the front"),
                place("U5", "SHTC3", "VIN", "c27", 180, "enclosure sensor"),
                place("XS1", "SOCKET", "1", f"i{BUS_ROW0}", 0, "bus socket, B3 top")]
PLACE["B4"] += [place("XP1", "PINS", "1", f"i{BUS_ROW0}", 0, "bus pins down into XS1"),
                place("U2", "INA", "H.VIN", "e10", 180, "battery INA228, pins 5-7 pulled"),
                place("U6", "MAX", "H.VIN", "e20", 180, "fuel gauge"),
                place("U7", "REG", "VOUT", "f6", 180, "3.3 V regulator")]


def pins_of(pl):
    """{model pin: (X, Y)} for a placement's pins that go into holes."""
    f = FP[pl["fp"]]
    out = {}
    for name, (x, y) in f["pins"].items():
        out[name] = tf(pl["rot"], pl["x0"], pl["y0"], x, y)
    return out


def pads_of(pl):
    f = FP[pl["fp"]]
    return {n: tf(pl["rot"], pl["x0"], pl["y0"], x, y) for n, (x, y) in f.get("pads", {}).items()}


def boxes_of(pl):
    f = FP[pl["fp"]]
    out = []
    for b in f["boxes"]:
        (xa, ya), (xb, yb) = tf(pl["rot"], pl["x0"], pl["y0"], b.x0, b.y0), tf(pl["rot"], pl["x0"], pl["y0"], b.x1, b.y1)
        out.append(Box(xa, ya, xb, yb, b.z0, b.z1, f"{pl['ref']} {b.what}", b.keepout, b.service))
    return out


def outline_of(pl):
    x0, y0, x1, y1 = FP[pl["fp"]]["outline"]
    (xa, ya), (xb, yb) = tf(pl["rot"], pl["x0"], pl["y0"], x0, y0), tf(pl["rot"], pl["x0"], pl["y0"], x1, y1)
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


# ------------------------------------------------------------------ conductors
# (kind, end1, end2, side, note). Ends: "B1:e5" (hole), ("U4", "H.VCC") (a pad or an off-stack pin).
# kind: jumper (bare or insulated link on one board), wire (insulated lead between boards, or to a pad),
# lead (a part's own lead to off-stack), cable (an off-stack cable or mating).
WIRES = []


def w(kind, a, b, side="top", note=""):
    WIRES.append((kind, a, b, side, note))


for k, s in PORT_START.items():
    for i, sig in ((1, "3V3"), (2, "SDA"), (3, "GND"), (4, "SCL")):
        w("jumper", f"B1:d{s + i}", f"B1:f{s + i}", "bottom", f"S{k} pin {i + 1} {sig} across the channel (fit before the BOB)")
w("wire", "B2:B+30", "B1:B+30", "top", "3V3 down to the B1 back + rail (22 AWG, 20 mm)")
# B2
for a, b, n in (("c2", "c3", "wind pins 2 and 3 (GND) joined"), ("d3", "f3", "wind GND across"),
                ("d4", "f4", "CUPS across"), ("d5", "f5", "VANE across"), ("d10", "f10", "rain GND across"),
                ("d11", "f11", "RAIN across")):
    w("jumper", f"B2:{a}", f"B2:{b}", "bottom", n + " (fit before the BOB)")
for a, b, n in (("j3", "B-3", "wind GND to the back - rail"), ("j10", "B-10", "rain GND to the back - rail"),
                ("j23", "B+23", "bus 3V3 to the back + rail"), ("j24", "B-24", "bus GND to the back - rail")):
    w("jumper", f"B2:{a}", f"B2:{b}", "top", n)
for a, b, n in (("h4", "h28", "CUPS to the bus"), ("h5", "h29", "VANE to the bus"), ("h11", "h30", "RAIN to the bus")):
    w("wire", f"B2:{a}", f"B2:{b}", "top", n)
for pad, h in (("VCC", "g23"), ("GND", "g24"), ("SCL", "g25"), ("SDA", "g26"), ("RST", "g27")):
    w("wire", ("U4", f"H.{pad}"), f"B2:{h}", "top", f"mux {pad} pad lead")
for i in range(8):
    r = BUS_ROW0 + i
    w("wire", f"B2:f{r}", f"B3:f{r}", "top", f"bus {model.BUS[i]} up to B3 (22 AWG, 20 mm)")
# B3 (underside links: the mini is soldered over its strips)
for a, b, n in (("e12", "g23", "mini 3V3"), ("e27", "h23", "SHTC3 VIN"), ("e8", "g24", "mini GND (B6)"),
                ("f13", "h24", "mini GND (D12)"), ("e25", "j24", "SHTC3 GND"), ("f12", "g25", "mini SCL PB15"),
                ("e24", "h25", "SHTC3 SCL"), ("f11", "g26", "mini SDA PA15"), ("e23", "h26", "SHTC3 SDA"),
                ("e6", "g27", "mini MUX_RST PB14"), ("f5", "g28", "mini CUPS PC0"), ("f9", "g29", "mini VANE PB3"),
                ("f10", "g30", "mini RAIN PB4")):
    w("wire", f"B3:{a}", f"B3:{b}", "bottom", n)
# B4 (underside links: the breakouts sit over their strips)
for a, b, n in (("g6", "g23", "S7V8F3 VOUT"), ("d10", "h23", "INA228 VIN"), ("d20", "j23", "MAX17048 VIN"),
                ("g5", "g24", "S7V8F3 GND"), ("d9", "h24", "INA228 GND"), ("d19", "j24", "MAX17048 GND"),
                ("d8", "g25", "INA228 SCL"), ("d18", "h25", "MAX17048 SCL"), ("d7", "g26", "INA228 SDA"),
                ("d17", "h26", "MAX17048 SDA")):
    w("wire", f"B4:{a}", f"B4:{b}", "bottom", n)
for pin, h, n in (("GND", "f24", "EVM GND"), ("SCL", "f25", "EVM SCL"), ("SDA", "f26", "EVM SDA"), ("SYS", "g4", "EVM SYS to S7V8F3 VIN")):
    w("lead", ("U1", pin), f"B4:{h}", "top", n)
# the battery loop: soldered end to end, no strip anywhere
w("lead", ("PG1", "L+"), ("U2", "X1.VIN+"), "top", "pack + (pigtail) to the shunt, soldered; BATP and gauge tap here")
w("lead", ("PG1", "L+"), ("U1", "BATP"), "top", "BATP sense, own wire from the pigtail tap")
w("lead", ("PG1", "L+"), ("U6", "JP2.VBAT"), "top", "gauge sense, own wire from the pigtail tap")
w("lead", ("U2", "X1.VIN-"), ("U1", "BAT"), "top", "shunt to EVM BAT (22 AWG minimum)")
w("lead", ("PG1", "L-"), ("U1", "BATN"), "top", "pack - to EVM BAT-")

CABLES = [(("BT1", "+"), ("PG1", "M+")), (("BT1", "-"), ("PG1", "M-")),
          (("PS1", "VBUS"), ("U1", "VIN1")), (("PS1", "GND"), ("U1", "PGND1")),
          (("PV1", "+"), ("U1", "VIN2")), (("PV1", "-"), ("U1", "PGND2")),
          (("A1", "ANT"), ("CX1", "P")), (("CX1", "J"), ("AE1", "RF"))]
for k in range(1, 5):
    for s in ("GND", "V+", "SDA", "SCL"):
        CABLES.append(((f"W1{k}", f"Q.{s}"), ("U4", f"CH{k - 1}.{s}")))
for k, mod in ((1, "MOD1"), (2, "MOD2"), (3, "MOD3")):
    for n in "2345":
        CABLES.append(((f"J1{k}", n), (mod, n)))
for n in "2345":
    CABLES.append((("J21", n), ("M1", n)))
for n in "34":
    CABLES.append((("J22", n), ("M2", n)))
for i in range(1, 9):
    CABLES.append((("XS1", str(i)), ("XP1", str(i))))


def placements():
    for b in BOARDS:
        for pl in PLACE[b]:
            yield b, pl


def board_of_ref():
    return {pl["ref"]: b for b, pl in placements()}
