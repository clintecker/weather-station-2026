"""KiCad 10 renders of the stack, from layout/stack.py.

Each board is a KiCad PCB: the SolderFul outline (edge notches and centre-line holes, datasheet p.2), every
hole as a plated pad, and the row strips and rails as copper under a red mask. Parts are footprints with 3D
models: KiCad's own STEP models where the library has the part (Sullins-style 1x8 socket, 0.1 in headers
under the breakouts, the right-angle SWD header, the vertical 10k resistors, the 100 nF discs); every other
part is a generated VRML of labelled boxes built from the same Box list the layout checks use, so a render
can never show a part where the checks did not. Wires are tubes between their holes.

Writes render/kicad/tx-stack-B1..B4.kicad_pcb and tx-stack-all.kicad_pcb (all four boards on M3 standoffs at
the layout's gaps) and renders PNGs into ../renders/. Run: python3 kicad_render.py [--no-render]
"""
import math
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import layout_checks as lc  # noqa: E402
import stack as st  # noqa: E402
from stack import S  # noqa: E402

OUT = HERE / "kicad"
M3D = OUT / "3d"
PNG = HERE.parent / "renders"
KICAD_CLI = "kicad-cli"
WRL = 1 / 2.54                      # KiCad reads VRML in units of 0.1 inch
T = st.BT
HDR, PCB = st.HDR, st.PCB


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "tx-stack-r1/" + "/".join(map(str, parts))))


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# ------------------------------------------------------------------ stroke font (y up, cell 4 x 6)
# (same glyph set as hardware/bench-breadboard-r1/layout/kicad_layout.py; copied so this tree stands alone)
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
    "+": [[(0, 3), (4, 3)], [(2, 1), (2, 5)]], "-": [[(0, 3), (4, 3)]], ".": [[(2, 0), (2, 0.6)]],
    "/": [[(0, 0), (4, 6)]], " ": [], "#": [[(1, 0), (1, 6)], [(3, 0), (3, 6)], [(0, 2), (4, 2)], [(0, 4), (4, 4)]],
}


class Mesh:
    """VRML mesh in the board frame (X right, Y back from the front edge, Z up from the board top), mm."""

    def __init__(self):
        self.parts = {}

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

    def disc(self, x, y, z, r, colour, n=12):
        pts = [(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n), z) for k in range(n)]
        self._add(colour, pts, [list(range(n))])

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

    def text(self, s, x, y, z, h, colour, anchor="center"):
        u = h / 6
        w = 0.13 * h
        adv = 6 * u
        total = len(s) * adv - 2 * u
        if anchor == "center":
            x -= total / 2
        for i, ch in enumerate(s):
            for stroke in FONT.get(ch, FONT.get(ch.upper(), [])):
                for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                    self._seg((x + i * adv + ax * u, y + ay * u), (x + i * adv + bx * u, y + by * u), w, z, colour)

    def _seg(self, p0, p1, w, z, colour):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            dx, dy, L = 0.0, 1e-3, 1e-3
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        ex, ey = dx / L * w / 2, dy / L * w / 2
        pts = [(p0[0] + nx - ex, p0[1] + ny - ey, z), (p1[0] + nx + ex, p1[1] + ny + ey, z),
               (p1[0] - nx + ex, p1[1] - ny + ey, z), (p0[0] - nx - ex, p0[1] - ny - ey, z)]
        self._add(colour, pts, [[3, 2, 1, 0]])

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


# ------------------------------------------------------------------ colours of the labelled boxes
def box_colour(what, fp_colour):
    w = what.lower()
    for key, c in (("keep", None), ("foam", "#8C8C8C"), ("header plastic", "#151515"), ("jack", "#1E1E1E"),
                   ("module", "#B8BCC2"), ("sma", "#D4AF37"), ("usb-c", "#B8BCC2"), ("qt socket", "#EDE6D6"),
                   ("jst ph", "#EDE6D6"), ("mf-r010", "#E8A317"), ("resistor", "#C9B48A"), ("capacitor", "#3060C0"),
                   ("inductor", "#2A2A2A"), ("button", "#444444"), ("socket", "#151515"), ("swd", "#151515"),
                   ("qt lead", "#151515"), ("bus pins", "#D4AF37"), ("pad leads", "#B03030")):
        if key in w:
            return c
    return fp_colour


