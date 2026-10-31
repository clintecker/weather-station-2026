"""The build-progression record's checks on the breadboard model (wiring.toml), without KiCad.

docs/superpowers/specs/2026-10-29-build-progression-decisions.md: D3 checks 1-6 and 9, check 8's ISET
constants (check_iset: step 1 exit 7), the H7 lead lengths (with its dated note of 2026-10-30: the 100 mm
cap is for L_REG_VIN and L_TIE only), the lead geometry, the M6 power-path segments, and M7's placement
rule (check_meter_at_jack: each meter pull-up and filter in its jack pin's own strip). D3 check 7 and
check 8's pins (the wiring guide both ways, the firmware pins) are wiring.check_guide,
wiring.check_guide_reverse and wiring.check_firmware.

Every check returns a list of problem strings, empty when the model passes. A check that needs the
breadboard jumpers takes them (wiring.plan_jumpers) or plans them itself.

Ground domains (record P4, D2): a node is 'power' when its joint, its part or a lead on it (other than
the TIE) says `domain = "power"`; 'logic' when it is a NUCLEO pin, a ground rail, or so marked; and
unmarked otherwise. Unmarked nodes take the domain of whatever they are joined to.

Standard library only."""
import math
import re
from collections import deque
from pathlib import Path

import wiring

P1_TAG = 'P1 regulator'
# Record P1, D3 check 1, 6.1 and 6.2: the regulator's supply chain, by stable id, exactly these seven.
# Every member carries the tag, and nothing else is excepted. The regulator's own pins (REG.VIN,
# REG.GND) are not members: a force-net pin in a breadboard hole is allowed only where a tagged chain
# member lands on its strip (L_REG_VIN on REG.VIN's strip), see _member_excused.
P1_CHAIN = ('L_REG_VIN', 'L_TIE', 'L_NUC_RET', 'LK_REG_SHUNT', 'SHUNT', 'L_REG_3V3', 'LK_3V3_CN6_4')
# The chain in current order, with its two ends (the regulator's pins and CN6.4): each neighbour pair
# shares a node by itself, so no planner jumper and no rail run sits in the chain (D3 check 1). The
# return side lands on the regulator's GND strip.
P1_ORDER = (('REG.VIN', 'L_REG_VIN'), ('REG.GND', 'L_TIE'), ('REG.GND', 'L_NUC_RET'),
            ('REG.VOUT', 'LK_REG_SHUNT'), ('LK_REG_SHUNT', 'SHUNT'), ('SHUNT', 'L_REG_3V3'),
            ('L_REG_3V3', 'LK_3V3_CN6_4'), ('LK_3V3_CN6_4', 'N:CN6.4'))
BATTERY_CLASS = 'battery lead'                     # wiring.NET_CLASSES: always a force net
CURRENT_CLASSES = (BATTERY_CLASS, 'power', 'ground')  # nets whose strips may carry current: no sense tap
GROUND_CLASS = 'ground'

TIE = 'L_TIE'                                      # record P4: the one conductor from STAR to logic ground
STAR, STAR_SPARE = 'WAGO_STAR', 5                  # P4: position 5 stays free for step 1b exit (g)
OFF_RAIL_LEADS = ('L_OLED_GND', 'L_OLED_VCC', 'L_NUC_RET')   # D3 check 3, N4: never on a board-B rail
OLED_GND, OLED_RETURN = 'OLED.GND', 'N:CN10.20'    # the OLED's return goes straight to CN10.20

GAUGE_SENSE = 'GAUGE.BAT1+'
INA_PLUS = ('INA.VIN+', 'INA.X1_VINP')             # the shunt's cell side: header pin, screw terminal
INA_MINUS = ('INA.VIN-', 'INA.X1_VINM')            # its charger side

DIVIDER = ('R4', 'R5', 'R6')                       # VBUS -> R4 -> R5 -> VIN_SENSE -> R6 -> GND
DIVIDER_DEFINES = (('firmware/stage0-node/App/power_config.h', 'POWER_VIN_DIVIDER_PPM'),
                   ('firmware/benchlink/App/benchlink.c', 'VIN_DIVIDER_PPM'))

# D3 check 8, the node's ISET constants (record M2, 1.4; step 1 exit 7). R_ISET is the charger's own
# (CHGR `iset_ohms`); the gain is CHGR's `iset_gain_ppm` (the M2 per-board fit) once it is fitted, and
# the PB1 node's R_IPD / (R_ISER + R_IPD) until then. The host logger applies both to
# benchlink's packet (benchlink.c carries neither), so its defaults are held to the same values.
CHARGER = 'CHGR'
ISET_SERIES, ISET_PULLDOWN = 'R_ISER', 'R_IPD'
NODE_CONFIG = 'firmware/stage0-node/App/power_config.h'
R_ISET_DEFINE, ISET_GAIN_DEFINE = 'POWER_R_ISET_OHM', 'POWER_ISET_GAIN_PPM'
HOST_LOGGER = 'tools/benchlink_log.py'
HOST_R_ISET, HOST_ISET_GAIN = 'R_ISET_OHM', 'ISET_GAIN'      # ohm; the gain as a fraction (ppm / 1e6)
ISET_FIT_SPAN = 0.10   # the farthest an M2 fit may sit from the network's nominal gain (M7: 10 %)

