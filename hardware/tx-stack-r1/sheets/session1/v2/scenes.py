"""Session 1 illustrations: every scene built from 3D geometry and rendered by r3d (hidden lines + flat colour).

Run with the CAD venv:  cadx/bin/python scenes.py [name ...]   ->  svg/<name>.svg + svg/<name>.json
"""
import math
import sys
import time
from pathlib import Path

import numpy as np
import cadquery as cq

import models as M
import r3d

OUT = Path(__file__).resolve().parent / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def place(wp, X, Y, origin):
    """Rigid placement: local x -> X, local y -> Y (world vectors), local origin -> origin."""
    X = np.asarray(X, float) / np.linalg.norm(X)
    Y = np.asarray(Y, float)
    Y = Y - X * (Y @ X)
    Y /= np.linalg.norm(Y)
    Z = np.cross(X, Y)
    R = np.column_stack([X, Y, Z])
    assert np.linalg.det(R) > 0
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    shp = wp.val() if isinstance(wp, cq.Workplane) and len(wp.vals()) == 1 else (
        cq.Compound.makeCompound(wp.vals()) if isinstance(wp, cq.Workplane) else wp)
    tr = gp_Trsf()
    tr.SetValues(*[float(v) for v in (R[0, 0], R[0, 1], R[0, 2], origin[0], R[1, 0], R[1, 1], R[1, 2], origin[1],
                                      R[2, 0], R[2, 1], R[2, 2], origin[2])])
    return cq.Shape.cast(BRepBuilderAPI_Transform(shp.wrapped, tr, True).Shape()), (R, np.asarray(origin, float))


def R(name, s, d, up=(0, 0, 1), fit=(260, 200), **kw):
    import handed
    handed.card_frame(s)                         # the SolderFul card pictures
    handed.board_frame(s, BX0, BZ0)              # the PAD3U pictures (FRONT toward the lid)
    if name.startswith("f_"):
        handed.box_drawing(s)                    # enclosure 2 in (Xb, Zb, Yb)
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


def add_caliper(s, gap, reading, xf=None):
    s.xf = xf
    fixed, slider, lcd, btns, jaw = M.caliper(gap, reading, scene=s)
    s.xf = None
    parts = [("cal_beam", fixed, M.STEEL), ("cal_jaw", jaw, M.STEEL), ("cal_head", slider, M.DARK),
             ("cal_lcd", lcd, M.LCD)]
    parts += [(f"cal_btn{i}", b, M.STEEL) for i, b in enumerate(btns)]
    for n, p, c in parts:
        if xf is not None:
            p, _ = place(p, xf[0][:, 0], xf[0][:, 1], xf[1])
        s.add(n, p, c, 1.0 if n != "cal_lcd" else 0.0)


def add_knife(s, tip, fwd, spine, blade_out=24):
    """Knife with its blade tip at `tip`, pointing along `fwd`, the spine side toward `spine`."""
    tipl = np.array([blade_out, 0, 0])
    X = np.asarray(fwd, float) / np.linalg.norm(fwd)
    Yv = np.asarray(spine, float)
    Yv = Yv - X * (Yv @ X)
    Yv /= np.linalg.norm(Yv)
    o = np.asarray(tip, float) - X * blade_out
    s.xf = (np.column_stack([X, Yv, np.cross(X, Yv)]), o)
    h, b = M.knife(scene=s, blade_out=blade_out)
    s.xf = None
    h, _ = place(h, X, Yv, o)
    b, _ = place(b, X, Yv, o)
    s.add("handle", h, M.SAFETY).add("blade", b, M.STEEL)


def add_clamp(s, pad_point, screw_dir_down, spine_dir, opening, name="clamp"):
    """C-clamp whose screw pad face sits at pad_point, screw pointing along screw_dir_down, frame spine toward
    spine_dir (horizontal)."""
    f, sc = M.c_clamp(opening)
    Zw = -np.asarray(screw_dir_down, float)          # local +Z (screw out of the frame) = up
    Xw = -np.asarray(spine_dir, float)               # local -X is the spine
    Yw = np.cross(Zw, Xw)
    f, _ = place(f, Xw, Yw, pad_point)
    sc, _ = place(sc, Xw, Yw, pad_point)
    s.add(name, f, M.SAFETY).add(name + "_screw", sc, M.STEEL)


# ================================================================== cover
@scene
def tool_caliper():
    s = r3d.Scene()
    add_caliper(s, 0, "0.00")
    R("tool_caliper", s, (0.15, -0.35, 1), up=(0, 1, 0), fit=(150, 60))


@scene
def tool_ruler():
    s = r3d.Scene()
    s.add("ruler", M.ruler(300, scene=s, step=5), M.STEEL)
    R("tool_ruler", s, (0.1, -0.5, 1), up=(0, 1, 0), fit=(150, 40))


@scene
def tool_knife():
    s = r3d.Scene()
    h, b = M.knife(scene=s)
    s.add("handle", h, M.SAFETY).add("blade", b, M.STEEL)
    R("tool_knife", s, (0.2, -0.45, 1), up=(0, 1, 0), fit=(150, 45))


@scene
def tool_clamps():
    s = r3d.Scene()
    for i in range(2):
        f, sc = M.c_clamp(30)
        s.add(f"clamp{i}", f.translate((i * 85, i * 40, 0)), M.SAFETY)
        s.add(f"screw{i}", sc.translate((i * 85, i * 40, 0)), M.STEEL)
    R("tool_clamps", s, (0.45, -1, 0.35), fit=(120, 70))


@scene
def tool_sandpaper():
    s = r3d.Scene()
    s.add("sand", M.box(0, 0, 0, 115, 140, 0.6), M.SAND)
    s.text("sand", "P120", (12, 12, 0.601), (1, 0, 0), (0, 1, 0), 14, colour="#6B5A3A", font="Helvetica-Bold",
           anchor="start")
    R("tool_sandpaper", s, (-0.3, -0.8, 1), fit=(110, 60))


@scene
def tool_drill():
    s = r3d.Scene()
    s.add("drill", M.drill_bit(), M.STEEL)
    R("tool_drill", s, (0.15, -1, 0.55), fit=(150, 28))


@scene
def tool_marker():
    s = r3d.Scene()
    b, c, t = M.marker()
    s.add("barrel", b, "#D9D9D9").add("cap", c, M.BLACK).add("tip", t, M.BLACK)
    R("tool_marker", s, (0.15, -1, 0.6), fit=(150, 30))


@scene
def tool_mask():
    s = r3d.Scene()
    sh, st = M.mask()
    s.add("mask", sh, "#F4F4F4").add("strap", st, M.TOWEL)
    R("tool_mask", s, (0.45, -1, 0.35), fit=(90, 60))


@scene
def tool_phone():
    s = r3d.Scene()
    b, sc, l = M.phone()
    s.add("phone", b, M.BLACK).add("screen", sc, "#2E3640").add("lens", l, "#555555")
    R("tool_phone", s, (-0.3, -0.9, 1), fit=(70, 70))


@scene
def tool_file():
    s = r3d.Scene()
    b, h = M.hand_file()
    s.add("file", b, M.STEEL).add("fh", h, M.SAFETY)
    s.lines("file", [((-140 + i * 5, -7.6 + i * 0.013, 2.001), (-136 + i * 5, 7.6 - i * 0.013, 2.001)) for i in range(27)],
            width=0.3, colour="#7A7E83")
    R("tool_file", s, (0.15, -0.6, 1), up=(0, 1, 0), fit=(150, 30))


