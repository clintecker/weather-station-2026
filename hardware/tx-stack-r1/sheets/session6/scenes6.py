"""Session 6 (wire the backplane) illustrations, same pipeline as Sessions 2-5 (r3d: hidden lines + flat colour).

Geometry, read-only: the PAD3U piece from session1/v2/models.py (b_region: the plated end, lines 0-30 x holes 1-38),
the sockets, parts, bus wires and leads from layout/stack.py (BP_PARTS, BP_BUS, MUX_BOX, WIRES), the mux's pads and
lead paths from layout/muxleads.py (Adafruit's own #5626 board file). build/BACKPLANE.md (via bpmd.py) gives the page
facts and is cross-checked against stack on import.

Board frame (session1's): x along the lines (line 0 left seen from the front), y along the holes (hole 1 at the
bottom), z out of the FRONT (component face) at z = 1.6; the copper face is z = 0 and "behind" is z < 0.

Run ONE scene per process (a multi-scene run segfaults partway and still exits 0):
  .venv-cad/bin/python -B scenes6.py NAME
  .venv-cad/bin/python -B scenes6.py list
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

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import stack as st                      # noqa: E402
import muxleads as ML                   # noqa: E402
import bpmd                             # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
P = M.P
T = M.PAD_T                             # 1.6: the front face
SX = M.B_SCORE_X
BX0, BZ0 = SX - 6.51, 48.71             # board frame -> box frame (session1 scenes.py)

BLACK = "#1E1E1E"
GOLD = "#D9AE3F"
SOLDER = "#A9AEB4"
MUXPCB = "#25283A"
JST = "#EFE8D8"
FOAM = "#E9E5DA"
RES = "#D9C9A3"
TAPE = "#F4F1E8"
DOT = {"blue": "#2D6FD0", "green": "#2E9E4F", "yellow": "#FFD400", "red": "#E8202A"}
COL = {"red": "#D7262E", "black": "#1C1C1C", "yellow": "#F2C318", "blue": "#2D6FD0", "green": "#2E9E48",
       "white": "#F2F2F2"}
# the mux leads' colours (Adafruit 1311 set: black, red, yellow, green, blue, white): power red, ground black,
# every clock yellow, every data blue, reset green
MUX_COL = {"VIN": "red", "GND": "black", "SCL": "yellow", "SDA": "blue", "RESET": "green",
           **{f"SD{k}": "blue" for k in range(4)}, **{f"SC{k}": "yellow" for k in range(4)}}
LINK_COL = {(2, 38): "black", (19, 5): "red", (21, 5): "red"}
# the EVM and pack leads (BACKPLANE.md: 24 AWG stranded): body colour, band colour or None, flag text
EVM_COL = {"PG1 lead +": ("red", "black", "PACK +"), "U1 battery + (J5 BATTERY)": ("red", "black", "J5 BAT"),
           "U1 system out (J3 SYS)": ("red", "black", "J3 SYS"), "U1 system ground (J3 GND)": ("black", None, "J3 GND"),
           "U1 battery sense (J5 SNS_BATP)": ("white", "red", "J5 SNS")}


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def R(name, s, d, up=(0, 1, 0), fit=(300, 300), **kw):
    import handed
    handed.board_frame(s, BX0, BZ0)              # every picture here is drawn in the PAD3U board frame
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


# ------------------------------------------------------------------ cross-checks: BACKPLANE.md against stack.py
SOCK = {st.model.SOCKETS[b]: (b, st.SOCKET_HOLE[b], st.model.KEY[b], st.model.KEY_COLOUR[b]) for b in st.BOARDS}
for ref, d in bpmd.SOCKETS.items():
    assert SOCK[ref] == (d["card"], d["hole"], d["key"], d["colour"]), (ref, d, SOCK[ref])
_bus = {i: hs for i, hs in st.BP_BUS}
for ln, net, a, b, cut, holes in bpmd.BUS:
    assert _bus[ln] == holes and holes[0] == a and holes[-1] == b, (ln, holes, _bus.get(ln))
assert sorted(_bus) == sorted(r[0] for r in bpmd.BUS)
_front = {(ref, ln, hl) for ref, pins, _n in st.BP_PARTS if not ref.startswith("XB") for h in pins.values()
          for ln, hl in [tuple(int(v) for v in h[1:].split("."))]}
assert _front == {(r[0], r[3], r[4]) for r in bpmd.FRONT}, (_front, bpmd.FRONT)
for pad, ln, hl, cut in bpmd.MUX_LEADS:
    assert ML.target()[pad] == (ln, hl) and ML.cut(pad) == cut, (pad, ln, hl, cut)
ISO = {(ln, bpmd.SOCKETS[ref]["hole"]) for ref, lines in bpmd.ISOLATED.items() for ln in lines}
assert ISO == {(i, n) for i, n in st.BP_ISOLATED if i >= 19}, ISO ^ st.BP_ISOLATED


# ------------------------------------------------------------------ geometry helpers
def X(line):
    return M.B_FAR + (M.B_LINE0_ROW + line - 1) * P


def Y(hole):
    return M.B_SIDE + (hole - 1) * P


def pt(line, hole, d=0.0):
    """(line, hole, mm behind the copper face) -> board frame."""
    return (X(line), Y(hole), -d)


def cyl(r, a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    v = b - a
    L = float(np.linalg.norm(v))
    return cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*(v / L)))


def simplify(pts):
    out = [tuple(map(float, pts[0]))]
    for p in pts[1:]:
        p = tuple(map(float, p))
        if np.linalg.norm(np.array(p) - np.array(out[-1])) < 1e-6:
            continue
        if len(out) >= 2:
            a, b = np.array(out[-2]), np.array(out[-1])
            d1, d2 = b - a, np.array(p) - b
            if np.linalg.norm(np.cross(d1, d2)) < 1e-6 and d1 @ d2 > 0:
                out[-1] = p
                continue
        out.append(p)
    return out


def tube(pts, r):
    pts = simplify(pts)
    sol = [cyl(r, a, b) for a, b in zip(pts[:-1], pts[1:])]
    sol += [cq.Solid.makeSphere(r, cq.Vector(*p)) for p in pts[1:-1]]
    s = sol[0]
    for x in sol[1:]:
        s = s.fuse(x)
    return s.clean()


def comp(shapes):
    shapes = [x.val() if isinstance(x, cq.Workplane) else x for x in shapes if x is not None]
    return cq.Compound.makeCompound(shapes)


def joint(line, hole, face="copper", r=0.95):
    """A solder joint: a low cone on the pad."""
    x, y = X(line), Y(hole)
    if face == "copper":
        return cq.Solid.makeCone(r, 0.35, 0.7, cq.Vector(x, y, -0.06), cq.Vector(0, 0, -1))
    return cq.Solid.makeCone(r, 0.35, 0.7, cq.Vector(x, y, T + 0.06), cq.Vector(0, 0, 1))


# ------------------------------------------------------------------ the parts
def board(x0=None, x1=None, y0=0.0, y1=None):
    x0 = SX if x0 is None else x0
    x1 = M.B_L if x1 is None else x1
    return M.b_region(x0, x1, y0, y1)


SOCK_H = 8.5


def socket(hole):
    """Generic female strip cut to 1x30 (lines 1-30), soldered: body, contact mouths, tails and joints."""
    body = M.box(X(1) - P / 2 + 0.05, Y(hole) - 1.25, T, X(30) + P / 2 - 0.05, Y(hole) + 1.25, T + SOCK_H)
    mouths = [cq.Workplane("XY").box(1.0, 1.0, 2.0).translate((X(i), Y(hole), T + SOCK_H)).val() for i in range(1, 31)]
    body = body.cut(cq.Workplane("XY").add(mouths))
    tails = [cyl(0.3, (X(i), Y(hole), T), (X(i), Y(hole), -2.2)) for i in range(1, 31)]
    joints = [joint(i, hole) for i in range(1, 31)]
    return body, comp(tails), comp(joints)


def key_plug(line, hole, proud=0.0):
    """A pin pulled from the male header stock, long end pushed into the contact (proud = mm above the mouth)."""
    top = T + SOCK_H + proud
    return M.box(X(line) - 0.32, Y(hole) - 0.32, top - 6.0, X(line) + 0.32, Y(hole) + 0.32, top)


def colour_dot(b):
    ref = st.model.SOCKETS[b]
    h = bpmd.SOCKETS[ref]["hole"]
    return (cq.Workplane("XY").workplane(offset=T + 0.06).center((X(1) + X(2)) / 2, Y(h) + 1.5 * P)
            .circle(1.6).extrude(0.08).val(), DOT[bpmd.SOCKETS[ref]["colour"]])


def male_pin(line, hole):
    """XJ1: one 0.1 in male pin from the header stock, plastic on the front, soldered on the copper side."""
    x, y = X(line), Y(hole)
    plastic = M.box(x - 1.25, y - 1.25, T, x + 1.25, y + 1.25, T + 2.5)
    pin = M.box(x - 0.32, y - 0.32, -2.6, x + 0.32, y + 0.32, T + 2.5 + 6.0)
    return plastic, pin, joint(line, hole)


def resistor(a, b, tail=1.6):
    """Axial 100 ohm lying flat on the front between holes a and b (line, hole); legs through, joints behind.
    tail: how far each leg's end stands proud of the copper face (R7's free leg stays long for the sense lead)."""
    pa, pb = np.array((X(a[0]), Y(a[1]))), np.array((X(b[0]), Y(b[1])))
    u = (pb - pa) / np.linalg.norm(pb - pa)
    mid = (pa + pb) / 2
    rb, Lb = 1.15, 6.0
    zc = T + rb
    c0 = (*(mid - u * Lb / 2), zc)
    body = cyl(rb, c0, (*(mid + u * Lb / 2), zc))
    bands = []
    for k, (off, colr) in enumerate(((0.9, "#7B4A2A"), (1.7, "#1A1A1A"), (2.5, "#7B4A2A"), (4.9, "#C9A227"))):
        s0 = mid - u * Lb / 2 + u * off
        bands.append((cyl(rb + 0.04, (*s0, zc), (*(s0 + u * 0.45), zc)), colr))
    legs = []
    for p, sgn, tl in ((pa, -1, tail if isinstance(tail, (int, float)) else tail[0]),
                       (pb, 1, tail if isinstance(tail, (int, float)) else tail[1])):
        e = mid + sgn * u * Lb / 2
        legs.append(tube([(*e, zc), (*p, zc), (*p, -tl)], 0.3))
    return body, bands, comp(legs)


def mux_parts(bridged=True):
    """Adafruit #5626 in its own frame (x along its 40.64, y along 20.32, the BACK face at z = 0, top at 1.6),
    from Adafruit's board file (layout/muxleads.py): PCB with its JP1 header holes and two mounting holes, the nine
    JST SH sockets, the PCA9548, SW1, the 8 channel 0-3 test pads and the A0 jumper on the back face."""
    pcb = M.box(0, 0, 0, 40.64, 20.32, ML.PCB)
    holes = [(ML.JP1_X, y, 0.5) for y in ML.JP1.values()] + [(2.54, 2.54, 1.25), (2.54, 17.907, 1.25)]
    for x, y, r in holes:
        pcb = pcb.cut(cq.Workplane("XY").center(x, y).circle(r).extrude(5).translate((0, 0, -1)))
    gold = []
    for x, y, r in holes:
        for z in (-0.04, ML.PCB):
            gold.append(cq.Workplane("XY").workplane(offset=z).center(x, y).circle(r + 0.55).circle(r).extrude(0.04).val())
    for x in ML.TP.values():
        gold.append(cq.Workplane("XY").workplane(offset=-0.04).center(x, ML.TP_Y).circle(0.75).extrude(0.04).val())
        gold.append(cq.Workplane("XY").workplane(offset=-0.04).center(x, 20.32 - ML.TP_Y).circle(0.75).extrude(0.04).val())
    ax, ay = ML.A0
    for dy in (-0.55, 0.55):
        gold.append(M.box(ax - 0.5, ay + dy - 0.35, -0.04, ax + 0.5, ay + dy + 0.35, 0).val())
    blob = M.box(ax - 0.45, ay - 0.25, -0.08, ax + 0.45, ay + 0.25, 0).val() if bridged else None
    jst = []
    for x, y, face in [(8.89, 0, -1), (16.51, 0, -1), (24.13, 0, -1), (31.75, 0, -1),
                       (8.89, 20.32, 1), (16.51, 20.32, 1), (24.13, 20.32, 1), (31.75, 20.32, 1)]:
        y0, y1 = (0.6, 5.0) if face < 0 else (15.32, 19.72)
        b = M.box(x - 3.0, y0, ML.PCB, x + 3.0, y1, ML.PCB + 2.9)
        mouth = M.box(x - 2.2, y0 - 0.1 if face < 0 else y1 - 1.6, ML.PCB + 0.6, x + 2.2,
                      y0 + 1.6 if face < 0 else y1 + 0.1, ML.PCB + 2.3)
        jst.append(b.cut(mouth).val())
    up = M.box(0.6, 7.16, ML.PCB, 5.0, 13.16, ML.PCB + 2.9)
    jst.append(up.cut(M.box(0.5, 7.96, ML.PCB + 0.6, 2.1, 12.36, ML.PCB + 2.3)).val())
    chip_ = M.box(22.86 - 3.9, 10.16 - 2.2, ML.PCB, 22.86 + 3.9, 10.16 + 2.2, ML.PCB + 1.1)
    sw = M.box(31.75 - 3.3, 10.16 - 1.3, ML.PCB, 31.75 + 3.3, 10.16 + 1.3, ML.PCB + 1.4)
    knob = M.box(31.75 + 0.3, 10.16 - 0.5, ML.PCB + 1.4, 31.75 + 1.6, 10.16 + 0.5, ML.PCB + 2.2)
    small = [M.box(x - 0.8, y - 0.45, ML.PCB, x + 0.8, y + 0.45, ML.PCB + 0.5).val()
             for x, y in ((16.0, 13.6), (4.19, 5.97), (7.49, 11.43), (35.56, 15.75), (10.41, 11.81), (17.27, 9.02),
                          (14.35, 11.3), (8.13, 7.87), (4.45, 14.1))]
    return dict(pcb=(pcb, MUXPCB), gold=(comp(gold), GOLD), jst=(comp(jst), JST), chip=(chip_, BLACK),
                sw=(comp([sw, knob]), "#3C3C3C"), small=(comp(small), "#2E2E2E"),
                **({"a0": (blob, SOLDER)} if bridged else {}))


def mux_to_board():
    """(R, origin) of the mux frame in the board frame: x along the lines, its y = 0 edge toward hole 10 (so y runs
    down the holes), its back face on the foam against the copper face (so its z runs away from the board)."""
    R_ = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)
    o = np.array(pt(ML.MUX_LINE0, ML.MUX_HOLE0, ML.FOAM))
    return R_, o


def mux_board_pt(x, y, z):
    R_, o = mux_to_board()
    return tuple(R_ @ np.array((x, y, z)) + o)


def add_mux_placed(s, bridged=True):
    import scenes as S1                   # session1/v2: rigid placement
    R_, o = mux_to_board()
    for nm, (shp, colr) in mux_parts(bridged).items():
        placed, _ = S1.place(shp, R_[:, 0], R_[:, 1], o)
        s.add("mux_" + nm, placed, colr, 0.6 if nm in ("gold", "small") else 1.0)
    s.placed_by("#5626 mux frame -> board frame", R_)
    x0, y0, _ = pt(ML.MUX_LINE0, ML.MUX_HOLE0, 0)
    s.add("foam", M.box(x0 + 4.0, y0 - 16.0, -ML.FOAM, x0 + 36.0, y0 - 4.5, 0), FOAM)


def lead_pts(pad):
    return [pt(l, h, d) for l, h, d in ML.path(pad)]


def insulated_lead(pts, r, bare_head=1, bare_tail=2):
    """An insulated wire along pts: the first bare_head and last bare_tail segments bare (thin, tinned)."""
    pts = [tuple(map(float, p)) for p in pts]
    ins = pts[bare_head:len(pts) - bare_tail + 1] if bare_tail else pts[bare_head:]
    body = tube(ins, r) if len(ins) >= 2 else None
    bare = []
    if bare_head:
        bare.append(tube(pts[:bare_head + 1], 0.32))
    if bare_tail:
        bare.append(tube(pts[-bare_tail - 1:], 0.32))
    return body, comp(bare)


def add_mux_leads(s, pads=None, colour=True):
    for pad in pads or [p for p, *_ in bpmd.MUX_LEADS]:
        body, bare = insulated_lead(lead_pts(pad), ML.WIRE_R, 1, 2)
        s.add(f"ml_{pad}", body, COL[MUX_COL[pad]] if colour else "#DDDDDD")
        s.add(f"mlb_{pad}", bare, SOLDER, 0.6)
        ln, hl = ML.target()[pad]
        s.add(f"mlj_{pad}", joint(ln, hl, "front"), SOLDER, 0.6)


def link_pts(a, b, lift=1.4):
    return [pt(*a, -T - 1.0), pt(*a, 0), pt(*a, lift), pt(*b, lift), pt(*b, 0), pt(*b, -T - 1.0)]


def add_links(s, only=None):
    for a, b, _w, _c in bpmd.JUMPERS:
        if only is not None and a not in only:
            continue
        body, bare = insulated_lead(link_pts(a, b), ML.WIRE_R, 2, 2)
        s.add(f"lk_{a[0]}_{a[1]}", body, COL[LINK_COL[a]])
        s.add(f"lkb_{a[0]}_{a[1]}", bare, SOLDER, 0.6)
        s.add(f"lkj_{a[0]}_{a[1]}", comp([joint(*a, "front"), joint(*b, "front")]), SOLDER, 0.6)


EVM_R = 0.7                              # 24 AWG stranded, insulated
DROP = 26.0                              # how far the loose ends hang below the board's hole-1 edge (drawn)


def evm_path(frm, ln, hl):
    """Backplane end of each EVM / pack lead: in from the copper side (or lapped on R7's free leg), then down the
    copper face, past the board's lower edge, to its tape flag."""
    yb = -DROP
    if frm.startswith("U1 battery sense"):          # lapped along R7's free leg on the copper side
        return [pt(ln, hl, 4.6), pt(ln, hl, 2.4), pt(ln, 4, 2.4), pt(ln, 0.0, 2.4), (X(ln), yb, -2.4)], False
    if hl == 11:                                     # the charger ground lead: above the mux, beside SYS (line 26)
        return [pt(ln, hl, -T - 1.0), pt(ln, hl, 0), pt(ln, hl, 4.0), pt(ln + 0.4, 11.4, 4.0), pt(25.5, 11.4, 4.0),
                pt(25.5, 4, 2.4), pt(25.5, 0.0, 2.4), (X(25.5), yb, -2.4)], True
    return [pt(ln, hl, -T - 1.0), pt(ln, hl, 0), pt(ln, hl, 2.4), pt(ln, 4, 2.4), pt(ln, 0.0, 2.4),
            (X(ln), yb, -2.4)], True


def add_evm_leads(s, flags=True):
    for frm, ln, hl, what, to in bpmd.EVM:
        body_c, band_c, flag = EVM_COL[frm]
        pts, thru = evm_path(frm, ln, hl)
        body, bare = insulated_lead(pts, EVM_R, 2 if thru else 1, 0)
        key = flag.replace(" ", "").replace("+", "P")
        s.add(f"ev_{key}", body, COL[body_c])
        s.add(f"evb_{key}", bare, SOLDER, 0.6)
        if thru:
            s.add(f"evj_{key}", joint(ln, hl, "front"), SOLDER, 0.6)
        else:
            s.add(f"evj_{key}", cq.Solid.makeSphere(0.9, cq.Vector(*pt(ln, hl, 3.6))), SOLDER, 0.6)
        xe, ye, ze = pts[-1]
        if band_c:
            s.add(f"evband_{key}", cyl(EVM_R + 0.06, (xe, ye + 8.0, ze), (xe, ye + 5.5, ze)), COL[band_c])
        if flags:
            s.add(f"evtape_{key}", cyl(EVM_R + 0.35, (xe, ye + 0.6, ze), (xe, ye - 4.0, ze)), TAPE)
            s.add(f"evflag_{key}", M.box(xe - 0.25, ye - 3.0, ze - 5.5, xe + 0.25, ye + 3.0, ze), TAPE)
            s.anchor(f"flag_{key}", (xe, ye, ze - 3.0))
        s.anchor(f"ev_{key}", pts[-3] if len(pts) > 3 else pts[-2])


def bus_wire(ln, holes):
    z = -0.06 - M.P * 0 - 0.32
    return cyl(0.32, (X(ln), Y(holes[0]) - 0.4, z), (X(ln), Y(holes[-1]) + 0.4, z))


def add_bus(s, lines=None, joints=True):
    for ln, net, a, b, cut, holes in bpmd.BUS:
        if lines is not None and ln not in lines:
            continue
        s.add(f"bus{ln}", bus_wire(ln, holes), SOLDER, 0.8)
        if joints:
            s.add(f"busj{ln}", comp([cq.Solid.makeSphere(0.8, cq.Vector(X(ln), Y(h), -0.3)) for h in holes]), SOLDER, 0.5)


def add_board(s, x0=None, x1=None, y0=0.0, y1=None, weight=0.15):
    b, cu = board(x0, x1, y0, y1)
    s.add("board", b, M.FR4).add("pads", cu, M.TIN, weight)


def add_sockets(s, keys=True, dots=True, proud=None):
    for b in st.BOARDS:
        ref = st.model.SOCKETS[b]
        d = bpmd.SOCKETS[ref]
        body, tails, joints = socket(d["hole"])
        s.add(f"sock_{ref}", body, BLACK).add(f"tail_{ref}", tails, GOLD, 0.5).add(f"sj_{ref}", joints, SOLDER, 0.5)
        if keys:
            s.add(f"key_{ref}", key_plug(d["key"], d["hole"], (proud or {}).get(ref, 0.0)), GOLD)
        if dots:
            shp, colr = colour_dot(b)
            s.add(f"dot_{ref}", shp, colr)
        s.anchor(f"sock_{ref}", (X(5), Y(d["hole"]), T + SOCK_H))
        s.anchor(f"sockend_{ref}", (X(30) + P / 2, Y(d["hole"]), T + SOCK_H / 2))
        s.anchor(f"key_{ref}", (X(d["key"]), Y(d["hole"]), T + SOCK_H))
        s.anchor(f"dot_{ref}", ((X(1) + X(2)) / 2, Y(d["hole"]) + 1.5 * P, T + 0.1))


def add_front_parts(s, xj=True, res=True, r7_tail=6.0):
    if xj:
        pl, pins, js = [], [], []
        for ref, note, pin, ln, hl, net in bpmd.FRONT:
            if ref == "XJ1":
                a, b, j = male_pin(ln, hl)
                pl.append(a), pins.append(b), js.append(j)
                s.anchor(f"xj_{ln}", (X(ln), Y(hl) + 1.25, T + 2.5))
        s.add("xj1", comp(pl), BLACK).add("xj1_pins", comp(pins), GOLD).add("xj1_j", comp(js), SOLDER, 0.5)
    if res:
        f = {(r[0], r[2]): (r[3], r[4]) for r in bpmd.FRONT}
        for ref in ("R7", "R8"):
            a, b = f[(ref, "1")], f[(ref, "2")]
            body, bands, legs = resistor(a, b, (1.6, r7_tail) if ref == "R7" else 1.6)
            s.add(ref, body, RES).add(f"{ref}_legs", legs, M.STEEL, 0.7)
            for k, (bd, colr) in enumerate(bands):
                s.add(f"{ref}_band{k}", bd, colr, 0.4)
            s.add(f"{ref}_j", comp([joint(*a), joint(*b)]), SOLDER, 0.5)
            s.anchor(ref, ((X(a[0]) + X(b[0])) / 2, (Y(a[1]) + Y(b[1])) / 2, T + 2.3))


def hole_anchors(s, z, which, drawn=True):
    """drawn=False where a lead fills the hole in this view (the ring still has to land on the anchor)."""
    for ln, hl in which:
        s.hole(f"h{ln}_{hl}", (X(ln), Y(hl), z), drawn)


def axis_anchors(s, z, lines=range(0, 31), holes=range(1, 39)):
    for ln in lines:
        s.anchor(f"L{ln}", (X(ln), Y(1) - 2.6, z))
        s.anchor(f"Lt{ln}", (X(ln), Y(38) + 2.6, z))
    for hl in holes:
        s.anchor(f"H{hl}", (SX - 1.0, Y(hl), z))
        s.anchor(f"Hr{hl}", (M.B_L + 1.0, Y(hl), z))


def everything(s, bus=True, mux=True, links=True, evm=True, front=True, sockets=True):
    add_board(s)
    if sockets:
        add_sockets(s)
    if front:
        add_front_parts(s)
    if mux:
        add_mux_placed(s)
        add_mux_leads(s)
    if links:
        add_links(s)
    if evm:
        add_evm_leads(s)
    if bus:
        add_bus(s)


FRONT_V = ((0, 0, 1), (0, 1, 0))
BACK_V = ((0, 0, -1), (0, 1, 0))


# ------------------------------------------------------------------ overview: front and copper side, all done
@scene
def ov_front():
    s = r3d.Scene()
    everything(s)
    axis_anchors(s, T)
    R("ov_front", s, *FRONT_V, fit=(250, 330), line=0.3, outline=1.0)


@scene
def ov_copper():
    s = r3d.Scene()
    everything(s)
    axis_anchors(s, -6)
    s.anchor("mux", pt(9.5, 5.5, 6.0))
    R("ov_copper", s, *BACK_V, fit=(250, 330), line=0.3, outline=1.0)


# ------------------------------------------------------------------ key plugs and dots
@scene
def k_front():
    """Front, the sockets as Clint has them plus key plugs and dots: hole callouts on the four key contacts."""
    s = r3d.Scene()
    add_board(s)
    add_sockets(s)
    axis_anchors(s, T)
    for ref, d in bpmd.SOCKETS.items():
        s.anchor(f"kc_{ref}", (X(d["key"]), Y(d["hole"]), T + SOCK_H))
    R("k_front", s, *FRONT_V, fit=(330, 330), line=0.3, outline=1.0)


def _key_zoom(name, proud, cut=False):
    s = r3d.Scene()
    d = bpmd.SOCKETS["XB4"]
    h = d["hole"]
    add_board(s, X(25) - P / 2, M.B_L, Y(h - 3) - P / 2, Y(h + 3) + P / 2, 0.3)
    body, tails, joints = socket(h)
    s.add("sock", body, BLACK).add("tails", tails, GOLD, 0.5).add("sj", joints, SOLDER, 0.5)
    s.add("plug", key_plug(d["key"], h, proud), GOLD)
    s.anchor("plug_top", (X(d["key"]), Y(h), T + SOCK_H + proud))
    s.anchor("mouth", (X(d["key"]), Y(h) - 0.5, T + SOCK_H))
    s.anchor("c29", (X(29), Y(h), T + SOCK_H))
    if cut:
        s.anchor("cut", (X(d["key"]) + 0.32, Y(h), T + SOCK_H))
    R(name, s, (0.55, -1, 0.75), up=(0, 0, 1), fit=(170, 150), line=0.5,
      crop=((X(28.5), Y(h), T + SOCK_H), 9, 9))


@scene
def k_push():
    _key_zoom("k_push", 4.0)


@scene
def k_flush():
    _key_zoom("k_flush", 0.0, True)


@scene
def k_pin():
    """One pin pulled from the male header stock: 0.64 square, the long end and the short end."""
    s = r3d.Scene()
    s.add("strip", comp([M.box(i * P - 1.25, -1.25, 0, i * P + 1.25, 1.25, 2.5).val() for i in range(4)]), BLACK)
    s.add("pins", comp([M.box(i * P - 0.32, -0.32, -3.0, i * P + 0.32, 0.32, 8.5).val() for i in range(4)]), GOLD)
    s.add("loose", M.box(4 * P + 3 - 0.32, -0.32, 4.0, 4 * P + 3 + 0.32, 0.32, 15.5), GOLD)
    s.anchor("loose", (4 * P + 3, 0, 13.0))
    s.anchor("long", (4 * P + 3, 0, 8.0))
    s.anchor("strip", (1.5 * P, -1.25, 1.2))
    R("k_pin", s, (0.4, -1, 0.35), up=(0, 0, 1), fit=(140, 120), line=0.6)


# ------------------------------------------------------------------ the front parts: XJ1, R7, R8
FP_X0, FP_X1 = X(0) - P, X(26) + P / 2
FP_Y0, FP_Y1 = Y(4) - P / 2, Y(14) + P / 2


@scene
def f_parts():
    s = r3d.Scene()
    add_board(s, SX, FP_X1, FP_Y0, FP_Y1, 0.3)
    body, tails, joints = socket(13)
    s.add("sock", M.box(SX + 0.1, Y(13) - 1.25, T, FP_X1 - 0.1, Y(13) + 1.25, T + SOCK_H).intersect(body), BLACK)
    add_front_parts(s)
    hole_anchors(s, T, [(r[3], r[4]) for r in bpmd.FRONT])
    axis_anchors(s, T, range(0, 27), range(4, 15))
    R("f_parts", s, *FRONT_V, fit=(520, 230), line=0.45, outline=1.1,
      crop=(((FP_X0 + FP_X1) / 2, (FP_Y0 + FP_Y1) / 2, T), (FP_X1 - FP_X0) / 2 + 1, (FP_Y1 - FP_Y0) / 2 + 1))


@scene
def f_res_iso():
    s = r3d.Scene()
    add_board(s, X(19) - P / 2, X(26) + P / 2, Y(5) - P / 2, Y(12) + P / 2, 0.3)
    add_front_parts(s, xj=False)
    s.anchor("r7_free", (X(24), Y(7), -5.0))
    R("f_res_iso", s, (-0.35, -1, 0.8), up=(0, 0, 1), fit=(250, 170), line=0.5)


@scene
def f_xj_iso():
    s = r3d.Scene()
    add_board(s, X(0) - P / 2, X(12) + P / 2, Y(8) - P / 2, Y(14) + P / 2, 0.3)
    add_front_parts(s, res=False)
    R("f_xj_iso", s, (-0.35, -1, 0.8), up=(0, 0, 1), fit=(250, 170), line=0.5)


# ------------------------------------------------------------------ the mux
def _mux_alone(name, face, bridged, leads, fit=(250, 150)):
    s = r3d.Scene()
    for nm, (shp, colr) in mux_parts(bridged).items():
        s.add("mux_" + nm, shp, colr, 0.6 if nm in ("gold", "small") else 1.0)
    z_back, z_top = 0.0, ML.PCB
    for pad, x in ML.TP.items():
        s.anchor(f"tp_{pad}", (x, ML.TP_Y, z_back))
    for pad, y in ML.JP1.items():
        s.anchor(f"jp_{pad}", (ML.JP1_X, y, z_top if face == "top" else z_back))
    s.anchor("a0", (*ML.A0, z_back))
    s.anchor("sw1", (31.75, 10.16, z_top + 1.6))
    s.anchor("up_qt", (2.8, 10.16, z_top + 1.5))
    s.anchor("ch_edge", (20.0, 0.0, z_top))
    if leads:                                         # straight stubs as they come off the pads, before routing
        for pad, x in ML.TP.items():
            pts = [(x, ML.TP_Y, -0.35), (x, -1.0, -0.35), (x, -9.0, -0.35)]
            b, bare = insulated_lead(pts, ML.WIRE_R, 1, 0)
            s.add(f"st_{pad}", b, COL[MUX_COL[pad]]).add(f"stb_{pad}", bare, SOLDER, 0.6)
            s.anchor(f"end_{pad}", pts[-1])
        for pad, y in ML.JP1.items():
            pts = [(ML.JP1_X, y, -0.3), (ML.JP1_X, y, ML.PCB + 1.0), (40.64 + 9.0, y, ML.PCB + 1.0)]
            b, bare = insulated_lead(pts, ML.WIRE_R, 1, 0)
            s.add(f"st_{pad}", b, COL[MUX_COL[pad]]).add(f"stb_{pad}", bare, SOLDER, 0.6)
            s.anchor(f"end_{pad}", pts[-1])
    d = (0, 0, 1) if face == "top" else (0, 0, -1)
    up = (0, 1, 0) if face == "top" else (0, -1, 0)
    R(name, s, d, up=up, fit=fit, line=0.5)


@scene
def m_top():
    _mux_alone("m_top", "top", False, False)


@scene
def m_back():
    _mux_alone("m_back", "back", False, False)


@scene
def m_back_done():
    _mux_alone("m_back_done", "back", True, True, fit=(250, 190))


@scene
def m_top_done():
    _mux_alone("m_top_done", "top", True, True, fit=(250, 190))


MZ_X0, MZ_X1 = SX, X(20) + P / 2
MZ_Y0, MZ_Y1 = 0.0, Y(13) + P / 2


@scene
def m_mounted():
    s = r3d.Scene()
    add_board(s, MZ_X0, MZ_X1, MZ_Y0, MZ_Y1, 0.3)
    add_mux_placed(s)
    add_mux_leads(s)
    hole_anchors(s, 0.0, [(ln, hl) for _p, ln, hl, _c in bpmd.MUX_LEADS], drawn=False)
    for pad in ML.target():
        p0 = ML.path(pad)[0]
        s.anchor(f"pad_{pad}", pt(p0[0], p0[1], p0[2] + 0.4 if pad in ML.JP1 else 0.0))
    axis_anchors(s, -6, range(0, 21), range(1, 14))
    s.anchor("foam", pt(9.0, 4.0, ML.FOAM / 2))
    s.anchor("mux", pt(6.0, 5.0, ML.FOAM + 4.6))
    R("m_mounted", s, *BACK_V, fit=(520, 300), line=0.4, outline=1.1,
      crop=(((MZ_X0 + MZ_X1) / 2, (MZ_Y0 + MZ_Y1) / 2, 0), (MZ_X1 - MZ_X0) / 2 + 1, (MZ_Y1 - MZ_Y0) / 2 + 1))


@scene
def m_iso():
    s = r3d.Scene()
    add_board(s, MZ_X0, MZ_X1, MZ_Y0, MZ_Y1, 0.3)
    add_mux_placed(s)
    add_mux_leads(s)
    s.anchor("foam", pt(4.0, 3.0, ML.FOAM / 2))
    R("m_iso", s, (0.45, -0.8, -0.9), up=(0, 0, -1), fit=(250, 180), line=0.45)


# ------------------------------------------------------------------ copper links
@scene
def l_power():
    s = r3d.Scene()
    add_board(s, X(17) - P / 2, X(24) + P / 2, Y(2) - P / 2, Y(9) + P / 2, 0.3)
    add_links(s, [(19, 5), (21, 5)])
    hole_anchors(s, 0.0, [(19, 5), (20, 5), (21, 5), (22, 5)])
    axis_anchors(s, -2, range(17, 25), range(2, 10))
    R("l_power", s, *BACK_V, fit=(250, 230), line=0.5)


@scene
def l_ground():
    s = r3d.Scene()
    add_board(s, X(0) - P / 2, X(14) + P / 2, Y(35) - P / 2, M.B_W, 0.3)
    add_links(s, [(2, 38)])
    hole_anchors(s, 0.0, [(2, 38), (12, 38)])
    axis_anchors(s, -2, range(0, 15), range(35, 39))
    R("l_ground", s, *BACK_V, fit=(250, 120), line=0.5)


@scene
def l_iso():
    s = r3d.Scene()
    add_board(s, X(17) - P / 2, X(24) + P / 2, Y(2) - P / 2, Y(9) + P / 2, 0.3)
    add_links(s, [(19, 5), (21, 5)])
    R("l_iso", s, (0.4, -0.8, -0.9), up=(0, 0, -1), fit=(250, 150), line=0.5)


# ------------------------------------------------------------------ the EVM and pack leads (backplane end only)
EV_X0, EV_X1 = X(9) - P / 2, X(30) + P / 2


@scene
def e_leads():
    s = r3d.Scene()
    add_board(s, SX, M.B_L, 0.0, Y(15) + P / 2, 0.3)
    add_front_parts(s, xj=False)
    add_mux_placed(s)
    add_mux_leads(s)
    add_links(s, only=[(19, 5), (21, 5)])
    add_evm_leads(s)
    hole_anchors(s, 0.0, [(ln, hl) for _f, ln, hl, _w, _t in bpmd.EVM if hl != 7], drawn=False)
    s.anchor("r7_free", pt(24, 7, 4.6))
    axis_anchors(s, -6, range(0, 31), range(1, 16))
    R("e_leads", s, *BACK_V, fit=(520, 300), line=0.4, outline=1.1)


@scene
def e_flag():
    s = r3d.Scene()
    p0 = (0.0, 0.0, 0.0)
    pts = [(0, 30, 0), (0, 0, 0)]
    s.add("lead", tube(pts, EVM_R), COL["red"])
    s.add("band", cyl(EVM_R + 0.06, (0, 8.0, 0), (0, 5.5, 0)), COL["black"])
    s.add("tape", cyl(EVM_R + 0.35, (0, 0.6, 0), (0, -4.0, 0)), TAPE)
    s.add("flag", M.box(-0.25, -3.0, -11.0, 0.25, 3.0, 0), TAPE)
    s.text("flag", "J5 BAT", (0.26, 0.0, -6.0), (0, 1, 0), (0, 0, 1), 2.2, colour="#121212")
    s.anchor("tape", (0, -1.5, EVM_R + 0.35))
    s.anchor("flag", (0.26, 0, -9.5))
    s.anchor("band", (0, 6.7, EVM_R))
    R("e_flag", s, (1, -0.25, 0.3), up=(0, 0, 1), fit=(150, 120), line=0.6)


# ------------------------------------------------------------------ bus wires
@scene
def b_all():
    s = r3d.Scene()
    everything(s)
    axis_anchors(s, -6)
    for ln, net, a, b, cut, holes in bpmd.BUS:
        s.anchor(f"top{ln}", (X(ln), Y(b) + 0.4, -0.7))
        s.anchor(f"bot{ln}", (X(ln), Y(a) - 0.4, -0.7))
    R("b_all", s, *BACK_V, fit=(330, 420), line=0.3, outline=1.0)


B2_X0 = X(17) - P / 2


@scene
def b_power():
    s = r3d.Scene()
    add_board(s, B2_X0, M.B_L, Y(3) - P / 2, Y(37) + P / 2, 0.25)
    add_sockets(s, dots=False)
    add_front_parts(s, xj=False)
    add_links(s)
    add_evm_leads(s, flags=False)
    add_bus(s, lines=range(17, 31))
    for ln, net, a, b, cut, holes in bpmd.BUS:
        if ln >= 19:
            s.anchor(f"top{ln}", (X(ln), Y(b) + 0.4, -0.7))
    hole_anchors(s, 0.0, sorted(ISO))
    axis_anchors(s, -2, range(17, 31), range(3, 38))
    R("b_power", s, *BACK_V, fit=(300, 420), line=0.35, outline=1.0,
      crop=(((B2_X0 + M.B_L) / 2, (Y(3) + Y(37)) / 2, 0), (M.B_L - B2_X0) / 2 + 1, (Y(37) - Y(3)) / 2 + P))


# ------------------------------------------------------------------ cover thumbnails
@scene
def p_header():
    s = r3d.Scene()
    s.add("strip", comp([M.box(i * P - 1.25, -1.25, 0, i * P + 1.25, 1.25, 2.5).val() for i in range(10)]), BLACK)
    s.add("pins", comp([M.box(i * P - 0.32, -0.32, -3.0, i * P + 0.32, 0.32, 8.5).val() for i in range(10)]), GOLD)
    R("p_header", s, (0.4, -1, 0.5), up=(0, 0, 1), fit=(150, 70), line=0.6)


@scene
def p_res():
    s = r3d.Scene()
    b, bands, legs = (None, None, None)
    rb, Lb = 1.15, 6.0
    s.add("body", cyl(rb, (-3, 0, 0), (3, 0, 0)), RES)
    for k, (off, colr) in enumerate(((0.9, "#7B4A2A"), (1.7, "#1A1A1A"), (2.5, "#7B4A2A"), (4.9, "#C9A227"))):
        s.add(f"b{k}", cyl(rb + 0.04, (-3 + off, 0, 0), (-3 + off + 0.45, 0, 0)), colr, 0.4)
    s.add("legs", comp([cyl(0.3, (-3, 0, 0), (-14, 0, 0)), cyl(0.3, (3, 0, 0), (14, 0, 0))]), M.STEEL)
    for dx in (0, 1):
        pass
    R("p_res", s, (0.2, -1, 0.5), up=(0, 0, 1), fit=(150, 50), line=0.6)


@scene
def p_mux():
    s = r3d.Scene()
    for nm, (shp, colr) in mux_parts(False).items():
        s.add("mux_" + nm, shp, colr, 0.6 if nm in ("gold", "small") else 1.0)
    R("p_mux", s, (0.35, -0.8, 1), up=(0, 0, 1), fit=(150, 90), line=0.5)


@scene
def p_foam():
    s = r3d.Scene()
    s.add("foam", M.box(0, 0, 0, 32, 11.5, ML.FOAM), FOAM)
    s.add("liner", M.box(0, 0, ML.FOAM, 32, 11.5, ML.FOAM + 0.1), "#F4D35E")
    R("p_foam", s, (0.35, -0.8, 1), up=(0, 0, 1), fit=(150, 60), line=0.6)


@scene
def p_wire22():
    s = r3d.Scene()
    s.add("bare", cyl(0.32, (0, 0, 0), (60, 0, 0)), SOLDER)
    for k, c in enumerate(("red", "black", "yellow", "blue", "green")):
        s.add(f"w{k}", tube([(3, 4 + 3.4 * k, 0), (60, 4 + 3.4 * k, 0)], 0.8), COL[c])
        s.add(f"e{k}", cyl(0.32, (0, 4 + 3.4 * k, 0), (3, 4 + 3.4 * k, 0)), SOLDER)
    R("p_wire22", s, (0, -0.4, 1), up=(0, 1, 0), fit=(150, 70), line=0.5)


@scene
def p_wire24():
    s = r3d.Scene()
    for k, (body, band) in enumerate((("red", "black"), ("red", "black"), ("red", "black"), ("black", None),
                                      ("white", "red"))):
        y = 3.4 * k
        s.add(f"w{k}", tube([(0, y, 0), (60, y, 0)], 0.7), COL[body])
        if band:
            s.add(f"b{k}", cyl(0.76, (50, y, 0), (53, y, 0)), COL[band])
    R("p_wire24", s, (0, -0.4, 1), up=(0, 1, 0), fit=(150, 60), line=0.5)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    if names == ["lengths"]:
        for pad, ln, hl, cut in bpmd.MUX_LEADS:
            print(pad, ln, hl, cut)
        sys.exit()
    for n in names:
        SCENES[n]()
