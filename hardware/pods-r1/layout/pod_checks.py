"""Pod electrical checks P1-P7 for the three sensor pods (TH, BARO, UV), run as a script or as a module.

  P1  copper: the netlist is built from the Perma-Proto strips and the wire ends alone (union-find, the method of the
      TX layout_checks build_copper); no strip carries two nets, and 3V3, GND, SDA, SCL and WP are each one connected group
  P2  the jack's pin map: 2 = 3V3, 3 = SDA, 4 = GND, 5 = SCL, pins 1 and 6 unconnected
  P3  each pod, on each TX sensor port S1-S4 through a straight cable, meets the TX's nets pin for pin
  P4  a reversed cable (1<->6, 2<->5, 3<->4) is detected (it puts 3V3 on SCL)
  P5  I2C addresses on a pod are unique: the sensor's and the EEPROM's 0x50
  P6  pull-up budget at the 2 m cable: total pull-up >= (3.3 - 0.4 V) / 3 mA and rise time 0.8473 R C <= 1000 ns
  P7  write protect: shunt on = WP at 3V3; shunt off = R1 holds WP at GND

The TX port model (hardware/tx-stack-r1/schematic/model.py) is loaded read-only under its own module name: PORTS and
PIN_MAPS give each port's jack and pin-to-net map, and the mux card U4's pullups_k the mux channel's pull-up.
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import pods                       # noqa: E402  hardware/pods-r1/layout/pods.py
import sources as S               # noqa: E402  hardware/pods-r1/sources.py

PP = pods.PP
NETS = ("3V3", "GND", "SDA", "SCL", "WP")
_TX_MODEL = _HERE.parent.parent / "tx-stack-r1" / "schematic" / "model.py"
_TX_NAMES = {"JSDA": "SDA", "JSCL": "SCL", "3V3": "3V3", "GND": "GND"}
PF_PER_DEVICE = 10.0
K_RISE = 0.8473                                 # 30 to 70 percent rise of an RC charge
CABLE_PF_TYPICAL = 100.0                        # pF/m; used only while sources.py cable_pf_per_m is TBD (see cable_pf_per_m)
SINK_NET = (3.3 - 0.4) / (S.val("i2c_sink_ma") * 1e-3)       # smallest total pull-up: 967 ohm


# ------------------------------------------------------------------ the TX port model (read-only)
def _tx_model():
    if "tx_stack_model" not in sys.modules:
        keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        spec = importlib.util.spec_from_file_location("tx_stack_model", _TX_MODEL)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["tx_stack_model"] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = keep
    return sys.modules["tx_stack_model"]


def tx_port_map(port):
    """{jack pin 1-6: net} of TX port S1-S4 (port: 1-4 or "S1"-"S4"), nets named as the pod names them."""
    m = _tx_model()
    k = int(str(port).lstrip("Ss"))
    out = {}
    for pin, net in m.PIN_MAPS[m.PORTS[k][0]].items():
        if net is None:
            out[int(pin)] = "NC"
        else:
            out[int(pin)] = _TX_NAMES[net.split("_", 1)[1] if net[0] == "P" and net[1].isdigit() else net]
    return out


def tx_mux_pullup_k():
    """The mux channel's header-side pull-up, kohm: the TX model's U4 pullups_k (the PCA9548 board's pull-ups)."""
    m = _tx_model()
    return next(p for p in m.PARTS if p["ref"] == "U4")["pullups_k"]


# ------------------------------------------------------------------ P1: copper
def _pins(pod):
    """Every pin node with its declared net: {(ref, pin): (hole, net or "NC")}. The TH lead's sensor-end pads
    ("U2", pad) are nodes too, joined to the pod-end hole the conductor is soldered into."""
    out = {}
    for p in pod.parts:
        for pin, hole in p.pins.items():
            out[(p.ref, pin)] = (hole, p.nets.get(pin) or "NC")
    if pod.lead:
        for c in pod.lead.conductors:
            out[(pod.lead.ref, c.pad)] = (c.hole, c.net)
    return out


def _groups(pod, join=()):
    """Copper groups: union-find over strip_of(hole), joined by each wire's two end holes. join: extra (pin, pin)
    pairs (the shunt). Returns a list of sets of (ref, pin)."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    pins = _pins(pod)
    for w in pod.wires:
        union(PP.strip_of(w.hole_a), PP.strip_of(w.hole_b))
    for a, b in join:
        union(PP.strip_of(pins[a][0]), PP.strip_of(pins[b][0]))
    groups = {}
    for key, (hole, _) in pins.items():
        groups.setdefault(find(PP.strip_of(hole)), set()).add(key)
    return list(groups.values())


def _labels(pod, group):
    pins = _pins(pod)
    return sorted({pins[k][1] for k in group})


def netlist(pod):
    """{net: {(ref, pin), ...}} from copper alone. A group is named by the declared nets of its pins: one net gives
    that name; a second group of the same net is "SDA#2" (an open); mixed nets give "3V3+GND" (a short). Pins left
    unconnected on purpose are "NC"."""
    out, seen = {}, {}
    for g in sorted(_groups(pod), key=lambda g: sorted(g)):
        name = "+".join(_labels(pod, g))
        seen[name] = seen.get(name, 0) + 1
        out[name if seen[name] == 1 else f"{name}#{seen[name]}"] = g
    return out


def net_of(pod, ref, pin):
    return _pins(pod)[(ref, str(pin))][1]


def copper_faults(pod):
    """Shorts (a group with two declared nets), opens (a declared net in two groups, or missing one of its pins),
    and a pin left unconnected on purpose that shares copper with another pin."""
    faults, per_net = [], {}
    declared = pod.nets()
    for g in _groups(pod):
        labs = _labels(pod, g)
        if len(labs) > 1:
            faults.append(f"{pod.name}: short between {' and '.join(labs)} ({sorted(f'{r}.{p}' for r, p in g)})")
        for lab in labs:
            per_net.setdefault(lab, []).append(g)
        if labs == ["NC"] and len(g) > 1:
            faults.append(f"{pod.name}: unconnected pins share copper: {sorted(f'{r}.{p}' for r, p in g)}")
    for net, pins in declared.items():
        gs = per_net.get(net, [])
        if len(gs) != 1:
            faults.append(f"{pod.name}: {net} is open: {len(gs)} copper groups for pins {sorted(pins)}")
        else:
            got = {f"{r}.{p}" for r, p in gs[0] if _pins(pod)[(r, p)][1] == net}
            if got != pins:
                faults.append(f"{pod.name}: {net} copper group {sorted(got)} is not the declared {sorted(pins)}")
    return faults


# ------------------------------------------------------------------ P2-P4: pin map, ports, cable
def cable_map(kind):
    """TX jack pin -> pod jack pin through the cable. A straight 6-conductor cable has a plug at each end; a reversed
    one (the two plugs crimped on the same way round) swaps 1<->6, 2<->5 and 3<->4."""
    if kind == "straight":
        return {i: i for i in range(1, 7)}
    if kind == "reversed":
        return {i: 7 - i for i in range(1, 7)}
    raise ValueError(kind)


def end_to_end(pod, port, cable="straight"):
    """{TX pin: (pod net, TX net)} for TX port S<port> through the cable; they match when the pod is wired right."""
    tx, cm = tx_port_map(port), cable_map(cable)
    return {t: (net_of(pod, "J1", cm[t]), tx[t]) for t in range(1, 7)}


def cable_faults(pod, cable="straight"):
    return [f"{pod.name} on S{k} through a {cable} cable: TX pin {t} ({tx}) meets the pod's {pn}"
            for k in range(1, 5) for t, (pn, tx) in end_to_end(pod, k, cable).items() if pn != tx]


# ------------------------------------------------------------------ P5: addresses
def addresses(pod):
    keys = [pod.sensor, "eeprom_24lc32"]
    return [int(S.val(k + "_addr"), 16) for k in keys]


# ------------------------------------------------------------------ P6: pull-ups and rise time
def breakouts(pod):
    """(ref, sources.py key) of every Adafruit breakout the pod carries; the TH's SHT45 is the lead's far end."""
    out = [(p.ref, p.source) for p in pod.parts if p.kind == "BREAKOUT"]
    if pod.lead:
        out.append((pod.lead.ref, pod.lead.source))
    return sorted(out)


def pullups(pod):
    """[(where, kohm)] of every fitted pull-up on one bus line: the TX mux channel's, then one per breakout (each
    Adafruit breakout carries 10 k on SDA and SCL on its header side; none has a jumper to cut them)."""
    return [("TX mux channel (U4)", tx_mux_pullup_k())] + [(f"{ref} {S.val(k + '_pullup_k')} k on {k}", S.val(k + "_pullup_k"))
                                                           for ref, k in breakouts(pod)]


def _parallel(kohms):
    return 1.0 / sum(1.0 / k for k in kohms)


def pullup_total(pod, extra_k=()):
    """Every fitted pull-up in parallel, ohms. extra_k: further pull-ups (kohm) to test a budget with."""
    return 1000.0 * _parallel([k for _, k in pullups(pod)] + list(extra_k))


def cable_pf_per_m():
    """Cable pF/m: sources.py cable_pf_per_m, or while that is TBD the typical 100 pF/m of PVC multi-conductor 24-28 AWG
    cable (50-100 pF/m between conductors in the catalogues; the top is taken). The report says which was used."""
    v = S.val("cable_pf_per_m")
    return CABLE_PF_TYPICAL if v is None else v


def device_count(pod):
    """Devices loading the bus line: the pod's breakouts (sensor, EEPROM) and the TX mux channel."""
    return len(breakouts(pod)) + 1


