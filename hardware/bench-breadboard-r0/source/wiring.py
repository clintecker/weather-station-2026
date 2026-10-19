"""The breadboard model of the bench station (wiring.toml): parts on holes, strips, nets.

A hole is (board, row, column). Board 'A' or 'B'; row 'a'..'j' or a rail 'L+', 'L-' (beside row a),
'R-', 'R+' (beside row j); column 1..63. A NUCLEO pin is ('N', header, pin), for example
('N', 'CN10', 14). Standard library only: the repository Python reads this, KiCad's Python reads
the layout.json that make.py writes from it."""
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
BOARD_GAP = 20.0                  # mm between boards A and B
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


@dataclass(frozen=True)
class Wiring:
    parts: dict         # id -> Part
    nets: dict          # net name -> list of 'PART.PIN' or 'N:CN10.14'
    net_class: dict     # net name -> class
    rails: dict         # net name -> list of rail ids such as 'A:L+'
    ties: tuple         # NUCLEO pins joined on the board itself
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
BOARD_X = {'A': 0.0, 'B': BOARD_WIDTH + BOARD_GAP}

# The NUCLEO headers, drawn beside board A for wiring only (not to scale). Morpho CN7 and CN10
# are 2 x 19, pin 1 at the top, odd pins in the left column. CN5 (10 pins) and CN6 (8 pins) are
# single rows, pin 1 at the top.
NUCLEO_Y = BOARD_HEIGHT + NUCLEO_GAP
HEADERS = {'CN7': (0.0, 2, 38), 'CN6': (15.24, 1, 8), 'CN5': (35.56, 1, 10), 'CN10': (50.8, 2, 38)}


def hole_xy(h):
    """The centre of a hole in mm."""
    if h[0] == 'N':
        x0, cols, n = HEADERS[h[1]]
        i = h[2] - 1
        if not 0 <= i < n:
            raise ValueError(f'{h[1]} has no pin {h[2]}')
        return (x0 + (i % cols)*PITCH, NUCLEO_Y + (i // cols)*PITCH)
    board, row, col = h
    if not 1 <= col <= COLUMNS:
        raise ValueError(f'no column {col}')
    return (BOARD_X[board] + (col - 1)*PITCH, _row_y(row))


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
                labels=tuple(t.get('labels', ())), source=t['source'], note=t.get('note', ''))


def load(path):
    data = tomllib.loads(Path(path).read_text())
    parts = {t['id']: _part(t) for t in data['part']}
    nets = {n['name']: list(n['members']) for n in data['net']}
    w = Wiring(parts=parts, nets=nets, net_class={n['name']: n['class'] for n in data['net']},
               rails={n['name']: list(n.get('rails', [])) for n in data['net']},
               ties=tuple(tuple(t) for t in data['nucleo']['ties']), split_rails=data['split_rails'])
    for members in nets.values():
        for m in members:
            hole_xy(member_hole(w, m))   # an unknown part, pin, header or column fails here
    return w
