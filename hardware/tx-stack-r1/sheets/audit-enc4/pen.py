import sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[1:]
from pl import *
from scipy import ndimage as nd
B={'pack':(18.5,87.5,2.0,56.0,24.41,42.41),'evm under':(8.25,98.25,11.6,101.6,44.41,48.41),'evm above':(6.75,104.25,11.6,101.6,50.01,65.01),
   'evm board':(8.25,98.25,11.6,101.6,48.41,50.01),'bp slab':(6.51,89.46,8.0,9.6,48.71,148.31),'locknut 26,25':(17.7,34.3,16.7,33.3,0,6)}
e=0.06
for n,(x0,x1,y0,y1,z0,z1) in B.items():
    vol=[];where=[]
    for zb in np.arange(z0+e,z1-e+1e-9,0.2):
        M,us,vs=plane(2,zb,x0+e,x1-e,y0+e,y1-e,0.2)
        if M.any():
            vol.append(M.sum()*0.04*0.2); uu,vv=np.nonzero(M); where.append((zb,us[uu].min(),us[uu].max(),vs[vv].min(),vs[vv].max()))
    print(f'{n:14s} overlap {sum(vol):8.1f} mm3', '' if not where else f'Zb {where[0][0]:.2f}..{where[-1][0]:.2f}  Xb {min(w[1] for w in where):.2f}..{max(w[2] for w in where):.2f}  Yb {min(w[3] for w in where):.2f}..{max(w[4] for w in where):.2f}')
