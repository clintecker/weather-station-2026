"""CadQuery models for the Session P sheets (the pod boards), drawn as supplied, from the repo's own numbers.

Sources (read-only):
  - the Perma-Proto Quarter #1608: layout/permaproto.py (holes, strips, outline from Adafruit's .brd via sources.py) and
    the silkscreen positions below (Adafruit-Perma-Proto-PCB "adafruit permaproto quarterbreadboard.brd", tPlace layer 21:
    row letters turned 90 degrees beside both long edges, column numbers upright; layer 112 red lines and '+' signs, 113
    blue lines and their '-' ticks). The board prints nothing on its copper side.
  - the four Adafruit breakouts: outline, header pads, pad names from sources.py; every other factory-fitted part (the two
    STEMMA QT sockets, the sensor or EEPROM chip, the regulator, level shifter, resistor packs, capacitors, LED, mounting
    holes) at the element positions read from each board's .brd (BRD below, parsed once from the files sources.py cites).
    Package sizes are the packages' nominal outlines (0603, 0805, SOT-23-5, SOT-363, SOIC-8, JST SH 4-pin horizontal).
  - the BOB-14021 kit: the TX sheets' board STEP and part sizes (hardware/tx-stack-r1/sheets/session3/scenes3.py
    bob_parts, copied here because importing scenes3 runs the TX card's own layout); the STEP stays in the TX tree.
  - JP1 (Sullins PRPC002SAAN-RC + SPC02SYAN), R1 (Yageo MFR-25), wires: pods.py and sources.py sizes.

Frames: every function builds its part in its own maker frame with the board's underside at z = 0 (a breakout: lower-left
corner at the origin, header row at y = 2.54, the face with the chips up). scenes_p.py places them.
"""
import math
import sys
from pathlib import Path

import cadquery as cq
import numpy as np

HERE = Path(__file__).resolve().parent
PODS = HERE.parent
REPO = PODS.parent.parent
for p in (PODS, PODS / "layout", REPO / "hardware" / "tx-stack-r1" / "sheets" / "session1" / "v2"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import sources as S            # noqa: E402  hardware/pods-r1/sources.py
import permaproto as PPM       # noqa: E402
import models as TXM           # noqa: E402  TX sheets models (read-only): box(), colours, _rod()

P = 2.54
T = S.val("permaproto_q_t")    # Perma-Proto thickness (1.6, TBD)
PCB = S.val("breakout_t")
HDR = S.val("hdr_plastic")
H_SHORT, H_LONG = 3.0, 6.0     # generic 0.1 in male header: pin above / below the plastic (TX sheets' H_SHORT, H_LONG)

# ------------------------------------------------------------------ colours
PP_BOARD = "#EFE7CF"            # Perma-Proto: cream solder mask [as remembered from Adafruit's photos; Clint to confirm]
PP_SILK = "#222222"
RAIL_RED = "#D7262E"
RAIL_BLUE = "#2D6FD0"
GOLD = TXM.GOLD
ADA_BOARD = "#25283A"           # Adafruit's black PCB (the TX sheets' ADA_BOARD)
ADA_SILK = "#F4F4F4"
JST = "#E9E6DC"                 # STEMMA QT socket, natural (the TX sheets' colour)
CHIP = "#2A2A2A"
TIN = TXM.TIN
PIN = "#D8B24A"
HDR_BLACK = "#1E1E1E"
CAP_TAN = "#B8996A"
LED_G = "#BFE3C0"
SILVER = "#C8CCD0"
PTFE = "#FAFAF7"
INS = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "green": "#2E9A48"}
COPPER = "#C87533"
JACKET = "#4A4D52"
PLUG = "#DCE6EA"


def box(x0, y0, z0, x1, y1, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return TXM.box(x0, y0, z0, x1, y1, z1)


def zcyl(r, z0, z1, x, y):
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))


def rounded_plate(w, h, r, t, z0=0.0):
    return cq.Workplane("XY").rect(w, h, centered=False).extrude(t).edges("|Z").fillet(r).translate((0, 0, z0))


def rod(pts, r):
    return TXM._rod(pts, r)


def simplify(pts):
    out = [tuple(map(float, pts[0]))]
    for p in pts[1:]:
        p = tuple(map(float, p))
        if len(out) >= 2:
            a, b = np.array(out[-2]), np.array(out[-1])
            d1, d2 = b - a, np.array(p) - b
            if np.linalg.norm(np.cross(d1, d2)) < 1e-6 and d1 @ d2 > 0:
                out[-1] = p
                continue
        if np.linalg.norm(np.array(p) - np.array(out[-1])) > 1e-6:
            out.append(p)
    return out


