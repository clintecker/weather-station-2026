"""Draw a dimensioned top-side assembly reference in millimeters."""
from pathlib import Path
import html

ROOT=Path(__file__).resolve().parents[1]
# SVG uses board coordinates directly, with margins for dimensions and notes.
parts=['''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="-7 -10 66 66">
<rect x="-7" y="-10" width="66" height="66" fill="white"/>
<style>text{font-family:Arial,sans-serif;fill:#14332d} .label{font-size:1.05px} .small{font-size:.85px}</style>
<text x="25" y="-7" text-anchor="middle" font-size="1.8">Chicago Stage 0 • R0 • top assembly</text>
<rect x="0" y="0" width="50" height="35" rx=".1" fill="#e3f2e9" stroke="#183c33" stroke-width=".2"/>
''']

def label(s,x,y,size=1,anchor='middle'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}">{html.escape(s)}</text>')

def route(points):
    parts.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+'" fill="none" stroke="#ae8355" stroke-width=".5"/>')

route([(8,12),(12,8),(23.73,8)])
route([(26.27,8),(38,8),(42,12)])
for y in [14.54,17.08,19.62]: route([(8,y),(42,y)])
for x,y in [(4,4),(46,4),(4,31),(46,31)]:
    parts.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="white" stroke="#183c33" stroke-width=".15"/>')
for x in (8,42):
    parts.append(f'<rect x="{x-1.27}" y="10.73" width="2.54" height="10.16" fill="none" stroke="#183c33" stroke-width=".15"/>')
    for i,y in enumerate([12,14.54,17.08,19.62]):
        if i==0:
            parts.append(f'<rect x="{x-1}" y="{y-1}" width="2" height="2" fill="#d8b36c"/>')
        else:
            parts.append(f'<circle cx="{x}" cy="{y}" r="1" fill="#d8b36c"/>')
        parts.append(f'<circle cx="{x}" cy="{y}" r=".51" fill="white"/>')
        label(str(i+1),x+(-2.6 if x==8 else 2.6),y+.3,.9)
label('J1 / HOST',8,8.8,1.2)
label('J2 / SENSOR',42,8.8,1.2)
for x in [23.73,26.27]:
    parts.append(f'<rect x="{x-1}" y="7" width="2" height="2" fill="#d8b36c"/><circle cx="{x}" cy="8" r=".51" fill="white"/>')
parts.append('<rect x="22.46" y="6.73" width="5.08" height="2.54" fill="none" stroke="#183c33" stroke-width=".2"/>')
label('JP1 + REMOVABLE SHUNT',25,5,1)
for i,(x,y) in enumerate([(35,8),(25,14.54),(25,17.08),(25,19.62)],1):
    parts.append(f'<circle cx="{x}" cy="{y}" r=".75" fill="#d8b36c"/>')
    label('TP'+str(i),x if i==1 else x+2.4,y+2.2 if i==1 else y+.35,.85)
for y,t in zip([12,14.54,17.08,19.62],['1  3V3','2  GND','3  SDA','4  SCL']):
    label(t,16,y+.35,.9)
label('3.3 V ONLY • NO BATTERY INPUT',25,25,1.3)
label('All three headers on top; square pad = pin 1',25,28,1)
# Dimension arrows are deliberately separate from the component legend.
parts.append('<path d="M0 36V39 M50 36V39 M0 38H50 M-1 0H-4 M-1 35H-4 M-3 0V35" fill="none" stroke="#183c33" stroke-width=".12"/>')
label('50.00 mm',25,40,1.3)
parts.append('<text transform="translate(-4 17.5) rotate(-90)" font-size="1.3" text-anchor="middle">35.00 mm</text>')
label('4 x Ø3.20 NPTH • hole-center rectangle 42.00 x 27.00 mm',25,43,1)
label('10 x Ø1.02 PTH • 2.54 mm header pitch • PCB 1.6 mm',25,45,1)
label('J1/J2: Samtec TSW-104-07-G-S',25,48,1)
label('JP1: TSW-102-07-G-S + SNT-100-BK-G shunt',25,50,1)
label('Prototype drawing — verify actual assembly before power',25,53,1)
parts.append('</svg>')
(ROOT/'manufacturing'/'assembly-top.svg').write_text(''.join(parts))
