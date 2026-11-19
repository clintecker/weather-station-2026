# Base v3: shelves build spec (pack tray, right fin, charger ledge, keepers)

> **Enclosure 4 (2026-11-17)** printed these shelves as this spec gives them (`sheets/audit-enc4/`):
> - tray Zb 21.4-24.4, Yb 0 to 58, with strap slots at Xb 13.5-16.5 and 89.5-92.5
> - fin Xb 96.25-100.25, Zb 21.4-48.4, Yb 0-109
> - left ledge Xb 0-9.85, top Zb 48.4, Yb 13.85-109
> - the right lid-end block Xb 102-121, Yb 101.75-109, Zb 38.4-48.4
> - the M3 keeper bores, Ø4, at (Xb 4.5, Yb 106) and (100.25, 106)
> - the rail from Zb 67
>
> The cards, backplane, plugs, EVM and gland nuts all clear.
>
> **One fault, from this spec:** the lip's chamfer (step 2) started at Yb 50. That's under the pack (54 deep, front at
> Yb 56), so the pack rode 4 up the ramp toward the EVM. **Fix 1 (asked of Clint):** extend the tray to **Yb 62** and
> start the 45° ramp at **Yb 56** (the pack's front). The ramp rises to Zb 30.41 at Yb 62. Steps 1 and 2 below now say
> so.

Enclosure 3 has no shelves. This spec adds them to the **next base print (v3)**, built on enclosure 3 exactly as
printed. Change nothing else in enclosure 3 except the left-wall rail (step 9).

The parts below the cards are:
- the **battery pack** on a **tray**
- above it, the **BQ25798EVM charger** on a **ledge** on the left wall and the top of a **fin** on the right
- a **cable space** under the tray, so every gland's cable can come out of its gland and turn toward the right column

Every dimension is in mm.
- **Numbers** come from `cage/cage.py` (`parts()`, `contents()`) as of 2026-11-17 (enclosure 4 plus fixes). Run
  `python3 cage/cage.py` and it prints the Zb stack and the tray and lip summary. It doesn't print the Xb and Yb
  extents of the shelf boxes. You'll find those in `cage.py` `parts()` (`cage.py:138-149`, `228-243`).
- **Wall faces** come from the enclosure 3 STL audit (`sheets/audit-enc3`).
- **EVM outline:** Clint's measurements and photo (IMG_8591, 2026-11-16).

## Why the shelves moved (read this first)

The enclosure 2 shelf spec put the tray 1.9 above the gland nuts and a ledge over the PG-9 bores. **No gland cable
could get out.**

- **The fix:** every shelf moved up as far as the backplane allows. That leaves **13.5 clear above the gland threads**
  (Zb 7.9 to 21.4) under the whole tray.
- **The limit:** nothing printed may sit in the backplane's install column (Xb 6.51 to 92.30 with its slide, from
  Zb 48.71, Yb 8 to the seam). You put the backplane in before you load the shelves. So the charger ledge's top is at
  **Zb 48.41**, 0.3 below the backplane's bottom edge.
- **Everything below stacks down from that:**

| Item | Zb |
|---|---|
| Ledge top (EVM board underside) | 48.41 |
| EVM underside parts (J6, tails) `[TBD-MEASURE]` | 44.41 to 48.41 |
| Margin | 2.0 |
| Pack, lying flat | 24.41 to 42.41 |
| Tray (3.0 thick) | 21.41 to 24.41 |
| Cable space | 7.9 (gland thread ends) to 21.41 |

The EVM's underside parts may turn out shorter than 4.0. If they do, the tray and pack move up by the difference, and
the cable space grows by the same amount.

## Coordinate frame

It's the same frame as `backplane-mount-spec.md`, and enclosure 3 is already mirrored. View the open base from the lid
side, with the glands at the bottom:

- **Xb** runs from the model's left inside face toward the right.
  - Enclosure 3's walls are thicker than the model's reference faces. Its **left wall face is at Xb 1.25** and its
    **right wall face is at Xb 122.25** (121.0 inside).
- **Zb** runs up from the model's bottom inside face. Enclosure 3's **bottom wall face is at Zb 1.0** and its top wall
  face is at Zb 168.5.
- **Yb** runs from the floor's inside face (the back, on the pole) toward the lid. The walls reach **Yb 117** (the
  seam), and the base is 120 deep outside. `cage.py` now models this enclosure 4 shell, so that closes audit item 2 in
  the model.
