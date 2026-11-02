"""The breadboard model of the bench station (wiring.toml): parts on holes, strips, nets.

A hole is (board, row, column). Board 'A' or 'B'; row 'a'..'j' or a rail 'L+', 'L-' (beside row a),
'R-', 'R+' (beside row j); column 1..63. A NUCLEO pin is ('N', header, pin), for example
('N', 'CN10', 14). A lead (`[[lead]]`) is a wire the planner does not route, with a role and a kind:
it joins its two ends and uses no strip of its own. An `off_board` part (the cell, the gauge's sense pigtail, the charger's input
source) is not plugged in: its pins are drawn at holes only to place it, every one is the end of a
lead, and no jumper or other part may use its strips. A part placed by `place_mm` instead of `origin`
has no holes at all: its pins are `terminals`, and it reserves no strip.

The schema of build-progression record D2 (docs/superpowers/specs/2026-10-29-build-progression-decisions.md):

- `[[part]]` `terminals`: pins in no hole (a JST socket, a screw terminal), joined by leads only;
  `internal`: groups of pins tied inside the part; `test_points`: header pins no jumper may join;
  `exception` ('P1 regulator'), `domain` ('power' or 'logic'), `ohms`, `place_mm` = [x, y] from
  board B's origin for a part off the breadboard, `iset_ohms` (a charger breakout's own R_ISET, the
  resistor behind its closed current jumper: checks.check_iset compares the firmware with it),
  `measured_ohms` (a resistor's DMM reading, record M2: the divider ratio then comes from R4-R6's
  measured values, checks.check_divider) and `iset_gain_ppm` (on the charger: the M2 per-board fit of
  the ISET gain, which then replaces the network's nominal gain in checks.check_iset).
- `[[joint]]` (a lever connector): id, kind, positions, place_mm, domain. A joint is one node.
- `[[lead]]`: id, a, b, role, gauge (AWG), kind, length_mm; optional max_ma, insulated, exception,
  domain, segment, note. An end is 'PART.PIN' (a hole pin or a terminal), 'J:<joint>.<n>',
  'N:<header>.<pin>', a hole '<board>:<row><col>', or 'insulated' (a folded-back lead end).
- `[[link]]`: id, a, b, optional exception.

Standard library only: the repository Python reads this, KiCad's Python reads the layout.json that
make.py writes from it."""
import dataclasses
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

COLUMNS = 63
PITCH = 2.54                      # mm between holes
ROWS = 'abcdefghij'
RAILS = ('L+', 'L-', 'R-', 'R+')
RAIL_SPLIT_AFTER = 31             # a split rail's halves meet between columns 31 and 32
CHANNEL = 7.62                    # mm between rows e and f
RAIL_GAP = 5.08                   # mm from row a to rail L-, and from row j to rail R-
BOARD_GAP = 20.0                  # mm between neighbouring boards
NUCLEO_GAP = 38.0                 # mm below the boards to the NUCLEO headers: room for flying.py's lanes (>= 20)


@dataclass(frozen=True)
class Part:
    id: str
    kind: str
    board: str
    origin: tuple
    pins: dict          # pin name -> hole
    labels: tuple
    source: str
    note: str
    body: tuple = None  # (dx, dy, w, d) in mm: the board outline, from the centre of the pins
    off_board: bool = False   # drawn at its holes, joined only by leads: nothing plugs in there
    terminals: tuple = ()     # pin names in no hole (a socket, a screw terminal): joined by leads only
    internal: tuple = ()      # groups of pin names tied inside the part
    test_points: tuple = ()   # header pins kept as zero-current test points: no jumper joins their strips
    exception: str = None     # 'P1 regulator' (record P1): the one tolerated current in a contact
    domain: str = None        # 'power' or 'logic' (record D2)
    ohms: float = None
    place_mm: tuple = None    # (x, y) mm from board B's origin: off the breadboard, no holes
    iset_ohms: float = None   # a charger's own R_ISET (record 1.4: the #4755's R9 behind its 1A jumper)
    measured_ohms: float = None   # a resistor's DMM reading (record M2), replacing `ohms` in the divider
    iset_gain_ppm: int = None     # a charger's M2 per-board ISET gain fit, ppm (PB1 node / V_ISET)


@dataclass(frozen=True)
class Joint:
    """An off-board lever connector (a WAGO 222): one node, its positions numbered from 1."""
    id: str
    kind: str
    positions: int
    place_mm: tuple     # (x, y) mm from board B's origin
    domain: str = None
    note: str = ''


@dataclass(frozen=True)
class Link:
    """A jumper the wiring guide requires, with a stable id (the build sheet's W-numbers change)."""
    id: str
    a: str
    b: str
    exception: str = None


@dataclass(frozen=True)
class Wiring:
    parts: dict         # id -> Part
    nets: dict          # net name -> list of 'PART.PIN', 'N:CN9.5' or 'J:<joint>'
    net_class: dict     # net name -> class
    rails: dict         # net name -> list of rail ids such as 'A:L+'
    mcu: dict           # net name -> STM32WL pin ('PB5'), or '3V3'/'GND', for a net that reaches the NUCLEO
    ties: tuple         # NUCLEO pins joined on the board itself
    links: tuple        # (member, member) pairs the wiring guide wants as one jumper
    split_rails: bool
    leads: tuple = ()   # Lead: wires the planner does not route (force, sense, signal or supply)
    joints: dict = field(default_factory=dict)   # id -> Joint
    link_info: tuple = ()   # Link, in the order of `links`
    revision: str = ''


@dataclass(frozen=True)
class Lead:
    """A wire the planner does not route, listed by its own id (record D2). Its `role` says what it carries:
    force (battery, charge, load or the P1 regulator chain's current), sense (microamps), signal, or supply
    (a logic supply, the bench OLED's pair). Its `kind` says what it is: a #1131 pigtail half, 22 AWG solid
    (hook-up wire or a part's own lead), a cable, or a Dupont jumper. An end is a part terminal (a screw
    terminal, a JST socket, a USB-C receptacle), a lever-connector position, a NUCLEO pin, a breadboard hole
    (a sense lead, the OLED's supply pair or the P1 chain landing in a strip) or an insulated, folded-back
    end. The planner draws no jumper for it; the proof joins its two ends."""
    id: str
    net: str
    a: str              # an end: 'PART.PIN', 'J:WAGO_STAR.4', 'N:CN6.7', 'B:c16' or 'insulated'
    b: str
    gauge: int          # wire gauge, AWG
    length_mm: float
    note: str = ''
    role: str = 'force'     # force, sense, signal or supply
    kind: str = 'solid'     # pigtail, solid, cable or dupont
    max_ma: float = None
    insulated: bool = False
    exception: str = None
    domain: str = None
    segment: str = None


