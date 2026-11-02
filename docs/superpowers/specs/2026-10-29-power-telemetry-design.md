# Power telemetry: design

Status: design, 2026-10-29 (revised the same day after review). The decisions in section 1 are
Clint's (2026-10-29). Everything else is this design's choice. Not implemented. It changes the radio
protocol (version 5 to version 6), the observation catalog (version 1 to version 2), the health
report, the WSMP registry, the node firmware, the gateway and the bench breadboard model. Section 13
lists the documents that change with it, and section 15 the open points for Clint. Section 17
reconciles this design with the build-progression decision record of the same day
([`2026-10-29-build-progression-decisions.md`](2026-10-29-build-progression-decisions.md)): each of its
rows that touches this design is adopted here (with a dated amendment where the text changed),
deferred or rejected, with the reason.
*Amended 2026-10-30:* the dated 2026-10-30 amendments carry Clint's survey answers (record section
7.1) into this design; section 17 lists them. The protocol is unchanged by them. *Amended 2026-10-30
(status):* "Not implemented" is no longer true: the node firmware (`firmware/stage0-node/App/power_acq.c`,
`power_config.h`, `mod_power.c`), the protocol and registry changes, the gateway, the host tools and the
bench model are implemented on `feat/power-telemetry`, uncommitted and pending the gates; the bench
measurements (section 11.1's checks, the phase exit criteria) are not done.

It builds on:
- [`docs/protocol-design.md`](../../protocol-design.md) and [`docs/protocol.md`](../../protocol.md):
  protocol version 5, catalog version 1;
- [`docs/module-protocol.md`](../../module-protocol.md): WSMP 1.0 and its registry;
- [`2026-10-18-wsmp-bench-station-design.md`](2026-10-18-wsmp-bench-station-design.md): the local
  modules and the interim catalog map;
- [`firmware/benchlink/README.md`](../../../firmware/benchlink/README.md) "Wiring" and "Known
  limits": the power wiring proven on the bench on 2026-10-28/29.

Datasheets cited: TI SLUS810N (bq2407x), ST DS13293 Rev 5 (STM32WL55), ST UM2592 Rev 4
(NUCLEO-WL55JC), TI SBOS904 (INA228), Analog Devices MAX17048.

## 1. Goal and decisions

Measure the station's power system, send it, store it and show it, with one wire format that every
later hardware phase fills without a redesign.

| | Decision (Clint, 2026-10-29) |
|---|---|
| Pack | 1S3P Li-ion: three 2,200 mAh cells in parallel, 6,600 mAh, 3.0 to 4.2 V, 3.7 V nominal, about 24.4 Wh. It may stay into the BQ25798 phase |
| Current phase | Adafruit bq24074 charger (#4755, 1.0 A ISET jumper, R_ISET about 890 Ω, single VBUS input), one INA228 at 0x40 with its shunt in the battery path and its VBUS sense on the charger OUT, a MAX17048 at 0x36 on the cell, an SHT45, all on I2C2 (PA11 SDA, PA12 SCL) through a STEMMA QT hub. *Amended 2026-10-30 (section 17, record 1.4 and 7.1):* R_ISET = 1 kΩ (R9, behind the 1A jumper; record 1.4), so ICHG = KISET ÷ R_ISET = 890 ÷ 1000 = 0.89 A typ (0.80–0.98 A); ISET currents logged earlier with 890 Ω read 12 % high. Status: adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2. Clint to confirm (section 15, D4) |
| Official wiring | the bench wiring of 2026-10-28/29: ISET to PB1 (ADC1_IN5, CN8.1, A0); charger VBUS through 20 kΩ (two 10 kΩ in series) over 10 kΩ to PA10 (ADC1_IN6, CN8.3, A2), VIN = 3 × the pin; CHG to PB10 (CN10.25) and PGOOD to PB8 (CN10.27) with the internal pull-ups; the same MCU pins on the bench and in the field. The node firmware reads all of it. *Amended 2026-10-29 (section 17, record 1.4): the same two pins are also on the Arduino headers, CHG = D6 (CN9.7), PGOOD = D5 (CN9.6) (UM2592 Table 17); no pin changes*. *Amended 2026-10-30 (record 1.4, N1, N3; step 1 change A, record 4.4 step 13):* the official leads land on the Arduino headers: CHG to PB10 at D6 (CN9.7) and PGOOD to PB8 at D5 (CN9.6); CN10.25 and CN10.27 are their morpho aliases (the carrier uses them, record N7). ISET reaches PB1 through the record's M2 network (10 kΩ 1 % at the charger, then a node with 100 nF and 1 MΩ to logic ground, section 9.5), and the divider ratio is the measured one, stored in `power_config.h` (section 8.6): adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); Clint to confirm (section 15, D5) |
| Bench lessons | keep the battery path short and low resistance (a 0.2 Ω breadboard path ended 1 A charges early); the gauge senses the cell, not OUT; the INA228 VBUS jumper goes to the intended net |
| Final goal | voltage and current of four rails: battery (signed), solar input, USB-C input, load. One INA228 per rail at distinct I2C addresses; the BQ25798 ADC later as a cross-check |
| USB-C | bench work and occasional backup charging only, never connected together with solar |
| Wire format | a place for all power data now, source-agnostic (what is measured, not which chip), with "not measured" and "invalid" told apart, so that later phases need no redesign |
| Cadence | voltages and currents every minute in the observation; slow items every 15 minutes in the health report: power-monitor die temperature, MCU supply voltage (VDDA from VREFINT), reset cause, boot count, crash count and last crash PC, radio TX timeouts, I2C bus recoveries, gauge SOC and rate, CHG/PGOOD state |
| Gateway | decodes, stores and exposes every new value where the other values are (API, dashboard data, MQTT). Analysis and alerts are out of scope |

Out of scope (section 16 has the full list): gateway analysis and alerts; the energy-state thresholds
(the energy state stays NORMAL in this phase); the BQ25798 driver; WSMP on the radio (sub-project 7
of the sixteen-stations design); the phase B and C hardware builds.

## 2. Phases

The phases are named once here and used everywhere else (plans, docs, code comments).

| Phase | Charger | Monitors | MCU inputs | Status |
|---|---|---|---|---|
| **A** (current) | bq24074 (#4755), one VBUS input | battery INA228 0x40 (shunt in the battery path, VBUS jumper on OUT), MAX17048 0x36 Kelvin on the cell. *Amended 2026-10-30 (record P4, M4):* the gauge senses the CELL+ node by its red lead; its minus is unconnected and its ground comes over STEMMA QT (section 11.1) | ISET → PB1, VBUS divider → PA10, CHG → PB10, PGOOD → PB8, VREFINT | proven on the bench with `firmware/benchlink` on 2026-10-28/29 **except the shunt in the battery path**: the cell sat in the charger's LIPO socket, so the shunt carried no current. Exit criteria 3 and 4 prove that part. The node firmware reads phase A from this design on |
| **B** (four rails) | bq24074 | phase A plus a load INA228 (OUT), a solar INA228 and a USB-C INA228, each upstream of the point where the sources join (section 11.3). The firmware no longer reads the battery INA228's VBUS (the load INA228 owns the load voltage); its sense lead may stay on OUT or move to the CELL+ node as a host-side cross-check (section 17, record P5 and M4). *Amended 2026-10-30 (record step 1b, P5, M4; section 17's P5/M4 row):* it moves from OUT to CELL+ position 4 at step 1b, a host-side cross-check only | as phase A | later; the firmware table and the host tests cover it now |
| **C** (BQ25798) | TI BQ25798: VAC1 = solar, VAC2 = USB-C, its own ADC over I2C, MPPT | with or without phase B's INA228s (section 3.2 says what fills each slot either way) | PB8 = BQ25798 /INT (open drain, active low, the same pull-up rule); /CE strapped low, charging enabled and stopped over I2C; PB1, PA10 and PB10 are released (ISET, the divider and CHG go away; PB10 does not exist on the UFQFPN48 package). *Amended 2026-10-29 (section 17, record N8): this row said PB10 = STAT and PB1, PA10 reserved* | later; only the fill table is defined now |

Phases B and C may come in either order: section 3.2's phase C column defines every slot with and
without phase B's monitors. The pack may stay 1S3P in every phase. *Amended 2026-10-30 (record
7.1 Q3):* the carrier (step 3) stays 1S3P; the reserve question stays open (section 15, D1).

**Exit criteria of phase A** (all must hold before phase A counts as done):
1. The node firmware, not only benchlink, reads ISET, the charger input voltage, CHG, PGOOD, the
   INA228 (battery current, OUT voltage, die temperature) and the MAX17048 (cell voltage, SOC, rate)
   on the official hub wiring with no mux.
2. The gateway decodes, stores and exposes every value of the phase A column of section 3.
3. The bench acceptance drill (section 12.2) passes on one pack with the shunt in the battery path.
4. A charge at the 1A jumper with the shunt in the path ends in a normal termination (CHG off and
   steady, not flashing), and the battery-path limits of section 11.2 hold. *Amended 2026-10-29
   (section 17, record 1.4 and P9):* the #4755 ties TMR to GND (Adafruit schematic; confirm on the
   board in hand, build-sheet check 10), so every bq24074 safety timer is disabled and a charge of any
   length may run from empty. ICHG = KISET ÷ R_ISET and ITERM = 0.03 × R_ITERM ÷ R_ISET with
   R_ITERM = 10 kΩ, about 0.3 A at the board's R_ISET (section 15, D4). A healthy charge ends with CHG
   released while the battery INA228 current is between 0.20 and 0.40 A and the cell voltage is at
   least 4.12 V (VBAT(REG) 4.16 V minimum less 0.375 A × 115 mΩ, the P8 loop). The earlier text (start
   at ≥ 3.85 V or fit RTMR, because a long charge would end in a timer fault) assumed TMR floating.
   *Amended 2026-10-30 (record P9, M4, P8):* the cell voltage at CHG release is taken as gauge
   VCELL − I × R_pack in the last sample before CHG releases (under charge the gauge reads the CELL+
   node, above the pack terminal by the pack-side drop); R_pack is the measured sum of the two
   pack-side spans of section 11.2 (record 4.3 check C14). Every charge run logs its start time, the
   CHG pattern (section 6.3 edge rule) and the end point.

## 3. Rails, signs and the fill table

### 3.1 Sign conventions

| Rail | Positive means | Phase A INA228 orientation | Firmware sign |
|---|---|---|---|
| Battery | current **into the cell** (charging) | cell on VIN+, charger LIPO on VIN−: the part counts VIN+ → VIN− as positive, which is **out of** the cell | −1 (the firmware negates the CHARGE delta) |
| Load | current into the load | VIN+ at OUT, VIN− towards the load | +1 |
| Solar, USB-C | current into the station | VIN+ at the source, VIN− towards the charger | +1 |
| Charger input (phase C, BQ25798 IBUS) | current into the charger | — | as the part reports |

The current node release (04fcc656938d) adds a positive CHARGE delta to "charge in"
(`mod_power.c:145-150`). With the official orientation that counts a discharge as a charge. The
bench found this on 2026-10-28/29. This design fixes it with the rail table's sign (section 9.3), and
RELEASES.md records it against that release.

### 3.2 Every-minute values (observation)

"Absent" means that the build has no source for the value: the field is not in the record's bitmap.
INVALID means that the source is fitted but failed, or its reading is out of range. Phase C has two
builds: with phase B's INA228s ("C+B") and without them ("C alone"); a cell that names an INA228 "if
fitted" falls back to the BQ25798 in "C alone".

| Value (field) | Phase A | Phase B | Phase C |
|---|---|---|---|
| Battery voltage (`batt_mv`, 11) | MAX17048 VCELL (Kelvin to the cell), mean of the minute's 4 reads | as phase A | as phase A |
| Battery current (`batt_current_ma`, 12) | battery INA228 CHARGE delta over the window ÷ the window's time, sign −1 | as phase A | as phase A |
| Battery energy and charge counters (13–16) | ΔQ of the battery INA228 × VCELL, split by sign; energy INVALID in a minute where a step had no fresh VCELL (section 5.2) | as phase A | as phase A |
| Load voltage (`load_mv`, 26) | battery INA228 VBUS (jumpered to OUT) | load INA228 VBUS | load INA228 VBUS if fitted, else BQ25798 VSYS |
| Load current (`load_current_ma`, 27) | absent | load INA228 CHARGE delta ÷ time | load INA228 if fitted, else absent |
| Charger input voltage (`charger_input_mv`, 28) | PA10 divider × 3. **The source (solar or USB-C) is not identified** | as phase A (a cross-check of the source rails) | BQ25798 VBUS (the selected input, after its input FETs) |
| Solar voltage (`solar_mv`, 29) | absent | solar INA228 VBUS, upstream of the join | solar INA228 if fitted, else BQ25798 VAC1 |
| Solar current (`solar_current_ma`, 30) | absent | solar INA228 CHARGE delta ÷ time | solar INA228 if fitted, else BQ25798 IBUS while solar is the active input, and 0 mA while USB-C is or while there is no input (the solar input FETs are off) |
| USB-C voltage (`usb_mv`, 32) | absent | USB-C INA228 VBUS, upstream of the join | USB-C INA228 if fitted, else BQ25798 VAC2 |
| USB-C current (`usb_current_ma`, 33) | absent | USB-C INA228 CHARGE delta ÷ time | USB-C INA228 if fitted, else BQ25798 IBUS while USB-C is the active input, and 0 mA while solar is or while there is no input |

*Amended 2026-10-30 (record P4, M4), the `batt_mv` row's "Kelvin to the cell":* the gauge senses
the CELL+ node by its red lead; its minus is unconnected and its ground comes over STEMMA QT. The
row's source, the field definition and the wire format are unchanged.

- **Battery voltage stays on the gauge in every phase.** The MAX17048 senses the cell Kelvin
  (section 11.1). An INA228 VBUS is referenced to the INA's ground, which is system ground at the
  charger, so it would include the negative-lead drop (up to about 35 mV at 1 A within the section
  11.2 budget) and change sensor across a phase change. When the gauge is absent or fails, field 11
  is INVALID; there is no fallback source. *Amended 2026-10-30 (record P4, M4):* "Kelvin" is not
  literal. The gauge senses the **CELL+ node** by its red lead; its minus is unconnected (insulated)
  and its ground comes over STEMMA QT from logic ground, which meets the pack's STAR only through the
  one TIE. Whenever current flows, the reading differs from the pack terminal by I × R_pack (about
  25–35 mV at 0.9 A charge); the host tools label it "CELL+ node, includes the pack-lead drop" and
  show VCELL − I × R_pack beside it (section 12.1). The `batt_mv` definition (section 5.2) and the
  wire format stay as they are.
