import sys; sys.path.insert(0,'.')
from sl import *
r=0.25
ys=[0.1,0.3,0.6,1.0,1.5]+list(np.arange(2,97,1.0))+[96.5]
top=None
for yb in ys:
    M,us,vs=mask(1,yb+0.0017,0,123.5,0,169.5,r)
    if top is None: top=np.full(M.shape,-1.0)
    top[M]=yb
np.save('top.npy',top); np.save('topuv.npy',np.array([us[0],vs[0],r]))
# report components of material outside known features
known=np.zeros(top.shape,bool)
U,V=np.meshgrid(us,vs,indexing='ij')
def boxk(x0,x1,z0,z1): return (U>=x0)&(U<=x1)&(V>=z0)&(V<=z1)
for x,z,d in ((7.78,54.06,8),(86.63,54.06,7),(58.58,54.06,6),(78.9,89.62,6),(68.74,127.72,6)):
    known|=np.hypot(U-x,V-z)<d/2+0.6
known|=boxk(0,9.2,58,151.3)   # card block + rail
known|=boxk(85.1,96.5,72,151.3) # corner post
present=(top>-0.5)&~known
print('cells with material not in known features:',present.sum())
# print by region coarse
idx=np.argwhere(present)
if len(idx):
    import collections
    bins=collections.Counter((int(us[i]//5*5),int(vs[j]//5*5)) for i,j in idx)
    for k,c in sorted(bins.items()): print(k,c, 'maxYb',top[(U>=k[0])&(U<k[0]+5)&(V>=k[1])&(V<k[1]+5)&present].max())
