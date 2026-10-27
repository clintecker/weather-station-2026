"""Build the bench breadboard map (docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md).

    .venv/bin/python hardware/bench-breadboard-r0/source/make.py all [--out DIR]
    .venv/bin/python hardware/bench-breadboard-r0/source/make.py layout OUT.json

`all` checks wiring.toml against the wiring guide and the firmware, plans and proves the jumpers,
writes layout.json, builds the board with KiCad 10's Python, routes the jumpers with
KiCadRoutingTools, and runs KiCad's DRC. Any problem stops it before a file is written to DIR."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
HW = SOURCE.parent
ROOT = HW.parent.parent
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(ROOT/'tools'))
import kicad_env  # noqa: E402
import wiring  # noqa: E402
# build_schematic, models, pcb_read and render (Pillow) load only to draw: the checks and the build
# sheet need the standard library alone (CI runs those tests without Pillow).

DATA = SOURCE/'wiring.toml'
GUIDE = ROOT/'docs'/'hardware'/'bench-station-wiring.md'
APP = ROOT/'firmware'/'stage0-node'/'App'
NAME = 'bench-breadboard'
MARGIN = 6.0      # mm around everything, inside the board outline
ROUTE = ['--nets', 'W*', '--grid-step', '0.635', '--track-width', '0.4', '--clearance', '0.2',
         '--layers', 'F.Cu', 'B.Cu']


def checked():
    """The model and its jumpers, or SystemExit naming every problem."""
    w = wiring.load(DATA)
    problems = wiring.check_guide(w, GUIDE) + wiring.check_firmware(w, APP)
    jumpers = wiring.plan_jumpers(w)
    problems += wiring.prove(w, jumpers)
    if problems:
        raise SystemExit('make.py: ' + '\n  '.join(['the model has problems:'] + problems))
    return w, jumpers


def model_footprints(w):
    """The 3D models of each part, on footprints with no pads: [{ref, x, y, models: [{file, z, rot}]}].
    A box's VRML file is models/<ref>.wrl next to the board."""
    import models
    out = []
    for part in w.parts.values():
        pins = [wiring.hole_xy(h) for h in part.pins.values()]
        cx, cy = sum(x for x, _ in pins)/len(pins), sum(y for _, y in pins)/len(pins)
        for i, (file, rot, box) in enumerate(models.models_for(part)):
            ref = f'3D_{part.id}_{i}'
            if box is None:   # KiCad's models run to the right from their pin 1: anchor on the left-most pin
                left = min(pins)
                out.append({'ref': ref, 'x': left[0], 'y': left[1], 'box': None,
                            'models': [{'file': f'{models.KICAD3D}/{file}', 'z': models.BREADBOARD_H, 'rot': rot}]})
            else:
                out.append({'ref': ref, 'x': cx + box[0], 'y': cy + box[1], 'box': list(box),
                            'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': box[5], 'rot': 0}]})
        real = models.real_model(part.id)
        if real:   # its left-hand header hole on the pin it carries, the board on its header
            file, (hx, hy), pin = real
            x, y = wiring.hole_xy(part.pins[pin])
            out.append({'ref': f'3D_{part.id}_maker', 'x': x, 'y': y, 'box': None,
                        'models': [{'file': file, 'z': models.HEADER_Z, 'rot': 0, 'dx': -hx, 'dy': -hy}]})
        if part.id == 'CELL' and (models.VENDOR/models.CELL_MODEL[0]).exists():   # on the bench beside board B
            file, (mx, my) = models.CELL_MODEL
            out.append({'ref': '3D_CELL_maker', 'x': cx + 75.0, 'y': cy + 52.0, 'box': None,
                        'models': [{'file': f'${{KIPRJMOD}}/../../vendor/cad/{file}', 'z': 0.0, 'rot': 0,
                                    'dx': -mx, 'dy': -my}]})
    return out


def hole_name(h):
    return f'{h[1]}{h[2]}' if h[0] != 'N' else f'{h[1]}.{h[2]}'


