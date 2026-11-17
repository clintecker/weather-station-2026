"""WHAT YOU ARE BUILDING: one page, shared by both sessions. `h` is the page builder's namespace (page, Grid, panel,
Art, label, chip, INK, NEON); the renders are asm_iso and asm_lid from assembly.py (repo 91a5345)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "schematic"))
import model  # noqa: E402  (the slot keys and colour dots: model.KEY, model.KEY_COLOUR)

ROLE = {"B4": "B4 POWER", "B2": "B2 PORTS B + METERS", "B1": "B1 PORTS A", "B3": "B3 CORE"}
ORDER_TOP_DOWN = ["B3", "B1", "B2", "B4"]


def built(c, pg, h, step_no, slogan):
    h.page(c, step_no, "WHAT YOU ARE BUILDING",
           "THE PRINTED BASE (ENCLOSURE 4). THE BACKPLANE. FOUR CARDS IN THEIR KEYED 1x30 SOCKETS.", pg, slogan)
    g = h.Grid(1, 2, heights=[1, 1])
    # 1: iso from the lid side
    x, y, w, hh = h.panel(c, g.cell(0, 0), 1, [
        "From the lid side, walls cut down. Each card slides toward the floor in its two slots until its 1x30 header",
        "(29 pins, one pulled: the slot key) seats in its socket: backplane holes 13, 19, 27, 35; pin n on line n.",
        "Keys, dots: " + ", ".join(f"{b} {model.KEY[b]} {model.KEY_COLOUR[b]}" for b in ORDER_TOP_DOWN[::-1])
        + ". A wrong card stops at the key plug."])
    a = h.Art(c, "asm_iso", x + 40, y + 4, w * 0.52, hh - 8, align="l")
    rx = a.x + a.w + 26
    ys = sorted((a.A(f"{b}_right")[1], b) for b in ORDER_TOP_DOWN)[::-1]
    top = a.y + a.h - 14
    for i, (_, b) in enumerate(ys):
        px, py = a.A(f"{b}_right")
        h.label(c, rx, top - i * 30, ROLE[b], px, py, 11, "HEAD", h.INK)
    yb = top - 4 * 30 - 4
    for (s_, an) in (("RIGHT CORNER POST (SLOTS)", "post_r"), ("BACKPLANE: PAD3U, 31 LINES\n(0-30) x 38 HOLES", "bp_low")):
        h.label(c, rx, yb, s_, *a.A(an), 9, "ALT", h.INK)
        yb -= 34
    bx_, by_ = a.A("bar")
    h.label(c, x + 8, by_ - 60, "RETENTION BAR", bx_, by_, 9, "ALT", h.INK)
    # 2: straight down from the lid
    x, y, w, hh = h.panel(c, g.cell(0, 1), 2, [
        "Straight down from the lid, glands at the bottom; the pack tray and the charger ledges below the cards.",
        "Not drawn: the EVM and the pack. Card parts are stack.py's layout boxes."])
    a = h.Art(c, "asm_lid", x + 30, y + 4, w * 0.5, hh - 8, align="l")
    rx = a.x + a.w + 26
    ys = sorted((a.A(f"{b}_front")[1], b) for b in ORDER_TOP_DOWN)[::-1]
    for i, (_, b) in enumerate(ys):
        px, py = a.A(f"{b}_front")
        h.label(c, rx, py - 4 + (6 - 4 * i), ROLE[b], px, py, 11, "HEAD", h.INK)
    h.label(c, rx, a.y + 40, "BACKPLANE: BIG HOLES RIGHT,\nNO SCREWS: THE CARDS HOLD IT", *a.A("bp_low"), 9, "ALT",
            h.INK)
