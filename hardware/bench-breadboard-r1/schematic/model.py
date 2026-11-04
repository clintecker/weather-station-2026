"""Breadboard bench r1: the electrical source of truth.

Every part, every pin and every net of the bench, as approved in ../design.md section 2. The KiCad
schematic is generated from this file (kicad_gen.py) and the rule checks (checks.py) read both this
model and KiCad's netlist export, so the drawing can never drift from the model unnoticed.

Pin tuple: (number, name, electrical type, contact). Pin numbers are function names, not header
positions: header order belongs to the layout step. Contact says how a conductor meets the pin, which
is what the force-current rule checks:
  screw   INA228 X1 terminal, #368/#369 terminals     wago    a WAGO 222 lever
  jst     a JST PH mating (pack, BATT, SYSOUT, gauge)  solder  a soldered lead (USB-C breakouts)
  usb     a USB-C plug/receptacle mating               barrel  a 2.1 mm barrel mating
  qt      a STEMMA QT (JST SH) mating                  rj11    an RJ11 mating
  header  a 2.54 mm header pin, breadboard strip or Dupont contact
  nc      left unconnected (KiCad no-connect flag)
"""

# KiCad pin electrical types used here
PAS, PIN, POUT, IN, OC, BI = "passive", "power_in", "power_out", "input", "open_collector", "bidirectional"


def qt(prefix, contact="qt"):
    """One STEMMA QT connector: GND, V+, SDA, SCL."""
    return [(f"{prefix}.GND", "GND", PIN, contact), (f"{prefix}.V+", "V+", PIN, contact),
            (f"{prefix}.SDA", "SDA", BI, contact), (f"{prefix}.SCL", "SCL", BI, contact)]


def ina228(ref, addr, note, sj1):
    """sj1 'closed' bridges VBUS to VIN+ on the board (decision D1), so the VBUS terminal stays empty."""
    pins = [(f"H.{n}", n, t, "nc") for n, t in
            (("VIN", PIN), ("GND", PAS), ("SCL", BI), ("SDA", BI), ("ALRT", OC), ("VBUS", PAS), ("VIN+", PAS), ("VIN-", PAS))]
    pins += [("X1.VIN+", "VIN+", PAS, "screw"), ("X1.VBUS", "VBUS", PAS, "nc" if sj1 == "closed" else "screw"),
             ("X1.VIN-", "VIN-", PAS, "screw")]
    pins += qt("QT1") + qt("QT2")
    ties = [["H.VIN", "QT1.V+", "QT2.V+"], ["H.GND", "QT1.GND", "QT2.GND"], ["H.SDA", "QT1.SDA", "QT2.SDA"],
            ["H.SCL", "QT1.SCL", "QT2.SCL"], ["H.VIN+", "X1.VIN+"], ["H.VBUS", "X1.VBUS"], ["H.VIN-", "X1.VIN-"]]
    if sj1 == "closed":
        ties.append(["X1.VIN+", "X1.VBUS"])
    return dict(ref=ref, value=f"INA228 {addr:#04x}", part="Adafruit #5832", block="power", pins=pins, ties=ties,
                i2c=[addr], pullups_k=10.0, note=note,
                vlimit={"X1.VIN+": 85, "X1.VIN-": 85, "X1.VBUS": 85, "QT1.SDA": 6, "QT1.SCL": 6},
                shunt_mohm=15, sj1=sj1)