def tube(pts, r):
    """A round tube through 3D points with half-ball joints (the TX sheets' wire tubes)."""
    pts = simplify(pts)
    sol = []
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = np.array(a), np.array(b)
        L = np.linalg.norm(b - a)
        sol.append(cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*((b - a) / L))))
    for p in pts[1:-1]:
        sol.append(cq.Solid.makeSphere(r, cq.Vector(*p), angleDegrees1=-90, angleDegrees2=90))
    s = sol[0]
    for x in sol[1:]:
        s = s.fuse(x)
    return s.clean()


def fillet_cone(x, y, z, up=True, r0=0.95, r1=0.38, h=0.6):
    """A solder joint round a pin or lead on a pad: a cone from the pad up (or down) the pin."""
    return cq.Solid.makeCone(r0, r1, h, cq.Vector(x, y, z), cq.Vector(0, 0, 1 if up else -1))


# ================================================================== Perma-Proto Quarter #1608
W, H = S.val("permaproto_q")
CX, CY = W / 2, H / 2          # the .brd's origin (board centre) in the lower-left frame
DRILL, PAD = S.val("permaproto_q_hole")
MOUNT = [(x, y) for x, y, _d in PPM.OUTLINE["mounting_holes"]]
MOUNT_D = PPM.OUTLINE["mounting_holes"][0][2]
COLS = range(1, 16)


def hxy(hole):
    return PPM.HOLES[hole]


# silkscreen (file coordinates, .brd tPlace / 112 / 113), shifted to the lower-left frame
SILK_LETTER_X = (-19.304, 20.574)                # baseline x of the turned letters (they read bottom to top)
SILK_NUM_Y = (15.24, -16.256)                    # baseline y of the column numbers
SILK_RED = (-23.368, 17.272)                     # red lines (beside the + rails), x -17.78..17.78
SILK_BLUE = (-17.272, 23.368)                    # blue lines (beside the - rails)
SILK_TICKS = [(-19.812, 22.606, 23.876), (20.066, 22.606, 23.876), (20.066, -18.034, -16.764),
              (-19.812, -18.034, -16.764)]       # short blue ticks at the blue lines' ends (x, y0, y1)
SILK_PLUS = [(-20.828, -24.638), (19.05, -24.638), (19.05, 16.002), (-20.828, 16.002)]


def permaproto(scene, part="pp", decals=True, copper_top=True, copper_bottom=True, strips=True, prefix=None):
    """The Perma-Proto Quarter in the board frame (layout/permaproto.py), underside z = 0, top z = T: the board, the plated
    pads on both faces, the copper strips on the underside (each column's A-E and F-J joined, each rail one trace), and the
    top silkscreen as decals. Adds parts `part`, `part`_cuT and `part`_cuB to the scene."""
    pre = prefix or part
    pts = list(PPM.HOLES.values())
    b = rounded_plate(W, H, S.val("permaproto_q_corner_r"), T)
    b = b.faces(">Z").workplane(origin=(0, 0, T)).pushPoints(pts).hole(DRILL)
    b = b.faces(">Z").workplane(origin=(0, 0, T)).pushPoints(MOUNT).hole(MOUNT_D)
    scene.add(part, b, PP_BOARD)
    ct = 0.05
    if copper_top:
        top = cq.Workplane("XY").workplane(offset=T).pushPoints(pts).circle(PAD / 2).circle(DRILL / 2).extrude(ct)
        scene.add(f"{pre}_cuT", top, GOLD, 0.0)
    if copper_bottom:
        bot = cq.Workplane("XY").workplane(offset=-ct).pushPoints(pts).circle(PAD / 2).extrude(ct)
        if strips:
            sw = 0.9
            for c in COLS:
                for lo, hi in (("A", "E"), ("F", "J")):
                    (x, y0), (_x, y1) = hxy(f"{lo}{c}"), hxy(f"{hi}{c}")
                    bot = bot.union(box(x - sw / 2, y0, -ct, x + sw / 2, y1, 0))
            for r in ("bot+", "bot-", "top+", "top-"):
                (x0, y), (x1, _y) = hxy(f"{r}1"), hxy(f"{r}15")
                bot = bot.union(box(x0, y - sw / 2, -ct, x1, y + sw / 2, 0))
        bot = bot.faces("<Z").workplane(origin=(0, 0, -ct)).pushPoints(pts).hole(DRILL)
        scene.add(f"{pre}_cuB", bot, GOLD, 0.0)
    if decals:
        silk(scene, part)
    return b


