"""Session 1 prep sheets for the TX stack, v2: cyberpunk flat-pack style, illustrations from real 3D geometry.

The illustrations are SVGs rendered by scenes.py (CadQuery + OpenCascade hidden lines + ray-cast flat colour, run in
the CAD venv). This script (reportlab + svglib venv) lays them out, adds every label on a paper chip with leaders
that stop at the chip edge, and checks the label layout for overlaps. Content, palette, fonts and page furniture are
v1's (../make_session1.py).

Usage: pdfenv/bin/python make_session1_v2.py OUT_DIR
"""
import json
import math
import sys
import textwrap
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import holecheck as HC  # noqa: E402
SVG = HERE / "svg"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out"
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

import re  # noqa: E402
_BUILD = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1/build")
_ASM = (_BUILD / "ASSEMBLY.md").read_text()
_BPMD = (_BUILD / "BACKPLANE.md").read_text()
assert "No inserts in the four corner posts" in _ASM and "EVM clip's two" in _ASM, \
    "ASSEMBLY.md section 2 step 3: printed lid bolts in the corner posts, M3 inserts for the bar and the EVM clip"
BP_SECS = dict(re.findall(r"^## (\d+)\. (.*)$", _BPMD, re.M))   # {"2": "Sockets (one per card; ...", ...}
BP_WIRING = [re.sub(r" \([^)]*\)", "", BP_SECS[k]) for k in ("2", "3", "4", "5")]   # sockets + key plugs, pins and parts, bus wires, leads
BP_FIT = re.sub(r" \([^)]*\)", "", BP_SECS["6"])                                    # "Fit it in the base"

MIN_LABEL, MIN_FINE, MIN_KEY = 9, 8, 12
PROTO = "PROTOCOL 01 // SESSION 1 // CARDS"   # set per session by the build loop


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
        return json.load(open(SVG / "s2_board.json"))["scale"] * self.k


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
    while pdfmetrics.stringWidth(title, "HEAD", ts) > W - 2 * M - 94 - 170:
        ts -= 1
    text(c, M + 94, H - 44, title, ts, "HEAD", WHITE)
    text(c, M + 95, H - 64, sub, 9, "MONO", HAZ)
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


# ------------------------------------------------------------------ pages
def _cover(c, pg, title, sub, items, mats, tasks, rules):
    page(c, "00", title, sub, pg, SLOGANS[0])
    g = Grid(2, 3, heights=[1.25, 0.95, 0.9])
    x, y, w, h = panel(c, g.cell(0, 0, 2), None, "REQUIRED APPARATUS. LAY IT ALL OUT BEFORE YOU BEGIN.")
    cw, rh = w / 6, h / 2
    for i, (name, art) in enumerate(items):
        col, row = i % 6, i // 6
        X, Y = x + cw * col, y + h - rh * (row + 1)
        if art:
            Art(c, art, X + 6, Y + 20, cw - 12, rh - 26)
        elif art is None:
            mask_icon(c, X + cw / 2, Y + 20 + (rh - 26) / 2, 1.0)
        chip(c, X + cw / 2, Y + 6, name, 9, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(0, 1), None, "MATERIAL ISSUED TO YOU.")
    n = len(mats)
    for i, (name, art) in enumerate(mats):
        Art(c, art, x + w * i / n + 6, y + 22, w / n - 12, h - 26)
        chip(c, x + w * (2 * i + 1) / (2 * n), y + 6, name, 9, "ALT", INK, "c")
    x, y, w, h = panel(c, g.cell(1, 1), None, f"THE {len(tasks)} TASKS. IN THIS ORDER.")
    for i, t in enumerate(tasks):
        text(c, x + 16, y + h - 22 - i * (h - 20) / max(4, len(tasks)), t, 17, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 2, 2), None, "STANDING ORDERS.", warn=True)
    for i, r in enumerate(rules):
        yy = y + h - 14 - i * (h - 14) / 4
        verdict(c, x + 22, yy, True, 10)
        text(c, x + 42, yy - 4, r, 11, "ALT", INK)
    mask_icon(c, x + w - 50, y + h / 2, 1.5)


def cover(c, pg):
    _cover(c, pg, "SESSION 1: PREP", "NO SOLDER. NO POWER. CARDS FIRST, THEN THE BASE: SNAP, LABEL, MEASURE, CUT, TEST-FIT.",
           [("CALIPERS", "tool_caliper"), ("STEEL RULER", "tool_ruler"), ("UTILITY KNIFE", "tool_knife"),
            ("2 C-CLAMPS", "tool_clamps"), ("SANDPAPER 120", "tool_sandpaper"),
            ("SHARPIE", "tool_marker"), ("FLAT FILE", "tool_file"), ("MASK", None), ("PHONE", "tool_phone"),
            ("IRON (INSERTS ONLY)", "")],
           [("1x PAD3U", "mat_pad3u"), ("4x SOLDERFUL", "mat_cards"), ("4x M3 INSERTS", "mat_base")],
           ["01  SNAP THE CARD RAILS", "02  LABEL. PHOTOGRAPH. REPORT.", "03  MEASURE THE INSERT",
            "04  CUT, TEST-FIT BACKPLANE", "05  REPORT THE BASE"],
           ["COUNT HOLES. DO NOT TRUST A RULER FOR POSITION.",
            "SCORE BOTH FACES. ALWAYS BOTH. FILE TO THE LINE, NEVER PAST IT.",
            "FIBREGLASS DUST: MASK ON, DAMP TOWEL UNDER, WASH HANDS AFTER.",
            "WRITE EVERY NUMBER DOWN. A NUMBER NOT WRITTEN DID NOT HAPPEN."])


