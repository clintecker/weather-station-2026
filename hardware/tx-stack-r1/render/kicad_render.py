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
import route  # noqa: E402
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
CD = st.CD                          # the card's depth once its back rails are snapped off
# the SolderFul half-hole notches (card frame: y from the front edge) that survive the snap: the side ones short of
# the snapped edge and the front-end pair; the back-end pair went with the rails
NOTCH_SIDE = [y for y in (_NY, st.BH / 2, st.BH - _NY) if y < CD - S.val("sb_mhole")]
NOTCH_FRONT = [st.BW / 2 - _NE / 2, st.BW / 2 + _NE / 2]


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

    def sphere(self, c, r, colour, n=8):
        pts, faces = [], []
        for i in range(n + 1):
            t = math.pi * i / n
            for k in range(n):
                f = 2 * math.pi * k / n
                pts.append((c[0] + r * math.sin(t) * math.cos(f), c[1] + r * math.sin(t) * math.sin(f), c[2] + r * math.cos(t)))
        for i in range(n):
            for k in range(n):
                a, b = i * n + k, i * n + (k + 1) % n
                faces.append([a, a + n, b + n, b])
        self._add(colour, pts, faces)

    def tube(self, pts, r, colour, n=8):
        for a, c in zip(pts, pts[1:]):
            self.cyl(a, c, r, colour, n, caps=False)

    def text(self, s, x, y, z, h, colour, anchor="center", under=False):
        """Stroke text in a plane z = const, read from above; under=True: mirrored and facing down, read from below."""
        u = h / 6
        w = 0.13 * h
        adv = 6 * u
        total = len(s) * adv - 2 * u
        if anchor == "center":
            x -= total / 2
        xm = x + total / 2
        for i, ch in enumerate(s):
            for stroke in FONT.get(ch, FONT.get(ch.upper(), [])):
                for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                    p0, p1 = (x + i * adv + ax * u, y + ay * u), (x + i * adv + bx * u, y + by * u)
                    if under:
                        p0, p1 = (2 * xm - p0[0], p0[1]), (2 * xm - p1[0], p1[1])
                    self._seg(p0, p1, w, z, colour, down=under)

    def _seg(self, p0, p1, w, z, colour, down=False):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            dx, dy, L = 0.0, 1e-3, 1e-3
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        ex, ey = dx / L * w / 2, dy / L * w / 2
        pts = [(p0[0] + nx - ex, p0[1] + ny - ey, z), (p1[0] + nx + ex, p1[1] + ny + ey, z),
               (p1[0] - nx + ex, p1[1] - ny + ey, z), (p0[0] - nx - ex, p0[1] - ny - ey, z)]
        self._add(colour, pts, [[0, 1, 2, 3]] if down else [[3, 2, 1, 0]])

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
    "MINI": "Wio-E5 mini: its board imported from Seeed's Eagle file; the LoRa-E5 module, SMA, USB-C and buttons are "
            "boxes (no maker model), and so is the right-angle SMA adapter AD1 (Amphenol RF: login)",
    "BOB": "RJ11 breakouts: the BOB-14021 board imported from SparkFun's Eagle file; the Amphenol 87180 jack is a box "
           "(Amphenol model: login), on its 1x6 header",
    "PTC": "MF-R010 fuses: boxes (Bourns model: login)",
}
GENERIC = {
    "RAH": "bus header (generic, Clint's): drawn from the Sullins PRPC drawing (tails, 90 degree bends, insulator, 5.8 mm mating pins "
           "past the snapped edge)",
    "RAS": "SWD header: drawn from the same Sullins drawing",
}
BUILT_NOTE = {"BOB": "SparkFun RJ11-Breakout.brd", "MINI": "Seeed LoRa-E5 mini v1.0.brd"}


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
        pkg = "D_DO-35_SOD27"
        # the body stands on lead 1. KiCad's pin 1 is the cathode: AnodeUp has its body on pin 1, CathodeUp on pin 2
        if PART_VALUE[pl["ref"]].startswith("BAT85"):        # lead 1 is the anode
            return [(lib(f"Diode_THT.3dshapes/{pkg}_P{span}mm_Vertical_CathodeUp.step"), pins["2"],
                     _rot(pins["2"], pins["1"]), 0.0)], True, ()
        return [(lib(f"Diode_THT.3dshapes/{pkg}_P{span}mm_Vertical_AnodeUp.step"), pins["1"],
                 _rot(pins["1"], pins["2"]), 0.0)], True, ()
    if kind == "CAP":
        return [(lib("Capacitor_THT.3dshapes/C_Disc_D3.8mm_W2.6mm_P2.50mm.step"), pins["1"],
                 _rot(pins["1"], pins["2"]), 0.0)], True, ()
    if kind in ("RAH", "RAS"):
        return [], False, ("mating pins", "pin bends", "solder tails")   # pins drawn bent in card_mesh
    out, skip = [], ()
    if kind in ("SHTC3", "INA", "MAX", "REG", "MINI", "BOB"):
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
            z = HDR
            out.append(("${KIPRJMOD}/../models/" + p.relative_to(fetch_models.MODELS).as_posix(), (x0, y0), rot, z))
            skip = ("PCB", "header plastic") if mk in fetch_models.BUILT else MAKER_SKIP
    return out, False, skip