def silk(scene, part):
    z = T + 0.001
    sz = 1.27 * 1.3
    for i, L in enumerate("ABCDEFGHIJ"):
        y = hxy(f"{L}1")[1]
        for xb in SILK_LETTER_X:
            # turned 90 degrees: the text runs up (+y), the glyphs stand toward -x from the baseline
            scene.text(part, L, (xb + CX, y, z), (0, 1, 0), (-1, 0, 0), sz, colour=PP_SILK, font="Helvetica-Bold")
    for c in COLS:
        x = hxy(f"A{c}")[0]
        for yb in SILK_NUM_Y:
            scene.text(part, str(c), (x, yb + CY, z), (1, 0, 0), (0, 1, 0), 1.016 * 1.3, colour=PP_SILK,
                       font="Helvetica-Bold")
    w = 0.4064

    def hline(y, col):
        # short pieces: the render keeps a decal piece only where its middle is visible (parts stand over these lines)
        xs = np.linspace(-17.78 + CX, 17.78 + CX, 71)
        scene.lines(part, [((a, y + CY, z), (b, y + CY, z)) for a, b in zip(xs[:-1], xs[1:])], colour=col, width_mm=w)
    for y in SILK_RED:
        hline(y, RAIL_RED)
    for y in SILK_BLUE:
        hline(y, RAIL_BLUE)
    for x, y0, y1 in SILK_TICKS:
        scene.lines(part, [((x + CX, y0 + CY, z), (x + CX, y1 + CY, z))], colour=RAIL_BLUE, width_mm=w)
    for x, y in SILK_PLUS:
        scene.text(part, "+", (x + CX + 0.9, y + CY, z), (1, 0, 0), (0, 1, 0), 2.54 * 1.1, colour=RAIL_RED,
                   font="Helvetica-Bold")


# ================================================================== Adafruit breakouts
# Element positions from each .brd (top side only; maker frame = the board's lower-left corner; the 24LC32's file origin
# is at (-4.953, -4.5085) and is shifted here). (package, x, y, rotation)
BRD = {
    "sht45": [("0805", 7.62, 6.096, 0), ("SOT23-5", 7.874, 9.525, 0), ("0805", 8.001, 12.827, 0),
              ("0603C", 11.049, 5.588, 0), ("RPACK", 17.526, 11.43, 180), ("SOT363", 17.0815, 6.096, 90),
              ("LED", 3.556, 12.573, 90), ("0603", 5.588, 12.446, 270), ("SHT4X", 12.7, 8.89, 180)],
    "ltr390": [("0805", 7.874, 5.715, 0), ("SOT23-5", 8.128, 8.763, 0), ("0805", 8.128, 12.192, 0),
               ("0603C", 11.811, 5.715, 0), ("RPACK", 17.145, 11.43, 180), ("SOT363", 16.891, 7.874, 90),
               ("LED", 3.556, 12.573, 90), ("0603", 5.588, 12.446, 270), ("LTR390", 12.7, 8.89, 0),
               ("0603", 17.145, 5.588, 0)],
    "bmp581": [("0603", 12.192, 13.462, 180), ("SOD323", 16.764, 5.334, 180), ("0603", 12.192, 11.938, 180),
               ("BMP581", 12.7, 8.89, 180), ("0805", 6.731, 5.715, 0), ("SOT23-5", 8.128, 8.763, 0),
               ("0805", 8.128, 12.192, 0), ("0603C", 10.541, 8.89, 90), ("RPACK", 17.145, 11.43, 180),
               ("SOT363", 16.891, 7.747, 90), ("LED", 3.556, 12.573, 90), ("0603", 5.588, 12.446, 270)],
    "eeprom_24lc32": [("0805", 7.62, 4.953, 0), ("SOT23-5", 8.128, 7.874, 0), ("0805", 18.288, 12.192, 0),
                      ("RPACK", 17.4625, 9.652, 180), ("SOT363", 16.891, 6.096, 90), ("LED", 3.556, 12.573, 90),
                      ("RPACK", 8.1915, 11.303, 180), ("SOIC8", 12.7, 8.89, 180), ("0603C", 5.5245, 12.3825, 270)],
}
# the two STEMMA QT sockets (JST SH 4-pin horizontal): centre x, y; mouth +x (right edge) or -x (left edge)
QT = {"sht45": ((22.225, 8.89), (3.175, 8.89)), "ltr390": ((22.733, 8.89), (2.667, 8.89)),
      "bmp581": ((22.225, 8.89), (3.175, 8.89)), "eeprom_24lc32": ((22.86, 8.89), (2.54, 8.89))}
HOLES25 = {"sht45": [(2.54, 2.54), (22.86, 2.54), (2.54, 15.24), (22.86, 15.24)],
           "ltr390": [(2.54, 2.54), (22.86, 2.54), (2.54, 15.24), (22.86, 15.24)],
           "bmp581": [(2.54, 15.24), (22.86, 15.24)],
           "eeprom_24lc32": [(2.54, 2.54), (22.86, 2.54), (2.54, 15.24), (22.86, 15.24)]}
EXTRA_PADS = {"eeprom_24lc32": [(12.7 + d, 15.24) for d in (-3.81, -1.27, 1.27, 3.81)]}    # JP3, 1x4, no pins
# pad names as printed beside each pad (the .brd's tPlace texts / PLABEL elements): below the pad or above it
PAD_TEXT = {"sht45": ["VIN", "3Vo", "GND", "SCL", "SDA"],
            "ltr390": ["VIN", "3Vo", "GND", "SCL", "SDA", "INT"],
            "bmp581": ["VIN", "3Vo", "GND", "SCK", "SDO", "SDI", "CS", "INT"],
            "eeprom_24lc32": ["VIN", "3V", "GND", "SCL", "SDA", "WP"]}