@scene
def mat_pad3u():
    s = r3d.Scene()
    b, _ = M.pad3u_region(0, 0, M.PAD_W, M.PAD_H)
    b, _ = place(b, (0, 1, 0), (-1, 0, 0), (0, 0, 0))      # lying down: 160 along x
    s.add("pad", b, M.FR4)
    R("mat_pad3u", s, (-0.45, -1, 1.25), fit=(150, 100), line=0.3)


@scene
def mat_cards():
    s = r3d.Scene()
    for k in range(4):
        b, p = M.solderful(z0=k * 9.0, labels=False)
        s.add(f"card{k}", b, M.RED_PCB).add(f"pads{k}", p, M.GOLD, 0.0)
    R("mat_cards", s, (-0.45, -1, 1.0), fit=(150, 110), line=0.3)


# ================================================================== step 01
INS_Y = -24.0


def insert_x():
    """Insert lying along X between x = 0 and 5.7 at y = INS_Y, mid-thickness of the caliper."""
    i = M.insert().rotate((0, 0, 0), (0, 1, 0), 90)
    return i.translate((0, INS_Y, 1.75))


@scene
def s1_len():
    s = r3d.Scene()
    add_caliper(s, M.INS_L, "5.70")
    s.add("insert", insert_x(), M.BRASS)
    s.anchor("jawL", (0, -38.5, 3.5))
    s.anchor("jawR", (M.INS_L, -38.5, 3.5))
    s.anchor("ins", (M.INS_L / 2, INS_Y, 1.75))
    s.anchor("e0", (0, INS_Y - 2.3, 4.05))
    s.anchor("e1", (M.INS_L, INS_Y - 2.3, 4.05))
    s.anchor("lcd", (M.INS_L + 42, 10, 12.4))
    d = (0.16, -0.28, 1)
    R("s1_len", s, d, up=(0, 1, 0), fit=(250, 170), crop=((36, -8, 0), 54, 35))
    R("s1_len_zoom", s, d, up=(0, 1, 0), fit=(120, 120), crop=((M.INS_L / 2, INS_Y, 1.75), 7.5, 7.5), line=0.7)


def insert_y(base_y, up=True):
    """Insert standing along +Y (collar end at base_y) or -Y, axis at x = 2.3."""
    i = M.insert().rotate((0, 0, 0), (1, 0, 0), -90 if up else 90)
    return i.translate((M.INS_D / 2, base_y, 1.75))


@scene
def s1_dia():
    s = r3d.Scene()
    add_caliper(s, M.INS_D, "4.60")
    s.add("insert", insert_y(-31.0), M.BRASS)
    s.anchor("ins", (M.INS_D / 2, -28, 1.75))
    s.anchor("e0", (0, -28.6, 4.05))
    s.anchor("e1", (M.INS_D, -28.6, 4.05))
    s.anchor("lcd", (M.INS_D + 42, 10, 12.4))
    d = (0.16, -0.28, 1)
    R("s1_dia", s, d, up=(0, 1, 0), fit=(250, 170), crop=((36, -8, 0), 54, 35))
    R("s1_dia_zoom", s, d, up=(0, 1, 0), fit=(120, 120), crop=((M.INS_D / 2, -28.2, 1.75), 7.0, 7.0), line=0.7)


@scene
def s1_end():
    """The insert seen end-on from the smooth collar end."""
    s = r3d.Scene()
    s.add("insert", M.insert(), M.BRASS)
    s.anchor("tipA", (-2.3, 0, 1.0))
    s.anchor("tipB", (2.3, 0, 1.0))
    s.anchor("boreA", (-1.3, 0, 0))
    s.anchor("boreB", (1.3, 0, 0))
    s.anchor("colA", (-2.0, 0, 0))
    s.anchor("colB", (2.0, 0, 0))
    R("s1_end", s, (0.0, 0.0, -1), up=(0, 1, 0), fit=(110, 110), line=0.6)


@scene
def s1_collar():
    """Wrong: the jaws on the smooth collar, the knurl hanging past the tips."""
    s = r3d.Scene()
    add_caliper(s, 4.0, "4.00")
    i = M.insert().rotate((0, 0, 0), (1, 0, 0), 90).translate((2.0, -37.4, 1.75))
    s.add("insert", i, M.BRASS)
    s.anchor("collar", (2.0, -37.9, 1.75))
    R("s1_collar", s, (0.16, -0.28, 1), up=(0, 1, 0), fit=(120, 120), crop=((2.0, -37.5, 1.75), 8.0, 8.0), line=0.7)


# ================================================================== step 02  (L backplane, repo 4550f83)
WASTE = "#B4B4B4"


def pad3u_split(z=0.0, drilled=(), pads=False):
    """The whole PAD3U stood up (100 across, 160 up): the L piece (bottom right), the line -1 waste strip above
    the tab, and the spare."""
    piece = M.pad3u_L(drilled=drilled)
    waste, _ = M.pad3u_region(M.TAB_X0, M.TAB_Y1, M.PIECE_X0, M.PIECE_Y1)
    sa, _ = M.pad3u_region(0, 0, M.TAB_X0, M.PAD_H)                          # left of cut A
    sb, _ = M.pad3u_region(M.TAB_X0, M.PIECE_Y1, M.PAD_W, M.PAD_H)           # above cut B
    sc, _ = M.pad3u_region(M.PIECE_X1, 0, M.PAD_W, M.PIECE_Y1)               # right of cut C
    sd, _ = M.pad3u_region(M.TAB_X0, 0, M.PIECE_X1, M.PIECE_Y0)              # below cut D
    spare = sa.union(sb).union(sc).union(sd)
    return piece.translate((0, 0, z)), waste.translate((0, 0, z)), spare.translate((0, 0, z))


def snapped_rect(z=0.0):
    """After cut A and cut B: the L piece and its waste strip as one rectangle (lines -1 to 20, holes 1-39)."""
    b, _ = M.pad3u_region(M.TAB_X0, M.PIECE_Y0, M.PIECE_X1, M.PIECE_Y1)
    return b.translate((0, 0, z))


def step_anchors(s, t):
    s.anchor("cutA0", (M.TAB_X0, 0, t))
    s.anchor("cutA1", (M.TAB_X0, M.PAD_H, t))
    s.anchor("cutB0", (M.TAB_X0, M.PIECE_Y1, t))
    s.anchor("cutB1", (M.PAD_W, M.PIECE_Y1, t))
    s.anchor("cutC0", (M.PIECE_X1, 0, t))
    s.anchor("cutC1", (M.PIECE_X1, M.PIECE_Y1, t))
    s.anchor("cutD0", (M.TAB_X0, M.PIECE_Y0, t))
    s.anchor("cutD1", (M.PIECE_X1, M.PIECE_Y0, t))
    s.anchor("pbl", (M.TAB_X0, M.PIECE_Y0, t))
    s.anchor("pbr", (M.PIECE_X1, M.PIECE_Y0, t))
    s.anchor("ptr", (M.PIECE_X1, M.PIECE_Y1, t))
    s.anchor("saw0", (M.PIECE_X0, M.PIECE_Y1, t))
    s.anchor("saw1", (M.PIECE_X0, M.TAB_Y1, t))
    s.anchor("sc0", (M.TAB_X0, M.TAB_Y1, t))
    s.anchor("tab", ((M.TAB_X0 + M.PIECE_X0) / 2, (M.TAB_Y1 + M.PIECE_Y0) / 2, t))
    s.anchor("waste", ((M.TAB_X0 + M.PIECE_X0) / 2, M.PIECE_Y1 * 0.6, t))


