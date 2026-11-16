import sys; sys.path.insert(0,'.')
from sl import *
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig,ax=plt.subplots(2,3,figsize=(24,22))
for k,yb in enumerate((2.0,5.0,9.0,12.0,20.0,40.0)):
    M,us,vs=mask(1,yb+0.013,-4,128,-4,174,0.25)   # u=Xb, v=Zb
    a=ax.flat[k]; a.imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys')
    a.set_title(f'section Yb {yb} (seen from lid: Xb right, Zb up)'); a.set_xticks(range(0,128,10)); a.set_yticks(range(0,174,10)); a.grid(alpha=.3)
plt.tight_layout(); plt.savefig('ov_yb.png',dpi=55)
