# Circuit review

- Project: weather-station-2026, Stage 0 bench test bed
- Revision: `hardware/chicago-test-hardware-r0` (commit 7e5a1c0), firmware release a07f498273f7
- Status: `USER_REVIEW` (F6 open: whether to order the passive PCB)
- Reviewed 2026-10-13. Review only; no design files changed.
- Electrical source of truth: `source/build_schematic.py` (generates `pcb/sensor-interface.kicad_sch`); PCB from `source/build_pcb.py`
- Reviewed evidence: generator part/net table, exported `validation/schematic-netlist.xml`, `validation/electrical.json`, `validation/pcb-drc.txt` (KiCad 7.0.11 run on another machine, 2026-10-08), `manufacturing/BOM.csv`, `docs/build-and-order.md`, `docs/schematic.png`, firmware `App/sensor.c`/`sensor.h`, `docs/protocol-stack.md`, `docs/hardware/nucleo-wl55jc-bringup.md`, Adafruit product pages 5665 and 6174 (fetched 2026-10-13). KiCad is not installed on this machine, so DRC/netlist were **not re-run**.

## Operating principle

The test bed is two purchased NUCLEO-WL55JC1 boards (TX node, RX bridge) plus one Adafruit SHT45 breakout on the TX board's I2C2. The only custom hardware is a passive 50 x 35 mm "sensor interface" PCB that sits between the Nucleo and the breakout: it passes 3.3 V, GND, SDA and SCL straight through, with a removable jumper in the sensor's 3.3 V feed (for a series ammeter) and four probe pads. It has no active parts and no firmware.

## Functional blocks and component roles

| Ref | Part | Role |
|---|---|---|
| J1 | Samtec TSW-104-07-G-S, 1x4 2.54 mm | Host side: 3V3_IN, GND, SDA, SCL from Nucleo CN6.4, CN6.6, CN5.9, CN5.10 |
| J2 | Samtec TSW-104-07-G-S, 1x4 2.54 mm | Sensor side: 3V3_SENSOR, GND, SDA, SCL to breakout via Adafruit 4397 JST-SH-to-socket cable |
| JP1 + shunt | TSW-102-07-G-S + SNT-100-BK-G | Links 3V3_IN to 3V3_SENSOR; remove shunt and insert ammeter to measure sensor-side current |
| TP1–TP4 | Bare copper pads | Probe points: 3V3_SENSOR, GND, SDA, SCL |
| H1–H4 | 3.2 mm NPTH | M3 mounting to printed base |

Netlist (5 nets) matches the generator exactly: 3V3_IN {J1.1, JP1.1}; 3V3_SENSOR {J2.1, JP1.2, TP1}; GND {J1.2, J2.2, TP2}; SDA {J1.3, J2.3, TP3}; SCL {J1.4, J2.4, TP4}.

## Power tree and budget

USB → Nucleo ST-LINK/regulator → Nucleo 3V3 (CN6.4) → J1.1 → JP1 → J2.1 → breakout VIN → breakout LDO → SHT45. The sensor draws well under 1 mA average at one reading per minute; the Nucleo 3V3 rail has ample margin. `[TBD-MEASURE]` actual breakout current via JP1.

## Voltage domains and interfaces

Single 3.3 V domain. I2C2: PA11 = SDA (AF4), PA12 = SCL (AF4), open-drain, MCU pull-ups off, 100 kHz, analog filter on (`sensor.c`). Pull-ups are on the breakout (values not published on the product page). SHT45 address 0x44. Pin mapping agrees across firmware (`sensor.h`), `protocol-stack.md`, bring-up log (checked against UM2592 Rev 4 Table 17), the hardware build guide and the context pack.

## Operating states, reset, and ownership

The MCU is the only I2C master. Firmware de-initialises and re-clocks the bus (stuck-bus recovery) after any failed transfer; a failed or CRC-bad read is reported as `sensor_fault` with no value, never as a plausible number (unit-tested in `tests/test_stage0.py`, including the Sensirion CRC-8 vector 0xBEEF → 0x92). Partial power: with JP1 open, the SDA/SCL pull-ups can back-feed the unpowered breakout; documented in the build guide.