@scene
def s2_board():
    s = r3d.Scene()
    piece, waste, spare = pad3u_split()
    s.add("piece", piece, M.HAZ).add("waste", waste, WASTE).add("spare", spare, M.FR4)
    t = M.PAD_T
    step_anchors(s, t)
    s.anchor("bl", (0, 0, t))
    s.anchor("tr", (M.PAD_W, M.PAD_H, t))
    s.anchor("br", (M.PAD_W, 0, t))
    for L, Hh in ((0, 1), (20, 1), (29, 1), (0, 39), (20, 39), (29, 39), (-1, 1)):
        s.anchor(f"h{L}_{Hh}", (*M.hole_xy(L, Hh), t))
    R("s2_board", s, (0, 0, 1), up=(0, 1, 0), fit=(190, 300), line=0.35, outline=1.2)


@scene
def s2_patch():
    """Close-up of a long cut: columns 14-19, rows 0-4, front face (bare FR4, holes only)."""
    s = r3d.Scene()
    x0, x1 = M.PIECE_X0 - 3 * M.P, M.PIECE_X0 + 3 * M.P
    piece, _ = M.pad3u_region(M.PIECE_X0, 0, x1, 4.5 * M.P + M.PAD_MY)
    spare, _ = M.pad3u_region(x0, 0, M.PIECE_X0, 4.5 * M.P + M.PAD_MY)
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4)
    t = M.PAD_T
    s.anchor("gap_top", (M.PIECE_X0, 4.5 * M.P + M.PAD_MY, t))
    s.anchor("gap_bot", (M.PIECE_X0, 0, t))
    xh = M.PIECE_X0 - 1.5 * M.P
    s.anchor("hole_top", (xh, 4.5 * M.P + M.PAD_MY, t))
    s.anchor("hole_bot", (xh, 0, t))
    R("s2_patch", s, (0, 0, 1), up=(0, 1, 0), fit=(150, 110), line=0.6, outline=1.0)


@scene
def s2_score():
    s = r3d.Scene()
    s.add("bench", M.bench(-70, -60, 190, 225, t=25, top=0), M.BENCH)
    s.add("towel", M.box(-50, -40, 0, 150, 200, 3), M.TOWEL)
    piece, waste, spare = pad3u_split(z=3)
    s.add("piece", piece.union(waste), M.HAZ).add("spare", spare, M.FR4)
    zt = 3 + M.PAD_T
    X0 = M.TAB_X0
    rl = M.ruler(300, scene=None)
    rl, xf = place(rl, (0, 1, 0), (-1, 0, 0), (X0 + 25, -60, zt))
    s.xf = xf
    M.ruler(300, scene=s, step=1)
    s.xf = None
    s.add("ruler", rl, M.STEEL)
    add_clamp(s, (X0 + 12.5, 212, zt + 1.0), (0, 0, -1), (0, 1, 0), opening=zt + 1 + 25)
    tip = (X0 - 0.3, 70, zt)
    add_knife(s, tip, (0, -0.82, -0.57), (0, -0.57, 0.82), blade_out=22)
    s.anchor("tip", tip)
    s.anchor("cutA0", (X0, 0, zt))
    s.anchor("cutA1", (X0, M.PIECE_Y1, zt))
    s.anchor("cutB1", (M.PAD_W, M.PIECE_Y1, zt))
    s.anchor("clamp", (X0 + 12.5, 212, zt + 8))
    s.anchor("towel", (125, 40, 3))
    R("s2_score", s, (0.55, -1, 1.15), fit=(330, 215), line=0.35, outline=1.1, crop=((X0 + 32, 95, 4), 105, 80))


@scene
def s2_snap():
    s = r3d.Scene()
    s.add("bench", M.bench(-40, -130, 200, 0, t=25, top=0), M.BENCH)
    piece, waste, spare = pad3u_split()
    X0 = M.TAB_X0
    pc, _ = place(piece.union(waste), (0, -1, 0), (1, 0, 0), (0, X0, 0))
    sp, _ = place(spare, (0, -1, 0), (1, 0, 0), (0, X0, 0))
    s.add("piece", pc, M.HAZ).add("spare", sp, M.FR4)
    t = M.PAD_T
    s.anchor("hold", (80, -30, t))
    s.anchor("push", (80, 25, t))
    s.anchor("edgeL", (-20, 0, 0))
    R("s2_snap", s, (0.75, 0.55, 0.65), fit=(240, 170), line=0.35)


SAW_FRONT = 45.0      # how far the hacksaw cut has come down (board y)


@scene
def s2_saw():
    """The snapped rectangle clamped on the bench, the line -1 strip over the edge; hacksaw half way down the
    slot between line -1 and line 0."""
    s = r3d.Scene()
    xe = M.PIECE_X0 + 3.0
    s.add("bench", M.bench(xe, -40, M.PIECE_X1 + 4, M.PIECE_Y1 + 30, t=25, top=0), M.BENCH)
    b = snapped_rect()
    kerf = M.box(M.PIECE_X0 - 0.35, SAW_FRONT, -1, M.PIECE_X0 + 0.35, M.PIECE_Y1 + 1, 3)
    b = b.cut(kerf)
    s.add("piece", b, M.HAZ)
    t = M.PAD_T
    # the short score across line -1 above hole 3 (both faces, done before)
    s.lines("piece", [((M.TAB_X0 + 0.05, M.TAB_Y1, t + 0.002), (M.PIECE_X0, M.TAB_Y1, t + 0.002))],
            colour="#1A1A1A", width=0.9)
    add_clamp(s, (M.PIECE_X1 - 9, M.PIECE_Y1 * 0.55, t + 1.0), (0, 0, -1), (1, 0, 0), opening=t + 1 + 25)
    a = math.radians(14)
    X = np.array([0, math.cos(a), -math.sin(a)])
    Y = np.array([0, math.sin(a), math.cos(a)])
    L0 = 110.0
    o = np.array([M.PIECE_X0, SAW_FRONT, t]) - X * L0
    fr, bl, hd = M.hacksaw()
    fr, _ = place(fr, X, Y, o)
    bl, _ = place(bl, X, Y, o)
    hd, _ = place(hd, X, Y, o)
    s.add("saw", fr, M.SAFETY).add("sawblade", bl, M.STEEL).add("sawhandle", hd, M.DARK)
    step_anchors(s, t)
    s.anchor("front", (M.PIECE_X0, SAW_FRONT, t))
    s.anchor("clamp", (M.PIECE_X1 - 9, M.PIECE_Y1 * 0.55, t + 8))
    s.anchor("handle", tuple(o + X * -40 + Y * 30))
    s.anchor("benchedge", (xe, 10, 0))
    R("s2_saw", s, (-1, -0.5, 0.62), fit=(270, 210), line=0.35, outline=1.1)


