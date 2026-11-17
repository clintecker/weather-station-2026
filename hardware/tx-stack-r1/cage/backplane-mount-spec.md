# Enclosure 2: backplane mount build spec (the printed TX base)

> **Enclosure 4 (2026-11-17): no screw posts.** Clint removed both screw posts (bottom left and bottom right) and
> their M3 inserts. Nothing is drilled in the backplane and nothing screws it down: it lies on the three plain
> support pads, its left edge in the left wall's groove (the rail now starts at Zb 67.0), its factory right edge in
> the right corner post's slot (Zb 72.75 to 150.6), and **the four cards plugged into its sockets hold it in place**
> (Clint). Until the cards are in it is loose. Sections 2 and 4 below are updated; the "Changes" list is history. The
> two retention-bar inserts (Xb 5.00, Zb 76.5 and 146.5) stay. Audit: `sheets/audit-enc4/`.

**Enclosure 2** is the new printed base the TX is built into (not yet printed; Clint's CAD bot makes it from these
specs). Everything below is printed into it: nothing is glued in or cut by hand afterwards.

The backplane is the plated end of a BusBoard PAD3U padboard. It stands 8 mm off the base's inside floor on printed
posts with M3 heat-set inserts. The cards plug into its sockets from the lid side. Every dimension is in mm. The
numbers come from `layout/stack.py` and `cage/cage.py` (the factory-edge rectangle with 1x30 sockets, 2026-11-13).

## Changes from the snap-mount version (for the CAD bot)

The current enclosure 2 STL follows `backplane-snap-mount-spec.md`. Change it as follows:

0. **MIRROR enclosure 2 across the lid frame's Y = 0 plane** (left↔right as seen from the lid) before applying the
   changes below. The lid rim, the O-ring land and the lid screw holes are symmetric and unaffected; the glands, the
   vent and the SMA bulkhead move with the mirror. The current STL is the mirror image of the model: seen from the
   lid with the glands down, its card block is on the right, and a real card would then plug in backwards (header
   pin n on line 31−n, the RJ11 jacks facing the block). After the mirror the card block and the retention bar are
   on the **left** and the corner post on the **right**, which is what every coordinate below already describes.
1. **Remove** both snap hooks and their pillars (about Xb 56 to 62).
2. **Remove** the length stops, including the top stop (about Xb 30 to 50, Zb 150).
3. **Remove** the snap version's support pads (about Xb 60, Zb 79 and 118).
4. ~~**Add two screw posts**~~ (removed again in enclosure 4: no screws), floor to Yb 8.0, each with an M3 insert bore Ø4.0 × 6.5 from the top (section 2):
   - bottom left at **(Xb 7.78, Zb 54.06)**, Ø8.0, with a flat on its +Xb side 3.5 from its centre;
   - bottom right at **(86.63, 54.06)**, Ø7.0 (the board now has 31 lines, so its factory holes sit one pitch
     further right than the 84.09 of the first draft).
5. **Add three plain support posts**, Ø6.0, floor to Yb 8.0, no bore: at **(58.58, 54.06)** (under s20.2),
   **(78.90, 89.62)** (s28.16) and **(68.74, 127.72)** (s24.31). Every socket is now 1x30, so the socket solder joints
   run along the whole of holes 13, 19, 27 and 35 on the copper face: no post or pad may sit on those rows. Each of
   these keeps at least 1.5 from every joint (taken as a 1.27 fillet round its hole) and every bus wire; the
   closest is 3.35 (L7). The first draft's (58.58, 140.42) and (78.90, 82.00) are gone: the second sat right under a
   B4 socket joint (line 28, hole 13).
6. **Cut the backplane slot** into the right corner post's left (−Xb) face: **Xb 85.8 to 92.3 (6.5 deep), Yb 8.0 to
   10.1**, the post's full length, with a 45° roof from (92.3, 10.1) up to the face (section 6).
7. **Widen the right corner post** to **Xb 85.8 to 95.8** (was 93.8), so 3.5 of it stands behind the deeper slot;
   Zb 72.73 to 150.61 as before (the STL has about 86 to 94, 73 to 148).
8. **Keep** the left wall's groove and the rail below it (section 3), the card slots and the cut-backs.

## Coordinate frame

The **box frame** is the one `cage.py` uses, looking into the open base from the lid side, hung as on the pole
(glands at the bottom):

- **Xb** runs from the inside face of the **left** wall toward the right wall, left to right as you look in. The
  card block and the retention bar are on the left wall; the right corner post and the SMA bulkhead are on the right.
  The inside width is 123.5.
- **Zb** runs from the inside face of the **bottom** wall (the one with the glands) toward the top wall. The inside
  length is 169.5.
- **Yb** runs from the inside face of the **floor** (the back as hung) toward the lid. The floor is 3.0 thick, so
  Yb 0 is 3.0 above the outside of the back.

