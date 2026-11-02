"""The 3D view of each part (renders/3d-*.png): KiCad 10's own model where its library has one
(resistors, capacitors, pin headers), and a box at the part's real size where it has none (the
breakout boards, the RJ11 jack, the pack). Sizes in mm, from the parts' design files: SparkFun
RJ11_Breakout (a 21.6 x 41.1 mm panel of two boards), Adafruit-BQ24074-PCB (38.1 x 33.0),
Adafruit-INA228-PCB and Adafruit-MAX17048-PCB (25.4 x 20.3), Pololu #2122 (11 x 17), Adafruit #353
pack (69 x 54 x 18). A breakout with no maker model and no colour of its own (a later part such as
the load switch LSW) is a generic pre-assembled board (GENERIC_BOARD) on its `body`.

Off the breadboard (record D2): a part placed by `place_mm` lies on the bench plate at z 0, its box
offset from its place point by OFF_BOARD (the pack hangs away from board B, its plug at the point the
leads end); a lever connector ([[joint]]) is a box over its drawn positions (JOINT_BOX)."""
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[3]/'vendor'/'cad'   # tools/fetch-cad.sh
KICAD3D = '${KICAD10_3DMODEL_DIR}'
BREADBOARD_H = 8.5                # an 830-point breadboard body is 8.5 mm tall
HEADER_Z = BREADBOARD_H + 2.5     # a breakout's header pins go into the breadboard: its plastic is 2.5 mm
WIRE_Z = BREADBOARD_H + 2.0       # jumper wires run 2 mm above the breadboard
WIRE_R = 0.5                      # mm, the radius of a 22 AWG jumper with its insulation
PCB = 1.6

BOARD_BLACK = (0.10, 0.10, 0.12)
SPARKFUN_RED = (0.70, 0.08, 0.08)
POLOLU_BLUE = (0.10, 0.25, 0.60)
GENERIC_BOARD = (0.20, 0.45, 0.30)   # a pre-assembled breakout without a maker model or colour here
JACK = (0.90, 0.88, 0.80)
TERMINAL = (0.15, 0.35, 0.80)
BATTERY = (0.75, 0.75, 0.80)
WAGO_GREY = (0.82, 0.82, 0.80)
WAGO_ORANGE = (0.95, 0.50, 0.05)
NTC_BEAD = (0.20, 0.20, 0.25)
ADAPTER_WHITE = (0.93, 0.93, 0.93)

# Boxes: (dx, dy, w, d, h, z, colour). dx, dy: the box centre from the centre of the part's pins
# (+dy is down the breadboard, into its rows), or from the place point of a part placed by place_mm.
# w along the columns, d along the rows. A breakout's board is its `body` in wiring.toml (the same
# outline the jumper planner keeps clear); BOARD_COLOUR gives its colour, and EXTRA the parts on it.
OLED_GREEN = (0.10, 0.45, 0.20)
GLASS = (0.04, 0.04, 0.06)
BOARD_COLOUR = {'BOB': SPARKFUN_RED, 'CHGR': BOARD_BLACK, 'INA': BOARD_BLACK, 'GAUGE': BOARD_BLACK, 'REG': POLOLU_BLUE,
                'OLED': OLED_GREEN}
