"""The backplane ends of the five EVM / pack leads (build/BACKPLANE.md sections 3 and 5) on the copper side.

Each lead goes in from the copper side at its hole (J5 SNS laps onto R7's free leg instead) and runs down the copper
face to the hole-1 edge, where it leaves the board for the EVM below. The board lies on three plain support pads
(stack.BP_SUPPORTS, cage.BP_PAD_D across) and the mux sits on foam over holes 2-9, so each lead keeps to its own lane:

  J5 BAT  (line 19, hole 6): down to hole 4.5 over the line 19-20 link, right along hole 4.5, down lane 22.5
  PACK +  (line 21, hole 6): right along hole 6, down lane 23.5
  J5 SNS  (R7's leg, line 24, hole 7): over to lane 24.5, down
  J3 GND  (line 12, hole 11): up to hole 12, right along it (under the mux header leads, clear of the joints on
          holes 11 and 13), down lane 25.3 beside SYS
  J3 SYS  (line 26, hole 6): straight down line 26 (the SYS / GND pair run side by side)

A straight drop down line 19 or 21 would cross the pad under s20.2. Paths are (line, hole, d), d = mm behind the copper
face; the last point is on the hole-1 edge (hole 0.5), and the drawing adds the loose end below it. Used by the Session 6
sheet (sheets/session6/scenes6.py) and layout check L7 (layout_checks.py), so the page and the check see the same
routes."""
import stack as st

LEAD_R = 0.7                         # 24 AWG stranded, insulated
LINK_LIFT = 0.8                      # a copper-side link (stack.WIRES "wire" between two backplane holes) lies flat
LINK_R = 0.8                         # 22 AWG solid, insulated (Adafruit 1311)
EDGE = 0.0                           # past the hole-1 edge (hole 0.5)
SENSE = tuple(int(v) for v in dict((r, p) for r, p, _n in st.BP_PARTS)["R7"]["2"][1:].split("."))   # R7's free leg


def _ends():
    out = []
    for kind, a, c, side, note in st.WIRES:
        if kind != "lead" or side != "copper":
            continue
        if isinstance(a, tuple) and a[0] in ("PG1", "U1") and isinstance(c, str) and c.startswith("BP:s"):
            out.append(tuple(int(v) for v in c[4:].split(".")))
        elif isinstance(a, tuple) and a[0] == "R7":
            out.append(SENSE)
    return out


ENDS = _ends()                       # (line, hole) of each lead's backplane end
LANE = {(21, 6): 23.5, (19, 6): 22.5, SENSE: 24.5, (12, 11): 25.3, (26, 6): 26.0}
WAY = {(21, 6): "along hole 6, down past line 23",
       (19, 6): "over the link, down past line 22",
       SENSE: "off R7's leg, down past line 24",
       (12, 11): "along hole 12, down beside SYS",
       (26, 6): "straight down line 26"}
assert sorted(ENDS) == sorted(LANE), (ENDS, list(LANE))


def path(ln, hl, front=1.6):
    """[(line, hole, d)] from the lead's joint to past the hole-1 edge. front: board thickness."""
    lane = LANE[(ln, hl)]
    if (ln, hl) == SENSE:                           # lapped along R7's free leg on the copper side
        return [(ln, hl, 4.6), (ln, hl, 2.4), (lane, hl - 0.4, 2.4), (lane, EDGE, 2.4)]
    head = [(ln, hl, -front - 1.0), (ln, hl, 0.0)]
    if hl == 11:                                    # J3 GND: up to hole 12 (between the XJ1 / R8 joints on hole 11
        #                                             and the B4 socket's tails on hole 13), along it under the mux
        #                                             header leads, down lane 25.3 beside SYS
        return head + [(ln, hl + 0.6, 1.9), (ln + 0.4, hl + 1, 1.9), (lane, hl + 1, 1.9), (lane, EDGE, 2.4)]
    if ln == 19:                                    # J5 BAT: over the line 19-20 link at hole 5, clear of the pad
        return head + [(ln, hl, 2.6), (ln, 4.5, 2.6), (lane, 4.5, 2.6), (lane, EDGE, 2.4)]
    if ln == lane:
        return head + [(ln, hl, 2.4), (ln, EDGE, 2.4)]
    return head + [(ln, hl, 2.4), (lane, hl, 2.4), (lane, EDGE, 2.4)]


def links():
    """[((line, hole), (line, hole))] of the copper-side links between two backplane holes (stack.WIRES)."""
    out = []
    for kind, a, c, side, _n in st.WIRES:
        if kind == "wire" and side == "copper" and isinstance(a, str) and a.startswith("BP:s") \
                and isinstance(c, str) and c.startswith("BP:s"):
            out.append(tuple(tuple(int(v) for v in e[4:].split(".")) for e in (a, c)))
    return out


def link_path(a, b, front=1.6):
    """[(line, hole, d)] of a copper-side link: through hole a, along at LINK_LIFT, back through hole b."""
    return [(*a, -front - 1.0), (*a, 0.0), (*a, LINK_LIFT), (*b, LINK_LIFT), (*b, 0.0), (*b, -front - 1.0)]