# Record H7, mm.
PIGTAIL_MAX = 60
FORCE_SOLID_MAX = 50
REG_SUPPLY_MAX, REG_SUPPLY_LEADS = 100, ('L_REG_VIN', 'L_TIE')
ROUTED_LEADS = ('L_REG_3V3', 'L_NUC_RET')          # length by routing, bounded by C20 and C21 (H7 dated note)
SIGNAL_MAX = 200
SUPPLY_MAX = 350
GEOMETRY_SLACK = 0.01                              # mm of rounding a length may fall short of its span

# Record M6: the segments found by their two ends; PATH_PACK_POS and PATH_PACK_NEG come from the
# leads' `segment` keys. The path runs over force leads, joints and these series parts.
SEGMENT_ENDS = {'PATH_POS': ('PACK.+', 'CHGR.BATT2'), 'PATH_NEG': ('CHGR.BATT1', 'PACK.-'),
                'PATH_CELL_OUT': ('J:WAGO_CELL_POS', 'J:WAGO_SYS_OUT')}
SERIES_HOPS = (('INA.X1_VINP', 'INA.X1_VINM'), ('CHGR.BATT2', 'CHGR.SYSOUT2'))

# Record M7's placement rule: each meter line's jack pin (a BOB-14021 pin) and the pins of its pull-up and
# filter that sit on the line share one strip, so no jumper sits between the jack pin and its pull-up: an
# open jumper is then always between the pull-up and the MCU, where the counter link probe (or, for the vane,
# the direction table) sees it.
METER_JACK = (('CUPS', 'BOBW.4', ('R1.1', 'C_CUPS.1')), ('RAIN', 'BOBR.4', ('R2.1', 'C_RAIN.1')),
              ('VANE', 'BOBW.5', ('R3.1',)))


# ---- helpers ----

def _part_of(end):
    return end.split('.', 1)[0]


def _node(w, end):
    """The connectivity node of an end, or None when the model has no such end."""
    try:
        return wiring.raw_node(w, end)
    except (ValueError, KeyError):
        return None


def _in_contact(w, end):
    """True when an end sits in a breadboard hole or a NUCLEO header pin: a hole, the hole pin of a part
    plugged into a breadboard (not one only drawn there), or a NUCLEO pin."""
    e = wiring.parse_end(w, end)
    if e[0] == 'pin':
        return not w.parts[_part_of(end)].off_board
    return e[0] in ('hole', 'nucleo')


def _tagged(item):
    return getattr(item, 'exception', None) == P1_TAG


def _plan(w, jumpers):
    """(jumpers, problems): the given jumpers, or the planner's."""
    if jumpers is not None:
        return list(jumpers), []
    try:
        return wiring.plan_jumpers(w), []
    except wiring.PlanError as e:
        return [], [f'the jumpers cannot be planned: {e}']


def _test_point_strips(w):
    """strip -> 'PART.PIN' of the test point on it."""
    return {wiring.strip(p.pins[n], w.split_rails): f'{p.id}.{n}' for p in w.parts.values() for n in p.test_points}


def _ground_rails(w):
    """The rail strips of the ground nets (logic ground: power ground never reaches a breadboard)."""
    return {s for net, cls in w.net_class.items() if cls == GROUND_CLASS for s in wiring._rail_strips(w, net)}


def _strip_nets(w, key):
    """The nets with a member or a rail on a node."""
    return {n for n, ms in w.nets.items()
            if key in wiring._rail_strips(w, n) or any(_node(w, m) == key for m in ms)}


# ---- D3 check 1 (P1) ----

def _force_lead_problems(w):
    problems = []
    for lead in w.leads:
        if lead.role != 'force' or _tagged(lead):
            continue
        problems += [f'{lead.id}: force lead ends in a breadboard or header contact at {end} (P1, D3 check 1)'
                     for end in (lead.a, lead.b) if _in_contact(w, end)]
    return problems


def _force_nets(w):
    """The nets that carry battery, charge or load current: every 'battery lead' net, and the net of
    each untagged force lead (so SYS_OUT, class 'power', is one through L_SYSOUT_POS and L_RLOAD_A, and
    GND through the pack and load returns). The P1 chain's own nets are not force nets by its leads."""
    nets = {n for n, cls in w.net_class.items() if cls == BATTERY_CLASS}
    return nets | {k.net for k in w.leads if k.role == 'force' and not _tagged(k)}


def _chain_landings(w):
    """The nodes where a P1-tagged lead or link ends: the strips the regulator chain feeds."""
    ends = [e for k in w.leads if _tagged(k) for e in (k.a, k.b)]
    ends += [e for k in w.link_info if _tagged(k) for e in (k.a, k.b)]
    return {_node(w, e) for e in ends} - {None}


def _member_excused(w, member, landings):
    """A force-net member in a contact is allowed as a zero-current test point, a pin of a P1-tagged
    part, or a pin on a strip where a tagged chain member lands (REG.VIN under L_REG_VIN)."""
    if member.startswith('N:'):
        return False
    part = w.parts[_part_of(member)]
    return member.split('.', 1)[1] in part.test_points or _tagged(part) or _node(w, member) in landings


