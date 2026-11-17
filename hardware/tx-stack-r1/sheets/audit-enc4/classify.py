"""Sort the voxel diff's blobs (diff.py output) into the explained groups; anything else prints UNEXPLAINED."""
import re, sys
cat = {}
side = None
for ln in open(sys.argv[1]):
    if ln.startswith('---'):
        side = 'enc4 only' if 'in enc4, not' in ln else 'model only'; continue
    m = re.findall(r'-?\d+\.\d+', ln)
    if len(m) < 7: continue
    v, x0, x1, y0, y1, z0, z1 = map(float, m)
    if x1 < -1.5: k = 'left outside face, 1 mm deep'
    elif x0 > 125: k = 'right outside face, 1 mm deep'
    elif z0 > 171: k = 'top outside face, 1 mm deep'
    elif z1 < -1.5: k = 'bottom outside face, 1 mm deep'
    elif 21 < z0 < 25 and 50 < y0 < 59: k = 'fix 1 (tray to Yb 62, lip from 56)'
    elif z1 < 8.5 and x0 > 85 and x1 < 111: k = 'fix 2 (PG-9 holes, 24 mm cuts)'
    else: k = 'UNEXPLAINED'
    c = cat.setdefault((side, k), [0, 0]); c[0] += 1; c[1] += v
for (s, k), (n, v) in sorted(cat.items()):
    print(f'{s:11s} {k:36s} {n:3d} blobs {v:8.1f} mm3')