def _row_y(row):
    """The y of a row (mm) from the top of a board: L+ at 0."""
    if row == 'L+':
        return 0.0
    if row == 'L-':
        return PITCH
    a = PITCH + RAIL_GAP
    if row in ROWS[:5]:
        return a + ROWS.index(row)*PITCH
    j = a + 4*PITCH + CHANNEL + 4*PITCH
    if row in ROWS[5:]:
        return j - (9 - ROWS.index(row))*PITCH
    return j + RAIL_GAP + (0 if row == 'R-' else PITCH)


BOARD_HEIGHT = _row_y('R+')
BOARD_WIDTH = (COLUMNS - 1)*PITCH
BOARDS = ('A', 'B', 'C')          # left to right on the bench: signals, power, display
BOARD_X = {b: i*(BOARD_WIDTH + BOARD_GAP) for i, b in enumerate(BOARDS)}

# The NUCLEO headers, drawn beside board A for wiring only (not to scale). Morpho CN7 and CN10
# are 2 x 19 male, pin 1 at the top, odd pins in the left column. The ARDUINO headers CN5 (10 pins),
# CN6 (8 pins), CN8 (6 pins, A0-A5) and CN9 (8 pins, D0-D7) are female single rows, pin 1 at the top
# (UM2592 Table 17).
NUCLEO_Y = BOARD_HEIGHT + NUCLEO_GAP
NUCLEO_X = BOARD_WIDTH + BOARD_GAP/2 - 25.4   # under the gap between the boards
HEADERS = {'CN7': (0.0, 2, 38), 'CN6': (15.24, 1, 8), 'CN8': (25.4, 1, 6), 'CN5': (35.56, 1, 10),
           'CN10': (50.8, 2, 38), 'CN9': (35.56, 1, 8)}
# UM2592 Table 17 and Figure 24: CN9 (D0-D7) and CN5 (D8-D15) make one ARDUINO digital line, D0 ...
# D7, a 160 mil (4.064 mm) gap, then D8 ... SCL/D15. With pin 1 at the top that puts CN9 above CN5 on
# CN5's x, CN9.8 (D7) 4.064 mm above CN5.1 (D8). CN9 starts at NUCLEO_Y like every other header, so CN5
# moves down by CN9's length and the gap; the band above the headers keeps its lanes.
HEADER_Y = {'CN5': 7*PITCH + 4.064}
FEMALE = ('CN5', 'CN6', 'CN8', 'CN9')   # take male-male jumpers; the morpho pins take male-female ones

# The net classes and the colour each is drawn in (render.py's COLOURS gives the RGB).
NET_CLASSES = {'i2c': 'blue', 'wind': 'green', 'rain': 'cyan', 'charger': 'orange', 'display': 'purple',
               'power': 'red', 'ground': 'black', 'analog': 'pink', 'battery lead': 'brown'}


def hole_xy(h):
    """The centre of a hole in mm."""
    if h[0] == 'N':
        x0, cols, n = HEADERS[h[1]]
        i = h[2] - 1
        if not 0 <= i < n:
            raise ValueError(f'{h[1]} has no pin {h[2]}')
        return (NUCLEO_X + x0 + (i % cols)*PITCH, NUCLEO_Y + HEADER_Y.get(h[1], 0.0) + (i // cols)*PITCH)
    board, row, col = h
    if not 1 <= col <= COLUMNS:
        raise ValueError(f'no column {col}')
    # Drawn as the board lies on the bench with row a at the top: the printed numbers then run from
    # 63 at the left to 1 at the right.
    return (BOARD_X[board] + (COLUMNS - col)*PITCH, _row_y(row))


def strip(h, split_rails=False):
    """The strip a hole belongs to: the holes a breadboard joins. A NUCLEO pin is its own."""
    if h[0] == 'N':
        return f'N:{h[1]}.{h[2]}'
    board, row, col = h
    if row in RAILS:
        if not split_rails:
            return f'{board}:{row}'
        return f'{board}:{row}:{1 if col <= RAIL_SPLIT_AFTER else 2}'
    return f'{board}:{"a-e" if row in ROWS[:5] else "f-j"}:{col}'


def board_holes(board):
    """Every hole of one breadboard (rails at every column: the model needs only the grid)."""
    return [(board, row, col) for row in RAILS[:2] + tuple(ROWS) + RAILS[2:] for col in range(1, COLUMNS + 1)]


def member_hole(w, member):
    """The hole of a net member: 'R1.2' or 'N:CN9.5'."""
    if member.startswith('N:'):
        header, pin = member[2:].split('.')
        return ('N', header, int(pin))
    part, pin = member.split('.', 1)
    return w.parts[part].pins[pin]


BODY_MARGIN = 0.8   # mm: a hole this close to a board's edge cannot take a wire either


def body_rect(part):
    """The outline of a part's board (x1, y1, x2, y2) in mm, or None for a part without one."""
    if part.body is None:
        return None
    dx, dy, w, d = part.body
    xs, ys = zip(*(hole_xy(h) for h in part.pins.values()), strict=True)
    cx, cy = sum(xs)/len(xs) + dx, sum(ys)/len(ys) + dy
    return (cx - w/2, cy - d/2, cx + w/2, cy + d/2)


def covered(part):
    """The holes under a part's board, other than its own pins: no wire or part can use them."""
    r = body_rect(part)
    if r is None:
        return set()
    m = BODY_MARGIN
    return {h for h in board_holes(part.board)
            if r[0] - m <= hole_xy(h)[0] <= r[2] + m and r[1] - m <= hole_xy(h)[1] <= r[3] + m} - set(part.pins.values())


# ---- the schema (record D2) ----

TOP_KEYS = {'version', 'revision', 'split_rails', 'nucleo', 'part', 'net', 'link', 'lead', 'joint'}
PART_KEYS = {'id', 'kind', 'board', 'origin', 'step', 'body', 'pins', 'labels', 'source', 'note', 'off_board',
             'terminals', 'internal', 'test_points', 'exception', 'domain', 'ohms', 'place_mm', 'iset_ohms',
             'measured_ohms', 'iset_gain_ppm'}
NET_KEYS = {'name', 'mcu', 'class', 'members', 'rails'}
LINK_KEYS = {'id', 'a', 'b', 'exception'}
JOINT_KEYS = {'id', 'kind', 'positions', 'place_mm', 'domain', 'note'}
LEAD_KEYS = {'id', 'a', 'b', 'role', 'gauge', 'kind', 'length_mm', 'max_ma', 'insulated', 'exception', 'domain',
             'segment', 'note'}
ROLES = ('force', 'sense', 'signal', 'supply')
LEAD_KINDS = ('pigtail', 'solid', 'cable', 'dupont')
DOMAINS = ('power', 'logic')
EXCEPTIONS = ('P1 regulator',)
SEGMENTS = ('PATH_POS', 'PATH_NEG', 'PATH_PACK_POS', 'PATH_PACK_NEG', 'PATH_CELL_OUT')
GAUGE_RANGE = (10, 26)   # a lead's gauge: heavy enough to matter, thin enough to be a hook-up wire
JOINT_PITCH = 5.0        # mm between a joint's positions in the drawing (a drawing pitch, not the part's)
HOLE_END = re.compile(r'^([A-Z]):(L\+|L-|R-|R\+|[a-j])(\d+)$')


def _check_keys(where, t, allowed, required=()):
    """Every key known, every required key present: a ValueError names the item."""
    unknown = sorted(set(t) - allowed)
    if unknown:
        raise ValueError(f'{where}: unknown key {", ".join(unknown)}')
    missing = [k for k in required if k not in t]
    if missing:
        raise ValueError(f'{where}: needs {", ".join(missing)}')


def _check_choice(where, key, value, choices):
    if value is not None and value not in choices:
        raise ValueError(f'{where}: {key} {value!r} is not one of {", ".join(choices)}')


def _check_positive(where, key, value):
    if value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0):
        raise ValueError(f'{where}: {key} {value} is not a positive number')


def _xy(where, value):
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)):
        raise ValueError(f'{where}: place_mm {value!r} is not [x, y] in mm')
    return (float(value[0]), float(value[1]))