def legend_lines(kinds):
    lines = []
    for k in ("MINI", "BOB", "PTC"):
        if k in kinds:
            if k in BUILT_NOTE and not fetch_models.path_of(k):
                lines.append(f"stand-in: {k}: boxes ({BUILT_NOTE[k]} not fetched; run render/fetch_models.py)")
            else:
                lines.append(("" if k in BUILT_NOTE else "stand-in: ") + STAND_IN[k])
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
    lines.append("KiCad library models: lying resistors, standing diodes, 100 nF discs, the breakouts' 0.1 in headers")
    lines.append("wires, jumpers and leads are tubes along their routed paths (layout/route.py): flat on the card, "
                 "right-angle runs, around every part; a lead off the card leaves at the front edge")
    return lines


# ------------------------------------------------------------------ colours
def box_colour(what, kind):
    w = what.lower()
    for key, c in (("header plastic", "#151515"), ("jack", "#1E1E1E"),
                   ("module", "#B8BCC2"), ("sma", "#D4AF37"), ("usb-c", "#B8BCC2"), ("qt socket", "#EDE6D6"),
                   ("jst ph", "#EDE6D6"), ("mf-r010", "#E8A317"), ("button", "#444444"), ("lug", "#D4AF37"),
                   ("screw", "#EDEDED"), ("battery leads", "#B03030"), ("inductor", "#2A2A2A")):
        if key in w:
            return c
    return st.KIND.get(kind, ("#8A8A8A",))[0]


def wire_colour(note):
    n = note.upper()
    for key, c in (("3.3 V", "#D62728"), ("BATTERY +", "#D62728"), ("PACK +", "#D62728"),
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
        if st.pins_of(pl) and pl["fp"] not in ("RAH", "RAS"):     # its tails are underneath: label it there too
            x0, y0, x1, y1 = st.outline_of(pl)
            cx, cy = min(max((x0 + x1) / 2, 4.0), st.BW - 4.0), min(max((y0 + y1) / 2, 2.0), CD - 2.0)
            m.text(pl["ref"], cx, cy - 0.6, -T - 0.06, 1.1, "#FFFFFF", under=True)
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
        if pl["fp"] in ("RAH", "RAS"):
            header_pins(m, pl)
    bundle = {}
    for i, (kind, a, c, side, note) in enumerate(route.WIRES):
        r = route.ROUTES[i]
        if side == "copper" or not r or not r["ok"] or r["card"] != b:
            continue
        col = wire_colour(note)
        rad = 0.30 if kind == "jumper" else S.val("wire24")[1] / 2
        pts = corners([tuple(p) for p in r["pts"]])
        if r.get("bundled"):                              # laid beside the first lead from the same pad
            k = bundle[id(r["pts"])] = bundle.get(id(r["pts"]), 0) + 1
            dz = 0.95 * k if side == "top" else -0.95 * k
            pts = [(x, y, z + dz) if abs(z - (route.Z_TOP if side == "top" else route.Z_BOT)) < 1e-6 else (x, y, z)
                   for x, y, z in pts]
        ends = [e for e in (a, c) if end3(e, b) is None]
        if ends:                                          # leaves the card at the front edge
            q = pts[-1] if abs(pts[-1][1]) < 1e-6 else pts[0]
            stub = [(q[0], q[1], q[2]), (q[0], -6.0, q[2])]
            m.tube(stub, rad, col, 8)
        for e in (a, c):                                  # down into its hole
            p3 = end3(e, b)
            if p3 and isinstance(e, str):
                z = route.Z_TOP if side == "top" else route.Z_BOT
                m.tube([(p3[0], p3[1], 0.0 if side == "top" else -T), (p3[0], p3[1], z)], rad, col, 8)
        m.tube(pts, rad, col, 8)
        for q in pts[1:-1]:                               # round the bends
            m.sphere(q, rad, col)
    return m, kinds


def corners(pts):
    """Drop the points in the middle of straight runs: the tube is drawn run by run, the bends rounded."""
    out = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - b[i] for i in range(3)]
        cr = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        if math.sqrt(sum(x * x for x in cr)) > 1e-9:
            out.append(b)
    out.append(pts[-1])
    return out


