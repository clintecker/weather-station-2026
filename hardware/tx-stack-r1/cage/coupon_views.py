"""Top (dimensioned) and iso views of the rim test-fit coupon, from the same solid cage.py exports.

    ../../../.venv-cad/bin/python coupon_views.py     writes ../renders/rim-coupon-top.png and rim-coupon-iso.png
"""
import sys
from pathlib import Path

sys.argv = sys.argv[:1]
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import cage  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "renders"


def outline(solid, z):
    """Edges of the section at height z, each as a list of (x, y) points."""
    sec = solid.section(z)
    lines = []
    for e in sec.edges().vals():
        pts = [e.positionAt(t / 40.0) for t in range(41)]
        lines.append([(p.x, p.y) for p in pts])
    return lines


def top(solid):
    cx, cz, ch = cage.COUPON
    land_h = ch - cage.TONGUE_H
    fig, ax = plt.subplots(figsize=(8, 8.6))
    for ln in outline(solid, land_h / 2):
        ax.plot(*zip(*ln), color="#555", lw=1.2)
    for ln in outline(solid, land_h + cage.TONGUE_H / 2):
        ax.plot(*zip(*ln), color="#b07a10", lw=1.6)
    c, w = cage.TONGUE_C, cage.TONGUE_W
    sx, sz = cage.SCREWS[0]
    hx, hz = sx + cage.T, sz + cage.T
    kw = dict(arrowprops=dict(arrowstyle="<->", color="#1f4e9c", lw=0.9), color="#1f4e9c", fontsize=8)
    ax.annotate("", (0, 36), (c, 36), **kw)
    ax.text(c / 2, 37, f"{c:g}", ha="center", color="#1f4e9c", fontsize=8)
    ax.annotate("", (c - w / 2, 30), (c + w / 2, 30), **kw)
    ax.text(c + w / 2 + 0.8, 29.6, f"lip {w:g} wide, {cage.TONGUE_H:g} tall", color="#1f4e9c", fontsize=8)
    ax.annotate("", (0, hz), (hx, hz), **kw)
    ax.text(hx / 2, hz + 0.8, f"{hx:g}", ha="center", color="#1f4e9c", fontsize=8)
    ax.annotate("", (hx, 0), (hx, hz), **kw)
    ax.text(hx + 0.6, hz / 2, f"{hz:g}", va="center", color="#1f4e9c", fontsize=8)
    ax.annotate("", (40, 0), (40, cage.LAND), **kw)
    ax.text(40.6, cage.LAND / 2, f"land {cage.LAND:g}", va="center", color="#1f4e9c", fontsize=8)
    ax.text(26, 17, f"S-curve bends R {cage.CURVE_R:g} on the lip's\ncentre line [TBD-MEASURE]", color="#1f4e9c",
            fontsize=8)
    ax.text(0.8, -2.6, f"outside corner R {cage.CORNER_R:g} [TBD-MEASURE]", color="#1f4e9c", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-4, cx + 4)
    ax.set_ylim(-5, cz + 4)
    ax.set_xlabel("mm from the lid's outside edge (short side)")
    ax.set_ylabel("mm from the lid's outside edge (long side)")
    ax.set_title(f"rim test-fit coupon, top: {cx:g} x {cz:g} x {ch:g} mm, lip (gold) on the lid channel's centre "
                 f"line;\nscrew bore {cage.INSERT_D:g} at {hx:g}/{hz:g} from the edges; the base's outside is "
                 "the lid's (no outward offset)", fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "rim-coupon-top.png", dpi=160)


def iso(solid):
    verts, tris = solid.val().tessellate(0.05)
    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(projection="3d")
    polys = [[(verts[i].x, verts[i].y, verts[i].z) for i in t] for t in tris]
    shade = []
    for p in polys:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = p
        n = ((y1 - y0) * (z2 - z0) - (z1 - z0) * (y2 - y0), (z1 - z0) * (x2 - x0) - (x1 - x0) * (z2 - z0),
             (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0))
        m = sum(v * v for v in n) ** 0.5 or 1.0
        k = 0.35 + 0.65 * max(0.0, (0.3 * n[0] + 0.5 * n[1] + 0.8 * n[2]) / m)
        top = sum(q[2] for q in p) / 3 > cage.COUPON[2] - cage.TONGUE_H + 0.01
        base = (0.85, 0.64, 0.25) if top else (0.78, 0.78, 0.74)
        shade.append(tuple(c * k for c in base))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=shade, edgecolor="none"))
    ax.set_xlim(0, 45)
    ax.set_ylim(0, 45)
    ax.set_zlim(0, 12)
    ax.set_box_aspect((45, 45, 12))
    ax.view_init(elev=35, azim=-120)
    ax.set_axis_off()
    ax.set_title("rim test-fit coupon, iso: the 3 mm lip (gold) on the 9 mm land, round the corner boss", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "rim-coupon-iso.png", dpi=160)


if __name__ == "__main__":
    s = cage.coupon_solid()
    top(s)
    iso(s)
    print("wrote renders/rim-coupon-top.png, renders/rim-coupon-iso.png")
