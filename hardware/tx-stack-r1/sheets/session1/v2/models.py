"""CadQuery models for the Session 1 sheets: the parts from the project's own numbers, the tools from published
nominal dimensions (no vendor STEP could be fetched in this session; see the report).

Card numbers: hardware/tx-stack-r1/sources.py (SolderFul DKS-SOLDERBREAD-02 drawing p.1-2) via layout/stack.py.
PAD3U numbers: sources.py strip_size / pad_pitch and build/BACKPLANE.md.
"""
import math

import cadquery as cq
import numpy as np

P = 2.54

# ------------------------------------------------------------------ colours
RED_PCB = "#C42A2E"
GOLD = "#D9AE3F"
SILK = "#FFFFFF"
FR4 = "#E4DBB4"
TIN = "#C8CCD0"
HAZ = "#FFD400"
STEEL = "#B9BCC0"
SAFETY = "#F0A21A"      # tool safety yellow (amber, so the hazard-yellow work piece stays distinct)
DARK = "#3A3A3A"
LCD = "#D7DEB2"
BRASS = "#D9B45A"
BENCH = "#9A958B"
WOOD = "#C69C6D"
TOWEL = "#6E9BC4"
SAND = "#B9A27A"
BLACK = "#202020"
COPPER = "#C8834A"
TIN = "#BFC5CC"                                # tinned pads (PAD3U, both faces)


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


# ------------------------------------------------------------------ SolderFul BreadBoard (DigiKey SOLDERBREAD#02-ND)
SB_W, SB_H, SB_T = 81.3, 50.8, 1.6
SB_X1 = 3.82                                   # number 1 hole from the left edge
LET_Y = {c: 11.43 + i * P for i, c in enumerate("ABCDE")}
LET_Y.update({c: SB_H - 11.43 - (4 - i) * P for i, c in enumerate("FGHIJ")})
RAILS_FRONT = (3.81, 6.35)                     # outer, inner rail from the front edge
RAILS_BACK = (SB_H - 6.35, SB_H - 3.81)        # inner, outer back rail
SNAP_Y = 41.91                                 # sources.py sb_snap_y (TBD: Clint measures)
NUM_Y_FRONT = 8.9                              # number row between the front rails and row A
NUM_Y_BACK = 40.95                             # number row on the J side, just short of the snap line


def col_x(n):
    return SB_X1 + (n - 1) * P


# ------------------------------------------------------------------ slot-key colour dot (model.KEY_COLOUR)
KEY_RGB = {"blue": "#2D6FD0", "green": "#2E9E4F", "yellow": "#FFD400", "red": "#E8202A"}
DOT_XY = (SB_X1, 1.6)                          # top face, at the front edge, near column 1 (build/Bn.md step 1.4)
DOT_R = 1.3


def key_dot(s, colour, z=SB_T, xy=DOT_XY, r=DOT_R, name="keydot"):
    """The card's colour dot (paint pen or sticker) on its top face at the front edge, near column 1: a disc in the
    key colour on a thin white rim (the red dot must read on the red card). Anchor `name` at its centre."""
    x, y = xy
    rim = cq.Solid.makeCylinder(r + 0.35, 0.10, cq.Vector(x, y, z), cq.Vector(0, 0, 1))
    dot = cq.Solid.makeCylinder(r, 0.10, cq.Vector(x, y, z + 0.10), cq.Vector(0, 0, 1))
    s.add(name + "_rim", rim, "#FFFFFF", 0.2).add(name, dot, KEY_RGB[colour], 0.2)
    s.anchor(name, (x, y, z + 0.2), on=name)