@scene
def s2_tabzoom():
    """Top view, bottom-left of the snapped rectangle: the tab (piece), the waste strip above it, line 0."""
    s = r3d.Scene()
    x1, y1 = M.PIECE_X0 + 4 * M.P, M.PAD_MY + 8.5 * M.P      # holes 1-8 (hole n = row n)
    piece = M.pad3u_L(x1=x1, y1=y1)
    waste, _ = M.pad3u_region(M.TAB_X0, M.TAB_Y1, M.PIECE_X0, y1)
    s.add("piece", piece, M.HAZ).add("waste", waste, WASTE)
    t = M.PAD_T
    s.anchor("saw0", (M.PIECE_X0, y1, t))
    s.anchor("saw1", (M.PIECE_X0, M.TAB_Y1, t))
    s.anchor("sc0", (M.TAB_X0, M.TAB_Y1, t))
    s.anchor("waste", ((M.TAB_X0 + M.PIECE_X0) / 2, M.PAD_MY + 6 * M.P, t))
    s.anchor("top", ((M.TAB_X0 + x1) / 2, y1, t))
    for Hh in (1, 2, 3, 4, 8):
        s.anchor(f"hm1_{Hh}", (*M.hole_xy(-1, Hh), t))
        s.anchor(f"h0_{Hh}", (*M.hole_xy(0, Hh), t))
    s.anchor("bot", ((M.TAB_X0 + x1) / 2, M.PIECE_Y0, t))
    R("s2_tabzoom", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 170), line=0.6, outline=1.2)


@scene
def s2_sand():
    """The L standing on its long left edge on sandpaper; the tab hangs off the end of the table."""
    s = r3d.Scene()
    xe = 12.0
    s.add("bench", M.bench(xe, -60, 170, 150, t=25, top=0), M.BENCH)
    s.add("sand", M.box(xe + 2, -20, 0, 125, 120, 0.6), M.SAND)
    w = M.PIECE_X1 - M.PIECE_X0
    pc = M.pad3u_L().translate((-M.PIECE_X0, -M.PIECE_Y0, 0))
    pc, _ = place(pc, (0, 0, 1), (1, 0, 0), (0, 50, 0.6))
    s.add("piece", pc, M.HAZ)
    s.anchor("top", (50, 50 - 0.8, 0.6 + w))
    s.anchor("a0", (25, 50, 0.6 + w * 0.55))
    s.anchor("a1", (105, 50, 0.6 + w * 0.55))
    s.anchor("tab", ((M.TAB_Y1 - M.PIECE_Y0) / 2, 50 - 0.8, 0.6 - 1.4))
    R("s2_sand", s, (0.6, -1, 0.7), fit=(150, 130), line=0.4)


@scene
def s2_edge():
    """Top-view close-up above the tab: the sanded left edge and line 0's holes (holes 5-8)."""
    s = r3d.Scene()
    x0 = M.PIECE_X0
    pc, _ = M.pad3u_region(x0, M.PAD_MY + 4.5 * M.P, x0 + 3.0 * M.P, M.PAD_MY + 8.5 * M.P)
    s.add("piece", pc, M.HAZ)
    xh, yh = M.hole_xy(0, 7)
    s.anchor("edge", (x0, yh, M.PAD_T))
    s.anchor("hole_near", (xh - 0.5, yh, M.PAD_T))
    s.anchor("line0", (xh, M.PAD_MY + 8.4 * M.P, M.PAD_T))
    R("s2_edge", s, (0, 0, 1), up=(0, 1, 0), fit=(110, 110), line=0.7, outline=1.2)


DRILLED = [M.hole_xy(0, 2), M.hole_xy(20, 2), M.hole_xy(20, 36)]      # repo 114aae1: three M3 screws


@scene
def s2_drill():
    s = r3d.Scene()
    pc = M.pad3u_L(drilled=DRILLED)
    s.add("piece", pc, M.HAZ)
    t = M.PAD_T
    cx = (M.PIECE_X0 + M.PIECE_X1) / 2
    s.text("piece", "FRONT", (cx, 52, t + 0.001), (1, 0, 0), (0, 1, 0), 9.5, colour="#1A1A1A",
           font="Helvetica-Bold")
    for nm, (L, Hh) in {"d0_2": (0, 2), "d20_2": (20, 2), "d20_36": (20, 36), "h1": (0, 1), "h0_4": (0, 4),
                         "h39": (20, 39), "l0top": (0, 39), "l20bot": (20, 1), "lm1": (-1, 1), "l29bot": (29, 1),
                         "l29top": (29, 39)}.items():
        s.anchor(nm, (*M.hole_xy(L, Hh), t))
    s.anchor("bl", (M.TAB_X0, M.PIECE_Y0, t))
    s.anchor("br", (M.PIECE_X1, M.PIECE_Y0, t))
    s.anchor("tr", (M.PIECE_X1, M.PIECE_Y1, t))
    s.anchor("tl_c", (M.PIECE_X0, M.PIECE_Y1, t))
    s.anchor("tabtop", (M.TAB_X0, M.TAB_Y1, t))
    R("s2_drill", s, (0, 0, 1), up=(0, 1, 0), fit=(250, 300), line=0.4, outline=1.3)


@scene
def s2_tab():
    """Top-view close-up of the tab after drilling: line 0 hole 2, and the board left of it."""
    s = r3d.Scene()
    x1, y1 = M.PIECE_X0 + 4 * M.P, M.PAD_MY + 5.5 * M.P
    pc = M.pad3u_L(x1=x1, y1=y1, drilled=[M.hole_xy(0, 2)])
    s.add("piece", pc, M.HAZ)
    t = M.PAD_T
    xh, yh = M.hole_xy(0, 2)
    s.anchor("hole", (xh, yh, t))
    s.anchor("hole_l", (xh - 1.6, yh, t))
    s.anchor("tab_l", (M.TAB_X0, yh, t))
    s.anchor("tabtop", (M.TAB_X0, M.TAB_Y1, t))
    s.anchor("step", (M.PIECE_X0, M.TAB_Y1, t))
    s.anchor("lm1", (*M.hole_xy(-1, 3), t))
    s.anchor("l0", (*M.hole_xy(0, 5), t))
    R("s2_tab", s, (0, 0, 1), up=(0, 1, 0), fit=(130, 150), line=0.6, outline=1.2)


@scene
def tool_hacksaw():
    s = r3d.Scene()
    fr, bl, hd = M.hacksaw()
    s.add("saw", fr, M.SAFETY).add("sawblade", bl, M.STEEL).add("sawhandle", hd, M.DARK)
    R("tool_hacksaw", s, (0.15, -0.3, 1), up=(0, 1, 0), fit=(150, 60))


# ================================================================== step 02, repo 82edf8a: the plated end, one cut
SX = M.B_SCORE_X
D02 = M.b_xy(0, 2)


def b_split(z=0.0, drilled=(), opened=False, pads=False):     # enclosure 4: nothing drilled
    piece, cu = M.b_region(SX, M.B_L, drilled=drilled, opened=opened)
    spare, cs = M.b_region(0, SX, drilled=drilled)
    pads = cq.Compound.makeCompound([c for c in (cu, cs) if c is not None])
    return piece.translate((0, 0, z)), spare.translate((0, 0, z)), pads.translate((0, 0, z))


def b_anchors(s, t):
    s.anchor("score0", (SX, 0, t))
    s.anchor("score1", (SX, M.B_W, t))
    s.hole("mh_lo", (*M.B_MH_LO, t))
    s.hole("mh_hi", (*M.B_MH_HI, t))
    s.hole("plain_lo", (*M.B_PLAIN[0], t))
    s.hole("plain_hi", (*M.B_PLAIN[1], t))
    for L, Hh in ((0, 1), (0, 2), (0, 38), (30, 1), (30, 38), (0, 37), (30, 2), (30, 37)):
        s.hole(f"h{L}_{Hh}", (*M.b_xy(L, Hh), t))
    s.anchor("bl", (0, 0, t))
    s.anchor("br", (M.B_L, 0, t))
    s.anchor("tr", (M.B_L, M.B_W, t))
    s.anchor("tl", (0, M.B_W, t))
    s.anchor("piece", ((SX + M.B_L) / 2, M.B_W / 2, t))
    s.anchor("spare", (SX / 2, M.B_W / 2, t))


