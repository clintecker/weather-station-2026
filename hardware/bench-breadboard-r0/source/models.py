"""The 3D view of each part (renders/3d-*.png): KiCad 10's own model where its library has one
(resistors, capacitors, pin headers, the JST plug), and a box at the part's real size where it has
none (the breakout boards, the RJ11 jack, the battery). Sizes in mm, from the parts' design files:
SparkFun RJ11_Breakout (a 21.6 x 41.1 mm panel of two boards), Adafruit-BQ24074-PCB (38.1 x 33.0),
Adafruit-INA228-PCB and Adafruit-MAX17048-PCB (25.4 x 20.3), Pololu #2122 (11 x 17), Adafruit #353
battery (69 x 54 x 18)."""
from pathlib import Path

KICAD3D = '${KICAD10_3DMODEL_DIR}'
HEADER_Z = 8.5                    # a breakout sits on its pin header: plastic 2.5 mm plus 6 mm pins
PCB = 1.6

BOARD_BLACK = (0.10, 0.10, 0.12)
SPARKFUN_RED = (0.70, 0.08, 0.08)
POLOLU_BLUE = (0.10, 0.25, 0.60)
JACK = (0.90, 0.88, 0.80)
TERMINAL = (0.15, 0.35, 0.80)
BATTERY = (0.75, 0.75, 0.80)

# Boxes: (dx, dy, w, d, h, z, colour). dx, dy: the box centre from the centre of the part's pins
# (+dy is down the breadboard, into its rows). w along the columns, d along the rows.
BOXES = {
    'BOB': [(0, 9.0, 21.6, 20.6, PCB, HEADER_Z, SPARKFUN_RED), (0, 13.5, 14.0, 13.0, 11.5, HEADER_Z + PCB, JACK)],
    'CHGR': [(0, 15.0, 38.1, 33.0, PCB, HEADER_Z, BOARD_BLACK)],
    'INA': [(0, 8.6, 25.4, 20.3, PCB, HEADER_Z, BOARD_BLACK), (0, 14.5, 10.5, 7.0, 8.5, HEADER_Z + PCB, TERMINAL)],
    'GAUGE': [(0, -6.5, 25.4, 20.3, PCB, HEADER_Z, BOARD_BLACK)],
    'REG': [(0, 7.0, 11.0, 17.0, PCB, HEADER_Z, POLOLU_BLUE)],
    'CELL': [(75.0, 52.0, 54.0, 69.0, 18.0, 0.0, BATTERY)],   # beside board B, on its pigtail
}
# KiCad's own models: (file, rotation about z in degrees) for parts by kind.
KICAD = {
    'resistor': ('Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal.step', 0),
    'capacitor': ('Capacitor_THT.3dshapes/C_Disc_D3.0mm_W2.0mm_P2.50mm.step', 0),
    'jst': ('Connector_JST.3dshapes/JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical.step', 0),
}


def header_model(pins):
    """KiCad's vertical pin header for a row of n pins, turned to run along the columns."""
    return (f'Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x{pins:02d}_P2.54mm_Vertical.step', -90)


def models_for(part):
    """[(kicad file or None, rotation, box or None)] for one part. The KiCad model sits at the first
    pin, as its footprint's origin is pin 1; a box sits at the centre of the pins."""
    n = len(part.pins)
    kind = part.kind.lower()
    if 'resistor' in kind or 'ohm' in kind and 'load' in kind:
        return [(*KICAD['resistor'], None)]
    if 'capacitor' in kind:
        return [(*KICAD['capacitor'], None)]
    out = []
    if part.id == 'CELL':
        out.append((*KICAD['jst'], None))
    elif n >= 2:
        out.append((*header_model(n), None))
    key = 'BOB' if part.id.startswith('BOB') else part.id
    out += [(None, 0, box) for box in BOXES.get(key, [])]
    return out


def write_box(path, box):
    """A VRML box (KiCad reads .wrl in units of 0.1 inch) with its base at z 0 of the model."""
    _dx, _dy, w, d, h, _z, (r, g, b) = box
    u = 1/2.54
    Path(path).write_text(
        '#VRML V2.0 utf8\n'
        f'Transform {{ translation 0 0 {h/2*u:.4f} children [ Shape {{\n'
        f'  appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} }} }}\n'
        f'  geometry Box {{ size {w*u:.4f} {d*u:.4f} {h*u:.4f} }} }} ] }}\n')