def _part_holes(t, where):
    """A breadboard part's pins on holes from `origin` along `step`; none for a part placed by place_mm."""
    if ('place_mm' in t) == ('origin' in t):
        raise ValueError(f'{where}: give `origin` (on the breadboard) or `place_mm` (off it), one of them')
    if 'place_mm' in t:
        if t.get('pins') or t.get('board', 'B') != 'B' or 'step' in t:
            raise ValueError(f'{where}: a part placed by place_mm has terminals only, beside board B')
        return {}, None
    _check_keys(where, t, PART_KEYS, ('board', 'step', 'pins'))
    row, col = t['origin']
    pins = {name: (t['board'], row, col + i*t['step']) for i, name in enumerate(t['pins'])}
    for h in pins.values():
        hole_xy(h)   # a pin past the board's columns fails here
    return pins, (t['board'], row, col)


def _check_part_names(where, pins, terminals, internal, test_points):
    """Terminals apart from the hole pins; ties and test points name the part's own pins."""
    if set(pins) & set(terminals) or len(set(terminals)) != len(terminals):
        raise ValueError(f'{where}: a terminal repeats a pin name')
    names = set(pins) | set(terminals)
    for group in internal:
        if len(group) < 2 or not set(group) <= names:
            raise ValueError(f'{where}: internal tie {list(group)} needs two or more of its own pins')
    if not set(test_points) <= set(pins):
        raise ValueError(f'{where}: test_points {sorted(set(test_points) - set(pins))} are not header pins')


def _part(t):
    where = f'part {t.get("id", "?")}'
    _check_keys(where, t, PART_KEYS, ('id', 'kind', 'source'))
    pins, origin = _part_holes(t, where)
    terminals, internal = tuple(t.get('terminals', ())), tuple(tuple(g) for g in t.get('internal', ()))
    test_points = tuple(t.get('test_points', ()))
    _check_part_names(where, pins, terminals, internal, test_points)
    _check_choice(where, 'exception', t.get('exception'), EXCEPTIONS)
    _check_choice(where, 'domain', t.get('domain'), DOMAINS)
    _check_positive(where, 'ohms', t.get('ohms'))
    _check_positive(where, 'iset_ohms', t.get('iset_ohms'))
    _check_positive(where, 'measured_ohms', t.get('measured_ohms'))
    _check_positive(where, 'iset_gain_ppm', t.get('iset_gain_ppm'))
    place = _xy(where, t['place_mm']) if 'place_mm' in t else None
    return Part(id=t['id'], kind=t['kind'], board=t.get('board', 'B'), origin=origin, pins=pins,
                labels=tuple(t.get('labels', ())), source=t['source'], note=t.get('note', ''),
                body=tuple(t['body']) if 'body' in t else None,
                off_board=bool(t.get('off_board', False)) or place is not None,
                terminals=terminals, internal=internal, test_points=test_points, exception=t.get('exception'),
                domain=t.get('domain'), ohms=t.get('ohms'), place_mm=place, iset_ohms=t.get('iset_ohms'),
                measured_ohms=t.get('measured_ohms'), iset_gain_ppm=t.get('iset_gain_ppm'))


def _joint(t):
    where = f'joint {t.get("id", "?")}'
    _check_keys(where, t, JOINT_KEYS, ('id', 'kind', 'positions', 'place_mm'))
    if not (isinstance(t['positions'], int) and not isinstance(t['positions'], bool) and t['positions'] >= 1):
        raise ValueError(f'{where}: positions {t["positions"]!r} is not a whole number from 1')
    _check_choice(where, 'domain', t.get('domain'), DOMAINS)
    return Joint(id=t['id'], kind=t['kind'], positions=t['positions'], place_mm=_xy(where, t['place_mm']),
                 domain=t.get('domain'), note=t.get('note', ''))