@scene
def b_board():
    s = r3d.Scene()
    piece, spare, pads = b_split(drilled=(), opened=False)
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4).add("pads", pads, M.TIN, 0.15)
    b_anchors(s, M.PAD_T)
    R("b_board", s, (0, 0, 1), up=(0, 1, 0), fit=(330, 215), line=0.3, outline=1.2)


@scene
def b_end():
    """The plated end from the BACK face (bus-wire side), turned over top-to-bottom: holes 1-6 of lines 25-30, the lower
    mounting hole and the missing pad beside it (as on Clint's scan)."""
    s = r3d.Scene()
    x0, y1 = M.b_row_x(M.B_LINE0_ROW + 25) - M.P / 2, M.b_xy(0, 6)[1] + M.P / 2
    b, cu = M.b_region(x0, M.B_L, 0, y1, pads=True)
    s.add("board", b, M.HAZ).add("cu", cu, M.TIN, 0.3)
    z = -0.06
    s.hole("mh", (*M.B_MH_LO, z))
    s.anchor("missing", (M.B_END_X, M.B_MH_LO[1], z))
    s.hole("end_row", (M.B_END_X, M.b_xy(0, 5)[1], z))
    s.anchor("edge", (M.B_L, M.b_xy(0, 4)[1], z))
    s.anchor("row24", (M.b_row_x(M.B_LINE0_ROW + 24), M.b_xy(0, 5)[1], z))
    R("b_end", s, (0, 0, -1), up=(0, -1, 0), fit=(220, 150), line=0.5, outline=1.1)


@scene
def b_patch():
    """Close-up of the score line: three rows each side, holes 6-10 (front; pads on both faces)."""
    s = r3d.Scene()
    y0, y1 = M.B_SIDE + 4.5 * M.P, M.B_SIDE + 9.5 * M.P
    piece, c1 = M.b_region(SX, SX + 3 * M.P, y0, y1)
    spare, c2 = M.b_region(SX - 3 * M.P, SX, y0, y1)
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4).add("pads", c1, M.TIN, 0.3).add("pads2", c2, M.TIN, 0.3)
    t = M.PAD_T
    s.anchor("gap_top", (SX, y1, t))
    s.anchor("gap_bot", (SX, y0, t))
    xh = SX - M.P / 2
    s.anchor("hole_top", (xh, y1, t))
    s.anchor("hole_bot", (xh, y0, t))
    R("b_patch", s, (0, 0, 1), up=(0, 1, 0), fit=(150, 110), line=0.6, outline=1.0)


@scene
def b_score():
    s = r3d.Scene()
    s.add("bench", M.bench(-40, -60, 200, 125, t=25, top=0), M.BENCH)
    s.add("towel", M.box(-20, -40, 0, 185, 118, 3), M.TOWEL)
    piece, spare, pads = b_split(z=3)
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4).add("pads", pads, M.TIN, 0.12)
    zt = 3 + M.PAD_T
    rl = M.ruler(300, scene=None)
    rl, xf = place(rl, (0, 1, 0), (-1, 0, 0), (SX + 25, -150, zt))
    s.xf = xf
    M.ruler(300, scene=s, step=1)
    s.xf = None
    s.add("ruler", rl, M.STEEL)
    add_clamp(s, (SX + 12.5, 112, zt + 1.0), (0, 0, -1), (0, 1, 0), opening=zt + 1 + 25)
    tip = (SX - 0.3, 40, zt)
    add_knife(s, tip, (0, -0.82, -0.57), (0, -0.57, 0.82), blade_out=22)
    s.anchor("tip", tip)
    s.anchor("score0", (SX, 0, zt))
    s.anchor("score1", (SX, M.B_W, zt))
    s.anchor("clamp", (SX + 12.5, 112, zt + 8))
    s.anchor("towel", (175, 10, 3))
    s.anchor("piece", (SX + 55, 60, zt))
    R("b_score", s, (0.55, -1, 1.15), fit=(330, 215), line=0.35, outline=1.1, crop=((SX + 15, 50, 4), 100, 72))


@scene
def b_snap():
    s = r3d.Scene()
    s.add("bench", M.bench(-40, -100, 140, 0, t=25, top=0), M.BENCH)
    piece, spare, pads = b_split()
    pc, _ = place(piece, (0, -1, 0), (1, 0, 0), (0, SX, 0))
    sp, _ = place(spare, (0, -1, 0), (1, 0, 0), (0, SX, 0))
    pd, _ = place(pads, (0, -1, 0), (1, 0, 0), (0, SX, 0))
    s.add("piece", pc, M.HAZ).add("spare", sp, M.FR4).add("pads", pd, M.TIN, 0.12)
    t = M.PAD_T
    s.anchor("hold", (50, -40, t))
    s.anchor("push", (50, 45, t))
    s.anchor("edgeL", (-20, 0, 0))
    s.anchor("edgeR", (128, 0, 0))
    R("b_snap", s, (0.75, 0.55, 0.65), fit=(240, 170), line=0.35)


@scene
def b_drill():
    """The plated half, FRONT up, before the snap: line 0 hole 2 drilled 3.2, the lower mounting hole opened."""
    s = r3d.Scene()
    x0 = SX - 2 * M.P
    piece, cu = M.b_region(SX, M.B_L, drilled=[D02], opened=True)
    spare, cs = M.b_region(x0, SX, drilled=[D02])
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4).add("pads", cu, M.TIN, 0.15).add("pads2", cs, M.TIN, 0.15)
    t = M.PAD_T
    b_anchors(s, t)
    s.anchor("x0b", (x0, 0, t))
    s.anchor("x0t", (x0, M.B_W, t))
    R("b_drill", s, (0, 0, 1), up=(0, 1, 0), fit=(250, 300), line=0.35, outline=1.2)


@scene
def b_holezoom():
    """Line 0 hole 2 drilled 3.2, before the snap: it crosses the score line by 0.3."""
    s = r3d.Scene()
    y1 = M.B_SIDE + 4.5 * M.P
    piece, c1 = M.b_region(SX, SX + 3.5 * M.P, 0, y1, drilled=[D02])
    spare, c2 = M.b_region(SX - 1.5 * M.P, SX, 0, y1, drilled=[D02])
    s.add("piece", piece, M.HAZ).add("spare", spare, M.FR4).add("pads", c1, M.TIN, 0.3).add("pads2", c2, M.TIN, 0.3)
    t = M.PAD_T
    s.hole("hole", (*D02, t))
    s.anchor("hole_l", (D02[0] - 1.6, D02[1], t))
    s.anchor("score0", (SX, 0, t))
    s.anchor("score1", (SX, y1, t))
    s.anchor("l0", (*M.b_xy(0, 4), t))
    R("b_holezoom", s, (0, 0, 1), up=(0, 1, 0), fit=(140, 150), line=0.6, outline=1.2)


def _mh_scene(opened):
    s = r3d.Scene()
    x0, y1 = M.b_row_x(M.B_ROWS - 2) - M.P / 2, M.B_SIDE + 3.5 * M.P
    b, cu = M.b_region(x0, M.B_L, 0, y1, opened=opened)
    s.add("board", b, M.HAZ).add("pads", cu, M.TIN, 0.3)
    t = M.PAD_T
    ri = 1.6 if opened else M.B_MH_D / 2
    s.hole("mh", (*M.B_MH_LO, t))
    s.anchor("mh_l", (M.B_MH_LO[0] - ri, M.B_MH_LO[1], t))
    s.anchor("mh_r", (M.B_MH_LO[0] + ri, M.B_MH_LO[1], t))
    return s


