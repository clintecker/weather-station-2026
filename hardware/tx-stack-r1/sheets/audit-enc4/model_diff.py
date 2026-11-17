import numpy as np, sys
from scipy import ndimage
a=np.load(sys.argv[1]); b=np.load(sys.argv[2])
A,Bm=a['V'],b['V']; xs,ys,zs=a['xs'],a['ys'],a['zs']
r3=0.125
print('enc4 vox',A.sum()*r3,'model',Bm.sum()*r3,'mm3')
for name,M in (('in enc4, not in the model',A&~Bm),('in the model, not in enc4',Bm&~A)):
    # open by one voxel to drop the half-voxel skins on matching faces
    O=ndimage.binary_opening(M,structure=np.ones((2,2,2)))
    L,n=ndimage.label(O)
    out=[]
    for i,sl in enumerate(ndimage.find_objects(L)):
        v=(L[sl]==i+1).sum()*r3
        if v<20: continue
        out.append((v,xs[sl[0]].min()-.25,xs[sl[0]].max()+.25,ys[sl[1]].min()-.25,ys[sl[1]].max()+.25,zs[sl[2]].min()-.25,zs[sl[2]].max()+.25))
    print(f'--- {name}: raw {M.sum()*r3:.0f} mm3, after opening {O.sum()*r3:.0f}; blobs over 20 mm3: {len(out)}')
    for o in sorted(out,reverse=True): print('  %7.1f mm3  Xb %6.2f..%6.2f  Yb %6.2f..%6.2f  Zb %6.2f..%6.2f'%o)