def _joint_end(w, end):
    """'J:<joint>' or 'J:<joint>.<n>': ('joint', id, n or None)."""
    name, _, pos = end[2:].partition('.')
    joint = w.joints.get(name)
    if joint is None:
        raise ValueError(f'{end}: no [[joint]] {name}')
    if not pos:
        return ('joint', name, None)
    if not (pos.isdigit() and 1 <= int(pos) <= joint.positions):
        raise ValueError(f'{end}: {name} has positions 1 to {joint.positions}')
    return ('joint', name, int(pos))


def _hole_end(end, m):
    if m[1] not in BOARDS:
        raise ValueError(f'{end}: no board {m[1]}')
    h = (m[1], m[2], int(m[3]))
    hole_xy(h)   # an impossible column fails here
    return ('hole', h)


def parse_end(w, end):
    """What a lead end or a net member names: ('insulated',), ('nucleo', hole), ('joint', id, n),
    ('hole', hole), ('pin', hole) for a part's hole pin, or ('terminal', 'PART.PIN'). ValueError otherwise."""
    if end == 'insulated':
        return ('insulated',)
    if end.startswith('N:'):
        h = member_hole(w, end)
        hole_xy(h)   # an unknown header or pin fails here
        return ('nucleo', h)
    if end.startswith('J:'):
        return _joint_end(w, end)
    m = HOLE_END.match(end)
    if m:
        return _hole_end(end, m)
    part, _, pin = end.partition('.')
    if part not in w.parts:
        raise ValueError(f'{end}: no part {part}')
    if pin in w.parts[part].pins:
        return ('pin', w.parts[part].pins[pin])
    if pin in w.parts[part].terminals:
        return ('terminal', end)
    raise ValueError(f'{end}: {part} has no pin or terminal {pin!r}')


def raw_node(w, end):
    """The connectivity node of an end before the NUCLEO ties: a strip, 'T:PART.PIN' for a terminal,
    'J:<joint>' for any position of a joint (one node), or None for an insulated end."""
    e = parse_end(w, end)
    if e[0] == 'insulated':
        return None
    if e[0] == 'joint':
        return f'J:{e[1]}'
    if e[0] == 'terminal':
        return f'T:{e[1]}'
    return strip(e[1], w.split_rails)


def end_xy(w, end):
    """Where an end is drawn, in mm: a hole, a part's hole pin or a joint position at its own place; a
    terminal at its part's origin (on the breadboard) or place_mm (off it). None for a NUCLEO pin (the
    headers are not drawn to scale) and for an insulated end."""
    e = parse_end(w, end)
    if e[0] in ('hole', 'pin'):
        return hole_xy(e[1])
    if e[0] == 'joint':
        x, y = w.joints[e[1]].place_mm
        return (BOARD_X['B'] + x + ((e[2] or 1) - 1)*JOINT_PITCH, y)
    if e[0] == 'terminal':
        part = w.parts[e[1].split('.', 1)[0]]
        if part.place_mm is None:
            return hole_xy(part.origin)
        return (BOARD_X['B'] + part.place_mm[0], part.place_mm[1])
    return None


def _rail_strips(w, net):
    out = set()
    for rail in w.rails[net]:
        board, row = rail.split(':')
        out |= {strip((board, row, 1), w.split_rails), strip((board, row, COLUMNS), w.split_rails)}
    return out


def _nets_at(w, end):
    """The nets an end belongs to: the nets that list it (any position of a joint counts), or for a
    hole the nets with a member or a rail on its strip."""
    e = parse_end(w, end)
    if e[0] == 'joint':
        return {n for n, ms in w.nets.items() for m in ms if m == f'J:{e[1]}' or m.startswith(f'J:{e[1]}.')}
    if e[0] != 'hole':
        return {n for n, ms in w.nets.items() if end in ms}
    key = strip(e[1], w.split_rails)
    return {n for n, ms in w.nets.items()
            if key in _rail_strips(w, n) or any(raw_node(w, m) == key for m in ms)}


def _lead_net(w, where, a, b):
    """The one net a lead's ends share. A hole on an empty strip or an insulated end takes the other's."""
    if a == b or a == b == 'insulated':
        raise ValueError(f'{where}: not two members of one net')
    found = []
    for end in (a, b):
        if end == 'insulated':
            continue
        nets = _nets_at(w, end)
        if not nets and parse_end(w, end)[0] != 'hole':
            raise ValueError(f'{where}: {end} is not a member of any net')
        found.append(nets)
    common = set.intersection(*[s for s in found if s]) if any(found) else set()
    if len(common) != 1:
        raise ValueError(f'{where}: not two members of one net')
    return common.pop()


def _lead_checks(where, t):
    _check_choice(where, 'role', t['role'], ROLES)
    _check_choice(where, 'kind', t['kind'], LEAD_KINDS)
    _check_choice(where, 'exception', t.get('exception'), EXCEPTIONS)
    _check_choice(where, 'domain', t.get('domain'), DOMAINS)
    _check_choice(where, 'segment', t.get('segment'), SEGMENTS)
    _check_positive(where, 'max_ma', t.get('max_ma'))
    gauge, length = t['gauge'], t['length_mm']
    if not (isinstance(gauge, int) and GAUGE_RANGE[0] <= gauge <= GAUGE_RANGE[1]):
        raise ValueError(f'{where}: gauge {gauge} is not a whole AWG from {GAUGE_RANGE[0]} to {GAUGE_RANGE[1]}')
    if not (isinstance(length, (int, float)) and length > 0):
        raise ValueError(f'{where}: length_mm {length} is not a positive length')
    if t.get('insulated') and 'insulated' not in (t['a'], t['b']):
        raise ValueError(f'{where}: insulated = true needs an end "insulated"')


