# Base v3: shelves build spec (pack tray, right fin, charger ledge, keepers)

> **Enclosure 4 (2026-11-17)** prints these shelves as specified below (`sheets/audit-enc4/`): tray Zb 21.4-24.4, Yb 0
> to 58, strap slots at Xb 13.5-16.5 and 89.5-92.5; fin Xb 96.25-100.25, Zb 21.4-48.4, Yb 0-109; left ledge Xb 0-9.85,
> top Zb 48.4, Yb 13.85-109; the right lid-end block Xb 102-121, Yb 101.75-109, Zb 38.4-48.4; the M3 keeper bores Ø4 at
> (Xb 4.5, Yb 106) and (100.25, 106); the rail from Zb 67. The cards, backplane, plugs, EVM and gland nuts all clear.
> **One fault, from this spec:** the lip's chamfer (step 2) started at Yb 50, under the pack (54 deep, front at Yb
> 56), so the pack rode 4 up the ramp toward the EVM. **Fix 1 (asked of Clint):** extend the tray to **Yb 62** and start
> the 45° ramp at **Yb 56** (the pack's front), rising to Zb 30.41 at Yb 62. Steps 1 and 2 below now say so.

Enclosure 3 has no shelves. This spec adds them to the **next base print (v3)**, built on enclosure 3 exactly as
printed. Change nothing else in enclosure 3 except the left-wall rail (step 9).

The parts below the cards are:
- the **battery pack** on a **tray**;
- above it, the **BQ25798EVM charger** on a **ledge** on the left wall and the top of a **fin** on the right;
- a **cable space** under the tray, so every gland's cable can come out of its gland and turn toward the right column.

Every dimension is in mm.
- **Numbers from `cage/cage.py`** (`parts()`, `contents()`), 2026-11-16: run `python3 cage/cage.py` to see them.
- **Wall faces** come from the enclosure 3 STL audit (`sheets/audit-enc3`).
- **EVM outline:** Clint's measurements and photo (IMG_8591, 2026-11-16).

## Why the shelves moved (read this first)

The enclosure 2 shelf spec put the tray 1.9 above the gland nuts and a ledge over the PG-9 bores. **No gland cable
could get out.**

- **The fix:** every shelf moved up as far as the backplane allows. That leaves **13.5 clear above the gland threads**
  (Zb 7.9 to 21.4) under the whole tray.
- **The limit:** nothing printed may sit in the backplane's install column (Xb 6.51 to 92.30 with its slide, from
  Zb 48.71, Yb 8 to the seam). The backplane goes in before the shelves are loaded. So the charger ledge's top is at
  **Zb 48.41**, 0.3 below the backplane's bottom edge.
- **Everything below is stacked down from that:**

| Item | Zb |
|---|---|
| Ledge top (EVM board underside) | 48.41 |
| EVM underside parts (J6, tails) `[TBD-MEASURE]` | 44.41 to 48.41 |
| Margin | 2.0 |
| Pack, lying flat | 24.41 to 42.41 |
| Tray (3.0 thick) | 21.41 to 24.41 |
| Cable space | 7.9 (gland thread ends) to 21.41 |

If the EVM's underside parts turn out shorter than 4.0, the tray and pack move up by the difference and the cable space
grows by that much.

## Coordinate frame

The same frame as `backplane-mount-spec.md`, and enclosure 3 is already mirrored. Look into the open base from the lid
side, glands at the bottom:

- **Xb** runs from the model's left inside face toward the right.
  - Enclosure 3's walls are thicker than the model's: its **left wall face is at Xb 1.25** and its **right wall face
    at Xb 122.25** (121.0 inside).
- **Zb** runs up from the model's bottom inside face. Enclosure 3's **bottom wall face is at Zb 1.0** and its top
  wall face at Zb 168.5.
- **Yb** runs from the floor's inside face (the back, on the pole) toward the lid. Enclosure 3's walls reach about
  **Yb 117**. `cage.py` still has the old 100-deep shell, with the seam at 97; that is audit item 2.
