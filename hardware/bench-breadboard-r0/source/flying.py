"""How the renders draw a flying jumper: one whose ends are on different boards, or on the NUCLEO. On the
bench it hops over in the air; the drawing runs it straight down and over, square to the boards, so it
never lies along another wire or across a part:

- off its board: half a column sideways from the hole, so the drop runs between two hole columns (a
  second wire from the same column takes the other side), then down past the board's edge;
- across: in a lane of its own in the band between the boards and the NUCLEO headers;
- onto the NUCLEO: down a column of its own beside the header (the outer side of a two-row header's
  column, the left of a single row), then sideways into the pin. In each group the shallowest pin takes
  the column nearest the header, so no wire crosses another's last leg. CN9 (D0-D7) and CN5 (D8-D15)
  are one line, CN9 above with D7 next to D8 (wiring.HEADER_Y), so CN9's pins share CN5's approach
  columns, deepest farthest out. The approach columns of two groups must not overlap: approach_bands()
  refuses a plan where they would;
- onto another board: up its own between-column slot to the hole.

Only jumpers fly. The lever connectors (joints) and the parts placed by place_mm sit beside board B,
above row a (y < 0), clear of the lanes below the boards; their leads are drawn straight, end to end
(make.py's layout), so nothing here plans them.

Pure geometry over wiring.py: tests/test_breadboard.py checks that no two paths share a stretch of line."""
import wiring

SLOT = wiring.PITCH/2      # mm sideways from a hole to the gap between two hole columns
LANE_TOP = wiring.BOARD_HEIGHT + 9.0   # below the column numbers (BOARD_HEIGHT + 6)
LANE_PITCH = 1.2
APPROACH_FIRST = 2.0       # mm from a header column to its nearest approach column
APPROACH_PITCH = 1.5


def is_flying(j):
    return j.a[0] != j.b[0]


def _header_side(h):
    """-1 to approach a NUCLEO pin from the left of its header column, +1 from the right."""
    _x0, cols, _n = wiring.HEADERS[h[1]]
    return 1 if cols == 2 and h[2] % 2 == 0 else -1


LANE_CLEAR = 3.0           # mm from the last lane to the top of the NUCLEO headers


def lane_capacity():
    """How many flying jumpers fit in the band between the boards and the NUCLEO headers."""
    return int((wiring.NUCLEO_Y - LANE_CLEAR - LANE_TOP)/LANE_PITCH + 1e-9) + 1


def _approach_groups(flying):
    """The NUCLEO ends of the flying jumpers by approach group: (header column x, side) -> [(y, id, hole)].
    CN9 shares CN5's column, so the two headers make one group."""
    groups = {}
    for j in flying:
        for h in (j.a, j.b):
            if h[0] == 'N':
                hx, hy = wiring.hole_xy(h)
                groups.setdefault((hx, _header_side(h)), []).append((hy, j.id, h))
    return groups


APPROACH_CLEAR = 0.5       # mm between the outermost approach columns of two neighbouring groups


def approach_bands(groups):
    """{(x, side): (lo, hi)}: the x span from each group's header column to its outermost approach
    column. ValueError when two spans overlap: the wires of two headers would run along each other."""
    bands = {}
    for (hx, side), members in groups.items():
        far = hx + side*(APPROACH_FIRST + (len(members) - 1)*APPROACH_PITCH)
        bands[(hx, side)] = (min(hx, far), max(hx, far))
    spans = sorted(bands.items(), key=lambda kv: kv[1])
    for (k1, (_lo1, hi1)), (k2, (lo2, _hi2)) in zip(spans, spans[1:], strict=False):
        if lo2 - hi1 < APPROACH_CLEAR:
            raise ValueError(f'the approach columns at x {k1[0]:.2f} and x {k2[0]:.2f} overlap: '
                             'too many NUCLEO wires on neighbouring headers')
    return bands


def _approach(flying):
    """{(jumper id, hole): approach column x}, nearest the header for the shallowest pin of its group."""
    groups = _approach_groups(flying)
    approach_bands(groups)
    approach = {}
    for (hx, side), members in groups.items():
        for k, (_y, jid, h) in enumerate(sorted(members)):
            approach[(jid, h)] = hx + side*(APPROACH_FIRST + k*APPROACH_PITCH)
    return approach


def plan(jumpers):
    """{jumper id: [(x, y), ...]} for the flying jumpers, in mm, from end a to end b."""
    flying = [j for j in jumpers if is_flying(j)]
    if len(flying) > lane_capacity():
        raise ValueError(f'{len(flying)} flying jumpers need more room above the NUCLEO than its '
                         f'{lane_capacity()} lanes: raise NUCLEO_GAP')
    lanes = {j.id: LANE_TOP + i*LANE_PITCH for i, j in enumerate(flying)}

    # Board ends: a between-column slot each, the second wire from a column on the other side.
    used = {}
    slot = {}
    for j in flying:
        for h in (j.a, j.b):
            if h[0] == 'N':
                continue
            key = (h[0], h[2])
            side = 1 if used.get(key, 0) % 2 == 0 else -1
            used[key] = used.get(key, 0) + 1
            slot[(j.id, h)] = wiring.hole_xy(h)[0] + side*SLOT*(1 + (used[key] - 1)//2)

    approach = _approach(flying)

    columns = {**approach, **slot}   # (jumper id, hole) -> the x its vertical run takes
    return {j.id: _leg(columns[(j.id, j.a)], lanes[j.id], j.a)[::-1] + _leg(columns[(j.id, j.b)], lanes[j.id], j.b)
            for j in flying}


def _leg(column, lane, h):
    """The points from the lane down column x to hole h."""
    x, y = wiring.hole_xy(h)
    return [(column, lane), (column, y), (x, y)]
