# External openings in the printed base: build spec

This covers the holes through the base's walls. There are seven cable glands, one pressure vent and one SMA bulkhead
for the antenna. Every dimension is in mm. The positions come from `cage/cage.py` and `sources.py` as of 0772400 or
later. That's **enclosure 4** plus its fixes, audited on 2026-11-17 in `sheets/audit-enc4/`. The gland and vent
coordinates haven't changed since 4550f83.

## Enclosure 4 as printed, and the two fixes asked for (2026-11-17)

Enclosure 4 (`~/Downloads/enclosure 4.stl`) differs from the table below in these ways:

- **The PG-7 holes are Ø13.0** as printed, not 12.0 undersize. Fit the glands straight in, with no reaming. There are
  five of them: G1, G2, G3, G5 and G6. **G7 is gone**, so you have no spare now (solar + S1-S4 + wind + rain).
- **Both PG-9 holes were left out.** Fix 2 **puts them back**: Ø15.5 at (Xb 98, Yb 25) and (98, 60). In the
  lid-centre frame that's Y −36.25, Z 28.0 and 63.0, through the bottom wall (X −87.75 to −84.75). Inside, each one
  needs its **Ø24 keep-out from Zb 0 to 8**:
  - The right corner block's left face is at **Xb 106.85** for Zb 0 to 8. Enclosure 3 had it at about 110. Take it
    back to **Xb ≥ 110** there.
  - A **1 mm land (Zb 0 to 1)** now covers the inside of the bottom wall from about Xb 80 to the right wall. Cut it
    away inside each Ø24, back to the 3.0 wall, so the locknut seats flat and the thread reaches.
- **The vent** is Ø12.46 at (50, 85). It hasn't changed.
- **The SMA bulkhead moved** low in the right wall, to **Yb 94.14, Zb 60.38**. The hole is Ø6.44, with a Ø14.2 inner
  nut seat. Enclosure 3 had it at Yb 86.14, Zb 144.6. Section 2 below has the new numbers.
- **Mounting:** two **mounting flanges** on the short ends replace the two pole lugs. They sit in the floor plane
  (Yb −3 to 3), from Xb 31.75 to 91.75, and stick out 28 past each end wall (to Zb −31 and 200.5). Each flange has
  **two 3.45 × 13.95 slots** at Xb 47.95 and 75.45 (centres Zb −18 and 187.5). Section 3 below has the new numbers.

## Coordinate frame

This is the same frame as `backplane-mount-spec.md`. Look at the open base from the lid side, with the box hung as it
is on its pole (long side vertical, glands at the bottom):

- **Xb** runs from the lid frame's left edge. The frame is 123.5 wide, and we keep it for the lid, the sheets and the
  renders. Enclosure 4's inside faces are at Xb 1.25 (left wall) and 122.25 (right wall), so the real inside width
  is 121.0.
- **Zb** runs up from the lid frame's bottom edge. The frame is 169.5 long. Enclosure 4's inside faces are at Zb 1.0
  (bottom wall) and 168.5 (top wall), so the real inside length is 167.5.
- **Yb** runs from the floor's inside face (the back, on the pole) toward the lid. The base–lid seam (the wall top) is
  at Yb 117.0, and the sealing lip stands 2.5 above it.
