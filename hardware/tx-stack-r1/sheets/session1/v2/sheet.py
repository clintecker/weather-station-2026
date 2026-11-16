"""Contact sheet of SVGs (pdfenv): python sheet.py out.png dpi a.svg b.svg ..."""
import subprocess, sys
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
out, dpi, files = sys.argv[1], sys.argv[2], sys.argv[3:]
ds = [svg2rlg(f) for f in files]
cols = 3 if len(ds) > 4 else 2 if len(ds) > 1 else 1
cw = max(d.width for d in ds) + 10
rh = []
for i in range(0, len(ds), cols):
    rh.append(max(d.height for d in ds[i:i+cols]) + 10)
W, H = cw * cols, sum(rh)
c = canvas.Canvas(out[:-4] + ".pdf", pagesize=(W, H))
y = H
for r in range(len(rh)):
    y -= rh[r]
    for k, d in enumerate(ds[r*cols:(r+1)*cols]):
        c.setStrokeColorRGB(.8, .8, .8); c.rect(k*cw+2, y+2, d.width+6, d.height+6)
        renderPDF.draw(d, c, k*cw+5, y+5)
c.save()
subprocess.run(["pdftoppm", "-r", dpi, "-png", "-singlefile", out[:-4] + ".pdf", out[:-4]], check=True)
