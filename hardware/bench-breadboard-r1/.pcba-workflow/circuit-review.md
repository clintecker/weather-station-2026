# Circuit review

- Project: weather station 2026, breadboard bench r1
- Revision: r1-draft (schematic generated 2026-11-02)
- Status: `PASS` for the layout step (2026-11-02): no critical or major finding left open, every automated check passes, and decisions D1-D4 are approved and in the model. **First power-up is still gated** on the bench measurements under Verification (`[TBD-MEASURE]`); they need the parts in hand.
- Electrical source of truth: `hardware/bench-breadboard-r1/schematic/model.py`. The schematic `bench-r1.kicad_sch` is generated from it by `kicad_gen.py`. `run.sh` regenerates the schematic, runs KiCad 10.0.7 ERC, exports the netlist, runs `checks.py` and writes `bench-r1.pdf`.
- Reviewed evidence:
  - TI SLUS810N (bq24074); TI SLYS021A (INA228); ADI MAX17048 rev 7; ST DS13293 rev 5; ST UM2592 rev 2 (third-party copy, revision to confirm against st.com); Pololu #2122 page; SSD1325 rev 2.3.
  - Adafruit Eagle files for #4755, #5832, #5580, #4090, #5978 and the QT sensors; SparkFun RJ11_Breakout; SEN-15901 datasheet.
  - Firmware `power_config.h`, `board_inputs.c`, `i2c_bus.c`, `i2cscan/App/oled.h`; `docs/current-system.md`.

## Operating principle

Either a USB-C wall adapter or a solar panel (never both) feeds the bq24074 charger through a metering detour. Each source's cable is broken by a pair of breakouts (#4090/#5978 or #368/#369) so an INA228 can sit in series before the charger's input Schottky diode.

The charger keeps OUT regulated at 4.4 V while an input is present. It charges the 1S3P pack at up to 0.89 A, and the pack's positive lead passes through the battery INA228. With no input, OUT follows the pack through the charger's internal FET.

OUT feeds a LOAD node through the load INA228. In mode A, LOAD drives a 100 Ω test load while the NUCLEO runs from its own USB. In mode B, LOAD feeds the S7V8F3 regulator, whose 3.3 V enters the NUCLEO's 3V3 pin through the BATTERY link, with the NUCLEO's JP4 removed.

The TX NUCLEO reads:
- every sensor and power monitor over one I²C2 bus (two QT branches);
- the charger's PGOOD and CHG pins, its ISET current monitor and its input voltage (through a 3:1 divider);
- the three weather-meter reed and resistor inputs.

It sends the readings over LoRa to the RX NUCLEO, which bridges them to the Mac over USB.

There are two grounds. Power ground is the STAR WAGO at pack negative. Logic ground covers the MCU, the QT parts and the signal returns. They meet through one 22 AWG tie.

## Functional blocks and component roles

| Ref | Part | Role |
|---|---|---|
| PS1, PV1 | wall adapter, P110 panel | sources (off the plate) |
| J3, P1 | #4090, #5978 | USB-C cable broken into screw/solder halves; J3's 5.1 kΩ Rd keeps the adapter's VBUS on |
| J4, P2 | #368, #369 | barrel cable broken into screw halves |
| U1 | #4755 bq24074 | charger and power path; ILIM mode (EN2 HI, EN1 LO, as shipped), R_ISET 1 kΩ, TMR at GND |
| U2-U5 | #5832 INA228 | battery (0x40), load (0x41), solar (0x45), USB-C (0x48) rails |
| U6 | #5580 MAX17048 | cell voltage and SOC; chip powered from BAT+ (SJ2 default) |
| WG1-WG3 | WAGO 222-415 | CELL+, STAR and LOAD nodes |
| W1 | 22 AWG ≤ 100 mm | the one power-to-logic ground tie |
| R9 | 100 Ω ½ W | mode-A test load |
| U7 | S7V8F3 | 3.3 V in mode B |
| JP1, JP2 | 2-pin headers | BATTERY link (mode B), OLED link |
| R4-R6 | 3 × 10 k | VBUS 3:1 divider to PA10 |
| R7, R8, C4 | 10 k, 1 M, 100 nF | ISET network to PB1 |
| J1, J2, M1, M2, R1-R3, C2, C3 | RJ11 breakouts, meter, pull-ups, filters | cups PB5, vane PB2, rain PB4 |
| W2, W3, U8, U9-U12 | QT-to-header cables, 5-port hub, SHT45, SHTC3, BMP581, LTR390 | sensor branch and power branch |
| DS1, C1 | #2674 OLED, 220 µF | SPI1 display |
| A1, A2, H1 | TX NUCLEO, RX NUCLEO, Mac | MCUs and host |

