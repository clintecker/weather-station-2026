"""Per underside wire (OD 1.45): closest used hole (not its own ends) and unused holes it lies over."""
import sys
sys.dont_write_bytecode = True
import numpy as np
import scenes2 as S
rt = S.rt
used = {tuple(np.round(h, 2)) for h in rt.used_holes("B4")}
names = [f"{c.lower()}{n}" for c in "ABCDEFGHIJ" for n in range(1, 31)] + \
        [f"F+{n}" for n in range(1, 31)] + [f"F-{n}" for n in range(1, 31)]
holes = {h: np.array(S.hole_xy(h)) for h in names}
print("used holes:", len(used))
order = ["f1", "f2", "i12", "h24", "a10", "a20", "h25", "a9", "a19", "d8", "d18", "d7", "d17"]


def dseg(p, a, b):
    ab = b - a
    t = np.clip((p - a) @ ab / (ab @ ab), 0, 1) if ab @ ab > 0 else 0
    return np.linalg.norm(p - (a + t * ab))


for n, a in enumerate(order, 1):
    w = next(w for w in S.UNDER if w["a"] == f"B4:{a}")
    pts = [np.array(p[:2]) for p in w["pts"]]
    pa, pb = pts[0], pts[-1]
    near_used, over_unused = [], []
    for h, p in holes.items():
        if np.linalg.norm(p - pa) < 0.1 or np.linalg.norm(p - pb) < 0.1:
            continue
        d = min(dseg(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        isused = tuple(np.round(p, 2)) in used
        if isused and d < 1.6:
            near_used.append(f"{h}:{d:.2f}")
        elif not isused and d < 1.225:
            over_unused.append(h)
    print(n, w["a"], w["b"], "| near used (<1.6):", " ".join(near_used) or "-", "| over unused:", " ".join(over_unused) or "-")
