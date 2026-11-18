"""Flat-pack line art from triangle meshes: the mesh counterpart of the TX sheets' r3d (session1/v2/r3d.py).

r3d draws CadQuery solids with OpenCascade's exact hidden-line removal and ray-cast fills. The shield's parts are
triangle meshes (shield/assemble.py, shield/remix.py: some 20 000 triangles each); OpenCascade's HLR does not take
them (a mesh made into faces crashes it). This renders the same picture from the meshes themselves, in r3d's style
and output format, so the page builder treats both alike:
  1. A depth buffer (`ss` pixels per output point) gives, per pixel, the nearest triangle: its part and its tone
     (three flat steps by the face normal, r3d's light from the upper left and its thresholds).
  2. Fills: each (part, tone) area is traced into polygons (contourpy) and written as one even-odd SVG path.
  3. Lines: every mesh edge that is a crease (faces meeting at more than `crease` degrees), an open edge or a
     silhouette (one face toward the viewer, the other away) is sampled along its length and kept where nothing
     lies in front of it; the kept runs are chained into polylines. Each part's visible area gets r3d's heavy outline.
  4. Anchors are checked visible on the part they name, as in r3d, and written with the same JSON (w, h, scale,
     anchors, holes).
CadQuery solids in a mesh scene (the pod boxes, screws, leads) are tessellated and drawn the same way. Every scene is
real geometry: the shield's own meshes, the remixed parts and the CadQuery models; nothing is drawn by hand.
"""
import json
import math
from pathlib import Path

import numpy as np
import contourpy
import shapely
from shapely.geometry import LineString, Polygon

import cadquery as cq
import r3d                                   # TX sheets (read-only): Scene, View, _tone, INK

INK = r3d.INK


class Scene(r3d.Scene):
    """r3d.Scene with mesh parts: add() takes (V, F) arrays, a manifold3d Manifold or a CadQuery shape."""

    def add(self, name, shape, colour, weight=1.0, tol=0.04, ang=0.25):
        if hasattr(shape, "to_mesh"):                                    # manifold3d.Manifold
            m = shape.to_mesh()
            v = np.asarray(m.vert_properties, float)[:, :3]
            f = np.asarray(m.tri_verts, np.int64)
        elif isinstance(shape, tuple) and len(shape) == 2:
            v, f = np.asarray(shape[0], float), np.asarray(shape[1], np.int64)
        else:
            if isinstance(shape, cq.Workplane):
                shape = cq.Compound.makeCompound(shape.vals())
            shape = cq.Shape.cast(shape.wrapped if hasattr(shape, "wrapped") else shape)
            vs, ts = shape.tessellate(tol, ang)
            v = np.array([(p.x, p.y, p.z) for p in vs], float)
            f = np.array(ts, np.int64).reshape(-1, 3)
        if self.xf is not None:
            v = v @ self.xf[0].T + self.xf[1]
        self.parts.append((name, _weld(v, f), colour, weight))
        return self

    def text(self, *a, **k):
        raise NotImplementedError("mrender draws no text decals")


def _weld(v, f, q=1e-4):
    key = np.round(v / q).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    f = inv.reshape(-1)[f]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 2] != f[:, 0])]
    return v[first], f