## Power tree and budget

```
PS1 5 V ─ J3 ─ U5 shunt ─ P1 ─┐                  ┌─ BATT ─ U2 shunt ─ CELL+ ─ BT1 (+ U6 sense)
                               ├─ D2/D4 ─ IN ─ U1 ┤
PV1 6 V ─ J4 ─ U4 shunt ─ P2 ─┘                  └─ OUT 4.4 V ─ U3 shunt ─ LOAD ─┬─ R9 (mode A)
                                                                                  └─ U7 ─ JP1 ─ 3V3 (mode B)
Mac USB ─ A1 ST-LINK ─ JP4 ─ LD39050 ─ 3V3 (mode A)
3V3 ─ QT sensors, INA228 VS, meter pull-ups, JP2 ─ OLED
```

| Load on 3V3 | Typical | Peak | Source |
|---|---|---|---|
| STM32WL55 + radio at 0 dBm (bench) | ~10 mA | ~25 mA TX | `[TBD-MEASURE]`; +22 dBm (rangetest) up to ~120 mA |
| 4 × INA228 | 2.6 mA | 3.0 mA | SLYS021A 640/750 µA |
| QT sensors and pull-up LEDs | ~3 mA | ~5 mA | inferred |
| OLED | 50 mA | 150 mA | Adafruit #2674 |
| **Total** | **~66 mA** | **~185 mA** (~280 mA at +22 dBm) | |

| Supply | Capacity | Margin |
|---|---|---|
| S7V8F3 (mode B) | 1 A at VIN > 3.3 V | large; at VIN 3.0 V (boost) the derating is shown only as a graph `[TBD-MEASURE]` |
| NUCLEO LD39050 (mode A) | 500 mA; USB switch U5 limits at 500 mA | large |
| bq24074 OUT | charge 0.89 A + load ≤ 0.2 A from the input, ILIM 1.5-1.72 A | input current stays ≤ ~1.2 A, under ILIM |
| R9 | 4.5² / 100 = 0.20 W on a ½ W part | 2.5× |
| INA228 shunts | 15 mΩ × 1.7² = 43 mW on 2 W | large |

## Voltage domains and interfaces

