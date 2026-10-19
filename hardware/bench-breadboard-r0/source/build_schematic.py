"""Write the wiring schematic (bench-breadboard.kicad_sch) from wiring.toml, drawn as circuits.

KiCad 10's own symbols (Device:R, Device:C, Device:R_Variable, Device:Battery_Cell, Switch:SW_Reed,
power:GND, power:+3V3, power:PWR_FLAG) are copied from its library into the file. The breakout
modules and the NUCLEO are labelled boxes whose pins are the parts' own. Wires join the parts of
each circuit; a net label joins a circuit to the NUCLEO pin of the same name. The meter's reed
switches and vane resistors sit inside the SEN-15901 and reach the breadboard through its cables:
they are drawn across the RJ11 breakout pins they connect (references in METER), and are not
breadboard parts."""
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
        self.npwr += 1
        self.place(f'#PWR{self.npwr:03d}', f'power:{NET_POWER[net]}', p[0], p[1], rot, NET_POWER[net], hide=True)

    def flag(self, p):
        self.npwr += 1
        self.place(f'#FLG{self.npwr:03d}', 'power:PWR_FLAG', p[0], p[1], 0, 'PWR_FLAG', hide=True)

    def wire(self, *points):
        for p, q in zip(points, points[1:]):
            self.items.append(f'(wire (pts (xy {p[0]:.2f} {p[1]:.2f}) (xy {q[0]:.2f} {q[1]:.2f})) '
                              f'(stroke (width 0) (type default)) (uuid {uid(f"w{len(self.items)}")}))')

    def junction(self, p):
        self.items.append(f'(junction (at {p[0]:.2f} {p[1]:.2f}) (diameter 0) (color 0 0 0 0) (uuid {uid(f"j{len(self.items)}")}))')

    def label(self, name, p):
        self.items.append(f'(label "{name}" (at {p[0]:.2f} {p[1]:.2f} 0) (effects (font (size {TEXT} {TEXT})) '
                          f'(justify left bottom)) (uuid {uid(f"l{len(self.items)}")}))')

    def nc(self, p):
        self.items.append(f'(no_connect (at {p[0]:.2f} {p[1]:.2f}) (uuid {uid(f"nc{len(self.items)}")}))')

    def text(self, value, x, y, size=TEXT):
        self.items.append(f'(text "{value}" (at {x:.2f} {y:.2f} 0) (effects (font (size {size} {size})) (justify left)) '
                          f'(uuid {uid(f"t{len(self.items)}")}))')

    def file(self, title):
        return (f'(kicad_sch (version 20230121) (generator eeschema) (uuid {uid("root")}) (paper "A3")\n'
                f'(title_block (title "{title}") (rev "r0"))\n(lib_symbols {"".join(self.lib.values())})\n'
                + '\n'.join(self.items) + '\n(sheet_instances (path "/" (page "1"))))\n')


def box_symbol(name, left, right, pitch):
    """A module box: `left` and `right` are [(number, name)] top to bottom, `pitch` mm apart."""
    rows = max(len(left), len(right), 1)
    top, bottom = pitch/2, -(rows - 1)*pitch - pitch/2
    pins = ''.join(f'(pin passive line (at -2.54 {-i*pitch:.2f} 0) (length 2.54) (name "{n}" (effects (font (size 1 1)))) '
                   f'(number "{num}" (effects (font (size 1 1)))))' for i, (num, n) in enumerate(left))
    pins += ''.join(f'(pin passive line (at {BOX_W + 2.54:.2f} {-i*pitch:.2f} 180) (length 2.54) (name "{n}" '
                    f'(effects (font (size 1 1)))) (number "{num}" (effects (font (size 1 1)))))' for i, (num, n) in enumerate(right))
    return (f'(symbol "BB:{name}" (pin_names (offset 0.5)) (in_bom yes) (on_board yes) '
            f'(property "Reference" "U" (at 0 {top + 2.54:.2f} 0) (effects (font (size {TEXT} {TEXT})))) '
            f'(property "Value" "{name}" (at 0 {top + 5.08:.2f} 0) (effects (font (size {TEXT} {TEXT})))) '
            f'(symbol "{name}_0_1" (rectangle (start 0 {top:.2f}) (end {BOX_W:.2f} {bottom:.2f}) '
            f'(stroke (width 0.254) (type default)) (fill (type background)))) (symbol "{name}_1_1" {pins}))')


def module(s, w, ref, at, left, right, pitch, title):
    """A breakout as a box at `at` (its first pin row). left/right: the pin names drawn on each side; its
    other pins go on the left, below, with no-connect marks. Returns {pin name: (x, y)}."""
    names = list(w.parts[ref].pins)
    number = {n: str(i + 1) for i, n in enumerate(names)}
    rest = [n for n in names if n not in left and n not in right]
    s.symbol(f'BB:{ref}', box_symbol(ref, [(number[n], n) for n in left + rest], [(number[n], n) for n in right], pitch))
    pos = s.place(ref, f'BB:{ref}', at[0], at[1], value=title, fields=(at[0], at[1] - pitch/2 - 6.35))
    by_name = {n: pos[number[n]] for n in names}
    for n in rest:
        s.nc(by_name[n])
    return by_name


def _std(s):
    for lib, name in (('Device', 'R'), ('Device', 'C'), ('Device', 'R_Variable'), ('Device', 'Battery_Cell'),
                      ('Switch', 'SW_Reed'), ('power', 'GND'), ('power', '+3V3'), ('power', 'PWR_FLAG')):
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


