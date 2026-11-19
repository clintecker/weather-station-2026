# Power metering: rails, monitors and phases

Status: design, 2026-10-29. Amended 2026-10-30 to match Clint's answers in the build-progression record.

This is the hardware side of the power telemetry design
([`docs/superpowers/specs/2026-10-29-power-telemetry-design.md`](../superpowers/specs/2026-10-29-power-telemetry-design.md),
"the spec"), section 11.3. It says which monitor measures which rail in each phase and where each
monitor sits. It also gives each monitor's address straps and the limits the hardware puts on the
sources.

Each phase maps to build steps of the build-progression record
([`2026-10-29-build-progression-decisions.md`](../superpowers/specs/2026-10-29-build-progression-decisions.md),
"the record"). Section 1 below gives that mapping. Where this page and the record differ, the record's
section 7.1 (Clint's answers, 2026-10-30) wins. The record's section 5 lists the parts for each step.

Sources read for this page (all as text, never executed):

| Source | Used for |
|---|---|
| TI SLUS810N (bq2407x), revised October 2021 | OVP 10.2-10.8 V (bq24074 row), VIN-DPM 4.35-4.63 V (EN2 = low), section 9.3.4.1.1, termination disabled while VIN-DPM acts (section 9.3.5), ISET (eq. 2, 3, section 9.3.5.1), TMR (section 9.3.5.6) |
| TI INA228 datasheet, the copy read is literature number SLYS021A (May 2022); the spec and `power_config.h` cite it as SBOS904 | address table 7-2, quiescent current (section 6.5), VBUS range, the extra SDA hold time for an SDA strap |
| ST DS13293 Rev 5 (STM32WL55) | pin structure (table 20), I/O input voltage and pull-up note (table 26), ADC source resistance (table 82) |
| Adafruit #5832 (INA228) and #4755 (bq24074) EAGLE schematics, from the `source` links in `hardware/bench-breadboard-r0/source/wiring.toml` | shunt part, solder jumpers, pull-up resistor pack, the charger's input diodes and straps |

## 1. Phases

| Phase | Charger | Monitors | Build steps (record section 3) |
|---|---|---|---|
| **A** | Adafruit bq24074 #4755, one input (VBUS) | battery INA228 0x40, MAX17048 0x36 on CELL+ | step **1** (breadboard v2; change A rebuilds the battery path per record P3, "yes, change A as written", 7.1). H01 runs on the breadboard build. The battery shunt is not yet proven at 1 A (spec section 2, exit criteria 3 and 4) |
| **B** (four rails) | bq24074 | phase A plus load INA228 0x41, solar INA228 0x45, USB-C INA228 0x48 | step **1b**, on the breadboard build (record S1). The INA228 module preparation it needs (A0/A1 jumpers, the 0x48 wire from ADDR1 to SDA) is allowed (7.1 Q1) |

Phase B adds to phase A on the same breadboard build (record S1). The pack is 1S3P in both phases
(record section 1.3): three 2,200 mAh Li-ion cells in parallel, 6,600 mAh, 3.0-4.2 V, 3.7 V nominal.

**History, not the design.** When we first wired phase A on the bench on 2026-10-28/29
([`bench-station-wiring.md`](bench-station-wiring.md) section 4), the pack plugged straight into the
charger's BATT socket. That socket is the LIPO node. So the current skipped the battery shunt, and the
shunt read about zero (record F5). Change A (record section 4.4) retires that wiring. Section 2.1
gives the design.

**USB-C rule.** USB-C is for bench work and occasional backup charging only. It is **never connected
at the same time as solar**, in any phase.

## 2. Rail table

Every INA228 runs with ADCRANGE 0 (±163.84 mV across the shunt) and a current step (CURRENT_LSB) of
10 µA. CURRENT is 20-bit signed, so each rail measures **±5.24 A** (2¹⁹ × 10 µA). CHARGE is a
40-bit signed accumulator. The shunt ADC alone would reach ±10.9 A at 15 mΩ. The bq24074 charges at
most 1.5 A, so 10 µA serves every rail in phases A and B.

A later rail that needs more current raises
its step (20 µA gives ±10.5 A, spec section 9.4). `firmware/stage0-node/App/power_config.h` holds the
same table.

Shunt: the Adafruit #5832's own R1. It's a 15 mΩ, 1 %, 2 W, 2512 resistor (schematic value
"HoLLR2512-2W-15mR-1%"). It dissipates 34 mW at 1.5 A and 0.41 W at the ±5.24 A range limit, well
inside 2 W.

