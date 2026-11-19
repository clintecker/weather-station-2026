"""TX card cage r2: the electrical source of truth.

The Wio-E5 mini TX (issue #35) on four SolderFul cards in a printed card cage, joined by a stripboard
backplane. kicad_gen.py draws the schematic from this file, checks.py checks it against KiCad's netlist and
against r1 (r1-connections.json), and ../layout/ places every pin of it on a hole.

Net keys (P1_SDA, CELL_P, ...) are code identifiers only. Everything a person reads uses NET_NAME: the
schematic labels, the build sheets, the drawings.

Pin tuple: (number, name, electrical type, contact). Contact is how a conductor meets the pin:
  header   a 0.1 in pin soldered into a card or backplane hole (it joins that hole's strip)
  socket   a 2.54 mm female header contact on the backplane (it joins that backplane strip)
  solder   a lead soldered straight to a pad or a wire end (no strip, no connector)
  lead     a flying lead soldered into a breakout's own hole (the RJ11 breakouts)
  jst      the pack's own JST PH mating           qt   a STEMMA QT (JST SH) mating
  rj11     an RJ11 6P6C mating                    usb  a USB mating
  sma      an SMA mating                          evm  a BQ25798EVM screw terminal or header pin (SLUUCB5)
  nc       left unconnected
"""

PAS, PIN, POUT, IN, OC, BI, OUT = ("passive", "power_in", "power_out", "input", "open_collector",
                                   "bidirectional", "output")


def qt(prefix, contact="qt"):
    return [(f"{prefix}.GND", "GND", PAS, contact), (f"{prefix}.V+", "V+", PIN, contact),
            (f"{prefix}.SDA", "SDA", BI, contact), (f"{prefix}.SCL", "SCL", BI, contact)]


def bob(ref, value, used, board):
    """BOB-14021 with an 87180-066LF jack, standing on its soldered 1x6 male header, mouth toward the card's front
    edge (the lid). Jack contact n is the breakout's hole n and header pin n, each in its own card strip; an unused
    contact's pin sits alone in its strip."""
    return dict(ref=ref, value=value, part="SparkFun BOB-14021 + Amphenol 87180-066LF", block=board,
                pins=[(str(i), f"contact {i}", PAS, "header" if i in used else "nc") for i in range(1, 7)])


def module(ref, value, sensor, addr):
    """An outdoor I2C module end: sensor breakout + 24LC32-class ID EEPROM (0x50) on one RJ11 cable."""
    return dict(ref=ref, value=value, part=f"{sensor} + 24LC32 EEPROM, Perma-Proto 1608", block="outdoor",
                pins=[("2", "3.3 V", PIN, "rj11"), ("3", "data (SDA)", BI, "rj11"), ("4", "ground", PAS, "rj11"),
                      ("5", "clock (SCL)", BI, "rj11")], i2c=[0x50, addr], pullups_k=10.0)


def two(ref, value, part, block, names=("1", "2")):
    return dict(ref=ref, value=value, part=part, block=block,
                pins=[("1", names[0], PAS, "header"), ("2", names[1], PAS, "header")])


ZENER = "onsemi 1N5232B, 5.6 V 500 mW zener, DO-35 (port supply clamp)"
SCHOTTKY = "Vishay BAT85S, 30 V 200 mA Schottky, DO-35, <= 10 pF (signal clamp)"
R100 = "Stackpole CF14JT100R, 100 ohm 1/4 W"
R1K = "Stackpole CF14JT1K00, 1 kohm 1/4 W"
R10K = "MFR-25 10K, 10 kohm 1/4 W"
C100N = "KEMET C320C104K5R5TA, 100 nF"

# Wio-E5 mini header pads (Seeed LoRa-E5 mini v1.0.brd, J1): B row and D row, pad -> MCU pin
MINI_B = ["5V", "3V3", "PA13", "PA14", "RST", "GND", "PA10", "PB14", "PB9", "PB13", "PB10", "PA9"]
MINI_D = ["PA2", "PA3", "PC1", "PC0", "PA0", "PB6", "PB7", "PB3", "PB4", "PA15", "PB15", "GND"]
MINI_USED = {"B2", "B3", "B4", "B5", "B6", "B8", "D4", "D8", "D9", "D10", "D11", "D12"}
MINI_PLAIN = {"5V": "USB 5 V", "3V3": "3.3 V", "GND": "ground", "RST": "reset (NRST)", "PA13": "debug data (PA13)",
              "PA14": "debug clock (PA14)", "PB14": "mux reset out (PB14)", "PC0": "cups in (PC0)",
              "PB3": "vane in (PB3)", "PB4": "rain in (PB4)", "PA15": "I2C data (PA15)", "PB15": "I2C clock (PB15)",
              "PA9": "sensor power (PA9, not wired)"}


def mini_pins():
    out = []
    for row, names in (("B", MINI_B), ("D", MINI_D)):
        for i, n in enumerate(names, 1):
            num = f"{row}{i}"
            et = PIN if n == "3V3" else PAS if n in ("GND", "5V") else BI
            out.append((num, MINI_PLAIN.get(n, n), et, "header" if num in MINI_USED else "nc"))
    return out + [("ANT", "antenna (SMA)", PAS, "sma")]


