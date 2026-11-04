# Breadboard bench r1: design record

A from-scratch layout of the whole weather station on breadboards: a development bench that can be
built, debugged and carried in one piece. Facts come from [`docs/current-system.md`](../../docs/current-system.md);
this file records the decisions and the design as it is approved, one step at a time. It does not
build on `hardware/bench-breadboard-r0`.

Status: step 2 (functional block list) approved 2026-11-02. Circuit review before layout: the
schematic is generated from [`schematic/model.py`](schematic/model.py) and checked by
[`schematic/run.sh`](schematic/run.sh); the review is [`.pcba-workflow/circuit-review.md`](.pcba-workflow/circuit-review.md)
(PASS for layout, 2026-11-02; power-up gated on bench checks). Step 3: layout option **B** chosen
(2026-11-02; sketches in [`layout/`](layout/)). Steps 4 and 5 redrafted 2026-11-03 with as much as
possible on the breadboards, awaiting approval: three Elegoo boards (BB2 the four INA228s and the gauge,
BB1 the charger and power signals, BB3 the RJ11 jacks and the OLED), power island between BB2 and BB1,
TX NUCLEO beside BB3; plate 400 x 292 mm. Build data [`layout/build.py`](layout/build.py) (checked
against the schematic); wire routes [`layout/routing.py`](layout/routing.py); KiCad boards and renders
[`layout/kicad_layout.py`](layout/kicad_layout.py) -> [`layout/kicad/`](layout/kicad/); generated
[`layout/wiring-plan.md`](layout/wiring-plan.md) and [`layout/homes.md`](layout/homes.md) (`python3 outputs.py`).

## 1. Decisions (survey, 2026-11-02)

| Topic | Decision |
|---|---|
| Parts | Design around the 2026-11-02 DigiKey order (not yet arrived), plus parts in hand but not in INVENTORY.md: OLED #2674, BOJACK pre-cut jumper kits, 3 Elegoo full-size breadboards (rails continuous), many STEMMA QT cables, a PCA9548 8-port mux #5626 |
| Metering | Phase B: four INA228 (battery 0x40, load 0x41, solar 0x45, USB-C 0x48) + MAX17048 0x36; firmware `WS_POWER_PROFILE=2` |
| Bench power modes | Both: A (NUCLEO on ST-LINK USB, 100 ohm test load) and B (pack -> charger -> S7V8F3 -> NUCLEO 3V3 through a removable link) |
| I2C | Two QT branches from the NUCLEO: sensor branch through the 5-port passive hub; power branch as a QT daisy chain, always powered |
| PCA9548 mux | Not used (default 0x70 collides with the SHTC3; firmware default build has no mux) |
| OLED | Existing SPI1 pins; its VCC goes through a removable link so mode B can run with it on or off |
| Mode-B console | None; watch the node over LoRa on the ws0 dashboard. Serial console in mode A only |
| Extras | No spare SHT45, no W25Q128 |
| On the base plate | Breadboards, both NUCLEOs, the pack, RJ11 jacks at the plate edge. Solar panel and wall adapter stay off the plate as cable entries |
| USB exits | TX and RX ST-LINK cables leave towards the back edge; the charger's adapter input enters from the **left** edge beside the solar plug (J3 above J4, amended 2026-11-04: BB2 fills the back-left corner) |
| Charger | Adafruit #4755 bq24074, both of its own inputs used: the #5978 plug goes into its USB-C, the #369 plug into its DC jack |
| D1 INA228 SJ1 | closed on battery 0x40, solar 0x45, USB-C 0x48 (VBUS = VIN+ on the board, terminal empty); open on load 0x41 with a sense lead to LOAD; boards labelled |
| D2 NTC return | to a #4755 header GND pin (power ground, 75 uA), not logic ground: removes the 40 mV TS offset at 1 A |
| D3 Mode switch | one jumper cap, on NUCLEO JP4 [1-2] in mode A or on the BATTERY link in mode B (UM2592 6.4: JP4 off for external 3V3) |
| On the breadboards (2026-11-03) | as much as possible: #4755 charger by its header (force current stays on its sockets and jacks; LIPO/OUT/GND strips kept empty); four INA228 and the MAX17048 by their headers, I2C still on the QT chain (header VIN+/VIN-/VBUS strips reserved); OLED by its 20-pin header. Sensors stay on QT + the 5-port hub. NUCLEOs, WAGOs, pack stay off |
| Breadboard geometry (photos 2026-11-03) | Elegoo, rails continuous; row-a side: - inner, + outer; row-j side: + inner, - outer; rail holes in groups of five beside columns 3-7, 9-13 ... 57-61 |
| Pinouts confirmed (photos 2026-11-03) | #4755 header VBUS, GND, THERM, ISET, CE, PGOOD, CHG, OUT, GND, LIPO, GND; DC jack above USB-C on one edge, Load Out above LiPo Batt on the other. INA228 header (terminal block opposite) ALRT, VIN+, VIN-, VBUS, SDA, SCL, GND, VIN. MAX17048 header VIN, GND, SCL, SDA, INT, QStart, JST sockets opposite. S7V8F3 4 pins on one edge, left to right with the board standing above its pins: VOUT, GND, VIN, SHDN (board in hand, 2026-11-04; side pads are capacitors). Sensors stay on the 5-port hub, not a chain (2026-11-03). All match build.py; header pin pitch positions still [TBD-MEASURE] |
| D4 Mode-B USB | TX USB stays plugged in during mode B: ST-LINK powered by the Mac, target by the battery; console works in mode B |