def _carries_force(w, net, member, labels):
    """Every member of a non-ground force net; on a ground net, only the members of the power domain
    (the logic ground's members are signal returns, D3 check 3's)."""
    if w.net_class[net] != GROUND_CLASS:
        return True
    return 'power' in labels.get(_node(w, member), set())


def _force_member_problems(w):
    landings, labels, problems = _chain_landings(w), _domain_labels(w), []
    for net in sorted(_force_nets(w)):
        problems += [f'{net}: {m} is in a breadboard or header contact and is neither a test point nor on '
                     f'a "{P1_TAG}" landing (P1, D3 check 1)'
                     for m in w.nets[net] if _carries_force(w, net, m, labels) and _in_contact(w, m)
                     and not _member_excused(w, m, landings)]
    return problems


def _taggable(w):
    """Every item that can carry `exception`: (kind, item) for parts, links and leads."""
    return ([('part', p) for p in w.parts.values()] + [('link', k) for k in w.link_info]
            + [('lead', k) for k in w.leads])


def _chain_problems(w):
    items = _taggable(w)
    problems = []
    for cid in P1_CHAIN:
        found = [(kind, item) for kind, item in items if item.id == cid]
        if not found:
            problems.append(f'{cid}: P1 chain member missing from the model (P1, D3 check 1)')
        problems += [f'{kind} {cid}: P1 chain member without exception = "{P1_TAG}" (P1, D3 check 1)'
                     for kind, item in found if not _tagged(item)]
    problems += [f'{kind} {item.id}: exception = "{P1_TAG}" outside the P1 chain (P1, D3 check 1)'
                 for kind, item in items if _tagged(item) and item.id not in P1_CHAIN]
    return problems


def _chain_ends(w, name):
    """The ends of a chain item: a lead's or link's two ends, a part's pins, or the name itself (an end)."""
    for k in list(w.leads) + list(w.link_info):
        if k.id == name:
            return (k.a, k.b)
    if name in w.parts:
        return tuple(f'{name}.{pin}' for pin in w.parts[name].pins)
    return (name,)


def _order_problems(w):
    """Each P1_ORDER pair shares a node directly: the chain runs through its own members only."""
    problems = []
    for a, b in P1_ORDER:
        nodes_a = {_node(w, e) for e in _chain_ends(w, a)} - {None}
        if not nodes_a & ({_node(w, e) for e in _chain_ends(w, b)} - {None}):
            problems.append(f'{a} and {b} share no strip, joint or pin: the P1 chain runs through something '
                            'outside it, a planner jumper or a rail run (P1, D3 check 1)')
    return problems


def check_force_off_breadboard(w):
    """D3 check 1: no force lead ends in a breadboard hole, a plugged-in part's hole pin or a NUCLEO pin,
    and no force-net member (CELL_POS, BATT, SYS_OUT, the power-domain ground) sits in one, unless the
    lead is tagged "P1 regulator" or the member is a test point or on a tagged lead's landing; every
    P1_CHAIN member carries the tag and nothing else does; and the chain is contiguous (P1_ORDER: each
    member lands where the next starts, so no untagged jumper or rail run carries the regulator current)."""
    chain = _chain_problems(w)
    return _force_lead_problems(w) + _force_member_problems(w) + chain + ([] if chain else _order_problems(w))


# ---- D3 check 2 ----

def _position_problems(w):
    """One lead end per joint position; a lead names its position."""
    seen, problems = {}, []
    for lead in w.leads:
        for end in (lead.a, lead.b):
            e = wiring.parse_end(w, end)
            if e[0] != 'joint':
                continue
            if e[2] is None:
                problems.append(f'{lead.id}: lands on joint {e[1]} without a position (D3 check 2)')
            else:
                seen.setdefault((e[1], e[2]), []).append(lead.id)
    for (joint, n), ids in sorted(seen.items()):
        if len(ids) > 1:
            problems.append(f'J:{joint}.{n} holds {len(ids)} lead ends ({", ".join(ids)}): one per clamp '
                            f'position (D3 check 2)')
    return problems


def _declared_problem(w, lead, end):
    """A sense lead's end lands on a declared node of its own net: a joint listed in the net, at a
    named position; a pin, a terminal or a NUCLEO pin of the net; or a hole on a strip the net holds by a
    member or a rail (never an empty strip, which the loader lets take the other end's net)."""
    e = wiring.parse_end(w, end)
    members = w.nets[lead.net]
    if e[0] == 'insulated':
        return None
    if e[0] == 'joint':
        ok = f'J:{e[1]}' in members or any(m.startswith(f'J:{e[1]}.') for m in members)
    elif e[0] == 'hole':
        key = wiring.raw_node(w, end)
        ok = key in wiring._rail_strips(w, lead.net) or any(_node(w, m) == key for m in members)
    else:
        ok = end in members
    return None if ok else (f'{lead.id}: sense end {end} is not a declared landing of its net {lead.net} '
                            f'(D3 check 2)')


