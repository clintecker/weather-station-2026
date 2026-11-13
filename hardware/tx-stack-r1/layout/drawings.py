"""Drawings and build sheets from layout/stack.py and cage/cage.py.

  drawings/B1..B4-top.svg   each card from above, to scale: strips tinted by net, parts, the routed wires
  drawings/backplane.svg    the PAD3U padboard backplane from the front (component side), the bus wires behind
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
import route
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


def insul(net):
    """Insulation colour for a wire or lead on `net` (the scheme in each build sheet's heading)."""
    if not net:
        return "-"
    if net in ("CELL_P", "BAT_P", "SYS", "PACK_P"):
        return "red, black band"
    if net in ("GAUGE_S", "BATP_S"):
        return "white, red band"
    if net in ("GND", "BAT_N", "PACK_N") or net.endswith("GND"):
        return "black"
    if net == "+3V3" or net.endswith("3V3"):
        return "red"
    if "SCL" in net:
        return "yellow"
    if "SDA" in net:
        return "blue"
    return "green"


COLOURS = ("Insulation colours: 3.3 V red; ground black; I2C clock (SCL) yellow; I2C data (SDA) blue; the battery "
           "and charger lines (battery + junction, charger battery +, SYS) red with a black heat-shrink band at each "
           "end; the battery sense leads white with a red band; every other signal green. Bare jumpers are bare.")


def plain(net):
    return NAME.get(net, "not connected") if net else "not connected"


def esc(s):
    return html.escape(str(s), quote=True)


def sx(x):
    return M + x * K


def sy(y):
    return M + 120 + (st.CD - y) * K          # room above the snapped edge for the overhanging back jacks


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
        return f"backplane line {h[1:].split('.')[0]} hole {h.split('.')[1]}" if b == "BP" else h
    part = next(p for p in model.PARTS if p["ref"] == e[0])
    pin = next(x for x in part["pins"] if x[0] == e[1])
    return f"{e[0]} {pin[1]}"


def length(i):
    """Cut length for wire i, mm: its routed path (layout/route.py) plus 10 mm for the stripped ends, rounded up to 5."""
    return route.cut_length(i)


def bends(i):
    r = route.ROUTES[i]
    g = r["grid"] if r and r.get("grid") else []
    return sum(1 for a, b, c in zip(g, g[1:], g[2:]) if (a[0] == b[0]) != (b[0] == c[0]))


# ------------------------------------------------------------------ one card from above
def top_view(b, ph):
    rep = REP
    W, H = sx(st.BW) + 360 + 40 * K, sy(0) + 140
    g = Svg(W, H)
    g.rect(sx(0), sy(st.CD), sx(st.BW), sy(0), "#B3202A", "#5a0e12", 1.5)
    r = S.val("sb_mhole") / 2 * K
    for x, y in st.MHOLES:
        if y > st.CD:
            continue
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
        g.text(x, sy(st.CD) - 6, row, 10, "middle")
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
    # conductors, along their routed paths
    for i, (kind, a, c, side, note) in enumerate(st.WIRES):
        ba, bc = board_of_end(a), board_of_end(c)
        if b not in (ba, bc) or side == "copper":
            continue
        r = route.ROUTES[i]
        net = net_of_end(a, lc_ph) or net_of_end(c, lc_ph)
        col = ncol(net)
        dash = ' stroke-dasharray="5 3"' if side == "bottom" else ""
        if r and r["ok"] and not r.get("bundled"):
            pts = " ".join(f"{sx(p[0]):.1f},{sy(p[1]):.1f}" for p in r["pts"])
            g.add(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="{2.4 if kind == "jumper" else 2.0}" '
                  f'stroke-linejoin="round" stroke-linecap="round"{dash} opacity="0.9"/>')
            if ba != bc or None in (ba, bc):
                p = r["pts"][-1] if (bc != b) else r["pts"][0]
                if abs(p[1]) < 0.01:
                    g.add(f'<circle cx="{sx(p[0]):.1f}" cy="{sy(p[1]):.1f}" r="5" fill="none" stroke="{col}" stroke-width="2.2"/>')
    # edges
    g.text(sx(st.BW / 2), sy(0) + 40, "FRONT EDGE (lid side): the card slides in from here", 14, "middle", weight="bold")
    g.text(sx(st.BW / 2), sy(st.TONGUE_Y1 + 6) - 10, "BACK EDGE (snapped, filed flat): header (row J, columns 1-18) plugs into the "
           "backplane", 13, "middle",
           weight="bold")
    g.text(sx(st.BW) + 14, sy(st.CD / 2), "RIGHT EDGE: jack mouths", 12, "start", weight="bold", rot=90)
    g.text(M, 24, f"{b} {st.ROLE[b]}: from above, {K:g} px/mm; SolderFul 81.3 x 50.8 mm with the back rails snapped off: "
           f"{st.BW:g} x {st.CD:.2f} mm [TBD-MEASURE]", 16, weight="bold")
    # legend
    lx, ly = sx(st.BW) + 40 + 25 * K, sy(st.CD) - 10
    g.text(lx, ly, "Lines on this card", 13, weight="bold")
    nets = sorted({n for n in rep[b].values() if n and "/" not in n}, key=lambda n: plain(n))
    for i, n in enumerate(nets):
        y = ly + 18 + i * 16
        g.add(f'<rect x="{lx}" y="{y - 10}" width="22" height="11" fill="{ncol(n)}" fill-opacity="0.7"/>')
        g.text(lx + 30, y, plain(n), 10.5)
    y = ly + 30 + len(nets) * 16
    for s_, d in (("solid line", "jumper, wire or lead on top, as routed"), ("dashed line", "wire on the underside, as routed"),
                  ("ring on the front edge", "lead leaving the card (to the charger, the pack)"), ("square", "pin in a hole"),
                  ("diamond", "pad with a soldered lead"), ("grey dashed box", "plug or service keep-out")):
        g.text(lx, y, f"{s_}: {d}", 10)
        y += 15
    g.write(OUT_SVG / f"{b}-top.svg", f"{b} {st.ROLE[b]} from above")


# ------------------------------------------------------------------ the backplane
def backplane_view(ph):
    KB = 7.0
    n_strips = st.BP_STRIPS + 1
    W = M * 2 + (n_strips + 1) * st.P * KB + 900
    H = M * 2 + (st.BP_HOLES + 2) * st.P * KB + 40

    def bx(i):
        return M + (i + 1.5) * st.P * KB          # line -1 (the tab) is the first column

    def bz(n):
        return H - M - (n + 0.5) * st.P * KB
    g = Svg(W, H)
    g.rect(bx(0) - st.P * KB / 2, bz(st.BP_HOLES + 0.5), bx(st.BP_STRIPS) + st.P * KB / 2, bz(0.5), "#B3202A", "#5a0e12", 1.2)
    g.rect(bx(-1) - st.P * KB / 2, bz(st.BP_TAB_HOLES + 0.5), bx(0) - st.P * KB / 2 + 2, bz(0.5), "#B3202A", "#5a0e12", 1.2)
    for n in range(1, st.BP_TAB_HOLES + 1):
        g.add(f'<rect x="{bx(-1) - 0.8 * KB:.1f}" y="{bz(n) - 0.8 * KB:.1f}" width="{1.6 * KB:.1f}" height="{1.6 * KB:.1f}" '
              f'rx="2" fill="#D4AF37" stroke="#7a5c12" stroke-width="0.5"/>')
        g.add(f'<circle cx="{bx(-1):.1f}" cy="{bz(n):.1f}" r="{0.47 * KB:.1f}" fill="#2b2b2b"/>')
    g.text(bx(-1), bz(st.BP_TAB_HOLES + 1.2), "-1 (tab)", 10, "middle")
    bus = dict(st.BP_BUS)
    for i in range(n_strips):
        g.text(bx(i), bz(st.BP_HOLES + 1.2), i, 10, "middle")
        for n in range(1, st.BP_HOLES + 1):
            g.add(f'<rect x="{bx(i) - 0.8 * KB:.1f}" y="{bz(n) - 0.8 * KB:.1f}" width="{1.6 * KB:.1f}" height="{1.6 * KB:.1f}" '
                  f'rx="2" fill="#D4AF37" stroke="#7a5c12" stroke-width="0.5"/>')
            g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="{0.47 * KB:.1f}" fill="#2b2b2b"/>')
        hs = bus.get(i)
        if hs:
            net = REP["BP"].get(f"s{i}")
            g.add(f'<line x1="{bx(i):.1f}" y1="{bz(hs[0]):.1f}" x2="{bx(i):.1f}" y2="{bz(hs[-1]):.1f}" stroke="{ncol(net)}" '
                  f'stroke-width="{0.64 * KB:.1f}" stroke-linecap="round" opacity="0.75"/>')
            for n in hs:
                g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="{0.9 * KB:.1f}" fill="none" stroke="{ncol(net)}" stroke-width="1.6"/>')
    for h in st.BP_SCREWS:
        i, n = (int(v) for v in h[1:].split("."))
        g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="{1.6 * KB:.1f}" fill="#fff" stroke="#000" stroke-width="1.2"/>')
    for n in range(1, st.BP_HOLES + 1, 2):
        g.text(bx(-1) - 2.5 * KB, bz(n) + 4, n, 9, "end")
    mx = st.MUX_BOX
    g.rect(bx(0) + (mx[0] - st.strip_x(0)) * KB, bz((mx[3] - st.BP_Z0) / st.P + 1),
           bx(0) + (mx[2] - st.strip_x(0)) * KB, bz((mx[1] - st.BP_Z0) / st.P + 1),
           "none", "#161616", 1.6, dash="8 4")
    g.text(bx(0) + (mx[0] + mx[2] - 2 * st.strip_x(0)) / 2 * KB, bz((mx[1] + mx[3] - 2 * st.BP_Z0) / 2 / st.P + 1),
           "PCA9548 mux (behind, on foam)", 12, "middle", weight="bold")
    for ref, pins, note in st.BP_PARTS:
        for pin, h in pins.items():
            i, n = (int(v) for v in h[1:].split("."))
            net = lc.NET_OF.get((ref, pin))
            g.add(f'<rect x="{bx(i) - 4:.1f}" y="{bz(n) - 4:.1f}" width="8" height="8" fill="{ncol(net)}" stroke="#000"/>')
        if ref.startswith("XB"):
            n = int(next(iter(pins.values())).split(".")[1])
            ln = model.HDR_LEN[next(b for b in st.BOARDS if model.SOCKETS[b] == ref)]
            g.rect(bx(1) - 1.27 * KB, bz(n) - 1.27 * KB, bx(ln) + 1.27 * KB, bz(n) + 1.27 * KB, "none", "#000", 1.4)
            g.text(bx(st.BP_STRIPS) + 2 * KB, bz(n) + 4, f"{ref}: {note}", 11, weight="bold")
        elif ref.startswith("W") or ref == "XJ1" or ref in ("R7", "R8"):
            if ref in ("R7", "R8"):
                (i1, n1), (i2, n2) = [tuple(int(v) for v in h[1:].split(".")) for h in pins.values()]
                g.add(f'<line x1="{bx(i1):.1f}" y1="{bz(n1):.1f}" x2="{bx(i2):.1f}" y2="{bz(n2):.1f}" stroke="#C9B48A" '
                      f'stroke-width="{2.5 * KB:.1f}" opacity="0.8"/>')
                g.text((bx(i1) + bx(i2)) / 2, (bz(n1) + bz(n2)) / 2 + 4, ref, 11, "middle", weight="bold")
            n = int(next(iter(pins.values())).split(".")[1])
            g.text(bx(st.BP_STRIPS) + 2 * KB, bz(n) + 4 + (12 if ref == "R8" else 0), f"{ref}: {note}", 10)
    for kind, a, c, side, note in st.WIRES:
        for e, o in ((a, c), (c, a)):
            if isinstance(e, str) and e.startswith("BP:"):
                i, n = (int(v) for v in e[4:].split("."))
                g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="6" fill="none" stroke="#8E44AD" stroke-width="2"/>')
    lx = bx(st.BP_STRIPS) + 2 * KB + 380
    g.text(M, 26, f"Backplane: BusBoard PAD3U padboard cut {n_strips} x {st.BP_HOLES} holes, seen from the front "
           "(component side); a pad per hole, no strips: the bus wires on the copper side join them", 15, weight="bold")
    y = M + 10
    g.text(lx, y, "Line: what its bus wire carries", 13, weight="bold")
    for i in range(n_strips):
        y += 15
        g.text(lx, y, f"{i}: {plain(REP['BP'].get(f's{i}')) if REP['BP'].get(f's{i}') else 'spare (no wire)' if 0 < i < 20 else 'screws, no wire'}", 10.5)
    y += 25
    for s_ in ("black outline: card socket (generic female strip, cut: 1x18, B4 1x26)", "small square: a pin in a hole",
               "coloured line: bare bus wire on the copper side, ringed where soldered",
               "purple ring: a lead soldered on the copper side", "white circle: 3.2 mm screw hole",
               "dashed: the mux, behind on foam"):
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
    for c in cage.contents():
        for o, a0, a1 in ((side, c.y0, c.y1), (front, c.x0, c.x1)):
            g.rect(o(a0), Z(c.z1), o(a1), Z(c.z0), "#fdf2e9", "#C0392B", 1.0, 0.9)
        if "J8" not in c.what and "underside" not in c.what:
            g.text(front((c.x0 + c.x1) / 2), Z((c.z0 + c.z1) / 2) + 4, c.what, 10, "middle")
    g.rect(side(st.BP_BACK), Z(bz1), side(st.BP_FRONT), Z(bz0), "#d9c08a", "#7a5c12", 1)
    mx = st.MUX_BOX
    g.rect(side(cage.mux_box().y0), Z(mx[3]), side(st.BP_BACK), Z(mx[1]), "#161616", "#000", 0.5, 0.6)
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
    for x, y, k in cage.GLANDS:
        gd = cage.GLAND_NUT[k]
        g.rect(front(x - gd / 2), Z(0), front(x + gd / 2), Z(-8), "#555", "#222", 0.5)
        g.rect(side(y - gd / 2), Z(0), side(y + gd / 2), Z(-8), "#555", "#222", 0.5, 0.7)
    g.text(front(w_in / 2), Z(-8) + 16, "glands in the bottom wall (2 x 4): 6 PG-7, 2 PG-9 (right column)", 10, "middle")
    for b_ in cage.shell():
        if "lug" in b_.what or "drip" in b_.what:
            g.rect(side(b_.y0), Z(b_.z1), side(b_.y1), Z(b_.z0), "#bbbbbb", "#555", 0.6, 0.8)
    g.add(f'<line x1="{side(cage.SEAM):.1f}" y1="{Z(h_in):.1f}" x2="{side(cage.SEAM):.1f}" y2="{Z(0):.1f}" '
          'stroke="#1F5FBF" stroke-width="1.5" stroke-dasharray="8 4"/>')
    g.text(side(cage.SEAM) + 4, Z(h_in) + 14, f"base / lid seam (Yb {cage.SEAM:g}): lid tray beyond", 10, fill="#1F5FBF")
    for k in cage.box_keepouts():
        g.rect(front(k.x0), Z(k.z1), front(k.x1), Z(k.z0), "#cccccc", "#666", 0.6, 0.6)
        if "floor" in k.what:
            g.text(front((k.x0 + k.x1) / 2), Z(k.z0) + 10, k.what.split()[-1], 8, "middle")
    a1 = [lc.to_box("B3", x) for r_, x in lc.board_boxes("B3") if r_ == "A1"]
    arm = next(x for x in a1 if x.what.endswith("forward arm"))
    _pe, yb, sz, _ax = cage.coax(arm)
    g.rect(front(w_in - 1), Z(sz + 4), front(w_in + 8), Z(sz - 4), "#D4AF37", "#7a5c12", 1)
    g.rect(side(yb - 4), Z(sz + 4), side(yb + 4), Z(sz - 4), "#D4AF37", "#7a5c12", 1)
    g.text(front(w_in + 10), Z(sz) + 4, "SMA bulkhead boss", 10)
    g.text(M, 28, "TX stack r3 in the printed PETG base (100 deep) under the #905 lid, hanging long side up, to scale "
           f"3.2 px/mm; inside {w_in:g} x {h_in:g} x {d_in:g} mm (lid interface: L1 and the rim ring's fit [TBD-MEASURE])", 15, weight="bold")
    g.text(M, 48, "Blue: moulded cage features. Red slabs: cards. Tan: backplane. Dashed: plug keep-outs. Grey: corner "
           "posts, gland nuts, pole lugs and drip edge.", 12)
    g.text(M, 64, "Shelves bottom to top: the pack, the BQ25798EVM (90 x 90, J8 toward the lid), B4, B2, B1, B3; all "
           "slide toward the back. Glands in the bottom wall; cables rise in the right column.", 12)
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
         f"Generated by `layout/drawings.py` from `layout/stack.py`; drawing `drawings/{b}-top.svg`. Holes as the SolderFul "
         "silkscreen names them: row letter + column number (`e10` = row E, column 10; letters A-J are rows, numbers "
         "1-30 are columns); rails `F+` (outer front: 3.3 V supply) and `F-` (inner front: ground). The front edge "
         "(row A) faces the lid; the back edge plugs into the backplane. Every strip carries one line (checked by "
         "`layout/layout_checks.py`). Every wire follows its route in `drawings/{b}-top.svg` (`layout/route.py`: flat, "
         "straight runs on the 1.27 mm grid with right-angle bends, around every part). Lengths are cut lengths (route "
         "+ 10 mm), 24 AWG solid insulated unless the table says otherwise (insulation OD about 1.45 mm, `[TBD-MEASURE]`). "
         + COLOURS, "",
         "## 1. Snap off the back rails (before any soldering)", "",
         f"1. Score both faces along the line between row J and the inner back rail (card Y {st.CD:.2f} mm from the "
         "front edge [TBD-MEASURE]: measure on the card), clamp the card along the line and snap the two back rails off.",
         "2. File the edge flat and square to the front edge; stop at the line (do not open the row J holes).",
         f"3. Check: the card is {st.CD:.2f} mm deep everywhere; it slides in a test slot without catching.", ""]
    ws = [(i, x) for i, x in enumerate(st.WIRES) if b in (board_of_end(x[1]), board_of_end(x[2]))]
    under = [(i, x) for i, x in ws if x[3] == "bottom" and board_of_end(x[1]) == board_of_end(x[2]) == b]
    step = 2
    if under:
        L += [f"## {step}. Underside wires first (parts cover these holes later)", "",
              "| # | From | To | Length | Line | Colour | What |", "|---|---|---|---|---|---|---|"]
        for k, (wi, (kind, a, c, side, note)) in enumerate(under, 1):
            n_ = net_of_end(a, ph)
            L.append(f"| {k} | {where(a)} | {where(c)} | {length(wi)} mm, {bends(wi)} bends | {plain(n_)} | {insul(n_)} | {note} |")
        L.append("")
        step += 1
    top = [(i, x) for i, x in ws if x[3] == "top" and board_of_end(x[1]) == board_of_end(x[2]) == b and x[0] == "jumper"]
    if top:
        L += [f"## {step}. Bare jumpers on top", "", "| # | From | To | Length | Line | What |", "|---|---|---|---|---|---|"]
        for k, (wi, (kind, a, c, side, note)) in enumerate(top, 1):
            L.append(f"| {k} | {where(a)} | {where(c)} | {length(wi)} mm | {plain(net_of_end(a, ph))} | {note} |")
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
    leads = [(i, x) for i, x in ws if x[0] == "lead" or board_of_end(x[1]) != board_of_end(x[2])]
    if leads:
        L += [f"## {step}. Leads (flying leads from the jacks, and leads off the card)", "",
              "Each lead climbs off its pad straight across its own breakout to the nearest edge, drops to the card and "
              "follows its route; a lead off the card leaves at the front edge where the drawing rings it.", "",
              "| # | From | To | Length | Line | Colour | What |", "|---|---|---|---|---|---|---|"]
        for k, (wi, (kind, a, c, side, note)) in enumerate(leads, 1):
            r = route.ROUTES[wi]
            on = board_of_end(a) == board_of_end(c) == b
            ln = (f"{length(wi)} mm" if on else f"{length(wi)} mm to the front edge, then see ASSEMBLY.md") \
                if r and r["ok"] else "see ASSEMBLY.md"
            if r and r.get("bundled"):
                ln += " (laid beside the lead before it)"
            n_ = net_of_end(a, ph) or net_of_end(c, ph)
            L.append(f"| {k} | {where(a)} | {where(c)} | {ln} | {plain(n_)} | {insul(n_)} | {note} |")
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
        name = (f"column {s_[1:]}, rows {'A-E' if s_[0] == 'L' else 'F-J'}" if s_[0] in "LR" else f"rail {s_}")
        L.append(f"| {name} | {plain(rep[b].get(s_)) if rep[b].get(s_) else 'nothing (an unused pin)'} | "
                 f"{', '.join(sorted(use[s_]))} |")
    L += ["", "## Before power", "",
          "- Meter each strip in the map to its neighbours: no continuity between neighbouring strips.",
          "- No continuity between the 3.3 V supply and ground (both front rails).",
          f"- Header pin n (row J, column n) to backplane line n: check against `build/BACKPLANE.md`."]
    if b == "B4":
        L.append("- Battery path: header pins 19 and 20 joined, 21 and 22 joined, each pair open to everything else; the "
                 "shunt pads only on their own leads. Pins 24 and 25 pulled.")
    (OUT_MD / f"{b}.md").write_text("\n".join(L) + "\n")