## 2. Functional block list (approved)

### A. Power island (force currents up to about 1.5 A; never through breadboard contacts)

| From | Conductor | To | Current | Meter |
|---|---|---|---|---|
| Wall adapter (USB-C, floating 5 V) | USB-C cable | #4090 female breakout (its 5.1 kohm CC pull-downs make the adapter turn on VBUS) | <= 1.5 A | — |
| #4090 VBUS | solder -> INA228 0x48 VIN+ -> VIN- | #5978 male plug VBUS -> #4755 USB-C | <= 1.5 A | USB-C rail, VBUS = USB_IN through SJ1 (D1) |
| #4090 GND | direct wire | #5978 GND (CC and data open on the #5978) | return | — |
| Solar panel | barrel plug | #368 jack-to-screw | <= about 1.7 A | — |
| #368 + | INA228 0x45 VIN+ -> VIN- | #369 plug + -> #4755 DC jack | <= about 1.7 A | solar rail, VBUS = SOLAR_IN through SJ1 (D1) |
| #368 - | direct wire | #369 - | return | — |
| Pack + (JST PH) | pigtail -> WAGO CELL+ -> INA228 0x40 VIN+ -> VIN- -> pigtail | #4755 BATT socket + | +/-1 A | battery rail, VBUS = CELL+ through SJ1 (D1; host cross-check only) |
| Pack - (JST PH) | pigtail -> WAGO STAR | #4755 BATT socket - | return | — |
| #4755 SYSOUT socket + | pigtail -> INA228 0x41 VIN+ -> VIN- -> WAGO LOAD | 100 ohm 1/2 W test load (mode A) or S7V8F3 VIN (mode B) | <= about 150 mA | load rail, SJ1 open, VBUS sense lead to LOAD |
| SYSOUT socket - | insulated, unused | — | — | — |
| Test-load return | wire | WAGO STAR | about 40 mA | — |

### B. Ground: one net, two domains, one tie

| Domain | Members |
|---|---|
| Power ground (WAGO STAR at pack -) | pack -, #4755 BATT -, test-load return, NTC return at a #4755 header GND (D2); source grounds return through the #4755's own input ground |
| Logic ground | NUCLEO GND, every QT cable ground, divider, ISET and meter returns, OLED GND, S7V8F3 GND |
| The tie | one wire <= 100 mm from STAR to S7V8F3 GND, in place in both modes |
| Not wired | #4755 header GND pins (except the one NTC return, D2), INA228 and MAX17048 header GND/VCC, gauge pigtail black lead, SYSOUT pigtail black lead |

### C. Supply rails (milliamps)

| Rail | Source | Feeds | Switch |
|---|---|---|---|
| 3V3 | mode A: NUCLEO ST-LINK USB through JP4; mode B: S7V8F3 VOUT -> BATTERY link (2-pin + the shared cap) -> CN6.4, JP4 off | both QT branches, three meter pull-ups, OLED | BATTERY link |
| OLED 3V3 | CN7.16 | OLED pin 2, 220 uF across it | OLED link (2-pin + shunt) |
| S7V8F3 VIN | WAGO LOAD, lead <= 100 mm | regulator | used in mode B only; the one tolerated breadboard path |
| Regulator return | CN6.7 -> S7V8F3 GND | — | never moves |

