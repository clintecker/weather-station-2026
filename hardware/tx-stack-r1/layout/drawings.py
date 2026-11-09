"""Drawings from layout/stack.py: a to-scale top view per board (SVG), a hole-by-hole build list per board
(markdown), and the to-scale side elevation of the stack (SVG). Run after layout_checks.py passes:
python3 drawings.py [--png]  (writes ../drawings/*.svg and ../build/*.md; --png also ../renders/*.png)
"""
import html
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import layout_checks as lc
import stack as st
from stack import S, model

ROOT = st.HERE.parent
OUT_SVG = ROOT / "drawings"
OUT_MD = ROOT / "build"
K = 9.0                       # px per mm in the top views
M = 60                        # margin, px

NET_COLOUR = {"+3V3": "#D62728", "GND": "#1A1A1A", "I2C_SDA": "#1F5FBF", "I2C_SCL": "#D4A017",
              "MUX_RST": "#8E44AD", "CUPS": "#2CA02C", "VANE": "#17A589", "RAIN": "#00A3D9", "SYS": "#E67E22",
              "VCCIO": "#999999", "SWDIO": "#7F8C8D", "SWCLK": "#7F8C8D", "NRST": "#7F8C8D"}
for k in range(1, 5):
    NET_COLOUR.update({f"P{k}_3V3": "#F08080", f"P{k}_SDA": "#6FA8DC", f"P{k}_SCL": "#F1C40F"})


def ncol(net):
    if net in NET_COLOUR:
        return NET_COLOUR[net]
    if net and model.NETS.get(net, ([], {}))[1].get("battery"):
        return "#C0392B"
    return "#888888"


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

    def write(self, path, title):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" height="{self.h:.0f}" '
                f'viewBox="0 0 {self.w:.0f} {self.h:.0f}" font-family="Helvetica, Arial, sans-serif">'
                f'<title>{esc(title)}</title><rect width="100%" height="100%" fill="#ffffff"/>')
        path.write_text(head + "\n".join(self.items) + "</svg>\n")


# ------------------------------------------------------------------ top view of one board
def end_xy(e):
    """Screen point of a conductor end on this board, or None."""
    if isinstance(e, str):
        return hole_s(e.split(":")[1])
    for _b, pl in st.placements():
        pads = st.pads_of(pl)
        if pl["ref"] == e[0] and e[1] in pads:
            x, y = pads[e[1]]
            return sx(x), sy(y)
    return None


def board_of_end(e):
    if isinstance(e, str):
        return e.split(":")[0]
    return st.board_of_ref().get(e[0])


