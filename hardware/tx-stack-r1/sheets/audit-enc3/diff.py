import sys; sys.path.insert(0,'.')
import numpy as np
R='/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1'
sys.path.insert(0,R+'/cage'); sys.path.insert(0,R+'/layout')
import cage as C, stack as st
d=np.load('vox.npz'); V,xs,ys,zs=d['V'],d['xs'],d['ys'],d['zs']
print('V shape',V.shape,'filled frac',V.mean())
X,Y,Z=np.meshgrid(xs,ys,zs,indexing='ij')
def inb(b): return (X>b.x0)&(X<b.x1)&(Y>b.y0)&(Y<b.y1)&(Z>b.z0)&(Z<b.z1)
Mo=np.zeros(V.shape,bool)
for p in C.parts():
    if p.name in ('retention bar','charger ledges','pack tray'): continue
    if p.name in ('backplane posts','backplane support pads'):
        for i,b in enumerate(p.boxes):
            cx,cz=(b.x0+b.x1)/2,(b.z0+b.z1)/2
            if b.what=='backplane post':
                cx=[7.78,86.63][i]; rr=[4.0,3.5][i]
            else: rr=3.0
            m=(np.hypot(X-cx,Z-cz)<rr)&(Y<8.0)
            if b.what=='backplane post':
                m&=~((np.hypot(X-cx,Z-cz)<2.0)&(Y>1.5))
                if i==0: m&=X<cx+3.5
            Mo|=m
        continue
    m=np.zeros(V.shape,bool)
    for b in p.boxes: m|=inb(b)
    for c in p.cuts: m&=~inb(c)
    if p.name=='left wall':
        x0,y0,z0,x1,y1,z1=C.GROOVE
        m&=~((X>x0)&(X<x1+0.01)&(Y>y1-0.001)&(Y<y1+(X-x0))&(Z>z0)&(Z<z1))
        for zc in C.BAR_INS[1:3]:
            m&=~((np.hypot(X-C.BAR_INS[0],Z-zc)<2.0)&(Y>C.CARD_FRONT+1-6.5))
    if p.name=='right corner post':
        x0,y0,z0,x1,y1,z1=C.RSLOT
        m&=~((X>x0-0.01)&(X<x1)&(Y>y1-0.001)&(Y<y1+(x1-X))&(Z>z0)&(Z<z1))
    Mo|=m
# shell as measured (walls 1.25 / 1.0 thick inside the spec frame) and corner blocks, kept out of the diff
shell=(X<1.25)|(Z<1.0)|(Z>168.5)|((X<16.5)&(Z>153.1))|((X<16.5)&(Z<16.4))
D1=V&~Mo&~shell   # in STL, not in model
D2=Mo&~V&~shell   # in model, not in STL
print('STL-only cells',D1.sum(),' model-only cells',D2.sum())
def report(D,name):
    idx=np.argwhere(D)
    if not len(idx): return
    # crude clustering by 2mm bins
    import collections
    b=collections.defaultdict(list)
    for i,j,k in idx: b[(int(xs[i]//4),int(ys[j]//4),int(zs[k]//4))].append((xs[i],ys[j],zs[k]))
    for key,v in sorted(b.items(), key=lambda kv:-len(kv[1]))[:40]:
        v=np.array(v); print(' ',name,len(v),'cells; Xb %.2f-%.2f Yb %.2f-%.2f Zb %.2f-%.2f'%(v[:,0].min(),v[:,0].max(),v[:,1].min(),v[:,1].max(),v[:,2].min(),v[:,2].max()))
report(D1,'STL-only'); report(D2,'model-only')
np.savez_compressed('diffs.npz',D1=D1,D2=D2)
