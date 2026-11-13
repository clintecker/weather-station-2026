# Backplane mount: build spec (printed TX base, floor posts)

The backplane is a piece of BusBoard PAD3U padboard. It stands 8 mm off the base's inside floor on printed posts with
M3 heat-set inserts. The cards plug into its sockets from the lid side. Every dimension is in mm. The numbers come from
`layout/stack.py` and `cage/cage.py` as of 7c780f7, with section 6 updated for the 8-hole B4-B2 pitch.

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

- **Board:** PAD3U, 2.54 pitch, 1.6 thick, cut as an **L**. Lines run along Zb.
  - The main piece is 30 lines × 39 holes (lines 0 to 29). That is the widest the fitting slide allows: its right
    edge, shifted 2.5 to the right, stops 0.59 short of the right corner post (Xb 85.8). A PAD3U is 38 holes across.
  - A **tab** carries one more line, line −1, beside holes 1 to 3.
  - The inside corner of the L is a hacksaw cut.
- **Outline:**
  - Main piece: **Xb 6.51 to 82.71**, Zb 50.25 to 149.31.
  - Tab: **Xb 3.97 to 6.51, Zb 50.25 to 57.87** (2.54 × 7.62). Its left edge is midway between lines −2 and −1, 3.81
    from line 0's hole centres. That leaves 2.21 of FR4 left of the 3.2 hole at s0.2.
- **Copper (back) face** at Yb 8.0, against the posts. The component face is at Yb 9.6.
- **Behind it, on the copper face:** the mux breakout on foam, at **Xb 11.59 to 52.23**, Zb 52.79 to 73.11, inside
  the 8 mm gap. It is boxed in: 0.31 from the bottom-left post's flat in place, and 0.35 from the bottom-right post
  during the fitting slide (section 3). Bus wires run along lines 1 to 18 (Xb 10.32 to 53.50), and along B4's
  power lines 19 to 23 and 26 from hole 5 to hole 13 (Xb 56.04 to 73.82, Zb 61.68 to 82.00).
- **On the front, at the lower end:** R7 (line 21 to line 24, hole 7) and R8 (line 22 hole 8 to line 23 hole 11) lie
  flat, 2.6 high; the leads to the EVM and the pack land on holes 6 of lines 19, 21 and 26.

## 2. Posts: three screw posts

| Post | Xb | Zb | X | Y | From the inside walls |
|---|---|---|---|---|---|
| Bottom left | 7.78 | 54.06 | −30.69 | −53.97 | 7.78 from left, 54.06 from bottom |
| Bottom right | 58.58 | 54.06 | −30.69 | −3.17 | 64.92 from right, 54.06 from bottom |
| Top right | 58.58 | 140.42 | +55.67 | −3.17 | 64.92 from right, 29.08 from top |

- **Spacing:** 50.80 across (20 holes) and 86.36 along (34 holes). These are the board's line 0 / line 20, holes
  2 / 36. The bottom-left screw goes through the tab.
- **The wider board keeps these three posts and screws.** No new screw post is needed in Clint's printed base:
  - The B4 socket (1x26, hole 13) ends at line 26. The B3 socket at hole 37 stays 1x18 and ends at Xb 54.81, so the
    s20.36 screw head (Xb 55.73 to 61.43) clears it by 0.92.
  - Line 20 carries the charger battery + only from hole 5 up, clear of the s20.2 post (its edge at Zb 57.56).
  - Lines 21 to 29 (Xb 61 to 82.7) overhang the right-hand posts by up to 24. Only the right end of B4's socket
    pushes there. **Optional:** a plain Ø6 × 8.0 printed spacer glued to the floor under line 28, hole 13 (Xb 78.90,
    Zb 82.00) supports it. Nothing else is on line 28.
- **Post:** a round boss, from the floor (Yb 0) to a flat top at **Yb 8.0**, with an R1.0 fillet at its foot.
  - **Bottom left: Ø8.0, with a flat on its +Xb side 3.5 from its centre** (at Xb 11.28). This is as first specified
    and as Clint printed it. It leaves 1.2 round the knurl on the flat side, 1.7 elsewhere, and 0.31 to the mux.
  - **Bottom right and top right: Ø7.0.** That leaves 1.2 round the knurl.
- **Insert bore:** **Ø4.0 × 6.5 deep** from the post top, for an M3 × 5.7 heat-set insert. It's a blind hole, with
  1.5 of post left under it.
- **Screws:** M3 × 6 button head (ISO 7380: head Ø5.7, 1.65 high), no washer, through 3.2 holes drilled in the board.
  - Each head covers its neighbouring holes on the front: line 1 holes 1 to 3 at s0.2, and line 19 holes 1 to 3 at
    s20.2. Nothing is in those holes, and the PAD3U's pads are on the back only.
  - The tops of the two bottom heads are at Yb 11.25. The EVM's envelope starts at Yb 11.6, so they clear it by only
    0.35. That envelope (`evm`) is `[TBD-MEASURE]`: the EVM's back edge there is its bare board.

