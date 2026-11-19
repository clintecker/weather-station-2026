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
import math
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
    "RAH": ("#202020", "bus header"), "RAS": ("#202020", "SWD"),
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
    if kind == "RLY" and xa != xb and ya != yb:     # on a slant (one column over across the channel): sliced boxes
        span = math.dist((xa, ya), (xb, yb))
        ux, uy = (xb - xa) / span, (yb - ya) / span

        def sliced(l, w, z0, z1, what, n=8):
            out = []
            for k in range(n):
                s0, s1 = -l / 2 + k * l / n, -l / 2 + (k + 1) * l / n
                pa, pb = (xm + ux * s0, ym + uy * s0), (xm + ux * s1, ym + uy * s1)
                out.append(Box(min(pa[0], pb[0]) - w / 2, min(pa[1], pb[1]) - w / 2, max(pa[0], pb[0]) + w / 2,
                               max(pa[1], pb[1]) + w / 2, z0, z1, f"{ref} {what}"))
            return out
        boxes = sliced(6.3, 2.5, 0.1, 0.1 + S.val("r_lying_h"), "resistor body") + \
            sliced(span, 0.6, 0, 1.0, "resistor leads")
    elif kind == "RLY":
        boxes = [body(6.3, 2.5, 0.1, 0.1 + S.val("r_lying_h"), "resistor body"),
                 body(span, 0.6, 0, 1.0, "resistor leads")]
    elif kind == "DSTAND":
        dl, dd = S.val("do35")
        sh = S.val("diode_stand_h")
        boxes = [Box(xa - dd / 2, ya - dd / 2, xa + dd / 2, ya + dd / 2, 0.8, 0.8 + dl, f"{ref} diode body"),
                 body(span, 0.6, sh - 1.2, sh, "diode lead loop")]
    elif kind == "PTC":
        w, t, h = S.val("ptc")
        boxes = [body(w, t, 1.0, 1.0 + h, "MF-R010 body")]
    elif kind == "CAP":
        boxes = [body(3.8, 2.6, 0.5, S.val("cap_h"), "disc capacitor")]
    else:
        raise ValueError(kind)
    return placed(ref, kind, {"1": (xa, ya), "2": (xb, yb)}, boxes, note)


def bob(ref, col, note):
    """BOB-14021 + 87180 jack turned so the mouth faces the card's front edge (toward the lid), standing on a
    soldered 1x6 male header: pin i in hole a(col + i - 1), six columns, six strips. The breakout overhangs the
    front edge; the plug goes in from the front."""
    peg = S.val("bob_peg_y")
    mouth = peg + 7.88                                  # KiCad fab: pegs 8.89, mouth 16.77 from pin-1 row
    hy = S.val("bob_hdr_y")
    x0, y0 = X(col) + 13.97, LETTER_Y["a"] + hy        # rot 180: maker +y (toward the mouth) -> -Y, maker +x -> -X
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    t = HDR + PCB
    pw, ph, pl_, _l = S.val("plug_6p")
    mk = [Box(0, hy - 1.27, S.val("bob_w"), hy + 1.27, 0, HDR, "header plastic"),
          Box(0, 0, S.val("bob_w"), S.val("bob_d"), HDR, t, "BOB-14021 PCB"),
          Box(7.62 - jw / 2, mouth - jd, 7.62 + jw / 2, mouth, t, t + jh, "87180-066LF jack"),
          Box(7.62 - pw / 2, mouth, 7.62 + pw / 2, mouth + S.val("plug_len"), t + 1, t + 1 + pl_,
              "RJ11 plug (standard 6P body after Cinch 32-5996UL)", keepout=True)]
    pins = {str(i): tf(180, x0, y0, 13.97 - (i - 1) * P, hy) for i in range(1, 7)}
    return placed(ref, "BOB", pins, [tbox(180, x0, y0, b, ref) for b in mk], note, step=[("BOB", 180, x0, y0)])


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


def ra_header(ref, n, first_hole, toward, kind="RAH", note="", names=None, pulled=()):
    """Right-angle 1xn male header, pins along +X from first_hole, mating ends pointing +Y ('back') or
    -Y ('front'); `pulled` pin numbers are taken out of the plastic. Boxes: insulator, mating pins, tails below
    the card."""
    hx, hy = hole_xy(first_hole)
    names = names or [str(i + 1) for i in range(n)]
    pins = {nm: (hx + i * P, hy) for i, nm in enumerate(names) if i + 1 not in pulled}
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


