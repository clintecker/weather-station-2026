"""Handedness declarations shared by both sessions' scenes (repo db1936a: the box frame is left-handed; cage.to_lid
maps it to the right-handed lid-centre frame; stack.card_to_box carries the right-handed card frame into the box).
Each render declares the maps its geometry went through; r3d.render refuses any with det < 0 (a mirrored picture)."""
import sys
from pathlib import Path

REPO = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1")
for d in ("layout", "cage"):
    if str(REPO / d) not in sys.path:
        sys.path.insert(0, str(REPO / d))
import r3d                 # noqa: E402
import stack as st         # noqa: E402
import cage                # noqa: E402

BP_BX0, BP_BZ0 = None, None


def vp(p):
    """Box frame -> drawing frame (Xb, Zb, Yb): seen from the lid, glands down, x right, y up, z toward you."""
    return (p[0], p[2], p[1])


def from_lid(X, Y, Z):
    return cage.W / 2 - Y, Z - cage.T, X + cage.H / 2


def card_frame(s, b="B4"):
    """Pictures drawn in the card frame: a true frame of the real card (card -> box -> lid is a rotation)."""
    s.placed_by(f"card frame ({b}) -> stack.card_to_box -> cage.to_lid",
                r3d.jacobian(lambda x, y, z: cage.to_lid(*st.card_to_box(b, x, y, z))))


def board_frame(s, bx0, bz0):
    """Pictures drawn in the PAD3U board frame (line, hole, out of FRONT): FRONT toward the lid, a rotation."""
    s.placed_by("PAD3U board frame -> box -> cage.to_lid",
                r3d.jacobian(lambda x, y, z: cage.to_lid(x - bx0, z + st.BP_BACK, y + bz0)))


def box_drawing(s):
    """Pictures drawn in (Xb, Zb, Yb): the real box, through the lid-centre frame."""
    s.placed_by("enclosure 2: lid-centre frame -> box -> (Xb, Zb, Yb)", r3d.jacobian(lambda *p: vp(from_lid(*p))))
