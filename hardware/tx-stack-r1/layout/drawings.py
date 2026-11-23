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


COLOURS = ("Insulation colours: 3.3 V red, ground black, I2C clock (SCL) yellow, I2C data (SDA) blue. The battery "
           "and charger lines (battery + junction, charger battery +, SYS) are red with a black heat-shrink band at each "
           "end. The battery sense leads are white with a red band. Every other signal is green, and bare jumpers are bare.")


def plain(net):
    return NAME.get(net, "not connected") if net else "not connected"


def esc(s):
    return html.escape(str(s), quote=True)


def sx(x):
    return M + x * K


def sy(y):
    return M + 120 + (st.CD - y) * K          # room above the snapped edge (labels, the header)


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


def lead_len(a, c):
    """Cut length of a lead that leaves the cards and the backplane (to the EVM or the pack): one value for
    ASSEMBLY.md section 4 and BACKPLANE.md section 5, cut long and trimmed to fit with a service loop. None for
    a lead between two points on the cards or the backplane (the mux pads included)."""
    off = [e for e in (a, c) if isinstance(e, tuple) and board_of_end(e) is None and e[0] != "U4"]
    if not off:
        return None
    to_bp = any((isinstance(x, str) and x.startswith("BP:")) or x[0] == "R7" for x in (a, c))
    return "100 mm, trim to fit" if to_bp else "150 mm, trim to fit"


def link_len(a, c):
    """A link between two backplane holes (copper side): the span plus 3 mm in each hole plus 7, rounded up to 5 mm."""
    if all(isinstance(e, str) and e.startswith("BP:") for e in (a, c)):
        (xa, za), (xc, zc) = st.bp_xy(a[3:]), st.bp_xy(c[3:])
        return f"{int(math.ceil((math.hypot(xc - xa, zc - za) + 13) / 5) * 5)} mm"
    return None


def mux_len(a):
    """Cut length of a mux lead or channel cable (muxleads.py: from the pad or QT port's real place on the #5626 to
    its hole 10), or None. A channel's two wires share one cable, so both rows give the cable's length."""
    if isinstance(a, tuple) and a[0] == "U4":
        import muxleads
        if a[1].startswith("CH"):
            return f"{muxleads.cable_cut(int(a[1][2]))} mm of cable"
        return f"{muxleads.cut({'H.VCC': 'VIN', 'H.GND': 'GND', 'H.SCL': 'SCL', 'H.SDA': 'SDA', 'H.RST': 'RESET'}[a[1]])} mm"
    return None