BUS_ROW_END = {"B3": ("f", "f"), "B4": ("f", "f")}
for b in BOARDS:
    PLACE[b].append(ra_header(model.HEADERS[b], model.HDR_LEN[b], "j1", "back", pulled=model.PULLED.get(b, ()),
                              note="bus header, mating pins toward the backplane"
                                   + ("; pins 19-23 and 26 are B4's power pins" if b == "B4" else "")
                                   + f"; pin {model.KEY[b]} pulled out of the plastic before fitting (the slot key: "
                                     f"{b}'s own socket has a key plug in that contact; every other card keeps that pin "
                                     "and stubs on the plug)"))
    # the bus 3.3 V and both bus grounds to the front rails, on the underside; BUS_ROW_END: where a card's
    # first two bus wires leave their strips (B3 and B4 straight up from row F: rows G-I of columns 1-2 are boxed in)
    r3, r0 = BUS_ROW_END.get(b, ("i", "i"))
    w("wire", f"{b}:{r3}{bus_row('+3V3')}", f"{b}:F+1", note="bus 3.3 V supply to the front 3.3 V rail")
    w("wire", f"{b}:{r0}{bus_row('GND')}", f"{b}:F-{2 if b != 'B1' else 3}", note="bus ground to the front ground rail")
    w("wire", f"{b}:i{bus_row('GND', 1)}", f"{b}:F-20", note="second bus ground to the front ground rail")


def port(card, k, c, p, junction=None, gnd=None):
    """Sensor port k: jack J1k (J14 for k 4) on its header in row a of columns c..c+5 (contact 1 and 6 unused, each
    alone in its strip), so its 3.3 V, data, ground and clock contacts own the strips c+1..c+4 (rows b-e free). The
    four signal clamps stand in those strips (rows b-d); the series resistors cross the channel from row e to the
    bus strips of the port's data and clock lines (straight, or one column over on a slant). `p`: the port's fuse
    block, a ground strip p on the ground rail, the fuse standing from the 3.3 V rail into strip p+1 (the port's
    3.3 V) and the zener from p+1 to p; one underside wire each brings the jack's 3.3 V and ground strips to the
    block (ground to the inner column, so the two wires nest and never cross)
    `junction` (cols n, n+1): the bus strips are out of reach (under the retention bar), so the resistors stand in
    junction strips there and the jack's data and clock strips reach them by underside wires."""
    v, sd, g, sc = c + 1, c + 2, c + 3, c + 4
    n, m = bus_row(f"P{k}_SDA"), bus_row(f"P{k}_SCL")
    assert m == n + 1, (k, n, m)
    pl = PLACE[card]
    jack = f"J1{k}"
    pl.append(bob(jack, c, f"S{k} jack on its 1x6 header in column a, rows {c}-{c + 5}; mouth toward the front edge"))
    pl.append(two_pin(f"D{k}2", "DSTAND", f"b{sd}", f"b{v}", f"port S{k} data to its 3.3 V, body on the data side"))
    pl.append(two_pin(f"D{k}5", "DSTAND", f"b{g}", f"b{sc}", f"port S{k} ground to clock, band to row {sc}"))
    pl.append(two_pin(f"D{k}3", "DSTAND", f"c{g}", f"c{sd}", f"port S{k} ground to data, band to row {sd}"))
    pl.append(two_pin(f"D{k}4", "DSTAND", f"d{sc}", f"d{v}", f"port S{k} clock to its 3.3 V, body on the clock side, "
                      f"looped over rows {sd}-{g}"))
    if junction:
        ja, jb = junction
        assert (ja, jb) == (n, m)
        pl.append(two_pin(f"R{k}1", "RLY", f"e{ja}", f"f{n}", f"port S{k} data series 100, across the channel"))
        pl.append(two_pin(f"R{k}2", "RLY", f"e{jb}", f"f{m}", f"port S{k} clock series 100, across the channel"))
        w("wire", f"{card}:e{sd}", f"{card}:d{ja}", note=f"S{k} jack data (contact 3) to its series resistor R{k}1")
        w("wire", f"{card}:e{sc}", f"{card}:d{jb}", note=f"S{k} jack clock (contact 5) to its series resistor R{k}2")
    else:
        assert sd == n or sc == m, (k, c)
        pl.append(two_pin(f"R{k}1", "RLY", f"e{sd}", f"f{n}", f"port S{k} data series 100, across the channel"
                          + ("" if sd == n else ", on a slant one row over")))
        pl.append(two_pin(f"R{k}2", "RLY", f"e{sc}", f"f{m}", f"port S{k} clock series 100, across the channel"
                          + ("" if sc == m else ", on a slant one row over")))
    pl.append(two_pin(f"F{k}", "PTC", f"F+{p + 1}", f"a{p + 1}", f"port S{k} 3.3 V fuse, standing, leads formed to 7.62"))
    pl.append(two_pin(f"D{k}1", "DSTAND", f"b{p + 1}", f"b{p}", f"port S{k} 3.3 V zener, cathode band to row {p + 1}"))
    w("jumper", f"{card}:a{p}", f"{card}:F-{p}", "top", f"port S{k} block ground strip to the ground rail")
    w("wire", f"{card}:e{v}", f"{card}:e{p + 1}", note=f"S{k} jack 3.3 V (contact 2) from its fuse F{k}")
    w("wire", f"{card}:e{g}", f"{card}:{gnd or f'e{p}'}", note=f"S{k} jack ground (contact 4) to "
      + (f"the bus ground strip ({gnd})" if gnd else "its block's ground strip"))


