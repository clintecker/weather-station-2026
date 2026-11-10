"""Drawings and build sheets from layout/stack.py and cage/cage.py.

  drawings/B1..B4-top.svg   each card from above, to scale: strips tinted by net, parts, wires
  drawings/backplane.svg    the stripboard backplane from the front (component side)
  drawings/cage-side.svg    the box from the side (section, back wall left, lid right) and from the front
  build/B1..B4.md           each card, step by step: underside wires (with lengths), parts lowest first
                            (with orientation), leads, the strip map, checks before power
  build/BACKPLANE.md        the backplane, step by step
  build/ASSEMBLY.md         the charger's jumper changes before power, the cage, the card order, the cables
Run after layout_checks.py passes: python3 drawings.py [--png]  (--png also writes ../renders/*.png)
"""
import html
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import layout_checks as lc
import stack as st
from stack import S, model
from layout_checks import cage

ROOT = st.HERE.parent
OUT_SVG = ROOT / "drawings"
OUT_MD = ROOT / "build"
K = 9.0                       # px per mm in the card views
M = 70                        # margin, px
NAME = model.NET_NAME

NET_COLOUR = {"+3V3": "#D62728", "GND": "#1A1A1A", "I2C_SDA": "#1F5FBF", "I2C_SCL": "#D4A017",
              "MUX_RST": "#8E44AD", "CUPS": "#2CA02C", "VANE": "#17A589", "RAIN": "#00A3D9", "SYS": "#E67E22",
              "SWDIO": "#7F8C8D", "SWCLK": "#7F8C8D", "NRST": "#7F8C8D", "BUS_SPARE": "#BBBBBB",
              "CUPS_J": "#82C982", "VANE_J": "#7FCFC2", "RAIN_J": "#80D4F0"}
for _k in range(1, 5):
    NET_COLOUR.update({f"P{_k}_3V3": "#F08080", f"P{_k}_SDA": "#6FA8DC", f"P{_k}_SCL": "#F1C40F",
                       f"P{_k}_JSDA": "#A9C9EC", f"P{_k}_JSCL": "#F7DC6F"})


def ncol(net):
    if net in NET_COLOUR:
        return NET_COLOUR[net]
    if net and model.NETS.get(net, ([], {}))[1].get("battery"):
        return "#C0392B"
    return "#888888"


def plain(net):
    return NAME.get(net, "not connected") if net else "not connected"


def esc(s):
    return html.escape(str(s), quote=True)


def sx(x):
    return M + x * K


def sy(y):
    return M + (st.BH - y) * K


def hole_s(h):
    x, y = st.hole_xy(h)
    return sx(x), sy(y)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.items = w, h, []

    def add(self, s):
        self.items.append(s)

    def text(self, x, y, s, size=11, anchor="start", fill="#222", weight="normal", rot=None):
        tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
                 f'font-weight="{weight}"{tr}>{esc(s)}</text>')

    def rect(self, x0, y0, x1, y1, fill="none", stroke="#333", sw=1.0, op=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{min(x0, x1):.1f}" y="{min(y0, y1):.1f}" width="{abs(x1 - x0):.1f}" height="{abs(y1 - y0):.1f}" '
                 f'fill="{fill}" fill-opacity="{op}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def write(self, path, title):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" height="{self.h:.0f}" '
                f'viewBox="0 0 {self.w:.0f} {self.h:.0f}" font-family="Helvetica, Arial, sans-serif">'
                f'<title>{esc(title)}</title><rect width="100%" height="100%" fill="#ffffff"/>')
        path.write_text(head + "\n".join(self.items) + "</svg>\n")


# ------------------------------------------------------------------ conductor helpers
def board_of_end(e):
    if isinstance(e, str):
        return e.split(":")[0]
    return st.board_of_ref().get(e[0])


def end_xy(e):
    """Card-frame point of a conductor end on a card (a hole or a pad), or None."""
    if isinstance(e, str):
        b, h = e.split(":")
        return None if b == "BP" else st.hole_xy(h)
    for _b, pl in st.placements():
        if pl["ref"] == e[0] and e[1] in st.pads_of(pl):
            return st.pads_of(pl)[e[1]]
    return None


def net_of_end(e, ph):
    if isinstance(e, str):
        b, h = e.split(":")
        occ = ph.get((b, h))
        if occ:
            return lc.eff_net(occ)
        return REP[b].get(h.split(".")[0] if b == "BP" else st.strip_of(h))
    return lc.eff_net(e)


def where(e):
    if isinstance(e, str):
        b, h = e.split(":")
        return f"backplane strip {h[1:].split('.')[0]} hole {h.split('.')[1]}" if b == "BP" else h
    part = next(p for p in model.PARTS if p["ref"] == e[0])
    pin = next(x for x in part["pins"] if x[0] == e[1])
    return f"{e[0]} {pin[1]}"


