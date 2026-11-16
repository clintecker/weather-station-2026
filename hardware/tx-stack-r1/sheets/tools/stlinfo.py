import sys, numpy as np, struct
p=sys.argv[1]; b=open(p,'rb').read()
if b[:5]==b'solid' and b'facet' in b[:300]:
    v=np.array([list(map(float,l.split()[1:])) for l in b.decode().splitlines() if l.strip().startswith('vertex')])
else:
    n=struct.unpack('<I',b[80:84])[0]; a=np.frombuffer(b[84:84+n*50],dtype=np.dtype([('n','<3f4'),('v','<9f4'),('a','<u2')]))
    v=a['v'].reshape(-1,3)
print(len(v)//3,'tris'); print('min',v.min(0).round(2),'max',v.max(0).round(2))
np.save('verts.npy',v.astype(np.float32))
