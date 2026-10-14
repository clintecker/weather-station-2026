"""Proof-of-concept station enclosure parts R1, CadQuery 2.7. Dimensions in millimetres.

Run:  .venv-cad/bin/python hardware/poc-enclosure-r1/source/build.py
Writes STEP + STL for each part to ../parts/ and a geometry summary to ../validation/parts.json.

Every part prints flat on the bed with no supports: shield plates rim-down (each layer smaller than
the one below), posts rising from the bed or from a printed surface, slots vertical.
Parameters that depend on parts not yet in hand are marked MEASURE; check them on arrival.
"""
from math import cos, radians, sin
from pathlib import Path
import json

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'parts'
OUT.mkdir(exist_ok=True)
(ROOT / 'validation').mkdir(exist_ok=True)
results = []

# ---------------------------------------------------------------- shield
PLATE_D = 130.0        # plate outside diameter
PLATE_OPEN_D = 60.0    # central air opening of the louvre plates
PLATE_DROP = 12.0      # rim sits this far below the inner edge (sheds rain outward)
PLATE_T = 2.4          # wall thickness, measured vertically
PITCH = 22.0           # plate-to-plate stacking pitch (≈ 19.6 mm air gap)
ROD_R = 50.0           # radius of the three M4 rods
ROD_HOLE = 4.5         # M4 clearance
POST_D = 10.0
N_LOUVRES = 7          # louvre plates between the cap and the arm

# ---------------------------------------------------------------- sensor (Adafruit 6174, SHT45)
SENSOR_PCB = (25.4, 17.8, 1.6)   # MEASURE: Adafruit 0.7 x 1.0 in STEMMA QT board

# ---------------------------------------------------------------- Nucleo (ST UM2592 Rev 4, Figure 7)
NUCLEO_W, NUCLEO_L, NUCLEO_T = 70.0, 64.5, 1.6
NUCLEO_UNDER = 14.0    # MEASURE: clearance for the underside morpho pins and parts
EDGE_GRIP = 1.5        # rail lip under the board edge; morpho pin centres sit 3.5 mm in

# ---------------------------------------------------------------- box (Adafruit 905) and battery (Adafruit 353)
CHASSIS = (160.0, 110.0, 3.0)    # MEASURE: Adafruit 905 inside floor (outside 175 x 125 x 75)
BATTERY = (69.0, 54.0, 18.0)     # Adafruit 353 3.7 V 6600 mAh pack, from its product page
MAST_D = 33.4                    # MEASURE: 1 in NPS pipe OD; set to your mast


def save(name, shape, note):
    solid = shape.val()
    assert solid.isValid(), name
    assert len(shape.solids().vals()) == 1, f'{name}: {len(shape.solids().vals())} solids'
    cq.exporters.export(shape, str(OUT / f'{name}.step'))
    cq.exporters.export(shape, str(OUT / f'{name}.stl'), tolerance=0.05, angularTolerance=0.1)
    bb = solid.BoundingBox()
    results.append(dict(part=name, note=note, valid=True, solids=1,
                        volume_cm3=round(solid.Volume() / 1000, 1),
                        bounds_mm=[round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)]))


def cone_top(r):
    """Height of a plate's top surface at radius r (rim at z = PLATE_T, inner edge PLATE_DROP higher)."""
    r0, r1 = PLATE_OPEN_D / 2, PLATE_D / 2
    return PLATE_T + PLATE_DROP * (r1 - r) / (r1 - r0)


def rod_points():
    return [(ROD_R * cos(radians(a)), ROD_R * sin(radians(a))) for a in (90, 210, 330)]


def plate(open_d):
    """Conical louvre: a revolved band, rim on the bed, rising towards the centre."""
    r0 = open_d / 2
    r1 = PLATE_D / 2
    top_inner = cone_top(r0)
    # With r0 = 0 (solid cap) the same profile closes on the axis.
    pts = [(r0, top_inner - PLATE_T), (r1, 0), (r1, PLATE_T), (r0, top_inner)]
    band = cq.Workplane('XZ').polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))
    # A short vertical drip lip on the rim (rain falls clear of the plate below).
    lip = (cq.Workplane('XY').circle(r1).circle(r1 - 1.6).extrude(PLATE_T + 1.0))
    body = band.union(lip)
    zr = cone_top(ROD_R)
    for x, y in rod_points():
        foot = cq.Workplane('XY').center(x, y).circle(POST_D / 2).extrude(zr)              # bed → plate
        spacer = (cq.Workplane('XY').workplane(offset=zr - 0.5).center(x, y)
                  .circle(POST_D / 2).extrude(PITCH - zr + 0.5))                         # plate → next foot
        body = body.union(foot).union(spacer)
        body = body.cut(cq.Workplane('XY').center(x, y).circle(ROD_HOLE / 2).extrude(PITCH + 5)
                        .translate((0, 0, -1)))
    return body