def _part_box(part):
    xs, ys = zip(*(wiring.hole_xy(h) for h in part.pins.values()), strict=False)
    return [min(xs) - 1.6, min(ys) - 1.6, max(xs) + 1.6, max(ys) + 1.6]


def layout(w, jumpers):
    """Everything build_pcb.py and the renderer draw, in mm."""
    end_net = {h: j.id for j in jumpers for h in (j.a, j.b)}
    footprints = []
    for board in wiring.BOARDS:
        holes = [{'name': hole_name(h), 'x': round(wiring.hole_xy(h)[0], 4), 'y': round(wiring.hole_xy(h)[1], 4),
                  'net': end_net.get(h)} for h in wiring.board_holes(board)]
        footprints.append({'ref': f'BB_{board}', 'holes': holes})
    nucleo = [('N', header, pin) for header, (_x, _c, n) in wiring.HEADERS.items() for pin in range(1, n + 1)]
    footprints.append({'ref': 'NUCLEO', 'holes': [
        {'name': hole_name(h), 'x': round(wiring.hole_xy(h)[0], 4), 'y': round(wiring.hole_xy(h)[1], 4),
         'net': end_net.get(h)} for h in nucleo]})
    boards = []
    for board, label in (('A', 'BOARD A: SIGNALS'), ('B', 'BOARD B: POWER'), ('C', 'BOARD C: DISPLAY')):
        x0 = wiring.BOARD_X[board]
        boards.append({'id': board, 'label': label, 'x1': x0 - 2.54, 'y1': -2.54,
                       'x2': x0 + wiring.BOARD_WIDTH + 2.54, 'y2': wiring.BOARD_HEIGHT + 2.54})
    parts = []
    for part in w.parts.values():
        box = _part_box(part)
        parts.append({'id': part.id, 'kind': part.kind, 'board': part.board, 'box': box,
                      'body': wiring.body_rect(part),
                      'label_x': box[0] + 1.0, 'label_y': box[1] - 1.0,
                      'pins': {n: wiring.hole_xy(h) for n, h in part.pins.items()}})
    labels = []
    for header, (_x0, cols, _n) in wiring.HEADERS.items():
        x, y = wiring.hole_xy(('N', header, 1))
        labels.append({'text': header, 'x': x + 0.6*(cols - 1)*2.54, 'y': y - 2.5})
    # The column numbers printed on the board, below row j's rails: centred on the column (KiCad centres
    # its text; render.py centres labels marked so), past the 3D breadboard body's edge (BOARD_HEIGHT + 4).
    for board in wiring.BOARDS:
        for col in (1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 63):
            x, _y = wiring.hole_xy((board, 'R+', col))
            labels.append({'text': str(col), 'x': x, 'y': wiring.BOARD_HEIGHT + 6.0, 'centre': True})
    nx, ny = wiring.hole_xy(('N', 'CN7', 1))
    labels.append({'text': 'NUCLEO-WL55JC1 headers: check against UM2592, not to scale', 'x': nx + 25, 'y': ny - 6})
    xs = [h['x'] for f in footprints for h in f['holes']]
    ys = [h['y'] for f in footprints for h in f['holes']]
    tops = [wiring.body_rect(p)[1] for p in w.parts.values() if p.body is not None]
    outline = [min(xs) - MARGIN, min(ys + tops) - MARGIN - 4, max(xs) + MARGIN, max(ys) + MARGIN]
    return {'jumper_nets': [j.id for j in jumpers], 'footprints': footprints, 'boards': boards, 'parts': parts,
            'labels': labels, 'outline': outline,
            'jumpers': [{'id': j.id, 'net': j.net, 'class': w.net_class[j.net],
                         'a': list(wiring.hole_xy(j.a)), 'b': list(wiring.hole_xy(j.b)),
                         'a_name': where(j.a), 'b_name': where(j.b),
                         # A wire between boards, or to the NUCLEO, hops over in the air: drawn straight.
                         'flying': j.a[0] != j.b[0]} for j in jumpers]}


