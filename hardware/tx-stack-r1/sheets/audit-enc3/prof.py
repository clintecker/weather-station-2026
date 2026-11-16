import sys; sys.path.insert(0,'.')
from sl import *
def pts(axis,c,u0,u1,v0,v1):
    a,b=segs(axis,c)
    P=np.r_[a,b]
    m=(P[:,0]>=u0)&(P[:,0]<=u1)&(P[:,1]>=v0)&(P[:,1]<=v1)
    Q=np.unique(np.round(P[m],3),axis=0)
    return Q
if __name__=='__main__':
    for zb in (59.0,65.0,73.5,85.0,100.0,120.0,150.0):
        print('Zb',zb,'left groove window (Xb,Yb):',[tuple(p) for p in pts(2,zb+0.0013,4,12,5,16)])
    for zb in (73.0,75.0,85.0,105.0,125.0,145.0,150.5):
        print('Zb',zb,'right slot window (Xb,Yb):',[tuple(p) for p in pts(2,zb+0.0013,83,98,5,25)])
