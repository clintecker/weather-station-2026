import sys; sys.path.insert(0,'.')
from sl import *
def mask2(axis,c,us,vs,scan_u=True):
    """occupancy at grid us x vs in plane axis=c (u,v = other axes in order); scanlines iterate over u if scan_u"""
    a,b=segs(axis,c)
    M=np.zeros((len(us),len(vs)),bool)
    if scan_u:  # iterate u, crossings along v
        k_it,k_al,it,al=0,1,us,vs
    else:
        k_it,k_al,it,al=1,0,vs,us
    ai,bi=a[:,k_it],b[:,k_it]
    for j,q in enumerate(it):
        s=(np.minimum(ai,bi)<q)&(np.maximum(ai,bi)>q)
        if not s.any(): continue
        A,B=a[s],b[s]
        x=A[:,k_al]+(B[:,k_al]-A[:,k_al])*(q-A[:,k_it])/(B[:,k_it]-A[:,k_it])
        x=np.sort(x); cnt=np.searchsorted(x,al)%2==1
        if scan_u: M[j,:]=cnt
        else: M[:,j]=cnt
    return M
if __name__=='__main__':
    r=0.2; off=0.0137
    xs=np.arange(0,100,r)+r/2+off; ys=np.arange(0,66,r)+r/2+off; zs=np.arange(45,156,r)+r/2+off
    V=np.zeros((len(xs),len(ys),len(zs)),bool)
    for k,z in enumerate(zs):
        V[:,:,k]=mask2(2,z,xs,ys,scan_u=True)
    np.savez_compressed('vox.npz',V=V,xs=xs,ys=ys,zs=zs)
    print('done',V.sum())
