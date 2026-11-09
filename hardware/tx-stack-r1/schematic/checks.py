"""Rule checks for the TX stack r1 schematic.

Reads model.py and KiCad's netlist export of tx-stack-r1.kicad_sch, then checks:
  1 the KiCad netlist is the model's, net for net and pin for pin (round trip);
  2 every connected pin is in exactly one net, every "nc" pin in none, and every net has >= 2 parts;
  3 the I2C address map: the upstream segment (before the PCA9548) has no clash and no 0x50; every 0x50
    EEPROM sits behind a mux channel; no channel, joined to the upstream bus when selected, gives a clash;
    the addresses match the firmware (i2c_bus.h I2C_MUX_ADDR, power_config.h); the upstream pull-ups stay
    >= 0.97 kohm;
  4 every I2C port's 3V3 (jack pin 2) comes only through its own MF-R010, whose other leg is on +3V3;
  5 no battery-current path through a header, a socket or a breadboard contact: every member of a battery
    net is a soldered lead, an EVM terminal or the pack's own JST PH mating; the series chain pack +
    -> pigtail -> INA228 shunt -> EVM BAT and pack - -> EVM BAT- exists; BATP and the gauge sense are on the
    pack side of the shunt;
  6 the RJ11 pin maps: I2C ports 2 3V3, 3 SDA, 4 GND, 5 SCL; wind 2 GND, 3 GND, 4 CUPS, 5 VANE; rain
    3 GND, 4 RAIN; unused positions unconnected;
  7 the Wio-E5 mini pins match the firmware's (firmware/board/wio-e5/board.toml, or board_pins.h before it);
  8 KiCad's ERC reports nothing beyond model.ERC_WAIVERS.
Run: python3 checks.py stack.net erc.json   (exit status 0 only if every check passes)
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from model import ERC_WAIVERS, MCU_FUNCTION, NETS, PARTS, PIN_MAPS

REPO = Path(__file__).resolve().parents[3]
PART = {p["ref"]: p for p in PARTS}
PIN = {(p["ref"], pin[0]): pin for p in PARTS for pin in p["pins"]}
NET_OF = {m: n for n, (ms, _a) in NETS.items() for m in ms}
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
        nodes = {n for n in nodes if not n[0].startswith("#")}
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
        parts = {r for r, _p in members}
        if len(members) < 2 or len(parts) < 2:
            fail(2, f"net {net} has {len(members)} member(s) on {len(parts)} part(s); every net needs >= 2")
    for key, (_n, _name, _t, contact) in PIN.items():
        nets = used.get(key, [])
        if len(nets) > 1:
            fail(2, f"{key[0]}.{key[1]} is in {len(nets)} nets: {nets}")
        if contact == "nc" and nets:
            fail(2, f"{key[0]}.{key[1]} is marked unconnected but is in {nets}")
        if contact != "nc" and not nets:
            fail(2, f"{key[0]}.{key[1]} ({contact}) is in no net")
    NOTES.append(f"{len(PARTS)} parts, {len(NETS)} nets, {sum(len(m) for m, _a in NETS.values())} connections")


def segment(ref):
    """Which I2C segment a part's SDA pin is on: 'up', 'ch0'..'ch3', or None."""
    for (r, pin), (_n, name, _t, _c) in PIN.items():
        if r == ref and name == "SDA" and (r, pin) in NET_OF:
            net = NET_OF[(r, pin)]
            if net == "I2C_SDA":
                return "up"
            m = re.fullmatch(r"P(\d)_SDA", net)
            if m:
                return f"ch{int(m.group(1)) - 1}"
    return None


def firmware_i2c():
    bus_h = (REPO / "firmware/stage0-node/App/i2c_bus.h").read_text()
    pc_h = (REPO / "firmware/stage0-node/App/power_config.h").read_text()
    out = {}
    m = re.search(r"#define I2C_MUX_ADDR\s+(0x[0-9A-Fa-f]+)", bus_h)
    out["mux"] = int(m.group(1), 16) if m else None
    for key in ("BATTERY", "GAUGE"):
        m = re.search(rf"#define POWER_ADDR_{key}\s+(0x[0-9A-Fa-f]+)", pc_h)
        out[key] = int(m.group(1), 16) if m else None
    return out