def solderful(snapped=False, decals=None, part="card", z0=0.0, labels=True):
    """Card in its own frame: X along numbers 1-30, Y from the FRONT edge (A side), top face at z0 + 1.6.
    decals: an r3d.Scene to receive the silkscreen. Returns (board, pads)."""
    H = SNAP_Y if snapped else SB_H
    t = SB_T
    b = cq.Workplane("XY").rect(SB_W, H, centered=False).extrude(t)
    b = b.edges("|Z").fillet(1.2)
    # half-round notches, 3.0 mm: short edges at Y 8.9 / 25.4 / 41.9, long edges at X 6.35 / 74.95
    notch = []
    for y in (8.9, 25.4, 41.9):
        if y < H - 0.5:
            notch += [(0, y), (SB_W, y)]
    for x in (6.35, 74.95):
        notch.append((x, 0))
        if not snapped:
            notch.append((x, SB_H))
    b = b.faces(">Z").workplane(origin=(0, 0, t)).pushPoints(notch).hole(3.0)
    # mounting holes in the centre channel
    mh = [(SB_W / 2 - 35.55, 25.4), (SB_W / 2, 25.4), (SB_W / 2 + 35.55, 25.4)]
    b = b.faces(">Z").workplane(origin=(0, 0, t)).pushPoints(mh).hole(3.0)
    rails = list(RAILS_FRONT) + ([] if snapped else list(RAILS_BACK))
    grid = [(col_x(n), LET_Y[c]) for n in range(1, 31) for c in "ABCDEFGHIJ"]
    railp = [(col_x(n), y) for n in range(1, 31) for y in rails]
    b = b.faces(">Z").workplane(origin=(0, 0, t)).pushPoints(grid + railp).hole(1.0)
    pt = 0.06
    pads = (cq.Workplane("XY").workplane(offset=t).pushPoints(grid).slot2D(2.05, 1.55, 90).extrude(pt))
    pads = pads.union(cq.Workplane("XY").workplane(offset=t).pushPoints(railp).circle(0.85).extrude(pt))
    # the strips, as on the real card: each column's A-E pads joined, its F-J pads joined, each rail one long trace
    sw = 0.9
    for n in range(1, 31):
        for lo, hi in (("A", "E"), ("F", "J")):
            pads = pads.union(box(col_x(n) - sw / 2, LET_Y[lo], t, col_x(n) + sw / 2, LET_Y[hi], t + pt))
    for y in rails:
        pads = pads.union(box(col_x(1), y - sw / 2, t, col_x(30), y + sw / 2, t + pt))
    pads = pads.faces(">Z").workplane(origin=(0, 0, t + pt)).pushPoints(grid + railp).hole(1.0)
    b, pads = b.translate((0, 0, z0)), pads.translate((0, 0, z0))
    if decals is not None and labels:
        top = z0 + t + 0.001
        sz = 1.25
        for n in range(1, 31):
            decals.text(part, str(n), (col_x(n), NUM_Y_FRONT - sz * 0.36, top), (1, 0, 0), (0, 1, 0), sz)
            decals.text(part, str(n), (col_x(n), NUM_Y_BACK - sz * 0.36, top), (1, 0, 0), (0, 1, 0), sz)
        for c, y in LET_Y.items():
            decals.text(part, c, (1.75, y - 0.5, top), (1, 0, 0), (0, 1, 0), 1.45)
            decals.text(part, c, (SB_W - 1.75, y - 0.5, top), (1, 0, 0), (0, 1, 0), 1.45)
        for (y, s) in zip(rails, ["+", "−", "−", "+"]):
            decals.text(part, s, (1.75, y - 0.6, top), (1, 0, 0), (0, 1, 0), 1.9)
            decals.text(part, s, (SB_W - 1.75, y - 0.6, top), (1, 0, 0), (0, 1, 0), 1.9)
        decals.text(part, "DigiKey", (SB_W / 2 - 17.8, 25.4 - 0.55, top), (1, 0, 0), (0, 1, 0), 1.7,
                    font="Helvetica-Bold")
        decals.text(part, "SolderFul BreadBoard", (SB_W / 2 + 17.8, 25.4 - 0.5, top), (1, 0, 0), (0, 1, 0), 1.45)
    return b, pads


# ------------------------------------------------------------------ BusBoard PAD3U
PAD_W, PAD_H, PAD_T = 100.08, 160.02, 1.6     # stood on its short edge: 38 holes across, 62 up
PAD_MX = (PAD_W - 37 * P) / 2                  # 3.05: grid centred (assumed)
PAD_MY = (PAD_H - 61 * P) / 2                  # 2.54
# Repo 114aae1: the piece keeps NO factory edge. Lines -1..29 sit in PAD3U columns 6..36 and holes 1..39 in rows
# 1..39, leaving one spare row below and right (and more left and above). Every edge is midway between rows.
LINE0_COL = 7                                  # line 0 = PAD3U column 7 (line -1 = column 6, line 29 = column 36)
PIECE_X0 = PAD_MX + (LINE0_COL - 0.5) * P      # main piece left edge (above the tab): midway between lines -1 and 0
PIECE_X1 = PAD_MX + (LINE0_COL + 29.5) * P     # right cut: midway between line 29 and the spare column
PIECE_Y0 = PAD_MY + 0.5 * P                    # bottom cut: midway between the spare row and hole 1
PIECE_Y1 = PAD_MY + 39.5 * P                   # top cut: midway between hole 39 and the spare row above