# ------------------------------------------------------------------ the backplane bus
# One row strip per line on every card (rows 1-18, f-j half; the card's right-angle header sits in column j),
# one strip per line on the stripboard backplane. Order chosen so each port's data and clock sit on adjacent
# rows next to its protection parts (layout/stack.py).
BUS = ["+3V3", "GND", "P1_SDA", "P1_SCL", "CUPS", "VANE", "I2C_SCL", "P2_SDA", "P2_SCL", "I2C_SDA", "RAIN", "GND",
       "P3_SDA", "P3_SCL", "MUX_RST", "BUS_SPARE", "P4_SDA", "P4_SCL"]
CARDS = {"B1": "PORTS A", "B2": "PORTS B + METERS", "B3": "CORE", "B4": "POWER"}


# Every card has the full 1x30 right-angle header (card rows 1-30, column j) and every backplane socket is 1x30:
# card pin n on backplane line n (the columns sit straight over the lines). Lines 1-18 are the bus. B4's power pins
# on lines 19-26: header pin / backplane line -> net; the ~1 A battery legs each take two pins.
B4_POWER = {19: "BAT_P", 20: "BAT_P", 21: "CELL_P", 22: "CELL_P", 23: "GAUGE_S", 26: "SYS"}
# pins 19-30 whose card row strip carries a card-local net: the header pin is on that net (it sits in the strip) and
# so is the socket contact it mates, but that contact is soldered to an isolated backplane pad (no bus wire there)
CARD_LOCAL = {"B3": {20: "+3V3", 21: "SWDIO", 22: "SWCLK", 23: "NRST", 24: "GND", 26: "MUX_RST"},
              "B4": {24: "+3V3", 25: "GND"}}
HDR_LEN = {"B1": 30, "B2": 30, "B3": 30, "B4": 30}
# Slot keys (Clint, 2026-11-16): the four sockets are identical, so without a key any card would seat in any slot
# (B3 in B4's would put the battery on the Wio-E5). Lines 27-30 carry nothing on any card (no BUS, B4_POWER or
# CARD_LOCAL pin there), so each card pulls one of them out of its header, and its own backplane socket takes a key
# plug in that same position: a male pin cut off the generic header stock, pushed into that socket contact, flush
# with the mouth, soldered to nothing (the contact's pad stays isolated). Every other card still has that pin, so it
# stubs on the plug and cannot seat. KEY_COLOUR: the dot on each card's front edge and on its slot.
PULLED = {"B1": (27,), "B2": (28,), "B3": (29,), "B4": (30,)}
KEY = {c: p[0] for c, p in PULLED.items()}          # the socket position holding the key plug, per card's socket
KEY_COLOUR = {"B1": "blue", "B2": "green", "B3": "yellow", "B4": "red"}


def line_net(i):
    """The net backplane line i's bus wire carries (None: no shared net, every contact on it is an isolated pad)."""
    return BUS[i - 1] if 1 <= i <= len(BUS) else B4_POWER.get(i)


def pin_net(card, i):
    """The net on a card's header pin i (and the socket contact it mates), or None."""
    if i <= len(BUS):
        return BUS[i - 1]
    if card == "B4" and i in B4_POWER:
        return B4_POWER[i]
    return CARD_LOCAL.get(card, {}).get(i)


def hdr_pins(card):
    return [i for i in range(1, HDR_LEN[card] + 1) if i not in PULLED.get(card, ())]


def socket_pins(card):
    """Every contact of the card's 1x30 backplane socket, the key plug's included (it is soldered like the rest)."""
    return list(range(1, HDR_LEN[card] + 1))


def _pname(card, i):
    if i <= len(BUS):
        return f"bus {i}"
    n = pin_net(card, i)
    if n is None:
        return f"spare {i}"
    return f"power {i}" if card == "B4" and i in B4_POWER else f"local {i} ({n})"


def card_header(card):
    n = HDR_LEN[card]
    return dict(ref=f"XH{card[1]}", value=f"bus header 1x{n} R/A", block="bus", card=card,
                part=f"generic 2.54 mm right-angle male header, cut to 1x{n}, card back edge; pin {KEY[card]} pulled (slot key)",
                pins=[(str(i), _pname(card, i), PAS, "header" if pin_net(card, i) else "nc") for i in hdr_pins(card)])


def bp_socket(card):
    n = HDR_LEN[card]
    return dict(ref=f"XB{card[1]}", value=f"bus socket 1x{n}", block="bus", card="BP",
                part=f"generic 2.54 mm female header strip, cut to 1x{n} (one position lost at each cut), on the backplane; key plug in contact {KEY[card]}", mates=card,
                pins=[(str(i), f"key plug {i}" if i == KEY.get(card) else _pname(card, i), PAS,
                       "socket" if pin_net(card, i) and i in hdr_pins(card) else "nc") for i in socket_pins(card)])


