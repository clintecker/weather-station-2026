import sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[1:]
from pl import *
for xb in (20,45,85):
    M,us,vs=plane(0,xb,40,60,21,32,0.05)
    print('Xb',xb,'; Zb: tray/lip Yb runs')
    for zb in (24.5,25,26,27,28,29,30,30.3):
        k=int(np.argmin(abs(vs-zb))); print(f'   Zb {zb:5}', runs(M[:,k],us))