def header_pins(m, pl):
    """A right-angle header's pins as Sullins draws them: tail below the card, up through the hole, a 90 degree
    bend at PIN_Z, then flat past the insulator to the tip (out past the snapped edge on the bus header)."""
    pins = st.pins_of(pl)
    s_ = 1 if pl["fp"] == "RAH" else -1
    tail, half = S.val("ra_tail"), 0.32
    for x, y in pins.values():
        tip = y + s_ * st.RA_TIP
        m.box(x - half, y - half, -tail, x + half, y + half, st.PIN_Z + half, "#D8B65A")
        m.box(x - half, min(y, tip), st.PIN_Z - half, x + half, max(y, tip), st.PIN_Z + half, "#D8B65A")


# ------------------------------------------------------------------ the KiCad board files
def card_outline():
    """The snapped SolderFul outline with its remaining half-hole notches (datasheet p.2), KiCad coordinates (y down:
    KiCad y 0 is the snapped back edge, y CD the front edge)."""
    r = S.val("sb_mhole") / 2
    W, H = st.BW, CD
    pts = []

    def notch(cx, cy, a0, a1, n=10):
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    ends = NOTCH_FRONT
    sides = NOTCH_SIDE
    pts.append((0, 0))
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
        lines.append(f'\t\t(pad "{i + 1}" thru_hole circle (at {x:.4f} {CD - y:.4f}) (size 1.9 1.9) '
                     f'(drill {S.val("sb_hole"):g}) (layers "*.Cu" "*.Mask") (uuid "{uid("pad", h)}"))')
    for x, y in st.MHOLES:
        lines.append(f'\t\t(pad "" np_thru_hole circle (at {x:.4f} {CD - y:.4f}) (size {S.val("sb_mhole"):g} '
                     f'{S.val("sb_mhole"):g}) (drill {S.val("sb_mhole"):g}) (layers "*.Cu" "*.Mask") (uuid "{uid("mh", x)}"))')
    lines.append("\t)")
    return "\n".join(lines)


def board_file(path, footprints, outline, thick, mask, copper=(), texts=(), height=CD):
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
\t\t\t(copper_finish "ENIG")
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
            out.append(fp_text(f"{pl['ref']}_{k}", Path(path).stem, x, CD - y, rot, [(path, (0, 0, z))]))
    return out


# ------------------------------------------------------------------ the cage assembly (box frame, envelopes)
CAGE_COLOUR = {"box": "#C9CDD2", "cage": "#E6E2D3", "card": "#B3202A", "backplane": "#B3202A", "socket": "#151515", "contact": "#D8B65A",
               "pack": "#3A6EA5", "charger": "#2E7D32", "mux": "#1A1A1A", "housing": "#151515", "part": "#8A8A8A"}