## Timing and signal integrity

100 kHz standard mode, short unbuffered leads (build guide target ≤ 25 cm host-to-sensor). Adequate for the bench. Not suitable for a remote outdoor sensor run.

## Protection, thermal, and mechanics

No ESD or series protection on the I2C lines; acceptable for indoor bench use only. Build guide keeps the sensor away from the warm MCU/regulator. Printed cradles, base and tray are untested for fit.

## Layout handoff constraints

- `[SPEC]` 2 layers, 1.6 mm FR-4, 0.50 mm traces, 0.25 mm clearance; no impedance control. Already laid out; DRC 0 violations (not re-run here).
- `[TARGET]` I2C total lead length ≤ 25 cm.

## Findings

| ID | Severity | Evidence | Consequence | Action | Gate | Status |
|---|---|---|---|---|---|---|
| F1 | Minor | Hardware BOM/build guide name Adafruit **5665**; firmware, `protocol-stack.md` and context pack name **6174**. Adafruit pages: 6174 is the same SHT45 breakout plus a PTFE membrane (IP67, particle/liquid protection), $13.50 vs $12.50. | Electrically interchangeable; risk is only documentation drift. 6174 is the better long-term choice outdoors. | None. 6174 is the part of record (`firmware/README.md`: "superseding the starter's older 5665 suggestion"); Clint's order delivered 2026-10-13 is 6174. The R0 package stays unedited because `SHA256SUMS.txt` locks it. | Sourcing | Closed |
| F2 | Information | Context pack §6.2 says "Firmware sensor driver: TODO". `App/sensor.c` already implements the I2C2 driver with stuck-bus recovery, and CRC/fault handling is unit-tested. It is shipped in a07f498 (current readings are `sensor_fault` because nothing is connected). | Planned work is smaller than the pack implies: tomorrow is wire up + hardware verification, not driver writing. | Correct the context pack. | — | Open |
| F3 | Minor | Breakout has its own LDO, level shifters and pull-ups (Adafruit page). | Current through JP1 is the whole breakout, not the SHT45 chip; overstates sensor current for the Stage 1 energy budget. | Record measurements as "breakout current"; budget the bare SHT45 from its datasheet until the Stage 1 board exists. | Stage 1 power | Open |
| F4 | Information | Build guide procedure says disable I2C and set pins high-impedance before removing sensor power; firmware has no console command for that. | The pack's "unplug test" is a hot unplug with I2C active. Low risk at 3.3 V through the breakout's level shifters, and it is exactly the fault the driver should survive. | None needed for Stage 0; note in bring-up log when performed. | — | Accepted |
| F5 | Information | No ERC exists (KiCad 7 CLI lacked it); netlist comparison stands in. | For a 5-net passive board with no driven outputs, netlist comparison covers what ERC would catch. | None. Re-run DRC/netlist if the board is regenerated. | — | Accepted |
| F6 | Information | The custom PCB has not been ordered (build guide). It only passes four wires through. | Stage 0 does not need it: the breakout can connect directly to the Nucleo with the 4397 cable plus male-to-female jumpers, keeping the same pin table. Its value is the ammeter jumper and probe pads. | Clint: decide whether to order (purchase needs his OK). | — | Open |

No critical or major findings.

## Approved design decisions and waivers

- Indoor bench only; no ESD protection, unbuffered I2C (build guide).
- G7 part B (true USB power-cut testing) deferred by Clint.

## Verification and unresolved evidence

- Verified here by reading: generator ↔ netlist agreement; firmware ↔ docs pin map agreement; breakout identity and features (Adafruit pages).
- Not verified here: DRC re-run, physical fit, continuity checks, real sensor read on hardware (sensor arrives ~2026-10-14), breakout pull-up values `[TBD-MEASURE]`.
