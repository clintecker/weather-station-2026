# External openings in the printed base: build spec

This covers the holes through the base's walls: seven cable glands, one pressure vent and one SMA bulkhead for the
antenna. Every dimension is in mm. The positions come from `cage/cage.py` and the layout checks as of 4550f83, updated
for **enclosure 4** (audited 2026-11-17, `sheets/audit-enc4/`).

## Enclosure 4 as printed, and the two fixes asked for (2026-11-17)

Enclosure 4 (`~/Downloads/enclosure 4.stl`) differs from the table below as follows:

- **PG-7 holes are Ø13.0** as printed (not 12.0 undersize): fit the glands straight in, no reaming. Five of them:
  G1, G2, G3, G5, G6. **G7 is gone**: there is no spare now (solar + S1-S4 + wind + rain).
- **Both PG-9 holes were left out.** Fix 2: **put them back**, Ø15.5 at (Xb 98, Yb 25) and (98, 60), i.e. in the
  lid-centre frame Y −36.25, Z 28.0 and 63.0, through the bottom wall (X −87.75 to −84.75). Inside, each needs its
  **Ø24 keep-out from Zb 0 to 8**:
  - the right corner block's left face is at **Xb 106.85** for Zb 0 to 8 (enclosure 3 had it at about 110): take it
    back to **Xb ≥ 110** there;
  - a **1 mm land (Zb 0 to 1)** now covers the bottom wall's inside from about Xb 80 to the right wall: cut it away
    inside each Ø24, back to the 3.0 wall, so the locknut seats flat and the thread reaches.
- **The vent** is Ø12.46 at (50, 85), unchanged.
- **The SMA bulkhead moved** low in the right wall: **Yb 94.14, Zb 60.38**, Ø6.44, with a Ø14.2 inner nut seat
  (it was Yb 86.14, Zb 144.6 in enclosure 3). Section 2 below is updated.
- **Mounting:** the two pole lugs are replaced by **two mounting flanges** on the short ends, in the floor plane
  (Yb −3 to 3), Xb 31.75 to 91.75, reaching 28 past each end wall (to Zb −31 and 200.5), each with **two 3.45 × 13.95
  slots** at Xb 47.95 and 75.45 (centres Zb −18 and 187.5). Section 3 below is updated.

## Coordinate frame

This is the same frame as `backplane-mount-spec.md`. Look into the open base from the lid side, with the box hung as
on its pole (long side vertical, glands at the bottom):

- **Xb** runs from the inside face of the **left** wall toward the right wall. The inside width is 123.5.
- **Zb** runs from the inside face of the **bottom** wall upward. The inside length is 169.5.
- **Yb** runs from the inside face of the **floor** (the back, on the pole) toward the lid. The base–lid seam is at
  Yb 97.0.
