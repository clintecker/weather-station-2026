"""Build the bench breadboard map (docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md).

    .venv/bin/python hardware/bench-breadboard-r0/source/make.py sheet [--out DIR]
    .venv/bin/python hardware/bench-breadboard-r0/source/make.py all [--out DIR]
    .venv/bin/python hardware/bench-breadboard-r0/source/make.py layout OUT.json

The two regeneration tiers of build-progression record D4. `sheet` needs no KiCad: it loads
wiring.toml, checks it against the wiring guide (both ways) and the firmware, plans and proves the
jumpers, runs the record's D3 checks (checks.py), and writes build-sheet.md and connections.json. It
also writes the sheet of each frozen earlier revision (HISTORY, source/revisions/) into
revisions/<revision>/, each against the revision before it (record 6.1).
`all` does the same, then writes layout.json, builds the board with KiCad 10's Python, routes the
jumpers with KiCadRoutingTools, runs KiCad's DRC and draws. Any problem stops either before a file is
written to DIR."""
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
try:   # KiCad's paths: only `all` needs them, so `sheet` and `layout` run without KiCad (record D4)
    import kicad_env  # noqa: E402
except ImportError:
    kicad_env = None
import checklist  # noqa: E402
import checks  # noqa: E402
import flying  # noqa: E402
import wiring  # noqa: E402
# build_schematic, models, pcb_read and render (Pillow) load only to draw: the checks and the build
# sheet need the standard library alone (CI runs those tests without Pillow).

DATA = SOURCE/'wiring.toml'
GUIDE = ROOT/'docs'/'hardware'/'bench-station-wiring.md'
FIRMWARE = ROOT/'firmware'   # wiring.FIRMWARE names the node's and the bench link's files under it
NAME = 'bench-breadboard'
CONNECTIONS = 'connections.json'                   # written beside the build sheet (record 6.1)
BASELINE = SOURCE/'baseline-2026-10-29.json'       # the r0 sheet's connections, before change A
# The frozen earlier revisions, oldest first (record 6.1, D7): each the whole model of the bench as that change
# leaves it, kept so its sheet, with its Remove list against the revision before, can be regenerated.
# wiring.toml is the current revision, after the last of these. To start a new revision, copy wiring.toml to
# source/revisions/<its revision>.toml, add that revision here, then bump wiring.toml's `revision`.
REVISIONS = SOURCE/'revisions'
HISTORY = ('bench-bb-r0.1', 'bench-bb-r0.2')
MARGIN = 6.0      # mm around everything, inside the board outline
# The copper only draws the jumpers. 0.3 mm tracks (above the 0.2 mm DRC floor) leave room for the
# board C jumpers into CN10's inner column once ISET and VIN_SENSE also run down to CN8 (0.4 mm did not route).
ROUTE = ['--nets', 'W*', '--grid-step', '0.635', '--track-width', '0.3', '--clearance', '0.2',
         '--layers', 'F.Cu', 'B.Cu']


def frozen_model(revision):
    """The model file of a frozen earlier revision (HISTORY)."""
    return REVISIONS/f'{revision}.toml'


def _revision_problems(w, model):
    """A frozen model's `revision` is its file's name; the current model's is none of the frozen ones."""
    if Path(model) != DATA:
        want = Path(model).stem
        return [] if w.revision == want else [f'{model}: revision {w.revision!r}, expected {want!r} (record 6.1)']
    if w.revision in HISTORY:
        return [f'wiring.toml: revision {w.revision!r} is frozen in source/revisions/: bump it (record 6.1)']
    return []


def checked(model=DATA):
    """The model and its jumpers, or SystemExit naming every problem. The current model (wiring.toml): the
    wiring guide both ways, the firmware pins, the connectivity proof and the record's D3 checks
    (checks.run_all), in that order. A frozen earlier revision (HISTORY): the proof and the D3 checks only,
    since the wiring guide and the firmware describe the current revision."""
    w = wiring.load(model)
    jumpers = wiring.plan_jumpers(w)
    problems = _revision_problems(w, model)
    if Path(model) == DATA:
        problems += (wiring.check_guide(w, GUIDE) + wiring.check_guide_reverse(w, GUIDE)
                     + wiring.check_firmware(w, FIRMWARE))
    problems += wiring.prove(w, jumpers) + checks.run_all(w, jumpers, ROOT)
    if problems:
        raise SystemExit(f'make.py: {Path(model).name}: ' + '\n  '.join(['the model has problems:'] + problems))
    return w, jumpers

def placed_xy(place_mm):
    """A place_mm point (mm from board B's origin, wiring.toml) in the drawing's mm, as wiring.end_xy places it."""
    return (wiring.BOARD_X['B'] + place_mm[0], place_mm[1])


def _anchor(part):
    """Where a part's models hang from: the centre of its pins, or its place point off the breadboard."""
    if part.place_mm is not None:
        return placed_xy(part.place_mm)
    pins = [wiring.hole_xy(h) for h in part.pins.values()]
    return sum(x for x, _ in pins)/len(pins), sum(y for _, y in pins)/len(pins)


def _part_models(models, part):
    """The 3D footprints of one part: KiCad models, boxes and the maker's model."""
    cx, cy = _anchor(part)
    off = part.place_mm is not None   # on the plate (z 0), not in the breadboard
    out = []
    for i, (file, rot, box) in enumerate(models.models_for(part)):
        ref = f'3D_{part.id}_{i}'
        if box is None:   # KiCad's models run to the right from their pin 1: anchor on the left-most pin
            x, y = (cx, cy) if off else min(wiring.hole_xy(h) for h in part.pins.values())
            out.append({'ref': ref, 'x': x, 'y': y, 'box': None,
                        'models': [{'file': f'{models.KICAD3D}/{file}', 'z': 0.0 if off else models.BREADBOARD_H,
                                    'rot': rot}]})
        else:
            out.append({'ref': ref, 'x': cx + box[0], 'y': cy + box[1], 'box': list(box),
                        'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': box[5], 'rot': 0}]})
    real = models.real_model(part.id)
    if real:   # its left-hand header hole on the pin it carries, the board on its header
        file, (hx, hy), pin = real
        x, y = wiring.hole_xy(part.pins[pin])
        out.append({'ref': f'3D_{part.id}_maker', 'x': x, 'y': y, 'box': None,
                    'models': [{'file': file, 'z': models.HEADER_Z, 'rot': 0, 'dx': -hx, 'dy': -hy}]})
    if part.id == 'PACK' and (models.VENDOR/models.PACK_MODEL[0]).exists():   # on the plate, its plug at place_mm
        file, (mx, my) = models.PACK_MODEL
        dx, dy = models.OFF_BOARD['PACK'][0][:2]
        out.append({'ref': '3D_PACK_maker', 'x': cx + dx, 'y': cy + dy, 'box': None,
                    'models': [{'file': f'${{KIPRJMOD}}/../../vendor/cad/{file}', 'z': 0.0, 'rot': 0,
                                'dx': -mx, 'dy': -my}]})
    return out


def model_footprints(w):
    """The 3D models of each part and each joint, on footprints with no pads: [{ref, x, y, models: [{file,
    z, rot}]}]. A box's VRML file is models/<ref>.wrl next to the board."""
    import models
    out = []
    for part in w.parts.values():
        out += _part_models(models, part)
    for joint in w.joints.values():   # a lever connector on the plate beside board B
        cx, cy = joint_centre(w, joint)
        for i, box in enumerate(models.joint_boxes(joint, wiring.JOINT_PITCH)):
            ref = f'3D_{joint.id}_{i}'
            out.append({'ref': ref, 'x': cx + box[0], 'y': cy + box[1], 'box': list(box),
                        'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': box[5], 'rot': 0}]})
    return out


def hole_name(h):
    return f'{h[1]}{h[2]}' if h[0] != 'N' else f'{h[1]}.{h[2]}'


def _part_box(part):
    """A part's outline (x1, y1, x2, y2): around its pins, or for a part off the breadboard its body there."""
    if part.place_mm is not None:
        return off_board_rect(part)
    xs, ys = zip(*(wiring.hole_xy(h) for h in part.pins.values()), strict=False)
    return [min(xs) - 1.6, min(ys) - 1.6, max(xs) + 1.6, max(ys) + 1.6]


RESISTOR_SPAN = 10.16   # mm: KiCad's axial resistor model, pin 1 to pin 2 (models.KICAD)


def off_board_rect(part):
    """The outline of a part off the breadboard on the plate: its first box in models.OFF_BOARD (or the
    default), or an axial resistor's body from its place point."""
    import models
    x, y = placed_xy(part.place_mm)
    if models._is_resistor(part.kind.lower()):
        return [x - 1.25, y - 1.25, x + RESISTOR_SPAN + 1.25, y + 1.25]   # its 2.5 mm body
    dx, dy, w, d = models.OFF_BOARD.get(part.id, [models.OFF_BOARD_DEFAULT])[0][:4]
    return [x + dx - w/2, y + dy - d/2, x + dx + w/2, y + dy + d/2]


def joint_xy(w, joint):
    """Each position of a joint as wiring.end_xy draws it, in order from position 1."""
    return [wiring.end_xy(w, f'J:{joint.id}.{n}') for n in range(1, joint.positions + 1)]


def joint_centre(w, joint):
    xs, ys = zip(*joint_xy(w, joint), strict=True)
    return (sum(xs)/len(xs), sum(ys)/len(ys))


def joint_rect(w, joint):
    """A joint's drawn outline: its positions wiring.JOINT_PITCH apart, models.JOINT_D deep (the 3D box)."""
    import models
    cx, cy = joint_centre(w, joint)
    w, d = joint.positions*wiring.JOINT_PITCH, models.JOINT_D
    return [cx - w/2, cy - d/2, cx + w/2, cy + d/2]


