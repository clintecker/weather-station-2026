"""Rule checks for the bench r1 schematic.

Reads model.py and KiCad's netlist export of bench-r1.kicad_sch, then checks:
  1 the KiCad netlist is the model's, net for net and pin for pin (round trip);
  2 every pin is in one net or deliberately unconnected;
  3 power ground and logic ground meet through exactly one conductor (the tie), counting the
    breakouts' internal ties (KiCad cannot see those);
  4 no force net reaches a header, breadboard or Dupont contact (BSW:215-217), except the listed exemptions;
  5 I2C addresses are unique and match the firmware; the bus pull-up stays >= 0.97 kohm (PM:326-330);
  6 no net's worst-case voltage exceeds a pin limit on it;
  7 the TX NUCLEO pins match the firmware's pin map (board_inputs.c, i2c_bus.c, i2cscan oled.h);
  8 every bench power mode has exactly one source on +3V3, and no fitting of the removable parts can
    give it two;
  9 KiCad's own ERC reports nothing beyond the written waivers (model.ERC_WAIVERS).
Run: python3 checks.py bench.net erc.json   (exit status 0 only if every check passes)
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import json
from itertools import product

from model import ERC_WAIVERS, MODES, NETS, PARTS, SHARED_SHUNT, sources_3v3

REPO = Path(__file__).resolve().parents[3]
PART = {p["ref"]: p for p in PARTS}
PIN = {(p["ref"], pin[0]): pin for p in PARTS for pin in p["pins"]}
FAILS, NOTES = [], []


def fail(check, msg):
    FAILS.append(f"[{check}] {msg}")


def sexpr(text):
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    stack = [[]]
    for t in tokens:
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def field(node, key):
    for item in node:
        if isinstance(item, list) and item and item[0] == key:
            return item
    return None


def kicad_nets(path):
    tree = sexpr(Path(path).read_text())
    out = {}
    for net in field(tree, "nets")[1:]:
        name = field(net, "name")[1].lstrip("/")
        nodes = {(field(n, "ref")[1], field(n, "pin")[1]) for n in net if isinstance(n, list) and n[0] == "node"}
        nodes = {n for n in nodes if not n[0].startswith("#")}   # PWR_FLAG markers are not parts
        if name.startswith("unconnected-"):
            continue
        out[name] = nodes
    return out


def check_round_trip(knets):
    model = {n: set(m) for n, (m, _a) in NETS.items()}
    for name in sorted(set(model) | set(knets)):
        if name not in knets:
            fail(1, f"net {name} is in the model but not in KiCad")
        elif name not in model:
            fail(1, f"net {name} is in KiCad but not in the model: {sorted(knets[name])}")
        elif model[name] != knets[name]:
            fail(1, f"net {name} differs: model only {sorted(model[name] - knets[name])}, "
                    f"KiCad only {sorted(knets[name] - model[name])}")


def check_pins():
    used = defaultdict(list)
    for net, (members, _a) in NETS.items():
        for m in members:
            if m not in PIN:
                fail(2, f"net {net} names {m[0]}.{m[1]}, which is not a pin of the model")
            used[m].append(net)
    for key, (_num, _name, _t, contact) in PIN.items():
        nets = used.get(key, [])
        if contact == "nc" and nets:
            fail(2, f"{key[0]}.{key[1]} is marked unconnected but is in {nets}")
        if contact != "nc" and not nets:
            if PART[key[0]]["part"].startswith("WAGO"):
                NOTES.append(f"spare lever {key[0]}.{key[1]}")
            else:
                fail(2, f"{key[0]}.{key[1]} ({contact}) is in no net")
    for net, (members, _a) in NETS.items():
        if len({r for r, _p in members}) < 2:
            fail(2, f"net {net} touches only one part")


def merged_groups():
    """Union of the model's nets with every part's internal ties: the copper as it really is."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for net, (members, _a) in NETS.items():
        for m in members:
            union(("net", net), m)
    for p in PARTS:
        for tie in p.get("ties", []):
            for pin in tie[1:]:
                union((p["ref"], tie[0]), (p["ref"], pin))
    groups = defaultdict(set)
    for net in NETS:
        groups[find(("net", net))].add(net)
    return {net: frozenset(groups[find(("net", net))]) for net in NETS}, find


def check_ground():
    group, find = merged_groups()
    domains = defaultdict(set)
    for net, (_m, attrs) in NETS.items():
        if "domain" in attrs:
            domains[attrs["domain"]].add(group[net])
    for d, gs in domains.items():
        if len(gs) != 1:
            fail(3, f"{d} ground is split into {len(gs)} copper groups: {[sorted(g) for g in gs]}")
    power, logic = next(iter(domains["power"])), next(iter(domains["logic"]))
    if power == logic:
        fail(3, f"power and logic ground are one copper group through an internal tie: {sorted(power)}")
        return
    bridges = []
    for p in PARTS:
        on = {g for pin in p["pins"] for net, (m, _a) in NETS.items() if (p["ref"], pin[0]) in m
              for g in [group[net]] if g in (power, logic)}
        if on == {power, logic}:
            bridges.append(p["ref"])
    ties = [r for r in bridges if PART[r].get("tie")]
    if len(ties) != 1 or bridges != ties:
        fail(3, f"conductors between power and logic ground: {bridges} (want exactly one tie)")
    NOTES.append(f"power ground group: {sorted(power)}")
    NOTES.append(f"logic ground group: {sorted(logic)}")
    NOTES.append(f"ground tie: {ties}; the USB-C adapter must float, or its earth would be a second tie via PS1.GND")


