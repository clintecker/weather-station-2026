"""Top (dimensioned) and iso views of the rim test-fit coupon, from the same solid cage.py exports.

    ../../../.venv-cad/bin/python coupon_views.py           writes ../renders/rim-coupon-top.png and rim-coupon-iso.png
    ../../../.venv-cad/bin/python coupon_views.py --edges   writes ../renders/rim-edge-short-top.png and rim-edge-long-top.png
"""
import sys
from pathlib import Path

EDGES = "--edges" in sys.argv
sys.argv = sys.argv[:1]
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import cadquery as cq  # noqa: E402
import cage  # noqa: E402
from cage import S  # noqa: E402

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
    # r7's lip and long edge, ghosted in r8's frame; the corner's diagonal through the screw
    g = dict(cage.COUPON_GHOST)
    old = cage.seal_region(cage.TONGUE_W / 2, 0, 1, **dict(g)).intersect(
        cq.Workplane("XY").rect(cx, cz, centered=False).extrude(1)).cut(cage.seal_region(-cage.TONGUE_W / 2, -1, 3, **dict(g)))
    for ln in outline(old, 0.5):
        ax.plot(*zip(*ln), color="#aaa", lw=1.0, ls="--")
    ax.plot([cage.COUPON_GHOST_EDGE] * 2, [4, cz], color="#aaa", lw=1.0, ls="--")
    _hx, _hz = cage.COUPON_HOLE
    _o = (_hx - _hz)                                       # the 45-degree line through the screw
    ax.plot([_o, _o + min(cx, cz)], [0, min(cx, cz)], color="#c03030", lw=0.8, ls="-.")
    ax.text(min(cx, cz) - 8, min(cx, cz) - 3, "diagonal through\nthe screw", color="#c03030", fontsize=8)
    cs, cl, w = cage.TONGUE_CS, cage.TONGUE_CL, cage.TONGUE_W
    rise, run, r, ri = cage.S_RISE, cage.COUPON_RUN, cage.CURVE_R, cage.CURVE_RI
    hx, hz = cage.COUPON_HOLE
    blue = "#1f4e9c"
    kw = dict(arrowprops=dict(arrowstyle="<->", color=blue, lw=0.9), color=blue, fontsize=8)
    t = dict(color=blue, fontsize=8)
    ax.annotate("", (0, 47), (cl, 47), **kw)
    ax.text(cl + 0.8, 46.6, f"{cl:g} (long side)", **t)
    ax.annotate("", (cx + 2, 0), (cx + 2, cs), **kw)
    ax.text(cx + 2.6, cs / 2 + 1.2, f"{cs:g}\n(short\nside)", **t)
    ax.annotate("", (cl - w / 2, 42), (cl + w / 2, 42), **kw)
    ax.text(cl + w / 2 + 0.8, 41.6, f"{w:g}", **t)
    # the middle runs' straights (between the outer and inner bends), axis-aligned
    st = rise - r - ri
    # the S's middle runs from the outside edges, and the lip-to-hole material
    ax.annotate("", (0, cs + rise + 1.5), (cl + run, cs + rise + 1.5), **kw)
    ax.text((cl + run) / 2, cs + rise + 2.2, f"{cl + run:g}", ha="center", **t)
    ax.annotate("", (cl + run + 1.5, 0), (cl + run + 1.5, cs + rise), **kw)
    ax.text(cl + run + 2.1, (cs + rise) / 2 - 3, f"{cs + rise:g}", **t)
    d = S.val("coupon_bore")
    face = cl + run - w / 2
    clr = min(face - (hx + d / 2), (cs + rise - w / 2) - (hz + d / 2))
    import math as _m
    _rc = _m.hypot(hx - cage.CORNER_R, hz - cage.CORNER_R) + cage.CORNER_R - d / 2
    ax.annotate("", (hx + d / 2, hz), (face, hz), arrowprops=dict(arrowstyle="<->", color="#c03030", lw=0.9))
    ax.text(hx + d / 2 - 0.2, hz - 1.8, f"{clr:.1f}", color="#c03030", fontsize=8)
    sx_ = run - r - ri
    ax.annotate("", (cl + r, cs + rise + 3.2), (cl + r + sx_, cs + rise + 3.2), **kw)
    ax.text(cl + r + sx_ / 2, cs + rise + 4.0, f"{sx_:g} straight", ha="center", **t)
    ax.annotate("", (cl + run + 3.2, cs + r), (cl + run + 3.2, cs + r + st), **kw)
    ax.text(cl + run + 4.0, cs + r + st / 2, f"{st:g} straight", va="center", **t)
    ax.text(cl + run + 4, 34, f"R {r:g} outer, R {ri:g} middle bends, on the lip's centre line [TBD-MEASURE]\nlip {w:g} wide, "
            f"{cage.TONGUE_H:g} tall; no land inside it", **t)
    d = S.val("coupon_bore")
    ax.annotate("", (0, hz), (hx, hz), **kw)
    ax.text(hx / 2, hz + 0.8, f"{hx:g}", ha="center", **t)
    ax.annotate("", (hx, 0), (hx, hz), **kw)
    ax.text(hx + 0.6, hz / 2 - 2.5, f"{hz:g}", va="center", **t)
    ax.text(hx + d / 2 + 0.5, hz + d / 2, f"\u00d8{d:g}", **t)
    ax.text(0.8, -4.4, f"outside corner R {cage.CORNER_R:g} [TBD-MEASURE]; grey dashed: r7's lip and long edge", **t)
    ax.set_aspect("equal")
    ax.set_xlim(-6, cx + 9)
    ax.set_ylim(-6, cz + 4)
    ax.set_xlabel("mm from the lid's outside edge (short side)")
    ax.set_ylabel("mm from the lid's outside edge (long side)")
    ax.set_title(f"rim test-fit coupon r8, top: {cx:g} x {cz:g} x {ch:g} mm (land {ch - cage.TONGUE_H:g}, lip "
                 f"{cage.TONGUE_H:g} above it); hole \u00d8{d:g} at {hx:g}/{hz:g}\nthe S's middle runs at "
                 f"{cl + run:g} from the long edge, {cs + rise:g} from the short, R{r:g} outer / R{ri:g} middle bends (r6 + r7 fits)\nthe hole: "
                 f"{clr:.1f} mm to the lip, {hz - d / 2:g} to the short edge, {_rc:.1f} to the R{cage.CORNER_R:g} corner\n"
                 "hole moved 1.5 toward the corner (Clint, r7 fit)", fontsize=9)
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
    ax.set_xlim(0, cage.COUPON[0])
    ax.set_ylim(0, cage.COUPON[1])
    ax.set_zlim(0, 12)
    ax.set_box_aspect((cage.COUPON[0], cage.COUPON[1], 12))
    ax.view_init(elev=35, azim=-120)
    ax.set_axis_off()
    ax.set_title("rim test-fit coupon, iso: r8, the lip (gold) 4.5 above the land, 2 mm wider on the long side than r6", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "rim-coupon-iso.png", dpi=160)