# B1: ports S1-S3, the three jacks across the front, mouths toward the lid. S1's bus strips (columns 3-4) sit behind
# the retention bar's corner, so its jack is on the right and its series resistors stand in junction strips 3-4.
port("B1", 2, 5, 19, gnd="f2")
port("B1", 3, 11, 17, gnd="f12")
port("B1", 1, 24, 21, junction=(3, 4))
# B2: port S4, the rain jack, the wind jack, and the weather meters
port("B2", 4, 15, 21)
for name, jack_net, r_pull, cap, zen, r_ser, gnd_row, line in (
        ("cups", "CUPS_J", "R1", "C1", "D51", "R4", 4, "CUPS"),
        ("vane", "VANE_J", "R2", "C3", "D52", "R5", 7, "VANE")):
    m = bus_row(line)
    PLACE["B2"] += [two_pin(r_pull, "RLY", f"F+{m}", f"a{m}", f"{name} pull-up 10k, lying over the ground rail"),
                    two_pin(cap, "CAP", f"b{m}", f"b{gnd_row}", f"{name} filter 100 nF"),
                    two_pin(zen, "DSTAND", f"c{m}", f"c{gnd_row}", f"{name} clamp zener, band to row {m}"),
                    two_pin(r_ser, "RLY", f"e{m}", f"f{m}", f"{name} series 1k, across the channel")]
for g in (4, 7):
    w("jumper", f"B2:a{g}", f"B2:F-{g}", "top", "meter ground strip to the ground rail")
# the rain jack's rain contact (4) lands in the RAIN bus column itself: its meter parts stand in the jack's strips
J22_C = bus_row("RAIN") - 3
PLACE["B2"].append(bob("J22", J22_C, f"rain jack on its 1x6 header in column a, rows {J22_C}-{J22_C + 5}; mouth "
                                     "toward the front edge"))
_r, _g = J22_C + 3, J22_C + 2
PLACE["B2"] += [two_pin("R3", "RLY", f"d{_r + 3}", f"d{_r}", "rain pull-up 10k, lying along column d over the jack's "
                        "unused strips"),
                two_pin("C2", "CAP", f"c{_r}", f"c{_g}", "rain filter 100 nF (column c: in column b the disc would touch "
                        "the jack's header)"),
                two_pin("D53", "DSTAND", f"b{_r}", f"b{_g}", f"rain clamp zener, band to row {_r}"),
                two_pin("R6", "RLY", f"e{_r}", f"f{_r}", "rain series 1k, across the channel")]
w("jumper", f"B2:a{_r + 3}", f"B2:F+{_r + 3}", "top", "rain pull-up's 3.3 V strip to the 3.3 V rail")
w("jumper", f"B2:e{_g}", "B2:e7", "top", "rain jack ground strip to the vane meter's ground strip")
J21_C = 24
PLACE["B2"].append(bob("J21", J21_C, f"wind jack on its 1x6 header in column a, rows {J21_C}-{J21_C + 5}; mouth "
                                     "toward the front edge"))