PAD_ABOVE = {"sht45": (0, 1, 0, 1, 0), "ltr390": (0, 1, 0, 1, 0, 1), "bmp581": (0, 1, 0, 1, 0, 1, 0, 1),
             "eeprom_24lc32": (0, 0, 0, 1, 0, 1)}
TITLE = {"ltr390": [("LTR390", 13.208, 16.383, 1.4732), ("ALS+UV Sensor", 14.097, 14.605, 1.016)],
         "eeprom_24lc32": [("I2C MEMORY", 14.605, 16.891, 0.8128)]}
PKG = {   # length (x at rotation 0), width (y), height, colour
    "0603": (1.6, 0.8, 0.45, CHIP), "0603C": (1.6, 0.8, 0.8, CAP_TAN), "0805": (2.0, 1.25, 0.85, CAP_TAN),
    "SOT23-5": (2.9, 1.6, 1.1, CHIP), "SOT363": (2.0, 1.25, 0.95, CHIP), "RPACK": (3.2, 1.6, 0.5, CHIP),
    "SOD323": (1.7, 1.25, 0.9, CHIP), "LED": (1.6, 0.8, 0.6, LED_G), "SOIC8": (4.9, 3.9, 1.5, CHIP),
    "SHT4X": (1.5, 1.5, 0.5, CHIP), "LTR390": (2.0, 2.0, 0.65, CHIP), "BMP581": (2.0, 2.0, 0.75, SILVER),
}


def _pkg_box(pkg, x, y, rot, z0):
    L, Wd, Hh, _c = PKG[pkg]
    if rot in (90, 270):
        L, Wd = Wd, L
    return box(x - L / 2, y - Wd / 2, z0, x + L / 2, y + Wd / 2, z0 + Hh)


def hdr_pads(key):
    hx1, hy, pitch = S.val(key + "_hdr")
    return [(hx1 + i * pitch, hy) for i in range(len(S.val(key + "_pins")))]