def _sense_end_problem(w, lead, end, test_points, rails):
    """A sense lead's end in a contact: allowed on a logic ground rail or on a strip that carries no
    battery, power or ground net (a signal such as THERM). A test-point strip is D3 check 6's alone (it
    holds nothing but its pin), so it is not judged here."""
    e = wiring.parse_end(w, end)
    if e[0] in ('joint', 'terminal', 'insulated') or not _in_contact(w, end):
        return None
    key = wiring.raw_node(w, end)
    if key in test_points or key in rails:
        return None
    busy = sorted(n for n in _strip_nets(w, key) if w.net_class[n] in CURRENT_CLASSES)
    if not busy:
        return None
    return (f'{lead.id}: sense lead lands at {end}, on a strip of {", ".join(busy)} that is neither a test '
            f'point nor a logic ground rail (D3 check 2)')


def check_sense_landings(w):
    """D3 check 2: each joint position holds at most one lead end (no sense lead in a force lead's
    clamp position); each sense lead end lands on its declared joint position, pin, terminal or a strip
    of its own net; and no sense end sits on a strip that carries current, other than a logic ground-rail
    hole (L_NTC_RET). A sense end on a test-point strip fails D3 check 6, not this one."""
    test_points, rails = _test_point_strips(w), _ground_rails(w)
    problems = _position_problems(w)
    for lead in (k for k in w.leads if k.role == 'sense'):
        for end in (lead.a, lead.b):
            problems += [p for p in (_declared_problem(w, lead, end),
                                     _sense_end_problem(w, lead, end, test_points, rails)) if p]
    return problems


# ---- D3 check 3 (P4, N4) ----

def _edges(w, jumpers):
    """Every conductor as (node, node, lead id or None): leads with two live ends, the ties inside
    parts, the NUCLEO's own ties, and the jumpers."""
    edges = []
    for lead in w.leads:
        a, b = wiring.raw_node(w, lead.a), wiring.raw_node(w, lead.b)
        if a is not None and b is not None:
            edges.append((a, b, lead.id))
    for part in w.parts.values():
        for group in part.internal:
            first = wiring.raw_node(w, f'{part.id}.{group[0]}')
            edges += [(first, wiring.raw_node(w, f'{part.id}.{n}'), None) for n in group[1:]]
    for tie in w.ties:
        edges += [(f'N:{tie[0]}', f'N:{p}', None) for p in tie[1:]]
    edges += [(wiring.strip(j.a, w.split_rails), wiring.strip(j.b, w.split_rails), None) for j in jumpers]
    return edges


def _union(edges):
    u = wiring._Union()
    for a, b, _ in edges:
        u.join(a, b)
    return u


def _ground_nodes(w):
    nodes = {_node(w, m) for net, ms in w.nets.items() if w.net_class[net] == GROUND_CLASS for m in ms}
    nodes |= {_node(w, e) for k in w.leads if w.net_class[k.net] == GROUND_CLASS for e in (k.a, k.b)}
    return (nodes | _ground_rails(w)) - {None}


def _mark_parts(w, mark):
    for part in w.parts.values():
        for name in (*part.pins, *part.terminals):
            mark(_node(w, f'{part.id}.{name}'), part.domain)


def _domain_labels(w):
    """Ground node -> {'power'} or {'logic'} (or both: a fault) from the explicit marks."""
    ground, labels = _ground_nodes(w), {}

    def mark(node, domain):
        if node in ground and domain:
            labels.setdefault(node, set()).add(domain)
    for joint in w.joints.values():
        mark(f'J:{joint.id}', joint.domain)
    _mark_parts(w, mark)
    for lead in w.leads:
        if lead.id != TIE:
            mark(_node(w, lead.a), lead.domain)
            mark(_node(w, lead.b), lead.domain)
    for node in ground:
        if node.startswith('N:') or node in _ground_rails(w):
            mark(node, 'logic')
    return labels


def _component_domains(u, labels):
    out = {}
    for node, domains in labels.items():
        out.setdefault(u.find(node), set()).update(domains)
    return out


def _mixed(u, labels):
    """The nodes of each component that holds both a power and a logic node."""
    roots = {r for r, d in _component_domains(u, labels).items() if len(d) > 1}
    groups = {}
    for node in labels:
        if u.find(node) in roots:
            groups.setdefault(u.find(node), []).append(node)
    return [sorted(g) for g in groups.values()]


def _crossings(w, edges, labels):
    """The ground leads that join a power component to a logic one: every other conductor first, then
    each ground lead (L_TIE last) joined unless its two sides are of opposite domains."""
    ground = {k.id for k in w.leads if w.net_class[k.net] == GROUND_CLASS}
    u = _union(e for e in edges if e[2] not in ground)
    pending = sorted((e for e in edges if e[2] in ground), key=lambda e: (e[2] == TIE, e[2]))
    crossing = []
    for a, b, lid in pending:
        domains = _component_domains(u, labels)
        da, db = domains.get(u.find(a), set()), domains.get(u.find(b), set())
        if len(da) == 1 and len(db) == 1 and da != db:
            crossing.append(lid)
        else:
            u.join(a, b)
    return crossing


