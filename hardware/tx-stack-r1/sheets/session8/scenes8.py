"""Session 8 (into the box) illustrations, same pipeline as Sessions 2-7 (r3d: hidden lines + flat colour).

The box is enclosure 4's printed base from cage.py (solids() for the printed parts inside, shell() for the floor,
walls and flanges), drawn the way session1/v2/assembly.py draws it: the box frame (Xb, Yb, Zb) is left-handed, so the
drawing frame is (Xb, Zb, Yb), a true right-handed picture, and every map is declared through cage.to_lid
(assembly.declare). The cards and the backplane come from assembly.py, the pack and the EVM from cage.contents() and
Session 7's EVM model (scenes7.add_evm, carried into the box), the glands from cage.GLANDS.

The EVM's two front clips and the test coupon are cage.py's (clip_solid, coupon_solid); the solar lead follows
cage.solar_route() and the gland map is cage.GLAND_USE. Not drawn: the base's STL (gated, cage.stl_gate), the gland
bodies' maker CAD (drawn as plain cylinders at the sizes in sources.py).

Run ONE scene per process: .venv-cad/bin/python -B scenes8.py NAME   (list: scenes8.py list)
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "session1" / "v2"
S7 = HERE.parent / "session7"
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
for p in (S7, V2, REPO / "layout", REPO / "cage", REPO, HERE):
    sys.path.insert(0, str(p))

import numpy as np                      # noqa: E402
import cadquery as cq                   # noqa: E402

import models as M                      # noqa: E402
import r3d                              # noqa: E402
import cage                             # noqa: E402
import stack as st                      # noqa: E402
from stack import S                     # noqa: E402
import assembly as A                    # noqa: E402
import scenes7 as E                     # noqa: E402  (the EVM model, the lead and tube helpers)
import lid_rim_spec as RS               # noqa: E402

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}
V, vp = A.V, A.vp
cyl, tube, COL = E.cyl, E.tube, E.COL
BRASS = "#C9A43A"
GLAND_C = "#3A3A3A"
CABLE = "#2B2B2B"
STRAP = "#2C2C2C"
TAPE = "#F4F1E8"
PACKBLUE = "#3C78C8"
DOT = {"B1": "#2D6FD0", "B2": "#2E9E4F", "B3": "#F2C318", "B4": "#D7262E"}

# which gland takes which cable, and the jack each port cable plugs into: cage.py's (it gives the reasons)
GLAND_USE = cage.GLAND_USE
JACK = {n: j for n, j in cage.GLAND_JACK.items() if n != "SOLAR"}


def R(name, s, d, up=(0, 1, 0), fit=(300, 300), keep=None, **kw):
    """keep: the anchors the page uses (the rest are dropped, so a part hidden in this view can't fail it)."""
    if keep is not None:
        for k in list(s.anchors):
            if k not in keep:
                s.anchors.pop(k)
                s.anchor_on.pop(k, None)
                s.holes.pop(k, None)
        missing = set(keep) - set(s.anchors)
        assert not missing, missing
    kw.setdefault("line", 0.3)
    kw.setdefault("outline", 1.0)
    r3d.render(s, OUT / name, d, up=up, fit=fit, **kw)


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def P(xb, yb, zb):
    """A box-frame point in the drawing frame."""
    return vp((xb, yb, zb))


def bx(x0, y0, z0, x1, y1, z1):
    """A box-frame box as a drawing-frame solid."""
    return V(M.box(x0, y0, z0, x1, y1, z1).val())


def zcyl(xb, yb, d, z0, z1):
    """A cylinder along Zb (the gland axis) at (Xb, Yb)."""
    return cyl(d / 2, P(xb, yb, z0), P(xb, yb, z1))


def new():
    s = r3d.Scene()
    A.declare(s)
    return s


def base(s, wall_y=16.0, bar=True, ledges=True, tray=True):
    keep = [k for k in A.BASE_KEEP if (bar or k != "retention bar") and (ledges or k != "charger ledges")
            and (tray or k != "pack tray")]
    old = A.BASE_KEEP
    A.BASE_KEEP = tuple(keep)
    try:
        A.base(s, wall_y)
    finally:
        A.BASE_KEEP = old


# ------------------------------------------------------------------ the EVM, carried into the box
class Into:
    """Session 7's EVM frame (x from J6 edge, y from the lid edge, z up from the underside) into the drawing:
    (x, y, z) -> box (EVM_X0 + x, EVM_Y1 - y, EVM_Z0 + z) -> drawing (Xb, Zb, Yb)."""

    def __init__(self, s):
        self.s = s

    @staticmethod
    def p(q):
        x, y, z = q
        return (cage.EVM_X0 + x, cage.EVM_Z0 + z, cage.EVM_Y1 - y)

    @staticmethod
    def v(u):
        return (u[0], u[2], -u[1])

    @staticmethod
    def sh(shape):
        return shape.rotate((0, 0, 0), (1, 0, 0), -90).translate((cage.EVM_X0, cage.EVM_Z0, cage.EVM_Y1))

    def add(self, name, shape, colour, weight=1.0):
        self.s.add(name, self.sh(shape), colour, weight)
        return self

    def anchor(self, name, q, on=None):
        self.s.anchor(name, self.p(q), on=on)

    def text(self, part, txt, origin, u, v, size, colour=None):
        self.s.text(part, txt, self.p(origin), self.v(u), self.v(v), size, colour=colour)


def declare_evm(s):
    s.placed_by("EVM frame -> box -> drawing", r3d.jacobian(lambda x, y, z: Into.p((x, y, z))))
    s.placed_by("EVM frame -> box -> cage.to_lid",
                r3d.jacobian(lambda x, y, z: cage.to_lid(cage.EVM_X0 + x, cage.EVM_Y1 - y, cage.EVM_Z0 + z)))


def evm(s, silk=True):
    declare_evm(s)
    E.add_evm(Into(s), silk=silk, jp_state="done")              # the jumpers as Session 7 leaves them


def pack(s, strap=True, rt1=True):
    b = cage.contents()[0]
    s.add("pack", bx(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1), PACKBLUE, 0.8)
    s.text("pack", "Adafruit #353  3.7 V 6600 mAh", P((b.x0 + b.x1) / 2 - 22, b.y1, b.z0 + 6), (1, 0, 0), (0, 1, 0),
           4.0, colour="#FFFFFF")
    top = b.z1
    if strap:
        w, ln, (c0, c1), y0 = cage.STRAP
        x0, x1 = c0 - w / 2, c1 + w / 2
        s.add("strap", V(M.box(x0, y0, top, x1, y0 + ln, top + 1.0).val()
                         .fuse(M.box(x0, y0, cage.PACK_TRAY_Z, x0 + w, y0 + ln, top + 1.0).val())
                         .fuse(M.box(x1 - w, y0, cage.PACK_TRAY_Z, x1, y0 + ln, top + 1.0).val())), STRAP, 0.7)
        s.anchor("strap", P(x1 - 12, y0 + ln, top + 0.5), on="strap")
    if rt1:
        # RT1 taped on the pack's face toward the lid (its leads go up to J7 on the EVM above)
        tx, tz = b.x0 + 54, b.z0 + 12
        s.add("rt1_tape", bx(tx - 6, b.y1, tz - 5, tx + 6, b.y1 + 0.4, tz + 5), TAPE, 0.6)
        s.add("rt1_bead", cyl(1.4, P(tx, b.y1 + 0.4, tz), P(tx, b.y1 + 2.0, tz)), "#1E1E1E")
        s.anchor("rt1", P(tx + 4, b.y1 + 0.4, tz - 2), on="rt1_tape")
    s.anchor("pack", P(b.x0 + 6, b.y1, b.z0 + 12), on="pack")
    # PG1: the pack's own plug and the JST PH socket on its leads, apart and taped (the pack stays unplugged)
    # (drawn lying on the pack's top, between the strap and the lid edge)
    s.add("pack_lead", tube([P(b.x1 - 0.9, b.y1 - 8, b.z1 - 4), P(b.x1 - 0.9, b.y1 - 8, b.z1 + 1.5),
                             P(b.x1 - 10, b.y1 - 8, b.z1 + 1.5)], 0.9), COL["red"])
    s.add("pg1_plug", bx(b.x1 - 17, b.y1 - 11, b.z1, b.x1 - 10, b.y1 - 5, b.z1 + 5), "#F2EEE4", 0.7)
    s.anchor("pg1", P(b.x1 - 13.5, b.y1 - 8, b.z1 + 5), on="pg1_plug")


def evm_boxes(s):
    """The EVM as cage.contents' boxes (for views where its detail would only clutter)."""
    for k, b in enumerate(cage.contents()[1:]):
        s.add(f"evmb{k}", bx(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1), E.EVM_PCB if k != 1 else "#F2EEE4", 0.6)
    s.add("evm_pcb", bx(cage.EVM_X0, cage.EVM_Y0, cage.EVM_Z0, cage.EVM_X1, cage.EVM_Y1, cage.EVM_Z0 + 1.6),
          E.EVM_PCB, 0.8)


# ------------------------------------------------------------------ glands, vent, bulkhead
def gland_dims(k):
    thread, inside, outside = cage.GLAND[k][:3]
    return thread, inside, outside, cage.GLAND_NUT[k]


def glands(s, outside=True, inside=True, stub=0.0):
    z_out = -cage.T                                          # the bottom wall's outside face (Zb)
    for x, y, k in cage.GLANDS:
        thread, inside_l, out_l, nut = gland_dims(k)
        nm = GLAND_USE[(x, y)].replace(" ", "_")
        if outside:
            s.add(f"g_{nm}", zcyl(x, y, nut, z_out - out_l * 0.45, z_out)
                  .fuse(zcyl(x, y, thread, z_out - out_l, z_out - out_l * 0.45)), GLAND_C, 0.8)
            s.anchor(f"g_{nm}", P(x, y + nut / 2, z_out - out_l * 0.25), on=f"g_{nm}")
        if inside:
            s.add(f"gn_{nm}", zcyl(x, y, nut, 1.0, inside_l), GLAND_C, 0.8)
        if stub:
            s.add(f"gc_{nm}", zcyl(x, y, 4.0 if k == "PG-7" else 5.0, z_out - out_l - stub, z_out - out_l), CABLE, 0.6)
    vx, vy = cage.VENT
    if outside:
        s.add("vent", zcyl(vx, vy, 14.0, z_out - 6.0, z_out), "#5A5A5A", 0.8)
        s.anchor("vent", P(vx, vy, z_out - 6.0), on="vent")
    yb, zb, hole, _seat = cage.SMA
    xo = cage.IN_X1 + cage.T + 0.75                        # the right wall's outside face
    s.add("sma_bh", cyl(hole / 2, P(xo, yb, zb), P(xo + 11.0, yb, zb)), E.GOLD, 0.8)
    s.add("sma_nut", cyl(cage.BULKHEAD_NUT / 2, P(xo, yb, zb), P(xo + 3.0, yb, zb)), E.STEEL, 0.8)
    s.anchor("sma_bh", P(xo + 11.0, yb, zb), on="sma_bh")


# ------------------------------------------------------------------ 01 the rim ring
@scene
def ring():
    s = r3d.Scene()
    s.placed_by("rim ring (lid-rim-spec frame, as printed)", r3d.jacobian(lambda x, y, z: (x, y, z)))
    sh = cage.ring_solid()
    s.add("ring", sh.val() if hasattr(sh, "val") else sh, "#E8E2D0", 0.9)
    sp = RS.load()
    hx, hy = sp["holes"]
    land = sp["land_z"][1]
    top = sp["lip_z"][1]
    s.anchor("hole", (hx + sp["hole_d"] / 2 + 0.3, hy, land), on="ring")
    bb = (sh.val() if hasattr(sh, "val") else sh).BoundingBox()
    # the lip: the highest face, sampled along the long side's middle
    lip = [v for v in (sh.val() if hasattr(sh, "val") else sh).Vertices() if abs(v.Z - top) < 1e-3 and v.Y < 0]
    lv = min(lip, key=lambda v: abs(v.X))
    s.anchor("lip", (lv.X, lv.Y, top), on="ring")
    R("ring", s, (0.35, -0.75, 0.9), up=(0, 0, 1), fit=(330, 220))


# ------------------------------------------------------------------ 02 the bare base: inserts
@scene
def base_ins():
    s = new()
    base(s, bar=False)
    bx_, z1, z2, _hole = cage.BAR_INS
    yf = cage.CARD_FRONT + 1.0
    for k, z in enumerate((z1, z2)):
        s.add(f"bar_ins{k}", cyl(2.3, P(bx_, yf - 5.0, z), P(bx_, yf + 0.2, z)), BRASS, 0.8)
        s.anchor(f"bar_ins{k}", P(bx_, yf + 0.2, z), on=f"bar_ins{k}")
    for k, (x, y) in enumerate(cage.CLIP_INS):
        s.add(f"clip_ins{k}", zcyl(x, y, 4.6, cage.EVM_Z0 - 5.0, cage.EVM_Z0 + 0.2), BRASS, 0.8)
        s.anchor(f"clip_ins{k}", P(x, y, cage.EVM_Z0 + 0.2), on=f"clip_ins{k}")
    # a corner block's bolt bore top: no insert there (the printed bolts thread the bore)
    s.anchor("corner", P(cage.IN_X1 - 6, cage.SEAM, cage.IN_Z1 - 6))
    R("base_ins", s, (0.5, 0.6, 1.0), fit=(330, 330))


# ------------------------------------------------------------------ 03 glands from outside
@scene
def glands_out():
    s = new()
    for k, b in enumerate(cage.shell()):
        if b.what.startswith("sealing lip"):
            continue
        s.add(f"sh{k}", bx(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1), "#C9C9C9", 0.8)
    glands(s)
    fx0, fx1 = S.val("mount_flange")[:2]
    s.anchor("flange", P((fx0 + fx1) / 2, -cage.T + 3.0, -cage.T - 20.0))
    R("glands_out", s, (0.2, -1.0, 0.5), up=(0, 0, 1), fit=(330, 300))


# ------------------------------------------------------------------ 04 the backplane in
def bp_anchors(s):
    pc, _cu = M.b_region(A.SC.SX, M.B_L)
    bb = pc.val().translate(cq.Vector(-A.SC.BX0, A.SC.BZ0, st.BP_BACK)).BoundingBox()
    zt = bb.zmax
    s.anchor("bp_left", (bb.xmin + 2.0, bb.ymin + (bb.ymax - bb.ymin) * 0.55, zt), on=("backplane", "bp_pads"))
    s.anchor("bp_right", (bb.xmax - 14.0, bb.ymin + (bb.ymax - bb.ymin) * 0.7, zt), on=("backplane", "bp_pads"))
    return bb


@scene
def bp_in():
    s = new()
    base(s, bar=False)
    A.backplane(s)
    bp_anchors(s)
    R("bp_in", s, (0.5, 0.6, 1.0), fit=(330, 330))


# ------------------------------------------------------------------ 05 the colour dots beside the slots
@scene
def dots():
    s = new()
    base(s, wall_y=None, bar=False)
    A.backplane(s)
    for b in st.ORDER:
        z = st.card_z(b) - st.BT / 2
        s.add(f"dot_{b}", cyl(2.5, P(cage.IN_X0 - 0.2, 85.0, z), P(cage.IN_X0 + 0.25, 85.0, z)), DOT[b], 0.9)
        s.anchor(f"dot_{b}", P(cage.IN_X0 + 0.25, 85.0, z + 1.0), on=f"dot_{b}")
    R("dots", s, (0.9, 0.25, 1.0), fit=(330, 330))


# ------------------------------------------------------------------ 06 the pack on its tray
@scene
def pack_in():
    s = new()
    base(s, ledges=True)
    A.backplane(s)
    pack(s)
    R("pack_in", s, (0.45, 0.35, 1.0), fit=(330, 330), keep=["rt1", "pg1", "strap", "pack"])


# ------------------------------------------------------------------ 07 the EVM on its ledges
@scene
def evm_in():
    s = new()
    base(s)
    A.backplane(s)
    pack(s, strap=True, rt1=False)
    evm(s)
    clips(s)
    R("evm_in", s, (0.45, 0.75, 1.0), fit=(330, 330), keep=["clip0", "clip1", "J2", "J8", "J6", "J3", "J5", "board"])


def clips(s):
    """The EVM's two front clips (cage.clip_solid) and their M3 socket caps."""
    hd, hh, _ln = cage.CLIP_SCREW
    for k, (x, y) in enumerate(cage.CLIP_INS):
        s.add(f"clip{k}", V(cage.clip_solid(k).val()), "#E8E2D0", 0.9)
        top = cage.EVM_Z0 + cage.CLIP_T
        s.add(f"clip_scr{k}", zcyl(x, y, hd, top, top + hh), E.STEEL, 0.8)
        b = cage.clip_boxes(k)[0]
        s.anchor(f"clip{k}", P((b.x0 + b.x1) / 2, b.y1, top), on=f"clip{k}")


# ------------------------------------------------------------------ 02 the test coupon
@scene
def coupon():
    s = new()
    s.add("coupon", V(cage.coupon_solid().val()), "#E8E2D0", 0.9)
    x, z = [(x, z) for x, z in cage.SCREWS if x < 60 and z > 100][0]
    s.anchor("bore", P(x, cage.SEAM, z))
    zs = st.card_z("B3") - st.BT / 2
    s.anchor("slot", P(cage.WALL, cage.COUPON[1] + 0.5, zs + 0.2))   # the slot's mouth on the cut face
    s.anchor("lip", P(cage.COUPON[3] - 3.0, cage.SEAM + cage.LIP_H, cage.IN_Z1 + cage.LIP_W / 2))
    R("coupon", s, (1.0, -0.7, 0.75), fit=(220, 230), keep=["bore", "slot", "lip"])


# ------------------------------------------------------------------ 08 the cards and the bar
@scene
def cards_in():
    s = new()
    base(s)
    A.backplane(s)
    pack(s, rt1=False)
    evm(s, silk=False)
    A.cards(s)
    R("cards_in", s, (0.5, 0.6, 1.0), fit=(330, 330), keep=[f"{b}_front" for b in st.ORDER] + ["bar"])


@scene
def built():
    s = new()
    base(s)
    A.backplane(s)
    pack(s, rt1=False)
    evm(s, silk=False)
    A.cards(s)
    glands(s, inside=True, stub=12.0)
    R("built", s, (0.5, 0.45, 1.0), fit=(330, 330), keep=[f"{b}_front" for b in st.ORDER] + ["bar"])


# ------------------------------------------------------------------ 09 the cable runs, seen from the lid
def jack_mouth(card, ref):
    for pl in st.PLACE[card]:
        if pl.get("ref") == ref:
            for x in pl["boxes"]:
                if x.what.endswith("jack") and not x.keepout:
                    a, c = st.card_to_box(card, x.x0, x.y0, x.z0), st.card_to_box(card, x.x1, x.y1, x.z1)
                    lo = [min(p, q) for p, q in zip(a, c)]
                    hi = [max(p, q) for p, q in zip(a, c)]
                    return ((lo[0] + hi[0]) / 2, hi[1], (lo[2] + hi[2]) / 2)
    raise KeyError(ref)


ZRUN = 18.5             # the run under the pack tray: above the corner block (Zb 16.4), under the tray (21.41)
assert cage.GLAND_IN < ZRUN - 2.0 and ZRUN + 2.0 < cage.PACK_TRAY_Z


def cable_path(name, k):
    """Plug at its jack -> forward -> right -> down the right column -> left under the tray -> its gland."""
    (gx, gy), = [g for g, n in GLAND_USE.items() if n == name]
    col = 101.0 + 3.2 * k
    card, ref = JACK[name]
    jx, jy, jz = jack_mouth(card, ref)
    yf = 86.0 + 1.2 * k
    return [(jx, jy + 12.0, jz), (jx, yf, jz), (col, yf, jz), (col, yf, ZRUN + 0.9 * k), (col, gy, ZRUN + 0.9 * k),
            (gx, gy, ZRUN + 0.9 * k), (gx, gy, cage.GLAND_IN)], (jx, jy, jz)


def solar_path():
    """The solar lead: cage.solar_route() (gland, forward under the EVM, up between the left clip and J8, back over
    the clip along the left wall, into J2 VIN2), checked in cage.py."""
    return cage.solar_route()


def plug_box(s, nm, jx, jy, jz):
    s.add(f"plug_{nm}", bx(jx - 4.8, jy, jz - 3.3, jx + 4.8, jy + 12.0, jz + 3.3), "#E6EEF2", 0.6)


@scene
def cables():
    s = new()
    base(s, wall_y=None)
    A.backplane(s)
    pack(s, strap=False, rt1=False)
    evm(s, silk=False)
    A.cards(s)
    glands(s, outside=False)
    names = ["S1 TH", "S2 UV", "S3 BARO", "S4 SPARE", "WIND", "RAIN"]
    for k, nm in enumerate(names):
        pts, (jx, jy, jz) = cable_path(nm, k)
        key = nm.replace(" ", "_")
        plug_box(s, key, jx, jy, jz)
        s.add(f"c_{key}", tube([P(*p) for p in pts], 1.5), CABLE, 0.5)
        s.anchor(f"c_{key}", P(pts[2][0], pts[2][1] + 1.5, pts[2][2] - 9 - 4 * k), on=f"c_{key}")
        s.anchor(f"plug_{key}", P(jx, jy + 12.0, jz + 3.3), on=f"plug_{key}")
    pts = solar_path()
    s.add("c_SOLAR", tube([P(*p) for p in pts], 1.8), "#7A1E1E", 0.5)
    s.anchor("c_SOLAR", P((pts[4][0] + pts[5][0]) / 2, pts[5][1] + 1.8, pts[5][2]), on="c_SOLAR")
    R("cables", s, (0, 0, 1), fit=(300, 400), keep=[a for a in s.anchors if a.startswith(("c_", "plug_"))])


# ------------------------------------------------------------------ 6P plugs: round cable, wind, rain
def plug6p(name, pos, colours):
    s = r3d.Scene()
    s.placed_by("6P plug (its own frame)", r3d.jacobian(lambda x, y, z: (x, y, z)))
    L, Wd, Ht = 20.0, 9.65, 6.6
    body = M.box(0, -Wd / 2, 0, L, Wd / 2, Ht).val().cut(M.box(3.0, -3.6, Ht - 1.9, L - 1.0, 3.6, Ht + 1).val())
    # the window: the clear body, drawn open on top so the conductors show as they do through the plastic
    latch = M.box(4, -2.5, -1.6, 14, 2.5, 0).val()
    s.add("plug", body, "#E6EEF2", 0.5)
    s.add("latch", latch, "#D8E2E8", 0.5)
    for p in range(1, 7):
        y = (p - 3.5) * 1.02
        s.add(f"pin{p}", M.box(0.2, y - 0.3, Ht - 0.6, 3.2, y + 0.3, Ht + 0.05).val(), E.GOLD)
        s.anchor(f"pin{p}", (1.6, y, Ht + 0.05), on=f"pin{p}")
    jac = M.box(L, -3.0, 1.2, L + 2.0, 3.0, 5.0).val()
    s.add("jacket", jac.fuse(M.box(L + 2.0, -3.0, 1.2, L + 14.0, 3.0, 5.0).val()), "#9A9A9A" if name != "plug_round"
          else "#2B2B2B", 0.6)
    for p, colr in zip(pos, colours):
        y = (p - 3.5) * 1.02
        s.add(f"w{p}", tube([(3.4, y, Ht - 1.2), (L - 1.0, y, Ht - 1.2), (L + 1.0, y * 0.6, 3.1)], 0.38), colr)
        s.anchor(f"w{p}", (L - 6.0, y, Ht - 1.2 + 0.38), on=f"w{p}")
    R(name, s, (0.15, -0.3, 1.0), up=(0, 1, 0), fit=(300, 160), line=0.4)


@scene
def plug_round():
    plug6p("plug_round", (2, 3, 4, 5), ("#8A8A8A", "#B0B0B0", "#6A6A6A", "#C8C8C8"))


@scene
def plug_wind():
    plug6p("plug_wind", (2, 3, 4, 5), ("#8A8A8A", "#B0B0B0", "#6A6A6A", "#C8C8C8"))


@scene
def plug_rain():
    plug6p("plug_rain", (3, 4), ("#8A8A8A", "#B0B0B0"))


# ------------------------------------------------------------------ the solar lead into J2
@scene
def solar_j2():
    s = r3d.Scene()
    s.placed_by("EVM frame -> box -> cage.to_lid",
                r3d.jacobian(lambda x, y, z: cage.to_lid(cage.EVM_X0 + x, cage.EVM_Y1 - y, cage.EVM_Z0 + z)))
    E.add_evm(s)
    for k, colr in ((0, "red"), (1, "black")):
        pts = E.into("J2", E.term_k("J2", ("VIN2", "GND")[k]), back=30.0)
        E.lead(s, f"sol{k}", pts, colr, r=0.65)
        # a bootlace ferrule on the bare end
        a, b = np.asarray(pts[-2], float), np.asarray(pts[-1], float)
        s.add(f"fer{k}", cyl(0.85, a + (b - a) * 0.15, a + (b - a) * 0.6), E.STEEL)
        s.anchor(f"sol{k}", tuple(np.asarray(pts[0], float) + np.array([0, 0, 0.65])), on=f"sol{k}")
    R7 = E.R
    E.OUT = OUT
    try:
        R7("solar_j2", s, (-0.55, -0.35, 1.0), up=(0, 1, 0), fit=(300, 260), line=0.4)
    finally:
        E.OUT = S7 / "svg"


# ------------------------------------------------------------------ the coax to the bulkhead
def a1_box(what):
    for pl in st.PLACE["B3"]:
        if pl.get("ref") == "A1":
            for x in pl["boxes"]:
                if x.what.endswith(what):
                    a, c = st.card_to_box("B3", x.x0, x.y0, x.z0), st.card_to_box("B3", x.x1, x.y1, x.z1)
                    return st.Box(min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1]),
                                  min(a[2], c[2]), max(a[2], c[2]), what)
    raise KeyError(what)


