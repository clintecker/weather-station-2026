"""Write tx-stack-r1.kicad_sch and tx-stack-r1.kicad_pro from model.py.

The sheet is drawn in functional groups (power, battery and charging, radio and MCU, sensor ports,
weather-meter inputs, the backplane and card headers, the outdoor ends). Inside a group every net is a drawn
wire: each pin has a short horizontal stub to a vertical trunk in the channel beside its column, and a
net's trunks in one group are joined by a horizontal row above the parts. A net that leaves the group ends
its row in one plain-name label at the group's left edge; KiCad joins equal labels, so labels are the only
links between groups. Unused pins carry a no-connect flag.

The routing cannot short by accident: stubs and trunks of different nets only ever cross (a crossing is not
a connection in KiCad), no wire end lies on another net's wire, and every T is split into segments with a
junction. checks.py then proves KiCad's netlist equals the model.

Run: python3 kicad_gen.py (writes next to this file).
"""
import json
import math
import re
import uuid
from pathlib import Path

from model import NET_NAME, NETS, PARTS, PWR_FLAGS

HERE = Path(__file__).resolve().parent
PROJECT = "tx-stack-r1"
G = 2.54                     # KiCad's 50 mil grid
PIN_LEN = 2 * G
CHAR = 0.85                  # approximate glyph advance per mm of font size (KiCad stroke font)
NS = uuid.UUID("2b7d1c44-8e1f-4a0c-9c3e-51f0a6d2e7aa")

GROUPS = [  # key, title, sheet band, max column height (grid units)
    ("power", "Power: sources and the 3.3 V supply", 0, 70),
    ("battery", "Battery and charging", 0, 90),
    ("radio", "Radio and MCU (card B3)", 0, 90),
    ("meters", "Weather-meter inputs (card B2)", 0, 60),
    ("ports", "Sensor ports S1-S4 (cards B1, B2) and the mux (backplane)", 1, 72),
    ("bus", "Backplane: one socket per card, the charger I2C pins", 1, 100),
    ("outdoor", "Outdoor ends (through the glands)", 1, 60),
]


def uid(*parts):
    """Stable UUIDs, so regenerating an unchanged model gives an identical file."""
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def font(size=1.27, hide=False, justify=None):
    j = f" (justify {justify})" if justify else ""
    h = " (hide yes)" if hide else ""
    return f"(effects (font (size {size} {size})){j}{h})"


def snap(v):
    return round(round(v / G) * G, 3)


PWR_FLAG_SYMBOL = """(symbol "stack:PWR_FLAG" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))
 (exclude_from_sim no) (in_bom no) (on_board no)
 (property "Reference" "#FLG" (at 0 1.905 0) (effects (font (size 1.27 1.27)) (hide yes)))
 (property "Value" "PWR_FLAG" (at 0 3.81 0) (effects (font (size 1.27 1.27))))
 (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
 (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
 (property "Description" "Marks a net as driven" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
 (symbol "PWR_FLAG_0_0" (pin power_out line (at 0 0 90) (length 0) (name "~" (effects (font (size 1.27 1.27))))
  (number "1" (effects (font (size 1.27 1.27))))))
 (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))
  (stroke (width 0) (type default)) (fill (type none))))
 (embedded_fonts no))"""


def split(part):
    """Left and right pin lists. Two-pin parts: pin 1 left, pin 2 right."""
    pins = part["pins"]
    half = (len(pins) + 1) // 2
    return pins[:half], pins[half:]


def body_h(part):
    left, right = split(part)
    n = max(len(left), len(right)) + 1
    return (n + n % 2) * G      # even, so every pin lands on the grid


def pin_points(part, box_w):
    """Pin number -> (x, y, side) in symbol coordinates (y up); x is the pin's outer end."""
    left, right = split(part)
    top = body_h(part) / 2 - G
    pts = {}
    for i, p in enumerate(left):
        pts[p[0]] = (-box_w / 2 - PIN_LEN, round(top - i * G, 3), "L")
    for i, p in enumerate(right):
        pts[p[0]] = (box_w / 2 + PIN_LEN, round(top - i * G, 3), "R")
    return pts


