"""Session 7 (charger and pack) illustrations, same pipeline as Sessions 2-6 (r3d: hidden lines + flat colour).

The BQ25798EVM: no maker CAD in the repo. What IS in the repo (sources.py) places it: the 90 x 90 outline (Clint);
J8 (Molex 0022053041, right-angle KK 4-pin) on the lid edge 15-27 mm from the left, 12 mm past it, and the right
blocks 6 mm past the right edge (Clint's photo IMG_8591); and from TI SLUUCB5E Figure 4-1 (the top-layer drawing,
scaled): each terminal's order and screw position (evm_terms, evm_term_y), J6 along the left edge (evm_j6_y), J7
(evm_j7) and the jumpers this build touches (evm_jp). J1, J2 (On-Shore ED120/2DS) on the left edge; J3 (ED120/2DS)
and J5 (ED120/3DS) on the right. The chips and the other parts are not drawn.

EVM frame (mm): x from the board's left (J6) edge to its right (J3/J5) edge, y from its lid edge (J8) to its back
edge (toward the backplane), z up from the underside (top face at 1.6). Into the box: (EVM_X0 + x, EVM_Y1 - y,
EVM_Z0 + z). Seen from above (top face up) the lid edge is at the BOTTOM of the picture, the backplane edge at the top:
that is how it sits in front of you with the box hanging, lid toward you.

Run ONE scene per process: .venv-cad/bin/python -B scenes7.py NAME   (list: scenes7.py list)
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "session1" / "v2"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V2))
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
sys.path.insert(0, str(REPO / "layout"))
sys.path.insert(0, str(REPO / "cage"))
sys.path.insert(0, str(REPO))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import cage                             # noqa: E402
from stack import S                     # noqa: E402
import asmd                             # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}

EVM_PCB = "#B72A2F"
BLOCK = "#2F8A4C"          # the On-Shore ED120 blocks are green
KK = "#F2EEE4"
BLACK = "#1E1E1E"
GOLD = "#D9AE3F"
STEEL = "#B9BCC0"
SOLDER = "#A9AEB4"
TAPE = "#F4F1E8"
PACKBLUE = "#3C78C8"
SHRINK = "#2B2B2B"
EPOXY = "#2A2A2A"
COL = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "white": "#F2F2F2"}

EVM_W, EVM_D, _evm_h = S.val("evm")
T_L1, T_L2, T_L3, T_L4, T_R1, T_R2, T_R3, T_R4 = S.val("evm_edge_tails")
J8_X0, J8_X1 = S.val("evm_j8_x")
J8_OUT = S.val("evm_j8")
OV_L, OV_R = S.val("evm_overhang")
PITCH5 = 5.08


def from_back(a, b):
    """evm_edge_tails spans are measured from the back edge; this frame's y runs from the lid edge."""
    return EVM_D - b, EVM_D - a


# terminal blocks: (name, edge, screw y's in this frame (lid edge first), silk names in the same order), from
# SLUUCB5E Figure 4-1 (sources: evm_terms, evm_term_y, which run from the back edge)
_TERMS = {b[0]: b[1:] for b in S.val("evm_terms")}
_TERM_Y = {b[0]: b[1:] for b in S.val("evm_term_y")}
BLOCKS = {n: ("L" if n in ("J1", "J2") else "R", tuple(EVM_D - y for y in reversed(_TERM_Y[n])),
              tuple(reversed(_TERMS[n]))) for n in ("J1", "J2", "J3", "J5")}
J6_Y = tuple(EVM_D - y for y in reversed(S.val("evm_j6_y")))     # SLUUCB5E Figure 4-1, along the left edge
J7_X0, J7_X1, _j7a, _j7b = S.val("evm_j7")
J7_Y = (EVM_D - _j7b, EVM_D - _j7a)
JPS = [(nm, x, EVM_D - y, n, ax) for nm, x, y, n, ax in S.val("evm_jp")]
# the shunts as supplied (SLUUCB5E Table 1-3) and after Session 7 (ASSEMBLY.md 1.1-1.5)
JP_ON = {"supplied": {"JP9", "JP12", "JP17", "JP18", "JP24", "JP30", "JP32"},
         "done": {"JP12", "JP17", "JP22", "JP30", "JP32"}}


def term_k(block, net):
    """The position (lid edge first) of `net` on a terminal block."""
    return BLOCKS[block][2].index(net)