TAB_X0 = PAD_MX + (LINE0_COL - 1.5) * P        # tab (line -1) left edge: midway between lines -2 and -1
TAB_Y1 = PAD_MY + 3.5 * P                      # tab top: the score above hole 3 (midway between holes 3 and 4)


def row_y(hole):
    """Centre of hole `hole` (1-39) along the piece."""
    return PAD_MY + hole * P


def pad3u_L(x_main0=None, x_tab0=None, x1=None, y_tab1=None, y1=None, drilled=(), y0=None):
    """The L backplane (repo 4550f83): main x_main0..x1 by y0..y1, plus the tab x_tab0..x_main0 by y0..y_tab1.
    Holes are drilled after the union, so the line 0 hole 2 hole may cross into the tab."""
    x_main0 = PIECE_X0 if x_main0 is None else x_main0
    x_tab0 = TAB_X0 if x_tab0 is None else x_tab0
    x1 = PIECE_X1 if x1 is None else x1
    y0 = PIECE_Y0 if y0 is None else y0
    y_tab1 = TAB_Y1 if y_tab1 is None else y_tab1
    y1 = PIECE_Y1 if y1 is None else y1
    b = box(x_main0, y0, 0, x1, y1, PAD_T).union(box(x_tab0, y0, 0, x_main0 + 0.01, y_tab1, PAD_T))
    pts = pad3u_grid(x_main0, y0, x1, y1) + pad3u_grid(x_tab0, y0, x_main0, y_tab1)
    plain = [p for p in pts if not any(abs(p[0] - d[0]) < 0.01 and abs(p[1] - d[1]) < 0.01 for d in drilled)]
    if plain:
        b = b.faces(">Z").workplane(origin=(0, 0, PAD_T)).pushPoints(plain).hole(1.0)
    if drilled:
        b = b.faces(">Z").workplane(origin=(0, 0, PAD_T)).pushPoints(list(drilled)).hole(3.2)
    return b


def hacksaw():
    """300 mm (12 in) hacksaw. Blade along +X from x = 0 to 300, teeth edge at y = 0 facing -Y, frame above (+Y),
    centred on z = 0. Returns (frame, blade, handle)."""
    blade = box(-5, 0, -0.33, 305, 12.5, 0.33)
    top = box(-14, 92, -5, 318, 102, 5)
    front = box(305, 4, -5, 318, 102, 5)
    back = box(-14, 4, -5, -1, 102, 5)
    frame = top.union(front).union(back)
    handle = (cq.Workplane("XY").polyline([(-14, 98), (-14, 20), (-30, -40), (-62, -40), (-46, 30), (-46, 98)])
              .close().extrude(22).translate((0, 0, -11)).edges("|Z").fillet(5))
    return frame, blade, handle


def hole_xy(line, hole):
    """Backplane piece: line -1 (tab) and 0-20 (left to right), hole 1-39 (bottom to top), full-board frame."""
    return PAD_MX + (LINE0_COL + line) * P, PAD_MY + hole * P


def pad3u_grid(x0, y0, x1, y1):
    return [(PAD_MX + i * P, PAD_MY + j * P) for i in range(38) for j in range(62)
            if x0 < PAD_MX + i * P < x1 and y0 < PAD_MY + j * P < y1]


def pad3u_region(x0, y0, x1, y1, drilled=(), pads=False):
    """A rectangle of the PAD3U (full-board frame, FRONT face up at z = 1.6). Returns (board, pads or None)."""
    b = box(x0, y0, 0, x1, y1, PAD_T)
    pts = pad3u_grid(x0, y0, x1, y1)
    plain = [p for p in pts if not any(abs(p[0] - d[0]) < 0.01 and abs(p[1] - d[1]) < 0.01 for d in drilled)]
    if plain:
        b = b.faces(">Z").workplane(origin=(0, 0, PAD_T)).pushPoints(plain).hole(1.0)
    if drilled:
        b = b.faces(">Z").workplane(origin=(0, 0, PAD_T)).pushPoints(list(drilled)).hole(3.2)
    pd = None
    if pads:      # copper side (bottom face) only: the FRONT is the component side
        pd = cq.Workplane("XY").workplane(offset=-0.06).pushPoints(pts).circle(0.95).extrude(0.06)
        pd = pd.faces("<Z").workplane(origin=(0, 0, -0.06)).pushPoints(pts).hole(1.0)
    return b, pd


