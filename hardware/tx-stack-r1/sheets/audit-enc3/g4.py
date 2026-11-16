import sys; sys.path.insert(0,'.')
from sl import *
from vox import mask2
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,3,figsize=(21,6))
for k,yb in enumerate((25.0,60.0)):
    us=np.arange(80,127,0.05)+.0037; vs=np.arange(-4,22,0.05)+.0041
    M=mask2(1,yb+.0013,us,vs)
    ax[k].imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys'); ax[k].set_title(f'section Yb {yb}: Xb right, Zb up; red = PG-9 nut keep-out Ø24 to Zb 8')
    ax[k].add_patch(plt.Rectangle((98-12,0),24,8,fill=False,color='r')); ax[k].grid(alpha=.3)
us=np.arange(80,124,0.1)+.0037; vs=np.arange(0,97,0.1)+.0041
M=mask2(2,7.8013,us,vs)
ax[2].imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys'); ax[2].set_title('section Zb 7.8: Xb right, Yb up')
for y in (25,60): ax[2].add_patch(plt.Circle((98,y),12,fill=False,color='r'))
plt.tight_layout(); plt.savefig('g4_corner.png',dpi=60)
for yb in (25,60):
  for zb in (7.6,8.0,10,16):
    print('Yb',yb,'Zb',zb,'Xb ray',ray(0,{1:yb+.0013,2:zb+.0017},80,127))