@scene
def coax():
    s = new()
    base(s)
    A.backplane(s)
    pack(s, rt1=False)
    evm(s, silk=False)
    A.cards(s)
    glands(s, outside=False, inside=True)
    adp, arm = a1_box("SMA right-angle adapter"), a1_box("SMA adapter forward arm")
    s.anchor("ad1", P(adp.x1 - 1.0, (adp.y0 + adp.y1) / 2, adp.z1 + 0.05))
    ax, az = (arm.x0 + arm.x1) / 2, (arm.z0 + arm.z1) / 2
    pe, yb, zb, _ = cage.coax(arm)
    s.add("plug", cyl(3.2, P(ax, arm.y1, az), P(ax, pe, az)), E.STEEL, 0.7)
    s.anchor("plug", P(ax, (arm.y1 + pe) / 2, az + 3.2), on="plug")
    r = S.val("rg316_bend")
    _run, inner = cage.coax_route(arm)
    pts = [(ax, pe, az), (ax, pe + 4, az - 2), (ax + r, pe + 4, az - 10), (ax + r, yb, zb + 12), (inner, yb, zb)]
    s.add("coax", tube([P(*p) for p in pts], 1.3), "#4A4A4A", 0.6)
    s.anchor("coax", P(ax + r + 1.3, (pe + 4 + yb) / 2, (az - 10 + zb + 12) / 2), on="coax")
    s.add("bh_plug", cyl(3.2, P(inner, yb, zb), P(cage.IN_X1 - 9.0, yb, zb)), E.STEEL, 0.7)
    s.anchor("bh_plug", P((inner + cage.IN_X1 - 9.0) / 2, yb + 3.2, zb), on="bh_plug")
    s.anchor("evm_corner", P(cage.EVM_X1 - 0.5, cage.EVM_Y1, cage.EVM_Z0 + 1.6), on="evm")
    R("coax", s, (0.55, 0.15, 1.0), fit=(330, 330), keep=["ad1", "plug", "coax", "bh_plug", "evm_corner"])


# ------------------------------------------------------------------ the box shut and mounted
@scene
def mount():
    s = new()
    for k, b in enumerate(cage.shell()):
        s.add(f"sh{k}", bx(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1), "#C9C9C9", 0.8)
    glands(s, stub=25.0)
    fx0, fx1, reach, ft = S.val("mount_flange")[:4]
    o1z = cage.H + cage.T
    s.anchor("flange_top", P(fx0 + 4.0, -cage.T, o1z + reach * 0.5))
    s.anchor("flange_bot", P(fx0 + 4.0, -cage.T, -cage.T - reach * 0.5))
    s.anchor("seam", P(cage.W * 0.6, cage.SEAM, cage.IN_Z1 + 1.0))
    s.anchor("bolt", P(cage.IN_X0 + 6.0, cage.SEAM, cage.IN_Z1 - 6.0))
    R("mount", s, (0.45, -0.35, -1.0), fit=(300, 330), keep=["flange_top", "flange_bot"])


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    for n in names:
        SCENES[n]()
