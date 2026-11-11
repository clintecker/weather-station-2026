# Backplane mount: build spec (printed TX base, floor posts)

The backplane is a piece of BusBoard PAD3U padboard. It stands 8 mm off the base's inside floor on printed posts with
M3 heat-set inserts. The cards plug into its sockets from the lid side. Every dimension is in mm. The numbers come from
`layout/stack.py` and `cage/cage.py` as of 7d5fc82.

## Coordinate frame

The **box frame** is the one `cage.py` uses, looking into the open base from the lid side, hung as on the pole:

- **Xb** runs from the inside face of the **left** wall toward the right wall. The inside width is 123.5.
- **Zb** runs from the inside face of the **bottom** wall (the one with the glands) toward the top wall. The inside
  length is 169.5.
- **Yb** runs from the inside face of the **floor** (the back as hung) toward the lid. The floor is 3.0 thick, so
  Yb 0 is 3.0 above the outside of the back.

The lid-centre frame of `lid-rim-spec.md` is also given: X = Zb − 84.75 (positive toward the top wall) and
Y = Xb − 61.75 (positive toward the right wall).

## 1. The backplane (for reference: not printed)

- **Board:** PAD3U cut 21 lines × 39 holes, 2.54 pitch, 1.6 thick. Lines run along Zb.
- **Outline:** Xb 6.51 to 59.85, Zb 50.25 to 149.31.
- **Copper (back) face** at Yb 8.0, against the posts. The component face is at Yb 9.6.
- **Behind it, on the copper face:** the mux breakout on foam, at Xb 11.59 to 52.23, Zb 52.79 to 73.11, inside the
  8 mm gap. Bus wires run along lines 1 to 18 (Xb 10.32 to 53.50).

## 2. Posts: three screw posts

| Post | Xb | Zb | X | Y | From the inside walls |
|---|---|---|---|---|---|
| Bottom left | 7.78 | 54.06 | −30.69 | −53.97 | 7.78 from left, 54.06 from bottom |
| Bottom right | 58.58 | 54.06 | −30.69 | −3.17 | 64.92 from right, 54.06 from bottom |
| Top right | 58.58 | 140.42 | +55.67 | −3.17 | 64.92 from right, 29.08 from top |

- **Spacing:** 50.80 across (20 holes) and 86.36 along (34 holes). These are the board's line 0 / line 20, holes 2 / 36.
- **Post:** a round boss **Ø7.0**, from the floor (Yb 0) to a flat top at **Yb 8.0**, with an R1.0 fillet at its foot.
- **Bottom-left only:** cut a flat on the boss's +Xb side, **3.1 from its centre** (at Xb 10.88). This leaves 0.7 to
  the mux breakout.
- **Insert bore:** **Ø4.0 × 6.5 deep** from the post top, for an M3 × 5.7 heat-set insert. It's a blind hole, with
  1.5 of post left under it.
- **Screws:** M3 × 6 button head (ISO 7380), no washer, through 3.2 holes drilled in the board.

**Why Ø7 and not bigger:** on the right posts, Ø7 clears line 18's pads by 0.7. On the bottom-left post, it clears
the mux.

## 3. Top left: a groove, not a post

A screw at the fourth corner (Xb 7.78, Zb 140.42) won't work, for two reasons:

- The left wall's slot side fills Xb 6.5 to 8.5 from the floor up for Zb 72.73 to 150.61. The board's left 2 mm and
  that screw are inside the wall.
- The screw's head would hit B3's socket at hole 35.

Instead, the board's left edge sits in a **groove** in the left wall:

- **Where:** in the wall's slot-side face (the face at Xb 8.5), for the wall's full length, Zb 72.73 to 150.61
  (X −12.02 to +65.86).
- **Section:** Xb 6.0 to 8.5 (2.5 deep, with 0.5 clearance past the board's edge), Yb 8.0 to 10.1.
- **Floor:** the groove floor is at **Yb 8.0**, level with the post tops. It holds up the board's left edge along
  the whole wall.
- **Roof:** it may be a 45° chamfer, rising from (Xb 6.0, Yb 10.1) to the wall face, so it prints without support.
- **No post at top left.**

**To fit the board:** lower it onto the posts 2.5 to the right (+Xb), then slide it left into the groove. Then drive
the three screws. The mux moves with it and clears the bottom-left flat in both positions.

## 4. Checks

- The post tops and the groove floor are all at Yb 8.0, flat to ±0.1.
- Every post centre falls on a board hole, on the 2.54 grid listed above.
- Nothing printed lies inside the board outline at Yb above 8.0, except the groove roof over the board's left 2 mm.
- The board has 2.5 of free travel to the right before anything stops it (the right corner post is at Xb 85.8).

## 5. Measure before printing

- **Heat-set insert:** its length and its largest (knurl) diameter, with calipers. The bore above assumes 5.7 long
  and about 4.6 across the knurl. If yours differ, make the bore the knurl diameter minus 0.6 and the length plus 0.8.