def assembly_boxes(explode=0.0, section=False):
    """(colour key, Box in the box frame) for everything in the assembly and the box's own floor posts, ribs and
    corner screw posts (the KiCad board is the box floor). explode: the
    cards (and the retention bar) drawn pulled out toward the lid by this much. section: the sockets drawn open
    (two walls and a back) so the header pins show inside them."""
    out = [("box", k) for k in cage.box_keepouts() + cage.floor_ribs()]
    out += [("cage", b) for name, b in cage.fixed_boxes()]
    out = [(k, sh(b, 0, explode + 8, 0) if "retention" in b.what and explode else b) for k, b in out]
    for b in st.BOARDS:
        out.append(("card", sh(lc.card_slab(b), 0, explode, 0)))
        for ref, x in lc.board_boxes(b):
            if not x.keepout and not any(k in x.what for k in ("mating pins", "pin bends", "solder tails")):
                bx = sh(lc.to_box(b, x), 0, explode, 0)
                out.append(("part:" + st.KIND[next(pl["fp"] for _b, pl in st.placements() if pl["ref"] == ref)][0], bx))
    p = st.P
    ox0, oz0, ox1, oz1 = st.BP_OUTLINE
    out.append(("backplane", st.Box(ox0, st.BP_BACK, ox1, st.BP_FRONT, oz0, oz1, "backplane")))
    for b in st.BOARDS:
        z = st.bp_xy(f"s1.{st.SOCKET_HOLE[b]}")[1]
        xa, xb, y0, y1 = st.strip_x(1) - p / 2, st.strip_x(st.model.HDR_LEN[b]) + p / 2, st.BP_FRONT, st.BP_FRONT + S.val("socket_h")
        if section:
            out += [("socket", st.Box(xa, y0, xb, y1, z - p / 2, z - 0.5, f"socket {b} lower wall")),
                    ("socket", st.Box(xa, y0, xb, y1, z + 0.5, z + p / 2, f"socket {b} upper wall")),
                    ("socket", st.Box(xa, y0, xb, y0 + 1.0, z - 0.5, z + 0.5, f"socket {b} floor"))]
            for i in st.model.socket_pins(b):            # contacts and tails through the board to the bus wire
                x = st.strip_x(i)
                if i == st.model.KEY[b]:                   # the key plug: a cut-off pin in the contact, flush with the mouth
                    out.append(("contact", st.Box(x - 0.32, y0 + 1.0, x + 0.32, y1, z - 0.32, z + 0.32, "key plug")))
                out.append(("contact", st.Box(x - 0.3, y0 + 1.0, x + 0.3, y1 - 0.8, z - 0.5, z - 0.25, "contact")))
                out.append(("contact", st.Box(x - 0.3, y0 + 1.0, x + 0.3, y1 - 0.8, z + 0.25, z + 0.5, "contact")))
                out.append(("contact", st.Box(x - 0.32, st.BP_BACK - 1.5, x + 0.32, y0 + 1.0, z - 0.32, z + 0.32, "tail")))
        else:
            out.append(("socket", st.Box(xa, y0, xb, y1, z - p / 2, z + p / 2, f"socket {b}")))
    for ref, pins, _note in st.BP_PARTS:
        if ref.startswith("W") or ref == "XJ1":
            hh = S.val("qt_lead_h") if ref.startswith("W") else 8.5
            for h in pins.values():
                x, z = st.bp_xy(h)
                out.append(("housing", st.Box(x - p / 2, st.BP_FRONT, x + p / 2, st.BP_FRONT + hh, z - p / 2, z + p / 2, ref)))
    if not fetch_models.path_of("MUX"):
        x0, z0, x1, z1 = st.MUX_BOX
        out.append(("mux", st.Box(x0, st.BP_BACK - S.val("foam") - 4.8, x1, st.BP_BACK - S.val("foam"), z0, z1, "mux")))
    for c in cage.contents():
        out.append(("pack" if "pack" in c.what else "charger", c))
    return out


def sh(b, dx, dy, dz):
    return st.Box(b.x0 + dx, b.y0 + dy, b.x1 + dx, b.y1 + dy, b.z0 + dz, b.z1 + dz, b.what, b.keepout, b.service)


def clip(b, win):
    """Box b cut to the window (x0, x1, z0, z1) in the box frame, or None."""
    x0, x1, z0, z1 = win
    if b.x0 >= x1 or b.x1 <= x0 or b.z0 >= z1 or b.z1 <= z0:
        return None
    return st.Box(max(b.x0, x0), b.y0, min(b.x1, x1), b.y1, max(b.z0, z0), min(b.z1, z1), b.what)


# the outside parts drawn in the cage render (envelopes: no maker model without a login, see MODELS.md)


def bulkhead_at():
    a1 = [lc.to_box("B3", x) for _r, x in lc.board_boxes("B3") if _r == "A1"]
    arm = next(x for x in a1 if x.what.endswith("SMA adapter forward arm"))
    return arm, cage.coax(arm)


