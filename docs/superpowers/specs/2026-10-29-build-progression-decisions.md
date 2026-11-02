# Build progression: decision record

Status: decision record, 2026-10-29. Clint's own decisions (section 1.3) are inputs. Everything else
was decided by a review of the earlier recommendations (R1–R13 and the locking-connector, shield and
carrier ideas) in six areas: power interconnect, measurement integrity, NUCLEO interface, hygiene and
mechanics, phase roadmap and documentation truth. This record merges the six areas' rulings, settles the
places where they disagree (section 2.7), and corrects repo facts that the review found wrong
(section 1.4). Revised the same day after a review of this record: section 2.8 lists each finding,
what changed and where a finding was modified or overruled. Not implemented (2026-10-29). *Dated note
(2026-10-30):* the model, generator, checks, tools, firmware and tests of section 6 are implemented on
`feat/power-telemetry`, uncommitted and pending the gates; section 8's last row gives the state row by
row, and the bench work (sections 3 and 4) is not done. Section 6 lists every
file that must change. Section 8 records, row by row, which decisions the power-telemetry design
adopted, deferred or rejected (reconciled the same day). Section 7 lists the questions only Clint
could answer. **Clint answered Q1–Q8, P3 and N2 in a formal survey on 2026-10-30 (section 7.1).**
Those answers replace the section 7 defaults. Every passage changed to follow them cites the
answer it follows, as "7.1" with the question (for example "decided 2026-10-30 (7.1 Q8)",
"(7.1 Q2)", "Approved 2026-10-30 (7.1 N2)"), or as a "Dated note (2026-10-30)" where a review
finding of that date, not a survey answer, changed it.

It builds on:
- [`docs/hardware/bench-station-wiring.md`](../../hardware/bench-station-wiring.md): the build steps
  (section 1), the pin table (section 2), the power modes (section 5) and the UM2592 checklist
  (section 6);
- [`hardware/bench-breadboard-r0/`](../../../hardware/bench-breadboard-r0/README.md): `source/wiring.toml`,
  the generated build sheet and drawings;
- [`2026-10-29-power-telemetry-design.md`](2026-10-29-power-telemetry-design.md): power profiles A, B
  and C (section 2), the INA228 addresses (9.2), the breadboard model changes (11.1), the battery-path
  budget (11.2) and four-rail metering (11.3);
- [`2026-10-21-sensor-module-ports-design.md`](2026-10-21-sensor-module-ports-design.md): the v1 base
  board (OQ-14), PORT-9 (INA228, MAX17048 and SHTC3 upstream of the mux), mux RESET;
- [`docs/next-stages-plan.md`](../../next-stages-plan.md): stage 1 parts (BQ25798EVM, the 10 mΩ Kelvin
  shunt, XT60, the pack fuse);
- [`firmware/benchlink/README.md`](../../../firmware/benchlink/README.md): the bench link, its logger and
  the "Known limits" of the 2026-10-28/29 bench.

Sources checked for this record (all read as text):
- UM2592 Rev 4 Tables 17 and 18 (scratchpad `dl-um/um.txt`).
- STM32WL55 DS13293 (scratchpad `dl-ds/ds.txt`): pin table and alternate functions.
- bq24074 SLUS810N (scratchpad `dl-bq/bq.txt`).
- The Adafruit bq24074 #4755 and INA228 #5832 EAGLE schematics, parsed locally (scratchpad
  `dl-ada-bq/sch.sch`, `dl-ada-ina/sch.sch`).
- WAGO 221 and 222 conductor ranges, from WAGO's 221 series page and distributor listings.

## 1. Intent and the why

### 1.1 What failed on the bench (2026-10-28/29)

| # | Seen | Mechanism | Class |
|---|---|---|---|
| F1 | 1 A charges ended early | about 0.2 Ω of breadboard contacts in the battery path. The bq24074's BAT pin is both its output and its voltage sense (SLUS810 pin table), so the cell reached CV about 0.2 V early and terminated low | force current through friction contacts |
| F2 | the gauge read OUT, not the cell | the MAX17048 was wired to OUT first | sense lead on the wrong node |
| F3 | the INA228 VBUS jumper had to be moved | VBUS read the wrong net | sense lead on the wrong node |
| F4 | with nothing touched, OUT wandered 120–150 mV below the cell at 38 mA, and the gauge's SOC was fooled | 3–4 Ω appearing and disappearing in the current path. It cannot be the charger: VDO(BAT–OUT) is 50 mV typ / 100 mV max at 1 A (bq.txt:619), so 2–4 mV at 38 mA | force current through friction contacts |
| F5 | the INA228 shunt read about zero | the pack sat in the charger's JST socket, which is the same node as LIPO, so the shunt was bypassed (benchlink README "Known limits") | topology not as drawn |
| F6 | a USB unplug on one NUCLEO stalled the other NUCLEO's serial port on the Mac | port open but silent; a fresh open recovered it (benchlink README, `rx_port_reopen`). Both NUCLEOs were on one hub when the RX stalled (7.1 Q5, runs of 2026-10-28/29) | host USB; root cause unknown (H8) |

F1, F4 and F5 are the same lesson: current went where the drawing said it did not, through contacts no
one measured. F2 and F3 are the same lesson about sense leads. Neither class is fixed by better
breadboards. Both are fixed by keeping force current off friction contacts, giving every sense lead its
own landing, measuring the result at the current that matters, and keeping the drawings true.

### 1.2 The rule this record serves

**Prove before solder.** Every connection that gets soldered (protoboard) or laid out in copper
(carrier PCB) is first proven on the no-solder bench, with numbers recorded. Nothing that failed there
is carried forward. What passed there carries forward unchanged: the same nets, the same sense points,
the same MCU pins, the same addresses, the same checks.

### 1.3 Clint's decisions (inputs, not reopened)

