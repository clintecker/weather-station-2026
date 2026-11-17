import numpy as np, sys
sys.path.insert(0, sys.argv[3])
from load import load
v=load(sys.argv[1])
T=np.stack([61.75-v[...,1], v[...,2]-3.0, v[...,0]+84.75],-1)   # enc3 box frame: Xb, Yb, Zb
TMIN=T.min(1); TMAX=T.max(1)
r=0.5; off=0.0137
xs=np.arange(-6,128,r)+r/2+off; ys=np.arange(-4,121,r)+r/2+off; zs=np.arange(-34,206,r)+r/2+off
V=np.zeros((len(xs),len(ys),len(zs)),bool)
for k,c in enumerate(zs):
    m=(TMIN[:,2]<c)&(TMAX[:,2]>c); t=T[m]; d=t[...,2]-c
    P=[];C=[]
    for i,j in ((0,1),(1,2),(2,0)):
        di,dj=d[:,i],d[:,j]; cr=(di*dj)<0; f=np.where(cr,di/(di-dj+1e-300),0)
        P.append(t[:,i,:2]+(t[:,j,:2]-t[:,i,:2])*f[:,None]); C.append(cr)
    cr=np.stack(C,1); pts=np.stack(P,1); ok=cr.sum(1)==2; cr,pts=cr[ok],pts[ok]
    idx=np.argsort(~cr,axis=1,kind='stable')[:,:2]
    a=pts[np.arange(len(pts)),idx[:,0]]; b=pts[np.arange(len(pts)),idx[:,1]]
    lo=np.minimum(a[:,0],b[:,0]); hi=np.maximum(a[:,0],b[:,0])
    for i,q in enumerate(xs):
        s=(lo<q)&(hi>q)
        if not s.any(): continue
        A,B=a[s],b[s]; y=np.sort(A[:,1]+(B[:,1]-A[:,1])*(q-A[:,0])/(B[:,0]-A[:,0]))
        V[i,:,k]=np.searchsorted(y,ys)%2==1
np.savez_compressed(sys.argv[2],V=V,xs=xs,ys=ys,zs=zs); print(sys.argv[2],V.sum())
