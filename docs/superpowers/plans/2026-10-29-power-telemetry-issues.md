# Power Telemetry Issue Catalog

This catalog lists every known issue caused by the power decision of 2026-10-29: the 1S3P pack (three
2200 mAh cells, 6600 mAh) on the Adafruit bq24074 charger in phase A, the proven bench breadboard wiring
becoming the official design (ISET on PB1, the charger input divider on PA10, CHG on PB10, PGOOD on PB8,
the INA228 at 0x40 with its shunt in the battery path and VBUS on OUT, the MAX17048 at 0x36 on the cell),
four metered rails (battery, solar, USB-C, load) as the final goal, the BQ25798 in a later phase, and a
source-agnostic place in the wire protocol for all power data now. The decision cascades through the
protocol, the WSMP registry, the node firmware, the gateway, the tests, the breadboard model, the bench
tools and the documents and plans.

- Design: [`../specs/2026-10-29-power-telemetry-design.md`](../specs/2026-10-29-power-telemetry-design.md)
- Implementation plan (batches and wave gates): [`2026-10-29-power-telemetry.md`](2026-10-29-power-telemetry.md)

Batches `B01`-`B34` are the plan's work batches. Batches `X1`-`X4` are completeness passes that searched
every layer for drift left after the batches and fixed what they found (issues `PT-X01`-`PT-X45`).

## Summary

199 issues: 197 resolved, 2 unresolved.

| Layer | Resolved | Unresolved | Total |
|---|---:|---:|---:|
| protocol | 12 | 0 | 12 |
| wsmp | 10 | 0 | 10 |
| firmware | 36 | 1 | 37 |
| gateway | 13 | 0 | 13 |
| tests | 20 | 0 | 20 |
| hardware | 27 | 1 | 28 |
| bench | 5 | 0 | 5 |
| docs | 7 | 0 | 7 |
| plans | 22 | 0 | 22 |
| completeness | 45 | 0 | 45 |
| **all** | **197** | **2** | **199** |

| Severity | Resolved | Unresolved | Total |
|---|---:|---:|---:|
| blocker | 22 | 0 | 22 |
| major | 95 | 2 | 97 |
| minor | 80 | 0 | 80 |

## Issues