def extras(m, explode=0.0, whole=False):
    """The printed base's walls (only the bottom and right walls unless whole, so the inside stays visible), the
    glands in the bottom wall's bosses, the SMA bulkhead, the antenna outside, and the coax."""
    W, H, D = cage.BOX_IN

    def P(x, y, z):
        return (x, z, y)
    for b in cage.shell():
        if whole or not any(w in b.what for w in ("left wall", "top wall")):
            m.box(b.x0, b.z0, b.y0, b.x1, b.z1, b.y1, "#E8E4D8")
    if whole:                                                          # the #905 clear lid, as a thin outline
        T = cage.T
        for x0, z0, x1, z1 in ((-T, -T, W + T, 0), (-T, H, W + T, H + T), (-T, 0, 0, H), (W, 0, W + T, H)):
            m.box(x0, z0, cage.SEAM + 0.5, x1, z1, cage.SEAM + 25.0, "#BFD9E8")
    for x, y, k in cage.GLANDS:                                        # bottom wall, the bosses outside
        d1, l1, l2, l3, _cmin, _cmax = cage.GLAND[k]
        nut = cage.GLAND_NUT[k]
        m.cyl(P(x, y, 0), P(x, y, l1), d1 / 2, "#2B2B2B", 12)               # thread inside
        m.cyl(P(x, y, 1.0), P(x, y, 4.0), nut / 2, "#2B2B2B", 6)            # locknut on it
        m.cyl(P(x, y, -6.0), P(x, y, -8.5), nut / 2 + 1.0, "#2B2B2B", 12)   # flange under the boss
        m.cyl(P(x, y, -8.5), P(x, y, -6.0 - l2 + l3 * 0.4), nut / 2, "#2B2B2B", 6)
        m.cyl(P(x, y, -6.0 - l2 + l3 * 0.4), P(x, y, -6.0 - l2), nut / 2 - 1.5, "#2B2B2B", 12)
    arm, (pe, yb, zb, ax) = bulkhead_at()
    m.cyl(P(W - 9.0, yb, zb), P(W + 12.0, yb, zb), 3.2, "#D4AF37", 12)  # bulkhead jack through the boss
    m.cyl(P(W - 2.5, yb, zb), P(W - 0.2, yb, zb), 5.5, "#D4AF37", 6)    # its nut inside
    m.cyl(P(W + 12.0, yb, zb), P(W + 22.0, yb, zb), 4.5, "#1A1A1A", 12)  # antenna hinge
    L = S.val("ant_len")
    tip = (W + 22.0 + L * math.cos(math.radians(70)), yb, zb + L * math.sin(math.radians(70)))
    m.cyl(P(W + 22.0, yb, zb), P(*tip), 4.0, "#1A1A1A", 12)            # whip, tilted 70 degrees up
    # coax: the straight plug on AD1's forward arm, the bend to the right, the run to the bulkhead
    az = (arm.z0 + arm.z1) / 2
    y0 = arm.y1
    m.cyl(P(ax, y0 + explode, az), P(ax, pe + explode, az), 3.0, "#D4AF37", 12)
    r = S.val("rg316_bend")
    pts = [P(ax, pe + explode, az)]
    for k in range(1, 10):
        t = math.radians(90 * k / 9)
        pts.append(P(ax + r - r * math.cos(t), pe + explode + r * math.sin(t), az + (zb - az) * k / 9))
    pts += [P(W - 9.0, yb, zb)]
    m.tube(pts, 1.25, "#7A4A2A", 8)


