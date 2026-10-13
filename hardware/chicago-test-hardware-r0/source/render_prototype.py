"""Render actual fixture meshes with clearly simplified purchased electronics.

Uses deterministic CAD triangles, not generated imagery. Purchased component
shapes are illustrative envelopes, not manufacturer-certified mechanical models.
"""
from pathlib import Path
import struct
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image, ImageDraw, ImageFont
import cadquery as cq

ROOT=Path('/workspace/scratch/f7a2ec9e9ecc/chicago-test-hardware-r0')
OUT=Path(__file__).resolve().parent
COLORS={'plastic':'#d8dfe3','green':'#08674f','black':'#232831','gold':'#dcb974','metal':'#a8afb9','blue':'#096aa3'}


def mesh_stl(path):
    data=Path(path).read_bytes();n=struct.unpack_from('<I',data,80)[0]
    return np.array([np.array(struct.unpack_from('<12fH',data,84+50*i)[3:12]).reshape(3,3) for i in range(n)])


def mesh_cq(shape):
    vertices,triangles=shape.tessellate(.08)
    xyz=np.array([[v.x,v.y,v.z] for v in vertices])
    return xyz[np.array(triangles)]


def cube(x,y,z,dx,dy,dz):
    return mesh_cq(cq.Workplane('XY').box(dx,dy,dz,centered=False).translate((x,y,z)).val())


def cylinder(x,y,z,r,h):
    return mesh_cq(cq.Workplane('XY').center(x,y).circle(r).extrude(h).translate((0,0,z)).val())


def add(ax,triangles,color,shift=(0,0,0)):
    triangles=triangles+np.array(shift)
    n=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);norm=np.linalg.norm(n,axis=1)
    n=n/np.maximum(norm[:,None],1e-12)
    light=np.array([-.4,-.6,1]);light/=np.linalg.norm(light)
    brightness=.63+.37*np.abs(n@light)
    rgb=np.array(matplotlib.colors.to_rgb(color))
    face=brightness[:,None]*rgb[None,:]
    ax._render_triangles.append(triangles)
    ax._render_colors.append(face)


def nucleo(ax):
    add(ax,mesh_stl(ROOT/'mechanical/nucleo-open-cradle.stl'),COLORS['plastic'])
    # ST UM2592 gives the 70 mm width / 64.5 mm maximum PCB height.
    add(ax,cube(-35,-32.25,12,70,64.5,1.6),COLORS['green'])
    for x in (-31,27):
        add(ax,cube(x,-25,13.6,4,50,5),COLORS['black'])
        for y in np.arange(-23,24,2.54):
            add(ax,cube(x+.8,y,18.6,.65,.65,1.6),COLORS['gold'])
            add(ax,cube(x+2.5,y,18.6,.65,.65,1.6),COLORS['gold'])
    for x,y,w,h in [(-14,4,10,10),(9,-12,10,12),(-12,-17,7,5)]:
        add(ax,cube(x,y,13.6,w,h,2),COLORS['black'])
    for x,y in [(-20,-25),(-13,-25),(17,-25)]:
        add(ax,cube(x,y,13.6,4,4,2),COLORS['metal'])
        add(ax,cylinder(x+2,y+2,15.6,1.1,.9),COLORS['blue'])
    # Approximate USB and antenna positions; do not use these to design mating parts.
    add(ax,cube(28,21,13.6,9,7,3),COLORS['metal'])
    add(ax,cylinder(-9,31,14,3,7),COLORS['gold'])
    add(ax,cylinder(-9,31,21,2.3,48),COLORS['black'])
    for x,y in [(-18,-2),(7,8),(13,9),(18,10),(-17,17),(2,-19)]:
        add(ax,cube(x,y,13.6,2,1.2,.8),'#baad92')


def interface(ax):
    add(ax,mesh_stl(ROOT/'mechanical/sensor-interface-base.stl'),COLORS['plastic'])
    shape=cq.importers.importStep(str(ROOT/'mechanical/sensor-interface-bare-pcb.step')).val()
    add(ax,mesh_cq(shape),COLORS['green'],(10,10,9))
    for x in (18,52):
        add(ax,cube(x-1.27,20.73,10.6,2.54,10.16,2.54),COLORS['black'])
        for y in (22,24.54,27.08,29.62):
            add(ax,cube(x-.32,y-.32,13.14,.64,.64,5.84),COLORS['gold'])
    add(ax,cube(32.46,16.73,10.6,5.08,2.54,2.54),COLORS['black'])
    add(ax,cube(32.4,16.6,13.14,5.2,2.8,5.5),'#1c2026')
    for x,y in [(45,18),(35,24.54),(35,27.08),(35,29.62)]:
        add(ax,cylinder(x,y,10.6,.75,.05),COLORS['gold'])
    for x,y in [(14,14),(56,14),(14,41),(56,41)]:
        add(ax,cylinder(x,y,10.6,2.65,1.8),COLORS['metal'])
    # The manufacturing artwork, not this simplified render, governs silkscreen.


