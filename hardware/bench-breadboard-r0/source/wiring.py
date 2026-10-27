"""The breadboard model of the bench station (wiring.toml): parts on holes, strips, nets.

A hole is (board, row, column). Board 'A' or 'B'; row 'a'..'j' or a rail 'L+', 'L-' (beside row a),
'R-', 'R+' (beside row j); column 1..63. A NUCLEO pin is ('N', header, pin), for example
('N', 'CN10', 14). Standard library only: the repository Python reads this, KiCad's Python reads
the layout.json that make.py writes from it."""
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

COLUMNS = 63
PITCH = 2.54                      # mm between holes
ROWS = 'abcdefghij'
RAILS = ('L+', 'L-', 'R-', 'R+')
RAIL_SPLIT_AFTER = 31             # a split rail's halves meet between columns 31 and 32
CHANNEL = 7.62                    # mm between rows e and f
RAIL_GAP = 5.08                   # mm from row a to rail L-, and from row j to rail R-
BOARD_GAP = 20.0                  # mm between neighbouring boards
NUCLEO_GAP = 20.0                 # mm below board A to the NUCLEO headers


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


@dataclass(frozen=True)
class Wiring:
    parts: dict         # id -> Part
    nets: dict          # net name -> list of 'PART.PIN' or 'N:CN10.14'
    net_class: dict     # net name -> class
    rails: dict         # net name -> list of rail ids such as 'A:L+'
    mcu: dict           # net name -> STM32WL pin ('PC0'), or '3V3'/'GND', for a net that reaches the NUCLEO
    ties: tuple         # NUCLEO pins joined on the board itself
    links: tuple        # (member, member) pairs the wiring guide wants as one jumper
    split_rails: bool


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
# are 2 x 19, pin 1 at the top, odd pins in the left column. CN5 (10 pins) and CN6 (8 pins) are
# single rows, pin 1 at the top.
NUCLEO_Y = BOARD_HEIGHT + NUCLEO_GAP
NUCLEO_X = BOARD_WIDTH + BOARD_GAP/2 - 25.4   # under the gap between the boards
HEADERS = {'CN7': (0.0, 2, 38), 'CN6': (15.24, 1, 8), 'CN5': (35.56, 1, 10), 'CN10': (50.8, 2, 38)}