BLK_DEPTH, BLK_H = 7.6, 10.0


def R(name, s, d, up=(0, 1, 0), fit=(300, 300), **kw):
    s.placed_by("EVM frame -> box -> cage.to_lid",
                r3d.jacobian(lambda x, y, z: cage.to_lid(cage.EVM_X0 + x, cage.EVM_Y1 - y, cage.EVM_Z0 + z)))
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def cyl(r, a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    v = b - a
    L = float(np.linalg.norm(v))
    return cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*(v / L)))


def tube(pts, r):
    pts = [np.asarray(p, float) for p in pts]
    sol = [cyl(r, a, b) for a, b in zip(pts[:-1], pts[1:]) if np.linalg.norm(b - a) > 1e-6]
    sol += [cq.Solid.makeSphere(r, cq.Vector(*p)) for p in pts[1:-1]]
    s = sol[0]
    for x in sol[1:]:
        s = s.fuse(x)
    return s.clean()


def comp(shapes):
    return cq.Compound.makeCompound([x if isinstance(x, cq.Shape) else x.val() for x in shapes])


def block_geom(name):
    """(x0, x1, y0, y1, positions centres [(x_entry, y)], outward direction sign)."""
    edge, ys, _silk = BLOCKS[name]
    y0, y1 = min(ys) - PITCH5 / 2, max(ys) + PITCH5 / 2
    if edge == "R":
        x0, x1, out = EVM_W + OV_R - BLK_DEPTH, EVM_W + OV_R, 1
    else:
        x0, x1, out = 2.4, 2.4 + BLK_DEPTH, -1                # Figure 4-1: J1, J2 from 2.4 in from the left edge
    pos = [((x1 if out > 0 else x0), y) for y in ys]
    return x0, x1, y0, y1, pos, out


def add_block(s, name, labels=True):
    x0, x1, y0, y1, pos, out = block_geom(name)
    z0 = 1.6
    body = M.box(x0, y0, z0, x1, y1, z0 + BLK_H).val()
    for xe, ye in pos:                                       # the wire entries in the outer face, the screws on top
        body = body.cut(M.box(xe - out * 3.5 - 1.6, ye - 1.6, z0 + 2.0, xe - out * 3.5 + 1.6, ye + 1.6, z0 + 5.2).val()
                        .translate(cq.Vector(out * 3.6, 0, 0)))
    s.add(name, body, BLOCK)
    for k, (xe, ye) in enumerate(pos):
        xs = (x0 + x1) / 2
        s.add(f"{name}_scr{k}", cyl(1.5, (xs, ye, z0 + BLK_H - 0.6), (xs, ye, z0 + BLK_H + 0.2)), STEEL)
        s.anchor(f"{name}_{k}", (xe, ye, z0 + 3.6))
        s.anchor(f"{name}_scr{k}", (xs, ye, z0 + BLK_H + 0.2), on=f"{name}_scr{k}")
    s.anchor(name, (x0 + 1.0, (y0 + y1) / 2 + PITCH5 / 2, z0 + BLK_H), on=name)