def breakout(key, scene=None, part=None, fitted=None, header=False, soldered=True, hdrop=0.0, trimmed_to=None,
             hdr_n=None):
    """An Adafruit breakout in its maker frame (underside z = 0, chips up): [(name, shape, colour, weight)] and
    {anchor: (point, on-part name or None)}.
    header: draw its male header (`hdr_n` pins from pad 1; default `fitted` or every pad) with the plastic under the board
    (dropped `hdrop` below it when shown loose), short ends up through the pads (soldered: a joint on each), long ends down.
    trimmed_to: the long ends' bottom z (else the plastic's bottom less H_LONG)."""
    w, d = S.val(key)
    t = PCB
    pads = hdr_pads(key)
    n = hdr_n or fitted or len(pads)
    out, anc = [], {}
    b = rounded_plate(w, d, 2.54, t)
    holes = [p for p in pads] + EXTRA_PADS.get(key, [])
    b = b.faces(">Z").workplane(origin=(0, 0, t)).pushPoints(holes).hole(1.0)
    b = b.faces(">Z").workplane(origin=(0, 0, t)).pushPoints(HOLES25[key]).hole(2.5)
    out.append(("board", b.val(), ADA_BOARD, 1.0))
    cu = []
    for z in (t, -0.05):
        w_ = cq.Workplane("XY").workplane(offset=z)
        cu.append(w_.pushPoints(holes).circle(0.889).circle(0.5).extrude(0.05).val())
        cu.append(cq.Workplane("XY").workplane(offset=z).pushPoints(HOLES25[key]).circle(1.75).circle(1.25)
                  .extrude(0.05).val())
    out.append(("pads", cq.Compound.makeCompound(cu), GOLD, 0.2))
    # chips and passives as fitted at the factory
    chips, tan, leds, leads = [], [], [], []
    for pkg, x, y, rot in BRD[key]:
        bx = _pkg_box(pkg, x, y, rot, t).val()
        if pkg == "SHT4X":
            chips.append(bx)
            out.append(("ptfe", box(x - 1.1, y - 1.1, t + 0.5, x + 1.1, y + 1.1, t + 1.2).edges("|Z").fillet(0.4).val(),
                        PTFE, 0.6))
            anc["sensor"] = ((x, y, t + 1.2), "ptfe")
        elif pkg == "BMP581":
            out.append(("lid", bx, SILVER, 0.6))
            anc["sensor"] = ((x + 0.5, y + 0.5, t + 0.75), "lid")
        elif pkg == "LTR390":
            chips.append(bx)
            out.append(("window", box(x - 0.6, y - 0.6, t + 0.65, x + 0.6, y + 0.6, t + 0.7).val(), "#8FB3C9", 0.3))
            anc["sensor"] = ((x + 0.75, y + 0.75, t + 0.65), "chips")
        elif pkg == "SOIC8":
            chips.append(bx)
            for i in range(4):
                xx = x - 1.905 + i * 1.27
                for sy in (-1, 1):
                    leads.append(box(xx - 0.2, y + sy * 1.95, t, xx + 0.2, y + sy * 3.0, t + 0.25).val())
            anc["chip"] = ((x + 1.0, y, t + 1.5), "chips")
        else:
            {CAP_TAN: tan, CHIP: chips, LED_G: leds}[PKG[pkg][3]].append(bx)
    out.append(("chips", cq.Compound.makeCompound(chips), CHIP, 0.5))
    for nm, lst, col, wt in (("caps", tan, CAP_TAN, 0.4), ("led", leds, LED_G, 0.3), ("leads", leads, TIN, 0.2)):
        if lst:
            out.append((nm, cq.Compound.makeCompound(lst), col, wt))
    # the two STEMMA QT sockets: JST SH 4-pin horizontal, 6.0 wide, 4.25 deep, 2.95 tall, mouth off the board edge
    qt = []
    for (x, y), sgn in zip(QT[key], (1, -1)):
        j = box(x - 2.125, y - 3.0, t, x + 2.125, y + 3.0, t + 2.95)
        mouth_x = x + sgn * 2.125
        j = j.cut(box(min(mouth_x, mouth_x - sgn * 3.2), y - 2.0, t + 0.6, max(mouth_x, mouth_x - sgn * 3.2), y + 2.0,
                      t + 2.35))
        qt.append(j.val())
        anc[f"qt{'R' if sgn > 0 else 'L'}"] = ((x - sgn * 1.0, y, t + 2.95), "qt")
    out.append(("qt", cq.Compound.makeCompound(qt), JST, 0.8))
    # header pins
    if header:
        zt = -hdrop
        hp = pads[:n]
        plast = box(hp[0][0] - 1.27, hp[0][1] - 1.27, zt - HDR, hp[-1][0] + 1.27, hp[0][1] + 1.27, zt)
        bot = trimmed_to if trimmed_to is not None else zt - HDR - H_LONG
        top = zt + H_SHORT
        pins = [box(x - 0.32, y - 0.32, bot, x + 0.32, y + 0.32, top).val() for x, y in hp]
        out.append(("hdr", plast.val(), HDR_BLACK, 0.6))
        out.append(("hpins", cq.Compound.makeCompound(pins), PIN, 0.4))
        anc["hdr"] = (((hp[0][0] + hp[-1][0]) / 2, hp[0][1] - 1.27, zt - HDR / 2), "hdr")
        anc["hpin_lo"] = ((hp[0][0], hp[0][1] - 0.32, bot + 0.6), "hpins")
        if soldered and not hdrop:
            fil = [fillet_cone(x, y, t + 0.05, True, 0.85, 0.38, 0.6) for x, y in hp]
            out.append(("hfil", cq.Compound.makeCompound(fil), TIN, 0.4))
            anc["hfil"] = ((hp[0][0], hp[0][1] - 0.62, t + 0.25), ("hfil", "hpins"))
    for i, (x, y) in enumerate(pads):
        anc[f"pad{i + 1}"] = ((x, y, t + 0.05), None)
    anc["board"] = ((w / 2, d - 3.0, t), "board")
    if scene is not None and part is not None:
        breakout_silk(scene, key, part)
    return out, anc


def breakout_silk(scene, key, part, xf=None):
    """The pad names (and board title) printed on the breakout's top face, as decals on `part` (the board)."""
    t = PCB + 0.001
    for (x, y), nm, up in zip(hdr_pads(key), PAD_TEXT[key], PAD_ABOVE[key]):
        yb = 4.191 if up else 0.889
        scene.text(part, nm, (x, yb, t), (1, 0, 0), (0, 1, 0), 1.016 * 1.25, colour=ADA_SILK, font="Helvetica-Bold")
    for s, x, y, sz in TITLE.get(key, []):
        scene.text(part, s, (x, y, t), (1, 0, 0), (0, 1, 0), sz * 1.2, colour=ADA_SILK, font="Helvetica-Bold",
                   anchor="middle")


def loose_header(n, scene=None, part="lh"):
    """A loose 1xn male header strip as supplied: plastic 2.5 tall (z 0..HDR), pins H_SHORT above and H_LONG below, pin 1
    at x = 0, running +x."""
    plast = box(-1.27, -1.27, 0, (n - 1) * P + 1.27, 1.27, HDR)
    pins = [box(i * P - 0.32, -0.32, -H_LONG, i * P + 0.32, 0.32, HDR + H_SHORT).val() for i in range(n)]
    return plast, cq.Compound.makeCompound(pins)