def cage_mesh(explode=0.0, win=None, section=False, whole=False):
    """Box frame (Xb, Yb, Zb) -> mesh (Xb, Zb, Yb) (stack.MESH_AXES): the box floor's inside face is the KiCad board
    top. The box frame is left-handed and this swap is a mirror, so the KiCad scene is the real box (L12): its top view
    is the true view from the lid, left wall on the left."""
    assert st.MESH_AXES == (0, 2, 1), "the mesh code below writes (Xb, Zb, Yb); L12 checks stack.MESH_AXES"
    m = Mesh()
    pl = 0.0
    for key, b in assembly_boxes(explode, section):
        if win:
            b = clip(b, win)
            if b is None:
                continue
        col = key.split(":")[1] if key.startswith("part:") else CAGE_COLOUR[key]
        m.box(b.x0, b.z0, b.y0 - pl, b.x1, b.z1, b.y1 - pl, col)
    for b in st.BOARDS:                                  # the bus headers, pins bent as drawn by Sullins
        hdr = next(p_ for bb, p_ in st.placements() if bb == b and p_["fp"] == "RAH")
        for x, y in st.pins_of(hdr).values():
            for (xa, ya, za), (xb, yb_, zb) in (((x - 0.32, y - 0.32, -S.val("ra_tail")), (x + 0.32, y + 0.32, st.PIN_Z + 0.32)),
                                                 ((x - 0.32, y, st.PIN_Z - 0.32), (x + 0.32, y + st.RA_TIP, st.PIN_Z + 0.32))):
                a = st.card_to_box(b, xa, ya, za)
                c = st.card_to_box(b, xb, yb_, zb)
                bx = st.Box(min(a[0], c[0]), min(a[1], c[1]) + explode, max(a[0], c[0]), max(a[1], c[1]) + explode,
                            min(a[2], c[2]), max(a[2], c[2]), "pin")
                if win:
                    bx = clip(bx, win)
                    if bx is None:
                        continue
                m.box(bx.x0, bx.z0, bx.y0 - pl, bx.x1, bx.z1, bx.y1 - pl, "#D8B65A")
    for line, holes in st.BP_BUS:                        # the tinned bus wires on the copper side
        if holes:
            x = st.strip_x(line)
            z0, z1 = st.bp_xy(f"s{line}.{holes[0]}")[1], st.bp_xy(f"s{line}.{holes[-1]}")[1]
            if win:
                if not (win[0] < x < win[1]):
                    continue
                z0, z1 = max(z0, win[2]), min(z1, win[3])
                if z0 >= z1:
                    continue
            y = st.BP_BACK - 0.32 - pl
            m.cyl((x, z0, y), (x, z1, y), 0.32, "#C0C0C0", 8)
    if not win:
        extras(m, explode, whole)
        for b in st.BOARDS:                              # card names on their front edges
            z = st.card_z(b)
            y = cage.CARD_FRONT - pl + 0.05 + explode
            m.text(f"{b} {st.ROLE[b]}", st.CAGE_LEFT + st.BW / 2, z - T + 0.15, y, 1.3, "#FFFFFF")
    return m


