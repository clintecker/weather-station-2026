"""Vector line art with flat colour from real 3D geometry (CadQuery / OpenCascade).

render(scene, ...) projects a scene orthographically:
  1. OpenCascade exact hidden-line removal gives the visible edges (sharp, smooth and silhouette).
  2. The visible edges are noded and polygonized into 2D regions (shapely). Each region is coloured by casting a
     ray into the scene through a point inside it: the nearest face hit owns the region. No painter's sort, so
     holes, overlaps and big faces near small ones come out right.
  3. Faces are toned by their normal (three flat steps, a light from the upper left).
  4. Decals (silkscreen, writing, scale ticks) are planar text or lines laid on a face, mapped by the same
     projection, and kept only where that face is the visible one.
Writes an SVG (points, y down) plus a JSON of named anchors in the same coordinates for the PDF script's labels.
"""
import json
import math
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import polygonize, unary_union

import cadquery as cq
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Lin, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

INK = "#121212"


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _hex(c):
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], float)


def _tone(col, k):
    r = np.clip(_hex(col) * k, 0, 255).astype(int)
    return "#%02X%02X%02X" % tuple(r)


def jacobian(f, p0=(10.0, 20.0, 30.0), h=1.0):
    """Linear part of a map f(x, y, z) -> (x', y', z') (affine), by differences: for Scene.placed_by."""
    p0 = np.asarray(p0, float)
    f0 = np.asarray(f(*p0), float)
    return np.array([np.asarray(f(*(p0 + h * e)), float) - f0 for e in np.eye(3)]).T / h


class Scene:
    def __init__(self):
        self.parts = []      # (name, TopoDS_Shape, colour, line weight factor)
        self.decals = []     # dicts
        self.anchors = {}    # name -> 3D point
        self.xf = None       # (R 3x3, t) applied to decals and anchors added while set
        self.holes = {}      # anchor name -> True if the hole is drawn face-on (checked against the SVG)
        self.anchor_on = {}  # anchor name -> part name(s) it must be seen on (render fails if it is hidden)
        self.frames = []     # (what, 3x3 linear part) of each map from a physical (right-handed) frame into this scene

    def placed_by(self, what, R):
        """Declare that some geometry was carried into this scene by the linear map R (3x3) from a right-handed
        physical frame. render() refuses any reflection (det < 0): a mirrored picture of a real object."""
        self.frames.append((what, np.asarray(R, float)))
        return self

    def _p(self, p):
        p = np.asarray(p, float)
        return p if self.xf is None else self.xf[0] @ p + self.xf[1]

    def _v(self, v):
        v = np.asarray(v, float)
        return v if self.xf is None else self.xf[0] @ v

    def add(self, name, shape, colour, weight=1.0):
        if isinstance(shape, cq.Workplane):
            shape = shape.val() if len(shape.vals()) == 1 else cq.Compound.makeCompound(shape.vals())
        if isinstance(shape, cq.Shape):
            shape = shape.wrapped
        self.parts.append((name, shape, colour, weight))
        return self

    def text(self, part, s, origin, u, v, size, colour="#FFFFFF", font="Helvetica", anchor="middle", lift=0.0):
        """Planar text on a face of `part`: origin = baseline anchor (3D), u = text direction, v = up."""
        self.decals.append(dict(kind="text", part=part, s=s, o=self._p(origin), u=_unit(self._v(u)), v=_unit(self._v(v)),
                                size=size, colour=colour, font=font, anchor=anchor))

    def lines(self, part, segs, colour=INK, width=0.4, check=True, opacity=1.0, width_mm=None):
        """3D segments drawn as decals: [(p0, p1), ...]; width in output points (or width_mm in model mm).
        Consecutive segments that share an end are joined into one path (round joins), so a translucent
        polyline has no dark overlaps."""
        self.decals.append(dict(kind="lines", part=part, segs=[(self._p(a), self._p(b)) for a, b in segs],
                                colour=colour, width=width, check=check, opacity=opacity, width_mm=width_mm))

    def anchor(self, name, p, on=None):
        """on: the part (or tuple of parts) a leader to this anchor names; render() checks the anchor is visible
        on it, so a leader can never land on whatever happens to be drawn in front."""
        self.anchors[name] = self._p(p)
        if on:
            self.anchor_on[name] = (on,) if isinstance(on, str) else tuple(on)

    def hole(self, name, p, drawn=True):
        """An anchor that names a hole: page callouts on it are checked by holecheck.py."""
        self.anchors[name] = self._p(p)
        self.holes[name] = drawn