def add_evm(s, silk=True, jp_state="supplied"):
    s.add("evm", M.box(0, 0, 0, EVM_W, EVM_D, 1.6).val(), EVM_PCB, 0.9)
    for n in BLOCKS:
        add_block(s, n)
    # J6 micro-B, bottom-mounted on the left edge (under the board), 1.5 past the edge
    s.add("J6", M.box(-OV_L, J6_Y[0], -2.6, 5.0, J6_Y[1], 0).val(), STEEL)
    s.anchor("J6", (-OV_L, sum(J6_Y) / 2, -1.3))
    # J8: right-angle KK 4-pin on the lid edge, pins out past it
    hx0, hx1 = J8_X0 + 0.9, J8_X1 - 0.9
    s.add("J8", M.box(hx0, 0.6, 1.6, hx1, 6.6, 4.8).val().fuse(M.box(hx0, 5.0, 1.6, hx1, 6.6, 9.5).val()), KK)
    for k in range(4):
        x = hx0 + 1.27 + 2.54 * k + (hx1 - hx0 - 10.16) / 2
        s.add(f"J8_p{k}", M.box(x - 0.32, 6.6 - J8_OUT - 0.6, 3.0, x + 0.32, 4.0, 3.64).val(), GOLD)
        s.anchor(f"J8_{k + 1}", (x, 6.6 - J8_OUT - 0.6, 3.3))
    s.anchor("J8", ((hx0 + hx1) / 2, 6.6, 9.5), on="J8")
    # J7 (Molex 0393570002, 2 x 3.5 mm) and the jumpers this build touches, where Figure 4-1 puts them
    s.add("J7", M.box(J7_X0, J7_Y[0], 1.6, J7_X1, J7_Y[1], 1.6 + 8.0).val(), BLOCK)
    for k, xs in enumerate(((J7_X0 + J7_X1) / 2 - 1.75, (J7_X0 + J7_X1) / 2 + 1.75)):
        s.add(f"J7_s{k}", cyl(1.1, (xs, sum(J7_Y) / 2, 9.4), (xs, sum(J7_Y) / 2, 9.8)), STEEL)
    s.anchor("J7", (J7_X1, sum(J7_Y) / 2, 9.6), on="J7")
    for nm, x, y, n, ax in JPS:
        hx, hy = (1.27 * n, 1.27) if ax == "x" else (1.27, 1.27 * n)
        s.add(f"{nm}_base", M.box(x - hx, y - hy, 1.6, x + hx, y + hy, 4.1).val(), BLACK)
        for k in range(n):
            px, py = (x - hx + 1.27 + 2.54 * k, y) if ax == "x" else (x, y - hy + 1.27 + 2.54 * k)
            s.add(f"{nm}_p{k}", M.box(px - 0.32, py - 0.32, 4.1, px + 0.32, py + 0.32, 10.0).val(), GOLD)
        if nm in JP_ON[jp_state]:                            # the shunt over two pins (JP9's on BATP-BATTERY)
            sx, sy = (x + 1.27, y) if (ax == "x" and n == 3) else (x, y)
            ex, ey = (2.54, 1.25) if ax == "x" else (1.25, 2.54)
            s.add(f"{nm}_sh", M.box(sx - ex, sy - ey, 4.3, sx + ex, sy + ey, 10.3).val(), "#2A2A2A")
        s.anchor(nm, (x, y, 10.3))
        if silk:
            s.text("evm", nm, (x + (hx + 0.8 if ax == "y" else -hx), y - (3.2 if ax == "x" else 0.9), 1.6),
                   (1, 0, 0), (0, 1, 0), 2.0, colour="#FFFFFF")
    if silk:
        for n, (edge, ys, _silk) in BLOCKS.items():
            x = EVM_W - 4.0 - BLK_DEPTH if edge == "R" else 4.0 + BLK_DEPTH
            s.text("evm", n, (x, sum(ys) / len(ys) - 1.2, 1.6), (1, 0, 0), (0, 1, 0), 3.0, colour="#FFFFFF")
        s.text("evm", "J8", ((J8_X0 + J8_X1) / 2, 10.0, 1.6), (1, 0, 0), (0, 1, 0), 3.0, colour="#FFFFFF")
        s.text("evm", "J6", (8.5, sum(J6_Y) / 2 - 1.2, 1.6), (1, 0, 0), (0, 1, 0), 3.0, colour="#FFFFFF")
        s.text("evm", "BQ25798EVM", (EVM_W / 2, EVM_D / 2, 1.6), (1, 0, 0), (0, 1, 0), 5.0, colour="#FFFFFF")
    s.anchor("board", (EVM_W * 0.45, EVM_D * 0.65, 1.6), on="evm")


def lead(s, name, pts, body, band=None, r=0.75, bare=3.0, end_cap=True):
    """A 24 AWG stranded lead along pts (last point = where its bare end goes in)."""
    pts = [np.asarray(p, float) for p in pts]
    d = pts[-1] - pts[-2]
    d = d / np.linalg.norm(d)
    ins_end = pts[-1] - d * bare
    s.add(name, tube(pts[:-1] + [ins_end], r), COL[body])
    s.add(f"{name}_cu", cyl(r * 0.55, ins_end, pts[-1]), "#C9874A")
    if band:
        p0, p1 = pts[0], pts[1]
        u = (p1 - p0) / np.linalg.norm(p1 - p0)
        s.add(f"{name}_band", cyl(r + 0.06, p0 + u * 4, p0 + u * 7), COL[band])


def into(name, k, back=34.0, bend=None, rise=0.0):
    """Points for a lead coming into block `name` position k from outside, straight, `back` mm long."""
    x0, x1, y0, y1, pos, out = block_geom(name)
    xe, ye = pos[k]
    z = 1.6 + 3.6
    p_in = (xe - out * 3.0, ye, z)
    p_out = (xe + out * 2.0, ye, z)
    far = (xe + out * back, ye + (bend or 0.0), z + rise)
    return [far, p_out, p_in]


