"""Which card holes does each underside wire (OD 1.45) lie over, apart from its own two end holes?"""
import sys
sys.dont_write_bytecode = True
import numpy as np
import scenes2 as S

names = [f"{c.lower()}{n}" for c in "ABCDEFGHIJ" for n in range(1, 31)] + \
        [f"F+{n}" for n in range(1, 31)] + [f"F-{n}" for n in range(1, 31)]
holes = {h: np.array(S.hole_xy(h)) for h in names}
order = ["f1", "f2", "i12", "h24", "a10", "a20", "h25", "a9", "a19", "d8", "d18", "d7", "d17"]


def dseg(p, a, b):
    ab = b - a
    t = np.clip((p - a) @ ab / (ab @ ab), 0, 1) if ab @ ab > 0 else 0
    return np.linalg.norm(p - (a + t * ab))


for n, a in enumerate(order, 1):
    w = next(w for w in S.UNDER if w["a"] == f"B4:{a}")
    pts = [np.array(p[:2]) for p in w["pts"]]
    ends = {w["a"].split(":")[1].lower(), w["b"].split(":")[1] if isinstance(w["b"], str) else ""}
    pa, pb = pts[0], pts[-1]
    hit = []
    for h, p in holes.items():
        if np.linalg.norm(p - pa) < 0.1 or np.linalg.norm(p - pb) < 0.1:
            continue
        d = min(dseg(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        if d < 0.725 + 0.5:          # wire radius + hole radius (1.0 mm hole)
            hit.append(h.upper() if h[0] != "F" else h)
    print(n, w["a"], w["b"], "covers:", " ".join(hit) or "-")
