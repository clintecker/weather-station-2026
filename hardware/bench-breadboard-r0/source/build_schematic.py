"""Write the wiring schematic (bench-breadboard.kicad_sch) from wiring.toml: one symbol per part with
its pins in the manufacturer's order, a net label on each connected pin, a no-connect mark on each
unused pin. A label of the same name joins pins (a single sheet). Repository Python, no KiCad."""
import uuid
from pathlib import Path


PIN = 2.54        # mm between pins
COL = 76.2        # mm between symbol columns
ROW_GAP = 12.7    # mm between symbols in a column
LEFT, TOP = 40.0, 40.0


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'bench-breadboard-r0/sch/{name}'))


def prop(name, value, x, y, hide=False):
    return (f'(property "{name}" "{value}" (at {x:.2f} {y:.2f} 0) '
            f'(effects (font (size 1.27 1.27)){" hide" if hide else ""}))')


def symbol_def(name, pins):
    body = ''.join(f'(pin passive line (at -5.08 {-i*PIN:.2f} 0) (length 2.54) '
                   f'(name "{p}" (effects (font (size 1 1)))) (number "{i+1}" (effects (font (size 1 1)))))'
                   for i, p in enumerate(pins))
    bottom = -(len(pins) - 1)*PIN - 1.27
    return (f'(symbol "BB:{name}" (pin_names (offset 0.5)) (in_bom yes) (on_board yes) '
            f'{prop("Reference", "U", 0, 3.81)} {prop("Value", name, 0, 6.35)} '
            f'(symbol "{name}_0_1" (rectangle (start -2.54 1.27) (end 17.78 {bottom:.2f}) '
            f'(stroke (width 0.254) (type default)) (fill (type background)))) '
            f'(symbol "{name}_1_1" {body}))')


def parts_with_nucleo(w):
    """(id, title, pins, net of each pin or None) for every part, and one for the NUCLEO pins used."""
    net_of = {m: net for net, members in w.nets.items() for m in members}
    rows = [(p.id, p.kind, list(p.pins), [net_of.get(f'{p.id}.{n}') for n in p.pins]) for p in w.parts.values()]
    used = sorted({m[2:] for m in net_of if m.startswith('N:')}, key=lambda s: (s.split('.')[0], int(s.split('.')[1])))
    pins = [f'{h} {w.mcu.get(net_of["N:" + h], "")}'.strip() for h in used]
    rows.append(('NUCLEO', 'NUCLEO-WL55JC1 (the pins this map uses)', pins, [net_of['N:' + h] for h in used]))
    return rows


def schematic(w):
    rows = parts_with_nucleo(w)
    lib = ''.join(symbol_def(ref, pins) for ref, _t, pins, _n in rows)
    items, x, y = [], LEFT, TOP
    for ref, title, pins, nets in rows:
        height = len(pins)*PIN + ROW_GAP
        if y + height > 260:
            x, y = x + COL, TOP
        items.append(f'(symbol (lib_id "BB:{ref}") (at {x:.2f} {y:.2f} 0) (unit 1) (in_bom yes) (on_board yes) '
                     f'(dnp no) (uuid {uid(ref)}) {prop("Reference", ref, x, y - 5.08)} '
                     f'{prop("Value", title[:48], x, y - 2.54)} '
                     f'(instances (project "bench-breadboard" (path "/{uid("root")}" (reference "{ref}") (unit 1)))))')
        for i, net in enumerate(nets):
            yy = y + i*PIN
            if net is None:
                items.append(f'(no_connect (at {x - 5.08:.2f} {yy:.2f}) (uuid {uid(f"{ref}nc{i}")}))')
                continue
            items.append(f'(wire (pts (xy {x - 20.32:.2f} {yy:.2f}) (xy {x - 5.08:.2f} {yy:.2f})) '
                         f'(stroke (width 0) (type default)) (uuid {uid(f"{ref}w{i}")}))')
            items.append(f'(label "{net}" (at {x - 20.32:.2f} {yy:.2f} 0) (effects (font (size 1.27 1.27)) '
                         f'(justify left bottom)) (uuid {uid(f"{ref}l{i}")}))')
        y += height
    title = 'Bench station on breadboards: the wiring of docs/hardware/bench-station-wiring.md'
    items.append(f'(text "{title}" (at {LEFT:.2f} 20.00 0) (effects (font (size 2 2)) (justify left)) '
                 f'(uuid {uid("title")}))')
    return (f'(kicad_sch (version 20230121) (generator eeschema) (uuid {uid("root")}) (paper "A3")\n'
            f'(title_block (title "Bench breadboard wiring") (rev "r0"))\n(lib_symbols {lib})\n'
            + '\n'.join(items) + '\n(sheet_instances (path "/" (page "1"))))\n')


def write(w, out):
    Path(out).write_text(schematic(w))
