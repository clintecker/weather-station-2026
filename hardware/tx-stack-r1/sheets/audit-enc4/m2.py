import sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[1:]
from pl import *
def line(axis,fix,lo,hi,r=0.05):
    # fix: dict of the other two coords; sample via thin plane
    o=[a for a in range(3) if a!=axis]
    # slice perpendicular to o[0] at fix[o[0]]
    p=o[0]; q=[a for a in range(3) if a!=p]
    if q[0]==axis:
        M,us,vs=plane(p,fix[p],lo,hi,fix[o[1]]-0.025,fix[o[1]]+0.025,r); return runs(M[:,0],us)
    M,us,vs=plane(p,fix[p],fix[o[1]]-0.025,fix[o[1]]+0.025,lo,hi,r); return runs(M[0,:],vs)
X,Y,Z=0,1,2
Q=[('tray Zb  @Xb45 Yb20',Z,{X:45,Y:20},5,60),('tray Yb @Xb45 Zb23.5',Y,{X:45,Z:23.5},-4,120),('tray lip Zb @Xb45 Yb56',Z,{X:45,Y:56},5,60),
('tray Xb @Zb23.5 Yb20',X,{Y:20,Z:23.5},-4,128),('tray Xb @Zb23.5 Yb54',X,{Y:54,Z:23.5},-4,128),('lip Xb @Zb28 Yb55',X,{Y:55,Z:28},-4,128),
('left block Zb @Xb5 Yb30',Z,{X:5,Y:30},-4,80),('left block Yb @Xb5 Zb20',Y,{X:5,Z:20},-4,120),('left Xb @Zb20 Yb30',X,{Y:30,Z:20},-4,60),
('fin Xb @Zb35 Yb50',X,{Y:50,Z:35},60,128),('fin Zb @Xb98.5 Yb50',Z,{X:98.5,Y:50},-4,80),('fin Yb @Xb98.5 Zb35',Y,{X:98.5,Z:35},-4,120),('fin Zb @Xb98.5 Yb100',Z,{X:98.5,Y:100},-4,80),
('Lledge Xb @Zb46 Yb30',X,{Y:30,Z:46},-4,60),('Lledge Xb @Zb46 Yb60',X,{Y:60,Z:46},-4,60),('Lledge Xb @Zb46 Yb90',X,{Y:90,Z:46},-4,60),('Lledge Zb @Xb5 Yb50',Z,{X:5,Y:50},20,80),('Lledge Zb @Xb3 Yb50',Z,{X:3,Y:50},20,80),('Lledge Yb @Xb5 Zb46',Y,{X:5,Z:46},-4,120),('Lledge Yb @Xb3 Zb42',Y,{X:3,Z:42},-4,120),
('Rblock Xb @Zb44 Yb105',X,{Y:105,Z:44},60,128),('Rblock Yb @Xb110 Zb44',Y,{X:110,Z:44},-4,120),('Rblock Zb @Xb110 Yb105',Z,{X:110,Y:105},20,80),('Rblock Yb @Xb100 Zb44',Y,{X:100,Z:44},-4,120),
('BRwall Xb @Zb3 Yb30',X,{Y:30,Z:3},60,128),('BRwall Zb @Xb108.5 Yb30',Z,{X:108.5,Y:30},-4,40),('BRwall Yb @Xb108.5 Zb3',Y,{X:108.5,Z:3},-4,120),('floor-raise Zb @Xb95 Yb30',Z,{X:95,Y:30},-4,20),('floor-raise Xb @Zb0.5 Yb30',X,{Y:30,Z:0.5},-4,128),('floor-raise Yb @Xb95 Zb0.5',Y,{X:95,Z:0.5},-4,120),
('groove Zb @Xb7 Yb9',Z,{X:7,Y:9},20,172),('rail Zb @Xb3 Yb12',Z,{X:3,Y:12},20,172),('rslot Zb @Xb89 Yb9',Z,{X:89,Y:9},20,172),('corner post Zb @Xb93 Yb5',Z,{X:93,Y:5},20,172),
('flange bottom Zb @Xb60 Yb-1',Z,{X:60,Y:-1.5},-40,0),('flange Yb @Xb60 Zb-20',Y,{X:60,Z:-20},-6,20),('flange Xb @Zb-20 Yb-1.5',X,{Y:-1.5,Z:-20},-6,128),('flange Xb @Zb-10 Yb-1.5',X,{Y:-1.5,Z:-10},-6,128),('flange top Zb @Xb60 Yb-1.5',Z,{X:60,Y:-1.5},170,210),('flange Xb @Zb190 Yb-1.5',X,{Y:-1.5,Z:190},-6,128),
('pads @Yb4 Xb58 Zb',Z,{X:58.4,Y:4},40,150),
]
for n,a,f,lo,hi in Q: print(f'{n:32s}',line(a,f,lo,hi))
for zb in (40,44,46,48):
    M,us,vs=plane(2,zb,-1,124,-1,118,0.1); print('holes Zb',zb,[h for h in holes(M,us,vs) if h[2]<12])
M,us,vs=plane(1,-1.5,-6,128,-40,0,0.1); print('flange holes bottom',holes(M,us,vs))
M,us,vs=plane(1,-1.5,-6,128,170,210,0.1); print('flange holes top',holes(M,us,vs))