def where(e):
    if isinstance(e, str):
        b, h = e.split(":")
        return f"backplane line {h[1:].split('.')[0]} hole {h.split('.')[1]}" if b == "BP" else h
    part = next(p for p in model.PARTS if p["ref"] == e[0])
    pin = next(x for x in part["pins"] if x[0] == e[1])
    if e[0] == "U4" and e[1].startswith("CH"):            # a channel's QT port, not the header pin of the same name
        return f"U4 {e[1].split('.')[0]} {pin[1]}"
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
    FRONT_Y = min([0.0] + [bx.y0 for bb, pl in st.placements() if bb == b and pl["fp"] == "BOB"
                           for bx in st.boxes_of(pl)])     # the RJ11 jacks and their plugs, in front of the card
    W, H = sx(st.BW) + 360 + 40 * K, sy(FRONT_Y) + 140
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
        g.text(x, sy(FRONT_Y) + 16, row, 10, "middle")
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
    for i, (kind, a, c, side, note) in enumerate(route.WIRES):
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
    g.text(sx(st.BW / 2), sy(FRONT_Y) + 40, "FRONT EDGE (lid side): the card slides in from here"
           + ("; the RJ11 jacks overhang it, mouths toward the lid" if b in ("B1", "B2") else ""), 14, "middle", weight="bold")
    g.text(sx(st.BW / 2), sy(st.CD) - 50, f"BACK EDGE (snapped, filed flat): 1x30 header (column J, rows 1-30, pin "
           f"{model.KEY[b]} pulled: the slot key) plugs into the backplane", 13, "middle",
           weight="bold")
    kx, ky = hole_s(f"j{model.KEY[b]}")
    g.add(f'<path d="M{kx - 6:.1f},{ky - 6:.1f} l12,12 M{kx - 6:.1f},{ky + 6:.1f} l12,-12" stroke="#000" stroke-width="2.4"/>')
    g.text(kx, ky - 12, f"key: pin {model.KEY[b]} pulled", 10, "middle", weight="bold")
    dot = {"blue": "#1F5FBF", "green": "#2CA02C", "yellow": "#F1C40F", "red": "#D62728"}[model.KEY_COLOUR[b]]
    g.add(f'<circle cx="{sx(1.5):.1f}" cy="{sy(1.5):.1f}" r="{1.5 * K:.1f}" fill="{dot}" stroke="#000" stroke-width="1"/>')
    g.text(sx(1.5) + 2 * K, sy(1.5) + 4, f"{model.KEY_COLOUR[b]} dot ({b})", 10, weight="bold")
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
        return M + (i + 1.5) * st.P * KB          # one column of margin left of line 0

    def bz(n):
        return H - M - (n + 0.5) * st.P * KB
    g = Svg(W, H)
    ox0, oz0, ox1, oz1 = st.BP_OUTLINE                 # the real outline: factory right, top and bottom edges

    def ux(x):
        return bx(0) + (x - st.strip_x(0)) * KB

    def uz(z):
        return bz(1) - (z - st.BP_Z0) * KB
    g.rect(ux(ox0), uz(oz1), ux(ox1), uz(oz0), "#B3202A", "#5a0e12", 1.2)
    for name, (fx, fz) in st.BP_FACTORY.items():
        used_f = name == st.BP_FACTORY_SCREW
        g.add(f'<circle cx="{ux(fx):.1f}" cy="{uz(fz):.1f}" r="{S.val("pad3u_mount")[1] / 2 * KB:.1f}" fill="#D4AF37" '
              f'stroke="#7a5c12" stroke-width="0.8"/>')
        g.add(f'<circle cx="{ux(fx):.1f}" cy="{uz(fz):.1f}" r="{(1.6 if used_f else 1.4) * KB:.1f}" '
              f'fill="{"#fff" if used_f else "#2b2b2b"}" stroke="#000" stroke-width="1.2"/>')
        g.text(ux(fx) + 2.6 * KB, uz(fz) + 4, f"factory hole ({'drill to 3.2, M3 screw' if used_f else 'unused: no screws'})", 10)
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
        g.text(bx(-1) - 0.5 * KB, bz(n) + 4, n, 9, "end")
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
            iso = (i, n) in st.BP_ISOLATED                 # an isolated socket contact: no bus wire, its own pad
            g.add(f'<rect x="{bx(i) - 4:.1f}" y="{bz(n) - 4:.1f}" width="8" height="8" fill="{"#FFFFFF" if iso else ncol(net)}" '
                  f'stroke="{"#888" if iso else "#000"}"/>')
        if ref.startswith("XB"):
            n = int(next(iter(pins.values())).split(".")[1])
            kb = next(b for b in st.BOARDS if model.SOCKETS[b] == ref)
            ki, kn = st.BP_KEYS[kb]
            g.add(f'<rect x="{bx(ki) - 5:.1f}" y="{bz(kn) - 5:.1f}" width="10" height="10" fill="#000" stroke="#000"/>')
            g.text(bx(ki), bz(kn) - 8, "K", 9, "middle", weight="bold")
            ln = model.HDR_LEN[kb]
            g.rect(bx(1) - 1.27 * KB, bz(n) - 1.27 * KB, bx(ln) + 1.27 * KB, bz(n) + 1.27 * KB, "none", "#000", 1.4)
            g.text(bx(st.BP_STRIPS) + 2 * KB, bz(n) + 4, f"{ref}: {note} ({model.KEY_COLOUR[kb]} dot)", 11, weight="bold")
        elif ref.startswith("W") or ref == "XJ1" or ref in ("R7", "R8"):
            if ref in ("R7", "R8"):
                (i1, n1), (i2, n2) = [tuple(int(v) for v in h[1:].split(".")) for h in pins.values()]
                g.add(f'<line x1="{bx(i1):.1f}" y1="{bz(n1):.1f}" x2="{bx(i2):.1f}" y2="{bz(n2):.1f}" stroke="#C9B48A" '
                      f'stroke-width="{2.5 * KB:.1f}" opacity="0.8"/>')
                g.text((bx(i1) + bx(i2)) / 2, (bz(n1) + bz(n2)) / 2 + 4, ref, 11, "middle", weight="bold")
            n = int(next(iter(pins.values())).split(".")[1])
            g.text(bx(st.BP_STRIPS) + 2 * KB, bz(n) + 4 + (12 if ref == "R8" else 0), f"{ref}: {note}", 10)
    for kind, a, c, side, note in route.WIRES:
        for e, o in ((a, c), (c, a)):
            if isinstance(e, str) and e.startswith("BP:"):
                i, n = (int(v) for v in e[4:].split("."))
                g.add(f'<circle cx="{bx(i):.1f}" cy="{bz(n):.1f}" r="6" fill="none" stroke="#8E44AD" stroke-width="2"/>')
    lx = bx(st.BP_STRIPS) + 2 * KB + 380
    g.text(M, 26, f"Backplane: BusBoard PAD3U padboard cut {n_strips} x {st.BP_HOLES} holes, seen from the lid (glands down: the front, "
           "component side; line 0 at the left wall); a pad per hole, no strips: the bus wires on the copper side join them", 15, weight="bold")
    y = M + 10
    g.text(lx, y, "Line: what its bus wire carries", 13, weight="bold")
    for i in range(n_strips):
        y += 15
        legs = [f"{ref}'s free leg" if all(h.split(".")[0] != f"s{i}" for h in pins.values() if h != hp) else ref
                for ref, pins, _n in st.BP_PARTS if not ref.startswith("XB") for hp in pins.values()
                if hp.split(".")[0] == f"s{i}"]
        txt = plain(REP['BP'].get(f's{i}')) if REP['BP'].get(f's{i}') else "no bus wire" + (f" ({', '.join(legs)})" if legs else "")
        g.text(lx, y, f"{i}: {txt}", 10.5)
    y += 25
    for s_ in ("black outline: card socket (generic female strip, every one cut to 1x30, lines 1-30)", "small square: a pin in a hole",
               "white square: a socket contact on an isolated pad (its card pin is spare or card-local: no bus wire)",
               "black square K: the socket's key plug (a cut-off male pin in that contact, flush; its pad soldered to nothing else)",
               "coloured line: bare bus wire on the copper side, ringed where soldered",
               "purple ring: a lead soldered on the copper side",
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
    zi0, zi1 = cage.IN_Z0, cage.IN_Z1                      # the base's inside faces (enclosure 4)
    for o, a0, a1, title in ((side, 0, d_in, "SIDE (section, seen from the left wall): back wall and pole left, lid right"),
                             (front, cage.IN_X0, cage.IN_X1, "FRONT (from the lid, glands down): left wall (card block) left")):
        g.rect(o(a0), Z(zi1), o(a1), Z(zi0), "#f4f6f8", "#555", 1.2, dash="6 3")
        g.text(o(a0), Z(zi1) - 10, title, 13, weight="bold")
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
    g.text(front(w_in / 2), Z(-8) + 16, f"glands in the bottom wall: {sum(1 for g_ in cage.GLANDS if g_[2] == 'PG-7')} PG-7, 2 PG-9 (right column), no spare", 10, "middle")
    for b_ in cage.shell():
        if "flange" in b_.what:
            g.rect(side(b_.y0), Z(b_.z1), side(b_.y1), Z(b_.z0), "#bbbbbb", "#555", 0.6, 0.8)
    g.add(f'<line x1="{side(cage.SEAM):.1f}" y1="{Z(zi1):.1f}" x2="{side(cage.SEAM):.1f}" y2="{Z(zi0):.1f}" '
          'stroke="#1F5FBF" stroke-width="1.5" stroke-dasharray="8 4"/>')
    g.text(side(cage.SEAM) + 4, Z(zi1) + 14, f"base / lid seam (Yb {cage.SEAM:g}): lid tray beyond", 10, fill="#1F5FBF")
    for k in cage.box_keepouts():
        g.rect(front(k.x0), Z(k.z1), front(k.x1), Z(k.z0), "#cccccc", "#666", 0.6, 0.6)
        if "floor" in k.what:
            g.text(front((k.x0 + k.x1) / 2), Z(k.z0) + 10, k.what.split()[-1], 8, "middle")
    a1 = [lc.to_box("B3", x) for r_, x in lc.board_boxes("B3") if r_ == "A1"]
    arm = next(x for x in a1 if x.what.endswith("forward arm"))
    _pe, yb, sz, _ax = cage.coax(arm)
    g.rect(front(cage.IN_X1 - 1), Z(sz + 4), front(cage.IN_X1 + 8), Z(sz - 4), "#D4AF37", "#7a5c12", 1)
    g.rect(side(yb - 4), Z(sz + 4), side(yb + 4), Z(sz - 4), "#D4AF37", "#7a5c12", 1)
    g.text(front(cage.IN_X1 + 10), Z(sz) + 4, "SMA bulkhead (enclosure 4)", 10)
    g.text(M, 28, "TX stack r3 in the printed PETG base (enclosure 4, 120 deep) under the #905 lid, hanging long side up, to scale "
           f"3.2 px/mm; inside {w_in:g} x {h_in:g} x {d_in:g} mm (lid interface: L2 and the rim ring's fit [TBD-MEASURE])", 15, weight="bold")
    g.text(M, 48, "Blue: moulded cage features. Red slabs: cards. Tan: backplane. Dashed: plug keep-outs. Grey: corner "
           "blocks, gland nuts, mounting flanges; the lid's channel wall and bosses above the seam.", 12)
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
         f"`layout/drawings.py` writes this sheet from `layout/stack.py`. The drawing is `drawings/{b}-top.svg`.", "",
         "Hole names are a letter plus a number, as on the SolderFul silkscreen: `e10` is column E, row 10. SolderFul "
         "and `layout/stack.py` call the lettered lines A-J columns and the numbered lines 1-30 rows. Rail `F+` is the "
         "outer front rail and carries the 3.3 V supply. Rail `F-` is the inner front rail and carries ground. The "
         f"front edge (column A) faces the lid, and the back edge plugs into the backplane.", "",
         f"Each strip on {b} carries one line, and `layout/layout_checks.py` checks that. Each wire follows its route in "
         f"`drawings/{b}-top.svg`. `layout/route.py` lays every route flat, in straight runs on the 1.27 mm grid, with "
         "right-angle bends around every part.", "",
         "Lengths are cut lengths: the route plus 10 mm, rounded up to the next 5 mm. Use 24 AWG solid insulated wire "
         "unless the table says otherwise. Its insulation OD is about 1.45 mm `[TBD-MEASURE]`.", "",
         COLOURS, "",
         "## 1. Snap off the back rails (before any soldering)", "",
         f"1. Score both faces along the line between column J and the inner back rail. That line is at card Y "
         f"{st.CD:.2f} mm from the front edge [TBD-MEASURE: measure it on your {b}]. Clamp {b} along the line and "
         "snap the two back rails off.",
         "2. File the edge flat and square to the front edge. Stop at the line, so you don't open the column J holes.",
         f"3. Check that {b} is {st.CD:.2f} mm deep everywhere and slides into a test slot without catching.",
         f"4. Label it: a {model.KEY_COLOUR[b]} paint-pen or sticker dot on the top face at the front edge, near row 1. "
         f"That's the {b} colour, and the matching dot goes on the base beside the {b} slot (ASSEMBLY.md). The header's "
         f"pin {model.KEY[b]} comes out before you fit the header (the slot key, see the header in the parts list "
         f"below), so {b} seats only in its own slot.", ""]
    ws = [(i, x) for i, x in enumerate(route.WIRES) if b in (board_of_end(x[1]), board_of_end(x[2]))]
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
        L += [f"## {step}. Bare jumpers on top", ""]
        for k, (wi, (kind, a, c, side, note)) in enumerate(top, 1):
            ends = [e.split(":")[1] for e in (a, c)]
            plus = [e for e in ends if e.startswith("F+")]
            if plus and not all(e.startswith("F") for e in ends):
                n_ = plus[0][2:]
                L += [f"Jumper {k} ({ends[0]} to {ends[1]}) runs straight over hole F-{n_} on the ground rail, and that "
                      f"hole has a bare pad. Sleeve this jumper (or use insulated wire), or arch it clear of F-{n_}. "
                      "Otherwise it can short the 3.3 V supply to ground.", ""]
        L += ["| # | From | To | Length | Line | What |", "|---|---|---|---|---|---|"]
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
        for (ref, pad), (sj, sj_at, why) in st.PAD_BRIDGED.items():
            if ref == pl["ref"]:
                L += [f"Before you fit {ref}, solder {sj} closed ({sj_at}): {why}. Then meter {pad.split('.')[-1]} to VIN+. It should beep.", ""]
        rows = []
        for pin, xy in st.pins_of(pl).items():
            rows.append(f"| {lc.PIN[(pl['ref'], pin)][1]} ({pin}) | {lc.hole_at(xy)} | {plain(lc.NET_OF.get((pl['ref'], pin)))} |")
        for pad in st.pads_of(pl):
            how = (f"pad: left bare ({st.PAD_BRIDGED[(pl['ref'], pad)][0]} closed joins it)" if (pl["ref"], pad) in st.PAD_BRIDGED
                   else "pad: soldered lead")
            rows.append(f"| {lc.PIN[(pl['ref'], pad)][1]} ({pad}) | {how} | {plain(lc.eff_net((pl['ref'], pad)))} |")
        if rows:
            L += ["| Pin | Hole | Line |", "|---|---|---|"] + rows
        if pl["ref"] == "U2":
            L.append("| VBUS, VIN-, VIN+ (header pins 5-7) | pulled out of the header before fitting | battery nodes stay off the card |")
        if pl["ref"] == model.HEADERS[b]:
            k = model.KEY[b]
            L.append(f"| key {k} ({k}) | none: pulled out of the plastic before fitting (grip the pin with pliers, "
                     f"heat it if it sticks, push it out; hole j{k} stays empty) | the slot key: {b}'s own socket has a "
                     f"key plug in contact {k}; every other socket's key plug meets one of {b}'s pins |")
        L.append("")
    step += 1
    leads = [(i, x) for i, x in ws if x[0] == "lead" or board_of_end(x[1]) != board_of_end(x[2])]
    if leads:
        L += [f"## {step}. Leads (off the card, and from breakout pads)", "",
              "Each lead runs off its pad straight across its own breakout to the nearest edge. Then it drops to "
              f"{b} and follows its route. A lead that leaves {b} goes off at the front edge, where the drawing "
              "shows a ring.", "",
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
    for kind, a, c, side, note in route.WIRES:
        for e in (a, c):
            if isinstance(e, str) and e.startswith(b + ":"):
                use[st.strip_of(e.split(":")[1])].append(f"{e.split(':')[1]} {kind}")

    def skey(s):
        return (0, int(s[1:]), s[0]) if s[0] in "LR" else (1, 0, s)
    for s_ in sorted(use, key=skey):
        name = (f"row {s_[1:]}, columns {'A-E' if s_[0] == 'L' else 'F-J'}" if s_[0] in "LR" else f"rail {s_}")
        L.append(f"| {name} | {plain(rep[b].get(s_)) if rep[b].get(s_) else 'nothing (an unused pin)'} | "
                 f"{', '.join(sorted(use[s_]))} |")
    nb = neighbour_beeps(b)
    L += ["", "## Before power", "",
          "- Meter each strip in the map to its neighbours: no continuity between neighbouring strips"
          + ("." if not nb else f", except {nb[0]}, which beep." if len(nb) == 1 else ", except these pairs, which beep:")]
    L += [f"  - {x}" for x in (nb if len(nb) > 1 else [])]
    L += [
          "- No continuity between the 3.3 V supply and ground (the two front rails).",
          "- Each header pin Jn beeps to Fn (column J to column F in the same row: its own strip). It beeps to no "
          "other header pin, except the groups below."]
    for grp, why in header_beeps(b):
        L.append(f"- Header pins {', '.join(f'J{n}' for n in grp)} beep to each other: {why}.")
    spare = [n for n in st.model.hdr_pins(b) if st.model.pin_net(b, n) is None]
    also = {}
    for (bb, h), (ref, pin) in lc_ph.items():
        if bb == b and ref != st.model.HEADERS[b] and st.strip_of(h)[0] == "R" and int(st.strip_of(h)[1:]) in spare:
            also[int(st.strip_of(h)[1:])] = f"{ref} {lc.PIN[(ref, pin)][1]}, unused"
    L.append(f"- The 1x30 header less its key pin: J{model.KEY[b]} pulled (hole j{model.KEY[b]} empty), and every other "
             f"pin fitted. Spare pins (no net on {b}, and their socket contacts sit on isolated pads): "
             + (", ".join(f"J{n}" + (f" (its strip also holds {also[n]})" if n in also else "") for n in spare) or "none") + ".")
    (OUT_MD / f"{b}.md").write_text("\n".join(L) + "\n")


SHUNT = "through U2's shunt (X1 VIN- to X1 VIN+, 15 milliohms)"


def neighbour_beeps(b):
    """The neighbouring strip pairs on card b that beep: same line (with what joins them), and B4's shunt pair."""
    def joins(s1, s2):
        for kind, a, c, side, note in route.WIRES:
            ends = [e.split(":")[1] for e in (a, c) if isinstance(e, str) and e.startswith(b + ":")]
            if len(ends) == 2 and {st.strip_of(e) for e in ends} == {s1, s2}:
                return f"joined by the {ends[0]}-{ends[1]} {kind}"
        return f"joined on {b}"
    out = []
    for half, cols in (("L", "A-E"), ("R", "F-J")):
        for n in range(1, 30):
            s1, s2 = f"{half}{n}", f"{half}{n + 1}"
            n1, n2 = REP[b].get(s1), REP[b].get(s2)
            if n1 and n1 == n2:
                both = f"both {plain(n1)}, " if "(" not in plain(n1) else ""
                out.append(f"rows {n}-{n + 1}, columns {cols} ({both}{joins(s1, s2)})")
            elif b == "B4" and half == "R" and n == 20:
                out.append("rows 20-21, columns F-J (through U2's shunt, X1 VIN- to X1 VIN+, 15 milliohms)")
    return out


def s5_holes():
    """The bus-wire holes that only the section-5 copper-side wires fill: 'hole 5 on lines 19, 20, 21 and 22, ...'."""
    by = defaultdict(set)
    for kind, a, c, side, note in route.WIRES:
        if side == "copper" and kind == "wire":
            for e in (a, c):
                if isinstance(e, str) and e.startswith("BP:s"):
                    i, n = e[4:].split(".")
                    by[int(n)].add(int(i))
    def ands(xs):
        xs = [str(x) for x in sorted(xs)]
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
    parts = [f"hole {n} on lines {ands(by[n])}" for n in sorted(by)]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]