- **Phase A cannot tell solar from USB-C**: the bq24074 has one VBUS input, and no monitor sits
  upstream of the point where the sources join. The charger input slot exists for exactly that
  reason. The firmware never guesses the source (the benchlink dashboard's panel-specific heuristic
  stays a bench tool, section 12.1).
- **Phase B** has one monitor per source. **Phase C** knows its active input (the BQ25798 switches
  its input FETs) and reports it in the charger status byte (section 6.3, bits 6-7), which is what
  attributes IBUS to a rail in "C alone". **No input** (code 3: neither VAC1 nor VAC2 powers the
  charger, every night on solar with USB-C unplugged) is a reading, not a gap: in "C alone" both
  source currents are 0 mA and the source voltages are still VAC1 and VAC2; the system runs from the
  battery, which the battery and load rails show. *Amended 2026-10-29: code 3 was reserved, which left
  phase C with no way to send this state.*
- Solar and USB-C are never connected together, so at most one source rail carries current. Two
  source rails with current at the same time are a broken operating rule, visible in the data in
  phases B and C (analysing it is out of scope; phase A cannot see it).

### 3.3 Every-15-minute values (health report)

| Value (health key) | Phase A | Phase B | Phase C |
|---|---|---|---|
| Gauge SOC (`battery_soc_pct`), SOC rate (`battery_soc_rate_pct_h`) | MAX17048 SOC 0x04, CRATE 0x16 | as phase A | as phase A |
| Charger status (`charger_input_power_ok`, `charger_charging`, `charger_fault`, `charger_stage`) | PGOOD and CHG pins (section 6.3) | as phase A | BQ25798 status registers |
| Charger active input (`charger_active_input`) | not reported | not reported | BQ25798 input selection: `solar`, `usb_c`, or `no_input` when neither input powers the charger |
| Power-monitor die temperature (`power_monitor_temp_c`) | battery INA228 DIETEMP | the hottest of the four INA228s | the hottest fitted INA228 |
| MCU supply (`mcu_supply_mv`) | VDDA from VREFINT | as phase A | as phase A |
| Charger-reported input voltage and current (`charger_reported_input_mv`, `charger_reported_input_ma`) | not measured | not measured | BQ25798 VBUS, IBUS |
| Charger-reported battery voltage (`charger_reported_battery_mv`) | not measured | not measured | BQ25798 VBAT |
| Charger-reported charge current (`charger_reported_battery_ma`) | ISET: I = 400 × V_ISET ÷ R_ISET (SLUS810 eq. 3) while PGOOD is asserted; **0 mA while PGOOD is deasserted** (no input, no charge current); none only when the ADC sequence failed, no new sequence completed in the minute, or the reading clipped | as phase A | BQ25798 IBAT |
| Charger die temperature (`charger_temp_c`) | not measured | not measured | BQ25798 TDIE |
| Pack temperature (`pack_temp_c`) | not measured (the NTC on THERM goes to the charger only) | not measured | BQ25798 TS |

The "charger-reported" keys carry the charger's own measurements. They are named apart from the
observation field `charger_input_mv` (field 28), which is a separate measurement (the PA10 divider in
phases A and B); the two never share a name (section 10.2). The station items (reset cause, boot
count, crashes, last crash PC, TX timeouts, I2C recoveries) are filled in every phase (section 9.8).

## 4. Protocol version 6

Every change in sections 5 and 6 ships under **protocol version 6**: byte 0 of a frame becomes 0x61
(observation), 0x62 (ACK), 0x63 (NACK), 0x64 (health report). The envelope, nonce, counter, tag and
the ACK/NACK plaintext do not change. No new frame kind is added.

- **Why a bump.** Under version 5 a gateway that was not updated would NACK the new bitmap bits
  (reason 2, `fields.decode`), and the node would abandon those records: permanent loss. An RX bridge
  that was not updated would drop the longer health report silently. With version 6 a mismatched end
  drops the frames as another version, so the records stay in the journal until both ends match.
- **Time sync becomes version 7.** The sixteen-stations design (section 5) planned version 6 for the
  time sync alone, with the catalog and the health report unchanged. Power telemetry takes version 6;
  the time sync keeps its rule ("one change per version") as version 7. That spec gets a dated note.
- **Release procedure** (replaces `protocol-design.md` section 7 for this and every later format
  change):
  0. Drain the journal: wait for `pending=0` on the TX console (a WIPE discards pending records).
  1. WIPE the node.
  2. Flash the RX board and the TX board from the same release (the TX and RX roles share
     `WS_FRAME_VERSION`; the boot known-answer test vectors change with the version byte).
  3. `init` a new run directory. The old run directory and its database stay with the old release.
  4. Run `provision-node` with the new key.
  5. Start the gateway (`RECORD_VERSION` 6).
  6. Record the release in `RELEASES.md` with the protocol version, the field set, the power wiring
     phase and the monitored rails.
- **Old data.** A run directory belongs to one record version, as today (`protocol-design.md`
  section 5.7). No migration. No catalog name is renamed, so a v5 database stays readable by the v5
  release and names mean the same thing across runs, except field 11 (section 5.2), whose v5 values
  are documented as "INA228 VBUS of whatever net the jumper sensed".
- **Home Assistant.** Retained discovery configs of `soc_gauge_pct` and `charger_pins` from older
  runs stay in the broker; the release note says to remove the two entities in Home Assistant. The
  new health-report entities use their own unique-ID namespace (section 10.2), so they never collide
  with observation entities.

## 5. Observation, catalog version 2

### 5.1 Layout

The 22-byte header is unchanged except the meaning of bitmap bit 31.

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | epoch |
| 4 | 4 | sequence |
| 8 | 4 | UTC (0 = unknown) |
| 12 | 4 | uptime, s |
| 16 | 1 | flags: bit 0 UTC known, bits 1–2 energy state, bits 3–7 zero |
| 17 | 1 | calibration revision |
| 18 | 4 | field bitmap: bit *i* = field *i* for *i* = 0–30; **bit 31 = EXT** |
| 22 | 2 | **extension bitmap**, present only when EXT is set: bit *j* = field 32 + *j* |
| 22 or 24 | — | the present fields in increasing index order (0–30, then 32–47) |

Canonical rules added to `protocol.md` section 5.5:
- EXT set with an extension bitmap of 0 is rejected.
- An extension bitmap bit for an undefined field (today bits 2–15, fields 34–47) is rejected.
- A record with no field is rejected: base bits 0–30 all zero and EXT clear. A record whose only
  fields are extension fields (bitmap 0x80000000, extension bitmap non-zero) is legal.

In C the field mask becomes 64-bit: `WS_F(i)` is `(uint64_t)1 << i`, `ws_obs_t.bitmap` is a
`uint64_t` logical mask of field indices, and bit 31 is never a field (`WS_FI_EXT` = 31 is a
placeholder in the enum, width 0). `WS_FIELDS_DEFINED` is `(WS_F(WS_FI_COUNT) - 1) & ~WS_F(WS_FI_EXT)`,
defined for every count; `_Static_assert(WS_FI_COUNT <= 48)`. `WS_OBS_PLAIN_LEN(m)` adds 2 when
`m >> 32` is non-zero. Python keeps `HEAD = '>IIIIBBI'` and adds the optional `'>H'` extension word;
the catalog table is indexed by field index (no entry at 31). This fixes the undefined
`WS_F(WS_FI_COUNT)` shift at 32 fields (`ws_obs.h:43,46`).

### 5.2 New and changed fields

Currents are all one encoding: 2 bytes, 1 mA, offset binary (`code = I + 32768`), range **−32,768
to +32,766 mA** (codes 0–65534), 0xFFFF INVALID, sign per section 3.1, mean over the minute. A value
outside that range is INVALID; the C map uses the codec's own range check (`ws_obs_code_ok`), never a
separate symmetric clamp. Voltages are all 2 bytes, 1 mV, 0 to 65,534 mV, 0xFFFF INVALID, mean over
the minute. The encoding range is wider than any monitor's: an INA228 rail measures ±5.24 A at the
10 µA current step this design uses (section 9.4).

| *i* | Field | Bytes | Meaning | Change |
|---:|---|---:|---|---|
| 11 | `batt_mv` | 2 | battery terminal (cell) voltage, mean over the minute | **meaning corrected**: v5 builds sent the INA228 VBUS, which the official wiring puts on OUT |
| 12 | `batt_current_ma` | 2 | battery current, + into the cell, mean over the minute | **step 0.1 mA → 1 mA** (range ±3.27 A → −32,768 to +32,766 mA). Never sent before, so no stored value changes |
| 13, 14 | `energy_in_mwh`, `energy_out_mwh` | 3 | mWh since boot: Σ ΔQ × battery voltage over the steps whose battery current is positive (in) or negative (out) | **meaning corrected**: v5 builds integrated the INA228 ENERGY register, which is VBUS (OUT) × current. **INVALID in any minute in which a step added charge without a fresh battery voltage**; the counter then lacks that step's energy for good, so the energy delta across such a minute is unknown |
| 15, 16 | `charge_in_mah`, `charge_out_mah` | 3 | mAh since boot, split by the sign of section 3.1 | sign corrected (section 3.1) |
| 17 | `soc_gauge_pct` | 1 | as v1 | **retired**: version 6 builds do not send it. The health report carries SOC at 1/256 % and its rate |
| 18 | `charger_pins` | 1 | as v1 | **retired**: the health report carries the source-agnostic charger status (section 6.3) |
| 26 | `load_mv` | 2 | load (system rail) voltage: the charger output that supplies the station | new |
| 27 | `load_current_ma` | 2 | load current, + into the load | new |
| 28 | `charger_input_mv` | 2 | charger input voltage after the sources join, measured under load; **the source is not identified** | new |
| 29 | `solar_mv` | 2 | solar input voltage, upstream of the join | new |
| 30 | `solar_current_ma` | 2 | solar input current, + into the station | new |
| 31 | — | — | EXT: not a field (section 5.1) | new meaning of the bit |
| 32 | `usb_mv` | 2 | USB-C input voltage, upstream of the join | new, extension |
| 33 | `usb_current_ma` | 2 | USB-C input current, + into the station | new, extension |
| 34–47 | reserved | — | must be zero | — |

A retired field stays in the catalog: a version 6 gateway still decodes it, and a later build may
send it again with the same meaning. No field index is ever reused. The qualifiers field still
covers fields 0–15 only.

Field notes written into `protocol.md`: `charger_input_mv` is measured at the charger's VBUS while
the charger draws current, so it can sit at VIN-DPM (4.35–4.63 V, SLUS810) while the charger limits
its input current; it is not the source's open-circuit voltage and not a source identifier. VIN-DPM
acts only in the USB100 and USB500 modes (EN2 low, SLUS810 section 9.3.4.1.1); with EN2 high the
input current limit is set by R_ILIM and nothing regulates the input voltage: a source that cannot
supply the current is pulled down, as far as a FET drop above the cell (amended 2026-10-29, section
17, record 1.4; the weak-source analysis is `power-metering.md` section 5.4 and R16).

Gateway metadata (`ws0/fields.py`): every new field has unit `mV` or `mA`, Home Assistant device
class `voltage` or `current`, a label (section 10.1), and is in `DIAGNOSTIC_FIELDS`. No new field
is a counter. Names say what is measured; none names a chip.

### 5.3 Presence: absent, INVALID and quality

- **Absent** = the build has no source (the per-phase fill table, section 3). The WSMP slot behind it
  carries the new snapshot quality "not fitted" (section 8.3), and the interim catalog map leaves
  the field out of the bitmap. Absence is a property of the build (`WS_POWER_PROFILE`), never of a
  part's state, and never makes a record "partial".
- **INVALID** = a fitted source failed, or its reading is out of range (a clipped ADC, a current
  outside −32,768 to +32,766 mA, energy without a battery voltage). It follows the v1 rules
  unchanged: a sensor fault never changes which fields are present.
- **The power modules are always in the layout.** They are base-board modules fixed by
  `WS_POWER_PROFILE`, not pluggable ones (section 8.5). So a station whose INA228 and gauge are both
  dead sends fields 11–16 as INVALID, never absent, and the dashboard says "sensor fault", not "not
  measured in this build".
- `fields.quality` does not change: a present INVALID power field makes the record "partial". A
  healthy phase A record is "valid". The H01 verdict still counts temperature and humidity only.

### 5.4 Sizes

| Record | Plaintext | Frame | SF7 | SF12 |
|---|---:|---:|---:|---:|
| Phase A (every module in the layout) | 65 B | 81 B | 35.9 ms | 739.3 ms |
| Phase B, phase C+B (every rail, with the extension word) | 77 B | 93 B | 41.0 ms | 821.2 ms |
| Phase C alone (no `load_current_ma`) | 75 B | 91 B | 39.7 ms | 821.2 ms |
| The node's field set `WS_F_WSMP_BENCH` (widest record, `OBS_FRAME_MAX`) | 77 B | 93 B | 41.0 ms | 821.2 ms |
| **Per-build ceiling** (the journal rule of section 7) | 80 B | 96 B | 41.0 ms | 821.2 ms |
| Every catalog v2 field (accepted only by the RX bridge and the gateway; never a build) | 94 B | 110 B | 46.1 ms | 944.1 ms |
| v5 bench build, for comparison | 61 B | 77 B | 34.6 ms | 698.4 ms |

Airtimes use the firmware's formula (`ws_lora_airtime_ms`, 500 kHz, CR 4/5, explicit header, CRC).
Phase A's 65 B is the v5 bench set (61 B) less fields 17 and 18 (2 B) plus fields 12, 26 and 28
(6 B). The node's field set holds every power field of every phase, so moving between phases changes
neither the journal slot nor the page magic. **The frame ceiling of a node build is 96 B** (80 B of
plaintext); the 110 B bound exists only so the RX bridge and the gateway accept any canonical
record. The sixteen-stations slot table, sized for 94 B, is recomputed for 96 B (at SF8 a 96 B frame
takes 74.4 ms against 72 ms for 94 B; section 15, R13).