def length(a, c):
    """Cut length for a wire or lead, mm: the route plus 10 mm for strip ends, rounded up to 5 mm."""
    pa, pc = end_xy(a), end_xy(c)
    if pa and pc and board_of_end(a) == board_of_end(c):
        d = abs(pa[0] - pc[0]) + abs(pa[1] - pc[1])
    else:
        d = None
    if d is None:
        return None
    return int(math.ceil((d + 10) / 5) * 5)


# ------------------------------------------------------------------ one card from above
def top_view(b, ph):
    rep = REP
    W, H = sx(st.BW) + 360 + 40 * K, sy(0) + 140
    g = Svg(W, H)
    g.rect(sx(0), sy(st.BH), sx(st.BW), sy(0), "#B3202A", "#5a0e12", 1.5)
    r = S.val("sb_mhole") / 2 * K
    for x, y in st.MHOLES:
        g.add(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r:.1f}" fill="#ffffff" stroke="#888"/>')
    hw = 1.15 * K
    for row in range(1, 31):
        for half, (c0, c1) in (("L", ("a", "e")), ("R", ("f", "j"))):
            net = rep[b].get(f"{half}{row}")
            x0, y0 = hole_s(f"{c1}{row}")
            x1, y1 = hole_s(f"{c0}{row}")
            g.add(f'<rect x="{x0 - hw:.1f}" y="{y0 - hw:.1f}" width="{2 * hw:.1f}" height="{y1 - y0 + 2 * hw:.1f}" '
                  f'rx="{hw:.1f}" fill="{ncol(net) if net else "#E9C46A"}" fill-opacity="{0.55 if net else 0.35}" '
                  f'stroke="#7a5c12" stroke-width="0.6"/>')
    for rail in st.RAIL_Y:
        net = rep[b].get(rail)
        x0, y0 = hole_s(f"{rail}1")
        x1, _ = hole_s(f"{rail}30")
        g.add(f'<rect x="{x0 - hw:.1f}" y="{y0 - hw:.1f}" width="{x1 - x0 + 2 * hw:.1f}" height="{2 * hw:.1f}" rx="{hw:.1f}" '
              f'fill="{ncol(net) if net else "#E9C46A"}" fill-opacity="{0.55 if net else 0.35}" stroke="#7a5c12" stroke-width="0.6"/>')
        g.text(sx(0) - 8, y0 + 4, rail, 10, "end")
    for h in st.ALL_HOLES:
        x, y = hole_s(h)
        g.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{S.val("sb_hole") / 2 * K:.1f}" fill="#2b2b2b"/>')
    for row in range(1, 31):
        x, _ = hole_s(f"a{row}")
        g.text(x, sy(st.BH) - 6, row, 10, "middle")
        g.text(x, sy(0) + 16, row, 10, "middle")
    for c in "abcdefghij":
        _, y = hole_s(f"{c}1")
        g.text(sx(0) - 8, y + 4, c, 11, "end")
    # parts
    for bb, pl in st.placements():
        if bb != b:
            continue
        colour = st.KIND[pl["fp"]][0]
        part = next(p for p in model.PARTS if p["ref"] == pl["ref"])
        for bx in st.boxes_of(pl):
            if bx.keepout:
                g.rect(sx(bx.x0), sy(bx.y1), sx(bx.x1), sy(bx.y0), "none", "#555", 0.8, dash="3 3")
            elif any(k in bx.what for k in ("PCB", "jack", "body", "insulator", "spacer", "module", "lug", "screw")):
                g.rect(sx(bx.x0), sy(bx.y1), sx(bx.x1), sy(bx.y0), colour, colour, 1.2, 0.22)
        x0, y0, x1, y1 = st.outline_of(pl)
        big = (x1 - x0) > 12 and (y1 - y0) > 5
        cx, cy = sx((x0 + x1) / 2), sy((y0 + y1) / 2)
        g.text(cx, cy + 4, f'{pl["ref"]} {part["value"]}' if big else pl["ref"], 11 if big else 8.5, "middle", "#000", "bold")
        for pin, (x, y) in st.pins_of(pl).items():
            net = lc.NET_OF.get((pl["ref"], pin))
            g.add(f'<rect x="{sx(x) - 3.5:.1f}" y="{sy(y) - 3.5:.1f}" width="7" height="7" fill="{ncol(net) if net else "#fff"}" '
                  f'stroke="#000" stroke-width="1"/>')
        for pad, (x, y) in st.pads_of(pl).items():
            net = lc.eff_net((pl["ref"], pad))
            g.add(f'<path d="M{sx(x):.1f},{sy(y) - 5:.1f} l5,5 l-5,5 l-5,-5 z" fill="{ncol(net)}" stroke="#000"/>')
    # conductors
    off = []
    for kind, a, c, side, note in st.WIRES:
        ba, bc = board_of_end(a), board_of_end(c)
        if b not in (ba, bc):
            continue
        pa = end_xy(a) if ba == b else None
        pc = end_xy(c) if bc == b else None
        net = net_of_end(a, lc_ph) or net_of_end(c, lc_ph)
        col = ncol(net)
        dash = ' stroke-dasharray="5 3"' if side == "bottom" else ""
        if pa and pc:
            g.add(f'<line x1="{sx(pa[0]):.1f}" y1="{sy(pa[1]):.1f}" x2="{sx(pc[0]):.1f}" y2="{sy(pc[1]):.1f}" stroke="{col}" '
                  f'stroke-width="{2.4 if kind == "jumper" else 2.0}" stroke-linecap="round"{dash} opacity="0.9"/>')
        else:
            p = pa or pc
            off.append((p, col, note))
    for p, col, note in off:
        g.add(f'<circle cx="{sx(p[0]):.1f}" cy="{sy(p[1]):.1f}" r="5" fill="none" stroke="{col}" stroke-width="2.2"/>')
    # edges
    g.text(sx(st.BW / 2), sy(0) + 40, "FRONT EDGE (lid side): the card slides in from here", 14, "middle", weight="bold")
    g.text(sx(st.BW / 2), sy(st.BH) - 34, f"BACK EDGE: header (column j, rows 1-18) plugs into the backplane", 13, "middle",
           weight="bold")
    g.text(sx(st.BW) + 14, sy(st.BH / 2), "RIGHT EDGE: jack mouths", 12, "start", weight="bold", rot=90)
    g.text(M, 24, f"{b} {st.ROLE[b]}: from above, 1:1 at {K:g} px/mm, SolderFul 81.3 x 50.8 mm", 16, weight="bold")
    # legend
    lx, ly = sx(st.BW) + 40 + 25 * K, sy(st.BH) - 10
    g.text(lx, ly, "Lines on this card", 13, weight="bold")
    nets = sorted({n for n in rep[b].values() if n and "/" not in n}, key=lambda n: plain(n))
    for i, n in enumerate(nets):
        y = ly + 18 + i * 16
        g.add(f'<rect x="{lx}" y="{y - 10}" width="22" height="11" fill="{ncol(n)}" fill-opacity="0.7"/>')
        g.text(lx + 30, y, plain(n), 10.5)
    y = ly + 30 + len(nets) * 16
    for s_, d in (("solid line", "jumper or wire on top"), ("dashed line", "wire on the underside"),
                  ("ring", "lead off the card (to a pad, the charger or a jack)"), ("square", "pin in a hole"),
                  ("diamond", "pad with a soldered lead"), ("grey dashed box", "plug or service keep-out")):
        g.text(lx, y, f"{s_}: {d}", 10)
        y += 15
    g.write(OUT_SVG / f"{b}-top.svg", f"{b} {st.ROLE[b]} from above")