PARTS = [
    # ------------------------------------------------------------ sources and the charger (beside the cards)
    dict(ref="PS1", value="USB 5 V adapter", part="wall adapter >= 2 A, USB-C to micro-B cable into EVM J6",
         block="power", pins=[("VBUS", "5 V", POUT, "usb"), ("GND", "ground", PAS, "usb")]),
    dict(ref="PV1", value="Solar P110", part="Voltaic P110 6 V 10 W (barrel cut at the gland)", block="power",
         pins=[("+", "+", POUT, "evm"), ("-", "-", PAS, "evm")]),
    dict(ref="U1", value="BQ25798EVM", block="power",
         part="TI BQ25798EVM (SLUUCB5): JP22 only on PROG (1S), JP24 out, JP9 out, JP18 out, JP12/JP17/JP30 in",
         pins=[("VIN1", "USB in (J6 micro-B, JP7 = VIN1)", PIN, "usb"), ("PGND1", "USB ground", PAS, "usb"),
               ("VIN2", "solar in (J2 VIN2)", PIN, "evm"), ("PGND2", "solar ground (J2)", PAS, "evm"),
               ("BAT", "battery + (J5 BATTERY)", PAS, "evm"), ("BATP", "battery sense (J5 SNS_BATP)", IN, "evm"),
               ("BATN", "battery - (J5 GND)", PAS, "evm"), ("SYS", "system out (J3 SYS)", POUT, "evm"),
               ("SYSN", "system ground (J3 GND)", PAS, "evm"), ("TS", "thermistor (J7)", IN, "evm"),
               ("TSN", "thermistor ground (J7 GND)", PAS, "evm"), ("J8.1", "ground (J8-1)", PAS, "evm"),
               ("J8.2", "I2C clock (J8-2)", BI, "evm"), ("J8.3", "I2C data (J8-3)", BI, "evm"),
               ("J8.4", "pull-up rail (J8-4)", PAS, "nc"), ("INT", "interrupt (INT)", OC, "nc")],
         ties=[["PGND1", "PGND2", "BATN", "SYSN", "TSN", "J8.1"]], i2c=[0x6B], pullups_k=10.0,
         note="R39-R42 10 kohm pull-ups to its 3.3 V PULLUP rail stay fitted (JP30 in); INT not wired yet "
              "(the bus keeps a spare line for it)"),
    dict(ref="RT1", value="10k NTC", part="Adafruit #372 10 kohm NTC (B 3950), taped to the pack, into EVM J7",
         block="battery", pins=[("1", "1", PAS, "solder"), ("2", "2", PAS, "solder")],
         note="the EVM's TS divider is set for a 103AT (B 3435): the cold and hot thresholds shift; see README"),
    # ------------------------------------------------------------ battery (soldered end to end, never a strip)
    dict(ref="BT1", value="1S3P 6600mAh", part="Adafruit #353 (own protection board)", block="battery",
         pins=[("+", "+", POUT, "jst"), ("-", "-", PAS, "jst")]),
    dict(ref="PG1", value="JST PH pigtail", part="JST PH 2-pin socket with leads (mates the pack, unmodified)",
         block="battery", pins=[("M+", "plug +", PAS, "jst"), ("M-", "plug -", PAS, "jst"),
                                ("L+", "lead +", PAS, "solder"), ("L-", "lead -", PAS, "solder")],
         ties=[["M+", "L+"], ["M-", "L-"]]),
    dict(two("R7", "100", R100 + " (charger sense, on the backplane at the battery + junction)", "battery"), card="BP",
         pins=[("1", "1", PAS, "solder"), ("2", "2", PAS, "solder")]),
    dict(two("R8", "100", R100 + " (gauge sense, on the backplane at the battery + junction)", "battery"), card="BP",
         pins=[("1", "1", PAS, "solder"), ("2", "2", PAS, "solder")]),
    # ------------------------------------------------------------ B4 POWER
    dict(ref="U2", value="INA228 0x40", part="Adafruit #5832", block="battery", card="B4",
         pins=[("H.VIN", "VIN", PIN, "header"), ("H.GND", "GND", PAS, "header"), ("H.SCL", "SCL", BI, "header"),
               ("H.SDA", "SDA", BI, "header"), ("H.VBUS", "VBUS", PAS, "nc"), ("H.VIN-", "VIN-", PAS, "nc"),
               ("H.VIN+", "VIN+", PAS, "nc"), ("H.ALRT", "ALERT", OC, "nc"),
               ("X1.VIN+", "shunt in (X1 VIN+)", PAS, "solder"), ("X1.VBUS", "VBUS", PAS, "nc"),
               ("X1.VIN-", "shunt out (X1 VIN-)", PAS, "solder")] + qt("QT1", "nc") + qt("QT2", "nc"),
         ties=[["H.VIN+", "X1.VIN+", "X1.VBUS", "H.VBUS"], ["H.VIN-", "X1.VIN-"], ["H.VIN", "QT1.V+", "QT2.V+"],
               ["H.GND", "QT1.GND", "QT2.GND"], ["H.SDA", "QT1.SDA", "QT2.SDA"], ["H.SCL", "QT1.SCL", "QT2.SCL"]],
         i2c=[0x40], pullups_k=10.0, removed=["H.VBUS", "H.VIN-", "H.VIN+"],
         note="shunt in the pack + leg (high side); SJ1 soldered closed so VBUS sits on VIN+ (open as shipped: Adafruit #5832 guide, VBUS jumper; INA228 bus voltage and power read VBUS); leads soldered to the X1 pads (no terminal block); header pins 5-7 pulled"),
    dict(ref="U6", value="MAX17048 0x36", part="Adafruit #5580", block="battery", card="B4",
         pins=[("H.VIN", "VIN", PIN, "header"), ("H.GND", "GND", PAS, "header"), ("H.SCL", "SCL", BI, "header"),
               ("H.SDA", "SDA", BI, "header"), ("H.INT", "INT", OC, "nc"), ("H.QST", "QST", IN, "nc"),
               ("JP2.VBAT", "cell sense (JP2 VBAT)", PAS, "solder"), ("JP2.GND", "GND", PAS, "nc"),
               ("BAT1.+", "BAT+", PAS, "nc"), ("BAT2.+", "BAT+", PAS, "nc")] + qt("QT1", "nc") + qt("QT2", "nc"),
         ties=[["JP2.VBAT", "BAT1.+", "BAT2.+"], ["H.GND", "JP2.GND", "QT1.GND", "QT2.GND"],
               ["H.VIN", "QT1.V+", "QT2.V+"], ["H.SDA", "QT1.SDA", "QT2.SDA"], ["H.SCL", "QT1.SCL", "QT2.SCL"]],
         i2c=[0x36], pullups_k=10.0, note="cell sense through R8 from the battery + junction on the backplane (B4 header pin 23)"),
    dict(ref="U7", value="S7V8F3 3.3V", part="Pololu #2122", block="power", card="B4",
         pins=[("VOUT", "3.3 V out", POUT, "header"), ("GND", "ground", PAS, "header"), ("VIN", "in", PIN, "header"),
               ("SHDN", "shutdown", IN, "nc")], note="SHDN open: enabled"),
    card_header("B4"),
    # ------------------------------------------------------------ B3 CORE
    dict(ref="A1", value="Wio-E5 mini TX", part="Seeed Wio-E5 mini (113990939), STM32WLE5JC", block="radio",
         card="B3", pins=mini_pins(), i2c=[], pullups_k=4.7,
         note="4.7 kohm I2C pull-ups R15/R16 on board; 3.3 V fed in on its 3V3 pad; USB-C = console"),
    dict(ref="J3", value="SWD 1x5 R/A", part="generic 2.54 mm right-angle male header (the bus header stock), cut to 1x5; ST-LINK Dupont leads",
         block="radio", card="B3",
         pins=[("1", "3.3 V", PAS, "header"), ("2", "SWDIO", PAS, "header"), ("3", "SWCLK", PAS, "header"),
               ("4", "NRST", PAS, "header"), ("5", "ground", PAS, "header")]),
    dict(ref="U5", value="SHTC3 0x70", part="Adafruit #4636", block="radio", card="B3",
         pins=[("VIN", "VIN", PIN, "header"), ("3V", "3V out", POUT, "nc"), ("GND", "GND", PAS, "header"),
               ("SCL", "SCL", BI, "header"), ("SDA", "SDA", BI, "header")], i2c=[0x70], pullups_k=10.0),
    dict(ref="AD1", value="SMA right angle", part="Amphenol RF 132172 (SMA plug to jack, right angle)",
         block="radio", pins=[("P", "plug", PAS, "sma"), ("J", "jack", PAS, "sma")], ties=[["P", "J"]]),
    dict(ref="CX1", value="SMA cable 6in", part="Amphenol 135110-01-06.00 (RG-316, bulkhead jack)", block="radio",
         pins=[("P", "plug", PAS, "sma"), ("J", "bulkhead", PAS, "sma")], ties=[["P", "J"]]),
    dict(ref="AE1", value="ANT-916-CW-HWR", part="Linx ANT-916-CW-HWR-SMA (outside, tilted up)", block="radio",
         pins=[("RF", "RF", PAS, "sma")]),
    card_header("B3"),
    # ------------------------------------------------------------ B2 PORTS B + METERS
    bob("J14", "RJ11 S4", {2, 3, 4, 5}, "ports"),
    bob("J21", "RJ11 WIND", {2, 3, 4, 5}, "meters"),
    bob("J22", "RJ11 RAIN", {3, 4}, "meters"),
    two("R1", "10k", R10K + " (cups pull-up)", "meters"),
    two("R2", "10k", R10K + " (vane pull-up)", "meters"),
    two("R3", "10k", R10K + " (rain pull-up)", "meters"),
    two("R4", "1k", R1K + " (cups series)", "meters"),
    two("R5", "1k", R1K + " (vane series)", "meters"),
    two("R6", "1k", R1K + " (rain series)", "meters"),
    two("C1", "100nF", C100N + " (cups filter)", "meters"),
    two("C2", "100nF", C100N + " (rain filter)", "meters"),
    two("C3", "100nF", C100N + " (vane filter)", "meters"),
    *[two(f"D5{i}", "1N5232B", ZENER.replace("port supply", w), "meters", ("cathode", "anode"))
      for i, w in ((1, "cups clamp"), (2, "vane clamp"), (3, "rain clamp"))],
    card_header("B2"),
    # ------------------------------------------------------------ B1 PORTS A
    bob("J11", "RJ11 S1", {2, 3, 4, 5}, "ports"),
    bob("J12", "RJ11 S2", {2, 3, 4, 5}, "ports"),
    bob("J13", "RJ11 S3", {2, 3, 4, 5}, "ports"),
    card_header("B1"),
    # per port: PTC, two series resistors, three clamps (on B1 for S1-S3, B2 for S4)
    *[p for k in range(1, 5) for p in (
        dict(two(f"F{k}", "MF-R010", "Bourns MF-R010 100 mA PTC", "ports"), note=f"port S{k} 3.3 V"),
        two(f"R{k}1", "100", R100 + f" (port S{k} data series)", "ports"),
        two(f"R{k}2", "100", R100 + f" (port S{k} clock series)", "ports"),
        two(f"D{k}1", "1N5232B", ZENER + f" (port S{k} 3.3 V)", "ports", ("cathode", "anode")),
        two(f"D{k}2", "BAT85S", SCHOTTKY + f" (port S{k} data to its 3.3 V)", "ports", ("anode", "cathode")),
        two(f"D{k}3", "BAT85S", SCHOTTKY + f" (port S{k} ground to data)", "ports", ("anode", "cathode")),
        two(f"D{k}4", "BAT85S", SCHOTTKY + f" (port S{k} clock to its 3.3 V)", "ports", ("anode", "cathode")),
        two(f"D{k}5", "BAT85S", SCHOTTKY + f" (port S{k} ground to clock)", "ports", ("anode", "cathode")))],
    # ------------------------------------------------------------ the backplane (BusBoard ST2 stripboard strip)
    *[bp_socket(c) for c in ("B4", "B2", "B1", "B3")],
    dict(ref="XJ1", value="charger bus pins", block="bus", card="BP",
         part="three 0.1 in male pins on the backplane; 3-wire lead to EVM J8 (Molex KK 2695 housing)",
         pins=[("GND", "ground", PAS, "header"), ("SCL", "clock", PAS, "header"), ("SDA", "data", PAS, "header")]),
    dict(ref="U4", value="PCA9548 0x71", part="Adafruit #5626 (A0 bridged, Vlogic SW1 = V+), foam pad on the backplane",
         block="ports", card="BP",
         pins=[("H.VCC", "VIN", PIN, "solder"), ("H.GND", "GND", PAS, "solder"), ("H.SCL", "SCL", BI, "solder"),
               ("H.SDA", "SDA", BI, "solder"), ("H.RST", "RESET", IN, "solder")]
         + qt("UP", "nc") + sum(([(p, n, t, "nc" if n == "V+" else c) for p, n, t, c in qt(f"CH{k}")] for k in range(4)), []),
         ties=[["H.GND", "UP.GND"] + [f"CH{k}.GND" for k in range(4)], ["H.VCC", "UP.V+"],
               ["H.SDA", "UP.SDA"], ["H.SCL", "UP.SCL"]],
         i2c=[0x71], pullups_k=10.0,
         note="five header leads (VIN GND SCL SDA RST); channels 0-3 each take a #4209 QT cable, pin end cut off, its "
              "SDA and SCL wires to sensor ports 1-4 (V+ and GND cut back and taped); upstream port empty"),
    # ------------------------------------------------------------ outdoors
    module("MOD1", "TH module", "SHT45 #6174", 0x44),
    module("MOD2", "Baro module", "BMP581 #6407", 0x47),
    module("MOD3", "UV module", "LTR390 #4831", 0x53),
    dict(ref="M1", value="Wind (vane+cups)", part="SparkFun SEN-15901", block="outdoor",
         pins=[("2", "vane return", PAS, "rj11"), ("3", "cups return", PAS, "rj11"), ("4", "cups", PAS, "rj11"),
               ("5", "vane", PAS, "rj11")]),
    dict(ref="M2", value="Rain gauge", part="SparkFun SEN-15901", block="outdoor",
         pins=[("3", "rain return", PAS, "rj11"), ("4", "rain", PAS, "rj11")]),
]