w("jumper", f"B2:d{J21_C + 1}", f"B2:d{J21_C + 2}", "top", "wind jack's two ground strips (contacts 2 and 3) joined")
w("wire", f"B2:e{J21_C + 1}", "B2:d21", note="wind jack ground (contacts 2-3) to S4's block ground strip")
w("wire", f"B2:e{J21_C + 3}", f"B2:d{bus_row('CUPS')}", note="wind jack cups (contact 4) to the cups meter strip")
w("wire", f"B2:e{J21_C + 4}", f"B2:d{bus_row('VANE')}", note="wind jack vane (contact 5) to the vane meter strip")

# B3: CORE
PLACE["B3"].append(mini("A1", 19, "on its own header; its D pins in column C, its B pins in column H, rows 19-30; SMA past the right edge"))
PLACE["B3"].append(ra_header("J3", 5, "a12", "front", "RAS",
                             "SWD, a generic right-angle male header cut to 1x5 (the bus header stock), soldered in column a "
                             "rows 12-16, its mating pins lying flat toward the front edge: they end at card Y "
                             f"{LETTER_Y['a'] - RA_TIP:.2f}, {LETTER_Y['a'] - RA_TIP:.2f} mm short of the edge (over the "
                             "front rails), and the ST-LINK Dupont housings push on there past the edge, lid open"))
PLACE["B3"].append(breakout("U5", "SHTC3", S.val("shtc3"), ["VIN", "3V", "GND", "SCL", "SDA"], 7.62, 180, "c8",
                            [Box(20.5, 5.9, 25.4, 11.9, HDR + PCB, HDR + PCB + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 4.9, 11.9, HDR + PCB, HDR + PCB + S.val("qt_h"), "QT socket")],
                            "enclosure air sensor, top card, away from the charger"))
for a, b_, n in (("F+18", "g20", "3.3 V supply to the mini (B2) and SWD, from the front 3.3 V rail"),
                 ("a8", "F+8", "3.3 V supply to the SHTC3, from the front 3.3 V rail"),
                 ("a6", "F-6", "ground to the SHTC3, from the front ground rail"),
                 ("g12", "a19", "ground to the mini (D12)"), ("i24", "h12", "ground to the mini (B6), from the second bus ground"),
                 (f"g{bus_row('I2C_SCL')}", "a20", "I2C clock (SCL) to the mini (PB15)"),
                 ("d5", f"h{bus_row('I2C_SCL')}", "I2C clock (SCL) to the SHTC3"),
                 (f"g{bus_row('I2C_SDA')}", "e21", "I2C data (SDA) to the mini (PA15)"),
                 ("d4", f"h{bus_row('I2C_SDA')}", "I2C data (SDA) to the SHTC3"),
                 (f"g{bus_row('MUX_RST')}", "g26", "mux reset from the mini (PB14)"),
                 (f"g{bus_row('CUPS')}", "a27", "cups pulse to the mini (PC0)"),
                 (f"g{bus_row('VANE')}", "a23", "vane voltage to the mini (PB3)"),
                 (f"g{bus_row('RAIN')}", "a22", "rain pulse to the mini (PB4)"),
                 ("F+11", "b12", "SWD 3.3 V, from the front 3.3 V rail"), ("f21", "b13", "SWD debug data (PA13)"),
                 ("f22", "b14", "SWD debug clock (PA14)"), ("f23", "b15", "SWD reset (NRST)"), ("F-16", "b16", "SWD ground, from the front ground rail")):
    w("wire", f"B3:{a}", f"B3:{b_}", "bottom", n)