def _edge_polylines(compound, defl):
    out = []
    if compound is None or compound.IsNull():
        return out
    ex = TopExp_Explorer(compound, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge_s(ex.Current())
        try:
            c = BRepAdaptor_Curve(e)
            if c.GetType() == GeomAbs_Line:
                pts = [c.Value(c.FirstParameter()), c.Value(c.LastParameter())]
            else:
                d = GCPnts_QuasiUniformDeflection(c, defl)
                pts = [d.Value(i) for i in range(1, d.NbPoints() + 1)] if d.IsDone() else []
            pl = [(p.X(), p.Y()) for p in pts]
            if len(pl) >= 2:
                out.append(pl)
        except Exception:
            pass
        ex.Next()
    return out


class View:
    def __init__(self, direction, up=(0, 0, 1)):
        self.n = _unit(direction)                      # toward the viewer
        up = np.asarray(up, float)
        x = np.cross(up, self.n)
        if np.linalg.norm(x) < 1e-9:
            x = np.cross((0, 1, 0), self.n)
        self.x = _unit(x)
        self.y = np.cross(self.n, self.x)

    def p2(self, p):
        p = np.asarray(p, float)
        return float(p @ self.x), float(p @ self.y)

    def ax2(self):
        return gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*self.n), gp_Dir(*self.x))