def isolated_list():
    """The isolated socket contacts, per socket: 'XB1 lines 19-30; ...'."""
    out = []
    for c in ("B4", "B2", "B1", "B3"):
        ls = sorted(i for i, n in st.BP_ISOLATED if n == st.SOCKET_HOLE[c])
        runs = []
        for i in ls:
            if runs and i == runs[-1][1] + 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
        out.append(f"{model.SOCKETS[c]} (hole {st.SOCKET_HOLE[c]}) lines "
                   + ", ".join(f"{a}-{z}" if z > a else f"{a}" for a, z in runs))
    return out


def header_beeps(b):
    """[(header columns, why)] that beep together on card b: one line joined on the card, or B4's battery path."""
    pins = sorted(n for n in range(1, st.model.HDR_LEN[b] + 1) if n not in st.model.PULLED.get(b, ()))
    by = {}
    for n in pins:
        by.setdefault(REP[b].get(f"R{n}"), []).append(n)
    out = [(g, f"all {plain(k)}") for k, g in by.items() if k and len(g) > 1]
    if b == "B4":
        out = [g for g in out if not set(g[0]) & {19, 20, 21, 22}]
        out.append(([19, 20, 21, 22], f"19-20 and 21-22 by the top jumpers, and 20-21 {SHUNT}"))
    return out