# ================================================================== BOB-14021 + 87180-066LF + 1x6 header
# Copied from hardware/tx-stack-r1/sheets/session3/scenes3.py (bob_step / bob_parts), read-only source.
TX = REPO / "hardware" / "tx-stack-r1"
BOB_STEP = TX / "render" / "models" / "BOB" / "bob14021_board.step"
PCB_STEP = 1.51
BOB_RED = "#B5121B"
JACK = "#33363B"
BOB_TAB = (15.24, 21.59)
JACK_PINS = [(5.71, 6.35), (8.25, 6.35), (10.79, 6.35), (4.45, 8.89), (6.99, 8.89), (9.52, 8.89)]
JACK_PEGS = [(2.54, 15.24), (12.7, 15.24)]
HY = S.val("bob_hdr_y")
HPINS = [(13.97 - (i - 1) * P, HY) for i in range(1, 7)]
_bob = []


def bob_step():
    if not _bob:
        shp = cq.importers.importStep(str(BOB_STEP))
        sols = [x for v in shp.vals() for x in v.Solids()]
        board = max(sols, key=lambda so: so.Volume())
        _bob.extend([board, [so for so in sols if so is not board]])
    return _bob


def bob_parts(tab=False, jack=True, jlift=0.0, header=True, hdrop=0.0, trimmed=False, soldered=True, flush=None):
    """One BOB-14021 build in its maker frame (board bottom at z 0); see scenes3.bob_parts. trimmed: the header's long ends
    cut 1 mm below the Perma-Proto (fitted)."""
    if flush is None:
        flush = soldered and not jlift
    board, cu = bob_step()
    parts = [("pcb", board, BOB_RED, 1.0), ("cu", cq.Compound.makeCompound(cu), GOLD, 0.3)]
    anc = {}
    bd = S.val("bob_d")
    if tab:
        parts.append(("tab", box(BOB_TAB[0] + 0.51, 0, 0, BOB_TAB[1], bd, PCB_STEP).val(), BOB_RED, 1.0))
        parts.append(("score", box(BOB_TAB[0], 0, 0.45, BOB_TAB[0] + 0.51, bd, PCB_STEP - 0.45).val(), BOB_RED, 0.3))
        anc["tab"] = (((BOB_TAB[0] + BOB_TAB[1]) / 2 + 0.6, 12.0, PCB_STEP), "tab")
        anc["score"] = ((BOB_TAB[0] + 0.25, 0.0, PCB_STEP / 2), "score")
        anc["score_top"] = ((BOB_TAB[0] + 0.25, 6.0, PCB_STEP - 0.45), "score")
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    mouth = S.val("bob_peg_y") + 7.88
    pw, ph = S.val("plug_6p")[0], S.val("plug_6p")[1]
    if jack:
        z0 = PCB_STEP + jlift
        j = box(7.62 - jw / 2, mouth - jd, z0, 7.62 + jw / 2, mouth, z0 + jh)
        j = j.cut(box(7.62 - pw / 2, mouth - 9.0, z0 + 1.0, 7.62 + pw / 2, mouth + 1, z0 + 1.0 + ph))
        parts.append(("jack", j.val(), JACK, 1.0))
        tail = (0.6 if flush else 3.0)
        pins = [zcyl(0.3, z0 - PCB_STEP - tail, z0, x, y) for x, y in JACK_PINS]
        pegs = [zcyl(1.4, z0 - PCB_STEP - 1.0, z0, x, y) for x, y in JACK_PEGS]
        parts.append(("jpins", cq.Compound.makeCompound(pins), PIN, 0.4))
        parts.append(("jpegs", cq.Compound.makeCompound(pegs), JACK, 0.6))
        if soldered and not jlift:
            fil = [cq.Solid.makeCone(0.95, 0.32, 0.55, cq.Vector(x, y, 0.0), cq.Vector(0, 0, -1)) for x, y in JACK_PINS]
            parts.append(("jfil", cq.Compound.makeCompound(fil), TIN, 0.4))
            anc["jfil"] = ((JACK_PINS[1][0] + 0.62, JACK_PINS[1][1], -0.2), ("jfil", "jpins"))
        anc["jack"] = ((7.62, mouth - jd / 2, z0 + jh), "jack")
        anc["mouth"] = ((7.62, mouth, z0 + 1.0 + ph + 1.5), "jack")
        anc["jpin"] = ((JACK_PINS[1][0], JACK_PINS[1][1], z0 - PCB_STEP - tail), "jpins")
        anc["peg"] = ((JACK_PEGS[0][0], JACK_PEGS[0][1], z0 - PCB_STEP - 1.0), "jpegs")
    if header:
        zt = -hdrop
        plast = box(0, HY - 1.27, zt - HDR, S.val("bob_w"), HY + 1.27, zt).val()
        bot = (-HDR - T - 1.0) if trimmed else (zt - HDR - H_LONG)
        top = zt + H_SHORT
        hp = [box(x - 0.32, y - 0.32, bot, x + 0.32, y + 0.32, top).val() for x, y in HPINS]
        parts.append(("hdr", plast, HDR_BLACK, 0.6))
        parts.append(("hpins", cq.Compound.makeCompound(hp), PIN, 0.4))
        if soldered and not hdrop:
            fil = [cq.Solid.makeCone(0.95, 0.38, 0.6, cq.Vector(x, y, PCB_STEP)) for x, y in HPINS]
            parts.append(("hfil", cq.Compound.makeCompound(fil), TIN, 0.4))
            anc["hfil"] = ((HPINS[0][0], HPINS[0][1] - 0.62, PCB_STEP + 0.2), ("hfil", "hpins"))
        anc["hdr"] = ((7.62, HY - 1.27, zt - HDR / 2), "hdr")
        anc["hdr_bot"] = ((HPINS[2][0] - 1.27, HY + 0.8, zt - HDR), "hdr")
        anc["hpin_lo"] = ((HPINS[0][0], HPINS[0][1], bot), "hpins")
    for i, (x, y) in enumerate(HPINS, 1):
        anc[f"pad{i}"] = ((x, y, PCB_STEP), None)
    anc["board"] = ((7.62 + 3.0, 3.6, PCB_STEP), ("pcb", "cu"))
    return parts, anc


