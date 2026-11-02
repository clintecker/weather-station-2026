# Next stages: parts and plan

Written 2026-10-14, while the first-revision (R0) test PCBs and printed fixtures are in transit.
**Nothing has been ordered or quoted.** The authority is the v0.2 product and technical
requirements (PRD/TRD, `weather-station-v0.2-prd-trd.html`): §3 gives the stage order, §7 the
component families. This document picks exact parts within those families.

**Amended 2026-10-29** by Clint's power decisions and the power telemetry design
([`superpowers/specs/2026-10-29-power-telemetry-design.md`](superpowers/specs/2026-10-29-power-telemetry-design.md),
"the power design"): the pack is **1S3P**, Stage 1 runs in the **power phases A, B and C** (§1.1, the
one place in the plans that defines them), the final goal is **four metered rails** (§1.2), and
**USB-C is for bench work and backup charging only, never together with solar** (§1.1). Every row
below that planned the 4S4P Molicel pack is restated for 1S3P and marked *superseded 2026-10-29*. The
implementation plan is
[`superpowers/plans/2026-10-29-power-telemetry.md`](superpowers/plans/2026-10-29-power-telemetry.md);
the rail, monitor and address details are in [`hardware/power-metering.md`](hardware/power-metering.md).

**Amended 2026-10-30** by the build-progression decision record
([`superpowers/specs/2026-10-29-build-progression-decisions.md`](superpowers/specs/2026-10-29-build-progression-decisions.md), "the record") and Clint's survey answers in its section 7.1: the
station is built in seven steps, mapped onto the stages in §1 "Build steps"; H01 runs first (Q8); the
carrier (v1 base board) stays **1S3P** (Q3); the **BQ25798EVM was ordered on 2026-11-02**, 2 units, with the step 1 order
(Q4); the pack connector is
XT60 from step 3 (record H6); v1 sensor ports are **RJ11** and RJ45 is the unscheduled v2 only
(record H6, sensor-module-ports spec).

**Price key:**
- **live** = read on the maker's or store's own page on 2026-10-14.
- **snapshot** = a search-engine copy of a distributor page.
- **not verified** = no price found (DigiKey, Mouser and TI blocked automated checks).

Check again every price that is not live before you order.

## 1. Where we are

The PRD orders the work in four stages. Each stage ends with acceptance tests (gates). The next
stage starts only after those tests pass.

```mermaid
flowchart LR
  S0["Stage 0: data path on the bench"] -- "H01 passes" --> S1["Stage 1: main power and pack state"]
  S1 -- "H02 and H03 pass" --> S2["Stage 2: one wired module"]
  S2 -- "H04 passes" --> S3["Stage 3: complete unheated sensing"]
  S3 -- "H05, H06, H07 and H11 pass" --> F["Stage 3 complete"]
```

| Stage | What it builds | Gate (PRD acceptance tests) | State |
|---|---|---|---|
| 0 | The data path: sensor node → LoRa → receiver → gateway → database, on the bench with USB power | H01, the 24-hour delivery test: ≥ 1,426 of 1,440 readings within 120 s, plus a restart and outage matrix | Protocol version 5 runs on the bench. The TX reads its sensors as DATAVANE5K local modules (release `04fcc656938d`, 2026-10-19). Protocol version 6 (power telemetry) is in the source, not yet released. Next steps: `CONTEXT-PACK.md` §6 |
| 1 | Main power and pack state: battery pack, charger, solar, pack monitoring | H02, pack energy accounting: pack Ah/Wh within 5 %. H03, cold and solar endurance: 168 h at −35 °C, cold-charge inhibit, dawn recovery, a 7-day deficit recovered in ≤ 3 solar days | **Power phase A runs now, beside Stage 0** (§1.1): the 1S3P pack, the bq24074 and its monitors are on the bench, and the node reads them. The gates H02 and H03, and the pack, chamber and solar endurance work, follow H01 |
| 2 | One wired sensor module on a sealed RJ45 port (*amended 2026-10-30:* v1 ports are RJ11, sensor-module-ports spec and record H6; RJ45 is the unscheduled v2 only) | H04, the port test: power, faults, 10 m cable, 10⁶ transactions | Long-lead parts identified. Every module follows DATAVANE5K, the module protocol WSMP ([`module-protocol.md`](module-protocol.md)), which replaces the PRD §11 register map |
| 3 | The complete unheated sensor set | H05 (defined in PRD §12). H06, the rain acceptance test. H07, UV index sensor qualification. H11, 30-day on-device storage | Instruments identified |

The PRD allows planning and sourcing Stage 1 now ("plan and source the stage-1 pack and chamber
access"). **Stage order since 2026-10-29:** power phase A (its telemetry: node firmware, protocol
version 6, gateway) is bench work on the USB-powered boards and runs now, beside Stage 0. It does
not change H01's criteria (the H01 verdict counts temperature and humidity only;
[`H01-checklist.md`](H01-checklist.md)). Stage 1's gates (H02, H03) and its pack, chamber and solar
endurance work follow H01.

**Build steps (decided 2026-10-30).** The record (section 2.5, S1; section 3) builds the station in
seven steps, in the order Clint set (7.1 Q8, H01 first): 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5. The Stage 1
gate above is kept: step 1b (the solar and USB-C rails) and everything after it follow H01. Each
step's exit criteria are in record section 3; each step starts only after the previous one exits.