def _tie_problems(w, edges, labels):
    tie = next((k for k in w.leads if k.id == TIE), None)
    problems = [] if tie else [f'no lead {TIE}: the one conductor from STAR to logic ground (P4, D3 check 3)']
    if tie and tie.role != 'force':
        problems.append(f'{TIE}: role {tie.role}, not force (P4)')
    problems += [f'without {TIE}, power and logic ground meet: {", ".join(g)} (P4, D3 check 3)'
                 for g in _mixed(_union(e for e in edges if e[2] != TIE), labels)]
    crossing = _crossings(w, edges, labels)
    if tie and TIE not in crossing:
        problems.append(f'{TIE} does not join power ground to logic ground (P4, D3 check 3)')
    others = [c for c in crossing if c != TIE]
    if others:
        problems.append(f'{", ".join(others)} also join power and logic ground: {TIE} must be the only one '
                        f'(P4, D3 check 3)')
    return problems


def _off_rail_problems(w):
    problems = []
    for lead in (k for k in w.leads if k.id in OFF_RAIL_LEADS):
        for end in (lead.a, lead.b):
            e = wiring.parse_end(w, end)
            if e[0] in ('hole', 'pin') and e[1][0] == 'B' and e[1][1] in wiring.RAILS:
                problems.append(f'{lead.id}: ends on the board-B rail at {end}; a logic supply or return '
                                f'goes straight to the NUCLEO (N4, D3 check 3)')
    return problems


def _oled_problems(w, edges):
    """OLED.GND reaches no board-B ground rail except through N:CN10.20."""
    node = _node(w, OLED_GND)
    if node is None:
        return []
    u = _union(e for e in edges if OLED_RETURN not in (e[0], e[1]))
    rails = sorted(r for r in _ground_rails(w) if r.startswith('B:') and u.find(r) == u.find(node))
    return [f'{OLED_GND} reaches the board-B ground rail {r} other than through {OLED_RETURN} (D3 check 3)'
            for r in rails]


def _spare_problems(w):
    if STAR not in w.joints:
        return []
    return [f'{lead.id}: uses {STAR} position {STAR_SPARE}, the spare kept for step 1b exit (g) (P4)'
            for lead in w.leads for end in (lead.a, lead.b)
            if wiring.parse_end(w, end) == ('joint', STAR, STAR_SPARE)]


def check_single_tie(w, jumpers=None):
    """D3 check 3 (P4, N4): without L_TIE the power and logic ground domains are apart, with it they
    meet, and no other lead joins them; L_OLED_GND, L_OLED_VCC and L_NUC_RET never end on a board-B
    rail; OLED.GND reaches the board-B ground rail only through N:CN10.20; STAR position 5 stays free.
    L_NTC_RET on the board-B logic rail is allowed."""
    jumpers, problems = _plan(w, jumpers)
    if problems:
        return problems
    edges = _edges(w, jumpers)
    return (_tie_problems(w, edges, _domain_labels(w)) + _off_rail_problems(w) + _oled_problems(w, edges)
            + _spare_problems(w))


# ---- D3 checks 4 and 5 ----

def _net_of(w):
    return {m: n for n, ms in w.nets.items() for m in ms}


def check_gauge_upstream(w):
    """D3 check 4: the gauge's sense (GAUGE.BAT1+) is on the net of INA.X1_VINP, the cell side of the
    shunt."""
    net_of = _net_of(w)
    gauge, plus = net_of.get(GAUGE_SENSE), net_of.get('INA.X1_VINP')
    if gauge is None or plus is None:
        missing = [m for m, n in ((GAUGE_SENSE, gauge), ('INA.X1_VINP', plus)) if n is None]
        return [f'{", ".join(missing)}: in no net, so the gauge sense cannot be checked (D3 check 4)']
    if gauge != plus:
        return [f'{GAUGE_SENSE} is on {gauge}, not on {plus} with INA.X1_VINP: the gauge senses the cell '
                f'upstream of the shunt (D3 check 4)']
    return []


def _has(w, member):
    part, _, pin = member.partition('.')
    return part in w.parts and (pin in w.parts[part].pins or pin in w.parts[part].terminals)


def check_shunt_only(w, jumpers=None):
    """D3 check 5: the shunt's two sides (INA VIN+ / X1_VINP and VIN- / X1_VINM) are on different nets,
    and nothing but the INA228's shunt joins them."""
    plus, minus = [m for m in INA_PLUS if _has(w, m)], [m for m in INA_MINUS if _has(w, m)]
    if not plus or not minus:
        return ['INA: no shunt pins (VIN+ or X1_VINP, VIN- or X1_VINM) in the model (D3 check 5)']
    net_of = _net_of(w)
    pn, mn = {net_of.get(m) for m in plus}, {net_of.get(m) for m in minus}
    problems = [f'{m}: in no net (D3 check 5)' for m in plus + minus if net_of.get(m) is None]
    shared = (pn & mn) - {None}
    if shared:
        problems.append(f'INA shunt: both sides are on {", ".join(sorted(shared))} (D3 check 5)')
    jumpers, plan = _plan(w, jumpers)
    problems += plan
    problems += [f'INA shunt: {", ".join(sorted(g & set(plus + minus)))} are joined other than through the '
                 f'shunt (D3 check 5)' for g in wiring.connectivity(w, jumpers) if g & set(plus) and g & set(minus)]
    return problems


