"""WHAT YOU ARE BUILDING: enclosure 2's base, the backplane and the four cards in their sockets (repo db1936a).

The box frame (Xb, Yb, Zb) is left-handed (db1936a, cage.to_lid, L12): seen from the lid, glands down, Xb runs left
to right, Zb up, Yb toward you. So the drawing frame is (Xb, Zb, Yb), a true right-handed picture of the real box;
every placement is checked by r3d's handedness assertion (Scene.placed_by) through cage.to_lid. The base comes from cage.py (solids() for the printed
parts inside, shell() for the floor and walls); the cards and their parts are stack.py's placement boxes (every part
as its box, keep-outs left out), carried into the box by stack.card_to_box; the backplane is models.b_region.
  ../../cadx/bin/python -B assembly.py [asm_iso asm_lid]
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")   # live tree, db1936a
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "layout"))
sys.path.insert(0, str(REPO / "cage"))

import cadquery as cq      # noqa: E402
import models as M         # noqa: E402
import r3d                 # noqa: E402
import stack as st         # noqa: E402
import cage                # noqa: E402
import scenes as SC        # noqa: E402  (board-frame -> box-frame constants for the backplane)

OUT = HERE / "svg"


def V(sh):
    """Box frame (Xb, Yb, Zb) is left-handed seen from the lid; draw in (Xb, Zb, Yb), right-handed: x right, y up
    (toward the top wall), z toward the lid. (x, y, z) -> (x, z, y)."""
    return sh.rotate((0, 0, 0), (1, 0, 0), 90).mirror("XZ")


def vp(p):
    return (p[0], p[2], p[1])
PLASTIC = "#D9D9D9"
BASE_KEEP = ("left wall", "right corner post", "backplane support pads", "retention bar", "charger ledges", "pack tray")
# enclosure 4 prints the shelves (the charger ledges and the pack tray); it has no backplane screw posts


def from_lid(X, Y, Z):
    """The inverse of cage.to_lid: the right-handed lid-centre frame -> the box frame."""
    return cage.W / 2 - Y, Z - cage.T, X + cage.H / 2


def declare(s):
    """Handedness: each map from a right-handed physical frame into the drawing must be a rotation (det > 0)."""
    s.placed_by("enclosure 2 (lid-centre frame -> box -> drawing)", r3d.jacobian(lambda *p: vp(from_lid(*p))))
    for b in st.ORDER:
        s.placed_by(f"{b} (card frame -> stack.card_to_box -> drawing)",
                    r3d.jacobian(lambda x, y, z, b=b: vp(st.card_to_box(b, x, y, z))))
    s.placed_by("backplane (line, hole, out of FRONT) -> drawing",
                r3d.jacobian(lambda x, y, z: (x - SC.BX0, y + SC.BZ0, z + st.BP_BACK)))
    # and the board frame is itself a true frame of the real board: FRONT toward the lid, through cage.to_lid
    s.placed_by("backplane board frame -> lid-centre frame",
                r3d.jacobian(lambda x, y, z: cage.to_lid(x - SC.BX0, z + st.BP_BACK, y + SC.BZ0)))
    # the drawing's own copies of the box mapping agree with the repo's
    assert all(abs(a - b_) < 1e-9 for a, b_ in zip(vp(st.card_to_box("B4", 1, 2, 3)),
                                                   card_point("B4", (1, 2, 3))))


def base(s, wall_y=None):
    """wall_y: cut the floor's walls down to this Yb (for the iso, so they hide nothing)."""
    for name, shape in cage.solids():
        if name in BASE_KEEP:
            s.add(name.replace(" ", "_"), V(cq.Compound.makeCompound(shape.vals()) if hasattr(shape, "vals") else shape), PLASTIC, 0.8)
    walls = [b for b in cage.shell() if b.what in ("floor (back)", "left wall", "right wall", "bottom wall", "top wall")]
    for k, b in enumerate(walls):
        y1 = b.y1 if wall_y is None or b.what == "floor (back)" else min(b.y1, wall_y)
        s.add(f"wall{k}", V(M.box(b.x0, b.y0, b.z0, b.x1, y1, b.z1).val()), "#C9C9C9", 0.8)