@scene
def b_mh_before():
    R("b_mh_before", _mh_scene(False), (0, 0, 1), up=(0, 1, 0), fit=(100, 90), line=0.6, outline=1.2)


@scene
def b_mh_after():
    R("b_mh_after", _mh_scene(True), (0, 0, 1), up=(0, 1, 0), fit=(100, 90), line=0.6, outline=1.2)


@scene
def b_sand():
    s = r3d.Scene()
    xe = 12.0
    s.add("bench", M.bench(xe, -60, 150, 150, t=25, top=0), M.BENCH)
    s.add("sand", M.box(xe + 2, -20, 0, 125, 120, 0.6), M.SAND)
    w = M.B_L - SX
    pc, cu = M.b_region(SX, M.B_L, drilled=[], opened=False)
    pc, cu = pc.translate((-SX, 0, 0)), cu.translate((-SX, 0, 0))
    pc, _ = place(pc, (0, 0, 1), (1, 0, 0), (0, 50, 0.6))
    cu, _ = place(cu, (0, 0, 1), (1, 0, 0), (0, 50, 0.6))
    s.add("piece", pc, M.HAZ).add("pads", cu, M.TIN, 0.12)
    s.anchor("top", (50, 50 - 0.8, 0.6 + w))
    s.anchor("a0", (25, 50, 0.6 + w * 0.55))
    s.anchor("a1", (105, 50, 0.6 + w * 0.55))
    R("b_sand", s, (0.6, -1, 0.7), fit=(150, 130), line=0.4)


@scene
def b_edge():
    """Top view: the sanded left edge and line 0's holes 5-8."""
    s = r3d.Scene()
    y0, y1 = M.B_SIDE + 3.5 * M.P, M.B_SIDE + 7.5 * M.P
    pc, cu = M.b_region(SX, SX + 3.0 * M.P, y0, y1)
    s.add("piece", pc, M.HAZ).add("pads", cu, M.TIN, 0.3)
    xh, yh = M.b_xy(0, 6)
    s.anchor("edge", (SX, yh, M.PAD_T))
    s.hole("hole_c", (xh, yh, M.PAD_T))
    s.anchor("hole_near", (xh - 0.5, yh, M.PAD_T))
    s.anchor("line0", (xh, y1 - 0.1, M.PAD_T))
    R("b_edge", s, (0, 0, 1), up=(0, 1, 0), fit=(110, 110), line=0.7, outline=1.2)


@scene
def b_right():
    """Top view: the factory right edge, line 30 and the lower mounting hole (holes 1-4)."""
    s = r3d.Scene()
    x0, y1 = M.b_row_x(M.B_ROWS - 2) - M.P / 2, M.B_SIDE + 3.5 * M.P
    b, cu = M.b_region(x0, M.B_L, 0, y1, opened=False)
    s.add("board", b, M.HAZ).add("pads", cu, M.TIN, 0.3)
    t = M.PAD_T
    s.hole("l30", (*M.b_xy(30, 3), t))
    s.anchor("edge", (M.B_L, M.b_xy(30, 3)[1], t))
    s.hole("mh", (*M.B_MH_LO, t))
    s.anchor("l29top", (M.B_END_X, y1, t))
    R("b_right", s, (0, 0, 1), up=(0, 1, 0), fit=(110, 100), line=0.7, outline=1.2)


# ------------------------------------------------------------------ the base (box frame: x = Xb, y = Zb, z = Yb)
BX0 = SX - 6.51                                # board frame -> box frame: Xb = x - BX0, Zb = y + 48.71
BZ0 = 48.71
BYB = 8.0                                      # the BACK face (bus-wire side)


def bxz(line, hole):
    x, y = M.b_xy(line, hole)
    return x - BX0, y + BZ0


