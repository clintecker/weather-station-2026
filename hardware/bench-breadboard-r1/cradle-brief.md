# Bench r1 cradle: brief for CAD

The cradle is a base plate for the whole breadboard bench of a solar LoRa weather station. It holds three
breadboards, two NUCLEO dev boards, a LiPo pack, a power-wiring island and five small STEMMA QT boards (a 5-port hub plus four sensor boards).
It's a development bench. It must stay open on top so you can reach and rewire every part. You must also be able to
carry it in one piece without parts or cables pulling loose.

The numbers below come from the layout data in `layout/build.py` as of 2026-11-04. Values marked
**[TBD-MEASURE]** are estimates. Leave margin around them, or make them parameters.

## 1. Frame and units

- Units are mm. The origin is the plate's **back-left corner** on the top surface.
- **x** runs right, **y** runs towards the **front** edge (the user's side), and **z** runs up from the plate's top surface.
- "Top-left" in the tables below means the corner with the smallest x and the smallest y.
- **Plate: 400 x 292 mm.** Thickness is your call. The plate must stay flat and stiff when you lift it from one side.
- Plates this size don't fit most printer beds. If you print the plate, split it into tiles and join
  them flat and rigidly. Never put a joint under a breadboard, a NUCLEO or a WAGO.

## 2. What sits on the plate

### 2.1 Breadboards (3 x Elegoo full-size, 830 points; adhesive backing)

| Board | Outline | Top-left (x, y) | Far corner (x, y) | Height |
|---|---|---|---|---|
| BB2 | 165.1 x 54.6 | (10.0, 5.0) | (175.1, 59.6) | 8.5 [TBD-MEASURE] |
| BB1 | 165.1 x 54.6 | (10.0, 100.0) | (175.1, 154.6) | 8.5 |
| BB3 | 165.1 x 54.6 | (10.0, 230.0) | (175.1, 284.6) | 8.5 |

- Set each board's position with a shallow pocket or low corner stops, with about 0.5 mm clearance per side.
- Keep any such feature **≤ 2 mm tall** on the edges that modules overhang (section 2.2). Those modules sit just above the board top.
- The boards' own adhesive or double-sided tape holds them down. They must also lift out for rework, so don't make the pocket a press-fit.
- **[TBD-MEASURE]:** the outline is the nominal Elegoo size. Measure one board before you finalise the pockets.

### 2.2 Modules that overhang a breadboard edge (no walls or tall features under them)

These modules plug into the breadboards. Their PCBs overhang the board edge with the underside at about z = 11
(8.5 board + 2.5 header plastic). Parts on top reach higher, up to about z 21 for the INA228 terminal blocks.
The plate under them must stay clear up to z ≈ 8.

| Part | What | Overhang footprint (x0, y0) to (x1, y1) | Over which edge |
|---|---|---|---|
| U2-U6 | four INA228 boards + MAX17048 gauge, in a row | (11, 43.7) to (148.5, 64.1) | BB2 front edge (y 59.6); their screw terminals face the power island |
| U1 | bq24074 charger | (64.6, 82.8) to (102.7, 115.8) | BB1 back edge (y 100) |
| P1, P2 | USB-C plug and barrel plug, plugged into the charger's side | (34.6, 86.6) to (64.6, 112.7) | hover beside U1, same height |
| DS1 | OLED, 85 x 58 | (5.6, 187.8) to (90.6, 245.8) | BB3 back edge (y 230); **two M2.5 standoffs under its far edge** (near y ≈ 190, x ≈ 8 and ≈ 88) [TBD-MEASURE: hole positions and height ≈ 8.5 + header height] |
| J1, J2 | RJ11 jack breakouts | J1 (112.2, 269.4) to (133.8, 289.9); J2 (140.2, 269.4) to (161.8, 289.9) | BB3 front edge (y 284.6); jacks open towards the front edge |

### 2.3 Parts mounted on the plate

| Ref | Part | Outline | Top-left (x, y) | Mount |
|---|---|---|---|---|
| A1 | NUCLEO-WL55JC1 (TX), turned 90° | 64.5 x 70.0 | (105, 158) to (169.5, 228) | **no mounting holes**: 4 corner ledges + snap lips (below); PCB underside at z = 10 |
| A2 | NUCLEO-WL55JC1 (RX), turned 180° | 70.0 x 64.5 | (322, 5) to (392, 69.5) | **no mounting holes**: 4 corner ledges + snap lips (below); PCB underside at z = 10 |
| BT1 | LiPo pack, Adafruit #353 (1S3P 6600 mAh) | 69 x 54 | (186, 40) | cradle or strap pocket; thickness 18 (Adafruit #353; `sources.py` 'sourced') [TBD-MEASURE: check the pack in hand]; must lift out without tools |
| U8 | QT 5-port hub | 25.4 x 17.8 | (186, 118) | 2 x M2.5 at (188.54, 120.54), (208.86, 120.54); z = 6 |
| U9 | SHT45 | 25.4 x 17.8 | (216, 118) | 2 x M2.5 at (218.54, 120.54), (238.86, 120.54) |
| U10 | SHTC3 | 25.4 x 17.8 | (246, 118) | 2 x M2.5 at (248.54, 120.54), (268.86, 120.54) |
| U11 | BMP581 | 25.4 x 17.8 | (216, 143) | 2 x M2.5 at (218.54, 145.54), (238.86, 145.54) |
| U12 | LTR390 (UV/light, faces up) | 25.4 x 17.8 | (246, 143) | 2 x M2.5 at (248.54, 145.54), (268.86, 145.54) |
| WG1 | WAGO 222-413 (3-way) | 17.0 x 20.5 | (104, 68) | WAGO holder or clip; wire entries face BB2 (−y) |
| WG2 | WAGO 222-415 (5-way) | 26.6 x 20.5 | (123, 68) | holder; entries face BB1 (+y) |
| WG3 | WAGO 222-415 (5-way) | 26.6 x 20.5 | (151.6, 68) | holder; entries face BB1 (+y) |
| J4 | Adafruit #368 barrel jack to screw terminal | 30 x 15 | (1, 84.8) | clip; the solar panel plug enters from the left edge at y ≈ 92 (zip-tie ear, section 3.1) |
| J3 | Adafruit #4090 USB-C female breakout, turned 90° | 14.0 x 20.3 | (6, 64.3) | 2 x M2.5 standoffs [TBD-MEASURE: hole positions]; the USB-C cable enters from the left at y ≈ 74.5; keep x < 6 clear around y ≈ 74.5 for the adapter's plug [TBD-MEASURE: plug length, still open in `hardware/base-plate/spec-r2.md`] |
| R9 | test load, 50 W 100 Ω aluminium-housed (marked 50W100RJ) | 62 x 30 incl. terminals and tabs (housing 50 x 15, 15 tall) | (262, 80) | flat pad, 2 x M3 (heat-set inserts or self-tapping) for its 3 mm tab holes, at plate **(273, 107.5)** and **(313, 82.5)**: 40 mm apart along x, 25 mm across, diagonally opposite corners (measured 2026-11-04); its terminals stick out 6 mm past each housing end at z ≈ 7.5; under 0.2 W, no heatsinking |

- **STEMMA QT boards (U8-U12):** each board has four M2.5 holes, 2.54 mm (0.1 in) in from each edge and 20.32 mm (0.8 in) apart.
  The plate uses two of them. The hole x values in the table are board x + 2.54 and + 22.86.
- **NUCLEO corner ledges (the boards have no mounting holes, confirmed 2026-11-04):** put one L-shaped post at each
  PCB corner. The PCB corner rests on a ledge about 3 mm wide, with its top at z = 10. The post's wall stands
  0.3 mm outside the PCB edge. A small flexible lip snaps over the top face.
- We assume the PCB is 1.6 mm thick, the usual value, but nobody measured it yet [TBD-MEASURE]. That puts the lip's
  underside at z ≈ 11.7, and the lip overlaps the PCB by about 1.5 mm. You must be able to lift the board out when you flex the lips.
- Keep each lip's footprint on the PCB within about 3 x 3 mm of the corner.
  Keep it clear of header pins [TBD-MEASURE: check what sits at each corner on the board].
- The TX board takes Dupont wires from above, so the ledges carry the push-in force. Make them stiff.
- **Morpho pins under the NUCLEO:** the morpho pins (CN7, CN10) stick out below the NUCLEO by several mm. They take a
  standard female socket [TBD-MEASURE: underside pin length]. Under the two morpho rows, keep the plate below
  z = 10 − pin length − 1, or cut slots there, or raise the ledge. The earlier cradle used a 14.0 ledge.
- **Free space:** most of the plate right of x = 275 and front of y = 115 is empty (R9 now takes x 262-324, y 80-110). That's a good place for cable-tie anchors, a tool or jumper-cap tray, and a label area.

## 3. Cable routing needs

### 3.1 Cables entering from outside (they need strain relief at the plate edge)

A pull on any of these cables must stop at the plate, not at a part plugged into a breadboard.

| Cable | Enters at | Lands on | Notes |
|---|---|---|---|
| Solar panel lead (5.5/2.1 barrel plug) | **left edge**, y ≈ 92 | J4 at (1, 92.3) | stiff, can be heavy: **clamp ear outside the left edge**, centred on y ≈ 92, zip-tie slot about 10 mm out; keep J4's two straps too |
| USB-C wall adapter cable | **left edge**, y ≈ 74.5 | J3 at (6, 74.5) | sits beside the solar plug (J3 above J4); optional small zip-tie ear at y ≈ 74 |
| Wind cable (RJ11) | **front edge**, x ≈ 123 | J1 jack at (112-134, 290) | J1 is only a breadboard-seated breakout, so a tug unseats it. Clamp the cable at the front edge, 2 mm in front of the jack |
| Rain cable (RJ11) | **front edge**, x ≈ 151 | J2 jack at (140-162, 290) | same clamp |
| TX ST-LINK USB (micro-USB, to the Mac) | A1's right side, at (169.5, 193), pointing +x | A1 | plugged in during both modes; route it right, then to the back edge |
| RX ST-LINK USB | **back edge**, at (357, 5) | A2 | straight out of the back edge |

- **Decided (2026-11-04):** the adapter enters from the left edge (J3 above J4), not the back edge.
- The RX ST-LINK cable leaves from the back edge. The TX one leaves A1's right side, so give it clips towards the back edge.

### 3.2 Antennas

- **A1 (TX):** the SMA jack is on A1's left side at (105, 193) and points −x. That's over the OLED's back half (DS1 reaches x = 90.6).
- **A2 (RX):** the SMA jack is on its front side at (357, 69.5) and points +y.
- Both boards carry ST's supplied LPRS ANT-SS900 antenna, glued to the SMA (UM2592 Rev 4) [TBD-MEASURE: shape and if it tilts].
  Keep a 360° swing clear around each SMA above z ≈ 15, with no tall walls nearby.

### 3.3 Wires running in the open above the plate (keep their paths clear, give them anchors)

| Bundle | Path | Count | Anchor |
|---|---|---|---|
| Dupont jumpers BB1 → A1 | from BB1 holes at y 118-149 (x 51-145, both halves) to A1's headers at y 170 and 216 (x 108-140) | 9 | one adhesive cable clip or tie point beside A1, near (100, 160) or (172, 160) |
| Dupont jumpers BB3 → A1 | from BB3 holes at y 248-279 (x 40-152: both halves and the front rails) to A1's headers at y 161-222.5 (x 108-142) | 11 | one clip near (172, 228) |
| QT sensor branch (W2) | BB1 near (140-150, 135) → hub U8 (186, 127) | 1 cable | lies across the gap between BB1 and the hub |
| QT hub → four sensors | U8 → U9 to U12, within x 186-272, y 118-161 | 4 short cables | none needed |
| QT power branch (W3) | BB1 (≈ 145, 135) → U3 on BB2 (148, 54), over the power island | 1 cable, 150 mm (fits: it needs about 103 mm by `build.py`'s estimate and about 129 mm along the routed path) | one clip at the island's right end, near (180, 95) |
| QT chain along BB2 | U3 → U2 → U6 → U5 → U4, along y ≈ 55 | 4 short cables | none |

- These wires drape over the boards from about z 9 up to about z 35. The Dupont housings over A1's sockets reach about 35 mm.
- Nothing on the plate in these zones should be taller than the breadboards (z = 8.5), except A1's corner posts.
- The gaps between the boards and A1 are small. BB1's front edge to A1 is only 3.4 mm, and A1 to BB3's back edge is 2 mm. So the wires go over the gaps, not through them.

### 3.4 The power island (y 59.6 to 100, x 0 to 180): force current up to 1.5 A

Short, stiff 20 AWG leads, JST PH pigtails and 22 AWG soldered leads join these parts:
- the WAGOs
- the INA228 screw terminals (on BB2's front edge, towards the island)
- the charger's side sockets
- J3/J4
- the pack lead.

Most island leads are 20-60 mm. The longer ones: the J3-P1 GND solder lead is about 77 mm, and the regulator lead is about 85 mm.
R9's own leads reach the WAGOs at about 120 and 230 mm.

- Keep this zone **flat and open**: no posts or ribs between the WAGOs and BB2/BB1. Leads cross it freely.
- The WAGO levers must open fully. We don't know the open-lever height yet [TBD-MEASURE]. WAGO's data gives 14.5 mm tall with the levers closed, so leave clear space above that.
- **Pack lead:** the pack (BT1, at x 186-255) has a 100 mm lead whose plug ends near (127-131, 95). Give it a clip or channel along y ≈ 95 from the pack to the WAGOs.
- **NTC thermistor:** its bead is taped to the pack, and its leads run about 160 mm to BB1 holes c38/c39, near (75, 118). Give it a small clip on the way.

## 4. Things that must stay reachable from above

- The jumper cap. It moves between A1's JP4 and the BATTERY link (JP1) at BB1 h18/h19, near (124-127, 136), when the bench changes mode.
- The OLED link on BB3.
- The WAGO levers.
- Both NUCLEO reset buttons.
- The pack must lift out without tools.
- All three breadboards must accept new wires from above anywhere on their surface.

## 5. Board names (wanted)

Emboss the names 0.6 mm high and about 6 mm tall. Build the letters from straight segments (a single-stroke font of your own),
so they don't depend on a machine's fonts.

| Name | Where |
|---|---|
| BB2 | the 10 mm strip left of its board: x 1-9, y ≈ 20-45, turned 90° |
| BB1 | same strip, y ≈ 115-140, turned 90° |
| BB3 | same strip, y ≈ 245-270, turned 90° (partly under the OLED: fine) |
| TX | right of A1, about x 171-184, y 163-180 (clear of A1's USB at y 185-200) |
| RX | below A2, about x 325-340, y 73-80 (clear of A2's antenna at x 357) |

## 6. Nice to have (your call)

- Feet or a rim underneath so cables can pass under the plate edges.
- Two hand grips on the left and right edges.
- Front-edge marker (the triangle).
- A shallow tray in the empty right-front area for spare jumpers and the cap.
