"""Shared sheet furniture (from Session 1 v2: make_session1_v2.py) for the TX stack, v2: cyberpunk flat-pack style, illustrations from real 3D geometry.

The illustrations are SVGs rendered by scenes.py (CadQuery + OpenCascade hidden lines + ray-cast flat colour, run in
the CAD venv). This script (reportlab + svglib venv) lays them out, adds every label on a paper chip with leaders
that stop at the chip edge, and checks the label layout for overlaps. Content, palette, fonts and page furniture are
v1's (../make_session1.py).

Usage: pdfenv/bin/python make_session1_v2.py OUT_DIR
"""
import json
import math
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "session1" / "v2"))
import holecheck as HC  # noqa: E402
SVG = HERE / "svg"
PROTO = "PROTOCOL 04 // SESSION 4 // B1 PORTS A"
SUP = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("HEAD", SUP + "DIN Condensed Bold.ttf"))
pdfmetrics.registerFont(TTFont("ALT", SUP + "DIN Alternate Bold.ttf"))
pdfmetrics.registerFont(TTFont("MONO", SUP + "Andale Mono.ttf"))

PAPER = HexColor("#EEECE6")
INK = HexColor("#121212")
HAZ = HexColor("#FFD400")      # hazard yellow: the thing you work on
NEON = HexColor("#FF2E88")     # magenta: measure / critical
FR4 = HexColor("#DCD6BF")
STEEL = HexColor("#B9BCC0")
GREY = HexColor("#7A7A7A")
WHITE = HexColor("#FFFFFF")

W, H = 612, 792                # US Letter
M = 30

SLOGANS = [
    "COMPLIANCE IS A FEATURE.",
    "MEASURE TWICE. THE MACHINE REMEMBERS BOTH.",
    "YOUR LABOUR IS APPRECIATED BY THE WEATHER.",
    "THERE IS NO SPARE BOARD. THERE ARE FOUR SPARE BOARDS.",
    "DUST IS PERMANENT. WEAR THE MASK.",
    "REPORT ALL NUMBERS TO CLAUDE.",
]

MIN_LABEL, MIN_FINE, MIN_KEY = 9, 8, 12


# ------------------------------------------------------------------ primitives
def lw(c, w):
    c.setLineWidth(w)


def text(c, x, y, s, size=9, font="MONO", color=INK, anchor="l", rec=True):
    c.setFillColor(color)
    c.setFont(font, size)
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[anchor](x, y, s)
    if rec and s.strip():
        wd = pdfmetrics.stringWidth(s, font, size)
        x0 = x - {"l": 0, "c": wd / 2, "r": wd}[anchor]
        LAB.texts.append((x0, y - size * 0.2, x0 + wd, y + size * 0.72, s))


LEADER_INK = False    # Session 2 sets True: every leader black (never red/magenta on the red card)
HALO = WHITE          # paper-white outline under every leader, arrow and dimension over artwork


def arrow(c, x1, y1, x2, y2, color=INK, w=2.2, head=9, halo=None):
    """Arrow with a contrast outline (halo colour, default paper white) under it."""
    halo = HALO if halo is None else halo
    a = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * 0.8 * math.cos(a), y2 - head * 0.8 * math.sin(a)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - head * math.cos(a - 0.45), y2 - head * math.sin(a - 0.45))
    p.lineTo(x2 - head * math.cos(a + 0.45), y2 - head * math.sin(a + 0.45))
    p.close()
    if halo:
        c.setStrokeColor(halo)
        c.setFillColor(halo)
        lw(c, w + 2.4)
        c.line(x1, y1, bx, by)
        lw(c, 2.4)
        c.drawPath(p, stroke=1, fill=1)
    c.setStrokeColor(color)
    c.setFillColor(color)
    lw(c, w)
    c.line(x1, y1, bx, by)
    c.drawPath(p, stroke=0, fill=1)


def curved_arrow(c, cx, cy, r, a0, a1, color=INK, w=2.2):
    c.setStrokeColor(color)
    lw(c, w)
    n = 24
    pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    for (x1, y1), (x2, y2) in zip(pts[:-2], pts[1:-1]):
        c.line(x1, y1, x2, y2)
    arrow(c, *pts[-3], *pts[-1], color=color, w=w)