# ------------------------------------------------------------------ M3 heat-set insert, 5.7 long, 4.6 over the knurl
INS_L, INS_D = 5.7, 4.6


def insert():
    """Axis along +Z from z = 0 (smooth lead-in collar end) to z = 5.7. Two knurl bands of opposite twist."""
    rt, rr = INS_D / 2, 2.05
    n = 18
    star = [((rt if i % 2 == 0 else rr) * math.cos(math.pi * i / n), (rt if i % 2 == 0 else rr) * math.sin(math.pi * i / n))
            for i in range(2 * n)]
    collar = cq.Workplane("XY").circle(2.0).extrude(1.0)
    k1 = cq.Workplane("XY").workplane(offset=1.0).polyline(star).close().twistExtrude(2.1, 25)
    groove = cq.Workplane("XY").workplane(offset=3.1).circle(2.0).extrude(0.5)
    k2 = cq.Workplane("XY").workplane(offset=3.6).polyline(star).close().twistExtrude(2.1, -25)
    body = collar.union(k1).union(groove).union(k2)
    body = body.faces(">Z").workplane().hole(2.6)
    return body


# ------------------------------------------------------------------ tools (modelled from nominal dimensions)
def caliper(gap, reading="0.00", scene=None, part="cal_head", beam_part="cal_beam"):
    """150 mm digital caliper (typical: 16 x 3.5 beam, 40 mm outside jaws, 230 overall). Frame: beam along +X,
    outside jaws down (-Y), fixed jaw face at x = 0, moving jaw face at x = gap, the beam's face at z = 0..3.5.
    Returns (beam+fixed jaw, slider)."""
    T = 3.5
    beam = box(-14, 0, 0, 225, 16, T)
    fj = cq.Workplane("XY").polyline([(0, 0), (0, -38.5), (-1.2, -40), (-5, -37), (-14, -12), (-14, 0)]).close().extrude(T)
    fi = cq.Workplane("XY").polyline([(-14, 16), (-1, 16), (-0.3, 29), (-2, 30), (-14, 22)]).close().extrude(T)
    fixed = beam.union(fj).union(fi)
    mj = cq.Workplane("XY").polyline([(gap, 0), (gap, -38.5), (gap + 1.2, -40), (gap + 5, -37), (gap + 14, -12),
                                      (gap + 14, 0)]).close().extrude(T)
    mi = cq.Workplane("XY").polyline([(gap + 14, 16), (gap + 1, 16), (gap + 0.3, 29), (gap + 2, 30),
                                      (gap + 14, 22)]).close().extrude(T)
    head = box(gap + 14, -7, -1.5, gap + 82, 23, 12).edges("|Z").fillet(3)
    jaw_plate = box(gap, -2, -0.6, gap + 14, 18, T + 0.6)
    thumb = cq.Workplane("XY").cylinder(4, 5).rotate((0, 0, 0), (0, 1, 0), 0).translate((gap + 16, -9, 5))
    slider = head
    lcd = box(gap + 22, 4, 12, gap + 62, 16.5, 12.4)
    btns = [cq.Workplane("XY").cylinder(1.0, 2.6).translate((gap + 30 + i * 13, -2.2, 12.5)) for i in range(3)]
    if scene is not None:
        segs = []
        for i in range(0, 221):
            x = gap + 82 + i if False else i
            if gap - 1 < x < gap + 83:
                continue
            ln = 4.5 if i % 10 == 0 else 3.2 if i % 5 == 0 else 2
            segs.append(((x, 16, T + 0.001), (x, 16 - ln, T + 0.001)))
        scene.lines(beam_part, segs, width=0.3)
        scene.text("cal_lcd", reading, (gap + 59, 6.3, 12.401), (1, 0, 0), (0, 1, 0), 8.2, colour="#1A1A1A",
                   font="Helvetica-Bold", anchor="end")
    return fixed, slider, lcd, btns, mj.union(mi).union(jaw_plate)


