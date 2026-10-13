"""Generate printable fixtures and editable STEP solids with CadQuery 2.7.

Dimensions are millimeters. These are open indoor bench fixtures, not enclosures.
"""
from pathlib import Path
import json
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'mechanical'
OUT.mkdir(exist_ok=True)
results = []


def box(x, y, z, dx, dy, dz):
    """Create a box located by its minimum corner."""
    return cq.Workplane('XY').box(dx, dy, dz, centered=False).translate((x,y,z))


def hole(shape, x, y, diameter, depth=30):
    """Cut a vertical through hole from below the print bed."""
    cutter = cq.Workplane('XY').center(x,y).circle(diameter/2).extrude(depth).translate((0,0,-1))
    return shape.cut(cutter)


def save(name, shape):
    """Export one solid in CAD and slicer formats and record geometry checks."""
    solid = shape.val()
    assert solid.isValid(), name
    assert len(shape.solids().vals()) == 1, name
    cq.exporters.export(shape, str(OUT / (name+'.step')))
    cq.exporters.export(shape, str(OUT / (name+'.stl')), tolerance=0.05, angularTolerance=0.1)
    bb=solid.BoundingBox()
    results.append(dict(part=name, valid=True, solids=1, volume_mm3=solid.Volume(),
                        bounds_mm=[bb.xlen,bb.ylen,bb.zlen]))


# The PCB uses four M3 holes on a 42 x 27 mm rectangle.
base = box(0,0,0,70,55,3)
for x,y in [(14,14),(56,14),(14,41),(56,41)]:
    base = base.union(cq.Workplane('XY').center(x,y).circle(3.3).extrude(9))
    base = hole(base,x,y,3.4)
for x,y in [(14,14),(56,14),(14,41),(56,41)]:
    pocket=cq.Workplane('XY').center(x,y).polygon(6,7.3).extrude(2.6)
    base=base.cut(pocket)
save('sensor-interface-base', base)

# Nucleo width from ST UM2592 Figure 7: 70 mm. Allow 0.8 mm total clearance.
# Four short edge rests leave underside pins and most edge connectors unobstructed.
# Actual board fit remains a physical check; no undocumented mounting holes assumed.
cradle=box(-42,-40,0,84,80,3)
inner=70.8/2
for side in (-1,1):
    for y in (-15,9):
        if side == -1:
            ledge_x=-inner-2
            wall_x=-inner-2
        else:
            ledge_x=inner-1.2
            wall_x=inner
        cradle=cradle.union(box(ledge_x,y,3,3.2,6,9))
        cradle=cradle.union(box(wall_x,y,3,2,6,11))
# Open ends leave antenna, buttons and cable access. This holder is not retained.
save('nucleo-open-cradle',cradle)

# A single pair of rests is a cheap, fast width/underside-clearance trial print.
coupon=box(-42,-5,0,84,10,3)
for side in (-1,1):
    lx=-inner-2 if side<0 else inner-1.2
    wx=-inner-2 if side<0 else inner
    coupon=coupon.union(box(lx,-3,3,3.2,6,9)).union(box(wx,-3,3,2,6,11))
save('nucleo-fit-coupon',coupon)

# Generic ventilated sensor tray: removable foam dots or loose nylon ties retain
# the breakout. No guessed sensor mounting-hole coordinates are imposed.
tray=box(0,0,3,42,38,3)
for x in (7,19,31):
    tray=tray.cut(box(x,9,-1,4,20,10))
# Feet lift the sensing board and open slots off the bench.
for x in (0,36):
    tray=tray.union(box(x,0,0,6,38,3))
for x in (3,37):
    for y in (5,30):
        tray=tray.cut(box(x,y,-1,2,3,10))
save('sensor-ventilated-tray',tray)
(ROOT/'validation'/'mechanical.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))

# Bare PCB mechanical reference: exact board and hole geometry, no component models.
pcb=box(0,0,0,50,35,1.6)
for x,y in [(4,4),(46,4),(4,31),(46,31)]:
    pcb=hole(pcb,x,y,3.2)
for x in (8,42):
    for y in (12,14.54,17.08,19.62): pcb=hole(pcb,x,y,1.02)
for x in (23.73,26.27): pcb=hole(pcb,x,8,1.02)
cq.exporters.export(pcb,str(OUT/'sensor-interface-bare-pcb.step'))
# Orthographic isometric drawing generated from the actual solids.
shapes=[base.val(),cradle.val().translate((120,40,0)),tray.val().translate((0,80,0)),coupon.val().translate((120,105,0))]
compound=cq.Compound.makeCompound(shapes)
cq.exporters.export(compound,str(ROOT/'docs'/'fixtures.svg'),opt={'width':1100,'height':700,'projectionDir':(1,-1,1.1),'showHidden':False,'strokeWidth':0.5})