def lib_symbol(part, box_w):
    name = f"stack:{part['ref']}"
    h = body_h(part)
    out = [f"(symbol {q(name)} (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom yes) (on_board yes)",
           f"(property \"Reference\" {q(re.sub(r'[0-9]+$', '', part['ref']))} (at 0 {h / 2 + G} 0) {font()})",
           f"(property \"Value\" {q(part['value'])} (at 0 {-h / 2 - G} 0) {font()})",
           f"(property \"Footprint\" \"\" (at 0 0 0) {font(hide=True)})",
           f"(property \"Datasheet\" \"\" (at 0 0 0) {font(hide=True)})",
           f"(property \"Description\" {q(part['part'])} (at 0 0 0) {font(hide=True)})",
           f"(symbol {q(part['ref'] + '_0_1')} (rectangle (start {-box_w / 2} {h / 2}) (end {box_w / 2} {-h / 2})"
           " (stroke (width 0.254) (type default)) (fill (type background))))",
           f"(symbol {q(part['ref'] + '_1_1')}"]
    for num, pname, etype, contact in part["pins"]:
        x, y, side = pin_points(part, box_w)[num]
        ang = 0 if side == "L" else 180
        etype = "no_connect" if contact == "nc" and etype == "passive" else etype
        out.append(f"(pin {etype} line (at {x} {y} {ang}) (length {PIN_LEN}) (name {q(pname.replace(" ", "\u00a0"))} {font(1.0)})"
                   f" (number {q(num)} {font(1.0)}))")
    out += [")", "(embedded_fonts no))"]
    return "\n".join(out)


def net_of():
    m = {}
    for net, (members, _attrs) in NETS.items():
        for ref, pin in members:
            if (ref, pin) in m:
                raise SystemExit(f"{ref}.{pin} is in two nets: {m[(ref, pin)]} and {net}")
            m[(ref, pin)] = net
    return m


def port_key(part):
    """Sensor-port group order: the mux, then port by port (fuse, clamps, resistors, jack, QT lead)."""
    ref = part["ref"]
    if ref == "U4":
        return (0, 0, 0)
    m = re.match(r"([A-Z]+)(\d)", ref)
    k = int(m.group(2)) if m.group(1) != "J" else int(ref[2])
    kind = {"F": 0, "D": 1, "R": 2, "J": 3, "W": 4}[m.group(1)]
    return (k, kind, ref)


class Sheet:
    def __init__(self):
        self.body, self.wires = [], []
        self.ends = {}           # point -> count of wire ends there

    def wire(self, a, b, key):
        if a == b:
            return
        self.wires.append((a, b, key))
        for pt in (a, b):
            self.ends[pt] = self.ends.get(pt, 0) + 1

    def polyline(self, pts, key):
        """A straight run through several points, split into segments at every point."""
        pts = sorted(set(pts))
        for i in range(len(pts) - 1):
            self.wire(pts[i], pts[i + 1], (key, i))