def step1(c, pg):
    page(c, "03", "MEASURE THE INSERT", "ONE M3 HEAT-SET INSERT. TWO NUMBERS. THE BAR'S INSERT BORES DEPEND ON THEM.", pg,
         SLOGANS[1])
    g = Grid(2, 2)
    # 1: length
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["LENGTH: jaws on the two flat ends.", "Expected about 5.7 mm."])
    big = Art(c, "s1_len", x + 30, y + h - 128, w - 34, 128, valign="t")
    z = Art(c, "s1_len_zoom", x + w - 112, y + 2, 104, 104, clip_circle=True)
    zoom_link(c, big, "ins", z)
    (ax, ay), (bx, by) = z.A("e0"), z.A("e1")
    dim(c, ax, ay - 14, bx, by - 14, "", ticks=True)
    label(c, x + 14, y + 40, "L: FLAT END\nTO FLAT END", ax, ay - 14, 12, "ALT", NEON, lcolor=NEON, dot=False)
    # 2: diameter
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["WIDEST DIAMETER: across the knurl", "teeth, tip to tip. Expected ~4.6 mm."])
    big = Art(c, "s1_dia", x + 30, y + h - 128, w - 34, 128, valign="t")
    z = Art(c, "s1_dia_zoom", x + 4, y + 2, 104, 104, clip_circle=True)
    zoom_link(c, big, "ins", z)
    (dx0, dy0), (dx1, dy1) = z.A("e0"), z.A("e1")
    dim(c, dx0, dy0 + 4, dx1, dy1 + 4, "", ticks=True)
    e = Art(c, "s1_end", x + w - 92, y + 18, 80, 80)
    (ax, ay), (bx, by) = e.A("tipA"), e.A("tipB")
    dim(c, ax, ay, bx, by, "", ticks=True)
    chip(c, (ax + bx) / 2, y + 4, "D: TIP TO TIP", 12, "ALT", NEON, "c")
    chip(c, x + w - 52, y + 104, "END VIEW", 9, "ALT", INK, "c")
    # 3: wrong ways
    x, y, w, h = panel(c, g.cell(0, 1), 3, ["DO NOT measure the hole inside,", "or across the smooth collar."], warn=True)
    e = Art(c, "s1_end", x + 14, y + h / 2 - 50, 100, 100)
    (ax, ay), (bx, by) = e.A("boreA"), e.A("boreB")
    dim(c, ax, ay, bx, by, "", ticks=False)
    verdict(c, e.x + e.w - 4, e.y + e.h - 4, False)
    chip(c, e.x + e.w / 2, y + 4, "NOT THE BORE", 12, "ALT", NEON, "c")
    z = Art(c, "s1_collar", x + w - 128, y + h / 2 - 54, 108, 108, clip_circle=True)
    verdict(c, z.cx + z.r * 0.72, z.cy + z.r * 0.72, False)
    chip(c, z.cx, y + 4, "NOT THE COLLAR", 12, "ALT", NEON, "c")
    # 4: write it down
    x, y, w, h = panel(c, g.cell(1, 1), 4, ["Write both numbers here.", "Then send them to Claude."])
    for i, (lab, exp) in enumerate([("L =", "expected 5.7"), ("D =", "expected 4.6")]):
        yy = y + h - 64 - i * 74
        text(c, x + 24, yy, lab, 30, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 2)
        c.rect(x + 80, yy - 10, 120, 44, stroke=1, fill=0)
        text(c, x + 210, yy + 4, "mm", 18, "HEAD", INK)
        text(c, x + 80, yy - 24, exp, 9, "MONO", GREY)
    chip(c, x + 24, y + 36, "IF D IS NOT ABOUT 4.6:\nHOLE = D − 0.6", 13, "ALT", NEON, "l", border=NEON)