State `resolved` means the batch named in the note fixed it. An unresolved row's note points to the
[unresolved issues](#unresolved-issues) section.

| ID | Layer | Severity | Title | Batch | State | Note |
|---|---|---|---|---|---|---|
| PT-001 | protocol | blocker | The observation catalog has no room for the four rails (6 free bits for 7 new values) | B01 | resolved | B01 |
| PT-002 | protocol | major | WS_FIELDS_DEFINED is undefined behaviour at 32 fields and C/Python could drift | B01 | resolved | B01 |
| PT-003 | protocol | major | Battery current field 12 range (+-3.27 A at 0.1 mA) is too narrow for the BQ25798 phase | B01 | resolved | B01 |
| PT-004 | protocol | blocker | The journal's 24 h floor is computed from every catalog field and fails above 80 B | B01 | resolved | B01 |
| PT-005 | tests | minor | test_obs's 'reserved bitmap bit' case uses bit 21, a defined field | B01 | resolved | B01 |
| PT-006 | protocol | major | Field 11 and fields 13-16 are defined as battery values but v5 builds fill them from OUT | B01 | resolved | B01 |
| PT-007 | protocol | major | Fields 17 (SOC) and 18 (raw bq24074 pins) are chip-specific and on the wrong cadence | B01 | resolved | B01 |
| PT-008 | gateway | major | New rail fields need source-agnostic names, units, HA classes, labels and diagnostic category | B01 | resolved | B01 |
| PT-009 | wsmp | blocker | The WSMP registry has no quantities for the load, charger-input, solar and USB-C rails | B02 | resolved | B02 |
| PT-010 | wsmp | blocker | Four rails of the same quantity would collide under WSMP-H1/H6 and exceed one 8-channel module | B02 | resolved | B02 |
| PT-011 | wsmp | major | Changing type 5 would strand stored descriptor sets; type names bind chips | B02 | resolved | B02 |
| PT-012 | wsmp | minor | The lock does not record report class, role or states, and the registry version has no bump rule | B02 | resolved | B02 |
| PT-013 | wsmp | major | WSMP has no 'not fitted' quality, so a slot a phase cannot fill looks like a failure | B03 | resolved | B03 |
| PT-014 | wsmp | major | The minute value budget (58 B) cannot hold 24 channels; the station reaches WSMP-P8 | B03 | resolved | B03 |
| PT-015 | firmware | major | INA228/MAX17048 and ADC conversions exist only in the bench tools and would be copied | B04 | unresolved | Open: see [unresolved issues](#unresolved-issues) |
| PT-016 | firmware | major | The node does not read ISET (PB1/ADC1_IN5) or the charger input divider (PA10/ADC1_IN6) | B05 | resolved | B05 |
| PT-017 | firmware | major | VDDA is hard-coded at 3300 mV; no VREFINT measurement | B05 | resolved | B05 |
| PT-018 | firmware | major | The CHG 2 Hz fault flash cannot be seen by one sample per latch | B05 | resolved | B05 |
| PT-019 | tests | minor | Nothing stops debug outputs from driving PA10, PA11, PA12 or PB2 | B05 | resolved | B05 |
| PT-020 | firmware | minor | The CHG/PGOOD internal pull-up constraint is undocumented in code and was mis-cited | B05 | resolved | B05 |
| PT-021 | tests | major | Host harnesses have no seams for the ADC values or the CHG edge count | B05 | resolved | B05 |
| PT-022 | bench | minor | The bench dashboard ignores the measured shunt current, has no shunt-in-path marker, and the sign conversion lives nowhere | B06 | resolved | B06 |
| PT-023 | protocol | blocker | The 32-byte health report has no room for the slow power and diagnostic items | B07 | resolved | B07 |
| PT-024 | protocol | major | A format change under version 5 would make a stale gateway NACK and the node abandon records | B07 | resolved | B07 |
| PT-025 | gateway | major | Every health-report producer and consumer depends on DIAG tuple order | B07 | resolved | B07 |
| PT-026 | protocol | minor | No slot for several INA228 die temperatures, pack temperature or the BQ25798 cross-check values | B07 | resolved | B07 |
| PT-027 | tests | major | Host device models lack the registers, instances and shunt physics the new acquisition reads | B08 | resolved | B08 |
| PT-028 | hardware | major | wiring.py cannot place CN8 and the flying-wire lanes overflow with two more jumpers | B09 | resolved | B09 |
| PT-029 | hardware | major | check_firmware cannot check ADC pins, misreads trailing comments and never checks benchlink | B09 | resolved | B09 |
| PT-030 | hardware | major | The model has no construct for short heavy leads off the breadboard | B09 | unresolved | Open: see [unresolved issues](#unresolved-issues) |
| PT-031 | firmware | blocker | The node bus requires a TCA9548A; the official STEMMA QT hub wiring reads nothing | B10 | resolved | B10 |
| PT-032 | firmware | major | No I2C bus-recovery counter for the health report | B10 | resolved | B10 |
| PT-033 | firmware | major | Only one INA228 client exists and the host model maps 0x44/0x46/0x47 behind mux channels | B10 | resolved | B10 |
| PT-034 | tests | major | Fuzz spec constants, the obs oracle and the seeds are sized for 26 fields, 78 B and version 5 | B11 | resolved | B11 |
| PT-035 | tests | minor | RX tests and rx_faults hard-code version-5 byte-0 values | B12 | resolved | B12 |
| PT-036 | tests | minor | test_counter_regression packs the health report positionally | B12 | resolved | B12 |
| PT-037 | gateway | blocker | The gateway decodes the health report positionally and has no keys for the new items | B13 | resolved | B13 |
| PT-038 | gateway | major | The simulator packs DIAG positionally and sends no power fields or new health items | B13 | resolved | B13 |
| PT-039 | gateway | major | Home Assistant gets no entities for SOC, charger status and the other power health keys | B13 | resolved | B13 |
| PT-040 | gateway | major | Record quality for 'not measured' vs 'invalid' is unpinned | B13 | resolved | B13 |
| PT-041 | hardware | blocker | wiring.toml lacks the official ISET, VBUS-divider and INA VBUS-to-OUT connections | B14 | resolved | B14 |
| PT-042 | hardware | blocker | The modelled battery path runs through breadboard strips (the 0.2 ohm path) | B14 | resolved | B14 |
| PT-043 | hardware | major | The fuel gauge senses the charger side of the shunt, not the cell | B14 | resolved | B14 |
| PT-044 | hardware | major | The schematic generator does not draw the divider, ISET, the input or INA VBUS to OUT | B14 | resolved | B14 |
| PT-045 | hardware | major | The charger thermistor input is unconnected although the bench wiring becomes the field design | B14 | resolved | B14 |
| PT-046 | hardware | minor | No part for the charger input source; 1S3P not named in the hardware sources | B14 | resolved | B14 |
| PT-047 | hardware | minor | Build-sheet bench checks are stale ('up to 5 V', 'confirm FT') and miss the power checks | B14 | resolved | B14 |
| PT-048 | hardware | minor | The breadboard README is stale (counts, decisions, parts) | B14 | resolved | B14 |
| PT-049 | hardware | major | Every generated breadboard artefact must be regenerated and the model tests extended | B14 | resolved | B14 |
| PT-050 | hardware | major | The wiring guide's pin table marks PB1 and PA10 'bench only' | B14 | resolved | B14 |
| PT-051 | firmware | blocker | The node counts battery discharge as charge in (INA228 sign vs the official orientation) | B15 | resolved | B15 |
| PT-052 | firmware | blocker | Battery voltage comes from the INA228 VBUS, which the official wiring puts on OUT | B15 | resolved | B15 |
| PT-053 | firmware | major | Energy counters integrate OUT x I instead of battery energy | B15 | resolved | B15 |
| PT-054 | firmware | major | The signed battery current is never produced and its minute mean needs a real time base | B15 | resolved | B15 |
| PT-055 | firmware | major | The gauge VCELL and CRATE and the INA228 die temperature are not read | B15 | resolved | B15 |
| PT-056 | firmware | major | The power driver handles one INA228 with a placeholder shunt at a hard-coded address | B15 | resolved | B15 |
| PT-057 | firmware | major | The charger FAULT state is never produced and CHG without PGOOD is hidden | B15 | resolved | B15 |
| PT-058 | bench | major | Shunt and charger calibration constants are placeholders in two copies with no home | B15 | resolved | B15 |
| PT-059 | firmware | major | ISET current and charger input voltage need VDDA scaling | B15 | resolved | B15 |
| PT-060 | tests | major | No test ties node, bench tool and logger conversions to the same reference values | B15 | resolved | B15 |
| PT-061 | firmware | minor | New power code needs WS_CHECK_FILE numbers, build lists and code-shape compliance | B15 | resolved | B15 |
| PT-062 | firmware | major | Boot count and last crash PC are not available to the health report | B16 | resolved | B16 |
| PT-063 | firmware | minor | A brown-out reset is reported as a power-on reset | B16 | resolved | B16 |
| PT-064 | gateway | major | The simulation harness never produces power fields or health reports | B17 | resolved | B17 |
| PT-065 | firmware | blocker | An absent INA228 removes the whole power module, so the gauge, pins and ADC values vanish | B18 | resolved | B18 |
| PT-066 | firmware | blocker | The power data does not fit type 5; ports, host names and tests pin the old 7-channel module | B18 | resolved | B18 |
| PT-067 | firmware | major | The health report has no path to the power values | B18 | resolved | B18 |
| PT-068 | wsmp | minor | Health-class channels are never checked against the health report (WSMP-A1) | B18 | resolved | B18 |
| PT-069 | wsmp | minor | The local serials of the power ports change with the module type | B18 | resolved | B18 |
| PT-070 | gateway | major | The dashboard has no power view and the Node health table lists only the v5 keys | B19 | resolved | B19 |
| PT-071 | gateway | major | Diagnostic thinning can drop charger state changes | B19 | resolved | B19 |
| PT-072 | tests | major | No test covers the new fields and health keys through the API, CSV and history | B19 | resolved | B19 |
| PT-073 | firmware | major | The interim catalog map sends no battery current, no rails, and keeps fields 17/18 | B20 | resolved | B20 |
| PT-074 | firmware | major | The node field set must become the 77-byte version-6 set | B20 | resolved | B20 |
| PT-075 | tests | major | No test pins what each phase puts in each slot | B20 | resolved | B20 |
| PT-076 | firmware | major | Phase A cannot tell solar from USB-C; the firmware needs a fixed rule | B20 | resolved | B20 |
| PT-077 | tests | minor | The descriptor-set fuzz seed describes the old module layout | B20 | resolved | B20 |
| PT-078 | firmware | blocker | send_diag fills only the 32-byte report | B21 | resolved | B21 |
| PT-079 | firmware | major | No total radio TX-timeout counter | B21 | resolved | B21 |
| PT-080 | tests | major | No TX-machine test decodes the health report the firmware sends | B21 | resolved | B21 |
| PT-081 | gateway | major | OpenAPI has no schemas for observations or health reports | B22 | resolved | B22 |
| PT-082 | gateway | major | Gateway docs do not describe the power entities, rail attribution per phase or field 11's meaning | B22 | resolved | B22 |
| PT-083 | gateway | minor | Freshness (180 s) is shorter than the CONSERVE interval (300 s) | B22 | resolved | B22 |
| PT-084 | firmware | major | The health report's airtime is not in the minute's budget | B23 | resolved | B23 |
| PT-085 | firmware | major | Energy state is fixed at NORMAL although the node now measures its battery | B23 | resolved | B23 |
| PT-086 | tests | minor | Larger frames could change the airtime-derived backlog pinned in the tests | B23 | resolved | B23 |
| PT-087 | docs | major | protocol.md and protocol-design.md describe version 5, catalog v1 and the 32-byte health report | B24 | resolved | B24 |
| PT-088 | docs | major | No written policy for old data across the format change | B24 | resolved | B24 |
| PT-089 | docs | minor | protocol-stack.md sizes, byte-0 values, catalog and health tables are version 5 | B25 | resolved | B25 |
| PT-090 | docs | major | module-protocol.md describes battery-only quantities, type 5, health-class battery data and H8 current derivation | B26 | resolved | B26 |
| PT-091 | docs | minor | module-protocol.md presents RJ45 as the module port | B26 | resolved | B26 |
| PT-092 | plans | blocker | The 1S3P pack (~24.4 Wh) is below the PRD reserve the energy policy uses (>= 50.4 Wh) | B27 | resolved | B27 |
| PT-093 | docs | major | radio-energy-policy.md inputs, kind-4 question and airtime tables are stale | B27 | resolved | B27 |
| PT-094 | docs | major | failure-modes.md has stale power context and no power-telemetry failure rows | B27 | resolved | B27 |
| PT-095 | plans | blocker | No document names the power phases (A bq24074, B four rails, C BQ25798) | B28 | resolved | B28 |
| PT-096 | plans | blocker | Stage-order text says power work waits for H01 | B28 | resolved | B28 |
| PT-097 | plans | blocker | next-stages-plan.md still plans the 4S4P Molicel pack | B28 | resolved | B28 |
| PT-098 | plans | blocker | The four-rail goal and per-phase coverage are recorded in no plan | B28 | resolved | B28 |
| PT-099 | plans | major | The USB-C role (bench and backup only, never with solar) is not recorded | B28 | resolved | B28 |
| PT-100 | plans | major | BQ25798 phase details are not re-derived for 1S, dual input, four rails and either order | B28 | resolved | B28 |
| PT-101 | plans | minor | Open checks lack the phase A calibration items | B28 | resolved | B28 |
| PT-102 | plans | major | H01 checklist does not cover the power release | B28 | resolved | B28 |
| PT-103 | plans | major | CONTEXT-PACK.md does not reflect phase A, the benchlink proof or the power steps | B28 | resolved | B28 |
| PT-104 | plans | minor | README.md power scope sentence and open-work lists are stale | B28 | resolved | B28 |
| PT-105 | hardware | major | No specification of the four-rail metering hardware | B29 | resolved | B29 |
| PT-106 | hardware | major | The wiring guide lacks the official power chain, analog notes, checklist items, pin budget and bench checks | B29 | resolved | B29 |
| PT-107 | hardware | minor | The bring-up log has no record of the proven power wiring | B29 | resolved | B29 |
| PT-108 | plans | major | The shopping list has one INA228, no address plan, 4-cell wording and missing divider parts | B29 | resolved | B29 |
| PT-109 | bench | major | No documented boundary of what moves from the bench to the field, and no acceptance drill | B30 | resolved | B30 |
| PT-110 | bench | minor | i2cscan docs and OLED describe VBUS as the cell | B30 | resolved | B30 |
| PT-111 | hardware | minor | chicago-test-hardware-r0 assumes a 4S pack | B30 | resolved | B30 |
| PT-112 | hardware | minor | poc-enclosure-r1 has no room or entries for the official power design | B30 | resolved | B30 |
| PT-113 | plans | major | Protocol version sequencing with the planned time-sync version 6 is unrecorded | B31 | resolved | B31 |
| PT-114 | plans | major | WSMP bench-station spec omits ISET/VIN, the pin limits and the bench lessons; its map and battery-channel notes are stale | B31 | resolved | B31 |
| PT-115 | plans | major | Bench breadboard spec leaves out ISET, the divider and their firmware check | B31 | resolved | B31 |
| PT-116 | wsmp | major | The ports spec has one 'battery and charger' port, one upstream INA228 and no address plan for four | B31 | resolved | B31 |
| PT-117 | plans | major | No implementation plan exists for the power telemetry work; older plans are stale | B32 | resolved | B32 |
| PT-118 | plans | major | Firmware budget lacks per-phase power estimates and the measured impact | B33 | resolved | B33 |
| PT-119 | plans | major | stage0-node README describes the old power module, field set and energy state | B33 | resolved | B33 |
| PT-120 | plans | minor | RELEASES.md has no format-change steps and no record of the sign finding | B33 | resolved | B33 |
| PT-121 | plans | minor | firmware/README.md hardware target and measurement notes predate phase A | B33 | resolved | B33 |
| PT-122 | tests | minor | Test, tool and Power of Ten docs are stale | B34 | resolved | B34 |
| PT-123 | gateway | major | Health key 'charger_input_mv' collided with observation field 28 in the API and Home Assistant | B13 | resolved | B13 |
| PT-124 | firmware | major | An absent power module would turn dead hardware into 'not measured' | B18 | resolved | B18 |
| PT-125 | protocol | major | Phase C assumed phase B's monitors and BQ25798 IBUS could not be attributed to a rail | B07 | resolved | B07 |
| PT-126 | protocol | minor | Current range stated as +-32,766 mA while the codec range is -32,768 to +32,766 | B01 | resolved | B01 |
| PT-127 | firmware | minor | Clipping rule missed partially clipped oversampled values; full scale assumed VDDA = 3.3 V | B15 | resolved | B15 |
| PT-128 | firmware | minor | Battery energy counters silently undercount when no fresh battery voltage exists | B15 | resolved | B15 |
| PT-129 | firmware | minor | Health airtime reserve must saturate; the CONSERVE exception happens once per health report | B23 | resolved | B23 |
| PT-130 | plans | minor | The per-build ceiling rises to a 96 B frame but the sixteen-stations slot table is sized for 94 B | B31 | resolved | B31 |
| PT-131 | wsmp | minor | 'Not fitted' is indistinguishable from missing on the WSMP radio quality | B26 | resolved | B26 |
| PT-132 | protocol | minor | Health report reserved bits (byte 51, stage 7, active input 3) had no decode rule | B07 | resolved | B07 |
| PT-133 | firmware | minor | Phase A charger-reported charge current was ambiguous when PGOOD is deasserted | B15 | resolved | B15 |
| PT-134 | hardware | major | The bq24074 default safety timer (4-6 h) is shorter than a 1 A charge of 6.6 Ah | B14 | resolved | B14 |
| PT-135 | hardware | major | The NTC in parallel with the breakout's fixed 10 kohm TS resistor disables the cold-charge inhibit | B14 | resolved | B14 |
| PT-136 | hardware | major | 'INA VBUS = OUT' cannot detect the INA228 VBUS-to-VIN+ back jumper still closed | B14 | resolved | B14 |
| PT-137 | hardware | major | An OR-ing diode pair would push USB-C into bq24074 VIN-DPM in phase B | B29 | resolved | B29 |
| PT-138 | hardware | minor | An off-board USB-C input needs a sink receptacle with Rd on CC1/CC2 | B29 | resolved | B29 |
| PT-139 | hardware | minor | The divider sets no input-voltage limit for PA10's absolute maximum | B29 | resolved | B29 |
| PT-140 | hardware | minor | The CHG/PGOOD LED anode net is unrecorded and the pull-up check has no worst-case condition | B14 | resolved | B14 |
| PT-141 | bench | minor | Phase A was called 'proven' although the shunt was never in the path; benchlink README puts the gauge on LIPO | B30 | resolved | B30 |
| PT-142 | firmware | minor | INA228 current range is +-5.24 A at 10 uA, not +-10.9 A | B15 | resolved | B15 |
| PT-143 | hardware | minor | ISET tolerance cited KISET instead of the monitor ratio; 890 ohm R_ISET is inferred | B14 | resolved | B14 |
| PT-144 | hardware | minor | Battery-path budget and checks under-specified (loop, connectors, shunt measurement, drill meter) | B14 | resolved | B14 |
| PT-145 | hardware | minor | The charger input part on CHGR_VBUS would carry input current through strips | B14 | resolved | B14 |
| PT-146 | tests | blocker | Switching host builds to the hub profile would break mux-dependent tests nobody owns | B10 | resolved | B10 |
| PT-147 | tests | blocker | New module types break the WSMP record tests' hand-written registry copy | B02 | resolved | B02 |
| PT-148 | tests | blocker | fuzz_wsmp and fuzz_record oracles stop at type 7 and quantity 17 | B11 | resolved | B11 |
| PT-149 | firmware | major | ws_minute_backlog's prototype lives in the hand-written ws_policy.h | B23 | resolved | B23 |
| PT-150 | tests | major | test_h01_report ingests version-5 records and goes red after B07 | B12 | resolved | B12 |
| PT-151 | tests | major | power_acq.c and power_regs.c are missing from the host build lists that B18 needs | B15 | resolved | B15 |
| PT-152 | firmware | major | The boot counter would double-count in benchlink and fault.c has no host test | B16 | resolved | B16 |
| PT-153 | plans | minor | B28's links depend on B29/B32 files and the doc indexes miss the new documents | B28 | resolved | B28 |
| PT-154 | tests | minor | Verify lists included tests that are known red or edited by a same-wave batch | B32 | resolved | B32 |
| PT-X01 | completeness | major | The build-progression decision record's required amendments to the power spec were never applied, so the two design documents still contradict each other | X1 | resolved | X1 |
| PT-X02 | completeness | minor | protocol.md and the design still describe the bq24074 TMR pin as floating and a safety-timer fault as expected, but the hardware model says TMR is tied to GND | X1 | resolved | X1 |
| PT-X03 | completeness | minor | USB-C INA228 at 0x48 is fixed in firmware while the I2C hold-time requirement for an SDA-strapped address is unresolved | X1 | resolved | X1 |
| PT-X04 | completeness | minor | docs/lora-firmware-update-study.md still claims protocol version 6 for the firmware-update kinds | X1 | resolved | X1 |
| PT-X05 | completeness | minor | docs/firmware-event-model.md is not updated: the 'How we know' table and TxTimeout row miss the power harness, the fault tests and the new counters | X1 | resolved | X1 |
| PT-X06 | completeness | minor | docs/runbook-moving-boards.md has no procedure for the version 6 format change or the journal slot-size change | X1 | resolved | X1 |
| PT-X07 | completeness | minor | Home Assistant health-report entities never go stale: a dead node's SOC and charger state stay 'available' indefinitely | X1 | resolved | X1 |
| PT-X08 | completeness | minor | History thinning keeps charger state changes but not charger_stage | X1 | resolved | X1 |
| PT-X09 | completeness | major | Home Assistant health-report entities never go stale when the node stops sending | X1 | resolved | X1 |
| PT-X10 | completeness | major | Health-report none codes mix up 'not measured in this phase' and 'fitted part failed'; the dashboard calls a dead gauge 'not measured by this build' | X1 | resolved | X1 |
| PT-X11 | completeness | minor | Phase A advertises seven Home Assistant entities that stay unavailable forever | X1 | resolved | X1 |
| PT-X12 | completeness | minor | Thinning the health history can drop charger_stage changes | X1 | resolved | X1 |
| PT-X13 | completeness | major | Two documents on this branch disagree about what PB10, PB1 and PA10 do in the BQ25798 phase | X1 | resolved | X1 |
| PT-X14 | completeness | major | The build-progression record changes the battery-voltage source and the ISET input, against the official design and firmware | X1 | resolved | X1 |
| PT-X15 | completeness | minor | firmware-event-model.md interrupt table predates the power ADC sequence and the CHG EXTI15_10 handler | X1 | resolved | X1 |
| PT-X16 | completeness | minor | The simulator sends health reports that the firmware cannot produce: reset cause 'power' with boots_since_power_up = epoch | X1 | resolved | X1 |
| PT-X17 | completeness | minor | README journal capacity is the version 5 figure, but the line describes the version 6 source | X1 | resolved | X1 |
| PT-X18 | completeness | minor | CONTEXT-PACK.md document map still describes protocol version 5 and WSMP 1.0 | X1 | resolved | X1 |
| PT-X19 | completeness | major | The battery-path amendment (P8) never reached the other documents: many still say 'the whole loop at most 50 mV at 1 A' | X2 | resolved | X2 |
| PT-X20 | completeness | major | The wiring guide's bench-check table disagrees with build-sheet checks 3, 7 and 10 | X2 | resolved | X2 |
| PT-X21 | completeness | major | The shunt constant is still described as 'measured', and it cites build-sheet 'phase B rows' that do not exist | X2 | resolved | X2 |
| PT-X22 | completeness | major | The phase B join decision (the breakout's D2/D4 with EN2 high) has not reached the shopping list or the stage plan | X2 | resolved | X2 |
| PT-X23 | completeness | major | The 'VIN-DPM acts only with EN2 low' amendment was not propagated, and losing panel regulation with EN2 high is not analysed | X2 | resolved | X2 |
| PT-X24 | completeness | minor | The 'EN2 high' condition leaves out 'EN1 low'; EN1 = EN2 = high puts the charger in standby | X2 | resolved | X2 |
| PT-X25 | completeness | minor | The 'cut the INA228 pull-up jumpers' instruction survives in two documents after the amendment removed it | X2 | resolved | X2 |
| PT-X26 | completeness | minor | protocol-stack.md still calls health-report byte 51 'Reserved. Must be 0' | X2 | resolved | X2 |
| PT-X27 | completeness | minor | The node README's '#diag sent' key list leaves out 'fitted=' | X2 | resolved | X2 |
| PT-X28 | completeness | minor | CI never builds the phase B power profile or the mux bus profile for the target | X2 | resolved | X2 |
| PT-X29 | completeness | minor | i2cscan recognises only the 0x40 INA228, so phase B monitors show as unknown | X2 | resolved | X2 |
| PT-X30 | completeness | minor | benchlink does not apply the node's ADC clipping rule, so the bench and the node disagree near full scale | X2 | resolved | X2 |
| PT-X31 | completeness | major | protocol-stack.md and the packet diagrams in three protocol documents still call health-report byte 51 'reserved, must be 0', but it is now the fitted byte | X2 | resolved | X2 |
| PT-X32 | completeness | minor | The firmware build ID does not identify the power profile or the calibration constants, although the code and the spec say it does | X2 | resolved | X2 |
| PT-X33 | completeness | minor | An untrusted crash PC (0xFFFFFFFF) is shown on the dashboard as a real program counter | X2 | resolved | X2 |
| PT-X34 | completeness | minor | bench_screen.h layout comment still shows the OLED line as 'VBUS', but the code now draws 'OUT' | X2 | resolved | X2 |
| PT-X35 | completeness | minor | #modules console line can now exceed WSMP_MODULES_LINE_MAX: adding the rails port breaks the documented worst-case bound | X3 | resolved | X3 |
| PT-X36 | completeness | minor | Power acquisition never checks the ADC sequence number, so a stalled ADC keeps sending VDDA, the charger input and the ISET current as good values | X3 | resolved | X3 |
| PT-X37 | completeness | minor | Catalog version 2 is described as having 34 fields; it has 33 | X3 | resolved | X3 |
| PT-X38 | completeness | minor | CONTEXT-PACK 'bench-verified' journal line gives only the version 5 capacity and a false 'every sensor' figure | X3 | resolved | X3 |
| PT-X39 | completeness | minor | Version 5 journal duration stated as both 28.7 h and 28.8 h | X3 | resolved | X3 |
| PT-X40 | completeness | minor | Dashboard charger chart ignores the fitted byte for the active-input band and draws no charger-stage band | X4 | resolved | X4 |
| PT-X41 | completeness | major | Phase C charger status cannot say 'no input active', so a charger with no input at night shows up as a sensor fault | X4 | resolved | X4 |
| PT-X42 | completeness | minor | OpenAPI null rule for the charge current (ISET) leaves out the stalled-ADC case | X4 | resolved | X4 |
| PT-X43 | completeness | minor | Health-report byte 51 is still 'reserved, 0' in the two literate packet diagrams | X4 | resolved | X4 |
| PT-X44 | completeness | minor | The benchlink README's table of where each bench finding went, and failure-modes.md, cite stale lines of the new power code | X4 | resolved | X4 |
| PT-X45 | completeness | minor | tools/README.md's CI section does not mention the new TX profile-variant builds | X4 | resolved | X4 |

## Unresolved issues

### PT-015: INA228/MAX17048 and ADC conversions exist only in the bench tools and would be copied

Layer firmware, severity major, batch B04.

Batch report: Two edits are still needed, and both files are outside B04's allowed list, so I left them alone. (1) firmware/i2cscan/App/i2cscan.c:165 calls `ina228_current_ua(shunt, BENCH_SHUNT_MOHM)`. It must pass `BENCH_SHUNT_UOHM`; as written it reports battery current 1000 times too high. Line 226's `BENCH_SHUNT_MOHM` only goes into help text and is correct. (2) firmware/benchlink/README.md:29 says the register decoding is shared through `../i2cscan/App/bench_regs.c`. It should say `../common/power_regs.c`. A follow-up batch that can edit those two files will clear both. The new guard tests in tests/test_i2cscan.py fail until it does.

What is needed:

- `firmware/i2cscan/App/i2cscan.c`: the battery current must be computed with `BENCH_SHUNT_UOHM`, not `BENCH_SHUNT_MOHM` (the milliohm value makes the current 1000 times too high). `BENCH_SHUNT_MOHM` stays only in the help text.
- `firmware/benchlink/README.md`: the shared register decoding is `../common/power_regs.c`, not `../i2cscan/App/bench_regs.c`.
- The guard tests in `tests/test_i2cscan.py` must pass (`python -m unittest tests.test_i2cscan`).

Worktree check (2026-10-29): the worktree already shows `ina228_current_ua(shunt, BENCH_SHUNT_UOHM)` at `firmware/i2cscan/App/i2cscan.c:172` and `:200`, and `firmware/benchlink/README.md:29` names `../common/power_regs.c`. A later batch appears to have made both edits; run `tests.test_i2cscan` and close the issue if it passes.

### PT-030: The model has no construct for short heavy leads off the breadboard

Layer hardware, severity major, batch B09.

Batch report: The schematic part of the construct is now done: make.py lead_notes() (called in outputs() right after build_schematic.write) adds one KiCad text note per lead, giving its net, both ends, AWG and length. The notes go in the free strip under the circuits (x 25.40, y from 256.54, at most 6 leads). A test checks that this strip is below everything build_schematic draws and that ERC passes with a lead present. A scratch PDF export showed the note text. So the model, proof, build sheet, layout.json, 2D renders, 3D view and schematic now all handle [[lead]]. Two parts are still open and outside B09's file list. (1) PT-030 asks for leads on the battery path and the charger input. That needs [[lead]] entries in hardware/bench-breadboard-r0/source/wiring.toml (and the bq24074 VBUS/ISET nets), which is wiring-batch work (B14). Until then layout.json has 'leads': [] and the committed schematic is unchanged. (2) The notes come from make.py, not build_schematic.py, because build_schematic.py is not in B09's files. A later batch could move them into build_schematic.Sheet. Out-of-scope drift is unchanged: hardware/bench-breadboard-r0/README.md (check_firmware row, CN8, leads, female ARDUINO header) is stale and needs a docs batch. wiring.FIRMWARE/ADC_NETS mapping of ISET (PB1, ADC1_IN5) and VIN_SENSE (PA10, ADC1_IN6) waits for those nets in wiring.toml (B14).

What is needed:

- `[[lead]]` entries in `hardware/bench-breadboard-r0/source/wiring.toml` for the battery path and the charger input (with the bq24074 VBUS and ISET nets), then regenerate every artefact so `layout.json` lists the leads and the schematic carries their notes.
- `wiring.FIRMWARE`/`ADC_NETS` must map ISET (PB1, ADC1_IN5) and VIN_SENSE (PA10, ADC1_IN6) once those nets exist.
- `hardware/bench-breadboard-r0/README.md` must describe the `check_firmware` row, CN8, the leads and the female ARDUINO header.
- Optional: move the lead notes from `make.py` `lead_notes()` into `build_schematic.Sheet`.

Worktree check (2026-10-29): the worktree already has seven `[[lead]]` entries (L1-L7) in `hardware/bench-breadboard-r0/source/wiring.toml:457-499`, a `"leads"` list in `hardware/bench-breadboard-r0/layout.json`, and a README that names CN8, the leads and `check_firmware` (`hardware/bench-breadboard-r0/README.md:39`, `:75`, `:95`). B14 appears to have done the wiring work; re-run the breadboard model tests and close the issue if they pass. The notes still come from `make.py:340` (`lead_notes()`).
