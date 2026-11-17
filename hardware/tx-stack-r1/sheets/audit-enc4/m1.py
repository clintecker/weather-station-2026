import sys; sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[1:]
from pl import *
for name,stl in (('enc3','/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/stl-enc3/enc3.stl'),('enc4',None)):
    if stl:
        import pl; v=load(stl); pl.T=np.stack([61.75-v[...,1], v[...,2]-3.0, v[...,0]+84.75],-1); g=pl
    else:
        import importlib, pl; v=load('/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/692bc986-c73f-47d7-a8f2-60ffe3bf60e8/scratchpad/dl-enc4/enc4.stl'); pl.T=np.stack([61.75-v[...,1], v[...,2]-3.0, v[...,0]+84.75],-1)
    print('=====',name)
    for zb in (-2.9,-1.5,-0.1):
        M,us,vs=pl.plane(2,zb,-1,124,-1,118,0.1); print(' bottom wall Zb',zb,'holes (Xb,Yb,eqD,w,h):',holes(M,us,vs))
    for xb in (121.2,122.5,124.2,126.0):
        M,us,vs=pl.plane(0,xb,-1,118,-1,172,0.1); print(' right wall Xb',xb,'holes (Yb,Zb,eqD,w,h):',holes(M,us,vs))