# ------------------------------------------------------------------ the backplane
def backplane_view(ph):
    KB = 7.0
    n_strips = st.BP_STRIPS + 1
    W = M * 2 + n_strips * st.P * KB + 900
    H = M * 2 + (st.BP_HOLES + 2) * st.P * KB + 40

    def bx(i):
        return M + (i + 0.5) * st.P * KB

    def bz(n):
        return H - M - (n + 0.5) * st.P * KB
    g = Svg(W, H)
    g.rect(bx(0) - st.P * KB / 2, bz(st.BP_HOLES + 0.5), bx(st.BP_STRIPS) + st.P * KB / 2, bz(0.5), "#d9c08a", "#7a5c12", 1.2)
    for i in range(n_strips):
        net = REP["BP"].get(f"s{i}")
        g.rect(bx(i) - 1.0 * KB, bz(st.BP_HOLES + 0.4), bx(i) + 1.0 * KB, bz(0.6), ncol(net) if net else "#c8a96a",
               "#7a5c12", 0.6, 0.55 if net else 0.4)
        g.text(bx(i), bz(st.BP_HOLES + 1.2), i, 10, "middle")
        for n in range(1, st.BP_HOLES + 1):
            g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="{0.5 * KB:.1f}" fill="#2b2b2b"/>')
    for n in range(1, st.BP_HOLES + 1, 2):
        g.text(bx(0) - 2.5 * KB, bz(n) + 4, n, 9, "end")
    mx = st.MUX_BOX
    g.rect(M + (mx[0] - st.strip_x(0)) * KB + st.P * KB / 2, bz((mx[3] - st.BP_Z0) / st.P + 1),
           M + (mx[2] - st.strip_x(0)) * KB + st.P * KB / 2, bz((mx[1] - st.BP_Z0) / st.P + 1),
           "none", "#161616", 1.6, dash="8 4")
    g.text(M + (mx[0] + mx[2] - 2 * st.strip_x(0)) / 2 * KB, bz((mx[1] + mx[3] - 2 * st.BP_Z0) / 2 / st.P + 1),
           "PCA9548 mux (behind, on foam)", 12, "middle", weight="bold")
    for ref, pins, note in st.BP_PARTS:
        for pin, h in pins.items():
            i, n = (int(v) for v in h[1:].split("."))
            net = lc.NET_OF.get((ref, pin))
            g.add(f'<rect x="{bx(i) - 4:.1f}" y="{bz(n) - 4:.1f}" width="8" height="8" fill="{ncol(net)}" stroke="#000"/>')
        if ref.startswith("XB"):
            n = int(next(iter(pins.values())).split(".")[1])
            g.rect(bx(1) - 1.27 * KB, bz(n) - 1.27 * KB, bx(18) + 1.27 * KB, bz(n) + 1.27 * KB, "none", "#000", 1.4)
            g.text(bx(20) + 2 * KB, bz(n) + 4, f"{ref}: {note}", 11, weight="bold")
        elif ref.startswith("W") or ref == "XJ1":
            n = int(next(iter(pins.values())).split(".")[1])
            g.text(bx(20) + 2 * KB, bz(n) + 4, f"{ref}: {note}", 10)
    for kind, a, c, side, note in st.WIRES:
        for e, o in ((a, c), (c, a)):
            if isinstance(e, str) and e.startswith("BP:"):
                i, n = (int(v) for v in e[4:].split("."))
                g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="6" fill="none" stroke="#8E44AD" stroke-width="2"/>')
    lx = bx(st.BP_STRIPS) + 2 * KB + 380
    g.text(M, 26, "Backplane: BusBoard ST2 stripboard cut 21 strips x 39 holes, seen from the front (component side); "
           "strips run up and down", 15, weight="bold")
    y = M + 10
    g.text(lx, y, "Strip: line", 13, weight="bold")
    for i in range(n_strips):
        y += 15
        g.text(lx, y, f"{i}: {plain(REP['BP'].get(f's{i}')) if REP['BP'].get(f's{i}') else 'spare / screw strip'}", 10.5)
    y += 25
    for s_ in ("black outline: card socket (Sullins PPPC181LFBN-RC)", "small square: a pin in a hole",
               "purple ring: a lead soldered on the copper side", "dashed: the mux, behind on foam"):
        g.text(lx, y, s_, 10)
        y += 15
    g.write(OUT_SVG / "backplane.svg", "backplane")


