"""KiCad 10 renders of the four cards and of the cage assembly, from layout/stack.py and cage/cage.py.

Each card is a KiCad PCB: the SolderFul outline (edge notches and centre-line holes, datasheet p.2), every
hole as a plated pad, and the row strips and rails as copper under a red mask. Parts with a real 3D model are
footprints carrying it:
  - KiCad's own library: the lying resistors (DIN0207, 7.62 mm), the standing DO-35 diodes (band on the right
    lead), the 100 nF discs, the right-angle bus and SWD headers, the 0.1 in headers under the breakouts;
  - the makers' STEP files, fetched by fetch_models.py into render/models/ (not committed): Adafruit SHTC3,
    MAX17048 and INA228, Pololu S7V8F3.
Every other part (the stand-ins: the Wio-E5 mini, the jack breakouts, the PTC fuses, the lug) is a generated
VRML of the same boxes the layout checks use, so a render never shows a part where the checks did not. Wires
are tubes between their holes; a lead to a part off the card ends in a short stub.

The assembly is one KiCad board standing for the cage back plate (box inside width x height), with the cage,
the backplane, the cards and the power zone drawn as envelope boxes in the box frame. Each PNG carries a
legend that names its stand-ins.

Writes render/kicad/tx-stack-B1..B4.kicad_pcb and tx-stack-cage.kicad_pcb, and PNGs into ../renders/.
Run: python3 kicad_render.py [--no-render] [name.png ...]
"""
import math
import textwrap
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
sys.path.insert(0, str(HERE.parent / "cage"))
sys.path.insert(0, str(HERE))
import cage  # noqa: E402
import fetch_models  # noqa: E402
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
_NY, _NE = S.val("sb_notch_side_y"), S.val("sb_notch_end_span")
NOTCHES = [(0, _NY), (0, st.BH / 2), (0, st.BH - _NY), (st.BW, _NY), (st.BW, st.BH / 2), (st.BW, st.BH - _NY),
           (st.BW / 2 - _NE / 2, 0), (st.BW / 2 + _NE / 2, 0), (st.BW / 2 - _NE / 2, st.BH), (st.BW / 2 + _NE / 2, st.BH)]


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


# ------------------------------------------------------------------ which parts get a real model
def lib(name):
    return "${KICAD10_3DMODEL_DIR}/" + name


PART_VALUE = {p["ref"]: p["value"] for p in st.model.PARTS}
MAKER_SKIP = ("PCB", "QT socket", "JST PH", "inductor", "header plastic")   # boxes a maker's STEP replaces
STAND_IN = {
    "MINI": "Wio-E5 mini: boxes from its outline (no maker 3D model); its right-angle SMA adapter a box",
    "BOB": "jack breakouts (SparkFun BOB-14021 + Amphenol 87180): boxes from the fab outline, on the printed spacer",
    "PTC": "MF-R010 fuses: boxes (Bourns gives no 3D model)",
    "LUG": "battery lug E1 (Keystone 7328) on its nylon screw: a box",
}
GENERIC = {
    "RAH": "bus header: KiCad's generic 1x18 right-angle header (the Sullins part is the same pitch and pin line)",
    "RAS": "SWD header: KiCad's generic 1x5 right-angle header",
}


def _rot(a, b, base=0.0):
    """KiCad rotation (degrees, CCW seen from the top) taking a model axis at `base` degrees onto a -> b."""
    return round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) - base) % 360


def _runs(pins):
    """Split a breakout's header pins into straight runs at 2.54 mm (one header piece each)."""
    rows = {}
    for x, y in pins.values():
        rows.setdefault(round(y, 2), []).append((x, y))
    runs = []
    for row in rows.values():
        row.sort()
        cur = [row[0]]
        for p in row[1:]:
            if abs(p[0] - cur[-1][0] - st.P) < 0.05:
                cur.append(p)
            else:
                runs.append(cur)
                cur = [p]
        runs.append(cur)
    return runs