# ------------------------------------------------------------------ the board, as supplied and done
@scene
def p_evm():
    s = r3d.Scene()
    add_evm(s, silk=False)
    R("p_evm", s, (0.35, -0.55, 1), up=(0, 1, 0), fit=(150, 95), line=0.45)


@scene
def evm_top():
    s = r3d.Scene()
    add_evm(s)
    R("evm_top", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 260), line=0.5)


# lead colours and where they land (ASSEMBLY.md section 4 / BACKPLANE.md section 3): block, position (SLUUCB5E
# Figure 4-1, lid end first), body, band
LEAD_AT = {"J5 BAT": ("J5", term_k("J5", "BATTERY"), "red", "black"),
           "J5 SNS": ("J5", term_k("J5", "SNS_BATP"), "white", "red"), "J5 GND": ("J5", term_k("J5", "GND"), "black", None),
           "J3 SYS": ("J3", term_k("J3", "SYS"), "red", "black"), "J3 GND": ("J3", term_k("J3", "GND"), "black", None)}


def add_leads(s, which=None):
    for nm, (blk, k, body, band) in LEAD_AT.items():
        if which and nm not in which:
            continue
        # the backplane leads arrive from the back edge (the backplane), the pack - lead from the pack (below, front)
        x0, x1, y0, y1, pos, out = block_geom(blk)
        xe, ye = pos[k]
        z = 5.2
        lane = EVM_W + OV_R + 6 + 3.2 * ("J3 SYS", "J3 GND", "J5 BAT", "J5 SNS", "J5 GND").index(nm)
        end_y = -24.0 if nm == "J5 GND" else EVM_D + 16          # the pack (in front, below) or the backplane (behind)
        pts = [(lane, end_y, z), (lane, ye + (2.0 if end_y > 0 else -2.0), z), (lane - 2.0, ye, z),
               (xe + 2.0, ye, z), (xe - 3.0, ye, z)]
        lead(s, f"L_{nm.replace(' ', '_')}", pts, body, band)
        ka = ("J3 SYS", "J3 GND", "J5 BAT", "J5 SNS", "J5 GND").index(nm)
        ya = (EVM_D + 8 - 7.0 * ka) if end_y > 0 else -14.0
        s.anchor(f"lead_{nm}", (pts[0][0], ya, z + 0.75), on=f"L_{nm.replace(' ', '_')}")


@scene
def evm_done():
    s = r3d.Scene()
    add_evm(s, jp_state="done")
    add_leads(s)
    # the J8 lead plugged on, three wires toward the backplane (up the picture: they run back over the board)
    hx0 = J8_X0 + 0.9
    plug_y0 = 6.6 - J8_OUT - 1.0
    s.add("kk_plug", M.box(hx0 - 0.4, plug_y0 - 12.0, 1.8, J8_X1 - 0.5, plug_y0, 6.2).val(), KK)
    for k, colr in enumerate(("black", "yellow", "blue")):
        x = hx0 + 1.27 + 2.54 * k + (J8_X1 - J8_X0 - 1.8 - 10.16) / 2
        s.add(f"kk_w{k}", tube([(x, plug_y0 - 12, 4.0), (x, plug_y0 - 22, 4.0), (x - 14 + 3 * k, plug_y0 - 34, 4.0)], 0.55),
              COL[colr])
    s.anchor("kk_plug", ((J8_X0 + J8_X1) / 2, plug_y0 - 6, 6.2), on="kk_plug")
    R("evm_done", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 300), line=0.5)


# ------------------------------------------------------------------ close-ups
def header2(s, name="jp", y=0.0):
    s.add(f"{name}_base", M.box(-2.54, y - 1.27, 0, 2.54, y + 1.27, 2.5).val(), BLACK)
    for k, x in enumerate((-1.27, 1.27)):
        s.add(f"{name}_p{k}", M.box(x - 0.32, y - 0.32, -3.0, x + 0.32, y + 0.32, 8.4).val(), GOLD)


def shunt(z):
    sh = M.box(-2.5, -1.25, z, 2.5, 1.25, z + 6.0).val()
    for x in (-1.27, 1.27):
        sh = sh.cut(M.box(x - 0.6, -0.6, z - 0.1, x + 0.6, 0.6, z + 5.0).val())
    return sh