The lid-centre frame of `lid-rim-spec.md` (the CAD bot's and the STL's frame) is also given: **X = Zb − 84.75**
(positive toward the top wall), **Y = 61.75 − Xb** (positive toward the **left** wall) and Z = Yb + 3.0 (from the
outside of the back toward the lid). That frame is right-handed; so the box frame (Xb, Yb, Zb) is left-handed, which
is what makes Xb run left to right seen from the lid (`cage.to_lid`, layout check L12).

## 1. The backplane (not printed; for reference)

- **Board:** PAD3U, 2.54 pitch, 1.6 thick, **a plain rectangle** (no tab, no hacksaw). Lines run along Zb.
  - It is the PAD3U's **plated end**: the 31 rows next to its two factory mounting holes become lines 0 to 30, each
    the full **38 holes** (holes 1 to 38). Card header pin n sits straight over line n, so the full 1x30 header
    needs line 30, the end row itself. Socket holes stay at 13, 19, 27 and 35; every socket is 1x30 (lines 1 to 30).
  - **Only the left edge is cut** (scored midway between line 0 and the next row out, 1.27 from line 0). The right
    edge (beyond the mounting holes), the top and the bottom are the PAD3U's own.
- **Measured from Clint's scan** (300 dpi with a steel ruler, 2026-11-13; ±0.1; `sources.py` pad3u_*):
  - Mounting holes: **Ø2.80 drill, Ø3.75 copper ring**, on the 2nd and 37th of the 38 holes (88.9 apart),
    **2.65 beyond the end row's hole centres**. The pads beside them are left off.
  - The other end: two plain Ø1.5 holes, on the same two holes, midway between the last two rows; 2.23 from the last
    row to the edge.
  - Long sides: 2.81 from the outer holes' centres to the edge (2.84 and 2.78). Width 99.68.
  - The scan shows **61** rows (BusBoard says 62); the mounting holes sit where a 62nd would be.
  - **Not measurable from the scan:** the plated end's edge. It is cut off in all three pages. BusBoard's 160.02 less
    the rest puts it **2.83 beyond the mounting holes** (5.48 from line 30). `[TBD-MEASURE]` with calipers.
- **Outline: Xb 6.51 to 89.46, Zb 48.71 to 148.31** (83.0 × 99.6).
- **Mounting holes:** lower **(86.63, 54.06)**, level with hole 2; upper **(86.63, 142.96)**, level with hole 37.
- **Copper (back) face** at Yb 8.0, against the posts. The component face is at Yb 9.6.
- **Behind it, on the copper face:** the mux breakout on foam, at **Xb 11.59 to 52.23**, Zb 52.79 to 73.11, inside
  the 8 mm gap. Bus wires run along lines 1 to 18, and along B4's power lines 19 to 23 and 26 from hole 5 to hole 13.
  On lines 19 to 30 every other socket joint is an isolated pad (no wire), but it is still a solder joint on the
  copper face.
- **On the front, at the lower end:** R7 and R8 lie flat, 2.6 high; the leads to the EVM and the pack land on
  holes 6 of lines 19, 21 and 26.

## 2. Holding it: the cards, a groove and a slot (enclosure 4: no screws)

| Edge | Held by | Where (Xb, Zb) |
|---|---|---|
| Back (copper face) | Three plain support pads, tops at Yb 8.0 | see below |
| Left | The left wall's groove (section 3) and its rail | left edge, Zb 67.0 up |
| Right | A **slot in the right corner post** (section 6), 6.5 deep; both factory holes unused | right edge, Zb 72.75 up |
| Front | The four cards' headers in its sockets: plugged in, they hold it (Clint, 2026-11-17) | sockets at holes 13, 19, 27, 35 |

Enclosures 2 and 3 had two M3 screws here (the drilled line 0 hole 2 at (7.78, 54.06) and the lower factory hole,
drilled out to 3.2, at (86.63, 54.06)). Enclosure 4 dropped them; the notes below on the screws are history.

- **Screws: M3, not M4.** The factory hole is Ø2.8, so either size means drilling it out (3.2 for M3, 4.2 for
  M4). An M4 button head (ISO 7380: Ø7.6, 2.2 high) would reach Yb 11.8 there, 0.2 into the EVM's envelope (Yb 11.6,
  up to Zb 52.5). The M3 head (Ø5.7, 1.65) clears it by 0.35, as the old screws did. Use M4 only if the EVM measures
  further forward.
- **The drilled hole is 1.27 from the scored edge**, so it opens 0.3 into it. Drill it before snapping the edge;
  the head clamps 4 mm of FR4 beside it. That keeps the board a plain rectangle (no tab) with the bottom-left post
  under line 0.