def _raster(X, Y, D, Wp, Hp):
    """Depth buffer: X, Y pixel coordinates (m, 3), D depth (bigger = nearer). Returns (zbuf, idbuf) (Hp, Wp)."""
    area = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])
    ok = np.abs(area) > 1e-9
    x0 = np.floor(X.min(1) - 0.5).astype(np.int64)
    y0 = np.floor(Y.min(1) - 0.5).astype(np.int64)
    x1 = np.ceil(X.max(1) - 0.5).astype(np.int64)
    y1 = np.ceil(Y.max(1) - 0.5).astype(np.int64)
    ok &= (x1 >= 0) & (y1 >= 0) & (x0 < Wp) & (y0 < Hp)
    span = np.maximum(x1 - x0, y1 - y0) + 1
    pix_all, dep_all, id_all = [], [], []

    def frag(ids, k):
        if not len(ids):
            return
        oy, ox = np.mgrid[0:k, 0:k]
        ox, oy = ox.ravel(), oy.ravel()
        step = max(1, 3_000_000 // (k * k))
        for s in range(0, len(ids), step):
            t = ids[s:s + step]
            px = x0[t][:, None] + ox[None]
            py = y0[t][:, None] + oy[None]
            cx, cy = px + 0.5, py + 0.5
            ax, ay = X[t, 0][:, None], Y[t, 0][:, None]
            bx, by = X[t, 1][:, None], Y[t, 1][:, None]
            qx, qy = X[t, 2][:, None], Y[t, 2][:, None]
            w0 = (bx - cx) * (qy - cy) - (qx - cx) * (by - cy)
            w1 = (qx - cx) * (ay - cy) - (ax - cx) * (qy - cy)
            w2 = (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)
            a = area[t][:, None]
            sg = np.sign(a)
            e = -1e-7 * np.abs(a)
            ins = (w0 * sg >= e) & (w1 * sg >= e) & (w2 * sg >= e)
            ins &= (px >= 0) & (py >= 0) & (px < Wp) & (py < Hp) & (px <= x1[t][:, None]) & (py <= y1[t][:, None])
            d = (w0 * D[t, 0][:, None] + w1 * D[t, 1][:, None] + w2 * D[t, 2][:, None]) / a
            pix_all.append((py * Wp + px)[ins].astype(np.int64))
            dep_all.append(d[ins].astype(np.float64))
            id_all.append(np.broadcast_to(t[:, None], ins.shape)[ins].astype(np.int64))

    ids = np.nonzero(ok)[0]
    lo = 0
    for k in (2, 4, 8, 16, 32, 64, 128):
        frag(ids[(span[ids] > lo) & (span[ids] <= k)], k)
        lo = k
    for t in ids[span[ids] > lo]:                                    # the few big triangles, one at a time
        k = int(span[t])
        frag(np.array([t]), k)
    zbuf = np.full(Hp * Wp, -np.inf)
    idbuf = np.full(Hp * Wp, -1, np.int64)
    if pix_all:
        pix, dep, tid = np.concatenate(pix_all), np.concatenate(dep_all), np.concatenate(id_all)
        o = np.lexsort((dep, pix))
        pix, dep, tid = pix[o], dep[o], tid[o]
        last = np.r_[pix[1:] != pix[:-1], True]
        zbuf[pix[last]] = dep[last]
        idbuf[pix[last]] = tid[last]
    return zbuf.reshape(Hp, Wp), idbuf.reshape(Hp, Wp)


def _rings_d(polys, ss, simp):
    out = []
    for pts, offs in polys:
        for a, b in zip(offs[:-1], offs[1:]):
            ring = pts[a:b]
            if len(ring) < 4:
                continue
            ls = shapely.simplify(LineString(ring), simp)
            c = np.asarray(ls.coords) / ss
            if len(c) < 3:
                continue
            out.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in c) + " Z")
    return out


def _chain(segs, nd=2):
    """Join 2D segments [(a, b)] that share ends into polylines."""
    key = lambda p: (round(p[0], nd), round(p[1], nd))
    ends = {}
    for i, (a, b) in enumerate(segs):
        ends.setdefault(key(a), []).append(i)
        ends.setdefault(key(b), []).append(i)
    used = np.zeros(len(segs), bool)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        line = [segs[i][0], segs[i][1]]
        for direction in (1, 0):
            while True:
                tip = line[-1] if direction else line[0]
                nxt = [j for j in ends.get(key(tip), []) if not used[j]]
                if len(ends.get(key(tip), [])) != 2 or not nxt:
                    break
                j = nxt[0]
                used[j] = True
                a, b = segs[j]
                q = b if key(a) == key(tip) else a
                if direction:
                    line.append(q)
                else:
                    line.insert(0, q)
        out.append(line)
    return out