def joint_rows_layout(w):
    """layout.json's joints: id, kind, place_mm, positions and each position's xy, the outline, the net."""
    out = []
    for joint in w.joints.values():
        box = joint_rect(w, joint)
        nets = sorted(n for n, ms in w.nets.items() if f'J:{joint.id}' in ms)
        out.append({'id': joint.id, 'kind': joint.kind, 'place_mm': list(joint.place_mm), 'positions': joint.positions,
                    'xy': [list(p) for p in joint_xy(w, joint)], 'box': box, 'net': ', '.join(nets),
                    'domain': joint.domain, 'label_x': box[0], 'label_y': box[1] - 1.0})
    return out


INSULATED_REACH = 8.0   # mm: where a folded-back lead end is drawn, toward -y (off the board) from its other end


def lead_end(w, end, other):
    """(xy, kind) of a lead end as drawn: wiring.end_xy; a NUCLEO pin at its header position; an insulated
    end INSULATED_REACH from the other end. kind is parse_end's, with a terminal of a part off the
    breadboard as 'off_board' (models.END_Z gives each its height)."""
    e = wiring.parse_end(w, end)
    if e[0] == 'insulated':
        x, y = lead_end(w, other, end)[0]
        return [x, y - INSULATED_REACH], 'insulated'
    if e[0] == 'nucleo':
        return list(wiring.hole_xy(e[1])), 'nucleo'
    kind = e[0]
    if kind == 'terminal' and w.parts[end.split('.', 1)[0]].place_mm is not None:
        kind = 'off_board'
    return list(wiring.end_xy(w, end)), kind


def lead_layout(w, k):
    (a, a_end), (b, b_end) = lead_end(w, k.a, k.b), lead_end(w, k.b, k.a)
    return {'id': k.id, 'net': k.net, 'class': w.net_class[k.net], 'role': k.role, 'kind': k.kind, 'gauge': k.gauge,
            'length_mm': k.length_mm, 'insulated': k.insulated, 'a': a, 'b': b, 'a_end': a_end, 'b_end': b_end,
            'a_name': k.a, 'b_name': k.b}


def _outline(w, footprints, joints, leads):
    """The board outline (Edge_Cuts): every hole, breakout body, joint, off-board part and lead end, MARGIN
    around them, and room above for the labels."""
    xs = [h['x'] for f in footprints for h in f['holes']] + [p[0] for k in leads for p in (k['a'], k['b'])]
    ys = [h['y'] for f in footprints for h in f['holes']] + [p[1] for k in leads for p in (k['a'], k['b'])]
    rects = ([wiring.body_rect(p) for p in w.parts.values() if p.body is not None] + [j['box'] for j in joints]
             + [off_board_rect(p) for p in w.parts.values() if p.place_mm is not None])
    xs += [r[i] for r in rects for i in (0, 2)]
    ys += [r[i] for r in rects for i in (1, 3)]
    return [min(xs) - MARGIN, min(ys) - MARGIN - 4, max(xs) + MARGIN, max(ys) + MARGIN]


def _labels():
    labels = []
    for header, (_x0, cols, _n) in wiring.HEADERS.items():   # CN7, CN6, CN8, CN5, CN10
        x, y = wiring.hole_xy(('N', header, 1))
        labels.append({'text': header, 'x': x + 0.6*(cols - 1)*2.54, 'y': y - 2.5})
    # The column numbers printed on the board, below row j's rails: centred on the column (KiCad centres
    # its text; render.py centres labels marked so), past the 3D breadboard body's edge (BOARD_HEIGHT + 4).
    for board in wiring.BOARDS:
        for col in (1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 63):
            x, _y = wiring.hole_xy((board, 'R+', col))
            labels.append({'text': str(col), 'x': x, 'y': wiring.BOARD_HEIGHT + 6.0, 'centre': True})
    nx, _ny = wiring.hole_xy(('N', 'CN7', 1))
    bottom = max(wiring.hole_xy(('N', h, n))[1] for h, (_x, _c, n) in wiring.HEADERS.items())
    labels.append({'text': 'NUCLEO-WL55JC1 headers: check against UM2592, not to scale', 'x': nx + 25, 'y': bottom + 5})
    return labels


def layout(w, jumpers):
    """Everything build_pcb.py and the renderer draw, in mm, with the wiring.toml blob it was drawn from
    (model_hash, record D4)."""
    end_net = {h: j.id for j in jumpers for h in (j.a, j.b)}
    paths = flying.plan(jumpers)
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
        off = part.place_mm is not None
        parts.append({'id': part.id, 'kind': part.kind, 'board': part.board, 'box': box, 'off_board': part.off_board,
                      'place_mm': list(part.place_mm) if off else None,
                      'body': box if off else wiring.body_rect(part),
                      'label_x': box[0] + 1.0, 'label_y': box[1] - 1.0,
                      'pins': ({t: list(placed_xy(part.place_mm)) for t in part.terminals} if off
                               else {n: wiring.hole_xy(h) for n, h in part.pins.items()})})
    joints = joint_rows_layout(w)
    leads = [lead_layout(w, k) for k in w.leads]   # off the breadboard, terminal to terminal: drawn straight
    return {'model_hash': checklist.blob_sha1(DATA), 'revision': w.revision,
            'jumper_nets': [j.id for j in jumpers], 'footprints': footprints, 'boards': boards, 'parts': parts,
            'joints': joints, 'labels': _labels(), 'outline': _outline(w, footprints, joints, leads), 'leads': leads,
            'jumpers': [{'id': j.id, 'net': j.net, 'class': w.net_class[j.net],
                         'a': list(wiring.hole_xy(j.a)), 'b': list(wiring.hole_xy(j.b)),
                         'a_name': where(j.a), 'b_name': where(j.b),
                         # A wire between boards, or to the NUCLEO, hops over in the air: drawn down
                         # and over (flying.py) instead of along the router's path.
                         'path': [[round(x, 4), round(y, 4)] for x, y in paths.get(j.id, [])]} for j in jumpers]}


def where(h):
    """A hole as the build sheet names it: 'A:j14' or 'NUCLEO CN10.14'."""
    return f'NUCLEO {h[1]}.{h[2]}' if h[0] == 'N' else f'{h[0]}:{h[1]}{h[2]}'


def end_name(end):
    """A lead end as the build sheet names it: a NUCLEO pin as where() names it, anything else as written."""
    return f'NUCLEO {end[2:]}' if end.startswith('N:') else end


def end_words(end):
    """A lead end in words, for the instructions: 'J:WAGO_STAR.3' is 'WAGO_STAR position 3'."""
    if end.startswith('J:'):
        joint, _, pos = end[2:].partition('.')
        return f'{joint} position {pos}' if pos else joint
    return end_name(end)


def nucleo_jumpers(jumpers, nets):
    """The ids of the jumpers that take these nets to the NUCLEO."""
    return [j.id for j in jumpers if j.net in nets and 'N' in (j.a[0], j.b[0])]


STAGE_TITLE = {0: 'Board A', 1: 'Board B', 2: 'Board C', 3: 'Between the boards', 4: 'To the NUCLEO'}
NO_5V = ('CN6.5', 'CN6.8', 'CN7.18', 'CN7.24', 'CN7.6', 'CN10.8')   # record N1, N3 and section 4.2
# The ARDUINO names of the signal headers (UM2592 Rev 4 Table 17): CN8 pins 1-6 are A0-A5, CN9 pins 1-8
# D0-D7, CN5 pins 1-6 D8-D13 and pins 9-10 D14-D15 (CN5.7 is GND and CN5.8 AVDD).
ARDUINO = {'CN8': ('A', 0), 'CN9': ('D', 0), 'CN5': ('D', 8)}    # header -> (name, number of pin 1)
ARDUINO_PINS = {('CN5', 9): 'D14', ('CN5', 10): 'D15'}           # the names that skip GND and AVDD


# ---- connections.json and the changes section (record D4, 6.1, section 4.4) ----

def strip_pins(w):
    """strip -> the 'PART.PIN' names of the part pins in it."""
    out = {}
    for part in w.parts.values():
        for name, h in part.pins.items():
            out.setdefault(wiring.strip(h, w.split_rails), []).append(f'{part.id}.{name}')
    return out


def pins_at(w, pins, hole):
    """The part pins on a hole's strip, as one string ('' for a NUCLEO pin or an empty strip)."""
    if hole is None or hole[0] == 'N':
        return ''
    return ', '.join(sorted(pins.get(wiring.strip(hole, w.split_rails), [])))


def end_hole(w, end):
    """The hole of a lead end in a hole or a part's hole pin, else None."""
    e = wiring.parse_end(w, end)
    return e[1] if e[0] in ('hole', 'pin') else None


def link_of(w, j):
    """The [[link]] a jumper carries: the one whose two members' strips are the jumper's, or None."""
    ends = {wiring.strip(j.a, w.split_rails), wiring.strip(j.b, w.split_rails)}
    for k in w.link_info:
        if {wiring.strip(wiring.member_hole(w, m), w.split_rails) for m in (k.a, k.b)} == ends:
            return k
    return None


