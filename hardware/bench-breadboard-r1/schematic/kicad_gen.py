"""Write bench-r1.kicad_sch and bench-r1.kicad_pro from model.py.

Each part becomes a box symbol with its real pins; every connected pin carries a local net label at its
end and every unused pin a no-connect flag, so KiCad's connectivity is exactly the model's. Parts are
grouped in labelled functional blocks. Run: python3 kicad_gen.py (writes next to this file).
"""
import json
import uuid
from pathlib import Path

from model import NETS, PARTS, PWR_FLAGS

HERE = Path(__file__).resolve().parent
PROJECT = "bench-r1"
G = 2.54                     # KiCad's 50 mil grid
BOX_W = 12 * G               # symbol body width
PIN_LEN = 2 * G
NS = uuid.UUID("6f1c3c2e-5b0a-4c55-9a0e-7d2b1f0e4b11")


def uid(*parts):
    """Stable UUIDs, so regenerating an unchanged model gives an identical file."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def font(size=1.27, hide=False, justify=None):
    j = f" (justify {justify})" if justify else ""
    h = " (hide yes)" if hide else ""
    return f"(effects (font (size {size} {size})){j}{h})"


BLOCKS = [  # (block key, title, column, row origin in grid units)
    ("sources", "Sources (off the plate)", 0, 0), ("pack", "Pack and NTC", 0, 30),
    ("usbc", "USB-C metering breakouts", 0, 52), ("solar", "Solar metering breakouts", 0, 90),
    ("charger", "Charger #4755", 1, 0), ("power", "Power metering, WAGO nodes, regulator, links", 2, 0),
    ("signals", "Charger signal networks", 1, 70), ("i2c", "I2C2: sensor branch and power branch", 4, 0),
    ("meter", "Weather meter inputs", 5, 0), ("oled", "OLED (SPI1)", 6, 0), ("mcu", "NUCLEOs and the Mac", 6, 45),
]
COL_W = 62 * G


PWR_FLAG_SYMBOL = """(symbol "bench:PWR_FLAG" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))
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


def split(pins):
    half = (len(pins) + 1) // 2
    return pins[:half], pins[half:]


def body_h(part):
    left, right = split(part["pins"])
    return (max(len(left), len(right)) + 1) * G


def pin_points(part):
    """Pin number -> (x, y, side) in symbol coordinates (y up)."""
    left, right = split(part["pins"])
    top = body_h(part) / 2 - G
    pts = {}
    for i, p in enumerate(left):
        pts[p[0]] = (-BOX_W / 2 - PIN_LEN, round(top - i * G, 2), "L")
    for i, p in enumerate(right):
        pts[p[0]] = (BOX_W / 2 + PIN_LEN, round(top - i * G, 2), "R")
    return pts


def lib_symbol(part):
    name = f"bench:{part['ref']}"
    h = body_h(part)
    out = [f"(symbol {q(name)} (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom yes) (on_board yes)",
           f"(property \"Reference\" {q(part['ref'][:1])} (at 0 {h / 2 + G} 0) {font()})",
           f"(property \"Value\" {q(part['value'])} (at 0 {-h / 2 - G} 0) {font()})",
           f"(property \"Footprint\" \"\" (at 0 0 0) {font(hide=True)})",
           f"(property \"Datasheet\" \"\" (at 0 0 0) {font(hide=True)})",
           f"(property \"Description\" {q(part['part'])} (at 0 0 0) {font(hide=True)})",
           f"(symbol {q(part['ref'] + '_0_1')} (rectangle (start {-BOX_W / 2} {h / 2}) (end {BOX_W / 2} {-h / 2})"
           " (stroke (width 0.254) (type default)) (fill (type background))))",
           f"(symbol {q(part['ref'] + '_1_1')}"]
    pts = pin_points(part)
    for num, pname, etype, contact in part["pins"]:
        x, y, side = pts[num]
        ang = 0 if side == "L" else 180
        etype = "no_connect" if contact == "nc" and etype == "passive" else etype
        out.append(f"(pin {etype} line (at {x} {y} {ang}) (length {PIN_LEN}) (name {q(pname)} {font(1.0)})"
                   f" (number {q(num)} {font(1.0)}))")
    out.append(")")
    out.append("(embedded_fonts no))")
    return "\n".join(out)


def placements():
    """Ref -> (x, y) of the symbol origin on the sheet, stacking each block's parts downwards."""
    pos, y_next = {}, {}
    for key, _title, col, row in BLOCKS:
        y_next[key] = (row + 4) * G
    col_of = {b[0]: b[2] for b in BLOCKS}
    for part in PARTS:
        b = part["block"]
        h = body_h(part)
        x = 20 * G + col_of[b] * COL_W + BOX_W / 2 + 14 * G
        if b == "power" and y_next[b] > 300 * G:        # long block: wrap into the next column
            col_of[b], y_next[b] = 3, 4 * G
            x = 20 * G + 3 * COL_W + BOX_W / 2 + 14 * G
        y = y_next[b] + h / 2 + 2 * G
        pos[part["ref"]] = (round(x / G) * G, round(y / G) * G)
        y_next[b] = y + h / 2 + 5 * G
    return pos


