"""Read the copper of a KiCad 10 board file (.kicad_pcb text): segments and vias by net name.
Standard library only, so the repository Python and the tests can check a routed board."""
import re
from pathlib import Path

SEGMENT = re.compile(r'\(segment\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)'
                     r'\s+\(width ([-\d.]+)\)\s+\(layer "([^"]+)"\)\s+\(net "([^"]*)"\)')
VIA = re.compile(r'\(via\b[^()]*(?:\((?!at\b)[^()]*\)\s*)*\(at ([-\d.]+) ([-\d.]+)\)(.*?)\(net "([^"]*)"\)', re.S)


def copper_by_net(path):
    """{net: {'segments': [((x1, y1), (x2, y2), layer)], 'vias': [(x, y)]}} in mm."""
    text = Path(path).read_text()
    copper = {}
    for m in SEGMENT.finditer(text):
        x1, y1, x2, y2, _w, layer, net = m.groups()
        copper.setdefault(net, {'segments': [], 'vias': []})['segments'].append(
            ((float(x1), float(y1)), (float(x2), float(y2)), layer))
    for m in VIA.finditer(text):
        copper.setdefault(m.group(4), {'segments': [], 'vias': []})['vias'].append((float(m.group(1)), float(m.group(2))))
    return copper


def joins(copper, a, b, tol=0.6):
    """True if the net's copper is one path that touches both points (within tol mm). Points that
    coincide count as joined: the ends meet on a through-hole pad or a via."""
    points = []
    for p, q, _layer in copper['segments']:
        points += [p, q]
    near = lambda p, q: abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol   # noqa: E731
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(0, len(points), 2):
        parent[find(i)] = find(i + 1)
    for i in range(len(points)):
        for k in range(i):
            if near(points[i], points[k]):
                parent[find(i)] = find(k)
    ends_a = {find(i) for i, p in enumerate(points) if near(p, a)}
    ends_b = {find(i) for i, p in enumerate(points) if near(p, b)}
    return bool(ends_a & ends_b)