@scene
def jp_pull():
    """A 2-pin jumper with its shunt pulled up off it (JP24, JP9, JP18, JP17 go this way)."""
    s = r3d.Scene()
    s.add("pcb", M.box(-8, -6, -1.6, 8, 6, 0).val(), EVM_PCB, 0.6)
    header2(s)
    s.add("shunt", shunt(13.0), BLACK)
    s.anchor("shunt", (0, -1.25, 16.0), on="shunt")
    s.anchor("pins", (1.27, -0.32, 6.5), on="jp_p1")
    R("jp_pull", s, (0.5, -1, 0.7), up=(0, 0, 1), fit=(130, 120), line=0.6)


@scene
def jp_fit():
    """A 2-pin jumper with its shunt pushed fully down (JP22 goes on this way)."""
    s = r3d.Scene()
    s.add("pcb", M.box(-8, -6, -1.6, 8, 6, 0).val(), EVM_PCB, 0.6)
    header2(s)
    s.add("shunt", shunt(2.6), BLACK)
    s.anchor("shunt", (0, -1.25, 6.0), on="shunt")
    R("jp_fit", s, (0.5, -1, 0.7), up=(0, 0, 1), fit=(130, 120), line=0.6)


@scene
def j5_sns():
    """J5 close up from outside the right edge: the white/red sense lead going into its middle position."""
    s = r3d.Scene()
    s.add("evm", M.box(EVM_W - 18, 12, 0, EVM_W, 48, 1.6).val(), EVM_PCB, 0.6)
    add_block(s, "J5")
    pts = into("J5", term_k("J5", "SNS_BATP"), back=26.0)
    lead(s, "sns", pts, "white", "red")
    s.anchor("sns", pts[0], on="sns")
    R("j5_sns", s, (1, -0.45, 0.8), up=(0, 0, 1), fit=(250, 150), line=0.55)


def j7_block(s, x=0.0, y=0.0):
    """Molex 0393570002: a 2-position 3.50 mm terminal block, drawn on its own (its place on the board: evm_j7)."""
    body = M.box(x - 3.5, y - 3.8, 0, x + 3.5, y + 3.8, 8.0).val()
    for k in (-1, 1):
        body = body.cut(M.box(x + k * 1.75 - 1.2, y + 2.0, 1.8, x + k * 1.75 + 1.2, y + 3.9, 4.2).val())
    s.add("J7", body, BLOCK)
    for k in (-1, 1):
        s.add(f"J7_s{k}", cyl(1.1, (x + k * 1.75, y - 0.5, 7.4), (x + k * 1.75, y - 0.5, 8.2)), STEEL)
    s.anchor("J7", (x, y - 3.8, 6.0), on="J7")


@scene
def rt1_j7():
    """Adafruit #372: the epoxy bead and its two leads (extended to 150 mm, trim to fit) into J7."""
    s = r3d.Scene()
    s.add("pcb", M.box(-9, -8, -1.6, 9, 8, 0).val(), EVM_PCB, 0.6)
    j7_block(s)
    s.add("bead", cq.Solid.makeSphere(1.6, cq.Vector(0, 46, 3.0)), EPOXY)
    for k, colr in ((-1, "white"), (1, "white")):
        x = k * 1.75
        pts = [(k * 0.5, 44.6, 3.0), (x, 38, 3.0), (x, 8.0, 3.0), (x, 4.5, 3.0)]
        s.add(f"w{k}", tube(pts[:-1], 0.45), COL[colr])
        s.add(f"cu{k}", cyl(0.3, pts[-2], pts[-1]), "#C9874A")
        s.add(f"sh{k}", cyl(0.75, (x, 30, 3.0), (x, 22, 3.0)), SHRINK)
    s.anchor("bead", (0, 46.0, 4.6), on="bead")
    s.anchor("splice", (1.75, 26.0, 3.75), on="sh1")
    R("rt1_j7", s, (0.7, -0.6, 1), up=(0, 1, 0), fit=(150, 230), line=0.55)


