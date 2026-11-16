import numpy as np
v=np.load('verts.npy').reshape(-1,3,3)
# box frame: Xb=Y+61.75, Zb=X+84.75, Yb=Z-3
T=np.stack([v[...,1]+61.75, v[...,0]+84.75, v[...,2]-3],-1)
# keep triangles whose all verts below Yb 40 and inside walls
m=(T[...,2].max(1)<40)&(T[...,0].min(1)>-0.5)&(T[...,0].max(1)<124)&(T[...,1].min(1)>-0.5)&(T[...,1].max(1)<170)
T=T[m]; r=0.5
H=np.full((int(124/r)+1,int(170/r)+1),-1.0)
# only flat-ish (horizontal) triangles to get top surfaces
n=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]); n/=np.linalg.norm(n,axis=1,keepdims=True)+1e-9
T=T[np.abs(n[:,2])>0.9]
for t in T:
    x0,x1=t[:,0].min(),t[:,0].max(); z0,z1=t[:,1].min(),t[:,1].max(); h=t[:,2].mean()
    # point-in-triangle raster
    xs=np.arange(np.ceil(x0/r),np.floor(x1/r)+1); zs=np.arange(np.ceil(z0/r),np.floor(z1/r)+1)
    if len(xs)==0 or len(zs)==0: continue
    X,Z=np.meshgrid(xs*r,zs*r,indexing='ij')
    a,b,c=t[0,:2],t[1,:2],t[2,:2]
    def s(p,q,X,Z): return (X-q[0])*(p[1]-q[1])-(p[0]-q[0])*(Z-q[1])
    d1,d2,d3=s(a,b,X,Z),s(b,c,X,Z),s(c,a,X,Z)
    ins=~(((d1<0)|(d2<0)|(d3<0))&((d1>0)|(d2>0)|(d3>0)))
    I=(xs[:,None].astype(int)*np.ones_like(zs)[None,:].astype(int))[ins]; J=(np.ones_like(xs)[:,None].astype(int)*zs[None,:].astype(int))[ins]
    H[I,J]=np.maximum(H[I,J],h)
np.save('H.npy',H)
# print coarse map Xb 0..124 step 2, Zb 40..160 step 2, heights rounded
for zb in range(160,38,-3):
    row=''.join(('.' if H[int(xb/r),int(zb/r)]<1 else ('%x'%min(15,int(H[int(xb/r),int(zb/r)]/2)))) for xb in range(0,124,2))
    print('%3d %s'%(zb,row))
print('    '+''.join(str((x//10)%10) if x%10==0 else ' ' for x in range(0,124,2)))
