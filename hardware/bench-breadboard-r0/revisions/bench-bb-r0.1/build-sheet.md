# Bench breadboard build sheet

`source/make.py sheet` (or `all`) writes this sheet from `source/revisions/bench-bb-r0.1.toml`, so don't edit it by hand. Build in the order of the sections. A hole is `board:row column`: `A:j14` is board A, row j, column 14. The rails are L+ and L- beside row a, and R- and R+ beside row j.

**bench-bb-r0.1 is a frozen earlier revision** (record 6.1). Build this sheet for its own change, then the next revision's sheet, whose Remove and Add lists start from this one. This revision has no renders, because the renders show the current revision (`build-sheet.md` at the top of this directory). The wiring guide and the firmware describe the current revision too, so `make.py` holds this model to the connectivity proof and the D3 checks only.

| Model | |
|---|---|
| Revision | bench-bb-r0.1 (frozen) |
| `source/revisions/bench-bb-r0.1.toml` git blob | `4b47c41f7e90374f81c37effcdf5c08448509deb` |
| Renders | none: `make.py all` draws the current revision only |

## Changes from the previous revision (r0, 2026-10-29)

To rebuild the bench from the previous sheet, first remove everything under **Remove**, then fit everything under **Add**. Each end is a hole, a NUCLEO pin, a joint position or a part terminal. If part pins share a hole's strip, they follow the hole in brackets. The planner numbers the jumpers by stage and position, so their W-numbers shift whenever the model's jumpers change, and this list never uses them. Parts that moved are in section 1. The previous revision is `source/baseline-2026-10-29.json`, the r0 sheet the bench was built from.

### Remove

| What | Net | From | To |
|---|---|---|---|
| jumper | 3V3 | A:L+30 | A:f30 (R3.2) |
| jumper | 3V3 | A:L+20 | A:f19 (R2.2) |
| jumper | 3V3 | A:h19 (R2.2) | A:h8 (R1.2) |
| jumper | CUPS | A:d6 (BOBW.4) | A:f11 (C_CUPS.1) |
| jumper | CUPS | A:e6 (BOBW.4) | A:f4 (R1.1) |
| jumper | GND | A:L-23 | A:f23 (C_RAIN.2) |
| jumper | GND | A:e14 (BOBR.3) | A:f12 (C_CUPS.2) |
| jumper | GND | A:h12 (C_CUPS.2) | A:e5 (BOBW.3) |
| jumper | RAIN | A:e15 (BOBR.4) | A:f15 (R2.1) |
| jumper | RAIN | A:h15 (R2.1) | A:h22 (C_RAIN.1) |
| jumper | VANE | A:e7 (BOBW.5) | A:f26 (R3.1) |
| jumper | BATT | B:c38 (INA.VIN-) | B:c51 (CHGR.LIPO) |
| jumper | BATT | B:e38 (INA.VIN-) | B:g31 (GBAT.+) |
| jumper | CELL_POS | B:e37 (INA.VIN+) | B:g39 (CELL.+) |
| jumper | GND | B:e50 (CHGR.GND) | B:g53 (RLOAD.2) |
| jumper | GND | B:L-47 | B:c50 (CHGR.GND) |
| jumper | GND | B:L-45 | B:c42 (INA.GND) |
| jumper | GND | B:e42 (INA.GND) | B:g40 (CELL.-) |
| jumper | GND | B:h40 (CELL.-) | B:h32 (GBAT.-) |
| jumper | GND | B:L-19 | B:b16 (REG.GND) |
| jumper | SYS_OUT | B:h49 (RLOAD.1) | B:e53 (CHGR.OUT) |
| jumper | SYS_OUT | B:e15 (REG.VIN) | B:g49 (RLOAD.1) |
| jumper | 3V3 | B:c9 (SHUNT.2) | C:c23 (COLED.+, OLED.VCC) |
| jumper | GND | A:c4 (BOBW.2) | B:L-63 |
| jumper | GND | B:L-1 | C:c22 (COLED.-, OLED.GND) |
| jumper | 3V3 | B:e9 (SHUNT.2) | NUCLEO CN7.16 |
| jumper | CHG | B:e54 (CHGR.CHG) | NUCLEO CN10.25 |
| jumper | CUPS | A:j4 (R1.1) | NUCLEO CN10.14 |
| jumper | PGOOD | B:e55 (CHGR.PGOOD) | NUCLEO CN10.27 |
| jumper | RAIN | A:j15 (R2.1) | NUCLEO CN10.29 |
| jumper | VANE | A:j26 (R3.1) | NUCLEO CN7.30 |

### Add

| What | Net | From | To |
|---|---|---|---|
| jumper | 3V3 | A:L+20 | A:b19 (R2.2) |
| jumper | 3V3 | A:d19 (R2.2) | A:d2 (R1.2, R3.2) |
| jumper | GND | A:c14 (BOBR.3, C_RAIN.2) | A:c5 (BOBW.3, C_CUPS.2) |
| jumper | GND | B:L-63 | B:c62 (R6.2) |
| jumper | GND | B:d62 (R6.2) | B:f59 (C_ISET.2, R_IPD.2) |
| jumper | GND | B:d16 (REG.GND) | B:L-19 |
| jumper | ISET_CHGR | B:e57 (CHGR.ISET) | B:g57 (R_ISER.1) |
| jumper | CHG | B:e54 (CHGR.CHG) | NUCLEO CN9.7 |
| jumper | CUPS | A:d6 (BOBW.4, C_CUPS.1, R1.1) | NUCLEO CN10.14 |
| jumper | ISET | B:j58 (C_ISET.1, R_IPD.1, R_ISER.2) | NUCLEO CN8.1 |
| jumper | PGOOD | B:e55 (CHGR.PGOOD) | NUCLEO CN9.6 |
| jumper | RAIN | A:d15 (BOBR.4, C_RAIN.1, R2.1) | NUCLEO CN10.29 |
| jumper | VANE | A:e7 (BOBW.5, R3.1) | NUCLEO CN8.2 |
| jumper | VIN_SENSE | B:c61 (R5.2, R6.1) | NUCLEO CN8.3 |
| lead L_PACK_POS | CELL_POS | PACK.+ | J:WAGO_CELL_POS.1 |
| lead L_PACK_NEG | GND | PACK.- | J:WAGO_STAR.1 |
| lead L_CELL_INA | CELL_POS | J:WAGO_CELL_POS.2 | INA.X1_VINP |
| lead L_INA_BATT | BATT | INA.X1_VINM | J:WAGO_BATT.1 |
| lead L_BATT_POS | BATT | J:WAGO_BATT.2 | CHGR.BATT2 |
| lead L_BATT_NEG | GND | CHGR.BATT1 | J:WAGO_STAR.2 |
| lead L_SYSOUT_POS | SYS_OUT | CHGR.SYSOUT2 | J:WAGO_SYS_OUT.1 |
| lead L_SYSOUT_NEG | GND | CHGR.SYSOUT1 | insulated |
| lead L_RLOAD_A | SYS_OUT | J:WAGO_SYS_OUT.2 | RLOAD.1 |
| lead L_RLOAD_B | GND | RLOAD.2 | J:WAGO_STAR.3 |
| lead L_GAUGE_POS | CELL_POS | GAUGE.BAT1+ | J:WAGO_CELL_POS.3 |
| lead L_GAUGE_NEG | GAUGE_BAT_NEG | GAUGE.BAT1- | insulated |
| lead L_VBUS | SYS_OUT | INA.X1_VBUS | J:WAGO_SYS_OUT.3 |
| lead L_REG_VIN | SYS_OUT | J:WAGO_SYS_OUT.4 | B:b15 (REG.VIN) |
| lead L_TIE | GND | J:WAGO_STAR.4 | B:b16 (REG.GND) |
| lead L_NUC_RET | GND | NUCLEO CN6.7 | B:c16 (REG.GND) |
| lead L_REG_3V3 | 3V3 | B:c9 (SHUNT.2) | A:c41 (QT.V+) |
| lead L_OLED_VCC | 3V3 | NUCLEO CN7.16 | C:c23 (COLED.+, OLED.VCC) |
| lead L_OLED_GND | GND | NUCLEO CN10.20 | C:c22 (COLED.-, OLED.GND) |
| lead L_NTC_THERM | THERM | NTC.1 | B:c58 (CHGR.THERM) |
| lead L_NTC_RET | GND | NTC.2 | B:L-46 |
| lead L_USB_IN | CHGR_IN | ADAPTER.+ | CHGR.USBC |