**Why the right posts are Ø7:** at Ø7 they clear line 18's pads by 0.7. Press their inserts slowly, with the iron a
little cooler.

## 3. The left edge above the tab: a groove

A screw at the fourth corner (Xb 7.78, Zb 140.42) won't work. It is inside the left wall's slot side (Xb 6.5 to 8.5,
Zb 72.73 to 155.69), and its head would hit B3's socket at hole 35. Instead, the board's left edge above the tab sits
in a **groove**:

- **In the left wall** (section 6): in its slot-side face (the face at Xb 8.5), Zb 72.73 to 155.69.
- **Below the wall, a rail:** a block Xb 0 to 8.5, Yb 0 to 13.6, **Zb 58.56 to 72.73**, joined to the wall's foot
  and moulded on the base's left wall and floor. The same groove runs through it.
  - It stops 0.5 above the bottom-left post (top at Zb 58.06) and 0.69 above the tab (Zb 57.87).
  - It is well above the charger: the EVM's envelope tops out at Zb 52.5.
- **Section:** Xb 6.0 to 8.5 (2.5 deep, with 0.5 clearance past the board's edge), Yb 8.0 to 10.1.
- **Floor:** the groove floor is at **Yb 8.0**, level with the post tops. It holds up the board's left edge.
- **Roof:** a 45° chamfer, rising from (Xb 6.0, Yb 10.1) to the wall face (Yb 12.6), so it prints without support.
- **If your base was printed to the first spec** (three posts, groove in the wall only): add the rail if you can. If
  not, the left edge is unsupported between the tab and Zb 72.73, but the bottom-left screw holds that corner.

**To fit the board:**

1. Lower it onto the posts 2.5 to the right (+Xb). The tab is then at Xb 6.47 to 9.01, under the rail's foot.
2. Slide it left: the edge goes into the groove, and the tab comes to rest on the bottom-left post.
3. Drive the three screws.

## 4. Checks

- The post tops and the groove floor are all at Yb 8.0, flat to ±0.1.
- Every post centre falls on a board hole, on the 2.54 grid listed above.
- Nothing printed lies inside the board outline or the tab at Yb above 8.0, except the groove roof over the board's
  left 2 mm. This holds in place and shifted 2.5 to the right (the slide-in).
- The board has 2.5 of free travel to the right before anything stops it: 3.09 to the right corner post (Xb 85.8).
- The tab's edge (Xb 3.97) is clear of the base's left wall (Xb 0). The EVM is 2.0 in front of the board's front face.
- The screw heads cover no used hole and meet nothing printed; they clear the EVM's envelope (0.35, see section 2).
- The rail starts above the tab and the bottom-left post.

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
| B2 | 101.05 | 99.30 to 101.20 |
| B1 | 121.37 | 119.62 to 121.52 |
| B3 | 141.69 | 139.94 to 141.84 |

B4 to B2 is 8 holes (20.32), set when a WAGO junction sat on B4 (it has since moved to the backplane as lines 21-22; the
heights stay because Clint's base is printed to them);
B2 to B1 and B1 to B3 stay 8 holes.

**Left wall:** a solid block from Xb 0 (on the base's left wall) to Xb 8.5, Yb 0 to 63.37, Zb 72.73 to 155.69.

- **Card slots:** cut into its +Xb face (the face at Xb 8.5), **2.0 deep** (Xb 6.5 to 8.5), from Yb 9.6 to 63.37.
- **Backplane groove:** the groove from section 3 is also cut into that face.
- **Retention-bar inserts:** two M3 × 5.7 heat-set inserts in its front face (Yb 63.37), at Xb 3.25 and Zb 76.0 and
  152.0. Each bore is Ø4.0 × 6.5 deep. *These positions are my call; the model doesn't fix them yet.*

**Right corner post:** a block Xb 85.8 to 93.8, Yb 0 to 21.96, Zb 72.73 to 155.69.

- **Card slots:** cut into its −Xb face (the face at Xb 85.8), **2.3 deep** (Xb 85.8 to 88.1), from Yb 9.6 to
  22.06, which is through its front.
- **Cut-backs:** above B2 and above B1, the post stops at **Yb 15.15** over the full post width. This clears the
  cards' back breakouts and plugs.

  | Above | Zb |
  |---|---|
  | B2 | 101.05 to 117.62 |
  | B1 | 121.37 to 137.94 |

**Retention bar:** a separate printed part, 12.0 (Xb 0 to 12.0) × 2.5 (Yb 63.37 to 65.87) × 82.96 (Zb 72.73 to
155.69). It sits flat on the left wall's front face.

- It screws to the left wall's front face, with Ø3.4 clearance holes at the two insert positions above.
- It covers each card's front-left corner, so no card can slide out.
- 1.0 is left between the bar and the cards' front edges (Yb 62.37). The sockets' pins engage far deeper than that.

## 5. Measure before printing

- **Heat-set insert:** its length and its largest (knurl) diameter, with calipers. The bore above assumes 5.7 long
  and about 4.6 across the knurl. If yours differ, make the bore the knurl diameter minus 0.6 and the length plus 0.8.