def step2a(c, pg):
    page(c, "02", "CUT THE BACKPLANE  1/3", "ONE L: 30 x 39 HOLES PLUS A TAB 1 x 3. FOUR SCORED EDGES. NO FACTORY EDGE.",
         pg, SLOGANS[3])
    g = Grid(1, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Stand the board on its short edge, FRONT face up: 38 holes across, 62 up. Leave ONE spare row of holes at",
        "the bottom and ONE at the right. The L: 30 lines (0-29) by 39 holes, plus a TAB of line -1 beside holes 1-3.",
        "Four cuts, each MIDWAY BETWEEN two rows of holes: A left of line -1, B above hole 39, C right of line 29,",
        "D below hole 1. Mark each with dots at both ends."])
    b = Art(c, "s2_board", x + 92, y + 22, 190, h - 28, align="l")
    (a0x, a0y), (a1x, a1y) = b.A("cutA0"), b.A("cutA1")
    (b0x, b0y), (b1x, b1y) = b.A("cutB0"), b.A("cutB1")
    (c0x_, c0y_), (c1x_, c1y_) = b.A("cutC0"), b.A("cutC1")
    (d0x, d0y), (d1x, d1y) = b.A("cutD0"), b.A("cutD1")
    dashed(c, a0x, a0y - 8, a1x, a1y + 8)
    dashed(c, b0x, b0y, b1x + 8, b1y)
    dashed(c, c0x_, c0y_ - 8, c1x_, c1y_)
    dashed(c, d0x, d0y, d1x, d1y)
    a1y = b0y                                  # top of the piece (cut B), for the dimensions below
    (s0x, s0y), (s1x, s1y), (c0x, c0y) = b.A("saw0"), b.A("saw1"), b.A("sc0")
    dashed(c, s0x, s0y, s1x, s1y, color=INK, w=1.2, d=(2, 2))
    blx, bly = b.A("bl")
    trx, try_ = b.A("tr")
    brx, bry = b.A("pbr")                      # the piece's bottom-right corner (cut C meets cut D)
    label(c, a0x - 64, a0y + 30, "CUT A", a0x, a0y + 26, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    label(c, b1x + 14, a1y + 44, "CUT B", b1x + 6, a1y, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    label(c, b1x + 40, a1y - 34, "CUT C", c1x_, a1y - 44, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    label(c, a0x - 64, a0y + 6, "CUT D", d0x + 24, d0y, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    tx_, ty_ = b.A("tab")
    label(c, a0x - 86, a0y + 64, "TAB: LINE -1,\nHOLES 1-3", tx_, ty_, 9, "ALT", INK)
    wx, wy = b.A("waste")
    label(c, a0x - 86, wy + 6, "GREY STRIP:\nWASTE, SAWN\nOFF IN PANEL 4", wx, wy, 9, "ALT", INK)
    dim(c, s0x, a1y + 22, brx, a1y + 22, "30 HOLES + TAB", 12, INK, lx=(s0x + brx) / 2, ly=a1y + 34)
    dim(c, b1x + 30, bry, b1x + 30, a1y, "39 HOLES", 13, INK, lx=b1x + 30, ly=(bry + a1y) / 2 + 20)
    chip(c, (a0x + brx) / 2 + 4, (bry + a1y) / 2 - 8, "PIECE", 20, "HEAD", INK, "c")
    chip(c, (blx + trx) / 2, try_ - 22, "SPARE", 16, "HEAD", INK, "c")
    chip(c, (blx + trx) / 2, y + 6, "ONE SPARE ROW STAYS BELOW AND RIGHT OF THE PIECE", 9, "ALT", INK, "c")
    chip(c, x + 4, y + h - 50, "FRONT FACE UP\n(the face you\nwill mark FRONT)", 9, "ALT", INK)
    zx = x + w - 156
    ok = Art(c, "s2_patch", zx, y + h - 120, 112, 96, align="l", valign="t", frame=True)
    (gx0, gy0), (gx1, gy1) = ok.A("gap_bot"), ok.A("gap_top")
    dashed(c, gx0, gy0 - 6, gx1, gy1 + 6, w=2.4)
    verdict(c, ok.x + ok.w + 16, ok.y + ok.h - 12, True)
    chip(c, ok.x + ok.w / 2 + 10, ok.y + ok.h + 8, "SCORE HERE: IN THE GAP", 10, "ALT", NEON, "c")
    bad = Art(c, "s2_patch", zx, y + 52, 112, 96, align="l", valign="b", frame=True)
    (hx0, hy0), (hx1, hy1) = bad.A("hole_bot"), bad.A("hole_top")
    dashed(c, hx0, hy0 - 6, hx1, hy1 + 6, w=2.4)
    verdict(c, bad.x + bad.w + 16, bad.y + bad.h - 12, False)
    chip(c, bad.x, bad.y - 18, "NOT THROUGH THE HOLES:\nTHE EDGE BREAKS\nRAGGED", 9, "ALT", NEON)
    # 2: the score
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Clamp the steel ruler on the PIECE side of the line. Draw the knife along it 10 times, light then firm.",
        "Flip the board, line up on the same gap from the dots, score 10 more. All four cuts, both faces.",
        "The short tab score (above hole 3, across line -1 only) comes after the snap: panel 4."])
    s = Art(c, "s2_score", x + 36, y + 4, 290, h - 30, align="l", valign="b")
    (t0x, t0y) = s.A("tip")
    label(c, s.x - 30, s.y + 40, "KNIFE ON\nTHE LINE.\nPULL TOWARD\nYOU.", t0x, t0y, 9, color=INK)
    label(c, s.x + s.w + 8, s.y + s.h - 14, "CLAMP", *s.A("clamp"), 9)
    label(c, s.x + s.w + 8, s.y + 30, "DAMP TOWEL\nUNDER THE WORK", *s.A("towel"), 9)
    tx = x + 350
    times(c, tx + 20, y + h - 70, "x10")
    curved_arrow(c, tx + 90, y + h - 58, 24, 200, -60, INK)
    chip(c, tx + 90, y + h - 104, "FLIP", 14, "HEAD", INK, "c")
    times(c, tx + 165, y + h - 70, "x10")
    chip(c, tx + 100, y + 60, "CUTS A, B, C AND D.\nBOTH FACES. x10 EACH.", 12, "ALT", NEON, "c", border=NEON)


def step2b(c, pg):
    page(c, "02", "CUT THE BACKPLANE  2/3", "SNAP CUTS A TO D. SAW THE TAB STEP. SAND EVERY EDGE.", pg, SLOGANS[4])
    g = Grid(1, 3, heights=[1, 1.15, 1])
    # 3: snap
    x, y, w, h = panel(c, g.cell(0, 0), 3, [
        "Snap A, then B, then C, then D. Score line exactly on the table edge. Hold the big side flat. Push the",
        "overhang down hard. Snap. The thin spare rows (C, D) snap the same way. Left: a rectangle 31 holes by 39."])
    s = Art(c, "s2_snap", x + 60, y + 2, 240, h - 4, align="l")
    hx, hy = s.A("hold")
    px, py = s.A("push")
    arrow(c, hx, hy + 44, hx, hy + 6, INK, 3)
    chip(c, hx, hy + 50, "HOLD", 12, "HEAD", INK, "c")
    arrow(c, px, py + 44, px, py + 6, NEON, 3.5, 12)
    chip(c, px, py + 50, "PUSH", 12, "HEAD", NEON, "c")
    ex, ey = s.A("edgeL")
    label(c, x + 6, y + 18, "SCORE LINE ON\nTHE TABLE EDGE", ex, ey, 9)
    # 4: the tab step
    x, y, w, h = panel(c, g.cell(0, 1), 4, [
        "Remove the grey strip (line -1, holes 4-39). Score across line -1 only, midway between holes 3 and 4, both",
        "faces. Clamp the piece with the strip over the table edge. Hacksaw DOWN the gap between line -1 and line 0,",
        "from cut B to that score. The strip breaks off there. Leave the 3 holes of line -1 below it: that is the tab."])
    z = Art(c, "s2_tabzoom", x + 44, y + 4, 100, h - 14, align="l")
    (s0x, s0y), (s1x, s1y), (c0x, c0y) = z.A("saw0"), z.A("saw1"), z.A("sc0")
    dashed(c, s0x, s0y + 4, s1x, s1y, w=2.4)
    dashed(c, c0x - 6, c0y, s1x, s1y, color=INK, w=2.0, d=(3, 2))
    label(c, z.x + z.w + 14, s0y - 6, "HACKSAW:\nBETWEEN LINE -1\nAND LINE 0", s0x + 1, s0y - 14, 9, "ALT", NEON,
          lcolor=NEON, dot=False)
    label(c, z.x + z.w + 14, c0y + 4, "SCORE ABOVE\nHOLE 3", s1x - 4, s1y, 9, "ALT", INK)
    label(c, z.x + z.w + 14, z.y + 14, "TAB: LINE -1,\nHOLES 1-3", *z.A("hm1_1"), 9, "ALT", INK)
    sw = Art(c, "s2_saw", x + 270, y + 12, w - 276, h - 20, align="r")
    label(c, x + 300, y + 22, "STRIP OVER THE TABLE EDGE", *sw.A("front"), 9, "ALT", INK)
    # 5: sand and check
    x, y, w, h = panel(c, g.cell(0, 2), 5, [
        "Sand every edge flat on paper on the table. For the long left edge, let the tab hang off the end",
        "of the table. File the sawn inside corner flat. CHECK, above the tab: left edge to the near side",
        "of line 0's holes = 0.5 to 1.2 mm."])
    s = Art(c, "s2_sand", x + 50, y + 4, 230, h - 8, align="l")
    (a0x, a0y), (a1x, a1y) = s.A("a0"), s.A("a1")
    arrow(c, (a0x + a1x) / 2, (a0y + a1y) / 2 + 26, a0x, a0y + 26, INK, 2)
    arrow(c, (a0x + a1x) / 2, (a0y + a1y) / 2 + 26, a1x, a1y + 26, INK, 2)
    label(c, s.x + s.w + 10, s.y + 20, "TAB HANGS OFF\nTHE END", *s.A("tab"), 9)
    e = Art(c, "s2_edge", x + w - 200, y + 18, 98, h - 30, frame=True)
    (ex, ey), (hx, hy) = e.A("edge"), e.A("hole_near")
    c.setStrokeColor(NEON)
    lw(c, 0.8)
    c.line(ex, ey - 16, ex, ey + 16)
    c.line(hx, hy - 16, hx, hy + 16)
    dim(c, ex, ey - 12, hx, hy - 12, "", 12, NEON, ticks=False, w=1.0)
    label(c, e.x + e.w + 14, ey - 30, "0.5 – 1.2 MM", (ex + hx) / 2, ey - 12, 12, "ALT", NEON, "l", lcolor=NEON)
    label(c, e.x + e.w + 14, e.y + e.h - 10, "LINE 0,\nABOVE THE TAB", *e.A("line0"), 9)


def step2c(c, pg):
    page(c, "02", "CUT THE BACKPLANE  3/3", "DRILL THREE HOLES. MARK THE FRONT.", pg, SLOGANS[4])
    g = Grid(1, 2, heights=[1.75, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 6, [
        "FRONT face up, TAB at the BOTTOM-LEFT. Write FRONT on this face. Count from the tab: line 0 is just",
        "right of it, hole 1 is the bottom row. Drill 3.2 mm through three pads: line 0 hole 2 (in the tab's",
        "width), line 20 hole 2 and line 20 hole 36. Line 20 is NOT the right edge: lines 21-29 go on past it.",
        "No other holes on line 0."])
    d = Art(c, "s2_drill", x + 150, y + 18, 240, h - 32, align="l")
    for nm, s, side in (("d0_2", "LINE 0\nHOLE 2", -1), ("d20_2", "LINE 20\nHOLE 2", 1), ("d20_36", "LINE 20\nHOLE 36", 1)):
        px, py = d.A(nm)
        c.setStrokeColor(NEON)
        lw(c, 1.6)
        c.circle(px, py, 6, stroke=1, fill=0)
        if nm == "d20_36":
            label(c, d.x + d.w + 16, py - 36, s, px + 6, py - 2, 12, "ALT", NEON, "l", lcolor=NEON, dot=False)
        elif side < 0:
            label(c, d.x - 40, py + 34, s, px - 6, py + 2, 12, "ALT", NEON, "r", lcolor=NEON, dot=False)
        else:
            label(c, d.x + d.w + 16, py + 30, s, px + 6, py + 2, 12, "ALT", NEON, "l", lcolor=NEON, dot=False)
    (lbx, lby), (ltx, lty) = d.A("h0_4"), d.A("l0top")
    c.setStrokeColor(NEON)
    lw(c, 1.4)
    c.setDash(4, 2)
    c.line(lbx, lby - 4, ltx, lty + 6)
    c.setDash()
    verdict(c, d.x - 30, (lby + lty) / 2 + 58, False, 11)
    chip(c, d.x - 18, (lby + lty) / 2 + 10, "NO OTHER HOLES\nON LINE 0:\nABOVE THE TAB\nTHIS EDGE GOES\nIN THE GROOVE",
         12, "ALT", NEON, "r")
    (l0x, l0y), (l20x, _) = d.A("h1"), d.A("l20bot")
    blx, bly = d.A("bl")
    brx, bry = d.A("br")
    trx, tr_y = d.A("tr")
    l29x, _ = d.A("l29bot")
    chip(c, l0x + 4, d.y + d.h + 1, "LINE 0", 9, "ALT", INK, "c")
    chip(c, l20x, d.y + d.h + 1, "LINE 20", 9, "ALT", INK, "c")
    chip(c, l29x, d.y + d.h + 1, "LINE 29", 9, "ALT", INK, "c")
    chip(c, (blx + brx) / 2, bly - 15, "ALL FOUR EDGES SCORED AND SANDED: NO FACTORY EDGE", 9, "ALT", INK, "c")
    label(c, d.x - 40, bly + 4, "TAB = LINE -1\n(BOTTOM-LEFT)", *d.A("lm1"), 9, "ALT", INK, "r")
    _, h39y = d.A("h39")
    chip(c, trx + 8, h39y - 3, "HOLE 39", 9, "ALT", INK)
    chip(c, trx + 8, l0y - 3, "HOLE 1", 9, "ALT", INK)
    # 7: the tab hole close-up + drilling
    x, y, w, h = panel(c, g.cell(0, 1), 7, [
        "Line 0 hole 2 sits inside the tab's width: about 2.2 mm of board stays to its left. Drill slowly so",
        "it does not split out. Drill from FRONT, board on scrap wood, slow speed, light pressure.",
        "Then blow the dust off. Outside."])
    t = Art(c, "s2_tab", x + 44, y + 20, 120, h - 24, align="l")
    (tlx, tly), (hlx, hly) = t.A("tab_l"), t.A("hole_l")
    c.setStrokeColor(NEON)
    lw(c, 0.8)
    yd = t.y - 9
    c.line(tlx, tly - 2, tlx, yd - 4)
    c.line(hlx, hly - 2, hlx, yd - 4)
    dim(c, tlx, yd, hlx, yd, "", 12, NEON, ticks=False, w=1.0)
    label(c, t.x + t.w + 14, yd - 4, "ABOUT 2.2 MM", hlx, yd, 12, "ALT", NEON, "l", lcolor=NEON, dot=False)
    label(c, t.x + t.w + 14, t.y + t.h - 30, "LINE 0 HOLE 2\n3.2 MM", *t.A("hole"), 10, "ALT", NEON, "l",
          lcolor=NEON)
    tx = x + 300
    Art(c, "tool_drill", tx, y + h - 40, 150, 30, align="l")
    chip(c, tx + 75, y + h - 62, "3.2 MM", 18, "HEAD", INK, "c")
    mask_icon(c, tx + 30, y + 30, 1.1)
    chip(c, tx + 64, y + 34, "MASK ON.\nDAMP TOWEL UNDER.\nWASH HANDS AFTER.", 9, "ALT", NEON, border=NEON)


def ringm(c, px, py, r=6, color=NEON, w=1.8):
    HC.mark(px, py, "ring")
    c.setStrokeColor(WHITE)
    lw(c, w + 1.6)
    c.circle(px, py, r, stroke=1, fill=0)
    c.setStrokeColor(color)
    lw(c, w)
    c.circle(px, py, r, stroke=1, fill=0)


def bp1(c, pg):
    page(c, "04", "BACKPLANE  1/5: FIND THE PLATED END",
         "ONE PAD3U. KEEP THE END WITH THE TWO BIG HOLES: 31 ROWS OF 38 HOLES. ONE CUT ONLY.", pg, SLOGANS[3])
    g = Grid(2, 2, heights=[1.45, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "FRONT is the face with the PadBoard-3U ... BusBoard.net legend. Big holes on the RIGHT, the legend reading",
        "up beside them, LINE 30's lone square pad 4th from you (hole 4): that face up is FRONT, bus wires on the BACK.",
        "Count 31 rows in from the right: line 30 is beside the big holes, line 0 is the 31st. Every line",
        "keeps all 38 holes, hole 1 the row nearest you. Dot each end of the gap left of line 0: the only cut."])
    b = Art(c, "b_board", x + 70, y + 30, 330, h - 64, align="l")
    (s0x, s0y), (s1x, s1y) = b.A("score0"), b.A("score1")
    dashed(c, s0x, s0y - 10, s1x, s1y + 10, w=2.4, halo=WHITE)
    for px, py in ((s0x, s0y), (s1x, s1y)):
        c.setFillColor(INK)
        c.circle(px, py + (3 if py < s0y + 1 else -3), 2.2, stroke=0, fill=1)
    label(c, s1x - 60, s1y + 22, "SCORE HERE: THE ONLY CUT", s1x, s1y + 10, 12, "HEAD", NEON, "r", dot=False)
    mhx, mhy = b.A("mh_hi")
    ringm(c, mhx, mhy, 5)
    ringm(c, *b.A("mh_lo"), 5)
    (brx, bry), (trx, tr_y) = b.A("br"), b.A("tr")
    label(c, brx + 14, (bry + tr_y) / 2 + 40, "PLATED END:\nTWO BIG HOLES", mhx + 5, mhy - 2, 10, "ALT", INK)
    plx, ply = b.A("plain_hi")
    _, h1y = b.A("h30_1")
    _, h38y = b.A("h30_38")
    label(c, b.x - 8, h38y - 50, "OTHER END:\nTWO SMALL\nPLAIN HOLES", plx, ply, 9, "ALT", INK, "r")
    chip(c, b.x - 6, h38y - 3, "HOLE 38", 9, "ALT", INK, "r")
    chip(c, b.x - 6, h1y - 3, "HOLE 1", 9, "ALT", INK, "r")
    (l0x, l0y), (l29x, _) = b.A("h0_38"), b.A("h30_38")
    chip(c, l0x + 2, b.y + b.h + 8, "LINE 0", 9, "ALT", INK, "c")
    chip(c, l29x - 2, b.y + b.h + 8, "LINE 30", 9, "ALT", INK, "c")
    dim(c, s0x, bry - 14, brx, bry - 14, "31 ROWS = LINES 0-30", 11, INK, lx=(s0x + brx) / 2, ly=bry - 28)
    dim(c, brx + 120, bry, brx + 120, tr_y, "38 HOLES", 11, INK, lx=brx + 120, ly=(bry + tr_y) / 2 - 40)
    chip(c, *b.A("piece"), "KEEP", 20, "HEAD", INK, "c")
    chip(c, *b.A("spare"), "SPARE", 16, "HEAD", INK, "c")
    chip(c, x + 4, bry - 30, "LEGEND FACE UP\n= FRONT (BIG HOLES\nRIGHT, HOLE 1 NEAR)", 9, "ALT", INK)
    # 2: the plated end from the BACK face
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The plated end from the BACK face (bus-wire", "side), turned over top-to-bottom like Clint's",
        "scan: the big plated hole, no pad beside it."])
    e = Art(c, "b_end", x + 6, y + 6, w * 0.62, h - 12, align="l")
    label(c, e.x + e.w + 10, e.y + e.h - 18, "BIG PLATED HOLE\n2.8 MM", *e.A("mh"), 9, "ALT", INK)
    label(c, e.x + e.w + 10, e.y + e.h - 62, "NO PAD HERE", *e.A("missing"), 9, "ALT", INK)
    label(c, e.x + e.w + 10, e.y + 20, "LINE 30: THE\nEND ROW", *e.A("end_row"), 9, "ALT", INK)
    # 3: where to score
    x, y, w, h = panel(c, g.cell(1, 1), 3, [
        "The cut runs IN THE GAP between line 0 and", "the next row out, never through the holes.",
        "It ends 1.27 mm from line 0's hole centres."])
    ok = Art(c, "b_patch", x + 16, y + 30, w / 2 - 30, h - 54, frame=True)
    (gx0, gy0), (gx1, gy1) = ok.A("gap_bot"), ok.A("gap_top")
    dashed(c, gx0, gy0 - 6, gx1, gy1 + 6, w=2.4)
    verdict(c, ok.x + ok.w - 6, ok.y + ok.h + 12, True)
    chip(c, ok.x + ok.w / 2, y + 8, "IN THE GAP", 10, "ALT", NEON, "c")
    bad = Art(c, "b_patch", x + w / 2 + 14, y + 30, w / 2 - 30, h - 54, frame=True)
    (hx0, hy0), (hx1, hy1) = bad.A("hole_bot"), bad.A("hole_top")
    dashed(c, hx0, hy0 - 6, hx1, hy1 + 6, w=2.4)
    verdict(c, bad.x + bad.w - 6, bad.y + bad.h + 12, False)
    chip(c, bad.x + bad.w / 2, y + 8, "THROUGH HOLES: RAGGED", 9, "ALT", NEON, "c")


def bp3(c, pg):
    page(c, "04", "BACKPLANE  2/5: SCORE AND SNAP", "LEFT EDGE ONLY. BOTH FACES. x10 EACH.", pg, SLOGANS[4])
    g = Grid(1, 2, heights=[1.25, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Clamp the steel ruler on the KEEP side of the dots (right). Knife along it 10 times, light then firm, in the",
        "gap. Flip the board over top-to-bottom, line up on the same gap from the dots, score 10 more. Nothing to drill."])
    s = Art(c, "b_score", x + 110, y + 4, 290, h - 10, align="l", valign="b")
    label(c, x + 6, s.y + 40, "KNIFE ON\nTHE LINE.\nPULL TOWARD\nYOU.", *s.A("tip"), 9, color=INK)
    label(c, x + 6, s.y + s.h - 14, "CLAMP", *s.A("clamp"), 9)
    label(c, s.x + s.w + 8, s.y + 40, "DAMP TOWEL\nUNDER THE WORK", *s.A("towel"), 9)
    tx = x + w - 150
    times(c, tx + 8, y + h - 70, "x10")
    curved_arrow(c, tx + 76, y + h - 58, 22, 200, -60, INK)
    chip(c, tx + 76, y + h - 102, "FLIP", 14, "HEAD", INK, "c")
    times(c, tx + 108, y + h - 70, "x10")
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Score line exactly on the table edge. Hold the KEEP side flat on the table. Push the spare down hard. Snap."])
    s = Art(c, "b_snap", x + 80, y + 2, 300, h - 4, align="l")
    hx, hy = s.A("hold")
    px, py = s.A("push")
    arrow(c, hx, hy + 44, hx, hy + 6, INK, 3)
    chip(c, hx, hy + 50, "HOLD", 12, "HEAD", INK, "c")
    arrow(c, px, py + 44, px, py + 6, NEON, 3.5, 12)
    chip(c, px, py + 50, "PUSH", 12, "HEAD", NEON, "c")
    label(c, x + w - 150, y + 30, "SCORE LINE ON\nTHE TABLE EDGE", *s.A("edgeR"), 9)


def bp4(c, pg):
    page(c, "04", "BACKPLANE  3/5: SAND. CHECK. MARK.", "THE NEW EDGE FLAT. TWO NUMBERS. ONE WORD.", pg, SLOGANS[1])
    g = Grid(2, 2, heights=[1.1, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "Sand the snapped LEFT edge flat on paper on the table, the board standing on that edge. CHECK: the edge to the",
        "near side of line 0's holes = 0.5 to 1.2 mm (1.27 mm to their centres). Over that, sand more: it must fit",
        "the left wall's groove."])
    s = Art(c, "b_sand", x + 40, y + 4, 230, h - 8, align="l")
    (a0x, a0y), (a1x, a1y) = s.A("a0"), s.A("a1")
    arrow(c, (a0x + a1x) / 2, (a0y + a1y) / 2 + 26, a0x, a0y + 26, INK, 2)
    arrow(c, (a0x + a1x) / 2, (a0y + a1y) / 2 + 26, a1x, a1y + 26, INK, 2)
    e = Art(c, "b_edge", x + w - 230, y + 18, 98, h - 30, frame=True)
    (ex, ey), (hx, hy) = e.A("edge"), e.A("hole_near")
    c.setStrokeColor(NEON)
    lw(c, 0.8)
    c.line(ex, ey - 16, ex, ey + 16)
    c.line(hx, hy - 16, hx, hy + 16)
    dim(c, ex, ey - 12, hx, hy - 12, "", 12, NEON, ticks=False, w=1.0)
    label(c, e.x + e.w + 14, ey - 30, "0.5 TO 1.2 MM", (ex + hx) / 2, ey - 12, 12, "ALT", NEON, "l", lcolor=INK)
    label(c, e.x + e.w + 14, e.y + e.h - 10, "LINE 0", *e.A("line0"), 9)
    # 2: the factory right edge
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The RIGHT edge is factory: no cut. Measure", "line 30's hole centres to that edge. Write",
        "it down: expected 5.48, at most 6.13."])
    r = Art(c, "b_right", x + 20, y + 14, w * 0.5, h - 20, align="l")
    (lx, ly), (ex2, ey2) = r.A("l30"), r.A("edge")
    c.setStrokeColor(NEON)
    lw(c, 0.8)
    c.line(lx, ly - 4, lx, r.y - 4)
    c.line(ex2, ey2 - 4, ex2, r.y - 4)
    dim(c, lx, r.y - 2, ex2, r.y - 2, "", 12, NEON, ticks=False, w=1.0)
    label(c, r.x + r.w + 14, r.y + 6, "___ MM\n(5.48; MAX 6.13)", (lx + ex2) / 2, r.y - 2, 12, "ALT", NEON,
          lcolor=INK, dot=False)
    label(c, r.x + r.w + 14, r.y + r.h - 10, "LINE 30", *r.A("l29top"), 9)
    # 3: meter + mark
    x, y, w, h = panel(c, g.cell(1, 1), 3, [
        "Meter two neighbouring pads anywhere: OPEN", "(the PAD3U has no strips). Legend face up,",
        "big holes RIGHT: write FRONT on that face."])
    text(c, x + 30, y + h - 40, "PAD TO PAD:", 16, "HEAD", INK)
    text(c, x + 30, y + h - 66, "OPEN. NO BEEP.", 20, "HEAD", NEON)
    text(c, x + 30, y + h - 110, "FRONT", 30, "HEAD", INK)
    text(c, x + 130, y + h - 100, "SHARPIE, NEAR LINE 0", 9, "ALT", INK)
    text(c, x + 130, y + h - 112, "HOLE 38. OTHER FACE: BACK", 9, "ALT", INK)
    verdict(c, x + w - 30, y + h - 34, True)