- **Posts** (round, from the floor to a flat top at **Yb 8.0**, R1.0 fillet at the foot, insert bore **Ø4.0 × 6.5**
  for an M3 × 5.7 heat-set insert):
  - **Bottom left: Ø8.0 with a flat** on its +Xb side 3.5 from its centre (as Clint printed it): 0.31 to the mux.
  - **Bottom right: Ø7.0 at (86.63, 54.06).** Below the right corner post (which starts at Zb 72.73); clear of the
    EVM (it is in front, from Yb 11.6) and of the charger's right rib (Xb 94.75).
- **Plain support posts** (Ø6, floor to Yb 8.0, no bore, no hole in the board) under **s20.2 (58.58, 54.06), s28.16
  (78.90, 89.62) and s24.31 (68.74, 127.72)**: they take the cards' push between the screws. Each is off the socket
  rows (holes 13, 19, 27, 35) and at least 1.5 clear of every joint and bus wire on the copper face (L7).

## 3. The left edge: a groove

The board's left edge sits in a **groove** in the left wall's slot-side face (Xb 8.5), as before:

- **Section:** Xb 6.0 to 8.5 (2.5 deep), Yb 8.0 to 10.1, a 45° chamfered roof up to the wall face. The board's edge
  (Xb 6.51) is 1.99 under the roof.
- **Below the wall, a rail** carries the groove down to **Zb 67.0** (enclosure 4; 2 above the EVM's top).

## 4. Fitting it, and the checks

**To fit the board** (every card out):

1. Tilt it and push its factory right edge into the right corner post's slot, to the slot's end (Xb 92.30). Its
   left edge is then at Xb 9.35, 0.85 clear of the left wall's face (8.5), so the left side comes down past it.
2. Lower the left side onto the pads, then slide the board 2.84 left: its left edge goes into the groove and the
   right edge stays 3.66 in the slot.
3. No screws (enclosure 4): plug the cards in; they hold it.

The factory right edge's position is `[TBD-MEASURE]`. With the 6.5 slot the fit works with the edge up to 6.13
past line 30's centres, 0.65 more than BusBoard's numbers give (5.48); past that, sand it back.

**Checks** (`cage/cage.py` backplane_checks, `layout/layout_checks.py` L7):

- The pad tops and the groove and slot floors are all at Yb 8.0.
- No screw hole in the board (L7 fails if one comes back). The two factory holes are 35 pitches apart, and neither
  ring reaches the edge.
- Nothing printed is inside the board's slab above Yb 8.0, except the groove's and the slot's roofs, in place and
  pushed to the slot's end.
- The mux clears every pad, in place and pushed right.
- Every support pad keeps 1.5 from each copper-face joint (a 1.27 fillet round its hole) and each bus wire
  (L7, `check_copper_face`).

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

B4 to B2 is 6 holes (15.24) again: the WAGO junction that needed 8 has moved to the backplane (lines 21-22), and
B4's tallest part is now 10.1 (U6's JST PH socket), which needs 12.1 of the 13.64 between the cards. B2 to B1 and
B1 to B3 stay 8 holes. The sockets are at backplane holes 13 (B4), 19 (B2), 27 (B1) and 35 (B3). Enclosure 2
prints the card slots at these heights (the STL's Zb 79, 94, 115 and 136 match).

**Left wall:** a solid block from Xb 0 (on the base's left wall) to Xb 8.5, Yb 0 to 63.37, Zb 72.73 to 150.61.

- **Card slots:** cut into its +Xb face (the face at Xb 8.5), **2.0 deep** (Xb 6.5 to 8.5), from Yb 9.6 to 63.37.
- **Backplane groove:** the groove from section 3 is also cut into that face.
- **Retention-bar inserts:** two M3 × 5.7 heat-set inserts in its front face (Yb 63.37), at Xb 5.00 and Zb 76.50 and
  146.50, as printed in enclosure 3 (audited 2026-11-16). Each bore is Ø4.0 × 6.5 deep. The lower bore leaves only
  0.48 of plastic to the floor of the B4 slot: set that insert gently, then run a 1.6 offcut through the B4 slot.

**Right corner post:** a block Xb 85.8 to 95.8, Yb 0 to 21.96, Zb 72.73 to 150.61.

- **Backplane slot:** in its −Xb face, **Xb 85.8 to 92.3 (6.5 deep), Yb 8.0 to 10.1**, the post's full length, a 45° chamfered roof up to the face. It takes the board's factory right edge (section 4).

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

- **Heat-set insert** (now only the retention bar's two): its length and its largest (knurl) diameter, with calipers. The bore assumes 5.7 long
  and about 4.6 across the knurl. If yours differ, make the bore the knurl diameter minus 0.6 and the length plus 0.8.

## Appendix: old printed base (not used)

Clint's first printed base (three posts, the groove in the wall only) is not used for the TX. It would need the
lower-right post and the support pads added and the 6.5 slot cut into a wider right corner post; enclosure 2 prints them.
