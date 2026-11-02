# Build Progression Issue Catalog

This catalog lists every known issue caused by the build-progression decision record and by Clint's
survey answers of 2026-10-30 (the record's section 7.1, which overrides every default in its section 7).
The record moves the bench from the r0 breadboard to breadboard v2 (step 1) and adds the four
metered rails on the same breadboard (step 1b). Later stages were removed from the repository on
2026-11-02 (git history has them), and with them this catalog's rows that concerned only them.
Its decisions cascade through the record itself, the power-telemetry design and plan, the
breadboard model and generator (`hardware/bench-breadboard-r0`, revisions `bench-bb-r0.1` for change A,
the power path off the breadboard with the pack, WAGO joints and INA228 shunt in the battery lead (P3);
`bench-bb-r0.2` for change B, cups PB5 (LPTIM1_IN1, AF1) and rain PB4 (EXTI4) (N2); `bench-bb-r0.3` for
change C, the PA9 sensor switch and the unswitched STEMMA QT branch; *2026-11-02:* the switch removed
from the breadboard build, r0.3 redefined without it), the node and bench firmware, the
bench tools, gateway and tests (the ws0 silent-port reopen, the preflight tool, the logger and dashboard),
and the documents: the wiring guide, the shopping lists, the runbooks and the indexes.

- Decision record: [`../specs/2026-10-29-build-progression-decisions.md`](../specs/2026-10-29-build-progression-decisions.md);
  Clint's survey answers: [section 7.1](../specs/2026-10-29-build-progression-decisions.md#71-clints-answers-2026-10-30)
- Cascade list (file by file): the record's section 6
- Earlier catalog this work builds on: [`2026-10-29-power-telemetry-issues.md`](2026-10-29-power-telemetry-issues.md)

Batches `W1`-`W13` are the work batches; the number is the wave the batch ran in, and the suffix
names its area. Batches `X1`-`X4` are completeness passes that searched every area for drift left after the
batches and fixed what they found (issues `BP-X01`-`BP-X58`).

## Summary

116 issues: 116 resolved, 0 unresolved.

| Area | Resolved | Unresolved | Total |
|---|---:|---:|---:|
| record | 15 | 0 | 15 |
| docs | 9 | 0 | 9 |
| model | 24 | 0 | 24 |
| firmware | 6 | 0 | 6 |
| tools-gateway-tests | 6 | 0 | 6 |
| completeness | 56 | 0 | 56 |
| **all** | **116** | **0** | **116** |

| Severity | Resolved | Unresolved | Total |
|---|---:|---:|---:|
| blocker | 8 | 0 | 8 |
| major | 52 | 0 | 52 |
| minor | 56 | 0 | 56 |

## Issues

State `resolved` means the batch named in the note fixed it. An unresolved row's note points to the
[unresolved issues](#unresolved-issues) section.

| ID | Area | Severity | Title | Batch | State | Note |
|---|---|---|---|---|---|---|
| BP-001 | record | major | Record status line and section 7 still read as open questions with defaults | W1-record-decisions | resolved | W1-record-decisions |
| BP-002 | record | major | S1, 2.7, D7 and the section 3 roadmap keep the Q1 and Q8 branches; step 1b still points at r0 | W1-record-decisions | resolved | W1-record-decisions |
| BP-004 | record | major | H5 and section 5 keep the BiPOM fallback; no BOB-14021 preparation step | W1-record-decisions | resolved | W1-record-decisions |
| BP-005 | record | minor | Meter wording is '200 mV range, see Q2' | W1-record-decisions | resolved | W1-record-decisions |
| BP-006 | record | major | Purchase wording: 1b purchase timing and the TS resistors | W1-record-decisions | resolved | W1-record-decisions |
| BP-007 | record | major | Section 8: R_ISET, M2 and N2 rows, with D4 and D5 recorded as the workflow's reading | W2-record-cascade | resolved | W2-record-cascade |
| BP-008 | record | major | 6.5 rows carry 'proposed', 'pending Clint' and Q-default wording, and miss documents | W2-record-cascade | resolved | W2-record-cascade |
| BP-009 | record | minor | Q5 fact missing from F6 and H8; stale references in 1.4 and N2 | W1-record-decisions | resolved | W1-record-decisions |
| BP-010 | record | major | P1 chain and NUCLEO jumpers named by drifting W-numbers; landings named by column | W1-record-decisions | resolved | W1-record-decisions |
| BP-011 | record | major | H8(f)'s 25 s stall threshold would reopen a healthy ws0 port every minute | W1-record-decisions | resolved | W1-record-decisions |
| BP-012 | record | major | 6.2, 6.3 and 6.4 rows that cannot work as written; stale 6.x references | W2-record-cascade | resolved | W2-record-cascade |
| BP-013 | record | major | D2 points: lead keys, the supply role, the NTC return and the STAR positions | W1-record-decisions | resolved | W1-record-decisions |
| BP-014 | docs | major | Power-telemetry design and plan: D4/D5, N2, Q8, the official wiring and the 'Kelvin' text | W1-telemetry-spec | resolved | W1-telemetry-spec |
| BP-015 | model | blocker | wiring.py schema cannot express joints, terminals, roles, domains, internal ties or off-board placement | W2-model-schema | resolved | W2-model-schema |
| BP-016 | model | blocker | check_guide is one-way, the comment check is not alias-aware, and the CN9 header is missing | W2-model-schema | resolved | W2-model-schema |
| BP-017 | model | blocker | Battery + path and gauge sense still model the soldered bench (change A, P2-P5, H7) | W4-model-change-a | resolved | W4-model-change-a |
| BP-018 | model | blocker | P1 chain has no stable taggable members; SHUNT.2 -> CN7.16 link must go; the P1 leads must fit the geometry | W4-model-change-a | resolved | W4-model-change-a |
| BP-019 | model | blocker | OLED supply comes from the SHUNT.2 strip and the board-B ground rail (R-3, N3) | W4-model-change-a | resolved | W4-model-change-a |
| BP-020 | model | major | Ground: no STAR, no domain split, several ties, and test-point strips shared with R6 and the NTC | W4-model-change-a | resolved | W4-model-change-a |
| BP-021 | model | major | OUT, the 100 Ohm load, the INA VBUS and the regulator input still run through breadboard strips (F4 path) | W4-model-change-a | resolved | W4-model-change-a |
| BP-022 | model | major | Charger input SRC is a panel on a 5.5 x 2.1 plug with leads into header test pins | W4-model-change-a | resolved | W4-model-change-a |
| BP-023 | model | major | NUCLEO header moves (N3), alias ties and the ISET network/divider (M2) are not in the model | W4-model-change-a | resolved | W4-model-change-a |
| BP-024 | model | minor | wiring.toml notes, meter pull-up placement and revision field | W4-model-change-a | resolved | W4-model-change-a |
| BP-025 | model | major | tests/test_breadboard.py pins the old lead model and lacks the change-A model tests | W4-model-change-a | resolved | W4-model-change-a |
| BP-026 | model | major | make.py has no sheet tier, the sheet carries no hashes or revision, and checked() runs no D3 check | W5-model-sheet | resolved | W5-model-sheet |
| BP-027 | model | major | Build sheet content misses joints, leads, the power-path table and C1-C23, and keeps stale check texts | W5-model-sheet | resolved | W5-model-sheet |
| BP-028 | model | minor | Phase B checks in make.py contradict Q8, P10 and the 1b exit criteria | W5-model-sheet | resolved | W5-model-sheet |
| BP-029 | model | minor | bench-breadboard-r0 README is stale against D1, D4, H6 and 7.1 | W5-model-sheet | resolved | W5-model-sheet |
| BP-030 | model | major | Drawing code hard-wired to the old topology; the 7-lead note limit overflows; drawing-side make.py functions | W6-model-drawings | resolved | W6-model-drawings |
| BP-031 | model | major | Regenerate the breadboard outputs for revision bench-bb-r0.1 (change A) | W7-regen-r0.1 | resolved | W7-regen-r0.1 |
| BP-032 | model | major | Change B in the model: cups PB5 at CN9.5, rain PB4 at CN8.4 (N2 approved) | W8-model-change-b | resolved | W8-model-change-b |
| BP-033 | model | major | Regenerate the breadboard outputs for revision bench-bb-r0.2 (change B) | W9-regen-r0.2 | resolved | W9-regen-r0.2 |
| BP-034 | model | major | Change C not modelled: PA9 load switch, unswitched QT branch, SENS_EN and 3V3_SW | W10-model-change-c | resolved | W10-model-change-c. *2026-11-02: superseded, change C's switch removed from the breadboard build (record 4.6 dated note)*: r0.3 redefined in place without LSW, 3V3_SW and SENS_EN; the QTM branch kept |
| BP-035 | model | major | Regenerate the breadboard outputs for revision bench-bb-r0.3 (change C) | W11-regen-r0.3 | resolved | W11-regen-r0.3. *2026-11-02:* regenerated again for the redefined r0.3 (no load switch) |
| BP-036 | firmware | major | R_ISET 890 Ohm; no ISET gain; integer divider 3; no microvolt ppm helper; stale 'x 3' comments | W2-fw-power-constants | resolved | W2-fw-power-constants |
| BP-037 | firmware | minor | benchlink: morpho-only pin comments, integer VIN_DIVIDER, ISET comment | W4-fw-benchlink | resolved | W4-fw-benchlink |
| BP-038 | firmware | major | Change B firmware: cups PB5 (LPTIM1_IN1 AF1), rain PB4 (EXTI4), LDORDY assert | W8-fw-change-b | resolved | W8-fw-change-b |
| BP-039 | firmware | minor | Mux RESET still 'TBD' though N5 fixed it at PB14 | W8-fw-change-b | resolved | W8-fw-change-b |
| BP-040 | firmware | major | PA9 sensor switch (change C): no way to run exit 9; stale text; no switched branch in the sim; no harness for the console test | W10-fw-change-c | resolved | W10-fw-change-c. *2026-11-02: superseded, change C's switch removed from the breadboard build (record 4.6 dated note)*: TEST-SENSOR-POWER, the sim's switched branch and the harness stay in the code; `i2c_bus` power-cycle stays a no-op on the breadboard |
| BP-041 | firmware | major | M7 counter link probe not implemented; the cups probe must not count its own edge; status key collision | W12-fw-link-probe | resolved | W12-fw-link-probe |
| BP-042 | tools-gateway-tests | major | ws0 has no open-but-silent reopen (H8 f), and the dashboard draws no marker for it | W2-tools-ws0-reopen | resolved | W2-tools-ws0-reopen |
| BP-043 | tools-gateway-tests | major | tools/preflight.py, tests/test_preflight.py and the shared checklist.py do not exist (D6) | W2-tools-preflight | resolved | W2-tools-preflight |
| BP-044 | tools-gateway-tests | major | benchlink_log: R_ISET default, ISET gain, and the model hash and preflight status (not in the CSV header) | W3-tools-benchlog | resolved | W3-tools-benchlog |
| BP-045 | tools-gateway-tests | major | benchlink_dash has no M6 path metric, VCELL step flag, M4 label or M7 cross-checks | W3-tools-dash | resolved | W3-tools-dash |
| BP-046 | tools-gateway-tests | major | tests/test_benchlink.py lacks the logger tests for R_ISET, the gain, the hashes and the preflight status | W3-tools-benchlog | resolved | W3-tools-benchlog |
| BP-047 | tools-gateway-tests | minor | h01_report.py ignores serial-link gaps | W3-tools-h01 | resolved | W3-tools-h01 |
| BP-048 | docs | minor | Change B docs: event model, root README and stage0-node README pin rows | W8-docs-change-b | resolved | W8-docs-change-b |
| BP-049 | docs | major | bench-station-wiring sections 1, 3-6, 6b and 8 contradict S1/Q8, P2-P7, N3, M7 and Q6 | W13-docs-guide | resolved | W13-docs-guide |
| BP-050 | docs | minor | Firmware READMEs carry pre-v2 wiring and R_ISET 890 | W13-docs-firmware-readmes | resolved | W13-docs-firmware-readmes |
| BP-051 | docs | minor | 10-18 and 10-19 specs and plans lack the record's dated notes | W13-docs-old-specs | resolved | W13-docs-old-specs |
| BP-054 | docs | major | PoC shopping list contradicts P3/P7, H5 and 7.1 | W13-docs-shopping | resolved | W13-docs-shopping |
| BP-055 | docs | minor | power-metering.md: phase status, VBUS wiring, phase A rows and the 1b joins | W13-docs-power-metering | resolved | W13-docs-power-metering |
| BP-056 | docs | major | H01 checklist, runbook, failure-modes and web-dashboard miss H8/Q5, the preconditions and the F1-F6 rows | W13-docs-runbooks | resolved | W13-docs-runbooks |
| BP-057 | docs | minor | Shared indexes: CONTEXT-PACK, tools/README and tests/README | W13-docs-indexes | resolved | W13-docs-indexes |
| BP-058 | record | major | 6.1 rows: step 1b clause, three revisions, P1 chain ids, NTC return, new files | W2-record-cascade | resolved | W2-record-cascade |
| BP-059 | record | major | M7: the status field collides with '#status link=', and the cups probe counts its own edge | W1-record-decisions | resolved | W1-record-decisions |
| BP-060 | record | major | H7's 100 mm cap applies only to the regulator-supply leads | W1-record-decisions | resolved | W1-record-decisions |
| BP-061 | model | blocker | Jumper planner can land on morpho aliases, lead-occupied pins and test-point or power-domain strips | W2-model-schema | resolved | W2-model-schema |
| BP-062 | model | blocker | D3 checks 1-6 and 9, the H7 lengths and the lead geometry exist nowhere | W3-model-checks | resolved | W3-model-checks |
| BP-063 | model | major | The build sheet has no 'Changes from the previous revision' section | W5-model-sheet | resolved | W5-model-sheet |
| BP-X01 | completeness | major | Step 1 exit 7: no check confirms POWER_R_ISET_OHM 1000 or POWER_ISET_GAIN_PPM | X1 | resolved | X1 |
| BP-X02 | completeness | major | Charger jumper check from change A step 3 (1A closed, 0.5A/1.5A open, EN1/EN2) is missing from the step 1 build sheet | X1 | resolved | X1 |
| BP-X03 | completeness | minor | nucleo-wl55jc-bringup.md still says the firmware holds 890 ohm for R_ISET | X1 | resolved | X1 |
| BP-X04 | completeness | minor | test_i2cscan comment still calls 890 ohm the 1.0 A jumper | X1 | resolved | X1 |
| BP-X05 | completeness | minor | Record file:line references outside 1.4/N2 now point at the wrong lines | X1 | resolved | X1 |
| BP-X06 | completeness | major | After change C, benchlink and i2cscan never drive PA9, so the hub's SHT45 stays unpowered (and is back-powered through the bus pull-ups) | X1 | resolved | X1. *2026-11-02: superseded, change C's switch removed from the breadboard build (record 4.6 dated note)*: the firmware still drives PA9 high, harmless with PA9 unconnected |
| BP-X07 | completeness | minor | Battery INA228 VBUS at step 1b: the stage plan says it stays on OUT; the record, power-metering and the WAGO model move it to CELL+ position 4 | X1 | resolved | X1 |
| BP-X08 | completeness | minor | Record 4.4 step 5 keeps a board-A-to-board-B ground link that the model removed | X1 | resolved | X1 |
| BP-X09 | completeness | minor | C11's 'cups count while spinning the cups' has no source in the logger | X1 | resolved | X1 |
| BP-X10 | completeness | minor | NUCLEO tie table and bench check omit the PA9, I2C and OLED Arduino/morpho aliases | X1 | resolved | X1 |
| BP-X11 | completeness | minor | check_firmware ignores the OLED pin constants although the OLED nets carry mcu pins | X1 | resolved | X1 |
| BP-X12 | completeness | minor | Bring-up log's 'Not verified' table still says the firmware holds R_ISET 890 Ω | X1 | resolved | X1 |
| BP-X13 | completeness | minor | 'Not implemented' status in the record and design is false against the worktree | X1 | resolved | X1 |
| BP-X14 | completeness | major | check_iset and check_divider demand nominal values exactly, so storing the M2 fit or the measured divider breaks D3 checks 8 and 9 | X2 | resolved | X2 |
| BP-X15 | completeness | major | Shunt verification needs a 'calibrated shunt or DC clamp meter' that no list buys; record M1 and 1b exit (a) still say DMM in series | X2 | resolved | X2 |
| BP-X17 | completeness | minor | power_config.h still says the battery INA228 VBUS lead 'may stay on OUT' at phase B | X2 | resolved | X2 |
| BP-X18 | completeness | minor | D1's word rule fails: 'Nominally' remains in docs/module-protocol.md | X2 | resolved | X2 |
| BP-X19 | completeness | minor | 10-18 bench-station spec pin table still wires ISET 'straight to ISET, no pull' with VIN = 3 x pin | X2 | resolved | X2 |
| BP-X20 | completeness | major | C2's lever-open half asks for 'open', but the M2 ISET network leaves a resistive path from STAR to logic ground | X2 | resolved | X2 |
| BP-X21 | completeness | major | The mode-B P1 output chain runs through an untagged planner jumper (W2) and two A:L+ rail contacts that no check or wiggle covers | X2 | resolved | X2 |
| BP-X22 | completeness | minor | i2cscan README's OLED wiring table still feeds the OLED from breadboard rails and lands its signals on Arduino aliases | X2 | resolved | X2 |
| BP-X23 | completeness | minor | Wiring guide omits THERM from the charger header pins kept on the breadboard | X2 | resolved | X2 |
| BP-X24 | completeness | minor | BOB-14021 preparation never says to separate the two-board panel | X2 | resolved | X2 |
| BP-X25 | completeness | minor | D1 word rule broken: 'Nominally' is still in module-protocol.md | X2 | resolved | X2 |
| BP-X26 | completeness | minor | Protocol docs and firmware comments still describe the pre-change-A sense wiring: gauge 'Kelvin to the cell', INA VIN- on 'the charger's LIPO', VBUS 'jumpered to OUT / the OUT column' | X2 | resolved | X2 |
| BP-X27 | completeness | minor | file:line references into power_config.h are one line off after the R_ISET/ISET-gain/divider edits | X2 | resolved | X2 |
| BP-X28 | completeness | blocker | Only the r0.3 build sheet exists; change A has no r0.1 sheet and no 'Remove' list against the r0 bench | X3 | resolved | X3 |
| BP-X29 | completeness | minor | Record 4.4 step 5 says the sheet lists removals by W-number; the generator and sheet never use W-numbers there | X3 | resolved | X3 |
| BP-X30 | completeness | major | The cups and rain pull-ups are not on the jack pin's strip, so a planner jumper sits on the side of the circuit the link probe cannot see | X3 | resolved | X3 |
| BP-X31 | completeness | minor | CONTEXT-PACK sends measured constants straight to power_config.h, skipping the model-first rule | X3 | resolved | X3 |
| BP-X32 | completeness | minor | Wiring guide still gives ISET's ADC source as about 1 kΩ | X3 | resolved | X3 |
| BP-X33 | completeness | minor | Build sheet says every jumper is solid 22 AWG, but its own OLED check calls W34-W38 Dupont leads | X3 | resolved | X3 |
| BP-X34 | completeness | minor | Part ids C1 and C2 (the meter capacitors) reuse the checklist row ids C1 and C2 | X3 | resolved | X3 |
| BP-X35 | completeness | minor | No test pins that benchlink and i2cscan actually drive PA9 high | X3 | resolved | X3 |
| BP-X36 | completeness | minor | stage0-node README points at board_inputs.c:3-17 for the pin list, which now runs to line 21 | X3 | resolved | X3 |
| BP-X37 | completeness | major | H01 'release' decision D2 is still open, but the H01 preconditions already require version 6 node firmware | X3 | resolved | X3 |
| BP-X38 | completeness | minor | Docs still show the power monitors on the STEMMA QT hub, but change C puts them on the unswitched QTM branch | X3 | resolved | X3 |
| BP-X39 | completeness | minor | Power-telemetry design cites tx_console.c:50 for the radio `link=` field, which is now at line 62 | X3 | resolved | X3 |
| BP-X40 | completeness | minor | failure-modes.md names the wrong console line and the wrong line number for i2c_stuck | X3 | resolved | X3 |
| BP-X41 | completeness | minor | stage0-node README cites board_inputs.c:3-17 for the pin list, which now runs to line 21 | X3 | resolved | X3 |
| BP-X42 | completeness | minor | The `Lead` docstring in wiring.py describes only the old heavy battery lead | X3 | resolved | X3 |
| BP-X43 | completeness | minor | The bring-up log's 'rules of the official wiring' paragraph still describes the battery path as short heavy leads | X3 | resolved | X3 |
| BP-X44 | completeness | major | Step 1 exit 9 cannot be observed as written: sensors are sampled every 15 s, but each PA9-low half lasts only 2 s | X4 | resolved | X4. *2026-11-02: superseded, change C's switch removed from the breadboard build (record 4.6 dated note)*: exit 9 removed from step 1 |
| BP-X45 | completeness | minor | Guide section 6b forbids the meter's current range in the battery path, but the shunt check puts the 87V there | X4 | resolved | X4 |
| BP-X46 | completeness | minor | 10-19 breadboard design's 'Supersedes' column cites line numbers that match neither the old nor the current text | X4 | resolved | X4 |
| BP-X47 | completeness | minor | tests/README.md test count is stale | X4 | resolved | X4 |
| BP-X48 | completeness | major | r0.1 build sheet tells the builder to use solid 22 AWG for the cups and rain jumpers, which land on morpho male pins | X4 | resolved | X4 |
| BP-X49 | completeness | major | Change A's step list never says to cut the THERM jumper (R10) or fit the NTC, but the r0.1 sheet adds the NTC leads | X4 | resolved | X4 |
| BP-X50 | completeness | minor | Record 4.4 step 5 says to keep the regulator-GND-to-rail link, but the r0.1 sheet removes it and fits it again | X4 | resolved | X4 |
| BP-X51 | completeness | minor | Guide 6b forbids the meter's current range in the battery path, but power check 3 puts the 87V in series there | X4 | resolved | X4 |
| BP-X52 | completeness | minor | oled.h's wiring comment still lands the OLED signals on the Arduino aliases that the model leaves empty | X4 | resolved | X4 |
| BP-X53 | completeness | minor | Breadboard README puts the A:L+ rail inside the P1 mode-B chain | X4 | resolved | X4 |
| BP-X54 | completeness | minor | Change C says it 'mirrors PORT-9', but the SHTC3 that PORT-9 keeps upstream sits on the switched hub branch | X4 | resolved | X4. *2026-11-02: superseded, change C's switch removed from the breadboard build (record 4.6 dated note)*: the bench has no switched branch now |
| BP-X55 | completeness | minor | power-metering.md names a firmware define that no longer exists and fixes the divider at 3:1 | X4 | resolved | X4 |
| BP-X56 | completeness | minor | failure-modes 'All down' row still assumes both boards share one USB hub | X4 | resolved | X4 |
| BP-X58 | completeness | minor | Root README puts power phase A 'beside' H01 although the record makes it an H01 precondition | X4 | resolved | X4 |

## Unresolved issues

None. Every issue above is resolved by the batch named in its note.
