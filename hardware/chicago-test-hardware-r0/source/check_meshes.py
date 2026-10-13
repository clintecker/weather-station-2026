"""Check exported binary STL edge closure, consistent orientation and volume."""
from pathlib import Path
from collections import Counter
import struct
import json

ROOT=Path(__file__).resolve().parents[1]
results=[]
for path in sorted((ROOT/'mechanical').glob('*.stl')):
    data=path.read_bytes()
    count=struct.unpack_from('<I',data,80)[0]
    assert len(data)==84+50*count, path
    edges=Counter(); directed=Counter(); volume=0
    for i in range(count):
        raw=struct.unpack_from('<12fH',data,84+50*i)
        vertices=[tuple(round(v,5) for v in raw[start:start+3]) for start in (3,6,9)]
        assert len(set(vertices))==3, (path,'degenerate triangle')
        a,b,c=vertices
        volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
        for v,w in zip(vertices,vertices[1:]+vertices[:1]):
            edges[tuple(sorted((v,w)))]+=1
            directed[(v,w)]+=1
    assert all(n==2 for n in edges.values()), (path,'open/nonmanifold edge')
    assert all(directed[(w,v)]==n for (v,w),n in directed.items()), (path,'inconsistent winding')
    assert volume>0,(path,'nonpositive volume')
    results.append(dict(file=path.name,triangles=count,closed_edges=True,consistent_winding=True,volume_mm3=volume))
(ROOT/'validation'/'mesh.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