def sensor(ax):
    add(ax,mesh_stl(ROOT/'mechanical/sensor-ventilated-tray.stl'),COLORS['plastic'])
    # A recognizable approximate breakout envelope; its detailed layout is not CAD-qualified.
    add(ax,cube(9,9,6,24,19,1.6),COLORS['blue'])
    for x in (10,28):add(ax,cube(x,15,7.6,4,5,3),'#eee9dc')
    add(ax,cube(19.5,17.5,7.6,3,3,1.4),'#c8c8bc')
    add(ax,cylinder(21,19,9,.7,.2),'#252c34')
    for x in (15,18,21,24):add(ax,cylinder(x,11.5,7.6,.8,.1),COLORS['gold'])


def render(name,fn,limits,elev=28,azim=-65):
    fig=plt.figure(figsize=(8.6,5.3),dpi=170,facecolor='#f2f5f6')
    ax=fig.add_axes([0,0,1,1],projection='3d',computed_zorder=True)
    ax._render_triangles=[];ax._render_colors=[]
    ax.set_facecolor('#f2f5f6');fn(ax)
    ax.add_collection3d(Poly3DCollection(np.concatenate(ax._render_triangles),facecolors=np.concatenate(ax._render_colors),edgecolors='none',linewidths=0,zsort='average'))
    ax.set_xlim(*limits[0]);ax.set_ylim(*limits[1]);ax.set_zlim(*limits[2])
    ax.set_box_aspect([b-a for a,b in limits]);ax.view_init(elev=elev,azim=azim);ax.set_proj_type('ortho');ax.set_axis_off()
    fig.savefig(OUT/(name+'.png'),dpi=170);plt.close(fig)

render('nucleo',nucleo,[(-48,48),(-44,44),(0,72)])
render('interface',interface,[(-5,75),(-5,60),(0,38)],elev=38)
render('sensor',sensor,[(-5,47),(-5,43),(0,25)],elev=38)
# Compose a labeled explanatory plate. Typography remains separate from precise geometry.
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def F(n,b=False):return ImageFont.truetype(bold if b else font,n)
canvas=Image.new('RGB',(2000,1610),'#ffffff');d=ImageDraw.Draw(canvas)
d.text((70,42),'WHAT THE FIRST BUILD LOOKS LIKE',font=F(42,True),fill='#163b33')
d.text((70,100),'Chicago bench prototype  •  purchased electronics + our manufactured test parts',font=F(25),fill='#52675f')
cards=[(60,170,'1  TRANSMITTER','nucleo','BUY: NUCLEO-WL55JC1','PRINT: open cradle'),
       (1030,170,'2  SENSOR INTERFACE','interface','MAKE: our 50 × 35 mm PCB','PRINT: matching base'),
       (60,820,'3  TEMPERATURE / HUMIDITY','sensor','BUY: Adafruit SHT45 breakout','PRINT: ventilated tray'),
       (1030,820,'4  RECEIVER','nucleo','BUY: second NUCLEO-WL55JC1','PRINT: second open cradle')]
for x,y,title,img,line1,line2 in cards:
    d.rounded_rectangle((x,y,x+910,y+615),radius=20,fill='#f2f5f6',outline='#d9e1dd',width=2)
    d.text((x+28,y+24),title,font=F(27,True),fill='#173f34')
    image=Image.open(OUT/(img+'.png')).convert('RGB');image.thumbnail((860,460))
    canvas.paste(image,(x+(910-image.width)//2,y+73))
    d.text((x+28,y+532),line1,font=F(25,True),fill='#173f34')
    d.text((x+28,y+569),line2,font=F(23),fill='#4f665d')
d.text((70,1470),'Data path:  3  →  2  →  1   ~ LoRa radio ~   4  →  USB → computer / Home Assistant',font=F(27,True),fill='#173f34')
d.text((70,1523),'Fixture geometry comes from the supplied CAD. Purchased boards, antennas and fasteners are simplified.',font=F(23),fill='#61736c')
d.text((70,1559),'Views are not at a common scale. Cables omitted for clarity. Physical fit and firmware are still to be tested.',font=F(23),fill='#61736c')
canvas.save(OUT/'chicago-prototype-render.png')
print(OUT/'chicago-prototype-render.png')
