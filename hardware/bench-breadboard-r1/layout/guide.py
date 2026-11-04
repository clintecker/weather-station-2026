"""Bench r1 build guide: one small action per page, each with a zoomed drawing, as a PDF.

Every drawing is generated from build.py (holes, parts, conductors) and routing.py (Dupont paths), so
the guide cannot drift from the checked plan. New items glow; what is already built is drawn faded.
Writes guide/wiring-guide.html and guide/wiring-guide.pdf (headless Chrome prints the PDF).
Run: python3 guide.py
"""
import html
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image

import build as b
import routing
from kicad_layout import BOJACK, dupont_colour

OUT = b.HERE / "guide"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GLOW = "#FFC400"
PHASE_COLOUR = {"Get ready": "#5B6770", "Prep": "#8A6D1E", "Boards": "#3E7CB1", "BB2": "#2E8B57", "BB1": "#C0612B",
                "BB3": "#7A4FB0", "Plate": "#3E7CB1", "Duponts": "#B0306A", "Power island": "#B8322A",
                "QT cables": "#1F7A8C", "Finish": "#2E8B57"}
NUCLEO_PIN = {"CN5.9": "D14 SDA", "CN5.10": "D15 SCL", "CN9.5": "D4", "CN9.6": "D5", "CN9.7": "D6",
              "CN8.1": "A0", "CN8.2": "A1", "CN8.3": "A2", "CN8.4": "A3", "CN6.4": "3V3", "CN6.6": "GND",
              "CN6.7": "GND", "CN5.7": "GND", "CN7.16": "3V3", "CN10.20": "GND", "CN10.11": "PA5",
              "CN10.15": "PA7", "CN10.17": "PA4", "CN10.21": "PC2", "CN10.23": "PC1"}
# Never a supply (decision record N1, N3; docs/hardware/bench-station-wiring.md): taped "NO 5V" in prep.
NO_5V = ("CN6.5", "CN6.8", "CN7.6", "CN7.18", "CN7.24", "CN10.8")
# Morpho pins one slip from a wire's pin, and what landing there does (UM2592 Table 18).
MORPHO_TRAPS = {"CN7.16": "CN7.18 next to it is <b>5 V</b> (taped); CN7.7 (BOOT0) and CN7.14 (RESET) in the other row stop the board running"}
BAND = ["#1A1A1A", "#7B4A1E", "#D22B2B", "#F07A1A", "#F2D21B", "#2E9E48", "#2E62C9", "#8A4FC0", "#8C8C8C", "#F4F4F4"]
BANDS = {"10k 1%": ([1, 0, 0, 2], "#7B4A1E", "brown, black, black, red, brown"),
         "10k": ([1, 0, 3], "#C9A43A", "brown, black, orange, gold"),
         "1M 1%": ([1, 0, 0, 4], "#7B4A1E", "brown, black, black, yellow, brown")}
MODULE_FILL = {"NUCLEO": "#E9ECEF", "WAGO3": "#D3D8DD", "WAGO5": "#D3D8DD", "PACK": "#6F7F94", "OLED": "#20252B"}
WHAT = {"U1": "the #4755 charger", "U2": "INA228 0x40 (battery)", "U3": "INA228 0x41 (load)",
        "U4": "INA228 0x45 (solar)", "U5": "INA228 0x48 (USB-C)", "U6": "the MAX17048 gauge",
        "U7": "the S7V8F3 regulator", "J1": "the RJ11 wind breakout", "J2": "the RJ11 rain breakout",
        "DS1": "the OLED"}
LIFT = {"U1": "Lift JP? no", }


def e(s):
    return html.escape(str(s), quote=True)


def hole(h):
    lab = b.label(h)
    cls = "h gnd" if lab.startswith("GND") else ("h v33" if lab.startswith("3V3") else "h")
    return f'<span class="{cls}">{e(lab)}</span>'


def short(h):
    return b.label(h)


def rail_note(*holes):
    rails = [h for h in holes if b.parse(h)[1] in b.RAILS]
    return "".join(f"<br><span class='why'>{e(b.label(h))} = {e(b.rail_words(h))}</span>" for h in rails)


def num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ what is on each board, as drawable items
def board_items(bd):
    """Items in build order: (key, kind, data). kind: jumper, leaded, module."""
    jumpers = sorted((c for c in b.CONDUCTORS if c[0] == "jumper" and c[1].startswith(bd + ":")),
                     key=lambda c: -b.parse(c[1])[2])
    leaded = {}
    for (ref, pin), h in b.ON_BB.items():
        if h.startswith(bd + ":") and ref not in b.PLACE and ref not in ("W1", "W2", "W3", "RT1"):
            leaded.setdefault(ref, {})[pin] = h
    mods = [r for r, pl in b.PLACE.items() if "seat" in pl and pl["seat"][1].startswith(bd + ":")]
    items = [(f"J:{c[1]}", "jumper", c) for c in jumpers]
    items += [(f"P:{r}", "leaded", (r, leaded[r])) for r in sorted(leaded, key=lambda r: -max(b.parse(h)[2] for h in leaded[r].values()))]
    items += [(f"M:{r}", "module", r) for r in sorted(mods, key=lambda r: -b.parse(b.PLACE[r]["seat"][1])[2])]
    return items


def item_holes(kind, data):
    if kind == "jumper":
        return [data[1], data[2]]
    if kind == "leaded":
        return list(data[1].values())
    if kind == "module":
        return [h for (r, _p), h in b.ON_BB.items() if r == data]
    if kind == "end":
        return [data[0]]
    return []


# ------------------------------------------------------------------ SVG: one breadboard, zoomed to some columns
def bxy(h):
    """Hole position in its board's own frame (mm)."""
    bd = h.split(":")[0]
    x, y, _r, _c = b.hole_xy(h)
    return x - b.BOARDS[bd][0], y - b.BOARDS[bd][1]


def col_x(c):
    return b.COL_MARGIN + (b.NCOL - c) * b.P


def draw_resistor(p1, p2, value, glow):
    (x1, y1), (x2, y2) = p1, p2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    digits, tol, _txt = BANDS.get(value, ([1, 0, 3], "#C9A43A", ""))
    bands = "".join(f'<rect x="{-2.3 + i * 0.95:.2f}" y="-1.05" width="0.5" height="2.1" fill="{BAND[d]}"/>'
                    for i, d in enumerate(digits))
    halo = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GLOW}" stroke-width="3.2" stroke-linecap="round" opacity=".55"/>'
            if glow else "")
    return (f'{halo}<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9AA0A6" stroke-width=".45"/>'
            f'<g transform="translate({mx:.2f},{my:.2f}) rotate({ang:.1f})">'
            f'<rect x="-3.2" y="-1.15" width="6.4" height="2.3" rx="1" fill="#E3C99A" stroke="#7A6440" stroke-width=".2"/>'
            f'{bands}<rect x="2.05" y="-1.05" width="0.5" height="2.1" fill="{tol}"/></g>')


def draw_leaded(ref, pins, glow):
    pts = {p: bxy(h) for p, h in pins.items()}
    val = b.PART[ref]["value"]
    if ref.startswith("R"):
        return draw_resistor(pts["1"], pts["2"], val, glow)
    (x1, y1), (x2, y2) = list(pts.values())[:2]
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    halo = f'<circle cx="{mx}" cy="{my}" r="3.4" fill="{GLOW}" opacity=".5"/>' if glow else ""
    legs = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9AA0A6" stroke-width=".45"/>'
    if ref.startswith("JP"):
        return (f'{halo}<rect x="{min(x1, x2) - 1.27:.2f}" y="{my - 1.27:.2f}" width="{abs(x2 - x1) + 2.54:.2f}" height="2.54" '
                f'fill="#1E1E1E"/>' + "".join(f'<rect x="{x - .35:.2f}" y="{y - .35:.2f}" width=".7" height=".7" fill="#D4AF37"/>'
                                               for x, y in pts.values()))
    if val.startswith("220"):
        nx, ny = pts["-"]
        return (f'{halo}{legs}<circle cx="{mx}" cy="{my - 2.6}" r="2.6" fill="#2F55B5" stroke="#16306E" stroke-width=".25"/>'
                f'<path d="M{mx - 2.6},{my - 2.6} A2.6,2.6 0 0 1 {mx - 1.2},{my - 4.9} L{mx - .6},{my - 2.6} Z" fill="#C9D3EE"/>'
                f'<text x="{nx}" y="{ny + 2.6}" class="pm">−</text><text x="{pts["+"][0]}" y="{pts["+"][1] + 2.6}" class="pm">+</text>')
    return (f'{halo}{legs}<ellipse cx="{mx}" cy="{my - 1.6}" rx="1.9" ry="1.5" fill="#E8A33D" stroke="#8C5A14" stroke-width=".2"/>'
            f'<text x="{mx}" y="{my - 1.25}" class="cap">104</text>')