def backplane_sheet(ph):
    n_lines = st.BP_STRIPS + 1
    bus = dict(st.BP_BUS)
    L = ["# Backplane: build sheet", "",
         "Generated by `layout/drawings.py`; drawing `drawings/backplane.svg`. A BusBoard PAD3U padboard "
         "(160.02 x 100.08 mm, 38 x 62 holes on 0.1 in, a separate plated pad per hole and no strips) cut to "
         f"{n_lines} x {st.BP_HOLES} holes. Nothing on it connects unless a wire does: on lines 1-18 a bare bus wire "
         "on the copper side, soldered at every used pad, carries bus line n for every card; lines 19-23 and 26 carry "
         "B4's power pins (the battery path, its senses and SYS) down to short leads to the charger and the pack. Lines run up and down in "
         "the box. Component side faces the cards (front); copper faces the back wall.", "",
         "## 1. Cut and drill", "",
         f"1. Cut an L from the bottom-right corner of one PAD3U, seen from the face that becomes the front, so its factory edges are its right and bottom: {n_lines} holes across by {st.BP_HOLES} holes along, plus a tab one hole wide (line -1) beside holes 1-{st.BP_TAB_HOLES} at the bottom left. Score both faces midway between two rows of holes, not through them, and snap the long cuts; cut the inside corner of the L with a hacksaw (down between lines -1 and 0 to the score above hole {st.BP_TAB_HOLES}), then sand every edge flat. The left edge above the tab (line 0) must end 0.5-1.2 mm from the near side of line 0's holes, or it will not fit the left wall's groove; the tab's left edge is midway between line -2 and line -1. Lines -1 (tab) and 0-{st.BP_STRIPS} across; holes 1-{st.BP_HOLES} along. A PAD3U is 38 holes across, so it fits.",
         "2. Drill 3.2 mm through three pads, for the M3 screws to the base's three floor posts: "
         + ", ".join(f"line {h[1:].split('.')[0]} hole {h[1:].split('.')[1]}" for h in st.BP_SCREWS)
         + " (bottom left, bottom right, top right). The tab leaves about 2.2 mm of board left of the line 0 hole. Line 0 has no "
         "screw higher up: its left edge sits in the left wall's groove. Nothing else is soldered on lines -1 and 0; line 20's bus wire (charger battery +) starts at hole 5, clear of the "
         "bottom-right screw and its post.",
         "3. Meter two neighbouring pads anywhere: open (the board has no strips).", "",
         "## 2. Sockets (one per card; pin n on line n)", "", "| Socket | Card | Hole along the lines |", "|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if ref.startswith("XB"):
            ln = model.HDR_LEN[next(b for b in st.BOARDS if model.SOCKETS[b] == ref)]
            L.append(f"| {ref} generic female strip, cut to 1x{ln} | {note} | {next(iter(pins.values())).split('.')[1]} |")
    L += ["", "Fit each socket square to the board (a card pin bent sideways will not enter); solder one end pin, check, "
          "then the rest. B4's is 1x26 (lines 1-26; positions 24 and 25 stay empty: B4's pins there are pulled). Cut each from a longer strip by pulling the contact one past the end and cutting through that empty position (one position lost at each cut); file the cut face flat.", "", "## 3. Pins and parts on the front (QT leads to the mux, the charger's I2C, the sense resistors)", "",
          "| Part | Pin | Line, hole | Bus line |", "|---|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if not ref.startswith("XB"):
            for pin, h in pins.items():
                i, n = h[1:].split(".")
                L.append(f"| {ref} ({note}) | {lc.PIN[(ref, pin)][1]} | {i}, {n} | {plain(lc.NET_OF.get((ref, pin)))} |")
    L += ["", "Each QT lead's V+ pin (red) is folded back along its lead and sleeved: the mux channel V+ is not the "
          "3.3 V supply. R7 and R8 lie flat on the front (R8 on a slant, its legs bent to the span); R7's free leg "
          "(line 24, hole 7) also takes the charger sense lead on the copper side.", "",
          "### Leads to the charger and the pack (copper side, short)", "",
          "| From | To the backplane | What |", "|---|---|---|"]
    for kind, a, c, side, note in st.WIRES:
        if kind == "lead" and isinstance(a, tuple) and a[0] in ("PG1", "U1") and isinstance(c, str) and c.startswith("BP:"):
            i, n = c[4:][1:].split(".")
            L.append(f"| {where(a)} | line {i}, hole {n} | {note} |")
        elif kind == "lead" and isinstance(a, tuple) and a[0] == "R7":
            L.append(f"| {where(c)} | R7's free leg (line 24, hole 7) | {note} |")
    L += ["", "Leave each 60-80 mm with a service loop: the EVM slides out on them.", "",
          "## 4. Bus wires (copper side)", "",
          f"Bare 22 AWG solid copper (the Adafruit 1311 hook-up wire on hand, stripped; {S.val('bus_wire'):g} mm). Lay each one straight along its line over the "
          "pads, tack it at the first and last hole, then solder it at every hole listed (each is already holding a "
          "pin). Cut length: the span plus 10 mm.", "",
          "| Line | Bus line | From hole | To hole | Cut | Soldered at holes |", "|---|---|---|---|---|---|"]
    for i in sorted(set(range(1, 19)) | set(bus)):
        hs = bus.get(i, [])
        net = REP["BP"].get(f"s{i}")
        if not hs:
            L.append(f"| {i} | {plain(net) if net else 'spare'} | - | - | no wire | - |")
            continue
        cut = int(math.ceil(((hs[-1] - hs[0]) * st.P + 10) / 5) * 5)
        L.append(f"| {i} | {plain(net)} | {hs[0]} | {hs[-1]} | {cut} mm | {', '.join(str(n) for n in hs)} |")
    L += ["", "## 5. Leads on the copper side", "", "| From | To | Length | Line | What |", "|---|---|---|---|---|"]
    for kind, a, c, side, note in st.WIRES:
        if side == "copper":
            L.append(f"| {where(a)} | {where(c)} | 40 mm | {plain(net_of_end(c, ph) or net_of_end(a, ph))} | {note} |")
    L += ["", "The mux (Adafruit #5626: bridge A0 for 0x71, its Vlogic switch SW1 to V+) sits on a foam pad on the "
          "copper side over holes 2-9, below the B4 socket and clear of the bus wires (they start at hole 10); its "
          "five header pads take short leads to hole 10.", "",
          "## 6. Fit it in the base (`cage/backplane-mount-spec.md`)", "",
          f"1. Copper side back, mux behind it: lower the board onto the three posts {S.val('bp_groove')[2]:g} mm to the "
          "right of its place (toward the right wall), its copper face down on the post tops; its left edge is then "
          "clear of the left wall.",
          f"2. Slide it {S.val('bp_groove')[2]:g} mm left, flat on the posts, until its left edge is in the left wall's "
          "groove and the rail below it, down to just above the tab (it stops 0.5 short of the groove's floor), the tab "
          "lands on the bottom-left post, and the three drilled holes are over the posts' inserts. The mux moves with it "
          "and clears the bottom-left post's flat and the bottom-right post in both places.",
          "3. Drive the three M3 x 6 button-head screws (ISO 7380, no washers). It comes out the same way, after every "
          "card is out.", "",
          "## 7. Hole by hole", "", "Every pad that has anything soldered in it; every other pad stays bare.", "",
          "| Line | Hole | What is in it | Bus wire |", "|---|---|---|---|"]
    used = defaultdict(list)
    for ref, pins, note in st.BP_PARTS:
        for pin, h in pins.items():
            used[h].append(f"{ref} {lc.PIN[(ref, pin)][1]}")
    for kind, a, c, side, note in st.WIRES:
        for e, o in ((a, c), (c, a)):
            if isinstance(e, str) and e.startswith("BP:"):
                used[e[3:]].append(f"lead to {where(o)}")
    for h in st.BP_SCREWS:
        used[h].append("3.2 mm screw hole (drilled)")
    for h in sorted(used, key=lambda h: tuple(int(v) for v in h[1:].split("."))):
        i, n = (int(v) for v in h[1:].split("."))
        wire = f"line {i}" if n in bus.get(i, []) else "-"
        L.append(f"| {i} | {n} | {'; '.join(used[h])} | {wire} |")
    L += ["", "## Before power", "",
          "- Each bus line to its neighbours: open. Line 2 to line 12: closed (both ground, joined at hole 38).",
          "- 3.3 V supply (line 1) to ground (line 2): open.",
          "- Each bus wire: continuity from its first to its last soldered hole."]
    (OUT_MD / "BACKPLANE.md").write_text("\n".join(L) + "\n")


def assembly_sheet():
    order = ", ".join(f"{b} {st.ROLE[b]}" for b in st.ORDER) + " (top)"
    L = ["# Assembly: charger set-up, the printed base, shelves, cards, cables", "",
         "Generated by `layout/drawings.py`. Read with `drawings/cage-side.svg`, `build/B1..B4.md` and "
         "`build/BACKPLANE.md`.", "",
         "## 1. Charger (BQ25798EVM) before any power: jumper changes (TI SLUUCB5; issue #34)", "",
         "The EVM ships set for two cells. Do these in order, with nothing connected:", "",
         "1. **JP24 off, JP22 on** (PROG: one cell, 1.5 MHz). JP22 is the only PROG jumper fitted.",
         "2. **Battery sense wire first, then JP9 off.** Solder the charger battery sense lead (from R7 on the backplane, its free leg at line 24 hole 7) "
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
         "## 2. Print the base (`cage/cage.py`)", "",
         "1. Print the rim test ring first (`cage.py --ring`, `cage/stl/rim-ring.stl`: the whole rim, 175.5 x 129.5 "
         "x 8, about an hour, flat on its land) and press the real lid onto it: the lip must drop into the O-ring "
         "channel all the way round and through all four S-curves, all four holes under the lid's at once, the outer "
         "edge flush on all four sides. Correct `cage/lid-rim-spec.md` until it does, then set `ring_fit` True. Settle L1 (the screws, the lid's "
         "corner pocket); `cage.py --stl` refuses the full base until both are sourced. Also the EVM's part heights "
         "and J6 under it (`evm`, `evm_under`).",
         "2. Then a second test coupon: one card slot (tune `slot_clear` until a card slides with light friction), one "
         "M4 insert post, one lid corner of the land and tongue (fit the lid on it: the sealing lip must press the O-ring "
         "about 1 mm, with the lid's walls down on the land), and a 30 mm square of the 3 mm wall to leak-test.",
         "3. Print the base in PETG, a light colour, rim down on the plate (the O-ring land is the bed face), walls "
         "3 mm (about 7 perimeters, solid). Set the M4 heat-set inserts in the four corner posts (option b: M4 stainless screws on 12 mm washers through the lid's 8 mm holes) and the M3 inserts in "
         "the backplane posts with the iron. Leak-test the bare base (water in the base, or soapy water with the lid on "
         "and a little pressure through the vent hole); coat the inside only if it leaks. Paint or clear-coat the "
         "outside against UV.",
         "4. Fit the glands in the bottom wall's bosses (six 12.0 mm holes for PG-7s #762, the round port cables; two "
         "15.5 mm for PG-9s #761, the flat wind and rain cables, right column), the M12 vent, and the SMA bulkhead in "
         "the right wall's boss. Fit the backplane (its build sheet, section 6): lowered onto its three posts 2.5 mm "
         "right of its place, slid left into the left wall's groove, three M3 screws (one through the tab); it comes off again only after "
         "every card is out.",
         "5. Shelves bottom to top: the pack on its tray (strap); the EVM (Bumpon feet peeled off) slid back on its "
         "ledges to the stop, clip at the front, leads with service loops; then the cards.",
         "6. Cables: each round port cable through its PG-7, cap tightened. Each flat weather-meter cable through a PG-9 "
         "with its seal out. Seal after the final cable position is set (silicone or a split grommet in the gap); the "
         "cable is then not removable without cutting the seal. Inside, a service loop in the space in front of the "
         "cards; outside, a drip loop below each gland before the cable is tied to the pole.",
         "7. The coax: AD1 on the mini's SMA, its arm toward the lid; the 135110 plug on it, the cable bent right in "
         "front of the cards to the bulkhead; clip it to the right corner post at the bend.",
         "8. Mount: hose clamps or U-bolts through the two pole lugs on the back; the lid on with its four screws.", "",
         f"## 3. Cards, bottom to top: {order}", "",
         "Every card has its back rails snapped off and the edge filed flat first (step 1 of its build sheet). "
         "Each card slides in from the lid side along its left-wall slot and right-post slot until its header pins "
         f"enter the socket ({S.val('insertion'):g} mm; the header insulator meets the socket "
         f"{st.Y_MOUTH - st.Y_INS:.2f} mm further in). On B1 and B2 the back breakout's spacer tongue enters the right "
         "post's slot. Fit the retention bar (front left, two M3 screws) last. To take "
         "a card out: bar off, unplug that card's own plugs (the RJ11 cables on B1 and B2, the coax at AD1 on B3, the "
         "SWD and USB-C leads if fitted), slide it out. No card needs another card out first, and nothing is soldered "
         "between a card and anything else (layout check L10).",
         "", "## 4. Leads off the cards", "", "| From | To | Length | What |", "|---|---|---|---|"]
    for kind, a, c, side, note in st.WIRES:
        off = [e for e in (a, c) if isinstance(e, tuple) and board_of_end(e) is None and e[0] != "U4"]
        if off:
            ln = "100 mm, trim to fit" if any((isinstance(x, str) and x.startswith("BP:")) or x[0] == "R7" for x in (a, c)) \
                else "150 mm, trim to fit"
            L.append(f"| {where(a)} | {where(c)} | {ln} | {note} |")
    L += ["| EVM J8 (KK 4-pin housing, pins 1-3) | backplane charger pins | 150 mm | charger I2C: ground, clock, data |",
          "| mux channel 0-3 (QT) | backplane QT lead pins | 150 mm (Adafruit #4209) | sensor ports S1-S4 |", "",
          f"Battery leads: 24 AWG stranded (red +, black -), soldered at the backplane and screwed at the EVM (about {S.val('wire24')[2] * 0.1:.1f} mV drop per 0.1 m at 1 A, {S.val('wire24')[2]:g} mohm/m); the charger sense lead from R7: 24 AWG stranded. The battery current reaches B4 only on doubled header pins (19-20, 21-22; layout check L4); no lead goes to a card (L10). Leave 60-80 mm service loops on the jack cables and the solar lead "
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
