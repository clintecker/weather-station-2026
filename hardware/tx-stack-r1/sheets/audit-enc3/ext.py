import sys; sys.path.insert(0,'.')
from sl import *
def circfit(x,y):
    A=np.c_[2*x,2*y,np.ones_like(x)]; b=x*x+y*y
    c=np.linalg.lstsq(A,b,rcond=None)[0]; r=np.sqrt(c[2]+c[0]**2+c[1]**2); return c[0],c[1],r
spec=[('G1',26,25,12),('G2',50,25,12),('G3',74,25,12),('G4',98,25,15.5),('G5',26,60,12),('G6',50,60,12),('G7',74,60,12),('G8',98,60,15.5),('V1',50,85,12.5)]
for zb in (-2.9,-1.5,0.5):
    a,b=segs(2,zb+0.0013); P=np.r_[a,b]   # (Xb,Yb)
    print('-- section Zb',zb)
    for n,x,y,d in spec:
        q=P[np.hypot(P[:,0]-x,P[:,1]-y)<d/2+1.0]
        if len(q)<6: print(n,'no edge found'); continue
        cx,cy,r=circfit(q[:,0],q[:,1]); rr=np.hypot(q[:,0]-cx,q[:,1]-cy)
        print(f'{n} spec ({x},{y}) Ø{d}: centre ({cx:.3f},{cy:.3f}) Ø{2*r:.3f} (rmin {rr.min():.3f} rmax {rr.max():.3f}) dXb {cx-x:+.3f} dYb {cy-y:+.3f} dØ {2*r-d:+.3f}')
# any other holes in bottom wall? count crossings along rays through the wall
print('bottom wall thickness at gland centres, ray along Zb just off hole edge:')
for n,x,y,d in spec:
    print(n, 'at hole edge+1.5', ray(2,{0:x+d/2+1.5+.001,1:y+.0013},-5,10), ' +6:', ray(2,{0:x+d/2+6+.001,1:y+.0013},-5,10))
# SMA
for xb in (122.6,124.4,126.2):
    a,b=segs(0,xb+0.0013); P=np.r_[a,b]  # (Yb,Zb)
    q=P[np.hypot(P[:,0]-86,P[:,1]-144.6)<6]
    if len(q)<6: print('SMA section Xb',xb,'no hole'); continue
    cy,cz,r=circfit(q[:,0],q[:,1]); print(f'SMA Xb {xb}: centre Yb {cy:.3f} Zb {cz:.3f} Ø{2*r:.3f} (lid X {cz-84.75:.3f}, Z {cy+3:.3f})')
print('right wall thickness near SMA: Xb rays',ray(0,{1:86.0013,2:144.6+5.5},100,140),ray(0,{1:86.0013,2:144.6+9},100,140), ray(0,{1:86.0013,2:144.6},100,140))
# any hole in the left wall (pre-mirror SMA position)?
for xb in (-1.5,124.4):
    a,b=segs(0,xb+0.0013); P=np.r_[a,b]
    m=(P[:,0]>5)&(P[:,0]<110)&(P[:,1]>5)&(P[:,1]<165)
    print('wall Xb',xb,'interior edge pts (holes/recesses) in wall section:',m.sum(), np.round(P[m].min(0),2) if m.sum() else '', np.round(P[m].max(0),2) if m.sum() else '')