def bp5(c, pg):
    page(c, "04", "BACKPLANE  4/5: READY THE BASE",
         "4 M3 INSERTS: THE BAR AND THE EVM CLIP. NONE IN THE CORNER POSTS.", pg,
         SLOGANS[0])
    g = Grid(2, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "Enclosure 4's base from the lid side, bottom wall at the bottom; all printed in, pad tops at 8.0. Positions",
        "are (Xb, Zb) mm from the left and bottom walls. No backplane screws. M3 inserts (ringed): BAR 1, BAR 2 and",
        "the EVM clip's two (down into the ledge tops). The four corner posts take printed lid bolts: no inserts."])
    p = Art(c, "f_plan", x + 130, y + 6, 240, h - 12)
    bolts = [p.A(f"bolt_{k}") for k in range(4)]     # cage.corners(): bottom left, top left, bottom right, top right
    label(c, p.x - 14, bolts[1][1] + 6, "LID BOLT POST\n(PRINTED BOLT)", bolts[1][0] - 5, bolts[1][1], 10, "ALT", INK, "r")
    label(c, p.x + p.w + 20, bolts[3][1] + 6, "LID BOLT POST (PRINTED BOLT)", bolts[3][0] + 5, bolts[3][1], 10, "ALT", INK)
    label(c, p.x - 14, bolts[0][1] - 4, "LID BOLT POST\n(PRINTED BOLT)", bolts[0][0] - 5, bolts[0][1], 10, "ALT", INK, "r")
    label(c, p.x + p.w + 20, bolts[2][1] - 4, "LID BOLT POST (PRINTED BOLT)", bolts[2][0] + 5, bolts[2][1], 10, "ALT", INK)
    for k, txt in ((0, "CLIP INSERT (M3), LEFT KEEPER"), (1, "CLIP INSERT (M3), RIGHT BLOCK")):
        cx0, cy0 = p.A(f"clip_{k}")
        ringm(c, cx0, cy0, 6)
        if k == 0:
            label(c, p.x - 14, cy0 - 26, txt.replace(", ", ",\n"), cx0 - 6, cy0, 10, "ALT", NEON, "r", lcolor=INK, dot=False)
        else:
            label(c, p.x + p.w + 20, cy0 - 26, txt, cx0 + 6, cy0, 10, "ALT", NEON, lcolor=INK, dot=False)
    rx = p.x + p.w + 20
    sx_, sy_ = p.A("post_s24_31")
    label(c, rx, sy_ - 4, "SUPPORT DIA 6 AT (68.74, 127.72)", sx_, sy_, 10, "ALT", INK)
    spx, spy = p.A("post_s28_16")
    label(c, rx, spy - 4, "SUPPORT DIA 6 AT (78.90, 89.62)", spx + 6, spy, 10, "ALT", INK)
    s2x, s2y = p.A("post_s20_2")
    label(c, rx, s2y + 34, "SUPPORT DIA 6 AT (58.58, 54.06)", s2x, s2y + 4, 10, "ALT", INK)
    gx, gy = p.A("groove")
    label(c, p.x - 14, gy + 10, "LEFT WALL\nGROOVE", gx, gy, 9, "ALT", INK, "r")
    for nm, txt in (("bar_lo", "BAR 1 INSERT\nAT (5.00, 76.50)"), ("bar_hi", "BAR 2 INSERT\nAT (5.00, 146.50)")):
        bx_, by_ = p.A(nm)
        ringm(c, bx_, by_, 7)
        label(c, p.x - 14, by_ + (30 if nm == "bar_lo" else -4), txt, bx_ - 7, by_, 10, "ALT", NEON, "r", lcolor=INK,
              dot=False)
    cx_, cy_ = p.A("slot_mid")
    label(c, rx, cy_ - 6, "CORNER POST: SLOT 6.5 DEEP", cx_, cy_, 10, "ALT", INK)
    # 2: the slot
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The RIGHT CORNER POST's slot takes the", "board's right edge: 6.5 deep, 8.0 to 10.1",
        "above the floor. Run an offcut along it."])
    sl = Art(c, "f_slot", x + 6, y + 20, w - 12, h - 52, valign="b")
    label(c, x + 60, y + h - 18, "PAD3U OFFCUT", *sl.A("offcut_tail"), 10, "ALT", INK)
    chip(c, x + w / 2, y + 4, "SLIDES FREELY, END TO END: OK", 10, "ALT", NEON, "c")
    # 3: the two inserts
    x, y, w, h = panel(c, g.cell(1, 1), 3, [
        "Iron on, no solder. One M3 insert, flush, in", "each of BAR 1, BAR 2 and the two EVM clip",
        "bores (ASSEMBLY.md 2.3). Corners: none.", "BAR 1 has 0.48 of plastic over the B4 slot:",
        "light pressure, iron not past flush. Then run", "a PAD3U offcut down the B4 slot from the",
        "front; file the slot if it binds."])
    mb = Art(c, "mat_base", x + 10, y + h - 58, w - 20, 50)
    chip(c, mb.A("m3_bar")[0], y + h - 70, "BAR x2", 9, "ALT", INK, "c")
    chip(c, mb.A("m3_clip")[0], y + h - 70, "CLIP x2", 9, "ALT", INK, "c")
    chip(c, x + 10, y + 56, "2 x M3 HEAT-SET INSERT (BAR 1, BAR 2)", 9, "ALT", INK)
    chip(c, x + 10, y + 40, "2 x M3 HEAT-SET INSERT (EVM CLIP)", 9, "ALT", INK)
    chip(c, x + 10, y + 24, "ALL PAD TOPS LEVEL: 8.0 ABOVE THE FLOOR", 9, "ALT", NEON)
    chip(c, x + 10, y + 8, "OFFCUT SLIDES THE WHOLE B4 SLOT: OK", 9, "ALT", NEON)


