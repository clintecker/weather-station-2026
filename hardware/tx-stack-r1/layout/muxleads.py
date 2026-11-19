"""The PCA9548 mux (Adafruit #5626) on the backplane's copper side, and its 13 leads to hole 10.

Pad positions are Adafruit's own board file (github.com/adafruit/Adafruit-PCA9548-PCB, "PCA9548A QT Board.brd",
40.64 x 20.32 mm, origin at the corner below the upstream QT port, seen from the top face):
  JP1, a 5-hole 0.1 in header at x 38.10 (the end away from the upstream port): VIN y 5.08, GND 7.62, SCL 10.16,
      SDA 12.70, RST 15.24. Through-plated.
  Channels 0-3: round 1.5 mm test pads on the BACK face (the face with the A0-A2 jumpers) along y 2.286, beside the
      QT ports CONN1/2/5/6: SD0 x 7.62, SC0 10.16, SD1 15.24, SC1 17.78, SD2 22.86, SC2 25.40, SD3 30.48, SC3 33.02.
  A0 jumper: back face at (17.53, 6.35).

Mounting (stack.MUX_BOX): back face on a foam pad on the copper side, the channel 0-3 edge (y = 0) toward hole 10,
the JP1 end toward the higher lines. In backplane terms: line = 1.5 + x / 2.54, hole = 9.5 - y / 2.54.

Lead paths are in (line, hole, d), d = mm behind the copper face (toward the back wall; the front face is at -1.6).
Each lead enters its hole 10 from the copper side and is soldered on the front; the bus wire's joint on the copper
side takes it too. Cut = path + 3 mm in the pad + 10 mm, rounded up to 5 mm. Used by drawings.py (BACKPLANE.md
section 5) and the Session 6 sheet (sheets/session6/scenes6.py), so both print the same lengths."""
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
TP_Y = 2.286
TP = {"SD0": 7.62, "SC0": 10.16, "SD1": 15.24, "SC1": 17.78, "SD2": 22.86, "SC2": 25.40, "SD3": 30.48, "SC3": 33.02}
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


def path(pad):
    """The lead's centreline, pad end first: [(line, hole, d)]."""
    tl, th = target()[pad]
    if pad in TP:                        # back-face test pad: the bare end lies on the pad, under the mux
        l0, h0 = lh(TP[pad], TP_Y)
        d = WIRE_R if pad.startswith("SD") else 3 * WIRE_R      # SC leads pass over the SD leads
        return [(l0, h0, FOAM - 0.35), (l0, MUX_HOLE0, FOAM - 0.35), (l0, 9.8, d), (tl, 9.8, d), (tl, th, 0.0),
                (tl, th, -PCB - 1.0)]
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
    pts = path(pad)
    L = sum(mm(a, b) for a, b in zip(pts, pts[1:])) + 3 + 10
    return int(math.ceil(L / 5) * 5)


if __name__ == "__main__":
    for p in list(JP1) + list(TP):
        print(p, target()[p], cut(p), "mm")
