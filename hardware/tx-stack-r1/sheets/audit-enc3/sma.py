import sys; sys.path.insert(0,'.')
from sl import *
from vox import mask2
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,3,figsize=(21,7))
for k,xb in enumerate((121.5,122.9,126.3)):
    us=np.arange(60,120,0.05)+.0037; vs=np.arange(120,170,0.05)+.0041
    M=mask2(0,xb+.0013,us,vs)
    ax[k].imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys'); ax[k].set_title(f'section Xb {xb} (Yb right, Zb up); red: Ø14 nut seat, blue: Ø14+2 mm')
    ax[k].add_patch(plt.Circle((86,144.6),7,fill=False,color='r')); ax[k].add_patch(plt.Circle((86,144.6),9,fill=False,color='b',ls='--')); ax[k].grid(alpha=.3)
plt.tight_layout(); plt.savefig('sma_wall.png',dpi=60)
# recess diameter and distance from Ø14 seat to nearest material inside (Xb 118-122.25 region)
for xb in (122.9,):
    for ang in range(0,360,45):
        a=np.radians(ang)
        for rr in np.arange(3.3,12,0.02):
            y,z=86+rr*np.cos(a),144.6+rr*np.sin(a)
            xr=ray(0,{1:y+.0013,2:z+.0017},110,127)
            if len(xr) and xr[0]<123.4: break
        print('recess edge dir',ang,'r=%.2f'%rr, 'inner wall face Xb',xr[:2])
# nearest material inside the box (Xb < 122.25) to the nut seat disc (Ø14, Xb 120.25..122.25)
best=9e9;bp=None
for xb in np.arange(110,122.2,0.1):
    us=np.arange(70,102,0.1)+.0037; vs=np.arange(128,162,0.1)+.0041
    M=mask2(0,xb+.0013,us,vs); I,J=np.nonzero(M)
    if not len(I): continue
    dr=np.maximum(0,np.hypot(us[I]-86,vs[J]-144.6)-7); dx=max(0,120.25-xb)
    d=np.hypot(dr,dx); k=d.argmin()
    if d[k]<best: best=d[k]; bp=(xb,us[I[k]],vs[J[k]])
print('nearest material to the inside Ø14 x 2 nut zone (Xb 120.25-122.25):',round(best,2),bp)