EXTRA = {
    'BOB': [(0, -13.5, 14.0, 13.0, 11.5, HEADER_Z + PCB, JACK)],          # the RJ11 jack, at the outer end
    'INA': [(0, -14.5, 10.5, 7.0, 8.5, HEADER_Z + PCB, TERMINAL)],        # the screw terminal
    'OLED': [(-0.6, -26.6, 74.0, 46.0, 5.0, HEADER_Z + PCB, GLASS)],      # the glass (Adafruit #2674: 74 x 46 x 5 mm)
}
# Off the breadboard, on the plate (z 0), from each part's place point. The pack's plug end is its place
# point, so its body hangs away from board B (-y); the NTC bead is taped on the pack's top; the wall
# adapter is a stand-in box where its cable is drawn from (the adapter itself is at the mains socket).
PACK_H = 18.0
OFF_BOARD = {
    'PACK': [(0.0, -30.0, 69.0, 54.0, PACK_H, 0.0, BATTERY)],
    'NTC': [(0.0, 0.0, 4.0, 4.0, 3.0, PACK_H, NTC_BEAD)],
    'ADAPTER': [(0.0, 0.0, 24.0, 24.0, 20.0, 0.0, ADAPTER_WHITE)],
}
OFF_BOARD_DEFAULT = (0.0, 0.0, 8.0, 6.0, 4.0, 0.0, GENERIC_BOARD)   # an off-board part not listed above
# A WAGO 222 lever connector, by kind: its box over the drawn positions (wiring.JOINT_PITCH apart, a
# drawing pitch), JOINT_D deep and JOINT_H tall, with its levers along the top. Not to scale in width
# and depth, so the four joints sit apart as placed; about the 222 series' height.
JOINT_KINDS = ('WAGO 222-413', 'WAGO 222-415')
JOINT_D = 9.0
JOINT_H = 8.5
LEVER_H = 1.5
# The makers' own models (tools/fetch-cad.sh), used in place of the boxes when fetched:
# part id -> (file, the model's hole at the left end of the header (x, y) in its own mm, the pin on that
# hole). Each model lies board-up with its header along its near edge, labels upright, as each part
# sits on the bench: the left-hand hole takes the part's highest column. Holes measured from the files.
REAL = {
    'CHGR': ('chgr-4755.step', (6.35, 2.54), 'VBUS'),
    'INA': ('ina-5832.step', (3.81, 2.54), 'VCC'),
    'GAUGE': ('gauge-5580.step', (6.35, 2.54), 'VIN'),
    'REG': ('reg-2122.step', (1.91, 1.27), 'VOUT'),
}
PACK_MODEL = ('cell-353.step', (35.0, 27.0))   # the pack's centre in its own mm (Adafruit #353)

def real_model(part_id):
    """(KiCad path, (hx, hy), pin) of a maker's model, or None if it is not fetched."""
    if part_id not in REAL or not (VENDOR/REAL[part_id][0]).exists():
        return None
    file, hole, pin = REAL[part_id]
    return (f'${{KIPRJMOD}}/../../vendor/cad/{file}', hole, pin)


# KiCad's own models: (file, rotation about z in degrees) for parts by kind.
KICAD = {
    'resistor': ('Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal.step', 0),
    'capacitor': ('Capacitor_THT.3dshapes/C_Disc_D3.0mm_W2.0mm_P2.50mm.step', 0),
}


def header_model(pins, rows=1, along_columns=True, female=False):
    """KiCad's vertical pin header, or its pin socket for a female header (the NUCLEO's ARDUINO
    headers CN5, CN6, CN8). Its pins run down the board from pin 1; a breakout's header is turned
    -90 degrees to run along the breadboard's columns; the NUCLEO's stay as drawn."""
    kind = 'PinSocket' if female else 'PinHeader'
    return (f'Connector_{kind}_2.54mm.3dshapes/{kind}_{rows}x{pins:02d}_P2.54mm_Vertical.step',
            -90 if along_columns else 0)


def _is_resistor(kind):
    return 'resistor' in kind or 'ohm' in kind and 'load' in kind


def _off_board(part):
    """The models of a part placed by place_mm, at its place point on the plate."""
    if part.id == 'PACK' and (VENDOR/PACK_MODEL[0]).exists():
        return []   # the maker's model replaces the box (make.py's model_footprints places it)
    if _is_resistor(part.kind.lower()):
        return [(*KICAD['resistor'], None)]
    return [(None, 0, box) for box in OFF_BOARD.get(part.id, [OFF_BOARD_DEFAULT])]


def board_colour(key):
    """A breakout's board colour: its maker's, or GENERIC_BOARD for a pre-assembled breakout without one."""
    return BOARD_COLOUR.get(key, GENERIC_BOARD)


def models_for(part):
    """[(kicad file or None, rotation, box or None)] for one part. make.py anchors the KiCad model on
    the part's left-most pin (the drawing is mirrored), or on the place point of a part off the
    breadboard; a box sits at the centre of the pins, or offset from the place point."""
    if part.place_mm is not None:
        return _off_board(part)
    n = len(part.pins)
    kind = part.kind.lower()
    if _is_resistor(kind):
        return [(*KICAD['resistor'], None)]
    if 'capacitor' in kind:
        return [(*KICAD['capacitor'], None)]
    out = [(*header_model(n), None)] if n >= 2 else []
    key = 'BOB' if part.id.startswith('BOB') else part.id
    if real_model(part.id):
        return out   # the maker's model replaces the box and its extras (model_footprints places it)
    if part.body is not None:
        dx, dy, w, d = part.body
        out.append((None, 0, (dx, dy, w, d, PCB, HEADER_Z, board_colour(key))))
    out += [(None, 0, box) for box in EXTRA.get(key, [])]
    return out