# which card each part is soldered to (None: off the cards)
for _p in PARTS:
    _p.setdefault("card", None)
for _ref, _card in [("J11", "B1"), ("J12", "B1"), ("J13", "B1"), ("J14", "B2"), ("J21", "B2"), ("J22", "B2")] + \
        [(f"{x}{k}{s}", "B1" if k < 4 else "B2") for k in range(1, 5) for x, ss in (("R", "12"), ("D", "12345")) for s in ss] + \
        [(f"F{k}", "B1" if k < 4 else "B2") for k in range(1, 5)] + \
        [(r, "B2") for r in ("R1", "R2", "R3", "R4", "R5", "R6", "C1", "C2", "C3", "D51", "D52", "D53")]:
    next(p for p in PARTS if p["ref"] == _ref)["card"] = _card

PORTS = {1: ("J11", "MOD1", 0), 2: ("J12", "MOD2", 1), 3: ("J13", "MOD3", 2), 4: ("J14", None, 3)}
HEADERS = {c: f"XH{c[1]}" for c in CARDS}
SOCKETS = {c: f"XB{c[1]}" for c in CARDS}


def bus(net):
    """Every card header pin and backplane socket pin of the bus line(s) carrying `net`."""
    out = []
    for i, n in enumerate(BUS, 1):
        if n == net:
            for c in CARDS:
                out += [(HEADERS[c], str(i)), (SOCKETS[c], str(i))]
    return out