def badge(c, x, y, n, r=13):
    c.setFillColor(INK)
    c.circle(x, y, r, stroke=0, fill=1)
    text(c, x, y - r * 0.42, str(n), r * 1.25, "HEAD", HAZ, "c", rec=False)


def verdict(c, x, y, ok, r=12):
    c.setFillColor(INK if ok else NEON)
    c.circle(x, y, r, stroke=0, fill=1)
    c.setStrokeColor(WHITE)
    lw(c, 3 * r / 12)
    if ok:
        c.line(x - r * 0.45, y, x - r * 0.1, y - r * 0.4)
        c.line(x - r * 0.1, y - r * 0.4, x + r * 0.5, y + r * 0.45)
    else:
        c.line(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4)
        c.line(x - r * 0.4, y + r * 0.4, x + r * 0.4, y - r * 0.4)
    LAB.block(x - r, y - r, x + r, y + r, "verdict")


def times(c, x, y, s, size=30):
    text(c, x, y, s, size, "HEAD", INK, "c")
    w = pdfmetrics.stringWidth(s, "HEAD", size)
    LAB.block(x - w / 2, y - 2, x + w / 2, y + size * 0.72, s)


def mask_icon(c, x, y, s=1.0):
    c.saveState()
    c.translate(x, y)
    c.scale(s, s)
    c.setStrokeColor(INK)
    c.setFillColor(WHITE)
    lw(c, 1.6)
    p = c.beginPath()
    p.moveTo(-16, 6)
    p.curveTo(-12, 16, 12, 16, 16, 6)
    p.curveTo(16, -8, 8, -14, 0, -15)
    p.curveTo(-8, -14, -16, -8, -16, 6)
    p.close()
    c.drawPath(p, stroke=1, fill=1)
    c.line(-16, 6, -26, 12)
    c.line(16, 6, 26, 12)
    c.line(-14, -6, -26, -10)
    c.line(14, -6, 26, -10)
    lw(c, 0.8)
    for i in (-6, 0, 6):
        c.line(i, -8, i, 8)
    c.restoreState()
    LAB.block(x - 26 * s, y - 15 * s, x + 26 * s, y + 14 * s, "mask")


# ------------------------------------------------------------------ labels: chips, leaders, checks
class Labels:
    """Every label is a paper chip. Records chips and leaders per page and checks them."""

    def __init__(self):
        self.reset(0)

    def reset(self, pg):
        self.pg = pg
        self.chips = []      # (x0, y0, x1, y1, text)
        self.blocks = []     # other things labels must not cover
        self.leaders = []    # (x0, y0, x1, y1, owner chip index)
        self.panels = []     # (x0, y0, x1, y1, caption_top)
        self.texts = []      # every text run drawn (x0, y0, x1, y1, s)
        self.arts = []       # every placed render (x0, y0, x1, y1, name)
        self.issues = []

    def block(self, x0, y0, x1, y1, what):
        self.blocks.append((x0, y0, x1, y1, what))

    def check(self):
        def ov(a, b, pad=0.5):
            return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad
        for i, a in enumerate(self.chips):
            for b in self.chips[i + 1:]:
                if ov(a, b):
                    self.issues.append(f"chips overlap: {a[4]!r} / {b[4]!r}")
            for b in self.blocks:
                if ov(a, b):
                    self.issues.append(f"chip {a[4]!r} overlaps {b[4]!r}")
            inside = [p for p in self.panels if a[0] >= p[0] - 0.1 and a[2] <= p[2] + 0.1 and a[1] >= p[1] - 0.1
                      and a[3] <= p[3] + 0.1]
            if not inside:
                self.issues.append(f"chip {a[4]!r} crosses a panel edge")
            elif a[1] < inside[0][4]:
                self.issues.append(f"chip {a[4]!r} runs into the caption")
        # panel badges own their corner: no text and no artwork may reach into it
        for b in [b for b in self.blocks if b[4] == "badge"]:
            for t in self.texts:
                if ov(t, b, 0.2):
                    self.issues.append(f"text {t[4]!r} under a panel badge")
            for a in self.arts:
                if ov(a, b, 0.2):
                    self.issues.append(f"art {a[4]!r} under a panel badge")
        for (x0, y0, x1, y1, k) in self.leaders:
            for j, b in enumerate(self.chips):
                if j == k:
                    continue
                if seg_hits_rect(x0, y0, x1, y1, b):
                    self.issues.append(f"leader of {self.chips[k][4]!r} crosses chip {b[4]!r}")
        for s in self.issues:
            print(f"  page {self.pg}: {s}")
        return self.issues


