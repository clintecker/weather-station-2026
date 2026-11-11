# Lid rim test ring: build spec (TIBOX DS-AT-1217 / Adafruit #905 lid)

The goal is a printed ring that the box's original clear lid presses onto. A raised lip on the ring sits in the lid's
O-ring channel all the way round, and four screw holes line up with the lid's corner holes. Every dimension is in mm.

## Where the numbers come from

- **Scale:** two 300 dpi flatbed scans of the lid, face-down with a steel ruler (2026-11-11). The ruler's metric and
  inch edges both give 11.953 px/mm, agreeing to 0.01%.
- **Accuracy:** the lip path is good to ±0.3 mm. The overall spans are good to ±0.4 mm.
- **Holes:** the screw-hole spacing comes from the maker's table (DS-AT-1217: H3 157, W3 109, ±1) and Clint's tape
  (155 × 108–110). It can't be read from the scan.
- **Earlier test prints:** Clint printed coupons r1–r8. r8 fitted closely and needed a rounder middle bend; the scan
  measures that bend at R7.15.

## Coordinate frame

- Origin at the **centre of the lid**.
- **X** runs along the long side (175), **Y** along the short side (130), and **Z** points up from the ring's
  underside (the print bed).
- The part is **symmetric about both the X and Y axes**. Model one quadrant (X ≥ 0, Y ≥ 0) and mirror it twice.

## 1. Outline (outer edge = the lid's outer edge)

- Rectangle **175.5 × 129.5**, centred on the origin.
- Corners rounded **R4**. This radius wasn't measured from the scan; r1–r8 used R4 without complaint.

## 2. Lip centre line: one closed path

Build the first quadrant from the segments below, in order. The path runs anticlockwise, starting on the +X short
side at Y = 0. Every arc is tangent to the lines on either side of it.

| # | Segment | From | To | Notes |
|---|---|---|---|---|
| 1 | line | (84.75, 0) | (84.75, 42.60) | straight lip along the short side |
| 2 | arc R3.5, turning left (CCW) | (84.75, 42.60) | (81.25, 46.10) | centre (81.25, 42.60): **outer bend** |
| 3 | line | (81.25, 46.10) | (76.50, 46.10) | first middle run, 4.75 straight |
| 4 | arc R7.15, turning right (CW) | (76.50, 46.10) | (69.35, 53.25) | centre (76.50, 53.25): **middle bend** round the boss |
| 5 | line | (69.35, 53.25) | (69.35, 58.00) | second middle run, 4.75 straight |
| 6 | arc R3.5, turning left (CCW) | (69.35, 58.00) | (65.85, 61.50) | centre (65.85, 58.00): **outer bend** |
| 7 | line | (65.85, 61.50) | (0, 61.50) | straight lip along the long side |

Mirror the quadrant about the Y axis and then about the X axis to close the loop.

**Checks for the path:**

- **Spans, centre line to centre line:** the straight lips are 169.5 apart along X and 123.0 apart along Y.
- **Inset:** the straight lip sits 3.25 in from the outer edge (scan: 3.15–3.36).
- **S depth:** each middle run is 15.4 in from its parallel straight lip (scan: 15.1–15.6 at all four corners).
- **Middle bend:** R7.15 on the centre line (scan: 7.14–7.16 at all four corners).
- **Outer bends:** R3.5 (scan: 3.0–4.0).

## 3. Lip (sweep this profile along the centre line)

- **Section:** 2.0 wide (±1.0 either side of the centre line) × 4.5 tall, square-topped.
- **Position:** the lip stands on top of the land, from Z 3.5 to Z 8.0.
- **Top edges:** optional 0.4 chamfer on both, for a lead-in.

## 4. Land (the flat base the lip stands on)

- **Thickness:** Z 0 to 3.5.
- **Extent:** from the outer outline (section 1) inward to the lip's **inner** face, that is the centre line offset
  1.0 toward the lid centre. **There is no land inside the lip.** The middle of the ring is open.
- **Corner pockets:** the land between the outline and the lip fills each corner pocket completely (the area around
  the screw hole, outside the S).

## 5. Screw holes

- **Size and number:** Ø7.0 through-holes, 4 of them.
- **Centres:** (±78.0, ±54.5). That's 156 apart along X and 109 apart along Y.
  - Along X, 156 is the midpoint of Clint's 155 and the maker's 157.
  - A Ø7 hole passes an M4 screw even if the true spacing is ±1 off.
- **Clearance:** each hole sits centred in its corner pocket, with at least 2.2 of plastic to the lip.

## 6. Print notes

- **Size:** about 175.5 × 129.5 × 8. It fits the Bambu H2D bed flat.
- **Orientation:** land on the bed, no supports.
- **Material:** PETG.

## What to check on the lid

1. Does the lip drop into the O-ring channel all the way round, including all four S-curves?
2. Do all four holes line up at the same time?
3. Is the ring's outer edge flush with the lid's edge on all four sides?