def step_models(pl):
    """([(model path, (x, y) card frame of the model origin, KiCad rotation, z offset)], skip-all, skip keys)."""
    kind, pins = pl["fp"], st.pins_of(pl)
    if kind == "RLY":
        return [(lib("Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal.step"), pins["1"],
                 _rot(pins["1"], pins["2"]), 0.0)], True, ()
    if kind == "DSTAND":
        span = "2.54" if math.dist(pins["1"], pins["2"]) < 3 else "5.08"
        # the body stands on lead 1. KiCad's pin 1 is the cathode: AnodeUp has its body on pin 1, CathodeUp on pin 2
        if PART_VALUE[pl["ref"]].startswith("BAT85"):        # lead 1 is the anode
            return [(lib(f"Diode_THT.3dshapes/D_DO-35_SOD27_P{span}mm_Vertical_CathodeUp.step"), pins["2"],
                     _rot(pins["2"], pins["1"]), 0.0)], True, ()
        return [(lib(f"Diode_THT.3dshapes/D_DO-35_SOD27_P{span}mm_Vertical_AnodeUp.step"), pins["1"],
                 _rot(pins["1"], pins["2"]), 0.0)], True, ()
    if kind == "CAP":
        return [(lib("Capacitor_THT.3dshapes/C_Disc_D3.8mm_W2.6mm_P2.50mm.step"), pins["1"],
                 _rot(pins["1"], pins["2"]), 0.0)], True, ()
    if kind in ("RAH", "RAS"):
        n = len(pins)
        path = lib(f"Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x{n:02d}_P2.54mm_Horizontal.step")
        # the model's pins run along -Y (board frame) from its origin, the mating ends point +X
        if kind == "RAH":                                     # mating ends toward the back (+Y)
            return [(path, pins["1"], 90, 0.0)], True, ()
        return [(path, pins[str(n)], 270, 0.0)], True, ()     # toward the front, origin at the last pin
    out, skip = [], ()
    if kind in ("SHTC3", "INA", "MAX", "REG", "MINI"):
        for run in _runs(pins):
            if len(run) == 1:
                out.append((lib("Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x01_P2.54mm_Vertical.step"), run[0], 0, 0.0))
            else:
                out.append((lib(f"Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x{len(run):02d}_P2.54mm_Vertical.step"),
                            run[0], _rot(run[0], run[1], -90), 0.0))
        skip = ("header plastic",)
    for mk, rot, x0, y0 in pl["step"]:
        p = fetch_models.path_of(mk)
        if p:
            out.append(("${KIPRJMOD}/../models/" + p.relative_to(fetch_models.MODELS).as_posix(), (x0, y0), rot, HDR))
            skip = MAKER_SKIP
    return out, False, skip


def legend_lines(kinds):
    lines = []
    for k in ("MINI", "BOB", "PTC", "LUG"):
        if k in kinds:
            lines.append("stand-in: " + STAND_IN[k])
    for k in ("SHTC3", "MAX", "INA", "REG"):
        if k in kinds:
            name = st.KIND[k][1]
            if fetch_models.path_of(k):
                note = "; it shows a terminal block that is not fitted" if k == "INA" else ""
                lines.append(f"{name}: maker's STEP ({fetch_models.SOURCES[k][3].split(';')[0]}){note}")
            else:
                lines.append(f"stand-in: {name}: boxes (model not fetched; run render/fetch_models.py)")
    for k in ("RAH", "RAS"):
        if k in kinds:
            lines.append(GENERIC[k])
    lines.append("wires are tubes; a lead to a part off this card ends in a short stub")
    return lines


# ------------------------------------------------------------------ colours
def box_colour(what, kind):
    w = what.lower()
    for key, c in (("spacer", "#E6E2D3"), ("header plastic", "#151515"), ("jack", "#1E1E1E"),
                   ("module", "#B8BCC2"), ("sma", "#D4AF37"), ("usb-c", "#B8BCC2"), ("qt socket", "#EDE6D6"),
                   ("jst ph", "#EDE6D6"), ("mf-r010", "#E8A317"), ("button", "#444444"), ("lug", "#D4AF37"),
                   ("screw", "#EDEDED"), ("battery leads", "#B03030"), ("inductor", "#2A2A2A")):
        if key in w:
            return c
    return st.KIND.get(kind, ("#8A8A8A",))[0]