def hole_xy(h):
    """The centre of a hole in mm."""
    if h[0] == 'N':
        x0, cols, n = HEADERS[h[1]]
        i = h[2] - 1
        if not 0 <= i < n:
            raise ValueError(f'{h[1]} has no pin {h[2]}')
        return (NUCLEO_X + x0 + (i % cols)*PITCH, NUCLEO_Y + (i // cols)*PITCH)
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
    """The hole of a net member: 'R1.2' or 'N:CN10.14'."""
    if member.startswith('N:'):
        header, pin = member[2:].split('.')
        return ('N', header, int(pin))
    part, pin = member.split('.', 1)
    return w.parts[part].pins[pin]


def _part(t):
    row, col = t['origin']
    step = t['step']
    pins = {name: (t['board'], row, col + i*step) for i, name in enumerate(t['pins'])}
    return Part(id=t['id'], kind=t['kind'], board=t['board'], origin=(t['board'], row, col), pins=pins,
                labels=tuple(t.get('labels', ())), source=t['source'], note=t.get('note', ''),
                body=tuple(t['body']) if 'body' in t else None)


BODY_MARGIN = 0.8   # mm: a hole this close to a board's edge cannot take a wire either


def body_rect(part):
    """The outline of a part's board (x1, y1, x2, y2) in mm, or None for a part without one."""
    if part.body is None:
        return None
    dx, dy, w, d = part.body
    xs, ys = zip(*(hole_xy(h) for h in part.pins.values()))
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


def load(path):
    data = tomllib.loads(Path(path).read_text())
    parts = {t['id']: _part(t) for t in data['part']}
    nets = {n['name']: list(n['members']) for n in data['net']}
    w = Wiring(parts=parts, nets=nets, net_class={n['name']: n['class'] for n in data['net']},
               rails={n['name']: list(n.get('rails', [])) for n in data['net']},
               mcu={n['name']: n['mcu'] for n in data['net'] if 'mcu' in n},
               ties=tuple(tuple(t) for t in data['nucleo']['ties']),
               links=tuple((k['a'], k['b']) for k in data.get('link', [])), split_rails=data['split_rails'])
    for members in nets.values():
        for m in members:
            hole_xy(member_hole(w, m))   # an unknown part, pin, header or column fails here
    for a, b in w.links:
        if not any(a in m and b in m for m in nets.values()):
            raise ValueError(f'link {a} - {b}: not two members of one net')
    for net, members in nets.items():
        if any(m.startswith('N:') for m in members) and net not in w.mcu:
            raise ValueError(f'net {net} reaches the NUCLEO but names no `mcu` pin to check')
    return w


# ---- checks against the wiring guide and the firmware ----

# The firmware's pin constants and the net each one serves. board_inputs.c gives the port in a
# comment (/* PC0 */); the I2C pins in i2c_bus.lit.md are on GPIOA.
FIRMWARE = {'board_inputs.c': {'CUPS_PIN': 'CUPS', 'VANE_PIN': 'VANE', 'RAIN_PIN': 'RAIN',
                               'PGOOD_PIN': 'PGOOD', 'CHG_PIN': 'CHG'},
            'i2c_bus.lit.md': {'SDA_PIN': 'I2C_SDA', 'SCL_PIN': 'I2C_SCL'}}
PIN_DEFINE = re.compile(r'^#define (\w+_PIN) GPIO_PIN_(\d+)\b(?:.*?/\* P([A-H])(\d+) \*/)?', re.M)


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


def check_firmware(w, app):
    """Each firmware pin constant names the same port and pin as the model's net."""
    problems = []
    for file, constants in FIRMWARE.items():
        found = {m.group(1): m for m in PIN_DEFINE.finditer((Path(app)/file).read_text())}
        for const, net in constants.items():
            m = found.get(const)
            if m is None:
                problems.append(f'{file}: no {const}')
                continue
            port = m.group(3) or 'A'    # the I2C pins are on GPIOA
            if m.group(4) is not None and m.group(4) != m.group(2):
                problems.append(f'{file}: {const} is GPIO_PIN_{m.group(2)} but its comment says P{port}{m.group(4)}')
            if f'P{port}{m.group(2)}' != w.mcu.get(net):
                problems.append(f'{file}: {const} is P{port}{m.group(2)}; the model has {w.mcu.get(net)} for {net}')
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


def _holes_of(w, key, ties):
    """The holes of a group: a strip's holes, or the NUCLEO pins of a tie."""
    if key.startswith('N:'):
        pins = [p for p in ties.parent if ties.find(p) == key] or [key]
        return [('N', p[2:].split('.')[0], int(p[2:].split('.')[1])) for p in sorted(set(pins))]
    board = key.split(':')[0]
    return [h for h in board_holes(board) if strip(h, w.split_rails) == key]


def _distance(p, q):
    (x1, y1), (x2, y2) = hole_xy(p), hole_xy(q)
    return ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5


def _groups(w, net, ties):
    keys = {_key(w, member_hole(w, m), ties) for m in w.nets[net]}
    for rail in w.rails[net]:
        board, row = rail.split(':')
        keys |= {strip((board, row, 1), w.split_rails), strip((board, row, COLUMNS), w.split_rails)}
    return sorted(keys)


def _refuse_shared_strips(w):
    """A strip that holds pins of two nets is a short before any jumper: name both pins."""
    owner = {}
    for net, members in sorted(w.nets.items()):
        for m in members:
            if m.startswith('N:'):
                continue
            key = strip(member_hole(w, m), w.split_rails)
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


def plan_jumpers(w):
    """The jumpers that join each net's strips: a minimum spanning tree over the net's groups, each
    edge a wire between two free holes (never a part pin, one wire a hole)."""
    ties = _tie_union(w)
    _refuse_shared_strips(w)
    _refuse_parts_under_bodies(w)
    used = {h for part in w.parts.values() for h in part.pins.values() if h[0] != 'N'}
    used |= {h for part in w.parts.values() for h in covered(part)}
    planned = []
    for net in sorted(w.nets):
        groups = _groups(w, net, ties)
        free = {g: [h for h in _holes_of(w, g, ties) if h not in used] for g in groups}
        for g, holes in free.items():
            if not holes:
                raise PlanError(f'net {net}: no free hole on strip {g}')
        cluster = {g: g for g in groups}
        for a, b in w.links:   # the guide's required jumpers go in first
            if a in w.nets[net] and b in w.nets[net]:
                ga, gb = _key(w, member_hole(w, a), ties), _key(w, member_hole(w, b), ties)
                ends = [[member_hole(w, m)] if m.startswith('N:') else free[g] for m, g in ((a, ga), (b, gb))]
                _, p, q = min((_distance(p, q), p, q) for p in ends[0] for q in ends[1] if p not in used and q not in used)
                used |= {p, q}
                planned.append(Jumper(id='', net=net, a=p, b=q))
                old = cluster[gb]
                cluster = {g: cluster[ga] if c == old else c for g, c in cluster.items()}
        joined = [g for g in groups if cluster[g] == cluster[groups[0]]]
        while len(joined) < len(groups):   # Prim; ties broken by the strip ids
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
            if best is None:
                full = sorted(g for g in groups if not any(p not in used for p in free[g]))
                raise PlanError(f'net {net}: no free hole on strip {", ".join(full)}')
            _, g, h, p, q = best
            used |= {p, q}
            planned.append(Jumper(id='', net=net, a=p, b=q))
            joined += [g for g in groups if cluster[g] == cluster[h] and g not in joined]
    planned.sort(key=lambda j: (jumper_stage(j), hole_xy(j.a), hole_xy(j.b)))
    return [Jumper(id=f'W{i}', net=j.net, a=j.a, b=j.b) for i, j in enumerate(planned, 1)]


def connectivity(w, jumpers):
    """Which part and NUCLEO pins the strips, the jumpers and the NUCLEO ties join: a list of sets of
    'PART.PIN' / 'N:CN10.14', one per joined group that holds a pin."""
    u = _tie_union(w)
    pins = {}
    for part in w.parts.values():
        for name, h in part.pins.items():
            pins[f'{part.id}.{name}'] = h
    for net in w.nets.values():
        for m in net:
            if m.startswith('N:'):
                pins[m] = member_hole(w, m)
    for j in jumpers:
        u.join(strip(j.a, w.split_rails), strip(j.b, w.split_rails))
    groups = {}
    for name, h in pins.items():
        groups.setdefault(u.find(strip(h, w.split_rails)), set()).add(name)
    return list(groups.values())


def prove(w, jumpers):
    """Problems where the board's connectivity differs from the declared nets: a net in pieces, two
    nets joined (a short), or a pin that joins a net it does not belong to."""
    net_of = {m: net for net, members in w.nets.items() for m in members}
    problems = []
    for group in connectivity(w, jumpers):
        nets = sorted({net_of[m] for m in group if m in net_of})
        if len(nets) > 1:
            problems.append(f'short: {" and ".join(nets)} are joined ({", ".join(sorted(group))})')
        strays = sorted(m for m in group if m not in net_of)
        if nets and strays:
            problems.append(f'stray: {", ".join(strays)} joined to {nets[0]}')
    for net, members in sorted(w.nets.items()):
        pieces = [g for g in connectivity(w, jumpers) if g & set(members)]
        if len(pieces) > 1:
            problems.append(f'open: {net} is in {len(pieces)} pieces')
    return problems