def seg_hits_rect(x0, y0, x1, y1, r, pad=0.8):
    rx0, ry0, rx1, ry1 = r[0] + pad, r[1] + pad, r[2] - pad, r[3] - pad
    n = 40
    for i in range(n + 1):
        t = i / n
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        if rx0 < x < rx1 and ry0 < y < ry1:
            return True
    return False


LAB = Labels()


def chip(c, x, y, s, size=9, font="ALT", color=INK, anchor="l", pad=2.6, fill=WHITE, border=None):
    """Text on a solid paper chip. (x, y) is the text baseline anchor. Returns the chip rect."""
    lines = s.split("\n")
    wd = max(pdfmetrics.stringWidth(l, font, size) for l in lines)
    asc = size * (0.72 if font in ("ALT", "HEAD") else 0.74)
    lead = size * 1.12
    hgt = asc + lead * (len(lines) - 1)
    x0 = x - {"l": 0, "c": wd / 2, "r": wd}[anchor]
    r = (x0 - pad, y - pad - lead * (len(lines) - 1), x0 + wd + pad, y + asc + pad)
    c.setFillColor(fill)
    if border is not None:
        c.setStrokeColor(border)
        lw(c, 1.0)
    c.rect(r[0], r[1], r[2] - r[0], r[3] - r[1], stroke=1 if border is not None else 0, fill=1)
    for i, l in enumerate(lines):
        text(c, x, y - lead * i, l, size, font, color, anchor)
    LAB.chips.append((*r, s))
    return r


def leader(c, r, px, py, color=INK, dot=True, w=1.0):
    if dot:
        HC.mark(px, py, "leader dot")
    """Line from the edge of chip r to the point (px, py)."""
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    # exit point on the chip boundary toward the target
    dx, dy = px - cx, py - cy
    hw, hh = (r[2] - r[0]) / 2, (r[3] - r[1]) / 2
    t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
    ex, ey = cx + dx * t, cy + dy * t
    if LEADER_INK:
        color = INK
    c.setStrokeColor(HALO)
    lw(c, 2.6)
    c.line(ex, ey, px, py)
    c.setStrokeColor(color)
    lw(c, w)
    c.line(ex, ey, px, py)
    if dot:
        c.setFillColor(HALO)
        c.circle(px, py, 2.6, stroke=0, fill=1)
        c.setFillColor(color)
        c.circle(px, py, 1.6, stroke=0, fill=1)
    k = [i for i, ch in enumerate(LAB.chips) if ch[:4] == tuple(r)]
    LAB.leaders.append((ex, ey, px, py, k[0] if k else -1))


def label(c, x, y, s, px, py, size=9, font="ALT", color=INK, anchor="l", lcolor=None, dot=True):
    r = chip(c, x, y, s, size, font, color, anchor)
    leader(c, r, px, py, lcolor or color, dot)
    return r


def dim(c, x1, y1, x2, y2, s, size=12, color=NEON, font="ALT", ticks=True, lx=None, ly=None, w=1.3):
    """Dimension line with arrowheads; the label sits on a chip that interrupts the line."""
    c.setStrokeColor(HALO)
    lw(c, w + 2.2)
    c.line(x1, y1, x2, y2)
    c.setStrokeColor(color)
    c.setFillColor(color)
    lw(c, w)
    c.line(x1, y1, x2, y2)
    a = math.atan2(y2 - y1, x2 - x1)
    for (x, y, sgn) in ((x1, y1, 1), (x2, y2, -1)):
        hx, hy = x + sgn * 6 * math.cos(a), y + sgn * 6 * math.sin(a)
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(hx - 2.4 * math.sin(a), hy + 2.4 * math.cos(a))
        p.lineTo(hx + 2.4 * math.sin(a), hy - 2.4 * math.cos(a))
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        if ticks:
            nx, ny = -math.sin(a) * 5, math.cos(a) * 5
            c.line(x - nx, y - ny, x + nx, y + ny)
    if s:
        mx = (x1 + x2) / 2 if lx is None else lx
        my = (y1 + y2) / 2 - size * 0.36 if ly is None else ly
        return chip(c, mx, my, s, size, font, color, "c")


