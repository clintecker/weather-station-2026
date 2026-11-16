import sys; sys.path.insert(0,'.')
from sl import *
def insc(axis,c,x,y,d,lo=None):
    a,b=segs(axis,c); 
    # sample boundary segments densely
    t=np.linspace(0,1,20)[:,None,None]
    P=(a[None]+(b-a)[None]*t).reshape(-1,2)
    P=P[np.hypot(P[:,0]-x,P[:,1]-y)<d/2+3]
    best=(0,None)
    for cx in np.arange(x-0.3,x+0.3001,0.01):
        for cy in np.arange(y-0.3,y+0.3001,0.01):
            r=np.hypot(P[:,0]-cx,P[:,1]-cy).min()
            if r>best[0]: best=(r,(cx,cy))
    return 2*best[0],best[1], np.hypot(P[:,0]-x,P[:,1]-y)
for n,x,y,d in [('G1',26,25,12),('G2',50,25,12),('G3',74,25,12),('G4',98,25,15.5),('G5',26,60,12),('G6',50,60,12),('G7',74,60,12),('G8',98,60,15.5),('V1',50,85,12.5)]:
    D,(cx,cy),rr=insc(2,-1.5013,x,y,d)
    lowh=rr  # vertex radii
    print(f'{n}: inscribed Ø{D:.3f} at ({cx:.2f},{cy:.2f}); spec Ø{d} centre ({x},{y}); dØ {D-d:+.3f}')
D,(cx,cy),rr=insc(0,125.0013,86,144.6,6.5)
print(f'SMA: inscribed Ø{D:.3f} at Yb {cx:.2f} Zb {cy:.2f}; spec Ø6.5 at (86.0,144.6); dØ {D-6.5:+.3f}')