# Louvre plate: identical, print N_LOUVRES of them.
save('shield-louvre', plate(PLATE_OPEN_D),
     f'print {N_LOUVRES}; white ASA or PETG; rim down; 3 perimeters, 20 % infill')

# Cap: solid top plate with a central boss (bed → ceiling) carrying the sensor cartridge.
cap = plate(0)
boss_h = cone_top(0) - PLATE_T
cap = cap.union(cq.Workplane('XY').rect(34, 14).extrude(boss_h))
for x in (-11, 11):   # heat-set insert holes for M3 (4.0 mm for common M3 x 5.7 inserts)
    cap = cap.cut(cq.Workplane('XY').center(x, 0).circle(2.0).extrude(boss_h - 1.0).translate((0, 0, -0.01)))
save('shield-cap', cap, 'print 1; rim down; 2 x M3 heat-set inserts in the central boss')

# Sensor cartridge: an L-shaped paddle. The short tab screws up into the cap's central boss; the long
# paddle hangs straight down through the louvre openings and holds the 6174 board edge-on to the air,
# 40-60 mm below the cap. Printed flat (paddle on the bed, tab standing up). The PCB slides into a slot;
# the STEMMA cable runs in a groove up to the tab.
PADDLE_L, PADDLE_W, PADDLE_T = 62.0, 30.0, 5.0
TAB_T = 5.0
paddle = cq.Workplane('XY').box(PADDLE_L, PADDLE_W, PADDLE_T, centered=(False, True, False))
tab = cq.Workplane('XY').box(TAB_T, 34, 14, centered=(False, True, False))
paddle = paddle.union(tab)
for y in (-11, 11):   # M3 clearance through the tab, along the paddle axis (vertical when installed)
    paddle = paddle.cut(cq.Workplane('YZ').workplane(offset=-1).center(y, 7).circle(1.7).extrude(TAB_T + 2))
# PCB window: open frame so both faces of the sensor see moving air.
px, py, pt = SENSOR_PCB
win_x0 = PADDLE_L - px - 4
paddle = paddle.cut(cq.Workplane('XY').box(px - 4, py - 4, PADDLE_T + 2, centered=False)
                    .translate((win_x0 + 2, -(py - 4) / 2, -1)))
# Edge slot for the PCB, 0.3 mm clearance, mid-thickness, open at the paddle's far end.
paddle = paddle.cut(cq.Workplane('XY').box(px + 4.6, py + 0.6, pt + 0.3, centered=False)
                    .translate((win_x0 - 0.3, -(py + 0.6) / 2, (PADDLE_T - pt - 0.3) / 2)))
# Cable groove along the paddle top, from the tab to the window.
paddle = paddle.cut(cq.Workplane('XY').box(win_x0 - TAB_T, 4.5, 2.2, centered=False)
                    .translate((TAB_T, -2.25, PADDLE_T - 2.2)))
save('shield-sensor-cartridge', paddle,
     'print 1; flat; slide the 6174 into the slot, sensor membrane facing the window; 2 x M3 x 8 into the cap')

# Arm: ring on the three rods above the cap, bar to a vertical V-saddle for the mast.
ARM_LEN, ARM_W, ARM_T = 90.0, 28.0, 6.0
ring = cq.Workplane('XY').circle(ROD_R + 8).circle(ROD_R - 8).extrude(ARM_T)
for x, y in rod_points():
    ring = ring.cut(cq.Workplane('XY').center(x, y).circle(ROD_HOLE / 2).extrude(ARM_T + 2).translate((0, 0, -1)))
# The bar is 14 mm tall on edge (a cantilever carrying the shield): a flat 6 mm bar would sag and creep.
bar = cq.Workplane('XY').box(ARM_LEN, 12, 14, centered=(False, True, False)).translate((ROD_R + 4, 0, 0))
# rotate the bar between two rods (rods at 90/210/330 deg → gap centred on 270 deg is not free; use 30 deg)
bar = bar.rotate((0, 0, 0), (0, 0, 1), 30)
saddle_x = ROD_R + 4 + ARM_LEN
block = cq.Workplane('XY').box(30, 44, 46, centered=(False, True, False)).translate((saddle_x - 6, 0, 0))
block = block.cut(cq.Workplane('XY').polyline([(0, 0), (MAST_D * 0.6, MAST_D * 0.75), (MAST_D * 0.6, -MAST_D * 0.75)])
                  .close().extrude(48).translate((saddle_x + 24 - MAST_D * 0.6 + 6, 0, -1)))
for z in (12, 34):   # two slots for stainless hose clamps (up to 14 mm band)
    block = block.cut(cq.Workplane('XY').box(4, 50, 15, centered=(False, True, True)).translate((saddle_x + 4, 0, z)))
block = block.rotate((0, 0, 0), (0, 0, 1), 30)
arm = ring.union(bar).union(block)
save('shield-arm', arm, 'print 1; flat; sits on the cap spacers; two stainless hose clamps to the mast')