# B4: POWER
T_ = HDR + PCB
PLACE["B4"].append(breakout("U2", "INA", S.val("ina228"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", None, None, None, "H.ALRT"],
                            3.81, 180, "e10",
                            [Box(20.1, 5.9, 25.4, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 5.3, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(7.7, 14.6, 17.7, 18.2, T_, T_ + 6.0, "soldered battery leads at X1")],
                            "battery monitor; SJ1 (VBUS jumper) soldered closed; header pins 5-7 pulled; battery leads soldered in X1's outer holes "
                            "(X1, the green 3-way 3.5 mm terminal block, comes fitted: desolder it and wick its holes open first, its top at 12.6 would hit B2's header tails, L7; VIN- 9.2, VBUS 12.7, VIN+ 16.2; "
                            "Adafruit-INA228-PCB .brd, TERMBLOCK_1X3-3.5MM at (12.7, 16.383) R180, 1.0 drills)",
                            pads={"X1.VIN-": (9.2, 16.383), "X1.VBUS": (12.7, 16.383), "X1.VIN+": (16.2, 16.383)}))
PLACE["B4"].append(breakout("U6", "MAX", S.val("max17048"), ["H.VIN", "H.GND", "H.SCL", "H.SDA", "H.INT", "H.QST"],
                            6.35, 180, "e20",
                            [Box(14.0, 14.5, 20.0, 19.0, T_, T_ + S.val("jstph_h"), "JST PH socket (unused)"),
                             Box(5.4, 14.5, 11.4, 19.0, T_, T_ + S.val("jstph_h"), "JST PH socket (unused)"),
                             Box(20.1, 5.9, 25.4, 11.9, T_, T_ + S.val("qt_h"), "QT socket"),
                             Box(0, 5.9, 5.3, 11.9, T_, T_ + S.val("qt_h"), "QT socket")],
                            "fuel gauge; cell sense on its JP2 VBAT pad", pads={"JP2.VBAT": (11.43, 11.43)}))
# a breakout pad with no lead gets its net from a solder jumper on that breakout, closed by hand before fitting
PAD_BRIDGED = {("U2", "X1.VBUS"): ("SJ1", "the VBUS jumper on the back, above the VIN+ and VBUS pins",
                                   "VBUS to VIN+: the INA228 then reads the pack voltage (bus voltage and power, high side); "
                                   "open as shipped (low side), so VBUS would float")}
_rw, _rd = S.val("s7v8f3")
PLACE["B4"].append(breakout("U7", "REG", (_rw, _rd), ["VOUT", "GND", "VIN", "SHDN"], 1.905, 0, "f24",
                            [Box(2.2, 3.0, 9.2, 10.0, T_, T_ + S.val("s7v8f3_h"), "inductor")],
                            "3.3 V regulator; pins in the F-J strips of rows 24-27, board toward the front", pin_y=15.24))
for a, b_, n in (("h24", "F+24", "3.3 V from the regulator to the front 3.3 V rail"),
                 ("a10", "F+10", "3.3 V supply to the INA228, from the front 3.3 V rail"),
                 ("a20", "F+21", "3.3 V supply to the MAX17048, from the front 3.3 V rail"),
                 ("h25", "F-25", "ground to the regulator, from the front ground rail"),
                 ("a9", "F-9", "ground to the INA228, from the front ground rail"),
                 ("a19", "F-19", "ground to the MAX17048, from the front ground rail"),
                 ("d8", f"g{bus_row('I2C_SCL')}", "I2C clock (SCL) to the INA228"),
                 ("d18", f"h{bus_row('I2C_SCL')}", "I2C clock (SCL) to the MAX17048"),
                 ("d7", f"g{bus_row('I2C_SDA')}", "I2C data (SDA) to the INA228"),
                 ("d17", f"h{bus_row('I2C_SDA')}", "I2C data (SDA) to the MAX17048")):
    w("wire", f"B4:{a}", f"B4:{b_}", "bottom", n)
# B4's power pins (model.B4_POWER): every lead leaving B4 now goes through its header (rule L10)
w("jumper", "B4:i19", "B4:i20", "top", "the two shunt-out pins' strips joined (battery current)")
w("lead", "B4:g20", ("U2", "X1.VIN-"), "top", "shunt out (X1 VIN-) to header pins 19-20 (charger battery +), 24 AWG stranded, red with a black band")
w("jumper", "B4:i21", "B4:i22", "top", "the two junction pins' strips joined (battery current)")
w("lead", "B4:g21", ("U2", "X1.VIN+"), "top", "header pins 21-22 (battery + junction) to the shunt in (X1 VIN+), 24 AWG stranded, red with a black band")
w("lead", "B4:g23", ("U6", "JP2.VBAT"), "top", "header pin 23 (gauge sense, from R8 on the backplane) to JP2 VBAT, 24 AWG stranded")
#   pin 26 sits in the regulator's VIN strip (R26): SYS needs no wire on B4
w("lead", ("PG1", "L-"), ("U1", "BATN"), "copper", "pack - to charger battery - (J5 GND), 24 AWG stranded, black")
w("lead", ("RT1", "1"), ("U1", "TS"), "top", "thermistor to EVM J7")
w("lead", ("RT1", "2"), ("U1", "TSN"), "top", "thermistor return to EVM J7")

# ------------------------------------------------------------------ the backplane (BusBoard PAD3U padboard)
# The plated end of a PAD3U (a separate plated pad per hole, no strips): its 31 rows nearest the factory mounting
# holes become lines 0-30, each the full 38 holes. Lines run vertically (along Zb); on line i (1..18, and B4's power lines) a tinned bus
# wire on the back (copper) face is soldered at every used pad of its net and carries line i. Hole n along a line is at
# Zb = BP_Z0 + (n - 1) P. Each card's socket pins sit in one hole row. Nothing connects unless a wire does.
# Edges: the right (beyond line 30, with the two factory mounting holes), the top and the bottom are the PAD3U's own;
# only the left edge is scored, midway between lines -1 and 0. Held (cage/backplane-mount-spec.md, enclosure 4): no
# screws and no drilled holes; it lies on three support pads, the right edge in a slot in the right corner post, the
# left edge in the left wall's groove, and the four cards plugged into its sockets hold it in place (Clint, 2026-11-17).
BP_STRIPS = 30       # lines 0..30: line 30 is the plated end's last row (card pin 30 sits over it)
BP_HOLES = 38        # the PAD3U's full 38 across
BP_SCREWS = ()          # no hole is drilled: enclosure 4 has no screw posts (the cards hold the backplane)
BP_SUPPORTS = ("s20.2", "s28.16", "s24.31")   # plain pads under the board (no screw, no hole), clear of every joint
#   and bus wire on the copper face (L7)
CAGE_LEFT = S.val("cage_wall") - 2.0              # card left edge, box frame (slots 2 mm deep in the left wall)
BP_X0 = CAGE_LEFT + X(0) - P / 2                  # backplane left edge: half a pitch outside line 0 (line 1 under card row 1)
FLOOR_LIFT = 0.0                   # the printed base's floor is the cage's: everything stands on it
BP_BACK = FLOOR_LIFT + S.val("cage_plate") + S.val("bp_posts")   # backplane copper face, Yb
BP_FRONT = BP_BACK + S.val("strip_size")[2]        # component face (sockets), Yb
CARD_DY = BP_FRONT - Y_BP                          # Yb = CARD_DY + (Y_BP - Y) ... see card_to_box
PITCH = {("B4", "B2"): 6, ("B2", "B1"): 8, ("B1", "B3"): 8}   # in backplane holes (2.54 mm); B4-B2 6 again (8 was for a WAGO junction on B4, since
#   moved to the backplane; enclosure 3, as printed, has its card slots at these heights: audited 2026-11-16, sheets/audit-enc3)
SOCKET_HOLE = {"B4": 13}                           # the mux sits behind holes 1-10, below the cards
BP_Z0 = S.val("power_zone") - (SOCKET_HOLE["B4"] - 1) * P   # first backplane hole, Zb
for lo, hi in PITCH:
    SOCKET_HOLE[hi] = SOCKET_HOLE[lo] + PITCH[(lo, hi)]


def card_z(b):
    """Zb of a card's top face: its header pins (PIN_Z above the face) sit on its socket's hole row."""
    return BP_Z0 + (SOCKET_HOLE[b] - 1) * P - PIN_Z


def card_to_box(b, x, y, z):
    """Card frame (x along the columns 1->30, y from the A row toward J, z out of the top face; right-handed: the
    top face seen with the logo upright, A row toward you, columns left to right) -> box frame. The box frame (Xb, Yb,
    Zb) is LEFT-handed: Xb runs to the right as you look in from the lid, glands down (cage.to_lid, L12)."""
    return CAGE_LEFT + x, BP_FRONT + (Y_BP - y), card_z(b) + z


def box_to_card(b, xb, yb, zb):
    """The inverse of card_to_box."""
    return xb - CAGE_LEFT, Y_BP - (yb - BP_FRONT), zb - card_z(b)


# how each drawing and render looks into the box: (screen right, screen up, toward the viewer) as box-frame
# directions; L12 checks each is a true (right-handed) view of the real box, through cage.to_lid
VIEWS = {
    "lid": (((1, 0, 0), (0, 0, 1), (0, 1, 0)),
            "from the lid, glands down: drawings/backplane.svg, the cage-side.svg front view, the cage KiCad renders"),
    "left": (((0, 1, 0), (0, 0, 1), (-1, 0, 0)),
             "from the left (card-block) wall side, lid to the right: the cage-side.svg section"),
    "right": (((0, 0, 1), (0, 1, 0), (1, 0, 0)),
              "from the right (corner-post) side, lid up: cage-render-section"),
}
MESH_AXES = (0, 2, 1)     # the KiCad cage meshes: mesh (x, y, z) = box (Xb, Zb, Yb), the floor as the board top


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
    BP_PARTS.append((model.SOCKETS[b], {str(i): f"s{i}.{SOCKET_HOLE[b]}" for i in model.socket_pins(b)},
                     f"socket for {b} ({ROLE[b]}); key plug in contact {model.KEY[b]}"))
BP_PARTS.append(("XJ1", {"GND": f"s{bus_row('GND')}.11", "SCL": f"s{bus_row('I2C_SCL')}.11",
                         "SDA": f"s{bus_row('I2C_SDA')}.11"}, "charger I2C pins (lead to EVM J8)"))
MUX_HOLES = {"H.VCC": f"s{bus_row('+3V3')}.10", "H.GND": f"s{bus_row('GND')}.10", "H.SCL": f"s{bus_row('I2C_SCL')}.10",
             "H.SDA": f"s{bus_row('I2C_SDA')}.10", "H.RST": f"s{bus_row('MUX_RST')}.10"}
for pad, h in list(MUX_HOLES.items()):
    w("wire", ("U4", pad), f"BP:{h}", "copper", f"mux {pad.split('.')[-1]} header lead to its line's bus wire")
for _k in range(1, 5):          # sensor ports 1-4 = mux channels 0-3: a cut QT cable in each channel's port
    for _s, _c in (("SDA", "blue"), ("SCL", "yellow")):
        MUX_HOLES[f"CH{_k - 1}.{_s}"] = f"s{bus_row(f'P{_k}_{_s}')}.10"
        w("wire", ("U4", f"CH{_k - 1}.{_s}"), f"BP:{MUX_HOLES[f'CH{_k - 1}.{_s}']}", "copper",
          f"QT cable #4209 in mux channel {_k - 1}, pin end cut off: its {_c} {_s} into hole 10")
w("wire", f"BP:s{bus_row('GND')}.38", f"BP:s{bus_row('GND', 1)}.38", "copper",
  "the two bus ground lines joined")
# B4's power lines (model.B4_POWER) at the backplane's lower end, beside the EVM: the battery + junction is lines
# 21-22 (R7 and R8 there, so both senses tap the junction itself); the leads to the EVM and the pack are short
BP_PARTS.append(("R7", {"1": "s21.7", "2": "s24.7"}, "charger sense 100 ohm, lying on the front, junction to a lone pad"))
BP_PARTS.append(("R8", {"1": "s22.8", "2": "s23.11"}, "gauge sense 100 ohm, lying on the front (on a slant), junction to line 23"))
w("wire", "BP:s19.5", "BP:s20.5", "copper", "lines 19 and 20 joined (charger battery +, two pins)")
w("wire", "BP:s21.5", "BP:s22.5", "copper", "lines 21 and 22 joined (battery + junction, two pins)")
w("lead", ("PG1", "L+"), "BP:s21.6", "copper", "pack + (pigtail) to the junction, 24 AWG stranded, red with a black band")
w("lead", ("U1", "BAT"), "BP:s19.6", "copper", "charger battery + (J5 BATTERY) to lines 19-20, 24 AWG stranded, red with a black band")
w("lead", ("U1", "SYS"), "BP:s26.6", "copper", "charger system output (J3 SYS) to line 26 (B4 pin 26, the regulator in), 24 AWG stranded, red with a black band")
#   SYS's return: its own lead from J3 GND to the bus ground (line 12, the nearer ground line to line 26; hole 11, just
#   above the mux), so the regulator's load and the LoRa TX peaks do not return through the I2C lead's J8 pin 1
GND_LEAD = "BP:s12.11"
w("lead", ("U1", "SYSN"), GND_LEAD, "copper", "charger system ground (J3 GND) to line 12 (the bus ground, SYS's return), 24 AWG stranded, black")
w("lead", ("R7", "2"), ("U1", "BATP"), "copper", "charger battery sense (J5 SNS_BATP) from R7's free leg, 24 AWG stranded, white with a red band")
BP_BUS = []          # (line, [holes the tinned bus wire is soldered at]): the used pads of the line's own net
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
# a socket contact whose card pin is not on the line's net (model.pin_net) is an isolated pad: no bus wire there
BP_ISOLATED = {(i, SOCKET_HOLE[b]) for b in BOARDS for i in model.socket_pins(b)
               if i not in model.hdr_pins(b) or model.pin_net(b, i) is None or model.pin_net(b, i) != model.line_net(i)}
BP_KEYS = {b: (model.KEY[b], SOCKET_HOLE[b]) for b in BOARDS}   # (line, hole) of each socket's key plug
for _i in range(1, BP_STRIPS + 1):
    _on = sorted(n for n in _used.get(_i, ()) if (_i, n) not in BP_ISOLATED)
    if model.line_net(_i) and (_i <= 18 or len(_on) > 1):   # a lone pad (R7's free leg on line 24) takes no bus wire
        BP_BUS.append((_i, _on))
MUX_BOX = (strip_x(2) - 1.27, BP_Z0 + 0.5 * P, strip_x(2) - 1.27 + S.val("mux_w"),
           BP_Z0 + 0.5 * P + S.val("mux_d"))   # on foam on the copper side behind holes 1.5-9.5: Xb and Zb extents
# the PAD3U's factory mounting holes (pad3u_mount, measured from Clint's scan): beyond line 30, on holes 2 and 37
_MD, _MRING, _MOFF, _MSPAN = S.val("pad3u_mount")
BP_FACTORY = {"lower right": (strip_x(BP_STRIPS) + _MOFF, BP_Z0 + P),
              "upper right": (strip_x(BP_STRIPS) + _MOFF, BP_Z0 + P + _MSPAN)}
BP_FACTORY_SCREW = None   # both factory holes unused since enclosure 4 (no screw posts)
# how each edge of the piece is made (build/BACKPLANE.md section 1): "cut" = scored midway between two hole rows
# (pad_margin from the hole centres); "factory" = the PAD3U's own edge (pad3u_edges and pad3u_plated_edge)
BP_EDGES = {"left": "cut", "right": "factory", "bottom": "factory", "top": "factory"}


def bp_sheet_outline():
    """The piece's outline (Xb0, Zb0, Xb1, Zb1) as the build sheet makes it: each edge cut or the PAD3U's own."""
    side, _far, _w = S.val("pad3u_edges")
    fac = {"left": None, "right": _MOFF + S.val("pad3u_plated_edge"), "bottom": side, "top": side}
    m = {k: (S.val("pad_margin") if v == "cut" else fac[k]) for k, v in BP_EDGES.items()}
    return (strip_x(0) - m["left"], BP_Z0 - m["bottom"], strip_x(BP_STRIPS) + m["right"],
            BP_Z0 + (BP_HOLES - 1) * P + m["top"])


_side = S.val("pad3u_edges")[0]
BP_OUTLINE = (BP_X0, BP_Z0 - _side, strip_x(BP_STRIPS) + _MOFF + S.val("pad3u_plated_edge"),
              BP_Z0 + (BP_HOLES - 1) * P + _side)   # Xb0, Zb0, Xb1, Zb1
BP_USED = {(i, n) for i, ns in _used.items() for n in ns} | {tuple(int(v) for v in h[1:].split(".")) for _r, _p, _n in BP_PARTS
                                                          for h in _p.values()}   # (line, hole) with anything in it

# ------------------------------------------------------------------ cables and matings (off the cards)
CABLES = [(("BT1", "+"), ("PG1", "M+")), (("BT1", "-"), ("PG1", "M-")),
          (("PS1", "VBUS"), ("U1", "VIN1")), (("PS1", "GND"), ("U1", "PGND1")),
          (("PV1", "+"), ("U1", "VIN2")), (("PV1", "-"), ("U1", "PGND2")),
          (("A1", "ANT"), ("AD1", "P")), (("AD1", "J"), ("CX1", "P")), (("CX1", "J"), ("AE1", "RF")),
          (("U1", "J8.1"), ("XJ1", "GND")), (("U1", "J8.2"), ("XJ1", "SCL")), (("U1", "J8.3"), ("XJ1", "SDA"))]
for k, mod in ((1, "MOD1"), (2, "MOD2"), (3, "MOD3")):
    for n in "2345":
        CABLES.append(((f"J1{k}", n), (mod, n)))
for n in "2345":
    CABLES.append((("J21", n), ("M1", n)))
for n in "34":
    CABLES.append((("J22", n), ("M2", n)))
for b in BOARDS:
    for i in model.hdr_pins(b):
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