def wire_colour(note):
    n = note.upper()
    for key, c in (("3.3 V", "#D62728"), ("BATTERY +", "#D62728"), ("PACK +", "#D62728"), ("LUG", "#D62728"),
                   ("SYS", "#E67E22"), ("GROUND", "#1A1A1A"), ("PACK -", "#1A1A1A"), ("CLOCK", "#D4A017"),
                   ("DATA", "#1F5FBF"), ("RESET", "#8E44AD"), ("CUPS", "#2CA02C"), ("VANE", "#17A589"),
                   ("RAIN", "#00A3D9"), ("THERMISTOR", "#7F7F7F"), ("SENSE", "#C2185B")):
        if key in n:
            return c
    return "#606060"


# ------------------------------------------------------------------ one card's VRML (stand-ins, wires, labels)
def top_of(pl):
    bx = [b for b in st.boxes_of(pl) if not b.keepout]
    pcb = [b.z1 for b in bx if "PCB" in b.what]
    return max(pcb) if pcb else max((b.z1 for b in bx), default=0.0)


def end3(e, b):
    """3D point of a conductor end on card b, or None (another card, the backplane or a part off the card)."""
    if isinstance(e, str):
        bb, h = e.split(":")
        return (*st.hole_xy(h), 0.0) if bb == b else None
    for bb, pl in st.placements():
        if bb == b and pl["ref"] == e[0] and e[1] in st.pads_of(pl):
            return (*st.pads_of(pl)[e[1]], top_of(pl))
    return None


def card_mesh(b):
    m = Mesh()
    kinds = set()
    for bb, pl in st.placements():
        if bb != b:
            continue
        kinds.add(pl["fp"])
        _models, skip_all, skip = step_models(pl)
        if skip_all:
            continue
        label_at, top = None, 0.0
        for bx in st.boxes_of(pl):
            if bx.keepout or any(k.lower() in bx.what.lower() for k in skip):
                continue
            m.box(bx.x0, bx.y0, bx.z0, bx.x1, bx.y1, bx.z1, box_colour(bx.what, pl["fp"]))
            if "sma" not in bx.what.lower():
                top = max(top, bx.z1)
            if "pcb" in bx.what.lower() or (label_at is None and (bx.x1 - bx.x0) * (bx.y1 - bx.y0) > 20):
                label_at = bx
        if pl["fp"] == "PTC":                                     # its two leads into the card
            for x, y in st.pins_of(pl).values():
                m.cyl((x, y, -T - 1.2), (x, y, 1.0), 0.3, "#C9C9C9", 6)
        for x, y in st.pads_of(pl).values():
            m.disc(x, y, top_of(pl) + 0.05, 0.9, "#D4AF37", 10)
        if label_at is not None and pl["fp"] not in ("PTC",):
            x0, y0, x1, y1 = label_at.x0, label_at.y0, label_at.x1, label_at.y1
            name = f'{pl["ref"]} {st.KIND[pl["fp"]][1]}'.upper()
            h = min(2.2, (x1 - x0) / max(len(name), 1) * 0.9, (y1 - y0) / 3)
            if h > 0.9:
                m.text(name, (x0 + x1) / 2, (y0 + y1) / 2 - h / 2, top + 0.06, h, "#FFFFFF")
            else:
                m.text(pl["ref"], (x0 + x1) / 2, (y0 + y1) / 2 - 0.6, top + 0.06, 1.2, "#FFFFFF")
    for kind, a, c, side, note in st.WIRES:
        ea, ec = end3(a, b), end3(c, b)
        col = wire_colour(note)
        if ea and ec:
            if side == "bottom":
                z = -T - 0.8
                pts = [(ea[0], ea[1], -T), (ea[0], ea[1], z), (ec[0], ec[1], z), (ec[0], ec[1], -T)]
            else:
                lift = 1.2 if kind == "jumper" else 2.5
                zt = max(ea[2], ec[2]) + lift
                pts = [ea, (ea[0], ea[1], zt), (ec[0], ec[1], zt), ec]
            m.tube(pts, 0.35 if kind == "jumper" else 0.45, col, 6)
        elif ea or ec:
            e = ea or ec
            m.tube([e, (e[0], e[1], e[2] + 6)], 0.45, col, 6)
    return m, kinds