# ------------------------------------------------------------------ the cage in the box, side and front
def cage_views():
    KZ = 3.2
    w_in, h_in, d_in = S.val("box_in")
    gap = 120
    W = M * 2 + (d_in + 40) * KZ + gap + (w_in + 40) * KZ + 40
    H = M * 2 + (h_in + 30) * KZ + 150
    g = Svg(W, H)
    ox1, ox2 = M + 20 * KZ, M + (d_in + 40) * KZ + gap + 20 * KZ

    def Z(z):
        return H - M - 110 - z * KZ

    def side(y):
        return ox1 + y * KZ

    def front(x):
        return ox2 + x * KZ
    for o, span, title in ((side, d_in, "SIDE (section): back wall and pole left, lid right"),
                           (front, w_in, "FRONT (lid open): left wall left")):
        g.rect(o(0), Z(h_in), o(span), Z(0), "#f4f6f8", "#555", 1.2, dash="6 3")
        g.text(o(0), Z(h_in) - 10, title, 13, weight="bold")
    g.add(f'<line x1="{side(0) - 18:.1f}" y1="{Z(-5):.1f}" x2="{side(0) - 18:.1f}" y2="{Z(h_in + 5):.1f}" stroke="#777" '
          f'stroke-width="12"/>')
    g.text(side(0) - 30, Z(h_in / 2), "pole", 12, "middle", rot=-90)
    # backplane first (behind the cards in the front view)
    bz0, bz1 = st.BP_Z0 - 2 * st.P, st.BP_Z0 + (st.BP_HOLES + 1) * st.P
    g.rect(front(st.strip_x(0) - 1.27), Z(bz1), front(st.strip_x(20) + 1.27), Z(bz0), "#d9c08a", "#7a5c12", 0.8, 0.35)
    # cage parts (the side view leaves out the left wall and the bar, which would hide the cards)
    for name, b in cage.fixed_boxes():
        if name not in ("left wall", "retention bar"):
            g.rect(side(b.y0), Z(b.z1), side(b.y1), Z(b.z0), "#9fb7d9", "#2b4a77", 0.6, 0.6)
        if name != "back plate":
            g.rect(front(b.x0), Z(b.z1), front(b.x1), Z(b.z0), "#9fb7d9", "#2b4a77", 0.6, 0.5)
    g.rect(front(0), Z(st.BP_Z0 + 120), front(cage.W), Z(0), "none", "#2b4a77", 0.4, dash="2 4")
    for c in cage.contents():
        for o, a0, a1 in ((side, c.y0, c.y1), (front, c.x0, c.x1)):
            g.rect(o(a0), Z(c.z1), o(a1), Z(c.z0), "#fdf2e9", "#C0392B", 1.0, 0.9)
        g.text(front((c.x0 + c.x1) / 2), Z((c.z0 + c.z1) / 2) + 4, c.what, 10, "middle")
    g.rect(side(st.BP_BACK), Z(bz1), side(st.BP_FRONT), Z(bz0), "#d9c08a", "#7a5c12", 1)
    mx = st.MUX_BOX
    g.rect(side(S.val("cage_plate") + 1), Z(mx[3]), side(st.BP_BACK), Z(mx[1]), "#161616", "#000", 0.5, 0.6)
    # cards and their parts
    for b in st.ORDER:
        slab = lc.card_slab(b)
        for _r, x in lc.board_boxes(b):
            bx_ = lc.to_box(b, x)
            if bx_.service:
                continue
            col = "#999" if bx_.keepout else st.KIND[next(pl["fp"] for bb, pl in st.placements() if pl["ref"] == _r)][0]
            dash = "3 3" if bx_.keepout else None
            g.rect(side(bx_.y0), Z(bx_.z1), side(bx_.y1), Z(bx_.z0), "none" if dash else col, col, 0.5, 0.3, dash)
            g.rect(front(bx_.x0), Z(bx_.z1), front(bx_.x1), Z(bx_.z0), "none" if dash else col, col, 0.5, 0.3, dash)
        g.rect(side(slab.y0), Z(slab.z1), side(slab.y1), Z(slab.z0), "#B3202A", "#5a0e12", 1)
        g.rect(front(slab.x0), Z(slab.z1), front(slab.x1), Z(slab.z0), "#B3202A", "#5a0e12", 1)
        g.text(side(d_in) + 8, Z(slab.z0) + 4, f"{b} {st.ROLE[b]} (Zb {slab.z1:.1f})", 11, weight="bold")
    # glands, SMA bulkhead
    gd = S.val("gland")[0]
    for i in range(4):
        for j, y in enumerate((20.0, 48.0)):
            x = 30 + i * 25
            g.rect(front(x - gd / 2), Z(2), front(x + gd / 2), Z(-3), "#555", "#222", 0.5)
    g.text(front(w_in / 2), Z(-3) + 18, "8 x PG-7 glands in the bottom wall (2 rows of 4); cables rise in the right zone",
           11, "middle")
    sz = st.card_z("B3") + 12
    g.rect(front(w_in - 1), Z(sz + 4), front(w_in + 8), Z(sz - 4), "#D4AF37", "#7a5c12", 1)
    g.text(front(w_in + 10), Z(sz) + 4, "SMA bulkhead", 10)
    g.text(M, 28, "TX card cage r2 in the #905 box (hanging, long side up), to scale 3.2 px/mm; box inside "
           f"{w_in:g} x {h_in:g} x {d_in:g} mm [TBD-MEASURE]", 15, weight="bold")
    g.text(M, 48, "Blue: printed cage. Red slabs: cards. Tan: backplane. Dashed: plug keep-outs. Pack and charger below "
           "the cards; the charger outline is a placeholder until measured.", 12)
    g.write(OUT_SVG / "cage-side.svg", "TX card cage side and front")