## 6. Health report (kind 4), version 6

### 6.1 Layout: 64 bytes

The first 32 bytes keep their version 5 layout. The report grows to a fixed 64 bytes (frame 80 B,
35.9 ms at SF7, 739.3 ms at SF12). A fixed length keeps the RX bridge's exact-length check
(`ws_console.c:82`) and the gateway's `PLAIN_LENGTHS`.

| Offset | Bytes | Type | Field (C member) | None code | Gateway key |
|---:|---:|---|---|---|---|
| 0–31 | 32 | | unchanged (`protocol.md` section 4) | | unchanged |
| 32 | 4 | u32 | PC of the last crash since power-up, backup register DR6 (`crash_pc`) | 0 = none; 0xFFFFFFFF = the stacked frame was not trusted (`fault.c:26`) | `last_crash_pc`: 8 hex digits, `null` for 0 |
| 36 | 2 | u16 | boots since power-up, backup register DR12, saturating (`boots`) | — | `boots_since_power_up` |
| 38 | 2 | u16 | radio TX timeouts since boot, saturating (`tx_timeouts`) | — | `tx_timeouts_since_boot` |
| 40 | 2 | u16 | I2C bus recoveries started since boot, saturating (`i2c_recoveries`) | — | `i2c_recoveries_since_boot` |
| 42 | 2 | u16 | MCU supply VDDA, mV, mean of the last minute's VREFINT conversions (`vdda_mv`) | 0xFFFF | `mcu_supply_mv` |
| 44 | 2 | i16 | power-monitor die temperature, 0.1 °C: the hottest fitted INA228, latest read (`monitor_temp`) | −32768 | `power_monitor_temp_c` |
| 46 | 2 | u16 | gauge SOC, 1/256 % (the MAX17048 register as read; can exceed 100 % near full) (`soc`) | 0xFFFF | `battery_soc_pct` |
| 48 | 2 | i16 | gauge SOC rate, 0.1 %/h, + while charging, saturating (`soc_rate`) | −32768 | `battery_soc_rate_pct_h` |
| 50 | 1 | u8 | charger status, section 6.3 (`charger_status`) | 0xFF | `charger_input_power_ok`, `charger_charging`, `charger_fault`, `charger_stage`, `charger_active_input` |
| 51 | 1 | u8 | **fitted**: the slots this build has a source for, one bit a group (table below); bit 7 reserved, 0 (`fitted`) | — | `power_not_measured`, `power_sensor_faults` |
| 52 | 2 | u16 | charger-reported input voltage, mV (`chg_input_mv`) | 0xFFFF | `charger_reported_input_mv` |
| 54 | 2 | i16 | charger-reported input current, 1 mA, + into the charger (`chg_input_ma`) | −32768 | `charger_reported_input_ma` |
| 56 | 2 | u16 | charger-reported battery voltage, mV (`chg_batt_mv`) | 0xFFFF | `charger_reported_battery_mv` |
| 58 | 2 | i16 | charger-reported charge current, 1 mA, + into the cell, mean of the last minute (`chg_batt_ma`); phase A: 0 while PGOOD is deasserted | −32768 | `charger_reported_battery_ma` |
| 60 | 2 | i16 | charger die temperature, 0.1 °C (`chg_temp`) | −32768 | `charger_temp_c` |
| 62 | 2 | i16 | pack temperature, 0.1 °C (`pack_temp`) | −32768 | `pack_temp_c` |

Python: `DIAG = struct.Struct('>IIHIHHHHBBIbbBBIHHHHhHhBBHhHhhh')` (64 B; byte 51 is decoded as
`B`, not skipped). The 2-byte counts saturate at 0xFFFF as today. Signed "none" codes are the type's
minimum, as `WS_SIGNAL_NONE` is for the i8 signal fields; unsigned ones are all-ones. The gateway
maps every none code to `null`.

**The fitted byte** (amended 2026-10-29; byte 51 was "reserved, must be 0"). One none code a slot
cannot tell "this phase has no source" from "the fitted source failed", which the observation keeps
apart as absent and INVALID (section 5.3). Byte 51 carries the difference: a set bit says the build
has a source for its slots, so a none code there is a sensor fault; a clear bit says the slots are
not measured in this build.

| Bit | C (`ws_frame.h`) / Python (`protocol.py`) | Slots | Phases A, B |
|---:|---|---|---|
| 0 | `WS_FIT_MCU_SUPPLY` / `FIT_MCU_SUPPLY` | `vdda_mv` | set |
| 1 | `WS_FIT_MONITOR_TEMP` / `FIT_MONITOR_TEMP` | `monitor_temp` | set |
| 2 | `WS_FIT_GAUGE` / `FIT_GAUGE` | `soc`, `soc_rate` | set |
| 3 | `WS_FIT_CHARGER_STATUS` / `FIT_CHARGER_STATUS` | `charger_status` bits 0–2 (power good, charging, fault) | set |
| 4 | `WS_FIT_CHARGER_REGS` / `FIT_CHARGER_REGS` | `charger_status` stage and active input, `chg_input_mv`, `chg_input_ma`, `chg_batt_mv`, `chg_temp` | clear |
| 5 | `WS_FIT_CHARGE_CURRENT` / `FIT_CHARGE_CURRENT` | `chg_batt_ma` | set |
| 6 | `WS_FIT_PACK_TEMP` / `FIT_PACK_TEMP` | `pack_temp` | clear |
| 7 | — | reserved, 0 | 0 |

Phases A and B send 0x2F (`mod_power.c` `HEALTH_FITTED`); phase C sets the bits of the parts it has.
The gateway stores two derived keys: `power_not_measured` (the `null` power keys whose bit is clear)
and `power_sensor_faults` (the `null` power keys whose bit is set), both sorted lists. The dashboard
says "sensor fault" for the second and "not measured in this build" for the first; Home Assistant
gets no entity for a key in the first (section 10.2).

**Canonical rules** (written into `protocol.md` section 4). The node never sends a non-canonical
report. A health report is never answered, so the gateway keeps every other value of a report that
breaks one:
- Bit 7 of byte 51 (the fitted byte) must be 0. If it is not, the gateway logs a warning and stores
  the report (`ws_diag_pack` writes `fitted & WS_FIT_DEFINED`, so the node never sets it).
- A charger status byte other than 0xFF with stage 7 is invalid: the gateway stores the five charger
  keys as `null` and logs a warning. Every active input code (bits 6-7 = 0 to 3) is canonical
  (section 6.3; amended 2026-10-29, code 3 was reserved).

`ws0/protocol.lit.md` provides `unpack_diag(payload) -> dict` (raw values by C member name),
`pack_diag(**fields)` (missing new fields default to their none codes, `fitted` to 0) and
`diag_problems(d) -> tuple[str, ...]` (the broken rules above, empty when canonical).

### 6.2 What the slow values mean

- **Boots since power-up** and **crashes since power-up** live in RTC backup registers, which a
  power loss clears (the NUCLEO has no backup battery). DR12 is the boot counter. One function owns
  it: `fault_boot_note(int power_on)` in `fault.c` zeroes DR12 when the reset cause is power-on and
  then adds one (saturating at 0xFFFF). It is called exactly once a boot, by `app_tx`, `app_rx` and
  benchlink's `bl_guard.c`, which loses its own increment (`bl_guard.c:62-69`); so the node and
  benchlink count the same way and never twice. The durable boot count since provisioning is the
  epoch, already at offset 0.
- **Last crash PC** is the PC that `fault_record` stored. It stays after `fault_report` (which clears
  only the magic) until the next crash or a power loss. `fault_last_pc()` returns 0 when the crash
  count is 0.
- **TX timeouts** count every `EV_TX_TIMEOUT`, in both the observation and the health-report paths
  (`tx_timed_out`, `App/tx_exchange.c:127-133`, called from the observation path at :393-394 and the
  health-report path at :417). The failure run `tx_counts.air` stays as it is.
- **I2C recoveries** count every stuck-bus recovery that the bus starts (`recover_begin`,
  `App/i2c_bus.c:316-318`).
  Recoveries that end with SDA still low and mux RESET pulses go to `#status` only.
- **Values are cached.** `send_diag` copies cached values only (`mod_power_health`, the fault and
  counter accessors). Nothing in the radio path touches I2C or the ADC.

### 6.3 Charger status byte

| Bits | Meaning | Phase A source | Phase C source |
|---|---|---|---|
| 0 | input power good | PGOOD asserted | PG_STAT |
| 1 | charging | CHG asserted steadily | CHG_STAT in trickle, pre-charge, CC, CV or top-off |
| 2 | fault | CHG flashing at about 2 Hz (SLUS810 section 9.3.5.6 and table 9-2): 3 or more CHG edges within 2 s; clears after 4 s without an edge | any FAULT_STATUS bit |
| 3–5 | charge stage: 0 not reported, 1 pre-charge or trickle, 2 constant current, 3 constant voltage, 4 top-off, 5 terminated, 6 not charging, 7 reserved (non-canonical) | 0 (the pins cannot tell) | CHG_STAT |
| 6–7 | active input: 0 not reported, 1 solar input, 2 USB-C input, 3 no input (the charger reports that neither input powers it) | 0 (one VBUS; the source is not identified) | the BQ25798 input selection, mapped to the rail by the fill table (VAC1 = solar, VAC2 = USB-C); 3 when neither VAC1 nor VAC2 is present |

0xFF = no charger status (its stage is 7, so it can never be a real status byte). **"Not reported"
and "no input" are different codes** (amended 2026-10-29): 0 says the input is not reported (phases A
and B cannot tell it; in a phase C build, whose fitted bit 4 is set, a 0 means the BQ25798 read failed,
a sensor fault), 3 says the charger reported that no input is present. With the fitted byte, the gateway then never files a normal night without input
under `power_sensor_faults`: code 3 is a value, not `null`. Phase A limits, written into `protocol.md`:
- CHG is off during a refresh charge after termination (table 9-2), so "not charging" in phase A is
  read together with the battery current and the charger-reported charge current.
- CHG asserted without PGOOD is kept as it is (bit 1 set, bit 0 clear). The stage is 0.
- **TMR is tied to GND on the #4755** (Adafruit schematic, X4.TMR in net GND; SLUS810 pin table:
  "Connect TMR to VSS to disable all safety timers"; `wiring.toml` CHGR note). Confirm it on the board
  in hand (build-sheet check 10). CHG flashing at 2 Hz is the bq24074's only fault indication and
  signals expired safety timers (SLUS810 section 9.3.5.6, table 9-2), so with TMR at GND a phase A
  `charger_fault` does not mean a long charge: it means something else, such as a board strapped
  differently from the schematic (TMR not at GND) or a CHG line that toggles at about 2 Hz for
  another reason (an intermittent CHG contact). The fault clears when CE or the input is toggled.
  *Amended 2026-10-29 (section 17): this bullet said a safety-timer fault was an expected phase A
  outcome of a long charge, which assumed TMR floating.*

Gateway keys: three booleans (`null` when the byte is 0xFF); `charger_stage` as one of `precharge`,
`cc`, `cv`, `topoff`, `terminated`, `not_charging` or `null`; `charger_active_input` as `solar`,
`usb_c`, `no_input` or `null` (`null` for code 0, not reported, or for no status).

### 6.4 Cadence and airtime

Unchanged cadence: after boot, every 15 minutes, and after each link-state change, after that
minute's exchange. Health reports have no journal: an outage loses the slow values of its reports.
That is accepted. The SOC and status have gaps; the counters recover with the next report; every
fast value is in the journaled observation.

**Airtime rule** (`radio-energy-policy.md` sections 6 and 9, `ws_minute_backlog`): in a minute whose
health report is due, the backlog allowance first reserves the health frame's airtime from the energy
state's cap, saturating:

```
by_airtime = cap_ms > reserve_ms ? (cap_ms - reserve_ms) / exchange_ms : 0
backlog    = by_airtime > 1 ? min(backlog, by_airtime - 1) : 0     (never below 0)
```

