"""Top (dimensioned, with one corner's segment points and radii) and iso views of the rim test ring, from the same
solid cage.py --ring exports, in the spec's frame (lid-rim-spec.md: origin at the lid centre, X along the long side).

    ../../../.venv-cad/bin/python ring_views.py     writes ../renders/rim-ring-top.png and rim-ring-iso.png
"""
import sys
from pathlib import Path

sys.argv = sys.argv[:1]
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import cage  # noqa: E402
import lid_rim_spec as RS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "renders"
BLUE, GOLD, GREY, RED = "#1f4e9c", "#b07a10", "#555", "#c03030"


def outline(solid, z):
    lines = []
    for e in solid.section(z).edges().vals():
        lines.append([(p.x, p.y) for p in (e.positionAt(t / 40.0) for t in range(41))])
    return lines


def centre_line():
    pts = []
    for e in cage.ring_edges():
        pts += [(p.x, p.y) for p in (e.positionAt(t / 20.0) for t in range(21))]
    return pts


def draw(ax, solid, sp):
    land_h, top = sp["land_z"][1], sp["lip_z"][1]
    for ln in outline(solid, land_h / 2):
        ax.plot(*zip(*ln), color=GREY, lw=1.0)
    for ln in outline(solid, (land_h + top) / 2):
        ax.plot(*zip(*ln), color=GOLD, lw=1.3)
    ax.plot(*zip(*centre_line()), color=GOLD, lw=0.6, ls="--")


def dim(ax, a, b, text, off, vertical=False, **kw):
    ax.annotate("", a, b, arrowprops=dict(arrowstyle="<->", color=BLUE, lw=0.8))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    ax.text(mx + (off if vertical else 0), my + (0 if vertical else off), text, color=BLUE, fontsize=8,
            ha="center", va="center", rotation=90 if vertical else 0, **kw)