def power(net):
    """B4's header pins and the B4 socket's pins carrying `net` (B4_POWER)."""
    return [x for i, n in B4_POWER.items() if n == net for x in ((HEADERS["B4"], str(i)), (SOCKETS["B4"], str(i)))]


def port_nets():
    out = {}
    for k, (jack, mod, ch) in PORTS.items():
        m = [] if mod is None else [mod]
        out[f"P{k}_3V3"] = ([(f"F{k}", "2"), (f"D{k}1", "1"), (f"D{k}2", "2"), (f"D{k}4", "2"), (jack, "2")] + [(x, "2") for x in m], dict(vmax=3.4))
        out[f"P{k}_JSDA"] = ([(jack, "3"), (f"D{k}2", "1"), (f"D{k}3", "2"), (f"R{k}1", "1")] + [(x, "3") for x in m], dict(vmax=3.6))
        out[f"P{k}_JSCL"] = ([(jack, "5"), (f"D{k}4", "1"), (f"D{k}5", "2"), (f"R{k}2", "1")] + [(x, "5") for x in m], dict(vmax=3.6))
        out[f"P{k}_SDA"] = ([(f"R{k}1", "2"), ("U4", f"CH{ch}.SDA")]
                            + bus(f"P{k}_SDA"), dict(vmax=3.6))
        out[f"P{k}_SCL"] = ([(f"R{k}2", "2"), ("U4", f"CH{ch}.SCL")]
                            + bus(f"P{k}_SCL"), dict(vmax=3.6))
    return out