def net_of():
    m = {}
    for net, (members, _attrs) in NETS.items():
        for ref, pin in members:
            if (ref, pin) in m:
                raise SystemExit(f"{ref}.{pin} is in two nets: {m[(ref, pin)]} and {net}")
            m[(ref, pin)] = net
    return m


def build():
    root = uid("root")
    pos = placements()
    nets = net_of()
    body = [f"(kicad_sch (version 20250114) (generator \"bench_r1_gen\") (generator_version \"10.0\") (uuid {q(root)})",
            "(paper \"A0\")",
            "(title_block (title \"Weather station breadboard bench r1\") (rev \"r1-draft\")"
            " (comment 1 \"Generated from hardware/bench-breadboard-r1/schematic/model.py: edit the model, not this file\"))",
            "(lib_symbols"]
    body += [lib_symbol(p) for p in PARTS]
    body.append(PWR_FLAG_SYMBOL)
    body.append(")")
    for key, title, col, row in BLOCKS:
        x, y = 20 * G + col * COL_W, (row + 2) * G
        body.append(f"(text {q(title)} (exclude_from_sim no) (at {x} {y} 0) {font(2.5, justify='left bottom')}"
                    f" (uuid {q(uid('blk', key))}))")
    for part in PARTS:
        ref = part["ref"]
        sx, sy = pos[ref]
        h = body_h(part)
        body.append(f"(symbol (lib_id {q('bench:' + ref)}) (at {sx} {sy} 0) (unit 1) (exclude_from_sim no)"
                    f" (in_bom yes) (on_board yes) (dnp no) (uuid {q(uid('sym', ref))})")
        body.append(f"(property \"Reference\" {q(ref)} (at {sx} {sy - h / 2 - G} 0) {font(1.5)})")
        body.append(f"(property \"Value\" {q(part['value'])} (at {sx} {sy + h / 2 + G} 0) {font()})")
        body.append(f"(property \"Footprint\" \"\" (at {sx} {sy} 0) {font(hide=True)})")
        body.append(f"(property \"Datasheet\" \"\" (at {sx} {sy} 0) {font(hide=True)})")
        body.append(f"(property \"Description\" {q(part['part'])} (at {sx} {sy} 0) {font(hide=True)})")
        for num, *_ in part["pins"]:
            body.append(f"(pin {q(num)} (uuid {q(uid('pin', ref, num))}))")
        body.append(f"(instances (project {q(PROJECT)} (path {q('/' + root)} (reference {q(ref)}) (unit 1)))))")
        for num, *_rest in part["pins"]:
            px, py, side = pin_points(part)[num]
            ax, ay = round(sx + px, 2), round(sy - py, 2)
            net = nets.get((ref, num))
            if net is None:
                body.append(f"(no_connect (at {ax} {ay}) (uuid {q(uid('nc', ref, num))}))")
            else:
                ang, just = (180, "right bottom") if side == "L" else (0, "left bottom")
                body.append(f"(label {q(net)} (at {ax} {ay} {ang}) {font(1.0, justify=just)}"
                            f" (uuid {q(uid('lbl', ref, num))}))")
    x0, y0 = 20 * G + 4 * COL_W, 330 * G
    body.append(f"(text \"Power flags (nets driven through a passive part)\" (exclude_from_sim no) (at {x0} {y0 - 3 * G} 0)"
                f" {font(2.0, justify='left bottom')} (uuid {q(uid('blk', 'flags'))}))")
    for i, net in enumerate(PWR_FLAGS):
        fx, fy = x0 + (i % 4) * 20 * G, y0 + (i // 4) * 8 * G
        ref = f"#FLG{i + 1:02d}"
        body.append(f"(symbol (lib_id \"bench:PWR_FLAG\") (at {fx} {fy} 0) (unit 1) (exclude_from_sim no) (in_bom no)"
                    f" (on_board no) (dnp no) (uuid {q(uid('flg', net))})")
        body.append(f"(property \"Reference\" {q(ref)} (at {fx} {fy - 2 * G} 0) {font(hide=True)})")
        body.append(f"(property \"Value\" \"PWR_FLAG\" (at {fx} {fy - G} 0) {font()})")
        body.append(f"(property \"Footprint\" \"\" (at {fx} {fy} 0) {font(hide=True)})")
        body.append(f"(property \"Datasheet\" \"\" (at {fx} {fy} 0) {font(hide=True)})")
        body.append(f"(property \"Description\" \"\" (at {fx} {fy} 0) {font(hide=True)})")
        body.append(f"(pin \"1\" (uuid {q(uid('flgpin', net))}))")
        body.append(f"(instances (project {q(PROJECT)} (path {q('/' + root)} (reference {q(ref)}) (unit 1)))))")
        body.append(f"(label {q(net)} (at {fx} {fy} 0) {font(1.0, justify='left bottom')} (uuid {q(uid('flglbl', net))}))")
    body.append(f"(sheet_instances (path \"/\" (page \"1\")))")
    body.append("(embedded_fonts no))")
    (HERE / f"{PROJECT}.kicad_sch").write_text("\n".join(body) + "\n")
    pro = {"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
           "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
           "sheets": [[root, "Root"]], "text_variables": {}}
    (HERE / f"{PROJECT}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")


if __name__ == "__main__":
    build()
    print(f"wrote {PROJECT}.kicad_sch: {len(PARTS)} parts, {len(NETS)} nets")
