"""TX protoboard stack r1: the electrical source of truth.

Every part, pin and net of the stack in docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md,
with the Wio-E5 mini as the MCU (issue #35). kicad_gen.py draws the schematic from this file, checks.py
checks it against KiCad's netlist, and ../layout/ places every pin of it on the boards' holes.

Pin tuple: (number, name, electrical type, contact). Contact is how a conductor meets the pin:
  header   a 0.1 in pin soldered into a SolderFul hole (so it joins that hole's row strip)
  socket   a Sullins PPPC081LFBN-RC socket contact (the B3-B4 bus)
  solder   a lead soldered straight to a pad or a wire end (no strip, no connector)
  jst      a JST PH mating (the pack's own plug)       qt   a STEMMA QT (JST SH) mating
  rj11     an RJ11 6P6C mating                         usb  a USB-C mating
  sma      an SMA mating                               evm  a BQ25798EVM terminal (type per SLUUCB5, to read)
  nc       left unconnected (a pin that sits in a hole but joins no net is still "nc" here)
"""

PAS, PIN, POUT, IN, OC, BI, OUT = ("passive", "power_in", "power_out", "input", "open_collector",
                                   "bidirectional", "output")


def qt(prefix, contact="qt"):
    return [(f"{prefix}.GND", "GND", PAS, contact), (f"{prefix}.V+", "V+", PIN, contact),
            (f"{prefix}.SDA", "SDA", BI, contact), (f"{prefix}.SCL", "SCL", BI, contact)]


def bob(ref, value, used, board):
    """BOB-14021 with an 87180-066LF jack. Pins 1-6 are the header; jack contact n is header pin n."""
    return dict(ref=ref, value=value, part="SparkFun BOB-14021 + Amphenol 87180-066LF", block=board,
                pins=[(str(i), f"P{i}", PAS, "header" if i in used else "nc") for i in range(1, 7)])


def module(ref, value, sensor, addr):
    """An outdoor I2C module end: sensor breakout + 24LC32-class ID EEPROM (0x50) on one RJ11 cable."""
    return dict(ref=ref, value=value, part=f"{sensor} + 24LC32 EEPROM, Perma-Proto 1608", block="outdoor",
                pins=[("2", "3V3", PIN, "rj11"), ("3", "SDA", BI, "rj11"), ("4", "GND", PAS, "rj11"),
                      ("5", "SCL", BI, "rj11")], i2c=[0x50, addr], pullups_k=10.0)