def where(h):
    """A hole as the build sheet names it: 'A:j14' or 'NUCLEO CN10.14'."""
    return f'NUCLEO {h[1]}.{h[2]}' if h[0] == 'N' else f'{h[0]}:{h[1]}{h[2]}'


def nucleo_jumpers(jumpers, nets):
    """The ids of the jumpers that take these nets to the NUCLEO."""
    return [j.id for j in jumpers if j.net in nets and 'N' in (j.a[0], j.b[0])]


STAGE_TITLE = {0: 'Board A', 1: 'Board B', 2: 'Board C', 3: 'Between the boards', 4: 'To the NUCLEO'}


def build_sheet(w, jumpers):
    """The hole-by-hole build sheet (build-sheet.md): parts, then jumpers in build order, then the
    checks to do on the bench before power."""
    out = ['# Bench breadboard build sheet', '',
           'Generated by `source/make.py` from `source/wiring.toml`. Do not edit. Build in this order.',
           'Holes are `board:row column`: `A:j14` is board A, row j, column 14. The rails are L+ and L- (beside',
           'row a) and R- and R+ (beside row j). The renders are in `renders/`.', '',
           '## 1. Parts', '', '| Part | What | Board | Pins (pin: hole) | Pin order from |', '|---|---|---|---|---|']
    for part in w.parts.values():
        pins = ', '.join(f'{n}: {where(h)[2:]}' for n, h in part.pins.items())
        out.append(f'| {part.id} | {part.kind} | {part.board} | {pins} | {part.source} |')
    out += ['', '## 2. Jumpers', '', 'Each jumper is one wire between the two holes. Colour by class: '
            'i2c blue, wind green, rain cyan, charger orange, display purple, power red, ground black.']
    stage = None
    for j in jumpers:
        s = wiring.jumper_stage(j)[0]
        if s != stage:
            stage = s
            out += ['', f'### {STAGE_TITLE[s]}', '', '| Jumper | From | To | Net | Class |', '|---|---|---|---|---|']
        out.append(f'| {j.id} | {where(j.a)} | {where(j.b)} | {j.net} | {w.net_class[j.net]} |')
    out += ['', '## Bench checks', '', 'Do these before you connect power.', '']
    for part in w.parts.values():
        if part.source == 'bench check' or part.note:
            out.append(f'- **{part.id}** ({part.kind}): {part.note or "check the pin order on the part"}.')
    to_3v3 = ' and '.join(j.id for j in jumpers if 'N' in (j.a[0], j.b[0]) and ('N', 'CN6', 4) in (j.a, j.b))
    out += [f'- **3V3, not 5 V:** {to_3v3} goes to CN6.4 (3V3). On the Arduino power header the next pin, '
            'CN6.5, is 5 V: check the hole against UM2592 Table 17 before you push the wire in.',
            '- **Rails:** some 830-point boards split each rail at the centre. If yours do, set '
            '`split_rails = true` in `source/wiring.toml` and rebuild: the plan then bridges the halves.',
            '- **NUCLEO headers:** the positions follow the wiring guide. Tick its section 6 checklist '
            'against UM2592 first. The drawing of the headers is not to scale.',
            '- **PGOOD and CHG voltage:** on the bq24074 breakout each status LED and its 10 kOhm resistor '
            'run from the charger output OUT to the pin (PGOOD: D1 and R11. CHG: D3 and R7. Source: '
            'adafruit/Adafruit-BQ24074-PCB). With the LED off, the pin goes toward OUT, up to about 5 V '
            'on USB. Confirm in the STM32WL55 datasheet that PB8 and PB10 '
            f'are 5 V tolerant (FT) before you connect {" and ".join(nucleo_jumpers(jumpers, ("CHG", "PGOOD")))}.',
            '- **Mode A is drawn:** the BATTERY POWER shunt is open and the 100 ohm load is fitted. For mode B, '
            'follow the wiring guide section 5.',
            f'- **OLED wires:** {", ".join(nucleo_jumpers(jumpers, ("OLED_SCLK", "OLED_DIN", "OLED_CS", "OLED_DC", "OLED_RST")))} '
            'run from board C to CN10: use female-to-male jumpers of about 30 cm. In mode B unplug '
            f'{" and ".join(j.id for j in jumpers if j.net == "3V3" and "C" in (j.a[0], j.b[0]))} (the OLED\'s 3.3 V), '
            'or the INA228 counts the display\'s 50-150 mA with the battery current.', '']
    return '\n'.join(out)