# ------------------------------------------------------------------ the KiCad board files
def card_outline():
    """SolderFul outline with the half-hole notches (datasheet p.2), in KiCad coordinates (y down)."""
    r = S.val("sb_mhole") / 2
    W, H = st.BW, st.BH
    pts = []

    def notch(cx, cy, a0, a1, n=10):
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    ends = sorted({x for x, y in NOTCHES if y == 0})
    sides = sorted({y for x, y in NOTCHES if x == 0})
    pts.append((0, 0))
    for x in ends:
        notch(x, 0, 180, 0)
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
    out, hw = [], 0.9
    for row in range(1, 31):
        for c0, c1 in (("a", "e"), ("f", "j")):
            (x, y0), (_x, y1) = st.hole_xy(f"{c0}{row}"), st.hole_xy(f"{c1}{row}")
            out.append((x - hw, y0 - hw, x + hw, y1 + hw))
    for rail in st.RAIL_Y:
        (x0, y), (x1, _y) = st.hole_xy(f"{rail}1"), st.hole_xy(f"{rail}30")
        out.append((x0 - hw, y - hw, x1 + hw, y + hw))
    return out


def fp_text(ref, value, x, y, rot, models):
    lines = [f'\t(footprint "stack:{value}"', '\t\t(layer "F.Cu")', f'\t\t(uuid "{uid("fp", ref, x, y)}")',
             f'\t\t(at {x:.4f} {y:.4f} {rot})',
             f'\t\t(property "Reference" "{ref}" (at 0 -1.5 {rot}) (layer "F.Fab") (uuid "{uid("ref", ref, x, y)}") '
             f'(effects (font (size 1 1) (thickness 0.15))))',
             f'\t\t(property "Value" "{value}" (at 0 0 {rot}) (layer "F.Fab") (uuid "{uid("val", ref, x, y)}") '
             f'(effects (font (size 1 1) (thickness 0.15))))',
             '\t\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)']
    for path, off in models:
        lines.append(f'\t\t(model "{path}" (offset (xyz {off[0]:.4f} {off[1]:.4f} {off[2]:.4f})) '
                     f'(scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    lines.append("\t)")
    return "\n".join(lines)


def grid_fp():
    """Every SolderFul hole as a plated pad in one footprint at the board origin."""
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


def board_file(path, footprints, outline, thick, mask, copper=(), texts=(), height=st.BH):
    head = f"""(kicad_pcb
\t(version 20240108)
\t(generator "tx-stack-r1-kicad_render")
\t(generator_version "8.0")
\t(general (thickness {thick}) (legacy_teardrops no))
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
\t\t\t(layer "dielectric 1" (type "core") (color "#C8B98AFF") (thickness {thick - 0.09:.2f}) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
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
    poly = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in outline)
    edge = [f'\t(gr_poly (pts {poly}) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts") '
            f'(uuid "{uid("edge", path.name)}"))']
    cu = []
    for i, (x0, y0, x1, y1) in enumerate(copper):
        for layer in ("F.Cu", "B.Cu"):
            cu.append(f'\t(gr_rect (start {x0:.4f} {height - y1:.4f}) (end {x1:.4f} {height - y0:.4f}) '
                      f'(stroke (width 0) (type solid)) (fill yes) (layer "{layer}") (uuid "{uid("cu", layer, i)}"))')
    tx = [f'\t(gr_text "{s_}" (at {x:.3f} {y:.3f} 0) (layer "F.SilkS") (uuid "{uid("txt", path.name, k)}") '
          f'(effects (font (size 1.6 1.6) (thickness 0.25)) (justify left)))' for k, (s_, x, y) in enumerate(texts)]
    grid = [grid_fp()] if copper else []
    path.write_text("\n".join([head] + grid + list(footprints) + cu + edge + tx + [")"]) + "\n")


def card_footprints(b):
    out = []
    for bb, pl in st.placements():
        if bb != b:
            continue
        for k, (path, (x, y), rot, z) in enumerate(step_models(pl)[0]):
            out.append(fp_text(f"{pl['ref']}_{k}", Path(path).stem, x, st.BH - y, rot, [(path, (0, 0, z))]))
    return out


# ------------------------------------------------------------------ the cage assembly (box frame, envelopes)
CAGE_COLOUR = {"cage": "#E6E2D3", "card": "#B3202A", "backplane": "#B8875A", "socket": "#151515",
               "pack": "#3A6EA5", "charger": "#2E7D32", "mux": "#1A1A1A", "housing": "#151515", "part": "#8A8A8A"}


def assembly_boxes():
    """(colour key, Box in the box frame) for everything in the assembly, the back plate excepted."""
    out = [("cage", b) for name, b in cage.fixed_boxes() if name != "back plate"]
    for b in st.BOARDS:
        out.append(("card", lc.card_slab(b)))
        for ref, x in lc.board_boxes(b):
            if not x.keepout:
                bx = lc.to_box(b, x)
                out.append(("part:" + st.KIND[next(pl["fp"] for _b, pl in st.placements() if pl["ref"] == ref)][0], bx))
    p = st.P
    out.append(("backplane", st.Box(st.strip_x(0) - p / 2, st.BP_BACK, st.strip_x(20) + p / 2, st.BP_FRONT,
                                    st.BP_Z0 - 2 * p, st.BP_Z0 + (st.BP_HOLES + 1) * p, "backplane")))
    for b in st.BOARDS:
        z = st.bp_xy(f"s1.{st.SOCKET_HOLE[b]}")[1]
        out.append(("socket", st.Box(st.strip_x(1) - p / 2, st.BP_FRONT, st.strip_x(18) + p / 2,
                                     st.BP_FRONT + S.val("socket_h"), z - p / 2, z + p / 2, f"socket {b}")))
    for ref, pins, _note in st.BP_PARTS:
        if ref.startswith("W") or ref == "XJ1":
            hh = S.val("qt_lead_h") if ref.startswith("W") else 8.5
            for h in pins.values():
                x, z = st.bp_xy(h)
                out.append(("housing", st.Box(x - p / 2, st.BP_FRONT, x + p / 2, st.BP_FRONT + hh, z - p / 2, z + p / 2, ref)))
    x0, z0, x1, z1 = st.MUX_BOX
    out.append(("mux", st.Box(x0, st.BP_BACK - S.val("foam") - 4.8, x1, st.BP_BACK - S.val("foam"), z0, z1, "mux")))
    for c in cage.contents():
        out.append(("pack" if "pack" in c.what else "charger", c))
    return out


def cage_mesh():
    """Box frame (Xb, Yb, Zb) -> mesh (Xb, Zb, Yb - plate): the back plate's front face is the KiCad board top."""
    m = Mesh()
    pl = cage.PLATE
    for key, b in assembly_boxes():
        col = key.split(":")[1] if key.startswith("part:") else CAGE_COLOUR[key]
        m.box(b.x0, b.z0, b.y0 - pl, b.x1, b.z1, b.y1 - pl, col)
    for b in st.BOARDS:                                  # card names on their front edges
        z = st.card_z(b)
        y = cage.CARD_FRONT - pl + 0.05
        m.text(f"{b} {st.ROLE[b]}", st.CAGE_LEFT + st.BW / 2, z - T + 0.15, y, 1.3, "#FFFFFF")
    return m


# ------------------------------------------------------------------ writing and rendering
def write_all():
    lc.FAILS.clear()
    lc.run()
    if lc.FAILS:
        sys.exit("layout checks fail; fix them first:\n" + "\n".join(lc.FAILS))
    M3D.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for b in st.BOARDS:
        mesh, kinds = card_mesh(b)
        p = M3D / f"{b}.wrl"
        mesh.write(p)
        fps = card_footprints(b) + [fp_text(f"{b}_parts", f"{b}_parts", 0, st.BH, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0))])]
        f = OUT / f"tx-stack-{b}.kicad_pcb"
        board_file(f, fps, card_outline(), T, "#B3202AFF", strips_copper(),
                   [(f"{b} {st.ROLE[b]}  FRONT EDGE (bus header at the back edge, up)", 1, st.BH + 3.5)])
        jobs[f] = (b, kinds)
    W, H, _D = cage.BOX_IN
    p = M3D / "cage.wrl"
    cage_mesh().write(p)
    f = OUT / "tx-stack-cage.kicad_pcb"
    board_file(f, [fp_text("cage", "cage", 0, H, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0))])],
               [(0, 0), (W, 0), (W, H), (0, H)], cage.PLATE, "#E6E2D3FF", height=H)
    jobs[f] = ("cage", None)
    print("wrote", ", ".join(str(x.relative_to(HERE)) for x in jobs))
    return jobs