def render(scene, out, direction, up=(0, 0, 1), fit=None, scale=None, margin=6, light=(-0.5, 0.35, 0.8), line=0.55,
           outline=1.1, tones=(1.0, 0.86, 0.72), crease=32.0, ss=3, verbose=True, bounds_parts=None, small_pt=7.0):
    """Render `scene` (mrender.Scene) to out.svg + out.json, r3d's format. fit=(w_pt, h_pt) or scale (pt per mm).
    bounds_parts: frame the picture on these parts only (others are clipped at the frame)."""
    for what, R in scene.frames:
        d = float(np.linalg.det(R))
        assert d > 0, f"{Path(str(out)).name}: {what} is placed by a reflection (det {d:+.3f}): the picture would be mirrored"
    view = r3d.View(direction, up)
    assert np.linalg.det(np.c_[view.x, view.y, view.n]) > 0
    B = np.c_[view.x, view.y, view.n]
    names = [p[0] for p in scene.parts]
    Vs, Fs, part_of, base = [], [], [], 0
    for k, (_n, (v, f), _c, _w) in enumerate(scene.parts):
        Vs.append(v @ B)
        Fs.append(f + base)
        part_of.append(np.full(len(f), k))
        base += len(v)
    P3 = np.vstack([p[1][0] for p in scene.parts])
    UVD = np.vstack(Vs)
    F = np.vstack(Fs)
    part_of = np.concatenate(part_of)
    sel = np.vstack([Vs[k] for k, n in enumerate(names) if (bounds_parts is None or n in bounds_parts)])
    u0, v0 = sel[:, 0].min(), sel[:, 1].min()
    u1, v1 = sel[:, 0].max(), sel[:, 1].max()
    if scale is None:
        fw, fh = fit
        scale = min((fw - 2 * margin) / (u1 - u0), (fh - 2 * margin) / (v1 - v0))
    Wpt = (u1 - u0) * scale + 2 * margin
    Hpt = (v1 - v0) * scale + 2 * margin
    Wp, Hp = int(math.ceil(Wpt * ss)), int(math.ceil(Hpt * ss))

    def T(u, v):
        return (u - u0) * scale + margin, (v1 - v) * scale + margin

    k_px = scale * ss
    X = ((UVD[:, 0] - u0) * scale + margin) * ss
    Y = ((v1 - UVD[:, 1]) * scale + margin) * ss
    D = UVD[:, 2]
    zbuf, idbuf = _raster(X[F], Y[F], D[F], Wp, Hp)

    # per-face normal and tone
    p = P3[F]
    nrm = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    facing = nrm @ view.n
    L = r3d._unit(view.x * light[0] + view.y * light[1] + view.n * light[2])
    dl = (np.where(facing[:, None] < 0, -nrm, nrm)) @ L
    tone = np.where(dl > 0.75, 0, np.where(dl > 0.35, 1, 2))
    hit = idbuf >= 0
    pbuf = np.where(hit, part_of[np.maximum(idbuf, 0)], -1)
    tbuf = np.where(hit, tone[np.maximum(idbuf, 0)], -1)
    label = np.where(hit, pbuf * 3 + tbuf, -1)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wpt:.2f}pt" height="{Hpt:.2f}pt" '
           f'viewBox="0 0 {Wpt:.2f} {Hpt:.2f}">']
    bycol = {}
    for lab in np.unique(label[label >= 0]):
        k, ti = divmod(int(lab), 3)
        mask = np.pad((label == lab).astype(np.float32), 1)
        gen = contourpy.contour_generator(z=mask, fill_type="OuterOffset")
        pts, offs = gen.filled(0.5, 1.5)
        polys = [(pp - 0.5, oo) for pp, oo in zip(pts, offs)]      # padded index -> pixel units (pad -1, centre +0.5)
        col = r3d._tone(scene.parts[k][2], tones[ti])
        bycol.setdefault(col, []).extend(_rings_d(polys, ss, 0.35))
    for col, ds in bycol.items():
        svg.append(f'<path d="{" ".join(ds)}" fill="{col}" fill-rule="evenodd" stroke="{col}" stroke-width="0.25"/>')

    # lines: crease, open and silhouette edges of every part, kept where visible
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fid = np.tile(np.arange(len(F)), 3)
    es = np.sort(e, axis=1)
    _, inv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    order = np.argsort(inv, kind="stable")
    first = np.r_[0, np.cumsum(cnt)[:-1]]
    f1 = fid[order[first]]
    f2 = np.where(cnt >= 2, fid[order[np.minimum(first + 1, len(order) - 1)]], -1)
    ev = es[order[first]]
    two = cnt == 2
    dot = np.where(two, (nrm[f1] * nrm[np.maximum(f2, 0)]).sum(1), -1.0)
    cos_c = math.cos(math.radians(crease))
    sil = two & (np.sign(facing[f1]) != np.sign(facing[np.maximum(f2, 0)]))
    sharp = ((cnt != 2) | (dot < cos_c)) & ~sil
    keep = sharp | sil
    ev, f1, f2, sil = ev[keep], f1[keep], f2[keep], sil[keep]
    ax_, ay_, ad = X[ev[:, 0]], Y[ev[:, 0]], D[ev[:, 0]]
    bx_, by_, bd = X[ev[:, 1]], Y[ev[:, 1]], D[ev[:, 1]]
    n = np.maximum(2, np.ceil(np.hypot(bx_ - ax_, by_ - ay_)).astype(np.int64) + 1)
    idx = np.repeat(np.arange(len(ev)), n)
    kk = np.arange(len(idx)) - np.repeat(np.cumsum(n) - n, n)
    t = kk / (n[idx] - 1)
    sx = ax_[idx] + (bx_[idx] - ax_[idx]) * t
    sy = ay_[idx] + (by_[idx] - ay_[idx]) * t
    sd = ad[idx] + (bd[idx] - ad[idx]) * t
    eps = max(0.03, 1.5 / k_px)
    vis = np.zeros(len(idx), bool)
    cx, cy = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            qx, qy = cx + dx, cy + dy
            inb = (qx >= 0) & (qy >= 0) & (qx < Wp) & (qy < Hp)
            qx, qy = np.clip(qx, 0, Wp - 1), np.clip(qy, 0, Hp - 1)
            idp = idbuf[qy, qx]
            ok = (idp == f1[idx]) | (idp == f2[idx]) | (zbuf[qy, qx] <= sd + eps)
            vis |= inb & ok
    inside = (sx >= 0) & (sy >= 0) & (sx < Wp) & (sy < Hp)
    vis &= inside
    pair = vis[:-1] & vis[1:] & (idx[:-1] == idx[1:])
    j = np.nonzero(pair)[0]
    seg_sil = sil[idx[j]]
    A2 = np.c_[sx[j], sy[j]] / ss
    B2 = np.c_[sx[j + 1], sy[j + 1]] / ss
    sharp_l = _chain([(tuple(a), tuple(b)) for a, b, s in zip(A2, B2, seg_sil) if not s])
    sil_l = _chain([(tuple(a), tuple(b)) for a, b, s in zip(A2, B2, seg_sil) if s])

    def simp(pls):
        out_ = []
        for pl in pls:
            ls = shapely.simplify(LineString(pl), 0.08) if len(pl) > 2 else LineString(pl)
            out_.append(list(ls.coords))
        return out_
    sharp_l, sil_l = simp(sharp_l), simp(sil_l)

    def pl_d(pls):
        return " ".join("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pl) for pl in pls)

    def plen(pl):
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pl[:-1], pl[1:]))

    # decals (lines only)
    for dc in scene.decals:
        segs = []
        for a3, b3 in dc["segs"]:
            ua, va = view.p2(a3)
            ub, vb = view.p2(b3)
            (xa, ya), (xb, yb) = T(ua, va), T(ub, vb)
            if dc["check"]:
                ok_ = True
                for (xx, yy), pp3 in (((xa, ya), a3), ((xb, yb), b3)):
                    i_, j_ = int(yy * ss), int(xx * ss)
                    if not (0 <= i_ < Hp and 0 <= j_ < Wp) or zbuf[i_, j_] > float(np.asarray(pp3) @ view.n) + 0.3:
                        ok_ = False
                if not ok_:
                    continue
            segs.append(f"M{xa:.2f} {ya:.2f} L{xb:.2f} {yb:.2f}")
        if segs:
            wd = dc["width_mm"] * scale if dc.get("width_mm") else dc["width"]
            op = dc.get("opacity", 1.0)
            extra = (f' stroke-opacity="{op:.2f}"' if op < 1 else "") + ' stroke-linecap="round" stroke-linejoin="round"'
            svg.append(f'<path d="{" ".join(segs)}" stroke="{dc["colour"]}" stroke-width="{wd:.2f}" fill="none"{extra}/>')

    small = [pl for pl in sharp_l if plen(pl) < small_pt]
    big = [pl for pl in sharp_l if plen(pl) >= small_pt]
    svg.append(f'<path d="{pl_d(small)}" stroke="{INK}" stroke-width="{line * 0.45:.2f}" fill="none" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')
    svg.append(f'<path d="{pl_d(big)}" stroke="{INK}" stroke-width="{line}" fill="none" stroke-linecap="round" '
               f'stroke-linejoin="round"/>')
    svg.append(f'<path d="{pl_d(sil_l)}" stroke="{INK}" stroke-width="{line * 1.3:.2f}" fill="none" stroke-linecap="round"/>')
    # heavy outline round each part's visible area
    for k, (_name, _m, _col, wf) in enumerate(scene.parts):
        mask = pbuf == k
        if outline <= 0 or not mask.any():
            continue
        z = np.pad(mask.astype(np.float32), 1, mode="edge")
        d = []
        for ln in contourpy.contour_generator(z=z, line_type="Separate").lines(0.5):
            c = (np.asarray(ln) - 0.5) / ss
            if len(c) < 3:
                continue
            closed = np.allclose(c[0], c[-1])
            if closed and Polygon(c).area < 4.0:
                continue
            # drop the stretches that run along the picture's frame (clipped parts)
            on_edge = (c[:, 0] < 0.6 / ss) | (c[:, 1] < 0.6 / ss) | (c[:, 0] > Wpt - 0.6 / ss) | (c[:, 1] > Hpt - 0.6 / ss)
            runs, cur = [], []
            for q, oe in zip(c, on_edge):
                if oe:
                    if len(cur) > 1:
                        runs.append(cur)
                    cur = []
                else:
                    cur.append(q)
            if len(cur) > 1:
                runs.append(cur)
            for r_ in runs:
                ls = shapely.simplify(LineString(r_), 0.12)
                d.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in ls.coords))
        if d:
            svg.append(f'<path d="{" ".join(d)}" stroke="{INK}" stroke-width="{outline * wf:.2f}" fill="none" '
                       f'stroke-linejoin="round"/>')
    svg.append("</svg>")

    # anchors: visible on the part they name
    def visible(names_on, p3):
        u, v = view.p2(p3)
        dd = float(np.asarray(p3) @ view.n)
        x, y = T(u, v)
        i0, j0 = int(y * ss), int(x * ss)
        ks = [names.index(o) for o in names_on]
        tol = 0.5 + 2.0 / k_px
        for di in range(-2, 3):
            for dj in range(-2, 3):
                i_, j_ = i0 + di, j0 + dj
                if 0 <= i_ < Hp and 0 <= j_ < Wp and pbuf[i_, j_] in ks and abs(zbuf[i_, j_] - dd) < tol:
                    return True
        return False
    hidden = [k for k, ons in scene.anchor_on.items() if not visible(ons, scene.anchors[k])]
    if hidden:
        raise SystemExit(f"{Path(out).name}: anchors hidden behind other parts: {hidden}")
    out = Path(out)
    Path(str(out) + ".svg").write_text("\n".join(svg))
    anchors = {k: T(*view.p2(p)) for k, p in scene.anchors.items()}
    json.dump({"w": Wpt, "h": Hpt, "scale": scale, "anchors": anchors,
               "holes": {k: bool(v and abs(view.n[2]) > 0.999) for k, v in scene.holes.items()}},
              open(Path(str(out) + ".json"), "w"), indent=1)
    if verbose:
        print(f"{out.name}: {len(F)} triangles, {len(sharp_l)} + {len(sil_l)} lines, {Wpt:.0f}x{Hpt:.0f}pt, "
              f"scale {scale:.3f} pt/mm (mesh render, {Wp}x{Hp} px)")
    return scale