def bus_pf(pod, metres):
    """Cable (metres x pF/m), 10 pF per device and, on TH, the lead at the same pF/m."""
    lead = pod.lead.length_m * cable_pf_per_m() if pod.lead else 0.0
    return metres * cable_pf_per_m() + PF_PER_DEVICE * device_count(pod) + lead


def rise_ns(pod, metres, extra_k=()):
    """30 to 70 percent rise time, ns: 0.8473 R C (ohm x pF = 1e-3 ns)."""
    return K_RISE * pullup_total(pod, extra_k) * bus_pf(pod, metres) * 1e-3


def budget_failures(pod, metres=None, extra_k=()):
    metres = S.val("cable_max_m") if metres is None else metres
    out, r = [], pullup_total(pod, extra_k)
    if r < SINK_NET:
        # every Adafruit breakout's 10 k pull-ups are in parallel with the TX mux channel's; remove the last one added
        ref, key = breakouts(pod)[0]
        out.append(f"{pod.name}: pull-up {r:.0f} ohm < {SINK_NET:.0f} ohm (3 mA sink at 0.4 V): remove the 10 k header-side "
                   f"pull-ups on {ref} ({key}); the board has no jumper, so cut the pack's resistor")
    t = rise_ns(pod, metres, extra_k)
    if t > S.val("rise_ns_max"):
        out.append(f"{pod.name}: rise time {t:.0f} ns > {S.val('rise_ns_max')} ns at {metres:g} m: shorten the cable or "
                   f"cut the capacitance (removing a pull-up makes it slower)")
    return out