def legend(png, title, lines):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    try:
        big, small = (ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", s) for s in (40, 28))
    except OSError:
        big, small = ImageFont.load_default(40), ImageFont.load_default(28)
    pad, lh = 24, 38
    width = max(40, int(im.width / 15))
    lines = [w for s in lines for w in textwrap.wrap(s, width, subsequent_indent="    ")]
    out = Image.new("RGB", (im.width, im.height + pad * 2 + 52 + lh * len(lines)), "white")
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    y = im.height + pad
    d.text((pad, y), title, fill="#111111", font=big)
    y += 52
    for s in lines:
        d.text((pad, y), s, fill="#333333", font=small)
        y += lh
    out = out.crop((0, 0, out.width, y + pad))
    out.save(png)


def render(jobs):
    PNG.mkdir(exist_ok=True)
    todo = []
    for f, (b, kinds) in jobs.items():
        if b == "cage":
            lines = ["every part is an envelope box from the layout checks (layout/stack.py, cage/cage.py), not a 3D model",
                     "stand-ins: the cage (printed PLA, not yet designed past these boxes); the BQ25798EVM outline "
                     f"{'x'.join(f'{v:g}' for v in cage.EVM)} mm and the box inside "
                     f"{'x'.join(f'{v:g}' for v in cage.BOX_IN)} mm [TBD-MEASURE]",
                     "cards bottom to top: " + ", ".join(f"{c} {st.ROLE[c]}" for c in st.ORDER)
                     + "; pack and charger in the power zone below; the lid side faces the viewer"]
            todo.append((f, "cage-render-iso.png", "cage assembly, iso (from the lid side)", lines,
                         ["--side", "top", "--rotate", "-40,0,-35", "--perspective", "--zoom", "0.62",
                          "-w", "2000", "-h", "2600"]))
            todo.append((f, "cage-render-front.png", "cage assembly, from the open lid", lines,
                         ["--side", "top", "--zoom", "0.95", "-w", "2000", "-h", "2700"]))
            continue
        lines = legend_lines(kinds)
        todo.append((f, f"{b}-render-top.png", f"{b} {st.ROLE[b]}, from above (front edge at the bottom)", lines,
                     ["--side", "top", "--zoom", "0.95", "-w", "2400", "-h", "1600"]))
        todo.append((f, f"{b}-render-iso.png", f"{b} {st.ROLE[b]}, iso", lines,
                     ["--side", "top", "--rotate", "-50,0,20", "--perspective", "--zoom", "0.9", "-w", "2400", "-h", "1700"]))
    ok = True
    only = [a for a in sys.argv[1:] if a.endswith(".png")]
    for f, png, title, lines, args in todo:
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
        legend(out, title, lines)
        print("rendered", png)
    return ok


if __name__ == "__main__":
    js = write_all()
    if "--no-render" not in sys.argv and not render(js):
        sys.exit(1)
