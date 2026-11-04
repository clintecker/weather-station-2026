"""Writes the bench as a KiCad board from build.py, with 3D models, and renders it with kicad-cli.

The KiCad board is the base plate. Breadboards, modules, leaded parts, jumpers and wires are footprints
with 3D models: KiCad's own STEP models for the resistors, capacitors and link headers; generated VRML
(kicad/3d/) for the breadboards, the modules and every wire. Connectivity is not KiCad's job here:
build.py proves the copper equals the schematic, and this script refuses to run while it fails.

Writes kicad/bench-r1.kicad_pcb (the whole plate) and kicad/bench-r1-BBn.kicad_pcb (one breadboard each,
for close-up renders). Run: python3 kicad_layout.py [--render]
"""
import math
import subprocess
import sys
import uuid
from pathlib import Path

import build as b
import routing

OUT = b.HERE / "kicad"
M3D = OUT / "3d"
LIB3D = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")
KICAD_CLI = "kicad-cli"
WRL = 1 / 2.54                      # KiCad reads VRML in units of 0.1 inch
SEAT_Z = b.BB_Z + 2.5               # PCB underside of a module seated on a breadboard (header plastic 2.5 mm)
PCB_T = 1.6


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "bench-r1/" + "/".join(map(str, parts))))


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# ------------------------------------------------------------------ stroke font (y up, cell 4 x 6)
_O = [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]]
FONT = {
    "0": _O + [[(0, 0), (4, 6)]], "1": [[(2, 0), (2, 6)], [(1, 5), (2, 6)]],
    "2": [[(0, 6), (4, 6), (4, 3), (0, 3), (0, 0), (4, 0)]], "3": [[(0, 6), (4, 6), (4, 0), (0, 0)], [(0, 3), (4, 3)]],
    "4": [[(0, 6), (0, 3), (4, 3)], [(4, 6), (4, 0)]], "5": [[(4, 6), (0, 6), (0, 3), (4, 3), (4, 0), (0, 0)]],
    "6": [[(4, 6), (0, 6), (0, 0), (4, 0), (4, 3), (0, 3)]], "7": [[(0, 6), (4, 6), (4, 0)]],
    "8": _O + [[(0, 3), (4, 3)]], "9": [[(4, 3), (0, 3), (0, 6), (4, 6), (4, 0), (0, 0)]],
    "A": [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 3), (4, 3)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 6), (0, 6), (0, 0), (4, 0)]], "D": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 1), (3, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]], "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 6), (0, 6), (0, 0), (4, 0), (4, 3), (2, 3)]], "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 0), (3, 0)], [(2, 0), (2, 6)], [(1, 6), (3, 6)]], "J": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 3), (4, 0)]], "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]], "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]], "O": _O,
    "P": [[(0, 0), (0, 6), (4, 6), (4, 3), (0, 3)]], "Q": _O + [[(2, 2), (4, 0)]],
    "R": [[(0, 0), (0, 6), (4, 6), (4, 3), (0, 3), (4, 0)]], "S": [[(4, 6), (0, 6), (0, 3), (4, 3), (4, 0), (0, 0)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]], "U": [[(0, 6), (0, 0), (4, 0), (4, 6)]], "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 3), (3, 0), (4, 6)]], "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]], "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "x": [[(0, 0), (4, 4)], [(0, 4), (4, 0)]],
    "a": [[(4, 4), (4, 0)], [(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "b": [[(0, 6), (0, 0)], [(0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (3, 4), (1, 4), (0, 3)]],
    "c": [[(4, 4), (1, 4), (0, 3), (0, 1), (1, 0), (4, 0)]],
    "d": [[(4, 6), (4, 0)], [(4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4), (3, 4), (4, 3)]],
    "e": [[(0, 2), (4, 2), (4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (4, 0)]],
    "f": [[(1, 0), (1, 5), (2, 6), (4, 6)], [(0, 3), (3, 3)]],
    "g": [[(4, 4), (4, -1), (3, -2), (0, -2)], [(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "q": [[(4, 4), (4, -2)], [(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "h": [[(0, 6), (0, 0)], [(0, 3), (1, 4), (3, 4), (4, 3), (4, 0)]],
    "i": [[(2, 0), (2, 4)], [(2, 5.4), (2, 6)]], "j": [[(3, 4), (3, -1), (2, -2), (0, -2)], [(3, 5.4), (3, 6)]],
    "+": [[(0, 3), (4, 3)], [(2, 1), (2, 5)]], "-": [[(0, 3), (4, 3)]], ".": [[(2, 0), (2, 0.6)]],
    "/": [[(0, 0), (4, 6)]], " ": [], "#": [[(1, 0), (1, 6)], [(3, 0), (3, 6)], [(0, 2), (4, 2)], [(0, 4), (4, 4)]],
}


# ------------------------------------------------------------------ VRML mesh, model frame in mm (y up)
class Mesh:
    def __init__(self):
        self.parts = {}          # colour -> (points, faces)

    def _add(self, colour, pts, faces):
        P, F = self.parts.setdefault(colour, ([], []))
        base = len(P)
        P.extend(pts)
        F.extend([[base + i for i in f] for f in faces])

    def box(self, x0, y0, z0, x1, y1, z1, colour):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
               (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        self._add(colour, pts, faces)

    def quad(self, x0, y0, x1, y1, z, colour):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        self._add(colour, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [[0, 1, 2, 3]])

    def cyl(self, p0, p1, r, colour, n=10, caps=True):
        ax = [p1[i] - p0[i] for i in range(3)]
        L = math.sqrt(sum(a * a for a in ax)) or 1e-9
        ax = [a / L for a in ax]
        ref = (0, 0, 1) if abs(ax[2]) < 0.9 else (1, 0, 0)
        u = [ax[1] * ref[2] - ax[2] * ref[1], ax[2] * ref[0] - ax[0] * ref[2], ax[0] * ref[1] - ax[1] * ref[0]]
        ul = math.sqrt(sum(a * a for a in u))
        u = [a / ul for a in u]
        v = [ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0]]
        pts = []
        for p in (p0, p1):
            for k in range(n):
                t = 2 * math.pi * k / n
                pts.append(tuple(p[i] + r * (math.cos(t) * u[i] + math.sin(t) * v[i]) for i in range(3)))
        faces = [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
        if caps:
            faces += [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
        self._add(colour, pts, faces)

    def tube(self, pts, r, colour, n=8):
        for a, c in zip(pts, pts[1:]):
            self.cyl(a, c, r, colour, n, caps=False)

    def text(self, s, x, y, z, h, colour, anchor="left", vertical=False):
        """Stroke text lying flat at height z; (x, y) is the baseline start (model frame)."""
        u = h / 6
        w = 0.12 * h
        adv = 6 * u
        total = len(s) * adv - 2 * u
        if anchor == "center":
            x -= total / 2
        elif anchor == "right":
            x -= total
        for i, ch in enumerate(s):
            for stroke in FONT.get(ch, FONT.get(ch.upper(), [])):
                for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                    p0 = (x + i * adv + ax * u, y + ay * u)
                    p1 = (x + i * adv + bx * u, y + by * u)
                    self._seg(p0, p1, w, z, colour)

    def _seg(self, p0, p1, w, z, colour):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            dx, dy, L = 0.0, 1e-3, 1e-3
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        ex, ey = dx / L * w / 2, dy / L * w / 2
        pts = [(p0[0] + nx - ex, p0[1] + ny - ey, z), (p1[0] + nx + ex, p1[1] + ny + ey, z),
               (p1[0] - nx + ex, p1[1] - ny + ey, z), (p0[0] - nx - ex, p0[1] - ny - ey, z)]
        self._add(colour, pts, [[0, 1, 2, 3]])

    def write(self, path):
        out = ["#VRML V2.0 utf8"]
        for colour, (P, F) in self.parts.items():
            r, g, bl = rgb(colour)
            pts = ", ".join(f"{x * WRL:.4f} {y * WRL:.4f} {z * WRL:.4f}" for x, y, z in P)
            idx = ", ".join(" ".join(map(str, f)) + " -1" for f in F)
            out.append(f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r:.3f} {g:.3f} {bl:.3f} "
                       f"specularColor 0.15 0.15 0.15 shininess 0.25 }} }} geometry IndexedFaceSet {{ solid FALSE "
                       f"creaseAngle 0.6 coord Coordinate {{ point [ {pts} ] }} coordIndex [ {idx} ] }} }}")
        path.write_text("\n".join(out) + "\n")


C = dict(bb="#F4F4F0", hole="#1C1C1C", trench="#DADAD4", red="#C8102E", blue="#1F5FBF", ink="#3A3A3A",
         pcb_ada="#161616", pcb_sf="#B5121B", pcb_pololu="#1D6B33", pcb_st="#F2F2F2", silk="#F5F5F5",
         gold="#D4AF37", plastic="#151515", metal="#B8BCC2", jst="#EDE6D6", term="#2E7D32", chip="#202020",
         wago="#C9CCCF", lever="#F08A24", pack="#27406E", label="#E8C547", glass="#0B0F14", glass_edge="#30343A",
         led="#3BD16F", copper="#B87333", shunt="#0A0A0A")


# ------------------------------------------------------------------ model of one breadboard
def breadboard_model():
    m = Mesh()
    z = b.BB_Z
    m.box(0, 0, 0, b.BB_W, -b.BB_H, z, C["bb"])
    m.box(0, -26.0, z - 0.6, b.BB_W, -28.6, z + 0.01, C["trench"])
    for row in b.ROW_ORDER:
        for col in range(1, b.NCOL + 1):
            h = f"BB1:{row}{col}"
            if not b.hole_exists(h):
                continue
            x = b.COL_MARGIN + (b.NCOL - col) * b.P
            y = -b.ROW_Y[row]
            m.quad(x - 0.55, y - 0.55, x + 0.55, y + 0.55, z + 0.02, C["hole"])
    for row, col in (("T+", C["red"]), ("T-", C["blue"]), ("B+", C["red"]), ("B-", C["blue"])):
        off = {"T+": 1.5, "T-": -1.5, "B+": 1.5, "B-": -1.5}[row]
        y = -(b.ROW_Y[row] + (-off if row.startswith("T") else off * -1))
        y = -(b.ROW_Y[row] - 1.6) if row in ("T+", "B+") and row == "T+" else y
        yy = {"T+": -(b.ROW_Y["T+"] - 1.7), "T-": -(b.ROW_Y["T-"] + 1.7),
              "B+": -(b.ROW_Y["B+"] - 1.7), "B-": -(b.ROW_Y["B-"] + 1.7)}[row]
        m.quad(4.0, yy - 0.2, b.BB_W - 4.0, yy + 0.2, z + 0.02, col)
        sign = "+" if row.endswith("+") else "-"
        for xx in (1.4, b.BB_W - 3.2):
            m.text(sign, xx, -b.ROW_Y[row] - 0.9, z + 0.03, 1.8, col)
    for col in list(range(5, b.NCOL + 1, 5)) + [1, b.NCOL]:
        x = b.COL_MARGIN + (b.NCOL - col) * b.P
        for yrow, dy in (("a", 2.0), ("j", -3.6)):
            m.text(str(col), x, -b.ROW_Y[yrow] + dy, z + 0.03, 1.5, C["ink"], "center")
    for row in "abcdefghij":
        for xx in (1.2, b.BB_W - 3.2):
            m.text(row, xx, -b.ROW_Y[row] - 0.7, z + 0.03, 1.5, C["ink"])
    return m


# ------------------------------------------------------------------ module models (local frame, z = 0 at the PCB underside)
def header_under(m, pts, into_board=True):
    """Male header soldered under a module: plastic below the PCB, long pins down into the breadboard."""
    for x, y in pts:
        m.box(x - 1.27, -y - 1.27, -2.5, x + 1.27, -y + 1.27, 0, C["plastic"])
        m.box(x - 0.32, -y - 0.32, -8.5 if into_board else -2.5, x + 0.32, -y + 0.32, PCB_T + 1.5, C["gold"])


def pcb(m, w, h, colour, holes=(), standoff=0.0):
    m.box(0, 0, 0, w, -h, PCB_T, colour)
    for x, y in holes:
        m.cyl((x, -y, PCB_T + 0.01), (x, -y, PCB_T + 0.02), 1.4, C["gold"], 14)
        if standoff:                                  # brass standoff down to the plate
            m.cyl((x, -y, -standoff), (x, -y, 0), 1.6, "#C9A227", 6)


def qt_socket(m, x, y, facing):
    """JST SH 4-pin socket at an edge; facing: 'left' or 'right' (mouth towards the outside)."""
    w = 4.25
    x0, x1 = (x, x + w) if facing == "left" else (x - w, x)
    m.box(x0, -y - 3.0, PCB_T, x1, -y + 3.0, PCB_T + 2.9, C["jst"])
    mx = x0 + 0.05 if facing == "left" else x1 - 0.05
    m.box(mx - 0.06, -y - 2.2, PCB_T + 0.6, mx + 0.06, -y + 2.2, PCB_T + 2.3, C["plastic"])


def label(m, s, x, y, h, colour=None, anchor="center"):
    m.text(s, x, -y, PCB_T + 0.02, h, colour or C["silk"], anchor)


def model_ina(name):
    m = Mesh()
    w, h = b.SIZE["INA"]
    pcb(m, w, h, C["pcb_ada"], holes=((2.54, 2.54), (22.86, 2.54)))
    m.box(7.45, -0.0, PCB_T, 17.95, -7.6, PCB_T + 8.5, C["term"])                 # 3-way 3.5 mm terminal
    for x in (9.2, 12.7, 16.2):
        m.cyl((x, -4.6, PCB_T + 8.5), (x, -4.6, PCB_T + 8.55), 1.25, C["metal"], 12)
        m.box(x - 1.1, 0.02, PCB_T + 1.6, x + 1.1, -0.2, PCB_T + 4.2, C["plastic"])
    m.box(10.2, -9.0, PCB_T, 15.2, -12.0, PCB_T + 0.7, C["chip"])
    m.box(4.0, -9.2, PCB_T, 8.0, -11.0, PCB_T + 0.6, C["chip"])
    qt_socket(m, 0, b.LOCAL["INA"]["QT1.GND"][1], "left")
    qt_socket(m, w, b.LOCAL["INA"]["QT2.GND"][1], "right")
    header_under(m, [b.LOCAL["INA"][p] for p in b.HEADER["INA"]])
    label(m, "INA228", w / 2, 14.8, 1.6)
    label(m, name, w / 2, 9.0 + 4.5, 1.4, C["label"])
    return m


def model_gauge():
    m = Mesh()
    w, h = b.SIZE["GAUGE"]
    pcb(m, w, h, C["pcb_ada"])
    for x in (8.0, 17.4):
        m.box(x - 3.0, -0.0, PCB_T, x + 3.0, -4.5, PCB_T + 6.0, C["jst"])
        m.box(x - 2.4, 0.02, PCB_T + 1.2, x + 2.4, -0.3, PCB_T + 5.0, C["plastic"])
    m.box(10.6, -7.5, PCB_T, 14.6, -10.5, PCB_T + 0.7, C["chip"])
    qt_socket(m, 0, 8.89, "left")
    qt_socket(m, w, 8.89, "right")
    header_under(m, [b.LOCAL["GAUGE"][p] for p in b.HEADER["GAUGE"]])
    label(m, "MAX17048", w / 2, 13.2, 1.4)
    return m


def model_chg():
    m = Mesh()
    w, h = b.SIZE["CHG"]
    L = b.LOCAL["CHG"]
    pcb(m, w, h, C["pcb_ada"], holes=((2.54, 2.54), (35.56, 2.54)))
    y = L["USB.VBUS"][1]
    m.box(-0.8, -y - 4.5, PCB_T, 7.0, -y + 4.5, PCB_T + 3.2, C["metal"])
    m.box(-0.82, -y - 3.6, PCB_T + 0.6, -0.78, -y + 3.6, PCB_T + 2.6, C["plastic"])
    y = L["DC.+"][1]
    m.box(-0.5, -y - 4.5, PCB_T, 13.5, -y + 4.5, PCB_T + 11.0, C["plastic"])
    m.cyl((-0.52, -y, PCB_T + 6.0), (-0.51, -y, PCB_T + 6.0), 3.2, C["metal"], 16)
    for key in ("BATT.+", "SYS.+"):
        y = L[key][1]
        m.box(w - 4.5, -y - 3.0, PCB_T, w + 0.6, -y + 3.0, PCB_T + 6.0, C["jst"])
        m.box(w + 0.58, -y - 2.4, PCB_T + 1.2, w + 0.62, -y + 2.4, PCB_T + 5.0, C["plastic"])
    m.box(17.0, -12.0, PCB_T, 21.0, -16.0, PCB_T + 0.8, C["chip"])
    for x, colour in ((25.0, C["led"]), (28.0, "#E03030")):
        m.box(x, -24.5, PCB_T, x + 1.6, -25.3, PCB_T + 0.6, colour)
    header_under(m, [L[p] for p in b.HEADER["CHG"]])
    label(m, "bq24074", w / 2, 8.0, 2.0)
    for i, n in enumerate(["VB", "G", "TH", "IS", "CE", "PG", "CH", "OUT", "G", "BAT", "G"]):
        m.text(n, 6.35 + i * b.P, -27.4, PCB_T + 0.02, 0.9, C["silk"], "center")
    return m


def model_reg():
    m = Mesh()
    w, h = b.SIZE["REG"]
    pcb(m, w, h, C["pcb_pololu"])
    m.box(2.2, -3.0, PCB_T, 9.2, -10.0, PCB_T + 3.0, "#3A3A3A")
    header_under(m, [b.LOCAL["REG"][p] for p in b.HEADER["REG"]])
    label(m, "S7V8F3", w / 2, 13.0, 1.2)
    return m


def model_bob():
    m = Mesh()
    w, h = b.SIZE["BOB"]
    pcb(m, w, h, C["pcb_sf"])
    m.box(w / 2 - 7.0, -6.0, PCB_T, w / 2 + 7.0, -h - 0.5, PCB_T + 11.5, "#DCDCDC")
    m.box(w / 2 - 4.8, -h - 0.52, PCB_T + 3.0, w / 2 + 4.8, -h - 0.48, PCB_T + 9.0, C["plastic"])
    header_under(m, [b.LOCAL["BOB"][p] for p in b.HEADER["BOB"]])
    for i in range(1, 7):
        x, y = b.LOCAL["BOB"][str(i)]
        m.text(str(i), x, -y - 3.0, PCB_T + 0.02, 1.0, C["silk"], "center")
    return m


def model_oled():
    m = Mesh()
    w, h = b.SIZE["OLED"]
    pcb(m, w, h, C["pcb_ada"], holes=((3.0, 3.0), (82.0, 3.0), (3.0, 55.0), (82.0, 55.0)))
    m.box(5.0, -7.5, PCB_T, 80.0, -52.0, PCB_T + 2.2, C["glass_edge"])
    m.box(8.5, -10.5, PCB_T + 2.2, 76.5, -47.0, PCB_T + 2.25, C["glass"])
    header_under(m, [b.LOCAL["OLED"][p] for p in b.HEADER["OLED"]])
    for i in (1, 2, 4, 7, 8, 15, 16, 20):
        x, y = b.LOCAL["OLED"][str(i)]
        m.text(str(i), x, -y - 3.6, PCB_T + 0.02, 1.0, C["silk"], "center")
    label(m, "SSD1325 OLED", w / 2, 50.5, 1.8)
    return m


def model_nucleo(name):
    m = Mesh()
    w, h = b.SIZE["NUCLEO"]
    L = b.LOCAL["NUCLEO"]
    pcb(m, w, h, C["pcb_st"])                          # no mounting holes: the cradle's corner ledges hold it
    for cx, cy, sx, sy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        m.box(cx - sx * 1.2, -(cy - sy * 1.2), -NUC_Z, cx + sx * 4.0, -(cy + sy * 4.0), 0, "#C8C4BA")
    for cn, n in (("CN5", 10), ("CN9", 8), ("CN6", 8), ("CN8", 6)):
        xs = [L[f"{cn}.{i}"] for i in range(1, n + 1)]
        x = xs[0][0]
        ys = [p[1] for p in xs]
        m.box(x - 1.27, -min(ys) + 1.27, PCB_T, x + 1.27, -max(ys) - 1.27, PCB_T + 8.5, C["plastic"])
        for _x, y in xs:
            m.quad(x - 0.45, -y - 0.45, x + 0.45, -y + 0.45, PCB_T + 8.51, "#000000")
    for cn in ("CN7", "CN10"):
        pts = [L[f"{cn}.{i}"] for i in range(1, 39)]
        xs = sorted({p[0] for p in pts})
        ys = [p[1] for p in pts]
        m.box(min(xs) - 1.27, -min(ys) + 1.27, PCB_T, max(xs) + 1.27, -max(ys) - 1.27, PCB_T + 2.5, C["plastic"])
        for x, y in pts:
            m.box(x - 0.32, -y - 0.32, PCB_T, x + 0.32, -y + 0.32, PCB_T + 8.5, C["gold"])
    m.box(28.0, -26.0, PCB_T, 35.0, -33.0, PCB_T + 0.9, C["chip"])
    m.box(30.0, -48.0, PCB_T, 40.0, -56.0, PCB_T + 0.9, C["chip"])
    m.box(31.3, -h + 0.5, -2.8, 38.7, -h - 1.0, 0, C["metal"])                      # ST-LINK micro-USB, underside
    m.cyl((35.0, 0.5, PCB_T + 3.2), (35.0, 9.0, PCB_T + 3.2), 3.1, C["gold"], 14)    # SMA
    m.cyl((35.0, 9.0, PCB_T + 3.2), (35.0, 22.0, PCB_T + 3.2), 4.0, C["plastic"], 14)
    for x, colour in ((44.0, "#3060FF"), (47.0, C["led"]), (50.0, "#E03030")):
        m.box(x, -10.0, PCB_T, x + 1.6, -10.8, PCB_T + 0.6, colour)
    label(m, "NUCLEO-WL55JC1", w / 2, 40.0, 2.2, C["ink"])
    label(m, name, w / 2, 44.5, 2.6, "#1F5FBF")
    return m


def model_wago(n):
    m = Mesh()
    w, h = b.SIZE[f"WAGO{n}"]
    m.box(0, 0, 0, w, -h, 8.0, C["wago"])
    for i in range(1, n + 1):
        x = (i - 0.5) * w / n
        m.box(x - w / n / 2 + 0.6, -6.0, 8.0, x + w / n / 2 - 0.6, -h + 1.0, 10.5, C["lever"])
        m.box(x - 1.0, 0.02, 2.5, x + 1.0, -0.2, 5.0, C["plastic"])
    return m


def model_pack():
    m = Mesh()
    w, h = b.SIZE["PACK"]
    m.box(0, 0, 0, w, -h, 18.0, C["pack"])
    m.box(6, -12, 18.0, w - 6, -h + 12, 18.05, "#D8D8D8")
    m.text("LIPO 3.7V 6600MAH", w / 2, -h / 2 - 1.0, 18.1, 3.0, C["ink"], "center")
    return m


def model_usbf():
    m = Mesh()
    w, h = b.SIZE["USBF"]
    pcb(m, w, h, C["pcb_ada"])
    m.box(w / 2 - 4.5 - 0.2, 0.8, PCB_T, w / 2 + 4.5 - 0.2, -7.0, PCB_T + 3.2, C["metal"])
    label(m, "USB-C #4090", w / 2, 11.0, 1.4)
    return m


def model_usbm():
    m = Mesh()
    w, h = b.SIZE["USBM"]
    pcb(m, w, h, C["pcb_ada"])
    m.box(w / 2 - 4.2, 6.6, PCB_T - 0.2, w / 2 + 4.2, 0, PCB_T + 2.4, C["metal"])
    m.box(w / 2 - 5.0, 0, PCB_T - 0.6, w / 2 + 5.0, -4.0, PCB_T + 3.6, C["plastic"])
    label(m, "#5978", w / 2, 8.5, 1.4)
    return m


def model_barrel(plug):
    m = Mesh()
    w, h = b.SIZE["BARREL"]
    m.box(0, 0, 0, 10.0, -h, 10.0, C["term"])
    for y in (4.0, 11.0):
        m.cyl((5.0, -y, 10.0), (5.0, -y, 10.05), 1.6, C["metal"], 12)
    m.cyl((10.0, -h / 2, 5.5), (w, -h / 2, 5.5), 5.0, C["plastic"], 18)
    if plug:
        m.cyl((w, -h / 2, 5.5), (w + 9.5, -h / 2, 5.5), 2.75, C["metal"], 16)
    else:
        m.cyl((w - 0.02, -h / 2, 5.5), (w + 0.01, -h / 2, 5.5), 3.0, "#000000", 16)
    return m


def model_loadr():
    """The 50 W aluminium-housed test load: finned housing, two corner tabs, solder terminals at the ends."""
    m = Mesh()
    w, h = b.SIZE["LOADR"]
    m.box(6.0, -7.5, 0, 56.0, -h + 7.5, 15.0, "#D9A62E")                 # the 50 x 15 x 15 housing
    for x0, y0 in ((6.0, -h + 7.5), (46.0, 0.0)):                         # corner tabs, 7.5 mm out
        m.box(x0, y0, 0, x0 + 10.0, y0 - 7.5, 2.0, "#D9A62E")
    for x0, x1 in ((0.0, 6.0), (56.0, 62.0)):
        m.cyl((x0, -h / 2, 7.5), (x1, -h / 2, 7.5), 0.8, C["metal"], 10)
    m.text("50W 100R", w / 2, -h / 2 - 1.0, 15.1, 3.0, C["ink"], "center")
    return m


def model_qt(name, hub=False):
    m = Mesh()
    w, h = b.SIZE["QT"]
    pcb(m, w, h, C["pcb_ada"], holes=((2.54, 2.54), (22.86, 2.54)), standoff=QT_Z)
    if hub:
        for i in range(1, 6):
            x = b.LOCAL["QT"][f"P{i}.GND"][0]
            m.box(x - 2.0, -h + 4.25, PCB_T, x + 2.0, -h - 0.2, PCB_T + 2.9, C["jst"])
    else:
        qt_socket(m, 0, 8.89, "left")
        qt_socket(m, w, 8.89, "right")
        m.box(w / 2 - 1.5, -7.5, PCB_T, w / 2 + 1.5, -10.5, PCB_T + 0.9, C["chip"])
    label(m, name, w / 2, 14.5, 1.8)
    return m


def model_shunt():
    m = Mesh()
    m.box(-1.25, 1.25, 0, 1.25 + b.P, -1.25, 6.0, C["shunt"])
    return m


# ------------------------------------------------------------------ wires (plate frame, model y = -plate y)
DUPONT_COLOUR = {"3V3": "#D42020", "GND": "#202020", "SDA": "#2060D0", "SCL": "#E0C020", "analog": "#2EA043",
                 "digital": "#F07820", "spi": "#8E44AD"}
BOJACK = {1: "#9A9A9A", 2: "#C8102E", 3: "#F07820", 4: "#E8C820", 5: "#2EA043", 6: "#2060D0", 7: "#8E44AD",
          8: "#808080", 9: "#F0F0F0", 10: "#202020", 20: "#C8102E", 30: "#F07820", 40: "#E8C820", 50: "#2EA043"}
FORCE_COLOUR = {"+": "#D42020", "-": "#202020"}
NUC_Z = 10.0               # NUCLEO PCB underside on M3 standoffs
QT_Z = 6.0                 # QT boards on M2.5 standoffs
Z_BASE = {"seated": SEAT_Z, "A1": NUC_Z, "A2": NUC_Z, "U8": QT_Z, "U9": QT_Z, "U10": QT_Z, "U11": QT_Z,
          "U12": QT_Z, "J3": 6.0, "J4": 0.0, "WG1": 0.0, "WG2": 0.0, "WG3": 0.0, "BT1": 0.0}


def base_z(ref):
    pl = b.PLACE[ref]
    if "seat" in pl:
        return SEAT_Z
    if ref == "P1":
        return SEAT_Z + PCB_T + 1.6 - 1.0
    if ref == "P2":
        return SEAT_Z + PCB_T + 6.0 - 5.5
    return Z_BASE.get(ref, 0.0)


EXT_XY = {"PS1": (-25.0, b.pin_xy(("J3", "IN.VBUS"))[1], 10.0), "PV1": (-25.0, b.pin_xy(("J4", "IN.+"))[1], 5.5),
          "M1": (None, b.PLATE_H + 30, 8.0), "M2": (None, b.PLATE_H + 30, 8.0)}


def end_xyz(end):
    """3D point where a conductor meets this end (model frame: x, -y, z)."""
    if isinstance(end, str):
        x, y = b.pin_xy(end)
        return (x, -y, b.BB_Z)
    ref, pin = end
    xy = b.pin_xy(end)
    if end in b.ON_BB and ref not in b.PLACE:
        return (xy[0], -xy[1], b.BB_Z)
    if ref == "BT1":
        return (xy[0], -xy[1], 4.0)
    if ref in ("WG1", "WG2", "WG3"):
        return (xy[0], -xy[1], 3.7)
    if ref in ("A1", "A2"):
        if pin.startswith(("CN7", "CN10")):
            return (xy[0], -xy[1], NUC_Z + PCB_T + 8.5 + 7.0)
        if pin.startswith("USB"):
            return (xy[0], -xy[1], NUC_Z - 1.5)
        return (xy[0], -xy[1], NUC_Z + PCB_T + 8.5)
    if ref == "U1":
        return (xy[0], -xy[1], SEAT_Z + PCB_T + 3.0)
    if ref in ("U2", "U3", "U4", "U5") and pin.startswith("X1"):
        return (xy[0], -xy[1] - 1.5, SEAT_Z + PCB_T + 3.0)
    if ref in ("J3", "J4", "P1", "P2"):
        return (xy[0], -xy[1], base_z(ref) + (3.0 if ref in ("J3", "P1") else 9.0))
    if xy is None:
        return None
    return (xy[0], -xy[1], base_z(ref) + PCB_T + 1.5)


def arc(p0, p1, lift, n=18):
    mid = [(p0[i] + p1[i]) / 2 for i in range(3)]
    mid[2] = max(p0[2], p1[2]) + lift
    pts = []
    for k in range(n + 1):
        t = k / n
        pts.append(tuple((1 - t) ** 2 * p0[i] + 2 * (1 - t) * t * mid[i] + t * t * p1[i] for i in range(3)))
    return pts


def dupont_colour(note, a, b_):
    n = note.lower()
    if "3v3" in n:
        return DUPONT_COLOUR["3V3"]
    if "gnd" in n or "ground" in n:
        return DUPONT_COLOUR["GND"]
    if "sda" in n:
        return DUPONT_COLOUR["SDA"]
    if "scl" in n:
        return DUPONT_COLOUR["SCL"]
    if "oled" in n:
        return DUPONT_COLOUR["spi"]
    if any(k in n for k in ("sense", "iset", "vane", "rain", "a0", "a2")):
        return DUPONT_COLOUR["analog"]
    return DUPONT_COLOUR["digital"]


def housing(m, p, up=True):
    x, y, z = p
    m.box(x - 1.25, y - 1.25, z, x + 1.25, y + 1.25, z + (14.0 if up else 0.5), C["plastic"])


def wires_model(keep=lambda c: True, extras=True):
    """Every drawn conductor that keep() accepts; extras adds the off-breadboard leads (whole plate only)."""
    m = Mesh()
    ext_ends = {}                                     # one drawn cable per outside cable, from the middle of its pins
    for c in b.CONDUCTORS:
        if c[0] == "cable" and keep(c):
            for e, other in ((c[1], c[2]), (c[2], c[1])):
                if isinstance(e, tuple) and e[0] in EXT_XY and end_xyz(e) is None and end_xyz(other) is not None:
                    ext_ends.setdefault(e[0], []).append(end_xyz(other))
    for ref, pts in ext_ends.items():
        known = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
        ex, ey, ez = EXT_XY[ref]
        m.tube(arc(known, (known[0] if ex is None else ex, -ey, ez), 4.0, 8), 1.9, "#303030")
    for c in b.CONDUCTORS:
        kind, e1, e2, note = c
        if kind in ("mate", "dupont", "reg") or not keep(c):
            continue                                  # Duponts and the regulator lead are routed: draw_routes()
        p1, p2 = end_xyz(e1), end_xyz(e2)
        ext = None
        for e, p in ((e1, p1), (e2, p2)):
            if p is None and isinstance(e, tuple) and e[0] in EXT_XY:
                ext = e
        if kind == "jumper":
            s = b.span(e1, e2)
            col = BOJACK.get(s, "#F07820")
            z = b.BB_Z + 0.45
            for p in (p1, p2):
                m.cyl((p[0], p[1], b.BB_Z - 1.5), (p[0], p[1], z), 0.3, C["gold"], 8)
            m.cyl((p1[0], p1[1], z), (p2[0], p2[1], z), 0.42, col, 10)
            continue
        if p1 is None or p2 is None:
            if kind == "cable" and ext:
                pass                                  # drawn once per cable, above
            elif kind == "cable" and ((e1[0] == "H1") or (e2[0] == "H1")):
                known = p2 if e1[0] == "H1" else p1
                far = (known[0] + 45.0, known[1] + 20.0, known[2])
                m.tube([known, (known[0] + 12.0, known[1], known[2]), far], 1.6, "#303030")
            continue
        if kind == "dupont":
            col = dupont_colour(note, e1, e2)
            q1 = (p1[0], p1[1], p1[2] + (14.0 if isinstance(e1, str) else 0.0))
            q2 = (p2[0], p2[1], p2[2] + (14.0 if isinstance(e2, str) else 0.0))
            for e, p in ((e1, p1), (e2, p2)):
                housing(m, (p[0], p[1], p[2] if isinstance(e, str) else p[2] - 14.0))
                if isinstance(e, str):
                    m.cyl((p[0], p[1], b.BB_Z - 2.0), (p[0], p[1], b.BB_Z), 0.32, C["gold"], 8)
            m.tube(arc(q1, q2, 10.0 + 0.08 * math.dist(q1, q2)), 0.65, col)
        elif kind == "qt":
            if e1[0] in ("W2", "W3") or not e1[1].endswith(".GND"):
                continue                              # one cable per four-wire connection; W2/W3 are routed
            if p1 is None or p2 is None:
                continue
            qt_cable(m, arc(p1, p2, 12.0 + 0.05 * math.dist(p1, p2)))
        elif kind in ("force", "pigtail", "solder", "sense", "reg", "lead"):
            neg = any(t in (e1[1] if isinstance(e1, tuple) else "") + (e2[1] if isinstance(e2, tuple) else "")
                      for t in ("-", "GND")) and "VIN-" not in str(e1) + str(e2)
            neg = neg or note.lower().startswith(("the ground tie",)) or "black" in note
            col = "#202020" if neg else ("#D42020" if kind in ("force", "pigtail", "solder") else
                                         {"sense": "#8E44AD", "reg": "#F07820", "lead": "#2EA043"}[kind])
            r = {"force": 0.85, "pigtail": 0.6, "solder": 0.7, "sense": 0.45, "reg": 0.5, "lead": 0.5}[kind]
            pts = arc(p1, p2, 6.0 + 0.06 * math.dist(p1, p2))
            if isinstance(e2, str):
                pts.append((p2[0], p2[1], b.BB_Z - 2.0))
            m.tube(pts, r, col)
    if not extras:
        return m
    # the pack's own lead and the NTC leads
    pk = (b.outline("BT1")[0], -(b.outline("BT1")[1] + 40.0), 6.0)
    for pin, col in (("+", "#D42020"), ("-", "#202020")):
        p = end_xyz(("BT1", pin))
        m.tube(arc(pk, p, 4.0, 10), 0.6, col)
        m.box(p[0] - 2.0, p[1] - 1.5, p[2] - 2.0, p[0] + 2.0, p[1] + 1.5, p[2] + 2.0, C["jst"])
    bead = (b.NTC_BEAD[0], -b.NTC_BEAD[1], 18.5)
    m.cyl((bead[0] - 1.5, bead[1], bead[2]), (bead[0] + 1.5, bead[1], bead[2]), 1.4, "#202020", 12)
    return m


QT_WIRES = (("GND", "#1A1A1A"), ("V+", "#D42020"), ("SDA", "#2060D0"), ("SCL", "#E8C820"))
ROUTE_COLOUR = {"reg": "#F07820", "lead": "#13A538"}


def offset_line(pts, off):
    """A 3D polyline moved sideways (in plan) by off mm."""
    out = []
    for k, p in enumerate(pts):
        a, c = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        dx, dy = c[0] - a[0], c[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        out.append((p[0] - dy / L * off, p[1] + dx / L * off, p[2]))
    return out


def qt_cable(m, pts):
    """STEMMA QT cable: four thin wires side by side, black, red, blue, yellow."""
    for k, (_s, col) in enumerate(QT_WIRES):
        m.tube(offset_line(pts, (k - 1.5) * 0.85), 0.42, col, 6)


_ROUTES = None


def routes():
    global _ROUTES
    if _ROUTES is None:
        rts, problems, pl = routing.route_all()
        if problems:
            sys.exit("routing problems:\n" + "\n".join(problems))
        _ROUTES = (rts, pl)
    return _ROUTES


def board_of(route):
    hs = [h for h in b.ALL_HOLES for e in route["ends"] if math.dist(b.pin_xy(h), e[:2]) < 0.05]
    return {h.split(":")[0] for h in hs}


def draw_routes(m, board=None):
    """The routed wires (routing.py), draped in 3D; board limits them to wires with an end on it."""
    rts, pl = routes()
    for key, rt in rts.items():
        if board and board not in board_of(rt):
            continue
        pts = [(x, -y, z) for x, y, z in routing.drape(pl, rt)]
        kind = rt["kind"]
        if kind == "dupont":
            k = int(key.split(":")[1])
            _kind, e1, e2, note = b.CONDUCTORS[k]
            m.tube(pts, routing.WIRE_R["dupont"], dupont_colour(note, e1, e2), 8)
            for e, end in ((e1, rt["ends"][0]), (e2, rt["ends"][1])):
                x, y, ztop = end[0], -end[1], end[2]
                housing(m, (x, y, ztop - 14.0))
                if isinstance(e, str):
                    m.cyl((x, y, b.BB_Z - 2.0), (x, y, b.BB_Z), 0.32, C["gold"], 8)
        elif kind == "qtcable":
            cable = key
            qt_cable(m, pts[6:])
            for k, (sig, col) in enumerate(QT_WIRES):          # four header pins, each on its own lead
                hx, hy = b.pin_xy(b.ON_BB[(cable, f"H.{sig}")])
                top = (hx, -hy, b.BB_Z + 14.0)
                housing(m, (hx, -hy, b.BB_Z))
                m.cyl((hx, -hy, b.BB_Z - 2.0), (hx, -hy, b.BB_Z), 0.32, C["gold"], 8)
                joint = offset_line(pts, (k - 1.5) * 0.85)[6]
                m.tube(arc((top[0], top[1], top[2] + 0.5), joint, 4.0, 10), 0.42, col, 6)
        else:
            col = ROUTE_COLOUR.get(kind) or ("#B03030" if key.endswith("1") else "#303030")
            hole = rt["ends"][1]
            m.tube(pts + [(hole[0], -hole[1], b.BB_Z - 2.0)], routing.WIRE_R[kind], col, 8)


# ------------------------------------------------------------------ the KiCad board file
def fp(ref, value, x, y, rot, models, fab=None, silk=None, lib="bench"):
    lines = [f'\t(footprint "{lib}:{value}"', '\t\t(layer "F.Cu")', f'\t\t(uuid "{uid("fp", ref)}")',
             f'\t\t(at {x:.4f} {y:.4f} {rot})',
             f'\t\t(property "Reference" "{ref}" (at {silk[0] if silk else 0} {silk[1] if silk else -1.5} {rot}) '
             f'(layer "F.SilkS") (uuid "{uid("ref", ref)}") (effects (font (size 2 2) (thickness 0.3)) (justify left)))',
             f'\t\t(property "Value" "{value}" (at 0 0 {rot}) (layer "F.Fab") (uuid "{uid("val", ref)}") '
             f'(effects (font (size 1 1) (thickness 0.15))))',
             '\t\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)']
    if fab:
        w, h = fab
        lines.append(f'\t\t(fp_rect (start 0 0) (end {w:.3f} {h:.3f}) (stroke (width 0.15) (type solid)) '
                     f'(fill none) (layer "F.Fab") (uuid "{uid("fab", ref)}"))')
    for path, off, mrot in models:
        lines.append(f'\t\t(model "{path}" (offset (xyz {off[0]:.4f} {off[1]:.4f} {off[2]:.4f})) '
                     f'(scale (xyz 1 1 1)) (rotate (xyz 0 0 {mrot})))')
    lines.append("\t)")
    return "\n".join(lines)


def silk_text(text, x, y, size, key):
    return (f'\t(gr_text "{text}" (at {x:.3f} {y:.3f} 0) (layer "F.SilkS") (uuid "{uid("txt", key)}") '
            f'(effects (font (size {size} {size}) (thickness {size * 0.15:.2f})) (justify left)))')


def board_file(path, footprints, texts, outline):
    x0, y0, x1, y1 = outline
    mask = "#3B3F45FF"                # dark grey base plate, so white boards stand out
    head = f"""(kicad_pcb
\t(version 20240108)
\t(generator "bench-r1-kicad_layout")
\t(generator_version "8.0")
\t(general (thickness 3) (legacy_teardrops no))
\t(paper "A2")
\t(layers
\t\t(0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
\t\t(42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) (45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "#E6E6E6FF"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "{mask}") (thickness 2.93) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "#2A2A2AFF"))
\t\t\t(copper_finish "None")
\t\t\t(dielectric_constraints no)
\t\t)
\t\t(pad_to_mask_clearance 0)
\t)
\t(net 0 "")"""
    edge = (f'\t(gr_rect (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.3) (type default)) (fill none) '
            f'(layer "Edge.Cuts") (uuid "{uid("edge", path.name)}"))')
    path.write_text("\n".join([head] + footprints + texts + [edge, ")"]) + "\n")


def lib(name):
    return str(LIB3D / name)


def leaded_footprints(only_board=None):
    """Resistors, capacitors and link headers in breadboard holes, with KiCad's STEP models."""
    out = []
    refs = sorted({r for (r, _p) in b.ON_BB if r[0] in "RCJ" and r.startswith(("R", "C", "JP"))})
    for ref in refs:
        if ref in b.PLACE or ref == "RT1":       # RT1 is the NTC: its leads are drawn with the wires
            continue
        pins = {p: h for (r, p), h in b.ON_BB.items() if r == ref}
        first, second = ("+", "-") if "+" in pins else ("1", "2")
        h1, h2 = pins[first], pins[second]
        if only_board and not h1.startswith(only_board):
            continue
        (x1, y1), (x2, y2) = b.pin_xy(h1), b.pin_xy(h2)
        dx, dy = x2 - x1, y2 - y1
        rot = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[
            (round(dx / max(abs(dx), abs(dy))), round(dy / max(abs(dx), abs(dy))))]
        n = b.span(h1, h2)
        value = b.PART[ref]["value"]
        if ref.startswith("R"):
            step = {4: "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 3: "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"}[n]
            models = [(lib(f"Resistor_THT.3dshapes/{step}.step"), (0, 0, b.BB_Z), 0)]
        elif ref == "C1":
            models = [(lib("Capacitor_THT.3dshapes/CP_Radial_D6.3mm_P2.50mm.step"), (0, 0, b.BB_Z), 0)]
        elif ref.startswith("C"):
            step = {1: "C_Disc_D5.0mm_W2.5mm_P2.50mm", 2: "C_Disc_D5.0mm_W2.5mm_P5.00mm"}[n]
            models = [(lib(f"Capacitor_THT.3dshapes/{step}.step"), (0, 0, b.BB_Z), 0)]
        else:     # link header: pins along the footprint's +y, so turn it a further -90
            models = [(lib("Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Vertical.step"),
                       (0, 0, b.BB_Z), 90)]
            if ref == "JP2":
                models.append((str(M3D / "shunt.wrl"), (0, 0, b.BB_Z + 2.5), 0))
        out.append(fp(ref, value.replace('"', ""), x1, y1, rot, models, silk=(0, -2.5)))
    return out


MODEL_OF = {}


def module_models():
    """Write every module's VRML; return {ref: wrl path}."""
    M3D.mkdir(parents=True, exist_ok=True)
    made = {}

    def save(name, mesh):
        p = M3D / f"{name}.wrl"
        mesh.write(p)
        return str(p)

    names = {"U2": "0x40 BATT", "U3": "0x41 LOAD", "U4": "0x45 SOLAR", "U5": "0x48 USB-C"}
    for ref in ("U2", "U3", "U4", "U5"):
        made[ref] = save(f"ina228_{ref}", model_ina(names[ref]))
    made["U6"] = save("max17048", model_gauge())
    made["U1"] = save("bq24074_4755", model_chg())
    made["U7"] = save("s7v8f3", model_reg())
    made["J1"] = save("bob14021_wind", model_bob())
    made["J2"] = made["J1"]
    made["DS1"] = save("oled_2674", model_oled())
    made["A1"] = save("nucleo_tx", model_nucleo("TX"))
    made["A2"] = save("nucleo_rx", model_nucleo("RX"))
    made["WG1"] = save("wago_222_413", model_wago(3))
    made["WG2"] = made["WG3"] = save("wago_222_415", model_wago(5))
    made["BT1"] = save("pack_6600", model_pack())
    made["J3"] = save("usbc_4090", model_usbf())
    made["P1"] = save("usbc_plug_5978", model_usbm())
    made["J4"] = save("dc_jack_368", model_barrel(False))
    made["P2"] = save("dc_plug_369", model_barrel(True))
    made["R9"] = save("load_50w_100r", model_loadr())
    for ref, nm in (("U8", "QT HUB"), ("U9", "SHT45"), ("U10", "SHTC3"), ("U11", "BMP581"), ("U12", "LTR390")):
        made[ref] = save(f"qt_{ref}", model_qt(nm, hub=(ref == "U8")))
    save("shunt", model_shunt())
    return made


def write(render=False):
    fails, _notes = b.check()
    if fails:
        sys.exit("build.py fails its checks; fix them first:\n" + "\n".join(fails))
    OUT.mkdir(exist_ok=True)
    made = module_models()
    bb = M3D / "breadboard_elegoo_830.wrl"
    breadboard_model().write(bb)

    def board_fps(name):
        x, y = b.BOARDS[name]
        return fp(name, "Elegoo 830", x, y, 0, [(str(bb), (0, 0, 0), 0)], fab=(b.BB_W, b.BB_H), silk=(0, -2.0))

    def part_fp(ref):
        ox, oy = b.origin(ref)
        w, h = b.SIZE[b.PLACE[ref]["kind"]]
        return fp(ref, b.PART[ref]["value"].replace('"', ""), ox, oy, b.PLACE[ref]["rot"],
                  [(made[ref], (0, 0, base_z(ref)), 0)], fab=(w, h), silk=(0, -2.0))

    def texts(keys):
        out = []
        for name in keys:
            x, y = b.BOARDS[name]
            out.append(silk_text(f"{name}: {b.BOARD_ROLE[name]}", x + b.BB_W + 3 if name != "BB1" else x + b.BB_W + 3,
                                 y + b.BB_H - 3, 2.5, name))
        return out

    # the whole plate
    fps = [board_fps(n) for n in b.BOARDS] + [part_fp(r) for r in b.PLACE] + leaded_footprints()
    wires = M3D / "wires_all.wrl"
    wm = wires_model()
    draw_routes(wm)
    wm.write(wires)
    fps.append(fp("WIRES", "wires", 0, 0, 0, [(str(wires), (0, 0, 0), 0)]))
    board_file(OUT / "bench-r1.kicad_pcb", fps, [], (0, 0, b.PLATE_W, b.PLATE_H))
    files = [OUT / "bench-r1.kicad_pcb"]
    # one breadboard each, with what sits on it and the wires that start on it
    for name in b.BOARDS:
        x, y = b.BOARDS[name]
        on = [r for r, pl in b.PLACE.items() if ("seat" in pl and pl["seat"][1].startswith(name)) or
              ("mate" in pl and b.PLACE[pl["mate"][1][0]].get("seat", ("", ""))[1].startswith(name))]
        if name in ("BB1", "BB3"):
            on.append("A1")                   # the TX NUCLEO sits between them; their Duponts end on it
        fps = [board_fps(name)] + [part_fp(r) for r in on] + leaded_footprints(name)

        def keep(c, name=name):
            return any(isinstance(e, str) and e.startswith(name) for e in c[1:3])
        wpath = M3D / f"wires_{name}.wrl"
        wm = wires_model(keep, extras=False)
        draw_routes(wm, name)
        wm.write(wpath)
        fps.append(fp("WIRES", "wires", 0, 0, 0, [(str(wpath), (0, 0, 0), 0)]))
        top = min([y] + [b.outline(r)[1] for r in on]) - 4
        bot = max([y + b.BB_H] + [b.outline(r)[1] + b.outline(r)[3] for r in on]) + 4
        f = OUT / f"bench-r1-{name}.kicad_pcb"
        board_file(f, fps, [], (x - 4, top, x + b.BB_W + 4, bot))
        files.append(f)
    print("wrote", ", ".join(str(f.relative_to(b.HERE)) for f in files))
    if render:
        renders(files)


def renders(files):
    """High-quality renders; transparent background composited onto white."""
    from PIL import Image
    jobs = [(files[0], "plate-top.png", ["--side", "top", "--zoom", "1.05", "-w", "3600", "-h", "2700"]),
            (files[0], "plate-iso.png", ["--side", "top", "--rotate", "-45,0,20", "--perspective", "--zoom", "1.35",
                                         "-w", "3600", "-h", "2600"])]
    for f in files[1:]:
        name = f.stem.split("-")[-1]
        jobs.append((f, f"{name}-top.png", ["--side", "top", "-w", "3600", "-h", "2000"]))
        jobs.append((f, f"{name}-iso.png", ["--side", "top", "--rotate", "-40,0,10", "--perspective", "--zoom", "1.1",
                                            "-w", "3600", "-h", "2200"]))
    for f, png, args in jobs:
        out = OUT / png
        cmd = [KICAD_CLI, "pcb", "render", "--quality", "high", "--use-board-stackup-colors", "--background",
               "transparent", "-o", str(out)] + args + [str(f)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(png, f"FAILED: {r.stderr[-400:]}")
            continue
        im = Image.open(out).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        Image.alpha_composite(bg, im).convert("RGB").save(out)
        print(png, "ok")


if __name__ == "__main__":
    write(render="--render" in sys.argv)