def draw_module(ref, glow, pin_labels=True):
    x, y, w, h = b.outline(ref)
    bd = b.PLACE[ref]["seat"][1].split(":")[0]
    ox, oy = b.BOARDS[bd]
    x, y = x - ox, y - oy
    kind = b.PLACE[ref]["kind"]
    fill = MODULE_FILL.get(kind, "#1E3550")
    out = [f'<rect x="{x - 1.2:.2f}" y="{y - 1.2:.2f}" width="{w + 2.4:.2f}" height="{h + 2.4:.2f}" rx="2" fill="{GLOW}" opacity=".55"/>' if glow else "",
           f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="1.2" fill="{fill}" opacity=".93" stroke="#0B1520" stroke-width=".3"/>']
    pins = [(p, h_) for (r, p), h_ in b.ON_BB.items() if r == ref]
    cy = y + h / 2
    for p, hl in pins:
        px, py = bxy(hl)
        out.append(f'<rect x="{px - .55:.2f}" y="{py - .55:.2f}" width="1.1" height="1.1" fill="#D4AF37" stroke="#5A4510" stroke-width=".15"/>')
        if pin_labels:
            label = p.replace("H.", "").replace("GND1", "GND").replace("GND2", "GND").replace("GND3", "GND")
            ty = py + (1.3 if cy > py else -1.3)
            anchor = "end" if cy > py else "start"
            out.append(f'<text x="{px + .45:.2f}" y="{ty:.2f}" class="pin" text-anchor="{anchor}" '
                       f'transform="rotate(-90 {px + .45:.2f} {ty:.2f})">{e(label)}</text>')
    tx = min(max(x + w / 2, 4), b.BB_W - 4)
    ty = cy + (4 if cy > b.BB_H / 2 else -3) if 0 < cy < b.BB_H else (y + h - 3 if cy < 0 else y + 4)
    ty = min(max(cy, y + 3.5), y + h - 2)
    out.append(f'<text x="{x + w / 2:.2f}" y="{ty:.2f}" class="mod">{e(ref)} · {e(b.PART[ref]["value"])}</text>')
    return "".join(out)


def draw_item(kind, data, glow):
    if kind == "jumper":
        (x1, y1), (x2, y2) = bxy(data[1]), bxy(data[2])
        col = BOJACK.get(b.span(data[1], data[2]), "#888")
        halo = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GLOW}" stroke-width="3.4" stroke-linecap="round" opacity=".6"/>'
                if glow else "")
        return (f'{halo}<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#222" stroke-width="1.45" stroke-linecap="round"/>'
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="1.1" stroke-linecap="round"/>')
    if kind == "leaded":
        return draw_leaded(data[0], data[1], glow)
    if kind == "module":
        return draw_module(data, glow)
    if kind == "end":
        h, colour, tag = data
        x, y = bxy(h)
        halo = f'<circle cx="{x}" cy="{y}" r="2.6" fill="{GLOW}" opacity=".7"/>' if glow else ""
        return (f'{halo}<circle cx="{x}" cy="{y}" r="1.05" fill="{colour}" stroke="#111" stroke-width=".3"/>'
                f'<rect x="{x - .6}" y="{y - .6}" width="1.2" height="1.2" fill="#555"/>')
    return ""


def used_holes(bd):
    return {h for h in b.occupants() if h.startswith(bd + ":")}


def board_svg(bd, cols, new, ghost, tags=(), mark=()):
    """Zoomed drawing of columns cols=(hi, lo) of board bd. new/ghost: lists of (kind, data)."""
    hi, lo = max(cols), min(cols)
    hi, lo = min(hi + 2, b.NCOL), max(lo - 2, 1)
    x0, x1 = col_x(hi) - 3.2, col_x(lo) + 3.2
    drawn = {h for k, d in new for h in item_holes(k, d)}       # faded earlier items may sit under the leader
    flip = set()
    # two tags in one column on one side would sit side by side with a slanted leader; send the one nearer the
    # far side across instead, on a straight vertical leader, when nothing new in this step lies in its way
    for t1 in tags:
        for t2 in tags:
            (xa, ya), (xb, yb) = bxy(t1[0]), bxy(t2[0])
            if t1 is t2 or len(t1) > 3 or len(t2) > 3 or abs(xa - xb) > .1 or (ya < b.BB_H / 2) != (yb < b.BB_H / 2):
                continue
            bottom = ya > b.BB_H / 2
            near_far = t1 if (ya < yb) == bottom else None      # t1 is the one nearer the opposite edge
            if near_far is None:
                continue
            _bd, row, col = b.parse(t1[0])
            k = b.ROW_ORDER.index(row)
            rows = b.ROW_ORDER[:k] if bottom else b.ROW_ORDER[k + 1:]
            path = [f"{bd}:{r}{col}" for r in rows if b.hole_exists(f"{bd}:{r}{col}")]
            if not any(h in drawn for h in path):
                flip.add(t1[0])
    side_of = lambda t: (t[3] if len(t) > 3 else  # noqa: E731
                         ("top" if (bxy(t[0])[1] < b.BB_H / 2) != (t[0] in flip) else "bottom"))
    two = any(sum(1.62 * len(t[1]) + 3.4 for t in tags if side_of(t) == sd) > (x1 - x0) - 1 for sd in ("top", "bottom"))
    pad = 15.0 if two else 9.0
    y0, y1 = -pad, b.BB_H + pad
    parts = [f'<rect x="{x0}" y="0" width="{x1 - x0}" height="{b.BB_H}" fill="#FAFAF7" stroke="#C9CCC4" stroke-width=".3"/>',
             f'<rect x="{x0}" y="{b.ROW_Y["e"] + 2.2}" width="{x1 - x0}" height="{b.ROW_Y["f"] - b.ROW_Y["e"] - 4.4}" fill="#E4E5DF"/>']
    for row, colour, dy in (("T+", "#D22B2B", -1.6), ("T-", "#2E62C9", 1.6), ("B+", "#D22B2B", -1.6), ("B-", "#2E62C9", 1.6)):
        yy = b.ROW_Y[row] + dy
        parts.append(f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" stroke="{colour}" stroke-width=".35"/>')
    used = used_holes(bd)
    for row in b.ROW_ORDER:
        for c in range(lo, hi + 1):
            h = f"{bd}:{row}{c}"
            if not b.hole_exists(h):
                continue
            x, y = bxy(h)
            parts.append(f'<rect x="{x - .5:.2f}" y="{y - .5:.2f}" width="1" height="1" fill="{"#6B6F73" if h in used else "#9EA2A6"}"/>')
    for c in range(lo, hi + 1):
        x = col_x(c)
        cls = "cn b5" if c % 5 == 0 else "cn"
        parts.append(f'<text x="{x:.2f}" y="{b.ROW_Y["a"] - 2.3:.2f}" class="{cls}">{c}</text>')
        parts.append(f'<text x="{x:.2f}" y="{b.ROW_Y["j"] + 3.2:.2f}" class="{cls}">{c}</text>')
    for row in "abcdefghij":
        y = b.ROW_Y[row]
        parts.append(f'<text x="{x0 + 1.3:.2f}" y="{y + .55:.2f}" class="rl">{row}</text>')
        parts.append(f'<text x="{x1 - 1.3:.2f}" y="{y + .55:.2f}" class="rl">{row}</text>')
    for row, s in (("T+", "+"), ("T-", "−"), ("B+", "+"), ("B-", "−")):
        y = b.ROW_Y[row]
        col = "#D22B2B" if s == "+" else "#2E62C9"
        parts.append(f'<text x="{x0 + 1.3:.2f}" y="{y + .6:.2f}" class="rl" fill="{col}">{s}</text>')
    cid = f"c{len(STEPS)}-{bd}-{hi}-{lo}"
    parts.append(f'<clipPath id="{cid}"><rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}"/></clipPath>')
    parts.append(f'<g clip-path="url(#{cid})"><g opacity=".28">' + "".join(draw_item(k, d, False) for k, d in ghost) + "</g>"
                 + "".join(draw_item(k, d, True) for k, d in new) + "</g>")
    for h in mark:
        x, y = bxy(h)
        parts.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="none" stroke="#E0002A" stroke-width=".45"/>')
    # tags: hole label boxes with leader lines, above for the top half, below for the bottom. Each side is one row
    # fanned out in hole order (so leader lines never cross); a second row only when one row cannot hold them.
    for sd in ("top", "bottom"):
        # in hole order; within one column the inner hole first, so its label goes left, clear of the outer hole
        mine = sorted((t for t in tags if side_of(t) == sd),
                      key=lambda t: (bxy(t[0])[0], bxy(t[0])[1] if sd == "bottom" else -bxy(t[0])[1]))
        xs = [round(bxy(t[0])[0], 1) for t in mine]
        if not mine:
            continue
        ws = [1.62 * len(t[1]) + 2.4 for t in mine]
        nrows = 1 if sum(ws) + len(ws) <= (x1 - x0) - 1 else 2
        for r in range(nrows):
            row = [(t, w) for k, (t, w) in enumerate(zip(mine, ws)) if k % nrows == r]
            pos, end = [], x0 + .5
            for t, w in row:                         # sweep right: as near the hole as the previous tag allows
                hx = bxy(t[0])[0]
                shared = xs.count(round(hx, 1)) > 1 and [round(bxy(u[0])[0], 1) for u, _w in row].index(round(hx, 1)) == len(pos)
                tx = max(hx - w - .5 if shared else hx - w / 2, end)
                pos.append(tx)
                end = tx + w + 1
            over = end - 1 - (x1 - .5)
            if over > 0:                             # sweep back from the right edge
                lim = x1 - .5
                for k in range(len(row) - 1, -1, -1):
                    pos[k] = min(pos[k], lim - row[k][1])
                    lim = pos[k] - 1
            ty = (y0 + 1 + 6 * (nrows - 1 - r)) if sd == "top" else (y1 - 6 - 6 * (nrows - 1 - r))
            ly = ty + 5 if sd == "top" else ty
            # untangle: swap neighbours whose leader lines cross (holes in one column fan out the wrong way round)
            centres = [tx + w / 2 for (_t, w), tx in zip(row, pos)]
            for _ in range(len(row)):
                for k in range(len(row) - 1):
                    (ta, wa), (tb, wb) = row[k], row[k + 1]
                    if crosses(bxy(ta[0]), (centres[k], ly), bxy(tb[0]), (centres[k + 1], ly)) and abs(wa - wb) < .01:
                        row[k], row[k + 1] = row[k + 1], row[k]
            for (t, w), tx in zip(row, pos):
                h, text, colour = t[:3]
                x, y = bxy(h)
                cx = tx + w / 2                      # leader: 45 degrees off the pin, then straight to the label
                d = min(abs(cx - x), max(abs(ly - y) - 3, 0))
                kx, ky = x + math.copysign(d, cx - x), y + (d if sd == "bottom" else -d)
                parts.append(f'<polyline points="{x},{y} {kx:.2f},{ky:.2f} {cx:.2f},{ly:.2f}" fill="none" stroke="{colour}" stroke-width=".35"/>'
                             f'<rect x="{tx:.2f}" y="{ty:.2f}" width="{w:.2f}" height="5" rx="1" fill="#fff" stroke="{colour}" stroke-width=".4"/>'
                             f'<text x="{tx + w / 2:.2f}" y="{ty + 3.55:.2f}" class="tag">{e(text)}</text>')
    vb = f"{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}"
    return f'<svg class="fig" viewBox="{vb}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


def crosses(p1, p2, q1, q2):
    """True if segment p1-p2 properly crosses segment q1-q2."""
    def side(a, b_, c):
        return (b_[0] - a[0]) * (c[1] - a[1]) - (b_[1] - a[1]) * (c[0] - a[0])
    return side(p1, p2, q1) * side(p1, p2, q2) < 0 and side(q1, q2, p1) * side(q1, q2, p2) < 0


def locator_svg(bd, cols):
    hi, lo = min(max(cols) + 2, b.NCOL), max(min(cols) - 2, 1)
    x0, x1 = col_x(hi) - 3.2, col_x(lo) + 3.2
    used = used_holes(bd)
    dots = "".join(f'<rect x="{bxy(h)[0] - .7:.2f}" y="{bxy(h)[1] - .7:.2f}" width="1.4" height="1.4" fill="#8A8F94"/>' for h in used)
    return (f'<svg class="loc" viewBox="-2 -2 {b.BB_W + 4} {b.BB_H + 4}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect x="0" y="0" width="{b.BB_W}" height="{b.BB_H}" rx="2" fill="#FAFAF7" stroke="#9EA2A6" stroke-width=".8"/>'
            f'{dots}<rect x="{x0:.2f}" y="-1" width="{x1 - x0:.2f}" height="{b.BB_H + 2}" fill="{GLOW}" opacity=".35" stroke="#E0A000" stroke-width="1"/>'
            f'<text x="{b.BB_W / 2}" y="{b.BB_H / 2 + 4}" class="locl">{bd}</text></svg>')


# ------------------------------------------------------------------ SVG: the plate
def plate_svg(focus=None, glow_refs=(), lines=(), show_parts=True, boards_glow=(), pins=(), only_boards=False, keep=None):
    """lines: (points, colour, width, dashed). pins: (x, y, label) callouts, or (x, y, label, (dx, dy)) to push the
    label out that way. focus: (x0, y0, x1, y1) crop; None fits the lines and labels. keep: refs drawn at full strength."""
    out = [f'<rect x="0" y="0" width="{b.PLATE_W}" height="{b.PLATE_H}" rx="3" fill="#F1EFE8" stroke="#8C8A80" stroke-width=".8"/>']
    for bd, (x, y) in b.BOARDS.items():
        if bd in boards_glow:
            out.append(f'<rect x="{x - 2}" y="{y - 2}" width="{b.BB_W + 4}" height="{b.BB_H + 4}" rx="3" fill="{GLOW}" opacity=".6"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{b.BB_W}" height="{b.BB_H}" rx="2" fill="#FBFBF8" stroke="#A5A8A0" stroke-width=".5"/>'
                   f'<rect x="{x}" y="{y + b.ROW_Y["e"] + 2.2}" width="{b.BB_W}" height="3.2" fill="#E4E5DF"/>'
                   f'<text x="{x + b.BB_W / 2}" y="{y + b.BB_H / 2 + 1.2}" class="bbl">{bd}</text>'
                   f'<text x="{x + 2}" y="{y + 4}" class="tiny">62</text><text x="{x + b.BB_W - 2}" y="{y + 4}" class="tiny" text-anchor="end">1</text>')
    if show_parts and not only_boards:
        for ref, pl in b.PLACE.items():
            x, y, w, h = b.outline(ref)
            kind = pl["kind"]
            if ref in glow_refs:
                out.append(f'<rect x="{x - 2}" y="{y - 2}" width="{w + 4}" height="{h + 4}" rx="2.5" fill="{GLOW}" opacity=".7"/>')
            fill = MODULE_FILL.get(kind, "#1E3550")
            tcol = "#222" if kind in ("NUCLEO", "WAGO3", "WAGO5") else "#fff"
            op = ".92" if keep is None or ref in keep else ".3"
            out.append(f'<g opacity="{op}"><rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="1.2" fill="{fill}" stroke="#222" stroke-width=".35"/>')
            if kind in ("WAGO3", "WAGO5"):
                for p in b.LOCAL[kind]:
                    px, py = b.local_xy(ref, p)
                    out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="1.9" fill="#F07A1A" stroke="#7A3A00" stroke-width=".3"/>'
                               f'<text x="{px:.2f}" y="{py + 1.1:.2f}" class="lever">{p}</text>')
            fs = 3.2 if w > 30 else 2.4
            out.append(f'<text x="{x + w / 2:.2f}" y="{y + h / 2 + (0 if kind not in ("WAGO3", "WAGO5") else 4):.2f}" class="pl" '
                       f'style="font-size:{fs}px" fill="{tcol}">{e(ref)}</text>')
            out.append("</g>")
    for pts, colour, width, dashed in lines:
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        dash = ' stroke-dasharray="3 2"' if dashed else ""
        out.append((f'<path d="{d}" fill="none" stroke="#111" stroke-width="{width + .8}" stroke-linecap="round" stroke-linejoin="round" opacity=".55"{dash}/>'
                    if width >= 1 else "") +
                   f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
    boxes = []
    for pn in pins:
        x, y, label = pn[:3]
        w, h = 1.75 * len(label) + 3, 5.6
        if len(pn) > 3:                       # label pushed out beyond the wire's end, leader line back to the ring
            dx, dy = pn[3]
            cx, cy = x + dx * (w / 2 + 6), y + dy * (h / 2 + 6)
            rx, ry = cx - w / 2, cy - h / 2
            out.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{cx:.2f}" y2="{cy:.2f}" stroke="#E0002A" stroke-width=".45"/>')
        else:
            rx, ry = x + 3, y - 7.5
        boxes.append((rx, ry, rx + w, ry + h))
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.7" fill="none" stroke="#E0002A" stroke-width=".7"/>'
                   f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{w:.2f}" height="{h:.2f}" rx="1.2" fill="#fff" stroke="#E0002A" stroke-width=".5"/>'
                   f'<text x="{rx + w / 2:.2f}" y="{ry + 4:.2f}" class="ptag">{e(label)}</text>')
    if isinstance(focus, list):               # crop to these points and the labels
        pts = focus + [(bx[0], bx[1]) for bx in boxes] + [(bx[2], bx[3]) for bx in boxes]
        focus = bbox(pts, margin=8, min_w=80, min_h=55)
    if focus:
        x0, y0, x1, y1 = focus
    else:
        x0, y0, x1, y1 = -4, -4, b.PLATE_W + 4, b.PLATE_H + 4
    return (f'<svg class="fig" viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}" xmlns="http://www.w3.org/2000/svg">'
            f'{"".join(out)}</svg>')


def bbox(points, margin=14, min_w=90, min_h=60):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
    if x1 - x0 < min_w:
        cx = (x0 + x1) / 2
        x0, x1 = cx - min_w / 2, cx + min_w / 2
    if y1 - y0 < min_h:
        cy = (y0 + y1) / 2
        y0, y1 = cy - min_h / 2, cy + min_h / 2
    return x0, y0, x1, y1


def morpho_row(pin):
    """'inner' or 'outer': which of a morpho header's two rows holds the pin, from the model."""
    x = b.LOCAL["NUCLEO"][pin][0]
    xs = {v[0] for k, v in b.LOCAL["NUCLEO"].items() if k.startswith(pin.split(".")[0] + ".")}
    edge = 0 if pin.startswith("CN7") else b.SIZE["NUCLEO"][0]
    return "outer" if abs(x - edge) == min(abs(v - edge) for v in xs) else "inner"


def nucleo_svg(pin=None, avoid=()):
    """The TX NUCLEO with every header pin, the target pin ringed and the avoid pins crossed out."""
    x, y, w, h = b.outline("A1")
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="#E9ECEF" stroke="#333" stroke-width=".5"/>']
    groups = {}
    for p in b.LOCAL["NUCLEO"]:
        if not p.startswith("CN"):
            continue
        px, py = b.local_xy("A1", p)
        groups.setdefault(p.split(".")[0], []).append((px, py))
        socket = p.split(".")[0] in ("CN5", "CN6", "CN8", "CN9")
        out.append(f'<rect x="{px - .9:.2f}" y="{py - .9:.2f}" width="1.8" height="1.8" '
                   f'fill="{"#1A1A1A" if socket else "#D4AF37"}" stroke="#333" stroke-width=".15"/>')
    for g, pts in groups.items():
        gx = sum(p[0] for p in pts) / len(pts)
        gy = min(p[1] for p in pts) - 2.2
        out.append(f'<text x="{gx:.2f}" y="{gy:.2f}" class="cnl">{g}</text>')
    ux, uy = b.local_xy("A1", "USB.VBUS")
    out.append(f'<rect x="{ux - 4}" y="{uy - 4}" width="8" height="8" fill="#9AA0A6" stroke="#333" stroke-width=".3"/>'
               f'<text x="{ux - 6}" y="{uy + 1}" class="tiny" text-anchor="end">ST-LINK USB</text>')
    for a in avoid:
        ax, ay = b.local_xy("A1", a)
        out.append(f'<path d="M{ax - 1.6:.2f},{ay - 1.6:.2f}L{ax + 1.6:.2f},{ay + 1.6:.2f}M{ax - 1.6:.2f},{ay + 1.6:.2f}'
                   f'L{ax + 1.6:.2f},{ay - 1.6:.2f}" stroke="#E0002A" stroke-width=".7"/>')
    if pin is None:
        return (f'<svg class="fig" viewBox="{x - 10:.1f} {y - 14:.1f} {w + 20:.1f} {h + 22:.1f}" xmlns="http://www.w3.org/2000/svg">'
                f'{"".join(out)}</svg>')
    px, py = b.local_xy("A1", pin)
    label = f"{pin.replace('.', ' pin ')}  {NUCLEO_PIN.get(pin, '')}"
    out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.2" fill="{GLOW}" opacity=".7"/>'
               f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.2" fill="none" stroke="#E0002A" stroke-width=".7"/>')
    tw = 1.9 * len(label) + 3
    tx = min(px + 4, x + w - tw)
    out.append(f'<rect x="{tx:.2f}" y="{py - 9:.2f}" width="{tw:.2f}" height="6" rx="1.2" fill="#fff" stroke="#E0002A" stroke-width=".5"/>'
               f'<text x="{tx + tw / 2:.2f}" y="{py - 4.7:.2f}" class="ptag">{e(label)}</text>')
    return (f'<svg class="fig" viewBox="{x - 10:.1f} {y - 14:.1f} {w + 20:.1f} {h + 22:.1f}" xmlns="http://www.w3.org/2000/svg">'
            f'{"".join(out)}</svg>')


# ------------------------------------------------------------------ steps
STEPS = []


def step(phase, title, do, need=(), check=(), tip=None, figs=(), cap=(), layout="stack"):
    STEPS.append(dict(phase=phase, title=title, do=list(do), need=list(need), check=list(check), tip=tip,
                      figs=list(figs), cap=list(cap), layout=layout))


def cols_of(holes, min_w=26):
    cs = [b.parse(h)[2] for h in holes]
    hi, lo = max(cs), min(cs)
    while hi - lo < min_w:
        hi, lo = min(hi + 1, b.NCOL), max(lo - 1, 1)
    return hi, lo


def overhang(ref):
    x, y, w, h = b.outline(ref)
    bd = b.PLACE[ref]["seat"][1].split(":")[0]
    oy = b.BOARDS[bd][1]
    if y < oy - 1:
        return "over the top edge (the back)"
    if y + h > oy + b.BB_H + 1:
        return "over the bottom edge (the front)"
    sy = b.hole_xy(b.PLACE[ref]["seat"][1])[1]
    return f"flat on the breadboard, its body toward row {'a' if y + h / 2 < sy else 'j'}"


def jumper_text(c):
    s = b.span(c[1], c[2])
    return f"one <b>{s}-hole</b> jumper ({num(s * b.P)} mm): {hole(c[1])} to {hole(c[2])}{rail_note(c[1], c[2])}"


def resistor_words(val):
    return BANDS.get(val, (None, None, ""))[2]


def board_phase(bd, intro):
    items = board_items(bd)
    done = []
    total = sum(1 for _ in items)
    step(bd, f"{bd}: {b.BOARD_ROLE[bd]}", [intro], figs=[plate_svg(boards_glow=(bd,), only_boards=True)],
         cap=[f"{bd} on the plate"], tip="Turn the board so the printed 1 is on the right and row a is at the top.")
    # jumpers in small clusters
    jumpers = [it for it in items if it[1] == "jumper"]
    clusters, cur = [], []
    for it in jumpers:
        c0 = b.parse(it[2][1])[2]
        if cur and (len(cur) == 3 or abs(b.parse(cur[0][2][1])[2] - c0) > 9):
            clusters.append(cur)
            cur = []
        cur.append(it)
    if cur:
        clusters.append(cur)
    for n, cl in enumerate(clusters, 1):
        holes = [h for it in cl for h in item_holes("jumper", it[2])]
        cols = cols_of(holes)
        lines = [jumper_text(it[2]) + f" <span class='why'>({e(it[2][3])})</span>" for it in cl]
        spans = sorted({b.span(it[2][1], it[2][2]) for it in cl})
        step(bd, f"Jumpers, set {n} of {len(clusters)}", lines,
             need=[f"{sum(1 for it in cl if b.span(it[2][1], it[2][2]) == s)} × {s}-hole jumper" for s in spans],
             check=["Each jumper lies flat and both legs are fully in."],
             figs=[board_svg(bd, cols, [(it[1], it[2]) for it in cl], [(k, d) for _k, k, d in done],
                             tags=[(h, short(h), "#333") for h in holes]), locator_svg(bd, cols)],
             cap=[f"{bd}, columns {cols[0]} to {cols[1]}", "where you are on the board"])
        done += cl
    for it in [i for i in items if i[1] == "leaded"]:
        ref, pins = it[2]
        val = b.PART[ref]["value"]
        holes = list(pins.values())
        cols = cols_of(holes)
        if ref.startswith("R"):
            what = f"resistor <b>{ref}</b>, {e(val)}"
            do = [f"Find a {e(val)} resistor. Its bands read <b>{resistor_words(val)}</b>.",
                  f"Bend both legs down. One leg in {hole(pins['1'])}, the other in {hole(pins['2'])}. Either way round.",
                  "Push it down so it lies flat on the board."]
            chk = ["The holes between its legs stay empty: that is normal."]
        elif ref.startswith("JP"):
            what = f"2-pin header <b>{ref}</b> ({e(val)})"
            do = [f"Push a 2-pin header into {hole(pins['1'])} and {hole(pins['2'])}.", "No jumper cap yet: that comes at the end."]
            chk = []
        elif val.startswith("220"):
            what = f"capacitor <b>{ref}</b>, {e(val)}"
            do = [f"The 220 uF can has a light stripe down one side: that leg is <b>minus</b>.",
                  f"Minus (stripe) leg in {hole(pins['-'])}. Plus (longer) leg in {hole(pins['+'])}.",
                  "This one has a right way round. Double-check the stripe."]
            chk = ["Stripe faces the minus hole."]
        else:
            what = f"capacitor <b>{ref}</b>, {e(val)}"
            do = [f"A small 100 nF ceramic capacitor, printed <b>104</b>.",
                  f"One leg in {hole(pins['1'])}, the other in {hole(pins['2'])}. Either way round."]
            chk = []
        step(bd, f"Add {what}", do, need=[f"{ref}: {val}"], check=chk,
             figs=[board_svg(bd, cols, [("leaded", it[2])], [(k, d) for _k, k, d in done],
                             tags=[(h, short(h), "#333") for h in holes]), locator_svg(bd, cols)],
             cap=[f"{bd}, columns {cols[0]} to {cols[1]}", "where you are on the board"])
        done.append(it)
    for it in [i for i in items if i[1] == "module"]:
        ref = it[2]
        pl = b.PLACE[ref]
        pin0, h0 = pl["seat"]
        pins = sorted(item_holes("module", ref), key=lambda h: -b.parse(h)[2])
        cols = cols_of(pins, 26)
        p_first = [p for (r, p), h in b.ON_BB.items() if r == ref and h == pins[0]][0]
        p_last = [p for (r, p), h in b.ON_BB.items() if r == ref and h == pins[-1]][0]
        away = "top" if "bottom" in overhang(ref) else "bottom"
        step(bd, f"Seat {WHAT.get(ref, ref)}",
             [f"Hold <b>{ref}</b> ({e(b.PART[ref]['part'])}) with its header pins pointing down.",
              f"Its <b>{e(pin0.replace('H.', ''))}</b> pin goes in {hole(h0)}. The header then fills "
              f"{hole(pins[0])} to {hole(pins[-1])} ({len(pins)} pins).",
              f"The module sits {overhang(ref)}.",
              "Press straight down, evenly, until the header plastic touches the breadboard."],
             need=[f"{ref} with its header soldered on"],
             check=[f"Leftmost pin is {e(p_first.replace('H.', ''))} in {hole(pins[0])}; rightmost is "
                    f"{e(p_last.replace('H.', ''))} in {hole(pins[-1])}."],
             figs=[board_svg(bd, cols, [("module", ref)], [(k, d) for _k, k, d in done],
                             tags=[(pins[0], short(pins[0]), "#333", away), (pins[-1], short(pins[-1]), "#333", away)]),
                   locator_svg(bd, cols)],
             cap=[f"{bd}, columns {cols[0]} to {cols[1]}", "where you are on the board"])
        done.append(it)
    render = {"BB1": "BB1-iso", "BB2": "BB2-iso", "BB3": "BB3-iso"}[bd]
    step(bd, f"{bd} done. Take a break.", [f"{bd} is built: {total} things in place.", "Stand up, drink some water."],
         figs=[f'<img class="render" src="img/{render}.jpg" alt="{bd} finished">'],
         cap=[f"{bd} when finished (the Dupont wires come later)"], tip="Breaks between phases are part of the plan.")


def all_board_items(bd):
    return [(k, d) for _key, k, d in board_items(bd)]


def dupont_steps(routes, pl):
    ds = [(k, c) for k, c in enumerate(b.CONDUCTORS) if c[0] == "dupont"]
    for n, (k, c) in enumerate(ds, 1):
        hole_end, (ref, pin) = c[1], c[2]
        rt = routes[f"dupont:{k}"]
        colour = dupont_colour(c[3], c[1], c[2])
        gender, what = c[3].split(": ", 1)
        d3 = routing.drape(pl, rt)
        mm = sum(math.dist(p, q) for p, q in zip(d3, d3[1:]))
        size = next(s_ for s_ in (10, 20, 30) if mm * 1.10 <= s_ * 10)
        bd = hole_end.split(":")[0]
        morpho = pin.startswith(("CN7", "CN10"))
        far = (f"Slide the <b>socket</b> end onto the NUCLEO's <b>morpho pin {pin.replace('.', ' pin ')}</b> ({NUCLEO_PIN[pin]}): "
               f"the <b>{morpho_row(pin)}</b> row, {'odd' if int(pin.split('.')[1]) % 2 else 'even'} pins."
               if morpho else f"Push the other pin into the NUCLEO's <b>{pin.split('.')[0]} socket, pin {pin.split('.')[1]}</b> ({NUCLEO_PIN[pin]}).")
        rail = rail_note(hole_end)
        cols = cols_of([hole_end], 22)
        pts = rt["plan"]
        step("Duponts", f"D{n}: {e(what)}",
             [f"Take a <b>{gender}</b> Dupont, <b>{size} cm</b>.",
              f"Push one pin end into {bd} hole {hole(hole_end)}{rail}.",
              "Lay it along the path in the drawing: round the parts, not over them.",
              far],
             need=[f"1 × Dupont {gender}, {size} cm"],
             check=[f"Gentle tug at both ends: nothing moves."] + ([f"Not one pin off: {MORPHO_TRAPS[pin]}."] if pin in MORPHO_TRAPS else []),
             tip="NUCLEO header positions in the drawings are approximate. Trust the CN label and pin number printed on the board.",
             figs=[plate_svg(focus=bbox(pts), lines=[(pts, colour, 1.4, False)],
                             pins=[(*b.pin_xy(hole_end), short(hole_end))]),
                   board_svg(bd, cols, [("end", (hole_end, colour, f"D{n}"))], all_board_items(bd),
                             tags=[(hole_end, f"D{n} {short(hole_end)}", colour)]),
                   nucleo_svg(pin)],
             cap=["the wire's path on the plate", f"{bd} end: hole {short(hole_end)}", "NUCLEO end"], layout="split")


def end_text(end):
    if isinstance(end, str):
        return f"{end.split(':')[0]} hole {hole(end)}"
    ref, pin = end
    if ref.startswith("WG"):
        return f"<b>{ref}</b> ({e(b.PART[ref]['value'])}) lever <b>{pin}</b>"
    if pin.startswith("X1."):
        return f"<b>{ref}</b> screw terminal <b>{pin[3:]}</b>"
    if pin.startswith(("BATT", "SYS")):
        return f"<b>{ref}</b> {'BATT' if pin.startswith('BATT') else 'SYSOUT (Load Out)'} JST socket"
    if pin.startswith("BAT1"):
        return f"<b>{ref}</b> BAT JST socket"
    return f"<b>{ref}</b> {e(pin)}"


def island_steps(routes):
    island = (95, 55, 215, 112)

    done = []                                # wires already fitted on this island, drawn faded for context

    def lead(cids, title, do, need, colour, check=(), tip=None):
        """One step per wire: do[k] is the line for cids[k]; extra lines in do go on the last step."""
        for k, c in enumerate(cids):
            p1, p2 = b.pin_xy(c[1]), b.pin_xy(c[2])
            col = colour if not isinstance(colour, dict) else colour[c]
            lines = [([q1, q2], "#CFCBC0", .6, False) for q1, q2 in done] + [([p1, p2], col, 1.6, False)]
            pins = [ends_pin(p1, p2, short_end(c[1])), ends_pin(p2, p1, short_end(c[2]))]
            if "BT1" in (c[1][0], c[2][0]):                # the pack's own lead out to its loose plug
                px, py = b.PLUG_XY[("BT1", "+")]
                bx, by_, bw, bh = b.outline("BT1")
                lines.append(([(bx, by_ + bh - 6), (px + 6, py), (px + 2, py)], "#555", .7, True))
                lines.append(([(px - 1.5, py), (px + 5.5, py)], "#EDEBE4", 3.6, False))      # the plug body
                pins.append((bx + 4, by_ + bh - 6, "the pack, BT1", (0.0, -1.0)))
            keep = {end[0] for end in (c[1], c[2]) if not isinstance(end, str)}
            last = k == len(cids) - 1
            lines_do = [do[k]] + (do[len(cids):] if last else [])
            step("Power island", title + (f" ({k + 1} of {len(cids)})" if len(cids) > 1 else ""), lines_do,
                 need=need if k == 0 else (), check=check if last else (), tip=tip if last else None,
                 figs=[plate_svg(focus=[p for ln in lines[len(done):] for p in ln[0]], lines=lines, pins=pins, keep=keep)],
                 cap=["the wire to fit now is bold; ringed ends are where it goes; grey wires are already in"])
            done.append((p1, p2))

    C = {(c[0], c[3]): c for c in b.CONDUCTORS}
    by = lambda kind, start: [c for c in b.CONDUCTORS if c[0] == kind and c[3].startswith(start)]  # noqa: E731
    step("Power island", "The power island: what it is",
         ["Everything that carries real current lives here, <b>off</b> the breadboards: the pack, three WAGO lever blocks "
          "and short thick wires.",
          "WAGO levers: lift the orange lever, push the stripped wire in, close the lever. Tug to check.",
          "<b>The pack stays unplugged</b> until the very last page."],
         figs=[plate_svg(focus=island, glow_refs=("WG1", "WG2", "WG3"))],
         cap=["WAGO CELL+ (WG1), STAR (WG2) and LOAD (WG3); lever numbers are drawn on each"],
         tip="STAR is power ground. CELL+ is the battery's plus. LOAD feeds the test load and the regulator.")
    lead(by("pigtail", "pack-side"), "Pack pigtail into CELL+ and STAR",
         ["Take the pack-side half of a JST PH pigtail (the socket end). Its socket will clip onto the pack's own plug "
          "(dashed: the pack's 100 mm lead), but <b>not yet</b>: leave it loose beside the plug. "
          f"Its <b>red</b> wire goes into {end_text(('WG1', '1'))}.",
          f"Its <b>black</b> wire goes into {end_text(('WG2', '1'))}."],
         ["1 × JST PH pigtail, pack-side (socket) half"], {c: ("#D22B2B" if "red" in c[3] else "#222") for c in by("pigtail", "pack-side")})
    f = [c for c in b.CONDUCTORS if c[0] == "force" and c[1] == ("WG1", "2")]
    lead(f, "Battery lead: CELL+ to the battery INA228",
         ["Cut a 20 AWG red lead, about 30 mm, strip both ends.", f"One end into {end_text(('WG1', '2'))}.",
          f"Other end into {end_text(('U2', 'X1.VIN+'))}; tighten the screw."], ["20 AWG red, 30 mm"], "#D22B2B")
    lead([c for c in b.CONDUCTORS if c[0] == "sense" and c[1] == ("WG1", "3")], "Gauge sense lead",
         ["Board-side half of a pigtail (the plug). Only its red wire is used; tape the black one's end.",
          f"Red wire into {end_text(('WG1', '3'))}.", "Plug the plug into the MAX17048 gauge's BAT socket (U6)."],
         ["1 × JST PH pigtail, board-side (plug) half"], "#8A4FC0", check=["Black wire is taped and touches nothing."])
    batt = [c for c in b.CONDUCTORS if c[0] == "pigtail" and ("U1", "BATT.+") in (c[1], c[2]) or c[1] == ("U1", "BATT.-")]
    lead(batt, "Charger BATT socket",
         ["Plug a board-side pigtail half into the #4755's <b>BATT</b> JST socket. "
          f"Its <b>red</b> wire goes into {end_text(('U2', 'X1.VIN-'))}; tighten.",
          f"Its <b>black</b> wire goes into {end_text(('WG2', '2'))}."],
         ["1 × JST PH pigtail, board-side (plug) half"], {c: ("#D22B2B" if ".+" in str(c) else "#222") for c in batt})
    sysl = [c for c in b.CONDUCTORS if c[1] == ("U1", "SYS.+")]
    lead(sysl, "Charger Load Out (SYSOUT) socket",
         ["Board-side pigtail half into the #4755's <b>SYSOUT / Load Out</b> socket.",
          f"Red wire into {end_text(('U3', 'X1.VIN+'))}; tighten.", "Tape the black wire's end. It is not used."],
         ["1 × JST PH pigtail, board-side (plug) half"], "#D22B2B")
    lead([c for c in b.CONDUCTORS if c[1] == ("U3", "X1.VIN-") or c[1] == ("U3", "X1.VBUS")], "Load INA228 to LOAD",
         ["20 AWG red lead: " + end_text(('U3', 'X1.VIN-')) + " to " + end_text(('WG3', '4')) + ".",
          "22 AWG sense lead (thin): " + end_text(('U3', 'X1.VBUS')) + " to " + end_text(('WG3', '2')) + "."],
         ["20 AWG red, about 50 mm", "22 AWG, about 60 mm"], "#D22B2B")
    r9 = [c for c in b.CONDUCTORS if c[0] == "lead" and c[1][0] == "R9"]
    lead(r9, "The test load (your orange aluminium resistor)",
         ["R9 is the 100 ohm, 50 W test load (mode A only), screwed to the plate earlier. "
          f"Its left terminal's wire goes into {end_text(('WG3', '3'))}.",
          f"Its right terminal's wire goes into {end_text(('WG2', '3'))}.",
          "It stays cool: about 0.16 W in a 50 W part."],
         [f"R9's wires: about {r9_mm(('R9', '1'), ('WG3', '3'))} mm and {r9_mm(('R9', '2'), ('WG2', '3'))} mm"], "#E07A1A")
    rg = [(k, c) for k, c in enumerate(b.CONDUCTORS) if c[0] == "reg"][0]
    pts = routes[f"reg:{rg[0]}"]["plan"]
    step("Power island", "Regulator supply lead to BB1",
         ["22 AWG solid, about 85 mm.", f"One end into {end_text(('WG3', '5'))}.",
          f"Other end into BB1 hole {hole(rg[1][2])} (the S7V8F3's VIN strip). Follow the drawn path."],
         need=["22 AWG solid, 95 mm"], check=["Under 100 mm long."],
         figs=[plate_svg(focus=list(pts), lines=[(pts, "#F07A1A", 1.6, False)],
                         pins=[ends_pin(pts[0], pts[1], "WG3 lever 5"), ends_pin(pts[-1], pts[-2], short(rg[1][2]))])],
         cap=["the regulator lead"])
    pts = routes["W1"]["plan"]
    step("Power island", "W1: the one ground tie",
         ["22 AWG solid, about 85 mm. This is the <b>only</b> wire joining power ground to logic ground.",
          f"One end into {end_text(('WG2', '4'))}.", f"Other end into BB1 hole {hole(b.PART_SPANS['W1'][1])} (the S7V8F3's GND strip)."],
         need=["22 AWG solid, green, 95 mm"], check=["Under 100 mm long."],
         figs=[plate_svg(focus=list(pts), lines=[(pts, "#13A538", 1.6, False)],
                         pins=[ends_pin(pts[0], pts[1], "WG2 lever 4"), ends_pin(pts[-1], pts[-2], short(b.PART_SPANS["W1"][1]))])],
         cap=["the ground tie W1"])
    sol = [c for c in b.CONDUCTORS if c[0] == "force" and c[1][0] == "J4" or (c[0] == "force" and c[2][0] == "P2")]
    lead(sol, "Solar path: jack, solar INA228, plug",
         [f"20 AWG red: {end_text(('J4', '+'))} to {end_text(('U4', 'X1.VIN+'))}.",
          f"20 AWG red: {end_text(('U4', 'X1.VIN-'))} to the #369 plug's + screw (P2).",
          "20 AWG black: the #368 jack's − screw to the #369 plug's − screw.",
          "Push the #369 plug into the #4755's DC jack."],
         ["20 AWG red × 2, black × 1, 30-50 mm each"], {c: ("#222" if c[1] == ("J4", "-") else "#D22B2B") for c in sol},
         tip="The solar panel itself stays unplugged. Never connect the panel and the USB-C adapter at the same time.")
    usb = [c for c in b.CONDUCTORS if c[0] == "solder"]
    lead(usb, "USB-C path: breakout, USB-C INA228, plug",
         ["These leads were soldered during prep; check each one. Red: the #4090's VBUS pad to the USB-C INA228's "
          "<b>VIN+</b> screw (U5).",
          "Red: U5's <b>VIN−</b> screw to the #5978 plug's VBUS pad.",
          "Black: the #4090's GND pad to the #5978's GND pad.",
          "Push the #5978 plug into the #4755's USB-C socket."],
         ["the soldered USB-C assembly"], {c: ("#222" if "GND" in c[3] else "#D22B2B") for c in usb})
    a = b.pin_xy(("RT1", "1"))
    step("Power island", "NTC: tape the bead, leads to BB1",
         ["Tape the NTC's bead flat to the pack's side.",
          f"Its two leads go to BB1 holes {hole('BB1:c38')} and {hole('BB1:c39')} (either way round).",
          "The leads need about 160 mm. Extend them with Dupont wire if they're short."],
         need=["NTC #372", "Kapton or electrical tape"],
         figs=[plate_svg(focus=list(routes["RT1:1"]["plan"]), lines=[(routes["RT1:1"]["plan"], "#444", 1.2, False),
                                                                      (routes["RT1:2"]["plan"], "#444", 1.2, False)],
                         pins=[ends_pin(b.NTC_BEAD, routes["RT1:1"]["plan"][-2], "bead on the pack"),
                               ends_pin(a, routes["RT1:1"]["plan"][1], "c38 / c39")],
                         keep={"BT1", "U1"})],
         cap=["the NTC leads, from the pack to BB1"])


def ends_pin(p, q, label):
    """A callout at wire end p, its label pushed away from the other end q."""
    dx, dy = p[0] - q[0], p[1] - q[1]
    n = math.hypot(dx, dy) or 1.0
    return (*p, label, (dx / n, dy / n))


def r9_mm(a, z):
    """A lead length to cut: straight line x 1.15 + 10 mm, rounded up to 10 mm (as outputs.py does off-board)."""
    d = math.dist(b.pin_xy(a), b.pin_xy(z)) * 1.15 + 10
    return int(math.ceil(d / 10) * 10)


def short_end(end):
    if isinstance(end, str):
        return short(end)
    ref, pin = end
    if ref.startswith("WG"):
        return f"{ref} lever {pin}"
    if ref == "R9":
        return f"R9 {'left' if pin == '1' else 'right'} terminal"
    if ref == "BT1":
        return f"socket, onto the pack's plug ({'red' if pin == '+' else 'black'})"
    return f"{ref} {pin.replace('X1.', '').replace('.', ' ')}"


def qt_steps(routes):
    colours = {"GND": "#222", "V+": "#D22B2B", "SDA": "#2E62C9", "SCL": "#E0B800"}
    for cable, to, what in (("W2", "the QT hub's port 1 (U8)", "sensor branch"), ("W3", "the load INA228's left QT socket (U3)", "power branch")):
        pins = {p.split(".")[1]: h for (r, p), h in b.ON_BB.items() if r == cable}
        cols = cols_of(list(pins.values()), 24)
        pts = routes[cable]["plan"]
        step("QT cables", f"{cable}: QT-to-header cable, {what}",
             ["Four coloured wires end in header pins. Push each into BB1:",
              *[f"<span class='sw' style='background:{colours[s]}'></span> {('black GND', 'red 3V3', 'blue SDA', 'yellow SCL')[i]} → {hole(pins[s])}"
                for i, s in enumerate(("GND", "V+", "SDA", "SCL"))],
              f"Plug the QT end into {to}."],
             need=["1 × STEMMA QT to male header cable (#4209)"],
             check=["Colours match the holes exactly. Red never goes in a − rail."],
             tip="W3 measures about 155 mm along its path; the cable is 150 mm. Take the shortest line you can." if cable == "W3" else None,
             figs=[board_svg("BB1", cols, [("end", (h, colours[s], s)) for s, h in pins.items()], all_board_items("BB1"),
                             tags=[(h, f"{s} {short(h)}", colours[s]) for s, h in pins.items()]),
                   plate_svg(focus=bbox(pts, 16), lines=[(pts, "#1F7A8C", 1.6, False)])],
             cap=["BB1, the four header pins", "the cable's path"])
    hub = ("U8", "U9", "U10", "U11", "U12")
    step("QT cables", "Hub to the four sensors",
         ["Four short QT-to-QT cables from the hub's ports 2, 3, 4 and 5 to the sensors:",
          "port 2 → SHT45 (U9), port 3 → SHTC3 (U10), port 4 → BMP581 (U11), port 5 → LTR390 (U12)."],
         need=["4 × STEMMA QT cable, 50-100 mm"], check=["Each plug clicks in fully."],
         figs=[plate_svg(focus=bbox([p for r in hub for p in (b.outline(r)[:2], (b.outline(r)[0] + 25, b.outline(r)[1] + 18))], 12),
                         glow_refs=hub)], cap=["the sensor corner"])
    chain = ("U3", "U2", "U6", "U5", "U4")
    step("QT cables", "The meter chain on BB2",
         ["Daisy-chain the meters with short QT cables, each from one board's right socket to the next board's left one:",
          "load U3 → battery U2 → gauge U6 → USB-C U5 → solar U4."],
         need=["4 × STEMMA QT cable, 50 mm"], check=["Five boards, four cables, and W3 in U3's free socket."],
         figs=[plate_svg(focus=(5, 0, 185, 75), glow_refs=chain)], cap=["BB2 and its five meter boards"])


def write_imgs():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    for name in ("BB1-iso", "BB2-iso", "BB3-iso", "plate-iso", "plate-top"):
        im = Image.open(b.HERE / "kicad" / f"{name}.png").convert("RGB")
        im.thumbnail((1800, 1800))
        im.save(OUT / "img" / f"{name}.jpg", quality=85)


# ------------------------------------------------------------------ prep: the INA228 address straps
# Adafruit #5832 geometry from its Eagle board file (Adafruit-INA228-PCB, read 2026-11-04), top-view mm with
# y up from the header edge. The back view is the board turned over left to right: x -> 25.4 - x.
INA_W, INA_H = 25.4, 20.32
INA_HDR = [("VIN", 3.81), ("GND", 6.35), ("SCL", 8.89), ("SDA", 11.43), ("VBUS", 13.97), ("VIN-", 16.51),
           ("VIN+", 19.05), ("ALRT", 21.59)]                       # JP2, y 2.54
INA_JMP = {"A0": ((21.72, 7.87), (20.19, 7.87)), "A1": ((21.72, 5.59), (20.19, 5.59)),   # (VCC pad, address pad)
           "SJ1": ((15.49, 18.67), (13.46, 18.67))}                                      # (VIN+ pad, VBUS pad)
INA_TERM = [("VIN-", 9.2), ("VBUS", 12.7), ("VIN+", 16.2)]          # X1 screws, top view, at the far edge
INA_PREP = [  # ref, rail, address, A1, A0, SJ1 closed, why SJ1
    ("U2", "battery", "0x40", "GND", "GND", True, "VBUS reads the cell through VIN+"),
    ("U3", "load", "0x41", "GND", "VS", False, "VBUS gets its own sense lead to LOAD"),
    ("U4", "solar", "0x45", "VS", "VS", True, "VBUS reads the panel through VIN+"),
    ("U5", "USB-C", "0x48", "SDA", "GND", True, "VBUS reads USB-C through VIN+"),
]


def ina_svg(side, closed=(), opened=(), wire=False, note=True):
    """One #5832, back or front, with the solder jumpers drawn shut (closed) or marked open (opened)."""
    def X(x):
        return INA_W - x if side == "back" else x

    def Y(y):
        return INA_H - y
    o = [f'<rect x="0" y="0" width="{INA_W}" height="{INA_H}" rx="1.2" fill="#1C2F4D" stroke="#0B1520" stroke-width=".25"/>']
    for hx in (2.54, 22.86):
        o.append(f'<circle cx="{X(hx)}" cy="{Y(17.78)}" r="1.3" fill="#F1EFE8" stroke="#C9A227" stroke-width=".5"/>')
    if side == "front":
        o.append(f'<rect x="7.2" y="{Y(19.6)}" width="11" height="6.4" rx=".4" fill="#2E9E48" stroke="#14521F" stroke-width=".2"/>')
        for q in (3.05, 22.35):            # the two STEMMA QT sockets
            o.append(f'<rect x="{q - 2.2}" y="{Y(11.9)}" width="4.4" height="6" rx=".3" fill="#E8E4D8" stroke="#555" stroke-width=".15"/>')
        o.append(f'<rect x="10.95" y="{Y(7.85)}" width="3" height="3" fill="#222"/>')   # the INA228 itself, about 3 mm square
    for name, x in INA_TERM:
        o.append(f'<circle cx="{X(x)}" cy="{Y(16.4)}" r=".9" fill="#C9C9C9" stroke="#555" stroke-width=".15"/>')
    for name, x in INA_HDR:
        o.append(f'<circle cx="{X(x)}" cy="{Y(2.54)}" r=".95" fill="#D4AF37" stroke="#5A4510" stroke-width=".2"/>'
                 f'<text x="{X(x)}" y="{Y(2.54) + 2.4:.2f}" style="font:600 .78px Menlo,monospace;fill:#fff" text-anchor="middle">{name}</text>')
    if side == "back":
        o.append(f'<rect x="1.6" y="{Y(2.54) - 1.3:.2f}" width="22.2" height="2.6" rx=".3" fill="#111" opacity=".55"/>')
        for lab, x, y in (("A0", 18.4, 8.9), ("A1", 18.5, 6.7), ("Addr", 20.7, 4.0), ("VBus", 12.8, 14.5)):
            o.append(f'<text x="{X(x)}" y="{Y(y) + .4:.2f}" style="font:600 1.15px Avenir Next,Arial;fill:#E8E8E8" text-anchor="middle">{lab}</text>')
        for j, (p1, p2) in INA_JMP.items():
            for px, py in (p1, p2):
                o.append(f'<rect x="{X(px) - .58:.2f}" y="{Y(py) - .8:.2f}" width="1.17" height="1.6" fill="#D9B44A" stroke="#6B5310" stroke-width=".12"/>')
            cx, cy = (X(p1[0]) + X(p2[0])) / 2, Y(p1[1])
            if j in closed:
                o.append(f'<circle cx="{cx}" cy="{cy}" r="1.75" fill="{GLOW}" opacity=".55"/>'
                         f'<rect x="{min(X(p1[0]), X(p2[0])) - .3:.2f}" y="{cy - .6:.2f}" width="{abs(X(p1[0]) - X(p2[0])) + .6:.2f}" '
                         f'height="1.2" rx=".6" fill="#E9E9E9" stroke="#777" stroke-width=".12"/>')
            if j in opened:
                o.append(f'<circle cx="{cx}" cy="{cy}" r="1.45" fill="none" stroke="#E0002A" stroke-width=".25" stroke-dasharray=".6 .35"/>')
        if wire:                           # ADDR1 pad, across the back, round the edge (top-view x = 25.4)
            ax, ay = X(INA_JMP["A1"][1][0]), Y(INA_JMP["A1"][1][1])
            o.append(f'<polyline points="{ax},{ay} {ax},{Y(4.3)} 0,{Y(4.3)} -2.5,{Y(4.3)}" fill="none" stroke="#1F9E4A" '
                     f'stroke-width=".55" stroke-linejoin="round"/><circle cx="{ax}" cy="{ay}" r=".55" fill="#1F9E4A"/>')
    elif wire:                             # front: from the edge to the SDA joint, below the QT socket
        sx = 11.43
        o.append(f'<polyline points="27.9,{Y(4.3)} {INA_W},{Y(4.3)} {sx + .9},{Y(4.3)} {sx},{Y(2.54) - .6}" fill="none" '
                 f'stroke="#1F9E4A" stroke-width=".55" stroke-linejoin="round"/><circle cx="{sx}" cy="{Y(2.54)}" r="1.5" '
                 f'fill="none" stroke="#E0002A" stroke-width=".35"/>')
    vb = "-3.5 -1.5 32.4 25" if wire else "-1.5 -1.5 28.4 25"
    return f'<svg class="fig" viewBox="{vb}" xmlns="http://www.w3.org/2000/svg">{"".join(o)}</svg>'


def prep_steps():
    step("Prep", "Tape the TX NUCLEO's 5 V pins",
         ["Six NUCLEO pins carry 5 V. Nothing on this bench uses them, and one wire on them would put 5 V on the 3V3 parts.",
          "Cover each with a small square of Kapton, written <b>NO 5V</b>: " + ", ".join(f"<b>{p.replace('.', ' pin ')}</b>" for p in NO_5V) + ".",
          "The two on CN6 are sockets: tape over the hole. The four on CN7 and CN10 are pins: fold the tape over the pin."],
         need=["the TX NUCLEO", "Kapton tape and a fine pen"],
         check=["Six squares of tape, none on CN6 pin 4 (3V3) or CN7 pin 16 (3V3): those two are used."],
         tip="CN7 pin 7 is BOOT0 and CN7 pin 14 is RESET: nothing goes on them either. A wire on either and the board stays silent.",
         figs=[nucleo_svg(avoid=NO_5V)], cap=["the six pins to tape, crossed out (positions approximate: trust the printed CN labels)"])
    step("Prep", "Give each INA228 its own address",
         ["The four INA228s share one I2C bus, so each needs its own address. New, they are all <b>0x40</b>.",
          "On the <b>back</b>, beside <b>Addr</b>: pad pairs <b>A0</b> and <b>A1</b>. Solder across a pair ties that pin "
          "to power; open, it reads ground.",
          "The pair beside <b>VBus</b> (SJ1) joins VBUS to VIN+.",
          "Do all four now, before the breadboards."],
         need=["the four INA228 boards (#5832)", "soldering iron, thin solder, flux", "tape and a pen"],
         check=["Turned over left to right, the header is still nearest you."],
         tip="U5 (0x48) also needs one short wire: the jumpers only make 0x40, 0x41, 0x44, 0x45, and 0x44 is the SHT45.",
         figs=[ina_svg("back")], cap=["the back of a #5832, header nearest you (pad positions from Adafruit's board file)"])
    for ref, rail, addr, a1, a0, sj1, why in INA_PREP:
        closed = [j for j, v in (("A0", a0), ("A1", a1)) if v == "VS"] + (["SJ1"] if sj1 else [])
        opened = [j for j in ("A0", "A1", "SJ1") if j not in closed]
        say = {"VS": "<b>bridge it</b> with solder", "GND": "leave it <b>open</b>", "SDA": "leave it <b>open</b> (a wire does this one)"}
        do = [f"Board <b>{ref}</b> measures the <b>{rail}</b> rail. It becomes <b>{addr}</b>.",
              f"<b>A0</b>: {say[a0]}. <b>A1</b>: {say[a1]}.",
              f"<b>VBus</b> (SJ1): {'<b>bridge it</b>' if sj1 else 'leave it <b>open</b>'} ({why}).",
              f"Stick a tape label on the front: <b>{ref} {rail} {addr}</b>."]
        if ref == "U5":
            do.insert(2, "<b>Never bridge A1 on this board</b>: with the wire fitted, that would tie SDA to power and stop "
                         "every I2C part.")
        step("Prep", f"{ref}: the {rail} board, {addr}", do, need=[f"{ref} (INA228, {rail})"],
             check=[f"Bridged: {', '.join(closed) or 'nothing'}. Open: {', '.join(opened) or 'nothing'}."],
             figs=[ina_svg("back", closed=closed, opened=opened)],
             cap=["back view; solder blobs glow, dashed red rings stay open"])
    step("Prep", "U5: the wire that makes 0x48 (1 of 2)",
         ["Cut 30 mm of thin insulated wire (30 AWG wire-wrap). Strip 1 mm at each end.",
          "On the back, solder one end to the <b>inner</b> A1 pad (nearer the middle). The outer pad is power: keep off it.",
          "Run it to the ALRT-side edge, just above the header, and round to the front.",
          "Tack it down with Kapton tape."],
         need=["30 mm of 30 AWG wire", "Kapton tape"],
         check=["A1's two pads are still separate: no solder bridge."],
         tip="This puts the board's 10 kOhm A1 resistor on SDA. Expected: the bus idles near 3.0 V; the last page checks it.",
         figs=[ina_svg("back", opened=["A1"], closed=["SJ1"], wire=True)], cap=["back view: the green wire leaves the inner A1 pad"])
    step("Prep", "U5: the wire that makes 0x48 (2 of 2)",
         ["On the front, run the wire along the board just above the header joints, below the QT socket.",
          "Solder its end to the <b>SDA</b> header pin's joint (fourth from VIN).",
          "Keep it flat so the board still sits level on the breadboard."],
         check=["Meter on beep: the inner A1 pad to the SDA pin beeps.",
                "The SDA pin to the VIN pin does <b>not</b> beep."],
         figs=[ina_svg("front", wire=True)], cap=["front view: the wire ends on the SDA joint (red ring)"])
    step("Prep", "Check all four with a meter",
         ["Meter on continuity (beep). Probe the jumper's two pads, or the header pins named.",
          "<b>U2</b> 0x40: A0 no beep, A1 no beep; VIN+ screw to VBUS screw <b>beeps</b>.",
          "<b>U3</b> 0x41: A0 <b>beeps</b>, A1 no beep; VIN+ to VBUS no beep.",
          "<b>U4</b> 0x45: A0 <b>beeps</b>, A1 <b>beeps</b>; VIN+ to VBUS <b>beeps</b>.",
          "<b>U5</b> 0x48: A0 no beep, A1 no beep; inner A1 pad to SDA <b>beeps</b>; VIN+ to VBUS <b>beeps</b>."],
         check=["Every board has its tape label: U2, U3, U4, U5."],
         tip="A bridged pad pair measures 0 ohm; an open one shows the board's 10 kOhm resistor or nothing.",
         figs=[ina_svg("back", closed=["A0", "A1", "SJ1"])], cap=["where to probe: the three pad pairs"])


def build_steps():
    routes, problems, pl = routing.route_all()
    if problems:
        sys.exit("routing problems: " + "; ".join(problems))
    step("Boards", "Lay out the three breadboards",
         ["Put the three breadboards on the plate as drawn. Back edge at the top.",
          "Label them with tape: <b>BB2</b> at the back, <b>BB1</b> in the middle, <b>BB3</b> at the front.",
          "Each board: printed <b>1</b> on the right, row <b>a</b> at the top."],
         need=["3 × Elegoo 830-point breadboards", "masking tape and a pen"],
         check=["Column 62 is on the left of every board."],
         figs=[plate_svg(boards_glow=("BB1", "BB2", "BB3"), only_boards=True)], cap=["the plate from above, back edge at the top"])
    prep_steps()
    board_phase("BB2", "Five meter boards push straight in. A quick win to start.")
    board_phase("BB1", "Charger, regulator and the small parts that read the charger.")
    board_phase("BB3", "Weather meter jacks, their pull-up resistors, and the OLED.")
    mount = [("A1", "the TX NUCLEO", "Rest its four corners on the cradle's corner ledges, then press until each lip clicks over. ST-LINK USB socket faces right."),
             ("A2", "the RX NUCLEO", "Back-right corner: corners on the ledges, press until the lips click. USB at the back edge."),
             (("WG1", "WG2", "WG3"), "the three WAGO blocks", "In their holders. CELL+ (3 levers) on the left, then STAR, then LOAD."),
             ("BT1", "the pack cradle", "Put the pack in its cradle. Leave it unplugged."),
             (("J3", "J4"), "the USB-C breakout and the barrel jack", "Left edge: cables come in from the left."),
             (("U8", "U9", "U10", "U11", "U12"), "the QT hub and four sensors", "On M2.5 standoffs, right of BB1."),
             ("R9", "the R9 test load", "Two M3 screws through its corner tabs. Its wires go to the WAGOs later.")]
    for refs, what, how in mount:
        refs = refs if isinstance(refs, tuple) else (refs,)
        pts = [p for r in refs for p in (b.outline(r)[:2], (b.outline(r)[0] + b.outline(r)[2], b.outline(r)[1] + b.outline(r)[3]))]
        step("Plate", f"Mount {what}", [how], need=[f"{r}: {b.PART[r]['part']}" for r in refs],
             figs=[plate_svg(focus=bbox(pts, 30, 140, 100), glow_refs=refs)], cap=["where it goes"])
    dupont_steps(routes, pl)
    island_steps(routes)
    qt_steps(routes)
    step("Finish", "Weather meter and USB cables",
         ["Wind cable into the RJ11 jack on J1, rain cable into J2 (both on BB3's front edge).",
          "TX NUCLEO ST-LINK USB to the Mac. RX NUCLEO USB to its own Mac port."],
         need=["the two weather meter cables", "2 × USB cables"],
         figs=[plate_svg(glow_refs=("A1", "A2", "J1", "J2"))], cap=["cable entries"])
    step("Finish", "Set mode A (daily)",
         ["Jumper cap on the NUCLEO's <b>JP4</b> pins 1-2.", "<b>No</b> cap on BB1's BATTERY link (JP1, h18/h19).",
          "Cap on BB3's OLED link (JP2, h37/h38) if you want the OLED on.", "R9 test load is in its WAGO levers."],
         need=["2 jumper caps"], check=["Only one cap moves between modes: JP4 (mode A) ↔ BATTERY link (mode B)."],
         figs=[board_svg("BB1", (24, 12), [("leaded", ("JP1", {"1": "BB1:h19", "2": "BB1:h18"}))], all_board_items("BB1"),
                         tags=[("BB1:h19", "JP1: no cap", "#E0002A")])],
         cap=["BB1: the BATTERY link stays open in mode A"])
    step("Finish", "Last look, then plug in the pack",
         ["Look for any bare wire touching another.", "Every WAGO lever closed; every screw tight.",
          "Now plug the pack into its pigtail. Then plug the TX USB into the Mac.", "You're done. Nice work."],
         check=["Nothing warm after a minute."],
         figs=[f'<img class="render" src="img/plate-iso.jpg" alt="finished bench">'], cap=["the whole bench, finished"])
    step("Finish", "Check the rails",
         ["TX USB plugged in (mode A). Meter on DC volts, black on the rail's own <b>−</b>.",
          "BB1 bottom <b>+</b> rail: <b>3.2 to 3.4 V</b>. BB3 bottom <b>+</b> rail: the same.",
          "BB2's rails and every top rail: <b>0 V</b>. They are not used.",
          "OLED link fitted: BB3 " + hole("BB3:e38") + " to " + hole("BB3:c37") + " reads 3.3 V too."],
         check=["About 5 V on a rail: unplug at once and find the wire on a taped pin.",
                "Console silent and the screen dark: a wire on CN7 pin 7 (BOOT0) or pin 14 (RESET)."],
         tip="0 V on BB3's + rail: D13 is not on CN7 pin 16. Count again from the CN7 label.",
         figs=[board_svg(bd, cols_of([f"{bd}:B+{col}"], 22), [], all_board_items(bd),
                         tags=[(f"{bd}:B-{col}", "red on + just above, black here", "#D22B2B")])
               for bd, col in (("BB1", 27), ("BB3", 28))],
         cap=["BB1: probe beside its GND/3V3 feeds", "BB3: probe beside D13 and D14"])
    step("Finish", "Check the I2C bus",
         ["TX USB plugged in (mode A), so the bus has power.",
          "Meter on DC volts: black on a GND rail, red in BB1's free SDA hole " + hole("BB1:j12") + ". Read <b>2.8 V or more</b> "
          "(about 3.0 V is normal: U5's wire adds a small pull-down).",
          "Flash and run <code>firmware/i2cscan</code>. Expect the gauge <b>0x36</b>, the four rails <b>0x40 0x41 0x45 0x48</b>, "
          "and the sensors 0x44, 0x47, 0x53, 0x70."],
         check=["U5 shown at 0x40 or 0x44 instead of 0x48: its wire is open or on the wrong pad."],
         tip="A rail missing and a ? at another address means that board's jumpers are set wrong.",
         figs=[ina_svg("back", closed=["SJ1"], opened=["A0", "A1"], wire=True)], cap=["U5, the board most likely to go wrong"])
    return routes


# ------------------------------------------------------------------ the document
CSS = """
@page { size: 11in 8.5in; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif; color: #1B1F23; background: #fff; }
.page { width: 11in; height: 8.5in; padding: .42in .5in .38in; page-break-after: always; position: relative; overflow: hidden;
  display: grid; grid-template-rows: auto auto 1fr; }
.top { display: flex; align-items: center; gap: 14px; font-size: 13px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.chip { color: #fff; padding: 5px 11px; border-radius: 999px; }
.bar { flex: 1; height: 8px; background: #E9EAE6; border-radius: 99px; overflow: hidden; }
.bar i { display: block; height: 100%; }
.count { color: #59626B; font-variant-numeric: tabular-nums; margin-right: 46px; }
h1 { font-size: 34px; line-height: 1.08; margin: 14px 0 10px; font-weight: 700; letter-spacing: -.01em; }
.body { display: grid; grid-template-columns: 3.35in 1fr; gap: .32in; min-height: 0; }
.left { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.box { border-radius: 10px; padding: 10px 13px; font-size: 15px; line-height: 1.4; }
.need { background: #F2F3EF; } .need b.k, .chk b.k, .tip b.k { display: block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #59626B; margin-bottom: 3px; }
.chk { background: #EAF6EE; } .tip { background: #FFF6DA; }
ol { margin: 0; padding: 0; list-style: none; counter-reset: s; display: flex; flex-direction: column; gap: 9px; }
ol li { counter-increment: s; position: relative; padding-left: 40px; font-size: 18px; line-height: 1.35; }
ol li::before { content: counter(s); position: absolute; left: 0; top: -1px; width: 28px; height: 28px; border-radius: 50%;
  background: var(--pc); color: #fff; font-weight: 700; font-size: 15px; display: grid; place-items: center; }
ul { margin: 0; padding-left: 18px; }
.h { font-family: Menlo, "SF Mono", monospace; font-weight: 700; background: #1B1F23; color: #FFD84D; padding: 1px 6px; border-radius: 5px; font-size: .92em; white-space: nowrap; }
.why { color: #6B737B; font-size: .85em; }
.h.gnd { background: #2E62C9; color: #fff; } .h.v33 { background: #D22B2B; color: #fff; }
.sw { display: inline-block; width: 13px; height: 13px; border-radius: 3px; vertical-align: -1px; border: 1px solid #0003; }
.right { display: flex; flex-direction: column; gap: 8px; min-width: 0; min-height: 0; }
.figs { display: flex; flex-direction: column; gap: 6px; min-height: 0; flex: 1; }
figure { margin: 0; display: flex; flex-direction: column; min-height: 0; flex: 1; }
figure.small { flex: 0 0 auto; }
.pair { display: grid; grid-template-columns: 1.25fr 1fr; gap: 10px; flex: 1; min-height: 0; }
.pair figure { min-height: 0; }
figure svg.fig, figure img.render { width: 100%; flex: 1; min-height: 0; object-fit: contain; }
figure img.render { border-radius: 8px; }
figure svg.loc { height: .78in; width: auto; align-self: flex-end; }
figcaption { font-size: 11.5px; color: #6B737B; text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }
.tickbox { position: absolute; right: .5in; top: .38in; width: 30px; height: 30px; border: 3px solid #1B1F23; border-radius: 7px; }
.foot { position: absolute; left: .5in; bottom: .18in; font-size: 10px; color: #8A9198; }
svg text { font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif; }
.cn { font-size: 1.35px; text-anchor: middle; fill: #8A8F94; } .cn.b5 { font-weight: 700; fill: #3E4246; font-size: 1.6px; }
.rl { font-size: 1.9px; font-weight: 700; text-anchor: middle; fill: #5A5F64; }
.pin { font-size: 1.2px; fill: #FFE9A8; font-family: Menlo, monospace; }
.mod { font-size: 2.4px; fill: #fff; text-anchor: middle; font-weight: 700; }
.tag { font-size: 2.6px; text-anchor: middle; font-weight: 700; fill: #111; font-family: Menlo, monospace; }
.pm { font-size: 2.8px; font-weight: 700; text-anchor: middle; fill: #16306E; }
.cap { font-size: 1.2px; text-anchor: middle; fill: #3A2200; font-weight: 700; }
.bbl { font-size: 9px; text-anchor: middle; font-weight: 700; fill: #B5B8B0; }
.tiny { font-size: 3px; fill: #777; }
.pl { text-anchor: middle; font-weight: 700; }
.lever { font-size: 2.2px; text-anchor: middle; fill: #fff; font-weight: 700; }
.ptag { font-size: 3.3px; text-anchor: middle; font-weight: 700; fill: #111; }
.cnl { font-size: 3px; text-anchor: middle; font-weight: 700; fill: #333; }
.locl { font-size: 12px; text-anchor: middle; fill: #B5B8B0; font-weight: 700; }
.intro h1 { font-size: 44px; } .intro p, .intro li { font-size: 19px; line-height: 1.45; max-width: 7.2in; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: .35in; }
.legend { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; align-items: center; font-size: 16px; }
.legend span.s { width: 44px; height: 12px; border-radius: 6px; }
"""


def page(n, total, s):
    pc = PHASE_COLOUR.get(s["phase"], "#444")
    figs = []
    for k, f in enumerate(s["figs"]):
        small = 'class="small"' if 'class="loc"' in f else ""
        cap = s["cap"][k] if k < len(s["cap"]) else ""
        figs.append(f"<figure {small}>{f}<figcaption>{e(cap)}</figcaption></figure>")
    left = [f'<ol>{"".join(f"<li>{d}</li>" for d in s["do"])}</ol>']
    if s["need"]:
        left.insert(0, f'<div class="box need"><b class="k">You need</b>{"<br>".join(e(x) for x in s["need"])}</div>')
    if s["check"]:
        left.append(f'<div class="box chk"><b class="k">Check it</b>{"<br>".join(s["check"])}</div>')
    if s["tip"]:
        left.append(f'<div class="box tip"><b class="k">Tip</b>{e(s["tip"])}</div>')
    if s["layout"] == "split" and len(figs) == 3:
        figs = [figs[0], f'<div class="pair">{figs[1]}{figs[2]}</div>']
    return (f'<section class="page" style="--pc:{pc}"><div class="top"><span class="chip" style="background:{pc}">{e(s["phase"])}</span>'
            f'<span class="bar"><i style="width:{100 * n / total:.1f}%;background:{pc}"></i></span>'
            f'<span class="count">step {n} of {total}</span></div><div class="tickbox"></div>'
            f'<h1>{s["title"]}</h1><div class="body"><div class="left">{"".join(left)}</div>'
            f'<div class="right"><div class="figs">{"".join(figs)}</div></div></div>'
            f'<div class="foot">Bench r1 build guide · generated from layout/build.py and routing.py · '
            f'drawings are to scale; header positions on modules are estimates until measured</div></section>')


def intro_pages(total):
    jumpers = [b.span(c[1], c[2]) for c in b.CONDUCTORS if c[0] == "jumper"]
    jl = ", ".join(f"{jumpers.count(s)} × {s}-hole" for s in sorted(set(jumpers)))
    tally = {}
    for st in STEPS:
        for n_ in st["need"]:
            if n_.startswith("1 × Dupont "):
                tally[n_[11:]] = tally.get(n_[11:], 0) + 1
    dl = ", ".join(f"{n} × {k}" for k, n in sorted(tally.items()))
    p1 = f"""<section class="page intro"><div><div class="top"><span class="chip" style="background:#5B6770">Get ready</span></div>
<h1>Bench r1: build it one step at a time</h1>
<div class="cols"><div><p><b>{total} steps.</b> One small thing per page. Do the numbered moves, then tick the box in the corner.</p>
<p>In every drawing, <b style="background:{GLOW};padding:0 5px;border-radius:4px">the glowing part</b> is what you add now.
Faded parts are already done.</p><p>The coloured bar at the top shows how far along you are. Take a break at every
"done" page. Stopping mid-phase is fine too: the tick boxes show where you left off.</p></div>
<div><div class="legend">
<span class="s" style="background:#D22B2B"></span><span>+ rail and red wires: 3V3 or battery plus</span>
<span class="s" style="background:#2E62C9"></span><span>− rail: ground</span>
<span class="s" style="background:#222"></span><span>black wires: ground</span>
<span class="s" style="background:#2E62C9"></span><span>blue wire: SDA (I2C data)</span>
<span class="s" style="background:#E0B800"></span><span>yellow wire: SCL (I2C clock)</span>
<span class="s" style="background:{GLOW}"></span><span>do this now</span></div>
<p style="margin-top:22px"><span class="h">h24</span> means row <b>h</b>, column <b>24</b>. Columns run <b>62 on the left</b>
down to <b>1 on the right</b>.</p><p><span class="h gnd">GND ↓27</span> is a hole in the blue − (ground) rail along the
<b>bottom</b> edge, straight below column 27. <span class="h v33">3V3 ↓18</span> is the red + rail, bottom edge, below
column 18. An ↑ arrow means the rails along the top edge.</p></div></div></div></section>"""
    p2 = f"""<section class="page intro"><div><div class="top"><span class="chip" style="background:#5B6770">Get ready</span></div>
<h1>Before you start</h1><div class="cols"><div><p><b>Gather these.</b></p><ul>
<li>3 breadboards, the plate, standoffs, WAGO holders</li><li>BOJACK jumpers: {jl}</li>
<li>Duponts: {dl}</li>
<li>Resistors: 4 × 10k 1%, 1 × 1M 1%, 3 × 10k; capacitors: 3 × 100 nF, 1 × 220 uF; 2 × 2-pin headers</li>
<li>20 AWG and 22 AWG wire, strippers, a small screwdriver, tape</li></ul></div>
<div><p><b>Already done in prep</b> (design.md section 3): headers soldered on every module, the #4755 THERM jumper cut, the USB-C leads soldered, the pigtails made.</p>
<p><b>Safety:</b> the pack stays unplugged until the last page. Nothing that carries battery current goes into a breadboard.</p></div></div></div></section>"""
    return p1 + p2


def write():
    fails, _n = b.check()
    if fails:
        sys.exit("build.check() fails:\n" + "\n".join(fails))
    OUT.mkdir(exist_ok=True)
    write_imgs()
    build_steps()
    total = len(STEPS)
    pages = intro_pages(total) + "".join(page(n, total, s) for n, s in enumerate(STEPS, 1))
    doc = f'<!doctype html><html><head><meta charset="utf-8"><title>Bench r1 build guide</title><style>{CSS}</style></head><body>{pages}</body></html>'
    src = OUT / "wiring-guide.html"
    src.write_text(doc)
    pdf = OUT / "wiring-guide.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                    f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True)
    print(f"wrote {pdf} ({total} steps + 2 intro pages)")


if __name__ == "__main__":
    write()
