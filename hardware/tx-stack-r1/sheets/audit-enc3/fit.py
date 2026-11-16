import sys; sys.path.insert(0,'.')
import numpy as np
import sl
from vox import mask2
R='/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1'
sys.path.insert(0,R+'/cage'); sys.path.insert(0,R+'/layout')
import cage as C, stack as st, layout_checks as lc
S=st.S
items=[]
def add(name,b,kind): items.append((name,(b.x0,b.x1,b.y0,b.y1,b.z0,b.z1),kind))
for b in st.BOARDS:
    add(f'{b} card slab',lc.card_slab(b),'card')
    for ref,x in lc.board_boxes(b):
        bb=lc.to_box(b,x)
        add(bb.what,bb,'service' if x.service else ('keepout' if x.keepout else 'part'))
    sock=st.Box(st.X(1)-1.27,st.Y_MOUTH,st.X(model_len:=30)+1.27,st.Y_BP,0.0,2*st.PIN_Z,'socket body')
    add(f'{b} backplane socket body (1x30)',lc.to_box(b,sock),'bp')
    z=st.bp_xy(f's1.{st.SOCKET_HOLE[b]}')[1]
    items.append((f'{b} socket solder tails behind backplane',(st.strip_x(1)-0.5,st.strip_x(30)+0.5,st.BP_BACK-S.val('socket_tail'),st.BP_BACK,z-0.5,z+0.5),'bp'))
x0,z0,x1,z1=st.BP_OUTLINE
items.append(('backplane PAD3U slab (seated)',(x0,x1,st.BP_BACK,st.BP_FRONT,z0,z1),'bp'))
m=C.mux_box(); items.append(('PCA9548 mux on foam',(m.x0,m.x1,m.y0,m.y1,m.z0,m.z1),'bp'))
for ref,pins,note in st.BP_PARTS:
    if ref.startswith('W') or ref=='XJ1':
        for pin,h in pins.items():
            x,z=st.bp_xy(h); hh=S.val('qt_lead_h') if ref.startswith('W') else 8.5
            items.append((f'{ref} {pin} housing',(x-1.27,x+1.27,st.BP_FRONT,st.BP_FRONT+hh,z-1.27,z+1.27),'bp'))
    elif ref in ('R7','R8'):
        (xa,za),(xb,zb)=(st.bp_xy(h) for h in pins.values())
        items.append((f'{ref} lying on backplane',(min(xa,xb)-1.25,max(xa,xb)+1.25,st.BP_FRONT,st.BP_FRONT+2.6,min(za,zb)-1.25,max(za,zb)+1.25),'bp'))
hd,hk=S.val('m3_button')
for (hx,hz),w in zip(C.BP_POSTS,C.BP_POST_WHAT):
    items.append((f'M3 button head, {w}',(hx-hd/2,hx+hd/2,st.BP_FRONT,st.BP_FRONT+hk,hz-hd/2,hz+hd/2),'cyl'))
MARG=2.0
def clearance(bx,r,marg=MARG,cyl=False):
    x0,x1,y0,y1,z0,z1=bx
    X0,X1,Y0,Y1,Z0,Z1=x0-marg,x1+marg,y0-marg,y1+marg,z0-marg,z1+marg
    # quick reject
    t=(sl.TMAX[:,0]>X0)&(sl.TMIN[:,0]<X1)&(sl.TMAX[:,1]>Y0)&(sl.TMIN[:,1]<Y1)&(sl.TMAX[:,2]>Z0)&(sl.TMIN[:,2]<Z1)
    xs=np.arange(X0,X1,r)+r/2+0.00137; ys=np.arange(Y0,Y1,r)+r/2+0.00171; zs=np.arange(Z0,Z1,r)+r/2+0.00113
    best=(9e9,None)
    if not t.any():
        # region could be entirely inside solid: test centre
        pass
    for z in zs:
        M=mask2(2,z,xs,ys,scan_u=len(xs)<len(ys))
        if not M.any(): continue
        I,J=np.nonzero(M); px,py=xs[I],ys[J]
        if cyl:
            cx,cz=(x0+x1)/2,(z0+z1)/2; rr=(x1-x0)/2
            dr=np.maximum(0,np.hypot(px-cx,z-cz)-rr); dy=np.maximum(0,np.maximum(y0-py,py-y1))
            d=np.hypot(dr,dy)
        else:
            dx=np.maximum(0,np.maximum(x0-px,px-x1)); dy=np.maximum(0,np.maximum(y0-py,py-y1)); dz=max(0,z0-z,z-z1)
            d=np.sqrt(dx*dx+dy*dy+dz*dz)
        k=d.argmin()
        if d[k]<best[0]: best=(d[k],(px[k],py[k],z))
        if best[0]==0 and not cyl: pass
    return best
if __name__=='__main__':
    res=[]
    for name,bx,kind in items:
        d,p=clearance(bx,0.1,cyl=(kind=='cyl'))
        if d<0.8:
            d2,p2=clearance(bx,0.025,marg=0.9,cyl=(kind=='cyl'))
            if d2<9e8: d,p=d2,p2
        res.append((d,name,kind,bx,p))
    res.sort(key=lambda r:r[0])
    with open('fit_results.txt','w') as f:
        for d,name,kind,bx,p in res:
            s=f'{("%.2f"%d) if d<9e8 else ">%.1f"%MARG:>6}  {kind:8s} {name:70s} box Xb {bx[0]:.2f}-{bx[1]:.2f} Yb {bx[2]:.2f}-{bx[3]:.2f} Zb {bx[4]:.2f}-{bx[5]:.2f}' + (f'  nearest solid at ({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})' if p else '')
            print(s); f.write(s+'\n')