# ---- D3 check 6 (P2) ----

def _strip_users(w, jumpers):
    """strip -> what lands on it: other part pins, jumper ids, lead ids (a lead on the pin itself too)."""
    users = {}
    for part in w.parts.values():
        for name, h in part.pins.items():
            users.setdefault(wiring.strip(h, w.split_rails), []).append(('pin', f'{part.id}.{name}'))
    for j in jumpers:
        for h in (j.a, j.b):
            users.setdefault(wiring.strip(h, w.split_rails), []).append(('jumper', j.id))
    for lead in w.leads:
        for end in (lead.a, lead.b):
            e = wiring.parse_end(w, end)
            if e[0] in ('hole', 'pin', 'nucleo'):
                users.setdefault(wiring.strip(e[1], w.split_rails), []).append(('lead', lead.id))
    return users


def check_test_point_strips(w, jumpers):
    """D3 check 6 (P2): each test-point pin is alone in its strip: no other part pin, no jumper and no
    lead end there."""
    users = _strip_users(w, jumpers)
    problems = []
    for key, tp in sorted(_test_point_strips(w).items()):
        others = [f'{kind} {name}' for kind, name in users.get(key, []) if (kind, name) != ('pin', tp)]
        if others:
            problems.append(f'test point {tp}: strip {key} also holds {", ".join(others)} (P2, D3 check 6)')
    return problems


# ---- D3 check 9 ----

def _define(path, name):
    """The integer value of '#define NAME <int>U?' in a file, or None."""
    m = re.search(rf'^\s*#define\s+{re.escape(name)}\s+(\d+)U?\b', path.read_text(), re.M)
    return int(m.group(1)) if m else None


def _model_divider(w):
    """(ppm, problems): (R4 + R5 + R6) / R6 x 1e6, rounded to the whole ppm the firmware's integer define
    can hold (half away from zero). Record M2 stores the measured ratio: once R4-R6 carry
    `measured_ohms` (each resistor's DMM reading), those values give the ratio; until then their
    nominal `ohms` do. All three are measured or none: a mix would store neither ratio."""
    missing = [p for p in DIVIDER if p not in w.parts or w.parts[p].ohms is None]
    if missing:
        return None, [f'{", ".join(missing)}: no part with `ohms`, so the divider cannot be checked (D3 check 9)']
    measured = [p for p in DIVIDER if w.parts[p].measured_ohms is not None]
    if measured and len(measured) != len(DIVIDER):
        return None, [f'{", ".join(measured)}: `measured_ohms` on only some of {", ".join(DIVIDER)}; record M2 '
                      'measures all three (D3 check 9)']
    ohms = [w.parts[p].measured_ohms if measured else w.parts[p].ohms for p in DIVIDER]
    return math.floor(sum(ohms)*1_000_000/ohms[2] + 0.5), []


def check_divider(w, root):
    """D3 check 9: POWER_VIN_DIVIDER_PPM (stage0-node power_config.h) and VIN_DIVIDER_PPM
    (benchlink.c) each equal the model's (R4 + R5 + R6) / R6 in ppm, exactly (rounded to the whole ppm):
    from R4-R6's `measured_ohms` once they are measured (record M2), from their `ohms` until then."""
    ppm, problems = _model_divider(w)
    for rel, name in DIVIDER_DEFINES:
        path = Path(root)/rel
        value = _define(path, name) if path.is_file() else None
        if value is None:
            problems.append(f'{rel}: no #define {name} (D3 check 9)')
        elif ppm is not None and value != ppm:
            problems.append(f'{rel}: {name} {value} does not equal the model\'s {ppm} = (R4 + R5 + R6) / R6 '
                            f'in ppm (D3 check 9)')
    return problems


# ---- D3 check 8: the ISET constants ----

def _iset_fit(charger, nominal):
    """(gain ppm, problems): the charger's `iset_gain_ppm` (record M2's per-board fit) when the model holds
    one, else the network's nominal gain. A fit more than ISET_FIT_SPAN from the nominal is refused: the
    network or the fit is wrong (M7's ISET cross-check allows 10 %)."""
    fit = charger.iset_gain_ppm if charger is not None else None
    if fit is None:
        return nominal, []
    fit = math.floor(fit + 0.5)
    if abs(fit - nominal) > nominal*ISET_FIT_SPAN:
        return None, [f'{CHARGER}: iset_gain_ppm {fit} is more than {ISET_FIT_SPAN:.0%} from the network\'s '
                      f'{nominal} ppm: check the ISET network and the fit (record M2, D3 check 8)']
    return fit, []