def connections(w, jumpers):
    """Every jumper, link and lead as {kind, net, a, b, id?, w?, a_at, b_at}: the list connections.json
    keeps. a_at and b_at name the part pins on each hole end's strip, so a removed wire can be found."""
    pins = strip_pins(w)
    out = []
    for j in jumpers:
        link = link_of(w, j)
        c = {'kind': 'link' if link else 'jumper', 'net': j.net, 'a': where(j.a), 'b': where(j.b), 'w': j.id,
             'a_at': pins_at(w, pins, j.a), 'b_at': pins_at(w, pins, j.b)}
        if link:
            c['id'] = link.id
        out.append(c)
    for k in w.leads:
        out.append({'kind': 'lead', 'id': k.id, 'net': k.net, 'a': end_name(k.a), 'b': end_name(k.b),
                    'a_at': pins_at(w, pins, end_hole(w, k.a)), 'b_at': pins_at(w, pins, end_hole(w, k.b))})
    return out


def load_baseline(revision):
    """{revision, connections} of the revision before this one (record 6.1), regenerated from its model: the
    frozen revision before it in HISTORY; for any revision not in HISTORY (the current wiring.toml), the last
    frozen one; before the first, the bootstrap baseline (source/baseline-2026-10-29.json, the r0 sheet the
    bench was built from, before change A)."""
    i = HISTORY.index(revision) if revision in HISTORY else len(HISTORY)
    if i == 0:
        boot = json.loads(BASELINE.read_text())
        return {'revision': boot['revision'], 'connections': boot['connections']}
    w = wiring.load(frozen_model(HISTORY[i - 1]))
    return {'revision': w.revision, 'connections': connections(w, wiring.plan_jumpers(w))}


def _baseline_source(baseline):
    if baseline['revision'] in HISTORY:
        return f'the frozen model `source/revisions/{baseline["revision"]}.toml`'
    return '`source/baseline-2026-10-29.json`, the r0 sheet the bench was built from'


def _same(c):
    """What makes two connections the same wire: a lead or not, and its two ends."""
    return (c['kind'] == 'lead', frozenset((c['a'], c['b'])))


def changes(current, previous):
    """(removed, added): the connections in only one of the two lists, each in its list's order."""
    now, before = {_same(c) for c in current}, {_same(c) for c in previous}
    return [c for c in previous if _same(c) not in now], [c for c in current if _same(c) not in before]


def _change_end(c, side):
    return f'{c[side]} ({c[side + "_at"]})' if c.get(side + '_at') else c[side]


def _change_table(title, items):
    out = ['', f'### {title}', '']
    if not items:
        return out + ['Nothing.']
    out += ['| What | Net | From | To |', '|---|---|---|---|']
    for c in items:
        what = c['kind'] if c['kind'] == 'jumper' else f'{c["kind"]} {c["id"]}'
        out.append(f'| {what} | {c["net"]} | {_change_end(c, "a")} | {_change_end(c, "b")} |')
    return out


def change_rows(w, jumpers, baseline):
    """The 'Changes from the previous revision' section: by net and ends, never by W-number."""
    removed, added = changes(connections(w, jumpers), baseline['connections'])
    return ['', f'## Changes from the previous revision ({baseline["revision"]})', '',
            'To rebuild the bench from the previous sheet: first take out everything under **Remove**, then fit '
            'everything under **Add**. Each end is a hole, a NUCLEO pin, a joint position or a part terminal; '
            'the part pins on a hole\'s strip follow it in brackets. W-numbers change on every regeneration, so '
            f'this list never uses them. Parts that moved are in section 1. The previous revision is '
            f'{_baseline_source(baseline)}.',
            *_change_table('Remove', removed), *_change_table('Add', added)]


# ---- the sheet's header: revision and hashes (record D4) ----

def render_hash(out):
    """The wiring.toml blob the drawings were made from (layout.json's model_hash), or None."""
    try:
        return json.loads((Path(out)/'layout.json').read_text()).get('model_hash')
    except FileNotFoundError:
        return None


def header_rows(w, out, data=DATA):
    model = checklist.blob_sha1(data)
    if Path(data) != DATA:
        return ['| Model | |', '|---|---|', f'| Revision | {w.revision} (frozen) |',
                f'| `source/revisions/{Path(data).name}` git blob | `{model}` |',
                '| Renders | none: `make.py all` draws the current revision only |']
    drawn = render_hash(out)
    rows = ['| Model | |', '|---|---|', f'| Revision | {w.revision} |', f'| `wiring.toml` git blob | `{model}` |',
            f'| Renders (`layout.json` model_hash) | {f"`{drawn}`" if drawn else "renders predate hashing"} |']
    if drawn and drawn != model:
        rows += ['', f'**Renders lag the model:** the drawings and renders are of wiring.toml `{drawn}`; this sheet '
                 'is of the blob above. Build from this sheet; `make.py all` redraws them.']
    return rows


# ---- parts, jumpers, leads, joints ----

def part_pins(w, part):
    """A part's Pins cell: hole pins by hole, terminals by the leads that end on them."""
    cells = [f'{n}: {where(h)[2:]}' for n, h in part.pins.items()]
    if part.off_board and part.pins:
        cells = [f'{n}: {", ".join(lead_ids(w, f"{part.id}.{n}"))}' for n in part.pins]
    terms = [f'{t}: {", ".join(lead_ids(w, f"{part.id}.{t}")) or "nothing"}' for t in part.terminals]
    text = ', '.join(cells)
    if terms:
        text += ('; ' if text else '') + 'terminals (leads only): ' + ', '.join(terms)
    return text


def part_rows(w):
    out = ['', '## 1. Parts', '', '| Part | What | Board | Pins (pin: hole) | Pin order from |', '|---|---|---|---|---|']
    for part in w.parts.values():
        board = f'off board, beside {part.board}' if part.place_mm else part.board
        out.append(f'| {part.id} | {part.kind} | {board} | {part_pins(w, part)} | {part.source} |')
    return out


# The pre-cut jumper kit on the bench (BOJACK, 14 lengths, 2-125 mm): each length is a span in holes at
# 2.54 mm, labelled in round mm (2 = 1 hole, 22 = 9 holes, 75 = 30 holes, 125 = 50 holes).
KIT_SPANS = {1: 2, 2: 5, 3: 7, 4: 10, 5: 12, 6: 15, 7: 17, 8: 20, 9: 22, 10: 25, 20: 50, 30: 75, 40: 100, 50: 125}
KIT_SLACK = 0.2   # holes: a span this much over a kit size still takes that size (the legs flex)
KIT_BOW = 1.2     # holes: a kit jumper longer than the span by more than this bows off the board, so cut one


def kit_length(j):
    """The kit jumper for a breadboard-to-breadboard jumper, as its label ('22 mm'): the next size up for a
    diagonal, or 'cut to fit' with the span when that size would bow (KIT_BOW) or there is none. The NUCLEO
    jumpers say what they are instead."""
    if j.b[0] == 'N' or j.a[0] == 'N':
        h = j.a if j.a[0] == 'N' else j.b
        return 'Dupont, about 30 cm' if h[1] not in wiring.FEMALE else 'cut to fit from 22 AWG solid'
    if j.a[0] != j.b[0]:   # hole_xy adds each board's BOARD_X: a length across boards would include it
        raise ValueError(f'{j.id} joins boards {j.a[0]} and {j.b[0]}: no kit length for that')
    (ax, ay), (bx, by) = wiring.hole_xy(j.a), wiring.hole_xy(j.b)
    span = ((ax - bx)**2 + (ay - by)**2)**0.5 / wiring.PITCH
    fit = [n for n in KIT_SPANS if span - KIT_SLACK <= n <= span + KIT_BOW]
    if fit:
        return f'{KIT_SPANS[min(fit)]} mm'
    return f'cut to fit: {span:.1f} holes ({span*wiring.PITCH:.0f} mm between the legs)'


def cut_list(jumpers):
    """How many of each kit length the sheet uses, shortest first, then the ones cut or Dupont."""
    counts = {}
    for j in jumpers:
        counts[kit_length(j)] = counts.get(kit_length(j), 0) + 1
    order = sorted(counts, key=lambda k: (not k[0].isdigit(), int(k.split()[0]) if k[0].isdigit() else 0, k))
    return ['', '### Cut list', '', '| Length | Jumpers |', '|---|---:|'] + [f'| {k} | {counts[k]} |' for k in order]


def jumper_rows(w, jumpers):
    colours = ', '.join(f'{c} {name}' for c, name in wiring.NET_CLASSES.items())
    oled = ', '.join(nucleo_jumpers(jumpers, OLED_NETS))
    dupont = (f' One exception: the OLED\'s signal jumpers from board C to CN10 ({oled}) are female-to-male Dupont '
              'jumpers of about 30 cm on the morpho\'s male pins, bench OLED only (record N3; the OLED wires bench '
              'check).') if oled else ''
    morpho = ', '.join(f'{j.id} ({j.net}, {h[1]}.{h[2]})' for j, h in morpho_signals(jumpers))
    if morpho:
        dupont += (f' Another: the station signals still on the morpho\'s male pins ({morpho}) are female-to-male Dupont '
                   'jumpers too, the female end on the pin: a solid wire cannot be pushed onto a male pin. A later '
                   'revision moves them to the ARDUINO female headers as solid 22 AWG (record 4.5, change B; the '
                   'morpho signal pins bench check).')
    out = ['', '## 2. Jumpers', '', f'Each jumper is one wire between the two holes: pre-cut solid 22 AWG laid flat '
           f'(record H3).{dupont} Length is the kit jumper to use (kit_length() in make.py: the BOJACK kit\'s 14 sizes, '
           f'the next size up for a diagonal); an ARDUINO-header jumper is cut to fit once the base plate fixes '
           f'where the NUCLEO sits (record H7: at most 200 mm). Colour by class: {colours}. A link is a jumper '
           f'the model names by a stable id.']
    stage = None
    for j in jumpers:
        s = wiring.jumper_stage(j)[0]
        if s != stage:
            stage = s
            out += ['', f'### {STAGE_TITLE[s]}', '', '| Jumper | From | To | Length | Net | Class | Link |',
                    '|---|---|---|---|---|---|---|']
        link = link_of(w, j)
        out.append(f'| {j.id} | {where(j.a)} | {where(j.b)} | {kit_length(j)} | {j.net} | {w.net_class[j.net]} | '
                   f'{link.id if link else ""} |')
    return out + cut_list(jumpers)