# parts drawn by KiCad library STEP models; the VRML skips their boxes
def lib(name):
    return "${KICAD10_3DMODEL_DIR}/" + name


def step_models(pl):
    """[(step path, (x, y) board frame of the model origin, kicad rotation, z offset)] for one placement."""
    ref, fpn = pl["ref"], pl["fp"]
    pins = st.pins_of(pl)

    def rot_of(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]           # board frame, y up; KiCad screen y is down
        sx, sy = round(dx / max(abs(dx), abs(dy), 1e-9)), round(-dy / max(abs(dx), abs(dy), 1e-9))
        return {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[(sx, sy)]

    if fpn == "SOCKET":
        return [(lib("Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x08_P2.54mm_Vertical.step"), pins["1"],
                 rot_of(pins["1"], pins["2"]), 0.0)], ("PPPC081",)
    if fpn == "SWD":
        return [(lib("Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x05_P2.54mm_Horizontal.step"), pins["1"],
                 rot_of(pins["1"], pins["2"]), 0.0)], ("SWD",)
    if fpn == "RV":
        return [(lib("Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P5.08mm_Vertical.step"), pins["2"],
                 rot_of(pins["2"], pins["1"]), 0.0)], ("resistor",)
    if fpn == "CAP":
        return [(lib("Capacitor_THT.3dshapes/C_Disc_D3.8mm_W2.6mm_P2.50mm.step"), pins["1"],
                 rot_of(pins["1"], pins["2"]), 0.0)], ("capacitor",)
    # 0.1 in male headers under the breakouts and the mini (contiguous rows only)
    rows = {"BOB": [[str(i) for i in range(1, 7)]], "SHTC3": [["VIN", "3V", "GND", "SCL", "SDA"]],
            "MAX": [["H.VIN", "H.GND", "H.SCL", "H.SDA", "H.INT", "H.QST"]], "INA": [["H.VIN", "H.GND", "H.SCL", "H.SDA"]],
            "REG": [["VOUT", "GND", "VIN", "SHDN"]],
            "MINI": [[f"B{k}" for k in range(1, 13)], [f"D{k}" for k in range(12, 0, -1)]]}
    out = []
    for row in rows.get(fpn, []):
        n = len(row)
        out.append((lib(f"Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x{n:02d}_P2.54mm_Vertical.step"),
                    pins[row[0]], rot_of(pins[row[0]], pins[row[1]]), 0.0))
    if fpn == "INA":                                    # the ALERT pin keeps a 1x1 piece
        out.append((lib("Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x01_P2.54mm_Vertical.step"), pins["H.ALRT"], 0, 0.0))
    return out, (("header plastic",) if out else ())


# ------------------------------------------------------------------ one board's VRML (parts, wires, labels)
def board_mesh(b, dz=0.0, m=None, slab=False, stubs=True):
    m = m or Mesh()
    if slab:                       # boards above the KiCad board are drawn as VRML slabs with their holes
        m.box(0, 0, dz - T, st.BW, st.BH, dz, "#B3202A")
        for h in st.ALL_HOLES:
            x, y = st.hole_xy(h)
            m.disc(x, y, dz + 0.02, 0.55, "#1A1A1A", 8)
            m.disc(x, y, dz - T - 0.02, 0.55, "#1A1A1A", 8)
        for x, y in st.MHOLES:
            m.disc(x, y, dz + 0.03, 1.5, "#F0F0F0", 16)
    for bb, pl in st.placements():
        if bb != b:
            continue
        f = st.FP[pl["fp"]]
        _models, skip = step_models(pl)
        top, label_at = -99, None
        for bx in st.boxes_of(pl):
            if bx.keepout or any(s.lower() in bx.what.lower() for s in skip):
                continue
            c = box_colour(bx.what, f["colour"])
            if c is None:
                continue
            m.box(bx.x0, bx.y0, dz + bx.z0, bx.x1, bx.y1, dz + bx.z1, c)
            area = (bx.x1 - bx.x0) * (bx.y1 - bx.y0)
            if "pcb" in bx.what.lower() or (label_at is None and area > 20):
                label_at = bx
            top = max(top, bx.z1)
        for pin, (x, y) in st.pins_of(pl).items():          # pin stubs below the board (solder tails)
            m.cyl((x, y, dz - T - 1.2), (x, y, dz), 0.32, "#C9C9C9", 6)
        for pad, (x, y) in st.pads_of(pl).items():
            m.disc(x, y, dz + (label_at.z1 if label_at else 0) + 0.05, 0.9, "#D4AF37", 10)
        if label_at is not None:
            x0, y0, x1, y1 = label_at.x0, label_at.y0, label_at.x1, label_at.y1
            part = next(p for p in st.model.PARTS if p["ref"] == pl["ref"])
            name = f'{pl["ref"]} {part["value"]}'.upper()
            h = min(2.2, (x1 - x0) / max(len(name), 1) * 0.9, (y1 - y0) / 3)
            if h > 0.9:
                m.text(name, (x0 + x1) / 2, (y0 + y1) / 2 - h / 2, dz + top + 0.06, h, "#FFFFFF")
            else:
                m.text(pl["ref"], (x0 + x1) / 2, (y0 + y1) / 2 - 0.6, dz + top + 0.06, 1.2, "#FFFFFF")
    # wires and jumpers that start and end on this board
    for kind, a, c, side, note in st.WIRES:
        ea, ec = end3(a, b, dz), end3(c, b, dz)
        if ea and ec:
            col = wire_colour(note)
            if side == "bottom":
                z = dz - T - 0.8
                pts = [(ea[0], ea[1], dz - T), (ea[0], ea[1], z), (ec[0], ec[1], z), (ec[0], ec[1], dz - T)]
            else:
                lift = 1.2 if kind == "jumper" else 2.5
                za, zc = ea[2], ec[2]
                pts = [(ea[0], ea[1], za), (ea[0], ea[1], max(za, zc) + lift), (ec[0], ec[1], max(za, zc) + lift),
                       (ec[0], ec[1], zc)]
            m.tube(pts, 0.35 if kind == "jumper" else 0.45, col, 6)
        elif stubs and (ea or ec) and isinstance(a, str) and isinstance(c, str):
            e = ea or ec
            other = c if ea else a
            up = st.BOARDS.index(other.split(":")[0]) > st.BOARDS.index(b)
            m.tube([(e[0], e[1], e[2]), (e[0], e[1], e[2] + (6 if up else -T - 5))], 0.45, wire_colour(note), 6)
    return m


def end3(e, b, dz):
    """3D point of a conductor end on board b, or None."""
    if isinstance(e, str):
        bb, h = e.split(":")
        if bb != b:
            return None
        x, y = st.hole_xy(h)
        return (x, y, dz)
    for bb, pl in st.placements():
        if pl["ref"] == e[0] and bb == b and e[1] in st.pads_of(pl):
            x, y = st.pads_of(pl)[e[1]]
            zt = max(bx.z1 for bx in st.boxes_of(pl) if "PCB" in bx.what)
            return (x, y, dz + zt)
    return None


def wire_colour(note):
    n = note.upper()
    for key, c in (("3V3", "#D62728"), ("VIN", "#D62728"), ("VOUT", "#D62728"), ("GND", "#1A1A1A"),
                   ("SCL", "#D4A017"), ("SDA", "#1F5FBF"), ("RST", "#8E44AD"), ("CUPS", "#2CA02C"),
                   ("VANE", "#17A589"), ("RAIN", "#00A3D9"), ("SYS", "#E67E22")):
        if key in n:
            return c
    return "#606060"


# ------------------------------------------------------------------ the KiCad board file
def outline_poly():
    """SolderFul outline with the half-hole notches (datasheet p.2), clockwise in KiCad coordinates."""
    r = S.val("sb_mhole") / 2
    W, H = st.BW, st.BH
    pts = []

    def notch(cx, cy, a0, a1, n=10):
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    ends = sorted({x for x, y in st.NOTCHES if y == 0})
    sides = sorted({y for x, y in st.NOTCHES if x == 0})
    # KiCad y = H - Y. Walk: top edge (back, Y = H) left to right, right side down, bottom (front) right to left, left up.
    pts.append((0, 0))
    for x in ends:
        notch(x, 0, 180, 0)          # notch dips into the board (KiCad +y)
    pts.append((W, 0))
    for Y in sorted(sides, reverse=True):
        notch(W, H - Y, 270, 90)
    pts.append((W, H))
    for x in sorted(ends, reverse=True):
        notch(x, H, 0, -180)
    pts.append((0, H))
    for Y in sides:
        notch(0, H - Y, 90, -90)
    return pts


def strips_copper():
    out = []
    hw = 0.9
    for row in range(1, 31):
        for c0, c1 in (("a", "e"), ("f", "j")):
            (x, y0), (_x, y1) = st.hole_xy(f"{c0}{row}"), st.hole_xy(f"{c1}{row}")
            out.append((x - hw, y0 - hw, x + hw, y1 + hw))
    for rail in st.RAIL_Y:
        (x0, y), (x1, _y) = st.hole_xy(f"{rail}1"), st.hole_xy(f"{rail}30")
        out.append((x0 - hw, y - hw, x1 + hw, y + hw))
    return out


def fp_text(ref, value, x, y, rot, models, layer="F.Cu"):
    lines = [f'\t(footprint "stack:{value}"', f'\t\t(layer "{layer}")', f'\t\t(uuid "{uid("fp", ref, x, y)}")',
             f'\t\t(at {x:.4f} {y:.4f} {rot})',
             f'\t\t(property "Reference" "{ref}" (at 0 -1.5 {rot}) (layer "F.Fab") (uuid "{uid("ref", ref, x, y)}") '
             f'(effects (font (size 1 1) (thickness 0.15))))',
             f'\t\t(property "Value" "{value}" (at 0 0 {rot}) (layer "F.Fab") (uuid "{uid("val", ref, x, y)}") '
             f'(effects (font (size 1 1) (thickness 0.15))))',
             '\t\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)']
    for path, off, mrot in models:
        lines.append(f'\t\t(model "{path}" (offset (xyz {off[0]:.4f} {off[1]:.4f} {off[2]:.4f})) '
                     f'(scale (xyz 1 1 1)) (rotate (xyz 0 0 {mrot})))')
    lines.append("\t)")
    return "\n".join(lines)


def grid_fp():
    """Every hole as a plated pad (1.0 mm drill) in one footprint at the board origin."""
    lines = ['\t(footprint "stack:SOLDERBREAD02_holes"', '\t\t(layer "F.Cu")', f'\t\t(uuid "{uid("grid")}")',
             '\t\t(at 0 0)', '\t\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)']
    for i, h in enumerate(st.ALL_HOLES):
        x, y = st.hole_xy(h)
        lines.append(f'\t\t(pad "{i + 1}" thru_hole circle (at {x:.4f} {st.BH - y:.4f}) (size 1.9 1.9) '
                     f'(drill {S.val("sb_hole"):g}) (layers "*.Cu" "*.Mask") (uuid "{uid("pad", h)}"))')
    for x, y in st.MHOLES:
        lines.append(f'\t\t(pad "" np_thru_hole circle (at {x:.4f} {st.BH - y:.4f}) (size {S.val("sb_mhole"):g} '
                     f'{S.val("sb_mhole"):g}) (drill {S.val("sb_mhole"):g}) (layers "*.Cu" "*.Mask") (uuid "{uid("mh", x)}"))')
    lines.append("\t)")
    return "\n".join(lines)


def board_file(path, footprints, extent):
    mask = "#B3202AFF"
    head = f"""(kicad_pcb
\t(version 20240108)
\t(generator "tx-stack-r1-kicad_render")
\t(generator_version "8.0")
\t(general (thickness {T}) (legacy_teardrops no))
\t(paper "A3")
\t(layers
\t\t(0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
\t\t(42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) (45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "#F0F0F0FF"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "#C8B98AFF") (thickness {T - 0.09:.2f}) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "#F0F0F0FF"))
\t\t\t(copper_finish "HAL SnPb")
\t\t\t(dielectric_constraints no)
\t\t)
\t\t(pad_to_mask_clearance 0)
\t)
\t(net 0 "")"""
    poly = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in outline_poly())
    edge = [f'\t(gr_poly (pts {poly}) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts") '
            f'(uuid "{uid("edge", path.name)}"))']
    cu = []
    for i, (x0, y0, x1, y1) in enumerate(strips_copper()):
        for layer in ("F.Cu", "B.Cu"):
            cu.append(f'\t(gr_rect (start {x0:.4f} {st.BH - y1:.4f}) (end {x1:.4f} {st.BH - y0:.4f}) '
                      f'(stroke (width 0) (type solid)) (fill yes) (layer "{layer}") (uuid "{uid("cu", layer, i)}"))')
    texts = []
    for k, (s_, x, y) in enumerate(extent):
        texts.append(f'\t(gr_text "{s_}" (at {x:.3f} {y:.3f} 0) (layer "F.SilkS") (uuid "{uid("txt", path.name, k)}") '
                     f'(effects (font (size 1.6 1.6) (thickness 0.25)) (justify left)))')
    path.write_text("\n".join([head, grid_fp()] + footprints + cu + edge + texts + [")"]) + "\n")