| Step | Built | Power profile | Stage | Gates and proofs here |
|---|---|---|---|---|
| 1 | breadboard v2, no solder: force path on JST PH and WAGO, signals on the breadboard, NUCLEO on its Arduino headers (record section 4) | A (and mode B) | Stage 0 bench, with power phase A beside it (§1.1) | no PRD gate; the record's section 4.3 checklist gates step 2 |
| 2 | #196 shield and Perma-Proto module board (phase-B INA228 positions empty); force harness unchanged | A | Stage 0 | **H01** (24 h); passing it opens Stage 1 |
| 1b | three more INA228s on the step 2 plate's breadboard, same harness; after H01 (decided 2026-10-30, 7.1 Q8; module preparation allowed, 7.1 Q1) | B | Stage 1, power phase B | no PRD gate; four-rail exit (rails against the meter, 24 h balance, back-feed) |
| 2c | BQ25798EVM on the step 2 harness, no solder (EVM ordered 2026-11-02, 7.1 Q4) | C | Stage 1, power phase C | the **H02 basis** (pack Ah and Wh within 5 % on the bench), profile C end to end |
| 3 | carrier PCB under the NUCLEO on morpho (v1 base board; OQ-14 decided 2026-10-30, 7.1 Q7), 1S3P (7.1 Q3); connectors per record H6: XT60 for the pack, a cold-rated solar connector, a USB-C receptacle, RJ11 for the meters and the v1 sensor ports, no RJ45 | C | Stage 1 gates | **H02** and the **H03 bench items** (cold-charge inhibit, dawn recovery); H04a (record section 3) |
| 4 | the carrier in the enclosure, outdoors | C | Stage 1 complete | **H03 proper** (168 h at −35 °C, 7-day deficit recovered in ≤ 3 solar days) |
| 5 | custom STM32WL55 board | C | PRD Stage 4 | re-pass of steps 3 and 4 |

### 1.1 Stage 1 power phases (decided 2026-10-29)

Clint's decisions of 2026-10-29 (power design §1). The phases are named here and in power design §2,
and used under these names everywhere else.