# battery: carries the cell's charge or discharge current (the F1 rule applies). force: other power current.
NETS = {
    "PACK_P": ([("BT1", "+"), ("PG1", "M+")], dict(battery=True)),
    "PACK_N": ([("BT1", "-"), ("PG1", "M-")], dict(battery=True)),
    "CELL_P": ([("PG1", "L+"), ("U2", "X1.VIN+"), ("R7", "1"), ("R8", "1")] + power("CELL_P"), dict(battery=True)),
    "BAT_P": ([("U2", "X1.VIN-"), ("U1", "BAT")] + power("BAT_P"), dict(battery=True)),
    "BAT_N": ([("PG1", "L-"), ("U1", "BATN")], dict(battery=True)),
    "BATP_S": ([("R7", "2"), ("U1", "BATP")], dict(sense=True)),
    "GAUGE_S": ([("R8", "2"), ("U6", "JP2.VBAT")] + power("GAUGE_S"), dict(sense=True)),
    "TS": ([("RT1", "1"), ("U1", "TS")], dict()),
    "TS_RET": ([("RT1", "2"), ("U1", "TSN")], dict()),
    "VUSB": ([("PS1", "VBUS"), ("U1", "VIN1")], dict(force=True)),
    "VUSB_RET": ([("PS1", "GND"), ("U1", "PGND1")], dict(force=True)),
    "SOLAR_P": ([("PV1", "+"), ("U1", "VIN2")], dict(force=True)),
    "SOLAR_N": ([("PV1", "-"), ("U1", "PGND2")], dict(force=True)),
    "SYS": ([("U1", "SYS"), ("U7", "VIN")] + power("SYS"), dict(force=True)),
    "+3V3": ([("U7", "VOUT"), ("U2", "H.VIN"), ("U6", "H.VIN"), ("U5", "VIN"), ("U4", "H.VCC"), ("A1", "B2"),
              ("J3", "1"), ("R1", "1"), ("R2", "1"), ("R3", "1")]
             + [(f"F{k}", "1") for k in range(1, 5)] + bus("+3V3"),
             dict(vmax=3.4)),
    "GND": ([("U7", "GND"), ("U2", "H.GND"), ("U6", "H.GND"), ("U5", "GND"), ("U4", "H.GND"), ("U1", "SYSN"), ("U1", "J8.1"),
             ("A1", "B6"), ("A1", "D12"), ("J3", "5"), ("C1", "2"), ("C2", "2"), ("C3", "2"), ("XJ1", "GND"),
             ("J21", "2"), ("J21", "3"), ("J22", "3"), ("M1", "2"), ("M1", "3"), ("M2", "3"),
             ("D51", "2"), ("D52", "2"), ("D53", "2")]
            + [(f"J1{k}", "4") for k in range(1, 5)] + [(f"MOD{k}", "4") for k in range(1, 4)]
            + [(f"D{k}{s}", p) for k in range(1, 5) for s, p in (("1", "2"), ("3", "1"), ("5", "1"))]
            + [("U4", f"CH{k}.GND") for k in range(4)] + bus("GND"), dict()),
    "I2C_SCL": ([("A1", "D11"), ("U2", "H.SCL"), ("U6", "H.SCL"), ("U5", "SCL"), ("U4", "H.SCL"), ("U1", "J8.2"),
                 ("XJ1", "SCL")] + bus("I2C_SCL"), dict(vmax=3.6)),
    "I2C_SDA": ([("A1", "D10"), ("U2", "H.SDA"), ("U6", "H.SDA"), ("U5", "SDA"), ("U4", "H.SDA"), ("U1", "J8.3"),
                 ("XJ1", "SDA")] + bus("I2C_SDA"), dict(vmax=3.6)),
    "MUX_RST": ([("A1", "B8"), ("U4", "H.RST")] + bus("MUX_RST"), dict(vmax=3.6)),
    "CUPS_J": ([("J21", "4"), ("R1", "2"), ("C1", "1"), ("D51", "1"), ("R4", "1"), ("M1", "4")], dict(vmax=3.4)),
    "VANE_J": ([("J21", "5"), ("R2", "2"), ("C3", "1"), ("D52", "1"), ("R5", "1"), ("M1", "5")], dict(vmax=3.4)),
    "RAIN_J": ([("J22", "4"), ("R3", "2"), ("C2", "1"), ("D53", "1"), ("R6", "1"), ("M2", "4")], dict(vmax=3.4)),
    "CUPS": ([("A1", "D4"), ("R4", "2")] + bus("CUPS"), dict(vmax=3.4)),
    "VANE": ([("A1", "D8"), ("R5", "2")] + bus("VANE"), dict(vmax=3.4)),
    "RAIN": ([("A1", "D9"), ("R6", "2")] + bus("RAIN"), dict(vmax=3.4)),
    "BUS_SPARE": (bus("BUS_SPARE"), dict()),
    "SWDIO": ([("A1", "B3"), ("J3", "2")], dict()),
    "SWCLK": ([("A1", "B4"), ("J3", "3")], dict()),
    "NRST": ([("A1", "B5"), ("J3", "4")], dict()),
    "RF_MINI": ([("A1", "ANT"), ("AD1", "P")], dict()),
    "RF_RA": ([("AD1", "J"), ("CX1", "P")], dict()),
    "RF_WALL": ([("CX1", "J"), ("AE1", "RF")], dict()),
    **port_nets(),
}
# the card-local header pins (CARD_LOCAL): in their strip's net, with the socket contact each one mates
for _c, _pins in CARD_LOCAL.items():
    for _i, _n in _pins.items():
        NETS[_n][0].extend([(HEADERS[_c], str(_i)), (SOCKETS[_c], str(_i))])