def part_footprints(b, dz=0.0):
    """KiCad STEP footprints for board b, model z raised by dz (stack render)."""
    out = []
    for bb, pl in st.placements():
        if bb != b:
            continue
        models, _skip = step_models(pl)
        for k, (path, (x, y), rot, z) in enumerate(models):
            # every STEP model sits on the board top; a breakout's PCB rests on its header's plastic
            out.append(fp_text(f"{pl['ref']}_{k}", Path(path).stem, x, st.BH - y, rot, [(path, (0, 0, dz + z), 0)]))
    return out


def standoffs_mesh(m, z_bot):
    r = st.STANDOFF_R
    for (lo, hi), gap in st.GAPS.items():
        za, zb = z_bot[lo], z_bot[hi] - T
        for _n, x, y in st.STANDOFFS:
            m.cyl((x, y, za), (x, y, zb), r, "#C9A227", 6)
    for _n, x, y in st.STANDOFFS:                           # screws below B1 and above B4
        m.cyl((x, y, z_bot["B1"] - T - S.val("floor")), (x, y, z_bot["B1"] - T), r, "#C9A227", 6)
        m.cyl((x, y, z_bot["B4"]), (x, y, z_bot["B4"] + 2.0), 2.7, "#9A9A9A", 12)


def crossings_mesh(m, z_bot):
    """Leads between boards: bus wires and the B1 3V3 wire as straight tubes; QT leads from the mux to B1."""
    for kind, a, c, side, note in st.WIRES:
        if isinstance(a, str) and isinstance(c, str) and a.split(":")[0] != c.split(":")[0]:
            (ba, ha), (bc, hc) = a.split(":"), c.split(":")
            (xa, ya), (xc, yc) = st.hole_xy(ha), st.hole_xy(hc)
            m.tube([(xa, ya, z_bot[ba]), (xc, yc, z_bot[bc])], 0.45, wire_colour(note), 6)
    mux = next(pl for b, pl in st.placements() if pl["ref"] == "U4")
    chans = st.FP["MUX"]["chans"]
    for k in range(1, 5):
        lead = next(pl for b, pl in st.placements() if pl["ref"] == f"W1{k}")
        cx, cy = st.tf(mux["rot"], mux["x0"], mux["y0"], *chans[k - 1])
        zq = z_bot["B2"] + S.val("foam") + PCB + 1.4
        lx, ly = st.pins_of(lead)["H.GND"]
        top = z_bot["B1"] + S.val("qt_lead_h")
        m.tube([(cx, cy, zq), (cx, cy - 3, zq), (cx, cy - 5, zq - 6), (lx, ly, top + 3), (lx, ly, top)], 0.6, "#2A2A2A", 6)


