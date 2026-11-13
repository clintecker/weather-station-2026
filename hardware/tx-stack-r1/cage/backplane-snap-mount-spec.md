# Backplane snap mount, for newer printed bases: build spec

This spec is for **new** bases only. The base Clint has already printed keeps its posts and screws (see
`backplane-mount-spec.md`).

**How the backplane goes in:**
1. Its left edge hooks into the groove in the left wall.
2. Its right edge presses down past two flexible snap hooks.
3. End stops fix it along its length.

There are no screws, no heat-set inserts and no sideways slide. Every dimension is in mm.

## Why not slide it in from the bottom end

The backplane is 99.06 long (Zb 50.25 to 149.31). To slide it along its length into grooves on both long edges, it
would need about 99 of clear groove below Zb 50.25. That run reaches past the bottom wall (Zb 0), and the charger
board and the pack also sit down there. So it doesn't fit.

## Coordinate frame

This is the same frame as `backplane-mount-spec.md`, looking into the open base from the lid side, hung as on the
pole:

- **Xb** runs from the inside face of the left wall to the right.
- **Zb** runs from the inside face of the bottom wall (the gland wall) upward.
- **Yb** runs from the inside face of the floor toward the lid.

## 1. The backplane (for reference: not printed)

- **Board:** a 21 × 39-hole piece of BusBoard PAD3U, 2.54 pitch, 1.6 thick, plain rectangular. It has **no tab and no
  drilled holes.**
- **Outline when seated:** Xb 6.51 to 59.85, Zb 50.25 to 149.31.
- **Faces:** the copper (back) face is at Yb 8.0 and the component (front) face at Yb 9.6.
- **Behind it:** the mux breakout on foam, at Xb 11.59 to 52.23, Zb 52.79 to 73.11.

## 2. Left edge: the groove (unchanged from the current model)

- **Where:** a groove in the left wall's slot-side face, and in the rail below the wall, along the board's whole
  left edge.
- **Section:** Xb 6.0 to 8.5, Yb 8.0 to 10.1, with a 45° roof rising from (Xb 6.0, Yb 10.1) to the wall face.
- **New requirement: tilt-in.** The board must be able to go in tilted. Its left edge goes into the groove with the
  board at about **15° to the floor** (right side up), then it swings down flat.
  - Check the swing by rotating the board's section about its left bottom corner inside the groove. It must not
    collide.
  - If it does, deepen the roof chamfer or raise the roof to Yb 10.6. The groove floor stays at Yb 8.0.

## 3. Under the board: support pads (replacing the screw posts)

- **Shape:** two round pads, **Ø7.0**, from the floor (Yb 0) to **Yb 8.0**, with an R1.0 fillet at the foot and **no
  bore.**
- **Positions:**
  - (Xb 58.58, Zb 54.06)
  - (Xb 58.58, Zb 140.42)
- **Job:** they carry the push when a card is plugged in. Along with the groove floor, they set the board at Yb 8.0.

## 4. Right edge: two snap hooks

Each hook is a horizontal arm running along Zb, held at one end by a stiff pillar. Its free end carries a lip that
reaches over the board's front face.

- **Why horizontal:** the base prints with Yb vertical. A horizontal arm bends within its print layers, which is
  strong. An upright arm would bend across its layers and crack.

| Part | Xb | Yb | Zb, lower hook | Zb, upper hook |
|---|---|---|---|---|
| Pillar (stiff root) | 61.65 to 64.65 | 0 to 12.6 | 58.0 to 62.0 | 136.0 to 140.0 |
| Arm (flexes in +Xb) | 60.15 to 61.65 (1.5 thick) | 9.7 to 12.6 (2.9 tall) | 62.0 to 82.0 (20 long) | 116.0 to 136.0 (20 long) |
| Lip, on the arm's free end | 59.15 to 60.15 (1.0 over the board) | 9.7 to 11.2 | 78.0 to 82.0 | 116.0 to 120.0 |

- **Arm direction:** the lower arm runs up from its pillar, and the upper arm runs down from its pillar. Both free
  ends point toward the board's middle.
- **The lip's underside:** flat, at Yb 9.7. That's 0.1 above the board's front face, so the board can't lift.
- **The lip's top:** a **45° lead-in ramp**, rising from (Xb 59.15, Yb 10.2) to (Xb 60.15, Yb 11.2). When the board's
  edge is pressed down onto the ramp, it pushes the arm out toward +Xb.
- **Arm clearance:**
  - 0.3 to the board's right edge (Xb 59.85 to 60.15).
  - At least 1.5 of clear space on the arm's +Xb side, along its whole length, so it can flex.
  - Nothing underneath the arm between Yb 0 and 9.7.
- **Flex check (PETG):**
  - deflection needed: 1.0 (the lip) + 0.2 = 1.2;
  - strain = 1.5 × 1.2 × 1.5 / 20² = **0.7 %**;
  - PETG allows about 2 % for repeated snaps, so the margin is good.
- **Printing:** the arm is a horizontal overhang. Print it on a small tree support, or a 0.2 mm-gap support block,
  under its full length, then remove the support. **Do not** join the arm to the floor.
- **Release:** push each lip out (+Xb) with a small screwdriver from the lid side, then lift the right side. This is
  only possible with every card out, because the cards cover the hooks.

## 5. Length stops (fix the board along Zb)

Two small blocks stand on the floor, one off each end of the board, away from the mux:

| Stop | Xb | Yb | Zb | Face |
|---|---|---|---|---|
| Bottom stop | 30.0 to 50.0 | 0 to 10.6 | 47.95 to 49.95 | 0.3 below the board's bottom edge |
| Top stop | 30.0 to 50.0 | 0 to 10.6 | 149.61 to 151.61 | 0.3 above the board's top edge |

- Give the top of each stop a **1.0 × 45° chamfer** on its face toward the board, as a lead-in.
- If the top stop runs into a card socket's solder joints or a card, move it along Xb to a clear place, or lower it to
  Yb 9.4 so it only catches the board's edge.

## 6. Removed from the current design

- All backplane screw posts and heat-set inserts.
- The fitting slide: lower 2.5 to the right, then slide left. The board now **tilts in**.
- The drilled holes in the board.

## 7. Checks

1. **Pads and groove floor:** the pad tops and the groove floor are all at Yb 8.0, flat to ±0.1.
2. **Tilt-in:** the board, tilted 15° about its left bottom edge inside the groove, swings flat without hitting
   anything.
3. **Hook flex:** the hooks' flex space is clear, at least 1.5 in +Xb along the whole arm.
4. **Hook clearance:**
   - Nothing on the board's front face lies under a lip. The board's line 20 is unused.
   - The lip clears the B4 socket's housing on lines 1–18. Line 18's pads stop at about Xb 54.4.
5. **Mux:** it clears the pads, the hooks and the stops by at least 0.5.
6. **Fit test:** print one hook and a 60 mm length of groove on a scrap plate first. Snap a board offcut in and out
   10 times. Nothing should crack or go loose.

## Assembly, for the build sheet

1. **Put it in:**
   - Hold the backplane at about 15°, right side up, component face toward the lid.
   - Slip its left edge into the groove.
   - Lower the right side until it rests on the two hooks' ramps.
   - Press down beside each hook until both click.
2. **Take it out (all cards out first):**
   - Push each hook's lip outward with a small screwdriver.
   - Lift the right side and draw the board out of the groove.
