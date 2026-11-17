import numpy as np, sys
def load(p):
    b=open(p,'rb').read()
    if b[:5]==b'solid' and b'facet' in b[:400]:
        import re
        v=np.array(re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)',b),float); return v.reshape(-1,3,3)
    n=np.frombuffer(b,'<u4',1,80)[0]
    d=np.frombuffer(b,np.dtype([('n','<f4',3),('v','<f4',(3,3)),('a','<u2')]),n,84)
    return d['v'].astype(float)
if __name__=='__main__':
    for p in sys.argv[1:]:
        v=load(p); print(p.split('/')[-1],len(v),'min',v.reshape(-1,3).min(0).round(2),'max',v.reshape(-1,3).max(0).round(2))