def joint_boxes(joint, pitch):
    """The boxes of a lever connector (a WAGO 222), centred on its drawn positions `pitch` mm apart:
    the body on the plate and its levers along the top. ValueError for a kind with no box here."""
    if joint.kind not in JOINT_KINDS:
        raise ValueError(f'joint {joint.id}: no 3D box for kind {joint.kind!r} (models.JOINT_KINDS)')
    w = joint.positions*pitch
    return [(0.0, 0.0, w, JOINT_D, JOINT_H, 0.0, WAGO_GREY),
            (0.0, -JOINT_D/4, w, JOINT_D/2, LEVER_H, JOINT_H, WAGO_ORANGE)]


def write_box(path, box):
    """A VRML box (KiCad reads .wrl in units of 0.1 inch) with its base at z 0 of the model."""
    _dx, _dy, w, d, h, _z, (r, g, b) = box
    u = 1/2.54
    Path(path).write_text(
        '#VRML V2.0 utf8\n'
        f'Transform {{ translation 0 0 {h/2*u:.4f} children [ Shape {{\n'
        f'  appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} }} }}\n'
        f'  geometry Box {{ size {w*u:.4f} {d*u:.4f} {h*u:.4f} }} }} ] }}\n')


U = 1/2.54                        # KiCad reads .wrl in units of 0.1 inch
BODY = (0.96, 0.96, 0.93)
HOLE_DARK = (0.06, 0.06, 0.06)
RAIL_RED, RAIL_BLUE = (0.85, 0.15, 0.15), (0.15, 0.30, 0.85)


def _v(x, y, z):
    """A board point (mm, y down) as VRML coordinates (0.1 inch, y up)."""
    return f'{x*U:.4f} {-y*U:.4f} {z*U:.4f}'


def _material(rgb):
    return f'appearance Appearance {{ material Material {{ diffuseColor {rgb[0]} {rgb[1]} {rgb[2]} }} }}'


def _quads(points, z, half, rgb):
    """One shape of square tiles (2*half mm) at z, centred on each point."""
    coords, faces = [], []
    for i, (x, y) in enumerate(points):
        coords += [_v(x - half, y - half, z), _v(x + half, y - half, z), _v(x + half, y + half, z), _v(x - half, y + half, z)]
        faces.append(f'{4*i} {4*i+1} {4*i+2} {4*i+3} -1')
    return (f'Shape {{ {_material(rgb)} geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ '
            + ', '.join(coords) + ' ] } coordIndex [ ' + ' '.join(faces) + ' ] } }\n')


def write_breadboard(path, x1, y1, x2, y2, holes, rails):
    """An 830-point breadboard: a white body, a dark opening at each hole, red and blue rail stripes.
    holes: [(x, y)] in mm; rails: [(x1, x2, y, 'red'|'blue')]. Absolute board coordinates."""
    cx, cy, w, d, h = (x1 + x2)/2, (y1 + y2)/2, x2 - x1, y2 - y1, BREADBOARD_H
    out = ['#VRML V2.0 utf8\n',
           f'Transform {{ translation {_v(cx, cy, h/2)} children [ Shape {{ {_material(BODY)} '
           f'geometry Box {{ size {w*U:.4f} {d*U:.4f} {h*U:.4f} }} }} ] }}\n',
           _quads(holes, h + 0.15, 0.55, HOLE_DARK)]
    for rx1, rx2, ry, colour in rails:
        tiles = [(rx1 + i*1.0, ry) for i in range(int((rx2 - rx1)/1.0) + 1)]
        out.append(_quads(tiles, h + 0.02, 0.5, RAIL_RED if colour == 'red' else RAIL_BLUE))
    Path(path).write_text(''.join(out))