def mux_footprint(H):
    p = fetch_models.path_of("MUX")
    if not p:
        return []
    x0, z0, _x1, _z1 = st.MUX_BOX
    zoff = st.BP_BACK - S.val("foam") - 4.53
    return [fp_text("mux", "PCA9548", x0, H - z0, 0,
                    [("${KIPRJMOD}/../models/" + p.relative_to(fetch_models.MODELS).as_posix(), (0, 0, zoff))])]


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
        fps = card_footprints(b) + [fp_text(f"{b}_parts", f"{b}_parts", 0, CD, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0))])]
        f = OUT / f"tx-stack-{b}.kicad_pcb"
        board_file(f, fps, card_outline(), T, "#B3202AFF", strips_copper(),
                   [(f"{b} {st.ROLE[b]}  FRONT EDGE (bus header at the back edge, up)", 1, CD + 3.5)])
        jobs[f] = (b, kinds)
    W, H, _D = cage.BOX_IN
    for name, kw in (("cage", {}), ("cage-exploded", {"explode": 45.0}), ("cage-box", {"whole": True})):
        p = M3D / f"{name}.wrl"
        cage_mesh(**kw).write(p)
        f = OUT / f"tx-stack-{name}.kicad_pcb"
        board_file(f, [fp_text(name, name, 0, H, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0))])] + mux_footprint(H),
                   [(0, 0), (W, 0), (W, H), (0, H)], 3.0, "#C9CDD2FF", height=H)
        jobs[f] = (name, None)
    # the section: B1 and its socket, cut through bus line 9 (everything at Xb past it removed), seen from the right
    xs = st.strip_x(9) + 1.27
    zc = st.card_z("B1")
    win = (0.0, xs, zc - 12.0, zc + 12.0)
    p = M3D / "cage-section.wrl"
    cage_mesh(win=win, section=True).write(p)
    f = OUT / "tx-stack-cage-section.kicad_pcb"
    board_file(f, [fp_text("section", "section", 0, H, 0, [("${KIPRJMOD}/3d/" + p.name, (0, 0, 0))])],
               [(0, H - win[3]), (xs, H - win[3]), (xs, H - win[2]), (0, H - win[2])], 3.0, "#C9CDD2FF", height=H)
    jobs[f] = ("cage-section", None)
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
    cage_lines = ["the printed PETG base (100 deep) and its moulded cage, the cards and the shelves: the envelope boxes "
                  "the layout checks use (layout/stack.py, cage/cage.py); the mux is Adafruit's 5626 STEP"
                  + ("" if fetch_models.path_of("MUX") else " (not fetched: a box)"),
                  "shelves bottom to top: the pack, the BQ25798EVM (90 x 90, Clint; heights [TBD-MEASURE]), B4, B2, "
                  "B1, B3; stand-ins (render/MODELS.md): the EVM, the pack, the sockets, the SMA bulkhead (135110 "
                  "cable), the ANT-916 antenna (length [TBD-MEASURE]); the PG-7 and PG-9 glands in the bottom wall "
                  "from the Adafruit #761 drawing",
                  f"inside {'x'.join(f'{v:g}' for v in cage.BOX_IN)} mm; the lid interface (rim, O-ring, screws) "
                  "is from Clint's photos, L1 and the rim ring's fit [TBD-MEASURE]; the coax: AD1's arm toward the lid, the cable bending right in front of "
                  "the cards to the bulkhead boss",
                  "cards bottom to top: " + ", ".join(f"{c} {st.ROLE[c]}" for c in st.ORDER)
                  + "; the lid side faces the viewer"]
    for f, (b, kinds) in jobs.items():
        if b == "cage":
            todo.append((f, "cage-render-iso.png", "cage assembly, iso (from the lid side)", cage_lines,
                         ["--side", "top", "--rotate", "-40,0,-35", "--perspective", "--zoom", "0.62",
                          "-w", "2400", "-h", "3000"]))
            todo.append((f, "cage-render-front.png", "cage assembly, from the open lid", cage_lines,
                         ["--side", "top", "--zoom", "0.95", "-w", "2400", "-h", "3200"]))
            continue
        if b == "cage-box":
            todo.append((f, "cage-render-box.png", "the whole printed base under the #905 lid (lid drawn as its rim "
                         "outline), from the lid side and below: glands, vent, SMA bulkhead",
                         cage_lines, ["--side", "top", "--rotate", "-62,0,-30", "--perspective", "--zoom", "0.5",
                                      "-w", "2400", "-h", "3000"]))
            continue
        if b == "cage-exploded":
            todo.append((f, "cage-render-exploded.png", "cage assembly, exploded: the cards and the retention bar "
                         "pulled 45 mm toward the lid, the way they slide in", cage_lines,
                         ["--side", "top", "--rotate", "-40,0,-35", "--perspective", "--zoom", "0.55",
                          "-w", "2400", "-h", "3000"]))
            continue
        if b == "cage-section":
            todo.append((f, "cage-render-section.png", "section through B1 and the backplane at bus line 9, seen from "
                         "the right: header pins bent 90 degrees, past the snapped card edge into the socket",
                         [f"B1 card snapped at {st.CD:.2f} mm [TBD-MEASURE]; card edge {st.Y_BP - st.CD:.2f} mm from the "
                          f"backplane; insertion {st.Y_INS + S.val('ra_mate') - st.Y_MOUTH:.2f} of {S.val('ra_mate'):g} mm; "
                          f"insulator {st.Y_MOUTH - st.Y_INS:.2f} mm short of the socket mouth",
                          "back plate at the bottom, the PAD3U backplane (its bus wire under it), the socket drawn open, "
                          "the card and its parts above; everything past line 9 cut away",
                          "boxes from the layout checks; pins drawn from the Sullins PRPC and PPPC drawings"],
                         ["--side", "right", "--zoom", "0.28", "--pan", "0,-18,0", "-w", "2400", "-h", "3000"]))
            continue
        lines = legend_lines(kinds)
        todo.append((f, f"{b}-render-top.png", f"{b} {st.ROLE[b]}, from above (front edge at the bottom)", lines,
                     ["--side", "top", "--zoom", "0.95", "-w", "3200", "-h", "2200"]))
        todo.append((f, f"{b}-render-bottom.png", f"{b} {st.ROLE[b]}, from below (the underside wires; labels read "
                     "from below)", lines, ["--side", "bottom", "--zoom", "0.95", "-w", "3200", "-h", "2200"]))
        todo.append((f, f"{b}-render-iso.png", f"{b} {st.ROLE[b]}, iso from the front right", lines,
                     ["--side", "top", "--rotate", "-55,0,-30", "--perspective", "--zoom", "0.85", "-w", "3200", "-h",
                      "2300"]))
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
