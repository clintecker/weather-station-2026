"""How the renders draw a flying jumper: one whose ends are on different boards, or on the NUCLEO. On the
bench it hops over in the air; the drawing runs it straight down and over, square to the boards, so it
never lies along another wire or across a part:

- off its board: half a column sideways from the hole, so the drop runs between two hole columns (a
  second wire from the same column takes the other side), then down past the board's edge;
- across: in a lane of its own in the band between the boards and the NUCLEO headers;
- onto the NUCLEO: down a column of its own beside the header (the outer side of a two-row header's
  column, the left of a single row), then sideways into the pin. In each group the shallowest pin takes
  the column nearest the header, so no wire crosses another's last leg;
- onto another board: up its own between-column slot to the hole.

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


def plan(jumpers):
    """{jumper id: [(x, y), ...]} for the flying jumpers, in mm, from end a to end b."""
    flying = [j for j in jumpers if is_flying(j)]
    lanes = {j.id: LANE_TOP + i*LANE_PITCH for i, j in enumerate(flying)}
    if flying and max(lanes.values()) > wiring.NUCLEO_Y - 3.0:
        raise ValueError(f'{len(flying)} flying jumpers need more room above the NUCLEO: raise NUCLEO_GAP')

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

    # NUCLEO ends: an approach column each, nearest the header for the shallowest pin of its group.
    groups = {}
    for j in flying:
        for h in (j.a, j.b):
            if h[0] == 'N':
                hx = wiring.hole_xy(h)[0]
                groups.setdefault((hx, _header_side(h)), []).append((wiring.hole_xy(h)[1], j.id, h))
    approach = {}
    for (hx, side), members in groups.items():
        for k, (_y, jid, h) in enumerate(sorted(members)):
            approach[(jid, h)] = hx + side*(APPROACH_FIRST + k*APPROACH_PITCH)

    paths = {}
    for j in flying:
        lane = lanes[j.id]

        def leg(h, inward):
            """The points from the lane to hole h (or reversed when inward is False)."""
            x, y = wiring.hole_xy(h)
            if h[0] == 'N':
                ax = approach[(j.id, h)]
                pts = [(ax, lane), (ax, y), (x, y)]
            else:
                sx = slot[(j.id, h)]
                pts = [(sx, lane), (sx, y), (x, y)]
            return pts if inward else pts[::-1]

        paths[j.id] = leg(j.a, False) + leg(j.b, True)
    return paths
