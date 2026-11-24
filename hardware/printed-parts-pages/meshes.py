"""Meshes for the printed-parts pages that aren't committed STLs. build.py runs this as a subprocess, one mode per
process, because hardware/tx-stack-r1 and hardware/pods-r1 both have a module called `sources`.

  .venv-cad/bin/python -B meshes.py tx OUTDIR       our own TX CAD (cage.py), in the hung frame
  .venv-cad/bin/python -B meshes.py shield OUTDIR   the shield (assemble.py, remix.py) and the pod boxes on it

Each mode writes binary STLs plus OUTDIR/<mode>.json (one entry per mesh: file, frame, explode direction, numbers).

Frames:
- tx, the hung frame: cage.py's box frame through cage.true_frame() (the real hand), then turned so Zb is up and the
  lid faces -Y. X = Xb - the mounting flanges' centre, Y = -3 - Yb (so Y 0 is the back face, the face on the pole),
  Z = Zb. The pole runs along Z behind the back face, at +Y.
- shield, assemble.py's shield frame: Z up, the louver plates' axis on Z, Z 0 on the arm's pocket floor. The pole runs
  behind the arm's upright, at -Y (remix.py). The pod boxes go in by remix.box_pose().

The shield mode reads the 3MF, whose licence is unknown: everything it writes is shield-derived and goes only into
the gitignored out/ folder and onto restricted pages (build.py RESTRICTED).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HW = HERE.parent


def write_stl(path, v, f, header=b"printed-parts-pages"):
    v = np.asarray(v, np.float64)
    f = np.asarray(f, np.int64)
    p = v[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, p
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b" ")[:80])
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(rec.tobytes())


def cq_mesh(shape, tol=0.05, ang=0.2):
    s = shape.val() if hasattr(shape, "val") else shape
    vs, ts = s.tessellate(tol, ang)
    return np.array([(p.x, p.y, p.z) for p in vs]), np.array(ts, np.int64)


def stats(v, f, vol=None):
    v = np.asarray(v)
    d = dict(lo=v.min(0).round(2).tolist(), hi=v.max(0).round(2).tolist(), tris=int(len(f)))
    if vol is not None:
        d["cm3"] = round(vol / 1000, 2)
    return d


# ---------------------------------------------------------------- tx
def tx(out):
    sys.path.insert(0, str(HW / "tx-stack-r1/cage"))
    import cadquery as cq
    import cage
    S = cage.S
    fx0, fx1 = S.val("mount_flange")[:2]
    XC = (fx0 + fx1) / 2

    def hung(real):
        """A real-hand shape (X = Xb, Y = Zb, Z = Yb) into the hung frame."""
        return real.rotate((0, 0, 0), (1, 0, 0), 90).translate((-XC, -cage.T, 0))

    def box_solid(p):
        b = p.boxes[0]
        s = cq.Workplane("XY").box(b.x1 - b.x0, b.y1 - b.y0, b.z1 - b.z0, centered=False).translate((b.x0, b.y0, b.z0))
        return p.solid(s)

    entries = []

    def put(key, shape, **kw):
        v, f = cq_mesh(shape)
        write_stl(out / f"{key}.stl", v, f)
        vol = shape.val().Volume()
        entries.append(dict(key=key, file=f"{key}.stl", frame="hung", **stats(v, f, vol), **kw))
        print(f"  tx {key}: {len(f)} triangles, {vol / 1000:.2f} cm3")

    base = cage.shell_solid()
    for name, s in cage.solids():
        if name != "retention bar":
            base = base.union(s)
    put("tx-base", hung(cage.true_frame(base)), explode=[0, 0, 0])
    bar = next(p for p in cage.parts() if p.name == "retention bar")
    put("tx-bar", hung(cage.true_frame(box_solid(bar))), explode=[0, -1, 0])
    clips = cage.true_frame(cage.clip_solid(0)).union(cage.true_frame(cage.clip_solid(1)))
    put("tx-clips", hung(clips), explode=[0, -1, 0])
    put("tx-shade", hung(cage.shade_solid()), explode=[0, -1, 0])
    # the #905 lid is bought, not printed, and cage.py only knows its outline: a plain 2 mm shell of it, for context
    x0, z0, x1, z1 = cage.LID_BOX
    r = cage.LID_R

    def rr(a, b, c, d, rad, za, zb):
        return (cq.Workplane("XY").workplane(offset=za).center((a + c) / 2, (b + d) / 2).rect(c - a, d - b)
                .extrude(zb - za).edges("|Z").fillet(rad))
    lid = rr(x0, z0, x1, z1, r, cage.SEAM, cage.LID_TOP).cut(rr(x0 + 2, z0 + 2, x1 - 2, z1 - 2, r - 1, cage.SEAM - 1,
                                                                  cage.LID_TOP - 2))
    put("tx-lid-outline", hung(lid), explode=[0, -1, 0])
    info = dict(meshes=entries, gate=cage.stl_gate(), flange_x=[fx0 - XC, fx1 - XC],
                flange_z=[-cage.T - S.val("mount_flange")[2], cage.H + cage.T + S.val("mount_flange")[2]],
                back_y=0.0, lid_top_y=-(cage.LID_TOP + cage.T), seam_y=-(cage.SEAM + cage.T),
                top_wall_z=cage.H + cage.T)
    (out / "tx.json").write_text(json.dumps(info, indent=1))


# ---------------------------------------------------------------- shield
def shield(out):
    pods = HW / "pods-r1"
    for p in (pods / "shield", pods / "box", pods):
        sys.path.insert(0, str(p))
    import sources as S
    if not S.shield_path().exists():
        raise SystemExit(f"the shield 3MF isn't at {S.shield_path()}: can't build the shield pages")
    import assemble as A
    import remix as X
    import podbox as P

    entries = []
    asm = A.assembled()
    pl = A.placements()

    def put(key, v, f, label=None, vol=None, **kw):
        write_stl(out / f"{key}.stl", v, f, b"shield-derived: restricted pages only, never git")
        entries.append(dict(key=key, file=f"{key}.stl", frame="shield", **stats(v, f, vol), **kw))
        print(f"  shield {key}: {len(f)} triangles")

    cap, arm = X.cap_remixed(), X.arm_remixed()
    put("shield-cap", *X.arrays(cap), vol=cap.volume(), explode=[0, 0, 160])
    put("shield-arm", *X.arrays(arm), vol=arm.volume(), explode=[0, 0, 0])
    put("shield-cup", *asm[A.CUP], vol=X.original(A.CUP).volume(), explode=[0, 0, 15])
    put("shield-stand", *asm[A.STAND], vol=X.original(A.STAND).volume(), explode=[0, 0, 35])
    v1, f1 = asm[f"{A.PLATE}.1"]
    inst = [(np.asarray(pl[f"{A.PLATE}.{k}"]) - np.asarray(pl[f"{A.PLATE}.1"])).round(4).tolist()
            for k in range(1, A.PITCH_PLATES + 1)]
    put("shield-plate", v1, f1, vol=X.original(f"{A.PLATE}.1").volume(), instances=inst,
        instance_explode=[[0, 0, 50 + 14 * k] for k in range(A.PITCH_PLATES)], explode=[0, 0, 0])
    # print poses, as remix.py writes them, for the downloads
    X._write_stl(cap, out / "cap_remixed.stl", X.CAP_PRINT_UP)
    X._write_stl(arm, out / "arm_remixed.stl", X.ARM_PRINT_UP)
    poses = {}
    for n in ("cap_remixed", "arm_remixed"):
        import struct
        b = (out / f"{n}.stl").read_bytes()
        k = struct.unpack("<I", b[80:84])[0]
        rec = np.frombuffer(b[84:84 + 50 * k], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        vv = rec["v"].reshape(-1, 3)
        poses[n] = dict(size=(vv.max(0) - vv.min(0)).round(2).tolist(), tris=int(k))

    # the pod boxes on the shield: our CAD, placed by remix.box_pose (shield frame)
    for name in ("TH", "BARO", "UV"):
        R, t = X.box_pose(name)
        for part, solid in (("body", P.body(name)), ("lid", P.lid(name))):
            v, f = cq_mesh(solid, 0.03, 0.15)
            w = v @ R.T + t
            if name == "UV":
                ex = [0, 0, 200] if part == "body" else [0, 0, 270]
            else:
                nz = R @ np.array([0, 0, 1.0])          # the lid's side, outward from the arm
                ex = (nz * (45 if part == "body" else 85)).round(3).tolist()
            put(f"pod-{name.lower()}-{part}", w, f, vol=(solid.val() if hasattr(solid, "val") else solid).Volume(), explode=ex)

    slots, y_back, y_front = X.clamp_slots()
    lo_all = min(min(e["lo"][2] for e in entries), 0)
    info = dict(meshes=entries, poses=poses, upright_back_y=float(y_back), lowest_z=float(lo_all),
                clamp_slots=[list(map(float, s)) for s in slots], cap_top_z=float(X.uv_mount()["top_z"]),
                checks=X.remix_checks())
    (out / "shield.json").write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    mode, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    {"tx": tx, "shield": shield}[mode](outdir)