def bp6(c, pg):
    page(c, "04", "BACKPLANE  5/5: TEST-FIT IT. OUT AGAIN.",
         "THE BARE BOARD: IN, CHECK, OUT. NO SCREWS, EVER: THE CARDS HOLD IT.", pg, SLOGANS[2])
    g = Grid(2, 3, heights=[1, 1, 1])
    steps = [("f_tilt", ["TILT IT. FRONT up, BACK face down. Push the", "right edge into the corner post's slot, to",
                         "the slot's end. The left edge clears the wall."]),
             ("f_slide", ["LOWER the left side onto the three", "support pads, BACK face down."]),
             ("f_home", ["SLIDE it 2.84 mm LEFT: left edge into the", "groove, right edge 3.66 in the slot. No",
                         "screws: plugged in, the cards hold it."])]
    for i, (art, cap) in enumerate(steps):
        x, y, w, h = panel(c, g.cell(0, i), i + 1, cap)
        a = Art(c, art, x + 10, y + 22, w - 20, h - 50, valign="c")
        if art == "f_slide":
            lx, ly = a.A("left_edge")
            arrow(c, lx + 40, ly + 24, lx + 10, ly + 24, NEON, 2.4)
            chip(c, lx + 60, ly + 36, "2.84 MM LEFT NEXT", 10, "ALT", NEON, "c")
        if art == "f_tilt":
            label(c, a.x + a.w - 10, a.y + a.h + 6, "RIGHT EDGE IN THE SLOT", *a.A("slot_end"), 9, "ALT", INK, "r")
        if art == "f_home":
            label(c, a.x + 10, a.y - 12, "LEFT EDGE IN THE GROOVE", *a.A("groove"), 9, "ALT", INK)
    cell = (g.cell(1, 0)[0], g.cell(1, 2)[1], g.cell(1, 0)[2], g.cell(1, 0)[1] + g.cell(1, 0)[3] - g.cell(1, 2)[1])
    x, y, w, h = panel(c, cell, 4, [
        "Seated, from the lid side: flat on all", "three pads. Then",
        "OUT: slide it right, lift the left side,", "tilt the right edge out of the slot.",
        "Wiring it is a later session; then it goes", f"back for good: {BP_FIT.lower()},",
        "held by the cards (BACKPLANE.md 6)."])
    wl = "LATER (BACKPLANE.md 2-5): " + "; ".join(t.upper() for t in BP_WIRING) + "."
    wl = textwrap.wrap(wl, 36)
    for k, ln in enumerate(wl):
        chip(c, x + 36, y + h - 14 - 13 * k, ln, 8.5, "ALT", NEON)
    d = Art(c, "f_done", x + 6, y + 30, w - 12, h - 40 - 13 * len(wl) - 18)
    label(c, d.x + d.w - 110, d.y + d.h + 10, "BOTH BIG HOLES: EMPTY", *d.A("upper_mh"), 9, "ALT", INK)