def _lead(w, t):
    """One [[lead]] table (record D2). Lead lengths (H7) are not checked here: see checks.py."""
    where = f'lead {t.get("id", "?")} ({t.get("a", "?")} - {t.get("b", "?")})'
    _check_keys(where, t, LEAD_KEYS, ('id', 'a', 'b', 'role', 'gauge', 'kind', 'length_mm'))
    try:
        net = _lead_net(w, where, t['a'], t['b'])
    except (KeyError, IndexError) as e:
        raise ValueError(f'{where}: {e}') from e
    _lead_checks(where, t)
    return Lead(id=t['id'], net=net, a=t['a'], b=t['b'], gauge=t['gauge'], length_mm=float(t['length_mm']),
                note=t.get('note', ''), role=t['role'], kind=t['kind'], max_ma=t.get('max_ma'),
                insulated=bool(t.get('insulated')) or 'insulated' in (t['a'], t['b']),
                exception=t.get('exception'), domain=t.get('domain'), segment=t.get('segment'))


def _link(t):
    where = f'link {t.get("id", "?")} ({t.get("a", "?")} - {t.get("b", "?")})'
    _check_keys(where, t, LINK_KEYS, ('id', 'a', 'b'))
    _check_choice(where, 'exception', t.get('exception'), EXCEPTIONS)
    return Link(id=t['id'], a=t['a'], b=t['b'], exception=t.get('exception'))


def _check_off_board(w):
    """An off-board part's pins: each a net member reached by a lead, since no strip carries it."""
    ends = {m for k in w.leads for m in (k.a, k.b)}
    for part in (p for p in w.parts.values() if p.off_board):
        for name in part.pins:
            if f'{part.id}.{name}' not in ends:
                raise ValueError(f'{part.id}.{name} is off the breadboard: it needs a [[lead]]')


def _check_unique(kind, ids):
    seen = set()
    for i in ids:
        if i in seen:
            raise ValueError(f'{kind} {i}: the id is used twice')
        seen.add(i)


def _check_members(w):
    """Each member names a part's pin or terminal, a NUCLEO pin or a joint; never a hole or 'insulated'."""
    for net, members in w.nets.items():
        for m in members:
            try:
                kind = parse_end(w, m)[0]
            except (KeyError, IndexError) as e:
                raise ValueError(f'net {net}: member {m}: {e}') from e
            if kind in ('hole', 'insulated'):
                raise ValueError(f'net {net}: member {m} is not a pin, a terminal or a joint')


def _check_links(w):
    """A link joins two members of one net, each in a hole (a part's pin or a NUCLEO pin)."""
    for k in w.link_info:
        if not any(k.a in m and k.b in m for m in w.nets.values()):
            raise ValueError(f'link {k.a} - {k.b}: not two members of one net')
        if any(parse_end(w, e)[0] not in ('pin', 'nucleo') for e in (k.a, k.b)):
            raise ValueError(f'link {k.id}: a jumper joins holes; a terminal or joint takes a [[lead]]')


def _check_nets(w):
    for net, members in w.nets.items():
        if any(m.startswith('N:') for m in members) and net not in w.mcu:
            raise ValueError(f'net {net} reaches the NUCLEO but names no `mcu` pin to check')
        if w.net_class[net] not in NET_CLASSES:
            raise ValueError(f'net {net}: class {w.net_class[net]!r} is not one of {", ".join(NET_CLASSES)}')


def _model(data):
    """The Wiring of a parsed wiring.toml, before its leads."""
    _check_keys('wiring.toml', data, TOP_KEYS, ('split_rails', 'nucleo', 'part', 'net'))
    _check_keys('[nucleo]', data['nucleo'], {'ties'})
    for n in data['net']:
        _check_keys(f'net {n.get("name", "?")}', n, NET_KEYS, ('name', 'class', 'members'))
    parts = [_part(t) for t in data['part']]
    joints = [_joint(t) for t in data.get('joint', [])]
    links = tuple(_link(t) for t in data.get('link', []))
    for kind, items in (('part', parts), ('joint', joints), ('link', links)):
        _check_unique(kind, [i.id for i in items])
    nets = {n['name']: list(n['members']) for n in data['net']}
    return Wiring(parts={p.id: p for p in parts}, nets=nets, net_class={n['name']: n['class'] for n in data['net']},
                  rails={n['name']: list(n.get('rails', [])) for n in data['net']},
                  mcu={n['name']: n['mcu'] for n in data['net'] if 'mcu' in n},
                  ties=tuple(tuple(t) for t in data['nucleo']['ties']),
                  links=tuple((k.a, k.b) for k in links), split_rails=data['split_rails'],
                  joints={j.id: j for j in joints}, link_info=links, revision=data.get('revision', ''))


def load(path):
    data = tomllib.loads(Path(path).read_text())
    w = _model(data)
    _check_members(w)
    w = dataclasses.replace(w, leads=tuple(_lead(w, t) for t in data.get('lead', [])))
    _check_unique('lead', [k.id for k in w.leads])
    _check_links(w)
    _check_off_board(w)
    _check_nets(w)
    return w


# ---- checks against the wiring guide and the firmware ----

# The firmware's pin constants and the net each one serves, by file under firmware/: the node and
# the bench link must use the same MCU pins (spec 2026-10-29 section 11.1). A constant gives its
# port in a comment that starts with the pin and may go on (/* PB5 = D4, CN9.5 */, /* PB1 = A0, CN8.1: ADC1_IN5 */);
# without one it is on GPIOA (the I2C pins). Add an entry only for a net the model has. Every bench
# firmware that drives a modelled pin is here: the node, benchlink, and i2cscan with its OLED (oled.c).
# Their POWER_PIN (PA9) is not here: the sensor power switch (change C) is not part of the breadboard build
# (record 4.6, 2026-11-02), so the breadboard model has no SENS_EN net and PA9 is unconnected on it.
FIRMWARE = {'stage0-node/App/board_inputs.c': {'CUPS_PIN': 'CUPS', 'VANE_PIN': 'VANE', 'RAIN_PIN': 'RAIN',
                                               'PGOOD_PIN': 'PGOOD', 'CHG_PIN': 'CHG',
                                               'ISET_PIN': 'ISET', 'VIN_PIN': 'VIN_SENSE'},
            'stage0-node/App/i2c_bus.lit.md': {'SDA_PIN': 'I2C_SDA', 'SCL_PIN': 'I2C_SCL'},
            'benchlink/App/benchlink.c': {'SDA_PIN': 'I2C_SDA', 'SCL_PIN': 'I2C_SCL',
                                          'PGOOD_PIN': 'PGOOD', 'CHG_PIN': 'CHG',
                                          'ISET_PIN': 'ISET', 'VIN_PIN': 'VIN_SENSE'},
            'i2cscan/App/i2cscan.c': {'SDA_PIN': 'I2C_SDA', 'SCL_PIN': 'I2C_SCL'},
            'i2cscan/App/oled.c': {'CS_PIN': 'OLED_CS', 'SCK_PIN': 'OLED_SCLK', 'MOSI_PIN': 'OLED_DIN',
                                   'RST_PIN': 'OLED_RST', 'DC_PIN': 'OLED_DC'}}