NET_NAME = {
    "PACK_P": "pack + (at its plug)", "PACK_N": "pack - (at its plug)", "CELL_P": "battery + junction (backplane lines 21-22)",
    "BAT_P": "charger battery + (after the shunt)", "BAT_N": "battery - (charger ground)",
    "BATP_S": "charger battery sense (BATP)", "GAUGE_S": "fuel gauge cell sense (VBAT)",
    "TS": "battery temperature (TS)", "TS_RET": "thermistor return", "VUSB": "USB 5 V in", "VUSB_RET": "USB ground",
    "SOLAR_P": "solar +", "SOLAR_N": "solar -", "SYS": "charger system output (SYS)", "+3V3": "3.3 V supply",
    "GND": "ground", "I2C_SCL": "I2C clock (SCL)", "I2C_SDA": "I2C data (SDA)", "MUX_RST": "mux reset",
    "CUPS_J": "cups (wind speed) pulse at the jack", "VANE_J": "vane (wind direction) at the jack",
    "RAIN_J": "rain pulse at the jack", "CUPS": "cups (wind speed) pulse", "VANE": "vane (wind direction) voltage",
    "RAIN": "rain gauge pulse", "BUS_SPARE": "spare bus line (for the charger interrupt)",
    "SWDIO": "debug data (SWDIO)", "SWCLK": "debug clock (SWCLK)",
    "NRST": "MCU reset (NRST)", "RF_MINI": "antenna feed at the radio", "RF_RA": "antenna feed after the elbow",
    "RF_WALL": "antenna feed at the wall",
    **{f"P{k}_{s}": f"sensor port {k} {w}" for k in range(1, 5) for s, w in (
        ("3V3", "3.3 V"), ("JSDA", "data (SDA) at the jack"), ("JSCL", "clock (SCL) at the jack"),
        ("SDA", "data (SDA)"), ("SCL", "clock (SCL)"))},
}

# The MCU pins the firmware must agree with (firmware/board/wio-e5/board.toml)
MCU_FUNCTION = {"I2C_SDA": "PA15", "I2C_SCL": "PB15", "CUPS": "PC0", "VANE": "PB3", "RAIN": "PB4", "MUX_RST": "PB14"}

# RJ11 pin maps (design doc): jack ref -> {pin: net}; the jack side of each line
PIN_MAPS = {**{f"J1{k}": {"1": None, "2": f"P{k}_3V3", "3": f"P{k}_JSDA", "4": "GND", "5": f"P{k}_JSCL", "6": None}
               for k in range(1, 5)},
            "J21": {"1": None, "2": "GND", "3": "GND", "4": "CUPS_J", "5": "VANE_J", "6": None},
            "J22": {"1": None, "2": None, "3": "GND", "4": "RAIN_J", "5": None, "6": None}}

