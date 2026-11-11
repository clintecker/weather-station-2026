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
- **Behind it, on the copper face:** the mux breakout on foam, at **Xb 11.59 to 52.23**, Zb 52.79 to 73.11, inside
  the 8 mm gap. It can't move right: during the fitting slide (section 3) its right edge passes 0.35 from the
  bottom-right post. Bus wires run along lines 1 to 18 (Xb 10.32 to 53.50).

## 2. Posts: three screw posts

| Post | Xb | Zb | X | Y | From the inside walls |
|---|---|---|---|---|---|
| Bottom left | 7.78 | 54.06 | −30.69 | −53.97 | 7.78 from left, 54.06 from bottom |
| Bottom right | 58.58 | 54.06 | −30.69 | −3.17 | 64.92 from right, 54.06 from bottom |
| Top right | 58.58 | 140.42 | +55.67 | −3.17 | 64.92 from right, 29.08 from top |

- **Spacing:** 50.80 across (20 holes) and 86.36 along (34 holes). These are the board's line 0 / line 20, holes 2 / 36.
- **Post:** a round boss, from the floor (Yb 0) to a flat top at **Yb 8.0**, with an R1.0 fillet at its foot.
  - **Bottom left: Ø8.0, with a flat on its +Xb side 3.5 from its centre** (at Xb 11.28). That leaves 1.2 round the
    knurl on the flat side (the same as the right posts), 1.7 elsewhere, and 0.3 to the mux.
  - **Bottom right and top right: Ø7.0.** That leaves 1.2 round the knurl.
- **Insert bore:** **Ø4.0 × 6.5 deep** from the post top, for an M3 × 5.7 heat-set insert. It's a blind hole, with
  1.5 of post left under it.
- **Screws:** M3 × 6 button head (ISO 7380), no washer, through 3.2 holes drilled in the board.

**Why the right posts are Ø7:** at Ø7 they clear line 18's pads by 0.7. Press their inserts slowly, with the iron a
little cooler.

## 3. Top left: a groove, not a post

A screw at the fourth corner (Xb 7.78, Zb 140.42) won't work, for two reasons:

- The left wall's slot side fills Xb 6.5 to 8.5 from the floor up for Zb 72.73 to 150.61. The board's left 2 mm and
  that screw are inside the wall.
- The screw's head would hit B3's socket at hole 35.

Instead, the board's left edge sits in a **groove** in the left wall (section 6). If you've built a stand-in rail
because your box has no wall, move the groove into the section 6 wall:

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

## 6. Card guides: the left wall, the right corner post and the retention bar

The four cards (B4, B2, B1, B3, from bottom to top) are SolderFul boards, **81.3 wide** (along Xb) and **1.6 thick**.
They lie flat, parallel to the bottom wall, and slide toward the floor (−Yb) until their headers seat in the
backplane's sockets. Each card's left edge runs in a slot in the left wall. Its back-right corner runs in a slot in
the right corner post. All of this is moulded into the base, standing on the floor.

**Card slots:** every slot is 1.9 tall along Zb (the card's 1.6 plus 0.3 of clearance). Each runs from Yb 9.6 to the
part's front face.

| Card | Card's top face, Zb | Slot, Zb |
|---|---|---|
| B4 | 80.73 | 78.98 to 80.88 |
| B2 | 95.97 | 94.22 to 96.12 |
| B1 | 116.29 | 114.54 to 116.44 |
| B3 | 136.61 | 134.86 to 136.76 |

**Left wall:** a solid block from Xb 0 (on the base's left wall) to Xb 8.5, Yb 0 to 63.37, Zb 72.73 to 150.61.

- **Card slots:** cut into its +Xb face (the face at Xb 8.5), **2.0 deep** (Xb 6.5 to 8.5), from Yb 9.6 to 63.37.
- **Backplane groove:** the groove from section 3 is also cut into that face.
- **Retention-bar inserts:** two M3 × 5.7 heat-set inserts in its front face (Yb 63.37), at Xb 3.25 and Zb 76.0 and
  147.0. Each bore is Ø4.0 × 6.5 deep. *These positions are my call; the model doesn't fix them yet.*

**Right corner post:** a block Xb 85.8 to 93.8, Yb 0 to 21.96, Zb 72.73 to 150.61.

- **Card slots:** cut into its −Xb face (the face at Xb 85.8), **2.3 deep** (Xb 85.8 to 88.1), from Yb 9.6 to
  22.06, which is through its front.
- **Cut-backs:** above B2 and above B1, the post stops at **Yb 15.15** over the full post width. This clears the
  cards' back breakouts and plugs.

  | Above | Zb |
  |---|---|
  | B2 | 95.97 to 112.54 |
  | B1 | 116.29 to 132.86 |

**Retention bar:** a separate printed part, 12.0 (Xb 0 to 12.0) × 2.5 (Yb 63.37 to 65.87) × 77.88 (Zb 72.73 to
150.61). It sits flat on the left wall's front face.

- It screws to the left wall's front face, with Ø3.4 clearance holes at the two insert positions above.
- It covers each card's front-left corner, so no card can slide out.
- 1.0 is left between the bar and the cards' front edges (Yb 62.37). The sockets' pins engage far deeper than that.

## 5. Measure before printing

- **Heat-set insert:** its length and its largest (knurl) diameter, with calipers. The bore above assumes 5.7 long
  and about 4.6 across the knurl. If yours differ, make the bore the knurl diameter minus 0.6 and the length plus 0.8.