def build():
    root = uid("root")
    nets = net_of()
    sh = Sheet()
    lib, inst = [], []
    flags = {n: i for i, n in enumerate(PWR_FLAGS)}
    group_of = {p["ref"]: p["block"] for p in PARTS}
    net_groups = {n: {group_of[r] for r, _p in ms} for n, (ms, _a) in NETS.items()}

    band_y = [10 * G, None]
    band_x = [10 * G, 10 * G]
    band_h = [0, 0]
    sheet_w = 0
    for key, title, band, max_h in GROUPS:
        parts = [p for p in PARTS if p["block"] == key]
        if key == "ports":
            parts.sort(key=port_key)
        name_len = max(max((len(x[1]) for x in split(p)[0]), default=0) + max((len(x[1]) for x in split(p)[1]),
                       default=0) for p in parts)
        box_w = 2 * G * math.ceil((max(8 * G, name_len * CHAR * 1.0 + 3 * G) + G) / (2 * G))  # even: pins on grid
        # columns of parts, each no taller than max_h grid units
        cols, cur, h = [], [], 0
        for p in parts:
            ph = body_h(p) / G + 5
            if cur and (h + ph > max_h or (key == "ports" and port_key(p)[0] != port_key(cur[-1])[0])):
                cols.append(cur)
                cur, h = [], 0
            cur.append(p)
            h += ph
        cols.append(cur)
        # which nets have pins on which (column, side), to size the channels
        side_nets = {}
        for ci, col in enumerate(cols):
            for p in col:
                pts = pin_points(p, box_w)
                for num, *_r in p["pins"]:
                    n = nets.get((p["ref"], num))
                    if n is not None:
                        side_nets.setdefault((ci, pts[num][2]), [])
                        if n not in side_nets[(ci, pts[num][2])]:
                            side_nets[(ci, pts[num][2])].append(n)
        group_nets = sorted({n for v in side_nets.values() for n in v}, key=lambda n: list(NETS).index(n))
        labelled = [n for n in group_nets if len(net_groups[n]) > 1]
        label_w = snap(max((len(NET_NAME[n]) for n in labelled), default=0) * CHAR * 1.27 + 3 * G)
        flag_w = 3 * G if any(n in flags for n in group_nets) else 0
        # x layout: [labels][L channel][column][R channel] per column
        if band == 1 and band_y[1] is None:
            band_y[1] = band_y[0] + band_h[0] + 14 * G
        gx0 = band_x[band]
        x = gx0 + label_w + flag_w
        col_x, trunk_x = [], {}
        for ci, col in enumerate(cols):
            left = side_nets.get((ci, "L"), [])
            for i, n in enumerate(reversed(left)):
                trunk_x[(n, ci, "L")] = snap(x + (i + 1) * G)
            x += (len(left) + 1) * G
            cx = snap(x + PIN_LEN + box_w / 2)
            col_x.append(cx)
            x = cx + box_w / 2 + PIN_LEN
            right = side_nets.get((ci, "R"), [])
            for i, n in enumerate(right):
                trunk_x[(n, ci, "R")] = snap(x + (i + 1) * G)
            x += (len(right) + 2) * G
        gx1 = x
        # rows above the parts: one per net that needs to join trunks, leave the group, or carry a flag
        row_nets = [n for n in group_nets
                    if len(net_groups[n]) > 1 or n in flags or sum(1 for k in trunk_x if k[0] == n) > 1]
        gy0 = band_y[band]
        row_y = {n: snap(gy0 + (4 + i) * G) for i, n in enumerate(row_nets)}
        parts_y0 = gy0 + (6 + len(row_nets)) * G
        # place the parts
        pin_pt = {}
        bottom = parts_y0
        for ci, col in enumerate(cols):
            y = parts_y0
            for p in col:
                ph = body_h(p)
                sy = snap(y + ph / 2 + 2 * G)
                sx = col_x[ci]
                ref = p["ref"]
                lib.append(lib_symbol(p, box_w))
                inst.append(f"(symbol (lib_id {q('stack:' + ref)}) (at {sx} {sy} 0) (unit 1) (exclude_from_sim no)"
                            f" (in_bom yes) (on_board yes) (dnp no) (uuid {q(uid('sym', ref))})")
                inst.append(f"(property \"Reference\" {q(ref)} (at {sx} {snap(sy - ph / 2) - 0.9} 0) {font(1.5)})")
                inst.append(f"(property \"Value\" {q(p['value'])} (at {sx} {snap(sy + ph / 2) + 1.6} 0) {font()})")
                for prop in ("Footprint", "Datasheet"):
                    inst.append(f"(property {q(prop)} \"\" (at {sx} {sy} 0) {font(hide=True)})")
                inst.append(f"(property \"Description\" {q(p['part'])} (at {sx} {sy} 0) {font(hide=True)})")
                for num, *_r in p["pins"]:
                    inst.append(f"(pin {q(num)} (uuid {q(uid('pin', ref, num))}))")
                inst.append(f"(instances (project {q(PROJECT)} (path {q('/' + root)} (reference {q(ref)}) (unit 1)))))")
                for num, *_r in p["pins"]:
                    px, py, side = pin_points(p, box_w)[num]
                    pt = (round(sx + px, 3), round(sy - py, 3))
                    if nets.get((ref, num)) is None:
                        sh.body.append(f"(no_connect (at {pt[0]} {pt[1]}) (uuid {q(uid('nc', ref, num))}))")
                    else:
                        pin_pt[(ref, num)] = (pt, ci, side)
                y = sy + ph / 2 + 3 * G
            bottom = max(bottom, y)
        # wires: stubs, trunks, rows
        trunk_pts = {}
        for (ref, num), (pt, ci, side) in pin_pt.items():
            n = nets[(ref, num)]
            tx = trunk_x[(n, ci, side)]
            sh.wire(pt, (tx, pt[1]), ("stub", ref, num))
            trunk_pts.setdefault((n, ci, side), []).append((tx, pt[1]))
        for (n, ci, side), pts in trunk_pts.items():
            if n in row_y:
                pts = pts + [(trunk_x[(n, ci, side)], row_y[n])]
            sh.polyline(pts, ("trunk", n, ci, side))
        for n, ry in row_y.items():
            xs = [trunk_x[k] for k in trunk_x if k[0] == n]
            end = snap(gx0 + label_w + (G if n in flags else 0))
            if len(net_groups[n]) > 1 or n in flags:
                xs.append(end)
            sh.polyline([(xx, ry) for xx in xs], ("row", key, n))
            if len(net_groups[n]) > 1:
                sh.body.append(f"(label {q(NET_NAME[n])} (at {end} {ry} 180) {font(1.27, justify='right bottom')}"
                               f" (uuid {q(uid('lbl', key, n))}))")
            if n in flags:
                i = flags.pop(n)
                ref = f"#FLG{i + 1:02d}"
                inst.append(f"(symbol (lib_id \"stack:PWR_FLAG\") (at {end} {ry} 0) (unit 1) (exclude_from_sim no)"
                            f" (in_bom no) (on_board no) (dnp no) (uuid {q(uid('flg', n))})")
                inst.append(f"(property \"Reference\" {q(ref)} (at {end} {ry - 2 * G} 0) {font(hide=True)})")
                inst.append(f"(property \"Value\" \"PWR_FLAG\" (at {end} {ry - 1.5 * G} 0) {font(1.0, hide=True)})")
                for prop in ("Footprint", "Datasheet", "Description"):
                    inst.append(f"(property {q(prop)} \"\" (at {end} {ry} 0) {font(hide=True)})")
                inst.append(f"(pin \"1\" (uuid {q(uid('flgpin', n))}))")
                inst.append(f"(instances (project {q(PROJECT)} (path {q('/' + root)} (reference {q(ref)}) (unit 1)))))")
        # notes under the parts
        notes = [f"{p['ref']}: {p['note']}" for p in parts if p.get("note")]
        ny = bottom + G
        for i, t in enumerate(notes):
            sh.body.append(f"(text {q(t)} (exclude_from_sim no) (at {snap(gx0 + G)} {round(ny + i * 1.8 * G, 3)} 0)"
                           f" {font(1.27, justify='left bottom')} (uuid {q(uid('note', key, i))}))")
        gy1 = ny + len(notes) * 1.8 * G + G
        gx1 = max(gx1, gx0 + max((len(t) for t in notes), default=0) * CHAR * 1.27 + 3 * G)
        gx1, gy1 = snap(gx1 + G), snap(gy1 + G)
        sh.body.append(f"(rectangle (start {gx0} {gy0}) (end {gx1} {gy1}) (stroke (width 0.3) (type dash))"
                       f" (fill (type none)) (uuid {q(uid('frame', key))}))")
        sh.body.append(f"(text {q(title)} (exclude_from_sim no) (at {gx0 + G} {gy0 + 2.2 * G} 0)"
                       f" {font(2.5, justify='left bottom')} (uuid {q(uid('blk', key))}))")
        band_x[band] = gx1 + 8 * G
        band_h[band] = max(band_h[band], gy1 - gy0)
        sheet_w = max(sheet_w, gx1)
    if flags:
        raise SystemExit(f"power flags not placed: {sorted(flags)}")
    for (a, b, key) in sh.wires:
        sh.body.append(f"(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default))"
                       f" (uuid {q(uid('w', *key, a, b))}))")
    for pt, c in sorted(sh.ends.items()):
        if c >= 3:
            sh.body.append(f"(junction (at {pt[0]} {pt[1]}) (diameter 0) (color 0 0 0 0) (uuid {q(uid('j', pt))}))")
    paper_w = math.ceil((sheet_w + 10 * G) / 10) * 10
    paper_h = math.ceil((band_y[1] + band_h[1] + 20 * G) / 10) * 10
    body = [f"(kicad_sch (version 20250114) (generator \"tx_stack_gen\") (generator_version \"10.0\") (uuid {q(root)})",
            f"(paper \"User\" {paper_w} {paper_h})",
            "(title_block (title \"Weather station TX card cage r2 (Wio-E5 mini)\") (rev \"r2\")"
            " (comment 1 \"Generated from hardware/tx-stack-r1/schematic/model.py: edit the model, not this file\")"
            " (comment 2 \"Wires inside each dashed group; a label names a line that continues in another group\"))",
            "(lib_symbols", *lib, PWR_FLAG_SYMBOL, ")", *sh.body, *inst,
            "(sheet_instances (path \"/\" (page \"1\")))", "(embedded_fonts no))"]
    (HERE / f"{PROJECT}.kicad_sch").write_text("\n".join(body) + "\n")
    pro = {"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
           "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
           "sheets": [[root, "Root"]], "text_variables": {}}
    (HERE / f"{PROJECT}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")
    return paper_w, paper_h, len(sh.wires)


if __name__ == "__main__":
    w, h, nw = build()
    print(f"wrote {PROJECT}.kicad_sch: {len(PARTS)} parts, {len(NETS)} nets, {nw} wire segments, {w} x {h} mm")