def check_i2c():
    segs = defaultdict(list)
    for p in PARTS:
        if not p.get("i2c"):
            continue
        s = segment(p["ref"])
        if s is None:
            fail(3, f"{p['ref']} has I2C addresses but its SDA is on no bus segment")
            continue
        for a in p["i2c"]:
            segs[s].append((a, p["ref"]))
    up = segs.get("up", [])
    seen = defaultdict(list)
    for a, ref in up:
        seen[a].append(ref)
    for a, refs in seen.items():
        if len(refs) > 1:
            fail(3, f"upstream address {a:#04x} used by {refs}")
    if 0x50 in seen:
        fail(3, f"a 0x50 EEPROM is upstream of the mux: {seen[0x50]}")
    for s in sorted(k for k in segs if k != "up"):
        joined = defaultdict(list)
        for a, ref in up + segs[s]:
            joined[a].append(ref)
        for a, refs in joined.items():
            if len(refs) > 1:
                fail(3, f"{s} selected: address {a:#04x} used by {refs}")
        NOTES.append(f"I2C {s}: " + ", ".join(f"{a:#04x} {r}" for a, r in segs[s]))
    eeproms = [(s, r) for s, v in segs.items() for a, r in v if a == 0x50]
    if any(s == "up" for s, _r in eeproms):
        fail(3, "an ID EEPROM is upstream")
    NOTES.append("I2C upstream: " + ", ".join(f"{a:#04x} {r}" for a, r in sorted(up)))
    fw = firmware_i2c()
    want = {"mux": ("U4", 0x71), "BATTERY": ("U2", 0x40), "GAUGE": ("U6", 0x36)}
    for key, (ref, _a) in want.items():
        model_addr = PART[ref]["i2c"][0]
        if fw[key] != model_addr:
            fail(3, f"{ref} at {model_addr:#04x} in the model, firmware {key} = {fw[key]}")
    conductance = sum(1 / PART[r]["pullups_k"] for r in {r for _a, r in up} | {"A1"} if "pullups_k" in PART[r])
    rr = 1 / conductance
    NOTES.append(f"upstream pull-ups in parallel: {rr * 1000:.0f} ohm (Wio-E5 4.7k, SHTC3, INA228, MAX17048, "
                 f"PCA9548 10k each; EVM pull-ups disabled)")
    if rr < 0.97:
        fail(3, f"upstream pull-up {rr * 1000:.0f} ohm is below 970 ohm")


def check_ptc():
    for jack, pins in PIN_MAPS.items():
        if not jack.startswith("J1"):
            continue
        net = NET_OF.get((jack, "2"))
        if net is None:
            fail(4, f"{jack} pin 2 is in no net")
            continue
        members = NETS[net][0]
        ptcs = [(r, p) for r, p in members if PART[r]["value"] == "MF-R010"]
        sources = [(r, p) for r, p in members if PIN[(r, p)][2] == "power_out" or r in ("U7", "A1", "XS1", "XP1")]
        if net == "+3V3" or len(ptcs) != 1 or sources:
            fail(4, f"{jack} pin 2 net {net}: PTCs {ptcs}, direct sources {sources}")
            continue
        ref, leg = ptcs[0]
        other = "1" if leg == "2" else "2"
        if NET_OF.get((ref, other)) != "+3V3":
            fail(4, f"{jack} pin 2 PTC {ref}'s other leg is on {NET_OF.get((ref, other))}, not +3V3")
        else:
            NOTES.append(f"{jack} pin 2 ({net}) <- {ref} MF-R010 <- +3V3")


def check_battery():
    for net, (members, attrs) in NETS.items():
        if not attrs.get("battery"):
            continue
        for ref, pin in members:
            c = PIN[(ref, pin)][3]
            if c in ("header", "socket"):
                fail(5, f"battery net {net} reaches {ref}.{pin} through a {c} contact")
            elif c == "jst" and net not in ("PACK_P", "PACK_N"):
                fail(5, f"battery net {net} has a JST mating at {ref}.{pin} (only the pack's own plug is allowed)")
            elif c not in ("solder", "evm", "jst"):
                fail(5, f"battery net {net} reaches {ref}.{pin} through '{c}'")
    chain = [("PACK_P", [("BT1", "+"), ("PG1", "M+")]), ("CELL_P", [("PG1", "L+"), ("U2", "X1.VIN+")]),
             ("BAT_P", [("U2", "X1.VIN-"), ("U1", "BAT")]), ("PACK_N", [("BT1", "-"), ("PG1", "M-")]),
             ("BAT_N", [("PG1", "L-"), ("U1", "BATN")])]
    for net, need in chain:
        for m in need:
            if NET_OF.get(m) != net:
                fail(5, f"battery chain: {m[0]}.{m[1]} should be on {net}, is on {NET_OF.get(m)}")
    for m in (("U1", "BATP"), ("U6", "JP2.VBAT")):
        if NET_OF.get(m) != "CELL_P":
            fail(5, f"{m[0]}.{m[1]} senses {NET_OF.get(m)}, not the pack side of the shunt (CELL_P)")
    NOTES.append("battery chain: BT1 + =JST= PG1 -solder- U2 shunt -solder- U1 BAT; BT1 - =JST= PG1 -solder- U1 BAT-; "
                 "BATP and MAX17048 VBAT on CELL_P")