- **Lid-centre frame** (the CAD bot's): **X = Zb − 84.75, Y = 61.75 − Xb, Z = Yb + 3.0**. +Y is the left wall.

The shelves are plates across Xb and Yb, so "height" means Zb (up the box as it hangs). **When printed** (floor on
the bed, Yb up), every plate below is a **vertical wall growing from the floor or from a side wall**. That is why the
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
  - Looking at the component side with J8 toward you (toward the lid), J6 (micro-USB) and the J1/J2 terminals are on
    the **left** edge.
  - J3 (SYS) and J5 (BATTERY) are on the **right** edge, and their screws open toward the right column. That's where
    the leads go.
- **Clear of everything:** the EVM's back edge is 2.0 in front of the backplane's component face (Yb 9.6). Its top
  (Zb 65.0) is 12.6 under B4's tails (Zb 77.6), and 7 under the right corner post and the bar. The M3 heads on the
  backplane posts are 0.35 behind the board's back edge, so the back stop (step 6) holds it there.
- **Screw terminals:** you can't reach them with the EVM in place, because B4 is 12 above. Wire them with the EVM
  out, leaving service loops.

## What to add to enclosure 3 (v3)

1. **The pack tray:** a plate at **Xb 1.25 to 96.25, Yb 0 to 62.0, Zb 21.41 to 24.41** (3.0 thick; enclosure 4
   printed it to Yb 58.0: fix 1).
   - **Joins:** it is moulded to the floor (Yb 0), to the left wall face (Xb 1.25) and to the right fin (step 3). It
     sits on top of the bottom-left corner block, which stops at about Zb 18.
   - **Lid frame:** Y +60.50 to −34.50, Z 3.0 to 65.0, X −63.34 to −60.34.
2. **The tray's front lip (fix 1):** a 45° ramp, **Xb 16.5 to 89.5**, from **Yb 56.0 at the tray face (Zb 24.41)**
   up to **Zb 30.41 at Yb 62.0**, the tray's front edge. It stops the pack sliding toward the lid; the pack lies flat
   on Yb 0 to 56 (it is 54 deep, set 2 off the floor).
   - **Print:** the ramp is its own 45° support (it rises toward the tray's free edge). Enclosure 4 had the chamfer
     from Yb 50.0 to 56.0 under a lip at Yb 56-58: that put 6 mm of ramp under the pack's front edge.
   - **Lid frame:** Y +45.25 to −27.75, Z 59.0 (ramp foot) to 65.0, X −60.34 at the foot to −54.34 at Z 65.0.
3. **The right fin:** a wall at **Xb 96.25 to 100.25, Yb 0 to 109.0, Zb 21.41 to 48.41** (4 thick, 27 tall), standing on
   the floor. It holds:
   - the tray's right end (step 1);
   - **on its top, the charger ledge for the board's right edge.** The board rests on the fin's inner 2 (Xb 96.25
     to 98.25).
   - **Lid frame:** Y −34.50 to −38.50, Z 3.0 to 112.0, X −63.34 to −36.34.
   - **Clearance:** the fin's bottom is the tray's underside, so the cables pass under the fin into the right column.
   - The fin is 0.45 outside the backplane's slide (Xb 92.30) and clear of the right corner post, which starts at
     Zb 72.
4. **The left charger ledge:** **Xb 1.25 to 10.25, Yb 10.1 to 103.6, Zb 46.41 to 48.41**, moulded to the left wall
   face.
   - It starts 0.5 in front of the backplane, clear of the backplane's left edge and of the bottom-left post.
   - **Chamfer:** its back end hangs in the air when printed, so chamfer it 45° underneath, from Yb 10.1 at the wall to
     Yb 19.1 at Xb 10.25.
   - **Lid frame:** Y +60.50 to +51.50, Z 13.1 to 106.6, X −38.34 to −36.34.
5. **Notch both supports under the edge tails:**
   - **Left ledge:** the J1, J2 and J6 tails sit near the left edge, so leave out the left ledge at **Yb 39.6 to 52.6**
     and **Yb 66.6 to 79.6**. That leaves three ledge pieces.
   - **Right fin:** the J3 and J5 tails sit near the right edge, so cut a 3 deep pocket into the fin's top, Xb 96.25
     to 98.25, at **Yb 45.6 to 59.6** and **Yb 62.6 to 80.6**.
   - These positions are scaled from the photo `[TBD-MEASURE]`. Check them against the real board before printing,
     and widen a notch rather than narrow it.
6. **The back stop:** a block **Xb 96.25 to 98.25, Yb 10.1 to 11.6, Zb 48.41 to 50.41**, on the fin top. It stops the
   board's back edge at Yb 11.6.
   - **Lid frame:** Y −34.50 to −36.50, Z 13.1 to 14.6, X −36.34 to −34.34.
   - There is none on the left: there the ledge has to stay below Zb 48.71, the backplane's install column.
7. **Two keeper bosses** at the front, one each side, with an M3 heat-set insert in each. The bore is Ø4.0 × 6.5, the
   same as the backplane posts, and it opens upward (+Zb) in the boss top. Each boss top is at the ledge top,
   Zb 48.41.
   - **Left:** **Xb 1.25 to 9.25, Yb 103.0 to 109.0, Zb 38.41 to 48.41**, moulded to the left wall, with its bore at
     (Xb 4.5, Yb 106.0).
     - Lid frame: Y +60.50 to +52.50, Z 106.0 to 112.0, X −46.34 to −36.34.
   - **Right:** **Xb 96.25 to 104.25, Yb 103.0 to 109.0, Zb 38.41 to 48.41**, on the fin's front end, with its bore at
     (Xb 100.25, Yb 106.0).
     - Lid frame: Y −34.50 to −42.50, Z 106.0 to 112.0, X −46.34 to −36.34.
   - Both bosses are below Zb 48.71, outside the backplane's install column, and in front of the board.
8. **Two strap slots** through the tray, for a hook-and-loop strap round the pack: 3 wide across Xb and 20 long along
   Yb, at **Xb 15.0** and **Xb 91.0**, centred at Yb 29.
   - The left one is over the corner block's top (Zb about 18), so the strap passes under the tray in the 3.4 gap.
9. **Raise the left-wall rail.** Enclosure 3's backplane groove rail on the left wall comes down to about Zb 58. Where
   it reaches Xb 7.0 to 8.5 at Yb 11.8 to 12.8, it hits the EVM's back-left corner at Zb 58.7 to 64.7.
   - Start the rail at **Zb 67.0** (the EVM's top plus 2) instead. Keep the groove itself as printed above that.
   - `cage.py` draws it this way (`RAIL_Z0`). The backplane still sits 1.99 into the groove.

### Separate printed parts

- **Two keeper tabs:** 14 × 8 × 3, a Ø3.4 hole 4 from one end, and a **1.6 step down** on the other end. The step
  presses on the board's top face (Zb 50.01), because the boss tops are level with the board's underside.
  - Fit each with an M3 × 8 button head. Swing the tab over the board's front corner to hold it, and away to slide
    the board out.

## Keep-outs (none of the shelves goes here)

- **Gland cable rise:** a column over each gland from its thread end (Zb 7.9) to the tray's underside (Zb 21.41).
  - Ø9.9 over each PG-7 at Xb 26, 50 and 74, and Ø12.5 over each PG-9 at Xb 98, in the rows at Yb 25 and 60.
  - Nothing printed sits in Zb 7.9 to 21.41 anywhere between the corner blocks.
  - **Cable route:** each round cable rises, turns right under the tray and goes up the right column.
  - **The flat cables (G4 wind, G8 rain):** they rise at Xb 98 and lean 3 right under the fin, which starts at Zb
    21.41, into the column.
- **The right column (cable riser):** Xb 100.25 to the right wall face at 122.25, Zb 18 (above the corner block) up to
  B4, for the full depth.
  - **Narrow point:** only J3, J5 and the BAT jumper reach into it, to Xb 104.25 at Zb 50 to 65 and Yb 46 to 80.
  - Every cable, and the EVM's SYS and BATTERY leads, use this column. Keep it empty.
- **The vent** at (Xb 50, Yb 85): the tray ends at Yb 62.
- **Backplane install column:** Xb 6.51 to 92.30, from Zb 48.71, Yb 8.0 to the seam. Nothing printed goes here.
- **Backplane screw posts:** bottom left Ø8 at (7.78, 54.06), bottom right Ø7 at (86.63, 54.06), Yb 0 to 8.0.
  - The left ledge starts at Yb 10.1, in front of both.
  - Their M3 heads reach Yb 11.25, 0.35 behind the board's back edge.
- **Corner blocks** (lid screws): Xb 1.25 to 16.55 and from about 106.8 to the right wall, Zb up to about 18, the full
  depth. The tray passes over the left one.

## Checks (`cage/cage.py`)

- Each content (the pack, the EVM, J6 and the tails, J8) keeps 2.0 from every wall, keep-out, cage part and the
  others.
- **The gland cable rises are keep-outs:** no printed part or content may enter them.
- The EVM is 2.0 in front of the backplane, 12.6 below B4's tails and 2 below the rail.
- Nothing printed sits in the backplane's install column.
- Checked against the enclosure 3 STL on 2026-11-16 (`sheets/audit-enc3`, `sl.py`): the tray, the pack, the fin, the
  ledge, the EVM's underside and J8 meet no solid in enclosure 3.
  - The EVM's parts above the board meet only the rail (step 9).
  - The cable space meets only the two corner blocks.
- Checked against the enclosure 4 STL on 2026-11-17 (`sheets/audit-enc4`): the same, except the pack meets the lip's
  ramp (Yb 50 to 56, 1197 mm³): fix 1.

## Still to measure

- **The EVM:** the tallest part above the board (15 assumed) and how far J6 and the tails reach below it (4
  assumed). The underside number sets the cable space.
- **Edge tails and notches:** the Yb ranges of the edge tails (step 5), from the board itself rather than the photo.
- **J8:** where J8 sits along the lid edge. Your sketch says 15 from the left and 66 from the right, but those don't
  close on 90 with a 12 housing; the photo gives about 63. Also, how far the I2C lead's plug and bend reach past J8.
- **Cable bend:** bend one round port cable through 90° in 13 to confirm the cable space works.