def check_force():
    for net, (members, attrs) in NETS.items():
        if not attrs.get("force"):
            continue
        exempt = attrs.get("exempt", {})
        for m in members:
            contact = PIN[m][3]
            if contact in ("header", "qt") and m not in exempt:
                fail(4, f"force net {net} reaches {m[0]}.{m[1]} through a {contact} contact")
        for m, why in exempt.items():
            NOTES.append(f"force exemption {net} at {m[0]}.{m[1]}: {why}")


def firmware_addresses():
    text = (REPO / "firmware/stage0-node/App/power_config.h").read_text()
    return {int(v, 16) for v in re.findall(r"#define POWER_ADDR_(?:BATTERY|LOAD|SOLAR|USB|GAUGE)\s+(0x[0-9A-Fa-f]+)", text)}


def check_i2c():
    addrs = defaultdict(list)
    conductance = 0.0
    for p in PARTS:
        for a in p.get("i2c", []):
            addrs[a].append(p["ref"])
        if "pullups_k" in p:
            conductance += 1 / p["pullups_k"]
    for a, refs in addrs.items():
        if len(refs) > 1:
            fail(5, f"I2C address {a:#04x} used by {refs}")
    power = {a for p in PARTS for a in p.get("i2c", []) if p["part"] in ("Adafruit #5832", "Adafruit #5580")}
    fw = firmware_addresses()
    if power != fw:
        fail(5, f"power-monitor addresses {sorted(map(hex, power))} differ from power_config.h {sorted(map(hex, fw))}")
    r = 1 / conductance
    NOTES.append(f"I2C pull-ups: {len([p for p in PARTS if 'pullups_k' in p])} breakouts in parallel = {r * 1000:.0f} ohm "
                 f"(plus the MCU's internal pull-ups, about 40 kohm)")
    if r < 0.97:
        fail(5, f"bus pull-up {r * 1000:.0f} ohm is below 970 ohm: more than 3 mA at 0.4 V")


def check_voltage():
    for net, (members, attrs) in NETS.items():
        if "vmax" not in attrs:
            continue
        v, why = attrs["vmax"]
        for ref, pin in members:
            limit = PART[ref].get("vlimit", {}).get(pin)
            if limit is not None and v > limit:
                fail(6, f"{net} reaches {v} V ({why}) at {ref}.{pin}, limit {limit} V")


def firmware_pins():
    src = (REPO / "firmware/stage0-node/App/board_inputs.c").read_text()
    pins = dict(re.findall(r"\*\s+(P[A-H]\d+)\s+(CN\d+\.\d+)", src))
    pins.update({m: c for m, c in re.findall(r"(P[A-H]\d+)\s+(CN\d+\.\d+)\s+D1[45]", src)})
    for c, m in re.findall(r"<- (CN\d+\.\d+) (P[A-H]\d+)", (REPO / "firmware/i2cscan/App/oled.h").read_text()):
        pins[m] = c
    pins.update({"PA11": "CN5.9", "PA12": "CN5.10"}) if "SDA_PIN GPIO_PIN_11" in \
        (REPO / "firmware/stage0-node/App/i2c_bus.c").read_text() else None
    return pins


def check_firmware_pins():
    fw = firmware_pins()
    for num, name, _t, contact in PART["A1"]["pins"]:
        m = re.match(r"(P[A-H]\d+)_", name)
        if not m or contact == "nc":
            continue
        mcu = m.group(1)
        if mcu not in fw:
            fail(7, f"A1 {num} {mcu}: not found in the firmware pin map")
        elif fw[mcu] != num:
            fail(7, f"A1 {mcu} is on {num} in the model but {fw[mcu]} in the firmware")


def check_modes():
    for name, mode in MODES.items():
        src = sources_3v3(mode)
        NOTES.append(f"mode {name}: +3V3 from {src or 'nothing'}; fitted {sorted(mode['fitted'])}, "
                     f"JP4 {'on' if mode['jp4'] else 'off'}, TX USB {'in' if mode['tx_usb'] else 'out'}")
        if len(src) != 1:
            fail(8, f"mode {name}: +3V3 has {len(src)} sources: {src}")
    for jp4, jp1, usb in product((False, True), repeat=3):
        if SHARED_SHUNT and jp4 and jp1:
            continue                                  # one cap cannot sit in both places
        src = sources_3v3(dict(jp4=jp4, fitted={"JP1"} if jp1 else set(), tx_usb=usb))
        if len(src) > 1:
            fail(8, f"JP4 {'on' if jp4 else 'off'}, JP1 {'on' if jp1 else 'off'}, USB {'in' if usb else 'out'}: "
                    f"two sources fight on +3V3: {src}")


def check_erc(path):
    report = json.loads(Path(path).read_text())
    waived = 0
    for sheet in report["sheets"]:
        for v in sheet["violations"]:
            item = v["items"][0]["description"] if v["items"] else ""
            m = re.match(r"Symbol (\S+) Pin (\S+)", item)
            key = (v["type"], m.group(1), m.group(2)) if m else None
            if v["type"] in ERC_WAIVERS or key in ERC_WAIVERS:
                waived += 1
                continue
            fail(9, f"ERC {v['severity']} {v['type']}: {v['description']} [{item}]")
    NOTES.append(f"ERC: {waived} violation(s) waived with a written reason (model.ERC_WAIVERS)")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    check_round_trip(kicad_nets(sys.argv[1]))
    check_erc(sys.argv[2])
    check_modes()
    check_pins()
    check_ground()
    check_force()
    check_i2c()
    check_voltage()
    check_firmware_pins()
    for n in NOTES:
        print("note ", n)
    for f in FAILS:
        print("FAIL ", f)
    print(f"{'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
