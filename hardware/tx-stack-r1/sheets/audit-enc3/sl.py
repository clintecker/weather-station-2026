import numpy as np
v=np.load('/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/work3/verts.npy').astype(np.float64).reshape(-1,3,3)
# box frame (mirrored enc3): Xb = 61.75 - Y, Yb = Z - 3, Zb = X + 84.75
T=np.stack([61.75-v[...,1], v[...,2]-3.0, v[...,0]+84.75],-1)
TMIN=T.min(1); TMAX=T.max(1)
def segs(axis,c,T=T):
    m=(TMIN[:,axis]<c)&(TMAX[:,axis]>c)
    t=T[m]; d=t[...,axis]-c
    out=[]
    o=[a for a in range(3) if a!=axis]
    P=[]
    for i,j in ((0,1),(1,2),(2,0)):
        di,dj=d[:,i],d[:,j]
        cr=(di*dj)<0
        f=np.where(cr, di/(di-dj+1e-300),0)
        p=t[:,i]+(t[:,j]-t[:,i])*f[:,None]
        P.append((cr,p[:,o]))
    # each tri: exactly two crossing edges (ignoring vertex-on-plane)
    cr=np.stack([P[k][0] for k in range(3)],1); pts=np.stack([P[k][1] for k in range(3)],1)
    ok=cr.sum(1)==2
    cr,pts=cr[ok],pts[ok]
    idx=np.argsort(~cr,axis=1,kind='stable')[:,:2]
    a=pts[np.arange(len(pts)),idx[:,0]]; b=pts[np.arange(len(pts)),idx[:,1]]
    return a,b   # 2D points in coords (o[0],o[1])
def mask(axis,c,u0,u1,v0,v1,r=0.05):
    """occupancy in plane axis=c; u,v = the two other box axes in increasing order. returns grid [nu,nv], u and v centres"""
    a,b=segs(axis,c)
    us=np.arange(u0+r/2,u1,r); vs=np.arange(v0+r/2,v1,r)
    M=np.zeros((len(us),len(vs)),bool)
    # scanline along u for each v
    av,bv=a[:,1],b[:,1]
    sel=(np.minimum(av,bv)<v1)&(np.maximum(av,bv)>v0)
    a,b=a[sel],b[sel]; av,bv=a[:,1],b[:,1]
    for j,vv in enumerate(vs):
        s=(np.minimum(av,bv)<vv)&(np.maximum(av,bv)>vv)
        if not s.any(): continue
        A,B=a[s],b[s]
        uu=A[:,0]+(B[:,0]-A[:,0])*(vv-A[:,1])/(B[:,1]-A[:,1])
        uu=np.sort(uu)
        # parity: count crossings with u<us
        cnt=np.searchsorted(uu,us)
        M[:,j]=(cnt%2)==1
    return M,us,vs
def runs(line,coords):
    """solid runs along a 1D boolean array -> list of (start,end)"""
    out=[];i=0;n=len(line);r=coords[1]-coords[0]
    while i<n:
        if line[i]:
            j=i
            while j<n and line[j]: j+=1
            out.append((round(coords[i]-r/2,2),round(coords[j-1]+r/2,2))); i=j
        else: i+=1
    return out
def ray(axis,fixed,lo,hi):
    """exact crossings along a line parallel to axis at fixed (dict other axis->value): returns sorted crossing coords"""
    o=[a for a in range(3) if a!=axis]
    # triangles whose projection contains the point
    m=(TMIN[:,o[0]]<=fixed[o[0]])&(TMAX[:,o[0]]>=fixed[o[0]])&(TMIN[:,o[1]]<=fixed[o[1]])&(TMAX[:,o[1]]>=fixed[o[1]])
    t=T[m]
    p=np.array([fixed[o[0]],fixed[o[1]]])
    A=t[:,0][:,o];B=t[:,1][:,o];Cc=t[:,2][:,o]
    def cr(p1,p2): return (p1[:,0]-p[0])*(p2[:,1]-p[1])-(p1[:,1]-p[1])*(p2[:,0]-p[0])
    d1,d2,d3=cr(A,B),cr(B,Cc),cr(Cc,A)
    ins=((d1>=0)&(d2>=0)&(d3>=0))|((d1<=0)&(d2<=0)&(d3<=0))
    t=t[ins]; d1,d2,d3=d1[ins],d2[ins],d3[ins]
    s=d1+d2+d3; ok=np.abs(s)>1e-12
    w0,w1,w2=d2[ok]/s[ok],d3[ok]/s[ok],d1[ok]/s[ok]
    t=t[ok]
    z=w0*t[:,0,axis]+w1*t[:,1,axis]+w2*t[:,2,axis]
    z=np.unique(np.round(z,4))
    return z[(z>=lo)&(z<=hi)]