The live reading and a due health report always go. Today's `backlog = by_airtime - 1` wraps when
`by_airtime` is 0 (`ws_policy.c`, unsigned); the new form cannot. At SF7 nothing changes (a 359 ms
exchange, 13 per 5 s). At SF12 (exchange 821.2 + 411.6 + 300 = 1,532.8 ms) NORMAL allows 3
exchanges, and 2 in a health minute. In CONSERVE at SF12 the live exchange plus the health report is
2,272 ms (2,274 ms with the firmware's whole-millisecond rounding: 1,534 + 740), over the 2 s cap
**once per health report**: every 15 minutes plus once after each link-state change. CONSERVE sends
only every 5th minute, so its average stays far below the cap. The policy documents that exception.
(The energy state is NORMAL in this phase.)

## 7. The journal

`node_store.c:71-76` asserts 24 hours for every catalog field (`WS_OBS_PLAIN_ALL`). Catalog v2 makes
that 94 B, a 112 B slot, 18 slots a page, 1,242 records: the build would fail. The rule changes to
**24 hours of the build's widest record** (`WS_OBS_PLAIN_MAX`, from `WS_NODE_FIELDS`), with the
same assertion. A build whose field set exceeds 80 B plaintext (a 96 B frame) does not compile; that
is the per-build ceiling of section 5.4.

| Field set | Plaintext | Slot | Slots a page | Records (69 pages) | Hours |
|---|---:|---:|---:|---:|---:|
| v5 bench build | 61 B | 80 B | 25 | 1,725 | 28.75 |
| v6 node field set (phases A–C) | 77 B | 96 B | 21 | 1,449 | 24.15 |
| every catalog v2 field (not a build) | 94 B | 112 B | 18 | 1,242 | 20.7 |

`flash_layout.h:20` and `tests/test_flash_layout.py` change with it: the test builds the default
field set and checks the slot count against the formula, not a fixed 21. The slot size changes, so
the page magic changes and the first boot of the version 6 image recycles every old page; the
release procedure drains the journal first (section 4).

## 8. WSMP: registry and module types

### 8.1 Registry (append-only, registry version 1 → 2)

New quantities (WSMP-G1: new codes, never reused):

| Code | Name | Unit | Range | HA class | Note |
|---:|---|---|---|---|---|
| 18 | load voltage | V (8) | 0–30 | voltage, measurement | the system rail that supplies the station: the charger output |
| 19 | load current | A (9) | −20 to 20 | current, measurement | positive into the load |
| 20 | charger input voltage | V | 0–30 | voltage, measurement | after the sources join; the source is not identified |
| 21 | solar input voltage | V | 0–30 | voltage, measurement | upstream of the join |
| 22 | solar input current | A | −20 to 20 | current, measurement | positive into the station |
| 23 | USB-C input voltage | V | 0–30 | voltage, measurement | upstream of the join |
| 24 | USB-C input current | A | −20 to 20 | current, measurement | positive into the station |

Quantity 9 "battery voltage" now means the cell terminal voltage, and quantity 10 "battery current"
(positive while charging) is used for the first time; neither code's meaning or unit changes.

New module types (function names; chips are display metadata only):

| Code | Name, id | Role | Class | Channels (quantity/kind) | Descriptors |
|---:|---|---|---|---|---|
| 8 | battery, `BATTERY` | battery | minute | 9/mean, 10/mean, 11/counter, 12/counter, 13/counter, 14/counter | V −3 w2 unsigned; A −3 w2 signed; Wh and Ah −3 w3 (as type 5) |
| 9 | power rails, `POWER_RAILS` | power | minute | 18/mean, 19/mean, 20/mean, 21/mean, 22/mean, 23/mean, 24/mean | V −3 w2 unsigned; A −3 w2 signed |

Type 5 "battery and charger" stays in the registry, frozen (schema 1 keeps decoding old descriptor
sets); version 6 builds do not build it. That avoids multi-schema support in the registry. One
quantity code per rail keeps the WSMP-H1 entity IDs (`<station>_<role>_<quantity>_<kind>`) distinct
without a per-channel role, so the descriptor format, `wsmp_unpack_desc` and WSMP-H6 do not change.

The lock file also records each type's report class, role and state names (new lines
`type_meta <type>.<schema> <class> <role> [states]`, appended for every type), so those can no longer
change silently. The registry version rule: it increments with every release that appends a code.

Several files hold independent, hand-written copies of the registry on purpose (test oracles): the
WSMP record reference `tests/wsmp_record_ref.py` and its test, and the fuzz oracles
`firmware/fuzz/fuzz_wsmp.c` and `fuzz_record.c`. They learn types 8 and 9 and quantities 18–24 from
this table, not from the generated header.

### 8.2 The slow items are not WSMP channels in this phase

SOC, SOC rate, charger status, die temperatures, VDDA, the charger-reported measurements and the
station counters reach the health report through `mod_power_health()` and the station accessors, not
through WSMP health-class channels. Rule 7, WSMP-G8 and section 11.3 of `module-protocol.md` change to
say so; sub-project 7 decides whether they become health-class channels on the radio. No module type
is health class after this change.

### 8.3 Snapshot quality "not fitted" (WSMP 1.0 → 1.1)

| Snapshot | Radio | Meaning |
|---:|---:|---|
| 6 | 3 | **not fitted**: this hardware build has no source for the channel. The value is not used |

Local binding only: code 6 already maps to "missing" on the radio (`wsmp.c:191-196`), so `wsmp.c`
does not change. `WSMP_VERSION_MINOR` becomes 1 (a compatible addition, WSMP-V2). WSMP-A2 holds: the
channel keeps its place.

The "not fitted versus missing" distinction holds **locally and through the catalog map** (a not
fitted slot becomes an absent field; a missing one becomes INVALID). It does not survive the 2-bit
WSMP radio quality: a receiver of a WSMP radio reading sees both as "missing". The WSMP-Q1 claim is
limited accordingly ("not fitted slots are not counted where the station's snapshots are evaluated").
Before WSMP readings travel (sub-project 7), the set needs a set-level marker for not fitted channels,
for example a per-channel flag in the descriptor set or a profile-dependent channel list (risk R10).

### 8.4 Budget, limits and ports

| Item | Before | After | Limit |
|---|---:|---:|---:|
| Minute channels | 11 | 24 (11 + 6 battery + 7 rails) | 24 (WSMP-P8) |
| Modules | 7 | 8 (6 + battery + rails) | 8 (WSMP-P8) |
| Minute values + quality | 23 + 3 = 26 B | 53 + 6 = 59 B | **60 B** (WSMP-A1) |

WSMP-A1's budget is "the planned plaintext less a 20-byte header". The planned plaintext limit is
now the journal's 80 B per build (section 7), so `WSMP_RADIO_BUDGET` becomes 60. The phases add no
channels (the rails module has every rail from the start), so the station stays at the limits in
every phase. Any further module or channel needs WSMP-P8 and A1 revised in sub-project 7. That is
risk R2 (section 15).

Ports (`wsmp_local.h`): `P_POWER` (5) becomes `P_BATTERY` (5, type 8) and a new `P_RAILS` (8, type 9),
`P_COUNT` 9. The ports design's port table (its section 6.7, "Port numbers") gets port 9 = battery, 14
= power rails, v2 remote ports from 15. Both local serials (`WSMP_LOCAL_SERIAL`) change once, because
the type changes; each starts a new counter series (WSMP-C3). The release notes say so.

### 8.5 Presence of the power modules (WSMP-P1)

The battery (port 5) and rails (port 8) modules are base-board modules fixed by `WS_POWER_PROFILE`,
not pluggable ports. **Both are present in every profile, always**, whatever their parts answer:
- A missing part (NACK or wrong ID) makes only its own channels missing; a bus fault (WSMP-P3) makes
  them fault. In phase A the battery INA228 gives the battery current, the counters and the load
  voltage; the gauge gives the battery voltage; the board ADC gives the charger input voltage.
- A channel the profile has no source for is "not fitted" (section 8.3).
- So the map turns a dead part into INVALID fields, never absent ones (section 5.3).

### 8.6 Calibration of the power parts

Base power constants are build constants in `App/power_config.h`, each with the build-sheet check
that measured it cited beside it, and marked "nominal" until measured:
- each rail's shunt in µΩ (15,000 µΩ nominal: the #5832's R1 is 15 mΩ, 1 %, 2 W, 2512) and its
  current step (`current_lsb_ua`, section 9.4). *Amended 2026-10-29 (section 17, record M1):* the
  shunt constant is **verified, not measured**: the battery current must agree with a series
  reference within 2 % + 2 mA (section 12.2); a value derived from that reference replaces the
  nominal only if the check fails (a two-wire meter cannot resolve 15 mΩ better than its 1 %);
- R_ISET in Ω (890 Ω nominal, inferred from KISET = 890 A·Ω at 1.0 A; measured ISET to GND with the
  charger unpowered and the cell disconnected). The Adafruit schematic shows R9 = 1 kΩ behind the 1A
  jumper (record 1.4), which would make ICHG 0.89 A typical and the 890 Ω constant read the ISET
  current about 12 % high; the constant stays Clint's 890 Ω until build-sheet check 2 measures the
  board in hand (section 15, D4). *Amended 2026-10-30 (record 1.4, M2, 7.1 P3):* the nominal is
  `POWER_R_ISET_OHM 1000` (R9 behind the 1A jumper; ICHG 0.89 A typ; earlier ISET currents logged
  with 890 Ω read 12 % high): adopted with change A, read by this workflow from record 7.1 P3
  "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured
  divider); R_ISET confirmed by build-sheet check 2. Clint to confirm (D4);
- *Added 2026-10-30 (record M2, D5):* the ISET gain in ppm, `POWER_ISET_GAIN_PPM 990099` (1 MΩ ÷
  1.01 MΩ, the attenuation of the 10 kΩ series resistor into the 1 MΩ node pull-down), nominal until
  fitted: a one-time per-board fit against the battery INA228 during a CC charge above 200 mA with the
  load disconnected multiplies it;
- the divider ratio (3, from the two measured resistances). *Amended 2026-10-30 (record M2, D5):*
  `POWER_VIN_DIVIDER_PPM 3000000` (ratio × 10⁶), nominal until the three divider resistors are
  measured with the meter (record 4.4 step 12), then the measured ratio; checked in circuit within
  1 % (section 12.2).

The constants are identified by two things a gateway already has (*amended 2026-10-29*): the
firmware build ID in the health report names the commit, so the `power_config.h` a build used, and
the observation's power fields name the profile (absence is a property of `WS_POWER_PROFILE`,
section 5.3: profile 2 sends `load_ma` and the solar and USB-C fields, profile 1 never does). The
build ID is the commit's first 8 hex digits only for a build from a clean tree; a build with
uncommitted changes (`git describe --dirty`) sends build ID 0, "not identified", so a measured
constant edited into `power_config.h` but not committed can never pose as the nominal build
(`firmware/stage0-node/Makefile`). A measured constant is therefore committed before the build that
carries it is flashed for data. The other `OPT` build constants (`WS_I2C_MUX` and the bench switches)
change no power constant. WSMP record calibration (registry calibration table) does not apply to
them.

## 9. Node firmware

### 9.1 I2C bus profile: hub or mux

The node bus (`i2c_bus.c:153-157`) needs a TCA9548A mux today: with no mux at 0x71 every client gets
`I2C_EBUS`, and the boot phantom check refuses the SHT45, BMP581 and LTR390 seen upstream. The
official current-phase wiring is a passive STEMMA QT hub. A build constant chooses:

| `WS_I2C_MUX` | Topology | Behaviour |
|---|---|---|
| 0 (**firmware default**, the official phase A design) | STEMMA QT hub, no mux | every client upstream; no mux boot job, no deselect plan, no phantom check; the record clients complete with `I2C_ENACK_ADDR` without bus traffic (no record EEPROMs on the hub), so port modules are admitted with `NO_RECORD` (READ) as the ports design allows |
| 1 | the ports board with the TCA9548A at 0x71 | as today |

Host builds: the existing host libraries (`tests/toolchain.py` `wsmp_sources()`, the TX and RX
harnesses) pass `-DWS_I2C_MUX=1` explicitly, so every existing module, record and calibration test
keeps its mux and its record EEPROMs. A separate hub variant (`-DWS_I2C_MUX=0`) serves the new tests:
the hub boot in `test_i2c_bus`, `test_power_acq`, and the phase A TX harness of `test_tx_machine`.
In the host bus model's no-mux mode (`i2c_sim.c`) no mux device exists and `i2c_sim_add` places every
device upstream, whatever its address. In the mux mode an INA228 is never placed behind a channel
(the channel rule keys on the device kind).

### 9.2 Addresses and the bus

| Part | Address | Straps (INA228: A1, A0) | Phase |
|---|---|---|---|
| battery INA228 | 0x40 | GND, GND (default) | A |
| load INA228 | 0x41 | GND, VS | B |
| solar INA228 | 0x45 | VS, VS | B |
| USB-C INA228 | 0x48 | SDA, GND (rework: the Adafruit #5832 jumpers reach VS only) | B |
| MAX17048 | 0x36 | — | A |

Never an INA228 address: 0x44 (SHT45, a phantom address), 0x46 and 0x47 (BMP581), plus 0x36, 0x50,
0x53, 0x70, 0x71. `power_config.h` asserts at build time that the rail addresses are distinct and
outside that set. Verify the strap table against the INA228 datasheet (SBOS904) before strapping.
*Amended 2026-10-29 (section 17, record 1.4):* the #5832 has **no pull-up cut jumper** (its SDA and
SCL pull-ups share a 10 kΩ resistor pack with the ADDR pull-downs), so the extra INA boards keep their
pull-ups and the bus pull-up is measured (section 11.3). 0x48 is a rework wire from the ADDR1 pad to
SDA, which leaves that pad's 10 kΩ pull-down from SDA to GND (idle SDA about 2.97 V with 1.11 kΩ up,
above 0.7 × 3.3 V). An SDA strap needs at least 100 ns of data hold on the address MSB (SBOS904): the
node's I2C2 timing gives SDADEL = 2, 2 × 62.5 ns + 1/48 MHz = 146 ns (`i2c_bus.c` `I2C_TIMING`,
`tests/test_i2c_bus.py` checks the field), so 0x48 stays. *Amended 2026-10-30 (record 7.1 Q1):*
this INA228 module preparation (the A0/A1 jumpers on the three extra #5832 boards, the 0x48 wire from
ADDR1 to SDA) is allowed; step 1b runs on the breadboard harness after H01, and the boards are
soldered into the module board only after 1b exits.

### 9.3 Power profile and rail table

`App/power_config.h` holds `WS_POWER_PROFILE` (A default, B, C) and a fixed rail table, no dynamic
allocation (Power of Ten):