def cage_slot_end():
    return lc.cage.RSLOT[3]


def cage_ins():
    return cage_slot_end() - st.BP_OUTLINE[2]


def cage_slot_room():
    """The most the factory right edge may sit past the last line and still let the left edge clear the wall coming in."""
    return lc.cage.RSLOT[3] - (lc.cage.WALL + 0.2) + st.BP_OUTLINE[0] - st.strip_x(st.BP_STRIPS)


def backplane_sheet(ph):
    n_lines = st.BP_STRIPS + 1
    bus = dict(st.BP_BUS)
    L = ["# Backplane: build sheet", "",
         "`layout/drawings.py` writes this sheet. The drawing is `drawings/backplane.svg`.", "",
         "The backplane is a BusBoard PAD3U padboard (160.02 x 100.08 mm, 38 x 62 holes on 0.1 in). It has a separate "
         f"plated pad per hole and no strips. You use {n_lines} of its rows at the plated end, each the full "
         f"{st.BP_HOLES} holes. Both faces have pads. This sheet calls the face the sockets go on the component side "
         "(the front, toward the cards), and the face with the bus wires the copper side (toward the back wall). The "
         "lines run up and down in the box.", "",
         "Nothing on the board connects unless a wire does. On lines 1-18 a bare bus wire on the copper side, soldered "
         "at every used pad, carries bus line n for every card (every socket is 1x30). Lines 19-23 and 26 carry B4's "
         "power pins (the battery path, its senses and SYS) down to short leads to the charger and the pack. The "
         "charger's own ground lead (J3 GND, SYS's return) lands on line 12, the bus ground.", "",
         "## 1. Cut", "",
         f"1. Take one PAD3U and find the end with the two large plated mounting holes. The other end has two small "
         f"plain holes. Count {n_lines} rows in from the mounting-hole end. They become lines {st.BP_STRIPS} (next to "
         f"the mounting holes) down to 0, each the full {st.BP_HOLES} holes. Seen from the face that becomes the front "
         "(the face the sockets go on), the mounting-hole end is the right edge. Keep the PAD3U's own right, top and "
         "bottom edges, with no cut there.",
         "2. There are no holes to drill, because the base has no screw posts (enclosure 4). The cards in the sockets "
         "hold the board. Leave both mounting holes as they are: the right corner post's slot holds that edge.",
         "3. Score both faces midway between line 0 and the next row out (never through the holes) and snap. That's "
         "the only cut. Sand the edge flat. Aim for 1.27 mm from line 0's hole centres, about 0.8 mm from the near "
         "side of the 0.94 mm holes. If the edge ends more than about 1.78 mm from those centres, it won't go fully "
         "into the left wall's groove. Cut a little short and it still seats under the groove roof.",
         f"4. Check the right edge. It should be {S.val('pad3u_plated_edge'):g} mm beyond the mounting holes' centres "
         f"({st.BP_OUTLINE[2] - st.strip_x(st.BP_STRIPS):.2f} from line {st.BP_STRIPS}'s) [TBD-MEASURE: the scan cuts "
         f"that end off]. For the fit, it must be no more than {cage_slot_room():.2f} past line {st.BP_STRIPS}'s centres.",
         "5. Meter any two neighbouring pads. They read open, because the board has no strips.", "",
         "## 2. Sockets (one per card; pin n on line n) and their key plugs", "",
         "| Socket | Card | Hole along the lines | Key plug (line, hole) | Colour dot |", "|---|---|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if ref.startswith("XB"):
            kb = next(b for b in st.BOARDS if model.SOCKETS[b] == ref)
            ln = model.HDR_LEN[kb]
            ki, kn = st.BP_KEYS[kb]
            L.append(f"| {ref} generic female strip, cut to 1x{ln} | {note} | {next(iter(pins.values())).split('.')[1]} | "
                     f"contact {ki}: line {ki}, hole {kn} | {model.KEY_COLOUR[kb]} |")
    L += ["", "Fit each socket square to the board, because a card pin bent sideways won't go in. Solder one end pin, "
          "check the socket, then solder the rest. Every socket is 1x30 (lines 1-30). It takes its card's 29 header "
          "pins, and the key plug (below) in the 30th contact. Solder all 30 tails, each in its own pad.", "",
          "On lines 19-30 only B4's contacts on lines 19-23 and 26 meet a bus wire. Every other contact there is "
          "soldered to its own pad and nothing else (an isolated pad):", ""]
    L += [f"- {x}" for x in isolated_list()]
    L += ["", "Cut each socket from a longer strip. Pull the contact one past the end and cut through that empty "
          "position, so you lose one position at each cut. File the cut face flat.", "",
          "**Key plugs (the slot keys).** The four sockets are the same, so each one gets a key plug that only its own "
          "card clears: " + ", ".join(f"{model.SOCKETS[b]} (for {b}) in contact {model.KEY[b]}" for b in st.ORDER) + ". "
          "Each card has that same pin pulled from its header (see its build sheet). Every other card still has that "
          "pin, so it stubs on the plug and can't seat. For example, B3 in B4's slot would put the battery on the Wio-E5.", "",
          "Make each plug from the generic male header stock. Pull one pin out of the plastic. Push its long end into "
          "the socket contact from the front until it bottoms. Cut it flush with the socket mouth and file the cut end "
          "flat, so nothing stands proud of the mouth.", "",
          "Only the contact's grip holds the plug. Never solder it, and solder nothing else to that contact's pad. It "
          "stays an isolated pad, with no bus wire and no lead. After fitting, try each card in each wrong socket by "
          "hand, off the base. Each one must stop at the mouth.", "",
          "**Colour dots.** Put a paint-pen or sticker dot beside each socket on the front face, and one on the base "
          "beside its card slot. Use the same colour as the dot on that card's front edge: " + ", ".join(
              f"{b} {model.KEY_COLOUR[b]}" for b in st.BOARDS) + ".", "", "## 3. Pins and parts on the front (the charger's I2C, the sense resistors)", "",
          "| Part | Pin | Line, hole | Bus line |", "|---|---|---|---|"]
    for ref, pins, note in st.BP_PARTS:
        if not ref.startswith("XB"):
            for pin, h in pins.items():
                i, n = h[1:].split(".")
                L.append(f"| {ref} ({note}) | {lc.PIN[(ref, pin)][1]} | {i}, {n} | {plain(lc.NET_OF.get((ref, pin)))} |")
    L += ["", "R7 and R8 lie flat on the front, with R8 on a slant and its legs bent to the span. R7's free leg (line 24, "
          "hole 7) also takes the charger sense lead on the copper side.", "",
          "### Leads to the charger and the pack (copper side, short)", "",
          "| From | To the backplane | What |", "|---|---|---|"]
    for kind, a, c, side, note in route.WIRES:
        if kind == "lead" and isinstance(a, tuple) and a[0] in ("PG1", "U1") and isinstance(c, str) and c.startswith("BP:"):
            i, n = c[len("BP:s"):].split(".")
            L.append(f"| {where(a)} | line {i}, hole {n} | {note} |")
        elif kind == "lead" and isinstance(a, tuple) and a[0] == "R7":
            L.append(f"| {where(c)} | R7's free leg (line 24, hole 7) | {note} |")
    L += ["", "Cut each lead to the length in section 5 and trim it to fit. Leave a service loop, because the EVM "
          "slides out on these leads.", "",
          "The ground lead (J3 GND to line 12) is SYS's return. The regulator's load and the radio's transmit peaks "
          "come back mainly on it, so they don't depend on the I2C lead's J8 pin 1. J8 pin 1 is tied to the same "
          "ground on the EVM and still carries a small parallel share. Run the ground lead beside the SYS lead from J3 "
          "and on to line 12 above the mux.", "",
          "## 4. Bus wires (copper side)", "",
          f"Use bare 22 AWG solid copper: the Adafruit 1311 hook-up wire on hand, stripped ({S.val('bus_wire'):g} mm). "
          "Lay each wire straight along its line over the pads and tack it at the first and last hole. Then solder it at "
          "every hole listed. Cut length: the span plus 10 mm.", "",
          "Most of those holes already hold a socket pin, an XJ1 pin, a resistor leg or a section-3 lead. The "
          "others take the section-5 leads: " + s5_holes() + ". Fit those leads before the bus wires, or leave those "
          "holes open and solder them in section 5.", "",
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
    for kind, a, c, side, note in route.WIRES:
        if side == "copper":
            L.append(f"| {where(a)} | {where(c)} | {lead_len(a, c) or mux_len(a) or link_len(a, c) or '40 mm'} | {plain(net_of_end(c, ph) or net_of_end(a, ph))} | {note} |")
    L += ["", "The mux is an Adafruit #5626. Bridge A0 for address 0x71 and set its Vlogic switch SW1 to V+. It sits "
          "on a foam pad on the copper side over holes 2-9, below the B4 socket. That keeps it clear of the bus wires, "
          "which start at hole 10. Its 5-hole header (VIN, GND, SCL, SDA, RST, at the far end from its upstream QT "
          "port) takes five leads to the main bus lines. Channels 0-3 reach sensor ports 1-4 through four Adafruit "
          "#4209 QT cables, one plugged into each channel's QT port. Its upstream port and channels 4-7 stay empty, "
          "and the sensors take power from their own card ports.", "",
          "VIN, GND, SCL, SDA and RST are 22 AWG solid insulated hook-up (Adafruit 1311), stripped 3 mm, soldered in "
          "from the top face with the tails trimmed flush on the back. Channels 0-3 are the QT ports along the long "
          "edge on the same side as the header's VIN end (CONN1, CONN2, CONN5, CONN6; Adafruit's board file, "
          "`layout/muxleads.py`). Cut each #4209 cable's male-pin end off at the length in the table, measured from "
          "the back of the plug. Strip 3 mm off its blue (SDA) and yellow (SCL) wires. Cut its red (V+) and black "
          "(GND) wires off about 3 mm from the plug and tape them; the mux's ground comes through its header lead. "
          "Nothing else is soldered to the mux. Stick the back face to the foam, the channel 0-3 edge toward hole 10, "
          "and plug the four cables in. The foam goes in the middle, no thicker than 1 mm, so the mux clears the "
          "floor. Each lead and cable wire goes into its hole 10 from the copper side and is soldered on the front; "
          "the bus wire's joint on the copper side takes it too.", "",
          "## 6. Fit it in the base (`cage/backplane-mount-spec.md`)", "",
          f"1. With the copper side back and the mux behind it, tilt the board. Push its factory right edge into the "
          f"right corner post's slot, to the slot's end (Xb {cage_slot_end():.2f}). Its left edge is then clear of the "
          "left wall's face. Lower the left side onto the pads, copper face down.",
          "2. Slide it left, flat on the pads, until its left edge is in the left wall's groove and the rail below it "
          f"(about {cage_ins():.2f} mm). The right edge stays "
          f"{st.BP_OUTLINE[2] - 85.8:.2f} mm into the slot. The mux moves with it and clears the pads.",
          f"3. There are no screws, because enclosure 4 has no screw posts. The board lies on the support pads under "
          f"{', '.join(st.BP_SUPPORTS)}. Once the cards are plugged into its sockets, they hold it in place. Until then "
          "it's loose, so fit the cards straight after. It comes out the same way, after every card is out.", "",
          "## 7. Hole by hole", "", "This table has every pad with anything soldered in it. Every other pad stays bare.", "",
          "| Line | Hole | What is in it | Bus wire |", "|---|---|---|---|"]
    used = defaultdict(list)
    for ref, pins, note in st.BP_PARTS:
        for pin, h in pins.items():
            used[h].append(f"{ref} {lc.PIN[(ref, pin)][1]}")
    for kind, a, c, side, note in route.WIRES:
        for e, o in ((a, c), (c, a)):
            if isinstance(e, str) and e.startswith("BP:"):
                used[e[3:]].append(f"lead to {where(o)}")
    for h in st.BP_SCREWS:
        used[h].append("3.2 mm screw hole (drilled; opens into the scored edge)")
    for h in sorted(used, key=lambda h: tuple(int(v) for v in h[1:].split("."))):
        i, n = (int(v) for v in h[1:].split("."))
        wire = f"line {i}" if n in bus.get(i, []) else ("- (isolated pad)" if (i, n) in st.BP_ISOLATED else "-")
        L.append(f"| {i} | {n} | {'; '.join(used[h])} | {wire} |")
    L += ["", "## Before power", "",
          "- Each bus line to its neighbours: open, except 19-20 and 21-22, which are closed (joined at hole 5), and "
          "22-23, which reads about 100 ohm through R8. Line 2 to line 12: closed (both ground, joined at hole 38).",
          "- 3.3 V supply (line 1) to ground (line 2): open.",
          "- Lines 19-30: each B4 contact on lines 19-23 and 26 beeps to its line's bus wire (19 to 20, 21 to 22). "
          "Every other contact on lines 19-30 (the isolated pads, the key plugs' included) beeps to nothing: not its "
          "line's wire, not its neighbours.",
          "- The charger ground lead's EVM end (J3 GND) beeps to line 12 and line 2.",
          "- Each bus wire: continuity from its first to its last soldered hole."]
    (OUT_MD / "BACKPLANE.md").write_text("\n".join(L) + "\n")


def assembly_sheet():
    order = ", ".join(f"{b} {st.ROLE[b]}" for b in st.ORDER) + " (top)"
    L = ["# Assembly: charger set-up, the printed base, shelves, cards, cables", "",
         "`layout/drawings.py` writes this sheet. Read it with `drawings/cage-side.svg`, `build/B1..B4.md` and "
         "`build/BACKPLANE.md`.", "",
         "## 1. Charger (BQ25798EVM) before any power: jumper changes (TI SLUUCB5; issue #34)", "",
         "The EVM ships set for two cells. Do these in order, with nothing connected:", "",
         "1. **JP24 off, JP22 on** (PROG: one cell, 1.5 MHz). JP22 is the only PROG jumper fitted.",
         "2. **Battery sense wire first, then JP9 off.** Screw the charger battery sense lead into J5 SNS_BATP, J5's "
         "middle position (J5 is an ED120/3DS screw block: PGND, BATP, BATTERY from the back edge, SLUUCB5E Figure "
         "4-1). It comes from R7 on the backplane (its free leg at line 24, hole 7). Only then remove JP9, so BATP never "
         "floats.",
         "3. **JP18 off, thermistor on J7.** Fit the Adafruit #372 10 kohm NTC (B 3950) to J7 and tape it to the pack. "
         "The EVM's TS divider is set for a 103AT (B 3435), so with this NTC the chip's fixed cold stop sits at "
         "about 4 C and its fixed hot stop at about 55 C. The firmware moves the warm point to about 42 C and stops "
         "charging there (`App/power_config.h`). "
         "Read the TS percentage over I2C at room temperature. Check that it sits in the normal band before you charge.",
         "4. **JP12, JP17 and JP30 stay in.** JP30 powers the EVM's 3.3 V PULLUP rail. That rail holds the I2C "
         "pull-ups R39 (SCL) and R40 (SDA), 10 kohm each. R41 and R42 on the same rail pull up /INT and /CE. Only the SCL/SDA "
         "pair counts toward the bus total (1.40 kohm, schematic check 3).",
         "5. There's one status LED, D13 (the STAT LED). It sits on JP32, which is fitted as shipped, and draws about "
         "0.6-0.7 mA when lit. Leave it, or pull JP32 to remove it.",
         "6. USB in is J6, micro-B (JP7 on VIN1). Use a USB-C to micro-B cable from the 2 A adapter.",
         "7. **First power without the pack and with JP17 out** (charge disabled). The firmware does the I2C part "
         "(`firmware/stage0-node/App/charger.c`, built with `WS_POWER_PROFILE=3 WS_I2C_MUX=1`). At every start it "
         "writes the charge voltage (4.2 V, REG0x01-0x02) and the charge current (ICHG about 0.9 A; spec charger "
         "set-up, electrical C1/M1/M2, and issue #34), reads both back and checks that REG0x0A says one cell. It "
         "writes them again after any chip reset, because ICHG goes back to its 1 A default on a power cycle or a "
         "chip watchdog timeout. It also sets the input over-voltage limit to 12 V (the chip powers up at 7 V, "
         "which the P110 can pass on a cold morning), the panel's MPPT at 0.81 of its open-circuit voltage, and "
         "the warm stop above. It keeps charge off until a fresh TS reading is neither cold, warm nor hot. The JP22 note "
         "says 2 A, and the datasheet default is 1 A. The firmware runs on the cards, so do this check once they're "
         "in (Session 8): USB in J6, no pack, JP17 out, then type `CHARGER` on the TX console. Look for `cells=1`, "
         "`vreg_mv=4200`, `ichg_ma=900`, `vac_ovp=2`, `voc_pct=4`, `ts=NORMAL` and `hold=none`, and write down "
         "`ts_pct` and `pack_dc` (the pack temperature in 0.1 C). Then refit JP17 and "
         "connect the pack, last.", "",
         "## 2. Print the base (`cage/cage.py`)", "",
         "1. Print the rim test ring first (`cage.py --ring`, `cage/stl/rim-ring.stl`). It's the whole rim, 175.5 x "
         "129.5 x 8, about an hour to print, flat on its land. Press the real lid onto it. The lip must drop into the "
         "O-ring channel all the way round and through all four S-curves. All four holes must sit under the lid's at "
         "once, and the outer edge must be flush on all four sides. Correct `cage/lid-rim-spec.md` until it does, then "
         "set `ring_fit` True.",
         "",
         "   `cage.py --stl` refuses the full base until `ring_fit` and L2 (`l2_screw_pos`, the lid bolt positions) are "
         "sourced. L1 left that gate when Clint's printed bolts (option c) were chosen. Also settle the EVM's part "
         "heights and J6 under it (`evm`, `evm_under`).",
         f"2. Then print the test coupon (`cage.py --coupon`, `cage/stl/coupon.stl`, not gated). It's the base's "
         f"top-left corner cut out of the model: Xb {cage.COUPON[0]:g} to {cage.COUPON[3]:g}, Zb {cage.COUPON[2]:g} up, "
         f"Yb {cage.COUPON[1]:g} to the lip, about {cage.RING_PRINT * cage.COUPON_CM3:.0f} minutes, printed Yb up with the cut "
         "face on the bed. It holds B3's slot in the left wall (tune `slot_clear` until a card slides in with light "
         "friction), the top-left lid bolt bore (try one of the printed bolts in it) and the land and sealing lip round "
         "that corner. Fit the lid on that corner and check that the sealing lip presses the O-ring with the lid's "
         "walls down on the land. The squeeze isn't settled: it follows from whichever lip height is right (README). "
         "Its left and top walls are more than 30 mm square, so leak-test them too.",
         "3. Print the base in a light-coloured PETG (README, PETG in sun), with the floor on the bed (Yb up), not rim "
         "down. The 45-degree roofs over the groove and the backplane slot are drawn for that orientation. The floor is "
         "3 mm, the long walls 4.25 mm and the short walls 4.0 mm, printed solid (roughly 9-10 perimeters at a 0.42 mm "
         "line width). Don't put inserts in the four corner posts: the lid goes on with Clint's 3D-printed bolts in "
         "their bores. With the iron, set the retention bar's two M3 heat-set inserts in the left wall's front face. "
         "Set the EVM clips' two down into the left keeper and the right lid-end block, at Xb 4.5 and 100.25, Yb 106. "
         "Print the two clips (`cage.py --clip`, `cage/stl/evm-clips.stl`, not gated) flat on their top faces.",
         "",
         "   Leak-test the bare base: water in the base, or soapy water with the lid on and a little pressure through "
         "the vent hole. Coat the inside only if it leaks. Paint or clear-coat the outside against UV.",
         f"4. Fit the glands in the bottom wall's bosses. Five {S.val('gland')[0]:g} mm holes take PG-7s #762, for the "
         "four sensor-port cables S1-S4 and the solar lead. Two 15.5 mm holes take PG-9s #761, for the flat wind and "
         "rain cables (right column). There's no spare. Which gland takes which cable (`cage.GLAND_USE`, Xb, Yb): "
         + ", ".join(f"{n} ({x:g}, {y:g})" for (x, y), n in sorted(cage.GLAND_USE.items(), key=lambda t: (t[0][1], t[0][0])))
         + ". The port cables in use get the shortest runs from the right column's foot (back and left under the tray), "
         "the spare S4 the longest, and the solar lead the left front one, nearest J2. Fit the M12 vent, and the SMA "
         "bulkhead low in the right wall (enclosure 4: Yb 94.14, Zb 60.38).",
         "",
         "   Then fit the backplane (its build sheet, section 6). Tilt its factory right edge into the right corner "
         "post's slot, lower it and slide it left into the left wall's groove. There are no screws, because the cards "
         "hold it, so fit them straight after. It comes off again only after every card is out.",
         "5. Shelves, bottom to top: the pack on its tray (strap) first. Next the EVM, with its Bumpon feet peeled off, "
         "slid back on its ledges to the stop. Then the two front clips, one each side of J8: each clip's lip over the "
         f"board's front edge, an M3 x {cage.CLIP_SCREW[2]:g} socket cap through it into its insert. Leads with service "
         "loops. Then the cards.",
         f"6. Cables. A 6P plug ({S.val('plug_6p')[0]:g} x {S.val('plug_6p')[1]:g} mm, "
         f"{math.hypot(S.val('plug_6p')[0], S.val('plug_6p')[1]):.1f} across its corners, "
         f"{math.hypot(S.val('plug_6p')[0], S.val('plug_6p')[2]):.1f} with the latch) passes no gland. The PG-7 bore is "
         f"{S.val('gland_bore')[0]:g} and the PG-9's {S.val('gland_bore')[1]:g}, even with the seal out. So every cable "
         "goes through its gland with no plug on its inside end. You crimp that plug afterwards, inside the box, with "
         "Clint's 6P crimp plugs and a 6P (RJ11/RJ12) crimp tool.",
         "",
         "   Round port cables: from outside, slide the cap, the seal and the body's bore over the bare end. Pull the "
         "length through, crimp the plug and tighten the cap. Use the same pin order as the module end: 2 3.3 V, "
         "3 data, 4 ground, 5 clock.",
         "",
         "   The weather meters' flat cables come with their plugs fitted. Note which colour sits at which plug "
         "position (wind 2-5, rain 3-4). Cut the plug off outside the box and pass the cable in through the PG-9 with "
         "its seal out. Crimp a new plug in the same order. Once the cable's position is final, seal the gap with "
         "silicone or a split grommet. After that the cable comes out only if you cut the seal (and the plug).",
         "",
         "   Check that the crimp plugs hold the meters' narrower flat cable with each conductor on its position. If "
         "they don't, use 6P4C plugs.",
         "",
         "   Inside, leave a service loop in the space in front of the cards. Outside, leave a drip loop below each "
         "gland before you tie the cable to the pole. Each cable runs from its plug to the right column, down it, and "
         "left under the pack tray to its gland (cage/shelves-spec.md).",
         "7. The coax: fit AD1 on the Wio-E5 mini's SMA, its arm toward the lid, and the 135110 plug on AD1. Bend the "
         "cable right in front of the cards and run it down the right column to the bulkhead low in the right wall. "
         "Clip it to the right corner post. The 6 in cable reaches. Clint checked it on 2026-11-17: it fits the low "
         "bulkhead with no tight bend. The straight plug on the bulkhead's inner end passes about "
         f"{cage.SMA[1] - 4.0 - cage.EVM_Z0 - 1.6:.1f} mm over the EVM's lid-right corner, where SLUUCB5E Figure 4-1 "
         "has only silk (JP9, the nearest part, is about 4 mm off; `cage.py` checks it).",
         "8. Mount the box with hose clamps or straps through the two slots in each mounting flange (the short ends, "
         "in the floor plane). Put the lid on with its four printed bolts.", "",
         f"## 3. Cards, bottom to top: {order}", "",
         "**Labels (the slot key's colour code).** Each card gets a dot on its front edge. The same colour goes "
         "beside its slot on the base and beside its socket on the backplane: " + ", ".join(f"{b} {model.KEY_COLOUR[b]}" for b in st.BOARDS)
         + ", so match the dots. The key plugs (BACKPLANE.md section 2) stop a wrong card at the socket mouth. If a card "
         "won't go the last few millimetres, it's in the wrong slot, so never force it.", "",
         "Every card has its back rails snapped off and the edge filed flat first (step 1 of its build sheet). Each "
         "card slides in from the lid side along its left-wall slot and right-post slot. It goes in until its header "
         f"pins enter the socket ({S.val('insertion'):g} mm), and the header insulator meets the socket "
         f"{st.Y_MOUTH - st.Y_INS:.2f} mm further in. On B1 and B2 the RJ11 jacks overhang the front edge, mouths "
         "toward the lid. Fit the retention bar (front left, two M3 screws) last.", "",
         "To take a card out, take the bar off. Unplug that card's own plugs: the RJ11 cables on B1 and B2, the coax "
         "at AD1 on B3, and the SWD and USB-C leads if fitted. Then slide it out. No card needs another card out first. "
         "Nothing is soldered between a card and anything else (layout check L10).",
         "", "## 4. Leads off the cards", "", "| From | To | Length | What |", "|---|---|---|---|"]
    for kind, a, c, side, note in route.WIRES:
        ln = lead_len(a, c)
        if ln:
            L.append(f"| {where(a)} | {where(c)} | {ln} | {note} |")
    L += ["| EVM J8 (KK 4-pin housing, pins 1-3) | backplane charger pins | 150 mm | charger I2C: ground, clock, data |",
          f"| solar panel cable (Voltaic P110), cut at its gland ({', '.join(f'{x:g}, {y:g}' for (x, y), n in cage.GLAND_USE.items() if n == 'SOLAR')}) "
          f"| EVM J2 VIN2 (red), J2 GND (black) | {math.ceil((cage.solar_len() + 70.0) / 10.0) * 10:.0f} mm | 22 AWG "
          "stranded red/black pair, twisted, soldered and heat-shrunk to the panel cable's cores just above the gland "
          "nut; 0.34 mm2 (22 AWG) bootlace ferrules into J2. Route: forward under the EVM, up in front of the left "
          "keeper between its clip and J8, back over the clip along the left wall to J2 |",
          "",
          f"Battery leads are 24 AWG stranded (red +, black -), about {S.val('wire24')[2] * 0.1:.1f} mV drop per 0.1 m "
          f"at 1 A ({S.val('wire24')[2]:g} mohm/m). J5 BATTERY to line 19 is soldered at the backplane and screwed at "
          "J5. The pack + pigtail is soldered at line 21. The pack - lead runs straight from the pack to J5 GND "
          "(screwed) and doesn't touch the backplane. The charger sense lead from R7 is 24 AWG stranded too.", "",
          "SYS (J3 SYS to line 26) and its return (J3 GND to line 12, black) are a same-length pair of 24 AWG stranded "
          "leads, run side by side. The 3.3 V regulator's load and the radio's transmit peaks return mainly on that "
          "ground lead. So they don't depend on the I2C lead's J8 pin 1. J8 pin 1 is tied to the same ground on the "
          "EVM and still carries a small parallel share. The battery current reaches B4 only on doubled header pins "
          "(19-20, 21-22, layout check L4). No lead goes to a card (L10).", "",
          f"The solar pair is 22 AWG: the panel gives {S.val('solar_p110')[1]:g} A at its maximum power point and about "
          f"{S.val('solar_p110')[3]:g} A into a short (solar_p110), and the pair's two legs drop about "
          f"{2 * (cage.solar_len() + 70.0) / 1000 * S.val('wire22')[2] / 1000 * S.val('solar_p110')[1] * 1000:.0f} mV at "
          f"{S.val('solar_p110')[1]:g} A. Its length is `cage.solar_route()` ({cage.solar_len():.0f} mm, checked clear "
          "of the cards, the pack, the EVM and the clips) plus a 70 mm service loop.", "",
          "Inside the box, leave 60-80 mm service loops on the jack cables and the solar lead (no spec sets that length "
          "yet). Outside, leave a drip loop below each gland.", "",
          "## 5. Before the first power", "",
          "- Charger jumpers as in section 1, the pack disconnected, JP17 out.",
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