def _model_iset(w):
    """(r_iset ohm, gain ppm, problems): the charger's `iset_ohms` and the ISET gain: the charger's
    `iset_gain_ppm` (the M2 per-board fit) when present, else R_IPD / (R_ISER + R_IPD) x 1e6, rounded to
    the whole ppm (half away from zero); None for a value the model cannot give."""
    problems = []
    charger = w.parts.get(CHARGER)
    r_iset = charger.iset_ohms if charger is not None else None
    if r_iset is None:
        problems.append(f'{CHARGER}: no `iset_ohms`, so R_ISET cannot be checked (D3 check 8)')
    missing = [p for p in (ISET_SERIES, ISET_PULLDOWN) if p not in w.parts or w.parts[p].ohms is None]
    if missing:
        problems.append(f'{", ".join(missing)}: no part with `ohms`, so the ISET gain cannot be checked (D3 check 8)')
        return r_iset, None, problems
    series, pulldown = w.parts[ISET_SERIES].ohms, w.parts[ISET_PULLDOWN].ohms
    gain, fit_problems = _iset_fit(charger, math.floor(pulldown*1_000_000/(series + pulldown) + 0.5))
    return r_iset, gain, problems + fit_problems


def _host_value(path, name, scale=1):
    """The number of a module-level 'NAME = <number>' in a Python file times `scale`, rounded to the
    whole unit (half away from zero), or None when the file or the name is missing."""
    m = re.search(rf'^{re.escape(name)}\s*=\s*([0-9.]+)', path.read_text(), re.M) if path.is_file() else None
    return math.floor(float(m.group(1))*scale + 0.5) if m else None


def _compare(rel, name, value, want, what):
    if value is None:
        return [f'{rel}: no {name} (D3 check 8)']
    if want is not None and value != want:
        return [f'{rel}: {name} {value:.12g} does not equal the model\'s {want:.12g} = {what} (D3 check 8)']
    return []


def _gain_source(w):
    """How the model's ISET gain was found, for the problem text."""
    charger = w.parts.get(CHARGER)
    if charger is not None and charger.iset_gain_ppm is not None:
        return f'{CHARGER} iset_gain_ppm (the M2 fit)'
    return f'{ISET_PULLDOWN} / ({ISET_SERIES} + {ISET_PULLDOWN}) in ppm'


def check_iset(w, root):
    """D3 check 8's ISET constants (record step 1 exit 7): POWER_R_ISET_OHM equals the charger's
    `iset_ohms`, and POWER_ISET_GAIN_PPM equals the charger's `iset_gain_ppm` (the M2 per-board fit) or,
    before the fit, R_IPD / (R_ISER + R_IPD) in ppm, exactly; the host logger's R_ISET_OHM and ISET_GAIN
    (tools/benchlink_log.py) carry the same two values. The model takes a measured or fitted value first."""
    r_iset, gain, problems = _model_iset(w)
    node, source = Path(root)/NODE_CONFIG, _gain_source(w)
    for name, want, what in ((R_ISET_DEFINE, r_iset, f'{CHARGER} iset_ohms'), (ISET_GAIN_DEFINE, gain, source)):
        problems += _compare(NODE_CONFIG, name, _define(node, name) if node.is_file() else None, want, what)
    host = Path(root)/HOST_LOGGER
    for name, value, want, what in (
            (HOST_R_ISET, _host_value(host, HOST_R_ISET), r_iset, f'{CHARGER} iset_ohms'),
            (HOST_ISET_GAIN, _host_value(host, HOST_ISET_GAIN, 1_000_000), gain, f'{source}, as ppm')):
        problems += _compare(HOST_LOGGER, name, value, want, what)
    return problems


# ---- H7 lead lengths and the lead geometry ----

def _length_limit(lead):
    """(limit mm or None for no cap, rule)."""
    if lead.kind == 'cable':
        return None, 'a cable'
    if lead.kind == 'pigtail':
        return PIGTAIL_MAX, 'a pigtail half'
    if lead.role == 'sense':
        return None, 'a sense lead'
    if lead.role == 'signal':
        return SIGNAL_MAX, 'a signal lead'
    if lead.role == 'supply':
        return SUPPLY_MAX, 'a supply lead'
    if lead.id in ROUTED_LEADS:
        return None, 'routed (C20, C21)'
    if lead.id in REG_SUPPLY_LEADS:
        return REG_SUPPLY_MAX, 'a regulator-supply lead'
    return FORCE_SOLID_MAX, 'a solid force lead'


def check_lead_lengths(w):
    """Record H7 (dated note 2026-10-30): pigtail halves <= 60 mm; solid force leads <= 50 mm, except
    L_REG_VIN and L_TIE <= 100 mm; L_REG_3V3 and L_NUC_RET uncapped here (bounded by C20 and C21 at
    preflight; their P1 tag is D3 check 1's); signal leads <= 200 mm; supply leads <= 350 mm; sense
    leads and cables any length."""
    problems = []
    for lead in w.leads:
        limit, rule = _length_limit(lead)
        if limit is not None and lead.length_mm > limit:
            problems.append(f'{lead.id}: {lead.length_mm:g} mm, over {limit} mm for {rule} (H7)')
    return problems


def check_lead_geometry(w):
    """Each lead is at least as long as the straight line between its drawn ends. A NUCLEO end (the
    headers are not to scale) or an insulated end skips the lead."""
    problems = []
    for lead in w.leads:
        a, b = wiring.end_xy(w, lead.a), wiring.end_xy(w, lead.b)
        if a is None or b is None:
            continue
        span = math.dist(a, b)
        if lead.length_mm + GEOMETRY_SLACK < span:
            problems.append(f'{lead.id}: {lead.length_mm:g} mm is shorter than the {span:.1f} mm between '
                            f'{lead.a} and {lead.b} as drawn')
    return problems