| Column | Phase A row | Phase B adds |
|---|---|---|
| I2C client | `I2C_C_INA228` (battery) | `I2C_C_INA_LOAD`, `I2C_C_INA_SOLAR`, `I2C_C_INA_USB` |
| address | 0x40 | 0x41, 0x45, 0x48 |
| shunt, µΩ | 15000 (nominal, measure) | per board |
| current step, µA (`current_lsb_ua`) | 10 (±5.24 A) | 10 each |
| sign | −1 | +1 |
| VBUS net | OUT (fills load voltage) | load: OUT; solar, USB-C: their source; battery: not read (OUT, or CELL+ as a host-side cross-check, section 17). *Amended 2026-10-30:* battery: CELL+ from step 1b (record step 1b; section 17's P5/M4 row), not read by the node |
| slots | battery current, counters, load voltage | as section 3.2 |

A profile C build stops with `#error` (the BQ25798 driver is a later phase). Host tests build
profile B with four INA228 models to prove the phase B rows need no redesign.

### 9.4 Acquisition (`App/power_acq.c`)

| Part | Every | Reads |
|---|---|---|
| each INA228 rail | 1 s | SHUNT_CAL check (a mismatch = the part reset: identify, calibrate, new base), VBUS 0x05, CHARGE 0x0A |
| each INA228 rail | 60 s | DIETEMP 0x06 (7.8125 m°C a count) |
| MAX17048 | 15 s | VERSION 0x08, VCELL 0x02 (78.125 µV a count), SOC 0x04 (1/256 %), CRATE 0x16 (0.208 %/h, signed) |
| board ADC (section 9.5) | 1 s sample of the latest sequence | ISET, charger input, VREFINT |
| CHG and PGOOD | 250 ms, plus the CHG edge count | section 6.3 |

- **Calibration:** SHUNT_CAL = 13107.2 × 10⁶ × CURRENT_LSB × R_shunt, in integers
  `131072 × current_lsb_ua × shunt_uohm ÷ 10⁷` (10 µA, 15,000 µΩ → 1966). ADCRANGE stays 0
  (±163.84 mV). The CURRENT register, and so CHARGE, is 20-bit signed: a rail measures
  ±2¹⁹ × CURRENT_LSB, **±5.24 A at 10 µA** (the shunt ADC itself would reach ±10.9 A at 15 mΩ). That
  is the per-rail limit in phases A and B (the bq24074 charges at most 1.5 A). A later rail that
  needs more raises its `current_lsb_ua` (20 µA gives ±10.5 A, SHUNT_CAL `262144 × R_µΩ ÷ 10⁶`); one
  CHARGE count is then CURRENT_LSB × 1 s. The ENERGY register is no longer read.
- **Rail current (minute mean)** = sign × Σ ΔCHARGE (CURRENT_LSB·s a count) of the window's valid
  steps ÷ Σ their elapsed time from `clock_ms()` (never raw `HAL_GetTick`, which counts 1/1024 s;
  `clock.h`). The CHARGE accumulator integrates every conversion, so radio bursts between samples
  count. The step after a reset or calibration is only a new base. No valid step: missing.
- **Battery energy:** each step adds ΔQ_signed × the latest VCELL (at most 20 s old) to energy in or
  out by sign. A step with no fresh VCELL adds its charge but no energy and marks the window: both
  energy slots get quality "missing" for that window, so fields 13 and 14 are INVALID that minute
  (section 5.2). Charge counters add every valid step.
- **Shared decoders:** the INA228 and MAX17048 register conversions and the ISET, divider and
  VREFINT conversions live once in `firmware/common/power_regs.{c,h}`, used by the node, i2cscan and
  benchlink, with the datasheet vectors of `tests/test_i2cscan.py` (`code_shape.sh` forbids copies).

### 9.5 Board ADC: vane, ISET, charger input, VREFINT

`board_inputs.c` runs one interrupt-driven sequence (no `HAL_ADC_PollForConversion`, banned by
`tools/blocking_report.py:92`; no `HAL_ADC_ConfigChannel` while ADSTART is set), started from the
existing 250 ms vane tick: IN4 (PB2 vane), IN5 (PB1 ISET), IN6 (PA10 divider), VREFINT (IN13).
- Sampling time 160.5 cycles for all channels: VREFINT needs at least 4 µs (DS13293
  `tS_vrefint`, ds.txt:4600); the divider's 6.67 kΩ source needs at least 19.5 cycles (DS13293 table
  82); ISET is about 890 Ω. ISET goes to PB1 directly (Clint's official wiring). The record's ISET
  input network (10 kΩ series, 100 nF and 1 MΩ at PB1, a 1 MΩ ÷ 1.01 MΩ gain term) is deferred
  (section 17, M2): it would change the official wiring, so it waits for Clint. *Amended
  2026-10-30 (record M2, 4.4 step 11; section 15, D5):* the ISET source is the record's network: the
  charger's ISET header → 10 kΩ 1 % at the charger end → the ISET node, which has 100 nF and 1 MΩ to
  logic ground → PB1 (A0, CN8.1). The 100 nF is the source the ADC samples (the 160.5-cycle sample
  charge is negligible against it); the 1 MΩ discharges the node in about 0.1 s if the wire opens, so
  an open reads 0 V and the CHG cross-check flags it; a firmware fault that drives PB1 low leaves
  ISET at 1 kΩ ∥ 10 kΩ = 909 Ω (ICHG + 10 %) instead of a short. Adopted with change A, read by this
  workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and
  store the measured divider); R_ISET confirmed by build-sheet check 2. Clint to confirm (D5).
- Hardware oversampling ×16, shift 4.
- VDDA (mV) = 3300 × VREFINT_CAL ÷ VREFINT_raw (`__HAL_ADC_CALC_VREFANALOG_VOLTAGE`; VREFINT_CAL at
  0x1FFF75AA is taken at VDDA = 3.3 V on this part, DS13293 table 14, ds.txt:2265 — not 3.0 V).
- Pin µV = raw × VDDA ÷ 4095. Full scale is VDDA at the pin, so the charger input reads up to
  **3 × VDDA** (9.9 V at VDDA = 3.3 V).
- **Clipping:** with ×16 oversampling a result is 4095 only when every conversion clipped; an input
  just above full scale averages to 4090–4094. So a result **≥ 4080** (99.6 % of full scale) is out of
  range: the minute's `charger_input_mv` is INVALID (never about 9.9 V), and for ISET the
  charger-reported charge current is none.
- ISET current (µA) = 400 × V_ISET(µV) ÷ R_ISET(Ω). Its error is the ISET monitor's 1/400 ratio,
  ±10 % (SLUS810 section 9.3.5.1), plus R_ISET's own tolerance; R_ISET comes from the build-sheet
  measurement (section 8.6). Charger input (mV) = 3 × pin mV. *Amended 2026-10-30 (record M2,
  section 8.6):* V_ISET = V_PB1 × 10⁶ ÷ `POWER_ISET_GAIN_PPM` (990099 nominal: 1 MΩ ÷ 1.01 MΩ, times
  the per-board fit), and ISET current = 400 × V_ISET ÷ `POWER_R_ISET_OHM` (1000); charger input (mV)
  = pin mV × `POWER_VIN_DIVIDER_PPM` ÷ 10⁶ (3000000 nominal until the divider resistors are
  measured). The ISET current stays a cross-check value (`charger_reported_battery_ma`), never the
  battery current.
- **Input voltage limits.** The bq24074 IN survives 28 V but charges only below OVP (10.2–10.8 V).
  PA10 (FT_fa) allows at most min(VDD, VDDA) + 3.6 V and at most 5.5 V (DS13293 table 26): with the
  3:1 divider that is a VBUS of 16.5 V with the MCU powered and about 10.8 V with it unpowered. Phase
  A and B panels keep their cold Voc at or below about 10.2 V (the Voltaic P110 is 8.7 V cold). A
  higher-voltage source needs another divider ratio (for example 47 kΩ over 10 kΩ) or a clamp before
  PA10; in phase C the divider goes away.
- **The vane stays ratiometric:** its thresholds (`mod_wind.c:21-30`) and its pull-up share VDDA, so
  it keeps the fixed 3300 "ratio mV". VREFINT scales only the absolute inputs.
- PB1 and PA10 are analog, no pull. `board_inputs.c` asserts at build time that the debug outputs on
  power and bus pins are off (`sys_conf.h:61-71`, `sys_debug.c`): `DEBUG_RF_HSE32RDY_ENABLED` (PA10),
  `DEBUG_RF_NRESET_ENABLED` (PA11, I2C SDA), `DEBUG_RF_BUSY_ENABLED` (PA12, I2C SCL) and
  `DEBUG_RF_SMPSRDY_ENABLED` (PB2, the vane, now in the sequence) are all 0. `DBG_Init` drives PB12
  and PB13 (CN8.6 = A5) as push-pull probe outputs unconditionally (`sys_debug.c:83-104`); they are
  listed as probe outputs in the pin budget, never as free pins.
- CHG (PB10) also counts edges on EXTI10, both edges, for the fault rule of section 6.3. PB8 and
  PB10 keep their internal pull-ups. Constraint written in the header: with the pull-ups on, a pin
  must stay below min(VDD, VDDA) + 0.3 V (DS13293 table 26 note 3; table 76 note 7). The bench
  measured at most 2.9 V on USB; section 11.1 records which net the breakout's LEDs pull up to and
  measures the worst case.
- Pin constants: `#define ISET_PIN GPIO_PIN_1 /* PB1 */` and `#define VIN_PIN GPIO_PIN_10 /* PA10 */`,
  in the format `wiring.check_firmware` reads.
- Seams (link-time, as `board_charger_pins`): `board_power_adc()` (latest complete sequence: ISET,
  VIN and VREFINT raw counts, VDDA and the sequence number) and `board_charger_edges()`. A call
  returns the latest sequence again, with the same number, until a new one completes. `power_acq.c`
  samples a sequence once: a number it has already sampled is no sample, so a stalled ADC (its
  interrupt stopped, or every start refused) leaves the minute without samples (charger input
  MISSING, VDDA and the ISET current none) instead of repeating the last values as good. The host
  defines both seams once, in `firmware/host/sim_core.c`, which every harness links, with setters
  `h_power_adc()`, `h_power_adc_stall()` (the sequence number stops) and `h_charger_edges()` (one
  copy, so `jscpd` sees no clone).

### 9.6 The two WSMP modules and the health accessor (`mod_power.c`)

`mod_power.c` turns `power_acq`'s values into the battery module (type 8) and the rails module (type
9) at each latch, sets "not fitted" for the profile's empty slots, keeps both modules present
(section 8.5), and caches the slow values. `mod_power_health(power_health_t *)` returns them with
their none codes: SOC, rate, charger status, the hottest die temperature, VDDA and the
charger-reported measurements (phase A: the ISET current while PGOOD is asserted, 0 mA while it is
not, none when the ADC failed, stalled (no new sequence in the minute) or clipped). `power_acq.c` (drivers) and `mod_power.c` (WSMP face) keep
each function within `code_shape.sh` (≤ 60 lines, complexity ≤ 10), each with its own
`WS_CHECK_FILE` number.

### 9.7 The interim catalog map

`wsmp_catalog_map.c` maps the battery module to fields 11–16 (12 with its offset; the codec's range,
−32,768 to +32,766 mA, decides INVALID through `put()`/`ws_obs_code_ok`) and the rails module to
26–30, 32, 33. A "not fitted" slot leaves its field out; a missing or faulted slot gives INVALID; a
long window gives INVALID for the means and keeps the counters (as today), and an energy slot marked
missing (section 9.4) gives INVALID for fields 13 and 14 only. Fields 17 and 18 are no longer mapped.
`node_fields.h`'s `WS_F_WSMP_BENCH` becomes the 77 B set of section 5.4. The header comment drops the
"field 12 left out" reason (`wsmp_catalog_map.c:5-6`).

### 9.8 Station health sources

| Item | Source |
|---|---|
| last crash PC | `fault_last_pc()` (new, `fault.h`) |
| boots since power-up | `fault_boots()` (new): DR12, kept by `fault_boot_note()` (section 6.2), the only writer |
| TX timeouts | `tx_counts.tx_timeouts` (new, `tx_exchange.h`), saturating; shown on `#status` |
| I2C recoveries | `i2c_bus_recoveries()` (new); `i2c_bus_stuck()` and the mux resets on `#status` only |
| VDDA, power values | `mod_power_health()` |
| reset cause | as today. A brown-out still reads as "power" (`watchdog.c:42-48`): a known limitation, written in `watchdog.h` |

`send_diag` (`tx_exchange.lit.md`) fills the 64-byte report from these, and the `#diag sent` console
line appends the new keys after the existing ones (scripts that read it keep working). A host test
compiles `fault.c` against a stub of the TAMP backup registers (`tests/test_fault.py`): count 0 gives
PC 0, the boot count saturates at 0xFFFF and resets on a power-on.

### 9.9 Energy state

`energy_state()` stays NORMAL (`tx_policy.c:28`). The thresholds need measured loads (H02) and
Clint's call on the pack reserve (section 15, D1). `tx_policy.h` and the node README say "deferred"
instead of "USB-powered bench".

### 9.10 Budgets

The TX build was 83,792 B of 112,640 (74.4 %) at c7e8860 in a scratch build. The new code (ADC
sequence, rail driver, shared decoders, health packing) is estimated at 4–7 KB. `docs/firmware-budget.md`
records the measured flash and stack after the change; `send_diag`'s stack grows by 64 B (two
buffers).

## 10. Gateway

### 10.1 Observation fields

| Field | Label | Unit | HA class |
|---|---|---|---|
| `batt_mv` | Battery voltage | mV | voltage |
| `batt_current_ma` | Battery current (+ charging) | mA | current |
| `load_mv` | Load voltage | mV | voltage |
| `load_current_ma` | Load current | mA | current |
| `charger_input_mv` | Charger input voltage (source not identified) | mV | voltage |
| `solar_mv` | Solar input voltage | mV | voltage |
| `solar_current_ma` | Solar input current | mA | current |
| `usb_mv` | USB-C input voltage | mV | voltage |
| `usb_current_ma` | USB-C input current | mA | current |

They reach `/v1/observations`, `/v1/observations/latest`, `/v1/history`, the CSV export, the
`…/weather` MQTT topic and Home Assistant discovery (diagnostic category) like every catalog field.

### 10.2 Health report

- `ws0/protocol.lit.md` provides `pack_diag`, `unpack_diag` and `diag_problems` (section 6.1); no
  caller depends on tuple order any more (`service.py`, `simulator.py`, every test).
- `receive_diagnostic` stores every key of section 6.1 with its none code mapped to `null`, and
  applies the canonical rules of section 6.1 (warning, charger keys `null`). The keys reach
  `/v1/diagnostics`, `/v1/status` `node_diagnostics`, the SSE `diagnostic` event and the
  `…/diagnostics` MQTT topic.
- **Names never overlap.** The health keys and `fields.MEASURED` are disjoint (a test checks it), so
  one name has one meaning in the API, the dashboard and Home Assistant.