# ---------------------------------------------------------------- electronics chassis
cw, cl, ct = CHASSIS
chassis = cq.Workplane('XY').box(cw, cl, ct, centered=False)
chassis = chassis.edges('|Z').fillet(6)
# Nucleo edge rails: two walls with a 1.9 mm slot; the board slides in from the antenna end (+Y side
# open) so the SMA faces the box wall where the bulkhead pigtail goes.
nx0, ny0 = 8.0, cl - NUCLEO_L - 6.0
slot_z = ct + NUCLEO_UNDER
for side in (0, 1):
    wx = nx0 - 3.0 if side == 0 else nx0 + NUCLEO_W
    rail = cq.Workplane('XY').box(3.0, NUCLEO_L - 8, slot_z + NUCLEO_T + 3.0, centered=False).translate((wx, ny0 + 4, 0))
    lip = cq.Workplane('XY').box(EDGE_GRIP + 3.0, NUCLEO_L - 8, 2.0, centered=False)
    lip = lip.translate((wx if side == 0 else wx - EDGE_GRIP, ny0 + 4, slot_z - 2.0))
    top = cq.Workplane('XY').box(EDGE_GRIP + 3.0, NUCLEO_L - 8, 1.6, centered=False)
    top = top.translate((wx if side == 0 else wx - EDGE_GRIP, ny0 + 4, slot_z + NUCLEO_T + 0.3))
    chassis = chassis.union(rail).union(lip).union(top)
# Stop at the closed end (−Y) so the board can't slide past.
chassis = chassis.union(cq.Workplane('XY').box(12, 3, slot_z + 2, centered=False).translate((nx0 + 6, ny0 + 1, 0)))
chassis = chassis.union(cq.Workplane('XY').box(12, 3, slot_z + 2, centered=False).translate((nx0 + NUCLEO_W - 18, ny0 + 1, 0)))
# Battery cradle (Adafruit 353) with two strap slots for a hook-and-loop strap.
bw, bl, bh = BATTERY
bx0, by0 = cw - bw - 10.0, cl - bl - 8.0
outer = cq.Workplane('XY').box(bw + 6, bl + 6, 12, centered=False).translate((bx0 - 3, by0 - 3, 0))
inner = cq.Workplane('XY').box(bw + 1, bl + 1, 13, centered=False).translate((bx0 - 0.5, by0 - 0.5, ct))
chassis = chassis.union(outer).cut(inner)
for y in (by0 + 8, by0 + bl - 30):          # strap passes down beside each long wall, under the floor
    for x in (bx0 - 8.0, bx0 + bw + 4.5):
        chassis = chassis.cut(cq.Workplane('XY').box(3.5, 22, ct + 2, centered=False).translate((x, y, -1)))
# Slotted area for the small boards (charger, regulator, INA228, MAX17048, SHTC3, flash, Qwiic hub):
# 3.2 mm slots fit M2.5/M3 nylon screws or zip ties, so no guessed hole patterns.
for i in range(8):
    x = 12 + i * 18
    if x + 3.2 > cw - 8:
        break
    chassis = chassis.cut(cq.Workplane('XY').box(3.2, 24, ct + 2, centered=False).translate((x, 8, -1)))
# Four corner holes for fixing to the box floor (MEASURE boss positions; slots allow ±4 mm).
for x, y in [(6, 6), (cw - 6, 6), (6, cl - 6), (cw - 6, cl - 6)]:
    chassis = chassis.cut(cq.Workplane('XY').center(x, y).slot2D(12, 4.4).extrude(ct + 2).translate((0, 0, -1)))
save('electronics-chassis', chassis,
     'print 1; flat; Nucleo slides into the rails from the antenna end; battery strapped; small boards on the slots')

# Fit coupon: one rail pair section and a PCB-edge slot sample (print this first, 15 min).
coupon = cq.Workplane('XY').box(NUCLEO_W + 12, 14, 2, centered=False)
for wx in (3.0, 3.0 + 3.0 + NUCLEO_W):
    coupon = coupon.union(cq.Workplane('XY').box(3.0, 14, 2 + 6 + NUCLEO_T + 3.0, centered=False).translate((wx, 0, 0)))
for wx, sgn in ((3.0, 1), (6.0 + NUCLEO_W, -1)):
    x = wx if sgn > 0 else wx - EDGE_GRIP
    coupon = coupon.union(cq.Workplane('XY').box(EDGE_GRIP + 3.0, 14, 2.0, centered=False).translate((x, 0, 6.0)))
    coupon = coupon.union(cq.Workplane('XY').box(EDGE_GRIP + 3.0, 14, 1.6, centered=False).translate((x, 0, 8.0 + NUCLEO_T + 0.3)))
save('nucleo-rail-coupon', coupon, 'print first: checks the 70 mm width and the 1.6 mm edge slot')

(ROOT / 'validation' / 'parts.json').write_text(json.dumps(results, indent=2) + '\n')
for r in results:
    print(f"{r['part']:26s} {r['bounds_mm']} mm  {r['volume_cm3']} cm3")