# ------------------------------------------------------------------ writing and rendering
def write_all():
    lc.FAILS.clear()
    lc.run()
    if lc.FAILS:
        sys.exit("layout checks fail; fix them first:\n" + "\n".join(lc.FAILS))
    M3D.mkdir(parents=True, exist_ok=True)
    files = []
    for b in st.BOARDS:
        mesh = board_mesh(b)
        p = M3D / f"{b}.wrl"
        mesh.write(p)
        fps = part_footprints(b) + [fp_text(f"{b}_parts", f"{b}_parts", 0, st.BH, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0), 0)])]
        f = OUT / f"tx-stack-{b}.kicad_pcb"
        board_file(f, fps, [(f"{b} {st.ROLE[b]}  FRONT EDGE BELOW", 1, st.BH + 3.5)])
        files.append(f)
    # the stack: B1 is the KiCad board, B2..B4 are slabs at their heights (z of each board's top face)
    z_bot = {"B1": 0.0}
    for (lo, hi), gap in st.GAPS.items():
        z_bot[hi] = z_bot[lo] + gap + T
    mesh = Mesh()
    for b in st.BOARDS:
        board_mesh(b, z_bot[b], mesh, slab=(b != "B1"), stubs=False)
    standoffs_mesh(mesh, z_bot)
    crossings_mesh(mesh, z_bot)
    p = M3D / "stack.wrl"
    mesh.write(p)
    fps = []
    for b in st.BOARDS:
        fps += part_footprints(b, z_bot[b])
    fps.append(fp_text("stack_parts", "stack_parts", 0, st.BH, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0), 0)]))
    f = OUT / "tx-stack-all.kicad_pcb"
    board_file(f, fps, [])
    files.append(f)
    print("wrote", ", ".join(str(x.relative_to(HERE)) for x in files))
    return files