def lead_ids(w, member):
    """The ids of the leads that end on a part pin or terminal."""
    return [k.id for k in w.leads if member in (k.a, k.b)]


def lead_mohm(k):
    """A lead's copper resistance in mOhm, from its gauge and length_mm (a #1131 pigtail assumed 26 AWG, P7)."""
    d = 0.127 * 92 ** ((36 - k.gauge)/39)          # the gauge's diameter, mm
    area = 3.14159265 * d * d / 4                   # mm2
    return 17.24 / area * k.length_mm / 1000        # copper: 17.24 mOhm mm2 / m


def loop_leads(w):
    """The leads of the battery loop: those on the PATH_POS and PATH_NEG segments (record M6)."""
    by_id = {k.id: k for k in w.leads}
    seg = checks.power_path_segments(w)
    return [by_id[i] for name in ('PATH_POS', 'PATH_NEG') for kind, i in seg.get(name, ()) if kind == 'lead']


def _dash(value, fmt='{}'):
    return '-' if value is None else fmt.format(value)


def lead_rows(w):
    """The build sheet's leads, apart from the jumpers: every [[lead]] once, with its record D2 fields."""
    if not w.leads:
        return []
    out = ['', '## 3. Leads', '',
           'Wires off the breadboard (record D2). A force lead ends in a lever clamp, a screw terminal or a JST '
           'socket; only sense leads, the OLED\'s supply pair and the P1 regulator chain (record P1) end in a '
           'breadboard hole or on a NUCLEO pin. Stranded ends go into a lever clamp stripped and twisted, the '
           'screw terminals take solid 22 AWG only (record P7). Cut each lead to its length or shorter: every '
           'span of the battery path counts (section 5, check 7). An `insulated` end is folded back under '
           'heat-shrink.', '',
           '| Lead | Role | Wire | Length | Max mA | From | To | Net | Segment | Exception | Note |',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    for k in w.leads:
        wire = f'{k.gauge} AWG {k.kind}' + (', one end insulated' if k.insulated else '')
        out.append(f'| {k.id} | {k.role} | {wire} | {k.length_mm:g} mm | {_dash(k.max_ma, "{:g}")} | '
                   f'{end_name(k.a)} | {end_name(k.b)} | {k.net} | {_dash(k.segment)} | {_dash(k.exception)} | {k.note} |')
    return out


def joint_positions(w, joint):
    """'1: L_PACK_POS; 2: ...; 5: spare': what lands in each position of a joint."""
    cells = []
    for n in range(1, joint.positions + 1):
        ids = [k.id for k in w.leads if f'J:{joint.id}.{n}' in (k.a, k.b)]
        cells.append(f'{n}: {", ".join(ids) or "spare"}')
    return '; '.join(cells)


def joint_rows(w):
    """The off-board lever connectors (record D2): every [[joint]] once, position by position."""
    if not w.joints:
        return []
    out = ['', '## 4. Joints', '',
           'Lever connectors off the breadboard, glued in a row beside board B (record P3-P7, H1). A joint is '
           'one node. One lead end per position; close every lever and pull-test each lead by hand.', '',
           '| Joint | Kind | Net | Positions | Note |', '|---|---|---|---|---|']
    for joint in w.joints.values():
        nets = ', '.join(n for n, ms in w.nets.items() if f'J:{joint.id}' in ms)
        out.append(f'| {joint.id} | {joint.kind} | {nets} | {joint_positions(w, joint)} | {joint.note} |')
    return out


# ---- the power-path table and the checklist (record M5, M6, P8, section 4.3) ----

def _steps(route):
    return ' > '.join(i for _kind, i in route)


def path_rows(w):
    """Section 5: each M6 segment with its P8 budget, the implied drops and blank measured columns."""
    by_id = {k.id: k for k in w.leads}
    out = ['', '## 5. Power path', '',
           'The battery-path segments (record M6) and their budgets at 1 A (record P8). At 1 A (C12-C14) fill '
           'the measured columns: mOhm = the meter\'s mV / the INA228 current in A. The lead copper is estimated '
           'from each lead\'s gauge and length.', '',
           '| Segment | Steps | Budget mOhm | Implied mV at 38 mA | Implied mV at 1 A | Lead copper mOhm | '
           'Measured mV | I (A) | mOhm |', '|---|---|---|---|---|---|---|---|---|']
    for seg, route in checks.power_path_segments(w).items():
        copper = sum(lead_mohm(by_id[i]) for kind, i in route if kind == 'lead')
        budget = checklist.BUDGETS.get(seg)
        if budget is None:
            cells = f'flag: drop - dV0 > {checklist.PATH_CELL_OUT_FLAG_MV:g} mV | - | -'
        else:
            cells = (f'{budget:g} | {checklist.implied_mv(budget, checklist.SCREEN_MA):.2f} | '
                     f'{checklist.implied_mv(budget, 1000.0):g}')
        out.append(f'| {seg} | {_steps(route)} | {cells} | {copper:.1f} |  |  |  |')
    pack = sum(checklist.BUDGETS[s] for s in checklist.PACK_SPANS)
    out.append(f'| R_pack | {" + ".join(checklist.PACK_SPANS)}, measured (C14): step 1 exit 5, record M4 | {pack:g} | '
               f'{checklist.implied_mv(pack, checklist.SCREEN_MA):.2f} | {checklist.implied_mv(pack, 1000.0):g} | - |  |  |  |')
    return out + ['', f'Coverage: {checklist.COVERAGE_NOTE}.']


OPS = {'le': '<=', 'lt': '<', 'ge': '>=', 'abs_le': 'within +-'}
LIMIT_NAMES = {'ph': 'each JST PH mating', 'clamp': 'each clamp', 'screw': 'each screw', 'pack_span': 'each pack-side span'}
NOTE_STATES_LIMIT = ('within', 'no step', 'no reset', 'open with', 'VBUS >=')   # a note that already says the limit


def limit_text(row):
    """A checklist row's limit in words, from its limit_value, unit and op ('' when the note says it)."""
    v, unit, op = row['limit_value'], row['unit'], row['op']
    if op in ('text', 'by_signal', 'record'):
        return '' if v in ('pass', None) or isinstance(v, dict) else str(v)
    if op == 'step':
        return f'no step >= {v:g} {unit}'
    if op == 'pct_mA':
        return f'within {v[0]:g} % + {v[1]:g} mA'
    if isinstance(v, dict):
        return ', '.join(f'{LIMIT_NAMES.get(k, k)} {OPS[op]} {x:g} {unit}' for k, x in v.items())
    return f'{OPS[op]} {v:g} {unit}'.replace('+- ', '+-')


def pass_text(row):
    """A checklist row's Pass cell: its limit, then the rest of the record's Pass cell (the note)."""
    note = row['note']
    if note.startswith(NOTE_STATES_LIMIT):
        return note
    return '; '.join(t for t in (limit_text(row), note) if t)


def _check_table(rows):
    out = ['| # | When | Condition | Measure | Pass |', '|---|---|---|---|---|']
    return out + [f'| {r["id"]} | {r["when"]} | {r["condition"]} | {r["measure"]} | {pass_text(r)} |' for r in rows]


def checklist_rows():
    """Section 6: the pre-run checklist C1-C23 (record 4.3), mode-A rows then the mode-B rows."""
    mode_a = [r for r in checklist.CHECKS if r['mode'] == 'A']
    mode_b = [r for r in checklist.CHECKS if r['mode'] == 'B']
    return ['', '## 6. Pre-run checklist (C1-C23)', '',
            f'Meter: {checklist.METER}, read directly (record 7.1 Q2). Back-probe the pack plug by sliding the probe '
            'tip along the wire into the back of the housing; never pull the plug to probe it. The 1 A limits are '
            'in mOhm: the mV limit is the mOhm figure times the INA228 current in A (0.8-1.0 A). Every reading '
            'goes into the run\'s preflight block (record D6, `tools/preflight.py`). When a span fails, measure '
            'joint by joint (C14) to find the bad one.', '', '### Mode A', '', *_check_table(mode_a), '',
            '### Mode B', '', 'The station running from the regulator (section 7: NUCLEO USB unplugged, SHUNT fitted, '
            '100 ohm load out, OLED VCC lead unplugged), the meter on min/max across at least 5 radio TX bursts.',
            '', *_check_table(mode_b), '',
            f'Before every mode-A run: {", ".join(checklist.REQUIRED_MODE_A)}. Before every mode-B run: '
            f'{", ".join(checklist.REQUIRED_MODE_B)}. After every rewire and at every step exit (1 A charge): '
            f'{", ".join(checklist.REQUIRED_1A)}.']


def mode_rows(w):
    """Section 7: the mode A to B and B to A steps, ground untouched (record 4.4)."""
    levers = [end_words(e) for k in w.leads if any(x.startswith('RLOAD.') for x in (k.a, k.b))
              for e in (k.a, k.b) if e.startswith('J:')]
    oled = next((k.id for k in w.leads if k.role == 'supply' and 'N:CN7.16' in (k.a, k.b)), 'the OLED VCC lead')
    ret = next((k.id for k in w.leads if 'N:CN6.7' in (k.a, k.b)), 'the CN6.7 lead')
    return ['', '## 7. Mode A and mode B', '',
            'Mode A (daily, the NUCLEO on USB) is drawn: the BATTERY POWER shunt open, the 100 ohm load fitted, the '
            'OLED on its own supply pair. A mode change never touches ground.', '',
            '**Mode A to B:**', '', '1. Unplug the NUCLEO\'s USB.',
            f'2. Open the load\'s two levers ({" and ".join(levers) or "OUT and STAR"}) and take the 100 ohm load out.',
            f'3. Unplug the OLED\'s VCC lead ({oled}) from CN7.16.', '4. Fit the BATTERY POWER shunt (SHUNT).', '',
            '**Mode B to A:** the reverse, the shunt out before the USB goes in.', '',
            '1. Take the BATTERY POWER shunt out.', f'2. Plug the OLED\'s VCC lead ({oled}) back into CN7.16.',
            '3. Refit the 100 ohm load and close its two levers.', '4. Plug the NUCLEO\'s USB in.', '',
            f'The TIE ({checks.TIE}) and the CN6.7 lead ({ret}) never move.']


# ---- the bench checks ----

# Record 4.4 step 3, P3 and 1.4: the charger's solder jumpers, checked at step 1 (not first at step 1b's B1),
# because EN2 low would hold the USB-C input to 100 or 500 mA and C12-C18 would never see the 1 A charge.
CHARGER_JUMPERS = (
    '- **Charger jumpers** (record 4.4 step 3, P3, 1.4; charger unpowered, pack unplugged): on the #4755 the 1A '
    'solder jumper is closed and the 0.5A and 1.5A solder jumpers are open: never the 1.5A setting on this pack. '
    'Record which way EN1 (SJ2) and EN2 (SJ1) are set: expected **EN2 = 1, EN1 = 0** (the R_ILIM input limit, no '
    'VIN-DPM; SLUS810 table 7-2). EN2 low holds the USB-C input to the 100 or 500 mA VIN-DPM modes, so C12-C18 '
    'and power check 7 never see the 0.8-1.0 A charge: stop and record it. EN1 = EN2 = 1 is standby, no charge.')


def bench_rows(w, jumpers):
    """Bench checks before power: part notes, module preparation, the NUCLEO header rules."""
    out = ['', '## Bench checks', '', 'Do these before you connect power.', '']
    for part in w.parts.values():
        if part.source == 'bench check' or part.note:
            out.append(f'- **{part.id}** ({part.kind}): {part.note or "check the pin order on the part"}.')
    to_3v3 = ' and '.join(j.id for j in jumpers if 'N' in (j.a[0], j.b[0]) and ('N', 'CN6', 4) in (j.a, j.b))
    return out + [
        CHARGER_JUMPERS,
        '- **BOB-14021 preparation** (module preparation, record H5, 7.1 Q6): the BOB-14021 comes as a panel of '
        'two boards; separate it into its two boards first (BOBW for the wind cable, BOBR for the rain cable). '
        'Then solder one PRT-00132 jack and one 6-pin header onto each board before it goes into the breadboard. '
        'Then the per-conductor continuity '
        'check, the Fluke 87V on continuity, the meter\'s cable plugged into the jack: BOBW pins 3 and 4 close and '
        'open as the cups turn, pins 2 and 5 read a resistance that changes with the vane\'s position; BOBR pins 3 '
        'and 4 close as the bucket tips; pins 1 and 6 read open to every other pin. The meter cables are never cut.',
        f'- **3V3, not 5 V:** {to_3v3} goes to CN6.4 (3V3). On the Arduino power header the next pin, '
        'CN6.5, is 5 V: check the hole against UM2592 Table 17 before you push the wire in.',
        f'- **NO 5V tape** (record N3): Kapton labelled "NO 5V" over {", ".join(NO_5V[:2])} (sockets) and '
        f'{", ".join(NO_5V[2:])} (pins). CN6.2 (IOREF) and CN5.8 (AVDD) stay empty.',
        '- **Rails:** some 830-point boards split each rail at the centre. If yours do, set '
        '`split_rails = true` in `source/wiring.toml` and regenerate: the plan then bridges the halves.',
        '- **NUCLEO headers:** the positions follow the wiring guide. Tick its section 6 checklist '
        'against UM2592 first. The drawing of the headers is not to scale.',
        *arduino_check(w, jumpers), *morpho_check(w, jumpers), oled_check(w, jumpers)]


OLED_NETS = ('OLED_SCLK', 'OLED_DIN', 'OLED_CS', 'OLED_DC', 'OLED_RST')
MORPHO = ('CN7', 'CN10')   # the morpho headers: male pins (UM2592 Table 18)


def morpho_signals(jumpers):
    """[(jumper, NUCLEO end)] for the jumpers on the morpho's male pins other than the OLED's: the station
    signals that stay there until change B (record 4.5), sorted by header and pin."""
    into = [(j, h) for j, h in _into(jumpers, MORPHO) if j.net not in OLED_NETS]
    return sorted(into, key=lambda t: (t[1][1], t[1][2]))


def morpho_check(w, jumpers):
    """A bench check for the station-signal jumpers on the morpho male pins, with their ARDUINO aliases
    ([nucleo] ties) that stay empty (record N1, N3)."""
    into = morpho_signals(jumpers)
    if not into:
        return []
    pins = ', '.join(f'{j.id} to {h[1]}.{h[2]} ({w.mcu.get(j.net)}, {j.net})' for j, h in into)
    alias = _aliases(w, into)
    empty = f' Their ARDUINO aliases ({", ".join(alias)}) stay empty: one landing per MCU pin (record N1).' if alias else ''
    return [f'- **Morpho signal pins:** {pins}. The morpho pins are male: each is a female-to-male Dupont jumper, '
            'its female end on the pin, its male end in the breadboard hole (a solid wire cannot be pushed onto a '
            f'male pin). Check each pin against UM2592 Table 18 before you fit the lead.{empty}']


def _aliases(w, into):
    """The header pins tied to the landed pins of `into` ([(jumper, NUCLEO end)]), less those landings."""
    pins = {a for j, _h in into for a in wiring.tied_headers(w, j.net)} - {f'{h[1]}.{h[2]}' for _j, h in into}
    return sorted(pins, key=lambda p: tuple(int(n) for n in p[2:].split('.')))   # CN5.1 .. CN10.29


def _into(jumpers, headers, nets=None):
    """[(jumper, NUCLEO end)] for the jumpers that land on these headers (of these nets, if given)."""
    return [(j, h) for j in jumpers for h in (j.a, j.b)
            if h[0] == 'N' and h[1] in headers and (nets is None or j.net in nets)]


def oled_check(w, jumpers):
    signals = ', '.join(nucleo_jumpers(jumpers, OLED_NETS))
    pair = ' and '.join(f'{k.id} ({end_name(k.a)} to {end_name(k.b)})' for k in w.leads if k.role == 'supply')
    alias = _aliases(w, _into(jumpers, ('CN10',), OLED_NETS))
    empty = f' Their ARDUINO aliases ({", ".join(alias)}) stay empty: one landing per MCU pin (record N1).' if alias else ''
    return (f'- **OLED wires:** {signals} run from board C to CN10: female-to-male jumpers of about 30 cm.{empty} '
            f'Its supply pair goes straight to the NUCLEO, off every breadboard rail (record N3): {pair}. In mode B '
            'unplug the OLED\'s VCC lead from CN7.16 (section 7), or the display\'s 50-150 mA rides the regulator chain.')


def arduino_name(header, pin):
    if (header, pin) in ARDUINO_PINS:
        return ARDUINO_PINS[(header, pin)]
    name, first = ARDUINO[header]
    return f'{name}{first + pin - 1}'


def arduino_check(w, jumpers):
    """A bench check for the jumpers into the ARDUINO signal headers CN5 (D8-D15), CN8 (A0-A5) and CN9
    (D0-D7), from the model, with the morpho aliases ([nucleo] ties) that stay empty (record 4.2, N1)."""
    into = _into(jumpers, tuple(ARDUINO))
    if not into:
        return []
    into.sort(key=lambda t: (t[1][1], t[1][2]))
    pins = ', '.join(f'{j.id} to {h[1]}.{h[2]} ({arduino_name(h[1], h[2])}, {w.mcu.get(j.net)}, {j.net})' for j, h in into)
    return [f'- **CN5 (D8-D15), CN8 (A0-A5) and CN9 (D0-D7):** {pins}. All three are female ARDUINO headers: use '
            'solid 22 AWG male ends (record H3, N3). Check each against UM2592 Table 17 before you push the wire '
            f'in. The morpho aliases of these pins ({", ".join(_aliases(w, into))}) stay empty: one landing per MCU '
            'pin (record N1).']


def _intro(w, data):
    source = Path(data).relative_to(SOURCE).as_posix()
    text = (f'Generated by `source/make.py sheet` (or `all`) from `source/{source}`. Do not edit. Build in this '
            'order. Holes are `board:row column`: `A:j14` is board A, row j, column 14. The rails are L+ and L- '
            '(beside row a) and R- and R+ (beside row j).')
    if Path(data) == DATA:
        return text + ' The renders are in `renders/`.'
    return text + (f' **{w.revision} is a frozen earlier revision** (record 6.1): build this sheet for its own change, '
                   'then the next revision\'s sheet, whose Remove and Add lists start from this one. It has no '
                   'renders: they are of the current revision (`build-sheet.md` at the top of this directory). The '
                   'wiring guide and the firmware describe the current revision, so `make.py` holds this model to '
                   'the connectivity proof and the D3 checks only.')


# Where everything off the breadboards lives on the bench base plate (hardware/base-plate/spec-r2.md),
# by model id: every off-board part and every joint needs one (homes_rows() raises otherwise). EXTRA_HOMES
# are the things the model does not draw.
PLATE_HOMES = {'PACK': 'battery cradle (strap over it; the + lead exits at the marked end)',
               'NTC': 'taped to the pack in its cradle; its leads leave by the cradle\'s lead gap',
               'RLOAD': 'the two raised posts beside its WAGOs, held by its leads, clear of the plastic',
               'ADAPTER': 'off the plate, at the wall; its cable held by the USB CHG clamp and tie bridge'}
JOINT_HOME = 'the WAGO row, in its labelled pocket, levers up'
EXTRA_HOMES = (('NUCLEO TX (the node)', 'its edge cradle on the plate, USB end at the cable exit'),
               ('NUCLEO RX (the bridge)', 'its edge cradle on the plate, USB end at the cable exit; its USB to a '
                'Mac port directly, not a hub'),
               ('spare WAGO 222-413 (the meter splice, check C5)', 'its splice pocket next to CELL_POS while in use, if the plate has one (base plate spec §7 item 13); '
                'otherwise held by a tie point there'),
               ('STEMMA QT hub', 'the sensor deck (M2.5 screws on standoffs), fed by the QT cable from board A'),
               ('STEMMA QT sensors', 'the sensor deck, screwed down, or off the plate on a longer QT cable'),
               ('wind and rain meters', 'off the plate (outdoors); their RJ11 cables held by the meter clamps'),
               ('USB cables to the NUCLEOs', 'one clamp and tie bridge each at the cable exit'))


def homes_rows(w):
    """Every part's home: a breadboard (section 1 gives the holes) or a place on the base plate."""
    missing = [p.id for p in w.parts.values() if p.place_mm and p.id not in PLATE_HOMES]
    if missing:
        raise ValueError(f'no base plate home for {missing}: add them to PLATE_HOMES')
    out = ['', '## 0b. Homes', '', 'Every board and part lives on a breadboard or in its own place on the base '
           'plate (`hardware/base-plate/spec-r2.md`); nothing is loose on the desk.', '',
           '| What | Home |', '|---|---|']
    out += [f'| {p.id} ({p.kind}) | breadboard {p.board} (section 1) |' for p in w.parts.values() if not p.place_mm]
    out += [f'| {p.id} ({p.kind}) | {PLATE_HOMES[p.id]} |' for p in w.parts.values() if p.place_mm]
    out += [f'| {j.id} ({j.kind}) | {JOINT_HOME} |' for j in w.joints.values()]
    return out + [f'| {what} | {home} |' for what, home in EXTRA_HOMES]


TEARDOWN = ['', '## 0a. Teardown (before building from this sheet)', '',
            'Take the old build apart in this order, so that nothing is ever live while you pull it:', '',
            '1. **Power off.** Unplug the charger\'s USB-C adapter at the wall, then both NUCLEO USB cables.',
            '2. **The pack:** unplug its JST PH plug from the pigtail. Never cut its lead. From here the pack is the '
            'only energy on the bench, and its plug is apart.',
            '3. **The leads (section 3), every one:** open each WAGO lever and pull its lead; unplug the JST PH '
            'plugs at the charger and the gauge by the plug body, never by the wires; loosen the INA228\'s X1 '
            'screws and pull its three leads; pull the adapter cable out of the charger\'s USB-C; pull every lead '
            'that ends in a breadboard hole or a NUCLEO pin (the regulator leads, L_REG_3V3, L_NUC_RET, the OLED '
            'supply pair, the NTC pair, so the pack and its taped NTC come free together).',
            '4. **The jumpers:** pull each one straight up with pliers or fingers on the bend. Sort the kit jumpers '
            'back by length. Keep a cut-to-fit wire only if it is the same span as one in section 2; tag it with '
            'the holes it joins (for example A:d19-A:d2), never a jumper number: those change whenever the model '
            'is regenerated.',
            '5. **The breakouts:** rock each one gently out by its board edges (charger, INA228, gauge, '
            'regulator, RJ11 breakouts, OLED), never by a header or the screw terminal.',
            '6. **The breadboards** stay where they are if they already sit in the base plate pockets; otherwise '
            'peel them off and seat them in the pockets before building.',
            '7. **Check before building:** with nothing fitted, each board\'s rails read open (OL) to each other '
            'on the meter. A short means a strand of wire is stuck in a strip: find it before going on.']


def build_sheet(w, jumpers, out=HW, data=DATA):
    """The hole-by-hole build sheet (build-sheet.md): the revision and hashes, the changes from the previous
    revision, parts, jumpers, leads, joints, the power path, the C1-C23 checklist, the modes, then the
    bench checks and the power checks. `out` is the directory whose layout.json the sheet is compared with
    (the committed tree by default, as `make.py sheet` writes it); `data` is the model file (wiring.toml, or
    a frozen revision's)."""
    out = Path(out)
    lines = ['# Bench breadboard build sheet', '', _intro(w, data), '', *header_rows(w, out, data)]
    lines += change_rows(w, jumpers, load_baseline(w.revision))
    if Path(data) == Path(DATA):   # the current revision only: the frozen sheets keep what they were
        lines += TEARDOWN + homes_rows(w)
    lines += part_rows(w) + jumper_rows(w, jumpers) + lead_rows(w) + joint_rows(w)
    lines += path_rows(w) + checklist_rows() + mode_rows(w) + bench_rows(w, jumpers)
    return '\n'.join(lines + power_checks(w, jumpers) + phase_b_checks() + [''])


def write_sheet(w, jumpers, out, data=DATA):
    """build-sheet.md and connections.json (this revision's connections and the baseline it was compared with)
    into out."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    text = build_sheet(w, jumpers, out, data)
    doc = {'revision': w.revision, 'connections': connections(w, jumpers), 'baseline': load_baseline(w.revision)}
    (out/'build-sheet.md').write_text(text)
    (out/CONNECTIONS).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')


def write_sheets(out):
    """The sheet tier's files: each frozen revision's sheet into out/revisions/<revision>/, then the current
    revision's into out. Every model is checked before any file is written."""
    models = [(frozen_model(r), Path(out)/'revisions'/r) for r in HISTORY] + [(DATA, Path(out))]
    done = [(checked(data), data, where) for data, where in models]
    for (w, jumpers), data, where in done:
        write_sheet(w, jumpers, where, data)
    return done[-1][0]


# ---- the power checks (numbered 1-10: other documents cite "build-sheet check N") ----

def _headers(w, net):
    """A net's NUCLEO pins, with the aliases the board ties to them."""
    own = wiring.nucleo_headers(w, net)
    alias = sorted(wiring.tied_headers(w, net) - set(own))
    return ', '.join(own) + (f'; alias {", ".join(alias)}' if alias else '')


def _sense_lead(w, terminal):
    """'L_VBUS' and its joint end: the lead from a terminal, as the checks name it."""
    k = next((k for k in w.leads if terminal in (k.a, k.b)), None)
    if k is None:
        return 'its VBUS sense lead', 'the OUT joint'
    return f'the {k.id} sense lead', end_words(k.b if k.a == terminal else k.a)


# Record M1 and 7.1 Q2: the series reference is the Fluke 87V itself (no shunt or clamp meter is bought),
# in series only for a short steady window, as power-telemetry 12.2 allows.
SERIES_METER = ('the Fluke 87V in series (its A input for about 1 A, its mA input, 400 mA, for the 38 mA load), '
                'spliced into the pack + lead at CELL+ position 1 (its two leads clipped to short 22 AWG solid stubs: '
                'the pack red lead and one stub in a spare 222-413, the other stub in position 1; the pack unplugged '
                'while it goes in and out), only for a '
                'short steady window: its current shunt adds tens to hundreds of mOhm, so never during a termination '
                'run or the battery-path checks (7, C12-C14)')


def power_checks(w, jumpers):
    """Checks 1-10 (spec 2026-10-29 section 11.1, as the build-progression record amends it), each with the
    C-rows of record 4.3 it shares, in build order."""
    lead, at = _sense_lead(w, 'INA.X1_VBUS')
    status = ' and '.join(nucleo_jumpers(jumpers, ('CHG', 'PGOOD')))
    analog = ' and '.join(nucleo_jumpers(jumpers, ('ISET', 'VIN_SENSE')))
    return ['', '## Power checks', '',
            'The phase A power checks (spec `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` '
            'section 11.1, amended by the build-progression record), in this order, with the section 6 rows each '
            'shares. **The model first:** a measured or fitted value goes into `source/wiring.toml` before the '
            'firmware, because D3 checks 8 and 9 (`make.py sheet`) hold the firmware to the model: check 2\'s '
            'R_ISET as the charger\'s `iset_ohms`; R4-R6 each measured (record 4.4 step 12) as their '
            '`measured_ohms`; the M2 ISET gain fit (4.4 step 11) as the charger\'s `iset_gain_ppm`. Then the same '
            'value into `firmware/stage0-node/App/power_config.h` (`POWER_R_ISET_OHM`, `POWER_VIN_DIVIDER_PPM`, '
            '`POWER_ISET_GAIN_PPM`), benchlink\'s `VIN_DIVIDER_PPM` and `tools/benchlink_log.py`\'s `R_ISET_OHM` '
            'and `ISET_GAIN`, and regenerate this sheet, in one commit. Check 3\'s value goes in only if the shunt '
            'fails its check. Commit a measured value before flashing the build that carries it: a build from a dirty tree '
            'reports firmware build ID 0, "not identified" (spec section 8.6).', '',
            f'1. **Before power, no VBUS lead fitted** (pre-run check C1): on the INA228, X1.2 (VBUS) to X1.3 (VIN+) and X1.2 to '
            f'X1.1 (VIN-) read open (SJ1, the back VBUS-to-VIN+ jumper, open). Then fit {lead} into the OUT joint '
            f'({at}).',
            '2. **R_ISET** (C16): with the charger unpowered and the pack unplugged, measure ISET to GND: R9, '
            '1 kOhm expected (POWER_R_ISET_OHM 1000), behind the closed 1A jumper (KISET 890 A*ohm gives about '
            '0.89 A). Any other reading replaces the charger\'s `iset_ohms` in the model first, then '
            '`POWER_R_ISET_OHM` and the logger\'s `R_ISET_OHM` (see above). The charge current read from ISET is '
            'I = 400 x V_ISET / R_ISET: the ISET monitor is 1/400 of the charge current, +-10 % (SLUS810 section '
            '9.3.5.1), plus R_ISET\'s own tolerance.',
            f'3. **Shunt** (C5): verified, not measured (spec section 8.6, record M1): at a steady current the '
            f'INA228 battery current agrees within 2 % + 2 mA with {SERIES_METER}. Only if the shunt fails, the '
            'reference-derived value (the meter\'s mV across the shunt\'s Kelvin points over the series A, never an '
            'ohm range) replaces the nominal 15 mOhm (1 %).',
            f'4. **ISET and VIN_SENSE before the pack** ({analog}): with the wall adapter on and the pack unplugged, '
            f'VIN_SENSE ({_headers(w, "VIN_SENSE")}) x the measured ratio (POWER_VIN_DIVIDER_PPM / 1e6, from R4-R6 '
            'each measured and held in the model as `measured_ohms`; record M2) agrees with the meter on VBUS, within 1 %, and ISET '
            f'({_headers(w, "ISET")}) reads near 0 V with no charge current.',
            '5. **TS:** with input power present, THERM to GND reads about 0.75 V at 25 C (the 10 kOhm NTC at 75 uA). '
            'About 0.375 V means the breakout\'s fixed 10 kOhm TS resistor (R10, the THERM jumper) is still in '
            'parallel: cut it.',
            *_checks_6_to_10(w, status)]


def _checks_6_to_10(w, status):
    loop = loop_leads(w)
    b = checklist.BUDGETS
    return [
        f'6. **CHG and PGOOD released** ({status}; C17): with the charge done, and with the input removed for a '
        f'moment, with the firmware\'s internal pull-ups on, {w.mcu.get("CHG")} (CHG: {_headers(w, "CHG")}) and '
        f'{w.mcu.get("PGOOD")} (PGOOD: {_headers(w, "PGOOD")}) both read at or below min(VDD, VDDA) + 0.3 V '
        '(DS13293 table 26 note 3: above that the internal pull-ups must be off; record N4). The LED anodes are on '
        'OUT (schematic), so a released pin sits near OUT - Vf: 2.9 V measured on 2026-10-28/29, under the VDD + 0.3 '
        'V rule (3.6 V). Re-measure at each step.',
        '7. **Battery path** (C12-C14, section 5): in the first 10 minutes of a CC charge, with the INA228 current I '
        'between 0.8 and 1.0 A, each span a mV drop on the meter over I (spec section 11.2, record P8): the + span '
        f'(PATH_POS: pack plug +, back-probed, to the charger\'s header LIPO, including the 15 mOhm shunt) at most '
        f'{b["PATH_POS"]:g} mOhm; the - span (PATH_NEG: header GND to pack plug -, back-probed) at most '
        f'{b["PATH_NEG"]:g} mOhm; each pack-side span (PATH_PACK_POS: pack plug + to the CELL+ clamp; PATH_PACK_NEG: '
        f'the STAR clamp to pack plug -) at most {b["PATH_PACK_POS"]:g} mOhm, their sum recorded as R_pack; each JST '
        'PH mating at most 20 mOhm; each lever clamp to clamp and each screw at most 5 mOhm. The leads of PATH_POS '
        f'and PATH_NEG are about {sum(lead_mohm(k) for k in loop):.0f} mOhm of copper ({", ".join(k.id for k in loop)}, '
        'from their gauge and length). A 0.2 ohm breadboard path ended 1 A charges early on 2026-10-28.',
        '8. **Gauge** (C10, C14; step 1 exit 5, record R-2): at rest or at the 38 mA load, the gauge VCELL within '
        '10 mV of the meter at the pack plug. At a 1 A charge, the gauge VCELL within 10 mV of the meter at the '
        'gauge\'s own sense points (the CELL+ clamp to the STAR clamp), and the pack-plug difference (gauge VCELL - '
        'the meter at the pack plug) recorded, at or below I x R_pack + 10 mV (R_pack from C14).',
        '9. **INA VBUS = OUT, and SJ1 really open:** during a charge with the pack below 4.1 V, OUT (`load_mv`, the '
        'INA228 VBUS) reads 4.3-4.5 V and at least 100 mV above the gauge VCELL. A closed SJ1 ties the cell to OUT '
        'and fails this check.',
        '10. **TMR and termination** (record P9): with the charger unpowered, TMR reads 0 ohm to GND (the schematic '
        'ties it to GND: all safety timers disabled, so the charge may start from any cell voltage). A charge at the '
        '1A jumper then ends with CHG off and steady, not flashing, while the INA228 battery current is 0.20-0.40 A '
        '(ITERM about 0.3 A) and the cell (gauge VCELL - I x R_pack) is at 4.12 V or more. Flashing at about 2 Hz '
        'means expired safety timers (SLUS810 table 9-2): with TMR at GND it should not happen, so check TMR and the '
        'CHG lead. If the board in hand has TMR floating (default 4-6 h), record it and start the charge at 3.85 V '
        'or more; no RTMR is fitted (record P9).']


def phase_b_checks():
    """The step 1b checks (record step 1b exit criteria, spec 2026-10-29 section 11.3,
    docs/hardware/power-metering.md): the three rail INA228s and the D2/D4 OR pair, before the node runs
    WS_POWER_PROFILE 2. Their wiring is in the protoboard model, not on this sheet."""
    return ['', '## Step 1b power checks', '',
            'Step 1b, after the step 2 H01 run, on the step 2 plate\'s small breadboard (record S1, 7.1 Q8), before '
            'the node runs profile B (`WS_POWER_PROFILE=2`): the load, solar and USB-C INA228s and the board\'s own '
            'D2/D4 OR pair (record P10). Step 1b is not drawn on this sheet: its wiring belongs to the protoboard '
            'model (record D7). Checks 1-10 still hold.', '',
            'B1. **EN1 and EN2** (charger unpowered): record both solder jumpers of the #4755 again, SJ2 (EN1) and SJ1 '
            '(EN2), as the step 1 bench check "Charger jumpers" first did. The design needs **EN2 high and EN1 low**: the R_ILIM input limit, no VIN-DPM (SLUS810 table '
            '7-2). EN1 = EN2 = high is standby, no charge. EN2 low means a 100 or 500 mA input limit with VIN-DPM: '
            'stop and record it (record 1.4, P10).',
            'B2. **Addresses:** the i2cscan bus scan lists 0x40 battery, 0x41 load, 0x45 solar and 0x48 USB-C '
            '(`power_config.h` `POWER_ADDR_*`), each with an `#rail` line (0x41, 0x45, 0x48). 0x48 is the ADDR1-to-SDA '
            'wire, allowed as INA228 module preparation (7.1 Q1): scope SDA against SCL on this bus, data hold at '
            'least 100 ns after the address MSB (spec R15).',
            'B3. **Rail shunts:** verified, not measured, as check 3: at a steady current on each rail (the load '
            'INA228 with the 100 ohm load; the solar and USB-C INA228s each during a charge from that source alone), '
            'the INA228 current (the i2cscan `#rail` line, or the node\'s `load_current_ma`, `solar_current_ma`, '
            '`usb_current_ma`) agrees within 2 % + 2 mA with the Fluke 87V in series in that rail\'s + lead at its '
            'lever joint, the same short steady window as check 3. Only a rail '
            'that fails gets its reference-derived value in `power_config.h` (`POWER_SHUNT_UOHM_LOAD`, `_SOLAR`, '
            '`_USB`).',
            'B4. **Bus pull-up** (exit f): bus idle and unpowered, SDA to 3V3 and SCL to 3V3 each read 0.97 kOhm or '
            'more, the measured value recorded (about nine 10 kOhm boards in parallel; power-metering.md section 7). '
            'Bus idle and powered, SDA high reads 2.8 V or more (the 0x48 board\'s 10 kOhm ADDR1 pull-down stays on '
            'SDA; record 1.4).',
            'B5. **One source at a time** (exit e): never solar and USB-C together. With solar alone (the wall '
            'adapter unplugged at the mains end), the USB-C INA228 reads |I| <= 1 mA and, with a 10 kOhm test load '
            'across the idle USB-C input, that input reads <= 0.5 V (D2 blocking); then the same with USB-C alone and '
            'the panel unplugged at its adapter: the solar INA228 reads |I| <= 1 mA and the idle solar input, with the '
            'same 10 kOhm load, <= 0.5 V (D4 blocking). The live source\'s INA228 VBUS reads the source, and '
            '`charger_input_mv` reads it less one Schottky drop (0.35-0.5 V).',
            'B6. **A weak source with EN2 high** (power-metering.md section 5.4): a bench supply at 7 V with its '
            'current limit at 0.3 A, then 0.1 A, into the DC jack through the solar INA228, the cell at about '
            '3.7 V. Record whether PGOOD and CHG hold steady or cycle, and `charger_input_mv`.']


# ---- the schematic's table of leads and joints (record D2, D4) ----

LEAD_NOTES = (25.40, 10.16, 3.81)   # mm: the tables' left edge, their gap below the lowest drawn item, row pitch
TABLE_GAP = 10.16                   # mm between the leads table and the joints table, side by side
CHAR_W = 1.1                        # mm per character of KiCad's 1.27 mm text, generous: no cell overflows
PAPERS = (('A3', 420.0, 297.0), ('A2', 594.0, 420.0), ('A1', 841.0, 594.0), ('A0', 1189.0, 841.0))
PAGE_FRAME = 10.0                   # mm: KiCad's border inside the paper edge
TITLE_BLOCK = (110.0, 32.0)         # mm: the title block's width and height in the frame's bottom-right corner
LEAD_COLUMNS = ('Lead', 'Role', 'Wire', 'Length', 'From', 'To', 'Net')
JOINT_COLUMNS = ('Joint', 'Kind', 'Net', 'Positions (lead ids)')


def lead_table_rows(w):
    """One row per lead: what the circuits draw as a wire with its id, in full."""
    return [[k.id, k.role, f'{k.gauge} AWG {k.kind}' + (', one end insulated' if k.insulated else ''),
             f'{k.length_mm:g} mm', end_name(k.a), end_name(k.b), k.net] for k in w.leads]


def joint_table_rows(w):
    """One row per lever connector, position by position."""
    return [[j.id, j.kind, ', '.join(n for n, ms in w.nets.items() if f'J:{j.id}' in ms), joint_positions(w, j)]
            for j in w.joints.values()]


def drawn_extent(sch_text):
    """(right, bottom) in mm of what a schematic draws outside its symbol library: every point, and each
    text, label and field run out to the right of its anchor."""
    body = sch_text
    if '(lib_symbols' in body:
        import build_schematic
        start = body.index('(lib_symbols')
        body = body[:start] + body[start + len(build_schematic._sexpr_block(body, start)):]
    xs, ys = [0.0], [0.0]
    for m in re.finditer(r'\((?:at|xy) ([-\d.]+) ([-\d.]+)', body):
        xs.append(float(m[1]))
        ys.append(float(m[2]))
    for m in re.finditer(r'\((?:text|label|property "[^"]*") "([^"]*)" \(at ([-\d.]+) ', body):
        xs.append(float(m[2]) + len(m[1])*CHAR_W)
    return max(xs), max(ys)


def _cell(build_schematic, key, value, x, y):
    t = build_schematic.TEXT
    return (f'(text "{value.replace(chr(34), chr(39))}" (at {x:.2f} {y:.2f} 0) (effects (font (size {t} {t})) '
            f'(justify left)) (uuid {build_schematic.uid(key)}))\n')


def _rule(build_schematic, key, p, q):
    return (f'(polyline (pts (xy {p[0]:.2f} {p[1]:.2f}) (xy {q[0]:.2f} {q[1]:.2f})) (stroke (width 0) (type default)) '
            f'(uuid {build_schematic.uid(key)}))\n')


def table_items(name, title, columns, rows, x, y):
    """A ruled table as schematic text: its title, a header row and one row per item, each column as wide
    as its longest cell. Returns (items, (x1, y1, x2, y2))."""
    import build_schematic
    pitch = LEAD_NOTES[2]
    widths = [max(len(str(r[c])) for r in [columns, *rows])*CHAR_W + 2.54 for c in range(len(columns))]
    edges = [x + sum(widths[:c]) for c in range(len(columns) + 1)]
    top, bottom = y + pitch, y + (len(rows) + 2)*pitch
    items = [_cell(build_schematic, f'{name}-title', title, x, y + pitch/2)]
    for r, row in enumerate([columns, *rows]):
        items += [_cell(build_schematic, f'{name}-{r}-{c}', str(v), edges[c] + 1.27, top + (r + 0.5)*pitch)
                  for c, v in enumerate(row)]
    for k, ry in enumerate((top, top + pitch, bottom)):
        items.append(_rule(build_schematic, f'{name}-h{k}', (edges[0], ry), (edges[-1], ry)))
    items += [_rule(build_schematic, f'{name}-v{c}', (ex, top), (ex, bottom)) for c, ex in enumerate(edges)]
    return items, (edges[0], y, edges[-1], bottom)


def paper_for(boxes):
    """The smallest paper (PAPERS) whose frame holds every box (x1, y1, x2, y2) clear of the title block."""
    for name, pw, ph in PAPERS:
        fx, fy = pw - PAGE_FRAME, ph - PAGE_FRAME
        tb = (fx - TITLE_BLOCK[0], fy - TITLE_BLOCK[1])
        if all(b[2] <= fx and b[3] <= fy and not (b[2] > tb[0] and b[3] > tb[1]) for b in boxes):
            return name
    raise ValueError(f'the schematic needs more than {PAPERS[-1][0]}: {boxes}')


def lead_notes(w, sch_text):
    """The schematic text with the table of leads and the table of joints side by side under the circuits
    (record D2: the drawing shows each lead's role, gauge and length), each sized from the model, on the
    smallest paper that holds the circuits and the tables. The circuits draw a lead as a wire with its
    id; the table gives its ends in full."""
    if not w.leads and not w.joints:
        return sch_text
    x, gap, _pitch = LEAD_NOTES
    right, lowest = drawn_extent(sch_text)
    y = round((lowest + gap)/1.27)*1.27
    items, boxes = [], [(0.0, 0.0, right, lowest)]
    for name, title, columns, rows in (
            ('lead-table', 'Leads off the breadboard (build sheet section 3): cut each to this length or shorter.',
             LEAD_COLUMNS, lead_table_rows(w)),
            ('joint-table', 'Lever connectors off the breadboard (build sheet section 4): one node each.',
             JOINT_COLUMNS, joint_table_rows(w))):
        if not rows:
            continue
        cells, box = table_items(name, title, columns, rows, x, y)
        items += cells
        boxes.append(box)
        x = box[2] + TABLE_GAP
    head, tail = sch_text.rsplit('(sheet_instances', 1)
    head = re.sub(r'\(paper "[^"]+"\)', f'(paper "{paper_for(boxes)}")', head, count=1)
    return head + ''.join(items) + '(sheet_instances' + tail


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
    """The 3D view's footprints: the parts, the joints, the NUCLEO headers, each breadboard body, each
    jumper wire along its routed path and each lead (its gauge; a joint or NUCLEO end at that part's
    height, an insulated end sleeved). Writes the generated .wrl files into models_dir."""
    import models
    import pcb_read
    import render
    out = model_footprints(w)
    for header, (_x, cols, n) in wiring.HEADERS.items():
        x, y = wiring.hole_xy(('N', header, 1))
        file, rot = models.header_model(n // cols, cols, along_columns=False, female=header in wiring.FEMALE)
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
        segments = (list(zip(map(tuple, j['path']), map(tuple, j['path'][1:]), strict=False)) if j['path']
                    else [(p, q) for p, q, _layer in copper[j['id']]['segments']])
        ref = f'3D_{j["id"]}'
        models.write_jumper(models_dir/f'{ref}.wrl', segments, [tuple(j['a']), tuple(j['b'])],
                            models.WIRE_Z + 0.4*(i % 4), rgb)
        out.append({'ref': ref, 'x': 0.0, 'y': 0.0, 'box': None,
                    'models': [{'file': f'${{KIPRJMOD}}/models/{ref}.wrl', 'z': 0.0, 'rot': 0}]})
    for lead in lay.get('leads', []):   # off the breadboard, above the breakouts, each end at its own height
        ref = f'3D_{lead["id"]}'
        z = tuple(models.END_Z.get(lead[f'{e}_end'], models.LEAD_Z) for e in 'ab')
        models.write_lead(models_dir/f'{ref}.wrl', tuple(lead['a']), tuple(lead['b']), lead['gauge'],
                          tuple(c/255 for c in render.COLOURS[lead['class']]), z,
                          tuple(e for e in 'ab' if lead[f'{e}_end'] == 'insulated'))
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
    sch.write_text(lead_notes(w, sch.read_text()))   # the leads' gauge and length (build_schematic draws the nets)
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
    for name, what in (('sheet', 'no KiCad: check and prove the model, write build-sheet.md and connections.json'),
                       ('all', 'everything: the sheet tier, then the KiCad board, schematic and renders')):
        sub.add_parser(name, help=what).add_argument('--out', default=str(HW))
    lay = sub.add_parser('layout')
    lay.add_argument('out')
    args = ap.parse_args(argv)
    if args.cmd == 'layout':
        Path(args.out).write_text(json.dumps(layout(*checked()), indent=1, sort_keys=True))
    elif args.cmd == 'sheet':
        w, jumpers = write_sheets(args.out)
        print(f'make.py: {w.revision}: {len(jumpers)} jumpers, {len(w.leads)} leads, {len(w.joints)} joints, '
              f'every check passed; build-sheet.md and {CONNECTIONS} written to {args.out}, with the frozen '
              f'revisions {", ".join(HISTORY)} under revisions/')
    else:
        if kicad_env is None:
            raise SystemExit('make.py: tools/kicad_env.py did not import: `all` needs KiCad, `sheet` does not')
        build_all(args.out)
        write_sheets(args.out)   # the sheet tier's sheets and connections.json, against out's layout.json


if __name__ == '__main__':
    main()