- **Lid-centre frame** (`lid-rim-spec.md`, the CAD bot's): X = Zb − 84.75, **Y = 61.75 − Xb**, Z = Yb + 3.0. It is
  right-handed, so +Y is the **left** wall and −Y the right wall. This describes enclosure 2 **after** the mirror in
  `backplane-mount-spec.md` (step 0): the glands, the vent and the bulkhead move with that mirror, so G4 and G8 (the
  PG-9s) end up in the column nearest the right wall, and the SMA in the right wall.
- **Walls:** all of them are 3.0 thick. The outside faces are at Xb −3.0 / 126.5, Zb −3.0 / 172.5 and Yb −3.0.

## 1. Bottom wall: eight cable glands and the vent

Every hole's axis runs along Zb, through the bottom wall (Zb −3.0 to 0). Each position is given as (Xb, Yb): across
from the left inside wall, and out from the floor's inside face toward the lid. Seen from the lid, G1 is nearest the
left wall and G4 nearest the right; in the lid-centre frame the columns are at Y +35.75, +11.75, −12.25 and −36.25,
the rows at Z 28.0 and 63.0, and the vent at (Y +11.75, Z 88.0).

| # | Xb | Yb | Gland | Hole | Cable (suggested; the model doesn't fix the order) |
|---|---|---|---|---|---|
| G1 | 26.0 | 25.0 | PG-7 (Adafruit #762) | Ø13.0 (enclosure 4) | Solar panel (Voltaic P110), plug cut off |
| G2 | 50.0 | 25.0 | PG-7 | Ø13.0 | Sensor port S1 |
| G3 | 74.0 | 25.0 | PG-7 | Ø13.0 | Sensor port S2 |
| G4 | 98.0 | 25.0 | **PG-9** (Adafruit #761) | **Ø15.5** (fix 2: missing in enclosure 4) | Wind meter (flat cable) |
| G5 | 26.0 | 60.0 | PG-7 | Ø13.0 | Sensor port S3 |
| G6 | 50.0 | 60.0 | PG-7 | Ø13.0 | Sensor port S4 |
| ~~G7~~ | 74.0 | 60.0 | - | none (enclosure 4) | Removed: no spare |
| G8 | 98.0 | 60.0 | **PG-9** | **Ø15.5** (fix 2: missing in enclosure 4) | Rain gauge (flat cable) |
| V1 | 50.0 | 85.0 | M12 × 1.5 vent | Ø12.5 | Pressure-equalising vent (part not chosen yet) |

- **Pitch:** 24 across, 35 between the two rows. The closest locknuts (a PG-9 beside a PG-7) are 4.7 apart.
- **Panel:** keep the wall **flat and 3.0 thick** round each hole, inside and out.
  - **Outside seat:** a flat ring for the gland's sealing washer: Ø19 for a PG-7, Ø24 for a PG-9 and Ø16 for the vent. Leave
    no ribs, text or chamfers inside that ring.
  - **Inside seat:** the same flat ring for the locknut. Keep a **keep-out cylinder** clear above it: Ø19 (PG-7) or
    Ø24 (PG-9) going 8.0 up into the box (to Zb 8.0). Nothing printed goes there. The battery tray already sits
    above Zb 9.9.
- **Don't thicken the wall at the glands.** The current model draws 3 mm outside bosses ("nut flats"). On a 6 mm
  panel, a PG-7's short thread may leave the locknut too little to grip. Use a flat 3.0 wall unless the glands Clint
  has show more thread.
  - 📏 **Measure:** on one PG-7 and one PG-9, the threaded length from the underside of the body's hex to the end of
    the thread.
- **Hole finish:** enclosure 4 prints the PG-7 holes at Ø13.0, which takes the 11.5 thread without reaming; the PG-9
  holes Ø15.5. Remove all elephant's foot from the
  outside face, so the sealing washer seats flat.
- **Water:** the holes face down when the box is hung, so water drains away from them. Give every cable a drip loop
  below its gland outside. Don't put a drip lip or a recess round the holes, because they would hold water.

## 2. Right wall: the SMA antenna bulkhead

- **Position (enclosure 4, as printed):** the hole axis runs along Xb, through the **right** wall, at **Yb 94.14,
  Zb 60.38** (enclosure 3 had it at Yb 86.14, Zb 144.6, beside B3).
  - In the lid-centre frame of `lid-rim-spec.md`: X −24.37, on the **−Y wall**, Z 97.14.
- **Hole:** **Ø6.44** as printed, for an SMA bulkhead jack with a 1/4-36 thread; inner nut seat Ø14.2.
  - If Clint's bulkhead has a flat on its thread, make it a **D-hole**: Ø6.5 with a flat at **5.8 across** (2.9 from
    the centre). That stops it turning.
  - 📏 **Check on the real cable** (the Amphenol 135110 end with the threaded body and nut): the thread diameter,
    whether it has a flat, and the maximum panel thickness it takes. The 3.0 wall must be within that maximum.
- **Seats:** a flat spot-face **Ø14** outside, and **Ø14** inside for the 3/8-in hex nut (11.0 across corners) and its
  lock washer. Keep 2.0 clear all round inside: the corner block and the rim lip are close by.
- **Seal:** put an O-ring or a flat rubber washer under the outside flange, or a ring of silicone when you fit it.
- **The antenna:** the 916 MHz tilting whip (Linx ANT-916-CW-HWR-SMA) screws on outside and tilts to point **up**,
  because the box hangs with this wall at its side. Leave the outside of the right wall clear of anything in a
  **Ø40 × 20** zone round the hole axis, for the hinge and the swing.
- **Inside:** the coax runs from the radio's SMA on B3 (Zb about 140, through the right-angle adapter AD1) to this
  jack, bending right in front of the cards and down the right column (Xb 88-121) to Zb 60.
  - 📏 **[TBD] Cable length:** the run is about 120-130 mm; the 6-inch Amphenol 135110-01-06.00 has about 110 between
    its plugs. It is probably too short: check at Session 6, or get a longer one.
  - 📏 **[TBD] The EVM corner:** a straight plug on the jack's inner end reaches about Xb 93, about 6-10 mm above the
    EVM's lid-right corner (board to Xb 98.25, Yb 101.6). Check it clears at Session 6, or use a right-angle plug.

## 3. Other outside features (for reference: no holes through the wall)

- **Two mounting flanges (enclosure 4)**, replacing the pole lugs: on the short ends, in the floor plane (Yb −3 to
  3), Xb 31.75 to 91.75, 28 past each end wall; two 3.45 × 13.95 slots in each, at Xb 47.95 and 75.45 (centres Zb −18
  and 187.5), for hose clamps or straps. Nothing passes through the back wall.
- **Drip edge:** over the top wall at the lid seam, 2.0 proud and 6.0 deep.

## 4. Checks

1. Every hole lies at least 4.0 from any inside wall face, and from the lid seam's land.
2. No locknut keep-out cylinder (section 1) hits the pack tray, the charger ledges or another nut.
3. The SMA nut's Ø14 seat inside clears the upper-right corner block, the rim lip and the right corner post by 2.0.
4. The panel is 3.0 everywhere a gland or the bulkhead goes through.
5. **Leak test before fitting electronics:** fit every gland with a blanking plug, put the lid on, and spray the box
   (or submerge its bottom 20 mm) for 10 minutes. It should stay dry inside.

## 📏 To measure before printing

- **Each round cable's outside diameter.** A PG-7 seals 3.0–4.3: the solar lead and the four sensor-port cables.
- **The flat meter cables' width and thickness.** A PG-9 seals 4.0–6.4 round; flat cables get silicone or a split
  grommet.
- **The thread length of both gland sizes**, and the SMA bulkhead's thread and maximum panel thickness (sections 1
  and 2).
