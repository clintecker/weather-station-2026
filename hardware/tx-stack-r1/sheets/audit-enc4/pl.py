import numpy as np, sys
from load import load
_v=load(sys.argv[1] if len(sys.argv)>1 and sys.argv[1].endswith('.stl') else '/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/692bc986-c73f-47d7-a8f2-60ffe3bf60e8/scratchpad/dl-enc4/enc4.stl')
T=np.stack([61.75-_v[...,1], _v[...,2]-3.0, _v[...,0]+84.75],-1)
def plane(axis,c,u0,u1,v0,v1,r=0.05):
    o=[a for a in range(3) if a!=axis]; t=T[(T[:,:,axis].min(1)<c)&(T[:,:,axis].max(1)>c)]
    d=t[...,axis]-c; P=[];C=[]
    for i,j in ((0,1),(1,2),(2,0)):
        di,dj=d[:,i],d[:,j]; cr=(di*dj)<0; f=np.where(cr,di/(di-dj+1e-300),0)
        p=t[:,i]+(t[:,j]-t[:,i])*f[:,None]; P.append(p[:,o]); C.append(cr)
    cr=np.stack(C,1); pts=np.stack(P,1); ok=cr.sum(1)==2; cr,pts=cr[ok],pts[ok]
    idx=np.argsort(~cr,axis=1,kind='stable')[:,:2]
    a=pts[np.arange(len(pts)),idx[:,0]]; b=pts[np.arange(len(pts)),idx[:,1]]
    us=np.arange(u0+r/2,u1,r)+0.00137; vs=np.arange(v0+r/2,v1,r)+0.00137
    M=np.zeros((len(us),len(vs)),bool); lo=np.minimum(a[:,0],b[:,0]); hi=np.maximum(a[:,0],b[:,0])
    for i,q in enumerate(us):
        s=(lo<q)&(hi>q)
        if not s.any(): continue
        A,B=a[s],b[s]; y=np.sort(A[:,1]+(B[:,1]-A[:,1])*(q-A[:,0])/(B[:,0]-A[:,0])); M[i]=np.searchsorted(y,vs)%2==1
    return M,us,vs
def runs(line,vals):
    """solid intervals along a 1-D line"""
    out=[];on=None
    for k,s in enumerate(line):
        if s and on is None: on=k
        if not s and on is not None: out.append((round(vals[on]-0.025,2),round(vals[k-1]+0.025,2))); on=None
    if on is not None: out.append((round(vals[on]-0.025,2),round(vals[-1]+0.025,2)))
    return out
def holes(M,us,vs,minpx=20):
    from scipy import ndimage as nd
    L,n=nd.label(~M); res=[]
    for i,s in enumerate(nd.find_objects(L)):
        m=L[s]==i+1
        if s[0].start==0 or s[1].start==0 or s[0].stop==M.shape[0] or s[1].stop==M.shape[1] or m.sum()<minpx: continue
        uu,vv=np.nonzero(m); cu=us[s[0]][uu].mean(); cv=vs[s[1]][vv].mean(); A=m.sum()*(us[1]-us[0])**2
        res.append((round(cu,2),round(cv,2),round(2*np.sqrt(A/np.pi),2),round(us[s[0]][-1]-us[s[0]][0]+0.05,2),round(vs[s[1]][-1]-vs[s[1]][0]+0.05,2)))
    return res