- **Lid-centre frame** (the CAD bot's): **X = Zb − 84.75, Y = 61.75 − Xb, Z = Yb + 3.0**. +Y is the left wall.

The shelves are plates across Xb and Yb, so "height" means Zb (up the box as it hangs). **When you print it** (floor on
the bed, Yb up), every plate below is a **vertical wall that grows from the floor or from a side wall**. That's why the
tray and the fin go all the way back to the floor.

## The EVM in the box

| | Xb | Yb | Zb |
|---|---|---|---|
| Board (90 × 90 × 1.6), component side up toward the cards | 8.25 to 98.25 | 11.6 to 101.6 | 48.41 to 50.01 |
| Parts above the board (15 tall `[TBD-MEASURE]`), with the overhangs: J6 1.5 past the left edge, J3, J5 and the BAT jumper 6 past the right | 6.75 to 104.25 | 11.6 to 101.6 | 50.01 to 65.01 |
| Underside parts (J6, solder tails) | 8.25 to 98.25 | 11.6 to 101.6 | 44.41 to 48.41 |
| J8, the EV2300/2400 I2C port (our I2C lead plugs in here), sticking out 12 past the lid edge | 23.25 to 35.25 | 101.6 to 113.6 | 48.41 to 58.41 |
| J8's plug and the lead's first bend `[TBD-MEASURE]` | 23.25 to 35.25 | to about 128.6 | to about 58.4 |

- **Orientation:** J8 faces the lid.
  - Look at the component side with J8 toward you (toward the lid). J6 (micro-USB) and the J1/J2 terminals are on the
    **left** edge.
  - J3 (SYS) and J5 (BATTERY) are on the **right** edge. Their wire entries face the right column, where the leads go.
    Their clamp screws are on top, under B4.
- **Clear of everything:**
  - The EVM's back edge (Yb 11.6) is 2.0 in front of the backplane's component face (Yb 9.6). Enclosure 4 has no
    backplane screw posts or M3 heads, only plain support pads. So nothing but the backplane itself sits behind the
    board's back edge.
  - Its top (Zb 65.0) is 12.6 under B4's tails (Zb 77.6).
  - Its top is also about 7.7 under the right corner post and the bar (Zb 72.73).
- **Screw terminals:** you can't reach them with the EVM in place, because B4 is 12 above. Wire them with the EVM out,
  and leave service loops.

## What to add to enclosure 3 (v3)

1. **The pack tray:** a plate at **Xb 1.25 to 96.25, Yb 0 to 62.0, Zb 21.41 to 24.41** (3.0 thick). Enclosure 4
   printed it to Yb 58.0 (fix 1).
   - **Joins:** mould it to the floor (Yb 0), to the left wall face (Xb 1.25) and to the right fin (step 3).
   - **Left end:** the bottom-left corner block stops at about Zb 16.4. The tray's left end rests on a 5 mm support
     block (Xb 1.25-12.0, Yb 0-58.0, Zb 16.41-21.41) that stands on the corner block.
   - **Lid frame:** Y +60.50 to −34.50, Z 3.0 to 65.0, X −63.34 to −60.34.
2. **The tray's front lip (fix 1):** a 45° ramp, **Xb 16.5 to 89.5**, from **Yb 56.0 at the tray face (Zb 24.41)**
   up to **Zb 30.41 at Yb 62.0**, the tray's front edge.
   - It stops the pack from sliding toward the lid. The pack lies flat on Yb 0 to 56 (it's 54 deep, set 2 off the
     floor).
   - **Print:** the ramp is its own 45° support, because it rises toward the tray's free edge. Enclosure 4 had the
     chamfer from Yb 50.0 to 56.0 under a lip at Yb 56-58. That put 6 mm of ramp under the pack's front edge.
   - **Lid frame:** Y +45.25 to −27.75, Z 59.0 (ramp foot) to 65.0, X −60.34 at the foot to −54.34 at Z 65.0.
3. **The right fin:** a wall at **Xb 96.25 to 100.25, Yb 0 to 109.0, Zb 21.41 to 48.41** (4 thick, 27 tall). It
   stands on the floor and holds two things:
   - the tray's right end (step 1)
   - **on its top, the charger ledge for the board's right edge.** The board rests on the fin's inner 2 (Xb 96.25
     to 98.25).
   - **Lid frame:** Y −34.50 to −38.50, Z 3.0 to 112.0, X −63.34 to −36.34.
   - **Clearance:** the fin's bottom is the tray's underside, so the cables pass under the fin into the right column.
   - The fin is 3.95 outside the backplane's slide (Xb 92.30). It's clear of the right corner post, which starts at
     Zb 72.73.
4. **The left charger ledge:** **Xb 1.25 to 10.25, Yb 10.1 to 103.0, Zb 38.41 to 48.41** overall, moulded to the left
   wall face.
   - It's 2 thick at its inner edge (Zb 46.41 to 48.41). Underneath, a 45° chamfer runs down to Zb 38.41 at the wall.
   - The left keeper (step 7) carries on in front of it to Yb 109.
   - It starts 0.5 in front of the backplane, clear of the backplane's left edge.
   - **Back-end chamfer:** its back end hangs in the air when you print it. So chamfer it 45° from Yb 10.1 at the wall
     to Yb 19.1 at Xb 10.25.
   - **Lid frame:** Y +60.50 to +51.50, Z 13.1 to 106.0, X −46.34 to −36.34.
5. **Notch both supports under the edge tails:**
   - **Left ledge:** the J1, J2 and J6 tails sit near the left edge. Notch the ledge's inner 4 (Xb 6.25 to 10.25) at
     **Yb 39.6 to 52.6** and **Yb 66.6 to 79.6**. Cut each notch's front end at 45° in plan, so it reaches 4 further
     forward at Xb 10.25. The ledge stays one piece along the wall.
   - **Right fin:** the J3 and J5 tails sit near the right edge. Cut a 3 deep pocket into the fin's top, Xb 96.25
     to 98.25, at **Yb 45.6 to 59.6** and **Yb 62.6 to 80.6**.
   - These positions come from scaling the photo `[TBD-MEASURE]`. Check them against the real board before you print,
     and widen a notch rather than narrow it.
6. **The back stop:** a block at **Xb 96.25 to 98.25, Yb 10.1 to 11.6, Zb 48.41 to 50.41**, on the fin top. It stops
   the board's back edge at Yb 11.6.
   - `cage.py` doesn't draw this block yet. Enclosure 4 printed without it.
   - **Lid frame:** Y −34.50 to −36.50, Z 13.1 to 14.6, X −36.34 to −34.34.
   - There's none on the left. The ledge there has to stay below Zb 48.71, the backplane's install column.
7. **The keeper (left) and the lid-end block (right)** at the front, each with an M3 heat-set insert. The bore is
   Ø4.0 × 6.5, the same as the retention bar's bores, and it opens upward (+Zb) in the block's top. Each top is at the
   ledge top, Zb 48.41.
   - **Left keeper:** **Xb 1.25 to 9.25, Yb 95.13 to 109.0, Zb 38.41 to 48.41**, moulded to the left wall. Its back is
     a 45° roof, from Yb 95.13 at the wall to Yb 103.13 at Xb 9.25. Its bore is at (Xb 4.5, Yb 106.0).
     - Lid frame: Y +60.50 to +52.50, Z 98.13 (at the wall, 106.13 at the roof's inner end) to 112.0, X −46.34 to
       −36.34.
   - **Right lid-end block:** **Xb 100.25 to 122.25 (the right wall), Yb 92.0 to 109.0, Zb 38.41 to 48.41**. Its back
     edge is a V: Yb 92.0 at its ends, reaching Yb 103 mid-span. It sits beside the fin's front end (fin Xb 96.25 to
     100.25, to Yb 109). Its bore is at (Xb 100.25, Yb 106.0).
     - Lid frame: Y −38.50 to −60.50, Z 95.0 (ends of the V) to 112.0, X −46.34 to −36.34. The fin's front end beside
       it is Y −34.50 to −38.50.
   - Both are below Zb 48.71, outside the backplane's install column, and clear of the board.
8. **Two strap slots** through the tray, for a hook-and-loop strap round the pack. Each is 3 wide across Xb and 20 long
   along Yb, at **Xb 15.0** and **Xb 91.0**, centred at Yb 29.
   - The left slot (Xb 13.5 to 16.5) is over the corner block's top. That top is at Zb 16.4 at most, and lower on its
     R8 inner corner. The slot is just right of the tray's support block (to Xb 12). So the strap passes under the tray
     in a gap of about 5.0.
9. **Raise the left-wall rail.** Enclosure 3's backplane groove rail on the left wall comes down to about Zb 58. There
   it hits the EVM's back-left corner.
   - The enclosure 3 STL check (commit 8289b23) found this rail was the only solid that the EVM's parts above the
     board met.
   - The first draft gave the overlap as Xb 7.0 to 8.5, Yb 11.8 to 12.8, Zb 58.7 to 64.7. Those figures came from a
     scratch mesh, and no committed audit output has them.
   - Start the rail at **Zb 67.0** (the EVM's top plus 2) instead. Keep the groove itself as printed above that.
   - `cage.py` draws it this way (`RAIL_Z0`). The backplane still sits 1.99 into the groove.

### Separate printed parts

- **The front clip:** it holds the board's front edge and goes on with two M3 screws into the inserts in step 7
  (`README.md`, the charger row).
  - Its shape isn't drawn in `cage.py` yet. The first draft of this spec had two keeper tabs, 14 × 8 × 3, each with a
    Ø3.4 hole 4 from one end and a **1.6 step down** on the other end. No other source has those numbers, so treat
    them as a sketch.
  - The step would press on the board's top face (Zb 50.01), because the insert tops are level with the board's
    underside.
  - The screw isn't chosen yet. The first draft named an M3 × 8 button head, but no BOM or build sheet lists one.
  - To take the board out, unscrew the front clip and slide the board toward the lid (`README.md`).

## Keep-outs (none of the shelves goes here)

- **Gland cable rise:** a column over each gland, from its thread end up to the tray's underside at Zb 21.41. The
  thread end is at Zb 6.0 for a PG-7 and Zb 7.9 for a PG-9.
  - Ø9.9 over each PG-7: Xb 26, 50 and 74 at Yb 25, and Xb 26 and 50 at Yb 60. There's no gland at Xb 74, Yb 60.
  - Ø12.5 over each PG-9, at Xb 98 in both rows. That makes 7 glands.
  - Nothing printed sits in Zb 7.9 to 21.41 anywhere between the corner blocks.
  - **Cable route:** each round cable rises, turns right under the tray and goes up the right column.
  - **The flat cables (G4 wind, G8 rain):** they rise at Xb 98 and lean 3 right under the fin, which starts at Zb
    21.41, into the column.
- **The right column (cable riser):** Xb 100.25 to the right wall face at 122.25, from above the corner block (Zb 16.4)
  up to B4.
  - It's clear from Yb 0 to 92. From Yb 92 to 109, the right lid-end block fills Zb 38.41 to 48.41.
  - **Narrow point:** J3, J5 and the BAT jumper reach into the column to Xb 104.25 (TBD) at Zb 50.01 to 65.01.
    `cage.py` reserves this along the board's full depth, Yb 11.6 to 101.6.
  - Every cable, and the EVM's SYS and BATTERY leads, use this column. Keep it empty.
- **The vent** at (Xb 50, Yb 85): the tray ends at Yb 62.
- **Backplane install column:** Xb 6.51 to 92.30, from Zb 48.71, Yb 8.0 to the seam. Nothing printed goes here.
- **Backplane screw posts:** there are none since enclosure 4, because the cards hold the backplane.
  - Only the three plain Ø6 support pads remain, Yb 0 to 8.0, at (58.58, 54.06), (78.90, 89.62) and (68.74, 127.72).
  - The Ø8 and Ø7 posts at (7.78, 54.06) and (86.63, 54.06) were enclosure 3.
  - The left ledge starts at Yb 10.1, in front of the pads.
  - With no screws, nothing stands on the backplane's front face behind the EVM. The EVM's back edge (Yb 11.6) is 2.0
    in front of the backplane (Yb 9.6). The old 0.35 figure was for the enclosure 3 screw heads (Yb 11.25).
- **Corner blocks** (lid screws): Xb 1.25 to 16.55 and from about 106.8 to the right wall, Zb up to about 16.4, the
  full depth. The tray passes over the left one.

## Checks (`cage/cage.py`)

- `cage.py` checks each content (the pack, the EVM, J8, and J6 with the tails) for 2.0 from:
  - the walls
  - every keep-out
  - every cage part, except the ledges, fin and tray that it sits on (`cage.py:815-823`)
- It doesn't check the contents against each other. Their 2.0 gaps come from how the stack is built
  (`cage.py:132-135`).
- **The gland cable rises are keep-outs:** no printed part or content may enter them.
- The EVM is 2.0 in front of the backplane, 12.6 below B4's tails and 2 below the rail.
- Nothing printed sits in the backplane's install column.
- We checked it against the enclosure 3 STL on 2026-11-16 (`sheets/audit-enc3`, `sl.py`). The tray, the pack, the fin,
  the ledge, the EVM's underside and J8 meet no solid in enclosure 3.
  - The EVM's parts above the board meet only the rail (step 9).
  - The cable space meets only the two corner blocks.
- We checked it against the enclosure 4 STL on 2026-11-17 (`sheets/audit-enc4`). The result was the same, except
  that the pack met the lip's ramp (Yb 50 to 56, 1197 mm³). Fix 1 deals with that.

## Still to measure

- **The EVM:** the tallest part above the board (15 assumed), and how far J6 and the tails reach below it (4
  assumed). The underside number sets the cable space.
- **Edge tails and notches:** the Yb ranges of the edge tails (step 5), from the board itself rather than the photo.
- **J8:** where J8 sits along the lid edge.
  - Your sketch says 15 from the left and 66 from the right, but those don't close on 90 with a 12 housing.
  - The photo scales J8's housing to about 12. With the sketch's 15 from the left, J8 ends about 63 from the right
    (derived, `sources.py` `evm_j8_x`).
  - Also measure how far the I2C lead's plug and bend reach past J8.
- **Cable bend:** bend one round port cable through 90° in 13, to confirm the cable space works.