# Every outdoor line: (jack-side net, series resistor, clamp). checks.py rule 9 holds the design to it.
# Every outdoor line: jack-side net -> (series part, [clamp diodes]). checks.py rule 9 holds the design to it:
# an I2C line has a series resistor and a Schottky to its port supply and one from ground (low capacitance);
# a meter line (100 nF on it already) and a port supply have a 5.6 V zener to ground.
OUTDOOR_LINES = {**{f"P{k}_JSDA": (f"R{k}1", [f"D{k}2", f"D{k}3"]) for k in range(1, 5)},
                 **{f"P{k}_JSCL": (f"R{k}2", [f"D{k}4", f"D{k}5"]) for k in range(1, 5)},
                 **{f"P{k}_3V3": (f"F{k}", [f"D{k}1"]) for k in range(1, 5)},
                 "CUPS_J": ("R4", ["D51"]), "VANE_J": ("R5", ["D52"]), "RAIN_J": ("R6", ["D53"])}

ERC_WAIVERS = {
    "lib_symbol_issues": "symbols are embedded in the generated schematic, not taken from a KiCad library",
}
PWR_FLAGS = ["GND", "P1_3V3", "P2_3V3", "P3_3V3", "P4_3V3", "CELL_P", "BAT_P"]

# ------------------------------------------------------------------ what changed from r1, and why
# checks.py rule 10 compares r1-connections.json with this model: every part added or removed, and every pin
# common to both whose net partners changed, must be listed here (and nothing else).
R1_REMOVED = {
    "XS1": "the B3-B4 socket: the four cards now plug into a backplane",
    "XP1": "the B4 bus pins, same reason",
    "W11": "QT lead S1 gone: the mux on the backplane takes sensor port 1 on a cut QT cable in its channel 0",
    "W12": "QT lead S2 gone (cut QT cable in mux channel 1)", "W13": "QT lead S3 gone (cut QT cable in mux channel 2)",
    "W14": "QT lead S4 gone (cut QT cable in mux channel 3)",
}
R1_ADDED = {
    **{h: "right-angle bus header on each card's back edge" for h in ("XH1", "XH2", "XH3", "XH4")},
    **{s: "backplane socket for one card" for s in ("XB1", "XB2", "XB3", "XB4")},
    "XJ1": "charger I2C lead lands on the backplane",
    "R7": "100 ohm at the tap end of the charger sense lead (electrical review m11)",
    "R8": "100 ohm at the tap end of the gauge sense lead (m11; 100 not 1k: the gauge may draw its supply here)",
    "RT1": "pack thermistor on EVM J7, JP18 removed (electrical review M2)",
    "AD1": "SMA right-angle adapter so the coax turns up at the card edge",
    **{f"R{k}{s}": "series resistor on an outdoor line (M5)" for k in range(1, 5) for s in "12"},
    **{f"D{k}{s}": "clamp on an outdoor line (M5)" for k in range(1, 5) for s in "12345"},
    "R4": "1 kohm cups series (M5)", "R5": "1 kohm vane series (M5)", "R6": "1 kohm rain series (M5)",
    "C3": "vane filter capacitor (M5)", **{f"D5{i}": "clamp on a weather-meter line (M5)" for i in range(1, 4)},
}
# EVM pins r1 named by function, r2 by the terminal they are on
R1_RENAMED = {("U1", "GND"): ("U1", "SYSN"), ("U1", "SDA"): ("U1", "J8.3"), ("U1", "SCL"): ("U1", "J8.2")}
# pins in both revisions whose partners (among pins both revisions have) changed, or pins one revision lacks
R1_MOVED = [
    ([("PG1", "L+"), ("U2", "X1.VIN+"), ("U1", "BATP"), ("U6", "JP2.VBAT")],
     "charger and gauge sense now leave the battery + junction (backplane lines 21-22) through 100 ohm resistors R7, R8 (review m11)"),
    ([("U1", "J8.1"), ("U1", "TS"), ("U1", "TSN")],
     "EVM pins newly used: J8-1 ground for the I2C lead, J7 for the pack thermistor (review M2)"),
    ([(f"J1{k}", p) for k in range(1, 5) for p in "35"] + [(f"MOD{k}", p) for k in range(1, 4) for p in "35"]
     + [("U4", f"CH{k}.{s}") for k in range(4) for s in ("SDA", "SCL")],
     "each port's data and clock now pass a 100 ohm series resistor between the jack and the mux (review M5)"),
    ([("U4", f"CH{k}.V+") for k in range(4)],
     "the channel QT V+ (VCCIO) is no longer used: each channel's cut QT cable carries only SDA and SCL to the "
     "backplane, and the sensors take power from their own card ports"),
    ([("J21", "4"), ("J21", "5"), ("J22", "4"), ("M1", "4"), ("M1", "5"), ("M2", "4"), ("R1", "2"), ("R2", "2"),
      ("R3", "2"), ("C1", "1"), ("C2", "1"), ("A1", "D4"), ("A1", "D8"), ("A1", "D9")],
     "each meter line now passes a 1 kohm series resistor between the jack side (pull-up, filter, clamps) and "
     "the MCU pin (review M5)"),
    ([("A1", "ANT"), ("CX1", "P")], "the right-angle SMA adapter AD1 now sits between the radio and the coax"),
]
