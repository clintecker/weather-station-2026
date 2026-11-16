import sys; sys.path.insert(0,'.')
import numpy as np, sl
from vox import mask2
from fit import items, st, C, lc, S
def pen(bx,r=0.05,shrink=0.03):
    x0,x1,y0,y1,z0,z1=bx; x0+=shrink;x1-=shrink;y0+=shrink;y1-=shrink;z0+=shrink;z1-=shrink
    xs=np.arange(x0,x1,r)+r/2+0.00137; ys=np.arange(y0,y1,r)+r/2+0.00171; zs=np.arange(z0,z1,r)+r/2+0.00113
    n=0; ext=None
    for z in zs:
        M=mask2(2,z,xs,ys,scan_u=len(xs)<len(ys))
        if M.any():
            I,J=np.nonzero(M); n+=len(I)
            e=(xs[I].min(),xs[I].max(),ys[J].min(),ys[J].max(),z,z)
            ext=e if ext is None else (min(ext[0],e[0]),max(ext[1],e[1]),min(ext[2],e[2]),max(ext[3],e[3]),min(ext[4],z),max(ext[5],z))
    return n*r**3, ext
tests=[]
for b in st.BOARDS:
    s=lc.card_slab(b); tests.append((f'{b} card slab in place',(s.x0,s.x1,s.y0,s.y1,s.z0,s.z1)))
    tests.append((f'{b} card slab swept out to Yb 117 (bar off)',(s.x0,s.x1,s.y0,117,s.z0,s.z1)))
    for ref,x in lc.board_boxes(b):
        if x.service or x.keepout: continue
        bb=lc.to_box(b,x)
        tests.append((f'{bb.what} swept out to Yb 117',(bb.x0,bb.x1,bb.y0,117,bb.z0,bb.z1)))
x0,z0,x1,z1=st.BP_OUTLINE
tests.append(('backplane seated',(x0,x1,8.0,9.6,z0,z1)))
ins=C.RSLOT[3]-x1
tests.append((f'backplane pushed {ins:.2f} right to the slot end',(x0+ins,x1+ins,8.0,9.6,z0,z1)))
tests.append(('backplane slide path (union)',(x0,x1+ins,8.0,9.6,z0,z1)))
tests.append(('backplane left part dropping in, outside the slot (Xb shifted left edge..85.8, Yb 8..117)',(x0+ins,85.8,8.0,117,z0,z1)))
tests.append(('backplane right part dropping in where no post (Zb below 72.73)',(85.8,x1+ins,8.0,117,z0,72.73)))
tests.append(('slot mouth (Xb 85.8-92.3, Yb 8-10.1) along the board length in the post',(85.8,92.3,8.0,10.1,72.73,z1)))
for name,bx in tests:
    v,e=pen(bx,r=0.05 if (bx[1]-bx[0])*(bx[3]-bx[2])<2000 else 0.1)
    print(f'{v:9.4f} mm3  {name}' + (f'   material at Xb {e[0]:.2f}-{e[1]:.2f} Yb {e[2]:.2f}-{e[3]:.2f} Zb {e[4]:.2f}-{e[5]:.2f}' if e else ''))