The value in `power_config.h` is nominal and **verified, not measured** (spec section 8.6,
record M1). The check: the battery current must agree with a series reference within 2 % + 2 mA. A
value from the reference replaces the nominal value only if that check fails. A two-wire meter can't
resolve 15 mΩ better than the part's own 1 %.

### 2.1 Phase A

| Rail | Net (from → to) | Monitor | Address, straps (A1, A0) | Shunt | VBUS sense point | Fills |
|---|---|---|---|---|---|---|
| Battery | pack plug → pack-mating half of a cut #1131 → WAGO 222-415 **CELL+** → 22 AWG solid → INA VIN+ (X1.3) → shunt → VIN− (X1.1) → 22 AWG solid → WAGO 222-413 **BATT** → board-mating half of the same #1131 → the charger's BATT socket (record P3). The header LIPO pin is a zero-current test point (record P2) | INA228 #5832 | 0x40, GND, GND (as shipped) | 15 mΩ, 2 W | **OUT** (the WAGO OUT connector on the charger's SYSOUT socket) by its own lead; SJ1 open | battery current, charge and energy counters (with VCELL), load voltage |
| Cell voltage | the CELL+ node: the board-mating half of a second cut #1131 in one MAX17048 socket, its red lead in its own CELL+ position, its black lead insulated; the gauge's ground comes over STEMMA QT (record P4, P5) | MAX17048 #5580 | 0x36 (fixed) | — | CELL+, before the shunt; labelled "CELL+ node, includes the pack-lead drop" (record M4) | battery voltage, SOC, SOC rate |
| Charger input | charger VBUS | PA10 through 20 kΩ / 10 kΩ | — | — | the charger's VBUS header pin (after the breakout's D2/D4 input diodes) | charger input voltage (source not identified) |
| Charge current (charger's view) | charger ISET | PB1 | — | — | ISET pin | charger-reported charge current (health report) |

### 2.2 Phase B

| Rail | Net (from → to) | Monitor | Address, straps (A1, A0) | Shunt | VBUS sense point | Fills |
|---|---|---|---|---|---|---|
| Battery | as phase A | INA228 | 0x40, GND, GND | 15 mΩ, 2 W | its own lead, moved at step 1b from OUT to **CELL+ position 4** (record P5). The node firmware does **not read** it in profile B (the load INA228 owns the load voltage); the host uses it as a cross-check of the cell voltage at CELL+ (spec section 17, record M4) | battery current, counters, energy |
| Load | WAGO OUT → 22 AWG solid → INA VIN+ → shunt → VIN− → solid → a new WAGO 222-415 **LOAD**, which takes the 100 Ω load, the regulator VIN lead L_REG_VIN (moved from OUT; the S7V8F3 and everything behind it) and the load VBUS lead | INA228 | 0x41, GND, VS (A0 jumper closed) | 15 mΩ, 2 W | the **LOAD** joint, by its own lead | load voltage, load current |
| Solar | panel + → INA VIN+ → shunt → VIN− → #369 barrel plug → DC jack → D4 (the joins in section 5.1) | INA228 | 0x45, VS, VS (both jumpers closed) | 15 mΩ, 2 W | the **SOLAR_IN** joint, before the shunt and D4, by its own lead | solar voltage, solar current |
| USB-C | female inline USB-C adapter VBUS → INA VIN+ → shunt → VIN− → male USB-C plug → the breakout's USB-C → D2 (section 5.1) | INA228 | 0x48, SDA, GND (module preparation, section 7) | 15 mΩ, 2 W | the **USB_IN** joint, before the shunt and D2, by its own lead | USB-C voltage, USB-C current |
| Charger input | D2/D4 cathodes → charger VBUS | PA10 divider | — | — | charger VBUS | charger input voltage (a cross-check of the source rails) |

**SJ1 is open on all four INA228s** (record M1, P5). Before you wire each board, check continuity
between X1.2 (VBUS) and X1.3 (VIN+). It must read open. If it reads closed, cut SJ1's trace (record
section 4.4 step 3, check C1).

A closed SJ1 makes VBUS read through the VIN+ clamp, and that clamp
carries the rail current. Each VBUS reaches its sense point on its own 22 AWG solid lead. That's a
sense lead, so never bundle it along a force lead:

