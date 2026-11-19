# Backplane snap mount, for newer printed bases: build spec

> **Not used (2026-11-13):** enclosure 2 holds the backplane by two screws, the left groove and a slot in the right
> corner post (`backplane-mount-spec.md`, which lists what to change from this version). The hooks below were for the
> old 82.71 edge.

This spec was for **new** bases only. Clint's first printed base (three posts, groove in the wall only) isn't used
for the TX either. See the appendix of `backplane-mount-spec.md`.

**How the backplane goes in:**
1. Its left edge hooks into the groove in the left wall.
2. Its right edge presses down past two flexible snap hooks.
3. End stops fix it along its length.

There are no screws, no heat-set inserts and no sideways slide. Every dimension is in mm.

## Why not slide it in from the bottom end

The backplane is 99.6 long (Zb 48.71 to 148.31). Say you slid it along its length into grooves on both long edges.
You'd need about 99 of clear groove below the board's bottom edge. That run reaches past the bottom wall (Zb 0), and the
charger board and the pack sit down there too. So it doesn't fit.

## Coordinate frame

This is the same frame as `backplane-mount-spec.md`. You view the open base from the lid side, with the base hung
as it is on the pole:

- **Xb** runs from the inside face of the left wall to the right.
- **Zb** runs from the inside face of the bottom wall (the gland wall) upward.
- **Yb** runs from the inside face of the floor toward the lid.

## 1. The backplane (for reference: not printed)

- **Board:** a 31-line × 38-hole piece of the BusBoard PAD3U's plated end (lines 0 to 30, holes 1 to 38), 2.54 pitch,
  1.6 thick, plain rectangular. It has **no tab and no drilled holes.**
- **Outline when seated:** Xb 6.51 to 89.46, Zb 48.71 to 148.31 (83.0 × 99.6).
- **Front, right part:** B4's socket (hole 13) is 1x30 and runs to line 30 (Xb 83.98). Line 26 is at Xb 73.82.
  No lines are spare, because the 1x30 sockets use lines 1 to 30.
- **Faces:** the copper (back) face is at Yb 8.0 and the component (front) face is at Yb 9.6.
- **Behind it:** the mux breakout on foam, at Xb 11.59 to 52.23, Zb 52.79 to 73.11.

## 2. Left edge: the groove (unchanged from the current model)

- **Where:** a groove in the left wall's slot-side face (Xb 8.5) and in the rail below it. The rail runs down only to
  Zb 67.0, so the groove doesn't cover the board's whole left edge.
- **Section:** Xb 6.0 to 8.5, Yb 8.0 to 10.1, with a 45° roof from (Xb 6.0, Yb 10.1) up to the wall face.
- **New requirement: tilt-in.** The board must go in tilted. Its left edge goes into the groove with the board at
  about **15° to the floor** (right side up). Then it swings down flat.
  - To check the swing, rotate the board's section about its left bottom corner inside the groove. It must not
    collide.
  - If it collides, deepen the roof chamfer or raise the roof to Yb 10.6. The groove floor stays at Yb 8.0.

## 3. Under the board: support pads (replacing the screw posts)

- **Shape:** three round pads, **Ø7.0**, from the floor (Yb 0) to **Yb 8.0**, with an R1.0 fillet at the foot and
  **no bore.**
- **Positions:**
  - (Xb 58.58, Zb 54.06)
  - (Xb 58.58, Zb 140.42)
  - (Xb 78.90, Zb 82.00): line 28, hole 13. That's directly under XB4's contact 28 solder joint on the copper face,
    so a pad can't go there (see item 5 of `backplane-mount-spec.md`).
- Lines 27 to 29 carry no nets or bus wires. But every 1x30 socket (XB1 to XB4) has an isolated solder joint on
  them at holes 13, 19, 27 and 35.
- **Job:** the pads take the push when you plug in a card. They and the groove floor set the board at Yb 8.0.

## 4. Right edge: two snap hooks

Each hook is a horizontal arm that runs along Zb. A stiff pillar holds one end. The free end carries a lip that
reaches over the board's front face.

- **Why horizontal:** the base prints with Yb vertical. A horizontal arm bends within its print layers, which is
  strong. An upright arm would bend across its layers and crack.