def step3(c, pg):
    page(c, "01", "SNAP THE CARD RAILS", "FOUR SOLDERFUL CARDS. THE TWO BACK RAILS COME OFF. BEFORE ANY SOLDER.", pg,
         SLOGANS[5])
    g = Grid(2, 3, heights=[1.35, 1, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "Columns 1-30. From the FRONT edge: two front rails, a number row, rows A-E, the channel, rows F-J,",
        "the J-side number row, then the two BACK rails. MEASURE front edge to the snap line (between the",
        "J-side numbers and the first back rail). The model says 41.91 mm. Write down what YOU measure."])
    a = Art(c, "s3_card", x + 96, y + 2, 290, h - 4, align="l")
    (sl, sly), (sr, sry) = a.A("snapL"), a.A("snapR")
    dashed(c, sl - 10, sly, sr + 10, sry, color=HAZ, w=2.4, halo=INK)   # never magenta on the red card
    flx, fly = a.A("fl")
    frx, fry = a.A("fr")
    brx, bry = a.A("br")
    label(c, sr + 22, sry + 16, "SNAP LINE", sr + 10, sry, 12, "HEAD", NEON, lcolor=NEON, dot=False)
    dim(c, sr + 34, fry, sr + 34, sry, "", 12)
    chip(c, sr + 42, sry - 34, "MEASURE", 13, "HEAD", NEON)
    chip(c, sr + 42, sry - 50, "model: 41.91 mm", 9, "MONO", NEON)
    # bracket: the back rails come off
    c.setStrokeColor(INK)
    lw(c, 1.4)
    c.line(flx - 8, sly + 2, flx - 8, bry)
    c.line(flx - 8, sly + 2, flx - 4, sly + 2)
    c.line(flx - 8, bry, flx - 4, bry)
    chip(c, flx - 12, (sly + bry) / 2 - 4, "COMES OFF", 9, "ALT", INK, "r")
    label(c, flx - 12, sly - 30, "J-SIDE\nNUMBERS", *a.A("numJ"), 9, anchor="r")
    chip(c, flx - 12, fly + 16, "FRONT EDGE\n(A SIDE)", 9, "ALT", INK, "r")
    c.setStrokeColor(INK)
    lw(c, 3)
    c.line(flx, fly - 3, frx, fry - 3)
    c.setStrokeColor(NEON)
    lw(c, 2)
    bx = x + w - 112
    c.rect(bx, y + 18, 100, 38, stroke=1, fill=0)
    text(c, bx + 96, y + 24, "mm", 14, "HEAD", INK, "r")
    chip(c, bx + 50, y + 64, "WRITE IT HERE", 10, "ALT", NEON, "c")
    # 2: score
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Ruler on the keep side of the line.", "Score x10. Flip. Score x10 on the same line."])
    s = Art(c, "s3_score", x + 32, y + 2, w - 98, h - 4, align="l")
    times(c, x + w - 34, y + h - 40, "x10", 26)
    curved_arrow(c, x + w - 34, y + h - 68, 13, 200, -60)
    times(c, x + w - 34, y + 12, "x10", 26)
    # 3: clamp and snap
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Snap line on the table edge, scrap wood on", "top, clamped. Push the rails down. Snap."])
    s = Art(c, "s3_snap", x + 2, y + 2, w - 4, h - 4)
    px, py = s.A("push")
    arrow(c, px, py + 40, px, py + 6, HAZ, 3.5, 12, halo=INK)
    chip(c, px, py + 46, "SNAP", 12, "HEAD", NEON, "c")
    label(c, x + 8, y + 40, "SCRAP WOOD", *s.A("wood"), 9)
    # 4: file to the line, not past
    x, y, w, h = panel(c, g.cell(0, 2), 4, ["File the edge flat and square.", "STOP at the line. Row J stays intact."])
    Art(c, "tool_file", x + 40, y + h - 24, 150, 22, align="l")
    ok = Art(c, "s3_edge_ok", x + 8, y + 16, 110, h - 54, frame=True)
    verdict(c, ok.x + ok.w - 2, ok.y + ok.h + 2, True)
    chip(c, ok.x + ok.w / 2, ok.y - 13, "ROW J WHOLE", 9, "ALT", INK, "c")
    bad = Art(c, "s3_edge_bad", x + w - 120, y + 16, 110, h - 54, frame=True)
    verdict(c, bad.x + bad.w - 2, bad.y + bad.h + 2, False)
    chip(c, bad.x + bad.w / 2, bad.y - 13, "FILED INTO THE PADS", 9, "ALT", NEON, "c")
    # 5: check, x4
    x, y, w, h = panel(c, g.cell(1, 2), 5, ["Measure the depth at BOTH ends.", "Same number? Next card. Do all 4."])
    s = Art(c, "s3_check", x + 30, y + 6, 160, h - 12, align="l")
    for nm in ("A", "B"):
        (ax, ay), (bx, by) = s.A(nm + "0"), s.A(nm + "1")
        dim(c, ax, ay, bx, by, nm, 13, INK)
    chip(c, s.x + s.w / 2, s.y + s.h / 2 - 8, "A = B", 18, "HEAD", INK, "c")
    times(c, x + w - 34, y + h / 2 - 10, "x4")