PIN_DEFINE = re.compile(r'^#define (\w+_PIN) GPIO_PIN_(\d+)\b(?:.*?/\* P([A-H])(\d+)\b([^\n]*?)\*/)?', re.M)
# The ADC1 channel of each ARDUINO analog pin (UM2592 Table 17: A0..A5 on CN8; A1 = PB2 is the vane).
ADC_CHANNEL = {'PB1': 5, 'PB2': 4, 'PA10': 6, 'PB4': 3, 'PB14': 1, 'PB13': 0}
ADC_NETS = ('VANE', 'ISET', 'VIN_SENSE')   # nets read with ADC1: the pin needs a channel the file selects


POWER_PINS = ('3V3', 'GND')   # power nets use several NUCLEO pins the board ties; a signal uses one


def nucleo_headers(w, net):
    return [m[2:] for m in w.nets[net] if m.startswith('N:')]


def guide_rows(guide):
    """The section 2 table of the wiring guide: (function, pins, headers) for each row."""
    text = Path(guide).read_text()
    section = text.split('\n## 2.', 1)[1].split('\n## ', 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 4 and cells[0] not in ('Function', '') and not set(cells[0]) <= set('-'):
            rows.append((cells[0], [p.strip() for p in cells[1].split(',')], cells[2]))
    return rows


def check_guide(w, guide):
    """Each net that reaches the NUCLEO: its pin has a row in the guide, and that row lists one of
    the headers the model uses for it."""
    rows = guide_rows(guide)
    problems = []
    for net, mcu in sorted(w.mcu.items()):
        headers = nucleo_headers(w, net)
        row = next((r for r in rows if mcu in r[1]), None)
        if row is None:
            problems.append(f'{net} ({mcu}): no row in the wiring guide section 2 table')
        elif not (any if mcu in POWER_PINS else all)(re.search(rf'\b{re.escape(h)}\b', row[2]) for h in headers):
            problems.append(f'{row[0]} ({mcu}): the model uses {", ".join(headers)}; the guide lists "{row[2]}"')
    return problems


STATION_PIN = re.compile(r'^(P[A-H]\d+|3V3|GND)$')
GUIDE_EXEMPT = ('protoboard only', 'carrier only')   # a row the breadboard model does not carry


def guide_table(guide):
    """The section 2 connection table as dicts keyed by its own column names (the first table whose
    header has a 'Function' and a 'Pin' column)."""
    section = Path(guide).read_text().split('\n## 2.', 1)[1].split('\n## ', 1)[0]
    lines = [ln.strip() for ln in section.splitlines() if ln.strip().startswith('|')]
    split = [[c.strip() for c in ln.strip('|').split('|')] for ln in lines]
    head = next((i for i, cells in enumerate(split) if cells[0] == 'Function' and 'Pin' in ' '.join(cells)), None)
    if head is None:
        return []
    names, rows = split[head], []
    for cells in split[head + 2:]:
        if len(cells) != len(names):
            break
        rows.append(dict(zip(names, cells, strict=True)))
    return rows


def check_guide_reverse(w, guide):
    """The other way round (record D3 check 7): each section 2 row whose pin cell names a station pin
    maps to a model net with that `mcu` pin. Rows whose wiring or notes cell says 'protoboard only' or
    'carrier only' are exempt; a 'bench only' row is not, so it must exist in the model."""
    have = set(w.mcu.values())
    problems = []
    for row in guide_table(guide):
        pin_col = next(k for k in row if k.startswith('Pin') or k.startswith('MCU pin'))
        notes = ' '.join(v for k, v in row.items() if k.startswith(('Wiring', 'Note'))).lower()
        if any(x in notes for x in GUIDE_EXEMPT):
            continue
        for pin in (p.strip() for p in row[pin_col].split(',')):
            if STATION_PIN.match(pin) and pin not in have:
                problems.append(f'{row["Function"]} ({pin}): the guide wires it; the model has no net with mcu = {pin}')
    return problems


def tied_headers(w, net):
    """The NUCLEO pins of a net, with every pin the board ties to one of them ([nucleo] ties)."""
    ties = _tie_union(w)
    roots = {ties.find(f'N:{h}') for h in nucleo_headers(w, net)}
    tied = {p for tie in w.ties for p in tie if ties.find(f'N:{p}') in roots}
    return set(nucleo_headers(w, net)) | tied


def _check_comment(w, file, const, net, m):
    """The text after the pin in a constant's comment: a header pin it names (CN8.1) must be the net's,
    or tied to one of the net's in [nucleo] ties; an ADC channel it names (ADC1_IN5) must be the pin's."""
    pin, rest, problems = f'P{m.group(3)}{m.group(2)}', m.group(5) or '', []
    for header in re.findall(r'\b(CN\d+\.\d+)\b', rest):
        if header not in tied_headers(w, net):
            problems.append(f'{file}: {const} says {header}; the model has {", ".join(nucleo_headers(w, net))} for {net}')
    for channel in re.findall(r'\bADC1_IN(\d+)\b', rest):
        if ADC_CHANNEL.get(pin) != int(channel):
            problems.append(f'{file}: {const} says ADC1_IN{channel}; {pin} is ADC1_IN{ADC_CHANNEL.get(pin)} (UM2592 Table 17)')
    return problems


def _check_adc(file, text, const, net, pin):
    """A net read by ADC1: its pin has a channel, and the file selects that channel."""
    if net not in ADC_NETS:
        return []
    if pin not in ADC_CHANNEL:
        return [f'{file}: {const} is {pin}, which has no ADC1 channel on the NUCLEO headers']
    if not re.search(rf'\bADC_CHANNEL_{ADC_CHANNEL[pin]}\b', text):
        return [f'{file}: {const} is {pin} (ADC1_IN{ADC_CHANNEL[pin]}) but the file never selects ADC_CHANNEL_{ADC_CHANNEL[pin]}']
    return []


def check_firmware(w, firmware):
    """Each firmware pin constant (FIRMWARE, files under the firmware directory) names the same port
    and pin as the model's net; its comment agrees; an ADC input's channel is the pin's."""
    problems = []
    for file, constants in FIRMWARE.items():
        text = (Path(firmware)/file).read_text()
        found = {m.group(1): m for m in PIN_DEFINE.finditer(text)}
        for const, net in constants.items():
            m = found.get(const)
            if m is None:
                problems.append(f'{file}: no {const}')
                continue
            port = m.group(3) or 'A'    # the I2C pins are on GPIOA
            pin = f'P{port}{m.group(2)}'
            if m.group(4) is not None and m.group(4) != m.group(2):
                problems.append(f'{file}: {const} is GPIO_PIN_{m.group(2)} but its comment says P{port}{m.group(4)}')
            if pin != w.mcu.get(net):
                problems.append(f'{file}: {const} is {pin}; the model has {w.mcu.get(net)} for {net}')
            if m.group(3):
                problems += _check_comment(w, file, const, net, m)
            problems += _check_adc(file, text, const, net, pin)
    return problems


# ---- jumpers and the connectivity proof ----

class PlanError(Exception):
    pass


@dataclass(frozen=True)
class Jumper:
    id: str
    net: str
    a: tuple
    b: tuple


STAGES = (*BOARDS, 'between', 'NUCLEO')   # the build order: each board, then between them, then the NUCLEO


def jumper_stage(j):
    """(stage, net): the order the build sheet lists jumpers in."""
    boards = {j.a[0], j.b[0]}
    stage = 'NUCLEO' if 'N' in boards else (boards.pop() if len(boards) == 1 else 'between')
    return (STAGES.index(stage), j.net)


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def _key(w, h, ties):
    """The group a hole belongs to: its strip, with NUCLEO pins that the board ties merged."""
    return ties.find(strip(h, w.split_rails))


def _tie_union(w):
    u = _Union()
    for tie in w.ties:
        for pin in tie[1:]:
            u.join(f'N:{pin}', f'N:{tie[0]}')
    return u


def _joined_off_board(w):
    """The nodes joined without a jumper: the NUCLEO's ties, every lead (a joint is one node, an
    insulated end joins nothing) and the ties inside parts."""
    u = _tie_union(w)
    for lead in w.leads:
        a, b = raw_node(w, lead.a), raw_node(w, lead.b)
        if a is not None and b is not None:
            u.join(a, b)
    for part in w.parts.values():
        for group in part.internal:
            for name in group[1:]:
                u.join(raw_node(w, f'{part.id}.{name}'), raw_node(w, f'{part.id}.{group[0]}'))
    return u


def _holes_of(w, net, key, ties):
    """The holes a jumper of a net may use in a group: a strip's holes, or of a NUCLEO tie only the
    pins the net names (never a morpho alias it does not list). A terminal or a joint has none."""
    if key.startswith('N:'):
        return sorted(h for h in (member_hole(w, m) for m in w.nets[net] if m.startswith('N:'))
                      if _key(w, h, ties) == key)
    board = key.split(':')[0]
    if board not in BOARDS:
        return []
    return [h for h in board_holes(board) if strip(h, w.split_rails) == key]


def _distance(p, q):
    (x1, y1), (x2, y2) = hole_xy(p), hole_xy(q)
    return ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5


def _groups(w, net, ties):
    keys = {ties.find(raw_node(w, m)) for m in w.nets[net]}
    return sorted(keys | _rail_strips(w, net))


def _refuse_shared_strips(w):
    """A strip that holds pins of two nets is a short before any jumper: name both pins. A pin in no
    net (a breakout pin left open) counts as a net of its own, and so does an off-board terminal."""
    net_of = {m: net for net, members in w.nets.items() for m in members}
    owner = {}
    for part in sorted(w.parts.values(), key=lambda p: p.id):
        for name, h in part.pins.items():
            m = f'{part.id}.{name}'
            net = net_of.get(m, f'unconnected {m}')
            if part.off_board:
                net = f'off the breadboard {m}'
            key = strip(h, w.split_rails)
            other = owner.setdefault(key, (net, m))
            if other[0] != net:
                raise PlanError(f'short: {other[1]} ({other[0]}) and {m} ({net}) share strip {key}')


def _refuse_parts_under_bodies(w):
    """A part pin under another part's board cannot be plugged in."""
    for part in w.parts.values():
        under = covered(part)
        for other in w.parts.values():
            for name, h in other.pins.items():
                if other.id != part.id and h in under:
                    raise PlanError(f'{other.id}.{name} at {h[0]}:{h[1]}{h[2]} is under {part.id}')


def _merge(cluster, ga, gb):
    """Join the clusters of two groups."""
    old = cluster[gb]
    return {g: cluster[ga] if c == old else c for g, c in cluster.items()}


def _holes_on(w, keys):
    return {h for b in BOARDS for h in board_holes(b) if strip(h, w.split_rails) in keys}


def off_board_holes(w):
    """Every hole on the strips where an off-board part is drawn: no jumper may land there. A part
    placed by place_mm has no holes, so it reserves nothing."""
    return _holes_on(w, {strip(h, w.split_rails) for p in w.parts.values() if p.off_board for h in p.pins.values()})


def forbidden_strips(w):
    """Strips no jumper may join: those of a test-point pin (a zero-current tap such as the charger's
    GND header pins, record P2), and those whose every part pin is of a power-domain part."""
    keys = {strip(p.pins[n], w.split_rails) for p in w.parts.values() for n in p.test_points}
    domains = {}
    for part in w.parts.values():
        for h in part.pins.values():
            domains.setdefault(strip(h, w.split_rails), set()).add(part.domain)
    return keys | {k for k, d in domains.items() if d == {'power'}}


def lead_holes(w):
    """The holes and NUCLEO pins that hold a lead's end: a jumper never shares them."""
    out = set()
    for lead in w.leads:
        for end in (lead.a, lead.b):
            e = parse_end(w, end)
            if e[0] in ('hole', 'pin', 'nucleo'):
                out.add(e[1])
    return out


def _reserved(w):
    """Every hole no jumper may use."""
    used = {h for part in w.parts.values() for h in part.pins.values() if h[0] != 'N'}
    used |= {h for part in w.parts.values() for h in covered(part)}
    used |= off_board_holes(w) | lead_holes(w) | _holes_on(w, forbidden_strips(w))
    return used


def _refuse_unreachable(net, groups, cluster, free):
    clusters = {c: [g for g in groups if cluster[g] == c] for c in cluster.values()}
    for members in clusters.values():   # a cluster a jumper must reach needs a free hole somewhere
        if len(clusters) > 1 and not any(free[g] for g in members):
            raise PlanError(f'net {net}: no free hole on strip {", ".join(members)}')


def _link_jumpers(w, net, ties, free, used, cluster):
    """The guide's required jumpers of a net, first: (jumpers, cluster)."""
    planned = []
    for a, b in w.links:
        if a in w.nets[net] and b in w.nets[net]:
            ga, gb = _key(w, member_hole(w, a), ties), _key(w, member_hole(w, b), ties)
            ends = [[member_hole(w, m)] if m.startswith('N:') else free[g] for m, g in ((a, ga), (b, gb))]
            pairs = [(_distance(p, q), p, q) for p in ends[0] for q in ends[1] if p not in used and q not in used]
            if not pairs:
                raise PlanError(f'net {net}: link {a} - {b} has no free hole')
            _, p, q = min(pairs)
            used |= {p, q}
            planned.append(Jumper(id='', net=net, a=p, b=q))
            cluster = _merge(cluster, ga, gb)
    return planned, cluster


def _best_edge(groups, joined, free, used):
    best = None
    for g in joined:
        for h in groups:
            if h in joined:
                continue
            pair = min(((_distance(p, q), p, q) for p in free[g] for q in free[h] if p not in used and q not in used),
                       default=None)
            if pair is None:
                continue   # this pair of groups has no free holes left: another may join them
            cand = (pair[0], g, h, pair[1], pair[2])
            if best is None or cand < best:
                best = cand
    return best


def _prim(net, groups, cluster, free, used):
    """The jumpers that join a net's clusters: Prim, ties broken by the strip ids."""
    planned = []
    joined = [g for g in groups if cluster[g] == cluster[groups[0]]]
    while len(joined) < len(groups):
        best = _best_edge(groups, joined, free, used)
        if best is None:
            full = sorted(g for g in groups if not any(p not in used for p in free[g]))
            raise PlanError(f'net {net}: no free hole on strip {", ".join(full)}')
        _, g, h, p, q = best
        used |= {p, q}
        planned.append(Jumper(id='', net=net, a=p, b=q))
        joined += [g for g in groups if cluster[g] == cluster[h] and g not in joined]
    return planned


def plan_jumpers(w):
    """The jumpers that join each net's strips: a minimum spanning tree over the net's groups, each
    edge a wire between two free holes (never a part pin, a lead's hole, a test-point or power-only
    strip, one wire a hole). Leads, joints and the ties inside parts join groups off the breadboard:
    no jumper, no hole."""
    ties = _tie_union(w)
    base = _joined_off_board(w)
    _refuse_shared_strips(w)
    _refuse_parts_under_bodies(w)
    used = _reserved(w)
    planned = []
    for net in sorted(w.nets):
        groups = _groups(w, net, ties)
        free = {g: [h for h in _holes_of(w, net, g, ties) if h not in used] for g in groups}
        cluster = {g: base.find(g) for g in groups}
        _refuse_unreachable(net, groups, cluster, free)
        links, cluster = _link_jumpers(w, net, ties, free, used, cluster)
        planned += links + _prim(net, groups, cluster, free, used)
    planned.sort(key=lambda j: (jumper_stage(j), hole_xy(j.a), hole_xy(j.b)))
    return [Jumper(id=f'W{i}', net=j.net, a=j.a, b=j.b) for i, j in enumerate(planned, 1)]


def _named_nodes(w):
    """Every named pin and its node: part hole pins, terminals, and the NUCLEO pins and joints the
    nets name."""
    out = {}
    for part in w.parts.values():
        for name in (*part.pins, *part.terminals):
            out[f'{part.id}.{name}'] = raw_node(w, f'{part.id}.{name}')
    for members in w.nets.values():
        for m in members:
            if m.startswith(('N:', 'J:')):
                out[m] = raw_node(w, m)
    return out


def connectivity(w, jumpers):
    """Which part pins, terminals, NUCLEO pins and joints the strips, the jumpers, the leads, the
    joints, the ties inside parts and the NUCLEO ties join: a list of sets of names, one per joined
    group that holds one."""
    u = _joined_off_board(w)
    for j in jumpers:
        u.join(strip(j.a, w.split_rails), strip(j.b, w.split_rails))
    groups = {}
    for name, key in _named_nodes(w).items():
        groups.setdefault(u.find(key), set()).add(name)
    return list(groups.values())


def prove(w, jumpers):
    """Problems where the board's connectivity differs from the declared nets: a net in pieces, two
    nets joined (a short), or a pin that joins a net it does not belong to."""
    net_of = {m: net for net, members in w.nets.items() for m in members}
    groups = connectivity(w, jumpers)
    problems = []
    for group in groups:
        nets = sorted({net_of[m] for m in group if m in net_of})
        if len(nets) > 1:
            problems.append(f'short: {" and ".join(nets)} are joined ({", ".join(sorted(group))})')
        strays = sorted(m for m in group if m not in net_of)
        if nets and strays:
            problems.append(f'stray: {", ".join(strays)} joined to {nets[0]}')
    for net, members in sorted(w.nets.items()):
        pieces = [g for g in groups if g & set(members)]
        if len(pieces) > 1:
            problems.append(f'open: {net} is in {len(pieces)} pieces')
    return problems