| Part | Xb | Yb | Zb, lower hook | Zb, upper hook |
|---|---|---|---|---|
| Pillar (stiff root) | 84.21 to 85.80 (on the right corner post's face, or free-standing below it) | 0 to 12.6 | 58.0 to 62.0 | 136.0 to 140.0 |
| Arm (flexes in +Xb) | 83.01 to 84.21 (1.2 thick) | 9.7 to 12.6 (2.9 tall) | 62.0 to 82.0 (20 long) | 116.0 to 136.0 (20 long) |
| Lip, on the arm's free end | 82.01 to 83.01 (0.7 over the board) | 9.7 to 11.2 | 78.0 to 82.0 | 116.0 to 120.0 |

The numbers in this section are for the old 39-hole board, whose right edge was at Xb 82.71. The current board runs
to Xb 89.46, so it would sit over these hooks.

The hooks moved out to that board's right edge. On the old board, the gap from the right edge (Xb 82.71) to the right corner post (Xb 85.8, from Zb 72.73 up) was
only 3.09. So the arm is 1.2 thick, and its 1.5 of flex space ends at Xb 85.71, 0.09 short of the post. The upper
pillar joins the post's −Xb face and stays at Xb ≤ 85.8. So it never enters the post's card slots (Xb 85.8 to 88.1).
The lower pillar (Zb 58 to 62) stands on the floor below the post, which starts at Zb 72.73.

- **Arm direction:** the lower arm runs up from its pillar, and the upper arm runs down from its pillar. Both free
  ends point toward the board's middle.
- **The lip's underside:** flat, at Yb 9.7. That's 0.1 above the board's front face, so the board can't lift.
- **The lip's top:** a **45° lead-in ramp**, from (Xb 82.01, Yb 10.2) up to (Xb 83.01, Yb 11.2). When you press the
  board's edge down onto the ramp, the edge pushes the arm out toward +Xb.
- **Arm clearance:**
  - 0.3 to the board's right edge (Xb 82.71 to 83.01).
  - At least 1.5 of clear space on the arm's +Xb side, along its whole length, so it can flex.
  - Nothing under the arm between Yb 0 and 9.7.
- **Flex check (PETG):**
  - Deflection needed: 0.7 (the lip's overlap of the board) + 0.2 = 0.9.
  - Strain = 1.5 × 1.2 × 0.9 / 20² ≈ **0.41 %**. If you use the full 1.0 lip width (1.2 deflection) instead, you
    get 0.54 %, which is on the safe side.
  - We haven't got a PETG strain limit yet. Nothing in the repo gives one, and a web search found no PETG-specific
    figure. General snap-fit guides start from the datasheet's yield strain and derate it to about 60 % for
    repeated snaps. So look up the yield strain on your filament's datasheet before you trust this margin.
- **Print support:** the arm is a horizontal overhang. Print it on a small tree support, or a support block with a
  0.2 mm gap, under its full length. Then remove the support. **Do not** join the arm to the floor.
- **Release:** push each lip out (+Xb) with a small screwdriver from the lid side, then lift the right side.
- **Clash with the cards:** the hooks as specified take up the same space as the B4 card (Zb 79.13 to 80.73) and
  the B1 card (Zb 114.69 to 116.29). So you couldn't fit those cards with these hooks in place. Release needs at
  least B4 and B1 out. For the design to work, the hooks would have to move clear of the card slots.

## 5. Length stops (fix the board along Zb)

Two small blocks stand on the floor, one off each end of the board, away from the mux:

| Stop | Xb | Yb | Zb | Face |
|---|---|---|---|---|
| Bottom stop | 30.0 to 50.0 | 0 to 10.6 | 47.95 to 49.95 | 0.3 below the board's bottom edge |
| Top stop | 30.0 to 50.0 | 0 to 10.6 | 149.61 to 151.61 | 0.3 above the board's top edge |

The Zb numbers in this table are for the old board (Zb 50.25 to 149.31).

- Give the top of each stop a **1.0 × 45° chamfer** on its face toward the board, as a lead-in. This spec is the
  only place that asks for it. No base model in the repo has these stops, and `backplane-mount-spec.md` (change 2)
  removes them.
- The top stop might hit a card socket's solder joints or a card. If it does, move it along Xb to a clear place. Or
  lower it to Yb 9.4 so it only catches the board's edge.

## 6. Removed from the current design

- All backplane screw posts and heat-set inserts.
- The fitting slide: lower 2.5 to the right, then slide left. The board now **tilts in**.
- The drilled holes in the board.

## 7. Checks

1. **Pads and groove floor:** the pad tops and the groove floor are all at Yb 8.0, flat to ±0.1.
2. **Tilt-in:** tilt the board 15° about its left bottom edge inside the groove. It swings flat without hitting
   anything.
3. **Hook flex:** the hooks' flex space is clear, at least 1.5 in +Xb along the whole arm.
4. **Hook clearance** (written for the old board with a 1x26 B4 socket):
   - Nothing on the board's front face lies under a lip. On the old board, nothing used line 29. The 1x30 sockets
     now have joints on it.
   - The lip clears the B4 socket's housing on lines 1 to 26. The housing ended at Xb 75.09, 6.9 short of the lip.
5. **Mux:** it clears the pads, the hooks and the stops by at least 0.5.
6. **Fit test (planned, never run):** print one hook and a 60 mm length of groove on a scrap plate first. Snap a
   board offcut in and out 10 times. Nothing should crack or go loose. Nobody ran this test, because we dropped the snap
   mount (see the note at the top and changes 1 to 3 in `backplane-mount-spec.md`).

## Assembly, for the build sheet

1. **Put it in:**
   - Hold the backplane at about 15°, right side up, component face toward the lid.
   - Slip its left edge into the groove.
   - Lower the right side until it rests on the two hooks' ramps.
   - Press down beside each hook until both click.
2. **Take it out (all cards out first):**
   - Push each hook's lip outward with a small screwdriver.
   - Lift the right side and draw the board out of the groove.