Mode change (D3, D4): one jumper cap serves both NUCLEO JP4 [1-2] and the BATTERY link. A -> B: remove
the test load, set the OLED link as wanted (bench unpowered), move the cap from JP4 to the BATTERY link.
B -> A: move the cap back to JP4, refit the load. The TX USB stays plugged in throughout. Never USB-C
adapter and solar together.

### D. I2C2 (PA11 SDA D14, PA12 SCL D15, 100 kHz)

| Branch | Start | Devices | Power |
|---|---|---|---|
| Sensor | QT-to-header cable on D14/D15, 3V3, GND -> 5-port hub | SHT45 0x44, SHTC3 0x70, BMP581 0x47, LTR390 0x53 | 3V3 |
| Power | second QT-to-header cable, same signals -> daisy chain | INA228 0x40 -> 0x41 -> 0x45 -> 0x48 -> MAX17048 0x36 | 3V3, always on |

Address prep: 0x41 A0 jumper to VS; 0x45 both jumpers to VS; 0x48 A1 wired to SDA (rework). SJ1 closed
on 0x40, 0x45, 0x48; open on 0x41 (D1). Pull-ups on the breakouts only: about 1.1 kohm in parallel, pass at >= 0.97 kohm.

### E. Charger signals to the TX MCU (on the breadboard)

| #4755 pin | Network | MCU |
|---|---|---|
| VBUS | 10 k + 10 k -> node -> 10 k -> logic GND | PA10 (A2), ADC |
| ISET | 10 k series at the charger end -> node, 100 nF and 1 Mohm to logic GND | PB1 (A0), ADC |
| PGOOD | direct, MCU internal pull-up | PB8 (D5) |
| CHG | direct, MCU internal pull-up | PB10 (D6) |
| THERM | NTC (taped to the pack) -> a #4755 header GND pin (D2); THERM solder jumper cut | — |
| MAX17048 BAT+ | red pigtail lead to WAGO CELL+ (sense only, never in a force lead's clamp) | over QT |

### F. Weather meter (RJ11 jacks on the plate edge)

| Jack pin | Conditioning, at the jack | MCU |
|---|---|---|
| Wind 4 (cups) | 10 k to 3V3, 100 nF to GND | PB5 (D4), LPTIM1 |
| Wind 5 (vane) | 10 k to 3V3 | PB2 (A1), ADC |
| Wind 2, 3; Rain 3 | logic GND | — |
| Rain 4 (bucket) | 10 k to 3V3, 100 nF to GND | PB4 (A3), EXTI |

### G. OLED (SPI1, write only)

| Signal | MCU |
|---|---|
| SCLK, DIN, CS, DC, RST | PA5, PA7, PA4, PC2, PC1 (morpho CN10.11, .15, .17, .21, .23) |
| GND | CN10.20, its own wire straight to the pin |

### H. NUCLEOs and the Mac

| Board | Connections |
|---|---|
| TX | ST-LINK USB -> Mac (mode A only), all signals above, antenna |
| RX | ST-LINK USB -> its own direct Mac port, nothing else |

## 3. Prep before the build

- Split the BOB-14021 panel; solder both RJ11 jacks and headers.
- INA228 address work: 0x41, 0x45 jumpers; 0x48 A1-to-SDA rework; close SJ1 on 0x40, 0x45, 0x48 (D1); label every board.
  On U5 (0x48) the A1 jumper stays open (bridged, it would tie SDA to VS through the wire). The wire runs
  from the inner (ADDR1) A1 pad on the back, round the ALRT-side edge just above the header, to the SDA
  header joint on the front. Its 10 kΩ ADDR1 pull-down (R6) stays on SDA, as accepted in
  `docs/hardware/power-metering.md` section 7; the build guide's last page checks SDA ≥ 2.8 V and the
  i2cscan addresses. Pad positions from Adafruit's Eagle board file (Adafruit-INA228-PCB, read 2026-11-04).
- #4755: cut the THERM solder jumper; record EN1/EN2 (phase B needs EN2 high, EN1 low).
- Solder VBUS and GND leads to the #4090 and #5978; make up the #368/#369 leads.
- Make the JST PH pigtails (pack, BATT, SYSOUT, gauge sense) from #1131 cables.