# ------------------------------------------------------------------ P7: write protect
def wp_level(pod, shunt):
    """The level of the EEPROM's WP pin: "3V3" with the shunt on (JP1 pin 1, 3V3, joined to pin 2, WP); with it off,
    "GND" when R1 ties WP to the ground net, else "floating"."""
    g = next(g for g in _groups(pod, [(("JP1", "1"), ("JP1", "2"))] if shunt else []) if ("U1", "WP") in g)
    labs = set(_labels(pod, g))
    if "3V3" in labs:
        return "3V3"
    if ("R1", "1") in g:
        return net_of(pod, "R1", "2")
    return "floating"


# ------------------------------------------------------------------ the whole set
def check_all():
    fails = []
    spec = {2: "3V3", 3: "SDA", 4: "GND", 5: "SCL", 1: "NC", 6: "NC"}
    for n in pods.POD_NAMES:
        p = pods.pod(n)
        fails += copper_faults(p)                                                       # P1
        fails += [f"{n}: J1 pin {k} is {net_of(p, 'J1', k)}, spec {v}" for k, v in spec.items()
                  if net_of(p, "J1", k) != v]                                           # P2
        fails += cable_faults(p, "straight")                                            # P3
        if not cable_faults(p, "reversed"):                                             # P4
            fails.append(f"{n}: a reversed cable is not flagged")
        a = addresses(p)                                                                # P5
        if len(a) != len(set(a)):
            fails.append(f"{n}: duplicate I2C address {[hex(x) for x in a]}")
        fails += budget_failures(p)                                                     # P6
        for sh, want in ((True, "3V3"), (False, "GND")):                                # P7
            if wp_level(p, sh) != want:
                fails.append(f"{n}: WP with the shunt {'on' if sh else 'off'} is {wp_level(p, sh)}, wanted {want}")
    return fails


def report():
    pf = S.val("cable_pf_per_m")
    m = S.val("cable_max_m")
    lines = [f"cable {m:g} m at {cable_pf_per_m():g} pF/m"
             + (" (TYPICAL, sources.py cable_pf_per_m is TBD: measure the bought cable)" if pf is None else ""),
             f"TX mux channel pull-up {tx_mux_pullup_k():g} k (read from tx-stack-r1/schematic/model.py U4 pullups_k)"]
    for n in pods.POD_NAMES:
        p = pods.pod(n)
        lines.append(f"{n:5s} pull-ups {' || '.join(f'{k:g}k' for _, k in pullups(p))} = {pullup_total(p):.0f} ohm "
                     f"(min {SINK_NET:.0f}); C {bus_pf(p, m):.0f} pF ({device_count(p)} devices"
                     + (f", lead {p.lead.length_m:g} m" if p.lead else "") + f"); rise {rise_ns(p, m):.0f} ns "
                     f"(max {S.val('rise_ns_max')}); addresses {', '.join(hex(x) for x in addresses(p))}; "
                     f"WP shunt on {wp_level(p, True)}, off {wp_level(p, False)}")
    return lines


if __name__ == "__main__":
    print("\n".join(report()))
    f = check_all()
    print("\n".join(["FAIL: " + x for x in f]) or "P1-P7: all pass")
    sys.exit(1 if f else 0)