def schematic(w):
    s = Sheet()
    _std(s)
    s.text('Bench station on breadboards: the circuits of docs/hardware/bench-station-wiring.md', 25.4, 15.24, 2.0)
    s.text('SW_CUPS, SW_RAIN and VANE_R are inside the SEN-15901 weather meter: its cables plug into the RJ11 breakouts.',
           25.4, 20.32)

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
    node = _reed(s, 'SW_CUPS', b['3'], b['4'], 'reed switch')
    s.junction(node)
    _signal(s, right(b['4'], NODE), 'CUPS', 'R1', 'C1')
    s.wire(node, right(b['4'], NODE))
    s.junction(right(b['4'], NODE))
    vx = right(b['5'], 12.7)
    vr = s.place('VANE_R', 'Device:R_Variable', vx[0], vx[1] + 7.62, 0, 'vane resistors',   # pin 1 (the signal) on top
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
    node = _reed(s, 'SW_RAIN', b['3'], b['4'], 'reed switch')
    s.junction(node)
    _signal(s, right(b['4'], NODE), 'RAIN', 'R2', 'C2')
    s.wire(node, right(b['4'], NODE))
    s.junction(right(b['4'], NODE))

    # The STEMMA QT hub: power from the NUCLEO, I2C to PA11 and PA12.
    q = module(s, w, 'QT', (231.14, 45.72), [], ['GND', 'V+', 'SDA', 'SCL'], 5.08, 'STEMMA QT cable to the 5-port hub')
    s.wire(q['GND'], right(q['GND'], 7.62))
    s.power('GND', right(q['GND'], 7.62), 90)
    s.wire(q['V+'], right(q['V+'], 7.62))
    s.power('3V3', right(q['V+'], 7.62), 270)
    for pin, net in (('SDA', 'I2C_SDA'), ('SCL', 'I2C_SCL')):
        s.wire(q[pin], right(q[pin], 10.16))
        s.label(net, right(q[pin], 10.16))
    s.text('The hub also feeds the SHT45 (0x44), BMP581 (0x47), LTR390 (0x53), SHTC3 (0x70),', 226.06, 71.12)
    s.text('INA228 (0x40) and MAX17048 (0x36), each on its own STEMMA QT cable.', 226.06, 74.93)

    # The power chain, mode A: cell -> INA228 shunt -> charger -> regulator -> BATTERY POWER shunt -> 3V3.
    s.text('Power chain, mode A (daily): the BATTERY POWER shunt is open, the test load is fitted (guide section 5).',
           226.06, 109.22)
    y0 = 127.0
    cell = s.place('CELL', 'Device:Battery_Cell', 233.68, y0 + 10.16, 0, '6600 mAh cell')
    s.power('GND', cell['2'])
    ina = module(s, w, 'INA', (254.0, y0), ['VIN+', 'GND'], ['VIN-'], 5.08, 'INA228 (shunt from VIN+ to VIN-)')
    s.wire(cell['1'], (cell['1'][0], ina['VIN+'][1]), ina['VIN+'])
    s.label('CELL_POS', (cell['1'][0], ina['VIN+'][1]))
    _gnd_below(s, ina['GND'], -5.08)
    chgr = module(s, w, 'CHGR', (320.04, y0), ['LIPO', 'GND'], ['OUT', 'CHG', 'PGOOD'], 5.08, 'bq24074 charger')
    bx = right(ina['VIN-'], 12.7)
    s.wire(ina['VIN-'], bx, (bx[0], chgr['LIPO'][1]), chgr['LIPO'])
    s.label('BATT', bx)
    _gnd_below(s, chgr['GND'], -5.08)
    gauge = module(s, w, 'GAUGE', (254.0, y0 + 55.88), [], ['VBAT', 'GND'], 5.08, 'MAX17048 fuel gauge (across the cell)')
    s.wire(bx, (bx[0], gauge['VBAT'][1]), gauge['VBAT'])
    s.junction(bx)
    _gnd_below(s, gauge['GND'], 5.08)
    ox = right(chgr['OUT'], 12.7)
    s.wire(chgr['OUT'], ox)
    s.label('SYS_OUT', ox)
    for pin in ('CHG', 'PGOOD'):
        s.wire(chgr[pin], right(chgr[pin], 7.62))
        s.label(pin, right(chgr[pin], 7.62))
    reg = module(s, w, 'REG', (320.04, y0 + 76.2), ['VIN', 'GND'], ['VOUT'], 5.08, 'S7V8F3 3.3 V regulator')
    s.wire(ox, (ox[0], y0 + 66.04), (reg['VIN'][0] - 7.62, y0 + 66.04), (reg['VIN'][0] - 7.62, reg['VIN'][1]), reg['VIN'])
    load = s.place('RLOAD', 'Device:R', ox[0] + 10.16, ox[1] + 7.62, 0, '100R 1/2 W test load')
    s.wire(ox, (ox[0] + 10.16, ox[1]), load['1'])
    s.junction(ox)
    s.power('GND', load['2'])
    _gnd_below(s, reg['GND'], -5.08)
    shunt = module(s, w, 'SHUNT', (368.3, y0 + 76.2), ['1'], ['2'], 5.08, 'BATTERY POWER shunt')
    s.wire(reg['VOUT'], shunt['1'])
    s.label('REG_OUT', reg['VOUT'])
    s.wire(shunt['2'], right(shunt['2'], 7.62))
    s.power('3V3', right(shunt['2'], 7.62), 270)

    # Power flags: the 3V3 and GND nets are driven from outside this sheet (the NUCLEO's regulator).
    s.flag((25.4, 119.38))
    s.power('3V3', (25.4, 119.38))
    s.flag((40.64, 119.38))
    s.power('GND', (40.64, 119.38))
    s.text('PWR_FLAG: 3V3 and GND come from the NUCLEO.', 25.4, 127.0)
    return s.file('Bench breadboard wiring')


def write(w, out):
    Path(out).write_text(schematic(w))