| Net | Worst case | Tightest pin limit on it | Margin / basis |
|---|---|---|---|
| SOLAR_IN/CHG, CHGR_VBUS | 8.7 V (cold Voc) | bq24074 OVP 10.2 V min | 1.5 V |
| USB_IN/CHG | 5.5 V | bq24074 IN | ok |
| SYS_OUT, LOAD | 4.5 V (VO(REG) max) | S7V8F3 11.8 V | ok |
| CELL_P, BATT | 4.2 V | MAX17048 VDD 4.5 V; bq24074 BAT 5 V abs | 0.3 V |
| VIN_SENSE (PA10) | 2.9 V (8.7 / 3) | ADC range VDDA 3.3 V; FT_fa 5.5 V | 0.4 V; unpowered MCU: 3.9 V abs |
| ISET_NODE (PB1) | 2.42 V (0.975 A / 400 × 1 kΩ × 0.99) | ADC 3.3 V | ok |
| PGOOD (PB8), CHG (PB10) | 3.1 V (OUT 4.5 V less the LED's ~1.4 V at µA) | 3.6 V (pull-up on: VDD + 0.3 V); unpowered MCU 3.9 V abs | 0.5 V; `[TBD-MEASURE]` on the panel |
| I2C_SDA/SCL, CUPS, RAIN, VANE | 3.3 V | 3.6 V | ok |
| OLED inputs | 3.3 V | VDD + 0.3 V = 3.6 V (with the OLED powered) | see F10 |

I²C: nine 10 kΩ pull-ups in parallel give 1.11 kΩ. At VOL 0.4 V the sink current is 2.6 mA, plus 0.07 mA for the MCU's internal pull-ups, against the INA228's VOL spec of 0.4 V at 3 mA. That's a 10 % margin. VIH: the INA228 needs ≥ 1.2 V and the MAX17048 ≥ 1.4 V. The 0x48 strap (A1 to SDA) needs 100 ns of extra hold, which the firmware gives (SDADEL = 2, 146 ns).

## Operating states, reset, and ownership

| State | JP4 (NUCLEO) | JP1 | TX USB | R9 | JP2 | +3V3 source (check 8) |
|---|---|---|---|---|---|---|
| A, daily | on [1-2] | off | in | in | on | LD39050 |
| B, power test | **off** | on | in (D4) | out | off | S7V8F3 |
| B + OLED | off | on | in (D4) | out | on | S7V8F3 |
| Both sources at once | on | on | in | | | **impossible** with D3 (one shunt serves JP4 and JP1) |
| Charger only, MCU off | off | off | out | any | any | none: the MCU is unpowered, while PB8/PB10/PA10 still see ≤ 3.1 V / 2.9 V (abs 3.9 V) |

Firmware not running (reset or held in boot): every MCU station pin is a high-impedance input. Inputs that could float (vane, cups, rain) are pulled up externally. CHG and PGOOD float up to ≤ 3.1 V through the LEDs. ISET is held down by 1 MΩ. Nothing on the bench depends on firmware to be safe. PA9 (the "sensor power" pin) is unconnected.

Bus ownership: there is one I²C master (A1). The MAX17048 runs from the cell even when 3V3 is off. When the bus pull-ups lose power it sees SDA and SCL low, and after 2.5 s it shuts down; it wakes on the next bus activity (no hazard).

## Timing and signal integrity

I²C at 100 kHz over about 1 m of QT cable plus nine boards: estimated capacitance well under 400 pF, and the rise time with 1.11 kΩ is about 0.4 µs against 1 µs allowed. SPI to the OLED at ≤ 1 MHz over Dupont leads of ≤ 150 mm `[TARGET]`. The ADC sources (6.67 kΩ divider, 100 nF ISET node, ≤ 10 kΩ vane) are all inside the 50 kΩ limit at 160.5 cycles. Cups debounce: 10 k × 100 nF = 1 ms, plus the LPTIM filter.

## Protection, thermal, and mechanics

- Pack: the #353's own protection circuit, plus the bq24074's OUT short-circuit detection (VBAT − VOUT > 250 mV). There is no fuse in the pack lead (F13).
- Inputs: the charger's OVP is 10.2 V minimum, its IN absolute maximum 28 V, and the D2/D4 Schottkys block back-feed between the two inputs.
- Thermal: on solar at 6 V and 0.9 A, the bq24074 dissipates (6.0 − 3.7) × 0.9 ≈ 2 W and will hit thermal regulation at 125 °C. That is expected on a warm panel; ventilate the charger `[TARGET]`.
- The S7V8F3 has no reverse-polarity protection, and the pack's JST colours vary (F12).

## Layout handoff constraints

- `[SPEC]` Force nets (USB_IN, USB_CHG, USB_RET, SOLAR_IN, SOLAR_CHG, SOLAR_RET, CELL_P, BATT, SYS_OUT, LOAD, PGND) use only screw, WAGO, JST, solder, USB and barrel contacts. The one exemption is U7.VIN on LOAD (mode B regulator chain). Checked by check 4.
- `[SPEC]` Exactly one conductor (W1, ≤ 100 mm) between STAR and logic ground. The #4755 header GND pins, the INA228 and MAX17048 header GND/VCC, and the gauge and SYSOUT pigtail black leads are not wired to logic ground. Checked by check 3.
- `[SPEC]` The gauge sense lead and each INA228 VBUS sense lead get their own WAGO lever, never sharing a clamp with a force lead or bundled along one.
- `[SPEC]` The OLED GND runs on its own wire to CN10.20. Its 3V3 comes from CN7.16 through JP2.
- `[SPEC]` Meter pull-ups and filters sit at the RJ11 breakouts.
- `[TARGET]` Lead lengths: pigtail halves ≤ 60 mm; solid force links ≤ 50 mm; regulator supply and tie ≤ 100 mm. At 1 A: + span ≤ 75 mΩ, − span ≤ 40 mΩ, each JST mating ≤ 20 mΩ, each clamp ≤ 5 mΩ.
- `[TARGET]` The ISET 10 k sits at the charger end, as close to header pin 8 as possible.
- `[TARGET]` Tape the NUCLEO's 5 V pins (CN6.5, CN6.8, CN7.18, CN7.24, CN7.6, CN10.8).
- `[TBD-MEASURE]` Before first power: the items in "Verification" below.

## Findings

| ID | Severity | Evidence | Consequence | Action | Gate | Status |
|---|---|---|---|---|---|---|
| F1 | major | UM2592 §6.4 and Fig. 15: an external 3V3 needs JP4 removed. The old mode-B procedure (BSW:305-326) left JP4 at its default [1-2]. | In mode B the LD39050's output is back-driven from the S7V8F3 with its input floating (reverse current unspecified). With USB plugged in and JP4 on, two regulators fight on 3V3. | D3: one jumper cap serves both JP4 [1-2] and JP1, so the two can never both be fitted. Check 8 proves it. | mode B | fixed by D3 (approved) |
| F2 | major (unknown) | UM2592 (end of the STD_ALONE_5V subsection): with the ST-LINK unpowered, remove JP7 and the six JP8 jumpers to isolate it | In mode B with USB out, MCU outputs (VCP TX on PA2, SWD) feed the unpowered ST-LINK. That phantom-powers it, adds current to the load rail and may disturb it. | D4: either keep the TX USB plugged in during mode B (ST-LINK powered by the Mac, target from the battery, JP4 off: also gives a console), or remove JP7 and JP8 | mode B | fixed by D4 (approved); `[TBD-MEASURE]` no current from USB into 3V3 with JP4 off |
| F3 | minor | SLUS810 §9.3.6: TS is referred to the charger's own GND, which sits about 40 mV from STAR at a 1 A charge (BSW:238-241) | 40 mV TS error: cold trip +0.4 °C, hot trip +3.8 °C | D2: return the NTC to the #4755 header GND (power domain, 75 µA, nothing on the logic side). Check 3 still finds one tie. | layout | fixed by D2 (approved); check 3: still one tie |
| F4 | information | #5832 schematic: SJ1 bridges VBUS to VIN+. On U2, U4 and U5 the VBUS sense point *is* VIN+. | Three sense leads and three WAGO levers that could be avoided | D1: close SJ1 on U2, U4 and U5; keep it open on U3 (VBUS on LOAD). Label each board. | layout | fixed by D1 (approved); check 2 fails if a closed-SJ1 board's VBUS terminal is wired |
| F5 | minor | #4755 R_ILIM 1 kΩ, below TI's 1.1-8 kΩ; ILIM is 1.61 A typical, at the IN absolute maximum of 1.6 A | Harmless at I_CHG 0.89 A (input ≤ 1.2 A). Selecting the 1.5 A ISET jumper would push the input to the limit. | `[SPEC]` keep the "1A" ISET jumper; adapter ≥ 2 A | — | rule recorded |
| F6 | information | SLUS810 §9.3.4.1.1: VIN-DPM works only with EN2 LO; the board ships EN2 HI (ILIM), which phase B requires | At low sun the panel collapses toward UVLO and PGOOD/CHG cycle (PM:246-271), with no VIN-DPM to hold it | expected behaviour; log it in solar tests | — | accepted |
| F7 | information | #4755 schematic: TMR at GND (timers disabled), CE 10 k to GND, EN1 LO / EN2 HI as shipped | closes current-system 9.1 #1 and #5 by schematic | confirm the jumpers by eye | — | closed pending visual check |
| F8 | information | SLUS810: OUT regulated to 4.4 V (4.5 V max) with any input; the LEDs pull CHG/PGOOD from OUT | released pins ≤ ~3.1 V < 3.6 V; ≤ 3.9 V abs with the MCU unpowered | closes 9.1 #9 by analysis | — | `[TBD-MEASURE]` once on the panel |
| F9 | minor | nine 10 k pull-ups = 1.11 kΩ; INA228 VOL rated at 3 mA | 10 % margin on the sink current | no more pulled-up breakouts on this bus; check 5 enforces ≥ 0.97 kΩ | — | accepted |
| F10 | minor | SSD1325: inputs ≤ VDD + 0.3 V. JP2 removes the OLED's VDD. | Driving the OLED pins with JP2 open back-powers the panel through its inputs. Fitting JP2 live dumps 220 µF onto 3V3 and can reset the MCU. | `[SPEC]` the firmware drives the OLED pins only with JP2 fitted; move JP2 only with the bench unpowered | firmware, ops | rule recorded |
| F11 | information (unknown) | SSD1325 rev 2.3 needs an external 8-16 V panel supply; Adafruit says the module has an on-board boost; no module schematic | if wrong, the display stays dark (no hazard) | it has run under i2cscan before? confirm | — | open |
| F12 | minor | Pololu: no reverse-polarity protection; #353 JST colours vary (WT:323) | a reversed pigtail kills U7, and stresses the INA228 and the charger | `[TBD-MEASURE]` check the pigtail polarity with the 87V before the first mating | build | rule recorded |
| F13 | information | no fuse in the pack lead | a CELL+ short is limited only by the pack's protection circuit | acceptable on the bench; cover unused WAGO levers; consider an inline 2 A fuse later | — | accepted |
| F14 | information | MAX17048 rev 7 Note 6 | the gauge sleeps when the bus pull-ups lose power, and wakes on traffic | none | — | accepted |
| F15 | information | ground check (check 3): USB_RET and SOLAR_RET join PGND inside the #4755 | an earthed adapter would form a second tie through the Mac's earth | `[SPEC]` the adapter must be floating (class II) | — | rule recorded |
| F16 | minor (unknown) | #4755 DC jack size inferred to be 5.5 × 2.1 mm (PM:181) | the #369 may not fit | `[TBD-MEASURE]` test-fit | build | open |

## Approved design decisions and waivers

Approved (block list, 2026-11-02): see `../design.md` sections 1-2.

Approved by the owner 2026-11-02 and applied in `model.py`:
- **D1**: SJ1 closed on U2 (0x40), U4 (0x45) and U5 (0x48); their VBUS terminals stay empty. SJ1 open on U3 (0x41), with its VBUS sense lead to LOAD. Every board labelled with its address and SJ1 state. CELL+ needs only a 3-way WAGO (222-413).
- **D2**: the NTC returns to a #4755 header GND pin (net NTC_RET, power domain). The breadboard row holding it touches nothing else.
- **D3**: one jumper cap serves both NUCLEO JP4 [1-2] (mode A) and the BATTERY link JP1 (mode B).
- **D4**: the TX USB stays plugged in during mode B. The ST-LINK runs from the Mac; with JP4 off, USB cannot power the target. The console and flashing keep working in mode B.

ERC waivers (`model.ERC_WAIVERS`):
- `lib_symbol_issues`: the symbols are embedded in the schematic.
- `pin_not_driven` on PB8 and PB10: open-drain outputs pulled up by the MCU's internal pull-up.

## Verification and unresolved evidence

Automated (`schematic/run.sh`, 2026-11-02): **PASS, 0 failures.** KiCad ERC reports only the waivers. Checks 1-9 pass. Planted defects were caught: a second ground tie, a pack lead through a breadboard row, a duplicate INA228 address, PA10 without its divider, and two 3V3 sources without D3.

Bench measurements before first power (`[TBD-MEASURE]`):
1. **#4755:** THERM jumper cut (TS about 0.75 V at 25 °C); TMR-GND, R_ISET and EN1/EN2 by eye and ohmmeter; DC jack fit (F16).
2. **INA228s:** SJ1 state on each board, matching D1; address jumpers; the 0x48 rework.
3. **Polarity:** the pack and pigtails (F12); the S7V8F3 pin order against its silk.
4. **NUCLEO:** JP4 position; 3V3 measured in modes A and B; with JP4 off and USB in, the current from USB into 3V3 is zero (F2, D4).
5. **On the panel:** released PGOOD/CHG voltage at the highest Voc (F8).
6. **I²C:** bus pull-up ≥ 0.97 kΩ, measured idle and unpowered.

Not reviewed here: the vane voltage table, the cups bounce and the RF link. Those are firmware and bench tests, not circuit questions.
