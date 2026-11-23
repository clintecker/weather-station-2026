"""Write firmware/stage0-node/App/scr_art.c: the two fixed drawings of the bench screens, as bitmaps.

    python3 firmware/stage0-node/tools/make_scr_art.py          # rewrite the C file
    python3 firmware/stage0-node/tools/make_scr_art.py --check  # exit 1 if the C file is out of date

The face and the rose are drawn here with the trigonometry of the approved mockups (.superpowers/sdd/2026-11-04-node-oled-
and-e2e/oledmock: hack.py face(), gen.py vane()), pixel for pixel, so the node needs no floating point:
  - the HACK THE PLANET face: the double ring, the eye patch and its strap, the smile. Not the open eye,
    the wink or the glint: App/scr_interludes.c draws those, they change by frame.
  - the vane compass rose: a dot every 4 degrees and a tick every 45. Not the N or the needle.
  - the pocket frog (original art, 2026-11-05): its body, the rims of its eyes, its feet and its lily pad.
    Not the pupils, the blink, the mouth or the tongue: App/scr_silly.c draws those, they change with its mood
    and by frame.
tests/test_scr_view.py runs --check."""
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]/'App/scr_art.c'
FACE_CX, FACE_CY = 31, 32      # App/scr_interludes.c draws the eye and the wink around this centre
ROSE_CX, ROSE_CY, ROSE_R = 32, 33, 26
FROG_CX, FROG_CY = 32, 44      # App/scr_silly.c draws the pupils at (FROG_CX -+ 10, FROG_CY - 12)


def cosd(a):
    """cos of a in degrees, to 12 places: libm's last bit differs between macOS and Linux, and a value like
    30 x cos(60) must land on 15, not either side of it, for the file to come out the same on both."""
    return round(math.cos(math.radians(a)), 12)


def sind(a):
    return round(math.sin(math.radians(a)), 12)


def snap(v):
    """A coordinate to 9 places before it is truncated or rounded (see cosd)."""
    return round(v, 9)


class Canvas:
    """The mockups' canvas (oledmock/canvas.py): float coordinates truncate, lines round."""
    def __init__(self):
        self.p = set()

    def px(self, x, y):
        if 0 <= x < 128 and 0 <= y < 64:
            self.p.add((int(snap(x)), int(snap(y))))

    def line(self, x0, y0, x1, y1):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) or 1
        for k in range(n + 1):
            self.px(round(snap(x0 + (x1 - x0) * k / n)), round(snap(y0 + (y1 - y0) * k / n)))


def face():
    c, cx, cy, r = Canvas(), FACE_CX, FACE_CY, 30
    for a in range(0, 360, 2):                         # the double ring
        for rr in (r, r - 1):
            c.px(cx + rr * cosd(a), cy + rr * sind(a))
    for x in range(cx + 3, cx + 19):                   # the patch over the right eye
        for y in range(cy - 14, cy - 1):
            if ((x - (cx + 11)) / 8.5) ** 2 + ((y - (cy - 8)) / 6.0) ** 2 <= 1:
                c.px(x, y)
    c.line(cx - 22, cy - 18, cx + 3, cy - 12); c.line(cx - 22, cy - 17, cx + 3, cy - 11)   # its strap
    c.line(cx + 17, cy - 13, cx + 26, cy - 15); c.line(cx + 17, cy - 12, cx + 26, cy - 14)
    for a in range(25, 156, 2):                        # the smile
        for rr in (17, 18):
            c.px(cx + rr * cosd(a), cy + 1 + rr * sind(a) * 0.75)
    return c.p


def rose():
    c, cx, cy, r = Canvas(), ROSE_CX, ROSE_CY, ROSE_R
    for a in range(0, 360, 4):
        c.px(cx + r * sind(a), cy - r * cosd(a))
    for a in range(0, 360, 45):
        c.line(cx + (r - 4) * sind(a), cy - (r - 4) * cosd(a),
               cx + r * sind(a), cy - r * cosd(a))
    return c.p


def frog():
    c, cx, cy = Canvas(), FROG_CX, FROG_CY
    eyes = (cx - 10, cx + 10)
    inside = lambda x, y: any((x - ex) ** 2 + (y - (cy - 12)) ** 2 < 6.5 ** 2 for ex in eyes)
    for a in range(0, 360, 2):                         # the body, a double outline, behind the eyes
        for rx, ry in ((20, 11), (19, 10)):
            x, y = round(snap(cx + rx * cosd(a))), round(snap(cy + ry * sind(a)))
            if not inside(x, y):
                c.px(x, y)
    for ex in eyes:                                    # the eyes' rims, sitting on the head
        for a in range(0, 360, 3):
            c.px(round(snap(ex + 6 * cosd(a))), round(snap(cy - 12 + 6 * sind(a))))
    for sx in (-1, 1):                                 # the front feet, three toes each
        c.line(cx + sx * 8, cy + 8, cx + sx * 9, cy + 12)
        for t in (-2, 0, 2):
            c.line(cx + sx * 9, cy + 12, cx + sx * 9 + t, cy + 13)
    for a in range(0, 360, 2):                         # the lily pad, a notch at the front
        if not 80 <= a <= 100:
            c.px(round(snap(cx + 30 * cosd(a))), round(snap(cy + 15 + 2.5 * sind(a))))
    c.line(cx, cy + 15, cx - 4, cy + 17); c.line(cx, cy + 15, cx + 4, cy + 17)
    return c.p


def bitmap(name, pixels):
    """A C bitmap 64 wide (oled_bits): the rows from the topmost lit one to the lowest, bit 63 the leftmost lit column."""
    x0, y0 = min(x for x, _ in pixels), min(y for _, y in pixels)
    w, h = max(x for x, _ in pixels) - x0 + 1, max(y for _, y in pixels) - y0 + 1
    assert w <= 64, (name, w)
    lines = [f'static const uint64_t {name}_rows[{h}] = {{']
    for y in range(y0, y0 + h):
        bits = sum(1 << (63 - (x - x0)) for x, yy in pixels if yy == y)
        art = ''.join('#' if (x0 + i, y) in pixels else '.' for i in range(w))
        lines.append(f'  0x{bits:016X}U,   /* {art} */')
    lines += ['};', f'const scr_art {name} = {{ {x0}, {y0}, {{ 64, {h}, 64, {name}_rows }} }};', '']
    return lines


def generate():
    lines = ['/* GENERATED by firmware/stage0-node/tools/make_scr_art.py: do not edit. Edit the script and re-run it. */',
             '#include "scr_art.h"', '']
    lines += bitmap('scr_art_face', face())
    lines += bitmap('scr_art_rose', rose())
    lines += bitmap('scr_art_frog', frog())
    return '\n'.join(lines)


def main():
    text = generate()
    if '--check' in sys.argv[1:]:
        if not OUT.exists() or OUT.read_text() != text:
            print(f'{OUT} is out of date: run {Path(__file__).name}', file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
