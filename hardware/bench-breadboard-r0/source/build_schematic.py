"""Write the wiring schematic (bench-breadboard.kicad_sch) from wiring.toml, drawn as circuits.

KiCad 10's own symbols (Device:R, Device:C, Device:R_Variable, Device:Thermistor_NTC, Device:Battery_Cell,
Device:NetTie_2, Switch:SW_Reed, power:GND, power:GNDPWR, power:+3V3, power:PWR_FLAG) are copied from its
library into the file. The breakout modules and the NUCLEO are labelled boxes whose pins are the parts'
own, sockets and screw terminals included; the pins a part ties inside itself (wiring.toml `internal`)
are one jumper pin group, so KiCad joins them as the part does. Wires join the parts of each circuit; a
net label joins a circuit to the NUCLEO pin of the same name. The meter's reed switches and vane
resistors sit inside the SEN-15901 and reach the breadboard through its cables: they are drawn across
the RJ11 breakout pins they connect (references in METER), and are not breadboard parts.

Off the breadboard (record D2): the pack (PACK), the test load (RLOAD), the thermistor (NTC) and the
wall adapter (ADAPTER) are drawn as parts; each WAGO lever connector is a box whose pins are its
positions, all one jumper pin group (a joint is one node). Each lead is a wire with its id beside it,
its stroke by role (LEAD_STROKE: force heaviest, sense thinnest); a lead whose two ends sit far apart
is drawn as a stub at each end with the net's label. A lead end folded back under heat-shrink
(`insulated`) ends in a no-connect. The power-domain ground (record P4: the pack minus, the charger's
battery and output minus, the load return, STAR) is GNDPWR; L_TIE is a net tie, the only conductor
between it and the logic ground GND. make.py adds the table of leads and joints."""
import re
import uuid
from pathlib import Path

import kicad_env

BOX_W = 25.4        # mm, the width of a module box
TEXT = 1.27
FIELD_UPRIGHT = 90   # a field angle that reads upright on a symbol turned 90 degrees; KiCad also
                     # mirrors the alignment of a turned symbol's fields, so those pass justify='right'
NODE = 35.56        # mm from a breakout pin to its signal node: room for the reed switch and its label
NET_POWER = {'3V3': '+3V3', 'GND': 'GND'}     # nets drawn with power symbols (net names +3V3, GND)
METER = ('SW_CUPS', 'SW_RAIN', 'VANE_R')     # the weather meter's own parts, on its cables
# mm: the stroke of a lead off the breadboard by its role (a jumper's wire is KiCad's default, 0).
LEAD_STROKE = {'force': 0.6, 'signal': 0.4, 'supply': 0.4, 'sense': 0.25}
HEAVY = LEAD_STROKE['force']
LEAD_TEXT = 1.0     # mm: the size of a lead's id beside it
POWER_GROUND = 'GNDPWR'   # the power-domain ground's symbol and net (record P4)


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'bench-breadboard-r0/sch/{name}'))


def _sexpr_block(text, start):
    """The balanced (...) block that starts at text[start]."""
    depth = 0
    for i in range(start, len(text)):
        depth += {'(': 1, ')': -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
    raise ValueError('unbalanced')


def library_symbol(lib, name):
    """A symbol from KiCad 10's library, renamed lib:name for the schematic's lib_symbols."""
    app = Path(kicad_env.find().cli).parent.parent if kicad_env.find() else Path(kicad_env.DEFAULT_APP)/'Contents'
    text = (app/'SharedSupport'/'symbols'/f'{lib}.kicad_sym').read_text()
    block = _sexpr_block(text, text.index(f'(symbol "{name}"'))
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def _pins_of(block):
    """{pin number: (x, y)} of a library symbol (library coordinates, y up)."""
    pins = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) [-\d.]+\).*?\(number "([^"]+)"', block, re.S):
        pins.setdefault(m.group(3), (float(m.group(1)), float(m.group(2))))
    return pins