def r(ref, value, part, block):
    return dict(ref=ref, value=value, part=part, block=block, pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")])


# Wio-E5 mini header pads (Seeed LoRa-E5 mini v1.0.brd, J1): B row and D row, pad -> MCU pin
MINI_B = ["5V", "3V3", "PA13", "PA14", "RST", "GND", "PA10", "PB14", "PB9", "PB13", "PB10", "PA9"]
MINI_D = ["PA2", "PA3", "PC1", "PC0", "PA0", "PB6", "PB7", "PB3", "PB4", "PA15", "PB15", "GND"]
MINI_USED = {"B2", "B3", "B4", "B5", "B6", "B8", "D4", "D8", "D9", "D10", "D11", "D12"}


def mini_pins():
    out = []
    for row, names in (("B", MINI_B), ("D", MINI_D)):
        for i, n in enumerate(names, 1):
            num = f"{row}{i}"
            et = PIN if n == "3V3" else PAS if n in ("GND", "5V") else BI
            out.append((num, n, et, "header" if num in MINI_USED else "nc"))
    return out + [("ANT", "ANT", PAS, "sma")]


PARTS = [
    # ------------------------------------------------------------ off the stack: sources, pack, EVM
    dict(ref="PS1", value="USB-C adapter 5V", part="wall adapter, >= 2 A", block="power",
         pins=[("VBUS", "VBUS", POUT, "usb"), ("GND", "GND", PAS, "usb")]),
    dict(ref="PV1", value="Solar P110", part="Voltaic P110 6 V 10 W (barrel cut at the gland)", block="power",
         pins=[("+", "+", POUT, "solder"), ("-", "-", PAS, "solder")]),
    dict(ref="BT1", value="1S3P 6600mAh", part="Adafruit #353 (own protection board)", block="power",
         pins=[("+", "+", POUT, "jst"), ("-", "-", PAS, "jst")]),
    dict(ref="PG1", value="JST PH pigtail", part="JST PH 2-pin socket with leads (mates the pack, kept unmodified)",
         block="power", pins=[("M+", "M+", PAS, "jst"), ("M-", "M-", PAS, "jst"), ("L+", "L+", PAS, "solder"),
                              ("L-", "L-", PAS, "solder")], ties=[["M+", "L+"], ["M-", "L-"]]),
    dict(ref="U1", value="BQ25798EVM", part="TI BQ25798EVM (SLUUCB5); jumpers and J numbers to read from the guide",
         block="power",
         pins=[("VIN1", "VIN1 USB", PIN, "evm"), ("VIN2", "VIN2 SOLAR", PIN, "evm"), ("PGND1", "PGND1", PAS, "evm"),
               ("PGND2", "PGND2", PAS, "evm"), ("BAT", "BAT", PAS, "evm"), ("BATN", "BAT-", PAS, "evm"),
               ("BATP", "SNS_BATP", IN, "evm"), ("SYS", "SYS", POUT, "evm"), ("GND", "GND", PAS, "evm"),
               ("SDA", "SDA", BI, "evm"), ("SCL", "SCL", BI, "evm"), ("INT", "INT", OC, "nc")],
         ties=[["PGND1", "PGND2", "BATN", "GND"]], i2c=[0x6B],
         note="EVM I2C pull-ups disabled (they may sit on a rail above 3.3 V); INT not wired yet"),
    # ------------------------------------------------------------ B4 POWER
    dict(ref="U2", value="INA228 0x40", part="Adafruit #5832", block="B4",
         pins=[("H.VIN", "VIN", PIN, "header"), ("H.GND", "GND", PAS, "header"), ("H.SCL", "SCL", BI, "header"),
               ("H.SDA", "SDA", BI, "header"), ("H.VBUS", "VBUS", PAS, "nc"), ("H.VIN-", "VIN-", PAS, "nc"),
               ("H.VIN+", "VIN+", PAS, "nc"), ("H.ALRT", "ALRT", OC, "nc"),
               ("X1.VIN+", "VIN+", PAS, "solder"), ("X1.VBUS", "VBUS", PAS, "nc"), ("X1.VIN-", "VIN-", PAS, "solder")]
         + qt("QT1", "nc") + qt("QT2", "nc"),
         ties=[["H.VIN+", "X1.VIN+", "X1.VBUS", "H.VBUS"], ["H.VIN-", "X1.VIN-"], ["H.VIN", "QT1.V+", "QT2.V+"],
               ["H.GND", "QT1.GND", "QT2.GND"], ["H.SDA", "QT1.SDA", "QT2.SDA"], ["H.SCL", "QT1.SCL", "QT2.SCL"]],
         i2c=[0x40], pullups_k=10.0, removed=["H.VBUS", "H.VIN-", "H.VIN+"],
         note="battery shunt in the pack + leg; X1 pads take soldered leads (no terminal block); header pins "
              "5-7 (VBUS, VIN-, VIN+) pulled from the strip so no battery node reaches a breadboard strip; SJ1 closed"),
    dict(ref="U6", value="MAX17048 0x36", part="Adafruit #5580", block="B4",
         pins=[("H.VIN", "VIN", PIN, "header"), ("H.GND", "GND", PAS, "header"), ("H.SCL", "SCL", BI, "header"),
               ("H.SDA", "SDA", BI, "header"), ("H.INT", "INT", OC, "nc"), ("H.QST", "QST", IN, "nc"),
               ("JP2.VBAT", "VBAT", PAS, "solder"), ("JP2.GND", "GND", PAS, "nc"),
               ("BAT1.+", "BAT+", PAS, "nc"), ("BAT2.+", "BAT+", PAS, "nc")] + qt("QT1", "nc") + qt("QT2", "nc"),
         ties=[["JP2.VBAT", "BAT1.+", "BAT2.+"], ["H.GND", "JP2.GND", "QT1.GND", "QT2.GND"],
               ["H.VIN", "QT1.V+", "QT2.V+"], ["H.SDA", "QT1.SDA", "QT2.SDA"], ["H.SCL", "QT1.SCL", "QT2.SCL"]],
         i2c=[0x36], pullups_k=10.0, note="cell sense on its own lead from the pack tap to JP2 VBAT"),
    dict(ref="U7", value="S7V8F3 3.3V", part="Pololu #2122", block="B4",
         pins=[("VOUT", "VOUT", POUT, "header"), ("GND", "GND", PAS, "header"), ("VIN", "VIN", PIN, "header"),
               ("SHDN", "SHDN", IN, "nc")], note="SHDN open: enabled"),
    dict(ref="XP1", value="bus header 1x8", part="0.1 in male header, plastic slid off (B4 underside)", block="B4",
         pins=[(str(i), n, PAS, "header") for i, n in enumerate(
             ["3V3", "GND", "SCL", "SDA", "MUX_RST", "CUPS", "VANE", "RAIN"], 1)]),
    # ------------------------------------------------------------ B3 CORE
    dict(ref="A1", value="Wio-E5 mini TX", part="Seeed Wio-E5 mini (113990939), STM32WLE5JC", block="B3",
         pins=mini_pins(), i2c=[], pullups_k=4.7,
         note="4.7 kohm I2C pull-ups R15/R16 on board; 3V3 fed in on B2 (the AP2112 LDO back-fed); USB-C = console"),
    dict(ref="J3", value="SWD 1x5 right angle", part="0.1 in right-angle male header", block="B3",
         pins=[("1", "3V3", PAS, "header"), ("2", "SWDIO", PAS, "header"), ("3", "SWCLK", PAS, "header"),
               ("4", "NRST", PAS, "header"), ("5", "GND", PAS, "header")],
         note="the NUCLEO ST-LINK's SWD leads (Adafruit 266 jumpers)"),
    dict(ref="U5", value="SHTC3 0x70", part="Adafruit #4636", block="B3",
         pins=[("VIN", "VIN", PIN, "header"), ("3V", "3V out", POUT, "nc"), ("GND", "GND", PAS, "header"),
               ("SCL", "SCL", BI, "header"), ("SDA", "SDA", BI, "header")], i2c=[0x70], pullups_k=10.0),
    dict(ref="XS1", value="bus socket 1x8", part="Sullins PPPC081LFBN-RC", block="B3",
         pins=[(str(i), n, PAS, "socket") for i, n in enumerate(
             ["3V3", "GND", "SCL", "SDA", "MUX_RST", "CUPS", "VANE", "RAIN"], 1)]),
    dict(ref="CX1", value="SMA cable 6in", part="Amphenol 135110-01-06.00 (RG-316, bulkhead jack)", block="B3",
         pins=[("P", "plug", PAS, "sma"), ("J", "bulkhead", PAS, "sma")], ties=[["P", "J"]]),
    dict(ref="AE1", value="ANT-916-CW-HWR", part="Linx ANT-916-CW-HWR-SMA (outside, vertical)", block="B3",
         pins=[("RF", "RF", PAS, "sma")]),
    # ------------------------------------------------------------ B2 METERS
    bob("J21", "RJ11 WIND", {2, 3, 4, 5}, "B2"),
    bob("J22", "RJ11 RAIN", {3, 4}, "B2"),
    r("R1", "10k", "MFR-25 10K (cups pull-up)", "B2"),
    r("R2", "10k", "MFR-25 10K (vane pull-up)", "B2"),
    r("R3", "10k", "MFR-25 10K (rain pull-up)", "B2"),
    r("C1", "100nF", "KEMET C320C104K5R5TA (cups)", "B2"),
    r("C2", "100nF", "KEMET C320C104K5R5TA (rain)", "B2"),
    dict(ref="U4", value="PCA9548 0x71", part="Adafruit #5626 (A0 bridged)", block="B2",
         pins=[("H.VCC", "VCC", PIN, "solder"), ("H.GND", "GND", PAS, "solder"), ("H.SCL", "SCL", BI, "solder"),
               ("H.SDA", "SDA", BI, "solder"), ("H.RST", "RESET", IN, "solder")]
         + qt("UP", "nc") + sum((qt(f"CH{k}") for k in range(4)), []),
         ties=[["H.GND", "UP.GND"] + [f"CH{k}.GND" for k in range(4)], ["H.VCC", "UP.V+"],
               ["H.SDA", "UP.SDA"], ["H.SCL", "UP.SCL"], [f"CH{k}.V+" for k in range(4)]],
         i2c=[0x71], pullups_k=10.0,
         note="foam-mounted (its 5-pin header cannot sit on one strip column without shorting); "
              "five leads soldered to the header pads; channel QT V+ is VCCIO and stays unused"),
    # ------------------------------------------------------------ B1 PORTS
    *[bob(f"J1{k}", f"RJ11 S{k}", {2, 3, 4, 5}, "B1") for k in range(1, 5)],
    *[dict(r(f"F{k}", "MF-R010", "Bourns MF-R010 100 mA PTC", "B1"), note=f"port S{k} 3V3") for k in range(1, 5)],
    *[dict(ref=f"W1{k}", value=f"QT lead S{k}", part="Adafruit #4209 QT to male pins (V+ pin folded back, insulated)",
           block="B1", pins=qt("Q") + [("H.GND", "GND", PAS, "header"), ("H.V+", "V+", PAS, "nc"),
                                        ("H.SDA", "SDA", BI, "header"), ("H.SCL", "SCL", BI, "header")],
           ties=[["Q.GND", "H.GND"], ["Q.V+", "H.V+"], ["Q.SDA", "H.SDA"], ["Q.SCL", "H.SCL"]])
      for k in range(1, 5)],
    # ------------------------------------------------------------ outdoors
    module("MOD1", "TH module", "SHT45 #6174", 0x44),
    module("MOD2", "Baro module", "BMP581 #6407", 0x47),
    module("MOD3", "UV module", "LTR390 #4831", 0x53),
    dict(ref="M1", value="Wind (vane+cups)", part="SparkFun SEN-15901", block="outdoor",
         pins=[("2", "VANE_RET", PAS, "rj11"), ("3", "CUPS_RET", PAS, "rj11"), ("4", "CUPS", PAS, "rj11"),
               ("5", "VANE", PAS, "rj11")]),
    dict(ref="M2", value="Rain gauge", part="SparkFun SEN-15901", block="outdoor",
         pins=[("3", "RAIN_RET", PAS, "rj11"), ("4", "RAIN", PAS, "rj11")]),
]

BUS = ["3V3", "GND", "SCL", "SDA", "MUX_RST", "CUPS", "VANE", "RAIN"]   # XS1/XP1 pin 1..8
BUS_NET = {"3V3": "+3V3", "GND": "GND", "SCL": "I2C_SCL", "SDA": "I2C_SDA", "MUX_RST": "MUX_RST",
           "CUPS": "CUPS", "VANE": "VANE", "RAIN": "RAIN"}


def bus(sig):
    i = str(BUS.index(sig) + 1)
    return [("XS1", i), ("XP1", i)]


PORTS = {1: ("J11", "MOD1", 0), 2: ("J12", "MOD2", 1), 3: ("J13", "MOD3", 2), 4: ("J14", None, 3)}


def port_nets():
    out = {}
    for k, (jack, mod, ch) in PORTS.items():
        m = [] if mod is None else [mod]
        out[f"P{k}_3V3"] = ([(f"F{k}", "2"), (jack, "2")] + [(x, "2") for x in m], dict(vmax=3.4))
        out[f"P{k}_SDA"] = ([("U4", f"CH{ch}.SDA"), (f"W1{k}", "Q.SDA"), (f"W1{k}", "H.SDA"), (jack, "3")]
                            + [(x, "3") for x in m], dict(vmax=3.6))
        out[f"P{k}_SCL"] = ([("U4", f"CH{ch}.SCL"), (f"W1{k}", "Q.SCL"), (f"W1{k}", "H.SCL"), (jack, "5")]
                            + [(x, "5") for x in m], dict(vmax=3.6))
    return out


# battery: carries the cell's charge or discharge current (the F1 rule applies). force: other power current.
NETS = {
    "PACK_P": ([("BT1", "+"), ("PG1", "M+")], dict(battery=True)),
    "PACK_N": ([("BT1", "-"), ("PG1", "M-")], dict(battery=True)),
    "CELL_P": ([("PG1", "L+"), ("U2", "X1.VIN+"), ("U1", "BATP"), ("U6", "JP2.VBAT")],
               dict(battery=True, sense={("U1", "BATP"), ("U6", "JP2.VBAT")})),
    "BAT_P": ([("U2", "X1.VIN-"), ("U1", "BAT")], dict(battery=True)),
    "BAT_N": ([("PG1", "L-"), ("U1", "BATN")], dict(battery=True)),
    "VUSB": ([("PS1", "VBUS"), ("U1", "VIN1")], dict(force=True)),
    "VUSB_RET": ([("PS1", "GND"), ("U1", "PGND1")], dict(force=True)),
    "SOLAR_P": ([("PV1", "+"), ("U1", "VIN2")], dict(force=True)),
    "SOLAR_N": ([("PV1", "-"), ("U1", "PGND2")], dict(force=True)),
    "SYS": ([("U1", "SYS"), ("U7", "VIN")], dict(force=True)),
    "+3V3": ([("U7", "VOUT"), ("U2", "H.VIN"), ("U6", "H.VIN"), ("U5", "VIN"), ("U4", "H.VCC"), ("A1", "B2"),
              ("J3", "1"), ("R1", "1"), ("R2", "1"), ("R3", "1")] + [(f"F{k}", "1") for k in range(1, 5)] + bus("3V3"),
             dict(vmax=3.4)),
    "GND": ([("U7", "GND"), ("U2", "H.GND"), ("U6", "H.GND"), ("U5", "GND"), ("U4", "H.GND"), ("U1", "GND"),
             ("A1", "B6"), ("A1", "D12"), ("J3", "5"), ("C1", "2"), ("C2", "2"),
             ("J21", "2"), ("J21", "3"), ("J22", "3"), ("M1", "2"), ("M1", "3"), ("M2", "3")]
            + [(f"J1{k}", "4") for k in range(1, 5)] + [(f"MOD{k}", "4") for k in range(1, 4)]
            + [(f"W1{k}", s) for k in range(1, 5) for s in ("Q.GND", "H.GND")]
            + [("U4", f"CH{k}.GND") for k in range(4)] + bus("GND"), dict()),
    "I2C_SCL": ([("A1", "D11"), ("U2", "H.SCL"), ("U6", "H.SCL"), ("U5", "SCL"), ("U4", "H.SCL"), ("U1", "SCL")]
                + bus("SCL"), dict(vmax=3.6)),
    "I2C_SDA": ([("A1", "D10"), ("U2", "H.SDA"), ("U6", "H.SDA"), ("U5", "SDA"), ("U4", "H.SDA"), ("U1", "SDA")]
                + bus("SDA"), dict(vmax=3.6)),
    "MUX_RST": ([("A1", "B8"), ("U4", "H.RST")] + bus("MUX_RST"), dict(vmax=3.6)),
    "CUPS": ([("A1", "D4"), ("J21", "4"), ("R1", "2"), ("C1", "1"), ("M1", "4")] + bus("CUPS"), dict(vmax=3.4)),
    "VANE": ([("A1", "D8"), ("J21", "5"), ("R2", "2"), ("M1", "5")] + bus("VANE"), dict(vmax=3.4)),
    "RAIN": ([("A1", "D9"), ("J22", "4"), ("R3", "2"), ("C2", "1"), ("M2", "4")] + bus("RAIN"), dict(vmax=3.4)),
    "VCCIO": ([("U4", f"CH{k}.V+") for k in range(4)] + [(f"W1{k}", "Q.V+") for k in range(1, 5)], dict()),
    "SWDIO": ([("A1", "B3"), ("J3", "2")], dict()),
    "SWCLK": ([("A1", "B4"), ("J3", "3")], dict()),
    "NRST": ([("A1", "B5"), ("J3", "4")], dict()),
    "RF_MINI": ([("A1", "ANT"), ("CX1", "P")], dict()),
    "RF_WALL": ([("CX1", "J"), ("AE1", "RF")], dict()),
    **port_nets(),
}

# The MCU pins the firmware must agree with (firmware/board/wio-e5/Core/Inc/board_pins.h)
MCU_FUNCTION = {"I2C_SDA": "PA15", "I2C_SCL": "PB15", "CUPS": "PC0", "VANE": "PB3", "RAIN": "PB4", "MUX_RST": "PB14"}

# RJ11 pin maps (design doc): jack ref -> {pin: role}; roles resolved to nets by checks.py
PIN_MAPS = {**{f"J1{k}": {"1": None, "2": f"P{k}_3V3", "3": f"P{k}_SDA", "4": "GND", "5": f"P{k}_SCL", "6": None}
               for k in range(1, 5)},
            "J21": {"1": None, "2": "GND", "3": "GND", "4": "CUPS", "5": "VANE", "6": None},
            "J22": {"1": None, "2": None, "3": "GND", "4": "RAIN", "5": None, "6": None}}

ERC_WAIVERS = {
    "lib_symbol_issues": "symbols are embedded in the generated schematic, not taken from a KiCad library",
}
PWR_FLAGS = ["GND", "P1_3V3", "P2_3V3", "P3_3V3", "P4_3V3", "CELL_P", "BAT_P", "VCCIO"]