## 1. Parts

| Part | What | Board | Pins (pin: hole) | Pin order from |
|---|---|---|---|---|
| BOBW | SparkFun BOB-14021 RJ11 breakout (wind cable) | A | 1: a3, 2: a4, 3: a5, 4: a6, 5: a7, 6: a8 | https://github.com/sparkfun/RJ11_Breakout |
| BOBR | SparkFun BOB-14021 RJ11 breakout (rain cable) | A | 1: a12, 2: a13, 3: a14, 4: a15, 5: a16, 6: a17 | https://github.com/sparkfun/RJ11_Breakout |
| QT | STEMMA QT to male header cable (to the 5-port hub) | A | GND: a40, V+: a41, SDA: a42, SCL: a43 | https://learn.adafruit.com/introducing-adafruit-stemma-qt/technical-specs |
| R1 | 10 kOhm resistor, cups pull-up | A | 1: c6, 2: c2 | passive |
| C_CUPS | 100 nF capacitor, cups filter | A | 1: e6, 2: e5 | passive |
| R2 | 10 kOhm resistor, rain pull-up | A | 1: c15, 2: c19 | passive |
| C_RAIN | 100 nF capacitor, rain filter | A | 1: e15, 2: e14 | passive |
| R3 | 10 kOhm resistor, vane pull-up | A | 1: b7, 2: b2 | passive |
| CHGR | Adafruit bq24074 charger #4755 (11-pin header; BATT and SYSOUT JST PH sockets; USB-C input) | B | GND: a50, LIPO: a51, GND2: a52, OUT: a53, CHG: a54, PGOOD: a55, CE: a56, ISET: a57, THERM: a58, GND3: a59, VBUS: a60; terminals (leads only): BATT1: L_BATT_NEG, BATT2: L_BATT_POS, SYSOUT1: L_SYSOUT_NEG, SYSOUT2: L_SYSOUT_POS, USBC: L_USB_IN | https://github.com/adafruit/Adafruit-BQ24074-PCB |
| INA | Adafruit INA228 #5832 (8-pin header; X1 screw terminal; I2C on its STEMMA QT cable) | B | VCC: a43, GND: a42, SCL: a41, SDA: a40, VBUS: a39, VIN-: a38, VIN+: a37, ALERT: a36; terminals (leads only): X1_VINP: L_CELL_INA, X1_VBUS: L_VBUS, X1_VINM: L_INA_BATT | https://github.com/adafruit/Adafruit-INA228-PCB |
| GAUGE | Adafruit MAX17048 #5580 (6-pin header, held in place only; I2C on its STEMMA QT cable) | B | VIN: a30, GND: a29, SCL: a28, SDA: a27, INT: a26, QSTART: a25; terminals (leads only): BAT1+: L_GAUGE_POS, BAT1-: L_GAUGE_NEG | https://learn.adafruit.com/adafruit-max17048-lipoly-liion-fuel-gauge-and-battery-monitor/pinouts |
| REG | Pololu S7V8F3 3.3 V regulator #2122 | B | SHDN: a14, VIN: a15, GND: a16, VOUT: a17 | bench check |
| SHUNT | 2-pin header with shunt: BATTERY POWER, USB UNPLUGGED (open in mode A) | B | 1: a8, 2: a9 | passive |
| R4 | 10 kOhm 1 % resistor, charger input divider (top, from VBUS) | B | 1: c60, 2: c63 | passive |
| R5 | 10 kOhm 1 % resistor, charger input divider (top, in series with R4) | B | 1: d63, 2: d61 | passive |
| R6 | 10 kOhm 1 % resistor, charger input divider (bottom, to the logic ground rail) | B | 1: e61, 2: e62 | passive |
| R_ISER | 10 kOhm 1 % resistor, ISET series (at the charger) | B | 1: f57, 2: f58 | passive |
| C_ISET | 100 nF capacitor, ISET node filter | B | 1: g58, 2: g59 | passive |
| R_IPD | 1 MOhm resistor, ISET node pull-down | B | 1: h58, 2: h59 | passive |
| PACK | 1S3P 6600 mAh, 3.0-4.2 V (3 x 2200 mAh, #353) | off board, beside B | terminals (leads only): +: L_PACK_POS, -: L_PACK_NEG | bench check |
| RLOAD | 100 Ohm 1/2 W test load (mode A only) | off board, beside B | terminals (leads only): 1: L_RLOAD_A, 2: L_RLOAD_B | passive |
| NTC | 10 kOhm NTC thermistor #372 (B = 3950) on THERM, taped to the pack | off board, beside B | terminals (leads only): 1: L_NTC_THERM, 2: L_NTC_RET | passive |
| ADAPTER | USB-C wall adapter, 5 V >= 2 A, floating from the Mac | off board, beside B | terminals (leads only): +: L_USB_IN | bench check |
| OLED | Adafruit 2.7in 128x64 OLED #2674 (SSD1325, SPI mode: R19 and R21 fitted) | C | GND: a22, VCC: a23, NC3: a24, DC: a25, WR: a26, RD: a27, SCLK: a28, DIN: a29, D2: a30, D3: a31, D4: a32, D5: a33, D6: a34, D7: a35, CS: a36, RST: a37, NC17: a38, NC18: a39, NC19: a40, FG: a41 | https://learn.adafruit.com/2-7-monochrome-128x64-oled-display-module/pinouts |
| COLED | 220 uF electrolytic capacitor, OLED supply | C | +: e23, -: e22 | bench check |

## 2. Jumpers

Each jumper is one pre-cut wire of solid 22 AWG between its two holes, laid flat (record H3). The exception is the OLED's signal jumpers from board C to CN10 (W20, W21, W22, W23, W24). They're female-to-male Dupont jumpers of about 30 cm on the morpho's male pins, for the bench OLED only (record N3 and the "OLED wires" bench check). Also, the station signals still on the morpho's male pins (W15 (CUPS, CN10.14), W26 (RAIN, CN10.29)) are female-to-male Dupont jumpers too, with the female end on the pin. You can't push a solid wire onto a male pin. A later revision moves them to the ARDUINO female headers as solid 22 AWG (record 4.5, change B, and the "Morpho signal pins" bench check).

The Length column gives the kit jumper to use. `kit_length()` in make.py picks from the BOJACK kit's 14 sizes and takes the next size up for a diagonal. You cut an ARDUINO-header jumper to fit once the base plate fixes where the NUCLEO sits (record H7: at most 200 mm). Colour by class: i2c blue, wind green, rain cyan, charger orange, display purple, power red, ground black, analog pink, battery lead brown. A link is a jumper that the model names by a stable id.

### Board A

| Jumper | From | To | Length | Net | Class | Link |
|---|---|---|---|---|---|---|
| W1 | A:L+41 | A:b41 | 10 mm | 3V3 | power |  |
| W2 | A:L+20 | A:b19 | 10 mm | 3V3 | power |  |
| W3 | A:d19 | A:d2 | cut to fit: 17.0 holes (43 mm between the legs) | 3V3 | power |  |
| W4 | A:L-40 | A:b40 | 7 mm | GND | ground |  |
| W5 | A:L-20 | A:b14 | 17 mm | GND | ground |  |
| W6 | A:c14 | A:c5 | 22 mm | GND | ground |  |
| W7 | A:b5 | A:b4 | 2 mm | GND | ground |  |

### Board B

| Jumper | From | To | Length | Net | Class | Link |
|---|---|---|---|---|---|---|
| W8 | B:L-63 | B:c62 | 10 mm | GND | ground |  |
| W9 | B:d62 | B:f59 | 12 mm | GND | ground |  |
| W10 | B:d16 | B:L-19 | 15 mm | GND | ground |  |
| W11 | B:e57 | B:g57 | 10 mm | ISET_CHGR | analog |  |
| W12 | B:b17 | B:b8 | 22 mm | REG_OUT | power | LK_REG_SHUNT |

### To the NUCLEO

| Jumper | From | To | Length | Net | Class | Link |
|---|---|---|---|---|---|---|
| W13 | A:e41 | NUCLEO CN6.4 | cut to fit from 22 AWG solid | 3V3 | power | LK_3V3_CN6_4 |
| W14 | B:e54 | NUCLEO CN9.7 | cut to fit from 22 AWG solid | CHG | charger |  |
| W15 | A:d6 | NUCLEO CN10.14 | Dupont, about 30 cm | CUPS | wind |  |
| W16 | A:e40 | NUCLEO CN6.6 | cut to fit from 22 AWG solid | GND | ground | LK_QT_GND_CN6_6 |
| W17 | A:e43 | NUCLEO CN5.10 | cut to fit from 22 AWG solid | I2C_SCL | i2c |  |
| W18 | A:e42 | NUCLEO CN5.9 | cut to fit from 22 AWG solid | I2C_SDA | i2c |  |
| W19 | B:j58 | NUCLEO CN8.1 | cut to fit from 22 AWG solid | ISET | analog |  |
| W20 | C:e36 | NUCLEO CN10.17 | Dupont, about 30 cm | OLED_CS | display |  |
| W21 | C:e25 | NUCLEO CN10.21 | Dupont, about 30 cm | OLED_DC | display |  |
| W22 | C:e29 | NUCLEO CN10.15 | Dupont, about 30 cm | OLED_DIN | display |  |
| W23 | C:e37 | NUCLEO CN10.23 | Dupont, about 30 cm | OLED_RST | display |  |
| W24 | C:e28 | NUCLEO CN10.11 | Dupont, about 30 cm | OLED_SCLK | display |  |
| W25 | B:e55 | NUCLEO CN9.6 | cut to fit from 22 AWG solid | PGOOD | charger |  |
| W26 | A:d15 | NUCLEO CN10.29 | Dupont, about 30 cm | RAIN | rain |  |
| W27 | A:e7 | NUCLEO CN8.2 | cut to fit from 22 AWG solid | VANE | wind |  |
| W28 | B:c61 | NUCLEO CN8.3 | cut to fit from 22 AWG solid | VIN_SENSE | analog |  |

### Cut list

| Length | Jumpers |
|---|---:|
| 2 mm | 1 |
| 7 mm | 1 |
| 10 mm | 4 |
| 12 mm | 1 |
| 15 mm | 1 |
| 17 mm | 1 |
| 22 mm | 2 |
| Dupont, about 30 cm | 7 |
| cut to fit from 22 AWG solid | 9 |
| cut to fit: 17.0 holes (43 mm between the legs) | 1 |

## 3. Leads

Leads are the wires off the breadboard (record D2). Only sense leads, the OLED's supply pair and the P1 regulator chain (record P1) end in a breadboard hole or on a NUCLEO pin. No other force lead does. The battery-path force leads end in a lever clamp, the INA228's X1 screw terminal or a JST PH socket. The adapter cable goes into the charger's USB-C, the load's own leads end at the resistor, and L_SYSOUT_NEG has an insulated free end.

Strip and twist a stranded end before it goes into a lever clamp. The screw terminals take solid 22 AWG only (record P7). Cut each lead to its length or shorter, because every span of the battery path counts (section 5, check 7). Fold an `insulated` end back under heat-shrink.

| Lead | Role | Wire | Length | Max mA | From | To | Net | Segment | Exception | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| L_PACK_POS | force | 26 AWG pigtail | 60 mm | - | PACK.+ | J:WAGO_CELL_POS.1 | CELL_POS | PATH_PACK_POS | - | cable 1, pack-mating half, red: the pack's plug to CELL+ position 1 |
| L_PACK_NEG | force | 26 AWG pigtail | 60 mm | - | PACK.- | J:WAGO_STAR.1 | GND | PATH_PACK_NEG | - | cable 1, pack-mating half, black: the pack's plug to STAR position 1 |
| L_CELL_INA | force | 22 AWG solid | 50 mm | - | J:WAGO_CELL_POS.2 | INA.X1_VINP | CELL_POS | PATH_POS | - | CELL+ position 2 to the INA228 screw terminal X1.3 (VIN+) |
| L_INA_BATT | force | 22 AWG solid | 50 mm | - | INA.X1_VINM | J:WAGO_BATT.1 | BATT | PATH_POS | - | the INA228 screw terminal X1.1 (VIN-) to BATT position 1 |
| L_BATT_POS | force | 26 AWG pigtail | 60 mm | - | J:WAGO_BATT.2 | CHGR.BATT2 | BATT | PATH_POS | - | cable 1, board-mating half, red: BATT position 2 to the charger's BATT socket |
| L_BATT_NEG | force | 26 AWG pigtail | 60 mm | - | CHGR.BATT1 | J:WAGO_STAR.2 | GND | PATH_NEG | - | cable 1, board-mating half, black: the charger's BATT socket to STAR position 2 |
| L_SYSOUT_POS | force | 26 AWG pigtail | 60 mm | - | CHGR.SYSOUT2 | J:WAGO_SYS_OUT.1 | SYS_OUT | PATH_CELL_OUT | - | cable 2, board-mating half, red: the charger's SYSOUT socket to OUT position 1 |
| L_SYSOUT_NEG | force | 26 AWG pigtail, one end insulated | 60 mm | - | CHGR.SYSOUT1 | insulated | GND | - | - | cable 2, board-mating half, black: insulated with heat-shrink, folded back (record P4) |
| L_RLOAD_A | force | 22 AWG solid | 30 mm | - | J:WAGO_SYS_OUT.2 | RLOAD.1 | SYS_OUT | - | - | the load's own lead into OUT position 2 (mode A only) |
| L_RLOAD_B | force | 22 AWG solid | 30 mm | - | RLOAD.2 | J:WAGO_STAR.3 | GND | - | - | the load's other lead into STAR position 3 (mode A only) |
| L_GAUGE_POS | sense | 26 AWG pigtail | 60 mm | - | GAUGE.BAT1+ | J:WAGO_CELL_POS.3 | CELL_POS | - | - | cable 3, board-mating half in the gauge's BAT1 socket, red: to CELL+ position 3 |
| L_GAUGE_NEG | sense | 26 AWG pigtail, one end insulated | 60 mm | - | GAUGE.BAT1- | insulated | GAUGE_BAT_NEG | - | - | cable 3, black: insulated with heat-shrink, folded back; the gauge's ground comes over STEMMA QT (record P4) |
| L_VBUS | sense | 22 AWG solid | 60 mm | - | INA.X1_VBUS | J:WAGO_SYS_OUT.3 | SYS_OUT | - | - | the INA228 screw terminal X1.2 (VBUS) to OUT position 3, the sense colour: load_mv |
| L_REG_VIN | force | 22 AWG solid | 100 mm | - | J:WAGO_SYS_OUT.4 | B:b15 | SYS_OUT | - | P1 regulator | OUT position 4 into the regulator VIN strip (record P1, P6; H7 at most 100 mm) |
| L_TIE | force | 22 AWG solid | 100 mm | - | J:WAGO_STAR.4 | B:b16 | GND | - | P1 regulator | the TIE: STAR position 4 into the regulator GND strip, the only conductor between STAR and logic ground (record P4; H7 at most 100 mm) |
| L_NUC_RET | force | 22 AWG solid | 200 mm | - | NUCLEO CN6.7 | B:c16 | GND | - | P1 regulator | the NUCLEO's mode-B supply return: CN6.7 into the regulator GND strip, fitted in both modes (record N4); its length is set by routing, bounded by checks C20 and C21 (H7) |
| L_REG_3V3 | force | 22 AWG solid | 280 mm | - | B:c9 | A:c41 | 3V3 | - | P1 regulator | the SHUNT.2 strip to the board-A 3V3 node, the QT.V+ strip (column 41) where LK_3V3_CN6_4 starts, never the A:L+ rail: the chain to CN6.4 has no planner jumper (P1). The mode-B feed, dead in mode A with the shunt open (record P1, N3); its length is set by routing, bounded by checks C20 and C21 (H7) |
| L_OLED_VCC | supply | 26 AWG dupont | 300 mm | - | NUCLEO CN7.16 | C:c23 | 3V3 | - | - | female-to-male jumper from CN7.16 (3V3) into the OLED's 3V3 strip (column 23, with COLED +); unplugged in mode B |
| L_OLED_GND | supply | 26 AWG dupont | 300 mm | - | NUCLEO CN10.20 | C:c22 | GND | - | - | female-to-male jumper from CN10.20 (GND) into the OLED's GND strip (column 22, with COLED -) |
| L_NTC_THERM | sense | 22 AWG solid | 300 mm | - | NTC.1 | B:c58 | THERM | - | - | the NTC's lead, extended, into the charger's THERM strip |
| L_NTC_RET | sense | 22 AWG solid | 300 mm | - | NTC.2 | B:L-46 | GND | - | - | the NTC's other lead, extended, to the board-B logic ground rail, not STAR (STAR position 5 stays the step 1b spare) |
| L_USB_IN | force | 22 AWG cable | 1000 mm | - | ADAPTER.+ | CHGR.USBC | CHGR_IN | - | - | the wall adapter's USB-C cable into the charger's USB-C receptacle (to VBUS through D2) |

## 4. Joints

Joints are the lever connectors off the breadboard. They sit in a row beside board B, glued down (record P3-P7, H1). Each joint is one node. Put one lead end in each position. Close every lever, then tug each lead by hand to test it.

| Joint | Kind | Net | Positions | Note |
|---|---|---|---|---|
| WAGO_CELL_POS | WAGO 222-415 | CELL_POS | 1: L_PACK_POS; 2: L_CELL_INA; 3: L_GAUGE_POS; 4: spare; 5: spare | CELL+: 1 pack red, 2 L_CELL_INA, 3 gauge red, 4 reserved for step 1b (the battery INA VBUS lead), 5 spare |
| WAGO_BATT | WAGO 222-413 | BATT | 1: L_INA_BATT; 2: L_BATT_POS; 3: spare | BATT: 1 L_INA_BATT, 2 board pigtail red (to the charger's BATT socket), 3 spare |
| WAGO_SYS_OUT | WAGO 222-415 | SYS_OUT | 1: L_SYSOUT_POS; 2: L_RLOAD_A; 3: L_VBUS; 4: L_REG_VIN; 5: spare | OUT: 1 SYSOUT pigtail red, 2 the 100 ohm load, 3 L_VBUS (sense), 4 L_REG_VIN, 5 spare |
| WAGO_STAR | WAGO 222-415 | GND | 1: L_PACK_NEG; 2: L_BATT_NEG; 3: L_RLOAD_B; 4: L_TIE; 5: spare | STAR at pack negative (record P4): 1 pack black, 2 board pigtail black, 3 the load return, 4 the TIE (L_TIE), 5 spare, kept for step 1b exit (g) |

## 5. Power path

Each battery-path segment (record M6) has a budget at 1 A (record P8). When you run C12-C14 at 1 A, fill the measured columns: mOhm = the meter's mV / the INA228 current in A. The lead copper column is an estimate from each lead's gauge and length.

| Segment | Steps | Budget mOhm | Implied mV at 38 mA | Implied mV at 1 A | Lead copper mOhm | Measured mV | I (A) | mOhm |
|---|---|---|---|---|---|---|---|---|
| PATH_POS | L_PACK_POS > WAGO_CELL_POS > L_CELL_INA > INA > L_INA_BATT > WAGO_BATT > L_BATT_POS | 75 | 2.85 | 75 | 21.4 |  |  |  |
| PATH_NEG | L_BATT_NEG > WAGO_STAR > L_PACK_NEG | 40 | 1.52 | 40 | 16.1 |  |  |  |
| PATH_PACK_POS | L_PACK_POS > WAGO_CELL_POS | 28 | 1.06 | 28 | 8.0 |  |  |  |
| PATH_PACK_NEG | L_PACK_NEG > WAGO_STAR | 28 | 1.06 | 28 | 8.0 |  |  |  |
| PATH_CELL_OUT | WAGO_CELL_POS > L_CELL_INA > INA > L_INA_BATT > WAGO_BATT > L_BATT_POS > CHGR > L_SYSOUT_POS > WAGO_SYS_OUT | flag: drop - dV0 > 20 mV | - | - | 21.4 |  |  |  |
| R_pack | PATH_PACK_POS + PATH_PACK_NEG, measured (C14): step 1 exit 5, record M4 | 56 | 2.13 | 56 | - |  |  |  |

Coverage: PATH_CELL_OUT covers CELL+ to OUT only; the pack mating (PATH_PACK_POS, PATH_PACK_NEG) is covered by C6/C11 at preflight, C12-C14 at 1 A and the VCELL step flag live.

## 6. Pre-run checklist (C1-C23)

Meter: Fluke 87V, 600 mV DC range, high-resolution mode (0.01 mV), read directly (record 7.1 Q2). To back-probe the pack plug, slide the probe tip along the wire into the back of the housing, and never pull the plug to probe it. The 1 A limits are in mOhm: the mV limit is the mOhm figure times the INA228 current in A (0.8-1.0 A). Every reading goes into the run's preflight block (record D6, `tools/preflight.py`). If a span fails, measure it joint by joint (C14) to find the bad one.

### Mode A

| # | When | Condition | Measure | Pass |
|---|---|---|---|---|
| C1 | before every mode-A run | pack unplugged, nothing powered | continuity INA228 X1.2 (VBUS) to X1.3 (VIN+) on every INA228 | open; SJ1 open |
| C2 | before every mode-A run | as C1 | open the TIE's lever at STAR: STAR to CN6.6 | < 0.5 ohm; with the TIE closed, under 0.5 ohm; with the lever open, at least 100 ohm on the ohms range (a reading with lever = "open"; the value recorded): never 0, since a second conductor reads like the TIE, and not OL either, since the TIE is not the only path: R9, R_ISER and R_IPD give about 1.01 MOhm, about 11 kOhm plus a diode by meter polarity (PB1's ESD diode), and the 100 ohm load, OUT and the regulator's switches give another diode path |
| C3 | before every mode-A run | as C1 | each breakout test-point strip (charger a50-a53, a59; INA228 VIN+, VIN-, VBUS) holds only its header pin | by eye against the build sheet |
| C4 | before every mode-A run | as C1 | pack-mating pigtail and board pigtails: red is + by meter against the board's silkscreen; unused black leads insulated | by eye and meter |
| C5 | before every mode-A run | pack plugged, input off, load on, 1 min settled (about 38 mA) | INA228 current against OUT / 100 ohm | within 2 % + 2 mA (reading: ma = INA228, value = OUT / 100 ohm in mA) |
| C6 | before every mode-A run | as C5 | pack plug + (back-probed) to charger header OUT | <= 10 mV |
| C7 | before every mode-A run | as C5 | STAR to charger header GND | <= 1 mV; the load does not return through the charger |
| C8 | before every mode-A run | as C5 | STAR to CN6.6 | <= 1 mV |
| C9 | before every mode-A run | as C5, then the load lever opened | INA228 current at zero load; record dV0 = gauge VCELL - INA VBUS | within +-1 mA; dV0 recorded (the block's dv0_mv) |
| C10 | before every mode-A run | as C5 | DMM at the pack plug against gauge VCELL | within 10 mV (reading: mv = DMM - gauge) |
| C11 | before every mode-A run | as C5, DMM min/max on C6's span | wiggle each lever, pigtail, PH plug, the TIE, the regulator leads and both USB cables for 30 s; watch vout and vcell in the logger and the A0 (ISET) and A2 (VIN) readings; under the node firmware only (benchlink has no counter), spin the cups through the wiggle: the next observation's wind speed is not zero and STATUS still shows meter_link=ok | no step >= 1 mV on the DMM (about 26 mOhm); no visible step in the logger |
| C12 | after every rewire and at every step exit (1 A charge) | charging, first 10 min of CC, I = 0.8-1.0 A, V_ISET about 2.0-2.4 V | + span: pack plug + to header LIPO | <= 75 mOhm; PATH_POS, including the 15 mOhm shunt |
| C13 | after every rewire and at every step exit (1 A charge) | as C12 | - span: header GND to pack plug - | <= 40 mOhm; PATH_NEG |
| C14 | after every rewire and at every step exit (1 A charge) | as C12 | each JST PH mating; each lever clamp to clamp; each screw (VIN+ link, VIN- link); the two pack-side spans: pack plug + (back-probed) to the CELL+ clamp, and the STAR clamp to pack plug - (back-probed) | each JST PH mating <= 20 mOhm, each clamp <= 5 mOhm, each screw <= 5 mOhm, each pack-side span <= 28 mOhm; their sum recorded as R_pack |
| C16 | after every rewire and at every step exit (1 A charge) | as C12 | ISET-derived current (R_ISET 1000 ohm) against INA228 battery current | within 10 % + 20 mA; a shunt bypass reads near 0 (reading: ma = INA228, value = ISET-derived mA) |
| C17 | after every rewire and at every step exit (1 A charge) | as C12, then the input removed for a moment | charger header VBUS while charging; CHG and PGOOD high levels with the input removed (both off) | VBUS >= 4.6 V; CHG/PGOOD highs <= 3.6 V (VDD + 0.3 V) |
| C18 | after every rewire and at every step exit (1 A charge) | as C12, DMM min/max on the + span | wiggle as C11 | no step >= 2 mV |
| C19 | before every mode-A run | NUCLEO | tug each Arduino-header jumper; tape in place; jumpers tied | none moves; tape present |

### Mode B

Run these with the station on the regulator (section 7: NUCLEO USB unplugged, SHUNT fitted, 100 ohm load out, OLED VCC lead unplugged). Keep the meter on min/max across at least 5 radio TX bursts.

| # | When | Condition | Measure | Pass |
|---|---|---|---|---|
| C15 | before every mode-B run | mode B, TX bursts (NUCLEO USB unplugged, SHUNT fitted, 100 ohm load out, OLED VCC lead unplugged, DMM min/max across at least 5 radio TX bursts) | TIE: STAR to the regulator GND strip | < 1 mV |
| C20 | before every mode-B run | as C15 | STAR to CN6.6 | <= 3 mV |
| C21 | before every mode-B run | as C15 | the regulator's VOUT pin to CN6.4 (the whole P1 output chain: LK_REG_SHUNT, SHUNT, L_REG_3V3, the board-A 3V3 strip where LK_3V3_CN6_4 starts (QT.V+; change C, which moved it to the load switch, is not built), LK_3V3_CN6_4) | <= 10 mV |
| C22 | before every mode-B run | as C15, between TX bursts | mode-B dV0: gauge VCELL - INA VBUS with the station idle | recorded (the block's dv0_mv) |
| C23 | before every mode-B run | as C15, DMM min/max on C21's span | wiggle L_REG_VIN, LK_REG_SHUNT, the SHUNT, L_REG_3V3, LK_3V3_CN6_4, L_NUC_RET (the CN6.7 lead) and L_TIE, for 30 s each | no reset; no step >= 2 mV |

Before every mode-A run: C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C19. Before every mode-B run: C15, C20, C21, C22, C23. After every rewire and at every step exit (1 A charge): C12, C13, C14, C16, C17, C18.

## 7. Mode A and mode B

The drawings show mode A, the daily setup with the NUCLEO on USB. In mode A the BATTERY POWER shunt is open, the 100 ohm load is fitted and the OLED is on its own supply pair. A mode change never touches ground.

**Mode A to B:**

1. Unplug the NUCLEO's USB.
2. Open the load's two levers (WAGO_SYS_OUT position 2 and WAGO_STAR position 3) and remove the 100 ohm load.
3. Unplug the OLED's VCC lead (L_OLED_VCC) from CN7.16.
4. Fit the BATTERY POWER shunt (SHUNT).

**Mode B to A:** the reverse, with the shunt out before the USB goes in.

1. Remove the BATTERY POWER shunt.
2. Plug the OLED's VCC lead (L_OLED_VCC) back into CN7.16.
3. Refit the 100 ohm load and close its two levers.
4. Plug the NUCLEO's USB in.

The TIE (L_TIE) and the CN6.7 lead (L_NUC_RET) never move.

## Bench checks

Do these before you connect power.

- **BOBW** (SparkFun BOB-14021 RJ11 breakout (wind cable)): Module preparation first (record H5, decided 2026-10-30, 7.1 Q6): the BOB-14021 comes as a panel of two boards; separate it into its two boards (one per meter cable: BOBW, BOBR), then solder one PRT-00132 jack and the 6-pin header onto each board, then do the per-conductor continuity check with the meter cable plugged in: wind 3/4 the cups, 2/5 the vane (SEN-15901). Inner conductors 3, 4: the cups. Outer 2, 5: the vane. The meter cable is never cut.
- **BOBR** (SparkFun BOB-14021 RJ11 breakout (rain cable)): Module preparation first (record H5, decided 2026-10-30, 7.1 Q6): the BOB-14021 comes as a panel of two boards; separate it into its two boards (one per meter cable: BOBW, BOBR), then solder one PRT-00132 jack and the 6-pin header onto each board, then do the per-conductor continuity check with the meter cable plugged in: rain 3/4 the bucket switch (SEN-15901). The meter cable is never cut.
- **QT** (STEMMA QT to male header cable (to the 5-port hub)): The hub's cable: every I2C device on its V+, the board-A 3V3 node (unswitched until change C, record 4.6).
- **R1** (10 kOhm resistor, cups pull-up): Jack end: R1.1 in BOBW pin 4's own strip (column 6), so no jumper sits between the jack pin and its pull-up (record M7).
- **C_CUPS** (100 nF capacitor, cups filter): Jack end: across BOBW pins 4 and 3, the cups pair, in their own strips (columns 6 and 5; record M7).
- **R2** (10 kOhm resistor, rain pull-up): Jack end: R2.1 in BOBR pin 4's own strip (column 15), so no jumper sits between the jack pin and its pull-up (record M7).
- **C_RAIN** (100 nF capacitor, rain filter): Jack end: across BOBR pins 4 and 3, the bucket pair, in their own strips (columns 15 and 14; record M7).
- **R3** (10 kOhm resistor, vane pull-up): Jack end: R3.1 in BOBW pin 5's own strip (column 7; record M7), R3.2 in R1.2's 3V3 strip (column 2).
- **CHGR** (Adafruit bq24074 charger #4755 (11-pin header; BATT and SYSOUT JST PH sockets; USB-C input)): Labels upright, board over the rails: VBUS at column 60, GND at 50. The LIPO, OUT and GND header pins (columns 50-53 and 59) are zero-current test points, each alone in its strip (record P2): current leaves only through the BATT and SYSOUT sockets. CHG and PGOOD are open drain, active low. From the schematic (confirm on the board in hand): R_ISET is 1 kOhm (R9, behind the closed 1A jumper), so ICHG = 890 / 1000 = 0.89 A typ; measure it (check 2). TMR is tied to GND, so all safety timers are disabled (timers disabled: no RTMR, and a long 1 A charge cannot end in a timer fault). ITERM is 0.30 A typ (0.225-0.375 A; record P9). The CHG and PGOOD LED anodes (D3, D1, through R7, R11, 10 kOhm) are on OUT, not VBUS, so a released pin sits near OUT - Vf and the LEDs stay. CE has R8 (10 kOhm) to GND, charging enabled, leave it open. ISET goes to PB1 through the ISET network (R_ISER, C_ISET, R_IPD; record M2). The THERM jumper (closed) ties R10 (10 kOhm) to TS: cut it for the NTC. The input is the breakout's own USB-C from a floating wall adapter (ADAPTER); the USB-C (X2) reaches VBUS through a Schottky diode (D2, SK34A), so VBUS reads the source minus that drop. Only R4's sense tap uses the VBUS header pin.
- **INA** (Adafruit INA228 #5832 (8-pin header; X1 screw terminal; I2C on its STEMMA QT cable)): Labels upright: VIN (VCC) at column 43, ALRT at 36. The shunt (15 mOhm 1 % 2 W) is between VIN+ and VIN-: the battery path lands on the X1 screw terminal, 22 AWG solid only (record P7), never on the header's strips. VBUS comes over its own sense lead L_VBUS from X1 pin 2 to the OUT joint (record P5). SJ1, the back solder jumper from VBUS to VIN+, must be open: check it by continuity, X1.2 to X1.3 open (pre-run checklist row C1). The I2C pull-ups are one 10 kOhm resistor pack. The header GND and VCC stay unconnected: the INA228 takes power and ground over STEMMA QT (record P4).
- **GAUGE** (Adafruit MAX17048 #5580 (6-pin header, held in place only; I2C on its STEMMA QT cable)): Labels upright: VIN at column 30, QStart at 25. No wire goes to the header. The board-mating half of a cut #1131 in one JST PH socket (BAT1; the other socket empty): its red lead to CELL+ position 3, the cell side of the shunt (record P5); its black lead insulated, folded back. The gauge's ground comes over STEMMA QT (record P4).
- **REG** (Pololu S7V8F3 3.3 V regulator #2122): Back labels, top to bottom: VOUT, GND (square pad), VIN, SHDN. Front up, over the rails: VOUT at column 17, SHDN at 14. Fed from the OUT joint by L_REG_VIN; its GND strip takes the TIE (L_TIE) and the NUCLEO return (L_NUC_RET). It feeds CN6.4 through the SHUNT, L_REG_3V3 and the QT.V+ strip, the board-A 3V3 node where LK_3V3_CN6_4 starts (mode B only; record P1, N3).
- **PACK** (1S3P 6600 mAh, 3.0-4.2 V (3 x 2200 mAh, #353)): 1S3P 6600 mAh, 3.0-4.2 V (3.7 V nominal). On the plate beside board B, never in the charger's BATT socket while the INA228 meters the battery (record P3). Its own lead is never cut: it plugs into the #1131 pack-mating half, at most 60 mm, no solder; red to CELL+ position 1, black to STAR position 1. JST PH colours vary: check + and - with a meter before plugging in.
- **RLOAD** (100 Ohm 1/2 W test load (mode A only)): Off the breadboard, between the OUT joint (position 2) and STAR (position 3) on its own leads (record P6). Removed for mode B.
- **NTC** (10 kOhm NTC thermistor #372 (B = 3950) on THERM, taped to the pack): Remove or cut the breakout's fixed 10 kOhm TS resistor first: cut the THERM solder jumper on its back (R10). In parallel TS never exceeds 10 kOhm (0.75 V at 75 uA), the cold trip (2.1 V) never fires and the hot trip moves to about 35 C. Tape the bead to the pack; extend its leads as needed (microamps). Its return goes to the board-B logic ground rail, not STAR, with the TS offset accepted (record D2: up to 40 mV during a 1 A charge, +0.4 C cold and +3.8 C hot). With B = 3950 charging stops below about +3.5 C and above about +47 C, not 0 and 50 C (spec D3).
- **ADAPTER** (USB-C wall adapter, 5 V >= 2 A, floating from the Mac): The charger's only input in step 1 (record D2, P4): a floating wall adapter on the breakout's own USB-C, never the Mac or a hub that shares the NUCLEO ground. One cable carries the supply and its return into the receptacle; the return reaches the charger's own GND inside the breakout, so the model draws the + only and the adapter adds no ground tie.
- **OLED** (Adafruit 2.7in 128x64 OLED #2674 (SSD1325, SPI mode: R19 and R21 fitted)): SPI mode needs R19 and R21 fitted and R18 and R20 empty on the back. Pin 1 (GND) at column 22, pin 20 (frame ground) at 41. Only GND, VCC, DC, SCLK, DIN, CS and RST are wired; FG may stay open. Bench only: its supply comes straight from the NUCLEO on its own pair (VCC from CN7.16, GND to CN10.20; record N3), never from a breadboard rail.
- **COLED** (220 uF electrolytic capacitor, OLED supply): Polarised: + (the longer lead) in column 23 with the OLED's 3.3 V, the striped - lead in column 22 with its GND.
- **Charger jumpers** (record 4.4 step 3, P3, 1.4), with the charger unpowered and the pack unplugged: on the #4755 the 1A solder jumper is closed and the 0.5A and 1.5A solder jumpers are open. On this pack it's never the 1.5A setting. Record which way EN1 (SJ2) and EN2 (SJ1) are set, and expect **EN2 = 1, EN1 = 0** (the R_ILIM input limit, no VIN-DPM, SLUS810 table 7-2). If EN2 is low, stop and record it. EN2 low holds the USB-C input to the 100 or 500 mA VIN-DPM modes, so C12-C18 and power check 7 never see the 0.8-1.0 A charge. EN1 = EN2 = 1 is standby, with no charge.
- **BOB-14021 preparation** (module preparation, record H5, 7.1 Q6): the BOB-14021 comes as a panel of two boards. Separate it into its two boards first (BOBW for the wind cable, BOBR for the rain cable). Then solder one PRT-00132 jack and one 6-pin header onto each board before it goes into the breadboard. Then do the per-conductor continuity check with the Fluke 87V on continuity and the meter's cable plugged into the jack:
  - BOBW pins 3 and 4 close and open as the cups turn.
  - BOBW pins 2 and 5 read a resistance that changes with the vane's position.
  - BOBR pins 3 and 4 close as the bucket tips.
  - Pins 1 and 6 read open to every other pin.
  - Never cut the meter cables.
- **3V3, not 5 V:** W13 goes to CN6.4 (3V3). The next pin on the Arduino power header, CN6.5, is 5 V. Check the hole against UM2592 Table 17 before you push the wire in.
- **NO 5V tape** (record N3): put Kapton labelled "NO 5V" over CN6.5, CN6.8 (sockets) and CN7.18, CN7.24, CN7.6, CN10.8 (pins). CN6.2 (IOREF) and CN5.8 (AVDD) stay empty.
- **Rails:** some 830-point boards split each rail at the centre. If yours do, set `split_rails = true` in `source/wiring.toml` and regenerate. The plan then bridges the halves.
- **NUCLEO headers:** the positions follow the wiring guide. Tick its section 6 checklist against UM2592 first. The drawing of the headers isn't to scale.
- **CN5 (D8-D15), CN8 (A0-A5) and CN9 (D0-D7):** W18 to CN5.9 (D14, PA11, I2C_SDA), W17 to CN5.10 (D15, PA12, I2C_SCL), W19 to CN8.1 (A0, PB1, ISET), W27 to CN8.2 (A1, PB2, VANE), W28 to CN8.3 (A2, PA10, VIN_SENSE), W25 to CN9.6 (D5, PB8, PGOOD), W14 to CN9.7 (D6, PB10, CHG). All three are female ARDUINO headers, so use solid 22 AWG male ends (record H3, N3). Check each pin against UM2592 Table 17 before you push the wire in. The morpho aliases of these pins (CN7.28, CN7.30, CN7.32, CN10.3, CN10.5, CN10.25, CN10.27) stay empty, so each MCU pin has one landing (record N1).
- **Morpho signal pins:** W15 to CN10.14 (PC0, CUPS), W26 to CN10.29 (PB5, RAIN). The morpho pins are male, so each one takes a female-to-male Dupont jumper: the female end on the pin, the male end in the breadboard hole. You can't push a solid wire onto a male pin. Check each pin against UM2592 Table 18 before you fit the lead. Their ARDUINO aliases (CN9.5) stay empty, so each MCU pin has one landing (record N1).
- **OLED wires:** W20, W21, W22, W23, W24 run from board C to CN10 as female-to-male jumpers of about 30 cm. Their ARDUINO aliases (CN5.1, CN5.3, CN5.4, CN5.6, CN9.8) stay empty, so each MCU pin has one landing (record N1). The OLED's supply pair goes straight to the NUCLEO and stays off every breadboard rail (record N3): L_OLED_VCC (NUCLEO CN7.16 to C:c23) and L_OLED_GND (NUCLEO CN10.20 to C:c22). In mode B unplug the OLED's VCC lead from CN7.16 (section 7). If you don't, the display draws its 50-150 mA through the regulator chain.

## Power checks

These are the phase A power checks (spec `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` section 11.1, as the build-progression record amends it). Do them in this order. Each check names the section 6 rows it shares.

**The model comes first.** Put a measured or fitted value into `source/wiring.toml` before the firmware, because D3 checks 8 and 9 (`make.py sheet`) hold the firmware to the model:

- check 2's R_ISET goes in as the charger's `iset_ohms`
- R4-R6, each measured (record 4.4 step 12), go in as their `measured_ohms`
- the M2 ISET gain fit (4.4 step 11) goes in as the charger's `iset_gain_ppm`

Then put the same value into `firmware/stage0-node/App/power_config.h` (`POWER_R_ISET_OHM`, `POWER_VIN_DIVIDER_PPM`, `POWER_ISET_GAIN_PPM`), benchlink's `VIN_DIVIDER_PPM` and `tools/benchlink_log.py`'s `R_ISET_OHM` and `ISET_GAIN`. Regenerate this sheet, and commit all of it in one commit. Check 3's value goes in only if the shunt fails its check. Commit a measured value before you flash the build that carries it. A build from a dirty tree reports firmware build ID 0, "not identified" (spec section 8.6).

1. **Before power, no VBUS lead fitted** (pre-run check C1): on the INA228, X1.2 (VBUS) to X1.3 (VIN+) and X1.2 to X1.1 (VIN-) read open (SJ1, the back VBUS-to-VIN+ jumper, is open). Then fit the L_VBUS sense lead into the OUT joint (WAGO_SYS_OUT position 3).
2. **R_ISET** (C16): with the charger unpowered and the pack unplugged, measure ISET to GND: R9, 1 kOhm expected (POWER_R_ISET_OHM 1000), behind the closed 1A jumper. With KISET at 890 A*ohm that gives about 0.89 A. If you read anything else, put it in the model as the charger's `iset_ohms` first, then in `POWER_R_ISET_OHM` and the logger's `R_ISET_OHM` (see above). The charge current from ISET is I = 400 x V_ISET / R_ISET. The ISET monitor is 1/400 of the charge current, +-10 % (SLUS810 section 9.3.5.1), plus R_ISET's own tolerance.
3. **Shunt** (C5): verified, not measured (spec section 8.6, record M1). At a steady current, the INA228 battery current agrees within 2 % + 2 mA with the Fluke 87V in series (its A input for about 1 A, its mA input, 400 mA, for the 38 mA load). Only if the shunt fails does a reference-derived value replace the nominal 15 mOhm (1 %). Take that value from the meter's mV across the shunt's Kelvin points over the series A, never an ohm range. To fit the meter:
   - Use the meter in series only for a short steady window, and never during a termination run or the battery-path checks (7, C12-C14). Its current shunt adds about 30 mOhm on the A input and about 1.8 ohm on the mA input (Fluke burden voltage 0.03 V/A and 1.8 mV/mA, typical).
   - Unplug the pack while the meter goes in and comes out.
   - Splice the meter into the pack + lead at CELL+ position 1.
   - Clip the meter's two leads to short 22 AWG solid stubs. The pack red lead and one stub go in a spare 222-413, and the other stub goes in position 1.
4. **ISET and VIN_SENSE before the pack** (W19 and W28): with the wall adapter on and the pack unplugged, VIN_SENSE (CN8.3; alias CN7.32) x the measured ratio (POWER_VIN_DIVIDER_PPM / 1e6) agrees with the meter on VBUS within 1 %. The ratio comes from R4-R6, each measured and held in the model as `measured_ohms` (record M2). ISET (CN8.1; alias CN7.28) reads near 0 V with no charge current.
5. **TS:** with input power present, THERM to GND reads about 0.75 V at 25 C (the 10 kOhm NTC at 75 uA). If it reads about 0.375 V, the breakout's fixed 10 kOhm TS resistor (R10, the THERM jumper) is still in parallel. Cut it.
6. **CHG and PGOOD released** (W14 and W25, C17): with the charge done, with the input removed for a moment and with the firmware's internal pull-ups on, PB10 (CHG: CN9.7; alias CN10.25) and PB8 (PGOOD: CN9.6; alias CN10.27) both read at or below min(VDD, VDDA) + 0.3 V. Above that the internal pull-ups must be off (DS13293 table 26 note 3, record N4). The LED anodes are on OUT (schematic), so a released pin sits near OUT - Vf. It measured 2.9 V on 2026-10-28/29, under the VDD + 0.3 V rule (3.6 V). Measure it again at each step.
7. **Battery path** (C12-C14, section 5): in the first 10 minutes of a CC charge, with the INA228 current I between 0.8 and 1.0 A, take each span's mV drop on the meter and divide it by I (spec section 11.2, record P8). The limits are:
   - the + span (PATH_POS: pack plug +, back-probed, to the charger's header LIPO, with the 15 mOhm shunt in it): at most 75 mOhm
   - the - span (PATH_NEG: header GND to pack plug -, back-probed): at most 40 mOhm
   - each pack-side span (PATH_PACK_POS: pack plug + to the CELL+ clamp, and PATH_PACK_NEG: the STAR clamp to pack plug -): at most 28 mOhm, with their sum recorded as R_pack
   - each JST PH mating: at most 20 mOhm
   - each lever clamp to clamp, and each screw: at most 5 mOhm

   The leads of PATH_POS and PATH_NEG are about 37 mOhm of copper (L_PACK_POS, L_CELL_INA, L_INA_BATT, L_BATT_POS, L_BATT_NEG, L_PACK_NEG, from their gauge and length). A 0.2 ohm breadboard path ended 1 A charges early on 2026-10-28.
8. **Gauge** (C10, C14, step 1 exit 5, record R-2): at rest or at the 38 mA load, the gauge VCELL is within 10 mV of the meter at the pack plug. At a 1 A charge, the gauge VCELL is within 10 mV of the meter at the gauge's own sense points (the CELL+ clamp to the STAR clamp). Also record the pack-plug difference (gauge VCELL - the meter at the pack plug). It must be at or below I x R_pack + 10 mV (R_pack from C14).
9. **INA VBUS = OUT, and SJ1 really open:** during a charge with the pack below 4.1 V, OUT (`load_mv`, the INA228 VBUS) reads 4.3-4.5 V. It also reads at least 100 mV above the gauge VCELL. A closed SJ1 ties the cell to OUT and fails this check.
10. **TMR and termination** (record P9): with the charger unpowered, TMR reads 0 ohm to GND. The schematic ties it to GND, so all safety timers are disabled and the charge may start from any cell voltage. A charge at the 1A jumper then ends with CHG off and steady, not flashing. At that point the INA228 battery current is 0.20-0.40 A (ITERM about 0.3 A) and the cell (gauge VCELL - I x R_pack) is at 4.12 V or more. If CHG flashes at about 2 Hz, the safety timers expired (SLUS810 table 9-2). With TMR at GND that shouldn't happen, so check TMR and the CHG lead. If the board in hand has TMR floating (default 4-6 h), record it and start the charge at 3.85 V or more, since no RTMR is fitted (record P9).

## Step 1b power checks

Step 1b, on the breadboard build (record S1), covers the load, solar and USB-C INA228s and the board's own D2/D4 OR pair (record P10). Do these checks before the node runs profile B (`WS_POWER_PROFILE=2`). This sheet doesn't draw step 1b, because the model doesn't hold its wiring yet. Checks 1-10 still hold.

B1. **EN1 and EN2** (charger unpowered): record both solder jumpers of the #4755 again, SJ2 (EN1) and SJ1 (EN2), as you first did in the step 1 bench check "Charger jumpers". The design needs **EN2 high and EN1 low**: the R_ILIM input limit, no VIN-DPM (SLUS810 table 7-2). EN1 = EN2 = high is standby, with no charge. If EN2 is low, stop and record it (record 1.4, P10). EN2 low means a 100 or 500 mA input limit with VIN-DPM.

B2. **Addresses:** the i2cscan bus scan lists 0x40 battery, 0x41 load, 0x45 solar and 0x48 USB-C (`power_config.h` `POWER_ADDR_*`). Each of 0x41, 0x45 and 0x48 has an `#rail` line. 0x48 is the ADDR1-to-SDA wire, allowed as INA228 module preparation (7.1 Q1). Scope SDA against SCL on this bus: data hold is at least 100 ns after the address MSB (spec R15).

B3. **Rail shunts:** verified, not measured, like check 3. At a steady current on each rail, the INA228 current agrees within 2 % + 2 mA with the Fluke 87V in series in that rail's + lead at its lever joint. Use the load INA228 with the 100 ohm load, and the solar and USB-C INA228s each during a charge from that source alone. Read the INA228 current from the i2cscan `#rail` line, or from the node's `load_current_ma`, `solar_current_ma` and `usb_current_ma`. Keep the meter in for the same short steady window as check 3. Only a rail that fails gets its reference-derived value in `power_config.h` (`POWER_SHUNT_UOHM_LOAD`, `_SOLAR`, `_USB`).

B4. **Bus pull-up** (exit f): with the bus idle and unpowered, SDA to 3V3 and SCL to 3V3 each read 0.97 kOhm or more. Record the measured value (about nine 10 kOhm boards in parallel, power-metering.md section 7). With the bus idle and powered, SDA high reads 2.8 V or more (the 0x48 board's 10 kOhm ADDR1 pull-down stays on SDA, record 1.4).

B5. **One source at a time** (exit e): never solar and USB-C together. First run solar alone, with the wall adapter unplugged at the mains end. The USB-C INA228 reads |I| <= 1 mA. With a 10 kOhm test load across the idle USB-C input, that input reads <= 0.5 V (D2 blocking). Then do the same with USB-C alone and the panel unplugged at its adapter. The solar INA228 reads |I| <= 1 mA, and the idle solar input, with the same 10 kOhm load, reads <= 0.5 V (D4 blocking). The live source's INA228 VBUS reads the source. `charger_input_mv` reads it less one Schottky drop, about 0.3-0.5 V and smaller at low current (the SK34A's VF is 0.55 V max at 3 A). Record the drop you measure.

B6. **A weak source with EN2 high** (power-metering.md section 5.4): feed a bench supply at 7 V into the DC jack through the solar INA228, with its current limit at 0.3 A, then 0.1 A, and the cell at about 3.7 V. Record if PGOOD and CHG hold steady or cycle, and record `charger_input_mv`.
