"""Export the UV crown (our own CAD only: no shield, no cap remix) as one mesh blob for the three.js page index.html.
Run with the CAD venv (sheets/env.sh's CADPY): python -B export_crown.py OUTDIR   (publish.sh does this)
Format: crown.json {meshes:[{name, group, color, nv, nt, off}], ...} + crown.txt = base64(float32 verts | uint32 faces, per mesh)."""
import base64, json, sys
from pathlib import Path
import numpy as np
import cadquery as cq
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sheets"))   # scenes_q sets the rest

import scenes_q as SQ
import models_q as Q
import podbox as PB

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
d = SQ.d_("UV")
cx, cy = d["axis"]

# the pod inside: board, crown body, glands, board screws, plug in J1, the UV lead (Session Q's bib scene, no shield)
s = SQ.bib_scene("UV")
inside = [p[0] for p in s.parts]
# the radial O-ring on the spigot
s.add("oring", Q.cord_in_groove("UV"), Q.CORD, 0.8)
# the dome lid, locked (smooth, not banded), its window disc in the recess
s.add("lid", PB.lid("UV"), Q.PETG, 1.0)
_m, wd, wt = Q.S.val("uv_window")
s.add("window", Q.window_disc().translate(cq.Vector(cx, cy, d["z_flat"] - d["window"]["depth"])), "#F7F7F5", 1.0)
n0 = len(s.parts)
SQ.ltr_in_lid(s)                                   # LTR390 on its bosses, 2 x M2.5 x 6, lead cores + jacket
ltr = [p[0] for p in s.parts[n0:]]
# one cable, board to LTR390: drop the straight stub that rises from the board's gather point and join it to the
# LTR390's jacket end with a slack loop round the drum (drawn only with the lid on: the page hides it when exploded)
stub = next(p for p in s.parts if p[0] == "L_jacket")
lj = next(p for p in s.parts if p[0] == "ltr_jacket")
s.parts = [p for p in s.parts if p[0] != "L_jacket"]
bs, bl = cq.Shape.cast(stub[1]).BoundingBox(), cq.Shape.cast(lj[1]).BoundingBox()
a = np.array((bs.center.x, bs.center.y, bs.zmin))            # the board's gather point
b = np.array((bl.center.x, bl.center.y, bl.zmin))            # the LTR390 jacket's lower end
r = 0.62 * d["r_in"]
th0 = np.arctan2(a[1] - cy, a[0] - cx)
loop = [(cx + r * np.cos(th0 + k * 0.5), cy + r * np.sin(th0 + k * 0.5), z) for k, z in ((1, 14.0), (2, 22.0), (3, 30.0), (4, 38.0))]
pts = [tuple(a), tuple(a + (0, 0, 6.0)), *loop, tuple(b - (0, 0, 6.0)), tuple(b)]
# drawn by the page (it follows the lid when the crown comes apart): send its path, not a mesh
cable = dict(pts=[[float(q[0] - cx), float(q[1] - cy), float(q[2])] for q in pts], r=2.0, color=stub[2],
             follow=[0.0, 0.0, 0.25, 0.5, 0.7, 0.85, 1.0, 1.0])            # how far each point moves with the lid
assert len(cable["follow"]) == len(pts)
# floor inserts and the four M3 x 10 up through the cap's flat top (cap not drawn)
for k, (x, y) in enumerate(d["floor_bosses"]):
    s.add(f"fins{k}", Q.insert_m3().translate(cq.Vector(x, y, d["z_bo"])), Q.BRASS, 0.8)
    s.add(f"fscrew{k}", SQ.mount_screw(np.array((0, 0, 1.0)), np.array((x, y, d["z_bo"] - 3.0))), Q.STEEL, 0.8)


def group(name):
    if name == "oring":
        return "oring"
    if name == "window":
        return "window"                                # lifts out of its recess when the crown comes apart
    if name == "lid" or name in ltr:
        return "lid"
    if name.startswith("fscrew"):
        return "screws"
    if name.endswith("_body") or name.startswith("fins") or name.startswith("gl"):
        return "body"
    return "pod"                                      # the board, its parts, the plug and lead


metas, blob, off = [], bytearray(), 0
for name, shp, col, _w in s.parts:
    shape = shp if isinstance(shp, cq.Shape) else cq.Shape.cast(shp)
    vs, fs = shape.tessellate(0.08 if name in ("lid", "uv_body", "oring") else 0.15, 0.25)
    if not fs:
        continue
    v = np.array([(p.x - cx, p.y - cy, p.z) for p in vs], np.float32)   # crown axis at the origin
    f = np.array(fs, np.uint32)
    metas.append(dict(name=name, group=group(name), color=col, nv=len(v), nt=len(f), off=off))
    blob += v.tobytes() + f.tobytes()
    off += v.nbytes + f.nbytes

info = dict(meshes=metas, cable=cable, r_out=d["r_out"], z_bo=d["z_bo"], z_joint=d["z_joint"], apex=d["apex"],
            turn=PB.CROWN_TURN, slots=PB._bayonet_angles(d))
(out / "crown.json").write_text(json.dumps(info))
(out / "crown.txt").write_text(base64.b64encode(bytes(blob)).decode())
for g in ("body", "oring", "lid", "window", "screws", "pod"):
    print(g, sum(m["nt"] for m in metas if m["group"] == g), [m["name"] for m in metas if m["group"] == g][:12])
print("bytes", off)