- **Lid-centre frame** (`lid-rim-spec.md`, the CAD bot's): X = Zb − 84.75, **Y = 61.75 − Xb**, Z = Yb + 3.0. It's
  right-handed, so +Y is the **left** wall and −Y is the right wall. It describes enclosure 2 **after** the mirror in
  `backplane-mount-spec.md` (step 0). The glands, the vent and the bulkhead move with that mirror. So G4 and G8 (the
  PG-9s) end up in the column nearest the right wall, and the SMA ends up in the right wall.
- **Walls:** the floor is 3.0 thick. The long walls (left and right) are 4.25 and the short walls (bottom and top) are
  4.0. The outside faces are at Xb −3.0 / 126.5, Zb −3.0 / 172.5 and Yb −3.0.

## 1. Bottom wall: seven cable glands and the vent (eight grid positions, G7 left empty)

Every hole's axis runs along Zb, through the bottom wall (Zb −3.0 to 0). Each position is (Xb, Yb): across from the
left, and out from the floor's inside face toward the lid. Seen from the lid, G1 is nearest the left wall and G4 is
nearest the right. In the lid-centre frame the columns are at Y +35.75, +11.75, −12.25 and −36.25. The rows are at Z
28.0 and 63.0, and the vent is at (Y +11.75, Z 88.0).

| # | Xb | Yb | Gland | Hole | Cable (`cage.py` `GLAND_USE`) |
|---|---|---|---|---|---|
| G1 | 26.0 | 25.0 | PG-7 (Adafruit #762) | Ø13.0 (enclosure 4) | Sensor port S4 (spare: no pod yet, a 4 mm blanking rod in the seal, `cage.GLAND_BLANK`) |
| G2 | 50.0 | 25.0 | PG-7 | Ø13.0 | Sensor port S3 (baro) |
| G3 | 74.0 | 25.0 | PG-7 | Ø13.0 | Sensor port S2 (UV) |
| G4 | 98.0 | 25.0 | **PG-9** (Adafruit #761) | **Ø15.5** (fix 2: missing in enclosure 4) | Wind meter (flat cable) |
| G5 | 26.0 | 60.0 | PG-7 | Ø13.0 | Solar panel (Voltaic P110), plug cut off |
| G6 | 50.0 | 60.0 | PG-7 | Ø13.0 | Sensor port S1 (TH) |
| ~~G7~~ | 74.0 | 60.0 | - | none (enclosure 4) | Removed: no spare |
| G8 | 98.0 | 60.0 | **PG-9** | **Ø15.5** (fix 2: missing in enclosure 4) | Rain gauge (flat cable) |
| V1 | 50.0 | 85.0 | M12 × 1.5 vent | Ø12.5 | Pressure-equalising vent (part not chosen yet) |

- **Pitch:** 24 across and 35 between the two rows. The closest locknuts (a PG-9 beside a PG-7) are 4.7 apart.
- **Panel:** keep the wall **flat and 3.0 thick** round each hole, inside and out.
  - **Outside seat:** a flat ring for the gland's sealing washer. Make it Ø19 for a PG-7, Ø24 for a PG-9 and Ø16 for
    the vent. Don't put ribs, text or chamfers inside that ring.
  - **Inside seat:** the same flat ring for the locknut. Keep the space above it clear, as the model has it:
    - PG-9: a Ø24 keep-out up to Zb 8.0.
    - PG-7: the 16.6 locknut up to Zb 6.0 (the thread length L1), on a Ø19 × 1 mm land.
    - Nothing printed goes in these spaces. The battery tray already sits above Zb 9.9.
    - If you want a Ø19 keep-out up to Zb 8 as the PG-7 rule, add it to `cage.py`. The model doesn't have it yet.
- **Don't thicken the wall at the glands.** Enclosure 4 and the current model have no outside bosses. The bottom wall
  is 4.0, with 1 mm pockets inside that bring it to 3.0 at the holes. Don't add bosses. On a thicker panel, a PG-7's
  short thread may leave the locknut too little to grip. Keep the wall at 3.0 unless Clint's glands show more thread.
  - 📏 **Measure:** on one PG-7 and one PG-9, measure the threaded length from the underside of the body's hex to the
    end of the thread.
- **Hole finish:** enclosure 4 prints the PG-7 holes at Ø13.0, which takes the 11.5 thread without reaming. The PG-9
  holes are Ø15.5. Remove all elephant's foot from the outside face, so the sealing washer seats flat.
- **Water:** the holes face down when the box hangs, so water drains away from them. Give every cable a drip loop
  below its gland outside. Don't put a drip lip or a recess round the holes, because they'd hold water.

## 2. Right wall: the SMA antenna bulkhead

- **Position (enclosure 4, as printed):** the hole axis runs along Xb, through the **right** wall, at **Yb 94.14,
  Zb 60.38**. Enclosure 3 had it at Yb 86.14, Zb 144.6, beside B3.
  - In the lid-centre frame of `lid-rim-spec.md` it's at X −24.37, on the **−Y wall**, Z 97.14.
- **Hole:** **Ø6.44** as printed, for an SMA bulkhead jack with a 1/4-36 thread. The inner nut seat is Ø14.2.
  - If Clint's bulkhead has a flat on its thread, make it a **D-hole**: Ø6.5 with a flat at **5.8 across** (2.9 from
    the centre). That stops it turning. These numbers are a suggestion. Nothing in the model has a D-hole, and we
    haven't found a drawing for the 135110 jack. Check the hole size and the flat on the real jack before you add it.
  - 📏 **Check on the real cable** (the Amphenol 135110 end with the threaded body and nut): the thread diameter,
    whether it has a flat, and the maximum panel thickness it takes.
  - The panel at the SMA is 3.25: the 4.25 right wall less the 1.0 nut seat. It must be within the bulkhead's maximum
    panel thickness. Similar Amphenol jacks allow only about 2.5-3.2. Measure it, or make the seat deeper.
- **Seats as printed:** an inner nut seat Ø14.2, 1.0 deep into the right wall. There's no outside spot-face, so the
  outside is the plain wall.
  - The model sizes the nut as a 3/8 in hex (11.0 across corners), but nothing confirms the 135110 uses that nut.
    Common SMA bulkhead nuts are 5/16 in or 8 mm across flats (about 9.2 across corners). Measure the nut and its
    lock washer on the real cable.
  - Keep 2.0 clear all round the nut inside. At Zb 60 the nearest item is the right wall's own inside face (the fit
    check gives 2.05). The corner blocks and the lip aren't near it any more.
- **Seal (suggested):** put an O-ring or a flat rubber washer under the outside flange, or a ring of silicone when you
  fit it. No build step calls for a seal yet, so this is a suggestion, not a tested method.
- **The antenna:** AE1, a Taoglas TI.96.A113 (915 MHz dipole, IP67, 203 x 12.7, hinged SMA(M)), screws straight
  onto the jack outside. Its hinge folds it 90 degrees so it stands **vertical, tip up**, because the box hangs with
  this wall at its side. The whip's axis then sits about 22 mm out from the right wall's outside face and its tip
  about 70 mm above the box's top. No cable.
  - Keep the outside of the right wall clear in a **Ø40 × 20** zone round the hole axis, for the coupling nut, the
    hinge and the fold. The bonding lug (README, Lightning and surge) sits on the jack's thread under its nut, inside
    that zone.
- **Inside:** the coax runs from the radio's SMA on B3 (Zb about 140, through the right-angle adapter AD1) to this
  jack. It bends right in front of the cards and runs down the right column (Xb 88-121) to Zb 60.
  - **Cable length:** the run from AD1 to the low bulkhead is about 110 mm on the shortest path (model). Clint
    confirmed on 2026-11-17 that the 6 inch 135110-01-06.00 fits.
  - 📏 **[TBD] The EVM corner:** a straight plug on the jack's inner end reaches about Xb 93. That's about 6-10 mm
    above the EVM's lid-right corner (board to Xb 98.25, Yb 101.6). Check it clears at Session 6, or use a
    right-angle plug.

## 3. Other outside features (for reference: no holes through the wall)

- **Two mounting flanges (enclosure 4)** replace the pole lugs. They sit on the short ends, in the floor plane (Yb −3
  to 3), from Xb 31.75 to 91.75, and stick out 28 past each end wall. Each has two 3.45 × 13.95 slots, at Xb 47.95
  and 75.45 (centres Zb −18 and 187.5), for hose clamps or straps. Nothing passes through the back wall.
- **Drip edge:** enclosure 4 and the model don't have one. An earlier design had a drip edge over the top wall at the
  lid seam, 2.0 proud and 6.0 deep. Treat it as a proposed addition only.

## 4. Checks

1. Every hole lies at least 4.0 from any inside wall face, and from the lid seam's land.
2. No locknut keep-out (section 1) hits the pack tray, the charger ledges or another nut.
3. The SMA nut seat inside (Ø14.2 at Yb 94.14, Zb 60.38) clears everything by 2.0. The audit fit gives 2.05, with
   the nearest item on the right wall face.
4. The panel is 3.0 at the glands and the vent. It's 3.25 at the SMA bulkhead (the 4.25 long wall less the 1.0 nut
   seat).
5. **Leak test before you fit electronics (proposed):** fit every gland with a blanking plug and put the lid on. Spray
   the box, or submerge its bottom 20 mm, for 10 minutes. It should stay dry inside. No build step or evidence file
   records this test yet.

## 📏 To measure before printing

- **Each round cable's outside diameter.** A PG-7 seals 3.0–4.3: the solar lead and the four sensor-port cables.
- **The flat meter cables' width and thickness.** A PG-9 seals 4.0–6.4 round. Flat cables get silicone or a split
  grommet.
- **The thread length of both gland sizes**, and the SMA bulkhead's thread, nut size and maximum panel thickness
  (sections 1 and 2).