PARTS = [
    # ---------------------------------------------------------------- sources and the pack
    dict(ref="PS1", value="USB-C adapter 5V", part="floating wall adapter, >= 2 A", block="sources",
         pins=[("VBUS", "VBUS", POUT, "usb"), ("GND", "GND", PAS, "usb")], vmax={"VBUS": 5.5}),
    dict(ref="PV1", value="Solar P110", part="Voltaic P110 6 V 10 W", block="sources",
         pins=[("+", "+", POUT, "barrel"), ("-", "-", PAS, "barrel")], vmax={"+": 8.7}),
    dict(ref="BT1", value="1S3P 6600mAh", part="Adafruit #353", block="pack",
         pins=[("+", "+", POUT, "jst"), ("-", "-", PAS, "jst")], vmax={"+": 4.2}),
    dict(ref="RT1", value="NTC 10k B3950", part="Adafruit #372", block="pack",
         pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    # ---------------------------------------------------------------- source metering breakouts
    dict(ref="J3", value="USB-C female", part="Adafruit #4090", block="usbc",
         pins=[("VBUS", "VBUS", PAS, "solder"), ("GND", "GND", PAS, "solder"),
               ("CC1", "CC1", PAS, "nc"), ("CC2", "CC2", PAS, "nc"), ("D+", "D+", PAS, "nc"), ("D-", "D-", PAS, "nc"),
               ("IN.VBUS", "IN.VBUS", PAS, "usb"), ("IN.GND", "IN.GND", PAS, "usb")],
         ties=[["VBUS", "IN.VBUS"], ["GND", "IN.GND"]],
         note="5.1k Rd on CC1/CC2 to GND on board: the adapter sees a sink and turns VBUS on"),
    dict(ref="P1", value="USB-C male plug", part="Adafruit #5978", block="usbc",
         pins=[("VBUS", "VBUS", PAS, "solder"), ("GND", "GND", PAS, "solder"),
               ("CC", "CC", PAS, "nc"), ("D+", "D+", PAS, "nc"), ("D-", "D-", PAS, "nc"),
               ("OUT.VBUS", "OUT.VBUS", PAS, "usb"), ("OUT.GND", "OUT.GND", PAS, "usb")],
         ties=[["VBUS", "OUT.VBUS"], ["GND", "OUT.GND"]], note="plugs into the #4755 USB-C; CC and data open"),
    dict(ref="J4", value="2.1mm jack-screw", part="Adafruit #368", block="solar",
         pins=[("+", "+", PAS, "screw"), ("-", "-", PAS, "screw"), ("IN.+", "IN.+", PAS, "barrel"), ("IN.-", "IN.-", PAS, "barrel")],
         ties=[["+", "IN.+"], ["-", "IN.-"]]),
    dict(ref="P2", value="2.1mm plug-screw", part="Adafruit #369", block="solar",
         pins=[("+", "+", PAS, "screw"), ("-", "-", PAS, "screw"), ("OUT.+", "OUT.+", PAS, "barrel"), ("OUT.-", "OUT.-", PAS, "barrel")],
         ties=[["+", "OUT.+"], ["-", "OUT.-"]]),
    # ---------------------------------------------------------------- charger
    dict(ref="U1", value="bq24074 charger", part="Adafruit #4755", block="charger",
         pins=[("USB.VBUS", "USB.VBUS", PIN, "usb"), ("USB.GND", "USB.GND", PAS, "usb"),
               ("DC.+", "DC.+", PIN, "barrel"), ("DC.-", "DC.-", PAS, "barrel"),
               ("BATT.+", "BATT.+", PAS, "jst"), ("BATT.-", "BATT.-", PAS, "jst"),
               ("SYS.+", "SYS.+", POUT, "jst"), ("SYS.-", "SYS.-", PAS, "nc"),
               ("H.GND1", "GND", PAS, "header"), ("H.LIPO", "LIPO", PAS, "nc"), ("H.GND2", "GND", PAS, "nc"),
               ("H.OUT", "OUT", PAS, "nc"), ("H.CHG", "CHG", OC, "header"), ("H.PGOOD", "PGOOD", OC, "header"),
               ("H.CE", "CE", IN, "nc"), ("H.ISET", "ISET", PAS, "header"), ("H.THERM", "THERM", PAS, "header"),
               ("H.GND3", "GND", PAS, "nc"), ("H.VBUS", "VBUS", PAS, "header")],
         vlimit={"USB.VBUS": 10.2, "DC.+": 10.2, "H.VBUS": 10.2, "BATT.+": 5.0, "H.CHG": 7.0, "H.PGOOD": 7.0},
         ties=[["USB.GND", "DC.-", "BATT.-", "SYS.-", "H.GND1", "H.GND2", "H.GND3"],
               ["BATT.+", "H.LIPO"], ["SYS.+", "H.OUT"]],
         note="inputs reach IN through Schottky D2 (USB) and D4 (DC); CE has 10k to GND on board; "
              "LIPO/OUT/GND header pins are zero-current test points, not wired"),
    # ---------------------------------------------------------------- power metering
    ina228("U2", 0x40, "battery: shunt in the pack + lead; VBUS = CELL+ through SJ1 (host cross-check)", "closed"),
    ina228("U3", 0x41, "load: OUT -> LOAD; SJ1 open, VBUS sense lead to LOAD; A0 jumper to VS", "open"),
    ina228("U4", 0x45, "solar: before the #4755 DC jack; VBUS = SOLAR_IN through SJ1; A0, A1 to VS", "closed"),
    ina228("U5", 0x48, "USB-C: before the #4755 USB-C; VBUS = USB_IN through SJ1; A1 wired to SDA (rework)", "closed"),
    dict(ref="U6", value="MAX17048 0x36", part="Adafruit #5580", block="power",
         pins=[(f"H.{n}", n, t, "nc") for n, t in (("VIN", PIN), ("GND", PAS), ("SCL", BI), ("SDA", BI), ("INT", OC), ("QST", IN))]
         + [("BAT1.+", "BAT+", PAS, "jst"), ("BAT1.-", "BAT-", PAS, "nc"), ("BAT2.+", "BAT+", PAS, "nc"), ("BAT2.-", "BAT-", PAS, "nc")]
         + qt("QT1") + qt("QT2", "nc"),
         ties=[["H.VIN", "QT1.V+", "QT2.V+"], ["H.GND", "QT1.GND", "QT2.GND", "BAT1.-", "BAT2.-"],
               ["H.SDA", "QT1.SDA", "QT2.SDA"], ["H.SCL", "QT1.SCL", "QT2.SCL"], ["BAT1.+", "BAT2.+"]],
         i2c=[0x36], pullups_k=10.0, vlimit={"BAT1.+": 4.5},
         note="BAT- is the board GND (pigtail black lead insulated); the chip runs from BAT+ (SJ2 default)"),
    # ---------------------------------------------------------------- force-current splices and loads
    dict(ref="WG1", value="WAGO CELL+", part="WAGO 222-413", block="power",
         pins=[(str(i), f"L{i}", PAS, "wago") for i in range(1, 4)], ties=[[str(i) for i in range(1, 4)]]),
    dict(ref="WG2", value="WAGO STAR", part="WAGO 222-415", block="power",
         pins=[(str(i), f"L{i}", PAS, "wago") for i in range(1, 6)], ties=[[str(i) for i in range(1, 6)]]),
    dict(ref="WG3", value="WAGO LOAD", part="WAGO 222-415", block="power",
         pins=[(str(i), f"L{i}", PAS, "wago") for i in range(1, 6)], ties=[[str(i) for i in range(1, 6)]]),
    dict(ref="R9", value="100R 50W", part="aluminium-housed 50 W 100 ohm 5% (marked 50W100RJ, in hand 2026-11-04)", block="power",
         pins=[("1", "1", PAS, "wago"), ("2", "2", PAS, "wago")], mode="A", note="test load, mode A only"),
    dict(ref="W1", value="GND tie", part="22 AWG solid <= 100 mm", block="power",
         pins=[("1", "STAR", PAS, "wago"), ("2", "LOGIC", PAS, "header")], tie=True,
         note="the one conductor between power ground and logic ground"),
    dict(ref="U7", value="S7V8F3 3.3V", part="Pololu #2122", block="power",
         pins=[("VIN", "VIN", PIN, "header"), ("GND", "GND", PAS, "header"), ("VOUT", "VOUT", POUT, "header"),
               ("SHDN", "SHDN", IN, "nc")],
         vlimit={"VIN": 11.8},
         note="SHDN left open (100k pull-up to VIN: enabled); no reverse-polarity protection"),
    dict(ref="JP1", value="BATTERY link", part="2-pin header + shunt", block="power",
         pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")], mode="B",
         note="fitted only in mode B (TX USB unplugged)"),
    # ---------------------------------------------------------------- charger signal networks
    dict(ref="R4", value="10k 1%", part="MFR-25 10K", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R5", value="10k 1%", part="MFR-25 10K", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R6", value="10k 1%", part="MFR-25 10K", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R7", value="10k 1%", part="MFR-25 10K", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R8", value="1M 1%", part="MFR-25 1M", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="C4", value="100nF", part="KEMET C320C104K5R5TA", block="signals", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    # ---------------------------------------------------------------- weather meter
    dict(ref="M1", value="Wind (vane+cups)", part="SparkFun SEN-15901", block="meter",
         pins=[("2", "VANE_RET", PAS, "rj11"), ("3", "CUPS_RET", PAS, "rj11"), ("4", "CUPS", PAS, "rj11"), ("5", "VANE", PAS, "rj11")]),
    dict(ref="M2", value="Rain gauge", part="SparkFun SEN-15901", block="meter",
         pins=[("3", "RAIN_RET", PAS, "rj11"), ("4", "RAIN", PAS, "rj11")]),
    dict(ref="J1", value="RJ11 wind", part="SparkFun BOB-14021", block="meter",
         pins=[(str(i), n, PAS, "nc" if i in (1, 6) else "header") for i, n in
               ((1, "1"), (2, "B"), (3, "R"), (4, "G"), (5, "Y"), (6, "6"))]),
    dict(ref="J2", value="RJ11 rain", part="SparkFun BOB-14021", block="meter",
         pins=[(str(i), n, PAS, "nc" if i in (1, 2, 5, 6) else "header") for i, n in
               ((1, "1"), (2, "B"), (3, "R"), (4, "G"), (5, "Y"), (6, "6"))]),
    dict(ref="R1", value="10k", part="MFR-25 10K", block="meter", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R2", value="10k", part="MFR-25 10K", block="meter", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="R3", value="10k", part="MFR-25 10K", block="meter", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="C2", value="100nF", part="KEMET C320C104K5R5TA", block="meter", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    dict(ref="C3", value="100nF", part="KEMET C320C104K5R5TA", block="meter", pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")]),
    # ---------------------------------------------------------------- I2C
    dict(ref="W2", value="QT-header (sensors)", part="Adafruit #4209", block="i2c",
         pins=qt("Q") + [("H.GND", "GND", PAS, "header"), ("H.V+", "V+", PAS, "header"),
                         ("H.SDA", "SDA", BI, "header"), ("H.SCL", "SCL", BI, "header")],
         ties=[["Q.GND", "H.GND"], ["Q.V+", "H.V+"], ["Q.SDA", "H.SDA"], ["Q.SCL", "H.SCL"]]),
    dict(ref="W3", value="QT-header (power)", part="Adafruit #4209", block="i2c",
         pins=qt("Q") + [("H.GND", "GND", PAS, "header"), ("H.V+", "V+", PAS, "header"),
                         ("H.SDA", "SDA", BI, "header"), ("H.SCL", "SCL", BI, "header")],
         ties=[["Q.GND", "H.GND"], ["Q.V+", "H.V+"], ["Q.SDA", "H.SDA"], ["Q.SCL", "H.SCL"]]),
    dict(ref="U8", value="QT hub 5-port", part="Adafruit #5625", block="i2c",
         pins=sum((qt(f"P{i}") for i in range(1, 6)), []),
         ties=[[f"P{i}.{s}" for i in range(1, 6)] for s in ("GND", "V+", "SDA", "SCL")], note="passive, no pull-ups"),
    dict(ref="U9", value="SHT45 0x44", part="Adafruit #6174", block="i2c", pins=qt("QT1") + qt("QT2", "nc"),
         ties=[[f"QT1.{s}", f"QT2.{s}"] for s in ("GND", "V+", "SDA", "SCL")], i2c=[0x44], pullups_k=10.0),
    dict(ref="U10", value="SHTC3 0x70", part="Adafruit #4636", block="i2c", pins=qt("QT1") + qt("QT2", "nc"),
         ties=[[f"QT1.{s}", f"QT2.{s}"] for s in ("GND", "V+", "SDA", "SCL")], i2c=[0x70], pullups_k=10.0),
    dict(ref="U11", value="BMP581 0x47", part="Adafruit #6407", block="i2c", pins=qt("QT1") + qt("QT2", "nc"),
         ties=[[f"QT1.{s}", f"QT2.{s}"] for s in ("GND", "V+", "SDA", "SCL")], i2c=[0x47], pullups_k=10.0),
    dict(ref="U12", value="LTR390 0x53", part="Adafruit #4831", block="i2c", pins=qt("QT1") + qt("QT2", "nc"),
         ties=[[f"QT1.{s}", f"QT2.{s}"] for s in ("GND", "V+", "SDA", "SCL")], i2c=[0x53], pullups_k=10.0),
    # ---------------------------------------------------------------- OLED
    dict(ref="DS1", value="OLED 2.7in SSD1325", part="Adafruit #2674", block="oled",
         pins=[(str(i), n, t, c) for i, n, t, c in (
             (1, "GND", PAS, "header"), (2, "3V3", PIN, "header"), (3, "NC3", PAS, "nc"), (4, "DC", IN, "header"),
             (5, "NC5", PAS, "nc"), (6, "NC6", PAS, "nc"), (7, "SCLK", IN, "header"), (8, "DIN", IN, "header"),
             (9, "NC9", PAS, "nc"), (10, "NC10", PAS, "nc"), (11, "NC11", PAS, "nc"), (12, "NC12", PAS, "nc"),
             (13, "NC13", PAS, "nc"), (14, "NC14", PAS, "nc"), (15, "CS", IN, "header"), (16, "RST", IN, "header"),
             (17, "NC17", PAS, "nc"), (18, "NC18", PAS, "nc"), (19, "NC19", PAS, "nc"), (20, "FGND", PAS, "nc"))],
         vlimit={"4": 3.6, "7": 3.6, "8": 3.6, "15": 3.6, "16": 3.6, "2": 3.6},
         note="SPI mode: R19, R21 fitted, R18, R20 empty"),
    dict(ref="C1", value="220uF 16V", part="Rubycon 16YXJ220MT16.3X11", block="oled",
         pins=[("+", "+", PAS, "header"), ("-", "-", PAS, "header")]),
    dict(ref="JP2", value="OLED link", part="2-pin header + shunt", block="oled",
         pins=[("1", "1", PAS, "header"), ("2", "2", PAS, "header")], note="remove to run mode B without the OLED"),
    # ---------------------------------------------------------------- MCUs and the Mac
    dict(ref="A1", value="NUCLEO-WL55JC1 TX", part="ST NUCLEO-WL55JC1", block="mcu",
         pins=[(p, n, t, "header") for p, n, t in (
             ("CN5.9", "PA11_SDA", BI), ("CN5.10", "PA12_SCL", BI), ("CN9.5", "PB5_CUPS", IN), ("CN8.2", "PB2_VANE", IN),
             ("CN8.4", "PB4_RAIN", IN), ("CN8.1", "PB1_ISET", IN), ("CN8.3", "PA10_VIN", IN), ("CN9.6", "PB8_PGOOD", IN),
             ("CN9.7", "PB10_CHG", IN), ("CN10.11", "PA5_SCK", "output"), ("CN10.15", "PA7_MOSI", "output"),
             ("CN10.17", "PA4_CS", "output"), ("CN10.21", "PC2_DC", "output"), ("CN10.23", "PC1_RST", "output"),
             ("CN6.4", "3V3", PAS), ("CN7.16", "3V3", PAS), ("CN6.6", "GND", PAS), ("CN6.7", "GND", PAS),
             ("CN5.7", "GND", PAS), ("CN10.20", "GND", PAS))]
         + [("CN6.5", "5V", PAS, "nc"), ("USB.VBUS", "USB.VBUS", PIN, "usb"), ("USB.GND", "USB.GND", PAS, "usb")],
         ties=[["CN6.4", "CN7.16"], ["CN6.6", "CN6.7", "CN5.7", "CN10.20", "USB.GND"]],
         # DS13293 Table 26: with the internal pull-up on, a pin stays below min(VDD, VDDA) + 0.3 V; an ADC
         # input measures only up to VREF+ = VDDA (3.3 V); PA10 (FT_fa, no pull) is limited to 5.5 V
         vlimit={"CN5.9": 3.6, "CN5.10": 3.6, "CN9.5": 3.6, "CN8.4": 3.6, "CN9.6": 3.6, "CN9.7": 3.6,
                 "CN8.2": 3.3, "CN8.1": 3.3, "CN8.3": 3.3},
         note="mode A: 3V3 from the on-board regulator (ST-LINK USB, JP4 on); mode B: 3V3 fed in on CN6.4 (JP4 off). "
              "Grounds: CN6.7 mode-B return, CN6.6 BB1 analog references, CN5.7 BB2, CN10.20 OLED"),
    dict(ref="A2", value="NUCLEO-WL55JC1 RX", part="ST NUCLEO-WL55JC1", block="mcu",
         pins=[("USB.VBUS", "USB.VBUS", PIN, "usb"), ("USB.GND", "USB.GND", PAS, "usb")]),
    dict(ref="H1", value="Mac USB host", part="the gateway Mac", block="mcu",
         pins=[("P1.VBUS", "P1.VBUS", POUT, "usb"), ("P1.GND", "P1.GND", PAS, "usb"),
               ("P2.VBUS", "P2.VBUS", POUT, "usb"), ("P2.GND", "P2.GND", PAS, "usb")],
         ties=[["P1.GND", "P2.GND"]], note="P1 = TX (mode A only), P2 = RX, a direct port"),
]