- **Home Assistant:** the power keys get discovery entities on the diagnostics topic (category
  diagnostic, `value_template` on the key, available while the gateway is online, the newest report
  is fresh and the key is not `null`). *Amended 2026-10-29:* "fresh" is the retained topic
  `…/diagnostics/availability`, which the gateway sets `offline` once the newest report is
  `HEALTH_MAX_AGE_S` = 1,900 s old (two 15-minute periods plus slack, the dashboard's "overdue" limit),
  so a node that stops sending does not leave its SOC and charger state live in Home Assistant.
  Entities are advertised only for keys the build measures: a key the report lists in
  `power_not_measured` (section 6.1) gets none, so phase A creates 8 power entities, not 15; a fitted
  key whose source fails keeps its entity, unavailable. Their unique ID and config topic use their own namespace: `unique_id =
  <station>_diag_<key>`, config topic `homeassistant/<component>/<station>_diag_<key>/config`, so they
  can never overwrite an observation entity's `<station>_<field>`. Entities: `battery_soc_pct`
  (battery), `battery_soc_rate_pct_h` (%/h), `charger_charging` (binary, battery_charging),
  `charger_input_power_ok` (binary, power), `charger_fault` (binary, problem), `power_monitor_temp_c`,
  `charger_temp_c`, `pack_temp_c` (temperature), `mcu_supply_mv`, `charger_reported_input_mv`,
  `charger_reported_battery_mv` (voltage), `charger_reported_input_ma`, `charger_reported_battery_ma`
  (current), `charger_stage`, `charger_active_input` (enum sensors). A test checks that no discovery
  config topic is generated twice. The station counters stay in the diagnostics JSON only, like the
  existing ones.
- **History:** `diagnostic_series` keeps state changes of `charger_charging`, `charger_input_power_ok`,
  `charger_fault`, `charger_stage`, `charger_active_input` and `reset_cause` when it thins
  (`web.py` `DIAGNOSTIC_STATE`; `charger_stage` added 2026-10-29: phase C moves through precharge,
  cc, cv, topoff and terminated, and the state band must keep each step).
- **Dashboard:** a "power" chart group: per rail V and I paired, battery current signed with a zero
  line, SOC with its rate, and three state bands: the charger status (the three booleans), the
  charge stage (`charger_stage`, so each step `DIAGNOSTIC_STATE` keeps is drawn) and the active input
  (`solar`, `USB-C`, `no input`); rails absent from every recent record say "not measured in this
  build"; the Node health table adds the new keys, and older reports without them show "—". A `null`
  stage or input band follows the fitted byte as the table does: "not measured in this build" when
  the report lists the key in `power_not_measured` (phases A and B), "sensor fault" when it lists it
  in `power_sensor_faults`. *Amended 2026-10-29: the stage band was missing, and the input band said
  "not reported" in phase A.*
- **OpenAPI:** `components.schemas` gets `Observation` and `HealthReport`; a test checks that their
  property sets equal `fields.MEASURED` (plus the base keys) and the health keys.
- **Simulator and harness:** the demo node sends a phase A power set (battery V and signed I with a
  day/night pattern, charger input voltage, load voltage, counters) and 64-byte health reports; the
  harness sends health reports every 15 minutes and checks their storage.
- `tools/rx_faults.py` classifies version 5 and version 6 kind bytes.

## 11. Hardware source of truth

### 11.1 The breadboard model (`hardware/bench-breadboard-r0/source/wiring.toml`)

| Change | Detail |
|---|---|
| ISET net | `mcu = "PB1"`, members CHGR.ISET and N:CN8.1. *Amended 2026-10-30 (record M2, 6.1; 4.4 step 11):* two nets: ISET_CHGR (CHGR.ISET, R_ISER.1) and ISET (`mcu = "PB1"`, N:CN8.1, R_ISER.2, C_ISET, R_IPD), with R_ISER 10 kΩ 1 %, C_ISET 100 nF and R_IPD 1 MΩ to logic ground (section 9.5; D5, Clint to confirm) |
| divider | R4, R5 (10 kΩ in series) from CHGR_VBUS to the mid node; R6 (10 kΩ) to GND; net VIN_SENSE (`mcu = "PA10"`, N:CN8.3). Only R4's sense tap connects at the breakout's VBUS header pin (microamps). *Amended 2026-10-30 (record M2, 4.4 step 12):* each of R4, R5, R6 is measured before fitting and the ratio stored as `POWER_VIN_DIVIDER_PPM` (section 8.6); the bottom resistor goes to logic ground; checked in circuit within 1 % |
| charger input | the source enters through the breakout's own USB-C or DC jack, from a floating wall adapter or the panel (a cable), never through breadboard strips; solar or USB-C, never both (amended 2026-10-29, record 6.1). *Amended 2026-10-30 (record 6.1, P4, 4.1):* in phase A (step 1) the input is the breakout's own USB-C from a floating wall adapter (5 V, ≥ 2 A), never the Mac or a hub that shares the NUCLEO ground; the DC jack and the panel enter at step 1b (section 11.3). USB-C is never used with solar |
| INA VBUS | INA.VBUS in SYS_OUT; note: VBUS jumper to OUT, the breakout's VBUS-to-VIN+ back jumper open (cut; confirm on the board in hand). *Amended 2026-10-29 (record P5):* its own sense lead into its own position of the OUT lever connector, never through the breadboard |
| gauge | GBAT.+ on the cell-side node (CELL_POS, before the shunt) with its own sense lead, never through load-carrying ground jumpers. *Amended 2026-10-29 (record P4, P5):* GBAT.− is left unconnected (insulated); the gauge takes ground over STEMMA QT, so the one TIE stays the only conductor between the pack's STAR and logic ground. *Amended 2026-10-30 (record P5, M4):* the gauge's sense lead is the red lead of a cut #1131 board-mating half in one MAX17048 socket (the other socket empty), landing in its own CELL+ position; the node it reads is labelled "CELL+ node" in the model, the build sheet and the host tools |
| battery path | cell → INA VIN+ → VIN− → charger LIPO, and cell − → charger GND, as short heavy leads off the breadboard: a new `[[lead]]` construct (gauge, length) that the connectivity proof, build sheet, schematic and 3D view understand. *Amended 2026-10-29 (record P1–P7, D2):* the pack connects through the charger's own JST PH BATT and SYSOUT sockets and WAGO 222 lever connectors (CELL+, BATT, OUT, STAR), modelled as `[[joint]]`s and `[[lead]]`s; the model change is the record's step 1 model commit (section 17) |
| thermistor | the 10 kΩ NTC (#372) on THERM, taped to the pack. **Remove or cut the breakout's fixed 10 kΩ TS resistor first**: in parallel TS can never exceed 10 kΩ (0.75 V at 75 µA), so the cold trip (2.1 V, 28 kΩ) never fires and the hot trip (0.3 V, 4 kΩ) moves to about 35 °C (SLUS810 TS section). SLUS810 specifies a 103AT-type curve; a B = 3950 part trips at about +3.5 °C and +47 °C instead of 0 and 50 °C (D3) |
| TMR | read the Adafruit bq24074 schematic (the `source` link in wiring.toml) and record how TMR is strapped on #4755. *Done 2026-10-29:* TMR is tied to GND (X4.TMR in net GND), "timers disabled", recorded in the `wiring.toml` CHGR note and the build sheet. Confirm on the board in hand (check 10); only if a board differs, fit RTMR or start the exit-criterion charge at ≥ 3.85 V as this row first said |
| CHG/PGOOD LEDs | read the same schematic and record which net the CHG and PGOOD LED anodes connect to. On OUT the released pins sit near OUT − Vf; on VBUS they would sit near VBUS − Vf (up to about 5–6.7 V on the panel), above the pull-up limit: then the LEDs are cut off the pins and the internal pull-ups carry them |
| pack | "1S3P 6600 mAh, 3.0–4.2 V" in labels and notes |
| CN8 | `wiring.py` HEADERS gains CN8 (1 × 6, female, male-male jumpers), its label and 3D header; `NUCLEO_GAP` grows for two more flying lanes (`flying.py:36-38`). *Amended 2026-10-30 (record N1, N3, 4.2, 6.1):* HEADERS also gains CN9 (1 × 8); CHG, PGOOD, the vane and (change B) cups and rain land on the Arduino headers (CN9.7, CN9.6, CN8.2, CN9.5, CN8.4), each tied in `[nucleo]` to its morpho alias |
| firmware check | `wiring.FIRMWARE` maps ISET and VIN_SENSE to the node constants and checks benchlink's pins too; the comment regex accepts trailing text; PB1 = ADC1_IN5, PA10 = ADC1_IN6 |

Everything under `hardware/bench-breadboard-r0` is regenerated with `make.py all` (KiCad through
`tools/kicad_env.py`); nothing generated is edited by hand.

Build-sheet checks (replacing the stale "up to 5 V" and "confirm FT" text):
1. **Before power, no VBUS wire fitted:** INA VBUS to VIN+ and VBUS to VIN− read open (the back
   jumper is cut).
2. **R_ISET:** ISET to GND with the charger unpowered and the cell disconnected; the value goes to
   `power_config.h`. *Amended 2026-10-30 (record 1.4, M2):* expected near 1 kΩ (R9 behind the 1A
   jumper); it confirms `POWER_R_ISET_OHM 1000`. With the ISET network fitted, its 10 kΩ + 1 MΩ path
   in parallel lowers the reading by about 0.1 %.
3. **Shunt:** verified, not measured (record M1): the battery current against a series reference
   within 2 % + 2 mA at a steady current; a reference-derived value replaces the nominal 15,000 µΩ in
   `power_config.h` only if this fails.
4. **ISET and VIN_SENSE** read sensibly before the cell is fitted.
5. **TS:** about 0.75 V at 25 °C with input power present; about 0.375 V means the fixed resistor is
   still in parallel.
6. **CHG and PGOOD released** (charge done; input above OVP if that can be tested), on the panel at
   its highest Voc: both below min(VDD, VDDA) + 0.3 V with the pull-ups on.
7. **Battery path** during the first 10 minutes of a CC charge: the span limits of section 11.2,
   each span measured as a DMM mV drop and scaled by the INA228 current.
   *Amended 2026-10-30 (record 7.1 Q2, 4.3):* the meter is a Fluke 87V (600 mV DC range, 0.01 mV
   in high-resolution mode), so the 38 mA screen and the 1 A spans are read directly; the full
   checklist is the record's section 4.3 (C1–C23), logged as the run's preflight block.
8. **Gauge:** VCELL against a meter on the cell terminals at 1 A charge, within 10 mV.
   *Amended 2026-10-30 (record M4, step 1 exit 5):* under current the gauge reads the CELL+ node,
   so at 1 A the 10 mV limit applies to a meter across the gauge's own sense points (CELL+ clamp to
   STAR clamp); the difference gauge VCELL − meter at the pack plug is recorded and must be at most
   I × R_pack + 10 mV. At rest or at the 38 mA load, gauge VCELL is within 10 mV of the pack plug.
9. **INA VBUS = OUT, and the back jumper really open:** during a charge with the cell below 4.1 V,
   OUT (`load_mv`) reads 4.3–4.5 V and at least 100 mV above the gauge VCELL. A closed back jumper ties
   the cell to OUT and fails this check (the cell would charge towards 4.4 V, bypassing the charger's
   4.2 V regulation).
10. **Termination and TMR:** TMR reads 0 Ω to GND on the board in hand (charger unpowered), and a
    charge at the 1A jumper (section 2, criterion 4) ends with CHG off and steady, not flashing, at a
    battery current of 0.20–0.40 A.

*Amended 2026-10-29 (completeness round):* check 10 also requires the cell at 4.12 V or more when
CHG releases (section 2, criterion 4), and the build sheet adds the phase B checks B1–B6 of section
11.3: EN1 and EN2 recorded (EN2 high, EN1 low), the rail addresses and the 0x48 hold time, each rail
shunt verified like check 3, the bus pull-up, one source at a time, and a weak source with EN2 high
(`power-metering.md` section 5.4). `docs/hardware/bench-station-wiring.md` section 8.1 repeats checks
1–10 with the same pass rules.

### 11.2 Battery-path limits

*Amended 2026-10-29 (section 17, record P8): this section said "the whole loop at most 50 mV at 1 A
(about 50 mΩ, of which the shunt is 15 mΩ)". That figure cannot be met with stock JST PH pigtails
(the record's part-by-part estimate of the + span is 57 mΩ typical, 71 mΩ worst) and ignored the −
side.*

Measured during the first 10 minutes of a CC charge with the INA228 current between 0.8 and 1.0 A,
each limit scaled by that current:

| Span | From – to | Limit |
|---|---|---|
| + span | pack plug (back-probed) to the charger's header LIPO, including the 15 mΩ shunt | ≤ 75 mΩ |
| − span | the charger's header GND to pack plug − (back-probed) | ≤ 40 mΩ |
| pack-side spans | pack plug + to the CELL+ clamp; the STAR clamp to pack plug − | ≤ 28 mΩ each; their sum is R_pack |
| each JST PH mating | | ≤ 20 mΩ |
| each lever clamp-to-clamp, each screw terminal | | ≤ 5 mΩ |

A 115 mΩ loop starts CV with the cell about 0.1 V below 4.2 V and leaves it about 35 mV low at
termination (0.3 A), inside the termination acceptance of section 2, criterion 4.
`tests/test_breadboard.py` checks that no battery-path net uses a breadboard strip.

### 11.3 Four-rail metering (`docs/hardware/power-metering.md`, new)

- **Rail table:** net, monitor, address, shunt and its power rating, VBUS sense point; the sign
  conventions of section 3.1; the fill table of section 3.
- **Phase B join** (*amended 2026-10-29, section 17, record P10*): the #4755 already diode-ORs its
  two inputs (USB-C VBUS through D2 and the DC jack through D4, both SK34A Schottky, into the
  charger's IN). Those are the OR pair: the solar INA228 sits in the panel's lead ahead of a 2.1 mm
  barrel plug into the DC jack, the USB-C INA228 in an inline USB-C screw-terminal pair ahead of the
  board's own USB-C, so each monitor is upstream of the join. No extra diode, no join moved off the
  board. **Condition:** EN2 is high **and EN1 is low** on the board in hand (SJ1 and SJ2; record both
  before phase B). EN2 high because VIN-DPM acts only with EN2 low (SLUS810 section 9.3.4.1.1), and
  the EN2-low modes also cap the input at 100 or 500 mA; EN1 low because EN1 = EN2 = high is standby
  (USB suspend, no charge; SLUS810 table 7-2), and the ITERM formula in use holds only with EN1 ≠ EN2.
  EN2 high also removes the only input-voltage regulation a weak panel has: it is pulled down rather
  than held (`power-metering.md` section 5.4, R16). With EN2 low the design's earlier
  choice applies, an ideal-diode or power-mux stage of at most about 100 mV at 1.5 A off the board
  (`power-metering.md` section 5.1). `charger_input_mv` then reads the source less one Schottky drop.
  Step 1b checks the input margin and back-feed one source at a time (the record's step 1b exit).
  *Amended 2026-10-30 (record P10, R-20):* the solar INA228 sits in the lead of **one** 6 V panel:
  the panel's own 3.5 × 1.1 mm plug goes into a female 3.5 × 1.1 mm screw-terminal adapter (the
  panel lead is never cut), then the INA228, then an Adafruit #369 barrel plug into the DC jack.
  *Amended 2026-10-30 (record P10, R-20 superseded):* Clint replaced the panel's 3.5 × 1.1 mm plug
  with a barrel plug that fits the #4755's DC jack directly (5.5 × 2.1 mm inferred from Adafruit's
  #4755 page, not measured: confirm with calipers). The panel's plug now goes into an Adafruit #368
  female 2.1 mm DC jack to screw-terminal adapter, then the INA228, then the #369 into the DC jack;
  the female 3.5 × 1.1 mm adapter is dropped. The one-time plug swap is not a cut in the metered lead.
  Without metering the panel plugs straight into the DC jack.
  The OR pair is the board's own D2 and D4 (SK34A); no extra diode, no ideal-diode module.
- **USB-C sink:** the off-board USB-C input is a sink-configured receptacle with 5.1 kΩ Rd on both CC1
  and CC2, 5 V only (no PD); without Rd a USB-C source never turns VBUS on.
- **Input voltage limits** per phase (section 9.5): cold Voc ≤ about 10.2 V for the bq24074, < 16.5 V
  for PA10; higher needs a new divider ratio or a clamp.
- **Pull-ups** (*amended 2026-10-29, record 1.4*): each Adafruit STEMMA board has 10 kΩ; nine in
  parallel is about 1.11 kΩ, and a part sinking at 0.4 V carries (3.3 − 0.4) V ÷ 1.11 kΩ = 2.6 mA,
  inside the 3 mA limit. The #5832 has no pull-up cut jumper, so the extra INA boards keep theirs;
  the bus pull-up is measured idle and unpowered, pass at ≥ 0.97 kΩ. (This bullet said to cut the
  jumpers.)
- **Current:** an INA228 in continuous mode draws about 0.6 mA (verify in SBOS904), about 2.6 mA for
  four, about 60 mAh a day, about 1 % of the pack a day; continuous mode stays because the CHARGE
  accumulator needs it.

## 12. Bench tools and the bench-to-field boundary

### 12.1 What moves and what stays

| Bench knowledge | Goes to |
|---|---|
| sign convention, VCELL as battery voltage, OUT as the load rail, ISET charge current, charger input voltage, CHG/PGOOD, gauge rate, die temperature, VDDA, the health counters | node firmware, protocol, gateway (this design) |
| battery-path resistance, gauge on the cell, VBUS jumper on OUT, FT_f pull-up limit, input sag (input voltage under load is not the source's open-circuit voltage; SLUS810 VIN-DPM 4.35–4.63 V only with EN2 low, a weak source pulled down with EN2 high, R16), the safety timer | wiring docs and build-sheet checks; the `charger_input_mv` field note |
| plain LoRa at 5 s, the CSV logger, the dashboard, `sources.csv`, the solar/USB-C heuristic, the OCV-anchored counted SOC, load = OUT ÷ 100 Ω, ISET min/max, the drills | bench only |

*Amended 2026-10-29 (section 17, record M4, M6, M7):* the battery-path metric (the drop form with
its per-mode zero-current offset dV0), the VCELL step flag, the interface cross-checks (PGOOD against
the divider, CHG against ISET, ISET against the INA228 current) and the current balance (profiles A
and B) or power balance (profile C, with a measured efficiency band) are host-side bench tools in the
benchlink dashboard, not node firmware (risk R8). The path metric covers CELL+ to OUT only, not the
pack's own mating, which the VCELL step flag covers. Under current the gauge's VCELL is the CELL+
node, which differs from the pack terminal by I × R_pack (about 25–35 mV at 0.9 A); the tools label
it so. A firmware field for the path metric waits for a protocol revision (risk R14).

The benchlink logger converts the raw INA228 shunt current once (`battery_ma = −ishunt_ma`, + into
the cell). The dashboard uses it only for rows at or after a `--shunt-from` timestamp (the moment the
cell went through the shunt; mirrors `gauge_from`), and keeps ISET − load as a marked fallback for
earlier rows and for CSVs without the column. The logger's R_ISET, K and the load resistor become
command-line options with today's values as defaults. The gauge's SOC over-read while charging is
documented in `protocol.md` beside `battery_soc_pct`.

*Amended 2026-10-29 (completeness round):* benchlink applies the node's ADC clipping rule: an
interval whose PA10 or PB1 mean reaches 4080 sets `BL_F_VIN_CLIP` or `BL_F_ISET_CLIP`, and the
logger leaves `vin_v` or the `charge_*` columns empty, as the node sends INVALID or no ISET current
(section 9.5), so the drill below compares like with like. The i2cscan bench tool names and reads the
phase B rail INA228s (0x41, 0x45, 0x48; one `#rail` line each a scan), so their straps and shunts are
checked (build-sheet checks B2, B3) before the node runs profile 2. CI builds profile 2 and the mux
bus profile for the target with the analyzer, the stack bound and the blocking-wait report
(`.github/workflows/ci.yml`, "TX profile variants").

### 12.2 Acceptance drill (node against benchlink)

On one breadboard and pack: flash benchlink, log a known-state window (USB-C charging, solar
charging, discharging into the 100 Ω load); flash the node and repeat. Pass:
- battery current sign and magnitude within 2 % + 2 mA against a separate reference: a calibrated
  shunt or a DC clamp meter. A DMM in series (its 10 A range adds tens to hundreds of mΩ and recreates
  the 0.2 Ω lesson) is used only in a short steady window, never during a termination run;
- ISET within 10 %; the divider ratio and VCELL against a DMM (within 1 % and 10 mV);
- CHG/PGOOD equal; die temperature and VDDA plausible;
- during a charge with the cell below 4.1 V, `load_mv` (OUT) is 4.3–4.5 V and at least 100 mV above
  VCELL (build-sheet check 9).

The results go in a new evidence run directory (never the live one) and the release's RELEASES.md
entry.

## 13. Documents that change

| Document | Change |
|---|---|
| `docs/protocol.md`, `docs/protocol-design.md`, `docs/protocol-stack.md` | version 6, catalog v2 (sections 5.x), health report v6 and its canonical rules, sizes and airtime tables, the 96 B per-build ceiling, release procedure, "not measured" rule, field notes, H8 text removed |
| `docs/module-protocol.md` | quantities 18–24, types 8 and 9, type 5 frozen, quality 6 and its radio limit, WSMP 1.1, registry version rule, A1 = 60, P1 power bullets (always present), multi-rail rule, fill table, rule 7/G8/11.3/H8 and section 15 text, RJ45 marked v2 |
| `docs/radio-energy-policy.md`, `docs/failure-modes.md` | 1S3P pack facts, per-phase inputs, kind-4 question closed, health airtime rule, deferred energy state, new failure rows |
| `docs/firmware-budget.md`, `firmware/README.md`, `firmware/stage0-node/README.md`, `RELEASES.md` | measured budgets, power inputs, field set, release steps, sign finding |
| `docs/next-stages-plan.md`, `docs/CONTEXT-PACK.md`, `docs/H01-checklist.md`, `README.md` | phases A–C, stage order, 1S3P, four-rail goal, USB-C rule; document index rows for this spec, its plan and `power-metering.md` |
| `docs/hardware/*`, `docs/poc-shopping-list.md`, `hardware/*/README.md`, errata | official wiring, power-metering doc, pin budget, bring-up entry, parts |
| specs and plans of 2026-10-16, 10-18, 10-19, 10-21; flash-layout plan | dated amendment notes; the sixteen-stations slot table recomputed for a 96 B frame |
| `docs/superpowers/plans/2026-10-29-power-telemetry.md` | the implementation plan (the batches of this work and its wave gate) |
| `docs/openapi.json`, `docs/web-dashboard.md`, `docs/runbook-home-assistant.md`, `docs/simulation-harness.md` | schemas, power view, entities, synthetic power data |
| `tests/README.md`, `tools/README.md`, `firmware/fuzz/README.md` | new tests, counts, lengths |

## 14. Tests

| Area | Tests |
|---|---|
| Catalog | C/Python agreement for the 33 fields and EXT (34 bitmap positions); EXT rules (empty extension, reserved extension bit, extension-only record); a truly reserved field (34) rejected; current edges −32,768 and +32,766 mA valid, −32,769 and +32,767 INVALID, in C and Python; `WS_FIELDS_DEFINED` = `fields.DEFINED`; no chip names in field names |
| Frame | version 6 byte 0; 64-byte health report C ↔ Python field by field with none codes and extremes; non-canonical vectors (fitted bit 7 set, stage 7; active input 3 is canonical, `no_input`); the fitted byte 0x2F in phase A and `diag_problems`; regenerated KAT vectors |
| Fuzz | spec constants (110 B, 80 B, 0x6k), the obs oracle for the 33 fields and EXT, the full-catalog seed; `fuzz_wsmp` and `fuzz_record` oracles with types 8 and 9 and quantities 18–24 |
| Journal | default field set ≥ 1,440 records; slot from `WS_OBS_PLAIN_MAX` |
| Registry | new quantities and types locked; `type_meta` lines; type 5 still decodes; the record reference knows types 8 and 9, and type 10 is "not in the registry" |
| Bus | hub-only boot reads INA228, MAX17048 and SHT45 with no mux; `I2C_TIMING` SDADEL gives ≥ 100 ns of hold (node, i2cscan, benchlink equal); every existing test keeps `WS_I2C_MUX=1`; recovery counter counts one per recovery and saturates; four INA228 addresses distinct and outside the reserved set |
| Board ADC | sequence of four channels; VDDA from a VREFINT pair against a Python reference; ISET and VIN conversion; a partially clipped oversampled result (4085) is out of range; pin modes (PB1/PA10 analog no pull, PB8/PB10 pull-up); vane unchanged |
| Acquisition | battery current sign (a VIN+ → VIN− current is a discharge), steady ±, burst mean exact, reset mid-window, energy from VCELL, energy INVALID when VCELL is stale, OUT ≠ cell kept apart (OUT 4.40 V, cell 3.90 V), CHG flashing → fault, ISET 0 mA without PGOOD, a stalled ADC (sequence number unchanged) gives charger input MISSING and VDDA and ISET none, a sequence counted once, profile B with four rails and one absent |
| Station health | `fault.c` host test: PC 0 with no crash, boot count saturates and resets on power-on, one increment a boot |
| Modules and map | battery and rails modules; both present with every part dead (fields 11–16 INVALID, not absent); not-fitted slots absent from the record; phase matrix (charger off, charging, done; USB-C vs solar) of present, absent and INVALID; gauge present without the INA228 |
| TX machine | a decoded health report (opened with `ws0.protocol.unseal`, decoded with `unpack_diag`) with every field, none codes and saturation; TX timeout counted; diag airtime reserved at SF12; a reserve ≥ the cap leaves the live reading only |
| Gateway | storage and exposure end to end (API, CSV, MQTT, HA discovery, dashboard fixtures), HA health entities only for measured keys and offline after `HEALTH_MAX_AGE_S`, `power_not_measured`/`power_sensor_faults` (a dead gauge is a fault), `charger_stage` kept by thinning, health keys disjoint from `fields.MEASURED`, no discovery topic generated twice, OpenAPI schema property sets, rx_faults v5/v6, simulator and harness health reports, a healthy phase A record is "valid" |
| Breadboard | ISET and VIN_SENSE nets, INA.VBUS in SYS_OUT, GBAT on the cell node, no battery-path or charger-input net on a strip, divider 20k/10k, CN8 pins, lane capacity, firmware ADC pins, renders current; the lead budget inside the + and − span limits (section 11.2); the build sheet's phase B checks B1–B6 name every rail address of `power_config.h` |
| Bench tools | benchlink and its logger leave a clipped interval empty (`tests/test_benchlink.py`); i2cscan names the phase B rails at `power_config.h`'s addresses (`tests/test_i2cscan.py`); the dashboard shows an untrusted crash PC (`ffffffff`) as text, not an address (`tests/test_dashboard_js.py`) |

**Wave gate.** The work runs in waves (the plan, `docs/superpowers/plans/2026-10-29-power-telemetry.md`).
After each wave the orchestrator runs the whole host suite once (not `tools/gates.sh`) and records the
expected-red set: tests that are red only because a later batch owns their fix. Each batch's "must
pass" list holds only the tests it owns plus tests green at the previous gate; a red test in the
expected-red set that the batch does not own is not that batch's failure. The last wave's gate has an
empty expected-red set, and the Gates stage then runs `tools/gates.sh`.

## 15. Risks and open decisions

| # | Item | Status |
|---|---|---|
| D1 | The 1S3P pack is about 24.4 Wh; the PRD reserve (≥ 50.4 Wh, R03 168 h at 0.25 W = 42 Wh) is about twice the pack | **open for Clint**: a lower measured core load, a larger 1S pack for phase C, or a PRD deviation. The energy state stays NORMAL until decided. *Amended 2026-10-30 (record 7.1 Q3):* the carrier stays 1S3P; the reserve question stays open |
| D2 | Whether H01 runs on a version 6 release | **open for Clint**; recommendation: yes, so the H01 evidence names the shipping protocol. *Amended 2026-10-30:* the build-progression record's step 2 exit and the H01 checklist's preconditions require a version 6 build: precondition 5 needs `#status meter_link=ok` (only the version 6 node prints it, `tx_console.c:62`), precondition 1 needs this design's phase A exit criteria 1–4, which version 5 firmware cannot meet (it reads no power). A "no" needs a version 5 backport of the M7 probe and the phase A power reading (no plan carries one) or a change to the record's step 2 exit |
| D3 | The 1S3P cells' discharge and charge temperature limits against H03 (−35 °C), and the charge window the NTC actually sets (about +3.5 to +47 °C with a B = 3950 part, section 11.1) | open check in `next-stages-plan.md` section 7 |
| D4 | R_ISET: Clint's decision gives about 890 Ω (KISET 890 A·Ω at the 1.0 A label); the Adafruit schematic shows R9 = 1 kΩ behind the 1A jumper, so ICHG is about 0.89 A and an 890 Ω constant reads the ISET current about 12 % high (section 8.6) | **open for Clint**: keep 890 Ω until build-sheet check 2 measures the board, or take the schematic's 1 kΩ as the nominal now (`POWER_R_ISET_OHM`, `tools/benchlink_log.py`). *Amended 2026-10-30:* adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2. Nominal now `POWER_R_ISET_OHM 1000` (R9 behind the 1A jumper, record 1.4); ICHG 0.89 A typ; ISET currents logged earlier with 890 Ω read 12 % high (section 8.6). **Clint to confirm** |
| D5 | The record's ISET input network (10 kΩ series, 100 nF, 1 MΩ; gain 1 MΩ ÷ 1.01 MΩ) and measured divider ratio (record M2) change the official wiring of section 1 | **open for Clint** (section 17); until then ISET goes to PB1 directly and `POWER_VIN_DIVIDER` is the integer 3. *Amended 2026-10-30:* adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2. The ISET network: 10 kΩ 1 % at the charger, then a node with 100 nF and 1 MΩ to logic ground, into PB1 (section 9.5). The firmware gain: 1 MΩ ÷ 1.01 MΩ, times a per-board fit (a CC charge above 200 mA, load off). `power_config.h`: `POWER_R_ISET_OHM 1000`, `POWER_ISET_GAIN_PPM 990099` (nominal until fitted), `POWER_VIN_DIVIDER_PPM 3000000` (nominal until the three divider resistors are measured; checked in circuit within 1 %). **Clint to confirm** |
| R1 | Health reports are not journaled | accepted (section 6.4) |
| R2 | The station is at WSMP-P8 (8 modules, 24 channels) and 1 B under A1 | any new module needs P8/A1 revised in sub-project 7 |
| R3 | CONSERVE at SF12 exceeds the 2 s cap by 272 ms (274 ms with firmware rounding) once per health report: every 15 minutes plus after each link-state change | documented exception (section 6.4) |
| R4 | ISET is ±10 % (monitor ratio) plus R_ISET, the divider ±2 % with 1 % resistors, the shunt nominal until measured | build-sheet measurements; constants in `power_config.h` |
| R5 | CHG flashing is detected by edges; a missed EXTI or a slow flash could miss a fault | host test. With TMR at GND the bq24074 cannot flash CHG (section 6.3), so a phase A fault cannot be provoked on the #4755 without changing TMR; the host test is the check |
| R6 | A field build with more than 80 B of fields does not compile | the rule is deliberate; more pages or SPI NOR is the later answer |
| R7 | Brown-out resets read as power-on | known limitation (section 9.8) |
| R8 | Wiring plausibility checks (gauge on OUT, VBUS jumper on the wrong net, early termination) are not in firmware | the build-sheet checks and the acceptance drill cover them; firmware checks are deferred |
| R9 | The gateway's 180 s freshness is shorter than CONSERVE's 300 s interval | deferred with the energy state (NORMAL in this phase) |
| R10 | "Not fitted" reaches the radio as "missing" in a WSMP reading (section 8.3) | **sub-project 7 requirement**: a set-level not-fitted marker before WSMP readings travel |
| R11 | The bq24074's default safety timer (4–6 h) is shorter than a 1 A charge of 6.6 Ah from empty; the 2026-10-28 "early end" may have been a timer fault rather than a termination | **closed 2026-10-29**: TMR is tied to GND on the #4755 (timers disabled), so the early end was the battery path (record P9); confirm TMR on the board in hand (build-sheet check 10) |
| R12 | An INA228 rail measures ±5.24 A at 10 µA a count | enough for phases A and B; a larger rail raises `current_lsb_ua` (section 9.4) |
| R13 | A 96 B frame (the per-build ceiling) overruns the sixteen-stations slots sized for 94 B at SF8 and SF10 | the slot table is recomputed for 96 B in its dated amendment |
| R14 | The battery-path metric and VCELL step flag (section 12.1, record M6) are host-side only; a node in the field cannot report a degrading battery path | a health field (path mΩ with its ΔI and a validity bit, the balance residual, the step count) under a later protocol revision, by the carrier (record S5) |
| R16 | With EN2 high (the mode phase B's D2/D4 join needs, and the expected phase A strap) VIN-DPM does not act, so a panel that cannot supply the charge current is pulled down towards the cell voltage; at low sun the input can fall under VBAT + VIN(DT) and the charger can cycle PGOOD and CHG (analysis, `power-metering.md` section 5.4) | accepted for phases A and B (no rating is exceeded; status churn only), pending the bench check of `power-metering.md` section 5.4 with step 1b; if not accepted, the fallback join with input-voltage regulation, or phase C |
| R15 | The I2C hold time for the SDA-strapped USB-C INA228 (0x48) rests on SDADEL = 2 (146 ns ≥ 100 ns), not yet measured on the bus | scope SDA against SCL on the first phase B bus; an SCL strap (0x43) is the fallback, a `power_config.h` change |

## 16. Out of scope

- Gateway analysis and alerts (two source rails with current, early termination, SOC trends).
- Energy-state thresholds and the CONSERVE/CRITICAL transitions (section 9.9, D1).
- The BQ25798 driver (phase C), the phase B and C hardware builds, and their parts orders.
- WSMP on the radio (sub-project 7), WSMP health-class channels, the gateway's WSMP entity mapping,
  a registry flag for HA entity categories.
- Rail energy counters other than the battery's, window minimum and maximum of currents (kinds 3
  and 4 stay unused), derived rail power.
- Firmware wiring-plausibility checks (R8), brown-out detection (R7).
- The enclosure's CAD geometry and regenerated parts (`hardware/poc-enclosure-r1`): its README
  records the requirements (solar and USB-C entries, the charger and monitors next to the battery
  cradle with a maximum lead length, slots for four INA228s); the geometry change needs a CadQuery
  session.

## 17. Reconciliation with the build-progression record (2026-10-29)

The build-progression decision record
([`2026-10-29-build-progression-decisions.md`](2026-10-29-build-progression-decisions.md)) was written
the same day by a review of the bench work. Its section 6.5 lists amendments this design must
receive. This section settles every record row that touches this design. **Adopted** rows are in
the text above as dated amendments. **Deferred** rows wait for Clint or for the record's own work
package (its "model commit" and steps 1 and 1b); the firmware and documents stay as this design
says until then. **Rejected** rows conflict with a decision in section 1. Clint's decisions
(section 1) are not reopened by the record: where the two disagree, section 1 holds and the row is
deferred to Clint.

| Record row | Subject | Status | Where, or why |
|---|---|---|---|
| 1.4 | R_ISET = 1 kΩ (R9) | *2026-10-29:* **deferred to Clint**. *Amended 2026-10-30:* adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2; Clint to confirm (D4) | section 1 gives about 890 Ω; the constant stays until build-sheet check 2 measures the board (section 8.6, D4). *2026-10-30:* sections 1, 8.6 and D4: `POWER_R_ISET_OHM 1000`, ICHG 0.89 A typ, earlier ISET currents 12 % high |
| 1.4, P9 | TMR tied to GND, timers disabled; ITERM 0.30 A; the termination acceptance | adopted | section 2 criterion 4, 6.3, 11.1 (TMR row, check 10), R5, R11 closed |
| 1.4, M1 | shunt 15 mΩ 1 % 2 W; verified against a series reference, not measured | adopted | section 8.6, check 3 |
| 1.4 | the #5832 has no pull-up cut jumper; keep and measure | adopted | sections 9.2, 11.3; `power-metering.md` section 7 |
| 1.4 | 0x48 leaves ADDR1's pull-down on SDA | adopted | section 9.2 |
| 1.4 | CHG = D6 (CN9.7), PGOOD = D5 (CN9.6) | adopted (aliases of the same pins) | section 1, "Official wiring" |
| 1.4, P10 | the board's D2/D4 are the phase B OR pair | adopted, on condition EN2 is high and EN1 is low (the record's "expected EN2 = 1, EN1 = 0") | section 11.3; `power-metering.md` section 5.1 |
| 1.4 | VIN-DPM acts only with EN2 low | adopted; its consequence for a weak panel with EN2 high is R16 | section 5.2 field note, 11.3, R16; `power-metering.md` section 5.4 |
| P1–P7, D1–D7 | force path off the breadboard (JST PH sockets, WAGO 222, STAR, TIE), sense leads, joints and leads in the model, checks, two regeneration tiers, preflight | adopted in this design's text (section 11.1 rows); **the model change is deferred** to the record's step 1 model commit | `wiring.toml` is not changed by this design beyond section 11.1's first rows |
| P5, M4 | battery INA228 VBUS lead to the OUT connector (phase A) and to CELL+ from step 1b; "CELL+ node" label | adopted for the wiring and the host tools | sections 2 (phase B row), 9.3, 11.1, 12.1; the node firmware does not read that VBUS in profile B (`power_config.h`) |
| M4 | the battery INA228 VBUS becomes the cell voltage of record from step 1b, the gauge a cross-check | **rejected for the wire format** | field 11 stays the gauge VCELL in every phase (section 3.2): Clint's decision 1 puts the gauge on the cell; one sensor for one field across phases keeps field 11's series comparable (decision 4, source-agnostic slots); the INA228 VBUS stays a host-side cross-check |
| P8 | battery-path limits (+ 75, − 40, pack-side 28 mΩ each, PH 20, clamps 5) | adopted | section 11.2, check 7 |
| M2 | ISET through 10 kΩ with 100 nF and 1 MΩ at PB1, gain 1 MΩ ÷ 1.01 MΩ × a fit, R_ISET 1000 Ω; divider ratio measured and stored | *2026-10-29:* **deferred to Clint**. *Amended 2026-10-30:* adopted with change A, read by this workflow from record 7.1 P3 "change A as written" (record 4.4 steps 11–12 fit the ISET network and store the measured divider); R_ISET confirmed by build-sheet check 2; Clint to confirm (D5) | it changes the official wiring of section 1 (ISET straight to PB1); D5. When adopted: `power_config.h` gains the gain term and a fractional divider ratio, `board_inputs.c` and benchlink follow, `wiring.toml` adds R_ISER, C_ISET, R_IPD. *2026-10-30:* sections 1 ("Official wiring"), 8.6, 9.5, 11.1 (ISET net, divider) and D5 carry the network, the gain (`POWER_ISET_GAIN_PPM 990099`, nominal until fitted) and the divider (`POWER_VIN_DIVIDER_PPM 3000000`, nominal until measured; checked in circuit within 1 %) |
| M3 | ADC reference unchanged (VREFINT) | adopted (unchanged) | section 9.5 |
| M5, M6, M7 (host part) | preflight checklist; path metric with dV0; VCELL step flag; interface cross-checks; current balance (A, B) and power balance (C) | adopted as host-side bench tools | section 12.1, R8, R14; the tools themselves are the record's work package (record 6.4) |
| M7 (node part) | counter link probe on PB5/PB4 in node firmware | **deferred** (not this design's work). *Amended 2026-10-30:* scheduled before the step 2 H01 run | not power telemetry; it follows the pin remap N2 and is scheduled before the step 2 H01 run (record S1). *2026-10-30:* it is a precondition of the step 2 H01 run (record step 2 exit criteria, M7); its bench status field is named `meter_link=` (record M7), apart from the radio `link=` the TX console already prints (`tx_console.c:62`); no protocol change |
| N1, N4 | the MCU pin contract; pull-up limit VDD + 0.3 V | adopted (unchanged) | sections 1, 9.5 |
| N2 | cups PC0 → PB5, rain PB5 → PB4 | *2026-10-29:* **deferred (pending)**. *Amended 2026-10-30:* **approved by Clint** (record 7.1); implemented at step 1 change B | step 1 change B, after change A passes (record section 3). `board_inputs.c` keeps PC0 and PB5 until that firmware change, which also moves `wiring.toml`, the READMEs and `tests/test_board_inputs.py` together. The power pins (PB1, PA10, PB8, PB10) do not move. *2026-10-30:* change B (record 4.5) moves the firmware (`CUPS_PIN` PB5, LPTIM1_IN1 on AF1; `RAIN_PIN` PB4, EXTI4), `wiring.toml`, the READMEs and the tests in one commit |
| N8 | at the BQ25798: PB1, PA10, PB10 released; PB8 = /INT; /CE strapped | adopted | section 2 (phase C row); `next-stages-plan.md`, `bench-station-wiring.md` |
| N3, N5–N7, H1–H9 | NUCLEO connection method, mux RESET, shield, carrier, hygiene | not part of this design | the record and its cascade |
| S1–S5 | build steps 1, 1b, 2, 2c, 3, 4, 5 | adopted as the mapping of phases to steps | phase A = steps 1 and 2 (H01 runs on step 2); phase B = step 1b (after H01 by default, record Q8); phase C = steps 2c onward. *Amended 2026-10-30 (record 7.1 Q8):* order decided 2026-10-30, H01 first: 1 → 2 (H01) → 1b → 2c → 3 → 4 → 5 |
| 6.5 | "section 1 and 2: USB-C never with solar, also in tests (step 1b exit e)" | adopted | sections 1, 3.2 already state it; step 1b's exit tests one source at a time |

*Amended 2026-10-30 (record 7.1):* Clint answered the record's survey on 2026-10-30. The rows above
carry the effect as dated amendments: N2 approved; the build order decided, H01 first (Q8); the
carrier stays 1S3P (Q3, D1); INA228 module preparation allowed (Q1, section 9.2). R_ISET 1 kΩ and the
M2 ISET network and measured divider are adopted with change A, read by this workflow from record
7.1 P3 "change A as written"; no survey question asked about D4 or D5, so both stay "Clint to confirm"
in section 15. No protocol text, field, size or wire format changes with these amendments.

The record's own status line ("Not implemented") stays true for its bench, model and tool work.
Its section 8 points back here for the rows above. *Amended 2026-10-30:* no longer true: the record's
model, checks, tools and tests are implemented on `feat/power-telemetry`, uncommitted and pending the
gates (record status line and section 8's last row); its bench work (record sections 3 and 4) is not
done.