def stable_uuids(path):
    """Replace every UUID with one made from its position in the file: two builds are identical."""
    text = Path(path).read_text()
    count = iter(range(1 << 30))
    text = re.sub(r'\(uuid "[0-9a-f-]+"\)',
                  lambda m: f'(uuid "{uuid.uuid5(uuid.NAMESPACE_URL, f"bench-breadboard-r0/{next(count)}")}")', text)
    Path(path).write_text(text)


def run(cmd, what):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'make.py: {what} failed ({r.returncode}):\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}')
    return r


def drc(env, pcb, report):
    """KiCad's DRC: the errors and the unconnected items."""
    run([env.cli, 'pcb', 'drc', '--format', 'json', '--severity-error', '--output', report, pcb], 'DRC')
    r = json.loads(Path(report).read_text())
    return r['violations'], r['unconnected_items']


def build_all(out):
    env = kicad_env.find()
    if env is None:
        raise SystemExit(f'make.py: {kicad_env.missing()}')
    w, jumpers = checked()
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t/'layout.json').write_text(json.dumps(layout(w, jumpers), indent=1, sort_keys=True))
        run([env.python, SOURCE/'build_pcb.py', t/'layout.json', t/f'{NAME}.kicad_pcb'], 'build_pcb.py')
        stable_uuids(t/f'{NAME}.kicad_pcb')
        routed = t/'routed'
        routed.mkdir()
        log = run([env.router_python, env.router/'py_router'/'route.py', t/f'{NAME}.kicad_pcb',
                   routed/f'{NAME}.kicad_pcb', *ROUTE], 'KiCadRoutingTools')
        shutil.copy(t/f'{NAME}.kicad_pro', routed/f'{NAME}.kicad_pro')
        stable_uuids(routed/f'{NAME}.kicad_pcb')
        errors, unconnected = drc(env, routed/f'{NAME}.kicad_pcb', t/'drc.json')
        if errors or unconnected:
            raise SystemExit(f'make.py: DRC found {len(errors)} errors and {len(unconnected)} unconnected items:\n'
                             + json.dumps((errors + unconnected)[:10], indent=1) + '\n' + log.stdout[-2000:])
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for f in (f'{NAME}.kicad_pcb', f'{NAME}.kicad_pro'):
            shutil.copy(routed/f, out/f)
        shutil.copy(t/'layout.json', out/'layout.json')
    outputs(env, w, jumpers, out)
    print(f'make.py: {len(jumpers)} jumpers routed, DRC and ERC clean, written to {out}')