@scene
def kk_lead():
    """The J8 lead: a Molex KK 2695 4-way housing (crimps in 1-3, 4 empty) at the EVM end and three 1-way 0.1 in
    housings at the backplane end, one per XJ1 pin, each with a tape flag (GND, SCL, SDA). XJ1's pins sit on lines 2,
    7 and 10 of hole 11 (BACKPLANE.md section 3), 12.7 and 7.6 mm apart, so no 1 x 3 housing fits them."""
    s = r3d.Scene()
    s.add("kk", M.box(-5.1, 0, 0, 5.1, 12.7, 6.3).val(), KK)
    for k in range(4):
        x = -3.81 + 2.54 * k
        s.add(f"kk_h{k}", M.box(x - 0.6, -0.05, 2.55, x + 0.6, 0.8, 3.75).val(), BLACK)
    s.text("kk", "1", (-3.81, 6.0, 6.3), (1, 0, 0), (0, 1, 0), 2.2, colour="#121212")
    s.text("kk", "4", (3.81, 6.0, 6.3), (1, 0, 0), (0, 1, 0), 2.2, colour="#121212")
    du_y = 70.0
    for k, (colr, flag) in enumerate((("black", "GND"), ("yellow", "SCL"), ("blue", "SDA"))):
        x = -3.81 + 2.54 * k
        xd = -9.0 + 9.0 * k                     # the three ends apart, each to its own pin
        s.add(f"w{k}", tube([(x, 12.7, 3.15), (x, 22, 3.15), (xd, 40, 2.2), (xd, du_y, 2.2)], 0.55), COL[colr])
        s.anchor(f"w{k}", (xd, 50, 2.75), on=f"w{k}")
        s.add(f"du{k}", M.box(xd - 1.27, du_y, 0.93, xd + 1.27, du_y + 14.0, 3.47).val(), BLACK)
        s.anchor(f"du{k}", (xd, du_y + 14.0, 3.47), on=f"du{k}")
        s.add(f"fl{k}", M.box(xd - 3.2, du_y - 9.0, 2.75, xd + 3.2, du_y - 3.0, 3.05).val(), "#F4F1E6")
        s.text(f"fl{k}", flag, (xd, du_y - 7.2, 3.05), (1, 0, 0), (0, 1, 0), 2.6, colour="#121212")
    s.anchor("kk", (0, 12.7, 6.3), on="kk")
    s.anchor("pos1", (-3.81, 0.0, 3.15))
    s.anchor("pos4", (3.81, 0.0, 3.15))
    s.anchor("du", (0, du_y + 14.0, 3.47), on="du1")
    R("kk_lead", s, (0.25, -0.35, 1), up=(1, 0, 0), fit=(300, 110), line=0.55)


def pack(s, x0=0.0, y0=0.0):
    px, py, pz = S.val("pack")
    s.add("pack", M.box(x0, y0, 0, x0 + px, y0 + py, pz).val(), PACKBLUE, 0.8)
    s.text("pack", "Adafruit #353  3.7 V 6600 mAh", (x0 + px / 2, y0 + py / 2, pz), (1, 0, 0), (0, 1, 0), 4.0,
           colour="#FFFFFF")
    return px, py, pz


@scene
def pack_pg1():
    """The pack (unplugged), its JST PH plug, PG1's socket on its two leads: + spliced to the backplane's PACK + lead,
    - on to J5 GND. The plug and the socket are apart: they meet only in Session 9 step 08."""
    s = r3d.Scene()
    px, py, pz = pack(s)
    # the pack's own two leads and its JST PH plug
    for k, colr in ((0, "red"), (1, "black")):
        y = py / 2 - 1.0 + 2.0 * k
        s.add(f"pl{k}", tube([(px, y, pz / 2), (px + 20, y, pz / 2), (px + 30, y, pz / 2)], 0.5), COL[colr])
    s.add("ph_plug", M.box(px + 30, py / 2 - 3.0, pz / 2 - 2.2, px + 36, py / 2 + 3.0, pz / 2 + 2.2).val(), KK)
    s.anchor("ph_plug", (px + 36, py / 2, pz / 2 + 2.2), on="ph_plug")
    # PG1: its socket 12 mm away (unplugged), red and black leads
    sx = px + 48
    s.add("pg1", M.box(sx, py / 2 - 3.2, pz / 2 - 2.6, sx + 7, py / 2 + 3.2, pz / 2 + 2.6).val(), KK)
    s.anchor("pg1", (sx + 3.5, py / 2 + 3.2, pz / 2 + 2.6), on="pg1")
    yr, yb = py / 2 - 1.0, py / 2 + 1.0
    s.add("pg_r", tube([(sx + 7, yr, pz / 2), (sx + 26, yr - 10, pz / 2), (sx + 40, yr - 14, pz / 2)], 0.5), COL["red"])
    s.add("splice", cyl(1.25, (sx + 36, yr - 14, pz / 2), (sx + 48, yr - 14, pz / 2)), SHRINK)
    s.add("plus", tube([(sx + 44, yr - 14, pz / 2), (sx + 80, yr - 14, pz / 2)], 0.75), COL["red"])
    s.add("plus_band", cyl(0.81, (sx + 52, yr - 14, pz / 2), (sx + 55, yr - 14, pz / 2)), COL["black"])
    s.anchor("splice", (sx + 42, yr - 14, pz / 2 + 1.25), on="splice")
    s.anchor("plus", (sx + 70, yr - 14, pz / 2 + 0.75), on="plus")
    s.add("pg_b", tube([(sx + 7, yb, pz / 2), (sx + 26, yb + 10, pz / 2), (sx + 80, yb + 16, pz / 2)], 0.5), COL["black"])
    s.anchor("minus", (sx + 53, yb + 13.0, pz / 2 + 0.5), on="pg_b")
    R("pack_pg1", s, (0.3, -0.5, 1), up=(0, 1, 0), fit=(330, 150), line=0.5)