def top_view(b, ph, rep):
    W, H = sx(st.BW) + 330, sy(0) + 120
    g = Svg(W, H)
    # board, notches, mounting holes
    g.add(f'<rect x="{sx(0):.1f}" y="{sy(st.BH):.1f}" width="{st.BW * K:.1f}" height="{st.BH * K:.1f}" '
          f'fill="#B3202A" stroke="#5a0e12" stroke-width="1.5"/>')
    r = S.val("sb_mhole") / 2 * K
    for x, y in st.NOTCHES:
        g.add(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r:.1f}" fill="#ffffff"/>')
    for x, y in st.MHOLES:
        g.add(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r:.1f}" fill="#ffffff" stroke="#888"/>')
    # strips as connected groups, tinted by net
    hw = 1.15 * K
    for row in range(1, 31):
        for half, (c0, c1) in (("L", ("a", "e")), ("R", ("f", "j"))):
            net = rep[b].get(f"{half}{row}")
            x0, y0 = hole_s(f"{c1}{row}")
            x1, y1 = hole_s(f"{c0}{row}")
            fill = ncol(net) if net else "#E9C46A"
            op = 0.55 if net else 0.35
            g.add(f'<rect x="{x0 - hw:.1f}" y="{y0 - hw:.1f}" width="{2 * hw:.1f}" height="{y1 - y0 + 2 * hw:.1f}" '
                  f'rx="{hw:.1f}" fill="{fill}" fill-opacity="{op}" stroke="#7a5c12" stroke-width="0.6"/>')
    for rail in st.RAIL_Y:
        net = rep[b].get(rail)
        x0, y0 = hole_s(f"{rail}1")
        x1, _ = hole_s(f"{rail}30")
        fill = ncol(net) if net else "#E9C46A"
        g.add(f'<rect x="{x0 - hw:.1f}" y="{y0 - hw:.1f}" width="{x1 - x0 + 2 * hw:.1f}" height="{2 * hw:.1f}" rx="{hw:.1f}" '
              f'fill="{fill}" fill-opacity="{0.55 if net else 0.35}" stroke="#7a5c12" stroke-width="0.6"/>')
        g.text(sx(0) + 6, y0 + 4, rail[1], 12, fill="#fff", weight="bold")
    for h in st.ALL_HOLES:
        x, y = hole_s(h)
        g.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{S.val("sb_hole") / 2 * K:.1f}" fill="#2b2b2b"/>')
    for row in range(1, 31):
        x, _ = hole_s(f"a{row}")
        g.text(x, sy(st.BH) - 6, row, 10, "middle")
        g.text(x, sy(0) + 14, row, 10, "middle")
    for c in "abcdefghij":
        _, y = hole_s(f"{c}1")
        g.text(sx(0) - 8, y + 4, c, 11, "end")
        g.text(sx(st.BW) + 8, y + 4, c, 11)
    # standoffs
    rr = st.STANDOFF_R * K
    for name, x, y in st.STANDOFFS:
        g.add(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{rr:.1f}" fill="#C9A227" fill-opacity="0.35" '
              f'stroke="#8a6d10" stroke-width="1.5" stroke-dasharray="4 2"/>')
        g.add(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{1.5 * K:.1f}" fill="none" stroke="#8a6d10"/>')
    # parts
    for bb, pl in st.placements():
        if bb != b:
            continue
        f = st.FP[pl["fp"]]
        x0, y0, x1, y1 = st.outline_of(pl)
        part = next(p for p in model.PARTS if p["ref"] == pl["ref"])
        g.add(f'<rect x="{sx(x0):.1f}" y="{sy(y1):.1f}" width="{(x1 - x0) * K:.1f}" height="{(y1 - y0) * K:.1f}" '
              f'fill="{f["colour"]}" fill-opacity="0.22" stroke="{f["colour"]}" stroke-width="1.6"/>')
        for bx in st.boxes_of(pl):
            if bx.keepout:
                g.add(f'<rect x="{sx(bx.x0):.1f}" y="{sy(bx.y1):.1f}" width="{(bx.x1 - bx.x0) * K:.1f}" '
                      f'height="{(bx.y1 - bx.y0) * K:.1f}" fill="none" stroke="#555" stroke-width="0.8" stroke-dasharray="3 3"/>')
            elif any(k in bx.what for k in ("jack", "module", "SMA-K", "USB-C rec", "inductor", "JST PH", "MF-R010", "QT socket")):
                g.add(f'<rect x="{sx(bx.x0):.1f}" y="{sy(bx.y1):.1f}" width="{(bx.x1 - bx.x0) * K:.1f}" '
                      f'height="{(bx.y1 - bx.y0) * K:.1f}" fill="{f["colour"]}" fill-opacity="0.18" stroke="#333" stroke-width="0.6"/>')
        cx, cy = sx((x0 + x1) / 2), sy((y0 + y1) / 2)
        g.text(cx, cy, f'{pl["ref"]} {part["value"]}', 11 if (x1 - x0) > 12 else 9, "middle", "#000", "bold")
        for pin, (x, y) in st.pins_of(pl).items():
            net = lc.NET_OF.get((pl["ref"], pin))
            g.add(f'<rect x="{sx(x) - 3.5:.1f}" y="{sy(y) - 3.5:.1f}" width="7" height="7" fill="{ncol(net) if net else "#fff"}" '
                  f'stroke="#000" stroke-width="1"/>')
        for pad, (x, y) in st.pads_of(pl).items():
            net = lc.NET_OF.get((pl["ref"], pad))
            g.add(f'<path d="M{sx(x):.1f},{sy(y) - 5:.1f} l5,5 l-5,5 l-5,-5 z" fill="{ncol(net)}" stroke="#000"/>')
    # conductors on this board
    off = []
    for kind, a, c, side, note in st.WIRES:
        ba, bc = board_of_end(a), board_of_end(c)
        if b not in (ba, bc):
            continue
        pa = end_xy(a) if ba == b else None
        pc = end_xy(c) if bc == b else None
        net = lc.eff_net(ph.get(tuple(a.split(":")), (None, None))) if False else None
        net = net_of_end(a, ph) or net_of_end(c, ph)
        col = ncol(net)
        dash = ' stroke-dasharray="5 3"' if side == "bottom" else ""
        if pa and pc:
            wdt = 2.4 if kind == "jumper" else 2.0
            g.add(f'<line x1="{pa[0]:.1f}" y1="{pa[1]:.1f}" x2="{pc[0]:.1f}" y2="{pc[1]:.1f}" stroke="{col}" '
                  f'stroke-width="{wdt}" stroke-linecap="round"{dash} opacity="0.9"/>')
        else:
            p = pa or pc
            other = c if pa else a
            ob = board_of_end(other)
            dest = (f"{'up' if ob and st.BOARDS.index(ob) > st.BOARDS.index(b) else 'down'} to {ob}"
                    if ob else f"to {other[0]} {other[1]}")
            off.append((p, col, dest, note))
    for p, col, dest, note in off:
        g.add(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="5" fill="none" stroke="{col}" stroke-width="2.2"/>')
        g.add(f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{p[0] + 8:.1f}" y2="{p[1] - 8:.1f}" stroke="{col}" stroke-width="2"/>')
    # front edge
    g.add(f'<line x1="{sx(0):.1f}" y1="{sy(0) + 30:.1f}" x2="{sx(st.BW):.1f}" y2="{sy(0) + 30:.1f}" stroke="#000" stroke-width="2"/>')
    g.text(sx(st.BW / 2), sy(0) + 50, "FRONT EDGE: jacks face the glands (box front wall)", 14, "middle", weight="bold")
    g.text(sx(st.BW / 2), sy(st.BH) - 24, f"{b} {st.ROLE[b]}: top view, 1:1 at {K:g} px/mm, SolderFul SOLDERBREAD#02 "
           f"81.3 x 50.8 mm", 15, "middle", weight="bold")
    # legend
    lx, ly = sx(st.BW) + 40, sy(st.BH) + 4
    g.text(lx, ly, "Nets on this board", 13, weight="bold")
    nets = sorted({n for n in rep[b].values() if n})
    for i, n in enumerate(nets):
        y = ly + 18 + i * 17
        g.add(f'<rect x="{lx}" y="{y - 10}" width="22" height="11" fill="{ncol(n)}" fill-opacity="0.7"/>')
        g.text(lx + 30, y, n, 11)
    y = ly + 30 + len(nets) * 17
    for s_, d in (("solid line", "jumper or wire on top"), ("dashed line", "on the underside"),
                  ("ring + tick", "lead to another board or off the stack"), ("square", "pin in a hole"),
                  ("diamond", "pad with a soldered lead"), ("gold dashed circle", "M3 standoff (hex corners)"),
                  ("grey dashed box", "plug or lead keep-out")):
        g.text(lx, y, f"{s_}: {d}", 10)
        y += 15
    y += 8
    g.text(lx, y, "Off-board leads", 13, weight="bold")
    for p, col, dest, note in off[:22]:
        y += 15
        g.text(lx, y, f"{dest}: {note}"[:52], 9.5, fill=col if col != "#888888" else "#444")
    g.write(OUT_SVG / f"{b}-top.svg", f"{b} {st.ROLE[b]} top view")


def net_of_end(e, ph):
    if isinstance(e, str):
        b, h = e.split(":")
        occ = ph.get((b, h))
        if occ:
            return lc.eff_net(occ)
        return REP[b].get(st.strip_of(h))
    return lc.eff_net(e)


# ------------------------------------------------------------------ build lists
def build_list(b, ph, rep):
    L = [f"# {b} {st.ROLE[b]}: build list", "",
         f"Generated by `layout/drawings.py` from `layout/stack.py`; drawing `drawings/{b}-top.svg`. Holes are named "
         "column letter + row number (`e5`); rails `F+`/`F-` (front edge) and `B+`/`B-` (back edge). The front edge is "
         "the jack side (column a). Every row strip listed carries exactly one net (checked by `layout/layout_checks.py`).", ""]
    ws = [x for x in st.WIRES if b in (board_of_end(x[1]), board_of_end(x[2]))]
    under = [x for x in ws if x[3] == "bottom" and board_of_end(x[1]) == board_of_end(x[2]) == b]
    step = 1
    if under:
        L += [f"## {step}. Underside first (before anything covers these holes)", "",
              "| # | From | To | Net | What |", "|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(under, 1):
            L.append(f"| {i} | {a.split(':')[1]} | {c.split(':')[1]} | {net_of_end(a, ph)} | {note} |")
        L.append("")
        step += 1
    pls = [pl for bb, pl in st.placements() if bb == b]
    pls.sort(key=lambda pl: max((x.z1 for x in st.boxes_of(pl) if not x.keepout), default=0))
    L += [f"## {step}. Parts, lowest first", ""]
    for pl in pls:
        part = next(p for p in model.PARTS if p["ref"] == pl["ref"])
        hmax = max((x.z1 for x in st.boxes_of(pl) if not x.keepout), default=0)
        L.append(f"**{pl['ref']}** {part['value']} ({part['part']}): {pl['note']}; top {hmax:.1f} mm above the board")
        L.append("")
        L.append("| Pin | Hole | Net |")
        L.append("|---|---|---|")
        for pin, xy in st.pins_of(pl).items():
            h = lc.hole_at(xy)
            L.append(f"| {pin} ({lc.PIN[(pl['ref'], pin)][1]}) | {h} | {lc.NET_OF.get((pl['ref'], pin), 'not connected')} |")
        for pad in st.pads_of(pl):
            L.append(f"| {pad} | pad, soldered lead | {lc.eff_net((pl['ref'], pad))} |")
        if pl["ref"] == "U2":
            L.append("| VBUS, VIN-, VIN+ (header 5-7) | pulled out of the header strip before fitting | battery nodes stay off the board |")
        L.append("")
    step += 1
    top = [x for x in ws if x[3] == "top" and board_of_end(x[1]) == board_of_end(x[2]) == b]
    if top:
        L += [f"## {step}. Jumpers and leads on top", "", "| # | From | To | Net | What |", "|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(top, 1):
            fa = a.split(":")[1] if isinstance(a, str) else f"{a[0]} {a[1]} pad"
            fc = c.split(":")[1] if isinstance(c, str) else f"{c[0]} {c[1]} pad"
            L.append(f"| {i} | {fa} | {fc} | {net_of_end(a, ph) or net_of_end(c, ph)} | {note} |")
        L.append("")
        step += 1
    cross = [x for x in ws if board_of_end(x[1]) != board_of_end(x[2])]
    if cross:
        L += [f"## {step}. Leads to other boards and off the stack", "", "| # | Here | There | Net | What |",
              "|---|---|---|---|---|"]
        for i, (kind, a, c, side, note) in enumerate(cross, 1):
            here, there = (a, c) if board_of_end(a) == b else (c, a)
            fh = here.split(":")[1] if isinstance(here, str) else f"{here[0]} {here[1]} pad"
            ft = there if isinstance(there, str) else f"{there[0]} {there[1]}"
            L.append(f"| {i} | {fh} | {ft} | {net_of_end(here, ph) or net_of_end(there, ph)} | {note} |")
        L.append("")
        step += 1
    L += [f"## {step}. Strip map (what every used strip carries)", "", "| Strip | Net | Holes used |", "|---|---|---|"]
    use = defaultdict(list)
    for (bb, h), (ref, pin) in ph.items():
        if bb == b:
            use[st.strip_of(h)].append(f"{h} {ref}.{pin}")
    for kind, a, c, side, note in st.WIRES:
        for e in (a, c):
            if isinstance(e, str) and e.startswith(b + ":"):
                use[st.strip_of(e.split(":")[1])].append(f"{e.split(':')[1]} {kind}")
    def skey(s):
        return (0, int(s[1:]), s[0]) if s[0] in "LR" else (1, 0, s)
    for s_ in sorted(use, key=skey):
        name = (f"row {s_[1:]} {'a-e' if s_[0] == 'L' else 'f-j'}" if s_[0] in "LR" else f"rail {s_}")
        L.append(f"| {name} | {rep[b].get(s_) or 'none (unconnected pin only)'} | {', '.join(sorted(use[s_]))} |")
    L.append("")
    L += ["## Before power", "", "- Continuity: each row strip above to its listed parts; no continuity between neighbouring strips.",
          "- No continuity from +3V3 to GND; on B4, none from any battery lead to any strip."]
    (OUT_MD / f"{b}.md").write_text("\n".join(L) + "\n")


# ------------------------------------------------------------------ side elevation
def elevation(total):
    KZ = 7.0
    t = st.BT
    z_bot = {"B1": S.val("floor")}
    for (lo, hi), gap in st.GAPS.items():
        z_bot[hi] = z_bot[lo] + t + gap
    inside = S.val("box_depth_out") - 2 * S.val("box_wall")
    H = 75 * KZ + 160
    W = M + (st.BW + 30) * KZ + 820
    g = Svg(W, H)
    x0 = M + 15 * KZ

    def X_(x):
        return x0 + x * KZ

    def Z_(z):
        return H - 70 - z * KZ

    # box
    g.add(f'<rect x="{X_(-14):.1f}" y="{Z_(inside):.1f}" width="{(st.BW + 28) * KZ:.1f}" height="{inside * KZ:.1f}" '
          f'fill="#f4f6f8" stroke="#555" stroke-dasharray="6 3"/>')
    g.add(f'<line x1="{X_(-14):.1f}" y1="{Z_(0):.1f}" x2="{X_(st.BW + 14):.1f}" y2="{Z_(0):.1f}" stroke="#000" stroke-width="2"/>')
    g.text(X_(-14), Z_(inside) - 6, f"#905 box inside, {inside:g} mm = 75 outside - 2 x {S.val('box_wall'):g} [TBD-MEASURE]", 12, fill="#555")
    g.add(f'<line x1="{X_(-14):.1f}" y1="{Z_(75 - S.val("box_wall")):.1f}" x2="{X_(st.BW + 14):.1f}" '
          f'y2="{Z_(75 - S.val("box_wall")):.1f}" stroke="#b00" stroke-width="1.2"/>')
    g.text(X_(st.BW + 14), Z_(75 - S.val("box_wall")) - 4, "outside 75 mm (lid top)", 11, "end", "#b00")
    colours = {"B1": "#B3202A", "B2": "#B3202A", "B3": "#B3202A", "B4": "#B3202A"}
    for b in st.BOARDS:
        zb = z_bot[b]
        g.add(f'<rect x="{X_(0):.1f}" y="{Z_(zb + t):.1f}" width="{st.BW * KZ:.1f}" height="{t * KZ:.1f}" fill="{colours[b]}"/>')
        g.text(X_(-2), Z_(zb + t / 2) + 4, f"{b} {st.ROLE[b]}", 12, "end", weight="bold")
        for bb, pl in st.placements():
            if bb != b:
                continue
            col = st.FP[pl["fp"]]["colour"]
            for bx in st.boxes_of(pl):
                if bx.keepout:
                    continue
                zz0 = zb + t + bx.z0 if bx.z0 >= 0 else zb + bx.z0
                zz1 = zb + t + bx.z1 if bx.z1 > 0 else zb
                g.add(f'<rect x="{X_(bx.x0):.1f}" y="{Z_(zz1):.1f}" width="{(bx.x1 - bx.x0) * KZ:.1f}" '
                      f'height="{(zz1 - zz0) * KZ:.1f}" fill="{col}" fill-opacity="0.28" stroke="{col}" stroke-width="0.8"/>')
    # standoffs
    for (lo, hi), gap in list(st.GAPS.items()) + [(("floor", "B1"), S.val("floor"))]:
        zb = z_bot[lo] + t if lo != "floor" else 0
        for name, x, y in st.STANDOFFS:
            r = st.STANDOFF_R
            xa, xb = max(x - r, -r), x + r
            g.add(f'<rect x="{X_(xa):.1f}" y="{Z_(zb + gap):.1f}" width="{(xb - xa) * KZ:.1f}" height="{gap * KZ:.1f}" '
                  f'fill="#C9A227" fill-opacity="0.75" stroke="#7a5c12"/>')
    # crossing wires
    for kind, a, c, side, note in st.WIRES:
        if isinstance(a, str) and isinstance(c, str) and a.split(":")[0] != c.split(":")[0]:
            ba, bc = a.split(":")[0], c.split(":")[0]
            x, _ = st.hole_xy(a.split(":")[1])
            lo, hi = sorted((ba, bc), key=st.BOARDS.index)
            g.add(f'<line x1="{X_(x):.1f}" y1="{Z_(z_bot[lo] + t):.1f}" x2="{X_(x):.1f}" y2="{Z_(z_bot[hi]):.1f}" '
                  f'stroke="#D62728" stroke-width="1.2"/>')
    # dimension column
    dx = X_(st.BW + 22)

    def dim(z0, z1, label, x, colour="#000"):
        g.add(f'<line x1="{x:.1f}" y1="{Z_(z0):.1f}" x2="{x:.1f}" y2="{Z_(z1):.1f}" stroke="{colour}" stroke-width="1"/>')
        for z in (z0, z1):
            g.add(f'<line x1="{x - 5:.1f}" y1="{Z_(z):.1f}" x2="{x + 5:.1f}" y2="{Z_(z):.1f}" stroke="{colour}"/>')
        g.text(x + 9, Z_((z0 + z1) / 2) + 4, label, 11, fill=colour)

    dim(0, S.val("floor"), f"floor {S.label('floor')}", dx)
    for b in st.BOARDS:
        dim(z_bot[b], z_bot[b] + t, f"{b} board {S.label('sb_t')}", dx)
    for (lo, hi), gap in st.GAPS.items():
        top, what = lc.tallest(lo, keepouts=True)
        dim(z_bot[lo] + t, z_bot[hi], f"gap {lo}-{hi} {gap:g} mm (M3 standoff); tallest below {top:.1f} ({what[:34]})", dx)
    top4, what4 = lc.tallest("B4")
    dim(z_bot["B4"] + t, z_bot["B4"] + t + top4, f"above B4 {top4:.1f} ({what4})", dx)
    dim(0, total, f"stack {total:.1f} mm vs box inside {inside:g} [TBD], outside 75", dx + 330, "#b00")
    # callouts: jack on BOB against the 20 mm gap, the socket and pin insertion
    jx = 6.0
    zb2 = z_bot["B1"] + t
    dim(zb2, zb2 + 15.6, "jack on BOB 15.6 = header 2.5 + BOB 1.6 + jack 11.5", X_(jx) - 40, "#0b5394")
    dim(zb2, z_bot["B2"], "", X_(jx) - 52, "#0b5394")
    g.text(X_(jx) - 56, Z_((zb2 + z_bot["B2"]) / 2) + 40, "20 mm gap", 10, "end", "#0b5394")
    sx3 = st.X(st.BUS_ROW0) - 1.27
    z3 = z_bot["B3"] + t
    dim(z3, z3 + S.val("socket_h"), f"socket {S.val('socket_h'):g}", X_(sx3) - 10, "#0b5394")
    dim(z_bot["B4"] - S.val("pin_below"), z_bot["B4"], f"pins {S.val('pin_below'):g} below B4", X_(sx3) - 70, "#0b5394")
    ins = S.val("pin_below") - (st.GAPS[("B3", "B4")] - S.val("socket_h"))
    g.text(X_(sx3) - 70, Z_(z3 - 3), f"insertion {ins:.1f} mm", 11, fill="#0b5394")
    g.text(W / 2, 26, "TX stack r1: side elevation from the front, to scale (7 px/mm). Gold: M3 standoffs. Red verticals: "
           "soldered 22 AWG crossings (B1-B2, B2-B3).", 14, "middle", weight="bold")
    g.text(W / 2, 46, "Brief's gaps 20/10/10 do not clear the B2 jacks (15.6 mm); B3-B4 stays 10 mm because the Wio-E5 "
           "is soldered low, not socketed.", 12, "middle")
    g.write(OUT_SVG / "stack-elevation.svg", "TX stack r1 side elevation")


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


def main():
    OUT_SVG.mkdir(exist_ok=True)
    OUT_MD.mkdir(exist_ok=True)
    lc.FAILS.clear()
    ph, total = lc.run()
    if lc.FAILS:
        sys.exit("layout checks fail; fix them first:\n" + "\n".join(lc.FAILS))
    REP.update(lc.strip_report(ph))
    for b in st.BOARDS:
        top_view(b, ph, REP)
        build_list(b, ph, REP)
    elevation(total)
    print("wrote drawings/B1..B4-top.svg, drawings/stack-elevation.svg, build/B1..B4.md")
    if "--png" in sys.argv:
        PNG = ROOT / "renders"
        PNG.mkdir(exist_ok=True)
        bad = [svg.name for svg in sorted(OUT_SVG.glob("*.svg")) if not svg_png(svg, PNG / (svg.stem + ".png"))]
        if bad:
            sys.exit("svg->png failed: " + ", ".join(bad))
        print("wrote renders/*.png for every drawings/*.svg")


if __name__ == "__main__":
    main()