# ---- M6 power-path segments ----

def _path_graph(w, leads):
    """node -> [(neighbour, step)]: a step is ('lead', id), ('part', id) for a series part, or None for
    a tie inside a part."""
    adj = {}

    def add(a, b, step):
        if a is not None and b is not None:
            adj.setdefault(a, []).append((b, step))
            adj.setdefault(b, []).append((a, step))
    for lead in leads:
        add(_node(w, lead.a), _node(w, lead.b), ('lead', lead.id))
    for a, b in SERIES_HOPS:
        add(_node(w, a), _node(w, b), ('part', _part_of(a)))
    for part in w.parts.values():
        for group in part.internal:
            for name in group[1:]:
                add(_node(w, f'{part.id}.{group[0]}'), _node(w, f'{part.id}.{name}'), None)
    return adj


def _route(adj, start, goal):
    """The shortest walk from start to goal as [('lead'|'joint'|'part', id)], or None."""
    prev, queue = {start: None}, deque([start])
    while queue:   # bound: each node enters the queue once
        node = queue.popleft()
        if node == goal:
            break
        for nxt, step in sorted(adj.get(node, ()), key=lambda t: (t[0], t[1] or ('', ''))):
            if nxt not in prev:
                prev[nxt] = (node, step)
                queue.append(nxt)
    if goal not in prev:
        return None
    out, node = [], goal
    while node is not None:   # bound: the walk back has as many steps as the walk out
        if node.startswith('J:'):
            out.append(('joint', node[2:]))
        back = prev[node]
        if back is not None and back[1] is not None:
            out.append(back[1])
        node = back[0] if back else None
    return out[::-1]


def _tagged_route(w, leads):
    """The leads that carry one `segment` key, in order from the end that is not a joint."""
    count = {}
    for lead in leads:
        for end in (lead.a, lead.b):
            node = _node(w, end)
            count[node] = count.get(node, 0) + 1
    ends = sorted((n for n, c in count.items() if c == 1 and n is not None), key=lambda n: (n.startswith('J:'), n))
    if len(ends) == 2:
        route = _route(_path_graph(w, leads), ends[0], ends[1])
        if route:
            return route
    return [('lead', k.id) for k in leads]


def power_path_segments(w):
    """Record M6's segments: id -> the ordered ('lead', id), ('joint', id) and ('part', id) steps.
    PATH_POS, PATH_NEG and PATH_CELL_OUT are found between their ends (SEGMENT_ENDS) over the force
    leads and the series parts; a segment named only by the leads' `segment` keys (PATH_PACK_POS,
    PATH_PACK_NEG) is those leads in order. A segment the model cannot trace is left out."""
    tagged = {}
    for lead in w.leads:
        if lead.segment:
            tagged.setdefault(lead.segment, []).append(lead)
    adj = _path_graph(w, [k for k in w.leads if k.role == 'force'])
    out = {}
    for seg in wiring.SEGMENTS:
        ends = [_node(w, e) for e in SEGMENT_ENDS.get(seg, ())]
        route = _route(adj, *ends) if len(ends) == 2 and None not in ends else None
        if route is None and seg in tagged:
            route = _tagged_route(w, tagged[seg])
        if route:
            out[seg] = route
    return out


# ---- record M7: the meter conditioning at the jack end ----

def check_meter_at_jack(w):
    """Record M7: each meter line's pull-up and filter pins share the jack pin's own strip (METER_JACK). A model
    without that line's net (a fixture with no meter) has nothing to check for it."""
    problems = []
    for net, jack, conditioning in METER_JACK:
        if net not in w.nets:
            continue
        missing = [m for m in (jack, *conditioning) if m not in w.nets.get(net, ())]
        if missing:
            problems.append(f'{net}: {", ".join(missing)} not on the net, so the jack end cannot be checked (record M7)')
            continue
        at = wiring.strip(wiring.member_hole(w, jack), w.split_rails)
        for m in conditioning:
            if wiring.strip(wiring.member_hole(w, m), w.split_rails) != at:
                problems.append(f'{net}: {m} is not in {jack}\'s strip: a jumper between the jack pin and its '
                                'pull-up or filter is a link the counter probe cannot see (record M7)')
    return problems


def run_each(w, jumpers, root):
    """Every check above, in record order: {check name: its problems}."""
    return {'check_force_off_breadboard': check_force_off_breadboard(w),
            'check_sense_landings': check_sense_landings(w),
            'check_single_tie': check_single_tie(w, jumpers),
            'check_gauge_upstream': check_gauge_upstream(w),
            'check_shunt_only': check_shunt_only(w, jumpers),
            'check_test_point_strips': check_test_point_strips(w, jumpers),
            'check_iset': check_iset(w, root),
            'check_divider': check_divider(w, root),
            'check_lead_lengths': check_lead_lengths(w),
            'check_lead_geometry': check_lead_geometry(w),
            'check_meter_at_jack': check_meter_at_jack(w)}


def run_all(w, jumpers, root):
    """Every check's problems, in record order."""
    return [p for problems in run_each(w, jumpers, root).values() for p in problems]
