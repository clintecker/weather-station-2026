import sys; sys.path.insert(0,'.')
from sl import *
G=[('G1',26,25,12,19),('G2',50,25,12,19),('G3',74,25,12,19),('G4',98,25,15.5,24),('G5',26,60,12,19),('G6',50,60,12,19),('G7',74,60,12,19),('G8',98,60,15.5,24),('V1',50,85,12.5,16)]
for n,x,y,d,seat in G:
    out=[]
    for ang in (0,90,180,270):
        ca,sa=np.cos(np.radians(ang)),np.sin(np.radians(ang))
        rin=None
        for rr in np.arange(d/2+0.2,d/2+12,0.05):
            px,py=x+rr*ca,y+rr*sa
            if py<0.3 or px<1.4 or px>122.1: break
            z=ray(2,{0:px+.0011,1:py+.0013},-5,30)
            if len(z)>=2 and abs(z[1]-1.0)<0.01: rin=rr; break
        out.append(None if rin is None else round(2*rin,2))
    # outside face: is it flat at -3 across seat?
    zs=[ray(2,{0:x+(seat/2-0.3)*np.cos(a)+.0011,1:y+(seat/2-0.3)*np.sin(a)+.0013},-6,0.5)[0] for a in np.radians([0,90,180,270])]
    print(f'{n}: inside 3.0-thick seat recess Ø (along +Xb,+Yb,-Xb,-Yb dirs): {out}  spec seat Ø{seat}; outside face Zb at seat edge {np.round(zs,2)}')
# keep-out cylinders: material inside Ø nut up to Zb 8.0 (above the 0 face)
for n,x,y,d,seat in G:
    nut=seat
    hit=[]
    for rr in np.arange(0,nut/2,0.25):
        for a in np.radians(np.arange(0,360,5)):
            px,py=x+rr*np.cos(a),y+rr*np.sin(a)
            z=ray(2,{0:px+.0011,1:py+.0013},-5,8.0)
            z=z[z>0.01]
            if len(z): hit.append((round(px,2),round(py,2),round(float(z.min()),2)))
    print(n,'keep-out Ø',nut,'to Zb 8: material hits',len(hit), hit[:6])