def dashed(c, x1, y1, x2, y2, color=NEON, w=2.0, d=(6, 3), halo=None):
    halo = HALO if halo is None else halo
    if halo:
        c.setStrokeColor(halo)
        lw(c, w + 2.2)
        c.line(x1, y1, x2, y2)
    c.setStrokeColor(color)
    lw(c, w)
    c.setDash(*d)
    c.line(x1, y1, x2, y2)
    c.setDash()


# ------------------------------------------------------------------ illustrations
class Art:
    """An SVG render placed on the page; A(name) maps its anchors to page coordinates."""

    def __init__(self, c, name, x, y, w, h, align="c", valign="c", clip_circle=False, frame=False):
        self.d = svg2rlg(str(SVG / f"{name}.svg"))
        meta = json.load(open(SVG / f"{name}.json"))
        sw, sh = meta["w"], meta["h"]
        self.k = min(w / sw, h / sh)
        self.w, self.h = sw * self.k, sh * self.k
        self.x = x + {"l": 0, "c": (w - self.w) / 2, "r": w - self.w}[align]
        self.y = y + {"b": 0, "c": (h - self.h) / 2, "t": h - self.h}[valign]
        self.anchors = meta["anchors"]
        self.holes = meta.get("holes", {})
        self.name, self.svg = name, SVG / f"{name}.svg"
        self.scale = meta["scale"]
        self.sh = sh
        mg = 5 * self.k
        LAB.arts.append((self.x + mg, self.y + mg, self.x + self.w - mg, self.y + self.h - mg, name))
        HC.art(self)
        c.saveState()
        if clip_circle:
            p = c.beginPath()
            r = min(self.w, self.h) / 2
            self.cx, self.cy, self.r = self.x + self.w / 2, self.y + self.h / 2, r
            p.circle(self.cx, self.cy, r)
            c.clipPath(p, stroke=0, fill=0)
            c.setFillColor(WHITE)
            c.rect(self.x, self.y, self.w, self.h, stroke=0, fill=1)
        else:                                   # a cropped render's decals (silk text) can run past its crop
            p = c.beginPath()
            p.rect(self.x, self.y, self.w, self.h)
            c.clipPath(p, stroke=0, fill=0)
        c.translate(self.x, self.y)
        c.scale(self.k, self.k)
        renderPDF.draw(self.d, c, 0, 0)
        c.restoreState()
        if clip_circle:
            c.setStrokeColor(INK)
            lw(c, 2.2)
            c.circle(self.cx, self.cy, self.r, stroke=1, fill=0)
        if frame:
            c.setStrokeColor(INK)
            lw(c, 1.2)
            c.rect(self.x, self.y, self.w, self.h, stroke=1, fill=0)

    def A_raw(self, n):
        ax, ay = self.anchors[n]
        return self.x + ax * self.k, self.y + (self.sh - ay) * self.k

    def A(self, n):
        xy = self.A_raw(n)
        HC.lookup(self, n, xy)
        return xy

    def mm(self):
        """Points per mm on the page."""
        return self.scale * self.k


def zoom_link(c, art_big, anchor, zoom, color=INK):
    """Small circle on the overview and a line to the zoom circle."""
    px, py = art_big.A(anchor)
    c.setStrokeColor(color)
    lw(c, 1.4)
    c.circle(px, py, 6, stroke=1, fill=0)
    a = math.atan2(zoom.cy - py, zoom.cx - px)
    c.line(px + 6 * math.cos(a), py + 6 * math.sin(a), zoom.cx - zoom.r * math.cos(a), zoom.cy - zoom.r * math.sin(a))


