import sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[1:]
from pl import *
for zb in (0.5,1.5,3,5,7.9):
    M,us,vs=plane(2,zb,80,122,0,90,0.05)
    for yb in (25,60):
        k=int(np.argmin(abs(vs-yb))); print(f'Zb {zb:4} Yb {yb}: solid Xb runs', runs(M[:,k],us))
    # nearest solid to each PG-9 axis in this plane, outside the wall
    uu,vv=np.nonzero(M)
    for yb in (25,60):
        d=np.hypot(us[uu]-98,vs[vv]-yb); print(f'      nearest solid to axis (98,{yb}) at r={d.min():.2f}')