def backplane(s):
    """Board frame (bx, by, bz) -> drawing frame (Xb, Zb, Yb) = (bx - BX0, by + BZ0, 8.0 + bz): a translation."""
    pc, cu = M.b_region(SC.SX, M.B_L)                    # nothing drilled: no screws since enclosure 4

    def tf(sh):
        return sh.translate((-SC.BX0, SC.BZ0, st.BP_BACK))
    s.add("backplane", tf(pc), M.HAZ, 0.9).add("bp_pads", tf(cu), M.TIN, 0.1)


def card_tf(b, sh):
    """Card frame (z = 0 at the card's top face) -> box: (CAGE_LEFT + x, BP_FRONT + Y_BP - y, card_z + z)."""
    return V(sh.mirror("XZ").translate((st.CAGE_LEFT, st.BP_FRONT + st.Y_BP, st.card_z(b))))


def cards(s):
    for b in st.ORDER:
        brd, _ = M.solderful(snapped=True, labels=False)
        s.add(f"{b}_card", card_tf(b, brd.translate((0, 0, -M.SB_T))), M.RED_PCB, 1.0)
        by_col = {}
        for pl in st.PLACE[b]:
            col = st.KIND.get(pl["fp"], ("#555555",))[0]
            for bx in pl["boxes"]:
                if bx.keepout or bx.service or bx.x1 - bx.x0 < 0.05 or bx.y1 - bx.y0 < 0.05 or bx.z1 - bx.z0 < 0.05:
                    continue
                by_col.setdefault(col, []).append(M.box(bx.x0, bx.y0, bx.z0, bx.x1, bx.y1, bx.z1).val())
        for k, (col, sols) in enumerate(by_col.items()):
            s.add(f"{b}_parts{k}", card_tf(b, cq.Compound.makeCompound(sols)), col, 0.5)
        # its 1x30 socket on the backplane: lines 1-30 on its socket hole row
        zr = st.BP_Z0 + (st.SOCKET_HOLE[b] - 1) * st.P
        x0, x1 = st.strip_x(1) - st.P / 2, st.strip_x(30) + st.P / 2
        s.add(f"{b}_socket", V(M.box(x0, st.BP_FRONT, zr - 1.27, x1, st.BP_FRONT + st.S.val("socket_h"), zr + 1.27).val()),
              "#2A2A2A", 0.7)
        cz = st.card_z(b)
        s.anchor(f"{b}_front", vp((st.CAGE_LEFT + st.BW * 0.62, st.BP_FRONT + st.Y_BP, cz + 0.8)))
        s.anchor(f"{b}_right", vp((st.CAGE_LEFT + st.BW, st.BP_FRONT + st.Y_BP - 20, cz + 0.8)))
        s.anchor(f"{b}_socket", vp((x1, st.BP_FRONT + st.S.val("socket_h"), zr)))
    # between lines 27 and 28, 1.2 above the bottom edge: the corner of the backplane that B4 does not hide in
    #   the iso (line 4 was behind B4, so the BACKPLANE leader landed on B4)
    s.anchor("bp_low", vp((st.strip_x(27) + st.P / 2, st.BP_FRONT, SC.BZ0 + 1.2)), on=("backplane", "bp_pads"))
    s.anchor("bp_low_l", vp((12.0, st.BP_FRONT, SC.BZ0 + 6)))
    s.anchor("post_r", vp((95.8, 21.96, 76.0)))
    s.anchor("bar", vp((3.0, cage.CARD_FRONT + 3.5, 74.5)))


def card_point(b, p):
    """card_tf on one point (for the assertion that it equals vp(stack.card_to_box))."""
    sh = card_tf(b, cq.Vertex.makeVertex(*p))
    v = sh.Center()
    return v.x, v.y, v.z


def scene(wall_y=None):
    s = r3d.Scene()
    declare(s)
    base(s, wall_y)
    backplane(s)
    cards(s)
    return s


def asm_iso():
    s = scene(wall_y=16.0)
    r3d.render(s, OUT / "asm_iso", (0.5, 0.6, 1.0), up=(0, 1, 0), fit=(330, 330), line=0.3, outline=1.0)


def asm_lid():
    s = scene()
    r3d.render(s, OUT / "asm_lid", (0, 0, 1), up=(0, 1, 0), fit=(250, 330), line=0.3, outline=1.0)


if __name__ == "__main__":
    for n in sys.argv[1:] or ["asm_iso", "asm_lid"]:
        globals()[n]()
