import sys; sys.path.insert(0,'.')
from sl import *
spec=[('BL screw Ø8 flat',7.78,54.06,8.0),('BR screw Ø7',86.63,54.06,7.0),('sup s20.2',58.58,54.06,6.0),('sup s28.16',78.90,89.62,6.0),('sup s24.31',68.74,127.72,6.0)]
def circfit(x,y):
    A=np.c_[2*x,2*y,np.ones_like(x)]; b=x*x+y*y
    c=np.linalg.lstsq(A,b,rcond=None)[0]; r=np.sqrt(c[2]+c[0]**2+c[1]**2); return c[0],c[1],r
for name,x,z,d in spec:
    print('==',name,'spec',x,z,'Ø',d)
    for yb in (1.5,3.0,5.0,7.0,7.9):
        a,b=segs(1,yb+0.0013)
        P=np.r_[a,b]  # coords (Xb,Zb)
        sel=np.hypot(P[:,0]-x,P[:,1]-z)<d/2+1.5
        Q=P[sel]
        if len(Q)<6: print(' Yb',yb,'no material'); continue
        rr=np.hypot(Q[:,0]-x,Q[:,1]-z)
        outer=Q[rr>2.6]; inner=Q[rr<=2.6]
        cx,cz,r=circfit(outer[:,0],outer[:,1])
        s=f' Yb {yb}: outer centre ({cx:.3f},{cz:.3f}) Ø{2*r:.3f}  Xb range {outer[:,0].min():.3f}-{outer[:,0].max():.3f} Zb {outer[:,1].min():.3f}-{outer[:,1].max():.3f}'
        if len(inner)>5:
            ix,iz,ir=circfit(inner[:,0],inner[:,1]); s+=f' | bore centre ({ix:.3f},{iz:.3f}) Ø{2*ir:.3f}'
        print(s)
    # top: rays along Yb
    for dx,dz in ((0,0),(2.5,0),(-2.5,0),(0,2.5),(0,-2.5)):
        print('  ray Yb at',(round(x+dx,2),round(z+dz,2)),ray(1,{0:x+dx+0.0011,2:z+dz+0.0013},-4,30))
