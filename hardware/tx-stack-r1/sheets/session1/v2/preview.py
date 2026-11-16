"""svg -> png preview (pdfenv): python preview.py a.svg [dpi]"""
import subprocess, sys
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
src = sys.argv[1]; dpi = sys.argv[2] if len(sys.argv) > 2 else "150"
d = svg2rlg(src)
renderPDF.drawToFile(d, src[:-4] + ".pdf")
subprocess.run(["pdftoppm", "-r", dpi, "-png", "-singlefile", src[:-4] + ".pdf", src[:-4]], check=True)