# ================================================================== JP1, R1
SULLINS = "#1E1E1E"
SHUNT = "#2B2B2B"


def jp1_parts(shunt=True, shunt_lift=0.0, tails=1.0, soldered=True, z0=0.0):
    """Sullins PRPC002SAAN-RC (2 posts along +x, pin 1 at x = 0) on a board whose top is z0, with its SPC02SYAN shunt
    (lifted shunt_lift above its seat when shown loose)."""
    plastic, post, sq = S.val("jp1_hdr")
    sl, sw, sh = S.val("shunt_spc02")
    out, anc = [], {}
    out.append(("jp1", box(-1.27, -1.27, z0, P + 1.27, 1.27, z0 + plastic).val(), SULLINS, 0.8))
    posts = [box(x - sq / 2, -sq / 2, z0 - T - tails, x + sq / 2, sq / 2, z0 + plastic + post).val() for x in (0, P)]
    out.append(("posts", cq.Compound.makeCompound(posts), PIN, 0.4))
    if soldered:
        out.append(("jfil", cq.Compound.makeCompound([fillet_cone(x, 0, z0 - T, False) for x in (0, P)]), TIN, 0.4))
    anc["jp1"] = ((P / 2, -1.27, z0 + plastic / 2), "jp1")
    anc["post1"] = ((0, 0, z0 + plastic + post), "posts")
    anc["top"] = ((P / 2, 0.8, z0 + plastic), "jp1")
    if shunt:
        zs = z0 + plastic + shunt_lift
        sb = box(P / 2 - sl / 2, -sw / 2, zs, P / 2 + sl / 2, sw / 2, zs + sh)
        sb = sb.faces(">Z").edges().chamfer(0.4)
        sb = sb.cut(box(P / 2 - sl / 2 - 1, -0.35, zs + sh - 1.4, P / 2 + sl / 2 + 1, 0.35, zs + sh + 1))   # grip slot
        out.append(("shunt", sb.val(), SHUNT, 0.9))
        anc["shunt"] = ((P / 2 + 1.6, -sw / 2, zs + sh * 0.6), "shunt")
    return out, anc


DIGIT = ["#1C1C1C", "#7A4A23", "#D7262E", "#F07C1A", "#F2D21A", "#2E9A48", "#2D6FD0", "#8E44AD", "#8C8C8C", "#F4F4F4"]
R1_BANDS = [DIGIT[1], DIGIT[0], DIGIT[0], DIGIT[2], DIGIT[1]]      # 10 k 1 %: brown black black red, brown tolerance
R1_BODY = "#8FB2DA"                                                # Yageo MFR-25: blue body (TX sheets' colour)


