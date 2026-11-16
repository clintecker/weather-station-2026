import sys; sys.path.insert(0,'.')
from sl import *
from vox import mask2
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
spec=[('G1',26,25,12),('G4',98,25,15.5),('G6',50,60,12),('V1',50,85,12.5)]
fig,ax=plt.subplots(1,5,figsize=(25,5))
for k,(n,x,y,d) in enumerate(spec):
    r=0.01; us=np.arange(x-d/2-1.5,x+d/2+1.5,r)+0.0037; vs=np.arange(y-d/2-1.5,y+d/2+1.5,r)+0.0041
    M=mask2(2,-1.5013,us,vs)
    U,Vv=np.meshgrid(us,vs,indexing='ij')
    hole=(~M)&(np.hypot(U-x,Vv-y)<d/2+1.4)
    A=hole.sum()*r*r; deq=2*np.sqrt(A/np.pi)
    cx,cy=U[hole].mean(),Vv[hole].mean()
    # extents
    print(f'{n}: area-equiv Ø{deq:.3f} (spec {d}), centroid ({cx:.3f},{cy:.3f}), Xb {U[hole].min():.3f}-{U[hole].max():.3f} (width {U[hole].max()-U[hole].min():.3f}), Yb {Vv[hole].min():.3f}-{Vv[hole].max():.3f} (height {Vv[hole].max()-Vv[hole].min():.3f})')
    ax[k].imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys'); ax[k].set_title(f'{n} section Zb -1.5 (Xb right, Yb up)')
    ax[k].add_patch(plt.Circle((x,y),d/2,fill=False,color='r'))
# SMA
r=0.01; us=np.arange(86-5,86+5,r)+0.0037; vs=np.arange(144.6-5,144.6+5,r)+0.0041
M=mask2(0,125.0013,us,vs); U,Vv=np.meshgrid(us,vs,indexing='ij')
hole=(~M)&(np.hypot(U-86,Vv-144.6)<4.5)
A=hole.sum()*r*r; print(f'SMA: area-equiv Ø{2*np.sqrt(A/np.pi):.3f}, centroid Yb {U[hole].mean():.3f} Zb {Vv[hole].mean():.3f}, Yb {U[hole].min():.3f}-{U[hole].max():.3f}, Zb {Vv[hole].min():.3f}-{Vv[hole].max():.3f}')
ax[4].imshow(M.T,origin='lower',extent=(us[0],us[-1],vs[0],vs[-1]),cmap='Greys'); ax[4].set_title('SMA section Xb 125 (Yb right, Zb up)')
ax[4].add_patch(plt.Circle((86,144.6),3.25,fill=False,color='r'))
plt.tight_layout(); plt.savefig('holes.png',dpi=60)
