# Bench base plate, revision 2: specification

For: the CAD AI that built the first version ("v1", 2026-10-30: `front_tile`, `back_tile`, `board_for_weather`), and the user.
This file is self-contained. It changes v1; it does not start over. Everything v1 does that is not named under section 5 stays as it is.

Coordinates, used throughout:

- **Plate frame**: origin at the front-left corner of the front tile. +x runs to the right and +y runs away from the user. z is height above the deck top.
- **Back-tile local frame**: what `back_tile.py` uses. Plate y = local y + 188 (`board_for_weather.py:12`). Both values are given where it matters.
- "Deck top" is `rib_depth + deck_thickness` = 11.0 mm above the bed (6 + 5; `front_tile.py:22-23`, `:79`).

Sources are cited as `file:line`. "Build sheet" is `hardware/bench-breadboard-r0/build-sheet.md` in the weather-station-2026 repo on master, revision bench-bb-r0.3. "Record" is `docs/superpowers/specs/2026-10-29-build-progression-decisions.md`. "STEP" means a maker's 3D model pinned in that repo's `tools/fetch-cad.sh`; its connector positions were read for this spec.

---

## 1. Purpose and the one rule

The plate is mechanical. It holds the step 1 bench of the solar LoRa weather station: three breadboards, two NUCLEO-WL55JC1 boards, the 1S3P pack and the lever-connector power harness. That bench runs unattended for days, and a 1 s USB dropout resets the debug board and ruins the run (record H1, line 150).

**The one rule: a tug on any cable stops at a printed anchor and never reaches an electrical contact.** Concretely:

1. Every cable mating needs a printed anchor within **30 mm** of the mating face (record P7, line 116; H1, line 150). That covers JST PH plugs, USB plugs, RJ11 plugs, STEMMA QT plugs and leads pushed into breadboard holes.
   - When a plug's rigid body (plug, overmold and boot) is longer than about 25 mm, the anchor grips the jacket within 5 mm of where that rigid body ends.
2. Every anchor is open. It is either a tie bridge that a 4 mm cable tie passes under, or an open-topped jacket clamp that a cable presses into and lifts out of. Nothing encloses a wire. Every lead can be rerouted without unplugging anything.
3. Every lead route between joints, boards and the pack fits the lead lengths fixed in record H7 (line 156). Those lengths are maximums, and the leads are already cut to them (section 3).
4. Sense leads are never bundled with force leads (H7). Where both kinds leave the same part, give the sense leads their own tie opening.
5. No fixed part crosses the tile joint, so either tile lifts straight off. Only wires cross the joint, through open tie points. A part carried by a breadboard may overhang toward the joint, but never past the joint line.
6. Every part lifts out without removing another part.

## 2. Printer and material (unchanged from v1)

| Item | Value | Source |
|---|---|---|
| Printer | Bambu Lab H2D, 0.4 mm nozzle | brief line 5 |
| Nozzles | **Single nozzle.** The single-nozzle envelope is 325 × 320 mm; the dual-nozzle envelope (300 × 320) leaves no brim room on a 300 mm tile | `front_tile.md:111-114` |
| Material | PETG, every part | `printer.toml:3` |
| Tiles | Front tile 300 × 200. Back tile 300 × **220** (v1: 212, of which the first 12 mm are the dovetail tails). The plate is 300 × 408 | section 5, change 4 |
| Joint | Four vertical dovetails at x = 50, 120, 190, 258. Neck 18, head 28, reach 12, total slack 0.5, all in the socket. Lowers on and lifts off | `system.py:17-18`, `front_tile.py:118`, `front_tile.md:79-84` |
| Tray | Deck 5.0 (light variant 3.5), ribs 6.0 deep, 36 mm cells, ribs 2.5 wide at the bed, corners rounded at 12, edge wall 4.0. First layer under 20 000 mm² | `front_tile.py:20-27`, `front_tile.md:48-56` |
| Feet | Four 12.7 mm bumper recesses per tile (+0.4 mm), 1.0 deep, in the solid corner cells | `system.py:135-140` |
| Polish | 1 mm chamfer on exposed edges. None inside pockets, the cradle slot, the dovetails or the WAGO row | `system.py:220-237`, `front_tile.md:108-110` |
| Wall loops | At least 4 for rails, posts, clamps and the joint | brief line 53 |

## 3. Parts on, or anchored to, the plate in step 1

The breakouts plug into the breadboards by their header pins and are not fixed to the plate. They still set keep-out zones and the positions of the connectors the plate must anchor.

Heights used below:

- A breadboard is 8.5 mm tall and sits 1.0 mm deep in its pocket, so its top is at z = 7.5.
- A breakout's header plastic is 2.5 mm (`models.py:16-17`), so **the underside of every breakout PCB and of the OLED is at z = 10.0**.

### 3a. Held by the plate