def qtnet(sig):
    """Every STEMMA QT pin of one signal on the bus (both branches share SDA, SCL, 3V3 and GND)."""
    out = [("W2", f"Q.{sig}"), ("W3", f"Q.{sig}")]
    out += [("U8", f"P{i}.{sig}") for i in range(1, 6)]
    out += [(r, f"QT1.{sig}") for r in ("U9", "U10", "U11", "U12")]
    out += [(r, f"QT{q}.{sig}") for r in ("U2", "U3", "U4", "U5") for q in (1, 2)]
    out += [("U6", f"QT1.{sig}")]
    return out


# name: (members, attributes). force: carries battery/charge/input/load current. domain: ground domain.
# vmax: worst-case voltage on the net, with its reason.
NETS = {
    # power island, force nets
    "USB_IN":   ([("PS1", "VBUS"), ("J3", "IN.VBUS"), ("J3", "VBUS"), ("U5", "X1.VIN+")],
                 dict(force=True, vmax=(5.5, "USB-C adapter, 5 V +10 %"))),
    "USB_CHG":  ([("U5", "X1.VIN-"), ("P1", "VBUS"), ("P1", "OUT.VBUS"), ("U1", "USB.VBUS")],
                 dict(force=True, vmax=(5.5, "as USB_IN"))),
    "USB_RET":  ([("PS1", "GND"), ("J3", "IN.GND"), ("J3", "GND"), ("P1", "GND"), ("P1", "OUT.GND"), ("U1", "USB.GND")],
                 dict(force=True, domain="power")),
    "SOLAR_IN": ([("PV1", "+"), ("J4", "IN.+"), ("J4", "+"), ("U4", "X1.VIN+")],
                 dict(force=True, vmax=(8.7, "P110 open circuit, cold"))),
    "SOLAR_CHG": ([("U4", "X1.VIN-"), ("P2", "+"), ("P2", "OUT.+"), ("U1", "DC.+")],
                  dict(force=True, vmax=(8.7, "as SOLAR_IN"))),
    "SOLAR_RET": ([("PV1", "-"), ("J4", "IN.-"), ("J4", "-"), ("P2", "-"), ("P2", "OUT.-"), ("U1", "DC.-")],
                  dict(force=True, domain="power")),
    "CELL_P":   ([("BT1", "+"), ("WG1", "1"), ("WG1", "2"), ("WG1", "3"),
                  ("U2", "X1.VIN+"), ("U6", "BAT1.+")],
                 dict(force=True, vmax=(4.2, "full cell"))),
    "BATT":     ([("U2", "X1.VIN-"), ("U1", "BATT.+")], dict(force=True, vmax=(4.2, "charger regulation"))),
    "SYS_OUT":  ([("U1", "SYS.+"), ("U3", "X1.VIN+")], dict(force=True, vmax=(4.5, "VO(REG) 4.4 V, 4.5 V max (SLUS810 8.5)"))),
    "LOAD":     ([("U3", "X1.VIN-"), ("U3", "X1.VBUS"), ("WG3", "1"), ("WG3", "2"), ("WG3", "3"), ("WG3", "4"),
                  ("R9", "1"), ("U7", "VIN")],
                 dict(force=True, vmax=(4.5, "as SYS_OUT"), exempt={("U7", "VIN"): "regulator chain, mode B (BSW:310-312)"})),
    "PGND":     ([("BT1", "-"), ("WG2", "1"), ("WG2", "2"), ("WG2", "3"), ("WG2", "4"), ("U1", "BATT.-"), ("R9", "2"), ("W1", "1")],
                 dict(force=True, domain="power")),
    # supplies
    "REG_OUT":  ([("U7", "VOUT"), ("JP1", "1")], dict(vmax=(3.4, "S7V8F3 3.3 V"))),
    "+3V3":     ([("JP1", "2"), ("A1", "CN6.4"), ("A1", "CN7.16"), ("W2", "H.V+"), ("W3", "H.V+"),
                  ("R1", "1"), ("R2", "1"), ("R3", "1"), ("JP2", "1")] + qtnet("V+"),
                 dict(vmax=(3.6, "NUCLEO 3V3 limit"))),
    "OLED_3V3": ([("JP2", "2"), ("DS1", "2"), ("C1", "+")], dict(vmax=(3.6, "as +3V3"))),
    "GND":      ([("W1", "2"), ("U7", "GND"), ("A1", "CN6.6"), ("A1", "CN6.7"), ("A1", "CN5.7"), ("A1", "CN10.20"),
                  ("W2", "H.GND"), ("W3", "H.GND"), ("R6", "2"), ("R8", "2"), ("C4", "2"), ("C2", "2"), ("C3", "2"),
                  ("J1", "2"), ("J1", "3"), ("J2", "3"), ("M1", "2"), ("M1", "3"), ("M2", "3"),
                  ("DS1", "1"), ("C1", "-")] + qtnet("GND"),
                 dict(domain="logic")),
    "VBUS_TX":  ([("H1", "P1.VBUS"), ("A1", "USB.VBUS")], dict(vmax=(5.5, "USB"))),
    "USBGND_TX": ([("H1", "P1.GND"), ("A1", "USB.GND")], dict(domain="logic")),
    "VBUS_RX":  ([("H1", "P2.VBUS"), ("A2", "USB.VBUS")], dict(vmax=(5.5, "USB"))),
    "USBGND_RX": ([("H1", "P2.GND"), ("A2", "USB.GND")], dict(domain="logic")),
    # I2C
    "I2C_SDA":  ([("A1", "CN5.9"), ("W2", "H.SDA"), ("W3", "H.SDA")] + qtnet("SDA"), dict(vmax=(3.6, "pull-ups to 3V3"))),
    "I2C_SCL":  ([("A1", "CN5.10"), ("W2", "H.SCL"), ("W3", "H.SCL")] + qtnet("SCL"), dict(vmax=(3.6, "pull-ups to 3V3"))),
    # charger signals
    "CHGR_VBUS": ([("U1", "H.VBUS"), ("R4", "1")], dict(vmax=(8.7, "solar Voc minus no drop at zero current"))),
    "DIV_MID":  ([("R4", "2"), ("R5", "1")], dict(vmax=(5.8, "2/3 of 8.7 V"))),
    "VIN_SENSE": ([("R5", "2"), ("R6", "1"), ("A1", "CN8.3")], dict(vmax=(2.9, "8.7 V / 3"))),
    "ISET":     ([("U1", "H.ISET"), ("R7", "1")], dict(vmax=(2.44, "ICHG max 975 mA / 400 x R_ISET 1 kohm (SLUS810 eq. 3)"))),
    "ISET_NODE": ([("R7", "2"), ("R8", "1"), ("C4", "1"), ("A1", "CN8.1")], dict(vmax=(2.44, "as ISET, less the 10k/1M divider"))),
    "PGOOD":    ([("U1", "H.PGOOD"), ("A1", "CN9.6")], dict(vmax=(3.1, "released: OUT 4.5 V max less red LED Vf ~1.4 V at uA; 2.9 V measured on USB"))),
    "CHG":      ([("U1", "H.CHG"), ("A1", "CN9.7")], dict(vmax=(3.1, "as PGOOD (CHG LED is the red one)"))),
    "NTC_RET":  ([("RT1", "2"), ("U1", "H.GND1")], dict(domain="power")),   # decision D2: the charger's own TS reference
    "THERM":    ([("U1", "H.THERM"), ("RT1", "1")], dict(vmax=(2.2, "TS 75 uA bias; charging stops above VCOLD 2.1 V (SLUS810 8.5)"))),
    # weather meter
    "CUPS":     ([("M1", "4"), ("J1", "4"), ("R2", "2"), ("C2", "1"), ("A1", "CN9.5")], dict(vmax=(3.3, "pull-up"))),
    "VANE":     ([("M1", "5"), ("J1", "5"), ("R1", "2"), ("A1", "CN8.2")], dict(vmax=(3.3, "pull-up"))),
    "RAIN":     ([("M2", "4"), ("J2", "4"), ("R3", "2"), ("C3", "1"), ("A1", "CN8.4")], dict(vmax=(3.3, "pull-up"))),
    # OLED
    "OLED_SCK": ([("A1", "CN10.11"), ("DS1", "7")], dict(vmax=(3.3, "MCU output"))),
    "OLED_DIN": ([("A1", "CN10.15"), ("DS1", "8")], dict(vmax=(3.3, "MCU output"))),
    "OLED_CS":  ([("A1", "CN10.17"), ("DS1", "15")], dict(vmax=(3.3, "MCU output"))),
    "OLED_DC":  ([("A1", "CN10.21"), ("DS1", "4")], dict(vmax=(3.3, "MCU output"))),
    "OLED_RST": ([("A1", "CN10.23"), ("DS1", "16")], dict(vmax=(3.3, "MCU output"))),
}