def top(solid, lines):
    sp = RS.load()
    d = RS.derived(sp)
    L, Wd = sp["outline"]
    hx, hy = sp["holes"]
    sx, sy = d["spans"]
    fig, (ax, az) = plt.subplots(1, 2, figsize=(16, 7.6), gridspec_kw=dict(width_ratios=[1.55, 1]))
    draw(ax, solid, sp)
    dim(ax, (-L / 2, -Wd / 2 - 6), (L / 2, -Wd / 2 - 6), f"{L:g} outline (R{sp['corner_r']:g} corners)", -2.5)
    dim(ax, (-L / 2 - 6, -Wd / 2), (-L / 2 - 6, Wd / 2), f"{Wd:g} outline", -3, vertical=True)
    dim(ax, (-sx / 2, -Wd / 2 + 16), (sx / 2, -Wd / 2 + 16), f"lip {sx:g} centre to centre", 2.5)
    dim(ax, (L / 2 - 30, -sy / 2), (L / 2 - 30, sy / 2), f"lip {sy:g} centre to centre", -3, vertical=True)
    dim(ax, (-hx, hy + 13), (hx, hy + 13), f"holes {2 * hx:g} apart (155 tape, 157 maker; +-1)", 2.5)
    dim(ax, (hx + 13, -hy), (hx + 13, hy), f"holes {2 * hy:g} apart (+-1)", 3, vertical=True)
    for x in (hx, -hx):
        ax.plot([x, x], [hy, hy + 13], color=BLUE, lw=0.4, ls=":")
    ax.plot([hx, hx + 13], [-hy, -hy], color=BLUE, lw=0.4, ls=":")
    ax.plot([hx, hx + 13], [hy, hy], color=BLUE, lw=0.4, ls=":")
    ax.plot([0, 0], [-Wd / 2 - 3, Wd / 2 + 3], color="#999", lw=0.5, ls="-.")
    ax.plot([-L / 2 - 3, L / 2 + 3], [0, 0], color="#999", lw=0.5, ls="-.")
    ax.add_patch(plt.Rectangle((60, 38), L / 2 - 60 + 2, Wd / 2 - 38 + 2, fill=False, ec=RED, lw=0.8, ls="--"))
    ax.text(60, 36, "zoomed, right", color=RED, fontsize=7, va="top")
    ax.set_aspect("equal")
    ax.set_xlim(-L / 2 - 14, L / 2 + 20)
    ax.set_ylim(-Wd / 2 - 13, Wd / 2 + 6)
    ax.set_xlabel("X mm (long side), origin at the lid centre")
    ax.set_ylabel("Y mm (short side)")
    ax.grid(alpha=0.2)
    # the +X +Y corner: the spec's segment points and radii
    draw(az, solid, sp)
    q = sp["quadrant"]
    off = {1: (1.0, -1.2), 2: (0.5, 1.4), 3: (-12.0, -2.6), 4: (-13.5, -0.3), 5: (-11.5, -1.8), 6: (-4.0, 1.3)}
    for i, sg in enumerate(q):
        a = sg[1]
        az.plot(*a, "o", color=RED, ms=3)
        if i in off:
            az.text(a[0] + off[i][0], a[1] + off[i][1], f"{i + 1}: ({a[0]:g}, {a[1]:g})", color=RED, fontsize=7)
        if sg[0] == "arc":
            c, r = sg[3], sg[4]
            az.plot(*c, "+", color=BLUE, ms=6)
            if r == sp["quadrant"][3][4]:
                az.annotate(f"R{r:g} (centre +)", c, (58.5, 49.5), color=BLUE, fontsize=8,
                            arrowprops=dict(arrowstyle="->", color=BLUE, lw=0.6))
            else:
                az.text(c[0] - 1.0, c[1] - 1.6, f"R{r:g}", color=BLUE, fontsize=8)
    az.text(55, 37.2, "segment 1 starts at (84.75, 0); 7 runs on to (0, 61.5)", color=RED, fontsize=7)
    az.add_patch(plt.Circle((hx, hy), sp["hole_d"] / 2, fill=False, ec=GREY, lw=0.6))
    az.text(hx + 3.8, hy + 2.2, f"Ø{sp['hole_d']:g} at ({hx:g}, {hy:g})", color=BLUE, fontsize=7)
    az.set_xlim(54, 98)
    az.set_ylim(36, 67)
    az.set_aspect("equal")
    az.set_xlabel("X mm")
    az.grid(alpha=0.2)
    az.set_title("the +X +Y corner (the others mirror it):\nthe spec's segment start points (red), arc centres (blue +)", fontsize=8)
    fig.suptitle(f"rim test ring, top (lid-rim-spec.md, Clint's 300 dpi lid scans): land Z 0-{sp['land_z'][1]:g}, lip "
                 f"{sp['lip_w']:g} x {sp['lip_h']:g} on it (gold; dashed its centre line), nothing inside the lip\n"
                 + "; ".join(lines[:2]) + "\n" + lines[2], fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "rim-ring-top.png", dpi=150, bbox_inches="tight")


def iso(solid):
    sp = RS.load()
    verts, tris = solid.val().tessellate(0.1)
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(projection="3d")
    polys = [[(verts[i].x, verts[i].y, verts[i].z) for i in t] for t in tris]
    shade = []
    for p in polys:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = p
        n = ((y1 - y0) * (z2 - z0) - (z1 - z0) * (y2 - y0), (z1 - z0) * (x2 - x0) - (x1 - x0) * (z2 - z0),
             (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0))
        m = sum(v * v for v in n) ** 0.5 or 1.0
        k = 0.35 + 0.65 * max(0.0, (0.3 * n[0] + 0.5 * n[1] + 0.8 * n[2]) / m)
        up = sum(c[2] for c in p) / 3 > sp["land_z"][1] + 0.01
        shade.append(tuple(c * k for c in ((0.85, 0.64, 0.25) if up else (0.78, 0.78, 0.74))))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=shade, edgecolor="none"))
    L, Wd = sp["outline"]
    ax.set_xlim(-L / 2, L / 2)
    ax.set_ylim(-Wd / 2, Wd / 2)
    ax.set_zlim(0, 20)
    ax.set_box_aspect((L, Wd, 20))
    ax.view_init(elev=38, azim=-125)
    ax.set_axis_off()
    ax.set_title(f"rim test ring, iso: {L:g} x {Wd:g} x {sp['lip_z'][1]:g}, the lip (gold) {sp['lip_h']:g} above the land",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "rim-ring-iso.png", dpi=150)


if __name__ == "__main__":
    s = cage.ring_solid()
    lines, bad = cage.ring_checks(s)
    top(s, lines)
    iso(s)
    print("wrote renders/rim-ring-top.png, renders/rim-ring-iso.png;", "checks:", "; ".join(bad) or "pass")