def step4(c, pg):
    page(c, "02", "LABEL. PHOTOGRAPH. REPORT.", "NAME EACH CARD. SHOW THE MACHINE YOUR WORK.", pg, SLOGANS[2])
    g = Grid(2, 2, heights=[1.25, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Sharpie the name on each card's FRONT", "edge (the A side). Shown as stacked",
                                             "in the box: B3 on top, B4 at the bottom."])
    s = Art(c, "s4_stack", x + 2, y + 2, w - 92, h - 34, align="l", valign="c")
    names = [("B4", "POWER"), ("B2", "PORTS B\n+ METERS"), ("B1", "PORTS A"), ("B3", "CORE")]
    for k, (n, role) in enumerate(names):
        px, py = s.A(f"right{k}")
        r = chip(c, x + w - 84, py - 4 + (6 if "\n" in role else 0), f"{n} {role}", 10, "ALT", INK)
        lx, ly = s.A(f"lab{k}")
        leader(c, r, lx, ly)
    chip(c, x + 38, y + h - 22, "WRITE ON THE FRONT EDGE", 10, "ALT", NEON)
    # 2: photo
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["Photograph ONE snapped card flat", "on the table, a ruler along its depth."])
    s = Art(c, "s4_photo", x + 2, y + 2, w - 4, h - 30, valign="b")
    phx, phy = s.A("phone")
    cx, cy = s.A("card")
    arrow(c, phx - 18, phy - 18, cx, cy + 12, NEON, 1.8)
    label(c, x + w - 110, y + h - 22, "STRAIGHT DOWN", phx + 10, phy, 10, "ALT", NEON, lcolor=NEON)
    label(c, x + w - 90, y + 46, "RULER ALONG\nTHE DEPTH", *s.A("ruler"), 9)
    # 3: the report
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "Send these to Claude. Claude updates the card model from them. Then on to the base (step 03)."])
    report(c, x, y, w, h, CARD_ROWS)