| Item | Decision |
|---|---|
| Pack | **1S3P Li-ion**: three 2,200 mAh cells in parallel, 6,600 mAh, 3.0–4.2 V, 3.7 V nominal, about 24.4 Wh (Adafruit #353, protected, JST PH plug; on the bench). It stays 1S3P in every phase and on the carrier: *decided 2026-10-30* (record 7.1 Q3; this cell said "It may stay 1S3P in every phase"). Whether it meets the PRD's energy reserve is still open (D1, §6) |
| Final goal | Voltage **and** current of four rails: **battery** (signed, + into the cell), **solar input**, **USB-C input**, **load** (the system rail). One INA228 per rail on the I2C bus at distinct addresses; the BQ25798's own ADC later as a cross-check |
| USB-C rule | USB-C is for bench work and occasional backup charging **only**. It is **never connected at the same time as solar**, in any phase |
| Wire format | One place for all power data now, source-agnostic (what is measured, not which chip), with "not measured" (the field is absent) and "invalid" told apart, so phases B and C need no redesign (power design §4–§6). Voltages and currents every minute (observation); slow items every 15 minutes (health report) |

**Why the USB-C rule.** The phase A charger (bq24074) has one input (VBUS). The Adafruit #4755 joins
its own USB-C and DC jack at VBUS through two Schottky diodes, and no monitor sits upstream of that
join: with both sources connected the higher one feeds the charger, and the firmware cannot tell
which (it never guesses the source). In phase B the same diodes (D2, D4) block back-feed between the sources, with each source's monitor
upstream of its diode (power-metering §5.1),
and in phase C the BQ25798 selects one input; the rule stays in every phase, so at most one source
rail carries current. Two source rails with current at the same time are a broken operating rule,
visible in the data of phases B and C ([`hardware/power-metering.md`](hardware/power-metering.md)
§1, §5).

| Phase | Charger | Monitors (I2C2 on PA11/PA12, through the STEMMA QT hub) | MCU inputs | Monitored nets | Status |
|---|---|---|---|---|---|
| **A** (current) | Adafruit bq24074 #4755: one VBUS input, 1.0 A ISET jumper, **R_ISET 1 kΩ** (0.89 A typ; KISET 890 A·Ω, I = 400 × V_ISET ÷ R_ISET), 4.2 V fixed | battery INA228 0x40 (shunt in the pack's + lead: pack → cut #1131 pigtail → WAGO CELL+ → INA228 shunt → WAGO BATT → charger BATT socket, record P3; its **VBUS sense lead** into its own position on the OUT connector, SJ1 open, record P5), MAX17048 0x36 with its red lead on the **CELL+ node** (minus unconnected, ground over STEMMA QT; record P4, P5, M4), SHT45 0x44; one WAGO STAR at pack − with one TIE to logic ground (record P4) | ISET → 10 kΩ → PB1 node (100 nF, 1 MΩ) → PB1 (ADC1_IN5, A0 CN8.1, record M2); charger VBUS through 20 kΩ (two 10 kΩ in series) over 10 kΩ → PA10 (ADC1_IN6, A2 CN8.3), VIN = 3 × the pin; **CHG → PB10 (D6 CN9.7; morpho alias CN10.25) and PGOOD → PB8 (D5 CN9.6; morpho alias CN10.27)**, internal pull-ups; VREFINT for VDDA. Step 1 lands every signal on the Arduino female headers and the mode-B supply at CN6.4 (record N3) | the CELL+ node (V), the battery path (I), OUT (V), the charger input after the sources join (V, source not identified), ISET, CHG, PGOOD | Proven on the bench with `firmware/benchlink` on 2026-10-28/29 **except the shunt in the battery path** (the cell sat in the charger's LIPO socket). The node firmware reads it from protocol version 6 on. *Amended 2026-10-30:* this row said R_ISET about 890 Ω, the VBUS jumper on OUT, the gauge Kelvin on the cell, and CHG CN10.25, PGOOD CN10.27. R_ISET 1 kΩ is adopted with change A, read by this workflow from 7.1 P3 ("change A as written"); it is confirmed by build-sheet check 2, and Clint is to confirm it (power design D4/D5). Change A (record 4.4, decided 2026-10-30, 7.1 P3) puts the shunt back in the battery path |
| **B** (four rails) | bq24074, as phase A | phase A plus a load INA228 0x41 (OUT to the load), a solar INA228 0x45 and a USB-C INA228 0x48, each source monitor upstream of the point where the sources join: the breakout's own Schottky pair D2/D4, with EN2 high and EN1 low on the board (power-metering §5.1; an ideal-diode or power-mux stage only as the fallback if EN2 is low). The battery INA228's VBUS sense lead moves from OUT to CELL+ position 4 (build-progression record step 1b; *dated note 2026-10-30:* it was "stays on OUT", which the record and `power-metering.md` overrule); the firmware no longer reads it (the load INA228 owns the load voltage), and the host tools use it as a cross-check against the gauge | as phase A | the four rails (V and I each) plus the charger input (V) | Step 1b, after H01 (§1 "Build steps"). Its parts are not ordered yet; they are bought with the step 2 list (record section 5). The firmware's rail table and the host tests cover it now |
| **C** (BQ25798) | TI BQ25798: VAC1 = solar, VAC2 = USB-C, its own ADC over I2C, MPPT. The wire format allows either order with phase B; the build runs B (step 1b) before C (step 2c), record S1 | with phase B's INA228s ("C+B") or without them ("C alone"; §1.2 says what fills each slot either way); the battery INA228 and the gauge stay | PB8 = BQ25798 /INT (open drain, active low, the same internal pull-up and pull-up rule); /CE strapped low, charging stopped and started over I2C; ISET, the divider and CHG go away, so **PB1, PA10 and PB10 are released** (power design §2 and §17, build-progression record N8; amended 2026-10-29: this cell said PB10 = STAT and PB1, PA10 reserved) | C+B: as phase B plus the charger's own VBUS, IBUS, VBAT, IBAT, TDIE, TS. C alone: the cell, the battery path, VSYS, VAC1, VAC2, VBUS, IBUS by active input | Step 2c, after H01 and 1b (§1 "Build steps"). The BQ25798EVM was ordered 2026-11-02, 2 units, with the step 1 order (record 7.1 Q4); the driver is not written yet. Only the fill table is defined now (§1.3). *Amended 2026-10-30:* this cell said "Later; not ordered" |

**The phase A wiring is the official design**, the same MCU pins on the bench and in the field. Its
source is [`firmware/benchlink/README.md`](../firmware/benchlink/README.md#wiring), "Wiring"; the
breadboard model is [`hardware/bench-breadboard-r0/`](../hardware/bench-breadboard-r0/README.md) with
its build sheet's "Power checks". The pull-up rule: PB8 and PB10 are FT_f pins, and with the internal
pull-ups on, the pin must stay below VDD + 0.3 V (DS13293 Rev 5, table 26); CHG and PGOOD measured at
most 2.9 V on the bench (their LEDs hang on OUT).

**Bench lessons carried forward** (2026-10-28/29):

| Lesson | Rule |
|---|---|
| A 0.2 Ω breadboard battery path ended 1 A charges early | keep the battery path short and low resistance, within the span limits of power design §11.2 (+ span at most 75 mΩ, − span at most 40 mΩ, each pack-side span at most 28 mΩ; build-sheet power check 7), never through breadboard strips |
| The gauge on OUT reads the charger's output, not the cell | the MAX17048's red lead sits at the **CELL+ node**, before the shunt; its minus is unconnected and it takes ground over STEMMA QT (record P4, P5, M4). Under current it reads CELL+, which differs from the pack terminal by I × R_pack. *Amended 2026-10-30:* this said "senses the cell, Kelvin" |
| The INA228 VBUS jumper sensed the wrong net | the battery INA228's VBUS sense lead goes into its own position on the OUT connector, its VBUS-to-VIN+ solder jumper (SJ1) open (record P5); build-sheet power check 9 proves it (OUT 4.3–4.5 V and at least 100 mV above VCELL during a charge) |
| The INA228 counts VIN+ → VIN− as positive, which is out of the cell | the firmware turns the battery current once (sign −1), + into the cell (power design §3.1) |

**Exit criteria of phase A** (power design §2; all must hold before phase A counts as done):

1. The node firmware, not only benchlink, reads ISET, the charger input voltage, CHG, PGOOD, the
   INA228 (battery current, OUT voltage, die temperature) and the MAX17048 (cell voltage, SOC, rate)
   on the official hub wiring with no mux.
2. The gateway decodes, stores and exposes every value of phase A's column of §1.2 (API, dashboard
   data, MQTT).
3. The bench acceptance drill (node against benchlink, power design §12.2) passes on one pack with
   the shunt in the battery path.
4. A 1 A charge with the shunt in the path ends in a normal termination (CHG off and steady, not
   flashing) while the battery INA228 current is 0.20–0.40 A (ITERM about 0.3 A) and the cell is at
   4.12 V or more, and the battery-path span limits of power design §11.2 hold (build-sheet power
   checks 7 and 10). *Amended 2026-10-29 (power design §2, record P8 and P9):* the #4755 ties TMR to
   GND (timers disabled; confirm on the board in hand, build-sheet check 10), so a charge may start
   from any cell voltage. Only a board with TMR floating needs RTMR = 72 kΩ, or a start at 3.85 V or
   more (§7). This criterion said "the battery loop budget (at most 50 mV at 1 A)" and made the
   3.85 V start the default.

Phases B and C: their hardware builds are outside the power design (its §16). Their exit criteria
are in the record's section 3: phase B is step 1b, phase C is step 2c (§1 "Build steps"). The wire
format, the gateway and the firmware's rail table already hold every value they fill.

### 1.2 The four rails in each phase

"Absent": the build has no source, so the field is not in the record. "INVALID": the source is fitted
but failed or out of range. Phase C has two builds: with phase B's INA228s ("C+B") and without them
("C alone"). Source of truth: power design §3.2 and §3.3, and
[`hardware/power-metering.md`](hardware/power-metering.md) §4.

| Rail | Value (field) | A | B | C+B | C alone |
|---|---|---|---|---|---|
| Battery | voltage (`batt_mv`, 11) | MAX17048 VCELL at the CELL+ node (includes the pack-lead drop under current; record M4) | as A | as A | as A |
| Battery | current (`batt_current_ma`, 12), + into the cell | battery INA228 | as A | as A | as A |
| Battery | energy and charge in and out (13–16) | battery INA228 ΔQ × VCELL, split by sign | as A | as A | as A |
| Load | voltage (`load_mv`, 26) | battery INA228 VBUS (on OUT) | load INA228 | load INA228 | BQ25798 VSYS |
| Load | current (`load_current_ma`, 27) | absent | load INA228 | load INA228 | absent |
| Charger input | voltage (`charger_input_mv`, 28), after the sources join | PA10 × the stored divider ratio (3 nominal), **source not identified** | as A (a cross-check of the source rails) | BQ25798 VBUS | BQ25798 VBUS |
| Solar | voltage (`solar_mv`, 29) | absent | solar INA228, upstream of the join | solar INA228 | BQ25798 VAC1 |
| Solar | current (`solar_current_ma`, 30) | absent | solar INA228 | solar INA228 | BQ25798 IBUS while solar is the active input, 0 mA while USB-C is or with no input |
| USB-C | voltage (`usb_mv`, 32) | absent | USB-C INA228, upstream of the join | USB-C INA228 | BQ25798 VAC2 |
| USB-C | current (`usb_current_ma`, 33) | absent | USB-C INA228 | USB-C INA228 | BQ25798 IBUS while USB-C is the active input, 0 mA while solar is or with no input |

Every 15 minutes the health report adds the gauge SOC and its rate (MAX17048, every phase), the
charger status (PGOOD and CHG in phases A and B, the BQ25798 status registers in phase C, with the
active input in phase C only), the power-monitor die temperature (the hottest fitted INA228), the MCU
supply (VDDA from VREFINT), the charger-reported measurements (phases A and B: the ISET charge
current only, 0 mA while PGOOD is deasserted; phase C: the BQ25798's VBUS, IBUS, VBAT, IBAT and TDIE)
and the pack temperature (phase C only: BQ25798 TS), plus the station items (reset cause, boots and
crashes since power-up, the last crash PC, radio TX timeouts, I2C bus recoveries) in every phase.
Power design §3.3 and §6 have the layout.

### 1.3 Phase C: the BQ25798 for a 1S pack

The rows below re-derive the earlier 4S BQ25798 plan for a 1S pack, two inputs, four rails and
either order with phase B. The BQ25798EVM was ordered 2026-11-02, 2 units, with the step 1 order (record 7.1 Q4), for
step 2c, which follows step 1b (record S1); the BQ25798 driver is outside the power design (its §16).
*Amended 2026-10-30:* this said "Nothing here is ordered" and allowed either order with phase B; the
record fixes B (1b) before C (2c).

| Item | Phase C plan |
|---|---|
| Inputs | **VAC1 = solar, VAC2 = USB-C.** The BQ25798 switches its input FETs, so one input is active at a time. The USB-C rule (§1.1) still holds |
| Current attribution in "C alone" | IBUS goes to the rail that the active-input bits name (the charger status byte, bits 6–7: 1 = solar, 2 = USB-C, 3 = no input; power design §6.3). The other source rail reads 0 mA (its input FETs are off); with no input (every night on solar with USB-C unplugged) both read 0 mA |
| ADC cross-check | With phase B's INA228s ("C+B") the INA228s fill the rails, and the BQ25798's VBUS, IBUS, VBAT, IBAT, TDIE and TS go to the health report's "charger-reported" keys, a cross-check of the rails. Without them ("C alone") the BQ25798 fills the load voltage (VSYS), the source voltages (VAC1, VAC2) and the source current (IBUS); the load current is absent. The battery current and voltage stay on the battery INA228 and the gauge in both builds |
| MCU pins | PB8 = BQ25798 /INT, open drain, active low, on its internal pull-up (the pull-up rule of §1.1). **/CE stays strapped low** (charging enabled in hardware); the driver stops and starts charging with the charge-enable register bit over I2C (EN_CHG, verify in SLUSDV2), so no GPIO holds /CE. The ISET wire, the PA10 divider and CHG go away: **PB1, PA10 and PB10 are released** (PB10 does not exist on the UFQFPN48 package, so a custom board needs no new home for it). I2C stays on I2C2 (PA11/PA12). *Amended 2026-10-29 (build-progression record N8, power design §17): this row said PB10 = STAT and PB1, PA10 reserved* |
| NTC | The BQ25798 TS pin carries the pack probe for the hardware charge inhibit; it is reported as `pack_temp_c`. The second probe for the firmware inhibit (finding 2) needs an MCU ADC pin, not yet assigned. The 4S plan's Semitec 103AT-11 probes (§3) stay the candidates; the TS network is re-derived from the BQ25798 datasheet (§7) |
| Cell count | **1S, 4.2 V** (or 4.1 V, §6). The EVM ships set for 2S: set it for 1S before the pack is connected (finding 3) |
| Panel | Phases A and B: **one Voltaic P110** (6 V; open-circuit voltage 6.94 V, about 8.7 V cold). The bq24074 charges only below its OVP (10.2–10.8 V), and the PA10 divider limits the input to 16.5 V with the MCU powered and about 10.8 V unpowered (power-metering §6): two P110s in series (13.9 V, about 17.2 V cold) are over both. Phase C: the divider is gone and the BQ25798's input range applies (finding 1): one P110, or two in series |
| MPPT | Re-derived from the BQ25798 datasheet before phase C (finding 4). Phases A and B have no MPPT. The bq24074's VIN-DPM (4.35–4.63 V) acts only with EN2 low (USB100/USB500); with EN2 high, which phase B's D2/D4 join needs and phase A's board is expected to have, nothing holds the panel up: a panel that cannot supply the charge current is pulled down towards the cell voltage, and at low sun the charger may cycle PGOOD and CHG (power-metering §5.4, power design R16) |

## 2. Order early (long lead or scarce)

| Item | Why early | Stage |
|---|---|---|
| ~~**Main pack quote** (custom 4S4P Molicel M35A, battery management system (BMS), thermistor (NTC) leads)~~ | *Superseded 2026-10-29:* the pack is the 1S3P Adafruit #353 (§1.1, on the bench; about 24.4 Wh, under the 100 Wh limit, so it ships normally). A larger 1S pack is one option of D1 (§6). The 4S4P quote (Class 9 dangerous goods, about 200 Wh, ground only) is not needed | 1 |
| **−35 °C chamber booking** (7+ days, energized lithium pack) | Few places accept it; booking lead time. For H03, after H01 | 1 |
| **STM32C0116-DK** (development kit for the module adapter's microcontroller) | One distributor snapshot showed a 99-week lead. Buy whatever stock appears | 2 |
| ~~**Sealed RJ45 pair** (Amphenol RJF544: receptacle RJF54421 + plug RJF5446)~~ | 16-week lead (snapshot). *Amended 2026-10-30:* v1 sensor ports are RJ11 (sensor-module-ports spec; record H6: no RJ45 anywhere in v1). RJ45 is the unscheduled v2 only; do not order this pair for v1 | 2 |
| **sglux ERYCA UV photodiode quote** (Boston Electronics) | Quote only. It is the one true-UV-index chip for a home-built sensor head (H07) | 3 |
| BQ25798EVM, TPS62933EVM, TPS26624-25EVM | These TI evaluation modules (EVMs) showed 0 stock or 12-week leads in snapshots. **The BQ25798EVM was ordered on 2026-11-02**, 2 units, with the step 1 order (record 7.1 Q4), for step 2c (phase C). The TPS62933EVM is not needed for 1S3P (§3) | 1, 2 |

## 3. Stage 1 bill of materials

Phase A's parts are on the bench ([`poc-shopping-list.md`](poc-shopping-list.md), rows marked
**Have**); phase B's and C's are listed there and in
[`hardware/power-metering.md`](hardware/power-metering.md). Phase B's are not ordered yet; phase C's
BQ25798EVM was ordered 2026-11-02, 2 units, with the step 1 order (record 7.1 Q4). The rows below are the
earlier 4S plan, each restated for 1S3P where it changed.

| Item | Part | Price | Notes |
|---|---|---|---|
| Charger evaluation (phase C, step 2c) | **TI BQ25798EVM** | ordered 2026-11-02, 2 units, with the step 1 order (record 7.1 Q4); ~$149–179 (not verified) | 1–4S, charger input (VBUS) 3.6–24 V operating / 30 V absolute maximum, 5 A charge, maximum power point tracking (MPPT), 16-bit ADC, two inputs (VAC1, VAC2). **It ships set for 2S. Set it for 1S before you connect the 1S3P pack** (the 4S plan named JP28 or JP29 as the cell-count jumper; check the 1S setting in the EVM user's guide). Configure it over I2C from the Nucleo board (TI's BQ Studio is Windows-only). *Superseded 2026-10-29:* "move the jumper to 4S" |
| Charger (phases A and B) | **Adafruit bq24074 #4755** | have | 1S only, 4.2 V fixed, 1.0 A ISET jumper (1.5 A maximum), one VBUS input, no MPPT, no ADC. Its CHG, PGOOD and ISET go to the MCU (§1.1) |
| Pack monitor | **Adafruit 5832** INA228 (or SparkFun SEN-31438 Qwiic) | $14.95 live (SparkFun) | Phase A: one at 0x40 (have). Phase B: three more at 0x41, 0x45 and 0x48 (power-metering §7). The INA228's ENERGY register is unsigned and uses its own VBUS (OUT), so the firmware integrates the battery energy from the signed CHARGE steps × VCELL (finding 5) |
| Shunt | The Adafruit 5832's own shunt: 15 mΩ, 1 %, 2 W, 2512 (power-metering §2) | on the board | Full scale ±10.9 A at ADCRANGE 0; the firmware's 10 µA current step reads ±5.24 A. Offset at most ±1 µV ÷ 15 mΩ ≈ 0.07 mA, about 0.1 % of the ≈ 68 mA core load (0.25 W ÷ 3.7 V). Nominal; verified against a series reference, not measured (§7, power check 3). *Superseded 2026-10-29:* the Vishay WSK2512R0100BEA 10 mΩ Kelvin shunt and its ≈ 17 mA core load at 14.4 V |
| Main pack | **1S3P Li-ion, Adafruit #353**: three 2,200 mAh cells in parallel, 6,600 mAh, 3.0–4.2 V, 3.7 V nominal, ≈ 24.4 Wh, protection circuit, JST PH plug | have | Its cells' charge and discharge temperature limits are open against H03 (D3, §7). *Superseded 2026-10-29:* the custom 4S4P Molicel INR18650-M35A (≈ 14.4 V, 14 Ah, ≈ 200 Wh, balancing BMS) and its vendor list |
| Pack temperature probes | Phases A and B: one 10 kΩ NTC (Adafruit #372) taped to the pack, on the bq24074's THERM pin. Phase C: 2× Semitec **103AT-11** (10 k, B3435) | $4.00 / ≈ $3 each (snapshot) | Phases A and B: the charger's hardware inhibit only; the node does not measure the pack temperature. Remove the breakout's fixed 10 kΩ TS resistor first. A B = 3950 part sets a charge window of about +3.5 to +47 °C, not the 0 to 50 °C of the 103AT curve that SLUS810 specifies (D3). Phase C: one 103AT on the BQ25798 TS pin, one on an STM32 ADC pin for the firmware inhibit, a second opinion (§1.3) |
| Enclosure T/RH | **Adafruit 4885** SHT40 | $5.95 live | PRD's enclosure sensor |
| Pack → Nucleo supply | **Pololu S7V8F3** (3.3 V buck-boost, 2.7–11.8 V in) from the charger OUT into the NUCLEO's 3V3: at **CN6.4** in steps 1 and 2 (through the BATTERY POWER shunt header; record N3), at **CN7.16** on the carrier (record N7). CN6.4 and CN7.16 are the same 3V3 net. *Amended 2026-10-30:* this said CN7.16 only | $9.95 | Never with the ST-LINK USB connected (poc-shopping-list.md, caveats). The Nucleo's own LEDs and ST-LINK spoil the idle-current figure. Stage-1 current numbers are for the development board, not the final node. *Superseded 2026-10-29:* the TPS62933EVM (5 V out) needs a pack above 5 V |
| Fuse | not chosen for 1S3P | — | The #353 has its own protection circuit. A fuse at the pack's + terminal counts against the + span limit of the battery path (at most 75 mΩ, power design §11.2); choose one with its resistance (§7). *Superseded 2026-10-29:* the 7.5 A ATO and its holder were sized for the 4S pack. A ≈ 3 A fuse on the solar input remains sensible |
| Pack connector | Steps 1 to 2c: the #353's JST PH plug into the pack-mating half of a cut Adafruit #1131 pigtail (≤ 60 mm), into WAGO CELL+ (and the − lead into WAGO STAR); the pack's own lead is never cut (record P3, P4). From step 3: an **XT60** pair (record H6) | — | Part of the battery loop: never through breadboard strips. *Amended 2026-10-30:* this row said "a JST PH socket on short heavy leads" and marked the XT60 pair superseded; record H6 restores XT60 for the carrier |
| Solar | Phases A and B: **1× Voltaic P110** (10 W, 6 V). Phase C: one, or **2× P110 in series** | $65 each, live | Two in series (about 17.2 V cold) are over the bq24074's OVP and the PA10 divider's limit (§1.3); see §5, finding 1 |
| Wiring | silicone leads, STEMMA QT cables, lugs | — | Kelvin sense leads separate from the current path. The battery path within its span limits (power design §11.2, build-sheet power check 7) |

**Must-have hardware:** phase A is on the bench. *Superseded 2026-10-29:* the 4S plan's
≈ $420–450 plus the pack quote. Phase B's parts (three INA228s, the barrel-plug and USB-C screw-terminal adapters
for the D2/D4 join, the 5.1 kΩ Rd pair) are priced in `poc-shopping-list.md` (unverified) and not
ordered yet; they are bought with the step 2 list (record section 5). Phase C's BQ25798EVM was ordered
on 2026-11-02, 2 units (record 7.1 Q4), and is used at step 2c.

### Bench equipment for H02 and H03

The pack is 1S: at most 4.2 V, at most 1.5 A of charge current in phases A and B.

| Item | Part | Price | Buy / rent |
|---|---|---|---|
| Reference for Ah/Wh accounting | Siglent SDM3065X 6½-digit multimeter with calibration certificate + calibrated Riedon RSN-5-100 shunt | $857 live + shunt (not verified) | Needed: H02 requires an independent calibrated reference. A PPK2 or Joulescope is not a calibrated reference. *Superseded 2026-10-29:* their 15 V limit excluded them on the 16.8 V 4S pack; a 4.2 V pack is inside it, so they may serve as a second opinion after a check of their current range against 1.5 A |
| Programmable load | Siglent SDL1020X-E ($574 live) or B&K 8500B ($1,405) | — | Borrow or rent if possible. Check its minimum operating voltage against the pack's 3.0 V cut-off. Resistors that the Nucleo switches can serve as the ≈ 68 mA core load (0.25 W ÷ 3.7 V, about 55 Ω); the bench uses 100 Ω on OUT. *Superseded 2026-10-29:* the ≈ 17 mA core load at 14.4 V |
| −35 °C chamber | Rent an Espec SU-242 (Transcat) or TestEquity 107; or use a lab such as Gaynes Labs (Bridgeview IL) | quote | −35 °C is near the SU-242's −40 °C floor for a 168 h hold. Confirm that the lab accepts energized lithium packs |
| Temperature logger | Pico USB TC-08 + type-T probes | $479 (listing) | Should-have. It can wait |

## 4. Stages 2 and 3: chosen parts

| Function | Pick | Price | Meets PRD target? |
|---|---|---|---|
| Module adapter microcontroller development kit | STM32C0116-DK (fallback NUCLEO-C031C6) | ≈ $12–14 (snapshot) | — |
| RS-485 | TI RS485-HF-DPLX-EVM (supplied without a chip) + THVD2410DR | not verified / ≈ $3 | ±70 V bus fault, < 1 µA shutdown |
| Port eFuse | TPS26624-25EVM | ≈ €100 (snapshot) | Needs resistor changes for the 10–18 V window and the 100 mA limit. Each powered port draws 340 µA, which counts against the 0.25 W budget |
| Bench RS-485 adapter | Waveshare USB TO RS232/485 (B), SKU 26547 | $16.99 live | Isolated |
| Cable | Vertical Cable 069-559/CMX outdoor Cat6, solid copper, −40 °C | not verified | Use RJ45 plugs rated for solid wire. *Amended 2026-10-30:* v1 sensor ports are RJ11 (sensor-module-ports spec; record H6); this RJ45 cable and plug choice is for the unscheduled v2 only |
| Rain | **Davis AeroCone 6466M** (0.2 mm per tip) | $160 live | Yes on paper (±3 % or ±1 tip). At 2 mm/h, test runs need ≥ 20 tips |
| Wind | **Davis 6410** | $240 live | **Speed: no, below about 10 m/s** (±1 m/s against the ±0.5 m/s target). Direction: yes (±3°). See the wind accuracy decision in §6 |
| UV index | **Davis 6490** as the commercial fallback; sglux ERYCA for a DIY head (H07) | $425 live / quote | The 6490 is borderline below about UV index 3. Check it against a reference. The LTR390 and GUVA-S12SD measure UVA only, **not** UV index |
| Pressure | Adafruit 4816 BMP390 | $10.95 (out of stock at Adafruit) | — |
| Ambient T/RH | SHT45-AD1F (PTFE membrane) | — | **Already have it**: Adafruit 6174 carries exactly this part |
| 30-day storage (H11) | Winbond W25Q128JVSIM (16 MB, −40 °C); Adafruit 5643 breakout for the bench | $4.95 live (breakout) | Prefer the "IM" suffix. The "IQ" part has quad mode permanently on, so it loses the hardware write-protect pin |
| Irradiance (optional) | Apogee SP-110-SS | $255 live | — |
| Precision reference (not a deliverable) | SparkFun SEN-15901 weather meter kit | $79.95 live | Cheap comparison only |

**Rough cost:** Stage 2 ≈ $250–650 (mostly connectors). Stage 3 core ≈ $850–1,000.

## 5. Findings that change designs

Findings 1–4 now hold per charger: the bq24074 in phases A and B, the BQ25798 in phase C.

1. **Panel voltage.**
   - **BQ25798 (phase C): ordinary "12 V" solar panels are incompatible in a Chicago winter.** A
     36-cell panel's open-circuit voltage (Voc) of about 22 V rises to about 27 V at −35 °C. That is
     above the charger's 24 V operating limit, and its over-voltage protection then blocks charging
     at the cold dawn that H03 tests. The Victron 36-cell panel reaches about 30 V, the absolute
     maximum. Rule: **Voc at standard test conditions (25 °C) ≤ about 18 V.** Two 6 V Voltaic panels
     in series give 13.9 V, rising to about 17.2 V when cold. This does not depend on the cell count.
   - **bq24074 (phases A and B):** the charger charges only below its OVP (10.2–10.8 V), and the
     PA10 divider reads the input up to 16.5 V with the MCU powered and about 10.8 V unpowered. Rule:
     **cold Voc ≤ about 10.2 V**: one Voltaic P110 (about 8.7 V cold), never two in series. A
     higher-voltage source needs another divider ratio or a clamp (power-metering §6).
2. **The charger alone gives no cold-charge margin.**
   - **bq24074:** its TS window stops charging outside 0 to 50 °C with the 103AT curve that SLUS810
     specifies, about +3.5 to +47 °C with the B = 3950 NTC on the bench (D3). The node does not
     measure the pack temperature in phases A and B, so there is no firmware inhibit: the charger's
     window is the only cold-charge stop. Whether that window fits the #353 cells' charge limit is
     open (D3, §7).
   - **BQ25798:** it stops charging at 0 °C and resumes at 3 °C (as read for the 4S plan): no margin
     if the #353 cells' charge limit is 0 °C (D3). Add a firmware inhibit at about +3–5 °C from the second probe (§1.3).
   - Both: require a hardware cold-charge cutoff in the pack or the charger; an open or shorted probe
     must inhibit charging. The firmware never sets `TS_IGNORE`.
3. **After a crash or watchdog reset, the BQ25798 returns to its jumper defaults.** The cell-count
   jumper must therefore be right in hardware: **1S, 4.2 V**, with a default charge current that the
   1S3P pack accepts. *Superseded 2026-10-29:* "the 4S jumper: 16.8 V, 1 A". The bq24074 has no
   register settings: its 4.2 V and its ISET current are fixed in hardware, so a reset changes
   nothing.
4. **MPPT after power-on: re-derive for 1S from the BQ25798 datasheet before phase C.** The 4S
   finding ("MPPT is off after power-on, and the firmware cannot enable it below about 12 V on the
   pack") was derived for a 4S pack and does not carry over. What stays: dawn recovery from a deeply
   discharged pack or a dead MCU must work without the firmware's help, and H03 must test exactly
   that case. The bq24074 (phases A and B) has no MPPT. Its VIN-DPM (4.35–4.63 V) acts only with EN2 low;
   with EN2 high (phase B's D2/D4 join) a weak panel is pulled down rather than held
   (power-metering §5.4, power design R16).
5. **The INA228 energy register cannot tell charge from discharge**, and it multiplies by its own
   VBUS, which is OUT on the official wiring. The node integrates the battery energy from the signed
   CHARGE steps × the gauge's cell voltage, split into energy in and out (fields 13–16; power design
   §5.2). The INA228's signed CHARGE register is the source; H02 checks it against the calibrated
   reference.
6. **Powered sensors cost standby current:** Hall or optical anemometers about 3 mA, the Davis
   6490 2.4 mA, each eFuse 0.34 mA. Power them only while sampling (PRD §6). Measure the warm-up
   time. Phase B's four INA228s add about 2.6 mA, about 1 % of the 1S3P pack a day
   (power-metering §8).

## 6. Decisions for Clint

| Decision | Options |
|---|---|
| Wind accuracy | Davis 6410 + own calibration against a reference. Or RM Young 05103 (meets the target, four-figure price not verified). Or revise the PRD target |
| ~~Pack~~ | *Decided 2026-10-29:* the 1S3P pack (§1.1). Its size against the reserve is D1 |
| **D1: pack reserve** (power design §15) | The 1S3P pack is about 24.4 Wh; the PRD reserve (≥ 50.4 Wh: 1.2 × R03's 168 h × 0.25 W) is about twice the pack. Options: a lower measured core load (H02), a larger 1S pack for phase C, or a PRD deviation ([`radio-energy-policy.md`](radio-energy-policy.md) section 3). *Amended 2026-10-30:* the carrier stays 1S3P (record 7.1 Q3), so a larger pack is not the carrier plan as answered; any change of pack is Clint's. D1 itself stays open. The energy state stays NORMAL until decided |
| **D2: H01 on a version 6 release** (power design §15) | Whether H01 runs on a protocol version 6 release. Recommendation: yes, so the H01 evidence names the shipping protocol ([`H01-checklist.md`](H01-checklist.md)). *Amended 2026-10-30:* the H01 preconditions (build-progression record step 2 exit; `meter_link=ok` from the M7 probe, the power-telemetry phase A exit criteria) can be met only on a version 6 build. A "no" needs a version 5 backport of the M7 probe and the phase A power reading, which no plan carries, or a change to the record's step 2 exit |
| H02 reference | SDM3065X + calibrated shunt (≈ $1k), or Qoitech Otii Ace Pro, or borrow one |
| Load | Buy the Siglent ($574), or rent the B&K |
| Chamber | Rental (Transcat/TestEquity), or a local lab (Gaynes) |
| Connectors | RJF544 composite (≈ $55–75 per pair), or RJF TV metal (≈ $170–200 per pair). *Amended 2026-10-30:* both are RJ45; v1 sensor ports are RJ11 (sensor-module-ports spec; record H6), so this choice belongs to the unscheduled v2 only. The carrier's connector families are fixed by record H6 |
| Charge voltage | Phases A and B: 4.2 V, fixed by the bq24074 (no choice). Phase C: 4.2 V (full capacity), or about 4.1 V (longer cell life). *Superseded 2026-10-29:* 16.8 V or about 16.4 V for 4S |
| ~~Phase B join~~ | *Decided 2026-10-29* (power design §11.3, record P10): the breakout's own Schottky pair D2/D4 with EN2 high and EN1 low; the ideal-diode or power-mux stage only as the fallback if EN2 is low (power-metering §5.1, §9). What stays open is the weak-panel behaviour with EN2 high (power-metering §5.4, R16) |

## 7. Open checks before ordering

**Phase A calibration and wiring** (build-sheet "Power checks"; each value goes to
`firmware/stage0-node/App/power_config.h`, marked nominal until measured; power design §8.6, §11.1,
risk R4):

| Check | How | Nominal now |
|---|---|---|
| Shunt of each INA228 | verified, not measured (power design §8.6): the INA228 current agrees within 2 % + 2 mA with the Fluke 87V in series in the rail's + lead at a steady current (build-progression record M1, dated note 2026-10-30: only for a short steady window; no shunt or clamp meter is bought), power check 3 for the battery rail and B3 for the load, solar and USB-C rails. Only on a fail does the reference-derived value (DMM mV across the Kelvin points ÷ reference A, never an ohm range) replace the nominal | 15 mΩ (15,000 µΩ) |
| R_ISET | ISET to GND, charger unpowered, cell disconnected (power check 2). The #4755 schematic shows 1 kΩ (R9, about 0.89 A at the 1.0 A jumper; record 1.4) | 1 kΩ (`POWER_R_ISET_OHM 1000`). *Amended 2026-10-30:* this said 890 Ω. 1 kΩ is adopted with change A, read by this workflow from 7.1 P3; confirmed by power check 2; Clint to confirm (power design D4/D5) |
| Divider ratio | the two measured resistances (20 kΩ and 10 kΩ, 1 %, ±2 % on the ratio); node `charger_input_mv` against a DMM on VBUS within 1 % (acceptance drill) | 3 |
| VDDA | node `mcu_supply_mv` (from VREFINT) against a DMM on the 3.3 V rail; it replaces the hard-coded 3,300 mV | — |
| TMR strap on the #4755 | confirm on the board in hand: tied to GND (timers disabled, as the schematic reads), floating (default 4–6 h: fit RTMR = 72 kΩ if reachable, else start the criterion-4 charge at ≥ 3.85 V), or a resistor | tied to GND (schematic) |
| CHG and PGOOD LED anodes | on OUT (schematic), so a released pin stays near OUT − Vf; power check 6 measures both below min(VDD, VDDA) + 0.3 V on the panel at its highest Voc | on OUT |
| Battery path | each span's mV drop over the INA228 current (0.8–1.0 A, first 10 minutes of a CC charge): + span at most 75 mΩ, − span at most 40 mΩ, each pack-side span at most 28 mΩ, each JST PH mating at most 20 mΩ, each clamp or screw at most 5 mΩ (power check 7, power design §11.2) | — |
| EN1 and EN2 jumpers on the #4755 | record SJ2 (EN1) and SJ1 (EN2): phase B's D2/D4 join needs EN2 high **and EN1 low** (EN1 = EN2 = high is standby, no charge; EN2 low brings VIN-DPM and a 100 or 500 mA input limit, so the fallback join); build-sheet check B1, power-metering §5.1 and §9 | expected EN2 = 1, EN1 = 0 (build-progression record) |

**D3: temperature limits.** The #353 cells' charge and discharge temperature limits (from the cell
maker's datasheet) against H03 (168 h at −35 °C), and the charge window that the NTC actually sets:
about +3.5 to +47 °C with the B = 3950 part on the bench, 0 to 50 °C with a 103AT-type part (power
design §11.1). Decide whether the bench NTC stays or a 103AT replaces it.

**Phase B and C:**
- BQ25798 datasheet inconsistencies. RT2 is printed as both 30.31 and 31.31 kΩ. The input
  over-voltage protection (ACOVP) option table differs between two sections. Check both against
  the EVM schematic.
- The BQ25798 for 1S: MPPT after power-on (finding 4), the cell-count setting and its default charge
  current (finding 3), the TS network for the chosen NTC.
- Only if EN2 is low on the board in hand (the fallback join): the join-stage part (TPS2121 or an
  ideal-diode controller) against the cold panel Voc and a drop of at most about 100 mV at 1.5 A
  (power-metering §5.1). With EN2 high and EN1 low the board's own D2/D4 are the join, and only the
  weak-source check of power-metering §5.4 is open.
- The USB-C INA228 at 0x48 needs the extra SDA hold time, or an SCL-strapped address
  (power-metering §7).
- A pack fuse for 1S3P, with its resistance inside the + span limit of the battery path (at most 75 mΩ, power design §11.2).
- *Superseded 2026-10-29:* the official Molicel M35A datasheet revision (maximum charge current 1.7
  or 3.4 A per cell). The SparkFun INA228's onboard shunt (10 or 15 mΩ): phase A uses the Adafruit
  5832, whose shunt is verified against a series reference as above.

**Other stages:**
- The RJ45 plug's cable-diameter range against the 6.1 mm cable. *Amended 2026-10-30:* v2 only; v1 sensor ports are RJ11 (sensor-module-ports spec; record H6).
- Live price and stock for everything marked snapshot or not verified.