def edge_top(which):
    """Top of one whole-edge coupon, the edge drawn horizontally: hole spacing and overall length dimensioned."""
    sol = cage.edge_coupon_solid(which)
    ll, wl, _r = S.val("l5_lid_out")
    sx, sz = S.val("edge_hole_span")
    ch = cage.COUPON[2]
    land_h = ch - cage.TONGUE_H
    # lid frame: x across the 130, y along the 175; draw the edge along the plot's x
    if which == "short":
        f = lambda x, y: (x, y)                        # noqa: E731
        L, span, n = wl, sx, "short"
    else:
        f = lambda x, y: (y, x)                        # noqa: E731
        L, span, n = ll, sz, "long"
    fig, ax = plt.subplots(figsize=(13 if which == "long" else 11, 3.9))
    for z, c, lw in ((land_h / 2, "#555", 1.1), (land_h + cage.TONGUE_H / 2, "#b07a10", 1.5)):
        for ln in outline(sol, z):
            ax.plot(*zip(*[f(*p) for p in ln]), color=c, lw=lw)
    blue = "#1f4e9c"
    kw = dict(arrowprops=dict(arrowstyle="<->", color=blue, lw=0.9))
    h0 = (L - span) / 2
    ax.annotate("", (h0, 30), (h0 + span, 30), **kw)
    tbd = " (108-110 measured)  [TBD-MEASURE]" if which == "short" else " (measured, +-1)  [TBD-MEASURE]"
    ax.text(L / 2, 31, f"holes {span:g} apart{tbd}", color=blue, fontsize=9, ha="center")
    ax.annotate("", (0, -5), (L, -5), **kw)
    ax.text(L / 2, -9.5, f"{L:g} overall (l5_lid_out)", color=blue, fontsize=9, ha="center")
    for x in (h0, h0 + span):
        ax.plot([x, x], [10, 29], color=blue, lw=0.5, ls=":")
    hx = h0
    hz = (ll - sz) / 2 if which == "short" else (wl - sx) / 2
    ax.text(hx + 5, hz - 1, f"\u00d8{S.val('coupon_bore'):g} at {hx:g} / {hz:g}", color=blue, fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-6, L + 6)
    ax.set_ylim(-13, 37)
    ax.set_xlabel(f"mm along the {n} edge")
    ax.set_ylabel("mm in from the edge")
    v = sol.val().Volume() / 1000
    lc, _ec = cage.edge_hole_clearance()
    other = "long" if which == "short" else "short"
    ax.set_title(f"rim edge coupon, {n} edge, top: {L:g} x {cage.EDGE_RETURN:g} x {ch:g} mm, {v:.1f} cm3 "
                 f"(land {land_h:g}, lip {cage.TONGUE_W:g} x {cage.TONGUE_H:g} above it, R{cage.CORNER_R:g} corners)\n"
                 f"both corners coupon r8's lip and S, mirrored; {cage.EDGE_RETURN:g} mm returns along each {other} side\n"
                 f"holes where the lid's spacings put them: {span:g} apart{tbd}; {lc:.1f} mm from the hole to the lip", fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    out = OUT / f"rim-edge-{which}-top.png"
    fig.savefig(out, dpi=160)
    return out


if __name__ == "__main__" and EDGES:
    for w in ("short", "long"):
        print("wrote", edge_top(w))
elif __name__ == "__main__":
    s = cage.coupon_solid()
    top(s)
    iso(s)
    print("wrote renders/rim-coupon-top.png, renders/rim-coupon-iso.png")