def ruler(length=300, width=25, t=1.0, scene=None, part="ruler", step=1):
    """Steel rule along +X from x = 0, y 0..width, top face z = t (300 x 25 x 1.0 typical)."""
    r = box(0, 0, 0, length, width, t)
    r = r.faces(">Z").workplane(origin=(length - 8, width / 2, t)).hole(5)
    if scene is not None:
        segs = []
        for i in range(0, length - 14, step):
            x = 3 + i
            ln = 5 if i % 10 == 0 else 3.5 if i % 5 == 0 else 2.2
            segs.append(((x, width, t + 0.001), (x, width - ln, t + 0.001)))
            if i % 2 == 0 and step == 1:
                segs.append(((x, 0, t + 0.001), (x, 1.8 if i % 10 else 3.5, t + 0.001)))
        scene.lines(part, segs, width=0.25)
        for i in range(10, length - 14, 10 * step if length < 160 else 20 * step):
            scene.text(part, str(i // 10), (3 + i, width - 9, t + 0.001), (1, 0, 0), (0, 1, 0), 3.2, colour="#202020")
    return r


def knife(scene=None, blade_out=24):
    """18 mm snap-off utility knife: handle 150 x 26 x 15 along -X from x = 0, blade out along +X to x = blade_out,
    blade in the XY plane, cutting edge at y = 0 (the tip at (blade_out, 0)). Returns (handle, blade)."""
    hd = (cq.Workplane("XY").polyline([(0, -4), (-150, -4), (-150, 22), (-6, 22), (0, 16)]).close().extrude(15)
          .translate((0, 0, -7.5)).edges("|Z").fillet(2.5))
    grip = box(-120, 20, -4, -40, 23, 4)
    slide = box(-70, 21.5, -3, -52, 25, 3)
    blade = cq.Workplane("XY").polyline([(-20, 0), (blade_out, 0), (blade_out - 10.8, 18), (-20, 18)]).close() \
        .extrude(0.5).translate((0, 0, -0.25))
    if scene is not None:
        segs = []
        for k in range(1, 4):
            x = blade_out - 10.8 * 0 - k * 9
            segs.append(((x, 0.4, 0.26), (x - 10.8 * (18 - 0.8) / 18, 17.6, 0.26)))
        scene.lines("blade", segs, width=0.35, colour="#6A6E73")
    return hd.union(grip).union(slide), blade


def c_clamp(opening=30):
    """2 in C-clamp, frame in the XZ plane. The screw pad's face is at z = 0 pointing down (-Z), the anvil face at
    z = -opening pointing up. Screw axis = Z through x = 0. Returns (frame, screw)."""
    th = 9      # frame thickness (Y)
    d = 52      # throat depth
    top, bot = 14, -opening - 12
    outer = [(-d - 12, top + 12), (8, top + 12), (8, top), (-d, top), (-d, bot), (8, bot), (8, bot - 12),
             (-d - 12, bot - 12)]
    fr = cq.Workplane("XZ").polyline(outer).close().extrude(th / 2, both=True)
    boss = cq.Workplane("XY").circle(9).extrude(14).translate((0, 0, top))
    anvil = cq.Workplane("XY").circle(8).extrude(12).translate((0, 0, bot)).union(
        cq.Workplane("XY").circle(9).extrude(12).translate((0, 0, bot - 12)))
    frame = fr.union(boss).union(anvil)
    screw = cq.Workplane("XY").circle(4.5).extrude(top + 34).translate((0, 0, 0))
    pad = cq.Workplane("XY").circle(8).extrude(3)
    tbar = cq.Workplane("YZ").circle(3).extrude(30, both=True).translate((0, 0, top + 30))
    return frame, screw.union(pad).union(tbar)


def drill_bit(d=3.2, L=65, flute=36):
    """DIN 338 jobber drill 3.2: 65 overall, 36 flute. Axis along +X, the point at x = L."""
    r = d / 2
    shank = cq.Workplane("YZ").circle(r).extrude(L - flute)
    sec = cq.Sketch().circle(r).push([(0, r * 0.62), (0, -r * 0.62)]).rect(2 * r, r * 0.75, mode="s")
    body = cq.Workplane("YZ").workplane(offset=L - flute).placeSketch(sec).twistExtrude(flute, 360 * flute / (math.pi * d / math.tan(math.radians(30))))
    tip_len = r / math.tan(math.radians(59))
    cone = cq.Solid.makeCone(r * 1.5, 0, tip_len * 1.5, cq.Vector(L - tip_len * 1.5, 0, 0), cq.Vector(1, 0, 0))
    big = cq.Workplane("YZ").workplane(offset=L - flute).circle(r * 2).extrude(flute - tip_len * 1.5)
    body = body.intersect(big.union(cq.Workplane().add(cone)))
    return shank.union(body)


def marker():
    """Fine-point permanent marker (cap on the back): about 137 long, barrel 11.5. Axis along +X, tip at x = 0+.
    Returns (barrel, cap, tip)."""
    tip = cq.Workplane("YZ").circle(0.6).extrude(3).translate((-3, 0, 0))
    cone = cq.Solid.makeCone(1.0, 4.8, 9, cq.Vector(-3 - 9 + 9, 0, 0), cq.Vector(-1, 0, 0))
    barrel = cq.Workplane("YZ").circle(5.4).extrude(-110).translate((-12, 0, 0)).union(cq.Workplane().add(cone))
    cap = cq.Workplane("YZ").circle(6.0).extrude(-50).translate((-90, 0, 0))
    clip = box(-140, -1.5, 5.5, -100, 1.5, 7.5)
    return barrel, cap.union(clip), tip


def hand_file(L=150):
    """Flat hand file: 150 blade along +X ending at x = 0 (the tip), 16 wide, 4 thick; handle behind. (blade, handle)"""
    blade = (cq.Workplane("XY").polyline([(0, -6), (-L, -8), (-L, 8), (0, 6)]).close().extrude(4).translate((0, 0, -2)))
    tang = box(-L - 12, -2, -1, -L, 2, 1)
    handle = cq.Workplane("YZ").circle(12).extrude(-95).translate((-L - 8, 0, 0)).edges().fillet(4)
    return blade.union(tang), handle


def phone():
    """Phone 71.5 x 147 x 8, screen up (+Z), long side along Y."""
    b = box(0, 0, 0, 71.5, 147, 8).edges("|Z").fillet(9).edges(">Z").fillet(1.5)
    scr = box(4, 9, 8, 67.5, 138, 8.05).edges("|Z").fillet(5)
    lens = cq.Workplane("XY").cylinder(0.3, 2).translate((35.75, 142, 8.15))
    return b, scr, lens


def mask():
    """FFP2 cup mask, facing -Y (out toward the viewer): a lofted dome. Returns (shell, strap)."""
    shell = (cq.Workplane("XZ").ellipse(62, 52).workplane(offset=30).ellipse(40, 32).workplane(offset=18)
             .ellipse(14, 10).loft(combine=True))
    valve = cq.Workplane("XZ").workplane(offset=46).circle(10).extrude(8).translate((0, 0, -10))
    strap = (cq.Workplane("XZ").ellipse(64, 54).ellipse(61, 51).extrude(4).translate((0, 4, 0)))
    return shell, strap


def bench(x0, y0, x1, y1, t=25, top=0.0):
    return box(x0, y0, top - t, x1, y1, top)


# ================================================================== repo 82edf8a: the PAD3U's plated end, factory edges
# Board frame (lying, FRONT = component face up at z = PAD_T): x along the 160 length from the plain-hole end,
# y along the 38 holes from the hole-1 edge. Numbers: backplane-mount-spec.md section 1 (Clint's 300 dpi scan).
B_SIDE = 2.81                                  # long sides: outer hole centres to edge
B_FAR = 2.23                                   # plain-hole end: last row to the edge
B_MH_OFF = 2.65                                # mounting holes beyond the end row's centres
B_MH_EDGE = 2.83                               # plated-end edge beyond the mounting holes [TBD-MEASURE]
B_ROWS = 61                                    # rows on the scan; the mounting holes sit where a 62nd would be
B_W = 2 * B_SIDE + 37 * P                      # 99.60 (scan 99.68)
B_END_X = B_FAR + (B_ROWS - 1) * P             # the end row (line 30) centres
B_MH_X = B_END_X + B_MH_OFF
B_L = B_MH_X + B_MH_EDGE                       # 160.11 (BusBoard 160.02)
B_MH_D, B_MH_RING = 2.80, 3.75
B_LINE0_ROW = B_ROWS - 30                      # line 0 = row 31 from the plain end (repo 91a5345: 31 lines, 0-30)
B_SCORE_X = B_FAR + (B_LINE0_ROW - 1) * P - P / 2   # midway between line 0 and the next row out
B_SQ_ROW = 4                                   # square-pad lines: r % 5 == 4, i.e. lines 29, 24, ... 4
B_SQ_HOLE = 0                                  # square-pad hole rows: holes 5, 10, ... 35 (IMG_8594: 5th from hole 1's edge)


def b_row_x(r):
    return B_FAR + (r - 1) * P


def b_xy(line, hole):
    """Line 0-30 (left to right), hole 1-38 (bottom to top), board frame."""
    return b_row_x(B_LINE0_ROW + line), B_SIDE + (hole - 1) * P


B_MH_LO = (B_MH_X, b_xy(0, 2)[1])              # lower mounting hole, level with hole 2
B_MH_HI = (B_MH_X, b_xy(0, 37)[1])             # upper, level with hole 37
B_PLAIN = [(B_FAR + P / 2, b_xy(0, 2)[1]), (B_FAR + P / 2, b_xy(0, 37)[1])]   # the other end: plain 1.5 holes


def b_holes(x0, x1, y0=0.0, y1=None):
    y1 = B_W if y1 is None else y1
    return [(b_row_x(r), B_SIDE + j * P) for r in range(1, B_ROWS + 1) for j in range(38)
            if x0 < b_row_x(r) < x1 and y0 < B_SIDE + j * P < y1]


def b_missing(p):
    """The end row's pads beside the mounting holes are left off (and so are their holes); so are the two pads
    either side of each plain Ø1.5 hole at the other end (a 1.9 pad 1.27 away would run into it)."""
    if abs(p[0] - B_END_X) < 0.01 and (abs(p[1] - B_MH_LO[1]) < 0.01 or abs(p[1] - B_MH_HI[1]) < 0.01):
        return True
    return any(abs(p[0] - px) < 1.3 and abs(p[1] - py) < 0.01 for px, py in B_PLAIN)


def b_region(x0, x1, y0=0.0, y1=None, drilled=(), opened=False, pads=True, plain_holes=True):
    """A rectangle of the PAD3U in the board frame (front up). drilled: holes opened to 3.2. opened: the lower
    mounting hole drilled out to 3.2. Returns (board, copper or None)."""
    y1 = B_W if y1 is None else y1
    b = box(x0, y0, 0, x1, y1, PAD_T)
    pts = [p for p in b_holes(x0, x1, y0, y1) if not b_missing(p)]
    small = [p for p in pts if not any(abs(p[0] - d[0]) < 0.01 and abs(p[1] - d[1]) < 0.01 for d in drilled)]
    if small:
        b = b.faces(">Z").workplane(origin=(0, 0, PAD_T)).pushPoints(small).hole(1.0)
    big = [d for d in drilled if x0 - 1.6 < d[0] < x1 + 1.6]
    if big:
        b = b.cut(cq.Workplane("XY").pushPoints(big).circle(1.6).extrude(PAD_T + 2).translate((0, 0, -1)))
    mh = [(B_MH_LO, 3.2 / 2 if opened else B_MH_D / 2), (B_MH_HI, B_MH_D / 2)]
    for (mx, my), r in mh:
        if x0 < mx < x1 and y0 < my < y1:
            b = b.cut(cq.Workplane("XY").center(mx, my).circle(r).extrude(PAD_T + 2).translate((0, 0, -1)))
    if plain_holes:
        for (px, py) in B_PLAIN:
            if x0 < px < x1 and y0 < py < y1:
                b = b.cut(cq.Workplane("XY").center(px, py).circle(0.75).extrude(PAD_T + 2).translate((0, 0, -1)))
    cu = None
    if pads:
        cu = b_copper(x0, x1, y0, y1, drilled, opened)
    return b, cu


def b_copper(x0, x1, y0, y1, drilled=(), opened=False):
    """The PAD3U is double-sided: a plated pad on BOTH faces of every hole; the plated mounting holes' rings on both
    faces. Pads are round except on every 5th line and every 5th hole row, which are square, like graph-paper
    gridlines (Clint's photos IMG_8592/8593, 2026-11-16): at the plated end line 30 is round, line 29 square, then
    four round and a square (lines 24, 19, 14, 9, 4); with FRONT up and the big holes on the right, the square rows
    are the 4th, 9th, ... from the far edge (holes 35, 30, ... 5), and line 30 has one more square at hole 4
    (IMG_8594). That face, the one with "PadBoard-3U-2.00 ... BusBoard.net" reading up the plated end, is FRONT."""
    out = []
    for (x, y) in b_holes(x0, x1, y0, y1):
        if b_missing((x, y)) or any(abs(x - d[0]) < 0.01 and abs(y - d[1]) < 0.01 for d in drilled):
            continue
        r = int(round((x - B_FAR) / P))
        j = int(round((y - B_SIDE) / P))
        sq = (r % 5 == B_SQ_ROW) or ((j + 1) % 5 == B_SQ_HOLE) or (r == B_ROWS - 1 and j + 1 == 4)
        #    r: rows from the plain end (line 30 = 60); j + 1 = hole; plus one lone square at line 30, hole 4
        for z in (-0.06, PAD_T):
            w = cq.Workplane("XY").workplane(offset=z).center(x, y)
            pad = (w.rect(1.9, 1.9) if sq else w.circle(0.95)).circle(0.5).extrude(0.06)
            out.append(pad.val())
    for (mx, my), hi in ((B_MH_LO, opened), (B_MH_HI, False)):
        if x0 < mx < x1 and y0 < my < y1:
            ri = 1.6 if hi else B_MH_D / 2
            for z in (-0.06, PAD_T):
                ring = (cq.Workplane("XY").workplane(offset=z).center(mx, my).circle(B_MH_RING / 2).circle(ri)
                        .extrude(0.06))
                out.append(ring.val())
    return cq.Compound.makeCompound(out) if out else None


# ------------------------------------------------------------------ Bourns MF-R010 PTC, Style 1 (datasheet table)
def _rod(pts, r):
    """A round wire through 3D points (cylinders + ball joints)."""
    pts = [np.asarray(p, float) for p in pts]
    sol = []
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.linalg.norm(b - a))
        if L > 1e-6:
            sol.append(cq.Solid.makeCylinder(r, L, cq.Vector(*a), cq.Vector(*((b - a) / L))))
    for p in pts[1:-1]:
        sol.append(cq.Solid.makeSphere(r, cq.Vector(*p)))
    s = sol[0]
    for x in sol[1:]:
        s = s.fuse(x)
    return s.clean()


def mfr010(p1, p2, card_top, w=7.4, t=3.1, h=12.7, pitch=5.1, lead_d=0.51, seat=1.0):
    """MF-R010 Style 1 standing on the card, its two leads formed out from the 5.1 pitch to the holes p1, p2 (XY).
    A dipped round disc (A = w across, E = t thick) on two kinked leads; B = h from the top to the kinks, which sit
    `seat` above the card. Returns dict(body, leads, top, face, n): face = centre of the disc's +n (viewer-side) face."""
    p1, p2 = np.asarray(p1, float)[:2], np.asarray(p2, float)[:2]
    u2 = (p2 - p1) / np.linalg.norm(p2 - p1)
    n2 = np.array([u2[1], -u2[0]])
    if n2[0] > 0 or (abs(n2[0]) < 1e-9 and n2[1] > 0):
        n2 = -n2                                              # face the -X (front-left) side
    mid = (p1 + p2) / 2
    u, n = np.array([*u2, 0.0]), np.array([*n2, 0.0])
    o = np.array([*mid, 0.0])
    zk = card_top + seat                                     # kink seating plane
    ztop = zk + h
    zc = ztop - w / 2                                        # disc centre
    P = lambda a, z, b=0.0: o + u * a + n * b + np.array([0, 0, z])
    disc = cq.Solid.makeCylinder(w / 2, t, cq.Vector(*P(0, zc, -t / 2)), cq.Vector(*n))
    disc = cq.Workplane().add(disc).edges().fillet(0.9).val()
    neck_bot = zc - w / 2 - 1.1                              # the dip runs a little way down the leads
    corners = [P(-2.3, zc - 2.6), P(2.3, zc - 2.6), P(pitch / 2 + 0.4, neck_bot), P(-pitch / 2 - 0.4, neck_bot)]
    base = cq.Workplane().polyline([tuple(c - n * (t * 0.35)) for c in corners]).close().wire().val()
    neck = cq.Solid.extrudeLinear(cq.Face.makeFromWires(base), cq.Vector(*(n * t * 0.7)))
    body = disc.fuse(neck).clean()
    leads = None
    for sgn, p in ((-1, p1), (1, p2)):
        a0 = sgn * pitch / 2
        hole = np.array([*p, 0.0]) - o
        a1 = float(hole @ u)
        pts = [P(a0, neck_bot + 0.5), P(a0, zk + 1.3), P(a0 + sgn * 0.45, zk + 0.75), P(a0, zk + 0.2),
               P(a1, card_top + 0.7), P(a1, card_top - 1.6)]
        lg = _rod(pts, lead_d / 2)
        leads = lg if leads is None else leads.fuse(lg)
    return dict(body=body, leads=leads, top=P(0, ztop), face=P(0, zc, t / 2), n=n, u=u, zc=zc)