# ------------------------------------------------------------------ build sheets
ORIENT = {"DSTAND": "standing: body on the first hole, the other lead looped over",
          "RLY": "lying flat, leads bent at the body",
          "PTC": "standing, leads formed out to the span", "CAP": "standing disc"}


def part_line(pl):
    part = next(p for p in model.PARTS if p["ref"] == pl["ref"])
    pins = st.pins_of(pl)
    o = ORIENT.get(pl["fp"], "")
    if pl["fp"] == "DSTAND":
        names = {x[0]: x[1] for x in part["pins"]}
        band = next((n for n, v in names.items() if v == "cathode"), "2")
        o += f"; cathode band toward {lc.hole_at(pins[band])}"
    return part, o


def build_list(b, ph):
    rep = REP
    L = [f"# {b} {st.ROLE[b]}: build sheet", "",
         f"Generated by `layout/drawings.py` from `layout/stack.py`; drawing `drawings/{b}-top.svg`. Holes: column letter "
         "+ row number (`e5`); rails `F+` (outer front: 3.3 V supply) and `F-` (inner front: ground), `B+`/`B-` at the back "
         "stay bare. The front edge (column a) faces the lid; the back edge plugs into the backplane. Every strip carries "
         "one line (checked by `layout/layout_checks.py`). Lengths are cut lengths (route + 10 mm), insulated 26 AWG "
         "unless the row says otherwise.", ""]
    ws = [x for x in st.WIRES if b in (board_of_end(x[1]), board_of_end(x[2]))]
    under = [x for x in ws if x[3] == "bottom" and board_of_end(x[1]) == board_of_end(x[2]) == b]
    step = 1
    if under:
        L += [f"## {step}. Underside wires first (parts cover these holes later)", "",
              "| # | From | To | Length | Line | What |", "|---|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(under, 1):
            L.append(f"| {i} | {where(a)} | {where(c)} | {length(a, c)} mm | {plain(net_of_end(a, ph))} | {note} |")
        L.append("")
        step += 1
    top = [x for x in ws if x[3] == "top" and board_of_end(x[1]) == board_of_end(x[2]) == b and x[0] == "jumper"]
    if top:
        L += [f"## {step}. Bare jumpers on top", "", "| # | From | To | Line | What |", "|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(top, 1):
            L.append(f"| {i} | {where(a)} | {where(c)} | {plain(net_of_end(a, ph))} | {note} |")
        L.append("")
        step += 1
    pls = [pl for bb, pl in st.placements() if bb == b]
    pls.sort(key=lambda pl: (max((x.z1 for x in st.boxes_of(pl) if not x.keepout), default=0), pl["ref"]))
    L += [f"## {step}. Parts, lowest first", ""]
    for pl in pls:
        part, o = part_line(pl)
        hmax = max((x.z1 for x in st.boxes_of(pl) if not x.keepout), default=0)
        L.append(f"**{pl['ref']}** {part['value']} ({part['part']}): {pl['note']}"
                 + (f"; {o}" if o else "") + f"; top {hmax:.1f} mm above the card")
        L.append("")
        rows = []
        for pin, xy in st.pins_of(pl).items():
            rows.append(f"| {lc.PIN[(pl['ref'], pin)][1]} ({pin}) | {lc.hole_at(xy)} | {plain(lc.NET_OF.get((pl['ref'], pin)))} |")
        for pad in st.pads_of(pl):
            rows.append(f"| {lc.PIN[(pl['ref'], pad)][1]} ({pad}) | pad: soldered lead | {plain(lc.eff_net((pl['ref'], pad)))} |")
        if rows:
            L += ["| Pin | Hole | Line |", "|---|---|---|"] + rows
        if pl["ref"] == "U2":
            L.append("| VBUS, VIN-, VIN+ (header pins 5-7) | pulled out of the header before fitting | battery nodes stay off the card |")
        L.append("")
    step += 1
    leads = [x for x in ws if x[0] == "lead" or board_of_end(x[1]) != board_of_end(x[2])]
    if leads:
        L += [f"## {step}. Leads (flying leads from the jacks, and leads off the card)", "",
              "| # | From | To | Length | Line | What |", "|---|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(leads, 1):
            pa, pc = end_xy(a), end_xy(c)
            ln = f"{int(math.ceil((math.dist(pa, pc) + 25) / 5) * 5)} mm" if pa and pc else "see ASSEMBLY.md"
            L.append(f"| {i} | {where(a)} | {where(c)} | {ln} | {plain(net_of_end(a, ph) or net_of_end(c, ph))} | {note} |")
        L.append("")
        step += 1
    L += [f"## {step}. Strip map (what every used strip carries)", "", "| Strip | Line | Holes used |", "|---|---|---|"]
    use = defaultdict(list)
    for (bb, h), (ref, pin) in ph.items():
        if bb == b:
            use[st.strip_of(h)].append(f"{h} {ref}")
    for kind, a, c, side, note in st.WIRES:
        for e in (a, c):
            if isinstance(e, str) and e.startswith(b + ":"):
                use[st.strip_of(e.split(":")[1])].append(f"{e.split(':')[1]} {kind}")

    def skey(s):
        return (0, int(s[1:]), s[0]) if s[0] in "LR" else (1, 0, s)
    for s_ in sorted(use, key=skey):
        name = (f"row {s_[1:]} {'a-e' if s_[0] == 'L' else 'f-j'}" if s_[0] in "LR" else f"rail {s_}")
        L.append(f"| {name} | {plain(rep[b].get(s_)) if rep[b].get(s_) else 'nothing (an unused pin)'} | "
                 f"{', '.join(sorted(use[s_]))} |")
    L += ["", "## Before power", "",
          "- Meter each strip in the map to its neighbours: no continuity between neighbouring strips.",
          "- No continuity between the 3.3 V supply and ground (both front rails).",
          f"- Header pin n (column j, row n) to backplane line n: check against `build/BACKPLANE.md`."]
    if b == "B4":
        L.append("- No continuity from any battery lead (lug, shunt pads) to any strip.")
    (OUT_MD / f"{b}.md").write_text("\n".join(L) + "\n")


def backplane_sheet(ph):
    L = ["# Backplane: build sheet", "",
         "Generated by `layout/drawings.py`; drawing `drawings/backplane.svg`. A BusBoard ST2 stripboard "
         "(100 x 80 mm, 31 strips x 39 holes, strips along the 100 mm side) cut to 21 strips x 39 holes. Strips run up "
         "and down in the box; strip n carries bus line n for every card. Component side faces the cards (front); "
         "copper faces the back wall.", "",
         "## 1. Cut and drill", "",
         "1. Cut 21 strips wide (strips 0-20). Keep all 39 holes along the strips.",
         "2. Drill 3.2 mm at strips 0 and 20, about 4 mm in from each end, for the four M3 screws to the cage posts.",
         "3. Do not cut any strip: every bus line runs the full length.", "",
         "## 2. Strips", "", "| Strip | Line |", "|---|---|"]
    for i in range(0, st.BP_STRIPS + 1):
        net = REP["BP"].get(f"s{i}")
        L.append(f"| {i} | {plain(net) if net else 'spare (screws on 0 and 20)'} |")
    L += ["", "## 3. Sockets (one per card; pin n in strip n)", "", "| Socket | Card | Hole along the strips |", "|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if ref.startswith("XB"):
            L.append(f"| {ref} Sullins PPPC181LFBN-RC | {note} | {next(iter(pins.values())).split('.')[1]} |")
    L += ["", "Fit each socket square to the board (a card pin bent sideways will not enter); solder one end pin, check, "
          "then the rest.", "", "## 4. Pins on the front (QT leads to the mux, the charger's I2C)", "",
          "| Part | Pin | Strip, hole | Line |", "|---|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if not ref.startswith("XB"):
            for pin, h in pins.items():
                i, n = h[1:].split(".")
                L.append(f"| {ref} ({note}) | {lc.PIN[(ref, pin)][1]} | {i}, {n} | {plain(lc.NET_OF.get((ref, pin)))} |")
    L += ["", "Each QT lead's V+ pin (red) is folded back along its lead and sleeved: the mux channel V+ is not the "
          "3.3 V supply.", "", "## 5. Copper side", "", "| From | To | Length | Line | What |", "|---|---|---|---|---|"]
    for kind, a, c, side, note in st.WIRES:
        if side == "copper":
            L.append(f"| {where(a)} | {where(c)} | 40 mm | {plain(net_of_end(c, ph) or net_of_end(a, ph))} | {note} |")
    L += ["", "The mux (Adafruit #5626: bridge A0 for 0x71, its Vlogic switch SW1 to V+) sits on a foam pad on the "
          "copper side over holes 2-9, below the B4 socket; its five header pads take short leads to strip hole 10.",
          "", "## Before power", "", "- Each strip to its neighbours: open. Strip 2 to strip 12: closed (both ground).",
          "- 3.3 V supply (strip 1) to ground (strip 2): open."]
    (OUT_MD / "BACKPLANE.md").write_text("\n".join(L) + "\n")


def assembly_sheet():
    order = ", ".join(f"{b} {st.ROLE[b]}" for b in st.ORDER) + " (top)"
    L = ["# Assembly: charger set-up, cage, cards, cables", "",
         "Generated by `layout/drawings.py`. Read with `drawings/cage-side.svg`, `build/B1..B4.md` and "
         "`build/BACKPLANE.md`.", "",
         "## 1. Charger (BQ25798EVM) before any power: jumper changes (TI SLUUCB5; issue #34)", "",
         "The EVM ships set for two cells. Do these in order, with nothing connected:", "",
         "1. **JP24 off, JP22 on** (PROG: one cell, 1.5 MHz). JP22 is the only PROG jumper fitted.",
         "2. **Battery sense wire first, then JP9 off.** Solder the charger battery sense lead (from R7 at the lug) "
         "to J5 SNS_BATP; only then remove JP9, so BATP is never left floating.",
         "3. **JP18 off, thermistor on J7.** Fit the Adafruit #372 10 kohm NTC (B 3950) to J7 and tape it to the pack. "
         "The EVM's TS divider is set for a 103AT (B 3435): the cold and hot thresholds move by a few degrees; "
         "read the TS percentage over I2C at room temperature and confirm it sits in the normal band before charging.",
         "4. **JP12, JP17 and JP30 stay in.** JP30 keeps the I2C pull-ups (R39-R42, 10 kohm) on the EVM's 3.3 V "
         "pull-up rail: they are counted in the bus total (1.40 kohm, schematic check 3).",
         "5. Status LEDs: leave them, or remove their jumpers if fitted (about 1 mA); identify them on the board "
         "against SLUUCB5 before cutting anything.",
         "6. USB in is J6, micro-B (JP7 on VIN1): use a USB-C to micro-B cable from the 2 A adapter.",
         "7. **First power without the pack and with JP17 out** (charge disabled); over I2C read REG0x0A "
         "(cell count) and REG0x01-0x02 (charge voltage 4.2 V), and set the charge current (ICHG) to about 0.9 A "
         "(electrical review m6: the JP22 note says 2 A, the datasheet default is 1 A). Then refit JP17 and connect "
         "the pack.", "",
         "## 2. Print and fit the cage (`cage/cage.py`)", "",
         "1. Measure the box first (the list in the README); set `box_in`, `boss`, `evm` and `slot_clear` in "
         "`sources.py`, then rerun `run.sh`.",
         "2. Print a test slot first and tune `slot_clear` until a card slides with light friction.",
         "3. Screw the back plate to the four corner bosses; screw the backplane to its four posts, copper side back.",
         "4. Drill the bottom wall for eight PG-7 glands (two rows of four), the right wall near the top for the SMA "
         "bulkhead.", "",
         f"## 3. Cards, bottom to top: {order}", "",
         "Each card slides in from the lid side along its left-wall slot and right-post slot until its header pins "
         f"enter the socket ({S.val('insertion'):g} mm). Fit the retention bar (front left, two M3 screws) last. To take "
         "a card out: bar off, unplug that card's cables (jacks, battery leads on B4, the coax on B3), slide it out.",
         "", "## 4. Leads off the cards", "", "| From | To | Length | What |", "|---|---|---|---|"]
    for kind, a, c, side, note in st.WIRES:
        off = [e for e in (a, c) if isinstance(e, tuple) and board_of_end(e) is None and e[0] != "U4"]
        if off:
            ln = "its own lead, at the lug" if "E1" in (a[0], c[0] if isinstance(c, tuple) else "") and \
                any(x[0] in ("R7", "R8") for x in (a, c) if isinstance(x, tuple)) else "150 mm, trim to fit"
            L.append(f"| {where(a)} | {where(c)} | {ln} | {note} |")
    L += ["| EVM J8 (KK 4-pin housing, pins 1-3) | backplane charger pins | 150 mm | charger I2C: ground, clock, data |",
          "| mux channel 0-3 (QT) | backplane QT lead pins | 150 mm (Adafruit #4209) | sensor ports S1-S4 |", "",
          "Battery leads: 22 AWG, soldered or screwed at both ends; nothing of the battery loop goes through a strip, "
          "a header or a socket (layout check L4). Leave 60-80 mm service loops on the jack cables and the solar lead "
          "inside the box, with a drip loop below each gland outside.", "",
          "## 5. Before the first power", "",
          "- Charger jumpers as in step 1; the pack disconnected; JP17 out.",
          "- Each card's own 'Before power' list, and the backplane's.",
          "- 3.3 V supply to ground on the backplane: open (more than 1 kohm)."]
    (OUT_MD / "ASSEMBLY.md").write_text("\n".join(L) + "\n")


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def svg_png(svg, png, scale=2):
    """SVG -> PNG with headless Chrome at the drawing's own size (x scale). Returns True on success."""
    import re
    import shutil
    import tempfile
    text = svg.read_text()
    m = re.search(r'width="([\d.]+)" height="([\d.]+)"', text)
    w, h = int(float(m.group(1))), int(float(m.group(2)))
    exe = CHROME if Path(CHROME).exists() else (shutil.which("google-chrome") or shutil.which("chromium"))
    if not exe:
        print("svg->png: no Chrome/Chromium found")
        return False
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={d}/prof",
                            f"--window-size={w},{h}", f"--force-device-scale-factor={scale}",
                            f"--screenshot={png.resolve()}", svg.resolve().as_uri()],
                           capture_output=True, text=True, timeout=120)
    if r.returncode or not png.exists():
        print(f"svg->png failed for {svg.name}: {r.stderr[-300:]}")
        return False
    return True


REP = {}
lc_ph = {}


def main():
    OUT_SVG.mkdir(exist_ok=True)
    OUT_MD.mkdir(exist_ok=True)
    lc.FAILS.clear()
    ph = lc.run()
    if lc.FAILS:
        sys.exit("layout checks fail; fix them first:\n" + "\n".join(lc.FAILS))
    REP.update(lc.strip_report(ph))
    lc_ph.update(ph)
    for old in ("stack-elevation.svg",):
        (OUT_SVG / old).unlink(missing_ok=True)
    for b in st.BOARDS:
        top_view(b, ph)
        build_list(b, ph)
    backplane_view(ph)
    backplane_sheet(ph)
    cage_views()
    assembly_sheet()
    print("wrote drawings/B1..B4-top.svg, backplane.svg, cage-side.svg; build/B1..B4.md, BACKPLANE.md, ASSEMBLY.md")
    if "--png" in sys.argv:
        PNG = ROOT / "renders"
        PNG.mkdir(exist_ok=True)
        (PNG / "stack-elevation.png").unlink(missing_ok=True)
        bad = [svg.name for svg in sorted(OUT_SVG.glob("*.svg")) if not svg_png(svg, PNG / (svg.stem + ".png"))]
        if bad:
            sys.exit("svg->png failed: " + ", ".join(bad))
        print("wrote renders/*.png for every drawings/*.svg")


if __name__ == "__main__":
    main()