| INA228 | VBUS sense lead lands at |
|---|---|
| battery (0x40) | OUT in phase A; CELL+ position 4 from step 1b |
| load (0x41) | LOAD |
| solar (0x45) | SOLAR_IN |
| USB-C (0x48) | USB_IN |

## 3. Sign conventions

| Rail | Positive means | INA228 orientation | Firmware sign |
|---|---|---|---|
| Battery | current **into the cell** (charging) | CELL+ on VIN+, BATT (towards the charger's BATT socket) on VIN−: the part counts VIN+ → VIN− as positive, which is **out of** the cell | −1 |
| Load | current into the load | VIN+ at OUT, VIN− towards the load | +1 |
| Solar, USB-C | current into the station | VIN+ at the source, VIN− towards the join | +1 |

If you swap a pair of shunt leads, you'll see the wrong sign at a known charge or discharge. The
acceptance drill catches this (spec section 12.2).

## 4. Fill table

"Absent" means the build has no source for the value, and the field isn't in the record. "INVALID"
means the source is fitted but failed or is out of range. The firmware never guesses a source.

### 4.1 Every minute (observation)

| Value (field) | A | B |
|---|---|---|
| Battery voltage (`batt_mv`, 11) | MAX17048 VCELL | MAX17048 VCELL |
| Battery current (`batt_current_ma`, 12) | battery INA228, sign −1 | battery INA228 |
| Battery energy and charge (13-16) | battery INA228 ΔQ, split by sign: energy (13, 14) is ΔQ × VCELL, charge (15, 16) is ΔQ alone | as A |
| Load voltage (`load_mv`, 26) | battery INA228 VBUS (on OUT) | load INA228 VBUS |
| Load current (`load_current_ma`, 27) | absent | load INA228 |
| Charger input voltage (`charger_input_mv`, 28) | PA10 × the divider ratio (nominal 3; the measured ratio in `POWER_VIN_DIVIDER_PPM`) | as A |
| Solar voltage (`solar_mv`, 29) | absent | solar INA228 VBUS |
| Solar current (`solar_current_ma`, 30) | absent | solar INA228 |
| USB-C voltage (`usb_mv`, 32) | absent | USB-C INA228 VBUS |
| USB-C current (`usb_current_ma`, 33) | absent | USB-C INA228 |

### 4.2 Every 15 minutes (health report)

| Value (health key) | A | B |
|---|---|---|
| Gauge SOC and rate | MAX17048 | MAX17048 |
| Charger status | PGOOD (PB8), CHG (PB10) | as A |
| Power-monitor die temperature | battery INA228 | hottest of four INA228s |
| MCU supply | VDDA from VREFINT | as A |
| Charger-reported input V and I | not measured | not measured |
| Charger-reported battery V | not measured | not measured |
| Charger-reported charge current | ISET while PGOOD is asserted, 0 mA without PGOOD | as A |
| Charger die temperature | not measured | not measured |
| Pack temperature | not measured (the NTC goes to the charger only) | not measured |

The report's fitted byte tells you what a `null` health value means (spec section 6.1). Phases A and
B send 0x2F. So the report lists the "not measured" rows above in `power_not_measured`. A `null` in a
row they do measure (a dead gauge, a failed ADC) goes in `power_sensor_faults`.

**Phase A can't tell solar from USB-C.** The bq24074 has one input. The breakout's USB-C (X2) and DC
jack (X3) join at VBUS through its own Schottky diodes D2 and D4 (SK34A). No monitor sits upstream of
that join. Phase B puts one monitor in each source's lead, upstream of the join (section 5).

## 5. Phase B: the join

### 5.1 Topology

*Decided 2026-10-29 (spec section 11.3 as amended, section 17; build-progression record P10).* The
#4755 already diode-ORs its two inputs into the charger's IN. USB-C VBUS goes through D2 and the DC
jack goes through D4, both SK34A Schottky. Those two diodes are the phase B OR pair. Each source's
monitor sits in that source's own cable, upstream of the join, so we can tell solar and USB-C current
apart:

| Step | Part | Rule |
|---|---|---|
| 1 | solar + | one 6 V panel's 2.1 mm barrel plug (the panel lead is never cut) → an Adafruit #368 female 2.1 mm DC jack to screw-terminal adapter (L_SOLAR_POS) → 22 AWG solid → WAGO 222-413 **SOLAR_IN** (which also takes the solar INA228's VBUS lead) → solid → the solar INA228's X1 VIN+ |
| 2 | solar INA228 VIN− | → 22 AWG solid → the + terminal of an Adafruit #369 2.1 mm barrel plug → the breakout's DC jack (X3, then D4) |
| 3 | USB-C + | wall adapter → USB-C cable → a female inline USB-C screw-terminal adapter with 5.1 kΩ Rd (section 5.3) → solid → WAGO 222-413 **USB_IN** (which also takes the USB-C INA228's VBUS lead) → solid → VIN+; VIN− → solid → a male USB-C screw-terminal plug → the breakout's own USB-C (X2, then D2) |
| 4 | source returns | the #368's − straight to the #369's − terminal (L_SOLAR_NEG); the USB-C female adapter's GND straight to the male plug's GND; through the breakout's own connectors from there. The monitors' GND comes with their STEMMA QT cables (no header ground) |

*Amended 2026-10-30 (record P10, R-20 superseded):* Clint swapped the panel's original 3.5 × 1.1 mm
plug for a barrel plug that fits the breakout's DC jack directly. So we dropped the female
3.5 × 1.1 mm adapter, and the #368 takes its place. That one-time plug swap isn't a cut in the metered
lead.

The jack is 5.5 × 2.1 mm by inference from Adafruit's #4755 page. We haven't measured it, so
confirm it with calipers. Without metering, the panel plugs straight into the DC jack.

Every screw terminal here takes **solid 22 AWG only** (record P7). That covers the INA228s' X1, the
#368, the USB-C adapters and the #369. Nothing goes through a breadboard strip or a Dupont contact.
Pull-test each lever and clamp by hand.

There's no extra diode, no ideal-diode module, and the join stays on the board. A second Schottky
would cost another 0.3-0.45 V on a 5 V source. You only connect one source at a time (the USB-C
rule). Step 1b checks the back-feed through the idle input, one source at a time, in both directions.
It puts a 10 kΩ test load on the idle input, because an SK34A's reverse leakage can float an unloaded
node to volts.

**Condition: EN2 high and EN1 low.** An SK34A drops about 0.3 V typical at 1 A (TSC SK34A-T Fig 4,
25 °C, and 0.55 V max at 3 A). So a 5 V USB-C source reaches IN at about 4.7 V. IN sits lower at a hot
junction or a higher current, where the drop moves toward the 0.45 V end of the range above.

VIN-DPM (4.35-4.63 V)
acts only in the USB100 and USB500 modes, with EN2 low (SLUS810 section 9.3.4.1.1, electrical
characteristics "EN2 = LO, EN1 = X"). Those modes also cap the input at 100 or 500 mA. SLUS810
table 7-2 sets the four modes:

| EN2 | EN1 | Mode | Phase B |
|---:|---:|---|---|
| 0 | 0 | USB100: input at most 100 mA, VIN-DPM acts | fallback join only |
| 0 | 1 | USB500: input at most 500 mA, VIN-DPM acts | fallback join only |
| 1 | 0 | input limit KILIM ÷ R_ILIM (up to 1.5 A), no VIN-DPM | **required for D2/D4** |
| 1 | 1 | standby (USB suspend): no input power, no charge | never |

The ITERM formula in use (0.03 × R_ITERM ÷ R_ISET, about 0.3 A) also holds only with EN1 ≠ EN2. On
the #4755, the two-way solder jumpers SJ2 and SJ1 set EN1 and EN2 (each to OUT or GND). Record both on
the board in hand before phase B (open point 2). With EN2 high and EN1 low, D2/D4 is the design.

**Input-margin check (step 1b exit d, record section 3).** Use USB-C as the only source, with the
charger at full charge current (CC, 0.89 A typ with the 1A jumper). The charger's VBUS header pin
(after D2) must stay **≥ 4.6 V**. ISET must report the full charge current until the charger enters
CV. If it doesn't, the fix is a USB-C wall adapter with a 5.1-5.25 V output, not a diode change. The
D2/D4 join stays.

With EN2 low, the fallback is the spec's earlier choice. That's an off-board ideal-diode or power-mux
stage that drops at most about 100 mV at 1.5 A and feeds the charger's VBUS directly. The breakout's
own USB-C and DC jack then get taped "PHASE B: DO NOT USE". With D2/D4, `charger_input_mv` reads the
source less one Schottky drop. With the fallback, it reads the source less the stage's drop.

With EN2 high, nothing regulates the input voltage. Section 5.4 says what a weak panel does then.

Fallback candidates (none ordered, none checked against a datasheet yet):

| Kind | Candidate | Check before ordering |
|---|---|---|
| Two-input power mux | TI TPS2121 (2.8-22 V, 4.5 A class, tens of mΩ on-resistance) | input range covers the panel's cold Voc (the Voltaic P110 is rated Voc 6.94 V at STC; about 8.7 V cold is a project estimate, see section 6); drop at 1.5 A ≤ about 100 mV; reverse blocking on the idle input |
| Ideal-diode controller, one per input | Analog Devices LTC4412 with a P-channel MOSFET of 50 mΩ or less | controller range covers the panel Voc; MOSFET VGS rating at the panel Voc |

### 5.2 Sense points

The solar and USB-C INA228s sit **before** the join (D4 and D2), each in its own source's lead. Their
VBUS leads land at SOLAR_IN and USB_IN, ahead of the shunt (SJ1 open, section 2.2). So each one reads
its own source's voltage, not the joined node. The charger input (PA10 divider) still reads the
charger's VBUS after the join. The difference between the two is the diode's drop plus the shunt's.

### 5.3 The USB-C input

The off-board USB-C input is a **sink-configured receptacle: 5.1 kΩ Rd from CC1 to GND and from CC2 to
GND, 5 V only, no USB PD**. Without Rd on the CC pins, a USB-C source never turns its VBUS on. A
source that advertises only default USB current may limit near 500 mA. For a 1 A charge, use a supply
that advertises 1.5 A or 3 A. The receptacle carries VBUS and GND to the USB-C INA228, and its data
pins stay unconnected.

### 5.4 A weak source with EN2 high (analysis, not yet measured)

D2/D4 needs EN2 high, and that mode removes the only input-voltage regulation the bq24074 has.
VIN-DPM doesn't act (section 5.1), and the input current limit is KILIM ÷ R_ILIM. This holds in
phase A too whenever the board in hand has EN2 high (the build-progression record expects EN2 = 1,
EN1 = 0).

The bq24074 is a linear charger. Its input current is the charge current plus the system
load, and IN only has to stay above OUT.

Take a source that can't supply the charge current plus the load, like the panel in low sun against a
0.89 A charge. Nothing holds it at 4.35-4.63 V. Its voltage drops down its I-V curve until OUT reaches
VDPPM (VO(REG) − 100 mV, about 4.3 V for the bq24074).

DPPM then cuts the charge current to hold OUT
(SLUS810 section 9.3.4.1.2). So IN sits about a Q1 drop above roughly 4.3 V, with the panel near its
short-circuit current.

IN drops toward the cell only when the source can't supply even the system
load. Then the charger is in supplement mode, with the BAT-FET fully on, and the cell carries the rest
of the load (SLUS810 section 9.3.4.1.3).

| Effect | What it means here |
|---|---|
| Charge current | about the panel's current less the load. A linear charger delivers the panel's current, not its power. So holding the panel at 4.5 V wouldn't give more current. VIN-DPM protects a USB source. It isn't MPPT. Phases A and B have no MPPT either way |
| Input detection | IN must stay above VBAT + VIN(DT) (55-130 mV) and above UVLO (3.2-3.4 V, hysteresis 200-300 mV; SLUS810 electrical characteristics). When the panel current can't even cover the load, IN drops toward the cell and can fall under VBAT + VIN(DT). Then Q1 turns off, PGOOD and CHG go high-impedance, and charging stops (SLUS810 section 9.3.2 Power On, and Table 9-1 in section 9.3.5.7). The unloaded panel goes back to its open-circuit voltage, and the charger starts again. At low sun, expect a cycle of PGOOD and CHG, not damage |
| Ratings | none is exceeded. The cold-Voc rule of section 6 still holds, and the charger's thermal regulation still limits its die temperature |
| Telemetry | the cycle shows as `charger_input_mv` swinging between about the cell voltage and the panel's Voc. It also shows as PGOOD and CHG edges (the charger status byte, CHG flashing detection) and a mean charge current below the ISET setting. Phases A and B do nothing about it in firmware. If `charger_input_mv` reads near the cell voltage while PGOOD is asserted, a source got pulled down. It isn't a 4 V source |

**Check before phase B** (with step 1b, after you record EN1 and EN2):

1. Set a bench supply to 7 V with its current limit at 0.3 A. Then repeat at 0.1 A. That's a weak
   panel's current-source region.
2. Feed it into the DC jack through the solar INA228, with the cell at about 3.7 V.
3. Record if PGOOD and CHG hold steady or cycle. Record `charger_input_mv` too.

A steady charge at the supply's limit passes. We accept a cycle for phases A and B, since it costs
only status churn at low sun. If we don't accept it, the option is the fallback join of
section 5.1 with a stage that regulates the input voltage. See spec section 15, R16.

## 6. Input voltage limits

| Limit | Value | Source |
|---|---|---|
| bq24074 IN, absolute | 28 V | SLUS810 |
| bq24074 charges only below OVP | 10.2-10.8 V (bq24074 row), 175 mV hysteresis | SLUS810 electrical characteristics |
| PA10 (FT_fa), MCU powered | pin ≤ min(min(VDD, VDDA) + 3.6 V, 5.5 V) = 5.5 V → VBUS ≤ **16.5 V** through the divider (nominal 3:1) | DS13293 table 26, note 2 |
| PA10, MCU unpowered | pin ≤ 0 + 3.6 V → VBUS ≤ about **10.8 V** | DS13293 table 26 |
| PA10 reading range | the divider ratio × VDDA (nominal 3: 9.9 V at 3.3 V; the measured ratio in `POWER_VIN_DIVIDER_PPM`); an oversampled result ≥ 4080 is out of range and `charger_input_mv` is INVALID | spec section 9.5 |
| INA228 VBUS | 0-85 V | INA228 datasheet |
| INA228 common mode | −0.3 V to 85 V | INA228 datasheet |

**The rule:** in phases A and B, the source's **cold open-circuit voltage stays at or below about
10.2 V**. That's the charger's OVP. Voltaic rates the P110 at Voc 6.94 V (STC). The "about 8.7 V
cold" figure in this project's docs is our own estimate. No doc gives the temperature coefficient or
minimum temperature behind it, so treat it as unsourced. The 10.2 V limit also keeps PA10 inside
its unpowered limit (10.8 V).

A higher-voltage source needs a clamp or another divider ratio before PA10. For example, 47 kΩ over
10 kΩ gives ratio 5.7, an 18.8 V full scale at VDDA = 3.3 V and a 20.5 V unpowered limit. Change the
ratio in the model first:

1. Put the new resistors' values (then their `measured_ohms`) into R4-R6 in
   `hardware/bench-breadboard-r0/source/wiring.toml`.
2. Put (R4 + R5 + R6) / R6 in ppm into both firmware copies. Those are the node's
   `POWER_VIN_DIVIDER_PPM` (`firmware/stage0-node/App/power_config.h`) and benchlink's
   `VIN_DIVIDER_PPM` (`firmware/benchlink/App/benchlink.c`).
3. Regenerate the sheet and commit it all in one commit (record M2 dated note).

D3 check 9 (`checks.check_divider`) holds both firmware copies to the model.

## 7. Addresses and the bus

| Part | Address | A1 | A0 | How |
|---|---|---|---|---|
| battery INA228 | 0x40 | GND | GND | as shipped |
| load INA228 | 0x41 | GND | VS | close the A0 jumper |
| solar INA228 | 0x45 | VS | VS | close both jumpers |
| USB-C INA228 | 0x48 | SDA | GND | a wire from the ADDR1 (A1) pad to SDA (the #5832 jumpers reach VS only) |
| MAX17048 | 0x36 | — | — | fixed |

The strap table matches table 7-2 of the INA228 datasheet copy read (SLYS021A). The jumpers and the
0x48 wire are module preparation on the three extra #5832 boards. Clint allowed them on 2026-10-30
(record 7.1 Q1). Do them before step 1b. The battery INA228 stays as shipped.

**Address rules:**
- Never put an INA228 on 0x44 (the SHT45, and a phantom address the boot check uses), 0x46 or 0x47
  (BMP581), nor on 0x36, 0x50, 0x53, 0x70, 0x71. `power_config.h` asserts this at build time.
- 0x48 needs A1 strapped to SDA. The datasheet asks for **100 ns extra hold time on the address MSB**
  when SDA sets A0 or A1. *Closed 2026-10-29:* the node's I2C2 timing is `0x20323E5D` (`i2c_bus.c`
  `I2C_TIMING`). i2cscan and benchlink use the same value. SDADEL = 2 gives a data hold of
  2 × 62.5 ns + 1/48 MHz = 146 ns at PCLK1 = 48 MHz (RM0453 I2C timings). `tests/test_i2c_bus.py`
  (`BusTiming`) checks the fields. The old value was `0x20303E5D` (SDADEL 0).

  Scope SDA against SCL on
  the first phase B bus (spec risk R15). If it fails, an SCL strap is a `power_config.h` change. For
  example, 0x43 (A1 = GND, A0 = SCL) isn't reserved.
- On the #5832, ADDR1 has a 10 kΩ pull-down in the resistor pack R6. Wired to SDA, it adds a 10 kΩ
  load to SDA. With 1.1 kΩ of pull-ups, the idle bus then sits at about 3.0 V (above VIH) and draws
  about 0.3 mA more. We accept it and measure it, and never rework it. Step 1b exit f checks the bus
  pull-up (≥ 0.97 kΩ) and SDA high (≥ 2.8 V) with it in place.

**Pull-ups.** The #5832 has **no pull-up cut jumper**. Its SDA and SCL pull-ups (10 kΩ) and the
ADDR0/ADDR1 pull-downs share one 4-resistor pack (R6). The spec used to say to cut the pull-up
jumpers. On 2026-10-29 we amended it (sections 9.2 and 11.3) to keep and measure them, as here.

The bus has about nine STEMMA boards (SHT45, BMP581, LTR390, SHTC3, MAX17048, four INA228). Their
pull-ups in parallel come to about 1.11 kΩ. A part pulling SDA to 0.4 V then sinks
(3.3 − 0.4) V ÷ 1.11 kΩ = 2.6 mA, inside the 3 mA I2C limit.

Keep them. **Measure** the bus pull-up
with the bus idle and powered off. It passes at 0.97 kΩ or more ((3.3 − 0.4) V ÷ 3 mA). Below that,
the fix is still open. Don't take pull-ups off an INA228. The sensor-pods spec found no cuttable
pull-up jumper on the Adafruit pod breakouts either (SHT45 #6174, BMP581 #6407, LTR390 #4831,
24LC32), and no doc names a board on this bus that has one.

## 8. The monitors' own current

An INA228 in continuous mode draws 640 µA typical, 750 µA maximum at 25 °C and 1.1 mA maximum over
−40 to +125 °C (datasheet section 6.5, VS = 3.3 V). Each #5832 also lights a green power LED (D1
through R7, 10 kΩ, from VCC). That's at most about 0.13 mA ((3.3 V − Vf) ÷ 10 kΩ), an estimate, not
measured.