def _rotate(p, rot):
    x, y = p
    return {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[rot]


class Sheet:
    def __init__(self):
        self.lib, self.items, self.pins_of, self.npwr = {}, [], {}, 0

    def symbol(self, lib_id, block):
        if lib_id not in self.lib:
            self.lib[lib_id] = block
            self.pins_of[lib_id] = _pins_of(block)

    def place(self, ref, lib_id, x, y, rot=0, value=None, hide=False, fields=None, field_angle=0, justify='left'):
        """Place a symbol; returns {pin number: (x, y)} on the sheet (y down). fields: where the
        reference and value go (x, y of the reference; the value below it), else beside the symbol."""
        value = value or ref
        h = ' hide' if hide else ''
        fx, fy = fields or (x + 2.54, y - 1.27)
        self.items.append(
            f'(symbol (lib_id "{lib_id}") (at {x:.2f} {y:.2f} {rot}) (unit 1) (in_bom yes) (on_board yes) (dnp no) '
            f'(uuid {uid(ref)}) (property "Reference" "{ref}" (at {fx:.2f} {fy:.2f} {field_angle}) '
            f'(effects (font (size {TEXT} {TEXT})) (justify {justify}){h})) '
            f'(property "Value" "{value}" (at {fx:.2f} {fy + 2.54:.2f} {field_angle}) '
            f'(effects (font (size {TEXT} {TEXT})) (justify {justify}){h})) '
            f'(instances (project "bench-breadboard" (path "/{uid("root")}" (reference "{ref}") (unit 1)))))')
        return {num: (round(x + _rotate(p, rot)[0], 2), round(y - _rotate(p, rot)[1], 2))
                for num, p in self.pins_of[lib_id].items()}

    def power(self, net, p, rot=0):
        """A power symbol: '3V3', 'GND' (NET_POWER) or POWER_GROUND."""
        name = NET_POWER.get(net, net)
        self.npwr += 1
        self.place(f'#PWR{self.npwr:03d}', f'power:{name}', p[0], p[1], rot, name, hide=True)

    def flag(self, p):
        self.npwr += 1
        self.place(f'#FLG{self.npwr:03d}', 'power:PWR_FLAG', p[0], p[1], 0, 'PWR_FLAG', hide=True)

    def wire(self, *points, width=0):
        for p, q in zip(points, points[1:], strict=False):
            self.items.append(f'(wire (pts (xy {p[0]:.2f} {p[1]:.2f}) (xy {q[0]:.2f} {q[1]:.2f})) '
                              f'(stroke (width {width}) (type default)) (uuid {uid(f"w{len(self.items)}")}))')

    def lead(self, w, lead_id, *points, note=True):
        """A lead off the breadboard along `points`: its stroke by role, its id beside its first segment
        (unless `note` is False: a text nearby names it)."""
        lead = next((k for k in w.leads if k.id == lead_id), None)
        if lead is None:
            raise ValueError(f'the schematic draws lead {lead_id}, which wiring.toml does not have')
        self.wire(*points, width=LEAD_STROKE[lead.role])
        (x1, y1), (x2, y2) = points[0], points[1]
        if not note:
            return
        if y1 == y2:   # along: above the wire, from its left end
            self.text(lead_id, min(x1, x2) + 0.64, y1 - 1.27, LEAD_TEXT)
        else:          # down: to its right, half way
            self.text(lead_id, x1 + 0.64, (y1 + y2)/2, LEAD_TEXT)

    def junction(self, p):
        self.items.append(f'(junction (at {p[0]:.2f} {p[1]:.2f}) (diameter 0) (color 0 0 0 0) (uuid {uid(f"j{len(self.items)}")}))')

    def label(self, name, p, angle=0):
        """A net label at p, reading to the right (angle 0) or to the left (180) of it."""
        justify = 'left' if angle == 0 else 'right'
        self.items.append(f'(label "{name}" (at {p[0]:.2f} {p[1]:.2f} {angle}) (effects (font (size {TEXT} {TEXT})) '
                          f'(justify {justify} bottom)) (uuid {uid(f"l{len(self.items)}")}))')

    def nc(self, p):
        self.items.append(f'(no_connect (at {p[0]:.2f} {p[1]:.2f}) (uuid {uid(f"nc{len(self.items)}")}))')

    def text(self, value, x, y, size=TEXT):
        self.items.append(f'(text "{value}" (at {x:.2f} {y:.2f} 0) (effects (font (size {size} {size})) (justify left)) '
                          f'(uuid {uid(f"t{len(self.items)}")}))')

    def file(self, title, rev):
        return (f'(kicad_sch (version 20230121) (generator eeschema) (uuid {uid("root")}) (paper "A3")\n'
                f'(title_block (title "{title}") (rev "{rev}"))\n(lib_symbols {"".join(self.lib.values())})\n'
                + '\n'.join(self.items) + '\n(sheet_instances (path "/" (page "1"))))\n')


def box_symbol(name, left, right, pitch, jumpers=()):
    """A module box: `left` and `right` are [(number, name)] top to bottom, `pitch` mm apart. `jumpers`:
    groups of pin numbers the part ties inside itself (KiCad's jumper pin groups: one net each)."""
    rows = max(len(left), len(right), 1)
    top, bottom = pitch/2, -(rows - 1)*pitch - pitch/2
    pins = ''.join(f'(pin passive line (at -2.54 {-i*pitch:.2f} 0) (length 2.54) (name "{n}" (effects (font (size 1 1)))) '
                   f'(number "{num}" (effects (font (size 1 1)))))' for i, (num, n) in enumerate(left))
    pins += ''.join(f'(pin passive line (at {BOX_W + 2.54:.2f} {-i*pitch:.2f} 180) (length 2.54) (name "{n}" '
                    f'(effects (font (size 1 1)))) (number "{num}" (effects (font (size 1 1)))))' for i, (num, n) in enumerate(right))
    groups = ''.join('(' + ' '.join(f'"{n}"' for n in g) + ')' for g in jumpers)
    groups = f'(jumper_pin_groups {groups}) ' if groups else ''
    return (f'(symbol "BB:{name}" (pin_names (offset 0.5)) {groups}(in_bom yes) (on_board yes) '
            f'(property "Reference" "U" (at 0 {top + 2.54:.2f} 0) (effects (font (size {TEXT} {TEXT})))) '
            f'(property "Value" "{name}" (at 0 {top + 5.08:.2f} 0) (effects (font (size {TEXT} {TEXT})))) '
            f'(symbol "{name}_0_1" (rectangle (start 0 {top:.2f}) (end {BOX_W:.2f} {bottom:.2f}) '
            f'(stroke (width 0.254) (type default)) (fill (type background)))) (symbol "{name}_1_1" {pins}))')


def module(s, w, ref, at, left, right, pitch, title, rest_side='left', apart=()):
    """A breakout as a box at `at` (its first pin row). left/right: the pin and terminal names drawn on
    each side; its other pins go below on `rest_side`, with no-connect marks. Its internal ties are jumper
    pin groups, less the pins in `apart` (a socket pin whose only lead is folded back: drawn on its own,
    ending in a no-connect, so no flag sits on a joined net). Returns {pin name: (x, y)}."""
    part = w.parts[ref]
    names = list(part.pins) + list(part.terminals)
    number = {n: str(i + 1) for i, n in enumerate(names)}
    rest = [n for n in names if n not in left and n not in right]
    sides = (left + rest, right) if rest_side == 'left' else (left, right + rest)
    groups = [g for g in ([number[n] for n in t if n not in apart] for t in part.internal) if len(g) > 1]
    s.symbol(f'BB:{ref}', box_symbol(ref, *([(number[n], n) for n in side] for side in sides), pitch, groups))
    pos = s.place(ref, f'BB:{ref}', at[0], at[1], value=title, fields=(at[0], at[1] - pitch/2 - 6.35))
    by_name = {n: pos[number[n]] for n in names}
    for n in rest:
        s.nc(by_name[n])
    return by_name


def _std(s):
    for lib, name in (('Device', 'R'), ('Device', 'C'), ('Device', 'R_Variable'), ('Device', 'Thermistor_NTC'),
                      ('Device', 'Battery_Cell'), ('Device', 'NetTie_2'), ('Switch', 'SW_Reed'), ('power', 'GND'),
                      ('power', POWER_GROUND), ('power', '+3V3'), ('power', 'PWR_FLAG')):
        s.symbol(f'{lib}:{name}', library_symbol(lib, name))


def right(p, dx):
    return (p[0] + dx, p[1])


def _gnd_below(s, p, dx):
    """A wire from p, dx sideways, then down to a GND symbol."""
    q = right(p, dx)
    s.wire(p, q, (q[0], q[1] + 5.08))
    s.power('GND', (q[0], q[1] + 5.08))
    return q


def _signal(s, node, net, r_ref, c_ref):
    """At node: a 10k pull-up to 3V3 above; a 100 nF filter to GND below (if c_ref); then a label."""
    r = s.place(r_ref, 'Device:R', node[0], node[1] - 7.62, 180, '10k',      # pin 1 (the signal) at the bottom
                fields=(node[0] + 2.54, node[1] - 8.89), justify='right')
    s.wire(node, r['1'])
    s.power('3V3', r['2'])
    end = right(node, 10.16)
    s.wire(node, end)
    if c_ref:
        c = s.place(c_ref, 'Device:C', end[0], end[1] + 3.81, 0, '100n')    # pin 1 (the signal) at the top
        s.power('GND', c['2'])
        s.junction(end)
    s.wire(end, right(end, 10.16))
    s.label(net, right(end, 10.16))


def _reed(s, ref, p_low, p_high, what):
    """The meter's reed switch across two breakout pins (p_low above p_high, 15.24 mm apart)."""
    x = p_low[0] + 12.7
    sw = s.place(ref, 'Switch:SW_Reed', x, (p_low[1] + p_high[1])/2, 90, what,
                 fields=(x + 3.81, (p_low[1] + p_high[1])/2 - 1.27), field_angle=FIELD_UPRIGHT, justify='right')
    top, bottom = sorted(sw.values(), key=lambda q: q[1])
    s.wire(p_low, right(p_low, 12.7), top)
    s.wire(p_high, right(p_high, 12.7), bottom)
    return right(p_high, 12.7)


def meter(s, w, bob, at, rows, title):
    return module(s, w, bob, at, [], rows, 15.24, title)


def _label_out(s, p, net, dx=7.62):
    """A short wire sideways from a pin to a net label reading away from it."""
    s.wire(p, right(p, dx))
    s.label(net, right(p, dx), 0 if dx > 0 else 180)


JOINT_PITCH = 5.08   # mm between a joint symbol's positions


def joint(s, w, jid, at, left, right):
    """A lever connector (a WAGO 222) as a box at `at`: its positions are its pins, numbered as on the
    part and named by the leads in them ('spare' when empty), all one jumper pin group. left/right: the
    positions drawn on each side, every position once. Returns {position: (x, y)}."""
    j = w.joints[jid]
    if sorted(left + right) != list(range(1, j.positions + 1)):
        raise ValueError(f'{jid}: the schematic must draw positions 1 to {j.positions} once each')
    names = {n: ', '.join(k.id for k in w.leads if f'J:{jid}.{n}' in (k.a, k.b)) or 'spare' for n in left + right}
    s.symbol(f'BB:{jid}', box_symbol(jid, [(str(n), names[n]) for n in left], [(str(n), names[n]) for n in right],
                                     JOINT_PITCH, [[str(n) for n in range(1, j.positions + 1)]]))
    pos = s.place(jid, f'BB:{jid}', at[0], at[1], value=j.kind, fields=(at[0], at[1] - JOINT_PITCH/2 - 6.35))
    return {n: pos[str(n)] for n in left + right}


def _ground(s, p, dx, net='GND'):
    """A short wire sideways from p to a ground symbol (GND or POWER_GROUND) facing away from it."""
    q = right(p, dx)
    s.wire(p, q)
    s.power(net, q, 90 if dx > 0 else 270)


def _lead_stub(s, w, lead_id, p, dx, net=None, ground=None):
    """One end of a lead whose other end is drawn elsewhere: a stub dx long from p, ending in the net's
    label (reading away from p) or a ground symbol."""
    q = right(p, dx)
    s.lead(w, lead_id, p, q)
    if ground:
        s.power(ground, q, 90 if dx > 0 else 270)
    else:
        s.label(net, q, 0 if dx > 0 else 180)


def _insulated(s, w, lead_id, p, dx, net=None):
    """A lead folded back under heat-shrink: from p to a no-connect; the pin's own net label if it has one."""
    q = right(p, dx)
    s.lead(w, lead_id, p, q, note=False)
    s.text(f'{lead_id} (insulated)', min(p[0], q[0]), p[1] + 1.91, LEAD_TEXT)
    s.nc(q)
    if net:
        s.label(net, p, 180 if dx < 0 else 0)


def battery_path(s, w, y0):
    """Record P3: pack + -> L_PACK_POS -> WAGO_CELL_POS -> L_CELL_INA -> the INA228's X1 (shunt) ->
    L_INA_BATT -> WAGO_BATT; the gauge's sense lead from CELL+ (P5); the pack's minus to STAR (P4)."""
    pack = s.place('PACK', 'Device:Battery_Cell', 231.14, y0 + 5.08, 0, w.parts['PACK'].kind.split(' (')[0],
                   fields=(228.6, y0 + 3.81), justify='right')
    cell = joint(s, w, 'WAGO_CELL_POS', (243.84, y0), [1], [2, 3, 4, 5])
    s.lead(w, 'L_PACK_POS', pack['1'], cell[1])
    ina = module(s, w, 'INA', (294.64, y0), ['X1_VINP'], ['X1_VINM', 'X1_VBUS', 'VIN-', 'VBUS', 'VIN+'], 5.08,
                 'INA228 #5832: shunt X1.3 VIN+ to X1.1 VIN-')
    s.lead(w, 'L_CELL_INA', cell[2], ina['X1_VINP'])
    for pin, net in (('VIN-', 'BATT'), ('VBUS', 'SYS_OUT'), ('VIN+', 'CELL_POS')):   # header test points
        _label_out(s, ina[pin], net, 5.08)
    _lead_stub(s, w, 'L_VBUS', ina['X1_VBUS'], 15.24, 'SYS_OUT')
    gauge = module(s, w, 'GAUGE', (294.64, y0 + 40.64), ['BAT1+', 'BAT1-'], [], 5.08,
                   'MAX17048 #5580: header held in place only', rest_side='right')
    x = cell[3][0] + 5.08
    s.lead(w, 'L_GAUGE_POS', cell[3], (x, cell[3][1]), (x, gauge['BAT1+'][1]), gauge['BAT1+'])
    _insulated(s, w, 'L_GAUGE_NEG', gauge['BAT1-'], -17.78, 'GAUGE_BAT_NEG')
    star = joint(s, w, 'WAGO_STAR', (243.84, y0 + 50.8), [1], [2, 3, 4, 5])
    s.lead(w, 'L_PACK_NEG', pack['2'], (pack['2'][0], star[1][1]), star[1])
    _lead_stub(s, w, 'L_BATT_NEG', star[2], 12.7, ground=POWER_GROUND)
    _lead_stub(s, w, 'L_RLOAD_B', star[3], 12.7, ground=POWER_GROUND)
    tie = s.place('L_TIE', 'Device:NetTie_2', star[4][0] + 7.62, star[4][1], 0, 'the only tie',
                  fields=(star[4][0] + 3.81, star[4][1] + 2.54))
    s.lead(w, 'L_TIE', star[4], tie['1'])
    _ground(s, tie['2'], 5.08)
    batt = joint(s, w, 'WAGO_BATT', (350.52, y0), [1], [2, 3])
    s.lead(w, 'L_INA_BATT', ina['X1_VINM'], batt[1])
    return batt


def charger(s, w, y0, batt):
    """The bq24074 breakout: its BATT socket on L_BATT_POS and L_BATT_NEG, its SYSOUT socket into
    WAGO_SYS_OUT (P6), its header pins as test points and labels, its USB-C from the adapter."""
    chgr = module(s, w, 'CHGR', (401.32, y0), ['BATT2', 'LIPO', 'BATT1', 'GND', 'GND2', 'GND3', 'SYSOUT1'],
                  ['SYSOUT2', 'OUT', 'CHG', 'PGOOD', 'ISET', 'THERM', 'VBUS', 'USBC'], 5.08,
                  'bq24074 charger #4755', apart=('SYSOUT1',))
    s.lead(w, 'L_BATT_POS', batt[2], chgr['BATT2'])
    _label_out(s, chgr['LIPO'], 'BATT', -5.08)
    _lead_stub(s, w, 'L_BATT_NEG', chgr['BATT1'], -15.24, ground=POWER_GROUND)
    for pin in ('GND', 'GND2', 'GND3'):
        _ground(s, chgr[pin], -5.08, POWER_GROUND)
    _insulated(s, w, 'L_SYSOUT_NEG', chgr['SYSOUT1'], -15.24)
    for pin, net in (('OUT', 'SYS_OUT'), ('CHG', 'CHG'), ('PGOOD', 'PGOOD'), ('ISET', 'ISET_CHGR'), ('THERM', 'THERM'),
                     ('VBUS', 'CHGR_VBUS')):
        _label_out(s, chgr[pin], net, 5.08)
    _lead_stub(s, w, 'L_USB_IN', chgr['USBC'], 15.24, 'CHGR_IN')
    out = joint(s, w, 'WAGO_SYS_OUT', (447.04, y0), [1], [2, 3, 4, 5])
    s.lead(w, 'L_SYSOUT_POS', chgr['SYSOUT2'], out[1])
    load = s.place('RLOAD', 'Device:R', out[2][0] + 30.48, y0 + 7.62, 0, '100R 1/2 W test load (mode A)')
    s.lead(w, 'L_RLOAD_A', out[2], (load['1'][0], out[2][1]), load['1'])
    s.lead(w, 'L_RLOAD_B', load['2'], (load['2'][0], load['2'][1] + 10.16))
    s.power(POWER_GROUND, (load['2'][0], load['2'][1] + 10.16))
    _lead_stub(s, w, 'L_VBUS', out[3], 15.24, 'SYS_OUT')
    _lead_stub(s, w, 'L_REG_VIN', out[4], 15.24, 'SYS_OUT')


def regulator(s, w, y0):
    """Record P1, N3: OUT -> L_REG_VIN -> the S7V8F3 -> LK_REG_SHUNT -> the BATTERY POWER shunt ->
    L_REG_3V3 -> the board-A 3V3 node (CN6.4); its GND strip takes L_TIE and L_NUC_RET."""
    reg = module(s, w, 'REG', (294.64, y0), ['VIN', 'GND'], ['VOUT'], 5.08, 'S7V8F3 3.3 V regulator')
    _lead_stub(s, w, 'L_REG_VIN', reg['VIN'], -15.24, 'SYS_OUT')
    _lead_stub(s, w, 'L_NUC_RET', reg['GND'], -15.24, ground='GND')
    s.text('Its GND strip also takes L_TIE (from WAGO_STAR.4); L_NUC_RET runs to CN6.7.', 274.32, y0 + 17.78)
    shunt = module(s, w, 'SHUNT', (342.9, y0), ['1'], ['2'], 5.08, 'BATTERY POWER shunt (open in mode A)')
    s.wire(reg['VOUT'], shunt['1'])
    s.label('REG_OUT', reg['VOUT'])
    s.lead(w, 'L_REG_3V3', shunt['2'], right(shunt['2'], 15.24))
    s.power('3V3', right(shunt['2'], 15.24), 270)
    s.text('L_REG_3V3: to the board-A 3V3 node, which LK_3V3_CN6_4 joins to CN6.4 (mode B).', 274.32, y0 + 21.59)


def iset_network(s, x, y):
    """Record M2: ISET -> R_ISER (10 kOhm 1 %) -> the PB1 node with C_ISET (100 nF) and R_IPD (1 MOhm) to GND."""
    r = s.place('R_ISER', 'Device:R', x + 8.89, y, 90, '10k 1%', fields=(x + 8.89, y - 5.08), field_angle=FIELD_UPRIGHT)
    s.wire((x, y), r['1'])
    s.label('ISET_CHGR', (x, y), 180)
    node = right(r['2'], 7.62)
    s.wire(r['2'], node, right(node, 10.16), right(node, 17.78))
    s.label('ISET', right(node, 17.78))
    for ref, at, value in (('C_ISET', node, '100n'), ('R_IPD', right(node, 10.16), '1M')):
        part = s.place(ref, 'Device:R' if ref.startswith('R') else 'Device:C', at[0], at[1] + 7.62, 0, value)
        s.wire(at, part['1'])
        s.power('GND', part['2'])
        s.junction(at)


def divider(s, x, y):
    """The charger input divider: CHGR_VBUS through R4 + R5 over R6 to logic ground, VIN_SENSE (PA10)
    at the R5-R6 node (record M2)."""
    s.wire((x, y), (x, y + 2.54))
    s.label('CHGR_VBUS', (x, y))
    node = (x, y + 2.54)
    for ref, net in (('R4', 'VIN_DIV'), ('R5', 'VIN_SENSE'), ('R6', None)):
        r = s.place(ref, 'Device:R', node[0], node[1] + 3.81, 0, '10k 1%', fields=(node[0] - 2.54, node[1] + 3.81),
                    justify='right')
        node = r['2']
        if net is None:
            s.power('GND', node)
            continue
        s.wire(node, right(node, 5.08))
        s.label(net, right(node, 5.08))
        s.junction(node)


def off_board(s, w, y0):
    """The wall adapter on its own cable into the charger's USB-C (D2), and the thermistor on THERM with
    its return to logic ground (D2)."""
    adapter = module(s, w, 'ADAPTER', (294.64, y0), [], ['+'], 5.08, 'USB-C wall adapter, floating (5 V)')
    _lead_stub(s, w, 'L_USB_IN', adapter['+'], 15.24, 'CHGR_IN')
    s.text('One cable: its return reaches the charger GND inside the breakout.', 274.32, y0 + 7.62)
    ntc = s.place('NTC', 'Device:Thermistor_NTC', 391.16, y0 + 2.54, 0, '10k B3950 #372',
                  fields=(393.7, y0 + 1.27))
    s.lead(w, 'L_NTC_THERM', ntc['1'], (ntc['1'][0], ntc['1'][1] - 7.62))
    s.label('THERM', (ntc['1'][0], ntc['1'][1] - 7.62))
    s.lead(w, 'L_NTC_RET', ntc['2'], (ntc['2'][0], ntc['2'][1] + 7.62))
    s.power('GND', (ntc['2'][0], ntc['2'][1] + 7.62))
    s.text('NTC taped to the pack: cut the THERM jumper (R10) first.', 396.24, y0 + 15.24)


def power_chain(s, w):
    """Mode A, the official phase A power wiring of change A (record 4.4): the battery path through the
    joints and the INA228 shunt, the charger, the regulator and the BATTERY POWER shunt; ISET, the divider
    and the NTC on the charger; the gauge's sense lead on CELL+."""
    s.text('Power chain, mode A (daily): the BATTERY POWER shunt is open, the 100 ohm test load is fitted '
           '(guide section 5).', 226.06, 105.41)
    s.text('Leads off the breadboard: force heaviest, sense thinnest, each with its id (table below). A WAGO '
           'lever connector is one node; its pins are its positions.', 226.06, 109.22)
    s.text('Power ground (GNDPWR: pack -, charger BATT and SYSOUT -, load return, STAR) meets logic ground only '
           'through L_TIE. INA228 SJ1 (VBUS-VIN+) open.', 226.06, 113.03)
    batt = battery_path(s, w, 127.0)
    charger(s, w, 127.0, batt)
    regulator(s, w, 213.36)
    iset_network(s, 406.4, 213.36)
    divider(s, 469.9, 205.74)
    off_board(s, w, 246.38)


def qt_cable(s, w, ref, at, title, supply):
    """A STEMMA QT-to-header cable: GND to ground, V+ to `supply` (a power net or a label), I2C labels."""
    q = module(s, w, ref, at, [], ['GND', 'V+', 'SDA', 'SCL'], 5.08, title)
    _ground(s, q['GND'], 7.62)
    if supply in NET_POWER:
        s.wire(q['V+'], right(q['V+'], 7.62))
        s.power(supply, right(q['V+'], 7.62), 270)
    else:
        _label_out(s, q['V+'], supply, 10.16)
    for pin, net in (('SDA', 'I2C_SDA'), ('SCL', 'I2C_SCL')):
        _label_out(s, q[pin], net, 10.16)


def sensor_power(s, w):
    """The I2C bus in two branches (record 4.6, PORT-9): the hub's cable QT and the power monitors' cable
    QTM, both on the unswitched 3V3. Change C, the PA9 sensor load switch, is not part of the
    breadboard build (record 4.6, 2026-11-02), so neither branch is switched and PA9 is unconnected here."""
    qt_cable(s, w, 'QT', (231.14, 45.72), 'STEMMA QT cable to the 5-port hub', '3V3')
    qt_cable(s, w, 'QTM', (350.52, 45.72), 'STEMMA QT cable to the power monitors', '3V3')
    s.text('The power monitors (INA228 0x40, MAX17048 0x36) are on QTM; the hub\'s sensors on QT. Both unswitched: '
           'there is no PA9 sensor switch', 226.06, 71.12)
    s.text('The hub feeds the SHT45 (0x44), BMP581 (0x47), LTR390 (0x53) and SHTC3 (0x70), each on its own '
           'STEMMA QT cable.', 226.06, 74.93)


def schematic(w):
    s = Sheet()
    _std(s)
    s.text('Bench station on breadboards: the circuits of docs/hardware/bench-station-wiring.md', 25.4, 15.24, 2.0)
    s.text('SW_CUPS, SW_RAIN and VANE_R are built into the SEN-15901 weather meter (not parts to fit): they reach the',
           25.4, 20.32)
    s.text('breadboard through the meter\'s two RJ11 cables, which plug into the BOBW and BOBR breakouts.', 25.4, 23.5)

    # The NUCLEO: each pin to a label or a power symbol.
    net_of = {m: net for net, members in w.nets.items() for m in members}
    used = sorted({m[2:] for m in net_of if m.startswith('N:')}, key=lambda h: (h.split('.')[0], int(h.split('.')[1])))
    s.symbol('BB:NUCLEO', box_symbol('NUCLEO', [], [(str(i + 1), f'{w.mcu.get(net_of["N:" + h], "")}/{h}')
                                                   for i, h in enumerate(used)], 5.08))
    pins = s.place('NUCLEO', 'BB:NUCLEO', 25.4, 45.72, value='NUCLEO-WL55JC1 (the pins this map uses)',
                   fields=(25.4, 45.72 - 2.54 - 6.35))
    for i, h in enumerate(used):
        p, net = pins[str(i + 1)], net_of['N:' + h]
        if net in NET_POWER:
            s.wire(p, right(p, 7.62))
            s.power(net, right(p, 7.62), 90 if net == 'GND' else 270)
        else:
            s.wire(p, right(p, 10.16))
            s.label(net, right(p, 10.16))

    # Wind: the cups (pins 3, 4) and the vane (pins 2, 5) on the wind cable's breakout.
    b = meter(s, w, 'BOBW', (101.6, 40.64), ['2', '3', '4', '5'], 'RJ11 breakout, wind cable')
    _gnd_below(s, b['2'], 5.08)
    q = _gnd_below(s, b['3'], 5.08)
    s.junction(q)
    node = _reed(s, 'SW_CUPS', b['3'], b['4'], 'in the anemometer')
    s.junction(node)
    _signal(s, right(b['4'], NODE), 'CUPS', 'R1', 'C_CUPS')
    s.wire(node, right(b['4'], NODE))
    s.junction(right(b['4'], NODE))
    vx = right(b['5'], 12.7)
    vr = s.place('VANE_R', 'Device:R_Variable', vx[0], vx[1] + 7.62, 0, 'in the wind vane',   # pin 1 (the signal) on top
                 fields=(vx[0] + 3.81, vx[1] + 6.35))
    s.wire(b['5'], vx, vr['1'])
    s.power('GND', vr['2'])
    s.junction(vx)
    _signal(s, right(b['5'], NODE + 30.48), 'VANE', 'R3', None)
    s.wire(vx, right(b['5'], NODE + 30.48))
    s.junction(right(b['5'], NODE + 30.48))

    # Rain: the bucket switch (pins 3, 4) on the rain cable's breakout.
    b = meter(s, w, 'BOBR', (101.6, 142.24), ['3', '4'], 'RJ11 breakout, rain cable')
    q = _gnd_below(s, b['3'], 5.08)
    s.junction(q)
    node = _reed(s, 'SW_RAIN', b['3'], b['4'], 'in the rain gauge')
    s.junction(node)
    _signal(s, right(b['4'], NODE), 'RAIN', 'R2', 'C_RAIN')
    s.wire(node, right(b['4'], NODE))
    s.junction(right(b['4'], NODE))

    # The I2C bus in two branches (record 4.6, PORT-9), both on the unswitched 3V3 (change C is not
    # built, 2026-11-02); I2C to PA11 and PA12.
    sensor_power(s, w)

    power_chain(s, w)

    # The bench OLED on SPI1 (board C) and the kit's 220 uF across its supply.
    s.text('Bench OLED on SPI1, board C (firmware/i2cscan/App/oled.h).', 147.32, 190.5)
    s.text('SPI mode: R19 and R21 fitted on its back.', 147.32, 194.31)
    s.text('Its supply on its own pair (record N3): L_OLED_VCC from CN7.16, L_OLED_GND to CN10.20.', 147.32, 198.12)
    o = module(s, w, 'OLED', (175.26, 210.82), ['VCC', 'GND'], ['SCLK', 'DIN', 'CS', 'DC', 'RST'], 2.54,
               'Adafruit #2674 2.7in OLED (SSD1325)')
    vq = right(o['VCC'], -15.24)
    s.lead(w, 'L_OLED_VCC', o['VCC'], vq, (vq[0], vq[1] - 5.08), note=False)
    s.power('3V3', (vq[0], vq[1] - 5.08))
    gq = right(o['GND'], -7.62)
    s.lead(w, 'L_OLED_GND', o['GND'], gq, (gq[0], gq[1] + 5.08), note=False)
    s.power('GND', (gq[0], gq[1] + 5.08))
    for pin, net in (('SCLK', 'OLED_SCLK'), ('DIN', 'OLED_DIN'), ('CS', 'OLED_CS'), ('DC', 'OLED_DC'), ('RST', 'OLED_RST')):
        s.wire(o[pin], right(o[pin], 10.16))
        s.label(net, right(o[pin], 10.16))
    c = s.place('COLED', 'Device:C', 139.7, 215.9, 0, '220 uF (+ to 3V3)')
    s.power('3V3', c['1'])
    s.power('GND', c['2'])

    # Power flags: the 3V3 and GND nets are driven from outside this sheet (the NUCLEO's regulator).
    s.flag((25.4, 160.02))
    s.power('3V3', (25.4, 160.02))
    s.flag((40.64, 160.02))
    s.power('GND', (40.64, 160.02))
    s.flag((55.88, 160.02))
    s.power(POWER_GROUND, (55.88, 160.02))
    s.text('PWR_FLAG: 3V3 and GND come from the NUCLEO; GNDPWR from the pack.', 25.4, 167.64)
    return s.file('Bench breadboard wiring', w.revision)


def write(w, out):
    Path(out).write_text(schematic(w))
