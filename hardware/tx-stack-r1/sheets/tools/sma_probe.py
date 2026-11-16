import numpy as np
v=np.load('verts.npy').reshape(-1,3)
for sgn in (1,-1):
    m=(np.abs(v[:,1]-sgn*63.25)<1.6)&(np.abs(v[:,0]-59.85)<6)&(np.abs(v[:,2]-89)<6)
    print('wall Y',sgn*61.75,'verts near SMA spot',m.sum(), v[m][:,[0,2]].min(0).round(2) if m.sum() else '', v[m][:,[0,2]].max(0).round(2) if m.sum() else '')
# card block: solid at Y ~ -61.75..-53.25 above Z 40?
for y0,y1,name in ((-61.7,-53.3,'block side Y-'),(53.3,61.7,'Y+ side')):
    m=(v[:,1]>y0)&(v[:,1]<y1)&(v[:,2]>40)&(v[:,2]<97)&(v[:,0]>-12)&(v[:,0]<66)
    print(name,m.sum(), v[m].min(0).round(1) if m.sum() else '', v[m].max(0).round(1) if m.sum() else '')