| | Decision |
|---|---|
| Order | breadboard (no solder) → hand-soldered protoboard → custom board |
| Current charger | Adafruit bq24074 #4755 with the 1S3P pack (3 × 2200 mAh, 6600 mAh) |
| Later charger | TI BQ25798 (dual input) |
| Final metering | voltage and current of four rails (battery, solar, USB-C, load), one INA228 per rail |
| USB-C | bench and backup only, never connected together with solar |
| Meter cables | RJ11 (the SEN-15901's 6P4C cables). No RJ45 anywhere in v1 |

### 1.4 Repo facts this review found wrong

Each of these goes into the cascade (section 6).

| Fact as written | Correct | Source | Where it is wrong |
|---|---|---|---|
| R_ISET is about 890 Ω for the 1 A jumper | **R_ISET = 1 kΩ** (R9, behind the "1A" jumper, closed by default; 0.5A = 2 kΩ and 1.5A = 590 Ω, both open). ICHG = KISET / R_ISET = 890/1000 = 0.89 A typ (0.80–0.98 A, KISET 797–975 A·Ω, bq.txt:680). The logged ISET currents (I = 400 × V_ISET / R_ISET) read 12 % high | Adafruit schematic | `tools/benchlink_log.py:37`, `firmware/benchlink/README.md:98` (and the `--r-iset 890` default at `:220`), power-telemetry spec section 1 |
| the safety timer may end long charges (TMR floating, 4–6 h) | **TMR is tied to GND on the Adafruit board: all safety timers are disabled** (bq.txt:461–463) | Adafruit schematic (X4.TMR in net GND) | an advocate's hypothesis only |
| termination at about 10 % of ICHG | **ITERM = 0.03 × R_ITERM / R_ISET = 0.03 × 10 kΩ / 1 kΩ = 0.30 A typ (0.225–0.375 A)** when EN1 ≠ EN2 (bq.txt:1666, KITERM at bq.txt:691–697). R_ITERM = 10 kΩ (R2) | Adafruit schematic | advocates' figures |
| the INA228 #5832 shunt is 0.1 % | **15 mΩ, 1 %, 2 W, 2512** (R1 "HoLLR2512-2W-15mR-1%") | Adafruit INA228 schematic | one area's ruling |
| cut the extra INA228 boards' I2C pull-up jumpers | **the #5832 has no pull-up jumper.** SDA and SCL pull-ups and the ADDR0/ADDR1 pull-downs share one 10 kΩ 4-resistor pack (R6). Nine 10 kΩ pull-ups in parallel are 1.11 kΩ: a part sinking at VOL 0.4 V carries (3.3 − 0.4) / 1.11 kΩ = 2.6 mA, within the 3 mA limit. Keep them and measure | Adafruit INA228 schematic | power-telemetry spec 9.2 and 11.3 |
| 0x48 is "a rework wire" | true, and it leaves the board's 10 kΩ ADDR1 pull-down from SDA to GND. SDA high with 1.11 kΩ up is then about 2.97 V, above 0.7 × 3.3 V. Accepted and checked (step 1b exit f) | Adafruit INA228 schematic | power-telemetry spec 9.2 |
| CHG is morpho-only | **PB10 is also Arduino D6 (CN9.7), PB8 is D5 (CN9.6).** Only PC0 (CN10.14) of the station pins is morpho-only | UM2592 Table 17 | `bench-station-wiring.md:72–73`, benchlink README |
| PB2 is "A1 in most examples, A0 in one" | **PB2 = A1, CN8.2** (A0 is PB1) | UM2592 Table 17 | `bench-station-wiring.md:70` |
| the 5 V pins to avoid are CN6.5, CN7.18 | also **CN10.8 (5V_USB_CHGR)**, CN7.24 (VIN), CN7.6 (E5V), CN6.8 (VIN) | UM2592 Table 18 | guide section 2 |
| the external OR-ing diode pair is new phase-B hardware | **the board already diode-ORs its two inputs**: USB-C VBUS through D2 and the DC jack through D4 (both SK34A Schottky) into the charger's IN | Adafruit schematic | power-telemetry spec 11.3 |
| VIN-DPM limits USB-C charging | VIN-DPM acts only in the USB100 and USB500 modes (EN2 = 0, bq.txt:1320–1321). With EN1 ≠ EN2 and EN2 = 1 the input limit is set by R_ILIM. The margin that matters is IN against OUT regulation and DPPM; it is checked directly (section 3, step 1b) | SLUS810 | one area's ruling |

## 2. Decisions

IDs: **P** power interconnect, **M** measurement, **N** NUCLEO interface, **H** hygiene and
mechanics, **S** build steps, **D** documentation. "From" names the area rulings each decision
merges, so their reasoning can be traced. The rejected alternatives include each original
recommendation (R1–R13) that the decision replaces.

### 2.1 Power interconnect

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| P1 | **No battery, charge, input or load current through any breadboard contact, header pin or Dupont contact, in any step.** The breadboard carries only sense and logic lines (µA to a few mA). One tolerated exception, in mode B only: **the S7V8F3 regulator's supply chain**. Its input side: the VIN and GND pins (30–60 mA), fed by L_REG_VIN (from the OUT node into the regulator VIN strip) and L_TIE (from STAR into the regulator GND strip), 22 AWG solid, with L_NUC_RET (CN6.7 into the same GND strip) carrying the station return. Its output side, which carries the whole station current (MCU and radio, tens of mA with peaks in TX, plus the sensors): REG.VOUT pin → LK_REG_SHUNT (REG.VOUT → SHUNT.1) → the BATTERY POWER SHUNT header → L_REG_3V3 → the unswitched board-A 3V3 node → LK_3V3_CN6_4 (that node → N:CN6.4) → CN6.4. *Dated note (2026-10-30):* that node is the strip on board A where LK_3V3_CN6_4 starts, and L_REG_3V3 lands in that strip itself: the QT.V+ strip (A:c41) in r0.1 and r0.2 (changes A and B; there is no LSW before change C), the LSW.IN strip (A:c34) from r0.3 (change C), as the r0.3 sheet's Remove and Add lists show (*2026-11-02:* r0.3 is redefined without the load switch, so it lands in the QT.V+ strip (A:c41) too; section 4.6 dated note). Landing it on the A:L+ rail put a planner jumper (no stable id, renumbered on every regeneration) and two rail contacts into the chain, untagged and never wiggled. D3 check 1 now also checks that each chain member lands where the next one starts (`checks.P1_ORDER`). These are stable ids in the model; the build sheet's W-numbers change on every regeneration (section 4.4). Every member of the chain is tagged `exception = "P1 regulator"` in wiring.toml, and the mode-B rows of section 4.3 (C15, C20–C23) measure it during radio TX. From POWE-1, MEAS-1, HYGI-1, PHAS-2 | every power failure (F1, F4) was a friction contact carrying current. With no current in a contact, its resistance stops mattering: 4 Ω in series with the INA228's VBUS input (about 1 MΩ) is about 4 µV | R4 (doubled or tripled breadboard jumpers): the single header-pin contact stays the weak point, and parallel contacts hide a failing one. R5 (a fresh BB830 as the power fix): new springs still loosen; no BusBoard contact-resistance figure exists. Keeping the 38 mA load in the OUT and GND strips: that is where F4 sat |
| P2 | **Current leaves the bq24074 breakout only through its own JST PH sockets.** BATT: pin 2 is VLIPO (= header LIPO = the chip's BAT), pin 1 GND. SYSOUT: pin 2 is OUT (= header OUT), pin 1 GND. The 11-pin header stays in the breadboard for CHG, PGOOD, ISET and VBUS (to the divider). Header LIPO (a51), OUT (a53) and the three GND pins (a50, a52, a59) each sit alone in their strip: zero-current test points for BAT, OUT and VSS. From POWE-2, MEAS-1 | checked in the Adafruit schematic: BATT and SYSOUT are "JST 2PH SMT-RA" with those nets. JST PH is rated 2 A at 24 AWG, contact resistance 10 mΩ initial, 20 mΩ after environmental tests | Power through the header pins (the failed bench). OUT and GND on female Dupont leads from the header pins to lever connectors (PHAS-2): it keeps a header contact and a Dupont contact in the load path. A Dupont pin in a lever connector: a poor joint |
| P3 | **Battery + path (no breadboard, no solder, the pack's own lead never cut):** pack plug → pack-mating half of a cut Adafruit #1131 (lead ≤ 60 mm) → WAGO 222-415 **CELL+** → 22 AWG solid ≤ 50 mm → INA228 terminal VIN+ (X1 pin 3) → 15 mΩ shunt → VIN− (X1 pin 1) → 22 AWG solid ≤ 50 mm → WAGO 222-413 **BATT** → board-mating half of the same #1131 (≤ 60 mm) → charger BATT socket. **While the INA228 meters the battery, the pack never plugs into the charger's BATT socket.** Charge current stays at the board default (1A jumper, R_ISET 1 kΩ, 0.89 A typ). Never the 1.5A setting on this pack. **Decided 2026-10-30 (7.1 P3): yes, change A as written**; the direct plug-in of 2026-10-28 is retired. From POWE-3, MEAS-2, PHAS-2 | the BATT socket is the LIPO node, so a pack in it bypasses the shunt (F5). Screw terminals take solid wire only (P7), so stranded pigtails meet the INA228 through a lever connector; that costs one clamp pair (about 2 mΩ) and needs no ferrule crimper. Two #1131 halves from one cable give both pigtails | Pass-through via the MAX17048 board (pragmatist): its trace rating is unpublished, and its ground would sit in the 1 A return. R1 "a Wago on every joint": every extra joint adds resistance inside the BAT sense loop. Cutting the pack lead: it is polarised, rated and behind the pack protection. Ferrules on 26 AWG into the screw terminal (POWE-3/7): needs a crimper and a 0.25 mm² ferrule is oversized for 0.13 mm² |
| P4 | **Ground: one WAGO 222-415 STAR at pack negative.** Positions: (1) pack − (pack pigtail black), (2) charger BATT − (board pigtail black), (3) the 100 Ω load return, (4) the **TIE**, (5) one spare, kept for step 1b exit (g)'s second 100 Ω (a 222-415 has no sixth position). The TIE is the only conductor between STAR and logic ground, in both power modes: one 22 AWG solid lead, L_TIE, from STAR into the regulator GND strip on breadboard B, which the model's regulator-GND link already joins to the B ground rail. Not connected to anything: the charger SYSOUT pigtail's black lead (insulated, folded back), the MAX17048 pigtail's black lead (insulated; the gauge gets ground over STEMMA QT), the charger header GND pins (test points), and the INA228 header GND and VCC (the INA228 takes power and ground over STEMMA QT). The charger input always comes from a floating wall adapter, never from the Mac or a hub that shares the NUCLEO ground. From POWE-4, MEAS-3, NUCL-4 | every extra path between cell − and NUCLEO ground is a loop that takes a share of the battery return through 28 AWG QT cables and breadboard contacts. A fixed TIE means a mode change never touches ground (MEAS-3's mode-swapped tie can be forgotten). The charger's VSS sits about 1 A × (board pigtail − lead and mating, ≤ 40 mΩ) ≤ 40 mV from STAR during charge: against V_ISET = 2.2 V that is under 2 % of the ISET reading, absorbed by its gain fit (M2) | R3 as a star with several ties, or the gauge's Kelvin minus to STAR (MEAS-3/4): a second tie through gauge → QT → NUCLEO. A tie swapped between CN6.6 and the regulator GND by mode (MEAS-3). No star, ground from the charger header strip (pragmatist). SYSOUT − to STAR (POWE-4): a second parallel conductor between charger GND and STAR, which blurs the − span measurement |
| P5 | **Sense points (R2, by position).** Gauge: the board-mating half of a second cut #1131 in one MAX17048 socket (the other socket empty); its red lead in its own CELL+ position. Battery INA228 VBUS (X1 pin 2): its own 22 AWG solid lead into its own position in the OUT connector (phase A; load_mv = INA VBUS, power-telemetry fill table unchanged). From step 1b: battery INA VBUS moves to the CELL+ spare position, and the load INA228 VBUS lands at the LOAD connector. The breakout's VBUS-to-VIN+ solder jumper (SJ1) must be open on every INA228 (continuity check). From POWE-5, MEAS-4/5 | a sense lead carries µA, so 3 Ω in it costs µV. The OUT connector is the load node, so the cell-to-OUT path metric (M6) covers every force joint **from CELL+ to OUT**, including the SYSOUT mating, and no INA228 lead touches the breadboard. **Limit:** every sense point sits downstream of the pack's own lead and its PH mating (pack + to CELL+, pack − to STAR). A fault there moves the gauge, the INA VBUS at CELL+ and OUT together, so F4 at the pack mating would still fool the SOC and PATH_CELL_OUT cannot see it. That span is covered by C6, C11, C12–C14 and, live, by the VCELL step flag (M6) | INA VBUS at the charger OUT header pin (MEAS-2): it leaves the SYSOUT mating out of the path metric and puts the INA's sense lead through the breadboard. INA VBUS at the LIPO header (metrologist): drops load_mv. Closing SJ1: VBUS would read through the VIN+ clamp, which carries current |
| P6 | **OUT and load.** The board-mating half of a third cut #1131 (≤ 60 mm) in the charger SYSOUT socket, red lead to a WAGO 222-415 **OUT**. OUT takes: SYSOUT +, the 100 Ω ½ W load (mode A), the battery INA VBUS lead (phase A), the regulator VIN lead (L_REG_VIN, 22 AWG solid into the regulator VIN strip on breadboard B), one spare. The load's other lead goes to STAR. From POWE-6, MEAS-2 | moves the 38 mA path of F4 off the breadboard; the breakout's own connector carries it, and one lever connector is the only splice | One lever connector per lead (R1 literally): one node is one connector |
| P7 | **Joint hardware.** WAGO **222-series** lever connectors for every splice (distributor listings: 28–12 AWG, 0.08–4 mm² fine-stranded; WAGO's own 221 series page gives 0.14 mm² fine-stranded and 0.2 mm² solid as its floor). Stranded ends stripped to the length printed on the connector, twisted, never tinned, never folded back. Screw terminals (INA228 X1, later the barrel and USB-C adapters) take **solid 22 AWG only**. Dupont pins never go into a lever or screw clamp. Every lever closed and every clamp pull-tested by hand. Each JST lead tied down within 30 mm of its connector; the boards anchored (H1). If WAGO's own 222 data sheet does not confirm 0.08–0.14 mm² fine-stranded, fall back to 221-41x with 0.25 mm² insulated ferrules and a ratchet crimper. From MEAS-6, PHAS-2, POWE-7 | #1131 wire gauge is unpublished; assume 26 AWG (about 0.13 mm²), at or below the 221's floor. An undersized lead in a spring clamp is the next intermittent joint. The 222 range covers it bare, with no tool | 221 bare with 26 AWG (POWE-7 without ferrules): below its listed range. Ferrules everywhere (POWE-7): needs a crimper for no gain on the 222. Doubled-back strands: not a rated termination |
| P8 | **Battery-path limits, measured at 1 A** (replaces power-telemetry 11.2's "at most 50 mΩ, + side"). During the first 10 minutes of a CC charge, with the INA228 current I between 0.8 and 1.0 A, scale each limit by I: **+ span** (pack plug, back-probed, to header LIPO) **≤ 75 mΩ** including the 15 mΩ shunt; **− span** (header GND to pack plug −, back-probed) **≤ 40 mΩ**; the two **pack-side spans** (pack plug + to the CELL+ clamp; the STAR clamp to pack plug −) **≤ 28 mΩ each** (one PH mating at 20 plus 60 mm of lead at 8); their measured sum is **R_pack**, used by exit criterion 5 and the M4 correction; each JST PH mating ≤ 20 mΩ; each lever clamp-to-clamp and each screw ≤ 5 mΩ. The TIE is checked in mode B (C15), where it carries current. From MEAS-7, POWE-8, PHAS-3 | estimate of the + span: shunt 15, two PH contacts 2 × 5–10, two 60 mm pigtail leads of 26 AWG 2 × 8, two 50 mm solid links 2 × 2.7, four clamps and two screws about 6 = 57 typical, 71 with both PH contacts at their 10 mΩ initial maximum. 50 mΩ cannot be met with stock pigtails. Effect of a 115 mΩ loop: CV starts with the cell about 0.1 V below 4.2 V and the taper is longer; at termination (0.3 A) the cell sits about 35 mV low, still within the healthy-termination limit of P9 | R11 as written (under 5 mV per joint at 38 mA): that allows 130 mΩ per joint, so the F1 path would have passed. 50 mΩ for the + side (telemetry 11.2): not achievable and ignores the − side. 60/40 mV (MEAS-7): the + limit sits at the typical estimate and would fail good builds |
| P9 | **Charge-termination acceptance baseline.** TMR is tied to GND, so no safety timer; ITERM = 0.30 A typ (0.225–0.375 A); ICHG = 0.89 A typ. A healthy full charge ends with CHG released while the INA228 battery current I is between 0.20 and 0.40 A, and the cell voltage at that moment is ≥ 4.12 V (VBAT(REG) 4.16 V minimum less 0.375 A × 115 mΩ). The cell voltage is taken as gauge VCELL − I × R_pack (P8) in the last sample before CHG releases, because under charge the gauge reads the CELL+ node, above the pack terminal by the pack-side drop (M4). (The earlier item "header LIPO minus VCELL ≤ 45 mV" is dropped: it subtracted a reading against charger ground from one against logic ground.) Every charge run logs its start time, the CHG pattern (the power-telemetry 6.3 edge rule) and the end point. From POWE-9, MEAS-12 | it settles F1's attribution: with timers disabled, an early end is the path, not the timer. 0.3 A is about C/22 on 6.6 Ah: acceptable, so R_ITERM stays | the safety-timer hypothesis (MEAS-12, pragmatist): disproved by the schematic. Changing R_ITERM or TMR: needs solder on the breakout, no gain. "10 % of ICHG": wrong formula for the bq24074 with R_ITERM fitted |
| P10 | **Four rails, one plan for every step.** Addresses (power-telemetry 9.2): battery 0x40, load 0x41, solar 0x45, USB-C 0x48; never 0x44, 0x46, 0x47, 0x36, 0x50, 0x53, 0x70, 0x71. Step 1b, bq24074: the load INA228 between the OUT and a new LOAD connector; the solar INA228 in the lead of **one** 6 V panel (*amended 2026-10-30, R-20 superseded:* the panel's 2.1 mm barrel plug into an Adafruit #368 female 2.1 mm DC jack to screw-terminal adapter; the panel lead is never cut) ahead of an Adafruit #369 male 2.1 mm barrel plug into the charger's DC jack; without metering (step 1) the panel plugs straight into the charger's DC jack. Clint replaced the panel's original 3.5 × 1.1 mm plug with a barrel plug that fits the #4755's DC jack directly and confirmed it plugs straight in; that one-time connector swap is not a cut in the metered lead. The jack is 5.5 × 2.1 mm by inference from Adafruit's #4755 page (it sells a 3.5/1.1 → 5.5/2.1 adapter for the board), not measured: confirm with calipers (this clause said a female 3.5 × 1.1 mm screw-terminal adapter took the panel's own 3.5 × 1.1 mm plug); the USB-C INA228 in an inline USB-C screw-terminal pair (a female adapter with 5.1 kΩ Rd, then a male plug) into the charger's own USB-C. **The board's own D2 and D4 (SK34A) are the OR pair.** No extra diode, no ideal-diode module, no join moved off the board. Steps 3 onward: four high-side 4-terminal 10 mΩ shunts (WSK2512R0100BEA, not verified) with INA228s strapped in copper to the same four addresses: SOLAR after the solar fuse and before VAC1, USB-C between the receptacle and VAC2, BAT between the pack fuse and the BQ25798 BAT, LOAD between SYS and the downstream regulators. From POWE-10, MEAS-14, PHAS-5, PHAS-10 | each source's monitor is upstream of the join (the D2/D4 cathodes), which is exactly what the telemetry fill table needs. A second Schottky would cost another 0.3–0.45 V on a 5 V source. One rail table in `power_config.h` serves every step | Ideal-diode modules plus a USB-C sink breakout (PHAS-5): more parts and contacts for no function the board lacks. An external Schottky pair (telemetry 11.3). Addresses 0x40–0x43 (three advocates): diverge from the frozen rail table. A mux channel for a second 0x40: contradicts PORT-9. The P110 panel pair in series: over the bq24074's 10.5 V VOVP; waits for the BQ25798 |

### 2.2 Measurement

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| M1 | **INA228 rules, every step.** Shunt in series in the rail's + lead (high side). VBUS on its own lead from the rail's sense point. SJ1 open, by continuity, on every board. ADCRANGE 0 (±163.84 mV). Shunt constant = 15,000 µΩ nominal (1 %); it is *verified*, not measured: the battery current must agree with a DMM in series within 2 % + 2 mA (power-telemetry 12.2). A DMM-derived value replaces the nominal only if that check fails. **Dated note (2026-10-30), the series reference:** the DMM is the Fluke 87V itself (7.1 Q2: no meter is bought; no calibrated shunt or clamp meter is on any list). It goes on its A input (about 1 A) or its mA input (400 mA, for the 38 mA load), spliced into the pack + lead at CELL+ position 1. It stays in series only for a short steady window, as power-telemetry 12.2 allows, and never during a termination run or the battery-path checks (C12–C14), because its current shunt adds tens to hundreds of mΩ. Build-sheet power check 3, B3 and step 1b exit (a) use this method. Power and energy registers unused. From MEAS-5 | a two-wire DMM cannot resolve a 15 mΩ part better than its 1 % tolerance; the series-current check tests what matters | ADCRANGE 1: clips at 2.73 A. Per-board shunt measurement with a DMM |
| M2 | **ISET and divider inputs.** ISET: the charger ISET header → **10 kΩ 1 % at the charger end** → the PB1 node, which has **100 nF and 1 MΩ to logic ground** → PB1 (A0). Firmware gain = 1 MΩ / 1.01 MΩ × a one-time per-board fit against the battery INA228 during a CC charge above 200 mA with the load disconnected; stored with R_ISET = 1000 Ω in `power_config.h`. ISET current is a cross-check field (charger_battery_ma), never the battery current. Divider: 20 kΩ (two 10 kΩ) over 10 kΩ, 1 % if available; each resistor measured with the DMM and the ratio stored in place of `VIN_DIVIDER 3`; checked in circuit within 1 %; bottom to logic ground. **Status (2026-10-30):** the ISET network, the gain fit and the measured divider are adopted with change A, read by this workflow from 7.1 P3 "change A as written" (4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5). **Dated note (2026-10-30), where the values live:** every measured or fitted value goes into `wiring.toml` first. Each divider resistor's DMM reading goes in as its `measured_ohms` (R4–R6, all three together), the gain fit as the charger part's `iset_gain_ppm`, and a check-2 R_ISET other than 1 kΩ as its `iset_ohms` (D2 schema keys). D3 checks 8 and 9 then hold `power_config.h`, benchlink and `tools/benchlink_log.py` to those values exactly, in the same commit. A fit more than 10 % from the network's nominal gain fails check 8 (M7's ISET tolerance). From MEAS-8, NUCL-5 | a firmware fault that drives PB1 low then leaves ISET at 1 kΩ ∥ 10 kΩ = 909 Ω (ICHG +10 %, still within the pack's rating) instead of a short. The start-up ISET short test (1.3 mA against 520 mV, bq.txt:604–606) passes. The 100 nF makes the 160.5-cycle sample current negligible. The 1 MΩ discharges the node in about 0.1 s if the wire opens, so an open reads 0 V and the CHG cross-check flags it, instead of floating | Direct ISET wire (today). 4.7 kΩ + 1 MΩ only (NUCL-5): no reservoir for the sample. 10 kΩ + 100 nF only (MEAS-8): an open wire holds a plausible voltage. 0.1 % divider resistors: the stored ratio does the job |
| M3 | **ADC reference unchanged**: VREFINT scaling (VREFINT_CAL at 0x1FFF75AA, VDDA 3.3 V), 160.5 cycles, mean of 16. The ADC is a ±1 % cross-check instrument, never the record for a battery voltage or current. From MEAS-9 | the NUCLEO ties VREF+ to AVDD (UM2592 CN5.8) | VREFBUF via a NUCLEO strap change; an external reference |
| M4 | **Cell voltage of record**: phase A the gauge VCELL; from step 1b the battery INA228 VBUS at CELL+, with the gauge as cross-check (gap over 15 mV after the baseline flagged). Both read the **CELL+ node**: whenever current flows, the reading differs from the pack terminal by I × R_pack (P8; about 25–35 mV at 0.9 A charge). The logger and dashboard label it "CELL+ node, includes the pack-lead drop" and show the estimate VCELL − I × R_pack beside it. SOC is marked suspect, never dropped, while the path metric or the VCELL step flag (M6) is raised. From MEAS-4 | the gauge's SOC is a voltage model; a path fault feeds it a wrong voltage (F4). Naming the node keeps anyone from reading a charge-time VCELL as the cell | Gauge SOC while charging as truth. Calling a charge-time VCELL "the cell" |
| M5 | **Pre-run checklist** (R11 replaced): the table in section 4.3, logged as a preflight block (D6) in every run's notes. A 38 mA screen before every run; a 1 A measurement after every rewire and at every step exit; a wiggle test at both. From POWE-8, MEAS-10, PHAS-3, HYGI-9, DOCU-6 | only a 1 A measurement resolves milliohm joints; the 38 mA screen catches the F4 class (3–4 Ω) by a factor of over 100 | R11 (under 5 mV per joint at 38 mA): too loose and laborious. One reading per joint every run: slow; kept as the method to locate a failed span |
| M6 | **Path metric (R12) and VCELL step flag, staged.** Segment IDs: PATH_POS (pack plug + to LIPO, + span), PATH_NEG (charger GND to pack plug −), PATH_PACK_POS and PATH_PACK_NEG (the pack-side spans of P8, inside PATH_POS and PATH_NEG), PATH_CELL_OUT (CELL+ to the OUT connector, the live metric). **What each covers:** PATH_CELL_OUT covers CELL+ to OUT only. **It does not cover the pack mating** (PATH_PACK_POS, PATH_PACK_NEG): a fault there shifts both of its ends together. That span is covered by C6 and C11 at every preflight, by C12–C14 at 1 A, and live only by the VCELL step flag below. **Now, host-side** (benchlink dashboard, from the existing `vcell`, `vout`, `ishunt` columns): (1) **drop form**, valid only with PGOOD inactive and battery discharge current ≥ 30 mA: drop = VCELL − VBUS_OUT − dV0 (dV0 = the same difference at zero current, recorded per power mode in the preflight); R_path = drop / I. Flag when drop > 20 mV (about 0.5 Ω at 38 mA), or when it steps by more than 10 mV between consecutive samples at constant load. (2) **VCELL step flag**, valid in every state: when \|ΔI_bat\| < 2 mA between consecutive samples, a step of more than 8 mV in gauge VCELL (and, from step 1b, in the INA VBUS at CELL+) is flagged, and SOC is marked suspect from the flag until 30 minutes pass with no further flag. A 6.6 Ah cell at constant current cannot step by 8 mV in one sample, so any such step is a contact. **Step 1b on**: in mode A the drop form stays the metric (PGOOD inactive; the 100 Ω load is constant and, with input present, is fed from IN, so no ΔI exists). The same-chip form R_path = Δ(Vcell_INA − Vload_INA) / ΔI_load, which cancels both offsets, is used only with PGOOD inactive and a real load step: radio TX against sleep in mode B, or for 1b's exit a deliberate step (a second 100 Ω switched in and out at the LOAD connector). **Current balance** (profiles A and B, bq24074, a linear charger whose input current equals OUT current plus charge current plus ICC): I_solar + I_usb − I_bat(charge +) − I_load, flagged above 2 mA + 2 %. **Power balance** (profile C on, BQ25798, a buck-boost whose input and battery currents differ by the voltage ratio over the efficiency): η = (P_bat(charge +) + P_load) / (P_solar + P_usb), each P = VBUS × I from its INA228; flagged outside the efficiency band measured once at step 2c against the BQ25798 efficiency curve (expected about 85–95 %); with no input, the current form (I_bat = I_load + quiescent) still applies. **Step 3 on**: a node health field (path mΩ with its ΔI and a validity bit, the balance residual, and the VCELL step count) under a later protocol revision; step 2c adds (BQ25798 VBAT − INA cell VBUS) / IBAT if its ADC reports both. From MEAS-11, PHAS-11, DOCU-7, POWE-8 | two different chips differ by up to about 10–12 mV (gauge ±7.5 mV at 25 °C, INA offset and gain), about ±0.3 Ω at 38 mA, so a raw (cell − OUT)/I is meaningless without dV0 or a ΔI step. OUT is regulated at 4.4 V whenever input power is present (bq.txt:624), hence the PGOOD gate. The drop form catches F4 between CELL+ and OUT at once; the step flag catches it at the pack mating, where it fooled the SOC on 10-28/29 (3–4 Ω at 38 mA is a 115–150 mV step). No firmware this week. The health report is at its 64-byte v6 layout, so firmware fields wait for a revision | Raw R12 with no baseline. Claiming PATH_CELL_OUT covers the whole battery path. A current balance across the BQ25798 (it cannot balance). A firmware field now. An absolute mΩ alarm (it ignores per-unit offsets). Dropping flagged rows |
| M7 | **Interface cross-checks** (host-side now, in the benchlink dashboard): PGOOD asserted with the divider below 4.0 V, or not asserted above 4.7 V; CHG asserted with V_ISET near 0, or V_ISET above 0.2 V with CHG off; ISET current against INA228 battery current during CC above 200 mA, outside 10 % + 20 mA (this also catches a bypassed shunt, F5). **Counter link probe** (node firmware, before the step 2 H01 run): at boot and every 15 minutes, switch PB5 and PB4 to the internal pull-down for about 1 ms and read. **Dated note (2026-10-30), probe timing:** the probe is two-phase on a UTIL one-shot timer of about 1 ms (phase 1 sets the pull-downs and arms the timer; phase 2, on expiry, reads and restores the pull-ups), so there is no busy wait at run time (CI "waits" check). **Dated note (2026-10-30), cups self-count:** LPTIM1's glitch filter (8 LSE samples, 244 µs; `board_inputs.c:144–146`) passes the 1 ms pull-down edge when the PB5 link is open, so the probe reads the LPTIM1 count before and after its window, subtracts the pulses added in it, and excludes edges inside the probe window from "edge since". **Placement rule:** the 10 kΩ pull-ups and the RC filters sit at the **jack end**, beside the RJ11 jack: on board A beside the BOB-14021s at step 1 (R1 and C_CUPS, R2 and C_RAIN, R3 in wiring.toml), on the module board beside the BOB-14021s at step 2 (not on the shield), next to the jacks on the carrier. An intact link from the jack-end pull-up to the MCU then reads high; an open link reads low. *Dated note (2026-10-30), jack strip:* at step 1 each pull-up's and filter's line-side lead sits in its BOB-14021 pin's own strip, checked by `checks.check_meter_at_jack`. With the pull-ups on the far side of the centre channel, a planner jumper (jack pin to pull-up: A:e6 → A:f4 for the cups, A:e15 → A:f15 for the rain) sat outside the probe, and an open there read as calm wind or no rain. The filter capacitors are C_CUPS and C_RAIN; they were C1 and C2, the ids of the pre-run checklist rows C1 and C2 (section 4.3). **What it covers:** the jumpers (step 1), the JST-XH harness and the shield (step 2), the board traces (step 3). **What it cannot cover:** the RJ11 cable and jack contacts beyond the pull-up. A reed-side open there reads high, like a healthy open reed, and **cannot be detected for rain**. For wind, the vane shares the RJ11 cable: a vane ADC reading outside the direction table (an open vane pair reads the pull-up rail) flags the cable or jack, though not an open on the cups pair alone. **Rules:** rain (reed open at rest): low on three reads in a row with no edge since → the rain module's existing quality = fault, `#status meter_link=rain-open`. **Dated note (2026-10-30), field name:** the bench status field is `meter_link=` (ok, rain-open, cups-suspect, cups-open, vane-out-of-table), because `#status role=tx` already prints `link=` for the radio link policy (`firmware/stage0-node/App/tx_console.c:62`; `tests/test_tx_machine.py:730`, `:745`, `:925` and `:1132`). Cups (the rotor can stop with the magnet holding the reed closed, so "closed reed" and "open link" both read low in calm air): the same reads set quality **suspect** only; it escalates to fault if the vane changes position during the same window (wind is blowing but no cup edge), or after 24 h of uninterrupted low reads with no edge. No protocol change. From NUCL-6 | an open counter wire reads as calm wind and no rain, silently. With 10 kΩ up against the roughly 40 kΩ internal pull-down the line sits near 2.6 V, never crossing VIL, so no false count. Faulting the cups in calm air would discard valid data every still night | Relying on the tug test alone. Reporting the ambiguous case as healthy. The same fault rule for cups and rain. Pull-ups at the MCU end (S2 as first written): the probe would test only a few millimetres of shield trace |

### 2.3 NUCLEO interface

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| N1 | **The interface is frozen as MCU pins, not a connector** (table in section 4.2). Every pin keeps its Arduino and morpho position; the connector changes per step. Never used: CN6.5 5V, CN6.8 VIN, CN7.18 5V, CN7.24 VIN, CN7.6 E5V, CN10.8 5V_USB_CHGR, CN6.2 IOREF and CN5.8 AVDD as supplies; D0/D1 (USART1 PB7/PB6 by default, UM2592 note p.36; reserved for the v2 RS-485 ports); D3/PB3 (T_SWO); D2/PB12 and A5/PB13 (probe lines, `sys_debug.h`); and the guide's keep-free list. From NUCL-1, PHAS-4 | firmware constants, wiring.toml net names and tests stay the same through every connector change | Freezing "Arduino header" or "morpho" (the carrier mates morpho underneath; the shield mates Arduino on top) |
| N2 | **Remap two meter inputs before any solder**: cups PC0 → **PB5** (LPTIM1_IN1 on AF1, the same AF as PC0: DS13293 AF table, ds.txt:3475; Arduino D4 CN9.5, morpho CN10.29); rain PB5 → **PB4** (EXTI4; A3 CN8.4, morpho CN7.34). PB4's reset function NJTRST is released when firmware configures it; debug is SWD only. Add compile-time asserts `DEBUG_RF_LDORDY_ENABLED == 0` (`firmware/board/nucleo-wl55jc/Core/Src/sys_debug.c:152–160` would drive PB4, rain) and `DEBUG_RF_SMPSRDY_ENABLED == 0` (`sys_debug.c:142–150` would drive PB2, the vane), beside the PA10/PA11 asserts. Done on breadboard v2 as change B (section 4.5), after change A passes its checklist; proven by a pulse count against a known rotation and 20 hand tips. From NUCL-2, PHAS-4 | PC0 is morpho-only (CN10.14): the step 2 shield cannot reach it, and a flying morpho lead on a silent-failure signal is the joint this work removes. **Approved 2026-10-30 (7.1 N2):** change B goes ahead on breadboard v2. PC0, PB1, PB10 and PB14 also do not exist on the UFQFPN48 package (DS13293 Table 20); PB4 and PB5 do. Repo search: the pins are used in code only by `board_inputs.c`; they are named in comments and documents in `mod_rain.h:3`, `docs/firmware-event-model.md:17`, the root and stage0-node READMEs, `wiring.py:96` and `:575` (examples), the guide and the 10-18/10-19 documents (all in section 6). No other station or plan is wired to them (the rangetest firmware's EXTI9_5 handler is its own image) | Keep PC0 on one morpho lead through step 2 (pragmatist, product engineer). Rain on PB12/D2 (a probe line). Decide at the carrier (it would reach solder unproven) |
| N3 | **Step 1 connection method: no screw shield.** Every station signal lands on the NUCLEO's **Arduino female headers** (CN5, CN6, CN8, CN9) with solid 22 AWG jumpers, so step 1 proves the exact positions the step 2 shield uses. **The mode-B supply enters at CN6.4**, the pin the shield's 3V3 uses at step 2: the regulator's output (through the SHUNT header and L_REG_3V3) lands on the unswitched board-A 3V3 node, which LK_3V3_CN6_4 already joins to CN6.4. CN6.4 and CN7.16 are the same 3V3 net (UM2592 Tables 17–18), so the guide's CN7.16 power-jumper check applies unchanged. Female Dupont on morpho male pins only for the **bench OLED** (bench only): its five signals on CN10 as today, and **its own supply pair straight to the NUCLEO**: VCC from **CN7.16** (freed by the move above) and GND to **CN10.20** (a free morpho GND), so no OLED current flows in any breadboard rail or in the TIE's ground path. Kapton, labelled "NO 5V", over CN6.5, CN6.8 (sockets) and CN7.18, CN7.24, CN7.6, CN10.8 (pins); CN6.2 and CN5.8 stay empty. NUCLEO and jumper bundle tied to the plate (H1). From NUCL-3, HYGI-3, PHAS-4 | the NUCLEO pins carry µA into ≥ 10 kΩ nodes; the real hazard is 5 V beside 3V3 (CN6.5 next to CN6.4), and tape fixes it for nothing. Candidate no-solder screw shields are unverified (assembly state, power stages, SDA/SCL ties to A4/A5 that would short PA11/PA12 to PB14/PB13, a D13 LED loading PA5) | R8 now (a pre-assembled screw shield): a new unproven part for a failure not seen. Morpho Dupont for station signals (NUCL-3): it proves positions the shield never uses. Mode-B feed on CN7.16 (as first written): the shield cannot reach morpho, so step 1 would prove a feed point step 2 does not use. OLED supply from the SHUNT.2 strip and OLED ground on the board-B rail (the removed jumpers SHUNT.2 strip → OLED 3V3 and OLED GND → board-B ground rail): screen-dependent current through the CN7.16 Dupont and along the rail where the TIE lands |
| N4 | **Ground and supply boundary at the NUCLEO.** Logic ground meets STAR only through the TIE (P4). In mode B the NUCLEO's supply return gets its own 22 AWG solid lead from **CN6.7** (GND) to the regulator GND strip, fitted in both modes, so the station return does not ride the breadboard rails. Sensor and hub 3V3 from CN6.4 only. PB8/PB10 keep their internal pull-ups only while the CHG/PGOOD high level stays ≤ VDD + 0.3 V (2.9 V measured); re-measured at each step. Unpowered, every contract pin stays below min(VDD, VDDA) + 3.6 V = 3.6 V (DS13293 Table 26 note); the divider (≤ 3.5 V at 10.5 V in) and ISET (2.2 V, behind 10 kΩ) satisfy it. From NUCL-4 | the gauge reads the cell against the QT (logic) ground: in mode B any return current between logic ground and STAR becomes gauge error. With the CN6.7 lead it stays about 2–3 mV | Several NUCLEO GND pins jumpered to STAR (a loop). Powering the INA228 or gauge from OUT |
| N5 | **Mux RESET = PB14** (A4, CN8.5 / CN7.36), a direct GPIO. Answers the ports spec's "Mux RESET: TBD". Wired when the mux is (`WS_I2C_MUX=1`). Depends on the shield's incoming check showing A4 not tied to SDA. From NUCL-8 | free (no solder bridge, not keep-free, FT_fa), reachable from both shield and carrier | PB4 (now rain), PB13 (probe line), an I/O expander (the ports spec forbids it for RESET) |
| N6 | **Step 2 shield: Adafruit Proto-ScrewShield (Wingshield) R3 #196**, one per node plus one spare. Build: omit the D13 LED (PA5 is the OLED clock) and the power LED; **do not fit the stacking header's 5V, VIN, IOREF and AREF pins** (clip each flush before the header is soldered), so the shield's 5V net cannot be live from CN6.5; leave the 5V, VIN and AREF terminals unpopulated and taped; skip the 2×3 ICSP header (the NUCLEO has none); Kapton on the underside over the morpho rows; check clearance over the NUCLEO's top-side parts by eye. **Incoming meter check, before any circuit is soldered and before it ever sits on a powered board**: each terminal continuous to its own CN pin; SDA–A4 and SCL–A5 open; with the four pins clipped, the shield's 5V, VIN and AREF nets reach no header pin; **each prototyping-area rail traced with the meter to the header pin it ties to**, and only a rail proven to be GND or the CN6.4 3V3 is used (a rail tied to 5V is taped over and never used). It carries the signal circuits only (section 3, step 2). From NUCL-7, HYGI-11, PHAS-6 | after N2 every station pin is on the Arduino headers, so one stacked shield removes every NUCLEO jumper. Its 3.5 mm terminals and locking headers fix the loose-joint class at the point where soldering is allowed | A Perma-Proto with morpho flying wires. DFRobot DFR0920 (a 7–24 V power stage). DFR0224 (overhang not checked) |
| N7 | **Carrier (v1 base board, OQ-14)** mates the morpho CN7/CN10 underside male pins through two 2 × 19 2.54 mm female sockets; routes the N1 contract at morpho positions; leaves the Arduino sockets free on top. The NUCLEO is powered in mode B through CN7.16 (3V3 input; the same net as the CN6.4 entry proved at steps 1 and 2, and the only 3V3 pin underneath) via a removable jumper; ST-LINK USB only with that jumper out. Before layout: measure the underside pin length and part clearance on a real NUCLEO-WL55JC1. **OQ-14 decided 2026-10-30 (7.1 Q7)**; the layout waits only for that measurement, the morpho grid and the chassis outline (S4). *Dated note (2026-10-30, 7.1 N7):* the measurement is satisfied by Clint's fit test: a cut-down standard 2.54 mm female header (short PCB tails) took the morpho pins fully seated, and no underside part touched it, so a standard-height 2.54 mm female socket works. The layout now waits only for the morpho grid from ST's drawing and the chassis outline. 2 × 19 female sockets come only at 1000-piece minimums, so the carrier uses standard 2 × N female headers cut to 2 × 19 (sacrificing one position at the cut). From NUCL-9, PHAS-8 | UM2592 7.5: morpho is male, on both sides, with every MCU pin; Arduino is top-side female only | A carrier on the Arduino headers (that is a shield, on top, not "under") |
| N8 | **Pin evolution.** At the BQ25798 (step 2c on): PB1, PA10 and PB10 are released; PB8 becomes the BQ25798 /INT (open-drain, active low, same pull-up rule). **/CE stays strapped low** (charging enabled in hardware); firmware stops and starts charging over I2C with the charger's charge-enable register bit (EN_CHG, verify in SLUSDV2), so no GPIO is held for /CE. A custom board on the UFBGA73 STM32WL55JC keeps every pin; on UFQFPN48 only PB14 needs a new home (the charger pins are already released). From NUCL-10 | fewest changes; the contract stays one table. Holding PB10 for /CE would leave a pin that does not exist on UFQFPN48 | New pins for /INT. PB10 held for /CE (NUCL-10 as written) |

### 2.4 Hygiene and mechanics

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| H1 | **Base plate (R7), mandatory now**: one plywood or MDF plate about 30 × 40 cm, 6–9 mm. Both NUCLEOs on nylon standoffs; breadboards by their adhesive; INA228, gauge and hub on foam tape or M2.5 standoffs; the lever connectors glued down in a row beside board B; adhesive tie mounts within 30 mm of every JST mating, the pack lead and both USB cables. The pack lies flat in a marked spot. Step 2 uses the same plate. From HYGI-4, PHAS-14 | a tug stops at an anchor, never at a contact. CONTEXT-PACK records that a 1 s USB dropout resets the ST-LINK board | Loose boards (today). The printed poc-enclosure-r1 chassis as the step 2 bench base (HYGI-4): a 165 mm breadboard does not fit the 160 mm chassis, and the enclosure is redrawn for the carrier anyway (H9) |
| H2 | **R5 rejected.** Keep the existing breadboards for signals. If a signal joint fails the wiggle test, move the part to unused holes; buy one BB830 only if failures repeat in different areas. From HYGI-2 | with P1 in place, breadboard contact resistance affects no measurement | A fresh board "to remove a variable": the variable no longer matters |
| H3 | **R6, limited.** Every jumper added or moved in changes A and B (section 4) is pre-cut solid 22 AWG laid flat, including all NUCLEO Arduino-header jumpers; headers fully seated and checked by eye. Untouched board-A jumpers stay unless they fail the wiggle test. From HYGI-3, PHAS-14 | removes the springy leads that lever contacts, without rebuilding what works; the breadboard retires at step 2 | Rewire everything now (step 2 replaces it). Dupont throughout (the failure-era jumper) |
| H4 | **R9 accepted as already done**: every I2C part on STEMMA QT through the passive 5625 hub; cables 50–100 mm, 200 mm only where the layout needs it; bench bus under 1 m. From HYGI-5 | a bad I2C contact fails loudly (NACK → suspect → absent) | I2C on breadboard jumpers; an active hub now |
| H5 | **R10 modified: the meter's RJ11 cables are never cut.** They land on SparkFun BOB-14021 breakouts with the PRT-00132 jack. **Decided 2026-10-30 (7.1 Q6):** the jack and header pins are soldered onto each BOB-14021 now, as module preparation (like the headers already soldered onto the Adafruit breakouts), not circuit wiring (change A step 4a); step 1 uses the BOB-14021s directly. Then the per-conductor continuity check of the build sheet (wind: 3/4 cups, 2/5 vane; rain: 3/4 bucket). From HYGI-6 | a jack breakout is the bench analogue of the product's RJ11 meter ports 12 and 13 | Screw-terminal RJ11 breakouts (the first version's fallback, removed by 7.1 Q6). Cutting the meter cables |
| H6 | **Connector families, fixed per step.** Step 1: JST PH (the breakouts' own sockets) and WAGO 222 only; no crimped connectors. Step 2: the force harness unchanged (S2); JST-XH 2.5 mm with pre-crimped leads for the signal links between the module board and the shield; RJ11 jacks; STEMMA QT. Step 3 on: **XT60** for the pack (next-stages-plan section 3); a cold-rated latched or screw-retained connector for solar (Molex Micro-Fit 3.0 or a pluggable 5.08 mm screw block, chosen at the schematic); a USB-C receptacle for the backup input; RJ11 jacks for the meters and the v1 sensor ports; STEMMA QT only on the external module boards; Kelvin pairs as traces. **No RJ45 anywhere in v1.** 7.1 Q3's "current connectors" is read as these connector families (decided 2026-10-30 (7.1)). From HYGI-7, PHAS-13, POWE-7 | JST-XH is rated −25 °C in most listings, so it stays indoors; the product's cold test (H03) is −35 °C | JST-XH for the carrier's battery, solar and USB-C inputs (PHAS-8). Molex KK beside XH (a second crimp family). Micro-Fit on a 0.1-inch protoboard (3.0 mm pitch) |
| H7 | **Lead lengths**, recorded in wiring.toml so the drawings show them: JST PH pigtail halves ≤ 60 mm from the housing; solid force links ≤ 50 mm; the TIE and regulator leads ≤ 100 mm; sense leads any length but never bundled along a force lead; signal jumpers ≤ 200 mm; OLED leads about 300 mm; QT 50–100 mm. **Dated note (2026-10-30), scope of the 100 mm cap:** it applies to the regulator-supply leads L_REG_VIN and L_TIE only. L_REG_3V3 and L_NUC_RET carry the P1 tag, but their length is set by routing and bounded by C20 and C21 (≤ 10 mV), not by 100 mm. Pigtails stay ≤ 60 mm and other solid force links ≤ 50 mm. From HYGI-8, P3 | each 100 mm of 26 AWG is about 13 mΩ, 13 mV at 1 A | 150 mm power leads (HYGI-8): over the P8 budget with 26 AWG pigtails. 80 or 100 mm (MEAS-7, PHAS-2) |
| H8 | **USB topology, set now; the gateway reopen before H01.** (a) The RX gateway NUCLEO alone on a direct Mac port, never plugged or unplugged during a run. (b) The TX and any other bench board on another port or hub; their replugs happen only there, at the board end. (c) Each USB cable labelled with its ST-LINK serial. (d) Acceptance: log both boards, unplug and replug the TX 5 times, no gap in the RX log. (e) A powered hub only if (d) fails. (f) `ws0/link.py` gets an open-but-silent reopen like the one in `tools/benchlink_log.py`, with its own threshold: **SILENT_REOPEN_S = 90 s, doubling to 400 s, reset on any received line**. The stage0 RX prints `#alive` every 60 s (`firmware/stage0-node/App/app_rx.c:70`), while benchlink_log's STALL_S = 25 s (`tools/benchlink_log.py:81`) suits its 10 s heartbeat; 25 s would reopen a healthy ws0 port every minute. The port is reopened in place, with no connect back-off, and a reopen does not count as a failure. Each reopen is logged as a `gateway_events` row of kind `serial-reopen` at level warn, with the port path and silent_s, and the dashboard draws it as a marker. Today ws0 reopens only on an exception; `receiver-silent` after 180 s (`ws0/__main__.py:25`) stays as the outer alarm. **Dated note (2026-10-30, 7.1 Q5):** both NUCLEOs were on one hub when the RX stalled (runs of 2026-10-28/29), so (a) and (b) are confirmed. From HYGI-10 | the stall raises no exception, so an unattended 24 h H01 run would lose data. Topology lowers the odds; the reopen makes a stall survivable. The root cause (macOS CDC or a shared controller) stays open, so the reopen (f) stays required | Topology alone. A per-port-switched hub as the mode-B step (untested back-feed). The 180 s log alone |
| H9 | **Enclosure.** No breadboard, Dupont lead, lever connector or bench module goes into `hardware/poc-enclosure-r1`. The enclosure work now is only to print the `nucleo-rail-coupon` and confirm the `MEASURE` parameters (CHASSIS 160 × 110 mm, NUCLEO_UNDER). The chassis is redrawn once, for the carrier outline (step 3), and first used in the field at step 4. From HYGI-11, PHAS-9 | the shield and module board are bench forms; the carrier is the first thing worth a chassis | Fitting the step 2 plate into the box. Skipping the coupon |

### 2.5 Build steps

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| S1 | **Seven steps, two axes.** Build steps: **1** breadboard v2 (no solder); **1b** the same bench with profile B, four rails on the bq24074; **2** hand-soldered protoboard (shield + module board), where H01 runs; **2c** BQ25798EVM on the step 2 harness (no solder); **3** carrier PCB under the NUCLEO (v1 base board, BQ25798 only); **4** the carrier in the enclosure, in the field; **5** custom STM32WL55 board (PRD Stage 4). Power profiles A, B, C stay as the power-telemetry spec defines them, selected by `WS_POWER_PROFILE`. **Order, decided 2026-10-30 (7.1 Q1 yes, Q8 H01 first): 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5.** **Gates:** step 2 needs step 1's exit, with the module board's three phase-B INA228 positions **left unpopulated and unwired**. Step 1b runs after step 2's H01 run has passed (`next-stages-plan.md:36` and `H01-checklist.md:6`: Stage 1 power work waits for H01); the INA228 module preparation it needs is allowed (7.1 Q1). It runs on the step 2 plate: the three extra INA228s sit in a small breadboard kept on the plate for their signal pins, on the same lever-connector harness, with no solder beyond module preparation. Only after 1b exits are those three boards moved into their module-board positions and soldered by their headers; 1b's checks are then re-run as a confirmation, never as the first proof. 2c needs H01 passed and 1b's exit. 3's layout needs 2 and 2c exits and the measured NUCLEO underside (S4); the cell count (1S3P, 7.1 Q3) and OQ-14 (7.1 Q7) were decided on 2026-10-30. Guide build step 1 = step 1; build step 2 = steps 2, 1b and 2c; build step 3 = steps 3–5. From PHAS-1, MEAS-14 | Clint's rule puts every proof before the solder that freezes it, including four-rail metering. Profile B on the bq24074 separates two unknowns (the monitors, then the charger). Putting four-rail work (three INA228s, a panel, a 24 h balance) on H01's critical path would reverse a stage gate Clint set; he kept the gate (7.1 Q8) | BQ25798 and four rails together (pragmatist). A soldered bq24074 power board or carrier (throwaway at step 3). 1b in parallel with step 2 on one harness (PHAS-1). 1b before step 2 as the default (the first version of this record): it moved the H01 gate without asking. Running 1b's checks first on the soldered module board (the first version's "Q1 = no" branch): that proves on solder |
| S2 | **Step 2 form.** The **force path is not re-soldered**: the step 1 JST PH + WAGO + INA228-terminal harness moves unchanged to the step 2 plate, re-measured; step 1b later extends it there (S1). Signals are soldered on two boards, and **every soldered circuit was first proved on the breadboard in step 1** (exit criterion 10 covers the mode-B entry, which was not in the first version; exit 9 covered the PA9 switch until 2026-11-02, see the dated note): (a) the **#196 shield** on the NUCLEO, with the circuits that belong at the MCU: ISET's 100 nF and 1 MΩ, the divider's bottom 10 kΩ, the mode-B BATTERY POWER shunt header feeding the shield's 3V3 (CN6.4, the entry step 1 proves), ~~the PA9 sensor load switch **only if step 1's exit 9 passed** (otherwise it is left off and `i2c_bus` keeps its no-op until the mux)~~ (superseded 2026-11-02: no sensor switch at step 2), the STEMMA QT-to-header leads (one to the power monitors, one to the hub, both on the unswitched 3V3, as in step 1), and JST-XH headers to (b); (b) a full-size **Perma-Proto module board** laid out like breadboards A and B, with the charger, the battery INA228, the gauge and the regulator soldered by their headers (signals only), **the three phase-B INA228 positions unpopulated and unwired until step 1b exits** (S1), the two BOB-14021 RJ11 breakouts **with the meter pull-ups, RC filters and the vane pull-up beside them at the jack end** (M7), ISET's 10 kΩ and the divider's top 20 kΩ at the charger (so every charger analog node leaves the module board only through its series resistor), and JST-XH leads to the shield. The charger's BATT and SYSOUT sockets stay the only force exits; its header LIPO, OUT and GND pins are soldered to isolated pads (test points). No current-carrying pad or trace on either board except the P1 regulator chain (VIN/GND leads and the 3V3 feed to the shield). *Dated note (2026-11-02):* change C's PA9 sensor load switch (LSW, net 3V3_SW) is **deferred to the carrier** (Clint's decision, 2026-11-02; section 4.6 dated note); steps 1 and 2 have no sensor power switch. PA9 stays unconnected on the shield and `i2c_bus` keeps its power-cycle no-op until the carrier. From PHAS-6, NUCL-7, HYGI-11 | what passed the 1 A checks carries forward unchanged; soldering a new force path for a charger that leaves at step 3 would be unproven and thrown away. The full-size Perma-Proto mirrors board B hole for hole, so the wiring.toml placement carries over | Charger LIPO/OUT carrying current through soldered pins (POWE-2/3 carry): a new, unproven force path. A Perma-Proto as the main board with morpho flying leads. A half-size module board (the parts need over 50 columns) |
| S3 | **Step 2c**: a BQ25798EVM replaces the bq24074 on the step 2 Wago harness. The bq24074 stays soldered on the module board but is fully disconnected: its BATT and SYSOUT pigtails unplugged, and **its JST-XH signal link (CHG, PGOOD, ISET, VBUS) unplugged** from the shield, so its unpowered !PGOOD pin and LED cannot load PB8, which becomes the BQ25798 /INT. The EVM gets its own JST-XH lead into the shield's charger header with /INT on the PGOOD position (PB8) and the CHG, ISET and VBUS positions open; its I2C joins the unswitched QT branch. The model records the unplugged link and the new lead (`bench-protoboard-r0`). Same four INA228s and addresses; VAC1 = solar, VAC2 = USB-C; the EVM strapped for 1S per its user guide. **Before the pack's lever is closed**, the driver writes and reads back ICHG ≤ 1.0 A (P8's budget and the JST PH 2 A rating; the BQ25798 can charge at up to 5 A), the input current limit ≤ 2 A (the wall adapter) and VREG 4.2 V, with charging held off by the EVM's /CE jumper until the read-back matches; the driver re-writes them after any watchdog or POR reset (verify which registers reset in SLUSDV2). Profile C firmware plus a BQ25798 driver (new work, outside the power-telemetry design). From PHAS-7 | the EVM is a finished board: no solder. With the monitors already trusted from 1b, any discrepancy is the charger's | The BQ25798 straight onto the carrier. 2c before 1b. Leaving the bq24074's link plugged (an unpowered pin on /INT). Trusting the POR charge current |
| S4 | **Step 3, carrier rev A (OQ-14)**: under the NUCLEO on morpho (N7); BQ25798 only; four INA228s (P10); the MAX17048 (the carrier stays 1S3P, 7.1 Q3); the SHTC3 and the TCA9548A at 0x71 with RESET on PB14, upstream/downstream exactly as the ports spec says; the RJ11 sensor ports and meter ports 12 and 13; connectors per H6; the step 2 shield's and module board's signal circuits. *Dated note (2026-11-02):* "signal circuits" means the meter pull-ups, RC filters and vane pull-up at the jack end (M7) and the I2C bus, **not** the bq24074-only circuits: the carrier has no ISET network and no VBUS / 3 divider (the BQ25798 reports its own currents and voltages over I2C), so PB1 and PA10 are released and PB10 (CHG) is not wired; PB8 becomes the BQ25798 /INT as at 2c (S3). The carrier also takes change C (deferred from step 1, section 4.6 dated note): PA9 (CN10.19) drives current-limited high-side power per sensor port (PORT-5), the port pull-ups after the switch, the power monitors and the SHTC3 unswitched (PORT-9), with a bench test equivalent to the old exit 9 (step 3). `docs/superpowers/specs/2026-11-02-carrier-board-requirements.md` is the carrier's requirements. **OQ-14 decided 2026-10-30 (7.1 Q7)**: the v1 base board is this carrier. Entry: steps 2 and 2c exited; the underside pin length and clearance measured on a real NUCLEO-WL55JC1 (N7; *satisfied 2026-10-30* by the fit test in 7.1 N7: a standard-height 2.54 mm female socket works); the morpho grid from ST's NUCLEO-64 mechanical drawing; an outline that fits the redrawn chassis. From PHAS-8, NUCL-9 | the one spin, with the charger that ships | A bq24074 carrier first. Layout during 2c |
| S5 | **Steps 4 and 5.** Step 4: the carrier in the printed chassis in the IP66 box, outdoors; the path metric, the VCELL step flag and the power-balance residual (M6, power form) become health-report alarms. Step 5: the custom STM32WL55 board starts only after step 4 shows the ports and power stage frozen; it keeps the N1 pins, addresses, net names and connector families. From PHAS-9 | the product engineer's and metrologist's order; the enclosure is reprinted once | The custom board before a field run |

### 2.6 Documentation truth

| ID | Decision | Why | Rejected alternatives |
|---|---|---|---|
| D1 | **The model first, describing the build to be built.** One commit changes `wiring.toml` to the step 1 v2 topology (section 6.1) and regenerates the build sheet before the bench is touched. The same commit records the 2026-10-28/29 as-run topology (pack in the charger socket, shunt bypassed, ishunt and the charge counters invalid; gauge on the LIPO column; INA VBUS on OUT) in the r0 README history as a deviation. Those runs are **kept** as evidence with ishunt and the charge counters marked invalid by time window; they are not repeated (step 1's exit needs new runs anyway). The word "nominally" leaves every document. From DOCU-1, POWE-11, MEAS-13, R13 | the model is false today and the tests are green (no PB1 or PA10 net; `wiring.toml:119` says ISET stays unconnected; the BATT net puts GBAT.+ after the shunt and the GND net puts CELL.−, RLOAD.2 and CHGR.GND on one breadboard rail) | Modelling the interim cell-in-socket bench. A new r1 tree now (git keeps r0). Hand-edited drawings |
| D2 | **Off-board parts as data.** `[[joint]]` (id, kind with part number, location off-board, members). `[[lead]]` keys: id, a, b; role = force, sense, signal or **supply** (a logic-supply lead such as the bench OLED's, checked by D3 check 3 and exempt from check 1); gauge (AWG); kind = pigtail, solid, cable or dupont; length_mm, max_ma, insulated, exception, domain, segment. `[[link]]` gains id and exception. The connectivity proof treats a joint as a node. Ground members carry `domain = "power"` or `"logic"`. Breakout sockets (CHGR.BATT, CHGR.SYSOUT, GAUGE.BAT1) and the INA228 terminal (INA.X1) are pins. **STAR** (P4) has five positions: 1 pack black, 2 board pigtail black, 3 load return, 4 TIE, 5 spare (kept for step 1b exit (g)'s second 100 Ω; a 222-415 has no sixth position). **Step 1 input:** the breakout's own USB-C from a floating wall adapter, modelled as an off-board part ADAPTER with one cable lead into the CHGR.USBC terminal. **NTC (dated note, 2026-10-30):** the #372 10 kΩ B3950 NTC is off-board, taped to the pack. L_NTC_THERM (sense) runs into the THERM strip; L_NTC_RET (sense) runs to the board-B logic ground rail, not STAR. Logic ground meets STAR only through the TIE, which carries no current in mode A, so it sits at STAR potential: a STAR return and a logic-ground return see the same offset against charger VSS, STAR above VSS by up to 40 mV during a 1 A charge (P4). TS therefore reads up to 40 mV high. With INTC = 75 µA, VCOLD = 2.1 V rising and VHOT = 0.3 V falling (`bq.txt:718–722`), and the breakout's fixed 10 kΩ TS resistor out of circuit (power-telemetry 11.1), the cold trip moves from 28.0 kΩ (+3.5 °C) to 27.5 kΩ (+3.9 °C), and the hot trip from 4.00 kΩ (+47.2 °C) to 3.47 kΩ (+50.9 °C). That is +0.4 °C cold and +3.8 °C hot at 1 A, falling with the charge current to zero at rest. The cold side moves the safe way. The hot shift is the same order as the datasheet's own tolerance (VHOT 270–330 mV; INTC 72–78 µA alone moves the hot trip from 46.1 to 48.2 °C). **The record accepts this shift**: the bq24074 charges only on the indoor bench and retires at step 2c. The a59 strip keeps GND3 alone (P2). **Dated note (2026-10-30), measured values:** a part may carry `measured_ohms` (a resistor's DMM reading; R4–R6 for the M2 divider ratio) and, on the charger, `iset_gain_ppm` (the M2 per-board ISET gain fit) beside `iset_ohms`. D3 checks 8 and 9 take them in place of the nominal values. From DOCU-3, POWE-11, MEAS-13, HYGI-12 | a plain netlist cannot tell a sense wire from a force wire, which is how F2, F3 and F5 stayed invisible | Prose-only joint tables. Per-wire current rules |
| D3 | **Checks** (all without KiCad): (1) no force lead or force net member in a breadboard hole, except the members tagged `exception = "P1 regulator"` (L_REG_VIN, L_TIE, L_NUC_RET and the output chain LK_REG_SHUNT, SHUNT, L_REG_3V3, LK_3V3_CN6_4; P1); every member of that chain carries the tag, so a missing tag fails; *dated note (2026-10-30):* and the chain is contiguous, each member landing where the next starts (`checks.P1_ORDER`), so no planner jumper or rail run carries the regulator current untagged; (2) no sense lead shares a clamp position with a force lead, and each sense lead lands on its declared joint; (3) exactly one conductor joins the power and logic ground domains, and no logic-supply current runs on the board-B ground rail (the OLED's supply and return go straight to NUCLEO pins, the mode-B station return goes on the CN6.7 lead); (4) GBAT/gauge sense is on CELL_POS, upstream of the shunt; (5) nothing but the shunt joins INA VIN+ and VIN−; (6) each breakout test-point pin (CHGR LIPO, OUT, GND×3; INA VIN+, VIN−, VBUS) is alone in its strip; (7) `check_guide` both ways; (8) firmware pins for `board_inputs.c`, `benchlink.c` and the node's ISET/VIN constants, with the comment regex accepting trailing text; (9) the divider ratio in firmware equals the model's resistors. From DOCU-2/3, MEAS-13, POWE-11 | each one is a failure already seen or a drift already present | Review discipline alone (what failed on 10-28) |
| D4 | **Two regeneration tiers**, both stamped with the wiring.toml git blob hash: `make.py sheet` (no KiCad: load, prove, checks, build sheet) on every commit that changes the model; `make.py all` (KiCad, router, renders, schematic PDF) at every step exit and whenever nets change. The build sheet prints both hashes, so a lagging render is visible. Every bench rewire is one commit with the model and the regenerated sheet. From DOCU-4, PHAS-12 | the build sheet is what Clint builds from and already has a no-KiCad freshness test | Never drawing the joints. Full regeneration on every commit (KiCad-bound) |
| D5 | **The wiring guide stays hand-written but carries no fact the model lacks.** Section 2 is checked both ways; section 4 points at the build sheet's power-path table instead of copying it; a new section 6b points at the preflight procedure. From DOCU-5 | the hand copy is what drifted (section 4 still says the shunt is in the path) | Generating the whole guide |
| D6 | **Preflight block**: each run's notes begin with a fenced TOML block (model hash, build-sheet hash, power mode, topology facts, the section 4.3 readings by joint and lead ID with computed mΩ, dV0, wiggle result, deviations, photo name), validated by a new `tools/preflight.py`. A missing or failing block does **not** block a run; it marks the run "wiring unverified". **Dated note (2026-10-30):** the model hash, the build-sheet hash and the preflight status go in `benchlink_log`'s `logger_start` event detail, not in the CSV header, because `prepare_csv` (`tools/benchlink_log.py:240–278`) would set a live CSV aside on a header it does not know. The status is one of: valid; stale (the model or the sheet changed since the run: a hash differs from the current file); failing; missing. The block's top keys include `rewire` and `step_exit` (booleans); C12–C18 are required when either is true. From DOCU-6 | keeps data during debugging while making every run traceable to a drawing | Refusing to log (loses data). Free-text notes (uncheckable) |
| D7 | **Source of truth per step.** Step 1: `hardware/bench-breadboard-r0/source/wiring.toml` (`bench-bb-r0.1` to `bench-bb-r0.3`), with a `revision` field and a git tag per bench revision. Step 1b runs after H01 on the step 2 plate (7.1 Q8), so its source is the protoboard model, which starts with step 2. Step 2: the logical layer moves by file move to `hardware/station-circuit/circuit.toml` (nets, parts, joints, leads, roles, budgets), read by both the breadboard placement and a new `hardware/bench-protoboard-r0` placement (shield and module board). Step 3: the KiCad schematic, held to circuit.toml by a netlist subset test. Rail and INA228 names in circuit.toml equal the `power_config.h` rail table (tested). Profile C is a new profile, not an in-place edit. From DOCU-8, PHAS-12 | the nets already carry no placement, so the split is cheap when a second placement exists, and costly before | Splitting now (path churn mid-rebuild). Redrawing per step |

### 2.7 Conflicts between the areas and how they were settled

| Conflict | Positions | Settled |
|---|---|---|
| Where the pack plugs in | HYGI-1: the pack stays in the charger BATT socket. POWE-3, MEAS-2, PHAS-2: through the shunt | through the shunt (P3). In the socket, the shunt reads zero (F5) |
| How OUT and GND leave the charger | PHAS-2: header pins on female Dupont leads. POWE-2, MEAS-1: the SYSOUT socket | the socket (P2, P6). PHAS-2 keeps two friction contacts in the load path |
| Lever-connector series | POWE-7: 221 with 0.25 mm² ferrules. MEAS-6, PHAS-2: 222 | 222 bare (P7); screw terminals solid only; 221 + ferrules is the fallback if WAGO's sheet disagrees with the distributors |
| Lead length | 60 (POWE), 80 (MEAS), 100 (PHAS), 150 mm (HYGI) | 60 mm pigtails, 50 mm solid links (H7), from the P8 budget |
| Battery-path limits | telemetry 11.2: + ≤ 50 mΩ. POWE-8: + ≤ 50 mV, − ≤ 25 mV. MEAS-7: + ≤ 60, − ≤ 40. PHAS-3: joint ≤ 5 mV, PH ≤ 20 mV | + ≤ 75 mΩ, − ≤ 40 mΩ, PH ≤ 20, clamps and screws ≤ 5 (P8), from the part-by-part estimate; telemetry 11.2 amended |
| Why charges ended early | MEAS-12: maybe the 4–6 h safety timer. POWE-9: timers disabled | timers disabled (schematic); termination is 0.30 A, not 0.1 A (P9) |
| INA VBUS sense point (phase A) | POWE-5: the OUT connector. MEAS-2: the charger OUT header | the OUT connector (P5) |
| Charger SYSOUT − | POWE-4: to STAR. MEAS-2: insulated | insulated (P4) |
| Gauge minus | MEAS-3/4: pigtail − to STAR (Kelvin). POWE-4: unconnected, ground over QT | unconnected (P4); the mode-B error is bounded by N4's CN6.7 lead |
| Logic-to-STAR tie | POWE-4: one fixed tie. MEAS-3: CN6.6 wire in mode A, regulator GND in mode B. NUCL-4: CN6.6 to star | one fixed TIE into the regulator GND strip, both modes (P4) |
| ISET protection | MEAS-8: 10 kΩ + 100 nF. NUCL-5: 4.7 kΩ + 1 MΩ | 10 kΩ + 100 nF + 1 MΩ (M2) |
| Phase-B OR-ing | telemetry 11.3: external Schottky pair, join off the board. PHAS-5: ideal-diode modules and a USB-C sink. POWE-10: the board's D2/D4 | the board's D2/D4 (P10) |
| Extra INA228 pull-ups | telemetry 11.3, PHAS-5: cut the jumpers | no jumper exists; keep and measure (section 1.4) |
| Step 2 force path | POWE-2/3, MEAS-1 carry: soldered pads and charger pins. PHAS-6: the Wago harness unchanged | harness unchanged; modules soldered by header for signals only (S2) |
| Step 2 base | HYGI-4: the printed chassis. PHAS-9: the enclosure only for the carrier | the plate (H1, H9) |
| Carrier input connectors | PHAS-8: JST-XH. HYGI-7, POWE-7: XT60 and cold-rated | XT60 and cold-rated (H6) |
| NUCLEO jumpers in step 1 | NUCL-3: female Dupont on morpho. HYGI-3: solid core to Arduino sockets | solid core to the Arduino headers; morpho only for the OLED and CN7.16 (N3) |
| R8 screw shield | metrologist, product engineer: buy a pre-assembled one now. NUCL-3, PHAS-4: no | none now; #196 soldered at step 2 (N3, N6) |
| Pin remap timing | NUCL-2: after the current runs. PHAS-4: by step 1 exit | change B of step 1, after change A passes (N2) |
| 1b against step 2 | PHAS-1: in parallel. First version of this record: 1b first | sequential: 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5, keeping the existing H01 gate; decided 2026-10-30 (7.1 Q1, Q8; S1) |
| Path-metric threshold | PHAS-11: R_path > 0.5 Ω. MEAS-11: drop > 20 mV after dV0 | the same at 38 mA; the drop form is used because it carries the baseline (M6) |
| Firmware path field | MEAS-11: phase B. PHAS-11: the carrier | the carrier, under a protocol revision; host-side before that (M6) |
| Breadboard current threshold | DOCU-3: BREADBOARD_MAX_MA 50. POWE-1: the regulator exception at 30–60 mA | role-based, with the regulator leads tagged as the one exception (D3) |
| Plate size | HYGI: 30 × 40 cm. PHAS: 30 × 20 cm | 30 × 40 cm (two NUCLEOs, three breadboards and the harness) |
| Divider parts | MEAS-8: 0.1 % at the protoboard. NUCL-5: 1 % | 1 % if available, measured and stored (M2) |

### 2.8 Review of this record (revision, 2026-10-29)

A review of the first version raised the findings below. Every one was checked against the repo
(`wiring.toml`, the build sheet's wire table, `sys_debug.c`, `mod_rain.h`, `next-stages-plan.md`,
`H01-checklist.md`, the ports spec, the shopping list). None was rejected outright; where the fix
differs from the one proposed, the last column says how and why.

| # | Finding | Change made | Where the proposed fix was modified or overruled |
|---|---|---|---|
| R-1 | the pack plug and pack pigtail sit upstream of every sense point, so F4 there fools the gauge and PATH_CELL_OUT cannot see it | P5 and M6 state the coverage limit; new VCELL step flag (M6); exit 4 gains injection case B at the pack lead; segment IDs PATH_PACK_POS/NEG; the build sheet's path table carries the note (6.1) | accepted as proposed |
| R-2, R-13 | exit 5 (gauge within 10 mV of the pack plug at 1 A) fails a healthy build; M4 and P9 mix references | exit 5 split: 10 mV at rest or 38 mA at the pack plug; at 1 A, 10 mV at the gauge's own sense points plus a recorded pack-plug difference within I × R_pack + 10 mV; R_pack from C14; M4 labels "CELL+ node"; P9's mixed-reference item dropped and its cell estimate corrected | both proposed fixes combined: the sense-point check tests the gauge, the pack-plug figure keeps the lead drop visible |
| R-3 | the OLED's supply and return run through the CN7.16 Dupont and the board-B rail where the TIE lands, so N3 is wrong and C8 fails | the jumpers SHUNT.2 strip → OLED 3V3 and OLED GND → board-B ground rail removed; OLED VCC on its own Dupont from CN7.16, GND to CN10.20; N3 corrected; D3 check 3 extended | modified: the proposal gave VCC "a NUCLEO 3V3 pin". The only two are CN6.4 (the hub's) and CN7.16 (the mode-B feed's). CN7.16 is freed by moving the mode-B feed to CN6.4, which R-11 also needs |
| R-4, R-17 | the mode-B regulator output chain is an untagged force path; C15 is measured when the TIE carries nothing | P1's exception names the whole chain; every member tagged; C15 moved to mode B during TX; new rows C20–C23 (including REG VOUT to CN6.4 ≤ 10 mV and a mode-B wiggle) | modified: the chain now ends at CN6.4 through LK_3V3_CN6_4, not at CN7.16 through the removed SHUNT.2 → N:CN7.16 link (R-3, R-11); the 10 mV limit is applied to that chain |
| R-5, R-9 | step 1b exit (e) joins USB-C and solar, against Clint's rule | (e) deleted; replaced by a one-source-at-a-time back-feed check in both directions | modified: "VBUS near 0 V" on the idle input is measured with a 10 kΩ test load, because an SK34A's reverse leakage into an unloaded node can float it to volts and fail a good build; the current limit (≤ 1 mA) is the real test |
| R-6 | the counter-link probe does not reach the meter cable, and at step 2 covers almost nothing | M7: pull-ups and RC at the jack end in every step (moved off the shield in S2); coverage and blind spots stated; the vane's out-of-table reading as the wind-cable check | accepted as proposed |
| R-7 | the 1b path metric divides by a ΔI that does not exist in mode A | M6: drop form in mode A; ΔV/ΔI only with PGOOD inactive and a real step; 1b exit adds a deliberate 100 Ω step at LOAD | accepted as proposed |
| R-8 | leaving the #196's 5V terminal empty does not isolate the 5V net | N6: 5V, VIN, IOREF and AREF header pins not fitted; proto rails traced by meter before any circuit is soldered | accepted as proposed |
| R-10 | Q1 defaulted to "yes" on soldering, and its "no" branch proved four rails on solder | Q1 defaults to "no, wait for Clint"; phase-B positions unpopulated; 1b only on the breadboard; S1, S2 and step 2 rewritten | accepted as proposed. Superseded 2026-10-30: Clint answered Q1 yes (7.1 Q1) |
| R-11 | step 2 solders the PA9 switch and the CN6.4 mode-B feed, which step 1 never proved | step 1 change C and exits 9 and 10; the mode-B feed moves to CN6.4 in step 1; the PA9 switch is soldered at step 2 only if exit 9 passes | the proposal's alternative (the shield keeps CN7.16 as the feed) is rejected: the shield cannot reach morpho and step 2's exit forbids Dupont on NUCLEO pins. Exit 9 is written so that a failure defers the switch to the mux instead of failing step 1. *Superseded in part 2026-11-02:* the PA9 switch and exit 9 moved to the carrier (section 4.6 dated note); the CN6.4 mode-B feed and exit 10 stay in step 1 |
| R-12 | a current balance cannot hold across the BQ25798 | M6: current form for profiles A and B, power form with a measured efficiency band from profile C on; 2c and step 4 use the power form | accepted as proposed |
| R-14 | H01 was made to wait on four-rail work without asking | S1 default restored to the existing gate; Q8 added | accepted as proposed. Confirmed 2026-10-30: H01 first (7.1 Q8) |
| R-15 | the record resolved OQ-14, Clint's open question | Q7 added; S4 gated on it; cascade says "proposed" | accepted as proposed. Superseded 2026-10-30: Clint decided OQ-14 (7.1 Q7) |
| R-16 | the probe faults the cups in calm air when the reed stops closed | M7: cups "suspect", fault only with vane movement or after 24 h; rain keeps the fault rule; test row added | accepted as proposed |
| R-18 | 2c leaves PB8 tied to the bq24074, claims an unchanged harness, and has no charge-current cap | S3: the bq24074's signal link unplugged and modelled; step 1 no longer claims the harness is unchanged at 2c; full C12–C18 and C15/C20–C23 re-run; ICHG ≤ 1 A written and read back before the pack connects | accepted; the cap is enforced with the EVM's /CE jumper until read-back, since the POR default is not verified |
| R-19 | the 1b pull-up limit (≥ 1.1 kΩ) fails good builds | pass at ≥ 0.97 kΩ ((3.3 − 0.4) V / 3 mA), measured value recorded | accepted as proposed |
| R-20 | the Voltaic P110 ends in a 3.5 × 1.1 mm plug | a female 3.5 × 1.1 mm screw-terminal adapter added to P10, step 1b, the shopping list and the model (L_SOLAR_POS/NEG) | accepted as proposed. Superseded 2026-10-30: Clint replaced the panel's 3.5 × 1.1 mm plug with a barrel plug that fits the #4755's DC jack directly (5.5 × 2.1 mm inferred from Adafruit's #4755 page, not measured: confirm with calipers); the female 3.5 × 1.1 mm adapter is dropped, and an Adafruit #368 (female 2.1 mm DC jack to screw terminal) takes its place in P10, step 1b and the shopping list. L_SOLAR_POS/NEG keep their names and land on the #368's terminals |
| R-21 | the cascade misses files; the guard list misses PB2 | `mod_rain.h`, `benchlink_dash.html`, `test_dashboard_js.py`, the 10-18 spec's RJ45 line, the `SMPSRDY` assert, `firmware-event-model.md`, the root README and `wiring.py`'s example added; N8: /CE stays strapped | accepted; for /CE the "stays strapped" option was chosen, so PB10 is released and only PB14 lacks a UFQFPN48 pin |
| R-22 | some later exit criteria cannot be tested as written | step 3 lists its H03 items with numbers; step 4 tests the sealing Clint chose; 2c's TS check uses fixed resistors | also removed: "H08" at step 4, which no repo document defines |

## 3. The phase roadmap

Summary:

| Step | Built | Power profile | Solder | Proves | Exit gate (short) |
|---|---|---|---|---|---|
| 1 | breadboard v2: force path on JST PH + WAGO, signals on the breadboard, NUCLEO on Arduino headers, OLED straight to the NUCLEO, mode-B feed at CN6.4, pins remapped | A (and mode B) | none | the force/sense topology, the budget, the path metric and step flag, the pin map, the mode-B supply chain | section 4.3 checklist (both modes), normal termination, 12 h path, two injection cases, gauge agreement, pulse counts, model tests, mode B 1 h |
| 2 | #196 shield + Perma-Proto module board (phase-B INA228 positions empty); force harness unchanged | A | yes | the soldered signal layer; H01 | H01 24 h, mode B 1 h, USB test, re-run checklist |
| 1b | three more INA228s on the step 2 plate's breadboard and the same harness, after H01 (decided 2026-10-30 (7.1 Q8)) | B | module preparation only (allowed, 7.1 Q1) | four-rail metering, signs, current balance, the D2/D4 OR pair one source at a time | rails vs DMM, 24 h balance with a source change, back-feed both ways, input margin, pull-ups, same-chip ΔV/ΔI on a load step |
| 2c | BQ25798EVM on the step 2 harness (re-terminated) | C | none | the charger configuration and driver | profile C end to end, 24 h power balance in the measured efficiency band, ADC agreement, TS stop and resume, H02 basis, full C12–C23 re-run |
| 3 | carrier PCB under the NUCLEO (OQ-14, decided 2026-10-30 (7.1 Q7)) | C | PCB | everything above in copper, and the PA9 port power switching (change C, from 2026-11-02) | all numbers reproduced, H02, the listed H03 bench items, H04a, the port power cycle, enclosure fit |
| 4 | carrier in the enclosure, outdoors | C | — | field behaviour | field run ≥ H01 length without alarm, H03 proper, the chosen sealing tested |
| 5 | custom STM32WL55 board | C | PCB | integration | re-pass steps 3 and 4 |

The table lists the build order decided 2026-10-30 (7.1 Q1 yes, Q8 H01 first; S1):
1 → 2 (H01) → 1b → 2c → 3 → 4 → 5.

*Dated note (2026-11-02):* the PA9 sensor switch (change C's load switch, exit 9) left the step 1
row for the step 3 row (Clint's decision; section 4.6 dated note).

### Step 1: breadboard v2 (no solder)

- **Built.** Change A: the force path of P3–P6 (pack, CELL+, INA228 terminal, BATT, charger BATT and
  SYSOUT sockets, OUT, STAR, TIE); the gauge and VBUS sense leads; ISET and divider parts (M2); the
  NUCLEO signals moved to the Arduino headers (N3); the OLED's supply pair straight to the NUCLEO
  and the mode-B feed moved to CN6.4 (N3); the base plate (H1). Change B: the cups and rain remap
  (N2). Change C: the QT bus split into a branch to the power monitors and a branch to the sensor
  hub, both on the unswitched 3V3, and the mode-B hour. *Dated note (2026-11-02):* change C no longer
  carries the PA9 sensor load switch or a switched branch; both moved to the carrier (section 4.6
  dated note). Parts
  and joints are listed in section 4.
- **Proves.** P1–P9, M1–M7, N1–N4, the mode-B supply chain into CN6.4, the build sheet's accuracy.
  (Until 2026-11-02 also the PA9 switch; it moved to the carrier.)
- **Carries forward unchanged.** The force harness to steps 1b and 2 (at 2c the BATT and OUT leads
  are re-terminated into the EVM, so 2c re-runs C12–C23 in full), every net name, every MCU pin, the
  CN6.4 mode-B entry, the 0x40 address, the checklist and limits, the path metric, the step flag and
  their IDs.
- **Exit criteria** (all recorded in the run notes of a new evidence run):
  1. The section 4.3 checklist passes, as a valid preflight block.
  2. A full 1 A charge from about 50 % SOC terminates per P9 (benchlink firmware is enough).
  3. The host path metric stays unflagged for 12 h at the 38 mA load (drop − dV0 ≤ 20 mV, no step
     over 10 mV).
  4. **Injection**, at the 38 mA load, input off, each case for at least 5 logged samples:
     (A) a 1 Ω 2 W resistor in place of the CELL+ → VIN+ solid link (downstream of the gauge's sense
     point) raises the drop-form flag of M6 on the next logged sample; removing it clears the flag.
     (B) the same 1 Ω in series with the pack-mating + lead at CELL+ position 1 (the red lead and one
     resistor lead spliced in a spare 222-413, the other resistor lead in position 1) raises the
     **VCELL step flag** on insertion and again on removal, and marks SOC suspect; the drop-form flag
     stays clear, as M6 predicts.
  5. **Gauge agreement**: (a) at rest or at the 38 mA load, gauge VCELL within 10 mV of a DMM at the
     pack plug (as C10); (b) during the 1 A charge, gauge VCELL within 10 mV of a DMM at the gauge's own
     sense points (CELL+ clamp to STAR clamp), and (gauge VCELL − DMM at the pack plug) recorded and
     ≤ I × R_pack + 10 mV, with R_pack from C14.
  6. After change B: cups on PB5 against a hand-counted rotation (± 1 pulse in 100), 20 hand tips on
     PB4 give 20 counts; vane positions unchanged.
  7. `wiring.toml` regenerates with `make.py all`; every D3 check passes, and checks 8 and 9 find
     `power_config.h` holding `POWER_R_ISET_OHM 1000`, `POWER_ISET_GAIN_PPM` and
     `POWER_VIN_DIVIDER_PPM`; the UM2592 checklist (guide section 6) is fully ticked, including PB4,
     PB5 and PB14. *Dated note (2026-10-30):* `checks.check_iset` (check 8's ISET constants) holds
     `POWER_R_ISET_OHM` to the charger part's `iset_ohms` in `wiring.toml` (R9, 1000; a D2 schema
     key) and `POWER_ISET_GAIN_PPM` to the charger part's `iset_gain_ppm` once the M2 fit is stored
     there, or to R_IPD / (R_ISER + R_IPD) = 990099 ppm until then, exactly, and
     `tools/benchlink_log.py`'s `R_ISET_OHM` and `ISET_GAIN` to the same values; `check_divider`
     (check 9) holds the two divider defines to (R4 + R5 + R6) / R6 from R4–R6's `measured_ohms`
     once they are measured (their `ohms` until then). A build-sheet check 2 reading other than 1 kΩ
     changes `iset_ohms` first; the fit and the measured resistors likewise go into the model first
     (M2 dated note).
  8. The USB acceptance test H8(d) is run and recorded (a failure buys the hub, it does not block).
  9. *Removed 2026-11-02 (Clint's decision): the PA9 sensor switch moved to the carrier; step 1 has
     no exit 9 and its number is kept so exit 10 keeps its name. The step 3 port power-cycle test
     replaces it. The text below is kept as history.* ~~**PA9 sensor switch** (change C): firmware drives PA9 low for 16 s and high again 10 times; each
     time the sensors on the switched branch drop off the bus and are found again, `i2c_bus`'s
     recovery leaves the bus working, and the power monitors on the unswitched branch read throughout
     without a NACK. With PA9 low, the switched rail reads ≤ 0.5 V. *Dated note (2026-10-30):* each
     half was 2 s, shorter than the 15 s sample period (`WSMP_SAMPLE_MS`), so most halves addressed
     no sensor and the `#test` lines (recoveries and stuck only) could not show a drop. A half is now
     `WSMP_SAMPLE_MS` + 1 s (a 320 s run), so every part is addressed in every half, and each line
     carries `ack=` and `fail=`: the parts that answered and that failed in the half that ended there
     (bit c for `enum i2c_client` c: 0x001 SHT45, 0x002 BMP581, 0x004 LTR390, 0x008 SHTC3, 0x010
     INA228 0x40, 0x100 MAX17048; `i2c_bus_outcomes`). A `pa9=1` line closes a low half, a later
     `pa9=0` line or `done` a high half. The evidence, per half: in a low half no switched sensor is
     in `ack` and each fitted one is in `fail`; in a high half each is in `ack` again; in every half the fitted monitors (0x010 and 0x100 at step 1) are in `ack` and never in
     `fail`; `recoveries=0 stuck=0` throughout. The 87V reads 3V3_SW in a low half. If the switched rail is held higher
     (sensors back-powered through their I/O pins from the live bus) or the bus stalls while they are
     off, the result is recorded, the switch is **not** soldered at step 2, and port power waits for
     the mux (PORT-5). Either outcome exits this criterion; only an unrecorded result fails it.~~
  10. **Mode B for 1 hour** (the 10-18 bench check 5, moved here so mode B is proved before solder):
      the station runs from the regulator through the CN6.4 entry, readings reach the gateway every
      minute, the mode-B rows of section 4.3 (C15, C20–C23) pass, and no reset is logged.
  Not a step 1 gate: the power-telemetry phase A exit criteria 1–2 (node firmware and gateway). They
  gate H01 (step 2), not soldering.
- **Docs and drawings true at exit.** `wiring.toml` and its build sheet, renders and schematic
  (step 1 topology, tagged `bench-bb-r0.1` after change A, `bench-bb-r0.2` after change B and
  `bench-bb-r0.3` after change C, redefined in place 2026-11-02 without the load switch); the build sheet's power-path table with its coverage note
  (PATH_CELL_OUT does not cover the pack mating);
  guide sections 2, 4, 5, 6, 6b; benchlink README wiring; `board_inputs.c` and its tests;
  `power_config.h` holding `POWER_R_ISET_OHM 1000`, `POWER_ISET_GAIN_PPM` (the M2 fit) and
  `POWER_VIN_DIVIDER_PPM` (the measured ratio): adopted with change A, read by this workflow from
  7.1 P3 "change A as written" (4.4 steps 11–12 fit the ISET network and store the measured
  divider); R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5);
  power-telemetry 11.1–11.3 amendments; D1's word rule holds (a repo-wide grep finds "nominally" in
  no document but this record's rule).

> **Parked 2026-11-02.** Steps 1b, 2, 2c, 3, 4 and 5 (from here to section 4) are parked. It is not maintained until step 1 (the breadboard prototype on its printed base plate) is done: do not build from it or update it to match step 1 changes.

### Step 1b: four rails on the bq24074 (profile B)

Timing (S1), decided 2026-10-30 (7.1 Q1 yes, Q8 H01 first): after step 2's H01 run, on the step 2
plate, in the order 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5. The INA228 module preparation it needs is
allowed (7.1 Q1). It is described here, after step 1, because it extends step 1's harness.

- **Built.** On the plate and the same lever-connector harness; the three extra INA228s sit in a small
  breadboard by their signal pins (test-point strips as in C3), never in the module board until 1b
  exits:
  - load INA228 #5832 at 0x41 (A0 jumper closed): OUT connector → 22 AWG solid → VIN+, VIN− → solid
    → a new WAGO 222-415 **LOAD**, which takes the 100 Ω load, the regulator VIN lead (moved from OUT),
    the load INA VBUS lead and, for the exit test only, a second 100 Ω ½ W whose other lead goes to
    STAR position 5 (the spare, P4);
  - solar INA228 at 0x45 (A0 and A1 closed): one 6 V panel's 2.1 mm barrel plug → an Adafruit #368
    female 2.1 mm DC jack to screw-terminal adapter (L_SOLAR_POS, L_SOLAR_NEG; the panel lead is never
    cut) → solid → WAGO 222-413 **SOLAR_IN** (+ the solar INA VBUS lead) → solid → VIN+, VIN− → solid →
    Adafruit #369 male 2.1 mm barrel plug terminal → the charger's DC jack; the #368's − straight to the
    #369 − terminal. *Amended 2026-10-30 (P10, R-20 superseded):* Clint replaced the panel's original
    3.5 × 1.1 mm plug with a barrel plug that fits the charger's DC jack directly, so the female
    3.5 × 1.1 mm adapter is dropped; that one-time plug swap is not a cut in the metered lead. The jack
    size (5.5 × 2.1 mm) is inferred from Adafruit's #4755 page, not measured: confirm with calipers.
    Without metering (step 1) the panel plugs straight into the charger's DC jack;
  - USB-C INA228 at 0x48 (rework wire from the ADDR1 pad to SDA; A0 default): wall adapter → USB-C
    cable → female USB-C screw adapter (5.1 kΩ Rd) → solid → WAGO 222-413 **USB_IN** (+ VBUS lead)
    → solid → VIN+, VIN− → solid → male USB-C screw plug → the charger's own USB-C; GND female →
    male directly;
  - the battery INA228's VBUS lead moves from OUT to CELL+ position 4;
  - all extra INA228s on the unswitched QT branch (daisy-chained from the battery INA228), high side,
    no header ground.
- **Proves.** The four-rail rail table, signs, the same-chip path metric, the current balance, the
  D2/D4 OR pair (one source at a time).
- **Carries forward unchanged.** Addresses, rail names, sense points by role, the LOAD/SOLAR_IN/USB_IN
  node names (they become carrier net names). After the exit, the three boards move into their
  module-board positions and are soldered by their headers; (a)–(c) and (f) are re-run there as a
  confirmation.
- **Exit criteria.** **USB-C and solar are never connected at the same time, in any test.**
  (a) each rail's current within 2 % + 2 mA of the Fluke 87V in series in that rail's + lead (M1
  dated note: a short steady window, never during a termination run), and its VBUS against the 87V
  at the same point; (b) with no input, battery
  and load currents agree within 1 mA plus charger quiescent; (c) while charging, the current balance
  (M6) stays within 2 mA + 2 % over 24 h, including one change from USB-C to solar made by
  disconnecting USB-C first; (d) at full charge current from USB-C, the charger VBUS header stays
  ≥ 4.6 V and ISET reports full current until CV (if not, a 5.1–5.25 V adapter, not a diode change);
  (e) **back-feed, one source at a time**: with solar alone (the wall adapter unplugged from the USB-C
  chain at the mains end), the USB_IN INA228 reads \|I\| ≤ 1 mA, and with a 10 kΩ test resistor on clip
  leads across the female USB-C adapter's VBUS and GND screws, that voltage stays ≤ 0.5 V (D2
  blocking); then the same with USB-C alone and the panel unplugged at its adapter: the solar INA228
  reads \|I\| ≤ 1 mA and the #368's + and − terminals (2026-10-30: they were the 3.5 × 1.1 mm adapter's), with the same test resistor,
  stay ≤ 0.5 V (D4 blocking). The 10 kΩ test resistor is there because an SK34A's
  reverse leakage into an open node can float it to several volts without any back-feed current;
  (f) SDA and SCL pull-up measured **≥ 0.97 kΩ** to 3V3 with the bus idle ((3.3 − 0.4) V / 3 mA
  sink at VOL), measured value recorded, and SDA high ≥ 2.8 V; (g) every step 1 check re-passes; in
  mode A the path metric stays in its drop form (PGOOD inactive); the same-chip form ΔV/ΔI is shown
  with PGOOD inactive across 30 minutes of the second 100 Ω being switched in and out at LOAD (one
  lever, every 2 minutes), agreeing with the drop form within 0.1 Ω, and in mode B across radio TX
  bursts.
- **Docs true at exit.** The protoboard model with the profile B nets (`hardware/station-circuit/circuit.toml`
  and `hardware/bench-protoboard-r0`, section 6.6; the breadboard model stops at `bench-bb-r0.3`); `docs/hardware/power-metering.md` (new, per power-telemetry 11.3 with this
  record's corrections); `power_config.h` profile B table.

### Step 2: soldered protoboard

- **Built.** S2: the #196 shield (N6) and the full-size Perma-Proto module board, with the three
  phase-B INA228 positions unpopulated and unwired; the step 1 force harness moved unchanged to the
  same plate; an existing full-size breadboard left on the plate for step 1b's boards (S1; 2026-11-02: no half-size board is bought). Everything soldered here
  passed step 1 first. ~~the PA9 switch is fitted only if step 1's exit 9 passed.~~ *2026-11-02:* step 2
  has no PA9 switch (moved to the carrier, section 4.6 dated note); PA9 stays unconnected.
- **Proves.** The soldered signal layer, mode B on the same CN6.4 entry proved in step 1, the 24 h
  H01 run.
- **Carries forward unchanged.** The shield's and module board's netlist (they become the carrier's
  sheets), the JST-XH pinouts (they become on-board nets), the force harness until 2c.
- **Exit criteria.** The guide's section 8 bench checks; section 4.3 re-run after the move, both
  modes; mode B for 1 h; the power-telemetry phase A exit criteria 1–4; ws0's silent-port reopen in
  place and H8(d) passed; the counter link probe (M7) running, with an unplugged JST-XH meter lead
  reported within three probe periods (M7: low on three reads in a row, 15 minutes apart, so 30–45
  minutes after the unplug; `meter_link=rain-open` for the rain lead, `cups-suspect` for the cups
  lead; *dated note 2026-10-30:* this said "within one probe period", which M7's rule cannot meet); no Dupont lead on any NUCLEO pin; the shield height checked
  against the NUCLEO's top parts; H01 24 h acceptance (the 10-18 bench-station spec assigns it here),
  judged on gateway evidence, under the release that power-telemetry D2 decides. *Dated note
  (2026-10-30):* the M7 criterion above (`#status meter_link=ok`) and the power-telemetry phase A
  exit criteria can be met only on a version 6 build: only the version 6 node prints `meter_link=`
  (`firmware/stage0-node/App/tx_console.c:62`), and version 5 firmware reads no power. A "no" on D2
  therefore needs a version 5 backport of the M7 probe and the phase A power reading, which no plan
  carries, or a change to this exit; as written, H01 runs on a version 6 build.
- **Docs true at exit.** `hardware/station-circuit/circuit.toml` and `hardware/bench-protoboard-r0`
  (placement, hand map, photos); guide section 1 build step 2; H01 checklist; CONTEXT-PACK.

### Step 2c: BQ25798EVM (profile C, no solder)

- **Built.** S3. The bq24074's pigtails and its JST-XH signal link are unplugged. The EVM's VBAT/SYS
  terminals take the BATT and OUT harness leads in place of the bq24074's sockets (re-terminated
  with solid leads into the EVM's terminals, so the force path is no longer the one step 1 measured);
  solar into VAC1 through the solar INA228, USB-C into VAC2 through the USB-C INA228 (never both at
  once); I2C on the unswitched QT branch; /INT on the shield's PGOOD position (PB8). ICHG ≤ 1 A,
  the input limit and VREG written and read back before the pack's lever closes (S3).
- **Proves.** The charger configuration (cell count, ICHG, input limits, TS) and the driver.
- **Carries forward unchanged.** The configuration and driver into steps 3 and 5. ISET and the divider
  retire.
- **Exit criteria.** The full section 4.3 checklist re-run (C1–C23, the re-terminated harness is a
  rewire), not only the P8 spans; profile C fill table end to end through the gateway; the efficiency
  η (M6) measured once at three operating points (solar and USB-C, each one at a time, at about
  0.3, 0.6 and 0.9 A charge) and within ± 3 percentage points of the BQ25798 efficiency curve, which
  sets the band; the power balance then stays inside that band over 24 h, including one source change
  made by disconnecting the first source before connecting the second; with no input, the current
  balance (I_bat = I_load + quiescent) within 2 mA + 2 %; BQ25798 ADC (IBUS, IBAT, VBAT, VSYS) against
  the INA228s within the datasheet accuracy; **TS cold-charge inhibit**: the pack has no thermistor,
  so a fixed resistor stands in for the NTC on TS: a resistor equal to the NTC's resistance just past
  the configured cold threshold (computed from the EVM's TS network and the TS settings in SLUSDV2;
  a 10 kΩ B3950 part such as the Adafruit #372 is about 33 kΩ at 0 °C, so a 0 °C threshold takes
  about 39 kΩ) stops charging, and 10 kΩ
  (25 °C) resumes it, three times each, with the charger status register and the battery INA228
  agreeing; the H02 energy basis (Ah and Wh within 5 %) on the bench; whether the BQ25798 has a
  remote battery-sense pin checked in SLUSDV2 (if so, it is Kelvin-routed to the pack side of the
  shunt on the carrier).
- **Docs true at exit.** The power-telemetry profile C table filled; the driver spec; next-stages-plan.

### Step 3: carrier PCB (v1 base board)

- **Built.** S4 and N7. *Dated note (2026-11-02):* with change C (section 4.6 dated note): PA9
  (CN10.19) controls current-limited high-side power per sensor port (PORT-5), the port pull-ups
  supplied after the switch, the power monitors and the SHTC3 unswitched (PORT-9).
- **Proves.** The topology in copper: force on pours, sense on separate Kelvin traces from the shunts'
  inner pads, a single net-tie between power return and quiet ground at the battery negative pad, all
  shunts high side, no low-side shunt anywhere.
- **Exit criteria.** Every step 1, 1b and 2c number reproduced on copper; P8's spans become a 1 A
  bring-up test (battery connector + fuse + shunt + copper ≤ 30 mΩ recorded); H02 (pack Ah and Wh
  within 5 % against the independent reference of next-stages-plan); **the H03 items that run on the
  bench**: (1) cold-charge inhibit on the carrier's own TS network with the 2c fixed-resistor method,
  stop and resume three times each; (2) dawn recovery: the pack discharged until the station stops
  reporting, then a current-limited bench supply standing in for the panel ramped from 0 to 6 V over
  30 minutes (limit 1.7 A, about the P110's short-circuit current, not verified): charging starts and
  the station reports to the gateway without any manual step, within 60 minutes of the ramp's start,
  time recorded; H03 proper (168 h at −35 °C, the 7-day deficit recovered in ≤ 3 solar days) needs the
  chamber and the field and is a step 4 item; H04a; *(2026-11-02)* the port power cycle that replaces
  step 1's exit 9: PA9 off and on 10 times, each half `WSMP_SAMPLE_MS` + 1 s, the switched ports'
  sensors drop off and return, the unswitched monitors and the SHTC3 answer throughout, a switched
  rail reads ≤ 0.5 V with PA9 low (no back-powering through the bus), and `i2c_bus` recovery leaves
  the bus working; the sensor-module-ports phase-2 cable test; net
  equivalence between circuit.toml and the KiCad schematic; the enclosure fit.
- **Docs true at exit.** The KiCad schematic and layout; circuit.toml profile C; the ports spec's OQ-14
  recorded as decided 2026-10-30 (7.1 Q7); the chassis redrawn.

### Step 4: field (carrier in the enclosure)

- **Built.** S5; the redrawn chassis in the IP66 box; glands, latched connectors, tied QT links.
- **Exit criteria.** A field run at least as long as H01 with no path, step or balance alarm; H03
  proper (168 h at −35 °C with cold-charge inhibit; a 7-day deficit recovered in ≤ 3 solar days),
  in a chamber or the field as next-stages-plan arranges; **the sealing Clint chose (ports spec 6.8)
  passes an IP check or a hose test, recorded** (the choice itself is Clint's decision, not a test).
  ("H08" in the first version is removed: no repo document defines it.)
- **Docs true at exit.** The installer subset of the guide (meter ports, power connectors); the
  commissioning preflight per station (station ID, model hash).

### Step 5: custom STM32WL55 board

- **Built and carried.** The carrier's schematic blocks, nets, addresses, connectors and the N1 pins;
  the NUCLEO and ST-LINK drop out.
- **Exit criteria.** Re-pass of steps 3 and 4.

## 4. The Breadboard v2 build (step 1)

**Order of work.** First the model commit (D1): `wiring.toml` and the regenerated build sheet. Once it
exists the build sheet's exact holes rule; this section is the content it must hold and the
list to follow until then. One step at a time; each irreversible action is marked **(cannot be
undone)**.

### 4.1 Parts for step 1

| Qty | Part | Use |
|---:|---|---|
| 3 (+1 spare) | Adafruit #1131 JST-PH extension, 500 mm | cable 1: pack-mating half (pack) + board-mating half (charger BATT); cable 2: board-mating half (SYSOUT); cable 3: board-mating half (gauge) |
| 3 | WAGO 222-415 (5-way) | CELL+, OUT, STAR |
| 2 | WAGO 222-413 (3-way) | BATT; the splice for injection case B (exit 4) |
| — | 22 AWG solid hook-up wire, red, black, one sense colour (yellow) | force links, TIE, regulator leads, sense leads, NUCLEO jumpers |
| 1 | 10 kΩ 1 % | ISET series (at the charger) |
| 1 | 1 MΩ | ISET node pull-down |
| 1 | 100 nF ceramic | ISET node filter |
| 3 | 10 kΩ (1 % if available; today's three may stay) | divider, each measured |
| 1 | 1 Ω 2 W | injection test (exit criterion 4, both cases) |
| 2 | SparkFun BOB-14021, each with a PRT-00132 jack and a 6-pin header | owned as one panel of two boards, separated first (4.4 step 4a); the meter cables' RJ11 landings. Jack and header soldered as module preparation (H5; decided 2026-10-30 (7.1 Q6); change A step 4a) |
| 2 | female-to-male jumper, about 30 cm | the OLED's own VCC (CN7.16) and GND (CN10.20) leads |
| ~~1~~ | ~~pre-assembled high-side load-switch breakout~~ | *removed 2026-11-02:* change C's switch moved to the carrier |
| 1 | STEMMA QT to male header cable (the same kind as the hub's) | change C, the branch to the power monitors (unswitched, as is the hub's since 2026-11-02) |
| 1 | USB-C wall adapter 5 V ≥ 2 A | charger input, floating from the Mac |
| — | plate, standoffs, foam tape, tie mounts, ties, Kapton, heat-shrink, labels | H1, N3, P4 |

### 4.2 The NUCLEO pin contract (UM2592 Rev 4 Tables 17 and 18)

| Function | MCU pin | Arduino (step 1, step 2) | Morpho (step 3, alias) | Step 1 lead |
|---|---|---|---|---|
| I2C2 SDA, SCL | PA11, PA12 | D14 CN5.9, D15 CN5.10 | CN10.5, CN10.3 | QT-to-header cable (unchanged) |
| Hub 3V3, and the mode-B 3V3 entry | 3V3 | CN6.4 | CN7.16 | unchanged (LK_3V3_CN6_4) from the unswitched board-A 3V3 node; in mode B the regulator's output reaches the same node by L_REG_3V3 (P1 regulator chain) |
| Hub GND | GND | CN6.6 | CN7.20 | unchanged (LK_QT_GND_CN6_6) |
| Mode-B supply return | GND | CN6.7 | CN7.22 | new, 22 AWG solid to the regulator GND strip (N4) |
| ISET | PB1 (ADC1_IN5) | A0 CN8.1 | CN7.28 | solid, from the ISET node |
| Wind vane | PB2 (ADC1_IN4) | A1 CN8.2 | CN7.30 | **moves**: the vane jumper from CN7.30 to CN8.2 |
| Charger VBUS / 3 | PA10 (ADC1_IN6) | A2 CN8.3 | CN7.32 | solid, from VIN_SENSE |
| Rain | **PB4** (EXTI4) | A3 CN8.4 | CN7.34 | change B: the rain jumper from CN10.29 to CN8.4 |
| Mux RESET (when wired) | PB14 | A4 CN8.5 | CN7.36 | — |
| Anemometer cups | **PB5** (LPTIM1_IN1, AF1) | D4 CN9.5 | CN10.29 | change B: the cups jumper from CN10.14 to CN9.5 |
| PGOOD | PB8 | D5 CN9.6 | CN10.27 | **moves**: the PGOOD jumper from CN10.27 to CN9.6 |
| CHG | PB10 | D6 CN9.7 | CN10.25 | **moves**: the CHG jumper from CN10.25 to CN9.7 |
| Sensor power enable | PA9 | D9 CN5.2 | CN10.19 | carrier only (2026-11-02): unconnected at steps 1 and 2; on the carrier it enables the port switches |
| Bench OLED signals (bench only) | PA5, PA7, PA4, PC2, PC1 | D13, D11, D10, D8, D7 | CN10.11, .15, .17, .21, .23 | unchanged on morpho (the five OLED signal jumpers) |
| Bench OLED supply (bench only) | 3V3, GND | — | CN7.16, CN10.20 | new, female Dupont straight to the OLED's 3V3 and GND strips on board C; the jumpers SHUNT.2 strip → OLED 3V3 and OLED GND → board-B ground rail removed; the VCC lead is unplugged in mode B |
| Mode-B 3V3 in | 3V3 | CN6.4 (steps 1 and 2) | CN7.16 (carrier only) | the link SHUNT.2 → N:CN7.16 removed; see the first 3V3 row |

Tape "NO 5V" over CN6.5, CN6.8, CN7.18, CN7.24, CN7.6 and CN10.8. CN6.2 (IOREF) and CN5.8 (AVDD) stay
empty.

### 4.3 Pre-run checklist (pass limits)

Meter: the Fluke 87V on its 600 mV DC range in high-resolution mode (0.01 mV), read directly (7.1 Q2).
The C11, C18 and C23 step limits and the 1 A mΩ limits are read on that range. Every reading goes
into the preflight block (D6). Back-probe the pack plug by sliding the probe tip along the wire into the back of the
housing; never pull the plug to probe it. 1 A limits are in mΩ: the mV limit is the mΩ figure times the
INA228 current in amperes.

| # | Condition | Measure | Pass |
|---|---|---|---|
| C1 | pack unplugged, nothing powered | continuity INA228 X1.2 (VBUS) to X1.3 (VIN+) on every INA228 | open (SJ1 open) |
| C2 | as C1 | open the TIE's lever at STAR: STAR to CN6.6 | with the TIE closed, under 0.5 Ω; with the lever open, at least 100 Ω, value recorded. *Dated note (2026-10-30):* this said "open", but the lever-open reading is never OL. Through change A, R9, R_ISER and R_IPD give about 1.01 MΩ. Depending on meter polarity, PB1's ESD diode gives about 11 kΩ plus a diode, and the 100 Ω load, OUT and the regulator give another diode path. Every such path holds 100 Ω or a junction, so a reading under 100 Ω is a second conductor (`checklist.C2_OPEN_MIN_OHM`; the preflight reading carries `lever = "open"`) |
| C3 | as C1 | each breakout test-point strip (charger a50–a53, a59; INA228 VIN+, VIN−, VBUS) holds only its header pin | by eye against the build sheet |
| C4 | as C1 | pack-mating pigtail and board pigtails: red is + by meter against the board's silkscreen; unused black leads insulated | by eye and meter |
| C5 | pack plugged, input off, load on, 1 min settled (about 38 mA) | INA228 current against OUT / 100 Ω | within 2 % + 2 mA |
| C6 | as C5 | pack plug + (back-probed) to charger header OUT | ≤ 10 mV |
| C7 | as C5 | STAR to charger header GND | ≤ 1 mV (the load does not return through the charger) |
| C8 | as C5 | STAR to CN6.6 | ≤ 1 mV |
| C9 | as C5, then the load lever opened | INA228 current at zero load; record dV0 = gauge VCELL − INA VBUS | \|I\| ≤ 1 mA; dV0 recorded |
| C10 | as C5 | DMM at the pack plug against gauge VCELL | within 10 mV |
| C11 | as C5, DMM min/max on C6's span | wiggle each lever, pigtail, PH plug, the TIE, the regulator leads and both USB cables for 30 s; watch vout and vcell in the logger and the A0 (ISET) and A2 (VIN) readings; under the node firmware only (benchlink has no counter), spin the cups through the wiggle: the next observation's wind speed is not zero and STATUS still shows meter_link=ok. *Dated note (2026-10-30):* this row said "the cups count while spinning the cups", which the benchlink logger cannot show | no step ≥ 1 mV on the DMM (about 26 mΩ); no visible step in the logger |
| C12 | charging, first 10 min of CC, I = 0.8–1.0 A, V_ISET about 2.0–2.4 V | + span: pack plug + to header LIPO | ≤ 75 mΩ |
| C13 | as C12 | − span: header GND to pack plug − | ≤ 40 mΩ |
| C14 | as C12 | each JST PH mating; each lever clamp to clamp; each screw (VIN+ link, VIN− link); the two pack-side spans: pack plug + (back-probed) to the CELL+ clamp, and the STAR clamp to pack plug − (back-probed) | PH ≤ 20 mΩ; clamp and screw ≤ 5 mΩ; each pack-side span ≤ 28 mΩ, their sum recorded as R_pack |
| C16 | as C12 | ISET-derived current (R_ISET 1000 Ω) against INA228 battery current | within 10 % + 20 mA (a shunt bypass reads near 0) |
| C17 | as C12, then the input removed for a moment | charger header VBUS while charging; CHG and PGOOD high levels with the input removed (both off) | VBUS ≥ 4.6 V; CHG/PGOOD highs ≤ 3.6 V (VDD + 0.3 V) |
| C18 | as C12, DMM min/max on the + span | wiggle as C11 | no step ≥ 2 mV |
| C19 | NUCLEO | tug each Arduino-header jumper; tape in place; jumpers tied | none moves; tape present |

Mode-B rows: the station running from the regulator (NUCLEO USB unplugged, SHUNT fitted, 100 Ω load
out, OLED VCC lead unplugged), the DMM on min/max across at least 5 radio TX bursts.

| # | Condition | Measure | Pass |
|---|---|---|---|
| C15 | mode B, TX bursts | TIE: STAR to the regulator GND strip | < 1 mV |
| C20 | as C15 | STAR to CN6.6 | ≤ 3 mV |
| C21 | as C15 | the regulator's VOUT pin to CN6.4 (the whole P1 output chain: LK_REG_SHUNT, SHUNT, L_REG_3V3, the board-A 3V3 strip where LK_3V3_CN6_4 starts (QT.V+ in every revision; LSW.IN in the r0.3 draft before 2026-11-02), LK_3V3_CN6_4) | ≤ 10 mV |
| C22 | as C15, between TX bursts | mode-B dV0: gauge VCELL − INA VBUS with the station idle | recorded |
| C23 | as C15, DMM min/max on C21's span | wiggle L_REG_VIN, LK_REG_SHUNT, the SHUNT, L_REG_3V3, LK_3V3_CN6_4, L_NUC_RET (the CN6.7 lead) and L_TIE, for 30 s each | no reset; no step ≥ 2 mV |

When a span fails, measure joint by joint (C14) to find the bad one. C1–C11 and C19 before every
mode-A run; C15 and C20–C23 before every mode-B run; C12–C18 after every rewire and at every step
exit.

### 4.4 Change A: power path and NUCLEO headers (step by step)

Do this with no runs in progress. The 2026-10-28/29 run gets a run boundary in its notes first.

W-numbers are the build sheet's and change on every regeneration; the regenerated sheet's "Changes
from the previous revision" section says which wires come out. *Dated note (2026-10-30):* change A's
sheet is the frozen revision's, `hardware/bench-breadboard-r0/revisions/bench-bb-r0.1/build-sheet.md`
(from `source/revisions/bench-bb-r0.1.toml`, section 6.1): its changes section is against the r0 sheet
the bench was built from. The top-level `build-sheet.md` is the current revision, r0.3, which also
builds change C's QTM branch (and, before 2026-11-02, its load switch); it is not the sheet for change A. This section therefore names links
by their stable model ids (LK_REG_SHUNT: REG.VOUT → SHUNT.1; LK_3V3_CN6_4: the unswitched board-A
3V3 node → N:CN6.4; LK_QT_GND_CN6_6), leads by their ids (L_REG_VIN, L_TIE, L_NUC_RET, L_REG_3V3),
every other jumper by function and endpoints, and the regulator landings by function (the regulator
VIN strip, the regulator GND strip), because the model may move REG and SHUNT to meet H7. From r0.3
(change C), QT.V+ is the switched 3V3_SW net, so LK_3V3_CN6_4 and L_REG_3V3 anchor on the
unswitched board-A 3V3 net (the A:L+ rail, LSW.IN and QTM.V+ are its members, but the chain lands only in the LSW.IN strip, never on the A:L+ rail). *Dated note (2026-10-30):* both land in one
strip itself, so no planner jumper or rail run sits in the chain (P1 dated note): for change A and B
(r0.1, r0.2) the QT.V+ strip (A:c41), from change C (r0.3) the LSW.IN strip (A:c34).
*Dated note (2026-11-02):* with the load switch deferred to the carrier, r0.3 has no LSW and no
3V3_SW: QT.V+ is on the unswitched 3V3 again, as in r0.2, and L_REG_3V3 and LK_3V3_CN6_4 land in
the QT.V+ strip (A:c41) in every revision.

1. **Stop and record.** Stop the logger. Unplug the charger input. Unplug the pack from the charger's
   BATT socket. Photograph the bench as it is, and confirm with the meter which topology it had
   (the as-run record of D1).
2. **Plate.** Mount both NUCLEOs on nylon standoffs, breadboards A, B, C by their adhesive, the hub on
   foam tape. Leave a strip about 15 × 10 cm beside board B, on the charger's socket side, for the
   connectors. Mark the pack's spot next to it.
3. **Check the breakouts.** INA228: continuity X1.2 to X1.3 open (C1); if closed, cut SJ1's trace
   (cutting is not soldering). Charger: the 1A jumper closed, 0.5A and 1.5A open; note which way the
   EN1 and EN2 jumpers are set (expected EN2 = 1, EN1 = 0). *Dated note (2026-10-30):* the build
   sheet carries this as its bench check "Charger jumpers" (generated by `make.py`), before power at
   step 1, not first at step 1b's B1: EN2 low would hold the USB-C input to the 100 or 500 mA VIN-DPM
   modes (section 1.4), and C12–C18 would never see the 0.8–1.0 A charge.
3a. **Cut the THERM jumper (cannot be undone).** *Dated note (2026-10-30):* the r0 bench has no NTC;
   change A fits it (the r0.1 sheet's Add list: L_NTC_THERM, L_NTC_RET). First cut the #4755's THERM
   solder jumper on its back (R10), the breakout's fixed 10 kΩ TS resistor: left in parallel with the
   NTC, TS never exceeds 10 kΩ, the cold trip never fires and the hot trip moves to about 35 °C (the
   r0.1 sheet's NTC bench check). Cutting is not soldering.
4. **Cut the pigtails (cannot be undone).** Cable 1: cut in the middle; trim each half to 60 mm from
   its housing. Cables 2 and 3: keep the board-mating half, trimmed to 60 mm; the pack-mating halves
   go in the spares bag. Strip each lead to the length printed on the WAGO 222; twist; no solder.
   Insulate cable 2's black lead and cable 3's black lead with heat-shrink, folded back.
4a. **Prepare the BOB-14021s (module preparation).** The BOB-14021 comes as a panel of two boards
   (Clint's inventory): separate it into its two boards first, one per meter cable (BOBW wind, BOBR
   rain). Then solder one PRT-00132 jack and one 6-pin header onto each board (H5, 7.1 Q6); then the build sheet's per-conductor continuity check (wind:
   3/4 cups, 2/5 vane; rain: 3/4 bucket).
5. **Remove from board B** (all power-carrying breadboard jumpers and parts): CELL (f39/f40) and its
   pigtail; GBAT (f31/f32) and its pigtail; RLOAD (f49/f53); the three battery-path jumpers; the
   load return via the charger GND header; charger GND to the rail (a second tie); INA228 header GND
   to the rail; INA228 GND to the cell −; cell − to the gauge −; the two SYS_OUT jumpers through the
   header strips; the OLED's 3V3 jumper from the SHUNT.2 strip (it put the OLED current through the
   CN7.16 Dupont); the OLED's ground jumper onto the board-B rail (where the TIE lands); and the
   SHUNT.2 strip → N:CN7.16 link. The r0.1 sheet's "Changes from the previous revision" lists them
   under Remove by net and endpoints (stable ids for links and leads), never by W-number. Keep
   LK_REG_SHUNT (regulator out to the shunt). *Dated note (2026-10-30):* the regulator-GND-to-rail
   jumper is not kept in place: its regulator end, in the regulator GND strip's hole that L_TIE now
   takes (r0.1: B:b16), comes out (the sheet's Remove list), and step 10 fits it again from another
   hole of that strip to the same rail point (the Add list; r0.1: B:d16 to B:L-19). *Dated note
   (2026-10-30), board A:* the r0.1 sheet also moves the meter conditioning on board A: R1, R2, R3 and
   the filter capacitors (C_CUPS and C_RAIN, the r0 sheet's C1 and C2) go into their BOB-14021 pins'
   own strips (M7 dated note), and the jumpers that joined them come out; its section 1 gives the
   holes, its Remove and Add lists the wires.
   *Dated note (2026-10-30):* the board-A-ground-to-board-B-ground link (r0 W29, A:c4 to B:L-63) also
   comes out; the model has no A-to-B ground jumper from r0.1 on, and the sheet against the r0 baseline
   lists it under Remove. A second path from the board-B rail to logic ground would put part of the
   mode-B station return through breadboard strips beside L_NUC_RET (P1, D3 check 3). The board-B
   logic returns (ISET's R_IPD and C_ISET, the divider's R6, the NTC) reach logic ground over the
   regulator-GND-to-rail link, the regulator GND strip and L_NUC_RET to CN6.7.
6. **Fix the connectors** to the plate in a row: CELL+ (222-415), BATT (222-413), OUT (222-415),
   STAR (222-415). Label each.
7. **Battery path** (pack still unplugged): pack-mating half red → CELL+ position 1; black → STAR
   position 1. 22 AWG solid ≤ 50 mm, CELL+ position 2 → INA228 X1.3 (VIN+). 22 AWG solid ≤ 50 mm,
   X1.1 (VIN−) → BATT position 1. Board-mating half of cable 1: red → BATT position 2, black → STAR
   position 2; plug it into the charger's **BATT** socket.
8. **OUT and load.** Cable 2's board-mating half into the charger's **SYSOUT** socket; red → OUT
   position 1 (black insulated). 100 Ω ½ W: one lead in OUT position 2, the other in STAR position 3.
9. **Sense leads.** Cable 3's board-mating half into one MAX17048 socket (the other socket empty); red
   → CELL+ position 3 (black insulated). 22 AWG solid (sense colour) from INA228 X1.2 (VBUS) → OUT
   position 3. CELL+ positions 4–5 stay free (position 4 is reserved for step 1b's battery VBUS lead).
10. **Regulator and TIE.** L_REG_VIN: 22 AWG solid ≤ 100 mm from OUT position 4 into the regulator
    VIN strip on board B. L_TIE: 22 AWG solid ≤ 100 mm from STAR position 4 into the regulator GND
    strip (the regulator-GND link already joins it to the B ground rail): this is the **TIE**.
    L_NUC_RET: 22 AWG solid from NUCLEO CN6.7 to the same regulator GND strip (N4), its length set by
    routing (H7). Fit the regulator-GND-to-rail jumper again, from its new hole in that strip to the B
    ground rail (step 5 dated note), before L_TIE goes into the hole it left. The build sheet gives the
    holes.
11. **ISET.** The 10 kΩ 1 % from the charger ISET strip (column 57, rows c–e; row b sits under the
    charger's board edge) across the centre channel to its own f–j strip: the ISET node. In that node:
    100 nF and 1 MΩ to logic ground (the B ground rail; the build sheet places the jumper), and a solid
    jumper to NUCLEO **CN8.1** (A0). The M2 gain fit comes later, during a CC charge above 200 mA with
    the load off. The fitted gain goes into the charger part's `iset_gain_ppm` in `wiring.toml` first,
    then into `POWER_ISET_GAIN_PPM` and `tools/benchlink_log.py`'s `ISET_GAIN`, with the sheet
    regenerated, in one commit (M2 dated note).
11a. **NTC** (after step 3a; *dated note 2026-10-30*). The #372 10 kΩ NTC: L_NTC_THERM (22 AWG solid,
    the NTC's lead extended) into the charger THERM strip (column 58), L_NTC_RET (its other lead) to the
    board-B logic ground rail, not STAR (STAR position 5 stays the step 1b spare; the TS offset is
    accepted, D2). Tape the bead to the pack. The build sheet gives the holes.
12. **Divider.** Measure the three 10 kΩ resistors and write the values down. They go into
    `wiring.toml` first, as R4–R6's `measured_ohms`, then (R4 + R5 + R6) / R6 in ppm into
    `POWER_VIN_DIVIDER_PPM` and benchlink's `VIN_DIVIDER_PPM`, in one commit (M2 dated note). Two in series from the
    charger VBUS strip (column 60) to a free strip, VIN_SENSE; the third from VIN_SENSE to the B ground
    rail; a solid jumper from VIN_SENSE to NUCLEO **CN8.3** (A2).
13. **NUCLEO header moves** (same MCU pins, no firmware change): the CHG jumper from CN10.25 to
    **CN9.7** (D6); the PGOOD jumper from CN10.27 to **CN9.6** (D5); the vane jumper from CN7.30 to
    **CN8.2** (A1). Solid
    22 AWG for each. Kapton per section 4.2. Tie the NUCLEO jumper bundle to the plate.
13a. **OLED supply and the mode-B feed.** A female-to-male jumper from **CN7.16** (3V3) into the
    OLED's 3V3 strip on board C (column 23, with COLED +); a second from **CN10.20** (GND) into its GND
    strip (column 22, with COLED −). Nothing else on board C touches a ground or 3V3 rail. Then a
    22 AWG solid lead, L_REG_3V3, from the SHUNT.2 strip on board B into the QT.V+ strip on
    board A (A:c41), the 3V3 node where LK_3V3_CN6_4 starts (not the A:L+ rail; the r0.1 sheet
    gives the holes). ~~Change C (section 4.6, the r0.3 sheet) moves both to the LSW.IN strip (A:c34).~~ (2026-11-02: no
    longer; both stay in the QT.V+ strip.) With the SHUNT open (mode A) this lead
    is dead.
14. **Strain relief.** Tie each JST lead to a mount within 30 mm of its housing; tie the pack lead and
    both USB cables at the plate edge.
15. **Before power:** C1–C4. Then plug the pack into its pigtail on the plate, never into the charger.
16. **Discharge checks:** C5–C11. Then connect the wall adapter to the charger's USB-C; at once read
    the build sheet's power check 5 (TS: THERM to GND about 0.75 V at 25 °C; about 0.375 V means R10 is
    still closed: unplug the adapter and do step 3a), then C12–C18 in the first 10 minutes of the
    charge.
17. Write the preflight block (`revision = "bench-bb-r0.1"`, the hashes of the r0.1 model and sheet;
    `tools/preflight.py` checks a frozen revision's block against that revision's files). Tag the model
    `bench-bb-r0.1`. Start the exit runs (section 3, step 1,
    criteria 2–5).

**Mode A to B** (ground untouched): unplug the NUCLEO's USB; open the load's two levers and remove the
100 Ω; unplug the OLED's VCC lead from CN7.16; fit the BATTERY POWER shunt. **B to A**: the reverse,
the shunt out before the USB goes in. The TIE and the CN6.7 lead never move.

### 4.5 Change B: meter pin remap

After change A's checklist passes and the charge-termination run is done:

1. Flash nothing yet. Move the cups jumper from CN10.14 to **CN9.5** (D4); move the rain jumper
   from CN10.29 to **CN8.4** (A3). Solid 22 AWG. *Dated note (2026-10-30):* the sheet is
   `revisions/bench-bb-r0.2/build-sheet.md`; its changes section against r0.1 is exactly these two moves.
2. Flash the node firmware built with `CUPS_PIN` = PB5 (GPIOB, AF1 LPTIM1) and `RAIN_PIN` = PB4
   (EXTI4), from the same commit as the model and guide change.
3. Spin the cups through a counted 100 pulses; tip the bucket 20 times; turn the vane through its
   positions. Wiggle the two moved jumpers while spinning (C11).
4. Tag the model `bench-bb-r0.2`.

### 4.6 Change C: PA9 sensor switch, split QT bus, mode B hour

*Dated note (2026-11-02):* **the PA9 sensor load switch is deferred to the carrier** (Clint's decision,
2026-11-02). Steps 1 (breadboard) and 2 (protoboard) have no sensor power switch. The main session's
call: `bench-bb-r0.3`, never built or released, is **redefined in place** rather than adding r0.4;
r0.1 and r0.2 under `revisions/` stay frozen and unchanged. In r0.3 now: no LSW part and no 3V3_SW or
SENS_EN net; the hub cable's V+ (QT.V+) is on the unswitched 3V3 as in r0.2; L_REG_3V3 and
LK_3V3_CN6_4 land in the QT.V+ strip (A:c41) again, so the P1 chain still has no planner jumper; PA9
is left unconnected (firmware driving it is harmless). The QTM branch is **kept** (redundant without
the switch, but harmless; it keeps S3's unswitched branch, the 1b daisy chain, the QTM tests and the
shopping row). Step 2 below (the second item) and step 4 (exit 9) are dropped; exit 10, the mode-B
hour, stays. The `i2c_bus` power cycle stays a no-op until the carrier. The carrier takes change C as
per-port switching (PORT-5, PORT-9, step 3) with a bench test equivalent to exit 9. Items 1-6 below
are kept as written for history; superseded parts are struck.

After change B. It proves on the breadboard the two circuits step 2 would otherwise solder unproven
(S2): the PA9 switch and the mode-B entry at CN6.4.

1. **Split the QT bus** (model first, as always). Power monitors on an **unswitched branch**: a
   second QT-to-header cable from the board-A 3V3, GND, SDA and SCL strips to the battery INA228,
   daisy-chained to the MAX17048 (and later the 1b INA228s). Sensors stay on the **hub**, whose QT
   cable now takes its V+ from the switch output instead of the 3V3 strip (*2026-11-02:* no longer; it
   stays on the 3V3 strip). GND, SDA and SCL stay
   shared. This mirrors PORT-9 for the monitors: upstream and always powered. *Dated note
   (2026-10-30):* it does not mirror PORT-9 for the SHTC3. PORT-9 keeps the SHTC3 upstream with the
   INA228 and the MAX17048, never on a port and never switched (OQ-3 recommends the BMP581 there too);
   on the bench both stay on the hub, behind the switch on 3V3_SW, so exit 9 and TEST-SENSOR-POWER
   cycle them too. Accepted as a bench difference: exit 9 proves the switch and the shared bus, not the
   carrier's power map. The carrier (step 3) follows PORT-9, not the bench: its SHTC3 is unswitched.
2. ~~**Load switch.** The breakout in board A: IN from the board-A 3V3 node, OUT to the hub cable's V+
   strip, GND to the board-A ground, EN by a solid jumper from **CN5.2** (D9, PA9). Check the
   breakout's own enable pull resistor holds it off at reset.~~ (Removed 2026-11-02.)
3. ~~Flash the node firmware with the sensor switch enabled in `i2c_bus` (today a no-op on the
   breadboard), from the same commit as the model change.~~ (Removed 2026-11-02.)
4. ~~Run exit criterion 9 (section 3, step 1). Record the switched-rail voltage with PA9 low, the
   21 `#test sensor-power` lines (their `ack=` and `fail=` masks are the per-half evidence), and
   whether the bus kept working, whatever the outcome.~~ (Removed 2026-11-02: moved to step 3.)
5. Mode B: C15 and C20–C23, then exit criterion 10 (one hour on the battery).
6. Tag the model `bench-bb-r0.3`. *Dated note (2026-10-30):* change C builds from the top-level
   `build-sheet.md` (r0.3), whose changes section is against the r0.2 sheet.

## 5. Shopping list (merged)

Buy now (step 1):

| Qty | Item | Note |
|---:|---|---|
| 4 | Adafruit #1131 JST-PH battery extension cable, 500 mm | 3 cut, 1 spare |
| 10 | WAGO 222-413 (3-way) | BATT now; SOLAR_IN, USB_IN at step 1b; spares. Confirm the 0.08 mm² fine-stranded rating on WAGO's own data sheet before ordering (P7) |
| 6 | WAGO 222-415 (5-way) | CELL+, OUT, STAR now; LOAD at step 1b; spares |
| 1 set | 22 AWG solid hook-up wire, red, black, yellow | skip colours already owned |
| 1 | pre-cut / pre-formed 22 AWG solid jumper kit (140–350 pieces) | H3 |
| 2 | 10 kΩ 1 % resistor | ISET series; one spare |
| 4 | 10 kΩ 1 % resistor | divider, if today's are 5 %; measured either way |
| 2 | 1 MΩ resistor | ISET pull-down; one spare |
| 2 | 100 nF ceramic capacitor | ISET node; one spare |
| 2 | 1 Ω 2 W resistor | injection test (both cases); one spare |
| ~~2~~ | ~~pre-assembled high-side load-switch breakout (3.3 V, current-limited, active-high enable, headers fitted; part not chosen)~~ | *Removed 2026-11-02: change C's switch moved to the carrier; not bought.* change C; one spare. Confirm it ships assembled. *2026-10-30:* not yet sourced: DigiKey had no matching breakout with a current limit (the TPS22918EVM was the nearest, and has none) |
| 1 | STEMMA QT to male header cable | change C, the power monitors' branch (kept 2026-11-02) |
| 2 | female-to-male jumper, about 30 cm | OLED supply leads; skip if owned |
| 1 | USB-C wall adapter, 5 V ≥ 2 A (5.1–5.25 V output preferred) | skip if one is owned |
| 1 | plywood or MDF, about 30 × 40 cm, 6–9 mm | scrap is fine |
| 1 | nylon standoff kit, M2.5 and M3 | |
| 1 | double-sided foam mounting tape | |
| 1 pack (20) | adhesive cable-tie mounts | |
| 1 pack (100) | small cable ties | |
| 1 | Kapton tape | skip if owned |
| 1 | heat-shrink assortment | skip if owned |
| 1 | cable labels or label tape | ST-LINK serials (H8) |
| 1 | wire stripper for 22–26 AWG | skip if owned |
| 1 | 10 kΩ 1 % resistor | TS stand-in at 25 °C for the step 2c cold-charge test (S3); bought now so it is on hand (7.1 Q4) |
| 1 | about 39 kΩ 1 % resistor (the computed cold-threshold value: a 10 kΩ B3950 NTC is about 33 kΩ at 0 °C) | TS stand-in past the cold threshold, step 2c; confirm the value against the EVM's TS network first |

> **Parked 2026-11-02.** The later-step parts lists, from here to section 6, are parked. It is not maintained until step 1 (the breadboard prototype on its printed base plate) is done: do not build from it or update it to match step 1 changes.

Step 1b (bought with the step 2 list, so the parts are on hand when H01 passes; 7.1 Q1, Q8):

| Qty | Item | Note |
|---:|---|---|
| 3 | Adafruit INA228 #5832 | load 0x41, solar 0x45, USB-C 0x48 |
| 1 | Adafruit #369 male 2.1 mm DC plug to screw terminal | solar into the charger's DC jack |
| 1 | Adafruit #368 female 2.1 mm DC jack to screw-terminal adapter | takes the panel's 2.1 mm barrel plug into SOLAR_IN, so the panel lead is never cut. *2026-10-30:* replaces the female 3.5 × 1.1 mm adapter (R-20 superseded): Clint swapped the panel's plug for one that fits the charger's DC jack |
| 1 pair | inline USB-C screw-terminal adapters: female with 5.1 kΩ Rd, male plug | model not chosen; confirm assembled and 5 V only. *2026-10-30:* no inline USB-C screw-terminal pair found on DigiKey; chosen instead: Adafruit #4090 (USB-C female breakout with 5.1 kΩ CC resistors) + Adafruit #5978 (USB-C male plug breakout), both need soldering; *2026-11-02:* ordered, 5 each |
| 1 | 100 Ω ½ W resistor | the deliberate load step at LOAD (exit g) |
| 1 | 10 kΩ resistor and two clip leads | the back-feed test load (exit e); skip if owned |
| — | small breadboard (half size) | *dropped from this list 2026-10-30*: not bought. *2026-11-02:* step 1b uses one of the full-size breadboards already owned (three Elegoo, two spare BB830s), on the plate (S1, step 2) |

Step 2 (buy when step 1 exits):

| Qty | Item | Note |
|---:|---|---|
| 2 | Adafruit Proto-ScrewShield (Wingshield) R3 kit #196 | one per node plus a spare; Clint may need more (one per node) |
| 2 | Adafruit Perma-Proto full-size breadboard PCB | module board plus a spare |
| 1 | Arduino R3 stacking header set | for #196 |
| 1 | JST-XH 2.5 mm kit: pre-crimped leads, 2-, 5- and 6-pin housings and PCB headers | signal links only |
| 2 | STEMMA QT to male header cable | soldered into the shield: unswitched branch (power monitors) and switched branch (hub) |

Step 2c (EVM ordered 2026-11-02, Q4): BQ25798EVM: 2 units, ordered 2026-11-02 with the step 1 order,
per 7.1 Q4; used at step 2c; do not buy again. Its TS stand-in resistors are on the step 1
list.

Step 3 (do not buy yet): Vishay WSK2512R0100BEA × 4 plus spares; 2 × 19 2.54 mm female sockets × 2
per carrier (*2026-10-30:* standard height, by the 7.1 N7 fit test; 2 × 19 parts come only at
1000-piece minimums, so standard 2 × N female headers cut to 2 × 19); XT60 pair (H6); an inline pack fuse and holder, sized at the carrier
schematic for the 1S3P path (7.1 Q3); about 3 A solar fuse; 16 AWG silicone wire; the cold-rated solar connector
(chosen at the schematic). 7.1 Q3's "current connectors" is read as H6's connector families.

Conditional: one powered USB hub only if H8(d) fails; one BusBoard BB830 only if signal strips fail repeatedly (H2); WAGO 221-413/415,
0.25 mm² insulated ferrules and a ratchet crimper only if WAGO's sheet does not cover 26 AWG on the 222
(P7).

Not bought (rejected): ideal-diode modules, a USB-C sink breakout, external Schottky diodes, a
pre-assembled screw shield for step 1, 0.1 % divider resistors, screw-terminal RJ11 breakouts (BiPOM
BRK6P6C-S-FT; 7.1 Q6), a new meter (the Fluke 87V is owned; 7.1 Q2), a calibrated shunt or a DC clamp
meter for the shunt checks (the 87V in series is the reference: M1 dated note).

*Purchasing status (2026-11-02):* ordered from DigiKey on 2026-11-02 (nothing before): the 2 BQ25798EVMs
(7.1 Q4), 5 BusBoard BB830, 10 × 1 Ω 2 W (injection test), 30 × 100 Ω ½ W and the rest of the step 1 and
step 1b parts Clint chose, including the USB-C pair (5 × Adafruit #4090 and 5 × #5978). Change C's
load-switch breakout is not bought: change C moved to the carrier (2026-11-02). `docs/poc-shopping-list.md`
("Purchasing status") holds the part numbers and quantities.

## 6. Cascade: what must change

Each item names the file, what changes and the decision behind it. "New" files do not exist yet. Nothing
generated is edited by hand.

*Dated note (2026-11-02):* change C's PA9 load switch is deferred to the carrier (section 4.6 dated
note). The rows below that make PA9 live at step 1 or say "step 1 exit 9" are superseded as follows:
`i2c_bus.lit.md`/`i2c_bus.h` keep the power-cycle no-op until the carrier (comments say so);
TEST-SENSOR-POWER in `tx_console.c` and its tests in `tests/test_tx_machine.py`, the PA9 seam in
`firmware/host/` and `i2c_bus_outcomes` stay, as the carrier's bench test (step 3), not step 1's;
`i2cscan.c` and `benchlink.c` may keep driving PA9 high (harmless with PA9 unconnected); the
breadboard model (6.1) has no LSW, 3V3_SW or SENS_EN, and D3 check 8 no longer holds `POWER_PIN`
to a model net; the guide's PA9 row is "carrier only".

### 6.1 Breadboard model and generator (`hardware/bench-breadboard-r0/`)

The model lands as three revisions, each a self-consistent tree with its own regeneration (`make.py
all` and `sheet`). `bench-bb-r0.1` = change A with the D2–D4 machinery. r0.2 = change B with the N2
firmware, `tests/test_board_inputs.py`, the guide's cups and rain rows and the READMEs. r0.3 = change C
with the PA9 firmware (*2026-11-02:* redefined in place without the load switch: the split QT bus and
the mode-B hour; section 4.6 dated note). Clint makes the git tags. *Dated note (2026-10-30):* the three revisions were
written in one uncommitted tree, so no commit holds r0.1 or r0.2. They are kept as **frozen models**,
`source/revisions/bench-bb-r0.1.toml` and `bench-bb-r0.2.toml` (`make.py`'s `HISTORY`), each the whole
bench as its change leaves it; `make.py sheet` (and `all`) regenerates each one's sheet and
`connections.json` into `revisions/<revision>/`, against the revision before it (r0.1 against the r0
sheet, `source/baseline-2026-10-29.json`), and the current `wiring.toml` (r0.3) against r0.2. A frozen
model gets the connectivity proof and the D3 checks; the wiring guide and the firmware are held to the
current revision only. The r0.1 and r0.2 models land L_REG_3V3 in the QT.V+ strip, where LK_3V3_CN6_4
starts (P1 dated note; there is no LSW.IN before change C, and since 2026-11-02 none in r0.3 either:
r0.3 lands it in the QT.V+ strip too). `tools/preflight.py` checks a block against
the frozen model and sheet its `revision` names. The tags then mark the bench, not a tree: each is the
commit at which Clint finished that change on the bench.

| File | Change | From |
|---|---|---|
| `source/wiring.toml` | add `revision`; **remove parts** CELL, GBAT and RLOAD from board B; **add off-board parts**: PACK (1S3P 6600 mAh, 3.0–4.2 V, pins +, −), RLOAD (off-board, between joints), the #1131 halves as leads; **add `[[joint]]`s** WAGO_CELL_POS (222-415), WAGO_BATT (222-413), WAGO_SYS_OUT (222-415), WAGO_STAR (222-415); **add `[[lead]]`s** with role, gauge and length: L_PACK_POS, L_PACK_NEG (#1131, 26 AWG assumed, ≤ 60 mm, force), L_CELL_INA and L_INA_BATT (22 AWG solid, ≤ 50 mm, force), L_BATT_POS, L_BATT_NEG (#1131, force), L_SYSOUT_POS (force), L_SYSOUT_NEG (insulated), L_GAUGE_POS (sense), L_GAUGE_NEG (insulated), L_VBUS (sense, X1.2 → WAGO_SYS_OUT), L_REG_VIN and L_TIE (22 AWG solid, ≤ 100 mm, force, `exception = "P1 regulator"`), L_NUC_RET (CN6.7 → the regulator GND strip, force in mode B, same exception; its length is set by routing and bounded by C20 and C21, not by 100 mm: H7), L_RLOAD_A, L_RLOAD_B; **off-board NTC and input** (D2): part NTC (#372 10 kΩ B3950, taped to the pack) with L_NTC_THERM (sense, into the THERM strip) and L_NTC_RET (sense, to the board-B logic ground rail, not STAR); part ADAPTER (the floating wall adapter) with one cable lead into CHGR.USBC; STAR position 5 stays a spare (P4: kept for step 1b exit (g)'s second 100 Ω); **pins for sockets and terminals**: CHGR.BATT1/BATT2, CHGR.SYSOUT1/SYSOUT2, GAUGE.BAT1+/− , INA.X1_VINM/X1_VBUS/X1_VINP; **rewrite nets**: CELL_POS = PACK.+, WAGO_CELL_POS, INA.X1_VINP, GAUGE.BAT1+ (and phase-B INA VBUS); BATT = INA.X1_VINM, WAGO_BATT, CHGR.BATT2, CHGR.LIPO (test point); SYS_OUT = CHGR.SYSOUT2, CHGR.OUT (test point), WAGO_SYS_OUT, RLOAD.1, INA.X1_VBUS, REG.VIN; GND split by `domain`: power = PACK.−, CHGR.BATT1, CHGR.GND/GND2/GND3 (test points), RLOAD.2, WAGO_STAR; logic = everything else, with L_TIE the only crossing; remove INA.GND and GBAT.− from GND; **add nets** ISET_CHGR (CHGR.ISET, R_ISER.1), ISET (mcu PB1, N:CN8.1, R_ISER.2, C_ISET, R_IPD), VIN_SENSE (mcu PA10, N:CN8.3, R5.2, R6.1) and the divider R4/R5/R6 from CHGR.VBUS; **move members**: CHG to N:CN9.7, PGOOD to N:CN9.6, VANE to N:CN8.2; change B (N2, approved 2026-10-30, 7.1 N2): CUPS `mcu = "PB5"` with N:CN9.5, RAIN `mcu = "PB4"` with N:CN8.4; **[nucleo] ties** for each Arduino/morpho pair of the same MCU pin (CN9.7–CN10.25, CN9.6–CN10.27, CN8.2–CN7.30, CN9.5–CN10.29, CN8.4–CN7.34, CN8.1–CN7.28, CN8.3–CN7.32, CN8.5–CN7.36) and CN6.7 to the GND tie; **notes**: CHGR note (drop "CE, ISET and THERM stay unconnected"; R_ISET 1 kΩ; TMR to GND; ITERM 0.30 A; LIPO/OUT/GND header pins are test points), INA note (SJ1 open, checked; pull-ups are a resistor pack; shunt 15 mΩ 1 %), pack label "1S3P 6600 mAh, 3.0–4.2 V"; the power-telemetry 11.1 rows for the thermistor and CN8 stay; its "charger input as a 2-pin pigtail" row is replaced by "the breakout's own USB-C or DC jack, from a floating wall adapter"; **OLED supply** (R-3): OLED.VCC and COLED.+ joined to N:CN7.16 by their own lead, OLED.GND and COLED.− to N:CN10.20 by their own lead, both off every breadboard rail (the generator's W28 and W30 disappear); **mode-B feed and the P1 chain** (P1, R-11, D3 check 1): remove the `[[link]]` SHUNT.2 → N:CN7.16 (W32 in the r0 sheet); give the kept links stable ids, LK_REG_SHUNT (REG.VOUT → SHUNT.1), LK_3V3_CN6_4 (the unswitched board-A 3V3 node → N:CN6.4) and LK_QT_GND_CN6_6; add lead L_REG_3V3 (force, 22 AWG solid, length by routing, bounded by C20 and C21) from SHUNT.2 to the unswitched board-A 3V3 node; tag `exception = "P1 regulator"` on every member of the chain by id: L_REG_VIN, L_TIE, L_NUC_RET, LK_REG_SHUNT, SHUNT, L_REG_3V3 and LK_3V3_CN6_4. From r0.3 (change C) QT.V+ is the switched 3V3_SW net, so the chain re-anchors on the unswitched 3V3 net (section 4.4): LK_3V3_CN6_4 and L_REG_3V3 land in the LSW.IN strip (A:c34) itself, never on the A:L+ rail and not on QT.V+, with no planner jumper and no rail contact in the chain (P1 dated note); REG note "feeds CN7.16" → "feeds CN6.4 through the board-A 3V3 node (same net as CN7.16)"; **change C**: part LSW (load-switch breakout, board A), part QTM (second QT-to-header cable, unswitched branch to the power monitors), net SENS_EN (`mcu = "PA9"`, N:CN5.2, LSW.EN), net 3V3_SW (LSW.OUT, QT.V+), LSW.IN on 3V3; the guide's PA9 row stops being "protoboard only"; **meter conditioning**: a note on R1/C1, R2/C2 and R3 that they stay at the jack end beside the BOB-14021s (M7), carried into the step 2 placement; **segment IDs**: PATH_PACK_POS and PATH_PACK_NEG on L_PACK_POS and L_PACK_NEG, PATH_CELL_OUT from WAGO_CELL_POS to WAGO_SYS_OUT; **step 1b is not in this model**: its joints, parts and leads (WAGO_LOAD, WAGO_SOLAR_IN, WAGO_USB_IN; INA_LOAD, INA_SOLAR, INA_USB at 0x41, 0x45, 0x48; RLOAD2; the #369 plug; the USB-C adapter pair; L_SOLAR_* and L_USB_*; each INA VBUS sense lead; the battery INA VBUS lead moved to WAGO_CELL_POS) belong to the protoboard model (`hardware/bench-protoboard-r0`, 6.6), because 1b runs after H01 on the step 2 plate (7.1 Q8, D7); r0 stops at `bench-bb-r0.3`. *Dated note (2026-10-30):* the `[nucleo]` ties gain PA9 (CN5.2 = CN10.19), the I2C pins (CN5.9 = CN10.5, CN5.10 = CN10.3) and the OLED pins' ARDUINO aliases (CN10.11 = CN5.6, CN10.15 = CN5.4, CN10.17 = CN5.3, CN10.21 = CN5.1, CN10.23 = CN9.8; UM2592 Tables 17 and 18), so the proof and the bench check see a second landing on them; CHGR gains `iset_ohms = 1000` (R9, section 1.4) for exit 7's ISET check. *Dated note (2026-10-30), second:* parts may carry `measured_ohms` and CHGR `iset_gain_ppm` (D2, M2), so checks 8 and 9 follow the measured divider and the fit; L_REG_3V3 lands in the strip where LK_3V3_CN6_4 starts, the QT.V+ strip (A:c41) in r0.1 and r0.2 and the LSW.IN strip (A:c34) from r0.3, not on the A:L+ rail (P1 dated note). *Dated note (2026-10-30), third:* the meter filter capacitors are C_CUPS and C_RAIN (not C1 and C2, the checklist row ids); R1.1, C_CUPS.1, R2.1, C_RAIN.1 and R3.1 land in their jack pin's own strip (M7 dated note, `checks.check_meter_at_jack`); r0.1 and r0.2 are frozen models under `source/revisions/` (6.1 dated note) | P1–P7, M2, M6, M7, N1–N4, D1, D2, D7, H7, 7.1 Q8 |
| `source/wiring.py` | `load()` accepts `[[joint]]`, `[[lead]]`, `domain`, `role`, `exception`, `insulated` and the `id` of a `[[link]]`; `HEADERS` gains CN8 (1 × 6) and CN9 (1 × 8) with their x positions; it calls the D3 checks in `source/checks.py` (row below); `check_guide` both ways ("protoboard only" / "carrier only" Wiring-cell exemptions; "bench only" rows must exist); `FIRMWARE` holds `firmware/benchlink/App/benchlink.c` (PGOOD_PIN, CHG_PIN, ISET_PIN, VIN_PIN) and the node's ISET_PIN and VIN_PIN in `board_inputs.c` (`wiring.py:579–585`); `PIN_DEFINE` accepts `/* PB1 = A0, CN8.1: ... */` and other trailing text, and the example comment `/* PC0 */` (now `wiring.py:575`) and the `('PC0')` example (now `wiring.py:96`) become PB5; a `power_path_segments()` helper that names PATH_POS, PATH_NEG, PATH_PACK_POS, PATH_PACK_NEG and PATH_CELL_OUT from the leads, for the build sheet. *Dated note (2026-10-30):* `FIRMWARE` (now `wiring.py:579`) also holds `POWER_PIN` (SENS_EN, PA9) in benchlink.c, and `firmware/i2cscan/App/i2cscan.c` (SDA_PIN, SCL_PIN, POWER_PIN) and `oled.c` (CS, SCK, MOSI, RST, DC), whose OLED nets the model has; a part may carry `iset_ohms` | D2, D3, M6 |
| `source/checks.py` (new) | the D3 checks 1–9 as functions (`check_force_off_breadboard`, `check_sense_landings`, `check_single_tie`, `check_gauge_upstream`, `check_shunt_only`, `check_test_point_strips`, the firmware-pin and divider checks); check 1 requires the P1 chain tagged member by member (an untagged L_REG_VIN, L_TIE, L_NUC_RET, LK_REG_SHUNT, SHUNT, L_REG_3V3 or LK_3V3_CN6_4 fails); check 3 also fails when a logic-supply return (OLED.GND, the NUCLEO supply return) lands on the board-B ground rail; check 9 compares `POWER_VIN_DIVIDER_PPM` and benchlink's `VIN_DIVIDER_PPM` with R4–R6; the H7 lead lengths (pigtail halves ≤ 60 mm, solid force links ≤ 50 mm, L_REG_VIN and L_TIE ≤ 100 mm, L_REG_3V3 and L_NUC_RET by routing with C20 and C21 as their bound, signal jumpers ≤ 200 mm); lead geometry (each lead's ends on its declared joint position or pin, no sense lead in a force lead's clamp position). *Dated note (2026-10-30):* `check_iset` (check 8's ISET constants, step 1 exit 7): `POWER_R_ISET_OHM` against CHGR's `iset_ohms`, `POWER_ISET_GAIN_PPM` against R_IPD / (R_ISER + R_IPD) in ppm, and `tools/benchlink_log.py`'s `R_ISET_OHM` and `ISET_GAIN` against the same | D3, H7 |
| `source/checklist.py` (new) | the section 4.3 rows and pass limits (C1–C23), the P8 budgets (+ span 75, − span 40, each pack-side span 28, each PH mating 20, each clamp and screw 5 mΩ), the meter (Fluke 87V, 600 mV DC range, 0.01 mV high resolution; 7.1 Q2) and `blob_sha1` (the wiring.toml git blob hash); one source for `make.py`'s checklist and `tools/preflight.py` | M5, P8, D4, D6, 7.1 Q2 |
| `source/flying.py` | lanes for CN8 and CN9; `NUCLEO_GAP` grows; off-board joints drawn as labelled boxes beside board B with their leads | D2, D4 |
| `source/build_pcb.py`, `source/build_schematic.py`, `source/render.py`, `source/models.py`, `source/pcb_read.py` | CN8/CN9 footprints and 3D headers; joints and leads in the schematic (symbols for the lever connectors, the pack, the load) and in the 3D view; force leads drawn heavier than sense leads | D2, D4 |
| `source/make.py` | new `sheet` subcommand (no KiCad); build sheet gains: an off-board joints table, a leads table (role, gauge, length), a power-path table by joint and lead ID with budget mΩ, implied mV at 38 mA and at 1 A and blank measured columns, the section 4.3 checklist, the mode A/B steps (ground untouched), both hashes; bench-check texts: remove "up to about 5 V … confirm FT" (replace with the measured 2.9 V and the VDD + 0.3 V rule), remove "CE, ISET and THERM stay unconnected", add the NO-5V tape rule and CN10.8; the power-path table carries the coverage note "PATH_CELL_OUT covers CELL+ to OUT only; the pack mating (PATH_PACK_POS, PATH_PACK_NEG) is covered by C6/C11 at preflight, C12–C14 at 1 A and the VCELL step flag live", and an R_pack row; the checklist includes the mode-B rows C15, C20–C23; the bench-check text "In mode B unplug W28" → "unplug the OLED's VCC lead from CN7.16"; the W38–W42 OLED note gains the two supply leads (CN7.16, CN10.20). *Dated note (2026-10-30):* the bench checks gain "Charger jumpers" (4.4 step 3: 1A closed, 0.5A and 1.5A open, EN1/EN2 recorded, expected EN2 = 1, EN1 = 0) before power at step 1; the ARDUINO-header check covers CN5 (D8–D15: PA9, PA11, PA12) with CN8 and CN9, and lists CN10.19, CN10.3 and CN10.5 among the aliases that stay empty; the OLED note lists its ARDUINO aliases that stay empty | D4, D6, M5, M6 |
| `connections.json` (generated), `source/baseline-2026-10-29.json` (new) | the connection list of each regeneration, by net and endpoints (with the stable id of each link and lead, and the W-number for reference only); the bootstrap baseline is the r0 list before change A, so the first sheet's "Changes from the previous revision" section names the wires that come out (section 4.4 step 5); each later sheet compares against the committed `connections.json`. *Dated note (2026-10-30):* each sheet compares against the revision before it, regenerated from its frozen model (6.1 dated note), not against a committed `connections.json`; `revisions/bench-bb-r0.1/` and `revisions/bench-bb-r0.2/` hold the frozen revisions' sheets and lists | D4, section 4.4 |
| `build-sheet.md`, `connections.json`, `bench-breadboard.kicad_sch`, `bench-breadboard.kicad_pcb`, `bench-breadboard-3d.kicad_pcb`, `layout.json`, `models/*.wrl`, `models/view.json`, `renders/*.png`, `renders/schematic.pdf` | regenerated (sheet tier on the model commit; all tier at each step exit) | D4 |
| `README.md` | history: the 2026-10-28/29 as-run deviation; the meter-connector note (`README.md:91–92`) gains: the v1 sensor ports are RJ11 per the ports spec, no RJ45 in v1; parts still to get (section 5); the two regeneration tiers; the model hash of the committed renders; the three revisions `bench-bb-r0.1` to `bench-bb-r0.3` (tags made by Clint) and the end of r0 at r0.3 (step 1b is in the protoboard model) | D1, D4, D7, H6 |

### 6.2 Tests

| File | Change | From |
|---|---|---|
| `tests/test_breadboard.py` | new tests: no force lead in a breadboard hole (and the regulator exception is the only one); a sense lead sharing a clamp position with a force lead fails; exactly one power/logic ground crossing (a second tie fails); gauge sense on CELL_POS upstream of the shunt; nothing but the shunt joins VIN+ and VIN−; each test-point strip holds one pin; ISET and VIN_SENSE nets exist with their mcu pins; divider ratio equals `POWER_VIN_DIVIDER_PPM` and benchlink's `VIN_DIVIDER_PPM` (nominal 3000000); CN8 and CN9 pins exist; Arduino/morpho ties agree with UM2592; `check_guide` two-way (a guide row with no model net fails; regression: delete a guide-listed net from a copy and expect failure); benchlink pin comments parsed; the build sheet lists every joint and lead once; the build sheet carries both hashes; `make.py sheet` output equals the committed sheet; update `test_the_hub_returns_straight_to_the_nucleo` for the new GND domains; the P1 chain is tagged member by member and nothing else is excepted; OLED.VCC reaches N:CN7.16 and OLED.GND reaches N:CN10.20 with no breadboard rail on the way; the 3V3 net has no link to N:CN7.16 from SHUNT.2; SENS_EN exists with `mcu = "PA9"` at N:CN5.2; the meter pull-ups share a board and a column group with their BOB-14021 (jack end); the build sheet's power-path table carries the coverage note. *Dated note (2026-10-30):* the bench checks carry "Charger jumpers" and the CN5/CN8/CN9 line with CN10.19 as PA9's alias; `check_firmware` fails on a moved `POWER_PIN` in benchlink or i2cscan and on a moved OLED pin in `oled.c` | D3, D4, M6, M7 |
| `tests/test_breadboard_checks.py` (new) | each function of `source/checks.py` against the committed model (passes) and against a copy broken in one place (exactly that check fails): a force lead in a hole, an untagged P1 chain member, a second tie, a sense lead in a force clamp position, a lead over its H7 length, L_REG_3V3 or L_NUC_RET judged by C20/C21 rather than 100 mm; `source/checklist.py`'s limits equal section 4.3 and P8. *Dated note (2026-10-30):* `check_iset`: the old 890 Ω, a gain 1 ppm off, a network change, a measured R_ISET moved into the model first, the host logger's defaults, and missing values each fail exactly that check | D3, H7, M5 |
| `tests/test_board_inputs.py` | cups on GPIOB pin 5 with AF1 LPTIM1 (GPIOB clock); rain on PB4 with EXTI4 and `EXTI4_IRQHandler`; EXTI9_5 no longer arms rain; the link probe (pull-down read, three lows with no edge → fault, restored pull-up); **the probe adds no false count on an open cups link** (the LPTIM1 count read before and after the probe window, its own edge subtracted, M7's dated note); rain: three lows with no edge → fault; **cups: three lows with no edge → suspect, not fault (calm air with the reed held closed); suspect → fault when the vane changes position in the same window, or after 24 h**; a vane reading outside the direction table → wind cable flagged; the `DEBUG_RF_LDORDY_ENABLED` and `DEBUG_RF_SMPSRDY_ENABLED` asserts present | N2, M7 |
| `tests/test_tx_machine.py` | TEST-SENSOR-POWER (the bench command behind step 1 exit 9: PA9 low for `WSMP_SAMPLE_MS` + 1 s and high again, each half's `ack=`/`fail=` part masks checked); the `#status` field `meter_link=` (ok, rain-open, cups-suspect, cups-open, vane-out-of-table); the radio `link` key (`n.status()['link']`, `test_tx_machine.py:730`, `:745`, `:925`, `:1132`) unchanged | M7, step 1 exit 9 |
| `tests/test_link.py` | ws0 `ReceiverLink` reopens an open-but-silent port after 90 s (SILENT_REOPEN_S), doubles the wait to 400 s, resets it on any received line; no reopen at the RX's 60 s `#alive` cadence; each reopen a `serial-reopen` event, not a failure; `receiver-silent` still at 180 s | H8 |
| `tests/test_benchlink.py` | the logger (`tools/benchlink_log.py`): the R_ISET 1000 Ω default and the `--iset-gain` default (990099 ppm, nominal) in `charge_ma`; the model hash, the build-sheet hash and the preflight status in the `logger_start` event detail; the CSV header unchanged | section 1.4, M2, D6 |
| `tests/test_benchlink_dash.py` (new) | `tools/benchlink_dash.py`: the M6 flags (PGOOD gate, ≥ 30 mA, dV0, the 20 mV and 10 mV-step drop flags; the VCELL step flag: 8 mV with \|ΔI\| < 2 mA flags, a load step does not, a 1 Ω pack-lead injection does; SOC suspect for 30 min after the last flag; injection case A raises only the drop flag and case B only the step flag); the M7 cross-checks; the "CELL+ node" label and the VCELL − I × R_pack estimate; P9's termination check with R_pack; `--rewrite-iset` changes only the rows after a `logger_start` whose detail has `r_iset=` the old value; a structural test of `tools/benchlink_dash.html` (an element for each flag) | M4, M6, M7, P9, D6 |
| `tests/test_dashboard_js.py` | it tests only `ws0/static/app.js` (`test_dashboard_js.py:1`); it gains a test that a `serial-reopen` gateway event draws a marker. The benchlink flags are not here: they are computed in `tools/benchlink_dash.py` and tested in `tests/test_benchlink_dash.py` | H8 |
| `tests/test_preflight.py` (new) | `tools/preflight.py` returns valid for a good block; stale when a hash differs from the current `wiring.toml` blob or `build-sheet.md`; failing for a missing joint or lead ID or a limit breach; missing when there is no block; C12–C18 required when `rewire` or `step_exit` is true, and not otherwise | D6 |
| `tests/README.md` | counts and new files | — |

### 6.3 Firmware

| File | Change | From |
|---|---|---|
| `firmware/stage0-node/App/board_inputs.c`, `board_inputs.h` | `CUPS_PIN` PB5 on GPIOB (AF1 LPTIM1, GPIOB clock in `HAL_LPTIM_MspInit`); `RAIN_PIN` PB4, `EXTI4_IRQn`, a new `EXTI4_IRQHandler`; the EXTI9_5 handler no longer serves rain (still clears line 6, button B3); `_Static_assert` on `DEBUG_RF_LDORDY_ENABLED == 0`; header comment updated (UM2592 checked); the `_Static_assert` on `DEBUG_RF_SMPSRDY_ENABLED == 0` (PB2, the vane; `sys_debug.c:142–150`); the M7 link probe with the rain fault rule, the cups suspect rule and the vane out-of-table check | N2, M7 |
| `firmware/stage0-node/App/mod_rain.h` | line 3: "on the PB5 interrupt" → "on the PB4 interrupt (EXTI4)"; line 12: "from the EXTI5 interrupt" → "from the EXTI4 interrupt" | N2 |
| `firmware/stage0-node/App/i2c_bus.lit.md` (tangles `i2c_bus.c`), `i2c_bus.h` | `i2c_bus.h:65` "only on the protoboard, a no-op on the breadboard", and the same claim at `i2c_bus.lit.md:75–76` and `:487` → the sensor switch on PA9 is live from step 1 change C (if exit 9 passes; otherwise it stays a no-op until the mux and the comment says why); the power monitors are on the unswitched branch, so recovery that cycles PA9 never drops them. *Dated note (2026-10-30):* `i2c_bus_outcomes` (the parts that answered and failed since the last call, `tests/test_i2c_bus.py` `test_outcomes_name_the_clients_that_answered_and_failed`) gives exit 9 its per-half evidence | M6, step 1 exit 9 |
| `firmware/stage0-node/App/i2c_bus.lit.md`, `i2c_bus.h`, `board_inputs.c` | mux RESET = PB14 (A4, CN8.5 / CN7.36), wired with the mux (`WS_I2C_MUX=1`): the "TBD" in `i2c_bus.h`'s `i2c_bus_mux_reset_line` comment and at `i2c_bus.lit.md:76–77` → PB14; `board_inputs.c` defines `i2c_bus_mux_reset_line` on PB14 (a no-op today) | N5 |
| `firmware/stage0-node/App/power_config.h` | `POWER_R_ISET_OHM 1000` (was 890); `POWER_ISET_GAIN_PPM 990099` (10 kΩ series and 1 MΩ pull-down, nominal until the per-board fit); `POWER_VIN_DIVIDER_PPM 3000000` in place of the integer `POWER_VIN_DIVIDER 3`, nominal until measured; shunt 15,000 µΩ nominal, verified | M1, M2, section 1.4 |
| `firmware/common/power_regs.c`, `power_regs.h` | `divider_mv_ppm` and `divider_uv_ppm` (the ppm divider, beside the integer `divider_mv`) and `unscale_ppm` (the ISET gain taken out of the pin voltage) | M2 |
| `firmware/stage0-node/App/tx_console.c` | TEST-SENSOR-POWER (bench builds: PA9 low for `WSMP_SAMPLE_MS` + 1 s and high again, for step 1 exit 9, each `#test` line with the half's `ack=`/`fail=` part masks from `i2c_bus_outcomes`); the `#status` field `meter_link=` (M7). It is not `link=`, which is the radio state at `tx_console.c:62` | M7, step 1 exit 9 |
| `firmware/host/i2c_sim.c`, `i2c_sim.h`, `wsmp_harness.c`, `tx_harness.c` | the host stubs follow: the PB5/PB4 pins and the probe's pull-down reads, the PA9 switch and the mux RESET seam, TEST-SENSOR-POWER and `meter_link=` | N2, N5, M7 |
| `firmware/benchlink/App/benchlink.c` | pin comments: `PB8 = D5, CN9.6 (CN10.27)`, `PB10 = D6, CN9.7 (CN10.25)`; `VIN_DIVIDER_PPM` (nominal 3000000) in place of `VIN_DIVIDER 3` (`benchlink.c:157`, used at `:413`), with the conversion staying in microvolts through `divider_uv_ppm`. R_ISET and the ISET gain are not in the firmware: the packet carries V_ISET in µV and `tools/benchlink_log.py` applies them. `bl_pkt.h:16–18`'s comment ("I = 400 * V_ISET / R_ISET") gains that the host applies R_ISET and the gain. *Dated note (2026-10-30), change C:* the TX drives PA9 high at start and keeps it high (`POWER_PIN`, `PA9 = D9, CN5.2 (CN10.19)`; `sensors_on`, before the bus starts). From r0.3 the hub's QT V+ is the load switch's output, so without it the SHT45 is unpowered under benchlink (step 1 exit 2 runs on it) and sits back-powered through the unswitched branch's pull-ups; D3 check 8 holds the pin to the model's SENS_EN | N1, M2, 4.6 |
| `firmware/i2cscan/App/i2cscan.c` | *Dated note (2026-10-30), change C:* PA9 driven high at start and kept high (`POWER_PIN`, `sensors_on`, a `#power` line, 2 ms for the switch and the SHT45's power-up), so the B2 address scan finds the hub's sensors after change C; D3 check 8 holds its `POWER_PIN`, `SDA_PIN` and `SCL_PIN` and `oled.c`'s five OLED pins to the model | 4.6, B2 |
| `firmware/stage0-node/README.md`, `README.md` (root) | pin map PB5/PB4; Arduino positions; the remap note | N2 |
| `firmware/benchlink/README.md` | wiring table (CHG D6 CN9.7, PGOOD D5 CN9.6, ISET via 10 kΩ with 100 nF and 1 MΩ, divider ratio measured); "VBUS jumper to OUT" → VBUS sense lead to the OUT connector; the gauge on CELL+; "Known limits": the bypass is fixed in step 1, the old runs' ishunt invalid; R_ISET 1 kΩ (the CSV `charge_ma` of earlier runs reads 12 % high); a section on the path metric and cross-checks | M2, M6, M7, P5, section 1.4 |

### 6.4 Tools and gateway

| File | Change | From |
|---|---|---|
| `tools/benchlink_log.py` | `R_ISET_OHM = 1000.0` (was 890; comment: 1 kΩ R9 behind the 1A jumper, ICHG 0.89 A typ): adopted with change A, read by this workflow from 7.1 P3 "change A as written"; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5); `--iset-gain` (default 990099 ppm, nominal until the per-board fit), `--model` (the wiring.toml whose hashes are logged) and `--preflight` (the run's preflight block); R_ISET, K and the load resistor stay options (power-telemetry 12.1); the model hash, the build-sheet hash and the preflight status (valid, stale, failing or missing) go in the `logger_start` event detail (`:583`), not in the CSV header, because `prepare_csv` (`benchlink_log.py:240`) sets aside a live CSV whose header it does not know | section 1.4, M2, D6 |
| `tools/benchlink_dash.py` | the step 1 flags only: the M6 path metric and flags (PATH_CELL_OUT drop form, per-mode dV0 option), the VCELL step flag, the SOC "suspect" band, the M7 cross-checks, P9's termination check with R_pack; vcell labelled "CELL+ node" with the R_pack-corrected estimate (R_pack from the preflight block); `--rewrite-iset` recomputes `charge_ma` only for the rows after a `logger_start` with `r_iset=` the old value (earlier `charge_ma` reads 12 % high). Not here: step 1b's current balance, the same-chip ΔV/ΔI and step 2c's power balance need the load, solar and USB-C INA228s, which the one-INA228 benchlink packet does not carry (`firmware/benchlink/App/bl_pkt.h:60–61`); they come from the node's profile B/C fields through ws0, in a host file named when step 1b starts | M4, M6, M7, P9 |
| `tools/benchlink_dash.html` | the page behind the dashboard: the VCELL step flag, the SOC "suspect" band, the "CELL+ node" label and the R_pack-corrected estimate, the drop-form flag with its coverage note, the M7 flags (the step 1 flags only) | M4, M6, M7 |
| `tools/preflight.py` (new) | validates the preflight TOML block against the model: joint and lead IDs, the limits and meter from `source/checklist.py`; returns one of four statuses: valid; stale (a hash in the block differs from the current `wiring.toml` blob or `build-sheet.md`); failing (a missing ID or a limit breach); missing (no block); C12–C18 required when `rewire` or `step_exit` is true | D6, M5 |
| `tools/h01_report.py`, `tests/test_h01_report.py` | the serial gaps beside the H01 score: each `serial-lost` and `serial-reopen` row and each run of missing `#alive` minutes in the window, so the H8(d) replug acceptance and every H01 run show a gap or none | H8 |
| `tools/README.md` | the preflight tool, the dashboard's step 1 flags and `h01_report`'s gap list | D6, H8 |
| `ws0/link.py`, `ws0/__main__.py` | the open-but-silent reopen: SILENT_REOPEN_S = 90 s, doubling to 400 s, reset on any received line, so the RX's 60 s `#alive` (`firmware/stage0-node/App/app_rx.c:70`) never triggers it; each reopen a `gateway_events` row of kind `serial-reopen` at level warn, with the port path and silent_s; `receiver-silent` at 180 s (`ws0/__main__.py:25`) stays the outer alarm | H8 |
| `ws0/static/app.js`, `ws0/README.md`, `docs/openapi.json` | `app.js`: a marker for `serial-reopen` beside RX boot, serial-lost and receiver-silent (`app.js:960`); `ws0/README.md`: the `link.py` row states the reopen; `openapi.json`: `serial-reopen` in the `gateway_events` kind list (`openapi.json:2128`); `docs/web-dashboard.md` in 6.5 | H8 |

### 6.5 Documents

| File | Change | From |
|---|---|---|
| `docs/hardware/bench-station-wiring.md` | section 1: build step 1 = step 1 (changes A, B, C; no current through the breadboard), build step 2 = steps 2, 1b and 2c in the order Clint set (7.1 Q8: 2 and H01, then 1b, then 2c; shield + module board, harness unchanged until 2c; 1b on the plate's breadboard after H01), build step 3 = carrier and beyond; the prove-before-solder rule; section 2 diagram and table: PB5 cups D4 CN9.5 / CN10.29, PB4 rain A3 CN8.4 / CN7.34, PB2 A1 CN8.2 / CN7.30, PB8 D5 CN9.6 / CN10.27, PB10 D6 CN9.7 / CN10.25, PB1 and PA10 as station rows (no longer "bench only"), PB14 mux RESET, CN6.7 mode-B return, the NO-5V list with CN10.8, the never-used list (D0/D1, D2/PB12, D3/PB3, A5/PB13); section 3: cups and rain pins; section 4 rewritten: the target force path, force and sense roles, the pointer to the build sheet's power-path table, the F5 note on the 2026-10-28/29 runs, the charger input from a floating wall adapter; section 5: the mode steps with ground untouched; section 6: tick PB2, PB5/PB4, PB8, PB10, PB1, PA10, PB14 from UM2592 Tables 17–18, add PB4 NJTRST and the LDORDY assert, add CN10.8; new section 6b "Power-path acceptance" pointing at the build sheet and section 4.3 of this record; section 8: add the pulse-count and link-probe checks, the PA9 power-cycle check and the mode-B hour on the breadboard; section 2 PA9 row: "protoboard only … Not on the breadboard" → "step 1 change C from a breakout; soldered at step 2 only if proven"; section 2 OLED: the supply pair CN7.16 and CN10.20; section 5 mode B: the regulator feeds CN6.4 through the SHUNT and the board-A 3V3 node (same 3V3 net as CN7.16), the OLED VCC lead unplugged in mode B; section 3: the meter pull-ups and RC at the jack end in every step (M7); remove "nominally" | D5, N1–N4, P1–P6, M7, 7.1 Q8 |
| `docs/hardware/power-metering.md` (new) | as power-telemetry 11.3, corrected: the rail table (net, monitor, address, 15 mΩ 1 % 2 W shunt, VBUS sense point), signs, phase B topology with the board's D2/D4 as the OR pair and each monitor in its source's lead, the #5832 pull-up resistor pack (no cut; 1.11 kΩ measured), the 0x48 ADDR1 pull-down on SDA, the input-margin check | P10, section 1.4 |
| `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` | dated amendments: section 1 "R_ISET about 890 Ω" → 1 kΩ, 0.89 A typ, and the "Official wiring" row's headers (CHG CN9.7, PGOOD CN9.6, with the morpho aliases); section 2 exit criterion 4 with P9's numbers; 8.6 shunt "measured" → nominal, verified; 9.2 and 11.3 pull-up cut removed (no jumper), 0x48 pull-down note; 9.5 ISET source (10 kΩ series, 100 nF, 1 MΩ; gain); 11.1 gauge minus unconnected, INA VBUS lead to the OUT connector, joints and leads per D2, the charger input row replaced; 11.2 budget per P8; 11.3 OR pair per P10; 12.1 path metric host-side per M6, with its coverage limit (not the pack mating) and the VCELL step flag; the gauge VCELL under current labelled "CELL+ node" (M4); the "Kelvin" wording per M4 and P4 (the gauge's red lead on the CELL+ node, its minus unconnected, ground over QT): section 2's phase A row (`:54`), section 3.2's `batt_mv` row (`:108`) and `load_mv` row (`:111`, "jumpered to OUT" → the VBUS sense lead to the OUT connector); the balance check: current form for profiles A and B, power form with the efficiency band for profile C (M6), wherever 3.x or 12.x states a Kirchhoff current residual for profile C; section 1 and 2: USB-C never with solar, also in tests (step 1b exit e); section 15 D4 and D5: adopted with change A, read by this workflow from 7.1 P3 'change A as written'; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5); 15: new risk row for the path metric's firmware field (step 3 revision); section 17: each row keeps its 2026-10-29 status and gains a dated 2026-10-30 amendment from 7.1. *Dated note (2026-10-30):* also section 2's phase B row (`:55`) and section 9.3's VBUS-net row (`:669`): the battery INA228's VBUS lead moves to CELL+ at step 1b (P5, M4; the design's own section 17 P5/M4 row), not "may stay on OUT"; and the status lines (`:4`, and section 17's closing line): implemented on `feat/power-telemetry`, uncommitted, pending the gates (this record's section 8) | P4, P5, P8–P10, M1, M2, M4, M6, 7.1 |
| `docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md` | OQ-14 (section 11, its row in the open-questions table, `:1236`) decided 2026-10-30 (7.1 Q7); add a dated line: the v1 base board is a carrier under the NUCLEO on morpho underside sockets, with four INA228s (0x40, 0x41, 0x45, 0x48), the MAX17048 (1S3P, 7.1 Q3) and the SHTC3 upstream of the mux; the layout waits for the measured underside pin length and clearance (N7); mux RESET = PB14 (A4, CN8.5 / CN7.36) in sections 4.1, 6.x and 13's guide row; section 4.1 "the breadboard itself does not change" amended for step 1 v2; 4.2 pull-ups: the #5832 has no cut jumper; PORT-5: the bench result of step 1 exit 9 (whether a switched sensor rail works without the mux) noted as evidence | N5, N7, S4, 7.1 Q3, Q7 |
| `docs/superpowers/specs/2026-10-19-bench-breadboard-wiring-design.md` | dated amendment: power leaves the breadboard (joints and leads modelled), CN8/CN9 headers, pin remap, two regeneration tiers | D1–D4, N2 |
| `docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md` | dated notes: lines 48–49 cups PB5 (LPTIM1_IN1, D4 CN9.5), rain PB4 (EXTI4, A3 CN8.4); line 28 "Outdoor cabling and RJ45 modules come later" → v1 sensor ports are RJ11 (ports spec), no RJ45 in v1; line 54 PA9 "a load switch on the protoboard. Not on the breadboard" → proved on the breadboard first (step 1 change C); line 284 check 5 (mode B for one hour) now also a step 1 exit on the breadboard | N2, H6, S2 |
| `docs/firmware-event-model.md` | line 17: "the rain gauge on EXTI9_5 (PB5 …)" → "the rain gauge on EXTI4 (PB4)" | N2 |
| `README.md` (root) | line 202 "the anemometer input filter on PC0" → PB5 | N2 |
| `docs/superpowers/plans/2026-10-18-wsmp-bench-station.md`, `docs/superpowers/plans/2026-10-19-bench-breadboard-wiring.md` | dated "superseded pins" note (history kept) | N2 |
| `docs/superpowers/plans/2026-10-29-power-telemetry.md` | the deferred-rows paragraph (`:27–30`) and the fixed-decisions bullet (`:56–63`, "R_ISET about 890 Ω"): dated notes that N2 is approved (7.1 N2) and owned by change B, the M7 probe precedes H01, and R_ISET 1 kΩ and M2 are adopted with change A, read by this workflow from 7.1 P3 'change A as written'; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5) | N2, M2, M7, section 1.4 |
| `docs/next-stages-plan.md` | *dated note (2026-10-30):* the phase B row (`:100`): the battery INA228's VBUS sense lead moves from OUT to CELL+ position 4 at step 1b (it said the "VBUS jumper stays on OUT"); the step list 1, 2 (H01), 1b, 2c, 3, 4, 5 against Stages 0–4, decided 2026-10-30 (7.1 Q8): the Stage 1 gate in section 1 (the Stage 1 row at `:41` and the paragraph at `:45–50`: Stage 1 work follows H01) is kept, so 1b, the solar and USB-C rails, runs after H01; H02 basis at 2c, H02 and the bench H03 items at 3, H03 proper at 4; the BQ25798EVM ordered 2026-11-02 (7.1 Q4) and its place at 2c; carrier connectors per H6; the carrier stays 1S3P (7.1 Q3), with telemetry D1 (the pack is about half the PRD reserve) still open; rows that put RJ45 in Stage 2 get a dated note: v1 sensor ports are RJ11 (ports spec), RJ45 is v2 only | S1, S4, H6, 7.1 Q3, Q4, Q8 |
| `docs/radio-energy-policy.md` | `:88` "The carrier's cell count is open (build-progression record, Q3)" and `:96` "The build-progression record's Q3" → the carrier stays 1S3P, decided 2026-10-30 (7.1 Q3) | 7.1 Q3 |
| `docs/CONTEXT-PACK.md` | section 2 (state: breadboard v2 not built yet, power off the breadboard), section 6 (next steps: model commit, change A, checks, change B, change C, step 2 and H01, then 1b, then 2c), section 7 (working rule: no current through a breadboard contact; prove before solder), section 8 (map: this record, power-metering.md, preflight tool) | all |
| `docs/poc-shopping-list.md` | "Breadboard build" section (`:68`) replaced by section 5's step 1 list; later steps listed as later; the BQ25798EVM is ordered (2026-11-02, 7.1 Q4: do not buy); its TS stand-in resistors are bought now with step 1; no screw-terminal RJ11 breakout (7.1 Q6); the BOB-14021 jack and header pins soldered now as module preparation (7.1 Q6); no meter purchase (the Fluke 87V is owned, 7.1 Q2); the "JST PH 2-pin socket with short tails (a pigtail)" row (`:87`) replaced; line 43 (Voltaic P110): note its 3.5 × 1.1 mm plug and add the female adapter for step 1b; line 45 (S7V8F3) "Feeds the Nucleo's 3V3 pin (CN7.16)" → "feeds the NUCLEO's 3V3 at CN6.4 (steps 1 and 2) or CN7.16 (carrier)" | section 5, N3, P10, 7.1 Q2, Q4, Q6 |
| `docs/H01-checklist.md` | the Stage 0 gate wording (line 6) stays; H01 runs on step 2, before four-rail work (Q8, decided); preconditions: step 1 exit (including mode B on the CN6.4 entry), preflight pass including the 1 A spans, H8(d) passed, ws0 reopen deployed, counter link probe running | S1, H8, D6, 7.1 Q8 |
| `docs/runbook-moving-boards.md` | the RX alone on a direct Mac port (7.1 Q5: both NUCLEOs were on one hub when the RX stalled); cable labels by ST-LINK serial; replug only the TX side | H8, 7.1 Q5 |
| `docs/failure-modes.md` | rows: a contact fault at the pack plug or pack lead (upstream of every sense point: fools the SOC, invisible to PATH_CELL_OUT, caught by the VCELL step flag); a logic-supply return on a breadboard ground rail (the OLED case); force current through a breadboard contact; shunt bypassed by the charger socket; sense lead on the wrong node; a second ground tie; an open counter link; a silent USB port; the `:288` row ("INA228 VBUS jumper on the wrong net, or the gauge on OUT") updated: the gauge's red lead at CELL+ position 3, its minus insulated, ground over QT (P4, M4), and build-sheet check 8 per step 1 exit 5 | F1–F6, P4, M4 |
| `docs/web-dashboard.md` | the markers list (`:63`, "RX boot, serial-lost and receiver-silent") gains serial-reopen; the `gateway_events` row (`:200`) names the `serial-reopen` kind | H8 |
| `firmware/i2cscan/README.md` | the troubleshooting rows `:119–122` follow change A: the gauge on its CELL+ sense lead (not leads L4, L5 on the cell), the pack through its #1131 pigtail and the INA228 shunt (P3), never in the charger's BATT socket; the "`i=` near zero" row names the bypass (F5) | P3, P5, F5 |
| `hardware/poc-enclosure-r1/README.md` | nothing but the carrier goes in; print the coupon now; the four-INA228 slot requirement becomes a carrier-outline requirement (step 3); its layout ids P1–P10 (the table at `README.md:121–130` and the diagram labels at `:50–51`) are renamed E1–E10 so they do not read as this record's P1–P10 | H9 |

### 6.6 New trees (when their step starts)

| Path | When | Content |
|---|---|---|
| `hardware/station-circuit/circuit.toml` | first day of step 2 | the logical layer moved from wiring.toml (D7) |
| `hardware/bench-protoboard-r0/` | step 2 | shield and module-board placements, hand map, photos, generated sheet |
| `docs/superpowers/specs/<date>-bq25798-driver-design.md` | step 2c | the driver and profile C configuration |

### 6.7 Owned by Clint (the workflow does not touch these)

- The 2026-10-28/29 run notes under `evidence/`: a deviation note (pack in the charger socket; ishunt
  and charge counters invalid; earlier `charge_ma` 12 % high).
- The run boundary note before change A.

## 7. Questions for Clint (answered 2026-10-30)

Asked on 2026-10-29. Clint answered every one in a formal survey on 2026-10-30 (section 7.1, which
governs); the defaults below are kept as history. INVENTORY.md, cited in 7.1 Q2, is Clint's inventory
in the parent electronics directory, outside this repository.

| # | Question | Default (historical, replaced by 7.1) | What it decides | Answer (7.1) |
|---|---|---|---|---|
| Q1 | Is **INA228 module preparation** allowed before the protoboard: closing the A0/A1 solder jumpers on the three extra #5832 boards and the 0x48 rework wire from the ADDR1 pad to SDA? The #5832 has no address pins on its header (ADDR0/ADDR1 reach VCC only through those jumpers), so this is solder on the breakouts, though no circuit wiring | **no: wait for Clint.** Nothing is soldered on an unanswered question | yes: step 1b runs on the breadboard (after H01 by default, Q8), then the boards are soldered into the module board. No: the module board's phase-B positions stay unpopulated and unwired, 1b waits until Clint allows it (or until an INA228 breakout with address pins on its header is found), and 2c waits for 1b. 1b's proof never moves onto the soldered board | yes: module preparation allowed; 1b on the breadboard harness after H01 |
| Q2 | Does your multimeter have a **200 mV range** (0.1 mV resolution)? | assume yes | no: the 38 mA screen (C6–C11) loses its resolution, so every joint check happens at 1 A, or buy a meter | Fluke 87V, 600 mV DC range, 0.01 mV in high-resolution mode; read directly; no meter bought |
| Q3 | **Cell count for the carrier**: stay 1S3P (your telemetry decision) or move to the 4S4P of next-stages-plan? Tied to telemetry D1 (the pack is about half the PRD reserve) | none: step 3 layout waits | the supply, whether the MAX17048 survives, the fuse and connectors | 1S3P: the MAX17048 stays; fuse and connectors for the 1S path (H6) |
| Q4 | Buy the **BQ25798EVM** now so it is on hand when step 2's H01 run ends, or after step 2 exits? | after step 1b exits | whether 2c can start the day H01 ends | buy now: ordered 2026-11-02 (2 units); do not buy again |
| Q5 | Which **Mac USB ports and hubs** are on the bench, and which one was the RX on when it stalled? | RX on a direct port alone | H8's port plan | both NUCLEOs were on one hub; the RX goes alone on a direct Mac port; H8(a)–(b) confirmed, (f) stays |
| Q6 | Are the **BOB-14021 breakouts already built** with their jacks and header pins? If not, may the jack and headers be soldered onto them as module preparation (H5)? | not built, and not allowed: two pre-assembled BiPOM BRK6P6C-S-FT are used for change B | whether change B needs the BiPOM fallback | not soldered yet; jack and header pins soldered now as module preparation (change A step 4a); no screw-terminal breakout |
| Q7 | **Confirm OQ-14** (sensor-module-ports spec section 11): is the v1 base unit a carrier board under the NUCLEO, mating the morpho CN7/CN10 underside pins (N7, S4)? | none: step 3 layout waits; the ports spec records the carrier as "proposed" | the step 3 board, its connectors and the GPIO budget | yes: OQ-14 decided; layout waits for the measured underside pin length and clearance (N7) |
| Q8 | **H01 before or after four-rail metering?** The existing gate (`next-stages-plan.md:36`, `H01-checklist.md:6`) says Stage 1 power work waits for H01; step 1b (solar and USB-C rails, a panel, a 24 h balance) is that kind of work | **before** (the existing gate): step 1 → step 2 and H01 → 1b on the step 2 plate → 2c | after: 1b runs on breadboard v2 right after step 1, and step 2 (and H01) wait for 1b's exit | H01 first: 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5 |

### 7.1 Clint's answers (2026-10-30)

Answered in a formal survey. These replace the defaults above; nothing in this section is reopened.

| # | Answer | Effect |
|---|---|---|
| P3 | **Yes**: the pack goes back through the cut #1131 pigtail, WAGOs and the INA228 shunt | change A as written; the direct plug-in of 2026-10-28 is retired |
| Q1 | **Yes**: INA228 module preparation is allowed (A0/A1 jumpers on the three extra #5832 boards, the 0x48 wire from ADDR1 to SDA) | step 1b runs on the breadboard harness after H01 (Q8); the boards are soldered into the module board only after 1b exits |
| Q2 | **Fluke 87V** (INVENTORY.md, at the office): 600 mV DC range, 0.01 mV resolution in high-resolution mode | the 38 mA screen and the 1 A checks are read directly; no meter purchase |
| Q3 | **1S3P** | the carrier keeps the 1S path: BQ25798 1S, MAX17048, the current connectors and fuse class |
| Q4 | **Buy the BQ25798EVM now** | moves to the step 1 shopping list; 2c can start as soon as H01 and 1b exit |
| Q5 | **Both NUCLEOs were on one hub** when the RX stalled | H8 confirmed: the RX goes alone on a direct Mac port; the TX may stay on the hub; the gateway's reopen-on-silence fix stays in the cascade |
| Q6 | **Not soldered yet; may be soldered now** (jack and header pins, as module preparation under H5) | step 1 uses the BOB-14021s directly with solid-core jumpers; the screw-terminal RJ11 breakout leaves the shopping list |
| Q7 | **Yes**: OQ-14 confirmed, the v1 base board is a carrier under the NUCLEO on morpho | S4 unblocked on this point; the ports spec records OQ-14 as decided, not "proposed". Layout still waits for the measured underside pin length and clearance (N7). *2026-10-30:* that measurement is satisfied by the N7 row below |
| Q8 | **H01 first** | build order stays 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5 |
| N2 | **Approved**: cups PC0 → PB5, rain PB5 → PB4 | change B goes ahead on breadboard v2 |
| N7 | **Morpho fit test** (the measurement N7 and S4 asked for): a cut-down standard 2.54 mm female header (short PCB tails) took the NUCLEO-WL55JC1's morpho pins fully seated, and no underside part touched it | a standard-height 2.54 mm female socket works for the carrier; N7's underside measurement is satisfied, and the layout waits only for the morpho grid from ST's drawing and the chassis outline (S4). 2 × 19 female sockets come only at 1000-piece minimums, so the carrier build uses standard 2 × N female headers cut to 2 × 19 (sacrificing one position at the cut) |

## 8. Status against the power-telemetry design (2026-10-29, amended 2026-10-30)

The power-telemetry design ([`2026-10-29-power-telemetry-design.md`](2026-10-29-power-telemetry-design.md),
section 17) settles every row of this record that touches it. Its section 1 holds Clint's own power
decisions, which this record does not reopen. Clint answered this record's survey on 2026-10-30
(section 7.1); the rows below follow those answers. Where no survey question covered a row, the row
says whose reading it is. Summary:

| Rows | Status | Effect |
|---|---|---|
| 1.4 (TMR, ITERM, shunt, pull-ups, 0x48 pull-down, Arduino aliases, D2/D4, VIN-DPM), P5 (sense points), P8, P9, P10 (with EN2 high), M1, M3, N1, N4, N8, S1–S5 | **adopted** | dated amendments in the design (sections 1, 2, 5.2, 6.3, 8.6, 9.2, 9.3, 11.1–11.3, 12.1, 15); `docs/hardware/power-metering.md`, `docs/next-stages-plan.md` and `docs/hardware/bench-station-wiring.md` follow |
| 1.4 R_ISET = 1 kΩ | **adopted with change A**, read by this workflow from 7.1 P3 'change A as written'; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5) | `power_config.h` `POWER_R_ISET_OHM 1000`; `tools/benchlink_log.py` `R_ISET_OHM = 1000.0` (6.4); ISET currents logged earlier with 890 Ω read 12 % high |
| M2 (ISET network and gain; measured divider ratio) | **adopted with change A**, read by this workflow from 7.1 P3 'change A as written'; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5) | section 4.4 steps 11–12 fit the ISET network and store the measured divider. `power_config.h` holds `POWER_ISET_GAIN_PPM 990099` (1 MΩ ÷ 1.01 MΩ, nominal until the per-board fit) and `POWER_VIN_DIVIDER_PPM 3000000` (nominal until measured); benchlink holds `VIN_DIVIDER_PPM`; R_ISET and the ISET gain for benchlink are applied in `tools/benchlink_log.py`. The fit and the measured resistors go into `wiring.toml` first (`iset_gain_ppm`, `measured_ohms`; M2 dated note), and checks 8 and 9 follow them |
| M4 (INA228 VBUS at CELL+ as the cell voltage of record from step 1b) | **rejected for the wire format**; the wiring and the host-side cross-check are adopted | field 11 stays the gauge VCELL in every phase (Clint's decision 1; one sensor a field across phases). The battery INA228 VBUS sits at CELL+ position 4 from step 1b (step 1b; *dated note 2026-10-30:* this said "may sit"; the design's phase B and VBUS-net rows and `next-stages-plan.md` now say "moves" too); the node firmware does not read it in profile B |
| N2 (cups PB5, rain PB4) and the M7 link probe | **approved 2026-10-30 (7.1 N2)** | implemented at step 1 change B (4.5) in one commit with `board_inputs.c`, `mod_rain.h`, `wiring.toml`, the guide's cups and rain rows, the READMEs and `tests/test_board_inputs.py`. The M7 probe (status field `meter_link=`) follows before the step 2 H01 run |
| P1–P7, D1–D7, M5, M6, M7 host part, the rest of section 6 | *2026-10-29:* **not implemented yet** (this record's own work package). *Dated note (2026-10-30):* **implemented on `feat/power-telemetry`, uncommitted, pending the gates** | the design's text already describes the target; `wiring.toml`, the generator, the tools and the tests change with the step 1 model commit (D1). *2026-10-30:* the model is `bench-bb-r0.3` (changes A, B and C: joints, leads, the P1 tags, PA9 and the split QT bus), with r0.1 and r0.2 as frozen models and sheets under `source/revisions/` and `revisions/` (6.1 dated note), with `source/checks.py` (D3 checks 1–9, `check_iset` for exit 7), `source/checklist.py` (C1–C23), the regenerated sheet and drawings carrying the model hash, `tools/preflight.py` (D6), the M6/M7 host flags in `tools/benchlink_dash.py`, the M7 node probe, and their tests (section 6.2). Not done: the commit and the gates, Clint's tags (6.1), the bench work of sections 3 and 4, and the section 6.6 trees (they start with their step) |

The R_ISET and M2 rows record this workflow's reading of 7.1 P3, not Clint's own words; design
section 15 keeps D4 and D5 for Clint to confirm.