def render(files):
    from PIL import Image
    PNG.mkdir(exist_ok=True)
    jobs = []
    for f in files[:-1]:
        b = f.stem.split("-")[-1]
        jobs.append((f, f"{b}-render-top.png", ["--side", "top", "--zoom", "0.95", "-w", "2400", "-h", "1600"]))
        jobs.append((f, f"{b}-render-iso.png", ["--side", "top", "--rotate", "-50,0,20", "--perspective",
                                                "--zoom", "0.9", "-w", "2400", "-h", "1700"]))
    jobs.append((files[-1], "stack-render-iso.png", ["--side", "top", "--rotate", "-65,0,25", "--perspective",
                                                     "--pivot", "0,0,3.5", "--pan", "1.0,2.0,3.5", "--zoom", "0.62",
                                                     "-w", "2400", "-h", "2200"]))
    jobs.append((files[-1], "stack-render-front.png", ["--side", "front", "--pan", "0,-3.5,0", "--zoom", "0.85",
                                                       "-w", "2400", "-h", "2200"]))
    ok = True
    only = [a for a in sys.argv[1:] if a.endswith('.png')]
    for f, png, args in jobs:
        if only and png not in only:
            continue
        out = PNG / png
        cmd = [KICAD_CLI, "pcb", "render", "--quality", "high", "--use-board-stackup-colors", "--background",
               "transparent", "-o", str(out)] + args + [str(f)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode or not out.exists():
            print(png, f"FAILED: {r.stderr[-400:]}")
            ok = False
            continue
        im = Image.open(out).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        Image.alpha_composite(bg, im).convert("RGB").save(out)
        print("rendered", png)
    return ok


if __name__ == "__main__":
    fs = write_all()
    if "--no-render" not in sys.argv and not render(fs):
        sys.exit(1)