def r1_parts(p1, p2, z_top, tails=1.0):
    """Lying axial resistor between hole centres p1 and p2 (XY) on a board whose top is z_top: body on the board, leads
    bent down at the body ends; bands start at lead 1's end."""
    bl, bd = S.val("r1_body")
    p1, p2 = np.array(p1, float), np.array(p2, float)
    u = (p2 - p1) / np.linalg.norm(p2 - p1)
    r = bd / 2
    zc = z_top + 0.1 + r
    a = (p1 + p2) / 2 - u * bl / 2
    b_ = a + u * bl
    out, anc = [], {}
    cyl = cq.Solid.makeCylinder(r, bl, cq.Vector(a[0], a[1], zc), cq.Vector(u[0], u[1], 0))
    cyl = cq.Workplane().add(cyl).edges().fillet(r * 0.45).val()
    out.append(("rbody", cyl, R1_BODY, 0.8))
    for k, (c, f) in enumerate(zip(R1_BANDS, [0.16, 0.27, 0.38, 0.49, 0.80])):
        q = a + u * (f * bl - 0.28)
        out.append((f"rb{k}", cq.Solid.makeCylinder(r + 0.03, 0.56, cq.Vector(q[0], q[1], zc), cq.Vector(u[0], u[1], 0)),
                    c, 0.3))
    e1, e2 = a + u * 0.3, b_ - u * 0.3
    lead = tube([(*p1, z_top - T - tails), (*p1, zc), (*e1, zc)], 0.3).fuse(
        tube([(*p2, z_top - T - tails), (*p2, zc), (*e2, zc)], 0.3))
    out.append(("rleads", lead, TIN, 0.4))
    fil = [fillet_cone(*p, z_top - T, False) for p in (p1, p2)]
    out.append(("rfil", cq.Compound.makeCompound(fil), TIN, 0.4))
    q = a + u * 0.65 * bl
    anc["r1"] = ((q[0], q[1], zc + r), "rbody")
    return out, anc


# ================================================================== the port cable: 6P6C plug, PG-7 gland, round cable
def plug(scene=None, part="plug", contacts=True):
    """A 6P6C (RJ12) crimp plug, the TX sources' plug_6p body (9.65 wide, 6.6 tall, 13.34 long; latch 5.95 long): its tip
    (contact end) at y = 0 pointing -y, the cable leaving +y, the gold contacts on its top face (+z), the latch underneath.
    Contact n at x = (n - 3.5) x 1.02 with the plug seen from above, tip toward the viewer: pin 1 on the RIGHT from above
    tip-away, i.e. on the LEFT when the plug is held tip UP, contacts toward you, latch away (TIA-968 numbering)."""
    pw, ph, phl, pl = S.val("plug_6p")
    body = box(-pw / 2, 0, 0, pw / 2, pl, ph).edges("|Y").fillet(0.6)
    latch = box(-1.7, 1.5, -(phl - ph), 1.7, 1.5 + 5.95, 0.01)
    parts = [("body", body.val(), PLUG, 1.0), ("latch", latch.val(), PLUG, 0.8)]
    cs, anc = [], {}
    for n in range(1, 7):
        # seen from above with the tip toward -y: TIA pin 1 sits at +x (it is on the left with the plug flipped tip-up,
        # contacts toward you): x = (3.5 - n) * 1.02
        x = (3.5 - n) * 1.02
        cs.append(box(x - 0.2, 0.4, ph - 0.25, x + 0.2, 3.6, ph + 0.05).val())
        anc[f"c{n}"] = ((x, 2.0, ph + 0.05), "contacts")
    if contacts:
        parts.append(("contacts", cq.Compound.makeCompound(cs), GOLD, 0.3))
    return parts, anc


def gland_pg7():
    """Adafruit #762 PG-7 cable gland (sources gland_pg7: 11.5 thread, 6.0 thread length, 16.6 nut across corners, 11.4
    cap): its axis along +y from y = 0 (the thread's end inside the box) to the dome's end. Returns
    [(name, shape, colour)] for the body + thread, the lock nut, the seal and the dome nut, and the y of each."""
    th, L1, nut, L3, cmin, cmax = S.val("gland_pg7")
    r = th / 2
    def ycyl(rr, y0, y1):
        return cq.Solid.makeCylinder(rr, y1 - y0, cq.Vector(0, y0, 0), cq.Vector(0, 1, 0))
    def hexy(af, y0, y1):
        return cq.Workplane("XZ").polygon(6, af).extrude(-(y1 - y0)).translate((0, y0, 0)).val()
    thread = ycyl(r, 0, L1)
    flange = hexy(nut, L1, L1 + 3.0)
    body = cq.Workplane().add(thread).union(cq.Workplane().add(flange)).union(cq.Workplane().add(ycyl(r, L1 + 3, L1 + 7)))
    body = body.cut(cq.Workplane().add(ycyl(3.3, -1, L1 + 8)))
    lock = cq.Workplane().add(hexy(nut, 0.5, 3.0)).cut(cq.Workplane().add(ycyl(r, 0, 4)))
    dome = cq.Workplane().add(hexy(nut * 0.95, L1 + 7, L1 + 11)).union(
        cq.Workplane().add(cq.Solid.makeCone(nut * 0.42, 3.4, 3.5, cq.Vector(0, L1 + 11, 0), cq.Vector(0, 1, 0))))
    dome = dome.cut(cq.Workplane().add(ycyl(2.4, L1 + 6, L1 + 16)))
    return [("gbody", body.val(), "#2B2B2B"), ("glock", lock.val(), "#3A3A3A"), ("gdome", dome.val(), "#2B2B2B")]
