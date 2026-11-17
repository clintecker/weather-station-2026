import numpy as np
from scipy import ndimage as nd
a=np.load('enc4tools/v3.npz'); b=np.load('enc4tools/v4.npz')
V3,V4,xs,ys,zs=a['V'],b['V'],a['xs'],a['ys'],a['zs']
for name,D in (('ADDED in enc4',V4&~V3),('REMOVED in enc4',V3&~V4)):
    D=nd.binary_opening(D,iterations=1)
    L,n=nd.label(D); objs=nd.find_objects(L); sz=nd.sum(D,L,range(1,n+1))
    print(f'== {name}: {n} blobs')
    for i in np.argsort(-sz):
        if sz[i]<20: break
        s=objs[i]
        print(f'  {sz[i]*0.125:8.1f} mm3  Xb {xs[s[0].start]-.25:6.1f}..{xs[s[0].stop-1]+.25:6.1f}  Yb {ys[s[1].start]-.25:6.1f}..{ys[s[1].stop-1]+.25:6.1f}  Zb {zs[s[2].start]-.25:6.1f}..{zs[s[2].stop-1]+.25:6.1f}')
