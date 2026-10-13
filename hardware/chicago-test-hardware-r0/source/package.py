"""Build the illustrated local guide, manufacturer ZIP and reproducibility manifest."""
from pathlib import Path
import base64
import csv
import hashlib
import html
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def inline(s):
    text=html.escape(s)
    text=re.sub(r'https://[^\s<]+',lambda m:'<a href="'+m[0]+'">'+m[0]+'</a>',text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    return re.sub(r'`([^`]+)`',r'<code>\1</code>',text)


def render_markdown(text):
    """Render only the small Markdown subset used by this package's own docs."""
    lines=text.splitlines(); out=[];i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip(): i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                row=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[:\-]+',c) for c in row): rows.append(row)
                i+=1
            out.append('<div class="table"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>')
            for row in rows[1:]:out.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            out.append('</tbody></table></div>');continue
        h=re.match(r'^(#{1,6}) (.*)$',line)
        if h: out.append(f'<h{len(h[1])}>{inline(h[2])}</h{len(h[1])}>');i+=1;continue
        if re.match(r'^(?:- |\d+\. )',line):
            ordered=bool(re.match(r'^\d+\.',line)); tag='ol' if ordered else 'ul';out.append('<'+tag+'>')
            while i<len(lines) and re.match(r'^(?:- |\d+\. )',lines[i]):
                out.append('<li>'+inline(re.sub(r'^(?:- |\d+\. )','',lines[i]))+'</li>');i+=1
            out.append('</'+tag+'>');continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','- ')):
            paragraph.append(lines[i]);i+=1
        out.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(out)

build=(ROOT/'docs'/'build-and-order.md').read_text()
bench=(ROOT/'docs'/'bench-equipment.md').read_text()
figures=''
for filename,title in [('assembly-top.png','Sensor test PCB — top assembly'),('fixtures.png','Printable bench fixtures')]:
    raw=base64.b64encode((ROOT/'docs'/filename).read_bytes()).decode()
    figures+=f'<figure><img alt="{title}" src="data:image/png;base64,{raw}"/><figcaption>{title}</figcaption></figure>'
style='''body{font:16px/1.6 system-ui,sans-serif;color:#18382e;background:#f2f6f4;margin:0}main{max-width:1100px;margin:auto;padding:30px}section,header{background:white;border:1px solid #ceddd5;border-radius:12px;padding:30px;margin-bottom:24px}h1{font-size:32px;line-height:1.2}h2{margin-top:32px;font-size:23px}a{color:#126b57;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #cbd9d1;padding:10px;text-align:left;vertical-align:top}th{background:#e8f1ec}.table{overflow:auto}code{background:#edf3ef;padding:2px 4px}img{max-width:100%;height:auto}figure{margin:20px 0}figcaption{color:#547267}nav a{display:inline-block;margin:0 20px 8px 0}.figures{display:grid;grid-template-columns:1fr 1fr;gap:25px}@media(max-width:700px){main{padding:10px}section,header{padding:18px}.figures{display:block}}'''
(ROOT/'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chicago weather station — prototype hardware and bench</title><style>'+style+'</style></head><body><main><header><h1>Chicago prototype build kit</h1><p>R0 · 8 October 2026 · Stage 0 bench hardware</p><p>Small-batch fabrication files, editable CAD, print files and an equipment list. Design checks pass; physical first-article tests remain to be performed.</p><nav><a href="#build">Build and order</a><a href="#bench">Bench equipment</a><a href="manufacturing/sensor-interface-gerbers.zip">Gerber ZIP</a><a href="pcb/sensor-interface.kicad_pro">KiCad project</a></nav><div class="figures">'+figures+'</div></header><section id="build">'+render_markdown(build)+'</section><section id="bench">'+render_markdown(bench)+'</section></main></body></html>')
# Export bench tables to one spreadsheet-readable UTF-8 CSV without adding a
# separate spreadsheet analysis or changing the table contents.
with (ROOT/'docs'/'bench-equipment.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['Section','Column1','Column2','Column3','Column4'])
    section=''
    for line in bench.splitlines():
        if line.startswith('## '):section=line[3:]
        elif line.startswith('|'):
            row=[c.strip().replace('**','') for c in line.strip('|').split('|')]
            if not all(re.fullmatch(r'[:\-]+',c) for c in row):w.writerow([section,*row])
# The manufacturer gets only the physical fabrication layers and drill files.
with zipfile.ZipFile(ROOT/'manufacturing'/'sensor-interface-gerbers.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((ROOT/'manufacturing'/'gerbers').iterdir()):
        if p.suffix in {'.gtl','.gbl','.gto','.gbo','.gts','.gbs','.gm1','.drl','.gbrjob'}:z.write(p,p.name)
# Remove the obsolete first schematic preview; the current schematic is in its own folder.
(ROOT/'docs'/'sensor-interface.svg').unlink(missing_ok=True)
manifest=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS.txt' and '__pycache__' not in p.parts:
        manifest.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(ROOT)))
(ROOT/'SHA256SUMS.txt').write_text('\n'.join(manifest)+'\n')
archive=ROOT.with_suffix('.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT.parent))
print(archive)
print('Files:',len(manifest)+1,'ZIP bytes:',archive.stat().st_size)
