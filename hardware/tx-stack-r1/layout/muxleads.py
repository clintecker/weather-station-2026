"""The PCA9548 mux (Adafruit #5626) on the backplane's copper side: its 5 header leads and its 4 channel cables.

Pad and port places are Adafruit's own board file (github.com/adafruit/Adafruit-PCA9548-PCB, "PCA9548A QT Board.brd",
40.64 x 20.32 mm, origin at the corner below the upstream QT port, seen from the top face):
  JP1, a 5-hole 0.1 in header at x 38.10 (the end away from the upstream port): VIN y 5.08, GND 7.62, SCL 10.16,
      SDA 12.70, RST 15.24. Through-plated. 22 AWG solid insulated leads (Adafruit 1311).
  Channels 0-3: the JST SH QT ports CONN1/2/5/6 on the top face at x 8.89, 16.51, 24.13, 31.75, mouths on the y = 0
      edge. (Their SD/SC test points TP1-TP16 are SMD pads on the bottom layer: no room for a lead under the mux.)
      Each takes an Adafruit #4209 QT cable (JST SH to male pins) with the pin end cut off. Its blue SDA and yellow
      SCL go to hole 10; red V+ and black GND are cut back at the plug and taped (the mux's GND is its header lead).
  A0 jumper: back face at (17.53, 6.35).

Mounting (stack.MUX_BOX): back face on a foam pad on the copper side, the channel 0-3 edge (y = 0) toward hole 10,
the JP1 end toward the higher lines. In backplane terms: line = 1.5 + x / 2.54, hole = 9.5 - y / 2.54.

Paths are in (line, hole, d), d = mm behind the copper face (toward the back wall; the front face is at -1.6).
Each wire enters its hole 10 from the copper side and is soldered on the front; the bus wire's joint on the copper
side takes it too. Header lead cut = path + 3 mm in the pad + 10 mm; cable cut = plug face to hole + 3 mm stripped +
10 mm; both rounded up to 5 mm. Used by drawings.py (BACKPLANE.md section 5) and the Session 6 sheet
(sheets/session6/scenes6.py), so both print the same lengths."""
import math

import stack as st
from stack import S

P = S.val("pitch")
FOAM = S.val("foam")
PCB = 1.6
MUX_LINE0, MUX_HOLE0 = 1.5, 9.5          # the mux's (x 0, y 0) corner: line 1.5, hole 9.5
assert abs(st.MUX_BOX[0] - (st.strip_x(2) - P / 2)) < 1e-6 and abs(st.MUX_BOX[3] - (st.BP_Z0 + 8.5 * P + 0.0)) < 1.0, \
    "stack.MUX_BOX moved: update muxleads"

JP1_X = 38.10
JP1 = {"VIN": 5.08, "GND": 7.62, "SCL": 10.16, "SDA": 12.70, "RESET": 15.24}   # model pin names (RESET = silk RST)
QT_X = {0: 8.89, 1: 16.51, 2: 24.13, 3: 31.75}           # channel -> its QT port's centre x (CONN1, 2, 5, 6)
QT_TOP = (0.6, 2.3)          # the JST SH mouth, mm above the top face (socket body 2.9 tall)
PLUG_IN, PLUG_OUT = 2.2, -2.8   # a seated #4209 plug runs from y 2.2 inside the socket to y -2.8 past the mux edge
PLUG_W = 4.4
QT_WIRE = {"GND": (-1.5, "black"), "V+": (-0.5, "red"), "SDA": (0.5, "blue"), "SCL": (1.5, "yellow")}  # x off, colour
TP_Y = 2.286                 # the channel 0-3 SMD test points on the bottom layer, as supplied (drawn only, never wired)
TP = {"SD0": 7.62, "SC0": 10.16, "SD1": 15.24, "SC1": 17.78, "SD2": 22.86, "SC2": 25.40, "SD3": 30.48, "SC3": 33.02}
CABLE_R = 0.45               # one #4209 wire (about 0.9 mm over the insulation)
STUB = 3.0                   # red and black are cut this far out of the plug and taped
A0 = (17.526, 6.35)
SILK = {"RESET": "RST"}


