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


def hole_name(h):
    return f'{h[1]}{h[2]}' if h[0] != 'N' else f'{h[1]}.{h[2]}'


def _part_box(part):
    xs, ys = zip(*(wiring.hole_xy(h) for h in part.pins.values()), strict=False)
    return [min(xs) - 1.6, min(ys) - 1.6, max(xs) + 1.6, max(ys) + 1.6]


def layout(w, jumpers):
    """Everything build_pcb.py and the renderer draw, in mm."""
    end_net = {h: j.id for j in jumpers for h in (j.a, j.b)}
    footprints = []
    for board in ('A', 'B'):
        holes = [{'name': hole_name(h), 'x': round(wiring.hole_xy(h)[0], 4), 'y': round(wiring.hole_xy(h)[1], 4),
                  'net': end_net.get(h)} for h in wiring.board_holes(board)]
        footprints.append({'ref': f'BB_{board}', 'holes': holes})
    nucleo = [('N', header, pin) for header, (_x, _c, n) in wiring.HEADERS.items() for pin in range(1, n + 1)]
    footprints.append({'ref': 'NUCLEO', 'holes': [
        {'name': hole_name(h), 'x': round(wiring.hole_xy(h)[0], 4), 'y': round(wiring.hole_xy(h)[1], 4),
         'net': end_net.get(h)} for h in nucleo]})
    boards = []
    for board, label in (('A', 'BOARD A: SIGNALS'), ('B', 'BOARD B: POWER')):
        x0 = wiring.BOARD_X[board]
        boards.append({'id': board, 'label': label, 'x1': x0 - 2.54, 'y1': -2.54,
                       'x2': x0 + wiring.BOARD_WIDTH + 2.54, 'y2': wiring.BOARD_HEIGHT + 2.54})
    parts = []
    for part in w.parts.values():
        box = _part_box(part)
        parts.append({'id': part.id, 'kind': part.kind, 'board': part.board, 'box': box,
                      'label_x': box[0] + 1.0, 'label_y': box[1] - 1.0,
                      'pins': {n: wiring.hole_xy(h) for n, h in part.pins.items()}})
    labels = []
    for header, (_x0, cols, _n) in wiring.HEADERS.items():
        x, y = wiring.hole_xy(('N', header, 1))
        labels.append({'text': header, 'x': x + 0.6*(cols - 1)*2.54, 'y': y - 2.5})
    nx, ny = wiring.hole_xy(('N', 'CN7', 1))
    labels.append({'text': 'NUCLEO-WL55JC1 headers: check against UM2592, not to scale', 'x': nx + 25, 'y': ny - 6})
    xs = [h['x'] for f in footprints for h in f['holes']]
    ys = [h['y'] for f in footprints for h in f['holes']]
    outline = [min(xs) - MARGIN, min(ys) - MARGIN - 4, max(xs) + MARGIN, max(ys) + MARGIN]
    return {'jumper_nets': [j.id for j in jumpers], 'footprints': footprints, 'boards': boards, 'parts': parts,
            'labels': labels, 'outline': outline,
            'jumpers': [{'id': j.id, 'net': j.net, 'class': w.net_class[j.net],
                         'a': list(wiring.hole_xy(j.a)), 'b': list(wiring.hole_xy(j.b)),
                         'a_name': where(j.a), 'b_name': where(j.b)} for j in jumpers]}


def where(h):
    """A hole as the build sheet names it: 'A:j14' or 'NUCLEO CN10.14'."""
    return f'NUCLEO {h[1]}.{h[2]}' if h[0] == 'N' else f'{h[0]}:{h[1]}{h[2]}'


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
    print(f'make.py: {len(jumpers)} jumpers routed, DRC clean, written to {out}')


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