# ------------------------------------------------------------------ page furniture (v1)
def page(c, step_no, title, sub, pg, slogan):
    LAB.reset(pg)
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(INK)
    c.rect(0, H - 92, W, 92, stroke=0, fill=1)
    c.setFillColor(HAZ)
    c.rect(M, H - 80, 78, 68, stroke=0, fill=1)
    text(c, M + 39, H - 69, step_no, 54, "HEAD", INK, "c")
    ts = 34
    room = W - 2 * M - 94 - pdfmetrics.stringWidth(PROTO, "MONO", 8) - 14
    while pdfmetrics.stringWidth(title, "HEAD", ts) > room:
        ts -= 1
    text(c, M + 94, H - 44, title, ts, "HEAD", WHITE)
    ss = 9
    while pdfmetrics.stringWidth(sub, "MONO", ss) > W - 2 * M - 95 and ss > 8:
        ss -= 0.25
    text(c, M + 95, H - 64, sub, ss, "MONO", HAZ)
    text(c, W - M, H - 26, PROTO, 8, "MONO", GREY, "r")
    text(c, W - M, H - 38, "UNIT: TX-STACK-R1", 8, "MONO", GREY, "r")
    c.saveState()
    p = c.beginPath()
    p.rect(0, H - 100, W, 8)
    c.clipPath(p, stroke=0)
    c.setFillColor(HAZ)
    c.rect(0, H - 100, W, 8, stroke=0, fill=1)
    c.setFillColor(INK)
    for i in range(-2, 80):
        q = c.beginPath()
        q.moveTo(i * 16, H - 100)
        q.lineTo(i * 16 + 8, H - 100)
        q.lineTo(i * 16 + 16, H - 92)
        q.lineTo(i * 16 + 8, H - 92)
        q.close()
        c.drawPath(q, stroke=0, fill=1)
    c.restoreState()
    c.setStrokeColor(INK)
    lw(c, 0.8)
    c.line(M, 34, W - M, 34)
    text(c, M, 20, slogan, 8, "MONO", INK)
    text(c, W - M, 20, f"{pg}", 8, "MONO", INK, "r")


class Grid:
    def __init__(self, cols, rows, top=H - 112, bottom=44, gap=10, heights=None):
        self.cols, self.rows = cols, rows
        self.top, self.bottom, self.gap = top, bottom, gap
        avail = top - bottom - gap * (rows - 1)
        hs = heights or [1] * rows
        self.hs = [avail * h / sum(hs) for h in hs]
        self.w = (W - 2 * M - gap * (cols - 1)) / cols

    def cell(self, col, row, span=1):
        x = M + col * (self.w + self.gap)
        y = self.top - sum(self.hs[:row + 1]) - self.gap * row
        return x, y, self.w * span + self.gap * (span - 1), self.hs[row]


CAP = 9          # caption size
CAP_LEAD = 11.5


def panel(c, cell, n, caption, warn=False):
    """Panel with badge and caption. Returns the free drawing area (x, y, w, h) above the caption."""
    x, y, w, h = cell
    c.setFillColor(WHITE)
    c.setStrokeColor(NEON if warn else INK)
    lw(c, 2.2 if warn else 1.4)
    c.rect(x, y, w, h, stroke=1, fill=1)
    lines = caption if isinstance(caption, list) else [caption]
    size = CAP
    while max(pdfmetrics.stringWidth(l, "MONO", size) for l in lines) > w - 20 and size > MIN_FINE:
        size -= 0.25
    for i, ln in enumerate(lines):
        text(c, x + 10, y + 10 + (len(lines) - 1 - i) * CAP_LEAD, ln, size, "MONO", NEON if warn else INK)
    cap_top = y + 10 + (len(lines) - 1) * CAP_LEAD + size + 4
    c.setStrokeColor(HexColor("#DDDDDD"))
    lw(c, 0.6)
    c.line(x + 8, cap_top, x + w - 8, cap_top)
    LAB.panels.append((x, y, x + w, y + h, cap_top))
    if n is not None:
        badge(c, x + 18, y + h - 18, n)
        LAB.block(x + 5, y + h - 31, x + 31, y + h - 5, "badge")
    return x + 4, cap_top + 4, w - 8, y + h - cap_top - 8