def lh(x, y):
    """Mux (x, y) mm -> backplane (line, hole)."""
    return MUX_LINE0 + x / P, MUX_HOLE0 - y / P


def target():
    """pad -> (line, hole) from stack.MUX_HOLES (BACKPLANE.md section 5)."""
    out = {}
    for pad, h in st.MUX_HOLES.items():
        i, n = (int(v) for v in h[1:].split("."))
        out[{"H.VCC": "VIN", "H.GND": "GND", "H.SCL": "SCL", "H.SDA": "SDA", "H.RST": "RESET"}.get(pad, pad)] = (i, n)
    return out


WIRE_R = 0.8                             # 22 AWG solid hook-up, insulated (Adafruit 1311): about 1.6 mm over the PVC


def plug_z():
    """d of the plug's centre: foam + PCB + the middle of the socket mouth."""
    return FOAM + PCB + sum(QT_TOP) / 2


def wire_exit(k, sig):
    """(line, hole, d) where wire sig of channel k's cable leaves the plug's back."""
    l0, h0 = lh(QT_X[k] + QT_WIRE[sig][0], PLUG_OUT)
    return l0, h0, plug_z()


def path(pad):
    """The lead's centreline, mux end first: [(line, hole, d)]. pad: a header pin (VIN GND SCL SDA RESET) or a
    channel wire 'CHk.SDA' / 'CHk.SCL' (from the cable plug's back)."""
    tl, th = target()[pad]
    if pad.startswith("CH"):             # out of the plug, down off the plug's end, back to hole 10 on its line
        k, sig = int(pad[2]), pad.split(".")[1]
        l0, h0, z = wire_exit(k, sig)
        return [(l0, h0, z), (l0, h0 + 0.3, z), (l0, h0 + 0.45, z - 1.2), (tl, h0 + 0.25, 1.2), (tl, th + 0.4, 0.7),
                (tl, th, 0.0), (tl, th, -PCB - 1.0)]
    k = list(JP1).index(pad)             # header: in from the top face, over the end, up to hole 11.5, along
    l0, h0 = lh(JP1_X, JP1[pad])
    top = FOAM + PCB
    lane = WIRE_R + 1.6 * k * 0.5        # the five lie side by side, a little stacked
    end = MUX_LINE0 + 40.64 / P + 0.35   # just past the mux's JP1 end
    xo = end + 0.25 + 0.45 * k          # side by side up the copper face past the mux's end
    return [(l0, h0, top), (l0, h0, top + 1.0), (end, h0, top + 1.0), (xo, h0, lane), (xo, 11.5, lane),
            (tl + 0.3, 11.5, lane), (tl, th + 0.5, 0.9), (tl, th, 0.0), (tl, th, -PCB - 1.0)]


def mm(p, q):
    return math.sqrt(((p[0] - q[0]) * P) ** 2 + ((p[1] - q[1]) * P) ** 2 + (p[2] - q[2]) ** 2)


def cut(pad):
    """Header lead: the whole lead. Channel wire: the cable from the plug's back (cut the pin end off there)."""
    pts = path(pad)
    L = sum(mm(a, b) for a, b in zip(pts, pts[1:])) + 3 + 10
    return int(math.ceil(L / 5) * 5)


def cable_cut(k):
    """Channel k's cable: the longer of its two signal wires."""
    return max(cut(f"CH{k}.SDA"), cut(f"CH{k}.SCL"))


if __name__ == "__main__":
    for p in list(JP1):
        print(p, target()[p], cut(p), "mm")
    for k in QT_X:
        print(f"CH{k}", target()[f"CH{k}.SDA"], target()[f"CH{k}.SCL"], cable_cut(k), "mm of cable")