POST_S20_2 = bxz(20, 2)
POST_S24_31 = bxz(24, 31)                      # repo 91a5345: supports s20.2, s28.16, s24.31
POST_S28_16 = bxz(28, 16)
SLOT_END = 92.3                                # backplane slot Xb 85.8-92.3 (6.5 deep)
POST_X1 = 95.8                                 # right corner post Xb 85.8-95.8
SLIDE = 2.84
sys.path.insert(0, "/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
import sources as _src                         # noqa: E402
BAR_X, BAR_LO, BAR_HI = _src.val("bar_inserts")[:3]   # enclosure 3 as printed: Xb 5.00, Zb 76.50 and 146.50
sys.path.insert(0, "/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1/cage")
import cage as _cage                           # noqa: E402  (the lid corner posts and their M4 inserts)
M4_D, M4_L = _cage.INSERT_D, _cage.INSERT_L    # insert_m4: hole 5.6, length 8.0
_M4_IN = _cage.POST - _cage._bore / 2 - 3.0     # bore centre from each inside wall (cage.POST: 3 mm round the bore)
M4_AT = [(_M4_IN if sx > 0 else _cage.W - _M4_IN, _M4_IN if sz > 0 else _cage.H - _M4_IN) for sx, sz in _cage.corners()]
CORNER_LAND = (_cage.CORNER_X, _cage.CORNER_Z, _cage.SEAM)   # the corner land (lid boss shelf) over each post
PLASTIC = "#D9D9D9"
ADD = M.HAZ


def base_parts(slot=True, wall_h=14.0, bar=False, lid_posts=False, shelves=False):
    """Enclosure 4's printed base (bar: the retention bar's two inserts, seen on the left block's top) (all printed in,
    nothing glued or cut), the parts that matter: floor, walls cut down, the left wall block with its groove, the right
    corner post with its slot and the three plain support posts (no screw posts since enclosure 4: the cards hold the
    backplane); shelves: the EVM ledges, the right fin and the pack tray (as printed, enclosure 4 + its lip fix).
    Returns [(name, solid, colour)]."""
    out = []
    out.append(("floor", M.box(-3, -3, -3, 126.5, 172.5, 0), PLASTIC))
    out.append(("wallL", M.box(-3, -3, 0, 0, 172.5, wall_h), PLASTIC))
    out.append(("wallB", M.box(0, -3, 0, 123.5, 0, wall_h), PLASTIC))
    blk = M.box(0, 72.73, 0, 8.5, 150.61, wall_h).cut(M.box(6.0, 70, BYB, 9, 153, 10.1))
    out.append(("leftblock", blk, PLASTIC))
    post = M.box(85.8, 72.73, 0, POST_X1, 150.61, 21.96)
    if slot:
        post = post.cut(M.box(85.79, 70, BYB, SLOT_END, 153, 10.1))
    out.append(("cornerpost", post, PLASTIC))
    for nm, p in (("post_s20_2", POST_S20_2), ("post_s24_31", POST_S24_31), ("post_s28_16", POST_S28_16)):
        out.append((nm, cq.Workplane("XY").center(*p).circle(3.0).extrude(BYB).val(), PLASTIC))
    if shelves:                                   # drawn in the scene frame (x Xb, y Zb, z Yb): heights along z
        sh = [M.box(0, 41.15, 13.85, 9.85, 48.4, 109.0),                 # left ledge (EVM's left edge)
              M.box(96.25, 21.4, 0, 100.25, 48.4, 109.0),                # right fin (EVM's right edge, the tray's end)
              M.box(102.0, 38.4, 101.75, 121.0, 48.4, 109.0),            # the right lid-end block
              M.box(0, 21.4, 0, 96.25, 24.4, _cage.TRAY_Y1),             # pack tray
              M.box(16.5, 24.4, _cage.LIP_Y0, 89.5, 30.4, _cage.TRAY_Y1)]   # its front lip
        out.append(("shelves", cq.Compound.makeCompound([b.val() for b in sh]), PLASTIC))
    if bar:
        bi = [cq.Workplane("XY").workplane(offset=wall_h - 0.05).center(BAR_X, z).circle(2.3).circle(1.3)
              .extrude(0.06).val() for z in (BAR_LO, BAR_HI)]
        out.append(("bar_inserts", cq.Compound.makeCompound(bi), M.BRASS))
    if lid_posts:                                # the four lid corner posts' lands, each with its M4 insert
        cx, cz, top = CORNER_LAND
        W, H = _cage.W, _cage.H
        lands = [M.box(0 if x < W / 2 else W - cx, 0 if z < H / 2 else H - cz, top - 3.0,
                       cx if x < W / 2 else W, cz if z < H / 2 else H, top).val() for x, z in M4_AT]
        out.append(("lid_posts", cq.Compound.makeCompound(lands), PLASTIC))
        m4 = [cq.Workplane("XY").workplane(offset=top - 0.05).center(x, z).circle(M4_D / 2 + 0.9).circle(M4_D / 2 - 0.6)
              .extrude(0.06).val() for x, z in M4_AT]
        out.append(("m4_inserts", cq.Compound.makeCompound(m4), M.BRASS))
    return out


def base_anchors(s):
    z = BYB
    for nm, p in (("post_s20_2", POST_S20_2), ("post_s24_31", POST_S24_31), ("post_s28_16", POST_S28_16)):
        s.anchor(nm, (*p, z))
    s.anchor("slot_lo", ((85.8 + SLOT_END) / 2, 72.73, 9.0))
    s.anchor("slot_mid", (85.8, 110, 9.0))
    s.anchor("post_top", (SLOT_END, 110, 21.96))
    s.anchor("groove", (8.5, 110, 9.0))


def board_in_base(dx=0.0, tilt=0.0):
    """The piece in the box frame, slid dx along +Xb from home; tilt (deg) lifts its left side about the right edge.
    Nothing drilled, no screws (enclosure 4: the cards hold it)."""
    pc, cu = M.b_region(SX, M.B_L)
    pc, cu = pc.translate((-BX0 + dx, BZ0, BYB)), cu.translate((-BX0 + dx, BZ0, BYB))
    if tilt:
        pivot = (M.B_L - BX0 + dx, 0, BYB)
        pc = pc.rotate(pivot, (pivot[0], 1, pivot[2]), tilt)
        cu = cu.rotate(pivot, (pivot[0], 1, pivot[2]), tilt)
    return [("board", pc, M.HAZ), ("pads", cu, M.TIN)]


@scene
def f_plan():
    s = r3d.Scene()
    for nm, so, col in base_parts(bar=True, lid_posts=True, shelves=True):
        s.add(nm, so, col)
    base_anchors(s)
    s.hole("bar_lo", (BAR_X, BAR_LO, 14.0))
    s.hole("bar_hi", (BAR_X, BAR_HI, 14.0))
    for k, (x, z) in enumerate(M4_AT):           # corners(): (+,+) bottom left, (+,-) top left, (-,+), (-,-)
        s.hole(f"m4_{k}", (x, z, CORNER_LAND[2]))
    R("f_plan", s, (0, 0, 1), up=(0, 1, 0), fit=(260, 320), line=0.35, outline=1.1,
      crop=((_cage.W / 2, _cage.H / 2, 0), _cage.W / 2 + 2, _cage.H / 2 + 2))


@scene
def f_slot():
    s = r3d.Scene()
    for nm, so, col in base_parts():
        if nm in ("wallL", "leftblock", "post_s20_36"):
            continue
        s.add(nm, so, col)
    base_anchors(s)
    # a PAD3U offcut (4 rows x 3 holes, factory edge first) run along the slot, pushed to its end
    oc, ocu = M.b_region(M.B_L - 4 * M.P, M.B_L, M.B_SIDE + 9.5 * M.P, M.B_SIDE + 12.5 * M.P)
    off = (SLOT_END - M.B_L, 76.0 - (M.B_SIDE + 9.5 * M.P), BYB)
    s.add("offcut", oc.translate(off), M.FR4).add("offcut_pads", ocu.translate(off), M.TIN, 0.3)
    s.anchor("offcut", (SLOT_END - 2 * M.P, 76.0 + 1.5 * M.P, BYB + M.PAD_T))
    s.anchor("offcut_tail", (SLOT_END - 4 * M.P, 76.0 + 3 * M.P, BYB + M.PAD_T))
    s.anchor("slot_end", (SLOT_END, 74, 9.05))
    s.anchor("slot_mouth", (85.8, 74, 10.1))
    R("f_slot", s, (-0.8, -1, 0.75), fit=(200, 160), line=0.4, outline=1.1, crop=((83, 76, 6), 23, 17))


def _side(name, dx, tilt):
    s = r3d.Scene()
    for nm, so, col in base_parts(wall_h=26):
        if nm in ("wallB",):
            continue
        s.add(nm, so, col)
    for nm, so, col in board_in_base(dx, tilt):
        s.add(nm, so, col, 0.12 if nm == "pads" else 1.0)
    s.anchor("left_edge", (6.51 + dx, 60, BYB + 0.8))
    s.anchor("right_edge", (M.B_L - BX0 + dx, 60, BYB + 0.8))
    s.anchor("groove", (8.5, 60, 9.0))
    s.anchor("slot_end", (SLOT_END, 60, 9.0))
    R(name, s, (0, -1, 0), up=(0, 0, 1), fit=(330, 90), line=0.35, outline=1.1, crop=((48, 0, 14), 50, 12))


@scene
def f_tilt():
    _side("f_tilt", SLIDE, 6.0)


@scene
def f_slide():
    _side("f_slide", SLIDE, 0.0)


@scene
def f_home():
    _side("f_home", 0.0, 0.0)                 # the bare board: no screws, ever (enclosure 4)


@scene
def f_done():
    s = r3d.Scene()
    for nm, so, col in base_parts():
        s.add(nm, so, col)
    for nm, so, col in board_in_base(0.0, 0.0):             # test fit: the bare board, no screws
        s.add(nm, so, col, 0.12 if nm == "pads" else 1.0)
    base_anchors(s)
    s.hole("upper_mh", (M.B_MH_HI[0] - BX0, M.B_MH_HI[1] + BZ0, BYB + M.PAD_T))
    R("f_done", s, (0, 0, 1), up=(0, 1, 0), fit=(260, 320), line=0.35, outline=1.1,
      crop=((48, 100, 0), 54, 58))


@scene
def mat_base():
    """The parts for the base: two M3 heat-set inserts (bars 1, 2) and four M4 (the lid corner posts, cage insert_m4:
    the M3 model scaled to its length)."""
    s = r3d.Scene()
    for k, x in enumerate((8, 16)):
        s.add(f"insert{k}", M.insert().translate((x, 0, 0)), M.BRASS, 0.5)
    k4 = M4_L / 5.7
    for k, x in enumerate((36, 47, 58, 69)):
        s.add(f"m4_{k}", M.insert().val().scale(k4).translate(cq.Vector(x, 0, 0)), M.BRASS, 0.5)
    s.anchor("m3", (12, -4, 0))
    s.anchor("m4", (52.5, -5, 0))
    R("mat_base", s, (-0.3, -1, 0.8), fit=(150, 80), line=0.35)


# ================================================================== step 03
def card_anchors(s, z=M.SB_T, snapped=False):
    s.anchor("fl", (0, 0, z))
    s.anchor("fr", (M.SB_W, 0, z))
    s.anchor("snapL", (0, M.SNAP_Y, z))
    s.anchor("snapR", (M.SB_W, M.SNAP_Y, z))
    s.anchor("bl", (0, M.SB_H, z))
    s.anchor("br", (M.SB_W, M.SB_H, z))
    s.anchor("railB_in", (M.SB_W - 6, M.RAILS_BACK[0], z))
    s.anchor("railB_out", (M.SB_W - 6, M.RAILS_BACK[1], z))
    s.anchor("numJ", (M.col_x(2), M.NUM_Y_BACK, z))
    s.anchor("rowJ", (M.col_x(27), M.LET_Y["J"], z))
    s.anchor("rowA", (M.col_x(27), M.LET_Y["A"], z))
    s.anchor("railF", (M.col_x(26), M.RAILS_FRONT[0], z))


@scene
def s3_card():
    s = r3d.Scene()
    b, p = M.solderful(decals=s)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    card_anchors(s)
    R("s3_card", s, (0, 0, 1), up=(0, 1, 0), fit=(300, 190), line=0.4, outline=1.2)


@scene
def s3_score():
    s = r3d.Scene()
    s.add("bench", M.bench(-40, -40, 130, 90, t=20, top=0), M.BENCH)
    b, p = M.solderful(decals=s, labels=False)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    zt = M.SB_T + 0.06
    rl = M.ruler(150)
    rl, _ = place(rl, (1, 0, 0), (0, 1, 0), (-30, M.SNAP_Y - 25, zt))
    s.add("ruler", rl, M.STEEL)
    tip = (22, M.SNAP_Y + 0.2, M.SB_T)
    add_knife(s, tip, (-0.82, 0, -0.57), (-0.57, 0, 0.82), blade_out=22)
    s.anchor("snapL", (0, M.SNAP_Y, M.SB_T))
    s.anchor("snapR", (M.SB_W, M.SNAP_Y, M.SB_T))
    s.anchor("tip", tip)
    R("s3_score", s, (-0.25, -0.55, 1.4), up=(0, 0, 1), fit=(170, 125), line=0.35, crop=((40, 30, 2), 56, 36))


@scene
def s3_snap():
    s = r3d.Scene()
    s.add("bench", M.bench(-50, -110, 130, 0, t=25, top=0), M.BENCH)
    b, p = M.solderful(labels=False)
    b = b.translate((0, -M.SNAP_Y, 0))
    p = p.translate((0, -M.SNAP_Y, 0))
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    s.add("wood", M.box(-30, -M.SNAP_Y + 2, M.SB_T + 0.06, 105, -1.0, M.SB_T + 18), M.WOOD)
    add_clamp(s, (-15, -20, M.SB_T + 18), (0, 0, -1), (0, 1, 0), opening=M.SB_T + 18 + 25 + 0.1)
    s.anchor("push", (40, (M.SB_H - M.SNAP_Y) / 2, M.SB_T))
    s.anchor("wood", (60, -20, M.SB_T + 18))
    s.anchor("edge0", (0, 0, M.SB_T))
    s.anchor("edge1", (M.SB_W, 0, M.SB_T))
    R("s3_snap", s, (0.45, 1, 1.3), fit=(170, 125), line=0.35, crop=((35, -8, 5), 68, 46))


def card_edge(cut_y):
    b, p = M.solderful(snapped=True)
    if cut_y < M.SNAP_Y:
        k = M.box(-1, cut_y, -1, 90, 60, 5)
        b, p = b.cut(k), p.cut(k)
    return b, p


@scene
def s3_edge_ok():
    s = r3d.Scene()
    b, p = card_edge(M.SNAP_Y)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    s.anchor("j", (M.col_x(3), M.LET_Y["J"], M.SB_T))
    R("s3_edge_ok", s, (0, 0, 1), up=(0, 1, 0), fit=(100, 70), crop=((M.col_x(3.5), 39.0, 0), 9.5, 5.5),
      line=0.6, outline=1.2)


@scene
def s3_edge_bad():
    s = r3d.Scene()
    b, p = card_edge(39.6)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    R("s3_edge_bad", s, (0, 0, 1), up=(0, 1, 0), fit=(100, 70), crop=((M.col_x(3.5), 39.0, 0), 9.5, 5.5),
      line=0.6, outline=1.2)


@scene
def s3_check():
    s = r3d.Scene()
    b, p = M.solderful(snapped=True, labels=False)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    for nm, x in (("A", 5.0), ("B", M.SB_W - 5.0)):
        s.anchor(nm + "0", (x, 0, M.SB_T))
        s.anchor(nm + "1", (x, M.SNAP_Y, M.SB_T))
    R("s3_check", s, (0, 0, 1), up=(0, 1, 0), fit=(150, 85), line=0.3)


# ================================================================== step 04
STACK = [("B4", "POWER"), ("B2", "PORTS B + METERS"), ("B1", "PORTS A"), ("B3", "CORE")]   # bottom to top


@scene
def s4_stack():
    s = r3d.Scene()
    gap = 16.0
    for k, (n, role) in enumerate(STACK):
        z0 = k * gap
        b, p = M.solderful(snapped=True, z0=z0, labels=False)
        s.add(f"card{k}", b, M.RED_PCB).add(f"pads{k}", p, M.GOLD, 0.0)
        s.text(f"card{k}", n, (12, -0.001, z0 + 0.25), (1, 0, 0), (0, 0, 1), 1.25, colour="#111111",
               font="Helvetica-Bold", anchor="start")
        s.anchor(f"lab{k}", (13.5, 0, z0 + 0.8))
        s.anchor(f"right{k}", (M.SB_W, 0, z0 + 0.8))
    R("s4_stack", s, (-0.35, -1, 0.55), fit=(250, 210), line=0.3)


@scene
def s4_photo():
    s = r3d.Scene()
    s.add("bench", M.bench(-35, -35, 135, 85, t=20, top=0), M.BENCH)
    b, p = M.solderful(snapped=True, labels=False)
    s.add("card", b, M.RED_PCB).add("pads", p, M.GOLD, 0.0)
    rl, xf = place(M.ruler(150), (0, 1, 0), (-1, 0, 0), (M.SB_W + 28, -25, 0))
    s.xf = xf
    M.ruler(150, scene=s, step=1)
    s.xf = None
    s.add("ruler", rl, M.STEEL)
    ph, sc, ln = M.phone()
    cam = M.box(6, 120, -1.2, 26, 140, 0).edges("|Z").fillet(4)
    ph, xf = place(ph, (1, 0, 0), (0, -1, 0), (5, 95, 150))      # screen down, camera toward the card
    cam, _ = place(cam, (1, 0, 0), (0, -1, 0), (5, 95, 150))
    s.add("phone", ph, M.BLACK).add("cam", cam, "#555A60")
    s.anchor("phone", (76.5, 40, 150))
    s.anchor("card", (40, 20, M.SB_T))
    s.anchor("ruler", (M.SB_W + 15, 60, 1))
    R("s4_photo", s, (0.55, -1, 0.42), fit=(240, 230), line=0.35)


if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENES)
    if names[0].startswith("+"):
        names = list(SCENES)[list(SCENES).index(names[0][1:]):]
    for n in names:
        t = time.time()
        SCENES[n]()