CARD_ROWS = [("CARD: FRONT EDGE TO SNAP LINE", "mm", "model 41.91"),
             ("ALL FOUR CARDS: A = B, ROW J WHOLE", "Y / N", ""),
             ("FOUR NAMES ON FOUR FRONT EDGES", "Y / N", "B1 PORTS A, B2 PORTS B + METERS, B3 CORE, B4 POWER"),
             ("PHOTO OF A SNAPPED CARD WITH A RULER", "SENT", "")]
BASE_ROWS = [("INSERT LENGTH  L", "mm", "expected 5.7"),
             ("INSERT DIAMETER  D (KNURL TIPS)", "mm", "expected 4.6"),
             ("BAR 1 + BAR 2 INSERTS SET, B4 SLOT CLEAR", "Y / N", "offcut slides the whole B4 slot"),
             ("2 x M3 INSERTS IN THE EVM CLIP BORES", "Y / N", "left keeper and right lid-end block, flush"),
             ("BACKPLANE: 31 x 38, TEST-FITS", "Y / N", "in, flat on the three pads, out again"),
             ("BACKPLANE: LINE 30 TO RIGHT EDGE", "mm", "expected 5.48, at most 6.13"),
             ("PHOTO OF THE BACKPLANE TEST-FITTED", "SENT", "")]


def report(c, x, y, w, h, rows):
    for i, (lab, unit, exp) in enumerate(rows):
        yy = y + h - 22 - i * (h - 16) / max(len(rows), 4)
        text(c, x + 44, yy, lab, 14, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.8)
        c.rect(x + 330, yy - 8, 110, 26, stroke=1, fill=0)
        text(c, x + 448, yy, unit, 12, "HEAD", INK)
        if exp:
            text(c, x + 44, yy - 13, exp, 9, "MONO", GREY)


def base_report(c, pg):
    page(c, "05", "REPORT THE BASE.", "THE BASE IS DONE. SHOW THE MACHINE YOUR NUMBERS.", pg, SLOGANS[5])
    g = Grid(1, 2, heights=[1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Send these to Claude. Claude updates the model, the bar's insert bores and the card slots from them."])
    report(c, x, y, w, h, BASE_ROWS)


def built_page(c, pg):
    import builtpage
    builtpage.built(c, pg, sys.modules[__name__], "00", SLOGANS[2])


# One session: the cards first (Clint builds them next), then the base.
SESSIONS = [
    ("session1", "Session 1: prep", "PROTOCOL 01 // SESSION 1 // PREP",
     [("00-cover", [cover]), ("00-what-you-are-building", [built_page]), ("01-snap-card-rails", [step3]),
      ("02-label-report", [step4]), ("03-measure-insert", [step1]), ("04-backplane", [bp1, bp3, bp4, bp5, bp6]),
      ("05-report-base", [base_report])]),
]


HOLE_ISSUES = []


def build(path, fns, start=1, report=False, title="Session 1: cards"):
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setTitle(title)
    c.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(c, start + i)
        if report:
            issues += len(LAB.check())
            hi = HC.check(start + i)
            for m in hi:
                print("  HOLE", m)
            HOLE_ISSUES.extend(hi)
        HC.reset()
        c.showPage()
    c.save()
    return issues


OUT.mkdir(parents=True, exist_ok=True)
bad = 0
for sid, title, proto, pages in SESSIONS:
    PROTO = proto
    allfns = []
    n = 1
    for name, fns in pages:
        build(OUT / f"{sid}-{name}.pdf", fns, n, title=title)
        allfns += fns
        n += len(fns)
    b = build(OUT / f"{sid}-all.pdf", allfns, 1, report=True, title=title)
    bad += b
    print(sid, "ok", n - 1, "pages,", b, "label issues")
print(len(HOLE_ISSUES), "hole-alignment issues", HC.STATS)
if HOLE_ISSUES:
    sys.exit("BUILD FAILED: hole callouts off their holes")