def check_pin_maps():
    for jack, pins in PIN_MAPS.items():
        for pin, want in pins.items():
            got = NET_OF.get((jack, pin))
            if want is None and got is not None:
                fail(6, f"{jack} pin {pin} should be unused, is on {got}")
            elif want is not None and got != want:
                fail(6, f"{jack} pin {pin} should be {want}, is on {got}")
    for k in range(1, 5):
        sda, scl = NETS[f"P{k}_SDA"][0], NETS[f"P{k}_SCL"][0]
        ch = k - 1
        if ("U4", f"CH{ch}.SDA") not in sda or ("U4", f"CH{ch}.SCL") not in scl:
            fail(6, f"port S{k} is not on mux channel {ch}")
    NOTES.append("RJ11 maps: S1-S4 2 3V3 (via PTC), 3 SDA, 4 GND, 5 SCL; WIND 2/3 GND, 4 CUPS, 5 VANE; RAIN 3 GND, 4 RAIN")


FW_TOML = "firmware/board/wio-e5/board.toml"
FW_HDR = "firmware/board/wio-e5/Core/Inc/board_pins.h"


def firmware_pins():
    """The mini's pins as the firmware has them: board.toml (tools/boardgen.py's source) when it exists,
    else the older hand-written board_pins.h. Returns ({function: pin}, source path)."""
    toml_path = REPO / FW_TOML
    if toml_path.exists():
        import tomllib
        t = tomllib.loads(toml_path.read_text())
        pins, i2c = t.get("pins", {}), t.get("i2c", {})
        get = lambda d: d.get("pin") if isinstance(d, dict) and d.get("fitted", True) else None  # noqa: E731
        return ({"I2C_SDA": get(i2c.get("sda")), "I2C_SCL": get(i2c.get("scl")), "CUPS": get(pins.get("cups")),
                 "VANE": get(pins.get("vane")), "RAIN": get(pins.get("rain")), "MUX_RST": get(pins.get("mux_reset"))},
                FW_TOML)
    src = (REPO / FW_HDR).read_text()
    out = {}
    for key, fn in (("I2C_SDA", "I2C_SDA"), ("I2C_SCL", "I2C_SCL"), ("CUPS", "CUPS"), ("VANE", "VANE")):
        port = re.search(rf"#define BOARD_{fn}_PORT\s+GPIO([A-H])", src)
        pin = re.search(rf"#define BOARD_{fn}_PIN\s+GPIO_PIN_(\d+)", src)
        out[key] = f"P{port.group(1)}{pin.group(1)}" if port and pin else None
    m = re.search(r"rain (P[A-H]\d+)", src)
    out["RAIN"] = m.group(1) if m else None
    m = re.search(r"mux RESET (P[A-H]\d+)", src)
    out["MUX_RST"] = m.group(1) if m else None
    return out, FW_HDR


def check_firmware_pins():
    fw, src = firmware_pins()
    mcu_of = {pin[0]: pin[1] for pin in PART["A1"]["pins"]}
    for net, want in MCU_FUNCTION.items():
        on = [p for r, p in NETS[net][0] if r == "A1"]
        got = [mcu_of[p] for p in on]
        if got != [want]:
            fail(7, f"{net} is on mini pads {on} ({got}), the model wants {want}")
        if fw.get(net) != want:
            fail(7, f"{net}: model {want}, firmware {src} {fw.get(net)}")
    NOTES.append(f"Wio-E5 pins = {src}: " + ", ".join(f"{n} {fw[n]}" for n in MCU_FUNCTION))


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
            fail(8, f"ERC {v['severity']} {v['type']}: {v['description']} [{item}]")
    NOTES.append(f"ERC: {waived} violation(s) waived with a written reason (model.ERC_WAIVERS)")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    check_round_trip(kicad_nets(sys.argv[1]))
    check_pins()
    check_i2c()
    check_ptc()
    check_battery()
    check_pin_maps()
    check_firmware_pins()
    check_erc(sys.argv[2])
    for n in NOTES:
        print("note ", n)
    for f in FAILS:
        print("FAIL ", f)
    print(f"schematic {'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