# Pins that are part of a net but must reach it by their own conductor (layout constraint, not netlist)
OWN_CONDUCTOR = {("DS1", "1"): "OLED GND straight to CN10.20 (FM:307)",
                 ("U6", "BAT1.+"): "gauge sense lead on its own WAGO lever, never in a force lead's clamp"}


# Bench power modes. Removable parts fitted in each mode, and the NUCLEO's JP4 (UM2592 Table 4: [1-2]
# STLK feeds the on-board LDO from the ST-LINK USB; removed for an external 3V3, UM2592 6.4 and Fig. 15).
# SHARED_SHUNT: one jumper cap serves both JP4 [1-2] and the BATTERY link JP1, so they cannot both be
# fitted (decision D3, approved 2026-11-02). In mode B the TX USB stays plugged in (decision D4): the
# ST-LINK runs from the Mac instead of being phantom-powered through PA2/PA3 and SWD.
SHARED_SHUNT = True
MODES = {
    "A": dict(fitted={"R9", "JP2"}, jp4=True, tx_usb=True, note="daily: NUCLEO on its USB, chain drives the test load"),
    "B": dict(fitted={"JP1"}, jp4=False, tx_usb=True, note="power tests: pack -> charger -> S7V8F3 -> 3V3"),
    "B+OLED": dict(fitted={"JP1", "JP2"}, jp4=False, tx_usb=True, note="mode B with the display on"),
}


def sources_3v3(mode):
    """What drives the +3V3 net in a mode."""
    out = []
    if mode["jp4"] and mode["tx_usb"]:
        out.append("A1 on-board LDO (ST-LINK USB through JP4)")
    if "JP1" in mode["fitted"]:
        out.append("U7 S7V8F3 through JP1")
    return out


# KiCad ERC results accepted on purpose, with the reason. Anything else ERC reports fails checks.py.
ERC_WAIVERS = {
    "lib_symbol_issues": "symbols are embedded in the generated schematic, not taken from a KiCad library",
    ("pin_not_driven", "A1", "CN9.6"): "PGOOD is open drain; the MCU's internal pull-up is the driver, invisible to ERC",
    ("pin_not_driven", "A1", "CN9.7"): "CHG is open drain; as PGOOD",
}
# Nets driven through a passive part (shunt, link, tie) or by a passive-typed source pin: KiCad's
# PWR_FLAG marks them as driven, as on any real schematic
PWR_FLAGS = ["USB_CHG", "SOLAR_CHG", "LOAD", "+3V3", "OLED_3V3", "GND", "PGND"]