# ------------------------------------------------------------------ cover icons
@scene
def p_rt1():
    s = r3d.Scene()
    s.add("bead", cq.Solid.makeSphere(1.6, cq.Vector(0, 0, 0)), EPOXY)
    for k in (-1, 1):
        s.add(f"w{k}", tube([(k * 0.5, -1.4, 0), (k * 1.2, -8, 0), (k * 1.2, -40, 0)], 0.35), COL["white"])
    R("p_rt1", s, (0, -0.3, 1), up=(1, 0, 0), fit=(150, 50), line=0.5)


@scene
def p_kk():
    s = r3d.Scene()
    s.add("kk", M.box(-5.1, 0, 0, 5.1, 12.7, 6.3).val(), KK)
    for k in range(3):                          # three 1-way 0.1 in housings (the XJ1 end)
        s.add(f"du{k}", M.box(28 + 4.5 * k, 3.0, 0.9, 30.6 + 4.5 * k, 17.0, 3.5).val(), BLACK)
    for k in range(6):                          # three KK crimps, three 0.1 in crimps
        s.add(f"c{k}", M.box(46 + 5 * k, 4, 0, 47.2 + 5 * k, 18, 1.2).val(), GOLD)
    R("p_kk", s, (0.3, -0.5, 1), up=(0, 1, 0), fit=(150, 70), line=0.5)


@scene
def p_pack():
    s = r3d.Scene()
    px, py, pz = pack(s)
    for k, colr in ((0, "red"), (1, "black")):
        y = py / 2 - 1.0 + 2.0 * k
        s.add(f"pl{k}", tube([(px, y, pz / 2), (px + 25, y, pz / 2)], 0.6), COL[colr])
    s.add("ph", M.box(px + 25, py / 2 - 3, pz / 2 - 2.2, px + 31, py / 2 + 3, pz / 2 + 2.2).val(), KK)
    s.add("pg1", M.box(px + 40, py / 2 - 3.2, pz / 2 - 2.6, px + 47, py / 2 + 3.2, pz / 2 + 2.6).val(), KK)
    for k, colr in ((0, "red"), (1, "black")):
        y = py / 2 - 1.0 + 2.0 * k
        s.add(f"gl{k}", tube([(px + 47, y, pz / 2), (px + 70, y, pz / 2)], 0.6), COL[colr])
    R("p_pack", s, (0.3, -0.5, 1), up=(0, 1, 0), fit=(150, 75), line=0.45)


@scene
def p_wires():
    s = r3d.Scene()
    for k, (body, band) in enumerate((("black", None), ("black", None), ("yellow", None), ("blue", None))):
        y = 3.4 * k
        s.add(f"w{k}", tube([(0, y, 0), (60, y, 0)], 0.7 if k < 2 else 0.55), COL[body])
    s.add("hs", cyl(1.3, (0, 16, 0), (25, 16, 0)), SHRINK)
    s.add("hs2", cyl(1.3, (32, 16, 0), (57, 16, 0)), SHRINK)
    R("p_wires", s, (0, -0.4, 1), up=(0, 1, 0), fit=(150, 60), line=0.5)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    for n in names:
        SCENES[n]()