def render(scene, out, direction, up=(0, 0, 1), fit=None, scale=None, margin=6, light=(-0.5, 0.35, 0.8),
           line=0.55, outline=1.1, defl=None, tones=(1.0, 0.86, 0.72), verbose=True, snap=3e-4, crop=None, small_pt=7.0):
    """Render `scene` to out.svg + out.json. fit=(w_pt, h_pt) scales to fit; or scale = pt per mm."""
    t0 = time.time()
    for what, R in scene.frames:
        d = float(np.linalg.det(R))
        assert d > 0, f"{Path(str(out)).name}: {what} is placed by a reflection (det {d:+.3f}): the picture would be mirrored"
    view = View(direction, up)
    assert np.linalg.det(np.c_[view.x, view.y, view.n]) > 0
    comp = cq.Compound.makeCompound([cq.Shape.cast(s) for _, s, _, _ in scene.parts]).wrapped
    algo = HLRBRep_Algo()
    algo.Add(comp)
    algo.Projector(HLRAlgo_Projector(view.ax2()))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    bb = cq.Shape.cast(comp).BoundingBox()
    diag = bb.DiagonalLength
    defl = defl or diag / 4000
    sharp = _edge_polylines(h.VCompound(), defl) + _edge_polylines(h.Rg1LineVCompound(), defl)
    sil = _edge_polylines(h.OutLineVCompound(), defl)
    allp = sharp + sil
    t1 = time.time()

    # regions
    q = 1e-4
    ls = [LineString(np.round(np.array(p), 4)) for p in allp if len(p) >= 2]
    ls = [l for l in ls if l.length > q]
    ml = MultiLineString(ls)
    snap_tol = diag * snap
    if snap_tol > 0:
        # close the small gaps OpenCascade leaves where silhouettes meet edges, or a region never closes
        ends = shapely.MultiPoint([c for l in ls for c in (l.coords[0], l.coords[-1])])
        ml = shapely.snap(ml, ends, snap_tol)
        ml = shapely.snap(ml, ml, snap_tol)
    noded = unary_union(ml)
    regions = [r for r in polygonize(noded) if r.area > 1e-6]
    # ray cast
    inters = []
    for name, shp, col, w in scene.parts:
        it = IntCurvesFace_ShapeIntersector()
        it.Load(shp, 1e-6)
        inters.append(it)
    far = diag * 4 + 1000
    L = view.x * light[0] + view.y * light[1] + view.n * light[2]
    L = _unit(L)

    def hit(u, v):
        o = view.x * u + view.y * v + view.n * far
        lin = gp_Lin(gp_Pnt(*o), gp_Dir(*(-view.n)))
        best = None
        for k, it in enumerate(inters):
            it.Perform(lin, -1e9, 1e9)
            if not it.IsDone():
                continue
            for i in range(1, it.NbPnt() + 1):
                wpar = it.WParameter(i)
                if best is None or wpar < best[0]:
                    best = (wpar, k, it.Face(i), it.UParameter(i), it.VParameter(i))
        return best

    fills = []
    miss = []
    for r in regions:
        rp = r.representative_point()
        b = hit(rp.x, rp.y)
        if b is None:
            miss.append(r)
            continue
        _, k, face, uu, vv = b
        surf = BRepAdaptor_Surface(face)
        pr = BRepLProp_SLProps(surf, uu, vv, 1, 1e-6)
        if pr.IsNormalDefined():
            nn = pr.Normal()
            nvec = np.array([nn.X(), nn.Y(), nn.Z()])
            if face.Orientation() == TopAbs_REVERSED:
                nvec = -nvec
            if nvec @ view.n < 0:
                nvec = -nvec
            d = float(nvec @ L)
        else:
            d = 1.0
        tone = tones[0] if d > 0.75 else tones[1] if d > 0.35 else tones[2]
        fills.append((r, _tone(scene.parts[k][2], tone), k))
    t2 = time.time()

    # optional crop window: (3D centre, half width mm, half height mm)
    if crop is not None:
        cu, cv = view.p2(crop[0])
        win = shapely.box(cu - crop[1], cv - crop[2], cu + crop[1], cv + crop[2])

        def clip_pl(pls):
            out = []
            for p in pls:
                g = LineString(p).intersection(win)
                for gg in getattr(g, "geoms", [g]):
                    if gg.geom_type == "LineString" and not gg.is_empty:
                        out.append(list(gg.coords))
            return out
        sharp, sil = clip_pl(sharp), clip_pl(sil)
        allp = sharp + sil
        nf = []
        for r, col, k in fills:
            g = r.intersection(win)
            for gg in getattr(g, "geoms", [g]):
                if gg.geom_type == "Polygon" and not gg.is_empty:
                    nf.append((gg, col, k))
        fills = nf
        x0, y0, x1, y1 = win.bounds
    else:
        win = None
        xs = [x for p in allp for x, _ in p]
        ys = [y for p in allp for _, y in p]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if scale is None:
        fw, fh = fit
        scale = min((fw - 2 * margin) / (x1 - x0), (fh - 2 * margin) / (y1 - y0))
    W = (x1 - x0) * scale + 2 * margin
    H = (y1 - y0) * scale + 2 * margin

    def T(x, y):
        return (x - x0) * scale + margin, (y1 - y) * scale + margin

    def path_of(coords):
        pts = [T(x, y) for x, y in coords]
        return "M" + " L".join(f"{a:.2f} {b:.2f}" for a, b in pts) + " Z"

    def poly_d(poly):
        d = path_of(poly.exterior.coords)
        for i in poly.interiors:
            d += " " + path_of(i.coords)
        return d

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.2f}pt" height="{H:.2f}pt" viewBox="0 0 {W:.2f} {H:.2f}">']
    # fills grouped by colour
    bycol = {}
    for r, col, k in fills:
        bycol.setdefault(col, []).append(r)
    for col, rs in bycol.items():
        d = " ".join(poly_d(r) for r in rs)
        svg.append(f'<path d="{d}" fill="{col}" fill-rule="evenodd" stroke="{col}" stroke-width="0.25"/>')

    # decals
    def visible(part_name, p3):
        u, v = view.p2(p3)
        b = hit(u, v)
        if b is None:
            return False
        pk = [n for n, *_ in scene.parts].index(part_name)
        if b[1] != pk:
            return False
        o = view.x * u + view.y * v + view.n * far
        dep = far - float((np.asarray(p3) - (view.x * u + view.y * v)) @ view.n)
        return abs(b[0] - dep) < 0.3
    hidden = [k for k, ons in scene.anchor_on.items() if not any(visible(o, scene.anchors[k]) for o in ons)]
    if hidden:
        raise SystemExit(f"{Path(out).name}: anchors hidden behind other parts: {hidden}")
    for dc in scene.decals:
        if dc["kind"] == "text":
            if win is not None and not win.contains(shapely.Point(view.p2(dc["o"]))):
                continue
            if not visible(dc["part"], dc["o"] + dc["u"] * 0.01):
                continue
            ox, oy = T(*view.p2(dc["o"]))
            ux, uy = view.p2(dc["u"])
            vx, vy = view.p2(dc["v"])
            # matrix maps text space (x right, y down) -> svg
            a, b_, c_, d_ = ux * scale, -uy * scale, -vx * scale, vy * scale
            fs = dc["size"]
            s = dc["s"].replace("&", "&amp;").replace("<", "&lt;")
            svg.append(f'<g transform="matrix({a:.5f} {b_:.5f} {c_:.5f} {d_:.5f} {ox:.2f} {oy:.2f})">'
                       f'<text x="0" y="0" font-family="{dc["font"]}" font-size="{fs:.3f}" fill="{dc["colour"]}" '
                       f'text-anchor="{dc["anchor"]}">{s}</text></g>')
        else:
            segs = []
            last = None
            for a3, b3 in dc["segs"]:
                if win is not None and not (win.contains(shapely.Point(view.p2(a3))) and
                                            win.contains(shapely.Point(view.p2(b3)))):
                    continue
                if dc["check"] and not visible(dc["part"], (a3 + b3) / 2):
                    continue
                (ax_, ay_), (bx_, by_) = T(*view.p2(a3)), T(*view.p2(b3))
                if last is not None and abs(last[0] - ax_) < 0.01 and abs(last[1] - ay_) < 0.01:
                    segs.append(f"L{bx_:.2f} {by_:.2f}")
                else:
                    segs.append(f"M{ax_:.2f} {ay_:.2f} L{bx_:.2f} {by_:.2f}")
                last = (bx_, by_)
            if segs:
                wd = dc["width_mm"] * scale if dc.get("width_mm") else dc["width"]
                op = dc.get("opacity", 1.0)
                extra = (f' stroke-opacity="{op:.2f}"' if op < 1 else "") + ' stroke-linecap="round" stroke-linejoin="round"'
                svg.append(f'<path d="{" ".join(segs)}" stroke="{dc["colour"]}" stroke-width="{wd:.2f}" fill="none"{extra}/>')

    # lines: sharp + smooth thin, silhouettes heavier, part outlines heaviest
    def pl_d(pls):
        return " ".join("M" + " L".join("%.2f %.2f" % T(x, y) for x, y in p) for p in pls)
    def plen(p):
        return sum(math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]) for i in range(len(p) - 1)) * scale
    small = [p for p in sharp if plen(p) < small_pt]
    big = [p for p in sharp if plen(p) >= small_pt]
    svg.append(f'<path d="{pl_d(small)}" stroke="{INK}" stroke-width="{line * 0.45:.2f}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    svg.append(f'<path d="{pl_d(big)}" stroke="{INK}" stroke-width="{line}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    svg.append(f'<path d="{pl_d(sil)}" stroke="{INK}" stroke-width="{line * 1.3:.2f}" fill="none" stroke-linecap="round"/>')
    # heavy outline around each part's visible area
    for k, (name, shp, col, wf) in enumerate(scene.parts):
        rs = [r for r, _, kk in fills if kk == k]
        if not rs or outline <= 0:
            continue
        u = unary_union([r.buffer(1e-3) for r in rs])
        geoms = getattr(u, "geoms", [u])
        d = []
        for g in geoms:
            if g.area * scale * scale < 4:
                continue
            if win is None:
                d.append(path_of(g.exterior.coords))
            else:
                e = g.exterior.difference(win.exterior.buffer(1e-3 + 0.5 / scale))
                for ee in getattr(e, "geoms", [e]):
                    if not ee.is_empty:
                        d.append(path_of(ee.coords)[:-2])
        if d:
            svg.append(f'<path d="{" ".join(d)}" stroke="{INK}" stroke-width="{outline * wf:.2f}" fill="none" stroke-linejoin="round"/>')
    svg.append("</svg>")
    out = Path(out)
    Path(str(out) + ".svg").write_text("\n".join(svg))
    anchors = {k: T(*view.p2(p)) for k, p in scene.anchors.items()}
    json.dump({"w": W, "h": H, "scale": scale, "anchors": anchors, "holes": {k: bool(v and abs(view.n[2]) > 0.999) for k, v in scene.holes.items()}}, open(Path(str(out) + ".json"), "w"), indent=1)
    if verbose:
        print(f"{out.name}: {len(allp)} edges, {len(regions)} regions ({len(miss)} empty), hlr {t1 - t0:.1f}s, fill {t2 - t1:.1f}s, "
              f"{W:.0f}x{H:.0f}pt, scale {scale:.3f} pt/mm")
    return scale