def presentation_models(w, lay, pcb, models_dir):
    """The 3D view's footprints: the parts, the NUCLEO headers, each breadboard body and each jumper
    wire along its routed path. Writes the generated .wrl files into models_dir."""
    import models
    import pcb_read
    import render
    out = model_footprints(w)
    for header, (_x, cols, n) in wiring.HEADERS.items():
        x, y = wiring.hole_xy(('N', header, 1))
        file, rot = models.header_model(n // cols, cols, along_columns=False)
        out.append({'ref': f'3D_{header}', 'x': x, 'y': y, 'box': None,
                    'models': [{'file': f'{models.KICAD3D}/{file}', 'z': 0.0, 'rot': rot}]})
    for b in lay['boards']:
        board = b['id']
        holes = [wiring.hole_xy(h) for h in wiring.board_holes(board)]
        x0 = wiring.BOARD_X[board]
        rails = [(x0, x0 + wiring.BOARD_WIDTH, wiring._row_y(row) + off, colour)
                 for row, off, colour in (('L+', -1.6, 'red'), ('L-', 1.6, 'blue'), ('R-', -1.6, 'blue'), ('R+', 1.6, 'red'))]
        ref = f'3D_BREADBOARD_{board}'
        models.write_breadboard(models_dir/f'{ref}.wrl', x0 - 4.0, -4.0, x0 + wiring.BOARD_WIDTH + 4.0,
                                wiring.BOARD_HEIGHT + 4.0, holes, rails)
        out.append({'ref': ref, 'x': 0.0, 'y': 0.0, 'box': None,
                    'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': 0.0, 'rot': 0}]})
    copper = pcb_read.copper_by_net(pcb)
    for i, j in enumerate(lay['jumpers']):
        rgb = tuple(c/255 for c in render.COLOURS[j['class']])
        segments = ([(tuple(j['a']), tuple(j['b']))] if j['flying']
                    else [(p, q) for p, q, _layer in copper[j['id']]['segments']])
        ref = f'3D_{j["id"]}'
        models.write_jumper(models_dir/f'{ref}.wrl', segments, [tuple(j['a']), tuple(j['b'])],
                            models.WIRE_Z + 0.4*(i % 4), rgb)
        out.append({'ref': ref, 'x': 0.0, 'y': 0.0, 'box': None,
                    'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': 0.0, 'rot': 0}]})
    return out


RENDER_3D = {'3d-top.png': ['--side', 'top', '--zoom', '1.1'],
             '3d-angle.png': ['--side', 'top', '--perspective', '--rotate', '-35,0,15', '--zoom', '1.3']}


def outputs(env, w, jumpers, out):
    """Everything else from the routed board: models, schematic (ERC), build sheet, renders."""
    import build_schematic
    import models
    import render
    lay = json.loads((out/'layout.json').read_text())
    shutil.rmtree(out/'models', ignore_errors=True)   # no model of an earlier build stays
    (out/'models').mkdir()
    view = presentation_models(w, lay, out/f'{NAME}.kicad_pcb', out/'models')
    for m in view:
        if m['box']:
            models.write_box(out/'models'/f'{m["ref"]}.wrl', m['box'])
    (out/'models'/'view.json').write_text(json.dumps(view, indent=1, sort_keys=True))
    view_pcb = out/f'{NAME}-3d.kicad_pcb'
    run([env.python, SOURCE/'build_pcb.py', '--add-models', out/f'{NAME}.kicad_pcb', out/'models'/'view.json', view_pcb],
        'build_pcb.py --add-models')
    stable_uuids(view_pcb)
    shutil.copy(out/f'{NAME}.kicad_pro', out/f'{NAME}-3d.kicad_pro')
    sch = out/f'{NAME}.kicad_sch'
    build_schematic.write(w, sch)
    run([env.cli, 'sch', 'erc', '--format', 'json', '--severity-error', '--exit-code-violations',
         '--output', out/'erc.json', sch], 'ERC')
    (out/'erc.json').unlink()
    (out/'build-sheet.md').write_text(build_sheet(w, jumpers))
    renders = out/'renders'
    render.render_all(lay, out/f'{NAME}.kicad_pcb', renders)
    run([env.cli, 'sch', 'export', 'pdf', '--output', renders/'schematic.pdf', sch], 'schematic PDF')
    for name, angle in RENDER_3D.items():
        run([env.cli, 'pcb', 'render', '--quality', 'high', '--width', '3000', '--height', '1400',
             '--background', 'opaque', *angle, '--output', renders/name, view_pcb], f'render {name}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('all')
    a.add_argument('--out', default=str(HW))
    lay = sub.add_parser('layout')
    lay.add_argument('out')
    args = ap.parse_args(argv)
    if args.cmd == 'layout':
        Path(args.out).write_text(json.dumps(layout(*checked()), indent=1, sort_keys=True))
    else:
        build_all(args.out)


if __name__ == '__main__':
    main()