| Part | Qty | Size (mm) | Held by | Source |
|---|---|---|---|---|
| BusBoard BB830 breadboard (A signals, B power, C display) | 3 | 165.1 × 54.6 × 8.5 | Pocket 1.0 deep, +0.3 per side, finger notch at the left end | `measurements.toml:3-16`, `system.py:144-166` |
| ST NUCLEO-WL55JC1 (MB1389): TX node and RX bridge | 2 | See the outline notes below this table | Edge-held cradle (v1 design) | **ST UM2592 Rev 4 (Nov 2025), figure 7, page 12**, and figure 6, page 11; `measurements.toml:18-41` |
| NUCLEO USB cable: USB-A to **Micro-B** (Adafruit #592 in the repo's buy list) | 2 | jacket ≈ 4.0 (param); plug length **unmeasured** | Jacket clamp at the front edge | UM2592 page 2 ("USB with Micro-B"), figure 6 (CN1); `hardware/chicago-test-hardware-r0/docs/build-and-order.md:7`; `front_tile.py:38` |

NUCLEO-WL55JC1 (MB1389) outline, from UM2592 Rev 4 figures 6 and 7. Seen from the top with the USB end toward the user, which is how it lies on the plate:

- **Width and length.** 70.0 wide. **64.5 long** on the left edge, measured from the antenna-end edge to the bottom of the button tab.
- **Antenna end.** The right part is notched 7.5 deep over the last 35.8 mm, so the right edge measures 57.0, also to the tab level.
- **USB end.** The edge is 2.0 mm short of the 64.5 line everywhere except a **31.7 mm tab** between 13.4 and 45.1 mm from the left edge, with 45° chamfers. v1's "two 2.0 corner cuts at the USB end" (`measurements.toml:33-36`) misreads this tab.
- **SMA.** 6.8 wide, 22.4 to 29.2 mm from the left edge, standing **10.0** past the antenna-end edge.
- **CN1, the Micro-B receptacle.** It is on the **underside** of the board, at the right end of the tab. It spans about 37.1 to 45.0 mm from the left edge, so its centre is **41.1 mm from the left edge, +6.1 mm from the board's centre line**. These positions are read off the figure 6 drawing, ±1 mm. Its plug axis is about **z 12.6**: the 14.0 ledge less about 1.4 to the receptacle's centre below the PCB.
- **Other.** No mounting holes. Morpho pin centres 3.5 in from each long edge. About 19 tall overall.
| Pack, Adafruit #353, 1S3P 6600 mAh | 1 | 69 × 54 × 18 (Adafruit's STEP is 70.0 long) | Cradle, 6 mm walls, 20 mm hook-and-loop strap | build sheet line 63; `models.py:5`, `:52`; `measurements.toml:63-76` |
| NTC #372 10 kΩ bead, taped on the pack | 1 | 4 × 4 × 3; two sense leads of 300 mm to B:c58 and B:L−46 | Its own tie point, separate from the pack's force leads | build sheet lines 65, 149-150; `models.py:53` |
| WAGO 222-415 (CELL_POS, SYS_OUT, STAR) | 3 | 26.6 × 20.5 × 14.5 (levers closed) | Pocket row, 8 mm walls, levers up | `measurements.toml:43-61` (WAGO data, version 19.04.2022), matches the element14 and Farnell listings; build sheet lines 159-162 |
| WAGO 222-413 (BATT) | 1 | 17.0 × 20.5 × 14.5 | Same row | same |
| Spare WAGO 222-413 (meter splice, temporary) | 1 | 17.0 × 20.5 × 14.5 | Optional pocket near CELL_POS | build sheet line 279 (power check 3); record line 282 (exit 4B) |
| 100 Ω ½ W test load (mode A only) | 1 | axial, ≈ 10 long; **its own leads are 30 mm**, into SYS_OUT position 2 and STAR position 3 | Two V posts, 7 mm clear of the plastic | build sheet lines 64, 138-139; `back_tile.py:192-193` |
| USB-C cable from the wall adapter into the charger's own USB-C | 1 | 1000 mm; jacket ≈ 4 (param); plug length **unmeasured** | **New** jacket clamp | build sheet lines 66, 151, 261 |

### 3b. On the breadboards, which set connector positions and keep-outs

| Part | Board, holes | Board outline (mm) | What the plate must handle | Source |
|---|---|---|---|---|
| Charger, Adafruit bq24074 #4755 | B: a50 (GND) to a60 (VBUS) | 38.1 × 33.02. It reaches 30.48 out from the header line, **17.15 past board B's edge**. Underside at z 10.0 | Its USB-C and DC jack face **column 63, along the board's length**. Its two JST PH sockets (BATT and SYSOUT) face **column 1** | build sheet line 52; `wiring.toml:182`; STEP `4755 USB Solar Charger.step` |
| INA228 #5832 (battery) | B: a36 (ALERT) to a43 (VCC) | 25.4 × 20.32, 4.45 past the edge | X1 screw terminal on its outer edge: 3.5 mm pitch, top at z ≈ 20.1, wires enter from outside the board | build sheet line 53; `wiring.toml:211`; `models.py:44`; STEP |
| Fuel gauge MAX17048 #5580 | B: a25 (QSTART) to a30 (VIN) | 25.4 × 20.32, 4.45 past the edge | Two JST PH sockets on its outer edge, facing outward. BAT1 takes the gauge pigtail | build sheet line 54; `wiring.toml:229`; STEP |
| Regulator, Pololu S7V8F3 #2122 | B: a14 (SHDN) to a17 (VOUT) | 11.43 × 16.51, 1.9 past the edge | Two 100 mm solid leads in B:b15 and B:b16 | build sheet lines 55, 143-144; `wiring.toml:241` |
| BATTERY POWER shunt header | B: a8, a9 | 2-pin | none | build sheet line 56 |
| RJ11 breakouts BOB-14021 with PRT-00132 jacks (wind BOBW, rain BOBR) | A: a3-a8 and a12-a17 | 21.6 × 20.6. Jack 14 × 13 × 11.5, its face **6.7 past board A's edge** | Both RJ11 meter cables plug in here | build sheet lines 42-43; `wiring.toml:58`, `:70`; `models.py:43` |
| STEMMA QT to male-header cables: QT to the hub, QTM to the power monitors | A: a40-a43 (QT) and a46-a49 (QTM) | 4 pins each | Two QT cables leave here | build sheet lines 44, 46 |
| OLED, Adafruit 2.7 in #2674, on 30 cm Dupont leads | C: a22 to a41 | 85 × 58 module board (74 × 46 × 5 glass on top). It reaches 55 out from the header line, **41.7 past board C's edge**. Underside at z 10.0 | Nothing taller than z 8 under it | build sheet line 67; `wiring.toml:403`; `models.py:45` |

### 3c. Leads, with H7 maximum lengths

| Lead | Kind | Max length | From | To | Source |
|---|---|---|---|---|---|
| L_PACK_POS, L_PACK_NEG | pack-mating half of #1131 cable 1 | 60 | pack plug | CELL_POS 1, STAR 1 | build sheet lines 130-131 |
| L_BATT_POS, L_BATT_NEG | board half of cable 1 | 60 | charger BATT socket | BATT 2, STAR 2 | lines 134-135 |
| L_SYSOUT_POS (black lead insulated) | board half of cable 2 | 60 | charger SYSOUT socket | SYS_OUT 1 | lines 136-137 |
| L_GAUGE_POS (sense; black lead insulated) | board half of cable 3 | 60 | gauge BAT1 socket | CELL_POS 3 | lines 140-141 |
| L_CELL_INA, L_INA_BATT | 22 AWG solid | **50** | CELL_POS 2 / INA X1 | INA X1 / BATT 1 | lines 132-133 |
| L_VBUS (sense) | 22 AWG solid | 60 | INA X1.2 | SYS_OUT 3 | line 142 |
| L_REG_VIN, L_TIE | 22 AWG solid | **100** | SYS_OUT 4 / STAR 4 | B:b15 / B:b16 | lines 143-144; record line 156 |
| L_RLOAD_A, L_RLOAD_B | the load's own leads | **30** | SYS_OUT 2 / STAR 3 | load | lines 138-139 |
| L_NUC_RET | 22 AWG solid | set by routing (≈ 200) | NUCLEO CN6.7 | B:c16 | line 145 |
| L_REG_3V3 | 22 AWG solid | set by routing (≈ 250) | B:c9 | A:c34 | line 146 (it names LSW's strip; the lead stays when LSW goes) |
| L_OLED_VCC, L_OLED_GND | Dupont | ≈ 300 | NUCLEO CN7.16, CN10.20 | C:c23, C:c22 | lines 147-148, 271 |
| W26-W30 (OLED signals) | Dupont | ≈ 300 | C:e25-e37 | NUCLEO CN10 | lines 72, 113-117 |
| W19-W35 to the NUCLEO | 22 AWG solid | ≤ 200 | boards A and B | NUCLEO Arduino headers | lines 104-122; record line 156 |
| QT cables | STEMMA QT | 50-100, 200 where the layout needs it | board A | hub; INA228, then the gauge | record H4, line 153 |

### 3d. Off the plate

- The wall adapter itself, at the mains.
- The SEN-15901 wind and rain meters. Their RJ11 cables are never cut, and each needs an anchor on the plate (record H5, line 154).
- The solar panel. It is **not connected in step 1**, where the USB-C adapter is the charger's only input (build sheet line 261).
- The Fluke 87V, which reaches the plate only through the temporary splice.
- **Not yet placed anywhere:** the passive STEMMA QT hub (#5625) and its four sensor breakouts (SHT45, BMP581, LTR390, SHTC3; `docs/hardware/bench-station-wiring.md:50-56`). Record H1 asks for them on foam tape or standoffs. Their sizes are not in the repo; see open item 9.

## 4. Layout, in plate coordinates

### 4a. Breadboard orientation (the assumption that drives everything)

`layout.json` shows which end of each breadboard is column 1. On board B, hole L+1 is at x = 334.96 and L+63 at x = 177.48, inside an outline from x 174.94 to 337.5, so column 1 is at the high-x end of the model's drawing. Row a and the L rails are at the drawing's low y, and every breakout overhangs past them (`wiring.toml:5-8`).

The renders (`renders/board-a.png`, `board-b.png`, `board-c.png`, `overview.png`) draw all three boards with column 63 on the left and row a and the L rails at the top, with the parts overhanging upward.

**This spec assumes all three boards lie on the plate as the renders show them:**

- column 63 at the left (low x), column 1 at the right;
- row a and the L+ and L− rails toward the back (+y);
- every breakout overhanging toward the back.

The user must confirm this (open item 1). The other way round, rotated 180°:

- **Board B:** the charger's 17.15 mm overhang would cross the tile joint.
- **Board C:** the OLED would land on board B.
- **Board A:** the RJ11 plugs would run into the TX NUCLEO.

Hole formulas from `layout.json`. The 5.71 mm margin from the board edge to the outer rail is assumed symmetric: (54.6 − 43.18) / 2. Treat both formulas as ±1.5 mm until the boards are measured.

- Hole x = pocket_x + 0.3 + 3.81 + 2.54 × (63 − column)
- Hole y = pocket_y + 0.3 + 54.6 − 5.71 − d, where d is the row's distance from the outer rail: L+ 0, L− 2.54, a 7.62, b 10.16, c 12.70, d 15.24, e 17.78, f 25.40, j 35.56, R− 40.64, R+ 43.18.

Each breakout's connectors were placed from the maker's STEP. `models.py:64-73` states how each model's header hole maps to the part's highest-numbered column, with the board extending over the rails.

### 4b. Back tile (r2 proposal; local y, with plate y in brackets)

| Item | x | y local [plate] | z | Notes |
|---|---|---|---|---|
| Joint line, tails | 0-300 | 0-12 [188-200] | — | unchanged |
| **Board B pocket** | **39.0-204.7** (v1: 14.0) | 20.0-75.2 [208.0-263.2] | — | column 63 at x 43.1, column 1 at x 200.6; row a at y 61.6, L+ at 69.2, board edge 74.9 |
| Charger board | 44.4-82.5 | 59.0-92.1 [247.0-280.1] | underside 10.0 | **its 17.15 mm overhang toward board C** |
| Charger **USB-C** receptacle | 43.4-51.3, face at **x 43.4 facing −x** | 64.7-73.7 [252.7-261.7], centre **69.2 [257.2]** | centre ≈ 12.7 (STEP: 0.58-4.78 above the charger PCB) | from STEP, unverified on the board |
| Charger DC jack (step 1b only) | 41.2-55.2, face at x 41.2 facing −x | 75.8-85.8 [263.8-273.8] | top 22.5 | STEP |
| Charger JST PH, inner socket | 73.6-82.2, opening at x 82.5 facing +x | 65.9-73.8 [253.9-261.8] | top 16.4 | which socket is BATT and which SYSOUT: open item 6; either fits below |
| Charger JST PH, outer socket | same | 77.3-85.2 [265.3-273.2] | | |
| INA228 board | 90.1-115.5 | 59.0-79.4 [247.0-267.4] | underside 10.0 | |
| INA228 X1 terminal | 95.3-110.3 | 69.3-79.1 [257.3-267.1] | top ≈ 20.1 | wires leave toward +y |
| Gauge board | 120.6-146.0 | 59.0-79.4 [247.0-267.4] | underside 10.0 | |
| Gauge JST PH sockets | 125.0-132.9 and 133.7-141.6 | opening at 79.4 [267.4] facing +y | top 16.4 | BAT1 is one of them (open item 7) |
| Regulator leads | B:b15 at 165.0, B:b16 at 162.5 | 59.0 [247.0] | | body over y 56.3-76.8 |
| **WAGO row** | **50.0-164.1**, left to right **BATT 52.5-70.7, SYS_OUT 73.2-101.0, STAR 103.5-131.3, CELL_POS 133.8-161.6** | **92.6-119.3 [280.6-307.3]** | walls 8, bodies 14.5 | wire entries face −y (toward board B), levers up; WAGO front faces at y 95.7 [283.7] |
| Spare 222-413 splice pocket (optional) | about 164-185 | 92.6-119.3 | | |
| Load V posts | ≈ 96.5 and 108.5 | ≈ 86 [274] | 7 | body over the SYS_OUT/STAR wall |
| **Battery cradle**, turned 90° (long axis along y) | outer ≈ 188-255 | outer ≈ 79-161 [267-349] | walls 16 | lead gap in the near wall, at the end nearest the row; exact place depends on open item 5 |
| **Board C pocket** | 14.0-179.7 | **121.0-176.2 [309.0-364.2]** (v1: 95.0) | — | column 63 at x 18.1 |
| OLED module (keep-out) | 54.3-139.3 | 175.9-217.6 [363.9-405.6] | underside 10.0 | only parts 8 mm tall or less underneath |
| **USB CHG jacket clamp** | from the plug length: (43.4 − L_c − 1 − 16) to (43.4 − L_c − 1); for L_c = 22, **4.4-20.4** | 69.2 [257.2] | bore at 12.7 (param) | raised clamp, open top |
| Solar lead clamp (step 1b, optional) | at the left edge, 0-16 | ≈ 81-90 [269-278] | bore ≈ 12 | beside the DC jack lane |
| Step 1b reserve (flat, empty) | 207-296 | 12-75 [200-263] | — | |
| Far edge | — | 220 [408] | — | |

### 4c. Front tile (r2 proposal)

| Item | x | y | z | Notes |
|---|---|---|---|---|
| NUCLEO jacket clamps (USB TX, USB RX) | lanes at cradle centre + `nucleo_usb_offset` (+6.1, one value for both): **x 53.6 and 140.6** | **2-18** (16 long) | bore at **≈ 12.6** (param = 14.0 ledge − ≈ 1.4; CN1 is on the underside) | raised clamp; v1 lanes were x 45 and 135 |
| TX cradle, centre x 47.5 | outer 8.1-86.9 | USB end at **41.0** (v1: 32.0); rails 41-91 | ledge 14.0 | `cradle_usb_y` = L_u + 16 + 3, with L_u the Micro-B plug length (default 22) |
| RX cradle, centre x 134.5 | outer 95.1-173.9 | same | same | |
| Antenna-end stops | x = cx − 31 to cx − 17 (v1 offset kept), which is 4 to 18 mm from the board's left edge | near face at `cradle_usb_y + nucleo_length + nucleo_clearance` = **106.0**; 4 deep | 17 tall | v1 had zero clearance. It bears on the full-length part of the antenna-end edge and clears the SMA (from 22.4) by 4.4 |
| SMA overhang (keep-out) | cx − 12.6 to cx − 5.8 | to 105.5 + 10.0 = **115.5** | | open item 4 (antenna sweep) |
| **Board A pocket** | 14.0-179.7 (unchanged) | 120.0-175.2 (unchanged) | — | column 63 at x 18.1; row a at 161.6; board edge at 174.9 |
| QTM header (A a46-a49), QT header (A a40-a43) | 53.7-61.3 and 68.9-76.5 | 161.6 | | |
| RJ11 jacks (BOBR, BOBW) | 134.3-148.3 and 157.2-171.2 | face at **181.6, facing +y** | 12.6-24.1 | the plugs reach about y 196 (open item 8); they must not pass the joint line at 200 |
| ~~Carrier reserve~~ | — | — | — | *Removed 2026-11-02:* the step 3 PCB it was kept for is parked. The space is free for the sensor deck (§7a) |
| QT hub and sensor area (flat) | 190-290 | 100-170 | — | open item 9 |
| Meter-cable jacket clamp | 280-296, running along x | ≈ 185 | ≈ 6 | width = `meter_cable_width` (open item 8) |

### 4d. Proposed anchors

Start from these points. Section 5 gives the acceptance rule each one must pass; move any of them in the sketch as long as they still pass.

| Id | Tile | Centre (x, y local) | Serves | Distance to the mating |
|---|---|---|---|---|
| T1 | back | (89, 86) | both charger JST plugs | 5 / 17 |
| T2 | back | (118, 86), double opening | INA X1 force links; L_VBUS in its own opening | 10-24 |
| T3 | back | (155, 86), double opening | gauge JST (sense, its own opening); L_REG_VIN and L_TIE (force) | 18-26 / 29 |
| T4 | back | about (174, 100) | the pack plug to pigtail mating, which floats here | ≤ 15 |
| T5 | back | on the battery cradle, away from T4 | the NTC pair, on its own | — |
| T6, T7 | back | (24, 16), and right of board B near (213, 28) | the bundle that crosses the joint: L_REG_3V3, L_NUC_RET, W20/W25/W31/W35, the OLED Duponts, QTM | — |
| F1 | front | (65, 182) | QT and QTM cables | 22 |
| F2 | front | (85, 182), kept from v1 | the bundle that crosses the joint | — |
| F3, F4 | front | (60, 114), clear of the TX SMA at x 34.9-41.7; and (91, 100) | the TX NUCLEO's jumper bundle (check C19, "jumpers tied"; record N3, line 139) | — |
| F5 | front | (152, 194) | both RJ11 meter cables, just past their plugs | ≈ 15 |
| F6 | front | right edge, y ≈ 185 | meter cables leave the plate (jacket clamp) | — |

## 5. Changes from v1

Each change gives what to do, why, and an acceptance check the sketch or `nurb check` must show. Checked lead paths use 1.15 × the straight-line distance, plus 10 mm wherever the wire must turn back behind a plug that faces away. Every lead keeps at least 5 mm spare.

1. **Fix the breadboard orientation in the model.** Mark column 1, column 63 and row a on each pocket in the sketch, all three boards as in section 4a.
   - *Why:* every connector position below depends on it, and v1 left it undefined.
   - *Check:* the sketch labels both ends and the row-a side of every pocket.

2. **Move the WAGO row next to board B's rail-side long edge, between boards B and C.** Use x 50.0-164.1 and back-tile y 92.6-119.3. Order from the left: BATT (222-413), SYS_OUT, STAR, CELL_POS. Turn the pockets so the wire entries face board B; keep the 8 mm walls, the levers up and v1's pocket clearances.
   - *Why:* v1's row (x 182-296, local y 20-46.7; `back_tile.py:148-150`) is out of reach of the H7 lengths whichever way board B lies. With the render orientation, the estimated paths are:
     - L_BATT_POS 155 vs 60;
     - L_SYSOUT_POS 213 vs 60;
     - L_INA_BATT 130 vs 50;
     - L_CELL_INA 153 vs 50;
     - L_GAUGE_POS 120 vs 60;
     - L_TIE 149 vs 100.

     Rotated 180°, the best case is still L_BATT_NEG 163, L_CELL_INA 103 and L_REG_VIN 209. The repo's own model draws the joints beyond board B's rails, between columns 63 and about 37 (`wiring.toml:363-390`, `place_mm`), which is where this change puts them. v1 abandoned that spot for lack of depth (`back_tile.md:48-54`); change 4 adds the depth.
   - *Check:* the sketch carries a reach table for every lead in section 3c with path ≤ limit − 5. The r2 estimates, worst case over which charger socket is BATT, are:

     | Lead | Path | Limit |
     |---|---|---|
     | L_BATT_POS | 47 | 60 |
     | L_BATT_NEG | 48 | 60 |
     | L_SYSOUT_POS | 40 | 60 |
     | L_INA_BATT | 41 | 50 |
     | L_CELL_INA | 39 | 50 |
     | L_VBUS | 17 | 60 |
     | L_GAUGE_POS | 15 | 60 |
     | L_REG_VIN | 88 | 100 |
     | L_TIE | 58 | 100 |

     Also: no part of the row sits under any breakout overhang (the charger reaches y 92.05; the row starts at 92.6), and every lever opens fully.

3. **Shift board B's pocket right, from x = 14.0 to 39.0** (parameter `board_b_x`). Its y stays 20.0.
   - *Why:* the charger's USB-C faces column 63, along the board. Its face sits 4.1 mm inside board B's left end. With v1's pocket at x 14, a 22 mm plug ends at x ≈ −4, off the plate, leaving nowhere to anchor the cable.
   - *Check:* the USB CHG clamp lies wholly on the tile (x ≥ 0); its near face is ≤ 30 mm from the receptacle face; the pack cradle and the step 1b reserve still fit at the right.

4. **Move board C back, from local y 95.0 to 121.0, and make the back tile 220 deep** (v1: 212), keeping board C at x 14.0.
   - *Why:* room for change 2, plus the OLED's 41.7 mm overhang behind board C. It reaches local 217.6, which would pass v1's far edge at 212.
   - *Check:* the OLED keep-out (x 54.3-139.3, local y 175.9-217.6) lies inside the tile and has nothing taller than z 8.0 under it. The back tile still fits 325 × 320 with a brim.

5. **Add the charger's USB-C anchor ("USB CHG").** Use v1's jacket clamp profile on a pedestal, so the bore centre sits at the plug's axis (`usb_chg_bore_z`, default 12.7, from the STEP). The clamp runs along x at local y 69.2. Its near face is at x = 43.4 − `usb_c_plug_length` − 1 (default plug length 22). It grips `usb_c_jacket` (default 4.0) with v1's 0.4 pinch. The cable leaves by the tile's left edge (it goes to a wall outlet, not the Mac), so it does not join the NUCLEO cables at the front edge.
   - *Why:* this is the charger's only input in step 1 (build sheet line 261), and v1 had no anchor for it.
   - *Check:* the clamp's near face is ≤ 30 mm from the receptacle face, and the bore is within 2 mm of the plug's axis height. Proved on the coupon with the real cable.

6. **Rework the NUCLEO cable lanes and the cradle stop.**
   - (a) Move the cradles back, so the board's USB end sits at `cradle_usb_y` = `nucleo_usb_plug_length` (default 22) + 16 (clamp) + 3 = 41.0 (v1: 32.0).
   - (b) Replace each deck-level clamp with a raised clamp whose bore sits at `nucleo_usb_z` (default 12.6), at y 2-18. CN1 hangs under the board, so the plug's axis is below the 14.0 ledge (UM2592 figure 6).
   - (c) Delete v1's tie bridges at y 24 (`front_tile.py:134`): they sit under the Micro-B plug body.
   - (d) Use one lane offset for both cradles, `nucleo_usb_offset` = **+6.1** from the cradle centre toward the 57.0 edge (UM2592 figure 6; confirm on the coupon). v1 used −2.5 on the TX lane and +0.5 on the RX lane (`front_tile.py:131`, `:146`). Both are wrong, and identical boards cannot need two values.
   - (g) In `measurements.toml`, replace `nucleo_corner_cut` with the tab: 31.7 wide, 2.0 proud, from 13.4 to 45.1 mm off the left edge. Add `nucleo_sma` (22.4 to 29.2, 10.0 proud) and `nucleo_cn1` (centre 41.1 off the left edge, underside). Cite UM2592 Rev 4 figures 6 and 7.
   - (e) Put the antenna-end stop's near face at `cradle_usb_y + nucleo_length + nucleo_clearance` (default 0.5). v1 put it at exactly `cradle_y + NUCLEO_LENGTH`, zero clearance (`front_tile.py:159`).
   - (f) Move the TX/RX label recesses off the stops.
   - *Why:* the plug's rigid body decides where the jacket starts. The plug's axis is about 12.6 mm up while v1's bore is 3.5 mm up. v1's lanes miss the receptacle by 8.6 mm (TX) and 5.6 mm (RX). A real board longer than 64.5 would not drop in.
   - *Check:* each clamp grips only jacket; the clamp-to-receptacle distance is ≤ 30; stop, antenna overhang and label stay clear of board A's pocket at y 120. Coupon section 6a.

7. **Anchor every board B mating, using T1-T4 in section 4d.** Each sits in the open band between board B's edge (local 74.9) and the row (92.6), never under a breakout. This replaces the draft's strips of bridges along both long edges of board B.
   - Use double-opening bridges where a sense lead leaves beside force leads: X1 with L_VBUS, and the gauge pigtail with the regulator leads.
   - *Why:*
     - Board B's near edge is 8 mm from the joint line.
     - Its far edge lies under the charger, INA228 and gauge (PCB underside at z 10.0). A tie cannot be threaded there.
     - The H7 sense/force separation needs separate openings.
     - The anchors must follow the connectors, whose columns the build sheet fixes (lines 52-55).
   - *Check:* a table listing, for each JST mating, the X1 terminal, B:b15/B:b16 and the pack mating, its anchor id and distance (≤ 30), and that no anchor sits under a breakout or inside a pocket.

8. **Move the load resistor's V posts in front of the row,** straddling the SYS_OUT/STAR wall (x ≈ 96.5 and 108.5, local y ≈ 86, 7 mm tall).
   - *Why:* its leads are 30 mm (build sheet lines 138-139). v1's posts at (279, 100) and (291, 100) are about 56 mm from STAR and 58 mm from SYS_OUT.
   - *Check:* both leads reach with 5 mm spare; the body is at least 3 mm from any wire route and from T1 and T2.

9. **Move and turn the battery cradle** to the right of the row: outer ≈ 188-255 by 79-161 local, long axis along y.
   - Put the pack-lead gap in the wall nearest the row's right end, with T4 at the mating.
   - Put the NTC lead gap in another wall, with T5.
   - Run the strap along y, with its bridges at the cradle's two ends, centred in x, so the near bridge clears board B's pocket corner.
   - Change `battery_slack` from 1.0 to **2.0**: Adafruit's STEP is 70.0 long, which leaves no slack against a 69 + 1 pocket.
   - *Why:* L_PACK_POS and L_PACK_NEG are 60 mm from the plug mating to CELL_POS and STAR.
   - *Check:* the mating point is within 48 mm straight line of a STAR position and a CELL_POS position, and the pack's own lead (open item 5) reaches it without tension. If it cannot, the sketch says so and proposes a cradle position.

10. **Add the RJ11 meter-cable anchors.** F5 sits just past both plugs, on the front tile's deck between the sockets at x 134-176. F6 is an open-top clamp at the right edge for `meter_cable_width`. The cables run along y ≈ 185-194 to the right column.
    - *Why:* the meter cables are live in step 1 (exit 6, record lines 289-290). A tug on one pulls a BOB-14021 out of board A. The brief and v1 did not list them.
    - *Check:* F5 is ≤ 30 mm from both jack faces; the plugs end before y 200; nothing fixed crosses the joint.

11. **Add the TX jumper-bundle and joint-crossing anchors** F1-F4 and T6-T7.
    - *Why:* check C19 ties the Arduino-header jumpers (build sheet line 204). Record N3 ties "NUCLEO and jumper bundle" to the plate. The QT cables and the long leads cross the joint.
    - *Check:* F1 is ≤ 30 mm from both QT headers. Every bundle that crosses the joint passes an open tie on each tile within 25 mm of the joint line.

12. **Turn the three INA228 spots off by default** with `ina_spots=False`. Keep the code; don't print them.
    - *Why:*
      - Step 1b puts its three INA228s in a breadboard by their signal pins, not on standoffs (record S1, line 164; step 1b "Built", line 343). Since 2026-11-02 that is "one of the full-size breadboards already owned" (record line 793).
      - Step 1b runs after step 2, on the step 2 plate (record line 339; `bench-station-wiring.md:30`).
      - Their v1 place (x 40-137, local y 168-188) is under the OLED overhang in v1 as well as in r2. The OLED underside is at z 10, and a spot stands about 18 tall.
    - *Check:* the default build has no standoffs; `ina_spots=True` still builds.

13. **Solar lead clamp: optional, default off, moved.** It goes to the back tile's left edge beside the USB CHG clamp, in the lane of the charger's DC jack (local y ≈ 81-90).
    - *Why:* step 1 has no solar input (build sheet line 261). v1's clamp at the front tile's right edge (286, 150) is about 250 mm and a tile joint away from the DC jack. Section 7 covers its step 1b use.
    - *Check:* with the option on, the clamp sits ≤ 30 mm past the DC plug's rigid body.

14. **Labels: blank recesses only, no text glyphs in any solid.** Keep v1's sizes, the tile arrows and the dots.
    - *Why:* this keeps the tiles byte-identical on any computer (`front_tile.md:86-90`). But `system.py:182-217`, edited 2 Nov, now engraves Arial Bold words "deliberately and at the user's request" (`system.py:195-198`), while the 30 Oct cards say no glyphs. The user must settle it (open item 10). This spec follows the no-glyph rule.
    - *Check:* no `Text` geometry in either tile.

15. **Re-place v1's tie points.**
    - Delete back tile (70, 86.5), (115, 86.5) and (155, 86.5): the row now sits there.
    - Delete back tile (191, 73), (285, 73), (285, 130), (191, 155), (245, 163), (191, 186) and (285, 186): they served the old row and cradle.
    - Delete front tile (152, 182), which F5 replaces, and (210, 120), (210, 170), (240, 150) and (262, 150), which served the old solar lane.
    - Keep front tile (85, 182) as F2.
    - *Check:* every tie in the build appears in the section 4d table or the sketch's anchor table.

16. **Optional OLED rest:** two posts under the OLED's far corners, near local y 214, top at z 9.0 (`oled_rest_z`), for a foam pad.
    - *Why:* the module is cantilevered 55 mm off a 20-pin header, and check C11 wiggles the bench.
    - *Check:* nothing else under the OLED is taller than z 8.0.

17. **Optional splice pocket** for the spare 222-413, placed by the sketch within 40 mm of CELL_POS.
    - *Why:* power check 3 and exit 4B splice the meter or a 1 Ω resistor into the pack's red lead (build sheet line 279; record line 282).
    - *Check:* if it cannot fit, the sketch says so (open item 13).

18. **Move the labels** displaced by the new positions: B POWER, C DISPLAY, the WAGO names, 100R, TILE 2, USB CHG and the TX/RX lanes. Add one label recess per WAGO, none under an overhang.

19. **`measurements.toml` additions,** each with its source:
    - the charger's board, USB-C, DC jack and JST positions (STEP);
    - INA X1 and gauge JST positions (STEP);
    - the OLED body (`wiring.toml:403`);
    - the BOB jack (`models.py:43`);
    - the breakout underside height of 10.0 (`models.py:16-17`);
    - `usb_c_plug_length`, `usb_c_jacket`, `nucleo_usb_plug_length`, `nucleo_usb_z`, `nucleo_usb_offset`, `meter_cable_width`, `rj11_plug_length` and the pack's lead length. Mark these "to measure" until the user gives values.

## 6. Fit-test coupon

Print this first and check each item with the real part:

1. NUCLEO cradle-length section.
   - (a) A full-width cradle (70.8 slot, 14.0 ledge, 3 mm capture), with the antenna-end stop at `nucleo_length + nucleo_clearance`, plus a USB-end marker. Check: a real NUCLEO-WL55JC1 drops in flat, its pins clear, its SMA clears the stop, and it lifts straight out.
   - (b) The raised Micro-B jacket clamp at its lane offset (+6.1), distance and bore height (12.6). Check: with the real cable plugged in, the jacket sits in the clamp with no bend at the plug.
2. USB CHG clamp section: the raised clamp at 12.7, with a 43.4 − `usb_c_plug_length` reference mark. Check: the real adapter cable's jacket lies straight in it.
3. One breadboard pocket corner with the finger notch (v1 item).
4. One 222-415 and one 222-413 pocket with the r2 entry orientation. Check: levers open fully; a wire enters straight.
5. One tie bridge and one double-opening bridge.
6. One RJ11 meter-cable clamp at `meter_cable_width`.
7. The load resistor's two V posts.
8. One tile-joint section (v1 item).
9. If chosen: one OLED rest post.

Dropped from v1's coupon: the INA228 standoff (change 12).

## 7. Open items: the user measures or decides

1. **Orientation:** do all three breadboards lie as the renders show (column 63 at the left, row a and the L rails toward the back)? Everything in sections 4 and 5 assumes so.
2. **USB-C adapter cable:** plug length from the receptacle face to the end of the boot, jacket diameter, and whether the plug is straight.
3. **NUCLEO USB:** the Micro-B plug length and jacket of the Adafruit #592 cables. Also confirm on the coupon the receptacle position read from UM2592 figure 6 (centre +6.1 from the board centre, underside, axis about z 12.6).
4. **NUCLEO length and antenna:**
   - **Verified against ST:** UM2592 Rev 4 (November 2025), figure 7, page 12 gives 70.0 × 64.5. The 64.5 runs from the antenna-end edge to the bottom of the 31.7 mm button tab. That matches v1 (`measurements.toml:23-26`) and the repo (`hardware/chicago-test-hardware-r0/source/render_prototype.py:54`).
   - It is a drawing dimension, so check the boards in hand on coupon section 6a.
   - The stop's near face moves 1:1 with `nucleo_length`. A board longer than `nucleo_length + nucleo_clearance` will not drop in. A shorter one leaves that much play toward the USB end, which the cable clamp, not the stop, must take.
   - The stop bears on the antenna-end edge 4 to 18 mm from the left edge, which is the full-length part, clear of the SMA.
   - Is the SMA antenna swung upright? Nothing on the plate may be in its sweep.
5. **Pack:** the length of its own lead from the pack to the plug face; which face and corner it leaves from; its true length (69 or 70).
6. Which charger JST is BATT and which is SYSOUT (inner at local y 69.8 or outer at 81.3). Both fit the reach table; this only decides the labels.
7. Which gauge socket is BAT1 (both fit).
8. **Meter cables:** RJ11 plug length past the jack, cable diameter, and which edge they should leave by (the right edge is proposed).
9. **QT hub and sensors:** on the plate or loose? If on the plate: sizes, and foam tape or standoffs (record H1). Area proposed at front tile x 190-290, y 100-170.
10. **Labels:** engraved words (the 2 Nov `system.py` note says you asked for them) or blank recesses (the cards and this spec)?
11. **OLED Dupont reach:** moving board C back 26 mm makes L_OLED_VCC (C:c23 to TX CN7.16) an estimated 290-305 mm path against a 300 mm Dupont. W26-W30 come to about 270-285. The sketch must report both. If L_OLED_VCC exceeds 285, choose between 40 cm Duponts (the model's 300 mm lengths, build sheet lines 147-148, would change) and accepting it.
12. Back tile 220 deep (plate 300 × 408): acceptable?
13. Splice pocket: wanted, or hold the spare 222-413 loose for the short check window?
14. INA228 spots off by default (change 12): agreed?
15. The warm load (about 0.15 W at 38 mA) sits in front of the harness, under the X1 wire routes: acceptable?

### 7a. The user's answers (2026-11-02)

These override anything above that differs.

- **Item 9, QT hub and sensors:**
  - The QT hub stays plugged into a breadboard.
  - The STEMMA QT sensor modules get a **screw-down sensor deck** on the plate. The user also wants to be able to run a sensor off the plate on a longer QT cable. The wind and rain meters are separate: they plug in by RJ11 (item 8).
  - **Sensor deck:**
    - At least 100 × 70 mm, in the area proposed at front tile x 190-290, y 100-170, or wherever the layout fits it best.
    - It must take Adafruit and SparkFun breakouts whose hole spacing varies (mostly M2.5 holes on 0.1-inch multiples). So build it as **parallel T-slots that capture M2.5 nuts**, at least 4 slots about 15 mm apart, with the nuts sliding along them. Then any board can be screwed down on 8 mm M2.5 standoffs wherever its holes fall.
    - Each slot gets an open end so nuts can slide in, and a printed stop.
    - Put the slots in the coupon.
  - Give each QT cable an open tie point within 30 mm of the hub, and a jacket clamp where it leaves the plate edge, with room for at least 4 QT cables.
  - The deck is labelled "SENSORS".
- **Item 10, labels:**
  - **Everything is labelled with words.** That covers every board, connector, WAGO, cradle, cable lane and anchor group, plus the tile IDs.
  - Use words, not blank recesses, in a contrasting colour.
  - The tiles stay single-nozzle, so get the colour by a filament change at a layer: text raised 0.6 mm above the deck, or recessed and filled. Say which in the Bambu Studio settings.
  - Make the result the same on any machine: ship the font file with the project and load it by path, never a system font.
- **Item 11, OLED leads:** the user will make custom leads to whatever length the layout needs, so lead length does not limit where board C goes. Report each custom lead's length, for the cut list.
- **Item 12, plate size:** make the plate as large as the layout needs, as long as every tile prints on the Bambu H2D in its single-nozzle envelope (325 × 320 mm) with brim room. A third tile is allowed if needed. The no-fixed-part-across-a-joint rule then applies to every joint.
- **Still open:**
  - Item 1, orientation: the user has been shown the renders and has not confirmed yet.
  - Items 2-8 and 13-15.

## 8. Step 1b and the solar lead clamp

- Step 1b's three INA228s (load 0x41, solar 0x45, USB-C 0x48) go in a full-size breadboard on **the step 2 plate**, with three more lever connectors: LOAD (222-415), SOLAR_IN (222-413) and USB_IN (222-413). It runs after step 2's H01 run (record S1, line 164; lines 343-366, 793). So this plate only keeps a flat reserve (back tile x 207-296, local y 12-75), and the INA228 standoff spots are off (change 12).
- **What the solar clamp is for in step 1b:** the 6 V panel's own lead, never cut, ends in a 2.1 mm barrel plug. That plug goes into an Adafruit #368 jack-to-terminal adapter, then SOLAR_IN, the solar INA228 and an Adafruit #369 plug into the charger's DC jack (record lines 350-358).
  - The clamp grips the panel lead's jacket where it comes onto the plate, so a tug on the outdoor lead stops there and never reaches the #368 screw terminals or the charger's DC jack, which sits in breadboard B.
  - It also serves record P10's unmetered case, where the panel plugs straight into the DC jack.
  - Not used in step 1.

## 9. Deliverables

1. **A dimensioned top-view sketch of both tiles, for the user's approval before any rebuild.** It shows:
   - the joint line and every item of section 4, with column 1, column 63 and row a marked on each pocket;
   - the breakout overhangs, the OLED keep-out and the USB, DC and RJ11 plug envelopes;
   - an **anchor table** (mating, anchor id, distance) and a **reach table** (every lead in section 3c, estimated path and limit);
   - the open items it could not close.
2. Updated `front_tile.py`, `back_tile.py`, `system.py` (raised clamp, double-opening bridge), the cards with dated changelog entries, and `measurements.toml` (change 19). Every new dimension goes in the parameter block.
3. 3MF and STL for each tile, in both the normal and the light variant.
4. A clean `nurb check` on both tiles and on `board_for_weather`. The cards' AUTO blocks date from 30 Oct and predate the 2 Nov source edits, so regenerate them.
5. The section 6 coupon as its own part, 3MF and STL.
6. Bambu Studio settings per tile: orientation, supports, wall loops (at least 4 for rails, clamps and the joint), infill, and PETG plate and temperatures (brief line 53).

Do not print anything before the user approves the sketch and the coupon passes.