def _prism(corners_bottom, corners_top, rgb):
    """A closed solid from four bottom and four top corners (mm), as faces KiCad's VRML reader takes."""
    pts = [_v(*c) for c in corners_bottom + corners_top]
    faces = '0 3 2 1 -1 4 5 6 7 -1 0 1 5 4 -1 1 2 6 5 -1 2 3 7 6 -1 3 0 4 7 -1'
    return (f'Shape {{ {_material(rgb)} geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ '
            f'{", ".join(pts)} ] }} coordIndex [ {faces} ] }} }}\n')


def _bar(p, q, z, rgb, r=WIRE_R):
    """A square wire piece from p to q (mm) at height z, a little longer than the gap so pieces meet."""
    import math
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ''
    ux, uy = dx/length, dy/length
    nx, ny = -uy*r, ux*r
    a = (p[0] - ux*r, p[1] - uy*r)
    b = (q[0] + ux*r, q[1] + uy*r)
    ring = [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]
    return _prism([(x, y, z - r) for x, y in ring], [(x, y, z + r) for x, y in ring], rgb)


def _leg(p, z_top, rgb, r=WIRE_R, z_bottom=BREADBOARD_H):
    """The vertical end of a wire, from the breadboard surface (or z_bottom) up to the wire."""
    ring = [(p[0] - r, p[1] - r), (p[0] + r, p[1] - r), (p[0] + r, p[1] + r), (p[0] - r, p[1] + r)]
    return _prism([(x, y, z_bottom) for x, y in ring], [(x, y, z_top + r) for x, y in ring], rgb)


def write_jumper(path, segments, ends, z, rgb):
    """A jumper wire along its routed segments [(p, q)] at height z, with legs into its two holes."""
    out = ['#VRML V2.0 utf8\n']
    out += [_bar(p, q, z, rgb) for p, q in segments]
    out += [_leg(e, z, rgb) for e in ends]
    Path(path).write_text(''.join(out))


LEAD_Z = HEADER_Z + PCB + 6.0     # a heavy lead runs above the breakouts' boards, terminal to terminal
INSULATION = 0.8                  # mm added to a lead's copper diameter
# Where a lead end meets its part, by the end's kind (make.py's layout names it): the top of a lever
# connector, a NUCLEO header pin's top, a breadboard hole, a terminal on a breakout's board, or a
# terminal of a part on the plate (the pack's plug, the load's leads).
END_Z = {'joint': JOINT_H, 'nucleo': 8.5, 'hole': BREADBOARD_H, 'pin': BREADBOARD_H, 'terminal': HEADER_Z + PCB,
         'off_board': 3.0}
SLEEVE = (0.05, 0.05, 0.05)       # the heat-shrink over an insulated end
SLEEVE_L = 6.0                    # mm of sleeve along the lead at that end


def lead_radius(awg):
    """The outer radius (mm) of a stranded hook-up lead of this gauge with its insulation."""
    return (0.127*92**((36 - awg)/39) + INSULATION)/2


def _sleeve(end, other, r):
    """The heat-shrink over the last SLEEVE_L mm of a lead at an insulated end, a little fatter than it."""
    import math
    length = math.dist(end, other) or 1.0
    k = min(1.0, SLEEVE_L/length)
    start = (end[0] + (other[0] - end[0])*k, end[1] + (other[1] - end[1])*k)
    return _bar(start, end, LEAD_Z, SLEEVE, r*1.6)


def write_lead(path, a, b, awg, rgb, z=(END_Z['terminal'], END_Z['terminal']), insulated=()):
    """A lead (wiring.Lead: a pigtail half, a solid lead, a cable or a Dupont jumper): up from end a at its
    height z[0] (a joint's top, a NUCLEO pin, a hole, a terminal), across at LEAD_Z and down to end b at z[1]. An end named in `insulated`
    ('a' or 'b') stops in the air under a black sleeve: folded back, it reaches nothing."""
    r = lead_radius(awg)
    out = ['#VRML V2.0 utf8\n', _bar(a, b, LEAD_Z, rgb, r)]
    for name, end, other, z_end in (('a', a, b, z[0]), ('b', b, a, z[1])):
        out.append(_sleeve(end, other, r) if name in insulated else _leg(end, LEAD_Z, rgb, r, z_end))
    Path(path).write_text(''.join(out))