| Build | INA228 current (typical) | Per day | Of the 6,600 mAh pack per day | Worst case (1.1 mA each) |
|---|---|---|---|---|
| Phase A (one INA228) | 0.64 mA | 15 mAh | 0.23 % | 26 mAh, 0.40 % |
| Phase B (four INA228s) | 2.56 mA | 61 mAh | 0.93 % | 106 mAh, 1.6 % |

The LEDs add about 3 mAh a day each. These currents are on the 3.3 V rail, which the S7V8F3 makes from
OUT. In phase B the load INA228 measures them as part of the load. **Continuous mode stays.** The
CHARGE accumulator only integrates while the part converts. Shutdown (2.8 µA) would lose the radio
bursts between samples.

## 9. Open points

| # | Point | Owner |
|---|---|---|
| 1 | ~~Phase B OR-ing~~ **closed 2026-10-29**: the board's D2/D4 with EN2 high, the ideal-diode or power-mux stage only as the fallback (section 5.1; spec sections 11.3 and 17) | — |
| 2 | The #4755's EN1/EN2 solder jumpers (SJ2, SJ1) on the board in hand: record both; D2/D4 needs EN2 high **and EN1 low** (EN1 = EN2 = high is standby, no charge; section 5.1) | bench, before phase B |
| 6 | A weak source with EN2 high: the PGOOD/CHG cycle check of section 5.4 | bench, with step 1b |
| 3 | ~~0x48 and the SDA hold time~~ **closed 2026-10-29**: SDADEL = 2, 146 ns (section 7); scope it on the first phase B bus (spec R15) | bench |
| 4 | ~~Pull-up cut jumpers~~ **closed 2026-10-29**: the spec now keeps and measures them (section 7) | — |
| 5 | Fallback join-stage part: datasheet check of the candidates (section 5.1), only if EN2 is low | before any fallback order |
